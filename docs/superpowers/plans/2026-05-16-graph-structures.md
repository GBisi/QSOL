# Graph Structures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add compiler-owned static graph structures with dotted static domains and predicates, while keeping existing `set` and `relation` syntax.

**Architecture:** Add `structure Name = Constructor(args);` as a problem declaration. Register `UndirectedGraph` and `DirectedGraph` instances in sema, expose synthetic static domains such as `G.edges` and `G.non_edges`, and materialize those domains during grounding from existing set/relation data. Dotted domain names are stored in the existing string domain fields to keep the first implementation narrow.

**Tech Stack:** Python dataclasses, Lark grammar, existing QSOL parser/sema/lower/grounder/estimator pipeline, pytest.

---

### Task 1: Parser And AST

**Files:**
- Modify: `src/qsol/parse/grammar.lark`
- Modify: `src/qsol/parse/ast.py`
- Modify: `src/qsol/parse/ast_builder.py`
- Test: `tests/parser/test_parser.py`

- [ ] Add failing parser tests for `structure G = UndirectedGraph(V, Edge);` and dotted domains in `forall`, comprehensions, `find Selected[G.edges]`, and `size(G.edges)`.
- [ ] Add `StructureDecl` to the AST and parse `structure` declarations as problem statements.
- [ ] Add a `DomainRef` expression for `G.edges` and allow dotted domain references in binder, find-index, and size-call positions.
- [ ] Run parser tests and confirm they pass.

### Task 2: Sema And Structure Types

**Files:**
- Modify: `src/qsol/sema/types.py`
- Modify: `src/qsol/sema/symbols.py`
- Modify: `src/qsol/sema/resolver.py`
- Modify: `src/qsol/sema/typecheck.py`
- Test: `tests/sema/test_typecheck.py`

- [ ] Add failing sema tests for accepted `UndirectedGraph(V, Edge)`, rejected ternary/wrong-set graph relations, `G.adjacent`, `G.nonedge`, tuple binders over `G.edges`, and scalar find indexing over `G.edges`.
- [ ] Add `StructureInstanceType` and `STRUCTURE` symbol kind.
- [ ] Resolve graph structure declarations and expose synthetic domains:
  - `G.vertices` as the original set type.
  - `G.edges` and `G.non_edges` as binary relation types over `V`.
  - `D.vertices`, `D.arcs`, and `D.non_arcs` for directed graphs.
- [ ] Typecheck graph method calls as static boolean predicates with element arguments from the graph vertex set.
- [ ] Run sema tests and confirm they pass.

### Task 3: Lowering And Grounding

**Files:**
- Modify: `src/qsol/lower/ir.py`
- Modify: `src/qsol/lower/lower.py`
- Modify: `src/qsol/lower/globals.py`
- Modify: `src/qsol/backend/instance.py`
- Test: `tests/backend/test_compile.py`

- [ ] Add failing grounding tests for canonical `G.edges`, `G.non_edges`, directed `D.arcs`, and `D.non_arcs`.
- [ ] Carry structure declarations into kernel IR.
- [ ] Materialize graph domains after base and derived relations are available.
- [ ] Evaluate `G.adjacent(u, v)` and `G.nonedge(u, v)` as static graph lookups during grounding.
- [ ] Reject self-loops in v1 graph structures and warn for symmetric duplicate orientations in undirected graphs.
- [ ] Run backend compile tests and confirm they pass.

### Task 4: Estimate, Docs, Examples, And Deferred Work

**Files:**
- Modify: `src/qsol/compiler/estimate.py`
- Modify: `docs/STDLIB.md`
- Modify: `QSOL_reference.md`
- Modify: `docs/QSOL_SYNTAX.md`
- Modify: `docs/TUTORIAL.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/COMPILER.md`
- Modify: `README.md`
- Modify: `examples/tutorials/graph_helpers.qsol`
- Create/modify: `TODO.md`
- Test: `tests/compiler/test_estimate.py`

- [ ] Add failing estimate test that structure declarations create zero variables and `find Selected[G.edges] : Bool` counts canonical graph edges.
- [ ] Report structure summaries in estimate output.
- [ ] Document `structure`, `UndirectedGraph`, `DirectedGraph`, dotted domains, and graph diagnostics.
- [ ] Add `TODO.md` with MUST/NICE checkboxes for later primitive-domain refactoring of sets and relations.
- [ ] Run focused tests.
- [ ] Run mandatory gates:
  - `uv run pre-commit run --all-files`
  - `uv run pytest`
  - `uv run python examples/run_equivalence_suite.py`

### Self-Review

- Spec coverage: The plan covers parser, AST, sema, graph typing, lowering, grounding, estimate, docs, examples, and the requested deferred TODO.
- Placeholder scan: No implementation placeholders remain in the execution tasks.
- Scope control: User-defined structures, plugin lowerings, generic primitive-domain refactors, and reusable constraint declarations remain out of scope.
