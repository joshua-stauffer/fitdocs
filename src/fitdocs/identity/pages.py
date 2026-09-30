"""The one frontmatter scan that yields page records.

Reads ``<data_root>/workouts/*.md`` through the contract's readers only and
returns a :class:`~fitdocs.identity.planning.PageIndex`. One of two identity
modules that touch the filesystem (with ``holds``). A page's key is built from
the page's *own* recorded identity keys; a page that lacks them (a legacy page)
gets a key whose ``elapsed_s``, ``distance_m``, ``device`` and ``kind`` are all
``None``, so no rule tier can match it (Req 7.4) and only the exact paths reach
it (Req 3.9).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from fitdocs.contract import (
    document_source_identity,
    document_sport,
    document_start_time,
    document_uuid,
    is_workout_document,
    source_refs,
)
from fitdocs.docio import read_frontmatter
from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.matching import SessionKey
from fitdocs.identity.planning import PageIndex, PageRecord
from fitdocs.layout import WORKOUTS_DIR

__all__ = ["page_record", "scan_pages"]


def _kind(text: str | None) -> SourceKind | None:
    if text is None:
        return None
    try:
        return SourceKind(text)
    except ValueError:
        return None


def page_record(path: Path, frontmatter: Mapping[str, object]) -> PageRecord:
    """The record of one workout page, from its parsed frontmatter."""
    identity = document_source_identity(frontmatter)
    sport = document_sport(frontmatter)
    if sport is None:
        # SessionKey.sport is a required str, so "" stands in for "no sport
        # recorded". Dropping the start too makes the placeholder inert: with no
        # start, pair_evidence returns None and duplicate_sets drops the page, so
        # two sport-less pages can never link by rule.
        sport, start = "", None
    else:
        start = document_start_time(frontmatter)
    key = SessionKey(
        sport=sport,
        start=start,
        elapsed_s=identity.elapsed_s,
        distance_m=identity.distance_m,
        device=identity.device,
        kind=_kind(identity.kind),
    )
    return PageRecord(
        path=str(path),
        sources=source_refs(frontmatter),
        session_uuid=document_uuid(frontmatter),
        key=key,
    )


def scan_pages(data_root: Path) -> PageIndex:
    """Index every workout document under ``<data_root>/workouts/`` (top level).

    Files are visited in sorted path order. A symlink, an unreadable file, a
    garbled or missing frontmatter block and any file that is not a workout
    document (the ownership declaration among them) are skipped. An absent
    ``workouts/`` directory yields an empty index.
    """
    workouts_dir = data_root / WORKOUTS_DIR
    if not workouts_dir.is_dir():
        return PageIndex(())
    records: list[PageRecord] = []
    for path in sorted(workouts_dir.glob("*.md")):
        frontmatter = read_frontmatter(path)
        if frontmatter is None or not is_workout_document(frontmatter):
            continue
        records.append(page_record(path, frontmatter))
    return PageIndex(records)
