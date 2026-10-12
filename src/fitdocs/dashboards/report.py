"""Text and JSON forms of a ``RunReport``.

Both forms put the report in a fixed order: location problems by page,
pages by name, a page's charts and problems by page line, removed paths in
code-point order. Problems that share a line keep the order they arrived in
(the chart kit's own order). A problem with no line sorts before one with a
line.

The JSON form is one document with the key order of ``render_json``. The text
form puts every problem on one line, with its accepted values after the fix.
Runs of whitespace in a message or fix (a database error spans several lines)
collapse to single spaces.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from fitdocs.dashboards.engine import ChartResult, Outcome, PageResult, RunReport
from fitdocs.dashboards.problems import Problem, Severity

_NO_ID = "-"  # the text form's stand-in for a chart whose directive has no id


@dataclass(frozen=True)
class _Counts:
    charts: int
    rendered: int
    unchanged: int
    failed: int
    checked: int


def _by_line(problems: Iterable[Problem]) -> tuple[Problem, ...]:
    return tuple(
        sorted(problems, key=lambda each: -1 if each.line is None else each.line)
    )


def _by_page(problems: Iterable[Problem]) -> tuple[Problem, ...]:
    """Location problems: the one with no page first, then by file name."""
    return tuple(sorted(problems, key=lambda each: each.page or ""))


def _ordered_pages(report: RunReport) -> tuple[PageResult, ...]:
    return tuple(sorted(report.pages, key=lambda page: page.page))


def _ordered_charts(page: PageResult) -> tuple[ChartResult, ...]:
    return tuple(sorted(page.charts, key=lambda chart: chart.line))


def _counts(report: RunReport) -> _Counts:
    charts = [chart for page in report.pages for chart in page.charts]

    def tally(outcome: Outcome) -> int:
        return sum(1 for chart in charts if chart.outcome is outcome)

    return _Counts(
        len(charts),
        tally(Outcome.RENDERED),
        tally(Outcome.UNCHANGED),
        tally(Outcome.FAILED),
        tally(Outcome.CHECKED),
    )


# -- JSON ----------------------------------------------------------------------


def _chart_json(chart: ChartResult) -> dict[str, object]:
    return {
        "id": chart.chart,
        "line": chart.line,
        "kind": chart.kind,
        "mode": chart.mode,
        "outcome": chart.outcome.value,
        "snapshot": chart.snapshot,
        "problems": [each.as_dict() for each in _by_line(chart.problems)],
        "notices": [each.as_dict() for each in _by_line(chart.notices)],
    }


def _page_json(page: PageResult) -> dict[str, object]:
    return {
        "page": page.page,
        "written": page.written,
        "problems": [each.as_dict() for each in _by_line(page.problems)],
        "notices": [each.as_dict() for each in _by_line(page.notices)],
        "charts": [_chart_json(chart) for chart in _ordered_charts(page)],
    }


def render_json(report: RunReport) -> str:
    """The report as one JSON document, keys in the documented order."""
    counts = _counts(report)
    document: dict[str, object] = {
        "action": report.action.value,
        "index": {
            "state": report.index,
            "problem": (
                None if report.index_problem is None else report.index_problem.as_dict()
            ),
        },
        "location_problems": [
            each.as_dict() for each in _by_page(report.location_problems)
        ],
        "pages": [_page_json(page) for page in _ordered_pages(report)],
        "removed": sorted(report.removed),
        "summary": {
            "charts": counts.charts,
            "rendered": counts.rendered,
            "unchanged": counts.unchanged,
            "failed": counts.failed,
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False)


# -- text ----------------------------------------------------------------------


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _problem_line(problem: Problem, indent: str) -> str:
    label = f"{problem.code}:"
    if problem.severity is Severity.NOTICE:
        label = f"notice {label}"
    line = f"{indent}{label} {_one_line(problem.message)} {_one_line(problem.fix)}"
    if problem.accepted:
        accepted = ", ".join(_one_line(each) for each in problem.accepted)
        line += f" Accepted: {accepted}."
    return line


def _findings(
    problems: Iterable[Problem], notices: Iterable[Problem], indent: str
) -> list[str]:
    return [
        _problem_line(each, indent)
        for each in (*_by_line(problems), *_by_line(notices))
    ]


def _chart_is_listed(chart: ChartResult) -> bool:
    quiet = chart.outcome in (Outcome.UNCHANGED, Outcome.CHECKED)
    return not quiet or bool(chart.problems) or bool(chart.notices)


def _chart_lines(page: PageResult) -> list[str]:
    lines: list[str] = []
    for chart in _ordered_charts(page):
        if not _chart_is_listed(chart):
            continue
        name = _NO_ID if chart.chart is None else chart.chart
        lines.append(f"{page.page}:{chart.line} {name} {chart.outcome.value}")
        lines.extend(_findings(chart.problems, chart.notices, "  "))
    return lines


def _page_lines(page: PageResult) -> list[str]:
    lines = _findings(page.problems, page.notices, "  ")
    if lines:
        lines.insert(0, page.page)
    return [*lines, *_chart_lines(page)]


def _has_something_to_say(report: RunReport, counts: _Counts) -> bool:
    return bool(
        counts.rendered
        or counts.failed
        or report.removed
        or report.location_problems
        or report.index_problem is not None
        or any(
            page.written
            or page.problems
            or page.notices
            or any(chart.problems or chart.notices for chart in page.charts)
            for page in report.pages
        )
    )


def _summary_line(counts: _Counts, removed: int) -> str:
    line = (
        f"Dashboards: {counts.rendered} rendered, {counts.unchanged} unchanged, "
        f"{counts.failed} failed"
    )
    if counts.checked:
        line += f", {counts.checked} checked"
    if removed:
        line += f", {removed} images removed"
    return f"{line}."


def render_text(report: RunReport, *, chained: bool) -> str:
    """The report as text; ``""`` when ``chained`` and nothing is worth saying."""
    counts = _counts(report)
    if chained and not _has_something_to_say(report, counts):
        return ""
    lines = [_problem_line(each, "") for each in _by_page(report.location_problems)]
    if report.index_problem is not None:
        lines.append(_problem_line(report.index_problem, ""))
    for page in _ordered_pages(report):
        lines.extend(_page_lines(page))
    lines.append(_summary_line(counts, len(report.removed)))
    return "\n".join(lines)
