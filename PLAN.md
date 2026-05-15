# QSOL Finite-Domain Scalar Release Plan

## Summary
Implement the release as two staged milestones. Milestone 1 ships the foundation: derived `Range` sets, bounded scalar `Bool`/`Int` decisions, indexed scalar decisions, CQM-native backend support, scalar decoding, estimates, docs, and examples. Milestone 2 adds `DiscreteReal`, safe `abs/max/min` lowering, and first graph/order/scheduling library ergonomics on top of that substrate.

The main rule: do not mix foundational `find`/IR/backend refactors with later modeling sugar in one large patch. Each milestone must preserve existing `Subset`, `Mapping`, custom unknowns, macro expansion, target checks, build, and solve behavior.

## Key Public Changes
- New set syntax:
  ```qsol
  set Positions = Range(1, size(V));
  ```
  `Range(lo, hi)` is inclusive. No `step` in Milestone 1.

- New scalar decision syntax:
  ```qsol
  find b : Bool;
  find T : Int[0 .. Total];
  find Load[Machines] : Int[0 .. Total];
  ```
  Bounds must be scenario-time integer constants: literals, scalar params, arithmetic over those, and `size(Set)`.

- Keep existing unknown syntax unchanged:
  ```qsol
  find S : Subset(V);
  find F : Mapping(A -> B);
  find X : CustomUnknown(A);
  ```

- New CLI:
  ```bash
  qsol inspect estimate model.qsol -c model.qsol.toml
  qsol targets check model.qsol -c model.qsol.toml --estimate
  ```

- Milestone 2 syntax:
  ```qsol
  find y : DiscreteReal[0.0 .. 10.0 step 0.1];
  minimize abs(expr);
  minimize max(load(m) for m in Machines);
  maximize min(score(a) for a in Agents);
  ```

## Implementation Changes
### 1. Regression Safety Net
- Add tests that lock current behavior before touching `FindDecl`:
  - parse/check/lower/build for `Subset`, `Mapping`, custom unknowns, `Comp(...)` macros, `stdlib.logic`, and current examples.
  - CLI tests for `inspect parse`, `inspect check`, `inspect lower`, `targets check`, `build`, and `solve`.
- Expected result: all existing behavior still passes after each milestone.

### 2. AST, Grammar, And IR Foundation
- Update parser/AST around `src/qsol/parse/grammar.lark`, `src/qsol/parse/ast.py`, and `src/qsol/lower/ir.py`.
- Add `SetDecl.expr` with `RangeSetExpr(lo, hi)`.
- Replace `FindDecl.unknown_type` with:
  ```python
  FindDecl(name, indices, decision_type)
  ```
  where `decision_type` is one of:
  - `UnknownDecisionType(UnknownTypeRef)`
  - `BoolDecisionType`
  - `IntDecisionType(lo, hi, encoding=None)`
- Preserve compatibility with old unknown finds by wrapping them as `UnknownDecisionType`.
- Kernel/Ground IR must carry derived-set metadata and scalar decision domains, not erase them into generic unknowns.

### 3. Semantic Model
- Add semantic types:
  - numeric range element type, e.g. `ElemOfType(set_name, numeric_kind="Int")`
  - scalar decision type for bare `Bool`/`Int`
  - indexed scalar decision type for `Load[m]`
- Typechecker behavior:
  - `T` from `find T : Int[...]` is numeric.
  - `b` from `find b : Bool` is boolean.
  - `Load[m]` returns the scalar value type.
  - bracket access still works for params.
  - arithmetic on opaque set elements remains rejected.
  - arithmetic/comparison on range binders is accepted.
- Add scenario-constant expression validation:
  - accept literals, scalar params, `size(Set)`, and arithmetic over accepted expressions.
  - reject unknown-dependent bounds such as `size(Chosen)` where `Chosen` is a `Subset`.
  - reject unbounded `find x : Int`.

### 4. Grounding
- Evaluate derived `Range` sets after input sets and scalar params are known.
- Do not require scenario TOML values for derived sets.
- If scenario data supplies a derived set, emit an error like:
  ```text
  QSOL4201: set `Positions` is derived in source and must not be supplied by scenario data.
  ```
- Store range elements with numeric identity. Default: ground range set values as native integers. Preserve string normalization for user-supplied opaque sets.
- Evaluate scalar decision bounds during grounding and attach concrete domains to ground find declarations.

### 5. CQM Backend And Decoding
- Extend dimod codegen:
  - `Bool` scalar -> `dimod.Binary`
  - `Int[lo..hi]` scalar -> native `dimod.Integer(..., lower_bound=lo, upper_bound=hi)`
  - indexed scalar -> one variable per grounded index tuple
- Treat CQM as canonical backend output. Convert to BQM only where export/runtime paths require it.
- Update stats to distinguish:
  - CQM binary variables
  - CQM integer variables
  - converted BQM variables
  - constraints
  - interactions
- Update decoding/output:
  ```json
  {
    "scalars": {
      "T": 7,
      "Load[m1]": 5
    },
    "selected_assignments": []
  }
  ```
- Keep existing selected binary assignment output for `Subset` and `Mapping`.

### 6. Estimate Reporting
- Add an estimator module that works from Ground IR and can return partial reports even if backend compile fails.
- Human output includes:
  - set sizes and derived-set sources
  - scalar/indexed scalar domain sizes
  - primitive `Subset`/`Mapping` binary counts
  - CQM variable counts
  - generated mapping exactly-one constraints
  - backend warnings
- JSON output includes stable fields for problem, scenario, sets, decision variables, constraints, expressions, and backend status.
- `targets check --estimate` should include the estimate next to compatibility output.

### 7. Milestone 2: DiscreteReal
- Implement after scalar `Int` is stable.
- Parse:
  ```qsol
  find y : DiscreteReal[0.0 .. 1.0 step 0.25];
  ```
- Lower as compiler-owned sugar:
  ```text
  __qsol_y_index : Int[0 .. 4]
  y = lo + step * __qsol_y_index
  ```
- Use rational arithmetic for `lo`, `hi`, and `step`.
- Reject invalid domains:
  - `step <= 0`
  - `hi < lo`
  - non-integral `(hi - lo) / step`
  - excessive domain size

### 8. Milestone 2: Piecewise Lowering
- Add compiler-owned builtins, not stdlib macros:
  - `abs(expr)`
  - `max(term for x in S)`
  - `min(term for x in S)`
- Supported first-pass lowering:
  - `must abs(e) <= T` -> `e <= T` and `-e <= T`
  - `minimize abs(e)` -> bounded auxiliary `z`, constraints `z >= e`, `z >= -e`, objective `z`
  - `minimize max(...)` -> bounded auxiliary `T`, constraints `T >= term`
  - `maximize min(...)` -> bounded auxiliary `Z`, constraints `Z <= term`
- Reject unsafe forms:
  - `minimize min(...)`
  - `maximize max(...)`
  - piecewise forms where finite auxiliary bounds cannot be inferred

### 9. Docs And Examples
- Update docs:
  - syntax guide: `Range`, scalar `find`, indexed scalar access, estimate CLI
  - backend docs: native CQM integer/bool variables and BQM conversion caveat
  - compiler docs: derived-set grounding and scalar decision domains
  - CLI docs: `inspect estimate` and `targets check --estimate`
  - stdlib docs after Milestone 2: `piecewise`, `cardinality`, graph/order conventions
- Add/update examples:
  - `job_sequencing` using `Makespan : Int[...]`
  - `minimum_graph_coloring` using `set Colors = Range(1, size(V))`
  - `scalar_bool_demo` for indexed `Bool`
  - Milestone 2: `number_partitioning_abs`
  - Milestone 2: `job_sequencing_max`
  - Milestone 2: rank/topological-order examples as templates, not full graph globals

## Test Plan
- Parser tests:
  - accepts `set P = Range(1, size(V))`
  - accepts scalar and indexed scalar finds
  - rejects `find x : Int`
  - rejects `find y : Real[0.0 .. 1.0]`
  - rejects malformed `Range(1)`

- Typecheck tests:
  - range binders support `p <= size(V)` and `p + 1`
  - opaque set binders still reject arithmetic
  - scalar `Bool` works in boolean contexts
  - scalar `Int` works in numeric contexts
  - `Load[m]` works as indexed scalar access
  - unknown-dependent bounds are rejected

- Grounding tests:
  - derived range sets are materialized from scenario data
  - TOML-supplied derived set errors
  - scalar bounds using params and `size(Set)` evaluate correctly
  - indexed scalar finds expand over grounded index sets

- Backend tests:
  - native CQM `Bool` scalar compiles
  - native CQM `Int` scalar compiles
  - indexed scalar `Int` compiles
  - existing `Subset`/`Mapping` examples still compile
  - scalar values decode into `run.json`

- Estimate tests:
  - human and JSON output for range sets and scalar finds
  - estimate still reports partial data when backend support fails
  - `targets check --estimate` includes compatibility plus estimate

- Docs/examples tests:
  - all documented examples parse/check
  - selected examples build with `local-dimod`
  - docs command snippets stay aligned with CLI help

## Assumptions And Defaults
- Milestone 1 does not implement explicit integer encoding syntax.
- Milestone 1 does not implement `DiscreteReal`, `abs`, `max`, `min`, graph globals, or ordering globals.
- `Range` is inclusive and has no step in Milestone 1.
- Derived range elements are native integers in Ground IR unless this breaks too much existing code; if so, use string labels plus an integer side table.
- CQM is the canonical compiled model; BQM conversion is secondary.
- Diagnostics should stay consistent with current repo taxonomy unless docs are updated in the same change.
- Stdlib graph/order additions should start as documented patterns and lightweight helpers, not hidden global constraints.
