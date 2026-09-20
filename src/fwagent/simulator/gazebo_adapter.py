"""
Gazebo adapter: Host-HAL behavioural model + (optionally) a REAL `gz sim` server.

Honesty rules:
  * Gazebo does not run firmware. The firmware side is the Host-HAL model.
  * If gz is missing or the world file is absent, the adapter says so
    (`mode == "plant-model"`, `notice` set, backend_name says so). It never
    claims to be Gazebo when no gz process is running. Pass require_gazebo=True
    to raise BackendUnavailable instead of degrading.
  * Each gz CLI call is a subprocess (0.2-1 s). Use a coarse tick_ms.

UNTESTED against your Gazebo version: verify the service and topic commands
with `gz service -l`, `gz topic -l`, `gz msg -h` before relying on them.
"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from fwagent.simulator.base import Simulator, Obs
from fwagent.simulator.errors import BackendUnavailable
from fwagent.simulator.host_hal import HostHALSimulator


class GazeboSimulator(Simulator):
    capabilities = {"physics", "lockstep", "host_fw_model"}
    executes_real_firmware = False
    independent = False              # shares the Host-HAL model, so not independent
    backend_name = "gazebo (plant model only, gz not running)"

    def __init__(self, world_file: Optional[str] = None, tick_ms: int = 100, model=None,
                 world_name: Optional[str] = None, cmd_topic: Optional[str] = None,
                 pose_topic: Optional[str] = None, step_ms: float = 1.0,
                 motor_pin: str = "9", require_gazebo: bool = False,
                 log_dir: str = "logs/gazebo", startup_timeout_s: float = 30.0,
                 **host_kwargs: Any):
        self.world_file   = world_file or os.environ.get("FWAGENT_GZ_WORLD", "worlds/plant.sdf")
        self.tick_ms = max(1, int(tick_ms))
        self.world_name = world_name
        self.cmd_topic    = cmd_topic  or os.environ.get("FWAGENT_GZ_CMD_TOPIC")
        self.pose_topic   = pose_topic or os.environ.get("FWAGENT_GZ_POSE_TOPIC")
        self.step_ms = step_ms              # world max_step_size in ms (default 1)
        self.motor_pin    = os.environ.get("FWAGENT_GZ_MOTOR_PIN", motor_pin)
        self.require_gazebo = require_gazebo or os.environ.get("FWAGENT_GZ_REQUIRE") == "1"
        self.log_dir = Path(log_dir)
        self.startup_timeout_s = startup_timeout_s

        self.host_sim = HostHALSimulator(model=model, **host_kwargs)
        self.gz_proc: Optional[subprocess.Popen] = None
        self._log_fh = None
        self.mode = "plant-model"
        self.notice: Optional[str] = None
        self.notes: List[str] = []
        self._last_speed: Optional[float] = None
        self.physical_state = self._fresh_state()
        self.obs_history: List[Obs] = []

    def set_model(self, model) -> None:
        """Propagate model to internal Host-HAL SITL simulator."""
        if hasattr(self.host_sim, "set_model"):
            self.host_sim.set_model(model)

    @staticmethod
    def _fresh_state() -> Dict[str, float]:
        return {"robot_x": 0.0, "robot_speed": 0.0, "motor_pwm": 0.0}

    # ---- availability / lifecycle ---------------------------------------
    @classmethod
    def available(cls) -> Tuple[bool, str]:
        exe = shutil.which("gz")
        if not exe:
            return False, "gz CLI not found (Gazebo needs Linux or WSL2)"
        try:
            p = subprocess.run([exe, "sim", "--versions"], capture_output=True,
                               text=True, timeout=10, shell=(os.name == 'nt'))
            if p.returncode == 0:
                return True, f"Gazebo ready: {p.stdout.strip() or 'version unknown'}"
            return False, f"gz sim --versions failed: {(p.stderr or p.stdout).strip()[:200]}"
        except Exception as e:
            return False, f"Gazebo check error: {e}"

    def _degrade(self, why: str) -> None:
        if self.require_gazebo:
            raise BackendUnavailable(why)
        self.mode = "plant-model"
        self.backend_name = "gazebo (plant model only, gz not running)"
        self.notice = f"Gazebo not running: {why}. Using Python plant model on Host-HAL."

    @staticmethod
    def _gz(*args: str, timeout: float = 10.0) -> Tuple[int, str]:
        try:
            exe = shutil.which("gz") or "gz"
            p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, shell=(os.name == 'nt'))
            return p.returncode, (p.stdout + p.stderr)
        except Exception as e:
            return 1, str(e)

    @staticmethod
    def _parse_world_name(path: Path) -> str:
        m = re.search(r'<world\s+name\s*=\s*"([^"]+)"', path.read_text(errors="ignore"))
        return m.group(1) if m else "default"

    def start(self, artifact_path: Optional[str] = None) -> None:
        self.host_sim.start(artifact_path)
        ok, reason = self.available()
        world = Path(self.world_file)
        if not ok:
            return self._degrade(reason)
        if not world.exists():
            return self._degrade(f"world file not found: {world}")
        self.world_name = self.world_name or self._parse_world_name(world)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_fh = open(self.log_dir / "gz_server.log", "w")
        exe = shutil.which("gz") or "gz"
        self.gz_proc = subprocess.Popen([exe, "sim", "-s", "-r", "-v", "3", str(world)],
                                        stdout=self._log_fh, stderr=subprocess.STDOUT,
                                        shell=(os.name == 'nt'))
        deadline = time.time() + self.startup_timeout_s
        while time.time() < deadline:
            if self.gz_proc.poll() is not None:
                self.stop()
                return self._degrade(f"gz exited early (see {self.log_dir / 'gz_server.log'})")
            rc, out = self._gz("topic", "-l", timeout=5)
            if rc == 0 and "/clock" in out:
                self.mode = "gazebo"
                self.backend_name = "gazebo"
                return
            time.sleep(1.0)
        self.stop()
        self._degrade("timed out waiting for /clock")

    def stop(self) -> None:
        if self.gz_proc is not None:
            try:
                self.gz_proc.terminate()
                self.gz_proc.wait(timeout=5)
            except Exception:
                self.gz_proc.kill()
            self.gz_proc = None
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None
        self.host_sim.stop()

    # ---- inputs / faults (all handled by the Host-HAL fault layer) -------
    def reset(self) -> None:
        self.host_sim.reset()
        self.physical_state = self._fresh_state()
        self.obs_history.clear()
        self._last_speed = None

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        self.host_sim.set_input(signal, value)

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0, **kwargs) -> None:
        self.host_sim.inject_fault(signal, fault_type, duration_ms, **kwargs)

    def clear_fault(self, signal: str) -> None:
        self.host_sim.clear_fault(signal)

    # ---- gazebo helpers --------------------------------------------------
    def _step_gz(self, iterations: int) -> bool:
        rc, out = self._gz("service", "-s", f"/world/{self.world_name}/control",
                           "--reqtype", "gz.msgs.WorldControl", "--reptype", "gz.msgs.Boolean",
                           "--timeout", "3000", "--req", f"multi_step: {iterations}")
        if rc != 0:
            self.notes.append(f"world step failed: {out.strip()[:200]}")
        return rc == 0

    def _send_speed(self, speed: float) -> None:
        if not self.cmd_topic or speed == self._last_speed:
            return
        rc, out = self._gz("topic", "-t", self.cmd_topic, "-m", "gz.msgs.Twist",
                           "-p", f"linear: {{x: {speed}}}")
        if rc != 0:
            self.notes.append(f"cmd publish failed: {out.strip()[:200]}")
        self._last_speed = speed

    def _read_x(self) -> Optional[float]:
        if not self.pose_topic:
            return None
        rc, out = self._gz("topic", "-e", "-t", self.pose_topic, "-n", "1", timeout=10)
        m = re.search(r"\bx:\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", out) if rc == 0 else None
        return float(m.group(1)) if m else None

    # ---- run -------------------------------------------------------------
    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        serial: List[Tuple[int, str]] = []
        remaining = int(duration_ms)
        while remaining > 0:
            dt = min(self.tick_ms, remaining)
            remaining -= dt
            serial += self.host_sim.run_for(dt)
            pin = self.host_sim.read_pin(self.motor_pin)
            speed = 1.0 if pin > 0 else 0.0
            st = self.physical_state
            st["motor_pwm"], st["robot_speed"] = float(pin), speed
            if self.mode == "gazebo":
                self._send_speed(speed)
                time.sleep(dt / 1000.0)
                x = self._read_x()
                if x is not None:
                    st["robot_x"] = x
            else:
                st["robot_x"] += speed * dt / 1000.0
            t = self.host_sim.t_ms
            self.obs_history.append(Obs(t_ms=t, source="physical", signal="robot_x", value=st["robot_x"]))
            self.obs_history.append(Obs(t_ms=t, source="physical", signal="robot_speed", value=speed))
        return serial

    def read_pin(self, pin: str) -> int:
        return self.host_sim.read_pin(pin)

    def read_serial(self) -> List[Tuple[int, str]]:
        return self.host_sim.read_serial()

    def read_physical_observations(self) -> List[Obs]:
        return self.obs_history
