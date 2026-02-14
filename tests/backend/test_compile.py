import json
from pathlib import Path

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
