"""Synthetic inputs for heart-rate benchmark tests."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

import tomli_w

from fitdocs.benchmarks import (
    ATHLETE_SCOPED,
    Benchmark,
    BenchmarkKind,
    BenchmarkSource,
    BenchmarkSourceKind,
    benchmarks_to_document,
)
from fitdocs.hr_benchmarks.types import HrMethod, SessionPeak
from fitdocs.model import Samples, Sport
from fitdocs.wellness import Metric, SeriesValue


def samples(
    time_s: Sequence[float],
    heart_rate_bpm: Sequence[int | None],
    *,
    cadence: Sequence[float | None] | None = None,
) -> Samples:
    times = tuple(time_s)
    hr = tuple(heart_rate_bpm)
    if len(hr) != len(times):
        raise ValueError("heart-rate length must match times")
    if cadence is not None and len(cadence) != len(times):
        raise ValueError("cadence length must match times")
    if any(right < left for left, right in zip(times, times[1:], strict=False)):
        raise ValueError("non-decreasing times required")
    absent = (None,) * len(times)
    return Samples(
        time_s=times,
        heart_rate_bpm=hr,
        cadence_rpm=absent if cadence is None else tuple(cadence),
        power_w=absent,
        speed_mps=absent,
        distance_m=absent,
        altitude_m=absent,
        latitude_deg=absent,
        longitude_deg=absent,
        temperature_c=absent,
    )


def session_peak(day: date, document: str, peak_bpm: float) -> SessionPeak:
    return SessionPeak(day, document, peak_bpm)


def source_days(
    source: str,
    values: Iterable[tuple[date, float]],
    *,
    canonical: bool = True,
    origin: str | None = None,
    metric: Metric = Metric.RESTING_HR_BPM,
) -> tuple[SeriesValue, ...]:
    return tuple(
        SeriesValue(day, metric, source, origin, value, canonical)
        for day, value in values
    )


def _check_scope(kind: BenchmarkKind, discipline: Sport | None) -> None:
    if (kind in ATHLETE_SCOPED) != (discipline is None):
        raise ValueError("benchmark scope disagrees with discipline")


def hand_benchmark(
    kind: BenchmarkKind,
    day: date,
    value: float,
    *,
    discipline: Sport | None = None,
    note: str | None = None,
    applies_from: date | None = None,
    measured: bool = False,
) -> Benchmark:
    _check_scope(kind, discipline)
    return Benchmark(
        kind,
        discipline,
        value,
        day,
        note,
        applies_from,
        BenchmarkSource(kind=BenchmarkSourceKind.MEASURED) if measured else None,
    )


def derived_benchmark(
    kind: BenchmarkKind,
    day: date,
    value: float,
    *,
    method: HrMethod,
    document: str,
    inputs: str,
    citation: str,
    discipline: Sport | None = None,
    series: str | None = None,
    note: str | None = None,
    applies_from: date | None = None,
) -> Benchmark:
    _check_scope(kind, discipline)
    return Benchmark(
        kind,
        discipline,
        value,
        day,
        note,
        applies_from,
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method=method.value,
            document=document,
            inputs=inputs,
            citation=citation,
            series=series,
        ),
    )


def make_data_root(path: Path, entries: Sequence[Benchmark] = ()) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "athlete.toml").write_text(
        tomli_w.dumps(benchmarks_to_document(entries)), encoding="utf-8"
    )
    return path
