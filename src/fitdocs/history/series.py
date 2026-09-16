"""Pure computation from scanned pages to the daily series, the weekly
table, coverage and the criterion-point report (load-history spec). See the
"SeriesAssembly (`src/fitdocs/history/series.py`)" component in
`.kiro/specs/load-history/design.md`.

This module is created by task 3.2 and extended by 3.3, 3.4 and 3.5 in that
order; each task adds only its own functions. Task 3.2 adds methodology
resolution and the partition it drives (Req 4.1-4.6):

- `select_methodology` is the pure selection rule: an explicitly requested
  methodology beats a configured one, which beats a single methodology
  observed across the archive. More than one methodology observed with
  nothing requested or configured, and a requested or configured identifier
  no page records, each yield a `MethodologyProblem` -- never a guess and
  never a silent majority ("never a guess" is design.md's wording; "never a
  silent majority" is tasks.md's). The case of nothing
  requested, nothing configured, and *no* methodology observed at all (an
  archive of unscored pages only) is governed by Req 1.10 -- "complete
  without reporting a failure" -- which `HistoryEngine` (task 5.2) satisfies
  by gating on "no page records a load" *before* calling this function, so
  this function's own empty-counts branch is never the engine's path to a
  configuration exit. It still returns a `MethodologyProblem` here,
  defensively: there is no id available to report as chosen under any of the
  three `MethodologyChoice.source` values, and a fabricated choice would be
  worse than an unreachable-in-practice problem.
- `partition_pages` splits the archive by the chosen methodology: a page
  recording the chosen methodology, and a page recording no load at all,
  are included; any page recording a different methodology is excluded.

Task 3.3 adds the contiguous daily series (Req 1.4-1.8):

- `DayLoad` is one calendar date's own record: the load actually recorded,
  and the page counts (`pages`, `pages_with_load`) that qualify it, so no
  consumer can read `recorded_load` as a complete total without also reading
  how many pages that date has and how many of them are known. `unknown_pages`
  and `is_complete` are derived views over those two counts.
- `build_daily_series` spans the earliest to the latest *contributing* page
  date inclusive -- a page contributes when it records a load, which for the
  included partition this function receives means `page.load is not None`
  (every load present in that partition is already under the chosen
  methodology; see `partition_pages`) -- with one `DayLoad` per calendar date
  and none omitted. An included page whose date falls outside that span (a
  page recorded before the first contributing page, or after the last) is
  simply not folded into any `DayLoad`; its `PageRecord` is still present, by
  construction, in the caller's own `pages` sequence, so nothing is dropped,
  only left for a later pass (Req 1.8, 3.10) to report by date-comparison
  against `DailySeries.start`/`.end`. Returns `None` iff no page in `pages`
  records a load (Req 1.10's empty-archive case, gated one level up by
  `HistoryEngine`, not re-guessed here).

No module in this package names a clock function, imports a YAML parser, or
spells the forbidden reference-docs path (package-wide rules the constant
guard checks independently). Task 3.2's own code holds no bare numeric
literal at all. Task 3.3 introduces three bare numeric literals, each
exempted at its own site in `tests/history/test_constant_guard.py`:

- `_ONE_DAY = timedelta(days=1)` below -- the daily series' own step size.
- `DailySeries.end`'s own `self.days[-1].day` -- the `-1` last-element
  index into the `days` tuple.
- `build_daily_series`'s own `sum(loaded, 0.0)` -- the `0.0` start value
  that keeps `DayLoad.recorded_load` a `float` even on a rest day, when
  `loaded` is empty and `sum` would otherwise default to `int 0`.

None of the three is a value any source cites -- each is a structural
detail of how this module walks or sums, not a methodological choice.

Task 3.4 adds the weekly aggregation, the coverage measure and the
suppression rule (Req 3.1-3.3, 3.5, 3.6, 3.10, 5.6):

- `Coverage` is `pages_with_load / pages`, `1.0` when `pages == 0` (an empty
  period is complete -- nothing is missing from it, Req 3.6), reported once
  per calendar year and once for the whole archive by `coverage_report`. A
  period row's excluded counts come from the excluded `PageRecord`s
  themselves, grouped by their own dates (an excluded page has a date; the
  methodology choice's own archive-wide totals do not), so the per-year
  split can differ from the archive-wide one. A skipped document has no date
  to attribute by, so `pages_skipped` is an integer on the archive-wide row
  only and `None` on every period row (Req 3.10).
- `suppressed_weeks` and `week_rows` walk `series.days` grouped by ISO
  `(year, week)` -- `date.isocalendar()`, never `date.year`, because an ISO
  week can straddle a calendar-year boundary. A week whose coverage is
  *strictly* below `threshold` is suppressed: its `WeekRow` carries
  `suppressed=True` and `None` for `fitness`/`fatigue`/`form`. Both
  functions take an already-computed `ModelSeries` (`week_rows`) or nothing
  at all (`suppressed_weeks` needs only the day counts) -- neither ever
  calls `run_model`; suppression is a reporting decision applied to values
  the recursion already produced over the whole, unsuppressed span (Req
  3.7), never a re-run confined to one week.

Task 3.4 introduces two further bare numeric literals, each exempted at its
own site in `tests/history/test_constant_guard.py`:

- `_last_index`'s own `indices[-1]` -- the same structural last-element
  offset as `DailySeries.end`'s `self.days[-1]` above, a second occurrence
  of that module's `(None, None, 1)` site.
- `week_rows`'s own `date.fromisocalendar(iso_year, iso_week, 1)` -- ISO
  weekday `1` is Monday by the calendar's own definition, not a value any
  source cites.

Task 3.5 adds the criterion-point count (Req 6.1-6.3):

- `criterion_points` walks the *scanned* pages (not the included/excluded
  partition `select_methodology`/`partition_pages` produce -- a criterion
  point is a fact about the tag, independent of which load methodology the
  page's load, if any, was recorded under), and classifies every tagged page
  exactly once: a malformed tag (`page.tag_problem is not None`) is named
  individually by its own path and the reader's own `describe()` string in
  `malformed`; a well-formed `hard` tag, and a well-formed `race`/`test` tag
  recording no `time_s`, are each counted into one of `excluded`'s two
  reason groups; a well-formed `race`/`test` tag recording a `time_s` is a
  criterion point, tallied into `by_kind` and folded into `earliest`/
  `latest`. An untagged page (`page.effort is None` and `page.tag_problem is
  None`) contributes to none of the four. `by_kind` lists only the kinds
  actually observed, in `EffortKind`'s own declaration order (`RACE`, then
  `TEST`) -- never by count, and never alphabetically, which happens to
  coincide with declaration order here (`"race" < "test"`), and is exactly
  why the test fixture that pins this ties the two kinds' counts (RACE and
  TEST both counted twice) with a TEST page counted first, so insertion
  order, ascending count and descending count each pick a different, wrong
  ordering than the declaration order this function actually returns.
  `excluded`'s two reason groups are sorted by their own reason text, and
  only a group that is actually non-empty appears, the same convention
  `MethodologyChoice.excluded` and `Coverage.pages_excluded` already use
  elsewhere in this module. This task introduces four bare numeric
  literals, each exempted at its own site in
  `tests/history/test_constant_guard.py`: the three `+= 1` tally
  increments (`reason_counts[_HARD_REASON]`, `reason_counts[_NO_TIME_REASON]`
  and `kind_counts[tag.kind]`), and `by_kind`'s own `kind_counts[kind] > 0`
  non-empty-count guard.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Protocol, TypeVar

from fitdocs.contract import EffortKind
from fitdocs.history.documents import PageRecord
from fitdocs.history.model import ModelSeries

__all__ = [
    "Coverage",
    "CriterionPoints",
    "DailySeries",
    "DayLoad",
    "MethodologyChoice",
    "MethodologyProblem",
    "MethodologyRecord",
    "WeekRow",
    "build_daily_series",
    "coverage_report",
    "criterion_points",
    "partition_pages",
    "select_methodology",
    "suppressed_weeks",
    "week_rows",
]

#: One calendar day -- the daily series' own step size (Req 1.6), not a
#: value any source cites. Declared once here so its constant-guard
#: exemption attaches to this single site, not to a literal repeated at
#: every use.
_ONE_DAY = timedelta(days=1)


class MethodologyRecord(Protocol):
    """Any record that carries a methodology -- the structural type the two
    published methodology helpers take, so a caller outside this package
    (e.g. `plans.aggregate`'s `LoggedWorkout`) can run them without
    building a `PageRecord` (Req 6.2).

    `PageRecord` already satisfies this structurally; nothing about it
    changes here.
    """

    @property
    def methodology(self) -> str | None: ...


_R = TypeVar("_R", bound=MethodologyRecord)


@dataclass(frozen=True)
class MethodologyChoice:
    """The one methodology a run's series is summed under, and how it was
    chosen (Req 4.1-4.3, 4.6).

    `source` names which of the three inputs produced `methodology`, so the
    page can say the methodology was inferred rather than configured (Req
    4.3). `excluded` is every *other* observed methodology and its page
    count, sorted by methodology name so the report renders identically
    every run (Req 4.6) -- the same information `partition_pages` uses to
    build the actual excluded `PageRecord`s.
    """

    methodology: str
    source: Literal["requested", "configured", "inferred"]
    excluded: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class MethodologyProblem:
    """The archive's pages do not resolve to one methodology (Req 4.4, 4.5).

    `detail` names every methodology found with its page count and the
    action that resolves the problem -- never a guess, never a silent
    majority.
    """

    detail: str


def _observed_counts(pages: Sequence[MethodologyRecord]) -> Counter[str]:
    """How many pages record each methodology, over pages that record a
    load at all (`PageRecord.methodology is not None`, the 3.1 invariant
    that `load is None` iff `methodology is None`)."""
    return Counter(page.methodology for page in pages if page.methodology is not None)


def _methodology_list(counts: Counter[str]) -> str:
    """Every observed methodology and its page count, sorted by name, in
    the fixed prose form every `MethodologyProblem.detail` embeds."""
    return ", ".join(
        f"{name!r} ({count} pages)" for name, count in sorted(counts.items())
    )


def _excluded(counts: Counter[str], chosen: str) -> tuple[tuple[str, int], ...]:
    """Every observed methodology other than `chosen`, sorted by name."""
    return tuple(
        (name, count) for name, count in sorted(counts.items()) if name != chosen
    )


def _present_clause(counts: Counter[str]) -> str:
    """The clause naming what is actually present, kept coherent when
    `counts` is empty: `_methodology_list` on an empty `Counter` renders as
    an empty string, so "methodologies present: ." is never emitted -- an
    archive that records no methodology at all says so plainly instead."""
    if not counts:
        return "no page in the archive records a methodology"
    return f"methodologies present: {_methodology_list(counts)}"


def select_methodology(
    pages: Sequence[MethodologyRecord],
    *,
    requested: str | None,
    configured: str | None,
) -> MethodologyChoice | MethodologyProblem:
    """Resolve the one methodology the series is summed under (Req 4.1-4.5).

    Precedence: `requested` beats `configured` beats a single methodology
    observed across `pages`. A `requested` or `configured` identifier that
    no page records is a `MethodologyProblem` naming every methodology
    actually present and its count (Req 4.5) -- resolved before the
    observed-archive rule even runs, because a caller-supplied identifier
    that matches no page is wrong regardless of what else the archive
    contains. More than one methodology observed with neither `requested`
    nor `configured` set is also a `MethodologyProblem` (Req 4.4). The
    degenerate case of none observed at all is governed by Req 1.10, which
    `HistoryEngine` gates before ever calling this function; this branch
    returns a `MethodologyProblem` only defensively, since there is no
    candidate id to report as `MethodologyChoice.source="inferred"`.
    """
    counts = _observed_counts(pages)

    if requested is not None:
        if requested not in counts:
            action = (
                (
                    "Choose one of the present methodologies, or record loads "
                    f"under {requested!r} before requesting it."
                )
                if counts
                else (
                    f"No methodology can be chosen until one is recorded; run "
                    f"`fitdocs load` to record loads, then request {requested!r} "
                    "again."
                )
            )
            return MethodologyProblem(
                f"requested methodology {requested!r} is recorded by no page "
                f"in the archive; {_present_clause(counts)}. {action}"
            )
        return MethodologyChoice(requested, "requested", _excluded(counts, requested))

    if configured is not None:
        if configured not in counts:
            action = (
                (
                    "Update [history].methodology or [load].default_calculator to "
                    "one of the present methodologies, or pass --methodology to "
                    "choose one explicitly."
                )
                if counts
                else (
                    "No methodology can be chosen until one is recorded; run "
                    "`fitdocs load` to record loads under one first."
                )
            )
            return MethodologyProblem(
                f"configured methodology {configured!r} is recorded by no page "
                f"in the archive; {_present_clause(counts)}. {action}"
            )
        return MethodologyChoice(
            configured, "configured", _excluded(counts, configured)
        )

    match sorted(counts):
        case []:
            return MethodologyProblem(
                "no page in the archive records a methodology, and none was "
                "requested or configured. Pass --methodology, set "
                "[history].methodology, or [load].default_calculator once "
                "loads are recorded under one."
            )
        case [only]:
            return MethodologyChoice(only, "inferred", _excluded(counts, only))
        case _:
            return MethodologyProblem(
                "the archive records more than one methodology and none was "
                f"requested or configured: {_methodology_list(counts)}. Pass "
                "--methodology, or set [history].methodology or "
                "[load].default_calculator, to choose one."
            )


def partition_pages(
    pages: Sequence[_R], choice: MethodologyChoice
) -> tuple[tuple[_R, ...], tuple[_R, ...]]:
    """Split `pages` by the chosen methodology (Req 4.1, 4.6).

    A page recording the chosen methodology, and a page recording no load
    at all (`methodology is None`), are *included*. A page recording any
    other methodology is *excluded*. Returns `(included, excluded)`, each in
    the input's own order.
    """
    included = tuple(
        page
        for page in pages
        if page.methodology is None or page.methodology == choice.methodology
    )
    excluded = tuple(
        page
        for page in pages
        if page.methodology is not None and page.methodology != choice.methodology
    )
    return included, excluded


@dataclass(frozen=True)
class DayLoad:
    """One calendar date's own record (Req 1.4, 1.5, 1.7).

    `recorded_load` is the sum over `pages` that date has which record a
    load; `pages` and `pages_with_load` travel with it always, so no
    consumer can read the sum as a complete total without also reading how
    many pages that date has and how many of them are known. A genuine rest
    day (`pages == 0`) and a date whose pages all lack a load
    (`pages_with_load == 0`, `pages > 0`) both record zero load, but are
    distinguishable by these counts, not by convention.
    """

    day: date
    recorded_load: float
    pages: int
    pages_with_load: int

    @property
    def unknown_pages(self) -> int:
        return self.pages - self.pages_with_load

    @property
    def is_complete(self) -> bool:
        return self.pages == self.pages_with_load


@dataclass(frozen=True)
class DailySeries:
    """A contiguous run of `DayLoad`, one per calendar date, spanning the
    earliest to the latest contributing page date inclusive (Req 1.6).

    `days` is never empty: `build_daily_series` returns `None` instead of an
    empty `DailySeries` whenever no page records a load, so `.end`'s own
    `self.days[-1]` is always safe to index."""

    start: date
    days: tuple[DayLoad, ...]

    @property
    def end(self) -> date:
        return self.days[-1].day


def build_daily_series(pages: Sequence[PageRecord]) -> DailySeries | None:
    """Build the contiguous daily series from `pages`, the scan's included
    partition (Req 1.4-1.8).

    Spans the earliest to the latest *contributing* page date inclusive --
    contributing means `page.load is not None`, which for the included
    partition this function receives means the load is already recorded
    under the chosen methodology (`partition_pages`'s own postcondition).
    Every calendar date in that span gets exactly one `DayLoad`, whether or
    not any page falls on it. An included page whose date falls outside the
    span (before the first contributing date, or after the last) is simply
    not folded into any `DayLoad` here -- it remains, unaltered, in the
    caller's own `pages` sequence for a later pass to count by comparing its
    date against `.start`/`.end`, never silently dropped.

    Returns `None` iff no page in `pages` records a load at all (Req 1.10's
    empty-archive case).
    """
    contributing_days = [page.day for page in pages if page.load is not None]
    if not contributing_days:
        return None
    start = min(contributing_days)
    end = max(contributing_days)

    pages_by_day: dict[date, list[PageRecord]] = {}
    for page in pages:
        if start <= page.day <= end:
            pages_by_day.setdefault(page.day, []).append(page)

    days: list[DayLoad] = []
    current = start
    while current <= end:
        day_pages = pages_by_day.get(current, [])
        loaded = [page.load for page in day_pages if page.load is not None]
        days.append(
            DayLoad(
                day=current,
                recorded_load=sum(loaded, 0.0),
                pages=len(day_pages),
                pages_with_load=len(loaded),
            )
        )
        current += _ONE_DAY

    return DailySeries(start=start, days=tuple(days))


def _coverage_fraction(pages: int, pages_with_load: int) -> float:
    """`pages_with_load / pages`, defined as `1.0` when `pages == 0` (Req
    3.6): an empty period is complete because nothing is missing from it,
    never a zero. The one site both `Coverage.fraction` and the weekly
    suppression check (`_week_coverage`) read, so the empty-period rule is
    stated exactly once."""
    if pages == 0:
        return 1.0
    return pages_with_load / pages


def _week_key(day: date) -> tuple[int, int]:
    """A day's ISO `(year, week)`, never `(date.year, isocalendar().week)`
    -- an ISO week can straddle a calendar-year boundary (e.g. 2024-12-30 is
    ISO week `(2025, 1)`), and this key is what groups a straddling week's
    days into one row rather than two."""
    iso_year, iso_week, _ = day.isocalendar()
    return iso_year, iso_week


def _week_groups(series: DailySeries) -> list[tuple[tuple[int, int], list[int]]]:
    """`series.days`' indices grouped by ISO `(year, week)`, in day order.
    Each `DailySeries` is contiguous by calendar date (Req 1.6), so every
    group's indices are already ascending and unbroken; nothing here
    re-sorts them."""
    groups: dict[tuple[int, int], list[int]] = {}
    order: list[tuple[int, int]] = []
    for index, day_load in enumerate(series.days):
        key = _week_key(day_load.day)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(index)
    return [(key, groups[key]) for key in order]


def _week_coverage(series: DailySeries, indices: Sequence[int]) -> float:
    """A week's own coverage fraction (Req 3.1, 3.3), summed only over the
    days of `series` that actually lie inside this week (a partial week's
    missing days are simply not counted, not treated as missing pages)."""
    pages = sum(series.days[index].pages for index in indices)
    pages_with_load = sum(series.days[index].pages_with_load for index in indices)
    return _coverage_fraction(pages, pages_with_load)


def _last_index(indices: Sequence[int]) -> int:
    """The index, into `series.days` and therefore into `model.fitness` /
    `.fatigue` / `.form` (`run_model`'s own postcondition: one value per
    day), of a week's own last in-span day -- "the week's end" (Req 5.6)."""
    return indices[-1]


def suppressed_weeks(
    series: DailySeries, threshold: float
) -> frozenset[tuple[int, int]]:
    """Every ISO `(year, week)` whose coverage falls *strictly* below
    `threshold` (Req 3.3) -- a week exactly at the threshold is not
    suppressed. Needs no `ModelSeries`: suppression is decided from the day
    counts alone, before any model value is consulted."""
    return frozenset(
        key
        for key, indices in _week_groups(series)
        if _week_coverage(series, indices) < threshold
    )


@dataclass(frozen=True)
class WeekRow:
    """One row of the weekly table (Req 5.6, 5.7): the week identified by
    its own ISO year and week number, its Monday, how many of its days lie
    inside the span, its total recorded load, its session count (pages that
    record a load), its page and known-page counts, and the fitness,
    fatigue and form at the week's end -- or, when `suppressed`, `None` for
    all three instead."""

    iso_year: int
    iso_week: int
    monday: date
    days_in_span: int
    total_load: float
    sessions: int
    pages: int
    pages_with_load: int
    fitness: float | None
    fatigue: float | None
    form: float | None
    suppressed: bool


def week_rows(
    series: DailySeries, model: ModelSeries, suppressed: frozenset[tuple[int, int]]
) -> tuple[WeekRow, ...]:
    """The weekly table, one `WeekRow` per ISO week from the week containing
    `series.start` to the week containing `series.end` (Req 5.6). `model` is
    an already-computed `ModelSeries` over the whole span -- this function
    only indexes into it at each week's own last in-span day; it never calls
    `run_model` itself, so suppression never restarts or re-runs the
    recursion (Req 3.7). A week in `suppressed` carries `None` for
    `fitness`/`fatigue`/`form` and `suppressed=True` (Req 3.3, 5.7); every
    other week reports the model's values at its own last day.
    """
    rows = []
    for key, indices in _week_groups(series):
        iso_year, iso_week = key
        is_suppressed = key in suppressed
        pages = sum(series.days[index].pages for index in indices)
        pages_with_load = sum(series.days[index].pages_with_load for index in indices)
        end_index = _last_index(indices)
        rows.append(
            WeekRow(
                iso_year=iso_year,
                iso_week=iso_week,
                monday=date.fromisocalendar(iso_year, iso_week, 1),
                days_in_span=len(indices),
                total_load=sum(series.days[index].recorded_load for index in indices),
                sessions=pages_with_load,
                pages=pages,
                pages_with_load=pages_with_load,
                fitness=None if is_suppressed else model.fitness[end_index],
                fatigue=None if is_suppressed else model.fatigue[end_index],
                form=None if is_suppressed else model.form[end_index],
                suppressed=is_suppressed,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class Coverage:
    """One row of the coverage statement (Req 3.1, 3.5, 3.6, 3.10):
    `label` is a calendar year (`"2019"`) or `"all"`. `pages_excluded` is
    that period's own excluded-page counts by methodology, sorted by name.
    `pages_skipped` is `None` on every period row -- a skipped document has
    no date to attribute by -- and an integer only on the archive-wide
    (`"all"`) row."""

    label: str
    pages: int
    pages_with_load: int
    pages_excluded: tuple[tuple[str, int], ...]
    pages_skipped: int | None

    @property
    def fraction(self) -> float:
        return _coverage_fraction(self.pages, self.pages_with_load)


def _excluded_by_methodology(
    records: Sequence[PageRecord],
) -> tuple[tuple[str, int], ...]:
    """`records`' own methodology counts, sorted by name -- the same sort
    order `_excluded` already uses for `MethodologyChoice.excluded`."""
    counts: Counter[str] = Counter(
        record.methodology for record in records if record.methodology is not None
    )
    return tuple(sorted(counts.items()))


def coverage_report(
    series: DailySeries,
    excluded: Sequence[PageRecord],
    choice: MethodologyChoice,
    skipped: int,
) -> tuple[Coverage, ...]:
    """The coverage statement (Req 3.1, 3.5, 3.6, 3.10): one row per
    calendar year touched by `series.days` or by an `excluded` page's own
    date, in ascending order, followed by one archive-wide `"all"` row.

    A period row's `pages`/`pages_with_load` come from `series.days` (the
    included partition's own daily series); its `pages_excluded` comes from
    `excluded`'s own records for that year, never from `choice.excluded`'s
    archive-wide totals, because an excluded page has a date and two
    different years can hold a different mix of excluded methodologies.
    `pages_skipped` is `None` on every period row and `skipped` on the
    archive-wide row only (Req 3.10).
    """
    assert all(record.methodology != choice.methodology for record in excluded), (
        "coverage_report received an 'excluded' page recording the chosen "
        "methodology -- partition_pages should never produce that"
    )
    years = sorted(
        {day.day.year for day in series.days} | {record.day.year for record in excluded}
    )
    rows = [
        Coverage(
            label=str(year),
            pages=sum(day.pages for day in series.days if day.day.year == year),
            pages_with_load=sum(
                day.pages_with_load for day in series.days if day.day.year == year
            ),
            pages_excluded=_excluded_by_methodology(
                [record for record in excluded if record.day.year == year]
            ),
            pages_skipped=None,
        )
        for year in years
    ]
    rows.append(
        Coverage(
            label="all",
            pages=sum(day.pages for day in series.days),
            pages_with_load=sum(day.pages_with_load for day in series.days),
            pages_excluded=_excluded_by_methodology(excluded),
            pages_skipped=skipped,
        )
    )
    return tuple(rows)


#: The two exclusion reasons `criterion_points` groups a well-formed but
#: non-counted tag under (Req 6.3). A malformed tag is never grouped here --
#: it is named individually in `CriterionPoints.malformed` instead, by its
#: own path and the reader's own `describe()`.
_HARD_REASON = "hard effort -- no official result is required"
_NO_TIME_REASON = "race or test tag recorded with no official time"


@dataclass(frozen=True)
class CriterionPoints:
    """The archive's criterion-point report (Req 6.1-6.3): how many pages
    carry a valid `race` or `test` effort tag *and* record an official
    time, broken down by kind, with the earliest and latest counted dates,
    and every other tagged page grouped as an exclusion with a stated
    reason. Attaches no judgement of any kind -- no sufficiency verdict, no
    confidence claim, no recommendation (Req 6.5's negative, restated here
    because this is the one value that report reads).

    `by_kind` lists only the kinds actually observed, sorted by
    `EffortKind`'s own declaration order (`RACE`, then `TEST`) -- never by
    count. `earliest`/`latest` are `None` exactly when `count == 0` (Req
    6.2). `excluded` is `(reason, count)` for each of the two well-formed
    exclusion reasons that actually occurred, sorted by reason text.
    `malformed` is `(path, description)` for every malformed tag, sorted by
    path, each carrying the contract reader's own `describe()` (Req 3.9,
    6.3) rather than a generic label.
    """

    count: int
    by_kind: tuple[tuple[EffortKind, int], ...]
    earliest: date | None
    latest: date | None
    excluded: tuple[tuple[str, int], ...]
    malformed: tuple[tuple[str, str], ...]


def criterion_points(pages: Sequence[PageRecord]) -> CriterionPoints:
    """The archive's criterion-point report (Req 6.1-6.3).

    Walks every page in `pages` once. A malformed tag
    (`page.tag_problem is not None`) is named individually in `malformed` by
    its own path and the reader's own description; an untagged page
    (`page.effort is None` and `page.tag_problem is None`) contributes
    nothing. A well-formed `hard` tag, and a well-formed `race`/`test` tag
    recording no `time_s`, are each tallied into one of `excluded`'s two
    reason groups. A well-formed `race`/`test` tag recording a `time_s` is a
    criterion point: tallied into `by_kind` and folded into
    `earliest`/`latest`.
    """
    kind_counts: Counter[EffortKind] = Counter()
    reason_counts: Counter[str] = Counter()
    malformed: list[tuple[str, str]] = []
    counted_dates: list[date] = []

    for page in pages:
        if page.tag_problem is not None:
            malformed.append((page.path, page.tag_problem))
            continue
        tag = page.effort
        if tag is None:
            continue
        if tag.kind is EffortKind.HARD:
            reason_counts[_HARD_REASON] += 1
            continue
        if tag.time_s is None:
            reason_counts[_NO_TIME_REASON] += 1
            continue
        kind_counts[tag.kind] += 1
        counted_dates.append(page.day)

    by_kind = tuple(
        (kind, kind_counts[kind]) for kind in EffortKind if kind_counts[kind] > 0
    )
    count = sum(n for _, n in by_kind)
    excluded = tuple(sorted(reason_counts.items()))

    return CriterionPoints(
        count=count,
        by_kind=by_kind,
        earliest=min(counted_dates) if counted_dates else None,
        latest=max(counted_dates) if counted_dates else None,
        excluded=excluded,
        malformed=tuple(sorted(malformed)),
    )
