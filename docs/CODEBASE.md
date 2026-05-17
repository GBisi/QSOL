# QSOL Codebase Guide

This guide explains QSOL's staged compiler + pluggable targeting architecture.

## 1. High-Level Architecture

Pipeline from source to runtime result:

1. Parse source text into AST (`qsol.parse`)
2. Resolve `use` imports into merged top-level unknown/predicate/function definitions (`qsol.parse.module_loader`)
3. Expand macros and elaborate custom unknown finds into primitive finds + generated constraints (`qsol.sema.unknown_elaboration`)
4. Resolve symbols (`qsol.sema.resolver`)
5. Typecheck (`qsol.sema.typecheck`)
6. Validate structural rules (`qsol.sema.validate`)
7. Lower compiler-owned global/graph helpers (`qsol.lower.globals`)
8. Desugar syntax sugar (`qsol.lower.desugar`)
9. Lower to symbolic kernel IR (`qsol.lower.lower`)
10. Ground IR from scenario-materialized instance payload (`qsol.backend.instance`, `qsol.config`)
11. Resolve runtime/backend selection (`qsol.targeting.resolution`)
12. Check pair support and capability requirements (`qsol.targeting.compatibility`)
13. Compile/export with selected backend plugin (`qsol.targeting.plugins`, backend export)
14. Run with selected runtime plugin (`qsol.targeting.plugins`)

## 2. Directory Map

- `src/qsol/cli.py`: Typer CLI (`inspect`, `targets`, `build`, `solve`)
- `src/qsol/compiler/`: frontend + targeting pipeline orchestration
- `src/qsol/targeting/`: plugin interfaces, registry, selection, compatibility
- `src/qsol/parse/`: grammar, parser, AST, AST builder, module loader
- `src/qsol/sema/`: symbol resolution, custom unknown elaboration, type checking, groundability checks, static validation
- `src/qsol/lower/`: global/helper lowering, desugaring, piecewise lowering, and kernel IR lowering
- `src/qsol/backend/`: instance grounding, static bound evaluation, graph encoding helpers, dimod codegen/export primitives
- `src/qsol/config/`: config TOML parsing, scenario selection, and instance materialization
- `src/qsol/stdlib/`: packaged unknown modules and source-level helper modules (`stdlib.*`)
- `src/qsol/diag/`: diagnostics, spans, reporter
- `src/qsol/util/`: utility helpers
- `tests/`: parser, sema, lowering, backend, targeting, CLI tests

## 3. Key Data Structures

### 3.1 Frontend IR (`src/qsol/lower/ir.py`)

- `KernelIR`: symbolic model after lowering, including set and relation declarations
- `GroundIR`: kernel IR + concrete sets/relations/params
- `BackendArtifacts`: exported file paths/stats

### 3.2 Targeting Types (`src/qsol/targeting/types.py`)

- `TargetSelection`: selected runtime/backend ids
- `SupportIssue`, `SupportReport`: capability and compatibility diagnostics
- `CompiledModel`: backend-compiled model payload (canonical `kind="cqm"` in v1)
- `StandardRunResult`: runtime output contract (`run.json` core schema)

### 3.3 Compilation Unit (`src/qsol/compiler/pipeline.py`)

`CompilationUnit` includes:
- frontend outputs: `ast`, `symbol_table`, `typed_program`, `lowered_ir_symbolic`, `ground_ir`
- targeting outputs: `target_selection`, `support_report`, `compiled_model`
- exported artifacts: `artifacts`
- diagnostics: `diagnostics`

## 4. Pipeline Entrypoints

- `compile_frontend`: parse/sema/lower/ground only
- `check_target_support`: frontend + selection + capability checks
- `build_for_target`: support check + backend compile/export
- `run_for_target`: build + runtime execution
- `compile_source`: backward-compatible wrapper (legacy API behavior)

## 5. CLI Flow

### 5.1 Inspect Commands

- `inspect parse`: parse output
- `inspect check`: semantic diagnostics
- `inspect lower`: lowered symbolic IR

### 5.2 Targets Commands

- `targets list`: discover runtime/backend plugins
- `targets capabilities`: inspect capability catalogs and pair compatibility
- `targets check`: evaluate specific model+scenario against selected pair

### 5.3 Build and Solve

- `build`: compile/export artifacts for selected pair
- `solve`: build + runtime execution + standardized `run.json`

Selection precedence:
1. CLI `--runtime`
2. Scenario execution default `execution.runtime` (from config)
3. Config `entrypoint.runtime`
4. Default backend `dimod-cqm-v1`

## 6. Plugin Model

Plugins use protocols in `src/qsol/targeting/interfaces.py`.

- Backends implement capability catalog, support checks, compile, export.
- Runtimes implement capability catalog, compatible backend ids, support checks, run.

Discovery:
- Built-ins are always registered first.
- Entry points: `qsol.backends`, `qsol.runtimes`.
- Optional module specs: `--plugin module:attribute`.

Reference built-ins:
- Backend: `dimod-cqm-v1`
- Runtime: `local-dimod`

See also: `docs/PLUGINS.md` for authoring and loading workflows.

## 7. Diagnostics Model

Families:
- `QSOL1xxx`: parse
- `QSOL2xxx`: semantic/type/instance
- `QSOL3xxx`: backend language-shape limitations
- `QSOL4xxx`: CLI/targeting/plugin resolution/preparation
- `QSOL5xxx`: runtime execution

Backend graph encoders use `QSOL330x` diagnostics for grounded graph data or
graph-unknown encoding failures, for example a graph unknown referencing a graph
that did not materialize during grounding.

`src/qsol/backend/graph_encoding.py` owns shared graph encoding utilities:
canonical undirected edge lookup, graph unknown labels, matching/maximality
constraints, rooted connectivity flow constraints, internal forest acyclicity
constraints, and directed topological-order constraints. These utilities are
backend internals and should not leak low-level flow, rank, or cycle-enumeration
syntax into QSOL source.

## 8. Test Suite Map

- `tests/parser/`: grammar + AST builder
- `tests/sema/`: resolver/typechecker
- `tests/lower/`: desugar/lower
- `tests/backend/`: grounding/codegen/export behavior
- `tests/targeting/`: registry/resolution/compatibility/pipeline branches
- `tests/cli/`: end-user command behavior
- `tests/golden/`: diagnostic rendering/stability

Run all checks:

```bash
uv run pre-commit run --all-files
uv run pytest
```
