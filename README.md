# QSOL

QSOL is a declarative modeling language and compiler for combinatorial optimization.

You describe sets, parameters, unknown structures (`Subset`, `Mapping`), constraints, and objectives. QSOL compiles the model plus instance data into dimod artifacts (CQM/BQM + QUBO/Ising export), and can run local samplers.

Pipeline:

`QSOL -> AST -> semantic/type checks -> desugaring -> symbolic IR -> grounded IR -> dimod CQM/BQM -> exported artifacts`

## Current Scope (v1)

Implemented and stable:
- Parsing with Lark (`src/qsol/parse/grammar.lark`)
- Source-spanned AST and diagnostics
- Name resolution and type checking
- Desugaring for guards and aggregate sugar (`if`, `where`, `else`, `count`, `any`, `all`)
- Symbolic and grounded IR
- dimod backend for core patterns
- CLI workflows: `compile`, `run`

Important limitation:
- The grammar/type system accepts more forms than backend v1 can encode. Unsupported codegen shapes are reported as `QSOL3001` during `compile`/`run`.

Backend behavior note:
- `must` constraints enforce hard feasibility; `should` and `nice` are soft-only weighted penalties.
- Hard `!=` comparisons are supported for backend-supported numeric expressions using the same `1e-6` tolerance band policy as boolean-context comparisons.

## Diagnostics UX

`compile` and `run` now emit rustc-style diagnostics by default:

- `error[CODE]: message`
- `--> file:line:col`
- source excerpt with caret highlights
- contextual `= note:` and `= help:` lines
- final summary line with error/warning/info counts

Example:

```text
error[QSOL2101]: size() expects a declared set identifier
  --> model.qsol:4:13
   |
  4 |   must size(3) = 1;
   |             ^
   = help: Pass a declared set name, for example `size(V)`.
aborting due to 1 error(s), 0 warning(s), 0 info message(s)
```

Diagnostic code families:
- `QSOL1xxx`: parser diagnostics
- `QSOL2xxx`: semantic/type/instance schema diagnostics
- `QSOL3xxx`: backend support/validation diagnostics
- `QSOL4xxx`: CLI/runtime preparation diagnostics (flags, file IO, artifact loading)
- `QSOL5xxx`: sampler runtime diagnostics

## Install

```bash
uv sync --extra dev
```

## Quickstart

Compile an included example:

```bash
uv run qsol compile \
  examples/qubo/bounded_max_cut.qsol \
  --instance examples/qubo/bounded_max_cut.instance.json \
  --out outdir/bounded_max_cut \
  --format qubo
```

Run it with a sampler:

```bash
uv run qsol run \
  examples/qubo/bounded_max_cut.qsol \
  --instance examples/qubo/bounded_max_cut.instance.json \
  --out outdir/bounded_max_cut \
  --sampler exact
```

Inspect syntax/semantics quickly:

```bash
uv run qsol compile examples/qubo/bounded_max_cut.qsol --parse --json
uv run qsol compile examples/qubo/bounded_max_cut.qsol --check
uv run qsol compile examples/qubo/bounded_max_cut.qsol --lower --json
```

## CLI Reference

```bash
uv run qsol compile <model.qsol> [--parse|--check|--lower] [--json]
uv run qsol compile <model.qsol> [-i <instance.json>] [-o <outdir>] [-f qubo|ising]
uv run qsol run <model.qsol> [-i <instance.json>] [-o <outdir>] [-s exact|simulated-annealing]
```

Defaults:
- Instance path: `<model>.instance.json` if present next to the model
- Output directory: `<cwd>/outdir/<model_stem>`
- `run` sampler: `simulated-annealing` with `--num-reads 100`

## Output Artifacts

`compile` and `run` generate:
- `model.cqm`: dimod constrained quadratic model
- `model.bqm`: dimod binary quadratic model
- `qubo.json` or `ising.json`: exported coefficient payload
- `varmap.json`: binary variable label to QSOL meaning
- `explain.json`: backend diagnostics summary
- `qsol.log`: run/compile log file
- `run.json`: only for `run`, sampler result summary

## Instance Format

```json
{
  "problem": "ProblemName",
  "sets": {
    "A": ["a1", "a2"],
    "B": ["b1"]
  },
  "params": {
    "K": 3
  }
}
```

Rules enforced by instantiation:
- Every declared `set` must be present and must be a JSON array
- Missing scalar params use defaults when provided in model
- Indexed params must match declared index shape

## Documentation

- Vision and design principles: `VISION.md`
- Language reference: `QSOL_reference.md`
- Syntax guide: `docs/QSOL_SYNTAX.md`
- Tutorials: `docs/tutorials/README.md`
- Codebase guide: `docs/CODEBASE.md`
- Tutorial model files: `examples/tutorials/README.md`
- Example models: `examples/generic_bqm/`, `examples/min_bisection/`, `examples/partition_equal_sum/`
- VS Code syntax extension: `editors/vscode-qsol/README.md`

## Python API

```python
from qsol import CompileOptions, compile_source

source = """
problem Demo {
  set A;
  find S : Subset(A);
  must forall x in A: S.has(x) or not S.has(x);
  minimize sum(if S.has(x) then 1 else 0 for x in A);
}
"""

unit = compile_source(source, options=CompileOptions(filename="demo.qsol"))
print(unit.diagnostics)
```

`CompilationUnit` exposes:
- `ast`
- `symbol_table`
- `typed_program`
- `lowered_ir_symbolic`
- `ground_ir`
- `artifacts`
- `diagnostics`

## Development

```bash
uv run pre-commit install
uv run pre-commit run --all-files
uv run pytest
uv run ruff check .
uv run mypy src
```

`pytest` is configured with coverage enforcement (`--cov-fail-under=90`).
