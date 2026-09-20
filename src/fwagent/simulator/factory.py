"""
Simulator factory: backend selection, honest fallback, and cross-backend comparison.

Fixes over the earlier version:
  * adapters are imported lazily, so one broken adapter cannot break the others;
  * create() passes the FirmwareModel and options through to the backend;
  * an unknown backend name raises instead of silently becoming "host";
  * missing available() is handled instead of crashing;
  * compare_backend_results() no longer reports agreement between backends that
    share the same engine, and ignores non-verdicts (INCONCLUSIVE, SKIPPED).
"""
import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fwagent.simulator.base import Simulator

_REGISTRY: Dict[str, Tuple[str, str]] = {
    "host":   ("fwagent.simulator.host_hal", "HostHALSimulator"),
    "wokwi":  ("fwagent.simulator.wokwi_adapter", "WokwiAdapter"),
    "renode": ("fwagent.simulator.renode_adapter", "RenodeSimulator"),
    "gazebo": ("fwagent.simulator.gazebo_adapter", "GazeboSimulator"),
}
COMPARABLE = {"PASS", "FAIL", "WARN", "AMBIGUOUS"}


def _load(name: str):
    module, cls = _REGISTRY[name]
    return getattr(importlib.import_module(module), cls)


def _available(name: str) -> Tuple[bool, str]:
    try:
        cls = _load(name)
    except Exception as e:                       # import error, missing module
        return False, f"cannot import adapter: {e}"
    fn = getattr(cls, "available", None)
    if fn is None:
        return False, "adapter has no available() method"
    try:
        return fn()
    except Exception as e:
        return False, f"available() raised: {e}"


class SimulatorFactory:
    @classmethod
    def get_available_backends(cls) -> Dict[str, Tuple[bool, str]]:
        return {name: _available(name) for name in _REGISTRY}

    @classmethod
    def auto_select(cls, firmware_dir: str) -> str:
        fw = Path(firmware_dir)
        worlds = list(fw.glob("world.sdf")) + list((fw / "worlds").glob("*.sdf"))
        if worlds and _available("gazebo")[0]:
            return "gazebo"
        if ((fw / "diagram.json").exists() or (fw / "wokwi.toml").exists()) and _available("wokwi")[0]:
            return "wokwi"
        if list(fw.glob("*.resc")) + list((fw / "boards").glob("**/*.resc")):
            if _available("renode")[0]:
                return "renode"
        return "host"

    @classmethod
    def create(cls, name: str, firmware_dir: str = ".", model: Any = None,
               **options: Any) -> Tuple[Simulator, Optional[str]]:
        """Return (simulator, notice). `notice` is set whenever we did not run
        what was asked for; print it in the terminal and put it in the report."""
        target = name.lower()
        if target == "auto":
            target = cls.auto_select(firmware_dir)
        if target not in _REGISTRY:
            raise ValueError(f"Unknown simulator '{name}'. Choose from: auto, {', '.join(_REGISTRY)}")

        ok, reason = _available(target)
        if not ok and target != "host":
            notice = f"Backend '{target}' unavailable ({reason}). Falling back to 'host' (behavioural model)."
            host = _load("host")(model=model)
            host.backend_name = "host (fallback)"
            return host, notice

        sim = _load(target)(model=model, **options) if target != "wokwi" else _load(target)(**options)
        if not getattr(sim, "backend_name", None):
            sim.backend_name = target
        return sim, None

    @staticmethod
    def label(sim: Simulator) -> str:
        real = "runs compiled firmware" if getattr(sim, "executes_real_firmware", False) \
            else "behavioural model, does not run compiled firmware"
        return f"{getattr(sim, 'backend_name', 'unknown')} ({real})"


def compare_backend_results(results_by_backend: Dict[str, List[Any]],
                            independent: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    names = list(results_by_backend)
    if not names:
        return {}
    independent = independent or {}
    ids = [r.test_id for r in results_by_backend[names[0]]]
    matrix, agreed, comparable = [], 0, 0
    for tid in ids:
        row: Dict[str, Any] = {"test_id": tid}
        verdicts = []
        for n in names:
            r = next((x for x in results_by_backend[n] if x.test_id == tid), None)
            v = getattr(r, "status", None) or "N/A"
            row[n] = v
            verdicts.append(v)
        usable = [v for v in verdicts if v in COMPARABLE]
        if len(usable) == len(verdicts) and len(usable) > 1:
            comparable += 1
            row["agreed"] = len(set(usable)) == 1
            agreed += row["agreed"]
        else:
            row["agreed"] = None           # not comparable (missing/INCONCLUSIVE/SKIPPED)
        matrix.append(row)
    n_indep = sum(1 for n in names if independent.get(n, True))
    out = {"backends": names, "total_tests": len(ids), "comparable_tests": comparable,
           "agreed_tests": agreed,
           "agreement_rate": round(agreed / comparable * 100.0, 1) if comparable else None,
           "matrix": matrix}
    if n_indep < 2:
        out["warning"] = ("Fewer than two independent engines ran, so agreement does not "
                          "raise confidence in the findings.")
    return out
