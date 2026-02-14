from __future__ import annotations

from rich.console import Console
from rich.text import Text

from qsol.diag.diagnostic import Diagnostic
from qsol.diag.source import SourceText


class DiagnosticReporter:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(stderr=True)

    def render_text(self, source: SourceText, diag: Diagnostic) -> str:
        excerpt = source.excerpt(diag.span)
        caret = " " * max(diag.span.col - 1, 0) + "^" * max(1, diag.span.end_col - diag.span.col)
        head = (
            f"{diag.span.filename}:{diag.span.line}:{diag.span.col}: "
            f"{diag.severity.value}[{diag.code}]: {diag.message}"
        )
        lines = [head, excerpt, caret]
        lines.extend(f"note: {n}" for n in diag.notes)
        lines.extend(f"help: {h}" for h in diag.help)
        return "\n".join(lines)

    def print(self, source: SourceText, diagnostics: list[Diagnostic]) -> None:
        for diag in diagnostics:
            style = "red" if diag.is_error else "yellow"
            text = Text(self.render_text(source, diag), style=style)
            self.console.print(text)
