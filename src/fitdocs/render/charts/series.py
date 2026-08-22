"""Reference section 3 chart-series math: smoothing, normalization, gaps.

Four pure helpers turn a plain telemetry series (a ``float | None`` sequence,
absent samples as ``None``) into something the hero chart can draw, per
``docs/reference/fitdocs-ai-reference.md`` section 3:

- :func:`boxcar_smooth` -- a null-skipping symmetric boxcar (default 11-sample
  window) that damps sample jitter without ever inventing a value at a hole.
- :func:`normalize_band` -- per-series min/max normalization into a target band
  ``[lo, hi]``, with flat series pinned to the band midpoint.
- :func:`gap_segments` -- splits a polyline into contiguous segments at runs of
  missing samples so gaps render as gaps.
- :func:`paired_gap_segments` -- the 2-channel sibling of :func:`gap_segments`:
  over two nullable channels a point exists only where both are present, and a
  ``None`` in either channel breaks the segment.

One rule governs all three: **missing samples are never interpolated or filled**
(Req 7.5). Real streams are sparse -- observed heart-rate coverage as low as
62% -- so a ``None`` stays ``None`` through smoothing and normalization, and a
run of ``None`` breaks the line rather than being bridged. Recorded zeros are
ordinary values throughout (presence is tested with ``is not None``, never
truthiness), so a real ``0`` participates in every window and normalization.

This module imports the standard library only -- no fit-ingest imports and
nothing from :mod:`fitdocs` outside :mod:`fitdocs.render.charts` (charts take
plain series; ``sections.py`` prepares them from the model).
"""

from __future__ import annotations

from collections.abc import Sequence


def boxcar_smooth(
    values: Sequence[float | None],
    k: int = 5,
) -> tuple[float | None, ...]:
    """Null-skipping symmetric boxcar smoothing (Req 7.5).

    For each index ``i``: if ``values[i]`` is ``None`` the output at ``i`` is
    ``None`` -- a missing sample stays missing, never fabricated. Otherwise the
    output is the arithmetic mean of the non-``None`` values within the
    symmetric window ``[i - k, i + k]`` (width ``2k + 1``, default ``k=5`` -> 11
    samples), clamped at the array ends. ``None`` neighbours are skipped from the
    mean, not counted as ``0``, so smoothing never interpolates across a hole.

    The window always contains ``values[i]`` itself (which is non-``None`` on
    this branch), so the mean is always over at least one value. Returns a tuple
    the same length as ``values``.
    """
    n = len(values)
    out: list[float | None] = []
    for i in range(n):
        center = values[i]
        if center is None:
            out.append(None)
            continue
        lo = max(0, i - k)
        hi = min(n, i + k + 1)
        window = [v for v in values[lo:hi] if v is not None]
        out.append(sum(window) / len(window))
    return tuple(out)


def normalize_band(
    values: Sequence[float | None],
    lo: float,
    hi: float,
) -> tuple[float | None, ...]:
    """Map the non-``None`` values into the target band ``[lo, hi]`` (Req 7.4).

    Let ``vmin`` / ``vmax`` be the min / max of the non-``None`` values. Each
    non-``None`` ``v`` maps to ``lo + (v - vmin) / (vmax - vmin) * (hi - lo)`` --
    so ``vmin`` lands on ``lo`` and ``vmax`` on ``hi``. A *flat* series
    (``vmax == vmin``, including a single distinct value) has no spread to
    normalize, so every non-``None`` value pins to the band midpoint
    ``(lo + hi) / 2`` (0.67 for the main ``[0.42, 0.92]`` band).

    ``None`` stays ``None``. If there are no non-``None`` values, every position
    is ``None``. Returns a tuple the same length as ``values``.
    """
    present = [v for v in values if v is not None]
    if not present:
        return tuple(None for _ in values)
    vmin = min(present)
    vmax = max(present)
    midpoint = (lo + hi) / 2
    if vmax == vmin:
        return tuple(None if v is None else midpoint for v in values)
    span = vmax - vmin
    band = hi - lo
    return tuple(None if v is None else lo + (v - vmin) / span * band for v in values)


def gap_segments(
    x: Sequence[float],
    y: Sequence[float | None],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Split a polyline into contiguous segments at runs of missing ``y`` (7.5).

    Each returned segment is a tuple of ``(x[i], y[i])`` points for a maximal run
    of indices where ``y[i]`` is not ``None``. A run of ``None`` breaks the
    polyline into separate segments, so gaps render as gaps and are never
    interpolated across. ``x`` values are all present (floats); ``x`` and ``y``
    must be the same length.

    Returns a tuple of segments. An all-``None`` (or empty) ``y`` yields the
    empty tuple ``()``.
    """
    segments: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] = []
    for xi, yi in zip(x, y, strict=True):
        if yi is None:
            if current:
                segments.append(tuple(current))
                current = []
        else:
            current.append((xi, yi))
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def paired_gap_segments(
    a: Sequence[float | None],
    b: Sequence[float | None],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Split two nullable channels into segments, breaking on either gap (2.4).

    The 2-channel sibling of :func:`gap_segments`: a point ``(a[i], b[i])``
    exists only at indices where **both** ``a[i]`` and ``b[i]`` are present
    (presence tested with ``is not None``, never truthiness -- a real ``0.0`` is
    an ordinary value that forms a point). A ``None`` in *either* channel breaks
    the current segment, so a hole in one channel splits the polyline exactly as
    a hole in the other does; a run of incomplete pairs is never bridged across.
    ``a`` and ``b`` must be the same length.

    Stated generally over any paired nullable channels -- the map planner later
    applies it to (latitude, longitude) before projection. Returns a tuple of
    segments; if no index has a complete pair (all-``None``, empty, or the two
    channels' present values never coincide) the result is the empty tuple
    ``()``.
    """
    segments: list[tuple[tuple[float, float], ...]] = []
    current: list[tuple[float, float]] = []
    for ai, bi in zip(a, b, strict=True):
        if ai is None or bi is None:
            if current:
                segments.append(tuple(current))
                current = []
        else:
            current.append((ai, bi))
    if current:
        segments.append(tuple(current))
    return tuple(segments)
