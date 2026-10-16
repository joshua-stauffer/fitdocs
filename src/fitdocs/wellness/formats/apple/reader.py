"""Streaming recognition and reading of Apple Health exports."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final, cast
from xml.etree.ElementTree import ParseError, iterparse

from fitdocs.wellness.formats.apple.defects import CHUNK_BYTES, DefectFilter
from fitdocs.wellness.formats.apple.records import (
    RECORD_ATTRIBUTES,
    AppleType,
    ExportDate,
    ExportItem,
    RawRecord,
    normalize_device,
)
from fitdocs.wellness.spec import WellnessFormatError

MAIN_DOCUMENT: Final[str] = "apple_health_export/export.xml"
CDA_SUFFIX: Final[str] = "_cda.xml"

_HEALTH_DATA = re.compile(rb"<HealthData(?=[\t\n\r />])")
_DOCTYPE = re.compile(rb"<!DOCTYPE[\t\n\r ]+HealthData(?=[\t\n\r >\[])")
_READ_TYPES = frozenset(AppleType)


def main_member(names: Iterable[str]) -> str | None:
    members = set(names)
    candidates = {
        name
        for name in members
        if name == MAIN_DOCUMENT
        or (
            name.count("/") <= 1
            and name.endswith(".xml")
            and name[:-4] + CDA_SUFFIX in members
        )
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def looks_like_export_document(head: bytes) -> bool:
    return _DOCTYPE.search(head) is not None or _HEALTH_DATA.search(head) is not None


@dataclass(frozen=True)
class MainDocument:
    stream: BinaryIO
    size: int


class _SizedReads:
    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(CHUNK_BYTES if size < 0 else size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()

    def seekable(self) -> bool:
        return self._stream.seekable()


@contextmanager
def open_main_document(candidate: Path) -> Iterator[MainDocument]:
    try:
        with candidate.open("rb") as source:
            bounded = cast(BinaryIO, _SizedReads(cast(BinaryIO, source)))
            if zipfile.is_zipfile(bounded):
                with zipfile.ZipFile(bounded) as archive:
                    name = main_member(archive.namelist())
                    if name is None:
                        raise WellnessFormatError(
                            "no unique Apple Health main document"
                        )
                    info = archive.getinfo(name)
                    with archive.open(info) as member:
                        yield MainDocument(cast(BinaryIO, member), info.file_size)
            else:
                source.seek(0, 2)
                size = source.tell()
                source.seek(0)
                yield MainDocument(cast(BinaryIO, source), size)
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as error:
        raise WellnessFormatError(f"the export could not be read: {error}") from error


class _CountingReader:
    def __init__(
        self, document: MainDocument, progress: Callable[[int, int], None] | None
    ) -> None:
        self._document = document
        self._progress = progress
        self._read = 0
        self._percent = -1

    def read(self, size: int = -1) -> bytes:
        data = self._document.stream.read(
            min(size, CHUNK_BYTES) if size >= 0 else CHUNK_BYTES
        )
        self._read += len(data)
        if self._progress is not None and self._document.size > 0:
            percent = self._read * 100 // self._document.size
            if percent > self._percent:
                self._percent = percent
                self._progress(self._read, self._document.size)
        return data


def iter_items(
    document: MainDocument, *, progress: Callable[[int, int], None] | None
) -> Iterator[ExportItem]:
    filtered = DefectFilter(_CountingReader(document, progress))  # type: ignore[arg-type]
    root = None
    depth = -1
    dated = False
    try:
        for event, element in iterparse(filtered, events=("start", "end")):
            if event == "start":
                depth += 1
                if root is None:
                    root = element
                    if root.tag != "HealthData":
                        raise WellnessFormatError(
                            "not an Apple Health export: root must be HealthData"
                        )
                continue
            if depth == 1:
                if element.tag == "ExportDate":
                    if dated:
                        raise WellnessFormatError("the export has a second ExportDate")
                    dated = True
                    yield ExportDate(element.get("value", ""))
                elif element.tag == "Record" and element.get("type") in _READ_TYPES:
                    if not dated:
                        raise WellnessFormatError(
                            "the export has a wanted Record before ExportDate"
                        )
                    attributes = [element.get(name) for name in RECORD_ATTRIBUTES]
                    device = attributes[3]
                    attributes[3] = (
                        normalize_device(device) if device is not None else None
                    )
                    yield RawRecord(
                        type=attributes[0] or "",
                        source_name=attributes[1],
                        source_version=attributes[2],
                        device=attributes[3],
                        unit=attributes[4],
                        creation_date=attributes[5],
                        start_date=attributes[6],
                        end_date=attributes[7],
                        value=attributes[8],
                        metadata=tuple(
                            (child.get("key", ""), child.get("value", ""))
                            for child in element
                            if child.tag == "MetadataEntry"
                        ),
                    )
                assert root is not None
                root.clear()
            depth -= 1
    except ParseError as error:
        line, column = error.position
        raise WellnessFormatError(
            f"the export could not be read at line {line}, column {column}: {error}"
        ) from error
    yield filtered.corrections
