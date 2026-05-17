# QSOL Language Reference

This reference describes the current QSOL language, standard library, CLI
workflow, configuration format, backend limits, and extension points. It is the
complete semantic reference for users. For a compact syntax cheat sheet, see
[docs/QSOL_SYNTAX.md](docs/QSOL_SYNTAX.md). For command examples and output
schemas, see [docs/CLI.md](docs/CLI.md).

## 1. What QSOL Is

QSOL is a declarative language for finite combinatorial optimization models.
A model states:

- which finite domains exist;
- which data values are provided by an instance;
- which decisions are unknown;
- which constraints must hold;
- which numeric objective should be minimized or maximized.

QSOL is not an imperative solver scripting language. Users describe model
semantics; the compiler resolves names, checks types, expands abstractions,
grounds finite data, validates backend support, and writes inspectable
artifacts.

The current built-in backend is `dimod-cqm-v1`. It targets D-Wave `dimod`
Constrained Quadratic Models (CQM), writes a converted Binary Quadratic Model
(BQM) view, and supports the `local-dimod` and `qiskit` runtimes.

## 2. File and Program Structure

A QSOL source file is a sequence of top-level items:

```qsol
use stdlib.logic;

predicate helper(x: Bool): Bool = not x;

unknown MyUnknown(S) {
  rep {
    inner : Subset(S);
  }
  laws {
    must count(x in S where inner.has(x)) >= 1;
  }
  view {
    predicate has(x: Elem(S)): Bool = inner.has(x);
  }
}

problem Demo {
  set Items;
  param Weight[Items] : Real = 1;
  find Pick : MyUnknown(Items);
  must forall i in Items: Weight[i] >= 0;
  maximize sum(Weight[i] for i in Items where Pick.has(i));
}
```

Top-level item kinds:

| Item | Purpose |
| --- | --- |
| `use module.path;` | Imports reusable unknowns, predicates, and functions. |
| `predicate name(...): Bool = expr;` | Defines a reusable boolean macro. |
| `function name(...): Real = expr;` | Defines a reusable numeric macro. |
| `unknown Name(...) { ... }` | Defines a reusable decision abstraction. |
| `problem Name { ... }` | Defines an optimization problem. |

Imported modules may contain only `use`, `unknown`, `predicate`, and
`function` top-level items. They may not contain `problem` blocks.

Statements are terminated with semicolons. Newlines and indentation are not
semantic. Single-line comments use `//`; block comments use `/* ... */`.

## 3. Imports and Module Resolution

Use statements map dotted module names to `.qsol` files:

```qsol
use stdlib.logic;
use mylib.graph_helpers;
```

Resolution rules:

1. `stdlib.<name>` resolves inside QSOL's installed standard library.
2. Non-stdlib imports resolve relative to the importing file.
3. If not found there, non-stdlib imports resolve relative to the process
   current working directory.

For example, `use mylib.graph_helpers;` resolves to
`mylib/graph_helpers.qsol`.

## 4. Problem Declarations

Problem statements may appear in any order, subject to normal name resolution:

```qsol
problem Assignment {
  set Workers;
  set Tasks;

  relation Qualified(worker: Workers, task: Tasks);

  param Cost[Workers, Tasks] : Real = 0;
  param Leader : Elem(Workers);

  find Assign : Mapping(Tasks -> Workers);
  find Active[Workers] : Bool;
  find Load[Workers] : Int[0 .. size(Tasks)];

  must forall t in Tasks: Qualified(AssignTarget, t);
  minimize sum(Cost[w, t] for w in Workers for t in Tasks where Assign.is(t, w));
}
```

The major declaration forms are:

| Form | Meaning |
| --- | --- |
| `set S;` | A base finite set supplied by TOML scenario data. |
| `set S = Range(lo, hi);` | A derived inclusive integer set computed at grounding time. |
| `relation R(a: A, b: B);` | A base static relation supplied by TOML scenario data. |
| `relation R(...) = pairs(...);` | A derived static relation from a finite product. |
| `relation R(...) = filter(...);` | A derived static relation by filtering another relation. |
| `structure G = UndirectedGraph(V, Edge);` | A compiler-owned static structure. |
| `param P : T;` | A scalar scenario parameter. |
| `param P[I, J] : T = default;` | An indexed scenario parameter with optional scalar default. |
| `param S : StaticSubset(V);` | A scenario-supplied subset that also acts as a static domain. |
| `find X : T;` | A scalar or structured decision. |
| `find X[I] : T;` | An indexed scalar decision over a static domain. |
| `must expr;` | A hard constraint. |
| `should expr;` | A soft constraint in language surface; backend support is currently narrow. |
| `nice expr;` | A weaker soft preference in language surface; backend support is currently narrow. |
| `minimize expr;` | Numeric minimization objective. |
| `maximize expr;` | Numeric maximization objective. |
| `minimize expr as label;` | Labeled objective metadata. |

Only backend-supported constructs can be built or solved. Frontend-valid QSOL
can still be rejected by `targets check` if the selected backend cannot encode
the grounded shape.

## 5. Primitive Domains

### 5.1 Sets

Base sets are finite and supplied by scenario TOML:

```qsol
set Items;
```

```toml
[scenarios.baseline.sets]
Items = ["a", "b", "c"]
```

Derived range sets are inclusive integer domains:

```qsol
set Positions = Range(1, size(Items));
```

`Range(lo, hi)` bounds must be scenario-time static. They may use static
parameters, static aggregate expressions, `size(...)`, arithmetic, and static
conditionals. They may not depend on decisions.

### 5.2 Relations

Base relations are finite tuple domains:

```qsol
relation Edge(u: V, v: V);
```

```toml
[scenarios.baseline.relations]
Edge = [
  { u = "a", v = "b" },
  { u = "b", v = "c" },
]
```

Membership is tested with a call:

```qsol
Edge(u, v)
not Edge(u, v)
```

Relation tuple binders destructure relation rows:

```qsol
forall (u, v) in Edge: Edge(v, u);
count((u, v) in Edge where Edge(v, u));
```

Derived relations use `pairs(...)` and `filter(...)`:

```qsol
relation NonEdge(u: V, v: V) =
  pairs(u in V, v in V where u != v and not Edge(u, v));

relation SymmetricEdge(u: V, v: V) =
  filter((u, v) in Edge where Edge(v, u));
```

Derived relation predicates must be scenario-time static. They can use static
binders, sets, params, base relations, earlier derived relations, and static
structure methods.

### 5.3 Structures

Structures are compiler-owned static views over sets and relations:

```qsol
use stdlib.graph;

problem IndependentSet {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);

  find Pick : Subset(V);

  must forall (u, v) in G.edges: not (Pick.has(u) and Pick.has(v));
  maximize count(v in V where Pick.has(v));
}
```

Built-in graph structures:

| Structure | Static domains | Methods |
| --- | --- | --- |
| `UndirectedGraph(V, Edge)` | `G.vertices`, `G.edges`, `G.non_edges` | `G.adjacent(u, v)`, `G.nonedge(u, v)` |
| `DirectedGraph(V, Arc)` | `D.vertices`, `D.arcs`, `D.non_arcs` | `D.arc(u, v)`, `D.nonarc(u, v)` |

Structures do not create decisions or backend variables. They materialize static
domains and lower methods to static relation membership checks.

## 6. Types and Values

QSOL has scalar, element, comprehension, and decision-abstraction types.

| Type | Meaning | Example |
| --- | --- | --- |
| `Bool` | Boolean value | `true`, `false`, `Pick.has(i)` |
| `Real` | Numeric value | `3`, `2.5`, `Weight[i]` |
| `Int[lo .. hi]` | Bounded integer scalar | `Int[0 .. size(Items)]` |
| `Elem(S)` | Element of set `S` | `Elem(Items)` |
| `Comp(Bool)` | Boolean comprehension argument | `Pick.has(i) for i in Items` |
| `Comp(Real)` | Numeric comprehension argument | `Weight[i] for i in Items` |
| `Subset(S)` | Unknown subset of `S` | `find Pick : Subset(Items);` |
| `Mapping(A -> B)` | Unknown total mapping from `A` to `B` | `find Assign : Mapping(Tasks -> Workers);` |
| `Matching(G)` | Unknown matching over an undirected graph | `find M : Matching(G);` |
| User unknown | Custom abstraction from `unknown` | `find Tour : Permutation(Cities);` |

Numeric literals are typed as `Real`. Integer decision bounds use numeric
expressions but must ground to integer values.

String literals are currently data literals in parsed syntax, but scenario set
members are normally supplied through TOML rather than QSOL string expressions.

## 7. Parameters

Scalar parameters:

```qsol
param Capacity : Int[0 .. 100];
param Penalty : Real = 10;
param Enabled : Bool = true;
param Start : Elem(Nodes);
```

Indexed parameters:

```qsol
param Weight[Items] : Real = 1;
param Cost[Workers, Tasks] : Real = 0;
param Next[Positions] : Elem(Positions);
```

Defaults are allowed for `Bool`, `Real`, and bounded `Int` parameters. Element
parameters (`Elem(S)`) and static subset parameters (`StaticSubset(S)`) do not
support defaults.

Static subset parameters:

```qsol
param Terminals : StaticSubset(Nodes);
```

`StaticSubset(S)` is scenario-time data, not a decision. TOML supplies it as an
array of members from the parent set:

```toml
[scenarios.baseline.params]
Terminals = ["a", "c"]
```

During grounding, the compiler validates that every member belongs to `S`,
rejects duplicates, stores the value as a parameter, and materializes a static
domain with the parameter name. Static subsets can be used in binders,
`size(...)`, and static membership checks:

```qsol
must forall t in Terminals: Pick.has(t);
minimize size(Terminals) + count(v in Nodes where Terminals.has(v));
```

TOML data for indexed params is normally an object keyed by the index values:

```toml
[scenarios.baseline.params]
Weight = { a = 3, b = 5, c = 8 }
Cost = { alice = { task1 = 2, task2 = 7 }, bob = { task1 = 4, task2 = 1 } }
```

## 8. Decisions and Unknowns

Primitive decision forms:

```qsol
find Pick : Subset(Items);
find Assign : Mapping(Tasks -> Workers);
find M : Matching(G);
find Enabled : Bool;
find Load[Machines] : Int[0 .. Capacity];
```

Semantics:

- `Subset(S)` exposes `Pick.has(x)`, a boolean decision for each `x in S`.
- `Mapping(A -> B)` exposes `Assign.is(a, b)`, with exactly one target `b` for
  each source `a`.
- `Matching(G)` expects `G` to be an `UndirectedGraph`. It exposes
  `M.has_edge(u, v)` and selects edges such that each vertex is incident to at
  most one selected edge. It is surfaced through `stdlib.graph` but implemented
  by compiler/backend graph encoders for efficient edge-indexed variables.
- Scalar `Bool` creates one binary decision.
- Scalar `Int[lo .. hi]` creates a bounded integer CQM decision. Indexed integer
  finds create one bounded integer decision per grounded index.

Custom unknowns wrap primitive or other user-defined unknowns:

```qsol
unknown NonemptySubset(S) {
  rep {
    inner : Subset(S);
  }
  laws {
    must count(x in S where inner.has(x)) >= 1;
  }
  view {
    predicate has(x: Elem(S)): Bool = inner.has(x);
  }
}
```

Representation fields in `rep` are private. Callers use only `view` predicates
and functions.

Current user unknown type arguments are names, not literals. For example, use a
parameter name:

```qsol
param K : Real = 3;
find Pick : ExactSubset(Items, K);
```

not:

```qsol
find Pick : ExactSubset(Items, 3); // invalid
```

## 9. Expressions

### 9.1 Boolean Expressions

Boolean operators:

```qsol
not a
a and b
a or b
a => b
a = b
a != b
```

`=` and `!=` support matching booleans, matching elements from the same set,
and numeric values. Numeric comparisons are `<`, `<=`, `>`, and `>=`.

### 9.2 Numeric Expressions

Numeric operators:

```qsol
a + b
a - b
a * b
a / b
-a
```

Multiplication is supported when the selected backend can encode the grounded
degree. The v1 backend is intentionally limited to linear/quadratic shapes.

### 9.3 Conditionals

Numeric conditional:

```qsol
if Pick.has(i) then Weight[i] else 0
```

Boolean conditional:

```qsol
if Enabled then RuleA else RuleB
```

The current backend supports numeric/objective conditionals in selected
contexts. Hard boolean if-then-else constraints are not generally supported by
`dimod-cqm-v1`; run `qsol targets check` before expecting a model to build.

### 9.4 Calls and Indexing

Parameters and indexed scalar decisions use bracket indexing:

```qsol
Weight[i]
Cost[w, t]
Load[m]
```

Relations and predicates use call syntax:

```qsol
Edge(u, v)
Qualified(w, t)
```

Unknown views and structure methods use dotted call syntax:

```qsol
Pick.has(i)
Assign.is(t, w)
G.adjacent(u, v)
```

## 10. Quantifiers, Aggregates, and Comprehensions

Quantifiers:

```qsol
forall x in S: expr
exists x in S: expr
forall (u, v) in Edge: expr
exists (u, v) in Edge: expr
```

Quantifiers do not support `where` or `else` clauses. Use `all(...)` or
`any(...)` for filtered quantified logic.

Aggregates:

```qsol
sum(term for x in S)
sum(term for x in S where cond)
sum(term for x in S where cond else fallback)

count(x in S)
count(x in S where cond)
count(term for x in S where cond)
count((u, v) in Edge where cond)

all(cond for x in S)
any(cond for x in S where filter)
```

Comprehensions can have multiple binders:

```qsol
sum(Cost[w, t] for w in Workers for t in Tasks where Assign.is(t, w))
```

`where` filters rows. For `sum`, an `else` value is used when the row fails the
filter. For `all` and `any`, `where`/`else` are folded into the boolean body
during desugaring.

## 11. Constraints and Objectives

Hard constraints:

```qsol
must forall i in Items: Weight[i] >= 0;
```

Guarded constraints:

```qsol
must Load[m] <= Capacity if MachineEnabled[m];
```

Objectives:

```qsol
minimize sum(Cost[w, t] for w in Workers for t in Tasks where Assign.is(t, w));
maximize count(i in Items where Pick.has(i));
minimize count(i in Items where not Pick.has(i)) as missing;
```

Objective labels use `as NAME`. Labels are metadata for diagnostics and future
target/runtime policy; they do not create expression names. Labels must be
unique within a problem.

Multiple objective statements express ordered objective intent in source order.
The current `dimod-cqm-v1` backend is single-objective and rejects multiple
objective statements with `QSOL3201` instead of silently summing them. To build
with this backend today, combine terms explicitly in one weighted objective
expression.

## 12. Compiler-Owned Helpers and Piecewise Forms

The compiler recognizes a small set of helper patterns:

```qsol
abs(expr)
max(term for x in S)
min(term for x in S)
all_different(term for x in S)
adjacent(Edge, u, v)
nonedge(Edge, u, v)
```

Supported v1 backend contexts include:

- `minimize abs(e)`
- `must abs(e) <= C`
- `minimize max(term for ...)`
- `maximize min(term for ...)`
- `all_different(term for x in S)` with one finite set binder

Unsupported contexts include `maximize abs(...)`, `minimize min(...)`,
`maximize max(...)`, `abs(...) >= C`, non-affine expressions that exceed
backend degree limits, and forms where finite auxiliary bounds cannot be
derived.

See [docs/BACKEND_V1_LIMITS.md](docs/BACKEND_V1_LIMITS.md).

## 13. Standard Library

Import standard library modules with `use stdlib.<module>;`.

### 13.1 `stdlib.logic`

Definitions:

| Name | Type | Meaning |
| --- | --- | --- |
| `count(p)` | `function count(p: Comp(Bool)): Real` | Counts true rows in a boolean comprehension. |
| `any(p)` | `predicate any(p: Comp(Bool)): Bool` | True when at least one row is true. |
| `all(p)` | `predicate all(p: Comp(Bool)): Bool` | True when all rows are true. |
| `indicator(cond)` | `function indicator(cond: Bool): Real` | `1` when true, `0` when false. |
| `exactly(k, terms)` | `predicate exactly(k: Real, terms: Comp(Real)): Bool` | Sum equals `k`. |
| `atleast(k, terms)` | `predicate atleast(k: Real, terms: Comp(Real)): Bool` | Sum is at least `k`. |
| `atmost(k, terms)` | `predicate atmost(k: Real, terms: Comp(Real)): Bool` | Sum is at most `k`. |
| `between(lo, hi, terms)` | `predicate between(lo: Real, hi: Real, terms: Comp(Real)): Bool` | Sum lies in `[lo, hi]`. |
| `iff(a, b)` | `predicate iff(a: Bool, b: Bool): Bool` | Boolean equivalence. |
| `xor(a, b)` | `predicate xor(a: Bool, b: Bool): Bool` | Exclusive or. |

Example:

```qsol
use stdlib.logic;

must exactly(2, indicator(Pick.has(i)) for i in Items);
```

### 13.2 Mapping Modules

| Module | Unknown | Semantics |
| --- | --- | --- |
| `stdlib.injective_mapping` | `InjectiveMapping(A, B)` | A mapping from `A` to `B` where each `b in B` has at most one preimage. |
| `stdlib.surjective_mapping` | `SurjectiveMapping(A, B)` | A mapping from `A` to `B` where each `b in B` has at least one preimage. |
| `stdlib.bijective_mapping` | `BijectiveMapping(A, B)` | Both injective and surjective. |

All expose:

```qsol
predicate is(a: Elem(A), b: Elem(B)): Bool
```

Example:

```qsol
use stdlib.bijective_mapping;

find SeatOf : BijectiveMapping(Guests, Seats);
must SeatOf.is(alice, seat1);
```

### 13.3 `stdlib.permutation`

`Permutation(A)` is a bijection from `A` to itself:

```qsol
use stdlib.permutation;

find Order : Permutation(Items);
must Order.is(first, second);
```

### 13.4 `stdlib.route`

`Route(Positions, V)` wraps a bijective mapping between route positions and
visited values. It exposes:

```qsol
predicate at(p: Elem(Positions), v: Elem(V)): Bool
predicate transition(p: Elem(Positions), q: Elem(Positions), u: Elem(V), v: Elem(V)): Bool
```

### 13.5 `stdlib.graph`

This module marks graph helpers and enables graph structure names used by the
compiler. Static graph behavior is compiler-owned rather than implemented as
ordinary QSOL decisions.

It also exposes compiler-known graph unknowns:

```qsol
use stdlib.graph;

find M : Matching(G);
```

`Matching(G)` requires an `UndirectedGraph`. It creates a matching decision over
`G.edges` and exposes `M.has_edge(u, v)`. The unknown itself only enforces the
matching property; cardinality, weights, and optimization direction belong in
ordinary `minimize` or `maximize` objectives.

## 14. TOML Configuration Format

QSOL runtime/build commands combine a `.qsol` model with a `.qsol.toml`
configuration file. The file contains scenario data and command defaults.

Minimal file:

```toml
schema_version = "1"

[entrypoint]
problem = "FirstProgram"
scenario = "baseline"
runtime = "local-dimod"
runtime_options = { sampler = "exact" }

[scenarios.baseline]
problem = "FirstProgram"

[scenarios.baseline.sets]
Items = ["i1", "i2", "i3", "i4"]

[scenarios.baseline.params]
Value = { i1 = 3, i2 = 8, i3 = 5, i4 = 2 }
```

Top-level tables:

| Table | Purpose |
| --- | --- |
| `schema_version` | Required string. Current schema is `"1"`. |
| `[entrypoint]` | CLI-equivalent defaults for the common run. |
| `[selection]` | Multi-scenario defaults. |
| `[defaults.execution]` | Default runtime/backend/plugins for all scenarios. |
| `[defaults.solve]` | Default solution count and energy thresholds. |
| `[scenarios.<name>]` | A named model instance. |
| `[scenarios.<name>.sets]` | Base set members. |
| `[scenarios.<name>.relations]` | Base relation rows. |
| `[scenarios.<name>.params]` | Scalar and indexed parameter values. |
| `[scenarios.<name>.execution]` | Scenario-specific runtime/backend/plugins. |
| `[scenarios.<name>.solve]` | Scenario-specific solve options. |

`[entrypoint]` keys:

| Key | Meaning |
| --- | --- |
| `problem` | Problem name to run when the source has multiple problems. |
| `scenario` | One default scenario. Mutually exclusive with `scenarios` and `all_scenarios`. |
| `scenarios` | Explicit list of scenarios for multi-scenario mode. |
| `all_scenarios` | Run every scenario in the file. |
| `combine_mode` | `intersection` or `union` for multi-scenario solves. |
| `failure_policy` | `run-all-fail`, `fail-fast`, or `best-effort`. |
| `out` | Default output directory. |
| `format` | Human-readable export format, normally `qubo` or `ising`. |
| `runtime` | Runtime id, such as `local-dimod` or `qiskit`. |
| `backend` | Backend id. Defaults to `dimod-cqm-v1` in current CLI workflows. |
| `plugins` | List of `module:attribute` plugin bundles to load. |
| `runtime_options` | Inline runtime options passed to the selected runtime. |
| `solutions` | Number of unique solutions requested. |
| `energy_min` | Inclusive minimum energy threshold. |
| `energy_max` | Inclusive maximum energy threshold. |

Selection defaults:

```toml
[selection]
mode = "subset"              # default, subset, or all
subset = ["small", "large"]
combine_mode = "intersection"
failure_policy = "run-all-fail"
```

Scenario execution and solve overrides:

```toml
[scenarios.large.execution]
runtime = "local-dimod"
plugins = ["my_pkg.plugins:plugin_bundle"]

[scenarios.large.solve]
solutions = 5
energy_max = 0
```

Resolution precedence:

1. CLI options
2. Scenario-specific config where applicable
3. `[entrypoint]`
4. `[selection]` or `[defaults]`
5. built-in defaults

## 15. CLI Commands

Root help:

```bash
uv run qsol -h
```

Core commands:

| Command | Purpose |
| --- | --- |
| `qsol build FILE` | Compile model and scenario data, check target support, and write artifacts. |
| `qsol solve FILE` | Build, run the selected runtime, and write `run.json`. |
| `qsol inspect parse FILE` | Parse and print AST, optionally as JSON. |
| `qsol inspect check FILE` | Parse, resolve, typecheck, validate, and report diagnostics. |
| `qsol inspect lower FILE` | Print symbolic lowered IR. |
| `qsol inspect estimate FILE -c FILE.toml` | Estimate grounded model size without writing artifacts. |
| `qsol targets list` | List built-in and loaded backend/runtime plugins. |
| `qsol targets capabilities --runtime ID` | Show runtime/backend capability catalogs. |
| `qsol targets check FILE -c FILE.toml --runtime ID` | Check model+scenario support for the selected runtime/backend pair. |

Common flags:

| Flag | Commands | Meaning |
| --- | --- | --- |
| `--config`, `-c` | `build`, `solve`, `inspect estimate`, `targets check` | TOML config path. |
| `--out`, `-o` | `build`, `solve`, `targets check` | Output directory. |
| `--format`, `-f` | `build`, `solve` | Human-readable export, normally `qubo` or `ising`. |
| `--runtime`, `-u` | `build`, `solve`, `targets check`, `targets capabilities` | Runtime plugin id. |
| `--plugin`, `-p` | Target-aware commands | Extra plugin bundle as `module:attribute`. |
| `--scenario` | Target-aware commands | Select one scenario; repeat for multi-scenario. |
| `--all-scenarios` | Target-aware commands | Select all scenarios in the config. |
| `--failure-policy` | Target-aware commands | `run-all-fail`, `fail-fast`, or `best-effort`. |
| `--combine-mode` | `solve` | `intersection` or `union` for multi-scenario result merging. |
| `--runtime-option`, `-x` | `solve` | Runtime option as `key=value`; repeatable. |
| `--runtime-options-file`, `-X` | `solve` | JSON object of runtime options. |
| `--solutions` | `solve` | Requested number of unique solutions. |
| `--energy-min`, `--energy-max` | `solve` | Inclusive energy thresholds for returned solutions. |
| `--estimate` | `targets check` | Print grounded size estimate with compatibility output. |
| `--json`, `-j` | Inspect commands that support it | Machine-readable output. |
| `--no-color`, `-n` | Leaf commands that support it | Disable ANSI styling. |
| `--log-level`, `-l` | Most leaf commands | `debug`, `info`, `warning`, or `error`. |

Aliases:

| Long command | Alias |
| --- | --- |
| `qsol build` | `qsol b` |
| `qsol solve` | `qsol s` |
| `qsol inspect ...` | `qsol ins ...` |
| `qsol targets ...` | `qsol tg ...` |
| `qsol inspect parse` | `qsol inspect p` |
| `qsol inspect check` | `qsol inspect c` |
| `qsol inspect lower` | `qsol inspect l` |
| `qsol inspect estimate` | `qsol inspect e` |
| `qsol targets list` | `qsol targets ls` |
| `qsol targets capabilities` | `qsol targets caps` |
| `qsol targets check` | `qsol targets chk` |

For full command tables and output examples, see [docs/CLI.md](docs/CLI.md).

## 16. Build and Solve Artifacts

`qsol build` writes:

| File | Meaning |
| --- | --- |
| `model.cqm` | Serialized `dimod.ConstrainedQuadraticModel`. |
| `model.bqm` | Converted `dimod.BinaryQuadraticModel` view. |
| `qubo.json` or `ising.json` | Human-readable objective export selected by `--format`. |
| `varmap.json` | Backend variable label to QSOL meaning map. |
| `explain.json` | Compiler diagnostics overlay. |
| `capability_report.json` | Required and supported target capabilities. |
| `qsol.log` | Log file when logging is configured by target-aware commands. |

`qsol solve` also writes:

| File | Meaning |
| --- | --- |
| `run.json` | Standard runtime result with status, best sample, selected assignments, scalars, timing, runtime options, and ranked solutions in `extensions.solutions`. |

There is no separate `solutions.json` artifact in the current implementation.
Multiple solutions are stored inside `run.json`.

## 17. Runtimes

### 17.1 `local-dimod`

Local runtime using `dimod` samplers.

Runtime options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `sampler` | string | `simulated-annealing` | `simulated-annealing` or `exact`. |
| `num_reads` | int | `100` | Reads for simulated annealing. Exact enumeration ignores this for sampling but it is still reported. |
| `seed` | int or null | `null` | Random seed for simulated annealing. |
| `solutions` | int | `1` | Number of unique ranked solutions requested. |
| `energy_min` | float or null | `null` | Inclusive minimum accepted energy. |
| `energy_max` | float or null | `null` | Inclusive maximum accepted energy. |

Example:

```bash
uv run qsol solve examples/tutorials/first_program.qsol \
  -c examples/tutorials/first_program.qsol.toml \
  --runtime local-dimod \
  -x sampler=exact
```

### 17.2 `qiskit`

Optional runtime for Qiskit experiments over dimod-exported BQM data. Install
optional dependencies before use:

```bash
uv sync --extra qiskit
```

Common runtime options include `algorithm` (`qaoa` or `numpy`), `fake_backend`,
`reps`, `maxiter`, `shots`, `seed`, and `optimization_level`. QAOA runs may
write `qaoa.qasm`.

See [docs/RUNTIMES.md](docs/RUNTIMES.md).

## 18. Backend Limits

The v1 backend is deliberately narrow. Important practical limits:

- CQM constraints must be reducible to supported linear/quadratic shapes.
- The converted BQM view cannot contain quadratic CQM constraints.
- Hard boolean if-then-else constraints are not generally supported.
- Soft `should` and `nice` are language surface forms, but backend support is
  intentionally limited.
- Custom unknowns are elaborated before backend support checking; the backend
  sees the expanded primitive decisions and laws.
- Some frontend-valid programs are rejected by `targets check` with `QSOL4010`.

Always run:

```bash
uv run qsol targets check model.qsol -c model.qsol.toml --runtime local-dimod --estimate
```

before assuming a model can build or solve.

More detail:

- [docs/BACKEND.md](docs/BACKEND.md)
- [docs/BACKEND_V1_LIMITS.md](docs/BACKEND_V1_LIMITS.md)
- [docs/COMPILER.md](docs/COMPILER.md)

## 19. Extensibility

QSOL can be extended at three levels:

1. Source modules: write `.qsol` files with reusable predicates, functions, and
   unknowns, then import them with `use`.
2. Runtime plugins: implement a Python `RuntimePlugin` to execute compiled
   models differently.
3. Backend plugins: implement a Python `BackendPlugin` for a new target model
   kind.

Plugin bundles are loaded with:

```bash
uv run qsol targets list --plugin my_pkg.plugins:plugin_bundle
uv run qsol solve model.qsol -c model.qsol.toml --plugin my_pkg.plugins:plugin_bundle
```

See:

- [docs/EXTENDING_QSOL.md](docs/EXTENDING_QSOL.md)
- [docs/CUSTOM_RUNTIME.md](docs/CUSTOM_RUNTIME.md)
- [docs/PLUGINS.md](docs/PLUGINS.md)

## 20. Pragmatic Modeling Workflow

Recommended workflow:

1. Write the model and keep it declarative.
2. Run `uv run qsol inspect check model.qsol`.
3. Add scenario TOML.
4. Run `uv run qsol inspect estimate model.qsol -c model.qsol.toml --json`.
5. Run `uv run qsol targets check model.qsol -c model.qsol.toml --runtime local-dimod --estimate`.
6. Build with `uv run qsol build ...`.
7. Solve with `uv run qsol solve ...`.
8. Inspect `run.json`, `varmap.json`, `explain.json`, and
   `capability_report.json`.

When a backend rejects a frontend-valid model, prefer changing the model shape
explicitly over relying on hidden compiler transformations. That keeps QSOL
models reviewable and diagnostics meaningful.
