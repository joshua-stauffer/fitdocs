"""The sync engine: the only writer, and the activity-identity resolver.

This module is the home of fitdocs's per-file pipeline (design: SyncEngine,
``src/fitdocs/sync.py``) and of the document-lookup surface that pipeline builds
on. :func:`sync` walks a source directory and, for each discovered ``.fit`` file,
runs the per-file pipeline -- ``hash -> dedup -> parse -> identity -> render ->
merge -> write -> archive`` -- with per-file failures isolated so one bad file
never aborts the batch (Req 1-4). :func:`regen` rebuilds documents from the data
root alone -- re-rendering each from its current archived source and rendering any
unreferenced archive fresh (Req 4.3, 4.4) -- reusing that same per-file pipeline;
only discovery and skip policy differ. :func:`drain` is the inbox spec's third
entry point (design: DrainOrchestration): it composes the standing-inbox policy
(:mod:`fitdocs.inbox` selection and stability) around this same per-file
pipeline without modifying it -- candidates are selected, settled, read once
each (a read failure defers rather than fails or quarantines the candidate,
inbox Req 4.2), and every stable, readable candidate not already quarantined
(or being retried, inbox Req 5.5) is handed to the same :func:`_process_isolated`
call :func:`sync` uses, with the candidate's inbox-relative path as its
``source_label`` (inbox Req 2.3). A candidate whose content hash is already in
the quarantine record, and retry is not requested, is reported in its own
``quarantined`` channel and never reaches :func:`_process_isolated` at all
(inbox Req 5.2). The composed :class:`DrainReport` wraps the unchanged
:class:`SyncReport` unmodified, alongside the inbox-only ``deferred`` and
``quarantined`` channels; neither :func:`sync` nor :func:`regen` nor
:func:`_process_file`/:func:`_write_outputs` is touched by this addition.
Processed-file disposition is a later inbox-spec task layered on top of this
same function -- this slice does not move or delete anything. The CLI wiring
is built on top in a later slice.

The *document lookup* (:func:`find_document`) is the read-only step that decides
whether an incoming ``.fit`` file updates an existing document or seeds a fresh
one (Req 3.6).

Write ordering is load-bearing (Req 3.1, 4.2). Per file the engine writes assets
first, then the document, then the archived source copy **last**: the archive's
presence is the processed-marker, so a crash before it leaves no archive and the
file is reprocessed idempotently on the next run. The source directory is opened
strictly read-only -- nothing under it is ever written, moved, or deleted (Req
1.6) -- and an already-archived source is never rewritten (Req 3.5).

**Offline guarantee (narrowed, Req 4.2).** The engine is offline except for one
carve-out: the per-file map path may fetch missing basemap tiles through the
injected :class:`~fitdocs.tiles.TileSource` on a cache miss while resolving a
route map. That is the *only* network access; every other operation --
discovery, decode, identity, render, merge, write, archive -- stays fully
offline, and the source directory remains strictly read-only. A tile that cannot
be resolved (offline, provider error, or the persistent opt-out) never fails a
document or a run: the map is omitted and a :class:`DocWarning` naming the
affected document rides alongside the report (Req 4.3, 4.4). The map path is run
only for the non-strength modalities whose views render a Map section -- the
strength view never renders one, so its tiles are never planned or fetched (Req
3.5).

**Reverse index.** A workout document's YAML frontmatter *is* the lookup index
(design: DocumentContract). Every read of it goes through :mod:`fitdocs.contract`
-- the fence, the ``type`` marker, the parse, the identity, and the ``sources``
history all have exactly one definition there, so a document this engine
recognizes is understood identically by the training-load pass and the audit
(Req 1.1-1.3). Two keys carry activity identity:

* ``uuid`` -- the recorded session identifier (a canonical UUID string), present
  only when the activity recorded a ``SESSION UUID``. It converges every
  re-export of one activity -- same session, different bytes -- onto one
  document.
* ``sources`` -- the append-ordered list of data-root-relative archive refs the
  document was rendered from (last entry = current). It resolves exact re-syncs
  and documents that carry no session UUID.

**Match precedence (Req 3.6).** ``uuid`` is matched first, then ``sources``.
Because the match is *content-based* -- it reads frontmatter, never the filename
-- a user-renamed document and a timezone change (which would otherwise rename
the document) both resolve to the same document. A plain sha256 identity (no
session UUID recorded) can never equal a canonical-UUID ``uuid`` value, so it
correctly falls through to the ``sources`` match. When nothing matches, the
caller makes a fresh-document decision.

The lookup is strictly read-only: it opens documents to read frontmatter and
never writes, moves, or deletes anything. Stray or malformed ``.md`` files under
``workouts/`` are skipped safely -- a broken neighbour never aborts the scan. A
``workouts/*.md`` symlink is refused the same way (never followed, wiki-contract
Req 7.5, 7.6, see :mod:`fitdocs.docio`): it can never be a match candidate, so a
re-export of the very activity it stands in for looks like a fresh one. That
refusal is not left silent, but the warning for it is not this function's
concern -- see :func:`_scan_symlinked_documents` below, which both :func:`sync`
and :func:`regen` run once per run, independent of which files that run happens
to process (task 7.2, F2).

**Document-format version gate (Req 5.4-5.9).** Before rewriting a matched
document, both :func:`sync` and :func:`regen` parse its frontmatter once and
read :func:`fitdocs.contract.document_version`. A version strictly greater
than :data:`fitdocs.contract.DOC_VERSION` means this engine is older than
whatever wrote the document: nothing is written for that source, a
:class:`DocWarning` names the document, and the file is counted as
``skipped``. A missing, unusable, or lower version proceeds through the
normal merge-and-write path and comes out at the current version -- this is
the whole of the migration story (Req 5.6): regeneration *is* the upgrade,
there is no in-place transform.

The two entry points differ in what "skipped" costs. In :func:`sync` the
gated source is a ``.fit`` file that was never archived, so it is retried
idempotently -- unchanged -- on every subsequent run until a fitdocs that
understands its document format is installed (Req 5.8). In :func:`regen` the
gated item is an already-archived source being rebuilt; regeneration performs
no archive interaction of its own in either branch (the archive commit
happens only in :func:`_write_outputs`, which the gate's early return never
reaches), so the archive is simply left exactly as it was.

**"Skipped" is a presentation bucket, not a completion signal (Req 5.9).**
``SyncReport.skipped`` also holds bytes that were already archived and
processed -- an ordinary, complete outcome. A version-gated source lands in
the *same* tuple for reporting convenience only: it is emphatically **not** a
completed file, and no disposition, cleanup, or archival policy may treat it
as one. The only fact that discriminates "fully processed" from
"version-gated and still pending" is whether the source's bytes are present
under ``fit-archive/`` -- never the ``skipped`` label. A downstream policy
(for example a future ingestion entry point's "move the file once handled"
disposition) that relocated a version-gated source out of its intake
location on the strength of the ``skipped`` bucket would orphan that source
and permanently defeat the retry this gate exists to preserve; such a policy
must gate on archive presence for the specific file it is about to move,
never on the report bucket.

**Unmanaged-frontmatter-key warning (Req 6.3).** When a matched document is
not version-gated (so it will actually be rewritten), the same frontmatter
parse the version gate above just performed is reused -- no second read, no
second parse -- to compute :func:`fitdocs.contract.unmanaged_keys`. The
frontmatter block is tool-owned and rebuilt on every rewrite, so any key that
is in neither :data:`fitdocs.contract.MANAGED_KEYS` nor
:data:`fitdocs.contract.USER_KEYS` is genuinely dropped by this rewrite (Req
6.1, 6.2); a user-owned key is not -- its lines are carried forward verbatim,
below. When the unmanaged set is non-empty, a :class:`DocWarning` names the
document and the sorted key names before they go. The rewrite still proceeds
and the run still succeeds. A version-gated document is never rewritten and so drops
nothing: this check only runs on the branch that falls through the gate.

**Invalid-effort-tag warning (Req 1.4, 3.4, 3.6, 4.7).** Immediately after the
unmanaged-key check above, the same reused frontmatter parse is handed to
:func:`fitdocs.contract.effort_tag`. A well-formed tag or no tag at all warns
nothing here. A malformed tag -- an :class:`~fitdocs.contract.InvalidEffortTag`
-- adds its own :class:`DocWarning` naming the document, ordered after the
unmanaged-key warning above when both fire for the same document. Its detail
is a fixed prefix stating the outcome (preserved unchanged, not in effect
until corrected) followed by
:meth:`~fitdocs.contract.InvalidEffortTag.describe`, the one renderer every
consumer of a malformed tag is designed to share (the ``check`` inspection's
:attr:`~fitdocs.audit.FindingKind.INVALID_EFFORT_TAG` finding for the
identical defect renders it the same way, through the same ``describe()``
renderer). The tag's lines are carried forward verbatim regardless (below,
User-owned frontmatter carry) -- this warning only names the problem; it never
blocks the rewrite or changes the exit code. A version-gated document is never
rewritten and so is never read for its tag: it is warned only for its version.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path
from typing import Final

from fitdocs import AthleteInputs, FitDecodeError, Modality, compute_metrics, parse_fit
from fitdocs.contract import (
    DOC_VERSION,
    InvalidEffortTag,
    document_uuid,
    document_version,
    effort_tag,
    is_workout_document,
    parse_frontmatter,
    sha_of_ref,
    source_refs,
    unmanaged_keys,
    user_owned_lines,
)
from fitdocs.declaration import (
    DECLARATION_FILENAME,
    DeclarationState,
    ensure_declarations,
)
from fitdocs.docio import REMEDY_REPLACE_SYMLINK as _REMEDY_REPLACE_SYMLINK
from fitdocs.docio import SYMLINK_DETAIL as _SYMLINK_DETAIL
from fitdocs.docio import read_frontmatter as _read_frontmatter
from fitdocs.docmerge import RegionError, merge_regions
from fitdocs.inbox import (
    Disposition,
    InboxNote,
    InboxSettings,
    move_processed,
    select_candidates,
    settle,
)
from fitdocs.layout import (
    ARCHIVE_DIR,
    WORKOUTS_DIR,
    activity_uid,
    archive_path,
    doc_path,
    doc_stem,
    source_ref,
)
from fitdocs.quarantine import QuarantineEntry, QuarantineRecord, save_quarantine
from fitdocs.render import Asset, DocContext, MapData, plan_map, render_document
from fitdocs.tiles import TileSource, TileUnavailableError

__all__ = [
    "DocumentMatch",
    "DocWarning",
    "DrainReport",
    "FileFailure",
    "SyncReport",
    "drain",
    "find_document",
    "is_source_level",
    "refresh_declarations",
    "regen",
    "sync",
]


@dataclass(frozen=True)
class DocumentMatch:
    """A resolved existing document and its recorded source-ref history.

    ``path`` is the matched workout document; ``sources`` is its frontmatter
    ``sources`` list as an append-ordered tuple (empty when the key is absent),
    which the caller extends with the newly archived ref when updating in place.
    """

    path: Path
    sources: tuple[str, ...]


def find_document(
    data_root: Path,
    *,
    activity_uid: str,
    source_ref: str,
) -> DocumentMatch | None:
    """Locate the existing workout document for an activity, or ``None`` (Req 3.6).

    Scans ``<data_root>/workouts/*.md`` (top level only, sorted for a
    deterministic order) and returns the first document whose frontmatter matches
    the activity, with ``uuid`` taking precedence over ``sources``:

    1. the first document whose ``uuid`` equals ``activity_uid`` (converges
       re-exports of one session, and survives renames + timezone changes since
       the match is content-based);
    2. otherwise the first document whose ``sources`` list contains
       ``source_ref`` (exact re-syncs and documents without a session UUID).

    Returns ``None`` when no document matches (a fresh-document decision) and
    when ``workouts/`` does not exist yet. Files that are not fitdocs workout
    documents -- missing or garbled frontmatter, not ``type: workout`` -- are
    skipped safely by the contract's readers (Req 1.2); this function only reads
    and never mutates the data root.

    A ``workouts/*.md`` symlink is never followed (wiki-contract Req 7.5, 7.6):
    :func:`~fitdocs.docio.read_frontmatter` refuses it unconditionally, so
    ``frontmatter`` is ``None`` for that path and it is skipped exactly like any
    other unreadable file -- it can never match by ``uuid`` or ``sources``,
    which means a re-export of the very activity it stands in for is treated as
    brand new (a duplicate document results). That refusal is reported, but not
    by this function -- see :func:`_scan_symlinked_documents`, which :func:`sync`
    and :func:`regen` each run once per run, independent of this scan.

    The ``sources`` test is deliberately *membership in the recorded history*, not
    a resolution of each entry: a re-export must reattach to its document whenever
    the incoming ref appears anywhere in that history, including an entry the
    archive no longer holds. Resolving refs is the regeneration concern
    (:func:`_last_source_archive`), not the matching one.
    """
    workouts_dir = data_root / WORKOUTS_DIR
    if not workouts_dir.is_dir():
        return None

    sources_match: DocumentMatch | None = None
    for path in sorted(workouts_dir.glob("*.md")):
        frontmatter = _read_frontmatter(path)
        if frontmatter is None or not is_workout_document(frontmatter):
            continue
        sources = source_refs(frontmatter)
        if document_uuid(frontmatter) == activity_uid:
            # uuid always wins: return the first uuid match in scan order.
            return DocumentMatch(path=path, sources=sources)
        if sources_match is None and source_ref in sources:
            # Hold the first sources match as the fallback if no uuid matches.
            sources_match = DocumentMatch(path=path, sources=sources)
    return sources_match


@dataclass(frozen=True)
class FileFailure:
    """One source file that could not be turned into a document (Req 1.3).

    ``source`` names the offending file (its path, or an archive ref for
    regeneration); ``reason`` is a concise, human-readable explanation naming the
    error kind and its message. A failure isolates one file -- the batch keeps
    going.
    """

    source: str
    reason: str


@dataclass(frozen=True)
class DocWarning:
    """A non-fatal, subject-scoped condition the run reports without failing.

    See :attr:`SyncReport.warnings` for the causes that emit one; this class
    deliberately names none of them, so adding a cause cannot falsify it.

    ``doc`` is the data-root-relative ref the condition affects (it names the
    subject, Req 4.3); ``detail`` is a concise, human-readable reason (for
    example a :class:`~fitdocs.tiles.TileUnavailableError` message). A warning is
    *never* a failure: it rides alongside the written/skipped/failures partition
    and never changes the exit code (Req 4.4).
    """

    doc: str
    detail: str


@dataclass(frozen=True)
class SyncReport:
    """The outcome of a sync run: every discovered file, classified (Req 1.4).

    Each discovered ``.fit`` file lands in exactly one of three tuples --
    ``written`` (a document was produced or updated), ``skipped``, or
    ``failures`` (a :class:`FileFailure`). The tuples are in deterministic
    (sorted-discovery) order.

    ``skipped`` is a **shared presentation bucket with two unrelated causes**:
    the source's bytes were already archived and ``force`` is off (Req 3.2), or
    the matched document records a *newer* document-format version and was left
    untouched (Req 5.5, 5.8). **It is not a completion signal** (Req 5.9). The
    first cause is finished work; the second wrote nothing and archived nothing,
    and depends on the source staying where it is to be retried next run.

    The authoritative discriminator for a fully-processed source is its presence
    in ``fit-archive/`` -- never this label. A disposition, cleanup, or archival
    policy that relocated a source because it appeared here would orphan a
    version-gated source and permanently defeat that retry. See the module
    docstring's version-gate section.

    ``warnings`` is a **separate, additive channel** for non-fatal, subject-scoped
    conditions. Six causes emit one today: a map that could not be rendered
    (Req 4.3, 4.4), a foreign ownership declaration that could not be placed
    (Req 3.6), a document left untouched because it records a newer
    document-format version (Req 5.5), a rewritten document that carried
    frontmatter keys fitdocs does not manage and therefore drops (Req 6.3), a
    rewritten document whose effort tag fitdocs cannot read (preserved
    unchanged, not in effect until corrected, Req 1.4, 3.4, 3.6, 4.7), and a
    ``workouts/*.md`` symlink discovery never follows (Req 7.5, 7.6, task
    7.2 F2). This is the canonical enumeration every other module points at
    instead of repeating (:class:`DocWarning`, :func:`fitdocs.cli._report`) --
    keep it, and only it, current when a seventh cause is added. A
    :class:`DocWarning` rides *alongside* the partition: it never enters
    ``failures``, never moves a file into or out of
    ``written``/``skipped``/``failures``, and never changes the exit code. A
    single document can carry more than one warning (for example a written
    document that both omitted its map and dropped an unmanaged key). Every
    discovered file is still counted exactly once across the three buckets; a
    warning only annotates the subject it names. The field defaults to empty,
    so every existing three-argument construction reports ``warnings == ()``.

    One file can emit **several**. When it does they appear in the order the
    per-file pipeline detects them -- the unmanaged-key notice, then the
    invalid-effort-tag notice, then the map omission -- which is fixed by
    statement order in ``_process_file``, not by any set or mapping
    iteration, so the sequence is reproducible run to run.
    """

    written: tuple[str, ...]
    skipped: tuple[str, ...]
    failures: tuple[FileFailure, ...]
    warnings: tuple[DocWarning, ...] = ()


def refresh_declarations(data_root: Path, warnings: list[DocWarning]) -> None:
    """Refresh every declared directory's ``AGENTS.md`` once per run (3.5, 3.6, 3.8).

    The single shared implementation of "every engine entry point that writes
    into the owned tree refreshes the declarations" (design: DeclarationWriter
    Implementation Notes) -- :func:`sync` and :func:`regen` both call this
    exactly once, before per-file processing starts, and nowhere else. A third
    entry point (the sibling ``inbox`` spec's ``drain()``, expected to become
    the primary ingestion path) calls this same function instead of
    duplicating the refresh; it is not implemented here.

    Delegates entirely to :func:`fitdocs.declaration.ensure_declarations`,
    which writes a directory's declaration only when it is absent or its
    content differs from what fitdocs would write -- the write-when-different
    rule that keeps a no-op run byte- and mtime-identical (Req 3.8). A
    :attr:`~fitdocs.declaration.DeclarationState.FOREIGN` outcome (an
    occupant that is not a readable fitdocs-generated file) is never
    overwritten; instead this appends one :class:`DocWarning` per foreign
    directory onto ``warnings`` naming its declaration path (Req 3.6). A
    foreign declaration therefore never enters ``failures``, never moves any
    discovered file between ``written``/``skipped``/``failures``, and never
    changes the run's exit code -- it only annotates the run the way a map
    omission does (:class:`DocWarning`'s existing contract).

    ``warnings`` is mutated in place (appended to) rather than returned, so the
    caller's single accumulating list gains the declaration warnings without a
    second merge step.
    """
    for outcome in ensure_declarations(data_root):
        if outcome.state is DeclarationState.FOREIGN:
            warnings.append(
                DocWarning(
                    doc=outcome.path,
                    detail=(
                        "an existing file at this path was not written by "
                        "fitdocs (no generated-file marker); it was left "
                        "untouched and the ownership declaration was not "
                        "placed"
                    ),
                )
            )


def _scan_symlinked_documents(data_root: Path) -> tuple[DocWarning, ...]:
    """Warn about each symlinked ``workouts/*.md`` *document*, once per run.

    (Req 7.5, 7.6, task 7.2 F2.)

    A symlinked ``workouts/*.md`` path is a property of the *data root*, not of
    any particular incoming file: it can never be a match candidate for
    :func:`find_document` or :func:`_discover_documents` no matter which file
    a given run happens to process (:func:`~fitdocs.docio.read_frontmatter`
    refuses it before either scan ever sees its content). So rather than
    re-detecting it once per incoming file -- which only warns when *some*
    file's per-file pipeline happens to re-scan ``workouts/`` -- both
    :func:`sync` and :func:`regen` call this exactly once, alongside
    :func:`refresh_declarations`, before any per-file processing starts. That
    means a run over a source directory whose every file is already archived
    (the ordinary steady-state re-sync) still warns about a symlinked sibling,
    and a second consecutive run warns exactly as the first did -- the warning
    depends only on what is on disk under ``workouts/``, never on what the run
    happened to write.

    Returns one :class:`DocWarning` (:func:`_symlink_warning`) per symlinked
    path found, sorted for a deterministic order; ``()`` when ``workouts/``
    does not exist or holds no symlinked document. The ownership declaration
    is the one deliberate exemption (Req 3.7): a symlinked
    :data:`~fitdocs.declaration.DECLARATION_FILENAME` is found by this glob and
    skipped here, because :func:`refresh_declarations` already reports it as a
    *foreign* declaration -- the true finding -- and this function's wording
    would assert a re-export consequence that is false of it. Read-only: this
    only glob-lists and ``is_symlink()``-tests, it never opens a file.
    """
    workouts_dir = data_root / WORKOUTS_DIR
    if not workouts_dir.is_dir():
        return ()
    return tuple(
        _symlink_warning(data_root, path)
        for path in sorted(workouts_dir.glob("*.md"))
        # Req 3.7: the ownership declaration is never treated as a workout
        # document in any document scan. A symlinked ``AGENTS.md`` is already
        # reported by ``ensure_declarations`` as a foreign declaration; warning
        # again here would assert a re-export/archive consequence that is false
        # of it. This is the fifth ``*.md`` tree-walk in ``src/``; the other
        # four all exclude the declaration via ``is_workout_document``, which
        # this scan cannot use because it deliberately never reads the file.
        if path.is_symlink() and path.name != DECLARATION_FILENAME
    )


def sync(
    source_dir: Path,
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    force: bool = False,
) -> SyncReport:
    r"""Turn every ``.fit`` file under ``source_dir`` into a workout document.

    Discovers ``.fit`` files recursively and case-insensitively in a deterministic
    (sorted) order (Req 1.1) and runs the per-file pipeline for each. The source
    directory is opened strictly read-only -- nothing under it is written, moved,
    or deleted (Req 1.6). Each file is classified into the returned
    :class:`SyncReport`: *written* (a document produced or updated), *skipped* (its
    bytes are already archived and ``force`` is off, Req 3.2, 3.3), or *failed*.

    Decode errors (:class:`~fitdocs.FitDecodeError` and subclasses), region
    conflicts (:class:`~fitdocs.docmerge.RegionError`), and any unexpected per-file
    exception become :class:`FileFailure`\ s without aborting the batch (Req 1.3).
    A second run over the same inputs writes nothing -- every file is skipped and
    the data root is left byte-identical (Req 4.2). ``force`` re-processes
    already-archived files (re-rendering their documents) but never rewrites the
    immutable archive (Req 3.5).

    ``tiles`` is the injected basemap-tile source for the per-file map path,
    always supplied by the caller (the CLI constructs one store per command). Each
    non-strength document whose samples carry a position gets a route map,
    resolving its exact tile set through ``tiles`` -- the sole network access, only
    on a cache miss (Req 4.2). A tile that cannot be resolved omits the map and
    records a :class:`DocWarning` naming the document (Req 4.3); it is never a
    failure and never changes the exit code (Req 4.4).

    Before any per-file processing, :func:`refresh_declarations` runs once over
    ``data_root`` (Req 3.5, 3.6, 3.8): every declared directory's ``AGENTS.md`` is
    written or refreshed, and a foreign occupant becomes a :class:`DocWarning`
    rather than a failure. Alongside it, :func:`_scan_symlinked_documents` also
    runs exactly once, warning about every ``workouts/*.md`` symlink on disk
    regardless of which files this run goes on to process -- so a run over a
    source directory that is entirely already-archived (no per-file processing
    reaches the symlink-adjacent scans in :func:`find_document` at all) still
    reports it (Req 7.5, 7.6, task 7.2 F2). Both are the same shared steps
    :func:`regen` calls -- neither function has its own copy.

    **Document-format version gate (Req 5.4, 5.5, 5.8, 5.9).** When an incoming
    file matches an existing document whose recorded ``doc_version`` is newer
    than this fitdocs produces, nothing is written for that source, a
    :class:`DocWarning` names the document, and the file is counted as
    *skipped* alongside ordinary already-archived skips. Because the source's
    bytes were never archived, the *next* run over the same input repeats this
    exact gate rather than treating the source as done (Req 5.8) -- see the
    module docstring for why the ``skipped`` count is not a completion signal
    (Req 5.9). A document recording no version, an unusable one, or an older
    one is upgraded in place at the current version instead, its user-owned
    regions carried over verbatim (Req 5.4, 5.6).
    """
    written: list[str] = []
    skipped: list[str] = []
    failures: list[FileFailure] = []
    warnings: list[DocWarning] = []
    refresh_declarations(data_root, warnings)
    warnings.extend(_scan_symlinked_documents(data_root))

    for source_file in _discover_fit_files(source_dir):
        _process_isolated(
            source_file,
            data_root,
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            force=force,
            source_label=str(source_file),
            written=written,
            skipped=skipped,
            failures=failures,
            warnings=warnings,
        )

    return SyncReport(
        written=tuple(written),
        skipped=tuple(skipped),
        failures=tuple(failures),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class DrainReport:
    """An inbox drain outcome: the standard sync report plus inbox channels
    (design: DrainOrchestration, inbox Req 2.3, 4.2, 7.1).

    ``sync`` carries the exact same :class:`SyncReport` contract an
    explicit-source :func:`sync` call would produce over the same admitted
    files -- every admitted candidate lands in exactly one of its
    ``written``/``skipped``/``failures`` tuples, and only its ``failures``
    (plus the load pass, outside this module) drives the failure exit code
    (inbox Req 4.6, 7.1). ``inbox`` names the drained inbox path (inbox Req
    2.3). ``deferred`` is the inbox-only channel for candidates that were not
    admitted this run because they were not observed stable across the
    settle interval, or because a stable candidate could not be read (inbox
    Req 4.2) -- never a failure and never a quarantine entry.

    ``moved`` and ``move_failures`` are the disposition channels (inbox Req
    6.2, 6.4, 6.5): populated only under :attr:`~fitdocs.inbox.Disposition.MOVE`,
    for candidates whose content hash :func:`drain` confirmed present in
    ``fit-archive/`` once their processing finished. Under the default
    :attr:`~fitdocs.inbox.Disposition.LEAVE` disposition, or when
    ``processed_dir`` is not supplied, both stay empty and nothing in the
    inbox is touched.
    """

    inbox: str
    """The path drained, as given to :func:`drain` (inbox Req 2.3)."""

    sync: SyncReport
    """The unchanged sync report over every admitted candidate."""

    deferred: tuple[InboxNote, ...]
    """Candidates left untouched this run: unstable across the settle
    interval, or stable but unreadable (inbox Req 4.2). Retried, unchanged,
    on a later drain."""

    quarantined: tuple[InboxNote, ...]
    """Stable, readable candidates whose content hash is already present in
    the quarantine record, and *not* being retried this drain (inbox Req 5.2).
    Each entry's ``detail`` is the reason recorded when the file was first
    quarantined. These candidates never reach :func:`_process_isolated` --
    they are excluded from ``sync.written``/``skipped``/``failures`` entirely,
    and never drive the failure exit code by themselves (inbox Req 5.3)."""

    moved: tuple[str, ...]
    """Destinations (as strings) of every admitted candidate relocated out of
    the inbox this drain, under :attr:`~fitdocs.inbox.Disposition.MOVE`
    (inbox Req 6.2). Always ``()`` under the leave-in-place default."""

    move_failures: tuple[InboxNote, ...]
    """A candidate that finished processing -- its content is archived -- but
    whose move out of the inbox failed (inbox Req 6.5). The already-completed
    processing stands; the file stays in the inbox and is retried next drain.
    Never folded into ``failures`` or ``moved``; never changes the run's exit
    code."""


def drain(
    inbox: Path,
    data_root: Path,
    *,
    settings: InboxSettings,
    processed_dir: Path | None,
    quarantine: QuarantineRecord,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    force: bool = False,
    retry_quarantined: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> DrainReport:
    r"""Drain the inbox: select, settle, quarantine-partition, and process
    eligible ``.fit`` files through the unmodified per-file pipeline (design:
    DrainOrchestration, inbox Req 2.1, 2.3, 2.4, 3.5, 4.2, 4.6, 5.1-5.5, 5.7,
    7.1, 7.4, 7.6).

    Sequence, mirroring the design's per-drain ordering for the slice this
    task builds: refresh the ownership declarations once, exactly where and
    how :func:`sync` does (inbox Req 7.6). Alongside it,
    :func:`_scan_symlinked_documents` also runs exactly once, before any
    per-file processing -- the same once-per-run parity :func:`sync` and
    :func:`regen` already share (task 7.2, F2; this is beyond the inbox
    spec's own requirement list, kept for parity with the other two entry
    points rather than mandated by it). Then select candidates
    (:func:`fitdocs.inbox.select_candidates`) against *settings*, so ignored
    files never reach any channel (inbox Req 3.5); settle them as one batch
    (:func:`fitdocs.inbox.settle`), through the injected *sleep* so a test
    spends no wall-clock time; read each stable candidate once -- the read
    doubles as a readability probe, so a candidate that observes as stable
    but cannot be read (for example an unmaterialized cloud placeholder) is
    *deferred* with its reason, never failed and never quarantined (inbox
    Req 4.2).

    **Quarantine partition (inbox Req 5.1-5.5, 5.7).** That same probe read's
    bytes are hashed (sha256, matching the archive's content identity) with no
    second read of the candidate. When that hash is already present in
    *quarantine* and *retry_quarantined* is not set, the candidate is *not*
    handed to the pipeline at all: it is reported once in ``quarantined`` with
    its recorded reason (inbox Req 5.2) and never enters
    ``sync.written``/``skipped``/``failures``. Every other stable, readable
    candidate -- new content, or a quarantined one being retried -- is handed
    to the same :func:`_process_isolated` call :func:`sync` uses, with the
    candidate's inbox-relative path (``candidate.rel``) as its
    ``source_label``, so report entries name inbox-relative paths and every
    admitted candidate is classified exactly as an explicit-source
    :func:`sync` over the same bytes would classify it (inbox Req 2.1, 2.3).
    A fresh failure is recorded into the quarantine only when
    :func:`_fresh_failure_is_source_level` -- which *re-derives* the fault by
    re-parsing the probe-read bytes, rather than inspecting the exception the
    pipeline actually raised (:func:`_process_isolated` isolates and discards
    it) -- says the re-derived fault is source-level per :func:`is_source_level`
    (Req 5.1); a fault that is a property of the existing document instead --
    a damaged preserved region being the representative case, and anything
    the re-derivation does not recognize -- is reported as a failure and
    deliberately left unrecorded (Req 5.7), so repairing the document is
    enough for the next drain to succeed. A retried candidate that fails
    again always has its entry updated with the new reason and is reported as
    a failure (Req 5.5), regardless of the re-derived level -- its content
    was already known-bad; one that now succeeds has its entry removed.
    *force* governs archive-skip policy only and never implies retry -- the
    two are independent.

    The composed :class:`DrainReport` wraps the resulting :class:`SyncReport`
    unmodified -- built from the same accumulating lists
    :func:`_process_isolated` expects, exactly as :func:`sync` builds its own
    -- alongside the ``deferred`` and ``quarantined`` channels. Only
    :class:`FileFailure`\ s inside that ``sync`` report drive the failure
    outcome; a drain whose only exceptional entries are deferrals and/or
    already-quarantined files reports success (inbox Req 4.6, 5.3).

    The quarantine record is evolved in memory as the drain proceeds and
    persisted (:func:`~fitdocs.quarantine.save_quarantine`) exactly once, at
    the end, and only if any entry was added, updated, or removed during this
    drain (inbox Req 7.4) -- an unchanged drain (every candidate already
    quarantined and not retried, or none at all) never touches the record
    file.

    **Disposition (inbox Req 6.2, 6.4, 6.5).** Once a candidate's per-file
    processing finishes *without failing this drain*, it is disposed of iff
    its content hash -- the same sha256 the quarantine check above already
    computed, not re-hashed or re-read -- is present under ``fit-archive/``:
    this is the positive, filesystem-checked gate, never the ``skipped``
    label. Written files pass it (the archive copy is the pipeline's last
    write); already-archived dedupe-skips pass it (that is exactly why they
    were skipped); a skip that deliberately archived nothing -- wiki-contract's
    newer-``doc_version`` gate above all -- fails it, so that file stays in
    the inbox and the next drain re-selects it as a candidate. Failed,
    deferred, and quarantined candidates never reach this gate at all -- the
    "did not fail this drain" condition matters in its own right, separately
    from archive presence: under ``force=True`` an already-archived candidate
    bypasses ``_process_file``'s ordinary dedupe skip and is reprocessed from
    scratch, so a damaged preserved region can raise a failure for content
    that *is* already present in ``fit-archive/`` -- archive presence alone
    would wrongly pass that failed candidate. Disposition only runs under
    :attr:`~fitdocs.inbox.Disposition.MOVE` with *processed_dir* supplied;
    under the leave-in-place default, or if *processed_dir* is ``None``,
    nothing in the inbox is touched and
    :attr:`DrainReport.moved`/:attr:`DrainReport.move_failures` stay empty.
    A candidate that passes the gate has its already-computed hash *passed to*
    :func:`fitdocs.inbox.move_processed` (collision-safe, ``shutil.move``),
    which uses it only for collision-safe naming and never re-hashes it; the
    drain never reads the candidate a second time (``shutil.move`` may copy
    the bytes itself when the destination is on another volume, but that is
    the move, not a re-read for the hash): success appends its destination to
    ``moved``; a
    failure -- the already-completed processing stands, and the file stays in
    the inbox for a later drain to retry -- appends an :class:`InboxNote` to
    ``move_failures`` instead, its own channel, never folded into
    ``failures`` or ``moved`` and never affecting the run's exit code.
    """
    written: list[str] = []
    skipped: list[str] = []
    failures: list[FileFailure] = []
    warnings: list[DocWarning] = []
    deferred: list[InboxNote] = []
    quarantined: list[InboxNote] = []
    moved: list[str] = []
    move_failures: list[InboxNote] = []

    refresh_declarations(data_root, warnings)
    warnings.extend(_scan_symlinked_documents(data_root))

    candidates = select_candidates(inbox, settings)
    settle_result = settle(
        candidates, settle_seconds=settings.settle_seconds, sleep=sleep
    )
    deferred.extend(settle_result.deferred)

    record = quarantine
    record_changed = False

    for candidate in settle_result.stable:
        try:
            data = candidate.path.read_bytes()
        except OSError as exc:
            deferred.append(
                InboxNote(
                    subject=candidate.rel,
                    detail=(
                        f"{candidate.rel}: could not be read ({exc}); left in "
                        "place and retried on a later drain"
                    ),
                )
            )
            continue

        sha = hashlib.sha256(data).hexdigest()
        recorded_entry = record.get(sha)

        if recorded_entry is not None and not retry_quarantined:
            # Already known-bad content, no retry requested: report quietly
            # from the record and never touch the pipeline (Req 5.2, 5.3).
            quarantined.append(
                InboxNote(subject=candidate.rel, detail=recorded_entry.reason)
            )
            continue

        failures_before = len(failures)
        _process_isolated(
            candidate.path,
            data_root,
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            force=force,
            source_label=candidate.rel,
            written=written,
            skipped=skipped,
            failures=failures,
            warnings=warnings,
        )

        failed_this_candidate = len(failures) > failures_before
        if failed_this_candidate:
            reason = failures[-1].reason
            if recorded_entry is not None:
                # A retried quarantined file failed again: the entry is
                # always updated with the new reason, regardless of fault
                # level (Req 5.5) -- its content was already known-bad.
                record = record.with_entry(
                    QuarantineEntry(sha256=sha, name=candidate.rel, reason=reason)
                )
                record_changed = True
            elif _fresh_failure_is_source_level(data):
                # A new failure caused by the source bytes themselves: record
                # it so it is reported quietly on future drains (Req 5.1).
                record = record.with_entry(
                    QuarantineEntry(sha256=sha, name=candidate.rel, reason=reason)
                )
                record_changed = True
            # else: a document-level (or otherwise unrecognized) fault is
            # reported as a failure and deliberately left unrecorded, so
            # repairing the document is enough for the next drain to succeed
            # (Req 5.7).
        elif recorded_entry is not None:
            # A retried quarantined file succeeded: clear its entry (Req 5.5).
            record = record.without(sha)
            record_changed = True

        # Disposition (inbox Req 6.2, 6.4, 6.5): a candidate that did not
        # fail is disposed of iff its content is now present in
        # `fit-archive/` -- the positive, filesystem-checked gate, never the
        # `skipped` label. A version-gated skip (wiki-contract's newer-
        # doc_version gate) deliberately archives nothing, so it fails this
        # check and stays in the inbox for the next drain to re-select.
        # Reuses `sha` from the probe read above -- no re-hash, no re-read.
        # Runs only under the move disposition with a processed directory
        # supplied; the leave-in-place default (and a MOVE disposition
        # missing its processed_dir) touches nothing here.
        if (
            not failed_this_candidate
            and settings.disposition is Disposition.MOVE
            and processed_dir is not None
            and archive_path(data_root, sha).exists()
        ):
            move_result = move_processed(candidate, processed_dir, sha)
            if isinstance(move_result, InboxNote):
                move_failures.append(move_result)
            else:
                moved.append(move_result)

    if record_changed:
        save_quarantine(data_root, record)

    sync_report = SyncReport(
        written=tuple(written),
        skipped=tuple(skipped),
        failures=tuple(failures),
        warnings=tuple(warnings),
    )
    return DrainReport(
        inbox=str(inbox),
        sync=sync_report,
        deferred=tuple(deferred),
        quarantined=tuple(quarantined),
        moved=tuple(moved),
        move_failures=tuple(move_failures),
    )


def is_source_level(exc: BaseException) -> bool:
    """Whether *exc* names a fault that is a property of the ``.fit`` bytes
    themselves -- the source -- rather than of an existing document (inbox
    Req 5.1, 5.7).

    A single predicate over the failure's exception type: ``True`` only for
    :class:`~fitdocs.FitDecodeError` and its subclasses (fit-ingest's
    decode/integrity errors), the fit-ingest-recognized ways the bytes
    themselves cannot be decoded or parsed. **Defaults to ``False`` for
    everything else it does not recognize** -- including
    :class:`~fitdocs.docmerge.RegionError` (a fault in the *existing
    document*, the representative document-level case) and any unexpected
    exception type. That default is deliberate: an unrecognized fault is
    loud on every run rather than silently remembered, so the only cost of
    not recognizing a new fault type is repetition, never silence.
    """
    return isinstance(exc, FitDecodeError)


def _fresh_failure_is_source_level(data: bytes) -> bool:
    """Whether the failure the pipeline just isolated for *data* is
    source-level (:func:`is_source_level`), re-deriving the underlying
    exception from the same already-in-memory bytes the probe read produced
    -- no second read of the candidate.

    :func:`_process_isolated` isolates its exception internally and reports
    only a :class:`FileFailure`, so this attempts the pure, side-effect-free
    first pipeline step (:func:`~fitdocs.parse_fit`) directly on *data* to
    recover it: a fault in decoding these exact bytes reproduces
    deterministically here, and any downstream fault (for example a region
    conflict merging into an existing document) leaves this parse succeeding,
    which is exactly the "not source-level" answer (Req 5.7).

    This re-derivation is *not* a perfect reconstruction of what the pipeline
    itself hit, and one known divergence is upstream of parsing rather than
    downstream: :func:`_process_file` performs its own
    ``source_file.read_bytes()`` rather than reusing the drain's probe-read
    ``data``, so a candidate that vanishes or becomes unreadable in the
    (typically sub-millisecond) window between the probe read and that
    second read raises ``OSError`` inside the pipeline instead of ever
    reaching :func:`~fitdocs.parse_fit`. Because *data* here is the probe
    read's own bytes -- captured before that race could happen -- this
    function still re-parses successfully-read, genuinely undecodable bytes
    and classifies that ``OSError``-caused :class:`FileFailure` as
    source-level too, recording it with the reason ``OSError: ...`` rather
    than the true (transient, unrelated-to-content) cause. This is an
    accepted, narrow imprecision of the re-derivation strategy: the recorded
    reason still names ``OSError`` honestly, and the recorded *content* is
    genuinely undecodable either way -- this branch is reached only when
    re-parsing the probe bytes raises -- so the entry itself is correct even
    though its reason names the transient cause. The entry then persists:
    later drains report it from the record without re-processing it, until
    ``--retry-quarantined`` re-attempts it.
    """
    try:
        parse_fit(data)
    except Exception as exc:
        return is_source_level(exc)
    return False


def regen(
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
) -> SyncReport:
    r"""Rebuild every workout document from the data root alone (Req 4.3, 4.4).

    Regeneration takes no source directory: it reconstructs documents from the
    archived ``.fit`` sources under ``fit-archive/`` plus the optional athlete
    inputs, so a data root with the original exports long deleted still rebuilds
    completely (Req 4.4). Discovery has two parts, both feeding the same per-file
    pipeline ``sync`` uses (only discovery and skip policy differ):

    * **Every document re-renders from its current source.** For each
      ``workouts/*.md`` workout document, the *last* entry of its frontmatter
      ``sources`` history (the current render source) is resolved to its archived
      file and re-rendered. Because those bytes are the archive the document was
      rendered from, the pipeline's lookup matches this same document, so
      ``merge_regions`` carries its ``notes``/``workout``/``load`` regions over
      verbatim while the generated content is refreshed (Req 4.3, 10.2). A
      document whose history is empty or whose current source is missing from the
      archive cannot be regenerated -- it becomes a :class:`FileFailure` and is
      left untouched, the batch continuing.
    * **Archived sources referenced by no document render fresh.** Any
      ``fit-archive/<sha>.fit`` whose sha appears in no document's ``sources``
      (its document was deleted -- documents are derived artifacts) is rendered
      into a new document (Req 4.4).

    ``force`` is implied for every item this discovery produces, so an
    already-archived source is never skipped on that basis alone; the *only*
    remaining skip is the document-format version gate below. The immutable
    archive is still never rewritten (Req 3.5). Region conflicts
    (:class:`~fitdocs.docmerge.RegionError`), decode errors, and unexpected
    per-file exceptions become :class:`FileFailure`\ s without aborting the batch
    (Req 1.3). Given an identical archive, athlete file, and ``tz``, output is
    byte-identical on every run (Req 4.1).

    **Document-format version gate (Req 5.4, 5.5, 5.8, 5.9).** When a document
    records a ``doc_version`` newer than this fitdocs produces, nothing is
    written for it, a :class:`DocWarning` names it, and it is counted as
    *skipped*. Unlike :func:`sync`, regeneration performs no archive
    interaction in either branch of the gate -- it rebuilds *from* the
    archive and never writes to it in this pass -- so the archive is simply
    left exactly as it was; there is no unarchived-source retry story here,
    only "this document was not touched". A document recording no version, an
    unusable one, or an older one is upgraded in place at the current version
    instead, its user-owned regions carried over verbatim (Req 5.4, 5.6) --
    this *is* the migration path (Req 5.6).

    ``tiles`` is the injected basemap-tile source for the per-file map path,
    identical to :func:`sync` and always supplied by the caller: each non-strength
    document with positions carries a route map (resolving tiles on a cache miss,
    the sole network access, Req 4.2), and an unresolvable tile omits the map with
    a :class:`DocWarning` (Req 4.3) rather than failing (Req 4.4). With a warm tile
    cache the map path adds no clock, randomness, or ordering, so output stays
    byte-identical on every run (Req 4.1).

    Before any per-file processing, :func:`refresh_declarations` and
    :func:`_scan_symlinked_documents` each run once over ``data_root`` (Req
    3.5, 3.6, 3.8, 7.5, 7.6) -- the identical shared steps :func:`sync` calls,
    not a second copy of either.
    """
    written: list[str] = []
    skipped: list[str] = []
    failures: list[FileFailure] = []
    warnings: list[DocWarning] = []
    refresh_declarations(data_root, warnings)
    warnings.extend(_scan_symlinked_documents(data_root))

    # Re-render each document from its current (last) source, accumulating every
    # archive sha any document references so unreferenced archives can be found.
    referenced: set[str] = set()
    for document, sources in _discover_documents(data_root):
        referenced.update(sha for sha in map(sha_of_ref, sources) if sha is not None)
        doc_ref = document.relative_to(data_root).as_posix()
        archive = _last_source_archive(data_root, sources)
        if archive is None:
            # No archived source to rebuild from: an empty/unresolvable history or
            # a current source missing from the archive. Fail this document (left
            # untouched) and keep going (an orphaned archive it references, if any,
            # renders fresh below).
            failures.append(
                FileFailure(
                    source=doc_ref,
                    reason=(
                        "no archived source to regenerate from: the document's "
                        "'sources' history is empty or unresolvable, or its "
                        "current source is missing from the archive"
                    ),
                )
            )
            continue
        _process_isolated(
            archive,
            data_root,
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            force=True,
            source_label=doc_ref,
            written=written,
            skipped=skipped,
            failures=failures,
            warnings=warnings,
        )

    # Archived sources no document references render fresh (docs are derived).
    for archive in _unreferenced_archives(data_root, referenced):
        _process_isolated(
            archive,
            data_root,
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            force=True,
            source_label=archive.relative_to(data_root).as_posix(),
            written=written,
            skipped=skipped,
            failures=failures,
            warnings=warnings,
        )

    return SyncReport(
        written=tuple(written),
        skipped=tuple(skipped),
        failures=tuple(failures),
        warnings=tuple(warnings),
    )


def _process_isolated(
    source_file: Path,
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    force: bool,
    source_label: str,
    written: list[str],
    skipped: list[str],
    failures: list[FileFailure],
    warnings: list[DocWarning],
) -> None:
    """Run the per-file pipeline for one item, isolating any failure (Req 1.3).

    Shared by :func:`sync` and :func:`regen`: the pipeline (``_process_file``) is
    identical -- only discovery and the ``source_label`` recorded in the report
    differ. Classifies the item into ``written`` (a document produced or updated),
    ``skipped`` (already archived and not forcing, Req 3.2, **or** version-gated
    because the matched document is newer, Req 5.5), or ``failures``. Expected
    per-file errors -- an undecodable source (Req 1.2, 1.3) or a damaged region in
    the existing document (Req 10.3) -- and any unexpected per-file exception all
    become a :class:`FileFailure`; the batch never aborts. (``BaseException`` --
    ``KeyboardInterrupt``, ``SystemExit`` -- deliberately propagates.)

    Zero or more :class:`DocWarning`\\ s are something ``_process_file``
    *returns*, so they can ride with either non-failing branch: a version-gate
    skip carries exactly one (Req 5.5) alongside its ``None`` outcome; a
    written file may carry a map omission (Req 4.3), an
    unmanaged-frontmatter-key notice (Req 6.3), both, or neither -- most
    written files and every already-archived skip carry none. The invariant is
    one-directional: a *raising* file can never carry one, because when
    ``_process_file`` raises (a :class:`FileFailure`) it returns nothing at all
    (Req 4.4). A ``workouts/*.md`` symlink is never among these -- it is not a
    per-file condition, so it never rides with any single file's outcome; see
    :func:`_scan_symlinked_documents`, which the caller (:func:`sync` or
    :func:`regen`) runs once per run instead.
    """
    try:
        outcome, file_warnings = _process_file(
            source_file, data_root, athlete=athlete, tz=tz, tiles=tiles, force=force
        )
    except (FitDecodeError, RegionError) as exc:
        failures.append(FileFailure(source=source_label, reason=_reason(exc)))
    except Exception as exc:
        failures.append(FileFailure(source=source_label, reason=_reason(exc)))
    else:
        if outcome is None:
            skipped.append(source_label)
        else:
            written.append(outcome)
        # Zero or more warnings can ride with either non-failing outcome -- a
        # written file may carry a map omission, an unmanaged-key notice, both,
        # or neither; a version-gated skip carries exactly one. Only the
        # converse is guaranteed: a raising file never has any.
        warnings.extend(file_warnings)


def _discover_fit_files(source_dir: Path) -> list[Path]:
    """Discover ``.fit`` files under ``source_dir``, recursively and case-insensitively.

    Returns every regular file whose extension is ``.fit`` (matching ``.fit``,
    ``.FIT``, ``.Fit``, ...) at any depth, sorted for a deterministic processing
    order (Req 1.1). The directory is only read -- discovery never writes, moves,
    or deletes anything (Req 1.6).
    """
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".fit"
    )


def _process_file(
    source_file: Path,
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    force: bool,
) -> tuple[str | None, tuple[DocWarning, ...]]:
    """Run the per-file pipeline; return ``(written-doc-ref | None, warnings)``.

    The first element is the data-root-relative POSIX path of the document written
    or updated on success, or ``None`` when the file is skipped -- either because
    its bytes are already archived and ``force`` is off (Req 3.2, 3.3), or because
    a matched document records a document-format version newer than this fitdocs
    can produce (Req 5.5, 5.8; see the module docstring's version-gate section).
    The second element is a tuple of zero or more :class:`DocWarning`\\ s: a
    version-gate skip carries exactly one and nothing else (the early return
    below); a written document may carry a non-fatal map omission (Req 4.3,
    4.4), an unmanaged-frontmatter-key notice (Req 6.3), both, or neither.

    **Map path (impure, Req 1.1, 3.5, 4.2, 4.3, 4.4).** When the activity is an
    outdoor (non-strength) modality -- the exact set of views that render a
    ``## Map`` section, so a fetched tile always corresponds to a rendered map (Req
    3.5) -- the route is planned from the position channels and its exact tile set
    is resolved through the injected ``tiles`` source *before* the pure render,
    then injected as ``map_data``. A tile that is neither cached nor fetchable
    raises :class:`~fitdocs.tiles.TileUnavailableError`, which becomes a
    :class:`DocWarning` naming this document while the document renders *without* a
    Map section (Req 4.3) -- never a failure (Req 4.4). The strength view renders
    no Map section, so its map path is skipped entirely (Req 3.5).

    Propagates the ingest decode errors and :class:`~fitdocs.docmerge.RegionError`
    for the caller to isolate as a per-file failure (Req 1.3); crucially, every
    filesystem write happens only *after* a successful merge, so a region conflict
    leaves the existing document untouched (Req 10.3).
    """
    data = source_file.read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    archive = archive_path(data_root, sha)
    if archive.exists() and not force:
        # Identical bytes are already archived: skip (dedups exact re-syncs and
        # two identically-named-differently files with the same content) (3.2, 3.3).
        return None, ()

    activity = parse_fit(data)
    metrics = compute_metrics(activity, athlete)

    uid = activity_uid(activity, sha)
    new_ref = source_ref(sha)
    # ``pending_warnings`` accumulates whatever the version gate or
    # unmanaged-key check below add for the file that matched -- one list,
    # appended to only, so a later exception in this function (a decode error,
    # a region conflict) discards every one of them together, preserving "a
    # raising file never carries a warning" (Req 4.4). A symlinked
    # workouts/*.md path is never a match candidate for ``find_document``
    # (Req 7.5, 7.6) and is never reported here at all -- see
    # ``_scan_symlinked_documents``, run once per run by the caller.
    pending_warnings: list[DocWarning] = []
    match = find_document(data_root, activity_uid=uid, source_ref=new_ref)

    # Document-format version gate (Req 5.4, 5.5, 5.7, 5.8, 5.9). Read the
    # matched document's frontmatter exactly ONCE here -- ``existing_text`` is
    # reused below for the merge instead of a second disk read/parse -- and
    # decide before any write. A version strictly greater than DOC_VERSION
    # means this fitdocs is older than whatever produced the document: write
    # nothing, warn, and let the caller count the file as skipped. Because the
    # early return happens before ``_write_outputs`` is ever reached, the
    # source stays unarchived (sync) or the archive stays untouched (regen).
    # Missing, unusable (a bool, a string, a float), or lower versions are
    # honest "out of date" and fall through unchanged to the normal
    # merge-and-write path below, coming out at the current version.
    existing_text: str | None = None
    carried: tuple[str, ...] = ()
    if match is not None:
        existing_text = match.path.read_text(encoding="utf-8")
        existing_frontmatter = parse_frontmatter(existing_text)
        existing_version = (
            document_version(existing_frontmatter)
            if existing_frontmatter is not None
            else None
        )
        if existing_version is not None and existing_version > DOC_VERSION:
            doc_ref = match.path.relative_to(data_root).as_posix()
            detail = _newer_version_detail(existing_version)
            pending_warnings.append(DocWarning(doc=doc_ref, detail=detail))
            return None, tuple(pending_warnings)

        # Unmanaged-frontmatter-key warning (Req 6.3, design: "Unmanaged-key
        # detection on rewrite"). Reuses ``existing_frontmatter`` -- the same
        # parse the version gate above just performed, no second read or
        # parse -- so this never fires for a version-gated document (it drops
        # nothing, since the early return above already left with a `None`
        # write). The rewrite below still proceeds and still drops these keys;
        # this only names them before they go.
        if existing_frontmatter is not None:
            dropped = unmanaged_keys(existing_frontmatter)
            if dropped:
                match_ref = match.path.relative_to(data_root).as_posix()
                pending_warnings.append(
                    DocWarning(doc=match_ref, detail=_unmanaged_keys_detail(dropped))
                )

            # Invalid-effort-tag warning (Req 1.4, 3.4, 3.6, 4.7, design:
            # "SyncEngine"). Reuses the same ``existing_frontmatter`` parse
            # above -- no second read, no second parse. A malformed tag is
            # never a failure: the rewrite still proceeds and its lines are
            # still carried (below) unchanged; this only names the problem
            # before the run continues. A valid tag, or no tag at all,
            # ``effort_tag`` returns as ``EffortTag``/``None`` and neither
            # warns here.
            tag = effort_tag(existing_frontmatter)
            if isinstance(tag, InvalidEffortTag):
                match_ref = match.path.relative_to(data_root).as_posix()
                pending_warnings.append(
                    DocWarning(doc=match_ref, detail=_invalid_effort_tag_detail(tag))
                )

        # User-owned frontmatter carry (Req 4.1, 4.2, 4.4, 4.5, 4.6): every
        # top-level frontmatter entry whose key is user-owned (``effort`` and
        # its three companions) is carried forward verbatim into the
        # rewritten document, including any continuation lines its value
        # spans -- whether or not it forms a valid effort tag, since carrying
        # never inspects validity (that check, and its warning, is a
        # different concern). Computed from ``existing_text``, already read
        # above for the version gate: no second read, no second parse.
        carried = user_owned_lines(existing_text.split("\n"))

    # Source history: existing refs (minus any already equal to the new one) with
    # the new ref appended last, so the current render source is always the unique
    # final entry -- a re-export appends onto the existing history (Req 3.4, 3.6).
    existing_refs = match.sources if match is not None else ()
    history = tuple(ref for ref in existing_refs if ref != new_ref) + (new_ref,)

    def taken(candidate: str) -> bool:
        # A stem is taken only by a *different* activity's document; the activity's
        # own matched document never collides with itself (Req 2.6).
        candidate_path = doc_path(data_root, candidate)
        if not candidate_path.exists():
            return False
        return match is None or candidate_path != match.path

    stem = doc_stem(activity, uid, tz, taken)
    # The write target -- and thus the data-root-relative doc ref used for both the
    # report entry and any map warning -- is known once the stem/match are resolved.
    target = match.path if match is not None else doc_path(data_root, stem)
    doc_ref = target.relative_to(data_root).as_posix()

    # Resolve prepared map inputs before the pure render, only for the outdoor
    # (non-strength) views that render a Map section (Req 3.5). Tile unavailability
    # degrades to a warning naming this document; the doc renders mapless (4.3, 4.4).
    map_data: MapData | None = None
    warnings: list[DocWarning] = pending_warnings
    if activity.modality is not Modality.STRENGTH:
        plan = plan_map(activity.samples.latitude_deg, activity.samples.longitude_deg)
        if plan is not None:
            try:
                resolved = tiles.resolve(plan.tiles)
            except TileUnavailableError as exc:
                warnings.append(DocWarning(doc=doc_ref, detail=_reason(exc)))
            else:
                map_data = MapData(
                    plan=plan,
                    tiles=tuple((ref, resolved[ref]) for ref in plan.tiles),
                    attribution=tiles.attribution,
                )

    ctx = DocContext(
        activity=activity,
        metrics=metrics,
        athlete=athlete,
        doc_stem=stem,
        source_refs=history,
        tz=tz,
        map_data=map_data,
        user_frontmatter=carried,
    )
    rendered = render_document(ctx)

    # ``existing_text`` is non-None exactly when ``match`` is -- it is read in
    # that branch and nowhere else -- so narrowing on it is equivalent to
    # narrowing on ``match`` and needs no ``assert`` (which ``python -O`` would
    # strip, leaving ``merge_regions`` to be handed ``None``).
    if existing_text is not None:
        # An existing document (a rename, timezone change, or re-export) is updated
        # in place: preserved regions carry over verbatim (Req 3.6, 4.3, 10.2). A
        # damaged region raises RegionError here -- before any write (Req 10.3).
        # It was already read once above for the version gate; reusing it here
        # avoids a second disk read and a second parse.
        markdown = merge_regions(rendered.markdown, existing_text)
    else:
        markdown = rendered.markdown

    _write_outputs(data_root, target, markdown, rendered.assets, archive, data)
    return doc_ref, tuple(warnings)


def _write_outputs(
    data_root: Path,
    document: Path,
    markdown: str,
    assets: tuple[Asset, ...],
    archive: Path,
    source_bytes: bytes,
) -> None:
    """Write one file's outputs in commit order: assets, document, archive last.

    Output directories are created on demand (Req 2.8). The archive copy is
    written **last** (Req 3.1, 4.2): its presence is the processed-marker, so a
    crash before it leaves no archive and the file is reprocessed idempotently. An
    existing archive is never rewritten (Req 3.5) -- only reachable under
    ``force``, where the immutable source copy must be preserved.
    """
    # (a) assets, each doc-relative under ``workouts/``.
    for asset in assets:
        asset_path = data_root / WORKOUTS_DIR / asset.rel_path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(asset.content, encoding="utf-8")
    # (b) the document.
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(markdown, encoding="utf-8")
    # (c) the archived source, LAST and write-once (presence = committed).
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(source_bytes)


def _newer_version_detail(existing_version: int) -> str:
    """The warning detail for a document written by a newer fitdocs (Req 5.5).

    Names both the recorded version and the installed one so the message is
    actionable without consulting anything else, and states the outcome
    (nothing written) in wording that holds for both callers: in ``sync`` the
    source stays unarchived (Req 5.8); in ``regen`` the archive this run reads
    from is simply left untouched, since neither branch of the gate writes
    to it.
    """
    return (
        f"records document-format version {existing_version}, newer than "
        f"the installed fitdocs (version {DOC_VERSION}); left unchanged and "
        "not rewritten"
    )


def _unmanaged_keys_detail(keys: tuple[str, ...]) -> str:
    """The warning detail naming keys a rewrite would drop (Req 6.3).

    ``keys`` arrives already sorted and deduplicated by
    :func:`fitdocs.contract.unmanaged_keys`; this only names them in a
    human-readable sentence stating the outcome (the rewrite proceeds and the
    keys are dropped) so the message is actionable without consulting
    anything else.
    """
    noun = "key" if len(keys) == 1 else "keys"
    return (
        f"carries frontmatter {noun} fitdocs does not manage, dropped by this "
        f"rewrite: {', '.join(keys)}"
    )


def _invalid_effort_tag_detail(tag: InvalidEffortTag) -> str:
    """The warning detail naming a malformed effort tag (Req 1.4, 3.4, 3.6).

    The design's fixed prefix, stating the outcome up front (preserved
    unchanged, not in effect, not a failure) followed by
    :meth:`fitdocs.contract.InvalidEffortTag.describe` -- the one renderer
    every consumer of a malformed tag is designed to share (Req 5.6, design:
    "SyncEngine"), so this warning and the ``fitdocs check`` inspection's
    :attr:`~fitdocs.audit.FindingKind.INVALID_EFFORT_TAG` finding for the
    identical defect describe it identically.
    """
    return (
        "carries an effort tag fitdocs cannot read -- preserved unchanged, "
        "not in effect until corrected: " + tag.describe()
    )


def _reason(exc: Exception) -> str:
    """A concise, non-empty failure reason naming the error kind and its message."""
    message = str(exc).strip()
    kind = type(exc).__name__
    return f"{kind}: {message}" if message else kind


def _discover_documents(data_root: Path) -> list[tuple[Path, tuple[str, ...]]]:
    """Every fitdocs workout document under ``workouts/`` with its ``sources`` history.

    Returns ``(path, sources)`` pairs sorted by path for a deterministic
    regeneration order (Req 4.1). Uses the same read-only frontmatter scan as
    :func:`find_document`: non-fitdocs pages and garbled ``.md`` files (missing or
    unparseable frontmatter, not ``type: workout``) are skipped safely, and a
    missing ``workouts/`` directory yields ``[]``.

    A ``workouts/*.md`` symlink is never followed (wiki-contract Req 7.5, 7.6):
    :func:`~fitdocs.docio.read_frontmatter` refuses it, so ``frontmatter`` is
    ``None`` for that path here and it is skipped exactly like any other
    unreadable file. Its sha history can therefore never be read, so its
    archived source (if any) is invisible to the "which archives are
    referenced" accounting in :func:`regen` and is rendered fresh as a
    *second*, separate document by :func:`_unreferenced_archives` unless
    nothing else references it either. This is not left silent (task 7.2, F2)
    -- but the warning for it is not this function's concern: see
    :func:`_scan_symlinked_documents`, which :func:`regen` runs once per run
    instead of relying on this per-document scan to happen to encounter it.
    """
    workouts_dir = data_root / WORKOUTS_DIR
    if not workouts_dir.is_dir():
        return []
    documents: list[tuple[Path, tuple[str, ...]]] = []
    for path in sorted(workouts_dir.glob("*.md")):
        frontmatter = _read_frontmatter(path)
        if frontmatter is None or not is_workout_document(frontmatter):
            continue
        documents.append((path, source_refs(frontmatter)))
    return documents


def _last_source_archive(data_root: Path, sources: tuple[str, ...]) -> Path | None:
    """The archived file for a document's current (last) source, or ``None``.

    Resolves the last ``sources`` entry -- the current render source -- back to
    ``fit-archive/<sha>.fit`` through :func:`fitdocs.contract.sha_of_ref`, the
    exact inverse of :func:`fitdocs.layout.source_ref`. Returns ``None`` when the
    history is empty, its last entry is not a resolvable archive ref, or the
    referenced archive file is absent: in each case the document cannot be
    regenerated from the archive and the caller records a failure.

    The contract's resolver validates the embedded sha rather than trusting it, so
    a hand-edited or traversal-shaped entry (``fit-archive/../secrets.fit``) is
    unresolvable here instead of becoming a path component joined onto the data
    root (Req 1.3). Such a document is reported as having no regenerable source --
    the same graceful degradation any other malformed history gets.
    """
    if not sources:
        return None
    sha = sha_of_ref(sources[-1])
    if sha is None:
        return None
    archive = archive_path(data_root, sha)
    return archive if archive.is_file() else None


def _unreferenced_archives(data_root: Path, referenced: set[str]) -> list[Path]:
    """Archived ``.fit`` files whose sha no document references (Req 4.4).

    Returns the archive paths whose sha is absent from ``referenced`` -- sources
    whose document was deleted -- sorted for a deterministic order. A missing
    ``fit-archive/`` directory yields ``[]``.
    """
    archive_dir = data_root / ARCHIVE_DIR
    if not archive_dir.is_dir():
        return []
    return [
        path
        for path in sorted(archive_dir.glob("*.fit"))
        if path.stem not in referenced
    ]


_SYMLINK_CONSEQUENCE: Final[str] = (
    "sync/regen cannot read through the symlink, so if this is a fitdocs "
    "workout document its uuid and sources history are invisible: a "
    "re-export of that activity, or a regeneration of the archive it was "
    "rendered from, is written as a new, separate document instead of "
    "updating this one"
)
"""The one consequence of the symlink refusal specific to a *writing* pass --
the read-only audit has no matching/regeneration story to warn about, so this
clause is not part of :mod:`fitdocs.audit`'s wording. Not silent by design
(wiki-contract task 7.2, F2): without it, a symlinked document's refusal would
be reported with no hint that a duplicate document is the likely next thing
the user sees."""


def _symlink_warning(data_root: Path, path: Path) -> DocWarning:
    """The :class:`DocWarning` for a ``workouts/*.md`` symlink skipped by
    discovery (wiki-contract Req 7.5, 7.6, task 7.2 F2).

    Reuses :mod:`fitdocs.docio`'s exact wording for the refusal itself
    (:data:`~fitdocs.docio.SYMLINK_DETAIL`,
    :data:`~fitdocs.docio.REMEDY_REPLACE_SYMLINK` -- the same names
    :mod:`fitdocs.audit` also imports) so ``fitdocs check``, ``sync``, and
    ``regen`` describe the same symlinked path with the same sentence, then
    appends :data:`_SYMLINK_CONSEQUENCE` -- the one thing a writing pass needs
    to say that a read-only audit does not.
    """
    doc_ref = path.relative_to(data_root).as_posix()
    detail = f"{_SYMLINK_DETAIL}; {_REMEDY_REPLACE_SYMLINK}; {_SYMLINK_CONSEQUENCE}"
    return DocWarning(doc=doc_ref, detail=detail)
