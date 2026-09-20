"""
Shared fault layer.

Design rules (these fix the earlier version):
  * Faults work on RAW ADC COUNTS and are applied at READ time, once, by the
    simulator that owns the layer. Adapters must not apply them a second time.
  * Unknown fault kinds raise ValueError instead of being silently ignored.
  * glitch is one-shot (N samples), stuck freezes the last value seen when the
    fault was injected, noise is seeded so runs are repeatable.
  * The open-circuit reading depends on the circuit, so it is configurable.
"""
import random
from typing import Any, Dict, Optional

ALIASES = {
    "open": "open_circuit",
    "short": "short_to_gnd",
    "stuck_high": "short_to_vcc",
    "stuck_low": "short_to_gnd",
    "disconnect": "stale",
}
ADC_KINDS = {"open_circuit", "short_to_gnd", "short_to_vcc", "stuck", "stale",
             "glitch", "noise", "drift"}
PROTOCOL_KINDS = {"silence", "garbage", "nack", "timeout", "bus_stuck_low"}
KNOWN_KINDS = ADC_KINDS | PROTOCOL_KINDS


class SharedFaultLayer:
    def __init__(self, full_scale: float = 1023.0,
                 open_circuit_value: Optional[float] = None, seed: int = 1234,
                 rail_low: float = 0.0, rail_high: Optional[float] = None):
        if rail_high is not None:
            full_scale = rail_high
        self.rail_low = float(rail_low)
        self.rail_high = float(full_scale)
        self.full_scale = float(full_scale)
        self.open_circuit_value = (self.full_scale if open_circuit_value is None
                                   else float(open_circuit_value))
        self._seed = seed
        self._rng = random.Random(seed)
        self.active: Dict[str, Dict[str, Any]] = {}
        self.last_good: Dict[str, float] = {}

    # -- registration -------------------------------------------------------
    def set_fault(self, signal: str, kind: str, **params: Any) -> None:
        k = ALIASES.get(str(kind).lower(), str(kind).lower())
        if k not in KNOWN_KINDS:
            raise ValueError(f"Unknown fault kind '{kind}'. Known: {sorted(KNOWN_KINDS)}")
        self.active[signal] = {"kind": k, "params": params,
                               "frozen": self.last_good.get(signal), "samples": 0}

    def clear_fault(self, signal: str) -> None:
        self.active.pop(signal, None)

    def clear_all(self) -> None:
        self.active.clear()

    def reset(self) -> None:
        self.active.clear()
        self.last_good.clear()
        self._rng = random.Random(self._seed)

    def is_active(self, signal: str, kind: Optional[str] = None) -> bool:
        f = self.active.get(signal)
        if f is None:
            return False
        if kind is None:
            return True
        return f["kind"] == ALIASES.get(kind.lower(), kind.lower())

    # -- application --------------------------------------------------------
    def _clamp(self, v: float) -> float:
        return max(0.0, min(self.full_scale, v))

    def apply(self, signal: str, raw: float) -> float:
        """Return the value the firmware should see. Call once per sample."""
        f = self.active.get(signal)
        if f is None:
            self.last_good[signal] = float(raw)
            return float(raw)

        kind, p = f["kind"], f["params"]
        f["samples"] += 1
        n = f["samples"]

        if kind == "open_circuit":
            return self._clamp(float(p.get("value", self.open_circuit_value)))
        if kind == "short_to_gnd":
            return 0.0
        if kind == "short_to_vcc":
            return self.full_scale
        if kind in ("stuck", "stale"):
            if f["frozen"] is None:
                f["frozen"] = float(raw)
            return f["frozen"]
        if kind == "glitch":
            if n <= int(p.get("samples", 1)):
                spike = self.full_scale if p.get("spike_high", True) else 0.0
                return self._clamp(float(p.get("value", spike)))
            self.last_good[signal] = float(raw)
            return float(raw)
        if kind == "noise":
            delta = float(p.get("delta", 2.0))
            return self._clamp(float(raw) + self._rng.uniform(-delta, delta))
        if kind == "drift":
            return self._clamp(float(raw) + float(p.get("per_sample", 0.5)) * n)
        return float(raw)  # protocol-level kinds do not change ADC values

    def transform(self, signal: str, raw_value: Any) -> Any:
        """Alias for apply() for backward compatibility."""
        try:
            val = float(raw_value)
            return self.apply(signal, val)
        except (ValueError, TypeError):
            return raw_value
