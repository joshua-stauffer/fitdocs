"""Wellness intake composed with the standing inbox and FIT planner."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from fitdocs.declaration import ensure_declarations
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS, Disposition, InboxNote
from fitdocs.quarantine import load_quarantine
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import DrainReport, SyncReport, drain, sync
from fitdocs.wellness import Metric, WellnessSettings, read_series
from fitdocs.wellness.engine import SeriesReport, SeriesStatus, rebuild_series
from fitdocs.wellness.intake import (
    AlreadyArchived,
    Archived,
    Identified,
    archive_identified,
    identify,
)
from fitdocs.wellness.spec import ExtractContext, WellnessFormatError
from tests.fixtures import builder
from tests.support import tiles as tile_factory
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    EXTRACT_SOURCE,
    build_extract,
    tree_snapshot,
    use_formats,
)
from tests.wellness.builders_garmin import (
    garmin_biometrics_record,
    garmin_file_bytes,
    garmin_file_name,
    garmin_maxmet_record,
    garmin_sleep_record,
    garmin_uds_record,
)
from tests.wellness.builders_intervals import (
    intervals_delivery_bytes,
    intervals_list_bytes,
    intervals_record,
)

sync_module = importlib.import_module("fitdocs.sync")
_DAY = date(2021, 9, 7)


class _Tiles:
    attribution = "synthetic offline tiles"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {
            ref: tile_factory.solid(tile_factory.DEFAULT_SIZE, (46, 139, 120))
            for ref in refs
        }


def _put(root: Path, name: str, data: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _drain(inbox: Path, root: Path, **kwargs: Any) -> DrainReport:
    return drain(
        inbox,
        root,
        settings=kwargs.pop(
            "settings", replace(DEFAULT_INBOX_SETTINGS, settle_seconds=0)
        ),
        processed_dir=kwargs.pop("processed_dir", None),
        quarantine=kwargs.pop("quarantine", load_quarantine(root)),
        athlete=None,
        tz=UTC,
        tiles=_Tiles(),
        **kwargs,
    )


def _channels(report: DrainReport) -> dict[str, set[str]]:
    return {
        "written": set(report.sync.written),
        "skipped": set(report.sync.skipped),
        "failures": {note.source for note in report.sync.failures},
        **{
            name: {note.subject for note in getattr(report, name)}
            for name in (
                "deferred",
                "quarantined",
                "unrecognized",
                "wellness_archived",
                "wellness_skipped",
                "wellness_failures",
            )
        },
    }


def _mixed(inbox: Path) -> set[str]:
    wellness = {
        "z-list.json": intervals_list_bytes([intervals_record(_DAY, restingHR=43)]),
        "a-envelope.json": intervals_delivery_bytes(
            [intervals_record(_DAY, hrv=61)], origins={"hrv": "oura"}
        ),
        garmin_file_name("uds", _DAY, _DAY): garmin_file_bytes(
            [garmin_uds_record(_DAY, totalSteps=7654)]
        ),
        garmin_file_name("sleep", _DAY, _DAY): garmin_file_bytes(
            [garmin_sleep_record(_DAY, deep_s=3600, light_s=7200, rem_s=1800)]
        ),
        garmin_file_name("maxmet", _DAY, _DAY): garmin_file_bytes(
            [
                garmin_maxmet_record(
                    _DAY, sport="RUNNING", vo2max=52, updated="2021-09-07T08:00:00Z"
                )
            ]
        ),
        garmin_file_name("biometrics", _DAY, _DAY): garmin_file_bytes(
            [
                garmin_biometrics_record(
                    _DAY, weight_g=73250, measured_at="2021-09-07T09:00:00Z"
                )
            ]
        ),
    }
    for name, data in reversed(list(wellness.items())):
        _put(inbox, name, data)
    _put(inbox, "activity.fit", builder.small_sport_fit_bytes(9891, "running"))
    identity = builder._file_id(4200000091, manufacturer="stryd")
    identity["type"] = "monitoring_b"
    _put(inbox, "monitoring.fit", builder.encode([identity]))
    _put(inbox, "unknown.json", b'{"other": 876}')
    _put(inbox, "ignored.gpx", b"<gpx/>")
    _put(
        inbox,
        "bad.json",
        garmin_file_bytes([garmin_uds_record("invalid-day", totalSteps=313)]),
    )
    return set(wellness)


def test_mixed_partition_rebuild_before_fit_and_single_settle(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    wellness = _mixed(inbox)
    sleeps: list[float] = []
    observed: list[dict[tuple[str, str, str | None], float]] = []

    def rendered(page: object) -> None:
        observed.append(
            {
                (v.metric.value, v.source, v.origin): v.value
                for v in read_series(root).for_day(_DAY)
            }
        )

    report = _drain(
        inbox,
        root,
        settings=replace(DEFAULT_INBOX_SETTINGS, settle_seconds=0.625),
        sleep=sleeps.append,
        on_rendered=rendered,
    )
    assert _channels(report) == {
        "written": {"workouts/2021-09-08-run-0146.md"},
        "skipped": {"monitoring.fit"},
        "failures": set(),
        "deferred": set(),
        "quarantined": set(),
        "unrecognized": {"unknown.json"},
        "wellness_archived": wellness,
        "wellness_skipped": set(),
        "wellness_failures": {"bad.json"},
    }
    assert sleeps == [0.625]
    assert observed == [
        {
            ("resting_hr_bpm", "intervals-icu", None): 43,
            ("hrv_rmssd_ms", "intervals-icu", "oura"): 61,
            ("steps", "garmin-export", "garmin"): 7654,
            ("sleep_deep_s", "garmin-export", "garmin"): 3600,
            ("sleep_light_s", "garmin-export", "garmin"): 7200,
            ("sleep_rem_s", "garmin-export", "garmin"): 1800,
            ("sleep_s", "garmin-export", "garmin"): 12600,
            ("vo2max_run_ml_per_kg_min", "garmin-export", "garmin"): 52,
            ("weight_kg", "garmin-export", "garmin"): 73.25,
        }
    ]
    assert (
        report.wellness_series is not None
        and report.wellness_series.status is SeriesStatus.REBUILT
    )
    formats = {
        "a-envelope.json": "intervals-icu",
        "z-list.json": "intervals-icu",
        "UDSFile_2021-09-07_2021-09-07.json": "garmin-uds",
        "2021-09-07_2021-09-07_1_sleepData.json": "garmin-sleep",
        "MetricsMaxMetData_2021-09-07_2021-09-07.json": "garmin-maxmet",
        "2021-09-07_2021-09-07_1_userBioMetrics.json": "garmin-biometrics",
    }
    assert [(n.subject, n.detail) for n in report.wellness_archived] == [
        (
            name,
            f"wellness-archive/{format_id}/"
            f"{hashlib.sha256((inbox / name).read_bytes()).hexdigest()}"
            f".json ({format_id})",
        )
        for name, format_id in sorted(formats.items())
    ]


def test_second_drain_is_unchanged_with_bytes_and_mtimes(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    wellness = _mixed(inbox)
    _drain(inbox, root)
    before = tree_snapshot(root / "wellness")
    assert "2021.csv" in before and before["2021.csv"][0].startswith(b"day,metric,")
    report = _drain(inbox, root)
    assert {n.subject for n in report.wellness_skipped} == wellness
    assert report.wellness_archived == ()
    assert (
        report.wellness_series is not None
        and report.wellness_series.status is SeriesStatus.UNCHANGED
    )
    assert tree_snapshot(root / "wellness") == before
    assert {n.subject for n in report.quarantined} == {"bad.json"}
    assert report.wellness_failures == ()


def test_quarantine_skip_retry_and_changed_content_identity(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    candidate = _put(
        inbox,
        "bad.json",
        garmin_file_bytes([garmin_uds_record("invalid-day", totalSteps=313)]),
    )
    bad_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    first = _drain(inbox, root)
    record = load_quarantine(root)
    assert [(n.subject, n.detail) for n in first.wellness_failures] == [
        ("bad.json", "invalid Garmin calendar date")
    ]
    assert [(e.sha256, e.name) for e in record.entries] == [(bad_sha, "bad.json")]
    second = _drain(inbox, root)
    assert second.quarantined == (InboxNote("bad.json", record.entries[0].reason),)
    assert second.wellness_failures == ()
    retry = _drain(inbox, root, retry_quarantined=True)
    assert {n.subject for n in retry.wellness_failures} == {"bad.json"}
    candidate.write_bytes(
        garmin_file_bytes([garmin_uds_record(_DAY, currentDayRestingHeartRate=47)])
    )
    fixed_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    fixed = _drain(inbox, root)
    assert {n.subject for n in fixed.wellness_archived} == {"bad.json"}
    assert fixed_sha != bad_sha and [
        (n.subject, n.detail) for n in fixed.wellness_archived
    ] == [("bad.json", f"wellness-archive/garmin-uds/{fixed_sha}.json (garmin-uds)")]
    assert load_quarantine(root) == record


def test_same_content_successful_retry_removes_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    candidate = _put(inbox, "recover.test-extract", build_extract("alpha"))

    def failed(path: Path, output: BinaryIO, context: ExtractContext) -> None:
        raise WellnessFormatError("synthetic temporary extraction fault")

    use_formats(
        monkeypatch,
        [replace(EXTRACT_FORMAT, id="extract-wire", extract=failed)],
        [EXTRACT_SOURCE],
    )
    first = _drain(inbox, root)
    sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert first.wellness_failures == (
        InboxNote("recover.test-extract", "synthetic temporary extraction fault"),
    )
    assert load_quarantine(root).get(sha) is not None

    def recovered(path: Path, output: BinaryIO, context: ExtractContext) -> None:
        extractor = EXTRACT_FORMAT.extract
        if extractor is None:
            raise RuntimeError("EXTRACT fixture has no extractor")
        extractor(path, output, replace(context, progress=None))
        if context.progress is not None:
            context.progress(7, context.size)

    use_formats(
        monkeypatch,
        [replace(EXTRACT_FORMAT, id="extract-wire", extract=recovered)],
        [EXTRACT_SOURCE],
    )
    progress: list[tuple[str, int, int]] = []
    report = _drain(
        inbox,
        root,
        retry_quarantined=True,
        wellness_progress=lambda *args: progress.append(args),
    )
    assert {n.subject for n in report.wellness_archived} == {"recover.test-extract"}
    assert load_quarantine(root).entries == ()
    assert progress == [("recover.test-extract", 7, candidate.stat().st_size)]


@pytest.mark.parametrize("missing_processed", [False, True])
def test_move_only_success_and_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_processed: bool
) -> None:
    inbox, root, processed = (
        tmp_path / "inbox",
        tmp_path / "root",
        tmp_path / "processed",
    )
    original = _put(
        inbox,
        "b-new.json",
        intervals_list_bytes([intervals_record(_DAY, restingHR=48)]),
    )
    _drain(inbox, root)
    _put(inbox, "a-copy.json", original.read_bytes())
    _put(inbox, "c-fresh.json", intervals_list_bytes([intervals_record(_DAY, hrv=68)]))
    unknown = _put(inbox, "unknown.json", b"{}")
    bad = _put(
        inbox,
        "bad.json",
        garmin_file_bytes([garmin_uds_record("invalid-day", totalSteps=313)]),
    )
    unreadable = _put(inbox, "unreadable.json", b"{}")
    original_open = Path.open

    def guarded(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == unreadable:
            raise OSError("synthetic unavailable candidate")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    report = _drain(
        inbox,
        root,
        settings=replace(
            DEFAULT_INBOX_SETTINGS, disposition=Disposition.MOVE, settle_seconds=0
        ),
        processed_dir=None if missing_processed else processed,
    )
    expected = {"a-copy.json", "b-new.json", "c-fresh.json"}
    assert {Path(p).name for p in report.moved} == (
        set() if missing_processed else expected
    )
    assert {n.subject for n in report.wellness_archived} == {"c-fresh.json"}
    assert {n.subject for n in report.wellness_skipped} == {"a-copy.json", "b-new.json"}
    assert {n.subject for n in report.unrecognized} == {unknown.name}
    assert {n.subject for n in report.wellness_failures} == {bad.name}
    assert {n.subject for n in report.deferred} == {unreadable.name}
    assert {p.name for p in inbox.iterdir()} == (
        {"unknown.json", "bad.json", "unreadable.json"}
        | (expected if missing_processed else set())
    )
    assert {p.name for p in processed.glob("*.json")} == (
        set() if missing_processed else expected
    )


def test_failed_move_uses_existing_channel(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    _put(
        inbox,
        "daily.json",
        intervals_list_bytes([intervals_record(_DAY, restingHR=49)]),
    )
    obstruction = _put(tmp_path, "processed", b"occupied")
    report = _drain(
        inbox,
        root,
        settings=replace(
            DEFAULT_INBOX_SETTINGS, disposition=Disposition.MOVE, settle_seconds=0
        ),
        processed_dir=obstruction,
    )
    assert {n.subject for n in report.wellness_archived} == {"daily.json"}
    assert {n.subject for n in report.move_failures} == {"daily.json"}
    assert report.moved == ()
    assert (inbox / "daily.json").is_file()


def test_unstable_wellness_deferred_in_combined_settle(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    candidate = _put(
        inbox,
        "daily.json",
        intervals_list_bytes([intervals_record(_DAY, restingHR=51)]),
    )

    def changed(seconds: float) -> None:
        candidate.write_bytes(candidate.read_bytes() + b" ")

    report = _drain(
        inbox,
        root,
        settings=replace(DEFAULT_INBOX_SETTINGS, settle_seconds=0.25),
        sleep=changed,
    )
    assert {n.subject for n in report.deferred} == {"daily.json"}
    assert report.wellness_archived == ()
    assert load_quarantine(root).entries == ()


def test_extract_change_defers_without_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    candidate = _put(inbox, "truncated.test-extract", build_extract("beta"))

    def truncated(path: Path, output: BinaryIO, context: ExtractContext) -> None:
        path.write_bytes(b"truncated")
        raise WellnessFormatError("broken after truncation")

    use_formats(
        monkeypatch, [replace(EXTRACT_FORMAT, extract=truncated)], [EXTRACT_SOURCE]
    )
    report = _drain(inbox, root)
    assert {n.subject for n in report.deferred} == {candidate.name}
    assert "changed during the run" in report.deferred[0].detail
    assert report.wellness_failures == ()
    assert load_quarantine(root).entries == ()
    assert list((root / "wellness-archive").rglob("*.jsonl")) == []


def test_source_sync_leaves_wellness_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root, source = tmp_path / "inbox", tmp_path / "root", tmp_path / "source"
    _put(
        inbox,
        "daily.json",
        intervals_list_bytes([intervals_record(_DAY, restingHR=54)]),
    )
    _drain(inbox, root)
    _put(
        source, "new.json", intervals_list_bytes([intervals_record(_DAY, restingHR=57)])
    )
    _put(source, "activity.fit", builder.small_sport_fit_bytes(9891, "running"))
    stale = _put(
        tmp_path,
        "stale.json",
        intervals_list_bytes([intervals_record("2021-09-06", restingHR=63)]),
    )
    identified = identify(stale)
    if not isinstance(identified, Identified):
        raise RuntimeError("synthetic staging file was not recognized")
    archive_identified(root, stale, identified, None)
    calls: list[str] = []
    for name in ("identify", "archive_identified", "rebuild_series"):
        original_call = getattr(sync_module, name)

        def observe(
            *args: Any, _name: str = name, _call: Any = original_call, **kwargs: Any
        ) -> Any:
            calls.append(_name)
            return _call(*args, **kwargs)

        monkeypatch.setattr(sync_module, name, observe)
    ensure_declarations(root)
    before = {
        name: tree_snapshot(root / name) for name in ("wellness", "wellness-archive")
    }
    original = tree_snapshot(source)
    report = sync(source, root, athlete=None, tz=UTC, tiles=_Tiles())
    assert report == SyncReport(("workouts/2021-09-08-run-0146.md",), (), ())
    assert calls == []
    assert {name: tree_snapshot(root / name) for name in before} == before
    assert tree_snapshot(source) == original


def test_drain_report_defaults() -> None:
    report = DrainReport("inbox", SyncReport((), (), ()), (), (), (), ())
    assert (
        report.unrecognized,
        report.wellness_archived,
        report.wellness_skipped,
        report.wellness_failures,
        report.wellness_series,
    ) == ((), (), (), (), None)


def test_nondefault_settings_rebuild_stale_series_without_new_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    _put(
        inbox,
        "device.json",
        garmin_file_bytes([garmin_uds_record(_DAY, currentDayRestingHeartRate=45)]),
    )
    _put(
        inbox, "hub.json", intervals_list_bytes([intervals_record(_DAY, restingHR=59)])
    )
    _drain(inbox, root)
    initial = read_series(root).canonical(Metric.RESTING_HR_BPM, _DAY)
    assert (
        initial is not None
        and initial.value == 45
        and initial.source == "garmin-export"
    )
    calls: list[tuple[Path, WellnessSettings, bool]] = []
    original_rebuild = rebuild_series

    def rebuild(
        data_root: Path, *, settings: WellnessSettings, force: bool
    ) -> SeriesReport:
        calls.append((data_root, settings, force))
        return original_rebuild(data_root, settings=settings, force=force)

    monkeypatch.setattr(sync_module, "rebuild_series", rebuild)
    configured = WellnessSettings(("intervals-icu", "garmin-export"), {})
    report = _drain(inbox, root, wellness_settings=configured)
    assert calls == [(root, configured, False)]
    canonical = read_series(root).canonical(Metric.RESTING_HR_BPM, _DAY)
    assert canonical is not None and (canonical.value, canonical.source) == (
        59,
        "intervals-icu",
    )
    assert report.wellness_archived == ()
    assert (
        report.wellness_series is not None
        and report.wellness_series.status is SeriesStatus.REBUILT
    )


def test_known_quarantine_does_not_attempt_archive_or_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "root"
    candidate = _put(inbox, "quiet.test-extract", build_extract("quiet"))
    sha = hashlib.sha256(candidate.read_bytes()).hexdigest()

    def failed(path: Path, output: BinaryIO, context: ExtractContext) -> None:
        raise WellnessFormatError("temporary quiet extractor fault")

    use_formats(
        monkeypatch,
        [replace(EXTRACT_FORMAT, id="quiet-wire", extract=failed)],
        [EXTRACT_SOURCE],
    )
    first = _drain(inbox, root)
    assert first.wellness_failures == (
        InboxNote(candidate.name, "temporary quiet extractor fault"),
    )
    assert [(e.sha256, e.name) for e in load_quarantine(root).entries] == [
        (sha, candidate.name)
    ]
    archive_attempts: list[Path] = []
    parse_attempts: list[BinaryIO] = []

    def observe_archive(*args: Any, **kwargs: Any) -> Any:
        archive_attempts.append(args[1])
        return archive_identified(*args, **kwargs)

    def observe_parse(stream: BinaryIO) -> Any:
        parse_attempts.append(stream)
        yield from EXTRACT_FORMAT.parse(stream)

    use_formats(
        monkeypatch,
        [replace(EXTRACT_FORMAT, id="quiet-wire", parse=observe_parse)],
        [EXTRACT_SOURCE],
    )
    monkeypatch.setattr(sync_module, "archive_identified", observe_archive)
    _drain(inbox, root)
    assert (archive_attempts, parse_attempts) == ([], [])


@pytest.mark.parametrize("outcome_kind", ["Archived", "AlreadyArchived"])
@pytest.mark.parametrize(
    "archive_state", ["missing", "directory", "symlink", "regular"]
)
def test_move_requires_actual_regular_nonsymlink_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome_kind: str,
    archive_state: str,
) -> None:
    inbox, root, processed = (
        tmp_path / "inbox",
        tmp_path / "root",
        tmp_path / "processed",
    )
    candidate = _put(
        inbox,
        "daily.json",
        intervals_list_bytes([intervals_record(_DAY, restingHR=67)]),
    )
    if outcome_kind == "AlreadyArchived":
        _drain(inbox, root)
    original = tree_snapshot(inbox)
    external = _put(tmp_path, "external.json", b"external regular file")
    observations: list[tuple[str, bool, bool, bool, bool]] = []

    def race(*args: Any, **kwargs: Any) -> Any:
        outcome = archive_identified(*args, **kwargs)
        if not isinstance(outcome, (Archived, AlreadyArchived)):
            raise RuntimeError("real intake did not complete archival")
        entry = outcome.entry.path
        before = (entry.is_file(), entry.is_symlink())
        if archive_state != "regular":
            entry.unlink()
            if archive_state == "directory":
                entry.mkdir()
            elif archive_state == "symlink":
                entry.symlink_to(external)
        observations.append(
            (type(outcome).__name__, *before, entry.is_file(), entry.is_symlink())
        )
        return outcome

    monkeypatch.setattr(sync_module, "archive_identified", race)
    report = _drain(
        inbox,
        root,
        settings=replace(
            DEFAULT_INBOX_SETTINGS, disposition=Disposition.MOVE, settle_seconds=0
        ),
        processed_dir=processed,
    )
    after_file, after_link = {
        "missing": (False, False),
        "directory": (False, False),
        "symlink": (True, True),
        "regular": (True, False),
    }[archive_state]
    assert observations == [(outcome_kind, True, False, after_file, after_link)]
    assert report.moved == (
        (str(processed / candidate.name),) if archive_state == "regular" else ()
    )
    assert report.move_failures == ()
    assert tree_snapshot(inbox) == ({} if archive_state == "regular" else original)
    assert tree_snapshot(processed) == (original if archive_state == "regular" else {})
