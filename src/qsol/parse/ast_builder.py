from __future__ import annotations

import ast as pyast
from dataclasses import dataclass
from typing import cast

from lark import Token, Tree

from qsol.diag.source import Span
from qsol.parse import ast

ParseNode = Tree[object] | Token | str
UnknownSections = tuple[list[ast.RepDecl], list[ast.Constraint], list[ast.ViewMember]]


@dataclass(slots=True)
class ASTBuilder:
    text: str
    filename: str

    def build(self, tree: Tree[object]) -> ast.Program:
        node = self._from_tree(tree)
        if not isinstance(node, ast.Program):
            raise TypeError("Expected program AST")
        return node

    def _from_tree(self, node: ParseNode) -> object:
        if isinstance(node, Token):
            return self._from_token(node)
        if isinstance(node, str):
            return node

        data = node.data
        c: list[ParseNode] = [cast(ParseNode, child) for child in node.children]

        if data == "start":
            return self._from_tree(c[0])
        if data == "program":
            collected: list[ast.TopItem] = []
            for ch in c:
                value = self._from_tree(ch)
                if isinstance(value, list):
                    collected.extend(v for v in value if isinstance(v, ast.TopItem))
                elif isinstance(value, ast.TopItem):
                    collected.append(value)
            return ast.Program(span=self._span(node), items=collected)
        if data == "item_list":
            item_list_values = [
                x for x in (self._from_tree(ch) for ch in c) if isinstance(x, ast.TopItem)
            ]
            return item_list_values
        if data == "items":
            items_values = [
                x for x in (self._from_tree(ch) for ch in c) if isinstance(x, ast.TopItem)
            ]
            return items_values
        if data == "sep":
            return None
        if data == "item":
            return self._from_tree(c[0])

        if data == "use_stmt":
            module = cast(str, self._from_tree(c[0]))
            return ast.UseStmt(span=self._span(node), module=module)
        if data == "module_path":
            if not c:
                raise ValueError("module path is empty")
            return ".".join(self._name(ch) for ch in c)

        if data == "problem":
            name = self._name(c[0])
            problem_stmts = cast(list[ast.ProblemStmt], self._from_tree(c[1]))
            return ast.ProblemDef(span=self._span(node), name=name, stmts=problem_stmts)
        if data == "block_problem":
            block_problem_stmts: list[ast.ProblemStmt] = []
            for ch in c:
                value = self._from_tree(ch)
                if isinstance(value, list):
                    block_problem_stmts.extend(v for v in value if isinstance(v, ast.ProblemStmt))
                elif isinstance(value, ast.ProblemStmt):
                    block_problem_stmts.append(value)
            return block_problem_stmts
        if data == "problem_stmt_list":
            stmt_list_values = [
                x for x in (self._from_tree(ch) for ch in c) if isinstance(x, ast.ProblemStmt)
            ]
            return stmt_list_values
        if data == "problem_stmt":
            return self._from_tree(c[0])

        if data == "unknown_def":
            name = self._name(c[0])
            unknown_formals: list[str] = []
            block_idx = 1
            if len(c) == 3:
                unknown_formals = cast(list[str], self._from_tree(c[1]))
                block_idx = 2
            rep_block, laws_block, view_block = cast(UnknownSections, self._from_tree(c[block_idx]))
            return ast.UnknownDef(
                span=self._span(node),
                name=name,
                formals=unknown_formals,
                rep_block=rep_block,
                laws_block=laws_block,
                view_block=view_block,
            )
        if data == "block_unknown":
            rep_entries: list[ast.RepDecl] = []
            law_entries: list[ast.Constraint] = []
            view_entries: list[ast.ViewMember] = []
            for ch in c:
                value = self._from_tree(ch)
                entries = value if isinstance(value, list) else [value]
                for entry in entries:
                    if isinstance(entry, tuple) and len(entry) == 2:
                        tag, payload = entry
                        if tag == "rep":
                            rep_entries = cast(list[ast.RepDecl], payload)
                        elif tag == "laws":
                            law_entries = cast(list[ast.Constraint], payload)
                        elif tag == "view":
                            view_entries = cast(list[ast.ViewMember], payload)
            return rep_entries, law_entries, view_entries
        if data == "unknown_stmt_list":
            entries = [x for x in (self._from_tree(ch) for ch in c) if x is not None]
            return entries
        if data == "unknown_stmt":
            return self._from_tree(c[0])
        if data == "rep_block":
            return "rep", cast(list[ast.RepDecl], self._from_tree(c[0]))
        if data == "block_rep":
            rep_values: list[ast.RepDecl] = []
            for ch in c:
                value = self._from_tree(ch)
                if isinstance(value, list):
                    rep_values.extend(v for v in value if isinstance(v, ast.RepDecl))
                elif isinstance(value, ast.RepDecl):
                    rep_values.append(value)
            return rep_values
        if data == "rep_stmt_list":
            rep_stmt_values = [
                x for x in (self._from_tree(ch) for ch in c) if isinstance(x, ast.RepDecl)
            ]
            return rep_stmt_values
        if data == "rep_stmt":
            return self._from_tree(c[0])
        if data == "find_like_decl":
            return ast.RepDecl(
                span=self._span(node),
                name=self._name(c[0]),
                unknown_type=cast(ast.UnknownTypeRef, self._from_tree(c[1])),
            )
        if data == "laws_block":
            return "laws", cast(list[ast.Constraint], self._from_tree(c[0]))
        if data == "block_laws":
            law_values: list[ast.Constraint] = []
            for ch in c:
                value = self._from_tree(ch)
                if isinstance(value, list):
                    law_values.extend(v for v in value if isinstance(v, ast.Constraint))
                elif isinstance(value, ast.Constraint):
                    law_values.append(value)
            return law_values
        if data == "laws_stmt_list":
            law_stmt_values = [
                x for x in (self._from_tree(ch) for ch in c) if isinstance(x, ast.Constraint)
            ]
            return law_stmt_values
        if data == "laws_stmt":
            return self._from_tree(c[0])
        if data == "view_block":
            return "view", cast(list[ast.ViewMember], self._from_tree(c[0]))
        if data == "block_view":
            view_values: list[ast.ViewMember] = []
            for ch in c:
                value = self._from_tree(ch)
                if isinstance(value, list):
                    view_values.extend(
                        v for v in value if isinstance(v, (ast.PredicateDef, ast.FunctionDef))
                    )
                elif isinstance(value, (ast.PredicateDef, ast.FunctionDef)):
                    view_values.append(value)
            return view_values
        if data == "view_stmt_list":
            view_stmt_values = [
                x
                for x in (self._from_tree(ch) for ch in c)
                if isinstance(x, (ast.PredicateDef, ast.FunctionDef))
            ]
            return view_stmt_values
        if data == "view_stmt":
            return self._from_tree(c[0])

        if data == "formal_params":
            return [self._name(ch) for ch in c]
        if data == "formal_param":
            return self._name(c[0])

        if data == "predicate_def":
            name = self._name(c[0])
            pred_expr = cast(ast.BoolExpr, self._from_tree(c[-1]))
            predicate_formals: list[ast.PredicateFormal] = []
            if len(c) == 3:
                predicate_formals = cast(list[ast.PredicateFormal], self._from_tree(c[1]))
            return ast.PredicateDef(
                span=self._span(node), name=name, formals=predicate_formals, expr=pred_expr
            )
        if data == "function_def":
            name = self._name(c[0])
            func_expr = cast(ast.NumExpr, self._from_tree(c[-1]))
            function_formals: list[ast.PredicateFormal] = []
            if len(c) == 3:
                function_formals = cast(list[ast.PredicateFormal], self._from_tree(c[1]))
            return ast.FunctionDef(
                span=self._span(node), name=name, formals=function_formals, expr=func_expr
            )

        if data == "pred_formals":
            return [cast(ast.PredicateFormal, self._from_tree(ch)) for ch in c]
        if data == "pred_formal":
            name = self._name(c[0])
            kind, type_arg = cast(tuple[str, str | None], self._from_tree(c[1]))
            return ast.PredicateFormal(
                span=self._span(node),
                name=name,
                kind=kind,
                type_arg=type_arg,
            )
        if data == "pred_formal_type":
            text = self._slice(node).strip()
            if text in {"Bool", "Real"}:
                return text, None
            if text.startswith("Elem("):
                return "Elem", self._name(c[0])
            if text.startswith("Comp("):
                return "Comp", cast(str, self._from_tree(c[0]))
            raise TypeError(f"unknown predicate formal type `{text}`")
        if data == "pred_formal_comp_type":
            return self._slice(node).strip()

        if data == "set_decl":
            return ast.SetDecl(span=self._span(node), name=self._name(c[0]))

        if data == "param_decl":
            name = self._name(c[0])
            indices: list[str] = []
            value_type: ast.ScalarTypeRef | ast.ElemTypeRef | None = None
            default: ast.Literal | None = None
            for ch in c[1:]:
                v = self._from_tree(ch)
                if isinstance(v, list) and all(isinstance(it, str) for it in v):
                    indices = cast(list[str], v)
                elif isinstance(v, (ast.ScalarTypeRef, ast.ElemTypeRef)):
                    value_type = v
                elif isinstance(v, ast.Literal):
                    default = v
            if value_type is None:
                raise ValueError("param declaration missing value type")
            return ast.ParamDecl(
                span=self._span(node),
                name=name,
                indices=indices,
                value_type=value_type,
                default=default,
            )

        if data == "param_indexing":
            return cast(list[str], self._from_tree(c[0]))
        if data == "name_list":
            return [self._name(ch) for ch in c]
        if data == "param_default":
            value = self._from_tree(c[0])
            if isinstance(value, ast.BoolLit):
                return ast.Literal(span=value.span, value=value.value)
            if isinstance(value, ast.NumLit):
                return ast.Literal(span=value.span, value=value.value)
            if isinstance(value, ast.StringLit):
                return ast.Literal(span=value.span, value=value.value)
            if isinstance(value, ast.Literal):
                return value
            raise TypeError(f"param default must be a literal, got {type(value)}")

        if data == "find_decl":
            return ast.FindDecl(
                span=self._span(node),
                name=self._name(c[0]),
                unknown_type=cast(ast.UnknownTypeRef, self._from_tree(c[1])),
            )

        if data == "unknown_type":
            return self._from_tree(c[0])
        if data == "subset_type":
            return ast.UnknownTypeRef(
                span=self._span(node), kind="Subset", args=(self._name(c[0]),)
            )
        if data == "mapping_type":
            return ast.UnknownTypeRef(
                span=self._span(node), kind="Mapping", args=(self._name(c[0]), self._name(c[1]))
            )
        if data == "user_unknown_type":
            user_type_args: list[str] = []
            if len(c) == 2:
                user_type_args = cast(list[str], self._from_tree(c[1]))
            return ast.UnknownTypeRef(
                span=self._span(node), kind=self._name(c[0]), args=tuple(user_type_args)
            )

        if data == "param_value_type":
            return self._from_tree(c[0])

        if data == "scalar_type":
            if c:
                return cast(ast.ScalarTypeRef, self._from_tree(c[0]))
            text = self._slice(node).strip()
            kind = "Bool" if text == "Bool" else "Real"
            return ast.ScalarTypeRef(span=self._span(node), kind=kind)

        if data == "elem_type":
            return ast.ElemTypeRef(span=self._span(node), set_name=self._name(c[0]))

        if data == "int_type":
            lo = int(cast(float, self._from_tree(c[0])))
            hi = int(cast(float, self._from_tree(c[1])))
            return ast.ScalarTypeRef(span=self._span(node), kind="Int", lo=lo, hi=hi)

        if data == "signed_int":
            return float(cast(Token, c[0]).value)

        if data == "constraint_stmt":
            kind_txt = cast(str, self._from_tree(c[0]))
            guard = cast(ast.BoolExpr | None, self._from_tree(c[2])) if len(c) == 3 else None
            return ast.Constraint(
                span=self._span(node),
                kind=ast.ConstraintKind(kind_txt),
                expr=cast(ast.BoolExpr, self._from_tree(c[1])),
                guard=guard,
            )
        if data == "hardness":
            return self._slice(node).strip()
        if data == "guard":
            return cast(ast.BoolExpr, self._from_tree(c[0]))

        if data == "objective_stmt":
            prefix = self._slice(node).lstrip()
            kind = (
                ast.ObjectiveKind.MAXIMIZE
                if prefix.startswith("maximize")
                else ast.ObjectiveKind.MINIMIZE
            )
            return ast.Objective(
                span=self._span(node), kind=kind, expr=cast(ast.NumExpr, self._from_tree(c[0]))
            )

        if data == "quantifier":
            head = self._slice(node).lstrip()
            kind = "forall" if head.startswith("forall") else "exists"
            return ast.Quantifier(
                span=self._span(node),
                kind=kind,
                var=self._name(c[0]),
                domain_set=self._name(c[1]),
                expr=cast(ast.BoolExpr, self._from_tree(c[2])),
            )

        if data == "num_aggregate":
            return self._from_tree(c[0])
        if data == "bool_aggregate":
            return self._from_tree(c[0])
        if data == "sum_agg":
            return ast.NumAggregate(
                span=self._span(node),
                kind="sum",
                comp=cast(ast.NumComprehension, self._from_tree(c[0])),
            )
        if data == "count_agg":
            return ast.NumAggregate(
                span=self._span(node),
                kind="count",
                comp=cast(ast.CountComprehension, self._from_tree(c[0])),
            )
        if data == "any_agg":
            return ast.BoolAggregate(
                span=self._span(node),
                kind="any",
                comp=cast(ast.BoolComprehension, self._from_tree(c[0])),
            )
        if data == "all_agg":
            return ast.BoolAggregate(
                span=self._span(node),
                kind="all",
                comp=cast(ast.BoolComprehension, self._from_tree(c[0])),
            )

        if data == "comp_num":
            num_term = cast(ast.NumExpr, self._from_tree(c[0]))
            num_var = self._name(c[1])
            num_domain = self._name(c[2])
            num_where: ast.BoolExpr | None = None
            num_else_term: ast.NumExpr | None = None
            if len(c) == 4:
                num_where, num_else_term = cast(
                    tuple[ast.BoolExpr | None, ast.NumExpr | None], self._from_tree(c[3])
                )
            return ast.NumComprehension(
                span=self._span(node),
                term=num_term,
                var=num_var,
                domain_set=num_domain,
                where=num_where,
                else_term=num_else_term,
            )

        if data == "comp_bool":
            bool_term = cast(ast.BoolExpr, self._from_tree(c[0]))
            bool_var = self._name(c[1])
            bool_domain = self._name(c[2])
            bool_where: ast.BoolExpr | None = None
            bool_else_term: ast.BoolExpr | None = None
            if len(c) == 4:
                bool_where, bool_else_term = cast(
                    tuple[ast.BoolExpr | None, ast.BoolExpr | None], self._from_tree(c[3])
                )
            return ast.BoolComprehension(
                span=self._span(node),
                term=bool_term,
                var=bool_var,
                domain_set=bool_domain,
                where=bool_where,
                else_term=bool_else_term,
            )
        if data == "comp_arg_num":
            num_term = cast(ast.NumExpr, self._from_tree(c[0]))
            num_var = self._name(c[1])
            num_domain = self._name(c[2])
            arg_num_where: ast.BoolExpr | None = None
            arg_num_else_term: ast.NumExpr | None = None
            if len(c) == 4:
                arg_num_where, arg_num_else_term = cast(
                    tuple[ast.BoolExpr | None, ast.NumExpr | None], self._from_tree(c[3])
                )
            return ast.NumAggregate(
                span=self._span(node),
                kind="sum",
                comp=ast.NumComprehension(
                    span=self._span(node),
                    term=num_term,
                    var=num_var,
                    domain_set=num_domain,
                    where=arg_num_where,
                    else_term=arg_num_else_term,
                ),
                from_comp_arg=True,
            )
        if data == "comp_arg_bool":
            bool_term = cast(ast.BoolExpr, self._from_tree(c[0]))
            bool_var = self._name(c[1])
            bool_domain = self._name(c[2])
            arg_bool_where: ast.BoolExpr | None = None
            arg_bool_else_term: ast.BoolExpr | None = None
            if len(c) == 4:
                arg_bool_where, arg_bool_else_term = cast(
                    tuple[ast.BoolExpr | None, ast.BoolExpr | None], self._from_tree(c[3])
                )
            return ast.BoolAggregate(
                span=self._span(node),
                kind="any",
                comp=ast.BoolComprehension(
                    span=self._span(node),
                    term=bool_term,
                    var=bool_var,
                    domain_set=bool_domain,
                    where=arg_bool_where,
                    else_term=arg_bool_else_term,
                ),
                from_comp_arg=True,
            )

        if data == "comp_count":
            var_ref = self._name(c[0])
            count_var = var_ref
            count_domain = ""
            count_tail_idx: int | None = None

            if len(c) == 2:
                count_domain = self._name(c[1])
            elif len(c) == 3 and isinstance(c[2], Tree):
                count_domain = self._name(c[1])
                count_tail_idx = 2
            elif len(c) == 3:
                count_var = self._name(c[1])
                count_domain = self._name(c[2])
            elif len(c) == 4:
                count_var = self._name(c[1])
                count_domain = self._name(c[2])
                count_tail_idx = 3
            else:
                raise TypeError("invalid count comprehension shape")

            count_where: ast.BoolExpr | None = None
            count_else_term: ast.BoolExpr | None = None
            if count_tail_idx is not None:
                count_where, count_else_term = cast(
                    tuple[ast.BoolExpr | None, ast.BoolExpr | None],
                    self._from_tree(c[count_tail_idx]),
                )
            return ast.CountComprehension(
                span=self._span(node),
                var_ref=var_ref,
                var=count_var,
                domain_set=count_domain,
                where=count_where,
                else_term=count_else_term,
            )

        if data == "comp_tail_num":
            tail_num_where: ast.BoolExpr | None = None
            tail_num_else: ast.NumExpr | None = None
            for ch in c:
                if isinstance(ch, Tree) and ch.data == "where_clause":
                    tail_num_where = cast(ast.BoolExpr, self._from_tree(ch))
                elif isinstance(ch, Tree) and ch.data == "else_clause_num":
                    tail_num_else = cast(ast.NumExpr, self._from_tree(ch))
            return tail_num_where, tail_num_else

        if data == "comp_tail_bool":
            tail_bool_where: ast.BoolExpr | None = None
            tail_bool_else: ast.BoolExpr | None = None
            for ch in c:
                if isinstance(ch, Tree) and ch.data == "where_clause":
                    tail_bool_where = cast(ast.BoolExpr, self._from_tree(ch))
                elif isinstance(ch, Tree) and ch.data == "else_clause_bool":
                    tail_bool_else = cast(ast.BoolExpr, self._from_tree(ch))
            return tail_bool_where, tail_bool_else

        if data == "where_clause":
            return cast(ast.BoolExpr, self._from_tree(c[0]))
        if data == "else_clause_num":
            return cast(ast.NumExpr, self._from_tree(c[0]))
        if data == "else_clause_bool":
            return cast(ast.BoolExpr, self._from_tree(c[0]))

        if data == "implies":
            return ast.Implies(
                span=self._span(node),
                left=cast(ast.BoolExpr, self._from_tree(c[0])),
                right=cast(ast.BoolExpr, self._from_tree(c[1])),
            )
        if data == "or_op":
            return ast.Or(
                span=self._span(node),
                left=cast(ast.BoolExpr, self._from_tree(c[0])),
                right=cast(ast.BoolExpr, self._from_tree(c[1])),
            )
        if data == "and_op":
            return ast.And(
                span=self._span(node),
                left=cast(ast.BoolExpr, self._from_tree(c[0])),
                right=cast(ast.BoolExpr, self._from_tree(c[1])),
            )
        if data == "not_op":
            return ast.Not(span=self._span(node), expr=cast(ast.BoolExpr, self._from_tree(c[0])))

        if data == "comparison":
            left = cast(ast.Expr, self._from_tree(c[0]))
            op = cast(str, self._from_tree(c[1]))
            right = cast(ast.Expr, self._from_tree(c[2]))
            return ast.Compare(span=self._span(node), op=op, left=left, right=right)
        if data in {"comp_op", "eq_op"}:
            return self._slice(node).strip()

        if data == "paren_call":
            func_args: list[ast.Expr] = []
            if len(c) == 2:
                func_args = cast(list[ast.Expr], self._from_tree(c[1]))
            return ast.FuncCall(
                span=self._span(node), name=self._name(c[0]), args=func_args, call_style="paren"
            )

        if data == "indexed_call":
            indexed_args: list[ast.Expr] = []
            if len(c) == 2:
                indexed_args = cast(list[ast.Expr], self._from_tree(c[1]))
            return ast.FuncCall(
                span=self._span(node),
                name=self._name(c[0]),
                args=indexed_args,
                call_style="bracket",
            )

        if data == "size_call":
            size_args: list[ast.Expr] = []
            if len(c) == 1:
                size_args = cast(list[ast.Expr], self._from_tree(c[0]))
            return ast.FuncCall(
                span=self._span(node), name="size", args=size_args, call_style="paren"
            )

        if data == "method_call":
            method_args: list[ast.Expr] = []
            if len(c) == 3:
                method_args = cast(list[ast.Expr], self._from_tree(c[2]))
            return ast.MethodCall(
                span=self._span(node),
                target=cast(ast.Expr, self._from_tree(c[0])),
                name=self._name(c[1]),
                args=method_args,
            )

        if data == "add":
            return ast.Add(
                span=self._span(node),
                left=cast(ast.NumExpr, self._from_tree(c[0])),
                right=cast(ast.NumExpr, self._from_tree(c[1])),
            )
        if data == "sub":
            return ast.Sub(
                span=self._span(node),
                left=cast(ast.NumExpr, self._from_tree(c[0])),
                right=cast(ast.NumExpr, self._from_tree(c[1])),
            )
        if data == "mul":
            return ast.Mul(
                span=self._span(node),
                left=cast(ast.NumExpr, self._from_tree(c[0])),
                right=cast(ast.NumExpr, self._from_tree(c[1])),
            )
        if data == "div":
            return ast.Div(
                span=self._span(node),
                left=cast(ast.NumExpr, self._from_tree(c[0])),
                right=cast(ast.NumExpr, self._from_tree(c[1])),
            )
        if data == "neg":
            return ast.Neg(span=self._span(node), expr=cast(ast.NumExpr, self._from_tree(c[0])))

        if data == "if_expr":
            return ast.IfThenElse(
                span=self._span(node),
                cond=cast(ast.BoolExpr, self._from_tree(c[0])),
                then_expr=cast(ast.NumExpr, self._from_tree(c[1])),
                else_expr=cast(ast.NumExpr, self._from_tree(c[2])),
            )

        if data == "bool_if_expr":
            return ast.BoolIfThenElse(
                span=self._span(node),
                cond=cast(ast.BoolExpr, self._from_tree(c[0])),
                then_expr=cast(ast.BoolExpr, self._from_tree(c[1])),
                else_expr=cast(ast.BoolExpr, self._from_tree(c[2])),
            )

        if data == "call_arg":
            return cast(ast.Expr, self._from_tree(c[0]))
        if data == "arg_list":
            return [cast(ast.Expr, self._from_tree(ch)) for ch in c]

        if data == "literal":
            return cast(ast.Expr, self._from_tree(c[0]))

        if len(c) == 1:
            return self._from_tree(c[0])

        raise NotImplementedError(f"Unhandled tree node: {data}")

    def _from_token(self, token: Token) -> object:
        span = self._span(token)
        if token.type == "NAME":
            return ast.NameRef(span=span, name=str(token.value))
        if token.type == "BOOL":
            return ast.BoolLit(span=span, value=str(token.value) == "true")
        if token.type == "NUMBER":
            return ast.NumLit(span=span, value=float(str(token.value)))
        if token.type == "STRING":
            value = pyast.literal_eval(str(token.value))
            if not isinstance(value, str):
                raise TypeError("string token did not decode to str")
            return ast.StringLit(span=span, value=value)
        if token.type == "SIGNED_NUMBER":
            return float(str(token.value))
        return token

    def _span(self, node: Tree[object] | Token) -> Span:
        def _ival(value: int | None, default: int = 0) -> int:
            return default if value is None else value

        if isinstance(node, Tree):
            meta = node.meta
            return Span(
                start_offset=_ival(meta.start_pos),
                end_offset=_ival(meta.end_pos),
                line=_ival(meta.line, default=1),
                col=_ival(meta.column, default=1),
                end_line=_ival(meta.end_line, default=1),
                end_col=_ival(meta.end_column, default=1),
                filename=self.filename,
            )
        return Span(
            start_offset=_ival(node.start_pos),
            end_offset=_ival(node.end_pos),
            line=_ival(node.line, default=1),
            col=_ival(node.column, default=1),
            end_line=_ival(node.end_line, default=1),
            end_col=_ival(node.end_column, default=1),
            filename=self.filename,
        )

    def _slice(self, node: Tree[object] | Token) -> str:
        def _ival(value: int | None, default: int = 0) -> int:
            return default if value is None else value

        if isinstance(node, Tree):
            start = _ival(node.meta.start_pos)
            end = _ival(node.meta.end_pos)
            return self.text[start:end]
        return self.text[_ival(node.start_pos) : _ival(node.end_pos)]

    def _name(self, node: ParseNode) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, Token):
            return str(node.value)
        value = self._from_tree(node)
        if isinstance(value, ast.NameRef):
            return value.name
        if isinstance(value, str):
            return value
        raise TypeError(f"Expected name token, got {type(value)}")
