"""The quarantine record store: known-bad inbox files, remembered by content.

This module is authoritative for ``<data_root>/.fitdocs/quarantine.toml`` --
the content-keyed record of inbox files that failed processing for a
source-level fault, so a later drain reports them once from the record rather
than re-parsing and re-failing on every scheduled run (Req 5.1, 5.2).

Two invariants shape the contract:

* **Absent is empty, never an error, and reading creates nothing.**
  :func:`load_quarantine` of a data root with no ``.fitdocs/quarantine.toml``
  -- including one with no ``.fitdocs/`` directory at all -- yields an empty
  :class:`QuarantineRecord` and creates neither the file nor the directory
  (Req 5.6). A file that exists but cannot be read (permissions, or any other
  ``OSError``), or that is not parseable TOML, or whose entries are not in
  the documented shape -- including two entries sharing one ``sha256`` --
  raises :class:`QuarantineError` naming the file -- never silently
  discarded or rebuilt (Req 5.6).

* **Content-keyed, atomic, and write-if-different.** Membership and mutation
  are keyed on the sha256 of file content, never on name, so a rename does
  not resurrect a known-bad file and a same-named new file is treated as new
  (Req 5.4). Entries carry no timestamp or other clock-derived value.
  :func:`save_quarantine` writes atomically (a temp file in the target
  directory, then ``os.replace``), creating ``.fitdocs/`` on demand if
  absent, and skips the write entirely -- returning ``False`` -- when the
  serialized bytes are unchanged from what is already on disk, so a re-run
  with no new quarantine activity is byte-identical (Req 7.4). Entries are
  always serialized sorted by sha256 for that same stability.

:class:`QuarantineRecord` and :class:`QuarantineEntry` are immutable;
:meth:`QuarantineRecord.with_entry` and :meth:`QuarantineRecord.without`
return copies rather than mutating in place.
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import tomli_w

from fitdocs.layout import quarantine_path

__all__ = [
    "QUARANTINE_VERSION",
    "QuarantineEntry",
    "QuarantineRecord",
    "QuarantineError",
    "load_quarantine",
    "save_quarantine",
]

QUARANTINE_VERSION: Final[int] = 1
"""Stamped into ``quarantine_version`` on every save so format changes are
detectable."""


class QuarantineError(Exception):
    """The quarantine record file cannot be read or is not in its documented shape.

    Raised when the file exists but cannot be read (an ``OSError`` such as a
    permissions failure), when it is not parseable TOML, or when a present
    ``entries`` value is not a list of tables each carrying string
    ``sha256``, ``name``, and ``reason`` keys with no ``sha256`` repeated.
    The message names the file so the user can correct or remove it. An
    *absent* file is never an error -- it yields an empty record instead
    (Req 5.6).
    """


@dataclass(frozen=True)
class QuarantineEntry:
    """One quarantined file, identified by content rather than name.

    ``sha256`` is the content identity -- the same hash the archive is keyed
    by (Req 5.4). ``name`` is the inbox-relative name as last seen, kept only
    as a human-readable report label. ``reason`` is the failure reason
    recorded at quarantine time. No timestamp or other clock-derived value is
    carried.
    """

    sha256: str
    name: str
    reason: str


@dataclass(frozen=True)
class QuarantineRecord:
    """An immutable, content-keyed collection of :class:`QuarantineEntry`.

    :func:`load_quarantine`, :meth:`with_entry`, and :meth:`without` all
    produce ``entries`` sorted and unique by ``sha256``, and
    :func:`save_quarantine` re-sorts defensively before writing -- but the
    constructor itself performs no validation, so a caller can build a
    :class:`QuarantineRecord` directly with out-of-order or duplicate
    entries. :meth:`with_entry` and :meth:`without` return new instances
    rather than mutating this one.
    """

    entries: tuple[QuarantineEntry, ...]

    def get(self, sha256: str) -> QuarantineEntry | None:
        """Return the entry whose content identity is ``sha256``, or ``None``.

        Lookup is by content hash only -- never by name (Req 5.4).
        """
        for entry in self.entries:
            if entry.sha256 == sha256:
                return entry
        return None

    def with_entry(self, entry: QuarantineEntry) -> QuarantineRecord:
        """Return a copy of this record with ``entry`` added or replaced.

        Any existing entry sharing ``entry.sha256`` is replaced; this
        instance is never mutated. The result's ``entries`` remain sorted by
        ``sha256``.
        """
        remaining = [e for e in self.entries if e.sha256 != entry.sha256]
        remaining.append(entry)
        remaining.sort(key=lambda e: e.sha256)
        return QuarantineRecord(entries=tuple(remaining))

    def without(self, sha256: str) -> QuarantineRecord:
        """Return a copy of this record with the entry for ``sha256`` removed.

        A ``sha256`` with no matching entry leaves the record unchanged
        (still a fresh copy). This instance is never mutated.
        """
        remaining = tuple(e for e in self.entries if e.sha256 != sha256)
        return QuarantineRecord(entries=remaining)


def load_quarantine(data_root: Path) -> QuarantineRecord:
    """Read ``<data_root>/.fitdocs/quarantine.toml`` into a :class:`QuarantineRecord`.

    An absent file -- including a data root with no ``.fitdocs/`` directory
    at all -- yields an empty record and creates nothing (Req 5.6). A file
    that exists but cannot be read (any ``OSError``, such as a permissions
    failure), that is not valid TOML, or whose ``entries`` are not in the
    documented shape (not a list, an entry not a table, an entry missing or
    mistyped ``sha256``/``name``/``reason``, or two entries sharing one
    ``sha256``), raises :class:`QuarantineError` naming the file (Req 5.6).
    """
    path = quarantine_path(data_root)
    if not path.is_file():
        return QuarantineRecord(entries=())

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise QuarantineError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise QuarantineError(f"{path} could not be read: {exc}") from exc

    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise QuarantineError(f"{path}: 'entries' must be a list, got {raw_entries!r}")

    entries: list[QuarantineEntry] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise QuarantineError(f"{path}: each entry must be a table, got {raw!r}")
        entry = _parse_entry(path, raw)
        if entry.sha256 in seen:
            raise QuarantineError(
                f"{path}: duplicate entry for sha256 {entry.sha256!r}"
            )
        seen.add(entry.sha256)
        entries.append(entry)

    entries.sort(key=lambda e: e.sha256)
    return QuarantineRecord(entries=tuple(entries))


def _parse_entry(path: Path, raw: dict[str, object]) -> QuarantineEntry:
    """Validate and build one :class:`QuarantineEntry` from a raw TOML table.

    Each of ``sha256``, ``name``, and ``reason`` must be present and a
    ``str``; any violation raises :class:`QuarantineError` naming ``path``
    (Req 5.6).
    """
    values: dict[str, str] = {}
    for key in ("sha256", "name", "reason"):
        value = raw.get(key)
        if not isinstance(value, str):
            raise QuarantineError(
                f"{path}: entry {key!r} must be a string, got {value!r}"
            )
        values[key] = value
    return QuarantineEntry(
        sha256=values["sha256"], name=values["name"], reason=values["reason"]
    )


def save_quarantine(data_root: Path, record: QuarantineRecord) -> bool:
    """Persist ``record`` to ``<data_root>/.fitdocs/quarantine.toml`` atomically.

    Creates the tool-state directory (``.fitdocs/``) on demand if it does not
    already exist -- unlike :func:`load_quarantine`, which never creates it.
    ``quarantine_version`` is stamped to :data:`QUARANTINE_VERSION`. Entries
    are serialized sorted by ``sha256`` and carry no clock-derived value, so
    an unchanged record serializes to identical bytes on every save.

    If the target file already exists and already holds those exact bytes,
    nothing is written and ``False`` is returned. Otherwise the document is
    written to a temporary file in the same directory, then :func:`os.replace`
    renames it over the target atomically, and ``True`` is returned. The
    temporary file is removed if anything fails, so no partial or ``.tmp``
    file is ever left behind (Req 7.4).
    """
    target = quarantine_path(data_root)
    document: dict[str, object] = {
        "quarantine_version": QUARANTINE_VERSION,
        "entries": [
            {"sha256": e.sha256, "name": e.name, "reason": e.reason}
            for e in sorted(record.entries, key=lambda e: e.sha256)
        ],
    }
    payload = tomli_w.dumps(document).encode("utf-8")

    if target.is_file() and target.read_bytes() == payload:
        return False

    tool_state_dir = target.parent
    tool_state_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=tool_state_dir, prefix=".quarantine-", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return True
