from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source


def test_shorthand_guard_hint() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must S.has(x) if true for x in A;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="golden.qsol"))
    assert unit.diagnostics
    rendered_help = "\n".join(h for d in unit.diagnostics for h in d.help)
    assert "trailing `for`" in rendered_help
