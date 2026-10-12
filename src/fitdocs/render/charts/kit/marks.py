"""Mark geometry as SVG element strings (Req 8.8, 9.1, 9.2).

One element per series where possible. Gaps (absent ``y``) split a series into
segments through :func:`fitdocs.render.charts.series.gap_segments`; nothing is
interpolated across them. Marker geometry lives in :mod:`theme` alone. Every
coordinate goes through :func:`fitdocs.render.charts.svg.fmt_num`.
"""

from __future__ import annotations

from collections.abc import Sequence

from fitdocs.render.charts.kit.theme import SeriesStyle, shape_path
from fitdocs.render.charts.series import gap_segments
from fitdocs.render.charts.svg import el, fmt_num

_LINE_WIDTH = "1.8"
_DOT_WIDTH = "5"
_TREND_WIDTH = "1.2"
_TREND_DASH = "5 3"
_STUB_HEIGHT = 2.0


def _xy(x: float, y: float) -> str:
    return f"{fmt_num(x)} {fmt_num(y)}"


def _segments(
    points: Sequence[tuple[float, float | None]],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    return gap_segments([p[0] for p in points], [p[1] for p in points])


def _outline(segment: Sequence[tuple[float, float]], style: SeriesStyle) -> str:
    """A polyline for two or more points, a round-cap dot for exactly one."""
    if len(segment) == 1:
        x, y = segment[0]
        return el(
            "path",
            {
                "d": f"M{_xy(x, y)}h0",
                "fill": "none",
                "stroke": style.color,
                "stroke-width": _DOT_WIDTH,
                "stroke-linecap": "round",
            },
        )
    attrs = {
        "points": " ".join(f"{fmt_num(x)},{fmt_num(y)}" for x, y in segment),
        "fill": "none",
        "stroke": style.color,
        "stroke-width": _LINE_WIDTH,
    }
    if style.dash is not None:
        attrs["stroke-dasharray"] = style.dash
    return el("polyline", attrs)


def line_series(
    points: Sequence[tuple[float, float | None]], style: SeriesStyle
) -> list[str]:
    """Polylines for each run of present points; a lone point becomes a dot."""
    return [_outline(segment, style) for segment in _segments(points)]


def area_series(
    points: Sequence[tuple[float, float | None]],
    baseline_px: float,
    style: SeriesStyle,
    *,
    opacity: str | None,
) -> list[str]:
    """Per segment, a fill closed down to ``baseline_px`` then the outline."""
    out: list[str] = []
    for segment in _segments(points):
        if len(segment) > 1:
            edge = "L".join(_xy(x, y) for x, y in segment)
            last_x, first_x = segment[-1][0], segment[0][0]
            d = f"M{edge}L{_xy(last_x, baseline_px)}L{_xy(first_x, baseline_px)}Z"
            attrs = {"d": d, "fill": style.color}
            if opacity is not None:
                attrs["fill-opacity"] = opacity
            out.append(el("path", attrs))
        out.append(_outline(segment, style))
    return out


def band_path(
    xs: Sequence[float], lower: Sequence[float], upper: Sequence[float]
) -> str:
    """The ``d`` value of a closed band: upper edge forward, lower edge back."""
    if not xs:
        raise ValueError("a band needs at least one x")
    forward = [_xy(x, y) for x, y in zip(xs, upper, strict=True)]
    backward = [_xy(x, y) for x, y in zip(reversed(xs), reversed(lower), strict=True)]
    return "M" + "L".join(forward + backward) + "Z"


def bar(x: float, y: float, width: float, height: float, color: str) -> str:
    """One ``<rect>`` anchored at the zero line.

    ``y`` is the zero-line pixel and ``height`` the signed pixel extent,
    positive upward: the rect spans ``y - height`` to ``y`` when ``height > 0``
    and ``y`` to ``y + |height|`` when ``height < 0``. ``width`` is signed the
    same way: ``x`` is the left edge when ``width > 0``; when ``width < 0`` the
    rect extends left from ``x``. Emitted width and height are never negative.
    """
    top = y - height if height > 0 else y
    left = x + width if width < 0 else x
    return el(
        "rect",
        {
            "x": fmt_num(left),
            "y": fmt_num(top),
            "width": fmt_num(abs(width)),
            "height": fmt_num(abs(height)),
            "fill": color,
        },
    )


def zero_stub(x: float, zero_px: float, width: float, color: str) -> str:
    """A 2 px tall ``<rect>`` centred on the zero line."""
    return el(
        "rect",
        {
            "x": fmt_num(x),
            "y": fmt_num(zero_px - _STUB_HEIGHT / 2),
            "width": fmt_num(width),
            "height": fmt_num(_STUB_HEIGHT),
            "fill": color,
        },
    )


def points(xy: Sequence[tuple[float, float]], style: SeriesStyle) -> str:
    """One ``<path>`` of markers, exactly the theme's ``shape_path``."""
    return shape_path(style.shape, xy, style.color)


def trend(x0: float, y0: float, x1: float, y1: float, color: str) -> str:
    """A dashed ``<line>`` in the series colour."""
    return el(
        "line",
        {
            "x1": fmt_num(x0),
            "y1": fmt_num(y0),
            "x2": fmt_num(x1),
            "y2": fmt_num(y1),
            "stroke": color,
            "stroke-width": _TREND_WIDTH,
            "stroke-dasharray": _TREND_DASH,
        },
    )
