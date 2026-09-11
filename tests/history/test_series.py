"""Tests for `fitdocs.history.series` (load-history spec). See the
"SeriesAssembly (`src/fitdocs/history/series.py`)" component in
`.kiro/specs/load-history/design.md`.

`tests/history/test_series.py` carries one headed section per task: this
file currently holds task 3.2's "methodology" section and task 3.3's "daily
series" section. Fixtures build
`PageRecord`s directly (the type task 3.1 already owns and tests through its
own real-frontmatter fixtures) rather than writing a page tree, because this
module is pure and never touches the filesystem.
"""

from __future__ import annotations

from datetime import date

from fitdocs.history.documents import PageRecord
from fitdocs.history.series import (
    DailySeries,
    DayLoad,
    MethodologyChoice,
    MethodologyProblem,
    build_daily_series,
    partition_pages,
    select_methodology,
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
