"""The dashboard page grammar: a total, fence-aware scan of a page's lines.

The scan reads lines only. It finds chart directives and chart regions and
reports near misses; it never reads YAML (that is ``directive``) and never
decides what a region may hold (that is ``region`` and the engine).

A BOM on the first line is kept in that line's text so the lines join back to
the input byte for byte, but the scan compares the first line without it: an
invisible character does not move an opener off column 0.

Fences are tracked in ordinary text and inside a region's body alike. Inside an
open fence a column-0 ``<!-- fitdocs:`` line neither closes nor cuts a region;
a fence still open when the page ends runs the region to the end of the page,
unclosed. Fences are not tracked inside a directive body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from fitdocs.dashboards.problems import DashboardCode, Problem, dashboard_problem

SLUG: Final = r"[a-z0-9]+(?:-[a-z0-9]+)*"
PAGE_NAME_RE: Final[re.Pattern[str]] = re.compile(SLUG)
CHART_ID_RE: Final[re.Pattern[str]] = re.compile(SLUG)  # length <= 64 is checked apart
OPENER: Final = "<!-- fitdocs:chart"
CLOSER: Final = "-->"
REFERENCE_RE: Final[re.Pattern[str]] = re.compile(
    rf"<!-- fitdocs:snapshot assets/{SLUG}/{SLUG}\.snapshot-[1-9][0-9]*\.json -->"
)

_BOM: Final = "\ufeff"
_MARKER_PREFIX: Final = "<!-- fitdocs:"
_BEGIN_RE: Final[re.Pattern[str]] = re.compile(
    rf"<!-- fitdocs:begin:chart:({SLUG}) -->"
)
_END_RE: Final[re.Pattern[str]] = re.compile(rf"<!-- fitdocs:end:chart:({SLUG}) -->")
_TERMINATORS: Final = ("-->", "--!>")
_FENCE_RE: Final[re.Pattern[str]] = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")


def begin_marker(chart_id: str) -> str:
    return f"<!-- fitdocs:begin:chart:{chart_id} -->"


def end_marker(chart_id: str) -> str:
    return f"<!-- fitdocs:end:chart:{chart_id} -->"


@dataclass(frozen=True)
class Line:
    number: int  # 1-based
    text: str  # without its ending
    ending: str  # "\n", "\r\n", or "" for a final line without one


@dataclass(frozen=True)
class DirectiveBlock:
    open_line: int
    close_line: int | None  # None: no closer before the end of the page
    body: str | None  # body lines joined with "\n"; None when unclosed
    terminator_line: int | None  # first body line containing "-->" or "--!>"


@dataclass(frozen=True)
class RegionBlock:
    chart_id: str
    begin_line: int
    end_line: int | None  # None: no end marker before the next fitdocs line
    body: tuple[Line, ...]  # lines strictly between the markers
    # The column-0 ``<!-- fitdocs:`` line that cut an unclosed region short;
    # None when the region is closed or ran to the end of the page.
    intruder_line: int | None


@dataclass(frozen=True)
class PageScan:
    lines: tuple[Line, ...]
    directives: tuple[DirectiveBlock, ...]
    regions: tuple[RegionBlock, ...]
    problems: tuple[Problem, ...]  # opener_malformed, marker_malformed


def split_lines(text: str) -> tuple[Line, ...]:
    """Split on ``\\n`` only, keeping each ending (``\\r\\n`` or ``\\n``) apart."""
    lines: list[Line] = []
    start = 0
    while start < len(text):
        newline = text.find("\n", start)
        if newline < 0:
            lines.append(Line(len(lines) + 1, text[start:], ""))
            break
        if newline > start and text[newline - 1] == "\r":
            lines.append(Line(len(lines) + 1, text[start : newline - 1], "\r\n"))
        else:
            lines.append(Line(len(lines) + 1, text[start:newline], "\n"))
        start = newline + 1
    return tuple(lines)


def _logical(line: Line) -> str:
    """The line's text as the scan compares it: the first line without a BOM."""
    if line.number == 1:
        return line.text.removeprefix(_BOM)
    return line.text


@dataclass(frozen=True)
class _Fence:
    char: str
    length: int


def _fence_opening(text: str) -> _Fence | None:
    found = _FENCE_RE.fullmatch(text)
    if found is None:
        return None
    marks, info = found.group(1), found.group(2)
    if marks[0] == "`" and "`" in info:
        return None
    return _Fence(marks[0], len(marks))


def _closes_fence(text: str, fence: _Fence) -> bool:
    found = re.fullmatch(r" {0,3}(" + re.escape(fence.char) + r"+)[ \t]*", text)
    return found is not None and len(found.group(1)) >= fence.length


def _opener_problem(page: str, number: int) -> Problem:
    return dashboard_problem(
        DashboardCode.OPENER_MALFORMED,
        f"Line {number} mentions a chart directive but is not a valid opening line.",
        f"Make line {number} exactly `{OPENER}` starting at column 0, with nothing "
        "else on the line.",
        page=page,
        line=number,
    )


def _marker_problem(page: str, number: int, reason: str, fix: str) -> Problem:
    return dashboard_problem(
        DashboardCode.MARKER_MALFORMED,
        f"Line {number} {reason}.",
        fix,
        page=page,
        line=number,
    )


def scan_page(text: str, *, page: str) -> PageScan:
    lines = split_lines(text)
    directives: list[DirectiveBlock] = []
    regions: list[RegionBlock] = []
    problems: list[Problem] = []
    fence: _Fence | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        logical = _logical(line)
        if fence is not None:
            if _closes_fence(logical, fence):
                fence = None
            index += 1
            continue
        opening = _fence_opening(logical)
        if opening is not None:
            fence = opening
            index += 1
            continue
        if logical == OPENER:
            close = next(
                (
                    later
                    for later in range(index + 1, len(lines))
                    if lines[later].text == CLOSER
                ),
                None,
            )
            if close is None:
                directives.append(DirectiveBlock(line.number, None, None, None))
                index += 1  # the rest of the page is scanned as ordinary lines
                continue
            body = lines[index + 1 : close]
            terminator = next(
                (
                    each.number
                    for each in body
                    if any(mark in each.text for mark in _TERMINATORS)
                ),
                None,
            )
            directives.append(
                DirectiveBlock(
                    line.number,
                    lines[close].number,
                    "\n".join(each.text for each in body),
                    terminator,
                )
            )
            index = close + 1
            continue
        if OPENER in logical:
            problems.append(_opener_problem(page, line.number))
            index += 1
            continue
        begun = _BEGIN_RE.fullmatch(logical)
        if begun is not None:
            chart_id = begun.group(1)
            stop = len(lines)
            closed = False
            intruder: int | None = None
            inner: _Fence | None = None
            for later in range(index + 1, len(lines)):
                candidate = lines[later].text
                if inner is not None:
                    if _closes_fence(candidate, inner):
                        inner = None
                    continue
                if candidate.startswith(_MARKER_PREFIX) and not REFERENCE_RE.fullmatch(
                    candidate
                ):
                    stop = later
                    if candidate == end_marker(chart_id):
                        closed = True
                    else:
                        intruder = lines[later].number
                    break
                inner = _fence_opening(candidate)
            regions.append(
                RegionBlock(
                    chart_id,
                    line.number,
                    lines[stop].number if closed else None,
                    lines[index + 1 : stop],
                    intruder,
                )
            )
            index = stop + 1 if closed else stop
            continue
        if _END_RE.fullmatch(logical) is not None:
            problems.append(
                _marker_problem(
                    page,
                    line.number,
                    "is an end marker with no open region above it",
                    f"Remove line {line.number}, or put the matching begin marker "
                    "above it.",
                )
            )
        elif "fitdocs:begin:chart:" in logical or "fitdocs:end:chart:" in logical:
            problems.append(
                _marker_problem(
                    page,
                    line.number,
                    "mentions a chart region marker but is not a valid marker",
                    f"Make line {line.number} exactly `{begin_marker('<id>')}` or "
                    f"`{end_marker('<id>')}` starting at column 0, where the id is "
                    "lowercase letters and digits joined by single hyphens.",
                )
            )
        index += 1
    return PageScan(lines, tuple(directives), tuple(regions), tuple(problems))


def following_region(scan: PageScan, directive: DirectiveBlock) -> RegionBlock | None:
    """The region whose begin marker is the first non-blank line after the directive."""
    if directive.close_line is None:
        return None
    position = directive.close_line  # 0-based index of the line after the closer
    while position < len(scan.lines) and not scan.lines[position].text.strip():
        position += 1
    if position >= len(scan.lines):
        return None
    number = scan.lines[position].number
    return next((each for each in scan.regions if each.begin_line == number), None)
