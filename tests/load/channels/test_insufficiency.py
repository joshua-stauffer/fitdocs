"""The insufficiency matrix and channel independence (task 5.2).

Covers Requirements 1.2, 1.4, 1.5, 1.7, 1.8, 2.4, 2.5, 2.6, 2.7 -- see
``.kiro/specs/load-channels/requirements.md`` and design.md's "Testing
Strategy" -> "Integration Tests" section ("Insufficiency matrix per channel",
"Channel independence", "Grade degradation" (partially -- 7.6/altitude
degradation is 3.3's own boundary and 5.3's cross-channel semantic, this
module only exercises the pace channel's *ordinary* insufficiency reasons)
and "Benchmark provenance flows through").

**Read-only over the channel modules** (task boundary): this module imports
``power``, ``heart_rate`` and ``pace`` and calls their public ``compute``
functions only, plus the shared ``ChannelVocabulary``/``SufficiencyGate``
types. No source module under ``src/fitdocs/load/channels/`` is edited by
this task -- the mutation-based discrimination evidence for this module's
assertions was gathered by editing a channel or gate module's source line,
observing the suite, and reverting it, entirely outside this file's own
content; that process and its results are recorded in the task's Status
Report, not here.

**The closed reason set is not uniformly reachable by every channel.**
:class:`~fitdocs.load.channels.types.InsufficiencyReason` has seven members,
but no single channel can produce all seven: the power channel never reports
``BENCHMARKS_INCONSISTENT`` or ``MODEL_NOT_DEFINED`` (it takes one benchmark
and is modality-agnostic, Req 4.7); the heart-rate channel never reports
``MODEL_NOT_DEFINED`` (it has no modality restriction); the pace channel
never reports ``BENCHMARKS_INCONSISTENT`` (it takes exactly one benchmark, so
there is nothing to be mutually inconsistent with). This module therefore
covers, per channel, exactly the reasons that channel's own ``compute`` can
produce -- five for power, six for heart rate, six for pace -- rather than
forcing all seven onto every channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate, pace, power
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    InsufficiencyReason,
    SufficiencySettings,
)
from fitdocs.load.channels.weighting import HeartRateIntensityModel
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# fixture builders -- self-contained in this module (read-only over the
# channel modules; not imported from any single-channel test module, per
# ``test_worked_examples.py``'s established convention for this test package)
# ---------------------------------------------------------------------------

_SETTINGS = SufficiencySettings()


def _time_s(n_seconds: int) -> tuple[float, ...]:
    return tuple(float(i) for i in range(n_seconds + 1))


def _partial(n_seconds: int, covered_s: int, value: float) -> tuple[float | None, ...]:
    """``covered_s`` leading samples carry ``value``; the rest (and the
    final sample, never inspected as an "earlier" sample under the gate's
    own dt-weighted accounting) are unrecorded. Under 1 Hz sampling this
    yields exactly ``covered_s`` covered seconds out of ``n_seconds`` total.
    """
    n = n_seconds + 1
    return tuple(value if i < covered_s else None for i in range(n))


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


def _samples(
    n_seconds: int,
    *,
    power_w: tuple[float | None, ...] | None = None,
    heart_rate_bpm: tuple[float | None, ...] | None = None,
    distance_m: tuple[float | None, ...] | None = None,
    altitude_m: tuple[float | None, ...] | None = None,
) -> Samples:
    n = n_seconds + 1
    none_vals: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=_time_s(n_seconds),
        heart_rate_bpm=heart_rate_bpm if heart_rate_bpm is not None else none_vals,  # type: ignore[arg-type]
        power_w=power_w if power_w is not None else none_vals,  # type: ignore[arg-type]
        cadence_rpm=none_vals,
        speed_mps=none_vals,
        distance_m=distance_m if distance_m is not None else none_vals,
        altitude_m=altitude_m if altitude_m is not None else none_vals,
        latitude_deg=none_vals,
        longitude_deg=none_vals,
        temperature_c=none_vals,
    )


def _activity(
    *, modality: Modality = Modality.RUN, sport: Sport = Sport.RUN, samples: Samples
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


def _ftp(value: float, **kw: object) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=value,
        measured_on=kw.get("measured_on", date(2026, 1, 1)),  # type: ignore[arg-type]
        note=kw.get("note"),  # type: ignore[arg-type]
    )


def _lthr(value: float, **kw: object) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=value,
        measured_on=kw.get("measured_on", date(2026, 1, 1)),  # type: ignore[arg-type]
        note=kw.get("note"),  # type: ignore[arg-type]
    )


def _resting_hr(value: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=value,
        measured_on=date(2026, 1, 1),
    )


def _max_hr(value: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=value,
        measured_on=date(2026, 1, 1),
    )


def _threshold_pace(value: float, **kw: object) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=value,
        measured_on=kw.get("measured_on", date(2026, 1, 1)),  # type: ignore[arg-type]
        note=kw.get("note"),  # type: ignore[arg-type]
    )


@dataclass
class _FakeHrModel:
    """A test double for :class:`HeartRateIntensityModel`, injected through
    ``heart_rate.compute``'s own documented ``model`` parameter -- the
    natural, already-present seam for forcing ``NOT_COMPUTABLE`` without
    reaching into ``BanisterTrimpModel``'s own arithmetic, which is out of
    this task's read-only boundary."""

    activity_return: float | None
    hourly_return: float | None
    model_id: str = "fake-hr-model"

    def activity_impulse(
        self, samples: Samples, *, resting_hr: int, max_hr: int
    ) -> float | None:
        return self.activity_return

    def hourly_impulse_at(
        self, heart_rate: int, *, resting_hr: int, max_hr: int
    ) -> float | None:
        return self.hourly_return


_FAKE_MODEL: HeartRateIntensityModel = _FakeHrModel(  # type: ignore[assignment]
    activity_return=None, hourly_return=50.0
)


# ===========================================================================
# Power channel -- five reachable reasons (no BENCHMARKS_INCONSISTENT, no
# MODEL_NOT_DEFINED; Req 4.7's modality-agnosticism and its single-benchmark
# shape rule both out)
# ===========================================================================


def test_power_no_benchmark_when_ftp_absent() -> None:
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(10, power_w=_partial(10, 10, 200.0)),
    )
    result = power.compute(activity, DerivedMetrics(), ftp=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.POWER
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "functional-threshold-power" in result.detail
    assert result.observed is None
    assert result.required is None


def test_power_stream_absent_when_power_never_recorded() -> None:
    activity = _activity(
        modality=Modality.BIKE, sport=Sport.RIDE, samples=_samples(100)
    )
    result = power.compute(
        activity, DerivedMetrics(), ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_ABSENT
    assert "power" in result.detail
    assert result.observed is None
    assert result.required is None


def test_power_stream_coverage_below_configured_minimum() -> None:
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(100, power_w=_partial(100, 41, 200.0)),
    )
    result = power.compute(
        activity, DerivedMetrics(), ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert "power" in result.detail
    assert result.observed == pytest.approx(0.41)
    assert result.required == pytest.approx(0.80)


def test_power_too_short_when_recorded_span_below_minimum_duration() -> None:
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(10, power_w=_partial(10, 10, 200.0)),
    )
    result = power.compute(
        activity, DerivedMetrics(), ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT
    assert "power" in result.detail
    assert result.observed == pytest.approx(10.0)
    assert result.required == pytest.approx(60.0)


def test_power_not_computable_when_normalized_power_is_none() -> None:
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(100, power_w=_partial(100, 100, 200.0)),
    )
    metrics = DerivedMetrics(normalized_power_w=None, moving_time_s=100.0)
    result = power.compute(activity, metrics, ftp=_ftp(250.0), settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE
    assert "normalized power" in result.detail
    assert result.observed is None
    assert result.required is None


# ===========================================================================
# Heart-rate channel -- six reachable reasons (no MODEL_NOT_DEFINED; the
# channel has no modality restriction)
# ===========================================================================


def test_hr_no_benchmark_names_the_missing_one() -> None:
    activity = _activity(samples=_samples(10, heart_rate_bpm=_partial(10, 10, 140.0)))
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=None,
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "(resting_hr_bpm)" in result.detail
    assert "(lthr_bpm)" not in result.detail
    assert "(max_hr_bpm)" not in result.detail
    assert result.observed is None
    assert result.required is None


def test_hr_benchmarks_inconsistent_when_lthr_exceeds_max() -> None:
    """Isolates exactly one of the three disjuncts: ``resting=100 < max=150``
    holds and ``lthr=160 > resting=100`` holds, so only ``lthr > max_hr`` is
    what trips this fixture into ``BENCHMARKS_INCONSISTENT`` -- not a fixture
    where more than one clause fires at once."""
    activity = _activity(samples=_samples(10, heart_rate_bpm=_partial(10, 10, 140.0)))
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(160.0),
        resting_hr=_resting_hr(100.0),
        max_hr=_max_hr(150.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.BENCHMARKS_INCONSISTENT
    assert "resting_hr=100" in result.detail
    assert "lthr=160" in result.detail
    assert "max_hr=150" in result.detail
    assert result.observed is None
    assert result.required is None


def test_hr_stream_absent_when_heart_rate_never_recorded() -> None:
    activity = _activity(samples=_samples(100))
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_ABSENT
    assert "heart_rate" in result.detail
    assert result.observed is None
    assert result.required is None


def test_hr_stream_coverage_below_configured_minimum() -> None:
    activity = _activity(samples=_samples(100, heart_rate_bpm=_partial(100, 52, 140.0)))
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert "heart_rate" in result.detail
    assert result.observed == pytest.approx(0.52)
    assert result.required == pytest.approx(0.80)


def test_hr_too_short_when_recorded_span_below_minimum_duration() -> None:
    activity = _activity(samples=_samples(20, heart_rate_bpm=_partial(20, 20, 140.0)))
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT
    assert "heart_rate" in result.detail
    assert result.observed == pytest.approx(20.0)
    assert result.required == pytest.approx(60.0)


def test_hr_not_computable_when_injected_model_returns_no_activity_impulse() -> None:
    activity = _activity(
        samples=_samples(100, heart_rate_bpm=_partial(100, 100, 140.0))
    )
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
        model=_FAKE_MODEL,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE
    assert "training impulse" in result.detail
    assert result.observed is None
    assert result.required is None


# ===========================================================================
# Pace channel -- six reachable reasons (no BENCHMARKS_INCONSISTENT; only
# one benchmark)
# ===========================================================================


def test_pace_model_not_defined_names_the_modality() -> None:
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(10, distance_m=_partial(10, 10, 5.0)),
    )
    result = pace.compute(
        activity,
        DerivedMetrics(),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.PACE
    assert result.reason is InsufficiencyReason.MODEL_NOT_DEFINED
    assert "bike" in result.detail
    assert result.observed is None
    assert result.required is None


def test_pace_no_benchmark_when_threshold_pace_absent() -> None:
    activity = _activity(samples=_samples(10, distance_m=_partial(10, 10, 5.0)))
    result = pace.compute(
        activity, DerivedMetrics(), threshold_pace=None, settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "threshold-pace" in result.detail
    assert result.observed is None
    assert result.required is None


def test_pace_stream_absent_when_distance_never_recorded() -> None:
    activity = _activity(samples=_samples(100))
    result = pace.compute(
        activity,
        DerivedMetrics(),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_ABSENT
    assert "distance" in result.detail
    assert result.observed is None
    assert result.required is None


def test_pace_stream_coverage_below_configured_minimum() -> None:
    activity = _activity(samples=_samples(100, distance_m=_partial(100, 63, 5.0)))
    result = pace.compute(
        activity,
        DerivedMetrics(),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert "distance" in result.detail
    assert result.observed == pytest.approx(0.63)
    assert result.required == pytest.approx(0.80)


def test_pace_too_short_when_recorded_span_below_minimum_duration() -> None:
    activity = _activity(samples=_samples(30, distance_m=_partial(30, 30, 5.0)))
    result = pace.compute(
        activity,
        DerivedMetrics(),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT
    assert "distance" in result.detail
    assert result.observed == pytest.approx(30.0)
    assert result.required == pytest.approx(60.0)


def test_pace_not_computable_when_moving_time_is_none() -> None:
    activity = _activity(samples=_samples(100, distance_m=_partial(100, 100, 5.0)))
    metrics = DerivedMetrics(moving_time_s=None)
    result = pace.compute(
        activity, metrics, threshold_pace=_threshold_pace(200.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE
    assert "moving" in result.detail
    assert result.observed is None
    assert result.required is None


# ===========================================================================
# A computed result always carries its own measured coverage and duration,
# and the anchoring benchmark's measurement date and note (Req 1.3, 2.7)
# ===========================================================================


def test_power_result_carries_coverage_duration_and_anchor_provenance() -> None:
    n = 200
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(n, power_w=_partial(n, n, 210.0)),
    )
    ftp = _ftp(250.0, measured_on=date(2025, 3, 4), note="early-season FTP test")
    metrics = DerivedMetrics(normalized_power_w=210.0, moving_time_s=float(n))
    result = power.compute(activity, metrics, ftp=ftp, settings=_SETTINGS)
    assert isinstance(result, ChannelLoad)
    assert result.coverage.fraction == pytest.approx(1.0)
    assert result.coverage.total_s == pytest.approx(float(n))
    assert result.scored_duration_s == pytest.approx(float(n))
    assert result.anchor.measured_on == date(2025, 3, 4)
    assert result.anchor.note == "early-season FTP test"


def test_hr_result_carries_coverage_duration_and_anchor_provenance() -> None:
    n = 200
    activity = _activity(samples=_samples(n, heart_rate_bpm=_partial(n, n, 140.0)))
    lthr = _lthr(165.0, measured_on=date(2025, 7, 8), note="mid-season LT test")
    result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=lthr,
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.coverage.fraction == pytest.approx(1.0)
    assert result.coverage.total_s == pytest.approx(float(n))
    assert result.scored_duration_s == pytest.approx(float(n))
    assert result.anchor.measured_on == date(2025, 7, 8)
    assert result.anchor.note == "mid-season LT test"


def test_pace_result_carries_coverage_duration_and_anchor_provenance() -> None:
    n = 200
    speed_mps = 4.0
    distance_m = tuple(speed_mps * i for i in range(n + 1))
    activity = _activity(samples=_samples(n, distance_m=distance_m))
    threshold_pace = _threshold_pace(
        200.0, measured_on=date(2025, 11, 2), note="autumn time trial"
    )
    result = pace.compute(
        activity,
        DerivedMetrics(moving_time_s=float(n)),
        threshold_pace=threshold_pace,
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.coverage.fraction == pytest.approx(1.0)
    assert result.coverage.total_s == pytest.approx(float(n))
    assert result.scored_duration_s == pytest.approx(float(n))
    assert result.anchor.measured_on == date(2025, 11, 2)
    assert result.anchor.note == "autumn time trial"


# ===========================================================================
# Channel independence: one activity, full power, thin heart rate -- a
# computed power load and a heart-rate insufficiency in the same pass,
# neither affecting the other (Req 1.7)
# ===========================================================================


def test_full_power_and_thin_heart_rate_neither_affects_the_other() -> None:
    n = 100
    power_full = _partial(n, n, 220.0)
    hr_thin = _partial(n, 30, 140.0)  # fraction 0.30, below the 0.80 default

    activity = _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=_samples(n, power_w=power_full, heart_rate_bpm=hr_thin),
    )
    ftp = _ftp(250.0)
    power_metrics = DerivedMetrics(normalized_power_w=220.0, moving_time_s=float(n))

    power_result = power.compute(activity, power_metrics, ftp=ftp, settings=_SETTINGS)
    assert isinstance(power_result, ChannelLoad)

    hr_result = heart_rate.compute(
        activity,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(hr_result, ChannelInsufficient)
    assert hr_result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert hr_result.observed == pytest.approx(0.30)

    # Independence, direction 1: the power channel's own result is
    # unaffected by the heart-rate stream's poor coverage -- an otherwise
    # identical activity with a FULLY covered heart-rate stream must
    # produce the exact same power load and coverage.
    hr_full = _partial(n, n, 140.0)
    activity_hr_full = _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=_samples(n, power_w=power_full, heart_rate_bpm=hr_full),
    )
    power_result_hr_full = power.compute(
        activity_hr_full, power_metrics, ftp=ftp, settings=_SETTINGS
    )
    assert isinstance(power_result_hr_full, ChannelLoad)
    assert power_result.load == power_result_hr_full.load
    assert power_result.coverage.fraction == pytest.approx(1.0)
    assert power_result_hr_full.coverage.fraction == pytest.approx(1.0)

    # Independence, direction 2: the heart-rate channel's insufficiency is
    # unaffected by whether the power stream is present at all -- an
    # otherwise identical activity with NO power stream must report the
    # exact same reason, observed and required values.
    activity_no_power = _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=_samples(n, heart_rate_bpm=hr_thin),
    )
    hr_result_no_power = heart_rate.compute(
        activity_no_power,
        DerivedMetrics(),
        lthr=_lthr(165.0),
        resting_hr=_resting_hr(48.0),
        max_hr=_max_hr(190.0),
        settings=_SETTINGS,
    )
    assert isinstance(hr_result_no_power, ChannelInsufficient)
    assert hr_result_no_power.reason is hr_result.reason
    assert hr_result_no_power.observed == hr_result.observed
    assert hr_result_no_power.required == hr_result.required
