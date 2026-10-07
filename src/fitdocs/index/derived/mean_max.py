"""Project composed-activity best-effort curves into the per-page index table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs.index.producer import PageComputed, Row, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.metrics.mean_max import MeanMaxChannel, mean_max_curve

MEAN_MAX_TABLE: Final[TableSpec] = TableSpec(
    name="mean_max",
    description=(
        "One row per duration of the best-effort set that at least one of power, "
        "speed and heart rate supports on this page's composed activity. A best "
        "effort is the highest average over a window of continuous recording; a "
        "window never spans a step longer than the maximum step between recorded "
        "values (see the records in fitdocs.metrics.mean_max_sources). Follows "
        "the page's rendering, like activities."
    ),
    columns=(
        ColumnSpec("duration_s", ColumnType.INTEGER, "Window length in seconds."),
        ColumnSpec(
            "power_w",
            ColumnType.DOUBLE,
            "Best average power in watts; NULL when no window "
            "of this duration is allowed.",
        ),
        ColumnSpec(
            "power_start_s",
            ColumnType.DOUBLE,
            "Seconds since the activity's start (records.elapsed_s scale) at "
            "which the best power window begins; NULL with power_w.",
        ),
        ColumnSpec(
            "speed_mps",
            ColumnType.DOUBLE,
            "Best average speed in metres per second; NULL when no window "
            "of this duration is allowed.",
        ),
        ColumnSpec(
            "speed_start_s",
            ColumnType.DOUBLE,
            "Seconds since the activity's start (records.elapsed_s scale) at "
            "which the best speed window begins; NULL with speed_mps.",
        ),
        ColumnSpec(
            "heart_rate_bpm",
            ColumnType.DOUBLE,
            "Best average heart rate in beats per minute; NULL when no window "
            "of this duration is allowed.",
        ),
        ColumnSpec(
            "heart_rate_start_s",
            ColumnType.DOUBLE,
            "Seconds since the activity's start (records.elapsed_s scale) at "
            "which the best heart-rate window begins; NULL with heart_rate_bpm.",
        ),
    ),
)


@dataclass(frozen=True)
class MeanMaxProducer:
    """Expose per-page best-effort rows from the composed activity."""

    name: str = "derived.mean_max"
    tables: tuple[TableSpec, ...] = (MEAN_MAX_TABLE,)

    def rows(self, page: PageComputed) -> Rows:
        power = mean_max_curve(page.activity.samples, MeanMaxChannel.POWER)
        speed = mean_max_curve(page.activity.samples, MeanMaxChannel.SPEED)
        heart_rate = mean_max_curve(page.activity.samples, MeanMaxChannel.HEART_RATE)
        rows: list[Row] = []
        for power_point, speed_point, heart_rate_point in zip(
            power, speed, heart_rate, strict=True
        ):
            if not any(
                point.value is not None
                for point in (power_point, speed_point, heart_rate_point)
            ):
                continue
            rows.append(
                (
                    power_point.duration_s,
                    power_point.value,
                    power_point.start_s,
                    speed_point.value,
                    speed_point.start_s,
                    heart_rate_point.value,
                    heart_rate_point.start_s,
                )
            )
        return {MEAN_MAX_TABLE.name: tuple(rows)}


MEAN_MAX_PRODUCER: Final[MeanMaxProducer] = MeanMaxProducer()
