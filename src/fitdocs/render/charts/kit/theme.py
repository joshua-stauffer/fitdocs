"""The kit theme: ink roles, the one style element, series styles and markers.

Inks are presentation attributes (a base ink that holds 3:1 on every reference
background) plus a role class; the single ``<style>`` element raises text to
4.5:1 for the colour scheme a viewer actually uses. Series are told apart by
colour, dash pattern and marker shape together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from fitdocs.render.charts.palette import CATEGORICAL_RAMP
from fitdocs.render.charts.svg import el, fmt_num


@dataclass(frozen=True)
class InkRole:
    css_class: str  # "ck-t"
    prop: Literal["fill", "stroke"]
    base: str  # presentation-attribute ink
    light: str  # prefers-color-scheme: light
    dark: str  # prefers-color-scheme: dark
    text: bool  # carries text: the 4.5:1 rule applies


TEXT: Final = InkRole("ck-t", "fill", "#7f7f7f", "#707070", "#8e8e8e", True)
STROKE: Final = InkRole("ck-s", "stroke", "#7f7f7f", "#707070", "#8e8e8e", False)
CORE_ROLES: Final[tuple[InkRole, ...]] = (TEXT, STROKE)
#: Every role, core first, append-only; read by tests only.
INK_ROLES: Final[tuple[InkRole, ...]] = (*CORE_ROLES,)
REFERENCE_BACKGROUNDS: Final = ("#ffffff", "#1e1e1e", "#0d1117", "#1e2129")
GRID_OPACITY: Final = "0.25"


def ink(role: InkRole) -> dict[str, str]:
    """The presentation attributes of ``role``: its class, then its base ink."""
    return {"class": role.css_class, role.prop: role.base}


def style_element(extra: tuple[InkRole, ...] = ()) -> str:
    """The media-query rules: ``CORE_ROLES`` then ``extra``, light then dark.

    The rules of ``extra`` roles appear only when a chart passes them.
    """
    roles = (*CORE_ROLES, *extra)
    light = "".join(f".{r.css_class}{{{r.prop}:{r.light}}}" for r in roles)
    dark = "".join(f".{r.css_class}{{{r.prop}:{r.dark}}}" for r in roles)
    return (
        f"@media (prefers-color-scheme:light){{{light}}}"
        f"@media (prefers-color-scheme:dark){{{dark}}}"
    )


class Shape(StrEnum):
    CIRCLE = "circle"
    SQUARE = "square"
    TRIANGLE_UP = "triangle-up"
    DIAMOND = "diamond"
    TRIANGLE_DOWN = "triangle-down"
    TRIANGLE_RIGHT = "triangle-right"
    TRIANGLE_LEFT = "triangle-left"
    PLUS = "plus"


@dataclass(frozen=True)
class SeriesStyle:
    color: str
    dash: str | None  # stroke-dasharray, None = solid
    shape: Shape


DASHES: Final[tuple[str | None, ...]] = (
    None,
    "6 3",
    "2 2",
    "8 3 2 3",
    "12 4",
    "1 3",
    "6 2 2 2",
    "10 3 4 3",
)
SHAPES: Final[tuple[Shape, ...]] = tuple(Shape)
MAX_SERIES: Final = 8


def series_style(index: int) -> SeriesStyle:
    """The style of series ``index`` (``0 <= index < MAX_SERIES``)."""
    if not 0 <= index < MAX_SERIES:
        raise ValueError(f"series index {index} is outside 0..{MAX_SERIES - 1}")
    return SeriesStyle(CATEGORICAL_RAMP[index], DASHES[index], SHAPES[index])


def _subpath(shape: Shape, x: float, y: float) -> str:
    fx, fy = fmt_num(x), fmt_num(y)

    def at(dx: float, dy: float) -> str:
        return f"M{fmt_num(x + dx)} {fmt_num(y + dy)}"

    if shape is Shape.CIRCLE or shape is Shape.SQUARE:
        return f"M{fx} {fy}h0"
    if shape is Shape.TRIANGLE_UP:
        return at(0, -3.5) + "l3.5 7h-7z"
    if shape is Shape.DIAMOND:
        return at(0, -3.5) + "l3.5 3.5l-3.5 3.5l-3.5-3.5z"
    if shape is Shape.TRIANGLE_DOWN:
        return at(-3.5, -3.5) + "h7l-3.5 7z"
    if shape is Shape.TRIANGLE_RIGHT:
        return at(-3.5, -3.5) + "l7 3.5l-7 3.5z"
    if shape is Shape.TRIANGLE_LEFT:
        return at(3.5, -3.5) + "l-7 3.5l7 3.5z"
    return at(-3.5, 0) + "h7" + at(0, -3.5) + "v7"


def shape_path(shape: Shape, centres: Sequence[tuple[float, float]], color: str) -> str:
    """One ``<path>`` holding one marker subpath per centre.

    The one marker geometry: markers fit a 7 px square; circle and square are
    zero-length subpaths stroked at width 7, plus is stroked at width 2, the
    rest are filled.
    """
    d = "".join(_subpath(shape, x, y) for x, y in centres)
    if shape is Shape.CIRCLE or shape is Shape.SQUARE:
        cap = "round" if shape is Shape.CIRCLE else "square"
        attrs = {
            "d": d,
            "fill": "none",
            "stroke": color,
            "stroke-width": "7",
            "stroke-linecap": cap,
        }
    elif shape is Shape.PLUS:
        attrs = {"d": d, "fill": "none", "stroke": color, "stroke-width": "2"}
    else:
        attrs = {"d": d, "fill": color}
    return el("path", attrs)
