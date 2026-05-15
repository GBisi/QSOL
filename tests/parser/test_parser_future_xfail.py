"""xfail probes for vNext syntax not yet in the grammar.

Each test here is expected to FAIL on the current grammar/sema.
When a feature is implemented the corresponding test must be updated:
  - Remove the xfail mark.
  - Assert the CORRECT shape, not merely that it parses.

These tests document intent and drive implementation — they are not allowed
to be silently passing or silently deleted.
"""

import pytest

from qsol.parse.parser import parse_to_ast

# ---------------------------------------------------------------------------
# Multi-generator comprehensions (Milestone 1)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="multi-generator comprehensions not yet implemented",
    strict=True,
)
def test_xfail_two_gen_sum() -> None:
    """sum(Cost[u,v] for u in U for v in V) should parse after Milestone 1."""
    text = """
problem P {
  set U;
  set V;
  param Cost[U, V] : Real = 1;
  minimize sum(Cost[u, v] for u in U for v in V);
}
"""
    parse_to_ast(text, filename="xfail_two_gen_sum.qsol")
    # must not raise


@pytest.mark.xfail(
    reason="multi-generator comprehensions not yet implemented",
    strict=True,
)
def test_xfail_two_gen_sum_with_where() -> None:
    """sum(Cost[u,v] for u in V for v in V where u != v) should parse after Milestone 1."""
    text = """
problem P {
  set V;
  param Cost[V, V] : Real = 1;
  minimize sum(Cost[u, v] for u in V for v in V where u != v);
}
"""
    parse_to_ast(text, filename="xfail_two_gen_sum_where.qsol")


@pytest.mark.xfail(
    reason="multi-generator comprehensions not yet implemented",
    strict=True,
)
def test_xfail_two_gen_any() -> None:
    """any(Allowed[i,j] for i in I for j in J) should parse after Milestone 1."""
    text = """
problem P {
  set I;
  set J;
  param Allowed[I, J] : Bool = true;
  must any(Allowed[i, j] for i in I for j in J);
}
"""
    parse_to_ast(text, filename="xfail_two_gen_any.qsol")


@pytest.mark.xfail(
    reason="multi-generator comprehensions not yet implemented",
    strict=True,
)
def test_xfail_two_gen_all_with_where() -> None:
    """all(Constraint[i,j] for i in I for j in J where Active[i]) should parse after Milestone 1."""
    text = """
problem P {
  set I;
  set J;
  param Constraint[I, J] : Bool = true;
  param Active[I] : Bool = true;
  must all(Constraint[i, j] for i in I for j in J where Active[i]);
}
"""
    parse_to_ast(text, filename="xfail_two_gen_all_where.qsol")


@pytest.mark.xfail(
    reason="multi-generator comprehensions not yet implemented",
    strict=True,
)
def test_xfail_three_gen_any() -> None:
    """any(Allowed[i,j,k] for i in I for j in J for k in K) should parse after Milestone 1."""
    text = """
problem P {
  set I;
  set J;
  set K;
  param Allowed[I, J, K] : Bool = true;
  must any(Allowed[i, j, k] for i in I for j in J for k in K);
}
"""
    parse_to_ast(text, filename="xfail_three_gen_any.qsol")


# ---------------------------------------------------------------------------
# Relation declarations (Milestone 2)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="relation declarations not yet implemented",
    strict=True,
)
def test_xfail_relation_declaration() -> None:
    """relation Edge(u: V, v: V); should parse after Milestone 2."""
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  must true;
}
"""
    parse_to_ast(text, filename="xfail_relation_decl.qsol")


@pytest.mark.xfail(
    reason="relation membership calls not yet implemented",
    strict=True,
)
def test_xfail_relation_membership_call() -> None:
    """Edge(u, v) membership call in constraint should parse after Milestone 2."""
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  must forall u in V: forall v in V: not (Pick.has(u) and Pick.has(v) and Edge(u, v));
}
"""
    parse_to_ast(text, filename="xfail_relation_call.qsol")


@pytest.mark.xfail(
    reason="tuple binders in comprehensions not yet implemented",
    strict=True,
)
def test_xfail_tuple_binder_in_count() -> None:
    """count((u,v) in Edge where Pick.has(u) and Pick.has(v)) after Milestone 2."""
    text = """
problem P {
  set V;
  relation Edge(u: V, v: V);
  find Pick : Subset(V);
  minimize count((u, v) in Edge where Pick.has(u) and Pick.has(v));
}
"""
    parse_to_ast(text, filename="xfail_tuple_binder_count.qsol")
