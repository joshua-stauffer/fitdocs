"""Freshness measurements for the analytics index."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.index import corpus, fingerprint, registry
from fitdocs.index.bookkeeping import PageState
from fitdocs.index.corpus import CorpusScan
from fitdocs.index.store import IndexConnection


@dataclass(frozen=True)
class PageDrift:
    workout_pages: int
    pages_held: int
    added: int
    changed: int
    removed: int

    @property
    def behind(self) -> bool:
        return bool(self.added or self.changed or self.removed)

    def as_mapping(self) -> Mapping[str, int | bool]:
        return {
            "workout_pages": self.workout_pages,
            "pages_held": self.pages_held,
            "added": self.added,
            "changed": self.changed,
            "removed": self.removed,
            "behind": self.behind,
        }


def page_drift(scan: CorpusScan, held: Mapping[str, PageState]) -> PageDrift:
    scanned = {page.page_key: page for page in scan.pages}
    added = scanned.keys() - held.keys()
    removed = held.keys() - scanned.keys()
    changed = {
        key
        for key in scanned.keys() & held.keys()
        if scanned[key].document_fingerprint != held[key].document_fingerprint
    }
    return PageDrift(len(scan.pages), len(held), len(added), len(changed), len(removed))


@dataclass(frozen=True)
class CorpusDrift:
    behind: tuple[str, ...]
    unassessed: tuple[tuple[str, str], ...]


def corpus_fingerprints(
    scan: CorpusScan,
    held: Mapping[str, PageState],
    *,
    data_root: Path,
    today: date,
    athlete_fingerprint: str,
) -> Mapping[str, str | Exception]:
    snapshot = corpus.corpus_snapshot(
        data_root,
        scan,
        today=today,
        athlete_fingerprint=athlete_fingerprint,
        held=frozenset(held),
    )
    fingerprints: dict[str, str | Exception] = {}
    for producer in registry.CORPUS_PRODUCERS:
        try:
            fingerprints[producer.name] = fingerprint.combined_corpus_fingerprint(
                producer, snapshot
            )
        except Exception as error:
            fingerprints[producer.name] = error
    return fingerprints


def corpus_drift(
    fingerprints: Mapping[str, str | Exception],
    stored: Mapping[str, str | None],
    tables: Mapping[str, tuple[str, ...]],
) -> CorpusDrift:
    behind: list[str] = []
    unassessed: list[tuple[str, str]] = []
    for name, current in fingerprints.items():
        if isinstance(current, Exception):
            unassessed.append((name, f"{type(current).__name__}: {current}"))
        elif current != stored.get(name):
            behind.extend(tables.get(name, ()))
    return CorpusDrift(tuple(sorted(behind)), tuple(sorted(unassessed)))


@dataclass(frozen=True)
class AthleteDrift:
    activities_other_inputs: int | None
    skipped_reason: str | None


def current_athlete_fingerprint(data_root: Path) -> str | AthleteFileError:
    try:
        inputs = load_athlete_inputs(data_root)
    except AthleteFileError as error:
        return error
    return fingerprint.athlete_fingerprint(inputs)


def athlete_drift(
    conn: IndexConnection, current: str | AthleteFileError
) -> AthleteDrift:
    if isinstance(current, AthleteFileError):
        return AthleteDrift(None, str(current))
    result = conn.execute(
        "SELECT count(*) FROM activities WHERE athlete_fingerprint IS DISTINCT FROM $1",
        (current,),
    )
    count = cast(int, result.fetchall()[0][0])
    return AthleteDrift(count, None)
