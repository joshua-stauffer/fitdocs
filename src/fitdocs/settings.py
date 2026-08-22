"""The one read of the user-owned settings file (design: SharedSettings).

``<data-root>/fitdocs.toml`` is shared: ``[tiles]`` lives there today, ``[inbox]``
and ``[plugins]`` join it. This module locates, reads, and parses that file
**once per invocation** and hands the resulting mapping to the per-table readers,
each of which validates only its own table.

Two rules make the split work:

* **One file-level voice.** A settings file that cannot be read or is not valid
  TOML is a property of the *file*, not of any table in it, so it raises
  :class:`SettingsError` here. A per-table reader never opens the file and so can
  never disagree about whether it parsed -- without this, a user with a stray
  bracket would get whichever table's message happened to run first.
* **Absent is not an error.** No settings file means no configuration, which is
  the normal case: :func:`load_settings_document` returns an empty mapping and
  every table reader falls back to its documented defaults. Raising here would
  make an optional file mandatory and break the keyless first run.

Table-level problems (a wrong-typed value, a scalar where a table belongs) stay
with the table's own reader and its own error type; those types subclass
:class:`SettingsError` so a caller that wants "any settings problem" can catch
one thing and exit ``2`` before anything is written.

The module is read-only by construction: it opens the file for reading and never
writes, creates, or prompts.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path

from fitdocs.layout import settings_path


class SettingsError(Exception):
    """The settings file exists but cannot be read or parsed.

    Raised for an unreadable file and for invalid TOML -- faults that belong to
    the file as a whole. The message names the file so the user can find it. An
    *absent* file is never an error (see :func:`load_settings_document`).

    Per-table error types subclass this, so ``except SettingsError`` catches both
    file-level and table-level configuration problems at a CLI boundary.
    """


def load_settings_document(data_root: Path) -> Mapping[str, object]:
    """Read and parse ``<data_root>/fitdocs.toml`` once; return its tables.

    Returns the parsed top-level mapping, or an **empty mapping** when the file
    is absent -- the keyless default case, never an error. Callers pass the
    result to each per-table reader (``[tiles]``, ``[inbox]``, ``[plugins]``), so
    the file is read once no matter how many tables an invocation consults.

    Raises :class:`SettingsError` when the file exists but cannot be read or is
    not valid TOML. Nothing is written, created, or prompted for.
    """
    path = settings_path(data_root)
    if not path.is_file():
        return {}

    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise SettingsError(f"{path} could not be read: {exc}") from exc
