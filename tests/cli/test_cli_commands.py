from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from typer.testing import CliRunner

from qsol.cli import app


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


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


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        rendered = ", ".join(_toml_value(item) for item in value)
        return f"[{rendered}]"
    raise TypeError(f"unsupported TOML literal: {type(value)!r}")


def _write_config(
    path: Path,
    *,
    with_execution: bool = False,
    execution: Mapping[str, object] | None = None,
) -> None:
    lines = [
        'schema_version = "1"',
        "",
        "[scenarios.base]",
        'problem = "Demo"',
        "",
        "[scenarios.base.sets]",
        'A = ["a1", "a2"]',
        "",
    ]

    execution_payload: Mapping[str, object] | None = execution
    if execution_payload is None and with_execution:
        execution_payload = {"runtime": "local-dimod", "backend": "dimod-cqm-v1"}

    if execution_payload is not None:
        lines.extend(["[scenarios.base.execution]"])
        for key, value in execution_payload.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


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
    assert "qiskit" in list_result.stdout
    assert "dimod-cqm-v1" in list_result.stdout

    caps_result = runner.invoke(
        app,
        [
            "tg",
            "caps",
            "-u",
            "local-dimod",
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
    config = tmp_path / "demo.qsol.toml"
    _write_config(config)
    outdir = tmp_path / "target-check"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tg",
            "chk",
            str(model),
            "-c",
            str(config),
            "-u",
            "local-dimod",
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


def test_targets_check_uses_config_execution_defaults(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    config = tmp_path / "demo.qsol.toml"
    _write_config(config, with_execution=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "tg",
            "chk",
            str(model),
            "-c",
            str(config),
            "-n",
        ],
    )

    assert result.exit_code == 0
    assert "Supported" in result.stdout


def test_targets_check_errors_when_target_selection_missing(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    config = tmp_path / "demo.qsol.toml"
    _write_config(config, with_execution=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "targets",
            "chk",
            str(model),
            "-c",
            str(config),
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4006]" in result.stdout


def test_targets_check_errors_when_config_plugins_is_invalid(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    config = tmp_path / "demo.qsol.toml"
    _write_config(
        config,
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
            "-c",
            str(config),
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4004]" in result.stdout


def test_build_command_exports_artifacts_and_report(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    config = tmp_path / "demo.qsol.toml"
    _write_config(config)
    outdir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "b",
            str(model),
            "-c",
            str(config),
            "-u",
            "local-dimod",
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
            "-n",
        ],
    )

    assert result.exit_code == 1
    assert "error[QSOL4007]" in result.stdout


def test_targets_and_build_reject_backend_option(tmp_path: Path) -> None:
    model = tmp_path / "demo.qsol"
    _write_model(model)
    config = tmp_path / "demo.qsol.toml"
    _write_config(config)

    runner = CliRunner()
    invocations = [
        ["targets", "caps", "-u", "local-dimod", "--backend", "dimod-cqm-v1"],
        ["targets", "chk", str(model), "-c", str(config), "--backend", "dimod-cqm-v1"],
        [
            "build",
            str(model),
            "-c",
            str(config),
            "-u",
            "local-dimod",
            "--backend",
            "dimod-cqm-v1",
        ],
    ]
    for args in invocations:
        result = runner.invoke(app, args)
        assert result.exit_code != 0
        plain_output = _strip_ansi(result.output)
        assert "No such option" in plain_output
        assert "--backend" in plain_output
