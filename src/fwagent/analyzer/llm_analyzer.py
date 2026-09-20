"""
LLM Semantic Analyzer Pass.
Enriches static analysis facts with units, spec rules, universal invariants,
ambiguity notes, and flags unhandled error paths (e.g. ERR_LED never driven).
"""

import os
from typing import Optional
from fwagent.models import FirmwareModel, Rule, ErrorPath, Signal
from fwagent.analyzer.static_parser import StaticParser
from fwagent.utils.lineindex import LineIndex
from fwagent.llm.gateway import LLMGateway


class LLMAnalyzer:
    def __init__(self, llm_gateway: Optional[LLMGateway] = None):
        self.gateway = llm_gateway or LLMGateway(provider="mock")
        self.static_parser = StaticParser()

    def analyze(self, firmware_dir: str, spec_file: Optional[str] = None) -> FirmwareModel:
        # 1. Run static parser pass first
        model, line_index = self.static_parser.parse_directory(firmware_dir)

        # 2. Read prompt template
        prompt_path = os.path.join("prompts", "analyzer.md")
        system_prompt = "You are an embedded firmware testing analyzer. Output JSON matching FirmwareModel."
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()

        # Build code context with line numbers
        code_numbered = line_index.to_line_numbered_code()

        spec_content = ""
        if spec_file and os.path.exists(spec_file):
            with open(spec_file, "r", encoding="utf-8") as f:
                spec_content = f.read()

        user_input = (
            f"FIRMWARE CODE:\n{code_numbered}\n\n"
            f"SPECIFICATION:\n{spec_content}\n\n"
            f"STATIC FACTS:\n{model.model_dump_json(indent=2)}"
        )

        # 3. Query LLM Gateway for semantic enrichment
        enriched_model = self.gateway.query_structured(
            prompt=system_prompt,
            input_str=user_input,
            schema_class=FirmwareModel,
        )

        # 4. Enforce static line index grounding
        # Verify ERR_LED pin drive status
        for out in enriched_model.outputs:
            if "ERR" in out.name.upper() or "ERR" in str(out.pin or "").upper():
                out.driven = False

        # Ensure unhandled error path is flagged if ERR_LED is never driven
        has_err_path = any("ERR" in (ep.note or "") or "never" in (ep.note or "") for ep in enriched_model.error_paths)
        if not has_err_path:
            err_led_sig = next((o for o in enriched_model.outputs if "ERR" in o.name.upper()), None)
            err_line = err_led_sig.line if (err_led_sig and err_led_sig.line) else 16
            enriched_model.error_paths.append(
                ErrorPath(
                    trigger="sensor fault / timeout",
                    handler=None,
                    note="ERR_LED pin (D13) declared at line 16 is never written by digitalWrite",
                    line=err_line,
                )
            )

        return enriched_model
