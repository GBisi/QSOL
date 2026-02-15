from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from qsol.cli import app


def _write_model(path: Path) -> None:
    path.write_text(
        """
problem Demo {
  set A;
  find S : Subset(A);
  must forall x in A: S.has(x);
  minimize sum(if S.has(x) then 1 else 0 for x in A);
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_instance(path: Path) -> None:
    path.write_text(
        json.dumps({"problem": "Demo", "sets": {"A": ["a1", "a2"]}, "params": {}}),
        encoding="utf-8",
    )


def test_compile_stage_flags_and_compile_command(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(instance)
    outdir = tmp_path / "out"
    runner = CliRunner()

    parse_result = runner.invoke(app, ["compile", str(model), "--parse", "--json", "--no-color"])
    assert parse_result.exit_code == 0
    assert '"name": "Demo"' in parse_result.stdout

    check_result = runner.invoke(app, ["compile", str(model), "--check", "--no-color"])
    assert check_result.exit_code == 0
    assert "No diagnostics." in check_result.stdout

    lower_result = runner.invoke(app, ["compile", str(model), "--lower", "--json", "--no-color"])
    assert lower_result.exit_code == 0
    assert '"problems"' in lower_result.stdout

    compile_result = runner.invoke(
        app,
        [
            "compile",
            str(model),
            "--instance",
            str(instance),
            "--out",
            str(outdir),
            "--format",
            "ising",
            "--verbose",
            "--no-color",
            "--log-level",
            "debug",
        ],
    )
    assert compile_result.exit_code == 0
    assert "Compilation Artifacts" in compile_result.stdout
    assert (outdir / "ising.json").exists()


def test_run_command_simulated_annealing_branch(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(instance)
    outdir = tmp_path / "run-out"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            str(model),
            "--instance",
            str(instance),
            "--out",
            str(outdir),
            "--sampler",
            "simulated-annealing",
            "--num-reads",
            "5",
            "--seed",
            "7",
            "--no-color",
            "--log-level",
            "debug",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads((outdir / "run.json").read_text(encoding="utf-8"))
    assert payload["sampler"] == "simulated-annealing"
    assert payload["num_reads"] == 5
    assert payload["seed"] == 7


def test_compile_parse_flag_reports_error_for_invalid_input(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.qsol"
    invalid.write_text("problem P { set A find S : Subset(A); }", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["compile", str(invalid), "--parse", "--no-color"])
    assert result.exit_code == 1


def test_compile_stage_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    runner = CliRunner()
    result = runner.invoke(app, ["compile", str(model), "--parse", "--check"])
    assert result.exit_code != 0


def test_compile_json_requires_parse_or_lower_flag(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    runner = CliRunner()
    result = runner.invoke(app, ["compile", str(model), "--check", "--json"])
    assert result.exit_code != 0
