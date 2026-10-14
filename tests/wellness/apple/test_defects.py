"""Byte-stream contracts for synthetic Apple Health defects."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from contextlib import suppress
from pathlib import Path

import pytest

from fitdocs.wellness.formats.apple import defects
from fitdocs.wellness.formats.apple.defects import DefectFilter
from fitdocs.wellness.formats.apple.records import Corrections
from fitdocs.wellness.spec import WellnessFormatError
from tests.wellness.apple.builders import export_document, record_xml


class CountingStream(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.requests: list[int | None] = []
        self.eof_read = False

    def read(self, size: int | None = -1) -> bytes:
        self.requests.append(size)
        result = super().read(size)
        self.eof_read = not result
        return result


class CountingFile(io.BufferedRandom):
    def __init__(self, path: Path) -> None:
        self.requests: list[int | None] = []
        self.seeks: list[tuple[int, int]] = []
        super().__init__(io.FileIO(path, "r+"))

    def read(self, size: int | None = -1) -> bytes:
        self.requests.append(size)
        return super().read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        self.seeks.append((offset, whence))
        return super().seek(offset, whence)


def drain(stream: DefectFilter, budget: int) -> bytes:
    chunks: list[bytes] = []
    for _ in range(budget):
        chunk = stream.read(1)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
    pytest.fail("filter did not finish within finite read budget")


def filtered(document: bytes, *, chunk_bytes: int = 7) -> tuple[bytes, Corrections]:
    stream = DefectFilter(io.BytesIO(document), chunk_bytes=chunk_bytes)
    return drain(stream, len(document) + 3), stream.corrections


def accepted_output(document: bytes) -> bytes | str:
    try:
        return filtered(document)[0]
    except WellnessFormatError as error:
        return str(error)


def minimal(children: str = "") -> bytes:
    return export_document(
        [],
        include_doctype=False,
        include_me=False,
        include_scaffold=False,
        export_date=None,
        extra_elements=(children,),
    )


def three_defects() -> bytes:
    statistics = (
        '<WorkoutStatistics startDate="first-date"\n startDate="last-date"'
        ' sum="17"\r\n sum="99" description="a>b"/>'
    )
    return export_document(
        [
            record_xml(
                "HKQuantityTypeIdentifierRestingHeartRate", value="5\x00\x0b\x1f3"
            )
        ],
        malformed_doctype=True,
        include_scaffold=False,
        extra_elements=(statistics,),
    )


@pytest.mark.parametrize(
    "name,expected",
    [
        ("CONTROL_BYTES", bytes((*range(9), 11, 12, *range(14, 32)))),
        ("PROLOG_LIMIT", 1_048_576),
        ("MAX_TAG_BYTES", 65_536),
        ("CHUNK_BYTES", 1_048_576),
    ],
)
def test_constants(name: str, expected: bytes | int) -> None:
    assert getattr(defects, name) == expected


@pytest.mark.parametrize("fault", ["doctype", "controls", "duplicates", "combined"])
def test_exact_repairs_and_parse(fault: str) -> None:
    if fault == "doctype":
        document = export_document([], malformed_doctype=True, include_scaffold=False)
        start, end = document.index(b"<!DOCTYPE"), document.index(b"<HealthData ")
        expected = (
            document[:start]
            + bytes(c for c in document[start:end] if c in (10, 13))
            + document[end:]
        )
    elif fault == "controls":
        document = minimal('<Record sourceName="Example\x00\x0b\x1f Watch"/>')
        expected = document.translate(None, b"\x00\x0b\x1f")
    elif fault == "duplicates":
        document = minimal(
            '<WorkoutStatistics startDate="first" startDate="last" sum="17" sum="99"/>'
        )
        expected = document.replace(b' startDate="last"', b"").replace(
            b' sum="99"', b""
        )
    else:
        document = three_defects()
        start, end = document.index(b"<!DOCTYPE"), document.index(b"<HealthData ")
        expected = (
            document[:start]
            + bytes(c for c in document[start:end] if c in (10, 13))
            + document[end:]
        )
        expected = (
            expected.translate(None, b"\x00\x0b\x1f")
            .replace(b'\n startDate="last-date"', b"\n")
            .replace(b'\r\n sum="99"', b"\r\n")
        )
    output, _ = filtered(document)
    assert output == expected
    list(ET.iterparse(io.BytesIO(output)))


@pytest.mark.parametrize(
    "field,expected",
    [
        ("doctype_removed", 1),
        ("control_characters_removed", 3),
        ("duplicate_attributes_removed", 2),
    ],
)
def test_exact_correction_counts(field: str, expected: int) -> None:
    _, corrections = filtered(three_defects())
    assert getattr(corrections, field) == expected


def test_initial_corrections() -> None:
    assert DefectFilter(io.BytesIO(three_defects())).corrections == Corrections(0, 0, 0)


def test_pristine_byte_identity() -> None:
    document = export_document(include_doctype=False)
    output, _ = filtered(document)
    assert output == document


def test_pristine_zero_corrections() -> None:
    _, corrections = filtered(export_document(include_doctype=False))
    assert corrections == Corrections(0, 0, 0)


@pytest.mark.parametrize("control", [*range(9), 11, 12, *range(14, 32)])
def test_every_forbidden_control_anywhere(control: int) -> None:
    document = (
        bytes((control,))
        + minimal('<Record value="é' + chr(control) + '漢"/>')
        + bytes((control,))
    )
    output, corrections = filtered(document)
    assert (output, corrections.control_characters_removed) == (
        document.replace(bytes((control,)), b""),
        3,
    )


@pytest.mark.parametrize("kept", [b"\t", b"\n", b"\r"])
def test_xml_whitespace_kept(kept: bytes) -> None:
    document = minimal().replace(b"<HealthData ", b"<HealthData" + kept) + kept
    output, _ = filtered(document)
    assert output == document


def test_doctype_span_keeps_crlf_and_real_root_delimiter() -> None:
    document = (
        b'<?xml version="1.0"?>\r\n<!DOCTYPE broken\n'
        b"<HealthDatabase/>\r\n<!BAD>\n<HealthData/>"
    )
    output, _ = filtered(document)
    assert output == b'<?xml version="1.0"?>\r\n\n\r\n\n<HealthData/>'
    ET.fromstring(output)


@pytest.mark.parametrize("delimiter", [b" ", b"\t", b"\r", b"\n", b">", b"/"])
def test_root_delimiters(delimiter: bytes) -> None:
    document = b"<!DOCTYPE broken\n<HealthData" + delimiter + b"tail"
    assert accepted_output(document) == b"\n<HealthData" + delimiter + b"tail"


def test_doctype_after_root_left_alone() -> None:
    document = minimal("<!DOCTYPE odd>")
    output, corrections = filtered(document, chunk_bytes=1000)
    assert (output, corrections.doctype_removed) == (document, 0)


@pytest.mark.parametrize("chunk_bytes", [1, 7, 18, 19, 37, 1000])
def test_split_names_and_quoted_gt_keep_first(chunk_bytes: int) -> None:
    document = minimal(
        "<WorkoutStatistics a=\"first>a\"\n a=\"last\" b='first>b'\r\n b='other'/>"
    )
    output, _ = filtered(document, chunk_bytes=chunk_bytes)
    assert output == document.replace(b'\n a="last"', b"\n").replace(
        b"\r\n b='other'", b"\r\n"
    )


def test_statistics_prefix_decoy_and_record_duplicates_left_alone() -> None:
    document = minimal(
        '<WorkoutStatisticsExtra a="1" a="2"/><Record value="3" value="4"/>'
    )
    output, corrections = filtered(document)
    assert (output, corrections.duplicate_attributes_removed) == (document, 0)


def test_duplicate_names_case_and_tag_scope() -> None:
    document = minimal(
        '<WorkoutStatistics a="1" A="2" a="3"/><WorkoutStatistics a="4" a="5"/>'
    )
    output, _ = filtered(document)
    assert output == document.replace(b' a="3"', b"").replace(b' a="5"', b"")


def test_line_count() -> None:
    document = three_defects()
    output, _ = filtered(document)
    assert output.count(b"\n") == document.count(b"\n")


def test_parser_error_line_matches_original() -> None:
    document = three_defects().replace(b"</HealthData>", b"<Broken></HealthData>")
    output, _ = filtered(document)
    try:
        ET.fromstring(output)
    except ET.ParseError as error:
        position = error.position[0]
    else:
        position = -1
    assert position == document[: document.index(b"</HealthData>")].count(b"\n") + 1


@pytest.mark.parametrize(
    "document",
    [b"<Other/>" + b"x" * 50, b"<HealthDatabase/>" + b"x" * 50, b"<HealthData"],
)
def test_missing_root_limit(document: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(defects, "PROLOG_LIMIT", 32)
    with pytest.raises(WellnessFormatError, match="no HealthData element.*32 bytes"):
        filtered(document)


def test_root_at_limit_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(defects, "PROLOG_LIMIT", 32)
    document = b" " * 20 + b"<HealthData/>"
    assert accepted_output(document) == document


@pytest.mark.parametrize("ending", [b"/>", b""])
def test_tag_limit(ending: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(defects, "MAX_TAG_BYTES", 64)
    with pytest.raises(WellnessFormatError, match="WorkoutStatistics.*64 bytes"):
        filtered(b'<HealthData><WorkoutStatistics a="' + b"x" * 64 + b'"' + ending)


def test_tag_at_limit_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(defects, "MAX_TAG_BYTES", 64)
    tag = b'<WorkoutStatistics a="' + b"x" * 39 + b'"/>'
    assert accepted_output(b"<HealthData>" + tag) == b"<HealthData>" + tag


def test_no_premature_eof_on_deleted_chunks() -> None:
    document = (
        b"<!DOCTYPE" + b"x" * 28 + b"\n<HealthData>" + b"\x0b" * 35 + b"</HealthData>"
    )
    upstream = CountingStream(document)
    stream = DefectFilter(upstream, chunk_bytes=7)
    observations = []
    for _ in range(len(document) + 3):
        part = stream.read(1)
        observations.append((part, upstream.eof_read))
        if not part:
            break
    assert (
        b"".join(part for part, _ in observations),
        observations[-1],
        all(part or ended for part, ended in observations),
    ) == (b"\n<HealthData></HealthData>", (b"", True), True)


@pytest.mark.parametrize("configured", [False, True])
def test_default_and_oversized_chunks_bounded(configured: bool) -> None:
    upstream = CountingStream(
        b"<HealthData>" + b"x" * (defects.CHUNK_BYTES + 10) + b"</HealthData>"
    )
    stream = (
        DefectFilter(upstream, chunk_bytes=defects.CHUNK_BYTES * 2)
        if configured
        else DefectFilter(upstream)
    )
    drain(stream, 10)
    assert bool(upstream.requests) and all(
        request is not None and 0 < request <= 1_048_576
        for request in upstream.requests
    )


def test_configured_chunks_and_readonly_original(tmp_path: Path) -> None:
    document = three_defects()
    original = tmp_path / "synthetic.xml"
    original.write_bytes(document)
    before = original.stat().st_mtime_ns
    with CountingFile(original) as upstream:
        stream = DefectFilter(upstream, chunk_bytes=7)
        drain(stream, len(document) + 3)
        if not upstream.closed:
            upstream.flush()
        assert (
            set(upstream.requests),
            upstream.seeks,
            original.read_bytes(),
            original.stat().st_mtime_ns,
            upstream.closed,
        ) == ({7}, [], document, before, False)


def test_partial_target_at_eof_preserved() -> None:
    document = b"<HealthData><WorkoutStatis"
    output, _ = filtered(document)
    assert output == document


def test_unclosed_target_at_eof_preserved() -> None:
    document = b'<HealthData><WorkoutStatistics a="x>y"'
    output, _ = filtered(document)
    assert output == document


def test_repeated_eof_is_empty() -> None:
    stream = DefectFilter(io.BytesIO(minimal()))
    drain(stream, 10)
    assert (stream.read(), stream.read(0), stream.read(999)) == (b"", b"", b"")


@pytest.mark.parametrize("size", [-1, 0, 1, 10_000_000])
def test_read_accepts_sizes(size: int) -> None:
    stream = DefectFilter(io.BytesIO(b"<!DOCTYPE bad\n<HealthData/>"), chunk_bytes=7)
    assert stream.read(size) == b"\n<HealthData/>"


def test_default_missing_root_error() -> None:
    with pytest.raises(
        WellnessFormatError,
        match="^not an Apple Health export: no HealthData element in its first 1 MiB$",
    ):
        filtered(b"<Other/>")


def test_prolog_stops_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(defects, "PROLOG_LIMIT", 32)
    upstream = CountingStream(b"x" * 100 + b"<HealthData/>")
    with suppress(WellnessFormatError):
        drain(DefectFilter(upstream, chunk_bytes=7), 20)
    assert upstream.tell() == 32


def test_controls_in_removed_doctype_are_counted() -> None:
    output, corrections = filtered(b"<!DOCTYPE bad\x00\x0b\x1f\n<HealthData/>")
    assert (output, corrections) == (b"\n<HealthData/>", Corrections(1, 3, 0))


def test_control_bytes_consume_raw_prolog_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(defects, "PROLOG_LIMIT", 32)
    upstream = CountingStream(b"\x00" * 25 + b"<HealthData/>")
    error = ""
    try:
        drain(DefectFilter(upstream, chunk_bytes=7), 20)
    except WellnessFormatError as failure:
        error = str(failure)
    assert (upstream.tell(), error) == (
        32,
        "not an Apple Health export: no HealthData element in its first 32 bytes",
    )


@pytest.mark.parametrize("quote", [chr(34), chr(39)], ids=["double", "single"])
@pytest.mark.parametrize("position", ["tag", "duplicate", "before", "after"])
@pytest.mark.parametrize(
    "whitespace", [" ", "\t", "\n", "\r"], ids=["space", "tab", "lf", "cr"]
)
def test_attribute_whitespace_contract(
    position: str, whitespace: str, quote: str
) -> None:
    tag_space = whitespace if position == "tag" else " "
    duplicate_space = whitespace if position == "duplicate" else " "
    before = whitespace if position == "before" else ""
    after = whitespace if position == "after" else ""
    duplicate = duplicate_space + "a" + before + "=" + after + quote + "last>99" + quote
    document = minimal(
        "<WorkoutStatistics"
        + tag_space
        + "a="
        + quote
        + "first>17"
        + quote
        + duplicate
        + "/>"
    )
    expected = document.replace(
        duplicate.encode(),
        bytes(byte for byte in duplicate.encode() if byte in (10, 13)),
    )
    output, corrections = filtered(document)
    try:
        statistics = ET.fromstring(output).find("WorkoutStatistics")
        parsed_first = statistics.attrib.get("a") if statistics is not None else None
    except ET.ParseError:
        parsed_first = None
    assert (output, corrections.duplicate_attributes_removed, parsed_first) == (
        expected,
        1,
        "first>17",
    )
