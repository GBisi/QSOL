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


def test_static_subset_param_typechecks_as_static_domain() -> None:
    text = """
problem P {
  set V;
  param Terminals : StaticSubset(V);
  find Pick : Subset(V);

  must forall t in Terminals: Pick.has(t);
  minimize size(Terminals);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="static_subset.qsol"))

    assert not any(d.is_error for d in unit.diagnostics)


def test_static_subset_param_rejects_unknown_parent_set_and_indexing() -> None:
    text = """
problem P {
  set V;
  param Bad[V] : StaticSubset(Missing);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="static_subset_bad_decl.qsol"))

    assert any(
        d.code == "QSOL2201" and "StaticSubset params cannot be indexed" in d.message
        for d in unit.diagnostics
    )
    assert any(
        d.code == "QSOL2201" and "unknown set `Missing` in param value type" in d.message
        for d in unit.diagnostics
    )


def test_static_subset_has_validates_arity_and_element_type() -> None:
    arity_text = """
problem P {
  set V;
  param Terminals : StaticSubset(V);
  must Terminals.has();
}
"""
    arity_unit = compile_source(
        arity_text, options=CompileOptions(filename="static_subset_has_arity.qsol")
    )
    assert any("StaticSubset.has expects one argument" in d.message for d in arity_unit.diagnostics)

    type_text = """
problem P {
  set V;
  set Other;
  param Terminals : StaticSubset(V);
  must forall x in Other: Terminals.has(x);
}
"""
    type_unit = compile_source(
        type_text, options=CompileOptions(filename="static_subset_has_type.qsol")
    )
    assert any("expected element of `V`" in d.message for d in type_unit.diagnostics)


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
        d.code == "QSOL2101" and "size() expects a declared set or relation identifier" in d.message
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
        d.code == "QSOL2101" and "size() expects a declared set or relation identifier" in d.message
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


def test_piecewise_builtins_accept_numeric_arguments() -> None:
    text = """
problem P {
  set Machines;
  find Balance : Int[-10 .. 10];
  find Load[Machines] : Int[0 .. 10];
  must abs(Balance) <= 5;
  minimize max(Load[m] for m in Machines) + min(Balance, 3);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="piecewise_ok.qsol"))
    assert not any(
        d.code == "QSOL2101"
        and ("abs()" in d.message or "min()" in d.message or "max()" in d.message)
        for d in unit.diagnostics
    )


def test_piecewise_builtins_reject_bool_arguments() -> None:
    text = """
problem P {
  set Machines;
  find Enabled : Bool;
  find Load[Machines] : Int[0 .. 10];
  must abs(Enabled) <= 1;
  minimize max(Enabled for m in Machines);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="piecewise_bad.qsol"))
    messages = [d.message for d in unit.diagnostics if d.code == "QSOL2101"]
    assert any("abs() argument must be numeric" in message for message in messages)
    assert any("max() aggregate term must be numeric" in message for message in messages)


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


def test_duplicate_objective_labels_are_rejected() -> None:
    text = """
problem P {
  set V;
  find Pick : Subset(V);
  minimize count(v in V where Pick.has(v)) as score;
  maximize count(v in V where not Pick.has(v)) as score;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="duplicate_objective_label.qsol"))

    assert any(
        d.code == "QSOL2101" and "duplicate objective label `score`" in d.message
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


def test_undirected_graph_structure_types_domains_and_methods() -> None:
    text = """
use stdlib.graph;

problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find Selected[G.edges] : Bool;
  must forall (u, v) in G.non_edges: not Selected[u, v];
  must forall u in G.vertices: forall v in G.vertices: G.adjacent(u, v) or G.nonedge(u, v);
  minimize size(G.edges) + size(G.non_edges);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="graph_structure_sema.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_matching_unknown_requires_graph_structure() -> None:
    valid_text = """
use stdlib.graph;

problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find M : Matching(G);
  must forall (u, v) in G.edges: M.has_edge(u, v) or not M.has_edge(u, v);
}
"""
    valid_unit = compile_source(valid_text, options=CompileOptions(filename="matching_ok.qsol"))
    assert not any(d.is_error for d in valid_unit.diagnostics)

    wrong_arg_text = """
use stdlib.graph;

problem P {
  set V;
  find M : Matching(V);
}
"""
    wrong_arg_unit = compile_source(
        wrong_arg_text, options=CompileOptions(filename="matching_bad_arg.qsol")
    )
    assert any(
        d.code == "QSOL2001"
        and "Matching expects an UndirectedGraph structure argument" in d.message
        for d in wrong_arg_unit.diagnostics
    )

    wrong_method_text = """
use stdlib.graph;

problem P {
  set V;
  set W;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find M : Matching(G);
  must forall u in V: forall w in W: M.has_edge(u, w);
}
"""
    wrong_method_unit = compile_source(
        wrong_method_text, options=CompileOptions(filename="matching_bad_method.qsol")
    )
    assert any(
        d.code == "QSOL2101" and "expected element of `V`" in d.message
        for d in wrong_method_unit.diagnostics
    )


def test_maximal_matching_unknown_uses_matching_graph_contract() -> None:
    valid_text = """
use stdlib.graph;

problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find M : MaximalMatching(G);
  must forall (u, v) in G.edges: M.has_edge(u, v) or not M.has_edge(u, v);
}
"""
    valid_unit = compile_source(
        valid_text, options=CompileOptions(filename="maximal_matching_ok.qsol")
    )
    assert not any(d.is_error for d in valid_unit.diagnostics)

    wrong_arg_text = """
use stdlib.graph;

problem P {
  set V;
  find M : MaximalMatching(V);
}
"""
    wrong_arg_unit = compile_source(
        wrong_arg_text, options=CompileOptions(filename="maximal_matching_bad_arg.qsol")
    )
    assert any(
        d.code == "QSOL2001"
        and "MaximalMatching expects an UndirectedGraph structure argument" in d.message
        for d in wrong_arg_unit.diagnostics
    )


def test_tree_graph_unknowns_use_matching_graph_contract() -> None:
    for unknown_name in ("SpanningTree", "Forest"):
        valid_text = f"""
use stdlib.graph;

problem P {{
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find T : {unknown_name}(G);
  must forall (u, v) in G.edges: T.has_edge(u, v) or not T.has_edge(u, v);
}}
"""
        valid_unit = compile_source(
            valid_text, options=CompileOptions(filename=f"{unknown_name}_ok.qsol")
        )
        assert not any(d.is_error for d in valid_unit.diagnostics)

        wrong_arg_text = f"""
use stdlib.graph;

problem P {{
  set V;
  find T : {unknown_name}(V);
}}
"""
        wrong_arg_unit = compile_source(
            wrong_arg_text, options=CompileOptions(filename=f"{unknown_name}_bad_arg.qsol")
        )
        assert any(
            d.code == "QSOL2001"
            and f"{unknown_name} expects an UndirectedGraph structure argument" in d.message
            for d in wrong_arg_unit.diagnostics
        )


def test_steiner_tree_unknown_requires_graph_and_static_subset() -> None:
    valid_text = """
use stdlib.graph;

problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  param Terminals : StaticSubset(V);
  find T : SteinerTree(G, Terminals);
  must forall (u, v) in G.edges: T.has_edge(u, v) or not T.has_edge(u, v);
  must forall v in G.vertices: T.has_vertex(v) or not T.has_vertex(v);
}
"""
    valid_unit = compile_source(valid_text, options=CompileOptions(filename="steiner_ok.qsol"))
    assert not any(d.is_error for d in valid_unit.diagnostics)

    wrong_subset_text = """
use stdlib.graph;

problem P {
  set V;
  set W;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  param Terminals : StaticSubset(W);
  find T : SteinerTree(G, Terminals);
}
"""
    wrong_subset_unit = compile_source(
        wrong_subset_text, options=CompileOptions(filename="steiner_bad_subset.qsol")
    )
    assert any(
        d.code == "QSOL2001"
        and "SteinerTree expects a StaticSubset whose parent set matches" in d.message
        for d in wrong_subset_unit.diagnostics
    )


def test_hamiltonian_graph_unknowns_type_views() -> None:
    valid_text = """
use stdlib.graph;

problem P {
  set V;
  set Pos = Range(1, size(V));
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find Pth : HamiltonianPath(G);
  find Cyc : HamiltonianCycle(G);
  must forall p in Pos: forall v in G.vertices: Pth.at(p, v) or not Pth.at(p, v);
  must forall (u, v) in G.edges: Cyc.uses(u, v) or not Cyc.uses(u, v);
}
"""
    valid_unit = compile_source(
        valid_text, options=CompileOptions(filename="hamiltonian_views_ok.qsol")
    )
    assert not any(d.is_error for d in valid_unit.diagnostics)

    wrong_arg_text = """
use stdlib.graph;

problem P {
  set V;
  find H : HamiltonianPath(V);
}
"""
    wrong_arg_unit = compile_source(
        wrong_arg_text, options=CompileOptions(filename="hamiltonian_bad_arg.qsol")
    )
    assert any(
        d.code == "QSOL2001"
        and "HamiltonianPath expects an UndirectedGraph structure argument" in d.message
        for d in wrong_arg_unit.diagnostics
    )


def test_graph_structure_rejects_wrong_relation_shape() -> None:
    ternary_text = """
problem P {
  set V;
  relation Edge(u: V, v: V, w: V);
  structure G = UndirectedGraph(V, Edge);
}
"""
    wrong_set_text = """
problem P {
  set V;
  set W;
  relation Edge(u: V, w: W);
  structure G = UndirectedGraph(V, Edge);
}
"""
    ternary_unit = compile_source(
        ternary_text, options=CompileOptions(filename="graph_ternary_bad.qsol")
    )
    wrong_set_unit = compile_source(
        wrong_set_text, options=CompileOptions(filename="graph_field_set_bad.qsol")
    )

    assert any(
        d.code == "QSOL2101" and "expects a binary relation over `V x V`" in d.message
        for d in ternary_unit.diagnostics
    )
    assert any(
        d.code == "QSOL2101" and "expects a binary relation over `V x V`" in d.message
        for d in wrong_set_unit.diagnostics
    )


def test_graph_structure_rejects_unknown_constructor_and_wrong_arity() -> None:
    unknown_text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = HyperGraph(V, Edge);
}
"""
    arity_text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V);
}
"""
    unknown_unit = compile_source(
        unknown_text, options=CompileOptions(filename="graph_unknown_ctor.qsol")
    )
    arity_unit = compile_source(arity_text, options=CompileOptions(filename="graph_arity.qsol"))

    assert any(
        d.code == "QSOL2101" and "unknown structure constructor `HyperGraph`" in d.message
        for d in unknown_unit.diagnostics
    )
    assert any(
        d.code == "QSOL2101" and "UndirectedGraph expects 2 argument(s)" in d.message
        for d in arity_unit.diagnostics
    )


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


def test_static_aggregate_int_bounds_typecheck() -> None:
    text = """
problem P {
  set Jobs;
  relation Arc(u: Jobs, v: Jobs);
  param Length[Jobs] : Int[0 .. 100];
  param Cost[Jobs, Jobs] : Int[0 .. 100] = 1;
  find Makespan : Int[0 .. sum(Length[j] for j in Jobs)];
  find Flow[Arc] : Int[0 .. size(Arc)];
  find SelectedCount : Int[0 .. count((u, v) in Arc where Cost[u, v] > 0)];
  minimize Makespan + SelectedCount + sum(Flow[u, v] for (u, v) in Arc);
}
"""
    unit = compile_source(text, options=CompileOptions(filename="static_aggregate_bounds.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_static_if_and_boolean_aggregate_int_bounds_typecheck() -> None:
    text = """
problem P {
  set Jobs;
  relation Arc(u: Jobs, v: Jobs);
  param Length[Jobs] : Int[0 .. 100];
  param Active[Jobs] : Bool = true;
  param Cost[Jobs, Jobs] : Int[0 .. 100] = 1;
  find ConditionalTotal : Int[
    0 ..
    if any(Active[j] = Active[j] for j in Jobs)
    then sum(Length[j] for j in Jobs)
    else 0
  ];
  find RelationChecked : Int[
    0 ..
    if forall (u, v) in Arc: Cost[u, v] >= 0
    then size(Arc)
    else 0
  ];
  minimize ConditionalTotal + RelationChecked;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="static_if_bounds.qsol"))
    assert not any(d.is_error for d in unit.diagnostics)


def test_range_bounds_do_not_accept_aggregate_expressions() -> None:
    text = """
problem P {
  set Jobs;
  param Length[Jobs] : Int[0 .. 100];
  set Positions = Range(1, sum(Length[j] for j in Jobs));
  minimize 0;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="range_aggregate_bad.qsol"))
    assert any(
        d.code == "QSOL2101"
        and "integer bounds may use literals, scalar params, size(Set), and arithmetic only"
        in d.message
        for d in unit.diagnostics
    )


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
        d.code == "QSOL2101" and "size() expects a declared set or relation identifier" in d.message
        for d in unit.diagnostics
    )


def test_decision_dependent_aggregate_int_bounds_are_rejected() -> None:
    text = """
problem P {
  set Jobs;
  param Weight[Jobs] : Int[0 .. 100];
  find Pick : Subset(Jobs);
  find T : Int[0 .. sum(if Pick.has(j) then Weight[j] else 0 for j in Jobs)];
  minimize T;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="decision_bound_bad.qsol"))
    assert any(
        d.code == "QSOL2101"
        and "Int upper bound is not scenario-time constant" in d.message
        and "Pick.has" in " ".join(d.notes + d.help)
        for d in unit.diagnostics
    )


def test_decision_name_and_indexed_decision_int_bounds_are_rejected() -> None:
    text = """
problem P {
  set Jobs;
  find Other : Int[0 .. 1];
  find Load[Jobs] : Int[0 .. 1];
  find T : Int[0 .. Other + sum(Load[j] for j in Jobs)];
  find U : Int[0 .. sum(Load[j] for j in Jobs)];
  minimize T + U;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="decision_name_bound_bad.qsol"))
    messages = [*unit.diagnostics]
    assert any(
        d.code == "QSOL2101"
        and "Int upper bound is not scenario-time constant" in d.message
        and "decision `Other`" in " ".join(d.notes)
        for d in messages
    )
    assert any(
        d.code == "QSOL2101"
        and "Int upper bound is not scenario-time constant" in d.message
        and "decision `Load`" in " ".join(d.notes)
        for d in messages
    )


def test_unknown_relation_aggregate_int_bound_is_rejected() -> None:
    text = """
problem P {
  set Jobs;
  find T : Int[0 .. count((u, v) in Missing)];
  minimize T;
}
"""
    unit = compile_source(text, options=CompileOptions(filename="missing_relation_bound_bad.qsol"))
    assert any(
        d.code == "QSOL2101"
        and "Int upper bound is not scenario-time constant" in d.message
        and "unknown relation `Missing`" in " ".join(d.notes)
        for d in unit.diagnostics
    )
