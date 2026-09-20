"""
LLM Prompt & Response Cache.
Hashes prompt + input to guarantee exact reproducible results across runs.
"""

import hashlib
import json
import os
from typing import Optional, Any


class LLMCache:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "llm_cache.json")
        self.cache: dict = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass

    def get_hash(self, prompt: str, input_str: str) -> str:
        combined = f"{prompt}:::{input_str}".encode("utf-8")
        return hashlib.sha256(combined).hexdigest()

    def get(self, prompt: str, input_str: str) -> Optional[dict]:
        key = self.get_hash(prompt, input_str)
        return self.cache.get(key)

    def set(self, prompt: str, input_str: str, response: dict):
        key = self.get_hash(prompt, input_str)
        self.cache[key] = response
        self._save_cache()
