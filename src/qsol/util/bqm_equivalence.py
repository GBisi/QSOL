from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field

import dimod
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.instance import instantiate_ir
from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source
from qsol.diag.diagnostic import Diagnostic

EdgeKey = frozenset[Hashable]


@dataclass(slots=True)
class LinearBiasMismatch:
    variable: str
    expected: float
    actual: float


@dataclass(slots=True)
class QuadraticBiasMismatch:
    u: str
    v: str
    expected: float
    actual: float


@dataclass(slots=True)
class BQMEquivalenceReport:
    equivalent: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    vartype_expected: str = "<unavailable>"
    vartype_actual: str = "<unavailable>"
    offset_expected: float = 0.0
    offset_actual: float = 0.0
    offset_delta: float = 0.0
    missing_variables: list[str] = field(default_factory=list)
    extra_variables: list[str] = field(default_factory=list)
    linear_bias_mismatches: list[LinearBiasMismatch] = field(default_factory=list)
    missing_interactions: list[tuple[str, str]] = field(default_factory=list)
    extra_interactions: list[tuple[str, str]] = field(default_factory=list)
    quadratic_bias_mismatches: list[QuadraticBiasMismatch] = field(default_factory=list)
    expected_num_variables: int = 0
    actual_num_variables: int = 0
    expected_num_interactions: int = 0
    actual_num_interactions: int = 0


def check_qsol_program_bqm_equivalence(
    program_text: str,
    bqm: dimod.BinaryQuadraticModel,
    *,
    instance: Mapping[str, object] | None = None,
    filename: str = "<input>",
    atol: float = 1e-9,
    console: Console | None = None,
) -> BQMEquivalenceReport:
    compiled_bqm, diagnostics = _compile_program_to_bqm(
        program_text=program_text,
        instance=instance or {},
        filename=filename,
    )
    report = _build_equivalence_report(compiled_bqm, bqm, diagnostics, atol=atol)
    _print_equivalence_report(report, console=console)
    return report


def _compile_program_to_bqm(
    *,
    program_text: str,
    instance: Mapping[str, object],
    filename: str,
) -> tuple[dimod.BinaryQuadraticModel | None, list[Diagnostic]]:
    unit = compile_source(program_text, options=CompileOptions(filename=filename))
    diagnostics = list(unit.diagnostics)
    if any(diag.is_error for diag in diagnostics):
        return None, diagnostics
    if unit.lowered_ir_symbolic is None:
        return None, diagnostics

    inst = instantiate_ir(unit.lowered_ir_symbolic, instance)
    diagnostics.extend(inst.diagnostics)
    if any(diag.is_error for diag in diagnostics):
        return None, diagnostics
    if inst.ground_ir is None:
        return None, diagnostics

    codegen = DimodCodegen().compile(inst.ground_ir)
    diagnostics.extend(codegen.diagnostics)
    if any(diag.is_error for diag in diagnostics):
        return None, diagnostics
    return codegen.bqm, diagnostics


def _build_equivalence_report(
    expected: dimod.BinaryQuadraticModel | None,
    actual: dimod.BinaryQuadraticModel,
    diagnostics: list[Diagnostic],
    *,
    atol: float,
) -> BQMEquivalenceReport:
    report = BQMEquivalenceReport(
        equivalent=False,
        diagnostics=diagnostics,
        vartype_actual=actual.vartype.name,
        offset_actual=float(actual.offset),
        actual_num_variables=int(len(actual.variables)),
        actual_num_interactions=int(len(actual.quadratic)),
    )
    if expected is None:
        return report

    report.vartype_expected = expected.vartype.name
    report.offset_expected = float(expected.offset)
    report.offset_delta = report.offset_actual - report.offset_expected
    report.expected_num_variables = int(len(expected.variables))
    report.expected_num_interactions = int(len(expected.quadratic))

    expected_vars = _variable_set(expected)
    actual_vars = _variable_set(actual)

    report.missing_variables = _sorted_labels(expected_vars - actual_vars)
    report.extra_variables = _sorted_labels(actual_vars - expected_vars)

    for var in sorted(expected_vars & actual_vars, key=_variable_sort_key):
        expected_bias = float(expected.get_linear(var))
        actual_bias = float(actual.get_linear(var))
        if abs(expected_bias - actual_bias) > atol:
            report.linear_bias_mismatches.append(
                LinearBiasMismatch(
                    variable=_label(var),
                    expected=expected_bias,
                    actual=actual_bias,
                )
            )

    expected_quadratic = _quadratic_map(expected)
    actual_quadratic = _quadratic_map(actual)
    expected_edges = set(expected_quadratic)
    actual_edges = set(actual_quadratic)

    report.missing_interactions = [
        _edge_labels(edge) for edge in sorted(expected_edges - actual_edges, key=_edge_sort_key)
    ]
    report.extra_interactions = [
        _edge_labels(edge) for edge in sorted(actual_edges - expected_edges, key=_edge_sort_key)
    ]

    for edge in sorted(expected_edges & actual_edges, key=_edge_sort_key):
        expected_bias = expected_quadratic[edge]
        actual_bias = actual_quadratic[edge]
        if abs(expected_bias - actual_bias) > atol:
            u, v = _edge_labels(edge)
            report.quadratic_bias_mismatches.append(
                QuadraticBiasMismatch(
                    u=u,
                    v=v,
                    expected=expected_bias,
                    actual=actual_bias,
                )
            )

    has_errors = any(diag.is_error for diag in report.diagnostics)
    report.equivalent = (
        not has_errors
        and report.vartype_expected == report.vartype_actual
        and abs(report.offset_delta) <= atol
        and not report.missing_variables
        and not report.extra_variables
        and not report.linear_bias_mismatches
        and not report.missing_interactions
        and not report.extra_interactions
        and not report.quadratic_bias_mismatches
    )
    return report


def _print_equivalence_report(report: BQMEquivalenceReport, *, console: Console | None) -> None:
    active_console = console or Console()
    status = "Equivalent" if report.equivalent else "Not Equivalent"
    border_style = "green" if report.equivalent else "red"
    active_console.print(
        Panel(
            f"{status}\nExpected vartype: {report.vartype_expected}\nActual vartype: {report.vartype_actual}",
            title="QSOL vs BQM",
            border_style=border_style,
        )
    )

    summary = Table(title="Model Summary")
    summary.add_column("Field")
    summary.add_column("Expected")
    summary.add_column("Actual")
    summary.add_row(
        "Variables", str(report.expected_num_variables), str(report.actual_num_variables)
    )
    summary.add_row(
        "Interactions",
        str(report.expected_num_interactions),
        str(report.actual_num_interactions),
    )
    summary.add_row("Offset", f"{report.offset_expected:.12g}", f"{report.offset_actual:.12g}")
    summary.add_row("Offset Delta", "-", f"{report.offset_delta:.12g}")
    active_console.print(summary)

    if report.diagnostics:
        diag_table = Table(title="Compilation Diagnostics")
        diag_table.add_column("Severity")
        diag_table.add_column("Code")
        diag_table.add_column("Location")
        diag_table.add_column("Message")
        for diag in report.diagnostics:
            diag_table.add_row(
                diag.severity.value,
                diag.code,
                f"{diag.span.filename}:{diag.span.line}:{diag.span.col}",
                diag.message,
            )
        active_console.print(diag_table)

    if report.vartype_expected != report.vartype_actual:
        mismatch = Table(title="Vartype Mismatch")
        mismatch.add_column("Expected")
        mismatch.add_column("Actual")
        mismatch.add_row(report.vartype_expected, report.vartype_actual)
        active_console.print(mismatch)

    if report.missing_variables:
        table = Table(title="Missing Variables (In Provided BQM)")
        table.add_column("Variable")
        for name in report.missing_variables:
            table.add_row(name)
        active_console.print(table)

    if report.extra_variables:
        table = Table(title="Extra Variables (Not In QSOL BQM)")
        table.add_column("Variable")
        for name in report.extra_variables:
            table.add_row(name)
        active_console.print(table)

    if report.linear_bias_mismatches:
        table = Table(title="Linear Bias Mismatches")
        table.add_column("Variable")
        table.add_column("Expected")
        table.add_column("Actual")
        table.add_column("Delta")
        for entry in report.linear_bias_mismatches:
            delta = entry.actual - entry.expected
            table.add_row(
                entry.variable,
                f"{entry.expected:.12g}",
                f"{entry.actual:.12g}",
                f"{delta:.12g}",
            )
        active_console.print(table)

    if report.missing_interactions:
        table = Table(title="Missing Interactions (In Provided BQM)")
        table.add_column("u")
        table.add_column("v")
        for u, v in report.missing_interactions:
            table.add_row(u, v)
        active_console.print(table)

    if report.extra_interactions:
        table = Table(title="Extra Interactions (Not In QSOL BQM)")
        table.add_column("u")
        table.add_column("v")
        for u, v in report.extra_interactions:
            table.add_row(u, v)
        active_console.print(table)

    if report.quadratic_bias_mismatches:
        table = Table(title="Quadratic Bias Mismatches")
        table.add_column("u")
        table.add_column("v")
        table.add_column("Expected")
        table.add_column("Actual")
        table.add_column("Delta")
        for quad_entry in report.quadratic_bias_mismatches:
            delta = quad_entry.actual - quad_entry.expected
            table.add_row(
                quad_entry.u,
                quad_entry.v,
                f"{quad_entry.expected:.12g}",
                f"{quad_entry.actual:.12g}",
                f"{delta:.12g}",
            )
        active_console.print(table)


def _variable_set(bqm: dimod.BinaryQuadraticModel) -> set[Hashable]:
    return set(bqm.variables)


def _quadratic_map(bqm: dimod.BinaryQuadraticModel) -> dict[EdgeKey, float]:
    out: dict[EdgeKey, float] = {}
    for (u, v), bias in bqm.quadratic.items():
        out[frozenset((u, v))] = float(bias)
    return out


def _sorted_labels(values: set[Hashable]) -> list[str]:
    return [_label(v) for v in sorted(values, key=_variable_sort_key)]


def _label(value: Hashable) -> str:
    return str(value)


def _variable_sort_key(value: Hashable) -> tuple[str, str]:
    return (type(value).__name__, _label(value))


def _edge_labels(edge: EdgeKey) -> tuple[str, str]:
    labels = sorted(_label(value) for value in edge)
    if len(labels) == 1:
        return labels[0], labels[0]
    return labels[0], labels[1]


def _edge_sort_key(edge: EdgeKey) -> tuple[str, str]:
    return _edge_labels(edge)
