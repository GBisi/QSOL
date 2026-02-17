from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from qsol.diag.source import Span


@dataclass(frozen=True, slots=True)
class Node:
    span: Span


class ConstraintKind(str, Enum):
    MUST = "must"
    SHOULD = "should"
    NICE = "nice"


class ObjectiveKind(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass(frozen=True, slots=True)
class Program(Node):
    items: list[TopItem]


class TopItem(Node):
    pass


@dataclass(frozen=True, slots=True)
class UseStmt(TopItem):
    module: str


@dataclass(frozen=True, slots=True)
class ProblemDef(TopItem):
    name: str
    stmts: list[ProblemStmt]


@dataclass(frozen=True, slots=True)
class UnknownDef(TopItem):
    name: str
    formals: list[str]
    rep_block: list[RepDecl]
    laws_block: list[Constraint]
    view_block: list[ViewMember]


class ProblemStmt(Node):
    pass


@dataclass(frozen=True, slots=True)
class SetDecl(ProblemStmt):
    name: str


@dataclass(frozen=True, slots=True)
class ScalarTypeRef(Node):
    kind: str
    lo: int | None = None
    hi: int | None = None


@dataclass(frozen=True, slots=True)
class ElemTypeRef(Node):
    set_name: str


@dataclass(frozen=True, slots=True)
class Literal(Node):
    value: bool | float | int | str


@dataclass(frozen=True, slots=True)
class ParamDecl(ProblemStmt):
    name: str
    indices: list[str]
    value_type: ScalarTypeRef | ElemTypeRef
    default: Literal | None


@dataclass(frozen=True, slots=True)
class UnknownTypeRef(Node):
    kind: str
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FindDecl(ProblemStmt):
    name: str
    unknown_type: UnknownTypeRef


@dataclass(frozen=True, slots=True)
class RepDecl(Node):
    name: str
    unknown_type: UnknownTypeRef


@dataclass(frozen=True, slots=True)
class Constraint(ProblemStmt):
    kind: ConstraintKind
    expr: BoolExpr
    guard: BoolExpr | None = None


@dataclass(frozen=True, slots=True)
class Objective(ProblemStmt):
    kind: ObjectiveKind
    expr: NumExpr


@dataclass(frozen=True, slots=True)
class PredicateFormal(Node):
    name: str
    kind: str
    type_arg: str | None = None


@dataclass(frozen=True, slots=True)
class PredicateDef(TopItem):
    name: str
    formals: list[PredicateFormal]
    expr: BoolExpr


@dataclass(frozen=True, slots=True)
class FunctionDef(TopItem):
    name: str
    formals: list[PredicateFormal]
    expr: NumExpr


ViewMember = PredicateDef | FunctionDef


class Expr(Node):
    pass


class BoolExpr(Expr):
    pass


class NumExpr(Expr):
    pass


@dataclass(frozen=True, slots=True)
class NameRef(Expr):
    name: str


@dataclass(frozen=True, slots=True)
class BoolLit(BoolExpr):
    value: bool


@dataclass(frozen=True, slots=True)
class NumLit(NumExpr):
    value: float


@dataclass(frozen=True, slots=True)
class StringLit(Expr):
    value: str


@dataclass(frozen=True, slots=True)
class Not(BoolExpr):
    expr: BoolExpr


@dataclass(frozen=True, slots=True)
class And(BoolExpr):
    left: BoolExpr
    right: BoolExpr


@dataclass(frozen=True, slots=True)
class Or(BoolExpr):
    left: BoolExpr
    right: BoolExpr


@dataclass(frozen=True, slots=True)
class Implies(BoolExpr):
    left: BoolExpr
    right: BoolExpr


@dataclass(frozen=True, slots=True)
class Compare(BoolExpr):
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class FuncCall(Expr):
    name: str
    args: list[Expr]
    call_style: str = "paren"


@dataclass(frozen=True, slots=True)
class MethodCall(Expr):
    target: Expr
    name: str
    args: list[Expr]


@dataclass(frozen=True, slots=True)
class Add(NumExpr):
    left: NumExpr
    right: NumExpr


@dataclass(frozen=True, slots=True)
class Sub(NumExpr):
    left: NumExpr
    right: NumExpr


@dataclass(frozen=True, slots=True)
class Mul(NumExpr):
    left: NumExpr
    right: NumExpr


@dataclass(frozen=True, slots=True)
class Div(NumExpr):
    left: NumExpr
    right: NumExpr


@dataclass(frozen=True, slots=True)
class Neg(NumExpr):
    expr: NumExpr


@dataclass(frozen=True, slots=True)
class IfThenElse(NumExpr):
    cond: BoolExpr
    then_expr: NumExpr
    else_expr: NumExpr


@dataclass(frozen=True, slots=True)
class BoolIfThenElse(BoolExpr):
    cond: BoolExpr
    then_expr: BoolExpr
    else_expr: BoolExpr


@dataclass(frozen=True, slots=True)
class Quantifier(BoolExpr):
    kind: str
    var: str
    domain_set: str
    expr: BoolExpr


@dataclass(frozen=True, slots=True)
class NumComprehension(Node):
    term: NumExpr
    var: str
    domain_set: str
    where: BoolExpr | None = None
    else_term: NumExpr | None = None


@dataclass(frozen=True, slots=True)
class BoolComprehension(Node):
    term: BoolExpr
    var: str
    domain_set: str
    where: BoolExpr | None = None
    else_term: BoolExpr | None = None


@dataclass(frozen=True, slots=True)
class CountComprehension(Node):
    var_ref: str
    var: str
    domain_set: str
    where: BoolExpr | None = None
    else_term: BoolExpr | None = None


@dataclass(frozen=True, slots=True)
class NumAggregate(NumExpr):
    kind: str
    comp: NumComprehension | CountComprehension
    from_comp_arg: bool = False


@dataclass(frozen=True, slots=True)
class BoolAggregate(BoolExpr):
    kind: str
    comp: BoolComprehension
    from_comp_arg: bool = False


TypedMap = dict[int, str]


@dataclass(frozen=True, slots=True)
class TypedProgram(Node):
    program: Program
    types: TypedMap = field(default_factory=dict)
