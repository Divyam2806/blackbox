import os
import re
import subprocess
import tempfile
from typing import List, Tuple, Dict, Any, Union
from fwagent.simulator.base import Simulator
from fwagent.models import TestCase
from fwagent.scenario_compiler import ScenarioCompiler


class WokwiCLISimulator(Simulator):
    """
    Wokwi CLI Hardware Simulator Driver.
    Executes real target MCU binaries inside Wokwi CLI headlessly using scenario YAML automation.
    """

    def __init__(self, firmware_dir: str, timeout_s: float = 10.0):
        self.firmware_dir = os.path.abspath(firmware_dir)
        self.timeout_s = timeout_s
        self.compiler = ScenarioCompiler()
        self.wokwi_cli_path = os.path.expanduser(r"~\.wokwi\bin\wokwi-cli.exe")
        self.token = os.environ.get("WOKWI_CLI_TOKEN", "")

    def reset(self) -> None:
        pass

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        pass

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0) -> None:
        pass

    def clear_fault(self, signal: str) -> None:
        pass

    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        return []

    def read_pin(self, pin: str) -> int:
        return 0

    def read_serial(self) -> List[Tuple[int, str]]:
        return []

    def run_test_case(self, test_case: TestCase) -> Dict[str, Any]:
        """
        Run a single TestCase via Wokwi CLI scenario execution.
        Returns simulation output dictionary containing serial_logs and pin_events.
        """
        yaml_content = self.compiler.compile_to_wokwi_yaml(test_case)
        scenario_path = os.path.join(self.firmware_dir, "scenario.yaml")

        with open(scenario_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        env = os.environ.copy()
        env["WOKWI_CLI_TOKEN"] = self.token

        cmd = [
            self.wokwi_cli_path,
            "--scenario", "scenario.yaml",
            self.firmware_dir
        ]

        serial_logs: List[Tuple[int, str]] = []
        raw_stdout = ""
        exit_code = -1

        try:
            res = subprocess.run(
                cmd,
                cwd=self.firmware_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_s
            )
            raw_stdout = res.stdout + "\n" + res.stderr
            exit_code = res.returncode
        except subprocess.TimeoutExpired as e:
            raw_stdout = (e.stdout or "") + "\nTimeout expired"
            exit_code = 124
        except Exception as e:
            raw_stdout = str(e)
            exit_code = 1

        # Parse serial lines matching T=... FAN=...
        t_ms = 0
        for line in raw_stdout.splitlines():
            line_str = line.strip()
            if "T=" in line_str or "FAN=" in line_str or "ERR" in line_str:
                serial_logs.append((t_ms, line_str))
                t_ms += 100

        return {
            "serial_logs": serial_logs,
            "raw_output": raw_stdout,
            "exit_code": exit_code
        }
