# QSOL Language Reference (Compiler v0.1.0)

QSOL is a small, highly declarative modeling language for expressing combinatorial optimization problems at a **very high level**. Users describe:
- **Finite sets** and **parameters** (inputs),
- **Unknown structures** (decisions) chosen by the solver,
- **Hard laws** (`must`) and **soft intent** (`should`, `nice`),
- Optional goals (`minimize`, `maximize`).

The **core** is intentionally minimal: the only *primitive unknowns* are:

- `Subset(X)` — choose a subset of `X`
- `Mapping(A -> B)` — choose a total function from `A` to `B`

Everything else—permutations, injections, partitions, tours, matchings, scheduling objects—is built as **libraries written in SOL itself**.

---

This reference describes the language accepted by the current QSOL parser/typechecker and the subset supported by backend v1 (`dimod-cqm-v1`).

## 1. Versioning and Compatibility

QSOL currently has two practical compatibility layers:

- Parse/typecheck layer: what the grammar and semantic passes accept.
- Backend layer: what selected targets can lower/run without `QSOL3001` or target capability failures.

This document calls out both layers explicitly so you can write models that are valid and compilable.

## 2. Rationale

### 2.1 Why "Unknown Structures" Instead of Variables

Most combinatorial optimization problems fall into a small number of structural patterns:

- **Pick a subset of items** — which tasks to schedule, which vertices to include, which items to pack.
- **Assign each thing to exactly one option** — color each vertex, assign each task to a worker, route each vehicle.

Traditional QUBO modeling forces you to work at a low level: declare individual boolean variables, write boilerplate one-hot constraints by hand, and tune penalty weights to balance feasibility against objectives. This is error-prone, repetitive, and obscures the modeler's actual intent.

QSOL makes these patterns first-class **unknown structures**. Instead of declaring `x_i ∈ {0,1}` and manually encoding what those bits mean, you write:

```qsol
find S : Subset(V);          // "pick some vertices"
find Color : Mapping(V -> C); // "assign each vertex a color"
```

The compiler handles the variable encoding, structural constraints (e.g., one-hot rows for `Mapping`), and penalty generation automatically.

### 2.2 Why a Minimal Core with `Subset` and `Mapping`

QSOL's two primitive unknowns — `Subset` and `Mapping` — form a minimal but sufficient basis:

- **Easier to implement correctly**: fewer primitives mean fewer backend encoding paths to test and maintain.
- **Easier to reason about**: every model reduces to subsets and/or mappings; users learn two concepts, not dozens.
- **Extensible in user space**: the `unknown` definition mechanism lets users (and the standard library) build richer types — `InjectiveMapping`, `Permutation`, `BijectiveMapping` — from these two primitives without modifying the compiler.
- **Backend-portable**: targeting a new solver backend only requires encoding `Subset` and `Mapping`; all higher-level types desugar to these before codegen.

## 3. Concepts at a Glance

A QSOL program declares a combinatorial optimization **problem** in four layers:

### 3.1 Sets and Parameters (Inputs)

Sets define the finite domains of the problem. Parameters carry known data provided at solve time.

```qsol
set Workers;
set Tasks;

param Cost[Workers, Tasks] : Real;
param Capacity : Int[0 .. 100];
```

### 3.2 Unknowns (Decisions)

Unknowns are the structures the solver must determine. The two primitives are `Subset` (pick a subset) and `Mapping` (assign each element of one set to an element of another).

```qsol
find S : Subset(Workers);          // which workers are selected?
find Assign : Mapping(Tasks -> Workers); // who does each task?
```

Standard library types such as `InjectiveMapping`, `Permutation`, and `BijectiveMapping` provide richer structure on top of these primitives.

### 3.3 Laws and Intent (Constraints)

Constraints express feasibility requirements and preferences:

| Keyword | Meaning | Weight |
|---------|---------|--------|
| `must`  | Hard constraint — must hold in every valid solution | ∞ (infeasible if violated) |
| `should` | Soft constraint — preferred to be true | 10.0 |
| `nice`  | Soft constraint — lower-priority preference | 1.0 |

```qsol
must forall w in Workers:
  sum(if Assign.is(t, w) then 1 else 0 for t in Tasks) <= Capacity;

should forall t in Tasks: Assign.is(t, preferred[t]);
nice S.has(backup_worker);
```

### 3.4 Objectives

Objectives direct the solver toward better solutions:

```qsol
minimize sum(
  sum(if Assign.is(t, w) then Cost[w, t] else 0 for w in Workers)
  for t in Tasks
);
```

`maximize expr` is equivalent to `minimize -expr`.

## 4. Program Structure

A QSOL file may contain top-level `use`, `unknown`, `predicate`, `function`, and `problem` definitions.

```qsol
problem Name {
  set A;
  param weight[A] : Real = 1;
  find S : Subset(A);

  must forall x in A: S.has(x) or not S.has(x);
  minimize sum(if S.has(x) then weight[x] else 0 for x in A);
}
```

### 4.1 Statement Terminator

- Statements are semicolon-terminated (`;`).
- Newlines are ignored by the grammar.

### 4.2 Comments

```qsol
// single line comment
/* block comment */
```

### 4.3 Imports (`use`)

QSOL uses one module-style import form for both stdlib and user libraries:

```qsol
use stdlib.permutation;
use mylib.graph.unknowns;
```

Rules:
- Module grammar: `NAME ("." NAME)*`
- Path mapping: `a.b.c -> a/b/c.qsol`
- `stdlib.*` is reserved and always resolves to packaged modules under `src/qsol/stdlib/`
- Non-stdlib modules resolve in order:
  1. importing file directory
  2. process current working directory
- Quoted file imports (for example `use "x.qsol";`) are not supported
- Import loading is recursive with stable de-duplication and cycle detection
- Imported modules may contain only `use`, `unknown`, `predicate`, and `function` top-level items (`problem` blocks are rejected in imported modules)

## 5. Declarations

### 5.1 Sets

```qsol
set Workers;
set Tasks;
```

Sets are finite domains whose concrete elements are provided by the selected config scenario.

### 5.2 Parameters

```qsol
param Alpha : Real;
param K : Int[1 .. 64] = 3;
param Cost[Workers,Tasks] : Real;
param Link[Workers,Tasks] : Bool = false;
param StartNode[Tasks] : Elem(Workers);
```

Supported parameter value types:
- `Bool`
- `Real`
- `Int[lo .. hi]`
- `Elem(SetName)` (an element drawn from a declared set)

Indexing:
- `param P[A,B] : Real;` means `P` is a nested map indexed first by `A`, then `B`.

Default values:
- Scalar defaults are allowed for all scalar types.
- Indexed params may also have scalar defaults; scenario expansion uses declared set elements.
- `Elem(SetName)` params do not support defaults.

Reading params in expressions:
- Indexed params can be read as `Cost[w, t]` (bracket syntax).
- Indexed params must use bracket syntax; `Cost(w, t)` is rejected with `QSOL2101`.
- Set-valued params can be used as set elements (for example `Pick.has(StartNode[t])`).
- Scalar params must be referenced as bare names (for example `C`, `Flag`, `Start`).
- Scalar call/index forms such as `C[]` and `Flag()` are rejected with `QSOL2101`.
- `size(SetName)` returns set cardinality and is constant-folded after scenario loading.

### 5.3 Unknowns

Primitive unknowns in backend v1:

```qsol
find S : Subset(A);
find F : Mapping(A -> B);
```

- `Subset(A)`: one binary decision variable per `a in A`
- `Mapping(A -> B)`: one binary variable per `(a,b)` with implicit `exactly one b` per row `a`

### 5.4 User-Defined Unknown Types

Grammar supports defining custom unknown types:

```qsol
unknown MyType(A) {
  rep {
    inner : Subset(A);
  }
  laws {
    must true;
  }
  view {
    predicate has(x: Elem(A)): Bool = inner.has(x);
  }
}
```

Current status:
- Parse/typecheck: supported.
- Frontend compilation for custom unknown instantiation in `find`: supported.
- Backend remains primitive-focused (`Subset`/`Mapping`); custom unknowns are elaborated in frontend into primitive finds plus generated constraints before resolver/typecheck/lower/backend stages.

See [§15. Extending QSOL: User-Defined Unknown Types](#15-extending-qsol-user-defined-unknown-types) for a detailed guide.

### 5.5 Predicates and Functions (Typed Macros)

Top-level reusable macros use typed declarations:

```qsol
predicate iff(a: Bool, b: Bool): Bool = a and b or not a and not b;
function indicator(b: Bool): Real = if b then 1 else 0;
```

Unknown `view` members use the same declaration style:

```qsol
view {
  predicate has(x: Elem(A)): Bool = inner.has(x);
  function score(x: Elem(A)): Real = if inner.has(x) then 1 else 0;
}
```

Rules:
- `predicate` return type is always `Bool`.
- `function` return type is `Real` in the current release.
- Macro formals are explicitly typed: `Bool`, `Real`, `Elem(SetName)`, `Comp(Bool)`, `Comp(Real)`.
- `Comp(...)` formals accept comprehension-style call arguments (`term for x in X where ... else ...`).
- Variadic formals (`...`) are not supported in this release.
- Macro calls can compose (predicate/function bodies may call other predicates/functions).
- All macro calls are expanded in frontend elaboration before lowering/backend stages.

## 6. Expressions

QSOL has boolean and numeric expressions.

### 6.1 Boolean Expressions

Operators and forms:
- `not E`
- `E and F`
- `E or F`
- `E => F`
- comparisons: `=`, `!=`, `<`, `<=`, `>`, `>=`
- quantifiers: `forall x in X: E`, `exists x in X: E`
- aggregates: `any(...)`, `all(...)`
- method calls (`S.has(x)`, `F.is(a,b)`)
- macro/function calls (`predicateName(x)`, `functionName(x)`)

### 6.2 Numeric Expressions

Operators and forms:
- `+`, `-`, `*`, `/`
- unary `-E`
- conditional: `if cond then A else B`
- aggregates: `sum(...)`, `count(...)`
- builtin set cardinality: `size(SetName)` (numeric)
- numeric macro/function calls (for example `indicator(S.has(x))`)
- parameter access:
  - indexed style: `Cost[i,j]` (numeric indexed params)
  - indexed params must use brackets (for example `Cost[i,j]`, not `Cost(i,j)`)
  - scalar style: `C` (bare scalar params)

### 6.3 Operator Precedence (high to low)

1. Unary: `not`, unary `-`
2. Multiplicative: `*`, `/`
3. Additive: `+`, `-`
4. Comparisons: `=`, `!=`, `<`, `<=`, `>`, `>=`
5. `and`
6. `or`
7. `=>`

Use parentheses for clarity in complex formulas.

## 7. Quantifiers and Aggregates

### 7.1 Quantifiers

```qsol
forall x in A: body
exists y in B: body
```

### 7.2 Aggregates and Comprehensions

General comprehension style:

```qsol
agg(term for x in X where predicate else fallback)
```

`where` and `else` are optional.

Each comprehension supports a single `for` clause. For multiple iteration variables, use nested comprehensions (e.g., nested `sum` calls).

Comprehension-style call arguments:

```qsol
predicate atleast(k: Real, terms: Comp(Real)): Bool = terms >= k;
must atleast(1, S.has(x) for x in X where cond else false);
```

#### Numeric aggregates

```qsol
sum(expr for x in X)
sum(expr for x in X where cond)
sum(expr for x in X where cond else alt)

count(x for x in X)
count(x for x in X where cond)
count(x in X)
count(x in X where cond)
```

#### Boolean aggregates

```qsol
any(expr for x in X)
any(expr for x in X where cond)
any(expr for x in X where cond else alt)

all(expr for x in X)
all(expr for x in X where cond)
all(expr for x in X where cond else alt)
```

## 8. Constraints and Objectives

### 8.1 Constraints

```qsol
must   bool_expr;
should bool_expr;
nice   bool_expr;
```

Guarded form:

```qsol
must expr if cond;
```

Desugars to implication:

```qsol
must (cond => expr);
```

### 8.2 Objectives

```qsol
minimize numeric_expr;
maximize numeric_expr;
```

Backend interpretation:
- `maximize E` is converted to minimizing `-E`.
- Soft constraints contribute penalties into objective:
  - `should`: weight 10.0
  - `nice`: weight 1.0

## 9. Desugaring Rules

Desugaring is applied before lowering/codegen.

### 9.1 Guards

- `must phi if c` -> `must (c => phi)`
- `should phi if c` -> `should (c => phi)`
- `nice phi if c` -> `nice (c => phi)`

### 9.2 `count`

- `count(x for x in X where c)` -> `sum(1 for x in X where c)`
- `count(x in X where c)` -> `sum(1 for x in X where c)`

### 9.3 `sum` with filters

- `sum(t for x in X where c)` -> `sum(if c then t else 0 for x in X)`
- `sum(t for x in X where c else e)` -> `sum(if c then t else e for x in X)`

### 9.4 `any` and `all`

- `any(...)` desugars to `exists ...`
- `all(...)` desugars to `forall ...`

### 9.5 Numeric conditional

- `if c then a else b` is lowered as indicator arithmetic (`c*a + (1-c)*b`) in backend numeric encoding.

## 10. Semantics

### 10.1 Solutions

A **solution** is a concrete assignment of values to every `find` unknown declared in the problem:

- For `find S : Subset(X)`, the solver picks which elements of `X` are included in `S`.
- For `find f : Mapping(A -> B)`, the solver picks exactly one element of `B` for each element of `A`.

A solution is **feasible** if all `must` constraints evaluate to true. Among feasible solutions, the solver seeks one that minimizes (or maximizes) the declared objective, while also minimizing soft-constraint violation penalties.

### 10.2 Primitive Unknown APIs

Each primitive unknown type exposes a single boolean method:

| Unknown type | Method | Semantics |
|---|---|---|
| `Subset(X)` | `S.has(x)` → `Bool` | True iff element `x` is included in the chosen subset |
| `Mapping(A -> B)` | `f.is(a, b)` → `Bool` | True iff the mapping sends `a` to `b` |

These methods are the fundamental building blocks for writing constraints and objectives.

### 10.3 Built-in Laws

`Mapping(A -> B)` carries an implicit structural invariant: the mapping is **total and single-valued**. For each `a ∈ A`, exactly one `b ∈ B` satisfies `f.is(a, b)`. Users never write this constraint — it is enforced automatically by the compiler via one-hot encoding.

`Subset(X)` has no implicit laws beyond the binary nature of membership.

### 10.4 Soft Constraint Interpretation

| Keyword | Effect when expression is false | Weight |
|---------|-------------------------------|--------|
| `should` | Cost increases by weight × violation | 10.0 |
| `nice` | Cost increases by weight × violation | 1.0 |

Soft constraints are accumulated into the objective as penalty terms. A model with only soft constraints (no `must`) will always produce a feasible solution — the solver simply minimizes total penalty.

`maximize E` is equivalent to `minimize -E`. The final objective seen by the solver is:

$$\text{objective} = \text{minimize\_expr} + \sum_i w_i \cdot \text{penalty}_i$$

where $w_i$ is the weight of the $i$-th soft constraint.

## 11. Compilation Intuition

This section provides a conceptual overview of how QSOL compiles a problem to a QUBO/CQM model. The actual backend is `dimod-cqm-v1`.

### 11.1 Lower Unknowns

- **`Subset(X)`** → one binary variable $x_i$ per element of $X$. The variable is 1 when the element is in the subset, 0 otherwise.
- **`Mapping(A → B)`** → a matrix of binary variables $m_{a,b}$ for each $(a, b) \in A \times B$, plus one-hot row constraints ensuring $\sum_b m_{a,b} = 1$ for each $a$.

User-defined unknown types and top-level/view predicate/function macros are elaborated before this step: unknown `rep` fields become primitive unknowns, unknown `laws` become additional constraints, and macro calls are expanded into core expressions.

### 11.2 Ground Quantifiers

`forall`, `exists`, `sum`, and `count` are expanded over their respective finite sets using the concrete scenario data. For example, `forall v in V: ...` with `V = {v1, v2, v3}` generates three concrete constraint instances.

### 11.3 Desugar

Surface-level syntactic sugar is rewritten into a smaller kernel:

- Guards → implication: `must φ if c` → `must (c ⇒ φ)`
- `count(...)` → `sum(1 for ...)`
- `any(...)` → `exists ...`
- `all(...)` → `forall ...`
- `sum(expr for x in X where c)` → `sum(if c then expr else 0 for x in X)`

### 11.4 Lower Constraints

- **Hard boolean constraints** become penalty terms or CQM sense constraints that are zero only when satisfied.
- **Comparison constraints** (e.g., `lhs <= rhs`) use CQM sense directly.
- **Boolean operators** (`and`, `or`, `not`, `=>`) in hard constraints are encoded via standard QUBO penalty gadgets.

### 11.5 Assemble Soft Preferences

Soft constraints are converted to penalty expressions and added to the objective with their weight bucket:

- `should` violations are penalized at weight 10.0.
- `nice` violations are penalized at weight 1.0.

### 11.6 Emit

The final compilation step produces:

- A **CQM** (Constrained Quadratic Model) or **BQM** (Binary Quadratic Model) via the `dimod` backend.
- A **variable-to-meaning decoder map** that translates solver output back to the problem's domain (e.g., which elements are in the subset, which mappings were chosen).
- Artifact files: `model.cqm`, `model.bqm`, export files, log, and optionally `explain` data.

> **Note**: This is a conceptual overview. For the precise compilation pipeline stages, see `docs/CODEBASE.md`.

## 12. Config TOML and Scenarios

CLI `targets check`, `build`, and `solve` consume a TOML config file (`*.qsol.toml`) with one or more named scenarios.

Required root shape:

```toml
schema_version = "1"

[entrypoint]
scenario = "baseline" # optional single scenario selector
# scenarios = ["baseline", "stress"] # optional repeated selector
# all_scenarios = true # optional equivalent of --all-scenarios
combine_mode = "intersection" # intersection|union
failure_policy = "run-all-fail" # run-all-fail|fail-fast|best-effort
out = "outdir/model"
format = "qubo"
runtime = "local-dimod"
backend = "dimod-cqm-v1"
plugins = []
runtime_options = { sampler = "exact", num_reads = 200 }
solutions = 3
energy_min = -10
energy_max = 0

[scenarios.baseline]
problem = "ProblemName"

[scenarios.baseline.sets]
A = ["a1", "a2"]
B = ["b1"]

[scenarios.baseline.params]
K = 3

[scenarios.baseline.params.Cost]
a1 = { b1 = 5.0 }
a2 = { b1 = 7.0 }

[scenarios.baseline.execution]
runtime = "local-dimod"
plugins = ["my_pkg.plugins:plugin_bundle"]

[scenarios.baseline.solve]
solutions = 5
energy_max = 1
```

Notes:
- `schema_version` must currently be `"1"`.
- `scenarios` must declare at least one scenario.
- `entrypoint` is optional and provides CLI-equivalent defaults.
- Each scenario materializes to the historical instance payload shape (`problem`, `sets`, `params`, optional `execution`) before grounding.
- Scenario `execution` values override `entrypoint` execution values, which override legacy `defaults.execution`.
- Scenario `solve` values override `entrypoint` solve defaults, and CLI solve flags override both.
- CLI backend defaults to `dimod-cqm-v1`.
- built-in runtime ids:
  - `local-dimod`
  - `qiskit`
- built-in backend ids:
  - `dimod-cqm-v1`

Config auto-discovery when `--config` is omitted:
- Search only `*.qsol.toml` in the model directory.
- If one config exists, use it.
- If multiple configs exist, use `<model>.qsol.toml` when present.
- Otherwise fail with `QSOL4002`.

Scenario selection precedence:
1. CLI `--all-scenarios`
2. CLI `--scenario <name>` (repeatable)
3. Config `entrypoint.all_scenarios`
4. Config `entrypoint.scenario(s)`
5. Config `selection.mode` (legacy)
6. Config `selection.default_scenario` (legacy)
7. If exactly one scenario exists, use it

If unresolved, fail with `QSOL4001`.

Runtime selection precedence:
1. CLI `--runtime`
2. Scenario `execution.runtime`
3. Config `entrypoint.runtime`
4. Legacy `defaults.execution.runtime`

If unresolved, fail with `QSOL4006`.

Plugin loading order for `targets check`/`build`/`solve`:
1. built-ins
2. installed entry points (`qsol.backends`, `qsol.runtimes`)
3. config `execution.plugins` (scenario -> `entrypoint` -> legacy defaults)
4. CLI `--plugin`

Config and CLI plugin specs are merged in order and deduplicated by exact string.

### 12.1 Qiskit Runtime Options

The built-in `qiskit` runtime is compatible with backend `dimod-cqm-v1` and supports:

- `algorithm=qaoa|numpy` (default: `qaoa`)
- `fake_backend=<FakeBackendClass>` (default: `FakeManilaV2`; used by `qaoa`)
- `shots=<int>` (default: `1024`, QAOA only)
- `reps=<int>` (default: `1`, QAOA only)
- `maxiter=<int>` (default: `100`, QAOA only)
- `seed=<int>` (optional)
- `optimization_level=<int>` (default: `1`, QAOA transpilation)
- `solutions`, `energy_min`, `energy_max` (same solve contract as other runtimes)

For `algorithm=qaoa`, QSOL auto-wires backend transpilation using
`pass_manager`/`transpiler` based on the installed Qiskit package variant.

When `algorithm=qaoa`, `solve` exports OpenQASM 3 to `qaoa.qasm` in the selected output directory and reports the path in `run.json` extensions.

## 13. Backend v1 Support Matrix

The language accepted by parser/typechecker is broader than backend v1 codegen.

### 13.1 Fully supported (safe patterns)

- `find` with `Subset`, `Mapping`, and user-defined unknown kinds that elaborate to primitive finds
- hard numeric comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) where both sides lower to numeric backend expressions
- boolean-context comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) are supported in objectives/soft expressions via indicator encoding
- hard constraints as conjunctions of supported atoms/comparisons
- hard `not <atom>`
- hard implications where both sides are atom-like
- `sum`, arithmetic, `if-then-else`, numeric param lookups
- soft constraints (`should`, `nice`) over bool formulas built from atom-like terms and boolean operators; these are soft-only and do not add hard feasibility constraints
- objectives over supported numeric expressions

### 13.2 Known unsupported/partial areas

- many template-style function calls (for example `exactly_one(...)`) are not backend primitives in v1
- some boolean expression shapes may parse/typecheck but fail backend lowering with `QSOL3001`
- backend quantifier handling is expansion-based; use quantified forms carefully and verify generated behavior on your problem

Compare tolerance notes:
- Boolean-context compare encoding uses a fixed epsilon `1e-6`.
- `<` is interpreted as `lhs - rhs <= -1e-6`; `<=` as `lhs - rhs <= +1e-6`.
- `>` is interpreted as `lhs - rhs >= +1e-6`; `>=` as `lhs - rhs >= -1e-6`.
- `=` is interpreted as inside `[-1e-6, +1e-6]`; `!=` as outside that band.
- At exact tolerance boundaries, truth value is intentionally indeterminate.

Practical rule: run `qsol targets check` early; treat `QSOL3001`/`QSOL4010` as signals that model syntax is valid but selected target support is incomplete for that shape.

## 14. Diagnostics

Common diagnostic codes:

- `QSOL1001`: parse error
- `QSOL2001`: unknown identifier/set/unknown type reference
- `QSOL2002`: duplicate declaration in scope
- `QSOL2101`: type rule violation
- `QSOL2201`: scenario data or indexing/shape issue
- `QSOL3001`: unsupported backend shape or validation/backend limitation
- `QSOL4002`: missing/ambiguous inferred config file
- `QSOL4003`: model or payload file read failure
- `QSOL4004`: config TOML load/validation failure before compilation
- `QSOL4005`: missing expected artifacts or target outputs
- `QSOL4006`: runtime selection unresolved
- `QSOL4007`: unknown runtime/backend id
- `QSOL4008`: incompatible runtime/backend pair
- `QSOL4009`: plugin load/registration failure
- `QSOL4010`: unsupported required capability for selected target
- `QSOL5001`: runtime execution failure
- `QSOL5002`: runtime policy/output contract failure

CLI diagnostics are rendered in rustc-style format by default:

- header: `error[CODE]: message`
- location: `--> file:line:col`
- source excerpt with highlighted spans
- contextual `= note:` and `= help:` hints
- final summary with error/warning/info totals

Use CLI commands progressively:
- `inspect parse` to validate syntax
- `inspect check` to validate semantics/types
- `inspect lower` to inspect normalized IR
- `targets check` to validate concrete target support on model+scenario
- `build` to export artifacts for selected runtime (backend is implicit)
- `solve` to execute selected runtime (backend is implicit)

## 15. Extending QSOL: User-Defined Unknown Types

QSOL's `unknown` definition mechanism allows users to create custom unknown types that compose the two primitives (`Subset` and `Mapping`) with additional laws and a clean public API.

### 15.1 Structure of an `unknown` Definition

An `unknown` block has three sections:

```qsol
unknown TypeName(A, B, ...) {
  rep { ... }
  laws { ... }
  view { ... }
}
```

- **`rep` (representation)**: Declares the internal unknown fields that implement this type. Each field must be a primitive (`Subset`/`Mapping`) or another user-defined unknown type.
- **`laws` (invariants)**: Declares `must` constraints that are always enforced whenever this type is instantiated. These encode the structural properties that distinguish this type from a plain `Mapping` or `Subset`.
- **`view` (public API)**: Declares `predicate` and/or `function` definitions that form the interface users interact with. Code outside the `unknown` block can only access the type through its `view` members.

During frontend compilation, each `find x : MyType(...)` is elaborated: the `rep` fields become primitive `find` declarations, the `laws` become additional `must` constraints, and the `view` members become available as methods on `x`.

### 15.2 Example: `InjectiveMapping`

An injective mapping (one-to-one function) from `A` to `B` ensures no two elements of `A` map to the same element of `B`.

From `src/qsol/stdlib/injective_mapping.qsol`:

```qsol
unknown InjectiveMapping(A, B) {
  rep {
    f : Mapping(A -> B);
  }
  laws {
    must forall b in B: count(a for a in A where f.is(a, b)) <= 1;
  }
  view {
    predicate is(a: Elem(A), b: Elem(B)): Bool = f.is(a, b);
  }
}
```

- **`rep`**: Uses a plain `Mapping(A -> B)` as its internal representation.
- **`laws`**: For each element `b` of the codomain, at most one element of `A` maps to it. This is the injectivity constraint.
- **`view`**: Exposes `is(a, b)` so callers interact with it the same way they would with a `Mapping`.

### 15.3 Example: `SurjectiveMapping`

A surjective mapping (onto function) ensures every element of `B` is mapped to by at least one element of `A`.

From `src/qsol/stdlib/surjective_mapping.qsol`:

```qsol
unknown SurjectiveMapping(A, B) {
  rep {
    f : Mapping(A -> B);
  }
  laws {
    must forall b in B: count(a for a in A where f.is(a, b)) >= 1;
  }
  view {
    predicate is(a: Elem(A), b: Elem(B)): Bool = f.is(a, b);
  }
}
```

### 15.4 Example: `BijectiveMapping`

A bijective mapping is both injective and surjective. Rather than duplicating constraints, it composes the two:

From `src/qsol/stdlib/bijective_mapping.qsol`:

```qsol
use stdlib.injective_mapping;
use stdlib.surjective_mapping;

unknown BijectiveMapping(A, B) {
  rep {
    inj : InjectiveMapping(A, B);
    sur : SurjectiveMapping(A, B);
  }
  laws {
    must forall a in A: forall b in B: inj.is(a, b) = sur.is(a, b);
  }
  view {
    predicate is(a: Elem(A), b: Elem(B)): Bool = inj.is(a, b);
  }
}
```

- **`rep`**: Two composed unknown types — an `InjectiveMapping` and a `SurjectiveMapping`.
- **`laws`**: The two internal mappings must agree on every pair, ensuring a single consistent bijection.

### 15.5 Example: `Permutation`

A permutation of set `A` is a bijective mapping from `A` to itself:

From `src/qsol/stdlib/permutation.qsol`:

```qsol
use stdlib.bijective_mapping;

unknown Permutation(A) {
  rep {
    bij : BijectiveMapping(A, A);
  }
  view {
    predicate is(a: Elem(A), b: Elem(A)): Bool = bij.is(a, b);
  }
}
```

Note that `Permutation` needs no `laws` block — all structural invariants are inherited from `BijectiveMapping`, which in turn inherits from `InjectiveMapping` and `SurjectiveMapping`.

### 15.6 How to Create Your Own Unknown Type

Follow these steps to define a custom unknown type:

1. **Choose a representation** using `Subset` and/or `Mapping` (or existing user-defined types) in the `rep` block. Think about what binary decisions your type encodes.

2. **Encode invariants** as `must` constraints in the `laws` block. These should capture the structural properties that always hold, independent of any specific problem.

3. **Expose a clean API** via `view` predicates and/or functions. Users of your type will only interact through these members, so design them to be intuitive and hide internal representation details.

Example — a type that selects exactly $k$ elements from a set:

```qsol
unknown ExactSubset(X, k) {
  rep {
    inner : Subset(X);
  }
  laws {
    must count(x in X where inner.has(x)) = k;
  }
  view {
    predicate has(x: Elem(X)): Bool = inner.has(x);
  }
}
```

## 16. Workflow — How to Write a QSOL Program

### Step 1: Identify Sets (Entities)

Determine the finite domains in your problem — tasks, workers, cities, vertices, edges, time slots, colors, etc. Each becomes a `set` declaration.

```qsol
set Cities;
set Routes;
```

### Step 2: Declare Parameters (Known Data)

Define the data that is known before solving — costs, distances, capacities, adjacency, weights. Use appropriate types (`Real`, `Int[lo..hi]`, `Bool`, `Elem(SetName)`).

```qsol
param Distance[Cities, Cities] : Real;
param MaxRoutes : Int[1 .. 100];
```

### Step 3: Find Unknown Structures

Choose the right unknown type for each decision:

- **"Which items to pick?"** → `Subset(X)`
- **"Assign each X to a Y?"** → `Mapping(X -> Y)`
- **"One-to-one assignment?"** → `InjectiveMapping(X, Y)` (via `use stdlib.injective_mapping;`)
- **"Permutation/ordering?"** → `Permutation(X)` (via `use stdlib.permutation;`)

```qsol
find Tour : Permutation(Cities);
```

### Step 4: Write `must` Laws (Feasibility)

Express hard constraints that every valid solution must satisfy.

```qsol
must forall c in Cities:
  sum(if Tour.is(c, d) then Distance[c, d] else 0 for d in Cities) <= MaxRoutes;
```

### Step 5: Write `should`/`nice` Intent (Preferences)

Express soft constraints for solution quality preferences.

```qsol
should Tour.is(home, first_stop);  // prefer starting from home
nice Tour.is(hub, second_stop);    // mildly prefer hub as second stop
```

### Step 6: Add `minimize`/`maximize` Goals

Define the objective to optimize.

```qsol
minimize sum(
  sum(if Tour.is(c, d) then Distance[c, d] else 0 for d in Cities)
  for c in Cities
);
```

### Step 7: Write Config TOML with Scenarios

Create a `*.qsol.toml` file with concrete data for each scenario.

```toml
schema_version = "1"

[entrypoint]
scenario = "small"
runtime = "local-dimod"

[scenarios.small]
problem = "MyProblem"

[scenarios.small.sets]
Cities = ["A", "B", "C"]

[scenarios.small.params.Distance]
A = { A = 0, B = 10, C = 20 }
B = { A = 10, B = 0, C = 15 }
C = { A = 20, B = 15, C = 0 }
```

### Step 8: Compile → Solve → Decode

Use the CLI to progressively validate and solve:

```bash
# Validate syntax and types
uv run qsol inspect check my_model.qsol

# Verify target support with scenario data
uv run qsol targets check my_model.qsol --config my_model.qsol.toml --runtime local-dimod

# Build artifacts
uv run qsol build my_model.qsol --config my_model.qsol.toml --runtime local-dimod --out outdir

# Solve and decode results
uv run qsol solve my_model.qsol --config my_model.qsol.toml --runtime local-dimod --out outdir --runtime-option sampler=exact
```

## 17. Examples — Famous QUBO Problems

This section demonstrates QSOL on well-known combinatorial optimization problems.

### 17.1 Max-Cut

Given a weighted graph $G = (V, E)$, partition the vertices into two sets to maximize the total weight of edges crossing the partition.

```qsol
problem MaxCut {
  set V;
  set E;

  param U[E] : Elem(V);
  param W[E] : Elem(V);
  param Weight[E] : Real;

  find S : Subset(V);

  maximize sum(Weight[e] * (if S.has(U[e]) != S.has(W[e]) then 1 else 0) for e in E);
}
```

The unknown `S ⊆ V` represents one side of the cut. An edge `e` crosses the cut iff exactly one of its endpoints is in `S`, captured by the `!=` test on `S.has(U[e])` and `S.has(W[e])`. The objective maximizes total crossing weight.

### 17.2 Graph Coloring

Given a graph $G = (V, E)$ and a set of colors, assign each vertex a color such that no edge has both endpoints with the same color.

```qsol
problem GraphColoring {
  set V;
  set E;
  set Colors;

  param U[E] : Elem(V);
  param W[E] : Elem(V);

  find Color : Mapping(V -> Colors);

  must forall e in E: forall c in Colors:
    not (Color.is(U[e], c) and Color.is(W[e], c));
}
```

The unknown `Mapping Color: V → Colors` assigns each vertex exactly one color (totality and single-valuedness are implicit). The hard constraint ensures no edge's endpoints share the same color.

### 17.3 Task Assignment (Injective)

Assign tasks to workers such that no worker handles more than one task (injective mapping), minimizing total cost. Prefer not to assign tasks to contractors.

```qsol
use stdlib.injective_mapping;

problem TaskAssignment {
  set Workers;
  set Tasks;

  param Cost[Workers, Tasks] : Real;
  param Contractor[Workers] : Bool;

  find Assign : InjectiveMapping(Tasks, Workers);

  minimize sum(
    sum(Cost[w, t] * (if Assign.is(t, w) then 1 else 0) for w in Workers)
    for t in Tasks
  );

  should forall t in Tasks: forall w in Workers:
    not (Assign.is(t, w) and Contractor[w]);
}
```

`InjectiveMapping(Tasks, Workers)` guarantees each task maps to a unique worker. The objective minimizes total assignment cost. The `should` constraint penalizes (but does not forbid) assigning tasks to contractors.

### 17.4 Knapsack

Given a set of items with values and weights, and a capacity limit, select items to maximize total value without exceeding capacity.

```qsol
problem Knapsack {
  set I;

  param Value[I] : Real;
  param Weight[I] : Int[0 .. 1000000000];
  param Capacity : Int[0 .. 1000000000];

  find Take : Subset(I);

  must sum(Weight[i] * (if Take.has(i) then 1 else 0) for i in I) <= Capacity;

  maximize sum(Value[i] * (if Take.has(i) then 1 else 0) for i in I);
}
```

The unknown `Take ⊆ I` represents the set of items to pack. The hard constraint enforces the capacity limit, and the objective maximizes total value of selected items.

### 17.5 Min-Bisection

Partition a graph's vertices into two equal-size groups, minimizing the number of edges that cross the partition.

```qsol
problem MinBisection {
  set V;
  set E;

  param U[E] : Elem(V);
  param W[E] : Elem(V);

  find Side : Subset(V);

  must count(v in V where Side.has(v)) * 2 = size(V);

  minimize sum(
    if Side.has(U[e]) then
      if Side.has(W[e]) then 0 else 1
    else
      if Side.has(W[e]) then 1 else 0
    for e in E
  );
}
```

`Side ⊆ V` represents one partition. The hard constraint ensures exactly half the vertices are in `Side` (requires `|V|` even). The objective minimizes crossing edges using nested `if-then-else` to implement XOR without boolean reification in the objective.

## 18. Complete Example

Model:

```qsol
use stdlib.logic;

problem FirstProgram {
  set Items;
  param Value[Items] : Real = 1;

  find Pick : Subset(Items);

  must exactly(2, Pick.has(i) for i in Items);
  maximize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
```

Config:

```toml
schema_version = "1"

[entrypoint]
scenario = "baseline"
runtime = "local-dimod"
plugins = []

[scenarios.baseline]
problem = "FirstProgram"

[scenarios.baseline.sets]
Items = ["i1", "i2", "i3", "i4"]

[scenarios.baseline.params.Value]
i1 = 3
i2 = 8
i3 = 5
i4 = 2
```

Inspect, check support, build, and solve:

```bash
uv run qsol inspect check examples/tutorials/first_program.qsol
uv run qsol targets check examples/tutorials/first_program.qsol --config examples/tutorials/first_program.qsol.toml --runtime local-dimod
uv run qsol build examples/tutorials/first_program.qsol --config examples/tutorials/first_program.qsol.toml --runtime local-dimod --out outdir/first_program --format qubo
uv run qsol solve examples/tutorials/first_program.qsol --config examples/tutorials/first_program.qsol.toml --runtime local-dimod --out outdir/first_program --runtime-option sampler=exact
```

## 19. Glossary

- **Unknown**: A solver-chosen structure declared with `find`. Represents one or more decisions the solver must make (e.g., which elements to include, which assignments to pick).
- **Representation (`rep`)**: The internal implementation of a user-defined unknown type, built from primitive unknowns (`Subset`/`Mapping`) or other user-defined types.
- **Laws (`laws`)**: Constraints that are always enforced whenever a user-defined unknown type is instantiated. They encode the type's structural invariants.
- **View (`view`)**: The public API for a user-defined unknown type, consisting of `predicate` and/or `function` definitions. Code outside the `unknown` block interacts with it only through `view` members.
- **Hard constraint (`must`)**: A constraint that must hold in every valid solution. Violation makes a solution infeasible.
- **Soft constraint (`should`)**: A preference that is penalized when violated, with a weight of 10.0 added to the objective.
- **Soft constraint (`nice`)**: A lower-priority preference that is penalized when violated, with a weight of 1.0 added to the objective.
- **Scenario**: A named set of concrete input data (sets and parameters) for a problem, defined in the TOML config file. Multiple scenarios allow testing the same model with different data.
- **Grounding**: The process of expanding quantifiers (`forall`, `exists`) and aggregates (`sum`, `count`, `any`, `all`) over finite sets using concrete scenario data, producing fully instantiated constraints and expressions.

## 20. Related Docs

- Syntax-oriented quick guide: `docs/QSOL_SYNTAX.md`
- Tutorials: `docs/tutorials/README.md`
- Code architecture: `docs/CODEBASE.md`
- Stdlib modules and contracts: `src/qsol/stdlib/README.md`
