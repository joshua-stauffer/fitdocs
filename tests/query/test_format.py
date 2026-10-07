"""Pure in-memory tests for query result rendering."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from fitdocs.query.format import (
    OutputFormat,
    ResultSet,
    csv_field,
    default_format,
    json_value,
    render_result,
    table_cell,
    text_value,
)

EMPTY_FRESHNESS: dict[str, int | bool] = {
    "missing": 0,
    "changed": 0,
    "removed": 0,
}


@pytest.mark.parametrize(
    ("value", "text", "json"),
    [
        (None, "NULL", "null"),
        (True, "true", "true"),
        (False, "false", "false"),
        (0, "0", "0"),
        (-12, "-12", "-12"),
        (0.0, "0.0", "0.0"),
        (1.25, "1.25", "1.25"),
        (1.2345678901234567, "1.2345678901234567", "1.2345678901234567"),
        (Decimal("1E+2"), "100", "100"),
        (
            Decimal("12345678901234567890.1234500"),
            "12345678901234567890.1234500",
            "12345678901234567890.1234500",
        ),
        ("hello", "hello", '"hello"'),
        ("café", "café", '"café"'),
        (dt.date(2024, 2, 3), "2024-02-03", '"2024-02-03"'),
        (dt.time(4, 5, 6), "04:05:06", '"04:05:06"'),
        (
            dt.time(4, 5, 6, tzinfo=dt.timezone(dt.timedelta(hours=2))),
            "04:05:06+02:00",
            '"04:05:06+02:00"',
        ),
        (
            dt.datetime(2024, 2, 3, 4, 5, 6),
            "2024-02-03T04:05:06",
            '"2024-02-03T04:05:06"',
        ),
        (
            dt.datetime(2024, 2, 3, 4, 5, 6, tzinfo=dt.timezone(dt.timedelta(hours=2))),
            "2024-02-03T04:05:06+02:00",
            '"2024-02-03T04:05:06+02:00"',
        ),
        (
            uuid.UUID("abcdef12-3456-abcd-ef12-abcdef123456"),
            "abcdef12-3456-abcd-ef12-abcdef123456",
            '"abcdef12-3456-abcd-ef12-abcdef123456"',
        ),
        (b"\x00\xff", "00ff", '"00ff"'),
        ([1, None, "x"], '[1, null, "x"]', '[1, null, "x"]'),
        ((1, False), "[1, false]", "[1, false]"),
        ({"a": 1}, '{"a": 1}', '{"a": 1}'),
        ({1: "one"}, '{"1": "one"}', '{"1": "one"}'),
        ({Decimal("1E+2"): "hundred"}, '{"100": "hundred"}', '{"100": "hundred"}'),
    ],
)
def test_value_rules(value: object, text: str, json: str) -> None:
    if value is None:
        assert table_cell(value) == text
        assert csv_field(value) == ""
        assert json_value(value) == json
    else:
        assert text_value(value) == text
        assert table_cell(value) == text
        csv_expected = (
            '"' + text.replace('"', '""') + '"'
            if any(character in text for character in ',"\r\n') or text == ""
            else text
        )
        assert csv_field(value) == csv_expected
        assert json_value(value) == json


@pytest.mark.parametrize(
    ("value", "expected"),
    [(float("nan"), "NaN"), (float("inf"), "Infinity"), (float("-inf"), "-Infinity")],
)
def test_nonfinite_float_tokens_in_each_format(value: float, expected: str) -> None:
    result = ResultSet(("v",), ((value,),), False, 10)
    assert table_cell(value) == expected
    assert csv_field(value) == expected
    assert f'"{expected}"' in render_result(
        result, OutputFormat.JSON, freshness=EMPTY_FRESHNESS
    )


def test_null_empty_zero_float_false_and_null_text_are_distinct() -> None:
    result = ResultSet(
        ("v", "v", "v", "v", "v", "v"),
        ((None, 0, 0.0, "", False, "NULL"),),
        False,
        10,
    )
    csv = render_result(result, OutputFormat.CSV, freshness=EMPTY_FRESHNESS)
    assert csv.splitlines()[1] == ',0,0.0,"",false,NULL'
    parsed = json_value((None, 0, 0.0, "", False, "NULL"))
    assert parsed == '[null, 0, 0.0, "", false, "NULL"]'
    rendered_json = render_result(result, OutputFormat.JSON, freshness=EMPTY_FRESHNESS)
    assert '[null, 0, 0.0, "", false, "NULL"]' in rendered_json
    table_values = tuple(table_cell(value) for value in result.rows[0])
    assert table_values == ("NULL", "0", "0.0", "", "false", "NULL")
    assert table_cell(None) == "NULL"
    assert csv_field(None) == ""
    assert json_value(None) == "null"


def test_table_layout_alignment_control_escaping_and_truncated_footer() -> None:
    result = ResultSet(
        ("name", "n", "note"),
        (("A\nB\t\x01\rC", 12, "x"),),
        True,
        1,
    )
    rendered = render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS)
    assert "A\\nB\\t\\x01\\rC" in rendered
    assert " 12  " in rendered
    assert rendered.splitlines()[-1] == "(first 1 rows; the result has more)"


def test_table_right_aligns_numeric_cells_in_mixed_columns() -> None:
    result = ResultSet(
        ("value",), (("long",), (2,), (3.14,), (Decimal("1.5"),)), False, 10
    )
    rendered = render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS)
    assert rendered.splitlines() == [
        "value",
        "-----",
        "long ",
        "    2",
        " 3.14",
        "  1.5",
        "(4 rows)",
    ]


def test_table_left_aligns_bools_even_in_a_numeric_column() -> None:
    result = ResultSet(("value",), (("much-longer",), (True,), (False,)), False, 10)
    rendered = render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS)
    assert rendered.splitlines() == [
        "value      ",
        "-----------",
        "much-longer",
        "true       ",
        "false      ",
        "(3 rows)",
    ]


def test_csv_preserves_unquoted_control_characters_and_quotes_line_breaks() -> None:
    result = ResultSet(("v",), (("tab\tcontrol\x01\nline",),), False, 1)
    rendered = render_result(result, OutputFormat.CSV, freshness=EMPTY_FRESHNESS)
    assert rendered == 'v\n"tab\tcontrol\x01\nline"'


def test_duration_formatting_keeps_fraction_and_negative_sign() -> None:
    duration = dt.timedelta(days=1, seconds=3661, microseconds=500000)
    assert text_value(duration) == "P1DT1H1M1.5S"
    assert json_value(duration) == '"P1DT1H1M1.5S"'
    assert text_value(dt.timedelta()) == "PT0S"
    assert text_value(-dt.timedelta(seconds=1, microseconds=250000)) == "-PT1.25S"
    assert json_value(dt.timedelta()) == '"PT0S"'
    assert json_value(-dt.timedelta(seconds=1, microseconds=250000)) == '"-PT1.25S"'
    assert text_value(dt.timedelta(days=2)) == "P2D"
    assert json_value(dt.timedelta(days=2)) == '"P2D"'


def test_csv_quotes_delimiters_quotes_cr_lf_and_empty_text() -> None:
    values = ("a,b", 'a"b', "a\rb", "a\nb", "")
    assert tuple(csv_field(value) for value in values) == (
        '"a,b"',
        '"a""b"',
        '"a\rb"',
        '"a\nb"',
        '""',
    )
    output = render_result(
        ResultSet(("a,b", 'q"q', "cr", "lf", "empty"), (values,), False, 10),
        OutputFormat.CSV,
        freshness=EMPTY_FRESHNESS,
    )
    assert output == '"a,b","q""q",cr,lf,empty\n"a,b","a""b","a\rb","a\nb",""'


def test_json_duplicate_columns_order_freshness_and_exact_decimal() -> None:
    result = ResultSet(
        ("first", "second"),
        ((Decimal("1E+2"), 2), (Decimal("12345678901234567890.1234500"), 3)),
        False,
        5,
    )
    rendered = render_result(
        result,
        OutputFormat.JSON,
        freshness={"missing": 3, "changed": 2, "removed": 1},
    )
    assert rendered == (
        '{"columns": ["first", "second"], "rows": [\n'
        "[100, 2],\n[12345678901234567890.1234500, 3]\n], "
        '"row_count": 2, "truncated": false, "max_rows": 5, '
        '"freshness": {"missing": 3, "changed": 2, "removed": 1}}'
    )
    assert render_result(result, OutputFormat.CSV, freshness=EMPTY_FRESHNESS) == (
        "first,second\n100,2\n12345678901234567890.1234500,3"
    )
    assert render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS) == (
        "first                         second\n"
        "----------------------------  ------\n"
        "                         100       2\n"
        "12345678901234567890.1234500       3\n(2 rows)"
    )


def test_json_repeated_column_names_keep_each_ordered_value() -> None:
    result = ResultSet(("score", "score"), ((17, 42),), False, 1)
    rendered = render_result(result, OutputFormat.JSON, freshness=EMPTY_FRESHNESS)
    assert rendered == (
        '{"columns": ["score", "score"], "rows": [\n'
        '[17, 42]\n], "row_count": 1, "truncated": false, '
        '"max_rows": 1, "freshness": '
        '{"missing": 0, "changed": 0, "removed": 0}}'
    )


def test_table_escapes_delete_control_character() -> None:
    result = ResultSet(("value",), (("before\x7fafter",),), False, 1)
    rendered = render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS)
    assert rendered == ("value          \n---------------\nbefore\\x7fafter\n(1 rows)")


def test_json_truncation_metadata_matches_printed_rows_and_limit() -> None:
    rendered = render_result(
        ResultSet(("n",), ((3,), (5,)), True, 2),
        OutputFormat.JSON,
        freshness=EMPTY_FRESHNESS,
    )
    assert '"row_count": 2' in rendered
    assert '"truncated": true' in rendered
    assert '"max_rows": 2' in rendered


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" leading", " leading"),
        ("trailing ", "trailing "),
        (" both ", " both "),
        ("   ", "   "),
    ],
)
def test_string_whitespace_is_preserved_by_value_renderers(
    value: str, expected: str
) -> None:
    assert text_value(value) == expected
    assert table_cell(value) == expected
    assert csv_field(value) == expected
    assert json_value(value) == '"' + expected + '"'


def test_whitespace_strings_are_preserved_in_exact_rendered_documents() -> None:
    result = ResultSet(
        (" leading", "trailing ", " both ", "   "),
        ((" leading", "trailing ", " both ", "   "),),
        False,
        1,
    )
    assert render_result(result, OutputFormat.CSV, freshness=EMPTY_FRESHNESS) == (
        " leading,trailing , both ,   \n leading,trailing , both ,   "
    )
    assert render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS) == (
        " leading  trailing    both      \n"
        "--------  ---------  ------  ---\n"
        " leading  trailing    both      \n"
        "(1 rows)"
    )
    assert render_result(result, OutputFormat.JSON, freshness=EMPTY_FRESHNESS) == (
        '{"columns": [" leading", "trailing ", " both ", "   "], "rows": [\n'
        '[" leading", "trailing ", " both ", "   "]\n], '
        '"row_count": 1, "truncated": false, "max_rows": 1, '
        '"freshness": {"missing": 0, "changed": 0, "removed": 0}}'
    )


def test_format_headers_preserve_whitespace_and_escape_documented_edges() -> None:
    columns = (
        " leading",
        "trailing ",
        " both ",
        "   ",
        "a,b",
        'q"q',
        "line\nb",
        "ctrl\x01",
    )
    result = ResultSet(columns, (), False, 1)
    assert render_result(result, OutputFormat.CSV, freshness=EMPTY_FRESHNESS) == (
        ' leading,trailing , both ,   ,"a,b","q""q","line\nb",ctrl\x01'
    )
    assert render_result(result, OutputFormat.TABLE, freshness=EMPTY_FRESHNESS) == (
        ' leading  trailing    both        a,b  q"q  line\\nb  ctrl\\x01\n'
        "--------  ---------  ------  ---  ---  ---  -------  --------\n"
        "(0 rows)"
    )
    assert render_result(result, OutputFormat.JSON, freshness=EMPTY_FRESHNESS) == (
        '{"columns": [" leading", "trailing ", " both ", "   ", '
        '"a,b", "q\\"q", "line\\nb", "ctrl\\u0001"], '
        '"rows": [], "row_count": 0, '
        '"truncated": false, "max_rows": 1, '
        '"freshness": {"missing": 0, "changed": 0, "removed": 0}}'
    )


def test_json_puts_each_result_row_on_its_own_line() -> None:
    rendered = render_result(
        ResultSet(("n",), ((3,), (5,)), False, 10),
        OutputFormat.JSON,
        freshness=EMPTY_FRESHNESS,
    )
    assert '"rows": [\n[3],\n[5]\n]' in rendered


@pytest.mark.parametrize("fmt", list(OutputFormat))
def test_zero_rows_have_format_structure(fmt: OutputFormat) -> None:
    rendered = render_result(
        ResultSet(("a", "b"), (), False, 10), fmt, freshness=EMPTY_FRESHNESS
    )
    if fmt is OutputFormat.TABLE:
        assert rendered == "a  b\n-  -\n(0 rows)"
    elif fmt is OutputFormat.CSV:
        assert rendered == "a,b"
    else:
        assert '"rows": []' in rendered and '"row_count": 0' in rendered


def test_default_format_tracks_terminal_state() -> None:
    assert default_format(True) is OutputFormat.TABLE
    assert default_format(False) is OutputFormat.CSV


def test_output_format_values_and_result_set_frozen_contract() -> None:
    assert tuple(fmt.value for fmt in OutputFormat) == ("table", "csv", "json")
    assert all(isinstance(fmt, str) for fmt in OutputFormat)
    result = ResultSet(("a",), ((1,),), False, 5)
    with pytest.raises(FrozenInstanceError):
        result.max_rows = 6  # type: ignore[misc]


def test_unknown_value_falls_back_to_text_and_json_string() -> None:
    class Strange:
        def __str__(self) -> str:
            return "strange-value"

    value = Strange()
    assert text_value(value) == "strange-value"
    assert json_value(value) == '"strange-value"'


def test_uuid_values_in_nested_json_use_canonical_lowercase() -> None:
    value = uuid.UUID("ABCDEF12-3456-ABCD-EF12-ABCDEF123456")
    assert text_value([value]) == '["abcdef12-3456-abcd-ef12-abcdef123456"]'
    assert json_value([value]) == '["abcdef12-3456-abcd-ef12-abcdef123456"]'
    assert json_value({value: value}) == (
        '{"abcdef12-3456-abcd-ef12-abcdef123456": '
        '"abcdef12-3456-abcd-ef12-abcdef123456"}'
    )
