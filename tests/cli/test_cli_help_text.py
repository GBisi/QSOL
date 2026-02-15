from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from qsol.cli import app


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_qsol_root_help_includes_command_descriptions() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["-h"], env={"COLUMNS": "120"})

    assert result.exit_code == 0
    assert "Compile model+scenario and export backend artifacts." in result.stdout
    assert "Compile, run, and export solve results for model+scenario." in result.stdout
    assert "Alias for `build`." in result.stdout
    assert "Alias for `solve`." in result.stdout
    assert "Frontend-only inspection commands" in result.stdout
    assert "Target discovery and compatibility commands" in result.stdout


def test_qsol_subcommand_help_includes_descriptions_and_arguments() -> None:
    runner = CliRunner()
    env = {"COLUMNS": "120"}

    inspect_help = runner.invoke(app, ["inspect", "-h"], env=env)
    assert inspect_help.exit_code == 0
    assert "Parse a QSOL model and print AST output." in inspect_help.stdout
    assert "Run frontend checks (parse/resolve/typecheck/validate)." in inspect_help.stdout
    assert "Lower a QSOL model to symbolic kernel IR." in inspect_help.stdout
    assert "Alias for `inspect parse`." in inspect_help.stdout
    assert "Alias for `inspect check`." in inspect_help.stdout
    assert "Alias for `inspect lower`." in inspect_help.stdout

    targets_help = runner.invoke(app, ["targets", "-h"], env=env)
    assert targets_help.exit_code == 0
    assert "List discovered runtime and backend plugins." in targets_help.stdout
    assert "Show capability catalogs and pair compatibility." in targets_help.stdout
    assert "Check model+scenario support for a selected target pair." in targets_help.stdout
    assert "Alias for `targets list`." in targets_help.stdout
    assert "Alias for `targets capabilities`." in targets_help.stdout
    assert "Alias for `targets check`." in targets_help.stdout

    solve_help = runner.invoke(app, ["solve", "-h"], env=env)
    assert solve_help.exit_code == 0
    plain_solve_help = _strip_ansi(solve_help.stdout)
    assert "Path to the QSOL model source file." in plain_solve_help
    assert "--backend" not in plain_solve_help
    assert re.search(r"--sol\S*", plain_solve_help)
    assert "Number of best unique" in plain_solve_help
    assert "solutions to return" in plain_solve_help
    assert "--config" in plain_solve_help
    assert "--scenario" in plain_solve_help
    assert "--all-scenarios" in plain_solve_help
    assert "--combine-mode" in plain_solve_help
    assert "--failure-policy" in plain_solve_help
    assert "--energy-min" in plain_solve_help
    assert "Inclusive minimum" in plain_solve_help
    assert "--energy-max" in plain_solve_help
    assert "Inclusive maximum" in plain_solve_help

    build_help = runner.invoke(app, ["build", "-h"], env=env)
    assert build_help.exit_code == 0
    assert "--backend" not in build_help.stdout
    assert "--config" in build_help.stdout
    assert "--scenario" in build_help.stdout
    assert "--all-scenarios" in build_help.stdout
    assert "--failure-policy" in build_help.stdout

    caps_help = runner.invoke(app, ["targets", "capabilities", "-h"], env=env)
    assert caps_help.exit_code == 0
    assert "--backend" not in caps_help.stdout

    check_help = runner.invoke(app, ["targets", "check", "-h"], env=env)
    assert check_help.exit_code == 0
    assert "--backend" not in check_help.stdout
    assert "--config" in check_help.stdout
    assert "--scenario" in check_help.stdout
    assert "--all-scenarios" in check_help.stdout
    assert "--failure-policy" in check_help.stdout


def test_argparse_cli_help_texts_are_useful() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    suite_script = repo_root / "examples" / "run_equivalence_suite.py"
    suite_help = subprocess.run(
        [sys.executable, str(suite_script), "-h"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert suite_help.returncode == 0
    assert "Run all example equivalence scripts and report a rich summary." in suite_help.stdout
    assert "Sampler mode to pass to each equivalence script" in suite_help.stdout
    assert "Per-script timeout in seconds; 0 disables timeout" in suite_help.stdout

    example_scripts = [
        repo_root / "examples" / "generic_bqm" / "test_equivalence.py",
        repo_root / "examples" / "min_bisection" / "test_equivalence.py",
        repo_root / "examples" / "partition_equal_sum" / "test_equivalence.py",
    ]
    for script in example_scripts:
        help_result = subprocess.run(
            [sys.executable, str(script), "-h"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert help_result.returncode == 0
        assert "--simulated-annealing" in help_result.stdout
        assert "SimulatedAnnealingSampler" in help_result.stdout
        assert "runtime" in help_result.stdout
        assert "solve" in help_result.stdout
        assert "checks" in help_result.stdout
        assert "Number of reads for simulated annealing" in help_result.stdout
