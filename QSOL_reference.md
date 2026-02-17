# ⚛️ QSOL Language Reference

**QSOL** (Quantum/Quadratic Specification-Oriented Optimisation Language) is a declarative language for modeling combinatorial optimization problems. It allows you to describe *what* you want to solve, rather than *how* to solve it.

This reference guide covers the entire language surface, from basic syntax to advanced custom types and the standard library.

---

## 1. The QSOL Model

A QSOL program describes a single **Optimization Problem**. Every problem consists of five key components:

1.  **Sets**: The universe of items involved (e.g., `Workers`, `Tasks`, `TimeSlots`).
2.  **Parameters**: The input data you have (e.g., `Costs`, `Capacities`, `Preferences`).
3.  **Unknowns**: The decisions the solver must make (e.g., "Choose a subset of workers", "Assign tasks to workers").
4.  **Constraints**: The rules that *must* be followed (`must`) and the preferences that *should* be satisfied (`should`, `nice`).
5.  **Objectives**: The quantitative goal (`minimize` cost, `maximize` efficiency).

The compiler turns this high-level specification into a format (like QUBO or CQM) that quantum or classical solvers can execute.

---

## 2. Program Structure

A QSOL file (`.qsol`) is a collection of top-level declarations. The entry point is usually a `problem` block.

```qsol
// Imports come first
use stdlib.logic;

// Top-level macro definitions
predicate is_valid(x: Bool) = x;

// The main problem definition
problem MyProblem {
  // Sets, Params, Unknowns, Constraints, Objectives
}
```

### Identifier Rules
*   **Case Sensitive**: `MySet` and `myset` are different.
*   **Conventions**:
    *   `PascalCase` for Sets, Problems, and Unknown Types (e.g., `Workers`, `BijectiveMapping`).
    *   `PascalCase` for Parameters (e.g., `CostMatrix`).
    *   `snake_case` for Unknown instances, predicates, and functions (e.g., `assign_task`, `is_valid`).

### Comments
```qsol
// Single-line comment regarding the next line
/* Multi-line comment block
   for longer explanations */
```

---

## 3. Types and Values

QSOL is a strongly typed language.

### Primitive Types

| Type | Description | Examples |
| :--- | :--- | :--- |
| `Bool` | Boolean logic | `true`, `false`, `x > 5` |
| `Real` | Continuous number | `3.14`, `-5.0`, `1e-6` |
| `Int[min..max]` | Integer in inclusive range | `Int[0..10]`, `Int[-5..5]` |
| `Elem(Set)` | An element of a declared Set | `Elem(Workers)` |

### Unknown Structure Types

These describe the shape of the decisions the solver makes.

| Type | Description |
| :--- | :--- |
| `Subset(S)` | A choice of zero or more elements from set `S`. |
| `Mapping(A -> B)` | A function mapping every element of `A` to exactly one element of `B`. |
| *Custom* | User-defined types (e.g., `Permutation(S)`, `BijectiveMapping(A, B)`). |

---

## 4. Problem Declarations

Inside a `problem` block, you define the components of your model.

### 4.1. Sets

Sets are abstract collections of items. Their concrete members are provided at runtime configuration.

```qsol
set Workers;
set Tasks;

// In the configuration (qsol.toml), these might look like:
// Workers = ["Alice", "Bob", "Charlie"]
// Tasks = ["FixBug", "WriteTests"]
```

### 4.2. Parameters

Parameters hold the input data.

```qsol
// Simple scalars
param MaxCost : Real;
param IsEnabled : Bool = true; // with default value

// Arrays / Maps
param Cost[Workers, Tasks] : Real;  // 2D Matrix
param JobType[Tasks] : Elem(Types); // Maps each task to a type

### 4.2.1. Referencing Specific Elements

To refer to a specific element of a set (an "atom") in your logic, you must declare a parameter for it.

```qsol
// I want to make a rule specifically for the Team Leader.
param TeamLeader : Elem(Workers);

// Later in qsol.toml:
// TeamLeader = "Alice"
```

### 4.3. Unknowns (`find`)

The `find` keyword forces the solver to search for a value.

```qsol
// "Find a subset of workers to hire"
find Hired : Subset(Workers);

// "Find a mapping from Tasks to Workers"
find Assignment : Mapping(Tasks -> Workers);

// "Find a permutation of cities (e.g. for TSP)"
// find Route : Permutation(Cities);
```

### 4.4. Constraints

Constraints restrict the search space or guide the optimization.

*   **`must` (Hard Constraint)**: Mandatory. If violated, the solution is invalid.
    ```qsol
    must forall t in Tasks: Assignment.is(t, competent_worker);
    ```
*   **`should` (Soft Constraint)**: Strongly preferred. Violation adds a large penalty.
    ```qsol
    should Hired.has(favorite_worker);
    ```
*   **`nice` (Weak Constraint)**: Light preference. Violation adds a small penalty.
    ```qsol
    nice forall w in Workers: not Hired.has(w); // Try to keep team small
    ```

> [!TIP]
> *   `must`: "Violating this is impossible." (Hard constraint)
> *   `should`: "Violating this is very bad." (High penalty)
> *   `nice`: "Violating this is slightly bad." (Low penalty)

### 4.5. Objectives

Objectives define the metric to optimize. You can have one objective per problem.

```qsol
minimize sum(Cost[w, t] for w in Workers for t in Tasks if Assignment.is(t, w));
// or
maximize TotalFun;
```

> [!NOTE]
> Only one objective function is allowed per problem.

---

## 5. Expressions

### 5.1. Logical Operators

Operate on `Bool` types.

*   `and`, `or`, `not`
*   `=>` (implies): `A => B` means "if A is true, then B must be true".
*   **Quantifiers**:
    *   `forall x in Set: body` — True if `body` holds for **every** element.
    *   `exists x in Set: body` — True if `body` holds for **at least one** element.
*   **Bool Aggregates**:
    *   `all(expr for x in S)` — Same semantics as `forall`, but supports `where`/`else` (see below).
    *   `any(expr for x in S)` — Same semantics as `exists`, but supports `where`/`else` (see below).

### 5.2. Numeric Operators

Operate on `Real` or `Int` types.

*   Standard Math: `+`, `-`, `*`, `/`
*   Comparisons: `=`, `!=`, `<`, `>`, `<=`, `>=` (return `Bool`)
*   **Aggregates**:
    *   `sum(expr for x in S)`: Summation.
    *   `count(x in S where predicate)`: Count matching elements.
    *   `size(Set)`: The number of elements in a set.
*   **Conditional**:
    *   `if condition then val_true else val_false` — works for both numeric and boolean branches.
    *   Numeric: `if cond then 1 else 0` (returns `Real`)
    *   Boolean: `if cond then true else false` (returns `Bool`)

### 5.3. Interaction with Unknowns

Unknowns expose methods to interact with them in expressions:

*   **`Subset(S).has(e)`**: Returns `true` if element `e` is in the subset.
*   **`Mapping(A->B).is(a, b)`**: Returns `true` if `a` maps to `b`.

### 5.4. Comprehensions: `where` and `else`

Aggregates (`sum`, `count`, `any`, `all`) use **comprehensions** that support optional `where` and `else` clauses to filter and provide defaults:

```
aggregate( expression for var in Set [where condition] [else fallback] )
```

*   **`where`** filters which elements participate.
*   **`else`** provides a fallback value for elements that *don't* pass the filter.
*   You can use `else` without `where` (applies as a default for all non-matching cases).
*   You can use `where` without `else` (non-matching elements contribute 0 for `sum`/`count`, or are skipped for `any`/`all`).

```qsol
// Sum costs only for hired workers
sum(Cost[w] for w in Workers where Hired.has(w))

// Sum costs for hired workers, charge 0 for non-hired
sum(Cost[w] for w in Workers where Hired.has(w) else 0)

// Count how many workers are hired
count(w in Workers where Hired.has(w))

// Are all assigned workers experienced?
all(IsExperienced[w] for w in Workers where Assigned.has(w))
```

> [!IMPORTANT]
> **Quantifiers (`forall`, `exists`) do NOT support `where` or `else`.**
> They take a plain body expression: `forall x in S: body`.
>
> To achieve filtering inside a quantifier, use logical operators in the body:
>
> | You want... | Use this pattern |
> | :--- | :--- |
> | "For all x matching a condition" | `forall x in S: condition => body` |
> | "There exists an x matching a condition" | `exists x in S: condition and body` |

```qsol
// ❌ NOT valid: forall with where
// forall w in Workers where IsAvailable[w]: ...

// ✅ Correct: use implies (=>) in the body
forall w in Workers: IsAvailable[w] => Hired.has(w);

// ❌ NOT valid: exists with where
// exists w in Workers where IsExpert[w]: ...

// ✅ Correct: use and in the body
exists w in Workers: IsExpert[w] and Hired.has(w);
```

> [!TIP]
> **`all`/`any` vs `forall`/`exists`**: They express the same logic, but `all`/`any` are aggregates that support `where`/`else`, while `forall`/`exists` are quantifiers with a simpler syntax. Under the hood, the compiler desugars `all` → `forall` and `any` → `exists`, folding any `where`/`else` into the body automatically.
>
> ```qsol
> // These two are equivalent:
> all(IsExperienced[w] for w in Workers where Assigned.has(w))
> forall w in Workers: Assigned.has(w) => IsExperienced[w]
> ```

---

## 6. Macros and Functions

You can define reusable logic using `predicate` and `function`.

### 6.1. Predicates

Named boolean expressions.

```qsol
// Return type (: Bool) is optional
predicate is_expensive(w: Elem(Workers), t: Elem(Tasks)) = Cost[w, t] > 100;

must forall w in Workers: forall t in Tasks:
    Assignment.is(t, w) => not is_expensive(w, t);
```

### 6.2. Functions

Named numeric types.

```qsol
// Return type (: Real) is optional
function cost_impact(w: Elem(Workers)) =
    if Hired.has(w) then 10.0 else 0.0;
```

### Optional Return Types
As of the latest version, explicit return type annotations (`: Bool`, `: Real`) on predicates and functions are optional. The compiler infers strict boolean returns for predicates and numeric returns for functions.

---

## 7. Custom Unknown Types

QSOL allows you to define new high-level unknown structures by composing primitives.

A custom unknown definition has three parts:
1.  **`rep`**: The underlying representation (Subset, Mapping, or other custom types).
2.  **`laws`**: Invariants that must always hold for this structure.
3.  **`view`**: The public API (predicates/functions) exposed to the user.

### Example: `ExactSubset`

A subset that must choose exactly `k` elements.

```qsol
unknown ExactSubset(S, k) {
  rep {
    inner: Subset(S);
  }
  laws {
    must count(x in S where inner.has(x)) = k;
  }
  view {
    predicate has(x: Elem(S)) = inner.has(x);
  }
}

// Usage
find MyTeam : ExactSubset(Workers, 5);
param TeamLeader : Elem(Workers); // Declare parameter to use specific element
must MyTeam.has(TeamLeader);
```

---

## 8. Standard Library

QSOL comes with a powerful standard library. Use `use stdlib.<module>;` to import.

### 8.1. Logic (`stdlib.logic`)
Key helpers for constraints.
*   `exactly(k, expressions)`: True if exactly `k` expressions are true.
*   `atleast(k, expressions)`: True if at least `k` expressions are true.
*   `atmost(k, expressions)`: True if at most `k` expressions are true.
*   `iff(a, b)`, `xor(a, b)`: Logical equivalence and exclusive or.

```qsol
// Example: Exactly 2 workers are hired
must exactly(2, (Hired.has(w) for w in Workers));

// Example: Either task A or B is done, but not both
must xor(TaskDone.has(TaskA), TaskDone.has(TaskB));
```

### 8.2. Mappings
Advanced mapping types built on `Mapping`.

*   **`stdlib.injective_mapping`**: `InjectiveMapping(A, B)`
    *   No two elements in A map to the same element in B. (Requires size(B) >= size(A)).
*   **`stdlib.surjective_mapping`**: `SurjectiveMapping(A, B)`
    *   Every element in B is mapped to by at least one element in A.
*   **`stdlib.bijective_mapping`**: `BijectiveMapping(A, B)`
    *   One-to-one and onto. (Requires size(A) == size(B)).

    ```qsol
    // Example: Assign each task to a unique worker (if #Tasks <= #Workers)
    find Assignment : InjectiveMapping(Tasks, Workers);
    ```

### 8.3. Permutation (`stdlib.permutation`)
*   **`Permutation(S)`**:
    *   A bijection from a set S to itself. Useful for ordering problems (TSP, Scheduling).

    ```qsol
    // Example: TSP Route
    find Route : Permutation(Cities);
    // Route.map(city) gives the next city in the tour
    ```

---

## 9. CLI & Configuration

The `qsol` CLI tool manages the compilation and solving process.

### Common Commands

*   **`qsol inspect parse <file>`**: Check for syntax errors. (Useful: `--json`)
*   **`qsol inspect check <file>`**: Run type checking and validation.
*   **`qsol targets check <file>`**: Verify if the backend supports your model features.
*   **`qsol build <file>`**: Compile the model to artifacts (e.g., CQM/BQM files).
*   **`qsol solve <file>`**: Compile and run the solver.

### Configuration (`qsol.toml`)

Data and solver settings are defined in a TOML file.

```toml
schema_version = "1"

[entrypoint]
scenario = "default"
runtime = "local-dimod"

[scenarios.default]
problem = "MyProblem"

# Concrete Data for Sets
[scenarios.default.sets]
Workers = ["Alice", "Bob", "Charlie"]
Tasks = ["T1", "T2"]

# Concrete Data for Params
[scenarios.default.params]
MaxCost = 100.0
# Matrix param
[scenarios.default.params.Cost]
Alice = { T1 = 10.0, T2 = 50.0 }
Bob   = { T1 = 20.0, T2 = 20.0 }
...
```

### Runtimes
*   **`local-dimod`**: Runs locally using simulated annealing or exact solvers. Great for testing.
*   **`qiskit`**: Targets local IBM Quantum noisy simulators via QAOA.

---

## 10. Backend Limitations

The default `dimod-cqm-v1` backend supports linear and quadratic expressions over binary variables. If your model uses unsupported patterns (e.g., cubic terms, division by variables), the compiler emits a `QSOL3001` diagnostic.

> For a complete list of supported and unsupported patterns, see [Backend V1 Limits](docs/BACKEND_V1_LIMITS.md).

---

## 11. Extensibility

QSOL is designed to be extensible.
*   **Plugin Architecture**: You can write Python plugins to add new **Backends** (compile to new formats) or **Runtimes** (execute on new hardware).
*   **Custom Libraries**: You can distribute your own `.qsol` files with custom `unknown` types and macros.

---
*Happy Optimizing!* 🚀
