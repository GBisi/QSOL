from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    start_offset: int
    end_offset: int
    line: int
    col: int
    end_line: int
    end_col: int
    filename: str = "<input>"


class SourceText:
    def __init__(self, text: str, filename: str = "<input>") -> None:
        self.text = text
        self.filename = filename
        self._line_starts = [0]
        for idx, ch in enumerate(text):
            if ch == "\n":
                self._line_starts.append(idx + 1)

    def line_text(self, line: int) -> str:
        if line < 1 or line > len(self._line_starts):
            return ""
        start = self._line_starts[line - 1]
        if line == len(self._line_starts):
            end = len(self.text)
        else:
            end = self._line_starts[line] - 1
        return self.text[start:end]

    def excerpt(self, span: Span) -> str:
        return self.line_text(span.line)
