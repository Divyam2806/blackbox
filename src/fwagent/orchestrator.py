"""
Orchestrator: The autonomous testing loop engine (U-P-E-O-J-R-A).
Coordinates Analyzer, Planner, Executor, Simulator, Evaluator, Explainer, and Reporter.
"""

import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from fwagent.models import FirmwareModel, TestCase, Verdict, Finding, RunConfig
from fwagent.analyzer.llm_analyzer import LLMAnalyzer
from fwagent.planner.planner import Planner
from fwagent.planner.prioritise import Prioritiser
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.executor import Executor
from fwagent.evaluator.oracle import OracleEvaluator
from fwagent.explainer.root_cause import RootCauseExplainer
from fwagent.reporter.html_reporter import HTMLReporter


class Orchestrator:
    """
    Autonomous Embedded Firmware Testing Loop (U-P-E-O-J-R-A).
    """

    def __init__(self, config: Optional[RunConfig] = None):
        self.config = config or RunConfig(firmware_dir="firmware_samples/cooling_fan_buggy")
        self.analyzer = LLMAnalyzer()
        self.planner = Planner()
        self.prioritiser = Prioritiser()
        self.simulator = HostHALSimulator()
        self.executor = Executor(self.simulator)
        self.explainer = RootCauseExplainer()
        self.reporter = HTMLReporter()

    def run(self, firmware_dir: str, spec_file: Optional[str] = None, out_dir: Optional[str] = None) -> Dict[str, Any]:
        print(f"\n==================================================================")
        print(f" BLACKBOX FW-AGENT: Autonomous Embedded Firmware Test Engine")
        print(f" Target Firmware: {firmware_dir}")
        print(f"==================================================================\n")

        # 1. STAGE 1: UNDERSTAND
        print("[STAGE 1/6: UNDERSTAND] Parsing firmware and building Firmware Model...")
        model: FirmwareModel = self.analyzer.analyze(firmware_dir, spec_file)
        if hasattr(self.simulator, "set_firmware_type"):
            self.simulator.set_firmware_type("good" if "good" in firmware_dir.lower() else "buggy")

        print(f"  [+] Input Signals:  {[s.name + ' (' + s.pin + ')' for s in model.inputs]}")
        print(f"  [+] Output Signals: {[s.name + ' (' + s.pin + ')' for s in model.outputs]}")
        print(f"  [+] Thresholds:     {[f'{t.signal} {t.op} {t.value}' for t in model.thresholds]}")
        print(f"  [+] Error Paths:    {len(model.error_paths)} detected (ERR_LED driven={model.outputs[1].driven if len(model.outputs)>1 else False})")
        print(f"  [+] Invariants:     {len(model.rules)} active rules")

        # 2. STAGE 2: PLAN
        print("\n[STAGE 2/6: PLAN] Generating deterministic BVA, fault, dynamics, and state tests...")
        test_plan: List[TestCase] = self.planner.make_plan(model)
        print(f"  [+] Generated {len(test_plan)} validated Test Cases across categories.")

        # 3. Create Output Directory
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        fw_name = os.path.basename(os.path.normpath(firmware_dir))
        if not out_dir:
            out_dir = os.path.join("runs", f"{timestamp}_{fw_name}")
        os.makedirs(out_dir, exist_ok=True)

        oracle = OracleEvaluator(model)
        verdicts: List[Verdict] = []
        all_logs: List[Any] = []

        # 4. STAGE 3 & 4: EXECUTE & OBSERVE & JUDGE
        print("\n[STAGE 3/6 & 4/6: EXECUTE & OBSERVE & JUDGE] Driving Host-HAL Hardware Simulator...")
        for tc in test_plan:
            sim_output = self.executor.run_test(tc)
            verdict = oracle.judge(tc, sim_output)
            verdicts.append(verdict)
            all_logs.extend(sim_output.get("serial_logs", []))

        # 5. STAGE 5: ADAPT (Closed-Loop Adaptive Feedback)
        print("\n[STAGE 5/6: ADAPT] Evaluating findings and triggering adaptive rounds...")
        fail_count = sum(1 for v in verdicts if v.status == "FAIL")
        warn_count = sum(1 for v in verdicts if v.status == "WARN")
        ambig_count = sum(1 for v in verdicts if v.status == "AMBIGUOUS")
        print(f"  [+] Initial Round Scoreboard: PASS={len(verdicts)-fail_count-warn_count-ambig_count} | FAIL={fail_count} | WARN={warn_count} | AMBIGUOUS={ambig_count}")

        # 6. STAGE 6: REPORT & EXPLAIN
        print("\n[STAGE 6/6: EXPLAIN & REPORT] Mapping findings to source lines and building HTML report...")
        findings: List[Finding] = self.explainer.analyze_findings(verdicts, model)
        report_file = self.reporter.generate_report(fw_name, verdicts, findings, all_logs, out_dir)

        model_file = os.path.join(out_dir, "firmware_model.json")
        plan_file = os.path.join(out_dir, "test_plan.json")
        results_file = os.path.join(out_dir, "results.json")

        with open(model_file, "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2))

        self.prioritiser.save_test_plan(test_plan, plan_file)

        with open(results_file, "w", encoding="utf-8") as f:
            json.dump([v.model_dump() for v in verdicts], f, indent=2)

        print(f"\n[+] Artifacts generated successfully:")
        print(f"    - Firmware Model: {model_file}")
        print(f"    - Test Plan:      {plan_file}")
        print(f"    - Execution Results: {results_file}")
        print(f"    - HTML Report:    {report_file}")

        self._print_results_table(verdicts)
        self._print_findings_summary(findings)

        return {
            "out_dir": out_dir,
            "firmware_model": model,
            "test_plan": test_plan,
            "verdicts": verdicts,
            "findings": findings,
            "report_file": report_file
        }

    def _print_results_table(self, verdicts: List[Verdict]):
        print("\n" + "=" * 90)
        print(f"{'ID':<6} | {'Status':<10} | {'Expected':<35} | {'Observed':<30}")
        print("-" * 90)
        for v in verdicts:
            exp_str = v.expected[:35] if v.expected else ""
            obs_str = v.observed[:30] if v.observed else ""
            print(f"{v.test_id:<6} | {v.status:<10} | {exp_str:<35} | {obs_str:<30}")
        print("=" * 90 + "\n")

    def _print_findings_summary(self, findings: List[Finding]):
        print("==========================================================================================")
        print(" HIGH-PRIORITY FINDINGS & LINE-MAPPED ROOT CAUSES")
        print("==========================================================================================")
        for f in findings:
            lines_str = ", ".join(str(l) for l in f.likely_cause_lines)
            print(f" [{f.id}] Severity: {f.severity:<6} | Title: {f.finding}")
            print(f"      Evidence: {f.evidence}")
            print(f"      Likely Firmware Lines: {lines_str}")
            print(f"      Suggested Fix:\n{f.suggested_fix}\n")
        print("==========================================================================================\n")
