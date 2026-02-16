# Extending QSOL

QSOL is designed to be extensible. You can define new "unknown" types and reusable logic macros directly in QSOL code.

## 1. Custom Unknowns

You can define higher-level decision variables (`unknown` types) by composing primitive ones (`Subset`, `Mapping`) and adding constraints.

When you use a custom unknown in a `find` statement, the compiler "elaborates" it: it creates the internal primitive variables and applies the defined laws.

### Syntax

```qsol
unknown BijectiveMapping(A, B) {
  // 1. Internal Representation
  // Define the primitive variables that back this unknown.
  rep {
    f : Mapping(A -> B);
  }

  // 2. Laws
  // Constraints that must always hold for this type.
  laws {
    // Injective: each element in B is mapped to at most once
    must forall b in B: count(a for a in A where f.is(a, b)) <= 1;

    // Surjective: each element in B is mapped to at least once
    must forall b in B: count(a for a in A where f.is(a, b)) >= 1;
  }

  // 3. View
  // Public interface methods that users can call.
  view {
    predicate is(a: Elem(A), b: Elem(B)): Bool = f.is(a, b);
  }
}
```

### Usage

Once defined, you can use it like any built-in type:

```qsol
find MyBijection : BijectiveMapping(Guests, Seats);
must MyBijection.is(alice, seat1);
```

## 2. Reusable Macros

You can define `predicate` and `function` macros to encapsulate common logic. These are textually substituted (inlined) where they are called.

### Predicates (return Bool)

```qsol
predicate iff(a: Bool, b: Bool): Bool = (a and b) or (not a and not b);
```

### Functions (return Real)

```qsol
function indicator(condition: Bool): Real = if condition then 1 else 0;
```

### Usage

```qsol
must iff(x, y);
minimize indicator(x);
```

## 3. Packaging as Modules

To share your extensions, plain `.qsol` files work as modules.

1.  Save your code in `mylib/graph_utils.qsol`.
2.  Import it using the dotted path:

```qsol
use mylib.graph_utils;

problem MyProblem {
  ...
}
```
