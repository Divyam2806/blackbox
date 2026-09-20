from typing import List, Dict, Any, Tuple, Optional
from fwagent.models import Verdict, TestCase, Step, FirmwareModel


class InvariantChecker:
    """
    Evaluates Universal Embedded Invariants (I1-I3) dynamically on test observations.
    I1: Safe state at boot (outputs OFF/safe at boot).
    I2: Implausible sensor data rejection (raw 0 or 1023 / disconnected sensor must signal error).
    I3: No output chattering near threshold (no excessive toggles).
    """

    def check_boot_safety(
        self,
        pin_trace: List[Dict[str, Any]],
        serial_logs: List[Tuple[int, str]],
        model: Optional[FirmwareModel] = None
    ) -> Tuple[bool, str]:
        """I1: Verify output pins/signals are OFF/safe at boot initialization (t <= 500ms)."""
        out_names = [s.name for s in model.outputs] if (model and model.outputs) else []
        out_label = out_names[0] if out_names else "output"

        # Check pin traces at boot
        for entry in pin_trace:
            if entry.get("t_ms", 0) <= 500:
                for k, v in entry.items():
                    if k != "t_ms" and v not in (0, "OFF", "LOW", False):
                        p_name = k.replace("_pin", "")
                        return False, f"Output pin {p_name} was HIGH/active ({v}) at boot (t={entry.get('t_ms')}ms)"

        # Check serial logs at boot for ON signals
        for t_ms, line in serial_logs:
            if t_ms <= 500:
                line_u = line.upper()
                for name in (out_names or ["output"]):
                    if f"{name.upper()}=ON" in line_u or f"{name.upper()}=HIGH" in line_u:
                        return False, f"Serial logged {name.upper()}=ON at boot (t={t_ms}ms)"

        return True, f"{out_label} OFF at boot (I1 satisfied)"

    def check_plausible_data(
        self,
        test_case: TestCase,
        pin_trace: List[Dict[str, Any]],
        serial_logs: List[Tuple[int, str]],
        model: Optional[FirmwareModel] = None
    ) -> Tuple[bool, str]:
        """I2: Verify implausible sensor data (rail fault / 0 / 1023) is not silently accepted."""
        has_rail_fault = any(
            s.action == "inject_fault" and s.value in ["open_circuit", "short_to_gnd", "short_to_vcc"]
            for s in test_case.steps
        ) or "raw 0" in test_case.title.lower() or "raw 1023" in test_case.title.lower() or "fault" in test_case.title.lower()

        if not has_rail_fault:
            return True, "No rail fault stimulus in test"

        # Check if error indicator or serial error was logged
        err_pin_driven = any(
            any(k.startswith("err") and v not in (0, "OFF", "LOW", False) for k, v in entry.items() if k != "t_ms")
            for entry in pin_trace
        )
        err_logged = any("ERR" in line.upper() or "FAULT" in line.upper() for _, line in serial_logs)

        if not err_pin_driven and not err_logged:
            in_name = model.inputs[0].name if (model and model.inputs) else "sensor"
            return False, f"Implausible sensor value for {in_name} accepted silently without driving error indicator or logging error"

        return True, "Error signaled on implausible sensor data"

    def check_chatter(
        self,
        serial_logs: List[Tuple[int, str]],
        max_toggles: int = 3,
        model: Optional[FirmwareModel] = None
    ) -> Tuple[bool, int, str]:
        """I3: Verify output does not chatter rapidly near threshold (e.g. > max_toggles in test)."""
        out_name = model.outputs[0].name if (model and model.outputs) else "output"
        out_u = out_name.upper()

        out_states: List[Tuple[int, str]] = []
        for t_ms, line in serial_logs:
            line_u = line.upper()
            if f"{out_u}=ON" in line_u or f"{out_u}=HIGH" in line_u:
                out_states.append((t_ms, "ON"))
            elif f"{out_u}=OFF" in line_u or f"{out_u}=LOW" in line_u:
                out_states.append((t_ms, "OFF"))

        toggles = 0
        for i in range(1, len(out_states)):
            if out_states[i][1] != out_states[i - 1][1]:
                toggles += 1

        if toggles > max_toggles:
            return False, toggles, f"{out_name} chattered {toggles} times near threshold (max allowed: {max_toggles})"

        return True, toggles, f"{out_name} stable with {toggles} toggles"
