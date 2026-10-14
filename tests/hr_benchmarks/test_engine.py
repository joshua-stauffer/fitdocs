"""Heart-rate settings and synthetic normalized-series integration."""

import hashlib
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from pathlib import Path

import pytest

from fitdocs import docio
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.hr_benchmarks import engine
from fitdocs.hr_benchmarks.maximum import max_evidence
from fitdocs.hr_benchmarks.peaks import session_peak
from fitdocs.hr_benchmarks.types import (
    Evidence,
    HrFailure,
    NoEvidenceReason,
    SessionPeak,
    SkippedDocument,
)
from fitdocs.load.channels.types import ChannelId, SufficiencySettings
from fitdocs.load.priority import ChannelPriority
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
        ("c-late.md", "2021-02-03", 139, "swimming"),
        ("m-median.md", "2021-02-02", 163, "rowing"),
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
    _workout_page(tmp_path, "problem.md", refs, day=day)
    settings = engine.load_hr_stage_settings({}, data_root=tmp_path)
    assert engine._read_workout_sessions(tmp_path, settings) == engine._WorkoutSessions(
        (), 1, 0, _reason_counts(**{reason.value: 1}), skipped, (), False
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
        (_forwarding_samples(139), Modality.SWIM, expected_flags),
        (_forwarding_samples(163), Modality.OTHER, expected_flags),
        (_forwarding_samples(181), Modality.BIKE, expected_flags),
    )
    peaks: list[SessionPeak] = []
    calls: list[tuple[Samples, Modality, FlagSettings]] = []
    real_maximum = max_evidence
    real_peak = session_peak

    def maximum(values: Sequence[SessionPeak]) -> tuple[Evidence, ...]:
        peaks.extend(values)
        return real_maximum(values)

    def peak(
        samples: Samples, *, modality: Modality, flags: FlagSettings
    ) -> float | NoEvidenceReason:
        calls.append((samples, modality, flags))
        return real_peak(samples, modality=modality, flags=flags)

    monkeypatch.setattr(engine, "max_evidence", maximum)
    monkeypatch.setattr(engine, "session_peak", peak)
    engine._read_workout_sessions(tmp_path, settings)
    assert (tuple(peaks), tuple(calls)) == (expected_peaks, expected_calls)


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

    def maximum(values: Sequence[SessionPeak]) -> tuple[Evidence, ...]:
        peaks.extend(values)
        return max_evidence(values)

    monkeypatch.setattr(engine, "session_peak", peak)
    monkeypatch.setattr(engine, "max_evidence", maximum)
    engine._read_workout_sessions(tmp_path, settings)
    assert (raw_peaks, peaks) == ([expected], expected_peaks)
