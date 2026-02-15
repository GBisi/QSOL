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
        p_sets: dict[str, list[str]] = {}
        p_params: dict[str, object] = {}

        for decl in problem.sets:
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
                continue

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
                                help=[
                                    "Use nested objects keyed by index set elements for indexed params."
                                ],
                            )
                        )
                        continue
                shape_ok = _check_shape(value, list(pdecl.indices), p_sets)
                if not shape_ok:
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
                    continue

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
                    continue

                normalized, bad_value = _normalize_elem_value(
                    value,
                    list(pdecl.indices),
                    allowed_members=frozenset(allowed),
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
                    continue
                value = normalized

            p_params[pdecl.name] = value

        out.append(
            GroundProblem(
                span=problem.span,
                name=problem.name,
                set_values=p_sets,
                params=p_params,
                finds=problem.finds,
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
            )
        )

    if any(d.is_error for d in diagnostics):
        LOGGER.error("Instance instantiation failed with %s diagnostics", len(diagnostics))
        return InstanceResult(ground_ir=None, diagnostics=diagnostics)
    LOGGER.info("Instance instantiation completed for %s problem(s)", len(out))
    return InstanceResult(
        ground_ir=GroundIR(span=kernel.span, problems=tuple(out)), diagnostics=diagnostics
    )


def _check_shape(value: object, dims: list[str], sets: dict[str, list[str]]) -> bool:
    if not dims:
        return not isinstance(value, dict)
    if not isinstance(value, dict):
        return False

    dim = dims[0]
    expected = sorted(sets.get(dim, []))
    keys = sorted(str(k) for k in value.keys())
    if expected and keys != expected:
        return False
    return all(_check_shape(v, dims[1:], sets) for v in value.values())


def _expand_indexed_default(
    default_value: object, dims: list[str], sets: dict[str, list[str]]
) -> object:
    if not dims:
        return default_value

    dim = dims[0]
    elems = sorted(sets.get(dim, []))
    return {elem: _expand_indexed_default(default_value, dims[1:], sets) for elem in elems}


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
