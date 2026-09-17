"""Tests for the cadence-lock measurement layer (``qa/cadence.py`` --
``paired_presence`` and ``span_statistics`` only; ``detect`` and the verdict
machinery are task 2.2's, added to the same module later and tested in
``tests/load/qa/test_cadence.py``, which this task does not touch).

Covers Requirements 2.1, 2.3, 2.4, 2.10, 8.1, 8.2 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and the "Domain --
src/fitdocs/load/qa/cadence.py" / "CadenceLockDetector" component in
design.md.

Constructed streams only -- the athlete's real activity corpus never enters
this repository (Req 2.11).
"""

from __future__ import annotations

import pytest

from fitdocs.load.channels.sufficiency import stream_coverage
from fitdocs.load.qa.cadence import paired_presence, span_statistics
from fitdocs.load.qa.types import FlagSettings
from tests.load.qa.conftest import make_samples, make_time_s

# ---------------------------------------------------------------------------
# paired_presence / stream_coverage composition (Req 8.1, 8.2)
# ---------------------------------------------------------------------------


def test_paired_presence_marks_only_fully_paired_indices() -> None:
    time_s = make_time_s(5, dt=1.0)
    samples = make_samples(
        time_s,
        heart_rate_bpm=(120, None, 140, 150, None),
        cadence_rpm=(80.0, 82.0, None, 88.0, 90.0),
    )

    presence = paired_presence(samples)

    # Paired at indices 0 and 3 only: index 1 lacks HR, index 2 lacks
    # cadence, index 4 lacks HR.
    assert presence[0] is not None
    assert presence[1] is None
    assert presence[2] is None
    assert presence[3] is not None
    assert presence[4] is None


def test_paired_presence_coverage_matches_stream_coverage_time_weighting() -> None:
    """The paired-coverage figure this module produces is exactly
    ``stream_coverage``'s own time-weighted result over the same presence
    array -- one coverage definition, reused, not restated (Req 8.1, 8.2)."""
    # Non-uniform spacing so time-weighting actually matters: dt values of
    # 1, 2, 3, 4 between the five samples.
    time_s = (0.0, 1.0, 3.0, 6.0, 10.0)
    samples = make_samples(
        time_s,
        heart_rate_bpm=(120, 122, None, 128, 130),
        cadence_rpm=(80.0, 81.0, 83.0, None, 90.0),
    )
    # Paired at indices 0, 1, 4. Earlier-sample-covered intervals:
    # [0,1) paired (idx0) -> 1s, [1,3) paired (idx1) -> 2s,
    # [3,6) not paired (idx2 hr missing) -> 0s covered,
    # [6,10) not paired (idx3 cadence missing) -> 0s covered.
    # total_s = 1+2+3+4 = 10, covered_s = 1+2 = 3.

    presence = paired_presence(samples)
    coverage = stream_coverage(samples, presence, stream="cadence-lock-paired")

    assert coverage is not None
    assert coverage.total_s == pytest.approx(10.0)
    assert coverage.covered_s == pytest.approx(3.0)
    assert coverage.fraction == pytest.approx(0.3)

    # And it matches a hand-built presence array reflecting the identical
    # pairing information, proving paired_presence's own float values carry
    # no extra information stream_coverage depends on beyond presence.
    hand_presence: tuple[float | None, ...] = (1.0, 1.0, None, None, 1.0)
    hand_coverage = stream_coverage(samples, hand_presence, stream="hand")
    assert coverage.covered_s == hand_coverage.covered_s  # type: ignore[union-attr]
    assert coverage.total_s == hand_coverage.total_s  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# span division: width, anchoring, full-cycle conversion (Req 2.1, 2.3, 2.4)
# ---------------------------------------------------------------------------


def _settings(**overrides: object) -> FlagSettings:
    return FlagSettings(**overrides)  # type: ignore[arg-type]


def test_spans_are_anchored_at_first_paired_sample_not_at_time_zero() -> None:
    """Cadence is unrecorded for the first 30s; the span boundaries must
    start at the first *paired* sample (t=30), not at t=0 (Req 2.1)."""
    time_s = make_time_s(20, dt=10.0)  # 0, 10, ..., 190
    heart_rate = tuple(120 for _ in time_s)
    # cadence absent for t < 30 (indices 0, 1, 2), present from index 3 on.
    cadence = tuple(None if t < 30 else 85.0 for t in time_s)

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=60, settings=_settings())

    assert len(spans) >= 1
    assert spans[0].start_s == pytest.approx(30.0)


def test_span_width_and_full_width_only_are_respected() -> None:
    """A 250s paired stream at a 100s window yields exactly two full-width
    spans; the trailing 50s remainder forms no third span (Req 2.4, 2.7)."""
    time_s = make_time_s(26, dt=10.0)  # 0..250
    heart_rate = tuple(120 + i for i in range(26))
    cadence = tuple(80.0 + i for i in range(26))

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=100, settings=_settings())

    assert [s.start_s for s in spans] == [0.0, 100.0]
    assert all(s.duration_s == pytest.approx(100.0) for s in spans)


def test_no_full_span_yields_empty_result() -> None:
    """A paired stream shorter than the configured window forms no span at
    all -- the way task 2.2 detects "no full span can be formed" (Req 2.7)."""
    time_s = make_time_s(5, dt=10.0)  # 0..40, 40s of paired data
    samples = make_samples(
        time_s,
        heart_rate_bpm=tuple(120 for _ in time_s),
        cadence_rpm=tuple(80.0 for _ in time_s),
    )

    spans = span_statistics(samples, window_s=120, settings=_settings())

    assert spans == ()


def test_span_universe_is_bounded_by_the_paired_extent_not_the_whole_activity() -> None:
    """The span universe runs to the *last paired sample*'s own time, not
    to the last recorded sample of the activity: pairing stops at t=650 but
    the activity's own last sample is at t=900. At a 120s window only spans
    fully inside [0, 650] are formed -- none starting at 600, whose 120s
    window would run past the paired extent (Req 2.1, 2.7)."""
    time_s = make_time_s(19, dt=50.0)  # 0, 50, ..., 900
    cadence = tuple(80.0 + i if t <= 650 else None for i, t in enumerate(time_s))
    heart_rate = tuple(
        int((80.0 + i) * 2) if t <= 650 else None for i, t in enumerate(time_s)
    )

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=120, settings=_settings())

    assert [s.start_s for s in spans] == [0.0, 120.0, 240.0, 360.0, 480.0]


def test_full_cycle_conversion_is_applied_not_the_raw_per_limb_number() -> None:
    """Heart rate is constructed to match cadence x2 (full-cycle) exactly,
    not cadence x1 (raw per-limb). Flipping the STEPS_PER_CADENCE_REVOLUTION
    factor from 2 to 1 in the implementation must turn this span's
    ``locked`` from True to False: at raw per-limb cadence the median delta
    is ~85 bpm, far above the default 5.0 bpm closeness threshold, even
    though the correlation (scale-invariant) stays 1.0 either way (Req 2.3).
    """
    time_s = make_time_s(7, dt=20.0)  # 0..120, one full 120s span
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    heart_rate = tuple(int(c * 2) for c in cadence)  # matches full-cycle exactly

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(
        samples, window_s=120, settings=_settings()
    )  # defaults: min_correlation 0.90, max_delta 5.0

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation == pytest.approx(1.0)
    assert span.median_delta_bpm == pytest.approx(0.0)
    assert span.locked is True


def test_high_correlation_but_large_offset_span_is_not_locked() -> None:
    """The lock decision is conjunctive (Req 2.2): a span whose association
    is strong (r=1.0, well above the 0.90 minimum) but whose numerical
    offset is far outside the closeness threshold must not be locked. This
    pins the ``and median_delta_bpm <= ...`` half of the conjunction --
    dropping it (leaving only the correlation gate) would flip this
    assertion, since correlation alone already clears its own threshold."""
    time_s = make_time_s(7, dt=20.0)
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    # Offset by a constant 40 bpm above the full-cycle value: correlation is
    # unaffected by a constant additive offset (still 1.0), but the median
    # delta is 40 bpm, far above the default 5.0 bpm threshold.
    heart_rate = tuple(int(c * 2) + 40 for c in cadence)

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=120, settings=_settings())

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation == pytest.approx(1.0)
    assert span.median_delta_bpm == pytest.approx(40.0)
    assert span.locked is False


def test_locked_when_correlation_exactly_meets_the_configured_minimum() -> None:
    """``locked`` is true when the correlation is *exactly* the configured
    minimum (``SpanStatistic.locked``'s own docstring: "at or above") --
    pins the ``>=`` half of the correlation gate, so flipping it to ``>``
    reds this test."""
    time_s = make_time_s(7, dt=20.0)
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    heart_rate = tuple(int(c * 2) for c in cadence)  # exact match -> r == 1.0

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(
        samples,
        window_s=120,
        settings=_settings(cadence_lock_min_correlation=1.0),
    )

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation == pytest.approx(1.0)
    assert span.median_delta_bpm == pytest.approx(0.0)
    assert span.locked is True


def test_locked_when_median_delta_exactly_meets_the_configured_maximum() -> None:
    """``locked`` is true when the median delta is *exactly* the configured
    maximum (``SpanStatistic.locked``'s own docstring: "at or below") --
    pins the ``<=`` half of the closeness gate, so flipping it to ``<`` reds
    this test."""
    time_s = make_time_s(7, dt=20.0)
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    # A constant +5 bpm offset from full-cycle: correlation is unaffected by
    # a constant additive offset (still 1.0), and every delta is exactly
    # the default 5.0 bpm maximum.
    heart_rate = tuple(int(c * 2) + 5 for c in cadence)

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=120, settings=_settings())

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation == pytest.approx(1.0)
    assert span.median_delta_bpm == pytest.approx(5.0)
    assert span.locked is True


def test_close_offset_but_low_correlation_span_is_not_locked() -> None:
    """The converse half of the conjunction (Req 2.2): a span whose values
    are numerically close (median delta well under the 5.0 bpm threshold)
    but whose association is weak must not be locked either."""
    time_s = make_time_s(7, dt=20.0)
    cadence = (80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0)
    full_cycle = [c * 2 for c in cadence]
    # Perturb the sequence order so it no longer tracks cadence (breaking
    # correlation) while keeping every value within 5 bpm of its own
    # full-cycle counterpart (keeping the median delta small).
    offsets = [4, -4, 4, -4, 4, -4, 0]
    heart_rate = tuple(int(v + off) for v, off in zip(full_cycle, offsets, strict=True))

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=120, settings=_settings())

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation is not None
    assert span.correlation < 0.90
    assert span.median_delta_bpm <= 5.0
    assert span.locked is False


# ---------------------------------------------------------------------------
# degeneracy: correlation is None, never fabricated (Req 2.1)
# ---------------------------------------------------------------------------


def test_constant_cadence_span_has_no_correlation_and_is_never_locked() -> None:
    """A span with zero variance in the cadence series (e.g. a device
    reporting a frozen cadence value) cannot demonstrate a real statistical
    association: correlation is None, not fabricated, and the span is never
    locked, even though the median delta may happen to be small."""
    time_s = make_time_s(7, dt=20.0)
    cadence = tuple(85.0 for _ in time_s)  # constant -> zero variance
    heart_rate = tuple(170 for _ in time_s)  # matches full-cycle exactly (delta 0)

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=120, settings=_settings())

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation is None
    assert span.median_delta_bpm == pytest.approx(0.0)
    assert span.locked is False


def test_span_with_single_paired_sample_has_no_correlation() -> None:
    """Fewer than two paired samples in a span cannot support a correlation
    computation; the span still reports a median delta (a median of one
    value is honest) but no correlation and is never locked."""
    # Two samples 20s apart form one 20s-wide span only if window_s <= 20;
    # use window_s=20 so exactly one paired point falls in [0, 20).
    time_s = (0.0, 20.0, 40.0)
    samples = make_samples(
        time_s,
        heart_rate_bpm=(170, None, 175),
        cadence_rpm=(85.0, None, 87.0),
    )

    spans = span_statistics(samples, window_s=20, settings=_settings())

    # Paired samples are at t=0 and t=40 only (t=20 has neither). Anchor is
    # t=0; spans are [0,20) and [20,40). [0,20) holds the t=0 point and is
    # emitted, degenerate. [20,40) holds *no* paired point at all (t=20 is
    # unpaired, t=40 is the span's own exclusive upper bound) and must be
    # omitted entirely rather than emitted as a fabricated empty-window
    # span -- pinned here as exactly one span, not merely "at least one".
    assert [s.start_s for s in spans] == [0.0]
    first = spans[0]
    assert first.correlation is None
    assert first.median_delta_bpm == pytest.approx(abs(170 - 85.0 * 2))


def test_span_with_exactly_two_paired_samples_has_a_correlation() -> None:
    """Exactly two paired samples is the minimum for a correlation to be
    computed at all (``SpanStatistic.correlation``'s own docstring: "fewer
    than two paired samples"). Pins that the threshold is two, not three --
    raising the internal minimum-sample guard by one would flip this span's
    correlation to ``None``."""
    # A third paired sample at t=20 only extends the paired range so the
    # [0, 20) span's own end boundary is reachable; it falls outside that
    # half-open span and never contributes to it.
    time_s = (0.0, 10.0, 20.0)
    samples = make_samples(
        time_s,
        heart_rate_bpm=(170, 174, 999),
        cadence_rpm=(85.0, 87.0, 50.0),
    )

    spans = span_statistics(samples, window_s=20, settings=_settings())

    assert len(spans) == 1
    span = spans[0]
    assert span.correlation is not None
    assert abs(span.correlation) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# temporal, per-span, not single-point (Req 2.1, 2.4) -- defeats a
# whole-activity-average implementation
# ---------------------------------------------------------------------------


def test_locking_is_decided_per_span_not_as_a_whole_activity_average() -> None:
    """First span tracks tightly (locked-eligible); second span is
    perfectly *negatively* correlated (never locked-eligible: r = -1.0, far
    below the 0.90 minimum). A whole-activity-average implementation would
    report one aggregate figure and could not produce two spans that
    disagree; this fixture requires genuinely independent per-span
    decisions (Req 2.1, 2.4)."""
    # 13 points, 0..120: span0 = [0,60) (indices 0-5), span1 = [60,120)
    # (indices 6-11). Index 12 (t=120) is a paired placeholder that only
    # extends the paired range to 120s so span1's end boundary is reached;
    # it falls outside both half-open spans and is never used in either.
    time_s = make_time_s(13, dt=10.0)
    cadence = (
        80.0,
        82.0,
        84.0,
        86.0,
        88.0,
        90.0,
        80.0,
        82.0,
        84.0,
        86.0,
        88.0,
        90.0,
        99.0,
    )

    span0_hr = tuple(int(c * 2) for c in cadence[:6])  # matches full-cycle exactly
    # A perfectly *decreasing* HR against the *increasing* span1 cadence:
    # both are arithmetic sequences with a constant step, opposite sign, so
    # their Pearson correlation is exactly -1.0 -- far below the 0.90
    # minimum, and never locked-eligible regardless of the closeness gate.
    span1_hr = (200, 196, 192, 188, 184, 180)
    placeholder_hr = (180,)
    heart_rate = span0_hr + span1_hr + placeholder_hr

    samples = make_samples(time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)
    spans = span_statistics(samples, window_s=60, settings=_settings())

    assert len(spans) == 2
    assert spans[0].locked is True
    assert spans[0].correlation == pytest.approx(1.0)
    assert spans[1].locked is False
    assert spans[1].correlation == pytest.approx(-1.0)
    assert spans[0].locked != spans[1].locked
