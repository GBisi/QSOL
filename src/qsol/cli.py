from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, cast

import dimod
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

from qsol.compiler.options import CompileOptions
from qsol.compiler.pipeline import (
    build_for_target,
    check_target_support,
    compile_frontend,
    run_for_target,
)
from qsol.diag.cli_diagnostics import file_read_error, missing_instance_file
from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.reporter import DiagnosticReporter
from qsol.diag.source import SourceText, Span
from qsol.targeting import PluginRegistry, RuntimeRunOptions
from qsol.targeting.compatibility import support_report_to_dict
from qsol.targeting.resolution import DEFAULT_BACKEND_ID
from qsol.targeting.types import StandardRunResult

app = typer.Typer(
    help="QSOL compiler frontend",
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
inspect_app = typer.Typer(help="Frontend-only inspection commands")
targets_app = typer.Typer(help="Target discovery and compatibility commands")

app.add_typer(inspect_app, name="inspect")
app.add_typer(inspect_app, name="ins")
app.add_typer(targets_app, name="targets")
app.add_typer(targets_app, name="tg")

LOGGER = logging.getLogger(__name__)


class SamplerKind(str, Enum):
    exact = "exact"
    simulated_annealing = "simulated-annealing"


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


@app.callback(invoke_without_command=True)
def root_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return

    console = Console()
    console.print(
        Panel(
            (
                "[bold cyan]Welcome to QSOL[/bold cyan]\n\n"
                "[white]QSOL compiles declarative models to CQM IR, checks target support, "
                "and runs pluggable runtimes.[/white]"
            ),
            title="[bold green]QSOL CLI[/bold green]",
            border_style="bright_blue",
            expand=False,
        )
    )

    quickstart = Table(title="Quick Start", show_header=True, header_style="bold magenta")
    quickstart.add_column("Workflow", style="bold yellow")
    quickstart.add_column("Command", style="green")
    quickstart.add_row(
        "Inspect frontend parse",
        "qsol inspect parse model.qsol --json",
    )
    quickstart.add_row(
        "Check target compatibility",
        ("qsol targets check model.qsol -i model.instance.json --runtime local-dimod"),
    )
    quickstart.add_row(
        "Build artifacts",
        ("qsol build model.qsol -i model.instance.json --runtime local-dimod -o outdir/model"),
    )
    quickstart.add_row(
        "Solve",
        ("qsol solve model.qsol -i model.instance.json --runtime local-dimod"),
    )
    console.print(quickstart)
    console.print("[dim]Use `qsol -h` for full command help.[/dim]")


def _configure_logging(level: LogLevel, *, log_file: Path | None = None) -> None:
    resolved_level = getattr(logging, level.value.upper())

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(resolved_level)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(resolved_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    return value


def _print_diags(
    console: Console, source: SourceText | None, diagnostics: list[Diagnostic]
) -> bool:
    reporter = DiagnosticReporter(console=console)
    if diagnostics:
        reporter.print(source, diagnostics)
    return any(d.is_error for d in diagnostics)


def _resolve_instance_path(
    file: Path, instance: Path | None
) -> tuple[Path | None, Diagnostic | None]:
    if instance is not None:
        return instance, None

    inferred_instance = file.with_suffix(".instance.json")
    if inferred_instance.exists():
        LOGGER.info("Inferred instance file: %s", inferred_instance)
        return inferred_instance, None
    return None, missing_instance_file(inferred_instance, model_path=file)


def _resolve_outdir(file: Path, outdir: Path | None) -> Path:
    if outdir is not None:
        return outdir

    inferred_outdir = Path.cwd() / "outdir" / file.stem
    LOGGER.info("Inferred output directory: %s", inferred_outdir)
    return inferred_outdir


def _diag(file: Path, *, code: str, message: str, notes: list[str] | None = None) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code=code,
        message=message,
        span=Span(
            start_offset=0,
            end_offset=1,
            line=1,
            col=1,
            end_line=1,
            end_col=2,
            filename=str(file),
        ),
        notes=notes or [],
    )


def _write_capability_report(outdir: Path, report_payload: dict[str, object]) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    report_path = outdir / "capability_report.json"
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")
    return report_path


def _parse_runtime_option_value(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _load_runtime_options_file(path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"failed to read runtime options file: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"failed to parse runtime options JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "runtime options file payload must be a JSON object"
    return {str(k): v for k, v in payload.items()}, None


def _parse_runtime_options(
    *,
    runtime_option_args: list[str],
    runtime_options_file: Path | None,
) -> tuple[dict[str, object] | None, str | None]:
    params: dict[str, object] = {}
    if runtime_options_file is not None:
        file_params, err = _load_runtime_options_file(runtime_options_file)
        if err is not None or file_params is None:
            return None, err
        params.update(file_params)

    for item in runtime_option_args:
        key, sep, raw_value = item.partition("=")
        if not sep or not key.strip():
            return None, (
                "runtime options must use `key=value` format; "
                "example: --runtime-option sampler=exact"
            )
        params[key.strip()] = _parse_runtime_option_value(raw_value)
    return params, None


def _is_internal_variable(label: str) -> bool:
    return label.startswith("aux:") or label.startswith("slack:")


def _sample_exact(bqm: dimod.BinaryQuadraticModel) -> Any:
    solver_ctor = cast(Callable[[], Any], dimod.ExactSolver)
    solver = solver_ctor()
    sample_fn = cast(Callable[[dimod.BinaryQuadraticModel], Any], solver.sample)
    return sample_fn(bqm)


def _sample_sa(bqm: dimod.BinaryQuadraticModel, sample_kwargs: dict[str, Any]) -> Any:
    sampler_ctor = cast(Callable[[], Any], dimod.SimulatedAnnealingSampler)
    sampler = sampler_ctor()
    sample_fn = cast(Callable[..., Any], sampler.sample)
    supported_params = set(getattr(sampler, "parameters", {}).keys())
    if supported_params:
        filtered_kwargs = {k: v for k, v in sample_kwargs.items() if k in supported_params}
        dropped = sorted(set(sample_kwargs) - set(filtered_kwargs))
        if dropped:
            LOGGER.debug("Ignoring unsupported simulated annealing kwargs: %s", ", ".join(dropped))
        return sample_fn(bqm, **filtered_kwargs)
    return sample_fn(bqm, **sample_kwargs)


def _write_run_output(
    *,
    outdir: Path,
    run_result: StandardRunResult | None = None,
    sampler: SamplerKind | None = None,
    num_reads: int | None = None,
    seed: int | None = None,
    sampleset: Any | None = None,
    varmap: dict[str, str] | None = None,
) -> Path:
    if run_result is None:
        if sampler is None or num_reads is None or sampleset is None or varmap is None:
            raise ValueError(
                "legacy run output mode requires sampler, num_reads, sampleset, and varmap"
            )
        first = sampleset.first
        selected: list[dict[str, object]] = []
        for var, value in sorted(first.sample.items(), key=lambda item: str(item[0])):
            if int(value) != 1:
                continue
            label = str(var)
            if _is_internal_variable(label) or label not in varmap:
                continue
            selected.append({"variable": label, "meaning": str(varmap[label]), "value": int(value)})
        payload = {
            "sampler": sampler.value,
            "num_reads": num_reads,
            "seed": seed,
            "energy": float(first.energy),
            "reads": int(len(sampleset)),
            "variables": int(len(first.sample)),
            "best_sample": {str(var): int(value) for var, value in first.sample.items()},
            "selected_assignments": selected,
        }
    else:
        payload = _to_jsonable(run_result)

    outdir.mkdir(parents=True, exist_ok=True)
    run_path = outdir / "run.json"
    run_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return run_path


@inspect_app.command("parse", help="Parse a QSOL model and print AST output.")
def inspect_parse(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Print AST as JSON."),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    _configure_logging(log_level)

    try:
        text = _read_file(file)
    except OSError as exc:
        _print_diags(console, None, [file_read_error(file, exc)])
        raise typer.Exit(code=1) from None

    unit = compile_frontend(text, options=CompileOptions(filename=str(file)))
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    if has_errors or unit.ast is None:
        raise typer.Exit(code=1) from None

    if json_out:
        console.print(json.dumps(_to_jsonable(unit.ast), indent=2, sort_keys=True))
    else:
        console.print(Pretty(unit.ast))


@inspect_app.command("check", help="Run frontend checks (parse/resolve/typecheck/validate).")
def inspect_check(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    _configure_logging(log_level)

    try:
        text = _read_file(file)
    except OSError as exc:
        _print_diags(console, None, [file_read_error(file, exc)])
        raise typer.Exit(code=1) from None

    unit = compile_frontend(text, options=CompileOptions(filename=str(file)))
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    if not unit.diagnostics:
        console.print("No diagnostics.")
    if has_errors:
        raise typer.Exit(code=1) from None


@inspect_app.command("lower", help="Lower a QSOL model to symbolic kernel IR.")
def inspect_lower(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Print lowered IR as JSON."),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    _configure_logging(log_level)

    try:
        text = _read_file(file)
    except OSError as exc:
        _print_diags(console, None, [file_read_error(file, exc)])
        raise typer.Exit(code=1) from None

    unit = compile_frontend(text, options=CompileOptions(filename=str(file)))
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    if has_errors or unit.lowered_ir_symbolic is None:
        raise typer.Exit(code=1) from None

    if json_out:
        console.print(json.dumps(_to_jsonable(unit.lowered_ir_symbolic), indent=2, sort_keys=True))
    else:
        console.print(Pretty(unit.lowered_ir_symbolic))


@targets_app.command("list", help="List discovered runtime and backend plugins.")
def targets_list(
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        "-p",
        help="Load an extra plugin bundle from module:attribute.",
    ),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
) -> None:
    console = Console(no_color=no_color)
    try:
        registry = PluginRegistry.from_discovery(module_specs=plugin)
    except Exception as exc:
        _print_diags(
            console,
            None,
            [
                _diag(
                    Path("<cli>"),
                    code="QSOL4009",
                    message="failed to load plugins",
                    notes=[str(exc)],
                )
            ],
        )
        raise typer.Exit(code=1) from None

    runtimes_table = Table(title="Runtimes")
    runtimes_table.add_column("ID")
    runtimes_table.add_column("Name")
    runtimes_table.add_column("Compatible Backends")
    for runtime in registry.list_runtimes():
        runtimes_table.add_row(
            runtime.plugin_id,
            runtime.display_name,
            ", ".join(sorted(runtime.compatible_backend_ids())),
        )
    console.print(runtimes_table)

    backends_table = Table(title="Backends")
    backends_table.add_column("ID")
    backends_table.add_column("Name")
    for backend in registry.list_backends():
        backends_table.add_row(backend.plugin_id, backend.display_name)
    console.print(backends_table)


@targets_app.command("capabilities", help="Show capability catalogs and pair compatibility.")
def targets_capabilities(
    runtime: str = typer.Option(..., "--runtime", "-u", help="Runtime plugin identifier."),
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        "-p",
        help="Load an extra plugin bundle from module:attribute.",
    ),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
) -> None:
    console = Console(no_color=no_color)
    try:
        registry = PluginRegistry.from_discovery(module_specs=plugin)
    except Exception as exc:
        _print_diags(
            console,
            None,
            [
                _diag(
                    Path("<cli>"),
                    code="QSOL4009",
                    message="failed to load plugins",
                    notes=[str(exc)],
                )
            ],
        )
        raise typer.Exit(code=1) from None

    runtime_plugin = registry.runtime(runtime)
    backend_plugin = registry.backend(DEFAULT_BACKEND_ID)
    diagnostics: list[Diagnostic] = []
    if runtime_plugin is None:
        diagnostics.append(
            _diag(Path("<cli>"), code="QSOL4007", message=f"unknown runtime id: `{runtime}`")
        )
    if backend_plugin is None:
        diagnostics.append(
            _diag(
                Path("<cli>"),
                code="QSOL4007",
                message=f"unknown backend id: `{DEFAULT_BACKEND_ID}`",
            )
        )
    if diagnostics:
        _print_diags(console, None, diagnostics)
        raise typer.Exit(code=1)

    assert runtime_plugin is not None
    assert backend_plugin is not None

    runtime_table = Table(title=f"Runtime Capabilities ({runtime_plugin.plugin_id})")
    runtime_table.add_column("Capability")
    runtime_table.add_column("Status")
    for cap, status in sorted(runtime_plugin.capability_catalog().items()):
        runtime_table.add_row(cap, status)
    console.print(runtime_table)

    backend_table = Table(title=f"Backend Capabilities ({backend_plugin.plugin_id})")
    backend_table.add_column("Capability")
    backend_table.add_column("Status")
    for cap, status in sorted(backend_plugin.capability_catalog().items()):
        backend_table.add_row(cap, status)
    console.print(backend_table)

    pair_table = Table(title="Pair Compatibility")
    pair_table.add_column("Runtime")
    pair_table.add_column("Backend")
    pair_table.add_column("Compatible")
    pair_table.add_row(
        runtime_plugin.plugin_id,
        backend_plugin.plugin_id,
        "yes" if backend_plugin.plugin_id in runtime_plugin.compatible_backend_ids() else "no",
    )
    console.print(pair_table)


def _read_model_and_instance(
    *,
    file: Path,
    instance: Path | None,
    console: Console,
) -> tuple[str | None, Path | None]:
    try:
        text = _read_file(file)
    except OSError as exc:
        _print_diags(console, None, [file_read_error(file, exc)])
        return None, None

    resolved_instance, instance_diag = _resolve_instance_path(file, instance)
    if instance_diag is not None:
        _print_diags(console, None, [instance_diag])
        return None, None

    return text, resolved_instance


@targets_app.command("check", help="Check model+instance support for a selected target pair.")
def targets_check(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    instance: Path | None = typer.Option(
        None,
        "--instance",
        "-i",
        help="Path to instance JSON. Defaults to <model>.instance.json when available.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output directory for capability_report.json and qsol.log.",
    ),
    runtime: str | None = typer.Option(None, "--runtime", "-u", help="Runtime plugin identifier."),
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        "-p",
        help="Load an extra plugin bundle from module:attribute.",
    ),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    resolved_outdir = _resolve_outdir(file, out)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")

    text, resolved_instance = _read_model_and_instance(
        file=file, instance=instance, console=console
    )
    if text is None or resolved_instance is None:
        raise typer.Exit(code=1)

    unit = check_target_support(
        text,
        options=CompileOptions(
            filename=str(file),
            instance_path=str(resolved_instance),
            runtime_id=runtime,
            plugin_specs=tuple(plugin),
        ),
    )
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    report_path: Path | None = None
    if unit.support_report is not None:
        report_path = _write_capability_report(
            resolved_outdir, support_report_to_dict(unit.support_report)
        )

    summary = Table(title="Target Support")
    summary.add_column("Key")
    summary.add_column("Value")
    summary.add_row(
        "Supported", "yes" if unit.support_report and unit.support_report.supported else "no"
    )
    summary.add_row(
        "Runtime",
        unit.target_selection.runtime_id if unit.target_selection else runtime or "<unresolved>",
    )
    summary.add_row(
        "Backend",
        unit.target_selection.backend_id if unit.target_selection else DEFAULT_BACKEND_ID,
    )
    summary.add_row(
        "Capability Report", str(report_path) if report_path is not None else "<not-written>"
    )
    console.print(summary)

    if has_errors or unit.support_report is None or not unit.support_report.supported:
        raise typer.Exit(code=1)


@app.command("build", help="Compile model+instance and export backend artifacts.")
def build_cmd(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    instance: Path | None = typer.Option(
        None,
        "--instance",
        "-i",
        help="Path to instance JSON. Defaults to <model>.instance.json when available.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output directory for artifacts. Defaults to <cwd>/outdir/<model_stem>.",
    ),
    output_format: str = typer.Option(
        "qubo",
        "--format",
        "-f",
        help="Export format for objective payload: qubo, ising, bqm, or cqm.",
    ),
    runtime: str | None = typer.Option(None, "--runtime", "-u", help="Runtime plugin identifier."),
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        "-p",
        help="Load an extra plugin bundle from module:attribute.",
    ),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
    log_level: LogLevel = typer.Option(
        LogLevel.info,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    resolved_outdir = _resolve_outdir(file, out)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")

    text, resolved_instance = _read_model_and_instance(
        file=file, instance=instance, console=console
    )
    if text is None or resolved_instance is None:
        raise typer.Exit(code=1)

    unit = build_for_target(
        text,
        options=CompileOptions(
            filename=str(file),
            instance_path=str(resolved_instance),
            outdir=str(resolved_outdir),
            output_format=output_format,
            runtime_id=runtime,
            plugin_specs=tuple(plugin),
        ),
    )
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    report_path: Path | None = None
    if unit.support_report is not None:
        report_path = _write_capability_report(
            resolved_outdir, support_report_to_dict(unit.support_report)
        )

    if has_errors or unit.artifacts is None:
        raise typer.Exit(code=1)

    table = Table(title="Build Artifacts")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Runtime", unit.target_selection.runtime_id if unit.target_selection else "")
    table.add_row("Backend", unit.target_selection.backend_id if unit.target_selection else "")
    table.add_row("CQM", unit.artifacts.cqm_path or "")
    table.add_row("BQM", unit.artifacts.bqm_path or "")
    table.add_row("Format", unit.artifacts.format_path or "")
    table.add_row("VarMap", unit.artifacts.varmap_path or "")
    table.add_row("Explain", unit.artifacts.explain_path or "")
    table.add_row("Capability Report", str(report_path) if report_path is not None else "")
    for key, value in sorted(unit.artifacts.stats.items()):
        table.add_row(key, str(value))
    console.print(table)


@app.command("solve", help="Compile, run, and export solve results for model+instance.")
def solve_cmd(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    instance: Path | None = typer.Option(
        None,
        "--instance",
        "-i",
        help="Path to instance JSON. Defaults to <model>.instance.json when available.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output directory for artifacts and run output. Defaults to <cwd>/outdir/<model_stem>.",
    ),
    output_format: str = typer.Option(
        "qubo",
        "--format",
        "-f",
        help="Export format for objective payload: qubo, ising, bqm, or cqm.",
    ),
    runtime: str | None = typer.Option(None, "--runtime", "-u", help="Runtime plugin identifier."),
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        "-p",
        help="Load an extra plugin bundle from module:attribute.",
    ),
    runtime_option: list[str] = typer.Option(
        [],
        "--runtime-option",
        "-x",
        help="Runtime option as key=value (repeatable).",
    ),
    runtime_options_file: Path | None = typer.Option(
        None,
        "--runtime-options-file",
        "-X",
        help="JSON object file containing runtime options.",
    ),
    solutions: int = typer.Option(
        1,
        "--solutions",
        help="Number of best unique solutions to return (default: 1).",
    ),
    energy_min: float | None = typer.Option(
        None,
        "--energy-min",
        help="Inclusive minimum energy threshold for returned solutions.",
    ),
    energy_max: float | None = typer.Option(
        None,
        "--energy-max",
        help="Inclusive maximum energy threshold for returned solutions.",
    ),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI color output."),
    log_level: LogLevel = typer.Option(
        LogLevel.warning,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    resolved_outdir = _resolve_outdir(file, out)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")

    text, resolved_instance = _read_model_and_instance(
        file=file, instance=instance, console=console
    )
    if text is None or resolved_instance is None:
        raise typer.Exit(code=1) from None

    runtime_params, runtime_options_error = _parse_runtime_options(
        runtime_option_args=runtime_option,
        runtime_options_file=runtime_options_file,
    )
    if runtime_options_error is not None or runtime_params is None:
        _print_diags(
            console,
            None,
            [
                _diag(
                    file,
                    code="QSOL4001",
                    message="invalid runtime options",
                    notes=[runtime_options_error or "unknown runtime options error"],
                )
            ],
        )
        raise typer.Exit(code=1) from None

    if solutions < 1:
        _print_diags(
            console,
            None,
            [
                _diag(
                    file,
                    code="QSOL4001",
                    message="invalid solve options",
                    notes=["`--solutions` must be >= 1"],
                )
            ],
        )
        raise typer.Exit(code=1) from None

    if energy_min is not None and energy_max is not None and energy_min > energy_max:
        _print_diags(
            console,
            None,
            [
                _diag(
                    file,
                    code="QSOL4001",
                    message="invalid solve options",
                    notes=["`--energy-min` must be <= `--energy-max`"],
                )
            ],
        )
        raise typer.Exit(code=1) from None

    runtime_params["solutions"] = solutions
    if energy_min is not None:
        runtime_params["energy_min"] = energy_min
    if energy_max is not None:
        runtime_params["energy_max"] = energy_max

    unit, run_result = run_for_target(
        text,
        options=CompileOptions(
            filename=str(file),
            instance_path=str(resolved_instance),
            outdir=str(resolved_outdir),
            output_format=output_format,
            runtime_id=runtime,
            plugin_specs=tuple(plugin),
        ),
        run_options=RuntimeRunOptions(params=runtime_params, outdir=str(resolved_outdir)),
    )
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    report_path: Path | None = None
    if unit.support_report is not None:
        report_path = _write_capability_report(
            resolved_outdir, support_report_to_dict(unit.support_report)
        )

    if has_errors or run_result is None:
        raise typer.Exit(code=1)

    if report_path is not None:
        run_result.capability_report_path = str(report_path)

    run_path = _write_run_output(outdir=resolved_outdir, run_result=run_result)
    feature_requested = solutions > 1 or energy_min is not None or energy_max is not None
    solutions_payload = run_result.extensions.get("solutions")
    if feature_requested and not isinstance(solutions_payload, list):
        _print_diags(
            console,
            None,
            [
                _diag(
                    file,
                    code="QSOL5002",
                    message="runtime did not return required multi-solution payload",
                    notes=[
                        "requested solve features require `extensions.solutions` in run output",
                        f"run output was written to: {run_path}",
                    ],
                )
            ],
        )
        raise typer.Exit(code=1)

    requested_solutions = run_result.extensions.get("requested_solutions", solutions)
    returned_solutions = run_result.extensions.get("returned_solutions", 1)
    threshold_payload = run_result.extensions.get("energy_threshold")
    threshold_min = ""
    threshold_max = ""
    threshold_passed = ""
    if isinstance(threshold_payload, dict):
        threshold_min = str(threshold_payload.get("min", ""))
        threshold_max = str(threshold_payload.get("max", ""))
        threshold_passed = str(threshold_payload.get("passed", ""))

    summary = Table(title="Run Summary")
    summary.add_column("Key")
    summary.add_column("Value")
    summary.add_row("Status", run_result.status)
    summary.add_row("Runtime", run_result.runtime)
    summary.add_row("Backend", run_result.backend)
    summary.add_row("Sampler", str(run_result.extensions.get("sampler", "")))
    summary.add_row("Energy", str(run_result.energy))
    summary.add_row("Reads", str(run_result.reads))
    summary.add_row("Solutions Requested", str(requested_solutions))
    summary.add_row("Solutions Returned", str(returned_solutions))
    summary.add_row("Energy Min", threshold_min)
    summary.add_row("Energy Max", threshold_max)
    summary.add_row("Energy Threshold Passed", threshold_passed)
    summary.add_row("Timing (ms)", f"{run_result.timing_ms:.3f}")
    summary.add_row("Run Output", str(run_path))
    summary.add_row("Capability Report", str(report_path) if report_path is not None else "")
    console.print(summary)

    selected = Table(title="Selected Assignments")
    selected.add_column("Variable")
    selected.add_column("Meaning")
    if run_result.selected_assignments:
        for row in run_result.selected_assignments:
            selected.add_row(
                escape(str(row.get("variable", ""))),
                escape(str(row.get("meaning", ""))),
            )
    else:
        selected.add_row("-", "No (non-aux) binary variable set to 1 in the best sample")
    console.print(selected)

    if run_result.status != "ok":
        _print_diags(
            console,
            None,
            [
                _diag(
                    file,
                    code="QSOL5002",
                    message="runtime policy rejected solve output",
                    notes=[f"status={run_result.status}", f"run output: {run_path}"],
                )
            ],
        )
        raise typer.Exit(code=1)


# Command aliases
inspect_app.command("p", help="Alias for `inspect parse`.")(inspect_parse)
inspect_app.command("c", help="Alias for `inspect check`.")(inspect_check)
inspect_app.command("l", help="Alias for `inspect lower`.")(inspect_lower)
targets_app.command("ls", help="Alias for `targets list`.")(targets_list)
targets_app.command("caps", help="Alias for `targets capabilities`.")(targets_capabilities)
targets_app.command("chk", help="Alias for `targets check`.")(targets_check)
app.command("b", help="Alias for `build`.")(build_cmd)
app.command("s", help="Alias for `solve`.")(solve_cmd)


if __name__ == "__main__":
    app()
