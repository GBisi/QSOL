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
```

### 3.2 Params

```qsol
param K : Int[1 .. 10] = 3;
param Cost[Workers,Tasks] : Real;
param Allowed[Workers,Tasks] : Bool = true;
param StartNode[Tasks] : Elem(Workers);
```

Usage notes:
- Indexed params can be referenced as `Cost[w, t]`.
- Indexed params must use brackets; `Cost(w, t)` is rejected with `QSOL2101`.
- `Elem(SetName)` params return set elements and can be passed to methods like `Subset.has(...)`.
- `Elem(SetName)` params do not allow defaults.
- Scalar params must be referenced as bare names (for example `C`, `Flag`, `Start`).
- Scalar call/index forms such as `C[]` and `Flag()` are rejected with `QSOL2101`.

### 3.3 Finds

```qsol
find Pick : Subset(Workers);
find Assign : Mapping(Workers -> Tasks);
find Perm : Permutation(Workers); // from `use stdlib.permutation;`
```

`find` supports primitive unknowns (`Subset`, `Mapping`) and user-defined unknowns.
Custom unknown finds are elaborated in frontend into primitive finds plus generated constraints.

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
```

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
if cond then a else b
size(V)
```

### 5.3 Calls and member access

```qsol
S.has(x)
Assign.is(w, t)
exactly(1, S.has(x) for x in X)

Cost[w, t]
C
size(V)
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

  find Pick : Subset(Items);

  must exactly(2, Pick.has(i) for i in Items);
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
