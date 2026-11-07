"""The publish template language (publish-core Req 4.4, 4.5, 5.6, 5.7).

Templates are scanned left to right.  ``{{`` and ``}}`` are literal braces,
``{name}`` is a placeholder drawn from a known set, and ``{?...}`` is an
optional clause that renders only when every placeholder inside it has a
value.  Any other brace is a syntax error reported with a 1-based line and
column.  Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Final

_NAME: Final = re.compile(r"[a-z][a-z0-9_]*")
_NAME_CHARS: Final = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_BAD_BRACE: Final = (
    "invalid placeholder: '{' must start a placeholder like {name}, "
    "an optional clause '{?', or be written '{{'"
)


@dataclass(frozen=True)
class Text:
    value: str


@dataclass(frozen=True)
class Placeholder:
    name: str


@dataclass(frozen=True)
class Clause:
    parts: tuple[Text | Placeholder, ...]


@dataclass(frozen=True)
class Template:
    source: str
    parts: tuple[Text | Placeholder | Clause, ...]


class TemplateSyntaxError(ValueError):
    """A template the grammar rejects, with where and why."""

    def __init__(self, line: int, column: int, reason: str) -> None:
        super().__init__(f"line {line}, column {column}: {reason}")
        self.line = line
        self.column = column
        self.reason = reason


@dataclass(frozen=True)
class TargetTemplates:
    title: Template
    description: Template


@dataclass(frozen=True)
class MissingValue:
    name: str


def _position(text: str, offset: int) -> tuple[int, int]:
    """1-based line and column of ``offset``; only ``\\n`` ends a line."""
    line = text.count("\n", 0, offset) + 1
    column = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, column


def parse_template(text: str, *, names: Collection[str]) -> Template:
    """Parse ``text``; raise ``TemplateSyntaxError`` on the first problem."""

    def fail(offset: int, reason: str) -> TemplateSyntaxError:
        line, column = _position(text, offset)
        return TemplateSyntaxError(line, column, reason)

    top: list[Text | Placeholder | Clause] = []
    clause: list[Text | Placeholder] = []
    clause_start = -1
    in_clause = False
    buf: list[str] = []
    i = 0
    n = len(text)

    def flush() -> None:
        if buf:
            piece = Text("".join(buf))
            buf.clear()
            (clause if in_clause else top).append(piece)

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "{" and nxt == "{":
            buf.append("{")
            i += 2
        elif ch == "}" and nxt == "}":
            buf.append("}")
            i += 2
        elif ch == "}":
            if not in_clause:
                raise fail(i, "a lone '}' (write '}}' for a literal brace)")
            flush()
            if not any(isinstance(p, Placeholder) for p in clause):
                raise fail(
                    clause_start, "an optional clause needs at least one placeholder"
                )
            top.append(Clause(tuple(clause)))
            clause = []
            in_clause = False
            i += 1
        elif ch == "{" and nxt == "?":
            if in_clause:
                raise fail(i, "an optional clause cannot hold another clause")
            flush()
            in_clause = True
            clause_start = i
            i += 2
        elif ch == "{":
            end = i + 1
            while end < n and text[end] in _NAME_CHARS:
                end += 1
            if end == n:
                raise fail(
                    i, "unterminated placeholder (write '{{' for a literal brace)"
                )
            name = text[i + 1 : end]
            if text[end] != "}" or not _NAME.fullmatch(name):
                raise fail(i, _BAD_BRACE)
            if name not in names:
                raise fail(i, f"unknown placeholder {{{name}}}")
            flush()
            (clause if in_clause else top).append(Placeholder(name))
            i = end + 1
        else:
            buf.append(ch)
            i += 1
    if in_clause:
        raise fail(clause_start, "unterminated optional clause (missing '}')")
    flush()
    return Template(text, tuple(top))


def is_placeholder_name(name: str) -> bool:
    """True when ``name`` follows the grammar ``parse_template`` accepts for names."""
    return _NAME.fullmatch(name) is not None


def template_names(template: Template) -> frozenset[str]:
    """Every placeholder name ``template`` uses, inside optional clauses or not."""
    found: set[str] = set()
    for part in template.parts:
        if isinstance(part, Placeholder):
            found.add(part.name)
        elif isinstance(part, Clause):
            found.update(p.name for p in part.parts if isinstance(p, Placeholder))
    return frozenset(found)


def render(template: Template, values: Mapping[str, str | None]) -> str | MissingValue:
    """Fill ``template``; the first bare placeholder without a value is missing."""
    out: list[str] = []
    for part in template.parts:
        if isinstance(part, Text):
            out.append(part.value)
        elif isinstance(part, Placeholder):
            value = values.get(part.name)
            if value is None:
                return MissingValue(part.name)
            out.append(value)
        else:
            pieces: list[str] = []
            for inner in part.parts:
                if isinstance(inner, Text):
                    pieces.append(inner.value)
                    continue
                value = values.get(inner.name)
                if value is None:
                    pieces = []
                    break
                pieces.append(value)
            out.append("".join(pieces))
    return "".join(out)
