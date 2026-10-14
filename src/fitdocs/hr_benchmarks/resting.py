"""Daily resting-heart-rate evidence from separate source baselines."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from math import floor
from statistics import median

from . import sources
from .types import Evidence


def resting_evidence(
    values: Mapping[str, Mapping[date, float]],
    *,
    order: Sequence[str],
    series_metric: str,
    document_for_year: Callable[[int], str],
) -> tuple[Evidence, ...]:
    days = {day for source_values in values.values() for day in source_values}
    if not days:
        return ()
    ranked = [source for source in order if source in values]
    ranked.extend(sorted(set(values) - set(order)))
    day = min(days)
    last_day = max(days)
    evidence: list[Evidence] = []
    while day <= last_day:
        start = day - timedelta(days=sources.RESTING_WINDOW_DAYS.value - 1)
        for source in ranked:
            window = [
                value
                for value_day, value in values[source].items()
                if start <= value_day <= day
            ]
            if len(window) < sources.RESTING_MIN_VALUES.value:
                continue
            evidence.append(
                Evidence(
                    day=day,
                    value=floor(median(window) + sources.ROUNDING_HALF_OFFSET.value),
                    key=source,
                    document=document_for_year(day.year),
                    series=f"{source}:{series_metric}",
                    inputs=(
                        f"median of {len(window)} daily values from {source} on the "
                        f"{sources.RESTING_WINDOW_DAYS.value} days ending "
                        f"{day.isoformat()}"
                    ),
                    summary=(
                        f"{source} resting heart rate, "
                        f"{sources.RESTING_WINDOW_DAYS.value}-day median"
                    ),
                )
            )
            break
        day += timedelta(days=1)
    return tuple(evidence)
