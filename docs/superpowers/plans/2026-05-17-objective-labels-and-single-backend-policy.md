# Objective Labels And Single-Objective Backend Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add objective labels and prevent `dimod-cqm-v1` from silently summing multiple objective statements.

**Architecture:** Keep objective labels as metadata on AST and Kernel IR objectives. Validate label uniqueness during semantic validation. Keep ordered multi-objective semantics out of backend code for now by rejecting multiple objectives in the single-objective backend with an explicit diagnostic.

**Tech Stack:** Python, Lark grammar, dataclass AST/KIR nodes, pytest, QSOL diagnostics.

---

### Task 1: Objective Label Parsing And Propagation

**Files:**
- Modify: `src/qsol/parse/grammar.lark`
- Modify: `src/qsol/parse/ast.py`
- Modify: `src/qsol/parse/ast_builder.py`
- Modify: `src/qsol/lower/ir.py`
- Modify: `src/qsol/lower/lower.py`
- Test: `tests/parser/test_parser.py`
- Test: `tests/lower/test_desugar_and_lower_branches.py`

- [ ] **Step 1: Write failing parser/lower tests**

Add tests proving `minimize expr as label;` parses and the label survives lowering to `KObjective`.

- [ ] **Step 2: Run focused tests to verify red**

Run:

```bash
uv run pytest tests/parser/test_parser.py::test_parse_objective_labels tests/lower/test_desugar_and_lower_branches.py::test_objective_label_survives_lowering -q
```

Expected: fail because labels are not parsed or stored.

- [ ] **Step 3: Implement label fields and grammar**

Add optional `objective_label: "as" NAME`, store `label: str | None` on `Objective` and `KObjective`, and preserve it in lowering.

- [ ] **Step 4: Run focused tests to verify green**

Run:

```bash
uv run pytest tests/parser/test_parser.py::test_parse_objective_labels tests/lower/test_desugar_and_lower_branches.py::test_objective_label_survives_lowering -q
```

Expected: pass.

### Task 2: Duplicate Objective Label Validation

**Files:**
- Modify: `src/qsol/sema/validate.py`
- Test: `tests/sema/test_typecheck.py`

- [ ] **Step 1: Write failing validation test**

Add a test showing duplicate labels in one problem produce a semantic diagnostic.

- [ ] **Step 2: Run focused test to verify red**

Run:

```bash
uv run pytest tests/sema/test_typecheck.py::test_duplicate_objective_labels_are_rejected -q
```

Expected: fail because duplicate labels are not checked.

- [ ] **Step 3: Implement uniqueness validation**

In `validate_program`, scan objectives per problem and emit `QSOL2101` when a label repeats.

- [ ] **Step 4: Run focused test to verify green**

Run:

```bash
uv run pytest tests/sema/test_typecheck.py::test_duplicate_objective_labels_are_rejected -q
```

Expected: pass.

### Task 3: Backend Rejects Multiple Objectives

**Files:**
- Modify: `src/qsol/backend/dimod_codegen.py`
- Test: `tests/backend/test_compile.py`

- [ ] **Step 1: Write failing backend test**

Add a test showing two objective statements produce a diagnostic and no silent scalarization.

- [ ] **Step 2: Run focused test to verify red**

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_compile_rejects_multiple_objectives_for_dimod_backend -q
```

Expected: fail because the backend currently sums objectives.

- [ ] **Step 3: Implement diagnostic**

Before objective emission, reject `len(problem.objectives) > 1` with `QSOL3201` and clear help. Do not set a summed objective for that problem.

- [ ] **Step 4: Run focused test to verify green**

Run:

```bash
uv run pytest tests/backend/test_compile.py::test_compile_rejects_multiple_objectives_for_dimod_backend -q
```

Expected: pass.

### Task 4: Documentation

**Files:**
- Modify: `QSOL_reference.md`
- Modify: `docs/QSOL_SYNTAX.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/BACKEND_V1_LIMITS.md`

- [ ] **Step 1: Document labels and backend policy**

State that objective labels use `as NAME`, labels are metadata, labels must be unique per problem, source order defines ordered objective intent, and `dimod-cqm-v1` rejects multiple objective statements until explicit scalarization exists.

- [ ] **Step 2: Run docs-related focused tests**

Run:

```bash
uv run pytest tests/parser/test_parser.py::test_parse_objective_labels tests/sema/test_typecheck.py::test_duplicate_objective_labels_are_rejected tests/backend/test_compile.py::test_compile_rejects_multiple_objectives_for_dimod_backend -q
```

Expected: pass.

### Task 5: Required Gates

**Files:**
- No code files.

- [ ] **Step 1: Run mandatory gates**

Run:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
```

Expected: all pass before claiming completion.
