"""The one filesystem read of this package: workout documents in, typed page
records out (load-history spec, task 3.1; Req 1.1, 1.2, 1.3, 1.4, 1.9, 3.9,
5.4). See the "DocumentScan (`src/fitdocs/history/documents.py`)" component
in `.kiro/specs/load-history/design.md`.

This module scans `workouts/*.md` at the data root's top level, sorted --
exactly the discovery rule `fitdocs.load.engine._discover_workout_docs` and
`fitdocs.audit.audit` each restate for their own pass (design.md's own
"Risks" note accepts the duplication: each pass owns its own scan and none
imports another's). It reads nothing under `history/`, nothing under
`fit-archive/`, and no `.fit` file at all (Req 1.1).

Every document read goes through `fitdocs.docio.read_frontmatter` -- the one
shared filesystem-plus-frontmatter read every scanner in the package uses --
and every interpretation of the parsed mapping goes through names bound
directly from `fitdocs.contract` by identity: `is_workout_document`,
`document_date`, `LOAD_KEYS` and `effort_tag`. This module is the `history`
package's only importer of either,
and the only one of this package's modules later registered in
`tests/test_contract_consumers.py` (task 5.4). It spells no frontmatter
fence, no workout-type literal and no effort key, and defines no private
duplicate of a contract reader.

What counts as a document this module has an opinion about
-------------------------------------------------------------
A file `docio.read_frontmatter` declines to read (a symlink, an OS or
decode error, no leading frontmatter fence, unparseable YAML, or a block
that is not a mapping) is not distinguishable, from here, from a file that
was simply never meant to be a fitdocs workout document at all -- the
in-tree ownership declaration (`workouts/AGENTS.md`) is the standing
example: it carries no YAML frontmatter *by design* (wiki-contract Req 3.7)
precisely so no frontmatter-based scan ever catches it up. Reporting every
such file as a "skipped" document would misreport that file on every run.
So, matching `fitdocs.load.engine._discover_workout_docs` and the
non-workout branch of `fitdocs.audit.audit`, a file whose frontmatter cannot
be read, or whose parsed frontmatter is not a workout document
(`is_workout_document` is `False`), is excluded from both this
scan's pages and its skipped files -- silently, because it was never this
module's document to report on.

A file that *is* a recognized workout document but whose own recorded date
cannot be read (`document_date` returns `None`) is a different
case: it is unambiguously a fitdocs document this scan failed to place in
the series, so it is reported, named, with a reason (Req 1.9).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fitdocs import contract, docio
from fitdocs.contract import (
    LOAD_KEYS,
    document_date,
    effort_tag,
    is_workout_document,
)
from fitdocs.layout import WORKOUTS_DIR

__all__ = [
    "DocumentScan",
    "PageRecord",
    "SkippedPage",
    "scan_documents",
]

# The three managed load keys, in the contract's own emission order --
# `load_value`, `load_methodology`, `load_basis` -- unpacked once here so no
# key name is respelled and no positional index is a bare literal this
# package's constant-literal guard would need an exemption for.
_LOAD_VALUE_KEY, _LOAD_METHODOLOGY_KEY, _LOAD_BASIS_KEY = LOAD_KEYS

#: The one reason a page is reported skipped by this module (Req 1.9). A
#: single constant so the reason text cannot drift between call sites.
_UNDATED_REASON = "the document's recorded date could not be read"


@dataclass(frozen=True)
class PageRecord:
    """One recognized workout document, reduced to what the series needs.

    `path` is data-root-relative and forward-slash form, never absolute and
    never machine-specific (Req 1.1's "no report or page ever leaks an
    absolute path"). `load` is `None` exactly when the page records no
    usable training load -- never a fabricated zero (Req 1.4) -- and
    `methodology` travels with it, read only when `load` was (see
    `_read_load`). `effort` is the well-formed effort tag, `None` for no tag
    at all; `tag_problem` is the malformed tag's own description (Req 3.9)
    when the tag was present but invalid, else `None`. A malformed tag never
    withholds the page's load.
    """

    path: str
    day: date
    load: float | None
    methodology: str | None
    effort: contract.EffortTag | None
    tag_problem: str | None


@dataclass(frozen=True)
class SkippedPage:
    """One workout document this scan could not place in the series, and why."""

    path: str
    reason: str


@dataclass(frozen=True)
class DocumentScan:
    """The whole scan's result: every placeable page, and every skip.

    `pages` is sorted by `(day, path)`; `skipped` is sorted by `path`. Both
    orders are the tuple's own contract, independent of how the filesystem
    happened to enumerate the directory.
    """

    pages: tuple[PageRecord, ...]
    skipped: tuple[SkippedPage, ...]


def _relative_posix(data_root: Path, path: Path) -> str:
    """`path`, relative to `data_root`, in forward-slash form (Req 1.1)."""
    return path.relative_to(data_root).as_posix()


def _read_load(
    frontmatter: dict[str, object],
) -> tuple[float | None, str | None]:
    """The page's load and methodology from the managed load keys (Req 1.3, 1.4).

    `load is None` if and only if `methodology is None` (design.md's stated
    postcondition): `load` is `None` -- never a fabricated zero -- whenever
    `load_value` is absent, not an `int`/`float`, a `bool` (an `int`
    subclass, rejected explicitly), not finite, or too large to convert to a
    Python `float`; and whenever the load is otherwise usable but
    `load_methodology` is absent or not a `str`, both `load` and
    `methodology` are dropped together, because Req 1.3 takes a load "only
    together with the methodology recorded alongside it" -- a load reported
    with no methodology would be summed under whatever methodology
    `SeriesAssembly` later chooses (design.md's `SeriesAssembly` "Partition"
    note), which Req 4.1 forbids.
    """
    value = frontmatter.get(_LOAD_VALUE_KEY)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, None
    try:
        load = float(value)
    except OverflowError:
        return None, None
    if not math.isfinite(load):
        return None, None
    methodology_value = frontmatter.get(_LOAD_METHODOLOGY_KEY)
    if not isinstance(methodology_value, str):
        return None, None
    return load, methodology_value


def _read_effort(
    frontmatter: dict[str, object],
) -> tuple[contract.EffortTag | None, str | None]:
    """The page's effort tag and any problem with it, through the one
    contract reader (Req 3.9). A malformed tag places no marker -- `effort`
    is `None` -- but its own `describe()` is recorded as `tag_problem`, and
    the page's load is untouched either way (the caller reads load
    independently, never gated on this)."""
    tag = effort_tag(frontmatter)
    if isinstance(tag, contract.InvalidEffortTag):
        return None, tag.describe()
    if tag is None:
        return None, None
    return tag, None


def scan_documents(data_root: Path) -> DocumentScan:
    """Every workout document under `data_root`'s `workouts/` top level,
    reduced to `PageRecord`s and `SkippedPage`s (Req 1.1, 1.2, 1.3, 1.4, 1.9,
    3.9, 5.4).

    Scans `workouts/*.md`, sorted, exactly as `fitdocs.load.engine` and
    `fitdocs.audit` each do for their own pass; a missing `workouts/`
    directory yields an empty scan rather than an error, and a subdirectory
    under it is never descended into (`Path.glob("*.md")` is not recursive).
    Never raises for a bad document: a file `docio.read_frontmatter` declines
    or that is not a recognized workout document is silently excluded (see
    the module docstring for why); a recognized document whose date cannot
    be read is reported as a `SkippedPage`.
    """
    workouts_dir = data_root / WORKOUTS_DIR
    pages: list[PageRecord] = []
    skipped: list[SkippedPage] = []

    if workouts_dir.is_dir():
        for path in sorted(workouts_dir.glob("*.md")):
            frontmatter = docio.read_frontmatter(path)
            if frontmatter is None or not is_workout_document(frontmatter):
                continue

            relpath = _relative_posix(data_root, path)
            day = document_date(frontmatter)
            if day is None:
                skipped.append(SkippedPage(relpath, _UNDATED_REASON))
                continue

            load, methodology = _read_load(frontmatter)
            effort, tag_problem = _read_effort(frontmatter)
            pages.append(
                PageRecord(
                    path=relpath,
                    day=day,
                    load=load,
                    methodology=methodology,
                    effort=effort,
                    tag_problem=tag_problem,
                )
            )

    pages.sort(key=lambda page: (page.day, page.path))
    skipped.sort(key=lambda skip: skip.path)
    return DocumentScan(pages=tuple(pages), skipped=tuple(skipped))
