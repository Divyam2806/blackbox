"""
CLI Interface for BlackBox FW-Agent.
Usage:
    python -m fwagent.cli run <firmware_dir> [--spec spec.md]
"""

import argparse
import sys
import os

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
    run_parser.add_argument("--sim", type=str, default="host", choices=["host", "wokwi", "fake"], help="Simulator adapter")

    args = parser.parse_args()

    if args.command == "run":
        config = RunConfig(
            firmware_dir=args.firmware_dir,
            spec_file=args.spec,
            simulator=args.sim,
            out_dir=args.out,
        )
        orchestrator = Orchestrator(config=config)
        result = orchestrator.run(args.firmware_dir, spec_file=args.spec, out_dir=args.out)
        sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
