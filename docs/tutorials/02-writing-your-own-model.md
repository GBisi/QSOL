# Tutorial 2: Writing Your Own QSOL Model

Goal: build a model from scratch and run it through the target-aware workflow.

## 1. Modeling Pattern

Use this sequence:

1. Import reusable unknown modules with `use` when needed.
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
problem WorkerAssignment {
  set Workers;
  set Tasks;

  param Cost[Workers,Tasks] : Real = 1;

  find Assign : Mapping(Tasks -> Workers);

  must forall w in Workers:
    sum(if Assign.is(t, w) then 1 else 0 for t in Tasks) <= 2;

  minimize sum(
    sum(if Assign.is(t, w) then Cost[w, t] else 0 for w in Workers)
    for t in Tasks
  );
}
```

Reusable unknown imports use the same module form for stdlib and user libraries:

```qsol
use stdlib.permutation;
use mylib.constraints.injective;
```

## 3. Config

`examples/tutorials/assignment_balance.qsol.toml`:

```toml
schema_version = "1"

[selection]
default_scenario = "baseline"

[defaults.execution]
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

The second command uses `execution.runtime` from config. Add CLI `--runtime` to override.

## 5. Backend-v1 Safety Checklist

To reduce unsupported diagnostics:

- Prefer primitive-friendly formulations and keep custom unknown definitions simple (`rep` + `laws` + `view`).
- Keep hard constraints to supported numeric comparisons and atom-like predicates.
- Use `sum` + arithmetic in objectives.
- Validate early with `targets check` on concrete scenarios.
- Custom unknowns in `find` are supported through frontend elaboration into primitive finds and generated constraints.

## 6. Incremental Extensions

Try one at a time and rerun `inspect check` and `targets check`:

1. Add a `should` balance preference.
2. Add a boolean forbidden-assignment param and hard exclusion.
3. Add a second weighted objective term.
