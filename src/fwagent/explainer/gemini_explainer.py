"""
Gemini API Explainer.
Uses Gemini 1.5 Flash/Pro via LLMGateway to generate deep domain-specific root cause analysis
and targeted C++ patches for firmware test failures.
"""

import json
import os
from typing import List, Optional
from fwagent.models import Verdict, Finding, FirmwareModel, FindingsResponse
from fwagent.llm.gateway import LLMGateway


class GeminiExplainer:
    """
    LLM-powered Root Cause Explainer using Gemini API.
    Dynamically analyzes spec text, source code, and failing execution traces to produce
    line-mapped findings and drop-in C++ code fixes.
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
                # Normalize and trim likely_cause to ensure conciseness
                for f in res.findings:
                    if f.severity:
                        f.severity = f.severity.capitalize()
                    if f.likely_cause:
                        # Keep maximum 2 sentences or 220 chars
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
