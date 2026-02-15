from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from typer.testing import CliRunner

from qsol.cli import app


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


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


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {type(value)!r}")


def _write_simple_config(
    config_path: Path,
    *,
    with_execution: bool = False,
    execution: Mapping[str, object] | None = None,
) -> None:
    lines = [
        'schema_version = "1"',
        "",
        "[scenarios.base]",
        'problem = "Simple"',
        "",
        "[scenarios.base.sets]",
        'A = ["a1", "a2"]',
        "",
    ]
    execution_payload = execution
    if execution_payload is None and with_execution:
        execution_payload = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}
    if execution_payload is not None:
        lines.append("[scenarios.base.execution]")
        for key, value in execution_payload.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    config_path.write_text("\n".join(lines), encoding="utf-8")


def _write_multi_solution_config(
    config_path: Path,
    *,
    with_execution: bool = False,
    execution: Mapping[str, object] | None = None,
) -> None:
    lines = [
        'schema_version = "1"',
        "",
        "[scenarios.base]",
        'problem = "Multi"',
        "",
        "[scenarios.base.sets]",
        'A = ["a1", "a2"]',
        "",
    ]
    execution_payload = execution
    if execution_payload is None and with_execution:
        execution_payload = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}
    if execution_payload is not None:
        lines.append("[scenarios.base.execution]")
        for key, value in execution_payload.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    config_path.write_text("\n".join(lines), encoding="utf-8")


def _write_multi_scenario_config(config_path: Path) -> None:
    config_path.write_text(
        """
schema_version = "1"

[selection]
mode = "subset"
subset = ["s1", "s2"]

[defaults.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"

[defaults.solve]
solutions = 3

[scenarios.s1]
problem = "Multi"
[scenarios.s1.sets]
A = ["a1", "a2"]

[scenarios.s2]
problem = "Multi"
[scenarios.s2.sets]
A = ["a1", "a2", "a3"]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_weighted_problem(source_path: Path) -> None:
    source_path.write_text(
        """
problem Weighted {
  set A;
  param W[A] : Real;
  find S : Subset(A);
  minimize sum(if S.has(x) then W[x] else 0 for x in A);
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_weighted_multi_scenario_config(config_path: Path) -> None:
    config_path.write_text(
        """
schema_version = "1"

[selection]
mode = "subset"
subset = ["s1", "s2"]

[defaults.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"

[defaults.solve]
solutions = 4

[scenarios.s1]
problem = "Weighted"
[scenarios.s1.sets]
A = ["a1", "a2"]
[scenarios.s1.params.W]
a1 = 1
a2 = 2

[scenarios.s2]
problem = "Weighted"
[scenarios.s2.sets]
A = ["a1", "a2"]
[scenarios.s2.params.W]
a1 = 3
a2 = 1
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_failure_policy_config(config_path: Path) -> None:
    config_path.write_text(
        """
schema_version = "1"

[selection]
mode = "subset"
subset = ["ok", "bad"]

[defaults.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"

[scenarios.ok]
problem = "Multi"
[scenarios.ok.sets]
A = ["a1", "a2"]

[scenarios.bad]
problem = "Multi"
[scenarios.bad.sets]
A = ["a1", "a2"]
[scenarios.bad.execution]
runtime = "missing-runtime"
backend = "dimod-cqm-v1"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_failure_policy_fail_first_config(config_path: Path) -> None:
    config_path.write_text(
        """
schema_version = "1"

[selection]
mode = "subset"
subset = ["bad", "ok"]

[defaults.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"

[scenarios.ok]
problem = "Multi"
[scenarios.ok.sets]
A = ["a1", "a2"]

[scenarios.bad]
problem = "Multi"
[scenarios.bad.sets]
A = ["a1", "a2"]
[scenarios.bad.execution]
runtime = "missing-runtime"
backend = "dimod-cqm-v1"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_root_command_shows_welcome_message() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Welcome to QSOL" in result.stdout


def test_solve_command_executes_runtime_and_exports_artifacts(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)
    outdir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--out",
            str(outdir),
            "--runtime",
            "local-dimod",
            "--runtime-option",
            "sampler=exact",
            "--no-color",
            "--log-level",
            "debug",
        ],
    )

    assert result.exit_code == 0
    assert "Run Summary" in result.stdout
    assert "Runtime Parameters" in result.stdout
    assert "sampler=exact" in result.stdout
    assert "num_reads=100" in result.stdout
    assert "│ Reads" not in result.stdout
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
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)
    outdir = tmp_path / "out-short"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "s",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
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


def test_solve_infers_config_and_outdir_from_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    inferred_config = tmp_path / "simple.qsol.toml"
    _write_simple_config(inferred_config, with_execution=True)

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
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path, with_execution=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--runtime-option",
            "sampler=exact",
        ],
    )

    assert result.exit_code != 0
    assert "error[QSOL4006]" in result.stdout


def test_solve_uses_plugins_declared_in_scenario_execution(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
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
    _write_simple_config(
        config_path,
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
            "--config",
            str(config_path),
            "--out",
            str(outdir),
            "--no-color",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["runtime"] == "instance-runtime"


def test_solve_errors_when_inferred_config_is_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)

    runner = CliRunner()
    result = runner.invoke(app, ["solve", str(source_path), "--runtime-option", "sampler=exact"])

    assert result.exit_code != 0
    assert "error[QSOL4002]" in result.stdout
    assert "default config was not found" in result.stdout


def test_solve_runtime_options_file(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)
    outdir = tmp_path / "out-file"
    options_path = tmp_path / "runtime_options.json"
    options_path.write_text(json.dumps({"sampler": "exact", "num_reads": 5}), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
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
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-u",
            "local-dimod",
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
    config_path = tmp_path / "multi.qsol.toml"
    _write_multi_solution_config(config_path)
    outdir = tmp_path / "out-multi"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
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
    assert "Returned Solutions" in result.stdout
    assert [solution["rank"] for solution in solutions] == [1, 2, 3]
    energies = [solution["energy"] for solution in solutions]
    assert energies == sorted(energies)
    for energy in energies:
        assert str(energy) in result.stdout
    unique_samples = {json.dumps(solution["sample"], sort_keys=True) for solution in solutions}
    assert len(unique_samples) == 3
    assert run_payload["best_sample"] == solutions[0]["sample"]
    assert run_payload["energy"] == solutions[0]["energy"]


def test_solve_threshold_failure_writes_run_and_exits_nonzero(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    config_path = tmp_path / "multi.qsol.toml"
    _write_multi_solution_config(config_path)
    outdir = tmp_path / "out-threshold-fail"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-u",
            "local-dimod",
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


def test_solve_multi_scenario_default_intersection_writes_aggregate_run(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    config_path = tmp_path / "multi.qsol.toml"
    _write_multi_scenario_config(config_path)
    outdir = tmp_path / "out-multi-scenarios"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-x",
            "sampler=exact",
            "-n",
        ],
    )

    assert result.exit_code == 0
    assert (outdir / "scenarios" / "s1" / "run.json").exists()
    assert (outdir / "scenarios" / "s2" / "run.json").exists()
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["extensions"]["combine_mode"] == "intersection"
    assert run_payload["extensions"]["returned_solutions"] == 0


def test_solve_multi_scenario_union_override_returns_union(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    config_path = tmp_path / "multi.qsol.toml"
    _write_multi_scenario_config(config_path)
    outdir = tmp_path / "out-multi-scenarios-union"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-x",
            "sampler=exact",
            "--combine-mode",
            "union",
            "-n",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["extensions"]["combine_mode"] == "union"
    assert run_payload["extensions"]["returned_solutions"] > 0
    assert run_payload["extensions"]["solutions"]


def test_solve_multi_scenario_worst_case_energy_ranking(tmp_path: Path) -> None:
    source_path = tmp_path / "weighted.qsol"
    _write_weighted_problem(source_path)
    config_path = tmp_path / "weighted.qsol.toml"
    _write_weighted_multi_scenario_config(config_path)
    outdir = tmp_path / "out-weighted-multi"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-x",
            "sampler=exact",
            "--combine-mode",
            "intersection",
            "-n",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    solutions = run_payload["extensions"]["solutions"]
    assert solutions
    energies = [entry["energy"] for entry in solutions]
    assert energies == sorted(energies)
    for entry in solutions:
        scenario_energies = entry["scenario_energies"]
        assert entry["energy"] == max(scenario_energies.values())


def test_solve_multi_scenario_runtime_pair_mismatch_errors(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    outdir = tmp_path / "out-runtime-mismatch"
    config_path = tmp_path / "multi.qsol.toml"
    plugin_path = tmp_path / "custom_runtime_mismatch_plugin.py"
    plugin_path.write_text(
        """
from dataclasses import dataclass

from qsol.targeting.interfaces import PluginBundle
from qsol.targeting.types import StandardRunResult


@dataclass(slots=True)
class CustomRuntime:
    plugin_id: str = "custom-runtime"
    display_name: str = "Custom Runtime"

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
            extensions={
                "requested_solutions": 1,
                "returned_solutions": 1,
                "solutions": [
                    {
                        "rank": 1,
                        "energy": 0.0,
                        "sample": {},
                        "selected_assignments": [],
                    }
                ],
            },
        )


plugin_bundle = PluginBundle(runtimes=(CustomRuntime(),))
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    config_path.write_text(
        """
schema_version = "1"

[selection]
mode = "subset"
subset = ["s1", "s2"]

[defaults.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"

[scenarios.s1]
problem = "Multi"
[scenarios.s1.sets]
A = ["a1", "a2"]

[scenarios.s2]
problem = "Multi"
[scenarios.s2.sets]
A = ["a1", "a2"]
[scenarios.s2.execution]
runtime = "custom-runtime"
plugins = ["custom_runtime_mismatch_plugin:plugin_bundle"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-x",
            "sampler=exact",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4001]" in result.stdout
    assert (outdir / "run.json").exists()


def test_solve_multi_scenario_failure_policy_best_effort(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    config_path = tmp_path / "multi.qsol.toml"
    _write_failure_policy_config(config_path)
    outdir = tmp_path / "out-best-effort"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "--failure-policy",
            "best-effort",
            "-x",
            "sampler=exact",
            "-n",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "ok"


def test_solve_multi_scenario_failure_policy_run_all_fail_default(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    config_path = tmp_path / "multi.qsol.toml"
    _write_failure_policy_config(config_path)
    outdir = tmp_path / "out-run-all-fail"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-x",
            "sampler=exact",
            "-n",
        ],
    )

    assert result.exit_code == 1


def test_solve_multi_scenario_failure_policy_fail_fast_stops_early(tmp_path: Path) -> None:
    source_path = tmp_path / "multi.qsol"
    _write_multi_solution_problem(source_path)
    config_path = tmp_path / "multi.qsol.toml"
    _write_failure_policy_fail_first_config(config_path)
    outdir = tmp_path / "out-fail-fast"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "--failure-policy",
            "fail-fast",
            "-x",
            "sampler=exact",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert not (outdir / "scenarios" / "ok").exists()


def test_solve_rejects_invalid_solutions_count(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-u",
            "local-dimod",
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
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "-c",
            str(config_path),
            "-u",
            "local-dimod",
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
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)
    outdir = tmp_path / "out-feature-contract"
    plugin_path = tmp_path / "custom_runtime_no_solutions_plugin.py"
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
            "-c",
            str(config_path),
            "-o",
            str(outdir),
            "-u",
            "custom-runtime",
            "-p",
            "custom_runtime_no_solutions_plugin:plugin_bundle",
            "--solutions",
            "2",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL5002]" in result.stdout
    assert (outdir / "run.json").exists()


def test_solve_qiskit_runtime_writes_openqasm_artifact(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)
    outdir = tmp_path / "out-qiskit"

    monkeypatch.setattr(
        "qsol.targeting.plugins._probe_qiskit_core_dependencies", lambda: (True, [])
    )

    def _fake_solver(**kwargs):
        outdir_raw = kwargs["outdir"]
        assert isinstance(outdir_raw, str)
        qasm_path = Path(outdir_raw) / "qaoa.qasm"
        qasm_path.parent.mkdir(parents=True, exist_ok=True)
        qasm_path.write_text("OPENQASM 3;\nqubit[1] q;\n", encoding="utf-8")
        return type(
            "Payload",
            (),
            {
                "algorithm": "qaoa",
                "reads": 128,
                "solutions": [
                    {
                        "rank": 1,
                        "energy": 0.0,
                        "sample": {"S.has[a1]": 1, "S.has[a2]": 1},
                        "selected_assignments": [
                            {"variable": "S.has[a1]", "meaning": "S.has(a1)", "value": 1},
                            {"variable": "S.has[a2]", "meaning": "S.has(a2)", "value": 1},
                        ],
                        "probability": 1.0,
                        "status": "SUCCESS",
                    }
                ],
                "fake_backend": "FakeManilaV2",
                "openqasm_path": str(qasm_path),
            },
        )()

    monkeypatch.setattr("qsol.targeting.plugins._run_qiskit_solver", _fake_solver)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--out",
            str(outdir),
            "--runtime",
            "qiskit",
            "--runtime-option",
            "algorithm=qaoa",
            "--runtime-option",
            "fake_backend=FakeManilaV2",
            "--runtime-option",
            "shots=128",
            "--no-color",
        ],
    )

    assert result.exit_code == 0
    assert (outdir / "qaoa.qasm").exists()
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["runtime"] == "qiskit"
    assert run_payload["extensions"]["algorithm"] == "qaoa"
    assert run_payload["extensions"]["fake_backend"] == "FakeManilaV2"
    assert run_payload["extensions"]["openqasm_path"] == str(outdir / "qaoa.qasm")


def test_solve_qiskit_runtime_missing_optional_dependencies_reports_error(
    tmp_path: Path, monkeypatch
) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)

    monkeypatch.setattr(
        "qsol.targeting.plugins._probe_qiskit_core_dependencies",
        lambda: (False, ["qiskit", "qiskit-optimization"]),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--runtime",
            "qiskit",
            "--runtime-option",
            "algorithm=qaoa",
            "--no-color",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4010]" in result.stdout
    assert "uv sync --extra qiskit" in result.stdout


def test_solve_rejects_backend_options(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    config_path = tmp_path / "simple.qsol.toml"
    _write_simple_config(config_path)

    runner = CliRunner()
    long_result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--runtime",
            "local-dimod",
            "--backend",
            "dimod-cqm-v1",
        ],
    )
    assert long_result.exit_code != 0
    plain_long_output = _strip_ansi(long_result.output)
    assert "No such option" in plain_long_output
    assert "--backend" in plain_long_output

    short_result = runner.invoke(
        app,
        [
            "s",
            str(source_path),
            "-c",
            str(config_path),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
        ],
    )
    assert short_result.exit_code != 0
    plain_short_output = _strip_ansi(short_result.output)
    assert "No such option" in plain_short_output
    assert "-b" in plain_short_output


def test_solve_uses_entrypoint_runtime_options_and_output_defaults(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    outdir = tmp_path / "entrypoint-out"
    config_path = tmp_path / "simple.qsol.toml"
    config_path.write_text(
        f"""
schema_version = "1"

[entrypoint]
runtime = "local-dimod"
out = "{outdir}"
format = "ising"
runtime_options = {{ sampler = "exact" }}

[scenarios.base]
problem = "Simple"

[scenarios.base.sets]
A = ["a1", "a2"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--no-color",
        ],
    )

    assert result.exit_code == 0
    assert (outdir / "run.json").exists()
    assert (outdir / "ising.json").exists()
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["runtime"] == "local-dimod"
    assert run_payload["extensions"]["sampler"] == "exact"
    assert run_payload["extensions"]["runtime_options"]["num_reads"] == 100


def test_solve_entrypoint_runtime_options_are_overridden_by_cli(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    outdir = tmp_path / "entrypoint-override"
    config_path = tmp_path / "simple.qsol.toml"
    config_path.write_text(
        f"""
schema_version = "1"

[entrypoint]
runtime = "local-dimod"
out = "{outdir}"
runtime_options = {{ sampler = "simulated-annealing", num_reads = 5 }}

[scenarios.base]
problem = "Simple"

[scenarios.base.sets]
A = ["a1", "a2"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "solve",
            str(source_path),
            "--config",
            str(config_path),
            "--runtime-option",
            "sampler=exact",
            "--runtime-option",
            "num_reads=3",
            "--no-color",
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["extensions"]["sampler"] == "exact"
    assert run_payload["extensions"]["runtime_options"]["num_reads"] == 3
