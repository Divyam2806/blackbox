import time
from typing import List, Dict, Any, Optional
from fwagent.models import Verdict


class ExecutionBudget:
    """
    Manages multi-round execution budgets and stop criteria.
    Enforces max_rounds, max_total_tests, wall-clock timeout, and 'no new information' rule.
    """

    def __init__(self, max_rounds: int = 3, max_tests: int = 50, timeout_s: float = 60.0):
        self.max_rounds = max_rounds
        self.max_tests = max_tests
        self.timeout_s = timeout_s
        self.start_time = time.time()
        self.current_round = 0
        self.total_tests_run = 0
        self.previous_failed_ids: set[str] = set()

    def should_continue(self, round_verdicts: List[Verdict]) -> bool:
        """
        Check if orchestrator should run another adaptive round.
        Returns False if max_rounds reached, time budget exhausted, max_tests exceeded,
        or no new information gained in this round.
        """
        self.current_round += 1
        self.total_tests_run += len(round_verdicts)

        # Stop rule 1: Max rounds reached
        if self.current_round >= self.max_rounds:
            return False

        # Stop rule 2: Max total tests reached
        if self.total_tests_run >= self.max_tests:
            return False

        # Stop rule 3: Time budget exhausted
        if (time.time() - self.start_time) >= self.timeout_s:
            return False

        # Stop rule 4: No new information (same set of failures as previous round)
        current_failed_ids = {v.test_id for v in round_verdicts if v.status in ["FAIL", "WARN"]}
        if self.current_round > 1 and current_failed_ids == self.previous_failed_ids:
            return False

        self.previous_failed_ids = current_failed_ids
        return True
