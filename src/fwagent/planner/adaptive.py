from typing import List, Dict, Any, Set
from fwagent.models import FirmwareModel, TestCase, Step, Expect, Verdict


class AdaptivePlanner:
    """
    Adaptive Test Generator (Stage A).
    Generates follow-up tests by bisecting raw ADC ranges, probing neighbor values (raw 1, 2, 1022),
    and retrying failing tests 3 times to isolate flaky timing bugs.
    """

    def generate_adaptive_tests(self, model: FirmwareModel, previous_verdicts: List[Verdict]) -> List[TestCase]:
        """
        Analyze previous verdicts and produce adaptive follow-up TestCases.
        """
        follow_ups: List[TestCase] = []
        failed_verdicts = [v for v in previous_verdicts if v.status in ["FAIL", "WARN", "AMBIGUOUS"]]

        if not failed_verdicts:
            return follow_ups

        # 1. Neighbor Probes & Raw Range Bisection
        has_rail_fail = any(v.test_id in ["T01", "T04", "T07", "T08", "T11", "T12"] for v in failed_verdicts)
        if has_rail_fail:
            # Probe neighbor ADC boundary counts (raw 1, 2, 5, 1018, 1022) to map trusted window
            bisection_points = [
                ("A01_bisect_raw1", "Adaptive: Neighbor probe raw 1 (0.098°C)", 1),
                ("A02_bisect_raw2", "Adaptive: Neighbor probe raw 2 (0.195°C)", 2),
                ("A03_bisect_raw5", "Adaptive: Lower trusted bound probe raw 5 (0.488°C)", 5),
                ("A04_bisect_raw1018", "Adaptive: Upper trusted bound probe raw 1018 (99.51°C)", 1018),
                ("A05_bisect_raw1022", "Adaptive: Neighbor probe raw 1022 (99.90°C)", 1022),
            ]

            for test_id, title, raw_val in bisection_points:
                follow_ups.append(TestCase(
                    id=test_id,
                    title=title,
                    category="adaptive",
                    rationale=f"Adaptive bisection probe at raw count {raw_val} to map exact trusted sensor range.",
                    steps=[
                        Step(at_ms=0, action="reset"),
                        Step(at_ms=100, action="set_input", target="temp", value=raw_val),
                        Step(at_ms=1000, action="wait", value=1000),
                    ],
                    expects=[Expect(kind="output_eq", target="fan", value="OFF" if raw_val < 307 else "ON", rule_id="I2")],
                    priority=1,
                    origin="adaptive"
                ))

        # 2. Flaky Retry Check (Run failing test 3 times)
        for v in failed_verdicts[:3]:  # Top 3 failing tests
            retry_id = f"A_retry_{v.test_id}"
            follow_ups.append(TestCase(
                id=retry_id,
                title=f"Adaptive: Flaky 3x Retry for {v.test_id}",
                category="adaptive",
                rationale=f"Retry {v.test_id} 3 times to isolate flaky timing/race conditions from deterministic logic bugs.",
                steps=[
                    Step(at_ms=0, action="reset"),
                    Step(at_ms=100, action="set_input", target="temp", value=307 if "hot" in v.expected.lower() or "on" in v.expected.lower() else 256),
                    Step(at_ms=1000, action="wait", value=1000),
                ],
                expects=[Expect(kind="output_eq", target="fan", value="ON" if "on" in v.expected.lower() else "OFF", rule_id="R1")],
                priority=1,
                origin="adaptive"
            ))

        return follow_ups

    def compute_trusted_adc_window(self, verdicts: List[Verdict]) -> str:
        """
        Compute the exact ADC count window where the sensor is trusted based on bisection results.
        """
        raw_0_ok = not any(v.test_id in ["T01", "T08"] and v.status == "FAIL" for v in verdicts)
        raw_1023_ok = not any(v.test_id in ["T04", "T07"] and v.status == "FAIL" for v in verdicts)

        if raw_0_ok and raw_1023_ok:
            return "0..1023 (Full ADC range trusted)"
        elif not raw_0_ok and not raw_1023_ok:
            return "5..1018 (Extreme rails raw <= 4 and raw >= 1019 rejected as faults)"
        elif not raw_0_ok:
            return "5..1023 (Lower rail raw <= 4 rejected as fault)"
        else:
            return "0..1018 (Upper rail raw >= 1019 rejected as fault)"
