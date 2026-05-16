from __future__ import annotations

from dataclasses import replace
from typing import cast

from qsol.parse import ast


def lower_global_helpers_program(program: ast.Program) -> ast.Program:
    """Rewrite compiler-owned global/helper calls into ordinary QSOL syntax."""

    items: list[ast.TopItem] = []
    for item in program.items:
        if isinstance(item, ast.ProblemDef):
            items.append(replace(item, stmts=[_lower_problem_stmt(stmt) for stmt in item.stmts]))
        else:
            items.append(item)
    return replace(program, items=items)


def _lower_problem_stmt(stmt: ast.ProblemStmt) -> ast.ProblemStmt:
    if isinstance(stmt, ast.Constraint):
        return replace(
            stmt,
            expr=cast(ast.BoolExpr, _lower_expr(stmt.expr)),
            guard=cast(ast.BoolExpr, _lower_expr(stmt.guard)) if stmt.guard is not None else None,
        )
    if isinstance(stmt, ast.Objective):
        return replace(stmt, expr=cast(ast.NumExpr, _lower_expr(stmt.expr)))
    if isinstance(stmt, ast.RelationDecl) and stmt.expr is not None:
        return replace(stmt, expr=_lower_relation_expr(stmt.expr))
    if isinstance(stmt, ast.SetDecl) and stmt.expr is not None:
        return replace(stmt, expr=stmt.expr)
    if isinstance(stmt, ast.FindDecl) and isinstance(stmt.decision_type, ast.IntDecisionType):
        return replace(
            stmt,
            decision_type=replace(
                stmt.decision_type,
                lo=cast(ast.NumExpr, _lower_expr(stmt.decision_type.lo)),
                hi=cast(ast.NumExpr, _lower_expr(stmt.decision_type.hi)),
            ),
        )
    return stmt


def _lower_relation_expr(expr: ast.RelationExpr) -> ast.RelationExpr:
    if isinstance(expr, ast.PairsRelationExpr):
        return replace(
            expr,
            where=cast(ast.BoolExpr, _lower_expr(expr.where)) if expr.where is not None else None,
        )
    if isinstance(expr, ast.FilterRelationExpr):
        return replace(
            expr,
            where=cast(ast.BoolExpr, _lower_expr(expr.where)) if expr.where is not None else None,
        )
    return expr


def _lower_expr(expr: ast.Expr | None) -> ast.Expr | None:
    if expr is None:
        return None

    if isinstance(expr, ast.FuncCall):
        lowered_args = [cast(ast.Expr, _lower_expr(arg)) for arg in expr.args]
        call = replace(expr, args=lowered_args)
        if expr.name == "all_different" and expr.call_style == "paren":
            return _lower_all_different(call)
        if expr.name == "adjacent" and expr.call_style == "paren":
            return _lower_adjacent(call)
        if expr.name == "nonedge" and expr.call_style == "paren":
            return _lower_nonedge(call)
        return call

    if isinstance(expr, ast.MethodCall):
        return replace(
            expr,
            target=cast(ast.Expr, _lower_expr(expr.target)),
            args=[cast(ast.Expr, _lower_expr(arg)) for arg in expr.args],
        )
    if isinstance(expr, ast.Not):
        return replace(expr, expr=cast(ast.BoolExpr, _lower_expr(expr.expr)))
    if isinstance(expr, ast.And):
        return replace(
            expr,
            left=cast(ast.BoolExpr, _lower_expr(expr.left)),
            right=cast(ast.BoolExpr, _lower_expr(expr.right)),
        )
    if isinstance(expr, ast.Or):
        return replace(
            expr,
            left=cast(ast.BoolExpr, _lower_expr(expr.left)),
            right=cast(ast.BoolExpr, _lower_expr(expr.right)),
        )
    if isinstance(expr, ast.Implies):
        return replace(
            expr,
            left=cast(ast.BoolExpr, _lower_expr(expr.left)),
            right=cast(ast.BoolExpr, _lower_expr(expr.right)),
        )
    if isinstance(expr, ast.Compare):
        return replace(
            expr,
            left=cast(ast.Expr, _lower_expr(expr.left)),
            right=cast(ast.Expr, _lower_expr(expr.right)),
        )
    if isinstance(expr, ast.Quantifier):
        return replace(expr, expr=cast(ast.BoolExpr, _lower_expr(expr.expr)))
    if isinstance(expr, ast.TupleQuantifier):
        return replace(expr, expr=cast(ast.BoolExpr, _lower_expr(expr.expr)))
    if isinstance(expr, ast.BoolAggregate):
        comp = expr.comp
        return replace(
            expr,
            comp=replace(
                comp,
                term=cast(ast.BoolExpr, _lower_expr(comp.term)),
                where=cast(ast.BoolExpr, _lower_expr(comp.where))
                if comp.where is not None
                else None,
                else_term=cast(ast.BoolExpr, _lower_expr(comp.else_term))
                if comp.else_term is not None
                else None,
            ),
        )
    if isinstance(expr, ast.NumAggregate):
        num_comp = expr.comp
        if isinstance(num_comp, ast.NumComprehension):
            return replace(
                expr,
                comp=replace(
                    num_comp,
                    term=cast(ast.NumExpr, _lower_expr(num_comp.term)),
                    where=cast(ast.BoolExpr, _lower_expr(num_comp.where))
                    if num_comp.where is not None
                    else None,
                    else_term=cast(ast.NumExpr, _lower_expr(num_comp.else_term))
                    if num_comp.else_term is not None
                    else None,
                ),
            )
        count_comp = expr.comp
        assert isinstance(count_comp, ast.CountComprehension)
        return replace(
            expr,
            comp=replace(
                count_comp,
                where=cast(ast.BoolExpr, _lower_expr(count_comp.where))
                if count_comp.where is not None
                else None,
            ),
        )
    if isinstance(expr, ast.BoolComprehension):
        return replace(
            expr,
            term=cast(ast.BoolExpr, _lower_expr(expr.term)),
            where=cast(ast.BoolExpr, _lower_expr(expr.where)) if expr.where is not None else None,
            else_term=cast(ast.BoolExpr, _lower_expr(expr.else_term))
            if expr.else_term is not None
            else None,
        )
    if isinstance(expr, ast.BoolIfThenElse):
        return replace(
            expr,
            cond=cast(ast.BoolExpr, _lower_expr(expr.cond)),
            then_expr=cast(ast.BoolExpr, _lower_expr(expr.then_expr)),
            else_expr=cast(ast.BoolExpr, _lower_expr(expr.else_expr)),
        )
    if isinstance(expr, ast.IfThenElse):
        return replace(
            expr,
            cond=cast(ast.BoolExpr, _lower_expr(expr.cond)),
            then_expr=cast(ast.NumExpr, _lower_expr(expr.then_expr)),
            else_expr=cast(ast.NumExpr, _lower_expr(expr.else_expr)),
        )
    if isinstance(expr, ast.Add | ast.Sub | ast.Mul | ast.Div):
        return replace(
            expr,
            left=cast(ast.NumExpr, _lower_expr(expr.left)),
            right=cast(ast.NumExpr, _lower_expr(expr.right)),
        )
    if isinstance(expr, ast.Neg):
        return replace(expr, expr=cast(ast.NumExpr, _lower_expr(expr.expr)))
    return expr


def _lower_all_different(expr: ast.FuncCall) -> ast.Expr:
    if len(expr.args) != 1:
        return expr
    arg = expr.args[0]
    if not (
        isinstance(arg, ast.NumAggregate)
        and arg.from_comp_arg
        and isinstance(arg.comp, ast.NumComprehension)
        and len(arg.comp.binders) == 1
        and isinstance(arg.comp.binders[0], ast.CompBinder)
    ):
        return expr

    comp = arg.comp
    binder = cast(ast.CompBinder, comp.binders[0])
    left_var = f"__qsol_all_different_{binder.var}_left"
    right_var = f"__qsol_all_different_{binder.var}_right"
    left_binder = ast.CompBinder(span=binder.span, var=left_var, domain_set=binder.domain_set)
    right_binder = ast.CompBinder(span=binder.span, var=right_var, domain_set=binder.domain_set)

    left_term = _rename_expr(comp.term, {binder.var: left_var})
    right_term = _rename_expr(comp.term, {binder.var: right_var})
    term = ast.Compare(span=expr.span, op="!=", left=left_term, right=right_term)

    where: ast.BoolExpr = ast.Compare(
        span=expr.span,
        op="!=",
        left=ast.NameRef(span=binder.span, name=left_var),
        right=ast.NameRef(span=binder.span, name=right_var),
    )
    if comp.where is not None:
        left_where = cast(ast.BoolExpr, _rename_expr(comp.where, {binder.var: left_var}))
        right_where = cast(ast.BoolExpr, _rename_expr(comp.where, {binder.var: right_var}))
        where = ast.And(
            span=expr.span,
            left=where,
            right=ast.And(span=expr.span, left=left_where, right=right_where),
        )

    return ast.BoolAggregate(
        span=expr.span,
        kind="all",
        comp=ast.BoolComprehension(
            span=expr.span,
            term=term,
            binders=(left_binder, right_binder),
            where=where,
        ),
    )


def _lower_adjacent(expr: ast.FuncCall) -> ast.Expr:
    if len(expr.args) != 3 or not isinstance(expr.args[0], ast.NameRef):
        return expr
    relation = expr.args[0].name
    left, right = expr.args[1], expr.args[2]
    return ast.Or(
        span=expr.span,
        left=cast(ast.BoolExpr, ast.FuncCall(span=expr.span, name=relation, args=[left, right])),
        right=cast(ast.BoolExpr, ast.FuncCall(span=expr.span, name=relation, args=[right, left])),
    )


def _lower_nonedge(expr: ast.FuncCall) -> ast.Expr:
    if len(expr.args) != 3 or not isinstance(expr.args[0], ast.NameRef):
        return expr
    relation = expr.args[0].name
    left, right = expr.args[1], expr.args[2]
    return ast.And(
        span=expr.span,
        left=ast.Not(
            span=expr.span,
            expr=cast(
                ast.BoolExpr, ast.FuncCall(span=expr.span, name=relation, args=[left, right])
            ),
        ),
        right=ast.Not(
            span=expr.span,
            expr=cast(
                ast.BoolExpr, ast.FuncCall(span=expr.span, name=relation, args=[right, left])
            ),
        ),
    )


def _rename_expr(expr: ast.Expr, names: dict[str, str]) -> ast.Expr:
    if isinstance(expr, ast.NameRef) and expr.name in names:
        return replace(expr, name=names[expr.name])
    if isinstance(expr, ast.FuncCall):
        return replace(expr, args=[_rename_expr(arg, names) for arg in expr.args])
    if isinstance(expr, ast.MethodCall):
        return replace(
            expr,
            target=_rename_expr(expr.target, names),
            args=[_rename_expr(arg, names) for arg in expr.args],
        )
    if isinstance(expr, ast.Not):
        return replace(expr, expr=cast(ast.BoolExpr, _rename_expr(expr.expr, names)))
    if isinstance(expr, ast.And):
        return replace(
            expr,
            left=cast(ast.BoolExpr, _rename_expr(expr.left, names)),
            right=cast(ast.BoolExpr, _rename_expr(expr.right, names)),
        )
    if isinstance(expr, ast.Or):
        return replace(
            expr,
            left=cast(ast.BoolExpr, _rename_expr(expr.left, names)),
            right=cast(ast.BoolExpr, _rename_expr(expr.right, names)),
        )
    if isinstance(expr, ast.Implies):
        return replace(
            expr,
            left=cast(ast.BoolExpr, _rename_expr(expr.left, names)),
            right=cast(ast.BoolExpr, _rename_expr(expr.right, names)),
        )
    if isinstance(expr, ast.Compare):
        return replace(
            expr, left=_rename_expr(expr.left, names), right=_rename_expr(expr.right, names)
        )
    if isinstance(expr, ast.Add | ast.Sub | ast.Mul | ast.Div):
        return replace(
            expr,
            left=cast(ast.NumExpr, _rename_expr(expr.left, names)),
            right=cast(ast.NumExpr, _rename_expr(expr.right, names)),
        )
    if isinstance(expr, ast.Neg):
        return replace(expr, expr=cast(ast.NumExpr, _rename_expr(expr.expr, names)))
    if isinstance(expr, ast.IfThenElse):
        return replace(
            expr,
            cond=cast(ast.BoolExpr, _rename_expr(expr.cond, names)),
            then_expr=cast(ast.NumExpr, _rename_expr(expr.then_expr, names)),
            else_expr=cast(ast.NumExpr, _rename_expr(expr.else_expr, names)),
        )
    if isinstance(expr, ast.BoolIfThenElse):
        return replace(
            expr,
            cond=cast(ast.BoolExpr, _rename_expr(expr.cond, names)),
            then_expr=cast(ast.BoolExpr, _rename_expr(expr.then_expr, names)),
            else_expr=cast(ast.BoolExpr, _rename_expr(expr.else_expr, names)),
        )
    return expr
