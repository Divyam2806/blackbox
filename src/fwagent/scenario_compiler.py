from typing import List, Dict, Any
from fwagent.models import TestCase, Step


class ScenarioCompiler:
    """
    Translates abstract TestCase steps into concrete execution sequences for the Simulator.
    """

    def compile(self, test_case: TestCase) -> List[Dict[str, Any]]:
        """
        Compile TestCase into a sequence of executable simulator instructions.
        """
        compiled_actions: List[Dict[str, Any]] = []

        # Always start with a hardware reset action
        compiled_actions.append({"op": "reset"})

        for step in test_case.steps:
            target_name = step.target or "sensor_input"
            if step.action == "set_input":
                compiled_actions.append({
                    "op": "set_input",
                    "target": target_name,
                    "value": step.value,
                    "at_ms": step.at_ms
                })
            elif step.action == "inject_fault":
                compiled_actions.append({
                    "op": "inject_fault",
                    "target": target_name,
                    "fault_type": str(step.value) if step.value else "open_circuit",
                    "at_ms": step.at_ms
                })
            elif step.action == "clear_fault":
                compiled_actions.append({
                    "op": "clear_fault",
                    "target": target_name,
                    "at_ms": step.at_ms
                })
            elif step.action == "wait":
                duration = int(step.value) if step.value is not None else 1000
                compiled_actions.append({
                    "op": "wait",
                    "duration_ms": max(100, duration),
                    "at_ms": step.at_ms
                })
            elif step.action == "reset":
                compiled_actions.append({"op": "reset"})

        # Default fallback wait if no explicit wait was given
        if not any(a["op"] == "wait" for a in compiled_actions):
            compiled_actions.append({"op": "wait", "duration_ms": 1000, "at_ms": 0})

        return compiled_actions

    def compile_to_wokwi_yaml(self, test_case: TestCase) -> str:
        """
        Compile TestCase steps into valid Wokwi Scenario YAML format.
        Maps set_input, inject_fault (open_circuit=100.0/raw 1023, short_to_gnd=0.0/raw 0, stuck=frozen), and wait delays.
        """
        import yaml
        steps_list = []
        last_val = 25.0

        for s in test_case.steps:
            target_name = s.target or "sensor_input"
            part_id = f"{target_name}1"
            if s.action == "set_input":
                try:
                    val = float(s.value) if s.value is not None else 25.0
                except (ValueError, TypeError):
                    val = 25.0
                # Raw ADC conversion if raw value specified
                if val > 100.0:
                    val = val * (100.0 / 1023.0)
                last_val = val
                steps_list.append({
                    "set-control": {
                        "part-id": part_id,
                        "control": target_name,
                        "value": round(val, 2)
                    }
                })
            elif s.action == "inject_fault":
                fault = str(s.value).lower() if s.value else "open_circuit"
                if "open" in fault or "vcc" in fault or "high" in fault:
                    fault_val = 100.0  # Rail High raw 1023
                elif "gnd" in fault or "short" in fault or "low" in fault:
                    fault_val = 0.0    # Rail Low raw 0
                else:
                    fault_val = last_val  # Stuck / frozen
                steps_list.append({
                    "set-control": {
                        "part-id": part_id,
                        "control": target_name,
                        "value": fault_val
                    }
                })
            elif s.action == "wait":
                dur_ms = int(s.value) if s.value is not None else 500
                steps_list.append({"delay": f"{max(100, dur_ms)}ms"})

        if not any("delay" in step for step in steps_list):
            steps_list.append({"delay": "500ms"})

        scenario_dict = {
            "name": test_case.id,
            "version": 1,
            "author": "FWAgent",
            "steps": steps_list
        }
        return yaml.dump(scenario_dict, sort_keys=False)

