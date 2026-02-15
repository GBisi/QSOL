from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from types import SimpleNamespace

import dimod
import pytest

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.util import bqm_equivalence as bqme
from qsol.util import example_equivalence as exeq


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


def _diag_error() -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL9999",
        message="error",
        span=_span(),
    )


def _diag_warning() -> Diagnostic:
    return Diagnostic(
        severity=Severity.WARNING,
        code="QSOL9000",
        message="warning",
        span=_span(),
    )


def _single_var_bqm(name: str = "x") -> dimod.BinaryQuadraticModel:
    bqm = dimod.BinaryQuadraticModel({}, {}, 0.0, dimod.BINARY)
    bqm.add_variable(name, 0.0)
    return bqm


def _write_minimal_example_files(base_dir: Path) -> None:
    program = """
problem P {
  set A;
  find X : Subset(A);
  minimize 0;
}
""".strip()
    instance = {"problem": "P", "sets": {"A": ["a"]}, "params": {}}
    (base_dir / "model.qsol").write_text(program, encoding="utf-8")
    (base_dir / "instance.json").write_text(json.dumps(instance), encoding="utf-8")


def _build_spec(
    base_dir: Path,
    *,
    require_structural_equivalence: bool = True,
    solve_fn: exeq.Callable[
        [dimod.BinaryQuadraticModel, exeq.Mapping[str, object], exeq.RuntimeSolveOptions], int
    ]
    | None = None,
    same_fn: exeq.Callable[[int, int, float], bool] | None = None,
) -> exeq.EquivalenceExampleSpec[int]:
    _write_minimal_example_files(base_dir)

    def default_solve(
        bqm: dimod.BinaryQuadraticModel,
        instance: exeq.Mapping[str, object],
        options: exeq.RuntimeSolveOptions,
    ) -> int:
        _ = instance, options
        return len(bqm.variables)

    def default_same(lhs: int, rhs: int, atol: float) -> bool:
        _ = atol
        return lhs == rhs

    def render_solution(
        console: exeq.Console,
        result: int,
        title: str,
    ) -> None:
        console.print(f"{title}: {result}")

    return exeq.EquivalenceExampleSpec[int](
        description="test",
        base_dir=base_dir,
        program_filename="model.qsol",
        instance_filename="instance.json",
        custom_solution_title="custom",
        compiled_solution_title="compiled",
        build_custom_bqm=lambda instance: _single_var_bqm(str(instance.get("problem", "x"))),
        solve_bqm=solve_fn or default_solve,
        render_solution=render_solution,
        same_runtime_result=same_fn or default_same,
        require_structural_equivalence=require_structural_equivalence,
    )


def test_sample_best_assignment_covers_exact_sa_and_guard() -> None:
    bqm = _single_var_bqm()
    exact = exeq.sample_best_assignment(
        bqm,
        exeq.RuntimeSolveOptions(use_simulated_annealing=False, max_exact_variables=10),
    )
    assert exact.sample

    sa = exeq.sample_best_assignment(
        bqm,
        exeq.RuntimeSolveOptions(use_simulated_annealing=True, num_reads=2),
    )
    assert sa.sample

    with pytest.raises(ValueError):
        exeq.sample_best_assignment(
            bqm,
            exeq.RuntimeSolveOptions(use_simulated_annealing=False, max_exact_variables=0),
        )


def test_parse_args_positive_int_and_read_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spec = _build_spec(tmp_path)

    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--simulated-annealing", "--num-reads", "7"],
    )
    args = exeq._parse_args(spec)
    assert args.simulated_annealing is True
    assert args.num_reads == 7

    assert exeq._positive_int("3") == 3
    with pytest.raises(argparse.ArgumentTypeError):
        exeq._positive_int("0")
    with pytest.raises(argparse.ArgumentTypeError):
        exeq._positive_int("x")

    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"k": 1}', encoding="utf-8")
    assert exeq._read_json(payload_path) == {"k": 1}
    payload_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        exeq._read_json(payload_path)


def test_parse_args_help_has_useful_descriptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = _build_spec(tmp_path)
    monkeypatch.setattr("sys.argv", ["prog", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        exeq._parse_args(spec)

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert spec.description in help_text
    assert "--simulated-annealing" in help_text
    assert "SimulatedAnnealingSampler" in help_text
    assert "runtime" in help_text
    assert "solve" in help_text
    assert "checks" in help_text
    assert "Number of reads for simulated annealing" in help_text


def test_compile_qsol_bqm_branching(monkeypatch: pytest.MonkeyPatch) -> None:
    good_bqm = _single_var_bqm()
    lowered = object()
    ground = object()

    monkeypatch.setattr(
        exeq,
        "compile_source",
        lambda _text, options: SimpleNamespace(
            diagnostics=[_diag_error()], lowered_ir_symbolic=None
        ),
    )
    out, diagnostics = exeq._compile_qsol_bqm(program_text="p", instance={}, filename="f")
    assert out is None
    assert diagnostics

    monkeypatch.setattr(
        exeq,
        "compile_source",
        lambda _text, options: SimpleNamespace(diagnostics=[], lowered_ir_symbolic=lowered),
    )
    monkeypatch.setattr(
        exeq,
        "instantiate_ir",
        lambda _lowered, _instance: SimpleNamespace(diagnostics=[_diag_error()], ground_ir=None),
    )
    out, diagnostics = exeq._compile_qsol_bqm(program_text="p", instance={}, filename="f")
    assert out is None
    assert diagnostics

    monkeypatch.setattr(
        exeq,
        "instantiate_ir",
        lambda _lowered, _instance: SimpleNamespace(diagnostics=[], ground_ir=ground),
    )
    monkeypatch.setattr(
        exeq,
        "DimodCodegen",
        lambda: SimpleNamespace(
            compile=lambda _ground: SimpleNamespace(diagnostics=[_diag_error()], bqm=good_bqm)
        ),
    )
    out, diagnostics = exeq._compile_qsol_bqm(program_text="p", instance={}, filename="f")
    assert out is None
    assert diagnostics

    monkeypatch.setattr(
        exeq,
        "DimodCodegen",
        lambda: SimpleNamespace(
            compile=lambda _ground: SimpleNamespace(diagnostics=[], bqm=good_bqm)
        ),
    )
    out, diagnostics = exeq._compile_qsol_bqm(program_text="p", instance={}, filename="f")
    assert out is good_bqm
    assert diagnostics == []


def test_run_bqm_equivalence_example_success_emits_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = _build_spec(tmp_path)
    bqm = _single_var_bqm()

    monkeypatch.setattr(
        exeq,
        "_parse_args",
        lambda _spec: argparse.Namespace(simulated_annealing=False, num_reads=4),
    )
    monkeypatch.setattr(exeq, "_compile_qsol_bqm", lambda **kwargs: (bqm, []))
    monkeypatch.setattr(
        exeq,
        "check_qsol_program_bqm_equivalence",
        lambda *args, **kwargs: bqme.BQMEquivalenceReport(equivalent=True),
    )
    monkeypatch.setenv("QSOL_EQUIV_SUMMARY_JSON", "1")

    assert exeq.run_bqm_equivalence_example(spec) == 0
    output = capsys.readouterr().out
    assert "__QSOL_EQUIV_SUMMARY__" in output


def test_run_bqm_equivalence_example_runtime_mismatch_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def always_different(lhs: int, rhs: int, atol: float) -> bool:
        _ = lhs, rhs, atol
        return False

    spec = _build_spec(tmp_path, same_fn=always_different)
    bqm = _single_var_bqm()

    monkeypatch.setattr(
        exeq,
        "_parse_args",
        lambda _spec: argparse.Namespace(simulated_annealing=False, num_reads=4),
    )
    monkeypatch.setattr(exeq, "_compile_qsol_bqm", lambda **kwargs: (bqm, []))
    monkeypatch.setattr(
        exeq,
        "check_qsol_program_bqm_equivalence",
        lambda *args, **kwargs: bqme.BQMEquivalenceReport(equivalent=True),
    )

    assert exeq.run_bqm_equivalence_example(spec) == 1


def test_run_bqm_equivalence_example_optional_structural_allows_runtime_skip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def raising_solver(
        bqm: dimod.BinaryQuadraticModel,
        instance: exeq.Mapping[str, object],
        options: exeq.RuntimeSolveOptions,
    ) -> int:
        _ = bqm, instance, options
        raise ValueError("skip")

    spec = _build_spec(tmp_path, require_structural_equivalence=False, solve_fn=raising_solver)
    bqm = _single_var_bqm()
    monkeypatch.setattr(
        exeq,
        "_parse_args",
        lambda _spec: argparse.Namespace(simulated_annealing=False, num_reads=4),
    )
    monkeypatch.setattr(exeq, "_compile_qsol_bqm", lambda **kwargs: (bqm, []))
    monkeypatch.setattr(
        exeq,
        "check_qsol_program_bqm_equivalence",
        lambda *args, **kwargs: bqme.BQMEquivalenceReport(equivalent=False),
    )

    assert exeq.run_bqm_equivalence_example(spec) == 0


def test_run_bqm_equivalence_example_optional_structural_runtime_true_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _build_spec(tmp_path, require_structural_equivalence=False)
    bqm = _single_var_bqm()
    monkeypatch.setattr(
        exeq,
        "_parse_args",
        lambda _spec: argparse.Namespace(simulated_annealing=False, num_reads=4),
    )
    monkeypatch.setattr(exeq, "_compile_qsol_bqm", lambda **kwargs: (bqm, []))
    monkeypatch.setattr(
        exeq,
        "check_qsol_program_bqm_equivalence",
        lambda *args, **kwargs: bqme.BQMEquivalenceReport(equivalent=True),
    )

    assert exeq.run_bqm_equivalence_example(spec) == 0


def test_run_bqm_equivalence_example_compile_failure_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _build_spec(tmp_path)
    monkeypatch.setattr(
        exeq,
        "_parse_args",
        lambda _spec: argparse.Namespace(simulated_annealing=False, num_reads=4),
    )
    monkeypatch.setattr(exeq, "_compile_qsol_bqm", lambda **kwargs: (None, []))
    monkeypatch.setattr(
        exeq,
        "check_qsol_program_bqm_equivalence",
        lambda *args, **kwargs: bqme.BQMEquivalenceReport(equivalent=False),
    )

    assert exeq.run_bqm_equivalence_example(spec) == 1


def test_run_bqm_equivalence_example_qsol_solver_value_error_keeps_success_on_equivalence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    custom_bqm = _single_var_bqm("custom")
    compiled_bqm = _single_var_bqm("qsol1")
    compiled_bqm.add_variable("qsol2", 0.0)

    def solve(
        bqm: dimod.BinaryQuadraticModel,
        instance: exeq.Mapping[str, object],
        options: exeq.RuntimeSolveOptions,
    ) -> int:
        _ = instance, options
        if len(bqm.variables) > 1:
            raise ValueError("skip-qsol-runtime")
        return 1

    spec = _build_spec(tmp_path, solve_fn=solve)
    spec = exeq.EquivalenceExampleSpec[int](
        description=spec.description,
        base_dir=spec.base_dir,
        program_filename=spec.program_filename,
        instance_filename=spec.instance_filename,
        custom_solution_title=spec.custom_solution_title,
        compiled_solution_title=spec.compiled_solution_title,
        build_custom_bqm=lambda _instance: custom_bqm,
        solve_bqm=solve,
        render_solution=spec.render_solution,
        same_runtime_result=spec.same_runtime_result,
        require_structural_equivalence=True,
    )

    monkeypatch.setattr(
        exeq,
        "_parse_args",
        lambda _spec: argparse.Namespace(simulated_annealing=False, num_reads=4),
    )
    monkeypatch.setattr(exeq, "_compile_qsol_bqm", lambda **kwargs: (compiled_bqm, []))
    monkeypatch.setattr(
        exeq,
        "check_qsol_program_bqm_equivalence",
        lambda *args, **kwargs: bqme.BQMEquivalenceReport(equivalent=True),
    )

    assert exeq.run_bqm_equivalence_example(spec) == 0


def test_build_and_print_equivalence_report_covers_all_render_sections() -> None:
    expected = dimod.BinaryQuadraticModel({"a": 0.0, "b": 0.0, "d": 0.0}, {}, 0.0, dimod.BINARY)
    expected.add_interaction("a", "b", 1.0)
    expected.add_interaction("a", "d", 0.5)

    actual = dimod.BinaryQuadraticModel({"a": 1.0, "c": 0.0, "d": 0.0}, {}, 0.0, dimod.SPIN)
    actual.add_interaction("a", "c", 2.0)
    actual.add_interaction("a", "d", 1.5)

    report = bqme._build_equivalence_report(expected, actual, [_diag_warning()], atol=1e-9)
    assert report.equivalent is False
    assert report.missing_variables
    assert report.extra_variables
    assert report.missing_interactions
    assert report.extra_interactions
    assert report.quadratic_bias_mismatches

    stream = io.StringIO()
    console = exeq.Console(file=stream, force_terminal=False, color_system=None, width=200)
    bqme._print_equivalence_report(report, console=console)
    output = stream.getvalue()
    assert "QSOL vs BQM" in output
    assert "Quadratic Bias Mismatches" in output


def test_compile_program_to_bqm_early_return_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    good_bqm = _single_var_bqm()
    lowered = object()
    ground = object()

    monkeypatch.setattr(
        bqme,
        "compile_source",
        lambda _text, options: SimpleNamespace(
            diagnostics=[_diag_error()], lowered_ir_symbolic=None
        ),
    )
    out, _ = bqme._compile_program_to_bqm(program_text="p", instance={}, filename="f")
    assert out is None

    monkeypatch.setattr(
        bqme,
        "compile_source",
        lambda _text, options: SimpleNamespace(diagnostics=[], lowered_ir_symbolic=None),
    )
    out, _ = bqme._compile_program_to_bqm(program_text="p", instance={}, filename="f")
    assert out is None

    monkeypatch.setattr(
        bqme,
        "compile_source",
        lambda _text, options: SimpleNamespace(diagnostics=[], lowered_ir_symbolic=lowered),
    )
    monkeypatch.setattr(
        bqme,
        "instantiate_ir",
        lambda _lowered, _instance: SimpleNamespace(diagnostics=[_diag_error()], ground_ir=ground),
    )
    out, _ = bqme._compile_program_to_bqm(program_text="p", instance={}, filename="f")
    assert out is None

    monkeypatch.setattr(
        bqme,
        "instantiate_ir",
        lambda _lowered, _instance: SimpleNamespace(diagnostics=[], ground_ir=None),
    )
    out, _ = bqme._compile_program_to_bqm(program_text="p", instance={}, filename="f")
    assert out is None

    monkeypatch.setattr(
        bqme,
        "instantiate_ir",
        lambda _lowered, _instance: SimpleNamespace(diagnostics=[], ground_ir=ground),
    )
    monkeypatch.setattr(
        bqme,
        "DimodCodegen",
        lambda: SimpleNamespace(
            compile=lambda _ground: SimpleNamespace(diagnostics=[_diag_error()], bqm=good_bqm)
        ),
    )
    out, _ = bqme._compile_program_to_bqm(program_text="p", instance={}, filename="f")
    assert out is None


def test_build_equivalence_report_expected_none_and_singleton_edge() -> None:
    actual = _single_var_bqm("solo")
    report = bqme._build_equivalence_report(None, actual, [], atol=1e-9)
    assert report.equivalent is False
    assert report.expected_num_variables == 0
    assert bqme._edge_labels(frozenset({"solo"})) == ("solo", "solo")
