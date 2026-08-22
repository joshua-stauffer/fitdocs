"""The one reader for the ``fitdocs.toml`` ``[load]`` table (design: LoadSettings).

This module owns the *entire* ``[load]`` table and every sub-table beneath it
(Req 14.1, Amendment 3 to the training-load spec). Its surface is contractual
-- four sibling specs (``athlete-benchmarks``, ``load-channels``,
``threshold-load``, ``activity-qa-flags``) each extend the one
:class:`LoadSettings` dataclass and its one :func:`load_load_settings` reader
rather than defining a second one. **No second reader of ``[load]`` may exist
anywhere in the tool.**

This reader never opens, reads, or parses a file itself.
``fitdocs.settings.load_settings_document`` locates, reads, and parses
``<data-root>/fitdocs.toml`` exactly once per invocation, raising the shared
:class:`~fitdocs.settings.SettingsError` for file-level problems (an
unreadable file, invalid TOML). This module receives only the mapping that
reader already produced and validates just its own ``[load]`` table, exactly
as :func:`fitdocs.plugins.load_plugin_settings` does for ``[plugins]``.

Two invariants shape the reader:

* **Every field is defaulted** (Req 14.2). Constructing :class:`LoadSettings`
  with no arguments always yields :data:`DEFAULT_LOAD_SETTINGS`, so a sibling
  spec adding a field breaks no existing construction site. An absent
  settings file or an absent ``[load]`` table is the normal case and resolves
  to :data:`DEFAULT_LOAD_SETTINGS` -- never an error.
* **Unknown keys and unknown sub-tables are ignored** (Req 14.3) -- the
  additivity contract that lets ``[load.sufficiency]`` (``load-channels``),
  ``[load.priority]`` (``threshold-load``) and ``[load.flags]``
  (``activity-qa-flags``) land as their own projections inside this module,
  or as sub-tables an older reader has not learned about yet, without ever
  touching this reader's control flow.

**Import direction (Req 14.7).** This module sits *above*
``fitdocs.load.types``, not below it: three sibling specs deliver their own
configuration as typed sub-settings living in their own ``fitdocs.load.*``
modules (``load/channels/types.py``, ``load/priority.py``,
``load/qa/types.py``), and this reader aggregates them, so it necessarily
imports ``fitdocs.load.*``. None of those sibling modules exist yet in this
checkout; when they land, this module gains an import of each and a
projection of its sub-table, and nothing else about this module's signature
changes. The one edge that must never become a runtime import is
``fitdocs.load.types``'s reference back to :class:`LoadSettings` for
``LoadContext.settings``'s annotation, which stays ``TYPE_CHECKING``-only on
that module's side. This module itself imports nothing from
``fitdocs.load.types`` or any other ``fitdocs.load.*`` module today.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from fitdocs.settings import SettingsError

LOAD_TABLE = "load"

DEFAULT_STALENESS_WINDOW_DAYS: Final[int] = 84
"""12 weeks: the outer end of the researched 8-12 week range, chosen so the
default under-flags rather than over-flags. Configurable per athlete."""


@dataclass(frozen=True)
class LoadSettings:
    """The resolved ``[load]`` configuration for a pass.

    Every field carries a default (Req 14.2), so ``LoadSettings()`` with no
    arguments always equals :data:`DEFAULT_LOAD_SETTINGS`. Sibling specs add
    their own defaulted fields here rather than opening a second settings
    type.
    """

    default_calculator: str | None = None
    benchmark_staleness_days: int = DEFAULT_STALENESS_WINDOW_DAYS


DEFAULT_LOAD_SETTINGS: Final[LoadSettings] = LoadSettings()


class LoadSettingsError(SettingsError):
    """The ``fitdocs.toml`` ``[load]`` table exists but is not valid configuration.

    Raised for a non-table ``load`` value or a non-string/empty
    ``default_calculator`` -- faults that belong to *this table*. An *absent*
    file or ``[load]`` table is never an error -- it yields
    :data:`DEFAULT_LOAD_SETTINGS`. The message names the settings file and the
    offending key so a user can correct the configuration.

    Whether a configured ``default_calculator`` identifier is *registered* is
    deliberately not checked here -- that is an arbitration concern raised by
    the engine (Requirement 10.4).

    This type subclasses the shared :class:`~fitdocs.settings.SettingsError`,
    so the CLI's existing ``except SettingsError`` handler maps it to exit 2
    with no new branch, exactly like a malformed ``[plugins]`` or ``[tiles]``
    table.
    """


def load_load_settings(
    document: Mapping[str, object], settings_file: Path
) -> LoadSettings:
    """Project the ``[load]`` table of an already-parsed settings document.

    The single reader for ``[load]`` and every sub-table beneath it: it
    validates only ``[load]`` and never opens a file -- ``document`` is the
    mapping :func:`~fitdocs.settings.load_settings_document` already returned
    for this invocation (empty when the settings file is absent), and
    ``settings_file`` -- obtained by the caller from
    :func:`fitdocs.layout.settings_path` -- is used only to name the file in
    error messages.

    Returns :data:`DEFAULT_LOAD_SETTINGS` when the file or its ``[load]``
    table is absent. Raises :class:`LoadSettingsError` when the ``[load]``
    table is malformed: a non-table ``load`` value, or a non-string/empty
    ``default_calculator``. Unknown keys inside ``[load]`` and unknown
    sub-tables beneath it are ignored (Req 14.3), because the document is
    shared with ``[tiles]``, ``[inbox]``, ``[plugins]``, and every future
    ``[load.*]`` sub-table a sibling spec adds.
    """
    if LOAD_TABLE not in document:
        return DEFAULT_LOAD_SETTINGS
    table = document[LOAD_TABLE]
    if not isinstance(table, dict):
        raise LoadSettingsError(
            f"{settings_file}: [load] must be a table, "
            f"got {table!r} ({type(table).__name__})"
        )

    return LoadSettings(
        default_calculator=_setting_default_calculator(table, settings_file),
        benchmark_staleness_days=_setting_benchmark_staleness_days(
            table, settings_file
        ),
    )


def _setting_default_calculator(
    table: dict[str, Any], settings_file: Path
) -> str | None:
    """Map the optional ``default_calculator`` key, rejecting non-string/empty."""
    if "default_calculator" not in table:
        return DEFAULT_LOAD_SETTINGS.default_calculator
    value = table["default_calculator"]
    if not isinstance(value, str) or not value:
        raise LoadSettingsError(
            f"{settings_file}: [load] default_calculator must be a non-empty "
            f"string, got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_benchmark_staleness_days(
    table: dict[str, Any], settings_file: Path
) -> int:
    """Map optional ``benchmark_staleness_days``, rejecting non-positive ints."""
    if "benchmark_staleness_days" not in table:
        return DEFAULT_LOAD_SETTINGS.benchmark_staleness_days
    value = table["benchmark_staleness_days"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LoadSettingsError(
            f"{settings_file}: [load] benchmark_staleness_days must be a "
            f"positive whole number of days, got {value!r} "
            f"({type(value).__name__})"
        )
    return value
