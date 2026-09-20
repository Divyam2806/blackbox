from typing import List, Tuple, Dict, Union, Optional
from fwagent.simulator.base import Simulator


class HostHALSimulator(Simulator):
    """
    Host-HAL Software-In-the-Loop (SIL) Virtual Hardware Simulator.
    Simulates MCU virtual clock, pin registers, ADC channels, pin faults, and UART serial buffers.
    Supports both buggy and fixed firmware operational modes.
    """

    def __init__(self, sample_interval_ms: int = 200, firmware_type: str = "buggy"):
        self.sample_interval_ms = sample_interval_ms
        self.firmware_type = firmware_type
        self.t_ms: int = 0
        self.adc_inputs: Dict[str, float] = {"A0": 256.0}  # default ~25 C (raw 256)
        self.gpio_outputs: Dict[str, int] = {"9": 0, "13": 0}  # D9=Fan, D13=ERR_LED
        self.active_faults: Dict[str, str] = {}
        self.stuck_values: Dict[str, float] = {}
        self.serial_buffer: List[Tuple[int, str]] = []
        self.glitch_counter: Dict[str, int] = {}
        self.fan_on_state: bool = False
        self.reset()

    def set_firmware_type(self, fw_type: str) -> None:
        """Set firmware mode: 'buggy' or 'good'."""
        self.firmware_type = "good" if "good" in fw_type.lower() else "buggy"

    def reset(self) -> None:
        """Reset virtual hardware state to boot defaults."""
        self.t_ms = 0
        self.adc_inputs = {"A0": 256.0}
        self.gpio_outputs = {"9": 0, "13": 0}
        self.active_faults.clear()
        self.stuck_values.clear()
        self.glitch_counter.clear()
        self.serial_buffer.clear()
        self.fan_on_state = False

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        """Set input signal value (temperature in C or raw ADC count)."""
        sig_lower = str(signal).lower()
        if "temp" in sig_lower or "a0" in sig_lower:
            try:
                val = float(value)
                if val > 100.0 or "raw" in sig_lower:
                    raw_count = max(0.0, min(1023.0, val))
                else:
                    raw_count = max(0.0, min(1023.0, val * (1023.0 / 100.0)))
                self.adc_inputs["A0"] = raw_count
            except ValueError:
                pass

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0) -> None:
        """Inject hardware fault."""
        pin = "A0" if ("temp" in str(signal).lower() or "a0" in str(signal).lower()) else str(signal)
        self.active_faults[pin] = fault_type
        if fault_type == "stuck":
            self.stuck_values[pin] = self.adc_inputs.get(pin, 256.0)
        elif fault_type == "glitch":
            self.glitch_counter[pin] = 1

    def clear_fault(self, signal: str) -> None:
        """Clear active fault."""
        pin = "A0" if ("temp" in str(signal).lower() or "a0" in str(signal).lower()) else str(signal)
        if pin in self.active_faults:
            del self.active_faults[pin]
        if pin in self.stuck_values:
            del self.stuck_values[pin]

    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        """Advance virtual clock by duration_ms and execute sketch loops."""
        start_idx = len(self.serial_buffer)
        steps = max(1, duration_ms // self.sample_interval_ms)

        for _ in range(steps):
            self.t_ms += self.sample_interval_ms
            self._step_hardware()

        return self.serial_buffer[start_idx:]

    def _step_hardware(self) -> None:
        """Execute one hardware sample loop iteration."""
        raw_adc = self.adc_inputs.get("A0", 256.0)
        fault = self.active_faults.get("A0")

        if fault == "open_circuit" or fault == "short_to_vcc":
            raw_adc = 1023.0
        elif fault == "short_to_gnd":
            raw_adc = 0.0
        elif fault == "stuck":
            raw_adc = self.stuck_values.get("A0", 256.0)
        elif fault == "glitch":
            if self.glitch_counter.get("A0", 0) > 0:
                raw_adc = 1023.0
                self.glitch_counter["A0"] = 0

        if self.firmware_type == "good":
            # Fixed firmware logic (cooling_fan_good)
            is_error = raw_adc <= 4 or raw_adc >= 1019
            if is_error:
                self.gpio_outputs["13"] = 1  # ERR_LED HIGH
                self.gpio_outputs["9"] = 1   # Fail-safe FAN ON
                if self.active_faults.get("uart") != "silence":
                    self.serial_buffer.append((self.t_ms, "ERR: Sensor Fault"))
            else:
                self.gpio_outputs["13"] = 0  # ERR_LED LOW
                temp_c = raw_adc * (100.0 / 1023.0)

                # Hysteresis control loop: ON >= 30 C, OFF <= 28 C
                if temp_c >= 30.0:
                    self.fan_on_state = True
                elif temp_c <= 28.0:
                    self.fan_on_state = False

                self.gpio_outputs["9"] = 1 if self.fan_on_state else 0
                if self.active_faults.get("uart") != "silence":
                    log_line = f"T={temp_c:.2f} FAN={'ON' if self.fan_on_state else 'OFF'}"
                    self.serial_buffer.append((self.t_ms, log_line))
        else:
            # Buggy firmware logic (cooling_fan_buggy)
            temp_c = raw_adc * (100.0 / 1023.0)
            fan_on = temp_c >= 30.0
            self.gpio_outputs["9"] = 1 if fan_on else 0
            self.gpio_outputs["13"] = 0  # Buggy sketch never writes ERR_LED

            if self.active_faults.get("uart") != "silence":
                log_line = f"T={temp_c:.2f} FAN={'ON' if fan_on else 'OFF'}"
                self.serial_buffer.append((self.t_ms, log_line))

    def read_pin(self, pin: str) -> int:
        pin_clean = str(pin).replace("D", "").replace("d", "")
        return self.gpio_outputs.get(pin_clean, 0)

    def read_serial(self) -> List[Tuple[int, str]]:
        return list(self.serial_buffer)
