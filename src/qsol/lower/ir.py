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
    expr: KSetExpr | None = None


@dataclass(frozen=True, slots=True)
class KRelationField(KNode):
    name: str
    set_name: str


@dataclass(frozen=True, slots=True)
class KRelationDecl(KNode):
    name: str
    fields: tuple[KRelationField, ...]
    expr: KRelationExpr | None = None


@dataclass(frozen=True, slots=True)
class KStructureDecl(KNode):
    name: str
    constructor: str
    args: tuple[str, ...]


class KSetExpr(KNode):
    pass


@dataclass(frozen=True, slots=True)
class KRangeSetExpr(KSetExpr):
    lo: KNumExpr
    hi: KNumExpr


@dataclass(frozen=True, slots=True)
class KParamDecl(KNode):
    name: str
    indices: tuple[str, ...]
    scalar_kind: str
    elem_set: str | None
    default: object | None


@dataclass(frozen=True, slots=True, init=False)
class KFindDecl(KNode):
    name: str
    indices: tuple[str, ...]
    decision_type: KDecisionType

    def __init__(
        self,
        span: Span,
        name: str,
        indices: tuple[str, ...] | None = None,
        decision_type: KDecisionType | None = None,
        unknown_type: UnknownTypeRef | None = None,
    ) -> None:
        if decision_type is None:
            if unknown_type is None:
                raise TypeError("KFindDecl requires decision_type or unknown_type")
            decision_type = KUnknownDecisionType(span=unknown_type.span, unknown_type=unknown_type)
        object.__setattr__(self, "span", span)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "indices", () if indices is None else indices)
        object.__setattr__(self, "decision_type", decision_type)

    @property
    def unknown_type(self) -> UnknownTypeRef:
        if isinstance(self.decision_type, KUnknownDecisionType):
            return self.decision_type.unknown_type
        raise AttributeError("scalar find declarations do not have unknown_type")


class KDecisionType(KNode):
    pass


@dataclass(frozen=True, slots=True)
class KUnknownDecisionType(KDecisionType):
    unknown_type: UnknownTypeRef


@dataclass(frozen=True, slots=True)
class KBoolDecisionType(KDecisionType):
    pass


@dataclass(frozen=True, slots=True)
class KIntDecisionType(KDecisionType):
    lo: KNumExpr
    hi: KNumExpr
    encoding: str | None = None


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
class KBoolIfThenElse(KBoolExpr):
    cond: KBoolExpr
    then_expr: KBoolExpr
    else_expr: KBoolExpr


@dataclass(frozen=True, slots=True)
class KQuantifier(KBoolExpr):
    kind: str
    var: str
    domain_set: str
    expr: KBoolExpr


@dataclass(frozen=True, slots=True)
class KTupleQuantifier(KBoolExpr):
    kind: str
    vars: tuple[str, ...]
    domain_relation: str
    expr: KBoolExpr


@dataclass(frozen=True, slots=True)
class KCompBinder(KNode):
    """One `for VAR in DOMAIN` binder in a kernel IR comprehension."""

    var: str
    domain_set: str


@dataclass(frozen=True, slots=True)
class KTupleCompBinder(KNode):
    vars: tuple[str, ...]
    domain_relation: str


class KRelationExpr(KNode):
    pass


@dataclass(frozen=True, slots=True)
class KPairsRelationExpr(KRelationExpr):
    binders: tuple[KCompBinder | KTupleCompBinder, ...]
    where: KBoolExpr | None = None


@dataclass(frozen=True, slots=True)
class KFilterRelationExpr(KRelationExpr):
    binder: KTupleCompBinder
    where: KBoolExpr | None = None


@dataclass(frozen=True, slots=True, init=False)
class KNumComprehension(KNode):
    term: KNumExpr
    binders: tuple[KCompBinder | KTupleCompBinder, ...]

    def __init__(
        self,
        span: Span,
        term: KNumExpr,
        binders: tuple[KCompBinder | KTupleCompBinder, ...] | None = None,
        *,
        var: str | None = None,
        domain_set: str | None = None,
    ) -> None:
        if binders is None:
            if var is None or domain_set is None:
                raise TypeError("KNumComprehension requires binders or var/domain_set")
            binders = (KCompBinder(span=span, var=var, domain_set=domain_set),)
        object.__setattr__(self, "span", span)
        object.__setattr__(self, "term", term)
        object.__setattr__(self, "binders", binders)

    @property
    def var(self) -> str:
        binder = self.binders[0]
        if not isinstance(binder, KCompBinder):
            raise AttributeError("tuple comprehension binders do not have var")
        return binder.var

    @property
    def domain_set(self) -> str:
        binder = self.binders[0]
        if not isinstance(binder, KCompBinder):
            raise AttributeError("tuple comprehension binders do not have domain_set")
        return binder.domain_set


@dataclass(frozen=True, slots=True, init=False)
class KBoolComprehension(KNode):
    term: KBoolExpr
    binders: tuple[KCompBinder | KTupleCompBinder, ...]

    def __init__(
        self,
        span: Span,
        term: KBoolExpr,
        binders: tuple[KCompBinder | KTupleCompBinder, ...] | None = None,
        *,
        var: str | None = None,
        domain_set: str | None = None,
    ) -> None:
        if binders is None:
            if var is None or domain_set is None:
                raise TypeError("KBoolComprehension requires binders or var/domain_set")
            binders = (KCompBinder(span=span, var=var, domain_set=domain_set),)
        object.__setattr__(self, "span", span)
        object.__setattr__(self, "term", term)
        object.__setattr__(self, "binders", binders)

    @property
    def var(self) -> str:
        binder = self.binders[0]
        if not isinstance(binder, KCompBinder):
            raise AttributeError("tuple comprehension binders do not have var")
        return binder.var

    @property
    def domain_set(self) -> str:
        binder = self.binders[0]
        if not isinstance(binder, KCompBinder):
            raise AttributeError("tuple comprehension binders do not have domain_set")
        return binder.domain_set


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
    relations: tuple[KRelationDecl, ...] = ()
    structures: tuple[KStructureDecl, ...] = ()


@dataclass(frozen=True, slots=True)
class KernelIR(KNode):
    problems: tuple[KProblem, ...]


@dataclass(frozen=True, slots=True)
class GroundProblem(KNode):
    name: str
    set_values: dict[str, list[object]]
    params: dict[str, object]
    finds: tuple[KFindDecl, ...]
    constraints: tuple[KConstraint, ...]
    objectives: tuple[KObjective, ...]
    relation_values: dict[str, tuple[tuple[object, ...], ...]] = field(default_factory=dict)
    derived_sets: dict[str, str] = field(default_factory=dict)
    derived_relations: dict[str, str] = field(default_factory=dict)
    structures: dict[str, dict[str, object]] = field(default_factory=dict)


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
