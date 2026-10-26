"""Windowed Ramer-Douglas-Peucker line simplifier (compact-chart-assets 2.1).

Reduces one gap-free run of output-unit points to the vertices its image can
show. Pure, deterministic, stdlib-only: no I/O, no clock, no randomness, and no
assumption that x is monotone (a hero series is not x-sorted; a route is 2-D).

The run is cut into windows ``[0..K], [K..2K], ...`` with K = :data:`THIN_WINDOW`:
each window spans at most K intervals (so at most K + 1 points) and adjacent
windows share their boundary point. Iterative RDP runs inside each window, so
the work is O(n * K), linear for the fixed window size.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from fitdocs.render.charts.svg import fmt_num

Point = tuple[float, float]

THIN_TOLERANCE: Final[float] = 0.3  # output units; RDP epsilon
# Intervals per RDP window (so K + 1 points); adjacent windows share one point.
THIN_WINDOW: Final[int] = 512
COORD_PLACES: Final[int] = 1  # decimal places of emitted coordinates


def _distance(p: Point, a: Point, b: Point) -> float:
    """Distance from ``p`` to the chord segment ``a``-``b``.

    Point-to-segment distance (the projection is clamped to the segment, so a
    point beyond the chord's end is measured to that end); the Euclidean
    distance to ``a`` when the chord has zero length (a closed window).
    """
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _rdp_window(points: Sequence[Point], lo: int, hi: int, keep: list[bool]) -> None:
    """Mark in ``keep`` the vertices RDP retains between ``lo`` and ``hi``."""
    stack = [(lo, hi)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        a, b = points[first], points[last]
        worst = -1.0
        index = first
        for i in range(first + 1, last):
            d = _distance(points[i], a, b)
            if d > worst:
                worst = d
                index = i
        if worst > THIN_TOLERANCE:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))


def thin(points: Sequence[Point]) -> tuple[Point, ...]:
    """Windowed RDP at ``THIN_TOLERANCE``, rounded to ``COORD_PLACES``, with
    consecutive duplicates created by rounding removed."""
    n = len(points)
    keep = [False] * n
    if n:
        keep[0] = keep[-1] = True
    lo = 0
    while lo < n - 1:
        hi = min(lo + THIN_WINDOW, n - 1)
        keep[lo] = keep[hi] = True
        _rdp_window(points, lo, hi, keep)
        lo = hi
    out: list[Point] = []
    for i in range(n):
        if not keep[i]:
            continue
        p = (round(points[i][0], COORD_PLACES), round(points[i][1], COORD_PLACES))
        if not out or out[-1] != p:
            out.append(p)
    return tuple(out)


def points_attr(points: Sequence[Point]) -> str:
    """``'x,y x,y ...'`` with ``fmt_num(v, places=COORD_PLACES)``."""
    return " ".join(
        f"{fmt_num(x, places=COORD_PLACES)},{fmt_num(y, places=COORD_PLACES)}"
        for x, y in points
    )
