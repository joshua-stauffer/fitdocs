import hashlib
import os
import tempfile
import tomllib
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from fitdocs.wellness import archive, engine, registry, series
from fitdocs.wellness.formats import garmin, intervals
from fitdocs.wellness.model import Metric
from fitdocs.wellness.settings import DEFAULT_WELLNESS_SETTINGS as DEFAULT
from fitdocs.wellness.settings import WellnessSettings
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    EXTRACT_SOURCE,
    build_extract,
    tree_snapshot,
)
from tests.wellness.builders_garmin import garmin_file_bytes, garmin_uds_record
from tests.wellness.builders_intervals import (
    intervals_delivery_bytes,
    intervals_list_bytes,
    intervals_record,
)


def stage(root: Path, form: Any, data: bytes, token: str | None = None) -> Path:
    digest = token or hashlib.sha256(data).hexdigest()
    path = root / archive.entry_ref(form, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def hub(
    root: Path,
    records: list[dict[str, object]],
    *,
    origins: dict[str, str] | None = None,
) -> Path:
    return stage(
        root,
        intervals.FORMAT,
        intervals_list_bytes(records)
        if origins is None
        else intervals_delivery_bytes(records, origins=origins),
    )


def build(
    root: Path, *, settings: WellnessSettings = DEFAULT, force: bool = False
) -> engine.SeriesReport:
    return engine.rebuild_series(root, settings=settings, force=force)


def manifest(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / "wellness/manifest.toml").read_text())


def counts(report: engine.SeriesReport) -> tuple[int, int, int, int, int]:
    return (
        report.values_added,
        report.values_changed,
        report.values_removed,
        report.canonical_days_changed,
        report.conflicts,
    )


def test_first_build_and_idempotency(tmp_path: Path) -> None:
    hub(
        tmp_path,
        [
            intervals_record("2025-04-03", restingHR=63, steps=4312),
            intervals_record("2023-02-01", weight=74),
        ],
    )
    stage(
        tmp_path,
        garmin.UDS_FORMAT,
        garmin_file_bytes(
            [
                garmin_uds_record(
                    "2025-04-03", currentDayRestingHeartRate=51, totalSteps=8351
                )
            ]
        ),
    )
    report = build(tmp_path)
    assert report.status is engine.SeriesStatus.REBUILT
    assert report.written == (
        "wellness/2023.csv",
        "wellness/2025.csv",
        "wellness/manifest.toml",
    )
    assert counts(report) == (5, 0, 0, 2, 0)
    assert report.removed == ()
    assert report.notes == ()
    assert [
        (v.day.isoformat(), v.metric.value, v.source, v.value, v.canonical)
        for v in series.read_series(tmp_path).values
    ] == [
        ("2023-02-01", "weight_kg", "intervals-icu", 74, True),
        ("2025-04-03", "resting_hr_bpm", "garmin-export", 51, True),
        ("2025-04-03", "resting_hr_bpm", "intervals-icu", 63, False),
        ("2025-04-03", "steps", "garmin-export", 8351, True),
        ("2025-04-03", "steps", "intervals-icu", 4312, False),
    ]
    doc = manifest(tmp_path)
    assert doc["inputs"] == series.inputs_digest(
        archive.list_archive(tmp_path), DEFAULT
    )
    assert doc["precedence"] == {
        "default": ["garmin-export", "apple-health", "intervals-icu"],
        "metrics": {},
    }
    assert [(e["format"], e["rules_version"], e["state"]) for e in doc["entries"]] == [
        ("garmin-uds", 1, "contributed"),
        ("intervals-icu", 1, "contributed"),
    ]
    assert [(f["path"], f["values"], f["sha256"]) for f in doc["files"]] == [
        (name, n, hashlib.sha256((tmp_path / name).read_bytes()).hexdigest())
        for name, n in [("wellness/2023.csv", 1), ("wellness/2025.csv", 4)]
    ]
    before = tree_snapshot(tmp_path / "wellness")
    for force in (False, True):
        again = build(tmp_path, force=force)
        assert again.status is engine.SeriesStatus.UNCHANGED
        assert again.written == again.removed == ()
        assert again.notes == ()
        assert counts(again) == (0, 0, 0, 0, 0)
        assert tree_snapshot(tmp_path / "wellness") == before


def test_counts_canonical_changes_and_empty_year(tmp_path: Path) -> None:
    first = hub(
        tmp_path,
        [
            intervals_record(
                "2022-01-02", updated="2024-01-01T00:00:00Z", restingHR=69
            ),
            intervals_record("2024-01-02", restingHR=65, steps=3456),
        ],
        origins={"restingHR": "garmin", "steps": "garmin"},
    )
    stage(
        tmp_path,
        garmin.UDS_FORMAT,
        garmin_file_bytes(
            [
                garmin_uds_record(
                    "2024-01-02", currentDayRestingHeartRate=65, totalSteps=3456
                )
            ]
        ),
    )
    build(tmp_path)
    settings = WellnessSettings(("intervals-icu",), {})
    moved = build(tmp_path, settings=settings)
    assert moved.status is engine.SeriesStatus.REBUILT
    assert counts(moved) == (0, 0, 0, 1, 0)
    assert manifest(tmp_path)["precedence"] == {
        "default": ["intervals-icu", "garmin-export", "apple-health"],
        "metrics": {},
    }
    first.unlink()
    hub(
        tmp_path,
        [
            intervals_record("2024-01-02", restingHR=67, steps=3456),
            intervals_record("2026-02-03", weight=72),
        ],
        origins={"restingHR": "garmin", "steps": "garmin"},
    )
    changed = build(tmp_path, settings=settings)
    assert changed.status is engine.SeriesStatus.REBUILT
    assert counts(changed) == (1, 1, 1, 3, 0)
    assert changed.removed == ("wellness/2022.csv",)
    assert not (tmp_path / "wellness/2022.csv").exists()
    for entry in archive.list_archive(tmp_path).entries:
        entry.path.unlink()
    empty = build(tmp_path)
    assert empty.status is engine.SeriesStatus.REBUILT
    assert counts(empty) == (0, 0, 5, 2, 0)
    assert empty.written == ()
    assert empty.removed == (
        "wellness/2024.csv",
        "wellness/2026.csv",
        "wellness/manifest.toml",
    )
    assert list((tmp_path / "wellness").iterdir()) == []
    assert build(tmp_path).status is engine.SeriesStatus.UNCHANGED
    (tmp_path / "wellness/manifest.toml").write_bytes(
        series.encode_manifest(
            series.Manifest(
                series.inputs_digest(archive.list_archive(tmp_path), DEFAULT)
            )
        )
    )
    assert build(tmp_path).status is engine.SeriesStatus.REBUILT
    assert not (tmp_path / "wellness/manifest.toml").exists()


@pytest.mark.parametrize(
    "change",
    [
        "added",
        "settings",
        "rules",
        "edited",
        "deleted",
        "manifest_missing",
        "extra_year",
    ],
)
def test_assess_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    settings = DEFAULT
    if change == "added":
        hub(tmp_path, [intervals_record("2026-01-01", weight=71)])
    elif change == "settings":
        settings = WellnessSettings((), {Metric.WEIGHT_KG: ("intervals-icu",)})
    elif change == "rules":
        monkeypatch.setattr(
            registry,
            "FORMATS",
            tuple(
                replace(f, rules_version=9) if f.id == "intervals-icu" else f
                for f in registry.FORMATS
            ),
        )
    elif change == "edited":
        path = tmp_path / "wellness/2024.csv"
        path.write_bytes(path.read_bytes().replace(b"73", b"79"))
    elif change == "deleted":
        (tmp_path / "wellness/2024.csv").unlink()
    elif change == "manifest_missing":
        (tmp_path / "wellness/manifest.toml").unlink()
    else:
        (tmp_path / "wellness/2021.csv").write_text(series.SERIES_HEADER + "\n")
    assessment = engine.assess_series(
        tmp_path, archive.list_archive(tmp_path), settings
    )
    assert not assessment.fresh
    assert assessment.reasons
    assert assessment.blocked == assessment.unreadable == ()
    assert build(tmp_path, settings=settings).status is engine.SeriesStatus.REBUILT
    assert engine.assess_series(
        tmp_path, archive.list_archive(tmp_path), settings
    ).fresh
    if change == "settings":
        assert manifest(tmp_path)["precedence"]["metrics"] == {
            "weight_kg": ["intervals-icu", "garmin-export", "apple-health"]
        }


def test_assessment_metadata_only_and_ignores_other_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    unrelated = tmp_path / "wellness/notes.txt"
    unrelated.write_text("private note")
    listing = archive.list_archive(tmp_path)
    original = Path.open

    def no_archive(path: Path, *args: Any, **kwargs: Any) -> Any:
        if "wellness-archive" in path.parts or path == unrelated:
            raise AssertionError("unexpected file read")
        return original(path, *args, **kwargs)

    before = tree_snapshot(tmp_path / "wellness")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", no_archive)
        assert engine.assess_series(
            tmp_path, listing, DEFAULT
        ) == engine.SeriesAssessment(True, (), (), ())
        assert build(tmp_path).status is engine.SeriesStatus.UNCHANGED
    assert tree_snapshot(tmp_path / "wellness") == before


@pytest.mark.parametrize(
    "location,kind",
    [
        (location, kind)
        for location in ("year", "manifest", "root")
        for kind in ("directory", "symlink", "foreign")
        if (location, kind) != ("root", "directory")
    ],
)
def test_occupied(tmp_path: Path, location: str, kind: str) -> None:
    hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    path = (
        tmp_path
        / {
            "year": "wellness/2024.csv",
            "manifest": "wellness/manifest.toml",
            "root": "wellness",
        }[location]
    )
    original_bytes = path.read_bytes() if location != "root" else b""
    if location == "root":
        for child in path.iterdir():
            child.unlink()
        path.rmdir()
    else:
        path.unlink()
    target = tmp_path / "target"
    if location == "root":
        target.mkdir()
        (target / "sentinel.txt").write_text("outside bytes")
    else:
        target.write_bytes(original_bytes)
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(target)
    else:
        path.write_text("foreign bytes")
    before = tree_snapshot(tmp_path)
    report = build(tmp_path, force=True)
    assert report.status is engine.SeriesStatus.BLOCKED
    assert [(note.subject, bool(note.detail)) for note in report.notes] == [
        (path.relative_to(tmp_path).as_posix(), True)
    ]
    assert report.written == report.removed == ()
    assert tree_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "document",
    [
        "series_version = 1\n",
        'generator = "other"\n',
        "broken = [",
        'generator = "fitdocs"\nseries_version = 999\n',
    ],
)
def test_manifest_ownership_and_newer(tmp_path: Path, document: str) -> None:
    hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    (tmp_path / "wellness/manifest.toml").write_text(document)
    before = tree_snapshot(tmp_path / "wellness")
    report = build(tmp_path, force=True)
    assert report.status is engine.SeriesStatus.BLOCKED
    assert report.notes[0].subject == "wellness/manifest.toml"
    if "999" in document:
        assert "written by a newer fitdocs" in report.notes[0].detail
    assert tree_snapshot(tmp_path / "wellness") == before


@pytest.mark.parametrize("target", ["entry", "year", "manifest"])
def test_read_io_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    path = hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    blocked = {
        "entry": path,
        "year": tmp_path / "wellness/2024.csv",
        "manifest": tmp_path / "wellness/manifest.toml",
    }[target]
    before = tree_snapshot(tmp_path / "wellness")
    original = Path.open

    def unavailable(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == blocked:
            raise OSError("cloud file offline")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", unavailable)
        report = build(tmp_path, force=True)
    assert report.status is engine.SeriesStatus.DEFERRED
    assert report.notes == (
        engine.SeriesNote(
            blocked.relative_to(tmp_path).as_posix(), "cloud file offline"
        ),
    )
    assert tree_snapshot(tmp_path / "wellness") == before


def test_all_unreadable_entries_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [
        hub(tmp_path, [intervals_record(day, weight=value)])
        for day, value in [("2023-02-01", 71), ("2024-02-01", 72)]
    ]
    build(tmp_path)
    before = tree_snapshot(tmp_path / "wellness")
    original = Path.open

    def unavailable(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path in paths:
            raise OSError("offline")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", unavailable)
        report = build(tmp_path, force=True)
    assert report.status is engine.SeriesStatus.DEFERRED
    assert report.notes == tuple(
        engine.SeriesNote(path.relative_to(tmp_path).as_posix(), "offline")
        for path in sorted(paths)
    )
    assert tree_snapshot(tmp_path / "wellness") == before


def test_invalid_entry_leaves_all_existing_files(tmp_path: Path) -> None:
    path = hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    hub(tmp_path, [intervals_record("2026-02-03", weight=71)])
    path.write_bytes(b"broken JSON")
    before = tree_snapshot(tmp_path / "wellness")
    report = build(tmp_path, force=True)
    assert report.status is engine.SeriesStatus.FAILED
    assert report.notes[0].subject == path.relative_to(tmp_path).as_posix()
    assert report.notes[0].detail
    assert tree_snapshot(tmp_path / "wellness") == before


def extracts(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    monkeypatch.setattr(registry, "FORMATS", (*registry.FORMATS, EXTRACT_FORMAT))
    monkeypatch.setattr(registry, "SOURCES", (*registry.SOURCES, EXTRACT_SOURCE))
    return [
        stage(
            root,
            EXTRACT_FORMAT,
            build_extract(order, corrupt_body=corrupt).replace(b"73.25", value),
            token * 64,
        )
        for token, order, corrupt, value in [
            ("9", "01", True, b"89.5"),
            ("2", "09", False, b"61.5"),
            ("f", "03", False, b"99.5"),
        ]
    ]


def test_latest_entry_before_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = extracts(tmp_path, monkeypatch)
    report = build(tmp_path)
    assert report.status is engine.SeriesStatus.REBUILT
    assert {e["path"]: e["state"] for e in manifest(tmp_path)["entries"]} == {
        p.relative_to(tmp_path).as_posix(): (
            "contributed" if p == paths[1] else "superseded"
        )
        for p in paths
    }
    assert [(v.value, v.source) for v in series.read_series(tmp_path).values] == [
        (61.5, "test-extract")
    ]


def test_latest_entry_ref_tie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = extracts(tmp_path, monkeypatch)
    paths[0].write_bytes(build_extract("09").replace(b"73.25", b"55.5"))
    assert build(tmp_path).status is engine.SeriesStatus.REBUILT
    assert [v.value for v in series.read_series(tmp_path).values] == [55.5]


@pytest.mark.parametrize("failure", ["header", "io", "body"])
def test_latest_entry_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    paths = extracts(tmp_path, monkeypatch)
    build(tmp_path)
    before = tree_snapshot(tmp_path / "wellness")
    target = paths[1] if failure == "body" else paths[0]
    original = Path.open

    def unavailable(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == target:
            raise OSError("offline order")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        if failure == "header":
            target.write_bytes(b"bad header\n")
        elif failure == "body":
            target.write_bytes(build_extract("09", corrupt_body=True))
        else:
            patch.setattr(Path, "open", unavailable)
        report = build(tmp_path, force=True)
    assert report.status is (
        engine.SeriesStatus.DEFERRED if failure == "io" else engine.SeriesStatus.FAILED
    )
    assert report.notes[0].subject == target.relative_to(tmp_path).as_posix()
    assert report.notes[0].detail
    assert tree_snapshot(tmp_path / "wellness") == before


def test_conflicts_recorded(tmp_path: Path) -> None:
    low = stage(
        tmp_path,
        intervals.FORMAT,
        intervals_list_bytes([intervals_record("2024-03-02", restingHR=82)]),
        "1" * 64,
    )
    high = stage(
        tmp_path,
        intervals.FORMAT,
        intervals_list_bytes([intervals_record("2024-03-02", restingHR=55)]),
        "f" * 64,
    )
    report = build(tmp_path)
    assert counts(report) == (1, 0, 0, 1, 1)
    assert manifest(tmp_path)["conflicts"] == [
        {
            "day": date(2024, 3, 2),
            "metric": "resting_hr_bpm",
            "source": "intervals-icu",
            "kept_entry": high.relative_to(tmp_path).as_posix(),
            "kept_value": 55.0,
            "other_entries": [low.relative_to(tmp_path).as_posix()],
            "other_values": [82.0],
        }
    ]
    assert build(tmp_path).conflicts == 1


def test_atomic_manifest_last_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub(
        tmp_path,
        [
            intervals_record("2025-02-03", weight=73),
            intervals_record("2023-02-03", weight=71),
        ],
    )
    calls = []
    original = os.replace

    def replacing(src: Any, dst: Any) -> None:
        src, dst = Path(src), Path(dst)
        calls.append(
            (
                src.parent == dst.parent,
                src.name.startswith("."),
                src.read_bytes(),
                dst.relative_to(tmp_path).as_posix(),
            )
        )
        original(src, dst)

    monkeypatch.setattr(os, "replace", replacing)
    build(tmp_path)
    assert [(a, b, d) for a, b, _, d in calls] == [
        (True, True, "wellness/2023.csv"),
        (True, True, "wellness/2025.csv"),
        (True, True, "wellness/manifest.toml"),
    ]
    assert all(data for _, _, data, _ in calls)
    assert not list((tmp_path / "wellness").glob(".*"))


def test_staging_error_preserves_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    hub(tmp_path, [intervals_record("2026-02-03", weight=71)])
    before = tree_snapshot(tmp_path / "wellness")

    original = tempfile.mkstemp
    openings = 0

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        nonlocal openings
        openings += 1
        if openings == 2:
            raise OSError("disk unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", unavailable)
    report = build(tmp_path)
    assert report.status is engine.SeriesStatus.DEFERRED
    assert report.notes[0].detail == "disk unavailable"
    assert tree_snapshot(tmp_path / "wellness") == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads chmod 000 files")
@pytest.mark.parametrize("latest", [False, True])
def test_chmod_entry_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, latest: bool
) -> None:
    path = (
        extracts(tmp_path, monkeypatch)[0]
        if latest
        else hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    )
    build(tmp_path)
    before = tree_snapshot(tmp_path / "wellness")
    path.chmod(0)
    try:
        report = build(tmp_path, force=True)
    finally:
        path.chmod(0o600)
    assert report.status is engine.SeriesStatus.DEFERRED
    assert report.notes[0].subject == path.relative_to(tmp_path).as_posix()
    assert tree_snapshot(tmp_path / "wellness") == before


def test_new_destination_occupied_during_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub(tmp_path, [intervals_record("2024-02-03", weight=73)])
    build(tmp_path)
    hub(tmp_path, [intervals_record("2026-02-03", weight=71)])
    before = tree_snapshot(tmp_path / "wellness")
    original = archive.parse_entry

    def occupy(entry: archive.ArchiveEntry) -> Any:
        (tmp_path / "wellness/2026.csv").write_text("foreign content")
        return original(entry)

    monkeypatch.setattr(engine, "parse_entry", occupy)
    report = build(tmp_path)
    assert report.status is engine.SeriesStatus.BLOCKED
    assert report.notes == (
        engine.SeriesNote(
            "wellness/2026.csv", "foreign year file: wrong series header"
        ),
    )
    assert (tmp_path / "wellness/2026.csv").read_text() == "foreign content"
    assert {
        name: item
        for name, item in tree_snapshot(tmp_path / "wellness").items()
        if name != "2026.csv"
    } == before


@pytest.mark.parametrize("canonical", [True, False])
def test_origin_only_changes(tmp_path: Path, canonical: bool) -> None:
    hub(
        tmp_path,
        [intervals_record("2024-02-03", updated="2024-03-01T00:00:00Z", restingHR=63)],
        origins={"restingHR": "apple"},
    )
    if not canonical:
        stage(
            tmp_path,
            garmin.UDS_FORMAT,
            garmin_file_bytes(
                [garmin_uds_record("2024-02-03", currentDayRestingHeartRate=51)]
            ),
        )
    build(tmp_path)
    expected = (
        [("intervals-icu", "apple", 63, True)]
        if canonical
        else [
            ("garmin-export", "garmin", 51, True),
            ("intervals-icu", "apple", 63, False),
        ]
    )
    assert [
        (value.source, value.origin, value.value, value.canonical)
        for value in series.read_series(tmp_path).values
    ] == expected
    hub(
        tmp_path,
        [intervals_record("2024-02-03", updated="2024-03-02T00:00:00Z", restingHR=63)],
        origins={"restingHR": "polar"},
    )
    report = build(tmp_path)
    assert report.status is engine.SeriesStatus.REBUILT
    assert counts(report) == (0, 1, 0, int(canonical), 0)
    assert [
        (value.source, value.origin, value.value, value.canonical)
        for value in series.read_series(tmp_path).values
    ] == [
        (source, "polar" if source == "intervals-icu" else origin, number, selected)
        for source, origin, number, selected in expected
    ]


def test_every_unreadable_latest_header_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = extracts(tmp_path, monkeypatch)
    build(tmp_path)
    before = tree_snapshot(tmp_path / "wellness")
    failures = {paths[2]: "remote header unavailable", paths[0]: "header access denied"}
    original = Path.open

    def unavailable(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path in failures:
            raise OSError(failures[path])
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", unavailable)
        report = build(tmp_path, force=True)
    assert report.status is engine.SeriesStatus.DEFERRED
    assert report.notes == tuple(
        engine.SeriesNote(path.relative_to(tmp_path).as_posix(), failures[path])
        for path in sorted(failures)
    )
    assert report.written == report.removed == ()
    assert tree_snapshot(tmp_path / "wellness") == before
