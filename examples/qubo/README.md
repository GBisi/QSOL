# QUBO Example Models

This folder contains runnable QSOL models and matching instance files.

## Contents

- `bounded_max_cut.qsol`
- `bounded_max_cut.instance.json`
- `bounded_max_cut.weighted.instance.json`
- `exact_k_subset.qsol`
- `exact_k_subset.instance.json`
- `mapping_collision_penalty.qsol`
- `mapping_collision_penalty.instance.json`

## Compile Examples

```bash
uv run qsol compile examples/qubo/bounded_max_cut.qsol --instance examples/qubo/bounded_max_cut.instance.json --out outdir/bounded_max_cut --format qubo
uv run qsol compile examples/qubo/bounded_max_cut.qsol --instance examples/qubo/bounded_max_cut.weighted.instance.json --out outdir/bounded_max_cut_weighted --format qubo
uv run qsol compile examples/qubo/mapping_collision_penalty.qsol --instance examples/qubo/mapping_collision_penalty.instance.json --out outdir/mapping_collision_penalty --format qubo
uv run qsol compile examples/qubo/exact_k_subset.qsol --instance examples/qubo/exact_k_subset.instance.json --out outdir/exact_k_subset --format qubo
```

## Run Examples

Exact solver:

```bash
uv run qsol run examples/qubo/bounded_max_cut.qsol --instance examples/qubo/bounded_max_cut.instance.json --out outdir/bounded_max_cut --sampler exact
uv run qsol run examples/qubo/bounded_max_cut.qsol --instance examples/qubo/bounded_max_cut.weighted.instance.json --out outdir/bounded_max_cut_weighted --sampler exact
uv run qsol run examples/qubo/mapping_collision_penalty.qsol --instance examples/qubo/mapping_collision_penalty.instance.json --out outdir/mapping_collision_penalty --sampler exact
uv run qsol run examples/qubo/exact_k_subset.qsol --instance examples/qubo/exact_k_subset.instance.json --out outdir/exact_k_subset --sampler exact
```

Simulated annealing (default sampler):

```bash
uv run qsol run examples/qubo/exact_k_subset.qsol --instance examples/qubo/exact_k_subset.instance.json --out outdir/exact_k_subset_sa --sampler simulated-annealing --num-reads 200 --seed 7
```

## Notes

`bounded_max_cut.qsol` supports weighted and unweighted runs:
- If `LinkWeight` is omitted, default value `1` is used.
- If `LinkWeight` is provided, those values drive edge-cut gain.

For beginner walkthroughs, see:
- `docs/tutorials/README.md`
