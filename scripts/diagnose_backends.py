#!/usr/bin/env python3
"""
Backend diagnostics for fwagent. Answers: which simulator backends REALLY run,
and if not, why. Writes every command and its output to logs/diagnostics/<time>/
and zips it (secrets redacted) so you can hand the zip over for review.

Run from the project root, inside the virtualenv:
    python scripts/diagnose_backends.py
    python scripts/diagnose_backends.py --e2e --tests
    python scripts/diagnose_backends.py --gz-world worlds/plant.sdf --renode-resc boards/renode/stm32.resc \
        --wokwi-project firmware_samples/cooling_fan_buggy
Flags: --e2e runs `fwagent run` once per backend; --tests runs pytest.
Command flags for gz/renode/wokwi-cli differ by version; failures are logged, not hidden.
"""
import argparse, datetime, json, os, platform, re, shutil, signal, subprocess, sys, time, zipfile
from pathlib import Path

ROOT = Path.cwd()
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.environ["PYTHONPATH"] = f"{SRC}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"

STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "logs" / "diagnostics" / STAMP
SECRET_HINT = re.compile(r"(TOKEN|KEY|SECRET|PASSWORD)", re.I)
RESULTS = []


def redact(text: str) -> str:
    for k, v in os.environ.items():
        if SECRET_HINT.search(k) and v and len(v) >= 6:
            text = text.replace(v, f"<redacted:{k}>")
    return text


def sh(name, cmd, timeout=60, cwd=None):
    """Run a command, log it to OUT/<name>.log, return (rc, output)."""
    log = OUT / f"{name}.log"
    started = time.time()
    env = dict(os.environ)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd or ROOT, env=env)
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc, out = 124, ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + f"\n[TIMEOUT after {timeout}s]"
    except FileNotFoundError:
        rc, out = 127, "[command not found]"
    except Exception as e:
        rc, out = 1, f"[error: {e}]"
    log.write_text(redact(f"$ {' '.join(map(str, cmd))}\n[exit {rc}, {time.time()-started:.1f}s]\n\n{out}"))
    return rc, out


def record(section, status, detail):
    RESULTS.append({"section": section, "status": status, "detail": detail})
    print(f"[{status:<4}] {section:<28} {detail}")


def version_of(tool, args):
    exe = shutil.which(tool)
    if not exe:
        return None
    rc, out = sh(f"ver_{tool}", [exe, *args], timeout=20)
    return (out.strip().splitlines() or ["?"])[-1] if rc == 0 else f"found, version cmd failed (exit {rc})"


def section_env():
    info = {"python": platform.python_version(), "os": platform.platform(), "cwd": str(ROOT),
            "in_venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
            "wsl": "microsoft" in platform.release().lower()}
    for tool, args in [("git", ["--version"]), ("g++", ["--version"]), ("node", ["--version"]),
                       ("arduino-cli", ["version"]), ("gz", ["sim", "--versions"]),
                       ("renode", ["--version"]), ("wokwi-cli", ["--version"])]:
        info[tool] = version_of(tool, args) or "NOT FOUND"
    info["env_vars_set"] = {k: bool(os.environ.get(k)) for k in
                            ("WOKWI_CLI_TOKEN", "LLM_API_KEY", "GZ_SIM_RESOURCE_PATH")}
    (OUT / "environment.json").write_text(json.dumps(info, indent=2))
    sh("pip_freeze", [sys.executable, "-m", "pip", "freeze"])
    record("environment", "INFO", f"python {info['python']}, venv={info['in_venv']}, WSL={info['wsl']}")
    return info


def section_repo():
    sh("git_status", ["git", "status", "--short", "--branch"])
    sh("git_log", ["git", "log", "-5", "--oneline"])
    listing = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")) if (ROOT / "src").exists() else []
    (OUT / "source_files.txt").write_text("\n".join(listing))
    record("repository", "INFO", f"{len(listing)} python files under src/")


def section_static_audit():
    """Detect adapters that never start the tool they claim to use."""
    sim_dir = ROOT / "src" / "fwagent" / "simulator"
    if not sim_dir.exists():
        return record("static audit", "SKIP", "src/fwagent/simulator not found")
    lines = []
    for f in sorted(sim_dir.glob("*.py")):
        src = f.read_text(errors="ignore")
        launches = len(re.findall(r"Popen\(|subprocess\.run\(", src))
        delegates = "HostHALSimulator(" in src
        name = f.name
        if name.endswith("adapter.py") or name in ("renode.py", "wokwi_cli.py"):
            if launches <= 1 and delegates:
                record(f"audit {name}", "WARN", "delegates to Host-HAL and never launches the real tool (stub)")
            elif launches == 0:
                record(f"audit {name}", "WARN", "no subprocess calls found (cannot be driving an external tool)")
            else:
                record(f"audit {name}", "PASS", f"{launches} subprocess call(s); delegates_to_host={delegates}")
        lines.append(f"{name}: subprocess_calls={launches} delegates_to_host={delegates}")
    (OUT / "static_audit.txt").write_text("\n".join(lines))


def section_host():
    code = (
        "from fwagent.simulator.host_hal import HostHALSimulator as H\n"
        "s=H(); s.set_input('temp','raw:307'); s.run_for(1000)\n"
        "print('serial_tail', s.read_serial()[-1:]); print('pin9', s.read_pin('9'))\n"
        "print('executes_real_firmware', getattr(s,'executes_real_firmware','attribute missing'))\n")
    rc, out = sh("host_smoke", [sys.executable, "-c", code], timeout=60)
    ok = rc == 0 and "pin9 1" in out
    record("host backend", "PASS" if ok else "FAIL", "raw 307 turns fan ON" if ok else out.strip()[-160:])
    if "executes_real_firmware False" in out or "attribute missing" in out:
        record("host is real firmware?", "WARN", "no: Host-HAL is a Python behavioural model, not your compiled sketch")


def section_factory():
    code = ("from fwagent.simulator.factory import SimulatorFactory as F\n"
            "import json; print(json.dumps(F.get_available_backends(), indent=2, default=str))\n")
    rc, out = sh("factory_backends", [sys.executable, "-c", code])
    record("factory availability", "PASS" if rc == 0 else "FAIL",
           "listed backends" if rc == 0 else out.strip().splitlines()[-1][:160])


def section_gazebo(world):
    exe = shutil.which("gz")
    if not exe:
        return record("gazebo", "SKIP", "gz not installed (Linux/WSL2 only)")
    world = world or "shapes.sdf"
    rc, out = sh("gz_headless_iterations", [exe, "sim", "-s", "-r", "-v", "4", "--iterations", "200", world], timeout=90)
    record("gazebo headless run", "PASS" if rc == 0 else "FAIL", f"exit {rc}, world={world}")
    log = OUT / "gz_server_live.log"
    with open(log, "w") as fh:
        proc = subprocess.Popen([exe, "sim", "-s", "-r", "-v", "3", world], stdout=fh, stderr=subprocess.STDOUT,
                                preexec_fn=getattr(os, "setsid", None))
    try:
        found, deadline = False, time.time() + 25
        while time.time() < deadline and not found:
            if proc.poll() is not None:
                break
            rc, topics = sh("gz_topic_list", [exe, "topic", "-l"], timeout=10)
            found = rc == 0 and "/clock" in topics
            time.sleep(1)
        record("gazebo topics", "PASS" if found else "FAIL", "/clock visible" if found else "no /clock topic (see gz_server_live.log)")
        if found:
            rc, out = sh("gz_clock_sample", [exe, "topic", "-e", "-t", "/clock", "-n", "1"], timeout=15)
            record("gazebo clock message", "PASS" if rc == 0 and out.strip() else "FAIL", f"exit {rc}")
            sh("gz_service_list", [exe, "service", "-l"], timeout=15)
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM) if hasattr(os, "killpg") else proc.terminate()
        except Exception:
            proc.kill()


def section_renode(resc):
    exe = shutil.which("renode")
    if not exe:
        return record("renode", "SKIP", "renode not installed / not on PATH")
    rc, out = sh("renode_version", [exe, "--version"], timeout=30)
    record("renode version", "PASS" if rc == 0 else "FAIL", (out.strip().splitlines() or ["?"])[-1])
    rc, out = sh("renode_headless_smoke", [exe, "--disable-xwt", "--console", "-e", "version; quit"], timeout=60)
    record("renode headless start", "PASS" if rc == 0 else "FAIL", f"exit {rc}")
    if resc and Path(resc).exists():
        rc, out = sh("renode_resc_run", [exe, "--disable-xwt", "--console", "-e", f"include @{resc}; quit"], timeout=120)
        bad = rc != 0 or "error" in out.lower()
        record("renode script", "FAIL" if bad else "PASS", f"{resc} exit {rc}")
    else:
        record("renode script", "SKIP", "pass --renode-resc <file.resc> to test your platform script")


def section_wokwi(project):
    exe = shutil.which("wokwi-cli")
    if not exe:
        return record("wokwi", "SKIP", "wokwi-cli not on PATH")
    token = bool(os.environ.get("WOKWI_CLI_TOKEN"))
    record("wokwi token", "PASS" if token else "FAIL", "WOKWI_CLI_TOKEN set" if token else "WOKWI_CLI_TOKEN missing")
    sh("wokwi_version", [exe, "--version"], timeout=20)
    if project and (Path(project) / "wokwi.toml").exists():
        rc, out = sh("wokwi_run", [exe, "--timeout", "8000", str(project)], timeout=90)
        record("wokwi project run", "PASS" if rc in (0,) else "FAIL", f"{project} exit {rc}")
    else:
        record("wokwi project run", "SKIP", "pass --wokwi-project <dir with wokwi.toml>")


def section_e2e(firmware):
    if not shutil.which("fwagent"):
        return record("end-to-end", "SKIP", "fwagent command not on PATH (activate the venv)")
    for backend in ("host", "wokwi", "renode", "gazebo"):
        rc, out = sh(f"e2e_{backend}", ["fwagent", "run", firmware, "--sim", backend], timeout=420)
        tail = " | ".join(out.strip().splitlines()[-2:])[:150]
        record(f"fwagent --sim {backend}", "INFO", f"exit {rc}: {tail}")


def section_tests():
    rc, out = sh("pytest", [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short"], timeout=600)
    record("pytest", "PASS" if rc == 0 else "FAIL", (out.strip().splitlines() or ["no output"])[-1])


def collect_latest_run():
    runs = sorted((ROOT / "runs").glob("*/"), key=lambda p: p.stat().st_mtime) if (ROOT / "runs").exists() else []
    if not runs:
        return
    dest = OUT / "latest_run"
    dest.mkdir(exist_ok=True)
    for name in ("status.json", "stdout.log", "results.json", "findings.json", "coverage.json", "firmware_model.json"):
        src = runs[-1] / name
        if src.exists() and src.stat().st_size < 2_000_000:
            (dest / name).write_text(redact(src.read_text(errors="replace")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gz-world"); ap.add_argument("--renode-resc"); ap.add_argument("--wokwi-project")
    ap.add_argument("--firmware", default="firmware_samples/cooling_fan_buggy")
    ap.add_argument("--e2e", action="store_true"); ap.add_argument("--tests", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Writing logs to {OUT}\n")
    section_env(); section_repo(); section_static_audit(); section_host(); section_factory()
    section_gazebo(a.gz_world); section_renode(a.renode_resc); section_wokwi(a.wokwi_project or a.firmware)
    if a.tests: section_tests()
    if a.e2e: section_e2e(a.firmware)
    collect_latest_run()

    (OUT / "summary.json").write_text(json.dumps(RESULTS, indent=2))
    (OUT / "summary.txt").write_text("\n".join(f"[{r['status']}] {r['section']}: {r['detail']}" for r in RESULTS))
    zpath = OUT.parent / f"diagnostics_{STAMP}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in OUT.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(OUT.parent))
    print(f"\nBundle ready: {zpath}\nSend this zip (secrets are redacted) for review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
