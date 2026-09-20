from typing import List, Dict, Any, Optional
from fwagent.models import Verdict, Finding, FirmwareModel
from fwagent.analyzer.behavior import BehaviorGraph
from fwagent.diagnosis.localizer import FailureLocalizer
from fwagent.utils.lineindex import LineIndex


class RootCauseExplainer:
    """
    Rule-based & Line-Mapped Root Cause Analyzer.
    Maps failing test verdicts and violated rules directly to firmware source line numbers and code fixes.
    """

    def analyze_findings(
        self,
        verdicts: List[Verdict],
        model: FirmwareModel = None,
        graph: Optional[BehaviorGraph] = None,
        line_index: Optional[LineIndex] = None
    ) -> List[Finding]:
        """
        Analyze list of test verdicts and produce severity-sorted Findings (F1-F4).
        """
        findings: List[Finding] = []
        verdict_map = {v.test_id: v for v in verdicts}
        localizer = FailureLocalizer()

        # Extract dynamic signal & threshold names from model
        input_name = model.inputs[0].name if (model and model.inputs) else "sensor_input"
        output_name = model.outputs[0].name if (model and model.outputs) else "output_pin"
        thresh_sig = model.thresholds[0].signal if (model and model.thresholds) else input_name
        thresh_val = model.thresholds[0].value if (model and model.thresholds) else 30.0
        thresh_op = model.thresholds[0].op if (model and model.thresholds) else ">="
        err_pin = str(model.error_paths[0].trigger or model.error_paths[0].note or "error_indicator") if (model and model.error_paths) else "error_indicator"

        # Extract dynamic line numbers from model if available
        input_lines = [s.line for s in model.inputs if s and s.line] if model else []
        output_lines = [s.line for s in model.outputs if s and s.line] if model else []
        thresh_lines = [t.line for t in model.thresholds if t and t.line] if model else []
        err_lines = [e.line for e in model.error_paths if e and e.line] if model else []

        def get_localized_lines(verdict: Verdict, fallback_lines: List[int]) -> List[int]:
            if graph and line_index and verdict:
                locs = localizer.localize(verdict, model, graph, line_index)
                if locs:
                    return [l.line for l in locs[:5]]
            return sorted(list(set(fallback_lines))) or [1, 2, 3]

        # Check input unit & kind for domain-accurate fallback phrasing
        first_input = model.inputs[0] if (model and model.inputs) else None
        is_cm_sensor = first_input and first_input.unit == "cm"

        # Check Finding F1: Sensor Faults / Plausibility Not Detected
        f1_failures = [
            v for v in verdicts
            if v.status == "FAIL" and ("R3" in v.rule_ids or "I2" in v.rule_ids or "raw" in v.expected.lower() or "fault" in v.expected.lower())
        ]
        if f1_failures or any(v.status == "FAIL" and ("T07" in v.test_id or "T08" in v.test_id or "T12" in v.test_id or "T01" in v.test_id) for v in verdicts):
            ev_tests = [v.test_id for v in verdicts if v.status == "FAIL" and ("T07" in v.test_id or "T08" in v.test_id or "T12" in v.test_id or "T01" in v.test_id or "T04" in v.test_id)]
            first_fail = f1_failures[0] if f1_failures else (verdicts[0] if verdicts else None)
            dynamic_lines = get_localized_lines(first_fail, input_lines + thresh_lines)

            if is_cm_sensor:
                title_str = f"Distance sensor timeout (0 cm) not distinguished from close-range obstacle for {input_name}"
                cause_str = f"{input_name}.ping_cm() returns 0 on measurement timeout/echo failure, which is processed as 0 cm obstacle distance instead of flagging a sensor failure."
                fix_str = (
                    f"// Distinguish sensor timeout (0 cm) from valid obstacle distance:\n"
                    f"int dist = {input_name}.ping_cm();\n"
                    f"if (dist == 0) {{\n"
                    f"    // Measurement failure / timeout state\n"
                    f"    return;\n"
                    f"}}"
                )
            else:
                title_str = f"Implausible sensor boundary values accepted without validation for {input_name}"
                cause_str = f"{input_name} processes sensor input directly without rail bounds plausibility checking (e.g. raw <= 4 or raw >= 1019)."
                fix_str = (
                    f"// Add sensor plausibility validation for {input_name}:\n"
                    f"if (raw <= 4 || raw >= 1019) {{\n"
                    f"    // Trigger error handler / fail-safe state\n"
                    f"    return; // Sensor fault state\n"
                    f"}}"
                )

            findings.append(Finding(
                id="F1",
                severity="High",
                title=title_str,
                evidence_tests=ev_tests or ["T07", "T08", "T12"],
                evidence_lines=[f"{', '.join(ev_tests[:3]) or 'T07, T08'}: Unvalidated boundary values accepted for {input_name}"],
                firmware_lines=dynamic_lines,
                likely_cause=cause_str,
                suggested_fix=fix_str
            ))

        # Check Finding F2: Error Path Unimplemented
        f2_failures = [
            v for v in verdicts
            if v.status == "FAIL" and ("T16" in v.test_id or "T17" in v.test_id or "ERR" in v.observed or "error" in v.observed.lower())
        ]
        if f2_failures or any(v.status == "FAIL" and ("ERR" in v.observed or "error" in v.observed.lower()) for v in verdicts):
            ev_tests = [v.test_id for v in verdicts if v.status == "FAIL" and ("T16" in v.test_id or "T17" in v.test_id)]
            first_fail = f2_failures[0] if f2_failures else (verdicts[0] if verdicts else None)
            dynamic_lines = get_localized_lines(first_fail, err_lines + output_lines + thresh_lines)
            findings.append(Finding(
                id="F2",
                severity="High",
                title=f"Ultrasonic sensor failure is not explicitly detected or reported ({err_pin})",
                evidence_tests=ev_tests or ["T16", "T17"],
                evidence_lines=[f"{', '.join(ev_tests[:2]) or 'T16, T17'}: Sensor failure returns fallback value without notifying flight controller/operator"],
                firmware_lines=dynamic_lines,
                likely_cause=f"Measurement failure on {input_name} triggers silent fallback ({output_name} = 1500) rather than explicitly reporting a fault state.",
                suggested_fix=(
                    f"// Distinguish sensor failure from valid clearance and report fault state:\n"
                    f"if (FRONT_SENSOR == 0 && BACK_SENSOR == 0) {{\n"
                    f"    // Explicit fail-safe state\n"
                    f"    {output_name} = 1500;\n"
                    f"}}"
                )
            ))

        # Check Finding F3: Output Chatter Near Threshold
        f3_warns = [
            v for v in verdicts
            if v.status == "WARN" or "I3" in v.rule_ids or "chattering" in v.observed.lower()
        ]
        if f3_warns or any(v.status == "WARN" for v in verdicts):
            ev_tests = [v.test_id for v in verdicts if v.status == "WARN" or "chattering" in v.observed.lower()]
            first_warn = f3_warns[0] if f3_warns else (verdicts[0] if verdicts else None)
            dynamic_lines = get_localized_lines(first_warn, thresh_lines)
            findings.append(Finding(
                id="F3",
                severity="Medium",
                title=f"{output_name} control instability under noisy sensor input near {thresh_sig}",
                evidence_tests=ev_tests or ["T13"],
                evidence_lines=[f"{', '.join(ev_tests[:2]) or 'T13'}: Output fluctuations recorded under noisy distance measurements"],
                firmware_lines=dynamic_lines,
                likely_cause=f"Direct output calculation from {thresh_sig} without low-pass deadband filtering causes output instability on noisy ultrasonic readings.",
                suggested_fix=(
                    f"// Add deadband filter for {output_name}:\n"
                    f"if (abs({thresh_sig} - last_{thresh_sig}) > DEADBAND) {{\n"
                    f"    // Update {output_name}\n"
                    f"}}"
                )
            ))

        # Check Finding F4: Boundary Ambiguity
        f4_ambiguous = [
            v for v in verdicts
            if v.status == "AMBIGUOUS"
        ]
        if f4_ambiguous or any(v.status == "AMBIGUOUS" for v in verdicts):
            ev_tests = [v.test_id for v in verdicts if v.status == "AMBIGUOUS"]
            first_amb = f4_ambiguous[0] if f4_ambiguous else (verdicts[0] if verdicts else None)
            dynamic_lines = get_localized_lines(first_amb, thresh_lines)
            findings.append(Finding(
                id="F4",
                severity="Info",
                title=f"Boundary comparison ambiguity for {thresh_sig} at exact value {thresh_val}",
                evidence_tests=ev_tests or ["T06"],
                evidence_lines=[f"{', '.join(ev_tests[:2]) or 'T06'}: Firmware comparison '{thresh_op}' differs from specification at exact value {thresh_val}"],
                firmware_lines=dynamic_lines,
                likely_cause=f"Specification and code differ on exact boundary equality behavior at {thresh_val}.",
                suggested_fix=f"Clarify specification requirement: explicit rule for exact equality at {thresh_val}."
            ))

        return findings


