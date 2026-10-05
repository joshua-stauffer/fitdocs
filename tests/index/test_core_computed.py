from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest

import fitdocs.metrics as metrics_api
from fitdocs.compose.composer import compose_activity
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.producer import LoadRegionReading, PageComputed, PageDocument
from fitdocs.index.schema import (
    ColumnSpec,
    ColumnType,
    TableScope,
    TableSpec,
    resolve_tables,
)
from fitdocs.ingest import parse_fit
from fitdocs.metrics import compute_metrics
from fitdocs.metrics.types import (
    AthleteInputs,
    DerivedMetrics,
    TrimpWeighting,
    ZoneSpec,
)
from fitdocs.model import Activity, Modality, Sport
from tests.fixtures import builder, merge


def _column(name: str, kind: ColumnType, description: str) -> ColumnSpec:
    return ColumnSpec(name, kind, description)


_METRIC_COLUMNS = (
    ("moving_time_s", ColumnType.DOUBLE, "Moving time in seconds."),
    ("elapsed_time_s", ColumnType.DOUBLE, "Elapsed time in seconds."),
    ("distance_m", ColumnType.DOUBLE, "Distance in metres."),
    ("avg_speed_mps", ColumnType.DOUBLE, "Average speed in metres per second."),
    ("max_speed_mps", ColumnType.DOUBLE, "Maximum speed in metres per second."),
    (
        "avg_pace_s_per_km",
        ColumnType.DOUBLE,
        "Average pace in seconds per kilometre.",
    ),
    (
        "avg_heart_rate_bpm",
        ColumnType.DOUBLE,
        "Average heart rate in beats per minute.",
    ),
    (
        "max_heart_rate_bpm",
        ColumnType.DOUBLE,
        "Maximum heart rate in beats per minute.",
    ),
    ("avg_power_w", ColumnType.DOUBLE, "Average power in watts."),
    ("max_power_w", ColumnType.DOUBLE, "Maximum power in watts."),
    (
        "avg_cadence_rpm",
        ColumnType.DOUBLE,
        "Average cadence in revolutions per minute.",
    ),
    (
        "max_cadence_rpm",
        ColumnType.DOUBLE,
        "Maximum cadence in revolutions per minute.",
    ),
    ("normalized_power_w", ColumnType.DOUBLE, "Normalized power in watts."),
    ("intensity_factor", ColumnType.DOUBLE, "Intensity factor."),
    ("variability_index", ColumnType.DOUBLE, "Variability index."),
    ("efficiency_factor", ColumnType.DOUBLE, "Efficiency factor."),
    ("decoupling_pct", ColumnType.DOUBLE, "Decoupling in percent."),
    ("elevation_gain_m", ColumnType.DOUBLE, "Elevation gain in metres."),
    ("elevation_loss_m", ColumnType.DOUBLE, "Elevation loss in metres."),
    ("min_altitude_m", ColumnType.DOUBLE, "Minimum altitude in metres."),
    ("max_altitude_m", ColumnType.DOUBLE, "Maximum altitude in metres."),
    ("min_temperature_c", ColumnType.DOUBLE, "Minimum temperature in degrees Celsius."),
    ("max_temperature_c", ColumnType.DOUBLE, "Maximum temperature in degrees Celsius."),
    ("avg_temperature_c", ColumnType.DOUBLE, "Average temperature in degrees Celsius."),
    ("trimp", ColumnType.DOUBLE, "Training impulse."),
    ("trimp_weighting", ColumnType.VARCHAR, "Training impulse weighting selection."),
    ("power_tss", ColumnType.DOUBLE, "Power-based training stress score."),
    ("calories_kcal", ColumnType.INTEGER, "Calories in kilocalories."),
)
METRIC_FIELD_NAMES = tuple(name for name, _kind, _description in _METRIC_COLUMNS)

SAMPLE_FIELD_NAMES = (
    "heart_rate_bpm",
    "power_w",
    "cadence_rpm",
    "speed_mps",
    "distance_m",
    "altitude_m",
    "latitude_deg",
    "longitude_deg",
    "temperature_c",
    "stance_time_ms",
    "stance_time_balance_pct",
    "vertical_oscillation_mm",
    "vertical_oscillation_balance_pct",
    "vertical_ratio_pct",
    "step_length_mm",
    "leg_spring_stiffness_kn_m",
    "leg_spring_stiffness_balance_pct",
    "form_power_w",
    "air_power_w",
    "impact_bw",
    "impact_loading_rate_balance_pct",
)


EXPECTED_TABLES = (
    TableSpec(
        "activities",
        "one row per page whose files compose.",
        (
            _column(
                "start_utc", ColumnType.TIMESTAMP, "Activity start instant in UTC."
            ),
            _column("sport", ColumnType.VARCHAR, "as fitdocs determines it"),
            _column("sub_sport", ColumnType.VARCHAR, "raw FIT value"),
            _column(
                "modality", ColumnType.VARCHAR, "Modality as fitdocs determines it."
            ),
            _column(
                "indoor", ColumnType.BOOLEAN, "Indoor flag as fitdocs determines it."
            ),
            _column("sample_count", ColumnType.INTEGER, "Number of activity samples."),
            *(
                _column(name, kind, description)
                for name, kind, description in _METRIC_COLUMNS
            ),
            _column(
                "athlete_fingerprint",
                ColumnType.VARCHAR,
                "SHA-256 of the athlete inputs the metrics were computed under",
            ),
        ),
    ),
    TableSpec(
        "records",
        "one row per sample of the composed activity.",
        (
            _column(
                "sample_index",
                ColumnType.INTEGER,
                "0-based recorded order",
            ),
            _column("time_utc", ColumnType.TIMESTAMP, "Sample instant in UTC."),
            _column(
                "elapsed_s",
                ColumnType.DOUBLE,
                "seconds since the activity's start; may be negative",
            ),
            _column(
                "heart_rate_bpm", ColumnType.INTEGER, "Heart rate in beats per minute."
            ),
            _column("power_w", ColumnType.INTEGER, "Power in watts."),
            _column(
                "cadence_rpm", ColumnType.DOUBLE, "Cadence in revolutions per minute."
            ),
            _column("speed_mps", ColumnType.DOUBLE, "Speed in metres per second."),
            _column("distance_m", ColumnType.DOUBLE, "Distance in metres."),
            _column("altitude_m", ColumnType.DOUBLE, "Altitude in metres."),
            _column("latitude_deg", ColumnType.DOUBLE, "Latitude in degrees."),
            _column("longitude_deg", ColumnType.DOUBLE, "Longitude in degrees."),
            _column(
                "temperature_c", ColumnType.DOUBLE, "Temperature in degrees Celsius."
            ),
            _column(
                "stance_time_ms", ColumnType.DOUBLE, "Stance time in milliseconds."
            ),
            _column(
                "stance_time_balance_pct",
                ColumnType.DOUBLE,
                "Stance time balance in percent.",
            ),
            _column(
                "vertical_oscillation_mm",
                ColumnType.DOUBLE,
                "Vertical oscillation in millimetres.",
            ),
            _column(
                "vertical_oscillation_balance_pct",
                ColumnType.DOUBLE,
                "Vertical oscillation balance in percent.",
            ),
            _column(
                "vertical_ratio_pct", ColumnType.DOUBLE, "Vertical ratio in percent."
            ),
            _column("step_length_mm", ColumnType.DOUBLE, "Step length in millimetres."),
            _column(
                "leg_spring_stiffness_kn_m",
                ColumnType.DOUBLE,
                "Leg spring stiffness in kilonewtons per metre.",
            ),
            _column(
                "leg_spring_stiffness_balance_pct",
                ColumnType.DOUBLE,
                "Leg spring stiffness balance in percent.",
            ),
            _column("form_power_w", ColumnType.DOUBLE, "Form power in watts."),
            _column("air_power_w", ColumnType.DOUBLE, "Air power in watts."),
            _column("impact_bw", ColumnType.DOUBLE, "Impact in body weights."),
            _column(
                "impact_loading_rate_balance_pct",
                ColumnType.DOUBLE,
                "Impact loading rate balance in percent.",
            ),
        ),
    ),
    TableSpec(
        "laps",
        "one row per base lap, in recorded order.",
        (
            _column(
                "lap_index",
                ColumnType.INTEGER,
                "Zero-based lap position in recorded order.",
            ),
            _column(
                "start_utc",
                ColumnType.TIMESTAMP,
                "Lap start instant in UTC; NULL when absent.",
            ),
            _column(
                "total_elapsed_time_s",
                ColumnType.DOUBLE,
                "Lap elapsed time in seconds.",
            ),
            _column(
                "total_timer_time_s", ColumnType.DOUBLE, "Lap timer time in seconds."
            ),
            _column("total_distance_m", ColumnType.DOUBLE, "Lap distance in metres."),
            _column(
                "avg_heart_rate_bpm",
                ColumnType.INTEGER,
                "Average heart rate in beats per minute.",
            ),
            _column(
                "max_heart_rate_bpm",
                ColumnType.INTEGER,
                "Maximum heart rate in beats per minute.",
            ),
            _column("avg_power_w", ColumnType.INTEGER, "Average power in watts."),
            _column("max_power_w", ColumnType.INTEGER, "Maximum power in watts."),
            _column(
                "avg_cadence_rpm",
                ColumnType.DOUBLE,
                "Average cadence in revolutions per minute.",
            ),
            _column(
                "avg_speed_mps",
                ColumnType.DOUBLE,
                "Average speed in metres per second.",
            ),
            _column(
                "max_speed_mps",
                ColumnType.DOUBLE,
                "Maximum speed in metres per second.",
            ),
            _column("total_ascent_m", ColumnType.DOUBLE, "Total ascent in metres."),
            _column("total_descent_m", ColumnType.DOUBLE, "Total descent in metres."),
            _column(
                "start_sample",
                ColumnType.INTEGER,
                "inclusive record indices; NULL when unmatched",
            ),
            _column(
                "end_sample",
                ColumnType.INTEGER,
                "inclusive record indices; NULL when unmatched",
            ),
        ),
    ),
    TableSpec(
        "strength_sets",
        "one row per base set, in recorded order.",
        (
            _column(
                "set_index",
                ColumnType.INTEGER,
                "Zero-based set position in recorded order.",
            ),
            _column("set_type", ColumnType.VARCHAR, "Recorded set type."),
            _column(
                "start_utc",
                ColumnType.TIMESTAMP,
                "Set start instant in UTC; NULL when absent.",
            ),
            _column("duration_s", ColumnType.DOUBLE, "Set duration in seconds."),
            _column("repetitions", ColumnType.INTEGER, "Recorded repetition count."),
            _column(
                "weight_kg",
                ColumnType.DOUBLE,
                "0 means bodyweight, a real zero in kilograms",
            ),
            _column("category", ColumnType.VARCHAR, "Recorded exercise category."),
            _column("exercise_name", ColumnType.VARCHAR, "Resolved exercise name."),
        ),
    ),
    TableSpec(
        "zone_times",
        "one row per channel and zone with computed times.",
        (
            _column("channel", ColumnType.VARCHAR, "heart_rate, power or pace"),
            _column(
                "zone",
                ColumnType.INTEGER,
                "1-based; zone 1 is below the first divider",
            ),
            _column(
                "lower_bound",
                ColumnType.DOUBLE,
                "in bound_unit; NULL for an open end",
            ),
            _column(
                "upper_bound",
                ColumnType.DOUBLE,
                "in bound_unit; NULL for an open end",
            ),
            _column(
                "bound_unit",
                ColumnType.VARCHAR,
                "bpm, w or s_per_km",
            ),
            _column(
                "time_s", ColumnType.DOUBLE, "Time credited to the zone in seconds."
            ),
        ),
    ),
    TableSpec(
        "channel_sources",
        "one row per channel per supplying file.",
        (
            _column("channel", ColumnType.VARCHAR, "activity-model channel name"),
            _column(
                "source_sha256",
                ColumnType.VARCHAR,
                "SHA-256 digest of the supplying file.",
            ),
            _column("role", ColumnType.VARCHAR, "base or extra"),
        ),
    ),
)


_START_WITH_OFFSET = datetime(
    2042, 6, 1, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
)
_START_UTC = datetime(2042, 6, 1, 0, 0)
_HR_DIVIDERS = (111.0, 139.0, 177.0)
_POWER_DIVIDERS = (121.5, 201.25, 260.75)
_PACE_DIVIDERS = (245.0, 333.0, 499.0)


def _athlete() -> AthleteInputs:
    return AthleteInputs(
        ftp_watts=237.5,
        resting_hr_bpm=53,
        max_hr_bpm=194,
        hr_zones=ZoneSpec(_HR_DIVIDERS),
        power_zones=ZoneSpec(_POWER_DIVIDERS),
        pace_zones=ZoneSpec(_PACE_DIVIDERS),
    )


def _supplied_metrics(
    page: PageComputed,
    *,
    weighting: TrimpWeighting | None = TrimpWeighting.BANISTER_FEMALE,
    calories: int = 704,
    max_heart_rate: float = 0.0,
) -> tuple[DerivedMetrics, tuple[object, ...]]:
    values: dict[str, str | int | float | None | TrimpWeighting] = {}
    for field_index, name in enumerate(METRIC_FIELD_NAMES):
        if name == "trimp_weighting":
            values[name] = weighting
        elif name == "calories_kcal":
            values[name] = calories
        elif name == "avg_heart_rate_bpm":
            values[name] = None
        elif name == "max_heart_rate_bpm":
            values[name] = max_heart_rate
        else:
            values[name] = 1.25 + 13.5 * field_index
    supplied = replace(page.metrics, **cast(Any, values))
    expected = tuple(
        value.value if isinstance(value, TrimpWeighting) else value
        for value in (values[name] for name in METRIC_FIELD_NAMES)
    )
    return supplied, expected


def _document() -> PageDocument:
    return PageDocument(
        page_key="p" * 64,
        path="workouts/synthetic-computed.md",
        text="synthetic fixture",
        frontmatter={},
        sources=(),
        load=LoadRegionReading("not_computed", None),
    )


def _page_computed(
    activity: Activity,
    provenance: Any,
    athlete: AthleteInputs | None,
) -> PageComputed:
    return PageComputed(
        document=_document(),
        activity=activity,
        metrics=compute_metrics(activity, athlete),
        provenance=provenance,
        athlete=athlete,
        athlete_fingerprint=athlete_fingerprint(athlete),
    )


def _run_case(*, athlete: AthleteInputs | None = None) -> tuple[PageComputed, Activity]:
    base_bytes, donor_bytes = merge.run_pair_fit_bytes()
    base = parse_fit(base_bytes)
    donor = parse_fit(donor_bytes)
    composition = compose_activity(base, [donor])
    activity = composition.activity
    time_s = (-1.25, 0.375) + tuple(
        1.625 + 0.75 * i for i in range(len(activity.samples.time_s) - 2)
    )
    samples = replace(activity.samples, time_s=time_s)
    channel_values: dict[str, tuple[int | float | None, ...]] = {}
    for channel_index, name in enumerate(SAMPLE_FIELD_NAMES):
        if name == "form_power_w":
            continue
        values: tuple[int | float | None, ...] = tuple(
            channel_index * 100 + sample_index + 1
            for sample_index in range(len(time_s))
        )
        if name == "heart_rate_bpm" or name == "power_w":
            channel_values[name] = tuple(
                int(value) for value in values if value is not None
            )
        else:
            channel_values[name] = values
    channel_values["altitude_m"] = (*channel_values["altitude_m"][:-1], None)
    samples = replace(samples, **cast(Any, channel_values))
    laps = (
        replace(activity.laps[0], start_time=_START_WITH_OFFSET),
        replace(activity.laps[1], start_index=None, end_index=None),
        *activity.laps[2:],
    )
    activity = replace(
        activity,
        start_time=_START_WITH_OFFSET,
        samples=samples,
        laps=laps,
    )
    return _page_computed(activity, composition.provenance, athlete), base


def _producer() -> Any:
    from fitdocs.index.core.computed import CORE_COMPUTED

    return CORE_COMPUTED


def test_tables_pin_full_ordered_schema_and_injected_page_key() -> None:
    producer = _producer()
    assert producer.name == "core.computed"
    assert producer.tables == EXPECTED_TABLES
    resolved = resolve_tables((), (producer,), (), ())
    assert tuple(table.name for table in resolved) == (
        "activities",
        "records",
        "laps",
        "strength_sets",
        "zone_times",
        "channel_sources",
    )
    assert all(table.scope is TableScope.COMPUTED for table in resolved)
    for spec, table in zip(EXPECTED_TABLES, resolved, strict=True):
        assert table.producer == "core.computed"
        assert table.columns[0].name == "page_key"
        assert tuple(table.columns[1:]) == spec.columns


def test_computed_activity_and_records_match_composed_activity_and_metrics() -> None:
    page, base = _run_case(athlete=_athlete())
    rows = _producer().rows(page)
    samples = page.activity.samples
    assert page.activity.samples.form_power_w != base.samples.form_power_w
    assert any(value is not None for value in page.activity.samples.form_power_w)
    assert "form_power_w" not in page.provenance.base.channels
    assert any("form_power_w" in item.channels for item in page.provenance.extras)
    assert samples.time_s[:2] == (-1.25, 0.375)
    assert page.metrics == compute_metrics(page.activity, page.athlete)
    assert page.athlete_fingerprint == athlete_fingerprint(page.athlete)
    assert page.athlete_fingerprint != ""

    metric_values = tuple(
        getattr(page.metrics, name).value
        if name == "trimp_weighting" and getattr(page.metrics, name) is not None
        else getattr(page.metrics, name)
        for name in METRIC_FIELD_NAMES
    )
    assert rows["activities"] == (
        (
            _START_UTC,
            page.activity.sport.value,
            page.activity.summary.sub_sport,
            page.activity.modality.value,
            page.activity.is_indoor,
            len(samples.time_s),
            *metric_values,
            page.athlete_fingerprint,
        ),
    )
    weighting_index = 6 + METRIC_FIELD_NAMES.index("trimp_weighting")
    assert type(rows["activities"][0][weighting_index]) is str

    expected_records = tuple(
        (
            sample_index,
            _START_UTC + timedelta(seconds=elapsed_s),
            elapsed_s,
            *(getattr(samples, name)[sample_index] for name in SAMPLE_FIELD_NAMES),
        )
        for sample_index, elapsed_s in enumerate(samples.time_s)
    )
    assert rows["records"] == expected_records
    assert rows["records"][0][1:3] == (_START_UTC - timedelta(seconds=1.25), -1.25)
    assert rows["records"][1][1:3] == (_START_UTC + timedelta(seconds=0.375), 0.375)
    assert set(rows) == {spec.name for spec in EXPECTED_TABLES}
    assert all(
        len(row) == len(spec.columns)
        for spec in EXPECTED_TABLES
        for row in rows[spec.name]
    )


def test_activity_projects_supplied_metrics_and_headers_without_recomputing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original, _base = _run_case(athlete=_athlete())
    supplied_metrics, expected_metrics = _supplied_metrics(original)
    assert len({repr(value) for value in expected_metrics}) == len(expected_metrics)
    assert expected_metrics[METRIC_FIELD_NAMES.index("avg_heart_rate_bpm")] is None
    assert expected_metrics[METRIC_FIELD_NAMES.index("max_heart_rate_bpm")] == 0.0
    assert type(expected_metrics[METRIC_FIELD_NAMES.index("calories_kcal")]) is int
    assert (
        expected_metrics[METRIC_FIELD_NAMES.index("trimp_weighting")]
        == "banister_female"
    )
    assert type(expected_metrics[METRIC_FIELD_NAMES.index("calories_kcal")]) is int

    no_start_swim = replace(
        original.activity,
        sport=Sport.SWIM,
        modality=Modality.OTHER,
        is_indoor=True,
        start_time=None,
        summary=replace(original.activity.summary, sub_sport=None),
    )
    page_with_headers = replace(
        original,
        activity=no_start_swim,
        metrics=supplied_metrics,
        athlete_fingerprint="provided-fingerprint",
    )
    null_weighting_metrics, null_weighting_values = _supplied_metrics(
        original,
        weighting=None,
        calories=0,
        max_heart_rate=0.5,
    )
    run_page = replace(
        original,
        activity=replace(
            original.activity,
            sport=Sport.WALK,
            modality=Modality.BIKE,
            is_indoor=False,
            start_time=_START_WITH_OFFSET,
            summary=replace(original.activity.summary, sub_sport="trail"),
        ),
        metrics=null_weighting_metrics,
        athlete_fingerprint="",
    )

    def unexpected_recompute(*_args: object, **_kwargs: object) -> DerivedMetrics:
        raise AssertionError("computed rows must use the supplied metrics")

    monkeypatch.setattr(metrics_api, "compute_metrics", unexpected_recompute)
    swim_row = _producer().rows(page_with_headers)["activities"][0]
    run_row = _producer().rows(run_page)["activities"][0]
    expected_swim = (
        None,
        "Swim",
        None,
        "other",
        True,
        len(no_start_swim.samples.time_s),
        *expected_metrics,
        "provided-fingerprint",
    )
    expected_run = (
        _START_UTC,
        "Walk",
        "trail",
        "bike",
        False,
        len(run_page.activity.samples.time_s),
        *null_weighting_values,
        "",
    )
    assert swim_row == expected_swim
    assert run_row == expected_run
    assert null_weighting_values[METRIC_FIELD_NAMES.index("trimp_weighting")] is None
    assert null_weighting_values[METRIC_FIELD_NAMES.index("calories_kcal")] == 0
    assert type(null_weighting_values[METRIC_FIELD_NAMES.index("calories_kcal")]) is int

    all_none_metrics = DerivedMetrics()
    none_page = replace(
        original,
        metrics=all_none_metrics,
        athlete_fingerprint="",
    )
    none_row = _producer().rows(none_page)["activities"][0]
    assert none_row == (
        _START_UTC,
        original.activity.sport.value,
        original.activity.summary.sub_sport,
        original.activity.modality.value,
        original.activity.is_indoor,
        len(original.activity.samples.time_s),
        *(None for _name in METRIC_FIELD_NAMES),
        "",
    )

    zero_values: dict[str, int | float | None] = {
        name: 0
        if name == "calories_kcal"
        else None
        if name == "trimp_weighting"
        else 0.0
        for name in METRIC_FIELD_NAMES
    }
    zero_metrics = replace(DerivedMetrics(), **cast(Any, zero_values))
    zero_page = replace(
        original,
        metrics=zero_metrics,
        athlete_fingerprint="zero-fingerprint",
    )
    zero_row = _producer().rows(zero_page)["activities"][0]
    assert zero_row == (
        _START_UTC,
        original.activity.sport.value,
        original.activity.summary.sub_sport,
        original.activity.modality.value,
        original.activity.is_indoor,
        len(original.activity.samples.time_s),
        *(zero_values[name] for name in METRIC_FIELD_NAMES),
        "zero-fingerprint",
    )


def test_laps_keep_all_base_fields_order_inclusive_indices_and_utc_starts() -> None:
    page, _base = _run_case()
    controlled_lap = replace(
        page.activity.laps[0],
        total_elapsed_time_s=12.75,
        total_timer_time_s=8.25,
        total_distance_m=333.5,
        avg_heart_rate_bpm=101,
        max_heart_rate_bpm=147,
        avg_power_w=193,
        max_power_w=281,
        avg_cadence_rpm=83.5,
        avg_speed_mps=2.75,
        max_speed_mps=3.875,
        total_ascent_m=16.25,
        total_descent_m=4.5,
        start_index=1,
        end_index=3,
    )
    page = replace(
        page,
        activity=replace(page.activity, laps=(controlled_lap, *page.activity.laps[1:])),
    )
    assert (
        controlled_lap.total_elapsed_time_s,
        controlled_lap.total_timer_time_s,
        controlled_lap.total_distance_m,
        controlled_lap.avg_heart_rate_bpm,
        controlled_lap.max_heart_rate_bpm,
        controlled_lap.avg_power_w,
        controlled_lap.max_power_w,
        controlled_lap.avg_cadence_rpm,
        controlled_lap.avg_speed_mps,
        controlled_lap.max_speed_mps,
        controlled_lap.total_ascent_m,
        controlled_lap.total_descent_m,
        controlled_lap.start_index,
        controlled_lap.end_index,
    ) == (12.75, 8.25, 333.5, 101, 147, 193, 281, 83.5, 2.75, 3.875, 16.25, 4.5, 1, 3)
    rows = _producer().rows(page)
    expected = tuple(
        (
            index,
            _START_UTC
            if index == 0
            else lap.start_time.replace(tzinfo=None)
            if lap.start_time is not None
            else None,
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
        for index, lap in enumerate(page.activity.laps)
    )
    assert rows["laps"] == expected
    assert rows["laps"][0][1] == _START_UTC
    assert rows["laps"][1][-2:] == (None, None)
    assert rows["laps"][2][-2:] == (
        page.activity.laps[2].start_index,
        page.activity.laps[2].end_index,
    )


def test_strength_sets_preserve_zero_nulls_order_and_utc_starts() -> None:
    strength = parse_fit(builder.strength_fit_bytes())
    composition = compose_activity(strength, [])
    sets = (
        replace(
            strength.sets[0],
            set_type="strength_control",
            start_time=_START_WITH_OFFSET,
            duration_s=37.25,
            repetitions=7,
            weight_kg=0.0,
            category="category_control",
            exercise_name="exercise_control",
        ),
        replace(strength.sets[1], start_time=None),
        *strength.sets[2:],
    )
    activity = replace(strength, sets=sets)
    page = _page_computed(activity, composition.provenance, None)

    rows = _producer().rows(page)["strength_sets"]
    expected = tuple(
        (
            index,
            item.set_type,
            _START_UTC
            if index == 0
            else item.start_time.replace(tzinfo=None)
            if item.start_time is not None
            else None,
            item.duration_s,
            item.repetitions,
            item.weight_kg,
            item.category,
            item.exercise_name,
        )
        for index, item in enumerate(activity.sets)
    )
    assert rows == expected
    assert rows[0][2] == _START_UTC
    assert rows[1][2] is None
    assert rows[1][5] == 0.0
    assert rows[2][5] is None


def test_zone_rows_use_each_distinct_divider_set_and_open_ends() -> None:
    page, _base = _run_case(athlete=_athlete())
    distinct_times = {
        "hr_time_in_zone_s": (1.25, 2.5, 3.75, 5.0),
        "power_time_in_zone_s": (11.5, 22.25, 33.75, 44.125),
        "pace_time_in_zone_s": (101.5, 202.25, 303.75, 404.125),
    }
    page = replace(
        page,
        metrics=replace(page.metrics, **cast(Any, distinct_times)),
    )
    assert (
        len(set(value for values in distinct_times.values() for value in values)) == 12
    )
    rows = _producer().rows(page)["zone_times"]
    expected: list[tuple[object, ...]] = []
    for channel, dividers, times, unit in (
        ("heart_rate", _HR_DIVIDERS, page.metrics.hr_time_in_zone_s, "bpm"),
        ("power", _POWER_DIVIDERS, page.metrics.power_time_in_zone_s, "w"),
        ("pace", _PACE_DIVIDERS, page.metrics.pace_time_in_zone_s, "s_per_km"),
    ):
        assert times is not None
        assert len(times) == len(dividers) + 1
        for zone_index, time_s in enumerate(times, start=1):
            expected.append(
                (
                    channel,
                    zone_index,
                    dividers[zone_index - 2] if zone_index > 1 else None,
                    dividers[zone_index - 1] if zone_index <= len(dividers) else None,
                    unit,
                    time_s,
                )
            )
    assert rows == tuple(expected)
    assert rows[0][2:4] == (None, _HR_DIVIDERS[0])
    assert rows[3][2:4] == (_HR_DIVIDERS[-1], None)
    assert rows[4][4] == "w"
    assert rows[8][4] == "s_per_km"


def test_each_missing_zone_input_omits_only_its_own_channel() -> None:
    page, _base = _run_case(athlete=_athlete())
    zone_inputs = (
        (
            "heart_rate",
            "hr_time_in_zone_s",
            "hr_zones",
            _HR_DIVIDERS,
            (1.25, 2.5, 3.75, 5.0),
            "bpm",
        ),
        (
            "power",
            "power_time_in_zone_s",
            "power_zones",
            _POWER_DIVIDERS,
            (11.5, 22.25, 33.75, 44.125),
            "w",
        ),
        (
            "pace",
            "pace_time_in_zone_s",
            "pace_zones",
            _PACE_DIVIDERS,
            (101.5, 202.25, 303.75, 404.125),
            "s_per_km",
        ),
    )
    metrics = replace(
        page.metrics,
        hr_time_in_zone_s=zone_inputs[0][4],
        power_time_in_zone_s=zone_inputs[1][4],
        pace_time_in_zone_s=zone_inputs[2][4],
    )
    page = replace(page, metrics=metrics)
    assert page.athlete is not None

    for missing_channel, absent_input in (
        (channel, missing_input)
        for channel, _metric, _zone, _dividers, _times, _unit in zone_inputs
        for missing_input in ("times", "spec")
    ):
        if absent_input == "times":
            metric_name = next(
                metric
                for channel, metric, *_rest in zone_inputs
                if channel == missing_channel
            )
            case_metrics = replace(
                page.metrics,
                **cast(Any, {metric_name: None}),
            )
            case_page = replace(page, metrics=case_metrics)
        else:
            zone_name = next(
                zone
                for channel, _metric, zone, *_rest in zone_inputs
                if channel == missing_channel
            )
            case_page = replace(
                page,
                athlete=replace(page.athlete, **cast(Any, {zone_name: None})),
            )

        expected: list[tuple[object, ...]] = []
        for channel, _metric, _zone, dividers, times, unit in zone_inputs:
            if channel == missing_channel:
                continue
            for zone_index, time_s in enumerate(times, start=1):
                expected.append(
                    (
                        channel,
                        zone_index,
                        dividers[zone_index - 2] if zone_index > 1 else None,
                        dividers[zone_index - 1]
                        if zone_index <= len(dividers)
                        else None,
                        unit,
                        time_s,
                    )
                )
        production_error: Exception | None = None
        actual_rows: object = None
        try:
            actual_rows = _producer().rows(case_page)["zone_times"]
        except (TypeError, AttributeError) as error:
            production_error = error
        assert production_error is None, (
            f"missing {absent_input} for {missing_channel} must omit that channel"
        )
        assert actual_rows == tuple(expected)


def test_absent_zone_specs_and_absent_activity_lap_starts_stay_null() -> None:
    page, _base = _run_case(athlete=None)
    activity = replace(
        page.activity,
        start_time=None,
        laps=(replace(page.activity.laps[0], start_time=None), *page.activity.laps[1:]),
    )
    no_athlete_page = replace(
        page,
        activity=activity,
        metrics=compute_metrics(activity, None),
        athlete_fingerprint=athlete_fingerprint(None),
    )

    rows = _producer().rows(no_athlete_page)

    assert rows["zone_times"] == ()
    assert rows["activities"][0][0] is None
    assert all(row[1] is None for row in rows["records"])
    assert rows["laps"][0][1] is None


def test_channel_sources_follow_base_and_extra_provenance() -> None:
    page, _base = _run_case()
    assert page.provenance.extras
    first_extra = page.provenance.extras[0]
    second_extra = replace(
        first_extra,
        sha256="2" * 64,
        channels=("cadence_rpm", "speed_mps"),
    )
    assert second_extra.sha256 != first_extra.sha256
    assert second_extra.channels == ("cadence_rpm", "speed_mps")
    page = replace(
        page,
        provenance=replace(
            page.provenance,
            extras=(*page.provenance.extras, second_extra),
        ),
    )
    rows = _producer().rows(page)["channel_sources"]
    expected = tuple(
        (channel, contribution.sha256, role)
        for contribution, role in (
            (page.provenance.base, "base"),
            *((extra, "extra") for extra in page.provenance.extras),
        )
        for channel in contribution.channels
    )
    assert rows == expected
    assert {row[2] for row in rows} == {"base", "extra"}
    assert any(row[0] == "form_power_w" and row[2] == "extra" for row in rows)
    assert rows[-2:] == (
        ("cadence_rpm", "2" * 64, "extra"),
        ("speed_mps", "2" * 64, "extra"),
    )
