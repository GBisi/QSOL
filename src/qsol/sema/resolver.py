from __future__ import annotations

from dataclasses import dataclass, field

from qsol.diag.diagnostic import Diagnostic, Severity
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
                if not global_scope.define(symbol):
                    diagnostics.append(self._dup(item.span, item.name))
            elif isinstance(item, ast.ProblemDef):
                symbol = Symbol(name=item.name, kind=SymbolKind.PROBLEM, type=REAL, span=item.span)
                if not global_scope.define(symbol):
                    diagnostics.append(self._dup(item.span, item.name))

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
                if not scope.define(symbol):
                    diagnostics.append(self._dup(stmt.span, stmt.name))

        for stmt in problem.stmts:
            if isinstance(stmt, ast.ParamDecl):
                indices: list[SetType] = []
                for index_name in stmt.indices:
                    set_symbol = scope.lookup(index_name)
                    if set_symbol is None or set_symbol.kind != SymbolKind.SET:
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2201",
                                message=f"unknown set `{index_name}` in param indexing",
                                span=stmt.span,
                            )
                        )
                    else:
                        indices.append(SetType(index_name))
                elem = self._param_value_to_type(scope, stmt.value_type, diagnostics, stmt.span)
                ptype = ParamType(indices=tuple(indices), elem=elem)
                if not scope.define(Symbol(stmt.name, SymbolKind.PARAM, ptype, stmt.span)):
                    diagnostics.append(self._dup(stmt.span, stmt.name))

            elif isinstance(stmt, ast.FindDecl):
                unknown_ref = stmt.unknown_type
                if unknown_ref.kind == "Subset":
                    target = unknown_ref.args[0]
                    set_symbol = scope.lookup(target)
                    if set_symbol is None or set_symbol.kind != SymbolKind.SET:
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=f"unknown set `{target}` for Subset",
                                span=stmt.span,
                            )
                        )
                elif unknown_ref.kind == "Mapping":
                    for target in unknown_ref.args:
                        set_symbol = scope.lookup(target)
                        if set_symbol is None or set_symbol.kind != SymbolKind.SET:
                            diagnostics.append(
                                Diagnostic(
                                    severity=Severity.ERROR,
                                    code="QSOL2001",
                                    message=f"unknown set `{target}` for Mapping",
                                    span=stmt.span,
                                )
                            )
                else:
                    if global_scope.lookup(unknown_ref.kind) is None:
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=f"unknown unknown-type `{unknown_ref.kind}`",
                                span=stmt.span,
                            )
                        )

                inst_type = UnknownInstanceType(
                    ref=UnknownTypeRef(name=unknown_ref.kind, args=tuple(unknown_ref.args))
                )
                if not scope.define(Symbol(stmt.name, SymbolKind.FIND, inst_type, stmt.span)):
                    diagnostics.append(self._dup(stmt.span, stmt.name))

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
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"unknown set `{value_type.set_name}` in param value type",
                    span=span,
                )
            )
        return ElemOfType(value_type.set_name)

    def _dup(self, span: Span, name: str) -> Diagnostic:
        return Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2002",
            message=f"redefinition of `{name}` in same scope",
            span=span,
        )


__all__ = ["Resolver", "ResolutionResult", "ElemOfType"]
