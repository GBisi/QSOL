# Tutorial Examples

These examples back `docs/tutorials/` and provide small end-to-end models for target-aware workflows.

## Files

- `first_program.qsol`
- `first_program.qsol.toml`
- `assignment_balance.qsol`
- `assignment_balance.qsol.toml`
- `graph_coloring.qsol`
- `graph_coloring.qsol.toml`
- `minimum_graph_coloring.qsol`
- `minimum_graph_coloring.qsol.toml`
- `custom_types.qsol`
- `custom_types_usage.qsol`
- `custom_types_usage.qsol.toml`
- `scalar_bool_demo.qsol`
- `scalar_bool_demo.qsol.toml`
- `relation_graph_independent_set.qsol`
- `relation_graph_independent_set.qsol.toml`
- `relation_set_packing.qsol`
- `relation_set_packing.qsol.toml`
- `derived_max_clique.qsol`
- `derived_max_clique.qsol.toml`
- `job_sequencing_max.qsol`
- `job_sequencing_max.qsol.toml`
- `all_different_slots.qsol`
- `all_different_slots.qsol.toml`
- `graph_helpers.qsol`
- `graph_helpers.qsol.toml`
- `route_demo.qsol`
- `route_demo.qsol.toml`
- `weighted_spanning_tree.qsol`
- `weighted_spanning_tree.qsol.toml`
- `route_successor.qsol`
- `route_successor.qsol.toml`
- `manual_objective_scalarization.qsol`
- `manual_objective_scalarization.qsol.toml`

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

```bash
uv run qsol solve \
  examples/tutorials/graph_coloring.qsol \
  --config examples/tutorials/graph_coloring.qsol.toml \
  --runtime local-dimod \
  --out outdir/graph_coloring \
  --runtime-option sampler=exact
```

```bash
uv run qsol inspect estimate \
  examples/tutorials/minimum_graph_coloring.qsol \
  --config examples/tutorials/minimum_graph_coloring.qsol.toml \
  --json
```

```bash
uv run qsol solve \
  examples/tutorials/scalar_bool_demo.qsol \
  --config examples/tutorials/scalar_bool_demo.qsol.toml \
  --runtime local-dimod \
  --out outdir/scalar_bool_demo \
  --runtime-option sampler=exact
```

```bash
uv run qsol solve \
  examples/tutorials/relation_graph_independent_set.qsol \
  --config examples/tutorials/relation_graph_independent_set.qsol.toml \
  --runtime local-dimod \
  --out outdir/relation_graph_independent_set \
  --runtime-option sampler=exact
```

```bash
uv run qsol solve \
  examples/tutorials/relation_set_packing.qsol \
  --config examples/tutorials/relation_set_packing.qsol.toml \
  --runtime local-dimod \
  --out outdir/relation_set_packing \
  --runtime-option sampler=exact
```

```bash
uv run qsol solve \
  examples/tutorials/derived_max_clique.qsol \
  --config examples/tutorials/derived_max_clique.qsol.toml \
  --runtime local-dimod \
  --out outdir/derived_max_clique \
  --runtime-option sampler=exact
```

```bash
uv run qsol solve \
  examples/tutorials/job_sequencing_max.qsol \
  --config examples/tutorials/job_sequencing_max.qsol.toml \
  --runtime local-dimod \
  --out outdir/job_sequencing_max \
  --runtime-option sampler=simulated-annealing \
  --runtime-option num_reads=100
```

```bash
uv run qsol solve \
  examples/tutorials/custom_types_usage.qsol \
  --config examples/tutorials/custom_types_usage.qsol.toml \
  --runtime local-dimod \
  --out outdir/custom_types_usage \
  --runtime-option sampler=exact
```

```bash
uv run qsol build \
  examples/tutorials/all_different_slots.qsol \
  --config examples/tutorials/all_different_slots.qsol.toml \
  --runtime local-dimod \
  --out outdir/all_different_slots \
  --format qubo
```

```bash
uv run qsol build \
  examples/tutorials/graph_helpers.qsol \
  --config examples/tutorials/graph_helpers.qsol.toml \
  --runtime local-dimod \
  --out outdir/graph_helpers \
  --format qubo
```

```bash
uv run qsol build \
  examples/tutorials/route_demo.qsol \
  --config examples/tutorials/route_demo.qsol.toml \
  --runtime local-dimod \
  --out outdir/route_demo \
  --format qubo
```

```bash
uv run qsol build \
  examples/tutorials/weighted_spanning_tree.qsol \
  --config examples/tutorials/weighted_spanning_tree.qsol.toml \
  --runtime local-dimod \
  --out outdir/weighted_spanning_tree \
  --format qubo
```

```bash
uv run qsol build \
  examples/tutorials/route_successor.qsol \
  --config examples/tutorials/route_successor.qsol.toml \
  --runtime local-dimod \
  --out outdir/route_successor \
  --format qubo
```

```bash
uv run qsol build \
  examples/tutorials/manual_objective_scalarization.qsol \
  --config examples/tutorials/manual_objective_scalarization.qsol.toml \
  --runtime local-dimod \
  --out outdir/manual_objective_scalarization \
  --format qubo
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
- `graph_coloring.qsol.toml`
  - `scenarios.triangle` and `scenarios.pentagon` provide graph nodes, colors, and adjacency weights.
  - The model minimizes same-color edge conflicts so it is runnable on the current v1 backend.
- `minimum_graph_coloring.qsol.toml`
  - `scenarios.triangle.sets.Nodes`
  - `Colors` is a derived `Range(1, size(Nodes))` set and is not supplied in TOML.
  - The model uses a large same-color conflict penalty plus a color-index tie breaker, which keeps it compatible with `dimod-cqm-v1`.
- `custom_types_usage.qsol.toml`
  - `custom_types.qsol` defines `ExactSubset(X, k)`, `exactly_k`, and `weighted_score`.
  - `scenarios.baseline.params.K` supplies the named cardinality parameter used as the unknown argument.
- `scalar_bool_demo.qsol.toml`
  - `scenarios.default.sets.Machines`
  - `scenarios.default.params.Capacity`
- `relation_graph_independent_set.qsol.toml`
  - `scenarios.baseline.sets.V`
  - `scenarios.baseline.relations.Edge`
- `relation_set_packing.qsol.toml`
  - `scenarios.baseline.sets.Sets`
  - `scenarios.baseline.sets.Items`
  - `scenarios.baseline.relations.Contains`
- `derived_max_clique.qsol.toml`
  - `scenarios.baseline.sets.V`
  - `scenarios.baseline.relations.Edge`
  - `NonEdge` is derived with `pairs(...)` and is not supplied in TOML.
- `job_sequencing.qsol.toml`
  - `scenarios.baseline.sets.Jobs`
  - `scenarios.baseline.params.Length`
  - `scenarios.baseline.relations.Precedence`
  - `Start` and `Makespan` use static aggregate `Int` bounds from `sum(Length[j] for j in Jobs)`.
- `job_sequencing_max.qsol.toml`
  - `scenarios.baseline.sets.Jobs`
  - `scenarios.baseline.params.Length`
  - `scenarios.baseline.relations.Precedence`
  - `minimize max(Finish[j] for j in Jobs)` generates a bounded piecewise auxiliary.
- `all_different_slots.qsol.toml`
  - `scenarios.baseline.sets.Items`
  - `all_different(Slot[i] for i in Items)` lowers to pairwise disequality constraints.
- `graph_helpers.qsol.toml`
  - `scenarios.baseline.sets.V`
  - `scenarios.baseline.relations.Edge`
  - `adjacent(Edge, u, v)` lowers to static relation membership checks.
- `route_demo.qsol.toml`
  - `scenarios.baseline.sets.Positions`
  - `scenarios.baseline.sets.Cities`
  - `Route(Positions, Cities)` wraps a `BijectiveMapping`.
- `weighted_spanning_tree.qsol.toml`
  - `scenarios.baseline.sets.V`
  - `scenarios.baseline.relations.Edge`
  - `scenarios.baseline.params.Cost` uses comma-joined tuple keys for `Cost[G.edges]`.
- `route_successor.qsol.toml`
  - `scenarios.baseline.sets.Cities`
  - `Positions` is a derived `Range(1, size(Cities))` set and is not supplied in TOML.
  - `cyclic_successor` restricts the transition-cost objective to consecutive positions plus wraparound.
- `manual_objective_scalarization.qsol.toml`
  - `entrypoint.objectives.qubo_policy = "manual"` enables explicit multiple-objective scalarization.
  - `entrypoint.objectives.qubo_weights` supplies one weight per objective label.

## Related

- [Examples index](../README.md)
- [QSOL tutorials index](../../docs/tutorials/README.md)
- [Tutorial 3](../../docs/tutorials/03-compiling-running-and-reading-results.md)
