from qsol.parse import ast
from qsol.parse.parser import _parser, parse_to_ast


def test_parser_backend_is_lalr_contextual() -> None:
    parser = _parser()
    assert parser.options.parser == "lalr"
    assert parser.options.lexer == "contextual"


def test_parse_with_dense_separators_builds_ast() -> None:
    text = """


problem P {

  set A;

  find S : Subset(A);

  must true;

}


unknown U(A) {
  rep {
    m : Subset(A);

  }

  laws {
    must true;

  }

  view {
    predicate has(x in A) = m.has(x);

  }
}

"""
    program = parse_to_ast(text, filename="dense.qsol")
    assert len(program.items) == 2
    assert isinstance(program.items[0], ast.ProblemDef)
    assert isinstance(program.items[1], ast.UnknownDef)


def test_unknown_blocks_are_populated() -> None:
    text = """
unknown MappingLike(A, B) {
  rep {
    f : Mapping(A -> B);
  }
  laws {
    must forall x in A: f.has(x);
  }
  view {
    predicate has(x in A) = f.has(x);
  }
}
"""
    program = parse_to_ast(text, filename="unknown.qsol")

    assert len(program.items) == 1
    unknown = program.items[0]
    assert isinstance(unknown, ast.UnknownDef)
    assert unknown.name == "MappingLike"
    assert unknown.formals == ["A", "B"]
    assert len(unknown.rep_block) == 1
    assert len(unknown.laws_block) == 1
    assert len(unknown.view_block) == 1
