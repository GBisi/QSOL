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


def test_any_becomes_quantifier() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must any(S.has(x) for x in A);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="any.qsol"))
    assert unit.lowered_ir_symbolic is not None
    expr = unit.lowered_ir_symbolic.problems[0].constraints[0].expr
    assert isinstance(expr, ir.KQuantifier)
    assert expr.kind == "exists"
