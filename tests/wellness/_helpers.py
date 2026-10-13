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
