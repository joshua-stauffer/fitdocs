"""Synthetic data roots and candidate read instrumentation."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from fitdocs.wellness.probe import CHUNK_BYTES, HEAD_BYTES

_END_RECORD_SIZE = 22
_END_RECORD_SIGNATURE = b"PK\x05\x06"
_END_RECORD_FORMAT = "<4s4H2LH"


def make_data_root(parent: Path, name: str = "data") -> Path:
    root = parent / name
    root.mkdir()
    return root


@dataclass(frozen=True)
class ReadRecord:
    path: Path
    opening: int
    file_size: int
    start: int
    requested: int
    returned: int
    central_offset: int | None = None
    central_size: int | None = None


def check_bounded_reads(reads: list[ReadRecord]) -> None:
    end_seen: set[int] = set()
    central_seen: set[int] = set()
    for read in reads:
        if 0 <= read.requested <= CHUNK_BYTES:
            continue
        if (
            read.requested < 0
            and read.start >= read.file_size - (1 << 16) - _END_RECORD_SIZE
            and read.opening not in end_seen
            and read.returned <= (1 << 16) + _END_RECORD_SIZE
        ):
            end_seen.add(read.opening)
        elif (
            read.requested == read.central_size
            and read.start == read.central_offset
            and read.opening not in central_seen
        ):
            central_seen.add(read.opening)
        else:
            raise AssertionError(f"unbounded candidate read: {read}")


class CountingFile:
    def __init__(self, stream: BinaryIO, owner: CountingOpener, opening: int) -> None:
        self.stream = stream
        self.owner = owner
        self.opening = opening

    def read(self, size: int = -1) -> bytes:
        start = self.stream.tell()
        if self.owner.fail_past_head and (
            start >= HEAD_BYTES or size < 0 or start + size > HEAD_BYTES
        ):
            raise OSError("candidate unavailable past head")
        result = self.stream.read(size)
        self.owner.reads.append(
            ReadRecord(
                self.owner.path,
                self.opening,
                self.owner.size,
                start,
                size,
                len(result),
                self.owner.central_offset,
                self.owner.central_size,
            )
        )
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)

    def __enter__(self) -> CountingFile:
        return self

    def __exit__(self, *args: object) -> None:
        self.stream.close()


class CountingOpener:
    def __init__(self, path: Path, *, fail_past_head: bool = False) -> None:
        self.path = path
        self.size = path.stat().st_size
        self.fail_past_head = fail_past_head
        self.reads: list[ReadRecord] = []
        self.opens = 0
        self.central_offset: int | None = None
        self.central_size: int | None = None
        with path.open("rb") as stream:
            stream.seek(max(0, self.size - (1 << 16) - _END_RECORD_SIZE))
            tail = stream.read((1 << 16) + _END_RECORD_SIZE)
        end = tail.rfind(_END_RECORD_SIGNATURE)
        if end >= 0 and len(tail) - end >= _END_RECORD_SIZE:
            fields = struct.unpack(_END_RECORD_FORMAT, tail[end : end + 22])
            self.central_size, self.central_offset = fields[5:7]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = Path.open

        def open_path(path: Path, *args: Any, **kwargs: Any) -> Any:
            stream = original(path, *args, **kwargs)
            if path != self.path:
                return stream
            self.opens += 1
            return CountingFile(stream, self, self.opens)

        monkeypatch.setattr(Path, "open", open_path)

    def check(self) -> None:
        check_bounded_reads(self.reads)


# Task 1.3 registry fixtures; the read instrumentation above remains unchanged.
import json  # noqa: E402
from collections.abc import Iterator, Sequence  # noqa: E402
from datetime import date  # noqa: E402

from fitdocs.wellness import registry  # noqa: E402
from fitdocs.wellness.model import DaySnapshot, Metric  # noqa: E402
from fitdocs.wellness.probe import CandidateProbe  # noqa: E402
from fitdocs.wellness.spec import (  # noqa: E402
    ArchiveForm,
    ExtractContext,
    FormatSpec,
    SourceKind,
    SourceSpec,
    Supersession,
    WellnessFormatError,
)


def _snapshot(record: object, metric: Metric, ordinal: int = 0) -> DaySnapshot:
    if not isinstance(record, dict):
        raise WellnessFormatError("invalid synthetic record")
    try:
        return DaySnapshot(
            date.fromisoformat(record["day"]),
            frozenset({metric}),
            {metric: float(record["value"])},
            {},
            None,
            ordinal,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise WellnessFormatError("invalid synthetic record") from error


def _original_recognize(probe: CandidateProbe) -> bool:
    value = probe.json()
    return isinstance(value, dict) and value.get("test_original") is True


def _original_parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
    try:
        record = json.load(stream)
    except (ValueError, UnicodeError) as error:
        raise WellnessFormatError("invalid synthetic original") from error
    yield _snapshot(record, Metric.RESTING_HR_BPM)


def _extract_header(stream: BinaryIO) -> dict[str, Any]:
    try:
        header = json.loads(stream.readline())
        if (
            not isinstance(header, dict)
            or header.get("test_extract") is not True
            or not isinstance(header.get("order"), str)
        ):
            raise ValueError("invalid header")
    except (ValueError, UnicodeError) as error:
        raise WellnessFormatError("invalid synthetic extract header") from error
    return header


def _extract_recognize(probe: CandidateProbe) -> bool:
    try:
        header = json.loads(probe.head.split(b"\n", 1)[0])
    except (ValueError, UnicodeError):
        return False
    return isinstance(header, dict) and header.get("test_extract") is True


def _extract_order(stream: BinaryIO) -> str:
    return str(_extract_header(stream)["order"])


def _extract_parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
    _extract_header(stream)
    for ordinal, line in enumerate(stream):
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError) as error:
            raise WellnessFormatError("invalid synthetic extract body") from error
        yield _snapshot(record, Metric.WEIGHT_KG, ordinal)


def _extract_copy(path: Path, output: BinaryIO, context: ExtractContext) -> None:
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            output.write(chunk)
            read += len(chunk)
            if context.progress is not None:
                context.progress(read, context.size)


ORIGINAL_SOURCE = SourceSpec("test-original", "Synthetic original", SourceKind.DEVICE)
EXTRACT_SOURCE = SourceSpec("test-extract", "Synthetic extract", SourceKind.HUB)
ORIGINAL_FORMAT = FormatSpec(
    "test-original",
    "Synthetic original",
    ORIGINAL_SOURCE,
    frozenset({".json"}),
    ArchiveForm.ORIGINAL,
    ".json",
    1,
    frozenset({Metric.RESTING_HR_BPM}),
    _original_recognize,
    _original_parse,
)
EXTRACT_FORMAT = FormatSpec(
    "test-extract",
    "Synthetic extract",
    EXTRACT_SOURCE,
    frozenset({".test-extract"}),
    ArchiveForm.EXTRACT,
    ".jsonl",
    1,
    frozenset({Metric.WEIGHT_KG}),
    _extract_recognize,
    _extract_parse,
    Supersession.LATEST_ENTRY,
    _extract_copy,
    _extract_order,
)


def build_extract(order: str, *, corrupt_body: bool = False) -> bytes:
    header = json.dumps({"test_extract": True, "order": order}).encode() + b"\n"
    body = b"broken body\n" if corrupt_body else b'{"day":"2024-02-03","value":73.25}\n'
    return header + body


def use_formats(
    monkeypatch: pytest.MonkeyPatch,
    formats: Sequence[FormatSpec],
    sources: Sequence[SourceSpec],
) -> None:
    monkeypatch.setattr(registry, "FORMATS", tuple(formats))
    monkeypatch.setattr(registry, "SOURCES", tuple(sources))


def tree_snapshot(path: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(file.relative_to(path)): (file.read_bytes(), file.stat().st_mtime_ns)
        for file in path.rglob("*")
        if file.is_file()
    }


def assert_untouched(
    before: dict[str, tuple[bytes, int]], after: dict[str, tuple[bytes, int]]
) -> None:
    assert before == after
