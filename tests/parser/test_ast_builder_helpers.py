from __future__ import annotations

from typing import cast

import pytest
from lark import Token, Tree

from qsol.parse import ast
from qsol.parse.ast_builder import ASTBuilder
from qsol.parse.parser import parse_program


def _with_meta(node: Tree) -> Tree:
    node.meta.start_pos = 0
    node.meta.end_pos = 1
    node.meta.line = 1
    node.meta.column = 1
    node.meta.end_line = 1
    node.meta.end_column = 2
    return node


def test_ast_builder_token_and_name_helpers() -> None:
    builder = ASTBuilder(text="problem P { set A; }", filename="f.qsol")

    name_node = builder._from_token(Token("NAME", "X"))
    bool_node = builder._from_token(Token("BOOL", "true"))
    num_node = builder._from_token(Token("NUMBER", "2"))
    str_node = builder._from_token(Token("STRING", '"x"'))
    signed = builder._from_token(Token("SIGNED_NUMBER", "-3"))

    assert isinstance(name_node, ast.NameRef)
    assert isinstance(bool_node, ast.BoolLit)
    assert isinstance(num_node, ast.NumLit)
    assert isinstance(str_node, ast.StringLit)
    assert signed == -3.0
    assert builder._name(Token("NAME", "alpha")) == "alpha"
    assert builder._name("beta") == "beta"


def test_ast_builder_slice_span_and_error_paths() -> None:
    text = "problem P { set A; param n : Int[0 .. 3] = 1; }"
    tree = parse_program(text, filename="typed.qsol")
    builder = ASTBuilder(text=text, filename="typed.qsol")
    program = builder.build(tree)
    assert isinstance(program, ast.Program)

    # Exercise tree-based slice path.
    snippet = builder._slice(tree)
    assert snippet.startswith("problem")

    # Exercise one-child passthrough and name-from-tree path.
    literal_tree = Tree("literal", [Token("NUMBER", "3")])
    literal = builder._from_tree(literal_tree)
    assert isinstance(literal, ast.NumLit)
    assert builder._name(Tree("literal", [Token("NAME", "k")])) == "k"

    # Explicitly exercise literal validation failure path.
    bad_default = Tree("param_default", [Token("NAME", "not_literal")])
    try:
        builder._from_tree(bad_default)
    except TypeError as exc:
        assert "literal" in str(exc)
    else:
        raise AssertionError("expected literal conversion failure")


def test_ast_builder_dispatch_branches() -> None:
    builder = ASTBuilder(text="Bool", filename="matrix.qsol")

    with pytest.raises(TypeError):
        builder.build(Tree("literal", [Token("NUMBER", "1")]))

    assert builder._from_tree(Tree("start", [Token("NAME", "x")])) is not None
    assert builder._from_tree(Tree("sep", [])) is None
    assert builder._from_tree(Tree("item", [Token("NAME", "x")])) is not None
    use_stmt = _with_meta(
        Tree(
            "use_stmt",
            [Tree("module_path", [Token("NAME", "stdlib"), Token("NAME", "permutation")])],
        )
    )
    use_node = builder._from_tree(use_stmt)
    assert isinstance(use_node, ast.UseStmt)
    assert use_node.module == "stdlib.permutation"
    assert builder._from_tree(
        Tree("param_indexing", [Tree("name_list", [Token("NAME", "A")])])
    ) == ["A"]
    subset_type = _with_meta(Tree("subset_type", [Token("NAME", "A")]))
    find_decl = _with_meta(Tree("find_decl", [Token("NAME", "S"), subset_type]))
    assert isinstance(builder._from_tree(find_decl), ast.FindDecl)
    mapping_type = _with_meta(Tree("mapping_type", [Token("NAME", "A"), Token("NAME", "B")]))
    unknown_type = _with_meta(Tree("unknown_type", [mapping_type]))
    assert isinstance(
        builder._from_tree(unknown_type),
        ast.UnknownTypeRef,
    )
    assert isinstance(builder._from_tree(_with_meta(Tree("scalar_type", []))), ast.ScalarTypeRef)
    assert isinstance(
        builder._from_tree(_with_meta(Tree("elem_type", [Token("NAME", "A")]))),
        ast.ElemTypeRef,
    )
    assert builder._from_tree(Tree("signed_int", [Token("SIGNED_NUMBER", "-2")])) == -2.0
    assert isinstance(builder._from_tree(_with_meta(Tree("hardness", []))), str)

    comp_tail_num = builder._from_tree(
        Tree(
            "comp_tail_num",
            [
                Tree("where_clause", [Token("BOOL", "true")]),
                Tree("else_clause_num", [Token("NUMBER", "0")]),
            ],
        )
    )
    assert isinstance(comp_tail_num, tuple)

    comp_tail_bool = builder._from_tree(
        Tree(
            "comp_tail_bool",
            [
                Tree("where_clause", [Token("BOOL", "true")]),
                Tree("else_clause_bool", [Token("BOOL", "false")]),
            ],
        )
    )
    assert isinstance(comp_tail_bool, tuple)

    count_comp_explicit = cast(
        ast.CountComprehension,
        builder._from_tree(
            _with_meta(
                Tree(
                    "comp_count",
                    [Token("NAME", "x"), Token("NAME", "y"), Token("NAME", "A")],
                )
            )
        ),
    )
    assert count_comp_explicit.var_ref == "x"
    assert count_comp_explicit.var == "y"
    assert count_comp_explicit.domain_set == "A"

    count_comp_shorthand = cast(
        ast.CountComprehension,
        builder._from_tree(
            _with_meta(
                Tree(
                    "comp_count",
                    [
                        Token("NAME", "x"),
                        Token("NAME", "A"),
                        Tree("comp_tail_bool", [Tree("where_clause", [Token("BOOL", "true")])]),
                    ],
                )
            )
        ),
    )
    assert count_comp_shorthand.var_ref == "x"
    assert count_comp_shorthand.var == "x"
    assert count_comp_shorthand.domain_set == "A"
    assert isinstance(count_comp_shorthand.where, ast.BoolLit)

    assert isinstance(
        builder._from_tree(
            _with_meta(Tree("implies", [Token("BOOL", "true"), Token("BOOL", "false")]))
        ),
        ast.Implies,
    )
    assert isinstance(
        builder._from_tree(
            _with_meta(Tree("or_op", [Token("BOOL", "true"), Token("BOOL", "false")]))
        ),
        ast.Or,
    )
    assert isinstance(
        builder._from_tree(
            _with_meta(Tree("and_op", [Token("BOOL", "true"), Token("BOOL", "false")]))
        ),
        ast.And,
    )
    assert isinstance(
        builder._from_tree(_with_meta(Tree("not_op", [Token("BOOL", "true")]))), ast.Not
    )

    assert isinstance(
        builder._from_tree(_with_meta(Tree("add", [Token("NUMBER", "1"), Token("NUMBER", "2")]))),
        ast.Add,
    )
    assert isinstance(
        builder._from_tree(_with_meta(Tree("sub", [Token("NUMBER", "1"), Token("NUMBER", "2")]))),
        ast.Sub,
    )
    assert isinstance(
        builder._from_tree(_with_meta(Tree("mul", [Token("NUMBER", "1"), Token("NUMBER", "2")]))),
        ast.Mul,
    )
    assert isinstance(
        builder._from_tree(Tree("arg_list", [Token("NUMBER", "1"), Token("BOOL", "false")])),
        list,
    )

    assert isinstance(builder._name(_with_meta(Tree("hardness", []))), str)
    with pytest.raises(TypeError):
        builder._name(Tree("literal", [Token("NUMBER", "1")]))
