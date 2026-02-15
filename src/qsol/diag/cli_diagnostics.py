from __future__ import annotations

from pathlib import Path

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span


def _span_for_file(file: Path | str | None) -> Span:
    filename = "<cli>" if file is None else str(file)
    return Span(
        start_offset=0,
        end_offset=1,
        line=1,
        col=1,
        end_line=1,
        end_col=2,
        filename=filename,
    )


def invalid_flag_combination(message: str, *, file: Path | str | None = None) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4001",
        message=message,
        span=_span_for_file(file),
        help=["Use `qsol compile -h` to inspect valid flag combinations."],
    )


def missing_instance_file(inferred_path: Path, *, model_path: Path) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4002",
        message=f"instance file not provided and default instance was not found: {inferred_path}",
        span=_span_for_file(model_path),
        help=[
            f"Create `{inferred_path.name}` next to the model, or pass `--instance <path>`.",
            "Instance JSON must contain `problem`, `sets`, and optional `params`.",
        ],
    )


def missing_config_file(
    inferred_path: Path,
    *,
    model_path: Path,
) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4002",
        message=f"config file not provided and default config was not found: {inferred_path}",
        span=_span_for_file(model_path),
        help=[
            f"Create `{inferred_path.name}` next to the model, or pass `--config <path>`.",
            "Config files must use TOML and include a `scenarios` table.",
        ],
    )


def ambiguous_config_file(
    *,
    model_path: Path,
    expected_path: Path,
    candidates: list[Path],
) -> Diagnostic:
    listed = ", ".join(path.name for path in candidates)
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4002",
        message="config file not provided and default config is ambiguous",
        span=_span_for_file(model_path),
        notes=[
            f"found candidates: {listed}",
            f"expected same-name config: {expected_path.name}",
        ],
        help=[
            "Pass `--config <path>` explicitly, or keep a single `*.qsol.toml` file.",
        ],
    )


def file_read_error(path: Path, exc: OSError) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4003",
        message=f"failed to read file: {path}",
        span=_span_for_file(path),
        notes=[str(exc)],
        help=["Verify the file path exists and is readable."],
    )


def config_load_error(path: Path, exc: Exception) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4004",
        message=f"failed to load config TOML: {path}",
        span=_span_for_file(path),
        notes=[str(exc)],
        help=["Ensure the config payload is valid TOML and matches the expected schema."],
    )


def instance_load_error(path: Path, exc: Exception) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4004",
        message=f"failed to load instance JSON: {path}",
        span=_span_for_file(path),
        notes=[str(exc)],
        help=["Ensure the instance payload is valid JSON object syntax."],
    )


def missing_artifact(message: str, *, model_path: Path) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4005",
        message=message,
        span=_span_for_file(model_path),
        help=["Run `qsol compile` first and verify artifacts were exported successfully."],
    )


def runtime_prep_error(
    model_path: Path,
    message: str,
    *,
    notes: list[str] | None = None,
) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL4005",
        message=message,
        span=_span_for_file(model_path),
        notes=notes or [],
        help=[
            "Inspect artifacts in the output directory and regenerate with `qsol compile` if needed."
        ],
    )


def runtime_sampling_error(model_path: Path, exc: Exception) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code="QSOL5001",
        message="sampler runtime failure",
        span=_span_for_file(model_path),
        notes=[str(exc)],
        help=[
            "Retry with a different runtime option profile (for example `--runtime-option sampler=exact`)."
        ],
    )
