"""The permanent snapshot format and the snapshot file names.

A snapshot is one JSON object holding the rows of one query at one date. The
format is versioned and never changes meaning. Decoding is strict about
content: exact keys, format, version 1, known column kinds, row widths, the
JSON type and shape of each value per kind, finite numbers, and slug page and
chart names. It does not require the exact byte layout `encode` writes beyond
UTF-8 and a single trailing newline.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from fitdocs.dashboards.grammar import SLUG
from fitdocs.render.charts.kit import ChartData, Column, Value, ValueKind

SNAPSHOT_FORMAT: Final = "fitdocs-dashboard-snapshot"
SNAPSHOT_VERSION: Final = 1

_SLUG: Final = SLUG
SNAPSHOT_NAME_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?P<id>{_SLUG})\.snapshot-(?P<generation>[1-9][0-9]*)\.json"
)
_SLUG_RE: Final = re.compile(_SLUG)
_DECIMAL_RE: Final = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_DATE_RE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATETIME_RE: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?"
)
_KEYS: Final = (
    "format",
    "version",
    "page",
    "chart",
    "generation",
    "today",
    "sql_sha256",
    "sql",
    "columns",
    "rows",
)
_MICROSECOND: Final = timedelta(microseconds=1)


class SnapshotFormatError(ValueError):
    """The bytes are not a snapshot this version of fitdocs wrote."""


@dataclass(frozen=True)
class Snapshot:
    page: str
    chart: str
    generation: int
    today: date
    sql: str
    sql_sha256: str
    data: ChartData  # columns: name + ValueKind (unit None); rows


def snapshot_rel_path(page: str, chart: str, generation: int) -> str:
    """``assets/<page>/<chart>.snapshot-<n>.json`` under the dashboards folder."""
    if not _SLUG_RE.fullmatch(page) or not _SLUG_RE.fullmatch(chart):
        raise ValueError("a snapshot is named by a page and a chart slug")
    if type(generation) is not int or generation < 1:
        raise ValueError("a snapshot generation is an integer of at least 1")
    return f"assets/{page}/{chart}.snapshot-{generation}.json"


# -- encoding -------------------------------------------------------------------


def _encode_value(kind: ValueKind, value: Value) -> object:
    if value is None:
        return None
    if kind is ValueKind.NUMBER:
        if type(value) is int:
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("a non-finite number cannot be stored")
            return value
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("a non-finite number cannot be stored")
            return format(value, "f")
    elif kind is ValueKind.DATE:
        if type(value) is date:
            return value.isoformat()
    elif kind is ValueKind.DATETIME:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.isoformat()
    elif kind is ValueKind.DURATION:
        if isinstance(value, timedelta):
            return value // _MICROSECOND
    elif kind is ValueKind.CATEGORY:
        if isinstance(value, str):
            return value
    elif isinstance(value, bool):
        return value
    raise ValueError(f"{value!r} is not a {kind.value} value")


def encode(snapshot: Snapshot) -> bytes:
    columns = snapshot.data.columns
    rows: list[list[object]] = []
    for row in snapshot.data.rows:
        if len(row) != len(columns):
            raise ValueError("a row's width differs from the column count")
        rows.append(
            [
                _encode_value(column.kind, v)
                for column, v in zip(columns, row, strict=True)
            ]
        )
    document = {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "page": snapshot.page,
        "chart": snapshot.chart,
        "generation": snapshot.generation,
        "today": snapshot.today.isoformat(),
        "sql_sha256": snapshot.sql_sha256,
        "sql": snapshot.sql,
        "columns": [{"name": c.name, "kind": c.kind.value} for c in columns],
        "rows": rows,
    }
    text = json.dumps(
        document, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return (text + "\n").encode("utf-8")


# -- decoding -------------------------------------------------------------------


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise SnapshotFormatError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _refuse_constant(name: str) -> Any:
    raise SnapshotFormatError(f"{name} is not a JSON number")


def _is_int(value: object) -> bool:
    return type(value) is int


def _decode_value(kind: ValueKind, value: Any, where: str) -> Value:
    if value is None:
        return None
    try:
        if kind is ValueKind.NUMBER:
            if _is_int(value):
                return value  # type: ignore[no-any-return]
            if type(value) is float:
                if math.isfinite(value):
                    return value
            elif isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
                number = Decimal(value)
                if number.is_finite():
                    return number
        elif kind is ValueKind.DATE:
            if isinstance(value, str) and _DATE_RE.fullmatch(value):
                return date.fromisoformat(value)
        elif kind is ValueKind.DATETIME:
            if isinstance(value, str) and _DATETIME_RE.fullmatch(value):
                return datetime.fromisoformat(value)
        elif kind is ValueKind.DURATION:
            if _is_int(value):
                return timedelta(microseconds=value)
        elif kind is ValueKind.CATEGORY:
            if isinstance(value, str):
                return value
        elif isinstance(value, bool):
            return value
    except (ValueError, OverflowError, InvalidOperation):
        pass
    raise SnapshotFormatError(f"{where}: not a valid {kind.value} value")


def _text(document: dict[str, Any], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise SnapshotFormatError(f"{key} must be a string")
    return value


def decode(raw: bytes) -> Snapshot:
    """Decode snapshot bytes, refusing any content that breaks the rules above."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SnapshotFormatError("not UTF-8") from error
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise SnapshotFormatError("must end with exactly one newline")
    try:
        document = json.loads(
            text, object_pairs_hook=_pairs, parse_constant=_refuse_constant
        )
    except SnapshotFormatError:
        raise
    except ValueError as error:  # malformed JSON, or an integer too long to read
        raise SnapshotFormatError(f"not JSON: {error}") from error
    except RecursionError as error:
        raise SnapshotFormatError("nested too deeply") from error
    if not isinstance(document, dict):
        raise SnapshotFormatError("not a JSON object")
    if set(document) != set(_KEYS):
        missing = sorted(set(_KEYS) - set(document))
        unknown = sorted(set(document) - set(_KEYS))
        raise SnapshotFormatError(f"keys differ: missing {missing}, unknown {unknown}")
    if document["format"] != SNAPSHOT_FORMAT:
        raise SnapshotFormatError("another format")
    if not _is_int(document["version"]) or document["version"] != SNAPSHOT_VERSION:
        raise SnapshotFormatError(f"version must be {SNAPSHOT_VERSION}")
    generation = document["generation"]
    if not _is_int(generation) or generation < 1:
        raise SnapshotFormatError("generation must be an integer of at least 1")
    today = document["today"]
    if not isinstance(today, str) or not _DATE_RE.fullmatch(today):
        raise SnapshotFormatError("today must be YYYY-MM-DD")
    try:
        today_date = date.fromisoformat(today)
    except ValueError as error:
        raise SnapshotFormatError("today is not a calendar date") from error
    page, chart = _text(document, "page"), _text(document, "chart")
    if not _SLUG_RE.fullmatch(page) or not _SLUG_RE.fullmatch(chart):
        raise SnapshotFormatError("page and chart must be slugs")
    raw_columns = document["columns"]
    if not isinstance(raw_columns, list):
        raise SnapshotFormatError("columns must be a list")
    columns: list[Column] = []
    for index, entry in enumerate(raw_columns):
        if not isinstance(entry, dict) or set(entry) != {"name", "kind"}:
            raise SnapshotFormatError(f"column {index} must hold exactly name and kind")
        name, kind_text = entry["name"], entry["kind"]
        if not isinstance(name, str) or not isinstance(kind_text, str):
            raise SnapshotFormatError(f"column {index}: name and kind are strings")
        try:
            kind = ValueKind(kind_text)
        except ValueError as error:
            raise SnapshotFormatError(
                f"column {index}: unknown kind {kind_text!r}"
            ) from error
        columns.append(Column(name, kind))
    raw_rows = document["rows"]
    if not isinstance(raw_rows, list):
        raise SnapshotFormatError("rows must be a list")
    rows: list[tuple[Value, ...]] = []
    for r, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, list) or len(raw_row) != len(columns):
            raise SnapshotFormatError(f"row {r}: expected {len(columns)} values")
        rows.append(
            tuple(
                _decode_value(column.kind, value, f"row {r}, column {column.name!r}")
                for column, value in zip(columns, raw_row, strict=True)
            )
        )
    return Snapshot(
        page=page,
        chart=chart,
        generation=generation,
        today=today_date,
        sql=_text(document, "sql"),
        sql_sha256=_text(document, "sql_sha256"),
        data=ChartData(tuple(columns), tuple(rows)),
    )
