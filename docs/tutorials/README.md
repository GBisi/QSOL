# QSOL Tutorials

A hands-on tutorial series that takes you from your first model to building reusable custom types.

## Prerequisites

```bash
uv sync --extra dev
uv run qsol -h
```

If the CLI help opens, you are ready to start.

## Tutorial List

### [01 — Your First QSOL Program](01-first-program.md)

Write a minimal QSOL model (`Subset` + constraint + objective), configure it with a TOML scenario, and walk through the full workflow: `inspect parse` → `inspect check` → `inspect lower` → `targets check` → `build` → `solve`. Includes a quick troubleshooting guide for common diagnostics.

### [02 — Writing Your Own Model](02-writing-your-own-model.md)

Build a worker–task assignment model from scratch using `Mapping`, `forall` constraints, and cost minimization. Covers the recommended modeling pattern, running the target-aware workflow, and a safety checklist for `dimod-cqm-v1`.

### [03 — Compiling, Running, and Reading Results](03-compiling-running-and-reading-results.md)

Deep dive into the CLI workflow: target discovery, TOML config authoring, multi-scenario solves, Qiskit QAOA integration, the output directory structure (`run.json`, `qubo.json`, `varmap.json`, …), and runtime/plugin selection precedence.

### [04 — Custom Unknowns, Functions, and Predicates](04-custom-unknowns-functions-and-predicates.md)

Define reusable `predicate` and `function` macros, build a custom `unknown` type with `rep`/`laws`/`view`, and import it from a separate module. Covers type rules, common mistakes, and the validation workflow.

## What's Next

After completing the tutorials, explore:

- [Language Reference](../../QSOL_reference.md) — full semantics and type system
- [Standard Library](../STDLIB.md) — built-in modules (`logic`, mappings, permutations)
- [Examples](../../examples/README.md) — more runnable models
