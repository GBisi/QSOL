from __future__ import annotations

import json
from pathlib import Path

import dimod

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.instance import (
    _eval_int_expr,
    _eval_num_expr,
    _eval_static_bool,
    _eval_static_value,
    _iter_static_binder_envs,
    instantiate_ir,
    load_instance,
    read_execution_config,
)
from qsol.diag.source import Span
from qsol.lower import ir
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


def _subset_find(name: str, set_name: str) -> ir.KFindDecl:
    span = _span()
    return ir.KFindDecl(
        span=span,
        name=name,
        unknown_type=ast.UnknownTypeRef(span=span, kind="Subset", args=(set_name,)),
    )


def _mapping_find(name: str, dom: str, cod: str) -> ir.KFindDecl:
    span = _span()
    return ir.KFindDecl(
        span=span,
        name=name,
        unknown_type=ast.UnknownTypeRef(span=span, kind="Mapping", args=(dom, cod)),
    )


def _contains_size_call(expr: ir.KExpr) -> bool:
    if isinstance(expr, ir.KFuncCall):
        return expr.name == "size" or any(_contains_size_call(arg) for arg in expr.args)
    if isinstance(expr, ir.KMethodCall):
        return _contains_size_call(expr.target) or any(
            _contains_size_call(arg) for arg in expr.args
        )
    if isinstance(expr, ir.KNot):
        return _contains_size_call(expr.expr)
    if isinstance(expr, (ir.KAnd, ir.KOr, ir.KImplies)):
        return _contains_size_call(expr.left) or _contains_size_call(expr.right)
    if isinstance(expr, ir.KCompare):
        return _contains_size_call(expr.left) or _contains_size_call(expr.right)
    if isinstance(expr, (ir.KAdd, ir.KSub, ir.KMul, ir.KDiv)):
        return _contains_size_call(expr.left) or _contains_size_call(expr.right)
    if isinstance(expr, ir.KNeg):
        return _contains_size_call(expr.expr)
    if isinstance(expr, ir.KIfThenElse):
        return (
            _contains_size_call(expr.cond)
            or _contains_size_call(expr.then_expr)
            or _contains_size_call(expr.else_expr)
        )

    if isinstance(expr, ir.KSum):
        return _contains_size_call(expr.comp.term)
    return False


def test_load_instance_requires_object_payload(tmp_path: Path) -> None:
    ok_path = tmp_path / "ok.json"
    ok_path.write_text(json.dumps({"sets": {}}), encoding="utf-8")
    assert load_instance(ok_path) == {"sets": {}}

    path = tmp_path / "bad.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    try:
        load_instance(path)
    except ValueError as exc:
        assert "instance payload must be a JSON object" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_instance_selection_execution_config_and_range_errors() -> None:
    assert read_execution_config({}).runtime is None
    assert (
        read_execution_config(
            {"execution": {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}}
        ).runtime
        == "local-dimod"
    )


def test_relation_instance_shape_diagnostics() -> None:
    span = _span()
    kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(ir.KSetDecl(span=span, name="V"),),
                relations=(
                    ir.KRelationDecl(
                        span=span,
                        name="Edge",
                        fields=(
                            ir.KRelationField(span=span, name="u", set_name="V"),
                            ir.KRelationField(span=span, name="v", set_name="V"),
                        ),
                    ),
                ),
                params=(),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )

    missing = instantiate_ir(kernel, {"problem": "P", "sets": {"V": ["a"]}})
    assert any("missing relation values for `Edge`" in d.message for d in missing.diagnostics)

    non_array = instantiate_ir(
        kernel,
        {"problem": "P", "sets": {"V": ["a"]}, "relations": {"Edge": "bad"}},
    )
    assert any("relation `Edge` must be an array" in d.message for d in non_array.diagnostics)

    missing_field_set_kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(),
                relations=(
                    ir.KRelationDecl(
                        span=span,
                        name="Edge",
                        fields=(ir.KRelationField(span=span, name="u", set_name="V"),),
                    ),
                ),
                params=(),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )
    missing_field_set = instantiate_ir(
        missing_field_set_kernel,
        {"problem": "P", "relations": {"Edge": [{"u": "a"}]}},
    )
    assert any("missing set values for `V`" in d.message for d in missing_field_set.diagnostics)

    wrong_shape = instantiate_ir(
        kernel,
        {
            "problem": "P",
            "sets": {"V": ["a"]},
            "relations": {"Edge": [{"u": "a"}, ["a"], "bad"], "Extra": []},
        },
    )
    messages = [d.message for d in wrong_shape.diagnostics]
    assert any("unknown relation `Extra`" in msg for msg in messages)
    assert any("wrong fields" in msg for msg in messages)
    assert any("wrong arity" in msg for msg in messages)
    assert any("must be an object or array" in msg for msg in messages)

    bad_elem = instantiate_ir(
        kernel,
        {
            "problem": "P",
            "sets": {"V": ["a"]},
            "relations": {"Edge": [{"u": "a", "v": "z"}]},
        },
    )
    assert any("outside its declared set" in d.message for d in bad_elem.diagnostics)

    derived_kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(ir.KSetDecl(span=span, name="V"),),
                relations=(
                    ir.KRelationDecl(
                        span=span,
                        name="Pair",
                        fields=(
                            ir.KRelationField(span=span, name="u", set_name="V"),
                            ir.KRelationField(span=span, name="v", set_name="V"),
                        ),
                        expr=ir.KPairsRelationExpr(
                            span=span,
                            binders=(
                                ir.KCompBinder(span=span, var="u", domain_set="V"),
                                ir.KCompBinder(span=span, var="v", domain_set="V"),
                            ),
                            where=None,
                        ),
                    ),
                ),
                params=(),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )
    supplied_derived = instantiate_ir(
        derived_kernel,
        {"problem": "P", "sets": {"V": ["a", "b"]}, "relations": {"Pair": [["a", "b"]]}},
    )
    assert any(
        "relation `Pair` is derived in source" in d.message for d in supplied_derived.diagnostics
    )

    kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(
                    ir.KSetDecl(
                        span=span,
                        name="Positions",
                        expr=ir.KRangeSetExpr(
                            span=span,
                            lo=ir.KNumLit(span=span, value=3.0),
                            hi=ir.KNumLit(span=span, value=1.0),
                        ),
                    ),
                ),
                params=(),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )

    missing = instantiate_ir(kernel, {"problem": "Missing", "sets": {}, "params": {}})
    assert missing.ground_ir is None
    assert any(
        diag.message == "instance problem does not match any compiled problem"
        for diag in missing.diagnostics
    )

    bad_range = instantiate_ir(kernel, {"problem": "P", "sets": {}, "params": {}})
    assert bad_range.ground_ir is None
    assert any(
        "Range lower bound exceeds upper bound" in diag.message for diag in bad_range.diagnostics
    )


def test_derived_relation_static_eval_branches() -> None:
    span = _span()
    diagnostics: list = []
    p_sets = {"V": ["a", "b"], "N": [1, 2]}
    p_relations = {"Edge": (("a", "b"),), "Loop": (("a", "a"),)}
    p_params = {
        "Flag": True,
        "Weight": {"a": 2, "b": 5},
        "Allowed": {"a": {"a": False, "b": True}, "b": {"a": False, "b": False}},
    }
    env = {"u": "a", "v": "b"}

    assert _iter_static_binder_envs(
        (
            ir.KCompBinder(span=span, var="n", domain_set="N"),
            ir.KTupleCompBinder(span=span, vars=("x", "y"), domain_relation="Edge"),
        ),
        p_sets=p_sets,
        p_relations=p_relations,
        span=span,
        diagnostics=diagnostics,
    ) == [{"n": 1, "x": "a", "y": "b"}, {"n": 2, "x": "a", "y": "b"}]

    relation_call = ir.KFuncCall(
        span=span,
        name="Edge",
        args=(ir.KName(span=span, name="u"), ir.KName(span=span, name="v")),
    )
    allowed_call = ir.KFuncCall(
        span=span,
        name="Allowed",
        args=(ir.KName(span=span, name="u"), ir.KName(span=span, name="v")),
    )
    bool_expr = ir.KBoolIfThenElse(
        span=span,
        cond=ir.KOr(
            span=span,
            left=ir.KName(span=span, name="Flag"),
            right=ir.KBoolLit(span=span, value=False),
        ),
        then_expr=ir.KAnd(
            span=span,
            left=ir.KNot(span=span, expr=ir.KBoolLit(span=span, value=False)),
            right=ir.KImplies(span=span, left=allowed_call, right=relation_call),
        ),
        else_expr=ir.KBoolLit(span=span, value=False),
    )
    assert (
        _eval_static_bool(
            bool_expr,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        is True
    )

    numeric_expr = ir.KIfThenElse(
        span=span,
        cond=ir.KCompare(
            span=span,
            op="<=",
            left=ir.KFuncCall(
                span=span,
                name="Weight",
                args=(ir.KName(span=span, name="u"),),
            ),
            right=ir.KFuncCall(
                span=span,
                name="Weight",
                args=(ir.KName(span=span, name="v"),),
            ),
        ),
        then_expr=ir.KAdd(
            span=span,
            left=ir.KFuncCall(span=span, name="size", args=(ir.KName(span=span, name="V"),)),
            right=ir.KMul(
                span=span,
                left=ir.KNumLit(span=span, value=3),
                right=ir.KDiv(
                    span=span,
                    left=ir.KNumLit(span=span, value=8),
                    right=ir.KNumLit(span=span, value=4),
                ),
            ),
        ),
        else_expr=ir.KNeg(span=span, expr=ir.KNumLit(span=span, value=1)),
    )
    assert (
        _eval_static_value(
            numeric_expr,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        == 8.0
    )

    assert (
        _eval_static_bool(
            ir.KCompare(
                span=span,
                op="!=",
                left=ir.KName(span=span, name="u"),
                right=ir.KName(span=span, name="v"),
            ),
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        is True
    )
    assert diagnostics == []


def test_derived_relation_static_eval_diagnostic_branches() -> None:
    span = _span()
    diagnostics: list = []

    assert (
        _iter_static_binder_envs(
            (ir.KTupleCompBinder(span=span, vars=("u", "v"), domain_relation="Missing"),),
            p_sets={"V": ["a"]},
            p_relations={},
            span=span,
            diagnostics=diagnostics,
        )
        == []
    )
    assert (
        _iter_static_binder_envs(
            (ir.KTupleCompBinder(span=span, vars=("u", "v"), domain_relation="Unary"),),
            p_sets={"V": ["a"]},
            p_relations={"Unary": (("a",),)},
            span=span,
            diagnostics=diagnostics,
        )
        == []
    )
    assert (
        _iter_static_binder_envs(
            (ir.KCompBinder(span=span, var="u", domain_set="Missing"),),
            p_sets={},
            p_relations={},
            span=span,
            diagnostics=diagnostics,
        )
        == []
    )

    empty_env: dict[str, object] = {}
    common = {
        "p_sets": {"V": ["a"]},
        "p_params": {},
        "p_relations": {"Edge": (("a", "a"),)},
        "env": empty_env,
        "diagnostics": diagnostics,
    }
    assert (
        _eval_static_bool(
            ir.KCompare(
                span=span,
                op="=",
                left=ir.KNumLit(span=span, value=1),
                right=ir.KNumLit(span=span, value=1),
            ),
            **common,
        )
        is True
    )
    assert (
        _eval_static_bool(
            ir.KCompare(
                span=span,
                op=">",
                left=ir.KNumLit(span=span, value=2),
                right=ir.KNumLit(span=span, value=1),
            ),
            **common,
        )
        is True
    )
    assert (
        _eval_static_bool(
            ir.KCompare(
                span=span,
                op="<",
                left=ir.KNumLit(span=span, value=1),
                right=ir.KNumLit(span=span, value=2),
            ),
            **common,
        )
        is True
    )
    assert (
        _eval_static_bool(
            ir.KCompare(
                span=span,
                op=">=",
                left=ir.KNumLit(span=span, value=2),
                right=ir.KNumLit(span=span, value=2),
            ),
            **common,
        )
        is True
    )
    assert (
        _eval_static_bool(
            ir.KCompare(
                span=span,
                op="<",
                left=ir.KName(span=span, name="missing"),
                right=ir.KNumLit(span=span, value=2),
            ),
            **common,
        )
        is None
    )
    assert (
        _eval_static_bool(
            ir.KMethodCall(
                span=span,
                target=ir.KName(span=span, name="Pick"),
                name="has",
                args=(),
            ),
            **common,
        )
        is None
    )
    assert (
        _eval_static_value(
            ir.KSub(
                span=span,
                left=ir.KNumLit(span=span, value=5),
                right=ir.KNumLit(span=span, value=3),
            ),
            **common,
        )
        == 2.0
    )
    assert (
        _eval_static_value(
            ir.KFuncCall(span=span, name="size", args=(ir.KName(span=span, name="Edge"),)),
            **common,
        )
        == 1.0
    )
    assert (
        _eval_static_value(
            ir.KFuncCall(span=span, name="MissingCall", args=()),
            **common,
        )
        is None
    )
    assert diagnostics


def test_instance_bound_expression_error_branches() -> None:
    span = _span()
    diagnostics: list = []

    assert (
        _eval_int_expr(
            ir.KNumLit(span=span, value=1.5),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KName(span=span, name="flag"),
            set_sizes={},
            params={"flag": True},
            diagnostics=diagnostics,
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KFuncCall(span=span, name="size", args=(ir.KName(span=span, name="Missing"),)),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KFuncCall(span=span, name="size", args=(ir.KName(span=span, name="Edge"),)),
            set_sizes={},
            relation_values={"Edge": (("a", "b"), ("b", "c"))},
            params={},
            diagnostics=diagnostics,
        )
        == 2.0
    )
    assert (
        _eval_num_expr(
            ir.KName(span=span, name="item"),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
            env={"item": "a"},
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KFuncCall(span=span, name="Weight", args=(ir.KName(span=span, name="item"),)),
            set_sizes={},
            set_values={"Items": ["a"]},
            params={"Weight": {"a": 7}},
            diagnostics=diagnostics,
            env={"item": "a"},
        )
        == 7.0
    )
    assert (
        _eval_num_expr(
            ir.KFuncCall(span=span, name="Flag", args=(ir.KName(span=span, name="item"),)),
            set_sizes={},
            set_values={"Items": ["a"]},
            params={"Flag": {"a": True}},
            diagnostics=diagnostics,
            env={"item": "a"},
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KAdd(
                span=span,
                left=ir.KNumLit(span=span, value=2.0),
                right=ir.KNumLit(span=span, value=3.0),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        == 5.0
    )
    assert (
        _eval_num_expr(
            ir.KSub(
                span=span,
                left=ir.KNumLit(span=span, value=5.0),
                right=ir.KNumLit(span=span, value=3.0),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        == 2.0
    )
    assert (
        _eval_num_expr(
            ir.KMul(
                span=span,
                left=ir.KNumLit(span=span, value=2.0),
                right=ir.KNumLit(span=span, value=3.0),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        == 6.0
    )
    assert (
        _eval_num_expr(
            ir.KDiv(
                span=span,
                left=ir.KNumLit(span=span, value=1.0),
                right=ir.KNumLit(span=span, value=0.0),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KNeg(span=span, expr=ir.KNumLit(span=span, value=4.0)),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        == -4.0
    )
    assert (
        _eval_num_expr(
            ir.KIfThenElse(
                span=span,
                cond=ir.KBoolLit(span=span, value=True),
                then_expr=ir.KNumLit(span=span, value=9.0),
                else_expr=ir.KNumLit(span=span, value=0.0),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        == 9.0
    )
    assert (
        _eval_num_expr(
            ir.KSum(
                span=span,
                comp=ir.KNumComprehension(
                    span=span,
                    term=ir.KFuncCall(
                        span=span,
                        name="Weight",
                        args=(ir.KName(span=span, name="item"),),
                    ),
                    binders=(ir.KCompBinder(span=span, var="item", domain_set="Items"),),
                ),
            ),
            set_sizes={"Items": 2},
            set_values={"Items": ["a", "b"]},
            params={"Weight": {"a": 2, "b": 5}},
            diagnostics=diagnostics,
        )
        == 7.0
    )
    assert (
        _eval_num_expr(
            ir.KSum(
                span=span,
                comp=ir.KNumComprehension(
                    span=span,
                    term=ir.KNumLit(span=span, value=1.0),
                    binders=(ir.KCompBinder(span=span, var="item", domain_set="Items"),),
                ),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        is None
    )
    assert (
        _eval_num_expr(
            ir.KCompare(
                span=span,
                op="=",
                left=ir.KNumLit(span=span, value=1.0),
                right=ir.KNumLit(span=span, value=1.0),
            ),
            set_sizes={},
            params={},
            diagnostics=diagnostics,
        )
        is None
    )
    assert any(
        "integer bound expression must evaluate to an integer" in diag.message
        for diag in diagnostics
    )
    assert any("division by zero in integer bound" in diag.message for diag in diagnostics)


def test_instantiate_ir_emits_shape_and_missing_errors() -> None:
    span = _span()
    kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(ir.KSetDecl(span=span, name="A"),),
                params=(
                    ir.KParamDecl(
                        span=span,
                        name="w",
                        indices=("A",),
                        scalar_kind="Real",
                        elem_set=None,
                        default=1.0,
                    ),
                ),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )

    result = instantiate_ir(
        kernel,
        {
            "problem": "P",
            "sets": {"A": "not-a-list"},
            "params": {"w": {"a1": {"nested": 1}}},
        },
    )
    assert result.ground_ir is None
    codes = [d.code for d in result.diagnostics]
    assert "QSOL2201" in codes

    missing_kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(ir.KSetDecl(span=span, name="A"),),
                params=(
                    ir.KParamDecl(
                        span=span,
                        name="w",
                        indices=("A",),
                        scalar_kind="Real",
                        elem_set=None,
                        default=None,
                    ),
                ),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )
    missing_param = instantiate_ir(
        missing_kernel,
        {
            "problem": "P",
            "sets": {"A": ["a1"]},
            "params": {},
        },
    )
    assert missing_param.ground_ir is None
    assert any("missing value for param `w`" in diag.message for diag in missing_param.diagnostics)

    scalar_for_indexed = instantiate_ir(
        missing_kernel,
        {
            "problem": "P",
            "sets": {"A": ["a1"]},
            "params": {"w": 1.0},
        },
    )
    assert scalar_for_indexed.ground_ir is None
    assert any(
        "param `w` expects indexed object" in diag.message
        for diag in scalar_for_indexed.diagnostics
    )


def test_instantiate_ir_validates_and_normalizes_elem_params() -> None:
    span = _span()
    kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(
                    ir.KSetDecl(span=span, name="V"),
                    ir.KSetDecl(span=span, name="E"),
                ),
                params=(
                    ir.KParamDecl(
                        span=span,
                        name="U",
                        indices=("E",),
                        scalar_kind="Elem",
                        elem_set="V",
                        default=None,
                    ),
                ),
                finds=(),
                constraints=(),
                objectives=(),
            ),
        ),
    )

    ok = instantiate_ir(
        kernel,
        {
            "problem": "P",
            "sets": {"V": [0, 1], "E": ["e0", "e1"]},
            "params": {"U": {"e0": 0, "e1": "1"}},
        },
    )
    assert ok.ground_ir is not None
    assert not any(diag.is_error for diag in ok.diagnostics)
    assert ok.ground_ir.problems[0].params["U"] == {"e0": "0", "e1": "1"}

    bad = instantiate_ir(
        kernel,
        {
            "problem": "P",
            "sets": {"V": [0, 1], "E": ["e0", "e1"]},
            "params": {"U": {"e0": 2, "e1": 1}},
        },
    )
    assert bad.ground_ir is None
    assert any("not present in set `V`" in diag.message for diag in bad.diagnostics)


def test_instantiate_ir_folds_size_builtin_to_numeric_literal() -> None:
    span = _span()
    kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(ir.KSetDecl(span=span, name="V"),),
                params=(),
                finds=(),
                constraints=(),
                objectives=(
                    ir.KObjective(
                        span=span,
                        kind=ast.ObjectiveKind.MINIMIZE,
                        expr=ir.KFuncCall(
                            span=span,
                            name="size",
                            args=(ir.KName(span=span, name="V"),),
                        ),
                    ),
                ),
            ),
        ),
    )
    result = instantiate_ir(
        kernel,
        {"problem": "P", "sets": {"V": ["v1", "v2", "v3"]}, "params": {}},
    )
    assert result.ground_ir is not None
    assert not any(diag.is_error for diag in result.diagnostics)

    expr = result.ground_ir.problems[0].objectives[0].expr
    assert isinstance(expr, ir.KNumLit)
    assert expr.value == 3.0
    assert not _contains_size_call(expr)


def test_instantiate_ir_keeps_missing_set_behavior_for_size_builtin() -> None:
    span = _span()
    kernel = ir.KernelIR(
        span=span,
        problems=(
            ir.KProblem(
                span=span,
                name="P",
                sets=(ir.KSetDecl(span=span, name="V"),),
                params=(),
                finds=(),
                constraints=(),
                objectives=(
                    ir.KObjective(
                        span=span,
                        kind=ast.ObjectiveKind.MINIMIZE,
                        expr=ir.KFuncCall(
                            span=span,
                            name="size",
                            args=(ir.KName(span=span, name="V"),),
                        ),
                    ),
                ),
            ),
        ),
    )
    result = instantiate_ir(kernel, {"problem": "P", "sets": {}, "params": {}})
    assert result.ground_ir is None
    assert any(diag.code == "QSOL2201" for diag in result.diagnostics)
    assert not any(diag.code == "QSOL2101" for diag in result.diagnostics)


def test_dimod_codegen_covers_soft_and_compare_paths() -> None:
    span = _span()
    x = ir.KName(span=span, name="x")
    s_name = ir.KName(span=span, name="S")
    has_a1 = ir.KMethodCall(
        span=span, target=s_name, name="has", args=(ir.KName(span=span, name="a1"),)
    )

    problem = ir.GroundProblem(
        span=span,
        name="P",
        set_values={"A": ["a1", "a2"], "B": ["b1", "b2"]},
        params={
            "w": {"a1": 2.0, "a2": 3.0},
            "alpha": 1.5,
            "flag": {"a1": True, "a2": False},
        },
        finds=(
            _subset_find("S", "A"),
            _mapping_find("M", "A", "B"),
            ir.KFindDecl(
                span=span,
                name="U",
                unknown_type=ast.UnknownTypeRef(span=span, kind="Custom", args=()),
            ),
        ),
        constraints=(
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KCompare(
                    span=span,
                    op="=",
                    left=has_a1,
                    right=ir.KNumLit(span=span, value=1.0),
                ),
            ),
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KCompare(
                    span=span,
                    op="!=",
                    left=ir.KNumLit(span=span, value=1.0),
                    right=ir.KNumLit(span=span, value=2.0),
                ),
            ),
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.SHOULD,
                expr=ir.KOr(span=span, left=has_a1, right=ir.KBoolLit(span=span, value=False)),
            ),
        ),
        objectives=(
            ir.KObjective(
                span=span,
                kind=ast.ObjectiveKind.MINIMIZE,
                expr=ir.KAdd(
                    span=span,
                    left=ir.KName(span=span, name="alpha"),
                    right=ir.KNeg(
                        span=span,
                        expr=ir.KDiv(
                            span=span,
                            left=ir.KMul(
                                span=span,
                                left=ir.KNumLit(span=span, value=4.0),
                                right=ir.KSub(
                                    span=span,
                                    left=ir.KNumLit(span=span, value=3.0),
                                    right=ir.KNumLit(span=span, value=1.0),
                                ),
                            ),
                            right=ir.KNumLit(span=span, value=2.0),
                        ),
                    ),
                ),
            ),
            ir.KObjective(
                span=span,
                kind=ast.ObjectiveKind.MAXIMIZE,
                expr=ir.KIfThenElse(
                    span=span,
                    cond=has_a1,
                    then_expr=ir.KSum(
                        span=span,
                        comp=ir.KNumComprehension(
                            span=span,
                            term=ir.KFuncCall(span=span, name="w", args=(x,)),
                            var="x",
                            domain_set="A",
                        ),
                    ),
                    else_expr=ir.KNumLit(span=span, value=0.0),
                ),
            ),
        ),
    )

    result = DimodCodegen().compile(ir.GroundIR(span=span, problems=(problem,)))
    assert result.bqm.num_variables > 0
    assert any(
        "unsupported" in d.message or "not supported" in d.message for d in result.diagnostics
    )
    assert not any(
        d.message == "`!=` constraints are not supported in backend v1" for d in result.diagnostics
    )
    assert any(key.startswith("S.has[") for key in result.varmap)
    assert any(key.startswith("M.is[") for key in result.varmap)


def test_dimod_codegen_internal_error_paths() -> None:
    span = _span()
    codegen = DimodCodegen()
    codegen._label_counter = 0
    diagnostics: list = []
    problem = ir.GroundProblem(
        span=span,
        name="P",
        set_values={"A": ["a1"]},
        params={"p": {"a1": 1.0}},
        finds=(),
        constraints=(),
        objectives=(),
    )
    binaries = {"S.has[a1]": dimod.Binary("S.has[a1]")}
    cqm = dimod.ConstrainedQuadraticModel()

    # Unknown set in soft quantifier.

    # Unknown method variable label path.
    bad_method = ir.KMethodCall(
        span=span,
        target=ir.KName(span=span, name="S"),
        name="has",
        args=(ir.KName(span=span, name="missing"),),
    )
    assert codegen._bool_atom(problem, bad_method, binaries, diagnostics, env={}) is None

    # Unsupported numeric expression and non-numeric binder path.
    assert (
        codegen._num_expr(
            problem,
            ir.KName(span=span, name="x"),
            binaries,
            diagnostics,
            env={"x": "abc"},
            cqm=cqm,
        )
        is None
    )
    assert (
        codegen._num_expr(
            problem,
            ir.KCompare(
                span=span,
                op="<",
                left=ir.KNumLit(span=span, value=1),
                right=ir.KNumLit(span=span, value=2),
            ),
            binaries,
            diagnostics,
            env={},
            cqm=cqm,
        )
        is None
    )

    # Unsupported objective path in compile().
    bad_problem = ir.GroundProblem(
        span=span,
        name="Bad",
        set_values={"A": ["a1"]},
        params={},
        finds=(_subset_find("S", "A"),),
        constraints=(
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.SHOULD,
                expr=ir.KCompare(
                    span=span,
                    op="!=",
                    left=ir.KNumLit(span=span, value=1),
                    right=ir.KNumLit(span=span, value=2),
                ),
            ),
        ),
        objectives=(
            ir.KObjective(
                span=span,
                kind=ast.ObjectiveKind.MINIMIZE,
                expr=ir.KMethodCall(
                    span=span,
                    target=ir.KName(span=span, name="S"),
                    name="has",
                    args=(ir.KName(span=span, name="a1"),),
                ),
            ),
            ir.KObjective(
                span=span,
                kind=ast.ObjectiveKind.MINIMIZE,
                expr=ir.KCompare(
                    span=span,
                    op="=",
                    left=ir.KNumLit(span=span, value=1),
                    right=ir.KNumLit(span=span, value=1),
                ),
            ),
        ),
    )
    compile_result = codegen.compile(ir.GroundIR(span=span, problems=(bad_problem,)))
    assert compile_result.diagnostics
    assert not any(
        d.message == "`!=` constraints are not supported in backend v1"
        for d in compile_result.diagnostics
    )

    # Mapping declaration with missing set.
    cqm = dimod.ConstrainedQuadraticModel()
    missing_mapping = ir.GroundProblem(
        span=span,
        name="MapMissing",
        set_values={"A": ["a1"]},
        params={},
        finds=(_mapping_find("M", "A", "B"),),
        constraints=(),
        objectives=(),
    )
    codegen._declare_find_variables(missing_mapping, cqm, {}, {}, diagnostics)

    # Explicitly cover emit paths for NOT and inequality operators.
    cqm2 = dimod.ConstrainedQuadraticModel()
    declared_binaries: dict[str, object] = {}
    codegen._declare_find_variables(
        ir.GroundProblem(
            span=span,
            name="Emit",
            set_values={"A": ["a1"]},
            params={},
            finds=(_subset_find("S", "A"),),
            constraints=(),
            objectives=(),
        ),
        cqm2,
        declared_binaries,
        {},
        diagnostics,
    )
    codegen._emit_constraint(
        problem,
        ir.KNot(
            span=span,
            expr=ir.KMethodCall(
                span=span,
                target=ir.KName(span=span, name="S"),
                name="has",
                args=(ir.KName(span=span, name="a1"),),
            ),
        ),
        cqm2,
        declared_binaries,
        diagnostics,
        env={},
    )
    for op in ("<", ">", "<=", ">="):
        codegen._emit_constraint(
            problem,
            ir.KCompare(
                span=span,
                op=op,
                left=ir.KMethodCall(
                    span=span,
                    target=ir.KName(span=span, name="S"),
                    name="has",
                    args=(ir.KName(span=span, name="a1"),),
                ),
                right=ir.KNumLit(span=span, value=1.0),
            ),
            cqm2,
            declared_binaries,
            diagnostics,
            env={},
        )

    # Direct bool/num helper edge paths.
    assert (
        codegen._bool_expr(
            problem,
            ir.KCompare(
                span=span,
                op="=",
                left=ir.KNumLit(span=span, value=1),
                right=ir.KNumLit(span=span, value=1),
            ),
            binaries,
            diagnostics,
            env={},
            cqm=cqm2,
        )
        is not None
    )
    assert (
        codegen._num_expr(
            problem,
            ir.KSum(
                span=span,
                comp=ir.KNumComprehension(
                    span=span,
                    term=ir.KCompare(
                        span=span,
                        op="=",
                        left=ir.KNumLit(span=span, value=1),
                        right=ir.KNumLit(span=span, value=1),
                    ),
                    var="x",
                    domain_set="A",
                ),
            ),
            binaries,
            diagnostics,
            env={},
            cqm=cqm2,
        )
        is None
    )


def test_dimod_codegen_bool_ops_prefer_algebraic_forms() -> None:
    span = _span()
    codegen = DimodCodegen()
    codegen._label_counter = 0
    diagnostics: list = []
    cqm = dimod.ConstrainedQuadraticModel()
    x = dimod.Binary("x")
    y = dimod.Binary("y")

    and_expr = codegen._bool_and(cqm, x, y, span=span, diagnostics=diagnostics)
    or_expr = codegen._bool_or(cqm, x, y, span=span, diagnostics=diagnostics)

    assert and_expr is not None
    assert or_expr is not None
    assert codegen._is_quadratic_model(and_expr)
    assert codegen._is_quadratic_model(or_expr)
    assert len(cqm.constraints) == 0
    assert not diagnostics


def test_dimod_codegen_bool_ops_fallback_when_product_is_not_quadratic_safe() -> None:
    span = _span()
    codegen = DimodCodegen()
    codegen._label_counter = 0
    diagnostics: list = []
    cqm = dimod.ConstrainedQuadraticModel()
    x = dimod.Binary("x")
    y = dimod.Binary("y")
    z = dimod.Binary("z")

    # x or y is quadratic in algebraic form; multiplying it by z is cubic and
    # triggers the conservative aux-variable fallback path.
    quadratic_or = codegen._bool_or(cqm, x, y, span=span, diagnostics=diagnostics)
    assert quadratic_or is not None
    constraints_before = len(cqm.constraints)

    fallback_and = codegen._bool_and(cqm, quadratic_or, z, span=span, diagnostics=diagnostics)
    assert fallback_and is not None
    assert len(cqm.constraints) == constraints_before + 3
    assert any(str(label).startswith("aux:and:") for label in fallback_and.variables)

    # x and y is quadratic in algebraic form; combining with z via OR similarly
    # triggers fallback to the reified constraints.
    quadratic_and = codegen._bool_and(cqm, x, y, span=span, diagnostics=diagnostics)
    assert quadratic_and is not None
    constraints_before = len(cqm.constraints)

    fallback_or = codegen._bool_or(cqm, quadratic_and, z, span=span, diagnostics=diagnostics)
    assert fallback_or is not None
    assert len(cqm.constraints) == constraints_before + 3
    assert any(str(label).startswith("aux:or:") for label in fallback_or.variables)
    assert not any(diag.is_error for diag in diagnostics)


def test_dimod_codegen_treats_should_false_as_soft_only() -> None:
    span = _span()
    problem = ir.GroundProblem(
        span=span,
        name="SoftOnly",
        set_values={"A": ["a1"]},
        params={},
        finds=(_subset_find("S", "A"),),
        constraints=(
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.SHOULD,
                expr=ir.KBoolLit(span=span, value=False),
            ),
        ),
        objectives=(),
    )

    result = DimodCodegen().compile(ir.GroundIR(span=span, problems=(problem,)))
    assert not any(diag.is_error for diag in result.diagnostics)
    assert len(result.cqm.constraints) == 0


def test_dimod_codegen_scalar_decisions_quantifiers_and_stats() -> None:
    span = _span()
    i_name = ir.KName(span=span, name="i")
    load_i = ir.KFuncCall(span=span, name="Load", args=(i_name,))
    flag_i = ir.KFuncCall(span=span, name="Flag", args=(i_name,))
    flag_one = ir.KFuncCall(span=span, name="Flag", args=(ir.KNumLit(span=span, value=1.0),))

    problem = ir.GroundProblem(
        span=span,
        name="Scalar",
        set_values={"A": [1, 2]},
        params={},
        finds=(
            ir.KFindDecl(span=span, name="enabled", decision_type=ir.KBoolDecisionType(span=span)),
            ir.KFindDecl(
                span=span,
                name="T",
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KNumLit(span=span, value=0.0),
                    hi=ir.KNumLit(span=span, value=3.0),
                ),
            ),
            ir.KFindDecl(
                span=span,
                name="Flag",
                indices=("A",),
                decision_type=ir.KBoolDecisionType(span=span),
            ),
            ir.KFindDecl(
                span=span,
                name="Load",
                indices=("A",),
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KNumLit(span=span, value=0.0),
                    hi=ir.KNumLit(span=span, value=3.0),
                ),
            ),
        ),
        constraints=(
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KQuantifier(
                    span=span,
                    kind="forall",
                    var="i",
                    domain_set="A",
                    expr=ir.KCompare(span=span, op=">=", left=load_i, right=i_name),
                ),
            ),
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KQuantifier(
                    span=span,
                    kind="exists",
                    var="i",
                    domain_set="A",
                    expr=flag_i,
                ),
            ),
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KImplies(
                    span=span, left=ir.KName(span=span, name="enabled"), right=flag_one
                ),
            ),
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.SHOULD,
                expr=ir.KQuantifier(
                    span=span,
                    kind="forall",
                    var="i",
                    domain_set="A",
                    expr=flag_i,
                ),
            ),
        ),
        objectives=(
            ir.KObjective(
                span=span,
                kind=ast.ObjectiveKind.MINIMIZE,
                expr=ir.KAdd(
                    span=span,
                    left=ir.KSum(
                        span=span,
                        comp=ir.KNumComprehension(
                            span=span,
                            term=load_i,
                            var="i",
                            domain_set="A",
                        ),
                    ),
                    right=ir.KIfThenElse(
                        span=span,
                        cond=flag_one,
                        then_expr=ir.KName(span=span, name="T"),
                        else_expr=ir.KNumLit(span=span, value=0.0),
                    ),
                ),
            ),
        ),
    )

    result = DimodCodegen().compile(ir.GroundIR(span=span, problems=(problem,)))

    assert not any(diag.is_error for diag in result.diagnostics)
    assert result.cqm.vartype("enabled") == dimod.BINARY
    assert result.cqm.vartype("T") == dimod.INTEGER
    assert result.cqm.vartype("Load[1]") == dimod.INTEGER
    assert result.varmap["Flag[1]"] == "Flag[1]"
    assert len(result.cqm.constraints) >= 4


def test_dimod_codegen_reports_scalar_branch_errors() -> None:
    span = _span()
    codegen = DimodCodegen()
    codegen._label_counter = 0
    diagnostics: list = []
    cqm = dimod.ConstrainedQuadraticModel()
    problem = ir.GroundProblem(
        span=span,
        name="BadScalar",
        set_values={},
        params={},
        finds=(
            ir.KFindDecl(
                span=span,
                name="x",
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KName(span=span, name="lo"),
                    hi=ir.KNumLit(span=span, value=3.0),
                ),
            ),
        ),
        constraints=(),
        objectives=(),
    )

    codegen._declare_find_variables(problem, cqm, {}, {}, diagnostics)
    assert any("ungrounded Int domain" in diag.message for diag in diagnostics)

    bad_call = ir.KFuncCall(
        span=span,
        name="Load",
        args=(ir.KName(span=span, name="x"), ir.KName(span=span, name="y")),
    )
    indexed_problem = ir.GroundProblem(
        span=span,
        name="Indexed",
        set_values={"A": ["a1"]},
        params={},
        finds=(
            ir.KFindDecl(
                span=span,
                name="Load",
                indices=("A",),
                decision_type=ir.KIntDecisionType(
                    span=span,
                    lo=ir.KNumLit(span=span, value=0.0),
                    hi=ir.KNumLit(span=span, value=1.0),
                ),
            ),
        ),
        constraints=(),
        objectives=(),
    )
    assert codegen._indexed_scalar_label(indexed_problem, bad_call, diagnostics, env={}) is None
    assert any("expects 1 index argument" in diag.message for diag in diagnostics)


def test_dimod_codegen_reports_infeasible_constant_hard_not_equal() -> None:
    span = _span()
    problem = ir.GroundProblem(
        span=span,
        name="HardNotEqualInfeasible",
        set_values={"A": ["a1"]},
        params={},
        finds=(_subset_find("S", "A"),),
        constraints=(
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=ir.KCompare(
                    span=span,
                    op="!=",
                    left=ir.KNumLit(span=span, value=1.0),
                    right=ir.KNumLit(span=span, value=1.0),
                ),
            ),
        ),
        objectives=(),
    )

    result = DimodCodegen().compile(ir.GroundIR(span=span, problems=(problem,)))
    assert any(diag.is_error for diag in result.diagnostics)
    assert any(diag.message == "infeasible constant constraint `=`" for diag in result.diagnostics)
