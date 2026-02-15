from __future__ import annotations

from qsol.parse import ast
from qsol.parse.module_loader import ModuleLoader
from qsol.parse.parser import parse_to_ast
from qsol.sema.unknown_elaboration import elaborate_unknowns


def test_unknown_elaboration_expands_recursive_custom_finds_to_primitives() -> None:
    program = parse_to_ast(
        """
unknown InjectiveMapping(A, B) {
  rep {
    f : Mapping(A -> B);
  }
  laws {
    must forall b in B: count(a for a in A where f.is(a, b)) <= 1;
  }
  view {
    predicate is(a: Elem(A), b: Elem(B)): Bool = f.is(a, b);
  }
}

unknown PermLike(A) {
  rep {
    inj : InjectiveMapping(A, A);
  }
  view {
    predicate is(a: Elem(A), b: Elem(A)): Bool = inj.is(a, b);
  }
}

problem Demo {
  set V;
  find P : PermLike(V);
  must forall x in V: forall y in V: P.is(x, y) = P.is(x, y);
  minimize 0;
}
""",
        filename="elab.qsol",
    )

    loaded = ModuleLoader().resolve(program, root_filename="elab.qsol")
    assert not any(diag.is_error for diag in loaded.diagnostics)

    elaborated = elaborate_unknowns(loaded.program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    finds = [stmt for stmt in problem.stmts if isinstance(stmt, ast.FindDecl)]
    assert finds
    assert all(stmt.unknown_type.kind in {"Subset", "Mapping"} for stmt in finds)
    assert any(stmt.unknown_type.kind == "Mapping" for stmt in finds)

    constraints = [stmt for stmt in problem.stmts if isinstance(stmt, ast.Constraint)]
    assert constraints
    assert len(constraints) >= 2


def test_unknown_elaboration_keeps_unresolved_custom_find_for_later_resolver_errors() -> None:
    program = parse_to_ast(
        """
problem Demo {
  set A;
  find X : MissingUnknown(A);
  must true;
}
""",
        filename="elab_missing.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    finds = [stmt for stmt in problem.stmts if isinstance(stmt, ast.FindDecl)]
    assert finds
    assert finds[0].unknown_type.kind == "MissingUnknown"


def test_unknown_elaboration_reports_find_arity_mismatch_and_keeps_original_find() -> None:
    program = parse_to_ast(
        """
unknown OneArg(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x: Elem(A)): Bool = s.has(x); }
}

problem Demo {
  set A;
  find Bad : OneArg(A, A);
  must true;
}
""",
        filename="elab_arity.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert any(
        diag.code == "QSOL2101" and "expects 1" in diag.message for diag in elaborated.diagnostics
    )

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    finds = [stmt for stmt in problem.stmts if isinstance(stmt, ast.FindDecl)]
    assert finds
    assert finds[0].name == "Bad"
    assert finds[0].unknown_type.kind == "OneArg"


def test_unknown_elaboration_retains_unresolved_child_rep_find_when_child_unknown_missing() -> None:
    program = parse_to_ast(
        """
unknown Outer(A) {
  rep { inner : MissingChild(A); }
  laws { must true; }
  view { predicate ok(): Bool = true; }
}

problem Demo {
  set A;
  find X : Outer(A);
  must true;
}
""",
        filename="elab_missing_child.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    generated = [
        stmt
        for stmt in problem.stmts
        if isinstance(stmt, ast.FindDecl) and stmt.name.startswith("__qsol_u__")
    ]
    assert generated
    assert generated[0].unknown_type.kind == "MissingChild"


def test_unknown_elaboration_reports_child_expansion_failure_and_falls_back_to_custom_find() -> (
    None
):
    program = parse_to_ast(
        """
unknown Child(A, B) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate ok(): Bool = true; }
}

unknown Outer(A) {
  rep { inner : Child(A); }
  laws { must true; }
  view { predicate ok(): Bool = true; }
}

problem Demo {
  set A;
  find X : Outer(A);
  must true;
}
""",
        filename="elab_child_arity.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert any(
        diag.code == "QSOL2101" and "Child" in diag.message for diag in elaborated.diagnostics
    )

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    generated = [
        stmt
        for stmt in problem.stmts
        if isinstance(stmt, ast.FindDecl) and stmt.name.startswith("__qsol_u__")
    ]
    assert generated
    assert generated[0].unknown_type.kind == "Child"


def test_unknown_elaboration_resolves_alias_collisions_for_generated_find_names() -> None:
    program = parse_to_ast(
        """
unknown Wrap(A) {
  rep { inner : Subset(A); }
  laws { must true; }
  view { predicate has(x: Elem(A)): Bool = inner.has(x); }
}

problem P {
  set A;
  find __qsol_u__P__inner : Subset(A);
  find P : Wrap(A);
  must true;
}
""",
        filename="elab_alias_collision.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    find_names = [stmt.name for stmt in problem.stmts if isinstance(stmt, ast.FindDecl)]
    assert "__qsol_u__P__inner" in find_names
    assert "__qsol_u__P__inner__2" in find_names


def test_unknown_elaboration_inlines_local_view_calls_and_rewrites_set_args() -> None:
    program = parse_to_ast(
        """
unknown Fancy(T) {
  rep { base : Subset(T); }
  laws {
    must size(T) >= 0;
  }
  view {
    predicate has(x: Elem(T)): Bool = base.has(x);
    predicate alias(x: Elem(T)): Bool = has(x);
  }
}

problem Demo {
  set A;
  find F : Fancy(A);
  must forall x in A: F.alias(x);
  minimize -size(A);
}
""",
        filename="elab_inline.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    constraints = [stmt for stmt in problem.stmts if isinstance(stmt, ast.Constraint)]
    assert constraints
    assert any("base" in repr(stmt.expr) for stmt in constraints)

    objective = next(stmt for stmt in problem.stmts if isinstance(stmt, ast.Objective))
    assert isinstance(objective.expr, ast.Neg)


def test_unknown_elaboration_reports_unknown_method_and_predicate_arity_issues() -> None:
    program = parse_to_ast(
        """
unknown U(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x: Elem(A)): Bool = s.has(x); }
}

problem Demo {
  set A;
  find X : U(A);
  must forall x in A: X.missing(x);
  must forall x in A: X.has();
}
""",
        filename="elab_method_errors.qsol",
    )
    elaborated = elaborate_unknowns(program)
    messages = [diag.message for diag in elaborated.diagnostics]
    assert any("unknown method `missing`" in message for message in messages)
    assert any("expects 1 argument(s), got 0" in message for message in messages)


def test_unknown_elaboration_reports_recursive_view_predicate_expansion() -> None:
    program = parse_to_ast(
        """
unknown Loop(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate p(x: Elem(A)): Bool = p(x); }
}

problem Demo {
  set A;
  find X : Loop(A);
  must forall x in A: X.p(x);
}
""",
        filename="elab_recursive_view.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert any(
        diag.code == "QSOL2101" and "recursive view predicate expansion detected" in diag.message
        for diag in elaborated.diagnostics
    )


def test_unknown_elaboration_expands_top_level_predicates_and_functions() -> None:
    program = parse_to_ast(
        """
predicate iff(a: Bool, b: Bool): Bool = a and b or not a and not b;
function indicator(b: Bool): Real = if b then 1 else 0;

problem Demo {
  param Flag : Bool;
  must iff(Flag, true);
  minimize indicator(Flag);
}
""",
        filename="elab_top_level_macros.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    constraint = next(stmt for stmt in problem.stmts if isinstance(stmt, ast.Constraint))
    objective = next(stmt for stmt in problem.stmts if isinstance(stmt, ast.Objective))
    assert isinstance(constraint.expr, ast.Or)
    assert isinstance(objective.expr, ast.IfThenElse)


def test_unknown_elaboration_expands_view_functions_and_global_calls() -> None:
    program = parse_to_ast(
        """
function add1(x: Real): Real = x + 1;

unknown Fancy(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view {
    function score(x: Elem(A)): Real = add1(if s.has(x) then 1 else 0);
    predicate ok(x: Elem(A)): Bool = score(x) >= 0;
  }
}

problem Demo {
  set A;
  find F : Fancy(A);
  must forall x in A: F.ok(x);
  minimize sum(F.score(x) for x in A);
}
""",
        filename="elab_view_functions.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    objective = next(stmt for stmt in problem.stmts if isinstance(stmt, ast.Objective))
    assert isinstance(objective.expr, ast.NumAggregate)
    assert "score(" not in repr(objective.expr)
    assert "add1(" not in repr(objective.expr)


def test_unknown_elaboration_reports_recursive_top_level_macro_expansion() -> None:
    program = parse_to_ast(
        """
predicate p(x: Bool): Bool = q(x);
predicate q(x: Bool): Bool = p(x);

problem Demo {
  must p(true);
}
""",
        filename="elab_recursive_top_level_macros.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert any(
        diag.code == "QSOL2101" and "recursive macro expansion detected" in diag.message
        for diag in elaborated.diagnostics
    )


def test_unknown_elaboration_comp_real_formal_accepts_bool_comprehension_args() -> None:
    program = parse_to_ast(
        """
predicate atleast(k: Real, terms: Comp(Real)): Bool = terms >= k;

problem Demo {
  set A;
  find S : Subset(A);
  must atleast(1, S.has(x) for x in A);
}
""",
        filename="elab_comp_real.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    constraint = next(stmt for stmt in problem.stmts if isinstance(stmt, ast.Constraint))
    assert isinstance(constraint.expr, ast.Compare)
    assert isinstance(constraint.expr.left, ast.NumAggregate)
    assert isinstance(constraint.expr.left.comp, ast.NumComprehension)
    assert isinstance(constraint.expr.left.comp.term, ast.IfThenElse)


def test_unknown_elaboration_comp_bool_formal_accepts_numeric_comprehension_args() -> None:
    program = parse_to_ast(
        """
predicate any_positive(terms: Comp(Bool)): Bool = terms;

problem Demo {
  set A;
  param Score[A] : Real = 1;
  must any_positive(Score[x] for x in A);
}
""",
        filename="elab_comp_bool.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert not any(diag.is_error for diag in elaborated.diagnostics)

    problem = next(item for item in elaborated.program.items if isinstance(item, ast.ProblemDef))
    constraint = next(stmt for stmt in problem.stmts if isinstance(stmt, ast.Constraint))
    assert isinstance(constraint.expr, ast.BoolAggregate)
    assert isinstance(constraint.expr.comp.term, ast.Compare)


def test_unknown_elaboration_rejects_comp_arg_for_non_comp_formal() -> None:
    program = parse_to_ast(
        """
predicate nonneg(x: Real): Bool = x >= 0;

problem Demo {
  set A;
  find S : Subset(A);
  must nonneg(S.has(x) for x in A);
}
""",
        filename="elab_non_comp_bad.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert any(
        diag.code == "QSOL2101" and "does not accept comprehension-style arguments" in diag.message
        for diag in elaborated.diagnostics
    )


def test_unknown_elaboration_rejects_non_comprehension_for_comp_formal() -> None:
    program = parse_to_ast(
        """
predicate atleast(k: Real, terms: Comp(Real)): Bool = terms >= k;

problem Demo {
  must atleast(1, 1);
}
""",
        filename="elab_comp_missing.qsol",
    )
    elaborated = elaborate_unknowns(program)
    assert any(
        diag.code == "QSOL2101" and "expects a comprehension-style argument" in diag.message
        for diag in elaborated.diagnostics
    )
