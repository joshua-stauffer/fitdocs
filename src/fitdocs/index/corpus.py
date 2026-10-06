"""Read workout pages once and build the corpus hand-off for index producers."""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from fitdocs import contract, docio
from fitdocs.index import fingerprint
from fitdocs.index.producer import (
    CorpusLeftOut,
    CorpusPage,
    CorpusSnapshot,
    LoadRegionReading,
)
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import docedit
from fitdocs.load.docedit import RegionState

LeftOutReason = Literal["no_base_reference", "duplicate_base"]


@dataclass(frozen=True)
class ScannedPage:
    page_key: str
    path: str
    text: str
    frontmatter: Mapping[str, object]
    sources: tuple[str, ...]
    document_fingerprint: str


@dataclass(frozen=True)
class LeftOutPage:
    path: str
    reason: LeftOutReason
    collides_with: str | None
    document_fingerprint: str


@dataclass(frozen=True)
class CorpusScan:
    pages: tuple[ScannedPage, ...]
    left_out: tuple[LeftOutPage, ...]


def scan_workout_pages(data_root: Path) -> CorpusScan:
    """Read sorted workout markdown once, keeping only unique archive bases."""
    pages: list[ScannedPage] = []
    left_out: list[LeftOutPage] = []
    first_path_by_key: dict[str, str] = {}
    workout_dir = data_root / WORKOUTS_DIR
    for path in sorted(workout_dir.glob("*.md")):
        document = docio.read_document(path)
        if document is None or not contract.is_workout_document(document.frontmatter):
            continue
        frontmatter = document.frontmatter
        assert frontmatter is not None
        relative_path = path.relative_to(data_root).as_posix()
        doc_fingerprint = fingerprint.document_fingerprint(relative_path, document.data)
        sources = contract.source_refs(frontmatter)
        page_key = contract.sha_of_ref(sources[-1]) if sources else None
        if page_key is None:
            left_out.append(
                LeftOutPage(relative_path, "no_base_reference", None, doc_fingerprint)
            )
            continue
        collision = first_path_by_key.get(page_key)
        if collision is not None:
            left_out.append(
                LeftOutPage(relative_path, "duplicate_base", collision, doc_fingerprint)
            )
            continue
        first_path_by_key[page_key] = relative_path
        pages.append(
            ScannedPage(
                page_key,
                relative_path,
                document.text,
                frontmatter,
                sources,
                doc_fingerprint,
            )
        )
    return CorpusScan(tuple(pages), tuple(left_out))


def corpus_snapshot(
    data_root: Path,
    scan: CorpusScan,
    *,
    today: date,
    athlete_fingerprint: str,
    held: Set[str] | None,
) -> CorpusSnapshot:
    """Partition a scan into held pages and left-outs without filesystem I/O."""
    pages = tuple(
        CorpusPage(
            page.page_key, page.path, page.frontmatter, page.document_fingerprint
        )
        for page in scan.pages
        if held is None or page.page_key in held
    )
    left_out = [
        CorpusLeftOut(page.path, page.document_fingerprint) for page in scan.left_out
    ]
    left_out.extend(
        CorpusLeftOut(page.path, page.document_fingerprint)
        for page in scan.pages
        if held is not None and page.page_key not in held
    )
    return CorpusSnapshot(
        data_root,
        tuple(sorted(pages, key=lambda page: page.path)),
        tuple(sorted(left_out, key=lambda page: page.path)),
        today,
        athlete_fingerprint,
    )


def _load_region_reading(markdown: str) -> LoadRegionReading:
    """Map the load editor's region states into the producer carrier vocabulary."""
    classification = docedit.classify_load_region(markdown)
    if classification.state is RegionState.COMPUTED:
        return LoadRegionReading("computed", classification.payload)
    if classification.state is RegionState.UNSUPPORTED:
        return LoadRegionReading("unsupported", classification.payload)
    if classification.state is RegionState.PLACEHOLDER:
        return LoadRegionReading("not_computed", None)
    if classification.state in (RegionState.SUPERSEDED, RegionState.FOREIGN):
        return LoadRegionReading("unreadable", None)
    raise AssertionError(f"unhandled load region state: {classification.state!r}")
