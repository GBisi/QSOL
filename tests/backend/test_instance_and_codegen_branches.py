from __future__ import annotations

import json
from pathlib import Path

import dimod

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.instance import instantiate_ir, load_instance
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


def test_load_instance_requires_object_payload(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    try:
        load_instance(path)
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected ValueError")


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


def test_dimod_codegen_covers_soft_and_compare_paths() -> None:
    span = _span()
    x = ir.KName(span=span, name="x")
    s_name = ir.KName(span=span, name="S")
    has_x = ir.KMethodCall(span=span, target=s_name, name="has", args=(x,))
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
                expr=ir.KQuantifier(
                    span=span,
                    kind="forall",
                    var="x",
                    domain_set="A",
                    expr=ir.KAnd(
                        span=span,
                        left=has_x,
                        right=ir.KImplies(
                            span=span,
                            left=has_x,
                            right=ir.KNot(span=span, expr=ir.KBoolLit(span=span, value=False)),
                        ),
                    ),
                ),
            ),
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
            ir.KConstraint(
                span=span,
                kind=ast.ConstraintKind.NICE,
                expr=ir.KQuantifier(
                    span=span,
                    kind="exists",
                    var="x",
                    domain_set="A",
                    expr=has_x,
                ),
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

    # Unknown set in soft quantifier.
    bad_quant = ir.KQuantifier(
        span=span,
        kind="forall",
        var="x",
        domain_set="Missing",
        expr=ir.KBoolLit(span=span, value=True),
    )
    assert codegen._soft_penalty(problem, bad_quant, binaries, diagnostics, env={}) is None

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
            problem, ir.KName(span=span, name="x"), binaries, diagnostics, env={"x": "abc"}
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
        )
        is None
    )

    # Unsupported objective and unsupported soft-constraint paths in compile().
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
        )
        is None
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
        )
        is None
    )
