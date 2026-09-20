from typing import List, Dict, Any
from fwagent.models import FirmwareModel, Verdict, TestCase


class CoverageEvaluator:
    """
    Calculates Rule Coverage and Threshold-side Coverage percentages.
    """

    def calculate_coverage(self, model: FirmwareModel, test_plan: List[TestCase], verdicts: List[Verdict]) -> Dict[str, Any]:
        """
        Calculate rule coverage % and threshold-side boundary coverage %.
        """
        # 1. Rule Coverage
        total_rules = {r.id for r in model.rules} if model and model.rules else {"R1", "R2", "R3", "R4", "I1", "I2", "I3"}
        tested_rules = set()

        for v in verdicts:
            for rid in v.rule_ids:
                if rid in total_rules:
                    tested_rules.add(rid)

        for tc in test_plan:
            for exp in tc.expects:
                if exp.rule_id and exp.rule_id in total_rules:
                    tested_rules.add(exp.rule_id)

        rule_coverage_pct = round((len(tested_rules) / len(total_rules)) * 100.0, 1) if total_rules else 100.0

        # 2. Threshold-side Coverage (Lower side vs Upper side)
        # Check if test cases exercise inputs both below threshold (< 30.0 C) and above threshold (>= 30.0 C)
        has_lower_side = False
        has_upper_side = False

        for tc in test_plan:
            for step in tc.steps:
                if step.action == "set_input" and step.value is not None:
                    try:
                        val = float(step.value)
                        if val < 30.0:
                            has_lower_side = True
                        elif val >= 30.0:
                            has_upper_side = True
                    except (ValueError, TypeError):
                        pass

        threshold_sides_covered = (1 if has_lower_side else 0) + (1 if has_upper_side else 0)
        threshold_coverage_pct = round((threshold_sides_covered / 2.0) * 100.0, 1)

        return {
            "rule_coverage_pct": rule_coverage_pct,
            "tested_rules": sorted(list(tested_rules)),
            "total_rules": sorted(list(total_rules)),
            "threshold_coverage_pct": threshold_coverage_pct,
            "has_lower_side": has_lower_side,
            "has_upper_side": has_upper_side
        }
