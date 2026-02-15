from __future__ import annotations

from collections.abc import Collection

from qsol.diag.diagnostic import Severity
from qsol.lower import ir
from qsol.targeting.interfaces import BackendPlugin, RuntimePlugin
from qsol.targeting.types import CompatibilityResult, SupportIssue, SupportReport, TargetSelection


def extract_required_capabilities(ground: ir.GroundIR) -> set[str]:
    capabilities: set[str] = set()
    for problem in ground.problems:
        for find in problem.finds:
            kind = find.unknown_type.kind
            if kind == "Subset":
                capabilities.add("unknown.subset.v1")
            elif kind == "Mapping":
                capabilities.add("unknown.mapping.v1")
            else:
                capabilities.add("unknown.custom.v1")

        for constraint in problem.constraints:
            _collect_expr_capabilities(constraint.expr, capabilities)
        for objective in problem.objectives:
            _collect_expr_capabilities(objective.expr, capabilities)

    return capabilities


def _collect_expr_capabilities(expr: ir.KExpr, capabilities: set[str]) -> None:
    if isinstance(expr, ir.KCompare):
        mapping = {
            "=": "constraint.compare.eq.v1",
            "!=": "constraint.compare.ne.v1",
            "<": "constraint.compare.lt.v1",
            "<=": "constraint.compare.le.v1",
            ">": "constraint.compare.gt.v1",
            ">=": "constraint.compare.ge.v1",
        }
        cap = mapping.get(expr.op)
        if cap is not None:
            capabilities.add(cap)
        _collect_expr_capabilities(expr.left, capabilities)
        _collect_expr_capabilities(expr.right, capabilities)
        return

    if isinstance(expr, ir.KQuantifier):
        if expr.kind == "forall":
            capabilities.add("constraint.quantifier.forall.v1")
        elif expr.kind == "exists":
            capabilities.add("constraint.quantifier.exists.v1")
        _collect_expr_capabilities(expr.expr, capabilities)
        return

    if isinstance(expr, ir.KIfThenElse):
        capabilities.add("objective.if_then_else.v1")
        _collect_expr_capabilities(expr.cond, capabilities)
        _collect_expr_capabilities(expr.then_expr, capabilities)
        _collect_expr_capabilities(expr.else_expr, capabilities)
        return

    if isinstance(expr, ir.KSum):
        capabilities.add("objective.sum.v1")
        _collect_expr_capabilities(expr.comp.term, capabilities)
        return

    if isinstance(expr, ir.KAnd):
        capabilities.add("expression.bool.and.v1")
        _collect_expr_capabilities(expr.left, capabilities)
        _collect_expr_capabilities(expr.right, capabilities)
        return

    if isinstance(expr, ir.KOr):
        capabilities.add("expression.bool.or.v1")
        _collect_expr_capabilities(expr.left, capabilities)
        _collect_expr_capabilities(expr.right, capabilities)
        return

    if isinstance(expr, ir.KImplies):
        capabilities.add("expression.bool.implies.v1")
        _collect_expr_capabilities(expr.left, capabilities)
        _collect_expr_capabilities(expr.right, capabilities)
        return

    if isinstance(expr, ir.KNot):
        capabilities.add("expression.bool.not.v1")
        _collect_expr_capabilities(expr.expr, capabilities)
        return

    if isinstance(expr, (ir.KAdd, ir.KSub, ir.KMul, ir.KDiv)):
        _collect_expr_capabilities(expr.left, capabilities)
        _collect_expr_capabilities(expr.right, capabilities)
        return

    if isinstance(expr, ir.KNeg):
        _collect_expr_capabilities(expr.expr, capabilities)
        return

    if isinstance(expr, ir.KFuncCall):
        for arg in expr.args:
            _collect_expr_capabilities(arg, capabilities)
        return

    if isinstance(expr, ir.KMethodCall):
        _collect_expr_capabilities(expr.target, capabilities)
        for arg in expr.args:
            _collect_expr_capabilities(arg, capabilities)
        return


def check_pair_support(
    *,
    ground: ir.GroundIR,
    selection: TargetSelection,
    backend: BackendPlugin,
    runtime: RuntimePlugin,
) -> CompatibilityResult:
    required = sorted(extract_required_capabilities(ground))
    backend_catalog = dict(backend.capability_catalog())
    runtime_catalog = dict(runtime.capability_catalog())

    issues: list[SupportIssue] = []

    allowed_backends: Collection[str] = runtime.compatible_backend_ids()
    if selection.backend_id not in allowed_backends:
        issues.append(
            SupportIssue(
                code="QSOL4008",
                message=(
                    f"runtime `{selection.runtime_id}` is not compatible with backend "
                    f"`{selection.backend_id}`"
                ),
                stage="pair",
                detail={"allowed_backends": sorted(allowed_backends)},
            )
        )

    issues.extend(backend.check_support(ground, required_capabilities=required))

    compiled_model = None
    if not issues:
        compiled_model = backend.compile_model(ground)
        for diag in compiled_model.diagnostics:
            if diag.severity != Severity.ERROR:
                continue
            issues.append(
                SupportIssue(
                    code="QSOL4010",
                    message=diag.message,
                    stage="backend",
                    detail={
                        "diagnostic_code": diag.code,
                        "line": diag.span.line,
                        "col": diag.span.col,
                    },
                )
            )

    if compiled_model is not None and not issues:
        issues.extend(runtime.check_support(compiled_model, selection=selection))

    report = SupportReport(
        selection=selection,
        supported=not issues,
        issues=issues,
        required_capabilities=required,
        backend_capabilities=backend_catalog,
        runtime_capabilities=runtime_catalog,
        model_summary={
            "kind": compiled_model.kind if compiled_model is not None else "cqm",
            "stats": dict(compiled_model.stats) if compiled_model is not None else {},
        },
    )
    return CompatibilityResult(report=report, compiled_model=compiled_model)


def support_report_to_dict(report: SupportReport) -> dict[str, object]:
    return {
        "selection": {
            "runtime": report.selection.runtime_id,
            "backend": report.selection.backend_id,
        },
        "supported": report.supported,
        "required_capabilities": list(report.required_capabilities),
        "backend_capabilities": dict(report.backend_capabilities),
        "runtime_capabilities": dict(report.runtime_capabilities),
        "model_summary": dict(report.model_summary),
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "stage": issue.stage,
                "capability_id": issue.capability_id,
                "detail": dict(issue.detail),
            }
            for issue in report.issues
        ],
    }
