# QSOL Roadmap

This roadmap is organized as `Now`, `Next`, and `Later` priorities.
Each item includes an acceptance note to make progress measurable.

## Now

- [ ] Stabilize onboarding and documentation accuracy.
  Acceptance: README quickstart commands run as written, links resolve, and docs are consistent with current CLI behavior.
- [ ] Keep backend-v1 boundaries explicit and discoverable.
  Acceptance: unsupported-shape expectations are clearly documented and aligned with `QSOL3001` diagnostics.
- [ ] Improve artifact interpretation guidance for first-time users.
  Acceptance: tutorials and top-level docs clearly explain `model.bqm`, exports, `varmap.json`, `explain.json`, and `run.json`.

## Next

- [ ] Broaden backend-supported expression patterns while preserving semantics.
  Acceptance: newly supported constructs are covered by parser/sema/lower/backend tests and documented with examples.
- [ ] Increase diagnostics depth and fix guidance.
  Acceptance: new failure modes include stable codes, spans, and concrete `help` text.
- [ ] Expand end-to-end examples for realistic optimization tasks.
  Acceptance: at least one additional production-style example includes model, instance, and equivalence/behavior checks.

## Later

- [ ] Expand language/runtime capabilities beyond current backend-v1 limits.
  Acceptance: feature rollout is staged across grammar, sema, lower, backend, tests, and docs with no regressions.
- [ ] Explore broader backend/runtime integration options.
  Acceptance: architecture decisions are documented with tradeoffs and validated by integration tests.
- [ ] Strengthen tooling ecosystem for authoring and review workflows.
  Acceptance: editor/tooling improvements are documented and verified against current language features.
