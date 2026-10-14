"""Canonical Apple Health compressed extracts."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError, asdict, replace
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast

import pytest

from fitdocs.wellness.formats.apple import extract
from fitdocs.wellness.formats.apple.records import (
    AppleType,
    Corrections,
    ExportDate,
    ExportItem,
    RawRecord,
)
from fitdocs.wellness.spec import WellnessFormatError

DATE = "2024-02-06 14:30:00 -0800"
UTC = "2024-02-06T22:30:00Z"
SHA = "9abcdef012345678" * 4
SIZE = 987654321
TYPES = sorted(str(value) for value in AppleType)
FIELDS = (
    ("type", "type"),
    ("sourceName", "source_name"),
    ("sourceVersion", "source_version"),
    ("device", "device"),
    ("unit", "unit"),
    ("creationDate", "creation_date"),
    ("startDate", "start_date"),
    ("endDate", "end_date"),
    ("value", "value"),
)
RAW = RawRecord(
    type=AppleType.STEP_COUNT,
    source_name="Example Apple Watch 雪",
    source_version="0009.3",
    device="manufacturer:Apple, model:Watch, hardware:0002",
    unit="count",
    creation_date="2024-01-12 07:09:11 +0900",
    start_date="2024-01-10 23:30:12 -0800",
    end_date="2024-01-11 00:10:13 -0800",
    value="007.50",
    metadata=(("z-key", "009"), ("a-key", "é"), ("z-key", "third")),
)
CORRECTIONS = Corrections(2, 3, 5)


def header() -> dict[str, object]:
    return {
        "format": "fitdocs.apple-health-extract",
        "version": 1,
        "original_sha256": SHA,
        "original_size": SIZE,
        "export_date": DATE,
        "export_date_utc": UTC,
        "record_types": TYPES,
    }


def record() -> dict[str, object]:
    return {
        **{key: getattr(RAW, field) for key, field in FIELDS},
        "metadata": [list(pair) for pair in RAW.metadata],
    }


def trailer() -> dict[str, object]:
    return {"end": {"records": 1, "corrections": asdict(CORRECTIONS)}}


def compressed(*objects: object) -> bytes:
    return gzip.compress(
        b"".join(
            json.dumps(
                obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
            for obj in objects
        ),
        mtime=0,
    )


def write(items: list[ExportItem] | None = None) -> bytes:
    sink = BytesIO()
    extract.write_extract(
        sink,
        items if items is not None else [ExportDate(DATE), RAW, CORRECTIONS],
        original_sha256=SHA,
        original_size=SIZE,
    )
    return sink.getvalue()


def objects() -> list[object]:
    return [header(), record(), trailer()]


def test_gzip_magic() -> None:
    assert write()[:2] == b"\x1f\x8b"


def test_constants() -> None:
    assert ("fitdocs.apple-health-extract", 1, frozenset({1})) == (
        extract.EXTRACT_FORMAT,
        extract.EXTRACT_VERSION,
        extract.READABLE_VERSIONS,
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        (DATE, UTC),
        ("2024-02-06 14:30:00 +0530", "2024-02-06T09:00:00Z"),
        ("0001-01-01 01:02:03 +0000", "0001-01-01T01:02:03Z"),
    ],
    ids=["west", "east", "fixed-width"],
)
def test_export_date_utc(text: str, expected: str) -> None:
    assert extract.export_date_utc(text) == expected


@pytest.mark.parametrize("text", ["not-a-date", "2024-02-06 14:30:00"])
def test_export_date_invalid(text: str) -> None:
    with pytest.raises(WellnessFormatError, match="export date"):
        extract.export_date_utc(text)


@pytest.mark.parametrize("key", list(header()))
def test_header_fields(key: str) -> None:
    payload = json.loads(gzip.decompress(write()).splitlines()[0])
    assert payload[key] == header()[key]


def test_read_header() -> None:
    assert extract.read_header(
        BytesIO(compressed(*objects()))
    ) == extract.ExtractHeader(1, SHA, SIZE, DATE, UTC, tuple(TYPES))


@pytest.mark.parametrize("key, field", FIELDS)
def test_record_verbatim_fields(key: str, field: str) -> None:
    payload = json.loads(gzip.decompress(write()).splitlines()[1])
    assert payload[key] == getattr(RAW, field)


@pytest.mark.parametrize("key, field", FIELDS[1:])
@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
def test_optional_attribute(key: str, field: str, value: str | None) -> None:
    changed = replace(RAW, **{field: value})  # type: ignore[arg-type]
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert (key in payload, payload.get(key)) == (value is not None, value)


@pytest.mark.parametrize("key, field", FIELDS)
def test_read_record_fields(key: str, field: str) -> None:
    restored = list(extract.read_records(BytesIO(compressed(*objects()))))[0]
    assert getattr(restored, field) == record()[key]


@pytest.mark.parametrize("key, field", FIELDS[1:])
@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
def test_read_optional_attribute(key: str, field: str, value: str | None) -> None:
    payload = record()
    if value is None:
        del payload[key]
    else:
        payload[key] = value
    restored = list(
        extract.read_records(BytesIO(compressed(header(), payload, trailer())))
    )
    assert getattr(restored[0], field) == value


@pytest.mark.parametrize("metadata", [RAW.metadata, ()], ids=["ordered", "empty"])
def test_metadata_write(metadata: tuple[tuple[str, str], ...]) -> None:
    changed = replace(RAW, metadata=metadata)
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert ("metadata" in payload, payload.get("metadata")) == (
        bool(metadata),
        [list(pair) for pair in metadata] if metadata else None,
    )


@pytest.mark.parametrize("metadata", [RAW.metadata, ()], ids=["ordered", "empty"])
def test_metadata_read(metadata: tuple[tuple[str, str], ...]) -> None:
    payload = record()
    if metadata:
        payload["metadata"] = [list(pair) for pair in metadata]
    else:
        del payload["metadata"]
    restored = list(
        extract.read_records(BytesIO(compressed(header(), payload, trailer())))
    )
    assert restored[0].metadata == metadata


def test_record_order() -> None:
    later = replace(RAW, value="003.25", start_date="2024-01-14 02:01:00 +0000")
    earlier = replace(RAW, value="001.75", start_date="2024-01-08 09:05:00 +0000")
    restored = list(
        extract.read_records(
            BytesIO(write([ExportDate(DATE), later, RAW, earlier, CORRECTIONS]))
        )
    )
    assert [item.value for item in restored] == ["003.25", "007.50", "001.75"]


def test_trailer() -> None:
    payload = json.loads(gzip.decompress(write()).splitlines()[-1])
    assert payload == trailer()


def test_canonical_lines() -> None:
    assert gzip.decompress(write()) == b"".join(
        json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        + b"\n"
        for obj in objects()
    )


def test_deterministic_named_sink(tmp_path: Path) -> None:
    first = tmp_path / "synthetic-extract-sink-one.gz"
    second = tmp_path / "another-synthetic-extract-sink-two.gz"
    for path in (first, second):
        with path.open("wb") as sink:
            extract.write_extract(
                sink,
                [ExportDate(DATE), RAW, CORRECTIONS],
                original_sha256=SHA,
                original_size=SIZE,
            )
    assert first.read_bytes()[:2] == b"\x1f\x8b"
    assert first.read_bytes() == second.read_bytes()


def test_gzip_filename_flag(tmp_path: Path) -> None:
    path = tmp_path / "distinct-named-extract-sink.bin"
    with path.open("wb") as sink:
        extract.write_extract(
            sink,
            [ExportDate(DATE), RAW, CORRECTIONS],
            original_sha256=SHA,
            original_size=SIZE,
        )
    assert (path.read_bytes()[3] & 8, path.name.encode() in path.read_bytes()) == (
        0,
        False,
    )


def test_gzip_mtime() -> None:
    assert write()[4:8] == b"\x00\x00\x00\x00"


def test_gzip_level() -> None:
    assert write()[8] == 2


def test_writer_keeps_sink_open() -> None:
    sink = BytesIO()
    extract.write_extract(
        sink, [ExportDate(DATE), CORRECTIONS], original_sha256=SHA, original_size=SIZE
    )
    assert not sink.closed


@pytest.mark.parametrize(
    "reader",
    [extract.read_header, lambda stream: list(extract.read_records(stream))],
    ids=["header", "records"],
)
def test_reader_keeps_input_open(reader: Callable[[BinaryIO], object]) -> None:
    source = BytesIO(compressed(*objects()))
    reader(source)
    assert not source.closed


def test_header_reads_one_logical_line(monkeypatch: pytest.MonkeyPatch) -> None:
    actual = gzip.GzipFile
    observed: list[bytes] = []

    class CountedGzip:
        def __init__(self, *, fileobj: BinaryIO, mode: str) -> None:
            self.inner = actual(fileobj=fileobj, mode=mode)

        def __enter__(self) -> CountedGzip:
            return self

        def __exit__(self, *args: object) -> None:
            self.inner.close()

        def readline(self) -> bytes:
            line = self.inner.readline()
            observed.append(line)
            return line

    monkeypatch.setattr(gzip, "GzipFile", CountedGzip)
    source = BytesIO(
        gzip.compress(json.dumps(header()).encode() + b"\ninvalid-body\n", mtime=0)
    )
    extract.read_header(source)
    assert observed == [json.dumps(header()).encode() + b"\n"]


@pytest.mark.parametrize(
    "items, problem",
    [
        ([RAW, ExportDate(DATE), CORRECTIONS], "before export date"),
        ([CORRECTIONS], "before export date"),
        ([], "export date"),
        ([ExportDate(DATE)], "trailer"),
        ([ExportDate(DATE), ExportDate(DATE), CORRECTIONS], "duplicate export date"),
        ([ExportDate(DATE), CORRECTIONS, RAW], "after trailer"),
    ],
    ids=[
        "record-first",
        "corrections-first",
        "no-date",
        "no-trailer",
        "duplicate-date",
        "after-trailer",
    ],
)
def test_writer_bad_sequence(items: list[ExportItem], problem: str) -> None:
    with pytest.raises(WellnessFormatError, match=problem):
        write(items)


HEADER_BAD: list[tuple[str, object, str]] = [
    ("format", "foreign-extract", "format"),
    ("version", 2, "written by a newer fitdocs \\(extract version 2\\)"),
    ("version", 0, "version"),
    ("version", True, "version"),
    ("version", "1", "version"),
    ("original_sha256", 42, "original_sha256"),
    ("original_size", "123", "original_size"),
    ("original_size", -1, "original_size"),
    ("original_size", True, "original_size"),
    ("export_date", 42, "export_date"),
    ("export_date", "2024-02-06 14:30:00", "export date"),
    ("export_date_utc", 42, "export_date_utc"),
    ("export_date_utc", "2024-02-06T22:30:01Z", "export_date_utc"),
    ("record_types", "types", "record_types"),
    ("record_types", [42], "record_types"),
    ("record_types", ["HKQuantityTypeIdentifierHeartRate"], "record_types"),
    ("record_types", [TYPES[0], TYPES[0]], "record_types"),
    ("unexpected", "extra", "header keys"),
]


@pytest.mark.parametrize(
    "key, value, problem",
    HEADER_BAD,
    ids=[f"{key}-{index}" for index, (key, _, _) in enumerate(HEADER_BAD)],
)
@pytest.mark.parametrize(
    "reader",
    [extract.read_header, lambda stream: list(extract.read_records(stream))],
    ids=["header", "records"],
)
def test_invalid_header(
    key: str, value: object, problem: str, reader: Callable[[BinaryIO], object]
) -> None:
    changed = {**header(), key: value}
    with pytest.raises(WellnessFormatError, match=problem):
        reader(
            BytesIO(
                compressed(
                    changed, {"end": {"records": 0, "corrections": asdict(CORRECTIONS)}}
                )
            )
        )


@pytest.mark.parametrize("key", list(header()))
def test_missing_header_field(key: str) -> None:
    changed = header()
    del changed[key]
    problem = {"format": "format", "version": "version"}.get(key, "header keys")
    with pytest.raises(WellnessFormatError, match=problem):
        extract.read_header(BytesIO(compressed(changed)))


@pytest.mark.parametrize("key, field", FIELDS)
def test_non_string_record_field(key: str, field: str) -> None:
    changed = {**record(), key: 42}
    with pytest.raises(WellnessFormatError, match=key):
        list(extract.read_records(BytesIO(compressed(header(), changed, trailer()))))


@pytest.mark.parametrize(
    "change, problem",
    [
        ({"unknown": "value"}, "record keys"),
        ({"type": "HKQuantityTypeIdentifierHeartRate"}, "record type"),
        ({"metadata": "pairs"}, "metadata"),
        ({"metadata": ["pair"]}, "metadata"),
        ({"metadata": [["key"]]}, "metadata"),
        ({"metadata": [["key", "value", "third"]]}, "metadata"),
        ({"metadata": [[42, "value"]]}, "metadata"),
        ({"metadata": [["key", None]]}, "metadata"),
    ],
    ids=[
        "unknown-key",
        "type-not-header",
        "metadata-text",
        "metadata-pair-text",
        "metadata-short",
        "metadata-long",
        "metadata-key-number",
        "metadata-value-null",
    ],
)
def test_invalid_record(change: dict[str, object], problem: str) -> None:
    changed = {**record(), **change}
    with pytest.raises(WellnessFormatError, match=problem):
        list(extract.read_records(BytesIO(compressed(header(), changed, trailer()))))


def test_missing_record_type() -> None:
    changed = record()
    del changed["type"]
    with pytest.raises(WellnessFormatError, match="record type"):
        list(extract.read_records(BytesIO(compressed(header(), changed, trailer()))))


def test_record_not_in_header_subset() -> None:
    changed = {**header(), "record_types": [str(AppleType.BODY_MASS)]}
    with pytest.raises(WellnessFormatError, match="record type"):
        list(extract.read_records(BytesIO(compressed(changed, record(), trailer()))))


@pytest.mark.parametrize(
    "ending, problem",
    [
        ({"end": {"records": 2, "corrections": asdict(CORRECTIONS)}}, "record count"),
        ({"end": {"records": True, "corrections": asdict(CORRECTIONS)}}, "records"),
        ({"end": {"records": -1, "corrections": asdict(CORRECTIONS)}}, "records"),
        ({"end": {"records": "1", "corrections": asdict(CORRECTIONS)}}, "records"),
        ({"end": {"records": 1}}, "trailer keys"),
        ({"end": {"records": 1, "corrections": []}}, "corrections"),
        ({"end": {"records": 1, "corrections": {}}}, "corrections keys"),
        (
            {"end": {"records": 1, "corrections": {**asdict(CORRECTIONS), "extra": 3}}},
            "corrections keys",
        ),
        ({"end": 1}, "trailer"),
        (
            {"end": {"records": 1, "corrections": asdict(CORRECTIONS)}, "extra": 2},
            "trailer keys",
        ),
    ],
    ids=[
        "count-mismatch",
        "boolean-count",
        "negative-count",
        "text-count",
        "missing-corrections",
        "corrections-list",
        "corrections-empty",
        "corrections-extra",
        "end-number",
        "trailer-extra",
    ],
)
def test_invalid_trailer(ending: object, problem: str) -> None:
    with pytest.raises(WellnessFormatError, match=problem):
        list(extract.read_records(BytesIO(compressed(header(), record(), ending))))


@pytest.mark.parametrize("field", list(asdict(CORRECTIONS)))
@pytest.mark.parametrize("value", [True, -1, "2"], ids=["boolean", "negative", "text"])
def test_invalid_correction_count(field: str, value: object) -> None:
    ending = {
        "end": {"records": 1, "corrections": {**asdict(CORRECTIONS), field: value}}
    }
    with pytest.raises(WellnessFormatError, match=field):
        list(extract.read_records(BytesIO(compressed(header(), record(), ending))))


@pytest.mark.parametrize(
    "extra", [record(), trailer(), {}], ids=["record", "trailer", "object"]
)
def test_trailer_last(extra: object) -> None:
    with pytest.raises(WellnessFormatError, match="after trailer"):
        list(extract.read_records(BytesIO(compressed(*objects(), extra))))


def test_missing_trailer() -> None:
    with pytest.raises(WellnessFormatError, match="missing trailer"):
        list(extract.read_records(BytesIO(compressed(header(), record()))))


@pytest.mark.parametrize("position", [0, 1, 2], ids=["header", "record", "trailer"])
def test_non_object_line(position: int) -> None:
    changed = objects()
    changed[position] = []
    with pytest.raises(WellnessFormatError, match="object"):
        list(extract.read_records(BytesIO(compressed(*changed))))


@pytest.mark.parametrize(
    "raw",
    [
        b"not-gzip",
        compressed(*objects())[:-5],
        b"\x1f\x8b\x08\x00" + b"\x00" * 6 + b"\x06",
    ],
    ids=["bad-gzip", "truncated", "zlib"],
)
def test_corrupt_gzip(raw: bytes) -> None:
    with pytest.raises(WellnessFormatError, match="gzip"):
        list(extract.read_records(BytesIO(raw)))


@pytest.mark.parametrize(
    "raw, problem",
    [(b"{bad json}\n", "JSON"), (b"\xff\n", "UTF-8"), (b"", "header")],
    ids=["json", "utf8", "empty"],
)
@pytest.mark.parametrize(
    "reader",
    [extract.read_header, lambda stream: list(extract.read_records(stream))],
    ids=["header", "records"],
)
def test_invalid_text(
    raw: bytes, problem: str, reader: Callable[[BinaryIO], object]
) -> None:
    with pytest.raises(WellnessFormatError, match=problem):
        reader(BytesIO(gzip.compress(raw, mtime=0)))


@pytest.mark.parametrize(
    "reader",
    [extract.read_header, lambda stream: list(extract.read_records(stream))],
    ids=["header", "records"],
)
def test_io_error_propagates(reader: Callable[[BinaryIO], object]) -> None:
    class BrokenSource(BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise OSError("synthetic read fault")

    with pytest.raises(OSError, match="synthetic read fault"):
        reader(BrokenSource())


def test_writer_io_error_propagates() -> None:
    class BrokenSink(BytesIO):
        def write(self, data: object) -> int:
            raise OSError("synthetic write fault")

    with pytest.raises(OSError, match="synthetic write fault"):
        extract.write_extract(
            cast(BinaryIO, BrokenSink()),
            [ExportDate(DATE), CORRECTIONS],
            original_sha256=SHA,
            original_size=SIZE,
        )


@pytest.mark.parametrize("change", ["added", "removed"])
@pytest.mark.parametrize(
    "reader",
    [extract.read_header, lambda stream: list(extract.read_records(stream))],
    ids=["header", "records"],
)
def test_newer_layout_version_precedes_keys(
    change: str, reader: Callable[[BinaryIO], object]
) -> None:
    future = {**header(), "version": 2}
    if change == "added":
        future["future_field"] = "future-layout-text"
    else:
        del future["original_sha256"]
    with pytest.raises(
        WellnessFormatError, match=r"written by a newer fitdocs \(extract version 2\)"
    ):
        reader(BytesIO(compressed(future)))


@pytest.mark.parametrize(
    "raw",
    [b"not-gzip", b"\x1f\x8b\x08\x00" + b"\x00" * 6 + b"\x06"],
    ids=["bad-gzip", "zlib"],
)
def test_header_corrupt_gzip(raw: bytes) -> None:
    with pytest.raises(WellnessFormatError, match="gzip"):
        extract.read_header(BytesIO(raw))


@pytest.mark.parametrize("position", [1, 2], ids=["record", "trailer"])
@pytest.mark.parametrize(
    "raw, problem",
    [(b"{bad json}\n", "JSON"), (b"\xff\n", "UTF-8")],
    ids=["json", "utf8"],
)
def test_body_invalid_text(position: int, raw: bytes, problem: str) -> None:
    prefix = b"".join(json.dumps(obj).encode() + b"\n" for obj in objects()[:position])
    with pytest.raises(WellnessFormatError, match=problem):
        list(extract.read_records(BytesIO(gzip.compress(prefix + raw, mtime=0))))


def test_header_frozen() -> None:
    restored = extract.read_header(BytesIO(compressed(*objects())))
    field = "version"
    with pytest.raises(FrozenInstanceError):
        setattr(restored, field, 2)


def test_writer_consumes_items_incrementally(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    actual = extract._write_line

    def counted(stream: gzip.GzipFile, obj: object) -> None:
        events.append("written")
        actual(stream, obj)

    def items() -> Iterator[ExportItem]:
        batch: list[ExportItem] = [ExportDate(DATE), RAW, CORRECTIONS]
        for item in batch:
            events.append("yielded")
            yield item

    monkeypatch.setattr(extract, "_write_line", counted)
    extract.write_extract(BytesIO(), items(), original_sha256=SHA, original_size=SIZE)
    assert events == ["yielded", "written", "yielded", "written", "yielded", "written"]


_ALT_PROVENANCE = (
    (
        "1a" * 32,
        173,
        "2032-11-19 01:02:03 -0430",
        "2032-11-19T05:32:03Z",
    ),
    (
        "BC" * 32,
        1099511632044,
        "2033-07-04T21:22:23+09:45",
        "2033-07-04T11:37:23Z",
    ),
)
_PROVENANCE_FIELDS = (
    "original_sha256",
    "original_size",
    "export_date",
    "export_date_utc",
)
_RECORD_TYPE_INPUTS = (
    "HKCategoryTypeIdentifierSleepAnalysis",
    "HKQuantityTypeIdentifierBodyMass",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
    "HKQuantityTypeIdentifierOxygenSaturation",
    "HKQuantityTypeIdentifierRespiratoryRate",
    "HKQuantityTypeIdentifierRestingHeartRate",
    "HKQuantityTypeIdentifierStepCount",
    "HKQuantityTypeIdentifierVO2Max",
)
_ALT_RECORD_TEXT = (
    ("sourceName", "source_name", "Example writer A écume", "Example writer B 雪"),
    ("sourceVersion", "source_version", "012.004", "088.009"),
    (
        "device",
        "device",
        "name:Example Watch A, manufacturer:Apple, model:Watch3, hardware:010",
        "name:Example Watch B, manufacturer:Apple, model:Watch5, hardware:030",
    ),
    ("unit", "unit", "count/min", "kg"),
    (
        "creationDate",
        "creation_date",
        "2031-09-04 08:09:10 +0100",
        "2032-10-05 11:12:13 -0300",
    ),
    (
        "startDate",
        "start_date",
        "2031-09-03 04:05:06 +0100",
        "2032-10-04 07:08:09 -0300",
    ),
    (
        "endDate",
        "end_date",
        "2031-09-03 05:06:07 +0100",
        "2032-10-04 08:09:10 -0300",
    ),
    ("value", "value", "003.125", "900.875"),
)
_ALT_METADATA = (
    (("c-alt", "103"), ("a-alt", "δ"), ("c-alt", "303")),
    (
        ("right", "700"),
        ("left", "étoile"),
        ("center", "090"),
        ("right", "004"),
    ),
)
_OPAQUE_SHA = "opaque synthetic provenance 雪: not a digest"


def _header_projection(payload: dict[str, object], field: str) -> object:
    try:
        restored = extract.read_header(BytesIO(compressed(payload)))
    except WellnessFormatError as error:
        return error
    return cast(object, getattr(restored, field))


def _decoded_records(*payloads: object) -> list[RawRecord] | WellnessFormatError:
    try:
        return list(extract.read_records(BytesIO(compressed(*payloads))))
    except WellnessFormatError as error:
        return error


def _record_projection(payload: dict[str, object], field: str) -> object:
    restored = _decoded_records(header(), payload, trailer())
    if isinstance(restored, WellnessFormatError):
        return restored
    return cast(object, getattr(restored[0], field))


@pytest.mark.parametrize("example", [0, 1], ids=["west", "east"])
@pytest.mark.parametrize("field", _PROVENANCE_FIELDS)
def test_writer_contrasting_provenance(example: int, field: str) -> None:
    sha, size, date, utc = _ALT_PROVENANCE[example]
    sink = BytesIO()
    extract.write_extract(
        sink,
        [ExportDate(date), RAW, CORRECTIONS],
        original_sha256=sha,
        original_size=size,
    )
    payload = json.loads(gzip.decompress(sink.getvalue()).splitlines()[0])
    expected = dict(zip(_PROVENANCE_FIELDS, (sha, size, date, utc), strict=True))
    assert payload[field] == expected[field]


@pytest.mark.parametrize("example", [0, 1], ids=["west", "east"])
@pytest.mark.parametrize("field", _PROVENANCE_FIELDS)
def test_reader_contrasting_provenance(example: int, field: str) -> None:
    sha, size, date, utc = _ALT_PROVENANCE[example]
    values = dict(zip(_PROVENANCE_FIELDS, (sha, size, date, utc), strict=True))
    payload = {**header(), **values}
    assert _header_projection(payload, field) == values[field]


@pytest.mark.parametrize(
    "types",
    [
        [],
        ["HKQuantityTypeIdentifierStepCount", "HKQuantityTypeIdentifierBodyMass"],
        [
            "HKQuantityTypeIdentifierVO2Max",
            "HKCategoryTypeIdentifierSleepAnalysis",
            "HKQuantityTypeIdentifierRestingHeartRate",
        ],
    ],
    ids=["empty", "pair-subset", "shuffled-triple"],
)
def test_reader_header_type_projection(types: list[str]) -> None:
    assert _header_projection(
        {**header(), "record_types": types}, "record_types"
    ) == tuple(types)


@pytest.mark.parametrize("record_type", _RECORD_TYPE_INPUTS)
def test_writer_all_record_types(record_type: str) -> None:
    changed = replace(RAW, type=record_type)
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert payload["type"] == record_type


@pytest.mark.parametrize("record_type", _RECORD_TYPE_INPUTS)
def test_reader_all_record_types(record_type: str) -> None:
    assert _record_projection({**record(), "type": record_type}, "type") == record_type


@pytest.mark.parametrize("example", [0, 1], ids=["first", "second"])
@pytest.mark.parametrize("key, field, first, second", _ALT_RECORD_TEXT)
def test_writer_contrasting_record_text(
    example: int, key: str, field: str, first: str, second: str
) -> None:
    value = (first, second)[example]
    changed = replace(RAW, **{field: value})  # type: ignore[arg-type]
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert payload[key] == value


@pytest.mark.parametrize("example", [0, 1], ids=["first", "second"])
@pytest.mark.parametrize("key, field, first, second", _ALT_RECORD_TEXT)
def test_reader_contrasting_record_text(
    example: int, key: str, field: str, first: str, second: str
) -> None:
    value = (first, second)[example]
    assert _record_projection({**record(), key: value}, field) == value


@pytest.mark.parametrize(
    "metadata", _ALT_METADATA, ids=["alternate-three", "alternate-four"]
)
def test_writer_contrasting_metadata(metadata: tuple[tuple[str, str], ...]) -> None:
    changed = replace(RAW, metadata=metadata)
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert payload["metadata"] == [list(pair) for pair in metadata]


@pytest.mark.parametrize(
    "metadata", _ALT_METADATA, ids=["alternate-three", "alternate-four"]
)
def test_reader_contrasting_metadata(metadata: tuple[tuple[str, str], ...]) -> None:
    payload = {**record(), "metadata": [list(pair) for pair in metadata]}
    assert _record_projection(payload, "metadata") == metadata


def test_reader_accepts_zero_original_size() -> None:
    assert _header_projection({**header(), "original_size": 0}, "original_size") == 0


def test_reader_accepts_zero_record_count() -> None:
    ending = {"end": {"records": 0, "corrections": asdict(CORRECTIONS)}}
    assert _decoded_records(header(), ending) == []


@pytest.mark.parametrize("field", list(asdict(CORRECTIONS)))
def test_reader_accepts_each_zero_correction(field: str) -> None:
    ending = {
        "end": {
            "records": 1,
            "corrections": {**asdict(CORRECTIONS), field: 0},
        }
    }
    assert _decoded_records(header(), record(), ending) == [RAW]


def test_reader_accepts_clean_corrections() -> None:
    ending = {"end": {"records": 1, "corrections": asdict(Corrections(0, 0, 0))}}
    assert _decoded_records(header(), record(), ending) == [RAW]


@pytest.mark.parametrize("sha", [_OPAQUE_SHA, ""], ids=["opaque", "empty"])
def test_writer_preserves_opaque_provenance(sha: str) -> None:
    sink = BytesIO()
    extract.write_extract(
        sink,
        [ExportDate(DATE), RAW, CORRECTIONS],
        original_sha256=sha,
        original_size=SIZE,
    )
    payload = json.loads(gzip.decompress(sink.getvalue()).splitlines()[0])
    assert payload["original_sha256"] == sha


@pytest.mark.parametrize("sha", [_OPAQUE_SHA, ""], ids=["opaque", "empty"])
def test_reader_preserves_opaque_provenance(sha: str) -> None:
    assert (
        _header_projection({**header(), "original_sha256": sha}, "original_sha256")
        == sha
    )


def test_writer_preserves_zero_original_size() -> None:
    sink = BytesIO()
    extract.write_extract(
        sink, [ExportDate(DATE), CORRECTIONS], original_sha256=SHA, original_size=0
    )
    payload = json.loads(gzip.decompress(sink.getvalue()).splitlines()[0])
    assert payload["original_size"] == 0


def test_reader_accepts_present_empty_metadata() -> None:
    assert _record_projection({**record(), "metadata": []}, "metadata") == ()


def test_writer_preserves_zero_record_count() -> None:
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), CORRECTIONS])).splitlines()[-1]
    )
    assert payload["end"]["records"] == 0


@pytest.mark.parametrize("field", list(asdict(CORRECTIONS)))
def test_writer_preserves_each_zero_correction(field: str) -> None:
    corrections = replace(CORRECTIONS, **{field: 0})
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), RAW, corrections])).splitlines()[-1]
    )
    assert payload["end"]["corrections"][field] == 0


def test_writer_preserves_clean_corrections() -> None:
    payload = json.loads(
        gzip.decompress(
            write([ExportDate(DATE), RAW, Corrections(0, 0, 0)])
        ).splitlines()[-1]
    )
    assert payload["end"]["corrections"] == asdict(Corrections(0, 0, 0))


_LEXICAL_RECORD_CASES = ("padded", "whitespace-only", "interior")
_LEXICAL_METADATA_MEMBERS = (
    ("key-padded", (" \te\u0301雪-key\r\n", "member-value-101")),
    ("value-padded", ("member-key-202", " \te\u0301雪-value\r\n")),
    ("key-whitespace-only", (" \t\r\n ", "member-value-303")),
    ("value-whitespace-only", ("member-key-404", " \r\n\t ")),
    ("key-interior", ("key-e\u0301雪\t gap\r\nend", "member-value-505")),
    ("value-interior", ("member-key-606", "value-e\u0301雪\t gap\r\nend")),
    ("key-empty", ("", "member-value-707")),
    ("value-empty", ("member-key-808", "")),
    ("both-empty", ("", "")),
)
_LEXICAL_METADATA_CONTAINERS = (
    ("empty-only", (("", ""),)),
    ("whitespace-only", ((" \t\r\n ", " \n\t\r "),)),
    ("repeated-empty", (("", ""), ("", ""))),
    ("mixed-empty-whitespace", (("", ""), (" \r\n\t ", "\t \n\r"))),
)
_LEXICAL_SHA = (
    ("padded", " \tverbatim-e\u0301雪-provenance\r\n"),
    ("whitespace-only", " \t\r\n "),
    ("interior", "verbatim-e\u0301雪\t middle\r\nend"),
)


def _lexical_record_value(field: str, variant: str) -> str:
    value = cast(str, getattr(RAW, field))
    if field in {"source_name", "device"}:
        value += "-e\u0301雪"
    if variant == "padded":
        return " \t" + value + "\r\n"
    if variant == "whitespace-only":
        return " \t\r\n "
    return value + "\t middle\r\nend"


def _lexical_metadata(subject: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    return (
        ("z-sentinel", "sentinel-before-919"),
        subject,
        ("a-sentinel", "sentinel-after-020"),
        (subject[0], "duplicate-key-tail-131"),
    )


@pytest.mark.parametrize("variant", _LEXICAL_RECORD_CASES)
@pytest.mark.parametrize("key, field", FIELDS[1:])
def test_writer_lexical_record_text(key: str, field: str, variant: str) -> None:
    value = _lexical_record_value(field, variant)
    changed = replace(RAW, **{field: value})  # type: ignore[arg-type]
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert (key in payload, payload.get(key)) == (True, value)


@pytest.mark.parametrize("variant", _LEXICAL_RECORD_CASES)
@pytest.mark.parametrize("key, field", FIELDS[1:])
def test_reader_lexical_record_text(key: str, field: str, variant: str) -> None:
    value = _lexical_record_value(field, variant)
    assert _record_projection({**record(), key: value}, field) == value


@pytest.mark.parametrize(
    "name, subject",
    _LEXICAL_METADATA_MEMBERS,
    ids=[name for name, _ in _LEXICAL_METADATA_MEMBERS],
)
def test_writer_lexical_metadata_member(name: str, subject: tuple[str, str]) -> None:
    metadata = _lexical_metadata(subject)
    changed = replace(RAW, metadata=metadata)
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert ("metadata" in payload, payload.get("metadata")) == (
        True,
        [list(pair) for pair in metadata],
    )


@pytest.mark.parametrize(
    "name, subject",
    _LEXICAL_METADATA_MEMBERS,
    ids=[name for name, _ in _LEXICAL_METADATA_MEMBERS],
)
def test_reader_lexical_metadata_member(name: str, subject: tuple[str, str]) -> None:
    metadata = _lexical_metadata(subject)
    payload = {**record(), "metadata": [list(pair) for pair in metadata]}
    assert _record_projection(payload, "metadata") == metadata


@pytest.mark.parametrize(
    "name, metadata",
    _LEXICAL_METADATA_CONTAINERS,
    ids=[name for name, _ in _LEXICAL_METADATA_CONTAINERS],
)
def test_writer_lexical_metadata_container(
    name: str, metadata: tuple[tuple[str, str], ...]
) -> None:
    changed = replace(RAW, metadata=metadata)
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert ("metadata" in payload, payload.get("metadata")) == (
        True,
        [list(pair) for pair in metadata],
    )


@pytest.mark.parametrize(
    "name, metadata",
    _LEXICAL_METADATA_CONTAINERS,
    ids=[name for name, _ in _LEXICAL_METADATA_CONTAINERS],
)
def test_reader_lexical_metadata_container(
    name: str, metadata: tuple[tuple[str, str], ...]
) -> None:
    payload = {**record(), "metadata": [list(pair) for pair in metadata]}
    assert _record_projection(payload, "metadata") == metadata


@pytest.mark.parametrize(
    "name, sha", _LEXICAL_SHA, ids=[name for name, _ in _LEXICAL_SHA]
)
def test_writer_lexical_provenance(name: str, sha: str) -> None:
    sink = BytesIO()
    extract.write_extract(
        sink,
        [ExportDate(DATE), RAW, CORRECTIONS],
        original_sha256=sha,
        original_size=SIZE,
    )
    payload = json.loads(gzip.decompress(sink.getvalue()).splitlines()[0])
    assert payload["original_sha256"] == sha


@pytest.mark.parametrize(
    "name, sha", _LEXICAL_SHA, ids=[name for name, _ in _LEXICAL_SHA]
)
def test_reader_lexical_provenance(name: str, sha: str) -> None:
    payload = {**header(), "original_sha256": sha}
    assert _header_projection(payload, "original_sha256") == sha


_CASE_RECORD_TEXT = (
    (
        "sourceVersion-ascii",
        "sourceVersion",
        "source_version",
        "12.4RC",
        "HKQuantityTypeIdentifierStepCount",
    ),
    (
        "sourceVersion-unicode",
        "sourceVersion",
        "source_version",
        "12.4RC-ßΣ",
        "HKQuantityTypeIdentifierStepCount",
    ),
    ("unit", "unit", "unit", "mL/kg*min", "HKQuantityTypeIdentifierVO2Max"),
    (
        "creationDate",
        "creationDate",
        "creation_date",
        "2031-09-04T08:09:10+0100",
        "HKQuantityTypeIdentifierStepCount",
    ),
    (
        "startDate",
        "startDate",
        "start_date",
        "2031-09-03T04:05:06+0100",
        "HKQuantityTypeIdentifierStepCount",
    ),
    (
        "endDate",
        "endDate",
        "end_date",
        "2031-09-03T05:06:07+0100",
        "HKQuantityTypeIdentifierStepCount",
    ),
    (
        "value",
        "value",
        "value",
        "HKCategoryValueSleepAnalysisAsleepCore",
        "HKCategoryTypeIdentifierSleepAnalysis",
    ),
)
_CASE_METADATA_MEMBERS = (
    ("key-ascii", ("HKMetadataKeyHeartRateMotionContext", "101")),
    ("key-unicode", ("HKMetadataKeyHeartRateMotionContext Straße Σ", "202")),
    ("value-ascii", ("member-key-303", "CaseSensitiveValue ÉCUME")),
    ("value-unicode", ("member-key-404", "CaseSensitiveValue Straße Σ")),
)


@pytest.mark.parametrize(
    "name, key, field, value, record_type",
    _CASE_RECORD_TEXT,
    ids=[row[0] for row in _CASE_RECORD_TEXT],
)
def test_writer_case_record_text(
    name: str, key: str, field: str, value: str, record_type: str
) -> None:
    changed = replace(RAW, type=record_type, **{field: value})  # type: ignore[arg-type]
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert payload[key] == value


@pytest.mark.parametrize(
    "name, key, field, value, record_type",
    _CASE_RECORD_TEXT,
    ids=[row[0] for row in _CASE_RECORD_TEXT],
)
def test_reader_case_record_text(
    name: str, key: str, field: str, value: str, record_type: str
) -> None:
    payload = {**record(), "type": record_type, key: value}
    assert _record_projection(payload, field) == value


@pytest.mark.parametrize(
    "name, subject",
    _CASE_METADATA_MEMBERS,
    ids=[name for name, _ in _CASE_METADATA_MEMBERS],
)
def test_writer_case_metadata_member(name: str, subject: tuple[str, str]) -> None:
    metadata = _lexical_metadata(subject)
    changed = replace(RAW, metadata=metadata)
    payload = json.loads(
        gzip.decompress(write([ExportDate(DATE), changed, CORRECTIONS])).splitlines()[1]
    )
    assert payload["metadata"] == [list(pair) for pair in metadata]


@pytest.mark.parametrize(
    "name, subject",
    _CASE_METADATA_MEMBERS,
    ids=[name for name, _ in _CASE_METADATA_MEMBERS],
)
def test_reader_case_metadata_member(name: str, subject: tuple[str, str]) -> None:
    metadata = _lexical_metadata(subject)
    payload = {**record(), "metadata": [list(pair) for pair in metadata]}
    assert _record_projection(payload, "metadata") == metadata


@pytest.mark.parametrize(
    "key, value, problem",
    [
        ("format", "FITDOCS.APPLE-HEALTH-EXTRACT", "invalid extract format"),
        ("record_types", ["hkquantitytypeidentifierstepcount"], "invalid record_types"),
        ("export_date_utc", "2024-02-06t22:30:00z", "invalid export_date_utc"),
    ],
    ids=["format", "record_types", "export_date_utc"],
)
@pytest.mark.parametrize(
    "reader",
    [extract.read_header, lambda stream: list(extract.read_records(stream))],
    ids=["header", "records"],
)
def test_header_exact_case(
    key: str, value: object, problem: str, reader: Callable[[BinaryIO], object]
) -> None:
    changed = {**header(), key: value}
    ending = {"end": {"records": 0, "corrections": asdict(CORRECTIONS)}}
    with pytest.raises(WellnessFormatError, match=f"^{problem}$"):
        reader(BytesIO(compressed(changed, ending)))


def test_record_exact_case() -> None:
    changed = {**record(), "type": "hkquantitytypeidentifierstepcount"}
    with pytest.raises(
        WellnessFormatError, match="^record type is absent from header record_types$"
    ):
        list(extract.read_records(BytesIO(compressed(header(), changed, trailer()))))
