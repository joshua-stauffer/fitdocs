"""Probe reads, lazy decoding and structural zip allowances."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from fitdocs.wellness import probe
from tests.wellness._helpers import CountingOpener, ReadRecord, check_bounded_reads


def test_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "candidate.JSON"
    content = b"abcd" * probe.HEAD_BYTES
    path.write_bytes(content)
    counter = CountingOpener(path, fail_past_head=True)
    counter.install(monkeypatch)
    candidate = probe.CandidateProbe.open(path)
    assert (candidate.path, candidate.name, candidate.suffix, candidate.size) == (
        path,
        "candidate.JSON",
        ".json",
        len(content),
    )
    assert candidate.head == content[: probe.HEAD_BYTES]
    assert [(r.start, r.requested) for r in counter.reads] == [(0, probe.HEAD_BYTES)]


def test_json_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "large.json"
    path.write_bytes(b'"' + b"x" * (2 * probe.CHUNK_BYTES) + b'"')
    monkeypatch.setattr(probe, "JSON_PROBE_LIMIT", probe.CHUNK_BYTES)
    counter = CountingOpener(path)
    counter.install(monkeypatch)
    candidate = probe.CandidateProbe.open(path)
    assert candidate.json() is None
    assert sum(r.returned for r in counter.reads) == probe.HEAD_BYTES
    counter.check()


@pytest.mark.parametrize(
    "content,expected",
    [
        (b'{"value": 37}', {"value": 37}),
        (b"broken", None),
        (b'"\xff"', None),
        (b"null", None),
    ],
)
def test_json_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes, expected: object
) -> None:
    path = tmp_path / "values.json"
    path.write_bytes(content)
    counter = CountingOpener(path)
    counter.install(monkeypatch)
    candidate = probe.CandidateProbe.open(path)
    first = candidate.json()
    assert first == expected
    opens = counter.opens
    assert opens == 2
    assert candidate.json() is first
    assert counter.opens == opens
    counter.check()


def test_json_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "values.json"
    value = "z" * (2 * probe.CHUNK_BYTES + 23)
    path.write_text('"' + value + '"')
    counter = CountingOpener(path)
    counter.install(monkeypatch)
    assert probe.CandidateProbe.open(path).json() == value
    counter.check()


@pytest.mark.parametrize("kind", ["small", "commented", "big"])
def test_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    path = tmp_path / "members.zip"
    names = tuple(
        f"member-{i:05}-" + "x" * 50 for i in range(12000 if kind == "big" else 2)
    )
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"synthetic" * (10000 if kind == "commented" else 1))
        if kind == "commented":
            archive.comment = b"c" * 40000
    counter = CountingOpener(path)
    if kind == "big":
        assert (
            counter.central_size is not None
            and counter.central_size > probe.CHUNK_BYTES
        )
    counter.install(monkeypatch)
    assert probe.CandidateProbe.open(path).zip_members() == names
    counter.check()


def test_nonzip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "plain.zip"
    path.write_bytes(b"synthetic non-zip" * 100)
    counter = CountingOpener(path)
    counter.install(monkeypatch)
    assert probe.CandidateProbe.open(path).zip_members() is None
    counter.check()


@pytest.mark.parametrize("kind", ["json", "zip"])
def test_lazy_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    path = tmp_path / f"lazy.{kind}"
    if kind == "json":
        path.write_bytes(b'"' + b"v" * (probe.HEAD_BYTES + 31) + b'"')
    else:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("member", b"a" * (probe.HEAD_BYTES + 31))
    counter = CountingOpener(path, fail_past_head=True)
    counter.install(monkeypatch)
    candidate = probe.CandidateProbe.open(path)
    assert candidate.size > probe.HEAD_BYTES
    with pytest.raises(OSError, match="unavailable past head"):
        if kind == "json":
            candidate.json()
        else:
            candidate.zip_members()


def test_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "hash.bin"
    content = b"abcdefg" * probe.CHUNK_BYTES + b"tail"
    path.write_bytes(content)
    counter = CountingOpener(path)
    counter.install(monkeypatch)
    assert probe.hash_file(path) == (hashlib.sha256(content).hexdigest(), len(content))
    assert [r.requested for r in counter.reads] == [probe.CHUNK_BYTES] * 9
    counter.check()


@pytest.mark.parametrize("kind", ["early_end", "repeated_central", "large_prefix"])
def test_checker_rejects(kind: str, tmp_path: Path) -> None:
    size = 8 * probe.CHUNK_BYTES
    central_size = 2 * probe.CHUNK_BYTES
    central = ReadRecord(
        tmp_path / "x",
        1,
        size,
        3 * probe.CHUNK_BYTES,
        central_size,
        central_size,
        3 * probe.CHUNK_BYTES,
        central_size,
    )
    reads = {
        "early_end": [ReadRecord(tmp_path / "x", 1, size, size - 65559, -1, 65558)],
        "repeated_central": [central, central],
        "large_prefix": [
            ReadRecord(
                tmp_path / "x", 1, size, 0, 2 * probe.CHUNK_BYTES, 2 * probe.CHUNK_BYTES
            )
        ],
    }[kind]
    with pytest.raises(AssertionError, match="unbounded candidate read"):
        check_bounded_reads(reads)


def test_zip_reader_tail_bound() -> None:
    import io

    stream = io.BytesIO(b"x" * 65559)
    reader = probe._ZipReader(stream)
    with pytest.raises(ValueError, match="bounded end window"):
        reader.read()
    assert stream.tell() == 0
    stream.seek(1)
    assert reader.read() == b"x" * 65558


def test_zip_reader_preserves_sized_reads() -> None:
    import io

    content = b"z" * (probe.CHUNK_BYTES + 3)
    reader = probe._ZipReader(io.BytesIO(content))
    assert reader.read(len(content)) == content


def test_data_root(data_root: Path, tmp_path: Path) -> None:
    assert data_root == tmp_path / "data"
    assert data_root.is_dir()


def test_zip_reader_records_original_error() -> None:
    import io

    error = OSError("synthetic read failure")

    class BrokenStream(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise error

    reader = probe._ZipReader(BrokenStream(b"data"))
    assert reader.read_error is None
    with pytest.raises(OSError) as caught:
        reader.read(4)
    assert caught.value is error
    assert reader.read_error is error


def test_probe_constants() -> None:
    assert (probe.HEAD_BYTES, probe.JSON_PROBE_LIMIT, probe.CHUNK_BYTES) == (
        65_536,
        67_108_864,
        1_048_576,
    )
