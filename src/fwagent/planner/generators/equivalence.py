"""
Equivalence Partitioning Test Generator.
Generates representative tests for valid input classes (Cold, Hot, Normal boot state).
"""

from typing import List
from fwagent.models import FirmwareModel, TestCase, Step, Expect


class EquivalenceGenerator:
    def __init__(self, adc_resolution_bits: int = 10, max_temp_c: float = 100.0):
        self.max_counts = (1 << adc_resolution_bits) - 1
        self.max_temp_c = max_temp_c

    def temp_to_adc(self, temp_c: float) -> int:
        return round(temp_c * (self.max_counts / self.max_temp_c))

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        test_cases: List[TestCase] = []

        # 1. State / Boot Normal test (T01)
        t01 = TestCase(
            id="T01",
            title="State: Reset and boot check",
            category="state",
            rationale="Verify system boots safely with outputs OFF as required by invariant I1.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=1000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=OFF", rule_id="I1")
            ],
            priority=1,
        )
        test_cases.append(t01)

        # 2. Normal Cold Operating Class (25°C, raw 256) -> Fan OFF (R2)
        raw_cold = self.temp_to_adc(25.0)
        t02 = TestCase(
            id="T02",
            title="Normal: Cold operating range (25°C)",
            category="normal",
            rationale="Standard cold input should keep fan OFF per requirement R2.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=raw_cold),
                Step(at_ms=2000, action="wait", value=2000),
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=OFF", rule_id="R2")
            ],
            priority=1,
        )
        test_cases.append(t02)

        # 3. Normal Hot Operating Class (40°C, raw 409) -> Fan ON (R1)
        raw_hot = self.temp_to_adc(40.0)
        t03 = TestCase(
            id="T03",
            title="Normal: Hot operating range (40°C)",
            category="normal",
            rationale="Standard hot input should turn fan ON per requirement R1.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=raw_hot),
                Step(at_ms=2000, action="wait", value=2000),
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=ON", rule_id="R1")
            ],
            priority=1,
        )
        test_cases.append(t03)

        return test_cases
