# Tutorial 3: Build, Solve, and Read Results

Goal: understand the target-aware CLI workflow, how to write instance JSON, and how to read every output file in `outdir/`.

This tutorial uses `examples/tutorials/first_program.qsol`.

## 1. Target Discovery

List available targets:

```bash
uv run qsol targets list
```

Inspect capability catalogs:

```bash
uv run qsol targets capabilities \
  --runtime local-dimod

uv run qsol targets capabilities \
  --runtime qiskit
```

## 2. Instance File Syntax and Authoring

QSOL instance files are JSON objects with this shape:

```json
{
  "problem": "FirstProgram",
  "sets": {
    "Items": ["i1", "i2", "i3", "i4"]
  },
  "params": {
    "Value": {
      "i1": 3,
      "i2": 8,
      "i3": 5,
      "i4": 2
    }
  },
  "execution": {
    "runtime": "local-dimod",
    "plugins": []
  }
}
```

Field rules:
- `problem`: optional problem selector by name.
- `sets`: required object; each declared set must map to a JSON array.
- `params`: optional object; required params without model defaults must be provided.
- `execution`: optional object for target defaults and plugin bundle specs.
- `execution.runtime`: optional runtime id.
- `execution.plugins`: optional array of `module:attribute` strings.

Validation notes:
- `execution.plugins` must be an array of non-empty strings.
- Leave it absent (or `[]`) when you only use built-in/entry-point plugins.
- Invalid plugin config reports `QSOL4009`.

## 3. Support Check Before Build

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --log-level debug
```

`targets check` hard-fails on unsupported model+instance+target combinations.

## 4. Build Artifacts

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

## 5. Solve

Exact solver:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

Top-3 solutions with an energy guard:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program_multi \
  --runtime-option sampler=exact \
  --solutions 3 \
  --energy-max 0
```

Qiskit QAOA on a fake IBM backend (writes OpenQASM3):

```bash
uv sync --extra qiskit
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime qiskit \
  --out outdir/first_program_qiskit \
  --runtime-option algorithm=qaoa \
  --runtime-option fake_backend=FakeManilaV2 \
  --runtime-option shots=1024 \
  --runtime-option reps=2
```

## 6. Output Directory Structure (`outdir/...`)

`--out <dir>` is the root output directory for each command.

Files by command:

| File | `targets check` | `build` | `solve` |
| --- | --- | --- | --- |
| `capability_report.json` | yes | yes | yes |
| `qsol.log` | yes | yes | yes |
| `model.cqm` | no | yes | yes |
| `model.bqm` | no | yes | yes |
| `qubo.json` or `ising.json` | no | yes | yes |
| `varmap.json` | no | yes | yes |
| `explain.json` | no | yes | yes |
| `run.json` | no | no | yes |
| `qaoa.qasm` | no | no | sometimes (Qiskit runtime + `algorithm=qaoa`) |

Detailed file contents:

- `capability_report.json`
  - Selection: chosen runtime/backend ids.
  - `supported`: overall compatibility verdict.
  - `required_capabilities`: features required by grounded model.
  - Backend/runtime capability catalogs.
  - `model_summary` stats.
  - `issues`: structured compatibility or capability failures.

- `qsol.log`
  - CLI and pipeline logs according to `--log-level`.

- `model.cqm`
  - Serialized dimod CQM artifact in binary format.

- `model.bqm`
  - Serialized dimod BQM artifact in binary format.

- `qubo.json`
  - Objective as QUBO payload with `offset` and `terms` entries (`u`, `v`, `bias`).

- `ising.json`
  - Objective as Ising payload with `offset`, linear `h`, and quadratic `j` entries.

- `varmap.json`
  - Maps compiled variable labels (for example `Pick.has[i2]`) to model-level meaning strings (for example `Pick.has(i2)`).

- `explain.json`
  - Backend diagnostic list emitted during codegen/export.

- `run.json`
  - Runtime output contract (`schema_version`, `runtime`, `backend`, `status`, `energy`, `reads`, `best_sample`, `selected_assignments`, `timing_ms`, `capability_report_path`, `extensions`).
  - `extensions.solutions` appears when multi-solution features are requested.
  - `extensions.energy_threshold` appears when `--energy-min/--energy-max` are used.
  - `extensions.openqasm_path` appears for Qiskit QAOA runs.

- `qaoa.qasm`
  - OpenQASM 3 circuit export for Qiskit QAOA runs.
  - Written only when runtime is `qiskit` and `algorithm=qaoa`.

Threshold behavior:
- Threshold checks are inclusive and apply to all returned solutions.
- If any returned solution violates thresholds, `run.json` is still written.
- In that case, solve exits non-zero and `status` is `threshold_failed`.

## 7. Selection and Plugin Precedence

Runtime selection order:

1. CLI: `--runtime`
2. Instance default: `execution.runtime`

If unresolved, QSOL emits `QSOL4006`.
Backend selection is implicit for CLI workflows and defaults to `dimod-cqm-v1`.

Plugin loading order for `targets check`, `build`, and `solve`:

1. Built-in plugins.
2. Installed entry-point plugins (`qsol.backends`, `qsol.runtimes`).
3. Instance defaults in `execution.plugins`.
4. CLI `--plugin module:attribute`.

Instance and CLI plugin specs are merged in order with exact-string deduplication.

## 8. Stage-by-Stage Debugging

1. `uv run qsol inspect parse model.qsol --json`
2. `uv run qsol inspect check model.qsol`
3. `uv run qsol inspect lower model.qsol --json`
4. `uv run qsol targets check model.qsol -i model.instance.json --runtime <id>`
5. `uv run qsol build model.qsol -i model.instance.json --runtime <id> -o outdir/model`
6. `uv run qsol solve model.qsol -i model.instance.json --runtime <id> -o outdir/model`

## 9. Common Diagnostics

- `QSOL1001`: parse grammar mismatch
- `QSOL2101`: type/arity mismatch
- `QSOL2201`: instance schema/shape mismatch
- `QSOL3001`: backend unsupported language shape
- `QSOL4006`: runtime not resolved
- `QSOL4007`: unknown runtime/backend id
- `QSOL4008`: incompatible runtime/backend pair
- `QSOL4009`: plugin loading failure or invalid plugin config
- `QSOL4010`: unsupported required capability for selected target
- `QSOL5001`: runtime execution failure
- `QSOL5002`: runtime policy/output contract failure (for example threshold rejection)

For target failures, inspect:
- CLI diagnostics
- `capability_report.json`
- `explain.json` (backend-specific)
