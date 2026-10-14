"""Intake decisions over synthetic wellness deliveries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from fitdocs.wellness import archive, intake
from fitdocs.wellness.formats import intervals
from fitdocs.wellness.probe import HEAD_BYTES, CandidateProbe
from fitdocs.wellness.spec import FormatSpec
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    ORIGINAL_FORMAT,
    ORIGINAL_SOURCE,
    CountingOpener,
    build_extract,
    tree_snapshot,
    use_formats,
)
from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record

ORIGINAL = b'{"test_original":true,"day":"2024-03-02","value":51}\n'


def candidate(tmp_path: Path, content: bytes = ORIGINAL) -> Path:
    path = tmp_path / "candidate.json"
    path.write_bytes(content)
    return path


def identified(
    form: FormatSpec = ORIGINAL_FORMAT, content: bytes = ORIGINAL
) -> intake.Identified:
    return intake.Identified(form, hashlib.sha256(content).hexdigest(), len(content))


def expected_entry(data_root: Path, item: intake.Identified) -> archive.ArchiveEntry:
    ref = (
        f"wellness-archive/{item.format.id}/{item.sha256}{item.format.archived_suffix}"
    )
    return archive.ArchiveEntry(item.format, item.sha256, data_root / ref, ref)


def test_identify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(monkeypatch, [ORIGINAL_FORMAT], [ORIGINAL_SOURCE])
    path = candidate(tmp_path)
    before = tree_snapshot(tmp_path)
    assert intake.identify(path) == identified()
    assert tree_snapshot(tmp_path) == before


@pytest.mark.parametrize("ambiguous", [False, True], ids=["unknown", "ambiguous"])
def test_unrecognized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ambiguous: bool
) -> None:
    other = replace(ORIGINAL_FORMAT, id="another-format")
    use_formats(
        monkeypatch, [ORIGINAL_FORMAT, other] if ambiguous else [], [ORIGINAL_SOURCE]
    )
    path = candidate(tmp_path)

    def no_hash(path: Path) -> Any:
        pytest.fail("unrecognized candidate was hashed")

    monkeypatch.setattr(intake, "hash_file", no_hash)
    before = tree_snapshot(tmp_path)
    reason = (
        "multiple wellness formats read this file: test-original, another-format"
        if ambiguous
        else "no supported wellness format reads this file"
    )
    assert intake.identify(path) == intake.IntakeUnrecognized(reason)
    assert tree_snapshot(tmp_path) == before


@pytest.mark.parametrize("stage", ["probe", "recognize", "hash"])
def test_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    use_formats(monkeypatch, [ORIGINAL_FORMAT], [ORIGINAL_SOURCE])
    path = candidate(tmp_path)

    def fail(*args: object) -> Any:
        raise OSError(f"{stage} unavailable")

    if stage == "probe":
        monkeypatch.setattr(CandidateProbe, "open", fail)
    elif stage == "recognize":
        monkeypatch.setattr(intake, "recognize", fail)
    else:
        monkeypatch.setattr(intake, "hash_file", fail)
    before = tree_snapshot(tmp_path)
    assert intake.identify(path) == intake.IntakeDeferred(
        f"could not be read ({stage} unavailable); "
        "left in place and retried on a later drain"
    )
    assert tree_snapshot(tmp_path) == before


def test_real_lazy_recognizer_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = (
        intervals_list_bytes([intervals_record("2024-05-06", restingHR=43)])
        + b" " * HEAD_BYTES
    )
    path = candidate(tmp_path, content)
    opener = CountingOpener(path, fail_past_head=True)
    opener.install(monkeypatch)
    assert intake.identify(path) == intake.IntakeDeferred(
        "could not be read (candidate unavailable past head); "
        "left in place and retried on a later drain"
    )
    assert [(read.start, read.requested) for read in opener.reads] == [(0, HEAD_BYTES)]
    assert opener.opens == 2


@pytest.mark.parametrize("version", [2, 17])
def test_newer_delivery(tmp_path: Path, version: int) -> None:
    content = json.dumps(
        {"format": intervals.DELIVERY_FORMAT, "version": version, "records": []}
    ).encode()
    path = candidate(tmp_path, content)
    assert intake.identify(path) == intake.IntakeUnrecognized(
        f"written by a newer fitdocs (delivery version {version})"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"format": "other", "version": 2},
        {"format": intervals.DELIVERY_FORMAT, "version": 1, "records": []},
        [1],
        None,
    ],
)
def test_delivery_reason_is_specific(tmp_path: Path, payload: object) -> None:
    path = candidate(tmp_path, json.dumps(payload).encode())
    result = intake.identify(path)
    if isinstance(payload, dict) and payload.get("format") == intervals.DELIVERY_FORMAT:
        assert result == identified(intervals.FORMAT, path.read_bytes())
    else:
        assert result == intake.IntakeUnrecognized(
            "no supported wellness format reads this file"
        )


@pytest.mark.parametrize(
    "form,content",
    [(ORIGINAL_FORMAT, ORIGINAL), (EXTRACT_FORMAT, build_extract("2024-07-08"))],
    ids=["original", "extract"],
)
def test_archive_fresh(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    form: FormatSpec,
    content: bytes,
) -> None:
    use_formats(monkeypatch, [form], [form.source])
    path = candidate(tmp_path, content)
    item = identified(form, content)
    entry = expected_entry(data_root, item)
    assert not entry.path.exists()
    source_before = (path.read_bytes(), path.stat().st_mtime_ns)
    progress: list[tuple[int, int]] = []
    result = intake.archive_identified(
        data_root, path, item, lambda read, total: progress.append((read, total))
    )
    assert result == intake.Archived(entry)
    assert entry.path.read_bytes() == content
    assert (path.read_bytes(), path.stat().st_mtime_ns) == source_before
    assert list(data_root.rglob(".incoming-*")) == []
    assert progress == (
        [(len(content), len(content))] if form is EXTRACT_FORMAT else []
    )


@pytest.mark.parametrize(
    "form,content",
    [(ORIGINAL_FORMAT, ORIGINAL), (EXTRACT_FORMAT, build_extract("2024-07-08"))],
    ids=["original", "extract"],
)
def test_already_archived(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    form: FormatSpec,
    content: bytes,
) -> None:
    form = replace(form, id=f"{form.id}-format")
    path = candidate(tmp_path, content)
    item = identified(form, content)
    entry = expected_entry(data_root, item)
    entry.path.parent.mkdir(parents=True)
    entry.path.write_bytes(b"kept entry need not be parsed")
    before = tree_snapshot(tmp_path)
    opener = CountingOpener(path)
    opener.install(monkeypatch)

    def no_commit(*args: object) -> Any:
        pytest.fail("duplicate reached archive commit")

    monkeypatch.setattr(archive, "commit_original", no_commit)
    monkeypatch.setattr(archive, "commit_extract", no_commit)
    assert intake.archive_identified(
        data_root, path, item, None
    ) == intake.AlreadyArchived(entry)
    assert opener.opens == 0
    assert tree_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "form,content",
    [(ORIGINAL_FORMAT, ORIGINAL), (EXTRACT_FORMAT, build_extract("2024-07-08"))],
    ids=["original", "extract"],
)
def test_source_directory_is_not_a_duplicate(
    data_root: Path,
    tmp_path: Path,
    form: FormatSpec,
    content: bytes,
) -> None:
    form = replace(form, id=f"{form.id}-format")
    path = candidate(tmp_path, content)
    item = identified(form, content)
    entry = expected_entry(data_root, item)
    decoy = (
        data_root
        / "wellness-archive"
        / form.source.id
        / f"{item.sha256}{form.archived_suffix}"
    )
    decoy.parent.mkdir(parents=True)
    decoy.write_bytes(b"source-directory decoy")
    decoy_before = (decoy.read_bytes(), decoy.stat().st_mtime_ns)
    assert not entry.path.exists()
    assert intake.archive_identified(data_root, path, item, None) == intake.Archived(
        entry
    )
    assert entry.path.read_bytes() == content
    assert (decoy.read_bytes(), decoy.stat().st_mtime_ns) == decoy_before


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (archive.Committed, None),
        (archive.Exists, None),
        (archive.Changed, intake.IntakeDeferred),
        (archive.Unreadable, intake.IntakeDeferred),
        (archive.Invalid, intake.Failed),
    ],
    ids=["committed", "exists", "changed", "unreadable", "invalid"],
)
def test_commit_outcomes(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: Any,
    expected: Any,
) -> None:
    path = candidate(tmp_path)
    item = identified()
    entry = expected_entry(data_root, item)
    result = (
        outcome(entry, 7)
        if outcome is archive.Committed
        else outcome(entry)
        if outcome is archive.Exists
        else outcome("distinct commit reason")
    )
    calls: list[tuple[object, ...]] = []

    def commit(*args: object) -> Any:
        calls.append(args)
        return result

    monkeypatch.setattr(archive, "commit_original", commit)
    before = tree_snapshot(tmp_path)
    actual = intake.archive_identified(data_root, path, item, None)
    wanted = (
        intake.Archived(entry)
        if outcome is archive.Committed
        else intake.AlreadyArchived(entry)
        if outcome is archive.Exists
        else expected("distinct commit reason")
    )
    assert actual == wanted
    assert calls == [(data_root, ORIGINAL_FORMAT, path, item.sha256)]
    assert tree_snapshot(tmp_path) == before


def test_extract_arguments(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = candidate(tmp_path)
    item = identified(EXTRACT_FORMAT)
    entry = expected_entry(data_root, item)
    calls: list[tuple[object, ...]] = []

    def commit(*args: object) -> archive.Committed:
        calls.append(args)
        return archive.Committed(entry, 3)

    monkeypatch.setattr(archive, "commit_extract", commit)

    def progress(read: int, total: int) -> None:
        pass

    assert intake.archive_identified(
        data_root, path, item, progress
    ) == intake.Archived(entry)
    assert calls == [
        (data_root, EXTRACT_FORMAT, path, item.sha256, item.size, progress)
    ]


@pytest.mark.parametrize(
    "form,content,reason",
    [
        (
            ORIGINAL_FORMAT,
            b'{"test_original":true,"day":"invalid","value":53}',
            "invalid synthetic record",
        ),
        (
            EXTRACT_FORMAT,
            build_extract("2024-07-08", corrupt_body=True),
            "invalid synthetic extract body",
        ),
    ],
    ids=["original", "extract"],
)
def test_invalid(
    data_root: Path, tmp_path: Path, form: FormatSpec, content: bytes, reason: str
) -> None:
    path = candidate(tmp_path, content)
    item = identified(form, content)
    assert intake.archive_identified(data_root, path, item, None) == intake.Failed(
        reason
    )
    assert [file for file in data_root.rglob("*") if file.is_file()] == []
    assert path.read_bytes() == content


@pytest.mark.parametrize(
    "form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda form: form.id
)
def test_changed(data_root: Path, tmp_path: Path, form: FormatSpec) -> None:
    path = candidate(tmp_path)
    item = identified(form)
    path.write_bytes(b"changed unreadable bytes")
    assert intake.archive_identified(
        data_root, path, item, None
    ) == intake.IntakeDeferred("candidate changed during the run")
    assert [file for file in data_root.rglob("*") if file.is_file()] == []


@pytest.mark.parametrize(
    "occupied", ["leaf-directory", "leaf-symlink", "root-symlink", "format-symlink"]
)
def test_occupied(data_root: Path, tmp_path: Path, occupied: str) -> None:
    path = candidate(tmp_path)
    item = identified()
    entry = expected_entry(data_root, item)
    outside = tmp_path / "outside"
    outside.mkdir()
    if occupied == "root-symlink":
        (data_root / "wellness-archive").symlink_to(outside, target_is_directory=True)
        (outside / item.format.id).mkdir()
        (outside / item.format.id / entry.path.name).write_bytes(b"outside sentinel")
    elif occupied == "format-symlink":
        entry.path.parent.parent.mkdir()
        entry.path.parent.symlink_to(outside, target_is_directory=True)
        (outside / entry.path.name).write_bytes(b"outside sentinel")
    else:
        entry.path.parent.mkdir(parents=True)
        if occupied == "leaf-directory":
            entry.path.mkdir()
            (entry.path / "sentinel").write_bytes(b"directory sentinel")
        else:
            target = outside / "target"
            target.write_bytes(b"symlink sentinel")
            entry.path.symlink_to(target)
    before = tree_snapshot(tmp_path)
    links_before = {
        str(file): (file.readlink(), file.lstat().st_mtime_ns)
        for file in tmp_path.rglob("*")
        if file.is_symlink()
    }
    result = intake.archive_identified(data_root, path, item, None)
    reason = (
        "archive directory is a symlink"
        if occupied.endswith("symlink") and occupied != "leaf-symlink"
        else "occupied path is not a regular archive entry"
    )
    assert result == intake.IntakeDeferred(reason)
    assert tree_snapshot(tmp_path) == before
    assert {
        str(file): (file.readlink(), file.lstat().st_mtime_ns)
        for file in tmp_path.rglob("*")
        if file.is_symlink()
    } == links_before
