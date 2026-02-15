from __future__ import annotations

import io
import json
from pathlib import Path

import dimod
from rich.console import Console

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.instance import instantiate_ir
from qsol.cli import SamplerKind, _print_diags, _sample_sa, _write_run_output
from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import (
    check_program,
    compile_source,
    compile_with_instance,
    lower_symbolic,
    parse_program,
)
from qsol.compiler.pipeline import (
    instantiate_ir as instantiate_ir_pipeline,
)
from qsol.diag.cli_diagnostics import (
    file_read_error,
    instance_load_error,
    invalid_flag_combination,
    missing_artifact,
    missing_instance_file,
    runtime_prep_error,
    runtime_sampling_error,
)
from qsol.diag.diagnostic import Diagnostic, DiagnosticLabel, Severity
from qsol.diag.reporter import DiagnosticReporter
from qsol.diag.source import SourceRepository, SourceText, Span
from qsol.parse import ast
from qsol.sema.validate import validate_program
from qsol.util.bqm_equivalence import check_qsol_program_bqm_equivalence
from qsol.util.stable_hash import stable_hash


def _span(
    *,
    line: int = 1,
    col: int = 1,
    end_line: int = 1,
    end_col: int = 2,
    filename: str = "test.qsol",
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
    assert src.line_count == 4
    assert src.line_length(2) == 1
    window = src.context_window(_span(line=2, end_line=2), before=1, after=1)
    assert window == [(1, "a"), (2, "b"), (3, "c")]


def test_source_repository_caching_and_lookup(tmp_path: Path) -> None:
    repo = SourceRepository()
    remembered = repo.from_text("x\n", filename="inline.qsol")
    assert repo.get("inline.qsol") is remembered
    assert repo.get("<input>") is None
    assert repo.get(str(tmp_path / "missing.qsol")) is None

    disk = tmp_path / "disk.qsol"
    disk.write_text("problem P {}\n", encoding="utf-8")
    loaded = repo.get(str(disk))
    assert loaded is not None
    assert loaded.line_text(1) == "problem P {}"


def test_source_repository_oserror_and_empty_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = SourceRepository()
    disk = tmp_path / "disk.qsol"
    disk.write_text("x\n", encoding="utf-8")

    def _boom(self: Path, encoding: str = "utf-8") -> str:
        _ = encoding
        raise OSError("boom")

    monkeypatch.setattr(type(disk), "read_text", _boom)
    assert repo.get(str(disk)) is None

    src = SourceText("x\n", filename="empty.qsol")
    src._lines = []
    assert src.context_window(_span()) == []


def test_diagnostic_reporter_render_and_print() -> None:
    span = _span()
    diag = Diagnostic(
        severity=Severity.WARNING,
        code="QSOL9999",
        message="demo",
        span=span,
        labels=[DiagnosticLabel(span=span, message="primary label", is_primary=True)],
        notes=["first note"],
        help=["try this"],
    )
    src = SourceText("x\n", filename="test.qsol")
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)
    reporter = DiagnosticReporter(console=console)

    rendered = reporter.render_text(src, diag)
    assert "warning[QSOL9999]: demo" in rendered
    assert "--> test.qsol:1:1" in rendered
    assert "primary label" in rendered
    assert "= note: first note" in rendered
    assert "= help: try this" in rendered

    reporter.print(src, [diag])
    output = stream.getvalue()
    assert "QSOL9999" in output
    assert "demo" in output
    assert "finished with 0 error(s), 1 warning(s), 0 info message(s)" in output


def test_diagnostic_reporter_handles_non_primary_and_multiline_spans() -> None:
    span = Span(
        start_offset=0,
        end_offset=1,
        line=1,
        col=10,
        end_line=2,
        end_col=1,
        filename="multi.qsol",
    )
    diag = Diagnostic(
        severity=Severity.INFO,
        code="QSOL7777",
        message="demo-info",
        span=span,
        labels=[DiagnosticLabel(span=span, message="label-without-primary", is_primary=False)],
    )
    src = SourceText("ab\ncd\n", filename="multi.qsol")
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)
    reporter = DiagnosticReporter(console=console)
    reporter.print(src, [diag])
    output = stream.getvalue()
    assert "info[QSOL7777]: demo-info" in output
    assert "label-without-primary" in output
    assert "finished with 0 error(s), 0 warning(s), 1 info message(s)" in output


def test_cli_diagnostic_builders_cover_codes(tmp_path: Path) -> None:
    model = tmp_path / "model.qsol"
    inferred = tmp_path / "model.instance.json"

    assert invalid_flag_combination("bad", file=model).code == "QSOL4001"
    assert missing_instance_file(inferred, model_path=model).code == "QSOL4002"
    assert file_read_error(model, OSError("denied")).code == "QSOL4003"
    assert instance_load_error(inferred, ValueError("json")).code == "QSOL4004"
    assert missing_artifact("missing", model_path=model).code == "QSOL4005"
    assert runtime_prep_error(model, "prep", notes=["note"]).code == "QSOL4005"
    assert runtime_sampling_error(model, RuntimeError("sampler")).code == "QSOL5001"


def test_cli_helper_branches(tmp_path: Path, monkeypatch) -> None:
    class _FakeSampler:
        parameters: dict[str, object] = {}

        def sample(self, _bqm, **kwargs: object) -> dict[str, object]:
            return {"kwargs": kwargs}

    monkeypatch.setattr("qsol.cli.dimod.SimulatedAnnealingSampler", lambda: _FakeSampler())
    bqm = dimod.BinaryQuadraticModel({}, {}, 0.0, dimod.BINARY)
    sampled = _sample_sa(bqm, {"num_reads": 3})
    assert sampled["kwargs"] == {"num_reads": 3}

    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None)
    has_errors = _print_diags(
        console,
        None,
        [Diagnostic(severity=Severity.INFO, code="QSOL9001", message="info", span=_span())],
    )
    assert not has_errors
    assert "info[QSOL9001]" in stream.getvalue()

    class _First:
        sample = {"x": 0, "aux:z": 1, "keep": 1}
        energy = 0.0

    class _Set:
        first = _First()

        def __len__(self) -> int:
            return 1

    run_path = _write_run_output(
        outdir=tmp_path,
        sampler=SamplerKind.exact,
        num_reads=1,
        seed=None,
        sampleset=_Set(),
        varmap={"keep": "Keep"},
    )
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    assert payload["selected_assignments"] == [{"meaning": "Keep", "value": 1, "variable": "keep"}]


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


def test_pipeline_wrapper_functions(tmp_path: Path) -> None:
    source = """
problem Demo {
  set A;
  find S : Subset(A);
  must true;
}
""".strip()
    tree = parse_program(source, filename="wrap.qsol")
    assert tree.data == "start"

    checked = check_program(source, filename="wrap.qsol")
    assert checked.ast is not None

    lowered = lower_symbolic(source, filename="wrap.qsol")
    assert lowered.lowered_ir_symbolic is not None

    instance = tmp_path / "wrap.instance.json"
    instance.write_text('{"problem":"Demo","sets":{"A":["a1"]},"params":{}}', encoding="utf-8")

    instantiated = instantiate_ir_pipeline(
        source,
        filename="wrap.qsol",
        instance_path=str(instance),
    )
    assert instantiated.lowered_ir_symbolic is not None

    outdir = tmp_path / "out"
    compiled = compile_with_instance(
        source,
        filename="wrap.qsol",
        instance_path=str(instance),
        outdir=str(outdir),
        output_format="qubo",
    )
    assert compiled.artifacts is not None


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
