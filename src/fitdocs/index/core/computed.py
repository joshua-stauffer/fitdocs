"""Computed-tier index rows projected from a composed activity."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from typing import Final, cast

from fitdocs.index.producer import ComputedProducer, PageComputed, Row, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Samples

_ZONE_METRIC_FIELDS: Final[frozenset[str]] = frozenset(
    {"hr_time_in_zone_s", "power_time_in_zone_s", "pace_time_in_zone_s"}
)

_METRIC_DESCRIPTIONS: Final[dict[str, str]] = {
    "moving_time_s": "Moving time in seconds.",
    "elapsed_time_s": "Elapsed time in seconds.",
    "distance_m": "Distance in metres.",
    "avg_speed_mps": "Average speed in metres per second.",
    "max_speed_mps": "Maximum speed in metres per second.",
    "avg_pace_s_per_km": "Average pace in seconds per kilometre.",
    "avg_heart_rate_bpm": "Average heart rate in beats per minute.",
    "max_heart_rate_bpm": "Maximum heart rate in beats per minute.",
    "avg_power_w": "Average power in watts.",
    "max_power_w": "Maximum power in watts.",
    "avg_cadence_rpm": "Average cadence in revolutions per minute.",
    "max_cadence_rpm": "Maximum cadence in revolutions per minute.",
    "normalized_power_w": "Normalized power in watts.",
    "intensity_factor": "Intensity factor.",
    "variability_index": "Variability index.",
    "efficiency_factor": "Efficiency factor.",
    "decoupling_pct": "Decoupling in percent.",
    "elevation_gain_m": "Elevation gain in metres.",
    "elevation_loss_m": "Elevation loss in metres.",
    "min_altitude_m": "Minimum altitude in metres.",
    "max_altitude_m": "Maximum altitude in metres.",
    "min_temperature_c": "Minimum temperature in degrees Celsius.",
    "max_temperature_c": "Maximum temperature in degrees Celsius.",
    "avg_temperature_c": "Average temperature in degrees Celsius.",
    "trimp": "Training impulse.",
    "trimp_weighting": "Training impulse weighting selection.",
    "power_tss": "Power-based training stress score.",
    "calories_kcal": "Calories in kilocalories.",
}

_METRIC_FIELDS: Final[tuple[str, ...]] = tuple(
    field.name
    for field in fields(DerivedMetrics)
    if field.name not in _ZONE_METRIC_FIELDS
)
_METRIC_COLUMNS: Final[tuple[ColumnSpec, ...]] = tuple(
    ColumnSpec(
        name,
        ColumnType.VARCHAR
        if name == "trimp_weighting"
        else ColumnType.INTEGER
        if name == "calories_kcal"
        else ColumnType.DOUBLE,
        _METRIC_DESCRIPTIONS[name],
    )
    for name in _METRIC_FIELDS
)

_SAMPLE_DESCRIPTIONS: Final[dict[str, str]] = {
    "heart_rate_bpm": "Heart rate in beats per minute.",
    "power_w": "Power in watts.",
    "cadence_rpm": "Cadence in revolutions per minute.",
    "speed_mps": "Speed in metres per second.",
    "distance_m": "Distance in metres.",
    "altitude_m": "Altitude in metres.",
    "latitude_deg": "Latitude in degrees.",
    "longitude_deg": "Longitude in degrees.",
    "temperature_c": "Temperature in degrees Celsius.",
    "stance_time_ms": "Stance time in milliseconds.",
    "stance_time_balance_pct": "Stance time balance in percent.",
    "vertical_oscillation_mm": "Vertical oscillation in millimetres.",
    "vertical_oscillation_balance_pct": "Vertical oscillation balance in percent.",
    "vertical_ratio_pct": "Vertical ratio in percent.",
    "step_length_mm": "Step length in millimetres.",
    "leg_spring_stiffness_kn_m": "Leg spring stiffness in kilonewtons per metre.",
    "leg_spring_stiffness_balance_pct": "Leg spring stiffness balance in percent.",
    "form_power_w": "Form power in watts.",
    "air_power_w": "Air power in watts.",
    "impact_bw": "Impact in body weights.",
    "impact_loading_rate_balance_pct": "Impact loading rate balance in percent.",
}
_SAMPLE_FIELDS: Final[tuple[str, ...]] = tuple(
    field.name for field in fields(Samples) if field.name != "time_s"
)
_SAMPLE_COLUMNS: Final[tuple[ColumnSpec, ...]] = tuple(
    ColumnSpec(
        name,
        ColumnType.INTEGER
        if name in {"heart_rate_bpm", "power_w"}
        else ColumnType.DOUBLE,
        _SAMPLE_DESCRIPTIONS[name],
    )
    for name in _SAMPLE_FIELDS
)

ACTIVITIES: Final[TableSpec] = TableSpec(
    "activities",
    "one row per page whose files compose.",
    (
        ColumnSpec("start_utc", ColumnType.TIMESTAMP, "Activity start instant in UTC."),
        ColumnSpec("sport", ColumnType.VARCHAR, "as fitdocs determines it"),
        ColumnSpec("sub_sport", ColumnType.VARCHAR, "raw FIT value"),
        ColumnSpec(
            "modality", ColumnType.VARCHAR, "Modality as fitdocs determines it."
        ),
        ColumnSpec(
            "indoor", ColumnType.BOOLEAN, "Indoor flag as fitdocs determines it."
        ),
        ColumnSpec("sample_count", ColumnType.INTEGER, "Number of activity samples."),
        *_METRIC_COLUMNS,
        ColumnSpec(
            "athlete_fingerprint",
            ColumnType.VARCHAR,
            "SHA-256 of the athlete inputs the metrics were computed under",
        ),
    ),
)
RECORDS: Final[TableSpec] = TableSpec(
    "records",
    "one row per sample of the composed activity.",
    (
        ColumnSpec(
            "sample_index",
            ColumnType.INTEGER,
            "0-based recorded order",
        ),
        ColumnSpec("time_utc", ColumnType.TIMESTAMP, "Sample instant in UTC."),
        ColumnSpec(
            "elapsed_s",
            ColumnType.DOUBLE,
            "seconds since the activity's start; may be negative",
        ),
        *_SAMPLE_COLUMNS,
    ),
)
LAPS: Final[TableSpec] = TableSpec(
    "laps",
    "one row per base lap, in recorded order.",
    (
        ColumnSpec(
            "lap_index",
            ColumnType.INTEGER,
            "Zero-based lap position in recorded order.",
        ),
        ColumnSpec(
            "start_utc",
            ColumnType.TIMESTAMP,
            "Lap start instant in UTC; NULL when absent.",
        ),
        ColumnSpec(
            "total_elapsed_time_s", ColumnType.DOUBLE, "Lap elapsed time in seconds."
        ),
        ColumnSpec(
            "total_timer_time_s", ColumnType.DOUBLE, "Lap timer time in seconds."
        ),
        ColumnSpec("total_distance_m", ColumnType.DOUBLE, "Lap distance in metres."),
        ColumnSpec(
            "avg_heart_rate_bpm",
            ColumnType.INTEGER,
            "Average heart rate in beats per minute.",
        ),
        ColumnSpec(
            "max_heart_rate_bpm",
            ColumnType.INTEGER,
            "Maximum heart rate in beats per minute.",
        ),
        ColumnSpec("avg_power_w", ColumnType.INTEGER, "Average power in watts."),
        ColumnSpec("max_power_w", ColumnType.INTEGER, "Maximum power in watts."),
        ColumnSpec(
            "avg_cadence_rpm",
            ColumnType.DOUBLE,
            "Average cadence in revolutions per minute.",
        ),
        ColumnSpec(
            "avg_speed_mps", ColumnType.DOUBLE, "Average speed in metres per second."
        ),
        ColumnSpec(
            "max_speed_mps", ColumnType.DOUBLE, "Maximum speed in metres per second."
        ),
        ColumnSpec("total_ascent_m", ColumnType.DOUBLE, "Total ascent in metres."),
        ColumnSpec("total_descent_m", ColumnType.DOUBLE, "Total descent in metres."),
        ColumnSpec(
            "start_sample",
            ColumnType.INTEGER,
            "inclusive record indices; NULL when unmatched",
        ),
        ColumnSpec(
            "end_sample",
            ColumnType.INTEGER,
            "inclusive record indices; NULL when unmatched",
        ),
    ),
)
STRENGTH_SETS: Final[TableSpec] = TableSpec(
    "strength_sets",
    "one row per base set, in recorded order.",
    (
        ColumnSpec(
            "set_index",
            ColumnType.INTEGER,
            "Zero-based set position in recorded order.",
        ),
        ColumnSpec("set_type", ColumnType.VARCHAR, "Recorded set type."),
        ColumnSpec(
            "start_utc",
            ColumnType.TIMESTAMP,
            "Set start instant in UTC; NULL when absent.",
        ),
        ColumnSpec("duration_s", ColumnType.DOUBLE, "Set duration in seconds."),
        ColumnSpec("repetitions", ColumnType.INTEGER, "Recorded repetition count."),
        ColumnSpec(
            "weight_kg",
            ColumnType.DOUBLE,
            "0 means bodyweight, a real zero in kilograms",
        ),
        ColumnSpec("category", ColumnType.VARCHAR, "Recorded exercise category."),
        ColumnSpec("exercise_name", ColumnType.VARCHAR, "Resolved exercise name."),
    ),
)
ZONE_TIMES: Final[TableSpec] = TableSpec(
    "zone_times",
    "one row per channel and zone with computed times.",
    (
        ColumnSpec("channel", ColumnType.VARCHAR, "heart_rate, power or pace"),
        ColumnSpec(
            "zone",
            ColumnType.INTEGER,
            "1-based; zone 1 is below the first divider",
        ),
        ColumnSpec(
            "lower_bound",
            ColumnType.DOUBLE,
            "in bound_unit; NULL for an open end",
        ),
        ColumnSpec(
            "upper_bound",
            ColumnType.DOUBLE,
            "in bound_unit; NULL for an open end",
        ),
        ColumnSpec(
            "bound_unit",
            ColumnType.VARCHAR,
            "bpm, w or s_per_km",
        ),
        ColumnSpec(
            "time_s", ColumnType.DOUBLE, "Time credited to the zone in seconds."
        ),
    ),
)
CHANNEL_SOURCES: Final[TableSpec] = TableSpec(
    "channel_sources",
    "one row per channel per supplying file.",
    (
        ColumnSpec("channel", ColumnType.VARCHAR, "activity-model channel name"),
        ColumnSpec(
            "source_sha256", ColumnType.VARCHAR, "SHA-256 digest of the supplying file."
        ),
        ColumnSpec("role", ColumnType.VARCHAR, "base or extra"),
    ),
)

_TABLES: Final[tuple[TableSpec, ...]] = (
    ACTIVITIES,
    RECORDS,
    LAPS,
    STRENGTH_SETS,
    ZONE_TIMES,
    CHANNEL_SOURCES,
)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(tzinfo=None)


def _sample_instant(start_time: datetime | None, elapsed_s: float) -> datetime | None:
    start_utc = _utc_naive(start_time)
    if start_utc is None:
        return None
    return start_utc + timedelta(seconds=elapsed_s)


def _metric_value(page: PageComputed, name: str) -> str | int | float | None:
    value = getattr(page.metrics, name)
    if name == "trimp_weighting" and value is not None:
        return cast(str, value.value)
    return cast(str | int | float | None, value)


def _zone_rows(page: PageComputed) -> tuple[Row, ...]:
    if page.athlete is None:
        return ()
    specs = (
        ("heart_rate", "hr_time_in_zone_s", page.athlete.hr_zones, "bpm"),
        ("power", "power_time_in_zone_s", page.athlete.power_zones, "w"),
        ("pace", "pace_time_in_zone_s", page.athlete.pace_zones, "s_per_km"),
    )
    rows: list[Row] = []
    for channel, metric_name, zone_spec, unit in specs:
        times = getattr(page.metrics, metric_name)
        if times is None or zone_spec is None:
            continue
        for index, time_s in enumerate(times):
            rows.append(
                (
                    channel,
                    index + 1,
                    zone_spec.dividers[index - 1] if index > 0 else None,
                    zone_spec.dividers[index]
                    if index < len(zone_spec.dividers)
                    else None,
                    unit,
                    time_s,
                )
            )
    return tuple(rows)


class _CoreComputed:
    name = "core.computed"
    tables = _TABLES

    def rows(self, page: PageComputed) -> Rows:
        activity = page.activity
        samples = activity.samples
        activity_row: Row = (
            _utc_naive(activity.start_time),
            activity.sport.value,
            activity.summary.sub_sport,
            activity.modality.value,
            activity.is_indoor,
            len(samples.time_s),
            *(_metric_value(page, name) for name in _METRIC_FIELDS),
            page.athlete_fingerprint,
        )
        record_rows = tuple(
            (
                index,
                _sample_instant(activity.start_time, elapsed_s),
                elapsed_s,
                *(getattr(samples, name)[index] for name in _SAMPLE_FIELDS),
            )
            for index, elapsed_s in enumerate(samples.time_s)
        )
        lap_rows = tuple(
            (
                index,
                _utc_naive(lap.start_time),
                lap.total_elapsed_time_s,
                lap.total_timer_time_s,
                lap.total_distance_m,
                lap.avg_heart_rate_bpm,
                lap.max_heart_rate_bpm,
                lap.avg_power_w,
                lap.max_power_w,
                lap.avg_cadence_rpm,
                lap.avg_speed_mps,
                lap.max_speed_mps,
                lap.total_ascent_m,
                lap.total_descent_m,
                lap.start_index,
                lap.end_index,
            )
            for index, lap in enumerate(activity.laps)
        )
        set_rows = tuple(
            (
                index,
                item.set_type,
                _utc_naive(item.start_time),
                item.duration_s,
                item.repetitions,
                item.weight_kg,
                item.category,
                item.exercise_name,
            )
            for index, item in enumerate(activity.sets)
        )
        source_rows = tuple(
            (channel, page.provenance.base.sha256, "base")
            for channel in page.provenance.base.channels
        ) + tuple(
            (channel, extra.sha256, "extra")
            for extra in page.provenance.extras
            for channel in extra.channels
        )
        return {
            "activities": (activity_row,),
            "records": record_rows,
            "laps": lap_rows,
            "strength_sets": set_rows,
            "zone_times": _zone_rows(page),
            "channel_sources": source_rows,
        }


CORE_COMPUTED: Final[ComputedProducer] = _CoreComputed()
