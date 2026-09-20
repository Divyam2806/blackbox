from typing import List, Tuple, Dict, Union, Optional
from fwagent.simulator.base import Simulator


class HostHALSimulator(Simulator):
    """
    Host-HAL Software-In-the-Loop (SIL) Virtual Hardware Simulator.
    Model-driven: self-configures from a FirmwareModel extracted by StaticParser.
    Falls back to cooling-fan defaults when no model is provided.
    """

    def __init__(
        self,
        model=None,               # Optional[FirmwareModel]
        sample_interval_ms: int = 200,
        firmware_type: str = "buggy",
    ):
        self.model = model
        self.sample_interval_ms = sample_interval_ms
        self.firmware_type = firmware_type
        self.t_ms: int = 0

        # --- Derive ADC channels from model.inputs -------------------------
        if model and model.inputs:
            self.adc_channels: Dict[str, float] = {}
            for s in model.inputs:
                pin_key = str(s.pin) if s.pin is not None else s.name
                unit = (s.unit or "").lower()
                default_raw = 300.0 if ("cm" in unit or "dist" in unit) else 256.0
                self.adc_channels[pin_key] = default_raw
        else:
            self.adc_channels = {"A0": 256.0}   # cooling-fan fallback

        # --- Derive GPIO output registers from model.outputs ---------------
        if model and model.outputs:
            self.gpio_outputs: Dict[str, int] = {
                str(s.pin) if s.pin is not None else s.name: 0
                for s in model.outputs
            }
        else:
            self.gpio_outputs = {"9": 0, "13": 0}   # fan + err_led fallback

        # --- Name → pin look-up maps ---------------------------------------
        self._input_name_to_pin: Dict[str, str] = {}
        if model and model.inputs:
            for s in model.inputs:
                pin_key = str(s.pin) if s.pin is not None else s.name
                self._input_name_to_pin[s.name.lower()] = pin_key

        self._output_name_to_pin: Dict[str, str] = {}
        if model and model.outputs:
            for s in model.outputs:
                pin_key = str(s.pin) if s.pin is not None else s.name
                self._output_name_to_pin[s.name.lower()] = pin_key

        self.active_faults: Dict[str, str] = {}
        self.stuck_values: Dict[str, float] = {}
        self.serial_buffer: List[Tuple[int, str]] = []
        self.glitch_counter: Dict[str, int] = {}
        self.fan_on_state: bool = False  # legacy state used by oracle checks
        self.reset()

    # ------------------------------------------------------------------
    # Simulator interface
    # ------------------------------------------------------------------

    def set_firmware_type(self, fw_type: str) -> None:
        self.firmware_type = "good" if "good" in fw_type.lower() else "buggy"

    def reset(self) -> None:
        self.t_ms = 0
        if self.model and self.model.inputs:
            for s in self.model.inputs:
                pin_key = str(s.pin) if s.pin is not None else s.name
                unit = (s.unit or "").lower()
                self.adc_channels[pin_key] = 300.0 if ("cm" in unit or "dist" in unit) else 256.0
        else:
            self.adc_channels = {"A0": 256.0}
        for k in list(self.gpio_outputs):
            self.gpio_outputs[k] = 0
        self.active_faults.clear()
        self.stuck_values.clear()
        self.glitch_counter.clear()
        self.serial_buffer.clear()
        self.fan_on_state = False

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        sig_lower = str(signal).lower()
        try:
            val = float(value)
        except (ValueError, TypeError):
            return
        pin_key = self._resolve_input_pin(sig_lower)
        if pin_key:
            self.adc_channels[pin_key] = self._to_raw(pin_key, val, sig_lower)
        else:
            self.adc_channels[sig_lower] = val

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0) -> None:
        pin = self._resolve_input_pin(str(signal).lower()) or str(signal)
        self.active_faults[pin] = fault_type
        if fault_type == "stuck":
            self.stuck_values[pin] = self.adc_channels.get(pin, 256.0)
        elif fault_type == "glitch":
            self.glitch_counter[pin] = 1

    def clear_fault(self, signal: str) -> None:
        pin = self._resolve_input_pin(str(signal).lower()) or str(signal)
        self.active_faults.pop(pin, None)
        self.stuck_values.pop(pin, None)

    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        start_idx = len(self.serial_buffer)
        steps = max(1, duration_ms // self.sample_interval_ms)
        for _ in range(steps):
            self.t_ms += self.sample_interval_ms
            self._step_hardware()
        return self.serial_buffer[start_idx:]

    def read_pin(self, pin: str) -> int:
        pin_clean = str(pin).replace("D", "").replace("d", "")
        return self.gpio_outputs.get(pin_clean, self.gpio_outputs.get(pin_clean.lstrip("0"), 0))

    def read_serial(self) -> List[Tuple[int, str]]:
        return list(self.serial_buffer)

    # ------------------------------------------------------------------
    # Internal simulation step
    # ------------------------------------------------------------------

    def _step_hardware(self) -> None:
        uart_silenced = self.active_faults.get("uart") == "silence"

        if self.model and self.model.inputs:
            # ---- Generic model-driven path --------------------------------
            readings: Dict[str, float] = {
                pin_key: self._apply_fault(pin_key)
                for pin_key in self.adc_channels
            }

            # Check for rail / implausible values across all input channels
            error_detected = False
            for s in self.model.inputs:
                pin_key = str(s.pin) if s.pin is not None else s.name
                raw = readings.get(pin_key, 256.0)
                if s.valid_range:
                    lo_raw = self._to_raw(pin_key, s.valid_range[0], s.name.lower())
                    hi_raw = self._to_raw(pin_key, s.valid_range[1], s.name.lower())
                    if raw <= lo_raw + 4 or raw >= hi_raw - 4:
                        error_detected = True
                else:
                    # Fallback: ADC rail detection
                    if raw <= 4 or raw >= 1019:
                        error_detected = True

            # Evaluate thresholds and drive output pins
            output_states: Dict[str, int] = {}
            for th in (self.model.thresholds or []):
                pin_key = self._resolve_input_pin(th.signal.lower()) or th.signal
                raw = readings.get(pin_key, 256.0)
                eng_val = self._to_engineering(pin_key, raw)
                op, tval = th.op, th.value
                triggered = (
                    (op in (">=", "=>") and eng_val >= tval) or
                    (op in ("<=", "=<") and eng_val <= tval) or
                    (op == ">"  and eng_val > tval) or
                    (op == "<"  and eng_val < tval) or
                    (op == "==" and eng_val == tval)
                )
                for out in (self.model.outputs or []):
                    out_pin = str(out.pin) if out.pin is not None else out.name
                    name_lower = out.name.lower()
                    if "err" in name_lower or "led" in name_lower:
                        output_states[out_pin] = 1 if error_detected else 0
                    else:
                        if self.firmware_type == "good":
                            if error_detected:
                                output_states[out_pin] = 1   # fail-safe ON
                            else:
                                if triggered:
                                    self.fan_on_state = True
                                elif not triggered:
                                    self.fan_on_state = False
                                output_states[out_pin] = 1 if self.fan_on_state else 0
                        else:
                            output_states[out_pin] = 1 if triggered else 0

            self.gpio_outputs.update(output_states)

            # Emit serial log
            if not uart_silenced:
                if error_detected and self.firmware_type == "good":
                    self.serial_buffer.append((self.t_ms, "ERR: Sensor Fault"))
                else:
                    parts = []
                    for s in self.model.inputs:
                        pin_key = str(s.pin) if s.pin is not None else s.name
                        eng_val = self._to_engineering(pin_key, readings.get(pin_key, 256.0))
                        parts.append(f"{s.name.upper()}={eng_val:.2f}")
                    for s in self.model.outputs:
                        out_pin = str(s.pin) if s.pin is not None else s.name
                        state = self.gpio_outputs.get(out_pin, 0)
                        parts.append(f"{s.name.upper()}={'ON' if state else 'OFF'}")
                    if parts:
                        self.serial_buffer.append((self.t_ms, " ".join(parts)))

        else:
            # ---- Legacy hardcoded cooling-fan path (no model) -------------
            raw_adc = self._apply_fault("A0")
            if self.firmware_type == "good":
                is_error = raw_adc <= 4 or raw_adc >= 1019
                if is_error:
                    self.gpio_outputs["13"] = 1
                    self.gpio_outputs["9"] = 1
                    if not uart_silenced:
                        self.serial_buffer.append((self.t_ms, "ERR: Sensor Fault"))
                else:
                    self.gpio_outputs["13"] = 0
                    temp_c = raw_adc * (100.0 / 1023.0)
                    if temp_c >= 30.0:
                        self.fan_on_state = True
                    elif temp_c <= 28.0:
                        self.fan_on_state = False
                    self.gpio_outputs["9"] = 1 if self.fan_on_state else 0
                    if not uart_silenced:
                        self.serial_buffer.append((self.t_ms, f"T={temp_c:.2f} FAN={'ON' if self.fan_on_state else 'OFF'}"))
            else:
                temp_c = raw_adc * (100.0 / 1023.0)
                fan_on = temp_c >= 30.0
                self.gpio_outputs["9"] = 1 if fan_on else 0
                self.gpio_outputs["13"] = 0
                if not uart_silenced:
                    self.serial_buffer.append((self.t_ms, f"T={temp_c:.2f} FAN={'ON' if fan_on else 'OFF'}"))

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _apply_fault(self, pin_key: str) -> float:
        """Return effective raw ADC value after applying active fault injection."""
        fault = self.active_faults.get(pin_key)
        raw = self.adc_channels.get(pin_key, 256.0)
        if fault in ("open_circuit", "short_to_vcc"):
            return 1023.0
        if fault == "short_to_gnd":
            return 0.0
        if fault == "stuck":
            return self.stuck_values.get(pin_key, raw)
        if fault == "glitch" and self.glitch_counter.get(pin_key, 0) > 0:
            self.glitch_counter[pin_key] = 0
            return 1023.0
        return raw

    def _resolve_input_pin(self, sig_lower: str) -> Optional[str]:
        """Map a signal name token to its ADC channel pin key."""
        if sig_lower in self._input_name_to_pin:
            return self._input_name_to_pin[sig_lower]
        for name, pin in self._input_name_to_pin.items():
            if name in sig_lower or sig_lower in name:
                return pin
        if "temp" in sig_lower or sig_lower == "a0":
            return list(self.adc_channels.keys())[0] if self.adc_channels else "A0"
        return None

    def _to_raw(self, pin_key: str, eng_val: float, sig_lower: str = "") -> float:
        """Convert engineering-unit value to raw ADC count for a channel."""
        unit = self._get_unit(pin_key)
        if "cm" in unit or "dist" in unit:
            return max(0.0, min(1023.0, eng_val))   # distance already in cm
        if eng_val > 100.0:
            return max(0.0, min(1023.0, eng_val))   # already raw-ish
        return max(0.0, min(1023.0, eng_val * (1023.0 / 100.0)))

    def _to_engineering(self, pin_key: str, raw: float) -> float:
        """Convert raw ADC count to engineering units for a channel."""
        unit = self._get_unit(pin_key)
        if "cm" in unit or "dist" in unit:
            return raw   # stored as cm directly
        return raw * (100.0 / 1023.0)

    def _get_unit(self, pin_key: str) -> str:
        """Return unit string for an input channel's pin key."""
        if self.model and self.model.inputs:
            for s in self.model.inputs:
                rpin = str(s.pin) if s.pin is not None else s.name
                if rpin == pin_key:
                    return (s.unit or "").lower()
        return ""


