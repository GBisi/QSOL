from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from typer.testing import CliRunner

from qsol.cli import app


def _write_simple_problem(source_path: Path) -> None:
    source_path.write_text(
        """
problem Simple {
  set A;
  find S : Subset(A);
  must forall x in A: S.has(x);
  minimize sum( if S.has(x) then 1 else 0 for x in A );
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_multi_solution_problem(source_path: Path) -> None:
    source_path.write_text(
        """
problem Multi {
  set A;
  find S : Subset(A);
  minimize sum( if S.has(x) then 1 else 0 for x in A );
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_simple_instance(
    instance_path: Path,
    *,
    with_execution: bool = False,
    execution: Mapping[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "problem": "Simple",
        "sets": {"A": ["a1", "a2"]},
        "params": {},
    }
    if execution is not None:
        payload["execution"] = dict(execution)
    elif with_execution:
        payload["execution"] = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}
    instance_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_multi_solution_instance(
    instance_path: Path,
    *,
    with_execution: bool = False,
    execution: Mapping[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "problem": "Multi",
        "sets": {"A": ["a1", "a2"]},
        "params": {},
    }
    if execution is not None:
        payload["execution"] = dict(execution)
    elif with_execution:
        payload["execution"] = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}
    instance_path.write_text(json.dumps(payload), encoding="utf-8")


def test_root_command_shows_welcome_message() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Welcome to QSOL" in result.stdout


def test_solve_command_executes_runtime_and_exports_artifacts(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)
    outdir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--instance",
            str(instance_path),
            "--out",
            str(outdir),
            "--runtime",
            "local-dimod",
            "--backend",
            "dimod-cqm-v1",
            "--runtime-option",
            "sampler=exact",
            "--no-color",
            "--log-level",
            "debug",
        ],
    )

    assert result.exit_code == 0
    assert "Run Summary" in result.stdout
    assert "Selected Assignments" in result.stdout
    assert (outdir / "model.bqm").exists()
    assert (outdir / "varmap.json").exists()
    assert (outdir / "run.json").exists()
    assert (outdir / "capability_report.json").exists()
    assert (outdir / "qsol.log").exists()

    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["schema_version"] == "1.0"
    assert run_payload["runtime"] == "local-dimod"
    assert run_payload["backend"] == "dimod-cqm-v1"
    assert "extensions" in run_payload


def test_solve_command_accepts_short_options(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)
    outdir = tmp_path / "out-short"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "s",
            str(source_path),
            "-i",
            str(instance_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-x",
            "sampler=exact",
            "-n",
            "-l",
            "debug",
        ],
    )

    assert result.exit_code == 0
    assert (outdir / "model.bqm").exists()
    assert (outdir / "run.json").exists()


def test_solve_infers_instance_and_outdir_from_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    inferred_instance = tmp_path / "simple.instance.json"
    _write_simple_instance(inferred_instance, with_execution=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "s",
            str(source_path),
            "-x",
            "sampler=exact",
            "--no-color",
        ],
    )

    inferred_outdir = tmp_path / "outdir" / "simple"
    assert result.exit_code == 0
    assert (inferred_outdir / "model.bqm").exists()
    assert (inferred_outdir / "run.json").exists()
    assert (inferred_outdir / "qsol.log").exists()


def test_solve_errors_when_target_selection_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "simple.instance.json"
    _write_simple_instance(instance_path, with_execution=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--instance",
            str(instance_path),
            "--runtime-option",
            "sampler=exact",
        ],
    )

    assert result.exit_code != 0
    assert "error[QSOL4006]" in result.stdout


def test_solve_uses_plugins_declared_in_instance_execution(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    outdir = tmp_path / "out-instance-plugin"
    plugin_path = tmp_path / "instance_runtime_plugin.py"
    plugin_path.write_text(
        """
from dataclasses import dataclass

from qsol.targeting.interfaces import PluginBundle
from qsol.targeting.types import StandardRunResult


@dataclass(slots=True)
class InstanceRuntime:
    plugin_id: str = "instance-runtime"
    display_name: str = "Runtime Loaded From Instance"

    def capability_catalog(self):
        return {"model.kind.cqm.v1": "full"}

    def compatible_backend_ids(self):
        return {"dimod-cqm-v1"}

    def check_support(self, _compiled_model, *, selection):
        _ = selection
        return []

    def run_model(self, _compiled_model, *, selection, run_options):
        _ = run_options
        return StandardRunResult(
            schema_version="1.0",
            runtime=selection.runtime_id,
            backend=selection.backend_id,
            status="ok",
            energy=0.0,
            reads=1,
            best_sample={},
            selected_assignments=[],
            timing_ms=0.0,
            capability_report_path="",
            extensions={"sampler": "instance-runtime"},
        )


plugin_bundle = PluginBundle(runtimes=(InstanceRuntime(),))
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_simple_instance(
        instance_path,
        execution={
            "runtime": "instance-runtime",
            "backend": "dimod-cqm-v1",
            "plugins": ["instance_runtime_plugin:plugin_bundle"],
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--instance",
            str(instance_path),
            "--out",
            str(outdir),
            "--no-color",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["runtime"] == "instance-runtime"


def test_solve_errors_when_inferred_instance_is_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)

    runner = CliRunner()
    result = runner.invoke(app, ["solve", str(source_path), "--runtime-option", "sampler=exact"])

    assert result.exit_code != 0
    assert "error[QSOL4002]" in result.stdout
    assert "default instance was not found" in result.stdout


def test_solve_runtime_options_file(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)
    outdir = tmp_path / "out-file"
    options_path = tmp_path / "runtime_options.json"
    options_path.write_text(json.dumps({"sampler": "exact", "num_reads": 5}), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-X",
            str(options_path),
            "-n",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["extensions"]["runtime_options"]["sampler"] == "exact"


def test_solve_invalid_runtime_option_format_reports_error(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-x",
            "not_key_value",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4001]" in result.stdout


def test_solve_returns_top_n_unique_solutions(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_multi_solution_instance(instance_path)
    outdir = tmp_path / "out-multi"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-x",
            "sampler=exact",
            "--solutions",
            "3",
            "-n",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "ok"
    solutions = run_payload["extensions"]["solutions"]
    assert len(solutions) == 3
    assert [solution["rank"] for solution in solutions] == [1, 2, 3]
    energies = [solution["energy"] for solution in solutions]
    assert energies == sorted(energies)
    unique_samples = {json.dumps(solution["sample"], sort_keys=True) for solution in solutions}
    assert len(unique_samples) == 3
    assert run_payload["best_sample"] == solutions[0]["sample"]
    assert run_payload["energy"] == solutions[0]["energy"]


def test_solve_threshold_failure_writes_run_and_exits_nonzero(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_multi_solution_instance(instance_path)
    outdir = tmp_path / "out-threshold-fail"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-x",
            "sampler=exact",
            "--solutions",
            "3",
            "--energy-max",
            "0",
            "-n",
        ],
    )

    assert result.exit_code == 1
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "threshold_failed"
    threshold = run_payload["extensions"]["energy_threshold"]
    assert threshold["passed"] is False
    assert threshold["violations"]
    assert "error[QSOL5002]" in result.stdout


def test_solve_rejects_invalid_solutions_count(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "--solutions",
            "0",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4001]" in result.stdout


def test_solve_rejects_invalid_energy_range(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "--energy-min",
            "2.0",
            "--energy-max",
            "1.0",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4001]" in result.stdout


def test_solve_feature_contract_failure_for_custom_runtime(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)
    outdir = tmp_path / "out-feature-contract"
    plugin_path = tmp_path / "custom_runtime_plugin.py"
    plugin_path.write_text(
        """
from dataclasses import dataclass

from qsol.targeting.interfaces import PluginBundle
from qsol.targeting.types import StandardRunResult


@dataclass(slots=True)
class RuntimeWithoutSolutions:
    plugin_id: str = "custom-runtime"
    display_name: str = "Custom Runtime Missing Solutions"

    def capability_catalog(self):
        return {"model.kind.cqm.v1": "full"}

    def compatible_backend_ids(self):
        return {"dimod-cqm-v1"}

    def check_support(self, _compiled_model, *, selection):
        _ = selection
        return []

    def run_model(self, _compiled_model, *, selection, run_options):
        _ = run_options
        return StandardRunResult(
            schema_version="1.0",
            runtime=selection.runtime_id,
            backend=selection.backend_id,
            status="ok",
            energy=0.0,
            reads=1,
            best_sample={},
            selected_assignments=[],
            timing_ms=0.0,
            capability_report_path="",
            extensions={},
        )


plugin_bundle = PluginBundle(runtimes=(RuntimeWithoutSolutions(),))
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-i",
            str(instance_path),
            "-o",
            str(outdir),
            "-u",
            "custom-runtime",
            "-b",
            "dimod-cqm-v1",
            "-p",
            "custom_runtime_plugin:plugin_bundle",
            "--solutions",
            "2",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL5002]" in result.stdout
    assert (outdir / "run.json").exists()
