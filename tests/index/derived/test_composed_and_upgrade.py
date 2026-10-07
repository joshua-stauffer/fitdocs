"""Pin composed best efforts and the schema-version rebuild path."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from fitdocs import parse_fit
from fitdocs.contract import sha_of_ref
from fitdocs.index import registry
from fitdocs.index.derived.benchmarks import (
    BENCHMARK_PERIODS_TABLE,
    BENCHMARKS_TABLE,
)
from fitdocs.index.derived.blocks import (
    BLOCKS_TABLE,
    MESOCYCLES_TABLE,
    PLANNED_WORKOUT_PAGES_TABLE,
    PLANNED_WORKOUTS_TABLE,
    UNPLANNED_PAGES_TABLE,
)
from fitdocs.index.derived.load_series import (
    DAILY_LOAD_TABLE,
    LOAD_SERIES_TABLE,
    WEEKLY_LOAD_TABLE,
)
from fitdocs.index.derived.mean_max import MEAN_MAX_TABLE
from fitdocs.index.location import resolve_index_location
from fitdocs.index.refresh import Outcome
from fitdocs.index.schema import SCHEMA_VERSION
from fitdocs.index.store import open_index
from fitdocs.layout import source_ref
from fitdocs.metrics.mean_max import MeanMaxChannel, mean_max_curve
from fitdocs.sync import RenderedPage
from tests.index.derived.conftest import (
    TODAY,
    _index_args,
    build_fixture_root,
    build_index,
    read_table,
    refresh,
    sync_with_handoff,
)

DERIVED_TABLES = (
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


def test_handoff_composition_adds_heart_rate_best_efforts(
    tmp_path: Path,
    composed_source: Path,
) -> None:
    root = build_fixture_root(tmp_path / "composed", composed=True)
    initial = build_index(root, today=TODAY)
    assert initial.outcome is Outcome.BUILT
    environ, home = _index_args(root, TODAY)
    location = resolve_index_location(root, environ, home)
    with open_index(location.database, read_only=True) as conn:
        stored_types = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'mean_max' "
            "AND column_name IN ('duration_s', 'heart_rate_bpm', "
            "'heart_rate_start_s') ORDER BY ordinal_position"
        ).fetchall()
    assert stored_types == [
        ("duration_s", "INTEGER"),
        ("heart_rate_bpm", "DOUBLE"),
        ("heart_rate_start_s", "DOUBLE"),
    ]

    base_bytes = (composed_source / "ride/garmin.fit").read_bytes()
    base = parse_fit(base_bytes)
    assert base.samples
    assert all(value is None for value in base.samples.heart_rate_bpm)

    base_ref = source_ref(hashlib.sha256(base_bytes).hexdigest())
    extra_bytes = (composed_source / "ride/healthfit.fit").read_bytes()
    extra_ref = source_ref(hashlib.sha256(extra_bytes).hexdigest())
    page_key = sha_of_ref(base_ref)
    assert page_key is not None

    report, refreshed, collector = sync_with_handoff(root, composed_source, today=TODAY)
    assert report.written
    assert refreshed.outcome is Outcome.REFRESHED
    composed_page = collector.take(page_key, (extra_ref, base_ref))
    assert isinstance(composed_page, RenderedPage)
    samples = composed_page.composition.activity.samples
    assert any(value is not None for value in samples.heart_rate_bpm)

    expected = tuple(
        (point.duration_s, point.value, point.start_s)
        for point in mean_max_curve(samples, MeanMaxChannel.HEART_RATE)
        if point.value is not None
    )
    assert expected
    all_rows = read_table(root, MEAN_MAX_TABLE.name)
    composed_rows = tuple(row for row in all_rows if row[0] == page_key)
    actual = tuple(
        (row[1], row[6], row[7]) for row in composed_rows if row[6] is not None
    )
    assert actual
    assert actual == expected


def test_earlier_schema_refresh_requests_rebuild_then_build_populates_every_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_fixture_root(tmp_path / "schema-upgrade", composed=True)
    environ, home = _index_args(root, TODAY)
    location = resolve_index_location(root, environ, home)
    with monkeypatch.context() as core_only_registry:
        core_only_registry.setattr(
            registry, "DOCUMENT_PRODUCERS", registry.DOCUMENT_PRODUCERS[:1]
        )
        core_only_registry.setattr(
            registry, "COMPUTED_PRODUCERS", registry.COMPUTED_PRODUCERS[:1]
        )
        core_only_registry.setattr(registry, "CORPUS_PRODUCERS", ())

        core_only = build_index(root, today=TODAY)
        assert core_only.outcome is Outcome.BUILT
        with open_index(location.database, read_only=True) as conn:
            meta = conn.execute("SELECT schema_version FROM index_meta").fetchall()[0]
            existing = {
                str(name)
                for (name,) in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
        assert meta == (SCHEMA_VERSION,)
        assert existing.isdisjoint(DERIVED_TABLES)

        _, initial_refresh, _ = sync_with_handoff(
            root, root / "composed-source", today=TODAY
        )
        assert initial_refresh.outcome is Outcome.REFRESHED

        with open_index(location.database, read_only=True) as conn:
            existing_after_sync = {
                str(name)
                for (name,) in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
        assert existing_after_sync.isdisjoint(DERIVED_TABLES)

    with open_index(location.database, read_only=False) as conn:
        conn.execute("UPDATE index_meta SET schema_version = ?", [SCHEMA_VERSION - 1])

    stale = refresh(root, today=TODAY)
    assert stale.outcome is Outcome.NEEDS_REBUILD
    assert stale.detail is not None
    assert f"schema version {SCHEMA_VERSION - 1}" in stale.detail
    assert f"this fitdocs uses {SCHEMA_VERSION}" in stale.detail

    upgraded = build_index(root, today=TODAY)
    assert upgraded.outcome is Outcome.BUILT
    with open_index(location.database, read_only=True) as conn:
        present = {
            str(name)
            for (name,) in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
    assert set(DERIVED_TABLES) <= present
    for table in DERIVED_TABLES:
        rows = read_table(root, table)
        assert rows, f"{table} must be physically present and populated after upgrade"

    assert (
        tuple(
            table.name
            for table in (
                MEAN_MAX_TABLE,
                LOAD_SERIES_TABLE,
                DAILY_LOAD_TABLE,
                WEEKLY_LOAD_TABLE,
                BENCHMARKS_TABLE,
                BENCHMARK_PERIODS_TABLE,
                BLOCKS_TABLE,
                MESOCYCLES_TABLE,
                PLANNED_WORKOUTS_TABLE,
                PLANNED_WORKOUT_PAGES_TABLE,
                UNPLANNED_PAGES_TABLE,
            )
        )
        == DERIVED_TABLES
    )
