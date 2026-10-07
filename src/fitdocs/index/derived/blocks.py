"""Project plan-resolution records into the five derived block tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs import plans
from fitdocs.index.derived.inputs import (
    digest,
    file_digest,
    page_keys,
    settings_digest,
    workouts_digest,
)
from fitdocs.index.producer import CorpusSnapshot, Row, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.settings import SettingsError

_BLOCKS_DESCRIPTION = (
    "One row per plan source the plan pass discovers. Equals the plan pass's "
    "resolution (`fitdocs plan`) on `resolved_on`, for the inputs as of the last "
    "refresh."
)
_MESOCYCLES_DESCRIPTION = (
    "One row per mesocycle of a valid block, with its actual-load picture. Equals "
    "the plan pass's resolution (`fitdocs plan`) for the inputs as of the last refresh."
)
_PLANNED_WORKOUTS_DESCRIPTION = (
    "One row per planned workout in a valid block's current plan, with its resolution. "
    "Equals the plan pass's resolution (`fitdocs plan`) for the inputs as of the "
    "last refresh."
)
_PLANNED_WORKOUT_PAGES_DESCRIPTION = (
    "One row per workout page a planned workout claims, and per page an override "
    "names that does not exist. Equals the plan pass's resolution (`fitdocs plan`) "
    "for the inputs as of the last refresh."
)
_UNPLANNED_PAGES_DESCRIPTION = (
    "One row per workout page in a mesocycle's window that no planned workout of "
    "the block claims. Equals the plan pass's resolution (`fitdocs plan`) for the "
    "inputs as of the last refresh."
)

BLOCKS_TABLE: Final[TableSpec] = TableSpec(
    "blocks",
    _BLOCKS_DESCRIPTION,
    (
        ColumnSpec("block_id", ColumnType.VARCHAR, "The plan source file's stem."),
        ColumnSpec(
            "source_path",
            ColumnType.VARCHAR,
            "The plan source path as the plan pass reports it.",
        ),
        ColumnSpec(
            "valid", ColumnType.BOOLEAN, "Whether the source parsed as a valid block."
        ),
        ColumnSpec(
            "problems", ColumnType.INTEGER, "Number of problems the plan pass reports."
        ),
        ColumnSpec(
            "title", ColumnType.VARCHAR, "Block title; NULL when the source is invalid."
        ),
        ColumnSpec(
            "goal", ColumnType.VARCHAR, "Block goal; NULL when the source is invalid."
        ),
        ColumnSpec(
            "starts_on", ColumnType.DATE, "First day; NULL when the source is invalid."
        ),
        ColumnSpec(
            "ends_on", ColumnType.DATE, "Last day; NULL when the source is invalid."
        ),
        ColumnSpec(
            "mesocycle_days",
            ColumnType.INTEGER,
            "Nominal mesocycle length in days; NULL when invalid.",
        ),
        ColumnSpec("resolved_on", ColumnType.DATE, "Date used to resolve the plan."),
    ),
)
MESOCYCLES_TABLE: Final[TableSpec] = TableSpec(
    "mesocycles",
    _MESOCYCLES_DESCRIPTION,
    (
        ColumnSpec("block_id", ColumnType.VARCHAR, "Identity of the plan block."),
        ColumnSpec(
            "mesocycle", ColumnType.INTEGER, "Mesocycle number, beginning at one."
        ),
        ColumnSpec("starts_on", ColumnType.DATE, "First day in the mesocycle."),
        ColumnSpec("ends_on", ColumnType.DATE, "Last day in the mesocycle."),
        ColumnSpec(
            "nominal_days", ColumnType.INTEGER, "Nominal mesocycle length in days."
        ),
        ColumnSpec(
            "days", ColumnType.INTEGER, "Actual inclusive mesocycle length in days."
        ),
        ColumnSpec(
            "target_load",
            ColumnType.DOUBLE,
            "Target load in dimensionless load points; NULL when unstated.",
        ),
        ColumnSpec("focus", ColumnType.VARCHAR, "Mesocycle focus; NULL when unstated."),
        ColumnSpec(
            "load_methodology",
            ColumnType.VARCHAR,
            "Methodology used for actual load; NULL when unavailable.",
        ),
        ColumnSpec(
            "actual_load",
            ColumnType.DOUBLE,
            "Actual load in dimensionless load points; NULL when absent.",
        ),
        ColumnSpec(
            "actual_load_lower_bound",
            ColumnType.BOOLEAN,
            "Whether actual load is a lower bound.",
        ),
        ColumnSpec(
            "actual_load_of_target_pct",
            ColumnType.INTEGER,
            "Actual load as a percent of target; NULL when unavailable.",
        ),
        ColumnSpec(
            "pages", ColumnType.INTEGER, "Workout pages in the mesocycle window."
        ),
        ColumnSpec("scored_pages", ColumnType.INTEGER, "Pages counted with a load."),
        ColumnSpec(
            "unscored_pages", ColumnType.INTEGER, "Counted pages without a load."
        ),
        ColumnSpec(
            "excluded_pages",
            ColumnType.INTEGER,
            "Pages excluded under another methodology.",
        ),
        ColumnSpec(
            "unplanned_pages",
            ColumnType.INTEGER,
            "Pages in the window no planned workout claims.",
        ),
    ),
)
PLANNED_WORKOUTS_TABLE: Final[TableSpec] = TableSpec(
    "planned_workouts",
    _PLANNED_WORKOUTS_DESCRIPTION,
    (
        ColumnSpec("block_id", ColumnType.VARCHAR, "Identity of the plan block."),
        ColumnSpec(
            "workout_id", ColumnType.VARCHAR, "Identity of the planned workout."
        ),
        ColumnSpec("mesocycle", ColumnType.INTEGER, "Containing mesocycle number."),
        ColumnSpec("day", ColumnType.DATE, "Planned calendar day."),
        ColumnSpec("sport", ColumnType.VARCHAR, "Planned sport."),
        ColumnSpec(
            "modality", ColumnType.VARCHAR, "Planned modality; NULL unless stated."
        ),
        ColumnSpec(
            "indoor", ColumnType.BOOLEAN, "Planned indoor flag; NULL unless stated."
        ),
        ColumnSpec("title", ColumnType.VARCHAR, "Planned workout title."),
        ColumnSpec("summary", ColumnType.VARCHAR, "Planned workout summary."),
        ColumnSpec(
            "state",
            ColumnType.VARCHAR,
            "Resolution state: matched, overridden, skipped, not logged or upcoming.",
        ),
        ColumnSpec(
            "confidence", ColumnType.VARCHAR, "Match confidence; NULL unless matched."
        ),
        ColumnSpec(
            "override_date",
            ColumnType.DATE,
            "Date of the deciding override; NULL unless overridden.",
        ),
        ColumnSpec(
            "claimed_pages", ColumnType.INTEGER, "Number of workout pages claimed."
        ),
        ColumnSpec(
            "missing_pages", ColumnType.INTEGER, "Number of named pages not found."
        ),
    ),
)
PLANNED_WORKOUT_PAGES_TABLE: Final[TableSpec] = TableSpec(
    "planned_workout_pages",
    _PLANNED_WORKOUT_PAGES_DESCRIPTION,
    (
        ColumnSpec("block_id", ColumnType.VARCHAR, "Identity of the plan block."),
        ColumnSpec(
            "workout_id", ColumnType.VARCHAR, "Identity of the planned workout."
        ),
        ColumnSpec("stem", ColumnType.VARCHAR, "Claimed workout page stem."),
        ColumnSpec(
            "path",
            ColumnType.VARCHAR,
            "Data-root-relative page path; NULL when not found.",
        ),
        ColumnSpec(
            "page_key", ColumnType.VARCHAR, "Index key; NULL when the page is not held."
        ),
        ColumnSpec("found", ColumnType.BOOLEAN, "Whether the named page exists."),
    ),
)
UNPLANNED_PAGES_TABLE: Final[TableSpec] = TableSpec(
    "unplanned_pages",
    _UNPLANNED_PAGES_DESCRIPTION,
    (
        ColumnSpec("block_id", ColumnType.VARCHAR, "Identity of the plan block."),
        ColumnSpec("mesocycle", ColumnType.INTEGER, "Containing mesocycle number."),
        ColumnSpec("stem", ColumnType.VARCHAR, "Unplanned workout page stem."),
        ColumnSpec("path", ColumnType.VARCHAR, "Data-root-relative workout page path."),
        ColumnSpec(
            "page_key", ColumnType.VARCHAR, "Index key; NULL when the page is not held."
        ),
    ),
)


@dataclass(frozen=True)
class BlockProducer:
    """Expose the plan pass's block and workout resolution as index rows."""

    name: str = "derived.blocks"
    tables: tuple[TableSpec, ...] = (
        BLOCKS_TABLE,
        MESOCYCLES_TABLE,
        PLANNED_WORKOUTS_TABLE,
        PLANNED_WORKOUT_PAGES_TABLE,
        UNPLANNED_PAGES_TABLE,
    )

    def fingerprint(self, corpus: CorpusSnapshot) -> str:
        try:
            sources = plans.read_plan_sources(corpus.data_root)
        except SettingsError as exc:
            plan_digests: str | tuple[tuple[str, str], ...] = (
                f"error:{type(exc).__name__}: {exc}"
            )
            has_sources = False
        else:
            plan_digests = tuple(
                sorted(
                    (source.entry.name, file_digest(source.entry))
                    for source in sources.sources
                )
            )
            has_sources = bool(sources.sources)
        keys = tuple(sorted(page_keys(corpus).items()))
        return digest(
            {
                "workouts": workouts_digest(corpus),
                "page_keys": keys,
                "settings": settings_digest(corpus.data_root),
                "plans": plan_digests,
                "today": corpus.today.isoformat() if has_sources else None,
            }
        )

    def rows(self, corpus: CorpusSnapshot) -> Rows:
        resolution = plans.resolve_plans(corpus.data_root, today=corpus.today)
        empty: dict[str, tuple[Row, ...]] = {table.name: () for table in self.tables}
        if not resolution.sources.sources:
            return empty

        block_rows: list[Row] = []
        mesocycle_rows: list[Row] = []
        workout_rows: list[Row] = []
        claimed_page_rows: list[Row] = []
        unplanned_rows: list[Row] = []
        reconciliations = {item.block_id: item for item in resolution.blocks}
        keys = page_keys(corpus)

        for source in resolution.sources.sources:
            block_rows.append(_block_row(source, resolution, corpus))
            block = source.block
            if block is None:
                continue
            reconciliation = reconciliations.get(block.id)
            if reconciliation is None:
                raise ValueError(f"missing reconciliation for block {block.id!r}")
            if resolution.corpus is None:
                raise ValueError(f"missing plan corpus for valid block {block.id!r}")
            if len(block.mesocycles) != len(reconciliation.mesocycles):
                raise ValueError(
                    f"mesocycle count differs for block {block.id!r}: "
                    f"{len(block.mesocycles)} != {len(reconciliation.mesocycles)}"
                )
            outcomes = {outcome.row_id: outcome for outcome in reconciliation.rows}
            for block_cycle, load_cycle in zip(
                block.mesocycles, reconciliation.mesocycles, strict=True
            ):
                if block_cycle.number != load_cycle.number:
                    raise ValueError(
                        f"mesocycle numbers differ for block {block.id!r}: "
                        f"{block_cycle.number} != {load_cycle.number}"
                    )
                mesocycle_rows.append(
                    (
                        block.id,
                        block_cycle.number,
                        block_cycle.starts,
                        block_cycle.ends,
                        block_cycle.nominal_days,
                        block_cycle.days,
                        block_cycle.target_load,
                        block_cycle.focus,
                        load_cycle.methodology,
                        load_cycle.total,
                        load_cycle.lower_bound,
                        load_cycle.percent_of_target,
                        len(load_cycle.pages),
                        len(load_cycle.scored),
                        len(load_cycle.unscored),
                        len(load_cycle.excluded),
                        len(load_cycle.unplanned),
                    )
                )
                for workout in block_cycle.workouts:
                    outcome = outcomes.get(workout.id)
                    if outcome is None:
                        raise ValueError(
                            f"missing outcome for planned workout {workout.id!r} "
                            f"in block {block.id!r}"
                        )
                    workout_rows.append(
                        (
                            block.id,
                            workout.id,
                            block_cycle.number,
                            workout.date,
                            str(workout.sport),
                            str(workout.modality)
                            if workout.modality is not None
                            else None,
                            workout.indoor,
                            workout.title,
                            workout.summary,
                            outcome.state.value,
                            outcome.confidence.value
                            if outcome.confidence is not None
                            else None,
                            outcome.override_date,
                            len(outcome.stems),
                            len(outcome.missing),
                        )
                    )
                    for stem in outcome.stems:
                        logged = resolution.corpus.by_stem(stem)
                        if logged is None:
                            raise ValueError(
                                f"claimed workout page {stem!r} is absent from "
                                "plan corpus"
                            )
                        claimed_page_rows.append(
                            (
                                block.id,
                                workout.id,
                                stem,
                                logged.path,
                                keys.get(logged.path),
                                True,
                            )
                        )
                    for stem in outcome.missing:
                        claimed_page_rows.append(
                            (block.id, workout.id, stem, None, None, False)
                        )
                for logged in load_cycle.unplanned:
                    unplanned_rows.append(
                        (
                            block.id,
                            block_cycle.number,
                            logged.stem,
                            logged.path,
                            keys.get(logged.path),
                        )
                    )

        return {
            BLOCKS_TABLE.name: tuple(block_rows),
            MESOCYCLES_TABLE.name: tuple(mesocycle_rows),
            PLANNED_WORKOUTS_TABLE.name: tuple(workout_rows),
            PLANNED_WORKOUT_PAGES_TABLE.name: tuple(claimed_page_rows),
            UNPLANNED_PAGES_TABLE.name: tuple(unplanned_rows),
        }


def _block_row(
    source: plans.ParsedSource,
    resolution: plans.PlanResolution,
    corpus: CorpusSnapshot,
) -> Row:
    block = source.block
    if block is None:
        return (
            source.block_id,
            source.source,
            False,
            len(source.problems),
            None,
            None,
            None,
            None,
            None,
            corpus.today,
        )
    reconciliation = next(
        (item for item in resolution.blocks if item.block_id == block.id), None
    )
    if reconciliation is None:
        raise ValueError(f"missing reconciliation for block {block.id!r}")
    return (
        source.block_id,
        source.source,
        True,
        len(reconciliation.problems),
        block.title,
        block.goal,
        block.starts,
        block.ends,
        block.mesocycle_days,
        corpus.today,
    )


BLOCK_PRODUCER: Final[BlockProducer] = BlockProducer()
