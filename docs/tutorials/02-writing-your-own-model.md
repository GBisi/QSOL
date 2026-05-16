# Tutorial 2: Writing Your Own QSOL Model

Goal: build a model from scratch and run it through the target-aware workflow.

## 1. Modeling Pattern

Use this sequence:

1. Import reusable modules (`unknown` and/or macro libraries) with `use` when needed.
2. Declare sets.
3. Declare params.
4. Declare unknowns with `find`.
5. Add hard feasibility with `must`.
6. Add objective with `minimize`/`maximize`.

## 2. Example Problem

Assign tasks to workers with:
- implicit exactly-one worker per task (from `Mapping`)
- explicit worker load limit
- cost minimization

Model (`examples/tutorials/assignment_balance.qsol`):

```qsol
use stdlib.logic;

problem WorkerAssignment {
  set Workers;
  set Tasks;

  param Cost[Workers,Tasks] : Real = 1;

  find Assign : Mapping(Tasks -> Workers);

  must forall w in Workers:
    atmost(2, Assign.is(t, w) for t in Tasks);

  minimize sum(
    sum(if Assign.is(t, w) then Cost[w, t] else 0 for w in Workers)
    for t in Tasks
  );
}
```

Reusable unknown imports use the same module form for stdlib and user libraries:

```qsol
use stdlib.permutation;
use stdlib.logic;
use mylib.constraints.injective;
```

## 3. Config

`examples/tutorials/assignment_balance.qsol.toml`:

```toml
schema_version = "1"

[entrypoint]
scenario = "baseline"
runtime = "local-dimod"

[scenarios.baseline]
problem = "WorkerAssignment"

[scenarios.baseline.sets]
Workers = ["w1", "w2", "w3"]
Tasks = ["t1", "t2", "t3", "t4"]

[scenarios.baseline.params.Cost]
w1 = { t1 = 2, t2 = 8, t3 = 4, t4 = 6 }
w2 = { t1 = 5, t2 = 3, t3 = 7, t4 = 2 }
w3 = { t1 = 6, t2 = 4, t3 = 2, t4 = 5 }
```

## 4. Run Workflow

```bash
uv run qsol inspect check examples/tutorials/assignment_balance.qsol

uv run qsol targets check \
  examples/tutorials/assignment_balance.qsol \
  --config examples/tutorials/assignment_balance.qsol.toml

uv run qsol build \
  examples/tutorials/assignment_balance.qsol \
  --config examples/tutorials/assignment_balance.qsol.toml \
  --out outdir/assignment_balance \
  --format qubo

uv run qsol solve \
  examples/tutorials/assignment_balance.qsol \
  --config examples/tutorials/assignment_balance.qsol.toml \
  --out outdir/assignment_balance \
  --runtime-option sampler=exact
```

The second command uses `entrypoint.runtime` from config. Add CLI `--runtime` to override.

## 5. Relation-Based Data

Use `relation` when your input is naturally tuple-shaped, such as graph edges or
set membership. Example:

```qsol
problem RelationGraphIndependentSet {
  set V;
  relation Edge(u: V, v: V);

  find Pick : Subset(V);

  must all(Edge(u, v) for (u, v) in Edge);
  maximize count(v in V where Pick.has(v));
}
```

Relation data lives in config TOML:

```toml
[scenarios.baseline.relations]
Edge = [
  { u = "a", v = "b" },
  { u = "b", v = "c" },
]
```

When a relation can be computed from static data, derive it in the model instead
of duplicating it in TOML:

```qsol
relation NonEdge(u: V, v: V) =
  pairs(u in V, v in V where u != v and not Edge(u, v));

relation Reciprocal(u: V, v: V) =
  filter((u, v) in Edge where Edge(v, u));
```

Derived relation filters run during grounding. They may use params and relation
membership calls, but not decisions such as `Pick.has(v)`.

Static data can also define bounded integer decision domains:

```qsol
problem JobSequencing {
  set Jobs;
  param Length[Jobs] : Int[1 .. 100];

  find Makespan : Int[0 .. sum(Length[j] for j in Jobs)];

  minimize Makespan;
}
```

The aggregate in the `Int` upper bound is evaluated from scenario data during
grounding. Bounds may use static params, `size(...)`, relation membership, and
static `sum`/`count`; they cannot reference decisions such as `Pick.has(j)`.

Compiler-owned piecewise builtins cover common balancing and makespan patterns
without manual auxiliary variables:

```qsol
problem MachineLoads {
  set Machines;
  find Load[Machines] : Int[0 .. 10];

  minimize max(Load[m] for m in Machines);
}
```

The supported first-pass forms are `minimize abs(expr)`, `must abs(expr) <= C`,
`minimize max(term for ...)`, and `maximize min(term for ...)`. The compiler
generates bounded scalar auxiliaries and hard constraints before backend
compilation.

## 6. Backend-v1 Safety Checklist

To reduce unsupported diagnostics:

- Prefer primitive-friendly formulations and keep custom unknown definitions simple (`rep` + `laws` + `view`).
- Keep hard constraints to supported numeric comparisons and atom-like predicates.
- Use `sum` + arithmetic in objectives, or the supported piecewise objective forms when they remove manual auxiliaries.
- Validate early with `targets check` on concrete scenarios.
- Custom unknowns in `find` are supported through frontend elaboration into primitive finds and generated constraints.

> For a complete list of unsupported patterns, see [Backend V1 Limits](../../docs/BACKEND_V1_LIMITS.md).

## 7. Incremental Extensions

Try one at a time and rerun `inspect check` and `targets check`:

1. Add a `should` balance preference.
2. Add a boolean forbidden-assignment param and hard exclusion.
3. Add a second weighted objective term.
