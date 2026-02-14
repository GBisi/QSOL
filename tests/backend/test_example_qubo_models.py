from __future__ import annotations

from pathlib import Path

import pytest

from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import compile_source


@pytest.mark.parametrize(
    ("model_name", "instance_name"),
    [
        ("bounded_max_cut.qsol", "bounded_max_cut.instance.json"),
        ("bounded_max_cut.qsol", "bounded_max_cut.weighted.instance.json"),
        ("mapping_collision_penalty.qsol", "mapping_collision_penalty.instance.json"),
        ("exact_k_subset.qsol", "exact_k_subset.instance.json"),
    ],
)
def test_example_qubo_models_compile(
    tmp_path: Path,
    model_name: str,
    instance_name: str,
) -> None:
    examples_dir = Path(__file__).resolve().parents[2] / "examples" / "qubo"
    source = (examples_dir / model_name).read_text(encoding="utf-8")
    instance_path = examples_dir / instance_name
    outdir = tmp_path / model_name.replace(".qsol", "")

    unit = compile_source(
        source,
        options=CompileOptions(
            filename=model_name,
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
