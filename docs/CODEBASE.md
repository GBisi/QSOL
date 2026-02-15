# QSOL Codebase Guide

This guide explains how the current QSOL compiler/runtime is organized and where to make changes safely.

## 1. High-Level Architecture

Pipeline from source to artifacts:

1. Parse source text into AST (`qsol.parse`)
2. Resolve symbols (`qsol.sema.resolver`)
3. Typecheck (`qsol.sema.typecheck`)
4. Validate structural rules (`qsol.sema.validate`)
5. Desugar syntax sugar (`qsol.lower.desugar`)
6. Lower to symbolic kernel IR (`qsol.lower.lower`)
7. Ground IR using instance JSON (`qsol.backend.instance`)
8. Generate dimod CQM/BQM (`qsol.backend.dimod_codegen`)
9. Export files (`qsol.backend.export`)

The pipeline entrypoint is `qsol.compiler.pipeline.compile_source`.

## 2. Directory Map

- `src/qsol/cli.py`: Typer CLI (`compile`, `run`)
- `src/qsol/compiler/`: compile options + pipeline orchestration
- `src/qsol/parse/`: grammar, parser, AST, AST builder
- `src/qsol/sema/`: symbol resolution, type checking, static validation
- `src/qsol/lower/`: desugaring + kernel IR lowering
- `src/qsol/backend/`: instance instantiation, dimod codegen, artifact export
- `src/qsol/diag/`: diagnostics, spans, reporter
- `src/qsol/util/`: utility helpers (stable hashing)
- `examples/qubo/`: runnable QSOL examples and instances
- `tests/`: parser, sema, lowering, backend, CLI tests
- `editors/vscode-qsol/`: VS Code syntax highlighting extension

## 3. Key Data Structures

### 3.1 AST (`src/qsol/parse/ast.py`)

Core nodes:
- `Program`, `ProblemDef`, `UnknownDef`
- declarations: `SetDecl`, `ParamDecl`, `FindDecl`
- constraints/objectives: `Constraint`, `Objective`
- expressions: bool/numeric expression classes + aggregates + quantifiers

All AST nodes carry a `Span` for diagnostics.

### 3.2 Symbols and Types (`src/qsol/sema/`)

- `SymbolTable` stores global + per-problem scopes.
- `Resolver` defines symbols and checks unknown declarations.
- `TypeChecker` infers/checks expression types and annotates `TypedProgram.types`.

### 3.3 IR (`src/qsol/lower/ir.py`)

- `KernelIR`: symbolic model after desugaring/lowering
- `GroundIR`: kernel IR plus concrete set/param values from instance
- `BackendArtifacts`: output file paths and model stats

### 3.4 Compilation Unit (`src/qsol/compiler/pipeline.py`)

`CompilationUnit` is the main output object used by CLI/API:
- `ast`, `symbol_table`, `typed_program`
- `lowered_ir_symbolic`, `ground_ir`, `artifacts`
- `diagnostics`

## 4. Command Flow

### 4.1 `compile --parse`

- Reads file
- Runs `compile_source` without instance/outdir
- Prints AST (pretty or JSON)

### 4.2 `compile --check`

- Same pipeline stage range as `parse`
- Prints diagnostics only

### 4.3 `compile --lower`

- Runs through desugaring/lowering
- Prints symbolic kernel IR

### 4.4 `compile` (full backend build)

- Resolves instance path + output directory
- Runs full pipeline with instance and codegen
- Writes artifacts and build log

### 4.5 `run`

- Performs `compile` flow to produce BQM
- Samples with dimod `ExactSolver` or `SimulatedAnnealingSampler`
- Writes `run.json` summary and prints selected assignments

## 5. Diagnostics Model

Diagnostics are created across all stages with a shared structure:

- `severity`: `error` / `warning` / `info`
- `code`: stable ID (e.g. `QSOL1001`)
- `message`
- `span`
- optional `notes` and `help`

Typical code groups:
- `QSOL1xxx`: parse
- `QSOL2xxx`: semantic/type/instance errors
- `QSOL3xxx`: backend limitations/unsupported shapes

## 6. Backend Behavior Notes

Current dimod backend (`src/qsol/backend/dimod_codegen.py`) is intentionally narrow:

- Native variable declaration support for `Subset` and `Mapping` only.
- Many grammar-valid expressions can still fail lowering/codegen.
- Unsupported patterns emit `QSOL3001` diagnostics rather than crashing.

When extending backend support, update:
- expression lowering paths (`_bool_expr`, `_num_expr`, `_emit_constraint`)
- diagnostics coverage
- backend tests in `tests/backend/`

## 7. How To Add a Language Feature

Use this order to minimize regressions:

1. Update grammar (`src/qsol/parse/grammar.lark`)
2. Update AST builder (`src/qsol/parse/ast_builder.py`)
3. Add/adjust AST nodes if needed (`src/qsol/parse/ast.py`)
4. Extend resolver/typechecker
5. Add desugaring rule if feature is surface sugar
6. Extend lowering to kernel IR
7. Extend backend codegen and/or instance handling
8. Add tests per stage (parser, sema, lower, backend, CLI)
9. Update docs (`README`, `QSOL_reference.md`, syntax/tutorial docs)

## 8. Test Suite Map

- `tests/parser/`: grammar and AST builder coverage
- `tests/sema/`: resolver/typechecker coverage
- `tests/lower/`: desugar/lower behavior
- `tests/backend/`: instance + codegen + compile pipeline
- `tests/cli/`: end-user command behavior
- `tests/golden/`: stable diagnostic expectations

Run all tests:

```bash
uv run pytest
```

## 9. Practical Debugging Workflow

1. `uv run qsol compile model.qsol --parse --json`
2. `uv run qsol compile model.qsol --check`
3. `uv run qsol compile model.qsol --lower --json`
4. `uv run qsol compile model.qsol -i instance.json -o outdir/model --log-level debug`
5. Inspect `outdir/model/explain.json` and `outdir/model/qsol.log`

This stage-by-stage process makes it easy to isolate grammar vs typing vs backend issues.
