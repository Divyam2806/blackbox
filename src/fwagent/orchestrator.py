"""
Orchestrator: The autonomous testing loop engine (U-P-E-O-J-R-A).
Coordinates Analyzer, Planner, and run artifact generation.
"""

import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from fwagent.models import FirmwareModel, TestCase, RunConfig
from fwagent.analyzer.llm_analyzer import LLMAnalyzer
from fwagent.planner.planner import Planner
from fwagent.planner.prioritise import Prioritiser


class Orchestrator:
    def __init__(self, config: Optional[RunConfig] = None):
        self.config = config or RunConfig(firmware_dir="firmware_samples/cooling_fan_buggy")
        self.analyzer = LLMAnalyzer()
        self.planner = Planner()
        self.prioritiser = Prioritiser()

    def run(self, firmware_dir: str, spec_file: Optional[str] = None, out_dir: Optional[str] = None) -> Dict[str, Any]:
        print(f"\n==================================================================")
        print(f" BLACKBOX FW-AGENT: Autonomous Embedded Firmware Test Engine")
        print(f" Target Firmware: {firmware_dir}")
        print(f"==================================================================\n")

        # 1. STAGE 1: UNDERSTAND
        print("[STAGE 1/2: UNDERSTAND] Parsing firmware and building Firmware Model...")
        model: FirmwareModel = self.analyzer.analyze(firmware_dir, spec_file)
        
        print(f"  [+] Input Signals:  {[s.name + ' (' + s.pin + ')' for s in model.inputs]}")
        print(f"  [+] Output Signals: {[s.name + ' (' + s.pin + ')' for s in model.outputs]}")
        print(f"  [+] Thresholds:     {[f'{t.signal} {t.op} {t.value}' for t in model.thresholds]}")
        print(f"  [+] Error Paths:    {len(model.error_paths)} detected (ERR_LED driven={model.outputs[1].driven if len(model.outputs)>1 else False})")
        print(f"  [+] Invariants:     {len(model.rules)} active rules")

        # 2. STAGE 2: PLAN
        print("\n[STAGE 2/2: PLAN] Generating deterministic BVA, fault, dynamics, and state tests...")
        test_plan: list[TestCase] = self.planner.make_plan(model)
        
        print(f"  [+] Generated {len(test_plan)} validated Test Cases across categories.")

        # 3. Create Run Directory & Save Artifacts
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        fw_name = os.path.basename(os.path.normpath(firmware_dir))
        if not out_dir:
            out_dir = os.path.join("runs", f"{timestamp}_{fw_name}")
        
        os.makedirs(out_dir, exist_ok=True)

        model_file = os.path.join(out_dir, "firmware_model.json")
        plan_file = os.path.join(out_dir, "test_plan.json")

        with open(model_file, "w", encoding="utf-8") as f:
            f.write(model.model_dump_json(indent=2))

        self.prioritiser.save_test_plan(test_plan, plan_file)

        print(f"\n[+] Artifacts written successfully:")
        print(f"    - Firmware Model: {model_file}")
        print(f"    - Test Plan:      {plan_file}")

        # Print Test Plan Table
        self._print_plan_table(test_plan)

        return {
            "out_dir": out_dir,
            "firmware_model": model,
            "test_plan": test_plan,
            "model_file": model_file,
            "plan_file": plan_file,
        }

    def _print_plan_table(self, test_plan: list[TestCase]):
        print("\n" + "=" * 90)
        print(f"{'ID':<6} | {'Category':<10} | {'Priority':<8} | {'Title':<45} | {'Rules'}")
        print("-" * 90)
        for tc in test_plan:
            rule_ids = ", ".join(e.rule_id for e in tc.expects if e.rule_id)
            print(f"{tc.id:<6} | {tc.category:<10} | {tc.priority:<8} | {tc.title[:45]:<45} | {rule_ids}")
        print("=" * 90 + "\n")
