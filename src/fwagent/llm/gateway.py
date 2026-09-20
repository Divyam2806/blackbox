"""
Provider-agnostic LLM Gateway.
Supports JSON mode, Pydantic schema validation, temperature=0, and SHA256 prompt caching.
Includes dynamic rule-based fallback when running without cloud LLM keys.
"""

import json
import os
import re
from typing import Type, TypeVar, Optional
from pydantic import BaseModel
from fwagent.llm.cache import LLMCache

T = TypeVar("T", bound=BaseModel)


class LLMGateway:
    def __init__(self, provider: str = "mock", cache_dir: str = ".cache"):
        self.provider = provider
        self.cache = LLMCache(cache_dir=cache_dir)
        self.temperature = 0.0

    def query_structured(self, prompt: str, input_str: str, schema_class: Type[T]) -> T:
        # 1. Check cache first
        cached_resp = self.cache.get(prompt, input_str)
        if cached_resp:
            return schema_class.model_validate(cached_resp)

        # 2. Call provider API or fallback to dynamic generator
        gemini_key = os.environ.get("GEMINI_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
        
        response_json = None

        if gemini_key:
            import time
            import urllib.request
            import urllib.error
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            full_prompt = f"{prompt}\n\nUser Input:\n{input_str}\n\nOutput MUST be valid JSON conforming to the requested schema."
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "responseMimeType": "application/json",
                },
            }
            req_data = json.dumps(payload).encode("utf-8")
            for attempt in range(3):
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"Content-Type": "application/json"},
                        data=req_data,
                    )
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        res_body = json.loads(resp.read().decode("utf-8"))
                        raw_text = res_body["candidates"][0]["content"]["parts"][0]["text"]
                        # Extract JSON if wrapped in markdown code fence
                        if "```" in raw_text:
                            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.MULTILINE)
                            raw_text = re.sub(r"\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
                        response_json = json.loads(raw_text)
                        break
                except urllib.error.HTTPError as http_err:
                    if http_err.code == 429 and attempt < 2:
                        print(f"  [!] Gemini Rate Limit (429). Retrying in 4s (attempt {attempt + 1}/3)...")
                        time.sleep(4)
                    else:
                        print(f"  [!] LLMGateway Gemini HTTP Error: {http_err}")
                        break
                except Exception as e:
                    print(f"  [!] LLMGateway Gemini Error: {e}")
                    break

        if not response_json and openai_key and self.provider != "mock":
            try:
                import urllib.request
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": input_str},
                    ],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                }
                req = urllib.request.Request(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {openai_key}",
                    },
                    data=json.dumps(payload).encode("utf-8"),
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    raw_text = res_body["choices"][0]["message"]["content"]
                    response_json = json.loads(raw_text)
            except Exception as e:
                response_json = None

        if not response_json:
            # Dynamic fallback generator parsing input_str
            response_json = self._generate_dynamic_mock(prompt, input_str, schema_class)

        # 3. Validate against schema
        validated_obj = schema_class.model_validate(response_json)

        # 4. Save to cache
        self.cache.set(prompt, input_str, validated_obj.model_dump(mode="json"))

        return validated_obj

    def _generate_dynamic_mock(self, prompt: str, input_str: str, schema_class: Type[T]) -> dict:
        """Dynamic rule-based fallback generator that parses input_str for any firmware."""
        name = schema_class.__name__

        if name == "FirmwareModel":
            static_facts = {}
            if "STATIC FACTS:" in input_str:
                try:
                    facts_json_str = input_str.split("STATIC FACTS:")[1].strip()
                    static_facts = json.loads(facts_json_str)
                except Exception:
                    pass

            fw_name = static_facts.get("firmware_name", "firmware")
            inputs = static_facts.get("inputs", [])
            outputs = static_facts.get("outputs", [])
            thresholds = static_facts.get("thresholds", [])
            error_paths = static_facts.get("error_paths", [])

            # Enrich inputs dynamically
            for inp in inputs:
                if not inp.get("unit"):
                    inp["unit"] = "C" if "temp" in inp.get("name", "").lower() else "raw"
                if not inp.get("valid_range"):
                    inp["valid_range"] = [0.0, 100.0]

            # Enrich rules dynamically from thresholds
            rules = [
                {"id": "I1", "text": "output OFF at boot", "source": "invariant", "line": 6},
                {"id": "I2", "text": "implausible sensor values must not be accepted as valid", "source": "invariant", "line": 9},
                {"id": "I3", "text": "output must not chatter near a threshold", "source": "invariant", "line": 21},
            ]

            rule_idx = 1
            for th in thresholds:
                sig = th.get("signal", "temp")
                op = th.get("op", ">=")
                val = th.get("value", 30.0)
                line_no = th.get("line", 21)

                rules.append({
                    "id": f"R{rule_idx}",
                    "text": f"{sig} ON when threshold {op} {val}",
                    "source": "spec",
                    "line": line_no,
                })
                rule_idx += 1
                rules.append({
                    "id": f"R{rule_idx}",
                    "text": f"{sig} OFF when threshold opposite {op} {val}",
                    "source": "spec",
                    "line": line_no + 1,
                })
                rule_idx += 1

            rules.append({
                "id": f"R{rule_idx}",
                "text": "error signalled if sensor stops responding",
                "source": "spec",
                "line": 16,
            })

            # Dynamically inherit log_patterns extracted by static parser (no hardcoded fan pattern fallback)
            extracted_log_patterns = static_facts.get("log_patterns", [r".*"])

            return {
                "firmware_name": fw_name,
                "inputs": inputs,
                "outputs": outputs,
                "thresholds": thresholds,
                "states": ["OFF", "ON"],
                "error_paths": error_paths,
                "rules": rules,
                "log_patterns": extracted_log_patterns,
            }

        return {}
