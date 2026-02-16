# QSOL Stdlib Library

This directory contains packaged unknown modules under the reserved `stdlib.*` namespace.

## 1. Import Style (Same as User Libraries)

QSOL uses one import form for both stdlib and user modules:

```qsol
use stdlib.permutation;
use stdlib.logic;
use mylib.graph.unknowns;
```

Rules:
- Dotted module path: `a.b.c`
- File mapping: `a/b/c.qsol`
- `stdlib.*` resolves from packaged files in `src/qsol/stdlib/`
- Non-`stdlib.*` resolves from importer directory, then process CWD
- `stdlib` prefix is reserved and cannot be overridden by user modules

## 2. Why Stdlib Modules Work on Backend v1

Backend v1 is primitive-focused (`Subset`, `Mapping`).
Stdlib unknown and macro modules compile because frontend expansion elaborates them into:
- generated primitive finds (`Subset`/`Mapping`)
- generated constraints from unknown `laws`
- rewritten method and macro calls from unknown `view` and top-level predicate/function definitions

## 3. Module Catalog

### `stdlib.injective_mapping`

Exports:
- `unknown InjectiveMapping(A, B)`

View methods:
- `is(a: Elem(A), b: Elem(B)) -> Bool`

Semantics:
- uses internal `Mapping(A -> B)`
- enforces injectivity:
`forall b in B: count(a for a in A where f.is(a, b)) <= 1`

### `stdlib.surjective_mapping`

Exports:
- `unknown SurjectiveMapping(A, B)`

View methods:
- `is(a: Elem(A), b: Elem(B)) -> Bool`

Semantics:
- uses internal `Mapping(A -> B)`
- enforces surjectivity:
`forall b in B: count(a for a in A where f.is(a, b)) >= 1`

### `stdlib.bijective_mapping`

Exports:
- `unknown BijectiveMapping(A, B)`

View methods:
- `is(a: Elem(A), b: Elem(B)) -> Bool`

Semantics:
- uses internal `Mapping(A -> B)`
- enforces injectivity and surjectivity directly:
  `forall b in B: count(a for a in A where f.is(a, b)) <= 1`
  `forall b in B: count(a for a in A where f.is(a, b)) >= 1`

### `stdlib.permutation`

Imports:
- `stdlib.bijective_mapping`

Exports:
- `unknown Permutation(A)`

View methods:
- `is(a: Elem(A), b: Elem(A)) -> Bool`

Semantics:
- a bijection from `A` to `A`

### `stdlib.logic`

Exports:
- `function indicator(b: Bool): Real`
- `predicate exactly(k: Real, terms: Comp(Real)): Bool`
- `predicate atleast(k: Real, terms: Comp(Real)): Bool`
- `predicate atmost(k: Real, terms: Comp(Real)): Bool`
- `predicate between(lo: Real, hi: Real, terms: Comp(Real)): Bool`
- `predicate iff(a: Bool, b: Bool): Bool`
- `predicate xor(a: Bool, b: Bool): Bool`

Semantics:
- frontend macro helpers for common boolean/count expressions
- no backend primitive changes; helpers expand before lowering/backend stages
- `iff(a, b)` is logical equivalence (`(a => b) and (b => a)`)
- `xor(a, b)` is exclusive-or (`(a or b) and not (a and b)`)
- `between(lo, hi, terms)` is inclusive
- Counting helpers take comprehension-style arguments, e.g. `atleast(1, S.has(x) for x in A)`

## 4. Usage Examples

### Permutation

```qsol
use stdlib.permutation;

problem Demo {
  set V;
  find P : Permutation(V);
  must forall v in V: exists w in V: P.is(v, w);
  minimize 0;
}
```

### Injective Assignment

```qsol
use stdlib.injective_mapping;

problem InjectiveAssign {
  set Workers;
  set Tasks;
  find Assign : InjectiveMapping(Tasks, Workers);
  minimize 0;
}
```

### Logic Helpers

```qsol
use stdlib.logic;

problem Demo {
  set A;
  find S : Subset(A);
  must exactly(1, S.has(x) for x in A);
  minimize sum(indicator(S.has(x)) for x in A);
}
```

## 5. Diagnostics and Failure Modes

Common import/elaboration diagnostics:
- `QSOL2001`: unknown or invalid module path (including unknown stdlib module)
- `QSOL2101`: import cycle, unsupported imported top-level item, unknown method/arity mismatch in view usage
- `QSOL1001`: parse failure inside imported module
- `QSOL4003`: imported module file read failure

## 6. Authoring and Extending

When adding new stdlib modules:
- keep top-level content to `use`, `unknown`, `predicate`, and/or `function` items
- provide stable, well-named `view` predicates/functions and top-level macro APIs
- encode semantics in `laws` with backend-friendly boolean/numeric patterns
- add parser/sema/backend tests and update docs (`README.md`, `QSOL_reference.md`, syntax/tutorial docs)
