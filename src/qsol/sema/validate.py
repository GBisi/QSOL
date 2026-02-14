from __future__ import annotations

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.parse import ast


def validate_program(program: ast.Program) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for item in program.items:
        if isinstance(item, ast.UnknownDef):
            if not item.rep_block:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        code="QSOL3001",
                        message=f"unknown `{item.name}` has empty rep block",
                        span=item.span,
                    )
                )
            for law in item.laws_block:
                if law.kind != ast.ConstraintKind.MUST:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2101",
                            message="laws block accepts only `must` constraints",
                            span=law.span,
                        )
                    )
    return diagnostics
