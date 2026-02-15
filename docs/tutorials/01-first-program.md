# Tutorial 1: Your First QSOL Program

Goal: write and run a minimal QSOL model end to end with explicit runtime targeting.

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

Ready-to-run copy:
- `examples/tutorials/first_program.qsol`

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
  },
  "execution": {
    "runtime": "local-dimod"
  }
}
```

Ready-to-run copy:
- `examples/tutorials/first_program.instance.json`

`execution` is optional. CLI flags can override it.

## 3. Inspect Frontend Stages

Parse:

```bash
uv run qsol inspect parse examples/tutorials/first_program.qsol --json
```

Type/semantic checks:

```bash
uv run qsol inspect check examples/tutorials/first_program.qsol
```

Lowered symbolic IR:

```bash
uv run qsol inspect lower examples/tutorials/first_program.qsol --json
```

## 4. Check Target Support

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod
```

This writes `capability_report.json` and hard-fails if unsupported.

## 5. Build Artifacts

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

Artifacts in `outdir/first_program`:
- `model.cqm`
- `model.bqm`
- `qubo.json`
- `varmap.json`
- `explain.json`
- `capability_report.json`
- `qsol.log`

## 6. Solve

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact
```

This also writes `run.json`.

## 7. Quick Troubleshooting

- `QSOL1001`: syntax issue (often missing semicolon).
- `QSOL2101`: type issue (method call target/arity mismatch).
- `QSOL2201`: instance shape mismatch.
- `QSOL3001`: backend-lowering limitation for valid language shape.
- `QSOL4006`: runtime not resolved from CLI or `execution` defaults.
- `QSOL4007`: unknown runtime/backend id.
- `QSOL4008`: incompatible runtime/backend pair.
- `QSOL4009`: plugin loading/config issue.
- `QSOL5001`: runtime execution failure.
