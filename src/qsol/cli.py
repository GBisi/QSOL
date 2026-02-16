from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable, Mapping, cast

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
from qsol.config import (
    CombineMode,
    FailurePolicy,
    QsolConfig,
    load_config,
    materialize_instance_payload,
    resolve_combine_mode,
    resolve_failure_policy,
    resolve_output_format,
    resolve_runtime_options,
    resolve_selected_scenarios,
    resolve_solve_settings,
)
from qsol.diag.cli_diagnostics import (
    ambiguous_config_file,
    config_load_error,
    file_read_error,
    missing_config_file,
)
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
    try:
        qsol_version = version("qsol")
    except Exception:
        qsol_version = "unknown"

    console.print(
        Panel(
            (
                f"[bold cyan]Welcome to QSOL v{qsol_version}[/bold cyan]\n\n"
                "[white]The Quantum SOlver Language (QSOL) compiler and runtime environment.\n"
                "Compile declarative models to CQM IR, check target support, and execute on pluggable runtimes.[/white]"
            ),
            title="[bold green]QSOL CLI[/bold green]",
            border_style="bright_blue",
            expand=False,
        )
    )

    quickstart = Table(
        title="Quick Start", show_header=True, header_style="bold magenta", expand=True
    )
    quickstart.add_column("Workflow", style="bold yellow", ratio=1)
    quickstart.add_column("Command", style="green", ratio=2)
    quickstart.add_row(
        "Inspect frontend parse",
        "qsol inspect parse model.qsol --json",
    )
    quickstart.add_row(
        "Check target compatibility",
        "qsol targets check model.qsol -c model.qsol.toml --runtime local-dimod",
    )
    quickstart.add_row(
        "Build artifacts",
        "qsol build model.qsol -c model.qsol.toml --runtime local-dimod -o outdir/model",
    )
    quickstart.add_row(
        "Solve",
        "qsol solve model.qsol -c model.qsol.toml --runtime local-dimod",
    )
    console.print(quickstart)
    console.print("[dim]Use `qsol --help` for full command documentation.[/dim]")


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


def _solution_entries(run_result: StandardRunResult) -> list[Mapping[str, object]]:
    raw_solutions = run_result.extensions.get("solutions")
    if not isinstance(raw_solutions, list):
        return []
    return [cast(Mapping[str, object], row) for row in raw_solutions if isinstance(row, Mapping)]


def _format_solution_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        normalized = {str(key): value_raw for key, value_raw in value.items()}
        return json.dumps(normalized, sort_keys=True, default=str)
    return str(value)


def _format_selected_assignments(value: object) -> str:
    if not isinstance(value, list):
        return ""

    count = 0
    for row in value:
        if isinstance(row, Mapping):
            count += 1
    if count == 0:
        count = len(value)
    return f"{count} selected"


def _format_sample_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return str(value) if value is not None else ""

    items = sorted(
        ((str(name), raw_value) for name, raw_value in value.items()), key=lambda item: item[0]
    )
    if not items:
        return "0/0 active"

    active_names = [
        name
        for name, raw_value in items
        if (isinstance(raw_value, bool) and raw_value)
        or (isinstance(raw_value, int) and raw_value == 1)
    ]
    header = f"{len(active_names)}/{len(items)} active"
    if not active_names:
        return header
    if len(active_names) <= 3:
        return f"{header}: {', '.join(active_names)}"
    return f"{header}: {', '.join(active_names[:3])} (+{len(active_names) - 3} more)"


def _format_runtime_parameter_value(value: object) -> str:
    if isinstance(value, Mapping):
        normalized = {str(key): raw for key, raw in value.items()}
        return json.dumps(normalized, sort_keys=True, default=str)
    if isinstance(value, list):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _runtime_parameters_summary(run_result: StandardRunResult) -> str:
    runtime_options_raw = run_result.extensions.get("runtime_options")
    if isinstance(runtime_options_raw, Mapping):
        runtime_options = {str(key): value for key, value in runtime_options_raw.items()}
        if runtime_options:
            return "\n".join(
                f"{key}={_format_runtime_parameter_value(runtime_options[key])}"
                for key in sorted(runtime_options)
            )

    scenario_options_raw = run_result.extensions.get("scenario_runtime_options")
    if isinstance(scenario_options_raw, Mapping):
        scenario_lines: list[str] = []
        for scenario_name in sorted(str(name) for name in scenario_options_raw.keys()):
            params_raw = scenario_options_raw.get(scenario_name)
            if not isinstance(params_raw, Mapping):
                continue
            params = {str(key): value for key, value in params_raw.items()}
            if params:
                joined = ", ".join(
                    f"{key}={_format_runtime_parameter_value(params[key])}"
                    for key in sorted(params)
                )
            else:
                joined = "<none>"
            scenario_lines.append(f"{scenario_name}: {joined}")
        if scenario_lines:
            return "\n".join(scenario_lines)

    return ""


def _print_diags(
    console: Console, source: SourceText | None, diagnostics: list[Diagnostic]
) -> bool:
    reporter = DiagnosticReporter(console=console)
    if diagnostics:
        reporter.print(source, diagnostics)
    return any(d.is_error for d in diagnostics)


def _resolve_config_path(file: Path, config: Path | None) -> tuple[Path | None, Diagnostic | None]:
    if config is not None:
        return config, None

    inferred_config = file.with_suffix(".qsol.toml")
    candidates = sorted(file.parent.glob("*.qsol.toml"))
    if not candidates:
        return None, missing_config_file(inferred_config, model_path=file)
    if len(candidates) == 1:
        LOGGER.info("Inferred config file: %s", candidates[0])
        return candidates[0], None
    if inferred_config in candidates:
        LOGGER.info("Inferred same-name config file: %s", inferred_config)
        return inferred_config, None
    return None, ambiguous_config_file(
        model_path=file, expected_path=inferred_config, candidates=candidates
    )


def _resolve_outdir(file: Path, outdir: Path | None, config: QsolConfig | None = None) -> Path:
    if outdir is not None:
        return outdir

    if config is not None and config.entrypoint.out is not None:
        entrypoint_outdir = Path(config.entrypoint.out)
        LOGGER.info("Using config entrypoint output directory: %s", entrypoint_outdir)
        return entrypoint_outdir

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
        LogLevel.warning,
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
        LogLevel.warning,
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
        LogLevel.warning,
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


def _read_model_and_config(
    *,
    file: Path,
    config: Path | None,
    console: Console,
) -> tuple[str | None, Path | None, QsolConfig | None]:
    try:
        text = _read_file(file)
    except OSError as exc:
        _print_diags(console, None, [file_read_error(file, exc)])
        return None, None, None

    resolved_config, config_diag = _resolve_config_path(file, config)
    if config_diag is not None or resolved_config is None:
        _print_diags(
            console, None, [config_diag or _diag(file, code="QSOL4002", message="missing config")]
        )
        return None, None, None

    try:
        parsed_config = load_config(resolved_config)
    except Exception as exc:
        _print_diags(console, None, [config_load_error(resolved_config, exc)])
        return None, None, None

    return text, resolved_config, parsed_config


def _scenario_outdir(*, outdir: Path, scenario_name: str, multi_scenario: bool) -> Path:
    if not multi_scenario:
        return outdir
    return outdir / "scenarios" / scenario_name


def _write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(slots=True)
class _ScenarioOutcome:
    scenario: str
    success: bool
    status: str
    runtime: str | None = None
    backend: str | None = None
    report_path: Path | None = None
    run_path: Path | None = None
    run_result: StandardRunResult | None = None
    requested_solutions: int = 1


def _command_success(
    *,
    failure_policy: FailurePolicy,
    successes: int,
    failures: int,
) -> bool:
    if failure_policy is FailurePolicy.best_effort:
        return successes > 0
    return failures == 0


def _merge_multi_scenario_solutions(
    *,
    successful_outcomes: list[_ScenarioOutcome],
    combine_mode: CombineMode,
    requested_solutions: int,
) -> list[dict[str, object]]:
    per_scenario: dict[str, dict[tuple[tuple[str, int], ...], Mapping[str, object]]] = {}

    for outcome in successful_outcomes:
        assert outcome.run_result is not None
        raw_solutions = outcome.run_result.extensions.get("solutions")
        if not isinstance(raw_solutions, list):
            raise ValueError(
                f"scenario `{outcome.scenario}` did not return `extensions.solutions` payload"
            )

        scenario_map: dict[tuple[tuple[str, int], ...], Mapping[str, object]] = {}
        for solution_raw in raw_solutions:
            if not isinstance(solution_raw, Mapping):
                raise ValueError(f"scenario `{outcome.scenario}` returned malformed solution entry")
            signature, normalized_sample = _solution_signature(
                solution_raw, scenario_name=outcome.scenario
            )
            normalized_solution = dict(solution_raw)
            normalized_solution["sample"] = normalized_sample
            scenario_map[signature] = normalized_solution

        per_scenario[outcome.scenario] = scenario_map

    if not per_scenario:
        return []

    signature_sets = [set(values.keys()) for values in per_scenario.values()]
    if combine_mode is CombineMode.intersection:
        signatures = set.intersection(*signature_sets)
    else:
        signatures = set.union(*signature_sets)

    rows: list[
        tuple[
            float,
            tuple[tuple[str, int], ...],
            dict[str, int],
            list[dict[str, object]],
            dict[str, float],
        ]
    ] = []
    for signature in signatures:
        scenario_energies: dict[str, float] = {}
        selected_assignments: list[dict[str, object]] = []
        for scenario_name, solution_map in per_scenario.items():
            solution = solution_map.get(signature)
            if solution is None:
                continue

            energy_raw = solution.get("energy")
            if isinstance(energy_raw, bool) or not isinstance(energy_raw, (int, float)):
                raise ValueError(f"scenario `{scenario_name}` has non-numeric solution energy")
            scenario_energies[scenario_name] = float(energy_raw)
            if not selected_assignments:
                selected_raw = solution.get("selected_assignments", [])
                if isinstance(selected_raw, list):
                    selected_assignments = list(cast(list[dict[str, object]], selected_raw))

        if not scenario_energies:
            continue

        worst_case = max(scenario_energies.values())
        rows.append(
            (
                worst_case,
                signature,
                {name: value for name, value in signature},
                selected_assignments,
                scenario_energies,
            )
        )

    rows.sort(key=lambda row: (row[0], row[1]))
    merged: list[dict[str, object]] = []
    for rank, (energy, _signature, sample, selected_assignments, scenario_energies) in enumerate(
        rows, start=1
    ):
        merged.append(
            {
                "rank": rank,
                "energy": energy,
                "sample": sample,
                "selected_assignments": selected_assignments,
                "scenario_energies": scenario_energies,
                "scenario_count": len(scenario_energies),
            }
        )
        if len(merged) >= requested_solutions:
            break
    return merged


def _solution_signature(
    solution: Mapping[str, object],
    *,
    scenario_name: str,
) -> tuple[tuple[tuple[str, int], ...], dict[str, int]]:
    sample_raw = solution.get("sample")
    if not isinstance(sample_raw, Mapping):
        raise ValueError(f"scenario `{scenario_name}` solution is missing mapping `sample` field")

    normalized_sample: dict[str, int] = {}
    for key, value in sample_raw.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"scenario `{scenario_name}` solution contains non-integer sample value"
            )
        normalized_sample[str(key)] = int(value)
    signature = tuple(sorted(normalized_sample.items(), key=lambda item: item[0]))
    return signature, normalized_sample


def _build_multi_scenario_run_result(
    *,
    outcomes: list[_ScenarioOutcome],
    selected_scenarios: list[str],
    combine_mode: CombineMode,
    failure_policy: FailurePolicy,
    command_ok: bool,
) -> StandardRunResult:
    successful = [
        outcome for outcome in outcomes if outcome.success and outcome.run_result is not None
    ]
    if not successful:
        return StandardRunResult(
            schema_version="1.0",
            runtime="<unresolved>",
            backend="<unresolved>",
            status="ok" if command_ok else "scenario_failed",
            energy=None,
            reads=0,
            best_sample={},
            selected_assignments=[],
            timing_ms=0.0,
            capability_report_path="",
            extensions={
                "selected_scenarios": selected_scenarios,
                "combine_mode": combine_mode.value,
                "failure_policy": failure_policy.value,
                "requested_solutions": 0,
                "returned_solutions": 0,
                "solutions": [],
                "scenario_results": {
                    outcome.scenario: {
                        "status": outcome.status,
                        "runtime": outcome.runtime,
                        "backend": outcome.backend,
                        "run_path": str(outcome.run_path) if outcome.run_path else None,
                        "energy": outcome.run_result.energy if outcome.run_result else None,
                    }
                    for outcome in outcomes
                },
            },
        )

    runtime = cast(StandardRunResult, successful[0].run_result).runtime
    backend = cast(StandardRunResult, successful[0].run_result).backend
    requested_solutions = max(outcome.requested_solutions for outcome in successful)
    merged_solutions = _merge_multi_scenario_solutions(
        successful_outcomes=successful,
        combine_mode=combine_mode,
        requested_solutions=requested_solutions,
    )

    first = merged_solutions[0] if merged_solutions else None
    energy = None if first is None else cast(float, first.get("energy"))
    best_sample: dict[str, int] = {}
    selected_assignments: list[dict[str, object]] = []
    if first is not None:
        sample_raw = first.get("sample")
        if isinstance(sample_raw, Mapping):
            best_sample = {str(k): int(v) for k, v in sample_raw.items() if isinstance(v, int)}
        selected_raw = first.get("selected_assignments")
        if isinstance(selected_raw, list):
            selected_assignments = list(cast(list[dict[str, object]], selected_raw))

    total_reads = 0
    total_timing_ms = 0.0
    scenario_runtime_options: dict[str, dict[str, object]] = {}
    for outcome in successful:
        assert outcome.run_result is not None
        total_reads += outcome.run_result.reads
        total_timing_ms += outcome.run_result.timing_ms
        runtime_options_raw = outcome.run_result.extensions.get("runtime_options")
        if isinstance(runtime_options_raw, Mapping):
            scenario_runtime_options[outcome.scenario] = {
                str(key): value for key, value in runtime_options_raw.items()
            }

    shared_runtime_options: dict[str, object] = {}
    if scenario_runtime_options:
        ordered_options = [
            scenario_runtime_options[scenario_name]
            for scenario_name in sorted(scenario_runtime_options)
        ]
        first_options = ordered_options[0]
        if all(candidate == first_options for candidate in ordered_options[1:]):
            shared_runtime_options = dict(first_options)

    return StandardRunResult(
        schema_version="1.0",
        runtime=runtime,
        backend=backend,
        status="ok" if command_ok else "scenario_failed",
        energy=energy,
        reads=total_reads,
        best_sample=best_sample,
        selected_assignments=selected_assignments,
        timing_ms=total_timing_ms,
        capability_report_path="",
        extensions={
            "selected_scenarios": selected_scenarios,
            "combine_mode": combine_mode.value,
            "failure_policy": failure_policy.value,
            "requested_solutions": requested_solutions,
            "returned_solutions": len(merged_solutions),
            "solutions": merged_solutions,
            "scenario_results": {
                outcome.scenario: {
                    "status": outcome.status,
                    "runtime": outcome.runtime,
                    "backend": outcome.backend,
                    "run_path": str(outcome.run_path) if outcome.run_path else None,
                    "energy": outcome.run_result.energy if outcome.run_result else None,
                }
                for outcome in outcomes
            },
            "runtime_options": shared_runtime_options,
            "scenario_runtime_options": scenario_runtime_options,
        },
    )


@targets_app.command("check", help="Check model+scenario support for a selected target pair.")
def targets_check(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config TOML. Defaults to discovered <model>.qsol.toml when available.",
    ),
    scenario: list[str] = typer.Option(
        [],
        "--scenario",
        help="Scenario name to execute (repeatable).",
    ),
    all_scenarios: bool = typer.Option(
        False,
        "--all-scenarios",
        help="Execute all scenarios declared in the config.",
    ),
    failure_policy: FailurePolicy | None = typer.Option(
        None,
        "--failure-policy",
        help="Scenario failure policy: run-all-fail, fail-fast, or best-effort.",
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
        LogLevel.warning,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    text, _resolved_config_path, parsed_config = _read_model_and_config(
        file=file, config=config, console=console
    )
    if text is None or parsed_config is None:
        raise typer.Exit(code=1)
    resolved_outdir = _resolve_outdir(file, out, parsed_config)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")

    try:
        selected_scenarios = resolve_selected_scenarios(
            config=parsed_config,
            cli_scenarios=scenario,
            cli_all_scenarios=all_scenarios,
        )
        resolved_failure_policy = resolve_failure_policy(
            config=parsed_config, cli_policy=failure_policy
        )
    except ValueError as exc:
        _print_diags(
            console,
            None,
            [_diag(file, code="QSOL4001", message="invalid scenario selection", notes=[str(exc)])],
        )
        raise typer.Exit(code=1) from None

    source = SourceText(text, str(file))
    multi_scenario = len(selected_scenarios) > 1
    outcomes: list[_ScenarioOutcome] = []
    for scenario_name in selected_scenarios:
        scenario_outdir = _scenario_outdir(
            outdir=resolved_outdir,
            scenario_name=scenario_name,
            multi_scenario=multi_scenario,
        )
        instance_payload = materialize_instance_payload(
            config=parsed_config, scenario_name=scenario_name
        )
        unit = check_target_support(
            text,
            options=CompileOptions(
                filename=str(file),
                instance_payload=instance_payload,
                runtime_id=runtime,
                plugin_specs=tuple(plugin),
            ),
        )
        has_errors = _print_diags(console, source, unit.diagnostics)
        report_path: Path | None = None
        if unit.support_report is not None:
            report_path = _write_capability_report(
                scenario_outdir, support_report_to_dict(unit.support_report)
            )

        success = not has_errors and bool(unit.support_report and unit.support_report.supported)
        outcomes.append(
            _ScenarioOutcome(
                scenario=scenario_name,
                success=success,
                status="ok" if success else "failed",
                runtime=(
                    unit.target_selection.runtime_id
                    if unit.target_selection is not None
                    else runtime or "<unresolved>"
                ),
                backend=(
                    unit.target_selection.backend_id
                    if unit.target_selection is not None
                    else DEFAULT_BACKEND_ID
                ),
                report_path=report_path,
            )
        )

        if multi_scenario:
            scenario_summary = Table(title=f"Target Support ({scenario_name})")
            scenario_summary.add_column("Key")
            scenario_summary.add_column("Value")
            scenario_summary.add_row("Supported", "yes" if success else "no")
            scenario_summary.add_row("Runtime", outcomes[-1].runtime or "")
            scenario_summary.add_row("Backend", outcomes[-1].backend or "")
            scenario_summary.add_row(
                "Capability Report",
                str(report_path) if report_path is not None else "<not-written>",
            )
            console.print(scenario_summary)

        if not success and resolved_failure_policy is FailurePolicy.fail_fast:
            break

    successes = sum(1 for outcome in outcomes if outcome.success)
    failures = len(outcomes) - successes
    command_ok = _command_success(
        failure_policy=resolved_failure_policy,
        successes=successes,
        failures=failures,
    )

    if multi_scenario:
        aggregate_payload: dict[str, object] = {
            "schema_version": "1",
            "mode": "multi-scenario",
            "selected_scenarios": selected_scenarios,
            "failure_policy": resolved_failure_policy.value,
            "supported": command_ok,
            "scenarios": {
                outcome.scenario: {
                    "supported": outcome.success,
                    "runtime": outcome.runtime,
                    "backend": outcome.backend,
                    "report_path": str(outcome.report_path) if outcome.report_path else None,
                }
                for outcome in outcomes
            },
        }
        _write_json_file(resolved_outdir / "capability_report.json", aggregate_payload)

        summary = Table(title="Target Support (Scenarios)")
        summary.add_column("Key")
        summary.add_column("Value")
        summary.add_row("Failure Policy", resolved_failure_policy.value)
        summary.add_row("Scenarios Requested", str(len(selected_scenarios)))
        summary.add_row("Scenarios Executed", str(len(outcomes)))
        summary.add_row("Scenarios Succeeded", str(successes))
        summary.add_row("Scenarios Failed", str(failures))
        summary.add_row("Aggregate Supported", "yes" if command_ok else "no")
        summary.add_row("Capability Report", str(resolved_outdir / "capability_report.json"))
        console.print(summary)
    else:
        outcome = outcomes[0]
        summary = Table(title="Target Support")
        summary.add_column("Key")
        summary.add_column("Value")
        summary.add_row("Scenario", outcome.scenario)
        summary.add_row("Supported", "yes" if outcome.success else "no")
        summary.add_row("Runtime", outcome.runtime or "")
        summary.add_row("Backend", outcome.backend or "")
        summary.add_row(
            "Capability Report",
            str(outcome.report_path) if outcome.report_path is not None else "<not-written>",
        )
        console.print(summary)

    if not command_ok:
        raise typer.Exit(code=1)


@app.command("build", help="Compile model+scenario and export backend artifacts.")
def build_cmd(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config TOML. Defaults to discovered <model>.qsol.toml when available.",
    ),
    scenario: list[str] = typer.Option(
        [],
        "--scenario",
        help="Scenario name to execute (repeatable).",
    ),
    all_scenarios: bool = typer.Option(
        False,
        "--all-scenarios",
        help="Execute all scenarios declared in the config.",
    ),
    failure_policy: FailurePolicy | None = typer.Option(
        None,
        "--failure-policy",
        help="Scenario failure policy: run-all-fail, fail-fast, or best-effort.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output directory for artifacts. Defaults to <cwd>/outdir/<model_stem>.",
    ),
    output_format: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Export format for objective payload: qubo, ising, bqm, or cqm (defaults to config entrypoint, then qubo).",
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
        LogLevel.warning,
        "--log-level",
        "-l",
        help="Set CLI log verbosity.",
    ),
) -> None:
    console = Console(no_color=no_color)
    text, _resolved_config_path, parsed_config = _read_model_and_config(
        file=file, config=config, console=console
    )
    if text is None or parsed_config is None:
        raise typer.Exit(code=1)
    resolved_outdir = _resolve_outdir(file, out, parsed_config)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")
    resolved_output_format = resolve_output_format(config=parsed_config, cli_format=output_format)

    try:
        selected_scenarios = resolve_selected_scenarios(
            config=parsed_config,
            cli_scenarios=scenario,
            cli_all_scenarios=all_scenarios,
        )
        resolved_failure_policy = resolve_failure_policy(
            config=parsed_config, cli_policy=failure_policy
        )
    except ValueError as exc:
        _print_diags(
            console,
            None,
            [_diag(file, code="QSOL4001", message="invalid scenario selection", notes=[str(exc)])],
        )
        raise typer.Exit(code=1) from None

    source = SourceText(text, str(file))
    multi_scenario = len(selected_scenarios) > 1
    outcomes: list[_ScenarioOutcome] = []
    artifact_summaries: dict[str, dict[str, object]] = {}

    for scenario_name in selected_scenarios:
        scenario_outdir = _scenario_outdir(
            outdir=resolved_outdir,
            scenario_name=scenario_name,
            multi_scenario=multi_scenario,
        )
        instance_payload = materialize_instance_payload(
            config=parsed_config, scenario_name=scenario_name
        )
        unit = build_for_target(
            text,
            options=CompileOptions(
                filename=str(file),
                instance_payload=instance_payload,
                outdir=str(scenario_outdir),
                output_format=resolved_output_format,
                runtime_id=runtime,
                plugin_specs=tuple(plugin),
            ),
        )
        has_errors = _print_diags(console, source, unit.diagnostics)

        report_path: Path | None = None
        if unit.support_report is not None:
            report_path = _write_capability_report(
                scenario_outdir, support_report_to_dict(unit.support_report)
            )

        success = not has_errors and unit.artifacts is not None
        outcomes.append(
            _ScenarioOutcome(
                scenario=scenario_name,
                success=success,
                status="ok" if success else "failed",
                runtime=unit.target_selection.runtime_id if unit.target_selection else None,
                backend=unit.target_selection.backend_id if unit.target_selection else None,
                report_path=report_path,
            )
        )
        if unit.artifacts is not None:
            artifact_summaries[scenario_name] = {
                "cqm": unit.artifacts.cqm_path,
                "bqm": unit.artifacts.bqm_path,
                "format": unit.artifacts.format_path,
                "varmap": unit.artifacts.varmap_path,
                "explain": unit.artifacts.explain_path,
                "stats": dict(unit.artifacts.stats),
            }

        if multi_scenario:
            scenario_table = Table(title=f"Build Artifacts ({scenario_name})")
            scenario_table.add_column("Key")
            scenario_table.add_column("Value")
            scenario_table.add_row("Status", "ok" if success else "failed")
            scenario_table.add_row("Runtime", outcomes[-1].runtime or "")
            scenario_table.add_row("Backend", outcomes[-1].backend or "")
            if unit.artifacts is not None:
                scenario_table.add_row("CQM", unit.artifacts.cqm_path or "")
                scenario_table.add_row("BQM", unit.artifacts.bqm_path or "")
                scenario_table.add_row("Format", unit.artifacts.format_path or "")
                scenario_table.add_row("VarMap", unit.artifacts.varmap_path or "")
                scenario_table.add_row("Explain", unit.artifacts.explain_path or "")
            scenario_table.add_row(
                "Capability Report",
                str(report_path) if report_path is not None else "<not-written>",
            )
            console.print(scenario_table)

        if not success and resolved_failure_policy is FailurePolicy.fail_fast:
            break

    successes = sum(1 for outcome in outcomes if outcome.success)
    failures = len(outcomes) - successes
    command_ok = _command_success(
        failure_policy=resolved_failure_policy,
        successes=successes,
        failures=failures,
    )

    if multi_scenario:
        aggregate_path = resolved_outdir / "build_summary.json"
        aggregate_payload: dict[str, object] = {
            "schema_version": "1",
            "mode": "multi-scenario",
            "selected_scenarios": selected_scenarios,
            "failure_policy": resolved_failure_policy.value,
            "status": "ok" if command_ok else "failed",
            "scenarios": {
                outcome.scenario: {
                    "status": outcome.status,
                    "runtime": outcome.runtime,
                    "backend": outcome.backend,
                    "report_path": str(outcome.report_path) if outcome.report_path else None,
                    "artifacts": artifact_summaries.get(outcome.scenario),
                }
                for outcome in outcomes
            },
        }
        _write_json_file(aggregate_path, aggregate_payload)

        summary = Table(title="Build Summary (Scenarios)")
        summary.add_column("Key")
        summary.add_column("Value")
        summary.add_row("Failure Policy", resolved_failure_policy.value)
        summary.add_row("Scenarios Requested", str(len(selected_scenarios)))
        summary.add_row("Scenarios Executed", str(len(outcomes)))
        summary.add_row("Scenarios Succeeded", str(successes))
        summary.add_row("Scenarios Failed", str(failures))
        summary.add_row("Summary File", str(aggregate_path))
        console.print(summary)
    else:
        outcome = outcomes[0]
        if outcome.scenario in artifact_summaries:
            artifacts = artifact_summaries[outcome.scenario]
            table = Table(title="Build Artifacts")
            table.add_column("Key")
            table.add_column("Value")
            table.add_row("Scenario", outcome.scenario)
            table.add_row("Runtime", outcome.runtime or "")
            table.add_row("Backend", outcome.backend or "")
            table.add_row("CQM", str(artifacts.get("cqm") or ""))
            table.add_row("BQM", str(artifacts.get("bqm") or ""))
            table.add_row("Format", str(artifacts.get("format") or ""))
            table.add_row("VarMap", str(artifacts.get("varmap") or ""))
            table.add_row("Explain", str(artifacts.get("explain") or ""))
            table.add_row(
                "Capability Report",
                str(outcome.report_path) if outcome.report_path is not None else "",
            )
            for key, value in sorted(cast(dict[str, object], artifacts.get("stats", {})).items()):
                table.add_row(key, str(value))
            console.print(table)

    if not command_ok:
        raise typer.Exit(code=1)


@app.command("solve", help="Compile, run, and export solve results for model+scenario.")
def solve_cmd(
    file: Path = typer.Argument(..., help="Path to the QSOL model source file."),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config TOML. Defaults to discovered <model>.qsol.toml when available.",
    ),
    scenario: list[str] = typer.Option(
        [],
        "--scenario",
        help="Scenario name to execute (repeatable).",
    ),
    all_scenarios: bool = typer.Option(
        False,
        "--all-scenarios",
        help="Execute all scenarios declared in the config.",
    ),
    combine_mode: CombineMode | None = typer.Option(
        None,
        "--combine-mode",
        help="Merge mode for multi-scenario solve: intersection or union.",
    ),
    failure_policy: FailurePolicy | None = typer.Option(
        None,
        "--failure-policy",
        help="Scenario failure policy: run-all-fail, fail-fast, or best-effort.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output directory for artifacts and run output. Defaults to <cwd>/outdir/<model_stem>.",
    ),
    output_format: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Export format for objective payload: qubo, ising, bqm, or cqm (defaults to config entrypoint, then qubo).",
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
    solutions: int | None = typer.Option(
        None,
        "--solutions",
        help="Number of best unique solutions to return (defaults to config, then 1).",
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
    text, _resolved_config_path, parsed_config = _read_model_and_config(
        file=file, config=config, console=console
    )
    if text is None or parsed_config is None:
        raise typer.Exit(code=1) from None
    resolved_outdir = _resolve_outdir(file, out, parsed_config)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")
    resolved_output_format = resolve_output_format(config=parsed_config, cli_format=output_format)

    cli_runtime_params, runtime_options_error = _parse_runtime_options(
        runtime_option_args=runtime_option,
        runtime_options_file=runtime_options_file,
    )
    if runtime_options_error is not None or cli_runtime_params is None:
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

    runtime_params_base = resolve_runtime_options(
        config=parsed_config,
        cli_runtime_options=cli_runtime_params,
    )

    if solutions is not None and solutions < 1:
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

    try:
        selected_scenarios = resolve_selected_scenarios(
            config=parsed_config,
            cli_scenarios=scenario,
            cli_all_scenarios=all_scenarios,
        )
        resolved_combine_mode = resolve_combine_mode(config=parsed_config, cli_mode=combine_mode)
        resolved_failure_policy = resolve_failure_policy(
            config=parsed_config, cli_policy=failure_policy
        )
    except ValueError as exc:
        _print_diags(
            console,
            None,
            [_diag(file, code="QSOL4001", message="invalid scenario selection", notes=[str(exc)])],
        )
        raise typer.Exit(code=1) from None

    source = SourceText(text, str(file))
    multi_scenario = len(selected_scenarios) > 1
    expected_pair: tuple[str, str] | None = None
    outcomes: list[_ScenarioOutcome] = []

    for scenario_name in selected_scenarios:
        scenario_outdir = _scenario_outdir(
            outdir=resolved_outdir,
            scenario_name=scenario_name,
            multi_scenario=multi_scenario,
        )
        try:
            solve_settings = resolve_solve_settings(
                config=parsed_config,
                scenario_name=scenario_name,
                cli_solutions=solutions,
                cli_energy_min=energy_min,
                cli_energy_max=energy_max,
            )
        except ValueError as exc:
            _print_diags(
                console,
                None,
                [
                    _diag(
                        file,
                        code="QSOL4001",
                        message="invalid solve options",
                        notes=[f"scenario `{scenario_name}`: {exc}"],
                    )
                ],
            )
            outcomes.append(
                _ScenarioOutcome(
                    scenario=scenario_name,
                    success=False,
                    status="failed",
                )
            )
            if resolved_failure_policy is FailurePolicy.fail_fast:
                break
            continue

        runtime_params = dict(runtime_params_base)
        runtime_params["solutions"] = solve_settings.solutions
        if solve_settings.energy_min is None:
            runtime_params.pop("energy_min", None)
        else:
            runtime_params["energy_min"] = solve_settings.energy_min
        if solve_settings.energy_max is None:
            runtime_params.pop("energy_max", None)
        else:
            runtime_params["energy_max"] = solve_settings.energy_max

        instance_payload = materialize_instance_payload(
            config=parsed_config, scenario_name=scenario_name
        )
        unit, run_result = run_for_target(
            text,
            options=CompileOptions(
                filename=str(file),
                instance_payload=instance_payload,
                outdir=str(scenario_outdir),
                output_format=resolved_output_format,
                runtime_id=runtime,
                plugin_specs=tuple(plugin),
            ),
            run_options=RuntimeRunOptions(params=runtime_params, outdir=str(scenario_outdir)),
        )
        has_errors = _print_diags(console, source, unit.diagnostics)

        report_path: Path | None = None
        if unit.support_report is not None:
            report_path = _write_capability_report(
                scenario_outdir, support_report_to_dict(unit.support_report)
            )

        scenario_success = not has_errors and run_result is not None
        scenario_run_path: Path | None = None
        status = "failed"
        runtime_id = None
        backend_id = None
        if run_result is not None:
            runtime_id = run_result.runtime
            backend_id = run_result.backend
            if report_path is not None:
                run_result.capability_report_path = str(report_path)
            scenario_run_path = _write_run_output(outdir=scenario_outdir, run_result=run_result)

            feature_requested = (
                solve_settings.solutions > 1
                or solve_settings.energy_min is not None
                or solve_settings.energy_max is not None
                or multi_scenario
            )
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
                                f"scenario `{scenario_name}`",
                                "requested solve features require `extensions.solutions` in run output",
                                f"run output was written to: {scenario_run_path}",
                            ],
                        )
                    ],
                )
                scenario_success = False
            if run_result.status != "ok":
                _print_diags(
                    console,
                    None,
                    [
                        _diag(
                            file,
                            code="QSOL5002",
                            message="runtime policy rejected solve output",
                            notes=[
                                f"scenario `{scenario_name}`",
                                f"status={run_result.status}",
                                f"run output: {scenario_run_path}",
                            ],
                        )
                    ],
                )
                scenario_success = False
            status = run_result.status

        if scenario_success and multi_scenario and run_result is not None:
            pair = (run_result.runtime, run_result.backend)
            if expected_pair is None:
                expected_pair = pair
            elif pair != expected_pair:
                _print_diags(
                    console,
                    None,
                    [
                        _diag(
                            file,
                            code="QSOL4001",
                            message="multi-scenario solve requires the same runtime/backend pair",
                            notes=[
                                f"scenario `{scenario_name}` resolved `{pair[0]}/{pair[1]}`",
                                f"expected `{expected_pair[0]}/{expected_pair[1]}`",
                            ],
                        )
                    ],
                )
                scenario_success = False
                status = "failed"

        outcomes.append(
            _ScenarioOutcome(
                scenario=scenario_name,
                success=scenario_success,
                status="ok" if scenario_success else status,
                runtime=runtime_id,
                backend=backend_id,
                report_path=report_path,
                run_path=scenario_run_path,
                run_result=run_result,
                requested_solutions=solve_settings.solutions,
            )
        )

        if multi_scenario:
            scenario_summary = Table(title=f"Run Summary ({scenario_name})")
            scenario_summary.add_column("Key")
            scenario_summary.add_column("Value")
            scenario_summary.add_row("Status", "ok" if scenario_success else status)
            scenario_summary.add_row("Runtime", runtime_id or "")
            scenario_summary.add_row("Backend", backend_id or "")
            scenario_summary.add_row(
                "Run Output", str(scenario_run_path) if scenario_run_path else ""
            )
            scenario_summary.add_row(
                "Capability Report", str(report_path) if report_path is not None else ""
            )
            console.print(scenario_summary)

        if not scenario_success and resolved_failure_policy is FailurePolicy.fail_fast:
            break

    successes = sum(1 for outcome in outcomes if outcome.success)
    failures = len(outcomes) - successes
    command_ok = _command_success(
        failure_policy=resolved_failure_policy,
        successes=successes,
        failures=failures,
    )

    final_run_result: StandardRunResult
    final_run_path: Path
    final_report_path: Path | None
    if multi_scenario:
        final_run_result = _build_multi_scenario_run_result(
            outcomes=outcomes,
            selected_scenarios=selected_scenarios,
            combine_mode=resolved_combine_mode,
            failure_policy=resolved_failure_policy,
            command_ok=command_ok,
        )
        final_report_path = resolved_outdir / "capability_report.json"
        aggregate_report_payload: dict[str, object] = {
            "schema_version": "1",
            "mode": "multi-scenario",
            "selected_scenarios": selected_scenarios,
            "failure_policy": resolved_failure_policy.value,
            "status": "ok" if command_ok else "failed",
            "scenarios": {
                outcome.scenario: {
                    "status": outcome.status,
                    "runtime": outcome.runtime,
                    "backend": outcome.backend,
                    "report_path": str(outcome.report_path) if outcome.report_path else None,
                    "run_path": str(outcome.run_path) if outcome.run_path else None,
                }
                for outcome in outcomes
            },
        }
        _write_json_file(
            final_report_path,
            aggregate_report_payload,
        )
        final_run_result.capability_report_path = str(final_report_path)
        final_run_path = _write_run_output(outdir=resolved_outdir, run_result=final_run_result)
    else:
        outcome = outcomes[0]
        if outcome.run_result is None:
            raise typer.Exit(code=1)
        final_run_result = outcome.run_result
        final_report_path = outcome.report_path
        final_run_path = outcome.run_path or _write_run_output(
            outdir=resolved_outdir, run_result=final_run_result
        )

    requested_solutions = final_run_result.extensions.get("requested_solutions", solutions or 1)
    returned_solutions = final_run_result.extensions.get("returned_solutions", 1)
    threshold_payload = final_run_result.extensions.get("energy_threshold")
    threshold_min = ""
    threshold_max = ""
    threshold_passed = ""
    if isinstance(threshold_payload, Mapping):
        threshold_min = str(threshold_payload.get("min", ""))
        threshold_max = str(threshold_payload.get("max", ""))
        threshold_passed = str(threshold_payload.get("passed", ""))

    summary = Table(title="Run Summary")
    summary.add_column("Key")
    summary.add_column("Value")
    summary.add_row("Status", final_run_result.status)
    summary.add_row("Runtime", final_run_result.runtime)
    summary.add_row("Backend", final_run_result.backend)
    summary.add_row("Runtime Parameters", _runtime_parameters_summary(final_run_result))
    summary.add_row("Energy", str(final_run_result.energy))
    summary.add_row("Solutions Requested", str(requested_solutions))
    summary.add_row("Solutions Returned", str(returned_solutions))
    summary.add_row("Energy Min", threshold_min)
    summary.add_row("Energy Max", threshold_max)
    summary.add_row("Energy Threshold Passed", threshold_passed)
    if multi_scenario:
        summary.add_row("Combine Mode", resolved_combine_mode.value)
        summary.add_row("Failure Policy", resolved_failure_policy.value)
        summary.add_row("Scenarios Requested", str(len(selected_scenarios)))
        summary.add_row("Scenarios Executed", str(len(outcomes)))
        summary.add_row("Scenarios Succeeded", str(successes))
        summary.add_row("Scenarios Failed", str(failures))
    summary.add_row("Timing (ms)", f"{final_run_result.timing_ms:.3f}")
    summary.add_row("Run Output", str(final_run_path))
    summary.add_row("Capability Report", str(final_report_path) if final_report_path else "")
    console.print(summary)

    solutions_table = Table(title="Returned Solutions")
    solutions_table.add_column("Rank")
    solutions_table.add_column("Energy")
    solutions_table.add_column("Selected")
    solutions_table.add_column("Occurrences")
    solutions_table.add_column("Probability")
    solutions_table.add_column("Status")
    solutions_table.add_column("Scenario Energies")
    solutions_table.add_column("Sample")
    solution_rows = _solution_entries(final_run_result)
    if solution_rows:
        for row in solution_rows:
            solutions_table.add_row(
                escape(str(row.get("rank", ""))),
                escape(str(row.get("energy", ""))),
                escape(_format_selected_assignments(row.get("selected_assignments"))),
                escape(str(row.get("num_occurrences", ""))),
                escape(str(row.get("probability", ""))),
                escape(str(row.get("status", ""))),
                escape(_format_solution_value(row.get("scenario_energies"))),
                escape(_format_sample_summary(row.get("sample"))),
            )
    else:
        solutions_table.add_row("-", "-", "", "", "", "", "", "No solutions returned")
    console.print(solutions_table)

    selected_table = Table(title="Selected Assignments")
    selected_table.add_column("Variable")
    selected_table.add_column("Meaning")
    if final_run_result.selected_assignments:
        for row in final_run_result.selected_assignments:
            selected_table.add_row(
                escape(str(row.get("variable", ""))),
                escape(str(row.get("meaning", ""))),
            )
    else:
        selected_table.add_row("-", "No (non-aux) binary variable set to 1 in the best sample")
    console.print(selected_table)

    if not command_ok:
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
