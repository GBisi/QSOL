from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.lower import ir
from qsol.lower.ir import GroundIR, GroundProblem, KernelIR, KProblem

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class InstanceResult:
    ground_ir: GroundIR | None
    diagnostics: list[Diagnostic]


@dataclass(frozen=True, slots=True)
class InstanceExecutionConfig:
    runtime: str | None = None
    backend: str | None = None


def load_instance(path: str | Path) -> dict[str, object]:
    LOGGER.debug("Loading instance payload from %s", path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"instance payload must be a JSON object: {path}"
        raise ValueError(msg)
    return cast(dict[str, object], payload)


def read_execution_config(instance: Mapping[str, object]) -> InstanceExecutionConfig:
    execution = instance.get("execution")
    if not isinstance(execution, Mapping):
        return InstanceExecutionConfig()

    runtime_raw = execution.get("runtime")
    backend_raw = execution.get("backend")
    runtime = str(runtime_raw) if isinstance(runtime_raw, str) and runtime_raw.strip() else None
    backend = str(backend_raw) if isinstance(backend_raw, str) and backend_raw.strip() else None
    return InstanceExecutionConfig(runtime=runtime, backend=backend)


def instantiate_ir(kernel: KernelIR, instance: Mapping[str, object]) -> InstanceResult:
    LOGGER.debug("Instantiating IR from instance payload")
    diagnostics: list[Diagnostic] = []
    requested_problem = instance.get("problem")

    problems: list[KProblem] = list(kernel.problems)
    if requested_problem is not None:
        problems = [p for p in problems if p.name == requested_problem]

    if not problems:
        LOGGER.error("Instance problem '%s' did not match any compiled problem", requested_problem)
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL3001",
                message="instance problem does not match any compiled problem",
                span=kernel.span,
                help=[
                    "Set `problem` in the instance payload to one of the compiled problem names.",
                    "Run `qsol inspect lower --json` to inspect compiled problem names.",
                ],
            )
        )
        return InstanceResult(ground_ir=None, diagnostics=diagnostics)

    set_values_raw = instance.get("sets")
    set_values = cast(dict[str, object], set_values_raw) if isinstance(set_values_raw, dict) else {}
    relation_values_raw = instance.get("relations")
    relation_values = (
        cast(dict[str, object], relation_values_raw)
        if isinstance(relation_values_raw, dict)
        else {}
    )
    params_raw = instance.get("params")
    params_payload = cast(dict[str, object], params_raw) if isinstance(params_raw, dict) else {}
    out: list[GroundProblem] = []

    for problem in problems:
        p_sets: dict[str, list[object]] = {}
        p_relations: dict[str, tuple[tuple[object, ...], ...]] = {}
        p_params: dict[str, object] = {}
        p_derived_sets: dict[str, str] = {}
        p_derived_relations: dict[str, str] = {}

        for decl in problem.sets:
            if decl.expr is not None:
                if decl.name in set_values:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL4201",
                            message=(
                                f"set `{decl.name}` is derived in source and must not be "
                                "supplied by scenario data"
                            ),
                            span=decl.span,
                            help=["Remove this set from the scenario `sets` table."],
                        )
                    )
                continue
            vals = set_values.get(decl.name)
            if vals is None:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"missing set values for `{decl.name}`",
                        span=decl.span,
                        help=[f"Add `sets.{decl.name}` as an array in the instance payload."],
                    )
                )
                continue
            if not isinstance(vals, list):
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"set `{decl.name}` must be an array",
                        span=decl.span,
                        help=[
                            f'Replace `sets.{decl.name}` with an array value, e.g. `["a1", "a2"]`.'
                        ],
                    )
                )
                continue
            p_sets[decl.name] = [str(v) for v in vals]

        for pdecl in problem.params:
            if not pdecl.indices:
                _materialize_param(pdecl, params_payload, p_sets, p_params, diagnostics)

        for decl in problem.sets:
            if decl.expr is None:
                continue
            if not isinstance(decl.expr, ir.KRangeSetExpr):
                continue
            lo = _eval_int_expr(
                decl.expr.lo,
                set_sizes={name: len(values) for name, values in p_sets.items()},
                params=p_params,
                diagnostics=diagnostics,
            )
            hi = _eval_int_expr(
                decl.expr.hi,
                set_sizes={name: len(values) for name, values in p_sets.items()},
                params=p_params,
                diagnostics=diagnostics,
            )
            if lo is None or hi is None:
                continue
            if hi < lo:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"Range lower bound exceeds upper bound for set `{decl.name}`",
                        span=decl.span,
                        help=["Use `Range(lo, hi)` with `lo <= hi`."],
                    )
                )
                continue
            p_sets[decl.name] = list(range(lo, hi + 1))
            p_derived_sets[decl.name] = "Range"

        for pdecl in problem.params:
            if pdecl.indices:
                _materialize_param(pdecl, params_payload, p_sets, p_params, diagnostics)

        declared_relation_names = {decl.name for decl in problem.relations}
        derived_relation_names = {decl.name for decl in problem.relations if decl.expr is not None}
        for supplied_name in relation_values:
            if supplied_name in derived_relation_names:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL4201",
                        message=(
                            f"relation `{supplied_name}` is derived in source and must not be "
                            "supplied by scenario data"
                        ),
                        span=problem.span,
                        help=["Remove this relation from the scenario `relations` table."],
                    )
                )
            elif supplied_name not in declared_relation_names:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"unknown relation `{supplied_name}` in scenario data",
                        span=problem.span,
                        help=["Remove this relation or declare it in the problem."],
                    )
                )

        for rdecl in problem.relations:
            if rdecl.expr is None:
                _materialize_relation(rdecl, relation_values, p_sets, p_relations, diagnostics)

        p_derived_relations.update(
            _materialize_derived_relations(problem, p_sets, p_params, p_relations, diagnostics)
        )

        grounded_finds = tuple(
            _ground_find(
                find,
                set_sizes={name: len(values) for name, values in p_sets.items()},
                params=p_params,
                diagnostics=diagnostics,
            )
            for find in problem.finds
        )

        out.append(
            GroundProblem(
                span=problem.span,
                name=problem.name,
                set_values=p_sets,
                relation_values=p_relations,
                params=p_params,
                finds=grounded_finds,
                constraints=_fold_size_in_constraints(
                    problem.constraints,
                    set_sizes={name: len(values) for name, values in p_sets.items()},
                    declared_sets=frozenset(s.name for s in problem.sets),
                    diagnostics=diagnostics,
                ),
                objectives=_fold_size_in_objectives(
                    problem.objectives,
                    set_sizes={name: len(values) for name, values in p_sets.items()},
                    declared_sets=frozenset(s.name for s in problem.sets),
                    diagnostics=diagnostics,
                ),
                derived_sets=p_derived_sets,
                derived_relations=p_derived_relations,
            )
        )

    if any(d.is_error for d in diagnostics):
        LOGGER.error("Instance instantiation failed with %s diagnostics", len(diagnostics))
        return InstanceResult(ground_ir=None, diagnostics=diagnostics)
    LOGGER.info("Instance instantiation completed for %s problem(s)", len(out))
    return InstanceResult(
        ground_ir=GroundIR(span=kernel.span, problems=tuple(out)), diagnostics=diagnostics
    )


def _materialize_param(
    pdecl: ir.KParamDecl,
    params_payload: Mapping[str, object],
    p_sets: dict[str, list[object]],
    p_params: dict[str, object],
    diagnostics: list[Diagnostic],
) -> None:
    provided = pdecl.name in params_payload
    if provided:
        value = params_payload[pdecl.name]
    elif pdecl.default is not None:
        value = pdecl.default
    else:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"missing value for param `{pdecl.name}`",
                span=pdecl.span,
                help=[
                    f"Provide `params.{pdecl.name}` in the instance payload or declare a default in the model."
                ],
            )
        )
        return

    if pdecl.indices:
        if not isinstance(value, dict):
            if not provided and pdecl.default is not None:
                value = _expand_indexed_default(pdecl.default, list(pdecl.indices), p_sets)
            else:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"param `{pdecl.name}` expects indexed object",
                        span=pdecl.span,
                        help=["Use nested objects keyed by index set elements for indexed params."],
                    )
                )
                return
        if not _check_shape(value, list(pdecl.indices), p_sets):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"param `{pdecl.name}` shape does not match index sets",
                    span=pdecl.span,
                    help=[
                        "Ensure object keys exactly match declared index set elements at each dimension."
                    ],
                )
            )
            return

    if pdecl.elem_set is not None:
        allowed = p_sets.get(pdecl.elem_set)
        if allowed is None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"missing set values for `{pdecl.elem_set}` used by `{pdecl.name}`",
                    span=pdecl.span,
                    help=[
                        f"Add `sets.{pdecl.elem_set}` to the instance payload before using `{pdecl.name}`."
                    ],
                )
            )
            return

        normalized, bad_value = _normalize_elem_value(
            value,
            list(pdecl.indices),
            allowed_members=frozenset(str(member) for member in allowed),
        )
        if bad_value is not None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=(
                        f"param `{pdecl.name}` has value `{bad_value}` not present in set "
                        f"`{pdecl.elem_set}`"
                    ),
                    span=pdecl.span,
                    help=[
                        f"Restrict values of `{pdecl.name}` to members declared in set `{pdecl.elem_set}`."
                    ],
                )
            )
            return
        value = normalized

    p_params[pdecl.name] = value


def _materialize_relation(
    rdecl: ir.KRelationDecl,
    relations_payload: Mapping[str, object],
    p_sets: dict[str, list[object]],
    p_relations: dict[str, tuple[tuple[object, ...], ...]],
    diagnostics: list[Diagnostic],
) -> None:
    raw = relations_payload.get(rdecl.name)
    if raw is None:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"missing relation values for `{rdecl.name}`",
                span=rdecl.span,
                help=[f"Add `relations.{rdecl.name}` as an array in the instance payload."],
            )
        )
        return
    if not isinstance(raw, list):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"relation `{rdecl.name}` must be an array",
                span=rdecl.span,
                help=["Use an array of field objects or compact tuples."],
            )
        )
        return

    field_names = [field.name for field in rdecl.fields]
    field_sets = [field.set_name for field in rdecl.fields]
    allowed_by_field: list[frozenset[str]] = []
    for set_name in field_sets:
        values = p_sets.get(set_name)
        if values is None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"missing set values for `{set_name}` used by relation `{rdecl.name}`",
                    span=rdecl.span,
                    help=[f"Add `sets.{set_name}` before relation `{rdecl.name}`."],
                )
            )
            return
        allowed_by_field.append(frozenset(str(value) for value in values))

    tuples: list[tuple[object, ...]] = []
    seen: set[tuple[object, ...]] = set()
    for idx, entry in enumerate(raw):
        tuple_values: list[object]
        if isinstance(entry, Mapping):
            keys = {str(key) for key in entry.keys()}
            expected = set(field_names)
            missing = sorted(expected - keys)
            extra = sorted(keys - expected)
            if missing or extra:
                detail = []
                if missing:
                    detail.append(f"missing: {', '.join(missing)}")
                if extra:
                    detail.append(f"extra: {', '.join(extra)}")
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"relation `{rdecl.name}` tuple {idx} has wrong fields",
                        span=rdecl.span,
                        help=["; ".join(detail)],
                    )
                )
                continue
            tuple_values = [
                cast(Mapping[str, object], entry)[field_name] for field_name in field_names
            ]
        elif isinstance(entry, list):
            if len(entry) != len(field_names):
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"relation `{rdecl.name}` tuple {idx} has wrong arity",
                        span=rdecl.span,
                        help=[f"Expected {len(field_names)} value(s)."],
                    )
                )
                continue
            tuple_values = list(entry)
        else:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"relation `{rdecl.name}` tuple {idx} must be an object or array",
                    span=rdecl.span,
                    help=["Use `{ field = value }` objects or compact arrays."],
                )
            )
            continue

        normalized = tuple(str(value) for value in tuple_values)
        bad_field: str | None = None
        bad_value: object | None = None
        for field_name, value, allowed in zip(
            field_names, normalized, allowed_by_field, strict=True
        ):
            if value not in allowed:
                bad_field = field_name
                bad_value = value
                break
        if bad_field is not None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=(
                        f"relation `{rdecl.name}` field `{bad_field}` has value "
                        f"`{bad_value}` outside its declared set"
                    ),
                    span=rdecl.span,
                    help=["Use only elements declared in the field set."],
                )
            )
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tuples.append(normalized)

    p_relations[rdecl.name] = tuple(tuples)


def _materialize_derived_relations(
    problem: KProblem,
    p_sets: dict[str, list[object]],
    p_params: Mapping[str, object],
    p_relations: dict[str, tuple[tuple[object, ...], ...]],
    diagnostics: list[Diagnostic],
) -> dict[str, str]:
    derived = {decl.name: decl for decl in problem.relations if decl.expr is not None}
    relation_decl_names = {decl.name for decl in problem.relations}
    sources: dict[str, str] = {}
    remaining = set(derived)

    while remaining:
        progressed = False
        for name in sorted(remaining):
            rdecl = derived[name]
            assert rdecl.expr is not None
            deps = {dep for dep in _derived_relation_deps(rdecl.expr) if dep in relation_decl_names}
            if not all(dep in p_relations for dep in deps):
                continue
            _materialize_derived_relation(rdecl, p_sets, p_params, p_relations, diagnostics)
            sources[name] = _derived_relation_source(rdecl.expr)
            remaining.remove(name)
            progressed = True
            break
        if not progressed:
            blocked = ", ".join(sorted(remaining))
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"derived relation dependency cycle or unresolved dependency: {blocked}",
                    span=problem.span,
                    help=[
                        "Derived relations must depend only on base or acyclic derived relations."
                    ],
                )
            )
            break

    return sources


def _materialize_derived_relation(
    rdecl: ir.KRelationDecl,
    p_sets: Mapping[str, list[object]],
    p_params: Mapping[str, object],
    p_relations: dict[str, tuple[tuple[object, ...], ...]],
    diagnostics: list[Diagnostic],
) -> None:
    if rdecl.expr is None:
        return

    binders: tuple[ir.KCompBinder | ir.KTupleCompBinder, ...]
    where: ir.KBoolExpr | None
    if isinstance(rdecl.expr, ir.KPairsRelationExpr):
        binders = rdecl.expr.binders
        where = rdecl.expr.where
    elif isinstance(rdecl.expr, ir.KFilterRelationExpr):
        binders = (rdecl.expr.binder,)
        where = rdecl.expr.where
    else:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"unsupported derived relation expression for `{rdecl.name}`",
                span=rdecl.span,
            )
        )
        return

    envs = _iter_static_binder_envs(
        binders, p_sets=p_sets, p_relations=p_relations, span=rdecl.span, diagnostics=diagnostics
    )
    field_names = [field.name for field in rdecl.fields]
    tuples: list[tuple[object, ...]] = []
    seen: set[tuple[object, ...]] = set()

    for env in envs:
        if where is not None:
            include = _eval_static_bool(
                where,
                p_sets=p_sets,
                p_params=p_params,
                p_relations=p_relations,
                env=env,
                diagnostics=diagnostics,
            )
            if include is None or not include:
                continue

        values: list[object] = []
        missing: list[str] = []
        for field_name in field_names:
            if field_name not in env:
                missing.append(field_name)
            else:
                values.append(str(env[field_name]))
        if missing:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"derived relation `{rdecl.name}` has unbound output field(s)",
                    span=rdecl.span,
                    help=[f"Bind: {', '.join(missing)}"],
                )
            )
            return

        normalized = tuple(values)
        if normalized in seen:
            continue
        seen.add(normalized)
        tuples.append(normalized)

    p_relations[rdecl.name] = tuple(tuples)


def _iter_static_binder_envs(
    binders: tuple[ir.KCompBinder | ir.KTupleCompBinder, ...],
    *,
    p_sets: Mapping[str, list[object]],
    p_relations: Mapping[str, tuple[tuple[object, ...], ...]],
    span: Span,
    diagnostics: list[Diagnostic],
) -> list[dict[str, object]]:
    envs: list[dict[str, object]] = [{}]
    for binder in binders:
        if isinstance(binder, ir.KTupleCompBinder):
            tuples = p_relations.get(binder.domain_relation)
            if tuples is None:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"unknown relation `{binder.domain_relation}` in derived relation",
                        span=span,
                    )
                )
                return []
            next_envs: list[dict[str, object]] = []
            for base_env in envs:
                for values in sorted(tuples, key=lambda item: tuple(str(value) for value in item)):
                    if len(values) != len(binder.vars):
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2201",
                                message=f"relation `{binder.domain_relation}` arity mismatch",
                                span=span,
                            )
                        )
                        return []
                    bound = dict(base_env)
                    for var, value in zip(binder.vars, values, strict=True):
                        bound[var] = value
                    next_envs.append(bound)
            envs = next_envs
            continue

        set_values = p_sets.get(binder.domain_set)
        if set_values is None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"unknown set `{binder.domain_set}` in derived relation",
                    span=span,
                )
            )
            return []
        next_envs = []
        for base_env in envs:
            for value in sorted(set_values, key=str):
                bound = dict(base_env)
                bound[binder.var] = value
                next_envs.append(bound)
        envs = next_envs
    return envs


def _derived_relation_deps(expr: ir.KRelationExpr) -> set[str]:
    deps: set[str] = set()
    if isinstance(expr, ir.KPairsRelationExpr):
        for binder in expr.binders:
            if isinstance(binder, ir.KTupleCompBinder):
                deps.add(binder.domain_relation)
        if expr.where is not None:
            _collect_relation_deps(expr.where, deps)
    elif isinstance(expr, ir.KFilterRelationExpr):
        deps.add(expr.binder.domain_relation)
        if expr.where is not None:
            _collect_relation_deps(expr.where, deps)
    return deps


def _collect_relation_deps(expr: ir.KExpr, deps: set[str]) -> None:
    if isinstance(expr, ir.KFuncCall):
        deps.add(expr.name)
        for arg in expr.args:
            _collect_relation_deps(arg, deps)
    elif isinstance(expr, ir.KMethodCall):
        _collect_relation_deps(expr.target, deps)
        for arg in expr.args:
            _collect_relation_deps(arg, deps)
    elif isinstance(expr, (ir.KNot, ir.KNeg)):
        _collect_relation_deps(expr.expr, deps)
    elif isinstance(
        expr, (ir.KAnd, ir.KOr, ir.KImplies, ir.KCompare, ir.KAdd, ir.KSub, ir.KMul, ir.KDiv)
    ):
        _collect_relation_deps(expr.left, deps)
        _collect_relation_deps(expr.right, deps)
    elif isinstance(expr, (ir.KIfThenElse, ir.KBoolIfThenElse)):
        _collect_relation_deps(expr.cond, deps)
        _collect_relation_deps(expr.then_expr, deps)
        _collect_relation_deps(expr.else_expr, deps)


def _derived_relation_source(expr: ir.KRelationExpr) -> str:
    if isinstance(expr, ir.KPairsRelationExpr):
        return "pairs"
    if isinstance(expr, ir.KFilterRelationExpr):
        return "filter"
    return type(expr).__name__


def _eval_static_bool(
    expr: ir.KBoolExpr,
    *,
    p_sets: Mapping[str, list[object]],
    p_params: Mapping[str, object],
    p_relations: Mapping[str, tuple[tuple[object, ...], ...]],
    env: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> bool | None:
    if isinstance(expr, ir.KBoolLit):
        return expr.value
    if isinstance(expr, ir.KName):
        value = _eval_static_value(
            expr,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return value if isinstance(value, bool) else None
    if isinstance(expr, ir.KNot):
        value = _eval_static_bool(
            expr.expr,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return None if value is None else not value
    if isinstance(expr, ir.KAnd):
        left = _eval_static_bool(
            expr.left,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        right = _eval_static_bool(
            expr.right,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return None if left is None or right is None else left and right
    if isinstance(expr, ir.KOr):
        left = _eval_static_bool(
            expr.left,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        right = _eval_static_bool(
            expr.right,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return None if left is None or right is None else left or right
    if isinstance(expr, ir.KImplies):
        left = _eval_static_bool(
            expr.left,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        right = _eval_static_bool(
            expr.right,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return None if left is None or right is None else (not left) or right
    if isinstance(expr, ir.KCompare):
        compare_left = _eval_static_value(
            expr.left,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        compare_right = _eval_static_value(
            expr.right,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        if compare_left is None or compare_right is None:
            return None
        if expr.op in {"=", "=="}:
            return compare_left == compare_right
        if expr.op == "!=":
            return compare_left != compare_right
        if isinstance(compare_left, (int, float)) and isinstance(compare_right, (int, float)):
            if expr.op == "<":
                return float(compare_left) < float(compare_right)
            if expr.op == "<=":
                return float(compare_left) <= float(compare_right)
            if expr.op == ">":
                return float(compare_left) > float(compare_right)
            if expr.op == ">=":
                return float(compare_left) >= float(compare_right)
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message="derived relation comparison requires numeric operands",
                span=expr.span,
            )
        )
        return None
    if isinstance(expr, ir.KFuncCall):
        if expr.name in p_relations:
            args: list[str] = []
            for arg in expr.args:
                value = _eval_static_value(
                    arg,
                    p_sets=p_sets,
                    p_params=p_params,
                    p_relations=p_relations,
                    env=env,
                    diagnostics=diagnostics,
                )
                if value is None:
                    return None
                args.append(str(value))
            return tuple(args) in p_relations[expr.name]
        value = _eval_static_value(
            expr,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return value if isinstance(value, bool) else None
    if isinstance(expr, ir.KBoolIfThenElse):
        cond = _eval_static_bool(
            expr.cond,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        if cond is None:
            return None
        branch = expr.then_expr if cond else expr.else_expr
        return _eval_static_bool(
            branch,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
    diagnostics.append(
        Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2201",
            message=f"unsupported derived relation predicate `{type(expr).__name__}`",
            span=expr.span,
        )
    )
    return None


def _eval_static_value(
    expr: ir.KExpr,
    *,
    p_sets: Mapping[str, list[object]],
    p_params: Mapping[str, object],
    p_relations: Mapping[str, tuple[tuple[object, ...], ...]],
    env: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> object | None:
    if isinstance(expr, ir.KNumLit):
        return float(expr.value)
    if isinstance(expr, ir.KBoolLit):
        return expr.value
    if isinstance(expr, ir.KName):
        if expr.name in env:
            return env[expr.name]
        if expr.name in p_params:
            return p_params[expr.name]
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"unknown static value `{expr.name}` in derived relation",
                span=expr.span,
            )
        )
        return None
    if isinstance(expr, ir.KFuncCall):
        if expr.name == "size" and len(expr.args) == 1 and isinstance(expr.args[0], ir.KName):
            name = expr.args[0].name
            if name in p_sets:
                return float(len(p_sets[name]))
            if name in p_relations:
                return float(len(p_relations[name]))
        if expr.name in p_params:
            return _static_param_call_value(expr, p_params, p_sets, p_relations, env, diagnostics)
        if expr.name in p_relations:
            return _eval_static_bool(
                expr,
                p_sets=p_sets,
                p_params=p_params,
                p_relations=p_relations,
                env=env,
                diagnostics=diagnostics,
            )
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"unknown static call `{expr.name}` in derived relation",
                span=expr.span,
            )
        )
        return None
    if isinstance(expr, ir.KAdd):
        return _eval_static_numeric_binary(
            expr.left, expr.right, "+", p_sets, p_params, p_relations, env, diagnostics
        )
    if isinstance(expr, ir.KSub):
        return _eval_static_numeric_binary(
            expr.left, expr.right, "-", p_sets, p_params, p_relations, env, diagnostics
        )
    if isinstance(expr, ir.KMul):
        return _eval_static_numeric_binary(
            expr.left, expr.right, "*", p_sets, p_params, p_relations, env, diagnostics
        )
    if isinstance(expr, ir.KDiv):
        return _eval_static_numeric_binary(
            expr.left, expr.right, "/", p_sets, p_params, p_relations, env, diagnostics
        )
    if isinstance(expr, ir.KNeg):
        value = _eval_static_value(
            expr.expr,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        return -float(value) if isinstance(value, (int, float)) else None
    if isinstance(expr, ir.KIfThenElse):
        cond = _eval_static_bool(
            expr.cond,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        if cond is None:
            return None
        branch = expr.then_expr if cond else expr.else_expr
        return _eval_static_value(
            branch,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
    return None


def _static_param_call_value(
    expr: ir.KFuncCall,
    p_params: Mapping[str, object],
    p_sets: Mapping[str, list[object]],
    p_relations: Mapping[str, tuple[tuple[object, ...], ...]],
    env: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> object | None:
    value = p_params.get(expr.name)
    if value is None:
        return None
    for arg in expr.args:
        key = _eval_static_value(
            arg,
            p_sets=p_sets,
            p_params=p_params,
            p_relations=p_relations,
            env=env,
            diagnostics=diagnostics,
        )
        if key is None or not isinstance(value, Mapping):
            return None
        value = value.get(str(key))
    return value


def _eval_static_numeric_binary(
    left_expr: ir.KExpr,
    right_expr: ir.KExpr,
    op: str,
    p_sets: Mapping[str, list[object]],
    p_params: Mapping[str, object],
    p_relations: Mapping[str, tuple[tuple[object, ...], ...]],
    env: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> float | None:
    left = _eval_static_value(
        left_expr,
        p_sets=p_sets,
        p_params=p_params,
        p_relations=p_relations,
        env=env,
        diagnostics=diagnostics,
    )
    right = _eval_static_value(
        right_expr,
        p_sets=p_sets,
        p_params=p_params,
        p_relations=p_relations,
        env=env,
        diagnostics=diagnostics,
    )
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    if op == "+":
        return float(left) + float(right)
    if op == "-":
        return float(left) - float(right)
    if op == "*":
        return float(left) * float(right)
    if op == "/":
        return float(left) / float(right)
    return None


def _check_shape(value: object, dims: list[str], sets: dict[str, list[object]]) -> bool:
    if not dims:
        return not isinstance(value, dict)
    if not isinstance(value, dict):
        return False

    dim = dims[0]
    expected = sorted(str(v) for v in sets.get(dim, []))
    keys = sorted(str(k) for k in value.keys())
    if expected and keys != expected:
        return False
    return all(_check_shape(v, dims[1:], sets) for v in value.values())


def _expand_indexed_default(
    default_value: object, dims: list[str], sets: dict[str, list[object]]
) -> object:
    if not dims:
        return default_value

    dim = dims[0]
    elems = sorted(str(v) for v in sets.get(dim, []))
    return {elem: _expand_indexed_default(default_value, dims[1:], sets) for elem in elems}


def _ground_find(
    find: ir.KFindDecl,
    *,
    set_sizes: Mapping[str, int],
    params: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> ir.KFindDecl:
    if not isinstance(find.decision_type, ir.KIntDecisionType):
        return find
    lo = _eval_int_expr(
        find.decision_type.lo, set_sizes=set_sizes, params=params, diagnostics=diagnostics
    )
    hi = _eval_int_expr(
        find.decision_type.hi, set_sizes=set_sizes, params=params, diagnostics=diagnostics
    )
    if lo is None or hi is None:
        return find
    if hi < lo:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message=f"Int decision `{find.name}` lower bound exceeds upper bound",
                span=find.span,
                help=["Use `Int[lo .. hi]` with `lo <= hi`."],
            )
        )
        return find
    return replace(
        find,
        decision_type=replace(
            find.decision_type,
            lo=ir.KNumLit(span=find.decision_type.lo.span, value=float(lo)),
            hi=ir.KNumLit(span=find.decision_type.hi.span, value=float(hi)),
        ),
    )


def _eval_int_expr(
    expr: ir.KNumExpr,
    *,
    set_sizes: Mapping[str, int],
    params: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> int | None:
    value = _eval_num_expr(expr, set_sizes=set_sizes, params=params, diagnostics=diagnostics)
    if value is None:
        return None
    if abs(value - round(value)) > 1e-9:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message="integer bound expression must evaluate to an integer",
                span=expr.span,
                help=["Use integer literals, integer params, size(Set), or integer arithmetic."],
            )
        )
        return None
    return int(round(value))


def _eval_num_expr(
    expr: ir.KNumExpr,
    *,
    set_sizes: Mapping[str, int],
    params: Mapping[str, object],
    diagnostics: list[Diagnostic],
) -> float | None:
    if isinstance(expr, ir.KNumLit):
        return float(expr.value)
    if isinstance(expr, ir.KName):
        value = params.get(expr.name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message=f"bound expression references non-numeric scalar param `{expr.name}`",
                    span=expr.span,
                    help=["Use only numeric scalar params in bounds."],
                )
            )
            return None
        return float(value)
    if isinstance(expr, ir.KFuncCall) and expr.name == "size" and len(expr.args) == 1:
        arg = expr.args[0]
        if isinstance(arg, ir.KName) and arg.name in set_sizes:
            return float(set_sizes[arg.name])
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2201",
                message="size() in a bound references an unknown set",
                span=expr.span,
                help=["Use `size(SetName)` with a grounded set."],
            )
        )
        return None
    if isinstance(expr, ir.KAdd):
        left = _eval_num_expr(
            expr.left, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        right = _eval_num_expr(
            expr.right, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        return None if left is None or right is None else left + right
    if isinstance(expr, ir.KSub):
        left = _eval_num_expr(
            expr.left, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        right = _eval_num_expr(
            expr.right, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        return None if left is None or right is None else left - right
    if isinstance(expr, ir.KMul):
        left = _eval_num_expr(
            expr.left, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        right = _eval_num_expr(
            expr.right, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        return None if left is None or right is None else left * right
    if isinstance(expr, ir.KDiv):
        left = _eval_num_expr(
            expr.left, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        right = _eval_num_expr(
            expr.right, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        if left is None or right is None:
            return None
        if abs(right) <= 1e-12:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2201",
                    message="division by zero in integer bound",
                    span=expr.span,
                    help=["Use a non-zero divisor in bound arithmetic."],
                )
            )
            return None
        return left / right
    if isinstance(expr, ir.KNeg):
        inner = _eval_num_expr(
            expr.expr, set_sizes=set_sizes, params=params, diagnostics=diagnostics
        )
        return None if inner is None else -inner

    diagnostics.append(
        Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2201",
            message="unsupported integer bound expression",
            span=expr.span,
            help=["Use literals, scalar params, size(Set), and arithmetic in bounds."],
        )
    )
    return None


def _normalize_elem_value(
    value: object,
    dims: list[str],
    *,
    allowed_members: frozenset[str],
) -> tuple[object, str | None]:
    if dims:
        if not isinstance(value, dict):
            return value, "<non-object>"
        normalized: dict[str, object] = {}
        for key, inner in value.items():
            normalized_inner, bad = _normalize_elem_value(
                inner,
                dims[1:],
                allowed_members=allowed_members,
            )
            if bad is not None:
                return value, bad
            normalized[str(key)] = normalized_inner
        return normalized, None

    if isinstance(value, dict):
        return value, "<object>"

    member = str(value)
    if member not in allowed_members:
        return value, member
    return member, None


def _fold_size_in_constraints(
    constraints: tuple[ir.KConstraint, ...],
    *,
    set_sizes: Mapping[str, int],
    declared_sets: frozenset[str],
    diagnostics: list[Diagnostic],
) -> tuple[ir.KConstraint, ...]:
    return tuple(
        replace(
            constraint,
            expr=_as_kbool(
                _fold_size_in_expr(
                    constraint.expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
        for constraint in constraints
    )


def _fold_size_in_objectives(
    objectives: tuple[ir.KObjective, ...],
    *,
    set_sizes: Mapping[str, int],
    declared_sets: frozenset[str],
    diagnostics: list[Diagnostic],
) -> tuple[ir.KObjective, ...]:
    return tuple(
        replace(
            objective,
            expr=_as_knum(
                _fold_size_in_expr(
                    objective.expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
        for objective in objectives
    )


def _as_kbool(expr: ir.KExpr) -> ir.KBoolExpr:
    return cast(ir.KBoolExpr, expr)


def _as_knum(expr: ir.KExpr) -> ir.KNumExpr:
    return cast(ir.KNumExpr, expr)


def _fold_size_in_expr(
    expr: ir.KExpr,
    *,
    set_sizes: Mapping[str, int],
    declared_sets: frozenset[str],
    diagnostics: list[Diagnostic],
) -> ir.KExpr:
    if isinstance(expr, ir.KFuncCall):
        args = tuple(
            _fold_size_in_expr(
                arg,
                set_sizes=set_sizes,
                declared_sets=declared_sets,
                diagnostics=diagnostics,
            )
            for arg in expr.args
        )
        call = expr if args == expr.args else replace(expr, args=args)
        if call.name != "size":
            return call
        return _fold_size_call(
            call,
            set_sizes=set_sizes,
            declared_sets=declared_sets,
            diagnostics=diagnostics,
        )

    if isinstance(expr, ir.KMethodCall):
        return replace(
            expr,
            target=_fold_size_in_expr(
                expr.target,
                set_sizes=set_sizes,
                declared_sets=declared_sets,
                diagnostics=diagnostics,
            ),
            args=tuple(
                _fold_size_in_expr(
                    arg,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
                for arg in expr.args
            ),
        )

    if isinstance(expr, ir.KNot):
        return replace(
            expr,
            expr=_as_kbool(
                _fold_size_in_expr(
                    expr.expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KAnd):
        return replace(
            expr,
            left=_as_kbool(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_kbool(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KOr):
        return replace(
            expr,
            left=_as_kbool(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_kbool(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KImplies):
        return replace(
            expr,
            left=_as_kbool(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_kbool(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KCompare):
        return replace(
            expr,
            left=_fold_size_in_expr(
                expr.left,
                set_sizes=set_sizes,
                declared_sets=declared_sets,
                diagnostics=diagnostics,
            ),
            right=_fold_size_in_expr(
                expr.right,
                set_sizes=set_sizes,
                declared_sets=declared_sets,
                diagnostics=diagnostics,
            ),
        )
    if isinstance(expr, ir.KAdd):
        return replace(
            expr,
            left=_as_knum(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_knum(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KSub):
        return replace(
            expr,
            left=_as_knum(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_knum(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KMul):
        return replace(
            expr,
            left=_as_knum(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_knum(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KDiv):
        return replace(
            expr,
            left=_as_knum(
                _fold_size_in_expr(
                    expr.left,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            right=_as_knum(
                _fold_size_in_expr(
                    expr.right,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KNeg):
        return replace(
            expr,
            expr=_as_knum(
                _fold_size_in_expr(
                    expr.expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KIfThenElse):
        return replace(
            expr,
            cond=_as_kbool(
                _fold_size_in_expr(
                    expr.cond,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            then_expr=_as_knum(
                _fold_size_in_expr(
                    expr.then_expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            else_expr=_as_knum(
                _fold_size_in_expr(
                    expr.else_expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KBoolIfThenElse):
        return replace(
            expr,
            cond=_as_kbool(
                _fold_size_in_expr(
                    expr.cond,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            then_expr=_as_kbool(
                _fold_size_in_expr(
                    expr.then_expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
            else_expr=_as_kbool(
                _fold_size_in_expr(
                    expr.else_expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KQuantifier):
        return replace(
            expr,
            expr=_as_kbool(
                _fold_size_in_expr(
                    expr.expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KTupleQuantifier):
        return replace(
            expr,
            expr=_as_kbool(
                _fold_size_in_expr(
                    expr.expr,
                    set_sizes=set_sizes,
                    declared_sets=declared_sets,
                    diagnostics=diagnostics,
                )
            ),
        )
    if isinstance(expr, ir.KSum):
        return replace(
            expr,
            comp=replace(
                expr.comp,
                term=_as_knum(
                    _fold_size_in_expr(
                        expr.comp.term,
                        set_sizes=set_sizes,
                        declared_sets=declared_sets,
                        diagnostics=diagnostics,
                    )
                ),
            ),
        )

    return expr


def _fold_size_call(
    call: ir.KFuncCall,
    *,
    set_sizes: Mapping[str, int],
    declared_sets: frozenset[str],
    diagnostics: list[Diagnostic],
) -> ir.KNumLit | ir.KFuncCall:
    fallback = ir.KNumLit(span=call.span, value=0.0)

    if len(call.args) != 1:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2101",
                message="size() expects exactly one set identifier argument",
                span=call.span,
                help=["Use `size(SetName)` with exactly one declared set identifier."],
            )
        )
        return fallback

    arg = call.args[0]
    if not isinstance(arg, ir.KName):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2101",
                message="size() expects a declared set identifier",
                span=call.span,
                help=["Pass a declared set name, e.g. `size(V)`."],
            )
        )
        return fallback

    if arg.name in set_sizes:
        return ir.KNumLit(span=call.span, value=float(set_sizes[arg.name]))

    if arg.name in declared_sets:
        # Keep existing missing-set QSOL2201 behavior from instance validation.
        return call

    diagnostics.append(
        Diagnostic(
            severity=Severity.ERROR,
            code="QSOL2101",
            message=f"size() expects a declared set identifier, got `{arg.name}`",
            span=arg.span,
            help=["Use a set declared in the active problem scope."],
        )
    )
    return fallback
