# Tutorial 3: Build, Solve, and Read Results

Goal: understand the target-aware CLI workflow, how to write config TOML with scenarios, and how to read outputs in `outdir/`.

This tutorial uses `examples/tutorials/first_program.qsol`.

If your model imports reusable unknowns, use dotted module imports:

```qsol
use stdlib.permutation;
use mylib.graph.unknowns;
```

## 1. Target Discovery

List available targets:

```bash
uv run qsol targets list
```

Inspect capability catalogs:

```bash
uv run qsol targets capabilities --runtime local-dimod
uv run qsol targets capabilities --runtime qiskit
```

## 2. Config File Syntax and Authoring

QSOL uses TOML config files (`*.qsol.toml`). Example:

```toml
schema_version = "1"

[selection]
default_scenario = "baseline"
combine_mode = "intersection"
failure_policy = "run-all-fail"

[defaults.execution]
runtime = "local-dimod"
plugins = []

[defaults.solve]
solutions = 3
energy_max = 0

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

Field rules:
- `schema_version`: currently must be `"1"`.
- `selection`: scenario selection defaults (`mode`, `default_scenario`, `subset`, `combine_mode`, `failure_policy`).
- `defaults.execution`: default runtime/backend/plugins.
- `defaults.solve`: default solve controls (`solutions`, `energy_min`, `energy_max`).
- `scenarios.<name>`: scenario payload (`problem`, `sets`, `params`, optional `execution`, optional `solve`).

Auto-discovery when `--config` is omitted:
- Search only `*.qsol.toml` in the model directory.
- If one file exists, use it.
- If multiple files exist, use `<model>.qsol.toml` when present; otherwise fail with `QSOL4002`.

## 3. Support Check Before Build

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program
```

Run all scenarios:

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --all-scenarios \
  --failure-policy run-all-fail
```

## 4. Build Artifacts

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

## 5. Solve

Single scenario:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

Multi-scenario solve with union merge:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --all-scenarios \
  --combine-mode union \
  --failure-policy best-effort \
  --out outdir/first_program_multi \
  --runtime-option sampler=exact
```

Qiskit QAOA:

```bash
uv sync --extra qiskit
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime qiskit \
  --out outdir/first_program_qiskit \
  --runtime-option algorithm=qaoa \
  --runtime-option fake_backend=FakeManilaV2 \
  --runtime-option shots=1024 \
  --runtime-option reps=2
```

## 6. Output Directory Structure (`outdir/...`)

Single-scenario outputs:
- `capability_report.json`
- `qsol.log`
- `model.cqm`, `model.bqm`
- `qubo.json` or `ising.json`
- `varmap.json`
- `explain.json`
- `run.json` (solve)
- `qaoa.qasm` (Qiskit QAOA only)

Multi-scenario outputs:
- Per-scenario files under `outdir/scenarios/<scenario_name>/...`
- Top-level aggregate `run.json` for multi-scenario solve
- Top-level summary file (`capability_report.json` for check/solve, `build_summary.json` for build)

Multi-scenario aggregate run extensions include:
- `selected_scenarios`
- `combine_mode`
- `failure_policy`
- `scenario_results`
- merged `solutions` metadata (`requested_solutions`, `returned_solutions`)

## 7. Selection and Plugin Precedence

Runtime selection order:
1. CLI: `--runtime`
2. Scenario/default config: `execution.runtime`

If unresolved, QSOL emits `QSOL4006`.
Backend selection is implicit for CLI workflows and defaults to `dimod-cqm-v1`.

Plugin loading order for `targets check`, `build`, and `solve`:
1. Built-in plugins
2. Installed entry-point plugins (`qsol.backends`, `qsol.runtimes`)
3. Config `execution.plugins`
4. CLI `--plugin module:attribute`

Scenario/default plugin specs and CLI plugin specs are merged with exact-string deduplication.

## 8. Stage-by-Stage Debugging

1. `uv run qsol inspect parse model.qsol --json`
2. `uv run qsol inspect check model.qsol`
3. `uv run qsol inspect lower model.qsol --json`
4. `uv run qsol targets check model.qsol -c model.qsol.toml --runtime <id>`
5. `uv run qsol build model.qsol -c model.qsol.toml --runtime <id> -o outdir/model`
6. `uv run qsol solve model.qsol -c model.qsol.toml --runtime <id> -o outdir/model`

## 9. Common Diagnostics

- `QSOL1001`: parse grammar mismatch
- `QSOL2001`: unknown symbol/module/import path
- `QSOL2101`: type/arity mismatch, import cycles, or invalid imported top-level items
- `QSOL2201`: scenario payload schema/shape mismatch after materialization
- `QSOL3001`: backend unsupported language shape
- `QSOL4002`: config not found/ambiguous discovery
- `QSOL4004`: config TOML load/validation failure
- `QSOL4006`: runtime not resolved
- `QSOL4007`: unknown runtime/backend id
- `QSOL4008`: incompatible runtime/backend pair
- `QSOL4009`: plugin loading failure or invalid plugin config
- `QSOL4010`: unsupported required capability for selected target
- `QSOL5001`: runtime execution failure
- `QSOL5002`: runtime policy/output contract failure
