"""Project the history engine's load-series computation into three tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs.history import (
    MethodologyChoice,
    compute_history,
    day_rows,
    observed_methodologies,
    read_history_inputs,
    select_methodology,
)
from fitdocs.index.derived.inputs import digest, settings_digest, workouts_digest
from fitdocs.index.producer import CorpusSnapshot, Row, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec

LOAD_SERIES_TABLE: Final[TableSpec] = TableSpec(
    name="load_series",
    description=(
        "One row per training-load methodology some workout page records a load "
        "under: the terms its fitness/fatigue/form series was computed with. "
        "Equals fitdocs history --methodology <methodology>'s computation for "
        "the inputs as of the last refresh."
    ),
    columns=(
        ColumnSpec("methodology", ColumnType.VARCHAR, "Calculator id."),
        ColumnSpec(
            "history_default",
            ColumnType.BOOLEAN,
            "TRUE for the methodology fitdocs history shows without "
            "--methodology; FALSE for every row when it would refuse to choose.",
        ),
        ColumnSpec(
            "default_selection",
            ColumnType.VARCHAR,
            "configured or inferred for the default; NULL otherwise.",
        ),
        ColumnSpec("series_start", ColumnType.DATE, "First day of the series."),
        ColumnSpec("series_end", ColumnType.DATE, "Last day of the series."),
        ColumnSpec(
            "tau_fitness_days",
            ColumnType.DOUBLE,
            "Fitness time constant in days.",
        ),
        ColumnSpec(
            "tau_fatigue_days",
            ColumnType.DOUBLE,
            "Fatigue time constant in days.",
        ),
        ColumnSpec("k_fitness", ColumnType.DOUBLE, "Fitness weighting, dimensionless."),
        ColumnSpec("k_fatigue", ColumnType.DOUBLE, "Fatigue weighting, dimensionless."),
        ColumnSpec(
            "constants_provenance",
            ColumnType.VARCHAR,
            "seeds for fitdocs's shipped starting values or configured.",
        ),
        ColumnSpec(
            "coverage_threshold",
            ColumnType.DOUBLE,
            "Fraction from 0 to 1 below which a week is suppressed.",
        ),
    ),
)

DAILY_LOAD_TABLE: Final[TableSpec] = TableSpec(
    name="daily_load",
    description=(
        "One row per day of each methodology's series, from its first to its "
        "last contributing day. Equals fitdocs history --methodology "
        "<methodology>'s computation for the inputs as of the last refresh."
    ),
    columns=(
        ColumnSpec("methodology", ColumnType.VARCHAR, "Calculator id."),
        ColumnSpec("day", ColumnType.DATE, "Calendar day."),
        ColumnSpec(
            "recorded_load",
            ColumnType.DOUBLE,
            "Sum of the day's recorded loads in dimensionless load points; 0 on "
            "a day with no load, as fitdocs history counts it.",
        ),
        ColumnSpec("pages", ColumnType.INTEGER, "Pages counted that day."),
        ColumnSpec(
            "pages_with_load", ColumnType.INTEGER, "Pages carrying a load that day."
        ),
        ColumnSpec(
            "fitness",
            ColumnType.DOUBLE,
            "Fitness on the daily-average load scale; NULL on a suppressed day.",
        ),
        ColumnSpec(
            "fatigue",
            ColumnType.DOUBLE,
            "Fatigue on the daily-average load scale; NULL on a suppressed day.",
        ),
        ColumnSpec(
            "form",
            ColumnType.DOUBLE,
            "Fitness minus fatigue on the daily-average load scale; "
            "NULL on a suppressed day.",
        ),
        ColumnSpec(
            "suppressed",
            ColumnType.BOOLEAN,
            "TRUE when the day's ISO week is suppressed for low coverage.",
        ),
    ),
)

WEEKLY_LOAD_TABLE: Final[TableSpec] = TableSpec(
    name="weekly_load",
    description=(
        "One row per ISO week of each methodology's series. Equals fitdocs "
        "history --methodology <methodology>'s weekly table, unrounded, for the "
        "inputs as of the last refresh."
    ),
    columns=(
        ColumnSpec("methodology", ColumnType.VARCHAR, "Calculator id."),
        ColumnSpec("iso_year", ColumnType.INTEGER, "ISO week-numbering year."),
        ColumnSpec("iso_week", ColumnType.INTEGER, "ISO week number."),
        ColumnSpec("week_start", ColumnType.DATE, "Monday of the ISO week."),
        ColumnSpec(
            "days_in_series", ColumnType.INTEGER, "Days of the week in the series."
        ),
        ColumnSpec(
            "total_load",
            ColumnType.DOUBLE,
            "Total dimensionless load points in the week.",
        ),
        ColumnSpec(
            "sessions", ColumnType.INTEGER, "Pages carrying a load in the week."
        ),
        ColumnSpec("pages", ColumnType.INTEGER, "Pages counted in the week."),
        ColumnSpec(
            "pages_with_load", ColumnType.INTEGER, "Pages carrying a load in the week."
        ),
        ColumnSpec(
            "fitness",
            ColumnType.DOUBLE,
            "Fitness on the daily-average load scale at the week's last day; "
            "NULL when suppressed.",
        ),
        ColumnSpec(
            "fatigue",
            ColumnType.DOUBLE,
            "Fatigue on the daily-average load scale at the week's last day; "
            "NULL when suppressed.",
        ),
        ColumnSpec(
            "form",
            ColumnType.DOUBLE,
            "Form on the daily-average load scale at the week's last day; "
            "NULL when suppressed.",
        ),
        ColumnSpec(
            "suppressed",
            ColumnType.BOOLEAN,
            "TRUE when the week is suppressed for low coverage.",
        ),
    ),
)


@dataclass(frozen=True)
class LoadSeriesProducer:
    """Expose every observed history methodology as corpus-level rows."""

    name: str = "derived.load_series"
    tables: tuple[TableSpec, ...] = (
        LOAD_SERIES_TABLE,
        DAILY_LOAD_TABLE,
        WEEKLY_LOAD_TABLE,
    )

    def fingerprint(self, corpus: CorpusSnapshot) -> str:
        return digest(
            {
                "workouts": workouts_digest(corpus),
                "settings": settings_digest(corpus.data_root),
            }
        )

    def rows(self, corpus: CorpusSnapshot) -> Rows:
        inputs = read_history_inputs(corpus.data_root)
        default = select_methodology(
            inputs.scan.pages, requested=None, configured=inputs.configured
        )
        series_rows: list[Row] = []
        daily_rows: list[Row] = []
        weekly_rows: list[Row] = []
        for methodology in observed_methodologies(inputs):
            computation = compute_history(inputs, methodology=methodology)
            if computation is None:
                continue
            if (
                isinstance(default, MethodologyChoice)
                and default.methodology == methodology
            ):
                default_selection = default.source
            else:
                default_selection = None
            is_default = default_selection is not None
            series_rows.append(
                (
                    methodology,
                    is_default,
                    default_selection,
                    computation.series.start,
                    computation.series.end,
                    computation.constants.tau_fitness_days,
                    computation.constants.tau_fatigue_days,
                    computation.constants.k_fitness,
                    computation.constants.k_fatigue,
                    computation.constants.provenance.value,
                    computation.threshold,
                )
            )
            daily_rows.extend(
                (
                    methodology,
                    row.day,
                    row.recorded_load,
                    row.pages,
                    row.pages_with_load,
                    row.fitness,
                    row.fatigue,
                    row.form,
                    row.suppressed,
                )
                for row in day_rows(
                    computation.series, computation.model, computation.weeks
                )
            )
            weekly_rows.extend(
                (
                    methodology,
                    row.iso_year,
                    row.iso_week,
                    row.monday,
                    row.days_in_span,
                    row.total_load,
                    row.sessions,
                    row.pages,
                    row.pages_with_load,
                    row.fitness,
                    row.fatigue,
                    row.form,
                    row.suppressed,
                )
                for row in computation.weeks
            )
        return {
            LOAD_SERIES_TABLE.name: tuple(series_rows),
            DAILY_LOAD_TABLE.name: tuple(daily_rows),
            WEEKLY_LOAD_TABLE.name: tuple(weekly_rows),
        }


LOAD_SERIES_PRODUCER: Final[LoadSeriesProducer] = LoadSeriesProducer()
