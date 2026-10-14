from __future__ import annotations

import dataclasses
import inspect
import tomllib
from datetime import date
from pathlib import Path
from typing import get_type_hints

import pytest

import fitdocs.hr_benchmarks.types as types
from fitdocs.benchmarks import (
    ATHLETE_SCOPED,
    Benchmark,
    BenchmarkKind,
    BenchmarkSource,
    BenchmarkSourceKind,
    parse_benchmarks,
)
from fitdocs.model import Sport
from fitdocs.performance.types import TAGGED_EFFORT_KINDS
from fitdocs.wellness import Metric, SeriesValue, read_series
from tests.hr_benchmarks.builders import (
    derived_benchmark,
    hand_benchmark,
    make_data_root,
    samples,
    session_peak,
    source_days,
)
from tests.wellness.builders_series import write_series

CONTRACTS = {
    "SessionPeak": [("day", "date"), ("document", "str"), ("peak_bpm", "float")],
    "Evidence": [
        ("day", "date"),
        ("value", "int"),
        ("key", "str"),
        ("document", "str"),
        ("series", "str | None"),
        ("inputs", "str"),
        ("summary", "str"),
    ],
    "KindRule": [
        ("kind", "BenchmarkKind"),
        ("method", "HrMethod"),
        ("citation_key", "str"),
        ("step_bpm", "int"),
        ("confirm_days", "int"),
    ],
    "Takeover": [
        ("kind", "BenchmarkKind"),
        ("derived", "Benchmark"),
        ("superseded", "Benchmark"),
    ],
    "BackReach": [
        ("kind", "BenchmarkKind"),
        ("entry", "Benchmark"),
        ("starts_on", "date"),
        ("ends_before", "date"),
    ],
    "BackReachChange": [
        ("kind", "BenchmarkKind"),
        ("entry", "Benchmark"),
        ("before", "tuple[date, date]"),
        ("after", "tuple[date, date]"),
    ],
    "Inconsistency": [
        ("violation", "Violation"),
        ("starts_on", "date"),
        ("ends_before", "date | None"),
        ("discipline", "Sport | None"),
        ("max_hr", "Benchmark"),
        ("resting_hr", "Benchmark"),
        ("lthr", "Benchmark | None"),
    ],
    "SkippedDocument": [
        ("document", "str"),
        ("reason", "NoEvidenceReason"),
        ("detail", "str"),
    ],
    "HrFailure": [("kind", "BenchmarkKind"), ("subject", "str"), ("reason", "str")],
    "KindOutcome": [
        ("kind", "BenchmarkKind"),
        ("entries", "tuple[Benchmark, ...]"),
        ("added", "tuple[Benchmark, ...]"),
        ("removed", "tuple[Benchmark, ...]"),
        ("kept", "bool"),
    ],
    "HrStageReport": [
        ("considered", "int"),
        ("with_evidence", "int"),
        ("no_evidence", "tuple[tuple[NoEvidenceReason, int], ...]"),
        ("skipped", "tuple[SkippedDocument, ...]"),
        ("resting_sources", "tuple[str, ...]"),
        ("kinds", "tuple[KindOutcome, ...]"),
        ("takeovers", "tuple[Takeover, ...]"),
        ("back_reach_changes", "tuple[BackReachChange, ...]"),
        ("inconsistencies", "tuple[Inconsistency, ...]"),
        ("failures", "tuple[HrFailure, ...]"),
        ("notes", "tuple[str, ...]"),
        ("written", "bool"),
        ("changed", "bool"),
    ],
}


def test_kind_partition() -> None:
    assert (
        frozenset({BenchmarkKind.RESTING_HR_BPM, BenchmarkKind.MAX_HR_BPM})
        == types.HR_KINDS
    )


def test_kind_partition_is_athlete_scoped() -> None:
    assert types.HR_KINDS <= ATHLETE_SCOPED


def test_partitions_are_disjoint() -> None:
    assert types.HR_KINDS.isdisjoint(TAGGED_EFFORT_KINDS)


@pytest.mark.parametrize(
    ("enum_name", "expected"),
    [
        (
            "HrMethod",
            {
                "RESTING_HR_SERIES_MEDIAN": "resting_hr_series_median",
                "MAX_HR_SUSTAINED_PEAK": "max_hr_sustained_peak",
            },
        ),
        (
            "NoEvidenceReason",
            {
                "UNDATED": "undated",
                "ARCHIVE_MISSING": "archive_missing",
                "ARCHIVE_UNDECODABLE": "archive_undecodable",
                "NO_HEART_RATE": "no_heart_rate",
                "CADENCE_LOCKED": "cadence_locked",
                "NO_SUSTAINED_STRETCH": "no_sustained_stretch",
            },
        ),
        (
            "Violation",
            {
                "MAX_NOT_ABOVE_REST": "max_not_above_rest",
                "THRESHOLD_OUTSIDE_RESERVE": "threshold_outside_reserve",
            },
        ),
    ],
)
def test_closed_tokens(enum_name: str, expected: dict[str, str]) -> None:
    enum = getattr(types, enum_name)
    assert tuple(
        (name, member.value) for name, member in enum.__members__.items()
    ) == tuple(expected.items())
    assert all(isinstance(member, str) for member in enum)


@pytest.mark.parametrize("name", CONTRACTS)
def test_field_order_and_types(name: str) -> None:
    cls = getattr(types, name)
    hints = get_type_hints(cls)
    namespace = {
        **vars(types),
        "date": date,
        "Benchmark": Benchmark,
        "BenchmarkKind": BenchmarkKind,
        "Sport": Sport,
    }
    assert [(field.name, hints[field.name]) for field in dataclasses.fields(cls)] == [
        (field_name, eval(hint, namespace)) for field_name, hint in CONTRACTS[name]
    ]


@pytest.mark.parametrize("name", CONTRACTS)
def test_no_defaults(name: str) -> None:
    assert [
        (field.default, field.default_factory)
        for field in dataclasses.fields(getattr(types, name))
    ] == [(dataclasses.MISSING, dataclasses.MISSING) for _ in CONTRACTS[name]]


def _values(name: str) -> dict[str, object]:
    return {field_name: object() for field_name, _ in CONTRACTS[name]}


@pytest.mark.parametrize("name", CONTRACTS)
def test_every_argument_required(name: str) -> None:
    cls = getattr(types, name)
    signature = inspect.signature(cls)
    values = _values(name)
    cls(**values)
    cls(*values.values())
    for omitted in values:
        with pytest.raises(TypeError):
            signature.bind(
                **{key: value for key, value in values.items() if key != omitted}
            )


@pytest.mark.parametrize("name", CONTRACTS)
def test_frozen(name: str) -> None:
    cls = getattr(types, name)
    value = cls(**_values(name))
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, CONTRACTS[name][0][0], "replacement")


def test_samples_preserve_explicit_channels() -> None:
    value = samples((0.0, 2.5, 11.0), (153, None, 187), cadence=(73.5, 88.0, None))
    assert (value.time_s, value.heart_rate_bpm, value.cadence_rpm) == (
        (0.0, 2.5, 11.0),
        (153, None, 187),
        (73.5, 88.0, None),
    )


def test_samples_absent_channels() -> None:
    value = samples((0.0, 7.0), (None, 164))
    assert {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {"time_s", "heart_rate_bpm"}
    } == {
        field.name: (None, None)
        for field in dataclasses.fields(value)
        if field.name not in {"time_s", "heart_rate_bpm"}
    }


@pytest.mark.parametrize(
    ("times", "hr", "cadence", "message"),
    [
        ((0.0, 4.0), (163,), None, "heart-rate length"),
        ((0.0, 4.0), (163, 171), (81.0,), "cadence length"),
        ((4.0, 0.0), (163, 171), None, "non-decreasing times"),
    ],
)
def test_samples_reject_invalid_inputs(
    times: tuple[float, ...],
    hr: tuple[int, ...],
    cadence: tuple[float, ...] | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        samples(times, hr, cadence=cadence)


def test_session_peak_preserves_arguments() -> None:
    assert session_peak(
        date(2024, 7, 3), "workouts/example.md", 183.75
    ) == types.SessionPeak(date(2024, 7, 3), "workouts/example.md", 183.75)


def test_source_days_preserve_source_dates_and_values() -> None:
    values = source_days(
        "apple-health",
        ((date(2025, 1, 3), 63.5), (date(2024, 12, 31), 47.0)),
        canonical=False,
        origin="phone",
        metric=Metric.HRV_SDNN_MS,
    )
    assert values == (
        SeriesValue(
            date(2025, 1, 3), Metric.HRV_SDNN_MS, "apple-health", "phone", 63.5, False
        ),
        SeriesValue(
            date(2024, 12, 31), Metric.HRV_SDNN_MS, "apple-health", "phone", 47.0, False
        ),
    )


def test_source_days_defaults() -> None:
    assert source_days("garmin-export", ((date(2025, 2, 7), 58.0),)) == (
        SeriesValue(
            date(2025, 2, 7), Metric.RESTING_HR_BPM, "garmin-export", None, 58.0, True
        ),
    )


@pytest.mark.parametrize("measured", [False, True])
def test_hand_benchmark_preserves_arguments(measured: bool) -> None:
    value = hand_benchmark(
        BenchmarkKind.LTHR_BPM,
        date(2025, 8, 7),
        173,
        discipline=Sport.RUN,
        note="field test",
        applies_from=date(2025, 7, 2),
        measured=measured,
    )
    assert value == Benchmark(
        BenchmarkKind.LTHR_BPM,
        Sport.RUN,
        173,
        date(2025, 8, 7),
        "field test",
        date(2025, 7, 2),
        BenchmarkSource(BenchmarkSourceKind.MEASURED) if measured else None,
    )


def test_hand_benchmark_defaults() -> None:
    assert hand_benchmark(
        BenchmarkKind.RESTING_HR_BPM, date(2025, 3, 6), 59
    ) == Benchmark(BenchmarkKind.RESTING_HR_BPM, None, 59, date(2025, 3, 6))


def test_derived_benchmark_preserves_arguments() -> None:
    value = derived_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        date(2025, 9, 11),
        191,
        method=types.HrMethod.MAX_HR_SUSTAINED_PEAK,
        document="workouts/high.md",
        inputs="three peaks",
        citation="custom-record",
        series="garmin-export:resting_hr_bpm",
        note="synthetic",
        applies_from=date(2025, 8, 4),
    )
    assert value == Benchmark(
        BenchmarkKind.MAX_HR_BPM,
        None,
        191,
        date(2025, 9, 11),
        "synthetic",
        date(2025, 8, 4),
        BenchmarkSource(
            BenchmarkSourceKind.DERIVED,
            "max_hr_sustained_peak",
            "workouts/high.md",
            "three peaks",
            "custom-record",
            "garmin-export:resting_hr_bpm",
        ),
    )


def test_derived_benchmark_defaults() -> None:
    assert derived_benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        date(2025, 10, 3),
        61,
        method=types.HrMethod.RESTING_HR_SERIES_MEDIAN,
        document="wellness/2025.csv",
        inputs="14 daily values",
        citation="resting_hr_timeline_choice",
    ) == Benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        None,
        61,
        date(2025, 10, 3),
        source=BenchmarkSource(
            BenchmarkSourceKind.DERIVED,
            "resting_hr_series_median",
            "wellness/2025.csv",
            "14 daily values",
            "resting_hr_timeline_choice",
        ),
    )


@pytest.mark.parametrize("builder", [hand_benchmark, derived_benchmark])
@pytest.mark.parametrize(
    ("kind", "discipline"),
    [(BenchmarkKind.MAX_HR_BPM, Sport.RUN), (BenchmarkKind.LTHR_BPM, None)],
)
def test_benchmark_builders_reject_wrong_scope(
    builder: object, kind: BenchmarkKind, discipline: Sport | None
) -> None:
    if builder is hand_benchmark:
        with pytest.raises(ValueError, match="scope"):
            hand_benchmark(kind, date(2025, 4, 1), 179, discipline=discipline)
    else:
        with pytest.raises(ValueError, match="scope"):
            derived_benchmark(
                kind,
                date(2025, 4, 1),
                179,
                discipline=discipline,
                method=types.HrMethod.MAX_HR_SUSTAINED_PEAK,
                document="workouts/a.md",
                inputs="test",
                citation="test",
            )


def test_data_root_writes_profile(tmp_path: Path) -> None:
    entries = (
        hand_benchmark(BenchmarkKind.RESTING_HR_BPM, date(2025, 2, 2), 57),
        derived_benchmark(
            BenchmarkKind.MAX_HR_BPM,
            date(2025, 3, 3),
            189,
            method=types.HrMethod.MAX_HR_SUSTAINED_PEAK,
            document="workouts/a.md",
            inputs="three sessions",
            citation="max_hr_timeline_choice",
        ),
    )
    root = make_data_root(tmp_path / "nested", entries)
    assert root == tmp_path / "nested"
    assert (
        parse_benchmarks(tomllib.loads((root / "athlete.toml").read_text())).entries
        == entries
    )


def test_data_root_fixture_is_empty_profile(data_root: Path, tmp_path: Path) -> None:
    assert data_root == tmp_path / "data"
    assert tomllib.loads((data_root / "athlete.toml").read_text()) == {"benchmarks": {}}


def test_source_days_staged_by_shared_writer(data_root: Path) -> None:
    write_series(
        data_root,
        (
            *source_days(
                "garmin-export", ((date(2024, 12, 31), 51.0), (date(2025, 1, 2), 53.0))
            ),
            *source_days(
                "apple-health",
                ((date(2024, 12, 31), 67.0), (date(2025, 1, 2), 69.0)),
                canonical=False,
            ),
        ),
    )
    assert [
        (value.day, value.source, value.value, value.canonical)
        for value in read_series(data_root).values
    ] == [
        (date(2024, 12, 31), "apple-health", 67.0, False),
        (date(2024, 12, 31), "garmin-export", 51.0, True),
        (date(2025, 1, 2), "apple-health", 69.0, False),
        (date(2025, 1, 2), "garmin-export", 53.0, True),
    ]


def test_derived_benchmark_scoped() -> None:
    assert (
        derived_benchmark(
            BenchmarkKind.LTHR_BPM,
            date(2025, 7, 6),
            169,
            discipline=Sport.RIDE,
            method=types.HrMethod.MAX_HR_SUSTAINED_PEAK,
            document="workouts/b.md",
            inputs="fixture",
            citation="fixture-choice",
        ).discipline
        is Sport.RIDE
    )


def test_samples_empty() -> None:
    value = samples((), ())
    assert tuple(getattr(value, field.name) for field in dataclasses.fields(value)) == (
        (),
    ) * len(dataclasses.fields(value))


def test_samples_equal_times() -> None:
    value = samples((0.0, 0.0, 3.0), (157, 161, 179))
    assert (value.time_s, value.heart_rate_bpm) == ((0.0, 0.0, 3.0), (157, 161, 179))
