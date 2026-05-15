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
    numeric_kind: str | None = None


@dataclass(frozen=True, slots=True)
class ElemOfType(Type):
    set_name: str
    numeric_kind: str | None = None


@dataclass(frozen=True, slots=True)
class ParamType(Type):
    indices: tuple[SetType, ...]
    elem: Type


@dataclass(frozen=True, slots=True)
class CompType(Type):
    elem_type: Type


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
    return isinstance(tp, (RealType, IntRangeType)) or (
        isinstance(tp, ElemOfType) and tp.numeric_kind == "Int"
    )


def promote_numeric(left: Type, right: Type) -> Type | None:
    if not is_numeric(left) or not is_numeric(right):
        return None
    if isinstance(left, RealType) or isinstance(right, RealType):
        return REAL
    if isinstance(left, IntRangeType) and isinstance(right, IntRangeType):
        return IntRangeType(lo=min(left.lo, right.lo), hi=max(left.hi, right.hi))
    if isinstance(left, ElemOfType) and left.numeric_kind == "Int":
        return right if isinstance(right, RealType) else REAL
    if isinstance(right, ElemOfType) and right.numeric_kind == "Int":
        return left if isinstance(left, RealType) else REAL
    return REAL
