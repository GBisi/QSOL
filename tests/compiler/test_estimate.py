from __future__ import annotations

from qsol.compiler.estimate import estimate_ground_ir
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
    assert report["relations"]["Edge"] == {"size": 1, "derived": False, "source": None}
    assert report["relations"]["NonEdge"] == {"size": 1, "derived": True, "source": "pairs"}
    assert report["decision_variables"]["Pick"]["binary_variables"] == 2
    assert report["decision_variables"]["Assign"]["exactly_one_constraints"] == 2
    assert report["decision_variables"]["Custom"]["supported"] is False
    assert report["decision_variables"]["enabled"]["domain_size"] == 2
    assert report["decision_variables"]["Load"]["instances"] == 2
    assert report["decision_variables"]["Load"]["domain_size"] == 3
    assert report["decision_variables"]["LateBound"]["domain_size"] is None
    assert report["constraints"] == {"explicit": 1, "mapping_exactly_one": 2}
    assert report["backend"] == {
        "status": "partial",
        "cqm_binary_variables": 5,
        "cqm_integer_variables": 3,
    }
