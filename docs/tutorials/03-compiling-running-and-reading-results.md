# Tutorial 3: Compile, Run, and Read Results

Goal: understand the full CLI workflow and what each output artifact means.

This tutorial uses `examples/tutorials/first_program.qsol`.

## 1. Compile Command Anatomy

```bash
uv run qsol compile \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --out outdir/first_program \
  --format qubo \
  --log-level debug
```

Key flags:
- `--instance` (`-i`): JSON instance payload
- `--out` (`-o`): output folder
- `--format` (`-f`): exported payload flavor (`qubo` or `ising`)
- `--log-level` (`-l`): logging verbosity

## 2. Output Files

After compile, inspect:

- `model.cqm`: constrained model before CQM->BQM conversion
- `model.bqm`: binary quadratic model used for sampling
- `qubo.json` or `ising.json`: coefficient export
- `varmap.json`: maps backend variable labels to QSOL semantics
- `explain.json`: backend diagnostic list
- `qsol.log`: execution log

## 3. Run and Sampling

Run with exact solver:

```bash
uv run qsol run \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --out outdir/first_program \
  --sampler exact
```

Run with simulated annealing:

```bash
uv run qsol run \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --out outdir/first_program_sa \
  --sampler simulated-annealing \
  --num-reads 200 \
  --seed 7
```

## 4. Understanding `run.json`

`run.json` contains:
- sampler metadata (`sampler`, `num_reads`, `seed`)
- best energy
- full best sample bit-vector
- `selected_assignments`: only variables set to `1`, decoded with human-readable meaning

Example snippet:

```json
{
  "sampler": "exact",
  "energy": -13.0,
  "selected_assignments": [
    {"variable": "Pick.has[i2]", "meaning": "Pick.has(i2)", "value": 1},
    {"variable": "Pick.has[i3]", "meaning": "Pick.has(i3)", "value": 1}
  ]
}
```

## 5. Stage-by-Stage Debugging

When something fails, use this order:

1. Syntax stage:

```bash
uv run qsol compile model.qsol --parse --json
```

2. Semantic/type stage:

```bash
uv run qsol compile model.qsol --check
```

3. Lowering stage:

```bash
uv run qsol compile model.qsol --lower --json
```

4. Backend stage:

```bash
uv run qsol compile model.qsol -i model.instance.json -o outdir/model
```

## 6. Diagnosing Common Errors

QSOL CLI diagnostics are rustc-style by default:

```text
error[QSOL2201]: missing set values for `Items`
  --> model.qsol:2:3
   |
  2 |   set Items;
   |   ^^^^^^^^^
   = help: Add `sets.Items` as a JSON array in the instance payload.
aborting due to 1 error(s), 0 warning(s), 0 info message(s)
```

- `QSOL1001`: parse grammar mismatch
  - Often missing semicolons or malformed comprehensions
- `QSOL2001`: unknown set/identifier/unknown type reference
- `QSOL2101`: invalid types or method arity
- `QSOL2201`: instance schema/shape mismatch
- `QSOL3001`: backend unsupported expression/unknown kind
- `QSOL400x`: CLI/runtime-preparation issues (invalid flags, missing files, artifact load errors)
- `QSOL500x`: sampler/runtime execution failures

For backend errors, inspect both:
- CLI diagnostic output
- `outdir/<model>/explain.json`

Run-specific examples:

- Missing inferred instance (`run` without `--instance` and no `<model>.instance.json`):
  - emits `QSOL4002` with a suggestion to create the default instance file or pass `--instance`.
- Corrupt/missing artifacts after compile:
  - emits `QSOL4005` with guidance to regenerate artifacts.
- Sampler crashes or rejects payload:
  - emits `QSOL5001` and suggests retrying with `--sampler exact`.
