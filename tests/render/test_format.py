"""Display-format and absence-rule tests (Req 13.1, 13.3).

These pin every formatter's exact output, the ``h:mm:ss`` / ``m:ss`` duration
boundary, the ``None`` -> ``None`` absence convention, and -- the
missing-data-honesty core -- that a recorded zero formats as a *genuine* value
and is never mapped to ``None`` or the in-table absence marker (Req 13.3).
``cell`` renders the marker only for ``None``.
"""

from __future__ import annotations

import pytest

from fitdocs.render.format import (
    ABSENT,
    cell,
    fmt_distance_km,
    fmt_duration,
    fmt_int,
    fmt_pace,
    fmt_speed_kmh,
)

# --- ABSENT marker ----------------------------------------------------------


def test_absent_is_the_en_dash() -> None:
    assert ABSENT == "–"  # EN DASH (U+2013), not a hyphen-minus
    assert len(ABSENT) == 1


# --- fmt_duration -----------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0:00"),
        (5, "0:05"),
        (59, "0:59"),
        (60, "1:00"),
        (65, "1:05"),
        (600, "10:00"),
        (3599, "59:59"),  # last second before the h:mm:ss boundary
        (3600, "1:00:00"),  # exactly one hour -> h:mm:ss
        (3661, "1:01:01"),
        (36000, "10:00:00"),
    ],
)
def test_fmt_duration_values(seconds: float, expected: str) -> None:
    assert fmt_duration(seconds) == expected


def test_fmt_duration_rounds_fractional_seconds() -> None:
    assert fmt_duration(65.4) == "1:05"


def test_fmt_duration_none() -> None:
    assert fmt_duration(None) is None


def test_fmt_duration_true_zero_is_genuine() -> None:
    result = fmt_duration(0)
    assert result == "0:00"
    assert result is not None and result != ABSENT


# --- fmt_pace ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("s_per_km", "expected"),
    [
        (0, "0:00 /km"),
        (65, "1:05 /km"),
        (300, "5:00 /km"),
        (305, "5:05 /km"),
    ],
)
def test_fmt_pace_values(s_per_km: float, expected: str) -> None:
    assert fmt_pace(s_per_km) == expected


def test_fmt_pace_rounds_fractional_seconds() -> None:
    assert fmt_pace(300.4) == "5:00 /km"


def test_fmt_pace_none() -> None:
    assert fmt_pace(None) is None


def test_fmt_pace_true_zero_is_genuine() -> None:
    result = fmt_pace(0)
    assert result == "0:00 /km"
    assert result is not None and result != ABSENT


# --- fmt_speed_kmh ----------------------------------------------------------


@pytest.mark.parametrize(
    ("mps", "expected"),
    [
        (0, "0.0 km/h"),
        (5.0, "18.0 km/h"),
        (8.0, "28.8 km/h"),
        (10.0, "36.0 km/h"),
    ],
)
def test_fmt_speed_kmh_values(mps: float, expected: str) -> None:
    assert fmt_speed_kmh(mps) == expected


def test_fmt_speed_kmh_none() -> None:
    assert fmt_speed_kmh(None) is None


def test_fmt_speed_kmh_true_zero_is_genuine() -> None:
    result = fmt_speed_kmh(0)
    assert result == "0.0 km/h"
    assert result is not None and result != ABSENT


# --- fmt_distance_km --------------------------------------------------------


@pytest.mark.parametrize(
    ("metres", "expected"),
    [
        (0, "0.00 km"),
        (1500, "1.50 km"),
        (5000, "5.00 km"),
        (10000, "10.00 km"),
    ],
)
def test_fmt_distance_km_values(metres: float, expected: str) -> None:
    assert fmt_distance_km(metres) == expected


def test_fmt_distance_km_none() -> None:
    assert fmt_distance_km(None) is None


def test_fmt_distance_km_true_zero_is_genuine() -> None:
    result = fmt_distance_km(0)
    assert result == "0.00 km"
    assert result is not None and result != ABSENT


# --- fmt_int ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (0, "w", "0 w"),
        (133, "bpm", "133 bpm"),
        (133.4, "bpm", "133 bpm"),
        (132.6, "bpm", "133 bpm"),
        (2000, "kcal", "2000 kcal"),
    ],
)
def test_fmt_int_values(value: float, unit: str, expected: str) -> None:
    assert fmt_int(value, unit) == expected


def test_fmt_int_none() -> None:
    assert fmt_int(None, "bpm") is None


def test_fmt_int_true_zero_is_genuine() -> None:
    result = fmt_int(0, "w")
    assert result == "0 w"
    assert result is not None and result != ABSENT


# --- cell -------------------------------------------------------------------


def test_cell_none_renders_absent_marker() -> None:
    assert cell(None) == ABSENT


@pytest.mark.parametrize("value", ["x", "0 kg", "0.00 km", ""])
def test_cell_passes_through_real_values(value: str) -> None:
    # A recorded zero has already been formatted to a genuine string; cell must
    # pass it through unchanged and never substitute the absence marker (13.3).
    assert cell(value) == value


# --- cross-formatter honesty invariants -------------------------------------


def test_none_maps_to_none_for_every_formatter() -> None:
    assert fmt_duration(None) is None
    assert fmt_pace(None) is None
    assert fmt_speed_kmh(None) is None
    assert fmt_distance_km(None) is None
    assert fmt_int(None, "w") is None


def test_true_zero_is_never_absence_for_any_formatter() -> None:
    for result in (
        fmt_duration(0),
        fmt_pace(0),
        fmt_speed_kmh(0),
        fmt_distance_km(0),
        fmt_int(0, "w"),
    ):
        assert result is not None
        assert result != ABSENT
        # And, wrapped for a table cell, a true zero stays a genuine value.
        assert cell(result) != ABSENT
