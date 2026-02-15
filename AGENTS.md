# AGENTS Policy for QSOL

## Purpose and Scope

This policy applies to all work in the QSOL codebase.

Audience: AI coding agents and human contributors.

Policy tone is strict and normative:
- `MUST` means required.
- `MUST NOT` means prohibited.
- `SHOULD` means strongly recommended unless there is a documented reason not to.

## Definition of Done (DoD)

A task is complete only when all applicable items below are satisfied.

1. Required code, tests, and documentation updates are present.
2. Required CLI documentation and CLI tests are updated when CLI behavior changes.
3. Mandatory quality gates pass.
4. Completion evidence is provided in the required checklist format.
5. Vision coherence gates are satisfied (pre-read + end-of-task coherence verification).
6. If grammar changes, grammar and semantic regression validation confirms no unintended language changes.

A task is not done if any required gate fails or any required docs/tests update is missing.

Documentation scope rule (`behavior-change only`):
- If user-visible behavior changes, docs `MUST` be updated.
- If user-visible behavior does not change, docs updates are optional (but encouraged for clarity).

## Vision Coherence Gates

Contributors/agents `MUST` read `/Users/gbisi/Documents/code/qsol/VISION.md` before design or implementation work starts.

Contributors/agents `MUST` verify final change coherence against the mandatory rubric in `/Users/gbisi/Documents/code/qsol/VISION.md` before claiming completion.

## Grammar Change Safety Gate

This gate applies whenever language grammar or parser behavior is changed (for example `qsol/src/qsol/parse/grammar.lark` and related parser/AST builder logic).

Contributors/agents `MUST` verify all of the following:
- The new grammar is syntactically correct and parser tests pass.
- There are no unintended or non-forecasted language acceptance/rejection changes.
- Language semantics remain correct and coherent across parser/sema/lower/backend stages for affected constructs.

If unintended changes or semantic risks are detected, contributors/agents `MUST`:
- report findings to the user clearly,
- provide concrete fix proposals/tradeoffs,
- wait for explicit user approval before continuing implementation.

## Mandatory Quality Gates

Before claiming task completion, contributors/agents `MUST` run:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
```

Coverage policy:
- `uv run pytest` `MUST` pass including coverage requirements defined in repository configuration.
- Coverage threshold values are inherited from `qsol/pyproject.toml` and `MUST NOT` be duplicated as hardcoded policy here.

Examples equivalence suite policy:
- `uv run python examples/run_equivalence_suite.py` `MUST` exit 0 (all example equivalence scripts pass by their own criteria).

Docs-only changes:
- Docs-only edits are not exempt.
- All mandatory gates still `MUST` pass.

## Required Change Matrix

Use this matrix to determine required updates for each change class.

| Change type | Required documentation updates | Required test updates | Enforcement |
| --- | --- | --- | --- |
| CLI flags/defaults/output/behavior changes | Update `qsol/README.md` (CLI reference/usage sections) and `qsol/docs/tutorials/03-compiling-running-and-reading-results.md` | Update relevant tests under `qsol/tests/cli/` | Mandatory |
| Language syntax/semantic behavior changes (including grammar edits) | Update as applicable: `qsol/QSOL_reference.md`, `qsol/docs/QSOL_SYNTAX.md`, and relevant files in `qsol/docs/tutorials/` | Update stage-specific tests under parser/sema/lower/backend/cli folders in `qsol/tests/`, and verify no unintended grammar/semantic regressions | Mandatory |
| Backend artifact/schema/output interpretation changes | Update `qsol/README.md` (output artifacts/usage) and `qsol/docs/tutorials/03-compiling-running-and-reading-results.md` | Update relevant backend and CLI tests under `qsol/tests/backend/` and `qsol/tests/cli/` | Mandatory |
| Internal refactor with no user-visible behavior change | Docs optional; `qsol/docs/CODEBASE.md` `SHOULD` be updated when architecture/module responsibilities materially change | Update affected tests as needed to preserve correctness | Quality gates still mandatory |
| Docs-only changes | Update changed docs for accuracy and consistency | Test changes not required unless behavior statements change | Both mandatory gates still required |

## Completion Evidence (Mandatory Checklist)

Completion claims `MUST` include the following checklist. Omission of any item is non-compliant.

```text
DoD Checklist
- Behavior impact: <yes/no> - <one-line statement>
- Docs updated: <file list> OR <none needed - reason>
- CLI impact: <yes/no> - <tests updated: file list or none>
- VISION pre-read: <yes/no> - <principles considered>
- Vision coherence check: <yes/no> - <one-line rationale>
- Grammar changed: <yes/no> - <files touched or N/A>
- Grammar/semantic regression check: <pass/fail/N.A.> - <scope and summary>
- Gate: uv run pre-commit run --all-files -> <pass/fail>
- Gate: uv run pytest -> <pass/fail>
- Gate: uv run python examples/run_equivalence_suite.py -> <pass/fail>
```

Contributors/agents `MUST NOT` claim completion without this checklist.

## Failure and Escalation Rules

- If any required gate fails, contributors/agents `MUST` report failure and `MUST NOT` mark the task complete.
- If required docs or CLI updates are missing, the task `MUST` be treated as incomplete.
- Missing either `VISION pre-read` or `Vision coherence check` evidence means the task is incomplete, even if tests pass.
- If grammar changed and grammar/semantic regression evidence is missing, the task is incomplete.
- If unintended grammar/semantic changes are found, implementation `MUST` pause until user approval is received on a proposed fix path.

## Public API / Interface Policy Note

- This policy does not change runtime Python APIs or CLI interfaces by itself.
- This file is the authoritative repository execution/completion governance policy for work performed in this codebase.

## Validation Scenarios (Policy Self-Checks)

1. CLI option changed in `qsol/src/qsol/cli.py`:
   - Must update CLI docs and `qsol/tests/cli/`.
   - Must pass both mandatory gates.
2. Language parser/type behavior changed:
   - Must update `qsol/QSOL_reference.md` and syntax/tutorial docs as applicable.
   - Must add/update stage-appropriate tests.
3. Docs-only correction:
   - Must still run and pass `uv run pre-commit run --all-files` and `uv run pytest`.
4. Internal backend refactor without behavior change:
   - User docs may remain unchanged.
   - `qsol/docs/CODEBASE.md` should be updated when architecture meaningfully changes.
   - Mandatory gates still apply.
5. Completion report omits gate status lines:
   - Report is non-compliant and task is incomplete.
6. Completion report omits `VISION pre-read`:
   - Report is non-compliant and task is incomplete.
7. Completion report omits `Vision coherence check`:
   - Report is non-compliant and task is incomplete.
8. Grammar changed but grammar/semantic regression evidence is missing:
   - Report is non-compliant and task is incomplete.
9. Unexpected grammar/semantic drift is found:
   - Contributor/agent must stop, propose fixes, and wait for explicit user approval.
