"""
Main Test Planner Orchestrator.
Combines boundary, equivalence, fault, dynamics, state, and LLM creative generators into a deduplicated, prioritized test plan.
"""

from typing import List
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
