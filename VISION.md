# QSOL Vision and Design Principles

## Project Purpose

QSOL exists to make combinatorial optimization models explicit, reviewable, and reliable.
The project prioritizes correctness, explainability, and reproducibility over opaque convenience.
Contributors must treat QSOL as language infrastructure, not only as a thin wrapper around a solver.

## Language Vision

QSOL should let users state optimization intent declaratively:
- what sets, parameters, unknowns, constraints, and objectives mean;
- not how a solver algorithm should be written procedurally.
- not low-level encoding or runtime implementation details.

The language should remain readable by domain experts, stable for tooling, and strict enough to catch modeling mistakes early with actionable diagnostics.
QSOL should preserve high-level abstraction as a primary objective and hide low-level implementation mechanics from end users unless explicitly needed for diagnostics.

## Core Principles

1. Declarative modeling first.
   Why: users should describe the problem semantics, while the compiler handles translation details.

2. Correctness and diagnosability over hidden magic.
   Why: predictable behavior and clear errors are more valuable than implicit transformations that are hard to trace.

3. Explicit modeling semantics over backend convenience.
   Why: language rules must be coherent at the model level, even when backend support is intentionally narrow.

4. Reproducibility and inspectable artifacts.
   Why: generated artifacts, logs, and mappings must make runs auditable and comparable across environments.

5. Incremental extensibility through staged compiler design.
   Why: clear stage boundaries allow safe evolution without destabilizing unrelated parts of the system.

6. High-level abstraction over low-level exposure.
   Why: users should think in model semantics, not backend encoding details; low-level mechanics belong inside compiler/runtime internals.

## Why This Architecture (Compiler + Runtime)

QSOL uses a staged compiler-plus-runtime flow:

`parse -> sema -> desugar/lower -> ground -> codegen -> artifacts -> run`

- Parse: convert text into structured syntax with spans for precise diagnostics.
- Sema: resolve symbols and types before expensive backend work.
- Desugar/lower: normalize surface forms into a smaller kernel for predictable codegen.
- Ground: apply instance data so backend operations run on concrete domains.
- Codegen: produce backend models and exports from normalized IR.
- Artifacts: emit inspectable outputs (`model.cqm`, `model.bqm`, exports, maps, logs, explain data).
- Run: sample generated models while preserving traceability through persisted outputs.

This separation improves reliability (fewer cross-stage side effects), debugging (failures localize to stages), and evolution (new features can be added stage-by-stage with targeted tests).

## Major Design Decisions (ADR-lite)

| Decision | Why | Tradeoff | Implication for Contributors |
| --- | --- | --- | --- |
| Declarative DSL instead of imperative solver scripting | Keeps model intent explicit and domain-facing | Some advanced backend tricks are less direct to express | Preserve semantic clarity when adding syntax/features |
| Stage-separated compiler pipeline | Enables isolated reasoning, diagnostics, and testing by phase | More internal abstractions to maintain | Place logic in the correct stage; avoid cross-stage leakage |
| Stable diagnostics and explicit unsupported-shape reporting | Users get actionable errors instead of silent degradation | Requires ongoing discipline in error taxonomy and spans | Add/maintain diagnostic codes and clear messages for new behavior |
| Artifact-first backend outputs (`CQM/BQM`, exports, `explain`, `log`) | Supports inspection, reproducibility, and offline analysis | Extra output management and docs upkeep | Keep output contracts stable and documented when behavior changes |
| Narrow v1 backend scope with explicit constraints | Protects correctness while the language surface grows | Some parse/type-valid programs are not backend-compilable yet | Reject unsupported forms explicitly; do not mask limitations |

## Non-Goals and Boundaries

- QSOL is not currently optimized for maximal backend feature coverage at any cost.
- QSOL is not a generic imperative optimization scripting framework.
- QSOL does not prioritize implicit coercions or permissive semantics that weaken model clarity.
- QSOL does not treat runtime sampling convenience as a substitute for compiler-stage correctness.

Contributions that expand capability must not erode semantic clarity, diagnosability, or stage discipline.

## Contribution Coherence Rubric (Mandatory)

Before finalizing any contribution, answer each question with `yes` or `no`:

1. Does this change reinforce declarative clarity?
2. Are semantics clearer or at least unchanged?
3. Does it preserve diagnosability (errors, spans, codes)?
4. Is stage ownership respected (parser/sema/lower/backend boundaries)?
5. Are docs/tests updated where behavior changed?
6. Is user-facing behavior consistent with project purpose?

A contribution is not coherent with project intent unless these checks are addressed explicitly in completion evidence.

## How to Use This Document During Work

Before start:
- Read this file.
- Select the specific principles and decisions relevant to the task.

Before completion:
- Run the mandatory coherence rubric.
- Report how the final change aligns with project purpose and principles.
- If tradeoffs are introduced, state them explicitly with rationale.
