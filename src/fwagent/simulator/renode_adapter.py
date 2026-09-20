"""
Renode adapter: drives a REAL Renode process over its monitor socket, or, if
Renode/.resc/ELF is missing, degrades openly to the Host-HAL model.

The earlier version never launched Renode; every call went to Host-HAL while
reporting "renode". This version starts the emulator, runs virtual time with
`emulation RunFor`, and reads UART output from a file backend the .resc sets up.

Needs from your .resc / config (Renode cannot guess these):
  * `$bin` is used for the ELF path (`sysbus LoadELF $bin`) in the script.
  * uart_log: file the script writes UART to, e.g.
        sysbus.usart2 CreateFileBackend @logs/renode/uart.log true
  * adc_feed_cmd: how to inject a sample, e.g. "sysbus.adc1 FeedSample {volts} {channel} 1"
    (depends on the peripheral model; check its Renode docs). Without it,
    set_input raises NotImplementedError and tests end INCONCLUSIVE, never fake PASS.
UNTESTED against your Renode version: verify command syntax in the monitor first.
"""
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from fwagent.simulator.base import Simulator
from fwagent.simulator.errors import BackendUnavailable
from fwagent.simulator.fault_layer import SharedFaultLayer
from fwagent.simulator.host_hal import HostHALSimulator

_PROMPT = re.compile(rb"\([^()\r\n]*\)\s*$")


class RenodeSimulator(Simulator):
    capabilities = {"real_mcu", "elf_binary", "cortex_m", "riscv"}
    independent = True
    backend_name = "renode (not started)"

    def __init__(self, platform_resc: Optional[str] = None, port: int = 12345,
                 uart_log: Optional[str] = None, adc_feed_cmd: Optional[str] = None,
                 channel_map: Optional[Dict[str, int]] = None, vref: float = 3.3,
                 full_scale: float = 4095.0, gpio_read_cmds: Optional[Dict[str, str]] = None,
                 runfor_fmt: str = 'emulation RunFor "{seconds}"', sample_ms: int = 50,
                 model=None, require_renode: bool = False,
                 log_dir: str = "logs/renode", startup_timeout_s: float = 40.0):
        self.platform_resc = platform_resc or "boards/renode/stm32.resc"
        self.port, self.uart_log = port, uart_log
        self.adc_feed_cmd, self.channel_map = adc_feed_cmd, channel_map or {}
        self.vref, self.full_scale = vref, full_scale
        self.gpio_read_cmds = gpio_read_cmds or {}
        self.runfor_fmt, self.sample_ms = runfor_fmt, sample_ms
        self.require_renode = require_renode
        self.log_dir, self.startup_timeout_s = Path(log_dir), startup_timeout_s

        self.faults = SharedFaultLayer(full_scale=full_scale)
        self.host_sim = HostHALSimulator(model=model)      # only used when degraded
        self.mode = "degraded"
        self.executes_real_firmware = False
        self.notice: Optional[str] = None
        self.t_ms = 0
        self._inputs: Dict[str, float] = {}
        self._uart_off = 0
        self._serial: List[Tuple[int, str]] = []
        self._proc: Optional[subprocess.Popen] = None
        self._sock: Optional[socket.socket] = None
        self._log_fh = None

    def set_model(self, model) -> None:
        """Propagate model to internal Host-HAL simulator."""
        if hasattr(self.host_sim, "set_model"):
            self.host_sim.set_model(model)

    @classmethod
    def available(cls) -> Tuple[bool, str]:
        exe = shutil.which("renode")
        if not exe:
            return False, "renode executable not found in PATH"
        try:
            p = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                return True, f"Renode ready: {(p.stdout or p.stderr).strip().splitlines()[0]}"
            return False, "renode --version returned non-zero"
        except Exception as e:
            return False, f"Renode check error: {e}"

    def _degrade(self, why: str) -> None:
        if self.require_renode:
            raise BackendUnavailable(why)
        self.mode, self.executes_real_firmware, self.independent = "degraded", False, False
        self.backend_name = "renode (NOT running, Host-HAL model used)"
        self.notice = f"Renode not running: {why}. Results come from the Host-HAL model."

    # ---- monitor socket --------------------------------------------------
    def _cmd(self, text: str, timeout: float = 10.0) -> str:
        assert self._sock is not None
        self._sock.sendall(text.encode() + b"\n")
        buf, end = b"", time.time() + timeout
        self._sock.settimeout(0.5)
        while time.time() < end:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                if _PROMPT.search(buf):
                    break
                continue
            if not chunk:
                break
            buf += chunk
            if _PROMPT.search(buf):
                break
        return buf.decode(errors="replace")

    def start(self, artifact_path: Optional[str] = None) -> None:
        ok, reason = self.available()
        resc = Path(self.platform_resc)
        if not ok:
            return self._degrade(reason)
        if not resc.exists():
            return self._degrade(f".resc script not found: {resc}")
        if artifact_path and not Path(artifact_path).exists():
            return self._degrade(f"firmware image not found: {artifact_path}")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_fh = open(self.log_dir / "renode.log", "w")
        self._proc = subprocess.Popen(
            ["renode", "--disable-xwt", "--port", str(self.port), "--hide-log"],
            stdout=self._log_fh, stderr=subprocess.STDOUT)
        deadline = time.time() + self.startup_timeout_s
        while time.time() < deadline and self._sock is None:
            if self._proc.poll() is not None:
                self.stop()
                return self._degrade(f"renode exited early (see {self.log_dir / 'renode.log'})")
            try:
                self._sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
            except OSError:
                time.sleep(0.5)
        if self._sock is None:
            self.stop()
            return self._degrade("could not connect to the Renode monitor port")
        if artifact_path:
            self._cmd(f"$bin=@{Path(artifact_path).resolve()}")
        out = self._cmd(f"include @{resc.resolve()}", timeout=30)
        if "error" in out.lower():
            self.notice = out.strip()[:300]
            self.stop()
            return self._degrade(f"script error: {out.strip()[:200]}")
        self.mode, self.executes_real_firmware, self.independent = "renode", True, True
        self.backend_name = "renode"
        if not self.uart_log:
            self.notice = "uart_log not configured: no serial output can be read"

    def stop(self) -> None:
        try:
            if self._sock:
                self._sock.close()
        finally:
            self._sock = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    # ---- interface -------------------------------------------------------
    def reset(self) -> None:
        self.faults.reset()
        self.t_ms, self._serial, self._inputs, self._uart_off = 0, [], {}, 0
        if self.mode == "renode":
            self._cmd("machine Reset")
            if self.uart_log and Path(self.uart_log).exists():
                self._uart_off = Path(self.uart_log).stat().st_size
        else:
            self.host_sim.reset()

    @staticmethod
    def _raw(value: Union[float, int, str]) -> float:
        return float(str(value).lower().replace("raw:", ""))

    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        if self.mode != "renode":
            return self.host_sim.set_input(signal, value)
        if not self.adc_feed_cmd:
            raise NotImplementedError("Renode adapter needs adc_feed_cmd to inject sensor values")
        self._inputs[signal] = self._raw(value)

    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0, **kwargs) -> None:
        if self.mode != "renode":
            return self.host_sim.inject_fault(signal, fault_type, duration_ms, **kwargs)
        self.faults.set_fault(signal, fault_type, **kwargs)

    def clear_fault(self, signal: str) -> None:
        if self.mode != "renode":
            return self.host_sim.clear_fault(signal)
        self.faults.clear_fault(signal)

    def _feed_inputs(self) -> None:
        for sig, raw in self._inputs.items():
            v = self.faults.apply(sig, raw)
            self._cmd(self.adc_feed_cmd.format(raw=int(v), volts=v / self.full_scale * self.vref,
                                               channel=self.channel_map.get(sig, 0)))

    def _collect_uart(self) -> None:
        if not self.uart_log or not Path(self.uart_log).exists():
            return
        with open(self.uart_log, "rb") as fh:
            fh.seek(self._uart_off)
            data = fh.read()
            self._uart_off += len(data)
        for line in data.decode(errors="replace").splitlines():
            if line.strip() and not self.faults.is_active("uart", "silence"):
                self._serial.append((self.t_ms, line.strip()))

    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        if self.mode != "renode":
            return self.host_sim.run_for(duration_ms)
        start = len(self._serial)
        remaining = int(duration_ms)
        while remaining > 0:
            dt = min(self.sample_ms, remaining)
            remaining -= dt
            if self.adc_feed_cmd:
                self._feed_inputs()
            self._cmd(self.runfor_fmt.format(seconds=f"{dt / 1000:.3f}"), timeout=30)
            self.t_ms += dt
            self._collect_uart()
        return self._serial[start:]

    def read_pin(self, pin: str) -> int:
        if self.mode != "renode":
            return self.host_sim.read_pin(pin)
        cmd = self.gpio_read_cmds.get(str(pin))
        if not cmd:
            raise NotImplementedError(f"No gpio_read_cmds entry for pin {pin}")
        m = re.search(r"-?\d+", self._cmd(cmd))
        return int(m.group(0)) if m else 0

    def read_serial(self) -> List[Tuple[int, str]]:
        return list(self._serial) if self.mode == "renode" else self.host_sim.read_serial()
