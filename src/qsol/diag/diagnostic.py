from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from qsol.diag.source import Span


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: Severity
    code: str
    message: str
    span: Span
    notes: list[str] = field(default_factory=list)
    help: list[str] = field(default_factory=list)

    @property
    def is_error(self) -> bool:
        return self.severity == Severity.ERROR
