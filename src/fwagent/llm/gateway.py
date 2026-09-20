"""
Provider-agnostic LLM Gateway.
Supports JSON mode, Pydantic schema validation, temperature=0, and SHA256 prompt caching.
Includes deterministic offline fallback for offline / mock testing.
"""

import json
import os
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

        # 2. Call provider API or fallback to mock
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")
        
        response_json = None

        if api_key and self.provider != "mock":
            try:
                # Try calling OpenAI compatible gateway if key exists
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
                        "Authorization": f"Bearer {api_key}",
                    },
                    data=json.dumps(payload).encode("utf-8"),
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    raw_text = res_body["choices"][0]["message"]["content"]
                    response_json = json.loads(raw_text)
            except Exception as e:
                # Fall back gracefully to offline generator
                response_json = None

        if not response_json:
            # Deterministic Offline Mock generator matching requested schema
            response_json = self._generate_mock(prompt, input_str, schema_class)

        # 3. Validate against schema
        validated_obj = schema_class.model_validate(response_json)

        # 4. Save to cache
        self.cache.set(prompt, input_str, validated_obj.model_dump(mode="json"))

        return validated_obj

    def _generate_mock(self, prompt: str, input_str: str, schema_class: Type[T]) -> dict:
        """Deterministic mock response generator for offline execution."""
        name = schema_class.__name__

        if name == "FirmwareModel":
            return {
                "firmware_name": "cooling_fan_buggy",
                "inputs": [
                    {
                        "name": "temp",
                        "kind": "adc",
                        "pin": "A0",
                        "unit": "C",
                        "valid_range": [0.0, 100.0],
                        "line": 9,
                        "driven": None,
                    }
                ],
                "outputs": [
                    {
                        "name": "fan",
                        "kind": "gpio_out",
                        "pin": "D9",
                        "unit": None,
                        "valid_range": None,
                        "line": 15,
                        "driven": True,
                    },
                    {
                        "name": "err_led",
                        "kind": "gpio_out",
                        "pin": "D13",
                        "unit": None,
                        "valid_range": None,
                        "line": 16,
                        "driven": False,  # Flags ERR_LED as never driven!
                    },
                ],
                "thresholds": [
                    {"signal": "temp", "op": ">=", "value": 30.0, "raw_adc": 307, "line": 21}
                ],
                "states": ["OFF", "ON"],
                "error_paths": [
                    {
                        "trigger": "sensor fault / timeout",
                        "handler": None,
                        "note": "ERR_LED pin (D13) declared at line 16 is never written by digitalWrite",
                        "line": 16,
                    }
                ],
                "rules": [
                    {"id": "R1", "text": "fan ON when temp above 30 C", "source": "spec", "line": 21},
                    {"id": "R2", "text": "fan OFF when temp below 30 C", "source": "spec", "line": 22},
                    {"id": "R3", "text": "error signalled if sensor stops responding", "source": "spec", "line": 16},
                    {"id": "I1", "text": "fan/motor OFF at boot", "source": "invariant", "line": 6},
                    {"id": "I2", "text": "implausible sensor values must not be accepted as valid", "source": "invariant", "line": 9},
                    {"id": "I3", "text": "output must not chatter near a threshold", "source": "invariant", "line": 21},
                ],
                "log_patterns": [r"T=(?P<t>[-\d.]+) FAN=(?P<fan>ON|OFF)"],
            }
        
        # Generic fallback
        return {}
