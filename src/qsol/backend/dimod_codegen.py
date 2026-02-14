from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, cast

import dimod

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.lower import ir

BinaryVar = Any


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
                self._emit_constraint(problem, constraint.expr, cqm, binaries, diagnostics, env={})

            for objective_stmt in problem.objectives:
                expr_obj = self._num_expr(
                    problem, objective_stmt.expr, binaries, diagnostics, env={}
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
                        problem, constraint.expr, binaries, diagnostics, env={}
                    )
                    if penalty is None:
                        diagnostics.append(
                            self._unsupported(constraint.span, "unsupported soft constraint")
                        )
                        continue
                    weight = 10.0 if constraint.kind.value == "should" else 1.0
                    objective += weight * penalty

        cqm.set_objective(objective)
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
                    cqm.add_constraint(sum(row) == 1, label=f"implicit_exactly_one:{find.name}:{a}")
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
            cqm.add_constraint(atom == 1, label=self._constraint_label(expr.span))
            return

        if isinstance(expr, ir.KNot):
            atom = self._bool_atom(problem, expr.expr, binaries, diagnostics, env)
            if atom is not None:
                cqm.add_constraint(atom == 0, label=self._constraint_label(expr.span))
                return

        if isinstance(expr, ir.KImplies):
            lhs = self._bool_atom(problem, expr.left, binaries, diagnostics, env)
            rhs = self._bool_atom(problem, expr.right, binaries, diagnostics, env)
            if lhs is not None and rhs is not None:
                cqm.add_constraint(lhs - rhs <= 0, label=self._constraint_label(expr.span))
                return

        if isinstance(expr, ir.KCompare):
            lhs = self._num_expr(problem, expr.left, binaries, diagnostics, env)
            rhs = self._num_expr(problem, expr.right, binaries, diagnostics, env)
            if lhs is not None and rhs is not None:
                label = self._constraint_label(expr.span)
                if expr.op == "=":
                    cqm.add_constraint(lhs == rhs, label=label)
                    return
                if expr.op == "!=":
                    diagnostics.append(
                        self._unsupported(
                            expr.span, "`!=` constraints are not supported in backend v1"
                        )
                    )
                    return
                if expr.op == "<=":
                    cqm.add_constraint(lhs <= rhs, label=label)
                    return
                if expr.op == "<":
                    cqm.add_constraint(lhs <= rhs - 1e-9, label=label)
                    return
                if expr.op == ">=":
                    cqm.add_constraint(lhs >= rhs, label=label)
                    return
                if expr.op == ">":
                    cqm.add_constraint(lhs >= rhs + 1e-9, label=label)
                    return

        diagnostics.append(self._unsupported(expr.span, "unsupported hard constraint shape"))

    def _soft_penalty(
        self,
        problem: ir.GroundProblem,
        expr: ir.KBoolExpr,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
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
                inner = self._soft_penalty(problem, expr.expr, binaries, diagnostics, next_env)
                if inner is None:
                    return None
                acc += inner
            return acc

        truth = self._bool_expr(problem, expr, binaries, diagnostics, env)
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
    ) -> Any | None:
        if isinstance(expr, ir.KBoolLit):
            return 1.0 if expr.value else 0.0
        if isinstance(expr, ir.KNot):
            inner = self._bool_expr(problem, expr.expr, binaries, diagnostics, env)
            return None if inner is None else (1 - inner)
        if isinstance(expr, ir.KAnd):
            left = self._bool_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._bool_expr(problem, expr.right, binaries, diagnostics, env)
            if left is None or right is None:
                return None
            return left * right
        if isinstance(expr, ir.KOr):
            left = self._bool_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._bool_expr(problem, expr.right, binaries, diagnostics, env)
            if left is None or right is None:
                return None
            return left + right - left * right
        if isinstance(expr, ir.KImplies):
            left = self._bool_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._bool_expr(problem, expr.right, binaries, diagnostics, env)
            if left is None or right is None:
                return None
            return 1 - left + left * right
        if isinstance(expr, ir.KCompare):
            diagnostics.append(
                self._unsupported(expr.span, "numeric compare in soft objective is not supported")
            )
            return None

        return self._bool_atom(problem, expr, binaries, diagnostics, env)

    def _bool_atom(
        self,
        problem: ir.GroundProblem,
        expr: ir.KExpr,
        binaries: dict[str, BinaryVar],
        diagnostics: list[Diagnostic],
        env: dict[str, str],
    ) -> Any | None:
        if isinstance(expr, ir.KMethodCall):
            label = self._method_label(problem, expr, env)
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
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env)
            return None if left is None or right is None else (left + right)
        if isinstance(expr, ir.KSub):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env)
            return None if left is None or right is None else (left - right)
        if isinstance(expr, ir.KMul):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env)
            if left is None or right is None:
                return None
            return left * right
        if isinstance(expr, ir.KDiv):
            left = self._num_expr(problem, expr.left, binaries, diagnostics, env)
            right = self._num_expr(problem, expr.right, binaries, diagnostics, env)
            if left is None or right is None:
                return None
            return left / right
        if isinstance(expr, ir.KNeg):
            inner = self._num_expr(problem, expr.expr, binaries, diagnostics, env)
            return None if inner is None else -inner
        if isinstance(expr, ir.KIfThenElse):
            cond = self._bool_expr(problem, expr.cond, binaries, diagnostics, env)
            tval = self._num_expr(problem, expr.then_expr, binaries, diagnostics, env)
            eval_ = self._num_expr(problem, expr.else_expr, binaries, diagnostics, env)
            if cond is None or tval is None or eval_ is None:
                return None
            return cond * tval + (1 - cond) * eval_
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
                term = self._num_expr(problem, expr.comp.term, binaries, diagnostics, next_env)
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
            key = self._resolve_name_arg(arg, env)
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
        self, problem: ir.GroundProblem, expr: ir.KMethodCall, env: dict[str, str]
    ) -> str | None:
        if not isinstance(expr.target, ir.KName):
            return None
        target = expr.target.name
        if expr.name == "has" and len(expr.args) == 1:
            arg = self._resolve_name_arg(expr.args[0], env)
            return None if arg is None else self._subset_label(target, arg)
        if expr.name == "is" and len(expr.args) == 2:
            a = self._resolve_name_arg(expr.args[0], env)
            b = self._resolve_name_arg(expr.args[1], env)
            if a is None or b is None:
                return None
            return self._mapping_label(target, a, b)
        return None

    def _resolve_name_arg(self, expr: ir.KExpr, env: dict[str, str]) -> str | None:
        if isinstance(expr, ir.KName):
            return env.get(expr.name, expr.name)
        if isinstance(expr, ir.KNumLit):
            return str(expr.value)
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
