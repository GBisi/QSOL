# QSOL: Quantum/Quadratic Specification-Oriented Optimization Language

## What QSOL Is

QSOL is a declarative language, compiler and runtime for combinatorial optimization problems.

You model sets, params, unknowns, constraints, and objectives; QSOL compiles model + scenario data (from config TOML) into inspectable dimod artifacts and can run a selected runtime target.

## Idea, Vision, and Why

QSOL exists to keep optimization models explicit, reviewable, and reproducible.

- Idea: express optimization intent at the language level, not solver procedure details.
- Vision: preserve declarative clarity, staged compiler ownership, and strong diagnostics.
- Why: predictable semantics and inspectable artifacts are more trustworthy than opaque workflows.

Project purpose, principles, and coherence rubric are in `VISION.md`.

## Compiler Pipeline Architecture

QSOL is staged and target-aware:

`parse -> module load (use) -> macro + unknown elaboration -> sema -> desugar/lower -> ground -> target selection/support check -> backend compile/export -> runtime solve`

Reference targets:
- Runtime: `local-dimod`
- Backend (implicit for CLI workflows): `dimod-cqm-v1`

Additional built-in runtime:
- Runtime: `qiskit` (QAOA/NumPy on fake IBM backends, OpenQASM3 export for QAOA)

## Module Imports and Stdlib

QSOL uses one import form for both packaged stdlib modules and user libraries:

```qsol
use stdlib.permutation;
use stdlib.logic;
use mylib.graph.unknowns;
```

Import rules:
- `stdlib.*` is reserved and always resolved from packaged modules under `src/qsol/stdlib/`.
- Non-stdlib modules resolve as user libraries from:
1. the importing file directory
2. the process current working directory
- Module path `a.b.c` maps to `a/b/c.qsol`.
- Quoted file imports (`use "x.qsol";`) are not supported.

Custom unknowns and predicate/function macros from imported modules are expanded in the frontend, so backend v1 remains primitive-focused.

Stdlib module catalog and usage details:
- `src/qsol/stdlib/README.md`

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
- `examples/tutorials/first_program.qsol.toml`

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

Check model+scenario support:

```bash
uv run qsol targets check \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod
```

Build artifacts:

```bash
uv run qsol build \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  --out outdir/first_program \
  --format qubo
```

Solve:

```bash
uv run qsol solve \
  examples/tutorials/first_program.qsol \
  --config examples/tutorials/first_program.qsol.toml \
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
  --config examples/tutorials/first_program.qsol.toml \
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
uv run qsol targets check <model.qsol> -c <config.qsol.toml> [--runtime <id>] [--scenario <name>] [--all-scenarios] [--failure-policy <policy>] [--plugin module:attr]

uv run qsol build <model.qsol> -c <config.qsol.toml> [--runtime <id>] [--scenario <name>] [--all-scenarios] [--failure-policy <policy>] -o <outdir>
uv run qsol solve <model.qsol> -c <config.qsol.toml> [--runtime <id>] [--scenario <name>] [--all-scenarios] [--combine-mode intersection|union] [--failure-policy <policy>] -o <outdir> [-x key=value] [-X runtime_options.json] [--solutions <n>] [--energy-min <value>] [--energy-max <value>]
```

Defaults:
- config discovery: `*.qsol.toml` in model directory; if multiple, `<model>.qsol.toml` is required
- outdir: CLI `--out`, then config `entrypoint.out`, then `<cwd>/outdir/<model_stem>`
- solve returns the best solution by default (`--solutions 1`)

Config entrypoint (`[entrypoint]`) can express CLI-equivalent defaults:
- selection: `scenario`, `scenarios`, `all_scenarios`
- execution: `runtime`, `backend`, `plugins`
- solve controls: `runtime_options`, `solutions`, `energy_min`, `energy_max`
- workflow defaults: `out`, `format`, `combine_mode`, `failure_policy`

Built-in runtime plugins and optional runtime params:
- `local-dimod`
- optional params: `sampler=exact|simulated-annealing` (default: `simulated-annealing`), `num_reads=<int>` (default: `100`), `seed=<int>`
- default runtime options when `runtime=local-dimod`: `sampler=simulated-annealing`, `num_reads=100`
- `qiskit`
- optional params: `algorithm=qaoa|numpy` (default: `qaoa`), `fake_backend=<FakeBackendClass>` (default: `FakeManilaV2`), `shots=<int>` (default: `1024`), `reps=<int>` (default: `1`), `maxiter=<int>` (default: `100`), `seed=<int>`, `optimization_level=<int>` (default: `1`)
- shared solve params for both runtimes: `solutions=<int>` (default: `1`), `energy_min=<number>`, `energy_max=<number>`
- for `algorithm=qaoa`, QSOL auto-wires backend transpilation via `pass_manager`/`transpiler` based on the installed Qiskit package variant
- QAOA writes `qaoa.qasm` (OpenQASM 3) into the selected `--out` directory

`solve` multi-solution and thresholds:
- `--solutions N` returns up to `N` best unique solutions.
- Returned solutions are ordered by energy ascending (ties are deterministic).
- `Run Summary` prints `Runtime Parameters` (resolved values, including defaults and user/config overrides).
- CLI output includes a `Returned Solutions` table that prints all returned solutions with
  rank, energy, compact sample summary, selected-assignment summary, and runtime-specific metadata when present.
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
2. Scenario config `execution.runtime`
3. Config `entrypoint.runtime`
4. Legacy config `defaults.execution.runtime`

If unresolved after precedence, `build`/`solve`/`targets check` fail with `QSOL4006`.
Backend selection is implicit for CLI workflows and defaults to `dimod-cqm-v1`.

Plugin bundle loading precedence for `targets check`/`build`/`solve`:

1. Built-in plugins
2. Installed entry-point plugins (`qsol.backends`, `qsol.runtimes`)
3. Config execution values in `execution.plugins` (scenario -> `entrypoint` -> legacy defaults)
4. CLI `--plugin module:attribute` values

Config + CLI plugin specs are merged with stable ordering and exact-string deduplication.

## Continuous Integration

GitHub Actions runs the mandatory quality gates on every push and pull request to `main`.

The CI workflow (`.github/workflows/ci.yml`) executes:

1. **Lint & Format** — `uv run pre-commit run --all-files`
2. **Tests & Coverage** — `uv run pytest` (90% coverage threshold)
3. **Examples Equivalence Suite** — `uv run python examples/run_equivalence_suite.py`

## Documentation Reading Path (Humans and Agents)

1. `README.md` (Both): project overview and getting started.
2. `VISION.md` (Both): project purpose, principles, and coherence rubric.
3. `docs/tutorials/01-first-program.md` (Human-first): first end-to-end workflow.
4. `docs/tutorials/02-writing-your-own-model.md` (Human-first): build your own model.
5. `docs/tutorials/03-compiling-running-and-reading-results.md` (Both): artifacts and troubleshooting.
6. `docs/tutorials/04-custom-unknowns-functions-and-predicates.md` (Human-first): author reusable unknowns and macro APIs.
7. `docs/PLUGINS.md` (Both): plugin architecture, authoring, and loading methods.
8. `docs/QSOL_SYNTAX.md` (Both): practical syntax reference.
9. `QSOL_reference.md` (Both): detailed language/reference guide (includes config TOML + scenario contract).
10. `docs/CODEBASE.md` (Agent-first): stage ownership and implementation map.
11. `src/qsol/stdlib/README.md` (Both): packaged stdlib modules and contracts.
12. `docs/README.md` (Both): documentation index.
13. `examples/README.md` and `examples/*/README.md` (Both): runnable examples.
14. `AGENTS.md` (Agent-first): repository execution/completion policy.

## Roadmap

Roadmap tracking is in `ROADMAP.md`.

## Contributing

Contribution workflow and quality gates are in `CONTRIBUTING.md`.
Agent-specific policy requirements are in `AGENTS.md`.

## License

MIT. See `LICENSE`.
