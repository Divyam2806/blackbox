"""
LLM Creative Test Generator (Stage P).
Queries Gemini API to generate domain-specific creative edge cases and validates them against allowed primitives.
"""
import json
from typing import List, Type
from pydantic import BaseModel, Field
from fwagent.models import FirmwareModel, TestCase, Step, Expect
from fwagent.llm.gateway import LLMGateway


class CreativeTestsResponse(BaseModel):
    tests: List[TestCase] = Field(default_factory=list)


class LLMCreativeGenerator:
    """
    LLM Creative Test Generator (Stage P).
    Generates domain-specific creative edge cases and validates them against allowed primitives.
    """

    ALLOWED_ACTIONS = {"set_input", "inject_fault", "clear_fault", "press_button", "uart_send", "reset", "wait"}
    ALLOWED_EXPECT_KINDS = {"output_eq", "serial_contains", "serial_absent", "transition_count", "within_ms", "no_change", "physical_eq", "within_tolerance"}

    def __init__(self):
        self.gateway = LLMGateway(provider="gemini")

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        """
        Produce creative domain edge-case test cases using Gemini API.
        """
        prompt = (
            "You are a senior embedded firmware test verification engineer.\n"
            "Given the FirmwareModel JSON, generate 2 to 4 creative, domain-specific edge case test cases.\n"
            "Focus on physical plant scenarios, race conditions, fault injection sequences, boundary transitions, and power resets.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. Each step action MUST be strictly one of: 'set_input', 'inject_fault', 'clear_fault', 'press_button', 'uart_send', 'reset', 'wait'.\n"
            "2. Each expect kind MUST be strictly one of: 'output_eq', 'serial_contains', 'serial_absent', 'transition_count', 'within_ms', 'no_change', 'physical_eq', 'within_tolerance'.\n"
            "3. Output MUST be valid JSON matching the CreativeTestsResponse schema with a single key 'tests'.\n"
        )

        try:
            res: CreativeTestsResponse = self.gateway.query_structured(
                prompt=prompt,
                input_str=model.model_dump_json(indent=2),
                schema_class=CreativeTestsResponse,
            )
            if res and res.tests:
                valid_tests = [tc for tc in res.tests if self._validate_primitives(tc)]
                if valid_tests:
                    return valid_tests
        except Exception as e:
            print(f"  [!] LLMCreativeGenerator Gemini Query Note: {e}")

        # Static domain fallback if Gemini is unavailable
        return self._fallback_cases(model)

    def _fallback_cases(self, model: FirmwareModel) -> List[TestCase]:
        inp_name = model.inputs[0].name if model.inputs else "temp"
        out_name = model.outputs[0].name if model.outputs else "fan"

        c01 = TestCase(
            id="C01_creative",
            title=f"LLM Creative: Intermittent sensor reconnection during ramp heating for {inp_name}",
            category="combo",
            rationale=f"Simulates sensor being unplugged then reconnected while {inp_name} is rising.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target=inp_name, value=35.0),
                Step(at_ms=500, action="inject_fault", target=inp_name, value="open_circuit"),
                Step(at_ms=1500, action="clear_fault", target=inp_name),
                Step(at_ms=2000, action="set_input", target=inp_name, value=25.0),
                Step(at_ms=3000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="output_eq", target=out_name, value="OFF", rule_id="R2")
            ],
            priority=2,
            origin="llm"
        )

        c02 = TestCase(
            id="C02_creative",
            title=f"LLM Creative: Rapid MCU hard reset stress test during active output state for {out_name}",
            category="timing",
            rationale="Simulates rapid power brownouts while MCU is driving outputs.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target=inp_name, value=40.0),
                Step(at_ms=500, action="reset"),
                Step(at_ms=1000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="output_eq", target=out_name, value="OFF", rule_id="I1")
            ],
            priority=2,
            origin="llm"
        )

        return [tc for tc in [c01, c02] if self._validate_primitives(tc)]

    def _validate_primitives(self, test_case: TestCase) -> bool:
        """Verify all test steps and expectations use allowed action and expect primitives."""
        for step in test_case.steps:
            if step.action not in self.ALLOWED_ACTIONS:
                return False
        for exp in test_case.expects:
            if exp.kind not in self.ALLOWED_EXPECT_KINDS:
                return False
        return True
