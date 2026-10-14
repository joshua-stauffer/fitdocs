"""Synthetic original and extract archive protocols."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO, cast

import pytest

from fitdocs.wellness import archive
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CHUNK_BYTES, hash_file
from fitdocs.wellness.spec import (
    ExtractContext,
    FormatSpec,
    ParsedEntry,
    Supersession,
    WellnessFormatError,
)
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    EXTRACT_SOURCE,
    ORIGINAL_FORMAT,
    ORIGINAL_SOURCE,
    CountingOpener,
    build_extract,
    use_formats,
)

ORIGINAL = b'{"test_original":true,"day":"2024-03-02","value":51}\n'


def candidate(tmp_path: Path, content: bytes = ORIGINAL) -> Path:
    path = tmp_path / "candidate.json"
    path.write_bytes(content)
    return path


def entry_path(root: Path, form: FormatSpec, digest: str) -> Path:
    return root / "wellness-archive" / form.id / f"{digest}{form.archived_suffix}"


def no_archive_files(root: Path) -> None:
    assert list(root.rglob(".incoming-*")) == []
    assert [path for path in root.rglob("*") if path.is_file()] == []


def commit(root: Path, form: FormatSpec, path: Path, digest: str | None = None) -> Any:
    expected, size = hash_file(path)
    if form is ORIGINAL_FORMAT:
        return archive.commit_original(root, form, path, digest or expected)
    return archive.commit_extract(root, form, path, digest or expected, size, None)


def test_original_commit(data_root: Path, tmp_path: Path) -> None:
    path = candidate(tmp_path)
    digest = hashlib.sha256(ORIGINAL).hexdigest()
    expected = entry_path(data_root, ORIGINAL_FORMAT, digest)
    result = commit(data_root, ORIGINAL_FORMAT, path)
    entry = archive.ArchiveEntry(
        ORIGINAL_FORMAT,
        digest,
        expected,
        f"wellness-archive/test-original/{digest}.json",
    )
    assert result == archive.Committed(entry, 1)
    assert expected.read_bytes() == ORIGINAL
    assert list(data_root.rglob(".incoming-*")) == []
    assert archive.entry_ref(ORIGINAL_FORMAT, digest) == entry.ref
    assert archive.parse_entry(entry) == ParsedEntry(
        entry.ref,
        "test-original",
        "test-original",
        Supersession.NONE,
        (
            DaySnapshot(
                date(2024, 3, 2),
                frozenset({Metric.RESTING_HR_BPM}),
                {Metric.RESTING_HR_BPM: 51.0},
                {},
                None,
                0,
            ),
        ),
    )


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_invalid_content(data_root: Path, tmp_path: Path, form: FormatSpec) -> None:
    path = candidate(tmp_path, b"invalid content")
    result = commit(data_root, form, path)
    assert isinstance(result, archive.Invalid)
    assert "invalid synthetic" in result.reason
    no_archive_files(data_root)


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_existing_entry(data_root: Path, tmp_path: Path, form: FormatSpec) -> None:
    content = ORIGINAL if form is ORIGINAL_FORMAT else build_extract("2024-09-01")
    path = candidate(tmp_path, content)
    digest, _ = hash_file(path)
    target = entry_path(data_root, form, digest)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing entry")
    os.utime(target, ns=(123456789, 123456789))
    before = (target.read_bytes(), target.stat().st_mtime_ns)
    result = commit(data_root, form, path)
    assert result == archive.Exists(
        archive.ArchiveEntry(
            form, digest, target, target.relative_to(data_root).as_posix()
        )
    )
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert list(data_root.rglob(".incoming-*")) == []


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_entry_appears_during_parse(
    data_root: Path, tmp_path: Path, form: FormatSpec
) -> None:
    content = ORIGINAL if form is ORIGINAL_FORMAT else build_extract("2024-09-01")
    path = candidate(tmp_path, content)
    digest, size = hash_file(path)
    target = entry_path(data_root, form, digest)

    def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
        yield from form.parse(stream)
        target.write_bytes(b"concurrent entry")
        os.utime(target, ns=(234567891, 234567891))

    updated = replace(form, parse=parse)
    result = (
        archive.commit_original(data_root, updated, path, digest)
        if form is ORIGINAL_FORMAT
        else archive.commit_extract(data_root, updated, path, digest, size, None)
    )
    assert isinstance(result, archive.Exists)
    assert (target.read_bytes(), target.stat().st_mtime_ns) == (
        b"concurrent entry",
        234567891,
    )
    assert list(data_root.rglob(".incoming-*")) == []


def test_original_changed_mid_copy(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = candidate(tmp_path)
    digest, _ = hash_file(path)
    original_open = Path.open

    class ChangingReader:
        def __init__(self, stream: BinaryIO) -> None:
            self.stream = stream
            self.changed = False

        def read(self, size: int) -> bytes:
            result = self.stream.read(size)
            if result and not self.changed:
                with original_open(path, "ab") as output:
                    output.write(b" changed")
                self.changed = True
            return result

        def __enter__(self) -> ChangingReader:
            return self

        def __exit__(self, *args: object) -> None:
            self.stream.close()

    def open_path(subject: Path, *args: Any, **kwargs: Any) -> Any:
        stream = original_open(subject, *args, **kwargs)
        return ChangingReader(stream) if subject == path else stream

    monkeypatch.setattr(Path, "open", open_path)
    result = archive.commit_original(data_root, ORIGINAL_FORMAT, path, digest)
    assert isinstance(result, archive.Changed)
    assert "changed during the run" in result.reason
    no_archive_files(data_root)


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_streaming(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: FormatSpec
) -> None:
    content = (
        ORIGINAL + b" " * (3 * CHUNK_BYTES)
        if form is ORIGINAL_FORMAT
        else build_extract("2024-08-01").rstrip(b"\n")
        + b" " * (3 * CHUNK_BYTES)
        + b"\n"
    )
    path = candidate(tmp_path, content)
    digest, size = hash_file(path)
    counter = CountingOpener(path)
    counter.install(monkeypatch)
    result = (
        archive.commit_original(data_root, form, path, digest)
        if form is ORIGINAL_FORMAT
        else archive.commit_extract(data_root, form, path, digest, size, None)
    )
    assert isinstance(result, archive.Committed)
    assert sum(read.returned for read in counter.reads) == size * (
        1 if form is ORIGINAL_FORMAT else 2
    )
    assert len([read for read in counter.reads if read.returned]) >= 4
    counter.check()


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_unreadable_candidate(
    data_root: Path, tmp_path: Path, form: FormatSpec
) -> None:
    path = candidate(tmp_path)
    digest, size = hash_file(path)
    path.chmod(0)
    try:
        result = (
            archive.commit_original(data_root, form, path, digest)
            if form is ORIGINAL_FORMAT
            else archive.commit_extract(data_root, form, path, digest, size, None)
        )
        assert isinstance(result, archive.Unreadable)
        assert result.reason
        no_archive_files(data_root)
    finally:
        path.chmod(0o600)


def test_extract_context_and_transformation(data_root: Path, tmp_path: Path) -> None:
    path = candidate(tmp_path, b"synthetic raw export")
    digest, size = hash_file(path)
    calls: list[object] = []

    def progress(done: int, total: int) -> None:
        calls.append((done, total))

    extract = build_extract("2025-03-04")

    def transform(subject: Path, output: BinaryIO, context: ExtractContext) -> None:
        calls.append((subject, context))
        output.write(extract)
        if context.progress:
            context.progress(7, context.size)

    form = replace(EXTRACT_FORMAT, extract=transform)
    result = archive.commit_extract(data_root, form, path, digest, size, progress)
    assert isinstance(result, archive.Committed)
    assert result.snapshots == 1
    assert calls == [(path, ExtractContext(digest, size, progress)), (7, size)]
    assert result.entry.path == entry_path(data_root, form, digest)
    assert result.entry.path.read_bytes() == extract
    assert path.read_bytes() == b"synthetic raw export"
    assert list(data_root.rglob(".incoming-*")) == []


@pytest.mark.parametrize(
    "error",
    [
        WellnessFormatError("bad extract"),
        OSError("extract read failed"),
        ValueError("unexpected extractor"),
    ],
    ids=["format", "os", "other"],
)
@pytest.mark.parametrize("changed", [False, True], ids=["unchanged", "changed"])
def test_extract_error_order(
    data_root: Path, tmp_path: Path, error: Exception, changed: bool
) -> None:
    path = candidate(tmp_path, build_extract("2024-08-01"))
    digest, size = hash_file(path)

    def extract(subject: Path, output: BinaryIO, context: ExtractContext) -> None:
        output.write(b"partial extract")
        if changed:
            subject.write_bytes(b"truncated")
        raise error

    form = replace(EXTRACT_FORMAT, extract=extract)
    if isinstance(error, ValueError) and not changed:
        with pytest.raises(ValueError) as raised:
            archive.commit_extract(data_root, form, path, digest, size, None)
        assert raised.value is error
    else:
        result = archive.commit_extract(data_root, form, path, digest, size, None)
        expected = (
            archive.Changed
            if changed
            else (
                archive.Invalid
                if isinstance(error, WellnessFormatError)
                else archive.Unreadable
            )
        )
        assert isinstance(result, expected)
        assert result.reason == (
            "candidate changed during the run" if changed else str(error)
        )
    no_archive_files(data_root)


@pytest.mark.parametrize(
    "extract_error",
    [None, WellnessFormatError("bad"), OSError("bad read")],
    ids=["returned", "format", "os"],
)
def test_extract_rehash_unreadable(
    data_root: Path, tmp_path: Path, extract_error: Exception | None
) -> None:
    path = candidate(tmp_path, build_extract("2024-08-01"))
    digest, size = hash_file(path)

    def extract(subject: Path, output: BinaryIO, context: ExtractContext) -> None:
        output.write(build_extract("2024-08-01"))
        subject.chmod(0)
        if extract_error:
            raise extract_error

    try:
        result = archive.commit_extract(
            data_root,
            replace(EXTRACT_FORMAT, extract=extract),
            path,
            digest,
            size,
            None,
        )
        assert isinstance(result, archive.Unreadable)
        assert "Permission denied" in result.reason
        no_archive_files(data_root)
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize(
    "error",
    [KeyboardInterrupt("interrupted"), SystemExit(17)],
    ids=["keyboard", "exit"],
)
def test_extract_interrupted(
    data_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    path = candidate(tmp_path, build_extract("2024-08-01"))
    digest, size = hash_file(path)

    def extract(subject: Path, output: BinaryIO, context: ExtractContext) -> None:
        output.write(b"partial")
        raise error

    def rehash(subject: Path) -> tuple[str, int]:
        pytest.fail("rehash after BaseException")

    monkeypatch.setattr(archive, "hash_file", rehash)
    with pytest.raises(type(error)) as raised:
        archive.commit_extract(
            data_root,
            replace(EXTRACT_FORMAT, extract=extract),
            path,
            digest,
            size,
            None,
        )
    assert raised.value is error
    no_archive_files(data_root)


def test_extract_changed_after_success(data_root: Path, tmp_path: Path) -> None:
    path = candidate(tmp_path, build_extract("2024-08-01"))
    digest, size = hash_file(path)

    def extract(subject: Path, output: BinaryIO, context: ExtractContext) -> None:
        output.write(build_extract("2024-08-01"))
        subject.write_bytes(b"changed")

    result = archive.commit_extract(
        data_root, replace(EXTRACT_FORMAT, extract=extract), path, digest, size, None
    )
    assert isinstance(result, archive.Changed)
    no_archive_files(data_root)


@pytest.mark.parametrize("bad", ["body", "header", "order"])
def test_extract_validated_before_replace(
    data_root: Path, tmp_path: Path, bad: str
) -> None:
    path = candidate(tmp_path, b"raw export")

    def extract(subject: Path, output: BinaryIO, context: ExtractContext) -> None:
        output.write(
            b"bad header\n"
            if bad == "header"
            else build_extract("2024-08-01", corrupt_body=bad == "body")
        )

    def order(stream: BinaryIO) -> str:
        raise WellnessFormatError("bad order")

    form = replace(
        EXTRACT_FORMAT,
        extract=extract,
        entry_order=order if bad == "order" else EXTRACT_FORMAT.entry_order,
    )
    result = commit(data_root, form, path)
    assert isinstance(result, archive.Invalid)
    assert result.reason == (
        "bad order" if bad == "order" else f"invalid synthetic extract {bad}"
    )
    no_archive_files(data_root)


def test_header_only_order(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = data_root / "corrupt.jsonl"
    path.write_bytes(build_extract("2024-12-09", corrupt_body=True))
    entry = archive.ArchiveEntry(EXTRACT_FORMAT, "a" * 64, path, "synthetic-ref")
    original_open = Path.open

    class HeaderReader:
        def __init__(self, stream: BinaryIO) -> None:
            self.stream = stream

        def readline(self, size: int = -1) -> bytes:
            return self.stream.readline(size)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.stream, name)

        def __iter__(self) -> Iterator[bytes]:
            pytest.fail("body read while ordering")

        def __enter__(self) -> HeaderReader:
            return self

        def __exit__(self, *args: object) -> None:
            self.stream.close()

    def open_path(subject: Path, *args: Any, **kwargs: Any) -> Any:
        return HeaderReader(original_open(subject, *args, **kwargs))

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_path)
        assert archive.read_entry_order(entry) == "2024-12-09"
    with pytest.raises(WellnessFormatError, match="body"):
        archive.parse_entry(entry)


@pytest.mark.parametrize("unreadable", [False, True], ids=["header", "unreadable"])
def test_order_errors(data_root: Path, unreadable: bool) -> None:
    path = data_root / "invalid.jsonl"
    path.write_bytes(b"broken header\n")
    entry = archive.ArchiveEntry(EXTRACT_FORMAT, "a" * 64, path, "synthetic-ref")
    if unreadable:
        path.chmod(0)
    try:
        with pytest.raises(OSError if unreadable else WellnessFormatError):
            archive.read_entry_order(entry)
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize(
    "fault",
    [
        "covers",
        "value",
        "value-null",
        "value-string",
        "origin-keys",
        "origin-token",
        "origin-null",
        "origin-bool",
    ],
)
@pytest.mark.parametrize("operation", ["parse", "commit"])
def test_snapshot_invariants(
    data_root: Path, tmp_path: Path, fault: str, operation: str
) -> None:
    metric = Metric.RESTING_HR_BPM
    snapshot = DaySnapshot(
        date(2024, 1, 2), frozenset({metric}), {metric: 49.0}, {}, None, 19
    )
    if fault == "covers":
        snapshot = replace(snapshot, covers=frozenset())
    elif fault == "value":
        snapshot = replace(snapshot, values={metric: 0.0})
    elif fault == "value-null":
        snapshot = replace(snapshot, values={metric: cast(float, None)})
    elif fault == "value-string":
        snapshot = replace(snapshot, values={metric: cast(float, "49")})
    elif fault == "origin-null":
        snapshot = replace(snapshot, origins={metric: cast(str, None)})
    elif fault == "origin-bool":
        snapshot = replace(snapshot, origins={metric: cast(str, False)})
    elif fault == "origin-keys":
        snapshot = replace(snapshot, origins={Metric.WEIGHT_KG: "valid-origin"})
    else:
        snapshot = replace(snapshot, origins={metric: "INVALID ORIGIN"})

    def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
        yield snapshot

    form = replace(ORIGINAL_FORMAT, parse=parse)
    path = candidate(tmp_path)
    if operation == "parse":
        with pytest.raises(WellnessFormatError):
            archive.parse_entry(archive.ArchiveEntry(form, "a" * 64, path, "ref"))
    else:
        result = archive.commit_original(data_root, form, path, hash_file(path)[0])
        assert isinstance(result, archive.Invalid)
        no_archive_files(data_root)


def test_parse_ordinals_and_preserved_fields(tmp_path: Path) -> None:
    snapshots = (
        DaySnapshot(
            date(2024, 7, 2),
            frozenset({Metric.WEIGHT_KG, Metric.STEPS}),
            {Metric.WEIGHT_KG: 73.0},
            {Metric.WEIGHT_KG: "device-one"},
            "2024-08-01",
            18,
        ),
        DaySnapshot(
            date(2023, 5, 4),
            frozenset({Metric.WEIGHT_KG}),
            {Metric.WEIGHT_KG: 67.0},
            {},
            None,
            6,
        ),
    )

    def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
        yield from snapshots

    form = replace(EXTRACT_FORMAT, id="test-extract-entry", parse=parse)
    result = archive.parse_entry(
        archive.ArchiveEntry(form, "b" * 64, candidate(tmp_path), "archive/ref")
    )
    assert result == ParsedEntry(
        "archive/ref",
        form.id,
        EXTRACT_SOURCE.id,
        Supersession.LATEST_ENTRY,
        tuple(replace(snapshot, ordinal=i) for i, snapshot in enumerate(snapshots)),
    )


def test_listing(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(
        monkeypatch,
        [EXTRACT_FORMAT, ORIGINAL_FORMAT],
        [EXTRACT_SOURCE, ORIGINAL_SOURCE],
    )
    top = data_root / "wellness-archive"
    original_dir = top / ORIGINAL_FORMAT.id
    original_dir.mkdir(parents=True)
    extract_dir = top / EXTRACT_FORMAT.id
    extract_dir.mkdir()
    for digest in ("f" * 64, "a" * 64):
        (original_dir / f"{digest}.json").write_bytes(b"unread")
    (extract_dir / f"{'9' * 64}.jsonl").write_bytes(b"unread")
    for directory in (top, original_dir):
        (directory / "AGENTS.md").write_text("skip")
        (directory / ".hidden").mkdir()
        (directory / ".hidden" / "unlisted").write_bytes(b"skip")
    (original_dir / "bad.json").write_bytes(b"orphan")
    (original_dir / f"{'b' * 64}.wrong").write_bytes(b"orphan")
    (original_dir / f"{'D' * 64}.json").write_bytes(b"orphan")
    (original_dir / f"{'c' * 64}.json").symlink_to(original_dir / f"{'a' * 64}.json")
    (original_dir / "nested").mkdir()
    (original_dir / f"{'e' * 64}.json").mkdir()
    unknown = top / "unknown-format"
    (unknown / "nested").mkdir(parents=True)
    (unknown / "first").write_bytes(b"unknown")
    (unknown / "nested" / "second").write_bytes(b"unknown")
    (unknown / "external-link").symlink_to(original_dir, target_is_directory=True)
    (top / "format-link").symlink_to(unknown, target_is_directory=True)
    (top / "loose").write_bytes(b"orphan")

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("listing opened a file")

    monkeypatch.setattr(Path, "open", forbidden)
    listing = archive.list_archive(data_root)
    assert listing.entries == tuple(
        archive.ArchiveEntry(
            form,
            digest,
            entry_path(data_root, form, digest),
            f"wellness-archive/{form.id}/{digest}{form.archived_suffix}",
        )
        for form, digest in [
            (EXTRACT_FORMAT, "9" * 64),
            (ORIGINAL_FORMAT, "a" * 64),
            (ORIGINAL_FORMAT, "f" * 64),
        ]
    )
    orphans = {orphan.ref: orphan.reason for orphan in listing.orphans}
    assert set(orphans) == {
        f"wellness-archive/test-original/{name}"
        for name in (
            "bad.json",
            f"{'b' * 64}.wrong",
            f"{'D' * 64}.json",
            f"{'c' * 64}.json",
            "nested",
            f"{'e' * 64}.json",
        )
    } | {
        "wellness-archive/unknown-format",
        "wellness-archive/format-link",
        "wellness-archive/loose",
    }
    assert "2 files" in orphans["wellness-archive/unknown-format"]
    assert all(orphans.values())


def test_empty_listing(data_root: Path) -> None:
    assert archive.list_archive(data_root) == archive.ArchiveListing((), ())


@pytest.mark.parametrize("location", ["archive", "format", "entry"])
@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_write_symlink_occupancy(
    data_root: Path, tmp_path: Path, location: str, form: FormatSpec
) -> None:
    content = ORIGINAL if form is ORIGINAL_FORMAT else build_extract("2024-08-01")
    path = candidate(tmp_path, content)
    digest, _ = hash_file(path)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns)
    target = entry_path(data_root, form, digest)
    link = {
        "archive": data_root / "wellness-archive",
        "format": target.parent,
        "entry": target,
    }[location]
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(
        sentinel if location == "entry" else outside,
        target_is_directory=location != "entry",
    )
    result = commit(data_root, form, path)
    assert isinstance(result, archive.Unreadable)
    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == before
    assert sorted(child.name for child in outside.iterdir()) == ["sentinel"]
    assert link.is_symlink()


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "../escape", "g" * 64])
def test_ref_rejects_invalid_sha(digest: str) -> None:
    with pytest.raises(ValueError):
        archive.entry_ref(ORIGINAL_FORMAT, digest)


def test_replace_protocol(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = candidate(tmp_path)
    digest, _ = hash_file(path)
    events: list[str] = []

    def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
        yield from ORIGINAL_FORMAT.parse(stream)
        events.append("parsed")

    form = replace(ORIGINAL_FORMAT, parse=parse)
    replace_file = os.replace

    def replace_checked(source: Path, target: Path) -> None:
        assert events == ["parsed"]
        assert source.parent == entry_path(data_root, form, digest).parent
        assert source.name.startswith(".incoming-") and source.suffix == ".tmp"
        assert source.read_bytes() == ORIGINAL
        assert target == entry_path(data_root, form, digest)
        events.append("replace")
        replace_file(source, target)

    monkeypatch.setattr(os, "replace", replace_checked)
    result = archive.commit_original(data_root, form, path, digest)
    assert isinstance(result, archive.Committed)
    assert events == ["parsed", "replace"]


@pytest.mark.parametrize("operation", ["parse", "order"])
def test_archived_entry_unreadable(tmp_path: Path, operation: str) -> None:
    path = candidate(tmp_path, build_extract("2024-08-01"))
    entry = archive.ArchiveEntry(EXTRACT_FORMAT, "a" * 64, path, "ref")
    path.chmod(0)
    try:
        with pytest.raises(OSError):
            (archive.parse_entry if operation == "parse" else archive.read_entry_order)(
                entry
            )
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize("operation", ["parse", "order"])
def test_archived_entry_symlink(tmp_path: Path, operation: str) -> None:
    real = candidate(tmp_path, build_extract("2024-08-01"))
    path = tmp_path / "symlink"
    path.symlink_to(real)
    entry = archive.ArchiveEntry(EXTRACT_FORMAT, "a" * 64, path, "ref")
    with pytest.raises(OSError, match="symlink"):
        (archive.parse_entry if operation == "parse" else archive.read_entry_order)(
            entry
        )


def test_order_requires_declaration(tmp_path: Path) -> None:
    entry = archive.ArchiveEntry(ORIGINAL_FORMAT, "a" * 64, candidate(tmp_path), "ref")
    with pytest.raises(WellnessFormatError, match="entry order"):
        archive.read_entry_order(entry)


@pytest.mark.parametrize("location", ["archive", "format"])
def test_listing_symlink_directory(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    use_formats(monkeypatch, [ORIGINAL_FORMAT], [ORIGINAL_SOURCE])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / f"{'a' * 64}.json").write_bytes(b"outside")
    top = data_root / "wellness-archive"
    link = top if location == "archive" else top / ORIGINAL_FORMAT.id
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    listing = archive.list_archive(data_root)
    assert listing == archive.ArchiveListing(
        (), (archive.Orphan(link.relative_to(data_root).as_posix(), "symlink"),)
    )


@pytest.mark.parametrize("operation", ["parse", "order"])
def test_read_preserves_entry(tmp_path: Path, operation: str) -> None:
    path = candidate(tmp_path, build_extract("2024-08-01"))
    os.utime(path, ns=(345678912, 345678912))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    entry = archive.ArchiveEntry(EXTRACT_FORMAT, "a" * 64, path, "ref")
    (archive.parse_entry if operation == "parse" else archive.read_entry_order)(entry)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
def test_candidate_symlink(
    data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: FormatSpec
) -> None:
    real = candidate(
        tmp_path, ORIGINAL if form is ORIGINAL_FORMAT else build_extract("2024-08-01")
    )
    digest, size = hash_file(real)
    path = tmp_path / "candidate-link"
    path.symlink_to(real)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("candidate symlink opened")

    monkeypatch.setattr(Path, "open", forbidden)
    result = (
        archive.commit_original(data_root, form, path, digest)
        if form is ORIGINAL_FORMAT
        else archive.commit_extract(data_root, form, path, digest, size, None)
    )
    assert isinstance(result, archive.Unreadable)
    assert "symlink" in result.reason
    no_archive_files(data_root)


def test_extract_requires_declaration(data_root: Path, tmp_path: Path) -> None:
    result = commit(
        data_root, replace(EXTRACT_FORMAT, extract=None), candidate(tmp_path)
    )
    assert isinstance(result, archive.Invalid)
    assert result.reason == "format does not declare an extractor"
    no_archive_files(data_root)


@pytest.mark.parametrize("form", [ORIGINAL_FORMAT, EXTRACT_FORMAT], ids=lambda f: f.id)
@pytest.mark.parametrize("kind", ["directory", "symlink"])
@pytest.mark.parametrize("timing", ["initial", "during-parse"])
def test_non_entry_occupancy(
    data_root: Path,
    tmp_path: Path,
    form: FormatSpec,
    kind: str,
    timing: str,
) -> None:
    path = candidate(
        tmp_path, ORIGINAL if form is ORIGINAL_FORMAT else build_extract("2024-08-01")
    )
    digest, size = hash_file(path)
    target = entry_path(data_root, form, digest)
    before: list[tuple[object, ...]] = []

    def state() -> tuple[object, ...]:
        if kind == "symlink":
            return (
                os.readlink(target),
                target.lstat().st_mtime_ns,
                (tmp_path / "missing-target").exists(),
            )
        return (
            target.stat().st_mtime_ns,
            tuple(
                (
                    child.relative_to(target).as_posix(),
                    None if child.is_dir() else child.read_bytes(),
                    child.stat().st_mtime_ns,
                )
                for child in sorted(target.rglob("*"))
            ),
        )

    def occupy() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "symlink":
            target.symlink_to(tmp_path / "missing-target")
        else:
            (target / "nested").mkdir(parents=True)
            (target / "nested" / "sentinel").write_bytes(b"existing orphan content")
            os.utime(target / "nested" / "sentinel", ns=(456789123, 456789123))
            os.utime(target / "nested", ns=(567891234, 567891234))
        os.utime(target, ns=(678912345, 678912345), follow_symlinks=False)
        before.append(state())

    def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
        yield from form.parse(stream)
        occupy()

    if timing == "initial":
        occupy()
        used = form
    else:
        used = replace(form, parse=parse)
    result = (
        archive.commit_original(data_root, used, path, digest)
        if form is ORIGINAL_FORMAT
        else archive.commit_extract(data_root, used, path, digest, size, None)
    )
    assert state() == before[0]
    assert isinstance(result, archive.Unreadable)
    assert "not a regular archive entry" in result.reason
    assert list(target.parent.glob(".incoming-*")) == []
