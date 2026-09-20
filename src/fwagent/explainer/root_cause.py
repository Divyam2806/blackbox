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

        def get_localized_lines(verdict: Optional[Verdict], fallback_lines: List[int]) -> List[int]:
            if graph and line_index and verdict:
                locs = localizer.localize(verdict, model, graph, line_index)
                if locs:
                    return [l.line for l in locs[:5]]
            valid = sorted(list(set(fallback_lines)))
            if valid:
                return valid
            if line_index and line_index.lines:
                return list(range(1, min(6, len(line_index.lines) + 1)))
            return [1]

        # Check input unit & kind for domain-accurate fallback phrasing
        first_input = model.inputs[0] if (model and model.inputs) else None
        is_cm_sensor = first_input and first_input.unit == "cm"
        has_timeout_error = any("loop timeout" in e.trigger.lower() or "i/o timeout" in e.trigger.lower() for e in (model.error_paths or [])) if model else False

        # Check Finding F1: Sensor Faults / Plausibility Not Detected
        f1_failures = [
            v for v in verdicts
            if v.status == "FAIL" and ("R3" in v.rule_ids or "I2" in v.rule_ids or "raw" in v.expected.lower() or "fault" in v.expected.lower() or "plausible" in v.expected.lower())
        ]
        if f1_failures:
            ev_tests = [v.test_id for v in f1_failures]
            first_fail = f1_failures[0]
            dynamic_lines = get_localized_lines(first_fail, err_lines + input_lines + thresh_lines)

            if has_timeout_error or is_cm_sensor:
                title_str = f"Sensor measurement returns 0 on timeout, making failure indistinguishable from 0 reading for {input_name}"
                cause_str = f"Measurement wait loop returns 0 on timeout (++timeout > 60000), which main loop processes as a valid 0 reading instead of flagging a fault."
                fix_str = (
                    f"// 1. Return explicit error sentinel (e.g. 0xFFFF) on timeout:\n"
                    f"if (++timeout > 60000) return 0xFFFF;\n\n"
                    f"// 2. Handle error sentinel in main loop:\n"
                    f"uint16_t val = get_{input_name}();\n"
                    f"if (val == 0xFFFF) {{\n"
                    f"    // Trigger error LED or fail-safe state\n"
                    f"    PORTB |= (1 << LED_PIN);\n"
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
                evidence_tests=ev_tests,
                evidence_lines=[f"{', '.join(ev_tests[:3])}: Unvalidated boundary values accepted for {input_name}"],
                firmware_lines=dynamic_lines,
                likely_cause=cause_str,
                suggested_fix=fix_str
            ))

        # Check Finding F2: Error Path Unimplemented
        f2_failures = [
            v for v in verdicts
            if v.status == "FAIL" and v not in f1_failures and ("ERR" in v.observed or "error" in v.observed.lower() or "fault" in v.observed.lower())
        ]
        if f2_failures:
            ev_tests = [v.test_id for v in f2_failures]
            first_fail = f2_failures[0]
            dynamic_lines = get_localized_lines(first_fail, err_lines + output_lines + thresh_lines)
            findings.append(Finding(
                id="F2",
                severity="High",
                title=f"Sensor failure is not explicitly detected or reported on {err_pin}",
                evidence_tests=ev_tests,
                evidence_lines=[f"{', '.join(ev_tests[:2])}: Sensor failure returns fallback value without notifying operator"],
                firmware_lines=dynamic_lines,
                likely_cause=f"Measurement failure on {input_name} triggers silent fallback ({output_name}) rather than explicitly reporting a fault state.",
                suggested_fix=(
                    f"// Distinguish sensor failure from valid state and report fault:\n"
                    f"if (is_{input_name}_fault()) {{\n"
                    f"    // Explicit fail-safe state\n"
                    f"    {output_name} = SAFE_VALUE;\n"
                    f"}}"
                )
            ))

        # Check Finding F3: Output Chatter Near Threshold
        clean_thresh_sig = input_name if ("millis" in thresh_sig.lower() or "time" in thresh_sig.lower() or "timer" in thresh_sig.lower()) else thresh_sig
        f3_warns = [
            v for v in verdicts
            if v.status == "WARN" or "I3" in v.rule_ids or "chattering" in v.observed.lower()
        ]
        if f3_warns:
            ev_tests = [v.test_id for v in f3_warns]
            first_warn = f3_warns[0]
            dynamic_lines = get_localized_lines(first_warn, thresh_lines)
            
            if is_cm_sensor:
                cause_text = f"Direct linear calculation of {output_name} from {clean_thresh_sig} without low-pass filtering causes single-sample sensor fluctuations to produce proportional control output jitter."
                fix_text = (
                    f"// Apply low-pass exponential moving average filter to {clean_thresh_sig}:\n"
                    f"static float filtered_{clean_thresh_sig} = {thresh_val};\n"
                    f"filtered_{clean_thresh_sig} = (filtered_{clean_thresh_sig} * 7 + {clean_thresh_sig} * 3) / 10;\n"
                    f"// Calculate {output_name} using filtered_{clean_thresh_sig}"
                )
            else:
                cause_text = f"Direct output calculation from {clean_thresh_sig} without low-pass deadband filtering causes output instability on noisy readings."
                fix_text = (
                    f"// Add deadband filter for {output_name}:\n"
                    f"if (abs({clean_thresh_sig} - last_{clean_thresh_sig}) > DEADBAND) {{\n"
                    f"    // Update {output_name}\n"
                    f"}}"
                )

            findings.append(Finding(
                id="F3",
                severity="Medium",
                title=f"{output_name} is directly sensitive to single-sample sensor fluctuations for {clean_thresh_sig}",
                evidence_tests=ev_tests,
                evidence_lines=[f"{', '.join(ev_tests[:2])}: Output fluctuations recorded under noisy sensor readings"],
                firmware_lines=dynamic_lines,
                likely_cause=cause_text,
                suggested_fix=fix_text
            ))


        # Check Finding F4: Boundary Ambiguity
        f4_ambiguous = [
            v for v in verdicts
            if v.status == "AMBIGUOUS"
        ]
        if f4_ambiguous:
            ev_tests = [v.test_id for v in f4_ambiguous]
            first_amb = f4_ambiguous[0]
            dynamic_lines = get_localized_lines(first_amb, thresh_lines)
            findings.append(Finding(
                id="F4",
                severity="Info",
                title=f"Boundary comparison ambiguity for {thresh_sig} at exact value {thresh_val}",
                evidence_tests=ev_tests,
                evidence_lines=[f"{', '.join(ev_tests[:2])}: Firmware comparison '{thresh_op}' differs from specification at exact value {thresh_val}"],
                firmware_lines=dynamic_lines,
                likely_cause=f"Specification and code differ on exact boundary equality behavior at {thresh_val}.",
                suggested_fix=f"Clarify specification requirement: explicit rule for exact equality at {thresh_val}."
            ))

        return findings



