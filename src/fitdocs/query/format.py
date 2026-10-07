"""Pure formatting helpers for in-memory query results."""

from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class OutputFormat(StrEnum):
    """Supported query output formats."""

    TABLE = "table"
    CSV = "csv"
    JSON = "json"


@dataclass(frozen=True)
class ResultSet:
    """Rows and result metadata captured before rendering."""

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    truncated: bool
    max_rows: int


FreshnessFields = Mapping[str, int | bool]


def default_format(stdout_is_terminal: bool) -> OutputFormat:
    """Choose a human-readable format only for an interactive terminal."""
    return OutputFormat.TABLE if stdout_is_terminal else OutputFormat.CSV


def _duration(value: dt.timedelta) -> str:
    total_microseconds = (
        value.days * 86400 + value.seconds
    ) * 1_000_000 + value.microseconds
    if total_microseconds == 0:
        return "PT0S"
    sign = "-" if total_microseconds < 0 else ""
    remaining = abs(total_microseconds)
    days, remaining = divmod(remaining, 86_400_000_000)
    hours, remaining = divmod(remaining, 3_600_000_000)
    minutes, remaining = divmod(remaining, 60_000_000)
    seconds, micros = divmod(remaining, 1_000_000)
    pieces = ["P"]
    if days:
        pieces.append(f"{days}D")
    time_parts: list[str] = []
    if hours:
        time_parts.append(f"{hours}H")
    if minutes:
        time_parts.append(f"{minutes}M")
    if seconds or micros or not days and not hours and not minutes:
        second_text = str(seconds)
        if micros:
            second_text += "." + f"{micros:06d}".rstrip("0")
        time_parts.append(second_text + "S")
    if time_parts:
        pieces.append("T" + "".join(time_parts))
    return sign + "".join(pieces)


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def text_value(value: object) -> str:
    """Convert a non-NULL database value to its specified textual value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, str):
        return value
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return _duration(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple, dict)):
        return json_value(value)
    return str(value)


def table_cell(value: object) -> str:
    """Render a table value, escaping control characters to keep rows intact."""
    if value is None:
        return "NULL"
    rendered = text_value(value)
    escaped: list[str] = []
    for character in rendered:
        codepoint = ord(character)
        if character == "\n":
            escaped.append(r"\n")
        elif character == "\t":
            escaped.append(r"\t")
        elif character == "\r":
            escaped.append(r"\r")
        elif codepoint < 32 or codepoint == 127:
            escaped.append(
                f"\\x{codepoint:02x}" if codepoint <= 255 else f"\\u{codepoint:04x}"
            )
        else:
            escaped.append(character)
    return "".join(escaped)


def csv_field(value: object) -> str:
    """Return an RFC-style CSV field, keeping NULL distinct from empty text."""
    if value is None:
        return ""
    rendered = text_value(value)
    if any(character in rendered for character in ',"\r\n') or rendered == "":
        return '"' + rendered.replace('"', '""') + '"'
    return rendered


def json_value(value: object) -> str:
    """Return one JSON token, retaining exact Decimal digits as a number."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return _json_string(text_value(value))
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, str):
        return _json_string(value)
    if isinstance(value, dt.datetime):
        return _json_string(value.isoformat())
    if isinstance(value, (dt.date, dt.time)):
        return _json_string(value.isoformat())
    if isinstance(value, dt.timedelta):
        return _json_string(_duration(value))
    if isinstance(value, bytes):
        return _json_string(value.hex())
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(json_value(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = (
            _json_string(text_value(key)) + ": " + json_value(item)
            for key, item in value.items()
        )
        return "{" + ", ".join(pairs) + "}"
    return _json_string(str(value))


def _table(result: ResultSet) -> str:
    headers = [table_cell(column) for column in result.columns]
    rows = [[table_cell(value) for value in row] for row in result.rows]
    widths = [
        max([len(headers[index]), *(len(row[index]) for row in rows)], default=0)
        for index in range(len(headers))
    ]
    rendered = [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    rendered.extend(
        "  ".join(
            value.rjust(widths[index])
            if isinstance(result.rows[row_index][index], (int, float, Decimal))
            and not isinstance(result.rows[row_index][index], bool)
            else value.ljust(widths[index])
            for index, value in enumerate(row)
        )
        for row_index, row in enumerate(rows)
    )
    count = len(result.rows)
    footer = (
        f"(first {count} rows; the result has more)"
        if result.truncated
        else f"({count} rows)"
    )
    rendered.append(footer)
    return "\n".join(rendered)


def _csv(result: ResultSet) -> str:
    lines = [",".join(csv_field(column) for column in result.columns)]
    lines.extend(",".join(csv_field(value) for value in row) for row in result.rows)
    return "\n".join(lines)


def _json(result: ResultSet, freshness: FreshnessFields) -> str:
    columns = "[" + ", ".join(_json_string(column) for column in result.columns) + "]"
    rows = (
        "[]"
        if not result.rows
        else "[\n"
        + ",\n".join(
            "[" + ", ".join(json_value(value) for value in row) + "]"
            for row in result.rows
        )
        + "\n]"
    )
    freshness_json = (
        "{"
        + ", ".join(
            _json_string(key) + ": " + json_value(value)
            for key, value in freshness.items()
        )
        + "}"
    )
    return (
        '{"columns": '
        + columns
        + ', "rows": '
        + rows
        + f', "row_count": {len(result.rows)}, '
        + f'"truncated": {json_value(result.truncated)}, '
        + f'"max_rows": {result.max_rows}, "freshness": {freshness_json}'
        + "}"
    )


def render_result(
    result: ResultSet,
    fmt: OutputFormat,
    *,
    freshness: FreshnessFields,
) -> str:
    """Render one result document in the chosen format."""
    if fmt is OutputFormat.TABLE:
        return _table(result)
    if fmt is OutputFormat.CSV:
        return _csv(result)
    if fmt is OutputFormat.JSON:
        return _json(result, freshness)
    raise ValueError(f"Unsupported output format: {fmt}")
