"""
Core Pydantic Data Models for BlackBox FW-Agent
"""

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


class Signal(BaseModel):
    name: str
    kind: str = "adc"
    pin: Optional[Any] = None
    unit: Optional[str] = None
    valid_range: Optional[tuple[float, float]] = None
    line: Optional[int] = None  # firmware source line number
    driven: Optional[bool] = None  # outputs: is it ever written/driven?


class Rule(BaseModel):
    id: str  # R1, I2, etc.
    text: str
    source: Literal["spec", "code", "invariant"]
    line: Optional[int] = None


class Threshold(BaseModel):
    signal: str
    op: str = "=="
    value: float
    raw_adc: Optional[int] = None
    line: Optional[int] = None


class ErrorPath(BaseModel):
    trigger: str = ""
    handler: Optional[str] = None
    note: Optional[str] = None
    line: Optional[int] = None


class FirmwareModel(BaseModel):
    firmware_name: str = "firmware"
    inputs: list[Signal] = Field(default_factory=list)
    outputs: list[Signal] = Field(default_factory=list)
    thresholds: list[Threshold] = Field(default_factory=list)
    states: list[Any] = Field(default_factory=list)
    error_paths: list[ErrorPath] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    log_patterns: list[str] = Field(default_factory=list)


class Step(BaseModel):
    at_ms: int
    action: Literal[
        "set_input",
        "inject_fault",
        "clear_fault",
        "press_button",
        "uart_send",
        "reset",
        "wait",
    ]
    target: Optional[str] = None
    value: Optional[float | str] = None


class Expect(BaseModel):
    kind: Literal[
        "output_eq",
        "serial_contains",
        "serial_absent",
        "transition_count",
        "within_ms",
        "no_change",
        "physical_eq",
        "within_tolerance",
    ]
    target: Optional[str] = None
    value: Optional[float | str] = None
    window_ms: Optional[tuple[int, int]] = None
    rule_id: Optional[str] = None


class TestCase(BaseModel):
    id: str
    title: str
    category: str = "normal"
    rationale: str
    steps: list[Step] = Field(default_factory=list)
    expects: list[Expect] = Field(default_factory=list)
    priority: int = 2
    origin: Literal["rule", "llm", "adaptive"] = "rule"


class Verdict(BaseModel):
    test_id: str
    status: Literal["PASS", "FAIL", "WARN", "AMBIGUOUS", "INCONCLUSIVE", "SKIPPED"]
    evidence: list[str] = Field(default_factory=list)          # kept for backward compat
    evidence_chain: list[dict] = Field(default_factory=list)   # structured: {ms, category, detail, data}
    rule_ids: list[str] = Field(default_factory=list)
    expected: str = ""
    observed: str = ""


class Finding(BaseModel):
    id: str = Field(default="F1")
    severity: str = Field(default="High")
    title: str = Field(default="")
    evidence_tests: list[str] = Field(default_factory=list)
    evidence_lines: list[str] = Field(default_factory=list)
    firmware_lines: list[int] = Field(default_factory=list)
    likely_cause: str = Field(default="")
    suggested_fix: str = Field(default="")


class FindingsResponse(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class ImprovementSuggestion(BaseModel):
    category: str = Field(default="Architecture & Robustness")
    title: str = Field(default="")
    description: str = Field(default="")
    code_snippet: Optional[str] = Field(default=None)


class SuggestionsResponse(BaseModel):
    suggestions: list[ImprovementSuggestion] = Field(default_factory=list)




class RunConfig(BaseModel):
    firmware_dir: str
    spec_file: Optional[str] = None
    simulator: Literal["auto", "host", "wokwi", "renode", "gazebo", "all", "fake"] = "auto"
    max_rounds: int = 3
    test_timeout_s: float = 10.0
    llm_provider: str = "mock"  # or openai, ollama, anthropic
    out_dir: Optional[str] = None


class ObservedEvent(BaseModel):
    t_ms: int
    signal: str
    value: Any
    raw_log: str = ""

