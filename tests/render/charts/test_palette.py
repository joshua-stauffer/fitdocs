"""Behavioral tests for the documented chart palette.

These exercise :mod:`fitdocs.render.charts.palette`: the sRGB hex color
constants used by the hero chart and HR-zone strip, each documented against its
reference ``oklch`` source (``docs/reference/fitdocs-ai-reference.md`` section 3;
Req 7.4).

The palette makes two claims this module verifies for real, not by trust:

1. **Every constant is a genuine oklch conversion.** We reimplement the standard
   OKLCH -> OKLab -> linear-sRGB -> gamma-sRGB pipeline here, independently, and
   assert each shipped hex constant equals the converter's output for its
   documented oklch source (within +/-1 per 8-bit channel for rounding). This
   both proves the constants are not guessed hex and ties each constant to its
   oklch source at test time.
2. **Every constant carries its oklch source** in a runtime-inspectable mapping,
   so the "carries its oklch source" property is not comment-only.

It also pins the cool->hot zone ramp: :func:`zone_colors` returns five base
colors (Z1 blue -> Z5 red) and extends deterministically beyond five.
"""

from __future__ import annotations

import math
import re

from fitdocs.render.charts.palette import (
    ROUTE_BIKE_TINT,
    ROUTE_COLORS,
    ROUTE_RUN_TINT,
    SERIES_COLORS,
    ZONE_COLORS,
    ZONE_RAMP,
    zone_colors,
)

_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")
_OKLCH_RE = re.compile(r"^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$")


# --- independent OKLCH -> sRGB hex reference converter -----------------------


def _oklch_to_rgb(spec: str) -> tuple[int, int, int]:
    """Standard OKLCH -> OKLab -> linear-sRGB -> gamma-sRGB conversion, written
    independently of the module under test so the shipped constants are checked
    against a real conversion rather than themselves.

    ``spec`` is an ``oklch(L C H)`` string (H in degrees). Out-of-gamut channels
    are clamped into ``[0, 1]`` -- the standard behavior -- then quantized to
    8-bit. Returns an ``(r, g, b)`` triple of ints in ``0..255``.
    """
    m = _OKLCH_RE.match(spec)
    assert m is not None, f"unparseable oklch source: {spec!r}"
    light, chroma, hue = (float(g) for g in m.groups())
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = light + 0.3963377774 * a + 0.2158037573 * b
    m_ = light - 0.1055613458 * a - 0.0638541728 * b
    s_ = light - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_**3, m_**3, s_**3
    r_lin = 4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc
    g_lin = -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc
    b_lin = -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc

    def channel(value: float) -> int:
        if value <= 0.0031308:
            srgb = 12.92 * value
        else:
            srgb = 1.055 * (value ** (1 / 2.4)) - 0.055
        return round(max(0.0, min(1.0, srgb)) * 255)

    return channel(r_lin), channel(g_lin), channel(b_lin)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _close(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    return all(abs(x - y) <= 1 for x, y in zip(a, b, strict=True))


# --- the shipped palette must be genuine oklch conversions ------------------


def _all_documented() -> list[tuple[str, str, str]]:
    """(name, hex, oklch_source) for every oklch-derived palette constant.

    Includes the oklch-derived route colors (:data:`ROUTE_COLORS`) but *not* the
    verbatim reference-hex route tints (``ROUTE_BIKE_TINT`` / ``ROUTE_RUN_TINT``),
    which are exempt from the oklch equality assertion by design -- their sRGB hex
    is carried from the reference product and has no exact oklch preimage.
    """
    rows: list[tuple[str, str, str]] = []
    for name, (hex_value, source) in SERIES_COLORS.items():
        rows.append((f"series:{name}", hex_value, source))
    for name, (hex_value, source) in ZONE_COLORS.items():
        rows.append((f"zone:{name}", hex_value, source))
    for name, (hex_value, source) in ROUTE_COLORS.items():
        rows.append((f"route:{name}", hex_value, source))
    return rows


def test_every_constant_is_valid_hex() -> None:
    for name, hex_value, _ in _all_documented():
        assert _HEX_RE.match(hex_value), f"{name}: bad hex {hex_value!r}"


def test_every_constant_carries_a_parseable_oklch_source() -> None:
    for name, _, source in _all_documented():
        assert _OKLCH_RE.match(source), f"{name}: bad oklch source {source!r}"


def test_every_constant_matches_its_oklch_source_conversion() -> None:
    """Each shipped hex constant equals an independent conversion of its
    documented oklch source, within +/-1 per channel (Req 7.4)."""
    for name, hex_value, source in _all_documented():
        want = _oklch_to_rgb(source)
        got = _hex_to_rgb(hex_value)
        assert _close(got, want), (
            f"{name}: {hex_value} = {got} but oklch {source} = {want}"
        )


def test_required_series_are_present_with_their_reference_sources() -> None:
    """Every reference series color (section 3) is present with its oklch."""
    expected = {
        "hr": "oklch(0.6 0.18 14)",
        "power": "oklch(0.62 0.17 60)",
        "pace": "oklch(0.55 0.16 240)",
        "speed": "oklch(0.55 0.16 200)",
        "cadence": "oklch(0.6 0.17 60)",
        "altitude": "oklch(0.55 0.14 150)",
    }
    for name, source in expected.items():
        assert name in SERIES_COLORS, f"missing series color {name!r}"
        assert SERIES_COLORS[name][1] == source


# --- route colors: oklch-derived provenance + reference-hex exemption -------


def test_required_route_colors_are_present_with_their_reference_sources() -> None:
    """Every oklch-derived route color is present with its oklch source (2.2, 2.3).

    These flow through ``_all_documented`` above, so the generic hex/parseable/
    conversion tests already enforce that each equals its oklch source's
    conversion; this pins the exact set and sources.
    """
    expected = {
        "neutral": "oklch(0.5 0.03 250)",
        "start": "oklch(0.55 0.15 150)",
        "finish": "oklch(0.55 0.19 25)",
    }
    assert set(ROUTE_COLORS) == set(expected), "unexpected ROUTE_COLORS keys"
    for name, source in expected.items():
        assert name in ROUTE_COLORS, f"missing route color {name!r}"
        assert ROUTE_COLORS[name][1] == source


def test_route_reference_tints_are_present_and_exempt_from_oklch() -> None:
    """The sport tints are verbatim reference hex, not oklch conversions (2.3).

    ``ROUTE_BIKE_TINT`` / ``ROUTE_RUN_TINT`` come straight from the reference
    product (``docs/reference/fitdocs-ai-reference.md`` section map); their sRGB
    hex has no exact oklch preimage, so they are intentionally kept out of
    ``ROUTE_COLORS`` and out of the oklch equality assertion. They must still be
    valid, stable hex.
    """
    assert ROUTE_BIKE_TINT == "#1f4d8a"
    assert ROUTE_RUN_TINT == "#b22d4a"
    for tint in (ROUTE_BIKE_TINT, ROUTE_RUN_TINT):
        assert _HEX_RE.match(tint), f"bad reference tint hex {tint!r}"
    # documented exemption: the reference tints are never subjected to the oklch
    # round-trip that ROUTE_COLORS entries are.
    documented_hexes = {hex_value for _, hex_value, _ in _all_documented()}
    assert ROUTE_BIKE_TINT not in documented_hexes
    assert ROUTE_RUN_TINT not in documented_hexes


# --- the cool -> hot zone ramp ----------------------------------------------


def test_zone_ramp_has_five_base_colors() -> None:
    assert len(ZONE_RAMP) == 5
    assert all(_HEX_RE.match(c) for c in ZONE_RAMP)


def test_zone_colors_five_returns_the_base_ramp() -> None:
    assert zone_colors(5) == ZONE_RAMP


def test_zone_ramp_runs_cool_to_hot() -> None:
    """Z1 is blue-dominant (cool), Z5 is red-dominant (hot)."""
    z1 = _hex_to_rgb(ZONE_RAMP[0])
    z5 = _hex_to_rgb(ZONE_RAMP[-1])
    assert z1[2] > z1[0], "Z1 should be blue-dominant"
    assert z5[0] > z5[2], "Z5 should be red-dominant"


def test_zone_colors_fewer_than_five_returns_prefix() -> None:
    assert zone_colors(1) == ZONE_RAMP[:1]
    assert zone_colors(3) == ZONE_RAMP[:3]


def test_zone_colors_zero_is_empty() -> None:
    assert zone_colors(0) == ()


def test_zone_colors_extends_beyond_five_deterministically() -> None:
    seven = zone_colors(7)
    assert len(seven) == 7
    # the first five are exactly the documented base ramp
    assert seven[:5] == ZONE_RAMP
    # every extension is valid hex
    assert all(_HEX_RE.match(c) for c in seven)
    # deterministic: same input, byte-identical output
    assert zone_colors(7) == seven
    # the extensions are distinct from each other and from Z5
    assert len(set(seven)) == 7


def test_zone_colors_length_matches_request() -> None:
    for n in range(0, 9):
        assert len(zone_colors(n)) == n
