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
            if step.action == "set_input":
                compiled_actions.append({
                    "op": "set_input",
                    "target": step.target or "temp",
                    "value": step.value,
                    "at_ms": step.at_ms
                })
            elif step.action == "inject_fault":
                compiled_actions.append({
                    "op": "inject_fault",
                    "target": step.target or "temp",
                    "fault_type": str(step.value) if step.value else "open_circuit",
                    "at_ms": step.at_ms
                })
            elif step.action == "clear_fault":
                compiled_actions.append({
                    "op": "clear_fault",
                    "target": step.target or "temp",
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
