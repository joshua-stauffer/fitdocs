"""Synthetic workout trees produced by the real sync engine."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.docio import read_frontmatter
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import sync
from tests.fixtures import builder, merge


class _SyntheticTiles:
    attribution = "Synthetic map fixture"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"synthetic-png" for ref in refs}


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
