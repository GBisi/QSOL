from __future__ import annotations

from dataclasses import dataclass
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


def _graph_diagnostic(span: Span, code: str, message: str) -> Diagnostic:
    return Diagnostic(severity=Severity.ERROR, code=code, message=message, span=span)
