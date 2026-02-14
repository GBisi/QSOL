from __future__ import annotations

from dataclasses import replace

from qsol.parse import ast


def desugar_program(program: ast.Program) -> ast.Program:
    items: list[ast.TopItem] = []
    for item in program.items:
        if isinstance(item, ast.ProblemDef):
            stmts: list[ast.ProblemStmt] = []
            for stmt in item.stmts:
                if isinstance(stmt, ast.Constraint):
                    expr = _desugar_bool(stmt.expr)
                    if stmt.guard is not None:
                        guard = _desugar_bool(stmt.guard)
                        expr = ast.Implies(span=stmt.span, left=guard, right=expr)
                    stmts.append(replace(stmt, expr=expr, guard=None))
                elif isinstance(stmt, ast.Objective):
                    stmts.append(replace(stmt, expr=_desugar_num(stmt.expr)))
                else:
                    stmts.append(stmt)
            items.append(replace(item, stmts=stmts))
        elif isinstance(item, ast.UnknownDef):
            laws = [replace(c, expr=_desugar_bool(c.expr), guard=None) for c in item.laws_block]
            views = [replace(v, expr=_desugar_bool(v.expr)) for v in item.view_block]
            items.append(replace(item, laws_block=laws, view_block=views))
        else:
            items.append(item)
    return replace(program, items=items)


def _desugar_bool(expr: ast.BoolExpr) -> ast.BoolExpr:
    if isinstance(expr, ast.Not):
        return replace(expr, expr=_desugar_bool(expr.expr))
    if isinstance(expr, ast.And):
        return replace(expr, left=_desugar_bool(expr.left), right=_desugar_bool(expr.right))
    if isinstance(expr, ast.Or):
        return replace(expr, left=_desugar_bool(expr.left), right=_desugar_bool(expr.right))
    if isinstance(expr, ast.Implies):
        return replace(expr, left=_desugar_bool(expr.left), right=_desugar_bool(expr.right))
    if isinstance(expr, ast.Compare):
        left = _desugar_expr(expr.left)
        right = _desugar_expr(expr.right)
        return replace(expr, left=left, right=right)
    if isinstance(expr, ast.Quantifier):
        return replace(expr, expr=_desugar_bool(expr.expr))
    if isinstance(expr, ast.BoolAggregate):
        comp = expr.comp
        term = _desugar_bool(comp.term)
        where = _desugar_bool(comp.where) if comp.where is not None else None
        else_term = _desugar_bool(comp.else_term) if comp.else_term is not None else None

        if expr.kind == "any":
            body: ast.BoolExpr
            if where is None and else_term is None:
                body = term
            elif where is not None and else_term is None:
                body = ast.And(span=expr.span, left=where, right=term)
            elif where is not None and else_term is not None:
                body = ast.Or(
                    span=expr.span,
                    left=ast.And(span=expr.span, left=where, right=term),
                    right=ast.And(
                        span=expr.span, left=ast.Not(span=expr.span, expr=where), right=else_term
                    ),
                )
            else:
                body = else_term if else_term is not None else term
            return ast.Quantifier(
                span=expr.span,
                kind="exists",
                var=comp.var,
                domain_set=comp.domain_set,
                expr=body,
            )

        body_all: ast.BoolExpr
        if where is None and else_term is None:
            body_all = term
        elif where is not None and else_term is None:
            body_all = ast.Implies(span=expr.span, left=where, right=term)
        elif where is not None and else_term is not None:
            body_all = ast.And(
                span=expr.span,
                left=ast.Implies(span=expr.span, left=where, right=term),
                right=ast.Implies(
                    span=expr.span, left=ast.Not(span=expr.span, expr=where), right=else_term
                ),
            )
        else:
            body_all = else_term if else_term is not None else term
        return ast.Quantifier(
            span=expr.span,
            kind="forall",
            var=comp.var,
            domain_set=comp.domain_set,
            expr=body_all,
        )
    if isinstance(expr, ast.FuncCall):
        return replace(expr, args=[_desugar_expr(a) for a in expr.args])
    if isinstance(expr, ast.MethodCall):
        return replace(
            expr, target=_desugar_expr(expr.target), args=[_desugar_expr(a) for a in expr.args]
        )
    return expr


def _desugar_num(expr: ast.NumExpr) -> ast.NumExpr:
    if isinstance(expr, ast.Add):
        return replace(expr, left=_desugar_num(expr.left), right=_desugar_num(expr.right))
    if isinstance(expr, ast.Sub):
        return replace(expr, left=_desugar_num(expr.left), right=_desugar_num(expr.right))
    if isinstance(expr, ast.Mul):
        return replace(expr, left=_desugar_num(expr.left), right=_desugar_num(expr.right))
    if isinstance(expr, ast.Div):
        return replace(expr, left=_desugar_num(expr.left), right=_desugar_num(expr.right))
    if isinstance(expr, ast.Neg):
        return replace(expr, expr=_desugar_num(expr.expr))
    if isinstance(expr, ast.IfThenElse):
        return replace(
            expr,
            cond=_desugar_bool(expr.cond),
            then_expr=_desugar_num(expr.then_expr),
            else_expr=_desugar_num(expr.else_expr),
        )
    if isinstance(expr, ast.NumAggregate):
        if expr.kind == "count":
            comp = expr.comp
            assert isinstance(comp, ast.CountComprehension)
            one = ast.NumLit(span=comp.span, value=1)
            ncomp = ast.NumComprehension(
                span=comp.span,
                term=one,
                var=comp.var,
                domain_set=comp.domain_set,
                where=comp.where,
                else_term=None,
            )
            expr = ast.NumAggregate(span=expr.span, kind="sum", comp=ncomp)

        assert isinstance(expr.comp, ast.NumComprehension)
        comp = expr.comp
        term = _desugar_num(comp.term)
        where = _desugar_bool(comp.where) if comp.where is not None else None
        else_term = _desugar_num(comp.else_term) if comp.else_term is not None else None

        if where is not None:
            fallback = else_term if else_term is not None else ast.NumLit(span=comp.span, value=0)
            term = ast.IfThenElse(span=comp.span, cond=where, then_expr=term, else_expr=fallback)
            where = None
            else_term = None

        return ast.NumAggregate(
            span=expr.span,
            kind="sum",
            comp=ast.NumComprehension(
                span=comp.span,
                term=term,
                var=comp.var,
                domain_set=comp.domain_set,
                where=where,
                else_term=else_term,
            ),
        )

    if isinstance(expr, ast.MethodCall):
        return replace(
            expr, target=_desugar_expr(expr.target), args=[_desugar_expr(a) for a in expr.args]
        )
    if isinstance(expr, ast.FuncCall):
        return replace(expr, args=[_desugar_expr(a) for a in expr.args])
    return expr


def _desugar_expr(expr: ast.Expr) -> ast.Expr:
    if isinstance(expr, ast.BoolExpr):
        return _desugar_bool(expr)
    if isinstance(expr, ast.NumExpr):
        return _desugar_num(expr)
    return expr
