"""The per-instance ledger: what a connector has already fetched (Req 7).

Authoritative for ``<data_root>/.fitdocs/connectors/<instance>.toml`` -- the
record of every remote activity an instance's pulls have decided about. A
pull decides whether a remote id is new from this record alone: an activity
missing from one listing (a lazily populated cloud folder) is fetched again
by whichever later pull lists it (Req 7.7).

Three invariants shape the contract, mirroring ``quarantine.py``'s:

* **Absent is empty, never an error, and reading creates nothing.**
  :func:`load_ledger` of an instance with no ledger file yields an empty
  :class:`Ledger` for the given ``connector_id`` and creates neither the
  file nor its directory (Req 7.5). A path that exists but is not a regular
  file (for example a directory), that cannot be read, is not parseable
  TOML, or is not in the documented shape -- including entries out of
  ``remote_id`` order, a duplicate ``remote_id``, an outcome missing the
  field its invariant requires, an invalid ``sha256``, a ``pending`` value
  that escapes its own tree (absolute, or containing a ``..`` segment), a
  ``watermark`` that is not timezone-aware, records a newer
  ``ledger_version`` than this version reads, or names a different
  ``connector`` than the instance now uses -- raises :class:`LedgerError`
  naming the file. fitdocs never overwrites or rebuilds a ledger it could
  not read (Req 7.6).
* **Sorted, atomic, and write-if-different.** :func:`save_ledger` always
  serializes ``entries`` sorted by ``remote_id`` -- regardless of the order
  they were built in -- writes no clock-derived value, creates
  ``.fitdocs/connectors/`` on demand, writes through
  :func:`fitdocs.connectors._atomic.write_atomic`, and skips the write
  entirely -- returning ``False`` -- when the serialized bytes already match
  what is on disk, so a pull that changes nothing leaves the ledger
  byte-identical (Req 7.3). Before writing anything, it runs the entries and
  watermark through the same shape check :func:`load_ledger` applies (see
  :func:`_invariant_violation` below), raising :class:`ValueError` and
  writing nothing if the in-memory :class:`Ledger` itself violates an
  invariant -- so :func:`save_ledger` can never write a file
  :func:`load_ledger` would then refuse to read back.
* **The watermark never moves backward.** :meth:`Ledger.with_watermark`
  raises :class:`ValueError` if given a value earlier than the ledger's
  current watermark; the watermark stays absent (``None``) until an
  activity with a start time reaches a final outcome (Req 7.2). This is an
  in-memory invariant of the value itself, not a load-time shape check, so
  it is a plain :class:`ValueError` rather than :class:`LedgerError`.

:class:`Ledger` and :class:`LedgerEntry` are immutable; :meth:`Ledger.with_entry`,
:meth:`Ledger.without`, and :meth:`Ledger.with_watermark` return copies
rather than mutating in place. Neither dataclass's constructor validates its
own invariants (see :class:`LedgerEntry`'s docstring) -- :func:`load_ledger`
and :func:`save_ledger` are the two places those invariants are enforced,
through the single shared :func:`_invariant_violation` check.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

import tomli_w

from fitdocs.connectors._atomic import write_atomic
from fitdocs.layout import connector_ledger_path

__all__ = [
    "LEDGER_VERSION",
    "Outcome",
    "LedgerEntry",
    "Ledger",
    "LedgerError",
    "load_ledger",
    "save_ledger",
]

LEDGER_VERSION: Final[int] = 1
"""Stamped into ``ledger_version`` on every save so format changes are
detectable; :func:`load_ledger` refuses a file recording a newer value
(Req 7.6)."""

_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
"""The archive's own content-hash form: 64 lowercase hex characters (Req 7.8)."""


class Outcome(StrEnum):
    """The three final outcomes a ledger entry can record (Req 7.1)."""

    DELIVERED = "delivered"
    ALREADY_HELD = "already-held"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class LedgerEntry:
    """One remote activity's final outcome, identified by ``remote_id``.

    ``sha256`` is required when ``outcome`` is :attr:`Outcome.DELIVERED` or
    :attr:`Outcome.ALREADY_HELD`, and -- whenever present, for any outcome --
    must be the archive's own naming (``fit-archive/<sha256>.fit``, 64
    lowercase hex characters, Req 7.8); it is present for
    :attr:`Outcome.SKIPPED` only when bytes were fetched before the skip was
    decided. ``detail`` is required when ``outcome`` is
    :attr:`Outcome.SKIPPED`. ``pending`` -- the inbox-relative delivery
    location -- is only ever set alongside :attr:`Outcome.DELIVERED`, must be
    a relative POSIX path with no ``..`` segment (task 4.1's sweep acts on
    this path against the inbox root, so it must never escape it), and is
    cleared once the sweep resolves the delivery. These invariants are
    enforced by :func:`load_ledger` and :func:`save_ledger` through
    :func:`_invariant_violation`; this dataclass's constructor does not
    check them.
    """

    remote_id: str
    outcome: Outcome
    revision: str | None = None
    sha256: str | None = None
    detail: str | None = None
    pending: str | None = None


@dataclass(frozen=True)
class Ledger:
    """An instance's whole fetched-activity record.

    ``entries`` is kept sorted and unique by ``remote_id`` by every method
    below; the constructor itself performs no validation, so a caller
    assembling one directly (as tests do to pin :func:`save_ledger`'s sort)
    can hand it entries in any order -- :func:`save_ledger` re-sorts before
    writing, and :func:`load_ledger` refuses a file whose entries are not
    already in that order (Req 7.3, 7.6).
    """

    connector_id: str
    watermark: datetime | None
    entries: tuple[LedgerEntry, ...]

    def get(self, remote_id: str) -> LedgerEntry | None:
        """Return the entry for ``remote_id``, or ``None`` if there is none."""
        for entry in self.entries:
            if entry.remote_id == remote_id:
                return entry
        return None

    def is_final(self, remote_id: str, revision: str | None) -> bool:
        """Whether ``remote_id`` already has a final outcome at ``revision``.

        ``True`` only when an entry exists for ``remote_id`` and its
        ``revision`` equals the given one -- ``None`` equals ``None``, and
        never equals a string (Req 7.7).
        """
        entry = self.get(remote_id)
        return entry is not None and entry.revision == revision

    def with_entry(self, entry: LedgerEntry) -> Ledger:
        """Return a copy with ``entry`` added or replacing any entry sharing its id.

        This instance is never mutated. The result's ``entries`` remain
        sorted by ``remote_id``.
        """
        remaining = [e for e in self.entries if e.remote_id != entry.remote_id]
        remaining.append(entry)
        remaining.sort(key=lambda e: e.remote_id)
        return Ledger(
            connector_id=self.connector_id,
            watermark=self.watermark,
            entries=tuple(remaining),
        )

    def without(self, remote_id: str) -> Ledger:
        """Return a copy with the entry for ``remote_id`` removed.

        A ``remote_id`` with no matching entry leaves the entries unchanged
        (still a fresh copy). This instance is never mutated.
        """
        remaining = tuple(e for e in self.entries if e.remote_id != remote_id)
        return Ledger(
            connector_id=self.connector_id, watermark=self.watermark, entries=remaining
        )

    def with_watermark(self, watermark: datetime) -> Ledger:
        """Return a copy with the watermark advanced to ``watermark``.

        Raises :class:`ValueError` if ``watermark`` is earlier than this
        ledger's current watermark -- the watermark never moves backward
        (Req 7.2). A ledger with no watermark yet accepts any value.
        """
        if self.watermark is not None and watermark < self.watermark:
            raise ValueError(
                f"watermark cannot move backward: {watermark!r} is earlier than "
                f"the current watermark {self.watermark!r}"
            )
        return Ledger(
            connector_id=self.connector_id, watermark=watermark, entries=self.entries
        )

    def pending_entries(self) -> tuple[LedgerEntry, ...]:
        """The entries still awaiting the sweep -- those with a ``pending`` location."""
        return tuple(e for e in self.entries if e.pending is not None)


class LedgerError(Exception):
    """A ledger file exists but cannot be read or is not in its documented shape.

    Raised by :func:`load_ledger` when the path exists but is not a regular
    file, cannot be read (any ``OSError``), is not parseable TOML, is not in
    the documented shape (a missing or mistyped field, entries out of
    ``remote_id`` order, a duplicate ``remote_id``, an entry or watermark
    violating one of :func:`_invariant_violation`'s checks), records a
    ``ledger_version`` newer than :data:`LEDGER_VERSION`, or names a
    ``connector`` other than the one the instance now uses. The message
    always names the file. An *absent* path is never an error -- it yields
    an empty :class:`Ledger` instead (Req 7.5, 7.6).
    """


def _is_safe_relative_path(value: str) -> bool:
    """Whether ``value`` is a relative POSIX path that never escapes its root.

    Every ``/``-separated segment must be non-empty and neither ``.`` nor
    ``..``: this rejects an empty string, an absolute path (leading ``/``), a
    trailing ``/`` or ``/.`` (which name a directory, not a delivered file),
    and any escape -- task 4.1's sweep resolves ``pending`` against the inbox
    root, so an unsafe value here could otherwise reach outside it.
    """
    return all(segment not in ("", ".", "..") for segment in value.split("/"))


def _invariant_violation(
    watermark: datetime | None, entries: tuple[LedgerEntry, ...]
) -> str | None:
    """Return the first invariant violation in ``watermark``/``entries``, or ``None``.

    The single check shared by :func:`load_ledger` (which raises
    :class:`LedgerError` naming the file) and :func:`save_ledger` (which
    raises :class:`ValueError` before writing anything) -- so a ledger
    :func:`save_ledger` accepts is always one :func:`load_ledger` accepts
    back. Checks, in order: ``watermark`` is timezone-aware when present;
    entries are unique by ``remote_id``; ``sha256`` is present (and 64
    lowercase hex) when ``outcome`` is ``delivered`` or ``already-held``, and
    is 64 lowercase hex whenever present at all; ``detail`` is present when
    ``outcome`` is ``skipped``; ``pending`` is present only when ``outcome``
    is ``delivered``, and is a safe relative path (see
    :func:`_is_safe_relative_path`).
    """
    if watermark is not None and watermark.tzinfo is None:
        return "'watermark' must be timezone-aware"

    seen: set[str] = set()
    for entry in entries:
        if entry.remote_id in seen:
            return f"duplicate entry for remote_id {entry.remote_id!r}"
        seen.add(entry.remote_id)

        if (
            entry.outcome in (Outcome.DELIVERED, Outcome.ALREADY_HELD)
            and entry.sha256 is None
        ):
            return (
                f"entry {entry.remote_id!r} has outcome {entry.outcome.value!r} "
                "but no 'sha256'"
            )
        if entry.sha256 is not None and not _SHA256_RE.fullmatch(entry.sha256):
            return f"entry {entry.remote_id!r} has an invalid 'sha256' {entry.sha256!r}"
        if entry.outcome is Outcome.SKIPPED and entry.detail is None:
            return f"entry {entry.remote_id!r} is 'skipped' but has no 'detail'"
        if entry.pending is not None:
            if entry.outcome is not Outcome.DELIVERED:
                return (
                    f"entry {entry.remote_id!r} has 'pending' but outcome "
                    f"{entry.outcome.value!r} is not 'delivered'"
                )
            if not _is_safe_relative_path(entry.pending):
                return (
                    f"entry {entry.remote_id!r} has an unsafe 'pending' path "
                    f"{entry.pending!r}"
                )
    return None


def load_ledger(data_root: Path, instance: str, *, connector_id: str) -> Ledger:
    """Read ``<data_root>/.fitdocs/connectors/<instance>.toml`` into a :class:`Ledger`.

    An absent path yields an empty ledger for ``connector_id`` and creates
    nothing (Req 7.5). A path that exists but is not a regular file (for
    example a directory) is never treated as absent -- it raises
    :class:`LedgerError` naming the file, the same as every other shape
    violation (Req 7.6), and fitdocs never overwrites or rebuilds it.
    """
    path = connector_ledger_path(data_root, instance)
    if not path.exists():
        return Ledger(connector_id=connector_id, watermark=None, entries=())
    if not path.is_file():
        raise LedgerError(f"{path} is not a regular file")

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise LedgerError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise LedgerError(f"{path} could not be read: {exc}") from exc

    version = data.get("ledger_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise LedgerError(
            f"{path}: 'ledger_version' must be an integer, got {version!r}"
        )
    if version > LEDGER_VERSION:
        raise LedgerError(
            f"{path} records ledger format {version}, newer than the "
            f"{LEDGER_VERSION} this version of fitdocs reads"
        )

    found_connector = data.get("connector")
    if not isinstance(found_connector, str):
        raise LedgerError(
            f"{path}: 'connector' must be a string, got {found_connector!r}"
        )
    if found_connector != connector_id:
        raise LedgerError(
            f"{path} belongs to connector {found_connector!r}, not {connector_id!r}"
        )

    watermark = data.get("watermark")
    if watermark is not None and not isinstance(watermark, datetime):
        raise LedgerError(f"{path}: 'watermark' must be a datetime, got {watermark!r}")

    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise LedgerError(f"{path}: 'entries' must be a list, got {raw_entries!r}")

    entries: list[LedgerEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise LedgerError(f"{path}: each entry must be a table, got {raw!r}")
        entries.append(_parse_entry(path, raw))

    remote_ids = [e.remote_id for e in entries]
    if remote_ids != sorted(remote_ids):
        raise LedgerError(f"{path}: entries are not sorted by remote_id")

    violation = _invariant_violation(watermark, tuple(entries))
    if violation is not None:
        raise LedgerError(f"{path}: {violation}")

    return Ledger(
        connector_id=found_connector, watermark=watermark, entries=tuple(entries)
    )


def _parse_entry(path: Path, raw: dict[str, object]) -> LedgerEntry:
    """Validate the *shape* of one raw TOML table and build a :class:`LedgerEntry`.

    Checks only field presence and type: ``remote_id`` is a required string;
    ``outcome`` is a required string naming one of :class:`Outcome`'s
    values; ``revision``, ``sha256``, ``detail``, and ``pending`` are
    optional strings when present. Cross-field invariants (``sha256``
    required for some outcomes, ``sha256`` format, ``detail`` required for
    ``skipped``, ``pending`` restrictions) are checked once, afterwards, by
    :func:`_invariant_violation` -- not here. Any shape violation raises
    :class:`LedgerError` naming ``path``.
    """
    remote_id = raw.get("remote_id")
    if not isinstance(remote_id, str):
        raise LedgerError(
            f"{path}: entry 'remote_id' must be a string, got {remote_id!r}"
        )

    raw_outcome = raw.get("outcome")
    if not isinstance(raw_outcome, str):
        raise LedgerError(
            f"{path}: entry {remote_id!r} has invalid 'outcome' {raw_outcome!r}"
        )
    try:
        outcome = Outcome(raw_outcome)
    except ValueError:
        raise LedgerError(
            f"{path}: entry {remote_id!r} has invalid 'outcome' {raw_outcome!r}"
        ) from None

    def _optional_str(key: str) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise LedgerError(
                f"{path}: entry {remote_id!r} has non-string {key!r}: {value!r}"
            )
        return value

    return LedgerEntry(
        remote_id=remote_id,
        outcome=outcome,
        revision=_optional_str("revision"),
        sha256=_optional_str("sha256"),
        detail=_optional_str("detail"),
        pending=_optional_str("pending"),
    )


def save_ledger(data_root: Path, instance: str, ledger: Ledger) -> bool:
    """Persist ``ledger`` atomically to
    ``<data_root>/.fitdocs/connectors/<instance>.toml``.

    Raises :class:`ValueError` and writes nothing if ``ledger`` itself
    violates an invariant :func:`_invariant_violation` checks -- the same
    check :func:`load_ledger` applies, so a ledger this function accepts is
    always one :func:`load_ledger` accepts back.

    Otherwise creates ``.fitdocs/connectors/`` on demand if it does not
    already exist -- unlike :func:`load_ledger`, which never creates it.
    ``ledger_version`` is stamped to :data:`LEDGER_VERSION`. Entries are
    serialized sorted by ``remote_id`` regardless of ``ledger.entries``' own
    order, and no clock-derived value is written, so an unchanged ledger
    serializes to identical bytes on every save.

    If the target file already exists and already holds those exact bytes,
    nothing is written and ``False`` is returned. Otherwise the document is
    written through :func:`fitdocs.connectors._atomic.write_atomic` and
    ``True`` is returned (Req 7.3).
    """
    violation = _invariant_violation(ledger.watermark, ledger.entries)
    if violation is not None:
        raise ValueError(violation)

    target = connector_ledger_path(data_root, instance)
    document: dict[str, object] = {
        "ledger_version": LEDGER_VERSION,
        "connector": ledger.connector_id,
    }
    if ledger.watermark is not None:
        document["watermark"] = ledger.watermark

    entry_tables: list[dict[str, object]] = []
    for entry in sorted(ledger.entries, key=lambda e: e.remote_id):
        table: dict[str, object] = {"remote_id": entry.remote_id}
        if entry.revision is not None:
            table["revision"] = entry.revision
        table["outcome"] = entry.outcome.value
        if entry.sha256 is not None:
            table["sha256"] = entry.sha256
        if entry.detail is not None:
            table["detail"] = entry.detail
        if entry.pending is not None:
            table["pending"] = entry.pending
        entry_tables.append(table)
    document["entries"] = entry_tables

    payload = tomli_w.dumps(document).encode("utf-8")

    if target.is_file() and target.read_bytes() == payload:
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(target, payload, prefix=instance)
    return True
