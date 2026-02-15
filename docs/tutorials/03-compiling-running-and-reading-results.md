# Tutorial 3: Build, Solve, and Read Results

Goal: understand the target-aware CLI workflow and output artifacts.

This tutorial uses `examples/tutorials/first_program.qsol`.

## 1. Target Discovery

List available targets:

```bash
uv run qsol targets list
```

Inspect pair capability catalogs:

```bash
uv run qsol targets capabilities \
  --runtime local-dimod \
  --backend dimod-cqm-v1
```

## 2. Support Check Before Build

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program \
  --log-level debug
```

Outputs:
- `outdir/first_program/capability_report.json`
- `outdir/first_program/qsol.log`

`targets check` hard-fails on unsupported model+instance+target combinations.

## 3. Build Artifacts

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program \
  --format qubo
```

Build outputs:
- `model.cqm`
- `model.bqm`
- `qubo.json` or `ising.json`
- `varmap.json`
- `explain.json`
- `capability_report.json`
- `qsol.log`

## 4. Solve

Exact solver:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

Simulated annealing:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program_sa \
  --runtime-option sampler=simulated-annealing \
  --runtime-option num_reads=200 \
  --runtime-option seed=7
```

Top-3 solutions with an energy guard:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program_multi \
  --runtime-option sampler=exact \
  --solutions 3 \
  --energy-max 0
```

## 5. Understanding `run.json`

`run.json` has a stable core schema:
- `schema_version`
- `runtime`, `backend`
- `status`
- `energy`, `reads`
- `best_sample`
- `selected_assignments`
- `timing_ms`
- `capability_report_path`
- `extensions` (runtime-specific fields)

When `--solutions` is used, `extensions` includes:
- `requested_solutions`
- `returned_solutions`
- `solutions` (ordered candidates with `rank`, `energy`, `num_occurrences`, `sample`, `selected_assignments`)

When `--energy-min`/`--energy-max` are used, `extensions.energy_threshold` records:
- `min`, `max`
- `scope` (`all_returned`)
- `inclusive` (`true`)
- `passed`
- `violations`

Threshold behavior:
- Threshold checks are inclusive and apply to all returned solutions.
- If any returned solution violates thresholds, `run.json` is still written.
- In that case, solve exits non-zero and `status` is `threshold_failed`.

Example snippet:

```json
{
  "schema_version": "1.0",
  "runtime": "local-dimod",
  "backend": "dimod-cqm-v1",
  "status": "ok",
  "energy": -13.0,
  "selected_assignments": [
    {"variable": "Pick.has[i2]", "meaning": "Pick.has(i2)", "value": 1}
  ],
  "extensions": {
    "sampler": "exact",
    "requested_solutions": 3,
    "returned_solutions": 3
  }
}
```

## 6. Selection Precedence

Runtime/backend resolution order:

1. CLI: `--runtime`, `--backend`
2. Instance defaults: `execution.runtime`, `execution.backend`

If unresolved, QSOL emits `QSOL4006`.

## 7. Stage-by-Stage Debugging

1. `uv run qsol inspect parse model.qsol --json`
2. `uv run qsol inspect check model.qsol`
3. `uv run qsol inspect lower model.qsol --json`
4. `uv run qsol targets check model.qsol -i model.instance.json --runtime <id> --backend <id>`
5. `uv run qsol build model.qsol -i model.instance.json --runtime <id> --backend <id> -o outdir/model`
6. `uv run qsol solve model.qsol -i model.instance.json --runtime <id> --backend <id> -o outdir/model`

## 8. Common Diagnostics

- `QSOL1001`: parse grammar mismatch
- `QSOL2101`: type/arity mismatch
- `QSOL2201`: instance schema/shape mismatch
- `QSOL3001`: backend unsupported language shape
- `QSOL4006`: runtime/backend not resolved
- `QSOL4007`: unknown runtime/backend id
- `QSOL4008`: incompatible runtime/backend pair
- `QSOL4009`: plugin loading failure
- `QSOL4010`: unsupported required capability for selected target
- `QSOL5001`: runtime execution failure
- `QSOL5002`: runtime policy/output contract failure (for example threshold rejection)

For target failures, inspect:
- CLI diagnostics
- `capability_report.json`
- `explain.json` (backend-specific)
