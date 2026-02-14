from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Protocol, TypeVar, cast

import dimod
from rich.console import Console

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.instance import instantiate_ir
from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source
from qsol.diag.diagnostic import Diagnostic
from qsol.util.bqm_equivalence import BQMEquivalenceReport, check_qsol_program_bqm_equivalence

SolveResultT = TypeVar("SolveResultT")


class _SampleLike(Protocol):
    sample: Mapping[object, int | float]
    energy: float


class _SampleSetLike(Protocol):
    first: _SampleLike


class _SimulatedAnnealingSamplerLike(Protocol):
    def sample(
        self,
        bqm: dimod.BinaryQuadraticModel,
        *,
        num_reads: int,
    ) -> _SampleSetLike: ...


class _ExactSolverLike(Protocol):
    def sample(self, bqm: dimod.BinaryQuadraticModel) -> _SampleSetLike: ...


@dataclass(slots=True)
class RuntimeSolveOptions:
    use_simulated_annealing: bool = False
    num_reads: int = 100
    max_exact_variables: int = 24


@dataclass(slots=True)
class EquivalenceExampleSpec(Generic[SolveResultT]):
    description: str
    base_dir: Path
    program_filename: str
    instance_filename: str
    custom_solution_title: str
    compiled_solution_title: str
    build_custom_bqm: Callable[[Mapping[str, object]], dimod.BinaryQuadraticModel]
    solve_bqm: Callable[
        [dimod.BinaryQuadraticModel, Mapping[str, object], RuntimeSolveOptions],
        SolveResultT,
    ]
    render_solution: Callable[[Console, SolveResultT, str], None]
    same_runtime_result: Callable[[SolveResultT, SolveResultT, float], bool]
    atol: float = 1e-9
    default_num_reads: int = 100
    default_max_exact_variables: int = 24
    runtime_pass_message: str = "Runtime check passed: both models return the same result."
    runtime_fail_message: str = "Runtime check failed: model results differ."
    equivalence_pass_message: str = "Equivalent: custom and compiled QSOL BQMs match."
    equivalence_pass_skipped_runtime_message: str = (
        "Equivalent: custom and compiled QSOL BQMs match (runtime check skipped)."
    )
    runtime_only_pass_message: str = (
        "Runtime-equivalent: solutions match (structural BQM differences ignored for this example)."
    )
    structural_mismatch_message: str = "Not equivalent: custom BQM differs from compiled QSOL BQM."
    runtime_mismatch_message: str = "Not equivalent: runtime solutions are not the same."
    require_structural_equivalence: bool = True


def sample_best_assignment(
    bqm: dimod.BinaryQuadraticModel,
    options: RuntimeSolveOptions,
) -> _SampleLike:
    if options.use_simulated_annealing:
        sa_factory = cast(
            Callable[[], _SimulatedAnnealingSamplerLike], dimod.SimulatedAnnealingSampler
        )
        sampler = sa_factory()
        return sampler.sample(bqm, num_reads=options.num_reads).first

    if len(bqm.variables) > options.max_exact_variables:
        raise ValueError(
            f"ExactSolver supports only small models in this check; got {len(bqm.variables)} vars"
        )
    exact_factory = cast(Callable[[], _ExactSolverLike], dimod.ExactSolver)
    solver = exact_factory()
    return solver.sample(bqm).first


def run_bqm_equivalence_example(spec: EquivalenceExampleSpec[SolveResultT]) -> int:
    args = _parse_args(spec)
    runtime_options = RuntimeSolveOptions(
        use_simulated_annealing=args.simulated_annealing,
        num_reads=args.num_reads,
        max_exact_variables=spec.default_max_exact_variables,
    )
    console = Console()
    qsol_path = spec.base_dir / spec.program_filename
    instance_path = spec.base_dir / spec.instance_filename
    program_text = qsol_path.read_text(encoding="utf-8")
    instance = _read_json(instance_path)

    custom_bqm = spec.build_custom_bqm(instance)
    custom_solution: SolveResultT | None = None
    try:
        custom_solution = spec.solve_bqm(custom_bqm, instance, runtime_options)
    except ValueError as exc:
        console.print(f"[bold yellow]Runtime check skipped: {exc}[/bold yellow]")
    else:
        spec.render_solution(console, custom_solution, spec.custom_solution_title)

    qsol_bqm, _ = _compile_qsol_bqm(
        program_text=program_text,
        instance=instance,
        filename=str(qsol_path),
    )

    runtime_result_matches: bool | None = None
    if qsol_bqm is None:
        console.print(
            "[bold yellow]Runtime check skipped: failed to compile QSOL model for execution.[/bold yellow]"
        )
    elif custom_solution is not None:
        try:
            qsol_solution = spec.solve_bqm(qsol_bqm, instance, runtime_options)
        except ValueError as exc:
            console.print(f"[bold yellow]Runtime check skipped: {exc}[/bold yellow]")
        else:
            spec.render_solution(console, qsol_solution, spec.compiled_solution_title)
            runtime_result_matches = spec.same_runtime_result(
                custom_solution,
                qsol_solution,
                spec.atol,
            )
            if runtime_result_matches:
                console.print(f"[bold green]{spec.runtime_pass_message}[/bold green]")
            else:
                console.print(f"[bold red]{spec.runtime_fail_message}[/bold red]")

    report = check_qsol_program_bqm_equivalence(
        program_text,
        custom_bqm,
        instance=instance,
        filename=str(qsol_path),
        atol=spec.atol,
        console=console,
    )

    if not report.equivalent and not spec.require_structural_equivalence:
        console.print(f"[bold yellow]{spec.structural_mismatch_message}[/bold yellow]")

    exit_code = 1
    if runtime_result_matches is False:
        console.print(f"[bold red]{spec.runtime_mismatch_message}[/bold red]")
    elif not spec.require_structural_equivalence:
        if runtime_result_matches is True:
            console.print(f"[bold green]{spec.runtime_only_pass_message}[/bold green]")
        else:
            console.print(
                f"[bold green]{spec.equivalence_pass_skipped_runtime_message}[/bold green]"
            )
        exit_code = 0
    elif report.equivalent:
        if runtime_result_matches is True:
            console.print(f"[bold green]{spec.equivalence_pass_message}[/bold green]")
        else:
            console.print(
                f"[bold green]{spec.equivalence_pass_skipped_runtime_message}[/bold green]"
            )
        exit_code = 0
    else:
        if not report.equivalent:
            console.print(f"[bold red]{spec.structural_mismatch_message}[/bold red]")

    _emit_suite_summary(
        example=spec.base_dir.name,
        report=report,
        runtime_result_matches=runtime_result_matches,
        require_structural_equivalence=spec.require_structural_equivalence,
        exit_code=exit_code,
    )
    return exit_code


def _emit_suite_summary(
    *,
    example: str,
    report: BQMEquivalenceReport,
    runtime_result_matches: bool | None,
    require_structural_equivalence: bool,
    exit_code: int,
) -> None:
    if os.environ.get("QSOL_EQUIV_SUMMARY_JSON") != "1":
        return
    # Keep this as a single line so the suite runner can parse it reliably.
    payload = {
        "example": example,
        "exit_code": exit_code,
        "structural_equivalent": bool(report.equivalent),
        "result_equivalent": runtime_result_matches,
        "require_structural_equivalence": require_structural_equivalence,
        "expected_num_variables": int(report.expected_num_variables),
        "actual_num_variables": int(report.actual_num_variables),
        "expected_num_interactions": int(report.expected_num_interactions),
        "actual_num_interactions": int(report.actual_num_interactions),
        "offset_expected": float(report.offset_expected),
        "offset_actual": float(report.offset_actual),
        "offset_delta": float(report.offset_delta),
    }
    print(f"__QSOL_EQUIV_SUMMARY__{json.dumps(payload, sort_keys=True)}")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _parse_args(spec: EquivalenceExampleSpec[SolveResultT]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=spec.description)
    parser.add_argument(
        "--simulated-annealing",
        action="store_true",
        help="Use dimod SimulatedAnnealingSampler for runtime solve checks.",
    )
    parser.add_argument(
        "--num-reads",
        type=_positive_int,
        default=spec.default_num_reads,
        help=f"Number of reads for simulated annealing (default: {spec.default_num_reads}).",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _compile_qsol_bqm(
    *,
    program_text: str,
    instance: Mapping[str, object],
    filename: str,
) -> tuple[dimod.BinaryQuadraticModel | None, list[Diagnostic]]:
    unit = compile_source(program_text, options=CompileOptions(filename=filename))
    diagnostics = list(unit.diagnostics)
    if any(diag.is_error for diag in diagnostics) or unit.lowered_ir_symbolic is None:
        return None, diagnostics

    inst = instantiate_ir(unit.lowered_ir_symbolic, instance)
    diagnostics.extend(inst.diagnostics)
    if any(diag.is_error for diag in diagnostics) or inst.ground_ir is None:
        return None, diagnostics

    codegen = DimodCodegen().compile(inst.ground_ir)
    diagnostics.extend(codegen.diagnostics)
    if any(diag.is_error for diag in diagnostics):
        return None, diagnostics
    return codegen.bqm, diagnostics
