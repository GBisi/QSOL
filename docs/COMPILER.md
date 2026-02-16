# QSOL Compiler Architecture

The QSOL compiler translates high-level declarative models into low-level representations suitable for optimization backends.

## 1. Compilation Pipeline

The pipeline consists of the following stages:

### Frontend
1.  **Parsing**: Converts `.qsol` source text into an Abstract Syntax Tree (AST).
2.  **Module Resolution**: Resolves `use` statements and loads referenced modules.
3.  **Elaboration**: Expands `unknown` types and macros into primitive structures and constraints.
4.  **Name Resolution**: Links identifiers to their definitions and builds a symbol table.
5.  **Type Checking**: Verifies type safety of expressions and constraints.
6.  **Validation**: Checks for semantic errors (e.g., unused variables, invalid constructs).
7.  **Lowering**: Transforms the validated AST into a symbolic Kernel IR (KIR).

### Middle / Grounding
If instance data is provided (via `model.qsol.toml`), the compiler performs **instantiation**:
1.  **Loading**: Reads data from the TOML file.
2.  **Binding**: Maps data values to model `set` and `param` declarations.
3.  **Grounding**: Unrolls quantifiers (`forall`, `exists`) and expands data-dependent expressions, producing a Ground IR (GIR).

### Backend / Targeting
1.  **Target Selection**: Identifies the target runtime and backend (e.g., `local-dimod` + `dimod-cqm-v1`).
2.  **Support Check**: Verifies that the selected backend supports all features used in the Ground IR.
3.  **Compilation**: The backend translates the Ground IR into its native format (e.g., a `dimod.ConstrainedQuadraticModel`).
4.  **Export**: Artifacts are written to disk.

## 2. Output Directory Structure

When running `qsol build` or `qsol solve`, the compiler generates an output directory (default: `outdir/<model_name>`).

### Standard Artifacts

*   **`model.json`**: The compiled model in a backend-agnostic or backend-specific JSON format (depends on the backend). For `dimod-cqm-v1`, this might not be present if it uses opaque binary objects, but typically backends produce some representation here.
*   **`capabilities.json`**: A report of the capabilities required by the model and whether the selected backend supports them.
*   **`run.json`** (for `solve`): The results of the execution, including:
    *   **energy**: The objective value of the best solution.
    *   **sample**: The raw variable assignments.
    *   **selected_assignments**: A user-friendly list of active variables (e.g., `Picked.has(apple)`).
*   **`solutions.json`** (optional): If multiple solutions are requested, they may be stored here.

## 3. Intermediate Representations (IR)

### Kernel IR (KIR)
A symbolic representation where sets and parameters are still abstract names. This is useful for analyzing the structure of the model without specific data.

### Ground IR (GIR)
A concrete representation where all sets are finite collections of values, and all expressions are fully expanded. This is the input to the backend plugins.
