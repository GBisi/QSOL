# Tutorial 4: Custom Unknowns, Functions, and Predicates

Goal: build a reusable QSOL module that defines your own unknown type and helper macros, then use them in a problem.

## 1. What to Create

Use these building blocks:

- `unknown`: a custom decision structure (implemented with `rep`, constrained with `laws`, exposed via `view`).
- `predicate`: reusable boolean macro (`Bool` return).
- `function`: reusable numeric macro (`Real` return in current release).

Use top-level `predicate`/`function` for shared helpers across many problems.
Use `view` members when the helper belongs to one unknown type.

## 2. Create a Reusable Module

Create `examples/tutorials/custom_types.qsol`:

```qsol
// Reusable helpers
function indicator(b: Bool): Real = if b then 1 else 0;

predicate exactly_k(k: Real, terms: Comp(Real)): Bool = terms = k;

// A subset that must contain exactly k elements
unknown ExactSubset(X, k) {
  rep {
    inner : Subset(X);
  }
  laws {
    must count(x in X where inner.has(x)) = k;
  }
  view {
    predicate has(x: Elem(X)): Bool = inner.has(x);
    function pick_score(x: Elem(X)): Real = indicator(inner.has(x));
  }
}
```

Notes:

- `rep` must be primitives (`Subset`/`Mapping`) or other user-defined unknowns.
- `laws` are always enforced whenever the unknown is instantiated with `find`.
- Outside the unknown, callers interact only through `view` members (`has`, `pick_score`).

## 3. Use the Module in a Problem

Create `examples/tutorials/custom_types_usage.qsol`:

```qsol
use custom_types;

problem PickThree {
  set Items;
  param Weight[Items] : Real = 1;

  find Pick : ExactSubset(Items, 3);

  // Use unknown view predicate in constraints
  must forall i in Items: Pick.has(i) => Weight[i] >= 0;

  // Use top-level predicate macro with comprehension argument
  must exactly_k(3, indicator(Pick.has(i)) for i in Items);

  // Use unknown view function in objective
  maximize sum(Pick.pick_score(i) * Weight[i] for i in Items);
}
```

Import path reminder:

- `use custom_types;` maps to `custom_types.qsol`.
- Non-`stdlib.*` imports resolve from the importer directory, then process CWD.

## 4. Type Rules to Remember

- `predicate` return type is always `Bool`. The `: Bool` annotation is optional.
- `function` return type is `Real` in the current release. The `: Real` annotation is optional.
- Formal argument types must be explicit (`Bool`, `Real`, `Elem(SetName)`, `Comp(Bool)`, `Comp(Real)`).
- `Comp(...)` parameters take comprehension-style call arguments.

## 5. Common Mistakes

- Calling representation fields outside the unknown (for example `Pick.inner.has(i)`) is invalid; use `view` members instead (`Pick.has(i)`).
- Forgetting `laws` for structural invariants makes the custom unknown under-constrained.
- Writing a `function` with non-`Real` return type is invalid in this release.

## 6. Validation Workflow

After creating your module and problem:

```bash
uv run qsol inspect parse examples/tutorials/custom_types_usage.qsol
uv run qsol inspect check examples/tutorials/custom_types_usage.qsol
```

If you add scenario data/config, continue with `targets check`, `build`, and `solve` as in earlier tutorials.

## 7. Where to Go Next

- `QSOL_reference.md` section "Extending QSOL: User-Defined Unknown Types"
- `docs/QSOL_SYNTAX.md` for declaration and expression syntax
- `src/qsol/stdlib/logic.qsol` and mapping modules for reusable patterns
