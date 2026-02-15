# Min Bisection Example

This example models equal-size graph partitioning: split vertices `V` into two balanced sides and minimize the number of crossing edges defined by endpoint mappings `U` and `W` over edge set `E`.

## Files

- `min_bisection.qsol`: QSOL model
- `min_bisection.instance.json`: sample graph instance
- `test_equivalence.py`: custom-vs-compiled BQM equivalence check

## Run

From repository root (`/Users/gbisi/Documents/code/qsol`):

```bash
uv run qsol targets check \
  examples/min_bisection/min_bisection.qsol \
  --instance examples/min_bisection/min_bisection.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1
```

```bash
uv run qsol build \
  examples/min_bisection/min_bisection.qsol \
  --instance examples/min_bisection/min_bisection.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/min_bisection \
  --format qubo
```

```bash
uv run qsol solve \
  examples/min_bisection/min_bisection.qsol \
  --instance examples/min_bisection/min_bisection.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/min_bisection \
  --runtime-option sampler=exact
```

```bash
uv run python examples/min_bisection/test_equivalence.py
```

```bash
uv run python examples/min_bisection/test_equivalence.py --simulated-annealing --num-reads 200
```

## Expected Result

- `test_equivalence.py` exits with status `0`.
- Runtime equivalence is the acceptance criterion for this example.
- Structural mismatch is informational-only for this example; structural equivalence may still pass for the provided instance.

## Instance Knobs

- `sets.V`: vertex identifiers
- `sets.E`: edge identifiers
- `params.U[e]`, `params.W[e]`: edge endpoints in `V`
- `params.PenaltyA`: balance-constraint penalty weight
- `params.WeightB`: edge-cut weight (optional, defaults to `1.0`)

## Related

- [Examples index](../README.md)
- [Tutorial 3: compiling, running, and reading results](../../docs/tutorials/03-compiling-running-and-reading-results.md)
