from typing import List, Dict, Any, Tuple
from fwagent.models import Verdict, TestCase, Step


class InvariantChecker:
    """
    Evaluates Universal Embedded Invariants (I1-I3) on test observations.
    I1: Safe state at boot (fan/motor OFF at boot).
    I2: Implausible sensor data rejection (raw 0 or 1023 must signal error).
    I3: No output chattering near threshold (no excessive toggles).
    """

    def check_boot_safety(self, pin_trace: List[Dict[str, Any]], serial_logs: List[Tuple[int, str]]) -> Tuple[bool, str]:
        """I1: Verify output pins are OFF at boot initialization (t <= 500ms)."""
        for entry in pin_trace:
            if entry.get("t_ms", 0) <= 500:
                if entry.get("fan_pin", 0) != 0:
                    return False, f"Fan pin D9 was HIGH ({entry.get('fan_pin')}) at boot (t={entry.get('t_ms')}ms)"
        for t_ms, line in serial_logs:
            if t_ms <= 500 and "FAN=ON" in line:
                return False, f"Serial logged FAN=ON at boot (t={t_ms}ms)"
        return True, "Fan OFF at boot (I1 satisfied)"

    def check_plausible_data(self, test_case: TestCase, pin_trace: List[Dict[str, Any]], serial_logs: List[Tuple[int, str]]) -> Tuple[bool, str]:
        """I2: Verify implausible sensor data (raw 0 or 1023) is not silently accepted as valid temp."""
        has_rail_fault = any(
            s.action == "inject_fault" and s.value in ["open_circuit", "short_to_gnd", "short_to_vcc"]
            for s in test_case.steps
        ) or "raw 0" in test_case.title or "raw 1023" in test_case.title

        if not has_rail_fault:
            return True, "No rail fault stimulus in test"

        # Check if error LED (pin D13) was driven HIGH or error logged in serial
        err_led_driven = any(entry.get("err_pin", 0) == 1 for entry in pin_trace)
        err_logged = any("ERR" in line.upper() or "FAULT" in line.upper() for _, line in serial_logs)

        if not err_led_driven and not err_logged:
            return False, "Implausible sensor value (raw 0 or 1023) accepted silently without driving ERR_LED (D13) or logging error"

        return True, "Error signaled on implausible sensor data"

    def check_chatter(self, serial_logs: List[Tuple[int, str]], max_toggles: int = 3) -> Tuple[bool, int, str]:
        """I3: Verify output does not chatter rapidly near threshold (e.g. > 3 toggles in test)."""
        fan_states: List[Tuple[int, str]] = []
        for t_ms, line in serial_logs:
            if "FAN=ON" in line:
                fan_states.append((t_ms, "ON"))
            elif "FAN=OFF" in line:
                fan_states.append((t_ms, "OFF"))

        toggles = 0
        for i in range(1, len(fan_states)):
            if fan_states[i][1] != fan_states[i - 1][1]:
                toggles += 1

        if toggles > max_toggles:
            return False, toggles, f"Fan chattered {toggles} times near threshold (max allowed: {max_toggles})"

        return True, toggles, f"Fan stable with {toggles} toggles"
