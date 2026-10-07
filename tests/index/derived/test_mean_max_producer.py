"""Per-page mean-max rows project curves of the composed activity."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from fitdocs.compose.types import ChannelProvenance, SourceContribution
from fitdocs.identity.kinds import SourceKind
from fitdocs.index.derived.mean_max import (
    MEAN_MAX_PRODUCER,
    MEAN_MAX_TABLE,
    MeanMaxProducer,
)
from fitdocs.index.producer import LoadRegionReading, PageComputed, PageDocument
from fitdocs.index.schema import (
    ColumnType,
    TableScope,
    resolve_tables,
)
from fitdocs.metrics.mean_max import MeanMaxChannel, mean_max_curve
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import (
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)


def _samples(
    time_s: tuple[float, ...],
    *,
    power: tuple[int | None, ...],
    speed: tuple[float | None, ...],
    heart_rate: tuple[int | None, ...],
) -> Samples:
    count = len(time_s)
    return Samples(
        time_s=time_s,
        power_w=power,
        speed_mps=speed,
        heart_rate_bpm=heart_rate,
        cadence_rpm=(None,) * count,
        distance_m=(None,) * count,
        altitude_m=(None,) * count,
        latitude_deg=(None,) * count,
        longitude_deg=(None,) * count,
        temperature_c=(None,) * count,
    )


def _page(samples: Samples, *, key: str = "a" * 64) -> PageComputed:
    activity = Activity(
        schema_version="1.0",
        provenance=Provenance(sha256=key, source_path=None, decode_errors=()),
        sport=Sport.WORKOUT,
        modality=Modality.OTHER,
        is_indoor=False,
        start_time=None,
        summary=SessionSummary(
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
        ),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )
    provenance = ChannelProvenance(
        base=SourceContribution(
            sha256=key,
            kind=SourceKind.UNKNOWN,
            manufacturer=None,
            devices=(),
            channels=(),
            alignment=None,
        ),
        extras=(),
    )
    return PageComputed(
        document=PageDocument(
            page_key=key,
            path="workouts/synthetic.md",
            text="synthetic",
            frontmatter={},
            sources=(),
            load=LoadRegionReading("not_computed", None),
        ),
        activity=activity,
        metrics=DerivedMetrics(),
        provenance=provenance,
        athlete=None,
        athlete_fingerprint="",
    )


def _expected_rows(samples: Samples) -> tuple[tuple[object, ...], ...]:
    power = mean_max_curve(samples, MeanMaxChannel.POWER)
    speed = mean_max_curve(samples, MeanMaxChannel.SPEED)
    heart_rate = mean_max_curve(samples, MeanMaxChannel.HEART_RATE)
    result: list[tuple[object, ...]] = []
    for power_point, speed_point, heart_rate_point in zip(
        power, speed, heart_rate, strict=True
    ):
        if not any(
            point.value is not None
            for point in (power_point, speed_point, heart_rate_point)
        ):
            continue
        result.append(
            (
                power_point.duration_s,
                power_point.value,
                power_point.start_s,
                speed_point.value,
                speed_point.start_s,
                heart_rate_point.value,
                heart_rate_point.start_s,
            )
        )
    return tuple(result)


def _distinct_channel_samples() -> Samples:
    time_s = tuple(float(index) for index in range(25))
    power = tuple(100 + index for index in range(25))
    speed = tuple(10.0 - index / 10 for index in range(25))
    heart_rate = tuple(200 - (index - 12) ** 2 for index in range(25))
    return _samples(time_s, power=power, speed=speed, heart_rate=heart_rate)


def test_rows_equal_curves_for_all_three_distinct_channels() -> None:
    samples = _distinct_channel_samples()
    expected = _expected_rows(samples)
    assert expected
    assert all(len({row[index] for index in (1, 3, 5)}) == 3 for row in expected), (
        "all three channels need different best values at every supported duration"
    )
    assert all(len({row[index] for index in (2, 4, 6)}) == 3 for row in expected), (
        "all three channels need distinct starts at every supported duration"
    )
    rows = MEAN_MAX_PRODUCER.rows(_page(samples))["mean_max"]
    assert tuple(rows) == expected
    assert tuple(row[0] for row in rows) == tuple(row[0] for row in expected)


def test_hr_only_nulls_other_channels_and_omits_unsupported_durations() -> None:
    times = tuple(float(index) for index in range(8)) + tuple(
        float(index) for index in range(20, 28)
    )
    heart_rate = tuple(range(100, 108)) + tuple(range(108, 100, -1))
    samples = _samples(
        times,
        power=(None,) * len(times),
        speed=(None,) * len(times),
        heart_rate=heart_rate,
    )
    expected = _expected_rows(samples)
    assert tuple(row[0] for row in expected) == (1, 5)
    assert all(row[1] is None and row[2] is None for row in expected)
    assert all(row[3] is None and row[4] is None for row in expected)
    assert all(row[5] is not None and row[6] is not None for row in expected)
    assert MEAN_MAX_PRODUCER.rows(_page(samples))["mean_max"] == expected


def test_no_row_when_every_channel_is_absent() -> None:
    times = tuple(float(index) for index in range(8))
    samples = _samples(
        times,
        power=(None,) * len(times),
        speed=(None,) * len(times),
        heart_rate=(None,) * len(times),
    )
    assert _expected_rows(samples) == ()
    assert MEAN_MAX_PRODUCER.rows(_page(samples)) == {"mean_max": ()}


def test_recorded_zero_values_still_support_rows() -> None:
    times = tuple(float(index) for index in range(8))
    samples = _samples(
        times,
        power=(0,) * len(times),
        speed=(None,) * len(times),
        heart_rate=(None,) * len(times),
    )
    expected = _expected_rows(samples)
    assert tuple(row[0] for row in expected) == (1, 5)
    assert all(row[1] == 0.0 and row[2] == 0.0 for row in expected)
    assert MEAN_MAX_PRODUCER.rows(_page(samples))["mean_max"] == expected


def test_producer_contract_and_resolved_table_schema() -> None:
    assert MEAN_MAX_PRODUCER.name == "derived.mean_max"
    assert MEAN_MAX_TABLE.name == "mean_max"
    assert MEAN_MAX_PRODUCER is not MeanMaxProducer()
    assert MEAN_MAX_PRODUCER.tables == (MEAN_MAX_TABLE,)
    with pytest.raises(FrozenInstanceError):
        MEAN_MAX_PRODUCER.name = "changed"  # type: ignore[misc]

    expected_columns = (
        ("duration_s", ColumnType.INTEGER),
        ("power_w", ColumnType.DOUBLE),
        ("power_start_s", ColumnType.DOUBLE),
        ("speed_mps", ColumnType.DOUBLE),
        ("speed_start_s", ColumnType.DOUBLE),
        ("heart_rate_bpm", ColumnType.DOUBLE),
        ("heart_rate_start_s", ColumnType.DOUBLE),
    )
    declared = tuple((column.name, column.type) for column in MEAN_MAX_TABLE.columns)
    assert declared == expected_columns
    expected_descriptions = (
        "Window length in seconds.",
        "Best average power in watts; NULL when no window of this duration is allowed.",
        "Seconds since the activity's start (records.elapsed_s scale) at "
        "which the best power window begins; NULL with power_w.",
        "Best average speed in metres per second; NULL when no window "
        "of this duration is allowed.",
        "Seconds since the activity's start (records.elapsed_s scale) at "
        "which the best speed window begins; NULL with speed_mps.",
        "Best average heart rate in beats per minute; NULL when no window "
        "of this duration is allowed.",
        "Seconds since the activity's start (records.elapsed_s scale) at "
        "which the best heart-rate window begins; NULL with heart_rate_bpm.",
    )
    assert (
        tuple(column.description for column in MEAN_MAX_TABLE.columns)
        == expected_descriptions
    )
    assert MEAN_MAX_TABLE.description == (
        "One row per duration of the best-effort set that at least one of power, "
        "speed and heart rate supports on this page's composed activity. A best "
        "effort is the highest average over a window of continuous recording; a "
        "window never spans a step longer than the maximum step between recorded "
        "values (see the records in fitdocs.metrics.mean_max_sources). Follows "
        "the page's rendering, like activities."
    )

    (resolved,) = resolve_tables((), (MEAN_MAX_PRODUCER,), (), ())
    assert resolved.scope is TableScope.COMPUTED
    assert tuple(column.name for column in resolved.columns) == (
        "page_key",
        *(name for name, _ in expected_columns),
    )
    assert resolved.columns[0].name == "page_key"
    assert all(column.name != "page_key" for column in MEAN_MAX_TABLE.columns)
