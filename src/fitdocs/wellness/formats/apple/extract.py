"""Canonical compressed Apple Health extract codec."""

from __future__ import annotations

import gzip
import json
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import BinaryIO, Final, cast

from fitdocs.wellness.formats.apple.records import (
    RECORD_ATTRIBUTES,
    AppleType,
    ExportDate,
    ExportItem,
    RawRecord,
)
from fitdocs.wellness.spec import WellnessFormatError

EXTRACT_FORMAT: Final[str] = "fitdocs.apple-health-extract"
EXTRACT_VERSION: Final[int] = 1
READABLE_VERSIONS: Final[frozenset[int]] = frozenset({1})
_HEADER_KEYS = frozenset(
    (
        "format",
        "version",
        "original_sha256",
        "original_size",
        "export_date",
        "export_date_utc",
        "record_types",
    )
)
_RECORD_FIELDS = (
    "type",
    "source_name",
    "source_version",
    "device",
    "unit",
    "creation_date",
    "start_date",
    "end_date",
    "value",
)
_CORRECTION_KEYS = frozenset(
    ("doctype_removed", "control_characters_removed", "duplicate_attributes_removed")
)


@dataclass(frozen=True)
class ExtractHeader:
    version: int
    original_sha256: str
    original_size: int
    export_date: str
    export_date_utc: str
    record_types: tuple[str, ...]


def export_date_utc(text: str) -> str:
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.utcoffset() is None:
            raise WellnessFormatError("export date requires a UTC offset")
        utc = parsed.astimezone(timezone.utc)  # noqa: UP017
    except (ValueError, OverflowError) as error:
        raise WellnessFormatError(f"invalid export date: {text!r}") from error
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T"
        f"{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}Z"
    )


def _write_line(stream: gzip.GzipFile, obj: object) -> None:
    stream.write(
        json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        + b"\n"
    )


def write_extract(
    sink: BinaryIO,
    items: Iterable[ExportItem],
    *,
    original_sha256: str,
    original_size: int,
) -> None:
    dated = False
    ended = False
    count = 0
    with gzip.GzipFile(
        fileobj=sink, mode="wb", compresslevel=9, mtime=0, filename=""
    ) as stream:
        for item in items:
            if ended:
                raise WellnessFormatError("item after trailer")
            if isinstance(item, ExportDate):
                if dated:
                    raise WellnessFormatError("duplicate export date")
                _write_line(
                    stream,
                    {
                        "format": EXTRACT_FORMAT,
                        **asdict(
                            ExtractHeader(
                                EXTRACT_VERSION,
                                original_sha256,
                                original_size,
                                item.text,
                                export_date_utc(item.text),
                                tuple(sorted(str(value) for value in AppleType)),
                            )
                        ),
                    },
                )
                dated = True
            else:
                if not dated:
                    raise WellnessFormatError("item before export date")
                if isinstance(item, RawRecord):
                    payload = {
                        key: value
                        for key, field in zip(
                            RECORD_ATTRIBUTES, _RECORD_FIELDS, strict=True
                        )
                        if (value := getattr(item, field)) is not None
                    }
                    if item.metadata:
                        payload["metadata"] = item.metadata
                    _write_line(stream, payload)
                    count += 1
                else:
                    _write_line(
                        stream, {"end": {"records": count, "corrections": asdict(item)}}
                    )
                    ended = True
        if not dated:
            raise WellnessFormatError("missing export date")
        if not ended:
            raise WellnessFormatError("missing trailer")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise WellnessFormatError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _line(stream: gzip.GzipFile, label: str) -> dict[str, object]:
    line = stream.readline()
    if not line:
        raise WellnessFormatError(f"missing {label}")
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WellnessFormatError(f"invalid UTF-8 in {label}") from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise WellnessFormatError(f"invalid JSON in {label}") from error
    return _object(value, label)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise WellnessFormatError(f"{label} must be a string")
    return value


def _count(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise WellnessFormatError(f"{label} must be a nonnegative integer")
    return value


def _header(obj: dict[str, object]) -> ExtractHeader:
    if obj.get("format") != EXTRACT_FORMAT:
        raise WellnessFormatError("invalid extract format")
    version = obj.get("version")
    if type(version) is not int:
        raise WellnessFormatError("invalid extract version")
    if version not in READABLE_VERSIONS:
        if version > EXTRACT_VERSION:
            raise WellnessFormatError(
                f"written by a newer fitdocs (extract version {version})"
            )
        raise WellnessFormatError(f"unsupported extract version {version}")
    if obj.keys() != _HEADER_KEYS:
        raise WellnessFormatError("invalid header keys")
    sha = _string(obj["original_sha256"], "original_sha256")
    size = _count(obj["original_size"], "original_size")
    date = _string(obj["export_date"], "export_date")
    utc = _string(obj["export_date_utc"], "export_date_utc")
    if utc != export_date_utc(date):
        raise WellnessFormatError("invalid export_date_utc")
    types = obj["record_types"]
    if (
        not isinstance(types, list)
        or any(
            not isinstance(value, str)
            or value not in {item.value for item in AppleType}
            for value in types
        )
        or len(set(types)) != len(types)
    ):
        raise WellnessFormatError("invalid record_types")
    return ExtractHeader(version, sha, size, date, utc, tuple(types))


def _record(obj: dict[str, object], header: ExtractHeader) -> RawRecord:
    if obj.keys() - {*RECORD_ATTRIBUTES, "metadata"}:
        raise WellnessFormatError("unknown record keys")
    for key in RECORD_ATTRIBUTES:
        if key in obj:
            _string(obj[key], key)
    if obj.get("type") not in header.record_types:
        raise WellnessFormatError("record type is absent from header record_types")
    metadata = obj.get("metadata", [])
    if not isinstance(metadata, list) or any(
        not isinstance(pair, list)
        or len(pair) != 2
        or any(not isinstance(value, str) for value in pair)
        for pair in metadata
    ):
        raise WellnessFormatError("metadata must be a list of string pairs")
    fields = {
        field: obj.get(key)
        for key, field in zip(RECORD_ATTRIBUTES, _RECORD_FIELDS, strict=True)
    }
    return RawRecord(
        **fields,  # type: ignore[arg-type]
        metadata=tuple((pair[0], pair[1]) for pair in metadata),
    )


def _trailer(obj: dict[str, object], count: int) -> None:
    if obj.keys() != {"end"}:
        raise WellnessFormatError("invalid trailer keys")
    end = _object(obj["end"], "trailer")
    if end.keys() != {"records", "corrections"}:
        raise WellnessFormatError("invalid trailer keys")
    records = _count(end["records"], "records")
    if records != count:
        raise WellnessFormatError("trailer record count mismatch")
    corrections = _object(end["corrections"], "corrections")
    if corrections.keys() != _CORRECTION_KEYS:
        raise WellnessFormatError("invalid corrections keys")
    for key in _CORRECTION_KEYS:
        _count(corrections[key], key)


def read_header(stream: BinaryIO) -> ExtractHeader:
    try:
        with gzip.GzipFile(fileobj=stream, mode="rb") as decoded:
            return _header(_line(decoded, "header"))
    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise WellnessFormatError(f"invalid gzip extract: {error}") from error


def read_records(stream: BinaryIO) -> Iterator[RawRecord]:
    try:
        with gzip.GzipFile(fileobj=stream, mode="rb") as decoded:
            header = _header(_line(decoded, "header"))
            count = 0
            while True:
                obj = _line(decoded, "trailer")
                if "end" in obj:
                    _trailer(obj, count)
                    if decoded.readline():
                        raise WellnessFormatError("line after trailer")
                    return
                yield _record(obj, header)
                count += 1
    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise WellnessFormatError(f"invalid gzip extract: {error}") from error
