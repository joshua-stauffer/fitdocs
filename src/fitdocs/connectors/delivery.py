"""Deliver fetched bytes into the inbox, and sweep archived deliveries away
(design: "Delivery layer", Req 6.7, 6.8, 8.1-8.8).

Two entry points. :func:`deliver` writes one fetched activity's bytes into
``<inbox>/<instance>/`` through the atomic writer, choosing a name that never
overwrites a different file already there (Req 8.1, 8.2, 8.3, 8.4).
:func:`sweep` walks an instance's ledger for deliveries still waiting
(``pending`` set) and resolves each one against the archive and the file's
current state on disk, producing the six outcomes design.md's "Delivery
lifecycle" names: removed, released, settled, unchanged, forgotten, and a
failed removal that stays pending (Req 8.5, 8.6, 8.7, 8.8).

:func:`sweep` never touches a file the ledger does not already know about:
it only ever acts on ``ledger.pending_entries()`` -- every other entry
(``skipped``, ``already-held``, or a ``delivered`` entry whose delivery was
already resolved) passes through unchanged -- and never removes a file whose
current bytes differ from the recorded hash (Req 8.6), so a hand-dropped
inbox file, or a delivery a later run modified, is left untouched either
way. :func:`deliver` makes no such claim about files outside its own target:
it reads the primary candidate's bytes to decide whether to reuse it, and
may leave a colliding file (even a directory) exactly as it found it while
writing elsewhere, but it is not scoped to "only files the ledger knows
about" the way :func:`sweep` is.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path

from fitdocs import layout
from fitdocs.connectors._atomic import write_atomic
from fitdocs.connectors.ledger import Ledger
from fitdocs.connectors.protocol import RemoteActivity

__all__ = [
    "is_fit",
    "delivery_name",
    "DeliveryResult",
    "deliver",
    "SweepResult",
    "sweep",
]

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]")
_STEM_CAP = 100
_FIT_SUFFIX = ".fit"


def is_fit(data: bytes) -> bool:
    """Whether ``data`` begins with a FIT file header (Req 6.7).

    The FIT header is at least 12 bytes; byte 0 is the header size (12 or 14
    depending on whether a CRC follows); bytes 8-12 spell ``.FIT``. Anything
    shorter, or failing either check, is not a FIT file.
    """
    if len(data) < 12:
        return False
    if data[0] not in (12, 14):
        return False
    return data[8:12] == b".FIT"


def delivery_name(activity: RemoteActivity) -> str:
    """The inbox filename to deliver ``activity`` under (design.md literal rule).

    ``base`` is ``activity.suggested_name`` if given, else ``remote_id`` --
    its last ``"/"``-separated path component. Characters outside
    ``[A-Za-z0-9._-]`` become ``"-"``; leading ``"."`` and ``"-"`` are then
    stripped. If what remains already ends in ``.fit`` (any case), that
    extension is kept as-is and only the part before it is capped at 100
    characters; otherwise the whole (capped) result becomes the stem and
    ``".fit"`` is appended. An empty stem becomes ``"activity"``.
    """
    base = activity.suggested_name or activity.remote_id
    base = base.rsplit("/", 1)[-1]

    sanitized = _SANITIZE_RE.sub("-", base)
    sanitized = sanitized.lstrip(".-")

    if sanitized.lower().endswith(_FIT_SUFFIX):
        stem, ext = sanitized[: -len(_FIT_SUFFIX)], sanitized[-len(_FIT_SUFFIX) :]
    else:
        stem, ext = sanitized, ""

    stem = stem[:_STEM_CAP]
    if not stem:
        stem = "activity"

    if ext:
        return stem + ext
    return stem + _FIT_SUFFIX


@dataclass(frozen=True)
class DeliveryResult:
    """The outcome of one :func:`deliver` call."""

    rel: str
    """Inbox-relative POSIX path, e.g. ``"healthfit/2026-09-20-run.fit"``."""

    written: bool
    """``False`` when an identical file already sat at the chosen path."""


def deliver(
    inbox: Path, instance: str, name: str, data: bytes, sha256: str
) -> DeliveryResult:
    """Write ``data`` into ``<inbox>/<instance>/`` under ``name`` (Req 8.1-8.4).

    The instance's subdirectory is created on demand. If ``<dir>/<name>``
    already holds a file whose content hash equals ``sha256``, that file is
    reused and nothing is written (``written=False``). Otherwise a
    content-derived name is chosen -- ``<stem>-<sha256[:8]>.fit``, then
    ``<stem>-<sha256[:8]>-2.fit``, ... -- escalating until a name that does
    not yet exist is found, the same scheme
    :func:`fitdocs.inbox._first_free_destination` uses (reimplemented here
    because that function is private and this package may not import
    :mod:`fitdocs.inbox`'s move-side internals). The write itself goes
    through :func:`fitdocs.connectors._atomic.write_atomic`, so the
    temporary name is dot-prefixed and the target is never partially
    written (Req 8.1); the bytes given are written unmodified (Req 8.2); an
    existing, different file at any candidate name is never overwritten
    (Req 8.3).
    """
    directory = inbox / instance
    directory.mkdir(parents=True, exist_ok=True)
    primary = directory / name

    if primary.is_file():
        if hashlib.sha256(primary.read_bytes()).hexdigest() == sha256:
            return DeliveryResult(
                rel=primary.relative_to(inbox).as_posix(), written=False
            )
        target = _escalate(primary, sha256)
    elif primary.exists():
        target = _escalate(primary, sha256)
    else:
        target = primary

    write_atomic(target, data, prefix=name)
    return DeliveryResult(rel=target.relative_to(inbox).as_posix(), written=True)


def _escalate(primary: Path, sha256: str) -> Path:
    """The next free name for ``primary``, given it (or its predecessor
    candidate) is already taken by different content.

    Mirrors :func:`fitdocs.inbox._first_free_destination`'s escalation
    scheme -- ``<stem>-<sha256[:8]>.fit``, then ``-2``, ``-3``, ... until a
    name that does not currently exist is found -- with one deliberate
    difference: :func:`fitdocs.inbox._first_free_destination` keeps
    ``primary.suffix`` verbatim (any extension a processed file may carry),
    while every delivery this package makes is a FIT file, so this function
    always appends the literal ``.fit`` to each escalated candidate
    regardless of ``primary``'s own suffix or its case. A pure function of
    ``primary``'s current filesystem state and ``sha256``.
    """
    name = primary.name
    stem = name[: -len(_FIT_SUFFIX)] if name.lower().endswith(_FIT_SUFFIX) else name
    parent = primary.parent
    short_hash = sha256[:8]

    hashed = parent / f"{stem}-{short_hash}{_FIT_SUFFIX}"
    if not hashed.exists():
        return hashed

    attempt = 2
    while True:
        candidate = parent / f"{stem}-{short_hash}-{attempt}{_FIT_SUFFIX}"
        if not candidate.exists():
            return candidate
        attempt += 1


@dataclass(frozen=True)
class SweepResult:
    """The outcome of one :func:`sweep` call."""

    ledger: Ledger
    """A copy of the given ledger with every resolved pending entry updated."""

    removed: tuple[str, ...]
    """Inbox-relative paths of files actually unlinked (Req 8.5)."""

    failures: tuple[tuple[str, str], ...]
    """``(path, reason)`` for a hash read or removal that raised; the entry
    stays pending. ``reason`` is ``f"{type(exc).__name__}: {exc}"``, matching
    the format ``pull.py``'s own exception reports use."""


def _remove(path: Path) -> None:
    """Unlink ``path``.

    Factored out so a test can make removal fail deterministically.
    """
    path.unlink()


def sweep(inbox: Path, data_root: Path, ledger: Ledger) -> SweepResult:
    """Resolve every pending delivery in ``ledger`` against the archive and
    the inbox's current state (design.md "Delivery lifecycle", Req 8.5-8.8).

    Only ``ledger.pending_entries()`` is ever considered -- a file the
    ledger does not record as pending is never touched (Req 8.6). For each
    pending entry, resolved by whether its archive copy
    (``fitdocs.layout.archive_path(data_root, entry.sha256)``) exists and
    whether the inbox file at ``entry.pending`` exists:

    * archived, file present, hash still equal -> unlink the file, clear
      ``pending``, record it in ``removed`` (Req 8.5) -- the hash is only
      computed in this branch, so a not-yet-archived entry costs one
      ``stat``, never a read.
    * archived, file present, hash differs -> clear ``pending`` only; the
      file itself is never touched (*released*, Req 8.6).
    * archived, file absent -> clear ``pending`` (*settled*: moved by the
      drain's move disposition, or deleted by a user after archiving).
    * not archived, file present -> leave the entry exactly as it is
      (*unchanged*: failed, quarantined, or not yet drained, Req 8.6).
    * not archived, file absent -> drop the entry entirely (*forgotten*, so
      the next pull fetches it again, Req 8.7).

    An :class:`OSError` while reading a present, archived file to hash it, or
    while removing it once the hash matches, leaves the entry pending and is
    reported in ``failures`` instead of ``removed`` -- the sweep continues
    with the next pending entry rather than aborting, and the next sweep will
    retry the failed one. ``pull.py`` (4.3) maps every ``failures`` pair to a
    deferred note keyed by the pending path.
    """
    result = ledger
    removed: list[str] = []
    failures: list[tuple[str, str]] = []

    for entry in ledger.pending_entries():
        pending_rel = entry.pending
        assert pending_rel is not None  # pending_entries() already filtered this
        pending_path = inbox / pending_rel
        sha = entry.sha256
        archive_exists = (
            sha is not None and layout.archive_path(data_root, sha).is_file()
        )
        file_exists = pending_path.is_file()

        if archive_exists:
            if file_exists:
                try:
                    current_hash = hashlib.sha256(pending_path.read_bytes()).hexdigest()
                except OSError as exc:
                    failures.append((pending_rel, f"{type(exc).__name__}: {exc}"))
                    continue
                if current_hash == sha:
                    try:
                        _remove(pending_path)
                    except OSError as exc:
                        failures.append((pending_rel, f"{type(exc).__name__}: {exc}"))
                        continue
                    result = result.with_entry(replace(entry, pending=None))
                    removed.append(pending_rel)
                else:
                    result = result.with_entry(replace(entry, pending=None))
            else:
                result = result.with_entry(replace(entry, pending=None))
        else:
            if file_exists:
                pass
            else:
                result = result.without(entry.remote_id)

    return SweepResult(ledger=result, removed=tuple(removed), failures=tuple(failures))
