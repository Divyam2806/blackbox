"""
Test Case Deduplication Engine.
Removes duplicate or structurally identical test cases based on categories, rationale, and step sequences.
"""

from typing import List, Set
from fwagent.models import TestCase


class Deduplicator:
    def __init__(self):
        pass

    def deduplicate(self, test_cases: List[TestCase]) -> List[TestCase]:
        unique_cases: List[TestCase] = []
        seen_signatures: Set[str] = set()

        for tc in test_cases:
            # Create a signature based on category, title, and key steps
            step_summary = tuple(
                (s.action, s.target, s.value) for s in tc.steps if s.action != "wait"
            )
            expect_summary = tuple((e.kind, e.target, e.value) for e in tc.expects)
            signature = f"{tc.category}:{step_summary}:{expect_summary}"

            if signature not in seen_signatures:
                seen_signatures.add(signature)
                unique_cases.append(tc)

        # Re-index test IDs neatly (T01, T02, ...)
        for idx, tc in enumerate(unique_cases, start=1):
            tc.id = f"T{idx:02d}"

        return unique_cases
