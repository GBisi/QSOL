from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from qsol.lower import ir


@dataclass(frozen=True, slots=True)
class EstimateReport:
    problem: str
    sets: dict[str, dict[str, object]]
    relations: dict[str, dict[str, object]]
    structures: dict[str, dict[str, object]]
    decision_variables: dict[str, dict[str, object]]
    decisions: dict[str, int]
    constraints: dict[str, int]
    expressions: dict[str, int]
    backend: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "problem": self.problem,
            "sets": self.sets,
            "relations": self.relations,
            "structures": self.structures,
            "decision_variables": self.decision_variables,
            "decisions": self.decisions,
            "constraints": self.constraints,
            "expressions": self.expressions,
            "backend": self.backend,
        }


def estimate_ground_ir(
    ground: ir.GroundIR, *, backend_status: str = "not_run"
) -> list[EstimateReport]:
    reports: list[EstimateReport] = []
    for problem in ground.problems:
        set_report: dict[str, dict[str, object]] = {
            name: {
                "size": len(values),
                "derived": _is_derived_set(problem, name),
                "source": problem.derived_sets.get(name),
            }
            for name, values in sorted(problem.set_values.items())
        }
        relation_report: dict[str, dict[str, object]] = {
            name: {
                "size": len(values),
                "arity": _relation_arity(values),
                "derived": _is_derived_relation(problem, name),
                "source": problem.derived_relations.get(name),
            }
            for name, values in sorted(problem.relation_values.items())
        }
        decision_report: dict[str, dict[str, object]] = {}
        cqm_binary = 0
        cqm_integer = 0
        auxiliary_binary = 0
        auxiliary_integer = 0
        mapping_exactly_one = 0

        for find in problem.finds:
            is_auxiliary = find.name.startswith("__qsol_")
            if isinstance(find.decision_type, ir.KUnknownDecisionType):
                kind = find.decision_type.unknown_type.kind
                if kind == "Subset":
                    set_name = find.decision_type.unknown_type.args[0]
                    count = len(problem.set_values.get(set_name, []))
                    cqm_binary += count
                    if is_auxiliary:
                        auxiliary_binary += count
                    decision_report[find.name] = {
                        "kind": "Subset",
                        "binary_variables": count,
                    }
                elif kind == "Mapping":
                    dom_name, cod_name = find.decision_type.unknown_type.args
                    dom_count = len(problem.set_values.get(dom_name, []))
                    cod_count = len(problem.set_values.get(cod_name, []))
                    count = dom_count * cod_count
                    cqm_binary += count
                    if is_auxiliary:
                        auxiliary_binary += count
                    mapping_exactly_one += dom_count
                    decision_report[find.name] = {
                        "kind": "Mapping",
                        "binary_variables": count,
                        "exactly_one_constraints": dom_count,
                    }
                else:
                    decision_report[find.name] = {"kind": kind, "supported": False}
                continue

            indexed_count = _indexed_count(problem, find.indices)
            if isinstance(find.decision_type, ir.KBoolDecisionType):
                cqm_binary += indexed_count
                if is_auxiliary:
                    auxiliary_binary += indexed_count
                decision_report[find.name] = {
                    "kind": "Bool",
                    "instances": indexed_count,
                    "domain_size": 2,
                }
            elif isinstance(find.decision_type, ir.KIntDecisionType):
                lo, hi = _int_bounds(find.decision_type)
                domain_size = None if lo is None or hi is None else hi - lo + 1
                cqm_integer += indexed_count
                if is_auxiliary:
                    auxiliary_integer += indexed_count
                decision_report[find.name] = {
                    "kind": "Int",
                    "instances": indexed_count,
                    "lo": lo,
                    "hi": hi,
                    "domain_size": domain_size,
                }

        reports.append(
            EstimateReport(
                problem=str(problem.name),
                sets=set_report,
                relations=relation_report,
                structures=problem.structures,
                decision_variables=decision_report,
                decisions={
                    "binary": cqm_binary,
                    "integer": cqm_integer,
                    "auxiliary_binary": auxiliary_binary,
                    "auxiliary_integer": auxiliary_integer,
                },
                constraints={
                    "explicit": len(problem.constraints),
                    "mapping_exactly_one": mapping_exactly_one,
                },
                expressions={
                    "max_polynomial_degree_before_reduction": 0,
                    "max_polynomial_degree_after_reduction": 0,
                },
                backend={
                    "status": backend_status,
                    "cqm_binary_variables": cqm_binary,
                    "cqm_integer_variables": cqm_integer,
                    "warnings": _estimate_warnings(set_report, relation_report),
                },
            )
        )
    return reports


def _is_derived_set(problem: ir.GroundProblem, name: str) -> bool:
    return name in problem.derived_sets


def _is_derived_relation(problem: ir.GroundProblem, name: str) -> bool:
    return name in problem.derived_relations


def _relation_arity(values: tuple[tuple[object, ...], ...]) -> int | None:
    if not values:
        return None
    return len(values[0])


def _indexed_count(problem: ir.GroundProblem, indices: tuple[str, ...]) -> int:
    if not indices:
        return 1
    count = 0
    domains = [
        problem.relation_values.get(index_name, problem.set_values.get(index_name, []))
        for index_name in indices
    ]
    for _values in product(*domains):
        count += 1
    return count


def _int_bounds(decision_type: ir.KIntDecisionType) -> tuple[int | None, int | None]:
    if not isinstance(decision_type.lo, ir.KNumLit) or not isinstance(decision_type.hi, ir.KNumLit):
        return None, None
    return int(decision_type.lo.value), int(decision_type.hi.value)


def _estimate_warnings(
    sets: dict[str, dict[str, object]],
    relations: dict[str, dict[str, object]],
) -> list[str]:
    warnings: list[str] = []
    for name, report in relations.items():
        size = report.get("size")
        if isinstance(size, int) and size > 10_000:
            warnings.append(f"relation `{name}` has {size} tuples; grounding may be large")
    for name, report in sets.items():
        size = report.get("size")
        if isinstance(size, int) and size > 10_000:
            warnings.append(f"set `{name}` has {size} elements; grounding may be large")
    return warnings
