from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.parse import ast


@dataclass(slots=True)
class UnknownElaborationResult:
    program: ast.Program
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(slots=True)
class _InstanceContext:
    alias: str
    unknown_def: ast.UnknownDef
    type_arg_map: dict[str, str]
    member_aliases: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _Expansion:
    finds: list[ast.FindDecl] = field(default_factory=list)
    laws: list[ast.Constraint] = field(default_factory=list)


@dataclass(slots=True)
class UnknownElaborator:
    _diagnostics: list[Diagnostic] = field(default_factory=list)
    _unknown_defs: dict[str, ast.UnknownDef] = field(default_factory=dict)
    _global_predicates: dict[str, ast.PredicateDef] = field(default_factory=dict)
    _global_functions: dict[str, ast.FunctionDef] = field(default_factory=dict)
    _custom_instances: dict[str, _InstanceContext] = field(default_factory=dict)
    _used_find_names: set[str] = field(default_factory=set)

    def elaborate(self, program: ast.Program) -> UnknownElaborationResult:
        self._unknown_defs = {}
        self._global_predicates = {}
        self._global_functions = {}
        for item in program.items:
            if isinstance(item, ast.UnknownDef) and item.name not in self._unknown_defs:
                self._unknown_defs[item.name] = item
            elif isinstance(item, ast.PredicateDef):
                if item.name in self._global_predicates or item.name in self._global_functions:
                    self._diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2101",
                            message=f"redefinition of macro `{item.name}`",
                            span=item.span,
                            help=[
                                "Use unique names across top-level `predicate` and `function` declarations."
                            ],
                        )
                    )
                    continue
                self._global_predicates[item.name] = item
            elif isinstance(item, ast.FunctionDef):
                if item.name in self._global_predicates or item.name in self._global_functions:
                    self._diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2101",
                            message=f"redefinition of macro `{item.name}`",
                            span=item.span,
                            help=[
                                "Use unique names across top-level `predicate` and `function` declarations."
                            ],
                        )
                    )
                    continue
                self._global_functions[item.name] = item

        items: list[ast.TopItem] = []
        for item in program.items:
            if isinstance(item, ast.ProblemDef):
                items.append(self._elaborate_problem(item))
            else:
                items.append(item)

        return UnknownElaborationResult(
            program=replace(program, items=items), diagnostics=list(self._diagnostics)
        )

    def _elaborate_problem(self, problem: ast.ProblemDef) -> ast.ProblemDef:
        self._custom_instances = {}
        self._used_find_names = {
            stmt.name for stmt in problem.stmts if isinstance(stmt, ast.FindDecl)
        }

        find_replacements: dict[int, list[ast.ProblemStmt]] = {}
        for stmt in problem.stmts:
            if not isinstance(stmt, ast.FindDecl):
                continue
            if stmt.unknown_type.kind in {"Subset", "Mapping"}:
                find_replacements[id(stmt)] = [stmt]
                continue

            unknown_def = self._unknown_defs.get(stmt.unknown_type.kind)
            if unknown_def is None:
                # Keep unresolved custom find; resolver will report unknown unknown-type.
                find_replacements[id(stmt)] = [stmt]
                continue

            expansion = self._expand_custom_find(
                alias=stmt.name,
                unknown_def=unknown_def,
                unknown_type=stmt.unknown_type,
                path=(stmt.name,),
                decl_span=stmt.span,
            )
            if expansion is None:
                find_replacements[id(stmt)] = [stmt]
                continue
            find_replacements[id(stmt)] = [*expansion.finds, *expansion.laws]

        assembled: list[ast.ProblemStmt] = []
        for stmt in problem.stmts:
            if isinstance(stmt, ast.FindDecl):
                assembled.extend(find_replacements.get(id(stmt), [stmt]))
                continue
            assembled.append(stmt)

        rewritten: list[ast.ProblemStmt] = []
        for stmt in assembled:
            if isinstance(stmt, ast.Constraint):
                constraint_expr = cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        stmt.expr,
                        current_instance=None,
                        value_subst={},
                        set_subst={},
                        call_stack=(),
                    ),
                )
                guard = (
                    cast(
                        ast.BoolExpr,
                        self._rewrite_expr(
                            stmt.guard,
                            current_instance=None,
                            value_subst={},
                            set_subst={},
                            call_stack=(),
                        ),
                    )
                    if stmt.guard is not None
                    else None
                )
                rewritten.append(replace(stmt, expr=constraint_expr, guard=guard))
            elif isinstance(stmt, ast.Objective):
                objective_expr = cast(
                    ast.NumExpr,
                    self._rewrite_expr(
                        stmt.expr,
                        current_instance=None,
                        value_subst={},
                        set_subst={},
                        call_stack=(),
                    ),
                )
                rewritten.append(replace(stmt, expr=objective_expr))
            else:
                rewritten.append(stmt)

        return replace(problem, stmts=rewritten)

    def _expand_custom_find(
        self,
        *,
        alias: str,
        unknown_def: ast.UnknownDef,
        unknown_type: ast.UnknownTypeRef,
        path: tuple[str, ...],
        decl_span: Span,
    ) -> _Expansion | None:
        if len(unknown_type.args) != len(unknown_def.formals):
            self._diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2101",
                    message=(
                        f"unknown `{unknown_def.name}` expects {len(unknown_def.formals)} "
                        f"argument(s), got {len(unknown_type.args)}"
                    ),
                    span=decl_span,
                    help=[
                        "Match `find` type arguments with unknown formal parameter count.",
                    ],
                )
            )
            return None

        context = _InstanceContext(
            alias=alias,
            unknown_def=unknown_def,
            type_arg_map={
                formal: actual
                for formal, actual in zip(unknown_def.formals, unknown_type.args, strict=False)
            },
        )
        self._custom_instances[alias] = context

        out = _Expansion()
        for rep_decl in unknown_def.rep_block:
            instantiated_type = self._instantiate_unknown_type(
                rep_decl.unknown_type, set_subst=context.type_arg_map
            )
            member_alias = self._allocate_alias((*path, rep_decl.name))
            context.member_aliases[rep_decl.name] = member_alias

            if instantiated_type.kind in {"Subset", "Mapping"}:
                out.finds.append(
                    ast.FindDecl(
                        span=rep_decl.span,
                        name=member_alias,
                        unknown_type=instantiated_type,
                    )
                )
                continue

            child_unknown = self._unknown_defs.get(instantiated_type.kind)
            if child_unknown is None:
                out.finds.append(
                    ast.FindDecl(
                        span=rep_decl.span,
                        name=member_alias,
                        unknown_type=instantiated_type,
                    )
                )
                continue

            child_expansion = self._expand_custom_find(
                alias=member_alias,
                unknown_def=child_unknown,
                unknown_type=instantiated_type,
                path=(*path, rep_decl.name),
                decl_span=rep_decl.span,
            )
            if child_expansion is None:
                out.finds.append(
                    ast.FindDecl(
                        span=rep_decl.span,
                        name=member_alias,
                        unknown_type=instantiated_type,
                    )
                )
                continue
            out.finds.extend(child_expansion.finds)
            out.laws.extend(child_expansion.laws)

        for law in unknown_def.laws_block:
            expr = cast(
                ast.BoolExpr,
                self._rewrite_expr(
                    law.expr,
                    current_instance=context,
                    value_subst={},
                    set_subst=context.type_arg_map,
                    call_stack=(),
                ),
            )
            guard = (
                cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        law.guard,
                        current_instance=context,
                        value_subst={},
                        set_subst=context.type_arg_map,
                        call_stack=(),
                    ),
                )
                if law.guard is not None
                else None
            )
            out.laws.append(replace(law, expr=expr, guard=guard))

        return out

    def _instantiate_unknown_type(
        self, unknown_type: ast.UnknownTypeRef, *, set_subst: dict[str, str]
    ) -> ast.UnknownTypeRef:
        return replace(
            unknown_type,
            args=tuple(set_subst.get(arg, arg) for arg in unknown_type.args),
        )

    def _allocate_alias(self, path: tuple[str, ...]) -> str:
        base = "__qsol_u__" + "__".join(path)
        candidate = base
        idx = 1
        while candidate in self._used_find_names:
            idx += 1
            candidate = f"{base}__{idx}"
        self._used_find_names.add(candidate)
        return candidate

    def _rewrite_expr(
        self,
        expr: ast.Expr,
        *,
        current_instance: _InstanceContext | None,
        value_subst: dict[str, ast.Expr],
        set_subst: dict[str, str],
        call_stack: tuple[tuple[str, str], ...],
    ) -> ast.Expr:
        if isinstance(expr, ast.NameRef):
            if expr.name in value_subst:
                return value_subst[expr.name]
            if current_instance is not None and expr.name in current_instance.member_aliases:
                return ast.NameRef(span=expr.span, name=current_instance.member_aliases[expr.name])
            if expr.name in set_subst:
                return ast.NameRef(span=expr.span, name=set_subst[expr.name])
            return expr

        if isinstance(expr, ast.BoolLit | ast.NumLit | ast.StringLit):
            return expr

        if isinstance(expr, ast.Not):
            return replace(
                expr,
                expr=cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        expr.expr,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
            )
        if isinstance(expr, ast.And | ast.Or | ast.Implies):
            return replace(
                expr,
                left=cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        expr.left,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
                right=cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        expr.right,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
            )
        if isinstance(expr, ast.Compare):
            return replace(
                expr,
                left=self._rewrite_expr(
                    expr.left,
                    current_instance=current_instance,
                    value_subst=value_subst,
                    set_subst=set_subst,
                    call_stack=call_stack,
                ),
                right=self._rewrite_expr(
                    expr.right,
                    current_instance=current_instance,
                    value_subst=value_subst,
                    set_subst=set_subst,
                    call_stack=call_stack,
                ),
            )
        if isinstance(expr, ast.FuncCall):
            rewritten_args = [
                self._rewrite_expr(
                    arg,
                    current_instance=current_instance,
                    value_subst=value_subst,
                    set_subst=set_subst,
                    call_stack=call_stack,
                )
                for arg in expr.args
            ]
            call = replace(expr, args=rewritten_args)
            if expr.call_style == "bracket" or expr.name == "size":
                return call

            if current_instance is not None:
                view_member = self._view_member(current_instance.unknown_def, expr.name)
                if isinstance(view_member, ast.PredicateDef):
                    return self._inline_view_predicate_call(
                        instance=current_instance,
                        predicate=view_member,
                        call_args=rewritten_args,
                        call_span=expr.span,
                        call_stack=call_stack,
                    )
                if isinstance(view_member, ast.FunctionDef):
                    return self._inline_view_function_call(
                        instance=current_instance,
                        function=view_member,
                        call_args=rewritten_args,
                        call_span=expr.span,
                        call_stack=call_stack,
                    )

            global_predicate = self._global_predicates.get(expr.name)
            if global_predicate is not None:
                return self._inline_global_predicate_call(
                    predicate=global_predicate,
                    call_args=rewritten_args,
                    call_span=expr.span,
                    current_instance=current_instance,
                    set_subst=set_subst,
                    call_stack=call_stack,
                )
            global_function = self._global_functions.get(expr.name)
            if global_function is not None:
                return self._inline_global_function_call(
                    function=global_function,
                    call_args=rewritten_args,
                    call_span=expr.span,
                    current_instance=current_instance,
                    set_subst=set_subst,
                    call_stack=call_stack,
                )
            return call
        if isinstance(expr, ast.MethodCall):
            rewritten_target = self._rewrite_expr(
                expr.target,
                current_instance=current_instance,
                value_subst=value_subst,
                set_subst=set_subst,
                call_stack=call_stack,
            )
            rewritten_args = [
                self._rewrite_expr(
                    arg,
                    current_instance=current_instance,
                    value_subst=value_subst,
                    set_subst=set_subst,
                    call_stack=call_stack,
                )
                for arg in expr.args
            ]
            method_call = replace(
                expr,
                target=rewritten_target,
                args=rewritten_args,
            )
            if isinstance(rewritten_target, ast.NameRef):
                target_name = rewritten_target.name
                instance = self._custom_instances.get(target_name)
                if instance is not None:
                    view_member = self._view_member(instance.unknown_def, expr.name)
                    if view_member is None:
                        self._diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2101",
                                message=f"unknown method `{expr.name}` for unknown `{instance.unknown_def.name}`",
                                span=expr.span,
                                help=[
                                    "Declare a matching predicate/function in the unknown `view` block.",
                                ],
                            )
                        )
                        return ast.BoolLit(span=expr.span, value=False)
                    if isinstance(view_member, ast.PredicateDef):
                        return self._inline_view_predicate_call(
                            instance=instance,
                            predicate=view_member,
                            call_args=rewritten_args,
                            call_span=expr.span,
                            call_stack=call_stack,
                        )
                    return self._inline_view_function_call(
                        instance=instance,
                        function=view_member,
                        call_args=rewritten_args,
                        call_span=expr.span,
                        call_stack=call_stack,
                    )
            return method_call
        if isinstance(expr, ast.Add | ast.Sub | ast.Mul | ast.Div):
            return replace(
                expr,
                left=cast(
                    ast.NumExpr,
                    self._rewrite_expr(
                        expr.left,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
                right=cast(
                    ast.NumExpr,
                    self._rewrite_expr(
                        expr.right,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
            )
        if isinstance(expr, ast.Neg):
            return replace(
                expr,
                expr=cast(
                    ast.NumExpr,
                    self._rewrite_expr(
                        expr.expr,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
            )
        if isinstance(expr, ast.IfThenElse):
            return replace(
                expr,
                cond=cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        expr.cond,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
                then_expr=cast(
                    ast.NumExpr,
                    self._rewrite_expr(
                        expr.then_expr,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
                else_expr=cast(
                    ast.NumExpr,
                    self._rewrite_expr(
                        expr.else_expr,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
            )
        if isinstance(expr, ast.Quantifier):
            return replace(
                expr,
                domain_set=set_subst.get(expr.domain_set, expr.domain_set),
                expr=cast(
                    ast.BoolExpr,
                    self._rewrite_expr(
                        expr.expr,
                        current_instance=current_instance,
                        value_subst=value_subst,
                        set_subst=set_subst,
                        call_stack=call_stack,
                    ),
                ),
            )
        if isinstance(expr, ast.BoolAggregate):
            comp = expr.comp
            return replace(
                expr,
                comp=replace(
                    comp,
                    term=cast(
                        ast.BoolExpr,
                        self._rewrite_expr(
                            comp.term,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        ),
                    ),
                    domain_set=set_subst.get(comp.domain_set, comp.domain_set),
                    where=cast(
                        ast.BoolExpr | None,
                        self._rewrite_expr(
                            comp.where,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        )
                        if comp.where is not None
                        else None,
                    ),
                    else_term=cast(
                        ast.BoolExpr | None,
                        self._rewrite_expr(
                            comp.else_term,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        )
                        if comp.else_term is not None
                        else None,
                    ),
                ),
            )
        if isinstance(expr, ast.NumAggregate):
            num_comp = expr.comp
            rewritten_num_comp: ast.NumComprehension | ast.CountComprehension
            if isinstance(num_comp, ast.NumComprehension):
                rewritten_num_comp = replace(
                    num_comp,
                    term=cast(
                        ast.NumExpr,
                        self._rewrite_expr(
                            num_comp.term,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        ),
                    ),
                    domain_set=set_subst.get(num_comp.domain_set, num_comp.domain_set),
                    where=cast(
                        ast.BoolExpr | None,
                        self._rewrite_expr(
                            num_comp.where,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        )
                        if num_comp.where is not None
                        else None,
                    ),
                    else_term=cast(
                        ast.NumExpr | None,
                        self._rewrite_expr(
                            num_comp.else_term,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        )
                        if num_comp.else_term is not None
                        else None,
                    ),
                )
            else:
                rewritten_num_comp = replace(
                    num_comp,
                    domain_set=set_subst.get(num_comp.domain_set, num_comp.domain_set),
                    where=cast(
                        ast.BoolExpr | None,
                        self._rewrite_expr(
                            num_comp.where,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        )
                        if num_comp.where is not None
                        else None,
                    ),
                    else_term=cast(
                        ast.BoolExpr | None,
                        self._rewrite_expr(
                            num_comp.else_term,
                            current_instance=current_instance,
                            value_subst=value_subst,
                            set_subst=set_subst,
                            call_stack=call_stack,
                        )
                        if num_comp.else_term is not None
                        else None,
                    ),
                )
            return replace(expr, comp=rewritten_num_comp)

        return expr

    def _inline_view_predicate_call(
        self,
        *,
        instance: _InstanceContext,
        predicate: ast.PredicateDef,
        call_args: list[ast.Expr],
        call_span: Span,
        call_stack: tuple[tuple[str, str], ...],
    ) -> ast.BoolExpr:
        rewritten = self._inline_macro_call(
            member=predicate,
            scope_key=instance.alias,
            scope_label=f"{instance.alias}.{predicate.name}",
            recursive_help="Break recursive predicate/function dependencies in unknown `view` blocks.",
            call_descriptor=f"method `{predicate.name}`",
            call_args=call_args,
            call_span=call_span,
            current_instance=instance,
            set_subst=instance.type_arg_map,
            call_stack=call_stack,
        )
        return cast(ast.BoolExpr, rewritten)

    def _inline_view_function_call(
        self,
        *,
        instance: _InstanceContext,
        function: ast.FunctionDef,
        call_args: list[ast.Expr],
        call_span: Span,
        call_stack: tuple[tuple[str, str], ...],
    ) -> ast.NumExpr:
        rewritten = self._inline_macro_call(
            member=function,
            scope_key=instance.alias,
            scope_label=f"{instance.alias}.{function.name}",
            recursive_help="Break recursive predicate/function dependencies in unknown `view` blocks.",
            call_descriptor=f"method `{function.name}`",
            call_args=call_args,
            call_span=call_span,
            current_instance=instance,
            set_subst=instance.type_arg_map,
            call_stack=call_stack,
        )
        return cast(ast.NumExpr, rewritten)

    def _inline_global_predicate_call(
        self,
        *,
        predicate: ast.PredicateDef,
        call_args: list[ast.Expr],
        call_span: Span,
        current_instance: _InstanceContext | None,
        set_subst: dict[str, str],
        call_stack: tuple[tuple[str, str], ...],
    ) -> ast.BoolExpr:
        rewritten = self._inline_macro_call(
            member=predicate,
            scope_key="__global__",
            scope_label=predicate.name,
            recursive_help="Break recursive dependencies among top-level predicates/functions.",
            call_descriptor=f"`{predicate.name}`",
            call_args=call_args,
            call_span=call_span,
            current_instance=current_instance,
            set_subst=set_subst,
            call_stack=call_stack,
        )
        return cast(ast.BoolExpr, rewritten)

    def _inline_global_function_call(
        self,
        *,
        function: ast.FunctionDef,
        call_args: list[ast.Expr],
        call_span: Span,
        current_instance: _InstanceContext | None,
        set_subst: dict[str, str],
        call_stack: tuple[tuple[str, str], ...],
    ) -> ast.NumExpr:
        rewritten = self._inline_macro_call(
            member=function,
            scope_key="__global__",
            scope_label=function.name,
            recursive_help="Break recursive dependencies among top-level predicates/functions.",
            call_descriptor=f"`{function.name}`",
            call_args=call_args,
            call_span=call_span,
            current_instance=current_instance,
            set_subst=set_subst,
            call_stack=call_stack,
        )
        return cast(ast.NumExpr, rewritten)

    def _inline_macro_call(
        self,
        *,
        member: ast.PredicateDef | ast.FunctionDef,
        scope_key: str,
        scope_label: str,
        recursive_help: str,
        call_descriptor: str,
        call_args: list[ast.Expr],
        call_span: Span,
        current_instance: _InstanceContext | None,
        set_subst: dict[str, str],
        call_stack: tuple[tuple[str, str], ...],
    ) -> ast.Expr:
        if len(call_args) != len(member.formals):
            self._diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2101",
                    message=(
                        f"{call_descriptor} expects {len(member.formals)} argument(s), "
                        f"got {len(call_args)}"
                    ),
                    span=call_span,
                )
            )
            if isinstance(member, ast.FunctionDef):
                return ast.NumLit(span=call_span, value=0.0)
            return ast.BoolLit(span=call_span, value=False)

        kind_key = "predicate" if isinstance(member, ast.PredicateDef) else "function"
        call_key = (scope_key, f"{kind_key}:{member.name}")
        if call_key in call_stack:
            message = f"recursive macro expansion detected for `{scope_label}`"
            if scope_key != "__global__" and isinstance(member, ast.PredicateDef):
                message = f"recursive view predicate expansion detected for `{scope_label}`"
            self._diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2101",
                    message=message,
                    span=call_span,
                    help=[recursive_help],
                )
            )
            if isinstance(member, ast.FunctionDef):
                return ast.NumLit(span=call_span, value=0.0)
            return ast.BoolLit(span=call_span, value=False)

        value_subst: dict[str, ast.Expr] = {}
        for formal, arg in zip(member.formals, call_args, strict=False):
            value_subst[formal.name] = arg

        body = member.expr
        rewritten = self._rewrite_expr(
            body,
            current_instance=current_instance,
            value_subst=value_subst,
            set_subst=set_subst,
            call_stack=(*call_stack, call_key),
        )
        return rewritten

    def _view_member(
        self, unknown_def: ast.UnknownDef, name: str
    ) -> ast.PredicateDef | ast.FunctionDef | None:
        for member in unknown_def.view_block:
            if member.name == name:
                return member
        return None


def elaborate_unknowns(program: ast.Program) -> UnknownElaborationResult:
    return UnknownElaborator().elaborate(program)


__all__ = ["UnknownElaborationResult", "UnknownElaborator", "elaborate_unknowns"]
