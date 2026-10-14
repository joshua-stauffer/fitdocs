"""Synthetic sustained-peak cases."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import fields

import pytest

from fitdocs.hr_benchmarks.peaks import session_peak
from fitdocs.hr_benchmarks.types import NoEvidenceReason
from fitdocs.load.qa import cadence
from fitdocs.load.qa.types import FlagSettings
from fitdocs.model import Modality, Samples, SessionSummary
from tests.hr_benchmarks.builders import samples


def _reading(outcome: cadence.CadenceLockOutcome) -> cadence.CadenceLockReading:
    return cadence.CadenceLockReading(outcome, None, 17, None, 0, None)


@pytest.mark.parametrize("times,hrs", [((), ()), ((0, 10, 30), (None, None, None))])
def test_no_heart_rate_precedes_detection(
    monkeypatch: pytest.MonkeyPatch,
    times: tuple[int, ...],
    hrs: tuple[None, ...],
) -> None:
    events: list[str] = []

    def detect(*args: object, **kwargs: object) -> cadence.CadenceLockReading:
        events.append("detect")
        return _reading(cadence.CadenceLockOutcome.LOCKED)

    monkeypatch.setattr(cadence, "detect", detect)
    result = session_peak(
        samples(times, hrs), modality=Modality.RUN, flags=FlagSettings()
    )
    assert (result, events) == (NoEvidenceReason.NO_HEART_RATE, [])


@pytest.mark.parametrize("hr", [24, 163])
def test_locked_verdict_precedes_spans_and_sample_filter(
    monkeypatch: pytest.MonkeyPatch, hr: int
) -> None:
    events: list[str] = []

    def spans(*args: object, **kwargs: object) -> tuple[cadence.SpanStatistic, ...]:
        events.append("spans")
        return ()

    monkeypatch.setattr(
        cadence,
        "detect",
        lambda *args, **kwargs: _reading(cadence.CadenceLockOutcome.LOCKED),
    )
    monkeypatch.setattr(cadence, "span_statistics", spans)
    result = session_peak(
        samples([0, 10, 20, 30], [hr] * 4), modality=Modality.RUN, flags=FlagSettings()
    )
    assert (result, events) == (NoEvidenceReason.CADENCE_LOCKED, [])


@pytest.mark.parametrize(
    "times,hrs,expected",
    [
        ([0, 10, 20, 30], [29] * 4, NoEvidenceReason.NO_SUSTAINED_STRETCH),
        ([0, 10, 20, 30], [30] * 4, 30.0),
        ([0, 10, 20, 30], [230] * 4, 230.0),
        ([0, 10, 20, 30], [231] * 4, NoEvidenceReason.NO_SUSTAINED_STRETCH),
        (list(range(41)), [120] * 5 + [220] + [120] * 35, 120.0),
        (list(range(37)), [120] * 5 + [220] + [138] * 31, 138.0),
        (list(range(37)), [200] * 5 + [90] * 32, NoEvidenceReason.NO_SUSTAINED_STRETCH),
        ([0, 10, 20, 30], [100, 200, 200, 200], 5000 / 30),
        ([0, 0, 10, 20, 30], [120, 125, 120, 120, 120], 120.0),
        ([0, 10, 20, 30], [154] * 4, 154.0),
        ([0, 10, 20, 30, 41, 51, 61, 71], [175] * 4 + [145] * 4, 175.0),
        ([0, 10, 20, 30, 41, 51, 61, 71], [135] * 4 + [185] * 4, 185.0),
        (
            [0, 10, 20, 30, 31, 42, 52, 62, 71],
            [140] * 5 + [190] * 4,
            140.0,
        ),
        (
            [0, 10, 19, 30, 40, 49],
            [180] * 3 + [200] * 3,
            NoEvidenceReason.NO_SUSTAINED_STRETCH,
        ),
        ([0, 10, 20, 29], [162] * 4, NoEvidenceReason.NO_SUSTAINED_STRETCH),
        ([0, 10, 20, 30], [162] * 4, 162.0),
        ([0, 10, 20, 30, 31], [162] * 5, 162.0),
        ([0, 10, 20, 30], [100, 120, 140, 160], 120.0),
        ([0, 2, 10, 20, 30], [100, 110, 130, 150, 170], 3880 / 30),
        ([0, 6, 14, 23, 31, 40, 49], [121, 116, 156, 143, 145, 141, 156], 4417 / 30),
        ([0, 6, 14, 23, 31, 40, 49], [117, 127, 131, 169, 129, 147, 127], 4360 / 30),
        (
            [0, 10, 20, 30, 40],
            [170, None, 180, 180, 180],
            NoEvidenceReason.NO_SUSTAINED_STRETCH,
        ),
        ([0], [176], NoEvidenceReason.NO_SUSTAINED_STRETCH),
        (
            [0, 10, 20, 30],
            [None, None, 166, None],
            NoEvidenceReason.NO_SUSTAINED_STRETCH,
        ),
    ],
    ids=[
        "below-range",
        "inclusive-low",
        "inclusive-high",
        "above-range",
        "spike",
        "previous-kept",
        "falling-rate",
        "inclusive-rate",
        "duplicate-time",
        "gap-ten",
        "higher-first-stretch",
        "higher-second-stretch",
        "shorter-higher-stretch",
        "no-bridge",
        "length-29",
        "length-30",
        "length-31",
        "forward-hold",
        "irregular-weight",
        "sample-start-family",
        "sample-end-family",
        "missing-hr-gap",
        "single-sample",
        "isolated-hr",
    ],
)
def test_sample_rules_and_windows(
    times: list[int], hrs: list[int | None], expected: float | NoEvidenceReason
) -> None:
    result = session_peak(
        samples(times, hrs), modality=Modality.BIKE, flags=FlagSettings()
    )
    assert result == (
        expected if isinstance(expected, NoEvidenceReason) else pytest.approx(expected)
    )


def _overlap_reference(times: Sequence[float], hrs: Sequence[int]) -> float:
    starts = {float(t) for t in times} | {t - 30 for t in times}
    means = [
        sum(
            max(0, min(right, start + 30) - max(left, start)) * hr
            for left, right, hr in zip(times, times[1:], hrs, strict=False)
        )
        / 30
        for start in starts
        if times[0] <= start and start + 30 <= times[-1]
    ]
    return max(means)


@pytest.mark.parametrize("seed", range(12))
def test_generated_stretches_match_interval_overlap_reference(seed: int) -> None:
    rng = random.Random(481 + seed)
    times = [0.0]
    hrs = [rng.randrange(120, 151)]
    for _ in range(45):
        gap = rng.randrange(4, 11)
        times.append(times[-1] + gap + rng.choice([0.0, -0.25]))
        hrs.append(rng.randrange(120, 151))
    result = session_peak(
        samples(times, hrs), modality=Modality.BIKE, flags=FlagSettings()
    )
    assert result == pytest.approx(_overlap_reference(times, hrs))


@pytest.mark.parametrize(
    "modality,expected", [(Modality.RUN, 176.0), (Modality.BIKE, 180.6)]
)
def test_real_locked_span_boundaries_and_modality(
    modality: Modality, expected: float
) -> None:
    hrs = [160] * 32 + [168, 174, 180, 186, 192, 186, 180, 174] + [180] * 25
    cad = [40.0] * 32 + [hr / 2 for hr in hrs[32:40]] + [40.0] * 25
    flags = FlagSettings(cadence_lock_window_s=8, cadence_lock_min_duration_s=16)
    result = session_peak(
        samples(list(range(65)), hrs, cadence=cad), modality=modality, flags=flags
    )
    assert result == pytest.approx(expected)


def test_real_locked_session() -> None:
    hrs = [160 + t % 7 for t in range(65)]
    flags = FlagSettings(cadence_lock_window_s=8, cadence_lock_min_duration_s=16)
    result = session_peak(
        samples(list(range(65)), hrs, cadence=[hr / 2 for hr in hrs]),
        modality=Modality.RUN,
        flags=flags,
    )
    assert result is NoEvidenceReason.CADENCE_LOCKED


@pytest.mark.parametrize("threshold", ["delta", "correlation"])
def test_configured_span_thresholds(threshold: str) -> None:
    hrs = [160] * 32 + [168, 174, 180, 186, 192, 186, 180, 174] + [180] * 25
    paired = (
        [hr + 3 for hr in hrs[32:40]]
        if threshold == "delta"
        else [169, 173, 179, 185, 194, 185, 179, 175]
    )
    cad = [40.0] * 32 + [hr / 2 for hr in paired] + [40.0] * 25
    flags = FlagSettings(
        cadence_lock_window_s=8,
        cadence_lock_min_duration_s=16,
        cadence_lock_max_delta_bpm=2 if threshold == "delta" else 5,
        cadence_lock_min_correlation=0.999 if threshold == "correlation" else 0.9,
    )
    result = session_peak(
        samples(list(range(65)), hrs, cadence=cad), modality=Modality.RUN, flags=flags
    )
    assert result == pytest.approx(180.6)


@pytest.mark.parametrize(
    "hr,summary_max,expected",
    [(143, 245, 143.0), (None, 228, NoEvidenceReason.NO_HEART_RATE)],
    ids=["recorded-hr", "absent-hr"],
)
def test_recorded_summary_maximum_is_a_decoy(
    hr: int | None, summary_max: int, expected: float | NoEvidenceReason
) -> None:
    summary = SessionSummary(
        sport="cycling",
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=30,
        total_timer_time_s=30,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=summary_max,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )

    class SummaryDecoySamples(Samples):
        @property
        def summary(self) -> SessionSummary:
            return summary

    recorded = samples([0, 10, 20, 30], [hr] * 4)
    stream = SummaryDecoySamples(
        **{field.name: getattr(recorded, field.name) for field in fields(Samples)}
    )
    result = session_peak(stream, modality=Modality.BIKE, flags=FlagSettings())
    assert result == expected
