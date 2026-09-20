from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Union, Literal, Set
from pydantic import BaseModel, Field


class Obs(BaseModel):
    """
    Unified Observation record returned by all simulator backends.
    """
    t_ms: int
    source: Literal["serial", "pin", "adc", "physical"]
    signal: str  # e.g., "FAN", "pin9", "robot_x", "temp"
    value: Union[float, int, str]


class Simulator(ABC):
    """
    Abstract Simulator Interface for driving virtual hardware.
    Supports Host-HAL SIL, Wokwi CLI, Renode, and Gazebo SITL backends.
    """
    capabilities: Set[str] = {"base"}

    @classmethod
    def available(cls) -> Tuple[bool, str]:
        """
        Check if the backend is installed and usable on this host machine.
        Returns (is_available, status_or_reason_string).
        """
        return True, "Available"

    @abstractmethod
    def reset(self) -> None:
        """Reset virtual MCU hardware state."""
        pass

    @abstractmethod
    def set_input(self, signal: str, value: Union[float, int, str]) -> None:
        """Set an input signal or pin value (ADC count or GPIO state)."""
        pass

    @abstractmethod
    def inject_fault(self, signal: str, fault_type: str, duration_ms: int = 0, **kwargs) -> None:
        """Inject a hardware fault (open_circuit, short_to_gnd, short_to_vcc, stuck, glitch)."""
        pass

    @abstractmethod
    def clear_fault(self, signal: str) -> None:
        """Clear active fault injection on a signal."""
        pass

    @abstractmethod
    def run_for(self, duration_ms: int) -> List[Tuple[int, str]]:
        """
        Advance virtual clock by duration_ms.
        Returns list of (timestamp_ms, serial_line) events produced.
        """
        pass

    @abstractmethod
    def read_pin(self, pin: str) -> int:
        """Read digital output or PWM pin state (0 or 1)."""
        pass

    @abstractmethod
    def read_serial(self) -> List[Tuple[int, str]]:
        """Get captured serial log lines since last read."""
        pass
