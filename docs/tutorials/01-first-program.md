# Tutorial 1: Your First QSOL Program

Goal: write and run a minimal QSOL model end to end.

## 1. Model

Create `first_program.qsol`:

```qsol
problem FirstProgram {
  set Items;
  param Value[Items] : Real = 1;

  find Pick : Subset(Items);

  must sum(if Pick.has(i) then 1 else 0 for i in Items) = 2;
  maximize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
```

A ready-to-run copy already exists at:
- `examples/tutorials/first_program.qsol`

What it means:
- `set Items`: domain of candidate items
- `find Pick : Subset(Items)`: solver chooses which items are selected
- `must ... = 2`: exactly two items must be selected
- `maximize ...`: maximize sum of selected item values

## 2. Instance Data

Create `first_program.instance.json`:

```json
{
  "problem": "FirstProgram",
  "sets": {
    "Items": ["i1", "i2", "i3", "i4"]
  },
  "params": {
    "Value": {
      "i1": 3,
      "i2": 8,
      "i3": 5,
      "i4": 2
    }
  }
}
```

Ready-to-run copy:
- `examples/tutorials/first_program.instance.json`

## 3. Validate the Model

Parse only:

```bash
uv run qsol compile examples/tutorials/first_program.qsol --parse --json
```

Type and semantic checks:

```bash
uv run qsol compile examples/tutorials/first_program.qsol --check
```

Inspect lowered symbolic IR:

```bash
uv run qsol compile examples/tutorials/first_program.qsol --lower --json
```

## 4. Compile to Artifacts

```bash
uv run qsol compile \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --out outdir/first_program \
  --format qubo
```

Artifacts appear in `outdir/first_program`:
- `model.cqm`
- `model.bqm`
- `qubo.json`
- `varmap.json`
- `explain.json`
- `qsol.log`

## 5. Run the Sampler

```bash
uv run qsol run \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --out outdir/first_program \
  --sampler exact
```

This command also writes:
- `outdir/first_program/run.json`

`run.json` includes best energy, selected binary variables, and decoded QSOL meanings via `varmap.json`.

## 6. Quick Troubleshooting

- `QSOL1001`: syntax issue; check missing semicolons.
- `QSOL2101`: type issue; check method call arguments (`Subset.has`, `Mapping.is`).
- `QSOL2201`: instance mismatch; check set/param keys and indexed shape.
- `QSOL3001`: backend limitation; simplify expression shape or use supported patterns.
