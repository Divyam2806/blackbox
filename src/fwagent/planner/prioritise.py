"""
Test Plan Prioritisation & Serialization Engine.
Orders test cases by safety/rule criticality and writes validated test_plan.json.
"""

import json
from typing import List
from pydantic import TypeAdapter
from fwagent.models import TestCase, FirmwareModel


class Prioritiser:
    def __init__(self):
        pass

    def prioritise(self, test_cases: List[TestCase]) -> List[TestCase]:
        # Sort by priority ascending (1 = highest priority), then category
        category_order = {
            "boundary": 1,
            "fault": 1,
            "state": 2,
            "normal": 2,
            "combo": 2,
            "timing": 2,
            "abnormal": 2,
            "comm": 2,
            "soak": 3,
            "adaptive": 3,
        }

        def sort_key(tc: TestCase):
            cat_score = category_order.get(tc.category, 2)
            return (tc.priority, cat_score, tc.id)

        sorted_cases = sorted(test_cases, key=sort_key)

        # Re-assign clean IDs
        for idx, tc in enumerate(sorted_cases, start=1):
            tc.id = f"T{idx:02d}"

        return sorted_cases

    def save_test_plan(self, test_cases: List[TestCase], filepath: str):
        # Validate list of TestCases using Pydantic TypeAdapter
        adapter = TypeAdapter(List[TestCase])
        json_data = adapter.dump_python(test_cases, mode="json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        return filepath
