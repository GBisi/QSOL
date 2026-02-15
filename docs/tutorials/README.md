# QSOL Tutorials

These tutorials walk from first model to target-aware build/solve workflows.

## Tutorial List

1. `01-first-program.md`
   - Write a minimal QSOL program
   - Inspect frontend stages with `inspect parse|check|lower`
   - Run target support checks and first solve

2. `02-writing-your-own-model.md`
   - Build a custom optimization model from scratch
   - Use `Subset`, `Mapping`, custom unknowns, constraints, and objectives
   - Validate with `targets check` and run with `solve`

3. `03-compiling-running-and-reading-results.md`
   - Discover runtimes with `targets list` (backend is implicit in CLI workflows)
   - Understand `capability_report.json` and build artifacts
   - Read standardized `run.json` output

4. `04-custom-unknowns-functions-and-predicates.md`
   - Define top-level reusable `predicate` and `function` macros
   - Build custom `unknown` types with `rep`, `laws`, and `view`
   - Use custom modules from problem files with concrete examples

## Prerequisites

```bash
uv sync --extra dev
uv run qsol -h
```

If the CLI help opens, you are ready.
