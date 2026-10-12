"""Tests for the kit's formatter (chart-kit Req 1.6, 2.4-2.8, 9.8)."""

from __future__ import annotations

import importlib.util
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fitdocs.render.charts.kit import format as fmt
from fitdocs.render.charts.kit.data import ValueKind
from fitdocs.render.charts.kit.format import (
    ABSENT,
    ELLIPSIS,
    axis_title,
    clean_text,
    display_label,
    escape_markdown,
    format_delta,
    format_duration,
    format_number_tick,
    format_pace,
    format_value,
)
from fitdocs.units import unit_named
from tests.render.charts.kit._helpers import column

# --- constants ---------------------------------------------------------------


def test_constants_are_the_exact_code_points() -> None:
    assert ABSENT == "—"
    assert ord(ABSENT) == 0x2014
    assert ELLIPSIS == "…"


# --- display_label (1.6) -----------------------------------------------------


def test_display_label_strips_the_unit_suffix_and_spaces_underscores() -> None:
    assert display_label(column("avg_speed_mps", unit="mps")) == "avg speed"
    assert display_label(column("max_heart_rate_bpm", unit="bpm")) == "max heart rate"


def test_display_label_explicit_label_wins() -> None:
    col = column("avg_speed_mps", unit="mps", label="Speed_x")
    assert display_label(col) == "Speed_x"


def test_display_label_keeps_full_text_without_the_suffix() -> None:
    # unit names a token whose suffix the name does not end with
    assert display_label(column("avg_speed", unit="mps")) == "avg speed"
    assert display_label(column("avg_speed_km", unit="mps")) == "avg speed km"
    # no unit: a suffix-looking tail is part of the name
    assert display_label(column("avg_speed_mps")) == "avg speed mps"
    # token not in the vocabulary
    assert display_label(column("avg_speed_mps", unit="zzz")) == "avg speed mps"


def test_display_label_strips_only_the_declared_unit_suffix() -> None:
    # the name ends with `_km`, but the column declares `m`: nothing is stripped
    assert display_label(column("ride_km", unit="m")) == "ride km"
    # the declared unit's suffix is removed once, from the end only
    assert display_label(column("m_split_m", unit="m")) == "m split"
    assert display_label(column("lap_m_best_m", unit="m")) == "lap m best"


# --- axis_title (2.7) --------------------------------------------------------


def test_axis_title_unit_symbols() -> None:
    assert axis_title(column("distance_km", unit="km")) == "distance (km)"
    assert axis_title(column("pace_s_per_km", unit="s_per_km")) == "pace (min/km)"
    assert axis_title(column("cadence_rpm", unit="rpm")) == "cadence (rpm)"
    assert axis_title(column("grade_pct", unit="pct")) == "grade (%)"
    assert axis_title(column("temp_c", unit="c")) == "temp (°C)"
    assert axis_title(column("elapsed", unit=None)) == "elapsed"


def test_axis_title_clock_units() -> None:
    dt = ValueKind.DATETIME
    assert axis_title(column("start_utc", dt, unit="utc")) == "start (UTC)"
    assert axis_title(column("start_local", dt, unit="local")) == "start (local time)"


def test_axis_title_durations_by_label_form() -> None:
    dur = ValueKind.DURATION
    assert axis_title(column("elapsed_s", unit="s")) == "elapsed (h:mm:ss)"
    assert axis_title(column("elapsed_s", unit="s"), hours=True) == "elapsed (h:mm:ss)"
    assert axis_title(column("elapsed_s", unit="s"), hours=False) == "elapsed (m:ss)"
    assert axis_title(column("moving", dur)) == "moving (h:mm:ss)"
    assert axis_title(column("moving", dur), hours=False) == "moving (m:ss)"
    # the form flag changes nothing for other units
    assert axis_title(column("distance_km", unit="km"), hours=False) == "distance (km)"


def test_axis_title_clock_date_inside_the_parentheses() -> None:
    dt = ValueKind.DATETIME
    day = date(2026, 3, 1)
    assert (
        axis_title(column("start_utc", dt, unit="utc"), clock_date=day)
        == "start (UTC, 2026-03-01)"
    )
    assert (
        axis_title(column("start_local", dt, unit="local"), clock_date=day)
        == "start (local time, 2026-03-01)"
    )
    assert axis_title(column("start", dt), clock_date=day) == "start (2026-03-01)"
    assert axis_title(column("start_utc", dt, unit="utc")) == "start (UTC)"


def test_axis_title_uses_the_explicit_label() -> None:
    col = column("distance_km", unit="km", label="Dist")
    assert axis_title(col) == "Dist (km)"


# --- format_value: numbers ---------------------------------------------------


def test_int_has_no_decimals_in_every_quantity_unit() -> None:
    assert format_value(150, column("hr_bpm", unit="bpm"), with_unit=False) == "150"
    assert format_value(150, column("hr_bpm", unit="bpm"), with_unit=True) == "150 bpm"
    assert format_value(12, column("d_km", unit="km"), with_unit=True) == "12 km"
    assert format_value(0, column("d_km", unit="km"), with_unit=True) == "0 km"
    assert format_value(12, column("n"), with_unit=True) == "12"
    assert format_value(3, column("g_pct", unit="pct"), with_unit=True) == "3%"
    assert format_value(1234567, column("n"), with_unit=False) == "1234567"
    assert format_value(-7, column("n"), with_unit=False) == "-7"


def test_float_uses_the_units_decimals() -> None:
    km = column("d_km", unit="km")
    assert format_value(12.34, km, with_unit=False) == "12.3"
    assert format_value(12.0, km, with_unit=False) == "12.0"
    assert format_value(0.0, km, with_unit=False) == "0.0"
    assert format_value(12.34, km, with_unit=True) == "12.3 km"
    mps = column("v_mps", unit="mps")
    assert format_value(4.5, mps, with_unit=True) == "4.50 m/s"
    assert format_value(4.567, mps, with_unit=False) == "4.57"
    bpm = column("hr_bpm", unit="bpm")
    assert format_value(150.6, bpm, with_unit=True) == "151 bpm"
    kn = column("k_kn_m", unit="kn_m")
    assert format_value(2.34, kn, with_unit=True) == "2.3 kN/m"
    bw = column("load_bw", unit="bw")
    assert format_value(1.5, bw, with_unit=True) == "1.50 BW"
    w = column("p_w", unit="w")
    assert format_value(250.4, w, with_unit=True) == "250 W"


def test_decimal_values_use_the_same_rules() -> None:
    km = column("d_km", unit="km")
    assert format_value(Decimal("12.34"), km, with_unit=True) == "12.3 km"
    assert format_value(Decimal("12"), km, with_unit=True) == "12.0 km"
    assert format_value(Decimal("-0.04"), km, with_unit=False) == "0.0"
    assert format_value(Decimal("0.830"), column("x"), with_unit=False) == "0.83"
    assert format_value(Decimal("3.00"), column("x"), with_unit=False) == "3"


def test_unitless_float_trims_to_at_most_two_decimals() -> None:
    x = column("x")
    assert format_value(0.83, x, with_unit=False) == "0.83"
    assert format_value(54.12, x, with_unit=False) == "54.12"
    assert format_value(3.0, x, with_unit=True) == "3"
    assert format_value(3.1, x, with_unit=False) == "3.1"
    assert format_value(3.14159, x, with_unit=False) == "3.14"
    assert format_value(0.0, x, with_unit=False) == "0"
    assert format_value(100.0, x, with_unit=False) == "100"
    assert format_value(1234.5, x, with_unit=False) == "1234.5"


def test_unknown_unit_token_formats_like_no_unit() -> None:
    x = column("x", unit="zzz")
    assert format_value(3.1, x, with_unit=True) == "3.1"
    assert format_value(3.0, x, with_unit=True) == "3"


def test_negative_zero_is_normalised() -> None:
    x = column("x")
    km = column("d_km", unit="km")
    pct = column("g_pct", unit="pct")
    assert format_value(-0.0, x, with_unit=False) == "0"
    assert format_value(-0.001, x, with_unit=False) == "0"
    assert format_value(-0.0, km, with_unit=True) == "0.0 km"
    assert format_value(-0.04, km, with_unit=False) == "0.0"
    assert format_value(-0.04, pct, with_unit=True) == "0.0%"
    # a genuine negative keeps its sign
    assert format_value(-0.06, km, with_unit=False) == "-0.1"
    assert format_value(-2.5, x, with_unit=False) == "-2.5"


def test_percent_is_unspaced() -> None:
    pct = column("g_pct", unit="pct")
    assert format_value(3.2, pct, with_unit=True) == "3.2%"
    assert format_value(3.2, pct, with_unit=False) == "3.2"
    assert format_value(0.0, pct, with_unit=True) == "0.0%"


def test_degrees_are_unspaced_and_celsius_spaced() -> None:
    assert format_value(45.0, column("a_deg", unit="deg"), with_unit=True) == "45.0°"
    assert format_value(45.0, column("a_deg", unit="deg"), with_unit=False) == "45.0"
    assert format_value(21.5, column("t_c", unit="c"), with_unit=True) == "21.5 °C"
    assert format_value(21.5, column("t_c", unit="c"), with_unit=False) == "21.5"


def test_mps_values_stay_metres_per_second() -> None:
    # no conversion to pace or any other unit (2.6): 3.67 m/s is not 4:32.
    mps = column("v_mps", unit="mps")
    assert format_value(3.67, mps, with_unit=True) == "3.67 m/s"
    assert format_value(3.67, mps, with_unit=False) == "3.67"
    assert format_value(0.0, mps, with_unit=True) == "0.00 m/s"


# --- format_value: durations, pace -------------------------------------------


def test_duration_values() -> None:
    s = column("t_s", unit="s")
    assert format_value(3599, s, with_unit=False) == "59:59"
    assert format_value(3600, s, with_unit=False) == "1:00:00"
    assert format_value(3600, s, with_unit=True) == "1:00:00"
    assert format_value(0, s, with_unit=True) == "0:00"
    assert format_value(59.5, s, with_unit=False) == "1:00"
    dur = column("moving", ValueKind.DURATION)
    assert format_value(timedelta(seconds=3599), dur, with_unit=True) == "59:59"
    assert format_value(timedelta(seconds=3600), dur, with_unit=True) == "1:00:00"
    assert format_value(timedelta(seconds=0), dur, with_unit=False) == "0:00"
    assert format_value(timedelta(seconds=-30), dur, with_unit=False) == "-0:30"


def test_pace_values() -> None:
    pace = column("p_s_per_km", unit="s_per_km")
    assert format_value(275, pace, with_unit=False) == "4:35"
    assert format_value(275, pace, with_unit=True) == "4:35 /km"
    assert format_value(275.4, pace, with_unit=True) == "4:35 /km"
    assert format_value(0, pace, with_unit=True) == "0:00 /km"
    assert format_value(3725, pace, with_unit=False) == "62:05"


def test_format_duration_boundaries() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(5) == "0:05"
    assert format_duration(59) == "0:59"
    assert format_duration(60) == "1:00"
    assert format_duration(3599) == "59:59"
    assert format_duration(3600) == "1:00:00"
    assert format_duration(3601) == "1:00:01"
    assert format_duration(36125) == "10:02:05"
    assert format_duration(360000) == "100:00:00"
    assert format_duration(-30) == "-0:30"
    assert format_duration(-3600) == "-1:00:00"
    assert format_duration(-3599) == "-59:59"


def test_format_duration_hours_forms() -> None:
    cases = {
        59: ("0:59", "0:00:59", "0:59"),
        3599.5: ("1:00:00", "1:00:00", "60:00"),
        5400: ("1:30:00", "1:30:00", "90:00"),
    }
    for seconds, (auto, forced_hours, forced_minutes) in cases.items():
        assert format_duration(seconds) == auto
        assert format_duration(seconds, hours=None) == auto
        assert format_duration(seconds, hours=True) == forced_hours
        assert format_duration(seconds, hours=False) == forced_minutes


def test_format_duration_hours_forms_keep_sign_and_rounding() -> None:
    assert format_duration(-90, hours=True) == "-0:01:30"
    assert format_duration(-5400, hours=False) == "-90:00"
    assert format_duration(2.5, hours=True) == "0:00:02"
    assert format_duration(3.5, hours=False) == "0:04"
    assert format_duration(0, hours=True) == "0:00:00"
    assert format_duration(360000, hours=False) == "6000:00"


def test_format_duration_rounds_half_to_even() -> None:
    # 0.5 and 2.5 round down, 1.5 and 3.5 round up; 2.7 is not truncated
    assert format_duration(0.5) == "0:00"
    assert format_duration(1.5) == "0:02"
    assert format_duration(2.5) == "0:02"
    assert format_duration(3.5) == "0:04"
    assert format_duration(2.7) == "0:03"
    assert format_duration(59.5) == "1:00"
    assert format_duration(60.5) == "1:00"
    assert format_duration(61.5) == "1:02"
    # the form is chosen after rounding
    assert format_duration(3599.5) == "1:00:00"
    assert format_duration(3599.4) == "59:59"
    # negative values round by magnitude; a rounded-away value has no sign
    assert format_duration(-2.5) == "-0:02"
    assert format_duration(-0.4) == "0:00"


def test_format_pace_boundaries() -> None:
    assert format_pace(275) == "4:35"
    assert format_pace(0) == "0:00"
    assert format_pace(59) == "0:59"
    assert format_pace(60) == "1:00"
    assert format_pace(3600) == "60:00"
    assert format_pace(3725) == "62:05"
    assert format_pace(274.5) == "4:34"
    assert format_pace(275.5) == "4:36"
    assert format_pace(274.7) == "4:35"


# --- format_value: dates, booleans, categories, absent -----------------------


def test_date_and_datetime_values() -> None:
    d = column("day", ValueKind.DATE)
    assert format_value(date(2026, 3, 1), d, with_unit=True) == "2026-03-01"
    assert format_value(date(987, 12, 31), d, with_unit=False) == "0987-12-31"
    dt = column("start_utc", ValueKind.DATETIME, unit="utc")
    stamp = datetime(2026, 3, 1, 7, 5, 59, 999999)
    assert format_value(stamp, dt, with_unit=False) == "2026-03-01 07:05"
    assert format_value(stamp, dt, with_unit=True) == "2026-03-01 07:05 UTC"
    local = column("start_local", ValueKind.DATETIME, unit="local")
    assert format_value(stamp, local, with_unit=True) == "2026-03-01 07:05"
    plain = column("start", ValueKind.DATETIME)
    assert format_value(stamp, plain, with_unit=True) == "2026-03-01 07:05"
    midnight = datetime(2026, 12, 31, 0, 0, 0)
    assert format_value(midnight, dt, with_unit=False) == "2026-12-31 00:00"


def test_boolean_values() -> None:
    b = column("flag", ValueKind.BOOLEAN)
    assert format_value(True, b, with_unit=True) == "true"
    assert format_value(False, b, with_unit=True) == "false"
    assert format_value(False, b, with_unit=False) == "false"


def test_category_values_are_cleaned_not_escaped() -> None:
    c = column("kind", ValueKind.CATEGORY)
    assert format_value("run", c, with_unit=True) == "run"
    assert format_value("a\nb\x01*c", c, with_unit=False) == "a b�*c"
    assert format_value("", c, with_unit=False) == ""


@pytest.mark.parametrize("kind", list(ValueKind))
@pytest.mark.parametrize("with_unit", [True, False])
def test_absent_is_the_em_dash_for_every_kind(kind: ValueKind, with_unit: bool) -> None:
    assert format_value(None, column("x", kind), with_unit=with_unit) == "—"
    unit = column("x_km", kind, unit="km")
    assert format_value(None, unit, with_unit=with_unit) == "—"


def test_zero_is_not_absent() -> None:
    assert format_value(0, column("x"), with_unit=False) == "0"
    assert format_value(0.0, column("x"), with_unit=False) == "0"
    assert (
        format_value(False, column("b", ValueKind.BOOLEAN), with_unit=False) == "false"
    )
    assert format_value("", column("c", ValueKind.CATEGORY), with_unit=False) == ""
    assert (
        format_value(timedelta(0), column("d", ValueKind.DURATION), with_unit=False)
        == "0:00"
    )


# --- format_number_tick ------------------------------------------------------


def test_number_tick_decimals_follow_the_step() -> None:
    assert format_number_tick(2.5, 0.5, None) == "2.5"
    assert format_number_tick(2.0, 0.5, None) == "2.0"
    assert format_number_tick(0.0, 0.5, None) == "0.0"
    assert format_number_tick(10.0, 5.0, None) == "10"
    assert format_number_tick(10, 2, None) == "10"
    assert format_number_tick(1200.0, 200.0, None) == "1200"
    assert format_number_tick(0.04, 0.02, None) == "0.04"
    assert format_number_tick(0.012, 0.002, None) == "0.012"
    assert format_number_tick(0.3, 0.1, None) == "0.3"
    assert format_number_tick(1.0, 0.1, None) == "1.0"
    assert format_number_tick(-1.5, 0.5, None) == "-1.5"
    assert format_number_tick(48000.0, 1000.0, None) == "48000"
    assert format_number_tick(0.5, 0.25, None) == "0.5"


def test_number_tick_normalises_negative_zero() -> None:
    assert format_number_tick(-0.0, 0.5, None) == "0.0"
    assert format_number_tick(-0.0, 5.0, None) == "0"


def test_number_tick_percent_appends_percent_only() -> None:
    pct = unit_named("pct")
    km = unit_named("km")
    assert pct is not None and km is not None
    assert format_number_tick(20.0, 10.0, pct) == "20%"
    assert format_number_tick(2.5, 0.5, pct) == "2.5%"
    assert format_number_tick(0.0, 5.0, pct) == "0%"
    # other units carry no symbol on a tick
    assert format_number_tick(20.0, 10.0, km) == "20"
    assert format_number_tick(2.5, 0.5, km) == "2.5"


# --- format_delta ------------------------------------------------------------


def test_delta_signs_and_units() -> None:
    km = column("d_km", unit="km")
    assert format_delta(3.1, km) == "+3.1 km"
    assert format_delta(-3.1, km) == "-3.1 km"
    assert format_delta(0.0, km) == "±0.0 km"
    assert format_delta(-0.0, km) == "±0.0 km"
    assert format_delta(0, km) == "±0 km"
    assert format_delta(3, km) == "+3 km"
    assert format_delta(-12.34, km) == "-12.3 km"


def test_delta_durations() -> None:
    dur = column("t_s", unit="s")
    assert format_delta(-30, dur) == "-0:30"
    assert format_delta(30, dur) == "+0:30"
    assert format_delta(0, dur) == "±0:00"
    assert format_delta(3725, dur) == "+1:02:05"
    kind_dur = column("moving", ValueKind.DURATION)
    assert format_delta(-90.0, kind_dur) == "-1:30"


def test_delta_percent_is_in_percentage_points() -> None:
    pct = column("g_pct", unit="pct")
    assert format_delta(1.2, pct) == "+1.2 pp"
    assert format_delta(-1.2, pct) == "-1.2 pp"
    assert format_delta(0.0, pct) == "±0.0 pp"


def test_delta_pace_and_unitless() -> None:
    pace = column("p_s_per_km", unit="s_per_km")
    assert format_delta(15, pace) == "+0:15 /km"
    assert format_delta(-15, pace) == "-0:15 /km"
    assert format_delta(0, pace) == "±0:00 /km"
    assert format_delta(3725, pace) == "+62:05 /km"
    x = column("x")
    assert format_delta(0.83, x) == "+0.83"
    assert format_delta(-0.83, x) == "-0.83"
    assert format_delta(0.0, x) == "±0"
    assert format_delta(2.0, column("a_deg", unit="deg")) == "+2.0°"


# --- clean_text --------------------------------------------------------------


def test_clean_text_replaces_forbidden_controls() -> None:
    assert clean_text("a\x01b") == "a�b"
    assert clean_text("a￾b￿c") == "a�b�c"
    assert clean_text("a\x00b") == "a�b"
    assert clean_text("a\x1fb") == "a�b"
    assert clean_text("a\x0bb\x0cc") == "a�b�c"


def test_clean_text_every_c0_control() -> None:
    for code in range(0x20):
        got = clean_text(chr(code))
        if code in (0x09, 0x0A, 0x0D):
            assert got == " ", hex(code)
        else:
            assert got == "�", hex(code)


def test_clean_text_collapses_whitespace_controls_to_a_space() -> None:
    assert clean_text("a\nb") == "a b"
    assert clean_text("a\rb") == "a b"
    assert clean_text("a\tb") == "a b"
    assert clean_text("a\r\nb") == "a  b"
    assert clean_text("a\n\nb") == "a  b"
    assert clean_text("a b") == "a b"


def test_clean_text_replaces_lone_surrogates() -> None:
    assert clean_text("a\ud800b") == "a�b"
    assert clean_text("a\udfffb") == "a�b"
    assert clean_text("\udc00") == "�"


def test_clean_text_leaves_legal_characters_alone() -> None:
    legal = "Zoë 5k – run ✓ 😀 \u007f\u0085 ퟿�￯"
    assert clean_text(legal) == legal
    assert clean_text("") == ""
    assert clean_text("plain 123.4") == "plain 123.4"


# --- escape_markdown ---------------------------------------------------------

MARKDOWN_SPECIALS = "\\`*_[]<>|&~#$"


@pytest.mark.parametrize("char", list(MARKDOWN_SPECIALS))
def test_escape_markdown_escapes_each_listed_character(char: str) -> None:
    assert escape_markdown(char) == "\\" + char
    assert escape_markdown("a" + char + "b") == "a\\" + char + "b"


def test_escape_markdown_listed_set_is_the_thirteen_characters() -> None:
    assert len(MARKDOWN_SPECIALS) == 13
    assert escape_markdown(MARKDOWN_SPECIALS) == (
        "\\\\\\`\\*\\_\\[\\]\\<\\>\\|\\&\\~\\#\\$"
    )


def test_escape_markdown_leaves_digits_and_dots_alone() -> None:
    assert escape_markdown("12.5 km 0 -3 +4 (a) {b} !c ,d :e") == (
        "12.5 km 0 -3 +4 (a) {b} !c ,d :e"
    )
    assert escape_markdown("") == ""
    assert escape_markdown("Zoë – run") == "Zoë – run"


def test_escape_markdown_does_not_double_escape() -> None:
    assert escape_markdown("a\\*") == "a\\\\\\*"
    assert escape_markdown("a|b|c") == "a\\|b\\|c"


# --- locale-free source (2.8) ------------------------------------------------

FORBIDDEN = (
    ("strftime", re.compile(r"strftime")),
    ("locale", re.compile(r"locale")),
    ("n format specifier", re.compile(r":[^{}:\"']*n\}")),
)


def forbidden_hits(source: str) -> list[str]:
    return [name for name, pattern in FORBIDDEN if pattern.search(source)]


def _format_source() -> str:
    spec = importlib.util.find_spec("fitdocs.render.charts.kit.format")
    assert spec is not None and spec.origin is not None
    return Path(spec.origin).read_text(encoding="utf-8")


def test_the_source_check_flags_what_it_forbids() -> None:
    assert forbidden_hits("d.strftime('%Y')") == ["strftime"]
    assert forbidden_hits("import locale") == ["locale"]
    assert forbidden_hits("f'{x:n}'") == ["n format specifier"]
    assert forbidden_hits("f'{x:.2n}'") == ["n format specifier"]
    assert forbidden_hits("f'{x:,n}'") == ["n format specifier"]
    assert forbidden_hits("f'{x:.2f} {y}'") == []


def test_the_source_check_reads_the_real_module() -> None:
    source = _format_source()
    assert Path(fmt.__file__).read_text(encoding="utf-8") == source
    assert "def format_duration(" in source
    assert "def escape_markdown(" in source
    assert len(source.splitlines()) > 100


def test_module_source_is_locale_free() -> None:
    assert forbidden_hits(_format_source()) == []
