"""The derivation pass: discover, resolve, derive, reconcile, report, write
once (design: PassEngine; Req 1.1-1.10, 6.1-6.8, 7.1-7.9, 9.1-9.7, 10.3).

This module is the *impure* half of the feature: it is the only place in
this package that touches the filesystem. The purity and reachability guards
that govern the rest of `fitdocs.performance` exclude this module by name for
that reason, and the constant guard's scanned tuple does not list it.

Task 4.1 lands the skeleton only: discovery in sorted order, one frontmatter
read per document, and the three-way branch over
:func:`fitdocs.contract.effort_tag` -- untagged (skipped, no archive ever
opened, Req 1.3), a well-formed tag (counted, its page date recorded on an
internal per-document record task 4.2 wires into
:func:`fitdocs.performance.derive.derive`), or a malformed tag (recorded as a
:class:`DeriveFailure` rendering the contract's own
:meth:`~fitdocs.contract.InvalidEffortTag.describe`, Req 1.6). No archive is
resolved, no `.fit` is parsed, and no derivation runs yet -- `entries` is
always empty and `written` is always `False` until task 4.2 (archive
resolution and failure classification) and task 4.3 (reconciliation and the
write) land on top of this skeleton without reshaping it.

The stream-sufficiency settings (`LoadSettings.sufficiency`, Req 9.7) are
**not yet read here**: `tests/load/test_settings.py` pins
`fitdocs.load.settings.load_load_settings` as called from exactly one module
in shipped source (`load/engine.py`, training-load Req 14.1). Its AST walk
reds on a literal or `from ... import ... as`-aliased call from this module;
its behavioural companion closes the remaining spellings only once the
command is wired (task 4.4). Calling the reader here would regress that
out-of-boundary invariant, so the read is deferred to the task that consumes
it (4.2, which threads `sufficiency` into `performance.derive.derive` and
widens the guard's caller set by the controller ruling recorded in
`.kiro/specs/performance-benchmarks/tasks.md` § Implementation Notes
`(4.1 -> 4.2)`; the conflict itself is
`.kiro/queue/2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard.md`).

Every frontmatter field this module reads comes through
:mod:`fitdocs.contract`'s published readers
(:func:`~fitdocs.contract.is_workout_document`,
:func:`~fitdocs.contract.effort_tag`, :func:`~fitdocs.contract.document_date`)
reached from exactly one :func:`fitdocs.docio.read_frontmatter` call per
document (Req 10.3) -- this module defines no second reader of the effort
tag, no second spelling of an effort key, and parses no frontmatter of its
own (Req 10.3): no `yaml` import and no fence-delimiter literal of its own
appear here, and a guard test in this task's own test module pins that.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fitdocs.contract import (
    EffortTag,
    InvalidEffortTag,
    document_date,
    effort_tag,
    is_workout_document,
)
from fitdocs.docio import read_frontmatter
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.performance.types import DerivationDeclined, DerivedBenchmark

__all__ = [
    "DeriveEntry",
    "DeriveFailure",
    "DeriveReport",
    "derive_benchmarks",
]


@dataclass(frozen=True)
class DeriveEntry:
    """One tagged document's outcomes (design: PassEngine Service Interface,
    Req 7.2, 7.3, 7.9). Empty in task 4.1: no derivation runs yet."""

    document: str
    derived: tuple[DerivedBenchmark, ...]
    declined: tuple[DerivationDeclined, ...]


@dataclass(frozen=True)
class DeriveFailure:
    """A document the pass could not process at all: an unresolvable or
    undecodable archive, an unreadable document, or a malformed tag (Req 1.5,
    1.6, 7.8)."""

    document: str
    reason: str


@dataclass(frozen=True)
class DeriveReport:
    """The pass's whole output (design: PassEngine Service Interface, Req
    7.1)."""

    considered: int
    tagged: int
    entries: tuple[DeriveEntry, ...]
    failures: tuple[DeriveFailure, ...]
    written: bool

    @property
    def derived(self) -> tuple[DerivedBenchmark, ...]:
        """Every derived benchmark across every entry, in entry order."""
        return tuple(outcome for entry in self.entries for outcome in entry.derived)

    @property
    def declined(self) -> tuple[DerivationDeclined, ...]:
        """Every declined derivation across every entry, in entry order."""
        return tuple(outcome for entry in self.entries for outcome in entry.declined)


@dataclass(frozen=True)
class _TaggedDocument:
    """One workout document that carried a well-formed effort tag, holding
    exactly what a page's frontmatter can tell the pass before any archive is
    touched: its data-root-relative path, its parsed tag, and its own
    recorded calendar date (`None` when the page carries none, Req 7.6) --
    never a wall-clock or file-timestamp substitute (Req 9.3).

    Deliberately holds nothing task 4.2 must replace: it adds fields (the
    resolved archive, the parsed activity) on top of this record rather than
    reshaping it.
    """

    document: str
    tag: EffortTag
    on: date | None


def _sorted_workout_paths(data_root: Path) -> list[Path]:
    """Every `*.md` directly under `<data_root>/workouts/`, sorted (Req 9.1).

    Not yet filtered to a fitdocs workout document -- that check needs the
    parsed frontmatter, and this pass reads a document's frontmatter exactly
    once (Req 10.3), so the filter is applied by the caller against the same
    read rather than here against a second one. An absent `workouts/`
    directory yields an empty list, exactly as the training-load pass's own
    discovery does.
    """
    workouts = data_root / WORKOUTS_DIR
    if not workouts.is_dir():
        return []
    return sorted(workouts.glob("*.md"))


def derive_benchmarks(data_root: Path, *, dry_run: bool = False) -> DeriveReport:
    """Run the benchmark-derivation pass over `data_root` (design: PassEngine
    Service Interface; Req 1.1, 1.2, 1.3, 1.6, 7.1, 9.1, 9.3, 9.7, 10.3).

    Task 4.1 implements discovery, the frontmatter read and the three-way
    tag branch only. `dry_run` is accepted for the Service Interface's sake
    but has no observable effect yet: nothing is written by any task-4.1
    code path (`written` is always `False`). The stream-sufficiency settings
    read (Req 9.7) is deferred to task 4.2 -- see the module docstring for
    why calling `load_load_settings` here would regress an existing,
    out-of-boundary guard.
    """
    _ = dry_run  # wired by task 4.3's write path; unused until then

    considered = 0
    tagged = 0
    failures: list[DeriveFailure] = []
    tagged_documents: list[_TaggedDocument] = []

    for path in _sorted_workout_paths(data_root):
        frontmatter = read_frontmatter(path)
        if not is_workout_document(frontmatter):
            continue
        considered += 1
        rel = path.relative_to(data_root).as_posix()

        tag = effort_tag(frontmatter)
        if tag is None:
            # Untagged: never opens the archive, contributes no outcome of
            # any kind (Req 1.3).
            continue
        if isinstance(tag, InvalidEffortTag):
            failures.append(DeriveFailure(document=rel, reason=tag.describe()))
            continue

        tagged += 1
        on = document_date(frontmatter)
        tagged_documents.append(_TaggedDocument(document=rel, tag=tag, on=on))

    # Task 4.2 resolves each tagged document's archive and derives from it;
    # task 4.3 reconciles and writes. Neither runs yet, so every tagged
    # document above produces no entry in this task.
    _ = tagged_documents

    return DeriveReport(
        considered=considered,
        tagged=tagged,
        entries=(),
        failures=tuple(failures),
        written=False,
    )
