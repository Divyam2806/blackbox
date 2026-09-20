import json
import os
import subprocess
from typing import List, Tuple, Dict, Any, Union
from fwagent.simulator.base import Simulator
from fwagent.simulator.host_hal import HostHALSimulator
from fwagent.simulator.wokwi_cli import WokwiCLISimulator
from fwagent.models import TestCase


class WokwiAdapter(Simulator):
    """
    Wokwi Hardware Simulator Adapter.
    Runs Wokwi CLI simulation with automatic fallback to Host-HAL if CLI fails or times out.
    """
    capabilities = {"real_mcu", "wokwi_parts", "arduino"}

    @classmethod
    def available(cls) -> Tuple[bool, str]:
        import shutil
        exe = shutil.which("wokwi-cli")
        if not exe:
            return False, "wokwi-cli executable not found"
        if not os.environ.get("WOKWI_CLI_TOKEN"):
            return False, "WOKWI_CLI_TOKEN environment variable not set"
        return True, "Wokwi CLI ready"

    def __init__(self, firmware_dir: str = "."):
        self.firmware_dir = firmware_dir
        self.wokwi_cli = WokwiCLISimulator(firmware_dir)
        self.fallback_sim = HostHALSimulator()

    def reset(self) -> None:
        self.fallback_sim.reset()

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        self.fallback_sim.set_input(signal, value)

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0) -> None:
        self.fallback_sim.inject_fault(signal, fault_type, duration_ms)

    def clear_fault(self, signal: str) -> None:
        self.fallback_sim.clear_fault(signal)

    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        return self.fallback_sim.run_for(duration_ms)

    def read_pin(self, pin: str) -> int:
        return self.fallback_sim.read_pin(pin)

    def read_serial(self) -> List[Tuple[int, str]]:
        return self.fallback_sim.read_serial()

    def run_test(self, test_case: TestCase) -> Dict[str, Any]:
        """
        Attempt to execute TestCase via Wokwi CLI.
        If Wokwi CLI fails, automatically fall back to Host-HAL.
        """
        try:
            cli_res = self.wokwi_cli.run_test_case(test_case)
            if cli_res.get("exit_code") == 0 and cli_res.get("serial_logs"):
                return cli_res
        except Exception as e:
            print(f"  [WARN] Wokwi CLI exception: {e}")

        # Fallback to Host-HAL execution
        print(f"  [INFO] Running {test_case.id} via Wokwi Adapter (Host-HAL SIL Engine)")
        from fwagent.executor import Executor
        executor = Executor(self.fallback_sim)
        return executor.run_test(test_case)

    def generate_wokwi_artifacts(self, out_dir: str) -> Dict[str, str]:
        """Generate diagram.json and wokwi.toml for visual inspection / Wokwi web simulator."""
        os.makedirs(out_dir, exist_ok=True)

        diagram = {
            "version": 1,
            "author": "FWAgent",
            "editor": "wokwi",
            "parts": [
                {"type": "wokwi-arduino-uno", "id": "uno", "top": 0, "left": 0},
                {"type": "wokwi-ntc-temperature-sensor", "id": "temp1", "top": -100, "left": 150},
                {"type": "wokwi-servo", "id": "fan1", "top": 100, "left": 200},
                {"type": "wokwi-led", "id": "err_led", "top": -50, "left": 250, "attrs": {"color": "red"}}
            ],
            "connections": [
                ["uno:A0", "temp1:OUT", "green", []],
                ["uno:9", "fan1:PWM", "blue", []],
                ["uno:13", "err_led:A", "red", []],
                ["uno:GND.1", "err_led:C", "black", []]
            ]
        }

        wokwi_toml = '[wokwi]\nversion = 1\nfirmware = "build/firmware.hex"\nelf = "build/firmware.hex"\n'

        diagram_path = os.path.join(out_dir, "diagram.json")
        toml_path = os.path.join(out_dir, "wokwi.toml")

        with open(diagram_path, "w", encoding="utf-8") as f:
            json.dump(diagram, f, indent=2)

        with open(toml_path, "w", encoding="utf-8") as f:
            f.write(wokwi_toml)

        return {"diagram": diagram_path, "wokwi_toml": toml_path}

