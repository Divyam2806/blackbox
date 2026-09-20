"""
CLI Interface for BlackBox FW-Agent.
Usage:
    python -m fwagent.cli run <firmware_dir> [--spec spec.md] [--sim auto|host|wokwi|renode|gazebo|all]
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Add src directory to path if executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fwagent.orchestrator import Orchestrator
from fwagent.models import RunConfig


def main():
    parser = argparse.ArgumentParser(
        prog="fwagent",
        description="BlackBox FW-Agent: Autonomous AI Agent for Embedded Firmware Testing",
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    run_parser = subparsers.add_parser("run", help="Run autonomous analysis and test plan generation")
    run_parser.add_argument("firmware_dir", type=str, help="Path to firmware directory")
    run_parser.add_argument("--spec", type=str, default=None, help="Path to optional spec.md file")
    run_parser.add_argument("--out", type=str, default=None, help="Output directory for run artifacts")
    run_parser.add_argument("--sim", type=str, default="auto", choices=["auto", "host", "wokwi", "renode", "gazebo", "all"], help="Simulator adapter choice")

    args = parser.parse_args()

    if args.command == "run":
        config = RunConfig(
            firmware_dir=args.firmware_dir,
            spec_file=args.spec,
            simulator=args.sim,
            out_dir=args.out,
        )
        orchestrator = Orchestrator(config=config)

        # Tee sys.stdout to stdout.log in out_dir
        out_dir = args.out
        if not out_dir:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            fw_name = os.path.basename(os.path.normpath(args.firmware_dir))
            out_dir = os.path.join("runs", f"{timestamp}_{fw_name}")
        os.makedirs(out_dir, exist_ok=True)

        log_path = os.path.join(out_dir, "stdout.log")
        class TeeStdout:
            def __init__(self, term, log_f):
                self.term = term
                self.log_f = log_f
            def write(self, msg):
                self.term.write(msg)
                if not self.log_f.closed:
                    self.log_f.write(msg)
                    self.log_f.flush()
            def flush(self):
                self.term.flush()
                if not self.log_f.closed:
                    self.log_f.flush()

        log_f = open(log_path, "w", encoding="utf-8")
        sys.stdout = TeeStdout(sys.stdout, log_f)

        result = orchestrator.run(args.firmware_dir, spec_file=args.spec, out_dir=out_dir)
        log_f.close()
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
