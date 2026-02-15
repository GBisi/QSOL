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
from qsol.compiler.pipeline import compile_source
from qsol.diag.diagnostic import Diagnostic
from qsol.diag.reporter import DiagnosticReporter
from qsol.diag.source import SourceText

app = typer.Typer(
    help="QSOL compiler frontend",
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
LOGGER = logging.getLogger(__name__)


class SamplerKind(str, Enum):
    exact = "exact"
    simulated_annealing = "simulated-annealing"


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


class CompileInspectMode(str, Enum):
    parse = "parse"
    check = "check"
    lower_ = "lower"


@app.callback(invoke_without_command=True)
def root_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return

    console = Console()
    console.print(
        Panel(
            (
                "[bold cyan]Welcome to QSOL[/bold cyan]\n\n"
                "[white]QSOL is a modeling language and compiler for optimization problems. "
                "You write a `.qsol` model, compile it to QUBO/Ising/BQM/CQM artifacts, "
                "and optionally run a sampler to get candidate solutions.[/white]"
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
        "Compile model + instance",
        "qsol compile model.qsol -i model.instance.json -o outdir/model",
    )
    quickstart.add_row(
        "Run solver (build + sample)",
        "qsol run model.qsol -i model.instance.json -o outdir/model -s simulated-annealing",
    )
    quickstart.add_row(
        "Defaults you can rely on",
        "Instance defaults to `model.instance.json`; outdir defaults to `./outdir/model`",
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

    LOGGER.debug("Logging configured")


def _read_file(path: Path) -> str:
    LOGGER.debug("Reading source file: %s", path)
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


def _print_diags(console: Console, source: SourceText, diagnostics: list[Diagnostic]) -> bool:
    reporter = DiagnosticReporter(console=console)
    if diagnostics:
        for diag in diagnostics:
            if diag.is_error:
                LOGGER.error("%s[%s] %s", diag.severity.value, diag.code, diag.message)
            elif diag.severity.value == "warning":
                LOGGER.warning("%s[%s] %s", diag.severity.value, diag.code, diag.message)
            else:
                LOGGER.info("%s[%s] %s", diag.severity.value, diag.code, diag.message)
        reporter.print(source, diagnostics)
    return any(d.is_error for d in diagnostics)


def _resolve_instance_path(file: Path, instance: Path | None) -> Path:
    if instance is not None:
        return instance

    inferred_instance = file.with_suffix(".instance.json")
    if inferred_instance.exists():
        LOGGER.info("Inferred instance file: %s", inferred_instance)
        return inferred_instance

    message = f"instance file not provided and default instance was not found: {inferred_instance}"
    LOGGER.error(message)
    raise typer.BadParameter(message)


def _resolve_outdir(file: Path, outdir: Path | None) -> Path:
    if outdir is not None:
        return outdir

    inferred_outdir = Path.cwd() / "outdir" / file.stem
    LOGGER.info("Inferred output directory: %s", inferred_outdir)
    return inferred_outdir


def _is_internal_variable(label: str) -> bool:
    # Internal variables introduced by the backend for reification / linearization.
    # Keep these out of CLI-facing output.
    return label.startswith("aux:") or label.startswith("slack:")


def _write_run_output(
    *,
    outdir: Path,
    sampler: SamplerKind,
    num_reads: int,
    seed: int | None,
    sampleset: Any,
    varmap: dict[str, str],
) -> Path:
    first = sampleset.first

    # Only export user-facing (mapped) assignments; internal variables are omitted.
    selected: list[dict[str, object]] = []
    for var, value in sorted(first.sample.items(), key=lambda item: str(item[0])):
        if int(value) != 1:
            continue
        label = str(var)
        if _is_internal_variable(label) or label not in varmap:
            continue
        selected.append(
            {
                "variable": label,
                "meaning": str(varmap[label]),
                "value": int(value),
            }
        )

    run_payload = {
        "sampler": sampler.value,
        "num_reads": num_reads,
        "seed": seed,
        "energy": float(first.energy),
        "reads": int(len(sampleset)),
        "variables": int(len(first.sample)),
        "best_sample": {str(var): int(value) for var, value in first.sample.items()},
        "selected_assignments": selected,
    }
    run_path = outdir / "run.json"
    run_path.write_text(json.dumps(run_payload, indent=2, sort_keys=True), encoding="utf-8")
    LOGGER.info("Run output written to %s", run_path)
    return run_path


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


@app.command("compile")
def compile_cmd(
    file: Path,
    parse: bool = typer.Option(False, "--parse", help="Run parse stage only"),
    check: bool = typer.Option(False, "--check", help="Run semantic checks only"),
    lower: bool = typer.Option(False, "--lower", help="Run lowering stage only"),
    json_out: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Print JSON output in --parse/--lower modes",
    ),
    instance: Path | None = typer.Option(None, "--instance", "-i", help="Instance JSON file"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output directory"),
    output_format: str = typer.Option("qubo", "--format", "-f", help="qubo|ising|bqm|cqm"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug summary"),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI colors"),
    log_level: LogLevel = typer.Option(LogLevel.info, "--log-level", "-l", help="Log level"),
) -> None:
    selected_modes = [
        mode
        for mode, enabled in (
            (CompileInspectMode.parse, parse),
            (CompileInspectMode.check, check),
            (CompileInspectMode.lower_, lower),
        )
        if enabled
    ]
    if len(selected_modes) > 1:
        raise typer.BadParameter("choose only one of --parse, --check, or --lower")

    inspect_mode = selected_modes[0] if selected_modes else None
    if json_out and inspect_mode not in (CompileInspectMode.parse, CompileInspectMode.lower_):
        raise typer.BadParameter("--json is only valid with --parse or --lower")

    resolved_outdir: Path | None = None
    if inspect_mode is None:
        resolved_outdir = _resolve_outdir(file, out)
        _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")
    else:
        _configure_logging(log_level)

    if inspect_mode == CompileInspectMode.parse:
        LOGGER.info("Running parse via compile on %s", file)
    elif inspect_mode == CompileInspectMode.check:
        LOGGER.info("Running check via compile on %s", file)
    elif inspect_mode == CompileInspectMode.lower_:
        LOGGER.info("Running lower via compile on %s", file)
    else:
        LOGGER.info("Running compile on %s", file)

    console = Console(no_color=no_color)
    text = _read_file(file)
    if inspect_mode is None:
        resolved_instance = _resolve_instance_path(file, instance)
        LOGGER.debug(
            "Compile options: instance=%s outdir=%s format=%s",
            resolved_instance,
            resolved_outdir,
            output_format,
        )
        unit = compile_source(
            text,
            options=CompileOptions(
                filename=str(file),
                instance_path=str(resolved_instance),
                outdir=str(resolved_outdir),
                output_format=output_format,
                verbose=verbose,
            ),
        )
    else:
        unit = compile_source(text, options=CompileOptions(filename=str(file)))

    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)

    if inspect_mode == CompileInspectMode.parse:
        if has_errors or unit.ast is None:
            raise typer.Exit(code=1)
        if json_out:
            console.print(json.dumps(_to_jsonable(unit.ast), indent=2, sort_keys=True))
        else:
            console.print(Pretty(unit.ast))
        return

    if inspect_mode == CompileInspectMode.check:
        if not unit.diagnostics:
            LOGGER.info("No diagnostics emitted")
            console.print("No diagnostics.")
        if has_errors:
            raise typer.Exit(code=1)
        return

    if inspect_mode == CompileInspectMode.lower_:
        if has_errors or unit.lowered_ir_symbolic is None:
            raise typer.Exit(code=1)
        if json_out:
            console.print(
                json.dumps(_to_jsonable(unit.lowered_ir_symbolic), indent=2, sort_keys=True)
            )
        else:
            console.print(Pretty(unit.lowered_ir_symbolic))
        return

    if has_errors or unit.artifacts is None or resolved_outdir is None:
        raise typer.Exit(code=1)

    table = Table(title="Compilation Artifacts")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("CQM", unit.artifacts.cqm_path or "")
    table.add_row("BQM", unit.artifacts.bqm_path or "")
    table.add_row("Format", unit.artifacts.format_path or "")
    table.add_row("VarMap", unit.artifacts.varmap_path or "")
    table.add_row("Explain", unit.artifacts.explain_path or "")
    for key, value in sorted(unit.artifacts.stats.items()):
        table.add_row(key, str(value))
    console.print(table)
    LOGGER.info("Compilation artifacts exported to %s", resolved_outdir)


@app.command("run")
def run_cmd(
    file: Path,
    instance: Path | None = typer.Option(None, "--instance", "-i", help="Instance JSON file"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output directory"),
    output_format: str = typer.Option("qubo", "--format", "-f", help="qubo|ising|bqm|cqm"),
    sampler: SamplerKind = typer.Option(
        SamplerKind.simulated_annealing,
        "--sampler",
        "-s",
        help="exact|simulated-annealing",
    ),
    num_reads: int = typer.Option(
        100, "--num-reads", "-r", min=1, help="Reads for simulated annealing"
    ),
    seed: int | None = typer.Option(None, "--seed", "-d", help="Optional random seed"),
    no_color: bool = typer.Option(False, "--no-color", "-n", help="Disable ANSI colors"),
    log_level: LogLevel = typer.Option(LogLevel.warning, "--log-level", "-l", help="Log level"),
) -> None:
    resolved_outdir = _resolve_outdir(file, out)
    _configure_logging(log_level, log_file=resolved_outdir / "qsol.log")

    resolved_instance = _resolve_instance_path(file, instance)
    LOGGER.info("Running solve flow on %s", file)
    LOGGER.debug(
        "Run options: instance=%s outdir=%s format=%s sampler=%s reads=%s seed=%s",
        resolved_instance,
        resolved_outdir,
        output_format,
        sampler.value,
        num_reads,
        seed,
    )

    console = Console(no_color=no_color)
    text = _read_file(file)
    unit = compile_source(
        text,
        options=CompileOptions(
            filename=str(file),
            instance_path=str(resolved_instance),
            outdir=str(resolved_outdir),
            output_format=output_format,
        ),
    )
    source = SourceText(text, str(file))
    has_errors = _print_diags(console, source, unit.diagnostics)
    if has_errors or unit.artifacts is None or unit.artifacts.bqm_path is None:
        raise typer.Exit(code=1)

    with Path(unit.artifacts.bqm_path).open("rb") as fp:
        bqm = dimod.BinaryQuadraticModel.from_file(fp)
    if unit.artifacts.varmap_path is None:
        LOGGER.error("Missing varmap artifact")
        raise typer.Exit(code=1)
    varmap = json.loads(Path(unit.artifacts.varmap_path).read_text(encoding="utf-8"))

    if sampler == SamplerKind.exact:
        LOGGER.info("Using exact solver")
        sampleset = _sample_exact(bqm)
    else:
        sample_kwargs: dict[str, Any] = {"num_reads": num_reads}
        if seed is not None:
            sample_kwargs["seed"] = seed
        LOGGER.info("Using simulated annealing sampler")
        sampleset = _sample_sa(bqm, sample_kwargs)

    run_output_path = _write_run_output(
        outdir=resolved_outdir,
        sampler=sampler,
        num_reads=num_reads,
        seed=seed,
        sampleset=sampleset,
        varmap=varmap,
    )

    first = sampleset.first

    summary = Table(title="Run Summary")
    summary.add_column("Key")
    summary.add_column("Value")
    summary.add_row("Sampler", sampler.value)
    summary.add_row("Energy", str(first.energy))
    summary.add_row("Reads", str(len(sampleset)))
    summary.add_row("Variables", str(len(first.sample)))
    summary.add_row("Run Output", str(run_output_path))
    console.print(summary)

    selected = Table(title="Selected Assignments")
    selected.add_column("Variable")
    selected.add_column("Meaning")
    selected_count = 0
    for var, value in sorted(first.sample.items(), key=lambda item: str(item[0])):
        if int(value) != 1:
            continue
        label = str(var)
        if _is_internal_variable(label) or label not in varmap:
            continue
        selected.add_row(escape(label), escape(str(varmap[label])))
        selected_count += 1
    if selected_count == 0:
        LOGGER.warning("No selected assignments in best sample")
        selected.add_row("-", "No (non-aux) binary variable set to 1 in the best sample")
    console.print(selected)


if __name__ == "__main__":
    app()
