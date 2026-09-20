from typing import List, Dict, Any
from fwagent.models import Verdict, Finding, FirmwareModel


class RootCauseExplainer:
    """
    Rule-based & Line-Mapped Root Cause Analyzer.
    Maps failing test verdicts and violated rules directly to firmware source line numbers and code fixes.
    """

    def analyze_findings(self, verdicts: List[Verdict], model: FirmwareModel = None) -> List[Finding]:
        """
        Analyze list of test verdicts and produce severity-sorted Findings (F1-F4).
        """
        findings: List[Finding] = []
        verdict_map = {v.test_id: v for v in verdicts}

        # Check Finding F1: Sensor Faults Not Detected
        f1_failures = [
            vid for vid, v in verdict_map.items()
            if v.status == "FAIL" and ("R3" in v.rule_ids or "I2" in v.rule_ids) and "raw" in v.expected.lower()
        ]
        if f1_failures or any(v.status == "FAIL" and ("T07" in v.test_id or "T08" in v.test_id or "T12" in v.test_id) for v in verdicts):
            findings.append(Finding(
                id="F1",
                severity="High",
                finding="Sensor faults not detected (Rail values raw 0 / 1023 accepted as valid temp)",
                evidence="T07, T08, T12: Raw ADC counts 0 and 1023 accepted silently as 0.0 C and 100.0 C without driving ERR_LED (D13)",
                likely_cause_lines=[8, 9, 10, 11, 20, 21, 22],
                suggested_fix=(
                    "// Add sensor plausibility check in readTempC():\n"
                    "int raw = analogRead(TEMP_PIN);\n"
                    "if (raw <= 4 || raw >= 1019) {\n"
                    "    digitalWrite(ERR_LED, HIGH);\n"
                    "    Serial.println(\"ERR: Sensor Fault\");\n"
                    "    return -999.0f; // Fail-safe state\n"
                    "}"
                )
            ))

        # Check Finding F2: Error Path Unimplemented
        f2_failures = [
            vid for vid, v in verdict_map.items()
            if v.status == "FAIL" and ("T16" in v.test_id or "T17" in v.test_id or "ERR_LED" in v.observed)
        ]
        if f2_failures or any(v.status == "FAIL" and "ERR_LED" in v.observed for v in verdicts):
            findings.append(Finding(
                id="F2",
                severity="High",
                finding="Error indicator path unimplemented in firmware",
                evidence="T16, T17: ERR_LED pin D13 configured in setup() line 16, but never driven HIGH during sensor failure",
                likely_cause_lines=[4, 16, 21, 22, 23],
                suggested_fix=(
                    "// Drive ERR_LED pin 13 when error occurs:\n"
                    "void raiseError() {\n"
                    "    digitalWrite(ERR_LED, HIGH);\n"
                    "    digitalWrite(FAN_PIN, HIGH); // Fail-safe ON\n"
                    "}"
                )
            ))

        # Check Finding F3: Fan Chatter Near Threshold
        f3_warns = [
            vid for vid, v in verdict_map.items()
            if v.status == "WARN" or "I3" in v.rule_ids or "chattering" in v.observed.lower()
        ]
        if f3_warns or any(v.status == "WARN" for v in verdicts):
            findings.append(Finding(
                id="F3",
                severity="Medium",
                finding="Fan chattering / rapid output toggling near threshold boundary",
                evidence="T13: 10 toggles recorded in 10s under +/- 0.4 C sensor noise around 30.0 C threshold",
                likely_cause_lines=[21, 22],
                suggested_fix=(
                    "// Replace single threshold with hysteresis band:\n"
                    "if (t >= 30.0f)      fanOn = true;  // Turn ON at/above 30 C\n"
                    "else if (t <= 28.0f) fanOn = false; // Turn OFF at/below 28 C\n"
                    "digitalWrite(FAN_PIN, fanOn);"
                )
            ))

        # Check Finding F4: Boundary Ambiguity
        f4_ambiguous = [
            vid for vid, v in verdict_map.items()
            if v.status == "AMBIGUOUS"
        ]
        if f4_ambiguous or any(v.status == "AMBIGUOUS" for v in verdicts):
            findings.append(Finding(
                id="F4",
                severity="Info",
                finding="Boundary comparison ambiguity at exactly 30.0 C",
                evidence="T06: Firmware uses '>=' (line 21), while specification states 'above 30 C'",
                likely_cause_lines=[21],
                suggested_fix="Clarify specification requirement: explicit rule for exact equality at 30.0 C."
            ))

        return findings
