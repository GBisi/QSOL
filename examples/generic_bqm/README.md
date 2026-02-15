# Generic BQM Example

This example models a generic unconstrained binary quadratic objective in QSOL, with one binary decision variable per element in `Vars` and objective terms from `L`, `Q`, and optional constant `C`.

## Files

- `generic_bqm.qsol`: QSOL model
- `generic_bqm.instance.json`: sample instance payload
- `test_equivalence.py`: custom-vs-compiled BQM equivalence check

## Run

From repository root (`/Users/gbisi/Documents/code/qsol`):

```bash
uv run qsol targets check \
  examples/generic_bqm/generic_bqm.qsol \
  --instance examples/generic_bqm/generic_bqm.instance.json \
  --runtime local-dimod
```

```bash
uv run qsol build \
  examples/generic_bqm/generic_bqm.qsol \
  --instance examples/generic_bqm/generic_bqm.instance.json \
  --runtime local-dimod \
  --out outdir/generic_bqm \
  --format qubo
```

```bash
uv run qsol solve \
  examples/generic_bqm/generic_bqm.qsol \
  --instance examples/generic_bqm/generic_bqm.instance.json \
  --runtime local-dimod \
  --out outdir/generic_bqm \
  --runtime-option sampler=exact
```

```bash
uv run python examples/generic_bqm/test_equivalence.py
```

```bash
uv run python examples/generic_bqm/test_equivalence.py --simulated-annealing --num-reads 200
```

## Expected Result

- `test_equivalence.py` exits with status `0`.
- Structural equivalence and runtime equivalence are both expected to pass for this example.

## Instance Knobs

- `sets.Vars`: variable names used to build binary decision variables
- `params.L[var]`: linear bias per variable
- `params.Q[i][j]`: quadratic bias for pair `(i, j)`
- `params.C`: constant objective offset

## Related

- [Examples index](../README.md)
- [Tutorial 3: compiling, running, and reading results](../../docs/tutorials/03-compiling-running-and-reading-results.md)
