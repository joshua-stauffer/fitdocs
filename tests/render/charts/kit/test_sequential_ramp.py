"""The sequential ramp's stated minima (chart-catalog Requirement 3.9).

Everything here is arithmetic written in this module, independent of the kit:
the WCAG 2.x contrast ratio, the sRGB -> OKLab conversion, and the Machado,
Oliveira and Fernandes (2009) colour-vision-deficiency simulation. Nothing is
imported from ``fitdocs.render.charts.kit``; the ramp itself comes from
:mod:`fitdocs.render.charts.palette`.
"""

from __future__ import annotations

import math

from fitdocs.render.charts.palette import SEQUENTIAL_COLORS, SEQUENTIAL_RAMP

# The four reference backgrounds the ramp must stay legible on (chart-kit 8.2).
BACKGROUNDS = ("#ffffff", "#1e1e1e", "#0d1117", "#1e2129")

# Machado, Oliveira & Fernandes (2009), "A Physiologically-based Model for
# Simulation of Color Vision Deficiency", IEEE TVCG 15(6), published matrices
# at severity 1.0, applied to LINEAR sRGB. Transcribed from the widely
# reproduced table of that paper. One check runs here: each row sums to 1
# (white is preserved, a property of the model; asserted below), which catches
# a transposed matrix but not a swapped row or a mistyped pair that keeps the
# sum. The nine values of each matrix were compared once, during the task 1.2
# review, with the copy Firefox DevTools ships
# (devtools/server/actors/accessibility/constants.js, citing the same paper)
# and matched exactly; that comparison is not repeated by this module.
Matrix = tuple[tuple[float, float, float], ...]
PROTANOPIA: Matrix = (
    (0.152286, 1.052583, -0.204868),
    (0.114503, 0.786281, 0.099216),
    (-0.003882, -0.048116, 1.051998),
)
DEUTERANOPIA: Matrix = (
    (0.367322, 0.860646, -0.227968),
    (0.280085, 0.672501, 0.047413),
    (-0.011820, 0.042940, 0.968881),
)
TRITANOPIA: Matrix = (
    (1.255528, -0.076749, -0.178779),
    (-0.078411, 0.930809, 0.147602),
    (0.004733, 0.691367, 0.303900),
)
IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

# (name, matrix, minimum adjacent OKLab distance)
VISIONS = (
    ("normal", IDENTITY, 0.045),
    ("protanopia", PROTANOPIA, 0.045),
    ("deuteranopia", DEUTERANOPIA, 0.045),
    ("tritanopia", TRITANOPIA, 0.03),
)

Vec = tuple[float, float, float]


def _rgb(hex_value: str) -> Vec:
    return (
        int(hex_value[1:3], 16) / 255,
        int(hex_value[3:5], 16) / 255,
        int(hex_value[5:7], 16) / 255,
    )


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_rgb(hex_value: str) -> Vec:
    r, g, b = _rgb(hex_value)
    return _linear(r), _linear(g), _linear(b)


def _luminance(hex_value: str) -> float:
    r, g, b = _linear_rgb(hex_value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _oklab_of_linear(rgb: Vec) -> Vec:
    r, g, b = rgb
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab(hex_value: str) -> Vec:
    return _oklab_of_linear(_linear_rgb(hex_value))


def _simulate(hex_value: str, matrix: Matrix) -> Vec:
    rgb = _linear_rgb(hex_value)
    out = tuple(
        max(0.0, min(1.0, sum(w * c for w, c in zip(row, rgb, strict=True))))
        for row in matrix
    )
    return _oklab_of_linear((out[0], out[1], out[2]))


def _distance(p: Vec, q: Vec) -> float:
    return math.dist(p, q)


def _chroma(hex_value: str) -> float:
    _, a, b = _oklab(hex_value)
    return math.hypot(a, b)


def test_ramp_is_five_entries_in_the_documented_order() -> None:
    assert len(SEQUENTIAL_RAMP) == 5
    assert tuple(h for h, _ in SEQUENTIAL_COLORS.values()) == SEQUENTIAL_RAMP
    assert tuple(SEQUENTIAL_COLORS) == ("s1", "s2", "s3", "s4", "s5")


def test_machado_matrices_preserve_white() -> None:
    """Every row sums to 1 (within the table's six decimals), the model's
    white-preservation property: a guard on the transcription above."""
    for matrix in (PROTANOPIA, DEUTERANOPIA, TRITANOPIA):
        for row in matrix:
            assert abs(sum(row) - 1.0) < 5e-6


def test_every_ramp_colour_has_three_to_one_on_every_background() -> None:
    for hex_value in SEQUENTIAL_RAMP:
        for background in BACKGROUNDS:
            ratio = _contrast(hex_value, background)
            assert ratio >= 3.0, f"{hex_value} on {background}: {ratio:.3f}"


def test_oklab_lightness_strictly_decreases_along_the_ramp() -> None:
    lightness = [_oklab(h)[0] for h in SEQUENTIAL_RAMP]
    for earlier, later in zip(lightness, lightness[1:], strict=False):
        assert later < earlier, lightness


def test_oklch_chroma_strictly_increases_along_the_ramp() -> None:
    chroma = [_chroma(h) for h in SEQUENTIAL_RAMP]
    for earlier, later in zip(chroma, chroma[1:], strict=False):
        assert later > earlier, chroma


def test_adjacent_steps_stay_apart_under_every_vision() -> None:
    for name, matrix, minimum in VISIONS:
        seen = [_simulate(h, matrix) for h in SEQUENTIAL_RAMP]
        for i, (p, q) in enumerate(zip(seen, seen[1:], strict=False), start=1):
            gap = _distance(p, q)
            assert gap >= minimum, f"{name}: steps {i}-{i + 1}: {gap:.4f}"
