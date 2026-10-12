"""Tests for kit/marks.py: mark geometry as SVG element strings (Req 8.8, 9.1, 9.2)."""

from __future__ import annotations

import pytest

from fitdocs.render.charts.kit import theme
from fitdocs.render.charts.kit.marks import (
    area_series,
    band_path,
    bar,
    line_series,
    points,
    trend,
    zero_stub,
)
from fitdocs.render.charts.kit.theme import SeriesStyle, Shape, series_style

S0 = series_style(0)
S1 = series_style(1)

# Pairwise-distinct pixel coordinates; the middle gap is None, 0.0 is a real value.
GAPPED = [(10.0, 20.5), (20.0, 0.0), (30.0, None), (40.0, 7.25), (50.0, 3.126)]


def test_gap_gives_two_polylines_and_series_zero_has_no_dash() -> None:
    assert line_series(GAPPED, S0) == [
        '<polyline points="10,20.5 20,0" fill="none" stroke="#3284d0"'
        ' stroke-width="1.8"/>',
        '<polyline points="40,7.25 50,3.13" fill="none" stroke="#3284d0"'
        ' stroke-width="1.8"/>',
    ]


def test_dash_present_for_series_one_to_seven_with_that_series_pattern() -> None:
    for i in range(1, 8):
        style = series_style(i)
        out = line_series([(1.0, 2.0), (3.0, 4.5)], style)
        assert out == [
            f'<polyline points="1,2 3,4.5" fill="none" stroke="{style.color}"'
            f' stroke-width="1.8" stroke-dasharray="{theme.DASHES[i]}"/>'
        ]
    assert "stroke-dasharray" not in line_series([(1.0, 2.0), (3.0, 4.5)], S0)[0]


def test_lone_point_between_nones_is_one_round_cap_dot_without_dash() -> None:
    pts = [(10.0, None), (20.126, 5.456), (30.0, None), (40.0, 1.0), (50.0, 2.0)]
    assert line_series(pts, S1) == [
        '<path d="M20.13 5.46h0" fill="none" stroke="#e86518" stroke-width="5"'
        ' stroke-linecap="round"/>',
        '<polyline points="40,1 50,2" fill="none" stroke="#e86518"'
        ' stroke-width="1.8" stroke-dasharray="6 3"/>',
    ]


def test_line_series_all_absent_is_empty() -> None:
    assert line_series([(1.0, None), (2.0, None)], S0) == []
    assert line_series([], S0) == []


def test_area_closes_each_segment_to_baseline_under_its_outline() -> None:
    pts = [(10.126, 20.456), (20.0, 5.0), (30.0, None), (40.0, 8.0), (50.0, 12.5)]
    assert area_series(pts, 100.456, S1, opacity="0.3") == [
        '<path d="M10.13 20.46L20 5L20 100.46L10.13 100.46Z"'
        ' fill="#e86518" fill-opacity="0.3"/>',
        '<polyline points="10.13,20.46 20,5" fill="none" stroke="#e86518"'
        ' stroke-width="1.8" stroke-dasharray="6 3"/>',
        '<path d="M40 8L50 12.5L50 100.46L40 100.46Z"'
        ' fill="#e86518" fill-opacity="0.3"/>',
        '<polyline points="40,8 50,12.5" fill="none" stroke="#e86518"'
        ' stroke-width="1.8" stroke-dasharray="6 3"/>',
    ]


def test_area_without_opacity_omits_fill_opacity_and_lone_point_is_only_a_dot() -> None:
    pts = [(10.126, 20.456), (20.0, None), (30.0, 9.0), (40.0, 0.0)]
    assert area_series(pts, -0.001, S0, opacity=None) == [
        '<path d="M10.13 20.46h0" fill="none" stroke="#3284d0" stroke-width="5"'
        ' stroke-linecap="round"/>',
        '<path d="M30 9L40 0L40 0L30 0Z" fill="#3284d0"/>',
        '<polyline points="30,9 40,0" fill="none" stroke="#3284d0"'
        ' stroke-width="1.8"/>',
    ]


def test_band_path_is_d_value_upper_forward_then_lower_backward() -> None:
    d = band_path([10.126, 20.0, 30.0], [90.0, 80.456, 70.0], [40.0, 30.0, 25.256])
    assert d == "M10.13 40L20 30L30 25.26L30 70L20 80.46L10.13 90Z"
    assert isinstance(d, str)
    assert d.startswith("M") and d.endswith("Z") and "<" not in d


def test_band_path_rejects_ragged_or_empty_input() -> None:
    with pytest.raises(ValueError):
        band_path([1.0, 2.0], [1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        band_path([], [], [])


def test_bar_positive_height_rises_from_zero_line() -> None:
    # y is the zero-line pixel; positive height extends upward from it.
    assert bar(10.126, 50.456, 6.789, 30.123, "#3284d0") == (
        '<rect x="10.13" y="20.33" width="6.79" height="30.12" fill="#3284d0"/>'
    )


def test_bar_negative_height_falls_below_the_same_zero_line() -> None:
    assert bar(10.126, 50.456, 6.789, -30.123, "#3284d0") == (
        '<rect x="10.13" y="50.46" width="6.79" height="30.12" fill="#3284d0"/>'
    )


def test_bar_negative_width_extends_left_of_x() -> None:
    assert bar(40.126, 50.456, -6.789, 30.123, "#3284d0") == (
        '<rect x="33.34" y="20.33" width="6.79" height="30.12" fill="#3284d0"/>'
    )
    assert bar(40.126, 50.456, -6.789, -30.123, "#3284d0") == (
        '<rect x="33.34" y="50.46" width="6.79" height="30.12" fill="#3284d0"/>'
    )


def test_bar_zero_height_is_a_zero_height_rect_not_absent() -> None:
    assert bar(-0.001, 20.0, 6.5, 0.0, "#3284d0") == (
        '<rect x="0" y="20" width="6.5" height="0" fill="#3284d0"/>'
    )


def test_zero_stub_is_two_px_tall_centred_on_zero_line() -> None:
    assert zero_stub(12.0, 50.0, 8.0, "#e86518") == (
        '<rect x="12" y="49" width="8" height="2" fill="#e86518"/>'
    )
    assert zero_stub(-0.001, 50.456, 8.126, "#e86518") == (
        '<rect x="0" y="49.46" width="8.13" height="2" fill="#e86518"/>'
    )
    assert zero_stub(12.0, 50.5, 8.0, "#e86518") == (
        '<rect x="12" y="49.5" width="8" height="2" fill="#e86518"/>'
    )


@pytest.mark.parametrize("shape", list(Shape))
def test_points_is_one_path_equal_to_theme_shape_path(shape: Shape) -> None:
    xy = [(10.123, 20.0), (30.0, 0.0), (45.678, 9.5)]
    style = SeriesStyle("#123456", None, shape)
    out = points(xy, style)
    assert out == theme.shape_path(shape, xy, "#123456")
    assert out.count("<path") == 1


def test_points_pins_a_literal_and_rounds_to_two_decimals() -> None:
    style = series_style(0)
    assert points([(10.123, 20.0), (30.0, 0.0)], style) == (
        '<path d="M10.12 20h0M30 0h0" fill="none" stroke="#3284d0"'
        ' stroke-width="7" stroke-linecap="round"/>'
    )


def test_trend_carries_series_colour_and_dash() -> None:
    assert trend(10.126, 20.456, 90.567, -0.001, "#ac4e87") == (
        '<line x1="10.13" y1="20.46" x2="90.57" y2="0" stroke="#ac4e87"'
        ' stroke-width="1.2" stroke-dasharray="5 3"/>'
    )
