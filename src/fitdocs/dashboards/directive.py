"""Strict reading of a chart directive's YAML body.

Every scalar is the text exactly as written: the loader has no implicit
resolvers, so ``no``, ``2026-10-11`` and ``012`` stay strings. Anchors,
aliases, explicit tags and repeated keys are refused, and ``sql`` must be a
literal block scalar. The parser takes the body text and the opener's page
line; it imports only ``problems``, ``grammar`` (for ``SLUG``) and ``yaml``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

import yaml

from fitdocs.dashboards.grammar import SLUG
from fitdocs.dashboards.problems import DashboardCode, Problem, dashboard_problem


class Mode(StrEnum):
    RELATIVE = "relative"
    FROZEN = "frozen"


REQUIRED_KEYS: Final = ("id", "kind", "mode", "title", "sql")
OPTIONAL_KEYS: Final = ("channels", "options", "window", "show_rows")
MAX_ID_LENGTH: Final = 64

# The chart-id grammar is the page grammar's slug rule.
_ID_RE: Final = re.compile(SLUG)
_ACCEPTED: Final = (*REQUIRED_KEYS, *OPTIONAL_KEYS)
_PLAIN_TAGS: Final = frozenset(
    {"tag:yaml.org,2002:str", "tag:yaml.org,2002:map", "tag:yaml.org,2002:seq"}
)


#: What ``yaml.parse`` / ``yaml.compose`` raise: ``YAMLError`` plus the builtin
#: errors PyYAML lets escape (an ``OverflowError`` from a ``\U`` escape past
#: 0x7FFFFFFF, a ``RecursionError`` from absurd nesting). The subset of
#: ``fitdocs.contract.YAML_LOAD_ERRORS`` that parse/compose (no construction)
#: can raise; this package may not import that module.
_YAML_ERRORS: Final = (yaml.YAMLError, OverflowError, RecursionError)


class _StrictLoader(yaml.SafeLoader):
    """Composes every plain scalar as ``str``: no implicit resolvers."""

    yaml_implicit_resolvers = {}  # noqa: RUF012


@dataclass(frozen=True)
class Directive:
    chart_id: str
    kind: str
    mode: Mode
    title: str
    sql: str
    channels: Mapping[str, str]
    options: Mapping[str, str]
    window: str | None
    show_rows: bool
    line: int  # the opener's page line

    @property
    def sql_sha256(self) -> str:
        """The digest of the SQL without its trailing line breaks.

        A ``sql: |`` block keeps its final newline only when another key
        follows, so the same query would otherwise digest differently after a
        key moves below it.
        """
        return hashlib.sha256(self.sql.rstrip("\r\n").encode("utf-8")).hexdigest()


def _single_line(text: str) -> bool:
    return "\n" not in text and "\r" not in text


def parse_directive(
    body: str, *, open_line: int, page: str
) -> Directive | tuple[Problem, ...]:
    """The directive in ``body`` (the lines between the delimiters), or its problems."""

    def line_at(index: int) -> int:
        # The page splits lines on "\n" only; PyYAML's own line count also
        # breaks on a lone "\r", U+0085, U+2028 and U+2029.
        return open_line + 1 + body[:index].count("\n")

    def at(mark: yaml.Mark) -> int:
        return line_at(mark.index)

    def problem(
        code: DashboardCode,
        message: str,
        fix: str,
        *,
        line: int,
        chart: str | None = None,
        **fields: object,
    ) -> Problem:
        return dashboard_problem(
            code, message, fix, page=page, chart=chart, line=line, **fields
        )

    def syntax(error: Exception) -> tuple[Problem, ...]:
        mark = getattr(error, "problem_mark", None) or getattr(
            error, "context_mark", None
        )
        position = getattr(error, "position", None)  # a ReaderError has no mark
        if mark is not None:
            line = at(mark)
        elif isinstance(position, int):
            line = line_at(position)
        else:
            line = open_line
        reason = getattr(error, "problem", None) or "the text is not valid YAML"
        return (
            problem(
                DashboardCode.YAML_SYNTAX,
                f"The directive body does not parse: {str(reason).rstrip('.')}.",
                "Fix the YAML at the named line.",
                line=line,
            ),
        )

    # Event walk: anchors, aliases and explicit tags are refused.
    shape: list[Problem] = []
    try:
        for event in yaml.parse(body, Loader=_StrictLoader):
            line = at(event.start_mark)
            if isinstance(event, yaml.AliasEvent):
                shape.append(
                    problem(
                        DashboardCode.YAML_SHAPE,
                        "The directive uses a YAML alias, which is not allowed.",
                        "Write the value out instead of using an alias.",
                        line=line,
                    )
                )
            elif getattr(event, "anchor", None) is not None:
                shape.append(
                    problem(
                        DashboardCode.YAML_SHAPE,
                        "The directive uses a YAML anchor, which is not allowed.",
                        "Remove the anchor and write the value out.",
                        line=line,
                    )
                )
            elif getattr(event, "tag", None) is not None:
                shape.append(
                    problem(
                        DashboardCode.YAML_SHAPE,
                        "The directive uses an explicit YAML tag, which is refused.",
                        "Remove the tag; every value is read as the text written.",
                        line=line,
                    )
                )
    except _YAML_ERRORS as error:
        return syntax(error)
    if shape:
        return tuple(shape)

    try:
        root = yaml.compose(body, Loader=_StrictLoader)
    except _YAML_ERRORS as error:
        return syntax(error)
    if not isinstance(root, yaml.MappingNode):
        return (
            problem(
                DashboardCode.YAML_SHAPE,
                "The directive body is not a mapping of keys to values.",
                "Write the directive as `key: value` lines.",
                line=at(root.start_mark) if root is not None else open_line + 1,
            ),
        )

    # Structure of every mapping: scalar keys, no repeats.
    structure: list[Problem] = []
    pending: list[yaml.Node] = [root]
    while pending:
        node = pending.pop(0)
        if node.tag not in _PLAIN_TAGS:
            structure.append(
                problem(
                    DashboardCode.YAML_SHAPE,
                    f"A directive value resolves to the type {node.tag!r}, "
                    "not to text.",
                    "Write the value as plain text.",
                    line=at(node.start_mark),
                )
            )
        if isinstance(node, yaml.MappingNode):
            seen: set[str] = set()
            for key, value in node.value:
                if not isinstance(key, yaml.ScalarNode):
                    structure.append(
                        problem(
                            DashboardCode.YAML_SHAPE,
                            "A directive key is not plain text.",
                            "Use a text key.",
                            line=at(key.start_mark),
                        )
                    )
                else:
                    if key.value in seen:
                        structure.append(
                            problem(
                                DashboardCode.DUPLICATE_KEY,
                                f"The key {key.value!r} appears more than once.",
                                "Keep one occurrence of the key.",
                                line=at(key.start_mark),
                            )
                        )
                    seen.add(key.value)
                pending.append(value)
        elif isinstance(node, yaml.SequenceNode):
            pending.extend(node.value)
    if structure:
        return tuple(structure)

    fields: dict[str, yaml.Node] = {}
    key_lines: dict[str, int] = {}
    for key, value in root.value:
        fields[key.value] = value
        key_lines[key.value] = at(key.start_mark)

    def scalar(name: str) -> str | None:
        node = fields.get(name)
        return node.value if isinstance(node, yaml.ScalarNode) else None

    raw_id = scalar("id")
    chart = raw_id if raw_id is not None and _valid_id(raw_id) else None
    problems: list[Problem] = []

    for name in REQUIRED_KEYS:
        if name not in fields:
            problems.append(
                problem(
                    DashboardCode.MISSING_KEY,
                    f"The directive has no `{name}` key.",
                    "Add the key; the accepted keys are listed.",
                    line=open_line,
                    chart=chart,
                    option=name,
                    accepted=_ACCEPTED,
                )
            )
    for name in sorted(fields.keys() - set(_ACCEPTED)):
        problems.append(
            problem(
                DashboardCode.UNKNOWN_KEY,
                f"The directive key `{name}` is not accepted.",
                "Remove the key or use one of the accepted keys.",
                line=key_lines[name],
                chart=chart,
                option=name,
                accepted=_ACCEPTED,
            )
        )

    def field_problem(name: str, what: str) -> None:
        problems.append(
            problem(
                DashboardCode.FIELD_VALUE,
                f"The directive key `{name}` must be {what}.",
                f"Rewrite `{name}` as {what}.",
                line=key_lines[name],
                chart=chart,
                option=name,
            )
        )

    if "id" in fields and chart is None:
        subject = f"The chart id {raw_id!r}" if raw_id is not None else "The chart id"
        problems.append(
            problem(
                DashboardCode.ID_GRAMMAR,
                f"{subject} is not valid: an id is one or more groups of "
                f"lowercase ASCII letters and digits joined by single hyphens, at most "
                f"{MAX_ID_LENGTH} characters long.",
                "Rewrite the id to follow that rule.",
                line=key_lines["id"],
                option="id",
            )
        )

    kind = scalar("kind")
    if "kind" in fields and kind is None:
        field_problem("kind", "a single text value")

    mode: Mode | None = None
    if "mode" in fields:
        raw_mode = scalar("mode")
        try:
            mode = Mode(raw_mode) if raw_mode is not None else None
        except ValueError:
            mode = None
        if mode is None:
            problems.append(
                problem(
                    DashboardCode.MODE_VALUE,
                    f"The mode {raw_mode!r} is neither 'relative' nor 'frozen'."
                    if raw_mode is not None
                    else "The mode is neither 'relative' nor 'frozen'.",
                    "Set mode to relative or frozen.",
                    line=key_lines["mode"],
                    chart=chart,
                    option="mode",
                    accepted=tuple(m.value for m in Mode),
                )
            )

    title = scalar("title")
    if "title" in fields and (title is None or not _single_line(title)):
        field_problem("title", "single-line text")

    sql = scalar("sql")
    if "sql" in fields:
        node = fields["sql"]
        if not (isinstance(node, yaml.ScalarNode) and node.style == "|"):
            problems.append(
                problem(
                    DashboardCode.SQL_STYLE,
                    "The `sql` value is not a literal block scalar (`sql: |`); "
                    "other scalar styles can fold or cut SQL text.",
                    "Write the SQL as `sql: |` followed by indented lines.",
                    line=key_lines["sql"],
                    chart=chart,
                    option="sql",
                )
            )
            sql = None

    mappings: dict[str, dict[str, str]] = {}
    for name in ("channels", "options"):
        if name not in fields:
            continue
        node = fields[name]
        collected = _name_mapping(node)
        if collected is None:
            field_problem(name, "a mapping of names to single-line text values")
        else:
            mappings[name] = collected

    window = scalar("window")
    if "window" in fields and (window is None or not _single_line(window)):
        field_problem("window", "single-line text")

    show_rows = False
    if "show_rows" in fields:
        raw_rows = scalar("show_rows")
        if raw_rows in ("true", "false"):
            show_rows = raw_rows == "true"
        else:
            field_problem("show_rows", "`true` or `false`")

    if problems:
        return tuple(problems)
    assert chart is not None and kind is not None and mode is not None
    assert title is not None and sql is not None
    return Directive(
        chart_id=chart,
        kind=kind,
        mode=mode,
        title=title,
        sql=sql,
        channels=MappingProxyType(mappings.get("channels", {})),
        options=MappingProxyType(mappings.get("options", {})),
        window=window,
        show_rows=show_rows,
        line=open_line,
    )


def _valid_id(text: str) -> bool:
    return len(text) <= MAX_ID_LENGTH and _ID_RE.fullmatch(text) is not None


def _name_mapping(node: yaml.Node) -> dict[str, str] | None:
    """A mapping node of single-line scalar names to single-line scalar values.

    Keys are already known to be scalars: the structure walk refuses any other.
    """
    if not isinstance(node, yaml.MappingNode):
        return None
    out: dict[str, str] = {}
    for key, value in node.value:
        if not (
            isinstance(value, yaml.ScalarNode)
            and _single_line(key.value)
            and _single_line(value.value)
        ):
            return None
        out[key.value] = value.value
    return out
