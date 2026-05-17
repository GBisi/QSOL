# QSOL Syntax Guide

This is a practical syntax-focused guide for writing valid `.qsol` files with the current compiler.

For full semantics and backend caveats, see `QSOL_reference.md`.

## 1. File Basics

- File extension: `.qsol`
- Statement terminator: `;` (required)
- Newlines/indentation: not semantically meaningful
- Comments:

```qsol
// line comment
/* block comment */
```

## 2. Top-Level Constructs

A file may contain top-level `use`, `unknown`, `predicate`, `function`, and `problem` blocks.

Module-style imports:

```qsol
use stdlib.permutation;
use stdlib.logic;
use mylib.graph.unknowns;
```

Import rules:
- `stdlib.*` is a reserved namespace for packaged stdlib modules.
- Non-stdlib modules resolve from importer directory, then process CWD.
- Dotted module path `a.b.c` maps to `a/b/c.qsol`.
- Quoted imports like `use "x.qsol";` are not supported.

```qsol
problem Demo {
  set A;
  find S : Subset(A);
  must true;
  minimize 0;
}
```

```qsol
unknown U(A) {
  rep {
    inner : Subset(A);
  }
  laws {
    must true;
  }
  view {
    predicate has(x: Elem(A)): Bool = inner.has(x);
    function indicator(x: Elem(A)): Real = if inner.has(x) then 1 else 0;
  }
}
```

Top-level reusable macros use the same typed declaration syntax:

```qsol
predicate iff(a: Bool, b: Bool): Bool = a and b or not a and not b;
function indicator(b: Bool): Real = if b then 1 else 0;
```

The return type annotation (`: Bool` / `: Real`) is optional since it is implied by the keyword:

```qsol
predicate iff(a: Bool, b: Bool) = a and b or not a and not b;
function indicator(b: Bool) = if b then 1 else 0;
```

## 3. Declarations Inside `problem`

### 3.1 Sets

```qsol
set Workers;
set Tasks;
set Positions = Range(1, size(Workers));
```

`Range(lo, hi)` defines a derived integer set. It is inclusive, has no `step`
argument, and is evaluated during grounding after scenario sets and scalar params
are available. Scenario data must not supply values for derived sets.

### 3.2 Params

```qsol
param K : Int[1 .. 10] = 3;
param Cost[Workers,Tasks] : Real;
param Allowed[Workers,Tasks] : Bool = true;
param StartNode[Tasks] : Elem(Workers);
param Terminals : StaticSubset(Workers);
```

Usage notes:
- Indexed params can be referenced as `Cost[w, t]`.
- Indexed params must use brackets; `Cost(w, t)` is rejected with `QSOL2101`.
- `Elem(SetName)` params return set elements and can be passed to methods like `Subset.has(...)`.
- `Elem(SetName)` params do not allow defaults.
- `StaticSubset(SetName)` params are scenario-supplied arrays of unique parent-set members.
- Static subset params can be used as domains (`forall t in Terminals`), with `size(Terminals)`, and with `Terminals.has(x)`.
- Scalar params must be referenced as bare names (for example `C`, `Flag`, `Start`).
- Scalar call/index forms such as `C[]` and `Flag()` are rejected with `QSOL2101`.

### 3.3 Relations

```qsol
relation Edge(u: Nodes, v: Nodes);
relation Contains(set: Sets, element: Items);
relation NonEdge(u: Nodes, v: Nodes) =
  pairs(u in Nodes, v in Nodes where u != v and not Edge(u, v));
```

Relations are finite, static data. Fields must reference declared sets. Use
relation membership calls as boolean expressions:

```qsol
Edge(u, v)
not Edge(v, u)
```

Tuple binders destructure relation rows:

```qsol
forall (u, v) in Edge: Edge(u, v)
count((u, v) in Edge where Edge(v, u))
all(Edge(u, v) for (u, v) in Edge)
```

Scenario TOML supplies relation data under `scenarios.<name>.relations`.

```toml
[scenarios.triangle.relations]
Edge = [
  { u = "a", v = "b" },
  { u = "b", v = "c" },
]
```

Compact tuple arrays are also accepted: `Edge = [["a", "b"], ["b", "c"]]`.
Scenario data supplies only base relations. Derived relations are evaluated at
grounding time and must not appear under `scenarios.<name>.relations`.

Derived relation constructors:

```qsol
pairs(u in Nodes, v in Nodes)
pairs(u in Nodes, v in Nodes where u != v)
filter((u, v) in Edge where Edge(v, u))
```

Derived `where` conditions must be scenario-time static. They may use binders,
params, relation membership calls, arithmetic, and comparisons, but not `find`
decisions or unknown view methods such as `Pick.has(u)`.
Record binders (`for e in Edge`, `e.u`) are not supported yet.

### 3.4 Static Structures

```qsol
use stdlib.graph;

set V;
relation Edge(u: V, v: V);
structure G = UndirectedGraph(V, Edge);
structure D = DirectedGraph(V, Arc);
```

`structure Name = Constructor(args);` creates a static compiler-owned wrapper.
The first builtins are graph structures:

- `UndirectedGraph(V, Edge)` requires a binary relation over `V x V`, rejects
  loops, and exposes `G.vertices`, `G.edges`, `G.non_edges`,
  `G.adjacent(u, v)`, and `G.nonedge(u, v)`.
- `DirectedGraph(V, Arc)` requires a binary relation over `V x V`, rejects
  loops, and exposes `D.vertices`, `D.arcs`, `D.non_arcs`,
  `D.adjacent(u, v)`, and `D.nonedge(u, v)`.

Dotted static domains can be used where static domains are accepted:

```qsol
find Selected[G.edges] : Bool;
forall (u, v) in G.non_edges: G.nonedge(u, v)
count((u, v) in G.edges where G.adjacent(u, v))
size(G.edges)
```

Structures create no solver variables or backend constraints by themselves.

### 3.5 Finds

```qsol
find Pick : Subset(Workers);
find Assign : Mapping(Workers -> Tasks);
find M : Matching(G); // from `use stdlib.graph;`
find MM : MaximalMatching(G); // from `use stdlib.graph;`
find Perm : Permutation(Workers); // from `use stdlib.permutation;`
find Enabled : Bool;
find Makespan : Int[0 .. 100];
find Load[Workers] : Int[0 .. size(Tasks)];
find Flow[Arc] : Int[0 .. size(Arc)];
find TotalLength : Int[0 .. sum(Length[j] for j in Jobs)];
```

`find` supports primitive unknowns (`Subset`, `Mapping`), stdlib-surfaced
compiler-known unknowns such as `Matching(G)`, and user-defined unknowns. Custom
unknown finds are elaborated in frontend into primitive finds plus generated
constraints.

Scalar decisions are also valid:
- `Bool` creates a binary scalar decision usable in boolean expressions.
- `Int[lo .. hi]` creates a native bounded integer CQM variable usable in numeric expressions.
- Indexed scalar decisions use bracket access, for example `Load[w]`.
- Relation-indexed scalar decisions create one decision per relation tuple and use one bracket argument per relation field, for example `Flow[u, v]` inside `for (u, v) in Arc`.
- Structure-domain-indexed scalar decisions work the same way, for example
  `Selected[u, v]` inside `for (u, v) in G.edges`.
- `Matching(G)` expects an `UndirectedGraph` and exposes
  `M.has_edge(u, v)`. It selects edges so no vertex is incident to more than
  one selected edge.
- `MaximalMatching(G)` has the same `has_edge` view and also ensures no
  additional graph edge can be added without violating the matching property.

`Int` bounds must be scenario-time integer constants. They may use literals,
numeric params, indexed params over static binders, `size(Set)`,
`size(Relation)`, static `sum`/`count`, static `if` expressions, relation
membership over static values, and arithmetic over those forms.
Decision-dependent bounds such as `sum(if Pick.has(j) then Weight[j] else 0 for j in Jobs)` are rejected.

### 3.6 Graph and Global Helpers

Compiler-owned helpers are rewritten before type checking:

```qsol
must all_different(Slot[i] for i in Items);
```

`all_different` currently supports one finite set binder and lowers to pairwise
disequality constraints. For graph relations, import the graph module:

```qsol
use stdlib.graph;

relation Edge(u: V, v: V);

minimize sum(if adjacent(Edge, u, v) then 1 else 0 for u in V for v in V);
```

`adjacent(Edge, u, v)` lowers to `Edge(u, v) or Edge(v, u)`.
`nonedge(Edge, u, v)` lowers to `not Edge(u, v) and not Edge(v, u)`.

## 4. Constraints and Objectives

### 4.1 Constraint keywords

```qsol
must expr;
should expr;
nice expr;
```

Optional guard form:

```qsol
must expr if cond;
```

### 4.2 Objectives

```qsol
minimize numeric_expr;
maximize numeric_expr;
minimize numeric_expr as label;
```

Objective labels are optional metadata and must be unique within a problem. They
do not create expression aliases. Multiple objective statements are ordered by
source order at the language level, but the current `dimod-cqm-v1` backend
rejects multiple objective statements instead of silently scalarizing them.

## 5. Expressions

### 5.1 Boolean expressions

```qsol
not a
(a and b)
(a or b)
(a => b)

x = y
x != y
x < y
x <= y
x > y
x >= y

if cond then bool_a else bool_b
```

Compare tolerance notes in boolean contexts (`if`, soft constraints, nested formulas) and hard `!=` constraints:
- fixed epsilon: `1e-6`
- `<` means `lhs - rhs <= -1e-6`
- `<=` means `lhs - rhs <= +1e-6`
- `>` means `lhs - rhs >= +1e-6`
- `>=` means `lhs - rhs >= -1e-6`
- `=` means `lhs - rhs` inside `[-1e-6, +1e-6]`
- `!=` means outside that band
- exactly-on-boundary cases are intentionally indeterminate

### 5.2 Numeric expressions

```qsol
1
-3
x + y
x - y
x * y
x / y
if cond then num_a else num_b
size(V)
abs(expr)
max(load[m] for m in Machines)
min(score[a] for a in Agents)
```

Piecewise builtins are compiler-owned numeric forms. The supported backend-safe
contexts are:

```qsol
minimize abs(balance)
must abs(balance) <= Limit
minimize max(load[m] for m in Machines)
maximize min(score[a] for a in Agents)
```

The first pass rejects unsupported contexts such as `maximize abs(...)`,
`minimize min(...)`, `maximize max(...)`, and `abs(...) >= C`.

### 5.3 Calls and member access

```qsol
S.has(x)
Assign.is(w, t)
exactly(1, S.has(x) for x in X)

Cost[w, t]
C
size(V)
Load[w]
```

Macro formal types:
- `Bool`
- `Real`
- `Elem(SetName)`
- `Comp(Bool)`
- `Comp(Real)`

Comprehension-style call arguments are written as:

```qsol
f(term for x in X where cond else alt)
```

`Comp(Real)` formals consume these as numeric aggregate inputs; `Comp(Bool)` formals consume them as boolean aggregate inputs.

## 6. Quantifiers

```qsol
forall x in X: expr
exists x in X: expr
```

Quantifier body is a boolean expression.

## 7. Aggregates and Comprehensions

### 7.1 Numeric

```qsol
sum(term for x in X)
sum(term for x in X where cond)
sum(term for x in X where cond else alt)

count(x for x in X)
count(x for x in X where cond)
count(x in X)
count(x in X where cond)
```

### 7.2 Boolean

```qsol
any(term for x in X)
any(term for x in X where cond)
any(term for x in X where cond else alt)

all(term for x in X)
all(term for x in X where cond)
all(term for x in X where cond else alt)
```

## 8. Minimal Complete Example

```qsol
use stdlib.logic;

problem ExactKSubset {
  set Items;
  set Positions = Range(1, size(Items));

  find Pick : Subset(Items);
  find Count : Int[0 .. size(Items)];

  must Count = sum(if Pick.has(i) then 1 else 0 for i in Items);
  must Count = 2;
  minimize sum(if Pick.has(i) then 1 else 0 for i in Items);
}
```

## 9. Common Syntax Errors

### 9.1 Missing semicolon

Invalid:

```qsol
set A
find S : Subset(A);
```

Valid:

```qsol
set A;
find S : Subset(A);
```

### 9.2 Trailing `for` after guarded constraint

Invalid:

```qsol
must S.has(x) if true for x in A;
```

Valid equivalent:

```qsol
must forall x in A: (true => S.has(x));
```

### 9.3 Wrong method arity

- `Subset.has` expects one argument.
- `Mapping.is` expects two arguments.

### 9.4 Legacy macro formal syntax

Invalid:

```qsol
predicate has(x in A): Bool = true;
```

Valid:

```qsol
predicate has(x: Elem(A)): Bool = true;
```

## 10. Grammar Source

The canonical grammar lives in:
- `src/qsol/parse/grammar.lark`

When in doubt, validate with:

```bash
uv run qsol inspect parse path/to/model.qsol --json
```
