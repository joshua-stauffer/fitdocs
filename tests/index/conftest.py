"""Synthetic workout trees produced by the real sync engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta, timezone
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.docio import read_frontmatter
from fitdocs.index import registry
from fitdocs.index.bookkeeping import IndexMeta
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.refresh import RefreshInputs, reconcile
from fitdocs.index.schema import SCHEMA_VERSION, ResolvedTable
from fitdocs.index.store import (
    create_index,
    create_schema,
    duckdb_version,
    read_bookkeeping,
    write_meta,
)
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import sync
from fitdocs.version import tool_version
from tests.fixtures import builder, merge


class _SyntheticTiles:
    attribution = "Synthetic map fixture"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"synthetic-png" for ref in refs}


@dataclass(frozen=True)
class BuiltIndex:
    data_root: Path
    database: Path
    tables: tuple[ResolvedTable, ...]


@pytest.fixture
def core_registry(monkeypatch: pytest.MonkeyPatch) -> tuple[ResolvedTable, ...]:
    from fitdocs.index.core.computed import CORE_COMPUTED
    from fitdocs.index.core.documents import CORE_DOCUMENTS

    monkeypatch.setattr(registry, "DOCUMENT_PRODUCERS", (CORE_DOCUMENTS,))
    monkeypatch.setattr(registry, "COMPUTED_PRODUCERS", (CORE_COMPUTED,))
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", ())
    return registry.registered_tables()


@pytest.fixture
def built_index(tmp_path: Path, core_registry: tuple[ResolvedTable, ...]) -> BuiltIndex:
    data_root = tmp_path / "empty-data"
    data_root.mkdir()
    database = tmp_path / "index.duckdb"
    today = date(2026, 10, 6)
    with create_index(database) as connection:
        create_schema(connection, core_registry)
        write_meta(
            connection,
            IndexMeta(
                schema_version=SCHEMA_VERSION,
                fitdocs_version=tool_version(),
                duckdb_version=duckdb_version(),
                data_root=str(data_root.resolve()),
                athlete_fingerprint=athlete_fingerprint(None),
            ),
        )
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
        assert bookkeeping.pages == {}
        initial = reconcile(
            connection,
            bookkeeping,
            RefreshInputs(data_root, None, None, today, None),
        )
        assert initial.added == ()
        assert initial.pages_held == 0
    return BuiltIndex(data_root, database, core_registry)


@pytest.fixture
def synced_corpus(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    data_root = tmp_path / "data"
    data_root.mkdir()
    healthfit, stryd = merge.run_pair_fit_bytes()
    files = {
        "run/healthfit.fit": healthfit,
        "run/stryd.fit": stryd,
        "ride.fit": builder.ride_fit_bytes(),
    }
    for relative, payload in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    report = sync(
        source,
        data_root,
        athlete=None,
        tz=timezone(timedelta(hours=-6)),
        tiles=_SyntheticTiles(),
    )
    assert report.failures == ()
    return data_root


@pytest.fixture
def synced_workout_pages(synced_corpus: Path) -> tuple[Path, ...]:
    workout_dir = synced_corpus / WORKOUTS_DIR
    pages = tuple(
        path
        for path in sorted(workout_dir.glob("*.md"))
        if contract.is_workout_document(read_frontmatter(path))
    )
    assert len(pages) == 2
    assert any(
        len(contract.source_refs(read_frontmatter(path) or {})) == 2 for path in pages
    )
    return pages
