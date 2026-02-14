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


def test_elem_param_unknown_set_target() -> None:
    text = """
problem P {
  set E;
  param U[E] : Elem(V);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="elem_unknown.qsol"))
    codes = [d.code for d in unit.diagnostics]
    assert "QSOL2201" in codes


def test_elem_param_default_is_rejected() -> None:
    text = """
problem P {
  set V;
  set E;
  param U[E] : Elem(V) = "v1";
}
"""
    unit = compile_source(text, options=CompileOptions(filename="elem_default.qsol"))
    messages = [d.message for d in unit.diagnostics]
    assert any("set-valued params do not support defaults" in msg for msg in messages)


def test_elem_param_equality_same_set_is_allowed() -> None:
    text = """
problem P {
  set V;
  set E;
  param U[E] : Elem(V);
  param W[E] : Elem(V);
  must forall e in E: U[e] = W[e];
}
"""
    unit = compile_source(text, options=CompileOptions(filename="elem_eq_ok.qsol"))
    messages = [d.message for d in unit.diagnostics]
    assert all(
        "matching Bool, numeric, or same-set element operands" not in msg for msg in messages
    )


def test_elem_param_equality_cross_set_fails() -> None:
    text = """
problem P {
  set A;
  set B;
  param X[A] : Elem(A);
  param Y[A] : Elem(B);
  must forall a in A: X[a] = Y[a];
}
"""
    unit = compile_source(text, options=CompileOptions(filename="elem_eq_bad.qsol"))
    messages = [d.message for d in unit.diagnostics]
    assert any("matching Bool, numeric, or same-set element operands" in msg for msg in messages)


def test_size_builtin_accepts_declared_set_identifier() -> None:
    text = """
problem P {
  set V;
  must size(V) >= 0;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="size_ok.qsol"))
    assert not any("size()" in d.message for d in unit.diagnostics if d.code == "QSOL2101")


def test_size_builtin_rejects_unknown_identifier() -> None:
    text = """
problem P {
  set V;
  must size(Unknown) > 0;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="size_unknown.qsol"))
    assert any(
        d.code == "QSOL2101" and "size() expects a declared set identifier" in d.message
        for d in unit.diagnostics
    )


def test_size_builtin_rejects_param_identifier() -> None:
    text = """
problem P {
  set V;
  param paramX : Real;
  must size(paramX) > 0;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="size_param.qsol"))
    assert any(
        d.code == "QSOL2101" and "size() expects a declared set identifier" in d.message
        for d in unit.diagnostics
    )


def test_size_builtin_rejects_wrong_arity() -> None:
    text = """
problem P {
  set V;
  set W;
  must size(V, W) > 0;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="size_arity.qsol"))
    assert any(
        d.code == "QSOL2101" and "size() expects exactly one argument" in d.message
        for d in unit.diagnostics
    )
