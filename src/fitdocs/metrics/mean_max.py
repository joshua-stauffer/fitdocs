"""Pure mean-max curves under fitdocs' recorded continuity rule."""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from enum import StrEnum
from itertools import accumulate
from typing import cast

from fitdocs.metrics import mean_max_sources
from fitdocs.model import Samples


class MeanMaxChannel(StrEnum):
    """A sample channel included in the mean-max curve."""

    POWER = "power_w"
    SPEED = "speed_mps"
    HEART_RATE = "heart_rate_bpm"


@dataclass(frozen=True)
class MeanMaxPoint:
    """The best average and the activity-relative start of its window."""

    duration_s: int
    value: float | None
    start_s: float | None


def _record_value(record: object) -> object:
    return getattr(record, "value", record)


def mean_max_durations_s() -> tuple[int, ...]:
    """Return the current recorded duration set in ascending order."""
    return tuple(
        cast(int, _record_value(record))
        for record in mean_max_sources.MEAN_MAX_DURATIONS_S
    )


def mean_max_curve(
    samples: Samples, channel: MeanMaxChannel
) -> tuple[MeanMaxPoint, ...]:
    """Compute each channel's best mean over continuous held-value windows."""
    values = getattr(samples, channel.value)
    maximum_step = cast(float, _record_value(mean_max_sources.MEAN_MAX_MAX_STEP_S))
    durations = mean_max_durations_s()

    recorded = [
        (instant, cast(int | float, value))
        for instant, value in zip(samples.time_s, values, strict=True)
        if value is not None and math.isfinite(value)
    ]
    stretches: list[list[tuple[float, int | float]]] = []
    for pair in recorded:
        if not stretches or pair[0] - stretches[-1][-1][0] > maximum_step:
            stretches.append([])
        stretches[-1].append(pair)

    best_values: list[float | None] = [None] * len(durations)
    best_starts: list[float | None] = [None] * len(durations)
    for stretch in stretches:
        origin = stretch[0][0]
        last = stretch[-1][0]
        grid: list[int | float] = []
        cursor = 0
        for offset in range(math.floor(last - origin) + 1):
            instant = origin + offset
            while cursor + 1 < len(stretch) and stretch[cursor + 1][0] <= instant:
                cursor += 1
            grid.append(stretch[cursor][1])

        prefix = [0, *accumulate(grid)]
        for index, duration in enumerate(durations):
            if len(grid) < duration:
                continue
            window_sums = tuple(
                map(operator.sub, prefix[duration:], prefix[:-duration])
            )
            maximum = max(window_sums)
            local_start = window_sums.index(maximum)
            average = maximum / duration
            previous = best_values[index]
            if previous is None or average > previous:
                best_values[index] = average
                best_starts[index] = origin + local_start

    return tuple(
        MeanMaxPoint(duration, best_values[index], best_starts[index])
        for index, duration in enumerate(durations)
    )
