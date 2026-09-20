"""
RegressionManager — Cross-run bug tracking for blackbox FW-Agent.

Compares current run findings against the previous run's findings.json
and classifies each finding as NEW, REGRESSION (re-appeared), or FIXED.
"""

import hashlib
import json
from pathlib import Path
from typing import List, Dict, Tuple
from fwagent.models import Finding


class RegressionManager:
    """
    Diffs current findings against a previous findings.json.
    Uses a stable bug ID (SHA-256 of title + sorted firmware_lines) so
    findings are matched across runs even if their F-number changes.
    """

    def _bug_id(self, f: Finding) -> str:
        key = f.title.strip() + str(sorted(f.firmware_lines))
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def compare(
        self, current: List[Finding], prev_json_path: str
    ) -> List[dict]:
        """
        Diff current findings against the previous run's findings.json.

        Returns a list of dicts, each with:
            {
                "finding": Finding,
                "status":  "NEW" | "REGRESSION" | "FIXED",
                "bug_id":  str,
            }
        """
        prev: Dict[str, Finding] = {}
        prev_path = Path(prev_json_path)
        if prev_path.exists():
            try:
                raw = json.loads(prev_path.read_text(encoding="utf-8"))
                items = raw if isinstance(raw, list) else raw.get("findings", [])
                for item in items:
                    try:
                        f = Finding(**item)
                        prev[self._bug_id(f)] = f
                    except Exception:
                        pass
            except Exception:
                pass

        report = []
        curr_ids = set()
        for f in current:
            bid = self._bug_id(f)
            curr_ids.add(bid)
            status = "REGRESSION" if bid in prev else "NEW"
            report.append({"finding": f, "status": status, "bug_id": bid})

        for bid, f in prev.items():
            if bid not in curr_ids:
                report.append({"finding": f, "status": "FIXED", "bug_id": bid})

        return report

    def print_summary(self, report: List[dict]) -> None:
        """Print a human-readable regression diff to stdout."""
        if not report:
            print("  [+] Regression check: No previous findings to compare.")
            return

        new_cnt = sum(1 for r in report if r["status"] == "NEW")
        reg_cnt = sum(1 for r in report if r["status"] == "REGRESSION")
        fix_cnt = sum(1 for r in report if r["status"] == "FIXED")

        print(f"\n[REGRESSION CHECK] New={new_cnt}  Regressions={reg_cnt}  Fixed={fix_cnt}")
        labels = {"NEW": "[NEW]", "REGRESSION": "[REGRESSION]", "FIXED": "[FIXED]"}
        for r in report:
            label = labels.get(r["status"], r["status"])
            print(f"  {label}  [{r['bug_id']}] {r['finding'].title}")
