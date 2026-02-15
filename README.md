# QSOL

## What QSOL Is

QSOL is a declarative language and compiler for combinatorial optimization.
You model sets, params, unknowns, constraints, and objectives; QSOL compiles model + instance data into inspectable dimod artifacts and can run a selected runtime/backend target pair.

## Idea, Vision, and Why

QSOL exists to keep optimization models explicit, reviewable, and reproducible.

- Idea: express optimization intent at the language level, not solver procedure details.
- Vision: preserve declarative clarity, staged compiler ownership, and strong diagnostics.
- Why: predictable semantics and inspectable artifacts are more trustworthy than opaque workflows.

Project purpose, principles, and coherence rubric are in `VISION.md`.

## Compiler Pipeline Architecture

QSOL is staged and target-aware:

`parse -> sema -> desugar/lower -> ground -> target selection/support check -> backend compile/export -> runtime solve`

Reference target pair:
- Runtime: `local-dimod`
- Backend: `dimod-cqm-v1`

Module map:
- `/Users/gbisi/Documents/code/qsol/src/qsol/parse/`
- `/Users/gbisi/Documents/code/qsol/src/qsol/sema/`
- `/Users/gbisi/Documents/code/qsol/src/qsol/lower/`
- `/Users/gbisi/Documents/code/qsol/src/qsol/backend/`
- `/Users/gbisi/Documents/code/qsol/src/qsol/targeting/`
- `/Users/gbisi/Documents/code/qsol/src/qsol/compiler/`
- `/Users/gbisi/Documents/code/qsol/src/qsol/cli.py`

## Libraries and Tooling

- `lark`: parser and grammar engine
- `dimod`: CQM/BQM model representation and local sampling
- `typer`: CLI command surface
- `rich`: terminal rendering
- `pytest`: tests and coverage checks
- `pre-commit`: quality-gate runner
- `ruff`: lint/format checks
- `mypy`: static typing checks
- `uv`: environment and command execution

## Setup

```bash
uv sync --extra dev
uv run qsol -h
```

## Quickstart

Use tutorial files:
- `examples/tutorials/first_program.qsol`
- `examples/tutorials/first_program.instance.json`

Inspect frontend stages:

```bash
uv run qsol inspect parse examples/tutorials/first_program.qsol --json
uv run qsol inspect check examples/tutorials/first_program.qsol
uv run qsol inspect lower examples/tutorials/first_program.qsol --json
```

List available targets:

```bash
uv run qsol targets list
```

Check pair capabilities:

```bash
uv run qsol targets capabilities --runtime local-dimod --backend dimod-cqm-v1
```

Check model+instance support:

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1
```

Build artifacts:

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program \
  --format qubo
```

Solve:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --backend dimod-cqm-v1 \
  --out outdir/first_program \
  --runtime-option sampler=exact \
  --solutions 3 \
  --energy-max 0
```

## CLI Overview

Core command groups:

```bash
uv run qsol inspect parse <model.qsol> [--json]
uv run qsol inspect check <model.qsol>
uv run qsol inspect lower <model.qsol> [--json]

uv run qsol targets list [--plugin module:attr]
uv run qsol targets capabilities --runtime <id> --backend <id> [--plugin module:attr]
uv run qsol targets check <model.qsol> -i <instance.json> [--runtime <id>] [--backend <id>] [--plugin module:attr]

uv run qsol build <model.qsol> -i <instance.json> [--runtime <id>] [--backend <id>] -o <outdir>
uv run qsol solve <model.qsol> -i <instance.json> [--runtime <id>] [--backend <id>] -o <outdir> [-x key=value] [-X runtime_options.json] [--solutions <n>] [--energy-min <value>] [--energy-max <value>]
```

Defaults:
- instance path: `<model>.instance.json` if present
- outdir: `<cwd>/outdir/<model_stem>`
- solve runtime options default to `sampler=simulated-annealing` and `num_reads=100`
- solve returns the best solution by default (`--solutions 1`)

`solve` multi-solution and thresholds:
- `--solutions N` returns up to `N` best unique solutions.
- Returned solutions are ordered by energy ascending (ties are deterministic).
- `--energy-min`/`--energy-max` are inclusive thresholds.
- Threshold checks are applied to all returned solutions.
- If any returned solution violates thresholds, `solve` writes `run.json` and exits non-zero (`status: "threshold_failed"`).

Short command aliases:
- `inspect` / `ins`
- `targets` / `tg`
- `build` / `b`
- `solve` / `s`
- `targets list` / `targets ls`
- `targets capabilities` / `targets caps`
- `targets check` / `targets chk`

Runtime/backend selection precedence:

1. CLI `--runtime` and `--backend`
2. Instance defaults in `execution.runtime` and `execution.backend`

If unresolved after precedence, `build`/`solve`/`targets check` fail with `QSOL4006`.

## Documentation Reading Path (Humans and Agents)

1. `README.md` (Both): project overview and getting started.
2. `VISION.md` (Both): project purpose, principles, and coherence rubric.
3. `docs/tutorials/01-first-program.md` (Human-first): first end-to-end workflow.
4. `docs/tutorials/02-writing-your-own-model.md` (Human-first): build your own model.
5. `docs/tutorials/03-compiling-running-and-reading-results.md` (Both): artifacts and troubleshooting.
6. `docs/QSOL_SYNTAX.md` (Both): practical syntax reference.
7. `QSOL_reference.md` (Both): detailed language/reference guide.
8. `docs/CODEBASE.md` (Agent-first): stage ownership and implementation map.
9. `docs/README.md` (Both): documentation index.
10. `examples/README.md` and `examples/*/README.md` (Both): runnable examples.
11. `AGENTS.md` (Agent-first): repository execution/completion policy.

## Roadmap

Roadmap tracking is in `ROADMAP.md`.

## Contributing

Contribution workflow and quality gates are in `CONTRIBUTING.md`.
Agent-specific policy requirements are in `AGENTS.md`.

## License

MIT. See `LICENSE`.
