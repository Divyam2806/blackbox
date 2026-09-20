from typing import List, Tuple, Dict, Any
from fwagent.models import TestCase, Verdict, FirmwareModel
from fwagent.evaluator.log_parser import LogParser
from fwagent.evaluator.invariants import InvariantChecker


class OracleEvaluator:
    """
    4-Tier Embedded Test Oracle Evaluator.
    Combines Spec Rules (R1-R3), Code Intent, Universal Invariants (I1-I3), and Metamorphic checks.
    Outputs evidence-backed verdicts (PASS, FAIL, WARN, AMBIGUOUS, INCONCLUSIVE).
    """

    def __init__(self, model: FirmwareModel = None):
        self.model = model
        self.log_parser = LogParser(model.log_patterns if model else None)
        self.invariants = InvariantChecker()

    def judge(self, test_case: TestCase, sim_output: Dict[str, Any]) -> Verdict:
        """
        Evaluate simulator output for a test case and assign verdict.
        """
        test_id = test_case.id
        logs: List[Tuple[int, str]] = sim_output.get("serial_logs", [])
        pin_trace: List[Dict[str, Any]] = sim_output.get("pin_trace", [])
        events = self.log_parser.parse(logs)

        evidence: List[str] = [f"[{t_ms}ms] {line}" for t_ms, line in logs[-5:]] if logs else ["No serial logs captured"]
        rule_ids = list(set(e.rule_id for e in test_case.expects if e.rule_id))

        has_err_log = any("ERR" in line.upper() or "FAULT" in line.upper() for _, line in logs)
        has_err_pin = any(entry.get("err_pin", 0) == 1 for entry in pin_trace)

        # Check Universal Invariant I1 (Boot Safety) for state/boot tests
        if test_case.category == "state" and ("boot" in test_case.title.lower() or "reset" in test_case.title.lower()):
            boot_ok, boot_msg = self.invariants.check_boot_safety(pin_trace, logs)
            if not boot_ok and not has_err_log:
                return Verdict(
                    test_id=test_id,
                    status="FAIL",
                    evidence=evidence + [boot_msg],
                    rule_ids=["I1"],
                    expected="Fan OFF at boot (I1)",
                    observed=boot_msg
                )

        # Check Universal Invariant I3 (Fan Chatter) for timing/chatter tests
        if test_case.category == "timing" or "chatter" in test_case.title.lower() or "noise" in test_case.title.lower():
            chatter_ok, toggle_count, chatter_msg = self.invariants.check_chatter(logs, max_toggles=3)
            if not chatter_ok:
                return Verdict(
                    test_id=test_id,
                    status="WARN",
                    evidence=evidence + [chatter_msg],
                    rule_ids=["I3"],
                    expected="Stable output near threshold (<= 3 toggles)",
                    observed=f"{toggle_count} toggles in 10s (Chattering detected)"
                )

        # Check Fault Injection & Invariant I2 (Plausible Data & Sensor Disconnect/Faults)
        is_fault_test = (
            test_case.category == "fault"
            or any("fault" in str(s.action).lower() for s in test_case.steps)
            or "open circuit" in test_case.title.lower()
            or "short circuit" in test_case.title.lower()
            or "frozen" in test_case.title.lower()
            or "rail extreme raw 0" in test_case.title.lower()
            or "rail extreme raw 1023" in test_case.title.lower()
        )

        if is_fault_test:
            plausible_ok, plausible_msg = self.invariants.check_plausible_data(test_case, pin_trace, logs)
            if not plausible_ok:
                return Verdict(
                    test_id=test_id,
                    status="FAIL",
                    evidence=evidence + [plausible_msg],
                    rule_ids=["R3", "I2"],
                    expected="Error signaled on sensor fault (R3, I2)",
                    observed="Sensor fault accepted as valid temp; ERR_LED (D13) remains LOW"
                )
            else:
                return Verdict(
                    test_id=test_id,
                    status="PASS",
                    evidence=evidence,
                    rule_ids=["R3", "I2"],
                    expected="Error signaled on sensor fault (R3, I2)",
                    observed="Error correctly signaled: " + (logs[-1][1] if logs else "ERR_LED HIGH")
                )

        # Check Spec-derived expectations (R1 & R2 & explicit Expect items)
        for expect in test_case.expects:
            kind = expect.kind
            target = expect.target or "fan"
            target_val = str(expect.value) if expect.value is not None else ""

            if kind == "output_eq":
                fan_events = [e for e in events if e.signal == target or e.signal == "fan"]
                if fan_events:
                    last_fan_val = str(fan_events[-1].value)
                    if last_fan_val != target_val and not has_err_log:
                        if "exactly 30.0" in test_case.title.lower() or "30.0" in test_case.stimulus:
                            return Verdict(
                                test_id=test_id,
                                status="AMBIGUOUS",
                                evidence=evidence,
                                rule_ids=[expect.rule_id] if expect.rule_id else ["R1"],
                                expected=f"Spec says 'above 30 C'; code uses '>=' ({target_val})",
                                observed=f"Observed FAN={last_fan_val} at boundary"
                            )
                        return Verdict(
                            test_id=test_id,
                            status="FAIL",
                            evidence=evidence,
                            rule_ids=[expect.rule_id] if expect.rule_id else ["R1"],
                            expected=f"{target.upper()}={target_val} ({expect.rule_id})",
                            observed=f"Observed {target.upper()}={last_fan_val}"
                        )
            elif kind == "serial_contains":
                serial_match = any(target_val in line for _, line in logs)
                if not serial_match and not has_err_log:
                    return Verdict(
                        test_id=test_id,
                        status="FAIL",
                        evidence=evidence,
                        rule_ids=[expect.rule_id] if expect.rule_id else ["R3"],
                        expected=f"Serial log containing '{target_val}'",
                        observed="No matching serial error log found"
                    )

        # Default PASS verdict if all oracle checks pass!
        last_log = logs[-1][1] if logs else "Executed cleanly"
        return Verdict(
            test_id=test_id,
            status="PASS",
            evidence=evidence,
            rule_ids=rule_ids if rule_ids else ["R1"],
            expected="Observed output matches expected requirement",
            observed=last_log
        )
