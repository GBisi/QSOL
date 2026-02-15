from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, cast

import dimod
from dimod import BinaryQuadraticModel, QuadraticModel

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.lower import ir

BinaryVar = Any
CMP_EPS = 1e-6
BOOL_EPS = 1e-9
INTEGRAL_TOL = 1e-9


def _new_cqm() -> dimod.ConstrainedQuadraticModel:
    ctor = cast(Callable[[], dimod.ConstrainedQuadraticModel], dimod.ConstrainedQuadraticModel)
    return ctor()


def _new_binary(label: str) -> BinaryVar:
    ctor = cast(Callable[[str], BinaryVar], dimod.Binary)
    return ctor(label)


def _convert_cqm_to_bqm(
    cqm: dimod.ConstrainedQuadraticModel,
) -> tuple[dimod.BinaryQuadraticModel, Any]:
    converter = cast(
        Callable[[dimod.ConstrainedQuadraticModel], tuple[dimod.BinaryQuadraticModel, Any]],
        dimod.cqm_to_bqm,
    )
    return converter(cqm)


@dataclass(slots=True)
class CodegenResult:
    cqm: dimod.ConstrainedQuadraticModel
    bqm: dimod.BinaryQuadraticModel
    inverter: Any
    varmap: dict[str, str]
    diagnostics: list[Diagnostic] = field(default_factory=list)


class DimodCodegen:
    def compile(self, ground: ir.GroundIR) -> CodegenResult:
        self._label_counter = 0
        cqm = _new_cqm()
        diagnostics: list[Diagnostic] = []
        varmap: dict[str, str] = {}
        binaries: dict[str, BinaryVar] = {}

        objective = 0.0

        for problem in ground.problems:
            self._declare_find_variables(problem, cqm, binaries, varmap, diagnostics)

            for constraint in problem.constraints:
                if constraint.kind.value == "must":
                    self._emit_constraint(
                        problem, constraint.expr, cqm, binaries, diagnostics, env={}
                    )

            for objective_stmt in problem.objectives:
                expr_obj = self._num_expr(
                    problem,
                    objective_stmt.expr,
                    binaries,
                    diagnostics,
                    env={},
                    cqm=cqm,
                )
                if expr_obj is None:
                    diagnostics.append(
                        self._unsupported(objective_stmt.span, "unsupported objective expression")
                    )
                    continue
                if objective_stmt.kind.value == "minimize":
                    objective += expr_obj
                else:
                    objective += -expr_obj

            for constraint in problem.constraints:
                if constraint.kind.value in {"should", "nice"}:
                    penalty = self._soft_penalty(
                        problem,
                        constraint.expr,
                        binaries,
                        diagnostics,
                        env={},
                        cqm=cqm,
                    )
                    if penalty is None:
                        diagnostics.append(
                            self._unsupported(constraint.span, "unsupported soft constraint")
                        )
                        continue
                    weight = 10.0 if constraint.kind.value == "should" else 1.0
                    objective += weight * penalty

        cqm.set_objective(self._normalize_objective(objective))
        bqm, inverter = _convert_cqm_to_bqm(cqm)
        return CodegenResult(
            cqm=cqm,
            bqm=bqm,
            inverter=inverter,
            varmap=varmap,
            diagnostics=diagnostics,
        )

    def _declare_find_variables(
        self,
        problem: ir.GroundProblem,
        cqm: dimod.ConstrainedQuadraticModel,
        binaries: dict[str, BinaryVar],
        varmap: dict[str, str],
        diagnostics: list[Diagnostic],
    ) -> None:
        for find in sorted(problem.finds, key=lambda f: f.name):
            kind = find.unknown_type.kind
            if kind == "Subset":
                set_name = find.unknown_type.args[0]
                elems = problem.set_values.get(set_name)
                if elems is None:
                    diagnostics.append(
                        self._unsupported(find.span, f"missing set `{set_name}` for subset")
                    )
                    continue
                for elem in sorted(elems):
                    label = self._subset_label(find.name, elem)
                    binaries[label] = _new_binary(label)
                    varmap[label] = f"{find.name}.has({elem})"
            elif kind == "Mapping":
                dom_name, cod_name = find.unknown_type.args
                dom = problem.set_values.get(dom_name)
                cod = problem.set_values.get(cod_name)
                if dom is None or cod is None:
                    diagnostics.append(self._unsupported(find.span, "missing set for mapping"))
                    continue
                for a in sorted(dom):
                    row = []
                    for b in sorted(cod):
                        label = self._mapping_label(find.name, a, b)
                        binaries[label] = _new_binary(label)
                        row.append(binaries[label])
                        varmap[label] = f"{find.name}.is({a},{b})"
                    self._add_numeric_constraint(
                        cqm,
                        lhs=sum(row),
                        rhs=1.0,
                        op="=",
                        label=f"implicit_exactly_one:{find.name}:{a}",
                        span=find.span,
                        diagnostics=diagnostics,
                    )
            else:
                diagnostics.append(
                    self._unsupported(find.span, f"unsupported unknown kind `{kind}`")
                )

    def _emit_constraint(
        self,
        problem: ir.GroundProblem,
        expr: ir.KBoolExpr,
        cqm: dimod.ConstrainedQuadraticModel,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> None:
        if isinstance(expr, ir.KQuantifier):
            vals = problem.set_values.get(expr.domain_set)
            if vals is None:
                diagnostics.append(
                    self._unsupported(expr.span, f"unknown set `{expr.domain_set}` in quantifier")
                )
                return
            for value in sorted(vals):
                next_env = dict(env)
                next_env[expr.var] = value
                self._emit_constraint(problem, expr.expr, cqm, binaries, diagnostics, next_env)
            return

        if isinstance(expr, ir.KAnd):
            self._emit_constraint(problem, expr.left, cqm, binaries, diagnostics, env)
            self._emit_constraint(problem, expr.right, cqm, binaries, diagnostics, env)
            return

        atom = self._bool_atom(problem, expr, binaries, diagnostics, env)
        if atom is not None:
            self._add_numeric_constraint(
                cqm,
                lhs=atom,
                rhs=1.0,
                op="=",
                label=self._constraint_label(expr.span),
                span=expr.span,
                diagnostics=diagnostics,
            )
            return

        if isinstance(expr, ir.KNot):
            atom = self._bool_atom(problem, expr.expr, binaries, diagnostics, env)
            if atom is not None:
                self._add_numeric_constraint(
                    cqm,
                    lhs=atom,
                    rhs=0.0,
                    op="=",
                    label=self._constraint_label(expr.span),
                    span=expr.span,
                    diagnostics=diagnostics,
                )
                return

        if isinstance(expr, ir.KImplies):
            lhs = self._bool_atom(problem, expr.left, binaries, diagnostics, env)
            rhs = self._bool_atom(problem, expr.right, binaries, diagnostics, env)
            if lhs is not None and rhs is not None:
                self._add_numeric_constraint(
                    cqm,
                    lhs=lhs,
                    rhs=rhs,
                    op="<=",
                    label=self._constraint_label(expr.span),
                    span=expr.span,
                    diagnostics=diagnostics,
                )
                return

        if isinstance(expr, ir.KCompare):
            lhs = self._num_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            rhs = self._num_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if lhs is not None and rhs is not None:
                label = self._constraint_label(expr.span)
                if expr.op == "=":
                    self._add_numeric_constraint(
                        cqm,
                        lhs=lhs,
                        rhs=rhs,
                        op=expr.op,
                        label=label,
                        span=expr.span,
                        diagnostics=diagnostics,
                    )
                    return
                if expr.op == "!=":
                    indicator = self._compare_truth_indicator(cqm, expr, lhs, rhs, diagnostics)
                    if indicator is None:
                        diagnostics.append(
                            self._unsupported(expr.span, "unsupported `!=` hard constraint")
                        )
                        return
                    self._add_numeric_constraint(
                        cqm,
                        lhs=indicator,
                        rhs=1.0,
                        op="=",
                        label=label,
                        span=expr.span,
                        diagnostics=diagnostics,
                    )
                    return
                if expr.op == "<=":
                    self._add_numeric_constraint(
                        cqm,
                        lhs=lhs,
                        rhs=rhs,
                        op=expr.op,
                        label=label,
                        span=expr.span,
                        diagnostics=diagnostics,
                    )
                    return
                if expr.op == "<":
                    self._add_numeric_constraint(
                        cqm,
                        lhs=lhs,
                        rhs=rhs,
                        op=expr.op,
                        label=label,
                        span=expr.span,
                        diagnostics=diagnostics,
                    )
                    return
                if expr.op == ">=":
                    self._add_numeric_constraint(
                        cqm,
                        lhs=lhs,
                        rhs=rhs,
                        op=expr.op,
                        label=label,
                        span=expr.span,
                        diagnostics=diagnostics,
                    )
                    return
                if expr.op == ">":
                    self._add_numeric_constraint(
                        cqm,
                        lhs=lhs,
                        rhs=rhs,
                        op=expr.op,
                        label=label,
                        span=expr.span,
                        diagnostics=diagnostics,
                    )
                    return

        diagnostics.append(self._unsupported(expr.span, "unsupported hard constraint shape"))

    def _is_quadratic_model(self, expr: Any) -> bool:
        return isinstance(expr, (BinaryQuadraticModel, QuadraticModel))

    def _normalize_objective(self, objective: Any) -> BinaryQuadraticModel | QuadraticModel:
        if self._is_quadratic_model(objective):
            return cast(BinaryQuadraticModel | QuadraticModel, objective)
        if isinstance(objective, (int, float)):
            return BinaryQuadraticModel({}, {}, float(objective), dimod.BINARY)
        raise TypeError(f"unsupported objective type `{type(objective).__name__}`")

    def _add_numeric_constraint(
        self,
        cqm: dimod.ConstrainedQuadraticModel,
        lhs: Any,
        rhs: Any,
        op: str,
        label: str,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> None:
        if op not in {"=", "<=", "<", ">=", ">"}:
            diagnostics.append(self._unsupported(span, f"unsupported comparison operator `{op}`"))
            return

        try:
            diff = lhs - rhs
        except TypeError:
            diagnostics.append(
                self._unsupported(span, f"unsupported numeric comparison operands for `{op}`")
            )
            return

        if self._is_quadratic_model(diff):
            integral_diff = self._is_integral_value(diff)
            if op == "=":
                sense, bound = "==", 0.0
            elif op == "<=":
                sense, bound = "<=", 0.0
            elif op == "<":
                sense, bound = "<=", (-1.0 if integral_diff else -CMP_EPS)
            elif op == ">=":
                sense, bound = ">=", 0.0
            else:  # op == ">"
                sense, bound = ">=", (1.0 if integral_diff else CMP_EPS)
            cqm.add_constraint_from_model(diff, sense=sense, rhs=bound, label=label)
            return

        if not isinstance(diff, (int, float)):
            diagnostics.append(
                self._unsupported(span, f"unsupported numeric comparison operands for `{op}`")
            )
            return

        value = float(diff)
        if op == "=":
            satisfied = abs(value) <= 1e-12
        elif op == "<=":
            satisfied = value <= 0.0
        elif op == "<":
            satisfied = value < 0.0
        elif op == ">=":
            satisfied = value >= 0.0
        else:  # op == ">"
            satisfied = value > 0.0

        if not satisfied:
            diagnostics.append(self._unsupported(span, f"infeasible constant constraint `{op}`"))

    def _soft_penalty(
        self,
        problem: ir.GroundProblem,
        expr: ir.KBoolExpr,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
        cqm: dimod.ConstrainedQuadraticModel,
    ) -> Any | None:
        if isinstance(expr, ir.KQuantifier):
            vals = problem.set_values.get(expr.domain_set)
            if vals is None:
                diagnostics.append(
                    self._unsupported(
                        expr.span, f"unknown set `{expr.domain_set}` in soft quantifier"
                    )
                )
                return None
            acc = 0.0
            for value in sorted(vals):
                next_env = dict(env)
                next_env[expr.var] = value
                inner = self._soft_penalty(
                    problem,
                    expr.expr,
                    binaries,
                    diagnostics,
                    next_env,
                    cqm=cqm,
                )
                if inner is None:
                    return None
                acc += inner
            return acc

        truth = self._bool_expr(
            problem,
            expr,
            binaries,
            diagnostics,
            env,
            cqm=cqm,
        )
        if truth is None:
            return None
        return 1 - truth

    def _bool_expr(
        self,
        problem: ir.GroundProblem,
        expr: ir.KBoolExpr,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
        cqm: dimod.ConstrainedQuadraticModel,
    ) -> Any | None:
        if isinstance(expr, ir.KBoolLit):
            return 1.0 if expr.value else 0.0
        if isinstance(expr, ir.KNot):
            inner = self._bool_expr(problem, expr.expr, binaries, diagnostics, env, cqm=cqm)
            return None if inner is None else (1 - inner)
        if isinstance(expr, ir.KAnd):
            left = self._bool_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._bool_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if left is None or right is None:
                return None
            return self._bool_and(cqm, left, right, span=expr.span, diagnostics=diagnostics)
        if isinstance(expr, ir.KOr):
            left = self._bool_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._bool_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if left is None or right is None:
                return None
            return self._bool_or(cqm, left, right, span=expr.span, diagnostics=diagnostics)
        if isinstance(expr, ir.KImplies):
            left = self._bool_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._bool_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if left is None or right is None:
                return None
            return self._bool_or(cqm, 1 - left, right, span=expr.span, diagnostics=diagnostics)
        if isinstance(expr, ir.KCompare):
            lhs = self._num_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            rhs = self._num_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if lhs is None or rhs is None:
                return None
            indicator = self._compare_truth_indicator(cqm, expr, lhs, rhs, diagnostics)
            if indicator is None:
                diagnostics.append(
                    self._unsupported(
                        expr.span, "unsupported compare expression in boolean context"
                    )
                )
                return None
            return indicator

        return self._bool_atom(problem, expr, binaries, diagnostics, env)

    def _bool_constant(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            number = float(value)
            if abs(number) <= BOOL_EPS:
                return 0.0
            if abs(number - 1.0) <= BOOL_EPS:
                return 1.0
        return None

    def _bool_and(
        self,
        cqm: dimod.ConstrainedQuadraticModel,
        left: Any,
        right: Any,
        *,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> Any | None:
        left_const = self._bool_constant(left)
        right_const = self._bool_constant(right)
        if left_const is not None and right_const is not None:
            return 1.0 if (left_const == 1.0 and right_const == 1.0) else 0.0
        if left_const == 0.0 or right_const == 0.0:
            return 0.0
        if left_const == 1.0:
            return right
        if right_const == 1.0:
            return left

        try:
            return left * right
        except TypeError:
            # Fallback for non-quadratic-safe products (e.g. quadratic * binary).
            pass

        z = _new_binary(self._aux_label("and", span))
        self._add_numeric_constraint(
            cqm,
            lhs=z,
            rhs=left,
            op="<=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        self._add_numeric_constraint(
            cqm,
            lhs=z,
            rhs=right,
            op="<=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        self._add_numeric_constraint(
            cqm,
            lhs=z,
            rhs=left + right - 1,
            op=">=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        return z

    def _bool_or(
        self,
        cqm: dimod.ConstrainedQuadraticModel,
        left: Any,
        right: Any,
        *,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> Any | None:
        left_const = self._bool_constant(left)
        right_const = self._bool_constant(right)
        if left_const is not None and right_const is not None:
            return 1.0 if (left_const == 1.0 or right_const == 1.0) else 0.0
        if left_const == 1.0 or right_const == 1.0:
            return 1.0
        if left_const == 0.0:
            return right
        if right_const == 0.0:
            return left

        try:
            return left + right - (left * right)
        except TypeError:
            # Fallback for non-quadratic-safe products (e.g. quadratic * binary).
            pass

        z = _new_binary(self._aux_label("or", span))
        self._add_numeric_constraint(
            cqm,
            lhs=z,
            rhs=left,
            op=">=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        self._add_numeric_constraint(
            cqm,
            lhs=z,
            rhs=right,
            op=">=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        self._add_numeric_constraint(
            cqm,
            lhs=z,
            rhs=left + right,
            op="<=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        return z

    def _compare_truth_indicator(
        self,
        cqm: dimod.ConstrainedQuadraticModel,
        expr: ir.KCompare,
        lhs: Any,
        rhs: Any,
        diagnostics: list[Diagnostic],
    ) -> Any | None:
        try:
            diff = lhs - rhs
        except TypeError:
            diagnostics.append(
                self._unsupported(expr.span, "compare operands are not numeric in boolean context")
            )
            return None
        integral_diff = self._is_integral_value(diff)
        strict_lo = -1.0 if integral_diff else -CMP_EPS
        strict_hi = 1.0 if integral_diff else CMP_EPS

        if expr.op == "<":
            return self._indicator_leq(
                cqm,
                diff,
                threshold=strict_lo,
                span=expr.span,
                diagnostics=diagnostics,
            )
        if expr.op == "<=":
            return self._indicator_leq(
                cqm,
                diff,
                threshold=(0.0 if integral_diff else CMP_EPS),
                span=expr.span,
                diagnostics=diagnostics,
            )
        if expr.op == ">":
            return self._indicator_geq(
                cqm,
                diff,
                threshold=strict_hi,
                span=expr.span,
                diagnostics=diagnostics,
            )
        if expr.op == ">=":
            return self._indicator_geq(
                cqm,
                diff,
                threshold=(0.0 if integral_diff else -CMP_EPS),
                span=expr.span,
                diagnostics=diagnostics,
            )
        if expr.op in {"=", "!="}:
            z_low = self._indicator_leq(
                cqm,
                diff,
                threshold=strict_lo,
                span=expr.span,
                diagnostics=diagnostics,
            )
            z_high = self._indicator_geq(
                cqm,
                diff,
                threshold=strict_hi,
                span=expr.span,
                diagnostics=diagnostics,
            )
            if z_low is None or z_high is None:
                return None

            z_ne = z_low + z_high
            self._add_numeric_constraint(
                cqm,
                lhs=z_ne,
                rhs=1.0,
                op="<=",
                label=self._constraint_label(expr.span),
                span=expr.span,
                diagnostics=diagnostics,
            )
            if expr.op == "!=":
                return z_ne
            return 1 - z_ne

        diagnostics.append(
            self._unsupported(expr.span, f"unsupported comparison operator `{expr.op}`")
        )
        return None

    def _indicator_leq(
        self,
        cqm: dimod.ConstrainedQuadraticModel,
        diff: Any,
        *,
        threshold: float,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> Any | None:
        if isinstance(diff, (int, float)):
            return 1.0 if float(diff) <= threshold else 0.0

        bounds = self._quadratic_bounds(diff)
        if bounds is None:
            diagnostics.append(
                self._unsupported(span, "unable to bound compare expression for <= indicator")
            )
            return None
        lo, hi = bounds
        if hi <= threshold:
            return 1.0
        if lo > threshold:
            return 0.0

        z = _new_binary(self._aux_label("leq", span))
        self._add_numeric_constraint(
            cqm,
            lhs=diff,
            rhs=threshold + (hi - threshold) * (1 - z),
            op="<=",
            label=self._constraint_label(span),
            span=span,
            diagnostics=diagnostics,
        )
        if abs(lo - threshold) > INTEGRAL_TOL:
            self._add_numeric_constraint(
                cqm,
                lhs=diff,
                rhs=threshold + (lo - threshold) * z,
                op=">=",
                label=self._constraint_label(span),
                span=span,
                diagnostics=diagnostics,
            )
        return z

    def _indicator_geq(
        self,
        cqm: dimod.ConstrainedQuadraticModel,
        diff: Any,
        *,
        threshold: float,
        span: Span,
        diagnostics: list[Diagnostic],
    ) -> Any | None:
        if isinstance(diff, (int, float)):
            return 1.0 if float(diff) >= threshold else 0.0

        bounds = self._quadratic_bounds(diff)
        if bounds is None:
            diagnostics.append(
                self._unsupported(span, "unable to bound compare expression for >= indicator")
            )
            return None
        lo, hi = bounds
        if lo >= threshold:
            return 1.0
        if hi < threshold:
            return 0.0

        z = _new_binary(self._aux_label("geq", span))
        if abs(lo - threshold) > INTEGRAL_TOL:
            self._add_numeric_constraint(
                cqm,
                lhs=diff,
                rhs=threshold + (lo - threshold) * (1 - z),
                op=">=",
                label=self._constraint_label(span),
                span=span,
                diagnostics=diagnostics,
            )
        if abs(hi - threshold) > INTEGRAL_TOL:
            self._add_numeric_constraint(
                cqm,
                lhs=diff,
                rhs=threshold + (hi - threshold) * z,
                op="<=",
                label=self._constraint_label(span),
                span=span,
                diagnostics=diagnostics,
            )
        return z

    def _quadratic_bounds(self, expr: Any) -> tuple[float, float] | None:
        if not self._is_quadratic_model(expr):
            return None

        model = cast(BinaryQuadraticModel | QuadraticModel, expr)
        lo = float(model.offset)
        hi = float(model.offset)

        for bias in model.linear.values():
            b = float(bias)
            lo += min(0.0, b)
            hi += max(0.0, b)

        for bias in model.quadratic.values():
            b = float(bias)
            lo += min(0.0, b)
            hi += max(0.0, b)
        return lo, hi

    def _is_integral_value(self, expr: Any) -> bool:
        if isinstance(expr, bool):
            return True
        if isinstance(expr, int):
            return True
        if isinstance(expr, float):
            return abs(expr - round(expr)) <= INTEGRAL_TOL
        if not self._is_quadratic_model(expr):
            return False
        model = cast(BinaryQuadraticModel | QuadraticModel, expr)
        values = [model.offset, *model.linear.values(), *model.quadratic.values()]
        return all(abs(float(value) - round(float(value))) <= INTEGRAL_TOL for value in values)

    def _aux_label(self, prefix: str, span: Span) -> str:
        self._label_counter += 1
        return f"aux:{prefix}:{span.line}:{span.col}:{self._label_counter}"

    def _bool_atom(
        self,
        problem: ir.GroundProblem,
        expr: ir.KExpr,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> Any | None:
        if isinstance(expr, ir.KName):
            if expr.name in problem.params and not isinstance(problem.params[expr.name], dict):
                val = problem.params[expr.name]
                truth = self._bool_constant(val)
                if truth is not None:
                    return truth
            return None
        if isinstance(expr, ir.KMethodCall):
            label = self._method_label(problem, expr, diagnostics, env)
            if label is None:
                diagnostics.append(self._unsupported(expr.span, "unsupported method call atom"))
                return None
            if label not in binaries:
                diagnostics.append(self._unsupported(expr.span, f"unknown variable `{label}`"))
                return None
            return binaries[label]
        if isinstance(expr, ir.KFuncCall):
            value = self._bool_func_call(problem, expr, diagnostics, env)
            if value is None:
                diagnostics.append(self._unsupported(expr.span, "unsupported function call atom"))
                return None
            return value
        if isinstance(expr, ir.KBoolLit):
            return 1.0 if expr.value else 0.0
        return None

    def _num_expr(
        self,
        problem: ir.GroundProblem,
        expr: ir.KExpr,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
        cqm: dimod.ConstrainedQuadraticModel,
    ) -> Any | None:
        if isinstance(expr, ir.KNumLit):
            return expr.value
        if isinstance(expr, ir.KName):
            if expr.name in env:
                bound_value = env[expr.name]
                try:
                    return float(bound_value)
                except ValueError:
                    diagnostics.append(
                        self._unsupported(
                            expr.span, f"non-numeric binder `{expr.name}` in numeric context"
                        )
                    )
                    return None
            if expr.name in problem.params and not isinstance(problem.params[expr.name], dict):
                val = problem.params[expr.name]
                if isinstance(val, (int, float)):
                    return float(val)
            diagnostics.append(
                self._unsupported(expr.span, f"unsupported numeric name `{expr.name}`")
            )
            return None
        if isinstance(expr, ir.KMethodCall):
            return self._bool_atom(problem, expr, binaries, diagnostics, env)
        if isinstance(expr, ir.KFuncCall):
            num_value = self._num_func_call(problem, expr, diagnostics, env)
            if num_value is None:
                diagnostics.append(
                    self._unsupported(expr.span, "unsupported numeric function call")
                )
                return None
            return num_value
        if isinstance(expr, ir.KAdd):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            return None if left is None or right is None else (left + right)
        if isinstance(expr, ir.KSub):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            return None if left is None or right is None else (left - right)
        if isinstance(expr, ir.KMul):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if left is None or right is None:
                return None
            try:
                return left * right
            except TypeError:
                diagnostics.append(
                    self._unsupported(expr.span, "unsupported numeric multiplication operands")
                )
                return None
        if isinstance(expr, ir.KDiv):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env, cqm=cqm)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env, cqm=cqm)
            if left is None or right is None:
                return None
            try:
                return left / right
            except ZeroDivisionError:
                diagnostics.append(self._unsupported(expr.span, "division by zero"))
                return None
            except TypeError:
                diagnostics.append(
                    self._unsupported(expr.span, "unsupported numeric division operands")
                )
                return None
        if isinstance(expr, ir.KNeg):
            inner = self._num_expr(problem, expr.expr, binaries, diagnostics, env, cqm=cqm)
            return None if inner is None else -inner
        if isinstance(expr, ir.KIfThenElse):
            cond = self._bool_expr(problem, expr.cond, binaries, diagnostics, env, cqm=cqm)
            tval = self._num_expr(problem, expr.then_expr, binaries, diagnostics, env, cqm=cqm)
            eval_ = self._num_expr(problem, expr.else_expr, binaries, diagnostics, env, cqm=cqm)
            if cond is None or tval is None or eval_ is None:
                return None
            try:
                return cond * tval + (1 - cond) * eval_
            except TypeError:
                diagnostics.append(
                    self._unsupported(expr.span, "unsupported conditional numeric expression")
                )
                return None
        if isinstance(expr, ir.KSum):
            vals = problem.set_values.get(expr.comp.domain_set)
            if vals is None:
                diagnostics.append(
                    self._unsupported(expr.span, f"unknown set `{expr.comp.domain_set}` in sum")
                )
                return None
            acc = 0.0
            for val in sorted(vals):
                next_env = dict(env)
                next_env[expr.comp.var] = val
                term = self._num_expr(
                    problem,
                    expr.comp.term,
                    binaries,
                    diagnostics,
                    next_env,
                    cqm=cqm,
                )
                if term is None:
                    return None
                acc += term
            return acc

        diagnostics.append(
            self._unsupported(expr.span, f"unsupported numeric expression `{type(expr).__name__}`")
        )
        return None

    def _bool_func_call(
        self,
        problem: ir.GroundProblem,
        expr: ir.KFuncCall,
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> float | None:
        value = self._param_call_value(problem, expr, diagnostics, env)
        if value is None:
            return None

        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return None

    def _num_func_call(
        self,
        problem: ir.GroundProblem,
        expr: ir.KFuncCall,
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> float | None:
        value = self._param_call_value(problem, expr, diagnostics, env)
        if value is None:
            return None
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _param_call_value(
        self,
        problem: ir.GroundProblem,
        expr: ir.KFuncCall,
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> object | None:
        if expr.name not in problem.params:
            return None
        value: object = problem.params[expr.name]
        for arg in expr.args:
            key = self._resolve_name_arg(problem, arg, diagnostics, env)
            if key is None or not isinstance(value, dict):
                return None
            if key not in value:
                diagnostics.append(
                    self._unsupported(expr.span, f"unknown index `{key}` for param `{expr.name}`")
                )
                return None
            value = value[key]
        return value

    def _method_label(
        self,
        problem: ir.GroundProblem,
        expr: ir.KMethodCall,
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> str | None:
        if not isinstance(expr.target, ir.KName):
            return None
        target = expr.target.name
        if expr.name == "has" and len(expr.args) == 1:
            arg = self._resolve_name_arg(problem, expr.args[0], diagnostics, env)
            return None if arg is None else self._subset_label(target, arg)
        if expr.name == "is" and len(expr.args) == 2:
            a = self._resolve_name_arg(problem, expr.args[0], diagnostics, env)
            b = self._resolve_name_arg(problem, expr.args[1], diagnostics, env)
            if a is None or b is None:
                return None
            return self._mapping_label(target, a, b)
        return None

    def _resolve_name_arg(
        self,
        problem: ir.GroundProblem,
        expr: ir.KExpr,
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> str | None:
        if isinstance(expr, ir.KName):
            if expr.name in env:
                return env[expr.name]
            if expr.name in problem.params and not isinstance(problem.params[expr.name], dict):
                return str(problem.params[expr.name])
            return expr.name
        if isinstance(expr, ir.KNumLit):
            return str(int(expr.value)) if float(expr.value).is_integer() else str(expr.value)
        if isinstance(expr, ir.KFuncCall):
            value = self._param_call_value(problem, expr, diagnostics, env)
            if value is None or isinstance(value, dict):
                return None
            return str(value)
        return None

    def _subset_label(self, name: str, elem: str) -> str:
        return f"{name}.has[{elem}]"

    def _mapping_label(self, name: str, a: str, b: str) -> str:
        return f"{name}.is[{a},{b}]"

    def _constraint_label(self, span: Span) -> str:
        self._label_counter += 1
        return f"c:{span.line}:{span.col}:{span.end_line}:{span.end_col}:{self._label_counter}"

    def _unsupported(self, span: Span, message: str) -> Diagnostic:
        return Diagnostic(
            severity=Severity.ERROR,
            code="QSOL3001",
            message=message,
            span=span,
        )
