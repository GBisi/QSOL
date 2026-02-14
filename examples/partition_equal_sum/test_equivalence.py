from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import dimod
from rich.console import Console
from rich.table import Table

from qsol.util.example_equivalence import (
    EquivalenceExampleSpec,
    RuntimeSolveOptions,
    run_bqm_equivalence_example,
    sample_best_assignment,
)


def build_number_partition_bqm(
    instance: Mapping[str, object],
    *,
    set_name: str = "Items",
    value_param: str = "Value",
    unknown_name: str = "R",
    penalty: float = 1.0,
) -> dimod.BinaryQuadraticModel:
    sets_payload = instance.get("sets")
    params_payload = instance.get("params")
    if not isinstance(sets_payload, dict):
        raise ValueError("instance `sets` must be an object")
    if not isinstance(params_payload, dict):
        raise ValueError("instance `params` must be an object")

    raw_items = sets_payload.get(set_name)
    raw_values = params_payload.get(value_param)
    if not isinstance(raw_items, list):
        raise ValueError(f"instance `sets.{set_name}` must be an array")
    if not isinstance(raw_values, dict):
        raise ValueError(f"instance `params.{value_param}` must be an object")

    items = sorted(str(item) for item in raw_items)
    values: dict[str, float] = {}
    for item in items:
        if item not in raw_values:
            raise ValueError(f"missing value for item `{item}` in `params.{value_param}`")
        value = raw_values[item]
        if not isinstance(value, (int, float)):
            raise ValueError(f"value for `{item}` must be numeric")
        values[item] = float(value)

    total = sum(values[item] for item in items)

    # H = A * (sum_i n_i s_i)^2 with s_i in {-1, +1}
    # Using x_i in {0, 1} with s_i = 2*x_i - 1:
    # H = A * (2*sum_i n_i*x_i - total)^2
    bqm = dimod.BinaryQuadraticModel({}, {}, penalty * (total**2), dimod.BINARY)

    for item in items:
        vi = values[item]
        linear = 4.0 * penalty * vi * (vi - total)
        bqm.add_variable(f"{unknown_name}.has[{item}]", linear)

    for idx, left in enumerate(items):
        for right in items[idx + 1 :]:
            quad = 8.0 * penalty * values[left] * values[right]
            bqm.add_interaction(f"{unknown_name}.has[{left}]", f"{unknown_name}.has[{right}]", quad)

    return bqm


@dataclass(slots=True)
class PartitionSolveResult:
    energy: float
    chosen_items: list[str]
    other_items: list[str]
    chosen_sum: float
    other_sum: float


def _solve_partition_bqm(
    bqm: dimod.BinaryQuadraticModel,
    instance: Mapping[str, object],
    options: RuntimeSolveOptions,
    *,
    unknown_name: str = "R",
) -> PartitionSolveResult:
    best = sample_best_assignment(bqm, options)
    prefix = f"{unknown_name}.has["
    chosen_labels = [
        str(name)
        for name, value in best.sample.items()
        if int(value) == 1 and str(name).startswith(prefix)
    ]
    chosen_items = sorted(label.removeprefix(prefix).removesuffix("]") for label in chosen_labels)

    sets_payload = instance.get("sets")
    params_payload = instance.get("params")
    items = sorted(
        str(item) for item in (sets_payload["Items"] if isinstance(sets_payload, dict) else [])
    )
    values = params_payload["Value"] if isinstance(params_payload, dict) else {}
    chosen_sum = sum(float(values[item]) for item in chosen_items if isinstance(values, dict))
    other_items = sorted(item for item in items if item not in chosen_items)
    other_sum = sum(float(values[item]) for item in other_items if isinstance(values, dict))

    return PartitionSolveResult(
        energy=float(best.energy),
        chosen_items=chosen_items,
        other_items=other_items,
        chosen_sum=chosen_sum,
        other_sum=other_sum,
    )


def _render_solution(console: Console, result: PartitionSolveResult, title: str) -> None:
    table = Table(title=title)
    table.add_column("Set")
    table.add_column("Items")
    table.add_column("Sum")
    table.add_row(
        "R",
        ", ".join(result.chosen_items) if result.chosen_items else "-",
        f"{result.chosen_sum:.6g}",
    )
    table.add_row(
        "Items - R",
        ", ".join(result.other_items) if result.other_items else "-",
        f"{result.other_sum:.6g}",
    )
    table.add_row("Energy", "-", f"{result.energy:.6g}")
    console.print(table)


def _same_runtime_result(lhs: PartitionSolveResult, rhs: PartitionSolveResult, atol: float) -> bool:
    lhs_sums = sorted((lhs.chosen_sum, lhs.other_sum))
    rhs_sums = sorted((rhs.chosen_sum, rhs.other_sum))
    return (
        abs(lhs.energy - rhs.energy) <= atol
        and abs(lhs_sums[0] - rhs_sums[0]) <= atol
        and abs(lhs_sums[1] - rhs_sums[1]) <= atol
    )


def _build_custom_bqm(instance: Mapping[str, object]) -> dimod.BinaryQuadraticModel:
    return build_number_partition_bqm(instance, penalty=1.0)


def main() -> int:
    spec = EquivalenceExampleSpec[PartitionSolveResult](
        description="Compare number partition custom BQM against compiled QSOL output.",
        base_dir=Path(__file__).resolve().parent,
        program_filename="partition_equal_sum.qsol",
        instance_filename="partition_equal_sum.instance.json",
        custom_solution_title="Best Partition From Custom BQM",
        compiled_solution_title="Best Partition From Compiled QSOL BQM",
        build_custom_bqm=_build_custom_bqm,
        solve_bqm=_solve_partition_bqm,
        render_solution=_render_solution,
        same_runtime_result=_same_runtime_result,
    )
    return run_bqm_equivalence_example(spec)


if __name__ == "__main__":
    raise SystemExit(main())
