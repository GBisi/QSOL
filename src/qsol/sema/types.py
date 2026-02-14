from __future__ import annotations

from dataclasses import dataclass


class Type:
    pass


@dataclass(frozen=True, slots=True)
class BoolType(Type):
    pass


@dataclass(frozen=True, slots=True)
class RealType(Type):
    pass


@dataclass(frozen=True, slots=True)
class IntRangeType(Type):
    lo: int
    hi: int


@dataclass(frozen=True, slots=True)
class SetType(Type):
    name: str


@dataclass(frozen=True, slots=True)
class ElemOfType(Type):
    set_name: str


@dataclass(frozen=True, slots=True)
class ParamType(Type):
    indices: tuple[SetType, ...]
    elem: Type


@dataclass(frozen=True, slots=True)
class UnknownTypeRef(Type):
    name: str
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnknownInstanceType(Type):
    ref: UnknownTypeRef


@dataclass(frozen=True, slots=True)
class UnknownType(Type):
    pass


BOOL = BoolType()
REAL = RealType()
UNKNOWN = UnknownType()


def is_numeric(tp: Type) -> bool:
    return isinstance(tp, (RealType, IntRangeType))


def promote_numeric(left: Type, right: Type) -> Type | None:
    if not is_numeric(left) or not is_numeric(right):
        return None
    if isinstance(left, RealType) or isinstance(right, RealType):
        return REAL
    if isinstance(left, IntRangeType) and isinstance(right, IntRangeType):
        return IntRangeType(lo=min(left.lo, right.lo), hi=max(left.hi, right.hi))
    return REAL
