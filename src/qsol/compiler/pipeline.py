from __future__ import annotations

import logging
from dataclasses import dataclass, field

from lark import Tree

from qsol.backend.dimod_codegen import DimodCodegen
from qsol.backend.export import export_artifacts
from qsol.backend.instance import instantiate_ir as instantiate_ir_pass
from qsol.backend.instance import load_instance
from qsol.compiler.options import CompileOptions
from qsol.diag.diagnostic import Diagnostic
from qsol.lower.desugar import desugar_program
from qsol.lower.ir import BackendArtifacts, GroundIR, KernelIR
from qsol.lower.lower import lower_symbolic as lower_symbolic_pass
from qsol.parse.ast import Program, TypedProgram
from qsol.parse.parser import ParseFailure, parse_to_ast
from qsol.parse.parser import parse_program as parse_program_pass
from qsol.sema.resolver import Resolver
from qsol.sema.symbols import SymbolTable
from qsol.sema.typecheck import TypeChecker
from qsol.sema.validate import validate_program

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


@dataclass(slots=True)
class CheckResult:
    unit: CompilationUnit


def compile_source(text: str, *, options: CompileOptions) -> CompilationUnit:
    LOGGER.debug("Starting compilation pipeline for %s", options.filename)
    unit = CompilationUnit()
    try:
        program = parse_to_ast(text, filename=options.filename)
    except ParseFailure as exc:
        LOGGER.error("Parse failure for %s", options.filename)
        unit.diagnostics.append(exc.diagnostic)
        return unit

    LOGGER.debug("Parse stage completed")
    unit.ast = program

    resolver = Resolver()
    res = resolver.resolve(program)
    LOGGER.debug("Resolve stage completed")
    unit.symbol_table = res.symbols
    unit.diagnostics.extend(res.diagnostics)

    checker = TypeChecker()
    tc = checker.check(program, res.symbols)
    LOGGER.debug("Typecheck stage completed")
    unit.typed_program = tc.typed_program
    unit.diagnostics.extend(tc.diagnostics)

    unit.diagnostics.extend(validate_program(program))
    LOGGER.debug("Validation stage completed")

    desugared = desugar_program(program)
    unit.lowered_ir_symbolic = lower_symbolic_pass(desugared)
    LOGGER.debug("Lowering stage completed")

    if options.instance_path is not None and unit.lowered_ir_symbolic is not None:
        LOGGER.debug("Loading instance from %s", options.instance_path)
        instance = load_instance(options.instance_path)
        inst_result = instantiate_ir_pass(unit.lowered_ir_symbolic, instance)
        unit.diagnostics.extend(inst_result.diagnostics)
        unit.ground_ir = inst_result.ground_ir
        LOGGER.debug("Instantiation stage completed")

    if options.outdir and options.instance_path and unit.ground_ir is not None:
        LOGGER.debug("Running dimod codegen")
        codegen = DimodCodegen().compile(unit.ground_ir)
        unit.diagnostics.extend(codegen.diagnostics)
        LOGGER.debug("Exporting artifacts to %s", options.outdir)
        unit.artifacts = export_artifacts(options.outdir, options.output_format, codegen)

    LOGGER.info(
        "Compilation pipeline completed for %s with %s diagnostics",
        options.filename,
        len(unit.diagnostics),
    )
    return unit


def parse_program(text: str, *, filename: str = "<input>") -> Tree[object]:
    return parse_program_pass(text, filename)


def check_program(text: str, *, filename: str = "<input>") -> CompilationUnit:
    return compile_source(text, options=CompileOptions(filename=filename))


def lower_symbolic(text: str, *, filename: str = "<input>") -> CompilationUnit:
    return compile_source(text, options=CompileOptions(filename=filename))


def instantiate_ir(
    text: str,
    *,
    filename: str,
    instance_path: str,
) -> CompilationUnit:
    return compile_source(
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
