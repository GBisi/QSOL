# Tutorial 2: Writing Your Own QSOL Model

Goal: build a model from scratch using a practical pattern and keep it backend-v1 compatible.

## 1. Modeling Pattern

Use this sequence:

1. Declare sets (entities).
2. Declare params (known data).
3. Declare unknown structure with `find`.
4. Add hard feasibility rules with `must`.
5. Add objective with `minimize` or `maximize`.

## 2. Example Problem

Assign tasks to workers with:
- implicit exactly-one worker per task (from `Mapping`)
- explicit max load per worker
- total assignment cost minimization

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

## 3. Instance

`examples/tutorials/assignment_balance.instance.json`:

```json
{
  "problem": "WorkerAssignment",
  "sets": {
    "Workers": ["w1", "w2", "w3"],
    "Tasks": ["t1", "t2", "t3", "t4"]
  },
  "params": {
    "Cost": {
      "w1": {"t1": 2, "t2": 8, "t3": 4, "t4": 6},
      "w2": {"t1": 5, "t2": 3, "t3": 7, "t4": 2},
      "w3": {"t1": 6, "t2": 4, "t3": 2, "t4": 5}
    }
  }
}
```

## 4. Run Workflow

```bash
uv run qsol check examples/tutorials/assignment_balance.qsol

uv run qsol compile \
  examples/tutorials/assignment_balance.qsol \
  --instance examples/tutorials/assignment_balance.instance.json \
  --out outdir/assignment_balance \
  --format qubo

uv run qsol run \
  examples/tutorials/assignment_balance.qsol \
  --instance examples/tutorials/assignment_balance.instance.json \
  --out outdir/assignment_balance \
  --sampler exact
```

## 5. Backend-v1 Safe Modeling Checklist

To reduce `QSOL3001` unsupported diagnostics:

- Prefer `Subset` and `Mapping` only for `find`.
- Use hard constraints as conjunctions of:
  - numeric comparisons (`=`, `<`, `<=`, `>`, `>=`)
  - atom-like predicates (`S.has(...)`, `F.is(...)`, bool params)
- Use `sum` + arithmetic for objectives.
- Add quantifiers carefully and test with `compile` early.
- Treat user-defined unknown instantiation as experimental for now.

## 6. Extend This Example

Try these incremental changes and re-run `check` then `compile` each time:

1. Add a `should` preference for balancing worker loads.
2. Add a `param Forbidden[Workers,Tasks] : Bool = false;` and forbid matches with `must`.
3. Add a second objective term (for example penalize assignments to a specific worker).
