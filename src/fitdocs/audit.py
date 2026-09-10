"""The read-only contract audit (design: ContractAudit, `src/fitdocs/audit.py`).

fitdocs is installed into wikis it does not control, and a maintainer -- human
or automation -- needs a way to ask "does this tree still match the installed
fitdocs?" without fitdocs writing anything to find out. :func:`audit` is that
question answered: a single sorted, read-only scan of ``workouts/*.md`` plus the
in-tree ownership declarations, producing a :class:`Finding` for every place the
tree and the contract disagree (Req 8.1-8.6).

Read-only, and offline
-----------------------
This module opens files to read text and nothing else. It never writes a byte,
never creates a directory (including ``workouts/`` itself when absent), never
opens a ``.fit`` source, and never touches the network (Req 8.1, 8.8). Every
reader it composes -- :mod:`fitdocs.contract`'s pure frontmatter/version/key
readers, :func:`fitdocs.docmerge.extract_regions`, and
:func:`fitdocs.declaration.inspect_declarations` -- already holds that
guarantee; this module is what walks the tree and turns their answers into
:class:`Finding` values.

One document, several findings
-------------------------------
A single workout document can be simultaneously out of date, carry damaged
regions, and hold an unmanaged key: :func:`audit` checks each condition
independently and reports every one it finds, so a document never masks a
second problem by reporting only the first. A clean tree yields
``findings == ()``.

The 5.7 trap
------------
A document with no ``doc_version`` key, or one whose value is not a genuine
integer, is *out of date* -- never *newer*. :func:`fitdocs.contract.document_version`
already encodes this (it returns ``None`` for both "absent" and "unusable", and
rejects ``bool``); this module classifies ``None`` the same way it classifies a
version below :data:`fitdocs.contract.DOC_VERSION` (Req 5.7).

Unreadable documents are findings, not exceptions
--------------------------------------------------
``workouts/*.md`` is glob-matched by name, not by type: a directory, a dangling
or hostile symlink, a permission-denied file, and a file that is not valid
UTF-8 can all appear in that listing. None of them raises here -- each is
reported as a finding naming its path, and the scan continues (Req 8.1). Such a
path is never counted in :attr:`AuditReport.documents`, since its contents were
never confirmed to be a fitdocs workout document at all.

Report-value convention
------------------------
:class:`Finding` follows the ``(subject, detail, remedy)`` naming shared with
the sibling report types this feature's design coordinates: ``subject`` is
always a data-root-relative POSIX path here (documented on the field, not left
implicit), ``detail`` is what was observed, and ``remedy`` is the action that
resolves it (Req 8.6). :class:`FindingKind` is a :class:`~enum.StrEnum`, the
project's convention for a new string-valued enum. This is a *new* type for a
*new* channel -- :class:`fitdocs.sync.DocWarning` is route-maps' shipped
document-scoped warning and is untouched and unrenamed here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fitdocs.contract import (
    DOC_VERSION,
    InvalidEffortTag,
    document_version,
    effort_tag,
    is_workout_document,
    parse_frontmatter,
    unmanaged_keys,
)
from fitdocs.declaration import (
    DECLARATION_FILENAME,
    DeclarationState,
    inspect_declarations,
)
from fitdocs.docio import REMEDY_REPLACE_SYMLINK as _REMEDY_REPLACE_SYMLINK
from fitdocs.docio import SYMLINK_DETAIL as _SYMLINK_DETAIL
from fitdocs.docmerge import RegionError, extract_regions
from fitdocs.layout import WORKOUTS_DIR

__all__ = [
    "AuditReport",
    "Finding",
    "FindingKind",
    "audit",
]


class FindingKind(StrEnum):
    """What kind of contract divergence a :class:`Finding` reports (Req 8.2-8.5)."""

    OUTDATED_VERSION = "outdated_version"
    """``doc_version`` is below :data:`fitdocs.contract.DOC_VERSION`, absent, or
    unusable -- including a document this pass could not read at all (Req 5.3,
    5.7, 8.2)."""

    NEWER_VERSION = "newer_version"
    """``doc_version`` is a genuine integer strictly above
    :data:`fitdocs.contract.DOC_VERSION` (Req 8.2)."""

    DAMAGED_REGIONS = "damaged_regions"
    """:func:`fitdocs.docmerge.extract_regions` raised
    :class:`~fitdocs.docmerge.RegionError` on the document's body (Req 8.3)."""

    UNMANAGED_KEYS = "unmanaged_keys"
    """The document's frontmatter carries one or more keys outside
    :data:`fitdocs.contract.MANAGED_KEYS` (Req 8.4)."""

    DECLARATION_MISSING = "declaration_missing"
    """A declared directory's ``AGENTS.md`` is absent (Req 8.5)."""

    DECLARATION_STALE = "declaration_stale"
    """A declared directory's ``AGENTS.md`` is present, fitdocs-generated, and
    its content no longer matches what fitdocs would write (Req 8.5)."""

    DECLARATION_FOREIGN = "declaration_foreign"
    """A declared directory's ``AGENTS.md`` path is occupied by a file fitdocs
    did not write (Req 8.5)."""

    INVALID_EFFORT_TAG = "invalid_effort_tag"
    """The document's effort tag (:func:`fitdocs.contract.effort_tag`) is
    malformed -- distinct from :attr:`UNMANAGED_KEYS`, since an effort key is
    user-owned, not unmanaged (Req 1.4, 3.5, 4.7)."""


@dataclass(frozen=True)
class Finding:
    """One place the owned tree diverges from the installed contract (Req 8.6)."""

    kind: FindingKind
    """What kind of divergence this is."""

    subject: str
    """The affected path, always data-root-relative and POSIX (e.g.
    ``"workouts/2026-07-12-run-0730.md"`` or ``"fit-archive/AGENTS.md"``)."""

    detail: str
    """What was observed -- concise and human-readable."""

    remedy: str
    """The action that resolves this finding."""


@dataclass(frozen=True)
class AuditReport:
    """The outcome of one :func:`audit` pass."""

    findings: tuple[Finding, ...]
    """Every divergence found, sorted by :attr:`Finding.subject` then
    :attr:`Finding.kind`. Empty for a clean tree."""

    documents: int
    """The number of recognized fitdocs workout documents inspected -- never a
    stray ``.md`` file, an unreadable path, or an ownership declaration."""


# --- remedies, named once and reused ------------------------------------------
#
# One string per remedy, referenced by every finding site that needs it, so a
# wording change happens in exactly one place.

_REMEDY_REGENERATE: str = "run `fitdocs regen` to bring it to the current format"
_REMEDY_REMOVE_DIRECTORY: str = (
    "remove or rename the directory so fitdocs can place the document"
)
_REMEDY_RESTORE_PERMISSION: str = "restore read permission on this file"
_REMEDY_RESTORE_ACCESS: str = (
    "restore access to this path, or remove it if it is no longer a document"
)
_REMEDY_RESTORE_OR_DELETE_CORRUPT: str = (
    "restore or delete the corrupt file; regeneration skips a document it cannot read"
)
_REMEDY_LEAVE_NEWER: str = (
    "leave it: it was written by a newer fitdocs and must not be downgraded"
)
_REMEDY_FIX_MARKERS: str = (
    "restore the document's region markers by hand; a damaged document is "
    "never rewritten automatically"
)
_REMEDY_MOVE_UNMANAGED: str = (
    "move any content worth keeping into the `notes` region before the next "
    "regeneration drops these keys"
)
_REMEDY_RUN_SYNC_OR_REGEN: str = (
    "run `fitdocs sync` or `fitdocs regen` to write the current declaration"
)
_REMEDY_CLEAR_FOREIGN: str = (
    "rename or remove the foreign file occupying this path so fitdocs can "
    "place its declaration"
)
_REMEDY_FIX_EFFORT_TAG: str = (
    "correct the named effort key(s) by hand; the tag is preserved as "
    "written but is not in effect until it is valid"
)


def _document_findings(
    subject: str, text: str, frontmatter: Mapping[str, object]
) -> tuple[Finding, ...]:
    """Every finding for one recognized ``workouts/*.md`` document, or ``()`` if
    it is clean.

    Only called once the caller has already read ``text``, parsed
    ``frontmatter`` from it, and confirmed :func:`fitdocs.contract.is_workout_document`
    -- an unreadable path or a stray, non-fitdocs ``.md`` file never reaches
    here (Req 8.1).
    """
    findings: list[Finding] = []

    version = document_version(frontmatter)
    if version is None:
        findings.append(
            Finding(
                kind=FindingKind.OUTDATED_VERSION,
                subject=subject,
                detail="doc_version is missing or unusable",
                remedy=_REMEDY_REGENERATE,
            )
        )
    elif version < DOC_VERSION:
        findings.append(
            Finding(
                kind=FindingKind.OUTDATED_VERSION,
                subject=subject,
                detail=f"doc_version is {version}, below the current {DOC_VERSION}",
                remedy=_REMEDY_REGENERATE,
            )
        )
    elif version > DOC_VERSION:
        findings.append(
            Finding(
                kind=FindingKind.NEWER_VERSION,
                subject=subject,
                detail=f"doc_version is {version}, above the current {DOC_VERSION}",
                remedy=_REMEDY_LEAVE_NEWER,
            )
        )

    try:
        extract_regions(text)
    except RegionError as exc:
        findings.append(
            Finding(
                kind=FindingKind.DAMAGED_REGIONS,
                subject=subject,
                detail=str(exc),
                remedy=_REMEDY_FIX_MARKERS,
            )
        )

    dropped = unmanaged_keys(frontmatter)
    if dropped:
        findings.append(
            Finding(
                kind=FindingKind.UNMANAGED_KEYS,
                subject=subject,
                detail=f"unmanaged frontmatter keys: {', '.join(dropped)}",
                remedy=_REMEDY_MOVE_UNMANAGED,
            )
        )

    tag = effort_tag(frontmatter)
    if isinstance(tag, InvalidEffortTag):
        findings.append(
            Finding(
                kind=FindingKind.INVALID_EFFORT_TAG,
                subject=subject,
                detail=f"malformed effort tag: {tag.describe()}",
                remedy=_REMEDY_FIX_EFFORT_TAG,
            )
        )

    return tuple(findings)


class _UnreadableCause(StrEnum):
    """Why one ``workouts/*.md`` path could not be read as a document's text
    (Req 8.1). Internal to this module -- distinct from, and never confused
    with, :class:`FindingKind`."""

    DIRECTORY = "directory"
    SYMLINK = "symlink"
    PERMISSION = "permission"
    OS_ERROR = "os_error"
    INVALID_UTF8 = "invalid_utf8"


@dataclass(frozen=True)
class _Unreadable:
    """Sentinel: something occupies ``path``, but its text could not be read.

    Mirrors :class:`fitdocs.declaration._Unreadable`'s role -- distinct from a
    bare ``str`` so the caller can tell "read" apart from "not read" -- but
    carries the specific :attr:`cause` and a ready-to-report ``detail``,
    because unlike the declaration reader (which treats every unreadable
    occupant identically as :attr:`~fitdocs.declaration.DeclarationState.FOREIGN`),
    this module owes each cause its own truthful detail and remedy (Req 8.6).
    """

    cause: _UnreadableCause
    detail: str


_UNREADABLE_REMEDY: dict[_UnreadableCause, str] = {
    _UnreadableCause.DIRECTORY: _REMEDY_REMOVE_DIRECTORY,
    _UnreadableCause.SYMLINK: _REMEDY_REPLACE_SYMLINK,
    _UnreadableCause.PERMISSION: _REMEDY_RESTORE_PERMISSION,
    _UnreadableCause.OS_ERROR: _REMEDY_RESTORE_ACCESS,
    _UnreadableCause.INVALID_UTF8: _REMEDY_RESTORE_OR_DELETE_CORRUPT,
}
"""Every :class:`_UnreadableCause`'s remedy -- never :data:`_REMEDY_REGENERATE`:
:func:`fitdocs.docio.read_frontmatter` (the same reader :mod:`fitdocs.sync`
imports as ``_read_frontmatter``) swallows ``OSError``/``UnicodeDecodeError``
and refuses a symlink outright, returning ``None`` for exactly these paths, so
``fitdocs regen`` silently skips a directory, a permission-denied file, an
other OS-level failure, or invalid UTF-8 rather than resolving anything. The
SYMLINK cause is the one exception: both ``sync`` and ``regen`` now emit a
:class:`~fitdocs.sync.DocWarning` naming that consequence for every symlinked
path they encounter (wiki-contract task 7.2), so that cause alone is not
silent -- only this read-only audit still reports it merely as a finding."""


def _read_document(path: Path) -> str | _Unreadable:
    """A workout document's text, or an :class:`_Unreadable` naming why it
    could not be read (Req 8.1).

    A symlink is refused before any read is attempted -- ``read_text`` follows
    one, and a dangling or hostile symlink must not be traversed; it is
    reported as :attr:`~_UnreadableCause.SYMLINK`, never opened at all.
    ``workouts/*.md`` is name-matched, not type-matched, so a directory can
    appear in the listing too, reported as :attr:`~_UnreadableCause.DIRECTORY`.
    A permission error or other OS-level failure opening a file that *is*
    valid UTF-8 is :attr:`~_UnreadableCause.OS_ERROR`; a file this process can
    open but that decodes to nothing is :attr:`~_UnreadableCause.INVALID_UTF8`.
    Never raises.
    """
    if path.is_symlink():
        return _Unreadable(_UnreadableCause.SYMLINK, _SYMLINK_DETAIL)
    if path.is_dir():
        return _Unreadable(
            _UnreadableCause.DIRECTORY,
            "a directory occupies this document's path",
        )
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _Unreadable(
            _UnreadableCause.INVALID_UTF8,
            "the file is not valid UTF-8 text",
        )
    except PermissionError as exc:
        # Split from the generic OSError below: "restore read permission" is
        # the wrong instruction for a file that was deleted between the scan
        # and the read, which reports "No such file or directory".
        reason = exc.strerror or str(exc)
        return _Unreadable(
            _UnreadableCause.PERMISSION,
            f"the file could not be opened: {reason}",
        )
    except OSError as exc:
        reason = exc.strerror or str(exc)
        return _Unreadable(
            _UnreadableCause.OS_ERROR,
            f"the file could not be opened: {reason}",
        )


_DECLARATION_FINDING_KIND: dict[DeclarationState, FindingKind] = {
    DeclarationState.MISSING: FindingKind.DECLARATION_MISSING,
    DeclarationState.STALE: FindingKind.DECLARATION_STALE,
    DeclarationState.FOREIGN: FindingKind.DECLARATION_FOREIGN,
}
"""Every :class:`~fitdocs.declaration.DeclarationState` that is itself a
finding. :attr:`~fitdocs.declaration.DeclarationState.CURRENT` and
:attr:`~fitdocs.declaration.DeclarationState.WRITTEN` are deliberately absent:
a current declaration is not a divergence, and :func:`inspect_declarations`
never returns ``WRITTEN`` (that state is ``ensure_declarations``-only)."""

_DECLARATION_DETAIL: dict[DeclarationState, str] = {
    DeclarationState.MISSING: "no AGENTS.md ownership declaration is present",
    DeclarationState.STALE: (
        "the AGENTS.md declaration is present but its content is out of date"
    ),
    DeclarationState.FOREIGN: (
        "a file occupies AGENTS.md's path but was not written by fitdocs"
    ),
}

_DECLARATION_REMEDY: dict[DeclarationState, str] = {
    DeclarationState.MISSING: _REMEDY_RUN_SYNC_OR_REGEN,
    DeclarationState.STALE: _REMEDY_RUN_SYNC_OR_REGEN,
    DeclarationState.FOREIGN: _REMEDY_CLEAR_FOREIGN,
}


def _declaration_findings(data_root: Path) -> tuple[Finding, ...]:
    """Every finding from the in-tree ownership declarations (Req 8.5).

    Delegates entirely to :func:`fitdocs.declaration.inspect_declarations`,
    which is itself read-only and creates no directory; this only maps the
    states that are divergences onto :class:`Finding` values.
    """
    findings: list[Finding] = []
    for outcome in inspect_declarations(data_root):
        kind = _DECLARATION_FINDING_KIND.get(outcome.state)
        if kind is None:
            continue
        findings.append(
            Finding(
                kind=kind,
                subject=outcome.path,
                detail=_DECLARATION_DETAIL[outcome.state],
                remedy=_DECLARATION_REMEDY[outcome.state],
            )
        )
    return tuple(findings)


def audit(data_root: Path) -> AuditReport:
    """Scan ``data_root`` against the current contract without writing anything.

    Scans ``workouts/*.md`` in sorted order (Req 8.1). The ownership
    declaration (``AGENTS.md``) is excluded by name **before** the unreadable
    branch below, so a symlinked, non-UTF-8, permission-denied, or
    directory-occupied declaration never contributes an
    :attr:`FindingKind.OUTDATED_VERSION` finding -- it is never treated as a
    workout document in this scan, in any identity match, in regeneration, or
    in a training-load operation (Req 3.7). Its own state is reported, and
    reported correctly, through :func:`fitdocs.declaration.inspect_declarations`
    below instead. Every other stray ``.md`` file is filtered afterward via
    :func:`fitdocs.contract.is_workout_document` and
    :func:`fitdocs.contract.parse_frontmatter` -- never a filename pattern. A
    missing ``workouts/`` directory yields zero documents, not an error: this
    pass never creates it (Req 8.1).

    Each recognized workout document is checked for every condition
    independently -- an out-of-date or newer ``doc_version``, damaged region
    markers, an unmanaged frontmatter key, and a malformed effort tag -- so
    one document can contribute more than one :class:`Finding` (Req 5.3, 5.7,
    8.2-8.4; effort-tags 1.4, 3.5). The unmanaged-key and malformed-tag checks
    are independent of each other: a document can carry both. The in-tree
    ownership declarations are inspected the same way (Req 8.5).

    Findings are sorted by :attr:`Finding.subject` then :attr:`Finding.kind`
    for a deterministic report; a clean tree yields ``findings == ()``. Opens
    no ``.fit`` file and performs no network access (Req 8.8): only the
    documents' own text and the declaration files are ever read.
    """
    documents = 0
    findings: list[Finding] = []

    workouts_dir = data_root / WORKOUTS_DIR
    if workouts_dir.is_dir():
        for path in sorted(workouts_dir.glob("*.md")):
            if path.name == DECLARATION_FILENAME:
                # Req 3.7: the ownership declaration is never treated as a
                # workout document in any document scan -- excluded here,
                # before the unreadable branch, so an unreadable declaration
                # (symlink, non-UTF-8, permission-denied, directory) never
                # produces a spurious OUTDATED_VERSION finding. Its own state
                # is reported by _declaration_findings below instead.
                continue
            subject = path.relative_to(data_root).as_posix()
            result = _read_document(path)

            if isinstance(result, _Unreadable):
                findings.append(
                    Finding(
                        kind=FindingKind.OUTDATED_VERSION,
                        subject=subject,
                        detail=result.detail,
                        remedy=_UNREADABLE_REMEDY[result.cause],
                    )
                )
                continue

            text = result
            frontmatter = parse_frontmatter(text)
            if frontmatter is None or not is_workout_document(frontmatter):
                continue  # not a fitdocs workout document -- not our concern
            documents += 1

            findings.extend(_document_findings(subject, text, frontmatter))

    findings.extend(_declaration_findings(data_root))

    findings.sort(key=lambda finding: (finding.subject, finding.kind))
    return AuditReport(findings=tuple(findings), documents=documents)
