"""
Orchestrator: Multi-Round Autonomous Testing Loop Engine (U-P-E-O-J-R-A).
Coordinates Analyzer, Planner, Executor, Simulator, Evaluator, Explainer, Reporter, and Adaptive Feedback.
"""

import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from fwagent.models import FirmwareModel, TestCase, Verdict, Finding, RunConfig
from fwagent.analyzer.llm_analyzer import LLMAnalyzer
from fwagent.analyzer.static_parser import StaticParser
from fwagent.analyzer.behavior_builder import BehaviorGraphBuilder
from fwagent.planner.planner import Planner
from fwagent.planner.prioritise import Prioritiser
from fwagent.planner.adaptive import AdaptivePlanner
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.executor import Executor
from fwagent.evaluator.oracle import OracleEvaluator
from fwagent.explainer.root_cause import RootCauseExplainer
from fwagent.explainer.gemini_explainer import GeminiExplainer
from fwagent.reporter.html_reporter import HTMLReporter
from fwagent.utils.budget import ExecutionBudget
from fwagent.regression.manager import RegressionManager


from fwagent.simulator.wokwi_adapter import WokwiAdapter


class Orchestrator:
    """
    Multi-Round Autonomous Embedded Firmware Test Engine.
    """

    def __init__(self, config: Optional[RunConfig] = None):
        self.config = config or RunConfig(firmware_dir="firmware_samples/cooling_fan_buggy")
        self.static_parser = StaticParser()
        self.analyzer = LLMAnalyzer()
        self.planner = Planner()
        self.prioritiser = Prioritiser()
        self.adaptive_planner = AdaptivePlanner()
        if getattr(self.config, "simulator", "host") == "wokwi":
            self.simulator = WokwiAdapter(self.config.firmware_dir)
        else:
            self.simulator = HostHALSimulator()
        self.executor = Executor(self.simulator)
        self.explainer = RootCauseExplainer()
        self.gemini_explainer = GeminiExplainer()
        self.reporter = HTMLReporter()


    def run(self, firmware_dir: str, spec_file: Optional[str] = None, out_dir: Optional[str] = None) -> Dict[str, Any]:
        if self.config.simulator == "wokwi":
            self.simulator = WokwiAdapter(firmware_dir)
            self.executor = Executor(self.simulator)

        print(f"\n==================================================================")
        print(f" BLACKBOX FW-AGENT: Autonomous Embedded Firmware Test Engine")
        print(f" Target Firmware: {firmware_dir}")
        print(f"==================================================================\n")

        # 1. STAGE 1: UNDERSTAND (Option A: Pure Static Parser Pass - 0 API Calls)
        print("[STAGE 1/6: UNDERSTAND (STATIC ONLY)] Parsing firmware using StaticParser...")
        model, line_index = self.static_parser.parse_directory(firmware_dir)
        behavior_graph = BehaviorGraphBuilder().build(model)

        # Reconfigure simulator and executor with the extracted model
        self.simulator = HostHALSimulator(model=model)
        self.simulator.set_firmware_type("good" if "good" in firmware_dir.lower() else "buggy")
        self.executor = Executor(self.simulator, model=model)

        print(f"  [+] Input Signals:  {[s.name + ' (' + str(s.pin or 'var') + ')' for s in model.inputs]}")
        print(f"  [+] Output Signals: {[s.name + ' (' + str(s.pin or 'var') + ')' for s in model.outputs]}")
        print(f"  [+] Thresholds:     {[f'{t.signal} {t.op} {t.value}' for t in model.thresholds]}")
        print(f"  [+] Invariants:     {len(model.rules)} active rules")

        # 2. STAGE 2: PLAN (Option A: Gemini API Creative Test Case Generator - API Call #1)
        print("\n[STAGE 2/6: PLAN] Generating Test Cases using Gemini API & Deterministic Generators...")
        test_plan: List[TestCase] = self.planner.make_plan(model)
        print(f"  [+] Generated {len(test_plan)} initial Test Cases across categories.")

        # Output Directory setup
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        fw_name = os.path.basename(os.path.normpath(firmware_dir))
        if not out_dir:
            out_dir = os.path.join("runs", f"{timestamp}_{fw_name}")
        os.makedirs(out_dir, exist_ok=True)

        oracle = OracleEvaluator(model)
        budget = ExecutionBudget(max_rounds=2, max_tests=50, timeout_s=60.0)

        all_verdicts: List[Verdict] = []
        all_logs: List[Any] = []
        current_tests = list(test_plan)
        round_no = 1

        # 3. MULTI-ROUND LOOP (Execute -> Observe -> Judge -> Adapt)
        while True:
            print(f"\n[ROUND {round_no}] Executing {len(current_tests)} tests on Host-HAL Simulator...")
            round_verdicts: List[Verdict] = []

            for tc in current_tests:
                sim_output = self.executor.run_test(tc)
                verdict = oracle.judge(tc, sim_output)
                round_verdicts.append(verdict)
                all_logs.extend(sim_output.get("serial_logs", []))

            all_verdicts.extend(round_verdicts)
            fail_cnt = sum(1 for v in round_verdicts if v.status == "FAIL")
            warn_cnt = sum(1 for v in round_verdicts if v.status == "WARN")
            pass_cnt = sum(1 for v in round_verdicts if v.status == "PASS")
            print(f"  [+] Round {round_no} Scoreboard: PASS={pass_cnt} | FAIL={fail_cnt} | WARN={warn_cnt}")

            # STAGE 5: ADAPT (Check stop rules & generate follow-up tests)
            if not budget.should_continue(round_verdicts):
                print(f"  [+] Adaptive stop rule triggered: Maximum rounds reached or no new information gained. Stopping loop.")
                break

            follow_up_tests = self.planner.adapt(model, round_verdicts)
            if not follow_up_tests:
                follow_up_tests = self.adaptive_planner.generate_adaptive_tests(model, round_verdicts)

            if not follow_up_tests:
                print(f"  [+] No adaptive follow-ups required. Stopping loop.")
                break

            print(f"\n[STAGE 5/6: ADAPT] Round {round_no} generated {len(follow_up_tests)} adaptive follow-up tests.")
            current_tests = follow_up_tests
            round_no += 1

        # Compute trusted ADC window
        trusted_adc_window = self.adaptive_planner.compute_trusted_adc_window(all_verdicts)
        print(f"\n[+] Trusted Sensor ADC Count Window: {trusted_adc_window}")

        # 4. STAGE 6: REPORT & EXPLAIN
        print("\n[STAGE 6/6: EXPLAIN & REPORT] Mapping findings to source lines and building HTML report...")
        findings: List[Finding] = []

        # Read spec and source code if available for Gemini API explainer context
        spec_content = ""
        fw_code_content = ""
        spec_path = os.path.join(firmware_dir, "spec.md")
        if os.path.exists(spec_path):
            try:
                with open(spec_path, "r", encoding="utf-8") as f:
                    spec_content = f.read()
            except Exception:
                pass

        src_dir = os.path.join(firmware_dir, "src")
        if os.path.exists(src_dir):
            ino_files = [os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith((".ino", ".cpp", ".c"))]
            if ino_files:
                try:
                    with open(ino_files[0], "r", encoding="utf-8") as f:
                        fw_code_content = f.read()
                except Exception:
                    pass

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
        if api_key:
            print("  [+] Querying Gemini API for AI Root Cause & C++ Code Fix Generation...")
            gemini_findings = self.gemini_explainer.analyze_findings(all_verdicts, model, spec_text=spec_content, firmware_code=fw_code_content)
            if gemini_findings:
                findings = gemini_findings
                print(f"  [+] Gemini API returned {len(findings)} domain-specific findings!")

        if not findings:
            print("  [+] Running Dynamic Deterministic Root Cause Explainer...")
            findings = self.explainer.analyze_findings(all_verdicts, model, behavior_graph, line_index)

        report_file = self.reporter.generate_report(fw_name, all_verdicts, findings, all_logs, out_dir, model=model, test_plan=test_plan)

        model_file = os.path.join(out_dir, "firmware_model.json")
        plan_file = os.path.join(out_dir, "test_plan.json")
        results_file = os.path.join(out_dir, "results.json")
        findings_file = os.path.join(out_dir, "findings.json")

        with open(model_file, "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2))

        self.prioritiser.save_test_plan(test_plan, plan_file)

        with open(results_file, "w", encoding="utf-8") as f:
            json.dump([v.model_dump() for v in all_verdicts], f, indent=2)

        with open(findings_file, "w", encoding="utf-8") as f:
            json.dump([fi.model_dump() for fi in findings], f, indent=2)

        # Regression check: compare against previous run
        prev_findings_path = os.path.join("runs", "last_findings.json")
        regression_report = RegressionManager().compare(findings, prev_findings_path)
        RegressionManager().print_summary(regression_report)

        # Save current findings as last_findings.json for the next run comparison
        try:
            import shutil
            shutil.copyfile(findings_file, prev_findings_path)
        except Exception:
            pass


        print(f"\n[+] Artifacts generated successfully:")
        print(f"    - Firmware Model:    {model_file}")
        print(f"    - Test Plan:         {plan_file}")
        print(f"    - Execution Results: {results_file}")
        print(f"    - Findings:          {findings_file}")
        print(f"    - HTML Report:       {report_file}")

        self._print_results_table(all_verdicts)
        self._print_findings_summary(findings, trusted_adc_window)

        return {
            "out_dir": out_dir,
            "firmware_model": model,
            "test_plan": test_plan,
            "verdicts": all_verdicts,
            "findings": findings,
            "trusted_adc_window": trusted_adc_window,
            "report_file": report_file,
            "results_file": results_file,
            "findings_file": findings_file
        }

    def _print_results_table(self, verdicts: List[Verdict]):
        print("\n" + "=" * 90)
        print(f"{'ID':<18} | {'Status':<10} | {'Expected':<30} | {'Observed':<25}")
        print("-" * 90)
        for v in verdicts:
            exp_str = v.expected[:30] if v.expected else ""
            obs_str = v.observed[:25] if v.observed else ""
            print(f"{v.test_id:<18} | {v.status:<10} | {exp_str:<30} | {obs_str:<25}")
        print("=" * 90 + "\n")

    def _print_findings_summary(self, findings: List[Finding], trusted_window: str):
        print("==========================================================================================")
        print(f" HIGH-PRIORITY FINDINGS & LINE-MAPPED ROOT CAUSES (Trusted ADC Window: {trusted_window})")
        print("==========================================================================================")
        for f in findings:
            lines_str = ", ".join(str(l) for l in f.firmware_lines)
            tests_str = ", ".join(f.evidence_tests)
            print(f" [{f.id}] Severity: {f.severity:<6} | Title: {f.title}")
            print(f"      Evidence Tests: {tests_str}")
            print(f"      Likely Cause:   {f.likely_cause}")
            print(f"      Firmware Lines: {lines_str}")
            print(f"      Suggested Fix:\n{f.suggested_fix}\n")
        print("==========================================================================================\n")

