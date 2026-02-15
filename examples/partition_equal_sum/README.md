# Partition Equal Sum Example

This example models number partitioning: choose subset `R` of `Items` such that the sum of `Value` over `R` equals the sum over its complement `Items - R`.

## Files

- `partition_equal_sum.qsol`: QSOL model
- `partition_equal_sum.qsol.toml`: sample partition scenario config
- `test_equivalence.py`: custom-vs-compiled BQM equivalence check

## Run

From repository root (`/Users/gbisi/Documents/code/qsol`):

```bash
uv run qsol targets check \
  examples/partition_equal_sum/partition_equal_sum.qsol \
  --config examples/partition_equal_sum/partition_equal_sum.qsol.toml \
  --runtime local-dimod
```

```bash
uv run qsol build \
  examples/partition_equal_sum/partition_equal_sum.qsol \
  --config examples/partition_equal_sum/partition_equal_sum.qsol.toml \
  --runtime local-dimod \
  --out outdir/partition_equal_sum \
  --format qubo
```

```bash
uv run qsol solve \
  examples/partition_equal_sum/partition_equal_sum.qsol \
  --config examples/partition_equal_sum/partition_equal_sum.qsol.toml \
  --runtime local-dimod \
  --out outdir/partition_equal_sum \
  --runtime-option sampler=exact
```

```bash
uv run python examples/partition_equal_sum/test_equivalence.py
```

```bash
uv run python examples/partition_equal_sum/test_equivalence.py --simulated-annealing --num-reads 200
```

## Expected Result

- `test_equivalence.py` exits with status `0`.
- Structural equivalence and runtime equivalence are both expected to pass for this example.

## Scenario Knobs

- `scenarios.baseline.sets.Items`: item identifiers
- `scenarios.baseline.params.Value[item]`: positive numeric weight for each item

## Related

- [Examples index](../README.md)
- [Tutorial 3: compiling, running, and reading results](../../docs/tutorials/03-compiling-running-and-reading-results.md)
