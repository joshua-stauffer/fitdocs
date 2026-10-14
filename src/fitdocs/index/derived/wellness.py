"""Project the normalized wellness series through its public reader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs.index.derived.inputs import digest, file_digest
from fitdocs.index.producer import CorpusSnapshot, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.wellness import METRICS, read_series, series_files

WELLNESS_DAILY_TABLE: Final[TableSpec] = TableSpec(
    name="wellness_daily",
    description=(
        "One row per value of the normalized wellness series "
        "(wellness/<year>.csv): one wellness day, metric and source. "
        "Equals the series files as of the last refresh. Every source's "
        "value is kept; exactly one row per day and metric is canonical."
    ),
    columns=(
        ColumnSpec(
            "day",
            ColumnType.DATE,
            "Wellness day: a local calendar date; nights belong to the wake date.",
        ),
        ColumnSpec(
            "metric",
            ColumnType.VARCHAR,
            "Metric name; its unit token ends the name when the metric has a unit.",
        ),
        ColumnSpec(
            "source",
            ColumnType.VARCHAR,
            "Source the value came from (for example garmin-export, intervals-icu).",
        ),
        ColumnSpec(
            "origin",
            ColumnType.VARCHAR,
            "Platform that measured the value; NULL when the source does not say.",
        ),
        ColumnSpec(
            "value",
            ColumnType.DOUBLE,
            "The value in the metric's unit; never converted between sources.",
        ),
        ColumnSpec(
            "unit",
            ColumnType.VARCHAR,
            "Unit token of the metric; NULL for a unitless metric.",
        ),
        ColumnSpec(
            "canonical",
            ColumnType.BOOLEAN,
            "TRUE for the one value per day and metric chosen by source precedence.",
        ),
    ),
)


@dataclass(frozen=True)
class WellnessProducer:
    """Expose every source-attributed series value as a corpus-level row."""

    name: str = "derived.wellness"
    tables: tuple[TableSpec, ...] = (WELLNESS_DAILY_TABLE,)

    def fingerprint(self, corpus: CorpusSnapshot) -> str:
        return digest(
            {
                "series": [
                    [path.relative_to(corpus.data_root).as_posix(), file_digest(path)]
                    for path in series_files(corpus.data_root)
                ]
            }
        )

    def rows(self, corpus: CorpusSnapshot) -> Rows:
        return {
            "wellness_daily": tuple(
                (
                    item.day,
                    item.metric.value,
                    item.source,
                    item.origin,
                    item.value,
                    METRICS[item.metric].unit,
                    item.canonical,
                )
                for item in read_series(corpus.data_root).values
            )
        }


WELLNESS_PRODUCER: Final[WellnessProducer] = WellnessProducer()
