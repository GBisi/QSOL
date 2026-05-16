from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source
from qsol.diag.source import Span
from qsol.lower import ir
from qsol.lower.piecewise import (
    _BoundAnalyzer,
    _Bounds,
    _combine_bounds,
    _contains_piecewise_call,
    _max_abs_bound,
    _mul_bounds,
    lower_piecewise_program,
)
from qsol.parse import ast


def _span() -> Span:
    return Span(
        start_offset=0,
        end_offset=1,
        line=1,
        col=1,
        end_line=1,
        end_col=2,
        filename="piecewise_test.qsol",
    )


def test_abs_constraint_lowers_without_auxiliary() -> None:
    text = """
problem P {
  find Balance : Int[0 .. 10];
  must abs(Balance - 5) <= 2;
  must 3 >= abs(Balance - 5);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="abs_constraint.qsol"))

    assert unit.lowered_ir_symbolic is not None
    assert not any(d.code == "QSOL3101" for d in unit.diagnostics)
    problem = unit.lowered_ir_symbolic.problems[0]
    assert len(problem.finds) == 1
    assert len(problem.constraints) == 4
    assert all(isinstance(constraint.expr, ir.KCompare) for constraint in problem.constraints)


def test_abs_constraint_rejects_unsupported_direction() -> None:
    text = """
problem P {
  find Balance : Int[0 .. 10];
  must abs(Balance) >= 2;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="abs_constraint_bad.qsol"))

    assert any(
        d.code == "QSOL3101" and "unsupported piecewise constraint context" in d.message
        for d in unit.diagnostics
    )
    assert unit.lowered_ir_symbolic is None


def test_maximize_min_aggregate_lowers_to_auxiliary() -> None:
    text = """
problem P {
  set Agents;
  find Score[Agents] : Int[0 .. 10];
  maximize min(Score[a] for a in Agents);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="min_lower.qsol"))

    assert unit.lowered_ir_symbolic is not None
    problem = unit.lowered_ir_symbolic.problems[0]
    aux = [find for find in problem.finds if find.name.startswith("__qsol_piecewise_min_")]
    assert len(aux) == 1
    assert len(problem.constraints) == 1
    assert isinstance(problem.constraints[0].expr, ir.KQuantifier)
    assert isinstance(problem.objectives[0].expr, ir.KName)


def test_piecewise_rejects_unsupported_objective_contexts() -> None:
    text = """
problem BadMax {
  set A;
  find X[A] : Int[0 .. 10];
  maximize max(X[a] for a in A);
}

problem BadMin {
  set A;
  find X[A] : Int[0 .. 10];
  minimize min(X[a] for a in A);
}

problem BadNested {
  find X : Int[0 .. 10];
  minimize max(X, 1);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="piecewise_bad_contexts.qsol"))
    messages = [d.message for d in unit.diagnostics if d.code == "QSOL3101"]

    assert any("maximize max()" in message for message in messages)
    assert any("minimize min()" in message for message in messages)
    assert any("unsupported piecewise objective context" in message for message in messages)


def test_abs_objective_uses_next_auxiliary_name_when_prefix_collides() -> None:
    text = """
problem P {
  find __qsol_piecewise_abs_0 : Int[0 .. 1];
  find Balance : Int[0 .. 10];
  minimize abs(Balance - 5);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="abs_collision.qsol"))

    assert unit.lowered_ir_symbolic is not None
    names = [find.name for find in unit.lowered_ir_symbolic.problems[0].finds]
    assert "__qsol_piecewise_abs_1" in names


def test_abs_objective_rejects_missing_finite_bounds() -> None:
    text = """
problem P {
  param Cost : Real;
  minimize abs(Cost);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="abs_unbounded.qsol"))

    assert any(
        d.code == "QSOL3101" and "missing finite bounds for abs()" in d.message
        for d in unit.diagnostics
    )


def test_piecewise_bounds_cover_complex_numeric_forms() -> None:
    text = """
problem P {
  set Machines;
  set Slots = Range(1, 3);
  find Left : Int[0 .. 5];
  find Right : Int[0 .. 5];
  find Enabled : Bool;
  find Load[Machines] : Int[0 .. 10];

  minimize abs((Left - Right) * 2 / 1);
  minimize abs(if Enabled then Left else Right);
  minimize max(Load[m] for m in Machines);
  maximize min(s + 0 for s in Slots);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="piecewise_complex.qsol"))

    assert unit.lowered_ir_symbolic is not None
    assert not any(d.code == "QSOL3101" for d in unit.diagnostics)
    problem = unit.lowered_ir_symbolic.problems[0]
    assert any(find.name.startswith("__qsol_piecewise_abs_") for find in problem.finds)
    assert any(find.name.startswith("__qsol_piecewise_max_") for find in problem.finds)
    assert any(find.name.startswith("__qsol_piecewise_min_") for find in problem.finds)


def test_piecewise_reports_missing_bounds_for_aggregate_auxiliaries() -> None:
    text = """
problem BadAbsSum {
  set A;
  find X[A] : Int[0 .. 10];
  minimize abs(sum(X[a] for a in A));
}

problem BadMax {
  set A;
  param Cost[A] : Real;
  minimize max(Cost[a] for a in A);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="piecewise_missing_bounds.qsol"))
    messages = [d.message for d in unit.diagnostics if d.code == "QSOL3101"]

    assert any("missing finite bounds for abs()" in message for message in messages)
    assert any("missing finite bounds for max()" in message for message in messages)


def test_piecewise_tuple_binder_bounds_and_quantifier_lowering() -> None:
    text = """
problem TupleMax {
  set Slots = Range(1, 3);
  relation Pair(a: Slots, b: Slots);

  minimize max(a + b for (a, b) in Pair);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="tuple_max.qsol"))

    assert unit.lowered_ir_symbolic is not None
    problem = unit.lowered_ir_symbolic.problems[0]
    assert isinstance(problem.constraints[0].expr, ir.KTupleQuantifier)


def test_piecewise_private_helpers_cover_uncommon_branches() -> None:
    span = _span()
    one = ast.NumLit(span=span, value=1)
    two = ast.NumLit(span=span, value=2)
    three = ast.NumLit(span=span, value=3)

    assert _combine_bounds(span, None, _Bounds(one, two), "+") is None
    assert _mul_bounds(span, None, _Bounds(one, two)) is None
    assert _max_abs_bound(span, _Bounds(ast.NameRef(span=span, name="lo"), two)) is None
    assert _mul_bounds(span, _Bounds(one, two), _Bounds(two, three)) is not None

    method = ast.MethodCall(
        span=span,
        target=ast.FuncCall(span=span, name="abs", args=[one]),
        name="value",
        args=[],
    )
    assert _contains_piecewise_call(method)

    bool_if = ast.BoolIfThenElse(
        span=span,
        cond=ast.BoolLit(span=span, value=True),
        then_expr=ast.BoolLit(span=span, value=False),
        else_expr=ast.FuncCall(span=span, name="max", args=[one]),
    )
    assert _contains_piecewise_call(bool_if)

    unknown = ast.UnknownDef(
        span=span,
        name="U",
        formals=[],
        rep_block=[],
        laws_block=[],
        view_block=[],
    )
    program = ast.Program(span=span, items=[unknown])
    result = lower_piecewise_program(program)
    assert result.program.items == [unknown]

    boolish_abs = ast.FuncCall(span=span, name="abs", args=[one])
    bad_constraint_problem = ast.ProblemDef(
        span=span,
        name="P",
        stmts=[
            ast.Constraint(
                span=span,
                kind=ast.ConstraintKind.MUST,
                expr=boolish_abs,  # type: ignore[arg-type]
            )
        ],
    )
    bad_result = lower_piecewise_program(ast.Program(span=span, items=[bad_constraint_problem]))
    assert any(d.code == "QSOL3101" for d in bad_result.diagnostics)


def test_bound_analyzer_private_branches() -> None:
    span = _span()
    problem = ast.ProblemDef(
        span=span,
        name="P",
        stmts=[
            ast.ParamDecl(
                span=span,
                name="Flag",
                indices=[],
                value_type=ast.ScalarTypeRef(span=span, kind="Bool"),
                default=None,
            ),
            ast.ParamDecl(
                span=span,
                name="Limit",
                indices=[],
                value_type=ast.ScalarTypeRef(span=span, kind="Int", lo=2, hi=7),
                default=None,
            ),
        ],
    )
    analyzer = _BoundAnalyzer(problem)

    assert analyzer.num_bounds(ast.NameRef(span=span, name="Flag"), {}) is not None
    assert analyzer.num_bounds(ast.NameRef(span=span, name="Limit"), {}) is not None
    assert (
        analyzer.num_bounds(
            ast.MethodCall(span=span, target=ast.NameRef(span=span, name="S"), name="has", args=[]),
            {},
        )
        is not None
    )
    assert (
        analyzer.num_bounds(
            ast.FuncCall(span=span, name="indicator", args=[ast.BoolLit(span=span, value=True)]), {}
        )
        is not None
    )
    assert (
        analyzer.num_bounds(
            ast.FuncCall(span=span, name="size", args=[ast.NameRef(span=span, name="A")]), {}
        )
        is not None
    )
    assert (
        analyzer.num_bounds(
            ast.FuncCall(span=span, name="abs", args=[ast.NameRef(span=span, name="Limit")]), {}
        )
        is not None
    )
