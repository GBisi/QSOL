from __future__ import annotations

import dimod

from qsol.backend.graph_encoding import (
    GraphData,
    GraphUnknownLabels,
    add_degree_at_most_one_constraints,
)
from qsol.diag.source import Span
from qsol.lower import ir


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


def _path_problem() -> ir.GroundProblem:
    span = _span()
    return ir.GroundProblem(
        span=span,
        name="P",
        set_values={"G.vertices": ["a", "b", "c"]},
        relation_values={"G.edges": (("a", "b"), ("b", "c"))},
        params={},
        finds=(),
        constraints=(),
        objectives=(),
        structures={"G": {"constructor": "UndirectedGraph"}},
    )


def test_graph_data_canonicalizes_undirected_edges_and_incidence() -> None:
    diagnostics = []
    graph = GraphData.from_ground_problem(_path_problem(), "G", _span(), diagnostics)

    assert graph is not None
    assert not diagnostics
    assert graph.edge_key("a", "b") == ("a", "b")
    assert graph.edge_key("b", "a") == ("a", "b")
    assert graph.edge_key("a", "c") is None
    assert graph.incident_edges("b") == (("a", "b"), ("b", "c"))
    assert graph.incident_edges("a") == (("a", "b"),)


def test_graph_data_reports_missing_grounded_graph() -> None:
    diagnostics = []
    graph = GraphData.from_ground_problem(_path_problem(), "Missing", _span(), diagnostics)

    assert graph is None
    assert [diagnostic.code for diagnostic in diagnostics] == ["QSOL3301"]
    assert "missing grounded graph `Missing`" in diagnostics[0].message


def test_add_degree_at_most_one_constraints_skips_redundant_vertices() -> None:
    diagnostics = []
    graph = GraphData.from_ground_problem(_path_problem(), "G", _span(), diagnostics)
    assert graph is not None
    labels = GraphUnknownLabels("M")
    cqm = dimod.ConstrainedQuadraticModel()
    binaries = {labels.edge_var(edge): dimod.Binary(labels.edge_var(edge)) for edge in graph.edges}

    added = add_degree_at_most_one_constraints(
        cqm,
        graph=graph,
        labels=labels,
        binaries=binaries,
        span=_span(),
        diagnostics=diagnostics,
    )

    assert added == 1
    assert len(cqm.constraints) == 1
    assert not diagnostics
