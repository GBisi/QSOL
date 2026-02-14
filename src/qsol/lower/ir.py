from __future__ import annotations

from dataclasses import dataclass, field

from qsol.diag.source import Span
from qsol.parse.ast import ConstraintKind, ObjectiveKind, UnknownTypeRef


@dataclass(frozen=True, slots=True)
class KNode:
    span: Span


@dataclass(frozen=True, slots=True)
class KSetDecl(KNode):
    name: str


@dataclass(frozen=True, slots=True)
class KParamDecl(KNode):
    name: str
    indices: tuple[str, ...]
    scalar_kind: str
    elem_set: str | None
    default: object | None


@dataclass(frozen=True, slots=True)
class KFindDecl(KNode):
    name: str
    unknown_type: UnknownTypeRef


class KExpr(KNode):
    pass


class KBoolExpr(KExpr):
    pass


class KNumExpr(KExpr):
    pass


@dataclass(frozen=True, slots=True)
class KName(KBoolExpr, KNumExpr):
    name: str


@dataclass(frozen=True, slots=True)
class KBoolLit(KBoolExpr):
    value: bool


@dataclass(frozen=True, slots=True)
class KNumLit(KNumExpr):
    value: float


@dataclass(frozen=True, slots=True)
class KNot(KBoolExpr):
    expr: KBoolExpr


@dataclass(frozen=True, slots=True)
class KAnd(KBoolExpr):
    left: KBoolExpr
    right: KBoolExpr


@dataclass(frozen=True, slots=True)
class KOr(KBoolExpr):
    left: KBoolExpr
    right: KBoolExpr


@dataclass(frozen=True, slots=True)
class KImplies(KBoolExpr):
    left: KBoolExpr
    right: KBoolExpr


@dataclass(frozen=True, slots=True)
class KCompare(KBoolExpr):
    op: str
    left: KExpr
    right: KExpr


@dataclass(frozen=True, slots=True)
class KFuncCall(KBoolExpr, KNumExpr):
    name: str
    args: tuple[KExpr, ...]


@dataclass(frozen=True, slots=True)
class KMethodCall(KBoolExpr, KNumExpr):
    target: KExpr
    name: str
    args: tuple[KExpr, ...]


@dataclass(frozen=True, slots=True)
class KAdd(KNumExpr):
    left: KNumExpr
    right: KNumExpr


@dataclass(frozen=True, slots=True)
class KSub(KNumExpr):
    left: KNumExpr
    right: KNumExpr


@dataclass(frozen=True, slots=True)
class KMul(KNumExpr):
    left: KNumExpr
    right: KNumExpr


@dataclass(frozen=True, slots=True)
class KDiv(KNumExpr):
    left: KNumExpr
    right: KNumExpr


@dataclass(frozen=True, slots=True)
class KNeg(KNumExpr):
    expr: KNumExpr


@dataclass(frozen=True, slots=True)
class KIfThenElse(KNumExpr):
    cond: KBoolExpr
    then_expr: KNumExpr
    else_expr: KNumExpr


@dataclass(frozen=True, slots=True)
class KQuantifier(KBoolExpr):
    kind: str
    var: str
    domain_set: str
    expr: KBoolExpr


@dataclass(frozen=True, slots=True)
class KNumComprehension(KNode):
    term: KNumExpr
    var: str
    domain_set: str


@dataclass(frozen=True, slots=True)
class KBoolComprehension(KNode):
    term: KBoolExpr
    var: str
    domain_set: str


@dataclass(frozen=True, slots=True)
class KSum(KNumExpr):
    comp: KNumComprehension


@dataclass(frozen=True, slots=True)
class KConstraint(KNode):
    kind: ConstraintKind
    expr: KBoolExpr


@dataclass(frozen=True, slots=True)
class KObjective(KNode):
    kind: ObjectiveKind
    expr: KNumExpr


@dataclass(frozen=True, slots=True)
class KProblem(KNode):
    name: str
    sets: tuple[KSetDecl, ...]
    params: tuple[KParamDecl, ...]
    finds: tuple[KFindDecl, ...]
    constraints: tuple[KConstraint, ...]
    objectives: tuple[KObjective, ...]


@dataclass(frozen=True, slots=True)
class KernelIR(KNode):
    problems: tuple[KProblem, ...]


@dataclass(frozen=True, slots=True)
class GroundProblem(KNode):
    name: str
    set_values: dict[str, list[str]]
    params: dict[str, object]
    finds: tuple[KFindDecl, ...]
    constraints: tuple[KConstraint, ...]
    objectives: tuple[KObjective, ...]


@dataclass(frozen=True, slots=True)
class GroundIR(KNode):
    problems: tuple[GroundProblem, ...]


@dataclass(slots=True)
class BackendArtifacts:
    cqm_path: str | None = None
    bqm_path: str | None = None
    format_path: str | None = None
    varmap_path: str | None = None
    explain_path: str | None = None
    stats: dict[str, float | int] = field(default_factory=dict)
