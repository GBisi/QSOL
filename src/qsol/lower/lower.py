from __future__ import annotations

from qsol.lower import ir
from qsol.parse import ast


def lower_symbolic(program: ast.Program) -> ir.KernelIR:
    problems: list[ir.KProblem] = []
    for item in program.items:
        if not isinstance(item, ast.ProblemDef):
            continue

        sets: list[ir.KSetDecl] = []
        params: list[ir.KParamDecl] = []
        finds: list[ir.KFindDecl] = []
        constraints: list[ir.KConstraint] = []
        objectives: list[ir.KObjective] = []

        for stmt in item.stmts:
            if isinstance(stmt, ast.SetDecl):
                sets.append(ir.KSetDecl(span=stmt.span, name=stmt.name))
            elif isinstance(stmt, ast.ParamDecl):
                scalar_kind = (
                    stmt.value_type.kind
                    if isinstance(stmt.value_type, ast.ScalarTypeRef)
                    else "Elem"
                )
                elem_set = (
                    stmt.value_type.set_name
                    if isinstance(stmt.value_type, ast.ElemTypeRef)
                    else None
                )
                params.append(
                    ir.KParamDecl(
                        span=stmt.span,
                        name=stmt.name,
                        indices=tuple(stmt.indices),
                        scalar_kind=scalar_kind,
                        elem_set=elem_set,
                        default=stmt.default.value if stmt.default else None,
                    )
                )
            elif isinstance(stmt, ast.FindDecl):
                finds.append(
                    ir.KFindDecl(span=stmt.span, name=stmt.name, unknown_type=stmt.unknown_type)
                )
            elif isinstance(stmt, ast.Constraint):
                constraints.append(
                    ir.KConstraint(span=stmt.span, kind=stmt.kind, expr=_lower_bool(stmt.expr))
                )
            elif isinstance(stmt, ast.Objective):
                objectives.append(
                    ir.KObjective(span=stmt.span, kind=stmt.kind, expr=_lower_num(stmt.expr))
                )

        problems.append(
            ir.KProblem(
                span=item.span,
                name=item.name,
                sets=tuple(sets),
                params=tuple(params),
                finds=tuple(finds),
                constraints=tuple(constraints),
                objectives=tuple(objectives),
            )
        )

    return ir.KernelIR(span=program.span, problems=tuple(problems))


def _lower_expr(expr: ast.Expr) -> ir.KExpr:
    if isinstance(expr, ast.BoolExpr):
        return _lower_bool(expr)
    if isinstance(expr, ast.NumExpr):
        return _lower_num(expr)
    if isinstance(expr, ast.MethodCall):
        return ir.KMethodCall(
            span=expr.span,
            target=_lower_expr(expr.target),
            name=expr.name,
            args=tuple(_lower_expr(a) for a in expr.args),
        )
    if isinstance(expr, ast.FuncCall):
        return ir.KFuncCall(
            span=expr.span, name=expr.name, args=tuple(_lower_expr(a) for a in expr.args)
        )
    if isinstance(expr, ast.NameRef):
        return ir.KName(span=expr.span, name=expr.name)
    raise TypeError(f"Unsupported AST expression in lowering: {type(expr)}")


def _lower_bool(expr: ast.BoolExpr) -> ir.KBoolExpr:
    if isinstance(expr, ast.BoolLit):
        return ir.KBoolLit(span=expr.span, value=expr.value)
    if isinstance(expr, ast.Not):
        return ir.KNot(span=expr.span, expr=_lower_bool(expr.expr))
    if isinstance(expr, ast.And):
        return ir.KAnd(span=expr.span, left=_lower_bool(expr.left), right=_lower_bool(expr.right))
    if isinstance(expr, ast.Or):
        return ir.KOr(span=expr.span, left=_lower_bool(expr.left), right=_lower_bool(expr.right))
    if isinstance(expr, ast.Implies):
        return ir.KImplies(
            span=expr.span, left=_lower_bool(expr.left), right=_lower_bool(expr.right)
        )
    if isinstance(expr, ast.Compare):
        return ir.KCompare(
            span=expr.span,
            op=expr.op,
            left=_lower_expr(expr.left),
            right=_lower_expr(expr.right),
        )
    if isinstance(expr, ast.MethodCall):
        return ir.KMethodCall(
            span=expr.span,
            target=_lower_expr(expr.target),
            name=expr.name,
            args=tuple(_lower_expr(a) for a in expr.args),
        )
    if isinstance(expr, ast.FuncCall):
        return ir.KFuncCall(
            span=expr.span, name=expr.name, args=tuple(_lower_expr(a) for a in expr.args)
        )
    if isinstance(expr, ast.Quantifier):
        return ir.KQuantifier(
            span=expr.span,
            kind=expr.kind,
            var=expr.var,
            domain_set=expr.domain_set,
            expr=_lower_bool(expr.expr),
        )
    if isinstance(expr, ast.BoolIfThenElse):
        return ir.KBoolIfThenElse(
            span=expr.span,
            cond=_lower_bool(expr.cond),
            then_expr=_lower_bool(expr.then_expr),
            else_expr=_lower_bool(expr.else_expr),
        )
    if isinstance(expr, ast.NameRef):
        return ir.KName(span=expr.span, name=expr.name)
    raise TypeError(f"Unsupported bool expression: {type(expr)}")


def _lower_num(expr: ast.NumExpr) -> ir.KNumExpr:
    if isinstance(expr, ast.NumLit):
        return ir.KNumLit(span=expr.span, value=expr.value)
    if isinstance(expr, ast.Add):
        return ir.KAdd(span=expr.span, left=_lower_num(expr.left), right=_lower_num(expr.right))
    if isinstance(expr, ast.Sub):
        return ir.KSub(span=expr.span, left=_lower_num(expr.left), right=_lower_num(expr.right))
    if isinstance(expr, ast.Mul):
        return ir.KMul(span=expr.span, left=_lower_num(expr.left), right=_lower_num(expr.right))
    if isinstance(expr, ast.Div):
        return ir.KDiv(span=expr.span, left=_lower_num(expr.left), right=_lower_num(expr.right))
    if isinstance(expr, ast.Neg):
        return ir.KNeg(span=expr.span, expr=_lower_num(expr.expr))
    if isinstance(expr, ast.IfThenElse):
        return ir.KIfThenElse(
            span=expr.span,
            cond=_lower_bool(expr.cond),
            then_expr=_lower_num(expr.then_expr),
            else_expr=_lower_num(expr.else_expr),
        )
    if isinstance(expr, ast.MethodCall):
        return ir.KMethodCall(
            span=expr.span,
            target=_lower_expr(expr.target),
            name=expr.name,
            args=tuple(_lower_expr(a) for a in expr.args),
        )
    if isinstance(expr, ast.FuncCall):
        return ir.KFuncCall(
            span=expr.span, name=expr.name, args=tuple(_lower_expr(a) for a in expr.args)
        )
    if isinstance(expr, ast.NameRef):
        return ir.KName(span=expr.span, name=expr.name)
    if isinstance(expr, ast.NumAggregate):
        if not isinstance(expr.comp, ast.NumComprehension):
            raise TypeError("Count aggregate should be desugared before lowering")
        comp = ir.KNumComprehension(
            span=expr.comp.span,
            term=_lower_num(expr.comp.term),
            var=expr.comp.var,
            domain_set=expr.comp.domain_set,
        )
        return ir.KSum(span=expr.span, comp=comp)
    raise TypeError(f"Unsupported numeric expression: {type(expr)}")
