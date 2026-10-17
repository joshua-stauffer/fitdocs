"""Synthetic Apple exports through the real inbox drain."""

from __future__ import annotations

import gzip
import hashlib
import json
import tomllib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest

from fitdocs.inbox import DEFAULT_INBOX_SETTINGS, Disposition, InboxNote
from fitdocs.layout import DECLARED_DIRS
from fitdocs.quarantine import load_quarantine
from fitdocs.sync import DrainReport, drain
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileStore
from fitdocs.wellness import read_series
from fitdocs.wellness.formats import apple
from fitdocs.wellness.formats.apple.reader import iter_items, open_main_document
from tests.wellness._helpers import tree_snapshot
from tests.wellness.apple.builders import (
    WATCH,
    export_document,
    export_zip,
    record_xml,
)

Progress = Callable[[str, int, int], None]
_APPLE_WATCH = replace(WATCH, device="manufacturer:Apple Inc., model:Watch")


def document(value: str = "53", *, date: str = "06", **kwargs: Any) -> bytes:
    records = [
        record_xml(
            "HKQuantityTypeIdentifierRestingHeartRate",
            writer=_APPLE_WATCH,
            value=value,
            unit="count/min",
        )
    ]
    return export_document(
        records, export_date=f"2024-02-{date} 14:30:00 -0800", **kwargs
    )


def put(inbox: Path, name: str, payload: bytes) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / name
    path.write_bytes(payload)
    return path


def run_drain(
    inbox: Path,
    root: Path,
    *,
    progress: Progress | None = None,
    move: bool = False,
) -> DrainReport:
    return drain(
        inbox,
        root,
        settings=replace(
            DEFAULT_INBOX_SETTINGS,
            settle_seconds=0,
            disposition=Disposition.MOVE if move else Disposition.LEAVE,
        ),
        processed_dir=root / "processed",
        quarantine=load_quarantine(root),
        athlete=None,
        tz=UTC,
        tiles=TileStore(root, replace(DEFAULT_TILE_SETTINGS, enabled=False)),
        wellness_progress=progress,
    )


def ref(payload: bytes) -> str:
    return (
        f"wellness-archive/apple-health/{hashlib.sha256(payload).hexdigest()}.jsonl.gz"
    )


def values(root: Path) -> list[tuple[str, str, str, str | None, float]]:
    return [
        (v.day.isoformat(), v.metric.value, v.source, v.origin, v.value)
        for v in read_series(root).values
    ]


def states(root: Path) -> dict[str, str]:
    manifest = tomllib.loads((root / "wellness/manifest.toml").read_text())
    return {entry["path"]: entry["state"] for entry in manifest["entries"]}


def years(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        k: v for k, v in tree_snapshot(root / "wellness").items() if k.endswith(".csv")
    }


def test_zip_archive_provenance_progress_and_confinement(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    xml = document(extra_elements=["<Ignored>" + "x" * 3_000_000 + "</Ignored>"])
    payload = export_zip(xml)
    candidate = put(inbox, "arbitrary-name.zip", payload)
    source = (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    put(root, "athlete-note.md", b"athlete-owned text\n")
    before = tree_snapshot(root)
    progress: list[tuple[str, int, int]] = []
    report = run_drain(inbox, root, progress=lambda *args: progress.append(args))
    entry = root / ref(payload)
    header = json.loads(gzip.decompress(entry.read_bytes()).splitlines()[0])
    assert (
        report.wellness_archived,
        sorted(root.glob("wellness-archive/apple-health/*")),
    ) == ((InboxNote(candidate.name, f"{ref(payload)} (apple-health)"),), [entry])
    assert (header["original_sha256"], header["original_size"]) == (
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    assert values(root) == [
        ("2024-02-02", "resting_hr_bpm", "apple-health", "apple", 53.0)
    ]
    percents = [done * 100 // total for _, done, total in progress]
    assert (
        len(percents) > 1 and percents == sorted(set(percents)) and percents[-1] == 100
    )
    assert {name for name, _, _ in progress} == {candidate.name}
    assert {total for _, _, total in progress} == {len(xml)}
    assert (
        candidate.is_file() and (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    ) == source
    after = tree_snapshot(root)
    changed = {
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    }
    assert ref(payload) in changed and "wellness/2024.csv" in changed
    declarations = {f"{directory}AGENTS.md" for directory in DECLARED_DIRS}
    assert changed <= declarations | {ref(payload)} | {
        "wellness/2024.csv",
        "wellness/manifest.toml",
    }


def test_second_drain_skips_without_extraction_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    payload = export_zip(document())
    put(inbox, "export.zip", payload)
    calls: list[Path] = []
    original = open_main_document

    def observed(path: Path) -> Any:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(apple, "open_main_document", observed)
    run_drain(inbox, root)
    assert calls == [inbox / "export.zip"]
    before = tree_snapshot(root)
    assert "wellness/2024.csv" in before and values(root)[0][-1] == 53
    calls.clear()
    report = run_drain(inbox, root)
    assert (report.wellness_archived, report.wellness_skipped, calls) == (
        (),
        (InboxNote("export.zip", f"{ref(payload)} (apple-health)"),),
        [],
    )
    assert tree_snapshot(root) == before


@pytest.mark.parametrize("phase", ["bare", "later", "older"])
def test_supersession_and_unchanged_archives(tmp_path: Path, phase: str) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    xml = document(
        extra_elements=[
            record_xml(
                "HKQuantityTypeIdentifierBodyMass",
                value="73.25",
                unit="kg",
                start="2023-12-30 10:00:00 -0800",
                end="2023-12-30 10:01:00 -0800",
            )
        ]
    )
    zipped = export_zip(xml)
    put(inbox, "export.zip", zipped)
    run_drain(inbox, root)
    old_archive = tree_snapshot(root / "wellness-archive")
    original_years = years(root)
    put(inbox, "same.xml", xml)
    run_drain(inbox, root)
    if phase == "bare":
        winner = max(ref(xml), ref(zipped))
        assert states(root) == {
            r: "contributed" if r == winner else "superseded"
            for r in [ref(xml), ref(zipped)]
        }
        assert years(root) == original_years
    else:
        later = document("41", date="09")
        put(inbox, "later.zip", export_zip(later))
        run_drain(inbox, root)
        if phase == "older":
            before = years(root)
            older = document("89", date="03")
            while ref(older) < ref(export_zip(later)):
                older = older.replace(
                    b"</HealthData>", b"<!--ref tie decoy--></HealthData>"
                )
            put(inbox, "older.xml", older)
            archived = run_drain(inbox, root)
            assert archived.wellness_archived == (
                InboxNote("older.xml", f"{ref(older)} (apple-health)"),
            )
            assert years(root) == before
        expected = {
            ref(zipped): "superseded",
            ref(xml): "superseded",
            ref(export_zip(later)): "contributed",
        }
        if phase == "older":
            expected[ref(older)] = "superseded"
        assert states(root) == expected
        assert values(root) == [
            ("2024-02-02", "resting_hr_bpm", "apple-health", "apple", 41.0)
        ]
    assert {
        key: val
        for key, val in tree_snapshot(root / "wellness-archive").items()
        if key in old_archive
    } == old_archive


def test_all_defects_corrections_are_archived(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    xml = document(
        malformed_doctype=True, control_character=True, duplicate_start_date=True
    )
    put(inbox, "defective.zip", export_zip(xml))
    report = run_drain(inbox, root)
    lines = gzip.decompress((root / ref(export_zip(xml))).read_bytes()).splitlines()
    assert report.wellness_failures == () and len(report.wellness_archived) == 1
    assert json.loads(lines[-1])["end"] == {
        "records": 1,
        "corrections": {
            "doctype_removed": 1,
            "control_characters_removed": 1,
            "duplicate_attributes_removed": 1,
        },
    }
    assert values(root) == [
        ("2024-02-02", "resting_hr_bpm", "apple-health", "apple", 53.0)
    ]


@pytest.mark.parametrize("fault", ["malformed", "unit"])
def test_failure_is_atomic_and_quarantined_without_reextracting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    put(inbox, "good.zip", export_zip(document()))
    run_drain(inbox, root)
    before = tree_snapshot(root / "wellness")
    assert values(root)[0][-1] == 53 and "2024.csv" in before
    xml = document("71", date="09", include_doctype=False)
    xml = (
        xml.replace(b"</HealthData>", b"<broken></HealthData>")
        if fault == "malformed"
        else xml.replace(b'unit="count/min"', b'unit="bananas"')
    )
    candidate = put(inbox, "bad.xml", xml)
    source = (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    calls: list[Path] = []
    original = open_main_document

    def observed(path: Path) -> Any:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(apple, "open_main_document", observed)
    report = run_drain(inbox, root, move=True)
    assert (
        len(report.wellness_failures) == 1
        and report.wellness_failures[0].subject == "bad.xml"
    )
    reason = report.wellness_failures[0].detail
    assert (
        (
            reason
            == (
                "the export could not be read at line 9, column 10: "
                "mismatched tag: line 9, column 10"
            )
        )
        if fault == "malformed"
        else reason
        == (
            "HKQuantityTypeIdentifierRestingHeartRate: unknown unit 'bananas'; "
            "startDate='2024-02-02 22:00:00 -0800'"
        )
    ), reason
    assert [(e.sha256, e.name, e.reason) for e in load_quarantine(root).entries] == [
        (hashlib.sha256(xml).hexdigest(), "bad.xml", reason)
    ]
    assert calls == [candidate]
    assert not (root / ref(xml)).exists() and not list(
        (root / "wellness-archive").rglob(".incoming-*")
    )
    assert tree_snapshot(root / "wellness") == before
    assert (
        candidate.is_file() and (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    ) == source
    calls.clear()
    second = run_drain(inbox, root, move=True)
    assert (second.quarantined, second.wellness_failures, calls) == (
        (InboxNote("bad.xml", reason),),
        (),
        [],
    )
    assert not list((root / "wellness-archive").rglob(".incoming-*"))
    assert tree_snapshot(root / "wellness") == before
    assert (
        candidate.is_file() and (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    ) == source


def test_in_place_already_read_rewrite_defers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    xml = document(
        include_doctype=False,
        extra_elements=["<Ignored>" + "x" * 3_000_000 + "</Ignored>"],
    )
    candidate = put(inbox, "changing.xml", xml)
    offset = xml.index(b'value="53"') + len(b'value="')
    observations: list[tuple[int, int, int, bool]] = []

    def change(name: str, done: int, total: int) -> None:
        if not observations:
            observations.append(
                (
                    done,
                    total,
                    offset,
                    bool(list((root / "wellness-archive").rglob(".incoming-*"))),
                )
            )
            with candidate.open("r+b") as stream:
                stream.seek(offset)
                stream.write(b"59")

    parsed: list[bool] = []
    original = iter_items

    def items(*args: Any, **kwargs: Any) -> Any:
        yield from original(*args, **kwargs)
        parsed.append(True)

    monkeypatch.setattr(apple, "iter_items", items)
    report = run_drain(inbox, root, progress=change)
    assert parsed == [True]
    assert (
        len(observations) == 1
        and offset + 2 < observations[0][0] < observations[0][1] == len(xml)
        and observations[0][3]
    )
    assert (
        len(candidate.read_bytes()) == len(xml)
        and candidate.read_bytes()[offset : offset + 2] == b"59"
    )
    assert (report.deferred, report.wellness_failures, report.wellness_archived) == (
        (InboxNote("changing.xml", "candidate changed during the run"),),
        (),
        (),
    )
    assert not (root / ref(xml)).exists() and not list(
        (root / "wellness-archive").rglob(".incoming-*")
    )
    assert years(root) == {} and load_quarantine(root).entries == ()


def test_transient_read_error_at_extraction_defers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    payload = export_zip(document())
    put(inbox, "flaky.zip", payload)
    faults: list[str] = []
    armed: list[bool] = []

    class Flaky:
        def __init__(self, stream: Any) -> None:
            self._stream = stream

        def __enter__(self) -> Flaky:
            return self

        def __exit__(self, *args: object) -> None:
            self._stream.close()

        def read(self, size: int = -1) -> bytes:
            if not faults:
                faults.append("read")
                raise OSError("transient read failure")
            return self._stream.read(size)  # type: ignore[no-any-return]

        def __getattr__(self, name: str) -> Any:
            return getattr(self._stream, name)

    real_open = Path.open

    def flaky_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        stream = real_open(self, *args, **kwargs)
        return Flaky(stream) if armed and self.name == "flaky.zip" else stream

    original = open_main_document

    def arm(*args: Any, **kwargs: Any) -> Any:
        armed.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(apple, "open_main_document", arm)
    monkeypatch.setattr(Path, "open", flaky_open)
    first = run_drain(inbox, root)
    assert faults == ["read"]
    assert (first.wellness_failures, first.quarantined, first.wellness_archived) == (
        (),
        (),
        (),
    )
    assert [note.subject for note in first.deferred] == ["flaky.zip"]
    assert load_quarantine(root).entries == ()
    assert years(root) == {} and not (root / ref(payload)).exists()
    second = run_drain(inbox, root)
    assert [note.subject for note in second.wellness_archived] == ["flaky.zip"]


def test_progress_interrupt_propagates_and_cleans_temp(tmp_path: Path) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    xml = document(extra_elements=["<Ignored>" + "x" * 3_000_000 + "</Ignored>"])
    candidate = put(inbox, "interrupt.xml", xml)
    source = (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    calls: list[tuple[int, int, bool]] = []

    def interrupt(name: str, done: int, total: int) -> None:
        calls.append(
            (done, total, bool(list((root / "wellness-archive").rglob(".incoming-*"))))
        )
        raise KeyboardInterrupt("stop synthetic import")

    with pytest.raises(KeyboardInterrupt, match="stop synthetic import"):
        run_drain(inbox, root, progress=interrupt)
    assert len(calls) == 1 and 0 < calls[0][0] < calls[0][1] == len(xml) and calls[0][2]
    assert not (root / ref(xml)).exists() and not list(
        (root / "wellness-archive").rglob(".incoming-*")
    )
    assert (
        candidate.is_file() and (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    ) == source


@pytest.mark.parametrize("move", [False, True])
def test_disposition_preserves_original(tmp_path: Path, move: bool) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    payload = export_zip(document())
    candidate = put(inbox, "export.zip", payload)
    source = (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    report = run_drain(inbox, root, move=move)
    destination = root / "processed/export.zip" if move else candidate
    assert report.moved == ((str(destination),) if move else ())
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == source
    assert candidate.exists() is (not move)


@pytest.mark.parametrize(
    "name,payload",
    [
        ("other.zip", export_zip(variant="garmin")),
        ("export_cda.xml", b"<ClinicalDocument/>"),
        ("other.xml", b"<Other/>"),
    ],
    ids=["garmin", "clinical", "other"],
)
def test_unrecognized_stays_in_place_under_move(
    tmp_path: Path, name: str, payload: bytes
) -> None:
    inbox, root = tmp_path / "inbox", tmp_path / "data"
    candidate = put(inbox, name, payload)
    source = (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    report = run_drain(inbox, root, move=True)
    assert [note.subject for note in report.unrecognized] == [name]
    assert (report.wellness_archived, report.wellness_failures, report.moved) == (
        (),
        (),
        (),
    )
    assert (
        candidate.is_file() and (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    ) == source
