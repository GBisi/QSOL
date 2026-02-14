from __future__ import annotations

from qsol.diag.source import Span
from qsol.parse import ast
from qsol.sema.resolver import Resolver
from qsol.sema.symbols import Scope, Symbol, SymbolKind
from qsol.sema.typecheck import TypeChecker
from qsol.sema.types import (
    ElemOfType,
    IntRangeType,
    ParamType,
    SetType,
    UnknownInstanceType,
    UnknownTypeRef,
)


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


def test_resolver_covers_duplicate_and_unknown_references() -> None:
    span = _span()
    problem = ast.ProblemDef(
        span=span,
        name="P",
        stmts=[
            ast.SetDecl(span=span, name="A"),
            ast.SetDecl(span=span, name="A"),
            ast.ParamDecl(
                span=span,
                name="w",
                indices=["MissingSet"],
                scalar_type=ast.ScalarTypeRef(span=span, kind="Real"),
                default=None,
            ),
            ast.FindDecl(
                span=span,
                name="S",
                unknown_type=ast.UnknownTypeRef(span=span, kind="Subset", args=("MissingSet",)),
            ),
            ast.FindDecl(
                span=span,
                name="M",
                unknown_type=ast.UnknownTypeRef(
                    span=span, kind="Mapping", args=("A", "MissingSet")
                ),
            ),
            ast.FindDecl(
                span=span,
                name="U",
                unknown_type=ast.UnknownTypeRef(span=span, kind="CustomUnknown", args=()),
            ),
        ],
    )
    unknown = ast.UnknownDef(
        span=span,
        name="CustomUnknown",
        formals=[],
        rep_block=[],
        laws_block=[],
        view_block=[],
    )
    duplicate_unknown = ast.UnknownDef(
        span=span,
        name="CustomUnknown",
        formals=[],
        rep_block=[],
        laws_block=[],
        view_block=[],
    )
    duplicate_problem = ast.ProblemDef(span=span, name="P", stmts=[])
    program = ast.Program(span=span, items=[unknown, duplicate_unknown, problem, duplicate_problem])

    result = Resolver().resolve(program)
    codes = [d.code for d in result.diagnostics]
    assert "QSOL2002" in codes
    assert "QSOL2201" in codes
    assert "QSOL2001" in codes


def test_typechecker_expr_branches() -> None:
    span = _span()
    checker = TypeChecker()
    scope = Scope(name="problem")
    scope.define(Symbol("A", SymbolKind.SET, SetType("A"), span))
    scope.define(Symbol("B", SymbolKind.SET, SetType("B"), span))
    scope.define(
        Symbol(
            "S",
            SymbolKind.FIND,
            UnknownInstanceType(ref=UnknownTypeRef(name="Subset", args=("A",))),
            span,
        )
    )
    scope.define(
        Symbol(
            "M",
            SymbolKind.FIND,
            UnknownInstanceType(ref=UnknownTypeRef(name="Mapping", args=("A", "B"))),
            span,
        )
    )
    scope.define(
        Symbol(
            "p",
            SymbolKind.PARAM,
            ParamType(indices=(SetType("A"),), elem=IntRangeType(lo=0, hi=10)),
            span,
        )
    )

    diagnostics = []
    tmap: dict[int, str] = {}
    binders = {"x": ElemOfType("A"), "y": ElemOfType("B")}

    exprs: list[ast.Expr] = [
        ast.Not(span=span, expr=ast.BoolLit(span=span, value=True)),
        ast.And(
            span=span,
            left=ast.BoolLit(span=span, value=True),
            right=ast.Or(
                span=span,
                left=ast.BoolLit(span=span, value=False),
                right=ast.BoolLit(span=span, value=True),
            ),
        ),
        ast.Implies(
            span=span,
            left=ast.BoolLit(span=span, value=True),
            right=ast.BoolLit(span=span, value=False),
        ),
        ast.Compare(
            span=span,
            op="<=",
            left=ast.NumLit(span=span, value=1),
            right=ast.NumLit(span=span, value=2),
        ),
        ast.Compare(
            span=span,
            op="=",
            left=ast.BoolLit(span=span, value=True),
            right=ast.BoolLit(span=span, value=False),
        ),
        ast.FuncCall(span=span, name="p", args=[ast.NameRef(span=span, name="x")]),
        ast.MethodCall(
            span=span,
            target=ast.NameRef(span=span, name="S"),
            name="has",
            args=[ast.NameRef(span=span, name="x")],
        ),
        ast.MethodCall(
            span=span,
            target=ast.NameRef(span=span, name="M"),
            name="is",
            args=[ast.NameRef(span=span, name="x"), ast.NameRef(span=span, name="y")],
        ),
        ast.Add(
            span=span,
            left=ast.NumLit(span=span, value=1),
            right=ast.Sub(
                span=span,
                left=ast.NumLit(span=span, value=3),
                right=ast.Mul(
                    span=span,
                    left=ast.NumLit(span=span, value=2),
                    right=ast.Div(
                        span=span,
                        left=ast.NumLit(span=span, value=4),
                        right=ast.NumLit(span=span, value=2),
                    ),
                ),
            ),
        ),
        ast.Neg(span=span, expr=ast.NumLit(span=span, value=1)),
        ast.IfThenElse(
            span=span,
            cond=ast.BoolLit(span=span, value=True),
            then_expr=ast.NumLit(span=span, value=1),
            else_expr=ast.NumLit(span=span, value=0),
        ),
        ast.Quantifier(
            span=span,
            kind="forall",
            var="z",
            domain_set="MissingSet",
            expr=ast.BoolLit(span=span, value=True),
        ),
        ast.BoolAggregate(
            span=span,
            kind="any",
            comp=ast.BoolComprehension(
                span=span,
                term=ast.BoolLit(span=span, value=True),
                var="x",
                domain_set="A",
                where=ast.BoolLit(span=span, value=True),
                else_term=ast.BoolLit(span=span, value=False),
            ),
        ),
        ast.NumAggregate(
            span=span,
            kind="sum",
            comp=ast.NumComprehension(
                span=span,
                term=ast.NumLit(span=span, value=1),
                var="x",
                domain_set="A",
                where=ast.BoolLit(span=span, value=True),
                else_term=ast.NumLit(span=span, value=0),
            ),
        ),
        ast.NumAggregate(
            span=span,
            kind="count",
            comp=ast.CountComprehension(
                span=span,
                var_ref="x",
                var="x",
                domain_set="A",
                where=ast.BoolLit(span=span, value=True),
                else_term=ast.BoolLit(span=span, value=False),
            ),
        ),
        ast.NameRef(span=span, name="unknown_name"),
        ast.StringLit(span=span, value="s"),
        ast.Literal(span=span, value=True),
    ]

    for expr in exprs:
        checker._expr_type(expr, scope, binders, diagnostics, tmap)

    assert tmap
    assert diagnostics
