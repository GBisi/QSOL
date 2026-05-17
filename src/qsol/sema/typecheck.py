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
    CompType,
    ElemOfType,
    IntRangeType,
    ParamType,
    RelationType,
    SetType,
    StructureInstanceType,
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


@dataclass(frozen=True, slots=True)
class GroundabilityResult:
    valid: bool
    dependency: str | None = None


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
                    if isinstance(stmt, ast.SetDecl) and isinstance(stmt.expr, ast.RangeSetExpr):
                        self._scenario_const_int_type(
                            stmt.expr.lo, scope, {}, diagnostics, typed.types
                        )
                        self._scenario_const_int_type(
                            stmt.expr.hi, scope, {}, diagnostics, typed.types
                        )
                    elif isinstance(stmt, ast.FindDecl):
                        if isinstance(stmt.decision_type, ast.IntDecisionType):
                            self._scenario_const_int_type(
                                stmt.decision_type.lo,
                                scope,
                                {},
                                diagnostics,
                                typed.types,
                                bound_role="lower",
                            )
                            self._scenario_const_int_type(
                                stmt.decision_type.hi,
                                scope,
                                {},
                                diagnostics,
                                typed.types,
                                bound_role="upper",
                            )
                    elif isinstance(stmt, ast.RelationDecl) and stmt.expr is not None:
                        self._check_relation_expr(stmt, scope, diagnostics, typed.types)
                    elif isinstance(stmt, ast.StructureDecl):
                        self._check_structure_decl(stmt, scope, diagnostics)
                    elif isinstance(stmt, ast.Constraint):
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
                        if isinstance(stmt.value_type, (ast.ElemTypeRef, ast.StaticSubsetTypeRef)):
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
                self._check_relation_dependency_cycles(item, diagnostics)

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
                    if isinstance(symbol.type, ParamType) and not symbol.type.indices:
                        out = symbol.type.elem
                    else:
                        out = symbol.type
        elif isinstance(expr, ast.DomainRef):
            symbol = scope.lookup(expr.name)
            if symbol is None or symbol.kind not in {SymbolKind.SET, SymbolKind.RELATION}:
                diagnostics.append(
                    self._type_err(
                        expr.span,
                        f"unknown static domain `{expr.name}`",
                    )
                )
                out = UNKNOWN
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
            if expr.name in {"abs", "min", "max"} and expr.call_style == "paren":
                out = self._piecewise_builtin_type(expr, scope, binders, diagnostics, tmap)
            elif expr.name == "size":
                out = self._size_call_type(expr, scope, binders, diagnostics, tmap)
            elif expr.call_style == "bracket":
                symbol = scope.lookup(expr.name)
                if (
                    symbol is not None
                    and symbol.kind in {SymbolKind.PARAM, SymbolKind.FIND}
                    and isinstance(symbol.type, ParamType)
                ):
                    out = self._param_call_type(
                        expr, symbol.type, scope, binders, diagnostics, tmap
                    )
                else:
                    for arg in expr.args:
                        self._expr_type(arg, scope, binders, diagnostics, tmap)
                    diagnostics.append(
                        self._type_err(
                            expr.span,
                            f"indexed access `{expr.name}[...]` requires a declared parameter",
                        )
                    )
                    out = UNKNOWN
            else:
                symbol = scope.lookup(expr.name)
                if (
                    symbol is not None
                    and symbol.kind == SymbolKind.RELATION
                    and isinstance(symbol.type, RelationType)
                ):
                    out = self._relation_call_type(
                        expr, symbol.type, scope, binders, diagnostics, tmap
                    )
                elif (
                    symbol is not None
                    and symbol.kind in {SymbolKind.PARAM, SymbolKind.FIND}
                    and isinstance(symbol.type, ParamType)
                ):
                    if symbol.type.indices:
                        label = "param" if symbol.kind == SymbolKind.PARAM else "value"
                        for arg in expr.args:
                            self._expr_type(arg, scope, binders, diagnostics, tmap)
                        diagnostics.append(
                            self._type_err(
                                expr.span,
                                f"indexed {label} `{expr.name}` must use bracket access "
                                f"`{expr.name}[...]`",
                            )
                        )
                        out = symbol.type.elem
                    else:
                        label = "param" if symbol.kind == SymbolKind.PARAM else "value"
                        out = self._param_call_type(
                            expr, symbol.type, scope, binders, diagnostics, tmap, label=label
                        )
                else:
                    for arg in expr.args:
                        self._expr_type(arg, scope, binders, diagnostics, tmap)
                    diagnostics.append(
                        self._type_err(
                            expr.span,
                            (
                                f"unknown function/predicate `{expr.name}`; "
                                "ensure it is declared and importable, and that macro expansion succeeded"
                            ),
                        )
                    )
                    out = UNKNOWN
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
        elif isinstance(expr, ast.BoolIfThenElse):
            cond = self._expr_type(expr.cond, scope, binders, diagnostics, tmap)
            then_ty = self._expr_type(expr.then_expr, scope, binders, diagnostics, tmap)
            else_ty = self._expr_type(expr.else_expr, scope, binders, diagnostics, tmap)
            if not isinstance(cond, type(BOOL)):
                diagnostics.append(self._type_err(expr.cond.span, "if condition must be Bool"))
            if not isinstance(then_ty, type(BOOL)):
                diagnostics.append(
                    self._type_err(expr.then_expr.span, "if-then branch must be Bool")
                )
            if not isinstance(else_ty, type(BOOL)):
                diagnostics.append(
                    self._type_err(expr.else_expr.span, "if-else branch must be Bool")
                )
            out = BOOL
        elif isinstance(expr, ast.Quantifier):
            binder_ty = self._binder_type(scope, expr.domain_set)
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
        elif isinstance(expr, ast.TupleQuantifier):
            body_scope = dict(binders)
            tuple_binder = ast.TupleCompBinder(
                span=expr.span,
                vars=expr.vars,
                domain_relation=expr.domain_relation,
            )
            self._extend_tuple_binder(scope, body_scope, tuple_binder, expr.span, diagnostics)
            body_ty = self._expr_type(expr.expr, scope, body_scope, diagnostics, tmap)
            if not isinstance(body_ty, type(BOOL)):
                diagnostics.append(self._type_err(expr.expr.span, "quantifier body must be Bool"))
            out = BOOL
        elif isinstance(expr, ast.BoolAggregate):
            inner = dict(binders)
            self._extend_comp_binders(scope, inner, expr.comp.binders, expr.comp.span, diagnostics)
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
        elif isinstance(expr, ast.BoolComprehension):
            body_scope = dict(binders)
            self._extend_comp_binders(scope, body_scope, expr.binders, expr.span, diagnostics)
            term_ty = self._expr_type(expr.term, scope, body_scope, diagnostics, tmap)
            if not isinstance(term_ty, type(BOOL)):
                diagnostics.append(
                    self._type_err(expr.term.span, "comprehension term must be Bool")
                )

            if expr.where is not None:
                where_ty = self._expr_type(expr.where, scope, body_scope, diagnostics, tmap)
                if not isinstance(where_ty, type(BOOL)):
                    diagnostics.append(self._type_err(expr.where.span, "where clause must be Bool"))

            out = CompType(elem_type=BOOL)
        elif isinstance(expr, ast.NumAggregate):
            inner = dict(binders)
            if isinstance(expr.comp, ast.NumComprehension):
                self._extend_comp_binders(
                    scope, inner, expr.comp.binders, expr.comp.span, diagnostics
                )
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
                # CountComprehension
                self._extend_comp_binders(
                    scope, inner, expr.comp.binders, expr.comp.span, diagnostics
                )
                first_binder = expr.comp.binders[0]
                if (
                    isinstance(first_binder, ast.CompBinder)
                    and expr.comp.var_ref != first_binder.var
                ):
                    diagnostics.append(
                        self._type_err(
                            expr.comp.span, "count binder and counted variable must match"
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

    def _piecewise_builtin_type(
        self,
        expr: ast.FuncCall,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        if expr.name == "abs":
            if len(expr.args) != 1:
                for arg in expr.args:
                    self._expr_type(arg, scope, binders, diagnostics, tmap)
                diagnostics.append(self._type_err(expr.span, "abs() expects exactly one argument"))
                return UNKNOWN
            arg_ty = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
            if not is_numeric(arg_ty):
                diagnostics.append(
                    self._type_err(expr.args[0].span, "abs() argument must be numeric")
                )
                return UNKNOWN
            return arg_ty

        if len(expr.args) == 1:
            arg = expr.args[0]
            if isinstance(arg, ast.NumAggregate):
                inner = dict(binders)
                if isinstance(arg.comp, ast.NumComprehension):
                    self._extend_comp_binders(
                        scope, inner, arg.comp.binders, arg.comp.span, diagnostics
                    )
                    term_ty = self._expr_type(arg.comp.term, scope, inner, diagnostics, tmap)
                    if not is_numeric(term_ty):
                        diagnostics.append(
                            self._type_err(
                                arg.comp.term.span,
                                f"{expr.name}() aggregate term must be numeric",
                            )
                        )
                        return UNKNOWN
                    if arg.comp.where is not None:
                        where_ty = self._expr_type(arg.comp.where, scope, inner, diagnostics, tmap)
                        if not isinstance(where_ty, type(BOOL)):
                            diagnostics.append(
                                self._type_err(arg.comp.where.span, "where clause must be Bool")
                            )
                    if arg.comp.else_term is not None:
                        else_ty = self._expr_type(
                            arg.comp.else_term, scope, inner, diagnostics, tmap
                        )
                        if not is_numeric(else_ty):
                            diagnostics.append(
                                self._type_err(arg.comp.else_term.span, "else term must be numeric")
                            )
                    return term_ty
                diagnostics.append(
                    self._type_err(arg.span, f"{expr.name}() aggregate expects numeric terms")
                )
                return UNKNOWN

            arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"{expr.name}() expects two numeric arguments or one numeric comprehension",
                )
            )
            return arg_ty if is_numeric(arg_ty) else UNKNOWN

        if len(expr.args) != 2:
            for arg in expr.args:
                self._expr_type(arg, scope, binders, diagnostics, tmap)
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"{expr.name}() expects two numeric arguments or one numeric comprehension",
                )
            )
            return UNKNOWN

        left = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
        right = self._expr_type(expr.args[1], scope, binders, diagnostics, tmap)
        promoted = promote_numeric(left, right)
        if promoted is None:
            diagnostics.append(
                self._type_err(expr.span, f"{expr.name}() arguments must be numeric")
            )
            return UNKNOWN
        return promoted

    def _method_type(
        self,
        expr: ast.MethodCall,
        target_ty: Type,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        if isinstance(target_ty, StructureInstanceType):
            return self._structure_method_type(expr, target_ty, scope, binders, diagnostics, tmap)

        if isinstance(target_ty, SetType) and expr.name == "has":
            if len(expr.args) != 1:
                diagnostics.append(
                    self._type_err(expr.span, "StaticSubset.has expects one argument")
                )
            else:
                expected_set = target_ty.element_set or target_ty.name
                arg_ty = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
                if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                    diagnostics.append(
                        self._type_err(expr.args[0].span, f"expected element of `{expected_set}`")
                    )
            return BOOL

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

        if (
            ref_name in {"Matching", "MaximalMatching", "SpanningTree", "Forest", "SteinerTree"}
            and expr.name == "has_edge"
        ):
            if len(expr.args) != 2:
                diagnostics.append(
                    self._type_err(expr.span, f"{ref_name}.has_edge expects two arguments")
                )
            else:
                graph_name = target_ty.ref.args[0] if target_ty.ref.args else ""
                graph_symbol = scope.lookup(graph_name)
                expected_set = ""
                if (
                    graph_symbol is not None
                    and isinstance(graph_symbol.type, StructureInstanceType)
                    and graph_symbol.type.vertex_set is not None
                ):
                    expected_set = graph_symbol.type.vertex_set
                for arg in expr.args:
                    arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
                    if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                        diagnostics.append(
                            self._type_err(arg.span, f"expected element of `{expected_set}`")
                        )
            return BOOL

        if ref_name == "SteinerTree" and expr.name == "has_vertex":
            graph_name = target_ty.ref.args[0] if target_ty.ref.args else ""
            graph_symbol = scope.lookup(graph_name)
            expected_set = ""
            if (
                graph_symbol is not None
                and isinstance(graph_symbol.type, StructureInstanceType)
                and graph_symbol.type.vertex_set is not None
            ):
                expected_set = graph_symbol.type.vertex_set
            if len(expr.args) != 1:
                diagnostics.append(
                    self._type_err(expr.span, "SteinerTree.has_vertex expects one argument")
                )
            else:
                arg_ty = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
                if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                    diagnostics.append(
                        self._type_err(expr.args[0].span, f"expected element of `{expected_set}`")
                    )
            return BOOL

        if ref_name in {"HamiltonianPath", "HamiltonianCycle"} and expr.name in {"at", "uses"}:
            graph_name = target_ty.ref.args[0] if target_ty.ref.args else ""
            graph_symbol = scope.lookup(graph_name)
            expected_set = ""
            if (
                graph_symbol is not None
                and isinstance(graph_symbol.type, StructureInstanceType)
                and graph_symbol.type.vertex_set is not None
            ):
                expected_set = graph_symbol.type.vertex_set

            if expr.name == "at":
                if len(expr.args) != 2:
                    diagnostics.append(
                        self._type_err(expr.span, f"{ref_name}.at expects two arguments")
                    )
                else:
                    pos_ty = self._expr_type(expr.args[0], scope, binders, diagnostics, tmap)
                    if not is_numeric(pos_ty):
                        diagnostics.append(
                            self._type_err(expr.args[0].span, "position must be numeric")
                        )
                    vertex_ty = self._expr_type(expr.args[1], scope, binders, diagnostics, tmap)
                    if not isinstance(vertex_ty, ElemOfType) or vertex_ty.set_name != expected_set:
                        diagnostics.append(
                            self._type_err(
                                expr.args[1].span, f"expected element of `{expected_set}`"
                            )
                        )
                return BOOL

            if len(expr.args) != 2:
                diagnostics.append(
                    self._type_err(expr.span, f"{ref_name}.uses expects two arguments")
                )
            else:
                for arg in expr.args:
                    arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
                    if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                        diagnostics.append(
                            self._type_err(arg.span, f"expected element of `{expected_set}`")
                        )
            return BOOL

        for arg in expr.args:
            self._expr_type(arg, scope, binders, diagnostics, tmap)
        return BOOL

    def _structure_method_type(
        self,
        expr: ast.MethodCall,
        target_ty: StructureInstanceType,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        allowed = (
            {"adjacent", "nonedge"}
            if target_ty.constructor
            in {
                "UndirectedGraph",
                "DirectedGraph",
            }
            else set()
        )
        if expr.name not in allowed:
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"unknown method `{expr.name}` for structure `{target_ty.name}`",
                )
            )
            for arg in expr.args:
                self._expr_type(arg, scope, binders, diagnostics, tmap)
            return UNKNOWN
        if len(expr.args) != 2:
            diagnostics.append(self._type_err(expr.span, f"{expr.name} expects two arguments"))
            for arg in expr.args:
                self._expr_type(arg, scope, binders, diagnostics, tmap)
            return BOOL
        expected_set = target_ty.vertex_set or ""
        for arg in expr.args:
            arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
            if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                diagnostics.append(
                    self._type_err(arg.span, f"expected element of `{expected_set}`")
                )
        return BOOL

    def _check_structure_decl(
        self,
        stmt: ast.StructureDecl,
        scope: Scope,
        diagnostics: list[Diagnostic],
    ) -> None:
        if stmt.constructor not in {"UndirectedGraph", "DirectedGraph"}:
            diagnostics.append(
                self._type_err(stmt.span, f"unknown structure constructor `{stmt.constructor}`")
            )
            return
        if len(stmt.args) != 2:
            diagnostics.append(
                self._type_err(stmt.span, f"{stmt.constructor} expects 2 argument(s)")
            )
            return

        vertex_name, relation_name = stmt.args
        vertex_symbol = scope.lookup(vertex_name)
        relation_symbol = scope.lookup(relation_name)
        if (
            vertex_symbol is None
            or vertex_symbol.kind != SymbolKind.SET
            or not isinstance(vertex_symbol.type, SetType)
        ):
            diagnostics.append(
                self._type_err(
                    stmt.span,
                    f"{stmt.constructor} expects first argument to be a declared set",
                )
            )
            return
        if (
            relation_symbol is None
            or relation_symbol.kind != SymbolKind.RELATION
            or not isinstance(relation_symbol.type, RelationType)
        ):
            diagnostics.append(
                self._type_err(
                    stmt.span,
                    f"{stmt.constructor} expects second argument to be a declared relation",
                )
            )
            return
        fields = relation_symbol.type.fields
        valid_fields = (
            len(fields) == 2
            and fields[0].set_type.name == vertex_name
            and fields[1].set_type.name == vertex_name
        )
        if not valid_fields:
            diagnostics.append(
                self._type_err(
                    stmt.span,
                    f"{stmt.constructor} expects a binary relation over `{vertex_name} x {vertex_name}`",
                )
            )

    def _param_call_type(
        self,
        expr: ast.FuncCall,
        ptype: ParamType,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
        *,
        label: str = "param",
    ) -> Type:
        relation_index = self._relation_index_for_param(ptype, scope)
        if relation_index is not None:
            return self._relation_param_call_type(
                expr, ptype, relation_index, scope, binders, diagnostics, tmap
            )

        expected_arity = len(ptype.indices)
        if expected_arity == 0:
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"scalar {label} `{expr.name}` must be referenced as `{expr.name}` (bare name)",
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

    def _relation_index_for_param(self, ptype: ParamType, scope: Scope) -> RelationType | None:
        if len(ptype.indices) != 1:
            return None
        index_name = ptype.indices[0].name
        symbol = scope.lookup(index_name)
        if (
            symbol is not None
            and symbol.kind == SymbolKind.RELATION
            and isinstance(symbol.type, RelationType)
        ):
            return symbol.type
        return None

    def _relation_param_call_type(
        self,
        expr: ast.FuncCall,
        ptype: ParamType,
        relation: RelationType,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        expected_arity = len(relation.fields)
        if len(expr.args) != expected_arity:
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"param call `{expr.name}` expects {expected_arity} argument(s) for relation `{relation.name}`",
                )
            )
        for i, arg in enumerate(expr.args):
            arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
            if i >= expected_arity:
                continue
            expected_set = relation.fields[i].set_type.name
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
        if not isinstance(arg, (ast.NameRef, ast.DomainRef)):
            self._expr_type(arg, scope, binders, diagnostics, tmap)
            diagnostics.append(
                self._type_err(
                    arg.span,
                    "size() expects a declared set identifier",
                )
            )
            return UNKNOWN

        symbol = scope.lookup(arg.name)
        if symbol is None or symbol.kind not in {SymbolKind.SET, SymbolKind.RELATION}:
            diagnostics.append(
                self._type_err(
                    arg.span,
                    f"size() expects a declared set or relation identifier, got `{arg.name}`",
                )
            )
            return UNKNOWN
        return IntRangeType(0, 2**31 - 1)

    def _lookup_set(self, scope: Scope, name: str) -> Symbol | None:
        sym = scope.lookup(name)
        if sym is None or sym.kind != SymbolKind.SET:
            return None
        return sym

    def _binder_type(self, scope: Scope, set_name: str) -> ElemOfType:
        sym = self._lookup_set(scope, set_name)
        numeric_kind = (
            sym.type.numeric_kind if sym is not None and isinstance(sym.type, SetType) else None
        )
        elem_set_name = (
            (sym.type.element_set or sym.type.name)
            if sym is not None and isinstance(sym.type, SetType)
            else set_name
        )
        return ElemOfType(set_name=elem_set_name, numeric_kind=numeric_kind)

    def _extend_comp_binders(
        self,
        scope: Scope,
        binders: dict[str, Type],
        comp_binders: tuple[ast.CompBinder | ast.TupleCompBinder, ...],
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> None:
        for binder in comp_binders:
            if isinstance(binder, ast.TupleCompBinder):
                self._extend_tuple_binder(scope, binders, binder, span, diagnostics)
                continue
            self._define_comp_var(
                binders,
                binder.var,
                self._binder_type(scope, binder.domain_set),
                span,
                diagnostics,
            )
            if self._lookup_set(scope, binder.domain_set) is None:
                self._unknown_domain_diagnostic(
                    scope, binder.domain_set, "set", "comprehension", span, diagnostics
                )

    def _define_comp_var(
        self,
        binders: dict[str, Type],
        name: str,
        ty: Type,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> None:
        if name in binders:
            diagnostics.append(self._type_err(span, f"duplicate binder `{name}` in comprehension"))
        binders[name] = ty

    def _extend_tuple_binder(
        self,
        scope: Scope,
        binders: dict[str, Type],
        binder: ast.TupleCompBinder,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> None:
        symbol = scope.lookup(binder.domain_relation)
        if (
            symbol is None
            or symbol.kind != SymbolKind.RELATION
            or not isinstance(symbol.type, RelationType)
        ):
            self._unknown_domain_diagnostic(
                scope, binder.domain_relation, "relation", "comprehension", span, diagnostics
            )
            return
        if len(binder.vars) != len(symbol.type.fields):
            diagnostics.append(
                self._type_err(
                    span,
                    f"relation `{binder.domain_relation}` tuple binder expects "
                    f"{len(symbol.type.fields)} variable(s)",
                )
            )
            return
        for name, relation_field in zip(binder.vars, symbol.type.fields, strict=True):
            self._define_comp_var(
                binders,
                name,
                ElemOfType(
                    relation_field.set_type.name,
                    numeric_kind=relation_field.set_type.numeric_kind,
                ),
                span,
                diagnostics,
            )

    def _check_relation_expr(
        self,
        stmt: ast.RelationDecl,
        scope: Scope,
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> None:
        if stmt.expr is None:
            return

        binders: dict[str, Type] = {}
        if isinstance(stmt.expr, ast.PairsRelationExpr):
            self._extend_comp_binders(
                scope, binders, stmt.expr.binders, stmt.expr.span, diagnostics
            )
            self._check_relation_output_fields(stmt, binders, diagnostics)
            if stmt.expr.where is not None:
                where_ty = self._expr_type(stmt.expr.where, scope, binders, diagnostics, tmap)
                if not isinstance(where_ty, type(BOOL)):
                    diagnostics.append(
                        self._type_err(
                            stmt.expr.where.span, "derived relation where clause must be Bool"
                        )
                    )
                if not self._is_static_relation_expr(stmt.expr.where, scope, binders):
                    diagnostics.append(self._derived_static_error(stmt.expr.where.span))
            return

        if isinstance(stmt.expr, ast.FilterRelationExpr):
            self._extend_tuple_binder(scope, binders, stmt.expr.binder, stmt.expr.span, diagnostics)
            self._check_relation_output_fields(stmt, binders, diagnostics)
            if stmt.expr.where is not None:
                where_ty = self._expr_type(stmt.expr.where, scope, binders, diagnostics, tmap)
                if not isinstance(where_ty, type(BOOL)):
                    diagnostics.append(
                        self._type_err(
                            stmt.expr.where.span, "derived relation where clause must be Bool"
                        )
                    )
                if not self._is_static_relation_expr(stmt.expr.where, scope, binders):
                    diagnostics.append(self._derived_static_error(stmt.expr.where.span))

    def _check_relation_output_fields(
        self,
        stmt: ast.RelationDecl,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
    ) -> None:
        for relation_field in stmt.fields:
            bound_ty = binders.get(relation_field.name)
            if bound_ty is None:
                diagnostics.append(
                    self._type_err(
                        relation_field.span,
                        f"derived relation field `{relation_field.name}` must be bound by the relation expression",
                    )
                )
                continue
            if not isinstance(bound_ty, ElemOfType) or bound_ty.set_name != relation_field.set_name:
                diagnostics.append(
                    self._type_err(
                        relation_field.span,
                        f"derived relation field `{relation_field.name}` must be an element of `{relation_field.set_name}`",
                    )
                )

    def _derived_static_error(self, span: Span) -> Diagnostic:
        return self._type_err(
            span,
            "derived relation condition must be scenario-time static",
        )

    def _is_static_relation_expr(
        self,
        expr: ast.Expr,
        scope: Scope,
        binders: dict[str, Type],
    ) -> bool:
        if isinstance(expr, (ast.BoolLit, ast.NumLit, ast.StringLit, ast.Literal)):
            return True
        if isinstance(expr, ast.NameRef):
            if expr.name in binders:
                return True
            symbol = scope.lookup(expr.name)
            return (
                symbol is not None
                and symbol.kind == SymbolKind.PARAM
                and isinstance(symbol.type, ParamType)
                and not symbol.type.indices
            )
        if isinstance(expr, ast.Not):
            return self._is_static_relation_expr(expr.expr, scope, binders)
        if isinstance(expr, (ast.And, ast.Or, ast.Implies)):
            return self._is_static_relation_expr(
                expr.left, scope, binders
            ) and self._is_static_relation_expr(expr.right, scope, binders)
        if isinstance(expr, ast.Compare):
            return self._is_static_relation_expr(
                expr.left, scope, binders
            ) and self._is_static_relation_expr(expr.right, scope, binders)
        if isinstance(expr, (ast.Add, ast.Sub, ast.Mul, ast.Div)):
            return self._is_static_relation_expr(
                expr.left, scope, binders
            ) and self._is_static_relation_expr(expr.right, scope, binders)
        if isinstance(expr, ast.Neg):
            return self._is_static_relation_expr(expr.expr, scope, binders)
        if isinstance(expr, ast.IfThenElse):
            return (
                self._is_static_relation_expr(expr.cond, scope, binders)
                and self._is_static_relation_expr(expr.then_expr, scope, binders)
                and self._is_static_relation_expr(expr.else_expr, scope, binders)
            )
        if isinstance(expr, ast.BoolIfThenElse):
            return (
                self._is_static_relation_expr(expr.cond, scope, binders)
                and self._is_static_relation_expr(expr.then_expr, scope, binders)
                and self._is_static_relation_expr(expr.else_expr, scope, binders)
            )
        if isinstance(expr, ast.FuncCall):
            symbol = scope.lookup(expr.name)
            if expr.name == "size":
                return all(self._is_static_relation_expr(arg, scope, binders) for arg in expr.args)
            if expr.call_style == "bracket":
                if symbol is None or symbol.kind != SymbolKind.PARAM:
                    return False
                return all(self._is_static_relation_expr(arg, scope, binders) for arg in expr.args)
            if symbol is None or symbol.kind not in {SymbolKind.PARAM, SymbolKind.RELATION}:
                return False
            if symbol.kind == SymbolKind.PARAM and isinstance(symbol.type, ParamType):
                if not symbol.type.indices:
                    return not expr.args
                return False
            return all(self._is_static_relation_expr(arg, scope, binders) for arg in expr.args)
        return False

    def _check_relation_dependency_cycles(
        self,
        problem: ast.ProblemDef,
        diagnostics: list[Diagnostic],
    ) -> None:
        derived = {
            stmt.name: stmt
            for stmt in problem.stmts
            if isinstance(stmt, ast.RelationDecl) and stmt.expr is not None
        }
        if not derived:
            return
        graph = {
            name: {dep for dep in self._relation_expr_deps(stmt.expr) if dep in derived}
            for name, stmt in derived.items()
            if stmt.expr is not None
        }
        visited: set[str] = set()
        active: list[str] = []

        def visit(name: str) -> None:
            if name in active:
                cycle = active[active.index(name) :] + [name]
                diagnostics.append(
                    self._type_err(
                        derived[name].span,
                        f"derived relation dependency cycle: {' -> '.join(cycle)}",
                    )
                )
                return
            if name in visited:
                return
            active.append(name)
            for dep in sorted(graph.get(name, ())):
                visit(dep)
            active.pop()
            visited.add(name)

        for name in sorted(graph):
            visit(name)

    def _relation_expr_deps(self, expr: ast.RelationExpr) -> set[str]:
        deps: set[str] = set()
        if isinstance(expr, ast.PairsRelationExpr):
            for binder in expr.binders:
                if isinstance(binder, ast.TupleCompBinder):
                    deps.add(binder.domain_relation)
            if expr.where is not None:
                self._collect_relation_call_deps(expr.where, deps)
        elif isinstance(expr, ast.FilterRelationExpr):
            deps.add(expr.binder.domain_relation)
            if expr.where is not None:
                self._collect_relation_call_deps(expr.where, deps)
        return deps

    def _collect_relation_call_deps(self, expr: ast.Expr, deps: set[str]) -> None:
        if isinstance(expr, ast.FuncCall):
            deps.add(expr.name)
            for arg in expr.args:
                self._collect_relation_call_deps(arg, deps)
        elif isinstance(expr, ast.MethodCall):
            self._collect_relation_call_deps(expr.target, deps)
            for arg in expr.args:
                self._collect_relation_call_deps(arg, deps)
        elif isinstance(expr, (ast.Not, ast.Neg)):
            self._collect_relation_call_deps(expr.expr, deps)
        elif isinstance(
            expr, (ast.And, ast.Or, ast.Implies, ast.Compare, ast.Add, ast.Sub, ast.Mul, ast.Div)
        ):
            self._collect_relation_call_deps(expr.left, deps)
            self._collect_relation_call_deps(expr.right, deps)
        elif isinstance(expr, (ast.IfThenElse, ast.BoolIfThenElse)):
            self._collect_relation_call_deps(expr.cond, deps)
            self._collect_relation_call_deps(expr.then_expr, deps)
            self._collect_relation_call_deps(expr.else_expr, deps)

    def _unknown_domain_diagnostic(
        self,
        scope: Scope,
        name: str,
        kind: str,
        context: str,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> None:
        candidates = self._set_names(scope) if kind == "set" else self._relation_names(scope)
        suggestion = self._did_you_mean(name, candidates)
        help_items = [f"Declare {kind} `{name}` before using it."]
        if suggestion is not None:
            help_items.append(f"Did you mean `{suggestion}`?")
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2001",
                message=f"unknown {kind} `{name}` in {context}",
                span=span,
                help=help_items,
            )
        )

    def _relation_call_type(
        self,
        expr: ast.FuncCall,
        relation_type: RelationType,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
    ) -> Type:
        if len(expr.args) != len(relation_type.fields):
            diagnostics.append(
                self._type_err(
                    expr.span,
                    f"relation `{expr.name}` expects {len(relation_type.fields)} argument(s)",
                )
            )
        for idx, arg in enumerate(expr.args):
            arg_ty = self._expr_type(arg, scope, binders, diagnostics, tmap)
            if idx >= len(relation_type.fields):
                continue
            expected_set = relation_type.fields[idx].set_type.name
            if not isinstance(arg_ty, ElemOfType) or arg_ty.set_name != expected_set:
                diagnostics.append(
                    self._type_err(arg.span, f"expected element of `{expected_set}`")
                )
        return BOOL

    def _scenario_const_int_type(
        self,
        expr: ast.NumExpr,
        scope: Scope,
        binders: dict[str, Type],
        diagnostics: list[Diagnostic],
        tmap: dict[int, str],
        *,
        bound_role: str | None = None,
    ) -> Type:
        ty = self._expr_type(expr, scope, binders, diagnostics, tmap)
        if not is_numeric(ty):
            diagnostics.append(
                self._type_err(expr.span, "integer bounds must be scenario-time numeric constants")
            )
        if bound_role is None:
            if not self._is_legacy_scenario_const_expr(expr, scope):
                diagnostics.append(
                    self._groundability_err(
                        expr.span,
                        "integer bounds may use literals, scalar params, size(Set), and arithmetic only",
                        None,
                    )
                )
            return ty
        result = self._groundability(expr, scope, binders)
        if not result.valid:
            diagnostics.append(
                self._groundability_err(
                    expr.span,
                    f"Int {bound_role} bound is not scenario-time constant",
                    result.dependency,
                )
            )
        return ty

    def _groundability(
        self, expr: ast.Expr, scope: Scope, binders: dict[str, Type]
    ) -> GroundabilityResult:
        if isinstance(expr, (ast.BoolLit, ast.NumLit, ast.StringLit, ast.Literal)):
            return GroundabilityResult(True)
        if isinstance(expr, ast.NameRef):
            if expr.name in binders:
                return GroundabilityResult(True)
            symbol = scope.lookup(expr.name)
            if symbol is None:
                return GroundabilityResult(False, f"unknown identifier `{expr.name}`")
            if symbol.kind == SymbolKind.FIND:
                return GroundabilityResult(False, f"decision `{expr.name}`")
            return GroundabilityResult(
                symbol.kind == SymbolKind.PARAM
                and isinstance(symbol.type, ParamType)
                and not symbol.type.indices,
                f"non-static identifier `{expr.name}`",
            )
        if isinstance(expr, (ast.Not, ast.Neg)):
            return self._groundability(expr.expr, scope, binders)
        if isinstance(
            expr, (ast.And, ast.Or, ast.Implies, ast.Compare, ast.Add, ast.Sub, ast.Mul, ast.Div)
        ):
            return self._merge_groundability(
                self._groundability(expr.left, scope, binders),
                self._groundability(expr.right, scope, binders),
            )
        if isinstance(expr, ast.IfThenElse):
            return self._merge_groundability(
                self._groundability(expr.cond, scope, binders),
                self._groundability(expr.then_expr, scope, binders),
                self._groundability(expr.else_expr, scope, binders),
            )
        if isinstance(expr, ast.BoolIfThenElse):
            return self._merge_groundability(
                self._groundability(expr.cond, scope, binders),
                self._groundability(expr.then_expr, scope, binders),
                self._groundability(expr.else_expr, scope, binders),
            )
        if isinstance(expr, ast.FuncCall):
            if expr.name == "size":
                if len(expr.args) != 1 or not isinstance(expr.args[0], ast.NameRef):
                    return GroundabilityResult(False, "invalid size() argument")
                symbol = scope.lookup(expr.args[0].name)
                return GroundabilityResult(
                    symbol is not None and symbol.kind in {SymbolKind.SET, SymbolKind.RELATION},
                    f"non-static size() argument `{expr.args[0].name}`",
                )
            symbol = scope.lookup(expr.name)
            if symbol is None:
                return GroundabilityResult(False, f"unknown call `{expr.name}`")
            if symbol.kind == SymbolKind.FIND:
                return GroundabilityResult(False, f"decision `{expr.name}`")
            if symbol.kind == SymbolKind.PARAM:
                return self._merge_groundability(
                    *(self._groundability(arg, scope, binders) for arg in expr.args)
                )
            if symbol.kind == SymbolKind.RELATION:
                return self._merge_groundability(
                    *(self._groundability(arg, scope, binders) for arg in expr.args)
                )
            return GroundabilityResult(False, f"non-static call `{expr.name}`")
        if isinstance(expr, ast.MethodCall):
            target = (
                expr.target.name
                if isinstance(expr.target, ast.NameRef)
                else type(expr.target).__name__
            )
            return GroundabilityResult(False, f"{target}.{expr.name}")
        if isinstance(expr, ast.Quantifier):
            inner = dict(binders)
            if self._lookup_set(scope, expr.domain_set) is None:
                return GroundabilityResult(False, f"unknown set `{expr.domain_set}`")
            inner[expr.var] = self._binder_type(scope, expr.domain_set)
            return self._groundability(expr.expr, scope, inner)
        if isinstance(expr, ast.TupleQuantifier):
            return self._tuple_binder_groundability(
                expr.vars, expr.domain_relation, expr.expr, expr.span, scope, binders
            )
        if isinstance(expr, ast.BoolAggregate):
            inner = dict(binders)
            binder_result = self._binders_groundability(scope, inner, expr.comp.binders)
            return self._merge_groundability(
                binder_result,
                self._groundability(expr.comp.term, scope, inner),
                self._groundability(expr.comp.where, scope, inner)
                if expr.comp.where is not None
                else GroundabilityResult(True),
                self._groundability(expr.comp.else_term, scope, inner)
                if expr.comp.else_term is not None
                else GroundabilityResult(True),
            )
        if isinstance(expr, ast.BoolComprehension):
            inner = dict(binders)
            binder_result = self._binders_groundability(scope, inner, expr.binders)
            return self._merge_groundability(
                binder_result,
                self._groundability(expr.term, scope, inner),
                self._groundability(expr.where, scope, inner)
                if expr.where is not None
                else GroundabilityResult(True),
            )
        if isinstance(expr, ast.NumAggregate):
            inner = dict(binders)
            binder_result = self._binders_groundability(scope, inner, expr.comp.binders)
            checks = [binder_result]
            if isinstance(expr.comp, ast.NumComprehension):
                checks.append(self._groundability(expr.comp.term, scope, inner))
                if expr.comp.where is not None:
                    checks.append(self._groundability(expr.comp.where, scope, inner))
                if expr.comp.else_term is not None:
                    checks.append(self._groundability(expr.comp.else_term, scope, inner))
            else:
                if expr.comp.where is not None:
                    checks.append(self._groundability(expr.comp.where, scope, inner))
            return self._merge_groundability(*checks)
        return GroundabilityResult(False, f"unsupported expression `{type(expr).__name__}`")

    def _binders_groundability(
        self,
        scope: Scope,
        binders: dict[str, Type],
        comp_binders: tuple[ast.CompBinder | ast.TupleCompBinder, ...],
    ) -> GroundabilityResult:
        for binder in comp_binders:
            if isinstance(binder, ast.TupleCompBinder):
                symbol = scope.lookup(binder.domain_relation)
                if (
                    symbol is None
                    or symbol.kind != SymbolKind.RELATION
                    or not isinstance(symbol.type, RelationType)
                ):
                    return GroundabilityResult(
                        False, f"unknown relation `{binder.domain_relation}`"
                    )
                if len(binder.vars) != len(symbol.type.fields):
                    return GroundabilityResult(False, f"relation `{binder.domain_relation}` arity")
                for name, relation_field in zip(binder.vars, symbol.type.fields, strict=True):
                    binders[name] = ElemOfType(
                        relation_field.set_type.name,
                        numeric_kind=relation_field.set_type.numeric_kind,
                    )
                continue
            if self._lookup_set(scope, binder.domain_set) is None:
                return GroundabilityResult(False, f"unknown set `{binder.domain_set}`")
            binders[binder.var] = self._binder_type(scope, binder.domain_set)
        return GroundabilityResult(True)

    def _tuple_binder_groundability(
        self,
        vars: tuple[str, ...],
        domain_relation: str,
        expr: ast.Expr,
        span: Span,
        scope: Scope,
        binders: dict[str, Type],
    ) -> GroundabilityResult:
        inner = dict(binders)
        binder = ast.TupleCompBinder(span=span, vars=vars, domain_relation=domain_relation)
        binder_result = self._binders_groundability(scope, inner, (binder,))
        return self._merge_groundability(binder_result, self._groundability(expr, scope, inner))

    def _merge_groundability(self, *results: GroundabilityResult) -> GroundabilityResult:
        for result in results:
            if not result.valid:
                return result
        return GroundabilityResult(True)

    def _groundability_err(self, span: Span, message: str, dependency: str | None) -> Diagnostic:
        notes = [f"The expression depends on {dependency}."] if dependency is not None else []
        return Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2101",
            message=message,
            span=span,
            notes=notes,
            help=[
                "Only input params, size(...), static relations, and aggregates over static domains are allowed in decision bounds."
            ],
        )

    def _is_legacy_scenario_const_expr(self, expr: ast.Expr, scope: Scope) -> bool:
        if isinstance(expr, ast.NumLit):
            return True
        if isinstance(expr, ast.NameRef):
            symbol = scope.lookup(expr.name)
            return (
                symbol is not None
                and symbol.kind == SymbolKind.PARAM
                and isinstance(symbol.type, ParamType)
                and not symbol.type.indices
                and is_numeric(symbol.type.elem)
            )
        if isinstance(expr, ast.FuncCall) and expr.name == "size" and len(expr.args) == 1:
            arg = expr.args[0]
            symbol = scope.lookup(arg.name) if isinstance(arg, ast.NameRef) else None
            return symbol is not None and symbol.kind == SymbolKind.SET
        if isinstance(expr, (ast.Add, ast.Sub, ast.Mul, ast.Div)):
            return self._is_legacy_scenario_const_expr(
                expr.left, scope
            ) and self._is_legacy_scenario_const_expr(expr.right, scope)
        if isinstance(expr, ast.Neg):
            return self._is_legacy_scenario_const_expr(expr.expr, scope)
        return False

    def _literal_type(self, lit: ast.Literal) -> Type:
        if isinstance(lit.value, bool):
            return BOOL
        if isinstance(lit.value, (int, float)):
            return REAL
        return UnknownType()

    def _param_decl_type(self, stmt: ast.ParamDecl) -> Type:
        if isinstance(stmt.value_type, ast.ElemTypeRef):
            return ElemOfType(stmt.value_type.set_name)
        if isinstance(stmt.value_type, ast.StaticSubsetTypeRef):
            return SetType(stmt.name, element_set=stmt.value_type.set_name)

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
        if (
            message.startswith("indexed value `") or message.startswith("indexed param `")
        ) and "must use bracket access" in message:
            return ["Use bracket syntax for indexed params, for example `Cost[i, j]`."]
        if message.startswith("indexed access `") and "requires a declared parameter" in message:
            return ["Use indexed access only with declared parameters."]
        if message.startswith("scalar value `"):
            return ["Reference scalar params and scalar decisions as bare names, not as calls."]
        if message.startswith("scalar param `"):
            return ["Reference scalar params as bare names, not as calls."]
        if message.startswith("unknown function/predicate `"):
            return [
                "Declare the predicate/function at top-level or in unknown `view`, and import modules before use."
            ]
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

    def _relation_names(self, scope: Scope) -> list[str]:
        names: set[str] = set()
        cur: Scope | None = scope
        while cur is not None:
            names.update(
                name for name, sym in cur.symbols.items() if sym.kind == SymbolKind.RELATION
            )
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
            suffix = f",{ty.numeric_kind}" if ty.numeric_kind is not None else ""
            return f"ElemOf({ty.set_name}{suffix})"
        if isinstance(ty, ParamType):
            return "Param"
        if isinstance(ty, UnknownInstanceType):
            return f"UnknownInstance({ty.ref.name})"
        return "Unknown"
