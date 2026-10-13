"""The engine: plan a run, then draw and write the charts.

Planning lists the pages, reads them, scans and parses each directive,
associates regions with directives, and decides for each chart what data it
needs (a fetch, the snapshot its region records, or the latest stored
generation). Planning opens no source and writes nothing.

The rendering half opens the source once, after planning, for the charts that
need a fetch; takes every other frozen chart's rows from its stored snapshot;
draws each chart through the chart kit; composes each chart's region body (or
keeps a rendered region, or writes a note); and writes per page the new
snapshots, the images and then one page replacement. A frozen chart that is
fetched is encoded and decoded first, and drawn from the decoded rows, so the
stored and the drawn values are the same. A ``CHECK`` run does everything but
write. After the pages, ``REFRESH`` and ``FREEZE`` runs remove the marked
images no page links.

The engine reads no clock: the run date arrives in the request. It imports no
``binding`` module; the source is reached only through the opener it is given.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum
from functools import partial
from pathlib import Path

from fitdocs.dashboards.directive import Directive, Mode, parse_directive
from fitdocs.dashboards.grammar import (
    PAGE_NAME_RE,
    DirectiveBlock,
    PageScan,
    RegionBlock,
    begin_marker,
    end_marker,
    following_region,
    scan_page,
)
from fitdocs.dashboards.problems import (
    DashboardCode,
    Problem,
    dashboard_problem,
    from_chart_problem,
)
from fitdocs.dashboards.region import (
    BodyState,
    ChartBody,
    RegionEdit,
    apply_edits,
    caption,
    chart_body,
    classify_body,
    note_body,
    recorded_snapshot,
)
from fitdocs.dashboards.snapshot import (
    Snapshot,
    SnapshotFormatError,
    decode,
    encode,
)
from fitdocs.dashboards.source import (
    ChartSource,
    Fetched,
    SourceOpener,
    SourceUnavailable,
)
from fitdocs.dashboards.storage import (
    PageFile,
    Refusal,
    asset_rel_path,
    create_snapshot,
    latest_snapshot,
    list_markdown,
    location_refusal,
    read_page,
    read_snapshot,
    remove_stale_images,
    replace_page,
    write_asset,
)
from fitdocs.render.charts.kit import (
    ChartData,
    ChartError,
    ChartRequest,
    Column,
    Output,
    RenderedChart,
    render_chart,
)
from fitdocs.units import unit_for_column

_PAGE_SUFFIX = ".md"
_TABLE_KIND = "table"  # the kit kind that draws the rows of ``show_rows``
_SHOW_ROWS = "show_rows"


class Action(StrEnum):
    CHECK = "check"
    REFRESH = "refresh"
    FREEZE = "freeze"


class Outcome(StrEnum):
    RENDERED = "rendered"  # bytes written (region, asset or snapshot)
    UNCHANGED = "unchanged"  # rendered; nothing differed
    CHECKED = "checked"  # check form, no problem
    FAILED = "failed"  # one or more problems


class DataNeed(StrEnum):
    FETCH = "fetch"  # run the chart's SQL
    RECORDED = "recorded"  # the snapshot the chart's region records
    LATEST = "latest"  # the highest stored generation for the chart


@dataclass(frozen=True)
class Target:
    page: str
    chart: str | None


class TargetError(ValueError):
    """A target names no existing page or chart; the message lists the names."""


@dataclass(frozen=True)
class RunRequest:
    action: Action
    data_root: Path
    targets: tuple[Target, ...]  # empty: every page
    today: date


@dataclass(frozen=True)
class ChartResult:
    chart: str | None
    line: int
    kind: str | None
    mode: str | None
    outcome: Outcome
    snapshot: str | None
    problems: tuple[Problem, ...]
    notices: tuple[Problem, ...]


@dataclass(frozen=True)
class PageResult:
    page: str
    written: bool
    problems: tuple[Problem, ...]
    notices: tuple[Problem, ...]
    charts: tuple[ChartResult, ...]


@dataclass(frozen=True)
class RunReport:
    action: Action
    index: str  # "ready" | "not_needed" | SourceUnavailable.state
    index_problem: Problem | None
    location_problems: tuple[Problem, ...]  # location_foreign, page_name
    pages: tuple[PageResult, ...]
    removed: tuple[str, ...]

    @property
    def failed(self) -> bool:
        """True when a problem is reported anywhere; notices do not count."""
        return (
            bool(self.location_problems)
            or self.index_problem is not None
            or any(
                page.problems or any(each.problems for each in page.charts)
                for page in self.pages
            )
        )


@dataclass(frozen=True)
class PlannedChart:
    chart: str | None  # the id, when a trusted one is known
    line: int  # the directive's opening line
    close_line: int | None  # None: the directive is unclosed
    directive: Directive | None  # None: the directive did not parse
    region: RegionBlock | None  # the region directly below, when it is this chart's
    need: DataNeed | None  # None: a planning problem, or relative under a page FREEZE
    snapshot: str | None  # the planned snapshot path (RECORDED or LATEST)
    problems: tuple[Problem, ...]  # in page line order


@dataclass(frozen=True)
class PlannedPage:
    name: str
    file: PageFile | None  # None: the page could not be read
    scan: PageScan | None
    problems: tuple[Problem, ...]
    notices: tuple[Problem, ...]
    charts: tuple[PlannedChart, ...]  # in page order, the targeted ones only


@dataclass(frozen=True)
class RunPlan:
    location_problems: tuple[Problem, ...]
    pages: tuple[PlannedPage, ...]  # in page-name order


# -- problems ------------------------------------------------------------------


def _location_problem(refusal: str) -> Problem:
    return dashboard_problem(
        DashboardCode.LOCATION_FOREIGN,
        f"The dashboards location cannot be used: {refusal}.",
        "Make dashboards/ and dashboards/assets/ real directories in the data root.",
        page=None,
    )


def _name_problem(stem: str) -> Problem:
    name = f"{stem}{_PAGE_SUFFIX}"
    return dashboard_problem(
        DashboardCode.PAGE_NAME,
        f"The file {name} is not a valid page name: a page name is one or more "
        "groups of lowercase ASCII letters and digits joined by single hyphens.",
        f"Rename {name} to follow that rule, or move it out of dashboards/.",
        page=name,
    )


def _read_problem(page: str, refusal: Refusal) -> Problem:
    if refusal is Refusal.NOT_UTF8:
        return dashboard_problem(
            DashboardCode.PAGE_ENCODING,
            f"The page {page} is not valid UTF-8, so it was left unchanged.",
            "Save the page as UTF-8.",
            page=page,
        )
    reason = {
        Refusal.SYMLINK: "it is a symbolic link",
        Refusal.NOT_REGULAR: "it is not a regular file",
        Refusal.UNREADABLE: "it could not be read",
    }[refusal]
    return dashboard_problem(
        DashboardCode.PAGE_UNREADABLE,
        f"The page {page} was left unchanged because {reason}.",
        "Make the page a regular, readable file in dashboards/.",
        page=page,
    )


def _unclosed_directive(page: str, line: int) -> Problem:
    return dashboard_problem(
        DashboardCode.DIRECTIVE_UNCLOSED,
        f"The directive opened at line {line} has no closing `-->` line before "
        "the end of the page.",
        "Add a line holding only `-->` at column 0 after the directive's last key.",
        page=page,
        line=line,
    )


def _terminator(page: str, chart: str | None, line: int) -> Problem:
    return dashboard_problem(
        DashboardCode.DIRECTIVE_TERMINATOR,
        f"Line {line} contains `-->` or `--!>`, which ends the comment early and "
        "exposes the rest of the directive as visible text.",
        "Remove that sequence from the line.",
        page=page,
        chart=chart,
        line=line,
    )


def _duplicate_id(page: str, chart: str, line: int, lines: Sequence[int]) -> Problem:
    where = ", ".join(str(each) for each in lines)
    return dashboard_problem(
        DashboardCode.DUPLICATE_ID,
        f"The chart id `{chart}` is used by more than one directive (lines {where}).",
        "Give each directive on the page its own id.",
        page=page,
        chart=chart,
        line=line,
    )


def _mismatch(page: str, chart: str, region: RegionBlock) -> Problem:
    return dashboard_problem(
        DashboardCode.REGION_MISMATCH,
        f"The region directly below the directive for `{chart}` belongs to chart "
        f"`{region.chart_id}`.",
        f"Change the region's markers to `{begin_marker(chart)}` and "
        f"`{end_marker(chart)}`, or delete the region.",
        page=page,
        chart=chart,
        line=region.begin_line,
    )


def _misplaced(page: str, chart: str, region: RegionBlock) -> Problem:
    return dashboard_problem(
        DashboardCode.REGION_MISPLACED,
        f"The region for chart `{chart}` at line {region.begin_line} is not "
        "directly below the directive with that id.",
        "Move the region directly below its directive, or delete it so fitdocs "
        "inserts a new one.",
        page=page,
        chart=chart,
        line=region.begin_line,
    )


def _unclosed_region(page: str, chart: str, region: RegionBlock) -> Problem:
    return dashboard_problem(
        DashboardCode.REGION_UNCLOSED,
        f"The region for chart `{chart}` that begins at line {region.begin_line} "
        "has no end marker.",
        f"Add `{end_marker(chart)}` at column 0 after the region's content.",
        page=page,
        chart=chart,
        line=region.begin_line,
    )


def _region_contents(page: str, chart: str, region: RegionBlock, line: int) -> Problem:
    return dashboard_problem(
        DashboardCode.REGION_CONTENTS,
        f"The region for chart `{chart}` that begins at line {region.begin_line} is "
        f"cut short at line {line} by another fitdocs comment.",
        f"Add `{end_marker(chart)}` before line {line}, and keep fitdocs comments "
        "out of region bodies.",
        page=page,
        chart=chart,
        line=line,
    )


def _orphan(page: str, region: RegionBlock) -> Problem:
    return dashboard_problem(
        DashboardCode.REGION_ORPHANED,
        f"The region for chart `{region.chart_id}` at line {region.begin_line} "
        "matches no directive on this page.",
        "Delete the region, or add the directive with that id directly above it.",
        page=page,
        chart=region.chart_id,
        line=region.begin_line,
    )


def _freeze_relative(page: str, planned: PlannedChart) -> Problem:
    assert planned.chart is not None
    return dashboard_problem(
        DashboardCode.FREEZE_RELATIVE,
        f"The chart `{planned.chart}` is in mode relative, so it has no snapshot "
        "to take.",
        "Set `mode: frozen` on the chart if it should keep a snapshot.",
        page=page,
        chart=planned.chart,
        line=planned.line,
    )


# -- pages ---------------------------------------------------------------------


def _list_pages(data_root: Path) -> tuple[tuple[str, ...], tuple[Problem, ...]]:
    """Page names in name order, and a ``page_name`` problem per misnamed file.

    The caller has already checked the location.
    """
    stems = list_markdown(data_root)
    pages = tuple(sorted(each for each in stems if PAGE_NAME_RE.fullmatch(each)))
    misnamed = sorted(
        f"{each}{_PAGE_SUFFIX}" for each in stems if not PAGE_NAME_RE.fullmatch(each)
    )
    return pages, tuple(_name_problem(name[: -len(_PAGE_SUFFIX)]) for name in misnamed)


def has_dashboards(data_root: Path) -> bool:
    """True when ``dashboards/`` is unusable (a link, say) or holds a markdown page.

    The generated ``AGENTS.md`` is not counted: ``list_markdown`` leaves it out.
    """
    return location_refusal(data_root) is not None or bool(list_markdown(data_root))


@dataclass(frozen=True)
class _Analysis:
    scan: PageScan
    charts: tuple[PlannedChart, ...]
    notices: tuple[Problem, ...]


def _trusted_id(parsed: Directive | tuple[Problem, ...] | None) -> str | None:
    if parsed is None:
        return None
    if isinstance(parsed, Directive):
        return parsed.chart_id
    return next((each.chart for each in parsed if each.chart is not None), None)


def _analyse(page: str, text: str) -> _Analysis:
    scan = scan_page(text, page=page)
    parsed: list[Directive | tuple[Problem, ...] | None] = []
    for block in scan.directives:
        if block.body is None:
            parsed.append(None)
        else:
            parsed.append(
                parse_directive(block.body, open_line=block.open_line, page=page)
            )
    trusted = [_trusted_id(each) for each in parsed]

    opened_at: dict[str, list[int]] = {}
    for block, tid in zip(scan.directives, trusted, strict=True):
        if tid is not None:
            opened_at.setdefault(tid, []).append(block.open_line)

    following: list[RegionBlock | None] = [
        following_region(scan, block) for block in scan.directives
    ]
    # Regions that sit directly below a directive with their own id.
    owned = {
        region.begin_line
        for tid, region in zip(trusted, following, strict=True)
        if tid is not None and region is not None and region.chart_id == tid
    }
    claimed = {region.begin_line for region in following if region is not None}

    charts: list[PlannedChart] = []
    for block, each, tid, region in zip(
        scan.directives, parsed, trusted, following, strict=True
    ):
        problems = _directive_problems(page, block, each, tid, opened_at)
        own_region: RegionBlock | None = None
        if tid is not None:
            if region is not None and region.chart_id != tid:
                problems.append(_mismatch(page, tid, region))
            elif region is not None:
                own_region = region
                if region.end_line is None:
                    problems.append(
                        _region_contents(page, tid, region, region.intruder_line)
                        if region.intruder_line is not None
                        else _unclosed_region(page, tid, region)
                    )
            problems.extend(
                _misplaced(page, tid, other)
                for other in scan.regions
                if other.chart_id == tid and other.begin_line not in owned
            )
        problems.sort(key=lambda found: found.line if found.line is not None else 0)
        charts.append(
            PlannedChart(
                chart=tid,
                line=block.open_line,
                close_line=block.close_line,
                directive=each if isinstance(each, Directive) else None,
                region=own_region,
                need=None,
                snapshot=None,
                problems=tuple(problems),
            )
        )

    known = {each for each in trusted if each is not None}
    notices = tuple(
        _orphan(page, region)
        for region in scan.regions
        if region.begin_line not in claimed and region.chart_id not in known
    )
    return _Analysis(scan, tuple(charts), notices)


def _directive_problems(
    page: str,
    block: DirectiveBlock,
    parsed: Directive | tuple[Problem, ...] | None,
    trusted: str | None,
    opened_at: dict[str, list[int]],
) -> list[Problem]:
    problems: list[Problem] = []
    if parsed is None:
        problems.append(_unclosed_directive(page, block.open_line))
        return problems
    if block.terminator_line is not None:
        problems.append(_terminator(page, trusted, block.terminator_line))
    if not isinstance(parsed, Directive):
        problems.extend(parsed)
    if trusted is not None and len(opened_at[trusted]) > 1:
        problems.append(
            _duplicate_id(page, trusted, block.open_line, opened_at[trusted])
        )
    return problems


# -- targets -------------------------------------------------------------------


def _parse_target(raw: str) -> Target:
    pieces = raw.split(":")
    if len(pieces) > 2 or not all(pieces):
        raise TargetError(
            f"invalid target {raw!r}: a target is a page name or PAGE:CHART"
        )
    return Target(pieces[0], pieces[1] if len(pieces) == 2 else None)


def _unknown_page(name: str, pages: Sequence[str]) -> TargetError:
    if not pages:
        return TargetError(f"unknown page {name!r}: there are no dashboard pages")
    return TargetError(f"unknown page {name!r}: the pages are {', '.join(pages)}")


def _unknown_chart(page: str, name: str, ids: Sequence[str]) -> TargetError:
    if not ids:
        return TargetError(f"unknown chart {name!r}: page {page!r} has no charts")
    return TargetError(
        f"unknown chart {name!r} on page {page!r}: the charts are {', '.join(ids)}"
    )


def _chart_ids(charts: Sequence[PlannedChart]) -> list[str]:
    ids: list[str] = []
    for each in charts:
        if each.chart is not None and each.chart not in ids:
            ids.append(each.chart)
    return ids


def _check_charts(
    page: str, analysis: _Analysis, wanted: frozenset[str] | None
) -> None:
    if wanted is None:
        return
    ids = _chart_ids(analysis.charts)
    for name in sorted(wanted):
        if name not in ids:
            raise _unknown_chart(page, name, ids)


def resolve_targets(data_root: Path, raw: Sequence[str]) -> tuple[Target, ...]:
    """Targets from ``page`` / ``page:chart`` text, sorted, without duplicates.

    A page target covers the page's chart targets, which are dropped. An
    unknown page or an unknown chart raises ``TargetError``; a chart target on a
    page that cannot be read is accepted, and the run reports the page.
    """
    targets = {_parse_target(each) for each in raw}
    whole = {each.page for each in targets if each.chart is None}
    targets = {each for each in targets if each.chart is None or each.page not in whole}
    if location_refusal(data_root) is not None:
        return _ordered(targets)  # the run reports the location; no page to check
    pages, _misnamed = _list_pages(data_root)
    for page in sorted({each.page for each in targets}):
        if page not in pages:
            raise _unknown_page(page, pages)
    for page in sorted({each.page for each in targets if each.chart is not None}):
        read = read_page(data_root, page)
        if isinstance(read, Refusal):
            continue
        wanted = frozenset(
            each.chart for each in targets if each.page == page and each.chart
        )
        _check_charts(page, _analyse(page, read.text), wanted)
    return _ordered(targets)


def _ordered(targets: set[Target]) -> tuple[Target, ...]:
    return tuple(sorted(targets, key=lambda each: (each.page, each.chart or "")))


# -- planning ------------------------------------------------------------------


def _wanted(targets: Sequence[Target]) -> dict[str, frozenset[str] | None]:
    """Per targeted page: ``None`` for every chart, else the targeted chart ids."""
    out: dict[str, frozenset[str] | None] = {}
    for each in targets:
        if each.chart is None:
            out[each.page] = None
        elif each.page not in out:
            out[each.page] = frozenset({each.chart})
        elif (current := out[each.page]) is not None:
            out[each.page] = current | {each.chart}
    return out


def _recorded_for(region: RegionBlock | None) -> str | None:
    """The snapshot path the region records, as written.

    A path naming another page or chart is honoured: a renamed page or chart
    keeps pointing at the snapshot it was drawn from.
    """
    if region is None:
        return None
    return recorded_snapshot(region.body)


def _plan_data(
    request: RunRequest, page: str, planned: PlannedChart, *, explicit: bool
) -> PlannedChart:
    """Decide what data the chart needs; ``explicit``: a chart target names it.

    Under ``FREEZE`` a relative chart reached only through a page target is not
    a freeze target: it is left alone, with no data need and no problem.
    """
    directive = planned.directive
    if planned.problems or directive is None:
        return planned
    if directive.mode is Mode.RELATIVE:
        if request.action is Action.FREEZE:
            if explicit:
                return replace(planned, problems=(_freeze_relative(page, planned),))
            return planned
        return replace(planned, need=DataNeed.FETCH)
    if request.action is Action.FREEZE:
        return replace(planned, need=DataNeed.FETCH)
    recorded = _recorded_for(planned.region)
    if recorded is not None:
        return replace(planned, need=DataNeed.RECORDED, snapshot=recorded)
    latest = latest_snapshot(request.data_root, page, directive.chart_id)
    if latest is not None:
        return replace(planned, need=DataNeed.LATEST, snapshot=latest)
    return replace(planned, need=DataNeed.FETCH)


def plan_run(request: RunRequest) -> RunPlan:
    """Discover, read, scan and plan every targeted page; nothing is written."""
    refusal = location_refusal(request.data_root)
    if refusal is not None:
        return RunPlan((_location_problem(refusal),), ())
    pages, misnamed = _list_pages(request.data_root)
    wanted = _wanted(request.targets)
    for name in sorted(wanted):
        if name not in pages:
            raise _unknown_page(name, pages)
    names = [each for each in pages if not wanted or each in wanted]
    planned: list[PlannedPage] = []
    for name in names:
        read = read_page(request.data_root, name)
        if isinstance(read, Refusal):
            planned.append(
                PlannedPage(name, None, None, (_read_problem(name, read),), (), ())
            )
            continue
        analysis = _analyse(name, read.text)
        want = wanted.get(name) if wanted else None
        _check_charts(name, analysis, want)
        charts = tuple(
            _plan_data(request, name, each, explicit=want is not None)
            for each in analysis.charts
            if want is None or each.chart in want
        )
        planned.append(
            PlannedPage(
                name,
                read,
                analysis.scan,
                analysis.scan.problems,
                analysis.notices,
                charts,
            )
        )
    return RunPlan(() if wanted else misnamed, tuple(planned))


# -- the run -------------------------------------------------------------------


def _chart_result(planned: PlannedChart) -> ChartResult:
    directive = planned.directive
    return ChartResult(
        chart=planned.chart,
        line=planned.line,
        kind=directive.kind if directive is not None else None,
        mode=directive.mode.value if directive is not None else None,
        outcome=Outcome.FAILED if planned.problems else Outcome.CHECKED,
        snapshot=planned.snapshot,
        problems=planned.problems,
        notices=(),
    )


def _needs_fetch(planned: PlannedChart) -> bool:
    """True for a chart the plan sends to the source.

    ``need`` is ``None`` for a chart with a planning problem, so those are never
    queried.
    """
    return planned.directive is not None and planned.need is DataNeed.FETCH


def _unavailable_problem(
    unavailable: SourceUnavailable,
    *,
    page: str | None,
    chart: str | None,
    line: int | None,
) -> Problem:
    return dashboard_problem(
        DashboardCode.INDEX_UNAVAILABLE,
        f"The chart was not queried: {unavailable.message}",
        unavailable.fix,
        page=page,
        chart=chart,
        line=line,
    )


def _write_failed(
    page: str, chart: str, line: int, what: str, error: OSError
) -> Problem:
    reason = " ".join(str(error).split()).rstrip(".")
    return dashboard_problem(
        DashboardCode.WRITE_FAILED,
        f"The {what} could not be written: {reason}.",
        "Check that dashboards/ is writable and run the command again.",
        page=page,
        chart=chart,
        line=line,
    )


def _asset_foreign(page: str, chart: str, line: int) -> Problem:
    path = asset_rel_path(page, chart)
    return dashboard_problem(
        DashboardCode.ASSET_FOREIGN,
        f"The image path dashboards/{path} is occupied by something fitdocs did "
        "not write, or sits below a link.",
        f"Move or delete whatever is at dashboards/{path}, then run the command again.",
        page=page,
        chart=chart,
        line=line,
    )


def _page_changed(page: str, chart: str, line: int) -> Problem:
    return dashboard_problem(
        DashboardCode.PAGE_CHANGED,
        f"The page {page} changed while fitdocs was working, so it was left unchanged.",
        "Run the command again.",
        page=page,
        chart=chart,
        line=line,
    )


def _freeze_command(page: str, chart: str) -> str:
    return f"`fitdocs dashboard freeze {page}:{chart}`"


def _snapshot_missing(page: str, planned: PlannedChart, path: str) -> Problem:
    assert planned.chart is not None
    return dashboard_problem(
        DashboardCode.SNAPSHOT_MISSING,
        f"The snapshot dashboards/{path} is missing or cannot be read.",
        "Restore that file, or run "
        f"{_freeze_command(page, planned.chart)} to take a new snapshot.",
        page=page,
        chart=planned.chart,
        line=planned.line,
    )


def _snapshot_unreadable(
    page: str, planned: PlannedChart, path: str, error: SnapshotFormatError
) -> Problem:
    assert planned.chart is not None
    detail = " ".join(str(error).split()).rstrip(".")
    return dashboard_problem(
        DashboardCode.SNAPSHOT_UNREADABLE,
        f"The snapshot dashboards/{path} cannot be used: {detail}.",
        "Restore that file from a backup, or run "
        f"{_freeze_command(page, planned.chart)} to take a new snapshot.",
        page=page,
        chart=planned.chart,
        line=planned.line,
    )


def _sql_changed(page: str, planned: PlannedChart, path: str) -> Problem:
    assert planned.chart is not None
    return dashboard_problem(
        DashboardCode.SQL_CHANGED,
        f"The SQL changed after the snapshot dashboards/{path} was taken, so the "
        "chart is still drawn from that snapshot.",
        f"Run {_freeze_command(page, planned.chart)} to take a new snapshot with "
        "the current SQL.",
        page=page,
        chart=planned.chart,
        line=planned.line,
    )


def _unstorable(
    page: str, planned: PlannedChart, column: Column, error: ValueError
) -> Problem:
    assert planned.chart is not None
    detail = " ".join(str(error).split()).rstrip(".")
    return dashboard_problem(
        DashboardCode.WRITE_FAILED,
        f"The result was not stored as a snapshot because the {column.kind.value} "
        f"column `{column.name}` holds a value that cannot be stored ({detail}).",
        "Exclude or cast the non-finite values in the SQL.",
        page=page,
        chart=planned.chart,
        line=planned.line,
        column=column.name,
    )


@dataclass(frozen=True)
class _Drawn:
    chart: RenderedChart
    rows_table: RenderedChart | None


def _kit_problems(
    error: ChartError, page: str, planned: PlannedChart, option: str | None
) -> list[Problem]:
    assert planned.chart is not None
    return [
        from_chart_problem(
            each, page=page, chart=planned.chart, line=planned.line, option=option
        )
        for each in error.problems
    ]


def _draw(
    page: str, planned: PlannedChart, directive: Directive, data: ChartData
) -> _Drawn | list[Problem]:
    """The chart and, for ``show_rows``, its rows table; or every kit problem.

    The chart and the table are both attempted, so a directive whose chart and
    table are both refused reports both, the chart's problems first.
    """
    ref = f"{page}:{directive.chart_id}"
    problems: list[Problem] = []
    chart: RenderedChart | None = None
    try:
        chart = render_chart(
            ChartRequest(
                ref,
                directive.kind,
                directive.title,
                directive.channels,
                directive.options,
            ),
            data,
        )
    except ChartError as error:
        problems.extend(_kit_problems(error, page, planned, None))
    table: RenderedChart | None = None
    if directive.show_rows:
        try:
            table = render_chart(ChartRequest(ref, _TABLE_KIND, directive.title), data)
        except ChartError as error:
            problems.extend(_kit_problems(error, page, planned, _SHOW_ROWS))
    if problems or chart is None:
        return problems
    return _Drawn(chart, table)


@dataclass
class _Pending:
    """One planned chart while its page is being handled."""

    planned: PlannedChart
    problems: list[Problem]
    notices: list[Problem] = field(default_factory=list)
    data: ChartData | None = None  # the rows the chart is drawn from
    stamp: date | None = None  # the snapshot date a frozen chart's caption states
    fresh: Snapshot | None = None  # a snapshot to create when the run writes
    snapshot: str | None = None  # the snapshot path the report names
    drawn: _Drawn | None = None
    body: ChartBody | None = None
    edit: RegionEdit | None = None
    asset: str = "none"  # "none" | "written" | "unchanged"


def _failure_body(
    planned: PlannedChart, problems: Sequence[Problem]
) -> ChartBody | None:
    """The note a never-rendered chart gets; ``None`` keeps a rendered region (12.2)."""
    assert problems, "a chart that is not drawn has a problem to state"
    region = planned.region
    if region is not None and classify_body(region.body) is BodyState.RENDERED:
        return None
    return note_body(problems[0].message)


def _edit_for(planned: PlannedChart, body: ChartBody) -> RegionEdit | None:
    """The edit that makes the chart's region hold ``body``; ``None`` if it does."""
    assert planned.chart is not None and planned.close_line is not None
    region = planned.region
    if region is not None and tuple(each.text for each in region.body) == body.lines:
        return None
    return RegionEdit(planned.chart, body, region, planned.close_line)


def _with_units(data: ChartData) -> ChartData:
    """The columns with the unit their names carry: stored columns hold no unit."""
    columns = tuple(
        Column(
            each.name,
            each.kind,
            unit.token if (unit := unit_for_column(each.name)) else None,
        )
        for each in data.columns
    )
    return ChartData(columns, data.rows)


def _storable(page: str, planned: PlannedChart, snapshot: Snapshot) -> bytes | Problem:
    """The snapshot's bytes, or the problem naming the column that cannot be stored."""
    try:
        return encode(snapshot)
    except ValueError:
        columns = snapshot.data.columns
        for index, column in enumerate(columns):
            alone = replace(
                snapshot,
                data=ChartData(
                    (column,), tuple((row[index],) for row in snapshot.data.rows)
                ),
            )
            try:
                encode(alone)
            except ValueError as found:
                return _unstorable(page, planned, column, found)
        raise  # no single column explains it: a defect, not a chart failure


def _freeze(
    request: RunRequest,
    page: PlannedPage,
    planned: PlannedChart,
    directive: Directive,
    data: ChartData,
    pending: _Pending,
) -> None:
    """Encode the fetched rows and draw from what decodes: the stored rows (10.9)."""
    assert planned.chart is not None
    snapshot = Snapshot(
        page=page.name,
        chart=planned.chart,
        generation=1,
        today=request.today,
        sql=directive.sql,
        sql_sha256=directive.sql_sha256,
        data=data,
    )
    raw = _storable(page.name, planned, snapshot)
    if isinstance(raw, Problem):
        pending.problems.append(raw)
        return
    stored = decode(raw)
    pending.fresh = snapshot
    pending.data = _with_units(stored.data)
    pending.stamp = stored.today


def _fetch(
    request: RunRequest,
    page: PlannedPage,
    planned: PlannedChart,
    directive: Directive,
    source: ChartSource | None,
    unavailable: SourceUnavailable | None,
    pending: _Pending,
) -> None:
    assert planned.chart is not None
    if source is None:
        assert unavailable is not None
        pending.problems.append(
            _unavailable_problem(
                unavailable, page=page.name, chart=planned.chart, line=planned.line
            )
        )
        return
    fetched = source.fetch(
        directive.sql,
        today=request.today,
        page=page.name,
        chart=planned.chart,
        line=planned.line,
    )
    if not isinstance(fetched, Fetched):
        pending.problems.extend(fetched)
    elif directive.mode is Mode.FROZEN:
        _freeze(request, page, planned, directive, fetched.data, pending)
    else:
        pending.data = fetched.data


def _load(
    request: RunRequest,
    page: PlannedPage,
    planned: PlannedChart,
    directive: Directive,
    pending: _Pending,
) -> None:
    """Take a frozen chart's rows from the snapshot the plan chose."""
    path = planned.snapshot
    assert path is not None
    raw = read_snapshot(request.data_root, path)
    if raw is None:
        pending.problems.append(_snapshot_missing(page.name, planned, path))
        return
    try:
        stored = decode(raw)
    except SnapshotFormatError as error:
        pending.problems.append(_snapshot_unreadable(page.name, planned, path, error))
        return
    if stored.sql_sha256 != directive.sql_sha256:
        pending.notices.append(_sql_changed(page.name, planned, path))
    pending.data = _with_units(stored.data)
    pending.stamp = stored.today


def _compose(
    page: str, pending: _Pending, directive: Directive, snapshot_path: str | None
) -> ChartBody:
    drawn, data = pending.drawn, pending.data
    assert drawn is not None and data is not None and pending.planned.chart is not None
    return chart_body(
        page=page,
        chart_id=pending.planned.chart,
        title=directive.title,
        rendered=drawn.chart,
        caption=caption(data, window=directive.window, snapshot_date=pending.stamp),
        rows_table=drawn.rows_table,
        snapshot_path=snapshot_path,
    )


def _settle(
    request: RunRequest,
    page: PlannedPage,
    planned: PlannedChart,
    source: ChartSource | None,
    unavailable: SourceUnavailable | None,
) -> _Pending:
    """Fetch or load, draw and compose one chart in memory; nothing is written.

    A chart that is freshly frozen has no body yet: its region records the
    snapshot, whose path is known only once the snapshot is created.
    """
    directive = planned.directive
    assert directive is not None and planned.chart is not None
    pending = _Pending(planned, [], snapshot=planned.snapshot)
    if planned.need is DataNeed.FETCH:
        _fetch(request, page, planned, directive, source, unavailable, pending)
    else:
        _load(request, page, planned, directive, pending)
    if pending.data is not None:
        drawn = _draw(page.name, planned, directive, pending.data)
        if isinstance(drawn, _Drawn):
            pending.drawn = drawn
            if pending.fresh is None:
                pending.body = _compose(page.name, pending, directive, planned.snapshot)
        else:
            pending.problems.extend(drawn)
            pending.fresh = None
    # An explicit freeze that fails changes nothing, not even a note (11.3).
    if (
        pending.body is None
        and pending.problems
        and request.action is not Action.FREEZE
    ):
        pending.body = _failure_body(planned, pending.problems)
    if pending.body is not None:
        pending.edit = _edit_for(planned, pending.body)
    return pending


def _encode_generation(snapshot: Snapshot, generation: int) -> bytes:
    return encode(replace(snapshot, generation=generation))


def _write_snapshots(
    request: RunRequest, page: PlannedPage, pending: Sequence[_Pending]
) -> None:
    """Create each fresh snapshot, then compose the body that records it."""
    for each in pending:
        fresh = each.fresh
        if fresh is None:
            continue
        planned = each.planned
        directive = planned.directive
        assert planned.chart is not None and directive is not None
        try:
            path = create_snapshot(
                request.data_root,
                page.name,
                planned.chart,
                partial(_encode_generation, fresh),
            )
        except OSError as error:
            each.problems.append(
                _write_failed(page.name, planned.chart, planned.line, "snapshot", error)
            )
            continue
        each.snapshot = path
        each.body = _compose(page.name, each, directive, path)
        each.edit = _edit_for(planned, each.body)


def _write_assets(
    request: RunRequest, page: PlannedPage, pending: Sequence[_Pending]
) -> None:
    for each in pending:
        if (
            each.drawn is None
            or each.problems
            or each.drawn.chart.output is not Output.SVG
        ):
            continue
        planned = each.planned
        assert planned.chart is not None
        try:
            state = write_asset(
                request.data_root, page.name, planned.chart, each.drawn.chart.text
            )
        except OSError as error:
            each.problems.append(
                _write_failed(page.name, planned.chart, planned.line, "image", error)
            )
            each.edit = None
            continue
        if state == "foreign":
            each.problems.append(_asset_foreign(page.name, planned.chart, planned.line))
            each.edit = None
        else:
            each.asset = state


def _replace_page(page: PlannedPage, pending: Sequence[_Pending]) -> bool:
    """Apply the surviving edits in one replacement; True when the page was written."""
    edited = [each for each in pending if each.edit is not None]
    if not edited or page.file is None or page.scan is None:
        return False
    edits = [each.edit for each in edited if each.edit is not None]
    text = apply_edits(page.scan.lines, edits)
    try:
        state = replace_page(page.file, text)
    except OSError as error:
        for each in edited:
            assert each.planned.chart is not None
            each.problems.append(
                _write_failed(
                    page.name, each.planned.chart, each.planned.line, "page", error
                )
            )
        return False
    if state == "changed":
        for each in edited:
            assert each.planned.chart is not None
            each.problems.append(
                _page_changed(page.name, each.planned.chart, each.planned.line)
            )
        return False
    return True


def _outcome(each: _Pending, action: Action, page_written: bool) -> Outcome:
    if each.problems:
        return Outcome.FAILED
    if action is Action.CHECK:
        return Outcome.CHECKED
    if each.asset == "written" or (each.edit is not None and page_written):
        return Outcome.RENDERED
    return Outcome.UNCHANGED


def _run_page(
    request: RunRequest,
    page: PlannedPage,
    source: ChartSource | None,
    unavailable: SourceUnavailable | None,
) -> PageResult:
    slots: list[_Pending | PlannedChart] = [
        _settle(request, page, each, source, unavailable)
        if each.directive is not None and each.need is not None
        else each
        for each in page.charts
    ]
    pending = [each for each in slots if isinstance(each, _Pending)]
    written = False
    if request.action is not Action.CHECK:
        _write_snapshots(request, page, pending)
        _write_assets(request, page, pending)
        written = _replace_page(page, pending)
    charts: list[ChartResult] = []
    for each in slots:
        if not isinstance(each, _Pending):
            charts.append(_chart_result(each))
            continue
        planned = each.planned
        directive = planned.directive
        assert directive is not None
        charts.append(
            ChartResult(
                chart=planned.chart,
                line=planned.line,
                kind=directive.kind,
                mode=directive.mode.value,
                outcome=_outcome(each, request.action, written),
                snapshot=each.snapshot,
                problems=tuple(each.problems),
                notices=tuple(each.notices),
            )
        )
    return PageResult(
        page=page.name,
        written=written,
        problems=page.problems,
        notices=page.notices,
        charts=tuple(charts),
    )


def run_dashboards(request: RunRequest, open_source: SourceOpener) -> RunReport:
    """Plan, then draw and write every targeted chart, and clean up the images.

    The source is opened once, after every page is planned and before anything
    is rendered or written, and only when some chart needs a query; it is closed
    in ``finally``. After the pages, a ``REFRESH`` or ``FREEZE`` run removes the
    marked images no page links; a ``CHECK`` run writes and removes nothing.
    """
    plan = plan_run(request)
    needs_query = any(
        _needs_fetch(chart) for page in plan.pages for chart in page.charts
    )
    index = "not_needed"
    index_problem: Problem | None = None
    source: ChartSource | None = None
    unavailable: SourceUnavailable | None = None
    try:
        if needs_query:
            opened = open_source()
            if isinstance(opened, SourceUnavailable):
                unavailable = opened
                index = opened.state
                index_problem = _unavailable_problem(
                    opened, page=None, chart=None, line=None
                )
            else:
                source = opened
                index = "ready"
        pages = tuple(
            _run_page(request, each, source, unavailable) for each in plan.pages
        )
    finally:
        if source is not None:
            source.close()
    removed: tuple[str, ...] = ()
    if request.action is not Action.CHECK:
        removed = remove_stale_images(request.data_root) or ()
    return RunReport(
        action=request.action,
        index=index,
        index_problem=index_problem,
        location_problems=plan.location_problems,
        pages=pages,
        removed=removed,
    )
