"""Tests for the golden harness and the shared data builders (Req 18.3)."""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.schema import ChartRequest
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
)
from tests.render.charts.kit.goldens import (
    assert_golden,
    golden_path,
    write_golden,
)

SVG = '<svg width="10">café &amp; –</svg>\n'


def _written(tmp_path: Path, text: str = SVG) -> Path:
    path = tmp_path / "line" / "typical.svg"
    write_golden(path, text)
    return path


def test_golden_path_layout() -> None:
    here = Path(__file__).parent
    path = golden_path("line", "typical", "svg")
    assert path == here / "golden" / "line" / "typical.svg"
    assert golden_path("stat", "no_rows", "md") == (
        here / "golden" / "stat" / "no_rows.md"
    )


def test_matching_text_passes(tmp_path: Path) -> None:
    path = _written(tmp_path)
    assert path.read_bytes() == SVG.encode("utf-8")
    assert_golden(path, SVG)


def test_one_flipped_byte_fails(tmp_path: Path) -> None:
    path = _written(tmp_path)
    raw = bytearray(path.read_bytes())
    index = raw.index(b'"10"') + 1
    assert raw[index] == ord("1")
    raw[index] = ord("2")
    tampered = bytes(raw)
    assert len(tampered) == len(SVG.encode("utf-8"))
    path.write_bytes(tampered)
    with pytest.raises(AssertionError, match=r"golden differs.*byte 12\)$"):
        assert_golden(path, SVG)


def test_flipped_multibyte_byte_fails(tmp_path: Path) -> None:
    path = _written(tmp_path)
    raw = bytearray(path.read_bytes())
    index = raw.index("é".encode()) + 1
    raw[index] ^= 0x01
    path.write_bytes(bytes(raw))
    with pytest.raises(AssertionError, match="golden differs"):
        assert_golden(path, SVG)


def test_trailing_newline_difference_fails_both_ways(tmp_path: Path) -> None:
    path = _written(tmp_path, "<svg/>\n")
    with pytest.raises(AssertionError, match="golden differs"):
        assert_golden(path, "<svg/>")
    bare = _written(tmp_path / "bare", "<svg/>")
    with pytest.raises(AssertionError, match="golden differs"):
        assert_golden(bare, "<svg/>\n")


def test_leading_whitespace_difference_fails(tmp_path: Path) -> None:
    path = _written(tmp_path, "<svg/>")
    with pytest.raises(AssertionError, match="golden differs"):
        assert_golden(path, " <svg/>")


def test_line_ending_difference_fails(tmp_path: Path) -> None:
    path = tmp_path / "crlf.svg"
    path.write_bytes(b"a\r\nb")
    with pytest.raises(AssertionError, match="golden differs"):
        assert_golden(path, "a\nb")
    assert_golden(path, "a\r\nb")


def test_truncation_reports_lengths(tmp_path: Path) -> None:
    path = _written(tmp_path, "abcdef")
    with pytest.raises(AssertionError, match=r"rendered 3 bytes, golden 6 bytes"):
        assert_golden(path, "abc")


def test_missing_golden_fails_and_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "line" / "absent.svg"
    assert not path.exists()
    with pytest.raises(AssertionError, match="golden missing"):
        assert_golden(path, SVG)
    assert not path.exists()
    assert not path.parent.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_golden_writes_exact_bytes_and_parents(tmp_path: Path) -> None:
    text = "a\r\nb\n\n  "
    path = tmp_path / "x" / "y" / "case.md"
    write_golden(path, text)
    assert path.read_bytes() == b"a\r\nb\n\n  "
    write_golden(path, "z")
    assert path.read_bytes() == b"z"


# --- builders ---------------------------------------------------------------


def test_case_is_frozen_with_ordered_fields() -> None:
    assert [f.name for f in dataclasses.fields(Case)] == [
        "name",
        "request",
        "data",
    ]
    request = chart_request("line")
    data = chart_data([column("a")], [])
    case = Case("typical", request, data)
    assert (case.name, case.request, case.data) == ("typical", request, data)
    with pytest.raises(dataclasses.FrozenInstanceError):
        case.name = "other"  # type: ignore[misc]


def test_column_defaults_and_fields() -> None:
    assert column("n") == Column("n", ValueKind.NUMBER, None, None)
    built = column("d", ValueKind.DATE, unit="u", label="Day")
    assert built == Column("d", ValueKind.DATE, "u", "Day")
    assert (built.unit, built.label) == ("u", "Day")


def test_chart_data_keeps_order_none_and_zero() -> None:
    columns = [
        column("z", ValueKind.CATEGORY),
        column("a"),
        column("d", ValueKind.DATE),
    ]
    rows: list[list[Value]] = [
        ["q", 3, date(2026, 1, 2)],
        [None, 0, None],
        ["b", None, date(2025, 5, 6)],
    ]
    built = chart_data(columns, rows)
    assert isinstance(built, ChartData)
    assert built.columns == (columns[0], columns[1], columns[2])
    assert isinstance(built.columns, tuple)
    assert built.rows == (
        ("q", 3, date(2026, 1, 2)),
        (None, 0, None),
        ("b", None, date(2025, 5, 6)),
    )
    assert isinstance(built.rows, tuple)
    assert all(isinstance(row, tuple) for row in built.rows)
    zero = built.rows[1][1]
    assert zero == 0 and zero is not None
    assert built.rows[2][1] is None


def test_chart_data_accepts_a_generator_once() -> None:
    built = chart_data((column("a"),), ([i] for i in (5, 1, 3)))
    assert built.rows == ((5,), (1,), (3,))


def test_chart_request_defaults_and_copies() -> None:
    channels = {"y": "b", "x": "a"}
    options: dict[str, str | int | float | bool] = {"smooth": True, "n": 0}
    built = chart_request("bar", channels=channels, options=options)
    assert isinstance(built, ChartRequest)
    assert (built.ref, built.kind, built.title) == ("c1", "bar", "Title")
    assert list(built.channels.items()) == [("y", "b"), ("x", "a")]
    assert dict(built.options) == {"smooth": True, "n": 0}
    channels["x"] = "changed"
    options["n"] = 9
    assert built.channels == {"y": "b", "x": "a"}
    assert built.options == {"smooth": True, "n": 0}
    bare = chart_request("line", ref="r9", title="T9")
    assert (bare.ref, bare.kind, bare.title) == ("r9", "line", "T9")
    assert dict(bare.channels) == {} and dict(bare.options) == {}
    other = chart_request("line")
    assert other.channels is not bare.channels
    assert other.options is not bare.options
