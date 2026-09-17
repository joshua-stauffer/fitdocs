"""Shared constructed-stream builders for this feature's tests (design:
CadenceLockDetector and siblings).

Created by task 2.1 and extended by task 4.1 alone (see
``.kiro/specs/activity-qa-flags/tasks.md``'s "Shared test fixture" note).
Tasks 2.3, 2.4 and 2.5 run concurrently with 2.1 and build their own
constructed values inside their own test modules instead of adding here.

These builders construct :class:`fitdocs.model.Samples` values directly --
no ``.fit`` file, no ingest, no I/O. The athlete's real activity corpus
never enters this repository (Req 2.11); where a test needs to reproduce a
statistic measured on that corpus, it is reconstructed here as a synthetic
stream, never read from a file.
"""

from __future__ import annotations

from collections.abc import Sequence

from fitdocs.model import Samples


def make_time_s(n: int, *, dt: float = 1.0, start_s: float = 0.0) -> tuple[float, ...]:
    """``n`` evenly spaced timestamps, ``dt`` seconds apart, starting at
    ``start_s``."""
    return tuple(start_s + i * dt for i in range(n))


def make_samples(
    time_s: Sequence[float],
    *,
    heart_rate_bpm: Sequence[int | None] | None = None,
    cadence_rpm: Sequence[float | None] | None = None,
    power_w: Sequence[int | None] | None = None,
    speed_mps: Sequence[float | None] | None = None,
    distance_m: Sequence[float | None] | None = None,
    altitude_m: Sequence[float | None] | None = None,
    latitude_deg: Sequence[float | None] | None = None,
    longitude_deg: Sequence[float | None] | None = None,
    temperature_c: Sequence[float | None] | None = None,
) -> Samples:
    """Build a :class:`Samples` value with ``time_s`` and any of the named
    channel arrays given; every other channel is an all-``None`` tuple of
    the same length, matching the ingest layer's own "absent data is
    ``None``" rule rather than fabricating a default.
    """
    n = len(time_s)

    def _ints(values: Sequence[int | None] | None) -> tuple[int | None, ...]:
        return tuple(values) if values is not None else (None,) * n

    def _floats(values: Sequence[float | None] | None) -> tuple[float | None, ...]:
        return tuple(values) if values is not None else (None,) * n

    return Samples(
        time_s=tuple(time_s),
        heart_rate_bpm=_ints(heart_rate_bpm),
        power_w=_ints(power_w),
        cadence_rpm=_floats(cadence_rpm),
        speed_mps=_floats(speed_mps),
        distance_m=_floats(distance_m),
        altitude_m=_floats(altitude_m),
        latitude_deg=_floats(latitude_deg),
        longitude_deg=_floats(longitude_deg),
        temperature_c=_floats(temperature_c),
    )
