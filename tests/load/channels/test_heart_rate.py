"""Tests for the heart-rate channel (``heart_rate.py``).

Covers Requirements 1.6, 1.7, 1.9, 1.11, 5.1, 5.2, 5.3, 5.9, 5.10, 5.11 -- see
``.kiro/specs/load-channels/requirements.md`` and the "Channel --
src/fitdocs/load/channels/heart_rate.py" / "HeartRateChannel" component in
design.md.
"""

from __future__ import annotations

import ast
import inspect
import math
from dataclasses import dataclass, replace
from datetime import date

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate
from fitdocs.load.channels.sources import DIVERGENCES
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    InsufficiencyReason,
    SufficiencySettings,
)
from fitdocs.load.channels.weighting import (
    BANISTER_TRIMP_MODEL,
    BanisterTrimpModel,
    HeartRateIntensityModel,
)
from fitdocs.metrics import sources as metrics_sources
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------


def _samples(
    time_s: tuple[float, ...], heart_rate_bpm: tuple[int | None, ...]
) -> Samples:
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
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


_DENSE_TIME = tuple(float(i) for i in range(3601))
"""One-hour-long, fully-covered span -- 3601 one-second samples so the
recorded span is exactly 3600 s -- used whenever a test needs the gate to
pass cleanly and wants to vary only the heart rate held constant."""


def _dense_activity(heart_rate_bpm: int) -> Activity:
    return _activity(samples=_samples(_DENSE_TIME, (heart_rate_bpm,) * 3601))


def _lthr(
    value: float,
    *,
    discipline: Sport | None = Sport.RUN,
    measured_on: date = date(2026, 1, 1),
) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=discipline,
        value=value,
        measured_on=measured_on,
    )


def _resting_hr(value: float, *, measured_on: date = date(2026, 1, 1)) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=value,
        measured_on=measured_on,
    )


def _max_hr(value: float, *, measured_on: date = date(2026, 1, 1)) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=value,
        measured_on=measured_on,
    )


_SETTINGS = SufficiencySettings()
_METRICS = DerivedMetrics()
"""``metrics`` is accepted for the uniform three-channel ``compute`` shape
and read nowhere by this channel -- an entirely-empty ``DerivedMetrics`` is
deliberately used everywhere in this module so that any accidental read of
one of its fields (especially ``trimp``, Req 5.1's forbidden flat-keyed
metric) would immediately surface as ``None``-handling breakage rather than
being silently masked by a populated fixture."""


@dataclass(frozen=True)
class _FakeModel:
    """A test double for :class:`HeartRateIntensityModel`, injected through
    ``compute``'s own ``model`` parameter -- the natural, already-present
    seam for pinning the delegation contract, no monkeypatching of a
    module-level name required."""

    activity_return: float | None
    hourly_return: float | None
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]]

    def activity_impulse(
        self, samples: Samples, *, resting_hr: int, max_hr: int
    ) -> float | None:
        self.calls.append(
            (
                "activity_impulse",
                (samples,),
                {"resting_hr": resting_hr, "max_hr": max_hr},
            )
        )
        return self.activity_return

    def hourly_impulse_at(
        self, heart_rate: int, *, resting_hr: int, max_hr: int
    ) -> float | None:
        self.calls.append(
            (
                "hourly_impulse_at",
                (heart_rate,),
                {"resting_hr": resting_hr, "max_hr": max_hr},
            )
        )
        return self.hourly_return


# ---------------------------------------------------------------------------
# 1.6 / 5.1 -- one hour at threshold scores exactly 100, intensity 1.0
# ---------------------------------------------------------------------------


def test_one_hour_at_threshold_scores_exactly_100_with_intensity_1() -> None:
    result = heart_rate.compute(
        _dense_activity(165),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(100.0)
    assert result.intensity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 1.11 / 5.11 -- the shared intensity relation, and the square root, not the
# bare impulse ratio -- THE central discrimination of this task. At
# threshold the ratio and its square root are both 1.0 (the multiplicative
# identity) and cannot tell the two definitions apart; only a sub-threshold
# fixture can.
# ---------------------------------------------------------------------------


def test_intensity_relation_holds_at_threshold() -> None:
    result = heart_rate.compute(
        _dense_activity(165),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    expected = (result.scored_duration_s / 3600) * result.intensity**2 * 100
    assert result.load == pytest.approx(expected)


def test_sub_threshold_intensity_is_the_square_root_not_the_bare_ratio() -> None:
    """The discriminating fixture (design.md's worked table row, HR 140 /
    resting 48 / max 190 / LTHR 165): intensity is 0.7489, not the bare
    impulse ratio 0.5608 -- so a wrong implementation that reports the bare
    ratio under the ``intensity`` label is caught here, and nowhere near
    threshold. Expected values are derived from the model itself, not
    hardcoded, so this test does not encode a second, independently-tuned
    formula that could coincidentally agree."""
    model = BanisterTrimpModel()
    activity_impulse = model.activity_impulse(
        _samples(_DENSE_TIME, (140,) * 3601), resting_hr=48, max_hr=190
    )
    reference = model.hourly_impulse_at(165, resting_hr=48, max_hr=190)
    assert activity_impulse is not None and reference is not None
    expected_load = activity_impulse / reference * 100
    expected_bare_ratio = expected_load / 100
    expected_intensity = math.sqrt(expected_bare_ratio)

    result = heart_rate.compute(
        _dense_activity(140),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(expected_load)
    assert result.load == pytest.approx(56.08, abs=0.1)  # design.md worked table

    # The central discrimination: intensity is NOT the bare ratio.
    assert result.intensity != pytest.approx(expected_bare_ratio)
    assert result.intensity == pytest.approx(expected_intensity)
    assert result.intensity == pytest.approx(0.7489, abs=0.001)  # design.md table

    # And the shared load relation still holds under the square-root form.
    relation = (result.scored_duration_s / 3600) * result.intensity**2 * 100
    assert result.load == pytest.approx(relation)


# ---------------------------------------------------------------------------
# 5.11 -- load computed before, and independent of, intensity
# ---------------------------------------------------------------------------


def test_load_is_independent_of_scored_duration_while_intensity_is_not() -> None:
    """``load`` is ``activity_impulse / reference * 100`` alone -- no
    duration term anywhere in it; ``intensity`` alone depends on
    ``scored_duration_s``. A real TRIMP-integrated impulse is itself a time
    integral, so varying an activity's *recorded* duration legitimately
    moves ``activity_impulse`` too and cannot isolate this claim (a
    shorter real activity has genuinely less accumulated impulse, not just
    a different reported duration). A :class:`_FakeModel` that returns
    FIXED impulse/reference values regardless of what ``samples`` it is
    handed isolates the two terms cleanly: only ``scored_duration_s``
    (driven by how much of the stream is covered) differs between the two
    calls below, while the fake's returned impulse and reference -- and
    therefore ``load`` -- do not. ``intensity``, which does read
    ``scored_duration_s``, differs."""
    full_hr: tuple[int | None, ...] = (140,) * 3600 + (None,)
    partial_hr: tuple[int | None, ...] = (140,) * 3200 + (None,) * 401

    full_calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    partial_calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    full = heart_rate.compute(
        _activity(samples=_samples(_DENSE_TIME, full_hr)),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=_FakeModel(activity_return=40.0, hourly_return=80.0, calls=full_calls),
    )
    partial = heart_rate.compute(
        _activity(samples=_samples(_DENSE_TIME, partial_hr)),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=_FakeModel(activity_return=40.0, hourly_return=80.0, calls=partial_calls),
    )
    assert isinstance(full, ChannelLoad)
    assert isinstance(partial, ChannelLoad)

    assert partial.scored_duration_s != pytest.approx(full.scored_duration_s)
    assert partial.load == pytest.approx(full.load)
    assert partial.load == pytest.approx(40.0 / 80.0 * 100)
    assert partial.intensity != pytest.approx(full.intensity)


def test_load_assigned_strictly_before_intensity_in_source() -> None:
    """Structural pin (Req 5.11's "compute and return the load before and
    independently of the intensity"): the ``load`` name is assigned before
    the ``intensity`` name anywhere in ``compute``'s own source, and the
    ``intensity`` expression textually reads ``load`` -- i.e. intensity is
    derived *from* load, not the reverse. This alone would not catch a
    numerically-independent computation of both from the two impulses
    directly (which would also happen to satisfy the relation at every
    effort by construction) -- that possibility is what
    ``test_load_is_independent_of_scored_duration_while_intensity_is_not``
    additionally rules out."""
    source = inspect.getsource(heart_rate.compute)
    load_idx = source.index("\n    load = ")
    intensity_idx = source.index("\n    intensity = ")
    assert load_idx < intensity_idx
    intensity_line = source.splitlines()[source[:intensity_idx].count("\n") + 1]
    assert "load" in intensity_line


def test_naive_bare_ratio_would_agree_with_intensity_only_at_threshold() -> None:
    """Confirms the fixture-discrimination claim itself: at threshold the
    bare ratio and its square root are indistinguishable (both 1.0), so
    ``test_one_hour_at_threshold_scores_exactly_100_with_intensity_1``
    alone cannot pin the square root -- only a sub-threshold fixture can
    (see ``test_sub_threshold_intensity_is_the_square_root_not_the_bare_ratio``)."""
    threshold_result = heart_rate.compute(
        _dense_activity(165),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(threshold_result, ChannelLoad)
    bare_ratio_at_threshold = threshold_result.load / 100
    assert threshold_result.intensity == pytest.approx(bare_ratio_at_threshold)
    assert threshold_result.intensity == pytest.approx(
        math.sqrt(bare_ratio_at_threshold)
    )


# ---------------------------------------------------------------------------
# 1.9 -- the wrong-quantity guard, called at entry, per benchmark, raises
# rather than computing
# ---------------------------------------------------------------------------


def test_wrong_lthr_kind_raises() -> None:
    wrong = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=165,
        measured_on=date(2026, 1, 1),
    )
    with pytest.raises(ValueError, match="lthr_bpm"):
        heart_rate.compute(
            _dense_activity(150),
            _METRICS,
            lthr=wrong,
            resting_hr=_resting_hr(48),
            max_hr=_max_hr(190),
            settings=_SETTINGS,
        )


def test_wrong_resting_hr_kind_raises() -> None:
    wrong = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=250,
        measured_on=date(2026, 1, 1),
    )
    with pytest.raises(ValueError, match="resting_hr_bpm"):
        heart_rate.compute(
            _dense_activity(150),
            _METRICS,
            lthr=_lthr(165),
            resting_hr=wrong,
            max_hr=_max_hr(190),
            settings=_SETTINGS,
        )


def test_wrong_max_hr_kind_raises() -> None:
    wrong = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=165,
        measured_on=date(2026, 1, 1),
    )
    with pytest.raises(ValueError, match="max_hr_bpm"):
        heart_rate.compute(
            _dense_activity(150),
            _METRICS,
            lthr=_lthr(165),
            resting_hr=_resting_hr(48),
            max_hr=wrong,
            settings=_SETTINGS,
        )


def test_wrong_kind_raises_before_the_no_benchmark_check() -> None:
    """The guard runs at entry, strictly before the NO_BENCHMARK check: a
    wrong-kind ``lthr`` whose ``value`` is non-positive still raises, and it
    raises even though ``resting_hr``/``max_hr`` are both absent (which
    alone would be NO_BENCHMARK)."""
    wrong = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=0,
        measured_on=date(2026, 1, 1),
    )
    empty_activity = _activity(samples=_samples((), ()))
    with pytest.raises(ValueError, match="lthr_bpm"):
        heart_rate.compute(
            empty_activity,
            _METRICS,
            lthr=wrong,
            resting_hr=None,
            max_hr=None,
            settings=_SETTINGS,
        )


def test_no_kind_check_when_all_three_are_none() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=None,
        resting_hr=None,
        max_hr=None,
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


# ---------------------------------------------------------------------------
# 5.2 -- NO_BENCHMARK naming every absent one of the three
# ---------------------------------------------------------------------------


def test_no_benchmark_when_lthr_missing_names_lthr() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=None,
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "threshold heart rate" in result.detail
    assert "resting heart rate" not in result.detail
    assert "maximum heart rate" not in result.detail


def test_no_benchmark_when_resting_hr_missing_names_resting_hr() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=None,
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "resting heart rate" in result.detail
    assert "threshold heart rate" not in result.detail
    assert "maximum heart rate" not in result.detail


def test_no_benchmark_when_max_hr_missing_names_max_hr() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=None,
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "maximum heart rate" in result.detail
    assert "threshold heart rate" not in result.detail
    assert "resting heart rate" not in result.detail


def test_no_benchmark_when_all_three_missing_names_all_three() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=None,
        resting_hr=None,
        max_hr=None,
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "threshold heart rate" in result.detail
    assert "resting heart rate" in result.detail
    assert "maximum heart rate" in result.detail


def test_no_benchmark_beats_a_failing_gate() -> None:
    empty_activity = _activity(samples=_samples((), ()))
    result = heart_rate.compute(
        empty_activity,
        _METRICS,
        lthr=None,
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


# ---------------------------------------------------------------------------
# 5.3 -- BENCHMARKS_INCONSISTENT, and that it is decided before the gate
# ---------------------------------------------------------------------------


def test_inconsistent_when_resting_and_max_are_equal() -> None:
    """NOTE on what this fixture actually isolates: production's
    inconsistency check is ``max<=resting OR lthr<=resting OR lthr>max``.
    The first disjunct (``max_hr.value <= resting_hr.value``) is logically
    REDUNDANT given the other two: if ``lthr > resting`` and ``lthr <= max``
    both hold (i.e. the other two disjuncts are both false), then
    transitively ``max >= lthr > resting``, so ``max > resting`` always --
    there is no reachable input for which ``max <= resting`` is true while
    the other two are false. Deleting or weakening that first disjunct
    therefore passes every test in this module; it is an equivalent
    mutant, not a coverage gap (confirmed under Fixture Discrimination).
    This fixture (resting=190, max=190, lthr=165) is inconsistent because
    ``lthr <= resting`` (165 <= 190) -- the SECOND disjunct -- not because
    of the first, despite the function's name; kept, and named for what it
    actually exercises, rather than removed, because ``max == resting`` is
    still a real inconsistent-benchmarks case worth a fixture of its own."""
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(190),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.BENCHMARKS_INCONSISTENT


def test_inconsistent_when_lthr_not_above_resting() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(48),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.BENCHMARKS_INCONSISTENT


def test_inconsistent_when_lthr_above_max() -> None:
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(200),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.BENCHMARKS_INCONSISTENT


def test_lthr_exactly_at_max_is_consistent() -> None:
    """The boundary is inclusive on the top: ``lthr <= max_hr``, not
    ``lthr < max_hr`` -- ``lthr == max_hr`` must compute, not reject."""
    result = heart_rate.compute(
        _dense_activity(190),
        _METRICS,
        lthr=_lthr(190),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)


def test_inconsistent_benchmarks_beats_a_failing_gate() -> None:
    empty_activity = _activity(samples=_samples((), ()))
    result = heart_rate.compute(
        empty_activity,
        _METRICS,
        lthr=_lthr(48),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.BENCHMARKS_INCONSISTENT


# ---------------------------------------------------------------------------
# 5.9 -- gate on the heart-rate stream; scored duration is covered time
# ---------------------------------------------------------------------------


def test_stream_absent_when_heart_rate_never_recorded() -> None:
    time_s = tuple(float(i) for i in range(120))
    activity = _activity(samples=_samples(time_s, (None,) * len(time_s)))
    result = heart_rate.compute(
        activity,
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.STREAM_ABSENT


def test_too_short_when_recorded_span_below_minimum_duration() -> None:
    time_s = (0.0, 1.0, 2.0)
    activity = _activity(samples=_samples(time_s, (150, 150, 150)))
    result = heart_rate.compute(
        activity,
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT


def test_stream_coverage_when_below_configured_minimum() -> None:
    time_s = tuple(float(i) for i in range(120))
    hr = tuple(150 if i < 60 else None for i in range(120))
    activity = _activity(samples=_samples(time_s, hr))
    result = heart_rate.compute(
        activity,
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert result.observed is not None
    assert result.required == pytest.approx(0.80)


def test_scored_duration_is_the_gates_covered_time_not_the_recorded_span() -> None:
    """Req 5.9's "scored duration is the covered time the impulse actually
    integrated over" -- pinned by a fixture whose recorded SPAN (999 s) and
    COVERED time (900 s) differ, so a wrong implementation reporting
    ``coverage.total_s`` (or the activity's raw elapsed time) instead of
    ``coverage.covered_s`` is caught."""
    time_s = tuple(float(i) for i in range(1000))
    hr = tuple(150 if i < 900 else None for i in range(1000))
    activity = _activity(samples=_samples(time_s, hr))
    result = heart_rate.compute(
        activity,
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.coverage.total_s == pytest.approx(999.0)
    assert result.coverage.covered_s == pytest.approx(900.0)
    assert result.scored_duration_s == pytest.approx(900.0)
    assert result.scored_duration_s != pytest.approx(result.coverage.total_s)


# ---------------------------------------------------------------------------
# NOT_COMPUTABLE -- when the injected model cannot produce a value, gate
# having passed
# ---------------------------------------------------------------------------


def test_not_computable_when_activity_impulse_is_none() -> None:
    fake = _FakeModel(activity_return=None, hourly_return=50.0, calls=[])
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.HEART_RATE
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_when_reference_is_none() -> None:
    fake = _FakeModel(activity_return=50.0, hourly_return=None, calls=[])
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_when_reference_is_non_positive() -> None:
    fake = _FakeModel(activity_return=50.0, hourly_return=0.0, calls=[])
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_and_no_benchmark_are_pairwise_distinct_reasons() -> None:
    """Four insufficiency sites this channel can return, each pinned
    pairwise -- NOT chained (Python chains ``a != b != c`` as
    ``a != b and b != c``, silently skipping the ``a`` vs ``c`` comparison;
    that bug previously let the NOT_COMPUTABLE and BENCHMARKS_INCONSISTENT
    detail texts be interchangeable without reddening anything). Each pair
    among the four is compared explicitly, and each detail's own content is
    pinned too, not merely its distinctness from its neighbors."""
    fake = _FakeModel(activity_return=None, hourly_return=50.0, calls=[])
    not_computable = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    no_benchmark = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=None,
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    inconsistent = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(48),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    empty_activity = _activity(samples=_samples((), ()))
    gate_failure = heart_rate.compute(
        empty_activity,
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )

    assert isinstance(not_computable, ChannelInsufficient)
    assert isinstance(no_benchmark, ChannelInsufficient)
    assert isinstance(inconsistent, ChannelInsufficient)
    assert isinstance(gate_failure, ChannelInsufficient)

    reasons = {
        not_computable.reason,
        no_benchmark.reason,
        inconsistent.reason,
        gate_failure.reason,
    }
    assert reasons == {
        InsufficiencyReason.NOT_COMPUTABLE,
        InsufficiencyReason.NO_BENCHMARK,
        InsufficiencyReason.BENCHMARKS_INCONSISTENT,
        InsufficiencyReason.TOO_SHORT,
    }

    # Each detail's own content, pinned individually -- not merely asserted
    # distinct from its neighbors.
    assert "impulse" in not_computable.detail or "reference" in not_computable.detail
    assert "threshold heart rate" in no_benchmark.detail
    assert "inconsistent" in inconsistent.detail
    assert "heart_rate" in gate_failure.detail

    # Explicit pairwise comparisons across all C(4, 2) = 6 pairs -- a
    # chained ``a != b != c != d`` here would (as it did before) skip every
    # non-adjacent pair.
    outcomes = {
        "not_computable": not_computable,
        "no_benchmark": no_benchmark,
        "inconsistent": inconsistent,
        "gate_failure": gate_failure,
    }
    names = list(outcomes)
    for i, name_a in enumerate(names):
        for name_b in names[i + 1 :]:
            detail_a = outcomes[name_a].detail
            detail_b = outcomes[name_b].detail
            assert detail_a != detail_b, (
                f"{name_a}.detail == {name_b}.detail == {detail_a!r}"
            )

    for outcome in outcomes.values():
        assert outcome.channel is ChannelId.HEART_RATE


# ---------------------------------------------------------------------------
# Delegation pinning -- the three-test pattern (value-equality does not pin
# a delegation contract)
# ---------------------------------------------------------------------------


def test_default_model_parameter_is_the_shipped_singleton_by_identity() -> None:
    """Identity, not value-equality: the ``model`` parameter's own default
    is the real shipped ``BANISTER_TRIMP_MODEL`` object, not a freshly
    constructed, merely-equal instance."""
    default = inspect.signature(heart_rate.compute).parameters["model"].default
    assert default is BANISTER_TRIMP_MODEL


def test_module_calls_model_activity_impulse_and_hourly_impulse_at_by_name() -> None:
    """Structural (Req 5.1): ``compute``'s own source calls
    ``model.activity_impulse(`` and ``model.hourly_impulse_at(`` literally
    -- the injected Protocol's two methods, called on the ``model``
    parameter specifically, not on a hardcoded module-level singleton."""
    source = inspect.getsource(heart_rate.compute)
    assert "model.activity_impulse(" in source
    assert "model.hourly_impulse_at(" in source
    assert "BANISTER_TRIMP_MODEL.activity_impulse(" not in source
    assert "BANISTER_TRIMP_MODEL.hourly_impulse_at(" not in source


def test_module_defines_no_second_function_and_no_lambda() -> None:
    source = inspect.getsource(heart_rate)
    tree = ast.parse(source)
    defined_functions = [
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ]
    assert defined_functions == ["compute"]
    lambdas = [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)]
    assert lambdas == []


def test_compute_calls_the_injected_model_once_each_with_exact_caller_objects() -> None:
    """The monkeypatch half of the three-test pattern: a fake model,
    injected exactly as a real caller would (via the ``model=`` keyword,
    the natural DI seam here), is called exactly once per method, with the
    *exact* ``samples`` object (``is``, not just ``==``) and the exact
    integer thresholds this call derived from the caller's benchmarks --
    and the fake's return values pass straight through into ``load``
    unmodified."""
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    fake = _FakeModel(activity_return=40.0, hourly_return=80.0, calls=calls)
    activity = _dense_activity(150)

    result = heart_rate.compute(
        activity,
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )

    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(40.0 / 80.0 * 100)

    assert len(calls) == 2
    activity_call = next(c for c in calls if c[0] == "activity_impulse")
    hourly_call = next(c for c in calls if c[0] == "hourly_impulse_at")

    assert activity_call[1][0] is activity.samples
    assert activity_call[2] == {"resting_hr": 48, "max_hr": 190}
    assert hourly_call[1][0] == 165
    assert hourly_call[2] == {"resting_hr": 48, "max_hr": 190}

    assert len([c for c in calls if c[0] == "activity_impulse"]) == 1
    assert len([c for c in calls if c[0] == "hourly_impulse_at"]) == 1


def test_ignoring_the_injected_model_parameter_would_red_the_call_path_test() -> None:
    """Confirms the monkeypatch above is not a no-op: a production version
    that hardcoded ``BANISTER_TRIMP_MODEL`` instead of reading the ``model``
    parameter would leave ``fake.calls`` empty and ``result.load`` computed
    from the real model instead of the fake's sentinel values -- this test
    documents that expectation directly rather than only asserting it
    holds. (Verified manually during Fixture Discrimination: production's
    ``model.activity_impulse``/``model.hourly_impulse_at`` call sites were
    rebound to
    ``BANISTER_TRIMP_MODEL.activity_impulse``/``.hourly_impulse_at`` and
    ``test_compute_calls_the_injected_model_once_each_with_exact_caller_objects``
    reddened with a load mismatch, while every other test in this file that
    used the real default model stayed green.)"""
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    fake = _FakeModel(activity_return=999.0, hourly_return=1.0, calls=calls)
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
        model=fake,
    )
    assert isinstance(result, ChannelLoad)
    # 999/1*100 is wildly different from anything the real model would ever
    # produce for a 150 bpm effort against LTHR 165 -- a hardcoded-model
    # implementation could never reach this value.
    assert result.load == pytest.approx(99900.0)
    assert calls


# ---------------------------------------------------------------------------
# 5.10 -- coefficient rescale invariance: the computed LOAD is unchanged
# when the shipped weighting's multiplicative coefficient is rescaled
# ---------------------------------------------------------------------------


def test_load_unchanged_when_shipped_coefficient_is_rescaled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """design.md's own statement of this observable is two-sided: the HRSS
    is unchanged "while the raw impulse moves". Asserting only the first
    half is vacuously satisfiable by a bug that caches the weighting pair
    at import and never re-reads ``weighting_for`` at all -- ``load`` would
    then trivially stay put because NOTHING moved, not because both terms
    moved together. The second assertion below, reading the raw impulse
    off this channel's own ``inputs_used`` (the value this module itself
    reports, not a second independently-computed number), closes that
    hole: it must move, by exactly the rescale factor, or the invariance
    above is not being exercised at all."""
    baseline = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(baseline, ChannelLoad)

    original_pair = metrics_sources.weighting_for(None)
    factor = 3.0
    rescaled_coefficient = replace(
        original_pair.coefficient, value=original_pair.coefficient.value * factor
    )
    rescaled_pair = replace(original_pair, coefficient=rescaled_coefficient)
    monkeypatch.setattr(
        metrics_sources, "weighting_for", lambda selection: rescaled_pair
    )

    rescaled = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(rescaled, ChannelLoad)
    assert rescaled.load == pytest.approx(baseline.load)
    # The intensity, derived from the (unchanged) load, is therefore also
    # unchanged.
    assert rescaled.intensity == pytest.approx(baseline.intensity)

    # Non-vacuity: the raw impulse -- one of the two terms load is built
    # from -- genuinely moved by the rescale factor. If it had not moved,
    # the load-invariance assertions above would prove nothing.
    baseline_impulse = float(dict(baseline.inputs_used)["impulse"])
    rescaled_impulse = float(dict(rescaled.inputs_used)["impulse"])
    # ``inputs_used`` reports impulse via ``:g`` (6 significant figures), so
    # a slightly looser relative tolerance than the default absorbs that
    # formatting round-trip without weakening the discrimination itself
    # (the factor-of-3 move is far larger than this tolerance).
    assert rescaled_impulse != pytest.approx(baseline_impulse)
    assert rescaled_impulse == pytest.approx(baseline_impulse * factor, rel=1e-4)


# ---------------------------------------------------------------------------
# inputs_used -- impulse, reference, all three HR inputs, anchor's date
# ---------------------------------------------------------------------------


def test_inputs_used_carries_impulse_reference_and_all_three_hr_inputs() -> None:
    measured = date(2026, 3, 14)
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165, measured_on=measured),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    inputs = dict(result.inputs_used)
    assert "impulse" in inputs
    assert "reference" in inputs
    assert inputs["lthr_bpm"] == "165"
    assert inputs["resting_hr_bpm"] == "48"
    assert inputs["max_hr_bpm"] == "190"
    assert inputs["lthr_measured_on"] == measured.isoformat()


def test_benchmark_values_are_truncated_not_rounded_and_inputs_used_matches() -> None:
    """``round()`` would pass every other test in this module -- the
    fixtures elsewhere all use whole-number bpm values, which round() and
    int() agree on. A fractional benchmark (165.7) discriminates the two:
    ``int(165.7) == 165`` (truncation) while ``round(165.7) == 166``. Both
    the value actually handed to the injected model AND the value reported
    in ``inputs_used`` (Req 1.3: inputs_used must name the values that
    produced the result) are pinned to the truncated integer here, so a
    swap to ``round()`` -- or an ``inputs_used`` that reports the raw,
    untruncated ``Benchmark.value`` instead of the integer actually
    delegated to the model -- reds this test."""
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    fake = _FakeModel(activity_return=40.0, hourly_return=80.0, calls=calls)
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=_lthr(165.7),
        resting_hr=_resting_hr(48.9),
        max_hr=_max_hr(190.2),
        settings=_SETTINGS,
        model=fake,
    )
    assert isinstance(result, ChannelLoad)

    activity_call = next(c for c in calls if c[0] == "activity_impulse")
    hourly_call = next(c for c in calls if c[0] == "hourly_impulse_at")
    assert activity_call[2] == {"resting_hr": 48, "max_hr": 190}
    assert hourly_call[1][0] == 165
    assert hourly_call[2] == {"resting_hr": 48, "max_hr": 190}

    inputs = dict(result.inputs_used)
    assert inputs["lthr_bpm"] == "165"
    assert inputs["resting_hr_bpm"] == "48"
    assert inputs["max_hr_bpm"] == "190"


def test_successful_result_carries_coverage_channel_and_anchor_identity() -> None:
    lthr = _lthr(165)
    result = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=lthr,
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.channel is ChannelId.HEART_RATE
    assert result.coverage.stream == "heart_rate"
    assert result.anchor is lthr


# ---------------------------------------------------------------------------
# 1.7 -- independence: sequential calls with different inputs never leak
# state into one another
# ---------------------------------------------------------------------------


def test_sequential_calls_are_independent() -> None:
    result_a = heart_rate.compute(
        _dense_activity(165),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    result_b = heart_rate.compute(
        _dense_activity(150),
        _METRICS,
        lthr=None,
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    result_c = heart_rate.compute(
        _dense_activity(140),
        _METRICS,
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )

    assert isinstance(result_a, ChannelLoad)
    assert result_a.load == pytest.approx(100.0)
    assert isinstance(result_b, ChannelInsufficient)
    assert result_b.reason is InsufficiencyReason.NO_BENCHMARK
    assert isinstance(result_c, ChannelLoad)
    assert result_c.load == pytest.approx(56.08, abs=0.1)


# ---------------------------------------------------------------------------
# 5.10 / 5.11 -- the intervals.icu material: load is an interop match, the
# reported intensity is the one stated divergence, pointing at the entry
# task 1.1 recorded
# ---------------------------------------------------------------------------


def test_module_docstring_names_the_correct_divergence_entry() -> None:
    """Mirrors the power channel's own divergence-provenance test's full
    shape (``test_power.py::test_module_docstring_names_the_correct_
    divergence_entry``), which asserts a distinctive phrase against BOTH
    the citation record's own ``reason`` text AND the module docstring
    itself -- the second half is the one that actually rules out an
    inverted paragraph; asserting only against ``hr_divergence.reason`` (a
    value pinned elsewhere, in ``test_sources.py``) proves nothing about
    what this module's own prose says. (This does not rule out a
    fabricated *causal clause* appended alongside the two phrases below --
    e.g. an invented "so it matches Strava's published relative-effort
    scale" -- only an inverted or dropped *claim*; that is the same
    substring-matching limit ``test_power.py``'s equivalent test already
    carries, accepted rather than re-engineered.) Both distinctive phrases
    below are quoted verbatim from the ``heart_rate_reported_intensity``
    entry's own ``reason`` field and checked against the
    (whitespace-normalized, so a mid-phrase line wrap cannot cause a false
    red) module docstring: "directly comparable" (the load's claim) and
    "Numeric identity is not claimed" (the explicit limit on that claim)
    -- a paragraph that inverted either claim (e.g. "fitdocs reproduces
    its published intensity exactly", or dropping the non-claim of
    numeric identity) would not contain this second phrase."""
    hr_divergence = next(
        d for d in DIVERGENCES if d.behavior == "heart_rate_reported_intensity"
    )
    assert "directly comparable" in hr_divergence.reason
    assert "Numeric identity is not claimed" in hr_divergence.reason

    doc = " ".join((inspect.getdoc(heart_rate) or "").split())
    assert hr_divergence.behavior in doc
    assert "intervals.icu" in doc
    assert "no heart-rate intensity definition" in doc
    assert "directly comparable" in doc
    assert "Numeric identity is not claimed" in doc


def test_module_docstring_does_not_overclaim_load_identity_with_intervals_icu() -> None:
    """Spec-conflict guard: the ``INTERVALS_ICU_HRSS`` citation's own note
    (``sources.py``, "Resolved 2026-07-26") states the read text supports
    only the shared scale, explicitly NOT that intervals.icu "computes the
    heart-rate load the same way" and NOT "requires the same three inputs"
    -- both overclaims previously stood in this module's docstring and are
    now retired. ``tasks.md``'s task 3.2 bullet, predating that citation
    correction by one day, still asks for the retired wording; this test
    enforces the corrected citation instead (queued for a maintainer
    ruling on the stale bullet, not blocked on here)."""
    doc = " ".join((inspect.getdoc(heart_rate) or "").split())
    assert "computes the heart-rate load the same way" not in doc
    assert "requires the same three inputs" not in doc
    assert "interop match" not in doc


# ---------------------------------------------------------------------------
# HeartRateIntensityModel Protocol conformance sanity (not a delegation
# pin by itself -- the identity/structural/monkeypatch trio above is)
# ---------------------------------------------------------------------------


def test_banister_trimp_model_satisfies_the_protocol() -> None:
    model: HeartRateIntensityModel = BANISTER_TRIMP_MODEL
    assert model.model_id == "banister-trimp"
