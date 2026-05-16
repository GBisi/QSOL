from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source
from qsol.lower import ir


def test_guard_desugars_to_implies() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must S.has(x) if true;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="lower.qsol"))
    assert unit.lowered_ir_symbolic is not None
    prob = unit.lowered_ir_symbolic.problems[0]
    assert isinstance(prob.constraints[0].expr, ir.KImplies)


def test_sum_desugars_to_sum() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must sum(1 for x in A) <= 5;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="sum.qsol"))
    assert unit.lowered_ir_symbolic is not None
    # Compare op is <=, right is 5.
    # left is sum
    expr = unit.lowered_ir_symbolic.problems[0].constraints[0].expr
    assert isinstance(expr, ir.KCompare)
    left = expr.left
    assert isinstance(left, ir.KSum)
    assert isinstance(left.comp.term, ir.KNumLit)
    assert left.comp.term.value == 1.0


def test_minimize_abs_lowers_to_aux_find_and_constraints() -> None:
    text = """
problem P {
  find Balance : Int[-10 .. 10];
  minimize abs(Balance);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="abs_lower.qsol"))
    assert unit.lowered_ir_symbolic is not None
    assert not any(d.is_error for d in unit.diagnostics)
    prob = unit.lowered_ir_symbolic.problems[0]

    aux = [find for find in prob.finds if find.name.startswith("__qsol_piecewise_abs_")]
    assert len(aux) == 1
    assert isinstance(aux[0].decision_type, ir.KIntDecisionType)
    assert len(prob.constraints) == 2
    assert isinstance(prob.objectives[0].expr, ir.KName)
    assert prob.objectives[0].expr.name == aux[0].name


def test_minimize_max_aggregate_lowers_to_aux_find_and_forall_constraints() -> None:
    text = """
problem P {
  set Machines;
  find Load[Machines] : Int[0 .. 10];
  minimize max(Load[m] for m in Machines);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="max_lower.qsol"))
    assert unit.lowered_ir_symbolic is not None
    assert not any(d.is_error for d in unit.diagnostics)
    prob = unit.lowered_ir_symbolic.problems[0]

    aux = [find for find in prob.finds if find.name.startswith("__qsol_piecewise_max_")]
    assert len(aux) == 1
    assert len(prob.constraints) == 1
    assert isinstance(prob.constraints[0].expr, ir.KQuantifier)
    assert isinstance(prob.objectives[0].expr, ir.KName)
    assert prob.objectives[0].expr.name == aux[0].name
