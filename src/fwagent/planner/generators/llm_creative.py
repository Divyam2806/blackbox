from typing import List
from fwagent.models import FirmwareModel, TestCase, Step, Expect


class LLMCreativeGenerator:
    """
    LLM Creative Test Generator (Stage P).
    Generates domain-specific creative edge cases and validates them against allowed primitives.
    """

    ALLOWED_ACTIONS = {"set_input", "inject_fault", "clear_fault", "press_button", "uart_send", "reset", "wait"}

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        """
        Produce creative domain edge-case test cases.
        """
        creative_tests: List[TestCase] = []

        # Creative Scenario 1: Intermittent Sensor Reconnection during Ramp
        c01 = TestCase(
            id="C01_creative",
            title="LLM Creative: Intermittent sensor reconnection during ramp heating",
            category="combo",
            rationale="Simulates sensor being unplugged then reconnected while temperature is rising above 30°C.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=35.0),
                Step(at_ms=500, action="inject_fault", target="temp", value="open_circuit"),
                Step(at_ms=1500, action="clear_fault", target="temp"),
                Step(at_ms=2000, action="set_input", target="temp", value=25.0),
                Step(at_ms=3000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="output_eq", target="fan", value="OFF", rule_id="R2")
            ],
            priority=2,
            origin="llm"
        )

        # Creative Scenario 2: Rapid Boot Reset Stress Test
        c02 = TestCase(
            id="C02_creative",
            title="LLM Creative: Rapid MCU hard reset stress test during hot state",
            category="timing",
            rationale="Simulates rapid power brownouts while MCU is driving fan output.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=40.0),
                Step(at_ms=500, action="reset"),
                Step(at_ms=1000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="output_eq", target="fan", value="OFF", rule_id="I1")
            ],
            priority=2,
            origin="llm"
        )

        creative_tests.extend([c01, c02])
        return [tc for tc in creative_tests if self._validate_primitives(tc)]

    def _validate_primitives(self, test_case: TestCase) -> bool:
        """Verify all test steps use only allowed action primitives."""
        for step in test_case.steps:
            if step.action not in self.ALLOWED_ACTIONS:
                return False
        return True
