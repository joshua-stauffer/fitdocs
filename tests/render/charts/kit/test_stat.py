"""The ``stat`` kind: output forms, refusals and goldens.

Regenerate the goldens with ``uv run python -m tests.render.charts.kit.test_stat``.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.stat import KIND
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    OptionValue,
    Output,
    OverBound,
)
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

KM = "km"
PRIOR = column("prior_km", unit=KM)
CURRENT = column("distance_km", unit=KM)
OTHER = column("sport", ValueKind.CATEGORY)


def _stat_data(
    value: Value,
    compare: Value,
    *,
    kind: ValueKind = ValueKind.NUMBER,
    unit: str | None = KM,
) -> ChartData:
    """Columns ``sport, prior, current``: value is not column 0, compare precedes it."""
    return chart_data(
        [
            OTHER,
            column("prior", kind, unit=unit),
            column("current", kind, unit=unit),
        ],
        [("run", compare, value)],
    )


def _text(
    value: Value,
    compare: Value,
    *,
    delta: str | None = None,
    kind: ValueKind = ValueKind.NUMBER,
    unit: str | None = KM,
    title: str = "T",
) -> str:
    options: dict[str, OptionValue] = {} if delta is None else {"delta": delta}
    request = chart_request(
        "stat",
        title=title,
        channels={"value": "current", "compare": "prior"},
        options=options,
    )
    return render_case(
        KIND, request, _stat_data(value, compare, kind=kind, unit=unit)
    ).text


def _value_only(value: Value, col: Column, title: str = "T") -> str:
    request = chart_request("stat", title=title, channels={"value": col.name})
    return render_case(KIND, request, chart_data([OTHER, col], [("run", value)])).text


# Goldens ------------------------------------------------------------------

_CASE_COLUMNS = [OTHER, PRIOR, CURRENT]
_CASE_CHANNELS = {"value": "distance_km", "compare": "prior_km"}


def _case(
    name: str,
    rows: list[tuple[Value, ...]],
    *,
    title: str = "Weekly distance",
    delta: str | None = None,
    columns: list[Column] | None = None,
    channels: dict[str, str] | None = None,
) -> Case:
    options: dict[str, OptionValue] = {} if delta is None else {"delta": delta}
    return Case(
        name,
        chart_request(
            "stat",
            title=title,
            channels=_CASE_CHANNELS if channels is None else channels,
            options=options,
        ),
        chart_data(_CASE_COLUMNS if columns is None else columns, rows),
    )


_FORM_COLUMNS = [OTHER, column("tsb_prior"), column("tsb")]

CASES: tuple[Case, ...] = (
    _case(
        "value",
        [("run", None, 25.3)],
        channels={"value": "distance_km"},
    ),
    _case("compare_absolute", [("run", 22.2, 25.3)]),
    Case(
        "compare_percent",
        chart_request(
            "stat",
            title="Form",
            channels={"value": "tsb", "compare": "tsb_prior"},
            options={"delta": "percent"},
        ),
        chart_data(_FORM_COLUMNS, [("run", -12.0, 4.5)]),
    ),
    _case("compare_both", [("run", 36.1, 39.2)], delta="both"),
    _case("absent_value", [("run", 22.2, None)]),
    _case("absent_compare", [("run", None, 25.3)]),
    _case("no_rows", []),
    _case(
        "special_chars",
        [("run", 22.2, 25.3)],
        title="Load *peak* | <b> #1",
    ),
)

EXPECTED_GOLDEN_TEXT = {
    "value": "**Weekly distance:** 25.3 km",
    "compare_absolute": "**Weekly distance:** 25.3 km (+3.1 km vs 22.2 km)",
    "compare_percent": "**Form:** 4.5 (+137.5% vs -12)",
    "compare_both": "**Weekly distance:** 39.2 km (+3.1 km, +8.6% vs 36.1 km)",
    "absent_value": "**Weekly distance:** — (— vs 22.2 km)",
    "absent_compare": "**Weekly distance:** 25.3 km (— vs —)",
    "no_rows": "**Weekly distance:** — (no data)",
    "special_chars": (
        "**Load \\*peak\\* \\| \\<b\\> \\#1:** 25.3 km (+3.1 km vs 22.2 km)"
    ),
}


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "value",
        "compare_absolute",
        "compare_percent",
        "compare_both",
        "absent_value",
        "absent_compare",
        "no_rows",
        "special_chars",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "stat"
    assert rendered.output is Output.MARKDOWN
    assert_golden(golden_path("stat", case.name, "md"), rendered.text)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden_text_is_what_the_design_says(case: Case) -> None:
    assert (
        render_case(KIND, case.request, case.data).text
        == (EXPECTED_GOLDEN_TEXT[case.name])
    )


def test_no_stale_goldens() -> None:
    directory = golden_path("stat", "x", "md").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.md" for case in CASES)


def main() -> None:
    for case in CASES:
        text = render_case(KIND, case.request, case.data).text
        write_golden(golden_path("stat", case.name, "md"), text)


# Declaration --------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "stat"
    assert KIND.description == "One headline value with its unit and an optional change"
    assert KIND.output is Output.MARKDOWN
    assert KIND.channels == (
        ChannelSpec(
            "value",
            (
                ValueKind.NUMBER,
                ValueKind.DATE,
                ValueKind.DATETIME,
                ValueKind.DURATION,
                ValueKind.CATEGORY,
                ValueKind.BOOLEAN,
            ),
            True,
            "The headline value.",
        ),
        ChannelSpec(
            "compare",
            (ValueKind.NUMBER, ValueKind.DURATION),
            False,
            "The value to compare against, of the same kind and unit.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "delta",
            OptionType.CHOICE,
            "How the change from the comparison is shown.",
            "absolute",
            choices=("absolute", "percent", "both"),
        ),
    )
    assert KIND.bound == MarkBound(
        1, "rows", OverBound.REFUSE, "A stat shows one row; more are refused."
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is False
    assert [f.name for f in dataclasses.fields(KIND)][:3] == [
        "name",
        "description",
        "output",
    ]


# Output forms -------------------------------------------------------------


def test_value_only_has_no_comparison_clause() -> None:
    assert _value_only(25.3, CURRENT, "Distance") == "**Distance:** 25.3 km"


def test_default_delta_is_absolute() -> None:
    assert _text(25.3, 22.2) == "**T:** 25.3 km (+3.1 km vs 22.2 km)"
    assert _text(25.3, 22.2, delta="absolute") == _text(25.3, 22.2)
    assert _text(25.3, 22.2, delta="percent") == "**T:** 25.3 km (+14.0% vs 22.2 km)"


def test_percent_and_both() -> None:
    assert _text(39.2, 36.1, delta="percent") == "**T:** 39.2 km (+8.6% vs 36.1 km)"
    assert _text(39.2, 36.1, delta="both") == (
        "**T:** 39.2 km (+3.1 km, +8.6% vs 36.1 km)"
    )


def test_decrease_has_a_minus_sign() -> None:
    assert _text(22.2, 25.3) == "**T:** 22.2 km (-3.1 km vs 25.3 km)"
    assert _text(22.2, 25.3, delta="percent") == "**T:** 22.2 km (-12.3% vs 25.3 km)"


def test_equal_comparison_is_signed_plus_minus() -> None:
    assert _text(25.3, 25.3) == "**T:** 25.3 km (±0.0 km vs 25.3 km)"
    assert _text(25.3, 25.3, delta="percent") == "**T:** 25.3 km (±0.0% vs 25.3 km)"
    assert _text(25.3, 25.3, delta="both") == (
        "**T:** 25.3 km (±0.0 km, ±0.0% vs 25.3 km)"
    )


def test_percentage_change_is_over_the_magnitude_of_the_comparison() -> None:
    assert _text(4.5, -12.0, kind=ValueKind.NUMBER, unit=None, delta="percent") == (
        "**T:** 4.5 (+137.5% vs -12)"
    )
    assert _text(-18.0, -12.0, unit=None, delta="percent") == (
        "**T:** -18 (-50.0% vs -12)"
    )


def test_zero_comparison_has_no_percentage() -> None:
    assert _text(3.0, 0.0) == "**T:** 3.0 km (+3.0 km vs 0.0 km)"
    assert _text(3.0, 0.0, delta="percent") == "**T:** 3.0 km (— vs 0.0 km)"
    assert _text(3.0, 0.0, delta="both") == "**T:** 3.0 km (+3.0 km, — vs 0.0 km)"
    assert _text(0.0, 0.0, delta="percent") == "**T:** 0.0 km (— vs 0.0 km)"


def test_zero_value_is_a_value_not_absent() -> None:
    assert _value_only(0.0, CURRENT) == "**T:** 0.0 km"
    assert _value_only(0, column("count")) == "**T:** 0"
    assert _text(0.0, 4.0) == "**T:** 0.0 km (-4.0 km vs 4.0 km)"
    assert _text(0.0, 4.0, delta="percent") == "**T:** 0.0 km (-100.0% vs 4.0 km)"


def test_zero_comparison_with_absent_value_is_still_shown() -> None:
    assert _text(None, 0.0) == "**T:** — (— vs 0.0 km)"


def test_absent_forms() -> None:
    assert _value_only(None, CURRENT) == "**T:** —"
    assert _text(None, 22.2) == "**T:** — (— vs 22.2 km)"
    assert _text(25.3, None) == "**T:** 25.3 km (— vs —)"
    assert _text(None, None) == "**T:** — (— vs —)"
    for mode in ("percent", "both"):
        assert _text(None, 22.2, delta=mode) == "**T:** — (— vs 22.2 km)"
        assert _text(25.3, None, delta=mode) == "**T:** 25.3 km (— vs —)"


def test_no_rows_shows_no_comparison() -> None:
    request = chart_request(
        "stat", title="T", channels={"value": "current", "compare": "prior"}
    )
    data = chart_data([OTHER, column("prior", unit=KM), column("current", unit=KM)], [])
    assert render_case(KIND, request, data).text == "**T:** — (no data)"
    both = chart_request(
        "stat",
        title="T",
        channels={"value": "current", "compare": "prior"},
        options={"delta": "both"},
    )
    assert render_case(KIND, both, data).text == "**T:** — (no data)"


def test_percent_unit_difference_is_in_percentage_points() -> None:
    assert _text(62.5, 58.0, unit="pct") == "**T:** 62.5% (+4.5 pp vs 58.0%)"
    assert _text(62.5, 58.0, unit="pct", delta="both") == (
        "**T:** 62.5% (+4.5 pp, +7.8% vs 58.0%)"
    )


def test_duration_value_and_delta() -> None:
    long, short = timedelta(seconds=3907), timedelta(seconds=3480)
    assert _text(long, short, kind=ValueKind.DURATION, unit=None) == (
        "**T:** 1:05:07 (+7:07 vs 58:00)"
    )
    assert _text(short, long, kind=ValueKind.DURATION, unit=None, delta="both") == (
        "**T:** 58:00 (-7:07, -10.9% vs 1:05:07)"
    )
    assert _text(long, short, kind=ValueKind.DURATION, unit=None, delta="percent") == (
        "**T:** 1:05:07 (+12.3% vs 58:00)"
    )


def test_duration_unit_number_and_pace() -> None:
    assert _text(3907, 3480, unit="s") == "**T:** 1:05:07 (+7:07 vs 58:00)"
    assert _text(300, 310, unit="s_per_km") == "**T:** 5:00 /km (-0:10 /km vs 5:10 /km)"
    assert _text(300, 310, unit="s_per_km", delta="percent") == (
        "**T:** 5:00 /km (-3.2% vs 5:10 /km)"
    )


def test_unitless_integers_and_decimals() -> None:
    assert _text(7, 4, unit=None) == "**T:** 7 (+3 vs 4)"
    assert _text(Decimal("25.3"), Decimal("22.2")) == (
        "**T:** 25.3 km (+3.1 km vs 22.2 km)"
    )


def test_other_value_kinds_are_formatted_by_the_column() -> None:
    cases: list[tuple[Value, ValueKind, str | None, str]] = [
        ("Base *block* | 2", ValueKind.CATEGORY, None, "Base \\*block\\* \\| 2"),
        (date(2026, 10, 12), ValueKind.DATE, None, "2026-10-12"),
        (
            datetime(2026, 10, 12, 6, 30),
            ValueKind.DATETIME,
            "utc",
            "2026-10-12 06:30 UTC",
        ),
        (False, ValueKind.BOOLEAN, None, "false"),
        (True, ValueKind.BOOLEAN, None, "true"),
        (None, ValueKind.CATEGORY, None, "—"),
    ]
    for value, kind, unit, shown in cases:
        col = column("v", kind, unit=unit)
        assert _value_only(value, col) == f"**T:** {shown}"


def test_title_specials_are_escaped_and_cleaned() -> None:
    assert _value_only(1, column("v"), "A*b|c<d#e") == "**A\\*b\\|c\\<d\\#e:** 1"
    assert _value_only(1, column("v"), "Two\nlines") == "**Two lines:** 1"


# Refusals -----------------------------------------------------------------


def _refusal(value_col: Column, compare_col: Column) -> tuple[ChartProblem, ...]:
    request = chart_request(
        "stat",
        ref="s7",
        channels={"value": value_col.name, "compare": compare_col.name},
    )
    data = chart_data([OTHER, compare_col, value_col], [("run", None, None)])
    return problems_of(KIND, request, data)


@pytest.mark.parametrize(
    ("value_col", "compare_col"),
    [
        (column("v", ValueKind.CATEGORY), column("c")),
        (column("v", ValueKind.DATE), column("c")),
        (column("v", ValueKind.DATETIME), column("c", ValueKind.DURATION)),
        (column("v", ValueKind.BOOLEAN), column("c")),
        (column("v", ValueKind.DURATION), column("c")),
        (column("v"), column("c", ValueKind.DURATION)),
    ],
)
def test_compare_of_another_kind_is_channel_kind(
    value_col: Column, compare_col: Column
) -> None:
    assert _refusal(value_col, compare_col) == (
        ChartProblem(
            ref="s7",
            kind="stat",
            code=ProblemCode.CHANNEL_KIND,
            message=(
                "Channel 'compare' must be the same kind as channel 'value', but "
                f"column '{value_col.name}' is {value_col.kind.value} and column "
                f"'{compare_col.name}' is {compare_col.kind.value}."
            ),
            fix=(
                "Bind 'value' and 'compare' to columns that are both number or "
                "both duration."
            ),
            channel="compare",
            column=compare_col.name,
        ),
    )


def test_channel_kind_lists_same_kind_columns_as_accepted() -> None:
    request = chart_request("stat", ref="s7", channels={"value": "v", "compare": "c"})
    data = chart_data(
        [
            OTHER,
            column("alt_a", ValueKind.DURATION),
            column("c"),
            column("v", ValueKind.DURATION),
            column("alt_b", ValueKind.DURATION),
        ],
        [("run", None, None, None, None)],
    )
    (problem,) = problems_of(KIND, request, data)
    assert problem.code is ProblemCode.CHANNEL_KIND
    assert problem.accepted == ("alt_a", "alt_b")


def test_compare_of_another_unit_is_unit_mismatch() -> None:
    value_col, compare_col = column("v", unit="km"), column("c", unit="m")
    assert _refusal(value_col, compare_col) == (
        ChartProblem(
            ref="s7",
            kind="stat",
            code=ProblemCode.UNIT_MISMATCH,
            message=(
                "Channel 'compare' must have the unit of channel 'value', but "
                "column 'v' has unit 'km' and column 'c' has unit 'm'."
            ),
            fix="Bind 'compare' to a column with the same unit as 'value'.",
            channel="compare",
            column="c",
        ),
    )


def test_a_missing_unit_on_one_side_is_unit_mismatch() -> None:
    (with_none,) = _refusal(column("v", unit="km"), column("c"))
    assert with_none.code is ProblemCode.UNIT_MISMATCH
    assert with_none.message == (
        "Channel 'compare' must have the unit of channel 'value', but "
        "column 'v' has unit 'km' and column 'c' has no unit."
    )
    (other_way,) = _refusal(column("v"), column("c", unit="km"))
    assert other_way.code is ProblemCode.UNIT_MISMATCH
    assert other_way.message == (
        "Channel 'compare' must have the unit of channel 'value', but "
        "column 'v' has no unit and column 'c' has unit 'km'."
    )


def test_unit_mismatch_accepts_columns_of_the_same_kind_and_unit() -> None:
    request = chart_request("stat", ref="s7", channels={"value": "v", "compare": "c"})
    data = chart_data(
        [
            OTHER,
            column("alt_m", unit="m"),
            column("alt_km", unit="km"),
            column("c", unit="m"),
            column("v", unit="km"),
            column("alt_km2", unit="km"),
        ],
        [("run", None, None, None, None, None)],
    )
    (problem,) = problems_of(KIND, request, data)
    assert problem.code is ProblemCode.UNIT_MISMATCH
    assert problem.accepted == ("alt_km", "alt_km2")


def test_kind_mismatch_reports_no_unit_mismatch() -> None:
    codes = [
        p.code
        for p in _refusal(column("v", unit="km"), column("c", ValueKind.DURATION))
    ]
    assert codes == [ProblemCode.CHANNEL_KIND]


def test_matching_kind_and_unit_is_accepted() -> None:
    assert _text(2.0, 1.0, unit="m") == "**T:** 2 m (+1 m vs 1 m)"
    assert _text(None, None, unit=None) == "**T:** — (— vs —)"


def test_no_compare_means_no_pairing_rules() -> None:
    col = column("v", ValueKind.CATEGORY)
    assert _value_only("x", col) == "**T:** x"


def _rows(count: int) -> ChartData:
    return chart_data([OTHER, column("v")], [("run", float(i)) for i in range(count)])


def test_two_rows_refuse_and_one_row_renders() -> None:
    request = chart_request("stat", ref="s7", channels={"value": "v"})
    assert render_case(KIND, request, _rows(1)).text == "**Title:** 0"
    expected = ChartProblem(
        ref="s7",
        kind="stat",
        code=ProblemCode.OVER_BOUND,
        message="stat draws at most 1 row; this data has 2.",
        fix=(
            "Aggregate the rows to one (for example with a SQL aggregate) or "
            "limit them to one."
        ),
        rows=2,
    )
    assert problems_of(KIND, request, _rows(2)) == (expected,)
    assert problems_of(KIND, request, _rows(5)) == (
        dataclasses.replace(
            expected,
            message="stat draws at most 1 row; this data has 5.",
            rows=5,
        ),
    )


if __name__ == "__main__":
    main()
