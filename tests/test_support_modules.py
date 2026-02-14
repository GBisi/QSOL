from __future__ import annotations

import io

from rich.console import Console

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.reporter import DiagnosticReporter
from qsol.diag.source import SourceText, Span
from qsol.parse import ast
from qsol.sema.validate import validate_program
from qsol.util.stable_hash import stable_hash


def _span() -> Span:
    return Span(
        start_offset=0,
        end_offset=1,
        line=1,
        col=1,
        end_line=1,
        end_col=2,
        filename="test.qsol",
    )


def test_stable_hash_is_deterministic_and_order_insensitive() -> None:
    a = {"x": 1, "y": [2, 3]}
    b = {"y": [2, 3], "x": 1}
    assert stable_hash(a) == stable_hash(b)


def test_source_text_line_text_and_excerpt_bounds() -> None:
    src = SourceText("a\nb\nc\n", filename="f.qsol")
    assert src.line_text(1) == "a"
    assert src.line_text(3) == "c"
    assert src.line_text(0) == ""
    assert src.line_text(99) == ""
    assert src.excerpt(_span()) == "a"


def test_diagnostic_reporter_render_and_print() -> None:
    span = _span()
    diag = Diagnostic(
        severity=Severity.WARNING,
        code="QSOL9999",
        message="demo",
        span=span,
        notes=["first note"],
        help=["try this"],
    )
    src = SourceText("x\n", filename="test.qsol")
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)
    reporter = DiagnosticReporter(console=console)

    rendered = reporter.render_text(src, diag)
    assert "warning[QSOL9999]: demo" in rendered
    assert "note: first note" in rendered
    assert "help: try this" in rendered

    reporter.print(src, [diag])
    output = stream.getvalue()
    assert "QSOL9999" in output
    assert "demo" in output


def test_validate_program_reports_unknown_block_issues() -> None:
    span = _span()
    unknown = ast.UnknownDef(
        span=span,
        name="U",
        formals=["A"],
        rep_block=[],
        laws_block=[
            ast.Constraint(
                span=span,
                kind=ast.ConstraintKind.SHOULD,
                expr=ast.BoolLit(span=span, value=True),
            )
        ],
        view_block=[],
    )
    program = ast.Program(span=span, items=[unknown])
    diagnostics = validate_program(program)
    codes = [d.code for d in diagnostics]
    severities = [d.severity for d in diagnostics]
    assert "QSOL3001" in codes
    assert "QSOL2101" in codes
    assert Severity.WARNING in severities
    assert Severity.ERROR in severities
