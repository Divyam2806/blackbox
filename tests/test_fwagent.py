import os
import unittest
from fwagent.models import FirmwareModel, TestCase, Step, Expect, RunConfig
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.executor import Executor
from fwagent.evaluator.oracle import OracleEvaluator
from fwagent.evaluator.invariants import InvariantChecker
from fwagent.orchestrator import Orchestrator


class TestFWAgent(unittest.TestCase):

    def test_host_hal_simulation(self):
        sim = HostHALSimulator(firmware_type="buggy")
        sim.set_input("temp", 25.0)  # Cold
        logs = sim.run_for(1000)
        self.assertTrue(len(logs) > 0)
        self.assertIn("FAN=OFF", logs[-1][1])

        sim.set_input("temp", 40.0)  # Hot
        logs_hot = sim.run_for(1000)
        self.assertIn("FAN=ON", logs_hot[-1][1])

    def test_host_hal_good_firmware_fault_injection(self):
        sim = HostHALSimulator(firmware_type="good")
        sim.inject_fault("temp", "open_circuit")  # raw 1023
        logs = sim.run_for(1000)
        self.assertTrue(any("ERR: Sensor Fault" in line for _, line in logs))
        self.assertEqual(sim.read_pin("13"), 1)  # ERR_LED HIGH

    def test_executor_and_oracle(self):
        sim = HostHALSimulator(firmware_type="buggy")
        executor = Executor(sim)
        oracle = OracleEvaluator()

        tc = TestCase(
            id="T01_test",
            title="Cold Operating Test",
            category="normal",
            rationale="Check fan OFF below 30C",
            steps=[Step(at_ms=0, action="set_input", target="temp", value=25.0), Step(at_ms=100, action="wait", value=1000)],
            expects=[Expect(kind="output_eq", target="fan", value="OFF", rule_id="R2")]
        )

        result = executor.run_test(tc)
        verdict = oracle.judge(tc, result)
        self.assertEqual(verdict.status, "PASS")

    def test_orchestrator_end_to_end(self):
        orchestrator = Orchestrator()
        out_dir = os.path.join("runs", "test_run_tmp")
        res = orchestrator.run(
            firmware_dir="firmware_samples/cooling_fan_buggy",
            spec_file="firmware_samples/cooling_fan_buggy/spec.md",
            out_dir=out_dir
        )

        self.assertIn("verdicts", res)
        self.assertIn("findings", res)
        self.assertTrue(os.path.exists(res["report_file"]))


if __name__ == "__main__":
    unittest.main()
