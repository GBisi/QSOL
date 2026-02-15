# QSOL Language Reference (Compiler v0.1.0)

This reference describes the language accepted by the current QSOL parser/typechecker and the subset supported by backend v1 (`dimod-cqm-v1`).

## 1. Versioning and Compatibility

QSOL currently has two practical compatibility layers:

- Parse/typecheck layer: what the grammar and semantic passes accept.
- Backend layer: what selected targets can lower/run without `QSOL3001` or target capability failures.

This document calls out both layers explicitly so you can write models that are valid and compilable.

## 2. Program Structure

A QSOL file may contain top-level `use`, `unknown`, and `problem` definitions.

```qsol
problem Name {
  set A;
  param weight[A] : Real = 1;
  find S : Subset(A);

  must forall x in A: S.has(x) or not S.has(x);
  minimize sum(if S.has(x) then weight[x] else 0 for x in A);
}
```

### 2.1 Statement Terminator

- Statements are semicolon-terminated (`;`).
- Newlines are ignored by the grammar.

### 2.2 Comments

```qsol
// single line comment
/* block comment */
```

### 2.3 Imports (`use`)

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
- Imported modules may contain only `use` and `unknown` top-level items (`problem` blocks are rejected in imported modules)

## 3. Declarations

### 3.1 Sets

```qsol
set Workers;
set Tasks;
```

Sets are finite domains whose concrete elements are provided by the selected config scenario.

### 3.2 Parameters

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
- Set-valued params can be used as set elements (for example `Pick.has(StartNode[t])`).
- Scalar params must be referenced as bare names (for example `C`, `Flag`, `Start`).
- Scalar call/index forms such as `C[]` and `Flag()` are rejected with `QSOL2101`.
- `size(SetName)` returns set cardinality and is constant-folded after scenario loading.

### 3.3 Unknowns

Primitive unknowns in backend v1:

```qsol
find S : Subset(A);
find F : Mapping(A -> B);
```

- `Subset(A)`: one binary decision variable per `a in A`
- `Mapping(A -> B)`: one binary variable per `(a,b)` with implicit `exactly one b` per row `a`

### 3.4 User-Defined Unknown Types

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
    predicate has(x in A) = inner.has(x);
  }
}
```

Current status:
- Parse/typecheck: supported.
- Frontend compilation for custom unknown instantiation in `find`: supported.
- Backend remains primitive-focused (`Subset`/`Mapping`); custom unknowns are elaborated in frontend into primitive finds plus generated constraints before resolver/typecheck/lower/backend stages.

## 4. Expressions

QSOL has boolean and numeric expressions.

### 4.1 Boolean Expressions

Operators and forms:
- `not E`
- `E and F`
- `E or F`
- `E => F`
- comparisons: `=`, `!=`, `<`, `<=`, `>`, `>=`
- quantifiers: `forall x in X: E`, `exists x in X: E`
- aggregates: `any(...)`, `all(...)`
- method calls (`S.has(x)`, `F.is(a,b)`)
- function calls (`Param(x)`, `predicateName(x)`)

### 4.2 Numeric Expressions

Operators and forms:
- `+`, `-`, `*`, `/`
- unary `-E`
- conditional: `if cond then A else B`
- aggregates: `sum(...)`, `count(...)`
- builtin set cardinality: `size(SetName)` (numeric)
- parameter access:
  - indexed style: `Cost[i,j]` (numeric indexed params)
  - scalar style: `C` (bare scalar params)

### 4.3 Operator Precedence (high to low)

1. Unary: `not`, unary `-`
2. Multiplicative: `*`, `/`
3. Additive: `+`, `-`
4. Comparisons: `=`, `!=`, `<`, `<=`, `>`, `>=`
5. `and`
6. `or`
7. `=>`

Use parentheses for clarity in complex formulas.

## 5. Quantifiers and Aggregates

### 5.1 Quantifiers

```qsol
forall x in A: body
exists y in B: body
```

### 5.2 Aggregates and Comprehensions

General comprehension style:

```qsol
agg(term for x in X where predicate else fallback)
```

`where` and `else` are optional.

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

## 6. Constraints and Objectives

### 6.1 Constraints

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

### 6.2 Objectives

```qsol
minimize numeric_expr;
maximize numeric_expr;
```

Backend interpretation:
- `maximize E` is converted to minimizing `-E`.
- Soft constraints contribute penalties into objective:
  - `should`: weight 10.0
  - `nice`: weight 1.0

## 7. Desugaring Rules

Desugaring is applied before lowering/codegen.

### 7.1 Guards

- `must phi if c` -> `must (c => phi)`
- `should phi if c` -> `should (c => phi)`
- `nice phi if c` -> `nice (c => phi)`

### 7.2 `count`

- `count(x for x in X where c)` -> `sum(1 for x in X where c)`
- `count(x in X where c)` -> `sum(1 for x in X where c)`

### 7.3 `sum` with filters

- `sum(t for x in X where c)` -> `sum(if c then t else 0 for x in X)`
- `sum(t for x in X where c else e)` -> `sum(if c then t else e for x in X)`

### 7.4 `any` and `all`

- `any(...)` desugars to `exists ...`
- `all(...)` desugars to `forall ...`

### 7.5 Numeric conditional

- `if c then a else b` is lowered as indicator arithmetic (`c*a + (1-c)*b`) in backend numeric encoding.

## 8. Config TOML and Scenarios

CLI `targets check`, `build`, and `solve` consume a TOML config file (`*.qsol.toml`) with one or more named scenarios.

Required root shape:

```toml
schema_version = "1"

[selection]
mode = "default" # default|all|subset
default_scenario = "baseline"
subset = ["baseline", "stress"]
combine_mode = "intersection" # intersection|union
failure_policy = "run-all-fail" # run-all-fail|fail-fast|best-effort

[defaults.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"
plugins = []

[defaults.solve]
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
- Each scenario materializes to the historical instance payload shape (`problem`, `sets`, `params`, optional `execution`) before grounding.
- Scenario `execution` values override `defaults.execution` values field-by-field.
- Scenario `solve` values override `defaults.solve`, and CLI solve flags override both.
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
3. Config `selection.mode`
4. Config `selection.default_scenario`
5. If exactly one scenario exists, use it

If unresolved, fail with `QSOL4001`.

Runtime selection precedence:
1. CLI `--runtime`
2. Scenario/default `execution.runtime`

If unresolved, fail with `QSOL4006`.

Plugin loading order for `targets check`/`build`/`solve`:
1. built-ins
2. installed entry points (`qsol.backends`, `qsol.runtimes`)
3. config `execution.plugins`
4. CLI `--plugin`

Config and CLI plugin specs are merged in order and deduplicated by exact string.

### 8.1 Qiskit Runtime Options

The built-in `qiskit` runtime is compatible with backend `dimod-cqm-v1` and supports:

- `algorithm=qaoa|numpy` (default: `qaoa`)
- `fake_backend=<FakeBackendClass>` (default: `FakeManilaV2`; used by `qaoa`)
- `shots=<int>` (default: `1024`, QAOA only)
- `reps=<int>` (default: `1`, QAOA only)
- `maxiter=<int>` (default: `100`, QAOA only)
- `seed=<int>` (optional)
- `optimization_level=<int>` (default: `1`, QAOA transpilation)
- `solutions`, `energy_min`, `energy_max` (same solve contract as other runtimes)

When `algorithm=qaoa`, `solve` exports OpenQASM 3 to `qaoa.qasm` in the selected output directory and reports the path in `run.json` extensions.

## 9. Backend v1 Support Matrix

The language accepted by parser/typechecker is broader than backend v1 codegen.

### 9.1 Fully supported (safe patterns)

- `find` with `Subset`, `Mapping`, and user-defined unknown kinds that elaborate to primitive finds
- hard numeric comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) where both sides lower to numeric backend expressions
- boolean-context comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) are supported in objectives/soft expressions via indicator encoding
- hard constraints as conjunctions of supported atoms/comparisons
- hard `not <atom>`
- hard implications where both sides are atom-like
- `sum`, arithmetic, `if-then-else`, numeric param lookups
- soft constraints (`should`, `nice`) over bool formulas built from atom-like terms and boolean operators; these are soft-only and do not add hard feasibility constraints
- objectives over supported numeric expressions

### 9.2 Known unsupported/partial areas

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

## 10. Diagnostics

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

## 11. Complete Example

Model:

```qsol
problem FirstProgram {
  set Items;
  param Value[Items] : Real = 1;

  find Pick : Subset(Items);

  must sum(if Pick.has(i) then 1 else 0 for i in Items) = 2;
  maximize sum(if Pick.has(i) then Value[i] else 0 for i in Items);
}
```

Config:

```toml
schema_version = "1"

[selection]
default_scenario = "baseline"

[defaults.execution]
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

## 12. Related Docs

- Syntax-oriented quick guide: `docs/QSOL_SYNTAX.md`
- Tutorials: `docs/tutorials/README.md`
- Code architecture: `docs/CODEBASE.md`
- Stdlib modules and contracts: `src/qsol/stdlib/README.md`
