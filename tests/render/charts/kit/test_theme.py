"""Tests for the kit theme and the categorical palette (chart-kit Req 8.2-8.4,
8.6-8.8, 18.4).

The WCAG contrast and the Machado-2009 colour-vision-deficiency arithmetic are
written here, independently of the kit.
"""

from __future__ import annotations

import dataclasses
import itertools
from enum import StrEnum
from pathlib import Path

import pytest

from fitdocs.render.charts.kit import theme
from fitdocs.render.charts.kit.theme import (
    CORE_ROLES,
    DASHES,
    GRID_OPACITY,
    INK_ROLES,
    MAX_SERIES,
    REFERENCE_BACKGROUNDS,
    SHAPES,
    STROKE,
    TEXT,
    InkRole,
    SeriesStyle,
    Shape,
    ink,
    series_style,
    shape_path,
    style_element,
)
from fitdocs.render.charts.palette import CATEGORICAL_RAMP

# --- independent colour arithmetic ------------------------------------------

_LIGHT_BG = "#ffffff"
_DARK_BGS = ("#1e1e1e", "#0d1117", "#1e2129")
_ALL_BGS = (_LIGHT_BG, *_DARK_BGS)

_PROTAN = (
    (0.152286, 1.052583, -0.204868),
    (0.114503, 0.786281, 0.099216),
    (-0.003882, -0.048116, 1.051998),
)
_DEUTAN = (
    (0.367322, 0.860646, -0.227968),
    (0.280085, 0.672501, 0.047413),
    (-0.011820, 0.042940, 0.968881),
)
_TRITAN = (
    (1.255528, -0.076749, -0.178779),
    (-0.078411, 0.930809, 0.147602),
    (0.004733, 0.691367, 0.303900),
)
_SIMULATIONS = {"protanopia": _PROTAN, "deuteranopia": _DEUTAN, "tritanopia": _TRITAN}


def _linear(hex_value: str) -> tuple[float, float, float]:
    out = []
    for i in (1, 3, 5):
        c = int(hex_value[i : i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out[0], out[1], out[2]


def _luminance(hex_value: str) -> float:
    r, g, b = _linear(hex_value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return float((hi + 0.05) / (lo + 0.05))


def _oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _simulate(
    rgb: tuple[float, float, float], matrix: tuple[tuple[float, ...], ...]
) -> tuple[float, float, float]:
    out = [sum(m * c for m, c in zip(row, rgb, strict=True)) for row in matrix]
    return (
        max(0.0, min(1.0, out[0])),
        max(0.0, min(1.0, out[1])),
        max(0.0, min(1.0, out[2])),
    )


def _distance(
    a: str, b: str, matrix: tuple[tuple[float, ...], ...] | None = None
) -> float:
    ra, rb = _linear(a), _linear(b)
    if matrix is not None:
        ra, rb = _simulate(ra, matrix), _simulate(rb, matrix)
    la, lb = _oklab(ra), _oklab(rb)
    total = sum((x - y) ** 2 for x, y in zip(la, lb, strict=True))
    return float(total**0.5)


def test_arithmetic_self_check() -> None:
    """The reference arithmetic reproduces textbook values."""
    assert _contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert _contrast("#7f7f7f", "#ffffff") == pytest.approx(4.0, abs=0.05)
    assert _distance("#ffffff", "#000000") == pytest.approx(1.0, abs=0.001)
    assert _distance("#336699", "#336699", _DEUTAN) == 0.0
    lab = _oklab(_linear("#ff0000"))
    for got, want in zip(lab, (0.62796, 0.22486, 0.12585), strict=True):
        assert got == pytest.approx(want, abs=1e-4)
    # Machado full-severity matrices keep neutral greys neutral (rows sum to 1).
    for matrix in _SIMULATIONS.values():
        for row in matrix:
            assert sum(row) == pytest.approx(1.0, abs=1e-5)


# --- inks (Req 8.2, 8.3, 8.4) ------------------------------------------------


def test_reference_backgrounds_are_the_four_pinned_colours() -> None:
    assert REFERENCE_BACKGROUNDS == ("#ffffff", "#1e1e1e", "#0d1117", "#1e2129")


def test_core_role_values_and_prefix() -> None:
    assert InkRole("ck-t", "fill", "#7f7f7f", "#707070", "#8e8e8e", True) == TEXT
    assert InkRole("ck-s", "stroke", "#7f7f7f", "#707070", "#8e8e8e", False) == STROKE
    assert CORE_ROLES == (TEXT, STROKE)
    assert INK_ROLES[:2] == (TEXT, STROKE)
    assert GRID_OPACITY == "0.25"


def test_ink_role_is_frozen_with_pinned_field_order() -> None:
    assert [f.name for f in dataclasses.fields(InkRole)] == [
        "css_class",
        "prop",
        "base",
        "light",
        "dark",
        "text",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        TEXT.base = "#000000"  # type: ignore[misc]


def test_every_ink_is_at_least_3_to_1_on_every_background() -> None:
    assert len(INK_ROLES) >= 2
    for role in INK_ROLES:
        for value in (role.base, role.light, role.dark):
            for bg in _ALL_BGS:
                assert _contrast(value, bg) >= 3.0, (role.css_class, value, bg)


def test_text_rule_inks_reach_4_5_to_1_on_the_scheme_they_target() -> None:
    texts = [role for role in INK_ROLES if role.text]
    assert TEXT in texts
    for role in texts:
        assert _contrast(role.light, _LIGHT_BG) >= 4.5, role.css_class
        for bg in _DARK_BGS:
            assert _contrast(role.dark, bg) >= 4.5, (role.css_class, bg)


# --- the categorical palette (Req 8.7) ---------------------------------------


def test_ramp_prefix_is_pinned_to_the_design_values() -> None:
    assert CATEGORICAL_RAMP[:8] == (
        "#3284d0",
        "#e86518",
        "#ac4e87",
        "#719a5b",
        "#c04637",
        "#c27895",
        "#098356",
        "#6e5dd8",
    )


def test_every_palette_colour_is_at_least_3_to_1_on_every_background() -> None:
    assert len(CATEGORICAL_RAMP) >= 8
    for color in CATEGORICAL_RAMP:
        for bg in _ALL_BGS:
            assert _contrast(color, bg) >= 3.0, (color, bg)


def test_every_palette_pair_is_distinct_in_normal_vision() -> None:
    pairs = list(itertools.combinations(CATEGORICAL_RAMP, 2))
    assert len(pairs) >= 28
    for a, b in pairs:
        assert _distance(a, b) >= 0.10, (a, b)


@pytest.mark.parametrize("name", sorted(_SIMULATIONS))
def test_every_palette_pair_is_distinct_under_each_simulation(name: str) -> None:
    matrix = _SIMULATIONS[name]
    for a, b in itertools.combinations(CATEGORICAL_RAMP, 2):
        assert _distance(a, b, matrix) >= 0.06, (name, a, b)


# --- the style element (Req 8.3, 8.4) ----------------------------------------

_STYLE_LITERAL = (
    "@media (prefers-color-scheme:light)"
    "{.ck-t{fill:#707070}.ck-s{stroke:#707070}}"
    "@media (prefers-color-scheme:dark)"
    "{.ck-t{fill:#8e8e8e}.ck-s{stroke:#8e8e8e}}"
)

_STUB = InkRole("ck-x", "fill", "#7f7f7f", "#606060", "#9a9a9a", False)
_STUB_B = InkRole("ck-y", "stroke", "#7f7f7f", "#616161", "#9b9b9b", False)


def test_style_element_equals_the_design_literal() -> None:
    assert style_element() == _STYLE_LITERAL
    assert style_element(()) == _STYLE_LITERAL


def test_style_element_appends_extra_roles_after_the_core_ones() -> None:
    assert style_element((_STUB,)) == (
        "@media (prefers-color-scheme:light)"
        "{.ck-t{fill:#707070}.ck-s{stroke:#707070}.ck-x{fill:#606060}}"
        "@media (prefers-color-scheme:dark)"
        "{.ck-t{fill:#8e8e8e}.ck-s{stroke:#8e8e8e}.ck-x{fill:#9a9a9a}}"
    )
    assert style_element((_STUB, _STUB_B)) == (
        "@media (prefers-color-scheme:light)"
        "{.ck-t{fill:#707070}.ck-s{stroke:#707070}"
        ".ck-x{fill:#606060}.ck-y{stroke:#616161}}"
        "@media (prefers-color-scheme:dark)"
        "{.ck-t{fill:#8e8e8e}.ck-s{stroke:#8e8e8e}"
        ".ck-x{fill:#9a9a9a}.ck-y{stroke:#9b9b9b}}"
    )


def test_style_element_does_not_read_ink_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(theme, "INK_ROLES", (*CORE_ROLES, _STUB))
    assert theme.INK_ROLES[-1] is _STUB
    assert style_element() == _STYLE_LITERAL


# --- ink() ---------------------------------------------------------------------


def test_ink_returns_class_then_property() -> None:
    assert ink(TEXT) == {"class": "ck-t", "fill": "#7f7f7f"}
    assert list(ink(TEXT)) == ["class", "fill"]
    assert ink(STROKE) == {"class": "ck-s", "stroke": "#7f7f7f"}
    assert list(ink(STROKE)) == ["class", "stroke"]


# --- series styles (Req 8.8) ---------------------------------------------------


def test_shape_members_names_and_values() -> None:
    assert [(m.name, m.value) for m in Shape] == [
        ("CIRCLE", "circle"),
        ("SQUARE", "square"),
        ("TRIANGLE_UP", "triangle-up"),
        ("DIAMOND", "diamond"),
        ("TRIANGLE_DOWN", "triangle-down"),
        ("TRIANGLE_RIGHT", "triangle-right"),
        ("TRIANGLE_LEFT", "triangle-left"),
        ("PLUS", "plus"),
    ]
    assert tuple(Shape) == SHAPES
    assert issubclass(Shape, StrEnum)
    assert str(Shape.TRIANGLE_UP) == "triangle-up"
    assert f"{Shape.PLUS}" == "plus"


def test_dashes_are_the_eight_pinned_distinct_patterns() -> None:
    assert DASHES == (
        None,
        "6 3",
        "2 2",
        "8 3 2 3",
        "12 4",
        "1 3",
        "6 2 2 2",
        "10 3 4 3",
    )
    assert len(set(DASHES)) == 8
    assert len(set(SHAPES)) == 8
    assert MAX_SERIES == 8


def test_series_style_pairs_ramp_dash_and_shape_by_index() -> None:
    assert [f.name for f in dataclasses.fields(SeriesStyle)] == [
        "color",
        "dash",
        "shape",
    ]
    for i in range(MAX_SERIES):
        assert series_style(i) == SeriesStyle(CATEGORICAL_RAMP[i], DASHES[i], SHAPES[i])
    assert series_style(0).dash is None
    assert series_style(1) == SeriesStyle("#e86518", "6 3", Shape.SQUARE)
    assert series_style(7) == SeriesStyle("#6e5dd8", "10 3 4 3", Shape.PLUS)
    with pytest.raises(dataclasses.FrozenInstanceError):
        series_style(0).color = "#000000"  # type: ignore[misc]


@pytest.mark.parametrize("index", [-1, MAX_SERIES, MAX_SERIES + 1])
def test_series_style_refuses_an_index_outside_the_series_limit(index: int) -> None:
    with pytest.raises(ValueError):
        series_style(index)


# --- shape_path ----------------------------------------------------------------

_C = "#123456"
_SHAPE_CASES = [
    (
        Shape.CIRCLE,
        (10.0, 20.0),
        f'<path d="M10 20h0" fill="none" stroke="{_C}" stroke-width="7" '
        'stroke-linecap="round"/>',
    ),
    (
        Shape.SQUARE,
        (11.0, 21.0),
        f'<path d="M11 21h0" fill="none" stroke="{_C}" stroke-width="7" '
        'stroke-linecap="square"/>',
    ),
    (
        Shape.TRIANGLE_UP,
        (12.0, 22.0),
        f'<path d="M12 18.5l3.5 7h-7z" fill="{_C}"/>',
    ),
    (
        Shape.DIAMOND,
        (13.0, 23.0),
        f'<path d="M13 19.5l3.5 3.5l-3.5 3.5l-3.5-3.5z" fill="{_C}"/>',
    ),
    (
        Shape.TRIANGLE_DOWN,
        (14.0, 24.0),
        f'<path d="M10.5 20.5h7l-3.5 7z" fill="{_C}"/>',
    ),
    (
        Shape.TRIANGLE_RIGHT,
        (15.0, 25.0),
        f'<path d="M11.5 21.5l7 3.5l-7 3.5z" fill="{_C}"/>',
    ),
    (
        Shape.TRIANGLE_LEFT,
        (16.0, 26.0),
        f'<path d="M19.5 22.5l-7 3.5l7 3.5z" fill="{_C}"/>',
    ),
    (
        Shape.PLUS,
        (17.0, 27.0),
        f'<path d="M13.5 27h7M17 23.5v7" fill="none" stroke="{_C}" stroke-width="2"/>',
    ),
]


@pytest.mark.parametrize(("shape", "centre", "expected"), _SHAPE_CASES)
def test_shape_path_for_one_centre_equals_the_literal(
    shape: Shape, centre: tuple[float, float], expected: str
) -> None:
    assert shape_path(shape, [centre], _C) == expected


def test_shape_path_covers_every_shape() -> None:
    assert [case[0] for case in _SHAPE_CASES] == list(Shape)


def test_shape_path_joins_one_subpath_per_centre_in_one_element() -> None:
    assert shape_path(Shape.CIRCLE, [(10.0, 20.0), (30.5, 40.25)], _C) == (
        f'<path d="M10 20h0M30.5 40.25h0" fill="none" stroke="{_C}" '
        'stroke-width="7" stroke-linecap="round"/>'
    )
    assert shape_path(Shape.TRIANGLE_UP, [(10.0, 20.0), (30.0, 40.0)], _C) == (
        f'<path d="M10 16.5l3.5 7h-7zM30 36.5l3.5 7h-7z" fill="{_C}"/>'
    )


def test_shape_path_formats_coordinates_through_fmt_num() -> None:
    assert shape_path(Shape.CIRCLE, [(10.123, 20.456)], _C).startswith(
        '<path d="M10.12 20.46h0"'
    )


# --- source hygiene (Req 8.6) --------------------------------------------------


def test_module_source_has_no_light_dark_or_current_color() -> None:
    source = Path(theme.__file__).read_text()
    assert "prefers-color-scheme" in source
    assert "light-dark(" not in source
    assert "currentColor" not in source
