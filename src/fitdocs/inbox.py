"""Inbox ingestion policy: the standing drain interface (design: Ingestion Policy).

fitdocs promotes ingestion from a per-invocation CLI argument to a standing,
configured interface: the user's export tooling (HealthFit -> iCloud, watch
sync, manual drops) delivers ``.fit`` files into a configured location, and
bare ``fitdocs sync`` drains it. This module owns the ingestion *policy* --
what the inbox is configured to be, which files are candidates, whether they
are stable, and what happens to them once processed. It never writes
documents, assets, or archive entries, and never knows what a document is.
Its filesystem writes are confined to the two user-configured locations: the
inbox and processed-files directories it may create inside the data root
(Req 1.5, 6.7, 8.5), and -- under the opt-in move disposition only -- the
moved file and its parent directories beneath the processed directory, whose
source side in the inbox is removed by that same move (Req 6.2, 6.6). The
stability check itself never opens or writes a candidate, only ``stat``s it.

This module holds five slices. The first owns the typed, validated
``[inbox]`` table reader (design: "InboxSettings + ``load_inbox_settings``",
Req 1.1-1.4, 1.7, 3.4, 4.4, 6.1, 6.2, 6.6). It follows the same table-reader
contract ``fitdocs.tiles`` already publishes for ``[tiles]``, now expressed
as a pure projection over the settings document ``fitdocs.settings`` parses
once per invocation:

* **Defaulted, never an error.** An absent ``fitdocs.toml`` -- or a file with
  no ``[inbox]`` table -- yields :data:`DEFAULT_INBOX_SETTINGS`. Each key
  defaults *independently*, so a partial ``[inbox]`` table fills only the
  keys it names.
* **Loud, never lossy.** A malformed ``[inbox]`` table -- a wrong-typed or
  empty value, an unrecognized disposition, a move disposition without a
  destination, or a destination equal to or nested inside the inbox -- raises
  :class:`InboxSettingsError`, naming the file and the offending key.
* **Reads no file.** :func:`load_inbox_settings` accepts the already-parsed
  settings mapping :func:`fitdocs.settings.load_settings_document` returns; it
  never opens ``fitdocs.toml`` itself. File-level faults (unreadable file,
  invalid TOML) are raised by that shared reader as :class:`SettingsError`
  and are never reported as :class:`InboxSettingsError` -- the two error
  voices stay separate so a user with a stray bracket gets one message
  instead of whichever table happened to be read first.

Unknown keys within ``[inbox]`` and unknown top-level tables are ignored,
because ``[tiles]`` and ``[plugins]`` share this same file.

The second slice owns :class:`InboxPaths` and :func:`prepare_inbox` (design:
"InboxPaths + ``prepare_inbox``", Req 1.1, 1.5, 1.6, 6.7, 8.5): turning
validated :class:`InboxSettings` into usable directories, or refusing loudly
-- naming the offending path -- before anything is processed. This is the
one place in the module that performs filesystem writes, and they are
confined to the two user-configured locations named above.

The third slice owns :class:`Candidate` and :func:`select_candidates` (design:
"CandidateSelector", Req 3.1-3.5): deciding what the engine is allowed to see
during a drain, and in what order. A candidate is a regular file whose
extension is ``.fit`` case-insensitively, discovered recursively and sorted
by inbox-relative POSIX path for a deterministic drain order (Req 3.1). Three
exclusions apply on top of that predicate, each one an *ignore*, never a
failure or a skip (Req 3.5):

* **Dot components** (Req 3.2): any candidate whose inbox-relative path has a
  component beginning with ``.`` -- covering AppleDouble ``._*`` companions
  and everything inside a hidden staging directory a sync tool creates
  (``.stversions/``, ``.AppleDouble/``, ...), without enumerating tools.
* **Default junk patterns** (Req 3.3): :data:`DEFAULT_IGNORE_PATTERNS`.
* **Configured patterns** (Req 3.4): ``settings.ignore``, applied in addition
  to, never instead of, the defaults.

Patterns match the basename or the inbox-relative POSIX path, with both the
pattern and the subject lowercased first, so behavior is identical on
case-sensitive and case-insensitive filesystems. :func:`select_candidates`
only reads the inbox -- it never writes, moves, or deletes anything, and an
ignored file never reaches the returned tuple, the only channel selection
has.

The fourth slice owns :class:`InboxNote`, :class:`SettleResult`, and
:func:`settle` (design: "StabilityCheck", Req 4.1-4.5): the batched stability
check that keeps a still-arriving file from ever being parsed, archived, or
quarantined. :func:`settle` stats every candidate once, waits **at most one**
settle interval for the *whole batch* -- never once per candidate (Req 4.5)
-- through an injected ``sleep`` callable so tests spend no wall-clock time,
then stats every candidate again. A candidate is stable only when both
observations succeed and report identical size and modification time
(Req 4.1); anything else -- changed, vanished, or otherwise unobservable --
is deferred, left completely untouched, and reported through
:class:`InboxNote` with a human-readable reason naming the file (Req 4.2).
A ``settle_seconds`` of ``0`` disables the wait and admits every candidate
that can be observed once (Req 4.4). The check is stateless: nothing about a
deferral persists, so a later call over the same file simply re-observes it
from scratch (Req 4.3). :class:`InboxNote` is the shared value type this
module introduces for the deferred, quarantined, and failed-move channels
alike -- ``subject`` (the file) and ``detail`` (the reason), deliberately
with no optional ``remedy`` field, since every note this feature produces is
already actionable from its detail; the already-shipped ``DocWarning`` and
``SyncReport`` types are not renamed here.

The fifth and final slice owns :func:`move_processed` (design: "Disposition",
Req 6.1-6.6): the disposition policy deciding what happens to a file once it
has been processed. :class:`Disposition` (defined above, alongside
:class:`InboxSettings`) has exactly two members, so a delete disposition is
unrepresentable in the type system, not merely undocumented (Req 6.6):

* **Leave-in-place** (:attr:`Disposition.LEAVE`, the default) is a no-op *by
  construction* -- there is no function in this module a caller invokes for
  it, so nothing ever touches the file. Re-drains skip it because its content
  is already archived; the archive copy is the processed marker, so no
  disposition-specific state is invented (Req 6.1).
* **Move** (:attr:`Disposition.MOVE`) is :func:`move_processed`: it relocates
  a file already confirmed processed out of the inbox to
  ``processed_dir``, preserving the file's inbox-relative subpath beneath
  that destination and creating parent directories on demand (Req 6.2).
  *Whether* a file is eligible to move -- content present in
  ``fit-archive/``, never failed/deferred/quarantined/skipped-without-archive
  -- is the caller's decision (a later task); this function only ever
  receives files already confirmed eligible.

  Collision safety (Req 6.3): when the destination path already exists (file
  or directory), the moved file is stored under a distinct,
  content-derived name instead -- ``<stem>-<sha256[:8]><suffix>``, then
  ``<stem>-<sha256[:8]>-2<suffix>``, ``-3``, and so on -- escalating
  deterministically until a free name is found, so both files always
  survive and neither is ever overwritten.

  The move itself is :func:`shutil.move`, onto a path confirmed absent, so
  it works when the inbox lives on a different volume from the data root
  (the common iCloud case) via copy-then-unlink rather than a bare
  ``os.rename``, which would raise ``EXDEV`` across filesystems.

  No code path in this module ever deletes an inbox file, under any
  configuration (Req 6.6): the only removal :func:`move_processed` ever
  performs is the source side of a move it just completed successfully. A
  move that fails for any reason -- an uncreatable parent, an unwritable
  destination, a source that vanished first -- returns an :class:`InboxNote`
  describing the failure rather than raising, so the already-completed
  processing stands and the file simply stays in the inbox for a later
  drain to retry (Req 6.5).

This module's slices are now complete for this spec; no further work is
outstanding here.
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from fitdocs.layout import DEFAULT_INBOX_DIR, settings_path
from fitdocs.settings import SettingsError

INBOX_TABLE: Final[str] = "inbox"


class Disposition(StrEnum):
    """What happens to an inbox file once it has been processed (Req 6.1-6.6).

    Exactly two members exist, so deletion is unrepresentable in the type
    system, not merely undocumented (Req 6.6).
    """

    LEAVE = "leave"
    """Default: inbox files are never written, moved, renamed, or deleted."""

    MOVE = "move"
    """Opt-in: move a processed file out of the inbox to ``processed_dir``."""


@dataclass(frozen=True)
class InboxSettings:
    """Validated ``[inbox]`` configuration (design: InboxSettings).

    Every field has a default (see :data:`DEFAULT_INBOX_SETTINGS`); a present
    ``[inbox]`` table overrides them per key, independently.
    """

    path: str
    """Data-root-relative or absolute inbox location.

    Default :data:`DEFAULT_INBOX_DIR`."""

    settle_seconds: float
    """Stability-check settle interval in seconds; ``>= 0``; ``0`` disables the
    wait; default ``2.0``."""

    ignore: tuple[str, ...]
    """Additional ignore patterns, applied in addition to the built-in defaults."""

    disposition: Disposition
    """The processed-file disposition; default :data:`Disposition.LEAVE`."""

    processed_dir: str | None
    """The processed-files destination; required iff ``disposition`` is ``MOVE``."""


DEFAULT_INBOX_SETTINGS: Final[InboxSettings] = InboxSettings(
    path=DEFAULT_INBOX_DIR,
    settle_seconds=2.0,
    ignore=(),
    disposition=Disposition.LEAVE,
    processed_dir=None,
)
"""The all-defaults :class:`InboxSettings`, used when ``fitdocs.toml`` or its
``[inbox]`` table is absent (Req 1.2)."""


class InboxSettingsError(SettingsError):
    """The ``fitdocs.toml`` ``[inbox]`` table exists but is not valid configuration.

    Raised for a non-table ``inbox`` value, a non-string or empty ``path``, a
    ``settle_seconds`` that is not a non-negative real number (a ``bool`` is
    rejected explicitly, since Python's ``bool`` subclasses ``int``), a
    non-list-of-non-empty-strings ``ignore``, a non-string or empty
    ``processed_dir``, an unrecognized ``disposition``, ``disposition =
    "move"`` without a ``processed_dir``, or a ``processed_dir`` equal to or
    nested inside the resolved inbox (Req 1.4, 3.4, 4.4, 6.2). Every message
    names the settings file and the offending key.

    File-level faults -- an unreadable file, invalid TOML -- are *not* raised
    here: they belong to the file rather than to this table and surface as the
    shared :class:`~fitdocs.settings.SettingsError` (Req 1.7). This type
    subclasses it, so ``except SettingsError`` still catches both.
    """


def load_inbox_settings(
    document: Mapping[str, object],
    *,
    data_root: Path,
) -> InboxSettings:
    """Project the ``[inbox]`` table of an already-parsed settings document.

    The per-table reader: it validates only ``[inbox]`` and never opens a
    file -- ``document`` is the mapping
    :func:`fitdocs.settings.load_settings_document` returned (empty when the
    settings file is absent), and ``data_root`` is used only to resolve the
    inbox and processed-files paths for the containment check; nothing is
    read, written, created, or prompted for.

    Returns :data:`DEFAULT_INBOX_SETTINGS` when the file or its ``[inbox]``
    table is absent (Req 1.2). Every present key overrides the default
    independently and unknown keys -- inside ``[inbox]`` or at the top level
    -- are ignored (Req 1.3). Raises :class:`InboxSettingsError` for a
    malformed ``[inbox]`` table (Req 1.4).
    """
    path = settings_path(data_root)
    if INBOX_TABLE not in document:
        return DEFAULT_INBOX_SETTINGS
    table = document[INBOX_TABLE]
    if not isinstance(table, dict):
        raise InboxSettingsError(
            f"{path}: [inbox] must be a table, got {table!r} ({type(table).__name__})"
        )

    inbox_path = _setting_nonempty_str(table, "path", DEFAULT_INBOX_SETTINGS.path, path)
    settle_seconds = _setting_settle_seconds(table, path)
    ignore = _setting_ignore(table, path)
    disposition = _setting_disposition(table, path)
    processed_dir = _setting_processed_dir(table, path)

    if disposition is Disposition.MOVE and processed_dir is None:
        raise InboxSettingsError(
            f'{path}: [inbox] disposition = "move" requires processed_dir to be set'
        )

    if processed_dir is not None:
        _check_processed_containment(data_root, inbox_path, processed_dir, path)

    return InboxSettings(
        path=inbox_path,
        settle_seconds=settle_seconds,
        ignore=ignore,
        disposition=disposition,
        processed_dir=processed_dir,
    )


def _setting_nonempty_str(
    table: dict[str, Any], key: str, default: str, path: Path
) -> str:
    """Map an optional non-empty string key; reject non-strings and the empty string."""
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, str) or value == "":
        raise InboxSettingsError(
            f"{path}: [inbox] {key} must be a non-empty string, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_processed_dir(table: dict[str, Any], path: Path) -> str | None:
    """Map the optional ``processed_dir`` key; absent stays ``None``."""
    if "processed_dir" not in table:
        return None
    value = table["processed_dir"]
    if not isinstance(value, str) or value == "":
        raise InboxSettingsError(
            f"{path}: [inbox] processed_dir must be a non-empty string, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_settle_seconds(table: dict[str, Any], path: Path) -> float:
    """Map the optional ``settle_seconds`` key: a non-negative real number.

    A ``bool`` is rejected explicitly -- Python's ``bool`` subclasses ``int``,
    so a naive numeric check would wrongly accept ``true``/``false``.
    """
    if "settle_seconds" not in table:
        return DEFAULT_INBOX_SETTINGS.settle_seconds
    value = table["settle_seconds"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise InboxSettingsError(
            f"{path}: [inbox] settle_seconds must be a non-negative number, "
            f"got {value!r} ({type(value).__name__})"
        )
    return float(value)


def _setting_ignore(table: dict[str, Any], path: Path) -> tuple[str, ...]:
    """Map the optional ``ignore`` key: a list of non-empty strings."""
    if "ignore" not in table:
        return DEFAULT_INBOX_SETTINGS.ignore
    value = table["ignore"]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item != "" for item in value
    ):
        raise InboxSettingsError(
            f"{path}: [inbox] ignore must be a list of non-empty strings, got {value!r}"
        )
    return tuple(value)


def _setting_disposition(table: dict[str, Any], path: Path) -> Disposition:
    """Map the optional ``disposition`` key onto the closed :class:`Disposition`."""
    if "disposition" not in table:
        return DEFAULT_INBOX_SETTINGS.disposition
    value = table["disposition"]
    valid = {member.value for member in Disposition}
    if not isinstance(value, str) or value not in valid:
        raise InboxSettingsError(
            f'{path}: [inbox] disposition must be "leave" or "move", got {value!r}'
        )
    return Disposition(value)


def _resolve_inbox_relative(data_root: Path, value: str) -> Path:
    """Resolve *value* against *data_root*, lexically, matching Req 1.1's rule.

    An absolute path is used as given; a relative path resolves against the
    data root. Both are lexically normalized (``os.path.normpath``) with no
    filesystem access, so a containment violation is reachable before any I/O
    (design: "no filesystem access, so a validation error is reachable before
    any I/O").
    """
    candidate = Path(value)
    joined = candidate if candidate.is_absolute() else data_root / candidate
    return Path(os.path.normpath(joined))


def _check_processed_containment(
    data_root: Path, inbox_value: str, processed_value: str, path: Path
) -> None:
    """Reject a ``processed_dir`` equal to or nested inside the resolved inbox.

    A destination that is the inbox itself, or lies beneath it, would re-ingest
    moved files forever (Req 1.4, 6.2).
    """
    resolved_inbox = _resolve_inbox_relative(data_root, inbox_value)
    resolved_processed = _resolve_inbox_relative(data_root, processed_value)
    nested = resolved_inbox in resolved_processed.parents
    if resolved_processed == resolved_inbox or nested:
        raise InboxSettingsError(
            f"{path}: [inbox] processed_dir must not equal or be nested "
            f"inside the inbox path "
            f"(inbox={resolved_inbox}, processed_dir={resolved_processed})"
        )


@dataclass(frozen=True)
class InboxPaths:
    """Resolved, existing directories the drain reads from and writes to
    (design: "InboxPaths + `prepare_inbox`", Req 1.1, 1.5, 1.6, 6.7, 8.5).

    Every field that is not ``None`` names a path that already exists and is
    a directory -- :func:`prepare_inbox` either created it or confirmed it,
    or it raised instead of returning.
    """

    inbox: Path
    """The resolved, existing inbox directory."""

    processed: Path | None
    """The resolved, existing processed-files destination, present iff the
    disposition is :attr:`Disposition.MOVE`."""


@dataclass(frozen=True)
class _ValidatedInboxPaths:
    """The result of validating the inbox config's paths, before either is
    created -- the seam between the no-writes validation phase and the
    create phase (design: "InboxPaths + `prepare_inbox`", Req 1.1, 1.5, 1.6,
    6.7, 7.2, 8.5).
    """

    inbox_resolved: Path
    inbox_needs_create: bool
    processed_resolved: Path | None
    processed_needs_create: bool


def validate_inbox_paths(
    data_root: Path, settings: InboxSettings
) -> _ValidatedInboxPaths:
    """Resolve and validate the inbox (and, under the move disposition, the
    processed-files destination) -- performing no filesystem writes -- or
    refuse (design: "InboxPaths + `prepare_inbox`", Req 1.1, 1.6, 6.7, 8.5).

    Resolution follows the same lexical rule :func:`load_inbox_settings`
    already applied for its containment check (Req 1.1): an absolute path is
    used as given, a relative path resolves against *data_root*, and both are
    normalized with :func:`os.path.normpath` -- no filesystem access.

    Existence policy, applied independently to each path: inside *data_root*
    and absent -- record that it needs creating, deferred to
    :func:`create_inbox_paths` (Req 1.5, 6.7); outside *data_root* and
    absent, or existing but not a directory anywhere -- raise
    :class:`InboxSettingsError` naming the offending path (Req 1.6, 6.7).
    Both paths are fully validated here, before either is created by the
    caller, so a refusal leaves the filesystem untouched (Req 7.2 in
    design's Error Handling; this module never partially applies a refused
    configuration).

    The processed-files destination is resolved only when
    ``settings.disposition`` is :attr:`Disposition.MOVE`; the leave-in-place
    default never touches it.
    """
    settings_file = settings_path(data_root)
    data_root_norm = Path(os.path.normpath(data_root))

    inbox_resolved, inbox_needs_create = _resolve_and_validate(
        data_root_norm, settings.path, settings_file, "path"
    )

    processed_resolved: Path | None = None
    processed_needs_create = False
    if settings.disposition is Disposition.MOVE:
        assert settings.processed_dir is not None  # load_inbox_settings enforces this
        processed_resolved, processed_needs_create = _resolve_and_validate(
            data_root_norm, settings.processed_dir, settings_file, "processed_dir"
        )

    return _ValidatedInboxPaths(
        inbox_resolved=inbox_resolved,
        inbox_needs_create=inbox_needs_create,
        processed_resolved=processed_resolved,
        processed_needs_create=processed_needs_create,
    )


def create_inbox_paths(validated: _ValidatedInboxPaths) -> InboxPaths:
    """Create whichever of the validated inbox paths is missing, and return
    the resolved, existing :class:`InboxPaths` (design: "InboxPaths +
    `prepare_inbox`", Req 1.5, 6.7).

    Callers must have already validated both paths with
    :func:`validate_inbox_paths`; this function performs the filesystem
    writes only, deliberately kept separate so a configuration refusal
    detected elsewhere (e.g. a malformed quarantine record) can be reported
    before either directory exists (Req 7.2).
    """
    if validated.inbox_needs_create:
        validated.inbox_resolved.mkdir(parents=True, exist_ok=True)
    if validated.processed_needs_create and validated.processed_resolved is not None:
        validated.processed_resolved.mkdir(parents=True, exist_ok=True)

    return InboxPaths(
        inbox=validated.inbox_resolved, processed=validated.processed_resolved
    )


def prepare_inbox(data_root: Path, settings: InboxSettings) -> InboxPaths:
    """Resolve the inbox (and, under the move disposition, the processed-files
    destination) and create whichever of them is missing and lies inside the
    data root -- or refuse before creating either (design: "InboxPaths +
    `prepare_inbox`", Req 1.1, 1.5, 1.6, 6.7, 8.5).

    A thin composition of :func:`validate_inbox_paths` (no writes) followed
    by :func:`create_inbox_paths` (writes only after validation succeeds),
    for callers that do not need to interleave another config check
    between the two phases.
    """
    return create_inbox_paths(validate_inbox_paths(data_root, settings))


def _resolve_and_validate(
    data_root_norm: Path, value: str, settings_file: Path, label: str
) -> tuple[Path, bool]:
    """Resolve one inbox-config path and decide whether it must be created.

    Returns ``(resolved_path, needs_create)``. Raises :class:`InboxSettingsError`
    naming *value*'s resolved path when it exists but is not a directory
    (regardless of location), or when it is absent and lies outside
    *data_root_norm* (Req 1.5, 1.6, 6.7).
    """
    resolved = _resolve_inbox_relative(data_root_norm, value)

    if resolved.exists():
        if not resolved.is_dir():
            raise InboxSettingsError(
                f"{settings_file}: [inbox] {label} exists but is not a "
                f"directory: {resolved}"
            )
        return resolved, False

    inside_data_root = resolved == data_root_norm or data_root_norm in resolved.parents
    if inside_data_root:
        return resolved, True

    raise InboxSettingsError(
        f"{settings_file}: [inbox] {label} does not exist: {resolved} "
        "(outside the data root, so fitdocs will not create it -- check for "
        "a typo or an unmounted volume)"
    )


DEFAULT_IGNORE_PATTERNS: Final[tuple[str, ...]] = (
    "*.tmp",
    "*.part",
    ".syncthing.*",
    ".DS_Store",
)
"""Default junk-name patterns ignored on top of the dot-component rule (Req 3.3).

All four are carried because Req 3.3 names them explicitly and because they
document the intent for readers of the settings file. None of them can
exclude a candidate that the ``.fit`` extension predicate and the
dot-component rule (Req 3.2) have already admitted: a name ending in
``.tmp`` or ``.part`` cannot also end in ``.fit``, and ``.syncthing.*`` /
``.DS_Store`` are themselves dot-prefixed, so the dot-component rule already
excludes them independently. The patterns exist to state the policy
Req 3.3 requires and to protect a candidate that a future, currently
unenumerated ``.fit``-suffixed junk name would otherwise slip through as --
not because any of today's four fixed strings is currently reachable."""


@dataclass(frozen=True)
class Candidate:
    """One inbox file eligible for the drain (design: CandidateSelector, Req 3.1)."""

    path: Path
    """The candidate's absolute path inside the inbox."""

    rel: str
    """The inbox-relative POSIX path -- the label every report entry uses."""


def select_candidates(inbox: Path, settings: InboxSettings) -> tuple[Candidate, ...]:
    """Discover ``.fit`` candidates under *inbox*, applying the ignore policy
    (design: "CandidateSelector", Req 3.1-3.5).

    Walks *inbox* recursively; a candidate is a regular file whose extension
    is ``.fit`` case-insensitively (Req 3.1) -- the same predicate ``sync``'s
    discovery uses. Three exclusions apply, each one an *ignore* rather than a
    failure or a skip (Req 3.5): any candidate whose inbox-relative path has a
    component beginning with ``.`` (Req 3.2); :data:`DEFAULT_IGNORE_PATTERNS`
    (Req 3.3); and ``settings.ignore``, applied in addition to the defaults
    (Req 3.4). Pattern matching checks both the basename and the
    inbox-relative POSIX path, with both the pattern and the subject
    lowercased first, so behavior is identical on case-sensitive and
    case-insensitive filesystems.

    Returns candidates sorted by inbox-relative path for a deterministic
    drain order. *inbox* is only read: this function never writes, moves, or
    deletes anything, and an ignored file never appears in the result -- the
    only channel selection has.
    """
    lowered_patterns = tuple(pattern.lower() for pattern in _ignore_patterns(settings))

    candidates = []
    for path in inbox.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".fit":
            continue
        rel = path.relative_to(inbox)
        if any(part.startswith(".") for part in rel.parts):
            continue
        rel_posix = rel.as_posix()
        if _matches_any_ignore_pattern(path.name, rel_posix, lowered_patterns):
            continue
        candidates.append(Candidate(path=path, rel=rel_posix))

    return tuple(sorted(candidates, key=lambda candidate: candidate.rel))


def _ignore_patterns(settings: InboxSettings) -> tuple[str, ...]:
    """The full ignore-pattern set for a drain: the defaults *plus* whatever
    ``settings.ignore`` configures -- never the configured set replacing the
    defaults (Req 3.3, 3.4). Factored out of :func:`select_candidates` so the
    additive composition itself is directly testable, independent of whether
    any given pattern happens to be reachable through a real inbox walk."""
    return DEFAULT_IGNORE_PATTERNS + settings.ignore


def _matches_any_ignore_pattern(
    basename: str, rel_posix: str, lowered_patterns: tuple[str, ...]
) -> bool:
    """Whether *basename* or *rel_posix* matches any of *lowered_patterns*.

    Pattern and subject are both lowercased before matching
    (:func:`fnmatch.fnmatchcase` against pre-lowercased strings), so results
    do not depend on the filesystem's case sensitivity (Req 3.3, 3.4)."""
    lowered_basename = basename.lower()
    lowered_rel = rel_posix.lower()
    return any(
        fnmatch.fnmatchcase(lowered_basename, pattern)
        or fnmatch.fnmatchcase(lowered_rel, pattern)
        for pattern in lowered_patterns
    )


@dataclass(frozen=True)
class InboxNote:
    """One inbox-scoped, non-fatal observation about a file (design:
    "StabilityCheck", Req 4.2, 5.2, 6.5).

    The shared value type for the deferred, quarantined, and failed-move
    channels: all three share the same shape -- a file and a reason -- so one
    type keeps the report and its presentation uniform. Field names follow
    the project-wide convention agreed for the Phase 3 report types --
    ``subject`` (the file it concerns) and ``detail`` (the human-readable
    reason) -- with no optional ``remedy`` field, since every note this
    feature produces is already actionable from its detail. It is deliberately
    distinct from :class:`~fitdocs.sync.FileFailure`, whose presence in a
    report means "this run failed"; the already-shipped ``DocWarning`` and
    ``SyncReport`` types are not renamed by this module.
    """

    subject: str
    """The inbox-relative POSIX path of the file this note concerns."""

    detail: str
    """The human-readable reason, naming what was observed."""


@dataclass(frozen=True)
class SettleResult:
    """The outcome of one :func:`settle` call (design: "StabilityCheck",
    Req 4.1-4.5).

    ``stable`` and ``deferred`` partition the input candidates, each ordered
    as the input was.
    """

    stable: tuple[Candidate, ...]
    """Candidates whose two observations matched -- safe to process."""

    deferred: tuple[InboxNote, ...]
    """Candidates that changed, vanished, or could not be observed twice,
    each carrying a human-readable reason naming the file."""


def settle(
    candidates: Sequence[Candidate],
    *,
    settle_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> SettleResult:
    """The batched stability check (design: "StabilityCheck", Req 4.1-4.5).

    Observes every candidate's size and modification time, waits at most
    *one* ``settle_seconds`` interval for the whole batch -- never once per
    candidate (Req 4.5) -- then observes every candidate again. A candidate
    is **stable** only when both observations succeed and report identical
    size and modification time (Req 4.1); anything else -- a changed size, a
    changed modification time, or the file vanishing or otherwise becoming
    unobservable between the two observations -- is **deferred**, left
    completely untouched, and reported with a human-readable reason naming
    the file (Req 4.2). This function never opens or reads a candidate's
    contents; only ``stat`` is used.

    A ``settle_seconds`` of ``0`` disables the wait entirely (Req 4.4): a
    single observation is taken, and every candidate that can be stat'd is
    treated as stable.

    The check is stateless: nothing about a deferral is recorded anywhere,
    so a later call over the same (now-settled) file simply admits it
    (Req 4.3).
    """
    first = _observe_all(candidates)

    if settle_seconds <= 0:
        stable = tuple(
            candidate for candidate in candidates if first[candidate.rel] is not None
        )
        deferred = tuple(
            InboxNote(subject=candidate.rel, detail=_unobservable_reason(candidate))
            for candidate in candidates
            if first[candidate.rel] is None
        )
        return SettleResult(stable=stable, deferred=deferred)

    sleep(settle_seconds)
    second = _observe_all(candidates)

    stable_list: list[Candidate] = []
    deferred_list: list[InboxNote] = []
    for candidate in candidates:
        before = first[candidate.rel]
        after = second[candidate.rel]
        if before is not None and after is not None and before == after:
            stable_list.append(candidate)
        else:
            reason = _settle_reason(candidate, before, after)
            deferred_list.append(InboxNote(subject=candidate.rel, detail=reason))

    return SettleResult(stable=tuple(stable_list), deferred=tuple(deferred_list))


def _observe_all(
    candidates: Sequence[Candidate],
) -> dict[str, tuple[int, int] | None]:
    """Stat every candidate once, keyed by inbox-relative path.

    ``None`` marks a candidate that could not be stat'd (vanished or
    otherwise inaccessible) in this observation."""
    observations: dict[str, tuple[int, int] | None] = {}
    for candidate in candidates:
        try:
            info = candidate.path.stat()
        except OSError:
            observations[candidate.rel] = None
        else:
            observations[candidate.rel] = (info.st_size, info.st_mtime_ns)
    return observations


def _unobservable_reason(candidate: Candidate) -> str:
    return f"{candidate.rel}: could not be observed (vanished or unreadable)"


def _settle_reason(
    candidate: Candidate,
    before: tuple[int, int] | None,
    after: tuple[int, int] | None,
) -> str:
    """A human-readable reason naming *candidate* for a deferral (Req 4.2)."""
    if before is None or after is None:
        return f"{candidate.rel}: vanished or became unreadable between observations"
    if before[0] != after[0]:
        return (
            f"{candidate.rel}: size changed while settling "
            f"({before[0]} -> {after[0]} bytes)"
        )
    return f"{candidate.rel}: modification time changed while settling"


def move_processed(
    candidate: Candidate,
    processed_dir: Path,
    sha256: str,
) -> str | InboxNote:
    """Move *candidate* out of the inbox to *processed_dir* (design:
    "Disposition", Req 6.1-6.6).

    Preserves *candidate*'s inbox-relative subpath beneath *processed_dir*,
    creating parent directories on demand (Req 6.2). *Whether* a file is
    eligible to move -- content present in ``fit-archive/``, never
    failed/deferred/quarantined/skipped-without-archive -- is decided by the
    caller; this function only ever handles files already confirmed
    processed.

    If the destination already exists (as a file or a directory), the file
    is instead stored under a distinct, content-derived name --
    ``<stem>-<sha256[:8]><suffix>``, then ``<stem>-<sha256[:8]>-2<suffix>``,
    ``-3``, and so on -- escalating deterministically until a free name is
    found, so both files always survive and neither is ever overwritten
    (Req 6.3). The escalation is a pure function of the destination and
    *sha256*, so repeated calls with the same inputs against the same
    filesystem state land on the same name.

    The move itself is :func:`shutil.move` onto a path already confirmed
    absent, so it works when the inbox lives on a different volume than the
    data root (the common iCloud case) via copy-then-unlink rather than a
    bare rename, which would raise ``EXDEV`` across filesystems.

    Never deletes anything other than the source side of a move it just
    completed (Req 6.6): a failure at any point -- an uncreatable parent
    directory, an unwritable destination, a source that vanished before the
    move -- returns an :class:`InboxNote` describing the failure instead of
    raising, leaving the already-completed processing intact and the file in
    the inbox for a later drain to retry (Req 6.5). Returns the destination
    path (as a string) on success -- always the full, absolute path, since
    this function carries no ``data_root`` argument to relativize against;
    a caller that wants a data-root-relative label for presentation derives
    it itself.
    """
    primary = processed_dir / Path(candidate.rel)
    destination = _first_free_destination(primary, sha256)

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(candidate.path), str(destination))
    except OSError as exc:
        return InboxNote(
            subject=candidate.rel,
            detail=f"could not move to {destination}: {exc}",
        )

    return str(destination)


def _first_free_destination(primary: Path, sha256: str) -> Path:
    """The destination :func:`move_processed` uses for *primary*, escalating
    deterministically through content-derived names until one is free
    (Req 6.3).

    ``primary`` itself is used when free. Otherwise the sequence is
    ``<stem>-<sha256[:8]><suffix>``, then ``<stem>-<sha256[:8]>-2<suffix>``,
    ``-3``, ... -- a pure function of *primary*'s current filesystem state
    and *sha256*, so identical inputs against identical filesystem state
    always escalate to the same name.
    """
    if not primary.exists():
        return primary

    stem = primary.stem
    suffix = primary.suffix
    parent = primary.parent
    short_hash = sha256[:8]

    hashed = parent / f"{stem}-{short_hash}{suffix}"
    if not hashed.exists():
        return hashed

    attempt = 2
    while True:
        escalated = parent / f"{stem}-{short_hash}-{attempt}{suffix}"
        if not escalated.exists():
            return escalated
        attempt += 1
