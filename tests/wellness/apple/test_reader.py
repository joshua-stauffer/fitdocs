"""Synthetic streaming Apple Health reader checks."""

import gc
import io
import os
import tracemalloc
import zipfile
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, BinaryIO, cast
from xml.etree.ElementTree import fromstring

import pytest

from fitdocs.wellness.formats.apple import reader
from fitdocs.wellness.formats.apple.defects import CHUNK_BYTES
from fitdocs.wellness.formats.apple.reader import (
    MainDocument,
    iter_items,
    looks_like_export_document,
    main_member,
    open_main_document,
)
from fitdocs.wellness.formats.apple.records import (
    AppleType,
    Corrections,
    ExportDate,
    ExportItem,
    RawRecord,
)
from fitdocs.wellness.spec import WellnessFormatError

from .builders import (
    CDA_DOCUMENT,
    ENGLISH_MAIN,
    EXPORT_DATE,
    INVENTED_DOB,
    TRANSLATED_MAIN,
    bulk_records,
    export_document,
    record_xml,
    zip_members,
)


def test_export_date() -> None:
    data = export_document(records=[], include_doctype=False)
    items = list(iter_items(MainDocument(io.BytesIO(data), len(data)), progress=None))
    assert items[:1] == [ExportDate(EXPORT_DATE)]


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ([ENGLISH_MAIN], ENGLISH_MAIN),
        ([TRANSLATED_MAIN, "exportation/sante_cda.xml"], TRANSLATED_MAIN),
        (
            ["__MACOSX/" + ENGLISH_MAIN, "__MACOSX/apple_health_export/export_cda.xml"],
            None,
        ),
        (["DI_CONNECT/wellness.json"], None),
        (["first/a.xml", "first/a_cda.xml", "second/b.xml", "second/b_cda.xml"], None),
        (["health.xml", "health_cda.xml"], "health.xml"),
        (["one/two/a.xml", "one/two/a_cda.xml"], None),
        (["lonely.xml"], None),
        ([ENGLISH_MAIN, "health.xml", "health_cda.xml"], None),
        ([ENGLISH_MAIN, ENGLISH_MAIN], ENGLISH_MAIN),
    ],
    ids=[
        "english",
        "translated",
        "macosx",
        "garmin",
        "ambiguous",
        "root-level",
        "deep",
        "no-companion",
        "english-ambiguous",
        "duplicate-name",
    ],
)
def test_main_member(names: list[str], expected: str | None) -> None:
    assert main_member(iter(names)) == expected


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (export_document(), True),
        (export_document(malformed_doctype=True), True),
        (CDA_DOCUMENT, False),
        (b"<gpx/>", False),
        (b"<!DOCTYPE HealthData [ broken", True),
        (b"<HealthData>", True),
        (b"<HealthData/>", True),
        (b'<HealthData locale="fr"', True),
        (b"<HealthData\t", True),
        (b"<HealthData\n", True),
        (b"<HealthData\r", True),
        (b"<HealthDatabase/>", False),
        (b"<!DOCTYPE HealthDatabase>", False),
        (b"<healthdata/>", False),
        (b"", False),
    ],
    ids=[
        "export",
        "defective",
        "clinical",
        "gpx",
        "doctype-only",
        "root",
        "selfclosing",
        "space",
        "tab",
        "lf",
        "cr",
        "prefix-root",
        "prefix-doctype",
        "case",
        "empty",
    ],
)
def test_recognition(head: bytes, expected: bool) -> None:
    assert looks_like_export_document(head) is expected


def read_items(
    data: bytes,
    *,
    size: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[ExportItem]:
    stream = io.BytesIO(data)
    return list(
        iter_items(
            MainDocument(stream, len(data) if size is None else size), progress=progress
        )
    )


@pytest.mark.parametrize("record_type", list(AppleType))
def test_read_types(record_type: AppleType) -> None:
    data = export_document(
        records=[record_xml(record_type, value="73.04")], include_scaffold=False
    )
    records = [item for item in read_items(data) if isinstance(item, RawRecord)]
    assert [record.type for record in records] == [record_type]


FIELD_NAMES = [
    ("sourceName", "source_name"),
    ("sourceVersion", "source_version"),
    ("device", "device"),
    ("unit", "unit"),
    ("creationDate", "creation_date"),
    ("startDate", "start_date"),
    ("endDate", "end_date"),
    ("value", "value"),
]


@pytest.mark.parametrize(("xml_field", "field"), FIELD_NAMES)
@pytest.mark.parametrize(
    "text",
    [None, "", "0", "  MiXeD e\u0301 文  "],
    ids=["missing", "empty", "zero", "literal"],
)
def test_raw_fields(xml_field: str, field: str, text: str | None) -> None:
    data = export_document(
        records=[record_xml(AppleType.BODY_MASS, attributes={xml_field: text})],
        include_scaffold=False,
    )
    record = next(item for item in read_items(data) if isinstance(item, RawRecord))
    assert getattr(record, field) == text


def test_device_normalization() -> None:
    data = export_document(
        records=[record_xml(AppleType.STEP_COUNT)], include_scaffold=False
    )
    record = next(item for item in read_items(data) if isinstance(item, RawRecord))
    assert (
        record.device
        == "name:Example Apple Watch, manufacturer:Apple Inc., model:Watch"
    )


def test_metadata() -> None:
    metadata = [(" z ", "  MiXeD e\u0301 文  "), ("a", "0"), (" z ", ""), ("a", "2")]
    data = export_document(
        records=[
            record_xml(
                AppleType.HRV_SDNN,
                metadata=metadata,
                children=(
                    "<HeartRateVariabilityMetadataList>"
                    '<InstantaneousBeatsPerMinute bpm="321" time="private"/>'
                    "</HeartRateVariabilityMetadataList>"
                    '<Other key="intruder" value="secret"/>'
                ),
            )
        ],
        include_scaffold=False,
    )
    record = next(item for item in read_items(data) if isinstance(item, RawRecord))
    assert record.metadata == tuple(metadata)


def test_document_order() -> None:
    data = export_document(
        records=[
            record_xml(AppleType.STEP_COUNT, value="9"),
            record_xml(AppleType.BODY_MASS, value="2"),
            record_xml(AppleType.STEP_COUNT, value="7"),
        ],
        include_scaffold=False,
    )
    records = [item for item in read_items(data) if isinstance(item, RawRecord)]
    assert [(record.type, record.value) for record in records] == [
        (AppleType.STEP_COUNT, "9"),
        (AppleType.BODY_MASS, "2"),
        (AppleType.STEP_COUNT, "7"),
    ]


@pytest.mark.parametrize(
    "kind",
    [
        "nested",
        "unread",
        "Me",
        "Workout",
        "ActivitySummary",
        "ClinicalRecord",
        "Electrocardiogram",
        "Audiogram",
    ],
)
def test_private_elements(kind: str) -> None:
    if kind == "nested":
        extra = (
            "<Correlation>"
            + record_xml(AppleType.BODY_MASS, value=INVENTED_DOB)
            + "</Correlation>"
        )
    elif kind == "unread":
        extra = record_xml("HKQuantityTypeIdentifierHeartRate", value=INVENTED_DOB)
    else:
        extra = f'<{kind} type="{AppleType.BODY_MASS}" value="{INVENTED_DOB}"/>'
    data = export_document(
        records=[],
        include_doctype=False,
        include_me=False,
        include_scaffold=False,
        extra_elements=[extra],
    )
    assert read_items(data) == [ExportDate(EXPORT_DATE), Corrections(0, 0, 0)]


def test_corrections_trailer() -> None:
    data = export_document(
        malformed_doctype=True, control_character=True, duplicate_start_date=True
    )
    assert read_items(data)[-1] == Corrections(1, 1, 1)


@pytest.mark.parametrize(
    "fault", ["wrong-root", "late-date", "second-date", "unclosed"]
)
def test_xml_errors(fault: str) -> None:
    if fault == "wrong-root":
        data = (
            export_document(
                records=[],
                include_doctype=False,
                include_me=False,
                include_scaffold=False,
                extra_elements=["<HealthData/>"],
            )
            .replace(b'<HealthData locale="en_US">', b"<Other>")
            .replace(b"</HealthData>", b"</Other>")
        )
        match = "root must be HealthData"
    elif fault == "late-date":
        data = export_document(
            records=[record_xml(AppleType.STEP_COUNT)],
            export_date=None,
            include_doctype=False,
            include_scaffold=False,
            extra_elements=['<ExportDate value="later"/>'],
        )
        match = "Record before ExportDate"
    elif fault == "second-date":
        data = export_document(
            records=[],
            include_doctype=False,
            include_scaffold=False,
            extra_elements=['<ExportDate value="second"/>'],
        )
        match = "second ExportDate"
    else:
        data = export_document(
            records=[],
            malformed_doctype=True,
            include_scaffold=False,
            extra_elements=["<Unclosed>"],
        )
        line = data[: data.index(b"</HealthData>")].count(b"\n") + 1
        match = f"at line {line}, column 2:"
    with pytest.raises(WellnessFormatError, match=match):
        read_items(data)


def test_no_trailer_on_error() -> None:
    data = export_document(
        records=[], include_doctype=False, extra_elements=["<Unclosed>"]
    )
    items = iter_items(MainDocument(io.BytesIO(data), len(data)), progress=None)
    observed = []
    with pytest.raises(WellnessFormatError):
        while True:
            observed.append(next(items))
    assert observed == [ExportDate(EXPORT_DATE)]


@pytest.mark.parametrize("variant", ["bare", "zip", "zip64"])
def test_open_document(tmp_path: Path, variant: str) -> None:
    data = export_document(
        records=[record_xml(AppleType.BODY_MASS, value="87.9")], include_scaffold=False
    )
    path = tmp_path / "arbitrary.bin"
    path.write_bytes(
        data
        if variant == "bare"
        else zip_members({ENGLISH_MAIN: data}, force_zip64=variant == "zip64")
    )
    with open_main_document(path) as document:
        observed = (
            document.size,
            [
                item.value
                for item in iter_items(document, progress=None)
                if isinstance(item, RawRecord)
            ],
        )
    assert (
        observed,
        document.stream.closed,
        path.read_bytes(),
        sorted(item.name for item in tmp_path.iterdir()),
    ) == (
        (len(data), ["87.9"]),
        True,
        data
        if variant == "bare"
        else zip_members({ENGLISH_MAIN: data}, force_zip64=variant == "zip64"),
        [path.name],
    )


@pytest.mark.parametrize("variant", ["bare", "zip"])
@pytest.mark.parametrize("outcome", ["normal", "parse-error", "interrupt"])
def test_context_closes_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str, outcome: str
) -> None:
    data = export_document(
        records=[],
        include_doctype=False,
        extra_elements=["<Unclosed>"] if outcome == "parse-error" else [],
    )
    path = tmp_path / "candidate"
    path.write_bytes(data if variant == "bare" else zip_members({ENGLISH_MAIN: data}))
    opened = []
    modes = []
    original = Path.open

    def tracked(candidate: Path, *args: Any, **kwargs: Any) -> BinaryIO:
        stream = cast(BinaryIO, original(candidate, *args, **kwargs))
        if candidate == path:
            opened.append(stream)
            modes.append(args[0] if args else kwargs.get("mode", "r"))
        return stream

    monkeypatch.setattr(Path, "open", tracked)
    try:
        with open_main_document(path) as document:
            if outcome == "interrupt":
                raise KeyboardInterrupt
            list(iter_items(document, progress=None))
    except (WellnessFormatError, KeyboardInterrupt):
        pass
    assert (len(opened), opened[0].closed, document.stream.closed, modes) == (
        1,
        True,
        True,
        ["rb"],
    )


@pytest.mark.parametrize(
    "fault", ["missing-member", "crc", "compression", "encryption"]
)
def test_zip_errors(tmp_path: Path, fault: str) -> None:
    data = bytearray(
        zip_members(
            {
                "not-export.txt"
                if fault == "missing-member"
                else ENGLISH_MAIN: export_document()
            }
        )
    )
    central = data.index(b"PK\x01\x02")
    if fault == "crc":
        data[central + 16 : central + 20] = b"\x00\x00\x00\x00"
        match = "CRC"
    elif fault == "compression":
        data[8:10] = data[central + 10 : central + 12] = (99).to_bytes(2, "little")
        match = "compression"
    elif fault == "encryption":
        data[6:8] = data[central + 8 : central + 10] = (1).to_bytes(2, "little")
        match = "password"
    else:
        match = "no unique"
    path = tmp_path / "fault.zip"
    path.write_bytes(data)
    with (
        pytest.raises(WellnessFormatError, match=match),
        open_main_document(path) as document,
    ):
        list(iter_items(document, progress=None))


def test_consumer_runtime_error_is_not_a_format_error(tmp_path: Path) -> None:
    path = tmp_path / "export.zip"
    path.write_bytes(zip_members({ENGLISH_MAIN: export_document()}))
    with (
        pytest.raises(RuntimeError, match="consumer") as caught,
        open_main_document(path),
    ):
        raise RuntimeError("consumer")
    assert not isinstance(caught.value, WellnessFormatError)


def test_recursion_error_while_reading_member_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "export.zip"
    path.write_bytes(zip_members({ENGLISH_MAIN: export_document()}))

    def deep(self: zipfile.ZipExtFile, size: int = -1) -> bytes:
        raise RecursionError("deep")

    monkeypatch.setattr(zipfile.ZipExtFile, "read", deep)
    with pytest.raises(RecursionError), open_main_document(path) as document:
        list(iter_items(document, progress=None))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OSError), open_main_document(tmp_path / "absent"):
        pass


def test_caller_stream_remains_open() -> None:
    data = export_document(records=[])
    stream = io.BytesIO(data)
    list(iter_items(MainDocument(stream, len(data)), progress=None))
    assert not stream.closed


class ShortReads(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        return super().read(min(size, 257) if size is not None and size >= 0 else 257)


def test_progress_throttle() -> None:
    data = export_document(records=bulk_records(1000), include_doctype=False)
    calls = []
    list(
        iter_items(
            MainDocument(ShortReads(data), len(data)),
            progress=lambda read, size: calls.append((read, size)),
        )
    )
    percents = [read * 100 // size for read, size in calls]
    assert (
        0 < len(calls) <= 101,
        all(a < b for a, b in zip(percents, percents[1:], strict=False)),
        calls[-1],
    ) == (True, True, (len(data), len(data)))


def test_progress_zero_size() -> None:
    calls = []
    data = export_document(records=[])
    read_items(data, size=0, progress=lambda read, size: calls.append((read, size)))
    assert calls == []


def test_progress_none(monkeypatch: pytest.MonkeyPatch) -> None:
    data = export_document(records=[])
    observed = []
    original = reader._CountingReader.read

    def tracked(self: reader._CountingReader, size: int = -1) -> bytes:
        observed.append(self._progress)
        return original(self, size)

    monkeypatch.setattr(reader._CountingReader, "read", tracked)
    read_items(data)
    assert (bool(observed), set(observed)) == (True, {None})


@pytest.mark.parametrize("variant", ["bare", "zip"])
def test_bounded_candidate_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    data = export_document(records=bulk_records(6000), include_doctype=False)
    raw = (
        data
        if variant == "bare"
        else zip_members(
            {
                ENGLISH_MAIN: data,
                **{f"extras/{i:05d}-" + "x" * 230: b"" for i in range(4000)},
            }
        )
    )
    path = tmp_path / "candidate"
    path.write_bytes(raw)
    reads = []
    original = Path.open

    class CountingFile:
        def __init__(self, stream: BinaryIO) -> None:
            self.stream = stream

        def read(self, size: int = -1) -> bytes:
            reads.append((self.stream.tell(), size))
            return self.stream.read(size)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.stream, name)

        def __enter__(self) -> "CountingFile":
            return self

        def __exit__(self, *args: object) -> None:
            self.stream.close()

    def tracked(candidate: Path, *args: Any, **kwargs: Any) -> BinaryIO:
        stream = cast(BinaryIO, original(candidate, *args, **kwargs))
        return cast(BinaryIO, CountingFile(stream)) if candidate == path else stream

    monkeypatch.setattr(Path, "open", tracked)
    with open_main_document(path) as document:
        for _ in iter_items(document, progress=None):
            pass
    end = raw.rfind(b"PK\x05\x06") if variant == "zip" else -1
    cd_size = int.from_bytes(raw[end + 12 : end + 16], "little") if end >= 0 else 0
    cd_start = int.from_bytes(raw[end + 16 : end + 20], "little") if end >= 0 else -1
    allowed = [
        (0 <= size <= CHUNK_BYTES)
        or (size == -1 and len(raw) - position <= zipfile.ZIP_MAX_COMMENT + 22)
        or (variant == "zip" and position == cd_start and size == cd_size)
        for position, size in reads
    ]
    print("candidate reads", variant, len(raw), reads)
    assert (
        bool(reads),
        all(allowed),
        any(position == len(raw) - 22 for position, size in reads),
        (
            sum(position == cd_start and size == cd_size for position, size in reads),
            cd_size > CHUNK_BYTES,
        )
        if variant == "zip"
        else (0, False),
    ) == (True, True, True, (1, True) if variant == "zip" else (0, False))


def test_memory_plateau() -> None:
    documents = [
        export_document(records=bulk_records(count), include_doctype=False)
        for count in (6000, 24000)
    ]
    peaks = []
    for data in documents:
        gc.collect()
        stream = io.BytesIO(data)
        tracemalloc.start()
        for _ in iter_items(MainDocument(stream, len(data)), progress=None):
            pass
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    print("memory", [len(data) for data in documents], peaks)
    assert (
        all(len(data) > CHUNK_BYTES for data in documents),
        peaks[1] < peaks[0] * 1.5,
    ) == (True, True)


@pytest.mark.parametrize("text", ["", "0", "  MiXeD e\u0301 文  "])
def test_raw_export_date(text: str) -> None:
    data = export_document(records=[], export_date=text, include_doctype=False)
    assert read_items(data)[0] == ExportDate(text)


def test_nested_metadata_excluded() -> None:
    data = export_document(
        records=[
            record_xml(
                AppleType.BODY_MASS,
                children='<Other><MetadataEntry key="private" value="nested"/></Other>',
            )
        ],
        include_scaffold=False,
    )
    record = next(item for item in read_items(data) if isinstance(item, RawRecord))
    assert record.metadata == ()


def test_metadata_missing_values() -> None:
    data = export_document(
        records=[
            record_xml(
                AppleType.BODY_MASS,
                children=(
                    '<MetadataEntry/><MetadataEntry key="0"/><MetadataEntry value="x"/>'
                ),
            )
        ],
        include_scaffold=False,
    )
    record = next(item for item in read_items(data) if isinstance(item, RawRecord))
    assert record.metadata == (("", ""), ("0", ""), ("", "x"))


def test_zip64_declared_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = export_document(records=[], include_doctype=False)
    path = tmp_path / "large-size.zip"
    path.write_bytes(zip_members({ENGLISH_MAIN: data}, force_zip64=True))
    original = zipfile.ZipFile.getinfo

    def large_info(self: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
        info = original(self, name)
        info.file_size = (1 << 32) + len(data)
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", large_info)
    with open_main_document(path) as document:
        assert document.size == (1 << 32) + len(data)


@pytest.mark.parametrize("variant", ["bare", "zip"])
def test_main_document_read_once(tmp_path: Path, variant: str) -> None:
    data = export_document(records=bulk_records(6000), include_doctype=False)
    path = tmp_path / "once"
    path.write_bytes(data if variant == "bare" else zip_members({ENGLISH_MAIN: data}))
    reads: list[int] = []
    seeks: list[tuple[int, int]] = []

    class PayloadReads:
        def __init__(self, stream: BinaryIO) -> None:
            self.stream = stream

        def read(self, size: int = -1) -> bytes:
            chunk = self.stream.read(size)
            reads.append(len(chunk))
            return chunk

        def seek(self, offset: int, whence: int = 0) -> int:
            seeks.append((offset, whence))
            return self.stream.seek(offset, whence)

        def __getattr__(self, name: str) -> Any:
            return getattr(self.stream, name)

    with open_main_document(path) as document:
        wrapped = MainDocument(
            cast(BinaryIO, PayloadReads(document.stream)), document.size
        )
        for _ in iter_items(wrapped, progress=None):
            pass
    assert (sum(reads), seeks) == (len(data), [])


def test_profile_date_of_birth_absent() -> None:
    data = export_document()
    profile = next(child for child in fromstring(data) if child.tag == "Me")
    dob = profile.attrib["HKCharacteristicTypeIdentifierDateOfBirth"]
    print("profile precondition", "HKCharacteristicTypeIdentifierDateOfBirth", dob)
    assert (dob, INVENTED_DOB not in repr(read_items(data))) == (INVENTED_DOB, True)


@pytest.mark.parametrize("variant", ["bare", "zip", "zip64"])
def test_file_bytes_and_timestamp_unchanged(tmp_path: Path, variant: str) -> None:
    data = export_document(records=[], include_doctype=False)
    raw = (
        data
        if variant == "bare"
        else zip_members({ENGLISH_MAIN: data}, force_zip64=variant == "zip64")
    )
    path = tmp_path / "unchanged"
    path.write_bytes(raw)
    os.utime(path, ns=(111_000_000_000, 111_000_000_000))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    with open_main_document(path) as document:
        list(iter_items(document, progress=None))
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_main_document_frozen() -> None:
    document = MainDocument(io.BytesIO(b"raw"), 3)
    field = "size"
    with pytest.raises(FrozenInstanceError):
        setattr(document, field, 7)


def test_zip64_items_equal_plain(tmp_path: Path) -> None:
    data = export_document(
        records=[record_xml(AppleType.BODY_MASS, value="87.9")], include_scaffold=False
    )
    all_items = []
    for forced in (False, True):
        path = tmp_path / ("large.zip" if forced else "plain.zip")
        path.write_bytes(zip_members({ENGLISH_MAIN: data}, force_zip64=forced))
        with open_main_document(path) as document:
            all_items.append(list(iter_items(document, progress=None)))
    plain, large = all_items
    assert ([item.value for item in plain if isinstance(item, RawRecord)], large) == (
        ["87.9"],
        plain,
    )


def test_caller_stream_remains_open_on_error() -> None:
    data = export_document(
        records=[], include_doctype=False, extra_elements=["<Unclosed>"]
    )
    stream = io.BytesIO(data)
    with pytest.raises(WellnessFormatError):
        list(iter_items(MainDocument(stream, len(data)), progress=None))
    assert not stream.closed


def test_main_document_dataclass_contract() -> None:
    from dataclasses import is_dataclass

    assert is_dataclass(MainDocument)


def test_main_document_field_names_contract() -> None:
    from dataclasses import fields

    assert tuple(field.name for field in fields(MainDocument)) == ("stream", "size")


@pytest.mark.parametrize("name", ["stream", "size"])
def test_main_document_field_types_contract(name: str) -> None:
    from typing import get_type_hints

    assert get_type_hints(MainDocument)[name] == {"stream": BinaryIO, "size": int}[name]


@pytest.mark.parametrize("name", ["stream", "size"])
@pytest.mark.parametrize("slot", ["default", "default_factory"])
def test_main_document_no_field_defaults_contract(name: str, slot: str) -> None:
    from dataclasses import MISSING, fields

    field = next(field for field in fields(MainDocument) if field.name == name)
    assert getattr(field, slot) is MISSING


def test_main_document_frozen_parameter_contract() -> None:
    parameter = "__dataclass_params__"
    assert getattr(MainDocument, parameter).frozen is True


@pytest.mark.parametrize("omitted", ["stream", "size", "both"])
def test_main_document_required_fields_contract(omitted: str) -> None:
    construct: Any = MainDocument
    with pytest.raises(TypeError):
        if omitted == "stream":
            construct(size=3)
        elif omitted == "size":
            construct(io.BytesIO(b"raw"))
        else:
            construct()


@pytest.mark.parametrize("mode", ["positional", "keyword"])
def test_main_document_normal_constructor_contract(mode: str) -> None:
    stream = io.BytesIO(b"raw")
    document = (
        MainDocument(stream, 3)
        if mode == "positional"
        else MainDocument(stream=stream, size=3)
    )
    assert (document.stream is stream, document.size) == (True, 3)


def test_iter_items_parameter_names_contract() -> None:
    from inspect import signature

    assert tuple(signature(iter_items).parameters) == ("document", "progress")


@pytest.mark.parametrize("name", ["document", "progress"])
def test_iter_items_parameter_kinds_contract(name: str) -> None:
    from inspect import Parameter, signature

    expected = {
        "document": Parameter.POSITIONAL_OR_KEYWORD,
        "progress": Parameter.KEYWORD_ONLY,
    }
    assert signature(iter_items).parameters[name].kind == expected[name]


@pytest.mark.parametrize("name", ["document", "progress"])
def test_iter_items_no_parameter_defaults_contract(name: str) -> None:
    from inspect import Parameter, signature

    assert signature(iter_items).parameters[name].default is Parameter.empty


@pytest.mark.parametrize("name", ["document", "progress", "return"])
def test_iter_items_type_annotations_contract(name: str) -> None:
    from collections.abc import Iterator
    from typing import get_type_hints

    expected = {
        "document": MainDocument,
        "progress": Callable[[int, int], None] | None,
        "return": Iterator[ExportItem],
    }
    assert get_type_hints(iter_items)[name] == expected[name]


@pytest.mark.parametrize("omitted", ["document", "progress", "both"])
def test_iter_items_required_arguments_contract(omitted: str) -> None:
    invoke: Any = iter_items
    document = MainDocument(io.BytesIO(b"raw"), 3)
    with pytest.raises(TypeError):
        if omitted == "document":
            invoke(progress=None)
        elif omitted == "progress":
            invoke(document)
        else:
            invoke()


def test_iter_items_rejects_positional_progress_contract() -> None:
    invoke: Any = iter_items
    document = MainDocument(io.BytesIO(b"raw"), 3)
    with pytest.raises(TypeError):
        invoke(document, None)


@pytest.mark.parametrize("mode", ["positional-document", "keyword-document"])
def test_iter_items_explicit_none_contract(mode: str) -> None:
    data = export_document(
        records=[], include_doctype=False, include_me=False, include_scaffold=False
    )
    document = MainDocument(io.BytesIO(data), len(data))
    items = (
        iter_items(document, progress=None)
        if mode == "positional-document"
        else iter_items(document=document, progress=None)
    )
    assert list(items) == [ExportDate(EXPORT_DATE), Corrections(0, 0, 0)]


@pytest.mark.parametrize(
    ("name", "parameter"),
    [
        ("main_member", "names"),
        ("looks_like_export_document", "head"),
        ("open_main_document", "candidate"),
    ],
)
def test_remaining_public_parameter_names_contract(name: str, parameter: str) -> None:
    from inspect import signature

    functions: dict[str, Callable[..., Any]] = {
        "main_member": main_member,
        "looks_like_export_document": looks_like_export_document,
        "open_main_document": open_main_document,
    }
    assert tuple(signature(functions[name]).parameters) == (parameter,)


@pytest.mark.parametrize(
    ("name", "parameter"),
    [
        ("main_member", "names"),
        ("looks_like_export_document", "head"),
        ("open_main_document", "candidate"),
    ],
)
def test_remaining_public_parameter_kinds_contract(name: str, parameter: str) -> None:
    from inspect import Parameter, signature

    functions: dict[str, Callable[..., Any]] = {
        "main_member": main_member,
        "looks_like_export_document": looks_like_export_document,
        "open_main_document": open_main_document,
    }
    assert (
        signature(functions[name]).parameters[parameter].kind
        == Parameter.POSITIONAL_OR_KEYWORD
    )


@pytest.mark.parametrize(
    ("name", "parameter"),
    [
        ("main_member", "names"),
        ("looks_like_export_document", "head"),
        ("open_main_document", "candidate"),
    ],
)
def test_remaining_public_no_defaults_contract(name: str, parameter: str) -> None:
    from inspect import Parameter, signature

    functions: dict[str, Callable[..., Any]] = {
        "main_member": main_member,
        "looks_like_export_document": looks_like_export_document,
        "open_main_document": open_main_document,
    }
    assert signature(functions[name]).parameters[parameter].default is Parameter.empty


@pytest.mark.parametrize(
    ("name", "parameter"),
    [
        ("main_member", "names"),
        ("looks_like_export_document", "head"),
        ("open_main_document", "candidate"),
    ],
)
def test_remaining_public_parameter_types_contract(name: str, parameter: str) -> None:
    from collections.abc import Iterable
    from inspect import unwrap
    from typing import get_type_hints

    functions: dict[str, Callable[..., Any]] = {
        "main_member": main_member,
        "looks_like_export_document": looks_like_export_document,
        "open_main_document": open_main_document,
    }
    expected = {
        "main_member": Iterable[str],
        "looks_like_export_document": bytes,
        "open_main_document": Path,
    }
    assert get_type_hints(unwrap(functions[name]))[parameter] == expected[name]


@pytest.mark.parametrize(
    "name", ["main_member", "looks_like_export_document", "open_main_document"]
)
def test_remaining_public_return_types_contract(name: str) -> None:
    from collections.abc import Iterator
    from inspect import unwrap
    from typing import get_type_hints

    functions: dict[str, Callable[..., Any]] = {
        "main_member": main_member,
        "looks_like_export_document": looks_like_export_document,
        "open_main_document": open_main_document,
    }
    expected = {
        "main_member": str | None,
        "looks_like_export_document": bool,
        "open_main_document": Iterator[MainDocument],
    }
    assert get_type_hints(unwrap(functions[name]))["return"] == expected[name]


@pytest.mark.parametrize(
    "name", ["main_member", "looks_like_export_document", "open_main_document"]
)
def test_remaining_public_required_arguments_contract(name: str) -> None:
    functions: dict[str, Callable[..., Any]] = {
        "main_member": main_member,
        "looks_like_export_document": looks_like_export_document,
        "open_main_document": open_main_document,
    }
    invoke: Any = functions[name]
    with pytest.raises(TypeError):
        invoke()


@pytest.mark.parametrize("name", ["MAIN_DOCUMENT", "CDA_SUFFIX"])
def test_reader_constant_declared_types_contract(name: str) -> None:
    from typing import Final, get_type_hints

    assert get_type_hints(reader)[name] == Final[str]


def native_parse_error(data: bytes) -> tuple[int, int, str]:
    from xml.etree.ElementTree import ParseError

    try:
        fromstring(data)
    except ParseError as error:
        return (*error.position, str(error))
    raise ValueError("malformed XML fixture parsed successfully")


def observed_reader(data: bytes) -> list[ExportItem] | WellnessFormatError:
    try:
        return read_items(data)
    except WellnessFormatError as error:
        return error


@pytest.mark.parametrize(
    "data",
    [
        b'<HealthData>\n  <ExportDate value="top"/>\n',
        b"<HealthData>\n  </Other>",
        b"<HealthData/>\n   <HealthData/>",
        b'<HealthData>\n    <Other value="&missing;"/>\n</HealthData>',
    ],
    ids=["unclosed", "wrong-closing", "multiple-roots", "undefined-entity"],
)
def test_complete_native_parse_error_wrapper(data: bytes) -> None:
    line, column, message = native_parse_error(data)
    observed = observed_reader(data)
    assert (type(observed), str(observed)) == (
        WellnessFormatError,
        f"the export could not be read at line {line}, column {column}: {message}",
    )


@pytest.mark.parametrize("depth", [2, 3], ids=["depth2", "depth3"])
@pytest.mark.parametrize("position", ["before", "after"])
def test_nested_export_date_ignored(depth: int, position: str) -> None:
    nested = (
        "<Correlation>" * (depth - 1)
        + '<ExportDate value="nested"/>'
        + "</Correlation>" * (depth - 1)
    )
    top = '<ExportDate value="top"/>'
    elements = nested + top if position == "before" else top + nested
    data = ("<HealthData>" + elements + "</HealthData>").encode()
    assert observed_reader(data) == [ExportDate("top"), Corrections(0, 0, 0)]


def test_zip_progress(tmp_path: Path) -> None:
    data = export_document(
        records=bulk_records(6000),
        include_doctype=False,
        include_me=False,
        include_scaffold=False,
    )
    candidate = tmp_path / "export.zip"
    candidate.write_bytes(zip_members({ENGLISH_MAIN: data}))
    with zipfile.ZipFile(candidate) as archive:
        info = archive.getinfo(ENGLISH_MAIN)
    calls = []
    with open_main_document(candidate) as document:
        genuine_member = isinstance(document.stream, zipfile.ZipExtFile)
        size = document.size
        items = list(
            iter_items(
                document, progress=lambda read, total: calls.append((read, total))
            )
        )
    percents = [read * 100 // total for read, total in calls]
    assert (
        genuine_member,
        info.compress_type,
        info.compress_size != info.file_size == len(data),
        len(data) > CHUNK_BYTES,
        size,
        items,
        1 < len(calls) <= 101,
        all(total == len(data) for _, total in calls),
        all(a < b for a, b in zip(percents, percents[1:], strict=False)),
        calls[-1] if calls else None,
    ) == (
        True,
        zipfile.ZIP_DEFLATED,
        True,
        True,
        len(data),
        [ExportDate(EXPORT_DATE), Corrections(0, 0, 0)],
        True,
        True,
        True,
        (len(data), len(data)),
    )


def test_depth3_record() -> None:
    nested = (
        "<Correlation><Correlation>"
        + record_xml(AppleType.BODY_MASS, value="private")
        + "</Correlation></Correlation>"
    )
    data = export_document(
        records=[],
        include_doctype=False,
        include_me=False,
        include_scaffold=False,
        extra_elements=[nested],
    )
    assert read_items(data) == [ExportDate(EXPORT_DATE), Corrections(0, 0, 0)]


@pytest.mark.parametrize("variant", ["bare", "zip"])
@pytest.mark.parametrize("repair", ["doctype", "control", "duplicate"])
def test_original_progress_after_repair(
    tmp_path: Path, variant: str, repair: str
) -> None:
    data = export_document(
        records=[record_xml(AppleType.STEP_COUNT)],
        include_me=False,
        include_doctype=repair == "doctype",
        malformed_doctype=repair == "doctype",
        control_character=repair == "control",
        include_scaffold=repair == "duplicate",
        duplicate_start_date=repair == "duplicate",
    )
    candidate = tmp_path / "repaired-export"
    candidate.write_bytes(
        data if variant == "bare" else zip_members({ENGLISH_MAIN: data})
    )
    calls: list[tuple[int, int]] = []
    with open_main_document(candidate) as document:
        actual_zip = isinstance(document.stream, zipfile.ZipExtFile)
        items = list(
            iter_items(
                document, progress=lambda read, total: calls.append((read, total))
            )
        )
    expected_corrections = {
        "doctype": Corrections(1, 0, 0),
        "control": Corrections(0, 1, 0),
        "duplicate": Corrections(0, 0, 1),
    }
    assert (
        actual_zip,
        items[-1],
        bool(calls),
        all(total == len(data) for _, total in calls),
        calls[-1] if calls else None,
    ) == (
        variant == "zip",
        expected_corrections[repair],
        True,
        True,
        (len(data), len(data)),
    )


@pytest.mark.parametrize("record_type", list(AppleType))
def test_device_normalized_for_each_read_type(record_type: AppleType) -> None:
    data = export_document(
        records=[record_xml(record_type)],
        include_doctype=False,
        include_me=False,
        include_scaffold=False,
    )
    records = [item for item in read_items(data) if isinstance(item, RawRecord)]
    assert [(record.type, record.device) for record in records] == [
        (
            record_type,
            "name:Example Apple Watch, manufacturer:Apple Inc., model:Watch",
        )
    ]


CONTRACT_TYPES = (
    "HKQuantityTypeIdentifierRestingHeartRate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
    "HKQuantityTypeIdentifierRespiratoryRate",
    "HKQuantityTypeIdentifierOxygenSaturation",
    "HKQuantityTypeIdentifierVO2Max",
    "HKQuantityTypeIdentifierStepCount",
    "HKQuantityTypeIdentifierBodyMass",
    "HKCategoryTypeIdentifierSleepAnalysis",
)
CONTRACT_FIELDS = (
    ("sourceName", "source_name"),
    ("sourceVersion", "source_version"),
    ("device", "device"),
    ("unit", "unit"),
    ("creationDate", "creation_date"),
    ("startDate", "start_date"),
    ("endDate", "end_date"),
    ("value", "value"),
)


@pytest.mark.parametrize("type_id", CONTRACT_TYPES)
def test_raw_projection_contract(type_id: str) -> None:
    populated: dict[str, str | None] = {
        "source_name": "  source-name e\u0301 文  ",
        "source_version": "version:09.37-beta",
        "device": "<<HKDevice: 0xaB19>, name:Contract Device, model:Distinct-42>",
        "unit": "unit:mixed/秒",
        "creation_date": "creation:2031-07-09 12:31:43 +0130",
        "start_date": "start:2030-06-08 11:29:41 -0230",
        "end_date": "end:2032-08-10 13:37:47 +0345",
        "value": "value:007.2300",
    }
    expected_populated = {
        **populated,
        "device": "name:Contract Device, model:Distinct-42",
    }
    metadata = (
        (" z-key ", "  first e\u0301 文  "),
        ("a-key", "0"),
        (" z-key ", "unequal-duplicate"),
        ("", "empty-key"),
        ("empty-value", ""),
        ("", ""),
        ("missing-value", ""),
        ("", "missing-key"),
    )
    children = (
        '<MetadataEntry/><MetadataEntry key="missing-value"/>'
        '<MetadataEntry value="missing-key"/>'
        '<Other key="intruder" value="unrelated"/>'
        '<Other><MetadataEntry key="nested" value="decoy"/></Other>'
        "<HeartRateVariabilityMetadataList><InstantaneousBeatsPerMinute "
        'bpm="987" time="private"/></HeartRateVariabilityMetadataList>'
    )
    inputs = [
        record_xml(
            type_id,
            attributes={xml: populated[slot] for xml, slot in CONTRACT_FIELDS},
            metadata=metadata[:5],
            children=children,
        )
    ]
    expected_rows: list[tuple[dict[str, str | None], tuple[tuple[str, str], ...]]] = [
        (expected_populated, metadata)
    ]
    for _xml, slot in CONTRACT_FIELDS:
        for special in (None, "", "0"):
            values = {**populated, "device": "ordinary:device > payload", slot: special}
            inputs.append(
                record_xml(
                    type_id,
                    attributes={name: values[field] for name, field in CONTRACT_FIELDS},
                )
            )
            expected_rows.append((values, ()))
    expected: list[ExportItem] = [ExportDate("contract-export:2040-03-05")]
    for values, pairs in expected_rows:
        expected.append(
            RawRecord(
                type=type_id,
                source_name=values["source_name"],
                source_version=values["source_version"],
                device=values["device"],
                unit=values["unit"],
                creation_date=values["creation_date"],
                start_date=values["start_date"],
                end_date=values["end_date"],
                value=values["value"],
                metadata=pairs,
            )
        )
    expected.append(Corrections(0, 0, 0))
    data = export_document(
        records=inputs,
        export_date="contract-export:2040-03-05",
        include_doctype=False,
        include_me=False,
        include_scaffold=False,
    )
    assert read_items(data) == expected


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"<!DOCTYPE HealthData>", True),
        (b"<!DOCTYPE\tHealthData>", True),
        (b"<!DOCTYPE\nHealthData>", True),
        (b"<!DOCTYPE\rHealthData>", True),
        (b"<!DOCTYPE HealthData ", True),
        (b"<!DOCTYPE HealthData\t", True),
        (b"<!DOCTYPE HealthData\n", True),
        (b"<!DOCTYPE HealthData\r", True),
        (b"<!DOCTYPE HealthData[", True),
        (b"<!DOCTYPE healthdata>", False),
        (b"<!doctype HealthData>", False),
        (b"<!DOCTYPEHealthData>", False),
        (b"<!DOCTYPE HealthData", False),
    ],
    ids=[
        "separator-space",
        "separator-tab",
        "separator-lf",
        "separator-cr",
        "boundary-space",
        "boundary-tab",
        "boundary-lf",
        "boundary-cr",
        "boundary-subset",
        "case-name",
        "case-marker",
        "missing-separator",
        "unfinished-name",
    ],
)
def test_doctype_recognition_contract(head: bytes, expected: bool) -> None:
    assert looks_like_export_document(head) is expected
