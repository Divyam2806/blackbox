"""
Gemini API Explainer.
Uses Gemini 1.5 Flash/Pro via LLMGateway to generate deep domain-specific root cause analysis
and targeted C++ patches for firmware test failures.
"""

import json
import os
from typing import List, Optional
from fwagent.models import Verdict, Finding, FirmwareModel, FindingsResponse, ImprovementSuggestion, SuggestionsResponse
from fwagent.llm.gateway import LLMGateway


class GeminiExplainer:
    """
    LLM-powered Root Cause Explainer & System Improvement Advisor using Gemini API.
    Dynamically analyzes spec text, source code, and failing execution traces to produce
    line-mapped findings, drop-in C++ code fixes, and architectural suggestions.
    """

    def __init__(self, provider: str = "gemini"):
        self.gateway = LLMGateway(provider=provider)

    def analyze_findings(
        self,
        verdicts: List[Verdict],
        model: Optional[FirmwareModel] = None,
        spec_text: str = "",
        firmware_code: str = "",
    ) -> Optional[List[Finding]]:
        """
        Perform AI analysis on failing verdicts. Returns list of Findings or None if LLM unavailable.
        """
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
        if not api_key:
            return None

        # Filter out non-failing/warning verdicts if all passed
        failing_verdicts = [v for v in verdicts if v.status in ("FAIL", "WARN", "AMBIGUOUS")][:8]
        if not failing_verdicts:
            return []

        prompt = (
            "You are an expert embedded firmware C/C++ verification engine.\n"
            "Analyze the provided specification, C/C++ source code, extracted firmware model, and test execution verdicts.\n"
            "Identify real root causes for test failures and generate high-priority Findings.\n"
            "CRITICAL CONSTRAINTS:\n"
            "- Keep 'likely_cause' VERY CONCISE: strictly 1-2 sentences maximum (under 30 words).\n"
            "- Focus directly on the code bug/flaw. Do NOT write long paragraphs or quote entire requirements.\n"
            "- IMPORTANT: Your response MUST be a JSON object with a single top-level key \"findings\" containing a list of Finding objects.\n"
            "Example JSON schema:\n"
            "{\n"
            "  \"findings\": [\n"
            "    {\n"
            "      \"id\": \"F1\",\n"
            "      \"severity\": \"High\",\n"
            "      \"title\": \"Domain-specific title referencing actual variable/sensor names\",\n"
            "      \"evidence_tests\": [\"T01\", \"T04\"],\n"
            "      \"evidence_lines\": [\"T01: Observed timeout zero accepted as 0 cm distance\"],\n"
            "      \"firmware_lines\": [42, 45],\n"
            "      \"likely_cause\": \"Short, direct 1-sentence technical explanation of the flaw in code logic.\",\n"
            "      \"suggested_fix\": \"// C++ drop-in code patch using exact project variables\\nif (val == 0) return;\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )

        # Build structured evidence trace from evidence_chain
        traces = []
        for v in failing_verdicts:
            chain = getattr(v, "evidence_chain", [])
            if chain:
                trace_lines = "\n".join(
                    f"    [{e['ms']}ms] [{e['category'].upper()}] {e['detail']}"
                    for e in chain[:20]
                )
                traces.append(f"--- Test {v.test_id} ({v.status}) ---\n{trace_lines}")
        evidence_trace_block = "\n".join(traces) if traces else "(no structured trace available)"

        input_data = {
            "spec_text": spec_text[:2500] if spec_text else "",
            "firmware_code": firmware_code[:5000] if firmware_code else "",
            "firmware_model": model.model_dump(mode="json") if model else {},
            "verdicts": [v.model_dump(mode="json") for v in failing_verdicts],
            "execution_traces": evidence_trace_block,
        }

        try:
            res: FindingsResponse = self.gateway.query_structured(
                prompt=prompt,
                input_str=json.dumps(input_data, indent=2),
                schema_class=FindingsResponse,
            )
            if res and res.findings:
                for f in res.findings:
                    if f.severity:
                        f.severity = f.severity.capitalize()
                    if f.likely_cause:
                        sentences = [s.strip() for s in f.likely_cause.split(". ") if s.strip()]
                        if len(sentences) > 2:
                            f.likely_cause = ". ".join(sentences[:2]) + "."
                        elif f.likely_cause and not f.likely_cause.endswith("."):
                            f.likely_cause += "."
                return res.findings
        except Exception as e:
            print(f"  [!] GeminiExplainer Exception: {e}")
            return None

        return None

    def generate_suggestions(
        self,
        verdicts: List[Verdict],
        model: Optional[FirmwareModel] = None,
        findings: Optional[List[Finding]] = None,
        spec_text: str = "",
        firmware_code: str = "",
    ) -> List[ImprovementSuggestion]:
        """
        Queries Gemini API to generate deep firmware improvement suggestions and architectural recommendations.
        """
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
        
        prompt = (
            "You are an expert embedded firmware systems architect and static analysis advisor.\n"
            "Analyze the target firmware code, extracted model, and test findings to provide 3-4 concrete, actionable Suggestions for Improvement.\n"
            "Focus on: Rail Boundary Validation, Filtering/Hysteresis, Explicit Error Indicator States, Watchdog Timers, State Machine Resilience.\n"
            "Your response MUST be a JSON object conforming to this schema:\n"
            "{\n"
            "  \"suggestions\": [\n"
            "    {\n"
            "      \"category\": \"Fault Tolerance & Plausibility\",\n"
            "      \"title\": \"Implement ADC Rail Plausibility Checks\",\n"
            "      \"description\": \"Guard against open circuit or grounded sensor wires by rejecting raw counts <= 4 or >= 1019.\",\n"
            "      \"code_snippet\": \"if (raw <= 4 || raw >= 1019) { set_error_state(); }\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )

        input_data = {
            "firmware_name": model.firmware_name if model else "firmware",
            "inputs": [s.name for s in model.inputs] if model else [],
            "outputs": [s.name for s in model.outputs] if model else [],
            "findings": [f.model_dump(mode="json") for f in (findings or [])],
            "verdicts_summary": {
                "total": len(verdicts),
                "pass": sum(1 for v in verdicts if v.status == "PASS"),
                "fail": sum(1 for v in verdicts if v.status == "FAIL"),
            },
            "firmware_code": firmware_code[:4000] if firmware_code else "",
        }

        if api_key:
            try:
                res: SuggestionsResponse = self.gateway.query_structured(
                    prompt=prompt,
                    input_str=json.dumps(input_data, indent=2),
                    schema_class=SuggestionsResponse,
                )
                if res and res.suggestions:
                    return res.suggestions
            except Exception as e:
                print(f"  [!] Gemini suggestions exception: {e}")

        return self._generate_fallback_suggestions(model, findings)

    def _generate_fallback_suggestions(
        self,
        model: Optional[FirmwareModel] = None,
        findings: Optional[List[Finding]] = None,
    ) -> List[ImprovementSuggestion]:
        """Dynamic rule-based fallback suggestion generator using model input/output names."""
        inp_name = model.inputs[0].name if (model and model.inputs) else "sensor_input"
        out_name = model.outputs[0].name if (model and model.outputs) else "actuator_output"

        return [
            ImprovementSuggestion(
                category="Bounds Safety & Input Guarding",
                title=f"Add Sensor Rail Plausibility Validation for {inp_name}",
                description=f"Validate raw analog counts before processing {inp_name}. Extreme boundary counts (raw <= 4 or raw >= 1019) indicate open-circuit or short-to-VCC faults.",
                code_snippet=f"// Plausibility Check:\nif (raw_{inp_name} <= 4 || raw_{inp_name} >= 1019) {{\n    trigger_fault_state(); // Enter safe state\n    return;\n}}"
            ),
            ImprovementSuggestion(
                category="Signal Processing & Hysteresis",
                title=f"Apply Low-Pass Deadband Filter to {out_name}",
                description=f"Prevent rapid output chatter on {out_name} near control thresholds by introducing a deadband hysteresis window or exponential moving average (EMA) filter.",
                code_snippet=f"// Deadband Filter:\nif (abs(current_val - last_val) > DEADBAND_THRESHOLD) {{\n    update_{out_name}(current_val);\n    last_val = current_val;\n}}"
            ),
            ImprovementSuggestion(
                category="Fault State Machine",
                title="Explicit Error Indicator & Fail-Safe Recovery",
                description=f"Ensure sensor hardware failures drive an explicit error signal (e.g. error LED or bus fault message) rather than silently defaulting to output fallbacks.",
                code_snippet=f"// Explicit Error Handling:\nif (sensor_fault_detected) {{\n    digitalWrite(ERROR_PIN, HIGH);\n    digitalWrite({out_name.upper()}_PIN, LOW); // Fail-safe state\n}}"
            ),
            ImprovementSuggestion(
                category="System Resilience",
                title="Hardware Watchdog & Serial Communication Timeout",
                description="Enable internal watchdog timer (WDT) and add communication timeout handlers to ensure automatic recovery if main loop execution freezes.",
                code_snippet="// Watchdog Initialization:\nwdt_enable(WDTO_2S); // 2-second timeout\n// In main loop:\nwdt_reset();"
            )
        ]

