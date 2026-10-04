"""The cross-source match rule: are two files the same session, and by what evidence.

Pure over :class:`SessionKey` values -- no file is read. The rule compares sport,
session start, distance, elapsed time and the device digest; it never compares a
file's timer time (the key has no such field), and the strict tier compares
elapsed time only when a distance is missing (Amendment 1). Every comparison is
inclusive (``<=``), and every absent value is ``None`` and never compared as a
number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from fitdocs.identity.kinds import SourceKind, source_identity
from fitdocs.model import Activity

__all__ = [
    "DISTANCE_TOLERANCE_FRACTION",
    "DISTANCE_TOLERANCE_M",
    "ELAPSED_TOLERANCE_S",
    "SHIFTED_DISTANCE_TOLERANCE_M",
    "SHIFTED_ELAPSED_TOLERANCE_S",
    "SHIFT_MAX_HOURS",
    "SHIFT_STEP_S",
    "START_TOLERANCE_S",
    "TOLERANCE_SOURCES",
    "Evidence",
    "SessionKey",
    "pair_evidence",
    "session_key",
]

START_TOLERANCE_S: Final[float] = 1.0
ELAPSED_TOLERANCE_S: Final[float] = 10.0
DISTANCE_TOLERANCE_M: Final[float] = 5.0
DISTANCE_TOLERANCE_FRACTION: Final[float] = 0.2
SHIFT_STEP_S: Final[int] = 3600
SHIFT_MAX_HOURS: Final[int] = 36
SHIFTED_ELAPSED_TOLERANCE_S: Final[float] = 5.0
SHIFTED_DISTANCE_TOLERANCE_M: Final[float] = 10.0

TOLERANCE_SOURCES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "START_TOLERANCE_S": (
            "Every Stryd↔HealthFit and Garmin↔HealthFit pair agreed on start to "
            "the second; a writer truncating a sub-second start and one rounding "
            "it differ by at most 1 s"
        ),
        "ELAPSED_TOLERANCE_S": (
            "Strict tier only when a distance is missing: Garmin↔HealthFit "
            "within about 1 s; never compared when both record a distance, "
            "because a Stryd file and its HealthFit copy end their sessions at "
            "different moments (90 pairs, 1 s to 1,685 s apart)"
        ),
        "DISTANCE_TOLERANCE_M": (
            "Floor of the strict distance comparison: Garmin↔HealthFit within "
            "5 m; 89 of 90 Stryd↔HealthFit pairs within 1.23 m"
        ),
        "DISTANCE_TOLERANCE_FRACTION": (
            "Of the longer distance, strict tier: a Stryd file that stopped "
            "recording 28 s early was 0.99 % short; deliberately tolerant, "
            "because a start agreeing to the second already separates sessions "
            "(one same-sport pair within 60 s across 2,561 pages, a true "
            "duplicate)"
        ),
        "SHIFT_STEP_S": "244 older HealthFit re-exports shifted by whole hours",
        "SHIFT_MAX_HOURS": "the 2026-09-12 adoption rule's ±36 h window",
        "SHIFTED_ELAPSED_TOLERANCE_S": (
            "the 2026-09-12 adoption rule (true pairs agreed to ≤ 1 s)"
        ),
        "SHIFTED_DISTANCE_TOLERANCE_M": (
            "the 2026-09-12 adoption rule (true pairs agreed to ≤ 1 m)"
        ),
    }
)


class Evidence(StrEnum):
    """Why two files are one session. ``SOURCE`` and ``UUID`` are exact paths."""

    SOURCE = "source"
    UUID = "uuid"
    DEVICE = "device"
    STRICT = "strict"
    SHIFTED = "shifted"


@dataclass(frozen=True)
class SessionKey:
    """The comparable projection of a file or a page. There is no timer field."""

    sport: str
    start: datetime | None
    elapsed_s: float | None
    distance_m: float | None
    device: str | None
    kind: SourceKind | None


def session_key(activity: Activity) -> SessionKey:
    """The key of a parsed file."""
    identity = source_identity(activity)
    return SessionKey(
        sport=activity.sport.value,
        start=activity.start_time,
        elapsed_s=identity.elapsed_s,
        distance_m=identity.distance_m,
        device=identity.device,
        kind=identity.kind,
    )


def _is_shift(delta_s: float) -> bool:
    """Whether ``delta_s`` is a whole 1..SHIFT_MAX_HOURS hours, to within 1 s."""
    hours = round(abs(delta_s) / SHIFT_STEP_S)
    if not 1 <= hours <= SHIFT_MAX_HOURS:
        return False
    return abs(abs(delta_s) - hours * SHIFT_STEP_S) <= START_TOLERANCE_S


def pair_evidence(a: SessionKey, b: SessionKey) -> Evidence | None:
    """The strongest rule tier that holds for the pair, or ``None``. Symmetric."""
    if a.sport != b.sport or a.start is None or b.start is None:
        return None
    start_delta_s = (a.start - b.start).total_seconds()
    close_start = abs(start_delta_s) <= START_TOLERANCE_S

    if (
        close_start
        and a.device is not None
        and b.device is not None
        and a.device == b.device
    ):
        return Evidence.DEVICE

    distance_delta_m = (
        abs(a.distance_m - b.distance_m)
        if a.distance_m is not None and b.distance_m is not None
        else None
    )
    if close_start and a.distance_m is not None and b.distance_m is not None:
        # Both distances recorded: elapsed is not compared (Amendment 1).
        limit_m = max(
            DISTANCE_TOLERANCE_M,
            DISTANCE_TOLERANCE_FRACTION * max(a.distance_m, b.distance_m),
        )
        if abs(a.distance_m - b.distance_m) <= limit_m:
            return Evidence.STRICT

    if a.elapsed_s is None or b.elapsed_s is None:
        return None
    elapsed_delta_s = abs(a.elapsed_s - b.elapsed_s)

    if (
        close_start
        and distance_delta_m is None
        and elapsed_delta_s <= ELAPSED_TOLERANCE_S
    ):
        return Evidence.STRICT

    if (
        SourceKind.PHONE_COPY in (a.kind, b.kind)
        and distance_delta_m is not None
        and _is_shift(start_delta_s)
        and elapsed_delta_s <= SHIFTED_ELAPSED_TOLERANCE_S
        and distance_delta_m <= SHIFTED_DISTANCE_TOLERANCE_M
    ):
        return Evidence.SHIFTED
    return None
