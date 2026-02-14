from __future__ import annotations

from qsol.diag.source import Span
from qsol.lower.desugar import desugar_program
from qsol.lower.lower import lower_symbolic
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


def test_desugar_and_lower_cover_additional_expression_paths() -> None:
    span = _span()
    x = ast.NameRef(span=span, name="x")
    s = ast.NameRef(span=span, name="S")
    has_x = ast.MethodCall(span=span, target=s, name="has", args=[x])

    any_expr = ast.BoolAggregate(
        span=span,
        kind="any",
        comp=ast.BoolComprehension(
            span=span,
            term=has_x,
            var="x",
            domain_set="A",
            where=ast.BoolLit(span=span, value=True),
            else_term=ast.BoolLit(span=span, value=False),
        ),
    )
    all_expr = ast.BoolAggregate(
        span=span,
        kind="all",
        comp=ast.BoolComprehension(
            span=span,
            term=ast.Not(span=span, expr=has_x),
            var="x",
            domain_set="A",
            where=ast.BoolLit(span=span, value=True),
            else_term=ast.BoolLit(span=span, value=False),
        ),
    )
    count_expr = ast.NumAggregate(
        span=span,
        kind="count",
        comp=ast.CountComprehension(
            span=span,
            var_ref="x",
            var="x",
            domain_set="A",
            where=has_x,
            else_term=ast.BoolLit(span=span, value=False),
        ),
    )

    program = ast.Program(
        span=span,
        items=[
            ast.ProblemDef(
                span=span,
                name="P",
                stmts=[
                    ast.SetDecl(span=span, name="A"),
                    ast.FindDecl(
                        span=span,
                        name="S",
                        unknown_type=ast.UnknownTypeRef(span=span, kind="Subset", args=("A",)),
                    ),
                    ast.Constraint(span=span, kind=ast.ConstraintKind.MUST, expr=any_expr),
                    ast.Constraint(span=span, kind=ast.ConstraintKind.MUST, expr=all_expr),
                    ast.Objective(
                        span=span,
                        kind=ast.ObjectiveKind.MINIMIZE,
                        expr=count_expr,
                    ),
                    ast.Objective(
                        span=span,
                        kind=ast.ObjectiveKind.MINIMIZE,
                        expr=ast.FuncCall(
                            span=span, name="f", args=[ast.NameRef(span=span, name="x")]
                        ),
                    ),
                    ast.Objective(
                        span=span,
                        kind=ast.ObjectiveKind.MINIMIZE,
                        expr=ast.MethodCall(
                            span=span,
                            target=ast.NameRef(span=span, name="S"),
                            name="has",
                            args=[ast.NameRef(span=span, name="x")],
                        ),
                    ),
                ],
            )
        ],
    )

    desugared = desugar_program(program)
    problem = desugared.items[0]
    assert isinstance(problem, ast.ProblemDef)
    constraints = [stmt for stmt in problem.stmts if isinstance(stmt, ast.Constraint)]
    objectives = [stmt for stmt in problem.stmts if isinstance(stmt, ast.Objective)]
    assert isinstance(constraints[0].expr, ast.Quantifier)
    assert isinstance(constraints[1].expr, ast.Quantifier)
    assert isinstance(objectives[0].expr, ast.NumAggregate)
    assert objectives[0].expr.kind == "sum"

    lowered = lower_symbolic(desugared)
    assert lowered.problems
    assert len(lowered.problems[0].constraints) == 2
    assert len(lowered.problems[0].objectives) == 3
