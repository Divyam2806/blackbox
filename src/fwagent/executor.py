from typing import List, Tuple, Dict, Any, Optional
from fwagent.models import TestCase
from fwagent.simulator.base import Simulator
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.scenario_compiler import ScenarioCompiler


class Executor:
    """
    Executes TestCases on a virtual hardware simulator.
    Model-driven: reads output pins generically from FirmwareModel.outputs when available.
    Falls back to cooling-fan pin layout (D9=fan, D13=err_led) when no model is provided.
    """

    def __init__(self, simulator: Simulator = None, model=None):
        self.sim = simulator or HostHALSimulator()
        self.model = model   # Optional[FirmwareModel]
        self.compiler = ScenarioCompiler()

    def run_test(self, test_case: TestCase, timeout_s: float = 10.0) -> Dict[str, Any]:
        """
        Execute a single TestCase against the simulator.
        Returns execution results including serial logs, pin observations, and timing trace.
        """
        self.sim.reset()
        actions = self.compiler.compile(test_case)

        execution_logs: List[Tuple[int, str]] = []
        pin_trace: List[Dict[str, Any]] = []

        for action in actions:
            op = action.get("op")
            if op == "reset":
                self.sim.reset()
            elif op == "set_input":
                target = action.get("target", "temp")
                val = action.get("value", 25.0)
                self.sim.set_input(target, val)
            elif op == "inject_fault":
                target = action.get("target", "temp")
                fault = action.get("fault_type", "open_circuit")
                self.sim.inject_fault(target, fault)
            elif op == "clear_fault":
                target = action.get("target", "temp")
                self.sim.clear_fault(target)
            elif op == "wait":
                duration = action.get("duration_ms", 1000)
                new_logs = self.sim.run_for(duration)
                execution_logs.extend(new_logs)

                # Record pin state snapshot after wait
                snapshot: Dict[str, Any] = {"t_ms": getattr(self.sim, "t_ms", 0)}

                if self.model and self.model.outputs:
                    # Generic: read every output signal defined in the model
                    for out_sig in self.model.outputs:
                        pin_str = str(out_sig.pin) if out_sig.pin is not None else out_sig.name
                        state = self.sim.read_pin(pin_str)
                        snapshot[out_sig.name] = state
                    # Legacy oracle compat: populate fan_pin / err_pin from first 2 outputs
                    out_names = [s.name.lower() for s in self.model.outputs]
                    fan_out = next(
                        (s for s in self.model.outputs if any(k in s.name.lower() for k in ("fan", "motor", "servo", "output"))),
                        self.model.outputs[0] if self.model.outputs else None,
                    )
                    err_out = next(
                        (s for s in self.model.outputs if any(k in s.name.lower() for k in ("err", "led", "alarm"))),
                        None,
                    )
                    if fan_out:
                        pin_str = str(fan_out.pin) if fan_out.pin is not None else fan_out.name
                        snapshot["fan_pin"] = self.sim.read_pin(pin_str)
                    if err_out:
                        pin_str = str(err_out.pin) if err_out.pin is not None else err_out.name
                        snapshot["err_pin"] = self.sim.read_pin(pin_str)
                else:
                    # Legacy cooling-fan fallback
                    snapshot["fan_pin"] = self.sim.read_pin("9")
                    snapshot["err_pin"] = self.sim.read_pin("13")

                pin_trace.append(snapshot)

        return {
            "test_id": test_case.id,
            "serial_logs": execution_logs,
            "pin_trace": pin_trace,
            "actions": actions,
        }

