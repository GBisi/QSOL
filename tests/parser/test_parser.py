from qsol.parse import ast
from qsol.parse.parser import ParseFailure, parse_to_ast


def test_parse_valid_program() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must forall x in A: S.has(x) or not S.has(x);
  minimize sum( if S.has(x) then 1 else 0 for x in A );
}
"""
    program = parse_to_ast(text, filename="test.qsol")
    assert len(program.items) == 1


def test_parse_invalid_missing_separator() -> None:
    text = "problem P { set A find S : Subset(A); }"
    try:
        parse_to_ast(text, filename="bad.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected parse failure")


def test_parse_with_extra_separators() -> None:
    text = """

problem P {

  set A;

  find S : Subset(A);
  must true;

}

"""
    program = parse_to_ast(text, filename="seps.qsol")
    assert len(program.items) == 1
    assert isinstance(program.items[0], ast.ProblemDef)


def test_parse_multiline_indented_if_expression() -> None:
    text = """
problem BoundedMaxCut {
  set V;
  param LinkWeight[V,V] : Real = 1;

  find Left : Subset(V);

  must sum(if Left.has(v) then 1 else 0 for v in V) <= 3;

  should any(Left.has(v) for v in V);
  should any(not Left.has(v) for v in V);

  maximize sum(sum(if Left.has(u) then
                      if Left.has(v) then 0
                      else LinkWeight[u, v]
                  else if Left.has(v) then LinkWeight[u, v]
                  else 0
                for v in V) for u in V) / 2;
}
"""
    program = parse_to_ast(text, filename="bounded_max_cut.qsol")
    assert len(program.items) == 1
    assert isinstance(program.items[0], ast.ProblemDef)
