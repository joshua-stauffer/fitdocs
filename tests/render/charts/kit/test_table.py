"""The table kind: a markdown table of every column.

Requirements 2.7, 9.8, 15.5, 15.6, 18.2 and 18.3.

Run ``uv run python -m tests.render.charts.kit.test_table`` to (re)write the
goldens under ``golden/table/``; a pytest run never writes them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from fitdocs.render.charts.kit import registry
from fitdocs.render.charts.kit.api import validate_chart
from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.table import KIND
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import MarkBound, Output, OverBound
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

REQUEST = chart_request("table", ref="t1", title="Workouts")

TYPICAL_COLUMNS = (
    column("day", ValueKind.DATE),
    column("started_utc", ValueKind.DATETIME, unit="utc"),
    column("run_name", ValueKind.CATEGORY),
    column("distance_km", unit="km"),
    column("elapsed", ValueKind.DURATION),
    column("pace_s_per_km", unit="s_per_km"),
    column("hr_bpm", unit="bpm"),
    column("done", ValueKind.BOOLEAN),
    column("moving_s", unit="s"),
    column("load"),
    column("grade_pct", unit="pct"),
)

# Rows are unsorted; row 1 holds zeros (not absent), row 2 is entirely absent,
# row 3 mixes present and absent cells.
TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (
        date(2026, 3, 14),
        datetime(2026, 3, 14, 6, 41, 59),
        "Tempo",
        12.345,
        timedelta(hours=1, minutes=2, seconds=3),
        301,
        152,
        True,
        1805,
        12.5,
        3.26,
    ),
    (
        date(2026, 3, 2),
        datetime(2026, 3, 2, 18, 5, 0),
        "Long",
        0,
        timedelta(0),
        0,
        0,
        False,
        0,
        0.0,
        0.0,
    ),
    (None, None, None, None, None, None, None, None, None, None, None),
    (
        None,
        None,
        "Zeta",
        7.0,
        timedelta(seconds=90),
        None,
        171,
        None,
        59.5,
        None,
        100.0,
    ),
)

TYPICAL_TEXT = "\n".join(
    (
        "| day | started (UTC) | run name | distance (km) | elapsed (h:mm:ss)"
        " | pace (min/km) | hr (bpm) | done | moving (m:ss) | load | grade (%) |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
        "| 2026-03-14 | 2026-03-14 06:41 | Tempo | 12.3 | 1:02:03 | 5:01 | 152"
        " | true | 30:05 | 12.5 | 3.3 |",
        "| 2026-03-02 | 2026-03-02 18:05 | Long | 0 | 0:00:00 | 0:00 | 0"
        " | false | 0:00 | 0 | 0.0 |",
        "| — | — | — | — | — | — | — | — | — | — | — |",
        "| — | — | Zeta | 7.0 | 0:01:30 | — | 171 | — | 1:00 | — | 100.0 |",
    )
)

NO_ROWS_COLUMNS = (
    column("run_name", ValueKind.CATEGORY),
    column("distance_km", unit="km"),
    column("elapsed", ValueKind.DURATION),
)
NO_ROWS_TEXT = (
    "| run name | distance (km) | elapsed (m:ss) |\n| --- | ---: | ---: |\n\nNo data"
)

SPECIAL_COLUMNS = (
    column("note", ValueKind.CATEGORY, label="Note | raw <b>\nnext\x07"),
    column("n"),
)
SPECIAL_ROWS: tuple[tuple[Value, ...], ...] = (
    ("a|b", 1),
    ("<b>bold</b>", 2),
    ("#tag", 3),
    ("[[x]]", 4),
    ("one\ntwo", 5),
    ("back\\slash", 6),
    ("x\r\ny", 7),
    ("tab\there", 8),
    ("`c` *e* _u_ ~s~ $v &a", 9),
    ("\x07bell", 10),
    (None, 11),
)
SPECIAL_TEXT = "\n".join(
    (
        "| Note \\| raw \\<b\\> next\ufffd | n |",
        "| --- | ---: |",
        "| a\\|b | 1 |",
        "| \\<b\\>bold\\</b\\> | 2 |",
        "| \\#tag | 3 |",
        "| \\[\\[x\\]\\] | 4 |",
        "| one two | 5 |",
        "| back\\\\slash | 6 |",
        "| x  y | 7 |",
        "| tab here | 8 |",
        "| \\`c\\` \\*e\\* \\_u\\_ \\~s\\~ \\$v \\&a | 9 |",
        "| �bell | 10 |",
        "| — | 11 |",
    )
)


def _at_bound_columns(count: int) -> tuple[Column, ...]:
    kinds = (
        column("day", ValueKind.DATE),
        column("started_utc", ValueKind.DATETIME, unit="utc"),
        column("run_name", ValueKind.CATEGORY),
        column("distance_km", unit="km"),
        column("elapsed", ValueKind.DURATION),
        column("pace_s_per_km", unit="s_per_km"),
        column("hr_bpm", unit="bpm"),
        column("done", ValueKind.BOOLEAN),
        column("moving_s", unit="s"),
        column("load"),
        column("grade_pct", unit="pct"),
        column("power_w", unit="w"),
    )
    return kinds[:count]


def _at_bound_data(rows: int = 100) -> ChartData:
    names = ("Easy", "Tempo", "Long", "Hill|rep", "Recovery")
    body: list[tuple[Value, ...]] = []
    for i in range(rows):
        absent = i % 9 == 4
        body.append(
            (
                date(2026, 1, 1) + timedelta(days=(i * 7) % 100),
                None if absent else datetime(2026, 1, 1, i % 24, (i * 7) % 60, i % 60),
                names[i % 5],
                None if absent else i * 0.37,
                timedelta(seconds=i * 61),
                240 + i * 3,
                None if absent else 120 + i % 55,
                i % 3 == 0,
                i * 97,
                i * 1.5,
                (i * 1.1) % 100,
                200 + (i * 13) % 150,
            )
        )
    return chart_data(_at_bound_columns(12), body)


CASES: tuple[Case, ...] = (
    Case("typical", REQUEST, chart_data(TYPICAL_COLUMNS, TYPICAL_ROWS)),
    Case("no_rows", REQUEST, chart_data(NO_ROWS_COLUMNS, [])),
    Case("special_chars", REQUEST, chart_data(SPECIAL_COLUMNS, SPECIAL_ROWS)),
    Case("at_bound", REQUEST, _at_bound_data()),
)


def _render(data: ChartData) -> str:
    return render_case(KIND, REQUEST, data).text


def _single_column(count: int) -> ChartData:
    return chart_data([column("v")], [(i,) for i in range(count)])


def _wide_columns(count: int) -> tuple[Column, ...]:
    return tuple(column(f"c{i}") for i in range(count))


def _registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``validate_chart`` find the table kind before task 6.1 registers it."""
    monkeypatch.setattr(registry, "KINDS", (*registry.KINDS, KIND))


# --- the declaration ---------------------------------------------------------


def test_kind_declaration() -> None:
    assert KIND.name == "table"
    assert KIND.description == "The rows as a markdown table with unit-aware cells"
    assert KIND.output is Output.MARKDOWN
    assert KIND.channels == ()
    assert KIND.options == ()
    assert KIND.bound == MarkBound(
        100, "rows", OverBound.REFUSE, "At most 100 rows and 12 columns."
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is True


# --- the output --------------------------------------------------------------


def test_every_value_kind_in_one_table() -> None:
    rendered = render_case(KIND, REQUEST, CASES[0].data)
    assert rendered.kind == "table"
    assert rendered.output is Output.MARKDOWN
    assert rendered.text == TYPICAL_TEXT
    assert not rendered.text.endswith("\n")


def test_header_and_delimiter_rows() -> None:
    header, delimiter, *_ = _render(CASES[0].data).split("\n")
    assert header.startswith("| day | started (UTC) | run name | distance (km) | ")
    assert delimiter == (
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |"
    )


def test_cells_carry_no_unit_and_no_utc_suffix() -> None:
    rows = _render(CASES[0].data).split("\n")[2:]
    assert "km" not in rows[0] and "bpm" not in rows[0] and "UTC" not in rows[0]
    assert "%" not in rows[0] and "/km" not in rows[0]


def test_rows_keep_their_order() -> None:
    lines = _render(CASES[0].data).split("\n")[2:]
    assert [line.split(" | ")[2] for line in lines] == [
        "Tempo",
        "Long",
        "—",
        "Zeta",
    ]


def test_zero_is_zero_and_absent_is_a_dash() -> None:
    lines = _render(CASES[0].data).split("\n")
    zeros, absent = lines[3], lines[4]
    assert zeros == (
        "| 2026-03-02 | 2026-03-02 18:05 | Long | 0 | 0:00:00 | 0:00 | 0"
        " | false | 0:00 | 0 | 0.0 |"
    )
    assert absent == "| — | — | — | — | — | — | — | — | — | — | — |"
    assert "None" not in "\n".join(lines)


def test_duration_headers_and_cells_agree() -> None:
    columns = (
        column("under", ValueKind.DURATION),
        column("mixed", ValueKind.DURATION),
        column("under_s", unit="s"),
        column("mixed_s", unit="s"),
        column("edge", ValueKind.DURATION),
        column("rounds_up", unit="s"),
        column("rounds_down", unit="s"),
        column("none_present", ValueKind.DURATION),
        column("neg", ValueKind.DURATION),
    )
    rows: list[tuple[Value, ...]] = [
        (
            timedelta(seconds=5),
            timedelta(seconds=90),
            1.5,
            90,
            timedelta(seconds=3599),
            3599.5,
            3599.4,
            None,
            timedelta(seconds=-30),
        ),
        (
            timedelta(seconds=3599),
            timedelta(seconds=5400),
            3599,
            5400,
            timedelta(seconds=3600),
            0,
            0,
            None,
            timedelta(seconds=-5400),
        ),
        (None, None, None, None, None, None, None, None, None),
    ]
    assert _render(chart_data(columns, rows)) == "\n".join(
        (
            "| under (m:ss) | mixed (h:mm:ss) | under (m:ss) | mixed (h:mm:ss)"
            " | edge (h:mm:ss) | rounds up (h:mm:ss) | rounds down (m:ss)"
            " | none present (m:ss) | neg (h:mm:ss) |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            "| 0:05 | 0:01:30 | 0:02 | 0:01:30 | 0:59:59 | 1:00:00 | 59:59"
            " | — | -0:00:30 |",
            "| 59:59 | 1:30:00 | 59:59 | 1:30:00 | 1:00:00 | 0:00:00 | 0:00"
            " | — | -1:30:00 |",
            "| — | — | — | — | — | — | — | — | — |",
        )
    )


def test_no_rows_form() -> None:
    assert _render(CASES[1].data) == NO_ROWS_TEXT


def test_special_characters_stay_inside_one_cell() -> None:
    text = _render(CASES[2].data)
    assert text == SPECIAL_TEXT
    lines = text.split("\n")
    assert len(lines) == 2 + len(SPECIAL_ROWS)
    assert "<b>" not in text and "\n\n" not in text


# --- the bounds ---------------------------------------------------------------


def test_100_rows_render() -> None:
    lines = _render(_single_column(100)).split("\n")
    assert len(lines) == 2 + 100
    assert lines[-1] == "| 99 |"


def test_101_rows_refuse() -> None:
    problems = problems_of(KIND, REQUEST, _single_column(101))
    assert problems == (
        ChartProblem(
            ref="t1",
            kind="table",
            code=ProblemCode.OVER_BOUND,
            message="table draws at most 100 rows; this data has 101.",
            fix="Aggregate the rows (for example by day or week) or limit them to "
            "at most 100.",
            rows=101,
        ),
    )


def test_12_columns_render_without_rows() -> None:
    columns = _wide_columns(12)
    text = _render(chart_data(columns, []))
    assert text.split("\n")[0] == "| " + " | ".join(f"c{i}" for i in range(12)) + " |"
    assert text.endswith("\n\nNo data")


def test_13_columns_refuse_at_validation_without_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _registered(monkeypatch)
    assert validate_chart(REQUEST, _wide_columns(12)) == ()
    assert validate_chart(REQUEST, _wide_columns(13)) == (
        ChartProblem(
            ref="t1",
            kind="table",
            code=ProblemCode.OVER_BOUND,
            message="table draws at most 12 columns; this data has 13.",
            fix="Select at most 12 columns in the query.",
        ),
    )


def test_13_columns_refuse_in_the_pipeline() -> None:
    problems = problems_of(KIND, REQUEST, chart_data(_wide_columns(13), []))
    assert [p.code for p in problems] == [ProblemCode.OVER_BOUND]
    assert problems[0].message == "table draws at most 12 columns; this data has 13."


# --- goldens ------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    assert_golden(golden_path("table", case.name, "md"), _render(case.data))


def test_cases_are_the_designed_four() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "no_rows",
        "special_chars",
        "at_bound",
    ]


def test_at_bound_case_sits_on_both_bounds() -> None:
    data = CASES[3].data
    assert len(data.rows) == 100
    assert len(data.columns) == 12
    assert {c.kind for c in data.columns} == set(ValueKind)


def main() -> None:
    for case in CASES:
        write_golden(golden_path("table", case.name, "md"), _render(case.data))


if __name__ == "__main__":
    main()
