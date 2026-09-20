"""
Hardware Fault Injection Test Generator.
Generates tests for open circuit (raw 1023), short circuit (raw 0), frozen value,
fault recovery, and combination fault scenarios.
"""

from typing import List
from fwagent.models import FirmwareModel, TestCase, Step, Expect


class FaultGenerator:
    def __init__(self, adc_resolution_bits: int = 10):
        self.max_counts = (1 << adc_resolution_bits) - 1

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        test_cases: List[TestCase] = []

        # T11: Sensor open circuit (raw 1023)
        t11 = TestCase(
            id="T11",
            title="Fault: Sensor open circuit (raw 1023)",
            category="fault",
            rationale="Disconnection of NTC/sensor pulls ADC to VCC rail (1023). System must signal error and not misinterpret as 100°C.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="inject_fault", target="temp", value="open_circuit"),
                Step(at_ms=100, action="set_input", target="temp", value=self.max_counts),
                Step(at_ms=2000, action="wait", value=2000),
            ],
            expects=[
                Expect(kind="serial_contains", value="ERR", rule_id="R3"),
                Expect(kind="no_change", target="fan", rule_id="I2"),
            ],
            priority=1,
        )
        test_cases.append(t11)

        # T12: Sensor short circuit (raw 0)
        t12 = TestCase(
            id="T12",
            title="Fault: Sensor short circuit (raw 0)",
            category="fault",
            rationale="Short circuit to GND forces ADC to 0. System must signal error (R3, I2).",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="inject_fault", target="temp", value="short_to_gnd"),
                Step(at_ms=100, action="set_input", target="temp", value=0),
                Step(at_ms=2000, action="wait", value=2000),
            ],
            expects=[
                Expect(kind="serial_contains", value="ERR", rule_id="R3"),
            ],
            priority=1,
        )
        test_cases.append(t12)

        # T14: Sensor frozen / no update
        t14 = TestCase(
            id="T14",
            title="Fault: Sensor frozen / stuck reading",
            category="fault",
            rationale="Sensor value frozen at last reading for 5 seconds. Expect error after timeout (R3).",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=256),  # 25°C
                Step(at_ms=500, action="inject_fault", target="temp", value="stuck"),
                Step(at_ms=5000, action="wait", value=5000),
            ],
            expects=[
                Expect(kind="serial_contains", value="ERR", rule_id="R3")
            ],
            priority=2,
        )
        test_cases.append(t14)

        # T15: Fault recovery (Fault applied then valid 25°C)
        t15 = TestCase(
            id="T15",
            title="Fault: Recovery after fault cleared",
            category="fault",
            rationale="System should clear error state and return to normal operation when valid sensor reading resumes.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="inject_fault", target="temp", value="open_circuit"),
                Step(at_ms=1000, action="clear_fault", target="temp"),
                Step(at_ms=1100, action="set_input", target="temp", value=256),  # 25°C
                Step(at_ms=2000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=OFF", rule_id="R2")
            ],
            priority=2,
        )
        test_cases.append(t15)

        # T16: Combo - Hot (fan ON) then sensor short (raw 0)
        t16 = TestCase(
            id="T16",
            title="Combo: Hot state followed by sensor short circuit",
            category="combo",
            rationale="When running hot with fan ON, a sudden short circuit must fail-safe and not silently turn off fan without error.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=409),  # 40°C
                Step(at_ms=1000, action="inject_fault", target="temp", value="short_to_gnd"),
                Step(at_ms=1000, action="set_input", target="temp", value=0),
                Step(at_ms=2000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="serial_contains", value="ERR", rule_id="R3")
            ],
            priority=1,
        )
        test_cases.append(t16)

        # T17: Combo - Hot + intermittent glitch
        t17 = TestCase(
            id="T17",
            title="Combo: Hot state with single-sample noise glitch",
            category="combo",
            rationale="Single sample noise spike must not crash system or cause improper lockup.",
            steps=[
                Step(at_ms=0, action="reset"),
                Step(at_ms=100, action="set_input", target="temp", value=409),  # 40°C
                Step(at_ms=1000, action="inject_fault", target="temp", value="glitch"),
                Step(at_ms=2000, action="wait", value=1000),
            ],
            expects=[
                Expect(kind="serial_contains", value="FAN=ON", rule_id="R1")
            ],
            priority=2,
        )
        test_cases.append(t17)

        return test_cases
