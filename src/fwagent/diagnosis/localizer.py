"""
FailureLocalizer — Ranks firmware source code lines by suspicion score for failing test cases.
Cross-references Verdict failures with BehaviorGraph nodes and line index mapping.
"""

from dataclasses import dataclass
from typing import List, Optional
from fwagent.models import Verdict, FirmwareModel
from fwagent.analyzer.behavior import BehaviorGraph, NodeType
from fwagent.utils.lineindex import LineIndex


@dataclass
class SourceLocation:
    file: str
    line: int
    function: str
    code_snippet: str
    suspicion_score: float  # 0.0 - 1.0


class FailureLocalizer:
    def localize(
        self,
        verdict: Verdict,
        model: FirmwareModel,
        graph: BehaviorGraph,
        line_index: LineIndex
    ) -> List[SourceLocation]:
        """
        Return source lines sorted by suspicion score for a failing verdict.
        Calculates suspicion scores based on threshold conditions, failing rules,
        undriven outputs, and missing boundary validation.
        """
        locs: List[SourceLocation] = []
        failing_rules = set(verdict.rule_ids)

        # 1. Condition nodes
        for node in graph.get_condition_nodes():
            if node.source_line:
                score = 0.5
                # Match threshold against failing rules
                th_signal = node.metadata.get("signal", "")
                if any(r.startswith("TC") or "threshold" in r.lower() for r in failing_rules):
                    score += 0.3
                snippet = line_index.get_line(node.source_line) if node.source_line <= len(line_index.lines) else ""
                locs.append(
                    SourceLocation(
                        file=model.firmware_name,
                        line=node.source_line,
                        function="main_loop",
                        code_snippet=snippet,
                        suspicion_score=score
                    )
                )

        # 2. Undriven outputs / Error paths
        for err_path in model.error_paths:
            if err_path.line:
                snippet = line_index.get_line(err_path.line) if err_path.line <= len(line_index.lines) else ""
                locs.append(
                    SourceLocation(
                        file=model.firmware_name,
                        line=err_path.line,
                        function="init",
                        code_snippet=snippet,
                        suspicion_score=0.9
                    )
                )

        # 3. Inputs missing validation
        for sig in model.inputs:
            if sig.line:
                snippet = line_index.get_line(sig.line) if sig.line <= len(line_index.lines) else ""
                locs.append(
                    SourceLocation(
                        file=model.firmware_name,
                        line=sig.line,
                        function="main_loop",
                        code_snippet=snippet,
                        suspicion_score=0.4
                    )
                )

        # Deduplicate by line number and return highest suspicion first
        unique_locs = {}
        for loc in locs:
            if loc.line not in unique_locs or loc.suspicion_score > unique_locs[loc.line].suspicion_score:
                unique_locs[loc.line] = loc

        return sorted(unique_locs.values(), key=lambda l: l.suspicion_score, reverse=True)
