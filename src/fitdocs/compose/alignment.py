"""Whole-hour shift, per-stretch lag and placement of an extra on the base.

Pure: no I/O, no clock. Only distance and power are read to establish a lag;
every other channel is untouched here (channel-merge Req 2.6, 3.3-3.9;
design.md § Alignment).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from fitdocs.compose.stretches import PAUSE_GAP_S, instants, split_stretches
from fitdocs.compose.types import ExtraAlignment, Placement, StretchLag
from fitdocs.identity.matching import (
    SHIFT_MAX_HOURS,
    SHIFT_STEP_S,
    START_TOLERANCE_S,
)
from fitdocs.model import Activity

__all__ = [
    "ALIGNMENT_KEYS",
    "ALIGNMENT_SOURCES",
    "MAX_LAG_S",
    "MIN_MATCHED_SAMPLES",
    "PAUSE_GAP_S",
    "AlignmentKey",
    "align_extra",
    "establish_lag",
    "hour_shift_s",
]


@dataclass(frozen=True)
class AlignmentKey:
    """A channel a lag may be established from."""

    channel: str
    """A ``Samples`` field name."""
    resolution: float
    """The channel's recorded resolution."""
    label: str
    """The word the page uses."""


ALIGNMENT_KEYS: Final[tuple[AlignmentKey, ...]] = (
    AlignmentKey("distance_m", 0.01, "distance"),
    AlignmentKey("power_w", 1.0, "power"),
)
MAX_LAG_S: Final[int] = 2
MIN_MATCHED_SAMPLES: Final[int] = 5

ALIGNMENT_SOURCES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "PAUSE_GAP_S": (
            "Recording is 1 Hz; the measured lag changed only at pauses "
            "(brief, viability check 2026-09-24)"
        ),
        "MAX_LAG_S": (
            "Measured lags of exactly reproduced channels were 0 and +1 s on "
            "three Stryd↔HealthFit pairs; one second of margin each side"
        ),
        "MIN_MATCHED_SAMPLES": (
            "Design choice, not measured: fewer exact matches cannot rule out "
            "coincidence on a repeating power value; a shorter stretch falls "
            "back and says so"
        ),
        "ALIGNMENT_KEYS": (
            "The channels HealthFit reproduced exactly; distance first because "
            "a moving cumulative distance matches at one lag only; heart rate "
            "(-1/0 s), step length (+0.8%) and cadence (±1) are not "
            "reproduced exactly"
        ),
    }
)


def hour_shift_s(base_start: datetime | None, extra_start: datetime | None) -> int:
    """The whole-hour shift to subtract from every extra instant, else ``0``.

    ``k * SHIFT_STEP_S`` when the extra's start minus the base's is a whole
    ``1 <= |k| <= SHIFT_MAX_HOURS`` hours to within ``START_TOLERANCE_S``.
    """
    if base_start is None or extra_start is None:
        return 0
    delta = (extra_start - base_start).total_seconds()
    k = round(delta / SHIFT_STEP_S)
    if not 1 <= abs(k) <= SHIFT_MAX_HOURS:
        return 0
    if abs(delta - k * SHIFT_STEP_S) > START_TOLERANCE_S:
        return 0
    return k * SHIFT_STEP_S


def establish_lag(
    stretch: range,
    extra_instants: Sequence[int | None],
    extra_values: Sequence[float | int | None],
    base_index: Mapping[int, int],
    base_values: Sequence[float | int | None],
    resolution: float,
) -> int | None:
    """The lag one key establishes for one stretch, or ``None``.

    The unique lag in ``-MAX_LAG_S..MAX_LAG_S`` with the most matches, when it
    has at least ``MIN_MATCHED_SAMPLES`` of them and more than half of the
    samples compared at that lag.
    """
    matched: dict[int, int] = {}
    compared: dict[int, int] = {}
    for lag in range(-MAX_LAG_S, MAX_LAG_S + 1):
        n_compared = 0
        n_matched = 0
        for j in stretch:
            value = extra_values[j]
            instant = extra_instants[j]
            if value is None or instant is None:
                continue
            i = base_index.get(instant + lag)
            if i is None:
                continue
            other = base_values[i]
            if other is None:
                continue
            n_compared += 1
            if abs(value - other) < resolution / 2:
                n_matched += 1
        matched[lag] = n_matched
        compared[lag] = n_compared
    best = max(matched.values())
    winners = [lag for lag, n in matched.items() if n == best]
    if len(winners) != 1:
        return None
    lag = winners[0]
    if best < MIN_MATCHED_SAMPLES or 2 * best <= compared[lag]:
        return None
    return lag


def align_extra(base: Activity, extra: Activity) -> Placement:
    """Put ``extra``'s samples on ``base``'s samples, alone, by instant."""
    shift = hour_shift_s(base.start_time, extra.start_time)
    base_instants = instants(base)
    extra_instants = tuple(None if t is None else t - shift for t in instants(extra))
    base_index: dict[int, int] = {}
    for i, t in enumerate(base_instants):
        if t is not None:
            base_index.setdefault(t, i)

    stretch_lags: list[StretchLag] = []
    placed: list[int | None] = [None] * len(base_instants)
    for stretch in split_stretches(extra_instants, base_instants):
        lag_s = 0
        used: str | None = None
        for key in ALIGNMENT_KEYS:
            found = establish_lag(
                stretch,
                extra_instants,
                getattr(extra.samples, key.channel),
                base_index,
                getattr(base.samples, key.channel),
                key.resolution,
            )
            if found is not None:
                lag_s = found
                used = key.channel
                break
        stretch_lags.append(StretchLag(stretch.start, stretch.stop, lag_s, used))
        for j in stretch:
            instant = extra_instants[j]
            if instant is None:
                continue
            slot = base_index.get(instant + lag_s)
            if slot is not None and placed[slot] is None:
                placed[slot] = j
    return Placement(
        alignment=ExtraAlignment(hour_shift_s=shift, stretches=tuple(stretch_lags)),
        extra_index=tuple(placed),
    )
