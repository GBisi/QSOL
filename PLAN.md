# Next QSOL Graph Milestones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the next QSOL language/compiler iteration after the objective-label and `StaticSubset(V)` foundation, keeping the compiler focused on general graph abstractions and efficient encoders while exposing concrete graph modeling concepts through `stdlib.graph`.

**Architecture:** Do not add graph keywords or orientation syntax. Add a small stdlib graph unknown registry in sema, a backend/lowering encoder layer for graph selections and global graph properties, and user-facing names in `stdlib.graph` docs/source stubs. Prefer grounded, graph-size-aware encodings that create only the variables required by each unknown.

**Tech Stack:** Python, Lark AST already in place, QSOL sema/typechecker, Kernel IR, grounded graph structures, `dimod` CQM/BQM codegen, pytest, QSOL diagnostics.

---

## Current Baseline

Already landed in `ce8f567`:

- Objective labels parse, lower, and duplicate labels are rejected.
- `dimod-cqm-v1` rejects multiple objective statements with `QSOL3201`.
- `StaticSubset(V)` parses, resolves, grounds, iterates, supports `size(...)`, and supports `.has(...)`.
- Coverage threshold is 85 as requested.

The remaining work starts from `main`.

---

## Architecture Boundaries

### Compiler-Owned

- Graph structure metadata from `UndirectedGraph(V, Edge)` and `DirectedGraph(V, Arc)`.
- Internal graph encoder utilities:
  - edge/arc variable allocation,
  - incident-edge lookup,
  - deterministic undirected edge canonicalization,
  - optional reverse-edge lookup for views,
  - rooted connectivity flow,
  - topological/order variables where needed,
  - backend diagnostics and model-size estimates.
- Sema validation for stdlib-surfaced compiler-known unknowns.

### Stdlib-Surfaced

- `Matching(G)`
- `MaximalMatching(G)`
- `SpanningTree(G)`
- `Forest(G)`
- `HamiltonianPath(G)`
- `HamiltonianCycle(G)`
- `SteinerTree(G, Terminals)`

These are not grammar features. They are unknown type names exposed by `stdlib.graph`, with compiler-known implementations until the source-level custom unknown system can express indexed scalar rep fields and graph intrinsics directly.

### Explicit Non-Goals During These Milestones

- No `lexicographic` syntax.
- No public `oriented_arcs`, `DirectedView`, or bidirected graph syntax.
- No all-cycles domain.
- No bound-inference syntax.
- No broad custom unknown system rewrite before graph value is delivered.
- No silent multi-objective scalarization.

---

## Milestone 1: Stdlib Graph Unknown Registry And `Matching(G)`

**Purpose:** Establish the smallest working pattern for stdlib-surfaced, compiler-known graph unknowns.

**Files:**
- Modify: `src/qsol/sema/resolver.py`
- Modify: `src/qsol/sema/typecheck.py`
- Modify: `src/qsol/targeting/compatibility.py`
- Modify: `src/qsol/targeting/plugins.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/stdlib/graph.qsol`
- Test: `tests/parser/test_parser.py`
- Test: `tests/sema/test_typecheck.py`
- Test: `tests/backend/test_compile.py`
- Test: `tests/targeting/test_compatibility.py`
- Docs: `QSOL_reference.md`, `docs/QSOL_SYNTAX.md`, `docs/STDLIB.md`, `docs/BACKEND.md`, `docs/COMPILER.md`

- [x] **Step 1: Add failing parser/sema/backend tests**

Add tests for:

```qsol
use stdlib.graph;

problem MatchingDemo {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);

  find M : Matching(G);

  must forall (u, v) in G.edges: M.has_edge(u, v) => G.adjacent(u, v);
  minimize count((u, v) in G.edges where M.has_edge(u, v));
}
```

Expected behaviors:

- `find M : Matching(G);` parses as an unknown type with one arg.
- Resolver rejects `Matching(V)` because `V` is a set, not a graph structure.
- Typechecker accepts `M.has_edge(u, v)` where `u` and `v` are elements of `G.vertices`.
- Backend creates one binary variable per grounded undirected edge.
- Backend adds `<= 1` incident-edge constraints for vertices with at least two incident edges.
- Backend resolves `M.has_edge(b, a)` to the same variable as `M.has_edge(a, b)` for undirected graphs.

Run:

```bash
uv run pytest \
  tests/parser/test_parser.py::test_parse_matching_unknown \
  tests/sema/test_typecheck.py::test_matching_unknown_requires_graph_structure \
  tests/backend/test_compile.py::test_matching_graph_unknown_builds_efficient_edge_variables \
  -q
```

Expected: fail before implementation.

- [x] **Step 2: Implement sema support**

Implement a small hardcoded registry first. Do not create a general plugin system.

Rules:

- `Matching` takes exactly one argument.
- The argument must resolve to `SymbolKind.STRUCTURE`.
- The structure constructor must be `UndirectedGraph`.
- The type is still represented as `UnknownInstanceType(UnknownTypeRef("Matching", ("G",)))`.
- `M.has_edge(u, v)` returns `Bool`.
- `has_edge` takes exactly two vertex elements from the graph vertex set.

Run:

```bash
uv run pytest tests/sema/test_typecheck.py::test_matching_unknown_requires_graph_structure -q
```

Expected: pass.

- [x] **Step 3: Implement backend support**

In `DimodCodegen`:

- Allocate labels as `M.has_edge[a,b]` internally.
- Export varmap meanings as `M.has_edge(a,b)`.
- Add matching constraints:

```text
for each vertex v:
  sum(M.has_edge(e) for incident edge e) <= 1
```

- Resolve reversed undirected view calls by checking both `(u, v)` and `(v, u)` labels.
- Emit a QSOL diagnostic if the graph structure was not grounded.
- Skip degree-0 and degree-1 vertices because their matching constraints are redundant.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_matching_graph_unknown_builds_efficient_edge_variables -q
```

Expected: pass.

- [x] **Step 4: Add targeting capability**

Add required capability `unknown.graph.matching.v1` and mark it supported by `dimod-cqm-v1`.

Run:

```bash
uv run pytest tests/targeting/test_compatibility.py::test_extract_required_capabilities_includes_matching_unknown -q
```

Expected: pass.

- [x] **Step 5: Update docs**

Document `Matching(G)` in `stdlib.graph`, including:

- one selected edge variable per `G.edges`,
- matching means each vertex touches at most one selected edge,
- `M.has_edge(u, v)` is the view,
- objectives decide minimum/maximum/weighted matching variants.

- [x] **Step 6: Gate and commit**

Run:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
git add src tests docs QSOL_reference.md
git commit -m "Add stdlib graph Matching unknown"
git push origin main
```

---

## Milestone 2: Shared Graph Encoder Utilities And Diagnostics

**Purpose:** Move `Matching(G)` support out of ad hoc backend branches before adding more graph unknowns.

**Files:**
- Create: `src/qsol/backend/graph_encoding.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/compiler/estimate.py`
- Test: `tests/backend/test_graph_encoding.py`
- Test: `tests/compiler/test_estimate.py`
- Docs: `docs/BACKEND.md`, `docs/COMPILER.md`, `docs/CODEBASE.md`

- [x] **Step 1: Add failing unit tests for graph encoding helpers**

Required helper behavior:

- canonical undirected edge lookup returns the same key for `(a, b)` and `(b, a)`;
- incident edge lookup is deterministic;
- missing edge view returns a diagnostic-ready `None`, not a traceback;
- estimate reports variable and constraint counts for matching.

Run:

```bash
uv run pytest tests/backend/test_graph_encoding.py -q
```

Expected: fail because the helper module does not exist.

- [x] **Step 2: Extract helpers**

Create `graph_encoding.py` with focused utilities:

- `GraphData.from_ground_problem(problem, graph_name, span, diagnostics)`
- `GraphData.edge_key(u, v)`
- `GraphData.incident_edges(vertex)`
- `GraphUnknownLabels(find_name).edge_var(edge)`
- `add_degree_at_most_one_constraints(cqm, graph=..., labels=..., binaries=..., span=..., diagnostics=...)`

Keep it backend-local for now. Do not expose it as public API.

- [x] **Step 3: Rewire `Matching(G)` to helpers**

`dimod_codegen.py` should call helper functions rather than reimplementing canonical edge logic.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_matching_graph_unknown_builds_efficient_edge_variables tests/backend/test_graph_encoding.py -q
```

Expected: pass.

- [x] **Step 4: Add diagnostics and estimates**

Diagnostics:

- `QSOL3301`: graph unknown references an ungrounded or non-graph structure.
- `QSOL3302`: graph view references a non-edge.

Estimate payload:

```json
{
  "decision_variables": {
    "M": {
      "kind": "Matching",
      "binary_variables": 2,
      "degree_constraints": 1
    }
  },
  "constraints": {
    "graph_matching_degree": 1
  }
}
```

Run:

```bash
uv run pytest tests/compiler/test_estimate.py tests/backend/test_graph_encoding.py -q
```

Expected: pass.

- [x] **Step 5: Gate and commit**

Run mandatory gates, then:

```bash
git add src tests docs
git commit -m "Refactor graph unknown encoding helpers"
git push origin main
```

---

## Milestone 3: `MaximalMatching(G)`

**Purpose:** Add the first specialized stdlib graph unknown using the shared edge-selection foundation.

**Files:**
- Modify: `src/qsol/sema/resolver.py`
- Modify: `src/qsol/sema/typecheck.py`
- Modify: `src/qsol/backend/graph_encoding.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/targeting/compatibility.py`
- Modify: `src/qsol/targeting/plugins.py`
- Modify: `src/qsol/stdlib/graph.qsol`
- Test: `tests/sema/test_typecheck.py`
- Test: `tests/backend/test_compile.py`
- Test: `tests/targeting/test_compatibility.py`
- Docs: `QSOL_reference.md`, `docs/QSOL_SYNTAX.md`, `docs/STDLIB.md`, `docs/BACKEND.md`

- [x] **Step 1: Add failing tests**

Program:

```qsol
use stdlib.graph;

problem MinimumMaximalMatchingDemo {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);

  find M : MaximalMatching(G);

  minimize count((u, v) in G.edges where M.has_edge(u, v)) as cardinality;
}
```

Backend expectations:

- same edge variables as `Matching`;
- degree constraints from matching;
- for every graph edge `(u, v)`, add maximality constraint:

```text
M.has_edge(u, v) OR matched(u) OR matched(v)
```

where `matched(x)` is the sum of selected incident edges at `x` being at least one.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_maximal_matching_adds_maximality_constraints -q
```

Expected: fail.

- [x] **Step 2: Implement registry and type support**

`MaximalMatching` has the same graph argument and `.has_edge(u, v)` view as `Matching`.

- [x] **Step 3: Implement efficient maximality constraints**

For each edge `(u, v)`:

```text
sum(selected edges incident to u or v) >= 1
```

Because matching constraints already enforce at most one incident selected edge per endpoint, this is enough and avoids extra `matched(v)` variables.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_maximal_matching_adds_maximality_constraints -q
```

Expected: pass.

- [x] **Step 4: Gate and commit**

Run mandatory gates, then:

```bash
git add src tests docs QSOL_reference.md
git commit -m "Add stdlib graph MaximalMatching unknown"
git push origin main
```

---

## Milestone 4: Internal Connectivity And Forest Encoders

**Purpose:** Add reusable internal graph global constraints before exposing tree-like unknowns.

**Files:**
- Modify: `src/qsol/backend/graph_encoding.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Test: `tests/backend/test_graph_encoding.py`
- Test: `tests/backend/test_compile.py`
- Docs: `docs/BACKEND.md`, `docs/CODEBASE.md`

- [x] **Step 1: Add failing tests for connected and forest encoders**

Tests should use tiny grounded graphs:

- path `a-b-c` connected with selected edges `ab, bc`;
- disconnected selected edge set rejected by generated constraints;
- triangle forest encoding rejects selecting all three edges.

Run:

```bash
uv run pytest tests/backend/test_graph_encoding.py::test_connectivity_encoder_uses_rooted_flow tests/backend/test_graph_encoding.py::test_forest_encoder_rejects_cycle -q
```

Expected: fail.

- [x] **Step 2: Implement rooted flow connectivity**

Encoding:

- choose deterministic root from required vertices;
- add directed flow variable per oriented selected edge only when connectivity is needed;
- selected edge opens capacity in both orientations;
- non-root selected vertices require one unit of inflow;
- root supplies selected vertex count minus one.

Keep orientation internal. Do not add user-visible orientation APIs.

- [x] **Step 3: Implement forest acyclicity**

KISS first encoding:

- selected edge count <= selected vertex count - number_of_components is hard without component variables;
- use internal subset edge-count constraints `selected_edges_inside(S) <= |S| - 1`;
- keep this exponential encoding internal and documented until estimator warnings are added.

Decision rule: correctness beats compactness; variable count must be reported.

- [x] **Step 4: Gate and commit**

Run mandatory gates, then:

```bash
git add src tests docs
git commit -m "Add internal graph connectivity encoders"
git push origin main
```

---

## Milestone 5: `SpanningTree(G)` And `Forest(G)`

**Purpose:** Surface tree-like graph unknowns once the internal encoders are tested.

**Files:**
- Modify: `src/qsol/sema/resolver.py`
- Modify: `src/qsol/sema/typecheck.py`
- Modify: `src/qsol/backend/graph_encoding.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/targeting/compatibility.py`
- Modify: `src/qsol/targeting/plugins.py`
- Modify: `src/qsol/stdlib/graph.qsol`
- Test: `tests/sema/test_typecheck.py`
- Test: `tests/backend/test_compile.py`
- Test: `tests/targeting/test_compatibility.py`
- Docs: `QSOL_reference.md`, `docs/QSOL_SYNTAX.md`, `docs/STDLIB.md`, `docs/BACKEND.md`

- [x] **Step 1: Add failing tests**

Programs:

```qsol
use stdlib.graph;

problem SpanningTreeDemo {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find T : SpanningTree(G);
  minimize count((u, v) in G.edges where T.has_edge(u, v));
}
```

```qsol
use stdlib.graph;

problem ForestDemo {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find F : Forest(G);
  minimize count((u, v) in G.edges where F.has_edge(u, v));
}
```

Expected:

- `SpanningTree`: one edge variable per edge, selected edge count `size(V) - 1`, all vertices connected.
- `Forest`: one edge variable per edge, no selected cycle.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_spanning_tree_builds_connectivity_and_edge_count tests/backend/test_compile.py::test_forest_rejects_selected_cycle -q
```

Expected: fail.

- [x] **Step 2: Implement sema/type support**

Both unknowns:

- require one `UndirectedGraph` argument;
- expose `.has_edge(u, v) -> Bool`.

- [x] **Step 3: Implement backend encoding**

`SpanningTree(G)`:

- reuse selected-edge variable allocation;
- add `sum(selected_edges) == |V| - 1`;
- add rooted connectivity over all vertices.

`Forest(G)`:

- reuse selected-edge variable allocation;
- add internal forest/acyclic constraints.

- [x] **Step 4: Gate and commit**

Run mandatory gates, then:

```bash
git add src tests docs QSOL_reference.md
git commit -m "Add stdlib graph tree unknowns"
git push origin main
```

---

## Milestone 6: `HamiltonianPath(G)` And `HamiltonianCycle(G)`

**Purpose:** Add vertex-order graph unknowns with clear hard adjacency semantics.

**Files:**
- Modify: `src/qsol/sema/resolver.py`
- Modify: `src/qsol/sema/typecheck.py`
- Modify: `src/qsol/backend/graph_encoding.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/targeting/compatibility.py`
- Modify: `src/qsol/targeting/plugins.py`
- Modify: `src/qsol/stdlib/graph.qsol`
- Test: `tests/sema/test_typecheck.py`
- Test: `tests/backend/test_compile.py`
- Docs: `QSOL_reference.md`, `docs/QSOL_SYNTAX.md`, `docs/STDLIB.md`, `docs/BACKEND.md`

- [x] **Step 1: Add failing tests**

Program:

```qsol
use stdlib.graph;

problem HamiltonianCycleDemo {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find C : HamiltonianCycle(G);
  minimize 0;
}
```

Expected:

- position variables are internal;
- every position has exactly one vertex;
- every vertex appears exactly once;
- consecutive positions must be adjacent;
- cycle adds wraparound adjacency.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_hamiltonian_path_builds_position_assignment tests/backend/test_compile.py::test_hamiltonian_cycle_adds_wraparound_adjacency -q
```

Expected: fail.

- [x] **Step 2: Implement sema/type support**

Views:

- `P.at(pos, v) -> Bool`
- `P.uses(u, v) -> Bool`
- `C.at(pos, v) -> Bool`
- `C.uses(u, v) -> Bool`

Positions are internal numeric positions `1..|V|`; do not require users to declare a positions set.

- [x] **Step 3: Implement backend encoding**

Use assignment variables:

```text
x[position, vertex] in {0,1}
```

Constraints:

- each position exactly one vertex;
- each vertex exactly one position;
- forbid non-adjacent consecutive pairs by adding `x[p,u] + x[p+1,v] <= 1`;
- for cycles, also forbid non-adjacent wraparound pairs.

This is O(n^2) variables and O(n^3) forbidden-pair constraints in dense worst case, but it is simple, correct, and inspectable.

- [x] **Step 4: Gate and commit**

Mandatory gates passed. Commit and push are intentionally not performed by the
agent unless explicitly requested by the user.

Run mandatory gates, then:

```bash
git add src tests docs QSOL_reference.md
git commit -m "Add stdlib Hamiltonian graph unknowns"
git push origin main
```

---

## Milestone 7: `SteinerTree(G, Terminals)`

**Purpose:** Use `StaticSubset(V)` and connectivity encoders for a specialized stdlib graph unknown.

**Files:**
- Modify: `src/qsol/sema/resolver.py`
- Modify: `src/qsol/sema/typecheck.py`
- Modify: `src/qsol/backend/graph_encoding.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/targeting/compatibility.py`
- Modify: `src/qsol/targeting/plugins.py`
- Modify: `src/qsol/stdlib/graph.qsol`
- Test: `tests/sema/test_typecheck.py`
- Test: `tests/backend/test_compile.py`
- Test: `tests/backend/test_instance_and_codegen_branches.py`
- Docs: `QSOL_reference.md`, `docs/QSOL_SYNTAX.md`, `docs/STDLIB.md`, `docs/BACKEND.md`

- [x] **Step 1: Add failing tests**

Program:

```qsol
use stdlib.graph;

problem SteinerTreeDemo {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);

  param Terminals : StaticSubset(V);
  find T : SteinerTree(G, Terminals);

  minimize count((u, v) in G.edges where T.has_edge(u, v));
}
```

Expected:

- empty `Terminals` is rejected with a QSOL diagnostic;
- all terminals are selected vertices;
- selected edges imply selected endpoints;
- selected vertices are connected by selected edges;
- tree/acyclic semantics are enforced, not left to objective positivity.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_steiner_tree_requires_nonempty_terminals tests/backend/test_compile.py::test_steiner_tree_builds_vertex_edge_connectivity -q
```

Expected: fail.

- [x] **Step 2: Implement sema/type support**

`SteinerTree` takes:

- first arg: `UndirectedGraph`;
- second arg: `StaticSubset` domain whose parent element set matches graph vertices.

Views:

- `T.has_edge(u, v) -> Bool`
- `T.has_vertex(v) -> Bool`

- [x] **Step 3: Implement backend encoding**

Variables:

- one selected vertex variable per `G.vertices`;
- one selected edge variable per `G.edges`.

Constraints:

- every terminal vertex selected;
- selected edge implies both endpoints selected;
- selected non-root vertex receives one flow unit from root if selected;
- selected edge capacity gates flow;
- acyclicity or tree edge-count tightening:

```text
sum(selected_edges) == sum(selected_vertices) - 1
```

because connectivity plus this count enforces a tree on selected vertices.

- [x] **Step 4: Gate and commit**

Mandatory gates passed. Commit and push are intentionally not performed by the
agent unless explicitly requested by the user.

Run mandatory gates, then:

```bash
git add src tests docs QSOL_reference.md
git commit -m "Add stdlib SteinerTree graph unknown"
git push origin main
```

---

## Milestone 8: Ordered Objective Manual Scalarization

**Purpose:** Complete the objective-label story without unsafe automatic bound inference.

**Files:**
- Modify: `src/qsol/config/types.py`
- Modify: `src/qsol/config/loader.py`
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/compiler/options.py`
- Modify: `src/qsol/compiler/pipeline.py`
- Test: `tests/config/test_loader.py`
- Test: `tests/backend/test_compile.py`
- Test: `tests/cli/test_cli_commands.py`
- Docs: `QSOL_reference.md`, `docs/BACKEND.md`, `docs/COMPILER.md`, `docs/CLI.md`, `docs/tutorials/03-compiling-running-and-reading-results.md`

- [x] **Step 1: Add failing tests**

Config:

```toml
[entrypoint.objectives]
qubo_policy = "manual"

[entrypoint.objectives.qubo_weights]
conflicts = 1000.0
used_colors = 1.0
```

Expected:

- manual weights are accepted by objective label;
- missing manual weight is rejected;
- unknown objective label in config is rejected;
- `qubo_policy = "error"` keeps current rejection behavior;
- `qubo_policy = "auto"` rejects with “auto bounds not implemented” until finite bound proof exists.

Run:

```bash
uv run pytest tests/config/test_loader.py::test_objective_qubo_weights_parse tests/backend/test_compile.py::test_manual_objective_weights_scalarize_labeled_objectives -q
```

Expected: fail.

- [x] **Step 2: Implement config model**

Add:

```python
qubo_policy: Literal["error", "manual", "auto"] = "error"
qubo_weights: dict[str, float] = field(default_factory=dict)
```

Support entrypoint defaults and scenario overrides.

- [x] **Step 3: Implement manual scalarization only**

For multiple objectives:

- `error`: emit `QSOL3201`;
- `manual`: use label or `objective_N` key;
- `auto`: emit `QSOL3202` until proven finite bounds are implemented.

Do not guess weights.

- [x] **Step 4: Gate and commit**

Mandatory gates passed. Commit and push are intentionally not performed by the
agent unless explicitly requested by the user.

Run mandatory gates, then:

```bash
git add src tests docs QSOL_reference.md
git commit -m "Add manual scalarization for ordered objectives"
git push origin main
```

---

## Milestone 9: Backend Shape Diagnostics Hardening

**Purpose:** Make unsupported backend shapes actionable after the graph work expands the reachable model surface.

**Files:**
- Modify: `src/qsol/backend/dimod_codegen.py`
- Modify: `src/qsol/compiler/pipeline.py`
- Test: `tests/backend/test_compile.py`
- Test: `tests/cli/test_cli_commands.py`
- Docs: `docs/BACKEND.md`, `docs/BACKEND_V1_LIMITS.md`, `docs/COMPILER.md`

- [x] **Step 1: Add failing diagnostics tests**

Cases:

- cubic Boolean product reports QSOL diagnostic, not traceback;
- unsupported multiplication of non-binary expressions reports a QSOL diagnostic;
- unsupported piecewise still reports `QSOL3101`;
- graph encoding too large or unbounded reports a graph-specific diagnostic.

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_cubic_terms_report_backend_shape_diagnostic tests/backend/test_compile.py::test_unsupported_piecewise_keeps_qsol3101 -q
```

Expected: fail for missing or vague diagnostics.

- [x] **Step 2: Add diagnostic family**

Use:

- `QSOL3001`: expression degree exceeds backend support;
- `QSOL3002`: unsupported multiplication shape;
- `QSOL3101`: existing piecewise limit;
- `QSOL330x`: graph lowering/encoding issues.

- [x] **Step 3: Gate and commit**

Mandatory gates passed. Commit and push are intentionally not performed by the
agent unless explicitly requested by the user.

Run mandatory gates, then:

```bash
git add src tests docs
git commit -m "Improve backend shape diagnostics"
git push origin main
```

---

## Milestone 10: Examples, Tutorials, And Final Coherence Pass

**Purpose:** Make the new surface learnable and verify examples remain reproducible.

**Files:**
- Create: `examples/tutorials/matching.qsol`
- Create: `examples/tutorials/steiner_tree.qsol`
- Modify: `examples/run_equivalence_suite.py`
- Modify: `docs/TUTORIAL.md`
- Modify: `docs/tutorials/02-writing-your-own-model.md`
- Modify: `docs/tutorials/03-compiling-running-and-reading-results.md`
- Modify: `README.md`
- Test: `tests/cli/test_cli_commands.py`

- [x] **Step 1: Add examples**

Examples must compile with `dimod-cqm-v1` and have small deterministic scenario data.

- [x] **Step 2: Add examples to equivalence suite only when stable**

Graph examples were added under `examples/tutorials/` but intentionally not
added to the required equivalence suite to keep the suite fast and stable.

Do not add slow graph examples to the required suite until runtime is acceptable.

- [x] **Step 3: Run final gates**

Run:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
```

Expected: all pass.

- [x] **Step 4: Commit and push**

Commit and push are intentionally not performed by the agent unless explicitly
requested by the user.

```bash
git add README.md docs examples tests
git commit -m "Document graph unknown examples"
git push origin main
```

---

## Recommended Execution Order

1. Milestone 1: `Matching(G)`
2. Milestone 2: shared graph encoder utilities
3. Milestone 3: `MaximalMatching(G)`
4. Milestone 4: internal connectivity/forest encoders
5. Milestone 5: `SpanningTree(G)` and `Forest(G)`
6. Milestone 7: `SteinerTree(G, Terminals)`
7. Milestone 6: Hamiltonian path/cycle
8. Milestone 8: ordered objective manual scalarization
9. Milestone 9: backend diagnostics hardening
10. Milestone 10: examples/tutorials/final coherence

Reason for moving `SteinerTree` before Hamiltonian in execution: it reuses `StaticSubset(V)` and connectivity, while Hamiltonian needs a separate position-assignment encoding and can be developed independently later.

---

## Risk Register

- **Connectivity encodings can explode.** Mitigation: add estimate payloads and diagnostics before exposing multiple tree unknowns.
- **Backend-only graph semantics can blur stage boundaries.** Mitigation: keep graph validation in sema, graph data extraction in grounding/backend helper modules, and document that the v1 implementation is a backend encoder for stdlib-surfaced unknowns.
- **`Forest(G)` is harder than it looks.** Mitigation: do not expose it until acyclicity tests fail correctly on triangles.
- **Hamiltonian views need careful typing.** Mitigation: keep positions internal; document view behavior and reject unsupported position expressions clearly.
- **Manual objective scalarization config can become fragile.** Mitigation: prefer labels; require weights for every objective; reject unknown labels.

---

## Self-Review

- Spec coverage: objective scalarization, graph unknowns, `SteinerTree`, `MaximalMatching`, graph diagnostics, docs, tests, and mandatory gates are covered.
- Placeholder scan: no task relies on “TBD” or unspecified tests; each milestone has concrete files, commands, and expected behavior.
- Type consistency: graph edge views consistently use `.has_edge(u, v)`, Steiner adds `.has_vertex(v)`, Hamiltonian uses `.at(pos, v)` and `.uses(u, v)`.
- Vision coherence: the plan keeps user-facing modeling declarative, hides orientation/flow mechanics inside compiler/backend internals, and requires diagnostics instead of silent backend magic.
