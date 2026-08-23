"""Grade adjustment as its own unit (design: GradeAdjustment; Req 7.1, 7.2,
7.3, 7.4, 7.5, 7.7, 7.8, 7.9).

**Why this is a separate unit.** The energy-cost-of-running model below is a
published, fuzzy physiological approximation; the pace channel's own
threshold-anchoring arithmetic (task 3.3) is exact scale contract work. Kept
apart, the model can be replaced (a later, better-validated regression, or a
walking form, if that scope choice is ever revisited) without touching the
scale contract, and the scale contract can be reviewed without wading through
polynomial coefficients (Req 7.8). This module imports nothing from the pace
channel and holds no threshold, FTP, or benchmark-anchoring logic of its own.

**The model, cited.** :func:`running_cost_ratio` applies Minetti, Moia, Roi,
Susta & Ferretti (2002)'s published energy-cost-of-**running** polynomial as
the ratio ``Cr(i) / Cr(0)`` (Req 7.1) -- see
:data:`fitdocs.load.channels.sources.MINETTI_2002`, whose own note records
that the paper's Fig. 1 caption (p. 1041) was read in full and gives both the
running and walking regressions together. Only the running form is
implemented here, by a **scope choice**, not because the walking form lacks a
source (Req 7.9) -- ``.kiro/specs/load-channels/requirements.md``'s Req 7.9
was itself amended 2026-07-27 to correct an earlier, now-false "was not
obtained" wording after that re-sourcing.

**The rejected transcription.** One widely-mirrored transcription of this
polynomial (a garbled OCR copy, documented in
``.kiro/specs/load-channels/research.md``, "Minetti energy cost of running on
a gradient") corrupts the linear term to ``-165*i``. Two independent sources
-- including the paper's own primary text -- agree on ``+19.5*i``, and only
``+19.5`` is physically coherent (uphill must cost more than level ground, not
less). :data:`MINETTI_RUNNING_COEFFICIENTS` below carries the correct
``+19.5``. A future editor who encounters the corrupted variant elsewhere
must not "fix" this module to match it.

**Why the shipped elevation-metric smoothing helper is not called directly.**
:func:`smoothed_altitude` reproduces the *width* and *trailing alignment* of
``fitdocs.metrics.aggregates._smoothed_altitude`` -- the same convention the
shipped elevation-gain/-loss metrics use, so the climb a rendered document
reports and the climb this module adjusts for describe the same terrain (Req
7.3) -- but cannot call that helper directly: it is a private, single-
underscore name, and it *compacts* its output (an index whose trailing window
holds no recorded sample is omitted, not represented). This module instead
needs one smoothed value *per input sample*, aligned index-for-index with the
distance stream so each interval's gradient can be attributed to the right
distance delta. The smoothing *width* itself is not retyped: it is read from
:data:`fitdocs.metrics.sources.ALTITUDE_SMOOTHING_WINDOW`, the exact record
the shipped helper itself reads, at import time -- a re-sourcing of that
record moves both together. The duplication is deliberate and documented
here; it does not change the shipped metric (Req 9.8).

**Untouched measured values.** :func:`equivalent_distance` returns a
*grade-equivalent* distance used only as an intensity input, alongside the
raw recorded distance -- never in place of it. It reads ``samples.distance_m``
and ``samples.altitude_m`` without reassigning or copying-then-mutating
either, and it derives nothing else: the activity's reported distance,
duration, and every other measured value are untouched (Req 7.7).

**Undefined smoothed altitude.** Req 7.5 sanctions treating an interval as
level only for its own two distance-based reasons (a non-positive delta, or
one below :data:`MIN_GRADIENT_DISTANCE_M`). This module extends that
treatment to a third case design.md does not spell out: an interval whose
distance delta clears both distance checks but whose *smoothed* altitude
(:func:`smoothed_altitude`) is undefined at either endpoint -- because the
device recorded no altitude anywhere inside that endpoint's trailing window
-- is also treated as level (gradient ``0``, ratio ``1.0``) rather than
raising or otherwise failing. This is a real, deliberate extrapolation
beyond what Req 7.5 sanctions, made here so the function has *some* defined
behavior rather than crashing on missing altitude coverage, and it is
recorded here precisely so it reads as an implementation decision open to
revision, not as a fourth clause of Req 7.5 itself. Notably, the interval's
own ``applied`` flag still reports ``True`` and no per-interval note or
counter distinguishes "grade genuinely computed" from "altitude missing,
forced level" -- :class:`GradeAdjustment` carries no field for that
distinction today (deliberately not added here; design.md's field list is
not this module's to widen unilaterally).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from fitdocs.metrics import sources as metrics_sources
from fitdocs.model import Samples

MINETTI_RUNNING_COEFFICIENTS: Final[tuple[float, float, float, float, float, float]] = (
    155.4,
    -30.4,
    -43.3,
    46.3,
    19.5,
    3.6,
)
"""``Cr(i) = 155.4*i**5 - 30.4*i**4 - 43.3*i**3 + 46.3*i**2 + 19.5*i + 3.6``,
descending powers of the gradient ``i`` (a decimal fraction), in
J*kg^-1*m^-1. See :data:`fitdocs.load.channels.sources.MINETTI_2002`. The
linear term is ``+19.5*i`` -- see this module's docstring for the corrupted
``-165*i`` variant that must never replace it."""

MINETTI_LEVEL_COST_J_PER_KG_PER_M: Final[float] = MINETTI_RUNNING_COEFFICIENTS[-1]
"""``Cr(0)`` -- the coefficient tuple's own constant term, not an
independently retyped ``3.6``."""

MINETTI_MAX_ABS_GRADIENT: Final[float] = 0.45
"""The published model's validated gradient range is ``-0.45 <= i <= 0.45``
(the treadmill grades Minetti et al. (2002) studied). A gradient outside this
range is clamped to the nearer boundary rather than extrapolated (Req 7.4)."""

MIN_GRADIENT_DISTANCE_M: Final[float] = 1.0
"""Below this recorded distance delta, an interval's gradient is not
meaningful and the interval is treated as level (Req 7.5)."""

ALTITUDE_SMOOTHING_WINDOW: Final[int] = metrics_sources.ALTITUDE_SMOOTHING_WINDOW.value
"""Bound from :data:`fitdocs.metrics.sources.ALTITUDE_SMOOTHING_WINDOW` at
import time -- the same record the shipped elevation metrics themselves read
-- rather than an independently retyped ``10`` (Req 7.3)."""

_NOT_APPLIED_NOTE: Final[str] = (
    "grade adjustment not applied: the caller (the pace channel) decided "
    "against it -- equivalent_distance_m equals the recorded distance"
)


def running_cost_ratio(gradient: float) -> tuple[float, bool]:
    """Minetti's running-cost ratio ``Cr(i) / Cr(0)`` at ``gradient``, and
    whether ``gradient`` had to be clamped into the model's validated range
    first (Req 7.4).

    ``gradient`` is clamped into ``[-MINETTI_MAX_ABS_GRADIENT,
    MINETTI_MAX_ABS_GRADIENT]`` *before* the polynomial is evaluated -- the
    model is never extrapolated beyond the range it was validated over. The
    comparison against the boundary is strict, so a gradient exactly at
    ``+-0.45`` is accepted unclamped. At ``gradient == 0`` this returns
    exactly ``(1.0, False)``, since ``Cr(0) / Cr(0) == 1.0`` by construction
    (:data:`MINETTI_LEVEL_COST_J_PER_KG_PER_M` *is*
    ``MINETTI_RUNNING_COEFFICIENTS[-1]``).
    """
    clamped = (
        gradient < -MINETTI_MAX_ABS_GRADIENT or gradient > MINETTI_MAX_ABS_GRADIENT
    )
    i = min(max(gradient, -MINETTI_MAX_ABS_GRADIENT), MINETTI_MAX_ABS_GRADIENT)
    c5, c4, c3, c2, c1, c0 = MINETTI_RUNNING_COEFFICIENTS
    cost = c5 * i**5 + c4 * i**4 + c3 * i**3 + c2 * i**2 + c1 * i + c0
    return cost / MINETTI_LEVEL_COST_J_PER_KG_PER_M, clamped


def smoothed_altitude(altitude: Sequence[float | None]) -> tuple[float | None, ...]:
    """Altitude smoothed by a trailing, ``None``-skipping boxcar of width
    :data:`ALTITUDE_SMOOTHING_WINDOW`, emitted index-for-index with
    ``altitude`` (Req 7.2, 7.3).

    For each index ``i`` the smoothed point is the arithmetic mean of the
    non-``None`` samples in ``altitude[max(0, i - window + 1) .. i]`` -- the
    same trailing window the shipped elevation metrics use (see this
    module's docstring for why that shipped helper is not called directly).
    An index whose window holds no recorded sample is ``None`` here, rather
    than omitted, so the returned tuple always has the same length as
    ``altitude`` and each entry can be paired with the distance sample at
    the same index.
    """
    window = ALTITUDE_SMOOTHING_WINDOW
    smoothed: list[float | None] = []
    for i in range(len(altitude)):
        lo = max(0, i - window + 1)
        present = [a for a in altitude[lo : i + 1] if a is not None]
        smoothed.append(sum(present) / len(present) if present else None)
    return tuple(smoothed)


@dataclass(frozen=True)
class GradeAdjustment:
    """The raw recorded distance alongside its grade-equivalent counterpart
    (Req 7.7)."""

    raw_distance_m: float
    equivalent_distance_m: float
    applied: bool
    clamped_intervals: int
    note: str | None


def equivalent_distance(
    samples: Samples, *, apply_grade: bool
) -> GradeAdjustment | None:
    """Turn ``samples``' recorded distance and altitude into a
    :class:`GradeAdjustment`, or ``None`` when accumulated distance cannot be
    derived at all.

    ``apply_grade`` is the caller's (the pace channel's) already-made
    decision about altitude coverage; this module reads no configuration and
    does not decide that question itself (Req 3.9, restated at this
    boundary).

    ``raw_distance_m`` is the sum of the recorded stream's positive distance
    deltas -- unaffected by anything the grade model does. When
    ``apply_grade`` is ``False``, ``equivalent_distance_m`` equals
    ``raw_distance_m`` exactly and ``applied`` is ``False`` with a
    descriptive ``note``. When ``apply_grade`` is ``True``,
    ``equivalent_distance_m`` is the cost-ratio-weighted sum of those same
    positive deltas: each interval's gradient is derived from the *smoothed*
    altitude at its two endpoints (Req 7.2), clamped into the model's
    validated range (Req 7.4, counted in ``clamped_intervals``), except that
    an interval whose distance delta is not positive, or is below
    :data:`MIN_GRADIENT_DISTANCE_M`, or whose smoothed altitude is undefined
    at either endpoint, is treated as level (gradient ``0``, ratio ``1.0``)
    rather than producing an extreme or undefined gradient (Req 7.5).

    No input array is mutated (Req 7.7): ``samples.distance_m`` and
    ``samples.altitude_m`` are only read.
    """
    distance = samples.distance_m
    n = len(distance)
    if n < 2:
        return None

    smoothed = smoothed_altitude(samples.altitude_m)

    raw = 0.0
    equivalent = 0.0
    clamped_intervals = 0
    any_defined_pair = False

    for i in range(n - 1):
        d0 = distance[i]
        d1 = distance[i + 1]
        if d0 is None or d1 is None:
            continue
        any_defined_pair = True
        delta = d1 - d0
        if delta <= 0:
            continue
        raw += delta

        if not apply_grade:
            continue

        a0 = smoothed[i]
        a1 = smoothed[i + 1]
        if delta < MIN_GRADIENT_DISTANCE_M or a0 is None or a1 is None:
            ratio = 1.0
            clamped = False
        else:
            gradient = (a1 - a0) / delta
            ratio, clamped = running_cost_ratio(gradient)
        if clamped:
            clamped_intervals += 1
        equivalent += delta * ratio

    if not any_defined_pair:
        return None

    if not apply_grade:
        return GradeAdjustment(
            raw_distance_m=raw,
            equivalent_distance_m=raw,
            applied=False,
            clamped_intervals=0,
            note=_NOT_APPLIED_NOTE,
        )

    return GradeAdjustment(
        raw_distance_m=raw,
        equivalent_distance_m=equivalent,
        applied=True,
        clamped_intervals=clamped_intervals,
        note=None,
    )
