from typing import List, Tuple, Dict, Any
from fwagent.models import TestCase
from fwagent.simulator.base import Simulator
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.scenario_compiler import ScenarioCompiler


class Executor:
    """
    Executes TestCases on a virtual hardware simulator, managing timeouts, resets, and log capture.
    """

    def __init__(self, simulator: Simulator = None):
        self.sim = simulator or HostHALSimulator()
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

                # Record pin state observation after wait
                fan_pin_state = self.sim.read_pin("9")
                err_pin_state = self.sim.read_pin("13")
                pin_trace.append({
                    "t_ms": getattr(self.sim, "t_ms", 0),
                    "fan_pin": fan_pin_state,
                    "err_pin": err_pin_state
                })

        return {
            "test_id": test_case.id,
            "serial_logs": execution_logs,
            "pin_trace": pin_trace,
            "actions": actions
        }
