# Backend V1 Limits and Boundaries

The `dimod-cqm-v1` backend targets Constrained Quadratic Models (CQM). This means your QSOL model must be reducible to linear or quadratic expressions over binary variables.

## 1. Supported Constraints

*   **Comparisons**: `=`, `!=`, `<`, `<=`, `>`, `>=` are fully supported.
*   **Logic**: `and`, `or`, `not`, `implies` are supported.
*   **Quantifiers**: `forall`, `exists`, `sum`, `count` are supported.

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
