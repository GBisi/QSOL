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
- `scalar_bool_demo.qsol`
- `scalar_bool_demo.qsol.toml`
- `relation_graph_independent_set.qsol`
- `relation_graph_independent_set.qsol.toml`
- `relation_set_packing.qsol`
- `relation_set_packing.qsol.toml`
- `derived_max_clique.qsol`
- `derived_max_clique.qsol.toml`

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
- `minimum_graph_coloring.qsol.toml`
  - `scenarios.triangle.sets.Nodes`
  - `Colors` is a derived `Range(1, size(Nodes))` set and is not supplied in TOML.
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

## Related

- [Examples index](../README.md)
- [QSOL tutorials index](../../docs/tutorials/README.md)
- [Tutorial 3](../../docs/tutorials/03-compiling-running-and-reading-results.md)
