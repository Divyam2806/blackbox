import re
from typing import List, Tuple, Dict, Any
from fwagent.models import ObservedEvent


class LogParser:
    """
    Parses raw timestamped serial log strings against regex patterns into structured ObservedEvent streams.
    """

    def __init__(self, log_patterns: List[str] = None):
        self.patterns = log_patterns or [r"T=(?P<temp>[-\d.]+) FAN=(?P<fan>ON|OFF)"]

    def parse(self, raw_logs: List[Tuple[int, str]]) -> List[ObservedEvent]:
        """
        Convert raw timestamped serial log entries [(t_ms, line), ...] into list of ObservedEvents.
        """
        events: List[ObservedEvent] = []

        for t_ms, line in raw_logs:
            parsed_line = False
            for pattern in self.patterns:
                match = re.search(pattern, line)
                if match:
                    group_dict = match.groupdict()
                    for sig_name, val_str in group_dict.items():
                        try:
                            val: Any = float(val_str)
                        except ValueError:
                            val = val_str
                        events.append(ObservedEvent(
                            t_ms=t_ms,
                            signal=sig_name,
                            value=val,
                            raw_log=line
                        ))
                    parsed_line = True
                    break

            if not parsed_line and line.strip():
                # Generic raw log capture if pattern didn't match
                events.append(ObservedEvent(
                    t_ms=t_ms,
                    signal="serial_raw",
                    value=line.strip(),
                    raw_log=line
                ))

        return events
