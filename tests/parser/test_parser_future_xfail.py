"""xfail probes for vNext syntax not yet in the grammar.

Each test here is expected to FAIL on the current grammar/sema.
When a feature is implemented the corresponding test must be updated:
  - Remove the xfail mark.
  - Assert the CORRECT shape, not merely that it parses.

These tests document intent and drive implementation — they are not allowed
to be silently passing or silently deleted.
"""

from qsol.parse import ast
from qsol.parse.parser import parse_to_ast

# ---------------------------------------------------------------------------
# Multi-generator comprehensions (Milestone 1)
# ---------------------------------------------------------------------------


def test_two_gen_sum_parses_with_binder_list() -> None:
    """sum(Cost[u,v] for u in U for v in V) parses with two binders."""
    text = """
problem P {
  set U;
  set V;
  param Cost[U, V] : Real = 1;
  minimize sum(Cost[u, v] for u in U for v in V);
}
"""
    program = parse_to_ast(text, filename="two_gen_sum.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    objective = problem.stmts[-1]
    assert isinstance(objective, ast.Objective)
    assert isinstance(objective.expr, ast.NumAggregate)
    assert isinstance(objective.expr.comp, ast.NumComprehension)
    assert [(b.var, b.domain_set) for b in objective.expr.comp.binders] == [
        ("u", "U"),
        ("v", "V"),
    ]


def test_two_gen_sum_with_where_parses() -> None:
    """sum(Cost[u,v] for u in V for v in V where u != v) parses."""
    text = """
problem P {
  set V;
  param Cost[V, V] : Real = 1;
  minimize sum(Cost[u, v] for u in V for v in V where u != v);
}
"""
    program = parse_to_ast(text, filename="two_gen_sum_where.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    objective = problem.stmts[-1]
    assert isinstance(objective, ast.Objective)
    assert isinstance(objective.expr, ast.NumAggregate)
    assert isinstance(objective.expr.comp, ast.NumComprehension)
    assert len(objective.expr.comp.binders) == 2
    assert objective.expr.comp.where is not None


def test_two_gen_any_parses() -> None:
    """any(Allowed[i,j] for i in I for j in J) parses."""
    text = """
problem P {
  set I;
  set J;
  find Assign : Mapping(I -> J);
  must any(Assign.is(i, j) for i in I for j in J);
}
"""
    program = parse_to_ast(text, filename="two_gen_any.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    constraint = problem.stmts[-1]
    assert isinstance(constraint, ast.Constraint)
    assert isinstance(constraint.expr, ast.BoolAggregate)
    assert isinstance(constraint.expr.comp, ast.BoolComprehension)
    assert [(b.var, b.domain_set) for b in constraint.expr.comp.binders] == [
        ("i", "I"),
        ("j", "J"),
    ]


def test_two_gen_all_with_where_parses() -> None:
    """all(Constraint[i,j] for i in I for j in J where Active[i]) parses."""
    text = """
problem P {
  set I;
  set J;
  find Assign : Mapping(I -> J);
  find Active : Subset(I);
  must all(Assign.is(i, j) for i in I for j in J where Active.has(i));
}
"""
    program = parse_to_ast(text, filename="two_gen_all_where.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    constraint = problem.stmts[-1]
    assert isinstance(constraint, ast.Constraint)
    assert isinstance(constraint.expr, ast.BoolAggregate)
    assert isinstance(constraint.expr.comp, ast.BoolComprehension)
    assert len(constraint.expr.comp.binders) == 2
    assert constraint.expr.comp.where is not None


def test_three_gen_any_parses() -> None:
    """any(Allowed[i,j,k] for i in I for j in J for k in K) parses."""
    text = """
problem P {
  set I;
  set J;
  set K;
  find Active : Subset(I);
  must any(Active.has(i) for i in I for j in J for k in K);
}
"""
    program = parse_to_ast(text, filename="three_gen_any.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    constraint = problem.stmts[-1]
    assert isinstance(constraint, ast.Constraint)
    assert isinstance(constraint.expr, ast.BoolAggregate)
    assert isinstance(constraint.expr.comp, ast.BoolComprehension)
    assert [(b.var, b.domain_set) for b in constraint.expr.comp.binders] == [
        ("i", "I"),
        ("j", "J"),
        ("k", "K"),
    ]


# ---------------------------------------------------------------------------
# Relation declarations (Milestone 2)
# ---------------------------------------------------------------------------


def test_relation_declaration_parses() -> None:
    """relation Edge(u: V, v: V); parses to a relation declaration."""
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  must true;
}
"""
    program = parse_to_ast(text, filename="relation_decl.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    relation = problem.stmts[1]
    assert isinstance(relation, ast.RelationDecl)
    assert relation.name == "Edge"
    assert [(field.name, field.set_name) for field in relation.fields] == [
        ("u", "V"),
        ("v", "V"),
    ]


def test_relation_membership_call_parses() -> None:
    """Edge(u, v) membership call parses after a relation declaration."""
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  must forall u in V: forall v in V: not (Pick.has(u) and Pick.has(v) and Edge(u, v));
}
"""
    program = parse_to_ast(text, filename="relation_call.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    constraint = problem.stmts[-1]
    assert isinstance(constraint, ast.Constraint)


def test_tuple_binder_in_count_parses() -> None:
    """count((u,v) in Edge where Pick.has(u) and Pick.has(v)) parses."""
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  minimize count((u, v) in Edge where Pick.has(u) and Pick.has(v));
}
"""
    program = parse_to_ast(text, filename="tuple_binder_count.qsol")
    problem = program.items[0]
    assert isinstance(problem, ast.ProblemDef)
    objective = problem.stmts[-1]
    assert isinstance(objective, ast.Objective)
    assert isinstance(objective.expr, ast.NumAggregate)
    assert isinstance(objective.expr.comp, ast.CountComprehension)
    binder = objective.expr.comp.binders[0]
    assert isinstance(binder, ast.TupleCompBinder)
    assert binder.vars == ("u", "v")
    assert binder.domain_relation == "Edge"
