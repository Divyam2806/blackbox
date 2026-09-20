"""
Main Test Planner Orchestrator.
Combines boundary, equivalence, fault, dynamics, state, and LLM creative generators into a deduplicated, prioritized test plan.
"""

from typing import List, Any
from fwagent.models import FirmwareModel, TestCase
from fwagent.planner.generators.boundary import BoundaryGenerator
from fwagent.planner.generators.equivalence import EquivalenceGenerator
from fwagent.planner.generators.faults import FaultGenerator
from fwagent.planner.generators.dynamics import DynamicsGenerator
from fwagent.planner.generators.state_machine import StateMachineGenerator
from fwagent.planner.generators.llm_creative import LLMCreativeGenerator
from fwagent.planner.dedupe import Deduplicator
from fwagent.planner.prioritise import Prioritiser


class Planner:
    def __init__(self):
        self.boundary_gen = BoundaryGenerator()
        self.equivalence_gen = EquivalenceGenerator()
        self.fault_gen = FaultGenerator()
        self.dynamics_gen = DynamicsGenerator()
        self.state_gen = StateMachineGenerator()
        self.llm_creative_gen = LLMCreativeGenerator()
        self.deduper = Deduplicator()
        self.prioritiser = Prioritiser()

    def make_plan(self, model: FirmwareModel) -> List[TestCase]:
        all_cases: List[TestCase] = []

        # Run all generators
        all_cases.extend(self.equivalence_gen.generate(model))
        all_cases.extend(self.boundary_gen.generate(model))
        all_cases.extend(self.fault_gen.generate(model))
        all_cases.extend(self.dynamics_gen.generate(model))
        all_cases.extend(self.state_gen.generate(model))
        all_cases.extend(self.llm_creative_gen.generate(model))

        # Deduplicate
        unique_cases = self.deduper.deduplicate(all_cases)

        # Prioritise and re-index IDs
        final_plan = self.prioritiser.prioritise(unique_cases)

        return final_plan

    def adapt(self, model: FirmwareModel, results: List[Any]) -> List[TestCase]:
        """
        Adaptive Closed-Loop Test Generator.
        Contract: planner.adapt(model, results) -> list[TestCase], with origin="adaptive".
        Analyzes test verdicts to dynamically synthesize targeted probe test cases.
        """
        from fwagent.models import Step, Expect, Verdict
        adaptive_cases: List[TestCase] = []
        
        # Convert results if dicts passed
        verdict_list: List[Verdict] = []
        for r in results:
            if isinstance(r, Verdict):
                verdict_list.append(r)
            elif isinstance(r, dict):
                verdict_list.append(Verdict(**r))

        failed_verdicts = [v for v in verdict_list if v.status in ("FAIL", "WARN", "AMBIGUOUS")]
        if not failed_verdicts:
            return adaptive_cases

        for idx, v in enumerate(failed_verdicts, start=1):
            if "sensor" in v.expected.lower() or "fault" in v.expected.lower() or "R3" in v.rule_ids or "I2" in v.rule_ids:
                # Synthesize adaptive rail fault probe
                adaptive_cases.append(TestCase(
                    id=f"A{idx:02d}",
                    title=f"Adaptive Rail Fault Probe for {v.test_id}",
                    category="adaptive",
                    rationale=f"Targeted adaptive probe following failure in {v.test_id}: {v.observed}",
                    steps=[
                        Step(at_ms=0, action="set_input", target="temp", value=-10.0),
                        Step(at_ms=100, action="wait", target=None, value=50),
                    ],
                    expects=[
                        Expect(kind="output_eq", target="err_led", value="HIGH", rule_id="R3"),
                        Expect(kind="serial_contains", value="ERR: Sensor Fault", rule_id="I2")
                    ],
                    priority=1,
                    origin="adaptive"
                ))
            elif "chatter" in v.observed.lower() or "WARN" in v.status:
                # Synthesize adaptive hysteresis noise probe
                adaptive_cases.append(TestCase(
                    id=f"A{idx:02d}",
                    title=f"Adaptive Hysteresis Noise Probe for {v.test_id}",
                    category="adaptive",
                    rationale=f"Targeted adaptive probe following chatter warning in {v.test_id}",
                    steps=[
                        Step(at_ms=0, action="set_input", target="temp", value=29.8),
                        Step(at_ms=50, action="set_input", target="temp", value=30.2),
                        Step(at_ms=100, action="set_input", target="temp", value=29.9),
                        Step(at_ms=150, action="set_input", target="temp", value=30.1),
                    ],
                    expects=[
                        Expect(kind="transition_count", target="fan", value=2, window_ms=(0, 200), rule_id="I3")
                    ],
                    priority=1,
                    origin="adaptive"
                ))
            elif "AMBIGUOUS" in v.status or "30.0" in v.observed:
                # Synthesize adaptive boundary probe
                adaptive_cases.append(TestCase(
                    id=f"A{idx:02d}",
                    title=f"Adaptive Exact Boundary Probe at 30.0C for {v.test_id}",
                    category="adaptive",
                    rationale=f"Targeted adaptive probe following boundary ambiguity in {v.test_id}",
                    steps=[
                        Step(at_ms=0, action="set_input", target="temp", value=30.0),
                        Step(at_ms=50, action="wait", value=50)
                    ],
                    expects=[
                        Expect(kind="output_eq", target="fan", value="OFF", rule_id="R2")
                    ],
                    priority=1,
                    origin="adaptive"
                ))
            else:
                # General adaptive re-probe
                adaptive_cases.append(TestCase(
                    id=f"A{idx:02d}",
                    title=f"Adaptive Follow-up Probe for {v.test_id}",
                    category="adaptive",
                    rationale=f"Targeted adaptive probe for non-PASS verdict in {v.test_id}",
                    steps=[
                        Step(at_ms=0, action="set_input", target="temp", value=35.0),
                        Step(at_ms=100, action="wait", value=50)
                    ],
                    expects=[
                        Expect(kind="output_eq", target="fan", value="ON", rule_id="R1")
                    ],
                    priority=1,
                    origin="adaptive"
                ))

        return adaptive_cases

