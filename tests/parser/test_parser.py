from qsol.parse import ast
from qsol.parse.parser import ParseFailure, parse_to_ast


def test_parse_valid_program() -> None:
    text = """
problem P {
  set A;
  find S : Subset(A);
  must all(S.has(x) or not S.has(x) for x in A);
  minimize sum( if S.has(x) then 1 else 0 for x in A );
}
"""
    program = parse_to_ast(text, filename="test.qsol")
    assert len(program.items) == 1


def test_parse_use_module_statements() -> None:
    text = """
use stdlib.permutation;
use mylib.graph.unknowns;

problem P {
  set A;
  find S : Subset(A);
  must true;
}
"""
    program = parse_to_ast(text, filename="use_modules.qsol")
    assert len(program.items) == 3
    assert isinstance(program.items[0], ast.UseStmt)
    assert isinstance(program.items[1], ast.UseStmt)
    assert isinstance(program.items[2], ast.ProblemDef)
    assert program.items[0].module == "stdlib.permutation"
    assert program.items[1].module == "mylib.graph.unknowns"


def test_parse_top_level_predicate_and_function_definitions() -> None:
    text = """
predicate iff(a: Bool, b: Bool): Bool = a and b or not a and not b;
function indicator(b: Bool): Real = if b then 1 else 0;

problem P {
  param Flag : Bool;
  must iff(Flag, true);
  minimize indicator(Flag);
}
"""
    program = parse_to_ast(text, filename="top_level_macros.qsol")
    assert len(program.items) == 3
    assert isinstance(program.items[0], ast.PredicateDef)
    assert isinstance(program.items[1], ast.FunctionDef)
    assert isinstance(program.items[2], ast.ProblemDef)


def test_parse_invalid_missing_separator() -> None:
    text = "problem P { set A find S : Subset(A); }"
    try:
        parse_to_ast(text, filename="bad.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
        assert exc.diagnostic.notes
        assert any("expected one of:" in note for note in exc.diagnostic.notes)
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


def test_parse_elem_param_type() -> None:
    text = """
problem P {
  set V;
  set E;
  param U[E] : Elem(V);
}
"""
    program = parse_to_ast(text, filename="elem_param.qsol")
    assert len(program.items) == 1
    assert isinstance(program.items[0], ast.ProblemDef)


def test_parse_static_subset_param_type() -> None:
    text = """
problem P {
  set V;
  param Terminals : StaticSubset(V);
}
"""
    program = parse_to_ast(text, filename="static_subset_param.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    param = problem.stmts[1]
    assert isinstance(param, ast.ParamDecl)
    assert isinstance(param.value_type, ast.StaticSubsetTypeRef)
    assert param.value_type.set_name == "V"


def test_parse_size_builtin_in_numeric_context() -> None:
    text = """
problem P {
  set V;
  find S : Subset(V);
  minimize size(V);
}
"""
    program = parse_to_ast(text, filename="size_builtin.qsol")
    assert len(program.items) == 1
    assert isinstance(program.items[0], ast.ProblemDef)


def test_parse_objective_labels() -> None:
    text = """
problem P {
  set V;
  find Pick : Subset(V);
  minimize count(v in V where not Pick.has(v)) as missing;
  maximize count(v in V where Pick.has(v)) as selected;
}
"""
    program = parse_to_ast(text, filename="objective_labels.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    objectives = [stmt for stmt in problem.stmts if isinstance(stmt, ast.Objective)]
    assert [objective.label for objective in objectives] == ["missing", "selected"]


def test_parse_structure_decl_and_dotted_graph_domains() -> None:
    text = """
use stdlib.graph;

problem P {
  set V;
  relation Edge(u: V, v: V);
  structure G = UndirectedGraph(V, Edge);
  find Selected[G.edges] : Bool;
  must forall (u, v) in G.non_edges: not (Selected[u, v] and G.adjacent(u, v));
  minimize size(G.edges) + count((u, v) in G.non_edges where G.nonedge(u, v));
}
"""
    program = parse_to_ast(text, filename="graph_structure.qsol")
    problem = program.items[1]
    assert isinstance(problem, ast.ProblemDef)
    assert isinstance(problem.stmts[2], ast.StructureDecl)
    assert problem.stmts[2].name == "G"
    assert problem.stmts[2].constructor == "UndirectedGraph"
    assert problem.stmts[3].indices == ["G.edges"]


def test_parse_bare_scalar_bool_param_in_constraint() -> None:
    text = """
problem P {
  param Flag : Bool;
  must Flag;
}
"""
    program = parse_to_ast(text, filename="bare_scalar_bool.qsol")
    assert len(program.items) == 1
    assert isinstance(program.items[0], ast.ProblemDef)


def test_parse_accepts_numeric_indexed_param_paren_style_for_sema_validation() -> None:
    text = """
problem P {
  set A;
  param Cost[A] : Real;
  find S : Subset(A);
  minimize sum(if S.has(x) then Cost(x) else 0 for x in A);
}
"""
    program = parse_to_ast(text, filename="indexed_param_paren_bad.qsol")
    assert len(program.items) == 1
    assert isinstance(program.items[0], ast.ProblemDef)


def test_parse_rejects_untyped_predicate_declaration() -> None:
    text = """
predicate old_style(x) = true;
problem P {
  must true;
}
"""
    try:
        parse_to_ast(text, filename="untyped_predicate_bad.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected parse failure")


def test_parse_rejects_legacy_in_set_formal_syntax() -> None:
    text = """
predicate has(x in A): Bool = true;
problem P {
  set A;
  must true;
}
"""
    try:
        parse_to_ast(text, filename="legacy_in_set_bad.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected parse failure")


def test_parse_comprehension_style_call_argument() -> None:
    text = """
predicate atleast(k: Real, terms: Comp(Real)): Bool = terms >= k;

problem P {
  set X;
  find S : Subset(X);
  must atleast(1, S.has(x) for x in X where true else false);
}
"""
    program = parse_to_ast(text, filename="comp_arg_call.qsol")
    problem = program.items[1]
    assert isinstance(problem, ast.ProblemDef)
    constraint = problem.stmts[2]
    assert isinstance(constraint, ast.Constraint)
    assert isinstance(constraint.expr, ast.FuncCall)
    assert isinstance(constraint.expr.args[1], ast.BoolComprehension)


def test_parse_missing_semicolon_produces_help() -> None:
    text = """
problem P {
  set A
  find S : Subset(A);
}
"""
    try:
        parse_to_ast(text, filename="missing_semicolon.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
        assert any("trailing `;`" in item for item in exc.diagnostic.help)
    else:
        raise AssertionError("expected parse failure")


def test_parse_rejects_quoted_use_paths() -> None:
    text = """
use "mylib/unknowns.qsol";

problem P {
  set A;
  find S : Subset(A);
  must true;
}
"""
    try:
        parse_to_ast(text, filename="quoted_use_bad.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected parse failure")


def test_parse_predicate_and_function_without_return_type() -> None:
    text = """
predicate iff(a: Bool, b: Bool) = a and b or not a and not b;
function indicator(b: Bool) = if b then 1 else 0;

problem P {
  param Flag : Bool;
  must iff(Flag, true);
  minimize indicator(Flag);
}
"""
    program = parse_to_ast(text, filename="optional_return_type.qsol")
    assert len(program.items) == 3


def test_parse_range_set_and_scalar_find_declarations() -> None:
    text = """
problem P {
  set V;
  set Positions = Range(1, size(V));
  find b : Bool;
  find T : Int[0 .. size(V)];
  find Load[V] : Int[0 .. size(V)];
}
"""
    program = parse_to_ast(text, filename="range_scalar_find.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    range_set = problem.stmts[1]
    assert isinstance(range_set, ast.SetDecl)
    assert isinstance(range_set.expr, ast.RangeSetExpr)
    scalar_bool = problem.stmts[2]
    assert isinstance(scalar_bool, ast.FindDecl)
    assert isinstance(scalar_bool.decision_type, ast.BoolDecisionType)
    scalar_int = problem.stmts[3]
    assert isinstance(scalar_int, ast.FindDecl)
    assert isinstance(scalar_int.decision_type, ast.IntDecisionType)
    indexed_int = problem.stmts[4]
    assert isinstance(indexed_int, ast.FindDecl)
    assert indexed_int.indices == ["V"]


def test_parse_rejects_unbounded_int_find() -> None:
    text = """
problem P {
  find x : Int;
}
"""
    try:
        parse_to_ast(text, filename="unbounded_int_find_bad.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected parse failure")


def test_parse_predicate_and_function_mixed_return_type_styles() -> None:
    text = """
predicate with_type(a: Bool): Bool = a;
predicate without_type(a: Bool) = a;
function with_type_f(x: Real): Real = x + 1;
function without_type_f(x: Real) = x + 1;

problem P {
  must true;
  minimize 0;
}
"""
    program = parse_to_ast(text, filename="mixed_return_type.qsol")
    assert len(program.items) == 5
    assert isinstance(program.items[0], ast.PredicateDef)
    assert isinstance(program.items[1], ast.PredicateDef)
    assert isinstance(program.items[2], ast.FunctionDef)
    assert isinstance(program.items[3], ast.FunctionDef)


def test_parse_view_predicate_and_function_without_return_type() -> None:
    text = """
unknown U(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view {
    predicate has(x: Elem(A)) = s.has(x);
    function score(x: Elem(A)) = if s.has(x) then 1 else 0;
  }
}

problem P {
  set A;
  find S : U(A);
  must true;
  minimize 0;
}
"""
    program = parse_to_ast(text, filename="view_optional_return_type.qsol")
    assert len(program.items) == 2
    unknown = program.items[0]
    assert isinstance(unknown, ast.UnknownDef)
    assert len(unknown.view_block) == 2
    assert isinstance(unknown.view_block[0], ast.PredicateDef)
    assert isinstance(unknown.view_block[1], ast.FunctionDef)
