from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source


def test_method_type_mismatch() -> None:
    text = """
problem P {
  set A;
  set B;
  find S : Subset(A);
  must forall x in B: S.has(x);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="sem.qsol"))
    codes = [d.code for d in unit.diagnostics]
    assert "QSOL2101" in codes


def test_unknown_param_index_set() -> None:
    text = """
problem P {
  param p[Missing] : Real;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="param.qsol"))
    codes = [d.code for d in unit.diagnostics]
    assert "QSOL2201" in codes
