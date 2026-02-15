from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from itertools import combinations
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


def graph_partition_bqm(
    V: list[Hashable],
    E: list[tuple[Hashable, Hashable]],
    A: float = 1.0,
    B: float = 1.0,
) -> dimod.BinaryQuadraticModel:
    """
    Build the SPIN BQM:

        H = A (sum_i s_i)^2  +  B * sum_(u,v in E) (1 - s_u s_v)/2

    with s_i in {-1, +1}.
    """
    bqm = dimod.BinaryQuadraticModel({}, {}, 0.0, vartype=dimod.SPIN)

    n = len(V)
    bqm.offset += A * n
    for u, v in combinations(V, 2):
        bqm.add_quadratic(u, v, 2.0 * A)

    bqm.offset += (B / 2.0) * len(E)
    for u, v in E:
        bqm.add_quadratic(u, v, -B / 2.0)

    return bqm


def build_min_bisection_bqm(
    instance: Mapping[str, object],
    *,
    set_vertices: str = "V",
    set_edges: str = "E",
    endpoint_u_param: str = "U",
    endpoint_w_param: str = "W",
    unknown_name: str = "Side",
    penalty_param: str = "PenaltyA",
    edge_weight_param: str = "WeightB",
) -> dimod.BinaryQuadraticModel:
    sets_payload = instance.get("sets")
    params_payload = instance.get("params")
    if not isinstance(sets_payload, dict):
        raise ValueError("instance `sets` must be an object")
    if not isinstance(params_payload, dict):
        raise ValueError("instance `params` must be an object")

    raw_vertices = sets_payload.get(set_vertices)
    raw_edges = sets_payload.get(set_edges)
    raw_u = params_payload.get(endpoint_u_param)
    raw_w = params_payload.get(endpoint_w_param)

    if not isinstance(raw_vertices, list):
        raise ValueError(f"instance `sets.{set_vertices}` must be an array")
    if not isinstance(raw_edges, list):
        raise ValueError(f"instance `sets.{set_edges}` must be an array")
    if not isinstance(raw_u, dict):
        raise ValueError(f"instance `params.{endpoint_u_param}` must be an object")
    if not isinstance(raw_w, dict):
        raise ValueError(f"instance `params.{endpoint_w_param}` must be an object")

    vertices = [str(v) for v in raw_vertices]
    if len(set(vertices)) != len(vertices):
        raise ValueError(f"instance `sets.{set_vertices}` contains duplicates")
    vertex_labels = {v: f"{unknown_name}.has[{v}]" for v in vertices}

    u_lookup = {str(k): v for k, v in raw_u.items()}
    w_lookup = {str(k): v for k, v in raw_w.items()}
    edge_ids = [str(e) for e in raw_edges]

    lifted_edges: list[tuple[str, str]] = []
    for edge_id in edge_ids:
        if edge_id not in u_lookup:
            raise ValueError(f"missing `{endpoint_u_param}[{edge_id}]`")
        if edge_id not in w_lookup:
            raise ValueError(f"missing `{endpoint_w_param}[{edge_id}]`")

        u = str(u_lookup[edge_id])
        v = str(w_lookup[edge_id])
        if u not in vertex_labels:
            raise ValueError(
                f"`{endpoint_u_param}[{edge_id}]` endpoint `{u}` is not in `{set_vertices}`"
            )
        if v not in vertex_labels:
            raise ValueError(
                f"`{endpoint_w_param}[{edge_id}]` endpoint `{v}` is not in `{set_vertices}`"
            )
        lifted_edges.append((vertex_labels[u], vertex_labels[v]))

    penalty_a = _read_numeric_param(params_payload, penalty_param, default=1.0)
    edge_weight_b = _read_numeric_param(params_payload, edge_weight_param, default=1.0)

    spin_bqm = graph_partition_bqm(
        [vertex_labels[v] for v in vertices],
        lifted_edges,
        A=penalty_a,
        B=edge_weight_b,
    )
    # QSOL backend emits BINARY BQMs; compare in that vartype.
    return spin_bqm.change_vartype(dimod.BINARY, inplace=False)


def _read_numeric_param(params: Mapping[str, object], key: str, *, default: float) -> float:
    if key not in params:
        return default
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"instance `params.{key}` must be numeric")
    return float(value)


@dataclass(slots=True)
class MinBisectionSolveResult:
    energy: float
    chosen_vertices: list[str]
    other_vertices: list[str]
    cut_edges: list[str]
    cut_size: int


def _solve_min_bisection_bqm(
    bqm: dimod.BinaryQuadraticModel,
    instance: Mapping[str, object],
    options: RuntimeSolveOptions,
    *,
    unknown_name: str = "Side",
) -> MinBisectionSolveResult:
    best = sample_best_assignment(bqm, options)

    active_unknown_name = unknown_name
    default_prefix = f"{unknown_name}.has["
    if not any(str(name).startswith(default_prefix) for name in best.sample):
        inferred = sorted(
            {label.split(".has[", 1)[0] for label in map(str, best.sample) if ".has[" in label}
        )
        if inferred:
            active_unknown_name = inferred[0]

    prefix = f"{active_unknown_name}.has["
    chosen_labels = [
        str(name)
        for name, value in best.sample.items()
        if int(value) == 1 and str(name).startswith(prefix)
    ]
    chosen_vertices = sorted(
        label.removeprefix(prefix).removesuffix("]") for label in chosen_labels
    )

    sets_payload = instance.get("sets")
    params_payload = instance.get("params")
    all_vertices = (
        [str(v) for v in sets_payload.get("V", [])]
        if isinstance(sets_payload, dict) and isinstance(sets_payload.get("V"), list)
        else []
    )
    other_vertices = sorted(v for v in all_vertices if v not in chosen_vertices)

    edge_ids = (
        [str(e) for e in sets_payload.get("E", [])]
        if isinstance(sets_payload, dict) and isinstance(sets_payload.get("E"), list)
        else []
    )
    u_map = params_payload.get("U", {}) if isinstance(params_payload, dict) else {}
    w_map = params_payload.get("W", {}) if isinstance(params_payload, dict) else {}
    cut_edges: list[str] = []
    side_a = set(chosen_vertices)
    if isinstance(u_map, dict) and isinstance(w_map, dict):
        for edge_id in edge_ids:
            if edge_id not in u_map or edge_id not in w_map:
                continue
            u = str(u_map[edge_id])
            v = str(w_map[edge_id])
            if (u in side_a) != (v in side_a):
                cut_edges.append(edge_id)

    return MinBisectionSolveResult(
        energy=float(best.energy),
        chosen_vertices=chosen_vertices,
        other_vertices=other_vertices,
        cut_edges=sorted(cut_edges),
        cut_size=len(cut_edges),
    )


def _render_solution(console: Console, result: MinBisectionSolveResult, title: str) -> None:
    table = Table(title=title)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("A", ", ".join(result.chosen_vertices) if result.chosen_vertices else "-")
    table.add_row("V - A", ", ".join(result.other_vertices) if result.other_vertices else "-")
    table.add_row("Cut Edges", ", ".join(result.cut_edges) if result.cut_edges else "-")
    table.add_row("Cut Size", str(result.cut_size))
    table.add_row("Energy", f"{result.energy:.6g}")
    console.print(table)


def _same_runtime_result(
    lhs: MinBisectionSolveResult, rhs: MinBisectionSolveResult, atol: float
) -> bool:
    _ = atol
    lhs_balanced = len(lhs.chosen_vertices) == len(lhs.other_vertices)
    rhs_balanced = len(rhs.chosen_vertices) == len(rhs.other_vertices)
    return lhs_balanced and rhs_balanced and lhs.cut_size == rhs.cut_size


def main() -> int:
    spec = EquivalenceExampleSpec[MinBisectionSolveResult](
        description="Compare min-bisection custom BQM against compiled QSOL output.",
        base_dir=Path(__file__).resolve().parent,
        program_filename="min_bisection.qsol",
        config_filename="min_bisection.qsol.toml",
        custom_solution_title="Best Partition From Custom BQM",
        compiled_solution_title="Best Partition From Compiled QSOL BQM",
        build_custom_bqm=lambda instance: build_min_bisection_bqm(instance, unknown_name="Side"),
        solve_bqm=_solve_min_bisection_bqm,
        render_solution=_render_solution,
        same_runtime_result=_same_runtime_result,
        structural_mismatch_message=(
            "Informational: custom and compiled BQMs differ structurally "
            "(runtime result is the acceptance criterion for this example)."
        ),
        require_structural_equivalence=False,
    )
    return run_bqm_equivalence_example(spec)


if __name__ == "__main__":
    raise SystemExit(main())
