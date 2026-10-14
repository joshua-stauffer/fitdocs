"""Streaming corrections for Apple Health export defects."""

from __future__ import annotations

import re
from typing import BinaryIO, Final

from fitdocs.wellness.formats.apple.records import Corrections
from fitdocs.wellness.spec import WellnessFormatError

CONTROL_BYTES: Final[bytes] = bytes((*range(9), 11, 12, *range(14, 32)))
PROLOG_LIMIT: Final[int] = 1_048_576
MAX_TAG_BYTES: Final[int] = 65_536
CHUNK_BYTES: Final[int] = 1_048_576

_ROOT = re.compile(rb"<HealthData(?=[\t\n\r />])")
_STATISTICS = b"<WorkoutStatistics"
_ATTRIBUTE = re.compile(
    rb"[\t\n\r ]+([^\s=/<>]+)[\t\n\r ]*=[\t\n\r ]*(?:\"[^\"]*\"|'[^']*')"
)


def _line_breaks(data: bytes) -> bytes:
    return bytes(byte for byte in data if byte in (10, 13))


class DefectFilter:
    """Repair bounded portions of an upstream binary stream on each read."""

    def __init__(self, upstream: BinaryIO, *, chunk_bytes: int = CHUNK_BYTES) -> None:
        if chunk_bytes <= 0:
            raise ValueError("chunk_bytes must be positive")
        self._upstream = upstream
        self._chunk_bytes = min(chunk_bytes, CHUNK_BYTES)
        self._prolog = True
        self._prolog_read = 0
        self._pending = b""
        self._eof = False
        self._doctype_removed = 0
        self._controls_removed = 0
        self._duplicates_removed = 0

    @property
    def corrections(self) -> Corrections:
        return Corrections(
            self._doctype_removed, self._controls_removed, self._duplicates_removed
        )

    def read(self, size: int = -1) -> bytes:
        while not self._eof:
            request = self._chunk_bytes
            if self._prolog:
                request = min(request, PROLOG_LIMIT - self._prolog_read)
                if request <= 0:
                    self._missing_root()
            raw = self._upstream.read(request)
            self._eof = not raw
            if self._prolog:
                self._prolog_read += len(raw)
            cleaned = raw.translate(None, CONTROL_BYTES)
            self._controls_removed += len(raw) - len(cleaned)
            self._pending += cleaned
            if self._prolog:
                root = _ROOT.search(self._pending)
                if root is None:
                    if self._eof or self._prolog_read >= PROLOG_LIMIT:
                        self._missing_root()
                    continue
                doctype = self._pending.find(b"<!DOCTYPE", 0, root.start())
                if doctype >= 0:
                    self._pending = (
                        self._pending[:doctype]
                        + _line_breaks(self._pending[doctype : root.start()])
                        + self._pending[root.start() :]
                    )
                    self._doctype_removed = 1
                self._prolog = False
            output = self._filter_tags()
            if output:
                return output
        return b""

    def _missing_root(self) -> None:
        limit = "1 MiB" if PROLOG_LIMIT == 1_048_576 else f"{PROLOG_LIMIT} bytes"
        raise WellnessFormatError(
            f"not an Apple Health export: no HealthData element in its first {limit}"
        )

    def _filter_tags(self) -> bytes:
        data = self._pending
        output: list[bytes] = []
        cursor = 0
        while cursor < len(data):
            start = data.find(_STATISTICS, cursor)
            if start < 0:
                carry = 0
                if not self._eof:
                    for length in range(
                        1, min(len(_STATISTICS), len(data) - cursor) + 1
                    ):
                        if data.endswith(_STATISTICS[:length]):
                            carry = length
                end = len(data) - carry
                output.append(data[cursor:end])
                self._pending = data[end:]
                return b"".join(output)
            name_end = start + len(_STATISTICS)
            if name_end == len(data) and not self._eof:
                output.append(data[cursor:start])
                self._pending = data[start:]
                return b"".join(output)
            if name_end < len(data) and data[name_end] not in b"\t\n\r />":
                output.append(data[cursor:name_end])
                cursor = name_end
                continue
            quote = 0
            end = name_end
            while end < len(data):
                byte = data[end]
                if quote:
                    if byte == quote:
                        quote = 0
                elif byte in (34, 39):
                    quote = byte
                elif byte == 62:
                    break
                end += 1
            complete = end < len(data)
            tag_end = end + 1 if complete else len(data)
            if tag_end - start > MAX_TAG_BYTES:
                raise WellnessFormatError(
                    f"WorkoutStatistics tag exceeds {MAX_TAG_BYTES} bytes"
                )
            output.append(data[cursor:start])
            if not complete:
                self._pending = data[start:]
                if self._eof:
                    output.append(self._pending)
                    self._pending = b""
                return b"".join(output)
            output.append(self._deduplicate(data[start:tag_end]))
            cursor = tag_end
        self._pending = b""
        return b"".join(output)

    def _deduplicate(self, tag: bytes) -> bytes:
        seen: set[bytes] = set()

        def attribute(match: re.Match[bytes]) -> bytes:
            name = match.group(1)
            if name in seen:
                self._duplicates_removed += 1
                return _line_breaks(match.group())
            seen.add(name)
            return match.group()

        return _ATTRIBUTE.sub(attribute, tag)
