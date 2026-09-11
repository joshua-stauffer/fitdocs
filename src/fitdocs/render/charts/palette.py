"""The documented chart palette: sRGB hex constants with oklch provenance.

fitdocs charts use a small, fixed set of colors. The reference application
(``docs/reference/fitdocs-ai-reference.md`` section 3) specifies them in the
``oklch`` color space; static SVG needs plain sRGB hex. This module ships each
color as an sRGB hex constant **converted once from its oklch source**, and --
crucially -- keeps that oklch source attached to the constant in two ways so the
provenance is real and checkable, never lost to a stale comment (Req 7.4):

1. an adjacent comment on each constant, and
2. the runtime-inspectable :data:`SERIES_COLORS` / :data:`ZONE_COLORS` /
   :data:`ROUTE_COLORS` mappings of ``name -> (hex, oklch_source)``.

The route sport tints (:data:`ROUTE_BIKE_TINT` / :data:`ROUTE_RUN_TINT`) are the
one documented exception: they are carried *verbatim* from the reference product
(``docs/reference/fitdocs-ai-reference.md`` section map) as reference-sourced
sRGB hex, so they are deliberately exempt from the oklch reconversion and are not
listed in :data:`ROUTE_COLORS` -- their hex has no exact oklch preimage.

The conversions use the standard OKLCH -> OKLab -> linear-sRGB -> gamma-sRGB
pipeline; the test suite reimplements that pipeline independently and asserts
each shipped constant equals its oklch source's conversion (within +/-1 per
8-bit channel), which is what makes "every palette constant carries its oklch
source" an observable, enforced property rather than a promise. A few reference
series hues (amber power, blue pace) sit just outside the sRGB gamut and are
clamped into it by the standard pipeline -- the shipped hex is the genuine
clamped conversion, and the test clamps identically.

This module imports the standard library only -- nothing from :mod:`fitdocs`
outside :mod:`fitdocs.render.charts`.
"""

from __future__ import annotations

import math
from typing import Final

# --- series colors (reference section 3) ------------------------------------
# Each constant is the sRGB hex conversion of the oklch source in its comment.

HR_COLOR: Final = "#d5455f"  # oklch(0.6 0.18 14)   -- red
POWER_COLOR: Final = "#cd6600"  # oklch(0.62 0.17 60)  -- amber (clamped to gamut)
PACE_COLOR: Final = "#0079c4"  # oklch(0.55 0.16 240) -- blue (clamped to gamut)
SPEED_COLOR: Final = "#008a96"  # oklch(0.55 0.16 200) -- teal (clamped to gamut)
CADENCE_COLOR: Final = "#c66000"  # oklch(0.6 0.17 60)   -- amber (clamped)
ALTITUDE_COLOR: Final = "#1c8742"  # oklch(0.55 0.14 150) -- green

# Three more series colors for the calendar chart (`charts/calendar.py`):
# fitness, fatigue and form. Hues chosen well clear of the six above (14, 60,
# 240, 200, 60, 150) so all nine stay mutually distinguishable.
FITNESS_COLOR: Final = "#5a66c7"  # oklch(0.55 0.15 275) -- indigo
FATIGUE_COLOR: Final = "#bf50a0"  # oklch(0.6 0.17 340)  -- magenta
FORM_COLOR: Final = "#849b11"  # oklch(0.65 0.15 120)  -- olive/lime

#: Runtime-inspectable provenance: series name -> (sRGB hex, oklch source).
SERIES_COLORS: Final[dict[str, tuple[str, str]]] = {
    "hr": (HR_COLOR, "oklch(0.6 0.18 14)"),
    "power": (POWER_COLOR, "oklch(0.62 0.17 60)"),
    "pace": (PACE_COLOR, "oklch(0.55 0.16 240)"),
    "speed": (SPEED_COLOR, "oklch(0.55 0.16 200)"),
    "cadence": (CADENCE_COLOR, "oklch(0.6 0.17 60)"),
    "altitude": (ALTITUDE_COLOR, "oklch(0.55 0.14 150)"),
    "fitness": (FITNESS_COLOR, "oklch(0.55 0.15 275)"),
    "fatigue": (FATIGUE_COLOR, "oklch(0.6 0.17 340)"),
    "form": (FORM_COLOR, "oklch(0.65 0.15 120)"),
}

# --- route colors (map section) ---------------------------------------------
# The route treatment's sport tints and start/finish markers. Two groups with
# different provenance, kept apart on purpose:
#
# 1. Sport tints -- ROUTE_BIKE_TINT / ROUTE_RUN_TINT -- are carried *verbatim*
#    from the reference product (docs/reference/fitdocs-ai-reference.md section
#    map). They are reference-sourced sRGB hex, NOT oklch conversions: their hex
#    has no exact oklch preimage, so they are deliberately exempt from the oklch
#    reconversion the other palette constants undergo and are not listed in
#    ROUTE_COLORS below.
# 2. The neutral tint and the start/finish marker colors are ordinary
#    standard-pipeline conversions of the oklch source in each comment, carrying
#    their provenance in ROUTE_COLORS exactly like SERIES_COLORS / ZONE_COLORS.

ROUTE_BIKE_TINT: Final = "#1f4d8a"  # ride tint -- verbatim reference hex (section map)
ROUTE_RUN_TINT: Final = "#b22d4a"  # run tint -- verbatim reference hex (section map)

ROUTE_NEUTRAL_TINT: Final = "#576574"  # oklch(0.5 0.03 250)  -- low-chroma slate
ROUTE_START_COLOR: Final = "#05893e"  # oklch(0.55 0.15 150) -- green (start marker)
ROUTE_FINISH_COLOR: Final = "#c92f33"  # oklch(0.55 0.19 25)  -- red   (finish marker)

#: Runtime-inspectable provenance for the oklch-derived route colors:
#: name -> (sRGB hex, oklch source). Mirrors :data:`SERIES_COLORS`. The verbatim
#: reference tints (ROUTE_BIKE_TINT / ROUTE_RUN_TINT) are intentionally excluded
#: -- they are reference-sourced hex with no exact oklch preimage.
ROUTE_COLORS: Final[dict[str, tuple[str, str]]] = {
    "neutral": (ROUTE_NEUTRAL_TINT, "oklch(0.5 0.03 250)"),
    "start": (ROUTE_START_COLOR, "oklch(0.55 0.15 150)"),
    "finish": (ROUTE_FINISH_COLOR, "oklch(0.55 0.19 25)"),
}

# --- cool -> hot HR-zone ramp -----------------------------------------------
# A five-step sequential ramp, Z1 blue (cool) -> Z5 red (hot). Fixed lightness
# is traded for hue: the hue sweeps blue -> green -> yellow -> orange -> red,
# with lightness lifted at the yellow step so it stays in gamut. Each constant
# is the sRGB hex conversion of the oklch source in its comment.

ZONE1_COLOR: Final = "#2f8adc"  # oklch(0.62 0.15 250) -- blue   (Z1, cool)
ZONE2_COLOR: Final = "#32b36e"  # oklch(0.68 0.15 155) -- green  (Z2)
ZONE3_COLOR: Final = "#d5bf36"  # oklch(0.8 0.15 100)  -- yellow (Z3)
ZONE4_COLOR: Final = "#e87f25"  # oklch(0.7 0.16 55)   -- orange (Z4)
ZONE5_COLOR: Final = "#e64343"  # oklch(0.62 0.2 25)   -- red    (Z5, hot)

#: The five base zone colors in cool -> hot order.
ZONE_RAMP: Final[tuple[str, ...]] = (
    ZONE1_COLOR,
    ZONE2_COLOR,
    ZONE3_COLOR,
    ZONE4_COLOR,
    ZONE5_COLOR,
)

#: Runtime-inspectable provenance: zone label -> (sRGB hex, oklch source).
ZONE_COLORS: Final[dict[str, tuple[str, str]]] = {
    "Z1": (ZONE1_COLOR, "oklch(0.62 0.15 250)"),
    "Z2": (ZONE2_COLOR, "oklch(0.68 0.15 155)"),
    "Z3": (ZONE3_COLOR, "oklch(0.8 0.15 100)"),
    "Z4": (ZONE4_COLOR, "oklch(0.7 0.16 55)"),
    "Z5": (ZONE5_COLOR, "oklch(0.62 0.2 25)"),
}

# Extension rule for zone models with more than five zones (e.g. the 7-zone
# Coggan bike model). Beyond Z5 the ramp continues "hotter" by holding the Z5
# red hue/chroma and lowering lightness one fixed step per extra zone -- deeper,
# more intense reds -- so more zones read as more effort. Deterministic and
# unbounded; lightness is floored so the conversion stays well-defined.
_EXT_BASE_LIGHTNESS: Final = 0.62
_EXT_CHROMA: Final = 0.20
_EXT_HUE: Final = 25.0
_EXT_LIGHTNESS_STEP: Final = 0.07
_EXT_LIGHTNESS_FLOOR: Final = 0.20


def _oklch_to_hex(light: float, chroma: float, hue_deg: float) -> str:
    """Convert an OKLCH color to an sRGB hex string via the standard pipeline.

    OKLCH -> OKLab -> linear sRGB -> gamma-encoded sRGB, with out-of-gamut
    channels clamped into ``[0, 1]`` before 8-bit quantization. Pure and
    deterministic; used only to synthesize the zone-ramp extension colors (the
    documented base constants are precomputed hex literals).
    """
    a = chroma * math.cos(math.radians(hue_deg))
    b = chroma * math.sin(math.radians(hue_deg))
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

    return f"#{channel(r_lin):02x}{channel(g_lin):02x}{channel(b_lin):02x}"


def zone_colors(n: int) -> tuple[str, ...]:
    """Return ``n`` HR-zone colors in cool -> hot order (Req 7.4).

    For ``n <= 5`` this is the first ``n`` of the documented five-step
    :data:`ZONE_RAMP` (so ``zone_colors(5) == ZONE_RAMP``). For ``n > 5`` the
    ramp extends deterministically per the module's extension rule: each zone
    beyond five continues the Z5 red at a lightness lowered one fixed step per
    extra zone. ``n <= 0`` returns the empty tuple. The result always has length
    ``max(n, 0)`` and is identical across calls with the same ``n``.
    """
    if n <= 0:
        return ()
    if n <= len(ZONE_RAMP):
        return ZONE_RAMP[:n]
    extensions: list[str] = []
    for step in range(1, n - len(ZONE_RAMP) + 1):
        light = max(
            _EXT_LIGHTNESS_FLOOR,
            _EXT_BASE_LIGHTNESS - _EXT_LIGHTNESS_STEP * step,
        )
        extensions.append(_oklch_to_hex(light, _EXT_CHROMA, _EXT_HUE))
    return ZONE_RAMP + tuple(extensions)
