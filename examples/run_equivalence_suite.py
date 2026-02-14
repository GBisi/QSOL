from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass(slots=True)
class SuiteResult:
    script: Path
    example: str
    returncode: int
    duration_seconds: float
    output: str
    timed_out: bool = False
    structural_equivalent: bool | None = None
    result_equivalent: bool | None = None
    expected_num_variables: int | None = None
    actual_num_variables: int | None = None
    expected_num_interactions: int | None = None
    actual_num_interactions: int | None = None
    offset_expected: float | None = None
    offset_actual: float | None = None
    offset_delta: float | None = None

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def status(self) -> str:
        if self.timed_out:
            return "timeout"
        return "pass" if self.passed else "fail"

    @property
    def structural_status(self) -> str:
        if self.structural_equivalent is None:
            return "unknown"
        return "equivalent" if self.structural_equivalent else "not-equivalent"

    @property
    def result_status(self) -> str:
        if self.result_equivalent is None:
            return "skipped"
        return "equivalent" if self.result_equivalent else "not-equivalent"


SUMMARY_MARKER = "__QSOL_EQUIV_SUMMARY__"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run all example equivalence scripts and report a rich summary. "
            "Discovers both test_equivalence.py and legacy test_quivalence.py."
        )
    )
    parser.add_argument(
        "--sampler",
        choices=("exact", "simulated-annealing"),
        default="exact",
        help="Sampler mode to pass to each equivalence script (default: exact).",
    )
    parser.add_argument(
        "--num-reads",
        type=_positive_int,
        default=100,
        help="Number of reads when using simulated annealing (default: 100).",
    )
    parser.add_argument(
        "--show-output",
        choices=("none", "failed", "all"),
        default="failed",
        help="Print child script output for none/failed/all (default: failed).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=0,
        help="Per-script timeout in seconds; 0 disables timeout (default: 0).",
    )
    return parser.parse_args()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def _discover_equivalence_scripts(examples_dir: Path) -> list[Path]:
    canonical = examples_dir.glob("*/test_equivalence.py")
    legacy = examples_dir.glob("*/test_quivalence.py")
    discovered = sorted({path.resolve() for path in [*canonical, *legacy] if path.is_file()})
    return discovered


def _build_command(script: Path, *, sampler: str, num_reads: int) -> list[str]:
    cmd = [sys.executable, str(script)]
    if sampler == "simulated-annealing":
        cmd.extend(["--simulated-annealing", "--num-reads", str(num_reads)])
    return cmd


def _run_script(
    script: Path,
    *,
    repo_root: Path,
    sampler: str,
    num_reads: int,
    timeout_seconds: int,
) -> SuiteResult:
    cmd = _build_command(script, sampler=sampler, num_reads=num_reads)
    example = script.parent.name
    start = perf_counter()
    run_env = {**os.environ, "QSOL_EQUIV_SUMMARY_JSON": "1"}
    try:
        completed = subprocess.run(
            cmd,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
        )
        duration = perf_counter() - start
        output = completed.stdout
        if completed.stderr:
            output = f"{output}\n{completed.stderr}" if output else completed.stderr
        clean_output, summary = _extract_summary(output)
        return SuiteResult(
            script=script,
            example=example,
            returncode=completed.returncode,
            duration_seconds=duration,
            output=clean_output,
            structural_equivalent=summary.get("structural_equivalent"),
            result_equivalent=summary.get("result_equivalent"),
            expected_num_variables=summary.get("expected_num_variables"),
            actual_num_variables=summary.get("actual_num_variables"),
            expected_num_interactions=summary.get("expected_num_interactions"),
            actual_num_interactions=summary.get("actual_num_interactions"),
            offset_expected=summary.get("offset_expected"),
            offset_actual=summary.get("offset_actual"),
            offset_delta=summary.get("offset_delta"),
        )
    except subprocess.TimeoutExpired as exc:
        duration = perf_counter() - start
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        output = stdout
        if stderr:
            output = f"{output}\n{stderr}" if output else stderr
        clean_output, summary = _extract_summary(output)
        return SuiteResult(
            script=script,
            example=example,
            returncode=124,
            duration_seconds=duration,
            output=clean_output,
            timed_out=True,
            structural_equivalent=summary.get("structural_equivalent"),
            result_equivalent=summary.get("result_equivalent"),
            expected_num_variables=summary.get("expected_num_variables"),
            actual_num_variables=summary.get("actual_num_variables"),
            expected_num_interactions=summary.get("expected_num_interactions"),
            actual_num_interactions=summary.get("actual_num_interactions"),
            offset_expected=summary.get("offset_expected"),
            offset_actual=summary.get("offset_actual"),
            offset_delta=summary.get("offset_delta"),
        )


def _extract_summary(output: str) -> tuple[str, dict[str, object]]:
    summary: dict[str, object] = {}
    kept_lines: list[str] = []
    for line in output.splitlines():
        if not line.startswith(SUMMARY_MARKER):
            kept_lines.append(line)
            continue
        payload = line.removeprefix(SUMMARY_MARKER)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            summary = parsed
    clean_output = "\n".join(kept_lines).strip()
    return clean_output, summary


def _should_show_output(show_output: str, result: SuiteResult) -> bool:
    if show_output == "all":
        return True
    if show_output == "failed" and not result.passed:
        return True
    return False


def _tail_output(text: str, *, max_lines: int = 60) -> str:
    if not text.strip():
        return "<no output>"
    lines = text.rstrip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    tail = "\n".join(lines[-max_lines:])
    omitted = len(lines) - max_lines
    return f"... ({omitted} lines omitted)\n{tail}"


def main() -> int:
    args = _parse_args()
    console = Console()

    examples_dir = Path(__file__).resolve().parent
    repo_root = examples_dir.parent
    scripts = _discover_equivalence_scripts(examples_dir)

    if not scripts:
        console.print("[bold yellow]No equivalence scripts found.[/bold yellow]")
        return 1

    results: list[SuiteResult] = []
    for script in scripts:
        results.append(
            _run_script(
                script,
                repo_root=repo_root,
                sampler=args.sampler,
                num_reads=args.num_reads,
                timeout_seconds=args.timeout_seconds,
            )
        )

    table = Table(title="Example Equivalence Suite")
    table.add_column("Example")
    table.add_column("Sampler")
    table.add_column("Structural Eq")
    table.add_column("Result Eq")
    table.add_column("Variables")
    table.add_column("Interactions")
    table.add_column("Offset")
    table.add_column("Offset Delta")
    table.add_column("Exit")
    table.add_column("Time (s)")

    for result in results:
        structural_style = (
            "green"
            if result.structural_equivalent is True
            else "red"
            if result.structural_equivalent is False
            else "yellow"
        )
        result_style = (
            "green"
            if result.result_equivalent is True
            else "red"
            if result.result_equivalent is False
            else "yellow"
        )
        variables = (
            f"{result.expected_num_variables}/{result.actual_num_variables}"
            if result.expected_num_variables is not None and result.actual_num_variables is not None
            else "-"
        )
        interactions = (
            f"{result.expected_num_interactions}/{result.actual_num_interactions}"
            if result.expected_num_interactions is not None
            and result.actual_num_interactions is not None
            else "-"
        )
        offset = (
            f"{result.offset_expected:.6g}/{result.offset_actual:.6g}"
            if result.offset_expected is not None and result.offset_actual is not None
            else "-"
        )
        offset_delta = f"{result.offset_delta:.6g}" if result.offset_delta is not None else "-"
        table.add_row(
            result.example,
            args.sampler,
            f"[{structural_style}]{result.structural_status}[/{structural_style}]",
            f"[{result_style}]{result.result_status}[/{result_style}]",
            variables,
            interactions,
            offset,
            offset_delta,
            str(result.returncode),
            f"{result.duration_seconds:.2f}",
        )

    console.print(table)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and not r.timed_out)
    timed_out = sum(1 for r in results if r.timed_out)
    structural_equivalent = sum(1 for r in results if r.structural_equivalent is True)
    structural_not_equivalent = sum(1 for r in results if r.structural_equivalent is False)
    result_equivalent = sum(1 for r in results if r.result_equivalent is True)
    result_not_equivalent = sum(1 for r in results if r.result_equivalent is False)
    result_skipped = sum(1 for r in results if r.result_equivalent is None)
    summary = (
        f"Total: {len(results)} | Passed: {passed} | Failed: {failed} | Timed out: {timed_out}"
        f"\nStructural Eq: {structural_equivalent} | Structural Not-Eq: {structural_not_equivalent}"
        f"\nResult Eq: {result_equivalent} | Result Not-Eq: {result_not_equivalent} | Result Skipped: {result_skipped}"
    )
    summary_style = "green" if failed == 0 and timed_out == 0 else "red"
    console.print(Panel(summary, title="Summary", border_style=summary_style))

    for result in results:
        if not _should_show_output(args.show_output, result):
            continue
        header = f"{result.example} ({result.status}, exit={result.returncode})"
        console.print(Panel(_tail_output(result.output), title=header, border_style="blue"))

    return 0 if failed == 0 and timed_out == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
