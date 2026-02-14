from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import dimod
from rich.console import Console
from rich.table import Table

from qsol.util.example_equivalence import (
    EquivalenceExampleSpec,
    RuntimeSolveOptions,
    run_bqm_equivalence_example,
    sample_best_assignment,
)

Var = Hashable
Linear = Mapping[Var, float]
Quadratic = Mapping[tuple[Var, Var], float]


def build_bqm(
    linear: Optional[Linear] = None,
    quadratic: Optional[Quadratic] = None,
    offset: float = 0.0,
    vartype: Union[str, dimod.Vartype] = "BINARY",
    add_interactions: Optional[Iterable[tuple[Var, Var, float]]] = None,
    add_linear: Optional[Iterable[tuple[Var, float]]] = None,
) -> dimod.BinaryQuadraticModel:
    """
    Build a generic BinaryQuadraticModel (BQM) using dimod.

    Args:
        linear: Mapping {v: bias} for linear terms.
        quadratic: Mapping {(u, v): bias} for quadratic terms (u,v order doesn't matter).
        offset: Constant energy offset.
        vartype: "BINARY" or "SPIN" (or dimod.Vartype).
        add_interactions: Optional iterable of (u, v, bias) to add quadratic terms.
        add_linear: Optional iterable of (v, bias) to add linear terms.

    Returns:
        A dimod.BinaryQuadraticModel instance.

    Notes:
        - Duplicate quadratic keys are summed.
        - Self-loops (u == v) are treated as linear in dimod; we route them to linear.
    """
    vt = dimod.as_vartype(vartype)

    bqm = dimod.BinaryQuadraticModel({}, {}, offset, vt)

    if linear:
        for v, b in linear.items():
            bqm.add_variable(v, float(b))

    if quadratic:
        for (u, v), b in quadratic.items():
            if u == v:
                bqm.add_variable(u, float(b))
            else:
                bqm.add_interaction(u, v, float(b))

    if add_linear:
        for v, b in add_linear:
            bqm.add_variable(v, float(b))

    if add_interactions:
        for u, v, b in add_interactions:
            if u == v:
                bqm.add_variable(u, float(b))
            else:
                bqm.add_interaction(u, v, float(b))

    return bqm


def build_generic_bqm_from_instance(
    instance: Mapping[str, object],
    *,
    set_name: str = "Vars",
    linear_param: str = "L",
    quadratic_param: str = "Q",
    offset_param: str = "C",
    unknown_name: str = "X",
) -> dimod.BinaryQuadraticModel:
    sets_payload = instance.get("sets")
    params_payload = instance.get("params")
    if not isinstance(sets_payload, dict):
        raise ValueError("instance `sets` must be an object")
    if not isinstance(params_payload, dict):
        raise ValueError("instance `params` must be an object")

    raw_vars = sets_payload.get(set_name)
    raw_linear = params_payload.get(linear_param, {})
    raw_quadratic = params_payload.get(quadratic_param, {})
    raw_offset = params_payload.get(offset_param, 0.0)

    if not isinstance(raw_vars, list):
        raise ValueError(f"instance `sets.{set_name}` must be an array")
    if not isinstance(raw_linear, dict):
        raise ValueError(f"instance `params.{linear_param}` must be an object")
    if not isinstance(raw_quadratic, dict):
        raise ValueError(f"instance `params.{quadratic_param}` must be an object")
    if isinstance(raw_offset, bool) or not isinstance(raw_offset, (int, float)):
        raise ValueError(f"instance `params.{offset_param}` must be numeric")

    variables = [str(v) for v in raw_vars]
    linear_biases: dict[str, float] = {}
    quadratic_biases: dict[tuple[str, str], float] = {}
    labels = {v: f"{unknown_name}.has[{v}]" for v in variables}

    for v in variables:
        raw_value = raw_linear.get(v, 0.0)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"instance `params.{linear_param}[{v}]` must be numeric")
        linear_biases[labels[v]] = float(raw_value)

    for i in variables:
        row = raw_quadratic.get(i, {})
        if not isinstance(row, dict):
            raise ValueError(f"instance `params.{quadratic_param}[{i}]` must be an object")
        for j in variables:
            raw_value = row.get(j, 0.0)
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValueError(f"instance `params.{quadratic_param}[{i}][{j}]` must be numeric")
            value = float(raw_value)
            if value != 0.0:
                quadratic_biases[(labels[i], labels[j])] = value

    return build_bqm(
        linear=linear_biases,
        quadratic=quadratic_biases,
        offset=float(raw_offset),
        vartype=dimod.BINARY,
    )


@dataclass(slots=True)
class GenericBQMSolveResult:
    energy: float
    chosen_variables: list[str]


def _solve_bqm(
    bqm: dimod.BinaryQuadraticModel,
    _instance: Mapping[str, object],
    options: RuntimeSolveOptions,
    *,
    unknown_name: str = "X",
) -> GenericBQMSolveResult:
    best = sample_best_assignment(bqm, options)
    prefix = f"{unknown_name}.has["
    chosen_labels = [
        str(name)
        for name, value in best.sample.items()
        if int(value) == 1 and str(name).startswith(prefix)
    ]
    chosen_variables = sorted(
        label.removeprefix(prefix).removesuffix("]") for label in chosen_labels
    )
    return GenericBQMSolveResult(
        energy=float(best.energy),
        chosen_variables=chosen_variables,
    )


def _render_solution(console: Console, result: GenericBQMSolveResult, title: str) -> None:
    table = Table(title=title)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row(
        "Chosen (x=1)",
        ", ".join(result.chosen_variables) if result.chosen_variables else "-",
    )
    table.add_row("Energy", f"{result.energy:.6g}")
    console.print(table)


def _same_runtime_result(
    lhs: GenericBQMSolveResult,
    rhs: GenericBQMSolveResult,
    atol: float,
) -> bool:
    return abs(lhs.energy - rhs.energy) <= atol


def main() -> int:
    spec = EquivalenceExampleSpec[GenericBQMSolveResult](
        description="Compare a custom generic BQM against compiled QSOL output.",
        base_dir=Path(__file__).resolve().parent,
        program_filename="generic_bqm.qsol",
        instance_filename="generic_bqm.instance.json",
        custom_solution_title="Best Assignment From Custom BQM",
        compiled_solution_title="Best Assignment From Compiled QSOL BQM",
        build_custom_bqm=build_generic_bqm_from_instance,
        solve_bqm=_solve_bqm,
        render_solution=_render_solution,
        same_runtime_result=_same_runtime_result,
        runtime_pass_message="Runtime check passed: both models return the same energy.",
        runtime_fail_message="Runtime check failed: model energies differ.",
    )
    return run_bqm_equivalence_example(spec)


if __name__ == "__main__":
    raise SystemExit(main())
