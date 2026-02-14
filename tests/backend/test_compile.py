import json
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
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(
        json.dumps({"problem": "Simple", "sets": {"A": ["a1", "a2"]}, "params": {}}),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="simple.qsol",
            instance_path=str(instance_path),
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
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(
        json.dumps({"problem": "LinkedCut", "sets": {"V": ["v1", "v2", "v3"]}, "params": {}}),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="linked_cut.qsol",
            instance_path=str(instance_path),
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()

    weighted_instance_path = tmp_path / "instance-weighted.json"
    weighted_instance_path.write_text(
        json.dumps(
            {
                "problem": "LinkedCut",
                "sets": {"V": ["v1", "v2", "v3"]},
                "params": {
                    "LinkWeight": {
                        "v1": {"v1": 0, "v2": 2, "v3": 0},
                        "v2": {"v1": 2, "v2": 0, "v3": 3},
                        "v3": {"v1": 0, "v2": 3, "v3": 0},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    weighted_outdir = tmp_path / "out-weighted"
    weighted_unit = compile_source(
        source,
        options=CompileOptions(
            filename="linked_cut.qsol",
            instance_path=str(weighted_instance_path),
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
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(
        json.dumps(
            {
                "problem": "PartitionEqualSum",
                "sets": {"Items": ["a", "b", "c", "d"]},
                "params": {"Value": {"a": 1, "b": 2, "c": 3, "d": 4}},
            }
        ),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="partition_equal_sum.qsol",
            instance_path=str(instance_path),
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
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(
        json.dumps(
            {
                "problem": "MinBisection",
                "sets": {"V": [0, 1, 2, 3], "E": ["e0", "e1", "e2"]},
                "params": {
                    "U": {"e0": 0, "e1": 1, "e2": 2},
                    "W": {"e0": 1, "e1": 2, "e2": 3},
                    "Half": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="min_bisection.qsol",
            instance_path=str(instance_path),
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
    instance_payload = {
        "problem": "MinBisection",
        "sets": {"V": ["v1", "v2", "v3", "v4"], "E": ["e1", "e2", "e3"]},
        "params": {
            "U": {"e1": "v1", "e2": "v2", "e3": "v3"},
            "W": {"e1": "v2", "e2": "v3", "e3": "v4"},
        },
    }
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps(instance_payload), encoding="utf-8")

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="min_bisection_bool_logic.qsol",
            instance_path=str(instance_path),
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
    assert len(variable_labels) == len(instance_payload["sets"]["V"])
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
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(
        json.dumps(
            {
                "problem": "SizeFold",
                "sets": {"V": ["v1", "v2", "v3"]},
                "params": {},
            }
        ),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    unit = compile_source(
        source,
        options=CompileOptions(
            filename="size_fold.qsol",
            instance_path=str(instance_path),
            outdir=str(outdir),
            output_format="qubo",
        ),
    )

    assert not any(diag.is_error for diag in unit.diagnostics)
    assert unit.artifacts is not None
    assert Path(unit.artifacts.cqm_path or "").exists()
    assert Path(unit.artifacts.bqm_path or "").exists()
