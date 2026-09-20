"""
State Machine & Soak / Reset Test Generator.
Generates tests for long-term soak stability and mid-operation hardware reset.
"""

from typing import List
from fwagent.models import FirmwareModel, TestCase, Step, Expect


class StateMachineGenerator:
    def __init__(self, adc_resolution_bits: int = 10):
        self.max_counts = (1 << adc_resolution_bits) - 1

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        test_cases: List[TestCase] = []

        # T18: Soak / Stress test
        t18 = TestCase(
            id="T18",
            title="Soak: Extended operation at 35°C (10 min virtual time)",
            category="soak",
            rationale="Verify system remains stable with no log buffer overflow, lockup, or memory degradation over long virtual runtime.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=358),  # 35°C
                Step(at_ms=1000, action="wait", value=10000),  # simulate soak period
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=ON", rule_id="R1")
            ],
            priority=3,
        )
        test_cases.append(t18)

        # T19: Reset mid-operation while hot
        t19 = TestCase(
            id="T19",
            title="State: Reset mid-operation while hot (40°C)",
            category="state",
            rationale="Trigger reset while hot. System must re-evaluate inputs cleanly after safe boot.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=409),  # 40°C
                Step(at_ms=1000, action="wait", value=1000),
                Step(at_ms=2000, action="reset"),  # mid-run reset
                Step(at_ms=2100, action="set_input", target="temp", value=409),
                Step(at_ms=3500, action="wait", value=1500),
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=ON", rule_id="I1")
            ],
            priority=2,
        )
        test_cases.append(t19)

        return test_cases
