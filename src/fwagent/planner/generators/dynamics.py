"""
Dynamic Signal & Chatter Generator.
Generates test cases for temperature ramps, rapid swings, and threshold noise chatter.
"""

from typing import List
from fwagent.models import FirmwareModel, TestCase, Step, Expect


class DynamicsGenerator:
    def __init__(self, adc_resolution_bits: int = 10):
        self.max_counts = (1 << adc_resolution_bits) - 1

    def temp_to_adc(self, temp_c: float) -> int:
        return round(temp_c * (self.max_counts / 100.0))

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        test_cases: List[TestCase] = []

        # T07: Rapid swings 25 -> 35 -> 25 °C every 100ms for 3s
        t07 = TestCase(
            id="T07",
            title="Timing: Rapid temperature swings (25 <-> 35 °C)",
            category="timing",
            rationale="Verify firmware tracks rapid temperature changes without hanging or crashing.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=self.temp_to_adc(25.0)),
                Step(at_ms=500, action="set_input", target="temp", value=self.temp_to_adc(35.0)),
                Step(at_ms=1000, action="set_input", target="temp", value=self.temp_to_adc(25.0)),
                Step(at_ms=1500, action="set_input", target="temp", value=self.temp_to_adc(35.0)),
                Step(at_ms=2000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="serial_contains", value="T=", rule_id="R1")
            ],
            priority=2,
        )
        test_cases.append(t07)

        # T08: Noise ±0.4°C around 30°C threshold for 10s (Chatter test - Invariant I3)
        t08 = TestCase(
            id="T08",
            title="Timing: Threshold noise chatter (30°C ± 0.4°C)",
            category="timing",
            rationale="Noisy input around threshold must not cause relay/output chatter (>3 toggles in 10s). Tests Invariant I3 (Hysteresis).",
            steps=[
                Step(at_ms=0, action="reset"),
                # Oscillate between 29.6°C (raw 303) and 30.4°C (raw 311)
                Step(at_ms=100, action="set_input", target="temp", value=303),
                Step(at_ms=400, action="set_input", target="temp", value=311),
                Step(at_ms=800, action="set_input", target="temp", value=304),
                Step(at_ms=1200, action="set_input", target="temp", value=310),
                Step(at_ms=1600, action="set_input", target="temp", value=303),
                Step(at_ms=2000, action="set_input", target="temp", value=311),
                Step(at_ms=3000, action="wait", value=2000),
            ],
            expects=[
                Expect(kind="transition_count", target="fan", value=1, window_ms=(0, 5000), rule_id="I3")
            ],
            priority=1,
        )
        test_cases.append(t08)

        # T09: Ramp 20 -> 40 °C over 10 s (OFF -> ON state transition)
        t09 = TestCase(
            id="T09",
            title="State: Ramp heating (20°C -> 40°C)",
            category="state",
            rationale="Smooth temperature ramp upward. Expect exactly 1 transition from OFF -> ON.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=self.temp_to_adc(20.0)),
                Step(at_ms=1000, action="set_input", target="temp", value=self.temp_to_adc(28.0)),
                Step(at_ms=2000, action="set_input", target="temp", value=self.temp_to_adc(32.0)),
                Step(at_ms=3000, action="set_input", target="temp", value=self.temp_to_adc(40.0)),
                Step(at_ms=4000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="transition_count", target="fan", value=1, rule_id="R1")
            ],
            priority=1,
        )
        test_cases.append(t09)

        # T10: Ramp 40 -> 20 °C over 10 s (ON -> OFF state transition)
        t10 = TestCase(
            id="T10",
            title="State: Ramp cooling (40°C -> 20°C)",
            category="state",
            rationale="Smooth temperature ramp downward. Expect exactly 1 transition from ON -> OFF.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=self.temp_to_adc(40.0)),
                Step(at_ms=1000, action="set_input", target="temp", value=self.temp_to_adc(32.0)),
                Step(at_ms=2000, action="set_input", target="temp", value=self.temp_to_adc(28.0)),
                Step(at_ms=3000, action="set_input", target="temp", value=self.temp_to_adc(20.0)),
                Step(at_ms=4000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="transition_count", target="fan", value=1, rule_id="R2")
            ],
            priority=1,
        )
        test_cases.append(t10)

        return test_cases
