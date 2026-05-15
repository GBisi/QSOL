from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from qsol.diag.diagnostic import Diagnostic, Severity
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
    params_raw = instance.get("params")
    params_payload = cast(dict[str, object], params_raw) if isinstance(params_raw, dict) else {}
    out: list[GroundProblem] = []

    for problem in problems:
        p_sets: dict[str, list[object]] = {}
        p_params: dict[str, object] = {}
        p_derived_sets: dict[str, str] = {}

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
