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
way. :func:`deliver` is scoped the same way on its reuse decision (R2
controller ruling, Req 15.4, Req 8.6): an existing file at a candidate name
is only ever reused when ``owned`` -- a mapping from inbox-relative path to
the sha256 this instance itself recorded delivering there -- maps that exact
path to the candidate's own sha256, and the file's current bytes still hash
to it; never merely because its bytes happen to match some other recorded
delivery, and never because the path alone was once this instance's. A
byte-identical file the athlete's own tool placed at that exact name, or one
the athlete overwrote after this instance delivered there, is therefore
never adopted, so it can never later be removed by :func:`sweep` once a
*different* file ends up archived under the same hash. Any other existing
file at a candidate name (identical or not, owned under a different hash, or
even a directory) is left exactly as :func:`deliver` found it, and the
delivery escalates to the next candidate.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

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
    """``False`` when this instance's own recorded delivery already sat there."""


def deliver(
    inbox: Path,
    instance: str,
    name: str,
    data: bytes,
    sha256: str,
    *,
    owned: Mapping[str, str] = MappingProxyType({}),
) -> DeliveryResult:
    """Write ``data`` into ``<inbox>/<instance>/`` under ``name`` (Req 8.1-8.4,
    15.4; R2 controller ruling).

    The instance's subdirectory is created on demand. Candidates are tried
    in order -- ``<dir>/<name>``, then ``<stem>-<sha256[:8]>.fit``, then
    ``<stem>-<sha256[:8]>-2.fit``, ... (the same scheme
    :func:`fitdocs.inbox._first_free_destination` uses, reimplemented here
    because that function is private and this package may not import
    :mod:`fitdocs.inbox`'s move-side internals). At each candidate: if
    nothing exists there, ``data`` is written there and that candidate is
    the result. If a *file* exists there, it is reused (``written=False``)
    only when ``owned`` maps its inbox-relative POSIX path to this exact
    ``sha256`` -- i.e. this instance itself previously recorded delivering
    these bytes at this path (Req 8.6's definition of a delivery) -- and the
    file's current on-disk bytes still hash to ``sha256``. Any other
    existing entry at a candidate -- an unowned file (identical content or
    not), a file owned under a different hash, or a directory -- is left
    exactly as found, and the search moves to the next candidate. This is
    what keeps a byte-identical file the athlete's own tool placed at the
    exact candidate name from ever being adopted (Req 15.4): callers pass a
    mapping from the inbox-relative paths of this instance's own pending and
    already-delivered-this-run entries to the sha256 recorded for each.

    The write itself goes through
    :func:`fitdocs.connectors._atomic.write_atomic`, so the temporary name
    is dot-prefixed and the target is never partially written (Req 8.1);
    the bytes given are written unmodified (Req 8.2); an existing, unowned
    file at any candidate name is never overwritten (Req 8.3).
    """
    directory = inbox / instance
    directory.mkdir(parents=True, exist_ok=True)
    primary = directory / name

    for candidate in _candidates(primary, sha256):
        rel = candidate.relative_to(inbox).as_posix()
        if candidate.is_file():
            if (
                owned.get(rel) == sha256
                and hashlib.sha256(candidate.read_bytes()).hexdigest() == sha256
            ):
                return DeliveryResult(rel=rel, written=False)
            continue
        if candidate.exists():
            # A directory (or other non-file) sits at this name -- never a
            # target to reuse or overwrite; move on to the next candidate.
            continue
        write_atomic(candidate, data, prefix=name)
        return DeliveryResult(rel=rel, written=True)
    raise AssertionError("unreachable: _candidates never stops yielding free names")


def _candidates(primary: Path, sha256: str) -> Iterator[Path]:
    """The ordered, unbounded sequence of names :func:`deliver` tries.

    ``primary`` first, then ``<stem>-<sha256[:8]>.fit``, then
    ``<stem>-<sha256[:8]>-2.fit``, ``-3``, ... without end -- the caller
    (:func:`deliver`) stops at the first candidate it can use. Mirrors
    :func:`fitdocs.inbox._first_free_destination`'s escalation scheme, with
    one deliberate difference: :func:`fitdocs.inbox._first_free_destination`
    keeps ``primary.suffix`` verbatim (any extension a processed file may
    carry), while every delivery this package makes is a FIT file, so this
    generator always appends the literal ``.fit`` to each escalated
    candidate regardless of ``primary``'s own suffix or its case. A pure
    function of ``primary`` and ``sha256`` -- it reads no filesystem state
    itself.
    """
    yield primary

    name = primary.name
    stem = name[: -len(_FIT_SUFFIX)] if name.lower().endswith(_FIT_SUFFIX) else name
    parent = primary.parent
    short_hash = sha256[:8]

    yield parent / f"{stem}-{short_hash}{_FIT_SUFFIX}"

    attempt = 2
    while True:
        yield parent / f"{stem}-{short_hash}-{attempt}{_FIT_SUFFIX}"
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
