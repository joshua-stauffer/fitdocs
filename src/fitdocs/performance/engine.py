"""The derivation pass: discover, resolve, derive, reconcile, report, write
once (design: PassEngine; Req 1.1-1.10, 6.1-6.8, 7.1-7.9, 9.1-9.7, 10.3).

This module is the *impure* half of the feature: it is the only place in
this package that touches the filesystem. The purity and reachability guards
that govern the rest of `fitdocs.performance` exclude this module by name for
that reason, and the constant guard's scanned tuple does not list it.

Task 4.1 landed the skeleton: discovery in sorted order, one frontmatter read
per document, and the three-way branch over
:func:`fitdocs.contract.effort_tag` -- untagged (skipped, no archive ever
opened, Req 1.3), a well-formed tag, or a malformed tag (recorded as a
:class:`DeriveFailure` rendering the contract's own
:meth:`~fitdocs.contract.InvalidEffortTag.describe`, Req 1.6).

Task 4.2 (this task) adds archive resolution, re-parsing and derivation for
the valid-tag arm, plus the remaining failure classes. It resolves a tagged
document's archived source by the *same rule* :func:`fitdocs.load.engine`'s
private `_resolve_archive` uses -- the document's last `sources` ref,
validated through :func:`fitdocs.contract.sha_of_ref` (which refuses a
traversal-shaped ref) and joined through :func:`fitdocs.layout.archive_path`
-- restated here rather than imported (design: PassEngine Implementation
Notes: "duplicating a private helper is rejected"; importing it would drag
the whole load pass's import surface into this one and couple two passes
through a private name). The mitigation the design names is a *shared
behavioural test*, not an import: `tests/performance/test_engine.py` proves
both passes discover the identical document set and resolve one fixture
document -- including a traversal ref -- to the identical answer.

The stream-sufficiency settings (`LoadSettings.sufficiency`, Req 9.7) are
now read exactly once per invocation, here, through
:func:`fitdocs.settings.load_settings_document` and
:func:`fitdocs.load.settings.load_load_settings` -- the same single reader
the training-load pass uses. `tests/load/test_settings.py`'s
`test_load_load_settings_is_called_from_exactly_the_licensed_modules`
(originally `..._from_exactly_one_module`) pinned `load/engine.py` as
training-load's *only* caller (training-load Req 14.1); that assertion's
expected caller set is widened, by this task, to name this module as a
sanctioned caller alongside load-history's engine -- the controller ruling
recorded in
`.kiro/specs/performance-benchmarks/tasks.md` § Implementation Notes
`(4.1 -> 4.2)` and in
`.kiro/queue/2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard.md`
(see that file's `## Resolution` section). The reader is still called from
nowhere else: two *passes*, one *reader*.

Every frontmatter field this module reads comes through
:mod:`fitdocs.contract`'s published readers
(:func:`~fitdocs.contract.is_workout_document`,
:func:`~fitdocs.contract.effort_tag`, :func:`~fitdocs.contract.document_date`,
:func:`~fitdocs.contract.source_refs`, :func:`~fitdocs.contract.sha_of_ref`)
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

from fitdocs import FitDecodeError, parse_fit
from fitdocs.contract import (
    EffortTag,
    InvalidEffortTag,
    document_date,
    effort_tag,
    is_workout_document,
    sha_of_ref,
    source_refs,
)
from fitdocs.docio import read_frontmatter
from fitdocs.layout import WORKOUTS_DIR, archive_path, settings_path
from fitdocs.load.settings import load_load_settings
from fitdocs.performance.derive import derive
from fitdocs.performance.types import DerivationDeclined, DerivedBenchmark
from fitdocs.settings import load_settings_document

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
    """A document the pass could not process at all: an unresolvable,
    unreadable or undecodable archive, or a malformed tag (Req 1.5, 1.6,
    7.8). An unreadable *page* never reaches here: `read_frontmatter` never
    raises, so such a page is not a workout document and is skipped, exactly
    as the load pass skips it."""

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

    Deliberately held nothing task 4.1 could not construct: task 4.2 uses this
    same record, unchanged, to carry `tag`/`on`/`document` into archive
    resolution and the `derive()` call rather than re-deriving any of them --
    the resolved archive and the parsed activity are local values in
    `derive_benchmarks`, not fields added here, because neither survives past
    the single document iteration that produces it.
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


def _resolve_pass_archive(
    data_root: Path, frontmatter: dict[str, object]
) -> Path | None:
    """Resolve a tagged document's archived source, or `None` (Req 1.4).

    The *same rule* :func:`fitdocs.load.engine`'s private `_resolve_archive`
    applies -- the document's last `sources` ref (:func:`source_refs`),
    validated by :func:`sha_of_ref` (which refuses a traversal-shaped ref
    such as `fit-archive/../secrets.fit` by returning `None` rather than
    joining it onto the data root), then joined through
    :func:`archive_path`. Restated here rather than imported (module
    docstring); `tests/performance/test_engine.py` proves the two resolvers
    agree, including on a traversal ref, by calling both directly.

    Returns `None` when the history is empty, its last entry is not a
    resolvable archive ref, or the referenced file is missing -- every case
    the caller reports as an "unresolvable archive" failure.
    """
    sources = source_refs(frontmatter)
    if not sources:
        return None
    sha = sha_of_ref(sources[-1])
    if sha is None:
        return None
    archive = archive_path(data_root, sha)
    return archive if archive.is_file() else None


def derive_benchmarks(data_root: Path, *, dry_run: bool = False) -> DeriveReport:
    """Run the benchmark-derivation pass over `data_root` (design: PassEngine
    Service Interface; Req 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.1, 9.1, 9.3, 9.7,
    10.3).

    Task 4.1 implemented discovery, the frontmatter read and the three-way
    tag branch. Task 4.2 (this task) adds, for the valid-tag arm only,
    archive resolution, re-parsing, and the call into
    :func:`fitdocs.performance.derive.derive` -- never for an untagged
    document (Req 1.3), and only after the tag branch has already committed
    to "valid tag" (a malformed or absent tag never reaches
    :func:`_resolve_pass_archive`).

    `dry_run` is still accepted for the Service Interface's sake but has no
    observable effect yet: nothing is written by any code path landed so far
    -- reconciliation and the single write are task 4.3's. The
    stream-sufficiency settings (Req 9.7) are read exactly once here, before
    the document loop, through the same single reader the training-load pass
    uses (module docstring) -- never once per document.
    """
    _ = dry_run  # wired by task 4.3's write path; unused until then

    settings_document = load_settings_document(data_root)
    settings = load_load_settings(settings_document, settings_path(data_root))

    considered = 0
    tagged = 0
    failures: list[DeriveFailure] = []
    entries: list[DeriveEntry] = []

    for path in _sorted_workout_paths(data_root):
        frontmatter = read_frontmatter(path)
        if not is_workout_document(frontmatter):
            continue
        assert frontmatter is not None  # is_workout_document(None) is False
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
        tagged_doc = _TaggedDocument(document=rel, tag=tag, on=on)

        archive = _resolve_pass_archive(data_root, frontmatter)
        if archive is None:
            failures.append(
                DeriveFailure(
                    document=rel,
                    reason=(
                        f"unresolvable archive for {rel}: the document's "
                        "'sources' history is empty, its last entry is not "
                        "a resolvable archive reference, or the referenced "
                        "file is missing from the archive"
                    ),
                )
            )
            continue

        try:
            activity = parse_fit(archive)
        except OSError as exc:
            failures.append(
                DeriveFailure(
                    document=rel,
                    reason=f"unreadable archive for {rel}: {exc}",
                )
            )
            continue
        except FitDecodeError as exc:
            failures.append(
                DeriveFailure(
                    document=rel,
                    reason=f"undecodable archive for {rel}: {exc}",
                )
            )
            continue

        outcomes = derive(
            activity,
            tagged_doc.tag,
            on=tagged_doc.on,
            document=tagged_doc.document,
            sufficiency=settings.sufficiency,
        )
        entries.append(
            DeriveEntry(
                document=tagged_doc.document,
                derived=tuple(o for o in outcomes if isinstance(o, DerivedBenchmark)),
                declined=tuple(
                    o for o in outcomes if isinstance(o, DerivationDeclined)
                ),
            )
        )

    return DeriveReport(
        considered=considered,
        tagged=tagged,
        entries=tuple(entries),
        failures=tuple(failures),
        written=False,
    )
