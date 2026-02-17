# QSOL CLI Reference

The `qsol` command-line interface is the primary tool for compiling, inspecting, and solving QSOL models. It takes a declarative `.qsol` model file and a `.qsol.toml` configuration file through a multi-stage compiler pipeline, ultimately producing quantum-compatible artifacts and solve results.

All examples in this document use the **graph coloring** tutorial as the running example:

```
examples/tutorials/
├── graph_coloring.qsol        # the model
└── graph_coloring.qsol.toml   # config with "triangle" and "pentagon" scenarios
```

---

## Table of Contents

1.  [Global Options](#global-options)
2.  [Core Commands](#core-commands)
    - [`qsol build`](#qsol-build)
    - [`qsol solve`](#qsol-solve)
3.  [Inspection Commands](#inspection-commands)
    - [`qsol inspect parse`](#qsol-inspect-parse)
    - [`qsol inspect check`](#qsol-inspect-check)
    - [`qsol inspect lower`](#qsol-inspect-lower)
4.  [Target Commands](#target-commands)
    - [`qsol targets list`](#qsol-targets-list)
    - [`qsol targets capabilities`](#qsol-targets-capabilities)
    - [`qsol targets check`](#qsol-targets-check)
5.  [Build Artifacts Deep Dive](#build-artifacts-deep-dive)
6.  [Solve Output Deep Dive](#solve-output-deep-dive)
7.  [Multi-Scenario Mode](#multi-scenario-mode)
8.  [Command Aliases](#command-aliases)
9.  [Exit Codes](#exit-codes)

---

## Global Options

These options are available on **every** command:

| Option                 | Short | Type    | Default   | Description                                           |
|------------------------|-------|---------|-----------|-------------------------------------------------------|
| `--no-color`           | `-n`  | flag    | off       | Disable ANSI color/style output (useful for piping).  |
| `--log-level`          | `-l`  | enum    | `warning` | Set CLI log verbosity: `debug`, `info`, `warning`, `error`. |
| `--help`               | `-h`  | flag    | —         | Show help message and exit.                           |

> **Tip:** Use `--log-level debug` to see the compiler's internal decision-making (config resolution, variable encoding, constraint lowering).

---

## Core Commands

### `qsol build`

Compiles a model + scenario and exports backend artifacts (CQM, BQM, QUBO/Ising files) to disk. This is useful when you want to inspect the compiled output **without** running it, or when preparing artifacts for a custom runtime.

**Synopsis:**

```bash
qsol build [OPTIONS] FILE
```

**All Options:**

| Option              | Short | Type     | Default                          | Description                                                                 |
|---------------------|-------|----------|----------------------------------|-----------------------------------------------------------------------------|
| `FILE`              | —     | path     | *required*                       | Path to the `.qsol` model source file.                                      |
| `--config`          | `-c`  | path     | auto-discovered `*.qsol.toml`    | Path to the TOML configuration file. If omitted, QSOL looks for `<model>.qsol.toml` or a single `*.qsol.toml` in the same directory. |
| `--out`             | `-o`  | path     | `./outdir/<model_stem>`          | Output directory for all generated artifacts.                               |
| `--format`          | `-f`  | string   | config entrypoint, then `qubo`   | Export format for the objective payload: `qubo`, `ising`, `bqm`, or `cqm`.  |
| `--runtime`         | `-u`  | string   | config entrypoint value          | Runtime plugin identifier (e.g., `local-dimod`).                            |
| `--plugin`          | `-p`  | string   | none                             | Load an extra plugin bundle from `module:attribute` (repeatable).           |
| `--scenario`        | —     | string   | config entrypoint scenario       | Scenario name to build (repeatable for multi-scenario).                     |
| `--all-scenarios`   | —     | flag     | off                              | Build all scenarios declared in the config.                                 |
| `--failure-policy`  | —     | enum     | config value or `run-all-fail`   | Scenario failure policy: `run-all-fail`, `fail-fast`, or `best-effort`.     |

**Example:**

```bash
$ qsol build examples/tutorials/graph_coloring.qsol \
    -c examples/tutorials/graph_coloring.qsol.toml \
    --runtime local-dimod \
    -o outdir/graph_coloring
```

**Example Output (stdout):**

```
                        Build Artifacts
┌────────────────────┬──────────────────────────────────────────────┐
│ Key                │ Value                                        │
├────────────────────┼──────────────────────────────────────────────┤
│ Scenario           │ triangle                                     │
│ Runtime            │ local-dimod                                  │
│ Backend            │ dimod-cqm-v1                                 │
│ CQM                │ outdir/graph_coloring/model.cqm              │
│ BQM                │ outdir/graph_coloring/model.bqm              │
│ Format             │ outdir/graph_coloring/qubo.json              │
│ VarMap             │ outdir/graph_coloring/varmap.json            │
│ Explain            │ outdir/graph_coloring/explain.json           │
│ Capability Report  │ outdir/graph_coloring/capability_report.json │
│ num_constraints    │ 80                                           │
│ num_interactions   │ 105                                          │
│ num_variables      │ 45                                           │
└────────────────────┴──────────────────────────────────────────────┘
```

**How to Read the Build Artifacts Table:**

| Row                 | Meaning                                                                                                     |
|---------------------|-------------------------------------------------------------------------------------------------------------|
| **Scenario**        | The scenario name selected from the config file (i.e., the data instance used).                             |
| **Runtime**         | The runtime plugin that will execute this model (e.g., `local-dimod`).                                      |
| **Backend**         | The backend that compiled the model to a quantum-compatible form (e.g., `dimod-cqm-v1`).                   |
| **CQM**             | Path to the serialized Constrained Quadratic Model (binary, dimod format). This is the native IR.           |
| **BQM**             | Path to the serialized Binary Quadratic Model (binary, dimod format). Derived from the CQM via penalty conversion. |
| **Format**          | Path to the human-readable export (e.g., `qubo.json` or `ising.json`), depending on `--format`.            |
| **VarMap**          | Path to the variable-map JSON that translates internal variable labels to QSOL-level meanings.              |
| **Explain**         | Path to the compiler explanation overlay (diagnostics, warnings recorded during compilation).                |
| **Capability Report** | Path to the JSON report showing which capabilities the model requires and whether the target supports them. |
| **num_constraints** | Number of constraints in the compiled CQM (includes user-defined `must` constraints and internal encoding constraints). |
| **num_interactions**| Number of quadratic interaction terms in the BQM (i.e., edges in the QUBO graph).                           |
| **num_variables**   | Total number of binary variables in the BQM (includes user variables + compiler-generated auxiliary/slack variables). |

> **Key insight:** `num_variables` is typically larger than the number of unknowns you declared. The compiler introduces **auxiliary variables** (prefixed `aux:`) for linearization and **slack variables** (prefixed `slack_v`) to convert inequality constraints into equalities for the QUBO encoding.

See [Build Artifacts Deep Dive](#build-artifacts-deep-dive) for a detailed breakdown of each generated file.

---

### `qsol solve`

Compiles, runs, and exports solve results. This is the **end-to-end** command: it performs the build step, hands the compiled model to a runtime/sampler, and reports the results.

**Synopsis:**

```bash
qsol solve [OPTIONS] FILE
```

**All Options:**

| Option                  | Short | Type     | Default                          | Description                                                                  |
|-------------------------|-------|----------|----------------------------------|------------------------------------------------------------------------------|
| `FILE`                  | —     | path     | *required*                       | Path to the `.qsol` model source file.                                       |
| `--config`              | `-c`  | path     | auto-discovered `*.qsol.toml`    | Path to the TOML configuration file.                                         |
| `--out`                 | `-o`  | path     | `./outdir/<model_stem>`          | Output directory for artifacts and run output.                               |
| `--format`              | `-f`  | string   | config entrypoint, then `qubo`   | Export format for objective payload: `qubo`, `ising`, `bqm`, or `cqm`.       |
| `--runtime`             | `-u`  | string   | config entrypoint value          | Runtime plugin identifier.                                                   |
| `--plugin`              | `-p`  | string   | none                             | Load an extra plugin bundle (repeatable).                                    |
| `--runtime-option`      | `-x`  | key=val  | none                             | Pass runtime-specific options (repeatable). E.g., `-x sampler=exact`.        |
| `--runtime-options-file`| `-X`  | path     | none                             | JSON file containing runtime options (merged with `-x` flags).               |
| `--solutions`           | —     | int      | config value, then `1`           | Number of best unique solutions to return.                                   |
| `--energy-min`          | —     | float    | none                             | Inclusive minimum energy threshold for returned solutions.                    |
| `--energy-max`          | —     | float    | none                             | Inclusive maximum energy threshold for returned solutions.                    |
| `--scenario`            | —     | string   | config entrypoint scenario       | Scenario name to execute (repeatable for multi-scenario).                    |
| `--all-scenarios`       | —     | flag     | off                              | Execute all scenarios declared in the config.                                |
| `--combine-mode`        | —     | enum     | config value or `intersection`   | Merge mode for multi-scenario solve: `intersection` or `union`.              |
| `--failure-policy`      | —     | enum     | config value or `run-all-fail`   | Scenario failure policy: `run-all-fail`, `fail-fast`, or `best-effort`.      |

**Example:**

```bash
$ qsol solve examples/tutorials/graph_coloring.qsol \
    -c examples/tutorials/graph_coloring.qsol.toml \
    --runtime local-dimod \
    -x sampler=simulated-annealing \
    -x num_reads=100 \
    -o outdir/graph_coloring
```

**Example Output (stdout):**

The `solve` command prints **three tables** to stdout:

#### 1. Run Summary

```
                          Run Summary
┌──────────────────────────┬──────────────────────────────────────────────┐
│ Key                      │ Value                                        │
├──────────────────────────┼──────────────────────────────────────────────┤
│ Status                   │ ok                                           │
│ Runtime                  │ local-dimod                                  │
│ Backend                  │ dimod-cqm-v1                                 │
│ Runtime Parameters       │ num_reads=100                                │
│                          │ sampler=simulated-annealing                  │
│ Energy                   │ 0.0                                          │
│ Solutions Requested      │ 1                                            │
│ Solutions Returned       │ 1                                            │
│ Energy Min               │                                              │
│ Energy Max               │                                              │
│ Energy Threshold Passed  │ True                                         │
│ Timing (ms)              │ 5223.224                                     │
│ Run Output               │ outdir/graph_coloring/run.json               │
│ Capability Report        │ outdir/graph_coloring/capability_report.json │
└──────────────────────────┴──────────────────────────────────────────────┘
```

**How to read each row:**

| Row                        | Meaning                                                                                                                                  |
|----------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| **Status**                 | `ok` means all constraints were satisfied and the solver completed normally. Other values: `scenario_failed`, `failed`.                  |
| **Runtime**                | The runtime plugin used (e.g., `local-dimod` uses the dimod library locally).                                                            |
| **Backend**                | The backend that compiled the model (e.g., `dimod-cqm-v1` compiles to CQM → BQM via penalty method).                                   |
| **Runtime Parameters**     | The effective runtime configuration used for this run. Includes sampler type, `num_reads`, `seed`, etc. These come from `-x` flags, `--runtime-options-file`, or config defaults. |
| **Energy**                 | The energy (objective value) of the **best** solution found. **Lower is better** for minimization problems. An energy of `0.0` means the objective function evaluates to zero — for graph coloring, this means zero same-color conflicts. |
| **Solutions Requested**    | How many unique solutions were requested (from `--solutions` or config).                                                                 |
| **Solutions Returned**     | How many unique solutions the sampler actually found and returned.                                                                       |
| **Energy Min / Max**       | If `--energy-min` or `--energy-max` was set, these show the threshold bounds. Blank if not set.                                          |
| **Energy Threshold Passed**| `True` if all returned solutions satisfy the energy threshold; `False` if any violate it; blank if no threshold was set.                 |
| **Timing (ms)**            | Wall-clock time for the entire solve pipeline (compile + sample + post-process), in milliseconds.                                        |
| **Run Output**             | Path to the `run.json` file containing the full structured result.                                                                       |
| **Capability Report**      | Path to the `capability_report.json` file.                                                                                               |

#### 2. Returned Solutions

```
                              Returned Solutions
┌──────┬────────┬───────────┬─────────────┬─────────────┬────────┬──────────────────┬────────────────────────────────────────┐
│ Rank │ Energy │ Selected  │ Occurrences │ Probability │ Status │ Scenario Energ…  │ Sample                                 │
├──────┼────────┼───────────┼─────────────┼─────────────┼────────┼──────────────────┼────────────────────────────────────────┤
│ 1    │ 0.0    │ 5 selectd │ 1           │             │        │                  │ 5/45 active: ColorOf.is[N1,Red], Co... │
└──────┴────────┴───────────┴─────────────┴─────────────┴────────┴──────────────────┴────────────────────────────────────────┘
```

**How to read each column:**

| Column               | Meaning                                                                                                                 |
|----------------------|-------------------------------------------------------------------------------------------------------------------------|
| **Rank**             | Solution ranking by energy (1 = best). When `--solutions N` is used, you get up to N ranked solutions.                  |
| **Energy**           | Objective value of this particular solution. Lower is better for `minimize`, higher is better for `maximize`.            |
| **Selected**         | Summary of how many user-level variables are set to 1 (i.e., "selected" or "active"). Format: `N selected`.             |
| **Occurrences**      | How many times this exact solution was found across all sampler reads. Higher = more likely the sample is a true minimum.|
| **Probability**      | Estimated probability of this solution (if the sampler provides it; otherwise blank).                                   |
| **Status**           | Per-solution status from the runtime (e.g., indicates feasibility).                                                     |
| **Scenario Energies**| In multi-scenario mode, shows the energy of this solution in each individual scenario.                                  |
| **Sample**           | Compact summary of the binary variable assignment. Shows `active/total active` and names the first few active variables. Active = variable set to 1. Internal (`aux:`, `slack_`) variables are counted in the total but not shown by name. |

#### 3. Selected Assignments

```
                      Selected Assignments
┌────────────────────────┬──────────────────────────┐
│ Variable               │ Meaning                  │
├────────────────────────┼──────────────────────────┤
│ ColorOf.is[N1,Red]     │ ColorOf.is(N1,Red)       │
│ ColorOf.is[N2,Green]   │ ColorOf.is(N2,Green)     │
│ ColorOf.is[N3,Red]     │ ColorOf.is(N3,Red)       │
│ ColorOf.is[N4,Green]   │ ColorOf.is(N4,Green)     │
│ ColorOf.is[N5,Blue]    │ ColorOf.is(N5,Blue)      │
└────────────────────────┴──────────────────────────┘
```

**How to read each column:**

| Column       | Meaning                                                                                                          |
|--------------|------------------------------------------------------------------------------------------------------------------|
| **Variable** | The internal variable label used in the BQM/QUBO. Format: `UnknownName.is[SetElement1,SetElement2]`.             |
| **Meaning**  | The human-readable QSOL-level interpretation: `UnknownName.is(Element1,Element2)` — reads as "the unknown `UnknownName` maps element `Element1` to element `Element2`". |

> **How to interpret:** Each row represents a binary variable that the solver set to **1** in the best solution.
> For a `Mapping(Nodes -> Colors)` unknown called `ColorOf`, the variable `ColorOf.is[N1,Red] = 1` means *"Node N1 is assigned the color Red"*.
> Only user-level variables are shown — internal auxiliary and slack variables are filtered out.
> If this table shows `-` with "No (non-aux) binary variable set to 1 in the best sample", it means no user-level variable was activated (which usually signals a problem in the model or that the solver found a trivial assignment).

See [Solve Output Deep Dive](#solve-output-deep-dive) for a detailed breakdown of the `run.json` file.

---

## Inspection Commands

These commands let you debug and understand how QSOL parses and processes your model **without** running a full compile or solve.

### `qsol inspect parse`

Parses a QSOL model and prints the Abstract Syntax Tree (AST). This is useful for verifying that the parser understands your syntax correctly.

**Synopsis:**

```bash
qsol inspect parse [OPTIONS] FILE
```

**Options:**

| Option   | Short | Type | Default | Description                         |
|----------|-------|------|---------|-------------------------------------|
| `FILE`   | —     | path | *req.*  | Path to the `.qsol` source file.    |
| `--json` | `-j`  | flag | off     | Print AST as JSON (default: pretty-print). |

**Example:**

```bash
$ qsol inspect parse examples/tutorials/graph_coloring.qsol --json
```

**Example Output (abbreviated):**

```json
{
  "imports": [
    {
      "kind": "UseImport",
      "module_path": ["stdlib", "logic"]
    }
  ],
  "items": [
    {
      "kind": "PredicateDecl",
      "name": "can_coexist",
      "params": [
        {"name": "n1", "type": {"kind": "ElemType", "set_name": "Nodes"}},
        {"name": "n2", "type": {"kind": "ElemType", "set_name": "Nodes"}},
        {"name": "c",  "type": {"kind": "ElemType", "set_name": "Colors"}}
      ],
      "body": { "kind": "IfThenElse", "..." : "..." }
    },
    {
      "kind": "ProblemDecl",
      "name": "GraphColoring",
      "body": {
        "sets": ["Nodes", "Colors"],
        "params": [{"name": "Edge", "...": "..."}],
        "finds": [{"name": "ColorOf", "type": {"kind": "MappingType", "..."}}],
        "constraints": ["..."],
        "objectives": ["..."]
      }
    }
  ]
}
```

**How to read the AST:**

- **`imports`**: Each `use` statement in your model, showing the module path being imported.
- **`items`**: Top-level declarations. These include:
  - `PredicateDecl` / `FunctionDecl` — helper predicates/functions with their parameters and body expression.
  - `ProblemDecl` — the main problem block, containing `sets`, `params`, `finds` (unknowns), `constraints` (must-clauses), and `objectives` (minimize/maximize).
- Each node has a **`kind`** field indicating its AST type (e.g., `IfThenElse`, `Forall`, `Sum`, `BinaryOp`).
- Without `--json`, the output uses Python's `rich.pretty` format, which is more compact but less machine-parseable.

---

### `qsol inspect check`

Runs the full frontend pipeline — **parse → resolve → typecheck → validate** — without generating any backend code. Use this to quickly verify your model is syntactically and semantically correct.

**Synopsis:**

```bash
qsol inspect check [OPTIONS] FILE
```

**Options:**

| Option | Short | Type | Default | Description                      |
|--------|-------|------|---------|----------------------------------|
| `FILE` | —     | path | *req.*  | Path to the `.qsol` source file. |

**Example (no errors):**

```bash
$ qsol inspect check examples/tutorials/graph_coloring.qsol
No diagnostics.
```

**Example (with errors):**

If the model contains an error (e.g., referencing an undefined set), the output shows structured diagnostics:

```
error[QSOL1003]: undefined identifier `Nodez`
 --> graph_coloring.qsol:16:9
   |
16 |     set Nodez;
   |         ^^^^^ did you mean `Nodes`?
   |
```

**How to read diagnostics:**
- **Severity**: `error` (compilation stops), `warning` (proceed with caution).
- **Code**: A unique diagnostic code like `QSOL1003` — useful for searching docs or reporting bugs.
- **Message**: Human-readable description of the issue.
- **Location**: `file:line:col` pointing to the exact span of source code.
- **Notes/Help**: Additional suggestions (e.g., "did you mean...?") or context.

---

### `qsol inspect lower`

Lowers a QSOL model to the **symbolic kernel IR** — the intermediate representation used before instantiation with concrete data. This shows what the compiler "sees" after resolving, typechecking, and lowering, but before plugging in scenario data.

**Synopsis:**

```bash
qsol inspect lower [OPTIONS] FILE
```

**Options:**

| Option   | Short | Type | Default | Description                            |
|----------|-------|------|---------|----------------------------------------|
| `FILE`   | —     | path | *req.*  | Path to the `.qsol` source file.       |
| `--json` | `-j`  | flag | off     | Print lowered IR as JSON.              |

**Example:**

```bash
$ qsol inspect lower examples/tutorials/graph_coloring.qsol --json
```

**Example Output (abbreviated):**

```json
{
  "objectives": [
    {
      "direction": "minimize",
      "expression": {
        "kind": "Sum",
        "iterator": "n1",
        "domain": "Nodes",
        "body": {
          "kind": "Sum",
          "iterator": "n2",
          "domain": "Nodes",
          "body": { "kind": "FunctionCall", "name": "edge_conflicts", "..." : "..." }
        }
      }
    }
  ],
  "constraints": [
    {
      "kind": "Forall",
      "iterators": ["n1", "n2", "c"],
      "domains": ["Nodes", "Nodes", "Colors"],
      "body": { "kind": "PredicateCall", "name": "can_coexist", "..." : "..." }
    }
  ]
}
```

**How to read the lowered IR:**
- This is the **symbolic** representation — set elements are still abstract iterators (e.g., `n1 in Nodes`), not yet expanded to concrete values.
- **`objectives`**: Each `minimize` / `maximize` statement, showing the direction and the symbolic expression tree.
- **`constraints`**: Each `must` statement, with quantifiers (`Forall`, `Exists`) and their constraint bodies.
- The output mirrors the structure of your QSOL source, but in a normalized, resolver-validated form.
- Useful for verifying that helper predicates/functions were inlined correctly before data binding.

---

## Target Commands

These commands let you explore available runtimes and backends, and check if your model is supported by a specific target pair.

### `qsol targets list`

Lists all discovered runtime and backend plugins.

**Synopsis:**

```bash
qsol targets list [OPTIONS]
```

**Options:**

| Option     | Short | Type   | Default | Description                                 |
|------------|-------|--------|---------|---------------------------------------------|
| `--plugin` | `-p`  | string | none    | Load an extra plugin bundle (repeatable).   |

**Example:**

```bash
$ qsol targets list
```

**Example Output:**

```
              Runtimes
┌─────────────┬─────────────┬──────────────────────┐
│ ID          │ Name        │ Compatible Backends  │
├─────────────┼─────────────┼──────────────────────┤
│ local-dimod │ Local dimod │ dimod-cqm-v1         │
└─────────────┴─────────────┴──────────────────────┘
              Backends
┌──────────────┬──────────────────────────┐
│ ID           │ Name                     │
├──────────────┼──────────────────────────┤
│ dimod-cqm-v1 │ dimod CQM backend (v1)  │
└──────────────┴──────────────────────────┘
```

**How to read:**
- **Runtimes table**: Each row is a runtime plugin. The **ID** is what you pass to `--runtime`. **Compatible Backends** shows which backend(s) this runtime can execute.
- **Backends table**: Each row is a backend plugin. The **ID** is the backend that compiles your model to a specific quantum format. Currently the default and only built-in backend is `dimod-cqm-v1`.
- Custom plugins loaded with `--plugin` will appear in these tables alongside built-in ones.

---

### `qsol targets capabilities`

Shows detailed capability catalogs for a specific runtime/backend pair, and checks their compatibility.

**Synopsis:**

```bash
qsol targets capabilities --runtime ID [OPTIONS]
```

**Options:**

| Option      | Short | Type   | Default | Description                                 |
|-------------|-------|--------|---------|---------------------------------------------|
| `--runtime` | `-u`  | string | *req.*  | Runtime plugin identifier.                  |
| `--plugin`  | `-p`  | string | none    | Load an extra plugin bundle (repeatable).   |

**Example:**

```bash
$ qsol targets capabilities --runtime local-dimod
```

**Example Output:**

```
       Runtime Capabilities (local-dimod)
┌────────────────────────────────┬────────┐
│ Capability                     │ Status │
├────────────────────────────────┼────────┤
│ model.kind.cqm.v1             │ full   │
│ sampler.exact.v1              │ full   │
│ sampler.simulated-annealing.v1│ full   │
└────────────────────────────────┴────────┘
       Backend Capabilities (dimod-cqm-v1)
┌──────────────────────────────────────┬─────────┐
│ Capability                           │ Status  │
├──────────────────────────────────────┼─────────┤
│ constraint.compare.eq.v1            │ full    │
│ constraint.compare.ge.v1            │ full    │
│ constraint.compare.le.v1            │ full    │
│ constraint.quantifier.exists.v1     │ partial │
│ constraint.quantifier.forall.v1     │ full    │
│ expression.bool.and.v1             │ full    │
│ expression.bool.not.v1             │ full    │
│ expression.bool.or.v1              │ full    │
│ objective.if_then_else.v1          │ partial │
│ objective.sum.v1                   │ full    │
│ unknown.mapping.v1                 │ full    │
│ unknown.subset.v1                  │ full    │
│ unknown.custom.v1                  │ none    │
└──────────────────────────────────────┴─────────┘
       Pair Compatibility
┌─────────────┬──────────────┬────────────┐
│ Runtime     │ Backend      │ Compatible │
├─────────────┼──────────────┼────────────┤
│ local-dimod │ dimod-cqm-v1 │ yes        │
└─────────────┴──────────────┴────────────┘
```

**How to read:**

- **Capability Status** values:
  - `full` — fully supported, no limitations.
  - `partial` — supported with caveats or limitations (see `BACKEND_V1_LIMITS.md` for details).
  - `none` — not supported by this target.
- **Runtime Capabilities** describe what the runtime can execute: `model.kind.cqm.v1` means it accepts CQM models, `sampler.*` lists available sampler modes.
- **Backend Capabilities** describe what QSOL language features the backend can compile: constraint types, expression types, unknown types, etc.
- **Pair Compatibility** confirms whether the runtime and backend can work together. A `no` here means you need a different combination.

---

### `qsol targets check`

Checks if a specific model and scenario are supported by the selected target pair. This performs compilation up to the point of target validation but does **not** produce artifacts or run the solver.

**Synopsis:**

```bash
qsol targets check [OPTIONS] FILE
```

**Options:**

| Option              | Short | Type   | Default                       | Description                                                      |
|---------------------|-------|--------|-------------------------------|------------------------------------------------------------------|
| `FILE`              | —     | path   | *required*                    | Path to the `.qsol` model source file.                           |
| `--config`          | `-c`  | path   | auto-discovered `*.qsol.toml` | Path to the TOML configuration file.                             |
| `--runtime`         | `-u`  | string | config entrypoint value       | Runtime plugin identifier.                                       |
| `--plugin`          | `-p`  | string | none                          | Load an extra plugin bundle (repeatable).                        |
| `--out`             | `-o`  | path   | `./outdir/<model_stem>`       | Output directory for `capability_report.json` and `qsol.log`.   |
| `--scenario`        | —     | string | config entrypoint scenario    | Scenario name to check (repeatable for multi-scenario).          |
| `--all-scenarios`   | —     | flag   | off                           | Check all scenarios declared in the config.                      |
| `--failure-policy`  | —     | enum   | config or `run-all-fail`      | Scenario failure policy.                                         |

**Example:**

```bash
$ qsol targets check examples/tutorials/graph_coloring.qsol \
    -c examples/tutorials/graph_coloring.qsol.toml \
    --runtime local-dimod
```

**Example Output:**

```
                Target Support
┌────────────────────┬──────────────────────────────────────────────┐
│ Key                │ Value                                        │
├────────────────────┼──────────────────────────────────────────────┤
│ Scenario           │ triangle                                     │
│ Supported          │ yes                                          │
│ Runtime            │ local-dimod                                  │
│ Backend            │ dimod-cqm-v1                                 │
│ Capability Report  │ outdir/graph_coloring/capability_report.json │
└────────────────────┴──────────────────────────────────────────────┘
```

**How to read:**
- **Supported**: `yes` means the model+scenario compiles and all required capabilities are available on the target. `no` means there is a gap — check the capability report for details.
- The **Capability Report** JSON contains the full breakdown of required vs. available capabilities. This is the same file documented in the [Build Artifacts Deep Dive](#build-artifacts-deep-dive).

---

## Build Artifacts Deep Dive

When you run `qsol build`, the following files are generated in the output directory:

```
outdir/graph_coloring/
├── model.cqm                # Serialized CQM (binary)
├── model.bqm                # Serialized BQM (binary)
├── qubo.json                # Human-readable QUBO export
├── varmap.json              # Variable label → QSOL meaning
├── explain.json             # Compiler diagnostics
├── capability_report.json   # Target support report
└── qsol.log                 # Debug log
```

### `model.cqm` — Constrained Quadratic Model

A binary file in [dimod CQM serialization format](https://docs.ocean.dwavesys.com/). This is the **native intermediate representation** produced by the `dimod-cqm-v1` backend. It contains:

- The objective function as a quadratic polynomial over binary variables.
- All constraints as labeled, typed comparisons (equality, inequality) over quadratic expressions.

> This file is not human-readable. Load it in Python with `dimod.CQM.from_file("model.cqm")`.

### `model.bqm` — Binary Quadratic Model

A binary file in [dimod BQM serialization format](https://docs.ocean.dwavesys.com/). Derived from the CQM by converting all constraints into penalty terms added to the objective. This is what the sampler actually operates on.

> This file is not human-readable. Load it in Python with `dimod.BinaryQuadraticModel.from_file("model.bqm")`.

### `qubo.json` (or `ising.json`) — Human-Readable Format Export

The objective function exported in a structured, human-readable JSON format. The format depends on the `--format` flag:

**QUBO format (`qubo.json`):**

```json
{
  "offset": 700.0,
  "terms": [
    {"u": "ColorOf.is[N1,Blue]", "v": "ColorOf.is[N1,Blue]", "bias": -100.0},
    {"u": "ColorOf.is[N1,Green]", "v": "ColorOf.is[N1,Blue]", "bias": 40.0},
    {"u": "slack_v0830ca..._0", "v": "ColorOf.is[N1,Red]", "bias": 40.0}
  ]
}
```

**How to read:**

| Field      | Meaning                                                                                                    |
|------------|------------------------------------------------------------------------------------------------------------|
| **offset** | A constant energy offset added to the QUBO value. The total energy = `offset + sum(bias * u * v for each term)`. |
| **terms**  | Array of quadratic/linear interaction terms. Each has `u`, `v` (variable labels) and `bias` (coefficient). |
| **u**, **v** | Variable labels. When `u == v`, this is a **linear** term (self-interaction). When `u != v`, it is a **quadratic** term (pairwise interaction). |
| **bias**   | The coefficient. **Negative biases** encourage the variable(s) to be active (set to 1). **Positive biases** discourage co-activation. |

> **Key patterns:**
> - Large negative diagonal bias (e.g., `-100.0` on `ColorOf.is[N1,Blue]`) = strong incentive for `N1` to be `Blue`.
> - Positive off-diagonal bias (e.g., `40.0` on `ColorOf.is[N1,Green]` × `ColorOf.is[N1,Blue]`) = penalty for `N1` being both `Green` and `Blue` simultaneously (enforces one-hot encoding).
> - `slack_v*` variables are compiler-generated slack variables used to convert inequalities to QUBO-compatible equalities.

**Ising format (`ising.json`):** Same structure but uses `h` (linear biases) and `J` (quadratic couplings) fields following the Ising model convention.

### `varmap.json` — Variable Map

Maps internal variable labels to their QSOL-level semantic meaning:

```json
{
  "ColorOf.is[N1,Blue]":  "ColorOf.is(N1,Blue)",
  "ColorOf.is[N1,Green]": "ColorOf.is(N1,Green)",
  "ColorOf.is[N1,Red]":   "ColorOf.is(N1,Red)",
  "ColorOf.is[N2,Blue]":  "ColorOf.is(N2,Blue)"
}
```

**How to read:**

| Key (Variable Label)       | Value (Meaning)            | Interpretation                     |
|----------------------------|----------------------------|------------------------------------|
| `ColorOf.is[N1,Red]`      | `ColorOf.is(N1,Red)`      | "Does node N1 have color Red?"     |
| `ColorOf.is[N2,Green]`    | `ColorOf.is(N2,Green)`    | "Does node N2 have color Green?"   |

- **Label format**: `UnknownName.is[Arg1,Arg2]` — uses brackets, as used in the BQM/QUBO.
- **Meaning format**: `UnknownName.is(Arg1,Arg2)` — uses parentheses, as written in QSOL source.
- Only user-defined variables appear here; compiler-internal variables (`slack_*`, `aux:*`) are **not** included.
- Use this file to translate raw solver output back to human-readable assignments.

### `explain.json` — Compiler Explanation Overlay

Contains compiler diagnostics (warnings, info messages) recorded during the build:

```json
{
  "diagnostics": []
}
```

If the compiler encountered non-fatal issues (e.g., partially supported features, implicit conversions), they appear here as structured diagnostic objects with `severity`, `code`, `message`, and optional `notes`/`help` fields.

An empty `diagnostics` array means the build completed cleanly.

### `capability_report.json` — Target Support Report

A detailed report of what the model requires vs. what the target provides:

```json
{
  "supported": true,
  "selection": {
    "runtime": "local-dimod",
    "backend": "dimod-cqm-v1"
  },
  "required_capabilities": [
    "constraint.compare.eq.v1",
    "constraint.compare.le.v1",
    "constraint.quantifier.forall.v1",
    "expression.bool.and.v1",
    "objective.if_then_else.v1",
    "objective.sum.v1",
    "unknown.mapping.v1"
  ],
  "backend_capabilities": {
    "constraint.compare.eq.v1": "full",
    "constraint.compare.le.v1": "full",
    "constraint.quantifier.forall.v1": "full",
    "expression.bool.and.v1": "full",
    "objective.if_then_else.v1": "partial",
    "objective.sum.v1": "full",
    "unknown.mapping.v1": "full",
    "unknown.custom.v1": "none"
  },
  "runtime_capabilities": {
    "model.kind.cqm.v1": "full",
    "sampler.exact.v1": "full",
    "sampler.simulated-annealing.v1": "full"
  },
  "model_summary": {
    "kind": "cqm",
    "stats": {
      "num_variables": 45,
      "num_constraints": 80,
      "num_interactions": 105
    }
  },
  "issues": []
}
```

**How to read each field:**

| Field                      | Meaning                                                                                                  |
|----------------------------|----------------------------------------------------------------------------------------------------------|
| **supported**              | `true` if every required capability has at least `partial` support in the backend. `false` if any capability is `none`. |
| **selection**              | The runtime/backend pair that was selected (either explicitly or by resolution).                          |
| **required_capabilities**  | List of capability identifiers that the compiled model actually uses. These are derived from the QSOL features present in your model. |
| **backend_capabilities**   | Full catalog of what the backend supports (`full`, `partial`, `none`). Capabilities not required by your model are still listed. |
| **runtime_capabilities**   | Full catalog of what the runtime supports (e.g., which sampler modes are available).                     |
| **model_summary.stats**    | Compilation statistics: `num_variables` (total binary vars), `num_constraints` (CQM constraints), `num_interactions` (BQM edges). |
| **issues**                 | List of specific compatibility issues. Empty if `supported` is `true`.                                   |

### `qsol.log` — Debug Log

A timestamped text log of the CLI's internal operations. Contents depend on `--log-level`:

```
2026-02-17 10:15:32 | INFO | qsol.config | Inferred config file: graph_coloring.qsol.toml
2026-02-17 10:15:32 | INFO | qsol.cli | Inferred output directory: outdir/graph_coloring
2026-02-17 10:15:33 | DEBUG | qsol.compiler.pipeline | Frontend compilation complete: 0 errors, 0 warnings
```

Useful for debugging config resolution, understanding which scenario was selected, and diagnosing runtime issues.

---

## Solve Output Deep Dive

When you run `qsol solve`, the following output files are generated in addition to the build artifacts:

### `run.json` — Full Solve Result

The complete, structured solve result. This is the most important output file.

```json
{
  "schema_version": "1.0",
  "runtime": "local-dimod",
  "backend": "dimod-cqm-v1",
  "status": "ok",
  "energy": 0.0,
  "reads": 100,
  "timing_ms": 5223.224,
  "capability_report_path": "outdir/graph_coloring/capability_report.json",

  "best_sample": {
    "ColorOf.is[N1,Red]": 1,
    "ColorOf.is[N1,Green]": 0,
    "ColorOf.is[N1,Blue]": 0,
    "ColorOf.is[N2,Green]": 1,
    "slack_v0830ca..._0": 0
  },

  "selected_assignments": [
    {"variable": "ColorOf.is[N1,Red]",   "meaning": "ColorOf.is(N1,Red)",   "value": 1},
    {"variable": "ColorOf.is[N2,Green]", "meaning": "ColorOf.is(N2,Green)", "value": 1},
    {"variable": "ColorOf.is[N3,Red]",   "meaning": "ColorOf.is(N3,Red)",   "value": 1},
    {"variable": "ColorOf.is[N4,Green]", "meaning": "ColorOf.is(N4,Green)", "value": 1},
    {"variable": "ColorOf.is[N5,Blue]",  "meaning": "ColorOf.is(N5,Blue)",  "value": 1}
  ],

  "extensions": {
    "sampler": "simulated-annealing",
    "num_reads": 100,
    "seed": null,
    "requested_solutions": 1,
    "returned_solutions": 1,
    "runtime_options": {
      "sampler": "simulated-annealing",
      "num_reads": 100,
      "seed": null,
      "solutions": 1,
      "energy_min": null,
      "energy_max": null
    },
    "energy_threshold": {
      "min": null,
      "max": null,
      "passed": true,
      "inclusive": true,
      "scope": "all_returned",
      "violations": []
    },
    "solutions": [
      {
        "rank": 1,
        "energy": 0.0,
        "num_occurrences": 1,
        "sample": { "ColorOf.is[N1,Red]": 1, "..." : "..." },
        "selected_assignments": [ "..." ]
      }
    ]
  }
}
```

**Field-by-field interpretation:**

#### Top-Level Fields

| Field                      | Type             | Meaning                                                                                         |
|----------------------------|------------------|-------------------------------------------------------------------------------------------------|
| **schema_version**         | string           | Schema version of the run output format. Currently `"1.0"`.                                     |
| **runtime**                | string           | Runtime plugin used (e.g., `local-dimod`).                                                      |
| **backend**                | string           | Backend plugin used (e.g., `dimod-cqm-v1`).                                                    |
| **status**                 | string           | `"ok"` = solver completed and constraints satisfied. `"scenario_failed"` = one or more scenarios failed. |
| **energy**                 | float \| null    | Objective value of the best solution. `0.0` for graph coloring = zero conflicts. `null` if no valid solution was found. |
| **reads**                  | int              | Total number of samples (reads) the sampler performed.                                          |
| **timing_ms**              | float            | Wall-clock time for the full solve pipeline, in milliseconds.                                   |
| **capability_report_path** | string           | Path to the capability report JSON file.                                                        |

#### `best_sample`

A dictionary mapping every binary variable to its value (0 or 1) in the best solution:

| Key Pattern             | Value | Interpretation                                                     |
|-------------------------|-------|---------------------------------------------------------------------|
| `ColorOf.is[N1,Red]`   | `1`   | Node N1 is assigned color Red.                                      |
| `ColorOf.is[N1,Green]` | `0`   | Node N1 is NOT assigned color Green.                                |
| `slack_v0830ca..._0`   | `0`   | Internal slack variable (ignore for interpretation).                |

> **Tip:** Focus on variables with value `1` and ignore `slack_*`/`aux:*` prefixed variables — those are compiler internals.

#### `selected_assignments`

A filtered, human-readable list of only the user-level variables set to 1:

| Field        | Meaning                                                        |
|--------------|-----------------------------------------------------------------|
| **variable** | Internal variable label (with brackets).                       |
| **meaning**  | QSOL-level readable interpretation (with parentheses).         |
| **value**    | Always `1` (only active variables are listed).                 |

This is the **primary answer** to your optimization problem. For graph coloring, it tells you which color was assigned to each node.

#### `extensions`

Runtime-specific metadata and multi-solution data:

| Field                  | Meaning                                                                                              |
|------------------------|------------------------------------------------------------------------------------------------------|
| **sampler**            | Which sampler was used: `"exact"`, `"simulated-annealing"`.                                          |
| **num_reads**          | Number of reads/samples the sampler performed.                                                       |
| **seed**               | Random seed used (if set); `null` means non-deterministic.                                           |
| **requested_solutions**| How many solutions were requested.                                                                   |
| **returned_solutions** | How many unique solutions were actually found.                                                       |
| **runtime_options**    | Full snapshot of all runtime options used (merged from CLI, config, and defaults).                    |
| **energy_threshold**   | Energy filtering metadata: `min`/`max` thresholds, whether all returned solutions `passed`, and any `violations`. |
| **solutions**          | Array of ranked solution objects (see below).                                                        |

#### `extensions.solutions[]` — Individual Solution Objects

Each element in the `solutions` array represents one unique solution:

| Field                    | Type          | Meaning                                                                                       |
|--------------------------|---------------|-----------------------------------------------------------------------------------------------|
| **rank**                 | int           | Ranking (1 = best). Ordered by energy (ascending for minimize).                               |
| **energy**               | float         | Objective value of this solution.                                                             |
| **num_occurrences**      | int           | How many times this exact assignment was found across all reads. Higher = more stable.         |
| **sample**               | dict          | Full binary variable assignment (same format as `best_sample`).                               |
| **selected_assignments** | list          | Filtered list of active user-level variables (same format as top-level `selected_assignments`).|

> **Interpreting `num_occurrences`:** If you run 100 reads and solution #1 has `num_occurrences: 87`, that means the sampler found this exact assignment 87 out of 100 times — a strong signal that this is likely the global optimum. Low occurrences may indicate multiple near-optimal solutions or that the landscape is rugged.

---

## Multi-Scenario Mode

QSOL supports running the same model against **multiple data scenarios** in a single command. This is useful for robust optimization (finding solutions that work well across different inputs).

### Selecting Scenarios

```bash
# Run a specific scenario (overrides config entrypoint)
qsol solve model.qsol --scenario pentagon

# Run multiple named scenarios
qsol solve model.qsol --scenario triangle --scenario pentagon

# Run all scenarios declared in the config
qsol solve model.qsol --all-scenarios
```

### Combine Mode (`--combine-mode`)

When multiple scenarios are solved, solutions must be merged:

| Mode             | Behavior                                                                                         |
|------------------|--------------------------------------------------------------------------------------------------|
| `intersection`   | **(default)** Only return solutions that appear in **all** scenarios. Guarantees robustness.      |
| `union`          | Return solutions that appear in **any** scenario. Maximizes coverage at the cost of robustness.  |

### Failure Policy (`--failure-policy`)

Controls what happens when individual scenarios fail:

| Policy          | Behavior                                                                                          |
|-----------------|---------------------------------------------------------------------------------------------------|
| `run-all-fail`  | **(default)** Run all scenarios, then fail the command if any scenario failed.                     |
| `fail-fast`     | Stop immediately when the first scenario fails. Skip remaining scenarios.                         |
| `best-effort`   | Run all scenarios, succeed if **at least one** scenario succeeded.                                |

### Multi-Scenario Stdout

When running multiple scenarios, the `solve` command prints per-scenario summary tables followed by an aggregate summary:

```
             Run Summary (triangle)
┌──────────────────────┬──────────────────────┐
│ Key                  │ Value                │
├──────────────────────┼──────────────────────┤
│ Status               │ ok                   │
│ Runtime              │ local-dimod          │
│ Backend              │ dimod-cqm-v1         │
│ Run Output           │ outdir/.../run.json  │
│ Capability Report    │ outdir/.../cap...json│
└──────────────────────┴──────────────────────┘
             Run Summary (pentagon)
┌──────────────────────┬──────────────────────┐
│ ...                  │ ...                  │
└──────────────────────┴──────────────────────┘
```

The final aggregate **Run Summary** table includes additional multi-scenario fields:

| Row                    | Meaning                                                              |
|------------------------|----------------------------------------------------------------------|
| **Combine Mode**       | `intersection` or `union` — how solutions were merged.               |
| **Failure Policy**     | The active failure policy.                                           |
| **Scenarios Requested**| Total number of scenarios that were requested.                       |
| **Scenarios Executed** | Number of scenarios that actually ran (may differ with `fail-fast`). |
| **Scenarios Succeeded**| Number that completed successfully.                                  |
| **Scenarios Failed**   | Number that failed.                                                  |

In the **Returned Solutions** table, the **Scenario Energies** column is populated, showing per-scenario energy for each merged solution:

```
Scenario Energies: {"pentagon": 0.0, "triangle": 0.0}
```

### Multi-Scenario Output Directory

In multi-scenario mode, per-scenario artifacts are organized into subdirectories:

```
outdir/graph_coloring/
├── run.json                          # Aggregate merged result
├── capability_report.json            # Aggregate capability report
├── scenarios/
│   ├── triangle/
│   │   ├── model.cqm
│   │   ├── model.bqm
│   │   ├── qubo.json
│   │   ├── varmap.json
│   │   ├── explain.json
│   │   ├── capability_report.json
│   │   └── run.json                  # Per-scenario result
│   └── pentagon/
│       ├── model.cqm
│       ├── ...
│       └── run.json
└── qsol.log
```

---

## Command Aliases

Every command has a short alias for faster typing:

| Full Command              | Alias              |
|---------------------------|--------------------|
| `qsol build`              | `qsol b`           |
| `qsol solve`              | `qsol s`           |
| `qsol inspect parse`      | `qsol inspect p`   |
| `qsol inspect check`      | `qsol inspect c`   |
| `qsol inspect lower`      | `qsol inspect l`   |
| `qsol targets list`       | `qsol targets ls`  |
| `qsol targets capabilities`| `qsol targets caps`|
| `qsol targets check`      | `qsol targets chk` |
| `qsol inspect ...`        | `qsol ins ...`     |
| `qsol targets ...`        | `qsol tg ...`      |

**Example with aliases:**

```bash
# These are equivalent:
qsol solve model.qsol --runtime local-dimod
qsol s model.qsol -u local-dimod

# These are equivalent:
qsol inspect parse model.qsol --json
qsol ins p model.qsol -j
```

---

## Exit Codes

| Code | Meaning                                                                          |
|------|----------------------------------------------------------------------------------|
| `0`  | Command completed successfully. All checks passed, build succeeded, solve found valid solutions. |
| `1`  | Command failed. Parse errors, check failures, unsupported targets, build errors, solve failures, or runtime errors occurred. Check stderr/diagnostics for details. |
