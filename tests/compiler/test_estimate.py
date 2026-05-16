from __future__ import annotations

from qsol.compiler.estimate import estimate_ground_ir
from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source
from qsol.diag.source import Span
from qsol.lower import ir
from qsol.parse import ast


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


def test_estimate_ground_ir_reports_all_decision_kinds() -> None:
    span = _span()
    problem = ir.GroundProblem(
        span=span,
        name="Estimate",
        set_values={"A": ["a1", "a2"], "B": ["b1"], "Positions": [1, 2, 3]},
        relation_values={
            "Edge": (("a1", "a2"),),
            "NonEdge": (("a2", "a1"),),
        },
        structures={},
        derived_relations={"NonEdge": "pairs"},
        derived_sets={"Positions": "Range"},
        params={},
        finds=(
            ir.KFindDecl(
                span=span,
                name="Pick",
                unknown_type=ast.UnknownTypeRef(span=span, kind="Subset", args=("A",)),
            ),
            ir.KFindDecl(
                span=span,
                name="Assign",
                unknown_type=ast.UnknownTypeRef(span=span, kind="Mapping", args=("A", "B")),
            ),
            ir.KFindDecl(
                span=span,
                name="Custom",
                unknown_type=ast.UnknownTypeRef(span=span, kind="CustomUnknown", args=("A",)),
            ),
            ir.KFindDecl(span=span, name="enabled", decision_type=ir.KBoolDecisionType(span=span)),
            ir.KFindDecl(
                span=span,
                name="Load",
                indices=("A",),
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KNumLit(span=span, value=1.0),
                    hi=ir.KNumLit(span=span, value=3.0),
                ),
            ),
            ir.KFindDecl(
                span=span,
                name="Flow",
                indices=("Edge",),
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KNumLit(span=span, value=0.0),
                    hi=ir.KNumLit(span=span, value=2.0),
                ),
            ),
            ir.KFindDecl(
                span=span,
                name="LateBound",
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KName(span=span, name="lo"),
                    hi=ir.KName(span=span, name="hi"),
                ),
            ),
        ),
        constraints=(
            ir.KConstraint(
                span=span, kind=ast.ConstraintKind.MUST, expr=ir.KBoolLit(span=span, value=True)
            ),
        ),
        objectives=(),
    )

    report = estimate_ground_ir(
        ir.GroundIR(span=span, problems=(problem,)), backend_status="partial"
    )[0].to_dict()

    assert report["sets"]["Positions"] == {"size": 3, "derived": True, "source": "Range"}
    assert report["relations"]["Edge"] == {
        "size": 1,
        "arity": 2,
        "derived": False,
        "source": None,
    }
    assert report["relations"]["NonEdge"] == {
        "size": 1,
        "arity": 2,
        "derived": True,
        "source": "pairs",
    }
    assert report["relations"]["Edge"]["arity"] == 2
    assert report["relations"]["NonEdge"]["arity"] == 2
    assert report["decision_variables"]["Pick"]["binary_variables"] == 2
    assert report["decision_variables"]["Assign"]["exactly_one_constraints"] == 2
    assert report["decision_variables"]["Custom"]["supported"] is False
    assert report["decision_variables"]["enabled"]["domain_size"] == 2
    assert report["decision_variables"]["Load"]["instances"] == 2
    assert report["decision_variables"]["Load"]["domain_size"] == 3
    assert report["decision_variables"]["Flow"]["instances"] == 1
    assert report["decision_variables"]["Flow"]["domain_size"] == 3
    assert report["decision_variables"]["LateBound"]["domain_size"] is None
    assert report["constraints"] == {"explicit": 1, "mapping_exactly_one": 2}
    assert report["backend"] == {
        "status": "partial",
        "cqm_binary_variables": 5,
        "cqm_integer_variables": 4,
        "warnings": [],
    }
    assert report["decisions"] == {
        "binary": 5,
        "integer": 4,
        "auxiliary_binary": 0,
        "auxiliary_integer": 0,
    }
    assert report["expressions"]["max_polynomial_degree_before_reduction"] == 0
    assert report["expressions"]["max_polynomial_degree_after_reduction"] == 0
    assert report["backend"]["warnings"] == []


def test_estimate_reports_piecewise_generated_aux_decision() -> None:
    source = """
problem AbsBalance {
  find Balance : Int[-5 .. 5];
  minimize abs(Balance);
}
"""
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="abs_balance.qsol",
            instance_payload={"problem": "AbsBalance"},
        ),
    )

    assert unit.ground_ir is not None
    report = estimate_ground_ir(unit.ground_ir)[0].to_dict()
    aux_names = [
        name for name in report["decision_variables"] if name.startswith("__qsol_piecewise_abs_")
    ]
    assert len(aux_names) == 1
    assert report["decision_variables"][aux_names[0]]["kind"] == "Int"
    assert report["constraints"]["explicit"] == 2


def test_estimate_reports_graph_structures_and_indexed_edge_decisions() -> None:
    source = """
use stdlib.graph;

problem GraphEstimate {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find Selected[G.edges] : Bool;
  maximize count((u, v) in G.edges where G.adjacent(u, v));
}
"""
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="graph_estimate.qsol",
            instance_payload={
                "problem": "GraphEstimate",
                "sets": {"V": ["A", "B", "C"]},
                "relations": {"Edge": [["A", "B"], ["B", "A"]]},
            },
        ),
    )

    assert unit.ground_ir is not None
    report = estimate_ground_ir(unit.ground_ir)[0].to_dict()
    assert report["structures"]["G"]["constructor"] == "UndirectedGraph"
    assert report["structures"]["G"]["domains"]["edges"] == 1
    assert report["structures"]["G"]["domains"]["non_edges"] == 2
    assert report["decision_variables"]["Selected"]["instances"] == 1
    assert report["decisions"]["binary"] == 1
