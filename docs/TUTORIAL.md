# QSOL Tutorial

Welcome to QSOL! This tutorial will guide you through writing your first QSOL model, compiling it, and running it.

## 1. Introduction

QSOL (Quantum/Quadratic Specification-oriented Optimisation Language) is a high-level, declarative language for modeling optimization problems. It allows you to focus on *what* the problem is, rather than *how* to solve it. QSOL compilers translate your high-level model into a format that can be solved by various optimization backends, including classical solvers and quantum hybrid solvers.

## 2. Prerequisites

Ensure you have QSOL installed. You can verify the installation by running:

```bash
qsol --help
```

## 3. Your First Model

Let's solve a simple problem: finding a subset of items that meets certain criteria.
Save the following code as `model.qsol`.

```qsol
// model.qsol
problem MyFirstModel {
    // 1. Define Sets representing your data
    set Items;

    // 2. Define Paramters (optional data values)
    param Weights[Items] : Real;

    // 3. Define the Unknown you want to find
    // Here we want to find a subset of Items
    find Picked : Subset(Items);

    // 4. Define Constaints
    // We must pick at least one item
    must count(i for i in Items where Picked.has(i)) >= 1;

    // 5. Define Objective
    // Minimize the total weight of picked items
    minimize sum(Weights[i] for i in Items where Picked.has(i));
}
```

## 4. Preparing Data

QSOL models separate logic from data. You provide data in a separate TOML configuration file.
Save the following as `model.qsol.toml`:

```toml
# model.qsol.toml
schema_version = "1"

[scenarios.default]
[scenarios.default.sets]
Items = ["apple", "banana", "cherry"]

[scenarios.default.params]
Weights = { apple = 2.5, banana = 1.0, cherry = 3.0 }

[scenarios.default.execution]
runtime = "local-dimod"
backend = "dimod-cqm-v1"
```

## 5. Compiling and Running

To solve the model, you use the `qsol solve` command. This compiles your model, combines it with the data, and runs it using a solver backend.

```bash
qsol solve model.qsol
```

By default, this will use the `local-dimod` runtime and `dimod-cqm-v1` backend, which runs a classical Simulated Annealing solver locally on your machine.

You should see output indicating the best solution found, for example:

```
...
Solutions:
  - Energy: 1.0
  - Assignment:
    - Picked.has(banana)
```

## 6. Using the Standard Library

QSOL comes with a powerful standard library (`stdlib`) that provides common patterns and logical helpers.

For example, let's use `stdlib.logic` to simplify our constraints, and `stdlib.permutation` to solve a different problem.

```qsol
use stdlib.logic;
use stdlib.permutation;

problem Ordering {
    set Guests;

    // Find a permutation (ordering) of guests
    find Seating : Permutation(Guests);

    // Use stdlib logic helpers
    // 'iff' means "if and only if"
    // 'xor' means "exclusive or"
    must forall g in Guests:
        iff(Seating.is(g, g), false); // No one sits in their original spot

    minimize 0; // Just find a valid configuration
}
```

## 7. Next Steps

- **[CLI Reference](CLI.md)**: Learn about all `qsol` commands and options.
- **[Standard Library](STDLIB.md)**: Explore available modules in `stdlib`.
- **[Language Reference](../QSOL_reference.md)**: Deep dive into QSOL semantics and features.
