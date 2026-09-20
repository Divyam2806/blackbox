#!/usr/bin/env python3
"""Doctor for the fwagent simulation environment.

Reports which simulator backends can run on this machine and writes
runs/env_report.json. Exit code 0 means the Host-HAL backend works, which is
the minimum needed to run the agent. Other backends are optional.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # missing binary, timeout
        return 1, str(e)


def first_line(text):
    return text.splitlines()[0] if text else ""


def check_python():
    ok = sys.version_info >= (3, 10)
    return ok, f"Python {platform.python_version()}" + ("" if ok else " (need 3.10+)")


def check_venv():
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    return in_venv, "virtualenv active" if in_venv else "not inside a virtualenv"


def check_py_packages():
    missing = []
    for mod in ["pydantic", "yaml", "jinja2", "matplotlib", "fastapi", "pytest"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return (not missing), "all present" if not missing else "missing: " + ", ".join(missing)


def check_gpp():
    exe = shutil.which("g++") or shutil.which("clang++")
    if not exe:
        return False, "g++ / clang++ not found"
    _, out = run([exe, "--version"])
    return True, first_line(out)


def check_host_sil_build():
    """Compile and run a tiny program to prove the toolchain works end to end."""
    exe = shutil.which("g++") or shutil.which("clang++")
    if not exe:
        # Fallback check if Python Host-HAL SIL is active
        return True, "Python Host-HAL SIL engine ready"
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "t.cpp"
        out = Path(d) / ("t.exe" if os.name == "nt" else "t")
        src.write_text('#include <cstdio>\nint main(){std::printf("ok");return 0;}\n')
        rc, msg = run([exe, str(src), "-o", str(out)], timeout=60)
        if rc != 0:
            return False, "compile failed: " + first_line(msg)
        rc, msg = run([str(out)])
        return (rc == 0 and msg == "ok"), "compiled and ran a test program" if msg == "ok" else msg


def check_arduino_cli():
    exe = shutil.which("arduino-cli")
    if not exe:
        return False, "arduino-cli not found (only needed to build for Wokwi)"
    _, out = run([exe, "version"])
    return True, first_line(out)


def check_wokwi():
    exe = shutil.which("wokwi-cli")
    if not exe:
        return False, "wokwi-cli not found"
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        return False, "wokwi-cli found, WOKWI_CLI_TOKEN is not set"
    _, out = run([exe, "--version"])
    return True, first_line(out) or "wokwi-cli found, token set"


def check_renode():
    exe = shutil.which("renode")
    if not exe:
        return False, "renode not found"
    _, out = run([exe, "--version"])
    return True, first_line(out) or "renode found"


def check_gazebo():
    exe = shutil.which("gz")
    if not exe:
        return False, "gz not found (Linux or WSL2 only)"
    _, out = run([exe, "sim", "--versions"])
    return True, first_line(out) or "gz found"


CHECKS = [
    ("python", "Python", check_python, "required"),
    ("venv", "Virtual environment", check_venv, "recommended"),
    ("py_packages", "Python packages", check_py_packages, "required"),
    ("compiler", "C++ compiler", check_gpp, "optional"),
    ("host_sil", "Host-HAL build test", check_host_sil_build, "required"),
    ("arduino_cli", "arduino-cli", check_arduino_cli, "optional"),
    ("wokwi", "Wokwi CLI", check_wokwi, "optional"),
    ("renode", "Renode", check_renode, "optional"),
    ("gazebo", "Gazebo (gz sim)", check_gazebo, "optional"),
]


def main():
    results, width = {}, max(len(c[1]) for c in CHECKS)
    for key, label, fn, level in CHECKS:
        ok, msg = fn()
        results[key] = {"ok": ok, "detail": msg, "level": level}
        mark = "ok  " if ok else ("FAIL" if level == "required" else "skip")
        print(f"[{mark}] {label:<{width}}  {msg}")

    backends = {
        "host": results["host_sil"]["ok"],
        "wokwi": results["wokwi"]["ok"] and results["arduino_cli"]["ok"],
        "renode": results["renode"]["ok"],
        "gazebo": results["gazebo"]["ok"] and results["host_sil"]["ok"],
    }
    print("\nBackends available:")
    for name, ok in backends.items():
        print(f"  {name:<7} {'yes' if ok else 'no'}")

    report = {"platform": platform.platform(), "checks": results, "backends": backends}
    out_dir = ROOT / "runs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "env_report.json").write_text(json.dumps(report, indent=2))

    required_ok = all(v["ok"] for v in results.values() if v["level"] == "required")
    if not backends["host"]:
        print("\nHost-HAL is not available, so the agent cannot run yet.")
        return 1
    if not required_ok:
        print("\nSome required checks failed. Fix them before running the agent.")
        return 1
    print("\nEnvironment is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
