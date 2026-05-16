from __future__ import annotations

from qsol.diag.source import Span
from qsol.lower.globals import _lower_expr, _rename_expr, lower_global_helpers_program
from qsol.parse import ast
from qsol.parse.parser import parse_to_ast


def _problem_stmt(source: str, index: int = 0) -> ast.ProblemStmt:
    program = parse_to_ast(source, filename="globals.qsol")
    lowered = lower_global_helpers_program(program)
    problem = next(item for item in lowered.items if isinstance(item, ast.ProblemDef))
    return problem.stmts[index]


def test_lower_all_different_rewrites_to_pairwise_bool_aggregate() -> None:
    stmt = _problem_stmt(
        """
problem P {
  set Items;
  find Slot[Items] : Int[0 .. size(Items) - 1];
  must all_different(Slot[i] for i in Items where Slot[i] >= 0);
}
""",
        index=2,
    )

    assert isinstance(stmt, ast.Constraint)
    assert isinstance(stmt.expr, ast.BoolAggregate)
    assert stmt.expr.kind == "all"
    assert len(stmt.expr.comp.binders) == 2
    assert isinstance(stmt.expr.comp.where, ast.And)


def test_lower_graph_nonedge_and_adjacent_helpers() -> None:
    adjacent_stmt = _problem_stmt(
        """
problem P {
  set V;
  relation Edge(u: V, v: V);
  must adjacent(Edge, u, v);
}
""",
        index=2,
    )
    assert isinstance(adjacent_stmt, ast.Constraint)
    assert isinstance(adjacent_stmt.expr, ast.Or)

    nonedge_stmt = _problem_stmt(
        """
problem P {
  set V;
  relation Edge(u: V, v: V);
  must nonedge(Edge, u, v);
}
""",
        index=2,
    )
    assert isinstance(nonedge_stmt, ast.Constraint)
    assert isinstance(nonedge_stmt.expr, ast.And)
    assert isinstance(nonedge_stmt.expr.left, ast.Not)


def test_lower_global_helpers_inside_relation_and_bounds() -> None:
    relation_stmt = _problem_stmt(
        """
problem P {
  set V;
  relation Edge(u: V, v: V);
  relation NonEdge(u: V, v: V) = pairs(u in V, v in V where nonedge(Edge, u, v));
}
""",
        index=2,
    )
    assert isinstance(relation_stmt, ast.RelationDecl)
    assert isinstance(relation_stmt.expr, ast.PairsRelationExpr)
    assert isinstance(relation_stmt.expr.where, ast.And)

    find_stmt = _problem_stmt(
        """
problem P {
  set Items;
  find X : Int[0 .. max(size(Items), 1)];
}
""",
        index=1,
    )
    assert isinstance(find_stmt, ast.FindDecl)
    assert isinstance(find_stmt.decision_type, ast.IntDecisionType)
    assert isinstance(find_stmt.decision_type.hi, ast.FuncCall)


def test_lower_invalid_helper_shapes_are_left_for_typecheck() -> None:
    span = Span(0, 1, 1, 1, 1, 2, "globals.qsol")
    bad_all_different = ast.FuncCall(span=span, name="all_different", args=[])
    bad_adjacent = ast.FuncCall(span=span, name="adjacent", args=[])
    bad_nonedge = ast.FuncCall(span=span, name="nonedge", args=[])

    assert _lower_expr(None) is None
    assert isinstance(_lower_expr(bad_all_different), ast.FuncCall)
    assert isinstance(_lower_expr(bad_adjacent), ast.FuncCall)
    assert isinstance(_lower_expr(bad_nonedge), ast.FuncCall)


def test_rename_expr_recurses_through_expression_shapes() -> None:
    span = Span(0, 1, 1, 1, 1, 2, "globals.qsol")
    expr = ast.BoolIfThenElse(
        span=span,
        cond=ast.Or(
            span=span,
            left=ast.Not(span=span, expr=ast.NameRef(span=span, name="old")),
            right=ast.Implies(
                span=span,
                left=ast.Compare(
                    span=span,
                    op="=",
                    left=ast.Add(
                        span=span,
                        left=ast.NameRef(span=span, name="old"),
                        right=ast.NumLit(span=span, value=1),
                    ),
                    right=ast.NumLit(span=span, value=2),
                ),
                right=ast.BoolLit(span=span, value=True),
            ),
        ),
        then_expr=ast.BoolLit(span=span, value=True),
        else_expr=ast.BoolLit(span=span, value=False),
    )

    renamed = _rename_expr(expr, {"old": "new"})

    assert isinstance(renamed, ast.BoolIfThenElse)
    assert "new" in repr(renamed)
    assert "old" not in repr(renamed)


def test_lower_expr_recurses_through_remaining_expression_shapes() -> None:
    span = Span(0, 1, 1, 1, 1, 2, "globals.qsol")
    name = ast.NameRef(span=span, name="x")
    bool_lit = ast.BoolLit(span=span, value=True)
    num_lit = ast.NumLit(span=span, value=1)

    expressions: list[ast.Expr] = [
        ast.MethodCall(span=span, target=name, name="has", args=[name]),
        ast.Not(span=span, expr=bool_lit),
        ast.And(span=span, left=bool_lit, right=bool_lit),
        ast.Or(span=span, left=bool_lit, right=bool_lit),
        ast.Implies(span=span, left=bool_lit, right=bool_lit),
        ast.Quantifier(span=span, kind="forall", var="x", domain_set="S", expr=bool_lit),
        ast.TupleQuantifier(
            span=span, kind="forall", vars=("u", "v"), domain_relation="E", expr=bool_lit
        ),
        ast.BoolAggregate(
            span=span,
            kind="all",
            comp=ast.BoolComprehension(span=span, term=bool_lit, var="x", domain_set="S"),
        ),
        ast.NumAggregate(
            span=span,
            kind="count",
            comp=ast.CountComprehension(span=span, var_ref="x", var="x", domain_set="S"),
        ),
        ast.BoolComprehension(span=span, term=bool_lit, var="x", domain_set="S"),
        ast.BoolIfThenElse(span=span, cond=bool_lit, then_expr=bool_lit, else_expr=bool_lit),
        ast.IfThenElse(span=span, cond=bool_lit, then_expr=num_lit, else_expr=num_lit),
        ast.Add(span=span, left=num_lit, right=num_lit),
        ast.Sub(span=span, left=num_lit, right=num_lit),
        ast.Mul(span=span, left=num_lit, right=num_lit),
        ast.Div(span=span, left=num_lit, right=num_lit),
        ast.Neg(span=span, expr=num_lit),
    ]

    for expr in expressions:
        assert _lower_expr(expr) is not None


def test_lower_program_preserves_non_problem_items_and_misc_statements() -> None:
    program = parse_to_ast(
        """
predicate ok(): Bool = true;

problem P {
  set R = Range(1, 2);
  relation E(u: R, v: R) = filter((u, v) in E where adjacent(E, u, v));
  find X : Int[0 .. size(R)];
  minimize 0;
}
""",
        filename="globals.qsol",
    )

    lowered = lower_global_helpers_program(program)

    assert isinstance(lowered.items[0], ast.PredicateDef)
    problem = next(item for item in lowered.items if isinstance(item, ast.ProblemDef))
    assert isinstance(problem.stmts[0], ast.SetDecl)
    assert isinstance(problem.stmts[1], ast.RelationDecl)
    assert isinstance(problem.stmts[2], ast.FindDecl)
    assert isinstance(problem.stmts[3], ast.Objective)
