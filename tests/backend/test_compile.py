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
  must forall x in A: S.has(x);
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
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()


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
    predicate is(a in A, b in B): Bool = m.is(a, b);
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

  must exactly(1, sum(indicator(S.has(x)) for x in A));
  must atleast(1, sum(indicator(S.has(x)) for x in A));
  must atmost(2, sum(indicator(S.has(x)) for x in A));
  must between(1, 2, sum(indicator(S.has(x)) for x in A));
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
