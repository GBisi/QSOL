from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.text import Text

from qsol.diag.diagnostic import Diagnostic, DiagnosticLabel, Severity
from qsol.diag.source import SourceRepository, SourceText, Span


class DiagnosticReporter:
    TAB_SIZE = 4

    def __init__(
        self,
        console: Console | None = None,
        *,
        repository: SourceRepository | None = None,
    ) -> None:
        self.console = console or Console(stderr=True)
        self.repository = repository or SourceRepository()

    def render_text(self, source: SourceText | None, diag: Diagnostic) -> str:
        filename = diag.span.filename
        line = max(1, diag.span.line)
        col = max(1, diag.span.col)
        lines = [
            f"{diag.severity.value}[{diag.code}]: {diag.message}",
            f"  --> {filename}:{line}:{col}",
        ]

        resolved_source = self._resolve_source(source, filename)
        labels = self._labels_for(diag)
        if resolved_source is not None:
            lines.append("   |")
            lines.extend(self._render_labels(resolved_source, labels))
        else:
            lines.append("   = note: source is unavailable for this diagnostic span")

        lines.extend(f"   = note: {n}" for n in diag.notes)
        lines.extend(f"   = help: {h}" for h in diag.help)
        return "\n".join(lines)

    def print(self, source: SourceText | None, diagnostics: list[Diagnostic]) -> None:
        ordered = sorted(
            enumerate(diagnostics),
            key=lambda item: (
                item[1].span.filename,
                item[1].span.line,
                item[1].span.col,
                item[0],
            ),
        )

        for _, diag in ordered:
            style = self._severity_style(diag.severity)
            text = Text(self.render_text(source, diag), style=style)
            self.console.print(text)
            self.console.print()
        if diagnostics:
            self.console.print(self.render_summary(diagnostics))

    def render_summary(self, diagnostics: list[Diagnostic]) -> str:
        errors = sum(1 for d in diagnostics if d.severity == Severity.ERROR)
        warnings = sum(1 for d in diagnostics if d.severity == Severity.WARNING)
        infos = sum(1 for d in diagnostics if d.severity == Severity.INFO)
        if errors:
            return (
                f"aborting due to {errors} error(s), {warnings} warning(s), {infos} info message(s)"
            )
        return f"finished with {errors} error(s), {warnings} warning(s), {infos} info message(s)"

    def _resolve_source(self, source: SourceText | None, filename: str) -> SourceText | None:
        if source is not None:
            self.repository.remember(source)
            if source.filename == filename:
                return source
        return self.repository.get(filename)

    def _labels_for(self, diag: Diagnostic) -> list[DiagnosticLabel]:
        labels = list(diag.labels)
        if not labels:
            labels.append(DiagnosticLabel(span=diag.span, is_primary=True))
            return labels
        if not any(label.is_primary for label in labels):
            labels[0] = DiagnosticLabel(
                span=labels[0].span,
                message=labels[0].message,
                is_primary=True,
            )
        return labels

    def _render_labels(self, source: SourceText, labels: Iterable[DiagnosticLabel]) -> list[str]:
        lines: list[str] = []
        for idx, label in enumerate(labels):
            if idx > 0:
                lines.append("   |")
            label_lines = self._render_single_label(source, label)
            lines.extend(label_lines)
        return lines

    def _render_single_label(self, source: SourceText, label: DiagnosticLabel) -> list[str]:
        span = label.span
        start_line = max(1, min(span.line, source.line_count))
        end_line = max(start_line, min(span.end_line, source.line_count))
        rendered: list[str] = []

        for line_no in range(start_line, end_line + 1):
            raw = source.line_text(line_no)
            expanded = raw.expandtabs(self.TAB_SIZE)
            start_col, end_col = self._span_cols_for_line(raw, span, line_no)
            start_visual = self._to_visual_col(raw, start_col)
            end_visual = self._to_visual_col(raw, end_col)
            width = max(1, end_visual - start_visual)
            marker = " " * start_visual + "^" * width
            rendered.append(f"{line_no:>3} | {expanded}")
            if line_no == start_line and label.message:
                rendered.append(f"   | {marker} {label.message}")
            else:
                rendered.append(f"   | {marker}")
        return rendered

    def _span_cols_for_line(self, raw: str, span: Span, line_no: int) -> tuple[int, int]:
        actual_span = span
        if line_no == actual_span.line:
            start = max(1, actual_span.col)
        else:
            start = 1
        if line_no == actual_span.end_line:
            end = max(start + 1, actual_span.end_col)
        else:
            end = len(raw) + 1
        max_col = len(raw) + 1
        start = min(max_col, start)
        end = min(max_col, end)
        if end <= start:
            end = min(max_col, start + 1)
        return start, end

    def _to_visual_col(self, raw: str, col: int) -> int:
        prefix = raw[: max(0, col - 1)]
        return len(prefix.expandtabs(self.TAB_SIZE))

    def _severity_style(self, severity: Severity) -> str:
        if severity == Severity.ERROR:
            return "red"
        if severity == Severity.WARNING:
            return "yellow"
        return "cyan"
