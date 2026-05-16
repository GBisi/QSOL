import tomllib
from pathlib import Path

import dimod

from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source


def test_compile_emits_artifacts(tmp_path: Path) -> None:
    source = """
problem Simple {
  set A;
  find S : Subset(A);
  must sum(if not S.has(x) then 1 else 0 for x in A) == 0;
  minimize sum( if S.has(x) then 1 else 0 for x in A );
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "Simple"

[scenarios.baseline.sets]
A = ["a1", "a2"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="simple.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()
    assert Path(unit.artifacts.format_path or "").exists()
    assert Path(unit.artifacts.varmap_path or "").exists()


def test_compile_supports_indexed_numeric_param_default_and_calls(tmp_path: Path) -> None:
    source = """
problem LinkedCut {
  set V;
  param LinkWeight[V,V] : Real = 1;

  find Left : Subset(V);

  maximize sum(sum(if Left.has(u) then if Left.has(v) then 0 else LinkWeight[u, v] else if Left.has(v) then LinkWeight[u, v] else 0 for v in V) for u in V) / 2;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "LinkedCut"

[scenarios.baseline.sets]
V = ["v1", "v2", "v3"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="linked_cut.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()

    weighted_instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "LinkedCut"

[scenarios.baseline.sets]
V = ["v1", "v2", "v3"]

[scenarios.baseline.params.LinkWeight]
v1 = { v1 = 0, v2 = 2, v3 = 0 }
v2 = { v1 = 2, v2 = 0, v3 = 3 }
v3 = { v1 = 0, v2 = 3, v3 = 0 }
""".lstrip()
    )
    weighted_outdir = tmp_path / "out-weighted"
    weighted_unit = compile_source(
        source,
        options=CompileOptions(
            filename="linked_cut.qsol",
            instance_payload=weighted_instance_payload["scenarios"]["baseline"],
            outdir=str(weighted_outdir),
            output_format="qubo",
        ),
    )

    assert weighted_unit.artifacts is not None
    assert Path(weighted_unit.artifacts.cqm_path or "").exists()
    assert Path(weighted_unit.artifacts.bqm_path or "").exists()


def test_compile_supports_static_relation_iteration_and_membership(tmp_path: Path) -> None:
    source = """
problem IndependentSet {
  set V;
  relation Edge(u: V, v: V);

  find Pick : Subset(V);

  must all(Edge(u, v) for (u, v) in Edge);
  must forall u in V: forall v in V: Edge(u, v) => Edge(v, u);
  maximize count(v in V where Pick.has(v));
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "IndependentSet"

[scenarios.baseline.sets]
V = ["a", "b", "c"]

[scenarios.baseline.relations]
Edge = [
  { u = "a", v = "b" },
  { u = "b", v = "a" },
  { u = "b", v = "c" },
  { u = "c", v = "b" },
]
""".lstrip()
    )

    outdir = tmp_path / "out-rel"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="independent_set.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(d.is_error for d in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_lowers_all_different_global_for_indexed_ints(tmp_path: Path) -> None:
    source = """
problem AssignDistinct {
  set Items;
  set Slots = Range(1, size(Items));

  find Slot[Items] : Int[0 .. size(Items) - 1];

  must all_different(Slot[i] for i in Items);
  minimize sum(Slot[i] for i in Items);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "AssignDistinct"

[scenarios.baseline.sets]
Items = ["a", "b", "c"]
""".lstrip()
    )

    outdir = tmp_path / "out-all-different"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="all_different.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="cqm",
        ),
    )

    assert not [d for d in unit.diagnostics if d.is_error]
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_compile_lowers_graph_adjacency_helpers(tmp_path: Path) -> None:
    source = """
use stdlib.graph;

problem GraphHelpers {
  set V;
  relation Edge(u: V, v: V);

  minimize sum(if adjacent(Edge, u, v) then 1 else 0 for u in V for v in V);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "GraphHelpers"

[scenarios.baseline.sets]
V = ["a", "b", "c"]

[scenarios.baseline.relations]
Edge = [
  { u = "a", v = "b" },
  { u = "b", v = "c" },
]
""".lstrip()
    )

    outdir = tmp_path / "out-graph-helpers"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="graph_helpers.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not [d for d in unit.diagnostics if d.is_error]
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_compile_supports_route_stdlib_unknown(tmp_path: Path) -> None:
    source = """
use stdlib.route;

problem TinyRoute {
  set Positions;
  set V;

  find Tour : Route(Positions, V);

  must forall p in Positions: exists v in V: Tour.at(p, v);
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "TinyRoute"

[scenarios.baseline.sets]
Positions = ["p1", "p2"]
V = ["a", "b"]
""".lstrip()
    )

    outdir = tmp_path / "out-route"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="route.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not [d for d in unit.diagnostics if d.is_error]
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_compile_supports_tuple_relation_count_objective(tmp_path: Path) -> None:
    source = """
problem ReciprocalEdges {
  set V;
  relation Edge(u: V, v: V);

  minimize count((u, v) in Edge where Edge(v, u));
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "ReciprocalEdges"

[scenarios.baseline.sets]
V = ["a", "b", "c"]

[scenarios.baseline.relations]
Edge = [["a", "b"], ["b", "a"], ["b", "c"]]
""".lstrip()
    )

    outdir = tmp_path / "out-rel-count"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="reciprocal_edges.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(d.is_error for d in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_compile_supports_derived_nonedge_relation(tmp_path: Path) -> None:
    source = """
use stdlib.logic;

problem MaxClique {
  set V;
  relation Edge(u: V, v: V);
  relation NonEdge(u: V, v: V) = pairs(u in V, v in V where u != v and not Edge(u, v));

  find Pick : Subset(V);

  must forall (u, v) in NonEdge: indicator(Pick.has(u)) + indicator(Pick.has(v)) <= 1;
  maximize count(v in V where Pick.has(v));
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "MaxClique"

[scenarios.baseline.sets]
V = ["a", "b", "c"]

[scenarios.baseline.relations]
Edge = [["a", "b"], ["b", "a"], ["b", "c"], ["c", "b"]]
""".lstrip()
    )

    outdir = tmp_path / "out-derived-nonedge"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="max_clique.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(d.is_error for d in unit.diagnostics)
    assert unit.ground_ir is not None
    problem = unit.ground_ir.problems[0]
    assert problem.relation_values["NonEdge"] == (("a", "c"), ("c", "a"))
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_compile_supports_derived_filter_and_param_conditions(tmp_path: Path) -> None:
    source = """
problem DerivedConditions {
  set V;
  relation Edge(u: V, v: V);
  param Flag : Bool = true;
  param Weight[V] : Int[0 .. 10];
  param Bias : Int[0 .. 10] = 1;

  relation Reciprocal(u: V, v: V) = filter((u, v) in Edge where Edge(v, u));
  relation Candidate(u: V, v: V) =
    pairs(u in V, v in V where Flag and Weight[u] + Bias >= Weight[v]);

  minimize count((u, v) in Reciprocal) + count((u, v) in Candidate);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "DerivedConditions"

[scenarios.baseline.sets]
V = ["a", "b", "c"]

[scenarios.baseline.params.Weight]
a = 1
b = 2
c = 8

[scenarios.baseline.relations]
Edge = [["a", "b"], ["b", "a"], ["b", "c"]]
""".lstrip()
    )

    outdir = tmp_path / "out-derived-conditions"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="derived_conditions.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(d.is_error for d in unit.diagnostics)
    assert unit.ground_ir is not None
    problem = unit.ground_ir.problems[0]
    assert problem.relation_values["Reciprocal"] == (("a", "b"), ("b", "a"))
    assert problem.derived_relations == {"Candidate": "pairs", "Reciprocal": "filter"}
    assert ("a", "b") in problem.relation_values["Candidate"]
    assert ("a", "c") not in problem.relation_values["Candidate"]


def test_compile_supports_model_vs_model_equality_without_objective(tmp_path: Path) -> None:
    source = """
problem PartitionEqualSum {
  set Items;
  param Value[Items] : Int[1 .. 1000000000];
  find R : Subset(Items);

  must
    sum(if R.has(i) then Value[i] else 0 for i in Items)
    =
    sum(if not R.has(i) then Value[i] else 0 for i in Items);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "PartitionEqualSum"

[scenarios.baseline.sets]
Items = ["a", "b", "c", "d"]

[scenarios.baseline.params.Value]
a = 1
b = 2
c = 3
d = 4
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="partition_equal_sum.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_elem_params_and_compare_in_objective_if(tmp_path: Path) -> None:
    source = """
problem MinBisection {
  set V;
  set E;
  param U[E] : Elem(V);
  param W[E] : Elem(V);
  param Half : Int[0 .. 1000000];
  find A : Subset(V);

  must sum(if A.has(v) then 1 else 0 for v in V) = Half;

  minimize sum(
    if A.has(U[e]) != A.has(W[e]) then 1 else 0
    for e in E
  );
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "MinBisection"

[scenarios.baseline.sets]
V = [0, 1, 2, 3]
E = ["e0", "e1", "e2"]

[scenarios.baseline.params.U]
e0 = 0
e1 = 1
e2 = 2

[scenarios.baseline.params.W]
e0 = 1
e1 = 2
e2 = 3

[scenarios.baseline.params]
Half = 2
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="min_bisection.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_min_bisection_boolean_objective_avoids_internal_variables(tmp_path: Path) -> None:
    source = """
problem MinBisection {
  set V;
  set E;
  param U[E] : Elem(V);
  param W[E] : Elem(V);
  find Side : Subset(V);

  must sum(if Side.has(v) then 2 else 0 for v in V) = size(V);

  minimize sum(
    if Side.has(U[e]) or Side.has(W[e])
    then 1 else 0
    for e in E
  );
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "MinBisection"

[scenarios.baseline.sets]
V = ["v1", "v2", "v3", "v4"]
E = ["e1", "e2", "e3"]

[scenarios.baseline.params.U]
e1 = "v1"
e2 = "v2"
e3 = "v3"

[scenarios.baseline.params.W]
e1 = "v2"
e2 = "v3"
e3 = "v4"
""".lstrip()
    )

    outdir = tmp_path / "out"
    scenario_payload = instance_payload["scenarios"]["baseline"]
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="min_bisection_bool_logic.qsol",
            instance_payload=scenario_payload,
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert unit.artifacts is not None
    assert Path(unit.artifacts.bqm_path or "").exists()

    bqm_path = Path(unit.artifacts.bqm_path or "")
    with bqm_path.open("rb") as fp:
        bqm = dimod.BinaryQuadraticModel.from_file(fp)

    variable_labels = [str(var) for var in bqm.variables]
    assert len(variable_labels) == len(scenario_payload["sets"]["V"])
    assert not any(label.startswith("aux:") for label in variable_labels)
    assert not any(label.startswith("slack_") for label in variable_labels)


def test_compile_supports_size_builtin_after_instance_fold(tmp_path: Path) -> None:
    source = """
problem SizeFold {
  set V;
  find S : Subset(V);
  must true;
  minimize size(V);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "SizeFold"

[scenarios.baseline.sets]
V = ["v1", "v2", "v3"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="size_fold.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None


def test_compile_supports_minimize_abs_piecewise_builtin(tmp_path: Path) -> None:
    source = """
problem AbsBalance {
  find Left : Int[0 .. 5];
  find Right : Int[0 .. 5];
  minimize abs(Left - Right);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "AbsBalance"
""".lstrip()
    )

    outdir = tmp_path / "out-abs"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="abs_balance.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(d.is_error for d in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_compile_supports_minimize_max_aggregate_piecewise_builtin(tmp_path: Path) -> None:
    source = """
problem Makespan {
  set Machines;
  find Load[Machines] : Int[0 .. 10];
  minimize max(Load[m] for m in Machines);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "Makespan"

[scenarios.baseline.sets]
Machines = ["m1", "m2"]
""".lstrip()
    )

    outdir = tmp_path / "out-max"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="makespan.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(d.is_error for d in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()


def test_rejects_unsupported_piecewise_objective_context() -> None:
    source = """
problem BadAbs {
  find Left : Int[0 .. 5];
  find Right : Int[0 .. 5];
  maximize abs(Left - Right);
}
"""
    unit = compile_source(source, options=CompileOptions(filename="bad_abs.qsol"))

    assert any(d.code == "QSOL3101" and "maximize abs()" in d.message for d in unit.diagnostics)


def test_compile_supports_bare_scalar_real_and_bool_params(tmp_path: Path) -> None:
    source = """
problem ScalarBare {
  set A;
  param C : Real;
  param Flag : Bool;
  find S : Subset(A);

  must Flag;
  minimize C;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "ScalarBare"

[scenarios.baseline.sets]
A = ["a1", "a2"]

[scenarios.baseline.params]
C = 3.5
Flag = true
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="scalar_bare.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_bare_scalar_elem_param_in_method_arg(tmp_path: Path) -> None:
    source = """
problem ScalarElemArg {
  set V;
  param Start : Elem(V);
  find S : Subset(V);

  must S.has(Start);
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "ScalarElemArg"

[scenarios.baseline.sets]
V = ["v1", "v2"]

[scenarios.baseline.params]
Start = "v1"
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="scalar_elem_arg.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_range_sets_and_scalar_decisions(tmp_path: Path) -> None:
    source = """
problem ScalarDecisions {
  set Machines;
  set Positions = Range(1, size(Machines));
  param Total : Int[0 .. 100];
  find enabled : Bool;
  find T : Int[0 .. Total];
  find Load[Machines] : Int[0 .. Total];

  must enabled;
  must forall p in Positions: p <= size(Machines);
  must forall m in Machines: Load[m] <= T;
  minimize T + sum(Load[m] for m in Machines);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "ScalarDecisions"

[scenarios.baseline.sets]
Machines = ["m1", "m2"]

[scenarios.baseline.params]
Total = 5
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="scalar_decisions.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.ground_ir is not None
    assert unit.ground_ir.problems[0].set_values["Positions"] == [1, 2]
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_static_aggregate_int_bounds(tmp_path: Path) -> None:
    source = """
problem StaticAggregateBounds {
  set Jobs;
  relation Arc(u: Jobs, v: Jobs);
  param Length[Jobs] : Int[0 .. 100];
  param Cost[Jobs, Jobs] : Int[0 .. 100] = 1;
  find Makespan : Int[0 .. sum(Length[j] for j in Jobs)];
  find Flow[Arc] : Int[0 .. size(Arc)];
  find SelectedCount : Int[0 .. count((u, v) in Arc where Cost[u, v] > 0)];

  must Makespan >= SelectedCount;
  minimize Makespan + SelectedCount + sum(Flow[u, v] for (u, v) in Arc);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "StaticAggregateBounds"

[scenarios.baseline.sets]
Jobs = ["a", "b", "c"]

[scenarios.baseline.params]
Length = { a = 2, b = 3, c = 4 }

[scenarios.baseline.relations]
Arc = [
  { u = "a", v = "b" },
  { u = "b", v = "c" },
]
""".lstrip()
    )

    unit = compile_source(
        source,
        options=CompileOptions(
            filename="static_aggregate_bounds.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(tmp_path / "out"),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.ground_ir is not None
    finds = {find.name: find for find in unit.ground_ir.problems[0].finds}
    makespan = finds["Makespan"].decision_type
    flow = finds["Flow"].decision_type
    selected_count = finds["SelectedCount"].decision_type
    assert makespan.hi.value == 9
    assert flow.hi.value == 2
    assert selected_count.hi.value == 2
    assert unit.compiled_model is not None
    cqm = unit.compiled_model.cqm
    assert cqm.upper_bound("Makespan") == 9
    assert cqm.upper_bound("SelectedCount") == 2
    assert cqm.upper_bound("Flow[a,b]") == 2


def test_derived_range_set_rejects_scenario_values(tmp_path: Path) -> None:
    source = """
problem DerivedSet {
  set V;
  set Positions = Range(1, size(V));
  find S : Subset(V);
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "DerivedSet"

[scenarios.baseline.sets]
V = ["v1", "v2"]
Positions = [1, 2]
""".lstrip()
    )

    unit = compile_source(
        source,
        options=CompileOptions(
            filename="derived_set_bad.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(tmp_path / "out"),
            output_format="qubo",
        ),
    )

    assert any(
        diag.code == "QSOL4201" and "must not be supplied" in diag.message
        for diag in unit.diagnostics
    )


def test_compile_supports_hard_not_equal_constraint(tmp_path: Path) -> None:
    source = """
problem HardNotEqual {
  set A;
  find S : Subset(A);
  must sum(if S.has(x) then 1 else 0 for x in A) != 1;
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "HardNotEqual"

[scenarios.baseline.sets]
A = ["a1", "a2"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="hard_not_equal.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_treats_should_false_as_soft_only(tmp_path: Path) -> None:
    source = """
problem SoftOnlyShould {
  set A;
  find S : Subset(A);
  should false;
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "SoftOnlyShould"

[scenarios.baseline.sets]
A = ["a1"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="soft_only_should.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_soft_not_equal_constraint(tmp_path: Path) -> None:
    source = """
problem SoftNotEqual {
  set A;
  find S : Subset(A);
  should sum(if S.has(x) then 1 else 0 for x in A) != 1;
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "SoftNotEqual"

[scenarios.baseline.sets]
A = ["a1", "a2"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="soft_not_equal.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_reports_infeasible_hard_not_equal_constant(tmp_path: Path) -> None:
    source = """
problem InfeasibleHardNotEqual {
  set A;
  find S : Subset(A);
  must 1 != 1;
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "InfeasibleHardNotEqual"

[scenarios.baseline.sets]
A = ["a1"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="infeasible_hard_not_equal.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert any(diag.is_error for diag in unit.diagnostics)
    assert any(diag.message == "infeasible constant constraint `=`" for diag in unit.diagnostics)


def test_compile_supports_user_module_imported_unknowns(tmp_path: Path) -> None:
    module_path = tmp_path / "mylib" / "unknowns.qsol"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        """
unknown AssignLike(A, B) {
  rep {
    m : Mapping(A -> B);
  }
  view {
    predicate is(a: Elem(A), b: Elem(B)): Bool = m.is(a, b);
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    source = """
use mylib.unknowns;

problem ImportedUnknown {
  set A;
  set B;
  find X : AssignLike(A, B);
  must true;
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "ImportedUnknown"

[scenarios.baseline.sets]
A = ["a1", "a2"]
B = ["b1", "b2"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename=str(tmp_path / "model.qsol"),
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_stdlib_permutation_unknown(tmp_path: Path) -> None:
    source = """
use stdlib.permutation;

problem StdlibPermutation {
  set V;
  find P : Permutation(V);
  must true;
  minimize 0;
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "StdlibPermutation"

[scenarios.baseline.sets]
V = ["v1", "v2"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="stdlib_perm.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


def test_compile_supports_stdlib_logic_macros(tmp_path: Path) -> None:
    source = """
use stdlib.logic;

problem StdlibLogic {
  set A;
  find S : Subset(A);

  must exactly(1, S.has(x) for x in A);
  must atleast(1, S.has(x) for x in A);
  must atmost(2, S.has(x) for x in A);
  must between(1, 2, S.has(x) for x in A);
  minimize sum(indicator(S.has(x)) for x in A);
}
"""
    instance_payload = tomllib.loads(
        """
schema_version = "1"

[scenarios.baseline]
problem = "StdlibLogic"

[scenarios.baseline.sets]
A = ["a1", "a2"]
""".lstrip()
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="stdlib_logic.qsol",
            instance_payload=instance_payload["scenarios"]["baseline"],
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()
