# QSOL: Quantum/Quadratic Specification-Oriented Optimization Language

## What QSOL Is

QSOL is a declarative language, compiler and runtime for combinatorial optimization problems.

You model sets, params, unknowns, constraints, and objectives; QSOL compiles model + instance data into inspectable dimod artifacts and can run a selected runtime target.

## Idea, Vision, and Why

QSOL exists to keep optimization models explicit, reviewable, and reproducible.

- Idea: express optimization intent at the language level, not solver procedure details.
- Vision: preserve declarative clarity, staged compiler ownership, and strong diagnostics.
- Why: predictable semantics and inspectable artifacts are more trustworthy than opaque workflows.

Project purpose, principles, and coherence rubric are in `VISION.md`.

## Compiler Pipeline Architecture

QSOL is staged and target-aware:

`parse -> sema -> desugar/lower -> ground -> target selection/support check -> backend compile/export -> runtime solve`

Reference targets:
- Runtime: `local-dimod`
- Backend (implicit for CLI workflows): `dimod-cqm-v1`

Additional built-in runtime:
- Runtime: `qiskit` (QAOA/NumPy on fake IBM backends, OpenQASM3 export for QAOA)

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

Install optional Qiskit runtime dependencies:

```bash
uv sync --extra dev --extra qiskit
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
uv run qsol targets capabilities --runtime local-dimod
uv run qsol targets capabilities --runtime qiskit
```

Check model+instance support:

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod
```

Build artifacts:

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

Solve:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime local-dimod \
  --out outdir/first_program \
  --runtime-option sampler=exact \
  --solutions 3 \
  --energy-max 0
```

Solve with Qiskit QAOA on a fake IBM backend and emit OpenQASM 3:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --instance examples/tutorials/first_program.instance.json \
  --runtime qiskit \
  --out outdir/first_program_qiskit \
  --runtime-option algorithm=qaoa \
  --runtime-option fake_backend=FakeManilaV2 \
  --runtime-option shots=1024 \
  --runtime-option reps=2
```

## CLI Overview

Core command groups:

```bash
uv run qsol inspect parse <model.qsol> [--json]
uv run qsol inspect check <model.qsol>
uv run qsol inspect lower <model.qsol> [--json]

uv run qsol targets list [--plugin module:attr]
uv run qsol targets capabilities --runtime <id> [--plugin module:attr]
uv run qsol targets check <model.qsol> -i <instance.json> [--runtime <id>] [--plugin module:attr]

uv run qsol build <model.qsol> -i <instance.json> [--runtime <id>] -o <outdir>
uv run qsol solve <model.qsol> -i <instance.json> [--runtime <id>] -o <outdir> [-x key=value] [-X runtime_options.json] [--solutions <n>] [--energy-min <value>] [--energy-max <value>]
```

Defaults:
- instance path: `<model>.instance.json` if present
- outdir: `<cwd>/outdir/<model_stem>`
- solve runtime options default to `sampler=simulated-annealing` and `num_reads=100`
- solve returns the best solution by default (`--solutions 1`)

`qiskit` runtime options:
- `algorithm=qaoa|numpy` (default: `qaoa`)
- `fake_backend=<FakeBackendClass>` (default: `FakeManilaV2`; used by `qaoa`)
- `shots=<int>`, `reps=<int>`, `maxiter=<int>`, `seed=<int>`, `optimization_level=<int>`
- QAOA writes `qaoa.qasm` (OpenQASM 3) into the selected `--out` directory.

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

Runtime selection precedence:

1. CLI `--runtime`
2. Instance default `execution.runtime`

If unresolved after precedence, `build`/`solve`/`targets check` fail with `QSOL4006`.
Backend selection is implicit for CLI workflows and defaults to `dimod-cqm-v1`.

Plugin bundle loading precedence for `targets check`/`build`/`solve`:

1. Built-in plugins
2. Installed entry-point plugins (`qsol.backends`, `qsol.runtimes`)
3. Instance defaults in `execution.plugins` (array of `module:attribute`)
4. CLI `--plugin module:attribute` values

Instance + CLI plugin specs are merged with stable ordering and exact-string deduplication.

## Documentation Reading Path (Humans and Agents)

1. `README.md` (Both): project overview and getting started.
2. `VISION.md` (Both): project purpose, principles, and coherence rubric.
3. `docs/tutorials/01-first-program.md` (Human-first): first end-to-end workflow.
4. `docs/tutorials/02-writing-your-own-model.md` (Human-first): build your own model.
5. `docs/tutorials/03-compiling-running-and-reading-results.md` (Both): artifacts and troubleshooting.
6. `docs/PLUGINS.md` (Both): plugin architecture, authoring, and loading methods.
7. `docs/QSOL_SYNTAX.md` (Both): practical syntax reference.
8. `QSOL_reference.md` (Both): detailed language/reference guide (includes instance JSON contract).
9. `docs/CODEBASE.md` (Agent-first): stage ownership and implementation map.
10. `docs/README.md` (Both): documentation index.
11. `examples/README.md` and `examples/*/README.md` (Both): runnable examples.
12. `AGENTS.md` (Agent-first): repository execution/completion policy.

## Roadmap

Roadmap tracking is in `ROADMAP.md`.

## Contributing

Contribution workflow and quality gates are in `CONTRIBUTING.md`.
Agent-specific policy requirements are in `AGENTS.md`.

## License

MIT. See `LICENSE`.
