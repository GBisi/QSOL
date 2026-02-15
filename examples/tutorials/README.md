# Tutorial Examples

These examples back `docs/tutorials/` and provide small end-to-end models for target-aware workflows.

## Files

- `first_program.qsol`
- `first_program.qsol.toml`
- `assignment_balance.qsol`
- `assignment_balance.qsol.toml`

## Run

From repository root (`/Users/gbisi/Documents/code/qsol`):

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml
```

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

```bash
uv run qsol solve \
  examples/tutorials/assignment_balance.qsol \
  --config examples/tutorials/assignment_balance.qsol.toml \
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

## Scenario Knobs

- `first_program.qsol.toml`
  - `scenarios.baseline.sets.Items`
  - `scenarios.baseline.params.Value[item]`
- `assignment_balance.qsol.toml`
  - `scenarios.baseline.sets.Tasks`
  - `scenarios.baseline.sets.Workers`
  - `scenarios.baseline.params.Cost[worker][task]`
  - optional `entrypoint.runtime`

## Related

- [Examples index](../README.md)
- [QSOL tutorials index](../../docs/tutorials/README.md)
- [Tutorial 3](../../docs/tutorials/03-compiling-running-and-reading-results.md)
