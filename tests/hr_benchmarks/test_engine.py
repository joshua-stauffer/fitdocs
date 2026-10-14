"""Heart-rate settings and synthetic normalized-series integration."""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from pathlib import Path

import pytest

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.hr_benchmarks import engine
from fitdocs.hr_benchmarks.types import Evidence, HrFailure
from fitdocs.load.channels.types import ChannelId, SufficiencySettings
from fitdocs.load.priority import ChannelPriority
from fitdocs.load.qa.types import FlagSettings
from fitdocs.load.settings import LoadSettings, LoadSettingsError, load_load_settings
from fitdocs.model import Sport
from fitdocs.settings import SettingsError
from fitdocs.wellness import Metric, SeriesValue, WellnessSettingsError
from tests.wellness.builders_series import write_series


def test_settings_keep_complete_load_value(tmp_path: Path) -> None:
    settings = engine.load_hr_stage_settings(
        {
            "wellness": {"precedence": ["intervals-icu"]},
            "load": {
                "default_calculator": "synthetic-method",
                "benchmark_staleness_days": 37,
                "sufficiency": {
                    "min_duration_s": 73,
                    "min_stream_coverage": 0.71,
                    "power_min_stream_coverage": 0.72,
                    "hr_min_stream_coverage": 0.73,
                    "pace_min_stream_coverage": 0.74,
                },
                "priority": {
                    "run": ["heart_rate", "power", "pace"],
                    "ride": ["heart_rate", "power"],
                },
                "flags": {
                    "cadence_lock_min_correlation": 0.81,
                    "cadence_lock_max_delta_bpm": 7.0,
                    "cadence_lock_window_s": 91,
                    "cadence_lock_min_duration_s": 211,
                    "cadence_lock_min_paired_coverage": 0.61,
                    "divergence_max_intensity_delta": 0.31,
                    "aerobic_drift_max_pct": 6.2,
                },
            },
        },
        data_root=tmp_path / "outer" / "athlete-library",
    )
    assert settings == engine.HrStageSettings(
        LoadSettings(
            default_calculator="synthetic-method",
            benchmark_staleness_days=37,
            sufficiency=SufficiencySettings(73, 0.71, 0.72, 0.73, 0.74),
            channel_priority=ChannelPriority(
                {
                    Sport.RUN: (ChannelId.HEART_RATE, ChannelId.POWER, ChannelId.PACE),
                    Sport.RIDE: (ChannelId.HEART_RATE, ChannelId.POWER),
                    Sport.WALK: (ChannelId.HEART_RATE,),
                    Sport.HIKE: (ChannelId.HEART_RATE,),
                }
            ),
            flags=FlagSettings(0.81, 7.0, 91, 211, 0.61, 0.31, 6.2),
        ),
        ("intervals-icu", "garmin-export"),
    )


@pytest.mark.parametrize("document", [{}, {"wellness": {}, "load": {}}])
def test_settings_defaults(document: Mapping[str, object], tmp_path: Path) -> None:
    assert engine.load_hr_stage_settings(document, data_root=tmp_path) == (
        engine.HrStageSettings(LoadSettings(), ("garmin-export", "intervals-icu"))
    )


def test_settings_reads_shared_load_reader_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document: Mapping[str, object] = {"load": {"benchmark_staleness_days": 39}}
    root = tmp_path / "reader-library"
    calls: list[tuple[Mapping[str, object], Path]] = []

    def read_load(document: Mapping[str, object], path: Path) -> LoadSettings:
        calls.append((document, path))
        return load_load_settings(document, path)

    monkeypatch.setattr(engine, "load_load_settings", read_load)
    engine.load_hr_stage_settings(document, data_root=root)
    assert calls == [(document, root / "fitdocs.toml")]


@pytest.mark.parametrize("field", ["load", "resting_order"])
def test_settings_frozen(field: str, tmp_path: Path) -> None:
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    error = None
    try:
        setattr(settings, field, None)
    except FrozenInstanceError as exc:
        error = exc
    assert isinstance(error, FrozenInstanceError)


@pytest.mark.parametrize(
    "document,error_type,detail",
    [
        ({"wellness": 17}, WellnessSettingsError, "[wellness] must be a table"),
        (
            {"load": {"flags": 23}},
            LoadSettingsError,
            "[load.flags] must be a table, got 23 (int)",
        ),
    ],
    ids=["wellness", "load-flags"],
)
def test_settings_errors_keep_type_file_and_reason(
    document: Mapping[str, object],
    error_type: type[SettingsError],
    detail: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "nested-library" / "data-home"
    error = None
    try:
        engine.load_hr_stage_settings(document, data_root=root)
    except SettingsError as exc:
        error = exc
    assert (type(error), str(error)) == (
        error_type,
        f"{root / 'fitdocs.toml'}: {detail}",
    )


def _stage_two_sources(root: Path) -> None:
    values: list[SeriesValue] = []
    for i in range(16):
        day = date(2022, 12, 18) + timedelta(days=i)
        values.extend(
            (
                SeriesValue(
                    day, Metric.RESTING_HR_BPM, "garmin-export", None, 91, True
                ),
                SeriesValue(day, Metric.STEPS, "intervals-icu", None, 8021, True),
                SeriesValue(day, Metric.MAX_HR_BPM, "garmin-export", None, 187, True),
            )
        )
        if i < 14:
            values.append(
                SeriesValue(
                    day,
                    Metric.RESTING_HR_BPM,
                    "intervals-icu",
                    None,
                    54 if i < 7 else 59,
                    False,
                )
            )
    write_series(root, values)


@pytest.mark.parametrize(
    "wellness",
    [
        {"precedence": ["intervals-icu"]},
        {
            "precedence": ["garmin-export"],
            "metric_precedence": {
                "resting_hr_bpm": ["intervals-icu"],
                "steps": ["garmin-export"],
            },
        },
    ],
    ids=["general-precedence", "metric-overrides-general"],
)
def test_series_use_configured_source_values_and_evidence_year(
    wellness: dict[str, object], tmp_path: Path
) -> None:
    root = tmp_path / "outer" / "another-library"
    _stage_two_sources(root)
    settings = engine.load_hr_stage_settings({"wellness": wellness}, data_root=root)
    assert engine._read_resting_series(root, settings) == engine._RestingSeries(
        (
            Evidence(
                date(2022, 12, 31),
                57,
                "intervals-icu",
                "wellness/2022.csv",
                "intervals-icu:resting_hr_bpm",
                "median of 14 daily values from intervals-icu "
                "on the 28 days ending 2022-12-31",
                "intervals-icu resting heart rate, 28-day median",
            ),
            Evidence(
                date(2023, 1, 1),
                57,
                "intervals-icu",
                "wellness/2023.csv",
                "intervals-icu:resting_hr_bpm",
                "median of 14 daily values from intervals-icu "
                "on the 28 days ending 2023-01-01",
                "intervals-icu resting heart rate, 28-day median",
            ),
            Evidence(
                date(2023, 1, 2),
                57,
                "intervals-icu",
                "wellness/2023.csv",
                "intervals-icu:resting_hr_bpm",
                "median of 14 daily values from intervals-icu "
                "on the 28 days ending 2023-01-02",
                "intervals-icu resting heart rate, 28-day median",
            ),
        ),
        False,
        (),
        (),
    )


def test_series_default_order_uses_device_source(tmp_path: Path) -> None:
    root = tmp_path / "default-library"
    _stage_two_sources(root)
    settings = engine.load_hr_stage_settings({}, data_root=root)
    assert engine._read_resting_series(root, settings) == engine._RestingSeries(
        (
            Evidence(
                date(2022, 12, 31),
                91,
                "garmin-export",
                "wellness/2022.csv",
                "garmin-export:resting_hr_bpm",
                "median of 14 daily values from garmin-export "
                "on the 28 days ending 2022-12-31",
                "garmin-export resting heart rate, 28-day median",
            ),
            Evidence(
                date(2023, 1, 1),
                91,
                "garmin-export",
                "wellness/2023.csv",
                "garmin-export:resting_hr_bpm",
                "median of 15 daily values from garmin-export "
                "on the 28 days ending 2023-01-01",
                "garmin-export resting heart rate, 28-day median",
            ),
            Evidence(
                date(2023, 1, 2),
                91,
                "garmin-export",
                "wellness/2023.csv",
                "garmin-export:resting_hr_bpm",
                "median of 16 daily values from garmin-export "
                "on the 28 days ending 2023-01-02",
                "garmin-export resting heart rate, 28-day median",
            ),
        ),
        False,
        (),
        (),
    )


def test_two_unformed_sources_are_not_spliced(tmp_path: Path) -> None:
    root = tmp_path / "separate-library"
    write_series(
        root,
        [
            SeriesValue(
                date(2020, 3, 1) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "intervals-icu" if i < 7 else "garmin-export",
                None,
                45 + i,
                True,
            )
            for i in range(14)
        ],
    )
    settings = engine.load_hr_stage_settings({}, data_root=root)
    assert engine._read_resting_series(root, settings) == engine._RestingSeries(
        (), False, (), ()
    )


@pytest.mark.parametrize("partition", ["absent", "empty", "other-metrics"])
def test_series_without_raw_resting_values_keeps_partition(
    partition: str, tmp_path: Path
) -> None:
    root = tmp_path / "empty-library"
    if partition != "absent":
        write_series(
            root,
            []
            if partition == "empty"
            else [
                SeriesValue(
                    date(2021, 4, 5), Metric.STEPS, "garmin-export", None, 9123, True
                )
            ],
        )
    settings = engine.load_hr_stage_settings({}, data_root=root)
    assert engine._read_resting_series(root, settings) == engine._RestingSeries(
        (),
        True,
        (),
        (
            "the wellness series holds no resting heart rate; "
            "derived resting entries kept as on file",
        ),
    )


@pytest.mark.parametrize("count", [1, 7, 13])
def test_short_resting_series_recomputes_without_empty_note(
    count: int, tmp_path: Path
) -> None:
    root = tmp_path / "short-library"
    write_series(
        root,
        [
            SeriesValue(
                date(2021, 6, 1) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                63 + i,
                True,
            )
            for i in range(count)
        ],
    )
    settings = engine.load_hr_stage_settings({}, data_root=root)
    assert engine._read_resting_series(root, settings) == engine._RestingSeries(
        (), False, (), ()
    )


@pytest.mark.parametrize("problem", ["manifest-utf8", "year-header"])
def test_unreadable_series_keeps_partition_with_reason(
    problem: str, tmp_path: Path
) -> None:
    root = tmp_path / "nested-root" / "broken-library"
    write_series(
        root,
        [
            SeriesValue(
                date(2020, 8, 6), Metric.RESTING_HR_BPM, "garmin-export", None, 67, True
            )
        ],
    )
    manifest = root / "wellness/manifest.toml"
    if problem == "manifest-utf8":
        manifest.write_bytes(b"\xff")
        reason = (
            f"{manifest}: invalid manifest: "
            "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"
        )
    else:
        year_file = root / "wellness/2020.csv"
        year_file.write_bytes(b"incorrect-header\n")
        reason = f"{year_file}:1: wrong series header"
    settings = engine.load_hr_stage_settings({}, data_root=root)
    assert engine._read_resting_series(root, settings) == engine._RestingSeries(
        (),
        True,
        (
            HrFailure(
                BenchmarkKind.RESTING_HR_BPM,
                "wellness/manifest.toml",
                reason,
            ),
        ),
        (),
    )
