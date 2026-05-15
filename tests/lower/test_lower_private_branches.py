from __future__ import annotations

from typing import cast

import pytest

from qsol.diag.source import Span
from qsol.lower import ir
from qsol.lower.lower import _lower_bool, _lower_expr, _lower_num, lower_symbolic
from qsol.parse import ast


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


def test_lower_symbolic_skips_non_problem_items() -> None:
    span = _span()
    unknown = ast.UnknownDef(
        span=span,
        name="U",
        formals=[],
        rep_block=[],
        laws_block=[],
        view_block=[],
    )
    program = ast.Program(
        span=span,
        items=[
            unknown,
            ast.ProblemDef(span=span, name="P", stmts=[ast.SetDecl(span=span, name="A")]),
        ],
    )
    lowered = lower_symbolic(program)
    assert len(lowered.problems) == 1
    assert lowered.problems[0].name == "P"


def test_comprehension_compat_properties_and_tuple_errors() -> None:
    span = _span()
    set_binder = ast.CompBinder(span=span, var="x", domain_set="A")
    tuple_binder = ast.TupleCompBinder(span=span, vars=("u", "v"), domain_relation="Edge")

    num_comp = ast.NumComprehension(
        span=span, term=ast.NumLit(span=span, value=1), binders=(set_binder,)
    )
    assert num_comp.var == "x"
    assert num_comp.domain_set == "A"
    bool_comp = ast.BoolComprehension(
        span=span, term=ast.BoolLit(span=span, value=True), binders=(tuple_binder,)
    )
    count_comp = ast.CountComprehension(span=span, var_ref="u", binders=(tuple_binder,))
    with pytest.raises(AttributeError):
        _ = bool_comp.var
    with pytest.raises(AttributeError):
        _ = bool_comp.domain_set
    with pytest.raises(AttributeError):
        _ = count_comp.var
    with pytest.raises(AttributeError):
        _ = count_comp.domain_set

    k_set_binder = ir.KCompBinder(span=span, var="x", domain_set="A")
    k_tuple_binder = ir.KTupleCompBinder(span=span, vars=("u", "v"), domain_relation="Edge")
    k_num_comp = ir.KNumComprehension(
        span=span, term=ir.KNumLit(span=span, value=1), binders=(k_set_binder,)
    )
    assert k_num_comp.var == "x"
    assert k_num_comp.domain_set == "A"
    k_bool_comp = ir.KBoolComprehension(
        span=span, term=ir.KBoolLit(span=span, value=True), binders=(k_tuple_binder,)
    )
    k_num_tuple_comp = ir.KNumComprehension(
        span=span, term=ir.KNumLit(span=span, value=1), binders=(k_tuple_binder,)
    )
    with pytest.raises(AttributeError):
        _ = k_bool_comp.var
    with pytest.raises(AttributeError):
        _ = k_bool_comp.domain_set
    with pytest.raises(AttributeError):
        _ = k_num_tuple_comp.var
    with pytest.raises(AttributeError):
        _ = k_num_tuple_comp.domain_set


def test_private_lower_helpers_cover_remaining_expression_branches() -> None:
    span = _span()
    assert isinstance(_lower_expr(ast.BoolLit(span=span, value=True)), ir.KBoolLit)
    with pytest.raises(TypeError):
        _lower_expr(ast.StringLit(span=span, value="bad"))

    bool_call = cast(
        ast.BoolExpr,
        ast.FuncCall(span=span, name="predicate", args=[ast.NameRef(span=span, name="x")]),
    )
    assert isinstance(_lower_bool(bool_call), ir.KFuncCall)
    assert isinstance(
        _lower_bool(cast(ast.BoolExpr, ast.NameRef(span=span, name="flag"))), ir.KName
    )
    with pytest.raises(TypeError):
        _lower_bool(cast(ast.BoolExpr, ast.StringLit(span=span, value="bad")))

    assert isinstance(
        _lower_num(
            ast.Add(
                span=span, left=ast.NumLit(span=span, value=1), right=ast.NumLit(span=span, value=2)
            )
        ),
        ir.KAdd,
    )
    assert isinstance(
        _lower_num(
            ast.Sub(
                span=span, left=ast.NumLit(span=span, value=3), right=ast.NumLit(span=span, value=1)
            )
        ),
        ir.KSub,
    )
    assert isinstance(
        _lower_num(
            ast.Mul(
                span=span, left=ast.NumLit(span=span, value=3), right=ast.NumLit(span=span, value=2)
            )
        ),
        ir.KMul,
    )
    assert isinstance(
        _lower_num(ast.Neg(span=span, expr=ast.NumLit(span=span, value=1))),
        ir.KNeg,
    )
    assert isinstance(_lower_num(cast(ast.NumExpr, ast.NameRef(span=span, name="n"))), ir.KName)

    with pytest.raises(TypeError):
        _lower_num(cast(ast.NumExpr, ast.StringLit(span=span, value="bad")))
