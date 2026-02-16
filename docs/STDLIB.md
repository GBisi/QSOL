# QSOL Standard Library

The Standard Library (`stdlib`) provides a collection of useful unknowns, predicates, and functions to simplify modeling.

To use a module, import it with `use stdlib.<module_name>;`.

## 1. Boolean Logic (`stdlib.logic`)

Provides helper predicates for common logical operations and counting constraints.

```qsol
use stdlib.logic;
```

### Predicates

*   **`iff(a: Bool, b: Bool): Bool`**
    *   Returns true if `a` and `b` have the same truth value (Logical Equivalence).
    *   `iff(true, true)` is `true`.
    *   `iff(true, false)` is `false`.

*   **`xor(a: Bool, b: Bool): Bool`**
    *   Returns true if exactly one of `a` or `b` is true (Exclusive OR).

*   **`exactly(k: Real, terms: Comp(Real)): Bool`**
    *   Returns true if the sum of `terms` equals `k`.
    *   Commonly used with boolean comprehensions: `exactly(1, S.has(x) for x in X)`.

*   **`atleast(k: Real, terms: Comp(Real)): Bool`**
    *   Returns true if shear sum of `terms` is `>= k`.

*   **`atmost(k: Real, terms: Comp(Real)): Bool`**
    *   Returns true if the sum of `terms` is `<= k`.

*   **`between(lo: Real, hi: Real, terms: Comp(Real)): Bool`**
    *   Returns true if `lo <= sum(terms) <= hi`.

### Functions

*   **`indicator(b: Bool): Real`**
    *   Returns `1` if `b` is true, `0` otherwise.

## 2. Mappings & Permutations

These modules provide specialized unknown types for mapping problems.

### `stdlib.injective_mapping`

```qsol
use stdlib.injective_mapping;
find F : InjectiveMapping(Domain, Codomain);
```

*   **`InjectiveMapping(A, B)`**: An unknown mapping from `A` to `B` where each element of `B` is mapped to by *at most one* element of `A`.
*   **View**: `is(a: Elem(A), b: Elem(B))`

### `stdlib.surjective_mapping`

```qsol
use stdlib.surjective_mapping;
find F : SurjectiveMapping(Domain, Codomain);
```

*   **`SurjectiveMapping(A, B)`**: An unknown mapping from `A` to `B` where each element of `B` is mapped to by *at least one* element of `A`.
*   **View**: `is(a: Elem(A), b: Elem(B))`

### `stdlib.bijective_mapping`

```qsol
use stdlib.bijective_mapping;
find F : BijectiveMapping(Domain, Codomain);
```

*   **`BijectiveMapping(A, B)`**: An unknown mapping from `A` to `B` that is both injective and surjective (one-to-one correspondence).
*   **View**: `is(a: Elem(A), b: Elem(B))`

### `stdlib.permutation`

```qsol
use stdlib.permutation;
find P : Permutation(Items);
```

*   **`Permutation(A)`**: A bijection from set `A` to itself. Useful for ordering or reordering problems.
*   **View**: `is(from: Elem(A), to: Elem(A))`
