"""Heart-rate settings and synthetic normalized-series integration."""

import hashlib
import os
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest

from fitdocs import docio
from fitdocs.benchmarks import (
    Benchmark,
    BenchmarkKind,
    BenchmarkSource,
    BenchmarkSourceKind,
    benchmarks_to_document,
)
from fitdocs.hr_benchmarks import engine
from fitdocs.hr_benchmarks.maximum import max_evidence
from fitdocs.hr_benchmarks.peaks import session_peak
from fitdocs.hr_benchmarks.timeline import TimelineResult, derive_timeline
from fitdocs.hr_benchmarks.types import (
    BackReachChange,
    Evidence,
    HrFailure,
    HrStageReport,
    Inconsistency,
    KindOutcome,
    KindRule,
    NoEvidenceReason,
    SessionPeak,
    SkippedDocument,
    Takeover,
    Violation,
)
from fitdocs.load.channels.types import ChannelId, SufficiencySettings
from fitdocs.load.priority import ChannelPriority
from fitdocs.load.profile import (
    AthleteProfile,
    ProfileError,
    load_profile,
    save_profile,
)
from fitdocs.load.qa.types import FlagSettings
from fitdocs.load.settings import LoadSettings, LoadSettingsError, load_load_settings
from fitdocs.model import Modality, Samples, Sport
from fitdocs.settings import SettingsError
from fitdocs.wellness import Metric, SeriesValue, WellnessSettingsError
from tests.fixtures import builder
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
        ("intervals-icu", "garmin-export", "apple-health"),
    )


@pytest.mark.parametrize("document", [{}, {"wellness": {}, "load": {}}])
def test_settings_defaults(document: Mapping[str, object], tmp_path: Path) -> None:
    assert engine.load_hr_stage_settings(document, data_root=tmp_path) == (
        engine.HrStageSettings(
            LoadSettings(), ("garmin-export", "apple-health", "intervals-icu")
        )
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


# Task 3.2: local workout fixtures.
def _session_fit(
    bpm: int | None = 151,
    *,
    sport: str = "running",
    duration: int = 40,
    locked: bool = False,
) -> bytes:
    messages = [m for m in builder.run_mesgs() if m["mesg_num"] not in (19, 20)]
    for message in messages:
        if "sport" in message:
            message["sport"] = sport
        if message["mesg_num"] == 18:
            message["timestamp"] = builder.FIT_TIMESTAMP_BASE + duration
            message["total_elapsed_time"] = float(duration)
            message["total_timer_time"] = float(duration)
            message["max_heart_rate"] = 229
    records: list[dict[str, object]] = []
    for second in range(0, duration + 1, 5):
        record: dict[str, object] = {
            "mesg_num": 20,
            "timestamp": builder.FIT_TIMESTAMP_BASE + second,
        }
        if bpm is not None:
            record["heart_rate"] = bpm + (2 * (second % 3) if locked else 0)
        if locked and bpm is not None:
            record["cadence"] = (bpm + 2 * (second % 3)) // 2
        records.append(record)
    return builder.encode([*messages[:3], *records, *messages[3:]])


def _workout_archive(root: Path, payload: bytes) -> str:
    ref = f"fit-archive/{hashlib.sha256(payload).hexdigest()}.fit"
    archive = root / ref
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(payload)
    return ref


def _workout_page(
    root: Path,
    name: str,
    refs: list[str],
    *,
    day: str | None = "2021-02-03",
    sport: str = "Run",
    kind: str = "workout",
) -> Path:
    page = root / "workouts" / name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        f"---\ntype: {kind}\nsport: {sport}\n"
        + (f"date: {day}\n" if day is not None else "")
        + "sources: "
        + repr(refs)
        + "\n---\nSynthetic workout.\n",
        encoding="utf-8",
    )
    return page


def _reason_counts(**counts: int) -> tuple[tuple[NoEvidenceReason, int], ...]:
    return tuple((reason, counts.get(reason.value, 0)) for reason in NoEvidenceReason)


def _three_peak_pages(root: Path) -> None:
    for name, day, bpm, sport in (
        ("z-early.md", "2021-02-01", 181, "cycling"),
        ("c-late.md", "2021-02-03", 139, "running"),
        ("m-median.md", "2021-02-02", 163, "cycling"),
    ):
        _workout_page(
            root,
            name,
            [_workout_archive(root, _session_fit(bpm, sport=sport))],
            day=day,
        )


def _three_peak_evidence() -> tuple[Evidence, ...]:
    return (
        Evidence(
            date(2021, 2, 3),
            163,
            "workouts",
            "workouts/m-median.md",
            None,
            "median of the three highest 30-second sustained peaks "
            "(181.0, 163.0, 139.0 bpm) among 3 sessions dated 2020-02-05 to 2021-02-03",
            "workout heart rate, 365 days ending 2021-02-03",
        ),
    )


def test_workouts_collect_all_peaks_and_calendar_dates(tmp_path: Path) -> None:
    _three_peak_pages(tmp_path)
    _workout_page(tmp_path, "a-personal.md", [], kind="note")
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        _three_peak_evidence(), 3, 3, _reason_counts(), (), (), False
    )


@pytest.mark.parametrize("sport", list(Sport))
def test_workouts_every_sport_without_effort_tag(sport: Sport, tmp_path: Path) -> None:
    _workout_page(
        tmp_path,
        "untagged.md",
        [_workout_archive(tmp_path, _session_fit())],
        sport=sport.value,
    )
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        (), 1, 1, _reason_counts(), (), (), False
    )


@pytest.mark.parametrize("reason", list(NoEvidenceReason))
def test_workouts_complete_reason_partition(
    reason: NoEvidenceReason, tmp_path: Path
) -> None:
    refs = [_workout_archive(tmp_path, _session_fit())]
    day: str | None = "2021-02-03"
    skipped: tuple[SkippedDocument, ...] = ()
    if reason is NoEvidenceReason.UNDATED:
        day = None
        refs = [_workout_archive(tmp_path, builder.non_fit_bytes())]
    elif reason is NoEvidenceReason.ARCHIVE_MISSING:
        refs = ["fit-archive/abc123.fit"]
        skipped = (
            SkippedDocument("workouts/problem.md", reason, "archived source not found"),
        )
    elif reason is NoEvidenceReason.ARCHIVE_UNDECODABLE:
        refs = [_workout_archive(tmp_path, builder.non_fit_bytes())]
        skipped = (
            SkippedDocument(
                "workouts/problem.md",
                reason,
                "Source is not a FIT file: header check failed.",
            ),
        )
    elif reason is NoEvidenceReason.NO_HEART_RATE:
        refs = [_workout_archive(tmp_path, _session_fit(None))]
    elif reason is NoEvidenceReason.CADENCE_LOCKED:
        refs = [
            _workout_archive(tmp_path, _session_fit(170, duration=400, locked=True))
        ]
    elif reason is NoEvidenceReason.NO_SUSTAINED_STRETCH:
        refs = [_workout_archive(tmp_path, _session_fit(duration=20))]
    elif reason is NoEvidenceReason.NOT_RUN_OR_BIKE:
        refs = [_workout_archive(tmp_path, _session_fit(sport="walking"))]
    _workout_page(tmp_path, "problem.md", refs, day=day)
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        (), 1, 0, _reason_counts(**{reason.value: 1}), skipped, (), False
    )


def test_workouts_other_modalities_supply_no_maximum_evidence(
    tmp_path: Path,
) -> None:
    _three_peak_pages(tmp_path)
    for name, sport in (("w-walk.md", "walking"), ("x-swim.md", "swimming")):
        _workout_page(
            tmp_path,
            name,
            [_workout_archive(tmp_path, _session_fit(215, sport=sport))],
            day="2021-02-03",
        )
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        _three_peak_evidence(), 5, 3, _reason_counts(not_run_or_bike=2), (), (), False
    )


def test_workouts_compose_only_extra_heart_rate_and_extra_priority(
    tmp_path: Path,
) -> None:
    _three_peak_pages(tmp_path)
    first = _workout_archive(tmp_path, _session_fit(207))
    preferred = _workout_archive(tmp_path, _session_fit(175))
    base = _workout_archive(tmp_path, _session_fit(None))
    _workout_page(
        tmp_path,
        "m-median.md",
        [first, "fit-archive/ff0011.fit", preferred, base],
        day="2021-02-02",
    )
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        (
            Evidence(
                date(2021, 2, 3),
                175,
                "workouts",
                "workouts/m-median.md",
                None,
                "median of the three highest 30-second sustained peaks "
                "(181.0, 175.0, 139.0 bpm) among 3 sessions "
                "dated 2020-02-05 to 2021-02-03",
                "workout heart rate, 365 days ending 2021-02-03",
            ),
        ),
        3,
        3,
        _reason_counts(),
        (),
        (),
        False,
    )


def test_workouts_last_source_is_base(tmp_path: Path) -> None:
    first = _workout_archive(tmp_path, _session_fit(207))
    base = _workout_archive(tmp_path, _session_fit(143))
    for name, bpm in (("a.md", 191), ("c.md", 125)):
        _workout_page(tmp_path, name, [_workout_archive(tmp_path, _session_fit(bpm))])
    _workout_page(tmp_path, "b.md", [first, base])
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings).evidence == (
        Evidence(
            date(2021, 2, 3),
            143,
            "workouts",
            "workouts/b.md",
            None,
            "median of the three highest 30-second sustained peaks "
            "(191.0, 143.0, 125.0 bpm) among 3 sessions dated 2020-02-05 to 2021-02-03",
            "workout heart rate, 365 days ending 2021-02-03",
        ),
    )


def test_workouts_supplied_flags_change_cadence_verdict(tmp_path: Path) -> None:
    _workout_page(
        tmp_path,
        "near-lock.md",
        [_workout_archive(tmp_path, _session_fit(170, duration=400, locked=True))],
    )
    settings = engine.load_hr_stage_settings(
        {
            "load": {
                "flags": {
                    "cadence_lock_min_duration_s": 500,
                    "cadence_lock_min_correlation": 1.0,
                }
            }
        },
        data_root=tmp_path,
    )
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        (), 1, 1, _reason_counts(), (), (), False
    )


@pytest.mark.parametrize("extra", [False, True], ids=["base", "extra"])
def test_workouts_decode_error_is_skip_and_continues(
    extra: bool, tmp_path: Path
) -> None:
    _three_peak_pages(tmp_path)
    bad = _workout_archive(tmp_path, builder.non_fit_bytes())
    refs = [bad, _workout_archive(tmp_path, _session_fit())] if extra else [bad]
    _workout_page(tmp_path, "b-broken.md", refs)
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    calls: list[tuple[int, int]] = []
    actual = engine._read_workout_sessions(
        tmp_path, settings, progress=lambda done, total: calls.append((done, total))
    )
    assert (actual, calls) == (
        engine._WorkoutSessions(
            _three_peak_evidence(),
            4,
            3,
            _reason_counts(archive_undecodable=1),
            (
                SkippedDocument(
                    "workouts/b-broken.md",
                    NoEvidenceReason.ARCHIVE_UNDECODABLE,
                    "Source is not a FIT file: header check failed.",
                ),
            ),
            (),
            False,
        ),
        [(1, 4), (2, 4), (3, 4), (4, 4)],
    )


@pytest.mark.parametrize("extra", [False, True], ids=["base", "extra"])
def test_workouts_unreadable_archive_keeps_maximum(extra: bool, tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read files without permission bits")
    _three_peak_pages(tmp_path)
    unreadable = _workout_archive(tmp_path, _session_fit(199))
    refs = (
        [unreadable, _workout_archive(tmp_path, _session_fit())]
        if extra
        else [unreadable]
    )
    _workout_page(tmp_path, "y-unreadable.md", refs)
    _workout_page(tmp_path, "b-unreadable.md", refs)
    archive = tmp_path / unreadable
    archive.chmod(0)
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    calls: list[tuple[int, int]] = []
    try:
        actual = engine._read_workout_sessions(
            tmp_path, settings, progress=lambda done, total: calls.append((done, total))
        )
    finally:
        archive.chmod(0o600)
    assert (actual, calls) == (
        engine._WorkoutSessions(
            _three_peak_evidence(),
            5,
            3,
            _reason_counts(),
            (),
            (
                HrFailure(
                    BenchmarkKind.MAX_HR_BPM,
                    "workouts/b-unreadable.md",
                    f"[Errno 13] Permission denied: '{archive}'",
                ),
                HrFailure(
                    BenchmarkKind.MAX_HR_BPM,
                    "workouts/y-unreadable.md",
                    f"[Errno 13] Permission denied: '{archive}'",
                ),
            ),
            True,
        ),
        [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)],
    )


def test_workouts_sorted_progress_and_single_frontmatter_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _three_peak_pages(tmp_path)
    _workout_page(tmp_path, "n-undated.md", [], day=None)
    _workout_page(tmp_path, "a-note.md", [], kind="note")
    _workout_page(tmp_path, "b-missing.md", [])
    pages = tmp_path / "workouts"
    (pages / "ignored.txt").write_text("not markdown", encoding="utf-8")
    (pages / "nested").mkdir()
    (pages / "nested/ignored.md").write_text("not direct", encoding="utf-8")
    events: list[tuple[object, ...]] = []
    real_read = docio.read_frontmatter
    real_glob = Path.glob
    real_peak = session_peak

    def read_once(path: Path) -> dict[str, object] | None:
        events.append(("read", path.name))
        return real_read(path)

    def reversed_glob(path: Path, pattern: str, **kwargs: object) -> Iterator[Path]:
        return iter(sorted(real_glob(path, pattern, **kwargs), reverse=True))

    def peak_after_processing(
        samples: Samples,
        *,
        modality: Modality,
        flags: FlagSettings,
    ) -> float | NoEvidenceReason:
        result = real_peak(samples, modality=modality, flags=flags)
        events.append(("peak", result))
        return result

    def progress(done: int, total: int) -> None:
        events.append(("progress", done, total))

    monkeypatch.setattr(docio, "read_frontmatter", read_once)
    monkeypatch.setattr(Path, "glob", reversed_glob)
    monkeypatch.setattr(engine, "session_peak", peak_after_processing)
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    engine._read_workout_sessions(tmp_path, settings, progress=progress)
    assert events == [
        ("read", "a-note.md"),
        ("read", "b-missing.md"),
        ("read", "c-late.md"),
        ("read", "m-median.md"),
        ("read", "n-undated.md"),
        ("read", "z-early.md"),
        ("progress", 1, 5),
        ("peak", 139.0),
        ("progress", 2, 5),
        ("peak", 163.0),
        ("progress", 3, 5),
        ("progress", 4, 5),
        ("peak", 181.0),
        ("progress", 5, 5),
    ]


@pytest.mark.parametrize("empty_directory", [False, True])
def test_workouts_empty_corpus_has_all_zero_reasons(
    empty_directory: bool, tmp_path: Path
) -> None:
    if empty_directory:
        (tmp_path / "workouts").mkdir()
    calls: list[tuple[int, int]] = []
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    actual = engine._read_workout_sessions(
        tmp_path, settings, progress=lambda done, total: calls.append((done, total))
    )
    assert (actual, calls) == (
        engine._WorkoutSessions((), 0, 0, _reason_counts(), (), (), False),
        [],
    )


def test_workouts_sorted_skips_keep_full_document_details(tmp_path: Path) -> None:
    missing = "fit-archive/123abc.fit"
    corrupt = _workout_archive(tmp_path, builder.non_fit_bytes())
    for name, ref in (
        ("z.md", corrupt),
        ("c.md", missing),
        ("b.md", corrupt),
        ("a.md", missing),
    ):
        _workout_page(tmp_path, name, [ref])
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        (),
        4,
        0,
        _reason_counts(archive_missing=2, archive_undecodable=2),
        (
            SkippedDocument(
                "workouts/a.md",
                NoEvidenceReason.ARCHIVE_MISSING,
                "archived source not found",
            ),
            SkippedDocument(
                "workouts/b.md",
                NoEvidenceReason.ARCHIVE_UNDECODABLE,
                "Source is not a FIT file: header check failed.",
            ),
            SkippedDocument(
                "workouts/c.md",
                NoEvidenceReason.ARCHIVE_MISSING,
                "archived source not found",
            ),
            SkippedDocument(
                "workouts/z.md",
                NoEvidenceReason.ARCHIVE_UNDECODABLE,
                "Source is not a FIT file: header check failed.",
            ),
        ),
        (),
        False,
    )


def test_workouts_undated_page_opens_no_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = _workout_archive(tmp_path, _session_fit())
    _workout_page(tmp_path, "undated.md", [ref], day=None)
    reads: list[Path] = []
    real_read = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path.suffix == ".fit":
            reads.append(path)
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    actual = engine._read_workout_sessions(tmp_path, settings)
    assert (actual, reads) == (
        engine._WorkoutSessions((), 1, 0, _reason_counts(undated=1), (), (), False),
        [],
    )


def _forwarding_samples(bpm: int) -> Samples:
    return Samples(
        time_s=(0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0),
        heart_rate_bpm=(bpm,) * 9,
        power_w=(None,) * 9,
        cadence_rpm=(None,) * 9,
        speed_mps=(None,) * 9,
        distance_m=(None,) * 9,
        altitude_m=(None,) * 9,
        latitude_deg=(None,) * 9,
        longitude_deg=(None,) * 9,
        temperature_c=(None,) * 9,
    )


def test_workouts_forward_each_sessions_inputs_and_peak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _three_peak_pages(tmp_path)
    settings = engine.load_hr_stage_settings(
        {
            "load": {
                "flags": {
                    "cadence_lock_min_correlation": 0.81,
                    "cadence_lock_max_delta_bpm": 7.0,
                    "cadence_lock_window_s": 91,
                    "cadence_lock_min_duration_s": 211,
                    "cadence_lock_min_paired_coverage": 0.61,
                    "divergence_max_intensity_delta": 0.31,
                    "aerobic_drift_max_pct": 6.2,
                }
            }
        },
        data_root=tmp_path,
    )
    expected_flags = FlagSettings(0.81, 7.0, 91, 211, 0.61, 0.31, 6.2)
    expected_peaks = (
        SessionPeak(date(2021, 2, 3), "workouts/c-late.md", 139.0),
        SessionPeak(date(2021, 2, 2), "workouts/m-median.md", 163.0),
        SessionPeak(date(2021, 2, 1), "workouts/z-early.md", 181.0),
    )
    expected_calls = (
        (_forwarding_samples(139), Modality.RUN, expected_flags),
        (_forwarding_samples(163), Modality.BIKE, expected_flags),
        (_forwarding_samples(181), Modality.BIKE, expected_flags),
    )
    peaks: list[SessionPeak] = []
    calls: list[tuple[Samples, Modality, FlagSettings]] = []
    real_maximum = max_evidence
    real_peak = session_peak

    hands: list[Collection[date]] = []

    def maximum(
        values: Sequence[SessionPeak], *, hand_dates: Collection[date] = ()
    ) -> tuple[Evidence, ...]:
        peaks.extend(values)
        hands.append(hand_dates)
        return real_maximum(values, hand_dates=hand_dates)

    def peak(
        samples: Samples, *, modality: Modality, flags: FlagSettings
    ) -> float | NoEvidenceReason:
        calls.append((samples, modality, flags))
        return real_peak(samples, modality=modality, flags=flags)

    monkeypatch.setattr(engine, "max_evidence", maximum)
    monkeypatch.setattr(engine, "session_peak", peak)
    hand_dates = frozenset({date(2021, 1, 5), date(2020, 12, 1)})
    engine._read_workout_sessions(tmp_path, settings, hand_dates)
    assert (tuple(peaks), tuple(calls), hands) == (
        expected_peaks,
        expected_calls,
        [hand_dates],
    )


@pytest.mark.parametrize(
    ("bpm", "expected"),
    [(31, 31.166666666666668), (163, 163.16666666666666)],
    ids=["low", "high"],
)
def test_workouts_forward_fractional_peak_without_rounding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bpm: int, expected: float
) -> None:
    messages = [
        message
        for message in builder.run_mesgs()
        if message["mesg_num"] not in (19, 20)
    ]
    for message in messages:
        if message["mesg_num"] == 18:
            message["timestamp"] = builder.FIT_TIMESTAMP_BASE + 40
            message["total_elapsed_time"] = 40.0
            message["total_timer_time"] = 40.0
    records: list[builder.Mesg] = [
        {
            "mesg_num": 20,
            "timestamp": builder.FIT_TIMESTAMP_BASE + second,
            "heart_rate": bpm + 1 if second == 20 else bpm,
        }
        for second in range(0, 41, 5)
    ]
    payload = builder.encode([*messages[:3], *records, *messages[3:]])
    _workout_page(tmp_path, "fractional.md", [_workout_archive(tmp_path, payload)])
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    expected_peaks = [SessionPeak(date(2021, 2, 3), "workouts/fractional.md", expected)]
    raw_peaks: list[float | NoEvidenceReason] = []
    peaks: list[SessionPeak] = []

    def peak(
        samples: Samples, *, modality: Modality, flags: FlagSettings
    ) -> float | NoEvidenceReason:
        value = session_peak(samples, modality=modality, flags=flags)
        raw_peaks.append(value)
        return value

    def maximum(
        values: Sequence[SessionPeak], *, hand_dates: Collection[date] = ()
    ) -> tuple[Evidence, ...]:
        peaks.extend(values)
        return max_evidence(values, hand_dates=hand_dates)

    monkeypatch.setattr(engine, "session_peak", peak)
    monkeypatch.setattr(engine, "max_evidence", maximum)
    engine._read_workout_sessions(tmp_path, settings)
    assert (raw_peaks, peaks) == ([expected], expected_peaks)


_REST = BenchmarkKind.RESTING_HR_BPM
_MAX = BenchmarkKind.MAX_HR_BPM
_EMPTY_SERIES_NOTE = (
    "the wellness series holds no resting heart rate; "
    "derived resting entries kept as on file"
)


def _tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def _tree_changes(before: dict[str, tuple[bytes, int]], root: Path) -> tuple[str, ...]:
    after = _tree_snapshot(root)
    return tuple(
        sorted(
            key
            for key in before.keys() | after.keys()
            if before.get(key) != after.get(key)
        )
    )


def _basic_entries() -> tuple[Benchmark, Benchmark]:
    return (
        Benchmark(
            _REST,
            None,
            57,
            date(2021, 1, 14),
            note=(
                "Derived by fitdocs from garmin-export resting heart rate, "
                "28-day median."
            ),
            source=BenchmarkSource(
                BenchmarkSourceKind.DERIVED,
                "resting_hr_series_median",
                "wellness/2021.csv",
                (
                    "median of 14 daily values from garmin-export on the 28 days "
                    "ending 2021-01-14"
                ),
                "resting_hr_timeline_choice",
                "garmin-export:resting_hr_bpm",
            ),
        ),
        Benchmark(
            _MAX,
            None,
            163,
            date(2021, 2, 3),
            note=(
                "Derived by fitdocs from workout heart rate, "
                "365 days ending 2021-02-03."
            ),
            source=BenchmarkSource(
                BenchmarkSourceKind.DERIVED,
                "max_hr_sustained_peak",
                "workouts/m-median.md",
                (
                    "median of the three highest 30-second sustained peaks "
                    "(181.0, 163.0, 139.0 bpm) "
                    "among 3 sessions dated 2020-02-05 to 2021-02-03"
                ),
                "max_hr_timeline_choice",
            ),
        ),
    )


def _basic_root(root: Path) -> None:
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 1, 1) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                57,
                True,
            )
            for i in range(14)
        ),
    )
    _three_peak_pages(root)
    (root / "extras").mkdir()
    (root / "extras/untouched.txt").write_text("independent extra", encoding="utf-8")


def test_stage_real_workflow_preview_write_and_noop(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "complete-stage-library"
    _basic_root(root)
    before = _tree_snapshot(root)
    settings = engine.load_hr_stage_settings({}, data_root=root)
    rest, maximum = _basic_entries()
    expected = HrStageReport(
        3,
        3,
        _reason_counts(),
        (),
        ("garmin-export",),
        (
            KindOutcome(_REST, (rest,), (rest,), (), False),
            KindOutcome(_MAX, (maximum,), (maximum,), (), False),
        ),
        (),
        (),
        (),
        (),
        (),
        False,
        True,
    )
    preview = engine.derive_hr_benchmarks(root, settings=settings, dry_run=True)
    assert (preview, _tree_changes(before, root)) == (expected, ())
    writing = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        writing,
        load_profile(root).benchmarks.entries,
        _tree_changes(before, root),
    ) == (
        replace(expected, written=True),
        (rest, maximum),
        ("athlete.toml",),
    )
    saved = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(root, settings=settings)
    assert (repeated, _tree_changes(saved, root), set(load_profile(root).data)) == (
        replace(
            expected,
            kinds=(
                KindOutcome(_REST, (rest,), (), (), False),
                KindOutcome(_MAX, (maximum,), (), (), False),
            ),
            changed=False,
        ),
        (),
        {"profile_version", "benchmarks"},
    )


def _seed_entries(root: Path, entries: Sequence[Benchmark]) -> None:
    data = benchmarks_to_document(entries)
    data["custom"] = {"future": "retain this table"}
    save_profile(root, AthleteProfile(data))


def _track_profile_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    events: list[tuple[object, ...]] = []
    real_load = load_profile
    real_save = save_profile
    real_write = AthleteProfile.with_derived_benchmarks

    def load(root: Path) -> AthleteProfile:
        events.append(("load", root))
        return real_load(root)

    def save(root: Path, profile: AthleteProfile) -> None:
        events.append(("save", root))
        real_save(root, profile)

    def write(
        profile: AthleteProfile,
        entries: Sequence[Benchmark],
        *,
        kinds: frozenset[BenchmarkKind],
        replace_applies_from: bool = False,
    ) -> AthleteProfile:
        events.append(("write", tuple(entries), kinds, replace_applies_from))
        return real_write(
            profile, entries, kinds=kinds, replace_applies_from=replace_applies_from
        )

    monkeypatch.setattr(engine, "load_profile", load)
    monkeypatch.setattr(engine, "save_profile", save)
    monkeypatch.setattr(AthleteProfile, "with_derived_benchmarks", write)
    return events


@pytest.mark.parametrize("kind", [_REST, _MAX], ids=["resting", "maximum"])
def test_stage_date_only_change_uses_real_parsed_writer(
    kind: BenchmarkKind, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "date-seam" / kind.value
    _basic_root(root)
    entries = _basic_entries()
    target = next(entry for entry in entries if entry.kind is kind)
    stale = replace(target, applies_from=date(2021, 1, 1))
    _seed_entries(
        root, tuple(stale if entry.kind is kind else entry for entry in entries)
    )
    settings = engine.load_hr_stage_settings({}, data_root=root)
    before = _tree_snapshot(root)
    previous_selection = load_profile(root).benchmarks.applicable(
        kind, discipline=None, on=date(2021, 1, 2)
    )
    calls = _track_profile_calls(monkeypatch)
    preview = engine.derive_hr_benchmarks(root, settings=settings, dry_run=True)
    outcomes = tuple(
        KindOutcome(
            entry.kind,
            (entry,),
            (entry,) if entry.kind is kind else (),
            (stale,) if entry.kind is kind else (),
            False,
        )
        for entry in entries
    )
    expected = HrStageReport(
        3,
        3,
        _reason_counts(),
        (),
        ("garmin-export",),
        outcomes,
        (),
        (),
        (),
        (),
        (),
        False,
        True,
    )
    assert (previous_selection, preview, calls, _tree_changes(before, root)) == (
        stale,
        expected,
        [("load", root), ("write", entries, frozenset({_REST, _MAX}), True)],
        (),
    )
    calls.clear()
    writing = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        writing,
        calls,
        load_profile(root).benchmarks.applicable(
            kind, discipline=None, on=date(2021, 1, 2)
        ),
        _tree_changes(before, root),
    ) == (
        replace(expected, written=True),
        [
            ("load", root),
            ("write", entries, frozenset({_REST, _MAX}), True),
            ("save", root),
        ],
        None,
        ("athlete.toml",),
    )
    saved = _tree_snapshot(root)
    calls.clear()
    repeated = engine.derive_hr_benchmarks(root, settings=settings)
    assert (repeated, calls, _tree_changes(saved, root)) == (
        replace(
            expected,
            kinds=tuple(KindOutcome(e.kind, (e,), (), (), False) for e in entries),
            changed=False,
        ),
        [("load", root), ("write", entries, frozenset({_REST, _MAX}), True)],
        (),
    )


@pytest.mark.parametrize(
    "series_state", ["absent", "empty", "other-metric", "one", "thirteen", "formed"]
)
@pytest.mark.parametrize("old_present", [False, True], ids=["no-old", "old"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
def test_stage_resting_input_partition(
    series_state: str, old_present: bool, dry_run: bool, tmp_path: Path
) -> None:
    root = tmp_path / "partition" / f"{series_state}-{old_present}-{dry_run}"
    root.mkdir(parents=True)
    rest, maximum = _basic_entries()
    stale = replace(
        rest, value=71, applies_from=date(2021, 1, 1), note="prior resting entry"
    )
    _seed_entries(root, (stale, maximum) if old_present else ())
    if series_state != "absent":
        count = {"empty": 0, "other-metric": 1, "one": 1, "thirteen": 13, "formed": 14}[
            series_state
        ]
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 1) + timedelta(days=i),
                    Metric.STEPS
                    if series_state == "other-metric"
                    else Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    57,
                    True,
                )
                for i in range(count)
            ),
        )
    kept = series_state in {"absent", "empty", "other-metric"}
    new_rest = (
        (stale,)
        if kept and old_present
        else (rest,)
        if series_state == "formed"
        else ()
    )
    old_rest = (stale,) if old_present else ()
    changed = new_rest != old_rest or old_present
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    assert (
        report,
        _tree_changes(before, root),
        load_profile(root).benchmarks.entries,
    ) == (
        HrStageReport(
            0,
            0,
            _reason_counts(),
            (),
            ("garmin-export",) if series_state == "formed" else (),
            (
                KindOutcome(
                    _REST,
                    new_rest,
                    tuple(e for e in new_rest if e not in old_rest),
                    tuple(e for e in old_rest if e not in new_rest),
                    kept,
                ),
                KindOutcome(_MAX, (), (), (maximum,) if old_present else (), False),
            ),
            (),
            (),
            (),
            (),
            (_EMPTY_SERIES_NOTE,) if kept else (),
            changed and not dry_run,
            changed,
        ),
        ("athlete.toml",) if changed and not dry_run else (),
        ((stale, maximum) if old_present else ()) if dry_run else new_rest,
    )


def _short_evidence(day: date, value: int, key: str = "workouts") -> Evidence:
    return Evidence(
        day,
        value,
        key,
        f"synthetic/{key}.md",
        None,
        f"input {key} {day}",
        f"summary {key}",
    )


def _short_entry(
    kind: BenchmarkKind,
    day: date,
    value: int,
    key: str,
    note: str,
    *,
    confirmed: bool = False,
) -> Benchmark:
    inputs = f"input {key} {day}"
    if confirmed:
        inputs += (
            f"; differed from the value in force by more than 3 bpm on each "
            f"day from {day} to {day + timedelta(days=13)}"
        )
    return Benchmark(
        kind,
        None,
        value,
        day,
        note=note,
        source=BenchmarkSource(
            BenchmarkSourceKind.DERIVED,
            "resting_hr_series_median" if kind is _REST else "max_hr_sustained_peak",
            f"synthetic/{key}.md",
            inputs,
            "resting_hr_timeline_choice" if kind is _REST else "max_hr_timeline_choice",
        ),
    )


@pytest.mark.parametrize("rest_kept", [False, True], ids=["rest-rebuilt", "rest-kept"])
@pytest.mark.parametrize("max_kept", [False, True], ids=["max-rebuilt", "max-kept"])
@pytest.mark.parametrize(
    "measured", [False, True], ids=["absent-origin", "measured-origin"]
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
def test_stage_join_policy_and_forwarding(
    rest_kept: bool,
    max_kept: bool,
    measured: bool,
    dry_run: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "nested-join" / "athlete-data"
    root.mkdir(parents=True)
    origin = BenchmarkSource(BenchmarkSourceKind.MEASURED) if measured else None
    hands = (
        Benchmark(_REST, None, 50, date(2021, 1, 1), source=origin),
        Benchmark(_MAX, None, 170, date(2021, 1, 1), source=origin),
    )
    old_rest = replace(
        _basic_entries()[0],
        measured_on=date(2020, 12, 1),
        value=73,
        applies_from=date(2020, 11, 1),
    )
    old_max = replace(
        _basic_entries()[1],
        measured_on=date(2020, 12, 2),
        value=181,
        applies_from=date(2020, 11, 2),
    )
    _seed_entries(root, (*hands, old_rest, old_max))
    profile = load_profile(root)
    raw = dict(profile.data)
    region = cast(dict[str, object], raw["benchmarks"])
    athlete = cast(dict[str, object], region["athlete"])
    for kind in (_REST, _MAX):
        group = cast(list[dict[str, object]], athlete[kind.value])
        group[0]["future_entry"] = f"kept-{kind.value}"
        cast(dict[str, object], group[0]["source"])["future_source"] = (
            f"source-{kind.value}"
        )
    save_profile(root, AthleteProfile(raw))
    initial = load_profile(root)
    before = _tree_snapshot(root)
    events: list[tuple[object, ...]] = []
    settings = engine.load_hr_stage_settings({}, data_root=root)
    rest_evidence = tuple(
        _short_evidence(date(2021, 1, 2) + timedelta(days=i), 61, "z-source")
        for i in range(14)
    )
    max_evidence_values = (_short_evidence(date(2021, 1, 2), 175),)
    rest_failure = (
        (HrFailure(_REST, "wellness/manifest.toml", "synthetic series read failure"),)
        if rest_kept
        else ()
    )
    max_failure = (
        (HrFailure(_MAX, "workouts/cannot-read.md", "synthetic archive read failure"),)
        if max_kept
        else ()
    )
    skipped = (
        SkippedDocument(
            "workouts/missing.md",
            NoEvidenceReason.ARCHIVE_MISSING,
            "archived source not found",
        ),
    )
    counts = _reason_counts(
        undated=1,
        archive_missing=2,
        archive_undecodable=3,
        no_heart_rate=4,
        cadence_locked=5,
        no_sustained_stretch=6,
    )

    def progress(done: int, total: int) -> None:
        events.append(("progress", done, total))

    def resting(
        data_root: Path,
        received: engine.HrStageSettings,
        hand_dates: Collection[date],
    ) -> engine._RestingSeries:
        events.append(("resting", data_root, received is settings, hand_dates))
        return engine._RestingSeries(
            rest_evidence, rest_kept, rest_failure, ("series note",)
        )

    def workouts(
        data_root: Path,
        received: engine.HrStageSettings,
        hand_dates: Collection[date],
        *,
        progress: object = None,
    ) -> engine._WorkoutSessions:
        events.append(
            (
                "workouts",
                data_root,
                received is settings,
                hand_dates,
                progress is callback,
            )
        )
        if callable(progress):
            progress(23, 27)
        return engine._WorkoutSessions(
            max_evidence_values, 27, 6, counts, skipped, max_failure, max_kept
        )

    callback = progress
    monkeypatch.setattr(engine, "_read_resting_series", resting)
    monkeypatch.setattr(engine, "_read_workout_sessions", workouts)
    calls = _track_profile_calls(monkeypatch)
    real_load = cast(Callable[[Path], AthleteProfile], engine.__dict__["load_profile"])

    def load_after_evidence(data_root: Path) -> AthleteProfile:
        events.append(("profile", data_root))
        return real_load(data_root)

    monkeypatch.setattr(engine, "load_profile", load_after_evidence)
    rest = _short_entry(
        _REST,
        date(2021, 1, 2),
        61,
        "z-source",
        (
            "Takes over from your hand-recorded 50 bpm of 2021-01-01: the "
            "evidence differed by more than 3 bpm."
        ),
        confirmed=True,
    )
    maximum = _short_entry(
        _MAX,
        date(2021, 1, 2),
        175,
        "workouts",
        (
            "Takes over from your hand-recorded 170 bpm of 2021-01-01: the "
            "evidence differed by more than 2 bpm."
        ),
    )
    entries = (old_rest if rest_kept else rest, old_max if max_kept else maximum)
    changed = not (rest_kept and max_kept)
    report = engine.derive_hr_benchmarks(
        root, settings=settings, dry_run=dry_run, progress=callback
    )
    expected_calls = [
        ("load", root),
        ("write", entries, frozenset({_REST, _MAX}), True),
    ]
    if changed and not dry_run:
        expected_calls.append(("save", root))
    raw_after = cast(
        dict[str, dict[str, list[dict[str, object]]]],
        load_profile(root).data["benchmarks"],
    )
    kept_raw = tuple(
        raw_after["athlete"][kind.value][0]
        for kind, kept in ((_REST, rest_kept), (_MAX, max_kept))
        if kept
    )
    expected_kept_raw = tuple(
        cast(dict[str, dict[str, list[dict[str, object]]]], initial.data["benchmarks"])[
            "athlete"
        ][kind.value][0]
        for kind, kept in ((_REST, rest_kept), (_MAX, max_kept))
        if kept
    )
    assert (report, events, calls, kept_raw, _tree_changes(before, root)) == (
        HrStageReport(
            27,
            6,
            counts,
            skipped,
            ("z-source",),
            (
                KindOutcome(
                    _REST,
                    (entries[0],),
                    () if rest_kept else (rest,),
                    () if rest_kept else (old_rest,),
                    rest_kept,
                ),
                KindOutcome(
                    _MAX,
                    (entries[1],),
                    () if max_kept else (maximum,),
                    () if max_kept else (old_max,),
                    max_kept,
                ),
            ),
            tuple(
                t
                for t, kept in (
                    (Takeover(_MAX, maximum, hands[1]), max_kept),
                    (Takeover(_REST, rest, hands[0]), rest_kept),
                )
                if not kept
            ),
            (),
            (),
            rest_failure + max_failure,
            ("series note",),
            changed and not dry_run,
            changed,
        ),
        [
            ("profile", root),
            ("resting", root, True, frozenset({date(2021, 1, 1)})),
            ("workouts", root, True, frozenset({date(2021, 1, 1)}), True),
            ("progress", 23, 27),
        ],
        expected_calls,
        expected_kept_raw,
        ("athlete.toml",) if changed and not dry_run else (),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX], ids=["resting", "maximum"])
def test_stage_real_backreach_change_and_expansion(
    kind: BenchmarkKind, tmp_path: Path
) -> None:
    root = tmp_path / "backreach" / kind.value
    _basic_root(root)
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 1, 1) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                57,
                True,
            )
            for i in range(27)
        ),
    )
    af = date(2021, 2, 5) if kind is _MAX else date(2021, 1, 20)
    hand = Benchmark(
        kind, None, 50 if kind is _REST else 170, date(2021, 3, 1), applies_from=af
    )
    _seed_entries(root, (hand,))
    settings = engine.load_hr_stage_settings({}, data_root=root)
    before = _tree_snapshot(root)
    rest, maximum = _basic_entries()
    target = rest if kind is _REST else maximum
    rest, maximum = (target, maximum) if kind is _REST else (rest, target)
    after_cover = (af, af)
    expected_change = BackReachChange(kind, hand, (af, hand.measured_on), after_cover)
    preview = engine.derive_hr_benchmarks(root, settings=settings, dry_run=True)
    assert (
        preview.kinds,
        preview.takeovers,
        preview.back_reach_changes,
        preview.changed,
        preview.written,
        _tree_changes(before, root),
    ) == (
        (
            KindOutcome(_REST, (rest,), (rest,), (), False),
            KindOutcome(_MAX, (maximum,), (maximum,), (), False),
        ),
        (),
        (expected_change,),
        True,
        False,
        (),
    )
    writing = engine.derive_hr_benchmarks(root, settings=settings)
    saved = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        replace(writing, written=False),
        _tree_changes(before, root),
        repeated.takeovers,
        repeated.back_reach_changes,
        repeated.changed,
        _tree_changes(saved, root),
    ) == (
        preview,
        ("athlete.toml",),
        (),
        (),
        False,
        (),
    )
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 1),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    57,
                    True,
                ),
            ),
        )
    else:
        for page in (root / "workouts").glob("*.md"):
            page.unlink()
    cleared_before = _tree_snapshot(root)
    removal = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        removal.kinds[0 if kind is _REST else 1],
        removal.back_reach_changes,
        removal.takeovers,
        removal.changed,
        removal.written,
        _tree_changes(cleared_before, root),
    ) == (
        KindOutcome(kind, (), (), (target,), False),
        (BackReachChange(kind, hand, after_cover, (af, hand.measured_on)),),
        (),
        True,
        True,
        ("athlete.toml",),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX], ids=["resting", "maximum"])
def test_stage_real_evidence_inside_hand_cover_starts_nothing(
    kind: BenchmarkKind, tmp_path: Path
) -> None:
    root = tmp_path / "held-cover" / kind.value
    _basic_root(root)
    hand = Benchmark(
        kind,
        None,
        50 if kind is _REST else 170,
        date(2021, 3, 1),
        applies_from=date(2021, 1, 1),
    )
    _seed_entries(root, (hand,))
    rest, maximum = _basic_entries()
    other = maximum if kind is _REST else rest
    report = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    index = 0 if kind is _REST else 1
    assert (
        report.kinds[index],
        report.takeovers,
        report.back_reach_changes,
        frozenset(load_profile(root).benchmarks.entries),
    ) == (
        KindOutcome(kind, (), (), (), False),
        (),
        (),
        frozenset((hand, other)),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX], ids=["resting", "maximum"])
def test_stage_legacy_takeover_inside_cover_is_replaced_and_cover_widens(
    kind: BenchmarkKind, tmp_path: Path
) -> None:
    root = tmp_path / "legacy-cover" / kind.value
    _basic_root(root)
    hand = Benchmark(
        kind,
        None,
        50 if kind is _REST else 170,
        date(2021, 3, 1),
        applies_from=date(2021, 1, 1),
    )
    rest, maximum = _basic_entries()
    legacy = rest if kind is _REST else maximum
    other = maximum if kind is _REST else rest
    _seed_entries(root, (hand, legacy))
    report = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    index = 0 if kind is _REST else 1
    assert (
        report.kinds[index],
        report.takeovers,
        report.back_reach_changes,
        frozenset(load_profile(root).benchmarks.entries),
    ) == (
        KindOutcome(kind, (), (), (legacy,), False),
        (),
        (
            BackReachChange(
                kind,
                hand,
                (date(2021, 1, 1), legacy.measured_on),
                (date(2021, 1, 1), hand.measured_on),
            ),
        ),
        frozenset((hand, other)),
    )


def test_stage_new_hand_removes_unnecessary_entry(tmp_path: Path) -> None:
    root = tmp_path / "new-hand" / "distinct-library"
    _basic_root(root)
    rest, maximum = _basic_entries()
    hand = Benchmark(
        _MAX,
        None,
        162,
        date(2021, 2, 1),
        source=BenchmarkSource(BenchmarkSourceKind.MEASURED),
    )
    _seed_entries(root, (rest, maximum, hand))
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    assert (
        report.kinds,
        report.takeovers,
        report.changed,
        report.written,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        (
            KindOutcome(_REST, (rest,), (), (), False),
            KindOutcome(_MAX, (), (), (maximum,), False),
        ),
        (),
        True,
        True,
        frozenset((rest, hand)),
        ("athlete.toml",),
    )


@pytest.mark.parametrize(
    "other",
    ["none", "empty", "replacement"],
    ids=["existing-view", "clear-view", "future-accepted-view"],
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
def test_stage_consistency_substitution_preserves_other_entries(
    other: str, dry_run: bool, tmp_path: Path
) -> None:
    root = tmp_path / "substitution" / other
    _basic_root(root)
    rest, maximum = _basic_entries()
    derived_threshold = Benchmark(
        BenchmarkKind.LTHR_BPM,
        Sport.RUN,
        170,
        date(2021, 1, 1),
        source=BenchmarkSource(
            BenchmarkSourceKind.DERIVED,
            "tagged",
            "workouts/older.md",
            "old inputs",
            "old citation",
        ),
    )
    hand_threshold = Benchmark(
        BenchmarkKind.LTHR_BPM, Sport.RIDE, 165, date(2021, 1, 2)
    )
    future = replace(
        derived_threshold,
        value=50,
        measured_on=date(2021, 2, 9),
        applies_from=date(2021, 2, 3),
    )
    _seed_entries(root, (derived_threshold, hand_threshold))
    before = _tree_snapshot(root)
    accepted = None if other == "none" else () if other == "empty" else (future,)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
        other_derived=accepted,
    )
    finding = Inconsistency(
        Violation.THRESHOLD_OUTSIDE_RESERVE,
        date(2021, 2, 3),
        None,
        Sport.RUN,
        maximum,
        rest,
        derived_threshold if other == "none" else future,
    )
    saved_entries = frozenset(load_profile(root).benchmarks.entries)
    assert (
        report.inconsistencies,
        report.changed,
        report.written,
        saved_entries,
        _tree_changes(before, root),
    ) == (
        (
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                date(2021, 2, 3),
                None,
                Sport.RIDE,
                maximum,
                rest,
                hand_threshold,
            ),
        )
        + (() if other == "empty" else (finding,)),
        True,
        not dry_run,
        frozenset(
            (derived_threshold, hand_threshold)
            if dry_run
            else (rest, maximum, hand_threshold, derived_threshold)
        ),
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize(
    "old_difference", ["provenance", "numeric", "date", "earlier-derived"]
)
def test_stage_takeovers_use_structural_identity(
    old_difference: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "takeovers" / old_difference
    root.mkdir(parents=True)
    hand = Benchmark(_MAX, None, 170, date(2021, 1, 1))
    new = _short_entry(
        _MAX,
        date(2021, 1, 4),
        175,
        "workouts",
        (
            "Takes over from your hand-recorded 170 bpm of 2021-01-01: the "
            "evidence differed by more than 2 bpm."
        ),
    )
    old = replace(
        new,
        note="older derivation",
        source=replace(
            cast(BenchmarkSource, new.source), document="different/old-page.md"
        ),
    )
    if old_difference == "numeric":
        old = replace(old, value=176)
    elif old_difference == "date":
        old = replace(old, measured_on=date(2021, 1, 5))
    earlier = replace(old, measured_on=date(2021, 1, 2), value=180)
    _seed_entries(
        root,
        (hand, old, earlier) if old_difference == "earlier-derived" else (hand, old),
    )
    monkeypatch.setattr(
        engine,
        "_read_workout_sessions",
        lambda *args, **kwargs: engine._WorkoutSessions(
            (_short_evidence(date(2021, 1, 4), 175),),
            3,
            3,
            _reason_counts(),
            (),
            (),
            False,
        ),
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    assert (
        report.takeovers,
        report.kinds[1].entries,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (
        () if old_difference == "provenance" else (Takeover(_MAX, new, hand),),
        (new,),
        True,
        True,
        ("athlete.toml",),
    )
    saved = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    assert (
        repeated.takeovers,
        repeated.changed,
        repeated.written,
        _tree_changes(saved, root),
    ) == ((), False, False, ())


@pytest.mark.parametrize(
    "dimension", ["kind", "derived-date", "value", "hand-date", "provenance"]
)
def test_stage_takeover_key_dimensions(dimension: str) -> None:
    derived = _basic_entries()[1]
    hand = Benchmark(_MAX, None, 170, date(2021, 1, 1))
    reference = (_MAX, date(2021, 2, 3), 163, date(2021, 1, 1))
    if dimension == "kind":
        derived = replace(derived, kind=_REST)
    elif dimension == "derived-date":
        derived = replace(derived, measured_on=date(2021, 2, 4))
    elif dimension == "value":
        derived = replace(derived, value=164)
    elif dimension == "hand-date":
        hand = replace(hand, measured_on=date(2021, 1, 2))
    else:
        derived = replace(derived, note="different provenance note")
    key = engine._takeover_key(Takeover(derived.kind, derived, hand))
    assert (key, key == reference) == (
        (derived.kind, derived.measured_on, derived.value, hand.measured_on),
        dimension == "provenance",
    )


def test_stage_resting_sources_first_use_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "sources" / "ordered-evidence"
    _basic_root(root)
    settings = engine.load_hr_stage_settings(
        {"wellness": {"precedence": ["garmin-export", "intervals-icu"]}},
        data_root=root,
    )
    evidence = tuple(
        _short_evidence(date(2021, 3, 1) + timedelta(days=i), 64, key)
        for i, key in enumerate(("intervals-icu", "garmin-export", "intervals-icu"))
    )
    monkeypatch.setattr(
        engine,
        "_read_resting_series",
        lambda *args: engine._RestingSeries(evidence, False, (), ()),
    )
    report = engine.derive_hr_benchmarks(root, settings=settings, dry_run=True)
    assert (
        settings.resting_order,
        tuple(item.key for item in evidence),
        report.resting_sources,
    ) == (
        ("garmin-export", "intervals-icu", "apple-health"),
        ("intervals-icu", "garmin-export", "intervals-icu"),
        ("intervals-icu", "garmin-export"),
    )


@pytest.mark.parametrize("profile_state", ["absent", "empty", "malformed"])
def test_stage_empty_profile_and_profile_errors(
    profile_state: str, tmp_path: Path
) -> None:
    root = tmp_path / "empty" / profile_state
    root.mkdir(parents=True)
    path = root / "athlete.toml"
    if profile_state != "absent":
        path.write_text("[[" if profile_state == "malformed" else "", encoding="utf-8")
    before = _tree_snapshot(root)
    result: HrStageReport | None = None
    error: Exception | None = None
    try:
        result = engine.derive_hr_benchmarks(
            root, settings=engine.load_hr_stage_settings({}, data_root=root)
        )
    except Exception as exc:
        error = exc
    expected = HrStageReport(
        0,
        0,
        _reason_counts(),
        (),
        (),
        (KindOutcome(_REST, (), (), (), True), KindOutcome(_MAX, (), (), (), False)),
        (),
        (),
        (),
        (),
        (_EMPTY_SERIES_NOTE,),
        False,
        False,
    )
    assert (result, type(error), str(error), _tree_changes(before, root)) == (
        None if profile_state == "malformed" else expected,
        ProfileError if profile_state == "malformed" else type(None),
        (
            f"{path} is not valid TOML: Invalid initial character for a key "
            f"part (at end of document)"
        )
        if profile_state == "malformed"
        else "None",
        (),
    )


def test_stage_facade_exports_working_entrypoint(tmp_path: Path) -> None:
    import fitdocs.hr_benchmarks as facade

    settings = facade.load_hr_stage_settings({}, data_root=tmp_path)
    report = facade.derive_hr_benchmarks(tmp_path, settings=settings)
    assert (facade.__all__, type(settings), type(report), report.changed) == (
        [
            "HrStageReport",
            "HrStageSettings",
            "derive_hr_benchmarks",
            "load_hr_stage_settings",
        ],
        facade.HrStageSettings,
        facade.HrStageReport,
        False,
    )


@pytest.mark.parametrize("kind", [_REST, _MAX], ids=["resting", "maximum"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
def test_stage_real_failure_retains_one_kind_and_updates_other(
    kind: BenchmarkKind, dry_run: bool, tmp_path: Path
) -> None:
    if os.geteuid() == 0 and kind is _MAX:
        pytest.skip("root can read files without permission bits")
    root = tmp_path / "failures" / kind.value
    _basic_root(root)
    entries = _basic_entries()
    old_entries = tuple(
        replace(e, value=e.value + 17, applies_from=date(2021, 1, 1)) for e in entries
    )
    _seed_entries(root, old_entries)
    unreadable: Path | None = None
    if kind is _REST:
        manifest = root / "wellness/manifest.toml"
        manifest.write_bytes(b"\xff")
        failures = (
            HrFailure(
                _REST,
                "wellness/manifest.toml",
                f"{manifest}: invalid manifest: "
                "'utf-8' codec can't decode byte 0xff in position 0: "
                "invalid start byte",
            ),
        )
    else:
        ref = _workout_archive(root, _session_fit(197))
        _workout_page(root, "y-unreadable.md", [ref])
        unreadable = root / ref
        failures = (
            HrFailure(
                _MAX,
                "workouts/y-unreadable.md",
                f"[Errno 13] Permission denied: '{unreadable}'",
            ),
        )
    before = _tree_snapshot(root)
    if unreadable is not None:
        unreadable.chmod(0)
    try:
        report = engine.derive_hr_benchmarks(
            root,
            settings=engine.load_hr_stage_settings({}, data_root=root),
            dry_run=dry_run,
        )
    finally:
        if unreadable is not None:
            unreadable.chmod(0o600)
    after_entries = tuple(
        old if old.kind is kind else fresh
        for old, fresh in zip(old_entries, entries, strict=True)
    )
    assert (
        report,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        HrStageReport(
            3 if kind is _REST else 4,
            3,
            _reason_counts(),
            (),
            () if kind is _REST else ("garmin-export",),
            tuple(
                KindOutcome(
                    fresh.kind,
                    (after,),
                    () if fresh.kind is kind else (fresh,),
                    () if fresh.kind is kind else (old,),
                    fresh.kind is kind,
                )
                for old, fresh, after in zip(
                    old_entries, entries, after_entries, strict=True
                )
            ),
            (),
            (),
            (),
            failures,
            (),
            not dry_run,
            True,
        ),
        frozenset(old_entries if dry_run else after_entries),
        () if dry_run else ("athlete.toml",),
    )


def test_stage_real_all_reason_counts_and_progress(tmp_path: Path) -> None:
    root = tmp_path / "reasons" / "whole-stage"
    _basic_root(root)
    for name, bpm, duration, locked in (
        ("f-no-hr.md", None, 40, False),
        ("g-lock.md", 170, 400, True),
        ("h-short.md", 153, 20, False),
    ):
        _workout_page(
            root,
            name,
            [
                _workout_archive(
                    root, _session_fit(bpm, duration=duration, locked=locked)
                )
            ],
        )
    _workout_page(root, "d-undated.md", [], day=None)
    _workout_page(root, "b-missing.md", ["fit-archive/aa0011.fit"])
    _workout_page(
        root, "a-corrupt.md", [_workout_archive(root, builder.non_fit_bytes())]
    )
    before = _tree_snapshot(root)
    progress: list[tuple[int, int]] = []
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=True,
        progress=lambda done, total: progress.append((done, total)),
    )
    assert (
        report.considered,
        report.with_evidence,
        report.no_evidence,
        report.skipped,
        report.failures,
        progress,
        _tree_changes(before, root),
    ) == (
        9,
        3,
        _reason_counts(
            undated=1,
            archive_missing=1,
            archive_undecodable=1,
            no_heart_rate=1,
            cadence_locked=1,
            no_sustained_stretch=1,
        ),
        (
            SkippedDocument(
                "workouts/a-corrupt.md",
                NoEvidenceReason.ARCHIVE_UNDECODABLE,
                "Source is not a FIT file: header check failed.",
            ),
            SkippedDocument(
                "workouts/b-missing.md",
                NoEvidenceReason.ARCHIVE_MISSING,
                "archived source not found",
            ),
        ),
        (),
        [(i, 9) for i in range(1, 10)],
        (),
    )


def test_stage_parsed_overlay_result_controls_change_and_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "parsed-overlay" / "athlete-library"
    _basic_root(root)
    entries = _basic_entries()
    _seed_entries(root, entries)
    before = _tree_snapshot(root)
    calls = _track_profile_calls(monkeypatch)

    def without_note(
        rule: KindRule, evidence: Sequence[Evidence], recorded: Sequence[Benchmark]
    ) -> TimelineResult:
        result = derive_timeline(rule, evidence, recorded)
        return replace(
            result, entries=tuple(replace(entry, note=None) for entry in result.entries)
        )

    monkeypatch.setattr(engine, "derive_timeline", without_note)
    report = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    assert (report, calls, _tree_changes(before, root)) == (
        HrStageReport(
            3,
            3,
            _reason_counts(),
            (),
            ("garmin-export",),
            tuple(
                KindOutcome(entry.kind, (entry,), (), (), False) for entry in entries
            ),
            (),
            (),
            (),
            (),
            (),
            False,
            False,
        ),
        [
            ("load", root),
            (
                "write",
                tuple(replace(entry, note=None) for entry in entries),
                frozenset({_REST, _MAX}),
                True,
            ),
        ],
        (),
    )


@pytest.mark.parametrize("median", [190, 199], ids=["agrees", "disagrees"])
def test_stage_real_evidence_after_backreach_hand_date(
    median: int, tmp_path: Path
) -> None:
    root = tmp_path / "after-hand" / str(median)
    _basic_root(root)
    hand = Benchmark(_MAX, None, 190, date(2021, 3, 1), applies_from=date(2021, 1, 1))
    _seed_entries(root, (hand,))
    settings = engine.load_hr_stage_settings({}, data_root=root)
    engine.derive_hr_benchmarks(root, settings=settings)
    for name, bpm in (
        ("a-future-high.md", 207),
        ("b-future-median.md", median),
        ("c-future-low.md", 185),
    ):
        _workout_page(
            root, name, [_workout_archive(root, _session_fit(bpm))], day="2021-03-02"
        )
    before = _tree_snapshot(root)
    target = Benchmark(
        _MAX,
        None,
        199,
        date(2021, 3, 2),
        note=(
            "Takes over from your hand-recorded 190 bpm of 2021-03-01: "
            "the evidence differed by more than 2 bpm."
        ),
        source=BenchmarkSource(
            BenchmarkSourceKind.DERIVED,
            "max_hr_sustained_peak",
            "workouts/b-future-median.md",
            (
                "median of the three highest 30-second sustained peaks "
                "(207.0, 199.0, 185.0 bpm) "
                "among 3 sessions dated 2021-03-02 to 2021-03-02"
            ),
            "max_hr_timeline_choice",
        ),
    )
    report = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        report.takeovers,
        report.back_reach_changes,
        report.kinds[1].added,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (
        (Takeover(_MAX, target, hand),) if median == 199 else (),
        (),
        (target,) if median == 199 else (),
        median == 199,
        median == 199,
        ("athlete.toml",) if median == 199 else (),
    )


def test_stage_reports_each_changed_hand_cover(tmp_path: Path) -> None:
    root = tmp_path / "many-hands" / "two-kind-library"
    _basic_root(root)
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 1, 1) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                57,
                True,
            )
            for i in range(27)
        ),
    )
    rest_hand = Benchmark(
        _REST, None, 50, date(2021, 3, 1), applies_from=date(2021, 1, 1)
    )
    max_hand = Benchmark(
        _MAX, None, 190, date(2021, 3, 2), applies_from=date(2021, 1, 2)
    )
    legacy_rest, legacy_max = _basic_entries()
    _seed_entries(root, (rest_hand, max_hand, legacy_rest, legacy_max))
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    assert (
        report.back_reach_changes,
        tuple(
            (t.kind, t.derived.measured_on, t.derived.value, t.superseded)
            for t in report.takeovers
        ),
        _tree_changes(before, root),
    ) == (
        (
            BackReachChange(
                _MAX,
                max_hand,
                (date(2021, 1, 2), legacy_max.measured_on),
                (date(2021, 1, 2), date(2021, 3, 2)),
            ),
            BackReachChange(
                _REST,
                rest_hand,
                (date(2021, 1, 1), legacy_rest.measured_on),
                (date(2021, 1, 1), date(2021, 3, 1)),
            ),
        ),
        (),
        ("athlete.toml",),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("rest_state", ["absent", "empty", "other", "failed"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_retained_cardinality(
    kind: BenchmarkKind, count: int, rest_state: str, dry_run: bool, tmp_path: Path
) -> None:
    if os.geteuid() == 0 and kind is _MAX:
        pytest.skip("root can read files without permission bits")
    root = tmp_path / "retained"
    _basic_root(root)
    entries = tuple(
        replace(
            _short_entry(
                kind,
                date(2020, 12, 1) + timedelta(days=i),
                (72, 68, 81)[i] if kind is _REST else (181, 193, 175)[i],
                f"retained-{i}",
                f"retained note {i}",
            ),
            applies_from=date(2020, 11, 1) + timedelta(days=2 * i),
        )
        for i in range(count)
    )
    data = benchmarks_to_document(entries)
    table = cast(dict[str, dict[str, list[dict[str, object]]]], data["benchmarks"])
    raw_entries = table.get("athlete", {}).get(kind.value, [])
    for i, raw in enumerate(raw_entries):
        raw["future_entry"] = [f"entry-{i}-z", f"entry-{i}-a"]
        cast(dict[str, object], raw["source"])["future_source"] = f"source-{i}-m"
    save_profile(root, AthleteProfile(data))
    failures: tuple[HrFailure, ...] = ()
    notes: tuple[str, ...] = ()
    unreadable: Path | None = None
    if kind is _REST:
        if rest_state == "absent":
            for path in (root / "wellness").glob("*"):
                path.unlink()
        elif rest_state == "empty":
            write_series(root, ())
        elif rest_state == "other":
            write_series(
                root,
                (
                    SeriesValue(
                        date(2021, 1, 1),
                        Metric.STEPS,
                        "garmin-export",
                        None,
                        8251,
                        True,
                    ),
                ),
            )
        else:
            manifest = root / "wellness/manifest.toml"
            manifest.write_bytes(b"\xff")
            failures = (
                HrFailure(
                    _REST,
                    "wellness/manifest.toml",
                    f"{manifest}: invalid manifest: "
                    "'utf-8' codec can't decode byte 0xff in position 0: "
                    "invalid start byte",
                ),
            )
        if rest_state != "failed":
            notes = (
                "the wellness series holds no resting heart rate; "
                "derived resting entries kept as on file",
            )
    else:
        ref = _workout_archive(root, _session_fit(197))
        _workout_page(root, "y-unreadable.md", [ref])
        unreadable = root / ref
        failures = (
            HrFailure(
                _MAX,
                "workouts/y-unreadable.md",
                f"[Errno 13] Permission denied: '{unreadable}'",
            ),
        )
    before = _tree_snapshot(root)
    if unreadable is not None:
        unreadable.chmod(0)
    try:
        report = engine.derive_hr_benchmarks(
            root,
            settings=engine.load_hr_stage_settings({}, data_root=root),
            dry_run=dry_run,
        )
    finally:
        if unreadable is not None:
            unreadable.chmod(0o600)
    saved = load_profile(root)
    saved_table = cast(
        dict[str, dict[str, list[dict[str, object]]]], saved.data["benchmarks"]
    )
    fresh = _basic_entries()[1 if kind is _REST else 0]
    expected_kinds = (
        KindOutcome(
            _REST,
            entries if kind is _REST else (fresh,),
            () if kind is _REST else (fresh,),
            (),
            kind is _REST,
        ),
        KindOutcome(
            _MAX,
            entries if kind is _MAX else (fresh,),
            () if kind is _MAX else (fresh,),
            (),
            kind is _MAX,
        ),
    )
    assert (
        report.kinds,
        report.failures,
        report.notes,
        report.changed,
        report.written,
        saved_table.get("athlete", {}).get(kind.value, []),
        frozenset(saved.benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected_kinds,
        failures,
        notes,
        True,
        not dry_run,
        raw_entries,
        frozenset(entries if dry_run else (*entries, fresh)),
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_two_same_kind_changed_covers(
    kind: BenchmarkKind, origin: BenchmarkSource | None, dry_run: bool, tmp_path: Path
) -> None:
    root = tmp_path / "covers"
    _basic_root(root)
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 8) + timedelta(days=i),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    57,
                    True,
                )
                for i in range(27)
            ),
        )
    first_start = date(2021, 2, 10)
    first = Benchmark(
        kind,
        None,
        50 if kind is _REST else 170,
        date(2021, 3, 1),
        applies_from=first_start,
        source=origin,
    )
    second = Benchmark(
        kind,
        None,
        49 if kind is _REST else 189,
        date(2021, 3, 2),
        applies_from=date(2021, 2, 5),
        source=origin,
    )
    _seed_entries(root, (first, second))
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    expected = (
        BackReachChange(
            kind, first, (first_start, first.measured_on), (first_start, first_start)
        ),
        BackReachChange(
            kind,
            second,
            (date(2021, 2, 5), first_start),
            (date(2021, 2, 5), date(2021, 2, 5)),
        ),
    )
    assert (report.back_reach_changes, _tree_changes(before, root)) == (
        expected,
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize(
    "rest_state", ["absent", "empty", "unformed", "formed", "failed"]
)
@pytest.mark.parametrize("max_state", ["empty", "unformed", "formed", "failed"])
@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_cross_partition_matrix(
    rest_state: str,
    max_state: str,
    count: int,
    origin: BenchmarkSource | None,
    dry_run: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    root = tmp_path / "matrix"
    root.mkdir()
    hands = (
        Benchmark(_REST, None, 50, date(2021, 1, 1), source=origin),
        Benchmark(_MAX, None, 170, date(2021, 1, 1), source=origin),
    )
    old_rest = tuple(
        replace(
            _short_entry(
                _REST, date(2020, 12, 1) + timedelta(days=i), 72 + i, "old-rest", "kept"
            ),
            applies_from=date(2020, 11, 1),
        )
        for i in range(count)
    )
    old_max = tuple(
        replace(
            _short_entry(
                _MAX, date(2020, 12, 11) + timedelta(days=i), 181 + i, "old-max", "kept"
            ),
            applies_from=date(2020, 11, 2),
        )
        for i in range(3 - count)
    )
    _seed_entries(root, (*hands, *old_rest, *old_max))
    rest_kept = rest_state in {"absent", "empty", "failed"}
    max_kept = max_state == "failed"
    rest_ev = (
        tuple(
            _short_evidence(date(2021, 1, 2) + timedelta(days=i), 61, "z-source")
            for i in range(14)
        )
        if rest_state == "formed"
        else ()
    )
    max_ev = (
        (_short_evidence(date(2021, 1, 2), 175),)
        if max_state in {"formed", "failed"}
        else ()
    )
    rest_fail = (
        (HrFailure(_REST, "wellness/manifest.toml", "rest failure"),)
        if rest_state == "failed"
        else ()
    )
    max_fail = (
        (HrFailure(_MAX, "workouts/fail.md", "max failure"),)
        if max_state == "failed"
        else ()
    )
    notes = (
        (
            "the wellness series holds no resting heart rate; "
            "derived resting entries kept as on file",
        )
        if rest_state in {"absent", "empty"}
        else ()
    )
    monkeypatch.setattr(
        engine,
        "_read_resting_series",
        lambda *a: engine._RestingSeries(rest_ev, rest_kept, rest_fail, notes),
    )
    monkeypatch.setattr(
        engine,
        "_read_workout_sessions",
        lambda *a, **kw: engine._WorkoutSessions(
            max_ev,
            27,
            6,
            _reason_counts(
                undated=1,
                archive_missing=2,
                archive_undecodable=3,
                no_heart_rate=4,
                cadence_locked=5,
                no_sustained_stretch=6,
            ),
            (),
            max_fail,
            max_kept,
        ),
    )
    rest_new = (
        (
            _short_entry(
                _REST,
                date(2021, 1, 2),
                61,
                "z-source",
                "Takes over from your hand-recorded 50 bpm of 2021-01-01: "
                "the evidence differed by more than 3 bpm.",
                confirmed=True,
            ),
        )
        if rest_state == "formed"
        else ()
    )
    max_new = (
        (
            _short_entry(
                _MAX,
                date(2021, 1, 2),
                175,
                "workouts",
                "Takes over from your hand-recorded 170 bpm of 2021-01-01: "
                "the evidence differed by more than 2 bpm.",
            ),
        )
        if max_state == "formed"
        else ()
    )
    after_rest = old_rest if rest_kept else rest_new
    after_max = old_max if max_kept else max_new
    expected = (
        KindOutcome(
            _REST,
            after_rest,
            () if rest_kept else rest_new,
            () if rest_kept else old_rest,
            rest_kept,
        ),
        KindOutcome(
            _MAX,
            after_max,
            () if max_kept else max_new,
            () if max_kept else old_max,
            max_kept,
        ),
    )
    changed = after_rest != old_rest or after_max != old_max
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    saved = frozenset(load_profile(root).benchmarks.entries)
    assert (
        report.kinds,
        report.failures,
        report.notes,
        report.resting_sources,
        report.changed,
        report.written,
        saved,
        _tree_changes(before, root),
    ) == (
        expected,
        rest_fail + max_fail,
        notes,
        ("z-source",) if rest_ev else (),
        changed,
        changed and not dry_run,
        frozenset(
            (*hands, *old_rest, *old_max)
            if dry_run
            else (*hands, *after_rest, *after_max)
        ),
        ("athlete.toml",) if changed and not dry_run else (),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_multiple_new_takeovers_same_kind(
    kind: BenchmarkKind,
    origin: BenchmarkSource | None,
    dry_run: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    root = tmp_path / "history"
    root.mkdir()
    first = Benchmark(
        kind, None, 50 if kind is _REST else 170, date(2021, 1, 1), source=origin
    )
    second = Benchmark(
        kind, None, 55 if kind is _REST else 185, date(2021, 1, 20), source=origin
    )
    _seed_entries(root, (first, second))
    evidence = tuple(
        _short_evidence(
            date(2021, 1, 2) + timedelta(days=i),
            61 if kind is _REST else 175,
            "z-source" if kind is _REST else "workouts",
        )
        for i in range(14 if kind is _REST else 1)
    ) + tuple(
        _short_evidence(
            date(2021, 1, 21) + timedelta(days=i),
            70 if kind is _REST else 200,
            "z-source" if kind is _REST else "workouts",
        )
        for i in range(14 if kind is _REST else 1)
    )
    if kind is _REST:
        monkeypatch.setattr(
            engine,
            "_read_resting_series",
            lambda *a: engine._RestingSeries(evidence, False, (), ()),
        )
    else:
        monkeypatch.setattr(
            engine,
            "_read_workout_sessions",
            lambda *a, **kw: engine._WorkoutSessions(
                evidence, 6, 6, _reason_counts(), (), (), False
            ),
        )
    first_derived = _short_entry(
        kind,
        date(2021, 1, 2),
        61 if kind is _REST else 175,
        "z-source" if kind is _REST else "workouts",
        f"Takes over from your hand-recorded {first.value:g} bpm of 2021-01-01: "
        f"the evidence differed by more than {3 if kind is _REST else 2} bpm.",
        confirmed=kind is _REST,
    )
    second_derived = _short_entry(
        kind,
        date(2021, 1, 21),
        70 if kind is _REST else 200,
        "z-source" if kind is _REST else "workouts",
        f"Takes over from your hand-recorded {second.value:g} bpm of 2021-01-20: "
        f"the evidence differed by more than {3 if kind is _REST else 2} bpm.",
        confirmed=kind is _REST,
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    assert (
        report.takeovers,
        report.kinds[0 if kind is _REST else 1].added,
        _tree_changes(before, root),
    ) == (
        (Takeover(kind, first_derived, first), Takeover(kind, second_derived, second)),
        (first_derived, second_derived),
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_generated_cardinality(
    kind: BenchmarkKind,
    count: int,
    origin: BenchmarkSource | None,
    dry_run: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    root = tmp_path / "generated"
    root.mkdir()
    hand_days = (date(2021, 1, 1), date(2021, 2, 1), date(2021, 3, 1))
    hand_values = (50, 55, 60) if kind is _REST else (170, 165, 160)
    values = (61, 79, 70) if kind is _REST else (175, 210, 200)
    hands = tuple(
        Benchmark(kind, None, v, d, source=origin)
        for d, v in zip(hand_days, hand_values, strict=True)
    )
    _seed_entries(root, hands)
    evidence = tuple(
        _short_evidence(
            d + timedelta(days=1 + i), v, "z-source" if kind is _REST else "workouts"
        )
        for d, v in zip(hand_days[:count], values[:count], strict=True)
        for i in range(14 if kind is _REST else 1)
    )
    if kind is _REST:
        monkeypatch.setattr(
            engine,
            "_read_resting_series",
            lambda *a: engine._RestingSeries(evidence, False, (), ()),
        )
    else:
        monkeypatch.setattr(
            engine,
            "_read_workout_sessions",
            lambda *a, **kw: engine._WorkoutSessions(
                evidence, count, count, _reason_counts(), (), (), False
            ),
        )
    entries = tuple(
        _short_entry(
            kind,
            d + timedelta(days=1),
            v,
            "z-source" if kind is _REST else "workouts",
            f"Takes over from your hand-recorded {hand.value:g} bpm of {d}: "
            f"the evidence differed by more than {3 if kind is _REST else 2} bpm.",
            confirmed=kind is _REST,
        )
        for d, v, hand in zip(
            hand_days[:count], values[:count], hands[:count], strict=True
        )
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    assert (
        report.kinds[0 if kind is _REST else 1],
        report.takeovers,
        report.changed,
        report.written,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        KindOutcome(kind, entries, entries, (), False),
        tuple(
            Takeover(kind, e, h) for e, h in zip(entries, hands[:count], strict=True)
        ),
        bool(count),
        bool(count) and not dry_run,
        frozenset(hands if dry_run else (*hands, *entries)),
        ("athlete.toml",) if count and not dry_run else (),
    )
    if dry_run:
        engine.derive_hr_benchmarks(
            root, settings=engine.load_hr_stage_settings({}, data_root=root)
        )
    saved = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(
        root, settings=engine.load_hr_stage_settings({}, data_root=root)
    )
    assert (
        repeated.kinds[0 if kind is _REST else 1],
        repeated.takeovers,
        repeated.back_reach_changes,
        repeated.changed,
        repeated.written,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(saved, root),
    ) == (
        KindOutcome(kind, entries, (), (), False),
        (),
        (),
        False,
        False,
        frozenset((*hands, *entries)),
        (),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("later_valid", [False, True])
def test_stage_repair_accepted_cardinality(
    count: int,
    dry_run: bool,
    later_valid: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitdocs.benchmarks import BenchmarkSet
    from fitdocs.hr_benchmarks.inspect import inconsistencies

    root = tmp_path / "accepted"
    _basic_root(root)
    source = BenchmarkSource(
        BenchmarkSourceKind.DERIVED,
        "tagged",
        "workouts/old.md",
        "old inputs",
        "old citation",
    )
    old = tuple(
        Benchmark(k, s, v, date(2020, 1, 1), source=source)
        for k, s, v in (
            (BenchmarkKind.LTHR_BPM, Sport.RUN, 180),
            (BenchmarkKind.FTP_WATTS, Sport.RIDE, 240),
            (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 330),
        )
    )
    hand = Benchmark(BenchmarkKind.LTHR_BPM, Sport.RIDE, 160, date(2021, 1, 1))
    _seed_entries(root, (*old, hand))
    accepted = (
        Benchmark(
            BenchmarkKind.LTHR_BPM, Sport.RUN, 170, date(2021, 2, 4), source=source
        ),
        Benchmark(
            BenchmarkKind.LTHR_BPM,
            Sport.RUN,
            160 if later_valid else 180,
            date(2021, 2, 10),
            source=source,
        ),
        Benchmark(
            BenchmarkKind.LTHR_BPM, Sport.RIDE, 50, date(2021, 2, 6), source=source
        ),
    )[:count]
    views: list[frozenset[Benchmark]] = []

    def inspect(view: BenchmarkSet) -> tuple[Inconsistency, ...]:
        views.append(frozenset(view.entries))
        return inconsistencies(view)

    monkeypatch.setattr(engine, "inconsistencies", inspect)
    rest, mx = _basic_entries()
    expected: tuple[Inconsistency, ...] = (
        ()
        if count == 0
        else (
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                date(2021, 2, 4),
                None if count == 1 else date(2021, 2, 10),
                Sport.RUN,
                mx,
                rest,
                accepted[0],
            ),
        )
    )
    if count == 3:
        expected += (
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                date(2021, 2, 6),
                None,
                Sport.RIDE,
                mx,
                rest,
                accepted[2],
            ),
        )
    if count >= 2 and not later_valid:
        expected += (
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                date(2021, 2, 10),
                None,
                Sport.RUN,
                mx,
                rest,
                accepted[1],
            ),
        )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
        other_derived=accepted,
    )
    assert (
        report.inconsistencies,
        views,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected,
        [frozenset((rest, mx, hand, *accepted))],
        frozenset((*old, hand) if dry_run else (*old, hand, rest, mx)),
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_real_multiple_failures(
    count: int, dry_run: bool, tmp_path: Path
) -> None:

    if os.geteuid() == 0:
        pytest.skip("permission bits need nonroot")
    root = tmp_path / "failures"
    _basic_root(root)
    rest, mx = _basic_entries()
    old = replace(mx, value=181)
    _seed_entries(root, (replace(rest, value=74), old))
    paths = []
    for i in range(count):
        ref = _workout_archive(root, _session_fit(190 + i))
        _workout_page(root, f"a-fail-{i}.md", [ref])
        paths.append(root / ref)
    before = _tree_snapshot(root)
    progress = []
    for p in paths:
        p.chmod(0)
    try:
        report = engine.derive_hr_benchmarks(
            root,
            settings=engine.load_hr_stage_settings({}, data_root=root),
            dry_run=dry_run,
            progress=lambda d, t: progress.append((d, t)),
        )
    finally:
        for p in paths:
            p.chmod(0o600)
    expected = tuple(
        HrFailure(
            _MAX, f"workouts/a-fail-{i}.md", f"[Errno 13] Permission denied: '{p}'"
        )
        for i, p in enumerate(paths)
    )
    changed = True
    assert (
        report.failures,
        report.considered,
        report.with_evidence,
        report.no_evidence,
        report.kinds,
        frozenset(load_profile(root).benchmarks.entries),
        progress,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (
        expected,
        3 + count,
        3,
        _reason_counts(),
        (
            KindOutcome(_REST, (rest,), (rest,), (replace(rest, value=74),), False),
            KindOutcome(
                _MAX,
                (old,) if count else (mx,),
                () if count else (mx,),
                () if count else (old,),
                bool(count),
            ),
        ),
        frozenset(
            (replace(rest, value=74), old) if dry_run else (rest, old if count else mx)
        ),
        [(i, 3 + count) for i in range(1, 4 + count)],
        changed,
        changed and not dry_run,
        ("athlete.toml",) if changed and not dry_run else (),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_later_hand_agreement_suppresses_entry(
    kind: BenchmarkKind,
    origin: BenchmarkSource | None,
    dry_run: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    root = tmp_path / "agreement"
    root.mkdir()
    first = Benchmark(
        kind, None, 50 if kind is _REST else 170, date(2021, 1, 1), source=origin
    )
    second = Benchmark(
        kind, None, 70 if kind is _REST else 200, date(2021, 1, 20), source=origin
    )
    _seed_entries(root, (first, second))
    evidence = tuple(
        _short_evidence(
            date(2021, 1, 2) + timedelta(days=i),
            61 if kind is _REST else 175,
            "z-source" if kind is _REST else "workouts",
        )
        for i in range(14 if kind is _REST else 1)
    ) + tuple(
        _short_evidence(
            date(2021, 1, 21) + timedelta(days=i),
            70 if kind is _REST else 200,
            "z-source" if kind is _REST else "workouts",
        )
        for i in range(14 if kind is _REST else 1)
    )
    if kind is _REST:
        monkeypatch.setattr(
            engine,
            "_read_resting_series",
            lambda *a: engine._RestingSeries(evidence, False, (), ()),
        )
    else:
        monkeypatch.setattr(
            engine,
            "_read_workout_sessions",
            lambda *a, **kw: engine._WorkoutSessions(
                evidence, 6, 6, _reason_counts(), (), (), False
            ),
        )
    target = _short_entry(
        kind,
        date(2021, 1, 2),
        61 if kind is _REST else 175,
        "z-source" if kind is _REST else "workouts",
        f"Takes over from your hand-recorded {first.value:g} bpm of 2021-01-01: "
        f"the evidence differed by more than {3 if kind is _REST else 2} bpm.",
        confirmed=kind is _REST,
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    assert (
        report.kinds[0 if kind is _REST else 1].entries,
        report.takeovers,
        _tree_changes(before, root),
    ) == (
        (target,),
        (Takeover(kind, target, first),),
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_real_multiple_skips(
    count: int, dry_run: bool, tmp_path: Path
) -> None:

    root = tmp_path / "skips"
    root.mkdir()
    for i in range(count):
        _workout_page(root, f"a-missing-{i}.md", ["fit-archive/aa0011.fit"])
    before = _tree_snapshot(root)
    progress = []
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
        progress=lambda d, t: progress.append((d, t)),
    )
    skipped = tuple(
        SkippedDocument(
            f"workouts/a-missing-{i}.md",
            NoEvidenceReason.ARCHIVE_MISSING,
            "archived source not found",
        )
        for i in range(count)
    )
    assert (
        report.skipped,
        report.no_evidence,
        report.considered,
        report.with_evidence,
        report.failures,
        progress,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (
        skipped,
        _reason_counts(archive_missing=count),
        count,
        0,
        (),
        [(i, count) for i in range(1, count + 1)],
        False,
        False,
        (),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_same_kind_cover_expansion_and_noop(
    kind: BenchmarkKind, origin: BenchmarkSource | None, dry_run: bool, tmp_path: Path
) -> None:

    root = tmp_path / "expansion"
    _basic_root(root)
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 1, 8) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                57,
                True,
            )
            for i in range(27)
        ),
    )
    first_start = date(2021, 2, 10)
    first = Benchmark(
        kind,
        None,
        50 if kind is _REST else 170,
        date(2021, 3, 1),
        applies_from=first_start,
        source=origin,
    )
    second = Benchmark(
        kind,
        None,
        49 if kind is _REST else 189,
        date(2021, 3, 2),
        applies_from=date(2021, 2, 5),
        source=origin,
    )
    _seed_entries(root, (first, second))
    settings = engine.load_hr_stage_settings({}, data_root=root)
    engine.derive_hr_benchmarks(root, settings=settings)
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 1),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    57,
                    True,
                ),
            ),
        )
    else:
        for page in (root / "workouts").glob("*.md"):
            page.unlink()
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(root, settings=settings, dry_run=dry_run)
    expected = (
        BackReachChange(
            kind, first, (first_start, first_start), (first_start, first.measured_on)
        ),
        BackReachChange(
            kind,
            second,
            (date(2021, 2, 5), date(2021, 2, 5)),
            (date(2021, 2, 5), first_start),
        ),
    )
    assert (
        report.back_reach_changes,
        report.kinds[0 if kind is _REST else 1].entries,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (expected, (), True, not dry_run, () if dry_run else ("athlete.toml",))
    if dry_run:
        engine.derive_hr_benchmarks(root, settings=settings)
    saved = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        repeated.back_reach_changes,
        repeated.takeovers,
        repeated.changed,
        repeated.written,
        _tree_changes(saved, root),
    ) == ((), (), False, False, ())


@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_real_resting_source_cardinality(
    count: int, dry_run: bool, tmp_path: Path
) -> None:

    root = tmp_path / "source-cardinality"
    keys = ("synthetic-z", "synthetic-a", "synthetic-m")[:count]
    starts = (date(2021, 1, 1), date(2021, 3, 1), date(2021, 5, 1))[:count]
    write_series(
        root,
        (
            SeriesValue(
                start + timedelta(days=i), Metric.RESTING_HR_BPM, key, None, 57, True
            )
            for start, key in zip(starts, keys, strict=True)
            for i in range(14)
        ),
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    assert (
        report.resting_sources,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (
        keys,
        bool(count),
        bool(count) and not dry_run,
        ("athlete.toml",) if count and not dry_run else (),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_cover_cardinality(
    kind: BenchmarkKind,
    count: int,
    origin: BenchmarkSource | None,
    dry_run: bool,
    tmp_path: Path,
) -> None:
    root = tmp_path / "cover-cardinality"
    root.mkdir()
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2020, 12, 20) + timedelta(days=i),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    71,
                    True,
                )
                for i in range(27)
            ),
        )
    else:
        for i, bpm in enumerate((173, 161, 151)):
            ref = _workout_archive(root, _session_fit(bpm))
            _workout_page(root, f"useful-{i}.md", [ref], day="2021-01-02")
    starts = (date(2021, 2, 10), date(2021, 1, 20), date(2021, 1, 10))[:count]
    measurement_days = (date(2021, 3, 1), date(2021, 3, 2), date(2021, 3, 3))[:count]
    values = ((50, 55, 60) if kind is _REST else (170, 165, 160))[:count]
    hands = tuple(
        Benchmark(kind, None, value, measured, applies_from=start, source=origin)
        for value, measured, start in zip(values, measurement_days, starts, strict=True)
    )
    _seed_entries(root, hands)
    before = _tree_snapshot(root)
    settings = engine.load_hr_stage_settings({}, data_root=root)
    report = engine.derive_hr_benchmarks(root, settings=settings, dry_run=dry_run)
    before_intervals = tuple(
        (start, measurement_days[0] if i == 0 else starts[i - 1])
        for i, start in enumerate(starts)
    )
    after_intervals = tuple((start, start) for start in starts)
    notices = tuple(
        BackReachChange(kind, hand, old, new)
        for hand, old, new in zip(hands, before_intervals, after_intervals, strict=True)
    )
    assert (
        report.back_reach_changes,
        report.changed,
        report.written,
        _tree_changes(before, root),
    ) == (
        notices,
        True,
        not dry_run,
        () if dry_run else ("athlete.toml",),
    )
    if dry_run:
        engine.derive_hr_benchmarks(root, settings=settings)
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 2),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    71,
                    True,
                ),
            ),
        )
    else:
        for page in (root / "workouts").glob("*.md"):
            page.unlink()
    before = _tree_snapshot(root)
    expanded = engine.derive_hr_benchmarks(root, settings=settings, dry_run=dry_run)
    expansions = tuple(
        BackReachChange(kind, hand, old, new)
        for hand, old, new in zip(hands, after_intervals, before_intervals, strict=True)
    )
    assert (
        expanded.back_reach_changes,
        expanded.kinds[0 if kind is _REST else 1].entries,
        expanded.changed,
        expanded.written,
        _tree_changes(before, root),
    ) == (
        expansions,
        (),
        True,
        not dry_run,
        () if dry_run else ("athlete.toml",),
    )
    if dry_run:
        engine.derive_hr_benchmarks(root, settings=settings)
    before = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        repeated.back_reach_changes,
        repeated.takeovers,
        repeated.changed,
        repeated.written,
        _tree_changes(before, root),
    ) == ((), (), False, False, ())


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_real_removal_cardinality(
    kind: BenchmarkKind, count: int, dry_run: bool, tmp_path: Path
) -> None:
    root = tmp_path / "real-removals"
    root.mkdir()
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 2),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    57,
                    True,
                ),
            ),
        )
    entries = tuple(
        replace(
            _short_entry(
                kind,
                date(2020, 12, 1) + timedelta(days=i),
                (72, 68, 81)[i] if kind is _REST else (181, 193, 175)[i],
                f"removed-{i}",
                f"old removed {i}",
            ),
            applies_from=date(2020, 11, 1) + timedelta(days=2 * i),
        )
        for i in range(count)
    )
    _seed_entries(root, entries)
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    expected = HrStageReport(
        0,
        0,
        _reason_counts(),
        (),
        (),
        (
            KindOutcome(_REST, (), (), entries if kind is _REST else (), kind is _MAX),
            KindOutcome(_MAX, (), (), entries if kind is _MAX else (), False),
        ),
        (),
        (),
        (),
        (),
        (
            "the wellness series holds no resting heart rate; "
            "derived resting entries kept as on file",
        )
        if kind is _MAX
        else (),
        bool(count) and not dry_run,
        bool(count),
    )
    assert (
        report,
        tuple(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected,
        entries if dry_run else (),
        ("athlete.toml",) if count and not dry_run else (),
    )


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize(
    "origin", [None, BenchmarkSource(BenchmarkSourceKind.MEASURED)]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_third_hand_agreement_suppresses_entry(
    kind: BenchmarkKind,
    origin: BenchmarkSource | None,
    dry_run: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "third-hand-agreement"
    root.mkdir()
    hand_dates = (date(2021, 1, 1), date(2021, 1, 20), date(2021, 2, 10))
    hand_values = (50, 70, 79) if kind is _REST else (170, 200, 210)
    hands = tuple(
        Benchmark(kind, None, value, day, source=origin)
        for day, value in zip(hand_dates, hand_values, strict=True)
    )
    _seed_entries(root, hands)
    values = (61, 70, 79) if kind is _REST else (175, 200, 210)
    key = "z-source" if kind is _REST else "workouts"
    evidence = tuple(
        _short_evidence(day + timedelta(days=1 + i), value, key)
        for day, value in zip(hand_dates, values, strict=True)
        for i in range(14 if kind is _REST else 1)
    )
    if kind is _REST:
        monkeypatch.setattr(
            engine,
            "_read_resting_series",
            lambda *args: engine._RestingSeries(evidence, False, (), ()),
        )
    else:
        monkeypatch.setattr(
            engine,
            "_read_workout_sessions",
            lambda *args, **kwargs: engine._WorkoutSessions(
                evidence, 9, 9, _reason_counts(), (), (), False
            ),
        )
    target = _short_entry(
        kind,
        date(2021, 1, 2),
        61 if kind is _REST else 175,
        key,
        f"Takes over from your hand-recorded {hands[0].value:g} bpm "
        "of 2021-01-01: the evidence differed by more than "
        f"{3 if kind is _REST else 2} bpm.",
        confirmed=kind is _REST,
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    assert (
        report.kinds[0 if kind is _REST else 1],
        report.takeovers,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        KindOutcome(kind, (target,), (target,), (), False),
        (Takeover(kind, target, hands[0]),),
        frozenset(hands if dry_run else (*hands, target)),
        () if dry_run else ("athlete.toml",),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 3])
@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_repair_real_joint_failures(
    count: int, dry_run: bool, tmp_path: Path
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read files without permission bits")
    root = tmp_path / "joint-reader-failures"
    _basic_root(root)
    old_rest = tuple(
        replace(
            _short_entry(
                _REST,
                date(2020, 12, 1) + timedelta(days=i),
                (72, 68, 81)[i],
                f"joint-rest-{i}",
                f"kept resting note {i}",
            ),
            applies_from=date(2020, 11, 1 + i),
        )
        for i in range(3)
    )
    old_max = tuple(
        replace(
            _short_entry(
                _MAX,
                date(2020, 12, 11) + timedelta(days=i),
                (181, 193, 175)[i],
                f"joint-max-{i}",
                f"kept maximum note {i}",
            ),
            applies_from=date(2020, 11, 11 + i),
        )
        for i in range(3)
    )
    _seed_entries(root, (*old_rest, *old_max))
    manifest = root / "wellness/manifest.toml"
    manifest.write_bytes(b"\xff")
    rest_failure = HrFailure(
        _REST,
        "wellness/manifest.toml",
        f"{manifest}: invalid manifest: "
        "'utf-8' codec can't decode byte 0xff in position 0: "
        "invalid start byte",
    )
    paths = []
    for i in range(count):
        ref = _workout_archive(root, _session_fit(190 + i))
        _workout_page(root, f"a-fail-{i}.md", [ref])
        paths.append(root / ref)
    before = _tree_snapshot(root)
    progress: list[tuple[int, int]] = []
    for path in paths:
        path.chmod(0)
    try:
        report = engine.derive_hr_benchmarks(
            root,
            settings=engine.load_hr_stage_settings({}, data_root=root),
            dry_run=dry_run,
            progress=lambda done, total: progress.append((done, total)),
        )
    finally:
        for path in paths:
            path.chmod(0o600)
    mx = _basic_entries()[1]
    expected = HrStageReport(
        3 + count,
        3,
        _reason_counts(),
        (),
        (),
        (
            KindOutcome(_REST, old_rest, (), (), True),
            KindOutcome(
                _MAX,
                old_max if count else (mx,),
                () if count else (mx,),
                () if count else old_max,
                bool(count),
            ),
        ),
        (),
        (),
        (),
        (
            rest_failure,
            *(
                HrFailure(
                    _MAX,
                    f"workouts/a-fail-{i}.md",
                    f"[Errno 13] Permission denied: '{path}'",
                )
                for i, path in enumerate(paths)
            ),
        ),
        (),
        not count and not dry_run,
        not count,
    )
    assert (
        report,
        progress,
        frozenset(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected,
        [(i, 3 + count) for i in range(1, 4 + count)],
        frozenset((*old_rest, *old_max) if count or dry_run else (*old_rest, mx)),
        ("athlete.toml",) if not count and not dry_run else (),
    )


_IDENTITY_ORIGIN_PAIRS = (
    (None, None),
    (None, BenchmarkSource(BenchmarkSourceKind.MEASURED)),
    (BenchmarkSource(BenchmarkSourceKind.MEASURED), None),
    (
        BenchmarkSource(BenchmarkSourceKind.MEASURED),
        BenchmarkSource(BenchmarkSourceKind.MEASURED),
    ),
)


def _identity_entry_state(
    entries: Sequence[Benchmark],
) -> frozenset[
    tuple[BenchmarkKind, float, date, date | None, BenchmarkSourceKind | None]
]:
    return frozenset(
        (
            entry.kind,
            entry.value,
            entry.measured_on,
            entry.applies_from,
            entry.source.kind if entry.source else None,
        )
        for entry in entries
    )


@pytest.mark.parametrize("origins", _IDENTITY_ORIGIN_PAIRS)
@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("same_date", [False, True])
@pytest.mark.parametrize("same_start", [False, True])
@pytest.mark.parametrize("same_value", [False, True])
def test_stage_repair_cross_kind_cover_identity(
    origins: tuple[BenchmarkSource | None, BenchmarkSource | None],
    dry_run: bool,
    same_date: bool,
    same_start: bool,
    same_value: bool,
    tmp_path: Path,
) -> None:
    root = tmp_path / "cross-kind-identity"
    _basic_root(root)
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 1, 1) + timedelta(days=i),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                57,
                True,
            )
            for i in range(27)
        ),
    )
    rest = Benchmark(
        _REST,
        None,
        50,
        date(2021, 3, 1),
        applies_from=date(2021, 2, 5),
        source=origins[0],
    )
    max_start = date(2021, 2, 5) if same_start else date(2021, 2, 6)
    maximum = Benchmark(
        _MAX,
        None,
        50 if same_value else 170,
        date(2021, 3, 1) if same_date else date(2021, 3, 2),
        applies_from=max_start,
        source=origins[1],
    )
    hands = (rest, maximum)
    _seed_entries(root, hands)
    hand_state = _identity_entry_state(hands)
    derived_state = frozenset(
        (
            (_REST, 57, date(2021, 1, 14), None, BenchmarkSourceKind.DERIVED),
            (_MAX, 163, date(2021, 2, 3), None, BenchmarkSourceKind.DERIVED),
        )
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    expected = (
        BackReachChange(
            _MAX,
            maximum,
            (max_start, maximum.measured_on),
            (max_start, max_start),
        ),
        BackReachChange(
            _REST,
            rest,
            (date(2021, 2, 5), date(2021, 3, 1)),
            (date(2021, 2, 5), date(2021, 2, 5)),
        ),
    )
    assert (
        report.back_reach_changes,
        report.changed,
        report.written,
        _identity_entry_state(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected,
        True,
        not dry_run,
        hand_state if dry_run else hand_state | derived_state,
        () if dry_run else ("athlete.toml",),
    )
    _identity_repeats_and_removal(root, dry_run, expected, hand_state, derived_state)


@pytest.mark.parametrize("kind", [_REST, _MAX])
@pytest.mark.parametrize("origins", _IDENTITY_ORIGIN_PAIRS)
@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("equal_values", [False, True])
@pytest.mark.parametrize("equal_start", [False, True])
def test_stage_repair_same_kind_cover_identity(
    kind: BenchmarkKind,
    origins: tuple[BenchmarkSource | None, BenchmarkSource | None],
    dry_run: bool,
    equal_values: bool,
    equal_start: bool,
    tmp_path: Path,
) -> None:
    root = tmp_path / "same-kind-identity"
    _basic_root(root)
    if kind is _REST:
        write_series(
            root,
            (
                SeriesValue(
                    date(2021, 1, 8) + timedelta(days=i),
                    Metric.RESTING_HR_BPM,
                    "garmin-export",
                    None,
                    57,
                    True,
                )
                for i in range(27)
            ),
        )
    value = 50 if kind is _REST else 170
    cover_start = date(2021, 2, 5)
    first_start = cover_start if equal_start else date(2021, 2, 10)
    first = Benchmark(
        kind,
        None,
        value,
        date(2021, 3, 1),
        applies_from=first_start,
        source=origins[0],
    )
    second = Benchmark(
        kind,
        None,
        value if equal_values else value - 1,
        date(2021, 3, 2),
        applies_from=cover_start,
        source=origins[1],
    )
    hands = (first, second)
    _seed_entries(root, hands)
    hand_state = _identity_entry_state(hands)
    rest_day = date(2021, 1, 21) if kind is _REST else date(2021, 1, 14)
    derived_state = frozenset(
        (
            (_REST, 57, rest_day, None, BenchmarkSourceKind.DERIVED),
            (_MAX, 163, date(2021, 2, 3), None, BenchmarkSourceKind.DERIVED),
        )
    )
    before = _tree_snapshot(root)
    report = engine.derive_hr_benchmarks(
        root,
        settings=engine.load_hr_stage_settings({}, data_root=root),
        dry_run=dry_run,
    )
    if equal_start:
        expected: tuple[BackReachChange, ...] = (
            BackReachChange(
                kind,
                first,
                (cover_start, date(2021, 3, 1)),
                (cover_start, cover_start),
            ),
        )
    else:
        expected = (
            BackReachChange(
                kind,
                first,
                (first_start, date(2021, 3, 1)),
                (first_start, first_start),
            ),
            BackReachChange(
                kind,
                second,
                (cover_start, first_start),
                (cover_start, cover_start),
            ),
        )
    assert (
        report.back_reach_changes,
        report.changed,
        report.written,
        _identity_entry_state(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected,
        True,
        not dry_run,
        hand_state if dry_run else hand_state | derived_state,
        () if dry_run else ("athlete.toml",),
    )
    _identity_repeats_and_removal(root, dry_run, expected, hand_state, derived_state)


def _identity_repeats_and_removal(
    root: Path,
    dry_run: bool,
    expected: tuple[BackReachChange, ...],
    hand_state: frozenset[
        tuple[BenchmarkKind, float, date, date | None, BenchmarkSourceKind | None]
    ],
    derived_state: frozenset[
        tuple[BenchmarkKind, float, date, date | None, BenchmarkSourceKind | None]
    ],
) -> None:
    settings = engine.load_hr_stage_settings({}, data_root=root)
    if dry_run:
        engine.derive_hr_benchmarks(root, settings=settings)
    before = _tree_snapshot(root)
    repeated = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        repeated.back_reach_changes,
        repeated.takeovers,
        repeated.changed,
        repeated.written,
        _identity_entry_state(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == ((), (), False, False, hand_state | derived_state, ())
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 1, 1),
                Metric.RESTING_HR_BPM,
                "garmin-export",
                None,
                57,
                True,
            ),
        ),
    )
    for page in (root / "workouts").glob("*.md"):
        page.unlink()
    before = _tree_snapshot(root)
    expanded = engine.derive_hr_benchmarks(root, settings=settings, dry_run=dry_run)
    expected_expansions = tuple(
        BackReachChange(change.kind, change.entry, change.after, change.before)
        for change in expected
    )
    assert (
        expanded.back_reach_changes,
        expanded.changed,
        expanded.written,
        _identity_entry_state(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == (
        expected_expansions,
        True,
        not dry_run,
        hand_state | derived_state if dry_run else hand_state,
        () if dry_run else ("athlete.toml",),
    )
    if dry_run:
        engine.derive_hr_benchmarks(root, settings=settings)
    before = _tree_snapshot(root)
    cleared_repeat = engine.derive_hr_benchmarks(root, settings=settings)
    assert (
        cleared_repeat.back_reach_changes,
        cleared_repeat.takeovers,
        cleared_repeat.changed,
        cleared_repeat.written,
        _identity_entry_state(load_profile(root).benchmarks.entries),
        _tree_changes(before, root),
    ) == ((), (), False, False, hand_state, ())
