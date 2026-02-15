from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from qsol.diag.diagnostic import Diagnostic, DiagnosticLabel, Severity
from qsol.diag.source import Span
from qsol.parse import ast
from qsol.sema.symbols import Scope, Symbol, SymbolKind, SymbolTable
from qsol.sema.types import (
    BOOL,
    REAL,
    ElemOfType,
    IntRangeType,
    ParamType,
    SetType,
    Type,
    UnknownInstanceType,
    UnknownTypeRef,
)


@dataclass(slots=True)
class ResolutionResult:
    symbols: SymbolTable
    diagnostics: list[Diagnostic] = field(default_factory=list)


class Resolver:
    def resolve(self, program: ast.Program) -> ResolutionResult:
        global_scope = Scope(name="global")
        diagnostics: list[Diagnostic] = []
        table = SymbolTable(global_scope=global_scope)

        for item in program.items:
            if isinstance(item, ast.UnknownDef):
                symbol = Symbol(
                    name=item.name,
                    kind=SymbolKind.UNKNOWN_DEF,
                    type=UnknownTypeRef(name=item.name, args=tuple(item.formals)),
                    span=item.span,
                )
                existing = global_scope.symbols.get(item.name)
                if existing is not None:
                    diagnostics.append(self._dup(item.span, item.name, previous=existing.span))
                else:
                    global_scope.define(symbol)
            elif isinstance(item, ast.ProblemDef):
                symbol = Symbol(name=item.name, kind=SymbolKind.PROBLEM, type=REAL, span=item.span)
                existing = global_scope.symbols.get(item.name)
                if existing is not None:
                    diagnostics.append(self._dup(item.span, item.name, previous=existing.span))
                else:
                    global_scope.define(symbol)

        for item in program.items:
            if isinstance(item, ast.ProblemDef):
                scope = Scope(name=f"problem:{item.name}", parent=global_scope)
                table.problem_scopes[item.name] = scope
                self._collect_problem(scope, item, diagnostics, global_scope)

        return ResolutionResult(symbols=table, diagnostics=diagnostics)

    def _collect_problem(
        self,
        scope: Scope,
        problem: ast.ProblemDef,
        diagnostics: list[Diagnostic],
        global_scope: Scope,
    ) -> None:
        for stmt in problem.stmts:
            if isinstance(stmt, ast.SetDecl):
                symbol = Symbol(stmt.name, SymbolKind.SET, SetType(stmt.name), stmt.span)
                existing = scope.symbols.get(stmt.name)
                if existing is not None:
                    diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                else:
                    scope.define(symbol)

        for stmt in problem.stmts:
            if isinstance(stmt, ast.ParamDecl):
                indices: list[SetType] = []
                for index_name in stmt.indices:
                    set_symbol = scope.lookup(index_name)
                    if set_symbol is None or set_symbol.kind != SymbolKind.SET:
                        suggestion = self._did_you_mean(index_name, self._set_candidates(scope))
                        help_items = ["Declare the set before using it in parameter indexing."]
                        if suggestion is not None:
                            help_items.append(f"Did you mean `{suggestion}`?")
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2201",
                                message=f"unknown set `{index_name}` in param indexing",
                                span=stmt.span,
                                help=help_items,
                            )
                        )
                    else:
                        indices.append(SetType(index_name))
                elem = self._param_value_to_type(scope, stmt.value_type, diagnostics, stmt.span)
                ptype = ParamType(indices=tuple(indices), elem=elem)
                existing = scope.symbols.get(stmt.name)
                if existing is not None:
                    diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                else:
                    scope.define(Symbol(stmt.name, SymbolKind.PARAM, ptype, stmt.span))

            elif isinstance(stmt, ast.FindDecl):
                unknown_ref = stmt.unknown_type
                if unknown_ref.kind == "Subset":
                    target = unknown_ref.args[0]
                    set_symbol = scope.lookup(target)
                    if set_symbol is None or set_symbol.kind != SymbolKind.SET:
                        suggestion = self._did_you_mean(target, self._set_candidates(scope))
                        help_items = [f"Declare set `{target}` before `find {stmt.name}`."]
                        if suggestion is not None:
                            help_items.append(f"Did you mean `{suggestion}`?")
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=f"unknown set `{target}` for Subset",
                                span=stmt.span,
                                help=help_items,
                            )
                        )
                elif unknown_ref.kind == "Mapping":
                    for target in unknown_ref.args:
                        set_symbol = scope.lookup(target)
                        if set_symbol is None or set_symbol.kind != SymbolKind.SET:
                            suggestion = self._did_you_mean(target, self._set_candidates(scope))
                            help_items = ["Mapping endpoints must reference declared sets."]
                            if suggestion is not None:
                                help_items.append(f"Did you mean `{suggestion}`?")
                            diagnostics.append(
                                Diagnostic(
                                    severity=Severity.ERROR,
                                    code="QSOL2001",
                                    message=f"unknown set `{target}` for Mapping",
                                    span=stmt.span,
                                    help=help_items,
                                )
                            )
                else:
                    if global_scope.lookup(unknown_ref.kind) is None:
                        candidates = [
                            sym.name
                            for sym in global_scope.symbols.values()
                            if sym.kind == SymbolKind.UNKNOWN_DEF
                        ]
                        suggestion = self._did_you_mean(unknown_ref.kind, candidates)
                        help_items = [
                            "Declare the unknown type with an `unknown` block before using it."
                        ]
                        if suggestion is not None:
                            help_items.append(f"Did you mean `{suggestion}`?")
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=f"unknown unknown-type `{unknown_ref.kind}`",
                                span=stmt.span,
                                help=help_items,
                            )
                        )

                inst_type = UnknownInstanceType(
                    ref=UnknownTypeRef(name=unknown_ref.kind, args=tuple(unknown_ref.args))
                )
                existing = scope.symbols.get(stmt.name)
                if existing is not None:
                    diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                else:
                    scope.define(Symbol(stmt.name, SymbolKind.FIND, inst_type, stmt.span))

    def _scalar_to_type(self, scalar: ast.ScalarTypeRef) -> Type:
        if scalar.kind == "Bool":
            return BOOL
        if scalar.kind == "Real":
            return REAL
        if scalar.kind == "Int":
            lo = scalar.lo if scalar.lo is not None else -(2**31)
            hi = scalar.hi if scalar.hi is not None else 2**31 - 1
            return IntRangeType(lo=lo, hi=hi)
        return REAL

    def _param_value_to_type(
        self,
        scope: Scope,
        value_type: ast.ScalarTypeRef | ast.ElemTypeRef,
        diagnostics: list[Diagnostic],
        span: Span,
    ) -> Type:
        if isinstance(value_type, ast.ScalarTypeRef):
            return self._scalar_to_type(value_type)

        set_symbol = scope.lookup(value_type.set_name)
        if set_symbol is None or set_symbol.kind != SymbolKind.SET:
            suggestion = self._did_you_mean(value_type.set_name, self._set_candidates(scope))
            help_items = [
                f"Declare set `{value_type.set_name}` before using it as `Elem(...)` value type."
            ]
            if suggestion is not None:
                help_items.append(f"Did you mean `{suggestion}`?")
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"unknown set `{value_type.set_name}` in param value type",
                    span=span,
                    help=help_items,
                )
            )
        return ElemOfType(value_type.set_name)

    def _dup(self, span: Span, name: str, *, previous: Span | None = None) -> Diagnostic:
        labels: list[DiagnosticLabel] = [
            DiagnosticLabel(span=span, message="redefined here", is_primary=True)
        ]
        notes: list[str] = []
        if previous is not None:
            labels.append(
                DiagnosticLabel(span=previous, message="previous definition here", is_primary=False)
            )
            notes.append(
                f"previous definition at {previous.filename}:{previous.line}:{previous.col}"
            )
        return Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2002",
            message=f"redefinition of `{name}` in same scope",
            span=span,
            labels=labels,
            notes=notes,
            help=[f"Rename one of the declarations of `{name}` in this scope."],
        )

    def _set_candidates(self, scope: Scope) -> list[str]:
        return sorted(
            name for name, symbol in scope.symbols.items() if symbol.kind == SymbolKind.SET
        )

    def _did_you_mean(self, name: str, candidates: list[str]) -> str | None:
        matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.75)
        return matches[0] if matches else None


__all__ = ["Resolver", "ResolutionResult", "ElemOfType"]
