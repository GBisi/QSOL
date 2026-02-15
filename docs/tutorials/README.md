# QSOL Tutorials

These tutorials walk from first model to target-aware build/solve workflows.

## Tutorial List

1. `01-first-program.md`
   - Write a minimal QSOL program
   - Inspect frontend stages with `inspect parse|check|lower`
   - Run target support checks and first solve

2. `02-writing-your-own-model.md`
   - Build a custom optimization model from scratch
   - Use `Subset`, `Mapping`, constraints, and objectives
   - Validate with `targets check` and run with `solve`

3. `03-compiling-running-and-reading-results.md`
   - Discover runtimes/backends with `targets list`
   - Understand `capability_report.json` and build artifacts
   - Read standardized `run.json` output

## Prerequisites

```bash
uv sync --extra dev
uv run qsol -h
```

If the CLI help opens, you are ready.
