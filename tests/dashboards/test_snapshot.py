"""SnapshotCodec: the permanent snapshot format, strict decoding, file names."""

from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from fitdocs.dashboards.snapshot import (
    SNAPSHOT_FORMAT,
    SNAPSHOT_NAME_RE,
    SNAPSHOT_VERSION,
    Snapshot,
    SnapshotFormatError,
    decode,
    encode,
    snapshot_rel_path,
)
from fitdocs.render.charts.kit import (
    ChartData,
    Column,
    Value,
    ValueKind,
    kind_names,
    render_chart,
)

SQL = "select 1 as a"
SHA = "a" * 64


def _snapshot(
    columns: tuple[Column, ...], rows: tuple[tuple[Value, ...], ...]
) -> Snapshot:
    return Snapshot(
        page="pace",
        chart="weekly-km",
        generation=3,
        today=date(2026, 10, 12),
        sql=SQL,
        sql_sha256=SHA,
        data=ChartData(columns, rows),
    )


def _round_trip(kind: ValueKind, values: list[Value]) -> list[Value]:
    snapshot = _snapshot((Column("v", kind),), tuple((v,) for v in values))
    return [row[0] for row in decode(encode(snapshot)).data.rows]


def _assert_same(decoded: list[Value], original: list[Value]) -> None:
    assert [type(v) for v in decoded] == [type(v) for v in original]
    assert decoded == original
    for got, want in zip(decoded, original, strict=True):
        if isinstance(want, Decimal):
            assert got.as_tuple() == want.as_tuple()  # type: ignore[union-attr]
        if isinstance(want, float):
            assert repr(got) == repr(want)


def test_number_round_trip_keeps_value_and_python_type() -> None:
    original: list[Value] = [
        Decimal("1.50"),
        Decimal("3"),
        Decimal("-0"),
        Decimal("0.5"),
        Decimal("100.25"),
        -0.0,
        1e-7,
        None,
        10**40 + 7,
        -3,
        0.1,
        Decimal("-0.003"),
        2.0,
        1.5e300,
    ]
    decoded = _round_trip(ValueKind.NUMBER, original)
    _assert_same(decoded, original)
    assert str(decoded[0]) == "1.50"  # Decimal("1.50") is not Decimal("1.5")


def test_decimal_with_an_exponent_decodes_to_its_plain_form() -> None:
    (decoded,) = _round_trip(ValueKind.NUMBER, [Decimal("1E+2")])
    assert decoded == Decimal("100")
    assert type(decoded) is Decimal


def test_float_that_is_whole_stays_a_float_and_int_stays_an_int() -> None:
    decoded = _round_trip(ValueKind.NUMBER, [2.0, 2])
    assert [type(v) for v in decoded] == [float, int]


def test_date_round_trip() -> None:
    original: list[Value] = [date(2026, 10, 12), None, date(1, 1, 1), date(2024, 2, 29)]
    _assert_same(_round_trip(ValueKind.DATE, original), original)


def test_datetime_round_trip_with_microseconds() -> None:
    original: list[Value] = [
        datetime(2026, 10, 12, 6, 30, 5, 123456),
        None,
        datetime(2026, 10, 12, 6, 30, 5),
        datetime(2026, 1, 1, 0, 0, 0, 1),
    ]
    decoded = _round_trip(ValueKind.DATETIME, original)
    _assert_same(decoded, original)
    assert decoded[0].microsecond == 123456  # type: ignore[union-attr]
    assert decoded[3].microsecond == 1  # type: ignore[union-attr]


def test_duration_round_trip_negative_and_multi_day() -> None:
    original: list[Value] = [
        timedelta(days=2, hours=3, microseconds=7),
        timedelta(seconds=-90, microseconds=-5),
        None,
        timedelta(0),
        timedelta(days=-3),
        timedelta(days=100_000_000, microseconds=7),
    ]
    _assert_same(_round_trip(ValueKind.DURATION, original), original)


def test_category_and_boolean_round_trip() -> None:
    category: list[Value] = ["Run", None, "", "naïve – “quoted” ☃", "line\nbreak"]
    _assert_same(_round_trip(ValueKind.CATEGORY, category), category)
    boolean: list[Value] = [True, None, False]
    decoded = _round_trip(ValueKind.BOOLEAN, boolean)
    _assert_same(decoded, boolean)
    assert [type(v) for v in decoded] == [bool, type(None), bool]


def test_header_fields_and_column_kinds_round_trip_and_units_are_dropped() -> None:
    columns = (
        Column("n", ValueKind.NUMBER, unit="km", label="Distance"),
        Column("when", ValueKind.DATE),
        Column("flag", ValueKind.BOOLEAN),
    )
    snapshot = _snapshot(columns, ((1, date(2026, 1, 2), True),))
    decoded = decode(encode(snapshot))
    assert decoded.page == "pace"
    assert decoded.chart == "weekly-km"
    assert decoded.generation == 3
    assert decoded.today == date(2026, 10, 12)
    assert decoded.sql == SQL
    assert decoded.sql_sha256 == SHA
    assert decoded.data.columns == (
        Column("n", ValueKind.NUMBER),
        Column("when", ValueKind.DATE),
        Column("flag", ValueKind.BOOLEAN),
    )


def test_exact_encoded_bytes() -> None:
    snapshot = Snapshot(
        page="pace",
        chart="weekly-km",
        generation=2,
        today=date(2026, 10, 12),
        sql="select 'é'",
        sql_sha256="b" * 64,
        data=ChartData(
            (
                Column("name", ValueKind.CATEGORY, unit="x"),
                Column("km", ValueKind.NUMBER),
                Column("dur", ValueKind.DURATION),
            ),
            (("Run", Decimal("1.50"), timedelta(seconds=-1)), (None, 2.5, None)),
        ),
    )
    expected = (
        '{"format":"fitdocs-dashboard-snapshot","version":1,"page":"pace",'
        '"chart":"weekly-km","generation":2,"today":"2026-10-12",'
        f'"sql_sha256":"{"b" * 64}","sql":"select \'é\'",'
        '"columns":[{"name":"name","kind":"category"},'
        '{"name":"km","kind":"number"},{"name":"dur","kind":"duration"}],'
        '"rows":[["Run","1.50",-1000000],[null,2.5,null]]}\n'
    )
    assert encode(snapshot) == expected.encode("utf-8")


def test_constants() -> None:
    assert SNAPSHOT_FORMAT == "fitdocs-dashboard-snapshot"
    assert SNAPSHOT_VERSION == 1


# -- strict decoding --------------------------------------------------------------


def _document() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        encode(
            _snapshot(
                (Column("a", ValueKind.NUMBER), Column("b", ValueKind.CATEGORY)),
                ((1, "x"), (2.5, None)),
            )
        )
    )
    return document


def _raw(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, separators=(",", ":")) + "\n").encode()


def test_the_base_document_decodes() -> None:
    assert decode(_raw(_document())).data.rows == ((1, "x"), (2.5, None))


def _drop(key: str) -> dict[str, Any]:
    document = _document()
    del document[key]
    return document


def _with(**changes: Any) -> dict[str, Any]:
    return {**_document(), **changes}


def _cell(value: Any) -> dict[str, Any]:
    return _with(rows=[[1, "x"], [value, None]])


REFUSED: list[tuple[str, dict[str, Any]]] = [
    ("missing page", _drop("page")),
    ("missing rows", _drop("rows")),
    ("missing sql_sha256", _drop("sql_sha256")),
    ("unknown key", _with(extra=1)),
    ("another format", _with(format="something-else")),
    ("version 2", _with(version=2)),
    ("version 0", _with(version=0)),
    ("version true", _with(version=True)),
    ("version as string", _with(version="1")),
    ("generation 0", _with(generation=0)),
    ("generation bool", _with(generation=True)),
    ("generation string", _with(generation="2")),
    ("page not a string", _with(page=4)),
    ("sql not a string", _with(sql=None)),
    ("sql_sha256 not a string", _with(sql_sha256=7)),
    ("chart not a string", _with(chart=7)),
    ("column entry not an object", _with(columns=["a", "b"])),
    ("column kind not a string", _with(columns=[{"name": "a", "kind": 5}])),
    ("page with underscore", _with(page="a_b")),
    ("columns empty object", _with(columns={}, rows=[])),
    ("columns empty string", _with(columns="", rows=[])),
    ("rows empty object", _with(rows={})),
    ("rows empty string", _with(rows="")),
    ("column entry a two-item list", _with(columns=[["name", "kind"]], rows=[])),
    (
        "row a string as wide as the columns",
        _with(
            columns=[
                {"name": "a", "kind": "category"},
                {"name": "b", "kind": "category"},
            ],
            rows=["ab"],
        ),
    ),
    ("chart with trailing hyphen", _with(chart="ab-")),
    ("today not a date", _with(today="2026-13-01")),
    ("today with time", _with(today="2026-10-12T00:00:00")),
    ("today short", _with(today="2026-1-2")),
    ("today compact", _with(today="20261012")),
    ("today week date", _with(today="2026-W42-1")),
    ("today number", _with(today=20261012)),
    (
        "kind outside ValueKind",
        _with(columns=[{"name": "a", "kind": "number"}, {"name": "b", "kind": "text"}]),
    ),
    (
        "column missing kind",
        _with(columns=[{"name": "a", "kind": "number"}, {"name": "b"}]),
    ),
    (
        "column unknown key",
        _with(
            columns=[
                {"name": "a", "kind": "number"},
                {"name": "b", "kind": "category", "unit": "s"},
            ]
        ),
    ),
    (
        "column name not a string",
        _with(
            columns=[{"name": "a", "kind": "number"}, {"name": 1, "kind": "category"}]
        ),
    ),
    ("columns not a list", _with(columns={"a": "number"})),
    ("row too narrow", _with(rows=[[1, "x"], [2]])),
    ("row too wide", _with(rows=[[1, "x"], [2, "y", 3]])),
    ("row not a list", _with(rows=[[1, "x"], {"a": 1}])),
    ("rows not a list", _with(rows="none")),
    ("number as bool", _cell(True)),
    ("number as list", _cell([1])),
    ("number string not numeric", _cell("abc")),
    ("number string NaN", _cell("NaN")),
    ("number string Infinity", _cell("Infinity")),
    ("number string padded", _cell(" 1.5")),
    ("number string exponent", _cell("1E+2")),
    ("number string underscore", _cell("1_000")),
    ("number string arabic digit", _cell("\u0661")),
    ("number string plus sign", _cell("+1")),
    ("number string trailing point", _cell("1.")),
    ("number string leading point", _cell(".5")),
    ("number string empty", _cell("")),
    ("number string bare minus", _cell("-")),
    ("number string double minus", _cell("--1")),
    ("number string two points", _cell("1.2.3")),
    ("number string trailing text", _cell("1.5x")),
    ("page not a slug", _with(page="../x")),
    ("chart not a slug", _with(chart="Weekly Km")),
    ("category as number", _with(rows=[[1, "x"], [2, 5]])),
    ("category as bool", _with(rows=[[1, "x"], [2, False]])),
]


@pytest.mark.parametrize("name,document", REFUSED, ids=[n for n, _ in REFUSED])
def test_strict_decoding_refuses(name: str, document: dict[str, Any]) -> None:
    with pytest.raises(SnapshotFormatError):
        decode(_raw(document))


def _kind_cell(kind: str, value: Any) -> bytes:
    return _raw(_with(columns=[{"name": "a", "kind": kind}], rows=[[value]]))


@pytest.mark.parametrize(
    "kind,value",
    [
        ("date", "2026-10-12T00:00:00"),
        ("date", "2026-1-2"),
        ("date", "20261012"),
        ("date", "2026-W42-1"),
        ("date", "2026-02-30"),
        ("date", 20261012),
        ("date", True),
        ("datetime", "2026-10-12"),
        ("datetime", "2026-10-12T06:30:05+00:00"),
        ("datetime", "2026-10-12T06:30"),
        ("date", "\u0662\u0660\u0662\u0666-\u0661\u0660-\u0661\u0662"),
        ("datetime", "2026-10-12T06:30:05Z"),
        ("datetime", "2026-10-12 06:30:05"),
        ("datetime", "2026-10-12T06:30:05.1"),
        ("datetime", "2026-10-12T06:30:05.123"),
        ("datetime", "2026-10-12T06:30:05.1234567"),
        ("datetime", 5),
        ("duration", 1.5),
        ("duration", "10"),
        ("duration", True),
        ("duration", 10**30),
        ("boolean", 1),
        ("boolean", "true"),
        ("boolean", 0),
        ("category", ["a"]),
    ],
)
def test_strict_decoding_refuses_a_value_of_the_wrong_type_or_shape(
    kind: str, value: Any
) -> None:
    with pytest.raises(SnapshotFormatError):
        decode(_kind_cell(kind, value))


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json\n",
        b"[]\n",
        b"null\n",
        b'{"format": ',
        b"\xff\xfe\n",
        _raw(_document()).replace(b"select", b"sel\xffect"),
        b"[" * 100000 + b"\n",
        b'{"format":' + b"9" * 5000 + b"}\n",
        _raw(_document()).replace(b"2.5", b"1e400"),
        b"\xef\xbb\xbf" + _raw(_document()),
        _raw(_document()).replace(b'"version":1', b'"version":1,"version":1'),
        _raw(_document()).replace(
            b'"rows":[[1,"x"],[2.5,null]]', b'"rows":[[1,"x"],[NaN,null]]'
        ),
        _raw(_document()).replace(
            b'"rows":[[1,"x"],[2.5,null]]', b'"rows":[[1,"x"],[Infinity,null]]'
        ),
        _raw(_document()).rstrip(b"\n"),
        _raw(_document()) + b"\n",
        _raw(_document()) + b"{}\n",
    ],
    ids=[
        "empty",
        "not json",
        "array",
        "null",
        "truncated",
        "bad utf-8",
        "bad utf-8 inside a string",
        "nested too deeply",
        "integer too long to read",
        "float overflowing to infinity",
        "byte order mark",
        "duplicate key",
        "NaN",
        "Infinity",
        "no trailing newline",
        "two trailing newlines",
        "trailing document",
    ],
)
def test_strict_decoding_refuses_malformed_bytes(raw: bytes) -> None:
    with pytest.raises(SnapshotFormatError):
        decode(raw)


def test_a_malformed_document_is_a_snapshot_format_error_and_a_value_error() -> None:
    assert issubclass(SnapshotFormatError, ValueError)
    with pytest.raises(SnapshotFormatError) as info:
        decode(_raw(_with(version=2)))
    assert "version" in str(info.value)


def test_encode_refuses_what_cannot_be_stored() -> None:
    nan = _snapshot((Column("v", ValueKind.NUMBER),), ((float("nan"),),))
    with pytest.raises(ValueError):
        encode(nan)
    inf = _snapshot((Column("v", ValueKind.NUMBER),), ((Decimal("Infinity"),),))
    with pytest.raises(ValueError):
        encode(inf)
    aware = _snapshot(
        (Column("v", ValueKind.DATETIME),),
        ((datetime(2026, 1, 1, tzinfo=None).astimezone(),),),
    )
    with pytest.raises(ValueError):
        encode(aware)
    date_column_with_datetime = _snapshot(
        (Column("v", ValueKind.DATE),), ((datetime(2026, 1, 1),),)
    )
    with pytest.raises(ValueError):
        encode(date_column_with_datetime)
    int_in_boolean = _snapshot((Column("v", ValueKind.BOOLEAN),), ((1,),))
    with pytest.raises(ValueError):
        encode(int_in_boolean)
    float_in_duration = _snapshot((Column("v", ValueKind.DURATION),), ((1.5,),))
    with pytest.raises(ValueError):
        encode(float_in_duration)
    datetime_column_with_text = _snapshot(
        (Column("v", ValueKind.DATETIME),), (("2026-01-01T00:00:00",),)
    )
    with pytest.raises(ValueError):
        encode(datetime_column_with_text)
    wrong = _snapshot((Column("v", ValueKind.CATEGORY),), ((3,),))
    with pytest.raises(ValueError):
        encode(wrong)
    boolean_in_number = _snapshot((Column("v", ValueKind.NUMBER),), ((True,),))
    with pytest.raises(ValueError):
        encode(boolean_in_number)
    narrow = _snapshot(
        (Column("a", ValueKind.NUMBER), Column("b", ValueKind.NUMBER)), ((1,),)
    )
    with pytest.raises(ValueError):
        encode(narrow)


# -- file names -----------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "pace.snapshot-12.json",
        "a-b1.snapshot-1.json",
        "x.snapshot-10.json",
        "a-b-c.snapshot-3.json",
        "pace.snapshot-123.json",
        "9.snapshot-1.json",
    ],
)
def test_name_grammar_accepts(name: str) -> None:
    assert SNAPSHOT_NAME_RE.fullmatch(name)


@pytest.mark.parametrize(
    "name",
    [
        "pace.snapshot-0.json",
        "pace.snapshot-01.json",
        "Pace.snapshot-1.json",
        "pace.snapshot-.json",
        "pace.snapshot-1.json.tmp",
        "pace.snapshot-1.svg",
        "pace.snapshot--1.json",
        "-pace.snapshot-1.json",
        ".snapshot-1.json",
        "pace.snapshot-1.json\n",
        "pace.snapshot-١.json",
        "a--b.snapshot-1.json",
        "pace.snapshot1.json",
        "pace.snapshot-1\u0661.json",
        "pace-.snapshot-1.json",
        "a_b.snapshot-1.json",
        "pacexsnapshot-1.json",
        "pace.snapshot-1xjson",
        "pace.snapshot-12a.json",
        "pace.snapshot-1.jsonx",
        "xpace/pace.snapshot-1.json",
    ],
)
def test_name_grammar_refuses(name: str) -> None:
    assert SNAPSHOT_NAME_RE.fullmatch(name) is None


def test_name_grammar_captures_the_generation() -> None:
    match = SNAPSHOT_NAME_RE.fullmatch("pace.snapshot-12.json")
    assert match is not None
    assert match.group("generation") == "12"


def test_snapshot_rel_path() -> None:
    assert snapshot_rel_path("pace", "weekly-km", 7) == (
        "assets/pace/weekly-km.snapshot-7.json"
    )
    assert SNAPSHOT_NAME_RE.fullmatch(snapshot_rel_path("p", "c", 10).split("/")[-1])


def test_snapshot_rel_path_refuses_a_bool_generation() -> None:
    with pytest.raises(ValueError):
        snapshot_rel_path("pace", "c", True)


@pytest.mark.parametrize(
    "page,chart,generation",
    [
        ("pace", "c", 0),
        ("pace", "c", -1),
        ("Pace", "c", 1),
        ("pace", "C", 1),
        ("pa/ce", "c", 1),
        ("pace", "..", 1),
        ("", "c", 1),
    ],
)
def test_snapshot_rel_path_refuses_what_could_not_be_named(
    page: str, chart: str, generation: int
) -> None:
    with pytest.raises(ValueError):
        snapshot_rel_path(page, chart, generation)


# -- every registered kind (10.9) ---------------------------------------------------


def test_every_registered_kind_renders_identically_from_a_decoded_snapshot() -> None:
    visited: dict[str, int] = {}
    for name in kind_names():
        module = importlib.import_module(
            f"tests.render.charts.kit.test_{name.replace('-', '_')}"
        )
        for case in module.CASES:
            snapshot = _snapshot(case.data.columns, case.data.rows)
            decoded = decode(encode(snapshot))
            assert decoded.data.rows == case.data.rows
            fresh = render_chart(case.request, case.data)
            from_snapshot = render_chart(
                case.request, ChartData(case.data.columns, decoded.data.rows)
            )
            assert from_snapshot.output == fresh.output
            assert from_snapshot.text.encode() == fresh.text.encode(), (name, case.name)
            visited[name] = visited.get(name, 0) + 1
    assert set(visited) == set(kind_names())
