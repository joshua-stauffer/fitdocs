"""Chart-catalog 1.3: the appended duration labeller, and the consumed
not-drawn note and duration axis title pinned at the catalog's vectors."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs.render.charts.kit.data import ValueKind
from fitdocs.render.charts.kit.format import (
    axis_title,
    format_duration,
    format_durations,
)
from fitdocs.render.charts.kit.frame import not_drawn_note
from tests.render.charts.kit._helpers import column

# --- A1: format_durations (Req 3.6, 9.3) -------------------------------------


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((5, 3600), ("0:00:05", "1:00:00")),
        ((5, 300), ("0:05", "5:00")),
        ((90.5,), ("1:30",)),  # half to even: 90.5 -> 90
        ((91.5,), ("1:32",)),  # half to even: 91.5 -> 92
        ((-65, 30), ("-1:05", "0:30")),
        # the threshold is >= 3600 exactly (a `> 3600` rule would give 60:00)
        ((3600,), ("1:00:00",)),
        ((3599,), ("59:59",)),
        # the magnitude decides: a negative hour switches the whole sequence
        ((-3600, 30), ("-1:00:00", "0:00:30")),
        # rounding precedes the threshold, as format_duration does
        ((3599.6,), ("1:00:00",)),
        ((), ()),
    ],
)
def test_format_durations_vectors(
    values: tuple[float, ...], expected: tuple[str, ...]
) -> None:
    assert format_durations(values) == expected


def test_format_durations_agrees_with_format_duration_on_one_side() -> None:
    below = (0.0, 59.4, 61.5, -125.0, 3599.0)
    above = (3600.0, 3725.5, 7200.0, -3601.0)
    assert format_durations(below) == tuple(format_duration(v) for v in below)
    assert format_durations(above) == tuple(format_duration(v) for v in above)


def test_format_durations_returns_a_tuple_of_equal_length() -> None:
    out = format_durations([1.0, 2.0, 7200.0])
    assert isinstance(out, tuple)
    assert len(out) == 3


# --- A2: frame.not_drawn_note (Req 2.6), consumed ----------------------------


def test_not_drawn_note_vectors() -> None:
    assert not_drawn_note((("x", 0), ("y", 1))) == "Not drawn: 1 row without y."
    assert (
        not_drawn_note((("y", 2), ("x", 3)))
        == "Not drawn: 2 rows without y, 3 rows without x."
    )
    assert not_drawn_note((("x", 0),)) is None


def test_not_drawn_note_matches_a_core_golden() -> None:
    svg = (Path(__file__).parent / "golden" / "scatter" / "typical.svg").read_text()
    lines = re.findall(r"Not drawn: .*?\.(?=[ <])", svg)
    assert lines  # the visible line and the description both carry it
    assert set(lines) == {not_drawn_note((("x", 2), ("y", 1)))}


# --- A3: axis_title(hours=), consumed (Req 3.6, 9.3) -------------------------


def test_axis_title_duration_forms() -> None:
    number = column("duration_s", unit="s")
    assert axis_title(number, hours=True) == "duration (h:mm:ss)"
    assert axis_title(number, hours=False) == "duration (m:ss)"
    moving = column("moving_time", ValueKind.DURATION)
    assert axis_title(moving, hours=True) == "moving time (h:mm:ss)"
    assert axis_title(moving, hours=False) == "moving time (m:ss)"


def test_axis_title_non_duration_ignores_hours() -> None:
    km = column("distance_km", unit="km")
    assert axis_title(km, hours=True) == axis_title(km) == "distance (km)"
    assert axis_title(km, hours=False) == "distance (km)"
