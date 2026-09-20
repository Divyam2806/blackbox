"""
Host-HAL simulator (behavioural model).

IMPORTANT: this class does NOT compile or run the firmware. It re-implements
sensor -> threshold -> output behaviour in Python from the FirmwareModel, and
`firmware_type` ("good" / "buggy") selects which behaviour is modelled. Findings
from it therefore describe the MODEL, not your source code. Reports must say so
(see `executes_real_firmware`). To test real firmware, compile the sketch with
the C++ shim (hal_shim/) and drive it through a subprocess-based simulator.

Fixes over the earlier version:
  * available()/capabilities/start() exist, so the factory can use it.
  * faults come from the shared layer (one implementation, applied once).
  * inject_fault accepts **kwargs; "uart" no longer maps to the first ADC pin.
  * time no longer drops the remainder when duration < sample interval.
  * the buggy model never drives the error output (matches finding F2).
  * "err"/"fault"/"alarm" name the error output, not any "led".
  * hysteresis applies in the model path too, not only in the legacy path.
  * numeric inputs are ambiguous (degrees or counts?). Use "raw:307" or
    "eng:125" to be explicit; plain numbers keep the old auto rule.
"""
from typing import Any, Dict, List, Optional, Tuple, Union

from fwagent.simulator.base import Simulator
from fwagent.simulator.fault_layer import SharedFaultLayer

_ERR_WORDS = ("err", "fault", "alarm")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a pydantic object or a plain dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class HostHALSimulator(Simulator):
    executes_real_firmware = False
    independent = True
    capabilities = {"virtual_time", "fast", "any_board", "behavioural_model"}
    backend_name = "host"

    def __init__(self, model=None, sample_interval_ms: int = 200,
                 firmware_type: str = "buggy", adc_full_scale: float = 1023.0,
                 default_hysteresis: float = 2.0):
        self.model = model
        self.sample_interval_ms = max(1, int(sample_interval_ms))
        self.firmware_type = "good" if "good" in str(firmware_type).lower() else "buggy"
        self.full_scale = float(adc_full_scale)
        self.default_hysteresis = float(default_hysteresis)
        self.faults = SharedFaultLayer(full_scale=self.full_scale)

        self.t_ms = 0
        self._carry_ms = 0
        self.adc_channels: Dict[str, float] = {}
        self.gpio_outputs: Dict[str, int] = {}
        self._input_name_to_pin: Dict[str, str] = {}
        self._output_name_to_pin: Dict[str, str] = {}
        self.serial_buffer: List[Tuple[int, str]] = []
        self.fan_on_state = False
        self._configure_from_model()
        self.reset()

    # ---- interface -------------------------------------------------------
    @classmethod
    def available(cls) -> Tuple[bool, str]:
        return True, "built-in behavioural model (does not execute compiled firmware)"

    def start(self, artifact_path: Optional[str] = None) -> None:
        return None

    def stop(self) -> None:
        return None

    def set_firmware_type(self, fw_type: str) -> None:
        self.firmware_type = "good" if "good" in str(fw_type).lower() else "buggy"

    def set_model(self, model) -> None:
        """Update simulator model and re-configure input/output pin maps."""
        self.model = model
        self._configure_from_model()
        self.reset()

    def reset(self) -> None:
        self.t_ms = 0
        self._carry_ms = 0
        for pin in self._inputs_pin_keys():
            self.adc_channels[pin] = self._default_raw(pin)
        for k in list(self.gpio_outputs):
            self.gpio_outputs[k] = 0
        self.faults.reset()
        self.serial_buffer.clear()
        self.fan_on_state = False

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        mode, val = self._parse_value(value)
        if val is None:
            return
        pin = self._resolve_input_pin(str(signal).lower())
        self.adc_channels[pin] = self._to_raw(pin, val, mode)

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0, **kwargs) -> None:
        target = self._fault_target(signal)
        self.faults.set_fault(target, fault_type, **kwargs)

    def clear_fault(self, signal: str) -> None:
        self.faults.clear_fault(self._fault_target(signal))

    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        start_idx = len(self.serial_buffer)
        total = self._carry_ms + max(0, int(duration_ms))
        steps, self._carry_ms = divmod(total, self.sample_interval_ms)
        for _ in range(steps):
            self.t_ms += self.sample_interval_ms
            self._step_hardware()
        return self.serial_buffer[start_idx:]

    def read_pin(self, pin: str) -> int:
        p = str(pin).replace("D", "").replace("d", "")
        return self.gpio_outputs.get(p, self.gpio_outputs.get(p.lstrip("0"), 0))

    def read_serial(self) -> List[Tuple[int, str]]:
        return list(self.serial_buffer)

    # ---- configuration ---------------------------------------------------
    def _model_inputs(self) -> list:
        return list(_get(self.model, "inputs", None) or [])

    def _model_outputs(self) -> list:
        return list(_get(self.model, "outputs", None) or [])

    @staticmethod
    def _pin_key(sig) -> str:
        pin = _get(sig, "pin")
        return str(pin) if pin is not None else str(_get(sig, "name", ""))

    def _inputs_pin_keys(self) -> List[str]:
        keys = [self._pin_key(s) for s in self._model_inputs()]
        return keys or ["A0"]

    def _configure_from_model(self) -> None:
        self._input_name_to_pin.clear()
        self._output_name_to_pin.clear()
        for s in self._model_inputs():
            self._input_name_to_pin[str(_get(s, "name", "")).lower()] = self._pin_key(s)
        outs = self._model_outputs()
        if outs:
            for s in outs:
                self.gpio_outputs[self._pin_key(s)] = 0
                self._output_name_to_pin[str(_get(s, "name", "")).lower()] = self._pin_key(s)
        else:
            self.gpio_outputs = {"9": 0, "13": 0}
        for pin in self._inputs_pin_keys():
            self.adc_channels[pin] = self._default_raw(pin)

    def _default_raw(self, pin: str) -> float:
        unit = self._get_unit(pin)
        return 300.0 if ("cm" in unit or "dist" in unit) else 256.0

    # ---- pin resolution --------------------------------------------------
    def _resolve_input_pin(self, sig_lower: str) -> str:
        if sig_lower in self._input_name_to_pin:
            return self._input_name_to_pin[sig_lower]
        for pin in self.adc_channels:
            if pin.lower() == sig_lower:
                return pin
        for name, pin in self._input_name_to_pin.items():
            if name and (name in sig_lower or sig_lower in name):
                return pin
        return next(iter(self.adc_channels), "A0")

    def _fault_target(self, signal: str) -> str:
        s = str(signal).lower()
        if s in ("uart", "serial"):
            return "uart"
        if s in self._input_name_to_pin:
            return self._input_name_to_pin[s]
        for pin in self.adc_channels:
            if pin.lower() == s:
                return pin
        for name, pin in self._input_name_to_pin.items():
            if name and (name in s or s in name):
                return pin
        if self.adc_channels:
            return next(iter(self.adc_channels))
        return "A0"

    # ---- unit handling ---------------------------------------------------
    @staticmethod
    def _parse_value(value) -> Tuple[str, Optional[float]]:
        if isinstance(value, str):
            v = value.strip().lower()
            for prefix, mode in (("raw:", "raw"), ("eng:", "eng")):
                if v.startswith(prefix):
                    v, m = v[len(prefix):], mode
                    break
            else:
                m = "auto"
            try:
                return m, float(v)
            except ValueError:
                return "auto", None
        try:
            return "auto", float(value)
        except (TypeError, ValueError):
            return "auto", None

    def _clamp(self, v: float) -> float:
        return max(0.0, min(self.full_scale, v))

    def _range(self, pin: str) -> Tuple[float, float]:
        vr = self._get_valid_range(pin)
        if vr and vr[1] > vr[0]:
            return float(vr[0]), float(vr[1])
        return 0.0, 100.0

    def _is_raw_unit(self, pin: str) -> bool:
        unit = self._get_unit(pin)
        return "cm" in unit or "dist" in unit or "raw" in unit

    def _to_raw(self, pin: str, val: float, mode: str = "auto") -> float:
        if mode == "raw" or self._is_raw_unit(pin):
            return self._clamp(val)
        lo, hi = self._range(pin)
        if mode == "auto" and val > hi:      # legacy rule: big numbers are counts
            return self._clamp(val)
        return self._clamp((val - lo) * self.full_scale / (hi - lo))

    def _to_engineering(self, pin: str, raw: float) -> float:
        if self._is_raw_unit(pin):
            return raw
        lo, hi = self._range(pin)
        return lo + raw * (hi - lo) / self.full_scale

    def _get_unit(self, pin: str) -> str:
        for s in self._model_inputs():
            if self._pin_key(s) == pin or str(_get(s, "name", "")).lower() == pin.lower():
                return str(_get(s, "unit", "") or "").lower()
        return ""

    def _get_valid_range(self, pin: str):
        for s in self._model_inputs():
            if self._pin_key(s) == pin or str(_get(s, "name", "")).lower() == pin.lower():
                return _get(s, "valid_range")
        return None

    # ---- simulation step -------------------------------------------------
    def _step_hardware(self) -> None:
        silenced = self.faults.is_active("uart", "silence")
        if self._model_inputs():
            self._step_model(silenced)
        else:
            self._step_legacy(silenced)

    def _emit(self, silenced: bool, text: str) -> None:
        if not silenced:
            self.serial_buffer.append((self.t_ms, text))

    def _sensor_error(self, readings: Dict[str, float]) -> bool:
        for s in self._model_inputs():
            pin = self._pin_key(s)
            raw = readings.get(pin, 256.0)
            vr = _get(s, "valid_range")
            if vr and not self._is_raw_unit(pin):
                lo_raw = self._to_raw(pin, vr[0], "eng")
                hi_raw = self._to_raw(pin, vr[1], "eng")
                if raw <= lo_raw + 4 or raw >= hi_raw - 4:
                    return True
            elif raw <= 4 or raw >= self.full_scale - 4:
                return True
        return False

    @staticmethod
    def _compare(eng: float, op: str, t: float) -> bool:
        return ((op in (">=", "=>") and eng >= t) or (op in ("<=", "=<") and eng <= t)
                or (op == ">" and eng > t) or (op == "<" and eng < t) or (op == "==" and eng == t))

    def _step_model(self, silenced: bool) -> None:
        readings = {p: self.faults.apply(p, raw) for p, raw in self.adc_channels.items()}
        error = self._sensor_error(readings)
        good = self.firmware_type == "good"

        actuators, err_pins = [], []
        for s in self._model_outputs():
            name = str(_get(s, "name", "")).lower()
            (err_pins if any(w in name for w in _ERR_WORDS) else actuators).append(self._pin_key(s))

        ths = list(_get(self.model, "thresholds", None) or [])
        th = ths[0] if ths else None
        if th is not None and actuators:
            pin = self._resolve_input_pin(str(_get(th, "signal", "")).lower())
            eng = self._to_engineering(pin, readings.get(pin, 256.0))
            op = str(_get(th, "op", ">="))
            tval = float(_get(th, "value", 0.0))
            triggered = self._compare(eng, op, tval)
            if good and error:
                self.fan_on_state = True                     # fail-safe ON
            elif good:
                h = _get(th, "hysteresis")
                hyst = self.default_hysteresis if h is None else float(h)
                margin = eng - tval if op in (">", ">=", "=>") else tval - eng
                if triggered:
                    self.fan_on_state = True
                elif margin <= -hyst:
                    self.fan_on_state = False
            else:
                self.fan_on_state = triggered
            for p in actuators:
                self.gpio_outputs[p] = 1 if self.fan_on_state else 0
        for p in err_pins:                                    # buggy model never drives it
            self.gpio_outputs[p] = 1 if (good and error) else 0

        if good and error:
            self._emit(silenced, "ERR: Sensor Fault")
            return
        parts = []
        for s in self._model_inputs():
            pin = self._pin_key(s)
            parts.append(f"{str(_get(s, 'name', pin)).upper()}="
                         f"{self._to_engineering(pin, readings.get(pin, 256.0)):.2f}")
        for s in self._model_outputs():
            parts.append(f"{str(_get(s, 'name', '')).upper()}="
                         f"{'ON' if self.gpio_outputs.get(self._pin_key(s), 0) else 'OFF'}")
        if parts:
            self._emit(silenced, " ".join(parts))

    def _step_legacy(self, silenced: bool) -> None:
        raw = self.faults.apply("A0", self.adc_channels.get("A0", 256.0))
        temp = raw * (100.0 / self.full_scale)
        if self.firmware_type == "good":
            if raw <= 4 or raw >= self.full_scale - 4:
                self.gpio_outputs["13"] = 1
                self.gpio_outputs["9"] = 1
                self._emit(silenced, "ERR: Sensor Fault")
                return
            self.gpio_outputs["13"] = 0
            if temp >= 30.0:
                self.fan_on_state = True
            elif temp <= 28.0:
                self.fan_on_state = False
            self.gpio_outputs["9"] = 1 if self.fan_on_state else 0
            self._emit(silenced, f"T={temp:.2f} FAN={'ON' if self.fan_on_state else 'OFF'}")
        else:
            fan = temp >= 30.0
            self.gpio_outputs["9"] = 1 if fan else 0
            self.gpio_outputs["13"] = 0
            self._emit(silenced, f"T={temp:.2f} FAN={'ON' if fan else 'OFF'}")
