# ⚛️ QSOL
## Quantum/Quadratic Specification-Oriented Optimization Language

> **Don't tell the solver *how* to search. Tell it *what* you need.**

**QSOL** is a high-level, declarative language for combinatorial optimization. You describe your problem — the sets, unknowns, constraints, and objectives — and the compiler handles translating it into a form that quantum and classical solvers can execute.

---

## 🚀 Why QSOL?

Traditional optimization often requires you to:
1.  Map your problem to low-level mathematical intermediates (QUBOs, Hamiltonians). 🧮
2.  Manage thousands of individual binary decision variables manually. 🤯
3.  Write imperative code that mixes *problem definition* with *solver configuration*. 🍝

QSOL takes a different approach:

*   **No Low-Level Math**: You define **Sets**, **Constraints**, and **Objectives** using a syntax close to natural language — not vectors and matrices.
*   **First-Class Unknowns**: The things you *want to find* — like a `Subset` or a `Mapping` — are expressed directly in QSOL as high-level declarations. You write `find ColorOf : Mapping(Nodes -> Colors)` and the compiler manages the underlying binary variables for you. *(See [QSOL Reference — Decisions and Unknowns](QSOL_reference.md#8-decisions-and-unknowns))*
*   **Solver Agnostic**: Write one model, target anything from your laptop CPU to a Quantum Processing Unit (QPU) (both adiabatic or gate-based).

---

## 🔮 What is a Program in QSOL?

A QSOL program is a **Problem Specification**, not a script. You describe the structure of your problem and the decisions to be made, and the compiler's job is to find a solution that satisfies your rules and optimizes your objective.

A QSOL program consists of 5 core components:

1.  **Sets** 🌍: The "entities" of your universe — the collections of things involved in the problem (e.g., `Nodes`, `Colors`, `Trucks`).
2.  **Params and Relations** 📊: The known data that defines a specific instance (e.g., `Distance`, `Cost`, or an `Edge(u, v)` relation). These values are fixed and provided in a configuration file.
3.  **Unknowns (the things you want to find)** 🤔: The decisions the solver must make. These are the core of QSOL — you express them at a high level, describing *what shape* the answer takes rather than managing individual variables.
    *   For example: `find Hired : Subset(Workers)` means "find a subset of workers to hire".
    *   Or: `find ColorOf : Mapping(Nodes -> Colors)` means "find a function that assigns a color to each node".
    *   The compiler automatically breaks these down into the binary variables that solvers need.
4.  **Constraints** ⚖️: The rules the solution must (or should) follow.
    *   `must`: Hard constraints — the solution is invalid if violated.
    *   `should` / `nice`: Soft preferences in the language surface. Backend
        support for soft preferences is intentionally narrow in the current
        v1 backend.

QSOL also supports finite-domain scalar decisions when a model needs a bounded
number or boolean switch directly:

```qsol
set Positions = Range(1, size(Nodes));
find Enabled : Bool;
find Load[Nodes] : Int[0 .. size(Nodes)];
```

`Range(lo, hi)` is inclusive and derived during grounding, so it does not appear
in scenario TOML. Bounded `Int` decisions compile to native CQM integer
variables.

Static relations let graph and incidence data stay tuple-shaped:

```qsol
use stdlib.graph;

relation Edge(u: Nodes, v: Nodes);
structure G = UndirectedGraph(Nodes, Edge);
minimize size(G.edges);
```

Compiler-owned helpers such as `all_different(...)`, `adjacent(...)`, and
`nonedge(...)` expand to ordinary constraints and relation membership formulas
before backend compilation. Graph structures such as `UndirectedGraph` and
`DirectedGraph` expose static domains like `G.edges`, `G.non_edges`, `D.arcs`,
and `D.non_arcs` for canonical graph iteration without creating solver
variables.
5.  **Objectives** 🏆: The quantitative goal (e.g., `minimize` cost, `maximize` efficiency).

> For the full language surface, see the [QSOL Language Reference](QSOL_reference.md).

---

## 🐣 Minimal Example: Graph Coloring

This example assigns a color to every node in a graph and minimizes same-color
edge conflicts. It uses an objective penalty rather than hard quadratic edge
constraints so it is runnable on the current `dimod-cqm-v1` backend.

### 1. The Model (`graph_coloring.qsol`)

```qsol
use stdlib.logic;

// Count same-color conflicts on an edge (0 if no edge)
function edge_conflicts(n1: Elem(Nodes), n2: Elem(Nodes)) =
    sum(if ColorOf.is(n1, c) and ColorOf.is(n2, c) then Edge[n1, n2] else 0 for c in Colors);

problem GraphColoring {
    set Nodes;
    set Colors;

    param Edge[Nodes, Nodes] : Real = 0.0;

    find ColorOf : Mapping(Nodes -> Colors);

    // Objective: minimize total conflicts
    minimize sum(sum(edge_conflicts(n1, n2) for n2 in Nodes) for n1 in Nodes);
}
```

**Key observations:**
*   `find ColorOf : Mapping(Nodes -> Colors)` — the **unknown**: "find a mapping that assigns exactly one color to each node".
*   `edge_conflicts(n1, n2)` — a custom **function** that counts whether two nodes share a color on an edge. Reused as the `minimize` objective.
*   The numeric `if ... then ... else ...` expression contributes the edge weight only when both endpoint color decisions are true.
*   `predicate` and `function` are **macros** — the compiler inlines them at every call site, so they can reference problem-scoped names like `Edge`, `ColorOf`, and `Colors`.

> For more on the QSOL syntax, see [QSOL Syntax Guide](docs/QSOL_SYNTAX.md). For the full standard library, see [stdlib reference](docs/STDLIB.md).

For graph models, `use stdlib.graph;` exposes compiler-owned unknowns such as
`Matching(G)`, `SteinerTree(G, Terminals)`, Hamiltonian path/cycle forms, and
`DirectedAcyclicSubgraph(D)`.
They keep graph semantics declarative while the backend owns the internal
variables and connectivity encodings.

### 2. The Data (`graph_coloring.qsol.toml`)

The **configuration file** (`.qsol.toml`) provides the concrete data for a specific instance of the problem. While the `.qsol` model describes the *structure* (sets, unknowns, constraints), the TOML file fills in the *values*: which scenario to run, what elements belong to each set, and the actual parameter values.

The configuration also specifies the **entrypoint** — which scenario to solve and which runtime to use.

```toml
schema_version = "1"

# Which scenario and runtime to use by default
[entrypoint]
scenario = "triangle"
runtime = "local-dimod"

# --- Scenario 1: A simple triangle (3 nodes, all connected) ---
[scenarios.triangle]
problem = "GraphColoring"

[scenarios.triangle.sets]
Nodes = ["N1", "N2", "N3"]
Colors = ["Red", "Green", "Blue"]

[scenarios.triangle.params.Edge]
N1 = { N1=0.0, N2=1.0, N3=1.0 }
N2 = { N1=1.0, N2=0.0, N3=1.0 }
N3 = { N1=1.0, N2=1.0, N3=0.0 }

# --- Scenario 2: A 5-node cycle (pentagon) ---
[scenarios.pentagon]
problem = "GraphColoring"

[scenarios.pentagon.sets]
Nodes = ["N1", "N2", "N3", "N4", "N5"]
Colors = ["Red", "Green", "Blue"]

[scenarios.pentagon.params.Edge]
N1 = { N1=0.0, N2=1.0, N3=0.0, N4=0.0, N5=1.0 }
N2 = { N1=1.0, N2=0.0, N3=1.0, N4=0.0, N5=0.0 }
N3 = { N1=0.0, N2=1.0, N3=0.0, N4=1.0, N5=0.0 }
N4 = { N1=0.0, N2=0.0, N3=1.0, N4=0.0, N5=1.0 }
N5 = { N1=1.0, N2=0.0, N3=0.0, N4=1.0, N5=0.0 }
```

#### What is a Scenario?

A **scenario** is a named data configuration for a specific instance of your problem. One `.qsol` model can have **multiple scenarios** — each with different set elements, parameter values, or even different problem blocks to solve.

This is useful when you want to test the same model against different inputs (e.g., small vs. large graphs, different cost matrices) without duplicating the model file. You define them all in the same `.qsol.toml`:

*   **`[scenarios.<name>]`** — each key under `scenarios` is a distinct scenario.
*   **`[entrypoint]`** — specifies which scenario to run by default.
*   **CLI override** — you can run any scenario with `--scenario <name>`:

```bash
# Run the default scenario (triangle)
uv run qsol solve graph_coloring.qsol

# Run a specific scenario
uv run qsol solve graph_coloring.qsol --scenario pentagon
```

> For the full configuration format and options, see [CLI Reference](docs/CLI.md).

### 3. Run It! 🏃💨

Use the `qsol` CLI to compile and solve.

```bash
# Install dependencies
uv sync --extra dev

# Run the solver
uv run qsol solve examples/tutorials/graph_coloring.qsol
```

Use `inspect estimate` before a build when you want grounded set/relation and
structure-domain sizes, decision summaries, CQM variable counts, and backend
warnings without writing artifacts. The warnings include graph-helper expansion
risks such as dense graph relations, forest acyclicity cuts, Steiner flow
variables, Hamiltonian transition/link variables, route transition aggregates,
and directed acyclic subgraph order constraints:

```bash
uv run qsol inspect estimate examples/tutorials/graph_helpers.qsol \
  --config examples/tutorials/graph_helpers.qsol.toml \
  --json
```

**Output:**
The compiler will:
1.  **Parse** your `.qsol` source file into an Abstract Syntax Tree (AST).
2.  **Analyze** (Sema): check types, resolve names, and validate logic safety.
3.  **Lower** the high-level `Mapping` unknown into binary variables and automatically generate the necessary internal constraints.
4.  **Ground** the model with your TOML data (it auto-detects `graph_coloring.qsol.toml`), expanding all quantifiers with concrete set elements.
5.  **Compile** (Backend): translate the grounded model into the solver's native format (e.g., a Constrained Quadratic Model).
6.  **Execute** (Runtime): send it to the solver (default: local simulated annealing).
7.  **Decode** the result back into readable JSON.

### 4. Generated Artifacts

After running `qsol solve`, the compiler produces an output directory (default: `outdir/<model_name>`) with the following files:

| Artifact | Description |
| :--- | :--- |
| `model.cqm`, `model.bqm` | The compiled model in binary format (Constraint Quadratic Model / Binary Quadratic Model). |
| `varmap.json` | Mapping from high-level variable names (e.g., `ColorOf.is(n1, Red)`) to low-level solver indices. |
| `explain.json` | Compiler diagnostics (warnings, errors) mapped to source code locations. |
| `capability_report.json` | Report of required model capabilities and backend support status. |
| `run.json` | Execution results: best energy, raw sample, selected binary assignments, and decoded scalar decisions. |
| `qubo.json` | (Optional) The model in flattened QUBO format (JSON) if requested. |

The `run.json` contains the decoded, human-readable solution:

```json
{
  "selected_assignments": [
    {"variable": "ColorOf.is[N1,Red]", "meaning": "ColorOf.is(N1,Red)", "value": 1}
  ],
  "scalars": {
    "T": 7,
    "Load[m1]": 5
  },
  "status": "ok"
}
```

> For details on the output directory structure and intermediate representations, see [Compiler Architecture](docs/COMPILER.md).

---

## 🧩 Extensibility: User-Defined Unknowns

One of QSOL's most powerful features is that **you can define new unknown types** using the `unknown` keyword. QSOL ships with two primitive unknowns — `Subset` and `Mapping` — but you can compose them into richer structures.

A custom unknown definition has three parts:
1.  **`rep`** (representation): The internal primitive unknowns that back this type.
2.  **`laws`**: Constraints that are automatically enforced whenever this type is used.
3.  **`view`**: The public API — predicates and functions — that users call.

### Example: `Permutation`

A permutation of a set is a mapping from the set to itself where every element appears exactly once as a target. Here's how you could define it:

```qsol
unknown Permutation(S) {
  rep {
    // Internally, a Permutation is just a Mapping from S to S
    f : Mapping(S -> S);
  }

  laws {
    // Each element must be mapped to by exactly one other element
    // (this + Mapping's built-in "each source maps to exactly one target"
    //  together enforce bijectivity)
    must forall b in S: count(a for a in S where f.is(a, b)) = 1;
  }

  view {
    // Users interact with Permutation.is(from, to)
    predicate is(a: Elem(S), b: Elem(S)) = f.is(a, b);
  }
}
```

Once defined, you use it like any built-in type:

```qsol
use stdlib.permutation;  // or use your own file

problem TSP {
    set Cities;
    param Dist[Cities, Cities] : Real;
    find Route : Permutation(Cities);
    minimize sum(sum(
        if Route.is(c1, c2) then Dist[c1, c2] else 0
    for c2 in Cities) for c1 in Cities);
}
```

### Example: `ExactSubset`

A subset with a fixed cardinality:

```qsol
unknown ExactSubset(S, k) {
  rep {
    inner : Subset(S);
  }
  laws {
    must count(x in S where inner.has(x)) = k;
  }
  view {
    predicate has(x: Elem(S)) = inner.has(x);
  }
}

// Usage: "Select exactly 3 workers"
// find Team : ExactSubset(Workers, 3);
```

### Reusable Macros: `predicate` and `function`

Beyond custom unknowns, you can define reusable logic with **predicates** (return `Bool`) and **functions** (return `Real`):

```qsol
// A predicate to check if two nodes are connected
predicate connected(n1: Elem(Nodes), n2: Elem(Nodes)) = Edge[n1, n2] = 1.0;

// A function to compute assignment cost
function assignment_cost(w: Elem(Workers), t: Elem(Tasks)) =
    if Assignment.is(t, w) then Cost[w, t] else 0;
```

The standard library itself is written in QSOL using these mechanisms — for example, `InjectiveMapping`, `SurjectiveMapping`, and `BijectiveMapping` are all defined as custom unknowns composing `Mapping` with additional constraints.

> For the full guide on custom unknowns and macros, see [Extending QSOL](docs/EXTENDING_QSOL.md) and [Tutorial 04](docs/tutorials/04-custom-unknowns-functions-and-predicates.md).

---

## ⚙️ How It Works: The Compiler Pipeline

QSOL uses a multi-stage compiler to transform your high-level specification into a format that solvers can execute.

```
Source (.qsol)  ➡️  Parse  ➡️  Sema  ➡️  Lower  ➡️  Ground  ➡️  Backend  ➡️  Runtime
```

1.  **Parse**: Reads your `.qsol` source code and converts it into an Abstract Syntax Tree (AST). This stage detects syntax errors like missing semicolons or malformed expressions.
2.  **Sema (Semantic Analysis)**: Resolves names, checks types, validates constraints, and expands `use` imports. This stage catches logical errors — like using a set that doesn't exist or passing the wrong type to a predicate.
3.  **Lower (Lowering)**: The key transformation step. It recursively breaks down complex unknowns (like `BijectiveMapping` or `Permutation`) into simpler ones (`Mapping`, `Subset`), and eventually into raw binary variables — *automatically generating the necessary glue constraints* at each level. For example, a `Mapping(A -> B)` produces `|A| × |B|` binary variables plus "exactly one" constraints for each element of `A`.
4.  **Ground (Grounding)**: Injects your specific data from the TOML configuration file, evaluates derived `Range` sets, grounds finite scalar domains, and unrolls quantifiers (`forall`, `exists`, `sum`) over concrete sets.
5.  **Backend**: Translates the grounded model into the solver's native format. For example, the `dimod-cqm-v1` backend produces a Constrained Quadratic Model (CQM) with native binary/integer variables and a converted BQM view when needed.
6.  **Runtime**: The component that actually executes the compiled model on a solver and returns results.

> For full details on the pipeline and intermediate representations (KIR, GIR), see [Compiler Architecture](docs/COMPILER.md). For backend specifics, see [Backend Reference](docs/BACKEND.md). For a complete list of supported and unsupported expression patterns, see [Backend V1 Limits](docs/BACKEND_V1_LIMITS.md).

### Runtimes

A **runtime** is the execution environment that takes the compiled model and runs it on a solver. Different runtimes target different hardware or solver backends:

| Runtime | Description | Best For |
| :--- | :--- | :--- |
| `local-dimod` | Runs locally using D-Wave's `dimod` samplers (simulated annealing or exact). | Development, testing, small instances. |
| `qiskit` | Targets IBM local Quantum noisy simulators via QAOA. | Quantum experiments with gate-based hardware. |
| Custom | You can write Python plugins to target any solver or cloud service. | Production, specialized hardware. |

You select a runtime in your TOML config (`runtime = "local-dimod"`) or via the CLI (`--runtime`).

> For runtime options and configuration, see [Runtimes](docs/RUNTIMES.md). To create your own, see [Custom Runtimes](docs/CUSTOM_RUNTIME.md).

---

## 🗺️ Documentation

| You are a... | Start Here | Then... |
| :--- | :--- | :--- |
| **New User** 👶 | **This README** | [First Program Tutorial](docs/tutorials/01-first-program.md) |
| **Power User** 🦸 | [QSOL Language Reference](QSOL_reference.md) | [Tutorials](docs/tutorials/) |
| **Contributor** 👷 | [CONTRIBUTING.md](CONTRIBUTING.md) | [VISION.md](VISION.md) |
| **AI Agent** 🤖 | [AGENTS.md](AGENTS.md) | [Codebase Guide](docs/CODEBASE.md) |

### Key References

*   **Language**: [QSOL Reference](QSOL_reference.md) · [Syntax Guide](docs/QSOL_SYNTAX.md)
*   **Tools**: [CLI Reference](docs/CLI.md) · [Compiler Architecture](docs/COMPILER.md)
*   **Solvers**: [Runtimes](docs/RUNTIMES.md) · [Backend](docs/BACKEND.md) · [Custom Runtimes](docs/CUSTOM_RUNTIME.md)
*   **Extending**: [Extending QSOL](docs/EXTENDING_QSOL.md) · [Standard Library](docs/STDLIB.md) · [Plugins](docs/PLUGINS.md)

## ⚖️ License

MIT License. Open and free. 🔓
