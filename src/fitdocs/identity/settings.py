"""The reader for the ``fitdocs.toml`` ``[identity]`` table (Req 2.5-2.7).

Peer of the other per-table readers: it receives the mapping
:func:`fitdocs.settings.load_settings_document` already parsed and never opens
a file. Unknown keys in the table are ignored, because the file is shared.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.identity.kinds import DEVELOPMENT_MANUFACTURER, SourceKind
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    Precedence,
    PrecedenceEntry,
    resolve_precedence,
)
from fitdocs.settings import SettingsError

__all__ = [
    "IDENTITY_TABLE",
    "PRECEDENCE_KEY",
    "IdentitySettings",
    "IdentitySettingsError",
    "load_identity_settings",
]

IDENTITY_TABLE: Final[str] = "identity"
PRECEDENCE_KEY: Final[str] = "precedence"

_ORIGINAL_PREFIX: Final[str] = f"{SourceKind.ORIGINAL.value}:"
_KINDS: Final[tuple[str, ...]] = tuple(kind.value for kind in SourceKind)


@dataclass(frozen=True)
class IdentitySettings:
    """The resolved ``[identity]`` configuration."""

    precedence: Precedence = DEFAULT_PRECEDENCE


class IdentitySettingsError(SettingsError):
    """The ``[identity]`` table exists but is not valid configuration."""


def load_identity_settings(
    document: Mapping[str, object], settings_file: Path
) -> IdentitySettings:
    """Project the ``[identity]`` table of an already-parsed settings document.

    An absent table or key yields the default precedence; a configured list is
    completed by :func:`~fitdocs.identity.roles.resolve_precedence`.
    """
    where = f"{settings_file}: [{IDENTITY_TABLE}] {PRECEDENCE_KEY}"
    if IDENTITY_TABLE not in document:
        return IdentitySettings()
    table = document[IDENTITY_TABLE]
    if not isinstance(table, dict):
        raise IdentitySettingsError(
            f"{settings_file}: [{IDENTITY_TABLE}] must be a table, "
            f"got {table!r} ({type(table).__name__})"
        )
    if PRECEDENCE_KEY not in table:
        return IdentitySettings()
    raw = table[PRECEDENCE_KEY]
    if not isinstance(raw, list):
        raise IdentitySettingsError(
            f"{where} must be a list of strings, got {raw!r} ({type(raw).__name__})"
        )
    seen: set[str] = set()
    entries: list[PrecedenceEntry] = []
    for item in raw:
        if not isinstance(item, str):
            raise IdentitySettingsError(
                f"{where} must be a list of strings, "
                f"got element {item!r} ({type(item).__name__})"
            )
        if item in seen:
            raise IdentitySettingsError(f"{where} lists {item!r} twice")
        seen.add(item)
        entries.append(_entry(item, where))
    return IdentitySettings(precedence=resolve_precedence(entries))


def _entry(text: str, where: str) -> PrecedenceEntry:
    if text in _KINDS:
        return PrecedenceEntry(SourceKind(text))
    if text.startswith(_ORIGINAL_PREFIX):
        manufacturer = text[len(_ORIGINAL_PREFIX) :]
        if not manufacturer:
            raise IdentitySettingsError(
                f"{where}: {text!r} names no manufacturer after 'original:'"
            )
        if manufacturer == DEVELOPMENT_MANUFACTURER:
            raise IdentitySettingsError(
                f"{where}: {text!r} is not allowed; "
                f"{DEVELOPMENT_MANUFACTURER!r} marks a phone copy, use 'phone_copy'"
            )
        return PrecedenceEntry(SourceKind.ORIGINAL, manufacturer)
    raise IdentitySettingsError(
        f"{where}: {text!r} is neither a kind ({', '.join(_KINDS)}) "
        "nor 'original:<manufacturer>'"
    )
