"""Placeholder values from a page (publish-core Req 5.1-5.5)."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping

import pytest

from fitdocs.publish.template import Placeholder, parse_template
from fitdocs.publish.values import (
    KM_PER_MILE,
    PLACEHOLDERS,
    format_duration,
    page_values,
)
from fitdocs.render.format import fmt_duration

EXPECTED_NAMES = (
    "title",
    "sport",
    "date",
    "start_time",
    "distance_km",
    "distance_mi",
    "moving_time",
    "elapsed_time",
    "pace_per_km",
    "pace_per_mi",
    "speed_kmh",
    "avg_hr_bpm",
    "avg_power_w",
    "elevation_gain_m",
    "calories_kcal",
    "load_value",
    "load_methodology",
)


# ------------------------------------------------------------ page builders


def run_page(**changes: object) -> dict[str, object]:
    """A run page whose figures are pairwise distinct; ``changes`` override and
    a ``None`` change removes the key."""
    page: dict[str, object] = {
        "title": "Morning Run",
        "sport": "Run",
        "modality": "run",
        "date": "2026-03-04",
        "start_time": "2026-03-04T07:05:00+01:00",
        "distance_km": 12.5,
        "moving_time": "58:20",
        "source_elapsed_s": 3725.0,
        "avg_hr_bpm": 148.6,
        "avg_power_w": 231.4,
        "elevation_gain_m": 87.6,
        "calories_kcal": 811.4,
        "load_value": 61.7,
        "load_methodology": "TRIMP",
    }
    for key, value in changes.items():
        if value is None:
            del page[key]
        else:
            page[key] = value
    return page


def ride_page(**changes: object) -> dict[str, object]:
    return run_page(modality="bike", sport="Ride", **changes)


def value_of(name: str, page: Mapping[str, object]) -> str | None:
    return page_values(page)[name]


# ------------------------------------------------------------------- names


def test_the_names_are_the_designs_seventeen_in_order() -> None:
    assert PLACEHOLDERS == EXPECTED_NAMES
    assert len(PLACEHOLDERS) == 17


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_each_name_follows_the_grammar_rule_and_parses_as_a_placeholder(
    name: str,
) -> None:
    assert re.fullmatch(r"[a-z][a-z0-9_]*", name)
    parsed = parse_template("{" + name + "}", names=PLACEHOLDERS)
    assert parsed.parts == (Placeholder(name),)


def test_page_values_has_every_name_in_order_even_for_an_empty_page() -> None:
    assert tuple(page_values({})) == EXPECTED_NAMES
    assert tuple(page_values(run_page())) == EXPECTED_NAMES


def test_an_empty_page_has_no_value_for_any_name() -> None:
    assert page_values({}) == dict.fromkeys(EXPECTED_NAMES)


def test_the_miles_constant_is_the_international_mile() -> None:
    assert KM_PER_MILE == 1.609344


# ------------------------------------------------------------ the full page


def test_a_run_page_renders_every_value_in_its_fixed_format() -> None:
    assert page_values(run_page()) == {
        "title": "Morning Run",
        "sport": "Run",
        "date": "2026-03-04",
        "start_time": "07:05",
        "distance_km": "12.50",
        "distance_mi": "7.77",
        "moving_time": "58:20",
        "elapsed_time": "1:02:05",
        "pace_per_km": "4:40",
        "pace_per_mi": "7:31",
        "speed_kmh": None,
        "avg_hr_bpm": "149",
        "avg_power_w": "231",
        "elevation_gain_m": "88",
        "calories_kcal": "811",
        "load_value": "62",
        "load_methodology": "TRIMP",
    }


def test_a_ride_page_has_speed_and_no_pace() -> None:
    values = page_values(ride_page())
    assert values["speed_kmh"] == "12.9"
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None
    assert values["distance_km"] == "12.50"
    assert values["moving_time"] == "58:20"


@pytest.mark.parametrize("modality", [None, "swim", "RUN", "Run", "", " run", "walk"])
def test_pace_and_speed_need_the_run_or_bike_modality_exactly(
    modality: object,
) -> None:
    page = run_page(modality=modality)
    if modality is not None:
        assert page["modality"] == modality
    values = page_values(page)
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None
    assert values["speed_kmh"] is None


@pytest.mark.parametrize("modality", [True, 1, ["run"], {"run": 1}])
def test_a_non_string_modality_gives_no_pace_and_no_speed(modality: object) -> None:
    values = page_values(run_page(modality=modality))
    assert values["pace_per_km"] is None
    assert values["speed_kmh"] is None


def test_only_the_athletes_own_text_keys_never_feed_a_value() -> None:
    page: dict[str, object] = {
        "effort": "tempo",
        "publish": ["intervals"],
        "notes": "10 km in 40:00, 150 bpm",
        "post": "Great run",
        "description": "5 km",
    }
    assert page_values(page) == dict.fromkeys(EXPECTED_NAMES)
    assert page_values({**run_page(), **page}) == page_values(run_page())


# ------------------------------------------------------------------- title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Morning Run", "Morning Run"),
        ("  padded  ", "  padded  "),
        ("Run – hills é", "Run – hills é"),
        ("a\nb", None),
        ("a\tb", None),
        ("a\rb", None),
        ("a\x00b", None),
        ("a\x7fb", None),
        ("Morning\u00a0Run", "Morning\u00a0Run"),
        ("\U0001f3c3\u200d\u2642\ufe0f Run", "\U0001f3c3\u200d\u2642\ufe0f Run"),
        ("soft\u00adhyphen", "soft\u00adhyphen"),
        ("a\x85b", None),
        ("a\x9fb", None),
        ("a\u2028b", None),
        ("a\u2029b", None),
        ("", None),
        ("   ", None),
        (42, None),
        (True, None),
        (["x"], None),
    ],
)
def test_title(title: object, expected: str | None) -> None:
    assert value_of("title", run_page(title=title)) == expected


def test_title_absent() -> None:
    assert value_of("title", run_page(title=None)) is None


# ------------------------------------------------------------------- sport


@pytest.mark.parametrize(
    ("sport", "expected"),
    [
        ("Run", "Run"),
        ("Trail Run", "Trail Run"),
        ("  Trail Run  ", "  Trail Run  "),
        ("Ru\nn", None),
        ("Run\t", None),
        ("Trail\u00a0Run", "Trail\u00a0Run"),
        ("Ru\x85n", None),
        ("Ru\x9fn", None),
        ("Ru\u2028n", None),
        ("Ru\u2029n", None),
        ("", None),
        (7, None),
        (True, None),
        (["Run"], None),
    ],
)
def test_sport(sport: object, expected: str | None) -> None:
    assert value_of("sport", run_page(sport=sport)) == expected


def test_sport_absent() -> None:
    assert value_of("sport", run_page(sport=None)) is None


# -------------------------------------------------------------------- date


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        ("2026-03-04", "2026-03-04"),
        ("2026-12-31", "2026-12-31"),
        (dt.date(2026, 3, 4), "2026-03-04"),
        ("2026-13-45", None),
        ("yesterday", None),
        ("", None),
        (20260304, None),
        (dt.datetime(2026, 3, 4, 7, 5), None),
        (True, None),
    ],
)
def test_date(date: object, expected: str | None) -> None:
    assert value_of("date", run_page(date=date)) == expected


def test_date_absent() -> None:
    assert value_of("date", run_page(date=None)) is None


# -------------------------------------------------------------- start_time


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        ("2026-03-04T07:05:00+01:00", "07:05"),
        ("2026-03-04T23:59:59-05:00", "23:59"),
        ("2026-03-04T00:00:30+09:30", "00:00"),
        ("2026-03-04T07:05:00Z", "07:05"),
        (
            dt.datetime(2026, 3, 4, 18, 42, tzinfo=dt.timezone(dt.timedelta(hours=-7))),
            "18:42",
        ),
        ("2026-03-04T07:05:00", None),
        ("2026-03-04", None),
        ("tomorrow", None),
        ("", None),
        (dt.datetime(2026, 3, 4, 7, 5), None),
        (dt.date(2026, 3, 4), None),
        (705, None),
        (True, None),
    ],
)
def test_start_time(start: object, expected: str | None) -> None:
    assert value_of("start_time", run_page(start_time=start)) == expected


def test_start_time_absent() -> None:
    assert value_of("start_time", run_page(start_time=None)) is None


# ------------------------------------------------------ distance_km and mi


@pytest.mark.parametrize(
    ("distance", "km", "mi"),
    [
        (12.5, "12.50", "7.77"),
        (1.73, "1.73", "1.07"),
        (10, "10.00", "6.21"),
        (10.004, "10.00", "6.22"),
        (0.005, "0.01", "0.00"),
        (0, "0.00", None),
        (0.0, "0.00", None),
    ],
)
def test_distance_present_and_zero(distance: object, km: str, mi: str | None) -> None:
    values = page_values(run_page(distance_km=distance))
    assert values["distance_km"] == km
    assert values["distance_mi"] == mi


@pytest.mark.parametrize(
    "distance",
    [
        None,
        True,
        False,
        "12.5",
        "",
        -1.0,
        float("nan"),
        float("inf"),
        [12.5],
        {"km": 12.5},
    ],
)
def test_distance_absent_or_malformed_has_no_km_and_no_miles(
    distance: object,
) -> None:
    page = run_page(distance_km=distance)
    if distance is not None:
        assert "distance_km" in page
    values = page_values(page)
    assert values["distance_km"] is None
    assert values["distance_mi"] is None


def test_miles_come_from_the_unrounded_kilometres() -> None:
    assert value_of("distance_mi", run_page(distance_km=10.004)) == "6.22"


# ----------------------------------------------------- moving and elapsed


@pytest.mark.parametrize(
    ("moving", "expected"),
    [
        ("58:20", "58:20"),
        ("0:00", "0:00"),
        ("0:07", "0:07"),
        ("59:59", "59:59"),
        ("1:00:00", "1:00:00"),
        ("1:02:05", "1:02:05"),
        ("12:00:09", "12:00:09"),
        ("100:00:00", "100:00:00"),
    ],
)
def test_moving_time_present_and_zero(moving: str, expected: str) -> None:
    assert value_of("moving_time", run_page(moving_time=moving)) == expected


@pytest.mark.parametrize(
    "moving",
    [None, 3500, 3500.0, True, "", "58", "58:60", "1:2:3", "aa:bb", "-1:00", [1]],
)
def test_moving_time_absent_or_malformed(moving: object) -> None:
    assert value_of("moving_time", run_page(moving_time=moving)) is None


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (3725.0, "1:02:05"),
        (3725, "1:02:05"),
        (59.4, "0:59"),
        (60, "1:00"),
        (0, "0:00"),
        (0.0, "0:00"),
        (36000, "10:00:00"),
    ],
)
def test_elapsed_time_present_and_zero(elapsed: object, expected: str) -> None:
    assert value_of("elapsed_time", run_page(source_elapsed_s=elapsed)) == expected


@pytest.mark.parametrize(
    "elapsed",
    [None, True, False, "3725", "1:02:05", -1, float("nan"), float("inf"), [5]],
)
def test_elapsed_time_absent_or_malformed(elapsed: object) -> None:
    assert value_of("elapsed_time", run_page(source_elapsed_s=elapsed)) is None


def test_elapsed_and_moving_time_are_read_independently() -> None:
    values = page_values(run_page(moving_time=None))
    assert values["moving_time"] is None
    assert values["elapsed_time"] == "1:02:05"
    values = page_values(run_page(source_elapsed_s=None))
    assert values["elapsed_time"] is None
    assert values["moving_time"] == "58:20"


# -------------------------------------------------------- the duration rule

DURATION_TABLE = [
    (0, "0:00"),
    (0.4, "0:00"),
    (0.5, "0:00"),
    (0.51, "0:01"),
    (1.5, "0:02"),
    (2.5, "0:02"),
    (9, "0:09"),
    (59, "0:59"),
    (59.4, "0:59"),
    (59.5, "1:00"),
    (60, "1:00"),
    (61, "1:01"),
    (599.5, "10:00"),
    (3599, "59:59"),
    (3599.4, "59:59"),
    (3599.5, "1:00:00"),
    (3600, "1:00:00"),
    (3661, "1:01:01"),
    (7384.6, "2:03:05"),
    (36000, "10:00:00"),
    (86399.6, "24:00:00"),
    (359999, "99:59:59"),
    (360000, "100:00:00"),
]


@pytest.mark.parametrize(("seconds", "expected"), DURATION_TABLE)
def test_format_duration_matches_the_render_layers_rule(
    seconds: float, expected: str
) -> None:
    assert format_duration(seconds) == expected
    assert format_duration(seconds) == fmt_duration(seconds)


# ------------------------------------------------------------------- pace


@pytest.mark.parametrize(
    ("moving", "distance", "per_km", "per_mi"),
    [
        ("58:20", 12.5, "4:40", "7:31"),
        ("24:58", 5.0, "5:00", "8:02"),
        ("25:00", 5.0, "5:00", "8:03"),
        ("0:07", 0.001, "116:40", "187:45"),
    ],
)
def test_run_pace(moving: str, distance: float, per_km: str, per_mi: str) -> None:
    values = page_values(run_page(moving_time=moving, distance_km=distance))
    assert values["pace_per_km"] == per_km
    assert values["pace_per_mi"] == per_mi


def test_pace_is_rounded_to_the_nearest_second_not_truncated() -> None:
    # 1498 s over 5 km is 299.6 s/km; 1497 s is 299.4 s/km
    values = page_values(run_page(moving_time="24:58", distance_km=5.0))
    assert values["pace_per_km"] == "5:00"
    values = page_values(run_page(moving_time="24:57", distance_km=5.0))
    assert values["pace_per_km"] == "4:59"


@pytest.mark.parametrize(("moving", "expected"), [("5:01", "2:30"), ("5:03", "2:32")])
def test_pace_on_an_exact_half_second_rounds_to_the_even_second(
    moving: str, expected: str
) -> None:
    # 301 s over 2 km is exactly 150.5 s/km; 303 s is exactly 151.5 s/km
    values = page_values(run_page(moving_time=moving, distance_km=2.0))
    assert values["pace_per_km"] == expected


def test_pace_is_minutes_and_seconds_even_past_an_hour() -> None:
    values = page_values(run_page(moving_time="0:07", distance_km=0.001))
    assert values["pace_per_km"] == "116:40"


def test_pace_uses_moving_time_not_elapsed_time() -> None:
    page = run_page(source_elapsed_s=7000.0)
    assert page_values(page)["pace_per_km"] == "4:40"


@pytest.mark.parametrize(
    "changes",
    [
        {"moving_time": None},
        {"distance_km": None},
        {"moving_time": "0:00"},
        {"distance_km": 0},
        {"distance_km": 0.0},
        {"moving_time": "0:00", "distance_km": 0},
        {"moving_time": True},
        {"distance_km": True},
        {"distance_km": "12.5"},
        {"moving_time": "bad"},
    ],
)
def test_run_pace_needs_present_positive_inputs(changes: dict[str, object]) -> None:
    page = run_page(**changes)
    values = page_values(page)
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None


def test_a_recorded_zero_distance_renders_zero_but_derives_nothing() -> None:
    values = page_values(run_page(distance_km=0))
    assert values["distance_km"] == "0.00"
    assert values["distance_mi"] is None
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None


def test_a_recorded_zero_moving_time_renders_zero_but_derives_nothing() -> None:
    values = page_values(run_page(moving_time="0:00"))
    assert values["moving_time"] == "0:00"
    assert values["pace_per_km"] is None


def test_pace_that_cannot_be_finite_is_no_value() -> None:
    tiny = run_page(distance_km=1e-320)
    values = page_values(tiny)
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None
    smallest = page_values(run_page(distance_km=5e-324))
    assert smallest["distance_mi"] == "0.00"
    assert smallest["pace_per_mi"] is None
    assert smallest["pace_per_km"] is None


# ------------------------------------------------------------------ speed


@pytest.mark.parametrize(
    ("moving", "distance", "expected"),
    [
        ("58:20", 12.5, "12.9"),
        ("1:00:00", 30.0, "30.0"),
        ("30:00", 15.04, "30.1"),
        ("30:00", 15.06, "30.1"),
        ("0:01", 0.01, "36.0"),
    ],
)
def test_ride_speed(moving: str, distance: float, expected: str) -> None:
    assert value_of(
        "speed_kmh", ride_page(moving_time=moving, distance_km=distance)
    ) == (expected)


def test_speed_is_rounded_to_one_decimal_not_truncated() -> None:
    assert value_of(
        "speed_kmh", ride_page(moving_time="1:00:00", distance_km=29.96)
    ) == ("30.0")


def test_speed_uses_moving_time_not_elapsed_time() -> None:
    assert value_of("speed_kmh", ride_page(source_elapsed_s=9999.0)) == "12.9"


@pytest.mark.parametrize(
    "changes",
    [
        {"moving_time": None},
        {"distance_km": None},
        {"moving_time": "0:00"},
        {"distance_km": 0},
        {"distance_km": 0.0},
        {"moving_time": True},
        {"distance_km": False},
        {"distance_km": "30"},
        {"moving_time": "x"},
    ],
)
def test_ride_speed_needs_present_positive_inputs(changes: dict[str, object]) -> None:
    assert value_of("speed_kmh", ride_page(**changes)) is None


def test_speed_that_cannot_be_finite_is_no_value() -> None:
    assert (
        value_of("speed_kmh", ride_page(moving_time="0:01", distance_km=1e308)) is None
    )


# ------------------------------------------------- whole-number measures

WHOLE_NUMBERS = [
    ("avg_hr_bpm", "avg_hr_bpm"),
    ("avg_power_w", "avg_power_w"),
    ("calories_kcal", "calories_kcal"),
]


@pytest.mark.parametrize(("name", "key"), WHOLE_NUMBERS)
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (148, "148"),
        (148.6, "149"),
        (148.4, "148"),
        (0, "0"),
        (0.0, "0"),
        (1500, "1500"),
    ],
)
def test_integer_measures_present_and_zero(
    name: str, key: str, raw: object, expected: str
) -> None:
    assert value_of(name, run_page(**{key: raw})) == expected


@pytest.mark.parametrize(("name", "key"), WHOLE_NUMBERS + [("elevation_gain_m",) * 2])
@pytest.mark.parametrize(
    "raw",
    [None, True, False, "148", "", -5, float("nan"), float("inf"), [148], {"v": 1}],
)
def test_measures_absent_or_malformed(name: str, key: str, raw: object) -> None:
    page = run_page(**{key: raw})
    if raw is not None:
        assert page[key] is raw
    assert value_of(name, page) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (87.6, "88"),
        (87.4, "87"),
        (87, "87"),
        (0, "0"),
        (0.0, "0"),
        (0.4, "0"),
        (0.5, "0"),
        (86.5, "86"),
        (1234, "1234"),
    ],
)
def test_elevation_gain_present_and_zero(raw: object, expected: str) -> None:
    assert value_of("elevation_gain_m", run_page(elevation_gain_m=raw)) == expected


def test_each_measure_is_read_from_its_own_key() -> None:
    values = page_values(run_page())
    assert len({values[n] for n in ("avg_hr_bpm", "avg_power_w", "calories_kcal")}) == 3
    assert values["avg_hr_bpm"] == "149"
    assert values["avg_power_w"] == "231"
    assert values["calories_kcal"] == "811"


# ------------------------------------------------------------------- load


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (61.7, "62"),
        (61.2, "61"),
        (61, "61"),
        (0, "0"),
        (0.0, "0"),
        (-0.0, "0"),
        (0.4, "0"),
        (250.5, "250"),
    ],
)
def test_load_value_present_and_zero(raw: object, expected: str) -> None:
    values = page_values(run_page(load_value=raw))
    assert values["load_value"] == expected
    assert values["load_methodology"] == "TRIMP"


@pytest.mark.parametrize(
    "raw",
    [None, True, False, "61.7", "", -5, -0.5, float("nan"), float("inf"), [61]],
)
def test_load_value_absent_or_malformed_takes_the_methodology_with_it(
    raw: object,
) -> None:
    page = run_page(load_value=raw)
    if raw is not None:
        assert page["load_value"] is raw
    values = page_values(page)
    assert values["load_value"] is None
    assert values["load_methodology"] is None


@pytest.mark.parametrize("methodology", [None, 5, True, ["TRIMP"]])
def test_load_without_a_usable_methodology_is_no_load(methodology: object) -> None:
    values = page_values(run_page(load_methodology=methodology))
    assert values["load_value"] is None
    assert values["load_methodology"] is None


def test_load_methodology_is_verbatim() -> None:
    values = page_values(run_page(load_methodology="Run rTSS (v2)"))
    assert values["load_methodology"] == "Run rTSS (v2)"
    assert values["load_value"] == "62"


@pytest.mark.parametrize(
    "methodology", [" TRIMP ", "TR IMP", "TRIMP ", "Run\u00a0rTSS", "r\u200dTSS"]
)
def test_load_methodology_is_kept_unstripped(methodology: str) -> None:
    values = page_values(run_page(load_methodology=methodology))
    assert values["load_methodology"] == methodology
    assert values["load_value"] == "62"


@pytest.mark.parametrize(
    "methodology",
    [
        "",
        "   ",
        "\u2003",
        "TR\nIMP",
        "TR\tIMP",
        "TR\x85IMP",
        "TR\u2028IMP",
        "TR\u2029IMP",
        "TRIMP\n",
    ],
)
def test_a_methodology_that_is_blank_or_not_single_line_is_no_load(
    methodology: str,
) -> None:
    page = run_page(load_methodology=methodology)
    assert page["load_methodology"] == methodology
    assert page_values(run_page())["load_value"] == "62"
    values = page_values(page)
    assert values["load_value"] is None
    assert values["load_methodology"] is None


# ------------------------------------------------------- booleans, directly


NUMERIC_KEYS = [
    "distance_km",
    "source_elapsed_s",
    "avg_hr_bpm",
    "avg_power_w",
    "elevation_gain_m",
    "calories_kcal",
    "load_value",
]


@pytest.mark.parametrize("flag", [True, False])
def test_a_boolean_is_never_read_as_a_number(flag: bool) -> None:
    page = run_page(**dict.fromkeys(NUMERIC_KEYS, flag), moving_time=flag)
    for key in (*NUMERIC_KEYS, "moving_time"):
        assert page[key] is flag
    values = page_values(page)
    numeric_names = [
        n for n in EXPECTED_NAMES if n not in {"title", "sport", "date", "start_time"}
    ]
    assert {n: values[n] for n in numeric_names} == dict.fromkeys(numeric_names)


def test_a_missing_distance_is_never_rendered_as_zero() -> None:
    values = page_values(run_page(distance_km=None))
    assert values["distance_km"] is None
    assert values["distance_mi"] is None
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None
    assert values["moving_time"] == "58:20"


def test_pace_is_never_computed_for_a_ride_even_with_positive_inputs() -> None:
    page = ride_page()
    assert page["distance_km"] == 12.5
    assert page["moving_time"] == "58:20"
    values = page_values(page)
    assert values["pace_per_km"] is None
    assert values["pace_per_mi"] is None
    assert values["speed_kmh"] is not None


def test_speed_is_never_computed_for_a_run_even_with_positive_inputs() -> None:
    page = run_page()
    assert page["distance_km"] == 12.5
    assert page_values(page)["speed_kmh"] is None
