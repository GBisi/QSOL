# QSOL Standard Library

The Standard Library (`stdlib`) provides a collection of useful unknowns, predicates, and functions to simplify modeling.

To use a module, import it with `use stdlib.<module_name>;`.

## 1. Boolean Logic (`stdlib.logic`)

Provides helper predicates for common logical operations and counting constraints.

```qsol
use stdlib.logic;
```

### Predicates

*   **`iff(a: Bool, b: Bool): Bool`**
    *   Returns true if `a` and `b` have the same truth value (Logical Equivalence).
    *   `iff(true, true)` is `true`.
    *   `iff(true, false)` is `false`.

*   **`xor(a: Bool, b: Bool): Bool`**
    *   Returns true if exactly one of `a` or `b` is true (Exclusive OR).

*   **`exactly(k: Real, terms: Comp(Real)): Bool`**
    *   Returns true if the sum of `terms` equals `k`.
    *   Commonly used with numeric comprehensions: `exactly(1, 1 for x in X where S.has(x))`.

*   **`atleast(k: Real, terms: Comp(Real)): Bool`**
    *   Returns true if the sum of `terms` is `>= k`.

*   **`atmost(k: Real, terms: Comp(Real)): Bool`**
    *   Returns true if the sum of `terms` is `<= k`.

*   **`between(lo: Real, hi: Real, terms: Comp(Real)): Bool`**
    *   Returns true if `lo <= sum(terms) <= hi`.

### Functions

*   **`indicator(b: Bool): Real`**
    *   Returns `1` if `b` is true, `0` otherwise.

## 2. Compiler Builtins

These names are handled by the compiler rather than loaded from `stdlib`:

*   **`abs(expr)`**
    *   Supported in `minimize abs(expr)` and `must abs(expr) <= C`.
*   **`max(term for ...)`**
    *   Supported in `minimize max(term for ...)`.
*   **`min(term for ...)`**
    *   Supported in `maximize min(term for ...)`.
*   **`all_different(term for x in S)`**
    *   Rewritten to pairwise disequality constraints over the comprehension domain.
    *   The first pass supports one finite set binder, for example `all_different(Slot[i] for i in Items)`.

They lower to generated scalar `Int` auxiliaries and hard constraints when finite
bounds are available. `all_different` lowers to ordinary quantified constraints.
These are not user-defined macros and do not require a
`use stdlib...` import.

## 3. Mappings & Permutations

These modules provide specialized unknown types for mapping problems.

### `stdlib.injective_mapping`

```qsol
use stdlib.injective_mapping;
find F : InjectiveMapping(Domain, Codomain);
```

*   **`InjectiveMapping(A, B)`**: An unknown mapping from `A` to `B` where each element of `B` is mapped to by *at most one* element of `A`.
*   **View**: `is(a: Elem(A), b: Elem(B))`

### `stdlib.surjective_mapping`

```qsol
use stdlib.surjective_mapping;
find F : SurjectiveMapping(Domain, Codomain);
```

*   **`SurjectiveMapping(A, B)`**: An unknown mapping from `A` to `B` where each element of `B` is mapped to by *at least one* element of `A`.
*   **View**: `is(a: Elem(A), b: Elem(B))`

### `stdlib.bijective_mapping`

```qsol
use stdlib.bijective_mapping;
find F : BijectiveMapping(Domain, Codomain);
```

*   **`BijectiveMapping(A, B)`**: An unknown mapping from `A` to `B` that is both injective and surjective (one-to-one correspondence).
*   **View**: `is(a: Elem(A), b: Elem(B))`

### `stdlib.permutation`

```qsol
use stdlib.permutation;
find P : Permutation(Items);
```

*   **`Permutation(A)`**: A bijection from set `A` to itself. Useful for ordering or reordering problems.
*   **View**: `is(from: Elem(A), to: Elem(A))`

### `stdlib.route`

```qsol
use stdlib.route;
find Tour : Route(Positions, Cities);
```

*   **`Route(Positions, V)`**: A route/order helper backed by `BijectiveMapping(Positions, V)`.
*   **Views**:
    *   `at(p: Elem(Positions), v: Elem(V))`
    *   `transition(p: Elem(Positions), q: Elem(Positions), u: Elem(V), v: Elem(V))`
*   **Successor predicates**:
    *   `linear_successor(p: Real, q: Real): Bool` is true when `q == p + 1`.
    *   `cyclic_successor(p: Real, q: Real, n: Real): Bool` is true when `q == p + 1`, or when `p == n` and `q == 1`.

`transition(...)` is the conjunction of two route-position decisions. It is
quadratic when used directly; keep numeric expressions backend-safe. Successor
predicates are static numeric helpers intended for route aggregates such as
transition-cost objectives.

## 4. Graph Structures And Helpers (`stdlib.graph`)

```qsol
use stdlib.graph;
set V;
relation Edge(u: V, v: V);
structure G = UndirectedGraph(V, Edge);
```

The graph module exposes compiler-owned static graph structures:

*   **`UndirectedGraph(V, Edge)`** expects a set and a binary relation over
    `V x V`. It rejects loops, canonicalizes unordered edge pairs in
    `G.edges`, and exposes `G.vertices`, `G.edges`, `G.non_edges`,
    `G.adjacent(u, v)`, and `G.nonedge(u, v)`.
*   **`DirectedGraph(V, Arc)`** expects a set and a binary relation over
    `V x V`. It rejects loops and exposes `D.vertices`, `D.arcs`,
    `D.non_arcs`, `D.adjacent(u, v)`, and `D.nonedge(u, v)`.

Structure declarations create no solver variables or backend constraints by
themselves. Their domains are static and can be used in tuple binders, scalar
find indexing, and `size(...)`:

```qsol
find Selected[G.edges] : Bool;
param Cost[G.edges] : Real;
must forall (u, v) in G.non_edges: not (Chosen.has(u) and Chosen.has(v));
minimize sum(if Selected[u, v] then Cost[u, v] else 0 for (u, v) in G.edges);
```

Relation-indexed graph params use the canonical tuple order exposed by the
graph domain. Scenario TOML supplies `Cost[G.edges]` with comma-joined tuple
keys such as `"a,b" = 2`; for `UndirectedGraph`, those keys match the canonical
orientation in `G.edges`.

The graph module also exposes stdlib-surfaced graph unknowns whose encodings are
compiler-owned:

```qsol
find M : Matching(G);
minimize count((u, v) in G.edges where M.has_edge(u, v));
find C : HamiltonianCycle(G);
minimize count((u, v) in G.edges where C.uses(u, v));
find A : DirectedAcyclicSubgraph(D);
maximize count((u, v) in D.arcs where A.has_arc(u, v));
```

*   **`Matching(G)`** expects an `UndirectedGraph` structure. It selects a set
    of edges such that each vertex is incident to at most one selected edge.
*   **View**: `has_edge(u: Elem(V), v: Elem(V))`.
*   **`MaximalMatching(G)`** has the same view and also enforces maximality:
    for every edge in `G.edges`, the edge is selected or at least one endpoint
    is already incident to a selected edge.
*   **`SpanningTree(G)`** has the same view and selects edges forming one
    connected tree over all vertices in `G.vertices`.
*   **`Forest(G)`** has the same view and selects an acyclic subset of
    `G.edges`.
*   **`SteinerTree(G, Terminals)`** expects an `UndirectedGraph` and a
    `StaticSubset` whose parent set is the graph vertex set. It exposes
    `has_edge(u, v)` and `has_vertex(v)`, selects all terminals, and connects
    selected vertices as a tree.
*   **`HamiltonianPath(G)`** expects an `UndirectedGraph` structure. It orders
    every vertex exactly once and requires consecutive positions to be adjacent.
*   **Views**: `at(pos: Real, v: Elem(V))` and
    `uses(u: Elem(V), v: Elem(V))`. Positions are internal numeric positions
    `1..size(G.vertices)`; users do not declare a positions set.
*   **`HamiltonianCycle(G)`** has the same views and also requires the last
    and first positions to be adjacent.
*   **`DirectedAcyclicSubgraph(D)`** expects a `DirectedGraph` structure. It
    selects a subset of `D.arcs` that admits a topological order.
*   **View**: `has_arc(u: Elem(V), v: Elem(V))`.

For `dimod-cqm-v1`, `Matching(G)` creates one binary variable per grounded edge
in `G.edges`. The backend adds incident-edge `<= 1` constraints only for
vertices with two or more incident grounded edges, so degree-0 and degree-1
vertices do not create redundant constraints. Objectives decide whether the
matching should be minimum, maximum, weighted, or used as a feasibility
component.

`MaximalMatching(G)` reuses the same edge variables and degree constraints, then
adds one maximality constraint per grounded edge. It does not impose a minimum
or maximum cardinality objective by itself.

`SpanningTree(G)` creates one edge variable per grounded edge, constrains the
selected edge count to `size(G.vertices) - 1`, and adds internal rooted-flow
connectivity constraints. `Forest(G)` creates one edge variable per grounded
edge and adds internal acyclicity constraints. Both keep objective choices
outside the unknown.

`HamiltonianPath(G)` creates internal assignment variables `P.at[pos,vertex]`
for every numeric position and grounded vertex. It constrains each position to
contain exactly one vertex, each vertex to appear exactly once, and forbids
non-adjacent consecutive vertex pairs. `HamiltonianCycle(G)` adds the same
encoding plus wraparound non-adjacency constraints between the final and first
positions. `uses(u, v)` is an edge-use view linked to adjacent position pairs.

`SteinerTree(G, Terminals)` creates one vertex variable per grounded vertex and
one edge variable per grounded edge. It requires nonempty terminals, selects
every terminal vertex, gates selected edges by selected endpoints, routes
internal connectivity flow from one terminal root, and enforces
`sum(selected_edges) == sum(selected_vertices) - 1`.

`DirectedAcyclicSubgraph(D)` creates one selected-arc binary variable per
grounded arc in `D.arcs` and one internal integer rank variable per vertex. For
every selected arc `(u, v)`, the backend enforces `rank[u] + 1 <= rank[v]`;
unselected arcs relax that order constraint. This provides a compact feedback
edge/arc modeling primitive while keeping objective choice in source.

The graph module also keeps the older compiler-owned relation helpers:

*   **`adjacent(Edge, u, v)`** lowers to `Edge(u, v) or Edge(v, u)`.
*   **`nonedge(Edge, u, v)`** lowers to `not Edge(u, v) and not Edge(v, u)`.

These helpers expect a binary static relation as their first argument. They are
source-level conveniences; relation values are still grounded before backend
compilation.
