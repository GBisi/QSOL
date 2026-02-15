from __future__ import annotations

import json
from collections.abc import Mapping
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


def _write_instance(
    path: Path,
    *,
    with_execution: bool = False,
    execution: Mapping[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "problem": "Demo",
        "sets": {"A": ["a1", "a2"]},
        "params": {},
    }
    if execution is not None:
        payload["execution"] = dict(execution)
    elif with_execution:
        payload["execution"] = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_inspect_parse_check_lower_commands(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    runner = CliRunner()

    parse_result = runner.invoke(app, ["ins", "p", str(model), "-j", "-n"])
    assert parse_result.exit_code == 0
    assert '"name": "Demo"' in parse_result.stdout

    check_result = runner.invoke(app, ["ins", "c", str(model), "-n"])
    assert check_result.exit_code == 0
    assert "No diagnostics." in check_result.stdout

    lower_result = runner.invoke(app, ["ins", "l", str(model), "-j", "-n"])
    assert lower_result.exit_code == 0
    assert '"problems"' in lower_result.stdout


def test_inspect_parse_reports_error_for_invalid_input(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.qsol"
    invalid.write_text("problem P { set A find S : Subset(A); }", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["inspect", "parse", str(invalid), "--no-color"])
    assert result.exit_code == 1
    assert "error[QSOL1001]" in result.stdout


def test_targets_list_and_capabilities_commands() -> None:
    runner = CliRunner()

    list_result = runner.invoke(app, ["tg", "ls", "-n"])
    assert list_result.exit_code == 0
    assert "Runtimes" in list_result.stdout
    assert "Backends" in list_result.stdout
    assert "local-dimod" in list_result.stdout
    assert "dimod-cqm-v1" in list_result.stdout

    caps_result = runner.invoke(
        app,
        [
            "tg",
            "caps",
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-n",
        ],
    )
    assert caps_result.exit_code == 0
    assert "Runtime Capabilities" in caps_result.stdout
    assert "Backend Capabilities" in caps_result.stdout
    assert "constraint.compare.eq.v1" in caps_result.stdout


def test_targets_check_writes_capability_report(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(instance)
    outdir = tmp_path / "target-check"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tg",
            "chk",
            str(model),
            "-i",
            str(instance),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-o",
            str(outdir),
            "-n",
        ],
    )

    assert result.exit_code == 0
    report_path = outdir / "capability_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["supported"] is True
    assert report["selection"]["runtime"] == "local-dimod"
    assert report["selection"]["backend"] == "dimod-cqm-v1"


def test_targets_check_uses_instance_execution_defaults(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(instance, with_execution=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tg",
            "chk",
            str(model),
            "-i",
            str(instance),
            "-n",
        ],
    )

    assert result.exit_code == 0
    assert "Supported" in result.stdout


def test_targets_check_errors_when_target_selection_missing(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(instance, with_execution=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "targets",
            "chk",
            str(model),
            "-i",
            str(instance),
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4006]" in result.stdout


def test_targets_check_errors_when_execution_plugins_is_invalid(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(
        instance,
        execution={
            "runtime": "local-dimod",
            "backend": "dimod-cqm-v1",
            "plugins": "broken",
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "targets",
            "chk",
            str(model),
            "-i",
            str(instance),
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4009]" in result.stdout


def test_build_command_exports_artifacts_and_report(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    instance = tmp_path / "demo.instance.json"
    _write_instance(instance)
    outdir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "b",
            str(model),
            "-i",
            str(instance),
            "-u",
            "local-dimod",
            "-b",
            "dimod-cqm-v1",
            "-o",
            str(outdir),
            "-f",
            "ising",
            "-n",
        ],
    )

    assert result.exit_code == 0
    assert (outdir / "model.cqm").exists()
    assert (outdir / "model.bqm").exists()
    assert (outdir / "ising.json").exists()
    assert (outdir / "capability_report.json").exists()


def test_targets_capabilities_unknown_id_error() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "targets",
            "caps",
            "-u",
            "missing-runtime",
            "-b",
            "dimod-cqm-v1",
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4007]" in result.stdout
