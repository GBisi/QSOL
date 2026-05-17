from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

import dimod

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.lower import ir


@dataclass(frozen=True, slots=True)
class GraphData:
    name: str
    vertices: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    edge_lookup: frozenset[tuple[str, str]]

    @classmethod
    def from_ground_problem(
        cls,
        problem: ir.GroundProblem,
        graph_name: str,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> GraphData | None:
        structure = problem.structures.get(graph_name)
        if structure is not None and structure.get("constructor") != "UndirectedGraph":
            diagnostics.append(
                _graph_diagnostic(
                    span,
                    "QSOL3301",
                    f"graph unknown expects an UndirectedGraph, got `{graph_name}`",
                )
            )
            return None

        vertices = problem.set_values.get(f"{graph_name}.vertices")
        edges = problem.relation_values.get(f"{graph_name}.edges")
        if vertices is None or edges is None:
            diagnostics.append(
                _graph_diagnostic(span, "QSOL3301", f"missing grounded graph `{graph_name}`")
            )
            return None

        normalized_edges = tuple((str(edge[0]), str(edge[1])) for edge in edges if len(edge) == 2)
        return cls(
            name=graph_name,
            vertices=tuple(str(vertex) for vertex in vertices),
            edges=normalized_edges,
            edge_lookup=frozenset(normalized_edges),
        )

    def edge_key(self, u: object, v: object) -> tuple[str, str] | None:
        forward = (str(u), str(v))
        if forward in self.edge_lookup:
            return forward
        reverse = (str(v), str(u))
        if reverse in self.edge_lookup:
            return reverse
        return None

    def incident_edges(self, vertex: object) -> tuple[tuple[str, str], ...]:
        key = str(vertex)
        return tuple(edge for edge in self.edges if key in edge)


@dataclass(frozen=True, slots=True)
class GraphUnknownLabels:
    find_name: str

    def edge_var(self, edge: tuple[object, object]) -> str:
        u, v = edge
        return f"{self.find_name}.has_edge[{u},{v}]"

    def edge_meaning(self, edge: tuple[object, object]) -> str:
        u, v = edge
        return f"{self.find_name}.has_edge({u},{v})"

    def vertex_var(self, vertex: object) -> str:
        return f"{self.find_name}.has_vertex[{vertex}]"

    def vertex_meaning(self, vertex: object) -> str:
        return f"{self.find_name}.has_vertex({vertex})"


@dataclass(frozen=True, slots=True)
class ConnectivityEncoding:
    flow_labels: tuple[str, ...]
    added_constraints: int


def add_degree_at_most_one_constraints(
    cqm: dimod.ConstrainedQuadraticModel,
    *,
    graph: GraphData,
    labels: GraphUnknownLabels,
    binaries: dict[str, Any],
    span: Span,
    diagnostics: list[Diagnostic],
) -> int:
    added = 0
    for vertex in sorted(graph.vertices, key=str):
        incident = [
            binaries[labels.edge_var(edge)]
            for edge in graph.incident_edges(vertex)
            if labels.edge_var(edge) in binaries
        ]
        if len(incident) <= 1:
            continue
        label = f"implicit_matching_degree:{labels.find_name}:{vertex}"
        try:
            cqm.add_constraint(sum(incident, 0.0) <= 1.0, label=label)
        except TypeError:
            diagnostics.append(
                _graph_diagnostic(
                    span,
                    "QSOL3303",
                    f"could not add matching degree constraint for `{labels.find_name}`",
                )
            )
            continue
        added += 1
    return added


def add_rooted_connectivity_constraints(
    cqm: dimod.ConstrainedQuadraticModel,
    *,
    graph: GraphData,
    labels: GraphUnknownLabels,
    binaries: dict[str, Any],
    root: object,
    span: Span,
    diagnostics: list[Diagnostic],
) -> ConnectivityEncoding:
    root_key = str(root)
    if root_key not in graph.vertices:
        diagnostics.append(
            _graph_diagnostic(
                span, "QSOL3303", f"connectivity root `{root_key}` is not in graph `{graph.name}`"
            )
        )
        return ConnectivityEncoding(flow_labels=(), added_constraints=0)

    capacity = max(len(graph.vertices) - 1, 1)
    flow_vars: dict[tuple[str, str], Any] = {}
    for u, v in _oriented_edges(graph):
        label = _flow_label(labels.find_name, u, v)
        flow_vars[(u, v)] = dimod.Integer(label, lower_bound=0, upper_bound=capacity)

    added = 0
    for u, v in _oriented_edges(graph):
        edge = graph.edge_key(u, v)
        if edge is None:
            continue
        selected = binaries.get(labels.edge_var(edge))
        if selected is None:
            diagnostics.append(
                _graph_diagnostic(
                    span,
                    "QSOL3303",
                    f"missing selected-edge variable for `{labels.find_name}`",
                )
            )
            continue
        _add_model_constraint(
            cqm,
            lhs=flow_vars[(u, v)],
            rhs=capacity * selected,
            sense="<=",
            label=f"implicit_connectivity_capacity:{labels.find_name}:{u}:{v}",
        )
        added += 1

    for vertex in graph.vertices:
        inflow = sum(
            (var for (u, v), var in flow_vars.items() if v == vertex),
            0.0,
        )
        outflow = sum(
            (var for (u, v), var in flow_vars.items() if u == vertex),
            0.0,
        )
        if vertex == root_key:
            _add_model_constraint(
                cqm,
                lhs=outflow - inflow,
                rhs=len(graph.vertices) - 1,
                sense="==",
                label=f"implicit_connectivity_balance:{labels.find_name}:{vertex}",
            )
        else:
            _add_model_constraint(
                cqm,
                lhs=inflow - outflow,
                rhs=1,
                sense="==",
                label=f"implicit_connectivity_balance:{labels.find_name}:{vertex}",
            )
        added += 1

    return ConnectivityEncoding(
        flow_labels=tuple(_flow_label(labels.find_name, u, v) for u, v in _oriented_edges(graph)),
        added_constraints=added,
    )


def add_steiner_tree_constraints(
    cqm: dimod.ConstrainedQuadraticModel,
    *,
    graph: GraphData,
    labels: GraphUnknownLabels,
    binaries: dict[str, Any],
    terminals: tuple[str, ...],
    span: Span,
    diagnostics: list[Diagnostic],
) -> int:
    if not terminals:
        diagnostics.append(
            _graph_diagnostic(span, "QSOL3304", "SteinerTree requires nonempty Terminals")
        )
        return 0

    missing = [vertex for vertex in terminals if vertex not in graph.vertices]
    if missing:
        diagnostics.append(
            _graph_diagnostic(
                span,
                "QSOL3304",
                f"SteinerTree terminal `{missing[0]}` is not a vertex of `{graph.name}`",
            )
        )
        return 0

    root = terminals[0]
    selected_vertices = {
        vertex: binaries[labels.vertex_var(vertex)]
        for vertex in graph.vertices
        if labels.vertex_var(vertex) in binaries
    }
    selected_edges = {
        edge: binaries[labels.edge_var(edge)]
        for edge in graph.edges
        if labels.edge_var(edge) in binaries
    }
    if len(selected_vertices) != len(graph.vertices) or len(selected_edges) != len(graph.edges):
        diagnostics.append(
            _graph_diagnostic(
                span,
                "QSOL3303",
                f"missing SteinerTree variables for `{labels.find_name}`",
            )
        )
        return 0

    added = 0
    for terminal in terminals:
        cqm.add_constraint(
            selected_vertices[terminal] == 1.0,
            label=f"implicit_steiner_terminal:{labels.find_name}:{terminal}",
        )
        added += 1

    for u, v in graph.edges:
        edge_var = selected_edges[(u, v)]
        cqm.add_constraint(
            edge_var - selected_vertices[u] <= 0.0,
            label=f"implicit_steiner_edge_endpoint:{labels.find_name}:{u}:{v}:u",
        )
        cqm.add_constraint(
            edge_var - selected_vertices[v] <= 0.0,
            label=f"implicit_steiner_edge_endpoint:{labels.find_name}:{u}:{v}:v",
        )
        added += 2

    edge_sum = sum(selected_edges.values(), 0.0)
    vertex_sum = sum(selected_vertices.values(), 0.0)
    cqm.add_constraint(
        edge_sum - vertex_sum == -1.0,
        label=f"implicit_steiner_tree_count:{labels.find_name}",
    )
    added += 1

    max_flow = max(len(graph.vertices) - 1, 1)
    flows: dict[tuple[str, str], Any] = {}
    for u, v in _oriented_edges(graph):
        label = _flow_label(labels.find_name, u, v)
        flows[(u, v)] = dimod.Integer(label, lower_bound=0, upper_bound=max_flow)

    for u, v in graph.edges:
        edge_var = selected_edges[(u, v)]
        for a, b in ((u, v), (v, u)):
            _add_model_constraint(
                cqm,
                lhs=flows[(a, b)] - (max_flow * edge_var),
                rhs=0,
                sense="<=",
                label=f"implicit_steiner_flow_capacity:{labels.find_name}:{a}:{b}",
            )
            added += 1

    for vertex in graph.vertices:
        inflow = sum(
            (flows[(u, v)] for u, v in _oriented_edges(graph) if v == vertex),
            0.0,
        )
        outflow = sum(
            (flows[(u, v)] for u, v in _oriented_edges(graph) if u == vertex),
            0.0,
        )
        if vertex == root:
            _add_model_constraint(
                cqm,
                lhs=outflow - inflow - vertex_sum + 1,
                rhs=0,
                sense="==",
                label=f"implicit_steiner_flow_balance:{labels.find_name}:{vertex}",
            )
        else:
            _add_model_constraint(
                cqm,
                lhs=inflow - outflow - selected_vertices[vertex],
                rhs=0,
                sense="==",
                label=f"implicit_steiner_flow_balance:{labels.find_name}:{vertex}",
            )
        added += 1

    return added


def add_maximal_matching_constraints(
    cqm: dimod.ConstrainedQuadraticModel,
    *,
    graph: GraphData,
    labels: GraphUnknownLabels,
    binaries: dict[str, Any],
    span: Span,
    diagnostics: list[Diagnostic],
) -> int:
    added = 0
    for edge in graph.edges:
        incident_edges = {
            incident
            for endpoint in edge
            for incident in graph.incident_edges(endpoint)
            if labels.edge_var(incident) in binaries
        }
        if not incident_edges:
            diagnostics.append(
                _graph_diagnostic(
                    span,
                    "QSOL3303",
                    f"could not add maximality constraint for `{labels.find_name}`",
                )
            )
            continue
        label = f"implicit_maximal_matching:{labels.find_name}:{edge[0]}:{edge[1]}"
        try:
            cqm.add_constraint(
                sum((binaries[labels.edge_var(incident)] for incident in incident_edges), 0.0)
                >= 1.0,
                label=label,
            )
        except TypeError:
            diagnostics.append(
                _graph_diagnostic(
                    span,
                    "QSOL3303",
                    f"could not add maximality constraint for `{labels.find_name}`",
                )
            )
            continue
        added += 1
    return added


def add_forest_constraints(
    cqm: dimod.ConstrainedQuadraticModel,
    *,
    graph: GraphData,
    labels: GraphUnknownLabels,
    binaries: dict[str, Any],
    span: Span,
    diagnostics: list[Diagnostic],
) -> int:
    added = 0
    vertices = tuple(graph.vertices)
    for size in range(2, len(vertices) + 1):
        for subset in combinations(vertices, size):
            subset_values = frozenset(subset)
            induced_edges = tuple(
                edge
                for edge in graph.edges
                if edge[0] in subset_values and edge[1] in subset_values
            )
            if len(induced_edges) <= size - 1:
                continue
            terms = []
            for edge in induced_edges:
                label = labels.edge_var(edge)
                if label not in binaries:
                    diagnostics.append(
                        _graph_diagnostic(
                            span,
                            "QSOL3303",
                            f"missing selected-edge variable for `{labels.find_name}`",
                        )
                    )
                    continue
                terms.append(binaries[label])
            if not terms:
                continue
            cqm.add_constraint(
                sum(terms, 0.0) <= size - 1,
                label=f"implicit_forest:{labels.find_name}:{':'.join(subset)}",
            )
            added += 1
    return added


def _oriented_edges(graph: GraphData) -> tuple[tuple[str, str], ...]:
    return tuple((u, v) for edge in graph.edges for u, v in (edge, (edge[1], edge[0])))


def _flow_label(find_name: str, u: object, v: object) -> str:
    return f"__qsol_flow:{find_name}:{u}:{v}"


def _add_model_constraint(
    cqm: dimod.ConstrainedQuadraticModel,
    *,
    lhs: Any,
    rhs: Any,
    sense: str,
    label: str,
) -> None:
    cqm.add_constraint_from_model(lhs - rhs, sense=sense, rhs=0.0, label=label)


def _graph_diagnostic(span: Span, code: str, message: str) -> Diagnostic:
    return Diagnostic(severity=Severity.ERROR, code=code, message=message, span=span)
