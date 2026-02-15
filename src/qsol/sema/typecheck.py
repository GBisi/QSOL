from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.parse import ast
from qsol.sema.symbols import Scope, Symbol, SymbolKind, SymbolTable
from qsol.sema.types import (
    BOOL,
    REAL,
    UNKNOWN,
    ElemOfType,
    IntRangeType,
    ParamType,
    Type,
    UnknownInstanceType,
    UnknownType,
    is_numeric,
    promote_numeric,
)


@dataclass(slots=True)
class TypeCheckResult:
    typed_program: ast.TypedProgram
    diagnostics: list[Diagnostic] = field(default_factory=list)


class TypeChecker:
    def check(self, program: ast.Program, symbols: SymbolTable) -> TypeCheckResult:
        diagnostics: list[Diagnostic] = []
        typed = ast.TypedProgram(span=program.span, program=program, types={})

        for item in program.items:
            if isinstance(item, ast.ProblemDef):
                scope = symbols.problem_scopes.get(item.name)
                if scope is None:
                    continue
                for stmt in item.stmts:
                    if isinstance(stmt, ast.Constraint):
                        expr_ty = self._expr_type(stmt.expr, scope, {}, diagnostics, typed.types)
                        if not isinstance(expr_ty, type(BOOL)):
                            diagnostics.append(
                                self._type_err(stmt.expr.span, "constraint expression must be Bool")
                            )
                        if stmt.guard is not None:
                            guard_ty = self._expr_type(
                                stmt.guard, scope, {}, diagnostics, typed.types
                            )
                            if not isinstance(guard_ty, type(BOOL)):
                                diagnostics.append(
                                    self._type_err(stmt.guard.span, "guard expression must be Bool")
                                )
                    elif isinstance(stmt, ast.Objective):
                        expr_ty = self._expr_type(stmt.expr, scope, {}, diagnostics, typed.types)
                        if not is_numeric(expr_ty):
                            diagnostics.append(
                                self._type_err(
                                    stmt.expr.span, "objective expression must be numeric"
                                )
                            )
                    elif isinstance(stmt, ast.ParamDecl) and stmt.default is not None:
                        if isinstance(stmt.value_type, ast.ElemTypeRef):
                            diagnostics.append(
                                self._type_err(
                                    stmt.default.span,
                                    "set-valued params do not support defaults",
                                )
                            )
                        else:
                            default_ty = self._literal_type(stmt.default)
                            decl_ty = self._param_decl_type(stmt)
                            if not self._compatible(decl_ty, default_ty):
                                diagnostics.append(
                                    self._type_err(stmt.default.span, "param default type mismatch")
                                )

        return TypeCheckResult(typed_program=typed, diagnostics=diagnostics)

    def _expr_type(
        self,
        expr: ast.Expr,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        out: Type = UNKNOWN

        if isinstance(expr, ast.BoolLit):
            out = BOOL
        elif isinstance(expr, ast.NumLit):
            out = REAL
        elif isinstance(expr, ast.StringLit):
            out = UnknownType()
        elif isinstance(expr, ast.Literal):
            if isinstance(expr.value, bool):
                out = BOOL
            elif isinstance(expr.value, (int, float)):
                out = REAL
            else:
                out = UnknownType()
        elif isinstance(expr, ast.NameRef):
            if expr.name in binders:
                out = binders[expr.name]
            else:
                symbol = scope.lookup(expr.name)
                if symbol is None:
                    candidates = sorted({*binders.keys(), *self._scope_names(scope)})
                    suggestion = self._did_you_mean(expr.name, candidates)
                    help_items = [
                        "Declare the identifier in the problem scope or bind it in a quantifier/comprehension."
                    ]
                    if suggestion is not None:
                        help_items.append(f"Did you mean `{suggestion}`?")
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2001",
                            message=f"unknown identifier `{expr.name}`",
                            span=expr.span,
                            help=help_items,
                        )
                    )
                    out = UNKNOWN
                else:
                    if (
                        symbol.kind == SymbolKind.PARAM
                        and isinstance(symbol.type, ParamType)
                        and not symbol.type.indices
                    ):
                        out = symbol.type.elem
                    else:
                        out = symbol.type
        elif isinstance(expr, ast.Not):
            sub = self._expr_type(expr.expr, scope, binders, diagnostics, tmap)
            if not isinstance(sub, type(BOOL)):
                diagnostics.append(self._type_err(expr.span, "`not` requires Bool"))
            out = BOOL
        elif isinstance(expr, (ast.And, ast.Or, ast.Implies)):
            left = self._expr_type(expr.left, scope, binders, diagnostics, tmap)
            right = self._expr_type(expr.right, scope, binders, diagnostics, tmap)
            if not isinstance(left, type(BOOL)) or not isinstance(right, type(BOOL)):
                diagnostics.append(
                    self._type_err(expr.span, "boolean operator requires Bool operands")
                )
            out = BOOL
        elif isinstance(expr, ast.Compare):
            left = self._expr_type(expr.left, scope, binders, diagnostics, tmap)
            right = self._expr_type(expr.right, scope, binders, diagnostics, tmap)
            if expr.op in {"<", "<=", ">", ">="}:
                if not is_numeric(left) or not is_numeric(right):
                    diagnostics.append(
                        self._type_err(expr.span, "comparison requires numeric operands")
                    )
            elif expr.op in {"=", "!="}:
                ok = (is_numeric(left) and is_numeric(right)) or (
                    isinstance(left, type(BOOL)) and isinstance(right, type(BOOL))
                )
                same_elem = (
                    isinstance(left, ElemOfType)
                    and isinstance(right, ElemOfType)
                    and left.set_name == right.set_name
                )
                if not ok:
                    if not same_elem:
                        diagnostics.append(
                            self._type_err(
                                expr.span,
                                "equality requires matching Bool, numeric, or same-set element operands",
                            )
                        )
            out = BOOL
        elif isinstance(expr, ast.FuncCall):
            if expr.name == "size":
                out = self._size_call_type(expr, scope, binders, diagnostics, tmap)
            else:
                symbol = scope.lookup(expr.name)
                if (
                    symbol is not None
                    and symbol.kind == SymbolKind.PARAM
                    and isinstance(symbol.type, ParamType)
                ):
                    out = self._param_call_type(
                        expr, symbol.type, scope, binders, diagnostics, tmap
                    )
                else:
                    for arg in expr.args:
                        self._expr_type(arg, scope, binders, diagnostics, tmap)
                    if expr.name in {"exactly_one", "at_most_one", "and", "or"}:
                        out = BOOL
                    else:
                        out = BOOL
        elif isinstance(expr, ast.MethodCall):
            target_ty = self._expr_type(expr.target, scope, binders, diagnostics, tmap)
            out = self._method_type(expr, target_ty, scope, binders, diagnostics, tmap)
        elif isinstance(expr, (ast.Add, ast.Sub, ast.Mul, ast.Div)):
            left = self._expr_type(expr.left, scope, binders, diagnostics, tmap)
            right = self._expr_type(expr.right, scope, binders, diagnostics, tmap)
            promoted = promote_numeric(left, right)
            if promoted is None:
                diagnostics.append(
                    self._type_err(expr.span, "arithmetic requires numeric operands")
                )
                out = UNKNOWN
            else:
                out = promoted
        elif isinstance(expr, ast.Neg):
            sub = self._expr_type(expr.expr, scope, binders, diagnostics, tmap)
            if not is_numeric(sub):
                diagnostics.append(
                    self._type_err(expr.span, "unary minus requires numeric operand")
                )
            out = sub
        elif isinstance(expr, ast.IfThenElse):
            cond = self._expr_type(expr.cond, scope, binders, diagnostics, tmap)
            then_ty = self._expr_type(expr.then_expr, scope, binders, diagnostics, tmap)
            else_ty = self._expr_type(expr.else_expr, scope, binders, diagnostics, tmap)
            if not isinstance(cond, type(BOOL)):
                diagnostics.append(self._type_err(expr.cond.span, "if condition must be Bool"))
            promoted = promote_numeric(then_ty, else_ty)
            if promoted is None:
                diagnostics.append(self._type_err(expr.span, "if branches must be numeric"))
                out = UNKNOWN
            else:
                out = promoted
        elif isinstance(expr, ast.Quantifier):
            binder_ty = ElemOfType(set_name=expr.domain_set)
            body_scope = dict(binders)
            body_scope[expr.var] = binder_ty
            body_ty = self._expr_type(expr.expr, scope, body_scope, diagnostics, tmap)
            if not isinstance(body_ty, type(BOOL)):
                diagnostics.append(self._type_err(expr.expr.span, "quantifier body must be Bool"))
            if self._lookup_set(scope, expr.domain_set) is None:
                suggestion = self._did_you_mean(expr.domain_set, self._set_names(scope))
                help_items = [f"Declare set `{expr.domain_set}` before using it in quantifiers."]
                if suggestion is not None:
                    help_items.append(f"Did you mean `{suggestion}`?")
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2001",
                        message=f"unknown set `{expr.domain_set}` in quantifier",
                        span=expr.span,
                        help=help_items,
                    )
                )
            out = BOOL
        elif isinstance(expr, ast.BoolAggregate):
            binder_ty = ElemOfType(set_name=expr.comp.domain_set)
            inner = dict(binders)
            inner[expr.comp.var] = binder_ty
            term_ty = self._expr_type(expr.comp.term, scope, inner, diagnostics, tmap)
            if not isinstance(term_ty, type(BOOL)):
                diagnostics.append(
                    self._type_err(expr.comp.term.span, "boolean aggregate term must be Bool")
                )
            if expr.comp.where is not None:
                where_ty = self._expr_type(expr.comp.where, scope, inner, diagnostics, tmap)
                if not isinstance(where_ty, type(BOOL)):
                    diagnostics.append(
                        self._type_err(expr.comp.where.span, "where clause must be Bool")
                    )
            if expr.comp.else_term is not None:
                else_ty = self._expr_type(expr.comp.else_term, scope, inner, diagnostics, tmap)
                if not isinstance(else_ty, type(BOOL)):
                    diagnostics.append(
                        self._type_err(expr.comp.else_term.span, "else term must be Bool")
                    )
            out = BOOL
        elif isinstance(expr, ast.NumAggregate):
            if isinstance(expr.comp, ast.NumComprehension):
                binder_ty = ElemOfType(set_name=expr.comp.domain_set)
                inner = dict(binders)
                inner[expr.comp.var] = binder_ty
                term_ty = self._expr_type(expr.comp.term, scope, inner, diagnostics, tmap)
                if not is_numeric(term_ty):
                    diagnostics.append(
                        self._type_err(expr.comp.term.span, "sum term must be numeric")
                    )
                if expr.comp.where is not None:
                    where_ty = self._expr_type(expr.comp.where, scope, inner, diagnostics, tmap)
                    if not isinstance(where_ty, type(BOOL)):
                        diagnostics.append(
                            self._type_err(expr.comp.where.span, "where clause must be Bool")
                        )
                if expr.comp.else_term is not None:
                    else_ty = self._expr_type(expr.comp.else_term, scope, inner, diagnostics, tmap)
                    if not is_numeric(else_ty):
                        diagnostics.append(
                            self._type_err(expr.comp.else_term.span, "else term must be numeric")
                        )
                out = REAL if expr.kind == "sum" else IntRangeType(0, 2**31 - 1)
            else:
                binder_ty = ElemOfType(set_name=expr.comp.domain_set)
                inner = dict(binders)
                inner[expr.comp.var] = binder_ty
                if expr.comp.var_ref != expr.comp.var:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2101",
                            message="count binder and counted variable must match",
                            span=expr.comp.span,
                        )
                    )
                if expr.comp.where is not None:
                    where_ty = self._expr_type(expr.comp.where, scope, inner, diagnostics, tmap)
                    if not isinstance(where_ty, type(BOOL)):
                        diagnostics.append(
                            self._type_err(expr.comp.where.span, "count where clause must be Bool")
                        )
                out = IntRangeType(0, 2**31 - 1)
        else:
            out = UNKNOWN

        tmap[id(expr)] = self._repr_type(out)
        return out

    def _method_type(
        self,
        expr: ast.MethodCall,
        target_ty: Type,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        if not isinstance(target_ty, UnknownInstanceType):
            diagnostics.append(
                self._type_err(expr.span, "method call target is not an unknown instance")
            )
            for arg in expr.args:
                self._expr_type(arg, scope, binders, diagnostics, tmap)
            return UNKNOWN

        ref_name = target_ty.ref.name
        if ref_name == "Subset" and expr.name == "has":
            if len(expr.args) != 1:
                diagnostics.append(self._type_err(expr.span, "Subset.has expects one argument"))
            else:
                arg_ty = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
                expected_set = target_ty.ref.args[0] if target_ty.ref.args else ""
                if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                    diagnostics.append(
                        self._type_err(
                            expr.args[0].span, f"expected element of set `{expected_set}`"
                        )
                    )
            return BOOL

        if ref_name == "Mapping" and expr.name == "is":
            if len(expr.args) != 2:
                diagnostics.append(self._type_err(expr.span, "Mapping.is expects two arguments"))
            else:
                dom = target_ty.ref.args[0] if len(target_ty.ref.args) > 0 else ""
                cod = target_ty.ref.args[1] if len(target_ty.ref.args) > 1 else ""
                lhs = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
                rhs = self._expr_type(expr.args[1], scope, binders, diagnostics, tmap)
                if not isinstance(lhs, ElemOfType) or lhs.set_name != dom:
                    diagnostics.append(
                        self._type_err(expr.args[0].span, f"expected element of `{dom}`")
                    )
                if not isinstance(rhs, ElemOfType) or rhs.set_name != cod:
                    diagnostics.append(
                        self._type_err(expr.args[1].span, f"expected element of `{cod}`")
                    )
            return BOOL

        for arg in expr.args:
            self._expr_type(arg, scope, binders, diagnostics, tmap)
        return BOOL

    def _param_call_type(
        self,
        expr: ast.FuncCall,
        ptype: ParamType,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        expected_arity = len(ptype.indices)
        if expected_arity == 0:
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"scalar param `{expr.name}` must be referenced as `{expr.name}` (bare name)",
                )
            )
            for arg in expr.args:
                self._expr_type(arg, scope, binders, diagnostics, tmap)
            return ptype.elem

        if len(expr.args) != expected_arity:
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"param call `{expr.name}` expects {expected_arity} argument(s)",
                )
            )
        for i, arg in enumerate(expr.args):
            arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
            if i >= expected_arity:
                continue
            expected_set = ptype.indices[i].name
            if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                diagnostics.append(
                    self._type_err(arg.span, f"expected element of `{expected_set}`")
                )
        return ptype.elem

    def _size_call_type(
        self,
        expr: ast.FuncCall,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        if len(expr.args) != 1:
            for arg in expr.args:
                self._expr_type(arg, scope, binders, diagnostics, tmap)
            diagnostics.append(self._type_err(expr.span, "size() expects exactly one argument"))
            return UNKNOWN

        arg = expr.args[0]
        if not isinstance(arg, ast.NameRef):
            self._expr_type(arg, scope, binders, diagnostics, tmap)
            diagnostics.append(
                self._type_err(
                    arg.span,
                    "size() expects a declared set identifier",
                )
            )
            return UNKNOWN

        symbol = scope.lookup(arg.name)
        if symbol is None or symbol.kind != SymbolKind.SET:
            diagnostics.append(
                self._type_err(
                    arg.span,
                    f"size() expects a declared set identifier, got `{arg.name}`",
                )
            )
            return UNKNOWN
        return IntRangeType(0, 2**31 - 1)

    def _lookup_set(self, scope: Scope, name: str) -> Symbol | None:
        sym = scope.lookup(name)
        if sym is None or sym.kind != SymbolKind.SET:
            return None
        return sym

    def _literal_type(self, lit: ast.Literal) -> Type:
        if isinstance(lit.value, bool):
            return BOOL
        if isinstance(lit.value, (int, float)):
            return REAL
        return UnknownType()

    def _param_decl_type(self, stmt: ast.ParamDecl) -> Type:
        if isinstance(stmt.value_type, ast.ElemTypeRef):
            return ElemOfType(stmt.value_type.set_name)

        scalar = stmt.value_type
        if scalar.kind == "Bool":
            return BOOL
        if scalar.kind == "Real":
            return REAL
        lo = scalar.lo or -(2**31)
        hi = scalar.hi or (2**31 - 1)
        return IntRangeType(lo=lo, hi=hi)

    def _compatible(self, left: Type, right: Type) -> bool:
        if isinstance(left, IntRangeType) and isinstance(right, IntRangeType):
            return True
        if isinstance(left, type(BOOL)) and isinstance(right, type(BOOL)):
            return True
        if is_numeric(left) and is_numeric(right):
            return True
        return False

    def _type_err(self, span: Span, message: str) -> Diagnostic:
        return Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2101",
            message=message,
            span=span,
            help=self._help_for_type_message(message),
        )

    def _help_for_type_message(self, message: str) -> list[str]:
        if message == "size() expects exactly one argument":
            return ["Use `size(SetName)` with one declared set identifier."]
        if message.startswith("size() expects a declared set identifier"):
            return ["Pass a declared set name, for example `size(V)`."]
        if message == "boolean operator requires Bool operands":
            return ["Convert both operands to Bool expressions before using boolean operators."]
        if message == "comparison requires numeric operands":
            return ["Use numeric operands on both sides of `<`, `<=`, `>`, and `>=`."]
        if message.startswith("param call `") and "expects" in message:
            return ["Pass one argument per declared index dimension of the parameter."]
        if message.startswith("scalar param `"):
            return ["Reference scalar params as bare names, not as calls."]
        if message == "constraint expression must be Bool":
            return ["`must`, `should`, and `nice` constraints require Bool expressions."]
        if message == "objective expression must be numeric":
            return ["`minimize` and `maximize` require numeric expressions."]
        if message == "arithmetic requires numeric operands":
            return ["Ensure all operands are numeric (`Real`/`Int`) before arithmetic."]
        if message.startswith("expected element of"):
            return ["Use a value that belongs to the expected set domain."]
        return []

    def _scope_names(self, scope: Scope) -> list[str]:
        names: set[str] = set()
        cur: Scope | None = scope
        while cur is not None:
            names.update(cur.symbols.keys())
            cur = cur.parent
        return sorted(names)

    def _set_names(self, scope: Scope) -> list[str]:
        names: set[str] = set()
        cur: Scope | None = scope
        while cur is not None:
            names.update(name for name, sym in cur.symbols.items() if sym.kind == SymbolKind.SET)
            cur = cur.parent
        return sorted(names)

    def _did_you_mean(self, name: str, candidates: list[str]) -> str | None:
        matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.75)
        return matches[0] if matches else None

    def _repr_type(self, ty: Type) -> str:
        if isinstance(ty, type(BOOL)):
            return "Bool"
        if isinstance(ty, type(REAL)):
            return "Real"
        if isinstance(ty, IntRangeType):
            return f"Int[{ty.lo}..{ty.hi}]"
        if isinstance(ty, ElemOfType):
            return f"ElemOf({ty.set_name})"
        if isinstance(ty, ParamType):
            return "Param"
        if isinstance(ty, UnknownInstanceType):
            return f"UnknownInstance({ty.ref.name})"
        return "Unknown"
