"""Tests for the kit's problem types (chart-kit Req 4.1, 4.5)."""

from __future__ import annotations

import dataclasses
import json

from fitdocs.render.charts.kit.problems import (
    ChartError,
    ChartProblem,
    ProblemCode,
    ProblemDict,
)

CORE_CODES = (
    "unknown_kind",
    "empty_title",
    "duplicate_column",
    "unknown_channel",
    "missing_channel",
    "unknown_column",
    "channel_kind",
    "unknown_unit",
    "unit_kind",
    "unit_mismatch",
    "unknown_option",
    "option_value",
    "option_conflict",
    "row_width",
    "value_type",
    "non_finite",
    "over_bound",
    "too_many_series",
    "duplicate_position",
    "log_domain",
    "stack_absent",
    "stack_negative",
    "stack_incomplete",
)

FIELD_ORDER = [
    "ref",
    "kind",
    "code",
    "message",
    "fix",
    "channel",
    "column",
    "option",
    "row",
    "rows",
    "accepted",
]


def test_core_codes_prefix() -> None:
    assert len(CORE_CODES) == 23
    assert tuple(str(c.value) for c in tuple(ProblemCode)[:23]) == CORE_CODES


def test_code_names_match_values() -> None:
    assert all(c.name == c.value.upper() for c in ProblemCode)


def _full() -> ChartProblem:
    return ChartProblem(
        "ref-1",
        "line",
        ProblemCode.UNKNOWN_COLUMN,
        "No such column.",
        "Name a column.",
        channel="x",
        column="c",
        option="o",
        row=0,
        rows=3,
        accepted=("a", "b"),
    )


def test_field_order_and_defaults() -> None:
    fields = dataclasses.fields(ChartProblem)
    assert [f.name for f in fields] == FIELD_ORDER
    bare = ChartProblem("r", None, ProblemCode.EMPTY_TITLE, "m.", "f.")
    assert (bare.channel, bare.column, bare.option, bare.row, bare.rows) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert bare.accepted == ()


def test_as_dict_keys_in_field_order_and_json() -> None:
    d = _full().as_dict()
    assert list(d) == FIELD_ORDER
    assert d["code"] == "unknown_column"
    assert type(d["code"]) is str
    assert d["accepted"] == ["a", "b"]
    assert type(d["accepted"]) is list
    assert d["row"] == 0
    assert d == {
        "ref": "ref-1",
        "kind": "line",
        "code": "unknown_column",
        "message": "No such column.",
        "fix": "Name a column.",
        "channel": "x",
        "column": "c",
        "option": "o",
        "row": 0,
        "rows": 3,
        "accepted": ["a", "b"],
    }
    assert json.loads(json.dumps(d)) == d
    assert list(json.loads(json.dumps(d))) == FIELD_ORDER


def test_problem_dict_declaration_order() -> None:
    assert list(ProblemDict.__annotations__) == FIELD_ORDER


def test_as_dict_defaults() -> None:
    d = ChartProblem("r", None, ProblemCode.EMPTY_TITLE, "m.", "f.").as_dict()
    assert d["kind"] is None
    assert d["row"] is None
    assert d["accepted"] == []


def test_chart_error_message_and_problems() -> None:
    p1 = _full()
    p2 = ChartProblem("r2", None, ProblemCode.EMPTY_TITLE, "Second.", "f.")
    err = ChartError((p1, p2))
    assert isinstance(err, ValueError)
    assert err.problems == (p1, p2)
    assert str(err) == "No such column.\nSecond."
