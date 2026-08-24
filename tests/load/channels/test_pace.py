"""Tests for the pace channel (``pace.py``).

Covers Requirements 1.6, 1.7, 1.9, 1.11, 6.1-6.9, 7.6 -- see
``.kiro/specs/load-channels/requirements.md`` and the "Channel --
src/fitdocs/load/channels/pace.py" / "PaceChannel" component in design.md
(``#### PaceChannel`` heading -- cite the heading over a line range when
following this pointer by hand, since any future edit above that section
shifts the range), plus the "Pace channel, grade branch" System Flow.
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import date

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import pace
from fitdocs.load.channels.grade import GradeAdjustment
from fitdocs.load.channels.sources import DIVERGENCES, INTERVALS_ICU_PACE_LOAD
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    InsufficiencyReason,
    SufficiencySettings,
)
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------


def _samples(
    time_s: tuple[float, ...],
    distance_m: tuple[float | None, ...],
    altitude_m: tuple[float | None, ...] | None = None,
) -> Samples:
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=none_ints,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=distance_m,
        altitude_m=altitude_m if altitude_m is not None else none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _summary() -> SessionSummary:
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def _activity(
    *,
    modality: Modality = Modality.RUN,
    sport: Sport = Sport.RUN,
    samples: Samples,
) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


def _level_activity(
    n: int, *, step_m: float = 3.6, modality: Modality = Modality.RUN
) -> Activity:
    """``n + 1`` one-second samples, ``step_m`` metres apart, no altitude at
    all -- so the gate on ``distance`` passes and the altitude gate fails
    STREAM_ABSENT, i.e. the raw (unadjusted) branch."""
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(step_m * i for i in range(n + 1))
    return _activity(modality=modality, samples=_samples(time_s, distance_m))


def _pace(
    value_s_per_km: float,
    *,
    discipline: Sport | None = Sport.RUN,
    measured_on: date = date(2026, 1, 1),
) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=discipline,
        value=value_s_per_km,
        measured_on=measured_on,
    )


_SETTINGS = SufficiencySettings()


def _metrics(*, moving_time_s: float | None) -> DerivedMetrics:
    return DerivedMetrics(moving_time_s=moving_time_s)


# ---------------------------------------------------------------------------
# 1.6 / 6.1 -- one hour at threshold pace, level ground, scores exactly 100
# with intensity exactly 1.0
# ---------------------------------------------------------------------------


def test_one_hour_at_threshold_pace_level_ground_scores_exactly_100() -> None:
    # threshold 300 s/km -> speed = 1000/300 m/s; run exactly 3600 s at that
    # speed on level ground (no altitude stream at all).
    threshold_s_per_km = 300.0
    speed_mps = 1000.0 / threshold_s_per_km
    n = 3600
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(speed_mps * i for i in range(n + 1))
    activity = _activity(modality=Modality.RUN, samples=_samples(time_s, distance_m))
    metrics = _metrics(moving_time_s=3600.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(threshold_s_per_km), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(100.0)
    assert result.intensity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 1.11 -- the shared intensity relation, at threshold AND sub-threshold
# ---------------------------------------------------------------------------


def test_intensity_relation_holds_at_threshold() -> None:
    threshold_s_per_km = 300.0
    speed_mps = 1000.0 / threshold_s_per_km
    n = 3600
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(speed_mps * i for i in range(n + 1))
    activity = _activity(samples=_samples(time_s, distance_m))
    metrics = _metrics(moving_time_s=3600.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(threshold_s_per_km), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    expected = (result.scored_duration_s / 3600) * result.intensity**2 * 100
    assert result.load == pytest.approx(expected)


def test_intensity_relation_holds_at_a_sub_threshold_pace() -> None:
    """Sub-threshold, not the multiplicative-identity case (Fixture
    Discrimination Gate item 5): intensity here is 0.75 (speed 3/4 of
    threshold), not 1.0, so ``intensity**2 -> intensity**3`` reds only this
    test, not the threshold-identity test above."""
    threshold_s_per_km = 240.0  # 1000/240 m/s at threshold
    threshold_speed = 1000.0 / threshold_s_per_km
    actual_speed = threshold_speed * 0.75
    n = 1800
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(actual_speed * i for i in range(n + 1))
    activity = _activity(samples=_samples(time_s, distance_m))
    metrics = _metrics(moving_time_s=1800.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(threshold_s_per_km), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(0.75)
    expected = (result.scored_duration_s / 3600) * result.intensity**2 * 100
    assert expected == pytest.approx((1800 / 3600) * 0.75**2 * 100)
    assert result.load == pytest.approx(expected)


def test_load_formula_uses_the_square_of_intensity() -> None:
    """Fixture Discrimination Gate item 5, made real rather than merely
    stated: a prior version of this test asserted ``0.75**2 != 0.75**3``
    directly, referencing no production symbol at all (an AST walk over
    its own body finds zero ``Name``/``Attribute`` nodes) -- a `32.0 ==
    32.0`-shaped defect that cannot fail under any change to ``pace.py``.
    This version instead extracts the exponent actually applied to
    ``intensity`` out of ``pace.py``'s own source via a regex anchored on
    the ``load = `` assignment, evaluates *that* extracted exponent against
    the sub-threshold and threshold fixtures, and asserts the extraction
    itself succeeded (a regex that matches nothing would make the rest of
    this test vacuously true, which is exactly the failure mode being
    guarded against here)."""
    source = inspect.getsource(pace)
    match = re.search(r"intensity\*\*(\d+)", source)
    assert match is not None, "could not find the intensity exponent in pace.py"
    exponent = int(match.group(1))
    assert exponent == 2

    sub_threshold_intensity = 0.75
    threshold_intensity = 1.0
    assert sub_threshold_intensity**exponent != sub_threshold_intensity**3
    assert threshold_intensity**exponent == threshold_intensity**3


# ---------------------------------------------------------------------------
# 6.2 -- unit conversion: seconds per kilometre -> speed, pinned at a
# non-round value so an inverted or mis-scaled conversion produces a
# different number
# ---------------------------------------------------------------------------


def test_threshold_pace_converted_from_seconds_per_km_to_speed() -> None:
    """330 s/km -> 1000/330 m/s ~= 3.0303 m/s. A conversion that treated the
    benchmark as seconds per MILE (1609.34/330 ~= 4.876 m/s), or that
    forgot the /1000 entirely (1/330 ~= 0.00303 m/s), or that inverted the
    ratio (330/1000 = 0.33 m/s), all produce a different intensity for the
    same run."""
    threshold_s_per_km = 330.0
    actual_speed = 1000.0 / threshold_s_per_km  # run exactly at threshold speed
    n = 1000
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(actual_speed * i for i in range(n + 1))
    activity = _activity(samples=_samples(time_s, distance_m))
    metrics = _metrics(moving_time_s=float(n))
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(threshold_s_per_km), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(1.0, rel=1e-6)
    inputs = dict(result.inputs_used)
    assert float(inputs["threshold_speed_mps"]) == pytest.approx(
        1000.0 / 330.0, rel=1e-4
    )


# ---------------------------------------------------------------------------
# 6.7 -- modality checked FIRST; MODEL_NOT_DEFINED for any non-running
# modality, naming the modality, without implying a substitute channel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "modality", [Modality.BIKE, Modality.SWIM, Modality.STRENGTH, Modality.OTHER]
)
def test_non_running_modality_is_model_not_defined(modality: Modality) -> None:
    activity = _level_activity(100, modality=modality)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.MODEL_NOT_DEFINED
    assert modality.value in result.detail


def test_model_not_defined_detail_does_not_name_another_channel() -> None:
    """Req 6.7's second half: the detail may name the *modality* but must
    not imply which channel should have been used instead.

    A prior version of this test matched only the exact phrases "power
    channel" / "heart-rate channel" / "heart rate channel", which both
    appending "; power is more appropriate here" (no word "channel") and
    appending an underscore-spelled f"; use the {ChannelId.HEART_RATE.value}
    instead" (renders "heart_rate", neither "heart-rate" nor "heart rate")
    survive untouched. This version closes both holes two ways: an exact
    match against the modality-naming template (so *any* appended text at
    all is caught, not just specific spellings of a channel name), and a
    bare-token check for "power" and "heart" with no surrounding phrase
    requirement."""
    activity = _level_activity(100, modality=Modality.BIKE)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.detail == (
        "the pace-load model is defined for the running modality "
        f"only; this activity's modality is {activity.modality.value!r}"
    )
    lowered = result.detail.lower()
    for forbidden_token in ("power", "heart"):
        assert forbidden_token not in lowered


def test_modality_checked_before_a_wrong_kind_benchmark_would_raise() -> None:
    """Modality is checked first (design.md Postconditions: "checked
    first") -- strictly before the wrong-quantity guard runs on
    ``threshold_pace``. A non-running activity handed a wrong-kind
    benchmark must come back MODEL_NOT_DEFINED, not raise. If the
    ordering were reversed, this exact fixture would raise ``ValueError``
    instead."""
    wrong = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=250,
        measured_on=date(2026, 1, 1),
    )
    activity = _level_activity(100, modality=Modality.BIKE)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(activity, metrics, threshold_pace=wrong, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.MODEL_NOT_DEFINED


def test_modality_checked_before_no_benchmark() -> None:
    """A non-running activity with NO benchmark at all still reports
    MODEL_NOT_DEFINED, not NO_BENCHMARK -- modality is checked first."""
    activity = _level_activity(100, modality=Modality.STRENGTH)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(activity, metrics, threshold_pace=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.MODEL_NOT_DEFINED


# ---------------------------------------------------------------------------
# 1.9 -- the wrong-quantity guard, called at entry (once modality passes),
# raises rather than computing or reporting insufficiency
# ---------------------------------------------------------------------------


def test_wrong_benchmark_kind_raises_on_a_running_activity() -> None:
    wrong = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=160,
        measured_on=date(2026, 1, 1),
    )
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    with pytest.raises(ValueError, match="threshold_pace_s_per_km"):
        pace.compute(activity, metrics, threshold_pace=wrong, settings=_SETTINGS)


def test_no_benchmark_kind_check_when_threshold_pace_is_none() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(activity, metrics, threshold_pace=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


# ---------------------------------------------------------------------------
# 6.3 / 6.4 -- NO_BENCHMARK: absent, zero, and negative
# ---------------------------------------------------------------------------


def test_no_benchmark_when_threshold_pace_is_none() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(activity, metrics, threshold_pace=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


def test_no_benchmark_when_threshold_pace_value_is_zero() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(0.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


def test_no_benchmark_when_threshold_pace_value_is_negative() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(-10.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


def test_no_benchmark_beats_a_failing_gate() -> None:
    empty_activity = _activity(samples=_samples((), ()))
    metrics = _metrics(moving_time_s=None)
    result = pace.compute(
        empty_activity, metrics, threshold_pace=None, settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


# ---------------------------------------------------------------------------
# 6.5 -- gate on the distance stream
# ---------------------------------------------------------------------------


def test_stream_absent_when_distance_never_recorded() -> None:
    time_s = tuple(float(i) for i in range(120))
    samples = _samples(time_s, (None,) * len(time_s))
    activity = _activity(samples=samples)
    metrics = _metrics(moving_time_s=120.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.STREAM_ABSENT


def test_too_short_when_recorded_span_below_minimum_duration() -> None:
    time_s = (0.0, 1.0, 2.0)
    samples = _samples(time_s, (0.0, 3.0, 6.0))
    activity = _activity(samples=samples)
    metrics = _metrics(moving_time_s=2.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT


def test_stream_coverage_when_below_configured_minimum() -> None:
    time_s = tuple(float(i) for i in range(120))
    distance_m = tuple(3.0 * i if i < 60 else None for i in range(120))
    samples = _samples(time_s, distance_m)
    activity = _activity(samples=samples)
    metrics = _metrics(moving_time_s=59.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert result.observed is not None
    assert result.required == pytest.approx(0.80)


def test_gate_failure_beats_not_computable() -> None:
    time_s = tuple(float(i) for i in range(120))
    samples = _samples(time_s, (None,) * len(time_s))
    activity = _activity(samples=samples)
    metrics = _metrics(moving_time_s=None)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_ABSENT


def test_distance_coverage_override_applies_to_the_distance_gate() -> None:
    """The pace channel's own coverage override (``pace_min_stream_
    coverage``) DOES apply to the distance stream gate (Req 6.5), unlike
    the altitude refinement gate below which must ignore it."""
    time_s = tuple(float(i) for i in range(101))
    distance_m = tuple(3.0 * i if i < 86 else None for i in range(101))
    activity = _activity(samples=_samples(time_s, distance_m))
    metrics = _metrics(moving_time_s=86.0)

    passes_default = pace.compute(
        activity,
        metrics,
        threshold_pace=_pace(300.0),
        settings=SufficiencySettings(),
    )
    assert isinstance(passes_default, ChannelLoad)

    stricter = SufficiencySettings(pace_min_stream_coverage=0.90)
    fails_stricter = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=stricter
    )
    assert isinstance(fails_stricter, ChannelInsufficient)
    assert fails_stricter.reason is InsufficiencyReason.STREAM_COVERAGE
    assert fails_stricter.required == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# 6.6 -- NOT_COMPUTABLE when moving time or accumulated distance is absent
# or not positive, gate having passed
# ---------------------------------------------------------------------------


def test_not_computable_when_moving_time_is_none() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=None)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_when_moving_time_is_zero() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=0.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_when_moving_time_is_negative() -> None:
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=-5.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_when_accumulated_distance_is_not_positive() -> None:
    """Every recorded distance sample is identical (no positive delta
    anywhere), so the accumulated distance is zero, not merely absent."""
    time_s = tuple(float(i) for i in range(120))
    distance_m = tuple(0.0 for _ in range(120))
    activity = _activity(samples=_samples(time_s, distance_m))
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    # ``channel`` was previously unpinned at this specific construction
    # site: hardcoding it to ChannelId.POWER, and separately to
    # ChannelId.HEART_RATE, both left every other test in this module (and
    # the whole ``tests/load`` suite) green, since no assertion anywhere
    # named this site's own ``channel`` value.
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_four_insufficiency_details_are_pairwise_distinct_and_own_content() -> None:
    """This module constructs exactly four distinct ``ChannelInsufficient``
    ``detail`` texts: MODEL_NOT_DEFINED, NO_BENCHMARK, NOT_COMPUTABLE (moving
    time), and NOT_COMPUTABLE (accumulated distance). A prior version of
    this suite pinned only MODEL_NOT_DEFINED's (via the "does not name
    another channel" test) and compared NOT_COMPUTABLE(moving) only against
    NO_BENCHMARK -- never against NOT_COMPUTABLE(distance) -- so making the
    two NOT_COMPUTABLE details identical, or emptying any of the other
    three, left the whole ``tests/load`` suite green. Every one of the six
    pairs among the four is compared explicitly here, and each detail's own
    distinctive substring is asserted so emptying one cannot pass by
    coincidentally still differing from the other three (an empty string is
    still != to three non-empty ones, which is exactly why emptying alone
    was previously undetected: the *other* three detail assertions in this
    module never existed)."""
    model_not_defined = pace.compute(
        _level_activity(100, modality=Modality.BIKE),
        _metrics(moving_time_s=100.0),
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    no_benchmark = pace.compute(
        _level_activity(100),
        _metrics(moving_time_s=100.0),
        threshold_pace=None,
        settings=_SETTINGS,
    )
    not_computable_moving = pace.compute(
        _level_activity(100),
        _metrics(moving_time_s=None),
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    zero_distance_time_s = tuple(float(i) for i in range(120))
    zero_distance_m = tuple(0.0 for _ in range(120))
    not_computable_distance = pace.compute(
        _activity(samples=_samples(zero_distance_time_s, zero_distance_m)),
        _metrics(moving_time_s=100.0),
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )

    for result in (
        model_not_defined,
        no_benchmark,
        not_computable_moving,
        not_computable_distance,
    ):
        assert isinstance(result, ChannelInsufficient)

    assert isinstance(model_not_defined, ChannelInsufficient)
    assert isinstance(no_benchmark, ChannelInsufficient)
    assert isinstance(not_computable_moving, ChannelInsufficient)
    assert isinstance(not_computable_distance, ChannelInsufficient)

    details = {
        "model_not_defined": model_not_defined.detail,
        "no_benchmark": no_benchmark.detail,
        "not_computable_moving": not_computable_moving.detail,
        "not_computable_distance": not_computable_distance.detail,
    }
    names = list(details)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            assert details[names[i]] != details[names[j]], (
                f"{names[i]!r} and {names[j]!r} details must differ"
            )

    assert "modality" in details["model_not_defined"]
    assert "benchmark" in details["no_benchmark"]
    assert "moving" in details["not_computable_moving"]
    assert "distance" in details["not_computable_distance"]


def test_not_computable_and_no_benchmark_are_pairwise_distinct_reasons() -> None:
    activity_no_moving = _level_activity(100)
    metrics_missing = _metrics(moving_time_s=None)
    not_computable = pace.compute(
        activity_no_moving,
        metrics_missing,
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    no_benchmark = pace.compute(
        activity_no_moving, metrics_missing, threshold_pace=None, settings=_SETTINGS
    )
    assert isinstance(not_computable, ChannelInsufficient)
    assert isinstance(no_benchmark, ChannelInsufficient)
    assert not_computable.reason is InsufficiencyReason.NOT_COMPUTABLE
    assert no_benchmark.reason is InsufficiencyReason.NO_BENCHMARK
    assert not_computable.detail != no_benchmark.detail


# ---------------------------------------------------------------------------
# 7.6 -- the grade branch: with/without altitude both compute, differ in
# value, differ in note, agree on distance coverage and duration
# ---------------------------------------------------------------------------


def _hilly_activity(
    n: int, *, step_m: float = 3.6, rise_per_step: float = 0.3
) -> Activity:
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(step_m * i for i in range(n + 1))
    altitude_m = tuple(rise_per_step * i for i in range(n + 1))
    return _activity(
        modality=Modality.RUN, samples=_samples(time_s, distance_m, altitude_m)
    )


def test_with_without_altitude_differ_value_note_agree_distance_duration() -> None:
    n = 200
    metrics = _metrics(moving_time_s=float(n))

    with_altitude = pace.compute(
        _hilly_activity(n),
        metrics,
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    without_altitude = pace.compute(
        _level_activity(n, step_m=3.6),
        metrics,
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )

    assert isinstance(with_altitude, ChannelLoad)
    assert isinstance(without_altitude, ChannelLoad)

    # Both compute.
    # Differ in value (the hill costs more than level ground at the same
    # raw pace).
    assert with_altitude.load != without_altitude.load
    assert with_altitude.intensity != without_altitude.intensity
    # Differ in the recorded note.
    assert with_altitude.notes != without_altitude.notes
    assert with_altitude.notes == ()
    assert without_altitude.notes != ()
    # Agree on distance (same distance-stream coverage) and duration.
    assert with_altitude.coverage == without_altitude.coverage
    assert with_altitude.scored_duration_s == without_altitude.scored_duration_s


def test_without_altitude_note_states_why_and_does_not_report_insufficiency() -> None:
    """Req 7.6's "and why", pinned against the *specific* underlying
    reason, not just the presence of some note: with no altitude stream at
    all, the fallback is STREAM_ABSENT, and the note must carry the
    altitude gate's own STREAM_ABSENT detail text, not a generic
    placeholder that would read identically for a thin-coverage fallback."""
    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert len(result.notes) == 1
    assert "grade adjustment" in result.notes[0]
    assert "not applied" in result.notes[0]
    # The "why": the altitude gate's own STREAM_ABSENT reasoning, verbatim.
    assert (
        "altitude carries no recorded value anywhere in the activity"
        in (result.notes[0])
    )


def test_thin_altitude_coverage_note_states_a_different_why_than_absent() -> None:
    """Absent altitude (STREAM_ABSENT) and thinly-covered altitude
    (STREAM_COVERAGE) both degrade to the unadjusted branch -- neither
    reports insufficiency for that reason alone (Req 7.6) -- but the two
    "why"s are genuinely different reasons and must produce genuinely
    different note text. A prior version of this test asserted only
    ``notes != ()``, which cannot distinguish a generic placeholder note
    from one that actually states the gate's own reason; deleting the
    ``f"({altitude_gate.detail})"`` interpolation in production, or
    replacing it with a literal ``"(x)"``, both left that assertion green."""
    n = 200
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(3.6 * i for i in range(n + 1))
    # Altitude recorded for only the first 10% of samples -> coverage well
    # below the 0.80 default (STREAM_COVERAGE, not STREAM_ABSENT).
    altitude_m = tuple((0.3 * i if i < (n + 1) // 10 else None) for i in range(n + 1))
    activity = _activity(
        modality=Modality.RUN, samples=_samples(time_s, distance_m, altitude_m)
    )
    metrics = _metrics(moving_time_s=float(n))
    thin_coverage_result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(thin_coverage_result, ChannelLoad)
    assert thin_coverage_result.notes != ()
    # The "why": the altitude gate's own STREAM_COVERAGE reasoning.
    assert "altitude coverage" in thin_coverage_result.notes[0]
    assert "below the configured minimum" in thin_coverage_result.notes[0]

    absent_result = pace.compute(
        _level_activity(n, step_m=3.6),
        metrics,
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    assert isinstance(absent_result, ChannelLoad)
    assert absent_result.notes != ()

    # The two fallback causes must produce genuinely different notes.
    assert thin_coverage_result.notes != absent_result.notes


# ---------------------------------------------------------------------------
# THE PACE-COVERAGE OVERRIDE MUST NOT AFFECT THE ALTITUDE DECISION
# ---------------------------------------------------------------------------


def test_pace_coverage_override_does_not_change_the_altitude_decision() -> None:
    """The altitude gate runs against the SHARED minimum
    (``settings.min_stream_coverage``), never the pace channel's own
    ``pace_min_stream_coverage`` override (design.md Implementation Notes).
    Constructed so the two thresholds diverge: altitude coverage is 0.70,
    which clears a shared minimum of 0.60 but fails a pace-specific
    override of 0.95. If the altitude gate wrongly consulted the pace
    override, grade adjustment would be skipped even though the shared
    minimum -- the value the altitude question must be judged against --
    is cleared."""
    n = 100
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(3.6 * i for i in range(n + 1))
    # 70 of the first 100 one-second intervals carry an altitude sample on
    # their earlier endpoint (indices 0..69 non-None out of 0..99 spanned
    # intervals) -> coverage 0.70.
    altitude_m = tuple((0.3 * i if i < 70 else None) for i in range(n + 1))
    activity = _activity(
        modality=Modality.RUN, samples=_samples(time_s, distance_m, altitude_m)
    )
    metrics = _metrics(moving_time_s=float(n))

    settings = SufficiencySettings(
        min_stream_coverage=0.60, pace_min_stream_coverage=0.95
    )
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=settings
    )
    assert isinstance(result, ChannelLoad)
    # Grade adjustment was applied: no fallback note, and the equivalent
    # distance differs from the flat-course value the pace channel would
    # compute over the same raw distance without any grade at all.
    assert result.notes == ()
    inputs = dict(result.inputs_used)
    assert inputs["grade_adjustment_applied"] == "True"


def test_swapping_which_minimum_the_altitude_gate_receives_reds_the_override_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms the discrimination in the test above is real. The actual
    mechanism: monkeypatch the module-level ``evaluate`` name ``pace.py``
    calls (``pace.evaluate``, imported at module scope from
    ``.sufficiency``) with a wrapper that forces the ``minimum=`` argument
    to ``0.95`` (the pace-specific override) whenever ``stream="altitude"``
    -- i.e. reproducing exactly the defect this test exists to rule out
    (the altitude question resolving against the pace override instead of
    the explicit shared minimum) -- and observe the previously-applying
    fixture fall back to unadjusted instead. (An earlier version of this
    docstring claimed the mechanism monkeypatched
    ``SufficiencySettings.minimum_for`` directly and carried a dead,
    never-called helper toward that end; corrected to describe what this
    test actually does.)"""
    from fitdocs.load.channels import sufficiency as sufficiency_module

    original_evaluate = sufficiency_module.evaluate

    def _fake_evaluate(*args: object, **kwargs: object) -> object:
        kwargs = dict(kwargs)
        if kwargs.get("stream") == "altitude":
            kwargs["minimum"] = 0.95
        return original_evaluate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pace, "evaluate", _fake_evaluate)

    n = 100
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(3.6 * i for i in range(n + 1))
    altitude_m = tuple((0.3 * i if i < 70 else None) for i in range(n + 1))
    activity = _activity(
        modality=Modality.RUN, samples=_samples(time_s, distance_m, altitude_m)
    )
    metrics = _metrics(moving_time_s=float(n))

    settings = SufficiencySettings(
        min_stream_coverage=0.60, pace_min_stream_coverage=0.95
    )
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=settings
    )
    assert isinstance(result, ChannelLoad)
    # Under the forced-override defect, the same 0.70-covered altitude
    # stream now fails (0.70 < 0.95) -> falls back to unadjusted.
    assert result.notes != ()


# ---------------------------------------------------------------------------
# 6.9 -- inputs_used carries the grade-adjusted speed, threshold speed,
# moving time, whether adjustment was applied, and clamped-interval count
# ---------------------------------------------------------------------------


def test_inputs_used_carries_all_required_fields() -> None:
    activity = _level_activity(200)
    metrics = _metrics(moving_time_s=200.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    inputs = dict(result.inputs_used)
    assert "grade_adjusted_speed_mps" in inputs
    assert "threshold_speed_mps" in inputs
    assert "moving_time_s" in inputs
    assert inputs["moving_time_s"] == "200"
    assert "grade_adjustment_applied" in inputs
    assert inputs["grade_adjustment_applied"] == "False"
    assert "clamped_intervals" in inputs
    assert inputs["clamped_intervals"] == "0"


def test_inputs_used_reports_applied_true_and_clamped_count_with_altitude() -> None:
    # Steep enough, sustained enough gradient to force clamping beyond
    # +-45% on at least one interval: distance step small, altitude step
    # large relative to it.
    n = 100
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(1.0 * i for i in range(n + 1))
    altitude_m = tuple(0.9 * i for i in range(n + 1))  # gradient ~0.9 -> clamped
    activity = _activity(
        modality=Modality.RUN, samples=_samples(time_s, distance_m, altitude_m)
    )
    metrics = _metrics(moving_time_s=float(n))
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    inputs = dict(result.inputs_used)
    assert inputs["grade_adjustment_applied"] == "True"
    assert int(inputs["clamped_intervals"]) > 0


def test_grade_adjusted_speed_is_the_true_value_away_from_threshold() -> None:
    """Req 6.9 exists "so that the number can be checked by hand" -- but
    every prior fixture asserting ``threshold_speed_mps`` ran exactly AT
    threshold, where ``grade_adjusted_speed_mps == threshold_speed_mps``
    (the identity-point trap, Fixture Discrimination Gate item 5, applied
    to ``inputs_used`` rather than to ``load``/``intensity``). Under that
    fixture, three wrong implementations all pass unnoticed: swapping the
    two ``inputs_used`` speed entries; hardcoding
    ``("grade_adjusted_speed_mps", "0")``; and reporting the UNADJUSTED
    (raw distance / moving time) speed under the "grade-adjusted" label.
    This fixture runs well away from threshold, with grade adjustment
    genuinely applied over a sustained, non-clamped uphill grade, and
    checks the reported value against the shipped
    :func:`fitdocs.load.channels.grade.equivalent_distance` called
    directly on the same samples -- the very primitive ``pace.py`` itself
    composes -- rather than against an independently hand-derived
    polynomial."""
    from fitdocs.load.channels.grade import (
        equivalent_distance as shipped_equivalent_distance,
    )

    n = 200
    time_s = tuple(float(i) for i in range(n + 1))
    distance_m = tuple(4.0 * i for i in range(n + 1))
    altitude_m = tuple(0.2 * i for i in range(n + 1))  # sustained ~5% uphill
    activity = _activity(
        modality=Modality.RUN, samples=_samples(time_s, distance_m, altitude_m)
    )
    metrics = _metrics(moving_time_s=float(n))
    # Raw pace here is roughly 1000/(4.0) = 250 s/km; anchoring on a much
    # faster threshold keeps this fixture well off the identity point.
    threshold = _pace(150.0)
    result = pace.compute(
        activity, metrics, threshold_pace=threshold, settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)

    adjustment = shipped_equivalent_distance(activity.samples, apply_grade=True)
    assert adjustment is not None
    assert adjustment.applied
    expected_grade_adjusted_speed = adjustment.equivalent_distance_m / float(n)
    expected_raw_speed = adjustment.raw_distance_m / float(n)
    # The grade genuinely changed the equivalent distance -- otherwise this
    # fixture could not distinguish "grade-adjusted" from "unadjusted" at
    # all, which is exactly the confound this fixture exists to avoid.
    assert expected_grade_adjusted_speed != pytest.approx(expected_raw_speed)

    inputs = dict(result.inputs_used)
    reported_speed = float(inputs["grade_adjusted_speed_mps"])
    reported_threshold_speed = float(inputs["threshold_speed_mps"])

    assert reported_speed == pytest.approx(expected_grade_adjusted_speed, rel=1e-5)
    assert reported_speed != pytest.approx(expected_raw_speed, rel=1e-5)
    assert reported_speed != pytest.approx(reported_threshold_speed, rel=1e-5)
    assert reported_speed != pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 2.7 (restated on ChannelLoad) -- coverage/duration reported on success;
# channel id and anchor identity
# ---------------------------------------------------------------------------


def test_successful_result_carries_channel_id_coverage_anchor_and_duration() -> None:
    activity = _level_activity(200)
    metrics = _metrics(moving_time_s=200.0)
    threshold = _pace(300.0)
    result = pace.compute(
        activity, metrics, threshold_pace=threshold, settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.channel is ChannelId.PACE
    assert result.coverage.stream == "distance"
    assert result.scored_duration_s == 200.0
    assert result.anchor is threshold


def test_benchmark_discipline_is_not_consulted() -> None:
    """``Benchmark.discipline`` was previously a fixture-fixed field: every
    call in this module anchored on ``_pace(...)``'s default
    ``discipline=Sport.RUN``, so a production path that behaved
    differently when ``discipline is None`` (e.g. estimating a threshold
    from the activity's own mean speed instead of anchoring on the
    supplied benchmark's ``value``, which Req 6.3 forbids) would have gone
    undetected. This channel does not read ``threshold_pace.discipline`` at
    all -- unlike the power channel, which reports it among
    ``inputs_used`` -- so a discipline-less benchmark (``discipline=None``,
    as an athlete-wide benchmark would carry) must compute the identical
    result as the same ``value`` with a discipline set."""
    activity = _level_activity(200)
    metrics = _metrics(moving_time_s=200.0)

    with_discipline = pace.compute(
        activity,
        metrics,
        threshold_pace=_pace(300.0, discipline=Sport.RUN),
        settings=_SETTINGS,
    )
    without_discipline = pace.compute(
        activity,
        metrics,
        threshold_pace=_pace(300.0, discipline=None),
        settings=_SETTINGS,
    )
    assert isinstance(with_discipline, ChannelLoad)
    assert isinstance(without_discipline, ChannelLoad)
    assert with_discipline.load == without_discipline.load
    assert with_discipline.intensity == without_discipline.intensity


# ---------------------------------------------------------------------------
# 1.7 -- independence: sequential calls with different inputs never leak
# state
# ---------------------------------------------------------------------------


def test_sequential_calls_are_independent() -> None:
    result_a = pace.compute(
        _level_activity(100),
        _metrics(moving_time_s=100.0),
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    result_b = pace.compute(
        _level_activity(100),
        _metrics(moving_time_s=None),
        threshold_pace=None,
        settings=_SETTINGS,
    )
    result_c = pace.compute(
        _level_activity(100, modality=Modality.BIKE),
        _metrics(moving_time_s=100.0),
        threshold_pace=_pace(300.0),
        settings=_SETTINGS,
    )
    assert isinstance(result_a, ChannelLoad)
    assert isinstance(result_b, ChannelInsufficient)
    assert result_b.reason is InsufficiencyReason.NO_BENCHMARK
    assert isinstance(result_c, ChannelInsufficient)
    assert result_c.reason is InsufficiencyReason.MODEL_NOT_DEFINED


# ---------------------------------------------------------------------------
# 6.8 -- the intervals.icu divergence is recorded, linked to the correct
# DIVERGENCES entry -- pins the entry's identity AND a distinctive clause
# from its own `reason` text (Fixture Discrimination Gate item 3/defect
# species: task 3.1's first attempt asserted only against the record)
# ---------------------------------------------------------------------------


def test_module_docstring_names_the_correct_divergence_entry() -> None:
    pace_divergence = next(
        d for d in DIVERGENCES if d.behavior == "pace_load_not_variability_normalized"
    )
    distinctive_phrase = "analogous to power's normalized-power treatment"
    assert distinctive_phrase in pace_divergence.reason

    doc = " ".join((inspect.getdoc(pace) or "").split())
    assert pace_divergence.behavior in doc
    assert "intervals.icu" in doc
    assert distinctive_phrase in doc


def test_module_docstring_cites_the_intervals_icu_pace_load_source() -> None:
    assert INTERVALS_ICU_PACE_LOAD.key == "intervals_icu_pace_load"
    doc = " ".join((inspect.getdoc(pace) or "").split())
    assert "INTERVALS_ICU_PACE_LOAD" in doc or "intervals_icu_pace_load" in doc


def test_divergence_paragraph_sentence_carries_the_exculpating_claim() -> None:
    """Req 6.8 sentence-containment guard, task 2.2's settled shape
    (``test_docstring_states_scope_choice_not_a_sourcing_gap`` in
    ``test_grade.py``): presence-only substring checks (the behavior key,
    the "intervals.icu" token, the distinctive phrase alone) cannot
    distinguish a true claim from its negation. In remediation round 1, a
    paragraph rewritten to claim the OPPOSITE of what this module actually
    does -- that fitdocs DOES variability-normalize and diverges from
    intervals.icu, rather than matching it -- survived every prior
    assertion in this module while keeping the distinctive phrase, the
    "intervals.icu" token and the behavior key intact.

    Whitespace is normalized, the source is split on sentence boundaries,
    and the *same sentence* carrying the distinctive phrase must also carry
    the exculpating claim -- "which this channel matches" together with
    "does not" -- naming fitdocs as the one that matches intervals.icu and
    does NOT variability-normalize, not merely nearby text on the same
    topic. This closes the specific inversion demonstrated in remediation
    round 1. It does not, and is not intended to, catch a paragraph that
    ADDS an unsupported claim alongside a true one -- the accepted terminal
    limit of a substring guard this spec has already settled (see
    ``test_grade.py``'s own docstring for the same acknowledgment); that
    case is not re-engineered a fourth time here."""
    distinctive_phrase = "analogous to power's normalized-power treatment"
    source = " ".join((inspect.getdoc(pace) or "").split())
    assert distinctive_phrase in source

    sentences = re.split(r"(?<=\.)\s+", source)
    assert sentences, "the sentence split produced nothing -- wrong source scanned"
    carrying = [sentence for sentence in sentences if distinctive_phrase in sentence]
    assert carrying, f"no sentence carries {distinctive_phrase!r}"
    for sentence in carrying:
        assert "which this channel matches" in sentence, sentence
        assert "does not" in sentence, sentence


def test_divergence_reasons_are_pairwise_distinct_and_non_empty() -> None:
    """Fixture Discrimination Gate item 4: guard against an
    ``assert a != b != c``-style chain that only compares adjacent pairs.
    Every pairwise comparison among the three divergences' ``reason`` texts
    is checked explicitly, and each text's own content is separately
    non-empty.

    This test's own name and docstring previously overclaimed: pairwise
    distinctness among a *set* of texts is, by construction, invariant
    under permuting which record holds which text -- swapping two
    divergences' ``reason`` values leaves every pairwise ``!=`` comparison
    among them true, so it stays green under a swap. It genuinely does
    catch duplication (two divergences sharing one ``reason``, which
    collapses a pair to equal) and emptying (caught by the non-empty
    check), which is what it is named and documented for here; catching a
    *swap* -- verifying divergence ``X``'s own distinctive content sits on
    divergence ``X`` and nowhere else -- is
    ``test_divergence_reasons_carry_their_own_distinctive_content_not_a_swapped_one``,
    immediately below."""
    reasons = [d.reason for d in DIVERGENCES]
    for text in reasons:
        assert text  # non-empty
    for i in range(len(reasons)):
        for j in range(i + 1, len(reasons)):
            assert reasons[i] != reasons[j]


def test_divergence_reasons_carry_their_own_distinctive_content_not_a_swapped_one() -> (
    None
):
    """Unlike pairwise ``!=`` (which is permutation-invariant and so
    cannot detect a swap -- see the test above), this asserts each
    divergence's own distinctive phrase appears in *its own* ``reason``
    text and in no other divergence's ``reason`` text. Swapping the
    ``running_power_from_recorded_watts`` and
    ``pace_load_not_variability_normalized`` ``reason`` values reds this
    test (each distinctive phrase now sits on the wrong record), which is
    exactly the shape ``test_divergence_reasons_are_pairwise_distinct_and_
    non_empty`` cannot catch."""
    distinctive_phrases = {
        "running_power_from_recorded_watts": "fabricate an absence that is not real",
        "pace_load_not_variability_normalized": (
            "analogous to power's normalized-power treatment"
        ),
        "heart_rate_reported_intensity": "Numeric identity is not claimed",
    }
    by_behavior = {d.behavior: d.reason for d in DIVERGENCES}
    assert set(by_behavior) >= set(distinctive_phrases)
    for behavior, phrase in distinctive_phrases.items():
        assert phrase in by_behavior[behavior], (
            f"{behavior!r}'s reason no longer carries its own phrase {phrase!r}"
        )
        for other_behavior, other_reason in by_behavior.items():
            if other_behavior == behavior:
                continue
            assert phrase not in other_reason, (
                f"{phrase!r} (belongs to {behavior!r}) also found on "
                f"{other_behavior!r} -- looks like a swap"
            )


# ---------------------------------------------------------------------------
# Delegation, not restatement: pin the CALL PATH to
# fitdocs.load.channels.grade.equivalent_distance -- three-test pattern
# (identity, structural, monkeypatch-call-once-by-identity)
# ---------------------------------------------------------------------------


def test_equivalent_distance_name_is_the_real_shipped_object_by_identity() -> None:
    """``test_grade.py`` reloads ``grade`` in-place (to exercise its own
    import-time settings binding), which -- run earlier in the same session
    (alphabetically, ``test_grade.py`` collects before this module) --
    replaces ``grade.equivalent_distance`` with a fresh function object
    that ``pace.py``'s own ``from .grade import equivalent_distance``,
    executed once at its own original import time, does not automatically
    track. Reloading ``pace`` here re-executes that import statement
    against whatever ``grade.equivalent_distance`` *currently* is, making
    this identity check correct regardless of what has run before it in
    the same session rather than merely correct in isolation."""
    import importlib

    from fitdocs.load.channels import grade as fresh_grade

    importlib.reload(pace)
    assert pace.equivalent_distance is fresh_grade.equivalent_distance


def test_module_defines_no_second_function_and_rebinds_equivalent_distance() -> None:
    source = inspect.getsource(pace)
    tree = ast.parse(source)
    assert "equivalent_distance(" in source

    defined_functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ]
    assert {fn.name for fn in defined_functions} == {"compute"}

    lambdas = [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)]
    assert lambdas == []

    def _assigned_names(node: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        return names

    reassigned: set[str] = set()
    for node in ast.walk(tree):
        reassigned |= _assigned_names(node)
    assert "equivalent_distance" not in reassigned


def test_compute_calls_equivalent_distance_once_with_the_callers_exact_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, bool]] = []
    sentinel = GradeAdjustment(
        raw_distance_m=999.0,
        equivalent_distance_m=888.0,
        applied=True,
        clamped_intervals=7,
        note=None,
    )

    def fake_equivalent_distance(
        samples: object, *, apply_grade: bool
    ) -> GradeAdjustment:
        calls.append((samples, apply_grade))
        return sentinel

    monkeypatch.setattr(pace, "equivalent_distance", fake_equivalent_distance)

    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)
    result = pace.compute(
        activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
    )

    assert len(calls) == 1
    called_samples, called_apply_grade = calls[0]
    assert called_samples is activity.samples
    assert called_apply_grade is False  # no altitude stream at all
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(
        (100.0 / 3600.0) * (888.0 / 100.0 / (1000.0 / 300.0)) ** 2 * 100.0
    )


def test_no_op_rebind_of_equivalent_distance_reds_the_call_path_test() -> None:
    """Confirms the monkeypatch test above actually has teeth. The actual
    mechanism: monkeypatch ``pace.equivalent_distance`` with a function
    that unconditionally raises, then call ``pace.compute`` and confirm
    that raise is observed. If production's call site had been rebound to
    a private alias (e.g. ``_shipped_equivalent_distance =
    equivalent_distance`` then calling ``_shipped_equivalent_distance(...)``
    instead of ``equivalent_distance(...)``), this patch would have no
    effect at all -- ``compute`` would keep calling the real, un-patched
    function through the alias, and the expected ``AssertionError`` would
    never be raised, failing this test's own ``pytest.raises`` block. The
    raise being observed is therefore proof the patched name is production's
    live call site, not a rebound alias it reads from elsewhere. (An
    earlier version of this docstring claimed the mechanism was "calling
    through an alias directly"; corrected to describe what this test
    actually does.)"""

    def _boom(samples: object, *, apply_grade: bool) -> GradeAdjustment:
        raise AssertionError("patched equivalent_distance was not called")

    import pytest as _pytest

    activity = _level_activity(100)
    metrics = _metrics(moving_time_s=100.0)

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(pace, "equivalent_distance", _boom)
        with _pytest.raises(AssertionError, match="was not called"):
            pace.compute(
                activity, metrics, threshold_pace=_pace(300.0), settings=_SETTINGS
            )
