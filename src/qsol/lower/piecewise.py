from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.parse import ast


@dataclass(frozen=True, slots=True)
class PiecewiseLoweringResult:
    program: ast.Program
    diagnostics: list[Diagnostic]


@dataclass(frozen=True, slots=True)
class _Bounds:
    lo: ast.NumExpr
    hi: ast.NumExpr


def lower_piecewise_program(program: ast.Program) -> PiecewiseLoweringResult:
    diagnostics: list[Diagnostic] = []
    items: list[ast.TopItem] = []
    for item in program.items:
        if not isinstance(item, ast.ProblemDef):
            items.append(item)
            continue
        lowered, problem_diagnostics = _PiecewiseProblemLowerer(item).lower()
        diagnostics.extend(problem_diagnostics)
        items.append(lowered)
    return PiecewiseLoweringResult(program=replace(program, items=items), diagnostics=diagnostics)


class _PiecewiseProblemLowerer:
    def __init__(self, problem: ast.ProblemDef) -> None:
        self.problem = problem
        self.diagnostics: list[Diagnostic] = []
        self.generated: list[ast.ProblemStmt] = []
        self.used_names = {
            stmt.name
            for stmt in problem.stmts
            if isinstance(
                stmt,
                (ast.SetDecl, ast.RelationDecl, ast.ParamDecl, ast.FindDecl),
            )
        }
        self.bounds = _BoundAnalyzer(problem)

    def lower(self) -> tuple[ast.ProblemDef, list[Diagnostic]]:
        stmts: list[ast.ProblemStmt] = []
        for stmt in self.problem.stmts:
            if isinstance(stmt, ast.Constraint):
                stmts.extend(self._lower_constraint(stmt))
                continue
            if isinstance(stmt, ast.Objective):
                stmts.extend(self._lower_objective(stmt))
                continue
            stmts.append(stmt)

        if self.generated:
            insert_at = 0
            for idx, stmt in enumerate(stmts):
                if isinstance(stmt, (ast.SetDecl, ast.RelationDecl, ast.ParamDecl, ast.FindDecl)):
                    insert_at = idx + 1
            stmts = [*stmts[:insert_at], *self.generated, *stmts[insert_at:]]

        return replace(self.problem, stmts=stmts), self.diagnostics

    def _lower_constraint(self, stmt: ast.Constraint) -> list[ast.ProblemStmt]:
        expr = stmt.expr
        if isinstance(expr, ast.Compare):
            if _is_abs_call(expr.left) and expr.op == "<=":
                arg = _abs_arg(expr.left)
                return [
                    replace(
                        stmt, expr=ast.Compare(span=expr.span, op="<=", left=arg, right=expr.right)
                    ),
                    replace(
                        stmt,
                        expr=ast.Compare(
                            span=expr.span,
                            op="<=",
                            left=ast.Neg(span=arg.span, expr=arg),
                            right=expr.right,
                        ),
                    ),
                ]
            if _is_abs_call(expr.right) and expr.op == ">=":
                arg = _abs_arg(expr.right)
                return [
                    replace(
                        stmt, expr=ast.Compare(span=expr.span, op=">=", left=expr.left, right=arg)
                    ),
                    replace(
                        stmt,
                        expr=ast.Compare(
                            span=expr.span,
                            op=">=",
                            left=expr.left,
                            right=ast.Neg(span=arg.span, expr=arg),
                        ),
                    ),
                ]
            if _contains_piecewise_call(expr):
                self.diagnostics.append(
                    _piecewise_error(
                        expr.span,
                        "unsupported piecewise constraint context",
                        [
                            "Supported first-pass constraints use `must abs(expr) <= C` "
                            "or equivalent `must C >= abs(expr)`.",
                        ],
                    )
                )
        elif _contains_piecewise_call(expr):
            self.diagnostics.append(
                _piecewise_error(
                    stmt.span,
                    "unsupported piecewise constraint context",
                    ["Rewrite piecewise constraints as a supported comparison form."],
                )
            )
        return [stmt]

    def _lower_objective(self, stmt: ast.Objective) -> list[ast.ProblemStmt]:
        expr = stmt.expr
        if isinstance(expr, ast.FuncCall) and _is_abs_call(expr):
            if stmt.kind != ast.ObjectiveKind.MINIMIZE:
                self.diagnostics.append(
                    _piecewise_error(
                        stmt.span,
                        "maximize abs() is not supported by first-pass piecewise lowering",
                        ["Use `minimize abs(expr)` or add an explicit bounded reformulation."],
                    )
                )
                return [stmt]
            return self._lower_abs_objective(stmt, _abs_arg(expr))

        if isinstance(expr, ast.FuncCall) and _is_aggregate_call(expr, "max"):
            if stmt.kind != ast.ObjectiveKind.MINIMIZE:
                self.diagnostics.append(
                    _piecewise_error(
                        stmt.span,
                        "maximize max() is not supported by first-pass piecewise lowering",
                        [
                            "Use `minimize max(term for ...)` for compiler-generated epigraph lowering."
                        ],
                    )
                )
                return [stmt]
            return self._lower_extreme_objective(stmt, call=expr, prefix="max", compare_op=">=")

        if isinstance(expr, ast.FuncCall) and _is_aggregate_call(expr, "min"):
            if stmt.kind != ast.ObjectiveKind.MAXIMIZE:
                self.diagnostics.append(
                    _piecewise_error(
                        stmt.span,
                        "minimize min() is not supported by first-pass piecewise lowering",
                        [
                            "Use `maximize min(term for ...)` for compiler-generated hypograph lowering."
                        ],
                    )
                )
                return [stmt]
            return self._lower_extreme_objective(stmt, call=expr, prefix="min", compare_op="<=")

        if _contains_piecewise_call(expr):
            self.diagnostics.append(
                _piecewise_error(
                    stmt.span,
                    "unsupported piecewise objective context",
                    [
                        "Supported first-pass objectives are `minimize abs(expr)`, "
                        "`minimize max(term for ...)`, and `maximize min(term for ...)`.",
                    ],
                )
            )
        return [stmt]

    def _lower_abs_objective(self, stmt: ast.Objective, arg: ast.NumExpr) -> list[ast.ProblemStmt]:
        bounds = self.bounds.num_bounds(arg, {})
        if bounds is None:
            self.diagnostics.append(
                _piecewise_error(
                    stmt.span,
                    "missing finite bounds for abs() auxiliary variable",
                    ["Use bounded Int decisions and bounded Int params inside `abs(...)`."],
                )
            )
            return [stmt]
        aux_name = self._new_aux_name("abs")
        upper = _max_abs_bound(stmt.span, bounds)
        if upper is None:
            self.diagnostics.append(
                _piecewise_error(
                    stmt.span,
                    "missing finite bounds for abs() auxiliary variable",
                    ["The current compiler requires literal lower/upper bounds for `abs(...)`."],
                )
            )
            return [stmt]
        aux_ref = ast.NameRef(span=stmt.span, name=aux_name)
        self.generated.append(
            ast.FindDecl(
                span=stmt.span,
                name=aux_name,
                decision_type=ast.IntDecisionType(
                    span=stmt.span,
                    lo=ast.NumLit(span=stmt.span, value=0),
                    hi=upper,
                ),
            )
        )
        return [
            ast.Constraint(
                span=stmt.span,
                kind=ast.ConstraintKind.MUST,
                expr=ast.Compare(span=stmt.span, op=">=", left=aux_ref, right=arg),
            ),
            ast.Constraint(
                span=stmt.span,
                kind=ast.ConstraintKind.MUST,
                expr=ast.Compare(
                    span=stmt.span,
                    op=">=",
                    left=aux_ref,
                    right=ast.Neg(span=arg.span, expr=arg),
                ),
            ),
            replace(stmt, expr=cast(ast.NumExpr, aux_ref)),
        ]

    def _lower_extreme_objective(
        self,
        stmt: ast.Objective,
        *,
        call: ast.FuncCall,
        prefix: str,
        compare_op: str,
    ) -> list[ast.ProblemStmt]:
        comp = _aggregate_call_comp(call)
        assert comp is not None
        binder_bounds = self.bounds.extend_binders({}, comp.binders)
        term_bounds = self.bounds.num_bounds(comp.term, binder_bounds)
        if term_bounds is None:
            self.diagnostics.append(
                _piecewise_error(
                    stmt.span,
                    f"missing finite bounds for {prefix}() auxiliary variable",
                    ["Use bounded Int terms inside compiler-lowered min()/max() aggregates."],
                )
            )
            return [stmt]

        aux_name = self._new_aux_name(prefix)
        aux_ref = ast.NameRef(span=stmt.span, name=aux_name)
        self.generated.append(
            ast.FindDecl(
                span=stmt.span,
                name=aux_name,
                decision_type=ast.IntDecisionType(
                    span=stmt.span,
                    lo=term_bounds.lo,
                    hi=term_bounds.hi,
                ),
            )
        )
        body = ast.Compare(
            span=call.span,
            op=compare_op,
            left=aux_ref,
            right=comp.term,
        )
        quantified = _quantify_binders(span=call.span, binders=comp.binders, body=body)
        return [
            ast.Constraint(span=stmt.span, kind=ast.ConstraintKind.MUST, expr=quantified),
            replace(stmt, expr=cast(ast.NumExpr, aux_ref)),
        ]

    def _new_aux_name(self, kind: str) -> str:
        idx = 0
        while True:
            name = f"__qsol_piecewise_{kind}_{idx}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
            idx += 1


class _BoundAnalyzer:
    def __init__(self, problem: ast.ProblemDef) -> None:
        self.sets = {stmt.name: stmt for stmt in problem.stmts if isinstance(stmt, ast.SetDecl)}
        self.params = {stmt.name: stmt for stmt in problem.stmts if isinstance(stmt, ast.ParamDecl)}
        self.finds = {stmt.name: stmt for stmt in problem.stmts if isinstance(stmt, ast.FindDecl)}
        self.relations = {
            stmt.name: stmt for stmt in problem.stmts if isinstance(stmt, ast.RelationDecl)
        }

    def extend_binders(
        self,
        binders: dict[str, _Bounds],
        comp_binders: tuple[ast.CompBinder | ast.TupleCompBinder, ...],
    ) -> dict[str, _Bounds]:
        out = dict(binders)
        for binder in comp_binders:
            if isinstance(binder, ast.CompBinder):
                domain_bounds = self._set_elem_bounds(binder.domain_set)
                if domain_bounds is not None:
                    out[binder.var] = domain_bounds
                continue
            relation = self.relations.get(binder.domain_relation)
            if relation is None:
                continue
            for name, field in zip(binder.vars, relation.fields, strict=False):
                field_bounds = self._set_elem_bounds(field.set_name)
                if field_bounds is not None:
                    out[name] = field_bounds
        return out

    def num_bounds(self, expr: ast.Expr, binders: dict[str, _Bounds]) -> _Bounds | None:
        if isinstance(expr, ast.NumLit):
            return _Bounds(expr, expr)
        if isinstance(expr, ast.NameRef):
            if expr.name in binders:
                return binders[expr.name]
            return self._symbol_bounds(expr.name)
        if isinstance(expr, ast.FuncCall):
            return self._func_bounds(expr, binders)
        if isinstance(expr, ast.MethodCall):
            if expr.name in {"has", "is"}:
                return _Bounds(_lit(expr.span, 0), _lit(expr.span, 1))
            return None
        if isinstance(expr, ast.Add):
            return _combine_bounds(
                expr.span,
                self.num_bounds(expr.left, binders),
                self.num_bounds(expr.right, binders),
                "+",
            )
        if isinstance(expr, ast.Sub):
            return _combine_bounds(
                expr.span,
                self.num_bounds(expr.left, binders),
                self.num_bounds(expr.right, binders),
                "-",
            )
        if isinstance(expr, ast.Neg):
            inner = self.num_bounds(expr.expr, binders)
            if inner is None:
                return None
            return _Bounds(_neg(inner.hi), _neg(inner.lo))
        if isinstance(expr, ast.Mul):
            return _mul_bounds(
                expr.span, self.num_bounds(expr.left, binders), self.num_bounds(expr.right, binders)
            )
        if isinstance(expr, ast.Div):
            right = self.num_bounds(expr.right, binders)
            if right is None or right.lo != right.hi:
                return None
            denominator = _literal_value(right.lo)
            if denominator is None or denominator == 0:
                return None
            left = self.num_bounds(expr.left, binders)
            if left is None:
                return None
            return _scale_bounds(expr.span, left, 1 / denominator)
        if isinstance(expr, ast.IfThenElse):
            then_bounds = self.num_bounds(expr.then_expr, binders)
            else_bounds = self.num_bounds(expr.else_expr, binders)
            if then_bounds is None or else_bounds is None:
                return None
            return _Bounds(
                _min_literal(expr.span, then_bounds.lo, else_bounds.lo),
                _max_literal(expr.span, then_bounds.hi, else_bounds.hi),
            )
        if isinstance(expr, ast.NumAggregate) and isinstance(expr.comp, ast.NumComprehension):
            binder_scope = self.extend_binders(binders, expr.comp.binders)
            term = self.num_bounds(expr.comp.term, binder_scope)
            if term is None:
                return None
            return _Bounds(
                ast.NumAggregate(
                    span=expr.span,
                    kind="sum",
                    comp=ast.NumComprehension(
                        span=expr.comp.span,
                        term=term.lo,
                        binders=expr.comp.binders,
                    ),
                ),
                ast.NumAggregate(
                    span=expr.span,
                    kind="sum",
                    comp=ast.NumComprehension(
                        span=expr.comp.span,
                        term=term.hi,
                        binders=expr.comp.binders,
                    ),
                ),
            )
        return None

    def _func_bounds(self, expr: ast.FuncCall, binders: dict[str, _Bounds]) -> _Bounds | None:
        if expr.name == "indicator" and len(expr.args) == 1:
            return _Bounds(_lit(expr.span, 0), _lit(expr.span, 1))
        if expr.name == "size" and len(expr.args) == 1:
            return _Bounds(_lit(expr.span, 0), _lit(expr.span, 2**31 - 1))
        if expr.call_style == "bracket":
            return self._symbol_bounds(expr.name)
        if expr.name == "abs" and len(expr.args) == 1:
            inner = self.num_bounds(expr.args[0], binders)
            if inner is None:
                return None
            upper = _max_abs_bound(expr.span, inner)
            return None if upper is None else _Bounds(_lit(expr.span, 0), upper)
        return None

    def _symbol_bounds(self, name: str) -> _Bounds | None:
        param = self.params.get(name)
        if param is not None and isinstance(param.value_type, ast.ScalarTypeRef):
            if param.value_type.kind == "Bool":
                return _Bounds(_lit(param.span, 0), _lit(param.span, 1))
            if param.value_type.kind == "Int":
                return _Bounds(
                    _lit(param.span, param.value_type.lo or 0),
                    _lit(param.span, param.value_type.hi or 0),
                )

        find = self.finds.get(name)
        if find is not None:
            if isinstance(find.decision_type, ast.BoolDecisionType):
                return _Bounds(_lit(find.span, 0), _lit(find.span, 1))
            if isinstance(find.decision_type, ast.IntDecisionType):
                return _Bounds(find.decision_type.lo, find.decision_type.hi)
        return None

    def _set_elem_bounds(self, set_name: str) -> _Bounds | None:
        set_decl = self.sets.get(set_name)
        if set_decl is None or not isinstance(set_decl.expr, ast.RangeSetExpr):
            return None
        return _Bounds(set_decl.expr.lo, set_decl.expr.hi)


def _quantify_binders(
    *,
    span: object,
    binders: tuple[ast.CompBinder | ast.TupleCompBinder, ...],
    body: ast.BoolExpr,
) -> ast.BoolExpr:
    out = body
    for binder in reversed(binders):
        if isinstance(binder, ast.TupleCompBinder):
            out = ast.TupleQuantifier(
                span=binder.span,
                kind="forall",
                vars=binder.vars,
                domain_relation=binder.domain_relation,
                expr=out,
            )
        else:
            out = ast.Quantifier(
                span=binder.span,
                kind="forall",
                var=binder.var,
                domain_set=binder.domain_set,
                expr=out,
            )
    return out


def _is_abs_call(expr: ast.Expr) -> bool:
    return isinstance(expr, ast.FuncCall) and expr.name == "abs" and len(expr.args) == 1


def _abs_arg(expr: ast.Expr) -> ast.NumExpr:
    assert isinstance(expr, ast.FuncCall)
    return cast(ast.NumExpr, expr.args[0])


def _is_aggregate_call(expr: ast.Expr, name: str) -> bool:
    return _aggregate_call_comp(expr if isinstance(expr, ast.FuncCall) else None, name) is not None


def _aggregate_call_comp(
    call: ast.FuncCall | None, name: str | None = None
) -> ast.NumComprehension | None:
    if call is None or (name is not None and call.name != name) or len(call.args) != 1:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.NumAggregate) and isinstance(arg.comp, ast.NumComprehension):
        return arg.comp
    return None


def _contains_piecewise_call(expr: ast.Expr) -> bool:
    if isinstance(expr, ast.FuncCall):
        if expr.name in {"abs", "min", "max"}:
            return True
        return any(_contains_piecewise_call(arg) for arg in expr.args)
    if isinstance(expr, ast.MethodCall):
        return _contains_piecewise_call(expr.target) or any(
            _contains_piecewise_call(arg) for arg in expr.args
        )
    if isinstance(expr, (ast.Not, ast.Neg)):
        return _contains_piecewise_call(expr.expr)
    if isinstance(
        expr, (ast.And, ast.Or, ast.Implies, ast.Compare, ast.Add, ast.Sub, ast.Mul, ast.Div)
    ):
        return _contains_piecewise_call(expr.left) or _contains_piecewise_call(expr.right)
    if isinstance(expr, (ast.IfThenElse, ast.BoolIfThenElse)):
        return (
            _contains_piecewise_call(expr.cond)
            or _contains_piecewise_call(expr.then_expr)
            or _contains_piecewise_call(expr.else_expr)
        )
    if isinstance(expr, ast.NumAggregate) and isinstance(expr.comp, ast.NumComprehension):
        return _contains_piecewise_call(expr.comp.term)
    if isinstance(expr, ast.BoolAggregate):
        return _contains_piecewise_call(expr.comp.term)
    return False


def _piecewise_error(span: object, message: str, help_items: list[str]) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL3101",
        message=message,
        span=span,  # type: ignore[arg-type]
        help=help_items,
    )


def _lit(span: object, value: float | int) -> ast.NumLit:
    return ast.NumLit(span=span, value=float(value))  # type: ignore[arg-type]


def _neg(expr: ast.NumExpr) -> ast.NumExpr:
    if isinstance(expr, ast.NumLit):
        return ast.NumLit(span=expr.span, value=-expr.value)
    return ast.Neg(span=expr.span, expr=expr)


def _combine_bounds(
    span: object, left: _Bounds | None, right: _Bounds | None, op: str
) -> _Bounds | None:
    if left is None or right is None:
        return None
    if op == "+":
        return _Bounds(
            _add_expr(span, left.lo, right.lo),
            _add_expr(span, left.hi, right.hi),
        )
    return _Bounds(
        _sub_expr(span, left.lo, right.hi),
        _sub_expr(span, left.hi, right.lo),
    )


def _mul_bounds(span: object, left: _Bounds | None, right: _Bounds | None) -> _Bounds | None:
    if left is None or right is None:
        return None
    left_const = _literal_value(left.lo) if left.lo == left.hi else None
    right_const = _literal_value(right.lo) if right.lo == right.hi else None
    if left_const is not None:
        return _scale_bounds(span, right, left_const)
    if right_const is not None:
        return _scale_bounds(span, left, right_const)
    products = [
        _literal_product(left.lo, right.lo),
        _literal_product(left.lo, right.hi),
        _literal_product(left.hi, right.lo),
        _literal_product(left.hi, right.hi),
    ]
    if any(value is None for value in products):
        return None
    numbers = [value for value in products if value is not None]
    return _Bounds(_lit(span, min(numbers)), _lit(span, max(numbers)))


def _scale_bounds(span: object, bounds: _Bounds, factor: float) -> _Bounds:
    lo = _mul_expr(span, _lit(span, factor), bounds.lo)
    hi = _mul_expr(span, _lit(span, factor), bounds.hi)
    return _Bounds(lo, hi) if factor >= 0 else _Bounds(hi, lo)


def _add_expr(span: object, left: ast.NumExpr, right: ast.NumExpr) -> ast.NumExpr:
    left_value = _literal_value(left)
    right_value = _literal_value(right)
    if left_value is not None and right_value is not None:
        return _lit(span, left_value + right_value)
    return ast.Add(span=span, left=left, right=right)  # type: ignore[arg-type]


def _sub_expr(span: object, left: ast.NumExpr, right: ast.NumExpr) -> ast.NumExpr:
    left_value = _literal_value(left)
    right_value = _literal_value(right)
    if left_value is not None and right_value is not None:
        return _lit(span, left_value - right_value)
    return ast.Sub(span=span, left=left, right=right)  # type: ignore[arg-type]


def _mul_expr(span: object, left: ast.NumExpr, right: ast.NumExpr) -> ast.NumExpr:
    product = _literal_product(left, right)
    if product is not None:
        return _lit(span, product)
    return ast.Mul(span=span, left=left, right=right)  # type: ignore[arg-type]


def _literal_product(left: ast.NumExpr, right: ast.NumExpr) -> float | None:
    left_value = _literal_value(left)
    right_value = _literal_value(right)
    if left_value is None or right_value is None:
        return None
    return left_value * right_value


def _literal_value(expr: ast.NumExpr) -> float | None:
    return expr.value if isinstance(expr, ast.NumLit) else None


def _min_literal(span: object, left: ast.NumExpr, right: ast.NumExpr) -> ast.NumExpr:
    left_value = _literal_value(left)
    right_value = _literal_value(right)
    if left_value is None or right_value is None:
        return left
    return _lit(span, min(left_value, right_value))


def _max_literal(span: object, left: ast.NumExpr, right: ast.NumExpr) -> ast.NumExpr:
    left_value = _literal_value(left)
    right_value = _literal_value(right)
    if left_value is None or right_value is None:
        return right
    return _lit(span, max(left_value, right_value))


def _max_abs_bound(span: object, bounds: _Bounds) -> ast.NumExpr | None:
    lo = _literal_value(bounds.lo)
    hi = _literal_value(bounds.hi)
    if lo is None or hi is None:
        return None
    return _lit(span, max(abs(lo), abs(hi)))
