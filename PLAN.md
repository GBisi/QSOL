# QSOL vNext Detailed Implementation Plan

Primary objective: implement the next language version after the finite-domain scalar foundation, with complete docs, tutorials, examples, tests, diagnostics, and regression coverage.

---

## 0. Scope and guiding constraints

This plan is for a coding agent working in the QSOL repository. It assumes the current repository already contains the finite-domain scalar work plan and partial or current implementation artifacts for:

- derived integer `Range(lo, hi)` sets,
- scalar and indexed scalar `find` declarations for `Bool` and bounded `Int`,
- CQM-native scalar decision support,
- CLI estimate/reporting support,
- tutorial examples for `first_program`, `assignment_balance`, `graph_coloring`, `minimum_graph_coloring`, and `scalar_bool_demo`,
- a strict contribution policy in `AGENTS.md`, including documentation, tests, vision coherence, and quality gates.

The next language iteration must not destabilize these pieces. Build incrementally.

### Non-negotiable repository rules

Before implementation starts:

1. Read `VISION.md`, `AGENTS.md`, and `CONTRIBUTING.md`.
2. Create a focused feature branch.
3. Establish a baseline by running the existing gates.
4. Add failing tests before changing grammar or semantics.
5. Do not claim completion unless the repository DoD checklist is filled in.

Mandatory gates before completion:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
```

For every user-visible behavior change, update docs and tutorials in the same PR series. Docs-only changes are not exempt from gates.

---

## 1. Current repository state to preserve

### 1.1 Compiler architecture

The compiler is stage-separated:

1. parse source into AST,
2. resolve imports,
3. elaborate custom unknowns,
4. resolve symbols,
5. typecheck,
6. validate structural rules,
7. desugar,
8. lower to symbolic kernel IR,
9. ground from scenario/config data,
10. resolve runtime/backend selection,
11. check target support,
12. compile/export backend artifacts,
13. run selected runtime.

Relevant code locations:

- `src/qsol/parse/grammar.lark`
- `src/qsol/parse/ast.py`
- `src/qsol/parse/ast_builder.py`
- `src/qsol/parse/module_loader.py`
- `src/qsol/sema/resolver.py`
- `src/qsol/sema/typecheck.py`
- `src/qsol/sema/validate.py`
- `src/qsol/sema/unknown_elaboration.py`
- `src/qsol/lower/desugar.py`
- `src/qsol/lower/lower.py`
- `src/qsol/lower/ir.py`
- `src/qsol/backend/instance.py`
- `src/qsol/backend/dimod_codegen.py`
- `src/qsol/config/`
- `src/qsol/targeting/`
- `src/qsol/diag/`
- `src/qsol/stdlib/`
- `tests/parser/`, `tests/sema/`, `tests/lower/`, `tests/backend/`, `tests/targeting/`, `tests/cli/`, `tests/golden/`

Preserve stage ownership: parsing creates syntax, sema proves meaning, lower normalizes syntax, grounding materializes static data, backend compiles supported grounded IR.

### 1.2 Current syntax and semantics

Current supported core forms include:

```qsol
use stdlib.logic;

problem Demo {
  set Items;
  set Positions = Range(1, size(Items));

  param Value[Items] : Real = 1;
  param Allowed[Items, Positions] : Bool = true;
  param Root : Elem(Items);

  find Pick : Subset(Items);
  find Assign : Mapping(Items -> Positions);
  find Enabled : Bool;
  find Load[Positions] : Int[0 .. size(Items)];

  must true;
  minimize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
```

Important current rules:

- `Range(lo, hi)` is inclusive and has no step.
- `Range` sets are derived; scenario TOML must not supply their elements.
- `find b : Bool` is a scalar binary decision.
- `find T : Int[lo .. hi]` is a native bounded CQM integer decision.
- `find X[IndexSet] : Bool/Int[...]` creates indexed scalar decisions.
- Primitive unknowns and custom unknowns must continue to work unchanged.
- `Subset` and `Mapping` remain core stable primitives.
- `Elem(Set)` params do not have defaults.
- Indexed params use bracket syntax, not call syntax.
- Boolean values must not silently coerce to numeric values; use `indicator(...)`.

### 1.3 Current stdlib surface

Current documented standard library modules include:

- `stdlib.logic`
  - `iff`
  - `xor`
  - `exactly`
  - `atleast`
  - `atmost`
  - `between`
  - `indicator`
- `stdlib.injective_mapping`
- `stdlib.surjective_mapping`
- `stdlib.bijective_mapping`
- `stdlib.permutation`

Preserve all current imports and behavior. New stdlib modules must not break existing dotted-module resolution.

### 1.4 Current backend boundary

The `dimod-cqm-v1` backend accepts models reducible to CQM-compatible linear/quadratic expressions. Unsupported or dangerous shapes include:

- cubic or higher-order products,
- variable division,
- unsupported dynamic sets,
- conditionals that lower to expressions beyond quadratic,
- unsupported piecewise forms without safe bounded linearization.

Backend diagnostics should remain in the `QSOL3xxx` family.

### 1.5 Current examples to preserve

Existing examples index includes:

- `examples/tutorials/`
- `examples/simple_subset/`
- `examples/generic_bqm/`
- `examples/min_bisection/`
- `examples/partition_equal_sum/`

The equivalence suite discovers `examples/*/test_equivalence.py` and legacy `test_quivalence.py` files. Do not break that discovery behavior. If a new example needs equivalence checking, place `test_equivalence.py` in that example folder.

---

## 2. Product goal for vNext

The next version should let users express relation-heavy optimization models without manually simulating tuples with parallel params.

Primary modeling improvements:

1. Static first-class relations.
2. Tuple and record binders.
3. Multi-generator comprehensions.
4. Groundable aggregate bounds for `Int` decisions.
5. Safe piecewise numeric forms: `abs`, `min`, `max`.
6. Graph standard library built on relations.
7. Route/path/cycle helpers built on `BijectiveMapping`/`Permutation`.
8. Transparent global constraints for graph/order structures.
9. Better model-size estimation and backend diagnostics.
10. A 24-model NP/Ising regression suite.

Design principle: high-level constructs must lower to inspectable IR/artifacts. Avoid opaque solver magic.

---

## 3. Feature priority and dependencies

### Priority P0: verification and baseline

Must happen before feature work.

- Verify existing `Range`, scalar `Bool`, scalar `Int`, indexed scalar decisions, estimate CLI, and examples.
- Run current gates.
- Add regression tests around the current behavior most likely to be affected by relation/comprehension work.

### Priority P1: relation substrate and comprehensions

Highest leverage. Enables most graph/set/logical models.

- Multi-generator comprehension grammar and AST.
- Static `relation` declarations.
- Tuple binders and field access.
- Relation membership calls.
- Scenario relation loading.
- Derived relations.
- Estimator relation support.

### Priority P1: piecewise numeric builtins

Smaller but high usability.

- `abs(expr)`.
- `min(a, b)`, `max(a, b)`.
- Aggregate `min`/`max` if feasible.
- Conservative exact lowering and diagnostics.

### Priority P1/P2: groundable aggregate bounds

Important for scheduling, flow, connectivity, and graph globals.

- Accept static aggregate expressions in `Int` bounds.
- Reject decision-dependent bounds precisely.

### Priority P2: graph stdlib

Build after relations exist.

- Adjacency.
- Incidence.
- Complement/nonedge relations.
- Degree helpers.
- Directed arc expansion from undirected edge relations.

### Priority P2/P3: route and graph/order globals

Build after relations and aggregate-bound infrastructure.

- `Route` helper.
- `all_different` convenience.
- `acyclic_directed`.
- `connected`.
- `tree`.
- `forest`.
- `flow_conservation`.

### Priority P3: optional advanced ergonomics

Do after the core is stable.

- Dedicated `graph G ...` syntax.
- Variable-indexed parameter sugar.
- Lexicographic objectives.
- Automatic higher-order quadratization beyond conservative cases.

---

## 4. Milestone 0: baseline, inventory, and guardrails

### 4.1 Branch and setup

```bash
git checkout -b feature/relations-graph-vnext
uv sync --extra dev
uv run qsol -h
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
```

Record baseline status in the first PR description.

### 4.2 Snapshot current syntax behavior

Create parser and sema tests that lock current behavior before adding relations:

- `Range` set declaration parses.
- scalar `Bool` find parses and typechecks.
- bounded `Int` find parses and typechecks.
- indexed `Bool` and `Int` finds parse and typecheck.
- `Subset` and `Mapping` finds still parse and typecheck.
- existing `Comp(Bool)` and `Comp(Real)` macro args still parse.
- single-generator `sum`, `count`, `any`, `all` still parse.
- nested single-generator aggregate pattern still parses:

```qsol
sum(sum(Cost[a, b] for b in B) for a in A)
```

### 4.3 Add explicit probes for future features

Add xfail or failing tests for desired syntax:

```qsol
relation Edge(u: V, v: V);
sum(Cost[u, v] for u in V for v in V where u != v)
count((u, v) in Edge where Pick.has(u) and Pick.has(v))
Edge(u, v)
Edge.e
```

Use these to drive implementation.

### 4.4 Documentation audit task

Before code changes, audit these docs for current truth:

- `README.md`
- `QSOL_reference.md`
- `docs/README.md`
- `docs/QSOL_SYNTAX.md`
- `docs/STDLIB.md`
- `docs/CLI.md`
- `docs/COMPILER.md`
- `docs/BACKEND.md`
- `docs/BACKEND_V1_LIMITS.md`
- `docs/TUTORIAL.md`
- `docs/tutorials/README.md`
- `docs/tutorials/01-first-program.md`
- `docs/tutorials/02-writing-your-own-model.md`
- `docs/tutorials/03-compiling-running-and-reading-results.md`
- `docs/tutorials/04-custom-unknowns-functions-and-predicates.md`
- `docs/CODEBASE.md`
- `docs/EXTENDING_QSOL.md`

Create a short `docs/vnext_audit_notes.md` only if inconsistencies are large enough to require tracking. Otherwise fix docs in each milestone PR.

---

## 5. Milestone 1: multi-generator comprehensions

### 5.1 User-facing goal

Allow natural syntax:

```qsol
sum(Cost[u, v] for u in U for v in V)
sum(Cost[u, v] for u in V for v in V where u != v)
any(Allowed[i, j, k] for i in I for j in J for k in K)
all(Constraint[i, j] for i in I for j in J where Active[i])
```

This should be backward-compatible with current single-generator comprehensions.

### 5.2 Syntax decisions

Support binder lists in:

- numeric comprehensions,
- boolean comprehensions,
- count comprehensions,
- `Comp(Bool)` and `Comp(Real)` call arguments.

Target surface:

```qsol
sum(term for x in X for y in Y where cond else alt)
count(x for x in X for y in Y where cond)
any(term for x in X for y in Y where cond else false)
```

Do not add tuple binders in this milestone unless the relation AST is being implemented at the same time. If implemented separately, allow only named binders over set domains first.

### 5.3 AST changes

Current comprehension AST likely stores one `var` and one `domain_set`. Replace with a list.

Add:

```python
@dataclass(frozen=True, slots=True)
class CompBinder(Node):
    var: str
    domain: DomainRef

@dataclass(frozen=True, slots=True)
class SetDomainRef(Node):
    set_name: str
```

For now, `DomainRef` may only be `SetDomainRef`. Relation domain refs come in Milestone 2.

Change comprehension nodes from:

```python
var: str
domain_set: str
```

to:

```python
binders: tuple[CompBinder, ...]
```

Migration rule: a single binder is represented as a one-item tuple.

### 5.4 Parser changes

Update `src/qsol/parse/grammar.lark` to parse one or more binders after the term:

```ebnf
comp_binders: comp_binder+
comp_binder: "for" NAME "in" NAME
```

Keep the current accepted forms intact.

### 5.5 AST builder changes

Update `src/qsol/parse/ast_builder.py`:

- build `CompBinder` nodes,
- attach binder tuples to numeric/boolean/count comprehensions,
- preserve spans for binder diagnostics.

### 5.6 Resolver/typechecker changes

Update binder scoping:

- process binders left to right,
- reject duplicate binder names in one comprehension,
- each binder domain must be a declared set,
- each binder introduces `Elem(Set)` or numeric `ElemOfType` for `Range` sets,
- `where`, `else`, and term expressions see all binders.

Diagnostics:

- unknown binder domain: `QSOL2001` or existing semantic code family,
- duplicate binder: semantic error with source span,
- `where` not `Bool`,
- numeric/boolean branch type mismatch,
- invalid shadowing of existing local binder.

### 5.7 Lowering changes

Update `src/qsol/lower/ir.py` comprehension IR.

Options:

1. Carry binder lists through Kernel IR and Ground IR.
2. Desugar multi-generator comprehensions to nested single-generator comprehensions before lowering.

Preferred: carry binder lists through IR. This is cleaner for estimator and relation support.

### 5.8 Grounding/backend changes

Update expression walkers in:

- instance grounding,
- codegen,
- expression degree analysis,
- estimator,
- capability checks.

Each binder list should ground as nested loops. Preserve left-to-right order for deterministic variable/constraint labels.

### 5.9 Tests

Add parser tests:

- numeric two-generator sum,
- boolean two-generator any/all,
- count with two generators,
- `where` and `else`,
- duplicate binder rejection,
- unknown domain rejection.

Add typecheck tests:

- term sees both binders,
- range binders support arithmetic,
- opaque binders reject arithmetic,
- shadowing errors.

Add lower/backend tests:

- two-generator objective compiles,
- two-generator constraint compiles,
- nested old-style and new-style produce equivalent CQM for tiny model.

### 5.10 Documentation updates

Mandatory files:

- `QSOL_reference.md`: comprehension semantics.
- `docs/QSOL_SYNTAX.md`: examples for multi-generator comprehensions.
- `docs/TUTORIAL.md`: if tutorials show nested aggregates.
- `docs/tutorials/02-writing-your-own-model.md`: add a small multi-generator expression.
- `docs/BACKEND_V1_LIMITS.md`: note that multi-generator comprehensions can create large grounded products but are semantically static.
- `docs/CODEBASE.md`: update if IR shape changes materially.

Examples:

- Update `examples/tutorials/graph_coloring.qsol` or add `examples/tutorials/multigen_demo.qsol`.
- Add tutorial README entry.

---

## 6. Milestone 2: static relation declarations

### 6.1 User-facing goal

Allow structured static data such as graph edges, set membership, clauses, arcs, transitions, and incidence without parallel params.

Surface syntax:

```qsol
problem IndependentSet {
  set V;
  relation Edge(u: V, v: V);

  find Pick : Subset(V);

  must forall (u, v) in Edge: not (Pick.has(u) and Pick.has(v));
  maximize count(v in V where Pick.has(v));
}
```

Also support relation membership calls:

```qsol
Edge(u, v)
not Edge(u, v)
```

### 6.2 Initial relation kind

Implement **static finite relations only**.

Do not support decision-dependent relations.
Do not support mutable relations.
Do not support relation-valued unknowns.
Do not support higher-kinded relation params yet.

### 6.3 Syntax

Base relation declaration:

```qsol
relation Edge(u: V, v: V);
relation Incidence(set: Sets, element: Universe);
relation Arc(tail: V, head: V);
```

Tuple binder:

```qsol
for (u, v) in Edge
forall (u, v) in Edge: expr
exists (u, v) in Edge: expr
```

Record binder:

```qsol
for e in Edge
Edge.u
```

Important: field access syntax should not conflict with method calls. If `e.u` is difficult because `e` is a tuple binder value, support only tuple destructuring in vNext and defer record binders. If both are feasible, implement both.

### 6.4 AST changes

Add problem statement:

```python
@dataclass(frozen=True, slots=True)
class RelationDecl(ProblemStmt):
    name: str
    fields: tuple[RelationField, ...]
    expr: RelationExpr | None = None

@dataclass(frozen=True, slots=True)
class RelationField(Node):
    name: str
    set_name: str
```

Add relation expressions later in this milestone or milestone 3:

```python
class RelationExpr(Node): ...
class PairsRelationExpr(RelationExpr): ...
class FilterRelationExpr(RelationExpr): ...
```

Add relation membership expression:

```python
RelationCall(name: str, args: tuple[Expr, ...]) -> BoolExpr
```

Be careful to distinguish `Edge(u, v)` from existing function calls. Resolver should determine whether name is a relation or function and produce clear diagnostics for arity mistakes.

### 6.5 Symbol table changes

Add `SymbolKind.RELATION` and type:

```python
@dataclass(frozen=True, slots=True)
class RelationType(Type):
    name: str
    fields: tuple[RelationFieldType, ...]

@dataclass(frozen=True, slots=True)
class RelationFieldType:
    name: str
    set_type: SetType
```

Resolver rules:

- relation fields reference declared sets,
- duplicate relation names rejected,
- duplicate field names in one relation rejected,
- relation name cannot collide with set/param/find/function/predicate names in same scope,
- derived relation dependencies must reference known static sets/relations.

### 6.6 Typechecker rules

Relation membership:

```qsol
Edge(u, v)
```

- arity must match relation fields,
- argument type must be compatible with field set element type,
- result type is `Bool`.

Tuple binders:

```qsol
for (u, v) in Edge
```

- arity must match relation field count,
- each variable gets `Elem(FieldSet)` type,
- duplicate binder names rejected.

Record binders if implemented:

```qsol
for e in Edge
```

- `e` gets a tuple/record element type,
- `e.u` gets `Elem(V)` for field `u`,
- invalid field names error with suggestions.

### 6.7 IR changes

Add relation declarations to `KProblem`:

```python
relations: tuple[KRelationDecl, ...]
```

Add grounded relation values to `GroundProblem`:

```python
relation_values: dict[str, tuple[tuple[str | int, ...], ...]]
```

or use typed element values consistent with existing `set_values`.

Add IR domain refs:

```python
KSetDomainRef(set_name)
KRelationDomainRef(relation_name, fields_or_tuple)
```

Add relation call IR node:

```python
KRelationCall(name, args)
```

### 6.8 Grounding model

Base relations are loaded from scenario TOML.

Canonical TOML:

```toml
[scenarios.triangle.sets]
V = ["a", "b", "c"]

[scenarios.triangle.relations]
Edge = [
  { u = "a", v = "b" },
  { u = "b", v = "c" },
  { u = "a", v = "c" },
]
```

Optional compact form after canonical is stable:

```toml
[scenarios.triangle.relations]
Edge = [["a", "b"], ["b", "c"], ["a", "c"]]
```

Validation rules:

- missing relation -> error unless default empty relation is explicitly supported,
- unknown relation in scenario -> error,
- derived relation supplied in scenario -> error,
- missing field -> error,
- extra field -> error,
- element not in declared set -> error,
- wrong tuple arity -> error,
- duplicate tuple -> dedupe with warning or error. Prefer warning + deterministic dedupe for user ergonomics.

Diagnostic family: likely `QSOL22xx` or `QSOL42xx` depending whether scenario materialization currently uses instance/targeting codes. Use existing taxonomy consistently.

### 6.9 Relation lowering strategy

Internally lower relation binders to static tuple iteration.

Do not lower user relations to visible sets/params unless necessary. If generated helper structures are used, hide names and preserve source-origin metadata.

For relation membership calls:

- If all args are ground constants, evaluate at grounding.
- If args are binders, evaluate during grounded loop expansion.
- If args include decision-dependent expressions, reject in vNext. Relation membership is static membership over static elements only.

### 6.10 Tests

Parser:

- base relation declaration,
- relation field parsing,
- tuple binder in quantifier,
- tuple binder in sum/count/any/all,
- relation membership call,
- invalid relation syntax.

Resolver/typecheck:

- field set exists,
- duplicate field names rejected,
- arity mismatch rejected,
- wrong field type rejected,
- unknown relation call rejected,
- function/relation name collision rejected,
- tuple binder types available in body.

Grounding:

- canonical TOML relation loads,
- compact tuple TOML loads if supported,
- wrong relation shape diagnostics,
- duplicate handling deterministic,
- relation membership evaluates.

Backend/codegen:

- relation iteration in objective,
- relation iteration in constraints,
- relation membership in `where`,
- relation membership in boolean formula.

Golden diagnostics:

- wrong arity,
- wrong field name,
- missing scenario relation,
- element not in set.

### 6.11 Documentation updates

Mandatory:

- `QSOL_reference.md`
  - new `relation` declarations,
  - relation membership semantics,
  - tuple binders,
  - scenario TOML relation schema,
  - static-only limitation.
- `docs/QSOL_SYNTAX.md`
  - concise relation syntax section.
- `docs/TUTORIAL.md`
  - introduce a relation example if high-level tutorial mentions graph/set models.
- `docs/tutorials/02-writing-your-own-model.md`
  - add relation-based set packing or graph edge example.
- `docs/tutorials/03-compiling-running-and-reading-results.md`
  - add TOML relation loading and output note if artifacts change.
- `docs/COMPILER.md`
  - describe relation lowering/grounding.
- `docs/CODEBASE.md`
  - update AST/IR/config directory responsibilities.
- `docs/BACKEND.md`
  - explain relation values are grounded before backend.
- `docs/BACKEND_V1_LIMITS.md`
  - relation iteration can still produce backend-unsupported expression degree.
- `docs/README.md`
  - add relation tutorial link if new file added.

Examples:

- `examples/tutorials/relation_set_packing.qsol`
- `examples/tutorials/relation_set_packing.qsol.toml`
- `examples/tutorials/relation_graph_independent_set.qsol`
- `examples/tutorials/relation_graph_independent_set.qsol.toml`
- Update `examples/tutorials/README.md`.
- Update `examples/README.md` if adding a new top-level example folder.

---

## 7. Milestone 3: derived relations

### 7.1 User-facing goal

Allow users to derive static relations from static sets/relations.

Examples:

```qsol
relation Pair(u: V, v: V) = pairs(u in V, v in V where u != v);
relation NonEdge(u: V, v: V) = pairs(u in V, v in V where u != v and not Edge(u, v));
relation Incident(e: Edge, v: V) = pairs(e in Edge, v in V where e.u = v or e.v = v);
```

If relation-valued fields such as `e: Edge` are too complex, support simpler tuple destructuring first:

```qsol
relation Incident(u: V, v: V, x: V) = pairs((u, v) in Edge, x in V where u = x or v = x);
```

### 7.2 Constructors for vNext

Implement only these constructors initially:

```qsol
pairs(x in X, y in Y)
pairs(x in X, y in Y where cond)
pairs(x in X, y in Y, z in Z where cond)
filter((u, v) in Edge where cond)
```

If parser complexity is high, use only a unified derived form:

```qsol
relation NonEdge(u: V, v: V) = select(u in V, v in V where cond);
```

Pick one spelling and document it. Recommended spelling: `pairs(...)` for Cartesian product-derived relations, `filter(...)` for filtering existing relations.

### 7.3 Static-only condition rule

Derived relation conditions must be scenario-time static. They may reference:

- set binders,
- relation binders,
- scalar params,
- indexed params,
- relation membership calls,
- arithmetic/comparisons over static values.

They must not reference:

- `find` decisions,
- `Subset.has`, `Mapping.is`, or custom unknown views,
- generated backend variables.

### 7.4 Cycle/dependency validation

Derived relations can depend on base or earlier derived relations. Implement dependency graph validation:

- no self-dependency,
- no cycles,
- deterministic evaluation order,
- clear diagnostic showing dependency cycle.

### 7.5 Grounding

Evaluate derived relations after all base sets, params, and base relations are loaded.

Do not allow scenario TOML to supply derived relations.

### 7.6 Estimator

Report:

- base relation cardinality,
- derived relation cardinality,
- source expression summary,
- Cartesian product size before filter if available,
- warning for large generated relations.

### 7.7 Tests

- derive full Cartesian product,
- derive filtered pairs,
- derive complement/nonedge,
- relation membership in filter,
- param condition in filter,
- reject decision-dependent filter,
- reject cycle in derived relations,
- reject supplied derived relation in TOML,
- estimator reports derived relation sizes.

### 7.8 Documentation and examples

Update all relation docs from Milestone 2.

Add examples:

- maximum clique using derived `NonEdge`,
- graph coloring using `Edge`,
- set cover with `Contains(set, element)` relation.

Update:

- `examples/tutorials/README.md`,
- `examples/README.md`,
- `docs/tutorials/02-writing-your-own-model.md`,
- `docs/QSOL_SYNTAX.md`,
- `QSOL_reference.md`.

---

## 8. Milestone 4: groundable aggregate bounds

### 8.1 User-facing goal

Accept scenario-time static aggregates in bounded integer decisions:

```qsol
find Makespan : Int[0 .. sum(Length[j] for j in Jobs)];
find Flow[Arc] : Int[0 .. size(V) - 1];
find SelectedCount : Int[0 .. count(s in Sets)];
```

### 8.2 Groundability rule

A bound is valid if it depends only on static data:

- literals,
- scalar params,
- indexed params over static sets/relations,
- `size(Set)` and `size(Relation)`,
- static `sum`, `count`, `min`, `max`,
- arithmetic over groundable expressions,
- static `if` expressions,
- relation membership over static values.

Invalid if it depends on:

- any `find`,
- unknown view predicates/functions,
- decision-dependent `where`,
- relation definitions depending on decisions.

### 8.3 Implementation

Add or extend a `GroundabilityChecker` used by typecheck and grounding.

Output:

- valid/invalid,
- inferred numeric type,
- dependency trace for diagnostics,
- optional conservative bound estimate.

The existing `_eval_int_expr` and `_eval_num_expr` in instance materialization can be extended, but do not bury semantic dependency checks inside only evaluation code. The user should get a semantic-quality diagnostic, not merely “could not evaluate.”

### 8.4 Diagnostics

Example:

```text
QSOL22xx: Int upper bound is not scenario-time constant.
The expression depends on decision `Pick.has(j)`.
Only input params, size(...), static relations, and aggregates over static domains are allowed in decision bounds.
```

### 8.5 Tests

- accept aggregate over set param,
- accept aggregate over relation param,
- accept `size(Relation)`,
- accept `count((u,v) in Edge where ...)`,
- reject `sum(if Pick.has(j) then Weight[j] else 0 for j in Jobs)`,
- reject relation filter with decision predicate,
- grounding attaches concrete integer bounds,
- backend creates native integer vars with correct bounds,
- estimator reports domain sizes.

### 8.6 Documentation and examples

Update:

- `QSOL_reference.md`,
- `docs/QSOL_SYNTAX.md`,
- `docs/BACKEND.md`,
- `docs/BACKEND_V1_LIMITS.md`,
- `docs/COMPILER.md`,
- `docs/tutorials/02-writing-your-own-model.md`,
- `docs/tutorials/03-compiling-running-and-reading-results.md` if scalar output examples change.

Add/update examples:

- `examples/tutorials/job_sequencing.qsol`,
- `examples/tutorials/job_sequencing.qsol.toml`,
- update `examples/tutorials/README.md`.

---

## 9. Milestone 5: safe piecewise numeric builtins

### 9.1 User-facing goal

Allow natural optimization expressions:

```qsol
minimize abs(balance);
minimize max(load[m] for m in Machines);
maximize min(score[a] for a in Agents);
```

### 9.2 Builtins

Add compiler-owned builtins:

- `abs(expr)`
- `min(a, b)`
- `max(a, b)`
- aggregate `min(term for ...)` and `max(term for ...)` if feasible.

Do not implement as ordinary stdlib macros, because lowering needs backend-aware auxiliary variables and diagnostics.

### 9.3 Supported first pass

Exact supported forms:

```qsol
minimize abs(e)
must abs(e) <= C
minimize max(term for ...)
maximize min(term for ...)
```

Optionally support:

```qsol
x = abs(e)
x >= max(...)
x <= min(...)
```

only if finite bounds are known and lowering is exact.

### 9.4 Reject initially

Reject with actionable diagnostics:

- `maximize abs(e)` unless explicitly linearized safely,
- `minimize min(...)`,
- `maximize max(...)`,
- `abs(e) >= C` without disjunction support,
- non-affine `e` if lowering would exceed backend degree,
- missing finite bounds for required auxiliary variables.

### 9.5 Lowering

`minimize abs(e)`:

```text
introduce aux z
z >= e
z >= -e
minimize z
```

`must abs(e) <= C`:

```text
e <= C
-e <= C
```

`minimize max(term for b in B)`:

```text
introduce aux T
forall b in B: T >= term[b]
minimize T
```

`maximize min(term for b in B)`:

```text
introduce aux Z
forall b in B: Z <= term[b]
maximize Z
```

Aux variables must appear in explain/estimate artifacts.

### 9.6 Code locations

Likely impacted:

- `src/qsol/parse/ast.py` if builtins get special AST nodes; otherwise parse as calls.
- `src/qsol/sema/typecheck.py` for builtin typing.
- `src/qsol/lower/desugar.py` for aux introduction.
- `src/qsol/lower/ir.py` for generated aux/find/constraints metadata.
- `src/qsol/backend/dimod_codegen.py` for safe compilation.
- `src/qsol/targeting/compatibility.py` for support checks.
- `src/qsol/diag/` for new diagnostics.
- estimator module.

Preferred implementation: recognize builtin calls in sema/lower, then rewrite to ordinary IR with compiler-generated scalar finds and constraints before backend.

### 9.7 Diagnostics

Add or extend `QSOL31xx` diagnostics for piecewise lowering:

- unsupported context,
- non-affine argument,
- missing finite bound,
- backend target lacks piecewise lowering,
- expression would exceed quadratic degree.

### 9.8 Tests

Parser:

- builtin calls parse as expressions.

Typecheck:

- numeric args accepted,
- boolean args rejected,
- aggregate min/max terms numeric,
- empty aggregate validation if detectable.

Lowering/backend:

- number partitioning with `abs`,
- scheduling with `max`,
- maximize-min toy model,
- `abs(e) <= C` constraint,
- unsupported forms produce diagnostics.

Estimator:

- generated aux variable counts,
- generated constraints counts,
- source-origin metadata.

### 9.9 Documentation and examples

Update:

- `QSOL_reference.md`,
- `docs/QSOL_SYNTAX.md`,
- `docs/BACKEND.md`,
- `docs/BACKEND_V1_LIMITS.md`,
- `docs/COMPILER.md`,
- `docs/STDLIB.md` only to say these are compiler builtins, not stdlib macros,
- `docs/tutorials/02-writing-your-own-model.md`,
- `docs/tutorials/03-compiling-running-and-reading-results.md` if explain/estimate output changes.

Examples:

- update `examples/partition_equal_sum/` or add `examples/number_partitioning_abs/`,
- add `examples/tutorials/job_sequencing_max.qsol`,
- update `examples/README.md`,
- update `examples/tutorials/README.md`.

---

## 10. Milestone 6: graph standard library

### 10.1 User-facing goal

Make graph models readable without parallel endpoint params.

Do this with stdlib conventions, not a core `graph` keyword yet.

### 10.2 Relation conventions

Undirected graph, canonical edge relation:

```qsol
set V;
relation Edge(u: V, v: V);
```

Directed graph:

```qsol
set V;
relation Arc(tail: V, head: V);
```

If undirected edges are stored canonically, stdlib adjacency should be symmetric:

```qsol
adjacent(Edge, u, v) = Edge(u, v) or Edge(v, u)
```

If relation formals are not yet available for macros, implement graph helpers as compiler-known stdlib builtins or provide documented relation patterns.

### 10.3 Required helpers

Minimum target API:

```qsol
use stdlib.graph;

adjacent(Edge, u, v)
incident(Edge, e, v)          // if edge records supported
nonedge(Edge, u, v)
degree(UseEdge, Edge, v)
```

Alternative if relation-valued macro formals are hard:

- `relation NonEdge(u: V, v: V) = graph_non_edges(V, Edge);`
- `relation Incident(edge: Edge, vertex: V) = graph_incidence(V, Edge);`

### 10.4 Scenario validators

Add optional graph validators, not hard-coded relation semantics:

- no self-loops if declared simple graph,
- no duplicate undirected edges,
- canonical edge ordering check if requested,
- symmetric relation check if requested,
- endpoints in vertex set,
- weights exist for each edge when weighted helper requires them.

Surface possibilities:

```qsol
relation Edge(u: V, v: V) @graph(simple=true, directed=false, canonical=true);
```

Defer annotations if too much. Instead provide CLI/docs validator recipes.

### 10.5 Tests

- independent set with `Edge`,
- vertex cover with `Edge`,
- maximum clique using `NonEdge`,
- graph coloring with `Edge`,
- min bisection with `Edge`,
- wrong graph relation shape diagnostics.

### 10.6 Documentation and examples

Update:

- `docs/STDLIB.md`: new `stdlib.graph` section.
- `docs/EXTENDING_QSOL.md`: relation-aware stdlib patterns if macro formals change.
- `QSOL_reference.md`: relation-formal semantics if added.
- `docs/QSOL_SYNTAX.md`: concise graph examples.
- `docs/TUTORIAL.md`: graph example if suitable.
- `docs/tutorials/02-writing-your-own-model.md`: relation graph example.
- `docs/BACKEND_V1_LIMITS.md`: graph helpers are source-level; backend limits still apply.

Examples:

- refactor or add `examples/min_bisection_relation/`,
- add `examples/tutorials/independent_set.qsol`,
- add `examples/tutorials/vertex_cover.qsol`,
- update `examples/README.md`.

---

## 11. Milestone 7: route/path/cycle helper

### 11.1 User-facing goal

Hamiltonian path/cycle and TSP should not require users to hand-write a large nested expression over positions and vertices.

Target syntax:

```qsol
use stdlib.route;

set V;
set Positions = Range(1, size(V));
relation Arc(u: V, v: V);

find Tour : Route(Positions, V);

must uses_only(Tour, Arc);
minimize transition_cost(Tour, Arc, Weight);
```

If this is too ambitious, implement smaller helpers:

```qsol
find At : BijectiveMapping(Positions, V);
transition_used(At, p, q, u, v)
```

### 11.2 Route representation

Represent `Route(Positions, V)` as a custom unknown wrapping `BijectiveMapping(Positions, V)`.

Views:

```qsol
predicate at(p: Elem(Positions), v: Elem(V))
predicate transition(p: Elem(Positions), q: Elem(Positions), u: Elem(V), v: Elem(V))
```

Potential problem: `transition(...)` is the product of two decision predicates. It may lead to quadratic expressions, and gated numeric branches may become cubic if not lowered carefully. The helper must either introduce auxiliary binaries or provide diagnostics.

### 11.3 Successor relation

Do not hard-code position arithmetic in the helper. Use an explicit static relation:

```qsol
relation Next(p: Positions, q: Positions);
```

For cycles, TOML or derived relation can supply wrap-around successor.

Future sugar:

```qsol
relation Next(p: Positions, q: Positions) = successor(Positions, cyclic=true);
```

### 11.4 Tests

- route is bijective,
- Hamiltonian path penalty model parses/checks/builds for tiny instance,
- Hamiltonian cycle penalty model parses/checks/builds,
- TSP cost expression either builds or gives precise degree diagnostic,
- estimator reports `O(|Positions|^2 |V|^2)` transition expansion if helpers expand naively.

### 11.5 Docs and examples

Update:

- `docs/STDLIB.md`: `stdlib.route`,
- `docs/EXTENDING_QSOL.md` if route is a custom unknown pattern,
- `QSOL_reference.md`: no new core syntax unless added,
- `docs/BACKEND_V1_LIMITS.md`: transition products and recommended helpers,
- `docs/tutorials/04-custom-unknowns-functions-and-predicates.md`: route as custom unknown if implemented that way.

Examples:

- `examples/np_ising_problems/16_hamiltonian_path_optimization.qsol`,
- `examples/np_ising_problems/17_hamiltonian_cycle_optimization.qsol`,
- `examples/np_ising_problems/18_traveling_salesman_problem.qsol`,
- tiny TOML scenarios.

---

## 12. Milestone 8: graph/order global constraints

### 12.1 User-facing goal

Provide transparent globals for recurring combinatorial structures:

```qsol
must all_different(Assign[i] for i in Items);
must acyclic_directed(V, Arc, KeepArc);
must connected(V, Edge, UseEdge);
must tree(V, Edge, UseEdge);
must forest(V, Edge, UseEdge);
must flow_conservation(Arc, Flow, Balance);
```

### 12.2 Design principle

Implement as inspectable stdlib/lowering templates. Every generated variable and constraint must carry source-origin metadata.

### 12.3 `all_different`

If `InjectiveMapping` already covers most use cases, add `all_different` mainly for scalar/indexed expression ergonomics.

Lowering:

- for finite enumerated domains, pairwise disequality or mapping injectivity,
- for `Range` integer values, support only bounded integer disequality if backend supports it cleanly; otherwise reject with diagnostic.

### 12.4 `acyclic_directed`

Input:

```qsol
relation Arc(tail: V, head: V);
find Remove : Subset(Arc);        // if relation-valued subsets are supported
```

If `Subset(Relation)` is not supported, use indexed bool decisions:

```qsol
find KeepArc[Arc] : Bool;
```

Lowering:

- introduce `Rank[V] : Int[1 .. size(V)]`, or
- use `BijectiveMapping(V, Positions)`.

For each kept arc `(u, v)`:

```qsol
Rank[u] < Rank[v]
```

Need conditional inequality support over `KeepArc[a]`.

### 12.5 `connected` and `tree`

Preferred lowering: single-commodity flow.

For an active graph:

- choose root or require supplied root,
- create directed arcs from undirected edges,
- create `Flow[DirectedArc] : Int[0 .. size(V)-1]`,
- enforce no flow on unselected edges,
- root sends `n_active - 1`,
- every active non-root receives one unit net flow,
- inactive vertices have zero incident selected edges/flow.

This requires groundable aggregate bounds and relation iteration.

`tree` = `connected` + selected edge count equals active vertex count minus one.

### 12.6 `forest`

General undirected forest is harder. Implement in this order:

1. `forest_by_cycles(Remove, Cycles)` where `Cycles` is an instance-supplied relation.
2. rooted forest with parent/rank encoding for directed/arborescence-style cases.
3. full undirected forest global after component machinery exists.

Do not claim general forest support until exact encoding exists.

### 12.7 Tests

- DAG topological order tiny instances,
- directed feedback vertex set model,
- directed feedback edge set model,
- connected selected subgraph tiny positive/negative examples,
- tree selected subgraph tiny positive/negative examples,
- estimator for generated flow variables,
- backend diagnostics for large/unsupported instances.

### 12.8 Docs and examples

Update:

- `docs/STDLIB.md`: globals section,
- `docs/BACKEND_V1_LIMITS.md`: generated variables and unsupported scale caveats,
- `docs/COMPILER.md`: global expansion and source-origin metadata,
- `docs/tutorials/04-custom-unknowns-functions-and-predicates.md`: if globals are custom unknowns/templates,
- `docs/tutorials/02-writing-your-own-model.md`: one graph global example if simple enough.

Examples:

- degree-constrained MST,
- Steiner tree,
- directed feedback vertex set,
- directed feedback edge set,
- undirected feedback vertex set as cycle-hitting if full forest is not ready.

---

## 13. Milestone 9: model-size estimator and explain output

### 13.1 User-facing goal

Before backend compilation, users should understand how large a model becomes.

Extend `qsol inspect estimate` and `qsol targets check --estimate` to report relation and global expansion.

### 13.2 Required JSON fields

Add or extend stable output fields:

```json
{
  "sets": {
    "V": {"size": 20, "derived": false},
    "Positions": {"size": 20, "derived": true, "source": "Range(1, size(V))"}
  },
  "relations": {
    "Edge": {"arity": 2, "size": 60, "derived": false},
    "NonEdge": {"arity": 2, "size": 320, "derived": true, "cartesian_candidates": 380}
  },
  "decisions": {
    "binary": 400,
    "integer": 45,
    "auxiliary_binary": 120,
    "auxiliary_integer": 10
  },
  "constraints": {
    "user": 84,
    "generated_unknown_laws": 60,
    "generated_globals": 220,
    "generated_piecewise": 12
  },
  "expressions": {
    "max_polynomial_degree_before_reduction": 3,
    "max_polynomial_degree_after_reduction": 2
  },
  "backend": {
    "target": "dimod-cqm-v1",
    "supported": true,
    "warnings": []
  }
}
```

### 13.3 Warnings

Warn for:

- relation cardinality above threshold,
- Cartesian product above threshold,
- `O(N^4)` expansions,
- dense graph route/TSP expansions,
- large integer bounds if binary expansion is used anywhere,
- graph globals that introduce flow variables over dense arcs,
- piecewise lowering introducing many auxiliaries.

### 13.4 Explain/source metadata

Generated variables/constraints should include:

- source file span,
- source construct type (`relation`, `global`, `piecewise`, `unknown_law`),
- user-visible name,
- generated internal name,
- reason for generation.

Update `explain.json` schema docs.

### 13.5 Tests

- estimate relation cardinalities,
- estimate derived relation candidates/filtered sizes,
- estimate global generated constraints,
- estimate piecewise auxiliaries,
- target check includes estimate,
- JSON schema stable snapshot tests.

### 13.6 Documentation

Update:

- `docs/CLI.md`,
- `docs/COMPILER.md`,
- `docs/BACKEND.md`,
- `docs/tutorials/03-compiling-running-and-reading-results.md`,
- `README.md` if the quickstart mentions artifacts/estimate,
- `docs/BACKEND_V1_LIMITS.md` with estimator-driven warnings.

---

## 14. Milestone 10: NP/Ising model regression suite

### 14.1 Goal

Add the 24 NP/Ising models as regression fixtures and language expressivity examples.

Folder:

```text
examples/np_ising_problems/
  README.md
  01_number_partitioning.qsol
  01_number_partitioning.qsol.toml
  02_graph_partitioning.qsol
  02_graph_partitioning.qsol.toml
  ...
  24_graph_isomorphism_optimization.qsol
  24_graph_isomorphism_optimization.qsol.toml
  test_smoke.py
  test_equivalence.py        # optional if exact comparisons are implemented
```

If the suite is too large for one example folder, use:

```text
examples/np_ising_problems/basic/
examples/np_ising_problems/graph/
examples/np_ising_problems/routing/
examples/np_ising_problems/tree_feedback/
```

### 14.2 Required model list

1. Number Partitioning
2. Graph Partitioning
3. Maximum Clique
4. Binary Integer Linear Programming
5. Minimum Exact Cover
6. Set Packing
7. Maximum Independent Set
8. Minimum Vertex Cover
9. Maximum Satisfiability
10. Minimum Maximal Matching
11. Set Cover
12. Knapsack with Integer Weights
13. Minimum Graph Coloring
14. Minimum Clique Cover
15. Job Sequencing with Integer Lengths
16. Hamiltonian Path as Optimization
17. Hamiltonian Cycle as Optimization
18. Traveling Salesman Problem
19. Degree-Constrained Minimum Spanning Tree
20. Steiner Tree
21. Directed Feedback Vertex Set
22. Undirected Feedback Vertex Set
23. Directed Feedback Edge Set
24. Graph Isomorphism as Optimization

### 14.3 Suite classification

Each model must be tagged in README:

- `stable`: expected to parse, check, estimate, build, and solve tiny scenario.
- `backend-diagnostic`: expected to parse/check/estimate but produce a targeted backend diagnostic.
- `prototype`: documents desired modeling surface but depends on a later feature.

No silent failures. Every model gets an expected status.

### 14.4 Tiny scenarios

Each model needs a minimal TOML instance. Keep sizes tiny:

- 3-5 vertices for graph models,
- 2-4 sets for set cover/packing,
- 2-4 jobs/machines for scheduling,
- 3 variables/2 clauses for MaxSAT,
- 3-4 cities for TSP.

### 14.5 Tests

Add smoke tests:

- parse all `.qsol`,
- check all `.qsol`,
- estimate all scenarios,
- build expected-stable tiny scenarios,
- assert expected diagnostics for diagnostic/prototype models.

Optional exact solve tests:

- exact sampler for stable tiny instances,
- compare objective values with brute-force Python reference.

### 14.6 Equivalence suite integration

If `test_equivalence.py` is added under `examples/np_ising_problems/`, ensure runtime is reasonable. The global `examples/run_equivalence_suite.py` will discover it automatically.

If the full suite is too slow, make `test_equivalence.py` run only a small stable subset and add a separate `test_smoke.py` for CI unit tests.

### 14.7 Documentation

Update:

- `examples/README.md`: add `np_ising_problems/` row.
- `examples/np_ising_problems/README.md`: explain suite, features, expected statuses, commands.
- `docs/README.md`: if this suite is useful as language stress-test docs.
- `docs/BACKEND_V1_LIMITS.md`: cite examples that intentionally trigger limitations.
- `docs/STDLIB.md`: link graph/route/global examples.

---

## 15. Documentation update matrix by feature

### 15.1 `README.md`

Update when:

- new CLI estimate behavior is user-facing,
- relation examples become part of quickstart,
- build/solve artifacts change,
- examples index changes significantly.

Expected vNext edits:

- mention `relation` as a core modeling construct after sets/params/finds,
- update quickstart if it uses a graph example,
- link to relation and graph tutorials.

### 15.2 `QSOL_reference.md`

Mandatory for every language-level change.

Add sections:

- Relations:
  - base relation declarations,
  - derived relation declarations,
  - tuple binders,
  - relation membership calls,
  - relation TOML schema,
  - static-only restrictions.
- Multi-generator comprehensions.
- Groundable aggregate bounds.
- Piecewise builtins.
- Graph/route/global constraints if any are language-level, otherwise link to stdlib.
- Diagnostics and backend limitation notes.

### 15.3 `docs/QSOL_SYNTAX.md`

Keep concise.

Add examples:

```qsol
relation Edge(u: V, v: V);
relation NonEdge(u: V, v: V) = pairs(u in V, v in V where u != v and not Edge(u, v));

sum(Cost[u, v] for u in V for v in V where Edge(u, v))
forall (u, v) in Edge: expr
minimize abs(expr)
minimize max(load[m] for m in Machines)
```

Add common syntax errors:

- wrong tuple binder arity,
- relation field typo,
- supplied derived relation in TOML,
- decision-dependent relation filter.

### 15.4 `docs/STDLIB.md`

Add sections:

- `stdlib.graph`,
- `stdlib.route`,
- `stdlib.global` or named modules for globals,
- relation-aware macro/helper patterns,
- migration from parallel params to relations.

Clarify which constructs are compiler builtins, not stdlib macros:

- `abs`,
- compiler-lowered `min`/`max` if implemented as builtins,
- generated graph globals if compiler-owned.

### 15.5 `docs/CLI.md`

Update for:

- estimator output schema,
- relation loading errors,
- explain output changes,
- target compatibility reports including relation/global summaries,
- any new flags such as `--explain-lowering` or `--estimate-threshold` if added.

### 15.6 `docs/COMPILER.md`

Update pipeline docs:

- relation parsing and resolving,
- static derived relation grounding,
- tuple binders in IR,
- global expansion phase placement,
- piecewise auxiliary generation,
- source-origin metadata.

### 15.7 `docs/BACKEND.md`

Update:

- CQM variable counts for scalar/relation/global auxiliaries,
- how static relations disappear before backend except through expanded constraints,
- generated auxiliary variable naming policy,
- backend artifact stats.

### 15.8 `docs/BACKEND_V1_LIMITS.md`

Update:

- relation constructs are source-level and static,
- multi-generator comprehensions can create large grounded expressions,
- route/TSP transition products may exceed quadratic unless helper introduces auxiliaries,
- piecewise supported/unsupported contexts,
- graph globals generated size caveats,
- explicit examples of `QSOL3001` with suggested rewrites.

### 15.9 `docs/TUTORIAL.md`

Update only if its guided introduction should expose relations. Recommended: include one relation example after `Subset`/`Mapping`, not before.

### 15.10 `docs/tutorials/01-first-program.md`

Probably minimal update. Keep beginner-focused. Only update if syntax or CLI outputs shown there change.

### 15.11 `docs/tutorials/02-writing-your-own-model.md`

Major update:

- add relation-based modeling,
- show multi-generator comprehensions,
- show relation scenario TOML,
- show backend-safe expression style.

### 15.12 `docs/tutorials/03-compiling-running-and-reading-results.md`

Update:

- relation TOML config example,
- `inspect estimate` relation fields,
- `explain.json` generated-source metadata,
- `run.json` if scalar/global outputs change,
- target diagnostics examples.

### 15.13 `docs/tutorials/04-custom-unknowns-functions-and-predicates.md`

Update if:

- relation types can be macro formals,
- graph/route helpers are implemented as custom unknowns,
- `Comp(...)` formals now support multi-generator args or relation binders.

### 15.14 `docs/CODEBASE.md`

Update when:

- AST/IR nodes for relations are added,
- grounding responsibilities change,
- estimator module changes,
- global expansion stage is added.

### 15.15 `docs/EXTENDING_QSOL.md`

Update if:

- stdlib module authoring supports relation formal types,
- custom unknowns can expose relation-aware views,
- macros can accept relation-valued or tuple-valued arguments.

### 15.16 `docs/README.md`

Update index links if new docs/tutorials are added:

- relation tutorial,
- graph tutorial,
- model-size estimation guide,
- NP/Ising suite guide.

---

## 16. Example update plan

### 16.1 Existing examples

#### `examples/tutorials/`

Add:

- `relation_set_packing.qsol`
- `relation_set_packing.qsol.toml`
- `relation_graph_independent_set.qsol`
- `relation_graph_independent_set.qsol.toml`
- `job_sequencing.qsol`
- `job_sequencing.qsol.toml`
- `number_partitioning_abs.qsol`
- `number_partitioning_abs.qsol.toml`

Update:

- `examples/tutorials/README.md`
- commands and scenario knobs.

#### `examples/min_bisection/`

Two options:

1. Preserve current endpoint-param example and add `min_bisection_relation.qsol` in same folder.
2. Create new `examples/min_bisection_relation/` folder.

Preferred: create new folder to avoid changing equivalence expectations for existing example.

#### `examples/partition_equal_sum/`

Keep existing example. Add a new abs-based variant after piecewise is implemented.

#### `examples/generic_bqm/`

Do not change unless estimator/backend stats output changes and docs need updating.

### 16.2 New top-level examples

Add only if stable and not too slow:

- `examples/relation_basics/`
- `examples/graph_relations/`
- `examples/np_ising_problems/`

Update `examples/README.md` for every new folder.

### 16.3 Example CI policy

Every new example folder should include at least one of:

- a README command that is exercised by docs/examples tests,
- a `test_equivalence.py` that the suite can discover,
- a unit/CLI test in `tests/cli/` or `tests/examples/`.

---

## 17. Test plan by stage

### 17.1 Parser tests

Location: `tests/parser/`

Add tests for:

- multi-generator comprehensions,
- tuple binders,
- relation declarations,
- derived relation declarations,
- relation membership calls,
- piecewise builtins parse,
- bad relation syntax,
- wrong tuple binder arity if parse-time detectable,
- optional record field access syntax.

### 17.2 Semantic tests

Location: `tests/sema/`

Add tests for:

- relation symbols,
- relation field set lookup,
- duplicate relation names,
- duplicate relation fields,
- relation membership type/arity,
- tuple binder scoping,
- static-only derived relation filters,
- aggregate-bound groundability,
- `Bool` in boolean contexts,
- `Bool` rejected in numeric contexts unless `indicator`.

### 17.3 Lowering tests

Location: `tests/lower/`

Add tests for:

- relation declarations in Kernel IR,
- tuple binder lowering,
- relation calls in IR,
- derived relation metadata,
- multi-generator comprehension IR,
- piecewise aux generation,
- global expansion source metadata.

### 17.4 Grounding tests

Location: `tests/backend/` or a new `tests/grounding/` if existing style allows.

Add tests for:

- canonical relation TOML,
- compact relation TOML if supported,
- invalid relation TOML diagnostics,
- derived relation materialization,
- no scenario data for derived relations,
- `size(Relation)`,
- relation membership evaluation,
- aggregate-bound evaluation over relations.

### 17.5 Backend/codegen tests

Location: `tests/backend/`

Add tests for:

- relation-iterated objective compiles,
- relation-iterated hard constraint compiles,
- relation membership in `where`,
- scalar aggregate-bound vars compile,
- piecewise-generated aux vars compile,
- route/global diagnostics for unsupported degree,
- generated variable naming deterministic.

### 17.6 Targeting/compatibility tests

Location: `tests/targeting/`

Add tests for:

- relation features reported as source-level/static,
- piecewise features report backend requirements,
- unsupported higher-degree after route/global lowering reports `QSOL3001` or new precise code,
- `targets check --estimate` includes relation/global estimate.

### 17.7 CLI tests

Location: `tests/cli/`

Add tests for:

- `inspect parse` on relation model,
- `inspect check` on relation model,
- `inspect lower` includes relation IR or lowered relation info,
- `inspect estimate --json` relation fields,
- `targets check --estimate`,
- scenario TOML relation errors displayed clearly.

### 17.8 Golden diagnostics

Location: `tests/golden/`

Add or update snapshots for:

- wrong relation arity,
- relation field typo,
- missing relation scenario data,
- element not in set,
- decision-dependent derived relation,
- unsupported piecewise context,
- backend degree too high with route/TSP.

### 17.9 Docs examples tests

Add a test that parses/checks every `.qsol` file referenced in docs/tutorials, if not already present.

At minimum:

```bash
uv run qsol inspect parse <file> --json
uv run qsol inspect check <file> --config <file>.toml --json
```

For selected examples:

```bash
uv run qsol targets check <file> --config <file>.toml --runtime local-dimod --estimate
uv run qsol solve <file> --config <file>.toml --runtime local-dimod --runtime-option sampler=exact
```

---

## 18. Diagnostics plan

### 18.1 Diagnostic families

Preserve existing families:

- `QSOL1xxx`: parse,
- `QSOL2xxx`: semantic/type/instance,
- `QSOL3xxx`: backend language-shape limitations,
- `QSOL4xxx`: CLI/targeting/plugin resolution/preparation,
- `QSOL5xxx`: runtime execution.

Suggested new codes:

- `QSOL23xx`: relation/type/arity semantic errors,
- `QSOL24xx`: groundability errors,
- `QSOL31xx`: piecewise lowering/backend-shape errors,
- `QSOL32xx`: global expansion/backend-shape errors,
- `QSOL42xx`: scenario relation materialization errors, if instance config errors currently live in `QSOL4xxx`.

Use actual existing code taxonomy if different. Do not invent codes inconsistently.

### 18.2 Diagnostic quality requirements

Every new diagnostic must include:

- source span when source-related,
- concise message,
- actionable help,
- expected/actual arity or type where relevant,
- candidate suggestions when a field/relation/set name is mistyped,
- backend target name for backend limitations,
- source construct origin for generated helper errors.

### 18.3 Examples

Wrong arity:

```text
QSOL23xx: relation `Edge` expects 2 arguments, got 3.
Help: `Edge` is declared as relation Edge(u: V, v: V).
```

Decision-dependent derived relation:

```text
QSOL24xx: derived relation `ActiveEdge` is not static.
Cause: filter references decision `Pick.has(u)`.
Help: derived relations may depend only on sets, params, static relations, and static expressions.
```

Piecewise unsupported:

```text
QSOL31xx: cannot lower `abs(expr) >= C` for backend `dimod-cqm-v1` without a disjunction.
Help: use `abs(expr) <= C`, minimize `abs(expr)`, or introduce an explicit bounded binary disjunction.
```

---

## 19. Backward compatibility requirements

Must remain valid:

```qsol
find S : Subset(A);
find M : Mapping(A -> B);
find P : Permutation(A);
find b : Bool;
find T : Int[0 .. size(A)];
sum(term for x in X)
all(term for x in X where cond else alt)
predicate atleast(k: Real, terms: Comp(Real)): Bool = terms >= k;
```

Must not change:

- existing example objective values,
- existing varmap labels unless an internal refactor explicitly requires it and docs/tests update accordingly,
- existing `run.json` core fields,
- existing `capability_report.json` fields unless versioned/extended compatibly,
- existing import resolution for `stdlib.*`.

If any backward-incompatible change is unavoidable, stop and ask for approval with a migration plan.

---

## 20. Suggested PR breakdown

### PR 1: baseline and tests

- Add baseline probes and xfail/failing relation tests.
- No behavior change.
- Docs: none or `docs/CODEBASE.md` note if test infrastructure changes.

### PR 2: multi-generator comprehensions

- Grammar/AST/type/lower/backend support.
- Docs: syntax/reference/tutorial updates.
- Examples: one tutorial example.

### PR 3: base relations and TOML loading

- `relation` declarations.
- Tuple binders.
- Membership calls.
- Scenario relation loading.
- Docs/tutorials/examples.

### PR 4: derived relations

- `pairs`/`filter` constructors.
- Static dependency validation.
- Estimator relation sizes.
- Docs/tutorials/examples.

### PR 5: aggregate bounds

- Groundability checker.
- Static aggregate bounds for `Int`.
- Job sequencing example.
- Docs/tutorials.

### PR 6: piecewise builtins

- `abs`, `min`, `max` safe lowering.
- Aux metadata.
- Number partitioning abs example.
- Docs/tutorials/backend limits.

### PR 7: graph stdlib

- `stdlib.graph` helpers.
- Relation graph examples.
- Docs/STDLIB/tutorials.

### PR 8: route helper

- `stdlib.route` helper.
- Hamiltonian/TSP examples with expected diagnostics if necessary.
- Docs/STDLIB/backend limits.

### PR 9: graph/order globals

- `acyclic_directed` first.
- `connected`/`tree` if flow infra is ready.
- Feedback/MST/Steiner examples.
- Docs/estimator updates.

### PR 10: NP/Ising suite and final docs pass

- 24 examples with tiny scenarios.
- Suite README and examples index.
- Full docs consistency sweep.
- Golden diagnostics and expected statuses.

---

## 21. Detailed file touch checklist

### Parser/AST

- `src/qsol/parse/grammar.lark`
- `src/qsol/parse/ast.py`
- `src/qsol/parse/ast_builder.py`
- `tests/parser/test_parser.py`

### Semantic model

- `src/qsol/sema/symbols.py`
- `src/qsol/sema/types.py`
- `src/qsol/sema/resolver.py`
- `src/qsol/sema/typecheck.py`
- `src/qsol/sema/validate.py`
- `tests/sema/`

### Lowering/IR

- `src/qsol/lower/ir.py`
- `src/qsol/lower/desugar.py`
- `src/qsol/lower/lower.py`
- `tests/lower/`

### Config/grounding

- `src/qsol/config/`
- `src/qsol/backend/instance.py`
- tests for config and instance materialization.

### Backend/targeting

- `src/qsol/backend/dimod_codegen.py`
- `src/qsol/targeting/compatibility.py`
- `src/qsol/targeting/types.py`
- `tests/backend/`
- `tests/targeting/`

### CLI/estimate/explain

- `src/qsol/cli.py`
- estimator module, existing or new,
- explain/capability report output code,
- `tests/cli/`.

### Standard library

- `src/qsol/stdlib/logic.qsol` if `indicator` or helpers change,
- `src/qsol/stdlib/graph.qsol` new,
- `src/qsol/stdlib/route.qsol` new,
- globals modules as needed,
- stdlib tests.

### Documentation

- `README.md`
- `QSOL_reference.md`
- `docs/README.md`
- `docs/QSOL_SYNTAX.md`
- `docs/STDLIB.md`
- `docs/CLI.md`
- `docs/COMPILER.md`
- `docs/BACKEND.md`
- `docs/BACKEND_V1_LIMITS.md`
- `docs/RUNTIMES.md` only if runtime behavior changes,
- `docs/TUTORIAL.md`
- `docs/tutorials/README.md`
- `docs/tutorials/01-first-program.md` if outputs/syntax there change,
- `docs/tutorials/02-writing-your-own-model.md`
- `docs/tutorials/03-compiling-running-and-reading-results.md`
- `docs/tutorials/04-custom-unknowns-functions-and-predicates.md`
- `docs/CODEBASE.md`
- `docs/EXTENDING_QSOL.md`

### Examples

- `examples/README.md`
- `examples/tutorials/README.md`
- new tutorial models and TOML files,
- optional relation-specific top-level examples,
- `examples/np_ising_problems/`
- `examples/run_equivalence_suite.py` only if discovery/timeout behavior needs adjustment. Avoid changes unless necessary.

---

## 22. Acceptance criteria for vNext

vNext is complete only when all are true:

1. Existing examples still pass their previous tests.
2. Existing tutorials still parse/check and command snippets are current.
3. Multi-generator comprehensions work in parse, sema, lower, ground, estimate, and backend.
4. Static relation declarations work with TOML loading.
5. Tuple binders work in quantifiers and comprehensions.
6. Relation membership calls typecheck and ground correctly.
7. Derived relations work for Cartesian product, filtered product, and graph nonedge/complement use cases.
8. `Int` bounds support static aggregate expressions.
9. `abs` works for minimization and `abs(e) <= C` constraints.
10. `min`/`max` work in at least the conservative objective contexts specified above.
11. `stdlib.graph` can express independent set, clique, vertex cover, graph coloring, and min bisection without parallel endpoint params.
12. Route helper can express Hamiltonian path/cycle source models; backend issues, if any, are precise diagnostics.
13. At least `acyclic_directed` is implemented as a transparent global or documented template.
14. Estimator reports relation sizes, derived relation sizes, generated aux variables, and global-generated constraints.
15. `docs/BACKEND_V1_LIMITS.md` clearly documents remaining unsupported shapes.
16. The 24 NP/Ising models exist as examples/fixtures with expected statuses and tiny scenarios.
17. Every changed behavior has docs and tests according to `AGENTS.md`.
18. All mandatory gates pass.
19. Completion report includes the repository DoD checklist.
20. Vision coherence rubric is answered explicitly.

---

## 23. Deferred items

Do not include these in vNext unless all core milestones are complete:

- dynamic decision-dependent relations,
- general relation-valued unknowns,
- unrestricted `Subset(Relation)` if it complicates core typing; use indexed `Bool[Relation]` first,
- full core `graph` declaration syntax,
- unrestricted automatic quadratization,
- lexicographic objectives,
- arbitrary record values outside static relation binders,
- generic imperative scripting features,
- silent Bool-to-numeric coercion.

---

## 24. Final implementation notes for coding agent

- Keep relation support static and boring first. That is the main unlock.
- Prefer exact rejection with high-quality diagnostics over clever but opaque lowering.
- Preserve existing `Subset`, `Mapping`, scalar `Bool`, scalar `Int`, and `Range` behavior.
- Update docs in the same PR as behavior changes.
- Add examples only when they can be parsed/checked and have explicit expected backend status.
- Make generated constructs inspectable in `explain.json` and estimator output.
- Do not compress multiple milestones into one large unreviewable patch.
