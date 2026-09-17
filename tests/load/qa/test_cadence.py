"""Tests for the cadence-lock *verdict* layer (``qa/cadence.py``'s
``detect``, ``CadenceLockOutcome`` and ``CadenceLockReading`` -- the
measurement layer, ``paired_presence`` and ``span_statistics``, is task
2.1's and is tested in ``tests/load/qa/test_cadence_spans.py``, which this
task does not touch).

Covers Requirements 1.3, 1.4, 1.5, 1.8, 1.10, 2.2, 2.5, 2.6, 2.7, 2.8, 2.9 --
see ``.kiro/specs/activity-qa-flags/requirements.md`` and the "Domain --
src/fitdocs/load/qa/cadence.py" / "CadenceLockDetector" component (including
the "cadence-lock decision" flowchart under System Flows) in design.md.

Constructed streams only -- the athlete's real activity corpus never enters
this repository (Req 2.11). This module builds every value it needs
directly; it does not add new shared builders to ``conftest.py`` (task
2.1's alone).
"""

from __future__ import annotations

import pytest

from fitdocs.load.qa.cadence import CadenceLockOutcome, CadenceLockReading, detect
from fitdocs.load.qa.types import FlagSettings
from fitdocs.model import Modality
from tests.load.qa.conftest import make_samples, make_time_s


def _settings(**overrides: object) -> FlagSettings:
    return FlagSettings(**overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Gate 1 (2.8): running only, checked before anything else
# ---------------------------------------------------------------------------


def test_not_assessed_for_non_running_modality() -> None:
    """A fully paired, well-formed running-shaped stream is still
    not-assessed when the activity's modality is not RUN -- the check is
    undefined there, not merely untriggered (Req 2.8)."""
    time_s = make_time_s(7, dt=20.0)
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    heart_rate = tuple(int(c * 2) for c in cadence)
    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)

    reading = detect(samples, modality=Modality.BIKE, settings=_settings())

    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.locked_duration_s is None
    assert reading.paired_coverage is None
    assert reading.spans_assessed == 0
    assert reading.not_assessed_reason is not None
    assert "bike" in reading.not_assessed_reason


def test_not_assessed_reason_names_the_specific_modality() -> None:
    """A different non-running modality gets its own name in the reason,
    not a generic "wrong modality" string -- confirms the reason is built
    from the actual modality, not a constant (Req 2.8)."""
    time_s = make_time_s(7, dt=20.0)
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    heart_rate = tuple(int(c * 2) for c in cadence)
    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)

    reading = detect(samples, modality=Modality.SWIM, settings=_settings())

    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.not_assessed_reason is not None
    assert "swim" in reading.not_assessed_reason
    assert "bike" not in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# Gate 2 (2.6): no recorded cadence value anywhere
# ---------------------------------------------------------------------------


def test_not_assessed_for_wholly_absent_cadence_stream() -> None:
    time_s = make_time_s(20, dt=20.0)
    heart_rate = tuple(150 for _ in time_s)
    samples = make_samples(
        time_s, heart_rate_bpm=heart_rate, cadence_rpm=(None,) * len(time_s)
    )

    reading = detect(samples, modality=Modality.RUN, settings=_settings())

    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.locked_duration_s is None
    assert reading.paired_coverage is None
    assert reading.spans_assessed == 0
    assert reading.not_assessed_reason is not None
    assert "absent" in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# Gate order (2.8 before 2.6): a fixture failing both must name the first
# ---------------------------------------------------------------------------


def test_gate_order_names_modality_not_absent_stream_when_both_fail() -> None:
    """Non-running modality *and* wholly absent cadence stream both fail on
    this fixture; the reading must name the modality (gate 1), proving the
    fixed order is enforced rather than incidental -- a reading that
    happened to check gate 2 first would instead report the absent stream."""
    time_s = make_time_s(10, dt=20.0)
    heart_rate = tuple(150 for _ in time_s)
    samples = make_samples(
        time_s, heart_rate_bpm=heart_rate, cadence_rpm=(None,) * len(time_s)
    )

    reading = detect(samples, modality=Modality.OTHER, settings=_settings())

    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.not_assessed_reason is not None
    assert "other" in reading.not_assessed_reason
    assert "absent" not in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# Gate 3 (2.7): paired coverage, at-or-above boundary
# ---------------------------------------------------------------------------


def _coverage_boundary_samples(*, paired_count: int) -> tuple:
    """11 evenly spaced samples (10 one-second intervals). The first
    ``paired_count`` samples (of the first 10) carry both heart rate and
    cadence; the remainder of the first 10 carry neither. Index 10 is left
    unpaired -- it only extends the paired *time_s* range and is never one
    of the ten dt intervals `` stream_coverage`` weights (Req 8.1, 8.2)."""
    time_s = make_time_s(11, dt=1.0)
    heart_rate: list[int | None] = [None] * 11
    cadence: list[float | None] = [None] * 11
    for i in range(paired_count):
        heart_rate[i] = 150
        cadence[i] = 80.0
    return make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)


def test_paired_coverage_exactly_at_minimum_passes_the_gate() -> None:
    """Coverage exactly equal to the configured minimum (0.50 default) must
    pass gate 3 -- proven by reaching a *different* not-assessed reason
    (gate 4's span-width shortfall, since this fixture's paired extent is
    only 4s wide, far short of the default 120s window) rather than the
    coverage reason. If gate 3 used a strict ``>`` this exact-boundary
    fixture would instead fail there, with the coverage reason."""
    samples = _coverage_boundary_samples(paired_count=5)

    reading = detect(samples, modality=Modality.RUN, settings=_settings())

    assert reading.paired_coverage is not None
    assert reading.paired_coverage.fraction == pytest.approx(0.5)
    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.not_assessed_reason is not None
    assert "coverage" not in reading.not_assessed_reason
    assert "span" in reading.not_assessed_reason


def test_paired_coverage_just_below_minimum_fails_the_gate() -> None:
    """Coverage one interval short of the minimum (0.40 vs the 0.50
    default) must fail gate 3, naming the coverage reason -- the converse
    of the exact-boundary case above."""
    samples = _coverage_boundary_samples(paired_count=4)

    reading = detect(samples, modality=Modality.RUN, settings=_settings())

    assert reading.paired_coverage is not None
    assert reading.paired_coverage.fraction == pytest.approx(0.4)
    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.locked_duration_s is None
    assert reading.spans_assessed == 0
    assert reading.not_assessed_reason is not None
    assert "coverage" in reading.not_assessed_reason


def test_not_assessed_when_coverage_is_undefined() -> None:
    """``stream_coverage`` itself returns ``None`` (fewer than two samples,
    or no positive inter-sample span) -- gate 3 must still fail rather than
    dereference a coverage that does not exist, carrying ``paired_coverage``
    as ``None`` and naming no fabricated observed figure (Req 1.5, 1.8).
    Pinned literally: the reason must say the figure is undefined, not a
    fabricated "0.000" standing in for a coverage that was never computed."""
    samples = make_samples((0.0,), heart_rate_bpm=(150,), cadence_rpm=(80.0,))

    reading = detect(samples, modality=Modality.RUN, settings=_settings())

    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.paired_coverage is None
    assert reading.not_assessed_reason is not None
    assert "coverage" in reading.not_assessed_reason
    assert "undefined" in reading.not_assessed_reason
    assert "0.000" not in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# Gate 4 (2.7): at least one full span can be formed
# ---------------------------------------------------------------------------


def test_not_assessed_when_no_full_span_can_be_formed() -> None:
    """Full paired coverage (1.0) but a paired extent far shorter than the
    configured window: gate 3 passes cleanly, gate 4 fails."""
    time_s = make_time_s(4, dt=10.0)  # paired extent: 30s, default window 120s
    heart_rate = tuple(150 for _ in time_s)
    cadence = tuple(80.0 for _ in time_s)
    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)

    reading = detect(samples, modality=Modality.RUN, settings=_settings())

    assert reading.paired_coverage is not None
    assert reading.paired_coverage.fraction == pytest.approx(1.0)
    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.locked_duration_s is None
    assert reading.spans_assessed == 0
    assert reading.not_assessed_reason is not None
    assert "span" in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# Gates 5/6 (2.2, 2.5): summed locked duration vs the configured minimum,
# at-or-above boundary
# ---------------------------------------------------------------------------


def _multi_span_samples(*, locked_spans: int, clear_spans: int) -> tuple:
    """``locked_spans`` 60s windows whose HR matches full-cycle cadence
    exactly (r=1.0, delta=0 -- locked), followed by ``clear_spans`` 60s
    windows whose HR is offset 40 bpm from full-cycle (r=1.0, delta=40 --
    never locked, per the conjunction). One second sampling throughout so
    the paired extent divides evenly into 60s windows with no remainder."""
    total_spans = locked_spans + clear_spans
    n = total_spans * 60 + 1  # +1 so the last window's end boundary is reached
    time_s = make_time_s(n, dt=1.0)
    cadence = tuple(80.0 + (i % 10) * 0.5 for i in range(n))
    heart_rate: list[int] = []
    for i in range(n):
        span_index = i // 60
        full_cycle = cadence[i] * 2
        if span_index < locked_spans:
            heart_rate.append(int(full_cycle))
        else:
            heart_rate.append(int(full_cycle) + 40)
    return make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)


def _pattern_span_samples(pattern: tuple[bool, ...]) -> tuple:
    """One 60s window per entry of ``pattern`` (``True`` locked-eligible --
    HR matches full-cycle cadence exactly; ``False`` never locked-eligible
    -- HR is offset 40 bpm), in the given order. Unlike
    ``_multi_span_samples``, which always groups every locked window before
    every clear one, this lets a test place locked spans non-contiguously
    -- e.g. locked/clear/locked/clear/locked -- so summing every locked
    span's duration is pinned as genuinely distinct from taking the longest
    *consecutive* run of locked spans (Req 2.5)."""
    n = len(pattern) * 60 + 1  # +1 so the last window's end boundary is reached
    time_s = make_time_s(n, dt=1.0)
    cadence = tuple(80.0 + (i % 10) * 0.5 for i in range(n))
    heart_rate: list[int] = []
    for i in range(n):
        span_index = min(i // 60, len(pattern) - 1)
        full_cycle = cadence[i] * 2
        if pattern[span_index]:
            heart_rate.append(int(full_cycle))
        else:
            heart_rate.append(int(full_cycle) + 40)
    return make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)


def test_non_contiguous_locked_spans_are_summed_not_taken_as_longest_run() -> None:
    """Locked/clear/locked/clear/locked (60s each): the summed locked
    duration is 180s -- reaching the configured minimum and reporting
    LOCKED -- even though no single *consecutive* run of locked spans
    reaches 120s. A longest-consecutive-run implementation would see at
    most 60s and report CLEAR; only a genuine sum distinguishes the two
    (Req 2.5)."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=180)
    samples = _pattern_span_samples((True, False, True, False, True))

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 5
    assert reading.locked_duration_s == pytest.approx(180.0)
    assert reading.outcome is CadenceLockOutcome.LOCKED


def test_locked_when_summed_duration_exactly_meets_the_minimum() -> None:
    """Three 60s locked spans sum to exactly 180s, the configured minimum
    -- must be LOCKED, pinning the ``>=`` half of gate 5/6 (design's
    flowchart: "at or above the minimum")."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=180)
    samples = _multi_span_samples(locked_spans=3, clear_spans=0)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 3
    assert reading.locked_duration_s == pytest.approx(180.0)
    assert reading.required_duration_s == 180
    assert reading.outcome is CadenceLockOutcome.LOCKED
    assert reading.not_assessed_reason is None
    assert reading.paired_coverage is not None
    assert reading.paired_coverage.fraction == pytest.approx(1.0)


def test_clear_when_summed_duration_is_one_span_short_of_the_minimum() -> None:
    """Only two of three 60s spans are locked -- 120s, one whole span-width
    short of the 180s minimum -- must be CLEAR, not LOCKED, and the reading
    must still carry the near-miss sum and the required minimum (Req 2.5)."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=180)
    samples = _multi_span_samples(locked_spans=2, clear_spans=1)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 3
    assert reading.locked_duration_s == pytest.approx(120.0)
    assert reading.required_duration_s == 180
    assert reading.outcome is CadenceLockOutcome.CLEAR
    assert reading.not_assessed_reason is None
    assert reading.paired_coverage is not None
    assert reading.paired_coverage.fraction == pytest.approx(1.0)


def test_clear_with_zero_locked_duration_is_zero_not_none() -> None:
    """When every gate through span-formation passes but no span is
    locked, ``locked_duration_s`` is ``0.0`` -- never ``None``, which is
    reserved for NOT_ASSESSED readings alone (Req 1.8)."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=180)
    samples = _multi_span_samples(locked_spans=0, clear_spans=3)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 3
    assert reading.locked_duration_s == 0.0
    assert reading.locked_duration_s is not None
    assert reading.outcome is CadenceLockOutcome.CLEAR


# ---------------------------------------------------------------------------
# The conjunction, at whole-activity scale (Req 2.2, 2.9) -- seated between
# the two failure modes on span count, not at a shared extremum
# ---------------------------------------------------------------------------


def test_high_correlation_large_offset_activity_is_clear_not_locked() -> None:
    """Strong association throughout (r=1.0) but a large constant offset:
    never locked on any span, so the whole activity is CLEAR (Req 2.2,
    2.9)."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=120)
    n = 3 * 60 + 1
    time_s = make_time_s(n, dt=1.0)
    cadence = tuple(80.0 + (i % 10) * 0.5 for i in range(n))
    heart_rate = tuple(int(c * 2) + 40 for c in cadence)
    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 3
    assert reading.locked_duration_s == 0.0
    assert reading.outcome is CadenceLockOutcome.CLEAR


def test_low_correlation_close_offset_activity_is_clear_not_locked() -> None:
    """Numerically close values throughout but weak association: never
    locked on any span, so the whole activity is CLEAR (Req 2.2, 2.9)."""
    settings = _settings(cadence_lock_window_s=140, cadence_lock_min_duration_s=140)
    time_s = make_time_s(8, dt=20.0)  # one 140s span, indices 0..6 inclusive
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0, 94.0)
    full_cycle = [c * 2 for c in cadence]
    offsets = [4, -4, 4, -4, 4, -4, 4, -4]
    heart_rate = tuple(int(v + off) for v, off in zip(full_cycle, offsets, strict=True))
    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 1
    assert reading.locked_duration_s == 0.0
    assert reading.outcome is CadenceLockOutcome.CLEAR


def test_both_together_sustained_is_locked() -> None:
    """Strong association *and* numerical closeness, sustained over enough
    spans to clear the minimum duration: LOCKED (Req 2.2, 2.9). The
    non-contiguous-arrangement fixture above (Req 2.5) is what actually
    distinguishes a real sum from a longest-consecutive-run reading; this
    fixture only pins the ordinary contiguous case."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=120)
    samples = _multi_span_samples(locked_spans=3, clear_spans=0)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 3
    assert reading.locked_duration_s == pytest.approx(180.0)
    assert reading.outcome is CadenceLockOutcome.LOCKED


def test_per_limb_cadence_match_is_clear_not_locked() -> None:
    """Heart rate matching the *per-limb* cadence value (not doubled to
    full-cycle) must not be locked: the median delta against the full-cycle
    comparison is far outside the closeness threshold, even though the
    correlation is perfect either way (Req 2.3, 2.9)."""
    settings = _settings(cadence_lock_window_s=60, cadence_lock_min_duration_s=120)
    n = 3 * 60 + 1
    time_s = make_time_s(n, dt=1.0)
    cadence = tuple(80.0 + (i % 10) * 0.5 for i in range(n))
    heart_rate = tuple(int(c) for c in cadence)  # per-limb, not full-cycle
    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)

    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == 3
    assert reading.locked_duration_s == 0.0
    assert reading.outcome is CadenceLockOutcome.CLEAR


# ---------------------------------------------------------------------------
# Total / never-raises (Req 1.10)
# ---------------------------------------------------------------------------


def test_never_raises_on_empty_samples() -> None:
    samples = make_samples((), heart_rate_bpm=(), cadence_rpm=())

    reading = detect(samples, modality=Modality.RUN, settings=_settings())

    assert reading.outcome is CadenceLockOutcome.NOT_ASSESSED
    assert reading.not_assessed_reason is not None


def test_reading_carries_required_duration_on_every_outcome() -> None:
    """``required_duration_s`` is always the configured minimum, on
    NOT_ASSESSED readings too -- not only on LOCKED/CLEAR ones."""
    settings = _settings(cadence_lock_min_duration_s=222)
    samples = make_samples((0.0,), heart_rate_bpm=(150,), cadence_rpm=(80.0,))

    reading: CadenceLockReading = detect(
        samples, modality=Modality.RUN, settings=settings
    )

    assert reading.required_duration_s == 222
