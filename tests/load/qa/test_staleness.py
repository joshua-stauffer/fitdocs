"""Tests for `fitdocs.load.qa.staleness.evaluate` (design: StalenessSurfacing,
task 2.5).

Covers Requirements 1.5, 1.8, 1.10, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8 --
see ``.kiro/specs/activity-qa-flags/requirements.md`` and design.md's
"StalenessSurfacing" component section, including the 2026-09-16 amendment
("Amendment -- 2026-09-16: retroactive anchors") that withdrew the pre-call
ordering guard an earlier revision of this task built.

**Own test module** (Test File Ownership / "Shared test fixture" note in
tasks.md): every constructed :class:`ChannelLoad` and :class:`Benchmark`
this task needs is built here, not added to ``tests/load/qa/conftest.py``,
which task 2.1 owns and tasks 2.3/2.4/2.5 must not touch to keep their
``(P)`` markers safe.
"""

from __future__ import annotations

from datetime import date, timedelta

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels.types import ChannelId, ChannelLoad, StreamCoverage
from fitdocs.load.qa.staleness import StalenessOutcome, evaluate
from fitdocs.model import Sport

ACTIVITY_DATE = date(2026, 6, 1)


def _channel_load(anchor: Benchmark) -> ChannelLoad:
    """Build a minimal `ChannelLoad` carrying ``anchor``. Every field but
    ``anchor`` is arbitrary and irrelevant to this check (5.1, 5.2)."""
    return ChannelLoad(
        channel=ChannelId.POWER,
        load=100.0,
        intensity=1.0,
        anchor=anchor,
        scored_duration_s=3600.0,
        coverage=StreamCoverage(stream="power", covered_s=3600.0, total_s=3600.0),
        inputs_used=(("power", "watts"),),
    )


def _benchmark(measured_on: date, *, applies_from: date | None = None) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=270.0,
        measured_on=measured_on,
        applies_from=applies_from,
    )


def test_no_activity_date_is_not_assessed_naming_the_absent_date() -> None:
    """Req 5.5: the sole reachable not-assessed path is an undated activity;
    the anchor is still carried (never None) and no age is computed."""
    anchor = _benchmark(date(2026, 1, 1))
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=None, window_days=90)

    assert reading.outcome is StalenessOutcome.NOT_ASSESSED
    assert reading.anchor is anchor
    assert reading.age is None
    assert reading.not_assessed_reason is not None
    # The activity's own absent calendar date is the sole reachable
    # not-assessed input (design: 5.5's "structurally unreachable" note) --
    # the reason must name the activity's date specifically, not blame the
    # benchmark's own measurement date, which is non-optional upstream and
    # can never be the absent input here.
    assert "activity" in reading.not_assessed_reason
    assert "calendar date" in reading.not_assessed_reason
    assert "measurement date" not in reading.not_assessed_reason


def test_stale_anchor_carries_age_and_anchor() -> None:
    """Req 5.3: an anchor measured well outside the window reaches STALE,
    carrying the computed age and the unmodified anchor."""
    measured_on = ACTIVITY_DATE - timedelta(days=200)
    anchor = _benchmark(measured_on)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.outcome is StalenessOutcome.STALE
    assert reading.anchor is anchor
    assert reading.age is not None
    assert reading.age.age_days == 200
    assert reading.age.window_days == 90
    assert reading.age.is_stale is True
    assert reading.not_assessed_reason is None


def test_current_anchor_within_window() -> None:
    """Req 5.3: an anchor measured well inside the window reaches CURRENT."""
    measured_on = ACTIVITY_DATE - timedelta(days=10)
    anchor = _benchmark(measured_on)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.outcome is StalenessOutcome.CURRENT
    assert reading.age is not None
    assert reading.age.age_days == 10
    assert reading.age.is_stale is False


def test_age_exactly_equal_to_window_is_current_not_stale() -> None:
    """Boundary-exactness: age_days == window_days is CURRENT, not STALE --
    this module must not reinterpret or re-derive benchmark_age's own
    "current at the boundary, stale one day beyond" contract."""
    window_days = 90
    measured_on = ACTIVITY_DATE - timedelta(days=window_days)
    anchor = _benchmark(measured_on)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=window_days)

    assert reading.age is not None
    assert reading.age.age_days == window_days
    assert reading.outcome is StalenessOutcome.CURRENT


def test_age_one_day_past_window_is_stale() -> None:
    """Boundary-exactness, the other side: age_days == window_days + 1 is
    STALE, pinned exactly at one day past the boundary rather than far
    beyond it the way the other STALE fixtures are. Without this, an
    off-by-one such as `age_days > window_days + 1` (instead of consuming
    `is_stale` verbatim) would leave every other STALE fixture (100-200
    days past a 30-90 day window) green."""
    window_days = 90
    measured_on = ACTIVITY_DATE - timedelta(days=window_days + 1)
    anchor = _benchmark(measured_on)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=window_days)

    assert reading.age is not None
    assert reading.age.age_days == window_days + 1
    assert reading.outcome is StalenessOutcome.STALE


def test_age_zero_measured_on_activity_date_is_current() -> None:
    """Sign boundary: measured exactly on the activity's own date --
    age_days == 0 -- is CURRENT, not RETROACTIVE."""
    anchor = _benchmark(ACTIVITY_DATE)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.age is not None
    assert reading.age.age_days == 0
    assert reading.outcome is StalenessOutcome.CURRENT


def test_age_negative_one_measured_one_day_after_is_retroactive() -> None:
    """Sign boundary: measured one day after the activity -- age_days == -1
    -- is RETROACTIVE, not CURRENT and not STALE."""
    measured_on = ACTIVITY_DATE + timedelta(days=1)
    anchor = _benchmark(measured_on, applies_from=ACTIVITY_DATE)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.age is not None
    assert reading.age.age_days == -1
    assert reading.outcome is StalenessOutcome.RETROACTIVE


def test_retroactive_anchor_measured_well_after_activity_no_ordering_guard() -> None:
    """Req 5.8: a benchmark measured well after the activity, declared to
    apply from on or before it, reaches RETROACTIVE -- unconditionally,
    with no pre-call ordering guard turning it into NOT_ASSESSED. This is
    the exact case the 2026-09-16 amendment exists for."""
    measured_on = ACTIVITY_DATE + timedelta(days=30)
    anchor = _benchmark(measured_on, applies_from=ACTIVITY_DATE - timedelta(days=1))
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.outcome is StalenessOutcome.RETROACTIVE
    assert reading.outcome is not StalenessOutcome.NOT_ASSESSED
    assert reading.outcome is not StalenessOutcome.STALE
    assert reading.anchor is anchor
    assert reading.age is not None
    assert reading.age.age_days == -30
    assert reading.not_assessed_reason is None


def test_retroactive_anchor_with_no_applies_from_still_reaches_retroactive() -> None:
    """Design: "A negative age without a declaration" -- a RETROACTIVE
    reading whose anchor carries no applies_from is unguarded, not a raise
    and not NOT_ASSESSED; this module does not enforce the store's own
    contract that such an anchor should be unreachable."""
    measured_on = ACTIVITY_DATE + timedelta(days=5)
    anchor = _benchmark(measured_on, applies_from=None)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.outcome is StalenessOutcome.RETROACTIVE
    assert reading.anchor.applies_from is None


def test_retroactive_iff_age_negative_positive_direction() -> None:
    """Invariant: outcome is RETROACTIVE if and only if age is not None and
    age.age_days < 0 -- positive direction: RETROACTIVE implies a negative
    age is present."""
    anchor = _benchmark(ACTIVITY_DATE + timedelta(days=1), applies_from=ACTIVITY_DATE)
    selected = _channel_load(anchor)

    reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert reading.outcome is StalenessOutcome.RETROACTIVE
    assert reading.age is not None
    assert reading.age.age_days < 0


def test_retroactive_iff_age_negative_negative_direction() -> None:
    """Invariant, negative direction: whenever age is present with a
    non-negative age_days, the outcome is never RETROACTIVE."""
    for delta_days in (0, 1, 90, 400):
        anchor = _benchmark(ACTIVITY_DATE - timedelta(days=delta_days))
        selected = _channel_load(anchor)

        reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

        assert reading.age is not None
        assert reading.age.age_days == delta_days
        assert reading.outcome is not StalenessOutcome.RETROACTIVE


def test_pure_same_inputs_same_output_called_twice() -> None:
    """Calling evaluate twice with the exact same arguments produces an
    equal reading both times, AND that reading is pinned against the age a
    clock-free computation over the fixed ``ACTIVITY_DATE`` fixture must
    produce (Req 5.4, 5.6). The second assertion is load-bearing: a
    function that reads `date.today()` instead of its `activity_date`
    argument would still satisfy `first == second` when called twice
    back-to-back with identical arguments, so equality-between-two-calls
    alone cannot distinguish "pure over its arguments" from "consults a
    clock that happens to agree with itself across two immediate calls" --
    pinning ``age_days`` against the fixture's own arithmetic closes that
    gap."""
    measured_on = ACTIVITY_DATE - timedelta(days=200)
    anchor = _benchmark(measured_on)
    selected = _channel_load(anchor)

    first = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)
    second = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

    assert first == second
    assert first.outcome is StalenessOutcome.STALE
    assert first.age is not None
    assert first.age.age_days == (ACTIVITY_DATE - measured_on).days == 200


def test_window_days_is_genuinely_threaded_not_a_hardcoded_default() -> None:
    """Settings/parameter-threading trap (bit tasks 1.3, 2.3, 2.4): the same
    age_days produces STALE at a narrow window and CURRENT at a wide one --
    only possible if window_days is genuinely read from the argument, not a
    hardcoded default."""
    measured_on = ACTIVITY_DATE - timedelta(days=100)
    anchor = _benchmark(measured_on)
    selected = _channel_load(anchor)

    narrow = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=30)
    wide = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=365)

    assert narrow.age is not None
    assert wide.age is not None
    assert narrow.age.age_days == wide.age.age_days == 100
    assert narrow.outcome is StalenessOutcome.STALE
    assert wide.outcome is StalenessOutcome.CURRENT


def test_no_input_reaches_not_assessed_on_ordering_of_the_two_dates() -> None:
    """Design: the withdrawn guard would have turned an anchor measured
    after the activity into NOT_ASSESSED. With activity_date present, no
    ordering of measured_on against activity_date reaches NOT_ASSESSED --
    only the absent-date path does."""
    for measured_on in (
        ACTIVITY_DATE - timedelta(days=1),
        ACTIVITY_DATE,
        ACTIVITY_DATE + timedelta(days=1),
        ACTIVITY_DATE + timedelta(days=500),
    ):
        applies_from = (
            None if measured_on <= ACTIVITY_DATE else ACTIVITY_DATE - timedelta(days=1)
        )
        anchor = _benchmark(measured_on, applies_from=applies_from)
        selected = _channel_load(anchor)

        reading = evaluate(selected, activity_date=ACTIVITY_DATE, window_days=90)

        assert reading.outcome is not StalenessOutcome.NOT_ASSESSED
