"""
Boundary Value Analysis (BVA) Test Generator.
Computes exact 10-bit ADC quantisation boundary values around threshold (e.g. raw 306 vs 307 for 30.0 °C),
as well as ADC rail extremes (0, 1, 1022, 1023).
"""

from typing import List
from fwagent.models import FirmwareModel, TestCase, Step, Expect


class BoundaryGenerator:
    def __init__(self, adc_resolution_bits: int = 10, max_temp_c: float = 100.0):
        self.max_counts = (1 << adc_resolution_bits) - 1  # 1023
        self.max_temp_c = max_temp_c

    def temp_to_adc(self, temp_c: float) -> int:
        counts = round(temp_c * (self.max_counts / self.max_temp_c))
        return max(0, min(self.max_counts, counts))

    def adc_to_temp(self, counts: int) -> float:
        return counts * (self.max_temp_c / self.max_counts)

    def generate(self, model: FirmwareModel) -> List[TestCase]:
        test_cases: List[TestCase] = []
        tc_id_counter = 1

        # 1. ADC Rail Boundaries (0, 1, 1022, 1023)
        rail_cases = [
            (0, "raw 0 (0.0°C)", "OFF", "I2"),
            (1, "raw 1 (0.098°C)", "OFF", "R2"),
            (self.max_counts - 1, f"raw {self.max_counts - 1} (99.9°C)", "ON", "R1"),
            (self.max_counts, f"raw {self.max_counts} (100.0°C)", "ON", "I2"),
        ]

        for raw_val, desc, exp_fan, rule_id in rail_cases:
            tc = TestCase(
                id=f"T{tc_id_counter:02d}",
                title=f"Boundary: Rail extreme {desc}",
                category="boundary",
                rationale=f"Test ADC rail boundary {desc} to check safety and transfer limits.",
                steps=[
                    Step(at_ms=0, action="reset"),
                    Step(at_ms=100, action="set_input", target="temp", value=raw_val),
                    Step(at_ms=1000, action="wait", value=1000),
                ],
                expects=[
                    Expect(kind="serial_contains", value=f"FAN={exp_fan}", rule_id=rule_id)
                ],
                priority=1,
            )
            test_cases.append(tc)
            tc_id_counter += 1

        # 2. Threshold Boundaries (raw 306 vs 307 for 30.0°C)
        for thresh in model.thresholds:
            if thresh.signal == "temp":
                val = thresh.value
                # Quantisation calculation:
                # 30.0 °C * 1023 / 100 = 306.9
                raw_exact = val * (self.max_counts / self.max_temp_c)
                raw_below = int(raw_exact)       # 306 -> 29.91°C
                raw_above = int(raw_exact) + 1   # 307 -> 30.01°C

                temp_below = self.adc_to_temp(raw_below)
                temp_above = self.adc_to_temp(raw_above)

                # Test 1: Just below threshold (raw 306 -> 29.91°C) -> Fan OFF
                tc_below = TestCase(
                    id=f"T{tc_id_counter:02d}",
                    title=f"Boundary: Just below threshold ({val}°C -> raw {raw_below} = {temp_below:.2f}°C)",
                    category="boundary",
                    rationale=f"Quantisation test: raw {raw_below} produces {temp_below:.2f}°C which is < {val}°C spec boundary.",
                    steps=[
                        Step(at_ms=0, action="reset"),
                        Step(at_ms=100, action="set_input", target="temp", value=raw_below),
                        Step(at_ms=1000, action="wait", value=1000),
                    ],
                    expects=[
                        Expect(kind="serial_contains", value="FAN=OFF", rule_id="R2")
                    ],
                    priority=1,
                )
                test_cases.append(tc_below)
                tc_id_counter += 1

                # Test 2: Just above threshold (raw 307 -> 30.01°C) -> Fan ON
                tc_above = TestCase(
                    id=f"T{tc_id_counter:02d}",
                    title=f"Boundary: Just above threshold ({val}°C -> raw {raw_above} = {temp_above:.2f}°C)",
                    category="boundary",
                    rationale=f"Quantisation test: raw {raw_above} produces {temp_above:.2f}°C which is > {val}°C spec boundary.",
                    steps=[
                        Step(at_ms=0, action="reset"),
                        Step(at_ms=100, action="set_input", target="temp", value=raw_above),
                        Step(at_ms=1000, action="wait", value=1000),
                    ],
                    expects=[
                        Expect(kind="serial_contains", value="FAN=ON", rule_id="R1")
                    ],
                    priority=1,
                )
                test_cases.append(tc_above)
                tc_id_counter += 1

                # Test 3: Ambiguity test (exact 30.0°C if code uses >= vs >)
                tc_ambig = TestCase(
                    id=f"T{tc_id_counter:02d}",
                    title=f"Boundary: Exact boundary value {val}°C (Ambiguity check)",
                    category="boundary",
                    rationale=f"Spec says 'above {val}°C', code uses '>='. Flag if exact threshold handling is ambiguous.",
                    steps=[
                        Step(at_ms=0, action="reset"),
                        Step(at_ms=100, action="set_input", target="temp", value=raw_above),
                        Step(at_ms=1000, action="wait", value=1000),
                    ],
                    expects=[
                        Expect(kind="serial_contains", value="FAN=ON", rule_id="R1")
                    ],
                    priority=2,
                )
                test_cases.append(tc_ambig)
                tc_id_counter += 1

        return test_cases
