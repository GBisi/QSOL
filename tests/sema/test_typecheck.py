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


def test_scalar_numeric_param_bare_name_is_numeric() -> None:
    text = """
problem P {
  set A;
  param C : Real;
  find S : Subset(A);
  must true;
  minimize C;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="scalar_numeric_bare.qsol"))
    assert not any(
        d.code == "QSOL2101" and "objective expression must be numeric" in d.message
        for d in unit.diagnostics
    )


def test_scalar_bool_param_bare_name_in_constraint() -> None:
    text = """
problem P {
  param Flag : Bool;
  must Flag;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="scalar_bool_bare.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_scalar_param_call_forms_are_rejected() -> None:
    numeric_text = """
problem P {
  set A;
  param C : Real;
  find S : Subset(A);
  must true;
  minimize C[];
}
"""
    bool_text = """
problem P {
  param Flag : Bool;
  must Flag();
}
"""
    numeric_unit = compile_source(
        numeric_text, options=CompileOptions(filename="scalar_numeric_call_reject.qsol")
    )
    bool_unit = compile_source(
        bool_text, options=CompileOptions(filename="scalar_bool_call_reject.qsol")
    )

    assert any(
        d.code == "QSOL2101"
        and "scalar param `C` must be referenced as `C` (bare name)" in d.message
        for d in numeric_unit.diagnostics
    )
    assert any(
        d.code == "QSOL2101"
        and "scalar param `Flag` must be referenced as `Flag` (bare name)" in d.message
        for d in bool_unit.diagnostics
    )


def test_indexed_param_parentheses_call_is_rejected() -> None:
    text = """
problem P {
  set A;
  param Cost[A] : Real;
  find S : Subset(A);
  minimize sum(if S.has(x) then Cost(x) else 0 for x in A);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="indexed_param_paren_reject.qsol"))
    assert any(
        d.code == "QSOL2101" and "indexed param `Cost` must use bracket access" in d.message
        for d in unit.diagnostics
    )


def test_relation_fields_and_membership_typecheck() -> None:
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  must forall u in V: forall v in V: Edge(u, v) or not Edge(v, u);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="relation_ok.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_relation_membership_rejects_wrong_arity() -> None:
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  must forall u in V: Edge(u);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="relation_arity.qsol"))
    assert any(
        d.code == "QSOL2101" and "relation `Edge` expects 2 argument(s)" in d.message
        for d in unit.diagnostics
    )


def test_relation_membership_rejects_wrong_argument_set() -> None:
    text = """
problem P {
  set A;
  set B;
  relation Edge(u: A, v: A);
  must forall a in A: forall b in B: Edge(a, b);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="relation_arg_set.qsol"))
    assert any(
        d.code == "QSOL2101" and "expected element of `A`" in d.message for d in unit.diagnostics
    )


def test_relation_tuple_binder_types_body() -> None:
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  must all(not (Pick.has(u) and Pick.has(v)) for (u, v) in Edge);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="relation_tuple_binder.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_relation_declaration_rejects_unknown_set_and_duplicate_fields() -> None:
    text = """
problem P {
  set V;
  relation Edge(u: V, u: Missing);
  must true;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="relation_decl_bad.qsol"))
    messages = [d.message for d in unit.diagnostics]
    assert any("redefinition of `u`" in msg for msg in messages)
    assert any("unknown set `Missing` in relation `Edge`" in msg for msg in messages)


def test_relation_tuple_binder_rejects_wrong_arity() -> None:
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  must forall (u, v, w) in Edge: true;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="relation_tuple_bad.qsol"))
    assert any(
        d.code == "QSOL2101" and "tuple binder expects 2 variable(s)" in d.message
        for d in unit.diagnostics
    )


def test_derived_relation_rejects_decision_dependent_filter() -> None:
    text = """
problem BadDerived {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  relation PickedEdge(u: V, v: V) = filter((u, v) in Edge where Pick.has(u));
}
"""
    unit = compile_source(text, options=CompileOptions(filename="derived_decision.qsol"))

    assert any(
        d.code == "QSOL2101"
        and "derived relation condition must be scenario-time static" in d.message
        for d in unit.diagnostics
    )


def test_derived_relation_rejects_dependency_cycle() -> None:
    text = """
problem Cycle {
  set V;
  relation A(u: V, v: V) = filter((u, v) in B where true);
  relation B(u: V, v: V) = filter((u, v) in A where true);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="derived_cycle.qsol"))

    assert any(
        d.code == "QSOL2101" and "derived relation dependency cycle" in d.message
        for d in unit.diagnostics
    )


def test_unknown_function_or_predicate_call_is_rejected_after_macro_pass() -> None:
    text = """
problem P {
  must missing_macro(true);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="unknown_macro_call.qsol"))
    assert any(
        d.code == "QSOL2101" and "unknown function/predicate `missing_macro`" in d.message
        for d in unit.diagnostics
    )


def test_bool_if_else_returns_bool() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must forall x in A: if S.has(x) then true else false;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="bool_if_else.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_bool_if_else_in_constraint_with_logic() -> None:
    text = """
problem P {
  set A;
  param Flag : Bool;
  find S : Subset(A);
  must forall x in A: if Flag then S.has(x) else not S.has(x);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="bool_if_else_logic.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_range_binder_supports_arithmetic_but_opaque_binder_rejects_it() -> None:
    range_text = """
problem P {
  set V;
  set Positions = Range(1, size(V));
  must forall p in Positions: p + 1 <= size(V) + 1;
}
"""
    opaque_text = """
problem P {
  set V;
  must forall v in V: v + 1 <= size(V) + 1;
}
"""
    range_unit = compile_source(range_text, options=CompileOptions(filename="range_math.qsol"))
    opaque_unit = compile_source(opaque_text, options=CompileOptions(filename="opaque_math.qsol"))

    assert not any(d.is_error for d in range_unit.diagnostics)
    assert any(
        d.code == "QSOL2101" and "arithmetic requires numeric operands" in d.message
        for d in opaque_unit.diagnostics
    )


def test_scalar_decisions_typecheck_in_bool_numeric_and_indexed_contexts() -> None:
    text = """
problem P {
  set Machines;
  param Total : Int[0 .. 100];
  find enabled : Bool;
  find T : Int[0 .. Total];
  find Load[Machines] : Int[0 .. Total];

  must enabled;
  must forall m in Machines: Load[m] <= T;
  minimize T + sum(Load[m] for m in Machines);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="scalar_decisions.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_unknown_dependent_int_bounds_are_rejected() -> None:
    text = """
problem P {
  set V;
  find Chosen : Subset(V);
  find T : Int[0 .. size(Chosen)];
  minimize T;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="unknown_bound_bad.qsol"))
    assert any(
        d.code == "QSOL2101" and "size() expects a declared set identifier" in d.message
        for d in unit.diagnostics
    )
