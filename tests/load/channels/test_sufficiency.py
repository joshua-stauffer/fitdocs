"""Tests for the shared data-sufficiency gate (``sufficiency.py``).

Covers Requirements 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10 --
see ``.kiro/specs/load-channels/requirements.md`` and the "Domain --
src/fitdocs/load/channels/sufficiency.py" / "SufficiencyGate" component in
design.md (lines 665-743).

The fixtures that pin the time-weighting rule itself -- they include
``test_dropout_reduces_coverage_by_exactly_the_expected_time_weighted_fraction``,
``test_device_pause_credited_to_its_pre_pause_sample_not_the_post_pause_sample``,
``test_coverage_exactly_at_the_minimum_passes_the_gate``,
``test_explicit_minimum_wins_over_a_strict_configured_per_channel_override``
and ``test_explicit_minimum_wins_over_a_lenient_configured_per_channel_override``
-- use **non-uniform** sample spacing deliberately: with uniform spacing,
time-weighted coverage and a plain covered-interval-count percentage are the
same number, so a uniformly-spaced fixture would pin nothing about *which*
of the two the gate computes (2.2). Not every fixture in this module needs
that property -- most exercise a different rule (order, absence, boundary,
override resolution) where spacing is incidental.
"""

from __future__ import annotations

import pytest

from fitdocs.load.channels.sufficiency import evaluate, stream_coverage
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    InsufficiencyReason,
    StreamCoverage,
    SufficiencySettings,
)
from fitdocs.model import Samples

# ---------------------------------------------------------------------------
# fixture builder
# ---------------------------------------------------------------------------


def _samples(time_s: tuple[float, ...]) -> Samples:
    """A ``Samples`` whose non-time channels are irrelevant to this gate --
    the gate is handed its ``values`` array explicitly, so every channel
    array here stays all-``None`` of the right length."""
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=none_ints,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


# ---------------------------------------------------------------------------
# stream_coverage -- time-weighted measurement (2.2, 2.3, 2.9, 2.10)
# ---------------------------------------------------------------------------


def test_dropout_reduces_coverage_by_exactly_the_expected_time_weighted_fraction() -> (
    None
):
    """Non-uniform spacing: a 10 s dropout among short 1 s intervals. A
    sample-count percentage would report 5/6 present; time-weighted coverage
    must report the *time* fraction instead, which is far lower because the
    missing sample governs the longest interval."""
    time_s = (0.0, 1.0, 2.0, 12.0, 13.0, 14.0)
    values: tuple[int | None, ...] = (100, 100, None, 100, 100, 100)
    coverage = stream_coverage(_samples(time_s), values, stream="power")
    assert coverage is not None
    # total span: 1 + 1 + 10 + 1 + 1 = 14; covered: 1 + 1 + 1 + 1 = 4
    # (the interval governed by the None at index 2 is uncovered).
    assert coverage.total_s == pytest.approx(14.0)
    assert coverage.covered_s == pytest.approx(4.0)
    assert coverage.fraction == pytest.approx(4.0 / 14.0)
    # A sample-count percentage over 6 samples (5 non-None) would be 5/6,
    # nowhere near the correct time-weighted 4/14 -- pins that this is not
    # what got computed.
    assert coverage.fraction != pytest.approx(5.0 / 6.0)


def test_recorded_zero_counts_as_covered_distinctly_from_none() -> None:
    """A real ``0`` and a real ``None`` in the same fixture (CLAUDE.md's
    absent-data rule): the interval governed by the recorded zero must count
    as covered; the interval governed by ``None`` must not."""
    time_s = (0.0, 10.0, 20.0)
    values: tuple[int | None, ...] = (0, None, 5)
    coverage = stream_coverage(_samples(time_s), values, stream="power")
    assert coverage is not None
    assert coverage.total_s == pytest.approx(20.0)
    # Interval (0, 10) governed by index 0 == 0 -> covered.
    # Interval (10, 20) governed by index 1 == None -> not covered.
    assert coverage.covered_s == pytest.approx(10.0)
    assert coverage.fraction == pytest.approx(0.5)


def test_device_pause_credited_to_its_pre_pause_sample_not_the_post_pause_sample() -> (
    None
):
    """A long device-pause interval whose *earlier* sample carries a value
    but whose *later* (post-resume) sample does not: earlier-attribution
    must count the whole 600 s pause as covered; later-attribution would
    instead count a *different*, much smaller, interval as covered and the
    long pause as not -- the two attribution rules disagree sharply here."""
    time_s = (0.0, 1.0, 601.0, 602.0, 603.0)
    values: tuple[int | None, ...] = (100, 100, None, 100, 100)
    coverage = stream_coverage(_samples(time_s), values, stream="power")
    assert coverage is not None
    assert coverage.total_s == pytest.approx(603.0)
    # Earlier-attribution: intervals governed by idx 0 (1s), idx 1 (600s,
    # the pause), and idx 3 (1s) are covered; idx 2 (1s, None) is not.
    expected_earlier = 1.0 + 600.0 + 1.0
    assert coverage.covered_s == pytest.approx(expected_earlier)
    # Later-attribution would instead credit intervals governed by idx 1
    # (600s pause -> uncovered, since idx 2's later sample is None), idx 2
    # (1s, later idx3=100 -> covered) and idx 3 (1s, later idx4=100 ->
    # covered): 1(idx0->idx1 covered since idx1=100 present)+1+1 = tiny by
    # comparison with the pause excluded.
    expected_later = 1.0 + 1.0 + 1.0
    assert coverage.covered_s != pytest.approx(expected_later)
    assert coverage.fraction == pytest.approx(expected_earlier / 603.0)


def test_single_sample_yields_no_measurement() -> None:
    coverage = stream_coverage(_samples((0.0,)), (5,), stream="power")
    assert coverage is None


def test_zero_span_series_yields_no_measurement() -> None:
    coverage = stream_coverage(_samples((5.0, 5.0, 5.0)), (1, 2, 3), stream="power")
    assert coverage is None


def test_value_recorded_only_on_the_final_sample_yields_zero_coverage() -> None:
    """The degenerate case the design calls out explicitly: a value sitting
    only on the last sample governs no interval and contributes nothing."""
    time_s = (0.0, 60.0, 120.0)
    values: tuple[int | None, ...] = (None, None, 5)
    coverage = stream_coverage(_samples(time_s), values, stream="power")
    assert coverage is not None
    assert coverage.covered_s == pytest.approx(0.0)
    assert coverage.total_s == pytest.approx(120.0)


def test_stream_name_is_carried_onto_the_result() -> None:
    time_s = (0.0, 10.0)
    coverage = stream_coverage(_samples(time_s), (1, 1), stream="heart_rate")
    assert coverage is not None
    assert coverage.stream == "heart_rate"


# ---------------------------------------------------------------------------
# evaluate -- fixed order, typed outcomes, never raises (1.8, 2.1, 2.4, 2.5,
# 2.6, 2.7, 2.8, 2.9)
# ---------------------------------------------------------------------------

_SETTINGS = SufficiencySettings()  # defaults: min_duration_s=60, min_coverage=0.80


def test_no_measurable_span_reports_too_short_naming_zero_and_the_minimum() -> None:
    time_s = (0.0,)
    result = evaluate(
        _samples(time_s),
        (5,),
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.POWER
    assert result.reason is InsufficiencyReason.TOO_SHORT
    assert result.observed == pytest.approx(0.0)
    assert result.required == pytest.approx(60.0)


def test_span_below_minimum_duration_reports_too_short() -> None:
    """Paired with ``test_no_measurable_span_reports_too_short_naming_zero_
    and_the_minimum`` above, which asserts ``channel is ChannelId.POWER`` at
    this same TOO_SHORT construction site: together the two pin that the site
    propagates *whichever* channel the caller passed, on two distinct
    members, rather than merely differing from one hardcoded guess (Req
    2.8)."""
    time_s = (0.0, 10.0, 20.0)
    values: tuple[int | None, ...] = (1, 1, 1)
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.HEART_RATE,
        stream="heart_rate",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.TOO_SHORT
    assert result.observed == pytest.approx(20.0)
    assert result.required == pytest.approx(60.0)
    assert "heart_rate" in result.detail


def test_too_short_required_reflects_a_non_default_configured_minimum_duration() -> (
    None
):
    """Every other TOO_SHORT fixture in this module uses the default
    ``min_duration_s`` (60), so both assert ``required == 60.0`` -- a tied
    value that a hardcoded ``required=60.0`` at the construction site would
    satisfy without ever reading ``settings.min_duration_s``. A distinct
    configured minimum (200) defeats that: hardcoding a fixed 60.0 (or any
    other single constant) cannot pass both this fixture and the others."""
    settings = SufficiencySettings(min_duration_s=200)
    time_s = (0.0, 100.0)
    values: tuple[int | None, ...] = (1, 1)
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=settings,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT
    assert result.observed == pytest.approx(100.0)
    assert result.required == pytest.approx(200.0)


def test_span_exactly_at_the_minimum_duration_passes() -> None:
    """The minimum duration is a floor, not an exclusive bound: a span
    exactly equal to it must pass (2.6 says "below the minimum duration"
    fails, not "at or below")."""
    time_s = (0.0, 60.0)
    values: tuple[int | None, ...] = (1, 1)
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, StreamCoverage)
    assert result.total_s == pytest.approx(60.0)


def test_wholly_absent_stream_reports_stream_absent_when_duration_passes() -> None:
    time_s = (0.0, 10.0, 20.0, 90.0)
    values: tuple[int | None, ...] = (None, None, None, None)
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.HEART_RATE,
        stream="heart_rate",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.STREAM_ABSENT
    assert result.observed is None
    assert result.required is None
    assert "heart_rate" in result.detail


def test_wholly_absent_stream_on_a_different_channel_also_propagates_it() -> None:
    """Paired with the HEART_RATE fixture above at the same STREAM_ABSENT
    construction site, on a distinct channel: together the two pin that this
    site propagates whichever channel the caller passed, not a hardcoded
    one (Req 2.8)."""
    time_s = (0.0, 20.0, 40.0, 90.0)
    values: tuple[int | None, ...] = (None, None, None, None)
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.POWER
    assert result.reason is InsufficiencyReason.STREAM_ABSENT


def test_coverage_below_minimum_reports_stream_coverage_naming_both_values() -> None:
    time_s = (0.0, 30.0, 60.0, 90.0)
    values: tuple[int | None, ...] = (1, None, None, 1)
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert result.observed == pytest.approx(30.0 / 90.0)
    assert result.required == pytest.approx(0.80)
    assert "power" in result.detail


def test_coverage_exactly_at_the_minimum_passes_the_gate() -> None:
    """The minimum is a floor, not an exclusive bound: a fraction exactly
    equal to the configured minimum must pass (2.5 says "below the
    configured minimum" fails, not "at or below")."""
    time_s = (0.0, 80.0, 100.0)
    values: tuple[int | None, ...] = (1, None, 1)  # 80/100 = 0.80 exactly
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, StreamCoverage)
    assert result.fraction == pytest.approx(0.80)


def test_activity_failing_both_duration_and_coverage_always_reports_duration() -> None:
    """Both conditions genuinely fail here -- assert the precondition using
    the module's own ``stream_coverage`` before asserting which reason wins,
    so the scenario is proven reachable rather than assumed."""
    time_s = (0.0, 10.0, 20.0, 30.0)
    values: tuple[int | None, ...] = (1, None, 1, 1)

    precondition = stream_coverage(_samples(time_s), values, stream="power")
    assert precondition is not None
    assert precondition.total_s < _SETTINGS.min_duration_s, (
        "precondition: duration must genuinely fail"
    )
    assert precondition.fraction < _SETTINGS.minimum_for(ChannelId.POWER), (
        "precondition: coverage must genuinely fail too"
    )
    assert precondition.covered_s > 0, "precondition: not the STREAM_ABSENT case"

    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT


def test_activity_failing_both_duration_and_stream_presence_reports_duration() -> None:
    """The other pairing the fixed order must resolve: duration fails *and*
    the stream is wholly absent (``covered_s == 0``) -- TOO_SHORT must still
    win over STREAM_ABSENT, since duration is judged first."""
    time_s = (0.0, 10.0, 20.0)
    values: tuple[int | None, ...] = (None, None, None)

    precondition = stream_coverage(_samples(time_s), values, stream="power")
    assert precondition is not None
    assert precondition.total_s < _SETTINGS.min_duration_s, (
        "precondition: duration must genuinely fail"
    )
    assert precondition.covered_s == 0, (
        "precondition: the stream must be genuinely wholly absent"
    )

    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT


def test_passing_gate_returns_the_stream_coverage_itself() -> None:
    time_s = tuple(float(i) for i in range(100))
    values: tuple[int | None, ...] = tuple(1 for _ in range(100))
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.POWER,
        stream="power",
        settings=_SETTINGS,
    )
    assert isinstance(result, StreamCoverage)
    assert not isinstance(result, ChannelInsufficient)
    assert result.total_s == pytest.approx(99.0)
    assert result.fraction == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# explicit minimum -- overrides per-channel resolution (3.2)
# ---------------------------------------------------------------------------


def test_explicit_minimum_wins_over_a_lenient_configured_per_channel_override() -> None:
    """The pace channel's own configured override is generous (0.50); an
    explicit minimum (0.95) must still fail the gate against the *actual*
    fraction of ~0.70 -- if the per-channel override were consulted instead,
    this would wrongly pass.

    Also the one fixture that *produces a ``ChannelInsufficient``* whose
    ``stream`` name ("altitude") differs from its ``channel`` value ("pace"):
    paired with
    ``test_no_explicit_minimum_falls_back_to_the_per_channel_resolution``
    below (HEART_RATE, stream "heart_rate") at the same STREAM_COVERAGE
    construction site, the two pin channel propagation on two distinct
    members (Req 2.8), and this one alone pins that ``detail`` is built from
    ``stream``, not ``channel``. The strict mirror below shares the same
    "altitude"/pace pairing but passes the gate and so builds no ``detail``;
    in every other fixture here the two are equal strings, which would make
    the substitution invisible."""
    settings = SufficiencySettings(
        min_stream_coverage=0.80, pace_min_stream_coverage=0.50
    )
    time_s = (0.0, 70.0, 100.0)
    values: tuple[int | None, ...] = (1, None, 1)  # 70/100 = 0.70 coverage
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.PACE,
        stream="altitude",
        settings=settings,
        minimum=0.95,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert result.required == pytest.approx(0.95)
    # Distinct from the 0.333... asserted in
    # test_coverage_below_minimum_reports_stream_coverage_naming_both_values
    # -- pairwise-distinct so hardcoding ``observed`` to either single value
    # cannot pass both.
    assert result.observed == pytest.approx(0.70)
    assert "altitude" in result.detail


def test_explicit_minimum_wins_over_a_strict_configured_per_channel_override() -> None:
    """The mirror case: the per-channel override is strict (0.95) but the
    explicit minimum is lenient (0.50) against the same ~0.70 fraction -- if
    the per-channel override were consulted instead of the explicit minimum,
    this would wrongly fail."""
    settings = SufficiencySettings(
        min_stream_coverage=0.80, pace_min_stream_coverage=0.95
    )
    time_s = (0.0, 70.0, 100.0)
    values: tuple[int | None, ...] = (1, None, 1)  # 70/100 = 0.70 coverage
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.PACE,
        stream="altitude",
        settings=settings,
        minimum=0.50,
    )
    assert isinstance(result, StreamCoverage)
    assert result.fraction == pytest.approx(0.70)


def test_no_explicit_minimum_falls_back_to_the_per_channel_resolution() -> None:
    """Without an explicit minimum, ``evaluate`` must consult
    ``settings.minimum_for(channel)`` -- proven here by a per-channel
    override that is *stricter* than the shared default, at a fraction that
    passes the shared default but fails the override."""
    settings = SufficiencySettings(
        min_stream_coverage=0.50, hr_min_stream_coverage=0.90
    )
    time_s = (0.0, 70.0, 100.0)
    values: tuple[int | None, ...] = (1, None, 1)  # 0.70 coverage
    result = evaluate(
        _samples(time_s),
        values,
        channel=ChannelId.HEART_RATE,
        stream="heart_rate",
        settings=settings,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert result.required == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# never raises (1.8)
# ---------------------------------------------------------------------------


def test_gate_never_raises_across_all_degenerate_inputs() -> None:
    Case = tuple[tuple[float, ...], tuple[object | None, ...]]
    degenerate_cases: tuple[Case, ...] = (
        ((), ()),
        ((0.0,), (1,)),
        ((5.0, 5.0), (1, 1)),
        ((0.0, 10.0, 90.0), (None, None, None)),
    )
    for time_s, values in degenerate_cases:
        result = evaluate(
            _samples(time_s),
            values,
            channel=ChannelId.POWER,
            stream="power",
            settings=_SETTINGS,
        )
        assert isinstance(result, (StreamCoverage, ChannelInsufficient))
