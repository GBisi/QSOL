from __future__ import annotations

import re
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

_EXPECTED_TOKEN_NAMES = {
    "END": "`;`",
    "RBRACE": "`}`",
    "LBRACE": "`{`",
    "RPAR": "`)`",
    "LPAR": "`(`",
    "RSQB": "`]`",
    "LSQB": "`[`",
    "COMMA": "`,`",
    "PLUS": "`+`",
    "MINUS": "`-`",
    "STAR": "`*`",
    "SLASH": "`/`",
    "EQUAL": "`=`",
    "LESSTHAN": "`<`",
    "MORETHAN": "`>`",
    "__ANON_3": "`<=`",
    "__ANON_4": "`>=`",
    "__ANON_5": "`!=`",
    "__ANON_6": "`=>`",
}


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
    lines = source.splitlines()
    hints: list[str] = []
    if line < 1:
        return hints
    if line > len(lines):
        return hints
    text = lines[line - 1]
    if " if " in text and " for " in text and text.strip().startswith(("must", "should", "nice")):
        hints.extend(
            [
                "Strict grammar does not allow trailing `for` after guarded constraints.",
                "Rewrite as explicit quantifier, e.g. `must forall x in X: cond => expr;`",
            ]
        )
    return hints


def _friendly_expected(expected: list[str]) -> list[str]:
    normalized: list[str] = []
    for token in expected:
        normalized.append(_EXPECTED_TOKEN_NAMES.get(token, token.lower()))
    # preserve order, drop duplicates
    return list(dict.fromkeys(normalized))


def _expected_note(expected: list[str]) -> str | None:
    if not expected:
        return None
    pretty = _friendly_expected(expected)
    limit = 8
    shown = pretty[:limit]
    extra = len(pretty) - len(shown)
    suffix = "" if extra <= 0 else f", ... (+{extra} more)"
    return f"expected one of: {', '.join(shown)}{suffix}"


def _syntax_hints(source: str, line: int, col: int, expected: list[str]) -> list[str]:
    hints = _parse_help_hint(source, line)
    lines = source.splitlines()
    if line >= 2 and line - 1 <= len(lines):
        prev = lines[line - 2].strip()
        cur = lines[line - 1].lstrip()
        if (
            prev
            and not prev.endswith((";", "{", "}", ","))
            and (
                cur.startswith(
                    (
                        "use ",
                        "set ",
                        "find ",
                        "param ",
                        "must ",
                        "should ",
                        "nice ",
                        "minimize ",
                        "maximize ",
                    )
                )
                or col <= 3
            )
        ):
            hints.append("A statement likely misses a trailing `;` before this location.")
            hints.append("Terminate declarations, constraints, and objectives with `;`.")

    if line >= 1 and line <= len(lines):
        text = lines[line - 1]
        if "LSQB" in expected and re.search(r"\b[A-Za-z_]\w*\s*\(", text):
            hints.append(
                "Indexed parameter access uses brackets, e.g. `Cost[i]` instead of `Cost(i)`."
            )
        if text.count("(") != text.count(")"):
            hints.append("Unbalanced parentheses detected near this line.")
        if text.count("[") != text.count("]"):
            hints.append("Unbalanced brackets detected near this line.")
    return list(dict.fromkeys(hints))


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
        expected_note = _expected_note(expected)
        if expected_note is not None:
            notes.append(expected_note)
        hint = _syntax_hints(text, line, col, expected)
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
