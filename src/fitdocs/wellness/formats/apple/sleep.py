"""Sleep interval unions and night totals."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum


class Stage(IntEnum):
    UNSPECIFIED = 1
    AWAKE = 2
    CORE = 3
    REM = 4
    DEEP = 5


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    stage: Stage


@dataclass(frozen=True)
class NightTotals:
    deep: int
    core: int
    rem: int
    awake: int
    unspecified: int

    @property
    def asleep(self) -> int:
        return self.deep + self.core + self.rem + self.unspecified

    @property
    def staged(self) -> bool:
        return self.deep + self.core + self.rem > 0


def night_totals(segments: Iterable[Segment]) -> NightTotals:
    segments = tuple(segments)
    boundaries = sorted(
        {boundary for segment in segments for boundary in (segment.start, segment.end)}
    )
    totals = dict.fromkeys(Stage, 0)
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        stage = max(
            (
                segment.stage
                for segment in segments
                if segment.start <= start and end <= segment.end
            ),
            default=None,
        )
        if stage is not None:
            totals[stage] += end - start
    return NightTotals(
        deep=totals[Stage.DEEP],
        core=totals[Stage.CORE],
        rem=totals[Stage.REM],
        awake=totals[Stage.AWAKE],
        unspecified=totals[Stage.UNSPECIFIED],
    )


def asleep_intervals(segments: Iterable[Segment]) -> tuple[tuple[int, int], ...]:
    intervals = sorted(
        (segment.start, segment.end)
        for segment in segments
        if segment.stage != Stage.AWAKE and segment.start < segment.end
    )
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)
