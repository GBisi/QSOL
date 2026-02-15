import json
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


def _write_simple_instance(instance_path: Path) -> None:
    instance_path.write_text(
        json.dumps({"problem": "Simple", "sets": {"A": ["a1", "a2"]}, "params": {}}),
        encoding="utf-8",
    )


def test_root_command_shows_welcome_message() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Welcome to QSOL" in result.stdout


def test_run_command_executes_solver_and_exports_artifacts(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)
    outdir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(source_path),
            "--instance",
            str(instance_path),
            "--out",
            str(outdir),
            "--sampler",
            "exact",
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
    assert (outdir / "qsol.log").exists()


def test_run_command_accepts_short_options(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    instance_path = tmp_path / "instance.json"
    _write_simple_instance(instance_path)
    outdir = tmp_path / "out-short"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(source_path),
            "-i",
            str(instance_path),
            "-o",
            str(outdir),
            "-s",
            "exact",
            "-n",
            "-l",
            "debug",
        ],
    )

    assert result.exit_code == 0
    assert (outdir / "model.bqm").exists()
    assert (outdir / "run.json").exists()


def test_run_infers_instance_and_outdir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)
    inferred_instance = tmp_path / "simple.instance.json"
    _write_simple_instance(inferred_instance)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(source_path),
            "--sampler",
            "exact",
            "--no-color",
        ],
    )

    inferred_outdir = tmp_path / "outdir" / "simple"
    assert result.exit_code == 0
    assert (inferred_outdir / "model.bqm").exists()
    assert (inferred_outdir / "run.json").exists()
    assert (inferred_outdir / "qsol.log").exists()


def test_run_errors_when_inferred_instance_is_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "simple.qsol"
    _write_simple_problem(source_path)

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(source_path), "--sampler", "exact"])

    assert result.exit_code != 0
    assert "error[QSOL4002]" in result.stdout
    assert "default instance was not found" in result.stdout
    assert "--> " in result.stdout
