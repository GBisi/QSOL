from __future__ import annotations

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.parse import ast


def validate_program(program: ast.Program) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for item in program.items:
        if isinstance(item, ast.ProblemDef):
            seen_objective_labels: dict[str, ast.Objective] = {}
            for stmt in item.stmts:
                if not isinstance(stmt, ast.Objective) or stmt.label is None:
                    continue
                previous = seen_objective_labels.get(stmt.label)
                if previous is not None:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2101",
                            message=f"duplicate objective label `{stmt.label}`",
                            span=stmt.span,
                            notes=[
                                (
                                    f"first objective label `{stmt.label}` appears at "
                                    f"{previous.span.filename}:{previous.span.line}:{previous.span.col}"
                                )
                            ],
                            help=[
                                "Use unique objective labels within a problem.",
                                "Objective labels are metadata and do not create expression names.",
                            ],
                        )
                    )
                    continue
                seen_objective_labels[stmt.label] = stmt

        if isinstance(item, ast.UnknownDef):
            if not item.rep_block:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        code="QSOL3001",
                        message=f"unknown `{item.name}` has empty rep block",
                        span=item.span,
                        help=[
                            "Add at least one representative declaration in `rep { ... }`.",
                            "Empty representations are accepted but usually indicate incomplete modeling.",
                        ],
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
                            help=[
                                "Replace `should`/`nice` with `must` inside `laws { ... }` blocks."
                            ],
                        )
                    )
    return diagnostics
