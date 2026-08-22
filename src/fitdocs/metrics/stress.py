"""Generic training-stress numbers: Banister TRIMP and power TSS.

These are plain, record-pinned functions any consumer may call -- **not**
methodology load. This module performs no ``LoadCalculator`` work and no
zone- or points-based scoring (Req 11.4); training-load methodology lives
entirely in the downstream training-load spec.

Both formulas' governing constants are read from
:mod:`fitdocs.metrics.sources` rather than named to any working reference
document (Req 15.5), and the two invariants of the metrics layer govern the
functions themselves:

- **``None`` means "not recorded".** Any missing or invalid input yields
  ``None`` -- never a fabricated value -- and nothing raises for absent data
  (Req 12.1). A metric depending on an entirely absent channel is ``None``, not
  ``0`` (Req 12.2).
- **A recorded value is real data.** Heart-rate presence is tested with
  ``is not None``, never truthiness.

**TRIMP** takes the caller-*resolved* weighting pair as an argument rather
than resolving one of its own: :func:`trimp` never calls
:func:`fitdocs.metrics.sources.weighting_for` and holds no notion of a
"default" selection -- resolving the caller's selection (or the default for
none, Req 17.2) is the metrics facade's job (Req 17.1, 17.2, 17.4); this
function's only job is the arithmetic once a pair is in hand, and it returns
that pair's own :class:`~fitdocs.metrics.types.TrimpWeighting` selection
alongside the value it produced (:class:`TrimpResult`, Req 17.6), so there is
no code path that produces a TRIMP value without the selection that produced
it. It sums, over each consecutive sample pair with ``dt > 0`` and
the *earlier* sample's heart rate present::

    HRr = clamp((hr - rest) / (max - rest), 0, 1)
    trimp += dt_min * HRr * c * exp(k * HRr)

where ``dt_min = (time_s[i+1] - time_s[i]) / 60``, ``rest`` / ``max`` are the
caller-supplied resting and maximum heart rate, and ``c`` / ``k`` are the
coefficient and exponent read off the caller-supplied ``weighting`` argument.
Both terms are governed by Banister (1991), corroborated where it agrees or
is silent by Morton (1990) (:data:`fitdocs.metrics.sources.BANISTER_1991`,
:data:`fitdocs.metrics.sources.MORTON_1990`); the departures fitdocs'
per-sample-pair integration and coefficient choice make from those cited
texts are recorded on :data:`fitdocs.metrics.sources.DEPARTURES`, not
characterized again here. :func:`trimp` returns ``None`` -- **whichever**
``weighting`` was supplied (Req 17.5) -- without both thresholds, when the
reserve ``max - rest`` is not positive, or when the heart-rate channel is
entirely unrecorded (no pair has a present earlier HR). Only the first two of
those checks run before ``weighting`` is read at all, so a missing or
non-positive threshold never touches the pair; the entirely-unrecorded-HR
case is detected only after ``weighting.coefficient``/``weighting.exponent``
have been read -- they are read before the accumulation loop -- while the
detection itself happens after that loop (TRIMP depends on the HR channel,
Req 11.1, 12.2).

**Power TSS** takes an *already-computed* normalized power (from
:mod:`fitdocs.metrics.power`) and moving time (from
:mod:`fitdocs.metrics.aggregates`) as inputs -- this module computes
neither::

    IF  = np_w / ftp
    TSS = moving_time_s * np_w * IF / (ftp * 3600) * scale

where ``scale`` is read from
:data:`fitdocs.metrics.sources.TSS_SCALE`, governed by Coggan (2003)
(:data:`fitdocs.metrics.sources.COGGAN_2003`). It is ``None`` without
normalized power, moving time, or a positive FTP (Req 11.2).

This module imports :mod:`fitdocs.model` (for :class:`Samples`),
:mod:`fitdocs.metrics.sources` (intra-``metrics`` reuse is allowed),
:mod:`fitdocs.metrics.types` (for the
:class:`~fitdocs.metrics.types.TrimpWeighting` type :class:`TrimpResult`
carries), and the standard library only -- never :mod:`fitdocs.ingest`, the
FIT SDK, or the sibling ``power`` / ``aggregates`` modules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from fitdocs.metrics import sources
from fitdocs.metrics.types import TrimpWeighting
from fitdocs.model import Samples

_TSS_SCALE: Final[float] = sources.TSS_SCALE.value
"""Percentage scaling for :func:`power_tss`, read from its record
(:data:`fitdocs.metrics.sources.TSS_SCALE`, governed by Coggan (2003)) --
not re-declared as an independent literal."""

_SECONDS_PER_MINUTE: Final[float] = 60.0
_SECONDS_PER_HOUR: Final[float] = 3600.0


def _clamp_unit(value: float) -> float:
    """Clamp ``value`` into the closed interval ``[0, 1]``."""
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class TrimpResult:
    """A computed TRIMP value bundled with the weighting selection that
    produced it (Req 17.6).

    :func:`trimp` never returns a bare number: every code path that yields a
    value returns it paired with ``weighting``, so a caller (the metrics
    facade) unpacks both fields from one result rather than deciding either
    itself, and a training-impulse number is never available without the
    pairing that produced it.
    """

    value: float
    weighting: TrimpWeighting


def trimp(
    samples: Samples,
    resting_hr: int | None,
    max_hr: int | None,
    weighting: sources.WeightingPair,
) -> TrimpResult | None:
    """Banister TRIMP over the heart-rate channel (Req 11.1), or ``None``.

    ``weighting`` is the caller-*resolved* training-impulse weighting pair
    (Req 17.1, 17.2) -- this function does not resolve one itself and holds
    no default; the caller (the metrics facade) resolves a selection, or the
    default for none, through :func:`fitdocs.metrics.sources.weighting_for`
    before calling this function.

    Requires both a resting and a maximum heart rate; returns ``None`` --
    regardless of which ``weighting`` was supplied (Req 17.5) -- if either
    threshold is missing or the reserve ``max_hr - resting_hr`` is not
    positive (an invalid reserve would divide by zero); that check runs
    before ``weighting`` is read at all. For each consecutive sample pair
    with ``dt = time_s[i+1] - time_s[i] > 0`` and the *earlier* sample's heart
    rate present, accumulates::

        HRr    = clamp((hr - resting_hr) / (max_hr - resting_hr), 0, 1)
        trimp += (dt / 60) * HRr * weighting.coefficient.value
                 * exp(weighting.exponent.value * HRr)

    Pairs whose earlier heart rate is ``None`` or whose ``dt`` is not positive
    are skipped. If *no* pair qualifies because the heart-rate channel is
    entirely unrecorded, returns ``None`` (the metric depends on that channel,
    Req 12.2) rather than a fabricated ``0.0``. Otherwise returns a
    :class:`TrimpResult` carrying the accumulated value together with
    ``weighting.selection`` (Req 17.6).
    """
    if resting_hr is None or max_hr is None:
        return None
    reserve = max_hr - resting_hr
    if reserve <= 0:
        return None

    coefficient = weighting.coefficient.value
    exponent = weighting.exponent.value

    time_s = samples.time_s
    heart_rate = samples.heart_rate_bpm
    n = min(len(time_s), len(heart_rate))

    total = 0.0
    contributed = False
    for i in range(n - 1):
        hr = heart_rate[i]
        if hr is None:
            continue
        dt = time_s[i + 1] - time_s[i]
        if dt <= 0:
            continue
        dt_min = dt / _SECONDS_PER_MINUTE
        hrr = _clamp_unit((hr - resting_hr) / reserve)
        total += dt_min * hrr * coefficient * math.exp(exponent * hrr)
        contributed = True

    if not contributed:
        return None
    return TrimpResult(value=total, weighting=weighting.selection)


def power_tss(
    np_w: float | None, moving_time_s: float | None, ftp: float | None
) -> float | None:
    """Power TSS from normalized power, moving time, and FTP (Req 11.2).

    ``np_w`` and ``moving_time_s`` are already-computed inputs (the metrics
    facade derives normalized power via :mod:`fitdocs.metrics.power` and moving
    time via :mod:`fitdocs.metrics.aggregates`); this function computes neither.
    Returns ``None`` if any input is missing or ``ftp`` is not positive.
    Otherwise::

        IF  = np_w / ftp
        TSS = moving_time_s * np_w * IF / (ftp * 3600) * _TSS_SCALE

    where :data:`_TSS_SCALE` is the scale read from its record (module
    docstring). One hour at FTP (``np_w == ftp`` and ``moving_time_s ==
    3600``) yields exactly ``100.0`` at the scale's shipped value.
    """
    if np_w is None or moving_time_s is None or ftp is None or ftp <= 0:
        return None
    intensity_factor = np_w / ftp
    return (
        moving_time_s * np_w * intensity_factor / (ftp * _SECONDS_PER_HOUR) * _TSS_SCALE
    )
