from __future__ import annotations

import io

import dimod
from rich.console import Console

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.instance import instantiate_ir
from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source
from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.reporter import DiagnosticReporter
from qsol.diag.source import SourceText, Span
from qsol.parse import ast
from qsol.sema.validate import validate_program
from qsol.util.bqm_equivalence import check_qsol_program_bqm_equivalence
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


def _compile_bqm_from_program(
    program: str, instance: dict[str, object]
) -> dimod.BinaryQuadraticModel:
    unit = compile_source(program, options=CompileOptions(filename="equivalence_test.qsol"))
    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.lowered_ir_symbolic is not None

    inst = instantiate_ir(unit.lowered_ir_symbolic, instance)
    assert not any(diag.is_error for diag in inst.diagnostics)
    assert inst.ground_ir is not None

    codegen = DimodCodegen().compile(inst.ground_ir)
    assert not any(diag.is_error for diag in codegen.diagnostics)
    return codegen.bqm


def test_check_qsol_program_bqm_equivalence_reports_equivalent() -> None:
    program = """
problem FirstProgram {
  set Items;
  param Value[Items] : Real = 1;
  find Pick : Subset(Items);
  must sum(if Pick.has(i) then 1 else 0 for i in Items) = 2;
  maximize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
""".strip()
    instance: dict[str, object] = {
        "problem": "FirstProgram",
        "sets": {"Items": ["i1", "i2", "i3", "i4"]},
        "params": {"Value": {"i1": 3, "i2": 8, "i3": 5, "i4": 2}},
    }
    reference_bqm = _compile_bqm_from_program(program, instance)
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)

    report = check_qsol_program_bqm_equivalence(
        program,
        reference_bqm,
        instance=instance,
        filename="equivalence_test.qsol",
        console=console,
    )

    assert report.equivalent
    output = stream.getvalue()
    assert "Equivalent" in output
    assert "Linear Bias Mismatches" not in output


def test_check_qsol_program_bqm_equivalence_reports_differences() -> None:
    program = """
problem FirstProgram {
  set Items;
  param Value[Items] : Real = 1;
  find Pick : Subset(Items);
  must sum(if Pick.has(i) then 1 else 0 for i in Items) = 2;
  maximize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
""".strip()
    instance: dict[str, object] = {
        "problem": "FirstProgram",
        "sets": {"Items": ["i1", "i2", "i3", "i4"]},
        "params": {"Value": {"i1": 3, "i2": 8, "i3": 5, "i4": 2}},
    }
    provided_bqm = _compile_bqm_from_program(program, instance)
    first_var = next(iter(provided_bqm.variables))
    provided_bqm.set_linear(first_var, float(provided_bqm.get_linear(first_var)) + 5.0)
    provided_bqm.add_variable("unexpected_var", 1.0)

    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)

    report = check_qsol_program_bqm_equivalence(
        program,
        provided_bqm,
        instance=instance,
        filename="equivalence_test.qsol",
        console=console,
    )

    assert not report.equivalent
    assert report.linear_bias_mismatches
    assert "unexpected_var" in report.extra_variables
    output = stream.getvalue()
    assert "Not Equivalent" in output
    assert "Linear Bias Mismatches" in output
