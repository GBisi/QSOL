# QSOL Language Reference (Compiler v0.1.0)

This reference describes the language accepted by the current QSOL parser/typechecker and the subset supported by backend v1 (`dimod-cqm-v1`).

## 1. Versioning and Compatibility

QSOL currently has two practical compatibility layers:

- Parse/typecheck layer: what the grammar and semantic passes accept.
- Backend layer: what selected targets can lower/run without `QSOL3001` or target capability failures.

This document calls out both layers explicitly so you can write models that are valid and compilable.

## 2. Program Structure

A QSOL file contains top-level `problem` and/or `unknown` definitions.

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

## 3. Declarations

### 3.1 Sets

```qsol
set Workers;
set Tasks;
```

Sets are finite domains whose concrete elements are provided by the instance JSON.

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
- Indexed params may also have scalar defaults; instance expansion uses declared set elements.
- `Elem(SetName)` params do not support defaults.

Reading params in expressions:
- Indexed params can be read as `Cost[w, t]` (bracket syntax).
- Set-valued params can be used as set elements (for example `Pick.has(StartNode[t])`).
- Scalar params must be referenced as bare names (for example `C`, `Flag`, `Start`).
- Scalar call/index forms such as `C[]` and `Flag()` are rejected with `QSOL2101`.
- `size(SetName)` returns set cardinality and is constant-folded after instance loading.

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
- Backend compilation to dimod: **not yet supported** for custom unknown instantiation in `find`.

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

## 8. Instance JSON

Required shape:

```json
{
  "problem": "ProblemName",
  "sets": {
    "A": ["a1", "a2"],
    "B": ["b1"]
  },
  "params": {
    "K": 3,
    "Cost": {
      "a1": {"b1": 5.0},
      "a2": {"b1": 7.0}
    }
  },
  "execution": {
    "runtime": "local-dimod",
    "backend": "dimod-cqm-v1"
  }
}
```

Notes:
- `problem` selects a compiled problem by name. If omitted, all compiled problems are considered.
- All declared sets must appear in `sets` and be arrays.
- Missing params without defaults produce errors.
- Indexed params must match declared dimension keys.
- For `Elem(SetName)` params, every leaf value is normalized to string and must be present in `sets.SetName`.
- `execution` is optional and provides default target selection:
  - `execution.runtime`
  - `execution.backend`
- CLI `--runtime` / `--backend` override `execution` defaults.

## 9. Backend v1 Support Matrix

The language accepted by parser/typechecker is broader than backend v1 codegen.

### 9.1 Fully supported (safe patterns)

- `find` with `Subset` and `Mapping`
- hard numeric comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) where both sides lower to numeric backend expressions
- boolean-context comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) are supported in objectives/soft expressions via indicator encoding
- hard constraints as conjunctions of supported atoms/comparisons
- hard `not <atom>`
- hard implications where both sides are atom-like
- `sum`, arithmetic, `if-then-else`, numeric param lookups
- soft constraints (`should`, `nice`) over bool formulas built from atom-like terms and boolean operators; these are soft-only and do not add hard feasibility constraints
- objectives over supported numeric expressions

### 9.2 Known unsupported/partial areas

- custom unknown kinds in `find` (user-defined unknown instantiation)
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
- `QSOL2201`: instance data or indexing/shape issue
- `QSOL3001`: unsupported backend shape or validation/backend limitation
- `QSOL4002`: missing inferred instance file
- `QSOL4003`: model or payload file read failure
- `QSOL4004`: instance JSON load/validation failure before compilation
- `QSOL4005`: missing expected artifacts or target outputs
- `QSOL4006`: runtime/backend selection unresolved
- `QSOL4007`: unknown runtime/backend id
- `QSOL4008`: incompatible runtime/backend pair
- `QSOL4009`: plugin load/registration failure
- `QSOL4010`: unsupported required capability for selected target
- `QSOL5001`: runtime execution failure

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
- `targets check` to validate concrete target support on model+instance
- `build` to export artifacts for selected runtime/backend
- `solve` to execute selected runtime/backend

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

Instance:

```json
{
  "problem": "FirstProgram",
  "sets": {
    "Items": ["i1", "i2", "i3", "i4"]
  },
  "params": {
    "Value": {
      "i1": 3,
      "i2": 8,
      "i3": 5,
      "i4": 2
    }
  },
  "execution": {
    "runtime": "local-dimod",
    "backend": "dimod-cqm-v1"
  }
}
```

Inspect, check support, build, and solve:

```bash
uv run qsol inspect check examples/tutorials/first_program.qsol
uv run qsol targets check examples/tutorials/first_program.qsol --instance examples/tutorials/first_program.instance.json --runtime local-dimod --backend dimod-cqm-v1
uv run qsol build examples/tutorials/first_program.qsol --instance examples/tutorials/first_program.instance.json --runtime local-dimod --backend dimod-cqm-v1 --out outdir/first_program --format qubo
uv run qsol solve examples/tutorials/first_program.qsol --instance examples/tutorials/first_program.instance.json --runtime local-dimod --backend dimod-cqm-v1 --out outdir/first_program --runtime-option sampler=exact
```

## 12. Related Docs

- Syntax-oriented quick guide: `docs/QSOL_SYNTAX.md`
- Tutorials: `docs/tutorials/README.md`
- Code architecture: `docs/CODEBASE.md`
