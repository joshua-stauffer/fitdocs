"""Tests for `fitdocs.history.series` (load-history spec). See the
"SeriesAssembly (`src/fitdocs/history/series.py`)" component in
`.kiro/specs/load-history/design.md`.

`tests/history/test_series.py` carries one headed section per task: this
file currently holds task 3.2's "methodology" section, task 3.3's "daily
series" section, and task 3.4's "weeks and coverage" section. Fixtures build
`PageRecord`s directly (the type task 3.1 already owns and tests through its
own real-frontmatter fixtures) rather than writing a page tree, because this
module is pure and never touches the filesystem. Task 3.4's fixtures build
`DailySeries`/`DayLoad`/`ModelSeries` directly too, rather than routing
through `build_daily_series` and `run_model` (each already exercised by its
own task), because `week_rows`/`suppressed_weeks` only ever consume those
types; `coverage_report` also takes a period's `DailySeries`, but its
`excluded`/`choice` arguments are `PageRecord`s and a `MethodologyChoice`
built the same way task 3.2's own fixtures build them.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from fitdocs.history.documents import PageRecord
from fitdocs.history.model import ModelSeries
from fitdocs.history.series import (
    Coverage,
    DailySeries,
    DayLoad,
    MethodologyChoice,
    MethodologyProblem,
    WeekRow,
    build_daily_series,
    coverage_report,
    partition_pages,
    select_methodology,
    suppressed_weeks,
    week_rows,
)

# ---------------------------------------------------------------------------
# methodology (task 3.2)
# ---------------------------------------------------------------------------


def _page(
    path: str,
    day: date,
    methodology: str | None,
    load: float | None = None,
) -> PageRecord:
    """A `PageRecord` with only the fields `series.py` reads populated
    meaningfully; `load` defaults to `1.0` whenever a `methodology` is given,
    preserving the 3.1 invariant `load is None` iff `methodology is None`."""
    if methodology is not None and load is None:
        load = 1.0
    return PageRecord(
        path=path,
        day=day,
        load=load,
        methodology=methodology,
        effort=None,
        tag_problem=None,
    )


_D1 = date(2024, 1, 1)
_D2 = date(2024, 1, 2)
_D3 = date(2024, 1, 3)


def test_single_methodology_is_inferred() -> None:
    pages = [
        _page("a.md", _D1, "banister"),
        _page("b.md", _D2, "banister"),
    ]
    result = select_methodology(pages, requested=None, configured=None)
    assert result == MethodologyChoice("banister", "inferred", ())


def test_methodology_configured_wins_with_two_observed() -> None:
    pages = [_page(f"old{i}.md", _D1, "old") for i in range(3)] + [
        _page(f"new{i}.md", _D2, "new") for i in range(5)
    ]
    result = select_methodology(pages, requested=None, configured="old")
    assert isinstance(result, MethodologyChoice)
    assert result.methodology == "old"
    assert result.source == "configured"
    assert result.excluded == (("new", 5),)


def test_methodology_requested_wins_with_two_observed() -> None:
    pages = [_page(f"old{i}.md", _D1, "old") for i in range(3)] + [
        _page(f"new{i}.md", _D2, "new") for i in range(5)
    ]
    result = select_methodology(pages, requested="new", configured=None)
    assert isinstance(result, MethodologyChoice)
    assert result.methodology == "new"
    assert result.source == "requested"
    assert result.excluded == (("old", 3),)


def test_methodology_requested_beats_configured_when_both_set_and_differ() -> None:
    """Confounded-fixture defense: `requested` and `configured` differ, and
    the two observed methodologies carry different counts, so a precedence
    swap (configured wins) would pick a different, wrong methodology than
    this test's `requested="alpha"` -- verified directly by mutation."""
    pages = [_page(f"alpha{i}.md", _D1, "alpha") for i in range(2)] + [
        _page(f"beta{i}.md", _D2, "beta") for i in range(4)
    ]
    result = select_methodology(pages, requested="alpha", configured="beta")
    assert isinstance(result, MethodologyChoice)
    assert result.methodology == "alpha"
    assert result.source == "requested"
    # `excluded` must be computed against the *chosen* methodology
    # ("alpha", the requested one), not against `configured` -- a swap
    # would exclude "alpha" (the chosen one) instead of "beta".
    assert result.excluded == (("beta", 4),)


def test_methodology_two_with_neither_is_an_ambiguous_problem() -> None:
    """Different counts (2 vs 5) so a most-common fallback is a real,
    detectably-wrong alternative to the problem this rule must return."""
    pages = [_page(f"jog{i}.md", _D1, "jog") for i in range(2)] + [
        _page(f"cycle{i}.md", _D2, "cycle") for i in range(5)
    ]
    result = select_methodology(pages, requested=None, configured=None)
    assert isinstance(result, MethodologyProblem)
    assert "'cycle' (5 pages)" in result.detail
    assert "'jog' (2 pages)" in result.detail
    # Pins the listed order too (name-ascending, "cycle" before "jog"): the
    # insertion order here is "jog" then "cycle", so a dropped `sorted()` in
    # `_methodology_list` would leave "jog" ahead of "cycle" instead.
    assert result.detail.index("'cycle'") < result.detail.index("'jog'")
    # The action must name both a CLI flag and the config keys that resolve
    # the problem (Req 4.4 "how to choose one"; design.md ~975, ~1411).
    assert "--methodology" in result.detail
    assert "[history].methodology" in result.detail


def test_methodology_requested_id_absent_from_archive_is_a_problem() -> None:
    pages = [_page("a.md", _D1, "banister")]
    result = select_methodology(pages, requested="tss", configured=None)
    assert isinstance(result, MethodologyProblem)
    assert "'tss'" in result.detail
    assert "'banister' (1 pages)" in result.detail
    # The action this branch names: choose one of the present methodologies.
    assert "Choose one of the present methodologies" in result.detail


def test_methodology_configured_id_absent_from_archive_is_a_problem() -> None:
    pages = [_page("a.md", _D1, "banister")]
    result = select_methodology(pages, requested=None, configured="tss")
    assert isinstance(result, MethodologyProblem)
    assert "'tss'" in result.detail
    assert "'banister' (1 pages)" in result.detail
    # The action this branch names: the config keys and the CLI flag.
    assert "[load].default_calculator" in result.detail
    assert "--methodology" in result.detail


def test_methodology_configured_id_absent_with_no_methodology_observed_at_all() -> None:
    """`configured` names an id, but the archive's pages record no
    methodology at all (unscored-only archive) -- the "methodologies
    present: ." fragment must not appear, and the only followable action
    (record loads first) must."""
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    result = select_methodology(pages, requested=None, configured="banister")
    assert isinstance(result, MethodologyProblem)
    assert "present: ." not in result.detail
    assert "no page in the archive records a methodology" in result.detail
    assert "fitdocs load" in result.detail


def test_methodology_requested_id_absent_with_no_methodology_observed_at_all() -> None:
    """`requested` names an id, but the archive's pages record no
    methodology at all (unscored-only archive) -- the "methodologies
    present: ." fragment must not appear, the "record loads first" action
    must, and the *other* absent-id action (naming present methodologies to
    choose from) must not, since there are none to choose from."""
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    result = select_methodology(pages, requested="x", configured=None)
    assert isinstance(result, MethodologyProblem)
    assert "present: ." not in result.detail
    assert "no page in the archive records a methodology" in result.detail
    assert "fitdocs load" in result.detail
    assert "Choose one of the present methodologies" not in result.detail


def test_methodology_archive_of_unscored_pages_only_is_a_problem() -> None:
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    result = select_methodology(pages, requested=None, configured=None)
    assert isinstance(result, MethodologyProblem)


def test_excluded_is_sorted_by_methodology_name() -> None:
    """Observed in an order that is *not* already alphabetical, and with the
    alphabetically-first methodology carrying the *smaller* count (1 vs 3):
    name-ascending order yields `(("alpha", 1), ("zulu", 3))`, while a
    count-descending fallback (e.g. `Counter.most_common()`) would yield the
    reverse -- so the two orderings are distinguishable, not confounded."""
    pages = (
        [_page(f"z{i}.md", _D1, "zulu") for i in range(3)]
        + [_page("a.md", _D2, "alpha")]
        + [_page("m.md", _D3, "mango")]
    )
    result = select_methodology(pages, requested="mango", configured=None)
    assert isinstance(result, MethodologyChoice)
    assert result.excluded == (("alpha", 1), ("zulu", 3))


def test_methodology_partition_includes_chosen_and_unscored_excludes_other() -> None:
    """Fixture order deliberately matches neither day order nor path order,
    for both `included` and `excluded`:

    - `included`: `chosen` is the latest day (`_D3`) and the lexically later
      path (`z-chosen.md`), but is listed first; `unscored` is the earliest
      day (`_D1`) and lexically earlier path (`a-unscored.md`). A
      `partition_pages` that re-sorted `included` by day, or by path, would
      return `(unscored, chosen)` here instead of `(chosen, unscored)`.
    - `excluded`: `other2` (`y-other.md`, `_D2`) is listed before `other`
      (`b-other.md`, `_D1`) even though `other`'s path sorts earlier and its
      day is earlier. A `partition_pages` that re-sorted `excluded` by path,
      or by day, would return `(other, other2)` here instead of the input
      order `(other2, other)`.
    """
    chosen = _page("z-chosen.md", _D3, "banister")
    unscored = _page("a-unscored.md", _D1, None)
    other2 = _page("y-other.md", _D2, "tss")
    other = _page("b-other.md", _D1, "tss")
    choice = MethodologyChoice("banister", "inferred", (("tss", 2),))

    included, excluded = partition_pages([chosen, unscored, other2, other], choice)

    assert included == (chosen, unscored)
    assert excluded == (other2, other)


# ---------------------------------------------------------------------------
# daily series (task 3.3)
# ---------------------------------------------------------------------------

# A single fixture threading every required scenario through one contiguous
# span, Jan 3 - Jan 7 2024:
#   Jan 1  -- a page dated *before* the first contributing page, recording no
#             load (leading unknown; outside the span; pins the span start
#             at Jan 3 rather than Jan 1).
#   Jan 3  -- two pages on one date, loads 4.5 and 7.25. Pairwise-distinct
#             and non-integral, and chosen so the sum (11.75) equals neither
#             addend, their average (5.875), nor either alone -- defeats
#             "sum only the first/last load" and "average the loads" alike,
#             and (being non-integral) defeats a `round(sum(...))` or a
#             truncating `int(sum(...))` alongside the correctly-summed
#             value. First contributing day: pins the span start.
#   Jan 4  -- a rest day inside the span: no pages at all. `sum([])` on the
#             empty `loaded` list defaults to `int 0` unless the production
#             code forces a `float` start value, so this day's own
#             `recorded_load` pins `DayLoad.recorded_load: float` (design.md)
#             by its runtime *type*, not merely its numeric value (`0 == 0.0`
#             both pass an equality check).
#   Jan 5  -- a partially known day: one page with a load (5.5), one without.
#   Jan 6  -- a fully unknown day: two pages, neither with a load.
#   Jan 7  -- a single page, load 9.0. Last contributing day: pins the span
#             end.
#   Jan 9  -- a page dated *after* the last contributing page, recording no
#             load (trailing unknown; outside the span; non-adjacent to
#             Jan 7 so a wrong end that included it would also manufacture a
#             phantom rest day on Jan 8, not merely shift the end by one).
#             Pins the span end at Jan 7 rather than Jan 9.
_LEADING = date(2024, 1, 1)
_SPAN_START = date(2024, 1, 3)
_REST_DAY = date(2024, 1, 4)
_PARTIAL_DAY = date(2024, 1, 5)
_UNKNOWN_DAY = date(2024, 1, 6)
_SPAN_END = date(2024, 1, 7)
_TRAILING = date(2024, 1, 9)


def _daily_series_fixture() -> list[PageRecord]:
    return [
        _page("leading.md", _LEADING, None),
        _page("start-a.md", _SPAN_START, "banister", load=4.5),
        _page("start-b.md", _SPAN_START, "banister", load=7.25),
        _page("partial-known.md", _PARTIAL_DAY, "banister", load=5.5),
        _page("partial-unknown.md", _PARTIAL_DAY, None),
        _page("unknown-a.md", _UNKNOWN_DAY, None),
        _page("unknown-b.md", _UNKNOWN_DAY, None),
        _page("end.md", _SPAN_END, "banister", load=9.0),
        _page("trailing.md", _TRAILING, None),
    ]


def _series_by_day(series: DailySeries) -> dict[date, DayLoad]:
    return {day_load.day: day_load for day_load in series.days}


def test_day_load_unknown_and_complete_views_distinguish_rest_from_unknown() -> None:
    """`DayLoad`'s derived views, exercised directly (not only through
    `build_daily_series`): a rest day (0 pages) and a fully unknown day (2
    pages, 0 with a load) both record zero load, so they must be
    distinguishable by their `pages`/`pages_with_load` fields -- and hence by
    equality -- not merely by convention."""
    rest = DayLoad(day=_REST_DAY, recorded_load=0.0, pages=0, pages_with_load=0)
    unknown_day = DayLoad(
        day=_UNKNOWN_DAY, recorded_load=0.0, pages=2, pages_with_load=0
    )
    partial = DayLoad(day=_PARTIAL_DAY, recorded_load=5.0, pages=2, pages_with_load=1)

    assert rest.unknown_pages == 0
    assert rest.is_complete is True

    assert unknown_day.unknown_pages == 2
    assert unknown_day.is_complete is False

    assert partial.unknown_pages == 1
    assert partial.is_complete is False

    assert rest != unknown_day


def test_build_daily_series_spans_first_to_last_contributing_day() -> None:
    series = build_daily_series(_daily_series_fixture())
    assert series is not None
    assert series.start == _SPAN_START
    assert series.end == _SPAN_END
    assert [day_load.day for day_load in series.days] == [
        _SPAN_START,
        _REST_DAY,
        _PARTIAL_DAY,
        _UNKNOWN_DAY,
        _SPAN_END,
    ]


def test_build_daily_series_sums_two_same_day_loads() -> None:
    series = build_daily_series(_daily_series_fixture())
    assert series is not None
    by_day = _series_by_day(series)
    assert by_day[_SPAN_START] == DayLoad(
        day=_SPAN_START, recorded_load=11.75, pages=2, pages_with_load=2
    )


def test_build_daily_series_rest_day_is_complete_with_zero_pages() -> None:
    series = build_daily_series(_daily_series_fixture())
    assert series is not None
    by_day = _series_by_day(series)
    assert by_day[_REST_DAY] == DayLoad(
        day=_REST_DAY, recorded_load=0.0, pages=0, pages_with_load=0
    )
    # `sum([])` on an empty `loaded` list defaults to `int 0` unless the
    # production code forces a `float` start value -- an equality check
    # against `0.0` alone cannot tell `int 0` from `float 0.0` apart
    # (`0 == 0.0`), so this pins `DailySeries`' design.md contract
    # (`recorded_load: float`) by the value's own runtime type.
    assert type(by_day[_REST_DAY].recorded_load) is float


def test_build_daily_series_partially_known_day_keeps_its_recorded_load() -> None:
    series = build_daily_series(_daily_series_fixture())
    assert series is not None
    by_day = _series_by_day(series)
    assert by_day[_PARTIAL_DAY] == DayLoad(
        day=_PARTIAL_DAY, recorded_load=5.5, pages=2, pages_with_load=1
    )


def test_build_daily_series_fully_unknown_day_records_zero_but_counts_pages() -> None:
    series = build_daily_series(_daily_series_fixture())
    assert series is not None
    by_day = _series_by_day(series)
    assert by_day[_UNKNOWN_DAY] == DayLoad(
        day=_UNKNOWN_DAY, recorded_load=0.0, pages=2, pages_with_load=0
    )
    # The rest day and the fully unknown day both record zero load, but
    # compare unequal -- the observable the task names.
    assert by_day[_REST_DAY] != by_day[_UNKNOWN_DAY]


def test_build_daily_series_pages_outside_span_are_not_counted() -> None:
    """The leading page (Jan 1) and the trailing page (Jan 9) are both
    included but record no load, so neither moves the span start or end,
    and neither is folded into any in-span day's `pages` count -- the total
    pages across the series' days must equal the number of included pages
    that fall inside the span (7 of the fixture's 9), not 8 or 9 as either
    outside page would add if it leaked in. The trailing page is also
    non-adjacent to the span end (Jan 7 vs. Jan 9): an end wrongly computed
    as `max(page.day for page in pages)` (the last *included* page rather
    than the last *contributing* one) would both move `.end` to Jan 9 and
    manufacture a phantom rest day on Jan 8, so `series.end` is pinned here
    directly alongside the page count."""
    series = build_daily_series(_daily_series_fixture())
    assert series is not None
    assert series.end == _SPAN_END
    total_pages = sum(day_load.pages for day_load in series.days)
    assert total_pages == 7


def test_build_daily_series_single_day_archive() -> None:
    only = _page("only.md", _SPAN_START, "banister", load=3.0)
    series = build_daily_series([only])
    assert series is not None
    assert series.start == _SPAN_START
    assert series.end == _SPAN_START
    assert series.days == (
        DayLoad(day=_SPAN_START, recorded_load=3.0, pages=1, pages_with_load=1),
    )


def test_build_daily_series_returns_none_when_nothing_records_a_load() -> None:
    pages = [
        _page("a.md", _D1, None),
        _page("b.md", _D2, None),
    ]
    assert build_daily_series(pages) is None


# ---------------------------------------------------------------------------
# weeks and coverage (task 3.4)
# ---------------------------------------------------------------------------


def test_weeks_rows_reports_end_of_week_values_and_distinct_session_count() -> None:
    """One full ISO week, Jan 1 (Mon) - Jan 7 (Sun) 2024, seven `DayLoad`s.
    Jan 1 carries two pages, only one with a load, so `pages` (8) and
    `sessions`/`pages_with_load` (7) differ -- a `sessions=pages` swap would
    report 8, not 7. `model` carries seven distinct, non-integral values per
    series so index 0 (week start) and index 6 (week end) are never equal --
    an `indices[0]` instead of `indices[-1]` mutation reports the wrong
    number, not merely a coincidentally-equal one."""
    days = (
        DayLoad(date(2024, 1, 1), recorded_load=1.25, pages=2, pages_with_load=1),
        DayLoad(date(2024, 1, 2), recorded_load=2.5, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 3), recorded_load=3.75, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 4), recorded_load=4.125, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 5), recorded_load=5.5, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 6), recorded_load=6.25, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 7), recorded_load=7.875, pages=1, pages_with_load=1),
    )
    series = DailySeries(start=days[0].day, days=days)
    model = ModelSeries(
        fitness=(10.5, 20.5, 30.5, 40.5, 50.5, 60.5, 70.5),
        fatigue=(1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1),
        form=(9.4, 18.4, 27.4, 36.4, 45.4, 54.4, 63.4),
    )

    rows = week_rows(series, model, suppressed=frozenset())

    assert len(rows) == 1
    row = rows[0]
    assert row.iso_year == 2024
    assert row.iso_week == 1
    assert row.monday == date(2024, 1, 1)
    assert row.days_in_span == 7
    assert row.total_load == pytest.approx(31.25)
    assert row.pages == 8
    assert row.pages_with_load == 7
    assert row.sessions == 7
    assert row.fitness == 70.5
    assert row.fatigue == 7.1
    assert row.form == 63.4
    assert row.suppressed is False


def test_suppressed_weeks_empty_week_is_complete_not_zero() -> None:
    """A week with no pages at all (a rest week) is *complete* coverage
    (Req 3.6), not suppressed -- an empty-period-coverage-as-zero mutation
    would suppress it and flip the whole page's report for that week."""
    days = tuple(
        DayLoad(
            date(2024, 1, 8 + offset), recorded_load=0.0, pages=0, pages_with_load=0
        )
        for offset in range(7)
    )
    series = DailySeries(start=days[0].day, days=days)

    assert suppressed_weeks(series, threshold=0.80) == frozenset()

    model = ModelSeries(fitness=(1.0,) * 7, fatigue=(1.0,) * 7, form=(0.0,) * 7)
    rows = week_rows(series, model, suppressed=suppressed_weeks(series, 0.80))
    assert len(rows) == 1
    assert rows[0].suppressed is False
    assert rows[0].fitness == 1.0
    assert rows[0].total_load == 0.0
    assert rows[0].pages == 0
    assert rows[0].sessions == 0


def test_weeks_suppression_at_threshold_not_suppressed_and_just_below_is() -> None:
    """Two adjacent full ISO weeks, contiguous Jan 15 - Jan 28 2024. Week
    (2024, 3) carries 5 pages, 4 with a load -- coverage exactly 0.80, the
    shipped threshold -- and must NOT be suppressed (a `<=` mutation would
    suppress it). Week (2024, 4) carries 5 pages, 3 with a load -- 0.60,
    strictly below -- and must be suppressed, with `None` for all three
    model values.

    Jan 15 carries two pages (both with a load), so the week's *page*
    coverage (4 loaded of 5 total pages, 0.80, at the threshold) and a
    per-*day* boolean coverage (days with any loaded page over days with
    any page: Jan 15-17 have one each, Jan 18 has none, 3/4 = 0.75, below
    the threshold) disagree -- a `_week_coverage` that counted
    `sum(bool(day.pages_with_load) for day in ...)` /
    `sum(bool(day.pages) for day in ...)` over days instead of summing the
    actual page counts would suppress week (2024, 3) here, where the page
    based measure must not."""
    at_threshold = [
        DayLoad(date(2024, 1, 15), 1.0, pages=2, pages_with_load=2),
        DayLoad(date(2024, 1, 16), 1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 17), 1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 18), 0.0, pages=1, pages_with_load=0),
        DayLoad(date(2024, 1, 19), 0.0, pages=0, pages_with_load=0),
        DayLoad(date(2024, 1, 20), 0.0, pages=0, pages_with_load=0),
        DayLoad(date(2024, 1, 21), 0.0, pages=0, pages_with_load=0),
    ]
    just_below = [
        DayLoad(date(2024, 1, 22), 1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 23), 1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 24), 1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 25), 0.0, pages=1, pages_with_load=0),
        DayLoad(date(2024, 1, 26), 0.0, pages=1, pages_with_load=0),
        DayLoad(date(2024, 1, 27), 0.0, pages=0, pages_with_load=0),
        DayLoad(date(2024, 1, 28), 0.0, pages=0, pages_with_load=0),
    ]
    days = tuple(at_threshold + just_below)
    series = DailySeries(start=days[0].day, days=days)

    suppressed = suppressed_weeks(series, threshold=0.80)
    assert suppressed == frozenset({(2024, 4)})

    model = ModelSeries(
        fitness=tuple(float(i) for i in range(14)),
        fatigue=tuple(float(i) for i in range(14)),
        form=tuple(float(i) for i in range(14)),
    )
    rows = week_rows(series, model, suppressed)
    assert len(rows) == 2
    week3, week4 = rows
    assert week3.iso_year == 2024 and week3.iso_week == 3
    assert week3.suppressed is False
    assert week3.fitness == 6.0  # index 6, the week's own last day (Jan 21)

    assert week4.iso_year == 2024 and week4.iso_week == 4
    assert week4.suppressed is True
    assert week4.fitness is None
    assert week4.fatigue is None
    assert week4.form is None


def test_weeks_rows_partial_first_and_last_week_days_in_span_and_monday() -> None:
    """A span Jan 4 (Thu) - Jan 10 (Wed) 2024 crosses one ISO-week boundary:
    the first week (2024, 1) holds only 4 of its 7 calendar days in span,
    the second (2024, 2) only 3. `monday` is each ISO week's own Monday --
    Jan 1 and Jan 8 -- neither of which is in the span at all, so a
    `date.fromisocalendar(..., 2)` (Tuesday) mutation is directly visible,
    and `days_in_span` must report the in-span count (4, 3), never a
    constant 7."""
    dates = [date(2024, 1, d) for d in (4, 5, 6, 7, 8, 9, 10)]
    days = tuple(
        DayLoad(d, recorded_load=1.0, pages=1, pages_with_load=1) for d in dates
    )
    series = DailySeries(start=days[0].day, days=days)
    model = ModelSeries(
        fitness=tuple(float(i) for i in range(7)),
        fatigue=tuple(float(i) for i in range(7)),
        form=tuple(float(i) for i in range(7)),
    )

    rows = week_rows(series, model, suppressed=frozenset())

    assert len(rows) == 2
    first, second = rows
    assert first.iso_year == 2024 and first.iso_week == 1
    assert first.monday == date(2024, 1, 1)
    assert first.days_in_span == 4

    assert second.iso_year == 2024 and second.iso_week == 2
    assert second.monday == date(2024, 1, 8)
    assert second.days_in_span == 3


def test_weeks_rows_iso_week_spanning_a_year_boundary_is_one_row() -> None:
    """Dec 30, 2024 (Mon) - Jan 5, 2025 (Sun) is a single ISO week,
    `(2025, 1)`, even though its calendar dates span two years -- a
    `(date.year, isocalendar().week)` keying mutation would split this into
    two rows instead of one, and would misreport `days_in_span` for each."""
    dates = [
        date(2024, 12, 30),
        date(2024, 12, 31),
        date(2025, 1, 1),
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 4),
        date(2025, 1, 5),
    ]
    days = tuple(
        DayLoad(d, recorded_load=1.0, pages=1, pages_with_load=1) for d in dates
    )
    series = DailySeries(start=days[0].day, days=days)
    model = ModelSeries(
        fitness=tuple(float(i) for i in range(7)),
        fatigue=tuple(float(i) for i in range(7)),
        form=tuple(float(i) for i in range(7)),
    )

    rows = week_rows(series, model, suppressed=frozenset())

    assert len(rows) == 1
    row = rows[0]
    assert row.iso_year == 2025
    assert row.iso_week == 1
    assert row.monday == date(2024, 12, 30)
    assert row.days_in_span == 7


def test_coverage_report_per_year_excluded_split_differs_from_archive_wide() -> None:
    """Two calendar years, each holding excluded pages of a *different*
    methodology: 2023 excludes 3 'cycle' pages, 2024 excludes 5 'swim'
    pages. An implementation that reads `choice.excluded` (the archive-wide
    total, `(('cycle', 3), ('swim', 5))`) instead of `excluded`'s own dated
    records would report that same combined tuple on *both* year rows --
    this fixture makes the two year rows differ from each other and from
    the combined total, so that mutation is directly visible.

    `series.days`' own page counts are pairwise-distinct and non-tied
    across the two years, and 2023 carries an unknown page: 2023 is
    pages=3/pages_with_load=2 (Dec-30's two pages split 1/1 -- the one
    unknown page -- and Dec-31's single page has a load), 2024 is Jan-1
    alone at pages=1/pages_with_load=1,
    and the combined archive-wide row is pages=4/pages_with_load=3 -- three
    distinct totals, so a year-row rule that sums every `series.days` entry
    regardless of year, or an archive-wide `pages_with_load` read from
    `pages` instead of `pages_with_load`, each lands on a value the fixture
    already rules out elsewhere.

    `excluded`'s own construction order is `swim` records built before
    `cycle` -- the reverse of the alphabetical order asserted below on the
    combined `archive.pages_excluded` -- so a `_excluded_by_methodology`
    that dropped its `sorted()` would return the input order (swim, cycle)
    instead of (cycle, swim), which the fixture's own input order does not
    already satisfy.
    """
    days = (
        DayLoad(date(2023, 12, 30), recorded_load=1.0, pages=2, pages_with_load=1),
        DayLoad(date(2023, 12, 31), recorded_load=1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 1, 1), recorded_load=1.0, pages=1, pages_with_load=1),
    )
    series = DailySeries(start=days[0].day, days=days)
    swim_records = tuple(
        PageRecord(
            path=f"swim{i}.md",
            day=date(2024, 7, 1),
            load=2.0,
            methodology="swim",
            effort=None,
            tag_problem=None,
        )
        for i in range(5)
    )
    cycle_records = tuple(
        PageRecord(
            path=f"cycle{i}.md",
            day=date(2023, 5, 1),
            load=2.0,
            methodology="cycle",
            effort=None,
            tag_problem=None,
        )
        for i in range(3)
    )
    excluded = swim_records + cycle_records
    choice = MethodologyChoice("run", "inferred", (("cycle", 3), ("swim", 5)))

    rows = coverage_report(series, excluded, choice, skipped=0)

    assert [row.label for row in rows] == ["2023", "2024", "all"]
    year_2023, year_2024, archive = rows
    assert year_2023.pages_excluded == (("cycle", 3),)
    assert year_2024.pages_excluded == (("swim", 5),)
    assert year_2023.pages_excluded != year_2024.pages_excluded
    assert archive.pages_excluded == (("cycle", 3), ("swim", 5))
    assert year_2023.pages_excluded != archive.pages_excluded
    assert year_2024.pages_excluded != archive.pages_excluded

    assert year_2023.pages == 3
    assert year_2023.pages_with_load == 2
    assert year_2024.pages == 1
    assert year_2024.pages_with_load == 1
    assert archive.pages == 4
    assert archive.pages_with_load == 3


def test_coverage_report_year_touched_only_by_excluded_page_gets_its_own_row() -> None:
    """An excluded page dated 2022, a year `series.days` never touches at
    all (the series only spans 2023-2024) -- `coverage_report`'s own year
    set is the *union* of the days' years and the excluded records' years,
    so 2022 still gets a row, with `pages == 0` (nothing from `series.days`
    falls in it) and therefore `fraction == 1.0` (an empty period is
    complete, Req 3.6), and its own `pages_excluded` naming the one
    excluded page. A `years` computed from `series.days` alone would omit
    2022 from the label list entirely."""
    days = (
        DayLoad(date(2023, 6, 1), recorded_load=1.0, pages=1, pages_with_load=1),
        DayLoad(date(2024, 6, 1), recorded_load=1.0, pages=1, pages_with_load=1),
    )
    series = DailySeries(start=days[0].day, days=days)
    excluded = (
        PageRecord(
            path="cycle.md",
            day=date(2022, 6, 1),
            load=2.0,
            methodology="cycle",
            effort=None,
            tag_problem=None,
        ),
    )
    choice = MethodologyChoice("run", "inferred", (("cycle", 1),))

    rows = coverage_report(series, excluded, choice, skipped=0)

    assert [row.label for row in rows] == ["2022", "2023", "2024", "all"]
    year_2022 = rows[0]
    assert year_2022.pages == 0
    assert year_2022.fraction == 1.0
    assert year_2022.pages_excluded == (("cycle", 1),)


def test_coverage_report_skipped_document_is_archive_wide_only() -> None:
    """One skipped, undated document: the archive-wide row must count it
    (an integer), and every period row must show `None` -- not zero, which
    would read as "none were skipped" -- and never the skipped count
    itself, which would misattribute an unplaceable document to a period it
    was never placed in (Req 3.10)."""
    days = (DayLoad(date(2024, 3, 1), recorded_load=1.0, pages=1, pages_with_load=1),)
    series = DailySeries(start=days[0].day, days=days)
    choice = MethodologyChoice("run", "inferred", ())

    rows = coverage_report(series, excluded=(), choice=choice, skipped=1)

    assert [row.label for row in rows] == ["2024", "all"]
    year_row, archive_row = rows
    assert year_row.pages_skipped is None
    assert archive_row.pages_skipped == 1


def test_coverage_fraction_is_one_when_empty_and_a_fraction_otherwise() -> None:
    """`Coverage.fraction` (Req 3.6): `1.0` when a period has no pages at
    all, `pages_with_load / pages` otherwise -- exercised directly against
    the dataclass, not only through the weekly-suppression path."""
    empty = Coverage(
        label="2024", pages=0, pages_with_load=0, pages_excluded=(), pages_skipped=None
    )
    partial = Coverage(
        label="2024", pages=5, pages_with_load=4, pages_excluded=(), pages_skipped=None
    )
    assert empty.fraction == 1.0
    assert partial.fraction == pytest.approx(0.8)


# --- frozenness (Req: design.md "SeriesAssembly" `@dataclass(frozen=True)`) --


def test_day_load_is_frozen() -> None:
    day_load = DayLoad(date(2024, 1, 1), recorded_load=1.0, pages=1, pages_with_load=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        day_load.pages = 2  # type: ignore[misc]


def test_daily_series_is_frozen() -> None:
    series = DailySeries(
        start=date(2024, 1, 1),
        days=(DayLoad(date(2024, 1, 1), 1.0, pages=1, pages_with_load=1),),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        series.start = date(2024, 1, 2)  # type: ignore[misc]


def test_methodology_choice_is_frozen() -> None:
    choice = MethodologyChoice("run", "inferred", ())
    with pytest.raises(dataclasses.FrozenInstanceError):
        choice.methodology = "cycle"  # type: ignore[misc]


def test_methodology_problem_is_frozen() -> None:
    problem = MethodologyProblem("detail")
    with pytest.raises(dataclasses.FrozenInstanceError):
        problem.detail = "other"  # type: ignore[misc]


def test_week_row_is_frozen() -> None:
    row = WeekRow(
        iso_year=2024,
        iso_week=1,
        monday=date(2024, 1, 1),
        days_in_span=7,
        total_load=1.0,
        sessions=1,
        pages=1,
        pages_with_load=1,
        fitness=1.0,
        fatigue=1.0,
        form=0.0,
        suppressed=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.suppressed = True  # type: ignore[misc]


def test_coverage_is_frozen() -> None:
    coverage = Coverage(
        label="all", pages=1, pages_with_load=1, pages_excluded=(), pages_skipped=0
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        coverage.pages = 2  # type: ignore[misc]
