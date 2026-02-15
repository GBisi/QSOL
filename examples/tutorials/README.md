# Tutorial Examples

These examples back `docs/tutorials/` and provide small end-to-end models for target-aware workflows.

## Files

- `first_program.qsol`
- `first_program.instance.json`
- `assignment_balance.qsol`
- `assignment_balance.instance.json`

## Run

From repository root (`/Users/gbisi/Documents/code/qsol`):

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json
```

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

```bash
uv run qsol solve \
  examples/tutorials/assignment_balance.qsol \
  --instance examples/tutorials/assignment_balance.instance.json \
  --runtime local-dimod \
  --out outdir/assignment_balance \
  --runtime-option sampler=exact
```

## Expected Result

Commands succeed and write artifacts under `outdir/*`, including:
- `model.cqm`
- `model.bqm`
- `varmap.json`
- `qubo.json` or `ising.json`
- `capability_report.json`
- `run.json` (for `solve`)

## Instance Knobs

- `first_program.instance.json`
  - `sets.Items`
  - `params.Value[item]`
- `assignment_balance.instance.json`
  - `sets.Tasks`
  - `sets.Workers`
  - `params.Cost[worker][task]`
  - optional `execution.runtime` default

## Related

- [Examples index](../README.md)
- [QSOL tutorials index](../../docs/tutorials/README.md)
- [Tutorial 3](../../docs/tutorials/03-compiling-running-and-reading-results.md)
