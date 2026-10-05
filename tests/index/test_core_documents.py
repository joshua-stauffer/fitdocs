from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any, cast

import pytest

from fitdocs.docmerge import extract_regions, region_block
from fitdocs.index.producer import LoadRegionReading, LoadStatus, PageDocument
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec, resolve_tables
from fitdocs.load.render import LoadPayload, encode_payload, parse_payload
from fitdocs.load.types import LoadResult, NonSelectedValue, QualityFlag
from tests.render.test_golden_docs import _render


def _column(name: str, kind: ColumnType, description: str) -> ColumnSpec:
    return ColumnSpec(name, kind, description)


EXPECTED_TABLES = (
    TableSpec(
        "pages",
        "one row per workout page; the page's frontmatter as recorded.",
        (
            _column("path", ColumnType.VARCHAR, "data-root-relative POSIX path"),
            _column("title", ColumnType.VARCHAR, "Workout page title"),
            _column("doc_version", ColumnType.INTEGER, "document-format version"),
            _column(
                "uuid",
                ColumnType.VARCHAR,
                "session UUID; NULL when no file recorded one",
            ),
            _column("date", ColumnType.DATE, "document date, local"),
            _column("start_time_local", ColumnType.TIMESTAMP, "local wall-clock start"),
            _column("sport", ColumnType.VARCHAR, "Document sport label"),
            _column("modality", ColumnType.VARCHAR, "Document movement modality"),
            _column(
                "indoor",
                ColumnType.BOOLEAN,
                "TRUE when the page records an indoor flag; NULL otherwise, "
                "because the key is written only when true",
            ),
            _column("source_kind", ColumnType.VARCHAR, "Base source kind"),
            _column(
                "source_elapsed_s", ColumnType.DOUBLE, "Elapsed source time in seconds"
            ),
            _column(
                "source_distance_m", ColumnType.DOUBLE, "Source distance in metres"
            ),
            _column("source_device", ColumnType.VARCHAR, "device digest"),
            _column(
                "load_status",
                ColumnType.VARCHAR,
                "`computed`, `unsupported`, `not_computed` or `unreadable`",
            ),
            _column(
                "load_value",
                ColumnType.DOUBLE,
                "the selected load as frontmatter records it; dimensionless load "
                "points",
            ),
            _column("load_methodology", ColumnType.VARCHAR, "calculator id"),
            _column("load_basis", ColumnType.VARCHAR, "the selected channel"),
            _column(
                "effort",
                ColumnType.VARCHAR,
                "`race`, `test` or `hard`; NULL when there is no valid tag",
            ),
            _column(
                "effort_distance_m", ColumnType.DOUBLE, "Effort distance in metres"
            ),
            _column("effort_time_s", ColumnType.DOUBLE, "Effort time in seconds"),
            _column("effort_event", ColumnType.VARCHAR, "the event label as recorded"),
            _column(
                "effort_invalid",
                ColumnType.BOOLEAN,
                "TRUE when an effort key is present but the tag is invalid by "
                "`fitdocs check`'s rule",
            ),
        ),
    ),
    TableSpec(
        "page_sources",
        "one row per listed file.",
        (
            _column(
                "position",
                ColumnType.INTEGER,
                "1-based in listed order, ascending rank, base last",
            ),
            _column("ref", ColumnType.VARCHAR, "archive reference as listed"),
            _column(
                "sha256",
                ColumnType.VARCHAR,
                "content hash the reference names; NULL when the reference is not an "
                "archive reference",
            ),
            _column("role", ColumnType.VARCHAR, "`base` or `extra`"),
        ),
    ),
    TableSpec(
        "loads",
        "one row per channel a computed load result reports.",
        (
            _column("calculator_id", ColumnType.VARCHAR, "Load calculator identifier"),
            _column(
                "channel",
                ColumnType.VARCHAR,
                "`power`, `heart_rate` or `pace` for the built-in calculator",
            ),
            _column(
                "selected",
                ColumnType.BOOLEAN,
                "Whether this channel is the selected load basis",
            ),
            _column(
                "load_value",
                ColumnType.DOUBLE,
                "dimensionless; NULL when the result records the channel as not "
                "computable",
            ),
        ),
    ),
    TableSpec(
        "quality_flags",
        "one row per flag a computed load result records.",
        (
            _column("flag", ColumnType.VARCHAR, "flag key"),
            _column(
                "verdict",
                ColumnType.VARCHAR,
                "`detected`, `not-detected` or `not-assessed`",
            ),
        ),
    ),
)


def _page(
    *,
    frontmatter: dict[str, object],
    load: LoadRegionReading,
    sources: tuple[str, ...] = ("fit-archive/" + "a" * 64 + ".fit", "phone-export.fit"),
) -> PageDocument:
    rendered = _render("strength_no_sets")
    regions = extract_regions(rendered.markdown)
    text = rendered.markdown.replace(
        region_block("notes", regions["notes"]),
        region_block("notes", "distinct user notes marker"),
    ).replace(
        region_block("workout", regions["workout"]),
        region_block("workout", "distinct workout marker"),
    )
    return PageDocument(
        page_key="b" * 64,
        path="workouts/2021-09-07-strength-1946.md",
        text=text,
        frontmatter={**frontmatter, "sources": list(sources)},
        sources=sources,
        load=load,
    )


def _computed_payload(
    *, selected_value: float = 17.25, heart_rate_value: float | None = 31.5
) -> LoadPayload:
    encoded = encode_payload(
        LoadPayload(
            "computed",
            LoadResult(
                calculator_id="calc-main",
                display_name="Main Calculator",
                value=selected_value,
                basis="power",
                non_selected=(
                    NonSelectedValue(
                        "heart_rate", "Heart Rate", heart_rate_value, "different method"
                    ),
                    NonSelectedValue("pace", "Pace", None, "no pace channel"),
                ),
                flags=(
                    QualityFlag(
                        "cadence-lock", "Cadence lock", "detected", "distinct detail"
                    ),
                    QualityFlag(
                        "missing-gps", "GPS coverage", "not-assessed", "another detail"
                    ),
                ),
                inputs_used=(("input", "9.75"),),
                notes=("private load note",),
            ),
            None,
        )
    )
    payload = parse_payload(encoded)
    assert payload is not None
    return payload


def _frontmatter(**extra: object) -> dict[str, object]:
    return {
        "title": "Synthetic page title",
        "doc_version": 7,
        "date": "2021-09-07",
        "start_time": "2021-09-07T19:46:40-06:00",
        "sport": "cycling",
        "modality": "bike",
        "source_kind": "garmin",
        "source_elapsed_s": 95.5,
        "source_distance_m": 1203.25,
        "source_device": "digest-unique",
        "load_value": 8.75,
        "load_methodology": "frontmatter-calc",
        "load_basis": "frontmatter-channel",
        **extra,
    }


def _producer() -> Any:
    from fitdocs.index.core.documents import CORE_DOCUMENTS

    return CORE_DOCUMENTS


def test_tables_pin_all_columns_and_resolved_page_key() -> None:
    producer = _producer()
    assert producer.name == "core.documents"
    assert producer.tables == EXPECTED_TABLES
    resolved = resolve_tables((producer,), (), (), ())
    assert tuple(table.name for table in resolved) == (
        "pages",
        "page_sources",
        "loads",
        "quality_flags",
    )
    for spec, table in zip(EXPECTED_TABLES, resolved, strict=True):
        assert table.producer == "core.documents"
        assert tuple(
            (c.name, c.type, c.description) for c in table.columns[1:]
        ) == tuple((c.name, c.type, c.description) for c in spec.columns)
        assert table.columns[0].name == "page_key"


def test_computed_page_has_exact_rows_and_preserves_absence() -> None:
    payload = _computed_payload()
    page = _page(
        frontmatter=_frontmatter(
            effort="hard",
            effort_distance_m=400.5,
            effort_time_s=91.25,
            effort_event="hill repeats",
            indoor=True,
        ),
        load=LoadRegionReading("computed", payload),
    )
    rows = _producer().rows(page)
    assert page.frontmatter["load_basis"] == "frontmatter-channel"
    assert payload.result is not None
    assert payload.result.basis == "power"
    assert set(rows) == {"pages", "page_sources", "loads", "quality_flags"}
    assert all(
        len(row) == len(spec.columns)
        for spec in EXPECTED_TABLES
        for row in rows[spec.name]
    )
    assert rows["pages"] == (
        (
            page.path,
            "Synthetic page title",
            7,
            None,
            date(2021, 9, 7),
            datetime(2021, 9, 7, 19, 46, 40),
            "cycling",
            "bike",
            True,
            "garmin",
            95.5,
            1203.25,
            "digest-unique",
            "computed",
            8.75,
            "frontmatter-calc",
            "frontmatter-channel",
            "hard",
            400.5,
            91.25,
            "hill repeats",
            False,
        ),
    )
    assert rows["page_sources"] == (
        (1, "fit-archive/" + "a" * 64 + ".fit", "a" * 64, "extra"),
        (2, "phone-export.fit", None, "base"),
    )
    assert rows["loads"] == (
        ("calc-main", "power", True, 17.25),
        ("calc-main", "heart_rate", False, 31.5),
        ("calc-main", "pace", False, None),
    )
    assert rows["quality_flags"] == (
        ("cadence-lock", "detected"),
        ("missing-gps", "not-assessed"),
    )


def test_notes_and_workout_region_text_is_not_emitted() -> None:
    page = _page(
        frontmatter=_frontmatter(), load=LoadRegionReading("not_computed", None)
    )
    regions = extract_regions(page.text)
    assert regions["notes"] == "distinct user notes marker"
    assert regions["workout"] == "distinct workout marker"
    rows = _producer().rows(page)
    serialized = repr(rows)
    assert "distinct user notes marker" not in serialized
    assert "distinct workout marker" not in serialized


@pytest.mark.parametrize("status", ("unsupported", "not_computed", "unreadable"))
def test_noncomputed_status_is_preserved_without_load_rows(status: LoadStatus) -> None:
    payload = _computed_payload() if status == "unsupported" else None
    page = _page(frontmatter=_frontmatter(), load=LoadRegionReading(status, payload))
    rows = _producer().rows(page)
    assert rows["pages"][0][13] == status
    assert rows["pages"][0][16] == "frontmatter-channel"
    assert rows["loads"] == ()
    assert rows["quality_flags"] == ()


def test_invalid_effort_is_null_and_absent_identity_stays_absent() -> None:
    page = _page(
        frontmatter=_frontmatter(effort="too-hard", effort_distance_m=15),
        load=LoadRegionReading("unsupported", None),
        sources=("manual-file.fit",),
    )
    rows = _producer().rows(page)
    assert rows["pages"] == (
        (
            page.path,
            "Synthetic page title",
            7,
            None,
            date(2021, 9, 7),
            datetime(2021, 9, 7, 19, 46, 40),
            "cycling",
            "bike",
            None,
            "garmin",
            95.5,
            1203.25,
            "digest-unique",
            "unsupported",
            8.75,
            "frontmatter-calc",
            "frontmatter-channel",
            None,
            None,
            None,
            None,
            True,
        ),
    )
    assert rows["page_sources"] == ((1, "manual-file.fit", None, "base"),)


def test_untagged_effort_and_absent_optional_frontmatter_are_null() -> None:
    frontmatter = _frontmatter()
    for key in (
        "date",
        "start_time",
        "sport",
        "modality",
        "indoor",
        "uuid",
        "source_kind",
        "source_elapsed_s",
        "source_distance_m",
        "source_device",
        "load_value",
        "load_methodology",
        "load_basis",
    ):
        frontmatter.pop(key, None)
    rows = _producer().rows(
        _page(
            frontmatter=frontmatter,
            load=LoadRegionReading("not_computed", None),
            sources=(),
        )
    )
    row = rows["pages"][0]
    assert row[3:9] == (None, None, None, None, None, None)
    assert row[9:13] == (None, None, None, None)
    assert row[13:17] == ("not_computed", None, None, None)
    assert row[17:22] == (None, None, None, None, False)
    assert rows["page_sources"] == ()


def test_present_uuid_and_absent_title_and_document_version_are_preserved() -> None:
    frontmatter = _frontmatter(uuid="recorded-session-42")
    frontmatter.pop("title")
    frontmatter.pop("doc_version")
    page = _page(
        frontmatter=frontmatter,
        load=LoadRegionReading("unreadable", None),
        sources=(),
    )

    row = _producer().rows(page)["pages"][0]

    assert row[1:4] == (None, None, "recorded-session-42")


def test_valid_bare_effort_keeps_optional_values_absent() -> None:
    page = _page(
        frontmatter=_frontmatter(effort="race"),
        load=LoadRegionReading("not_computed", None),
        sources=(),
    )

    assert _producer().rows(page)["pages"][0][17:22] == (
        "race",
        None,
        None,
        None,
        False,
    )


def test_real_frontmatter_selected_and_nonselected_zeros_are_preserved() -> None:
    page = _page(
        frontmatter=_frontmatter(load_value=0.0),
        load=LoadRegionReading(
            "computed",
            _computed_payload(selected_value=0.0, heart_rate_value=0.0),
        ),
        sources=(),
    )

    rows = _producer().rows(page)

    assert rows["pages"][0][14] == 0.0
    assert rows["loads"] == (
        ("calc-main", "power", True, 0.0),
        ("calc-main", "heart_rate", False, 0.0),
        ("calc-main", "pace", False, None),
    )


def test_selected_none_remains_none() -> None:
    payload = _computed_payload()
    assert payload.result is not None
    selected_none_result = replace(payload.result, value=cast(float, None))
    page = _page(
        frontmatter=_frontmatter(),
        load=LoadRegionReading(
            "computed", LoadPayload("computed", selected_none_result, None)
        ),
        sources=(),
    )

    assert _producer().rows(page)["loads"][0] == ("calc-main", "power", True, None)


@pytest.mark.parametrize(
    "payload",
    (None, LoadPayload("computed", None, None)),
    ids=("missing-payload", "missing-result"),
)
def test_computed_missing_payload_or_result_has_no_load_rows(
    payload: LoadPayload | None,
) -> None:
    page = _page(
        frontmatter=_frontmatter(),
        load=LoadRegionReading("computed", payload),
        sources=(),
    )

    try:
        rows = _producer().rows(page)
    except AttributeError as error:
        pytest.fail(f"nullable computed load input must be handled: {error}")

    assert rows["loads"] == ()
    assert rows["quality_flags"] == ()


def test_source_hash_roles_cover_archive_base_and_nonarchive_extra() -> None:
    archive_ref = "fit-archive/" + "c" * 64 + ".fit"
    page = _page(
        frontmatter=_frontmatter(),
        load=LoadRegionReading("not_computed", None),
        sources=("nonarchive-extra.fit", archive_ref),
    )

    assert _producer().rows(page)["page_sources"] == (
        (1, "nonarchive-extra.fit", None, "extra"),
        (2, archive_ref, "c" * 64, "base"),
    )


@pytest.mark.parametrize("invalid_field", ("load_value", "load_methodology"))
def test_recorded_basis_is_independent_of_unusable_frontmatter_load(
    invalid_field: str,
) -> None:
    frontmatter = _frontmatter(load_basis="recorded-independent-basis")
    if invalid_field == "load_value":
        frontmatter.pop("load_value")
    else:
        frontmatter["load_methodology"] = 42
    page = _page(
        frontmatter=frontmatter,
        load=LoadRegionReading("unreadable", None),
        sources=(),
    )

    assert _producer().rows(page)["pages"][0][14:17] == (
        None,
        None,
        "recorded-independent-basis",
    )
