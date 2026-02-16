# Tutorial 3: Build, Solve, and Read Results

Goal: understand the target-aware CLI workflow, how to write config TOML with scenarios, and how to read outputs in `outdir/`.

This tutorial uses `examples/tutorials/first_program.qsol`.

If your model imports reusable unknowns/macros, use dotted module imports:

```qsol
use stdlib.permutation;
use stdlib.logic;
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

[entrypoint]
scenario = "baseline"
combine_mode = "intersection"
failure_policy = "run-all-fail"
runtime = "local-dimod"
plugins = []
runtime_options = { sampler = "exact" }
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
- `entrypoint`: optional CLI-equivalent defaults (`scenario`/`scenarios`/`all_scenarios`, `runtime`, `backend`, `plugins`, `runtime_options`, `solutions`, `energy_min`, `energy_max`, `out`, `format`, `combine_mode`, `failure_policy`).
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

For `algorithm=qaoa`, QSOL auto-wires backend transpilation using
`pass_manager`/`transpiler` according to the installed Qiskit package variant.

Solve terminal output:
- `Run Summary` reports status/runtime/backend, solve thresholds, and `Runtime Parameters`
  (resolved runtime option values including defaults).
- `Returned Solutions` lists every returned solution row with rank/energy/compact sample summary plus
  optional metadata (`num_occurrences`, `probability`, `status`, `scenario_energies`) when present.
- `Selected Assignments` still summarizes the best solution assignment meanings.

## 6. Output Directory and Artifacts (`outdir/...`)

When you run `build` or `solve`, QSOL generates several artifacts in the output directory.

### Key Files

#### `run.json`
The primary result file. Contains:
- `energy`: The objective value of the best solution found.
- `solution`: The decoded high-level solution (e.g., `ColorOf: { N1: Red, ... }`).
- `is_feasible`: Boolean indicating if all hard constraints were satisfied.
- `sample`: The raw low-level variable assignments (0/1).

#### `varmap.json`
Maps your high-level QSOL variables to the solver's low-level indices.
- Key: The high-level name (e.g., `ColorOf.is(n1, Red)`).
- Value: The integer index used in the CQM/BQM.
Useful for debugging raw solver outputs or understanding variable counts.

#### `model.cqm` / `model.bqm`
The compiled model in binary format (Python pickle of `dimod.ConstrainedQuadraticModel` or `dimod.BinaryQuadraticModel`).
- **CQM**: Contains constraints and objectives.
- **BQM**: If the backend supports it, a purely binary quadratic model (often used for annealing).
You can load these in Python with `dimod.serialization.file.load` to inspect or run them manually.

#### `explain.json`
Contains compiler diagnostics (warnings, errors) mapped to specific lines in your source code. Use this to trace back why a constraint might be behaving unexpectedly or to see optimization hints.

#### `capability_report.json`
A report listing the QSOL features used by your model (e.g., "quadratic constraints", "inequality constraints") and confirming that the selected backend supports them.

### Multi-Scenario Structure

If you run with multiple scenarios, the output is organized hierarchically:
- `outdir/run.json`: Aggregated results for all scenarios.
- `outdir/scenarios/<scenario_name>/...`: Per-scenario artifacts (model, varmap, etc.).

Multi-scenario aggregate run extensions include:
- `selected_scenarios`
- `combine_mode`
- `failure_policy`
- `scenario_results`
- merged `solutions` metadata (`requested_solutions`, `returned_solutions`)

## 7. Selection and Plugin Precedence

Runtime selection order:
1. CLI: `--runtime`
2. Scenario config: `execution.runtime`
3. Config `entrypoint.runtime`
4. Legacy config `defaults.execution.runtime`

If unresolved, QSOL emits `QSOL4006`.
Backend selection is implicit for CLI workflows and defaults to `dimod-cqm-v1`.

Plugin loading order for `targets check`, `build`, and `solve`:
1. Built-in plugins
2. Installed entry-point plugins (`qsol.backends`, `qsol.runtimes`)
3. Config `execution.plugins` (scenario -> `entrypoint` -> legacy defaults)
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
- `QSOL3001`: backend unsupported language shape. See [Backend V1 Limits](../BACKEND_V1_LIMITS.md) for supported and unsupported patterns.
- `QSOL4002`: config not found/ambiguous discovery
- `QSOL4004`: config TOML load/validation failure
- `QSOL4006`: runtime not resolved
- `QSOL4007`: unknown runtime/backend id
- `QSOL4008`: incompatible runtime/backend pair
- `QSOL4009`: plugin loading failure or invalid plugin config
- `QSOL4010`: unsupported required capability for selected target
- `QSOL5001`: runtime execution failure
- `QSOL5002`: runtime policy/output contract failure
