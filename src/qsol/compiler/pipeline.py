from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

from lark import Tree

from qsol.backend.instance import instantiate_ir as instantiate_ir_pass
from qsol.backend.instance import load_instance
from qsol.compiler.options import CompileOptions
from qsol.diag.cli_diagnostics import instance_load_error
from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.lower.desugar import desugar_program
from qsol.lower.ir import BackendArtifacts, GroundIR, KernelIR
from qsol.lower.lower import lower_symbolic as lower_symbolic_pass
from qsol.parse.ast import Program, TypedProgram
from qsol.parse.module_loader import resolve_use_modules
from qsol.parse.parser import ParseFailure, parse_to_ast
from qsol.parse.parser import parse_program as parse_program_pass
from qsol.sema.resolver import Resolver
from qsol.sema.symbols import SymbolTable
from qsol.sema.typecheck import TypeChecker
from qsol.sema.unknown_elaboration import elaborate_unknowns
from qsol.sema.validate import validate_program
from qsol.targeting import (
    CompiledModel,
    PluginRegistry,
    RuntimeRunOptions,
    StandardRunResult,
    SupportReport,
    TargetSelection,
    check_pair_support,
    resolve_target_selection,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CompilationUnit:
    ast: Program | None = None
    symbol_table: SymbolTable | None = None
    typed_program: TypedProgram | None = None
    lowered_ir_symbolic: KernelIR | None = None
    ground_ir: GroundIR | None = None
    artifacts: BackendArtifacts | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    instance_payload: dict[str, object] | None = None
    resolved_plugin_specs: tuple[str, ...] = ()
    target_selection: TargetSelection | None = None
    support_report: SupportReport | None = None
    compiled_model: CompiledModel | None = None


@dataclass(slots=True)
class CheckResult:
    unit: CompilationUnit


def _span(filename: str) -> Span:
    return Span(
        start_offset=0,
        end_offset=1,
        line=1,
        col=1,
        end_line=1,
        end_col=2,
        filename=filename,
    )


def _diag(filename: str, *, code: str, message: str, notes: list[str] | None = None) -> Diagnostic:
    return Diagnostic(
        severity=Severity.ERROR,
        code=code,
        message=message,
        span=_span(filename),
        notes=notes or [],
    )


def _apply_frontend_stages(text: str, *, options: CompileOptions, unit: CompilationUnit) -> None:
    try:
        raw_program = parse_to_ast(text, filename=options.filename)
    except ParseFailure as exc:
        LOGGER.error("Parse failure for %s", options.filename)
        unit.diagnostics.append(exc.diagnostic)
        return

    unit.ast = raw_program

    module_result = resolve_use_modules(raw_program, root_filename=options.filename)
    unit.diagnostics.extend(module_result.diagnostics)
    if any(diag.is_error for diag in unit.diagnostics):
        return

    elaboration = elaborate_unknowns(module_result.program)
    unit.diagnostics.extend(elaboration.diagnostics)
    if any(diag.is_error for diag in unit.diagnostics):
        return

    program = elaboration.program

    resolver = Resolver()
    res = resolver.resolve(program)
    unit.symbol_table = res.symbols
    unit.diagnostics.extend(res.diagnostics)

    checker = TypeChecker()
    tc = checker.check(program, res.symbols)
    unit.typed_program = tc.typed_program
    unit.diagnostics.extend(tc.diagnostics)

    unit.diagnostics.extend(validate_program(program))

    desugared = desugar_program(program)
    unit.lowered_ir_symbolic = lower_symbolic_pass(desugared)

    if unit.lowered_ir_symbolic is None:
        return

    instance: dict[str, object] | None = None
    if options.instance_payload is not None:
        LOGGER.debug("Using in-memory instance payload for %s", options.filename)
        instance = dict(options.instance_payload)
    elif options.instance_path is not None:
        LOGGER.debug("Loading instance from %s", options.instance_path)
        try:
            instance = load_instance(options.instance_path)
        except Exception as exc:  # pragma: no cover - defensive guard for runtime IO/JSON failures
            unit.diagnostics.append(instance_load_error(Path(options.instance_path), exc))
            return
    else:
        return

    unit.instance_payload = instance
    inst_result = instantiate_ir_pass(unit.lowered_ir_symbolic, instance)
    unit.diagnostics.extend(inst_result.diagnostics)
    unit.ground_ir = inst_result.ground_ir


def compile_frontend(text: str, *, options: CompileOptions) -> CompilationUnit:
    LOGGER.debug("Starting frontend pipeline for %s", options.filename)
    unit = CompilationUnit()
    _apply_frontend_stages(text, options=options, unit=unit)
    LOGGER.info(
        "Frontend pipeline completed for %s with %s diagnostics",
        options.filename,
        len(unit.diagnostics),
    )
    return unit


def _with_support_diagnostics(unit: CompilationUnit, *, filename: str) -> CompilationUnit:
    if unit.support_report is None:
        return unit

    for issue in unit.support_report.issues:
        unit.diagnostics.append(
            _diag(
                filename,
                code=issue.code,
                message=issue.message,
                notes=[f"stage={issue.stage}"]
                + ([f"capability={issue.capability_id}"] if issue.capability_id else []),
            )
        )
    return unit


def check_target_support(text: str, *, options: CompileOptions) -> CompilationUnit:
    unit = compile_frontend(text, options=options)
    if any(diag.is_error for diag in unit.diagnostics):
        return unit

    if unit.ground_ir is None:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4006",
                message=(
                    "target support checks require instance grounding; "
                    "provide config-resolved scenario data"
                ),
            )
        )
        return unit

    resolution = resolve_target_selection(
        instance_payload=unit.instance_payload,
        cli_runtime=options.runtime_id,
        cli_backend=options.backend_id,
        cli_plugin_specs=options.plugin_specs,
    )
    unit.resolved_plugin_specs = tuple(resolution.plugin_specs)
    unit.target_selection = resolution.selection
    if resolution.issues:
        unit.support_report = SupportReport(
            selection=resolution.selection
            or TargetSelection(runtime_id="<missing>", backend_id="<missing>"),
            supported=False,
            issues=resolution.issues,
        )
        return _with_support_diagnostics(unit, filename=options.filename)

    try:
        registry = PluginRegistry.from_discovery(module_specs=list(unit.resolved_plugin_specs))
    except Exception as exc:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4009",
                message="failed to load runtime/backend plugins",
                notes=[str(exc)],
            )
        )
        return unit

    if resolution.selection is None:
        unit.support_report = SupportReport(
            selection=TargetSelection(runtime_id="<missing>", backend_id="<missing>"),
            supported=False,
        )
        return _with_support_diagnostics(unit, filename=options.filename)

    selection = resolution.selection
    assert selection is not None

    backend = registry.backend(selection.backend_id)
    if backend is None:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4007",
                message=f"unknown backend id: `{selection.backend_id}`",
            )
        )
        return unit

    runtime = registry.runtime(selection.runtime_id)
    if runtime is None:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4007",
                message=f"unknown runtime id: `{selection.runtime_id}`",
            )
        )
        return unit

    compat = check_pair_support(
        ground=unit.ground_ir,
        selection=selection,
        backend=backend,
        runtime=runtime,
    )
    unit.support_report = compat.report
    unit.compiled_model = compat.compiled_model
    return _with_support_diagnostics(unit, filename=options.filename)


def build_for_target(text: str, *, options: CompileOptions) -> CompilationUnit:
    unit = check_target_support(text, options=options)
    if any(diag.is_error for diag in unit.diagnostics):
        return unit

    if options.outdir is None:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4001",
                message="build requires output directory; provide `--out <dir>`",
            )
        )
        return unit

    if unit.compiled_model is None or unit.target_selection is None:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4005",
                message="target build did not produce compiled model",
            )
        )
        return unit

    try:
        registry = PluginRegistry.from_discovery(module_specs=list(unit.resolved_plugin_specs))
        backend = registry.require_backend(unit.target_selection.backend_id)
    except Exception as exc:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4009",
                message="failed to load backend plugin for export",
                notes=[str(exc)],
            )
        )
        return unit

    unit.artifacts = backend.export_model(
        unit.compiled_model,
        outdir=options.outdir,
        output_format=options.output_format,
    )
    return unit


def run_for_target(
    text: str,
    *,
    options: CompileOptions,
    run_options: RuntimeRunOptions,
) -> tuple[CompilationUnit, StandardRunResult | None]:
    unit = build_for_target(text, options=options)
    if any(diag.is_error for diag in unit.diagnostics):
        return unit, None

    if unit.compiled_model is None or unit.target_selection is None:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4005",
                message="target run did not produce compiled model",
            )
        )
        return unit, None

    try:
        registry = PluginRegistry.from_discovery(module_specs=list(unit.resolved_plugin_specs))
        runtime = registry.require_runtime(unit.target_selection.runtime_id)
    except Exception as exc:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL4009",
                message="failed to load runtime plugin",
                notes=[str(exc)],
            )
        )
        return unit, None

    try:
        result = runtime.run_model(
            unit.compiled_model,
            selection=unit.target_selection,
            run_options=run_options,
        )
    except Exception as exc:
        unit.diagnostics.append(
            _diag(
                options.filename,
                code="QSOL5001",
                message="runtime execution failure",
                notes=[str(exc)],
            )
        )
        return unit, None

    return unit, result


def compile_source(text: str, *, options: CompileOptions) -> CompilationUnit:
    # Backward-compatible wrapper used by legacy Python helpers/tests.
    # For full build requests, default to the built-in local target pair.
    has_instance = options.instance_path is not None or options.instance_payload is not None
    if has_instance and options.outdir is not None:
        target_options = options
        if target_options.runtime_id is None or target_options.backend_id is None:
            target_options = replace(
                target_options,
                runtime_id=target_options.runtime_id or "local-dimod",
                backend_id=target_options.backend_id or "dimod-cqm-v1",
            )
        return build_for_target(text, options=target_options)

    return compile_frontend(text, options=options)


def parse_program(text: str, *, filename: str = "<input>") -> Tree[object]:
    return parse_program_pass(text, filename)


def check_program(text: str, *, filename: str = "<input>") -> CompilationUnit:
    return compile_frontend(text, options=CompileOptions(filename=filename))


def lower_symbolic(text: str, *, filename: str = "<input>") -> CompilationUnit:
    return compile_frontend(text, options=CompileOptions(filename=filename))


def instantiate_ir(
    text: str,
    *,
    filename: str,
    instance_path: str,
) -> CompilationUnit:
    return compile_frontend(
        text,
        options=CompileOptions(filename=filename, instance_path=instance_path),
    )


def compile_with_instance(
    text: str,
    *,
    filename: str,
    instance_path: str,
    outdir: str,
    output_format: str,
) -> CompilationUnit:
    return compile_source(
        text,
        options=CompileOptions(
            filename=filename,
            instance_path=instance_path,
            outdir=outdir,
            output_format=output_format,
        ),
    )
