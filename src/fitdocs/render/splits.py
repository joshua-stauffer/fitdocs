"""Device-lap table and 1 km re-slice over the sample stream (design: SplitsRenderer).

This module renders the two splits tables a run/ride document carries: the
device-lap table taken straight from the recorded :class:`~fitdocs.model.Lap`
summary fields, and a 1 km re-slice cut from the cumulative-distance sample
stream. Re-slicing is a *presentation-level* derivation owned here (research:
"Split re-slicing is presentation-level derivation") -- the per-slice aggregates
are table cells, not fit-ingest contract metrics.

Two rules carry the honesty requirement (Req 13):

- **Missing samples are never filled.** Every per-slice aggregate is a simple
  mean/maximum over the *non-``None``* samples in the slice window; a ``None``
  hole is skipped (divided out of the count), never treated as a ``0``. An
  aggregate with no present sample stays ``None`` and renders as :data:`~
  fitdocs.render.format.ABSENT`.
- **Each variant is omitted independently.** No recorded laps -> the lap table
  is omitted; no cumulative-distance channel -> the km table is omitted; both
  absent -> :func:`splits_section` returns ``""`` (Req 6.5).

The exact 1 km slicing rule
---------------------------
Let the *positioned samples* be the sample indices whose ``distance_m`` is
recorded (holes without a cumulative distance cannot be placed in a window and
are dropped, per the honesty rule). Let ``d0`` be the cumulative distance of the
first positioned sample (the baseline; typically ``0``). A positioned sample at
cumulative distance ``d`` belongs to slice ``k = max(1, ceil((d - d0) / 1000))``
-- so the first slice holds every sample up to *and including* the 1000 m mark,
the second holds ``(1000, 2000]``, and so on. Consecutive same-slice samples
form one slice, in order.

For a slice ending at positioned sample ``e`` whose predecessor slice ended at
``p`` (the baseline for the first slice), the slice's reported ``distance_m`` is
``dist[e] - dist[p]`` and its ``time_s`` is ``time[e] - time[p]`` -- the
cumulative delta across the slice boundary, so slice distances and times tile
the covered span exactly (they sum to ``dist[last] - d0`` and
``time[last] - time[first]``). The avg/max aggregates use only the slice's own
member samples. Every slice but the last reaches a full km and is labeled
``"1 km"``, ``"2 km"``, ...; the trailing slice is labeled ``"N km"`` when it
lands exactly on a km boundary, otherwise it is a partial km labeled by its
actual covered distance (for example ``"0.50 km"``).

Sport-aware columns (Req 6.3, 6.4): the distance/time/HR columns are common;
runs add a Pace column, rides add Speed and Avg Power. A split's pace/speed is
derived from its ``avg_speed_mps`` aggregate (recorded lap avg speed, or the
mean of the slice's speed samples); the fastest (quickest pace / highest speed)
and slowest splits are marked ``(fastest)`` / ``(slowest)`` on that cell. A
final ``**Total**`` row sums distance and time and shows the elapsed-weighted
activity-level pace/speed (``total distance / total time``).

Rendering is pure: functions return markdown strings and never touch the
filesystem (Req 4.1).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from fitdocs.model import Activity, Modality
from fitdocs.render.format import (
    ABSENT,
    cell,
    fmt_distance_km,
    fmt_duration,
    fmt_int,
    fmt_pace,
    fmt_speed_kmh,
)

__all__ = ["Split", "km_splits", "lap_splits", "splits_section"]

_KM_M = 1000.0
_EPS = 1e-9


@dataclass(frozen=True)
class Split:
    """One splits-table row: a device lap or a 1 km slice.

    ``distance_m``/``time_s`` are the span the split covers; the remaining fields
    are its display aggregates. Any field the source did not provide is ``None``
    and renders as :data:`~fitdocs.render.format.ABSENT` -- never a fabricated
    ``0`` (Req 13.1).
    """

    label: str
    distance_m: float | None
    time_s: float | None
    avg_hr_bpm: float | None
    max_hr_bpm: float | None
    avg_power_w: float | None
    avg_cadence_rpm: float | None
    avg_speed_mps: float | None


# --- lap splits (recorded fields only) --------------------------------------


def lap_splits(activity: Activity) -> tuple[Split, ...]:
    """One :class:`Split` per recorded lap, filled from lap summary fields (6.3).

    No derivation happens here: each field is the lap's recorded summary value,
    and an unrecorded field stays ``None``. Empty ``activity.laps`` -> ``()``.
    """
    return tuple(
        Split(
            label=f"Lap {number}",
            distance_m=lap.total_distance_m,
            time_s=lap.total_elapsed_time_s,
            avg_hr_bpm=lap.avg_heart_rate_bpm,
            max_hr_bpm=lap.max_heart_rate_bpm,
            avg_power_w=lap.avg_power_w,
            avg_cadence_rpm=lap.avg_cadence_rpm,
            avg_speed_mps=lap.avg_speed_mps,
        )
        for number, lap in enumerate(activity.laps, start=1)
    )


# --- km re-slice ------------------------------------------------------------


def km_splits(activity: Activity) -> tuple[Split, ...]:
    """Re-slice the sample stream into 1 km splits (6.3); see the module docstring
    for the exact slicing rule.

    Returns ``()`` when the cumulative-distance channel carries no data (6.5).
    """
    s = activity.samples
    # Positioned samples: (index, cumulative distance, elapsed time). Samples
    # without a recorded distance cannot be placed in a window and are dropped.
    positioned = [
        (i, d, s.time_s[i]) for i, d in enumerate(s.distance_m) if d is not None
    ]
    if not positioned:
        return ()

    d0 = positioned[0][1]
    t0 = positioned[0][2]
    d_last = positioned[-1][1]

    # Group consecutive positioned samples that fall in the same 1 km bucket.
    groups: list[list[tuple[int, float, float]]] = []
    current: list[tuple[int, float, float]] = []
    current_bucket = 0
    for point in positioned:
        bucket = max(1, math.ceil((point[1] - d0) / _KM_M))
        if current and bucket != current_bucket:
            groups.append(current)
            current = []
        current.append(point)
        current_bucket = bucket

    if current:
        groups.append(current)

    splits: list[Split] = []
    prev_d = d0
    prev_t = t0
    for group_index, group in enumerate(groups):
        member_indices = [index for index, _d, _t in group]
        last_d = group[-1][1]
        last_t = group[-1][2]
        bucket = max(1, math.ceil((last_d - d0) / _KM_M))
        distance = last_d - prev_d
        elapsed = last_t - prev_t

        is_final = group_index == len(groups) - 1
        reaches_full_km = (d_last - d0) >= bucket * _KM_M - _EPS
        if is_final and not reaches_full_km:
            label = fmt_distance_km(distance) or ABSENT  # trailing partial km
        else:
            label = f"{bucket} km"

        hr = [s.heart_rate_bpm[i] for i in member_indices]
        power = [s.power_w[i] for i in member_indices]
        cadence = [s.cadence_rpm[i] for i in member_indices]
        speed = [s.speed_mps[i] for i in member_indices]

        splits.append(
            Split(
                label=label,
                distance_m=distance,
                time_s=elapsed,
                avg_hr_bpm=_mean(hr),
                max_hr_bpm=_max(hr),
                avg_power_w=_mean(power),
                avg_cadence_rpm=_mean(cadence),
                avg_speed_mps=_mean(speed),
            )
        )
        prev_d = last_d
        prev_t = last_t

    return tuple(splits)


def _mean(values: Sequence[float | None]) -> float | None:
    """The mean of the non-``None`` values, or ``None`` when none are present."""
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _max(values: Sequence[float | None]) -> float | None:
    """The maximum of the non-``None`` values, or ``None`` when none are present."""
    present = [v for v in values if v is not None]
    return max(present) if present else None


# --- section rendering ------------------------------------------------------


def splits_section(activity: Activity, modality: Modality) -> str:
    """The Splits section body: a device-lap table and a 1 km table (6.3-6.5).

    Each variant is rendered only when its source data is present and omitted
    independently otherwise; both absent -> ``""`` (6.5).
    """
    blocks: list[str] = []
    laps = lap_splits(activity)
    if laps:
        blocks.append("**Device laps**\n\n" + _table(laps, modality))
    kms = km_splits(activity)
    if kms:
        blocks.append("**1 km splits**\n\n" + _table(kms, modality))
    return "\n\n".join(blocks)


def _table(splits: tuple[Split, ...], modality: Modality) -> str:
    """A splits table with sport-aware columns, marks, and a totals row."""
    is_run = modality is Modality.RUN
    is_bike = modality is Modality.BIKE

    columns = ["Split", "Distance", "Time", "Avg HR", "Max HR"]
    if is_run:
        columns.append("Pace")
    elif is_bike:
        columns += ["Speed", "Avg Power"]

    fastest, slowest = _fastest_slowest(splits)
    lines = [_row(columns), _row(["---"] * len(columns))]
    for index, split in enumerate(splits):
        mark = None
        if index == fastest:
            mark = "fastest"
        elif index == slowest:
            mark = "slowest"
        lines.append(_split_row(split, is_run, is_bike, mark))
    lines.append(_totals_row(splits, is_run, is_bike))
    return "\n".join(lines)


def _fastest_slowest(splits: tuple[Split, ...]) -> tuple[int | None, int | None]:
    """Indices of the fastest and slowest splits by ``avg_speed_mps`` (6.4).

    Comparison uses recorded speed only; splits without a positive speed are not
    ranked. When fewer than two splits are comparable or every comparable split
    shares one speed, nothing is marked (a single split, or a uniform set, has no
    meaningful fastest/slowest distinction).
    """
    ranked = [
        (index, split.avg_speed_mps)
        for index, split in enumerate(splits)
        if split.avg_speed_mps is not None and split.avg_speed_mps > 0
    ]
    if len(ranked) < 2:
        return None, None
    fastest = max(ranked, key=lambda item: item[1])
    slowest = min(ranked, key=lambda item: item[1])
    if fastest[1] == slowest[1]:
        return None, None
    return fastest[0], slowest[0]


def _split_row(split: Split, is_run: bool, is_bike: bool, mark: str | None) -> str:
    """One data row, with the fastest/slowest mark on the pace/speed cell."""
    cells = [
        split.label,
        cell(fmt_distance_km(split.distance_m)),
        cell(fmt_duration(split.time_s)),
        cell(fmt_int(split.avg_hr_bpm, "bpm")),
        cell(fmt_int(split.max_hr_bpm, "bpm")),
    ]
    if is_run:
        cells.append(_marked(_pace(split.avg_speed_mps), mark))
    elif is_bike:
        cells.append(_marked(fmt_speed_kmh(split.avg_speed_mps), mark))
        cells.append(cell(fmt_int(split.avg_power_w, "w")))
    return _row(cells)


def _totals_row(splits: tuple[Split, ...], is_run: bool, is_bike: bool) -> str:
    """The summary row: total distance/time and activity-level pace/speed (6.4)."""
    total_distance = _sum(split.distance_m for split in splits)
    total_time = _sum(split.time_s for split in splits)
    speed = (
        total_distance / total_time
        if total_distance is not None and total_time is not None and total_time > 0
        else None
    )
    cells = [
        "**Total**",
        cell(fmt_distance_km(total_distance)),
        cell(fmt_duration(total_time)),
        ABSENT,
        ABSENT,
    ]
    if is_run:
        cells.append(cell(_pace(speed)))
    elif is_bike:
        cells.append(cell(fmt_speed_kmh(speed)))
        cells.append(ABSENT)
    return _row(cells)


def _sum(values: Iterable[float | None]) -> float | None:
    """Sum the non-``None`` values, or ``None`` when none are present."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _pace(speed_mps: float | None) -> str | None:
    """Pace (``m:ss /km``) derived from a speed, or ``None`` when non-positive."""
    if speed_mps is None or speed_mps <= 0:
        return None
    return fmt_pace(_KM_M / speed_mps)


def _marked(value: str | None, mark: str | None) -> str:
    """A pace/speed cell, appending ``(fastest)`` / ``(slowest)`` when marked."""
    if value is None:
        return ABSENT
    return f"{value} ({mark})" if mark is not None else value


def _row(cells: Sequence[str]) -> str:
    """One markdown table row from its cells."""
    return "| " + " | ".join(cells) + " |"
