"""The feature's pure arithmetic, as stdlib-only functions over
:class:`~fitdocs.model.Samples` (design: PerformanceModels; task 1.3; Req 2.1,
3.2, 3.7, 4.2, 8.3).

This module holds no I/O, no clock and no citation record of its own -- every
constant it needs is read through :mod:`fitdocs.performance.sources`
(``sources.FOO.value``), never as a bare numeric literal (Req 8.3). The
numeric-literal guard in ``tests/performance/test_constant_guard.py`` proves
that mechanically: every remaining literal in this module's own source is
either an arithmetic identity (an index, a loop bound, an additive/
multiplicative identity, a divisor guard) or the one registered unit
conversion (metres to kilometres), never a methodology constant.

**Absent-data rule.** Every function returns ``None`` rather than raising
when its inputs cannot support a result: fewer than two samples, a zero
recorded span, or a wholly unrecorded stream. ``riegel_equivalent_distance_m``
and ``threshold_pace_s_per_km`` return ``None`` for the same reason when their
own inputs are not finite and strictly positive -- the design's precondition
("callers gate first") is a promise about the ordinary calling path through
``DerivationLeaf``, not a license for this module to raise on a malformed
call.

**The time-weighted mean's domain.** ``time_weighted_mean`` accumulates over
exactly the consecutive-pair domain ``fitdocs.load.channels.sufficiency.
stream_coverage`` uses: for each pair of adjacent samples with a positive
``dt = time_s[i+1] - time_s[i]``, the interval is credited to the *earlier*
sample (``values[i]``, not ``values[i+1]``) when that earlier sample is not
``None``. This is a deliberate match, not a coincidence -- a mean computed
over any other domain (crediting the later sample, or ignoring the timestamps
and averaging the raw values by count) could report a value over a span the
coverage gate never actually measured, silently decoupling the two. This is
also why the shipped ``fitdocs.metrics.aggregates._mean_non_none`` is *not*
interchangeable here: that function is an unweighted, sample-count mean with
no notion of ``dt`` at all, so two samples separated by one second and two
samples separated by one hour would contribute equally to it, while this
mean (correctly) weights the hour-long interval 3,600 times more.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from fitdocs.model import Samples
from fitdocs.performance import sources


def _is_finite_positive(value: float) -> bool:
    """``True`` only for a finite, strictly positive number -- the
    precondition both Riegel-model functions below require of their inputs
    (Req 2.6: an absent, non-positive or non-finite input cannot support a
    result)."""
    return math.isfinite(value) and value > 0


def riegel_equivalent_distance_m(*, distance_m: float, time_s: float) -> float | None:
    """The distance whose Riegel-predicted time equals the one-hour solve
    target (Req 2.1, 2.9): ``distance_m * (target_s / time_s) **
    (1 / exponent)``, both ``target_s`` and ``exponent`` read from their
    cited records rather than written as bare literals. Returns ``None``
    when either input is absent, non-positive or non-finite (Req 2.6)."""
    if not _is_finite_positive(distance_m) or not _is_finite_positive(time_s):
        return None
    exponent = sources.RIEGEL_EXPONENT.value
    target_s = sources.RIEGEL_SOLVE_TARGET_S.value
    # float ** float is typed `Any` in typeshed (a complex result is possible
    # for a negative base); the two guards above already rule that out here,
    # so `float(...)` states what the value already is rather than changing it.
    return float(distance_m * (target_s / time_s) ** (1.0 / exponent))


def threshold_pace_s_per_km(*, distance_m: float, time_s: float) -> float | None:
    """The pace, in seconds per kilometre, that follows from the one-hour
    equivalent distance (Req 2.7): the one-hour solve target divided by that
    distance expressed in kilometres. Composes
    :func:`riegel_equivalent_distance_m` and so inherits its ``None`` cases;
    the ``1000.0`` metres-per-kilometre conversion is the module's one
    registered unit-conversion exemption."""
    equivalent_m = riegel_equivalent_distance_m(distance_m=distance_m, time_s=time_s)
    if equivalent_m is None or not _is_finite_positive(equivalent_m):
        return None
    target_s = sources.RIEGEL_SOLVE_TARGET_S.value
    return target_s / (equivalent_m / 1000.0)


def time_weighted_mean(
    samples: Samples, values: Sequence[float | int | None]
) -> float | None:
    """The time-weighted mean of ``values`` over ``samples.time_s`` (Req
    3.2), accumulated over exactly the consecutive-pair domain this module's
    docstring describes -- see there for why this differs from a
    sample-count mean. Returns ``None`` when there are fewer than two
    samples, the total positive inter-sample span is zero, or every covered
    interval's earlier sample is ``None`` (a wholly unrecorded stream) --
    never by raising."""
    time_s = samples.time_s
    n = min(len(time_s), len(values))
    total_weight = 0.0
    covered_weight = 0.0
    weighted_sum = 0.0
    for i in range(n - 1):
        dt = time_s[i + 1] - time_s[i]
        if dt <= 0:
            continue
        total_weight += dt
        value = values[i]
        if value is not None:
            covered_weight += dt
            weighted_sum += value * dt

    if total_weight <= 0 or covered_weight <= 0:
        return None
    return weighted_sum / covered_weight


def recorded_span_s(samples: Samples) -> float | None:
    """The activity's recorded span, in seconds (Req 3.3, 3.6): the sum of
    every positive consecutive inter-sample ``dt`` in ``samples.time_s`` --
    the same accumulation ``stream_coverage.total_s`` performs, but over the
    timestamps alone rather than any one channel. Returns ``None`` when
    there are fewer than two samples or the total is not positive, never by
    raising."""
    time_s = samples.time_s
    n = len(time_s)
    total = 0.0
    for i in range(n - 1):
        dt = time_s[i + 1] - time_s[i]
        if dt > 0:
            total += dt

    if total <= 0:
        return None
    return total


def _round_half_away_from_zero(value: float) -> int:
    """Round ``value`` to the nearest whole number, ties broken away from
    zero rather than to even (Req 3.7): unlike the builtin ``round``, both
    ``169.5`` and ``170.5`` move away from zero rather than either landing on
    the nearer even neighbour. The ``0.5`` offset is read through
    :data:`fitdocs.performance.sources.ROUNDING_HALF_OFFSET` rather than
    written as a bare literal (Req 8.3)."""
    offset = sources.ROUNDING_HALF_OFFSET.value
    if value >= 0:
        return int(value + offset)
    return -int(-value + offset)


def whole_bpm(value: float) -> int:
    """``value`` rounded to a whole number of beats per minute, ties broken
    away from zero through the cited rounding offset (Req 3.7)."""
    return _round_half_away_from_zero(value)


def whole_watts(value: float) -> int:
    """``value`` rounded to a whole number of watts, ties broken away from
    zero through the cited rounding offset (Req 4.2's whole-watts
    expression)."""
    return _round_half_away_from_zero(value)
