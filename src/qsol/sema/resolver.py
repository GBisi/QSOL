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
    RelationFieldType,
    RelationType,
    SetType,
    StructureInstanceType,
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
                numeric_kind = "Int" if isinstance(stmt.expr, ast.RangeSetExpr) else None
                symbol = Symbol(
                    stmt.name,
                    SymbolKind.SET,
                    SetType(stmt.name, numeric_kind=numeric_kind),
                    stmt.span,
                )
                existing = scope.symbols.get(stmt.name)
                if existing is not None:
                    diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                else:
                    scope.define(symbol)

        for stmt in problem.stmts:
            if isinstance(stmt, ast.RelationDecl):
                fields: list[RelationFieldType] = []
                seen_fields: dict[str, Span] = {}
                for field in stmt.fields:
                    if field.name in seen_fields:
                        diagnostics.append(
                            self._dup(field.span, field.name, previous=seen_fields[field.name])
                        )
                    else:
                        seen_fields[field.name] = field.span

                    set_symbol = scope.lookup(field.set_name)
                    if (
                        set_symbol is None
                        or set_symbol.kind != SymbolKind.SET
                        or not isinstance(set_symbol.type, SetType)
                    ):
                        suggestion = self._did_you_mean(field.set_name, self._set_candidates(scope))
                        help_items = ["Relation fields must reference declared sets."]
                        if suggestion is not None:
                            help_items.append(f"Did you mean `{suggestion}`?")
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=f"unknown set `{field.set_name}` in relation `{stmt.name}`",
                                span=field.span,
                                help=help_items,
                            )
                        )
                    else:
                        fields.append(RelationFieldType(field.name, set_symbol.type))

                existing = scope.symbols.get(stmt.name)
                if existing is not None:
                    diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                else:
                    scope.define(
                        Symbol(
                            stmt.name,
                            SymbolKind.RELATION,
                            RelationType(stmt.name, tuple(fields)),
                            stmt.span,
                        )
                    )

        for stmt in problem.stmts:
            if isinstance(stmt, ast.StructureDecl):
                existing = scope.symbols.get(stmt.name)
                if existing is not None:
                    diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                    continue

                vertex_set: str | None = None
                relation_name: str | None = None
                if stmt.constructor in {"UndirectedGraph", "DirectedGraph"} and len(stmt.args) == 2:
                    vertex_set, relation_name = stmt.args

                scope.define(
                    Symbol(
                        stmt.name,
                        SymbolKind.STRUCTURE,
                        StructureInstanceType(
                            name=stmt.name,
                            constructor=stmt.constructor,
                            args=stmt.args,
                            vertex_set=vertex_set,
                            relation_name=relation_name,
                        ),
                        stmt.span,
                    )
                )
                self._define_structure_domains(scope, stmt, diagnostics)

        for stmt in problem.stmts:
            if isinstance(stmt, ast.ParamDecl):
                if isinstance(stmt.value_type, ast.StaticSubsetTypeRef):
                    if stmt.indices:
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2201",
                                message="StaticSubset params cannot be indexed",
                                span=stmt.span,
                                help=["Use `param Name : StaticSubset(SetName);`."],
                            )
                        )
                    set_symbol = scope.lookup(stmt.value_type.set_name)
                    if (
                        set_symbol is None
                        or set_symbol.kind != SymbolKind.SET
                        or not isinstance(set_symbol.type, SetType)
                    ):
                        suggestion = self._did_you_mean(
                            stmt.value_type.set_name, self._set_candidates(scope)
                        )
                        help_items = [
                            (
                                f"Declare set `{stmt.value_type.set_name}` before using it "
                                "as `StaticSubset(...)` parent."
                            )
                        ]
                        if suggestion is not None:
                            help_items.append(f"Did you mean `{suggestion}`?")
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2201",
                                message=(
                                    f"unknown set `{stmt.value_type.set_name}` in param value type"
                                ),
                                span=stmt.span,
                                help=help_items,
                            )
                        )
                    existing = scope.symbols.get(stmt.name)
                    if existing is not None:
                        diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
                    else:
                        scope.define(
                            Symbol(
                                stmt.name,
                                SymbolKind.SET,
                                SetType(stmt.name, element_set=stmt.value_type.set_name),
                                stmt.span,
                            )
                        )
                    continue

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
                index_types: list[SetType] = []
                for index_name in stmt.indices:
                    index_symbol = scope.lookup(index_name)
                    if (
                        index_symbol is not None
                        and index_symbol.kind == SymbolKind.RELATION
                        and isinstance(index_symbol.type, RelationType)
                    ):
                        index_types.extend(field.set_type for field in index_symbol.type.fields)
                        continue
                    if (
                        index_symbol is None
                        or index_symbol.kind != SymbolKind.SET
                        or not isinstance(index_symbol.type, SetType)
                    ):
                        suggestion = self._did_you_mean(index_name, self._set_candidates(scope))
                        help_items = ["Find indices must reference declared sets or relations."]
                        if suggestion is not None:
                            help_items.append(f"Did you mean `{suggestion}`?")
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=f"unknown set or relation `{index_name}` in find indexing",
                                span=stmt.span,
                                help=help_items,
                            )
                        )
                    else:
                        index_types.append(index_symbol.type)

                if isinstance(stmt.decision_type, ast.BoolDecisionType):
                    find_type: Type = (
                        ParamType(indices=tuple(index_types), elem=BOOL) if index_types else BOOL
                    )
                    self._define_find(scope, stmt, find_type, diagnostics)
                    continue

                if isinstance(stmt.decision_type, ast.IntDecisionType):
                    # Concrete bounds are validated and attached during grounding.
                    find_type = (
                        ParamType(
                            indices=tuple(index_types), elem=IntRangeType(-(2**31), 2**31 - 1)
                        )
                        if index_types
                        else IntRangeType(-(2**31), 2**31 - 1)
                    )
                    self._define_find(scope, stmt, find_type, diagnostics)
                    continue

                unknown_ref = stmt.unknown_type
                if stmt.indices:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2001",
                            message="unknown-valued find declarations cannot be indexed",
                            span=stmt.span,
                            help=["Use `find X : Subset(A)` or `find X[A] : Bool/Int[...]`."],
                        )
                    )
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
                elif unknown_ref.kind in {
                    "Matching",
                    "MaximalMatching",
                    "SpanningTree",
                    "Forest",
                }:
                    if len(unknown_ref.args) != 1:
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2001",
                                message=(
                                    f"{unknown_ref.kind} expects one UndirectedGraph "
                                    "structure argument"
                                ),
                                span=stmt.span,
                                help=[f"Use `find M : {unknown_ref.kind}(G);`."],
                            )
                        )
                    else:
                        graph_name = unknown_ref.args[0]
                        graph_symbol = scope.lookup(graph_name)
                        if (
                            graph_symbol is None
                            or graph_symbol.kind != SymbolKind.STRUCTURE
                            or not isinstance(graph_symbol.type, StructureInstanceType)
                            or graph_symbol.type.constructor != "UndirectedGraph"
                        ):
                            diagnostics.append(
                                Diagnostic(
                                    severity=Severity.ERROR,
                                    code="QSOL2001",
                                    message=(
                                        f"{unknown_ref.kind} expects an UndirectedGraph "
                                        "structure argument"
                                    ),
                                    span=stmt.span,
                                    help=[
                                        "Declare `structure G = UndirectedGraph(V, Edge);` "
                                        f"before `find M : {unknown_ref.kind}(G);`."
                                    ],
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
                self._define_find(scope, stmt, inst_type, diagnostics)

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

    def _define_find(
        self,
        scope: Scope,
        stmt: ast.FindDecl,
        find_type: Type,
        diagnostics: list[Diagnostic],
    ) -> None:
        existing = scope.symbols.get(stmt.name)
        if existing is not None:
            diagnostics.append(self._dup(stmt.span, stmt.name, previous=existing.span))
        else:
            scope.define(Symbol(stmt.name, SymbolKind.FIND, find_type, stmt.span))

    def _define_structure_domains(
        self,
        scope: Scope,
        stmt: ast.StructureDecl,
        diagnostics: list[Diagnostic],
    ) -> None:
        if stmt.constructor not in {"UndirectedGraph", "DirectedGraph"} or len(stmt.args) != 2:
            return
        vertex_name, relation_name = stmt.args
        vertex_symbol = scope.lookup(vertex_name)
        relation_symbol = scope.lookup(relation_name)
        if (
            vertex_symbol is None
            or vertex_symbol.kind != SymbolKind.SET
            or not isinstance(vertex_symbol.type, SetType)
            or relation_symbol is None
            or relation_symbol.kind != SymbolKind.RELATION
            or not isinstance(relation_symbol.type, RelationType)
        ):
            return
        fields = (
            RelationFieldType("u", vertex_symbol.type),
            RelationFieldType("v", vertex_symbol.type),
        )
        exposed: list[tuple[str, SymbolKind, Type]]
        if stmt.constructor == "UndirectedGraph":
            exposed = [
                (f"{stmt.name}.vertices", SymbolKind.SET, vertex_symbol.type),
                (
                    f"{stmt.name}.edges",
                    SymbolKind.RELATION,
                    RelationType(f"{stmt.name}.edges", fields),
                ),
                (
                    f"{stmt.name}.non_edges",
                    SymbolKind.RELATION,
                    RelationType(f"{stmt.name}.non_edges", fields),
                ),
            ]
        else:
            exposed = [
                (f"{stmt.name}.vertices", SymbolKind.SET, vertex_symbol.type),
                (
                    f"{stmt.name}.arcs",
                    SymbolKind.RELATION,
                    RelationType(f"{stmt.name}.arcs", fields),
                ),
                (
                    f"{stmt.name}.non_arcs",
                    SymbolKind.RELATION,
                    RelationType(f"{stmt.name}.non_arcs", fields),
                ),
            ]
        for name, kind, typ in exposed:
            existing = scope.symbols.get(name)
            if existing is not None:
                diagnostics.append(self._dup(stmt.span, name, previous=existing.span))
                continue
            scope.define(Symbol(name, kind, typ, stmt.span))

    def _param_value_to_type(
        self,
        scope: Scope,
        value_type: ast.ScalarTypeRef | ast.ElemTypeRef | ast.StaticSubsetTypeRef,
        diagnostics: list[Diagnostic],
        span: Span,
    ) -> Type:
        if isinstance(value_type, ast.ScalarTypeRef):
            return self._scalar_to_type(value_type)
        if isinstance(value_type, ast.StaticSubsetTypeRef):
            return SetType(value_type.set_name)

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
