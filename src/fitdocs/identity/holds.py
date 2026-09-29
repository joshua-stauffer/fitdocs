"""The hold record: archived files that no page lists, remembered by content.

Authoritative for ``<data_root>/.fitdocs/held.toml`` (path from
:func:`fitdocs.layout.held_path`). A file whose identity match is ambiguous is
archived and *held*; the record names it so ``check`` can report it and a later
run can re-evaluate it (Req 4.7, 4.10, 8.4).

* **Absent is empty and reading creates nothing.** :func:`load_holds` of a data
  root with no record -- including one with no ``.fitdocs/`` directory --
  returns an empty :class:`HoldRecord` and creates neither. A record that
  cannot be read, is not valid TOML, or is not in the documented shape (a
  repeated ``sha256`` included) raises :class:`HoldRecordError` naming the file.
* **Atomic and write-if-different.** :func:`save_holds` writes a temp file in
  ``.fitdocs/`` then replaces the target, creating the directory on demand, and
  writes nothing (returning ``False``) when the serialized bytes equal what is
  on disk. Entries are serialized sorted by ``sha256`` and carry no
  clock-derived value.

The temp-file-then-replace idiom is another private copy; see the queue item
``2026-09-15-atomic-write-helper-copied-per-engine``.
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import tomli_w

from fitdocs.layout import held_path

__all__ = [
    "HELD_VERSION",
    "HeldSource",
    "HoldRecord",
    "HoldRecordError",
    "load_holds",
    "save_holds",
]

HELD_VERSION: Final[int] = 1
"""Written to ``held_version`` on every save."""

_STRING_KEYS: Final[tuple[str, ...]] = ("sha256", "name")
_STRING_LIST_KEYS: Final[tuple[str, ...]] = ("candidates", "evidence")


class HoldRecordError(Exception):
    """The hold record cannot be read or is not in its documented shape.

    The message names the file. An absent file is never an error.
    """


@dataclass(frozen=True)
class HeldSource:
    """One held file, identified by the sha256 of its content.

    ``name`` is the label the file arrived under (or its archive ref),
    ``candidates`` the data-root-relative page paths it could belong to, and
    ``evidence`` the tier names of the matches.
    """

    sha256: str
    name: str
    candidates: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class HoldRecord:
    """An immutable collection of :class:`HeldSource`, unique by ``sha256``."""

    entries: tuple[HeldSource, ...]

    def get(self, sha256: str) -> HeldSource | None:
        """The entry for ``sha256``, or ``None``."""
        for entry in self.entries:
            if entry.sha256 == sha256:
                return entry
        return None

    def with_entry(self, entry: HeldSource) -> HoldRecord:
        """A copy with ``entry`` added, replacing any entry sharing its ``sha256``."""
        remaining = [e for e in self.entries if e.sha256 != entry.sha256]
        remaining.append(entry)
        remaining.sort(key=lambda e: e.sha256)
        return HoldRecord(entries=tuple(remaining))

    def without(self, sha256: str) -> HoldRecord:
        """A copy with the entry for ``sha256`` removed (unchanged if absent)."""
        return HoldRecord(entries=tuple(e for e in self.entries if e.sha256 != sha256))


def load_holds(data_root: Path) -> HoldRecord:
    """Read the hold record; absent is empty and creates nothing.

    Raises :class:`HoldRecordError` naming the file when it cannot be read, is
    not valid TOML, has an unsupported ``held_version``, has ``held`` that is not
    a list of tables, has an entry with a missing or mistyped key, or repeats a
    ``sha256``.
    """
    path = held_path(data_root)
    if not path.is_file():
        return HoldRecord(entries=())

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise HoldRecordError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise HoldRecordError(f"{path} could not be read: {exc}") from exc

    version = data.get("held_version", HELD_VERSION)
    if isinstance(version, bool) or version != HELD_VERSION:
        raise HoldRecordError(
            f"{path}: 'held_version' must be {HELD_VERSION}, got {version!r}"
        )

    raw_entries = data.get("held", [])
    if not isinstance(raw_entries, list):
        raise HoldRecordError(f"{path}: 'held' must be a list, got {raw_entries!r}")

    entries: list[HeldSource] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise HoldRecordError(f"{path}: each entry must be a table, got {raw!r}")
        entry = _parse_entry(path, raw)
        if entry.sha256 in seen:
            raise HoldRecordError(
                f"{path}: duplicate entry for sha256 {entry.sha256!r}"
            )
        seen.add(entry.sha256)
        entries.append(entry)

    entries.sort(key=lambda e: e.sha256)
    return HoldRecord(entries=tuple(entries))


def _parse_entry(path: Path, raw: dict[str, object]) -> HeldSource:
    strings: dict[str, str] = {}
    for key in _STRING_KEYS:
        value = raw.get(key)
        if not isinstance(value, str):
            raise HoldRecordError(
                f"{path}: entry {key!r} must be a string, got {value!r}"
            )
        strings[key] = value
    lists: dict[str, tuple[str, ...]] = {}
    for key in _STRING_LIST_KEYS:
        value = raw.get(key)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HoldRecordError(
                f"{path}: entry {key!r} must be a list of strings, got {value!r}"
            )
        lists[key] = tuple(value)
    return HeldSource(
        sha256=strings["sha256"],
        name=strings["name"],
        candidates=lists["candidates"],
        evidence=lists["evidence"],
    )


def save_holds(data_root: Path, record: HoldRecord) -> bool:
    """Persist ``record``; return ``False`` and write nothing when unchanged.

    Creates ``.fitdocs/`` on demand. The write goes to a temp file in that
    directory and is then renamed over the target; the temp file is removed if
    anything fails.
    """
    target = held_path(data_root)
    document: dict[str, object] = {
        "held_version": HELD_VERSION,
        "held": [
            {
                "sha256": e.sha256,
                "name": e.name,
                "candidates": list(e.candidates),
                "evidence": list(e.evidence),
            }
            for e in sorted(record.entries, key=lambda e: e.sha256)
        ],
    }
    payload = tomli_w.dumps(document).encode("utf-8")

    if target.is_file() and target.read_bytes() == payload:
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".held-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return True
