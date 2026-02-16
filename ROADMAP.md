# QSOL Roadmap

This roadmap is organized as `Now`, `Next`, and `Later` priorities.
Each item includes an acceptance note to make progress measurable.

## Now

- [x] Stabilize onboarding and documentation accuracy.
  Acceptance: README quickstart commands run as written, links resolve, and docs are consistent with current CLI behavior.
- [x] Keep backend-v1 boundaries explicit and discoverable.
  Acceptance: unsupported-shape expectations are clearly documented and aligned with `QSOL3001` diagnostics.
- [x] Improve artifact interpretation guidance for first-time users.
  Acceptance: tutorials and top-level docs clearly explain `model.bqm`, exports, `varmap.json`, `explain.json`, and `run.json`.

## Next

- [ ] Broaden backend-supported expression patterns while preserving semantics.
  Acceptance: newly supported constructs are covered by parser/sema/lower/backend tests and documented with examples.
- [ ] Expand user-defined `function` return types beyond `Real`.
  Acceptance: `Bool`, bounded `Int[...]`, and `Elem(Set)` return annotations are supported end-to-end (grammar, sema, lowering, diagnostics, docs, and tests).
- [ ] Add variadic formal parameters/call-site support for macros.
  Acceptance: syntax and expansion support `...` signatures/calls (for example `exactly(k, ...)`) with arity/type diagnostics and full regression coverage.
- [ ] Define migration/compatibility policy for future macro typing extensions.
  Acceptance: docs specify versioned compatibility guarantees and migration notes for macro syntax/typing changes.
- [ ] Increase diagnostics depth and fix guidance.
  Acceptance: new failure modes include stable codes, spans, and concrete `help` text.
- [ ] Expand end-to-end examples for realistic optimization tasks.
  Acceptance: at least one additional production-style example includes model, instance, and equivalence/behavior checks.
- [ ] Custom weights for constraints.
  Acceptance: `must` constraints accept an optional weight parameter (e.g. `must(expr, weight: 5.0)`); weighted constraints are propagated through sema, lowering, and backend; docs and tests cover weighted vs. hard constraints.
- [ ] Explainable constraints — richer constraint metadata for debugging and insight.
  Acceptance: constraints can carry user-supplied labels/descriptions; `explain.json` output includes constraint names, weights, and satisfaction status; docs explain how to annotate and interpret constraints.
- [ ] Parameter validation and preconditions on instances.
  Acceptance: models can declare preconditions on parameters (e.g. `require size(V) % 2 == 0`, `require U[e] != W[e]`, `require U[e] in V`); violations produce clear diagnostics at instance-load time with span and message; grammar, sema, and tests cover `require` declarations.
- [ ] Selective imports.
  Acceptance: `use` syntax supports named imports (e.g. `from stdlib use exactly, atmost`); unused-import diagnostics are emitted; grammar, sema, docs, and tests are updated.

## Later

- [ ] Expand language/runtime capabilities beyond current backend-v1 limits.
  Acceptance: feature rollout is staged across grammar, sema, lower, backend, tests, and docs with no regressions.
- [ ] Gate-based quantum backend support beyond QAOA.
  Acceptance: at least one gate-based formulation (e.g. VQE or Grover-based) is supported as an alternative backend; architecture docs describe the gate model mapping; integration tests validate correctness against known solutions.
- [ ] Additional runtime integrations.
  Acceptance: at least one new runtime beyond the current set is supported (e.g. Azure Quantum, Amazon Braket, or a classical solver); runtime selection is configurable; integration tests and docs cover setup and usage.
- [ ] Explore broader backend/runtime integration options.
  Acceptance: architecture decisions are documented with tradeoffs and validated by integration tests.
- [ ] Managing multiple objective functions.
  Acceptance: models can declare more than one `minimize`/`maximize` objective; multi-objective strategy (weighted sum, Pareto, lexicographic) is configurable; sema, lowering, backend, docs, and tests are updated.
- [ ] Strengthen tooling ecosystem for authoring and review workflows.
  Acceptance: editor/tooling improvements are documented and verified against current language features.
