"""Page selection, page state and the publish subject (publish-core Req 6.6,
7.2, 7.3, 7.8, 11.7).

Selection finds the workout pages a run considers: every top-level page of
``workouts/`` in file-name order, or the pages the athlete named. Reading a
page classifies its state from its recorded format version and its regions.
The completed-activity subject is built only from what the page records; an
absent fact is ``None``, never a default. Every document reading goes through
the contract's readers.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from fitdocs.contract import (
    DOC_VERSION,
    POST_REGION,
    PUBLISHED_REGION,
    document_source_identity,
    document_sport,
    document_start_time,
    document_version,
    is_workout_document,
    sha_of_ref,
    source_refs,
)
from fitdocs.docio import read_document, read_frontmatter_diagnosed
from fitdocs.docmerge import RegionError, extract_regions
from fitdocs.layout import WORKOUTS_DIR, archive_path
from fitdocs.publish.request import CompletedActivity

PAGE_SUFFIX: Final[str] = ".md"


@dataclass(frozen=True)
class SelectedPage:
    path: Path
    rel: str  # data-root-relative POSIX path
    named: bool  # named in PAGES


class PageSelectionError(Exception):
    """A named page cannot be selected; the message says what to fix."""


class PageStatus(StrEnum):
    CURRENT = "current"
    OLDER = "older"
    NEWER = "newer"
    DAMAGED = "damaged"


@dataclass(frozen=True)
class PageView:
    text: str
    frontmatter: Mapping[str, object]
    status: PageStatus
    regions: Mapping[str, str] | None  # None unless CURRENT
    detail: str | None  # fitdocs-written reason for DAMAGED


def _selected(workouts: Path, file_name: str, *, named: bool) -> SelectedPage:
    return SelectedPage(
        path=workouts / file_name,
        rel=f"{WORKOUTS_DIR}/{file_name}",
        named=named,
    )


def _is_workout_page(path: Path) -> bool:
    document = read_document(path)
    return document is not None and is_workout_document(document.frontmatter)


def _top_level_pages(data_root: Path) -> tuple[SelectedPage, ...]:
    """Every regular top-level workout page, by file name (symlinks skipped)."""
    workouts = data_root / WORKOUTS_DIR
    try:
        entries = sorted(os.listdir(workouts))
    except OSError:
        return ()
    pages: list[SelectedPage] = []
    for file_name in entries:
        path = workouts / file_name
        if not file_name.endswith(PAGE_SUFFIX) or path.is_symlink():
            continue
        if _is_workout_page(path):
            pages.append(_selected(workouts, file_name, named=False))
    return tuple(pages)


def _bare_candidates(name: str) -> tuple[str, ...]:
    if name.endswith(PAGE_SUFFIX):
        return (name,)
    return (name, f"{name}{PAGE_SUFFIX}")


def _resolve_name(workouts: Path, name: str, cwd: Path) -> Path:
    """The path a name stands for, or a refusal naming what to fix."""
    if os.sep in name or "/" in name:
        candidate = Path(os.path.abspath(cwd / name))
        try:
            directly_in = os.path.samefile(candidate.parent, workouts)
        except OSError:
            directly_in = False
        if not directly_in:
            raise PageSelectionError(
                f"{name}: not a file directly in {WORKOUTS_DIR}/ of the data root"
            )
        if not os.path.lexists(candidate):
            raise PageSelectionError(f"{name}: no such file")
        return candidate
    for file_name in _bare_candidates(name):
        candidate = workouts / file_name
        if os.path.lexists(candidate) and not (
            candidate.is_dir() and not candidate.is_symlink()
        ):
            return candidate
    raise PageSelectionError(f"{name}: no such page in {WORKOUTS_DIR}/")


def select_pages(
    data_root: Path, names: Sequence[str], *, cwd: Path
) -> tuple[SelectedPage, ...]:
    """The pages a run considers, in file-name order, duplicates collapsed.

    No names selects every top-level workout page. A name without a path
    separator is ``workouts/<name>`` or ``workouts/<name>.md``; a name with
    one is a path from ``cwd`` that must be a file directly in the data
    root's ``workouts/``. Raises :class:`PageSelectionError` for a name that
    resolves to nothing, a symlink, a file elsewhere or a readable file that
    is not a workout page. A named page that cannot be read is selected; the
    run reports it (Req 7.8) and :func:`read_page` gives ``None`` for it.
    """
    if not names:
        return _top_level_pages(data_root)
    workouts = data_root / WORKOUTS_DIR
    chosen: dict[tuple[int, int], SelectedPage] = {}
    for name in names:
        path = _resolve_name(workouts, name, cwd)
        if path.is_symlink():
            raise PageSelectionError(f"{name}: is a symlink; name the page itself")
        if not path.is_file():
            raise PageSelectionError(f"{name}: is not a file")
        frontmatter, reason = read_frontmatter_diagnosed(path)
        # An unreadable page is selected so the run can report it (Req 7.8);
        # only a readable page that is not a workout page is refused.
        if reason is None and not is_workout_document(frontmatter):
            raise PageSelectionError(f"{name}: is not a workout page")
        identity = _identity(path)
        if identity not in chosen:
            file_name = _on_disk_name(workouts, path.name, identity) or path.name
            chosen[identity] = _selected(workouts, file_name, named=True)
    return tuple(sorted(chosen.values(), key=lambda page: page.path.name))


def _identity(path: Path) -> tuple[int, int]:
    info = path.stat()
    return (info.st_dev, info.st_ino)


def _on_disk_name(workouts: Path, typed: str, identity: tuple[int, int]) -> str | None:
    """The directory entry's own spelling of the file with this identity.

    The typed name when it is itself an entry of ``workouts/`` for this file
    (a hard link keeps the name the athlete used); otherwise, for a
    case-variant spelling, the first entry in file-name order that is this
    file. Entries are compared by ``lstat``, so a symlink to the file is not
    the file.
    """
    try:
        entries = sorted(os.listdir(workouts))
    except OSError:
        return None
    matches: list[str] = []
    for file_name in entries:
        try:
            info = os.lstat(workouts / file_name)
        except OSError:
            continue
        if (info.st_dev, info.st_ino) == identity:
            matches.append(file_name)
    if typed in matches:
        return typed
    return matches[0] if matches else None


def _status(frontmatter: Mapping[str, object], text: str) -> PageView:
    version = document_version(frontmatter)
    if version is None or version < DOC_VERSION:
        return PageView(text, frontmatter, PageStatus.OLDER, None, None)
    if version > DOC_VERSION:
        return PageView(text, frontmatter, PageStatus.NEWER, None, None)
    try:
        regions = extract_regions(text)
    except RegionError as exc:
        return PageView(text, frontmatter, PageStatus.DAMAGED, None, str(exc))
    for region_id in (POST_REGION, PUBLISHED_REGION):
        if region_id not in regions:
            detail = f"the page has no {region_id} region; run fitdocs regen"
            return PageView(text, frontmatter, PageStatus.DAMAGED, None, detail)
    return PageView(text, frontmatter, PageStatus.CURRENT, regions, None)


def read_page(page: SelectedPage) -> PageView | None:
    """The page's state, or ``None`` when unreadable or not a workout page."""
    document = read_document(page.path)
    if document is None or document.frontmatter is None:
        return None
    if not is_workout_document(document.frontmatter):
        return None
    return _status(document.frontmatter, document.text)


def source_shas(frontmatter: Mapping[str, object]) -> tuple[str, ...]:
    """The page's archived files' digests, lowercased, in ascending rank."""
    shas: list[str] = []
    for ref in source_refs(frontmatter):
        sha = sha_of_ref(ref)
        if sha is not None:
            shas.append(sha.lower())
    return tuple(shas)


def completed_activity(
    frontmatter: Mapping[str, object], data_root: Path
) -> CompletedActivity | None:
    """The page's completed activity, or ``None`` without a sport or an aware start."""
    sport = document_sport(frontmatter)
    start = document_start_time(frontmatter)
    if sport is None or start is None:
        return None
    identity = document_source_identity(frontmatter)
    refs = source_refs(frontmatter)
    base_sha = sha_of_ref(refs[-1]) if refs else None
    base_fit: Path | None = None
    if base_sha is not None:
        candidate = archive_path(data_root, base_sha.lower())
        if candidate.is_file():
            base_fit = candidate
    return CompletedActivity(
        sport=sport,
        start=start,
        elapsed_s=identity.elapsed_s,
        distance_m=identity.distance_m,
        source_shas=source_shas(frontmatter),
        base_fit=base_fit,
    )


def sha_index(data_root: Path) -> Mapping[str, tuple[str, ...]]:
    """Each source digest to the pages recording it, for every workout page."""
    index: dict[str, list[str]] = {}
    for page in _top_level_pages(data_root):
        document = read_document(page.path)
        if document is None or document.frontmatter is None:
            continue
        for sha in dict.fromkeys(source_shas(document.frontmatter)):
            index.setdefault(sha, []).append(page.rel)
    return {sha: tuple(rels) for sha, rels in index.items()}
