# Contributing to QSOL

## Purpose and Audience

This guide is for both human contributors and AI agents working in this repository.
QSOL contributions should preserve declarative clarity, diagnosability, and stage ownership across parser, sema, lowering, backend, and CLI layers.

## Local Setup

From repository root:

```bash
uv sync --extra dev
uv run qsol -h
```

Recommended one-time setup:

```bash
uv run pre-commit install
```

## Development Workflow

1. Create a branch using the `codex/*` naming convention.
2. Make focused changes scoped to one intent.
3. If user-visible behavior changes, update required documentation and tests.
4. Run mandatory quality gates before completion.
5. Include completion evidence and gate results in your final report.

Example branch creation:

```bash
git checkout -b codex/<short-topic>
```

## Mandatory Quality Gates

Run these commands before claiming completion:

```bash
uv run pre-commit run --all-files
uv run pytest
uv run python examples/run_equivalence_suite.py
```

Docs-only changes are not exempt.

These same gates run automatically in CI via GitHub Actions on every push and pull request to `main`. See `.github/workflows/ci.yml`.

## Behavior-Change Docs/Test Matrix (Summary)

| Change type | Required docs updates | Required tests updates |
| --- | --- | --- |
| CLI flags/defaults/output/behavior | `README.md`, `docs/tutorials/03-compiling-running-and-reading-results.md` | `tests/cli/` |
| Language syntax/semantic behavior | `QSOL_reference.md`, `docs/QSOL_SYNTAX.md`, relevant `docs/tutorials/` | Parser/sema/lower/backend/cli tests under `tests/` |
| Backend artifact/schema/output interpretation | `README.md`, `docs/tutorials/03-compiling-running-and-reading-results.md` | `tests/backend/` and `tests/cli/` |
| Internal refactor (no user-visible behavior) | Docs optional; update `docs/CODEBASE.md` if architecture meaningfully changes | Affected tests as needed |
| Docs-only changes | Changed docs only | Test changes optional unless behavior statements change |

## Vision Coherence Checklist

Before completion, verify coherence against `VISION.md`.
Use the contribution rubric and ensure these checks are explicitly addressed:

1. Declarative clarity reinforced
2. Semantics clearer or unchanged
3. Diagnosability preserved
4. Stage ownership respected
5. Docs/tests updated where behavior changed
6. User-facing behavior coherent with project purpose

Reference: `VISION.md`

## Agent-Specific Policy

Agents must follow repository execution/completion policy in `AGENTS.md`, including:

- Mandatory VISION pre-read and coherence check
- Grammar safety gate when grammar/parser behavior changes
- Mandatory completion evidence checklist format
- Mandatory quality gates

Reference: `AGENTS.md`
