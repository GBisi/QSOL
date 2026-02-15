# QSOL Stdlib Unknown Library

This directory contains packaged unknown modules under the reserved `stdlib.*` namespace.

## 1. Import Style (Same as User Libraries)

QSOL uses one import form for both stdlib and user modules:

```qsol
use stdlib.permutation;
use mylib.graph.unknowns;
```

Rules:
- Dotted module path: `a.b.c`
- File mapping: `a/b/c.qsol`
- `stdlib.*` resolves from packaged files in `src/qsol/stdlib/`
- Non-`stdlib.*` resolves from importer directory, then process CWD
- `stdlib` prefix is reserved and cannot be overridden by user modules

## 2. Why Stdlib Unknowns Work on Backend v1

Backend v1 is primitive-focused (`Subset`, `Mapping`).
Stdlib unknowns compile because frontend unknown elaboration expands them into:
- generated primitive finds (`Subset`/`Mapping`)
- generated constraints from unknown `laws`
- rewritten method calls from unknown `view` predicates

## 3. Module Catalog

### `stdlib.injective_mapping`

Exports:
- `unknown InjectiveMapping(A, B)`

View methods:
- `is(a in A, b in B) -> Bool`

Semantics:
- uses internal `Mapping(A -> B)`
- enforces injectivity:
`forall b in B: count(a for a in A where f.is(a, b)) <= 1`

### `stdlib.surjective_mapping`

Exports:
- `unknown SurjectiveMapping(A, B)`

View methods:
- `is(a in A, b in B) -> Bool`

Semantics:
- uses internal `Mapping(A -> B)`
- enforces surjectivity:
`forall b in B: count(a for a in A where f.is(a, b)) >= 1`

### `stdlib.bijective_mapping`

Imports:
- `stdlib.injective_mapping`
- `stdlib.surjective_mapping`

Exports:
- `unknown BijectiveMapping(A, B)`

View methods:
- `is(a in A, b in B) -> Bool`

Semantics:
- composes one injective and one surjective mapping over the same domains
- enforces pointwise equality between their `is(a, b)` relations

### `stdlib.permutation`

Imports:
- `stdlib.bijective_mapping`

Exports:
- `unknown Permutation(A)`

View methods:
- `is(a in A, b in A) -> Bool`

Semantics:
- a bijection from `A` to `A`

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

## 5. Diagnostics and Failure Modes

Common import/elaboration diagnostics:
- `QSOL2001`: unknown or invalid module path (including unknown stdlib module)
- `QSOL2101`: import cycle, unsupported imported top-level item, unknown method/arity mismatch in view usage
- `QSOL1001`: parse failure inside imported module
- `QSOL4003`: imported module file read failure

## 6. Authoring and Extending

When adding new stdlib modules:
- keep top-level content to `use` and `unknown` items
- provide stable, well-named `view` predicates as module API
- encode semantics in `laws` with backend-friendly boolean/numeric patterns
- add parser/sema/backend tests and update docs (`README.md`, `QSOL_reference.md`, syntax/tutorial docs)
