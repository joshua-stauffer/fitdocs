"""The strict evidence tier of the match rule, standard library only.

Shared with the relay, which carries a pinned copy: nothing here may import
from ``fitdocs``. Every comparison is inclusive to floating-point precision and
every absent value is ``None`` and never compared as a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

__all__ = [
    "DISTANCE_TOLERANCE_FRACTION",
    "DISTANCE_TOLERANCE_M",
    "ELAPSED_TOLERANCE_S",
    "START_TOLERANCE_S",
    "StrictFacts",
    "strict_match",
    "within",
]

START_TOLERANCE_S: Final[float] = 1.0
ELAPSED_TOLERANCE_S: Final[float] = 10.0
DISTANCE_TOLERANCE_M: Final[float] = 5.0
DISTANCE_TOLERANCE_FRACTION: Final[float] = 0.2

_RELATIVE_SLACK: Final[float] = 1e-9
"""Floating-point slack, relative to the tolerance (``math.isclose``'s default);
far below any tolerance's measured meaning."""


@dataclass(frozen=True)
class StrictFacts:
    """What the strict tier compares. ``start`` is timezone-aware when present."""

    sport: str
    start: datetime | None
    elapsed_s: float | None
    distance_m: float | None


def within(delta: float, tolerance: float) -> bool:
    """``delta <= tolerance``, inclusive to floating-point precision: a gap that
    is a tolerance exactly in decimal (25.05 m - 20.04 m against 20 % of
    25.05 m) can exceed it by one unit in the last place in binary."""
    return delta <= tolerance * (1.0 + _RELATIVE_SLACK)


def strict_match(a: StrictFacts, b: StrictFacts) -> bool:
    """Whether two sets of facts are one session by the strict tier. Symmetric.

    The sports are equal and both starts are present and within
    ``START_TOLERANCE_S``; then either both distances are present and within
    ``max(DISTANCE_TOLERANCE_M, DISTANCE_TOLERANCE_FRACTION * max(distances))``
    (elapsed is not compared), or a distance is missing, both elapsed times are
    present and they are within ``ELAPSED_TOLERANCE_S``.
    """
    if a.sport != b.sport or a.start is None or b.start is None:
        return False
    if not within(abs((a.start - b.start).total_seconds()), START_TOLERANCE_S):
        return False
    if a.distance_m is not None and b.distance_m is not None:
        limit_m = max(
            DISTANCE_TOLERANCE_M,
            DISTANCE_TOLERANCE_FRACTION * max(a.distance_m, b.distance_m),
        )
        return within(abs(a.distance_m - b.distance_m), limit_m)
    if a.elapsed_s is None or b.elapsed_s is None:
        return False
    return within(abs(a.elapsed_s - b.elapsed_s), ELAPSED_TOLERANCE_S)
