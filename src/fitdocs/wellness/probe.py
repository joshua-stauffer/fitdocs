"""Bounded recognition inputs and streamed content hashing."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, cast

HEAD_BYTES = 65_536
JSON_PROBE_LIMIT = 64 * 1024 * 1024
CHUNK_BYTES = 1_048_576


class _ZipReader:
    """Translate zipfile's unsized tail reads into bounded sized requests."""

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        self.read_error: OSError | None = None

    def read(self, size: int = -1) -> bytes:
        try:
            if size < 0:
                position = self.stream.tell()
                self.stream.seek(0, os.SEEK_END)
                end = self.stream.tell()
                self.stream.seek(position)
                size = end - position
                if size > 65558:
                    raise ValueError("zipfile unsized read outside bounded end window")
            return self.stream.read(size)
        except OSError as error:
            self.read_error = error
            raise

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self.stream.seek(offset, whence)

    def tell(self) -> int:
        return self.stream.tell()


@dataclass
class CandidateProbe:
    path: Path
    name: str
    suffix: str
    size: int
    head: bytes
    _json_loaded: bool = field(default=False, init=False, repr=False)
    _json_value: object | None = field(default=None, init=False, repr=False)

    @classmethod
    def open(cls, path: Path) -> CandidateProbe:
        size = path.stat().st_size
        with path.open("rb") as stream:
            head = stream.read(HEAD_BYTES)
        return cls(path, path.name, path.suffix.lower(), size, head)

    def json(self) -> object | None:
        if self._json_loaded:
            return self._json_value
        if self.size > JSON_PROBE_LIMIT:
            self._json_loaded = True
            return None
        content = bytearray()
        with self.path.open("rb") as stream:
            while len(content) <= JSON_PROBE_LIMIT:
                chunk = stream.read(
                    min(CHUNK_BYTES, JSON_PROBE_LIMIT + 1 - len(content))
                )
                if not chunk:
                    break
                content.extend(chunk)
        if len(content) <= JSON_PROBE_LIMIT:
            try:
                self._json_value = json.loads(content)
            except (ValueError, UnicodeError):
                self._json_value = None
        self._json_loaded = True
        return self._json_value

    def zip_members(self) -> tuple[str, ...] | None:
        with self.path.open("rb") as stream:
            reader = _ZipReader(stream)
            try:
                with zipfile.ZipFile(cast(BinaryIO, reader)) as archive:
                    return tuple(archive.namelist())
            except zipfile.BadZipFile:
                if reader.read_error is not None:
                    raise reader.read_error from None
                return None


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
