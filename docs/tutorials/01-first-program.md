# Tutorial 1: Your First QSOL Program

Goal: write and run a minimal QSOL model end to end with explicit runtime targeting.

## 1. Model

Create `first_program.qsol`:

```qsol
use stdlib.logic;

problem FirstProgram {
  set Items;
  param Value[Items] : Real = 1;

  find Pick : Subset(Items);

  must exactly(2, Pick.has(i) for i in Items);
  maximize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
```

Ready-to-run copy:
- `examples/tutorials/first_program.qsol`

## 2. Config + Scenario Data

Create `first_program.qsol.toml`:

```toml
schema_version = "1"

[entrypoint]
scenario = "baseline"
runtime = "local-dimod"

[scenarios.baseline]
problem = "FirstProgram"

[scenarios.baseline.sets]
Items = ["i1", "i2", "i3", "i4"]

[scenarios.baseline.params.Value]
i1 = 3
i2 = 8
i3 = 5
i4 = 2
```

Ready-to-run copy:
- `examples/tutorials/first_program.qsol.toml`

`entrypoint` is optional. CLI flags override config defaults.

## 3. Inspect Frontend Stages

Parse:

```bash
uv run qsol inspect parse examples/tutorials/first_program.qsol --json
```

Type/semantic checks:

```bash
uv run qsol inspect check examples/tutorials/first_program.qsol
```

Lowered symbolic IR:

```bash
uv run qsol inspect lower examples/tutorials/first_program.qsol --json
```

## 4. Check Target Support

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod
```

This writes `capability_report.json` and hard-fails if unsupported.

## 5. Build Artifacts

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

Artifacts in `outdir/first_program`:
- `model.cqm`
- `model.bqm`
- `qubo.json`
- `varmap.json`
- `explain.json`
- `capability_report.json`
- `qsol.log`

## 6. Solve

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

This also writes `run.json`.

## 7. Reading Your Results

After `solve` completes, check the output directory (`outdir/first_program/`):

- **`run.json`** — The primary result file. Contains `energy` (objective value), `solution` (decoded high-level assignments like `Pick.has(i2)`), `is_feasible` (whether all hard constraints are satisfied), and `sample` (raw 0/1 variable values).
- **`varmap.json`** — Maps each high-level QSOL variable name (e.g., `Pick.has(i1)`) to the solver's internal integer index. Useful for debugging or cross-checking raw samples.
- **`explain.json`** — Compiler diagnostics (warnings, info) with source-level spans. Check this if a constraint behaves unexpectedly.
- **`capability_report.json`** — Shows which model features (e.g., "quadratic constraints") the backend supports. Useful when `targets check` reports issues.
- **`model.cqm` / `model.bqm`** — Binary serialized solver models. Load in Python with `dimod` for advanced inspection.
- **`qubo.json`** — (If `--format qubo` was used) The flattened QUBO in JSON format (linear/quadratic terms).

> For a full description of all artifacts, see [Compiler Architecture — Output Directory](../COMPILER.md#2-output-directory-structure).

## 8. Quick Troubleshooting

- `QSOL1001`: syntax issue (often missing semicolon).
- `QSOL2101`: type issue (method call target/arity mismatch).
- `QSOL2201`: scenario payload shape mismatch.
- `QSOL3001`: backend-lowering limitation for valid language shape. See [Backend V1 Limits](../BACKEND_V1_LIMITS.md) for supported and unsupported patterns.
- `QSOL4006`: runtime not resolved from CLI or config `entrypoint.runtime` / `execution.runtime`.
- `QSOL4007`: unknown runtime/backend id.
- `QSOL4008`: incompatible runtime/backend pair.
- `QSOL4009`: plugin loading/config issue.
- `QSOL5001`: runtime execution failure.
