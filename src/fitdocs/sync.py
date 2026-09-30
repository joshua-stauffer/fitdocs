"""The sync engine: the only writer, and the activity-identity resolver.

This module is the home of fitdocs's per-file pipeline (design: SyncEngine,
``src/fitdocs/sync.py``) and of the document-lookup surface that pipeline builds
on. :func:`sync` walks a source directory and plans the run as a whole: every
discovered ``.fit`` file is hashed, deduplicated and parsed (run preparation),
the workout pages are scanned once, the planner assigns each file to an existing
page, a new page, or a *hold* as a function of the *set* of files, and one page
task per target then renders, merges, writes and archives -- with per-file
failures isolated so one bad file never aborts the batch (Req 1-4;
activity-identity Req 4). :func:`regen` rebuilds documents from the data
root alone -- re-rendering each page from its base archived source through the
per-page task (:func:`_process_isolated`), then planning every archived
file no page lists against the rebuilt pages exactly as :func:`sync` plans its
run (Req 4.3, 4.4; activity-identity Req 4.10, 7.2, 7.3). :func:`drain` is the
inbox spec's third entry point
(design: DrainOrchestration): it composes the standing-inbox policy
(:mod:`fitdocs.inbox` selection and stability) around the same planned run --
candidates are selected, settled and read once each (a read failure defers
rather than fails or quarantines the candidate, inbox Req 4.2); a candidate
whose content hash is already in the quarantine record, and retry is not
requested, is reported in its own ``quarantined`` channel and never reaches the
planner (inbox Req 5.2); every other candidate is prepared from the bytes of
that probe read and planned together, with the candidate's inbox-relative path
as its report label (inbox Req 2.3). The composed :class:`DrainReport` wraps an
ordinary :class:`SyncReport` alongside the inbox-only ``deferred`` and
``quarantined`` channels. Processed-file disposition moves every candidate
whose content is archived, a held one included.

The *document lookup* (:func:`find_document`) is the read-only step that decides
whether an incoming ``.fit`` file updates an existing document or seeds a fresh
one (Req 3.6).

Write ordering is load-bearing (Req 3.1, 4.2, activity-identity 6.7). Per file the
engine writes the new assets first, then -- only when the page is renamed --
removes the previous render's stale assets and moves the document with a
same-directory ``os.replace``, then writes the document, then the archived
source copy **last**: the archive's presence is the processed-marker, so a crash
before it leaves no archive and the file is reprocessed idempotently on the next
run, and no instant leaves the page at two paths (each step is one
``_write_outputs`` helper). After every file of a run, a settle pass moves each
page written under a collision suffix to its unsuffixed name once that name is
free (Req 6.6); it also takes every page an interrupted settle stranded, found
by one ``workouts/*.md`` scan (a page still at ``<U>-<uid8>.md`` with
``<U>.md`` free, or at ``<U>.md`` whose generated content, outside its regions,
still links charts named for the suffix), because the next run skips every
archived file (Req 6.7). Settling a stranded page is opportunistic: when it
cannot complete it is left for a later run to finish and nothing is reported
for it. Any
ordinary rewrite of a page that sits under its own suffix with the unsuffixed
name free finishes that rename itself. The source directory is opened
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

* ``uuid`` -- the page's session identifier (a canonical UUID string), present
  only when the page's base or one of its extras recorded a ``SESSION UUID``, or
  the page already carried one (a page keeps its UUID when a later base records
  none). It converges every
  re-export of one activity -- same session, different bytes -- onto one
  document.
* ``sources`` -- the list of data-root-relative archive refs of the document's
  files, in ascending rank (the last entry is the base, the file the page is
  rendered from; refs that no longer resolve to an archived file come first).
  It resolves exact re-syncs and documents that carry no session UUID.

**Match precedence (Req 3.6).** ``uuid`` is matched first, then ``sources``;
:func:`sync` then places a file no page lists by the cross-source rule of
:mod:`fitdocs.identity` (a file that could belong to two pages, or that claims a
page another group of the run also claims, is *held*: archived, recorded in
``.fitdocs/held.toml``, warned and skipped, never merged by guesswork).
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
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import tzinfo
from pathlib import Path
from typing import Final, Literal

from fitdocs import (
    Activity,
    AthleteInputs,
    FitDecodeError,
    Modality,
    compute_metrics,
    parse_fit,
)
from fitdocs.contract import (
    DOC_VERSION,
    InvalidEffortTag,
    document_uuid,
    document_version,
    effort_tag,
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
from fitdocs.docmerge import (
    RegionError,
    begin_marker,
    end_marker,
    extract_regions,
    merge_regions,
)
from fitdocs.identity.holds import HeldSource, HoldRecord, load_holds, save_holds
from fitdocs.identity.kinds import source_identity
from fitdocs.identity.matching import session_key
from fitdocs.identity.pages import scan_pages
from fitdocs.identity.planning import (
    Hold,
    PageRecord,
    PageTaskPlan,
    RunFile,
    plan_run,
)
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    PageRoles,
    Precedence,
    SourceMember,
    page_session_uuid,
    rank_members,
    source_member,
)
from fitdocs.inbox import (
    Candidate,
    Disposition,
    InboxNote,
    InboxSettings,
    move_processed,
    select_candidates,
    settle,
)
from fitdocs.layout import (
    ARCHIVE_DIR,
    ASSETS_SUBDIR,
    WORKOUTS_DIR,
    archive_path,
    doc_path,
    doc_stem,
    held_path,
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
    ``sources`` list as a tuple in the order recorded (empty when the key is
    absent), which the caller ranks together with the newly archived ref when
    updating in place.
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
    (:func:`_resolvable_source_archive`), not the matching one.
    """
    # One scan, then the index's exact match: the session UUID first, else the
    # sources history. ``activity_uid`` (a session UUID or a file sha) goes to
    # the UUID side unchanged, so a hand-edited ``uuid: <sha>`` keeps matching.
    found = scan_pages(data_root).exact_match(activity_uid, source_ref)
    if found is None:
        return None
    return DocumentMatch(path=Path(found.path), sources=found.sources)


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

    ``skipped`` is a **shared presentation bucket with three unrelated causes**:
    the source's bytes were already archived and ``force`` is off, or its bytes
    appeared earlier in the run (Req 3.2, 3.3) -- finished work; the matched
    document records a *newer* document-format version and was left untouched
    (Req 5.5, 5.8), which wrote nothing and archived nothing and depends on the
    source staying where it is to be retried next run; or the file was *held*
    because its page is ambiguous (activity-identity Req 4.5-4.7, 7.5), which is
    archived and recorded but written to no page. **It is not a completion
    signal** (Req 5.9): a held file is archived (so a later run skips it) yet
    belongs to no page, and is never a failure.

    The authoritative discriminator for a fully-processed source is its presence
    in ``fit-archive/`` -- never this label. A disposition, cleanup, or archival
    policy that relocated a source because it appeared here would orphan a
    version-gated source and permanently defeat that retry. See the module
    docstring's version-gate section.

    ``warnings`` is a **separate, additive channel** for non-fatal, subject-scoped
    conditions. Eight causes emit one today: a map that could not be rendered
    (Req 4.3, 4.4), a foreign ownership declaration that could not be placed
    (Req 3.6), a document left untouched because it records a newer
    document-format version (Req 5.5), a rewritten document that carried
    frontmatter keys fitdocs does not manage and therefore drops (Req 6.3), a
    rewritten document whose effort tag fitdocs cannot read (preserved
    unchanged, not in effect until corrected, Req 1.4, 3.4, 3.6, 4.7), and a
    ``workouts/*.md`` symlink discovery never follows (Req 7.5, 7.6, task
    7.2 F2), a page renamed because its base changed or because a
    collision suffix was settled (activity-identity Req 6.5, 6.6), and a file
    held because the page it belongs to is ambiguous, naming the archived file,
    every page it could belong to and the evidence (activity-identity Req 4.7).
    This is the canonical enumeration every other module points at
    instead of repeating (:class:`DocWarning`, :func:`fitdocs.cli._report`) --
    keep it, and only it, current when a ninth cause is added. A
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
    invalid-effort-tag notice, then the map omission, then the rename notice --
    which is fixed by statement order in ``_page_task``, not by any set or mapping
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
    :func:`find_document` or :func:`~fitdocs.identity.pages.scan_pages` no
    matter which file a given run happens to process
    (:func:`~fitdocs.docio.read_frontmatter`
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
    precedence: Precedence = DEFAULT_PRECEDENCE,
) -> SyncReport:
    r"""Turn every ``.fit`` file under ``source_dir`` into a workout document.

    Discovers ``.fit`` files recursively and case-insensitively in a deterministic
    (sorted) order (Req 1.1) and plans the run as a whole (:func:`_run_planned`).
    The source directory is opened strictly read-only -- nothing under it is
    written, moved, or deleted (Req 1.6). Each file is classified into the returned
    :class:`SyncReport`: *written* (a document produced or updated), *skipped* (its
    bytes are already archived and ``force`` is off, Req 3.2, 3.3, or its bytes
    appeared earlier in this run (even under ``force``); it is held
    because its page is ambiguous; or its page records a newer document-format
    version), or *failed*.

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

    **Planned runs and holds (activity-identity Req 4).** The run's files are
    assigned to pages together, as a function of the *set* of files and the
    existing pages (:func:`_run_planned`), so the tree a run produces does not
    depend on discovery order. A file whose page is ambiguous -- it could belong
    to two pages, or claims a page another group of the run also claims -- is
    *held*: recorded in ``.fitdocs/held.toml`` first, then archived, reported in
    ``skipped`` with a :class:`DocWarning` naming the archive ref, every
    candidate page and the evidence, and never counted as a failure. The hold
    record is read before anything is written; a damaged one raises
    :class:`~fitdocs.identity.holds.HoldRecordError`, uncaught here.
    """
    written: list[str] = []
    skipped: list[str] = []
    failures: list[FileFailure] = []
    warnings: list[DocWarning] = []
    ledger = _RunLedger()
    # The hold record is read before anything is written, so a damaged one
    # raises HoldRecordError with the data root untouched (Req 4.7, 4.10).
    holds = _HoldState(load_holds(data_root))
    refresh_declarations(data_root, warnings)
    warnings.extend(_scan_symlinked_documents(data_root))

    task_renames = _run_planned(
        [_RunItem(str(path), path) for path in _discover_fit_files(source_dir)],
        data_root,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        force=force,
        precedence=precedence,
        holds=holds,
        ledger=ledger,
        written=written,
        skipped=skipped,
        failures=failures,
        warnings=warnings,
    )

    settle_renames = _settle_pass(
        data_root,
        ledger,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        precedence=precedence,
        written=written,
        failures=failures,
        warnings=warnings,
    )
    _finish_holds(data_root, holds, task_renames, settle_renames)

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
    ``written``/``skipped``/``failures`` tuples, except that identical
    undecodable content under a second name, whose first copy was just
    quarantined in this drain, is reported in ``quarantined`` instead of as a
    second failure -- and only its ``failures``
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
    """The sync report over the admitted candidates (see the class docstring
    for the one demotion to ``quarantined``)."""

    deferred: tuple[InboxNote, ...]
    """Candidates left untouched this run: unstable across the settle
    interval, or stable but unreadable (inbox Req 4.2). Retried, unchanged,
    on a later drain."""

    quarantined: tuple[InboxNote, ...]
    """Stable, readable candidates whose content hash is already present in
    the quarantine record, and *not* being retried this drain (inbox Req 5.2);
    these never reach the planner. Also a second candidate with the same
    undecodable bytes as one that failed and was recorded earlier in this
    drain (unless retrying): it does reach the planner and fails there, then
    is demoted from ``sync.failures`` to here after the run, carrying the
    recorded reason.
    Otherwise each entry's ``detail`` is the reason recorded when the file was
    first quarantined. Entries are in candidate order. They are excluded from
    ``sync.written``/``skipped``/``failures`` and never drive the failure exit
    code by themselves (inbox Req 5.3)."""

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
    precedence: Precedence = DEFAULT_PRECEDENCE,
) -> DrainReport:
    r"""Drain the inbox: select, settle, quarantine-partition, then plan and
    apply the admitted ``.fit`` files as one run (design: DrainOrchestration,
    inbox Req 2.1, 2.3, 2.4, 3.5, 4.2, 4.6, 5.1-5.5, 5.7, 7.1, 7.4, 7.6;
    activity-identity Req 4).

    Sequence: the hold record is loaded first, before anything is written, so a
    damaged one raises :class:`~fitdocs.identity.holds.HoldRecordError`
    (uncaught here) with the data root untouched. Then the ownership
    declarations are refreshed once, exactly where and how :func:`sync` does
    (inbox Req 7.6), and :func:`_scan_symlinked_documents` runs once (the
    once-per-run parity :func:`sync` and :func:`regen` share). Then candidates
    are selected (:func:`fitdocs.inbox.select_candidates`) against *settings*,
    so ignored files never reach any channel (inbox Req 3.5); settled as one
    batch (:func:`fitdocs.inbox.settle`), through the injected *sleep* so a
    test spends no wall-clock time; and read once each -- the read doubles as
    a readability probe, so a candidate that observes as stable but cannot be
    read (for example an unmaterialized cloud placeholder) is *deferred* with
    its reason, never failed and never quarantined (inbox Req 4.2).

    **Quarantine partition (inbox Req 5.1-5.5, 5.7).** That same probe read's
    bytes are hashed (sha256, matching the archive's content identity). When
    that hash is already present in *quarantine* and *retry_quarantined* is
    not set, the candidate is *not* handed to the planner at all: it is
    reported once in ``quarantined`` with its recorded reason (inbox Req 5.2)
    and never enters ``sync.written``/``skipped``/``failures``. Every other
    stable, readable candidate -- new content, or a quarantined one being
    retried -- is *admitted*.

    **Planned run (activity-identity Req 4).** The admitted candidates are
    prepared from their probe bytes (the planner does not read them again),
    assigned to pages together as a function of the *set* of candidates and
    the existing pages, and applied one page task or hold task at a time
    (:func:`_run_planned`, the same planner :func:`sync` uses), with the
    candidate's inbox-relative path (``candidate.rel``) as its report label. A
    task re-reads its candidates once to confirm their bytes are the planned
    ones. A candidate whose page is ambiguous is *held*: recorded in
    ``.fitdocs/held.toml``, archived, reported in ``sync.skipped`` with a
    warning, and never a failure. A fresh failure is recorded into the
    quarantine only when :func:`_fresh_failure_is_source_level` -- which
    *re-derives* the fault by re-parsing the probe-read bytes, rather than
    inspecting the exception the run isolated -- says the fault is
    source-level per :func:`is_source_level` (Req 5.1); a fault that is a
    property of the existing document instead -- a damaged preserved region
    being the representative case, and anything the re-derivation does not
    recognize -- is reported as a failure and deliberately left unrecorded
    (Req 5.7), so repairing the document is enough for the next drain to
    succeed. That holds for every member of a group task whose document fails:
    none is quarantined. A held candidate is not a failure and is never
    quarantined. A retried candidate that fails again always has its entry
    updated with the new reason and is reported as a failure (Req 5.5),
    regardless of the re-derived level -- its content was already known-bad;
    one that now succeeds (or is held) has its entry removed. Identical
    undecodable bytes under a second name are reported ``quarantined`` from the
    entry the first copy just earned, not as a second failure (Req 5.2) --
    unless *retry_quarantined* is set, when every such copy is a failure and the
    entry carries the last name; the planner has already parsed and failed the
    copy, and the demotion happens after the run. *force* governs
    archive-skip policy only and never implies retry -- the two are
    independent. Afterwards the settle pass runs and the hold record's
    candidate paths follow the run's renames.

    The composed :class:`DrainReport` wraps the resulting :class:`SyncReport`
    alongside the ``deferred`` and ``quarantined`` channels. Only
    :class:`FileFailure`\ s inside that ``sync`` report drive the failure
    outcome; a drain whose only exceptional entries are deferrals, holds and/or
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
    bypasses the planner's ordinary archived-file skip and is reprocessed from
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
    disposition never reads the candidate again (``shutil.move`` may copy
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
    ledger = _RunLedger()

    # The hold record is read before anything is written, so a damaged one
    # raises HoldRecordError with the data root untouched (Req 4.7, 4.10).
    holds = _HoldState(load_holds(data_root))
    refresh_declarations(data_root, warnings)
    warnings.extend(_scan_symlinked_documents(data_root))

    candidates = select_candidates(inbox, settings)
    settle_result = settle(
        candidates, settle_seconds=settings.settle_seconds, sleep=sleep
    )
    deferred.extend(settle_result.deferred)

    record = quarantine
    record_changed = False

    admitted: list[tuple[Candidate, bytes, str, QuarantineEntry | None]] = []
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
        admitted.append((candidate, data, sha, recorded_entry))

    # The admitted candidates are planned together, from the probe bytes.
    task_renames = _run_planned(
        [_RunItem(c.rel, c.path, data) for c, data, _sha, _entry in admitted],
        data_root,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        force=force,
        precedence=precedence,
        holds=holds,
        ledger=ledger,
        written=written,
        skipped=skipped,
        failures=failures,
        warnings=warnings,
    )
    failed_reasons = {failure.source: failure.reason for failure in failures}

    demoted: set[str] = set()
    for candidate, data, sha, recorded_entry in admitted:
        reason = failed_reasons.get(candidate.rel)
        earlier = record.get(sha)
        if (
            reason is not None
            and recorded_entry is None
            and earlier is not None
            and not retry_quarantined
        ):
            # Identical undecodable bytes under another name: an earlier
            # candidate of this drain was just recorded, and this one is
            # reported from that entry, not as a second failure (Req 5.2).
            quarantined.append(InboxNote(subject=candidate.rel, detail=earlier.reason))
            demoted.add(candidate.rel)
            continue
        failed_this_candidate = reason is not None
        if reason is not None:
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
            # (Req 5.7). A held candidate is not a failure and never
            # reaches this branch.
        elif recorded_entry is not None:
            # A retried quarantined file succeeded: clear its entry (Req 5.5).
            record = record.without(sha)
            record_changed = True

        # Disposition (inbox Req 6.2, 6.4, 6.5): a candidate that did not
        # fail is disposed of iff its content is now present in
        # `fit-archive/` -- the positive, filesystem-checked gate, never the
        # `skipped` label. A version-gated skip (wiki-contract's newer-
        # doc_version gate) deliberately archives nothing, so it fails this
        # check and stays in the inbox for the next drain to re-select. A
        # held candidate is archived, so it is moved like any other.
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

    failures[:] = [f for f in failures if f.source not in demoted]
    order = {c.rel: i for i, c in enumerate(settle_result.stable)}
    quarantined.sort(key=lambda note: order[note.subject])
    settle_renames = _settle_pass(
        data_root,
        ledger,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        precedence=precedence,
        written=written,
        failures=failures,
        warnings=warnings,
    )
    _finish_holds(data_root, holds, task_renames, settle_renames)

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
    """Whether the failure :func:`drain` just saw for *data* is source-level
    (:func:`is_source_level`), re-derived by parsing the drain's probe-read
    bytes again.

    Called only by :func:`drain`, for a candidate that failed and is not a
    retried quarantine entry (regen does not use it). The planned run reports
    only a :class:`FileFailure`, never the exception, so this attempts the pure,
    side-effect-free first step (:func:`~fitdocs.parse_fit`) on *data*: a fault
    in decoding these exact bytes reproduces deterministically, and any later
    fault (a region conflict merging into an existing page, a changed-during-
    the-run file, a failed hold save, a write error) leaves the parse
    succeeding, which is exactly the "not source-level" answer (Req 5.7). The
    bytes are the probe read's, so a candidate that vanishes after the probe
    can never be classified source-level by an ``OSError`` here.
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
    precedence: Precedence = DEFAULT_PRECEDENCE,
) -> SyncReport:
    r"""Rebuild every workout document from the data root alone (Req 4.3, 4.4).

    Regeneration takes no source directory: it reconstructs documents from the
    archived ``.fit`` sources under ``fit-archive/`` plus the optional athlete
    inputs, so a data root with the original exports long deleted still rebuilds
    completely (Req 4.4). It runs in two parts: the first rebuilds each page
    through the per-page task (:func:`_process_isolated`), the second plans
    every archived file no page lists through the same planner :func:`sync`
    uses:

    * **Every document re-renders from its base.** For each ``workouts/*.md``
      workout document, every file its frontmatter ``sources`` history lists is
      resolved to its archived file, parsed and ranked with the given
      ``precedence``, and the page is re-rendered from the highest-ranked one --
      its base -- with ``sources`` rewritten in ascending rank (activity-identity
      Req 5.1, 5.2, 7.2, 7.3). Because the page task's match is the scan
      record of this same document, ``merge_regions`` carries its
      ``notes``/``workout``/``load`` regions over verbatim while the
      generated content is refreshed (Req 4.3, 10.2). A
      document whose history is empty or none of whose listed files is in the
      archive cannot be regenerated -- it becomes a :class:`FileFailure` and is
      left untouched, the batch continuing.
    * **Archived sources no page lists are planned.** After the pages are
      rebuilt the page index is scanned again; every ``fit-archive/<sha>.fit``
      whose sha no page's ``sources`` lists (its page was deleted -- documents
      are derived artifacts -- or the file was held) is parsed and planned
      against the rebuilt pages by :func:`_run_planned`, the planner
      :func:`sync` uses, labelled with its archive ref. A file joins the page
      it belongs to, seeds a new page, or is *held* when its page is ambiguous
      (activity-identity Req 4.10, Req 4.4 of the original spec). The planned
      tasks and holds write no archive file: the bytes are already archived.
    * **The hold record is this run's holds.** The old record is never read, so
      a damaged one is rebuilt rather than raised and an entry whose archived
      file no longer exists is not re-held. An existing record is replaced by
      the run's holds even when that is none (an empty record: no entry
      outlives its cause); when the run holds nothing and no record exists,
      none is created, so ``.fitdocs/`` never appears in a tree that never held
      anything. Held candidates are rewritten through the run's renames, as in
      :func:`sync`.

    ``force`` is implied for every item this discovery produces, so an
    already-archived source is never skipped on that basis alone; the
    remaining skips are the document-format version gate below, a file the
    second part holds, and bytes repeated within the run. The immutable
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
    not a second copy of either. The settle pass runs last, as in :func:`sync`.
    """
    written: list[str] = []
    skipped: list[str] = []
    failures: list[FileFailure] = []
    warnings: list[DocWarning] = []
    ledger = _RunLedger()
    refresh_declarations(data_root, warnings)
    warnings.extend(_scan_symlinked_documents(data_root))

    # Re-render each page from the files it lists (roles rebuilt with the
    # current precedence), one isolated task per scan record. The record itself
    # is the match: a page is never looked up again by its session UUID, so two
    # pages that record the same UUID are each rebuilt from their own list and
    # no file moves between them (Req 4.9, 7.2).
    for record in scan_pages(data_root).records:
        doc_ref = Path(record.path).relative_to(data_root).as_posix()
        if _resolvable_source_archive(data_root, record.sources) is None:
            # No archived source to rebuild from: an empty history, or every
            # listed file unresolvable or missing from the archive. Fail this
            # document (left untouched) and keep going (an archive it lists, if
            # any, is a page-listed file and is not planned below).
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
            DocumentMatch(path=Path(record.path), sources=record.sources),
            data_root,
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            precedence=precedence,
            source_label=doc_ref,
            written=written,
            skipped=skipped,
            failures=failures,
            warnings=warnings,
            ledger=ledger,
        )

    # The pages are rebuilt: rescan, so "listed by no page" is judged against
    # the pages as they now are (renames included), then plan every archived
    # file no page lists exactly as a sync run would. The hold record is *this
    # run's* holds and nothing else: the old record is never read, so a damaged
    # one cannot block regeneration and a stale entry cannot survive it.
    listed = {
        sha
        for record in scan_pages(data_root).records
        for sha in map(sha_of_ref, record.sources)
        if sha is not None
    }
    holds = _HoldState(HoldRecord(entries=()))
    task_renames = _run_planned(
        [
            _RunItem(source_ref(archive.stem), archive)
            for archive in _unreferenced_archives(data_root, listed)
        ],
        data_root,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        force=True,
        precedence=precedence,
        holds=holds,
        ledger=ledger,
        written=written,
        skipped=skipped,
        failures=failures,
        warnings=warnings,
        write_archive=False,
    )

    settle_renames = _settle_pass(
        data_root,
        ledger,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        precedence=precedence,
        written=written,
        failures=failures,
        warnings=warnings,
    )
    _finish_holds(data_root, holds, task_renames, settle_renames)
    if holds.record.entries or held_path(data_root).exists():
        # An existing record is replaced by this run's holds even when that is
        # none (an empty record, so no entry outlives its cause); a tree that
        # never held anything never gains ``.fitdocs/``.
        save_holds(data_root, holds.record)

    return SyncReport(
        written=tuple(written),
        skipped=tuple(skipped),
        failures=tuple(failures),
        warnings=tuple(warnings),
    )


def _process_isolated(
    match: DocumentMatch,
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    precedence: Precedence,
    source_label: str,
    written: list[str],
    skipped: list[str],
    failures: list[FileFailure],
    warnings: list[DocWarning],
    ledger: _RunLedger,
) -> None:
    """Rebuild one page from its listed files, isolating any failure (Req 1.3).

    Used by :func:`regen` for the per-page rebuild (:func:`sync`, :func:`drain`
    and regeneration's unreferenced files are planned through
    :func:`_run_planned` instead): a page task with the scan record as its match
    and no incoming file. Classifies the page into ``written`` (a document
    produced or updated), ``skipped`` (version-gated because the matched
    document is newer, Req 5.5), or ``failures``. Expected
    per-file errors -- an undecodable source (Req 1.2, 1.3) or a damaged region in
    the existing document (Req 10.3) -- and any unexpected per-file exception all
    become a :class:`FileFailure`; the batch never aborts. (``BaseException`` --
    ``KeyboardInterrupt``, ``SystemExit`` -- deliberately propagates.)

    Zero or more :class:`DocWarning`\\ s are something ``_page_task``
    *returns*, so they can ride with either non-failing branch: a version-gate
    skip carries exactly one (Req 5.5) alongside its ``None`` outcome; a
    written file may carry a map omission (Req 4.3), an
    unmanaged-frontmatter-key notice (Req 6.3), an invalid-effort-tag notice
    (Req 1.4), a rename notice (activity-identity Req 6.5), any combination,
    or none -- most
    written pages carry none. The invariant is
    one-directional: a *raising* file can never carry one, because when
    ``_page_task`` raises (a :class:`FileFailure`) it returns nothing at all
    (Req 4.4). A ``workouts/*.md`` symlink is never among these -- it is not a
    per-file condition, so it never rides with any single file's outcome; see
    :func:`_scan_symlinked_documents`, which the caller (:func:`sync` or
    :func:`regen`) runs once per run instead.
    """
    try:
        result = _page_task(
            data_root,
            match=match,
            news=(),
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            precedence=precedence,
            settling=False,
            quiet=False,
            expected_stem=None,
        )
    except (FitDecodeError, RegionError) as exc:
        failures.append(FileFailure(source=source_label, reason=_reason(exc)))
    except Exception as exc:
        failures.append(FileFailure(source=source_label, reason=_reason(exc)))
    else:
        if result.doc_ref is None:
            skipped.append(source_label)
        else:
            written.append(result.doc_ref)
        _note_task_result(result, ledger)
        file_warnings = result.warnings
        # Zero or more warnings can ride with either non-failing outcome -- a
        # written file may carry a map omission, an unmanaged-key notice, both,
        # or neither; a version-gated skip carries exactly one. Only the
        # converse is guaranteed: a raising file never has any.
        warnings.extend(file_warnings)


def _note_task_result(result: _TaskResult, ledger: _RunLedger) -> None:
    """Fold one task's rename facts into the run's settle ledger (Req 6.6).

    A moved page no longer sits at any path the ledger recorded for it; a page
    now under a collision suffix is a settle candidate.
    """
    if result.renamed_from is not None:
        ledger.settle[:] = [
            entry for entry in ledger.settle if entry.path != result.renamed_from
        ]
    if result.settle_entry is not None:
        ledger.settle.append(result.settle_entry)


@dataclass(frozen=True)
class _RunItem:
    """One file of a planned run: the label its report entries use, and where it is."""

    label: str
    path: Path
    data: bytes | None = None
    """Bytes the caller already read (the drain's probe read); preparation uses
    them instead of reading ``path`` again. ``None`` means read ``path``."""


@dataclass(frozen=True)
class _Prepared:
    """A run file after preparation: hashed and parsed once, activity not kept."""

    position: int
    item: _RunItem
    sha: str
    run_file: RunFile


@dataclass(frozen=True)
class _Outcome:
    """One file's place in the report: ``value`` is a page ref or a reason."""

    kind: Literal["written", "skipped", "failed"]
    value: str = ""


@dataclass
class _HoldState:
    """The hold record as the run evolves it (saved only when it changes)."""

    record: HoldRecord


def _run_planned(
    items: Sequence[_RunItem],
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    force: bool,
    precedence: Precedence,
    holds: _HoldState,
    ledger: _RunLedger,
    written: list[str],
    skipped: list[str],
    failures: list[FileFailure],
    warnings: list[DocWarning],
    write_archive: bool = True,
) -> dict[str, str]:
    """Plan and apply one run's files (activity-identity Req 4, 7.1, 7.5).

    Preparation reads (or takes the caller's bytes), hashes and parses each item
    in discovery order (a file
    already archived, or whose bytes appeared earlier in the run, is skipped
    without a parse; a read or decode failure is that file's failure); the page
    index is scanned once; :func:`~fitdocs.identity.planning.plan_run` assigns
    every file to a page, a new page or a hold as a function of the *set* of
    files; page tasks and hold tasks then run in first-member order. Report
    entries are appended in discovery order, warnings in task order. Returns the
    renames the tasks made (previous data-root-relative path to new path).

    ``write_archive=False`` (regeneration, whose files are read *from* the
    archive) applies the page tasks and holds without asking for any archive
    write; a hold is still recorded before it is reported.
    """
    outcomes: list[_Outcome | None] = [None] * len(items)
    duplicate_of: dict[int, int] = {}
    seen: dict[str, int] = {}
    prepared: dict[str, _Prepared] = {}
    run_files: list[RunFile] = []
    for position, item in enumerate(items):
        try:
            data = item.data if item.data is not None else item.path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if archive_path(data_root, sha).exists() and not force:
                outcomes[position] = _Outcome("skipped")
                continue
            if sha in seen:
                duplicate_of[position] = seen[sha]
                continue
            activity = parse_fit(data)
        except Exception as exc:
            outcomes[position] = _Outcome("failed", _reason(exc))
            continue
        seen[sha] = position
        run_file = RunFile(
            id=item.label,
            ref=source_ref(sha),
            session_uuid=source_identity(activity).session_uuid,
            key=session_key(activity),
        )
        prepared[item.label] = _Prepared(position, item, sha, run_file)
        run_files.append(run_file)

    renames: dict[str, str] = {}
    if run_files:
        index = scan_pages(data_root)
        plan = plan_run(run_files, index)
        records = {record.path: record for record in index.records}
        work: list[tuple[int, PageTaskPlan | str]] = [
            (prepared[task.members[0]].position, task) for task in plan.tasks
        ]
        work.extend((prepared[label].position, label) for label in plan.holds)
        work.sort(key=lambda entry: entry[0])
        for _position, unit in work:
            if isinstance(unit, str):
                decision = plan.decisions[unit]
                assert isinstance(decision, Hold)
                _hold_task(
                    prepared[unit],
                    decision,
                    data_root,
                    holds=holds,
                    outcomes=outcomes,
                    warnings=warnings,
                    write_archive=write_archive,
                )
                continue
            page = records[unit.page] if unit.page is not None else None
            _group_task(
                [prepared[label] for label in unit.members],
                page,
                data_root,
                athlete=athlete,
                tz=tz,
                tiles=tiles,
                precedence=precedence,
                ledger=ledger,
                outcomes=outcomes,
                warnings=warnings,
                renames=renames,
                write_archive=write_archive,
            )

    for position, primary in duplicate_of.items():
        first = outcomes[primary]
        outcomes[position] = (
            first
            if first is not None and first.kind == "failed"
            else _Outcome("skipped")
        )
    for item, outcome in zip(items, outcomes, strict=True):
        assert outcome is not None
        if outcome.kind == "written":
            written.append(outcome.value)
        elif outcome.kind == "skipped":
            skipped.append(item.label)
        else:
            failures.append(FileFailure(source=item.label, reason=outcome.value))
    return renames


def _reload(member: _Prepared) -> tuple[bytes, str]:
    """Re-read a planned file; its bytes must still be the ones that were planned.

    Raises when they changed during the run (or cannot be read); the caller
    fails that member alone.
    """
    data = member.item.path.read_bytes()
    if hashlib.sha256(data).hexdigest() != member.sha:
        raise _ChangedDuringRun(
            "the file changed during the run (its bytes no longer match the "
            "ones that were planned); it was not processed"
        )
    return data, member.sha


class _ChangedDuringRun(Exception):
    """A planned file's bytes differ from what preparation hashed."""


def _group_task(
    members: list[_Prepared],
    page: PageRecord | None,
    data_root: Path,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    precedence: Precedence,
    ledger: _RunLedger,
    outcomes: list[_Outcome | None],
    warnings: list[DocWarning],
    renames: dict[str, str],
    write_archive: bool = True,
) -> None:
    """One page task for the files the plan gave one page or one new page.

    Each member is re-read and parsed here; a member whose bytes changed is
    failed alone and the others proceed. An exception in the task fails every
    remaining member with the same reason (Req 1.3).
    """
    news: list[_NewMember] = []
    for member in members:
        try:
            data, sha = _reload(member)
            activity = parse_fit(data)
        except Exception as exc:
            outcomes[member.position] = _Outcome("failed", _reason(exc))
            continue
        news.append(
            _NewMember(
                ref=member.run_file.ref,
                sha=sha,
                activity=activity,
                data=data,
                archive=archive_path(data_root, sha) if write_archive else None,
            )
        )
    if not news:
        return
    live = [m for m in members if outcomes[m.position] is None]
    match = (
        DocumentMatch(path=Path(page.path), sources=page.sources)
        if page is not None
        else None
    )
    try:
        result = _page_task(
            data_root,
            match=match,
            news=tuple(news),
            athlete=athlete,
            tz=tz,
            tiles=tiles,
            precedence=precedence,
            settling=False,
            quiet=False,
            expected_stem=None,
        )
    except Exception as exc:
        for member in live:
            outcomes[member.position] = _Outcome("failed", _reason(exc))
        return
    outcome = (
        _Outcome("skipped")
        if result.doc_ref is None
        else _Outcome("written", result.doc_ref)
    )
    for member in live:
        outcomes[member.position] = outcome
    _note_task_result(result, ledger)
    if result.renamed_from is not None and result.doc_ref is not None:
        renames[result.renamed_from.relative_to(data_root).as_posix()] = result.doc_ref
    warnings.extend(result.warnings)


def _hold_task(
    member: _Prepared,
    hold: Hold,
    data_root: Path,
    *,
    holds: _HoldState,
    outcomes: list[_Outcome | None],
    warnings: list[DocWarning],
    write_archive: bool = True,
) -> None:
    """Record, then archive, a file whose page is ambiguous (Req 4.7, 7.1, 7.5).

    The record is saved **before** the archive write: the archive is the
    processed-marker, so a file archived but never recorded would be skipped by
    every later run with nothing naming it. When the save fails the file is not
    archived, is reported as a failure, and the next run plans and holds it
    again. A held file is ``skipped``, never a failure.

    With ``write_archive=False`` (regeneration) the record is still saved but no
    archive write follows: the file was read from the archive.
    """
    try:
        data, sha = _reload(member)
        candidates = tuple(
            Path(path).relative_to(data_root).as_posix() for path in hold.candidates
        )
        entry = HeldSource(
            sha256=sha,
            name=member.item.label,
            candidates=candidates,
            evidence=tuple(str(evidence) for evidence in hold.evidence),
        )
        if holds.record.get(sha) != entry:
            updated = holds.record.with_entry(entry)
            save_holds(data_root, updated)
            holds.record = updated
        if write_archive:
            _write_archive(archive_path(data_root, sha), data)
    except Exception as exc:
        outcomes[member.position] = _Outcome("failed", _reason(exc))
        return
    outcomes[member.position] = _Outcome("skipped")
    warnings.append(DocWarning(doc=source_ref(sha), detail=_held_detail(entry)))


def _held_detail(entry: HeldSource) -> str:
    """The warning for a held file: every candidate page and the evidence."""
    return (
        f"held, not merged: could be the same session as "
        f"{', '.join(entry.candidates)} (evidence: {', '.join(entry.evidence)}); "
        "the file was archived and recorded in .fitdocs/held.toml, and no page "
        "was written or changed; `fitdocs regen` re-evaluates it"
    )


def _finish_holds(
    data_root: Path,
    holds: _HoldState,
    *renames: Mapping[str, str],
) -> None:
    """Rewrite held candidates through the run's renames (write-if-different).

    Each rename map is applied once, in order, so a page moved to a suffixed
    name and then settled reads as its final path. Saves only when an entry
    changed: a run with nothing held never creates ``.fitdocs/``.
    """

    def follow(path: str) -> str:
        for mapping in renames:
            path = mapping.get(path, path)
        return path

    record = holds.record
    changed = False
    for entry in record.entries:
        moved = tuple(follow(path) for path in entry.candidates)
        if moved != entry.candidates:
            record = record.with_entry(replace(entry, candidates=moved))
            changed = True
    if changed:
        save_holds(data_root, record)
        holds.record = record


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


@dataclass(frozen=True)
class _NewMember:
    """The incoming file of a page task: parsed once, archived last."""

    ref: str
    sha: str
    activity: Activity
    data: bytes
    archive: Path | None
    """Where the file is archived last; ``None`` when its bytes already are
    (regeneration re-plans files read *from* the archive and writes none)."""


@dataclass(frozen=True)
class _SettleEntry:
    """A page to settle onto its unsuffixed name (Req 6.6, 6.7).

    ``path`` is where it sits; ``unsuffixed`` is the stem it would have had if
    no other page had held the name. ``opportunistic`` marks a page found by the
    scan of :func:`_stranded_pages` rather than written by this run: settling it
    is best effort and reports nothing when it cannot complete.
    """

    path: Path
    unsuffixed: str
    opportunistic: bool = False


@dataclass(frozen=True)
class _TaskResult:
    """What one page task reports: the outcome, warnings, and rename facts.

    ``doc_ref`` is ``None`` for a version-gated skip. ``renamed_from`` is the
    page's previous path when the task moved it; ``settle_entry`` is set when
    the page now sits under a collision suffix.
    """

    doc_ref: str | None
    warnings: tuple[DocWarning, ...]
    renamed_from: Path | None = None
    settle_entry: _SettleEntry | None = None


@dataclass
class _RunLedger:
    """The settle candidates one run accumulates (sync, drain, regen)."""

    settle: list[_SettleEntry] = field(default_factory=list)


_ASSET_LINK_RE: Final[re.Pattern[str]] = re.compile(
    r"!\[[^\]\n]*\]\((?P<ref>assets/(?P<name>[^/()\s]+\.svg))\)"
)


def _asset_names(text: str) -> set[str]:
    """Single-component ``assets/<name>.svg`` image links in ``text`` (Req 6.4)."""
    return {match.group("name") for match in _ASSET_LINK_RE.finditer(text)}


def _split_regions(text: str) -> tuple[str, list[str]]:
    """``text`` without its regions, and each region's content.

    Raises :class:`RegionError` when the markers are damaged.
    """
    outside = text
    inside: list[str] = []
    for region_id, content in extract_regions(text).items():
        inside.append(content)
        outside = re.sub(
            re.escape(begin_marker(region_id))
            + ".*?"
            + re.escape(end_marker(region_id)),
            "",
            outside,
            flags=re.DOTALL,
        )
    return outside, inside


def _stale_assets(existing_text: str, new_assets: tuple[Asset, ...]) -> tuple[str, ...]:
    """The chart assets a rename leaves behind (Req 6.4), sorted by name.

    Every single-component ``assets/<name>.svg`` image link in the existing
    page *outside* its regions -- the generated content the new render
    replaces -- that the new render does not write and no region links (a
    region's content survives the rewrite verbatim, so its links must too).
    """
    outside, inside = _split_regions(existing_text)
    written = {Path(asset.rel_path).name for asset in new_assets}
    protected = _asset_names("\n".join(inside))
    return tuple(sorted(_asset_names(outside) - written - protected))


def _rename_detail(old: str, new: str, reason: str) -> str:
    return (
        f"page renamed from {old} to {new} because {reason}; wiki links to the "
        "old name and plan overrides naming the old stem need updating"
    )


def _page_task(
    data_root: Path,
    *,
    match: DocumentMatch | None,
    news: tuple[_NewMember, ...],
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    precedence: Precedence,
    settling: bool,
    quiet: bool,
    expected_stem: str | None,
) -> _TaskResult:
    """Write one page from its members: roles, render, rename, write, archive.

    ``match`` is the page (``None`` for a fresh group) and ``news`` the incoming
    files the plan assigned to it (empty for a settle task, which re-renders a
    page from its listed files alone and moves it to its unsuffixed name, Req
    6.6). The write order is the crash-healing one of Req 6.7 -- see
    :func:`_write_outputs`.

    A settle task (``settling``) is ``quiet`` when it re-renders a page this
    very run just wrote: the unmanaged-key, effort-tag and map-omission notices
    were already given for that write, so only the rename notice is kept. A
    stranded page found by the scan was not written this run and is not quiet.
    A settle task also names the ``expected_stem`` its caller took the page
    for; when the stem the page computes unsuffixed is not that one, the page
    is left exactly where it is and nothing is written.
    """
    # ``pending_warnings`` accumulates whatever the version gate or
    # unmanaged-key check below add for the file that matched -- one list,
    # appended to only, so a later exception in this function (a decode error,
    # a region conflict) discards every one of them together, preserving "a
    # raising file never carries a warning" (Req 4.4). A symlinked
    # workouts/*.md path is never a match candidate for ``find_document``
    # (Req 7.5, 7.6) and is never reported here at all -- see
    # ``_scan_symlinked_documents``, run once per run by the caller.
    pending_warnings: list[DocWarning] = []

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
    existing_frontmatter: Mapping[str, object] | None = None
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
            return _TaskResult(None, tuple(pending_warnings))

        # Unmanaged-frontmatter-key warning (Req 6.3, design: "Unmanaged-key
        # detection on rewrite"). Reuses ``existing_frontmatter`` -- the same
        # parse the version gate above just performed, no second read or
        # parse -- so this never fires for a version-gated document (it drops
        # nothing, since the early return above already left with a `None`
        # write). The rewrite below still proceeds and still drops these keys;
        # this only names them before they go. A settle task re-renders a page
        # this very run just wrote, so it repeats none of these notices.
        if existing_frontmatter is not None and not quiet:
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

    # Roles (activity-identity Req 5.1, 5.2, 7.1): the page's listed files plus
    # the incoming one, each resolved through the archive and parsed once, then
    # ranked. The incoming file is parsed already, so it is never read or parsed
    # again (in regen and under force its bytes are archived, but the parse in
    # hand is the one used); every other listed ref that does not resolve to an
    # archived file is ``unresolved`` and keeps its place at the front of
    # ``sources``.
    existing_refs = match.sources if match is not None else ()
    listed = tuple(dict.fromkeys((*existing_refs, *(n.ref for n in news))))
    incoming = {n.ref: n for n in news}
    parsed: dict[str, Activity] = {}
    resolved: list[SourceMember] = []
    unresolved: list[str] = []
    for ref in listed:
        new = incoming.get(ref)
        if new is not None:
            parsed[ref] = new.activity
            resolved.append(source_member(ref, new.sha, new.activity))
            continue
        member_sha = sha_of_ref(ref)
        member_archive = (
            archive_path(data_root, member_sha) if member_sha is not None else None
        )
        if member_sha is None or member_archive is None or not member_archive.is_file():
            unresolved.append(ref)
            continue
        member_activity = parse_fit(member_archive.read_bytes())
        parsed[ref] = member_activity
        resolved.append(source_member(ref, member_sha, member_activity))
    if not resolved:
        # Only a settle task can reach here (a page task with an incoming file
        # always resolves it): the page's files left the archive mid-run.
        raise FileNotFoundError("no archived source to regenerate from")
    roles = rank_members(resolved, unresolved, precedence)

    # The page's session UUID is the first of base, extras that carries one,
    # else the value the page already records (Req 5.5): a base that carries
    # none never drops the identity its page converged on. The identity keys
    # come from the base's own parse, never from a composed activity (Req 5.4).
    page_uuid = page_session_uuid(
        roles,
        document_uuid(existing_frontmatter)
        if existing_frontmatter is not None
        else None,
    )
    uid = page_uuid if page_uuid is not None else roles.base.sha
    base_activity = parsed[roles.base.ref]
    identity = replace(source_identity(base_activity), session_uuid=page_uuid)

    def taken(candidate: str) -> bool:
        # A stem is taken only by a *different* activity's document; the activity's
        # own matched document never collides with itself (Req 2.6).
        candidate_path = doc_path(data_root, candidate)
        if not candidate_path.exists():
            return False
        return match is None or candidate_path != match.path

    unsuffixed = doc_stem(base_activity, uid, tz, lambda _: False)
    if settling and match is not None and unsuffixed != expected_stem:
        return _TaskResult(match.path.relative_to(data_root).as_posix(), ())
    stem = unsuffixed if settling else doc_stem(base_activity, uid, tz, taken)

    # The write target -- and thus the data-root-relative doc ref used for both the
    # report entry and any map warning -- is known once the stem/match are resolved.
    # An existing page keeps its path (a user's rename, a timezone change) unless
    # its base changed and the base's computed name differs (Req 6.2, 6.3); a
    # settle task moves it to its unsuffixed name (Req 6.6).
    stranded = False
    base_changed = False
    if match is None:
        target = doc_path(data_root, stem)
    else:
        previous_base = match.sources[-1] if match.sources else None
        base_changed = previous_base is not None and previous_base != roles.base.ref
        # A page still under the collision suffix of its own computed stem,
        # whose unsuffixed name is free, is a settle rename an interrupted run
        # left behind; any rewrite finishes it (its own uid names the suffix,
        # so a user's filename never qualifies).
        stranded = stem == unsuffixed and match.path.stem == f"{unsuffixed}-{uid[:8]}"
        if (base_changed or settling or stranded) and doc_path(
            data_root, stem
        ) != match.path:
            target = doc_path(data_root, stem)
        else:
            target = match.path
    renaming = match is not None and target != match.path
    doc_ref = target.relative_to(data_root).as_posix()

    # The activity the page renders (the channel-merge seam) and everything
    # computed from it: metrics and the map plan.
    render_activity = _render_activity(roles, parsed)
    metrics = compute_metrics(render_activity, athlete)

    # Resolve prepared map inputs before the pure render, only for the outdoor
    # (non-strength) views that render a Map section (Req 3.5). Tile unavailability
    # degrades to a warning naming this document; the doc renders mapless (4.3, 4.4).
    map_data: MapData | None = None
    warnings: list[DocWarning] = pending_warnings
    if render_activity.modality is not Modality.STRENGTH:
        plan = plan_map(
            render_activity.samples.latitude_deg, render_activity.samples.longitude_deg
        )
        if plan is not None:
            try:
                resolved_tiles = tiles.resolve(plan.tiles)
            except TileUnavailableError as exc:
                if not quiet:
                    warnings.append(DocWarning(doc=doc_ref, detail=_reason(exc)))
            else:
                map_data = MapData(
                    plan=plan,
                    tiles=tuple((ref, resolved_tiles[ref]) for ref in plan.tiles),
                    attribution=tiles.attribution,
                )

    ctx = DocContext(
        activity=render_activity,
        metrics=metrics,
        athlete=athlete,
        doc_stem=stem,
        source_refs=roles.sources,
        tz=tz,
        map_data=map_data,
        user_frontmatter=carried,
        identity=identity,
    )
    rendered = render_document(ctx)

    # ``existing_text`` is non-None exactly when ``match`` is -- it is read in
    # that branch and nowhere else -- so narrowing on it is equivalent to
    # narrowing on ``match`` and needs no ``assert`` (which ``python -O`` would
    # strip, leaving ``merge_regions`` to be handed ``None``).
    stale: tuple[str, ...] = ()
    if existing_text is not None:
        # An existing document (a rename, timezone change, or re-export) is updated
        # in place: preserved regions carry over verbatim (Req 3.6, 4.3, 10.2). A
        # damaged region raises RegionError here -- before any write (Req 10.3).
        # It was already read once above for the version gate; reusing it here
        # avoids a second disk read and a second parse.
        markdown = merge_regions(rendered.markdown, existing_text)
        if renaming:
            stale = _stale_assets(existing_text, rendered.assets)
    else:
        markdown = rendered.markdown

    moved_from = match.path if renaming and match is not None else None
    _write_outputs(
        data_root,
        target,
        markdown,
        rendered.assets,
        tuple((n.archive, n.data) for n in news if n.archive is not None),
        moved_from=moved_from,
        stale_assets=stale,
    )
    if moved_from is not None:
        old_ref = moved_from.relative_to(data_root).as_posix()
        reason = (
            f"the unsuffixed name {doc_ref} became free"
            if settling or (stranded and not base_changed)
            else "its base file changed"
        )
        warnings.append(
            DocWarning(doc=doc_ref, detail=_rename_detail(old_ref, doc_ref, reason))
        )
    # A page sitting under a collision suffix (its path *is* its computed stem,
    # so a user's own filename is never a candidate) is settled at the end of
    # the run (Req 6.6).
    settle_entry = (
        _SettleEntry(path=target, unsuffixed=unsuffixed)
        if stem != unsuffixed and target == doc_path(data_root, stem)
        else None
    )
    return _TaskResult(
        doc_ref,
        tuple(warnings),
        renamed_from=moved_from,
        settle_entry=settle_entry,
    )


def _stranded_pages(data_root: Path) -> list[_SettleEntry]:
    """Pages an interrupted settle left behind, from one ``workouts/*.md`` scan.

    The next run skips every archived file, so a settle rename that died part
    way cannot be healed from that run's own records (Req 6.7). Two shapes
    qualify, each by the page's own uid (its recorded ``uuid``, else the sha of
    its last listed source), so a user-chosen filename never does:

    * the filename is ``<U>-<uid8>.md`` (``uid8`` the uid's first eight
      characters) and ``workouts/<U>.md`` is free: the page still sits under
      its collision suffix;
    * the filename is ``<U>.md`` but the page's generated content (outside its
      regions -- a note that links a suffixed chart does not count) still
      links ``assets/<U>-<uid8>-...``: the move happened and the content
      write did not, so the page is rewritten in place. This shape needs each
      page's text, read once per run.

    Every entry is ``opportunistic``, and the settle task moves or rewrites a
    candidate only when the stem it computes unsuffixed is ``U``.
    """
    found: list[_SettleEntry] = []
    for record in scan_pages(data_root).records:
        uid = record.session_uuid
        if uid is None and record.sources:
            uid = sha_of_ref(record.sources[-1])
        if uid is None:
            continue
        path = Path(record.path)
        suffix = f"-{uid[:8]}"
        if path.stem.endswith(suffix) and len(path.stem) > len(suffix):
            unsuffixed = path.stem[: -len(suffix)]
            if not doc_path(data_root, unsuffixed).exists():
                found.append(
                    _SettleEntry(path=path, unsuffixed=unsuffixed, opportunistic=True)
                )
            continue
        try:
            outside, _regions = _split_regions(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, RegionError):
            continue
        if f"assets/{path.stem}{suffix}-" in outside:
            found.append(
                _SettleEntry(path=path, unsuffixed=path.stem, opportunistic=True)
            )
    return found


def _settle_pass(
    data_root: Path,
    ledger: _RunLedger,
    *,
    athlete: AthleteInputs | None,
    tz: tzinfo,
    tiles: TileSource,
    precedence: Precedence,
    written: list[str],
    failures: list[FileFailure],
    warnings: list[DocWarning],
) -> dict[str, str]:
    """Move each page under a collision suffix to its unsuffixed name.

    Runs after every file of a run (Req 6.6). The candidates are the pages this
    run recorded under a suffix plus :func:`_stranded_pages`, taken from one
    scan at the start of the pass (not one per iteration). Each move is a page
    task with no incoming file that renders the page again under the unsuffixed
    stem. Report entries naming a moved page's suffixed path are rewritten to
    the path it ended at.

    A page this run wrote is settled under today's reporting: a failure is a
    :class:`FileFailure`, and its notices are not repeated. A stranded page was
    not written this run, so settling it is opportunistic: when its task
    cannot complete (no archived source, a newer document version, any error)
    the page is left for a later run to finish (a fault part way can leave
    healable partial writes) and nothing at all is reported for it, so an idle
    run stays silent. When it does complete, its notices and the rename
    notice are reported like any other rewrite.

    Req 6.6 requires repeating until a whole pass renames nothing, so the loop
    does. A move only ever vacates a suffixed path, and no candidate waits on a
    suffixed name, so in practice the second pass finds nothing and the loop
    is the requirement's termination rule rather than a source of extra moves.
    """
    pending = list(ledger.settle)
    known = {entry.path for entry in pending}
    pending.extend(e for e in _stranded_pages(data_root) if e.path not in known)
    moved: dict[str, str] = {}
    while True:
        progressed = False
        for entry in list(pending):
            if not entry.path.is_file():
                pending.remove(entry)
                continue
            occupant = doc_path(data_root, entry.unsuffixed)
            if occupant.exists() and occupant != entry.path:
                continue
            pending.remove(entry)
            page_ref = entry.path.relative_to(data_root).as_posix()
            try:
                text = entry.path.read_text(encoding="utf-8")
                front = parse_frontmatter(text)
                match = DocumentMatch(
                    path=entry.path,
                    sources=source_refs(front) if front is not None else (),
                )
                result = _page_task(
                    data_root,
                    match=match,
                    news=(),
                    athlete=athlete,
                    tz=tz,
                    tiles=tiles,
                    precedence=precedence,
                    settling=True,
                    quiet=not entry.opportunistic,
                    expected_stem=entry.unsuffixed,
                )
            except Exception as exc:
                if not entry.opportunistic:
                    failures.append(FileFailure(source=page_ref, reason=_reason(exc)))
                continue
            if result.doc_ref is None and entry.opportunistic:
                continue  # a version-gated page: left alone, and silently
            warnings.extend(result.warnings)
            if result.doc_ref is not None and result.renamed_from is not None:
                moved[page_ref] = result.doc_ref
                progressed = True
        if not progressed:
            break
    if moved:
        written[:] = [moved.get(ref, ref) for ref in written]
        warnings[:] = [
            DocWarning(doc=moved[warning.doc], detail=warning.detail)
            if warning.doc in moved
            else warning
            for warning in warnings
        ]
    return moved


def _render_activity(roles: PageRoles, parsed: Mapping[str, Activity]) -> Activity:
    """The activity a page renders: the base's own (Req 5.8).

    ``parsed`` maps each resolved member's archive ref to its parse. This is the
    seam channel-merge widens to compose the extras' channels; the page's
    identity keys never come from what it returns.
    """
    return parsed[roles.base.ref]


def _write_outputs(
    data_root: Path,
    document: Path,
    markdown: str,
    assets: tuple[Asset, ...],
    archives: tuple[tuple[Path, bytes], ...],
    *,
    moved_from: Path | None = None,
    stale_assets: tuple[str, ...] = (),
) -> None:
    """Write one page task's outputs in the crash-healing order (Req 3.1, 6.7, 7.1).

    New assets; stale assets removed; the document moved with a same-directory
    replace (a rename only); the document written; the archive copy **last**.
    At no instant does the page exist at two paths, and a crash after any step
    leaves a state the next run over the same inputs completes: the new member
    is not archived until the end, so it is re-planned onto the page that now
    holds its fellow members. Each step is its own helper so a test can inject
    a fault after any one of them.

    The archive's presence is the processed-marker (Req 3.1, 4.2). An existing
    archive is never rewritten (Req 3.5) -- only reachable under ``force``,
    where the immutable source copy must be preserved. Each new member of the
    task is archived, in order, after every other write; a settle task has no
    incoming file, so it passes none.
    """
    _write_assets(data_root, assets)
    _remove_stale_assets(data_root, stale_assets)
    if moved_from is not None:
        _move_document(moved_from, document)
    _write_document(document, markdown)
    for archive, source_bytes in archives:
        _write_archive(archive, source_bytes)


def _write_assets(data_root: Path, assets: tuple[Asset, ...]) -> None:
    """Step 1: the new render's assets, each doc-relative under ``workouts/``."""
    for asset in assets:
        asset_path = data_root / WORKOUTS_DIR / asset.rel_path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(asset.content, encoding="utf-8")


def _remove_stale_assets(data_root: Path, names: tuple[str, ...]) -> None:
    """Step 2: the previous render's chart files (Req 6.4); nothing else."""
    for name in names:
        (data_root / WORKOUTS_DIR / ASSETS_SUBDIR / name).unlink(missing_ok=True)


def _move_document(existing: Path, target: Path) -> None:
    """Step 3: ``os.replace`` within ``workouts/`` -- never two paths (Req 6.7)."""
    if target.exists():
        # A rename never overwrites another file: the computed name (or its
        # suffixed form) is held by something that is not this page.
        raise FileExistsError(f"cannot rename the page onto existing {target.name}")
    os.replace(existing, target)


def _write_document(document: Path, markdown: str) -> None:
    """Step 4: the document itself."""
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(markdown, encoding="utf-8")


def _write_archive(archive: Path, source_bytes: bytes) -> None:
    """Step 5, last and write-once: the archived source (presence = committed)."""
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


def _resolvable_source_archive(
    data_root: Path, sources: tuple[str, ...]
) -> Path | None:
    """An archived file for a document's ``sources`` history, or ``None``.

    Walks the history from its last entry -- the base -- backwards and returns
    the first entry that resolves back to a present ``fit-archive/<sha>.fit``
    through :func:`fitdocs.contract.sha_of_ref`, the exact inverse of
    :func:`fitdocs.layout.source_ref`. The page task then resolves every other
    listed file itself, so which one triggers the rebuild does not change the
    result. Returns ``None`` when the history is empty or none of its entries
    resolves to an archived file: the document cannot be regenerated and the
    caller records a failure.

    The contract's resolver validates the embedded sha rather than trusting it, so
    a hand-edited or traversal-shaped entry (``fit-archive/../secrets.fit``) is
    unresolvable here instead of becoming a path component joined onto the data
    root (Req 1.3). Such a document is reported as having no regenerable source --
    the same graceful degradation any other malformed history gets.
    """
    for ref in reversed(sources):
        sha = sha_of_ref(ref)
        if sha is None:
            continue
        archive = archive_path(data_root, sha)
        if archive.is_file():
            return archive
    return None


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
