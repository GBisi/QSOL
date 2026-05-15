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
