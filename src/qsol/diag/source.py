from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
        self._lines = text.split("\n")

    def line_text(self, line: int) -> str:
        if line < 1 or line > len(self._lines):
            return ""
        return self._lines[line - 1].rstrip("\r")

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def line_length(self, line: int) -> int:
        return len(self.line_text(line))

    def excerpt(self, span: Span) -> str:
        return self.line_text(span.line)

    def context_window(
        self,
        span: Span,
        *,
        before: int = 0,
        after: int = 0,
    ) -> list[tuple[int, str]]:
        if self.line_count <= 0:
            return []
        start_line = max(1, min(span.line, self.line_count))
        end_line = max(start_line, min(span.end_line, self.line_count))
        start_line = max(1, start_line - before)
        end_line = min(self.line_count, end_line + after)
        return [(line, self.line_text(line)) for line in range(start_line, end_line + 1)]


class SourceRepository:
    def __init__(self) -> None:
        self._cache: dict[str, SourceText | None] = {}

    def remember(self, source: SourceText) -> SourceText:
        self._cache[source.filename] = source
        return source

    def from_text(self, text: str, filename: str = "<input>") -> SourceText:
        return self.remember(SourceText(text=text, filename=filename))

    def get(self, filename: str) -> SourceText | None:
        if filename in self._cache:
            return self._cache[filename]
        if filename.startswith("<") and filename.endswith(">"):
            self._cache[filename] = None
            return None
        try:
            path = Path(filename)
            if not path.exists() or not path.is_file():
                self._cache[filename] = None
                return None
            text = path.read_text(encoding="utf-8")
        except OSError:
            self._cache[filename] = None
            return None
        source = SourceText(text=text, filename=filename)
        self._cache[filename] = source
        return source
