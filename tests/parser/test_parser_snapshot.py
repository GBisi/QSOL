"""Baseline snapshot tests: lock current parser behavior before vNext feature work.

These tests must pass on every PR.  Any regression here means a backward-incompatible
language change has occurred.
"""

from qsol.parse import ast
from qsol.parse.parser import ParseFailure, parse_to_ast

# ---------------------------------------------------------------------------
# Set declarations
# ---------------------------------------------------------------------------


def test_snapshot_range_set_parses() -> None:
    """Range(lo, hi) derived set declaration must parse."""
    text = """
problem P {
  set V;
  set Positions = Range(1, size(V));
}
"""
    program = parse_to_ast(text, filename="snap_range.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    set_pos = problem.stmts[1]
    assert isinstance(set_pos, ast.SetDecl)
    assert isinstance(set_pos.expr, ast.RangeSetExpr)


def test_snapshot_bare_set_parses() -> None:
    """Plain `set A;` without initializer must parse."""
    text = """
problem P {
  set A;
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_set.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    assert isinstance(problem.stmts[0], ast.SetDecl)
    assert problem.stmts[0].expr is None


# ---------------------------------------------------------------------------
# Find declarations
# ---------------------------------------------------------------------------


def test_snapshot_scalar_bool_find_parses() -> None:
    """Scalar `find b : Bool` must parse to BoolDecisionType."""
    text = """
problem P {
  find b : Bool;
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_bool_find.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    find = problem.stmts[0]
    assert isinstance(find, ast.FindDecl)
    assert isinstance(find.decision_type, ast.BoolDecisionType)
    assert find.indices == []


def test_snapshot_bounded_int_find_parses() -> None:
    """Scalar `find T : Int[0 .. 10]` must parse to IntDecisionType."""
    text = """
problem P {
  find T : Int[0 .. 10];
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_int_find.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    find = problem.stmts[0]
    assert isinstance(find, ast.FindDecl)
    assert isinstance(find.decision_type, ast.IntDecisionType)
    assert find.indices == []


def test_snapshot_indexed_bool_find_parses() -> None:
    """Indexed `find X[A] : Bool` must parse with correct index list."""
    text = """
problem P {
  set A;
  find X[A] : Bool;
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_indexed_bool.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    find = problem.stmts[1]
    assert isinstance(find, ast.FindDecl)
    assert isinstance(find.decision_type, ast.BoolDecisionType)
    assert find.indices == ["A"]


def test_snapshot_indexed_int_find_parses() -> None:
    """Indexed `find Load[Positions] : Int[0 .. 5]` must parse."""
    text = """
problem P {
  set V;
  set Positions = Range(1, size(V));
  find Load[Positions] : Int[0 .. 5];
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_indexed_int.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    find = problem.stmts[2]
    assert isinstance(find, ast.FindDecl)
    assert isinstance(find.decision_type, ast.IntDecisionType)
    assert find.indices == ["Positions"]


def test_snapshot_subset_find_parses() -> None:
    """find S : Subset(A) must parse to UnknownDecisionType."""
    text = """
problem P {
  set A;
  find S : Subset(A);
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_subset.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    find = problem.stmts[1]
    assert isinstance(find, ast.FindDecl)
    assert isinstance(find.decision_type, ast.UnknownDecisionType)
    assert find.decision_type.unknown_type.kind == "Subset"
    assert find.decision_type.unknown_type.args == ("A",)


def test_snapshot_mapping_find_parses() -> None:
    """find M : Mapping(A -> B) must parse."""
    text = """
problem P {
  set A;
  set B;
  find M : Mapping(A -> B);
  must true;
}
"""
    program = parse_to_ast(text, filename="snap_mapping.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    find = problem.stmts[2]
    assert isinstance(find, ast.FindDecl)
    assert isinstance(find.decision_type, ast.UnknownDecisionType)
    assert find.decision_type.unknown_type.kind == "Mapping"
    assert find.decision_type.unknown_type.args == ("A", "B")


# ---------------------------------------------------------------------------
# Aggregates and comprehensions (single-generator, current behavior)
# ---------------------------------------------------------------------------


def test_snapshot_single_gen_sum_parses() -> None:
    """sum(term for x in X) must parse."""
    text = """
problem P {
  set X;
  param Cost[X] : Real = 1;
  find S : Subset(X);
  minimize sum(if S.has(x) then Cost[x] else 0 for x in X);
}
"""
    program = parse_to_ast(text, filename="snap_single_sum.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    obj = problem.stmts[3]
    assert isinstance(obj, ast.Objective)
    agg = obj.expr
    assert isinstance(agg, ast.NumAggregate)
    assert agg.kind == "sum"
    assert isinstance(agg.comp, ast.NumComprehension)


def test_snapshot_single_gen_any_parses() -> None:
    """any(term for x in X) must parse."""
    text = """
problem P {
  set X;
  find S : Subset(X);
  must any(S.has(x) for x in X);
}
"""
    program = parse_to_ast(text, filename="snap_any.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    c = problem.stmts[2]
    assert isinstance(c, ast.Constraint)
    agg = c.expr
    assert isinstance(agg, ast.BoolAggregate)
    assert agg.kind == "any"
    assert isinstance(agg.comp, ast.BoolComprehension)


def test_snapshot_single_gen_all_parses() -> None:
    """all(term for x in X) must parse."""
    text = """
problem P {
  set X;
  find S : Subset(X);
  must all(S.has(x) for x in X);
}
"""
    program = parse_to_ast(text, filename="snap_all.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    c = problem.stmts[2]
    assert isinstance(c, ast.Constraint)
    agg = c.expr
    assert isinstance(agg, ast.BoolAggregate)
    assert agg.kind == "all"


def test_snapshot_single_gen_count_parses() -> None:
    """count(x for x in X where cond) must parse."""
    text = """
problem P {
  set X;
  find S : Subset(X);
  minimize count(x for x in X where S.has(x));
}
"""
    program = parse_to_ast(text, filename="snap_count.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    obj = problem.stmts[2]
    assert isinstance(obj, ast.Objective)
    agg = obj.expr
    assert isinstance(agg, ast.NumAggregate)
    assert agg.kind == "count"
    assert isinstance(agg.comp, ast.CountComprehension)


def test_snapshot_sum_with_where_and_else_parses() -> None:
    """sum(term for x in X where cond else alt) must parse."""
    text = """
problem P {
  set X;
  param W[X] : Real = 1;
  find S : Subset(X);
  minimize sum(W[x] for x in X where S.has(x) else 0);
}
"""
    program = parse_to_ast(text, filename="snap_sum_where_else.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    obj = problem.stmts[3]
    assert isinstance(obj, ast.Objective)
    agg = obj.expr
    assert isinstance(agg, ast.NumAggregate)
    comp = agg.comp
    assert isinstance(comp, ast.NumComprehension)
    assert comp.where is not None
    assert comp.else_term is not None


def test_snapshot_nested_single_gen_sum_parses() -> None:
    """sum(sum(Cost[a,b] for b in B) for a in A) must parse."""
    text = """
problem P {
  set A;
  set B;
  param Cost[A, B] : Real = 1;
  minimize sum(sum(Cost[a, b] for b in B) for a in A);
}
"""
    program = parse_to_ast(text, filename="snap_nested_sum.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    obj = problem.stmts[3]
    assert isinstance(obj, ast.Objective)
    outer = obj.expr
    assert isinstance(outer, ast.NumAggregate)
    assert outer.kind == "sum"
    # inner term is also a NumAggregate
    inner = outer.comp.term
    assert isinstance(inner, ast.NumAggregate)
    assert inner.kind == "sum"


def test_snapshot_comp_bool_arg_parses() -> None:
    """Comp(Bool) comprehension argument must parse."""
    text = """
predicate atleast(k: Real, terms: Comp(Bool)): Bool = terms >= k;

problem P {
  set X;
  find S : Subset(X);
  must atleast(1, S.has(x) for x in X where true else false);
}
"""
    program = parse_to_ast(text, filename="snap_comp_bool_arg.qsol")
    problem = program.items[1]
    assert isinstance(problem, ast.ProblemDef)
    c = problem.stmts[2]
    assert isinstance(c, ast.Constraint)
    assert isinstance(c.expr, ast.FuncCall)
    assert isinstance(c.expr.args[1], ast.BoolComprehension)


def test_snapshot_comp_real_arg_parses() -> None:
    """Comp(Real) comprehension argument must parse.

    The ast_builder wraps comp_arg_num in NumAggregate(from_comp_arg=True) — the
    inner NumComprehension is in .comp.
    """
    text = """
function mysum(terms: Comp(Real)): Real = terms;

problem P {
  set X;
  param W[X] : Real = 1;
  find S : Subset(X);
  minimize mysum(W[x] for x in X);
}
"""
    program = parse_to_ast(text, filename="snap_comp_real_arg.qsol")
    problem = program.items[1]
    assert isinstance(problem, ast.ProblemDef)
    obj = problem.stmts[3]
    assert isinstance(obj, ast.Objective)
    assert isinstance(obj.expr, ast.FuncCall)
    # comp_arg_num produces NumAggregate(from_comp_arg=True, .comp is NumComprehension)
    arg = obj.expr.args[0]
    assert isinstance(arg, ast.NumAggregate)
    assert arg.from_comp_arg is True
    assert isinstance(arg.comp, ast.NumComprehension)


def test_snapshot_piecewise_builtin_calls_parse() -> None:
    """Compiler-owned piecewise builtins must parse as ordinary numeric calls."""
    text = """
problem P {
  set Machines;
  find Balance : Int[-10 .. 10];
  find Load[Machines] : Int[0 .. 10];
  must abs(Balance) <= 3;
  minimize max(Load[m] for m in Machines);
}
"""
    program = parse_to_ast(text, filename="snap_piecewise.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    constraint = problem.stmts[3]
    assert isinstance(constraint, ast.Constraint)
    assert isinstance(constraint.expr, ast.Compare)
    assert isinstance(constraint.expr.left, ast.FuncCall)
    assert constraint.expr.left.name == "abs"

    objective = problem.stmts[4]
    assert isinstance(objective, ast.Objective)
    assert isinstance(objective.expr, ast.FuncCall)
    assert objective.expr.name == "max"
    assert isinstance(objective.expr.args[0], ast.NumAggregate)
    assert objective.expr.args[0].from_comp_arg is True


# ---------------------------------------------------------------------------
# Parse errors that must remain errors
# ---------------------------------------------------------------------------


def test_snapshot_rejects_unbounded_int_find() -> None:
    """`find x : Int;` (no bounds) must still be a parse error."""
    text = """
problem P {
  find x : Int;
}
"""
    try:
        parse_to_ast(text, filename="snap_bad_int.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected ParseFailure")


def test_snapshot_rejects_missing_separator() -> None:
    """Missing semicolons remain a parse error."""
    text = "problem P { set A find S : Subset(A); }"
    try:
        parse_to_ast(text, filename="snap_bad_sep.qsol")
    except ParseFailure as exc:
        assert exc.diagnostic.code == "QSOL1001"
    else:
        raise AssertionError("expected ParseFailure")
