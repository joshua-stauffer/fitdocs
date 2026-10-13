"""Declaration contracts and shared synthetic format helpers."""

from __future__ import annotations

import io
import os
from dataclasses import MISSING, FrozenInstanceError, fields
from datetime import date
from pathlib import Path

import pytest

from fitdocs.wellness import spec
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    EXTRACT_SOURCE,
    ORIGINAL_FORMAT,
    ORIGINAL_SOURCE,
    assert_untouched,
    build_extract,
    tree_snapshot,
)


@pytest.mark.parametrize(
    "enum, expected",
    [
        (spec.SourceKind, {"DEVICE": "device", "HUB": "hub", "RELAY": "relay"}),
        (spec.ArchiveForm, {"ORIGINAL": "original", "EXTRACT": "extract"}),
        (spec.Supersession, {"NONE": "none", "LATEST_ENTRY": "latest-entry"}),
    ],
)
def test_enums(
    enum: type[spec.SourceKind] | type[spec.ArchiveForm] | type[spec.Supersession],
    expected: dict[str, str],
) -> None:
    assert {key: value.value for key, value in enum.__members__.items()} == expected
    assert all(isinstance(value, str) for value in enum)


@pytest.mark.parametrize(
    "cls, expected",
    [
        (spec.SourceSpec, {"id": "str", "display_name": "str", "kind": "SourceKind"}),
        (
            spec.ExtractContext,
            {
                "expected_sha256": "str",
                "size": "int",
                "progress": "Callable[[int, int], None] | None",
            },
        ),
        (
            spec.FormatSpec,
            {
                "id": "str",
                "display_name": "str",
                "source": "SourceSpec",
                "suffixes": "frozenset[str]",
                "archive_form": "ArchiveForm",
                "archived_suffix": "str",
                "rules_version": "int",
                "metrics": "frozenset[Metric]",
                "recognize": "Callable[[CandidateProbe], bool]",
                "parse": "Callable[[BinaryIO], Iterator[DaySnapshot]]",
                "supersession": "Supersession",
                "extract": "Callable[[Path, BinaryIO, ExtractContext], None] | None",
                "entry_order": "Callable[[BinaryIO], str] | None",
            },
        ),
        (
            spec.ParsedEntry,
            {
                "entry_ref": "str",
                "format_id": "str",
                "source_id": "str",
                "supersession": "Supersession",
                "snapshots": "tuple[DaySnapshot, ...]",
            },
        ),
    ],
)
def test_fields(
    cls: type[
        spec.SourceSpec | spec.FormatSpec | spec.ExtractContext | spec.ParsedEntry
    ],
    expected: dict[str, str],
) -> None:
    assert {field.name: field.type for field in fields(cls)} == expected
    defaults = {
        field.name: field.default
        for field in fields(cls)
        if field.default is not MISSING
    }
    assert defaults == (
        {"supersession": spec.Supersession.NONE, "extract": None, "entry_order": None}
        if cls is spec.FormatSpec
        else {}
    )


@pytest.mark.parametrize(
    "instance, field",
    [
        (ORIGINAL_SOURCE, "id"),
        (ORIGINAL_FORMAT, "rules_version"),
        (spec.ExtractContext("a" * 64, 12, None), "size"),
        (
            spec.ParsedEntry("ref", "format", "source", spec.Supersession.NONE, ()),
            "entry_ref",
        ),
    ],
)
def test_frozen(instance: object, field: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field, "changed")


def test_format_error() -> None:
    assert spec.WellnessFormatError.__bases__ == (Exception,)
    with pytest.raises(Exception, match="broken format"):
        raise spec.WellnessFormatError("broken format")


def test_original_helper(tmp_path: Path) -> None:
    path = tmp_path / "unknown.JSON"
    path.write_bytes(b'{"test_original":true,"day":"2024-02-03","value":61.5}')
    assert ORIGINAL_FORMAT.source is ORIGINAL_SOURCE
    assert ORIGINAL_SOURCE != EXTRACT_SOURCE
    assert ORIGINAL_FORMAT.archive_form is spec.ArchiveForm.ORIGINAL
    assert ORIGINAL_FORMAT.recognize(CandidateProbe.open(path)) is True
    with path.open("rb") as stream:
        assert tuple(ORIGINAL_FORMAT.parse(stream)) == (
            DaySnapshot(
                date(2024, 2, 3),
                frozenset({Metric.RESTING_HR_BPM}),
                {Metric.RESTING_HR_BPM: 61.5},
                {},
                None,
                0,
            ),
        )
    path.write_bytes(b'{"test_original":false}')
    assert ORIGINAL_FORMAT.recognize(CandidateProbe.open(path)) is False
    path.write_bytes(b"[]")
    assert ORIGINAL_FORMAT.recognize(CandidateProbe.open(path)) is False


@pytest.mark.parametrize(
    "content",
    [
        b"broken",
        b"[]",
        b"{}",
        b'{"day":"invalid","value":4}',
        b'{"day":"2024-02-03","value":"bad"}',
        b"\xff",
    ],
)
def test_original_invalid(content: bytes) -> None:
    with pytest.raises(spec.WellnessFormatError):
        tuple(ORIGINAL_FORMAT.parse(io.BytesIO(content)))


def test_extract_helper(tmp_path: Path) -> None:
    content = build_extract("revision-z")
    path = tmp_path / "sample.test-extract"
    path.write_bytes(content)
    assert EXTRACT_FORMAT.source is EXTRACT_SOURCE
    assert EXTRACT_FORMAT.archive_form is spec.ArchiveForm.EXTRACT
    assert EXTRACT_FORMAT.supersession is spec.Supersession.LATEST_ENTRY
    assert EXTRACT_FORMAT.recognize(CandidateProbe.open(path)) is True
    assert EXTRACT_FORMAT.entry_order is not None
    stream = io.BytesIO(content)
    assert EXTRACT_FORMAT.entry_order(stream) == "revision-z"
    assert stream.tell() == content.index(b"\n") + 1
    assert tuple(EXTRACT_FORMAT.parse(io.BytesIO(content))) == (
        DaySnapshot(
            date(2024, 2, 3),
            frozenset({Metric.WEIGHT_KG}),
            {Metric.WEIGHT_KG: 73.25},
            {},
            None,
            0,
        ),
    )
    output = io.BytesIO()
    progress: list[tuple[int, int]] = []
    assert EXTRACT_FORMAT.extract is not None
    EXTRACT_FORMAT.extract(
        path,
        output,
        spec.ExtractContext(
            "a" * 64, len(content), lambda read, total: progress.append((read, total))
        ),
    )
    assert output.getvalue() == content
    assert progress == [(len(content), len(content))]
    output = io.BytesIO()
    EXTRACT_FORMAT.extract(
        path, output, spec.ExtractContext("a" * 64, len(content), None)
    )
    assert output.getvalue() == content


@pytest.mark.parametrize(
    "header",
    [
        b"broken",
        b"[]",
        b'{"test_extract":false,"order":"x"}',
        b'{"test_extract":true,"order":4}',
        b"\xff",
    ],
)
def test_extract_bad_header(header: bytes, tmp_path: Path) -> None:
    content = header + b"\nbody"
    path = tmp_path / "bad.test-extract"
    path.write_bytes(content)
    # Recognition checks the format marker; order validation belongs to parsing.
    assert EXTRACT_FORMAT.recognize(CandidateProbe.open(path)) is (
        header == b'{"test_extract":true,"order":4}'
    )
    assert EXTRACT_FORMAT.entry_order is not None
    with pytest.raises(spec.WellnessFormatError, match="header"):
        EXTRACT_FORMAT.entry_order(io.BytesIO(content))
    with pytest.raises(spec.WellnessFormatError, match="header"):
        tuple(EXTRACT_FORMAT.parse(io.BytesIO(content)))


def test_tree_helpers(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    first = tmp_path / "one"
    second = nested / "two"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta")
    os.utime(first, ns=(123000000000, 123000000000))
    os.utime(second, ns=(456000000000, 456000000000))
    before = tree_snapshot(tmp_path)
    assert before == {
        "one": (b"alpha", 123000000000),
        "nested/two": (b"beta", 456000000000),
    }
    assert_untouched(before, tree_snapshot(tmp_path))
    for after in (
        {"one": (b"different", 123000000000), "nested/two": before["nested/two"]},
        {"one": (b"alpha", 124000000000), "nested/two": before["nested/two"]},
        {"one": before["one"]},
        {**before, "new": (b"new", 123000000000)},
    ):
        assert after != before
        with pytest.raises(AssertionError):
            assert_untouched(before, after)
    assert tree_snapshot(tmp_path / "absent") == {}


def test_extract_ordinals() -> None:
    content = build_extract("chosen") + b'{"day":"2024-02-04","value":81.5}\n'
    assert tuple(EXTRACT_FORMAT.parse(io.BytesIO(content))) == (
        DaySnapshot(
            date(2024, 2, 3),
            frozenset({Metric.WEIGHT_KG}),
            {Metric.WEIGHT_KG: 73.25},
            {},
            None,
            0,
        ),
        DaySnapshot(
            date(2024, 2, 4),
            frozenset({Metric.WEIGHT_KG}),
            {Metric.WEIGHT_KG: 81.5},
            {},
            None,
            1,
        ),
    )


def test_corrupt_extract_order_is_header_only() -> None:
    corrupt = build_extract("revision-a", corrupt_body=True)
    assert EXTRACT_FORMAT.entry_order is not None
    assert EXTRACT_FORMAT.entry_order(io.BytesIO(corrupt)) == "revision-a"
    with pytest.raises(spec.WellnessFormatError, match="body"):
        tuple(EXTRACT_FORMAT.parse(io.BytesIO(corrupt)))
