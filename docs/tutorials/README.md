# QSOL Tutorials

These tutorials walk from first model to inspecting solver output.

## Tutorial List

1. `01-first-program.md`
   - Write a minimal QSOL program
   - Stage checks via `compile --parse/--check/--lower`
   - Compile and run with a small instance

2. `02-writing-your-own-model.md`
   - Build a custom optimization model from scratch
   - Use `Subset`, `Mapping`, constraints, and objectives
   - Keep models backend-v1 compatible

3. `03-compiling-running-and-reading-results.md`
   - Use CLI options effectively
   - Understand generated artifacts (`model.bqm`, `varmap.json`, `run.json`, etc.)
   - Debug unsupported patterns with diagnostics

## Prerequisites

```bash
uv sync --extra dev
```

From repository root (`qsol`):

```bash
uv run qsol -h
```

If that command works, you are ready.
