from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, product

from qsol.backend.graph_encoding import GraphData
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
        graph_matching_degree = 0
        graph_maximal_matching = 0
        graph_spanning_tree_edge_count = 0
        graph_spanning_tree_connectivity = 0
        graph_forest_acyclic = 0
        graph_steiner_terminal = 0
        graph_steiner_edge_endpoint = 0
        graph_steiner_tree_count = 0
        graph_steiner_flow_capacity = 0
        graph_steiner_flow_balance = 0
        graph_hamiltonian_assignment = 0
        graph_hamiltonian_adjacency = 0
        graph_hamiltonian_uses_link = 0

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
                elif kind in {
                    "Matching",
                    "MaximalMatching",
                    "SpanningTree",
                    "Forest",
                    "SteinerTree",
                }:
                    graph_name = find.decision_type.unknown_type.args[0]
                    graph = GraphData.from_ground_problem(problem, graph_name, find.span, [])
                    edge_count = 0 if graph is None else len(graph.edges)
                    vertex_count = 0 if graph is None else len(graph.vertices)
                    degree_constraints = 0
                    maximality_constraints = 0
                    spanning_edge_count_constraints = 0
                    connectivity_constraints = 0
                    forest_constraints = 0
                    steiner_terminal_constraints = 0
                    steiner_edge_endpoint_constraints = 0
                    steiner_tree_count_constraints = 0
                    steiner_flow_capacity_constraints = 0
                    steiner_flow_balance_constraints = 0
                    if graph is not None:
                        degree_constraints = sum(
                            1 for vertex in graph.vertices if len(graph.incident_edges(vertex)) > 1
                        )
                        if kind == "MaximalMatching":
                            maximality_constraints = edge_count
                        elif kind == "SpanningTree":
                            spanning_edge_count_constraints = 1 if graph.vertices else 0
                            connectivity_constraints = (2 * edge_count) + len(graph.vertices)
                        elif kind == "Forest":
                            forest_constraints = _forest_constraint_count(graph)
                        elif kind == "SteinerTree":
                            terminal_name = find.decision_type.unknown_type.args[1]
                            terminal_count = len(problem.set_values.get(terminal_name, []))
                            steiner_terminal_constraints = terminal_count
                            steiner_edge_endpoint_constraints = 2 * edge_count
                            steiner_tree_count_constraints = 1 if graph.vertices else 0
                            steiner_flow_capacity_constraints = 2 * edge_count
                            steiner_flow_balance_constraints = len(graph.vertices)
                    binary_count = edge_count + (vertex_count if kind == "SteinerTree" else 0)
                    cqm_binary += binary_count
                    if kind == "SpanningTree":
                        cqm_integer += 2 * edge_count
                    elif kind == "SteinerTree":
                        cqm_integer += 2 * edge_count
                    if is_auxiliary:
                        auxiliary_binary += binary_count
                    graph_matching_degree += degree_constraints
                    graph_maximal_matching += maximality_constraints
                    graph_spanning_tree_edge_count += spanning_edge_count_constraints
                    graph_spanning_tree_connectivity += connectivity_constraints
                    graph_forest_acyclic += forest_constraints
                    graph_steiner_terminal += steiner_terminal_constraints
                    graph_steiner_edge_endpoint += steiner_edge_endpoint_constraints
                    graph_steiner_tree_count += steiner_tree_count_constraints
                    graph_steiner_flow_capacity += steiner_flow_capacity_constraints
                    graph_steiner_flow_balance += steiner_flow_balance_constraints
                    decision_report[find.name] = {
                        "kind": kind,
                        "binary_variables": edge_count,
                    }
                    if kind in {"Matching", "MaximalMatching"}:
                        decision_report[find.name]["degree_constraints"] = degree_constraints
                    if kind == "MaximalMatching":
                        decision_report[find.name]["maximality_constraints"] = (
                            maximality_constraints
                        )
                    elif kind == "SpanningTree":
                        decision_report[find.name]["flow_variables"] = 2 * edge_count
                        decision_report[find.name]["edge_count_constraints"] = (
                            spanning_edge_count_constraints
                        )
                        decision_report[find.name]["connectivity_constraints"] = (
                            connectivity_constraints
                        )
                    elif kind == "Forest":
                        decision_report[find.name]["acyclicity_constraints"] = forest_constraints
                    elif kind == "SteinerTree":
                        decision_report[find.name] = {
                            "kind": kind,
                            "vertex_variables": vertex_count,
                            "edge_variables": edge_count,
                            "binary_variables": binary_count,
                            "flow_variables": 2 * edge_count,
                            "terminal_constraints": steiner_terminal_constraints,
                            "edge_endpoint_constraints": steiner_edge_endpoint_constraints,
                            "tree_count_constraints": steiner_tree_count_constraints,
                            "flow_capacity_constraints": steiner_flow_capacity_constraints,
                            "flow_balance_constraints": steiner_flow_balance_constraints,
                        }
                elif kind in {"HamiltonianPath", "HamiltonianCycle"}:
                    graph_name = find.decision_type.unknown_type.args[0]
                    graph = GraphData.from_ground_problem(problem, graph_name, find.span, [])
                    vertex_count = 0 if graph is None else len(graph.vertices)
                    edge_count = 0 if graph is None else len(graph.edges)
                    adjacent_pair_count = 0
                    nonedge_ordered_count = 0
                    if graph is not None:
                        adjacent_pair_count = (
                            vertex_count
                            if kind == "HamiltonianCycle" and vertex_count > 1
                            else max(vertex_count - 1, 0)
                        )
                        nonedge_ordered_count = sum(
                            1
                            for left in graph.vertices
                            for right in graph.vertices
                            if left != right and graph.edge_key(left, right) is None
                        )
                    at_variables = vertex_count * vertex_count
                    uses_variables = edge_count
                    transition_variables = 2 * edge_count * adjacent_pair_count
                    assignment_constraints = 2 * vertex_count
                    adjacency_constraints = adjacent_pair_count * nonedge_ordered_count
                    uses_link_constraints = edge_count + (3 * transition_variables)
                    cqm_binary += at_variables + uses_variables + transition_variables
                    graph_hamiltonian_assignment += assignment_constraints
                    graph_hamiltonian_adjacency += adjacency_constraints
                    graph_hamiltonian_uses_link += uses_link_constraints
                    decision_report[find.name] = {
                        "kind": kind,
                        "at_variables": at_variables,
                        "uses_variables": uses_variables,
                        "transition_variables": transition_variables,
                        "assignment_constraints": assignment_constraints,
                        "adjacency_constraints": adjacency_constraints,
                        "uses_link_constraints": uses_link_constraints,
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

        constraint_report: dict[str, int] = {
            "explicit": len(problem.constraints),
            "mapping_exactly_one": mapping_exactly_one,
        }
        if graph_matching_degree:
            constraint_report["graph_matching_degree"] = graph_matching_degree
        if graph_maximal_matching:
            constraint_report["graph_maximal_matching"] = graph_maximal_matching
        if graph_spanning_tree_edge_count:
            constraint_report["graph_spanning_tree_edge_count"] = graph_spanning_tree_edge_count
        if graph_spanning_tree_connectivity:
            constraint_report["graph_spanning_tree_connectivity"] = graph_spanning_tree_connectivity
        if graph_forest_acyclic:
            constraint_report["graph_forest_acyclic"] = graph_forest_acyclic
        if graph_steiner_terminal:
            constraint_report["graph_steiner_terminal"] = graph_steiner_terminal
        if graph_steiner_edge_endpoint:
            constraint_report["graph_steiner_edge_endpoint"] = graph_steiner_edge_endpoint
        if graph_steiner_tree_count:
            constraint_report["graph_steiner_tree_count"] = graph_steiner_tree_count
        if graph_steiner_flow_capacity:
            constraint_report["graph_steiner_flow_capacity"] = graph_steiner_flow_capacity
        if graph_steiner_flow_balance:
            constraint_report["graph_steiner_flow_balance"] = graph_steiner_flow_balance
        if graph_hamiltonian_assignment:
            constraint_report["graph_hamiltonian_assignment"] = graph_hamiltonian_assignment
        if graph_hamiltonian_adjacency:
            constraint_report["graph_hamiltonian_adjacency"] = graph_hamiltonian_adjacency
        if graph_hamiltonian_uses_link:
            constraint_report["graph_hamiltonian_uses_link"] = graph_hamiltonian_uses_link

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
                constraints=constraint_report,
                expressions={
                    "max_polynomial_degree_before_reduction": 0,
                    "max_polynomial_degree_after_reduction": 0,
                },
                backend={
                    "status": backend_status,
                    "cqm_binary_variables": cqm_binary,
                    "cqm_integer_variables": cqm_integer,
                    "warnings": _estimate_warnings(
                        set_report,
                        relation_report,
                        problem.structures,
                        decision_report,
                    ),
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


def _forest_constraint_count(graph: GraphData) -> int:
    count = 0
    vertices = tuple(graph.vertices)
    for size in range(2, len(vertices) + 1):
        for subset in combinations(vertices, size):
            subset_values = frozenset(subset)
            induced_edges = tuple(
                edge
                for edge in graph.edges
                if edge[0] in subset_values and edge[1] in subset_values
            )
            if len(induced_edges) > size - 1:
                count += 1
    return count


def _int_bounds(decision_type: ir.KIntDecisionType) -> tuple[int | None, int | None]:
    if not isinstance(decision_type.lo, ir.KNumLit) or not isinstance(decision_type.hi, ir.KNumLit):
        return None, None
    return int(decision_type.lo.value), int(decision_type.hi.value)


def _estimate_warnings(
    sets: dict[str, dict[str, object]],
    relations: dict[str, dict[str, object]],
    structures: dict[str, dict[str, object]],
    decisions: dict[str, dict[str, object]],
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
    for name, report in structures.items():
        warnings.extend(_graph_structure_warnings(name, report))
    for name, report in decisions.items():
        warnings.extend(_decision_warnings(name, report))
    return warnings


def _graph_structure_warnings(name: str, report: dict[str, object]) -> list[str]:
    constructor = report.get("constructor")
    domains = report.get("domains")
    if not isinstance(constructor, str) or not isinstance(domains, dict):
        return []

    warnings: list[str] = []
    vertices = _int_field(domains, "vertices")
    if constructor == "UndirectedGraph":
        edges = _int_field(domains, "edges")
        possible = vertices * (vertices - 1) // 2 if vertices > 1 else 0
        if vertices >= 8 and possible > 0 and edges / possible >= 0.75:
            warnings.append(
                f"UndirectedGraph `{name}` has {edges} tuples over {vertices} vertices; "
                "dense relation helpers such as non_edges, Forest, and Hamiltonian encodings may expand quickly"
            )
    elif constructor == "DirectedGraph":
        arcs = _int_field(domains, "arcs")
        possible = vertices * (vertices - 1)
        if vertices >= 8 and possible > 0 and arcs / possible >= 0.75:
            warnings.append(
                f"DirectedGraph `{name}` has {arcs} tuples over {vertices} vertices; "
                "dense relation helpers such as non_arcs and selected-arc encodings may expand quickly"
            )
    return warnings


def _decision_warnings(name: str, report: dict[str, object]) -> list[str]:
    kind = report.get("kind")
    warnings: list[str] = []
    if kind == "Forest":
        acyclicity_constraints = _int_field(report, "acyclicity_constraints")
        if acyclicity_constraints >= 100:
            warnings.append(
                f"Forest `{name}` generates {acyclicity_constraints} acyclicity constraints; "
                "dense graphs can produce exponential subset constraints"
            )
    elif kind == "SpanningTree":
        flow_variables = _int_field(report, "flow_variables")
        connectivity_constraints = _int_field(report, "connectivity_constraints")
        if flow_variables >= 50 or connectivity_constraints >= 100:
            warnings.append(
                f"SpanningTree `{name}` uses {flow_variables} integer flow variables and "
                f"{connectivity_constraints} connectivity constraints; check target support before solving"
            )
    elif kind == "SteinerTree":
        flow_variables = _int_field(report, "flow_variables")
        flow_constraints = _int_field(report, "flow_capacity_constraints") + _int_field(
            report, "flow_balance_constraints"
        )
        if flow_variables >= 50 or flow_constraints >= 100:
            warnings.append(
                f"SteinerTree `{name}` uses {flow_variables} integer flow variables and "
                f"{flow_constraints} flow constraints; flow-based connectivity can dominate model size"
            )
    elif kind in {"HamiltonianPath", "HamiltonianCycle"}:
        transition_variables = _int_field(report, "transition_variables")
        uses_link_constraints = _int_field(report, "uses_link_constraints")
        if transition_variables >= 100 or uses_link_constraints >= 300:
            warnings.append(
                f"{kind} `{name}` introduces {transition_variables} transition variables and "
                f"{uses_link_constraints} link constraints; route encodings scale with positions times edges"
            )
    return warnings


def _int_field(report: dict[str, object], field: str) -> int:
    value = report.get(field)
    return value if isinstance(value, int) else 0
