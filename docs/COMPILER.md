# QSOL Compiler Architecture

The QSOL compiler translates high-level declarative models into low-level representations suitable for optimization backends.

## 1. Compilation Pipeline

The pipeline consists of the following stages:

### Frontend
1.  **Parsing**: Converts `.qsol` source text into an Abstract Syntax Tree (AST).
2.  **Module Resolution**: Resolves `use` statements and loads referenced modules.
3.  **Elaboration**: Expands `unknown` types and macros into primitive structures and constraints.
4.  **Name Resolution**: Links identifiers to their definitions and builds a symbol table.
5.  **Type Checking**: Verifies type safety of expressions and constraints.
6.  **Validation**: Checks for semantic errors (e.g., unused variables, invalid constructs).
7.  **Global Helper Lowering**: Rewrites compiler-owned helpers such as `all_different`, `adjacent`, and `nonedge` into ordinary QSOL expressions.
8.  **Desugaring and Piecewise Lowering**: Normalizes guards/aggregates and lowers supported compiler-owned piecewise builtins (`abs`, aggregate `min`/`max`) into generated scalar `Int` decisions plus explicit constraints.
9.  **Kernel Lowering**: Transforms the validated AST into a symbolic Kernel IR (KIR).

### Middle / Grounding
If instance data is provided (via `model.qsol.toml`), the compiler performs **instantiation**:
1.  **Loading**: Reads data from the TOML file.
2.  **Binding**: Maps data values to model `set` and `param` declarations.
3.  **Grounding**: Evaluates derived `Range` sets and derived static relations, materializes scalar/indexed params and `StaticSubset` static domains, resolves bounded scalar decision domains including scenario-time static aggregate bounds, unrolls quantifiers (`forall`, `exists`), and expands data-dependent expressions, producing a Ground IR (GIR).

### Backend / Targeting
1.  **Target Selection**: Identifies the target runtime and backend (e.g., `local-dimod` + `dimod-cqm-v1`).
2.  **Support Check**: Verifies that the selected backend supports all features used in the Ground IR.
3.  **Compilation**: The backend translates the Ground IR into its native format (e.g., a `dimod.ConstrainedQuadraticModel`).
4.  **Export**: Artifacts are written to disk.

For `dimod-cqm-v1`, multiple objectives remain ordered in the IR. The backend
only combines them when config explicitly selects manual scalarization with one
weight for each objective label. Automatic bound-based scalarization is
reserved and reports `QSOL3202`.

## 2. Output Directory Structure

When running `qsol build` or `qsol solve`, the compiler generates an output directory (default: `outdir/<model_name>`).

### Standard Artifacts

*   **`model.cqm` / `model.bqm`**: The compiled Constrained Quadratic Model (CQM) and Binary Quadratic Model (BQM) in binary format (Python pickle of dimod objects).
    *   The CQM is canonical and may contain native binary and integer variables.
    *   The BQM is a converted binary view for runtimes/export formats that require it.
*   **`varmap.json`**: A mapping from human-readable variable names (e.g., `ColorOf.is(n1, Red)`) to the backend's internal integer indices.
*   **`explain.json`**: A list of diagnostics generated during compilation, mapped to source locations.
*   **`qubo.json` / `ising.json`**: The flattened optimization problem in JSON format (linear/quadratic terms), useful for debugging or portability.
*   **`capability_report.json`**: A report of the capabilities required by the model and whether the selected backend supports them.
*   **`run.json`** (for `solve`): The results of the execution, including:
    *   **status**: Runtime status such as `ok`, `threshold_failed`, or `scenario_failed`.
    *   **energy**: The objective value of the best solution.
    *   **best_sample**: The raw binary variable assignment for the best ranked solution.
    *   **selected_assignments**: A user-friendly list of active variables (e.g., `Picked.has(apple)`).
    *   **scalars**: Decoded scalar `Bool`/`Int` decisions, including indexed scalar labels such as `Load[m1]`.
    *   **extensions.solutions**: Ranked solution rows when one or more solutions are requested.

The current implementation stores ranked solutions inside `run.json`; it does
not write a separate `solutions.json` file.

## 3. Intermediate Representations (IR)

### Kernel IR (KIR)
A symbolic representation where sets, relations, and parameters are still abstract names. This is useful for analyzing the structure of the model without specific data.

### Ground IR (GIR)
A concrete representation where all sets are finite collections of values, static relations are finite tuples, and all expressions are fully expanded. This is the input to the backend plugins.

Derived sets are recorded with their source (`Range`) and are not loaded from scenario data. Range members are native integers in GIR so range binders can participate in numeric expressions.
Base relation declarations are loaded from scenario `relations` data during grounding. Derived relation declarations are then evaluated in dependency order from static sets, params, base relations, and earlier derived relations. Relation tuple binders and membership calls are resolved against those grounded relation values before backend code generation.

Static structure declarations are also grounded before backend code generation.
`UndirectedGraph(V, Edge)` and `DirectedGraph(V, Arc)` validate their source
relation and materialize compiler-owned static domains such as `G.edges`,
`G.non_edges`, `D.arcs`, and `D.non_arcs`. Structure declarations do not create
decision variables or backend constraints; their methods lower to static
relation membership formulas.

Stdlib-surfaced graph unknowns such as `Matching(G)` remain graph-level unknowns
through semantic checking and Kernel IR. The backend graph encoder validates the
grounded graph data, allocates only the required graph-indexed variables, and
adds the implicit graph constraints. For `Matching(G)`, this means one binary
variable per grounded `G.edges` tuple plus incident-edge constraints for
vertices of degree at least two. `MaximalMatching(G)` reuses that encoding and
adds one maximality constraint per grounded edge. `SpanningTree(G)` adds a
grounded edge-count constraint plus rooted connectivity flow. `Forest(G)` adds
internal acyclicity constraints over vertex subsets.

The reusable graph encoding helpers live in `qsol.backend.graph_encoding`.
They centralize canonical undirected edge lookup, incident-edge enumeration,
graph-unknown variable labels, and small graph constraint emitters so future
stdlib graph unknowns can share the same grounded graph semantics. Connectivity
is encoded with internal rooted flow variables, and forest acyclicity is encoded
with internal subset edge-count constraints. Both are implementation details;
QSOL source still has no public orientation or all-cycles syntax.

Bounded `Int` decisions are checked for groundability in sema and evaluated in grounding. Valid bounds may use static params, indexed params over static binders, `size(Set)`, `size(Relation)`, static `sum`/`count`, static `if` expressions, relation membership over static values, and arithmetic. Bounds that depend on decisions are rejected before backend code generation.

Supported piecewise numeric forms are lowered before KIR:

- `minimize abs(e)` becomes a generated aux decision with two hard constraints.
- `must abs(e) <= C` becomes two ordinary comparisons.
- `minimize max(term for ...)` and `maximize min(term for ...)` become one generated aux decision plus a generated `forall` constraint over the aggregate binders.

The generated aux decisions are ordinary scalar `Int` finds in KIR/GIR, so
model-size estimates and backend artifacts account for them.

Global helper lowering happens before KIR. `all_different(term for x in S)`
becomes pairwise disequality constraints over the finite domain. `adjacent` and
`nonedge` over binary relations become explicit relation membership formulas, so
the backend sees only grounded static relation calls and ordinary boolean logic.
Graph structure methods such as `G.adjacent(u, v)` are lowered after structure
domain materialization so the backend also sees ordinary static relation calls.
