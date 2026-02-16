# QSOL Backend Reference: `dimod-cqm-v1`

The `dimod-cqm-v1` backend translates QSOL models into Constrained Quadratic Models (CQMs) compatible with D-Wave's `dimod` library.

## 1. Supported Features

This backend supports:
*   **Problem Types**: Optimization and Satisfaction.
*   **Variables**: Binary variables generated from higher-level `Subset` and `Mapping` unknowns.
*   **Constraints**: Linear and Quadratic equality/inequality constraints.
*   **Objectives**: Linear and Quadratic objectives.

## 2. Variable Mapping

The backend automatically flattens high-level QSOL unknowns into binary variables.

### `Subset(S)`
For a find `Find : Subset(S)`, where `S` contains elements `{e1, e2, ...}`, the backend generates one binary variable for each element:
*   `Find.has(e1)`
*   `Find.has(e2)`
...

If `Find.has(e1)` is 1, the element is in the subset. If 0, it is not.

### `Mapping(D -> C)`
For a find `Map : Mapping(D -> C)`, the backend generates binary variables for each pair `(d, c)` in `D x C`:
*   `Map.is(d, c)`

It also generates implicit "exactly one" constraints to ensure each element in `D` maps to exactly one element in `C`:
`sum(Map.is(d, c) for c in C) == 1` for each `d` in `D`.

## 3. Constraint Translation

QSOL constraints are translated into mathematical inequalities.

### Comparisons
*   `lhs <= rhs` -> `lhs - rhs <= 0`
*   `lhs >= rhs` -> `lhs - rhs >= 0`
*   `lhs == rhs` -> `lhs - rhs == 0`
*   `lhs != rhs` -> **Supported via aux variables**: `z == 1` if `lhs != rhs`, `z == 0` otherwise.

### Logical Operators
Boolean logic is converted to arithmetic constraints on binary selection variables (0 or 1).
*   `A and B` -> `A * B` (if linear/quadratic) or via auxiliary variable `Z <= A`, `Z <= B`, `Z >= A + B - 1`.
*   `A or B` -> `A + B - A*B` or via auxiliary variable `Z >= A`, `Z >= B`, `Z <= A + B`.
*   `not A` -> `1 - A`
*   `A implies B` -> `A <= B`

## 4. Objectives and Soft Constraints

*   `minimize expr` adds `expr` to the CQM objective.
*   `maximize expr` adds `-expr` to the CQM objective.
*   `should expr` adds a penalty to the objective if `expr` is violated (weight 10.0).
*   `nice expr` adds a smaller penalty (weight 1.0).

## 5. Limitations

*   **Higher-Order Logic**: Complex nested quantifiers or non-linear expressions that cannot be reduced to quadratic forms may be unsupported or require significant auxiliary variables.
*   **Integer/Real Variables**: Native integer or continuous variables are not currently supported; all unknowns must be reducable to binary decisions (Sets/Mappings).
