"""Registration, table-description and version contract for derived producers."""

from __future__ import annotations

import re

from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.derived.benchmarks import BENCHMARK_PRODUCER
from fitdocs.index.derived.blocks import BLOCK_PRODUCER
from fitdocs.index.derived.load_series import LOAD_SERIES_PRODUCER
from fitdocs.index.derived.mean_max import MEAN_MAX_PRODUCER
from fitdocs.index.registry import (
    COMPUTED_PRODUCERS,
    CORPUS_PRODUCERS,
    DOCUMENT_PRODUCERS,
    registered_tables,
)
from fitdocs.index.schema import SCHEMA_VERSION, UNIT_SUFFIXES, ColumnType


def test_derived_producers_are_registered_after_core_in_corpus_order() -> None:
    assert DOCUMENT_PRODUCERS == (CORE_DOCUMENTS,)
    assert COMPUTED_PRODUCERS == (CORE_COMPUTED, MEAN_MAX_PRODUCER)
    assert CORPUS_PRODUCERS == (
        LOAD_SERIES_PRODUCER,
        BENCHMARK_PRODUCER,
        BLOCK_PRODUCER,
    )


def test_registered_schema_has_the_exact_core_and_derived_table_order() -> None:
    assert tuple(table.name for table in registered_tables()) == (
        "index_meta",
        "index_pages",
        "index_producers",
        "pages",
        "page_sources",
        "loads",
        "quality_flags",
        "activities",
        "records",
        "laps",
        "strength_sets",
        "zone_times",
        "channel_sources",
        "mean_max",
        "load_series",
        "daily_load",
        "weekly_load",
        "benchmarks",
        "benchmark_periods",
        "blocks",
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    )
    assert len(registered_tables()) == 24


def test_derived_descriptions_and_units_are_complete() -> None:
    derived_names = {
        "mean_max",
        "load_series",
        "daily_load",
        "weekly_load",
        "benchmarks",
        "benchmark_periods",
        "blocks",
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    }
    producers = (
        MEAN_MAX_PRODUCER,
        LOAD_SERIES_PRODUCER,
        BENCHMARK_PRODUCER,
        BLOCK_PRODUCER,
    )
    derived_tables = tuple(table for item in producers for table in item.tables)
    assert {table.name for table in derived_tables} == derived_names

    for table in derived_tables:
        assert table.description.strip()
        for column in table.columns:
            assert column.type is not ColumnType.TIMESTAMP
            assert column.description.strip()
            matching_units = tuple(
                (suffix, unit)
                for suffix, unit in UNIT_SUFFIXES
                if column.name.endswith(suffix)
            )
            if matching_units:
                unit = max(matching_units, key=lambda entry: len(entry[0]))[1]
                description_words = re.findall(
                    r"[^\W_]+", column.description.casefold()
                )
                unit_words = re.findall(r"[^\W_]+", unit.casefold())
                width = len(unit_words)
                assert any(
                    description_words[index : index + width] == unit_words
                    for index in range(len(description_words) - width + 1)
                )


def test_each_corpus_table_states_its_engine_agreement_and_refresh_boundary() -> None:
    producer_tables = {
        "load_series": (
            ("load_series", "daily_load", "weekly_load"),
            LOAD_SERIES_PRODUCER.tables,
        ),
        "benchmarks": (
            ("benchmarks", "benchmark_periods"),
            BENCHMARK_PRODUCER.tables,
        ),
        "blocks": (
            (
                "blocks",
                "mesocycles",
                "planned_workouts",
                "planned_workout_pages",
                "unplanned_pages",
            ),
            BLOCK_PRODUCER.tables,
        ),
    }
    agreement_phrases = (
        "fitdocs history --methodology",
        "the athlete profile's own",
        "fitdocs plan",
    )
    producer_phrase = {
        "load_series": agreement_phrases[0],
        "benchmarks": agreement_phrases[1],
        "blocks": agreement_phrases[2],
    }

    for producer, (names, specs) in producer_tables.items():
        tables = {table.name: table for table in specs}
        assert set(tables) == set(names)
        for name in names:
            description = tables[name].description.casefold()
            assert "as of the last refresh" in description
            assert sum(description.count(phrase) for phrase in agreement_phrases) == 1
            assert description.count(producer_phrase[producer]) == 1


def test_registered_schema_version_advances_to_two() -> None:
    assert SCHEMA_VERSION == 2
