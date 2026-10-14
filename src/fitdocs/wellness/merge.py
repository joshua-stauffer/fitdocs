"""Pure resolution of archive snapshots into daily source-attributed values."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from fitdocs.wellness.model import DaySnapshot, Metric, SeriesValue
from fitdocs.wellness.spec import ParsedEntry, Supersession


@dataclass(frozen=True)
class Conflict:
    day: date
    metric: Metric
    source: str
    kept_entry: str
    kept_value: float
    others: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class MergeResult:
    values: tuple[SeriesValue, ...]
    conflicts: tuple[Conflict, ...]


def merge(
    entries: Sequence[ParsedEntry],
    *,
    order_for: Callable[[Metric], tuple[str, ...]],
) -> MergeResult:
    latest_formats: set[str] = set()
    groups: dict[tuple[str, date, Metric], list[tuple[str, DaySnapshot]]] = defaultdict(
        list
    )
    for entry in entries:
        if entry.supersession == Supersession.LATEST_ENTRY:
            if entry.format_id in latest_formats:
                raise ValueError(
                    f"multiple latest entries for format {entry.format_id}"
                )
            latest_formats.add(entry.format_id)
        for snapshot in entry.snapshots:
            for metric in snapshot.covers:
                groups[entry.source_id, snapshot.day, metric].append(
                    (entry.entry_ref, snapshot)
                )

    resolved: dict[tuple[date, Metric, str], tuple[float, str | None]] = {}
    conflicts = []
    for (source, day, metric), candidates in groups.items():
        revision = max(
            (snapshot.revision for _, snapshot in candidates),
            key=lambda revision: (revision is not None, revision or ""),
        )
        present = [
            candidate
            for candidate in candidates
            if candidate[1].revision == revision and metric in candidate[1].values
        ]
        if not present:
            continue
        winner = max(
            present, key=lambda candidate: (candidate[0], candidate[1].ordinal)
        )
        ref, snapshot = winner
        value = snapshot.values[metric]
        resolved[day, metric, source] = (value, snapshot.origins.get(metric))
        if len({candidate[1].values[metric] for candidate in present}) > 1:
            conflicts.append(
                Conflict(
                    day,
                    metric,
                    source,
                    ref,
                    value,
                    tuple(
                        sorted(
                            (candidate[0], candidate[1].values[metric])
                            for candidate in present
                            if candidate is not winner
                        )
                    ),
                )
            )

    canonical = {
        (day, metric): next(
            source for source in order_for(metric) if (day, metric, source) in resolved
        )
        for day, metric, _ in resolved
    }
    values = tuple(
        SeriesValue(
            day, metric, source, origin, value, canonical[day, metric] == source
        )
        for (day, metric, source), (value, origin) in sorted(resolved.items())
    )
    return MergeResult(
        values,
        tuple(
            sorted(
                conflicts,
                key=lambda conflict: (conflict.day, conflict.metric, conflict.source),
            )
        ),
    )
