"""Compose a chart region's body, classify an existing body, splice it into a page.

Everything fitdocs writes into a dashboard page is a region body; this module
decides its lines and where they go. Text that did not come from the chart kit
(the image's alt text, the caption's window, the not-rendered note) passes
through ``escape_markdown(clean_text(...))`` here, the only module that imports
``fitdocs.render.charts.kit.format``.

A body is a tuple of lines without endings. The last line of a chart body or a
note body is blank, which separates the end marker from the content above it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final

from fitdocs.dashboards.grammar import (
    REFERENCE_RE,
    Line,
    RegionBlock,
    begin_marker,
    end_marker,
)
from fitdocs.render.charts.kit import ChartData, Output, RenderedChart, ValueKind
from fitdocs.render.charts.kit.format import clean_text, escape_markdown

NOTE_RE: Final[re.Pattern[str]] = re.compile(r"^\*Not rendered: .*\*$")

_MARKER_PREFIX: Final = "<!-- fitdocs:"
_REFERENCE_HEAD: Final = "<!-- fitdocs:snapshot "
_REFERENCE_TAIL: Final = " -->"
_CAPTION_SEPARATOR: Final = " · "
_DATE_KINDS: Final = (ValueKind.DATE, ValueKind.DATETIME)


class BodyState(StrEnum):
    EMPTY = "empty"  # no non-blank line
    NOTE = "note"  # exactly one non-blank line, matching NOTE_RE
    RENDERED = "rendered"  # anything else


@dataclass(frozen=True)
class ChartBody:
    lines: tuple[str, ...]  # without endings


@dataclass(frozen=True)
class RegionEdit:
    chart_id: str
    body: ChartBody
    replace: RegionBlock | None  # None: insert after the directive's closing line
    after_line: int  # the directive's closing line (insertion point)


def _text(value: str) -> str:
    return escape_markdown(clean_text(value))


def _kit_lines(rendered: RenderedChart) -> list[str]:
    return rendered.text.split("\n")


def _refuse_markers(lines: Sequence[str]) -> None:
    for text in lines:
        if text.startswith(_MARKER_PREFIX):
            raise ValueError(
                "a region body line may not start with a fitdocs comment marker"
            )


def chart_body(
    *,
    page: str,
    chart_id: str,
    title: str,
    rendered: RenderedChart,
    caption: str | None,
    rows_table: RenderedChart | None,
    snapshot_path: str | None,
) -> ChartBody:
    """The lines of a rendered chart's region, parts apart by one blank line."""
    if rows_table is not None and rows_table.output is not Output.MARKDOWN:
        raise ValueError("a rows table is a markdown chart")
    parts: list[list[str]] = []
    if snapshot_path is not None:
        reference = f"{_REFERENCE_HEAD}{snapshot_path}{_REFERENCE_TAIL}"
        if REFERENCE_RE.fullmatch(reference) is None:
            raise ValueError("not a snapshot path fitdocs can read back")
        parts.append([reference])
    content: list[str] = []
    if rendered.output is Output.SVG:
        content.append(f"![{_text(title)}](assets/{page}/{chart_id}.svg)")
    else:
        content.extend(_kit_lines(rendered))
    _refuse_markers(content)
    parts.append(content)
    if caption is not None:
        parts.append([caption])
    if rows_table is not None:
        table = _kit_lines(rows_table)
        _refuse_markers(table)
        parts.append(table)
    lines: list[str] = []
    for part in parts:
        lines.extend(part)
        lines.append("")
    return ChartBody(tuple(lines))


def _latest_date(data: ChartData) -> date | None:
    latest: date | None = None
    for index, column in enumerate(data.columns):
        if column.kind not in _DATE_KINDS:
            continue
        for row in data.rows:
            value = row[index]
            if value is None:
                continue
            assert isinstance(value, date)
            day = value.date() if isinstance(value, datetime) else value
            if latest is None or day > latest:
                latest = day
    return latest


def caption(
    data: ChartData, *, window: str | None, snapshot_date: date | None
) -> str | None:
    """The caption line, or None when no part applies."""
    parts: list[str] = []
    if snapshot_date is not None:
        parts.append(f"Snapshot {snapshot_date.isoformat()}")
    if window is not None and window.strip():
        parts.append(_text(window))
    if not data.rows:
        parts.append("no rows")
    else:
        latest = _latest_date(data)
        if latest is not None:
            parts.append(f"through {latest.isoformat()}")
    if not parts:
        return None
    return "*" + _CAPTION_SEPARATOR.join(parts) + "*"


def note_body(message: str) -> ChartBody:
    return ChartBody((f"*Not rendered: {_text(message)}*", ""))


def classify_body(body: Sequence[Line]) -> BodyState:
    filled = [line for line in body if line.text.strip()]
    if not filled:
        return BodyState.EMPTY
    if len(filled) == 1 and NOTE_RE.fullmatch(filled[0].text):
        return BodyState.NOTE
    return BodyState.RENDERED


def recorded_snapshot(body: Sequence[Line]) -> str | None:
    """The path of the first snapshot reference line in the body, if any."""
    for line in body:
        if REFERENCE_RE.fullmatch(line.text):
            return line.text[len(_REFERENCE_HEAD) : -len(_REFERENCE_TAIL)]
    return None


def _span(edit: RegionEdit) -> tuple[int, int]:
    if edit.replace is None:
        return (edit.after_line, edit.after_line)
    assert edit.replace.end_line is not None
    return (edit.replace.begin_line, edit.replace.end_line)


def apply_edits(lines: Sequence[Line], edits: Sequence[RegionEdit]) -> str:
    """The page text with each edit applied; every other line is kept as it was.

    Inserted and replaced lines end as the directive's closing line does, or
    with ``\\n`` (added to that line) when it has no ending.
    """
    for checked in edits:
        if not 1 <= checked.after_line <= len(lines):
            raise ValueError("an edit's directive closing line is not on the page")
        if checked.replace is not None:
            if checked.replace.chart_id != checked.chart_id:
                raise ValueError("an edit replaces the region of another chart")
            if checked.replace.end_line is None:
                raise ValueError("an unclosed region cannot be replaced")
    ordered = sorted(edits, key=lambda each: _span(each)[0])
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if _span(earlier)[1] >= _span(later)[0]:
            raise ValueError("two edits touch the same lines")
    by_start = {_span(edit)[0]: edit for edit in ordered}
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        edit = by_start.get(line.number)
        if edit is None:
            out.append(line.text + line.ending)
            index += 1
            continue
        closer = lines[edit.after_line - 1]
        ending = closer.ending or "\n"
        body = [each + ending for each in edit.body.lines]
        if edit.replace is None:
            out.append(line.text + ending)
            out.append(begin_marker(edit.chart_id) + ending)
            out.extend(body)
            out.append(end_marker(edit.chart_id) + ending)
            index += 1
            continue
        assert edit.replace.end_line is not None
        out.append(line.text + line.ending)
        out.extend(body)
        index = edit.replace.end_line - 1
    return "".join(out)
