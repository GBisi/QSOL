from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from qsol.diag.source import Span
from qsol.sema.types import Type


class SymbolKind(str, Enum):
    UNKNOWN_DEF = "unknown_def"
    PROBLEM = "problem"
    SET = "set"
    PARAM = "param"
    FIND = "find"
    BINDER = "binder"
    PREDICATE = "predicate"


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    kind: SymbolKind
    type: Type
    span: Span


@dataclass(slots=True)
class Scope:
    name: str
    parent: Scope | None = None
    symbols: dict[str, Symbol] = field(default_factory=dict)

    def define(self, symbol: Symbol) -> bool:
        if symbol.name in self.symbols:
            return False
        self.symbols[symbol.name] = symbol
        return True

    def lookup(self, name: str) -> Symbol | None:
        cur: Scope | None = self
        while cur is not None:
            if name in cur.symbols:
                return cur.symbols[name]
            cur = cur.parent
        return None


@dataclass(slots=True)
class SymbolTable:
    global_scope: Scope
    problem_scopes: dict[str, Scope] = field(default_factory=dict)
