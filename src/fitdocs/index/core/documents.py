"""Document-tier index rows sourced from a workout page."""

from __future__ import annotations

from typing import Final

from fitdocs import contract
from fitdocs.contract import EffortTag, InvalidEffortTag
from fitdocs.index.producer import (
    DocumentProducer,
    LoadRegionReading,
    PageDocument,
    Row,
    Rows,
)
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec

PAGES: Final[TableSpec] = TableSpec(
    "pages",
    "one row per workout page; the page's frontmatter as recorded.",
    (
        ColumnSpec("path", ColumnType.VARCHAR, "data-root-relative POSIX path"),
        ColumnSpec("title", ColumnType.VARCHAR, "Workout page title"),
        ColumnSpec("doc_version", ColumnType.INTEGER, "document-format version"),
        ColumnSpec(
            "uuid", ColumnType.VARCHAR, "session UUID; NULL when no file recorded one"
        ),
        ColumnSpec("date", ColumnType.DATE, "document date, local"),
        ColumnSpec("start_time_local", ColumnType.TIMESTAMP, "local wall-clock start"),
        ColumnSpec("sport", ColumnType.VARCHAR, "Document sport label"),
        ColumnSpec("modality", ColumnType.VARCHAR, "Document movement modality"),
        ColumnSpec(
            "indoor",
            ColumnType.BOOLEAN,
            "TRUE when the page records an indoor flag; NULL otherwise, because the "
            "key is written only when true",
        ),
        ColumnSpec("source_kind", ColumnType.VARCHAR, "Base source kind"),
        ColumnSpec(
            "source_elapsed_s", ColumnType.DOUBLE, "Elapsed source time in seconds"
        ),
        ColumnSpec("source_distance_m", ColumnType.DOUBLE, "Source distance in metres"),
        ColumnSpec("source_device", ColumnType.VARCHAR, "device digest"),
        ColumnSpec(
            "load_status",
            ColumnType.VARCHAR,
            "`computed`, `unsupported`, `not_computed` or `unreadable`",
        ),
        ColumnSpec(
            "load_value",
            ColumnType.DOUBLE,
            "the selected load as frontmatter records it; dimensionless load points",
        ),
        ColumnSpec("load_methodology", ColumnType.VARCHAR, "calculator id"),
        ColumnSpec("load_basis", ColumnType.VARCHAR, "the selected channel"),
        ColumnSpec(
            "effort",
            ColumnType.VARCHAR,
            "`race`, `test` or `hard`; NULL when there is no valid tag",
        ),
        ColumnSpec("effort_distance_m", ColumnType.DOUBLE, "Effort distance in metres"),
        ColumnSpec("effort_time_s", ColumnType.DOUBLE, "Effort time in seconds"),
        ColumnSpec("effort_event", ColumnType.VARCHAR, "the event label as recorded"),
        ColumnSpec(
            "effort_invalid",
            ColumnType.BOOLEAN,
            "TRUE when an effort key is present but the tag is invalid by "
            "`fitdocs check`'s rule",
        ),
    ),
)
PAGE_SOURCES: Final[TableSpec] = TableSpec(
    "page_sources",
    "one row per listed file.",
    (
        ColumnSpec(
            "position",
            ColumnType.INTEGER,
            "1-based in listed order, ascending rank, base last",
        ),
        ColumnSpec("ref", ColumnType.VARCHAR, "archive reference as listed"),
        ColumnSpec(
            "sha256",
            ColumnType.VARCHAR,
            "content hash the reference names; NULL when the reference is not an "
            "archive reference",
        ),
        ColumnSpec("role", ColumnType.VARCHAR, "`base` or `extra`"),
    ),
)
LOADS: Final[TableSpec] = TableSpec(
    "loads",
    "one row per channel a computed load result reports.",
    (
        ColumnSpec("calculator_id", ColumnType.VARCHAR, "Load calculator identifier"),
        ColumnSpec(
            "channel",
            ColumnType.VARCHAR,
            "`power`, `heart_rate` or `pace` for the built-in calculator",
        ),
        ColumnSpec(
            "selected",
            ColumnType.BOOLEAN,
            "Whether this channel is the selected load basis",
        ),
        ColumnSpec(
            "load_value",
            ColumnType.DOUBLE,
            "dimensionless; NULL when the result records the channel as not computable",
        ),
    ),
)
QUALITY_FLAGS: Final[TableSpec] = TableSpec(
    "quality_flags",
    "one row per flag a computed load result records.",
    (
        ColumnSpec("flag", ColumnType.VARCHAR, "flag key"),
        ColumnSpec(
            "verdict",
            ColumnType.VARCHAR,
            "`detected`, `not-detected` or `not-assessed`",
        ),
    ),
)


def _load_rows(reading: LoadRegionReading) -> tuple[tuple[Row, ...], tuple[Row, ...]]:
    if reading.status != "computed" or reading.payload is None:
        return (), ()
    result = reading.payload.result
    if result is None:
        return (), ()
    loads: tuple[Row, ...] = (
        (result.calculator_id, result.basis, True, result.value),
        *(
            (result.calculator_id, item.key, False, item.value)
            for item in result.non_selected
        ),
    )
    flags = tuple((flag.key, flag.verdict) for flag in result.flags)
    return loads, flags


class _CoreDocuments:
    name = "core.documents"
    tables = (PAGES, PAGE_SOURCES, LOADS, QUALITY_FLAGS)

    def rows(self, page: PageDocument) -> Rows:
        fm = page.frontmatter
        identity = contract.document_source_identity(fm)
        effort = contract.effort_tag(fm)
        load = contract.document_load(fm)
        basis = contract.document_load_basis(fm)
        title_value = fm.get("title")
        title = title_value if isinstance(title_value, str) else None
        effort_values = (
            (effort.kind.value, effort.distance_m, effort.time_s, effort.event, False)
            if isinstance(effort, EffortTag)
            else (None, None, None, None, isinstance(effort, InvalidEffortTag))
        )
        recorded_start_time = contract.document_start_time(fm)
        page_row: Row = (
            page.path,
            title,
            contract.document_version(fm),
            contract.document_uuid(fm),
            contract.document_date(fm),
            recorded_start_time.replace(tzinfo=None)
            if recorded_start_time is not None
            else None,
            contract.document_sport(fm),
            contract.document_modality(fm),
            contract.document_indoor(fm),
            identity.kind,
            identity.elapsed_s,
            identity.distance_m,
            identity.device,
            page.load.status,
            load.value if load is not None else None,
            load.methodology if load is not None else None,
            basis,
            *effort_values,
        )
        refs = contract.source_refs(fm)
        source_rows = tuple(
            (
                position,
                ref,
                contract.sha_of_ref(ref),
                "base" if position == len(refs) else "extra",
            )
            for position, ref in enumerate(refs, 1)
        )
        load_rows, flag_rows = _load_rows(page.load)
        return {
            "pages": (page_row,),
            "page_sources": source_rows,
            "loads": load_rows,
            "quality_flags": flag_rows,
        }


CORE_DOCUMENTS: Final[DocumentProducer] = _CoreDocuments()
