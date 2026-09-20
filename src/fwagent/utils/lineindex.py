"""
LineIndex utility for mapping firmware symbols, constants, and rules to exact 1-based source lines.
"""

from typing import List, Tuple, Optional


class LineIndex:
    def __init__(self, content: str):
        self.raw_content = content
        self.lines: List[str] = content.splitlines()

    def get_line(self, line_number: 1) -> str:
        if 1 <= line_number <= len(self.lines):
            return self.lines[line_number - 1]
        return ""

    def find_line_of_pattern(self, pattern: str) -> Optional[int]:
        for i, line in enumerate(self.lines, start=1):
            if pattern in line:
                return i
        return None

    def get_line_numbers_of_pattern(self, pattern: str) -> List[int]:
        matches = []
        for i, line in enumerate(self.lines, start=1):
            if pattern in line:
                matches.append(i)
        return matches

    def to_line_numbered_code(self) -> str:
        return "\n".join(
            f"{i:4d} | {line}" for i, line in enumerate(self.lines, start=1)
        )
