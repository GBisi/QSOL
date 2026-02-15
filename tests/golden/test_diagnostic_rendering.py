from __future__ import annotations

import io

from rich.console import Console

from qsol.diag.diagnostic import Diagnostic, DiagnosticLabel, Severity
from qsol.diag.reporter import DiagnosticReporter
from qsol.diag.source import SourceText, Span


def _span(
    *,
    line: int = 1,
    col: int = 1,
    end_line: int = 1,
    end_col: int = 2,
    filename: str = "render.qsol",
) -> Span:
    return Span(
        start_offset=0,
        end_offset=1,
        line=line,
        col=col,
        end_line=end_line,
        end_col=end_col,
        filename=filename,
    )


def test_rendering_supports_multiline_and_secondary_labels() -> None:
    source = SourceText("\tset A;\nfind A : Subset(A);\n", filename="render.qsol")
    diag = Diagnostic(
        severity=Severity.ERROR,
        code="QSOL2002",
        message="redefinition of `A` in same scope",
        span=_span(line=2, col=6, end_line=2, end_col=7),
        labels=[
            DiagnosticLabel(
                span=_span(line=2, col=6, end_line=2, end_col=7),
                message="redefined here",
                is_primary=True,
            ),
            DiagnosticLabel(
                span=_span(line=1, col=6, end_line=1, end_col=7),
                message="previous definition here",
                is_primary=False,
            ),
        ],
    )

    stream = io.StringIO()
    reporter = DiagnosticReporter(
        console=Console(file=stream, force_terminal=False, color_system=None)
    )
    reporter.print(source, [diag])

    output = stream.getvalue()
    assert "error[QSOL2002]" in output
    assert "--> render.qsol:2:6" in output
    assert "redefined here" in output
    assert "previous definition here" in output
    assert "aborting due to 1 error(s), 0 warning(s), 0 info message(s)" in output


def test_rendering_handles_missing_source_files() -> None:
    missing_span = _span(filename="/tmp/does-not-exist.qsol")
    diag = Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4003",
        message="failed to read file: /tmp/does-not-exist.qsol",
        span=missing_span,
    )

    stream = io.StringIO()
    reporter = DiagnosticReporter(
        console=Console(file=stream, force_terminal=False, color_system=None)
    )
    reporter.print(None, [diag])
    output = stream.getvalue()

    assert "source is unavailable for this diagnostic span" in output
    assert "QSOL4003" in output
