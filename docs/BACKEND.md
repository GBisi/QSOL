# QSOL Backend Reference: `dimod-cqm-v1`

The `dimod-cqm-v1` backend translates QSOL models into Constrained Quadratic Models (CQMs) compatible with D-Wave's `dimod` library.

## 1. Supported Features

This backend supports:
*   **Problem Types**: Optimization and Satisfaction.
*   **Variables**: Binary variables generated from higher-level `Subset`, `Mapping`, and supported graph unknowns, scalar `Bool` decisions, and bounded scalar/indexed `Int` decisions.
*   **Constraints**: Linear and Quadratic equality/inequality constraints.
*   **Objectives**: One linear or quadratic objective statement, or multiple
    objectives with explicit manual scalarization weights.
*   **Static relations**: Base relation values are loaded from scenario data and derived relations are evaluated before backend compilation. Tuple iteration expands over grounded relation rows, and relation membership calls evaluate as constants for the grounded tuple values.
*   **Static subsets**: `StaticSubset(S)` params are validated against their parent set and materialized as grounded static domains. They create no backend variables.
*   **Static graph structures**: `UndirectedGraph` and `DirectedGraph` are resolved before backend compilation. Their derived domains are ordinary grounded static relations from the backend's perspective.

## 2. Variable Mapping

The backend automatically flattens high-level QSOL unknowns into binary variables.

### `Subset(S)`
For a find `Find : Subset(S)`, where `S` contains elements `{e1, e2, ...}`, the backend generates one binary variable for each element:
*   `Find.has(e1)`
*   `Find.has(e2)`
...

If `Find.has(e1)` is 1, the element is in the subset. If 0, it is not.

### `Mapping(D -> C)`
For a find `Map : Mapping(D -> C)`, the backend generates binary variables for each pair `(d, c)` in `D x C`:
*   `Map.is(d, c)`

It also generates implicit "exactly one" constraints to ensure each element in `D` maps to exactly one element in `C`:
`sum(Map.is(d, c) for c in C) == 1` for each `d` in `D`.

### `Matching(G)` and `MaximalMatching(G)`

For a find `M : Matching(G)`, where `G` is an `UndirectedGraph`, the backend
generates one binary variable for each grounded edge in `G.edges`:

*   `M.has_edge(u, v)`

The backend also generates matching constraints. For every vertex with at least
two incident grounded edges, the incident selected-edge sum is constrained:

```text
sum(M.has_edge(u, v) for (u, v) incident to x) <= 1
```

Vertices with degree 0 or 1 do not need a backend constraint. The view
`M.has_edge(v, u)` resolves to the same binary variable as `M.has_edge(u, v)`
for the canonical undirected edge stored in `G.edges`.

The graph encoder reports `Matching(G)` in model estimates as the number of
edge variables and the number of non-redundant degree constraints.

`MaximalMatching(G)` uses the same edge variables and matching degree
constraints. It also adds one maximality constraint per grounded edge:

```text
sum(M.has_edge(e) for e incident to u or v) >= 1
```

for every `(u, v)` in `G.edges`. This means no unselected edge can be added
without touching an already selected edge.

### `SpanningTree(G)` and `Forest(G)`

`SpanningTree(G)` and `Forest(G)` use one binary variable per grounded edge in
`G.edges`, with the same `T.has_edge(u, v)` view shape.

`SpanningTree(G)` adds:

* `sum(T.has_edge(e) for e in G.edges) == size(G.vertices) - 1`;
* rooted connectivity constraints using internal integer flow variables over
  both orientations of each grounded edge.

`Forest(G)` adds internal subset edge-count constraints:

```text
selected_edges_inside(S) <= |S| - 1
```

for vertex subsets that have enough induced edges to form a cycle. This
encoding is exact but can be large on dense graphs; it is an internal backend
encoding, not public cycle-domain syntax.

Internal graph encoders also provide reusable building blocks for later graph
unknowns:

* rooted connectivity uses internal integer flow variables over both
  orientations of each grounded undirected edge, with capacity gated by selected
  edge variables;
* forest acyclicity uses subset edge-count constraints of the form
  `selected_edges_inside(S) <= |S| - 1`.

These encoders are compiler/backend internals. They do not add public graph
orientation syntax or a user-facing all-cycles domain.

### `SteinerTree(G, Terminals)`

`SteinerTree(G, Terminals)` requires `Terminals` to be a nonempty grounded
`StaticSubset` of `G.vertices`. The backend creates binary variables for both
selected vertices and selected edges:

```text
T.has_vertex(v) in {0,1}
T.has_edge(u,v) in {0,1}
```

Every terminal is forced selected. Selected edges imply both endpoint vertices
are selected. Internal integer flow variables route connectivity from one
terminal root to each selected non-root vertex, and the tree count constraint
`sum(selected_edges) == sum(selected_vertices) - 1` removes connected cycles.

### `HamiltonianPath(G)` and `HamiltonianCycle(G)`

`HamiltonianPath(G)` and `HamiltonianCycle(G)` use internal assignment
variables for every grounded vertex and numeric position:

```text
P.at[p,v] in {0,1}
```

The backend adds two families of assignment constraints:

* each position contains exactly one vertex;
* each vertex appears in exactly one position.

For every non-edge `(u, v)` and each consecutive position pair, the backend
forbids selecting `u` immediately followed by `v`:

```text
P.at[p,u] + P.at[p+1,v] <= 1
```

Because `G` is undirected, both orientations are forbidden when the unordered
pair is absent from `G.edges`. `HamiltonianCycle(G)` also adds the same
non-adjacency constraints between the final and first positions.

The public views are `P.at(pos, v)` and `P.uses(u, v)`. Positions are internal
numeric positions `1..size(G.vertices)` and do not require a user-declared set.
`uses(u, v)` is linked to adjacent-position transitions for the corresponding
grounded edge. The encoding is deliberately direct and inspectable: it uses
O(n^2) assignment variables and O(n^3) forbidden-pair constraints in the dense
worst case.

### Scalar Decisions

```qsol
find enabled : Bool;
find T : Int[0 .. 10];
find Load[Machines] : Int[0 .. Capacity];
find Flow[Arc] : Int[0 .. size(Arc)];
find Makespan : Int[0 .. sum(Length[j] for j in Jobs)];
```

The backend keeps CQM as the canonical model:

* `Bool` scalar decisions become native `dimod.Binary` variables.
* `Int[lo .. hi]` scalar decisions become native `dimod.Integer` variables with the grounded bounds.
* Indexed scalar decisions create one native CQM variable per grounded index tuple, for example `Load[m1]`.
* Relation-indexed scalar decisions create one native CQM variable per grounded relation tuple, for example `Flow[a,b]`.
* Structure-domain-indexed scalar decisions create one native CQM variable per grounded structure-domain tuple, for example `Selected[a,b]` for `find Selected[G.edges] : Bool`.
* Compiler-lowered piecewise builtins create generated scalar `Int` auxiliaries named like `__qsol_piecewise_abs_0` or `__qsol_piecewise_max_0`.
* Compiler-owned global helpers are expanded before backend compilation. For example, `all_different(Slot[i] for i in Items)` becomes pairwise disequality constraints.

The exported BQM is derived from the CQM for runtimes and export formats that require binary quadratic form.

## 3. Constraint Translation

QSOL constraints are translated into mathematical inequalities.

### Comparisons
*   `lhs <= rhs` -> `lhs - rhs <= 0`
*   `lhs >= rhs` -> `lhs - rhs >= 0`
*   `lhs == rhs` -> `lhs - rhs == 0`
*   `lhs != rhs` -> **Supported via aux variables**: `z == 1` if `lhs != rhs`, `z == 0` otherwise.

### Logical Operators
Boolean logic is converted to arithmetic constraints on binary selection variables (0 or 1).
*   `A and B` -> `A * B` (if linear/quadratic) or via auxiliary variable `Z <= A`, `Z <= B`, `Z >= A + B - 1`.
*   `A or B` -> `A + B - A*B` or via auxiliary variable `Z >= A`, `Z >= B`, `Z <= A + B`.
*   `not A` -> `1 - A`
*   `A implies B` -> `A <= B`
*   Static relation guards are evaluated during grounded emission when all operands are scenario values.

## 4. Objectives and Soft Constraints

*   `minimize expr` adds `expr` to the CQM objective.
*   `maximize expr` adds `-expr` to the CQM objective.
*   `minimize expr as label` and `maximize expr as label` preserve label metadata for diagnostics.
*   Multiple objective statements are rejected with `QSOL3201` by default. With `qubo_policy = "manual"`, each objective label (or `objective_N` fallback) must have an explicit scalarization weight. `qubo_policy = "auto"` is reserved and reports `QSOL3202`.
*   `should expr` adds a penalty to the objective if `expr` is violated (weight 10.0).
*   `nice expr` adds a smaller penalty (weight 1.0).

Piecewise numeric builtins are lowered before backend code generation in these
contexts:

* `minimize abs(e)` introduces `z >= e`, `z >= -e`, then minimizes `z`.
* `must abs(e) <= C` lowers to `e <= C` and `-e <= C`.
* `minimize max(term for ...)` introduces `T >= term` for every grounded binder row, then minimizes `T`.
* `maximize min(term for ...)` introduces `Z <= term` for every grounded binder row, then maximizes `Z`.

Generated auxiliaries are visible in lowered/ground IR and estimator output.

## 5. Limitations

*   **Higher-Order Logic**: Complex nested quantifiers or non-linear expressions that cannot be reduced to quadratic forms may be unsupported or require significant auxiliary variables.
*   **Continuous Variables**: Native continuous variables are not currently supported.
*   **Integer Bounds**: `Int` decision bounds must ground to finite integers before backend compilation. Bounds may include static params, `size(Set)`, `size(Relation)`, static `sum`/`count`, static `if` expressions, relation membership over static values, and arithmetic. Decision-dependent bounds are rejected before backend compilation.
*   **Piecewise Contexts**: Unsupported piecewise contexts are rejected with `QSOL3101`, including `maximize abs(...)`, `minimize min(...)`, `maximize max(...)`, `abs(...) >= C`, and forms without finite auxiliary bounds.

> For a complete list of unsupported patterns and workarounds, see [Backend V1 Limits](BACKEND_V1_LIMITS.md).
