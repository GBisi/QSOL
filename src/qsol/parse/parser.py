from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from lark import Lark, Tree
from lark.exceptions import UnexpectedInput

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.parse.ast import Program
from qsol.parse.ast_builder import ASTBuilder


@dataclass(frozen=True, slots=True)
class ParseFailure(Exception):
    diagnostic: Diagnostic


@lru_cache(maxsize=1)
def _parser() -> Lark:
    grammar = Path(__file__).with_name("grammar.lark").read_text(encoding="utf-8")
    return Lark(
        grammar,
        parser="lalr",
        lexer="contextual",
        propagate_positions=True,
        maybe_placeholders=False,
        start="start",
    )


def _parse_help_hint(source: str, line: int) -> list[str]:
    if line < 1:
        return []
    lines = source.splitlines()
    if line > len(lines):
        return []
    text = lines[line - 1]
    if " if " in text and " for " in text and text.strip().startswith(("must", "should", "nice")):
        return [
            "Strict grammar does not allow trailing `for` after guarded constraints.",
            "Rewrite as explicit quantifier, e.g. `must forall x in X: cond => expr;`",
        ]
    return []


def parse_program(text: str, filename: str | None = None) -> Tree[object]:
    actual_name = filename or "<input>"
    try:
        return cast(Tree[object], _parser().parse(text))
    except UnexpectedInput as exc:
        expected = sorted(exc.expected) if hasattr(exc, "expected") and exc.expected else []
        pos = exc.pos_in_stream if exc.pos_in_stream is not None else 0
        line = exc.line if exc.line is not None else 1
        col = exc.column if exc.column is not None else 1
        span = Span(
            start_offset=pos,
            end_offset=pos + 1,
            line=line,
            col=col,
            end_line=line,
            end_col=col + 1,
            filename=actual_name,
        )
        notes: list[str] = []
        if expected:
            notes.append(f"expected one of: {', '.join(expected)}")
        hint = _parse_help_hint(text, line)
        raise ParseFailure(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL1001",
                message="parse error",
                span=span,
                notes=notes,
                help=hint,
            )
        ) from exc


def parse_to_ast(text: str, filename: str | None = None) -> Program:
    actual_name = filename or "<input>"
    tree = parse_program(text, actual_name)
    return ASTBuilder(text=text, filename=actual_name).build(tree)
