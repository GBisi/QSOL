# Backend V1 Limits and Boundaries

The `dimod-cqm-v1` backend targets Constrained Quadratic Models (CQM). This means your QSOL model must be reducible to linear or quadratic expressions over binary variables.

## 1. Supported Constraints

*   **Comparisons**: `=`, `!=`, `<`, `<=`, `>`, `>=` are fully supported.
*   **Logic**: `and`, `or`, `not`, `implies` are supported.
*   **Quantifiers**: `forall`, `exists`, `sum`, `count` are supported.
*   **Static relations**: Tuple binders over grounded relations are supported. Base relations come from scenario data; derived relations are evaluated during grounding. Relation membership calls evaluate against static relation values.
*   **Grounded integer bounds**: Bounded `Int` decisions may use scenario-time static aggregate bounds such as `sum(Length[j] for j in Jobs)`, `count((u, v) in Edge where Weight[u, v] > 0)`, and `size(Edge)`. Bounds that reference decisions or unknown view methods are rejected.
*   **Safe piecewise builtins**: `minimize abs(e)`, `must abs(e) <= C`, `minimize max(term for ...)`, and `maximize min(term for ...)` are supported when the compiler can create finite bounded `Int` auxiliaries.
*   **Source-level globals/helpers**: `all_different(term for x in S)` lowers to pairwise disequality constraints for one finite set binder. `adjacent` and `nonedge` are graph relation helpers that lower to explicit static relation membership formulas.

## 2. Arithmetic Limitations

*   **Addition/Subtraction**: Fully supported (`a + b`, `a - b`).
*   **Multiplication**: Supported if the result is at most quadratic (e.g., `const * var` or `var * var`). Cubic terms (`var * var * var`) are **NOT** supported and will trigger `QSOL3001`.
*   **Division**: Only supported if the divisor is a constant (e.g., `var / 2`). Division by variables is not supported.

## 3. Conditionals (`if-then-else`)

*   **On Parameters**: Fully supported (resolved at compile time).
*   **On Variables**: Supported via linearization, but costly.
    *   **Numeric branches**: `if BoolVar then expr1 else expr2` becomes `BoolVar * expr1 + (1 - BoolVar) * expr2`.
    *   **Boolean branches**: `if BoolVar then boolA else boolB` uses the same linearization pattern.
    *   Ensure the resulting expression stays quadratic.

## 4. Unsupported Shapes (`QSOL3001`)

If you encounter `QSOL3001`, you have likely used a construct that cannot be lowered to a CQM:

*   **Non-Quadratic**: `x * y * z` (cubic interactions).
*   **Non-Linear Comparisons**: `x * y <= z` (quadratic inequality) *is* supported, but `x * y * z <= 1` is not.
*   **Dynamic Sets**: `sum(x for x in S if Var.has(x))` (filtering a set based on a variable) is not supported directly; use `indicator` masks instead: `sum(if Var.has(x) then x else 0 for x in S)`.
*   **Relation Size Blowups**: Relation iteration is static, but a large base or derived relation can still produce many grounded constraints or objective terms.
*   **Aggregate Bound Blowups**: Aggregate bounds are evaluated during grounding. Large static domains or relations can increase grounding time even though they do not add backend expression degree by themselves.
*   **Global Helper Blowups**: `all_different` creates pairwise constraints over its finite domain. Large domains can produce quadratic constraint growth.
*   **Unsupported Piecewise Contexts**: `maximize abs(e)`, `minimize min(...)`, `maximize max(...)`, `abs(e) >= C`, non-affine expressions that would exceed backend degree, and missing finite auxiliary bounds are rejected with `QSOL3101`.
