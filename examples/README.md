# QSOL Examples

This index points to runnable QSOL example folders and the main command to start each one.

| Example | Summary | Primary command | Details |
| --- | --- | --- | --- |
| `tutorials/` | Tutorial starter models used by the docs walkthroughs | `uv run qsol solve examples/tutorials/first_program.qsol --config examples/tutorials/first_program.qsol.toml --runtime local-dimod --out outdir/first_program --runtime-option sampler=exact` | [`examples/tutorials/README.md`](tutorials/README.md) |
| `simple_subset/` | Minimal subset selection model | `uv run qsol solve examples/simple_subset/simple_subset.qsol --runtime local-dimod --out outdir/simple_subset` | — |
| `generic_bqm/` | Generic unconstrained binary quadratic objective (`L`, `Q`, `C`) | `uv run python examples/generic_bqm/test_equivalence.py` | [`examples/generic_bqm/README.md`](generic_bqm/README.md) |
| `min_bisection/` | Balanced graph bisection that minimizes cut edges | `uv run python examples/min_bisection/test_equivalence.py` | [`examples/min_bisection/README.md`](min_bisection/README.md) |
| `partition_equal_sum/` | Number partitioning into two equal-sum subsets | `uv run python examples/partition_equal_sum/test_equivalence.py` | [`examples/partition_equal_sum/README.md`](partition_equal_sum/README.md) |

`examples/run_equivalence_suite.py` runs all example equivalence scripts together.

```bash
uv run python examples/run_equivalence_suite.py
```
