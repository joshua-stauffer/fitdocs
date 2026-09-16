"""The one reader for the ``fitdocs.toml`` ``[plans]`` table, and the
plan-source directory's lexical resolution (design: "PlanSettings
(`src/fitdocs/plans/settings.py`)"; Req 1.8, 1.9, 8.3).

Peer of :func:`fitdocs.history.settings.load_history_settings`,
:func:`fitdocs.load.settings.load_load_settings`,
:func:`fitdocs.tiles.tile_settings_from_document`,
:func:`fitdocs.inbox.load_inbox_settings` and
:func:`fitdocs.plugins.load_plugin_settings`: :func:`load_plan_settings`
receives the mapping :func:`fitdocs.settings.load_settings_document`
already parsed for this invocation and validates only its own ``[plans]``
table. It never opens, reads or parses a file itself, and unknown keys
inside ``[plans]`` are ignored, because the file is shared with every other
table.

``path`` is the only field: a non-empty string, or absent. An absent
``path`` is kept as ``None`` -- it means "unconfigured", never the default
directory name baked into the settings value itself; the default
(:data:`~fitdocs.layout.DEFAULT_PLANS_DIR`) is applied only by
:func:`resolve_plans_dir`, so a caller that only wants to know *whether* a
path was configured can still tell (Req 1.8).

:func:`resolve_plans_dir` is purely lexical: an absolute ``path`` is used as
given, a relative one resolves against the data root, and the join is
normalized with :func:`os.path.normpath` -- no filesystem access, so a
containment violation is reachable before any I/O, matching
:func:`fitdocs.inbox._resolve_inbox_relative`. It raises
:class:`PlanSettingsError` -- naming the settings file, the ``[plans] path``
key and the resolved path -- when the resolved directory *is* the data root
itself, or lies inside any of :data:`fitdocs.layout.OWNED_PATHS`'s prefixes
(compared by path component, never by string prefix, so a directory whose
name merely starts with an owned name, e.g. ``blocks-mine``, is accepted).
Existence is **not** checked here: whether an absent directory is an error
depends on whether ``path`` was configured at all, and only the engine that
also knows that can decide it (Req 1.10 -- not this module's).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.layout import DEFAULT_PLANS_DIR, OWNED_PATHS
from fitdocs.settings import SettingsError

PLANS_TABLE: Final[str] = "plans"
"""The ``fitdocs.toml`` table this reader validates: ``[plans]``."""


@dataclass(frozen=True)
class PlanSettings:
    """Validated ``[plans]`` configuration (design: PlanSettings).

    ``path`` is ``None`` when unconfigured -- :func:`resolve_plans_dir`
    applies :data:`~fitdocs.layout.DEFAULT_PLANS_DIR` in that case, never
    this dataclass. A configured value is kept verbatim, exactly as the
    athlete wrote it, whether relative or absolute.
    """

    path: str | None = None


DEFAULT_PLAN_SETTINGS: Final[PlanSettings] = PlanSettings()
"""The all-defaults :class:`PlanSettings`, used when ``fitdocs.toml`` or its
``[plans]`` table is absent (Req 1.8)."""


class PlanSettingsError(SettingsError):
    """The ``fitdocs.toml`` ``[plans]`` table exists but is not valid
    configuration, or the configured (or default) plan-source directory
    resolves somewhere fitdocs may not read a plan source from.

    Raised by :func:`load_plan_settings` for a non-table ``plans`` value or
    a ``path`` that is not a non-empty string -- including a boolean, which
    is rejected by the plain ``isinstance(value, str)`` check alone
    (``bool`` is not a ``str`` subclass in Python, unlike the numeric
    ``[history]`` fields in :mod:`fitdocs.history.settings`, where ``bool``
    *is* an ``int`` subclass and an explicit exclusion is load-bearing; no
    such exclusion is needed, or present, here). Raised by
    :func:`resolve_plans_dir` when the resolved directory is the data root
    itself or lies inside a fitdocs-owned path (Req 1.9): fitdocs may
    delete owned paths wholesale, and a plan source there would not be
    safe.

    This type subclasses the shared
    :class:`~fitdocs.settings.SettingsError`, so the CLI's existing
    ``except SettingsError`` handler maps it to the configuration exit with
    no new branch (Req 8.3).
    """


def load_plan_settings(
    document: Mapping[str, object], settings_file: Path
) -> PlanSettings:
    """Project the ``[plans]`` table of an already-parsed settings document.

    ``document`` is the mapping
    :func:`~fitdocs.settings.load_settings_document` already returned for
    this invocation (empty when the settings file is absent); this reader
    never opens a file itself. ``settings_file`` is used only to name the
    file in error messages.

    Returns :data:`DEFAULT_PLAN_SETTINGS`, by identity, when the file or its
    ``[plans]`` table is absent or present-but-empty (Req 1.8). Raises
    :class:`PlanSettingsError` when the table is malformed. Unknown keys
    inside ``[plans]`` are ignored, because the document is shared with
    ``[tiles]``, ``[inbox]``, ``[plugins]``, ``[load]`` and ``[history]``.
    """
    if PLANS_TABLE not in document:
        return DEFAULT_PLAN_SETTINGS
    table = document[PLANS_TABLE]
    if not isinstance(table, dict):
        raise PlanSettingsError(
            f"{settings_file}: [plans] must be a table, "
            f"got {table!r} ({type(table).__name__})"
        )

    if "path" not in table:
        return DEFAULT_PLAN_SETTINGS

    value = table["path"]
    if not isinstance(value, str) or not value:
        raise PlanSettingsError(
            f"{settings_file}: [plans] path must be a non-empty string, "
            f"got {value!r} ({type(value).__name__})"
        )
    return PlanSettings(path=value)


def resolve_plans_dir(
    data_root: Path, settings: PlanSettings, settings_file: Path
) -> Path:
    """Resolve the plan-source directory `settings` names, lexically.

    An absolute ``settings.path`` is used as given; a relative one -- and
    the default, :data:`~fitdocs.layout.DEFAULT_PLANS_DIR`, applied when
    ``settings.path`` is ``None`` -- resolves against `data_root`. The join
    is normalized with :func:`os.path.normpath`; nothing on disk is touched
    and existence is not checked.

    Raises :class:`PlanSettingsError`, naming `settings_file`, the
    ``[plans] path`` key and the resolved path, when the result equals
    `data_root` itself or lies inside any of :data:`fitdocs.layout.OWNED_PATHS`'s
    directory prefixes -- compared component-wise (``Path.parts``), never as
    a plain string prefix, so ``blocks-mine`` is accepted where ``blocks``
    is refused (Req 1.9).
    """
    root = Path(os.path.normpath(data_root))
    raw = settings.path if settings.path is not None else DEFAULT_PLANS_DIR
    candidate = Path(raw)
    joined = candidate if candidate.is_absolute() else root / candidate
    resolved = Path(os.path.normpath(joined))

    if resolved == root:
        raise PlanSettingsError(
            f"{settings_file}: [plans] path resolves to the data root itself "
            f"({resolved}); the plan-source directory must be its own location"
        )

    owned_names = {Path(prefix).parts[0] for prefix in OWNED_PATHS}
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        relative = None
    if relative is not None and relative.parts and relative.parts[0] in owned_names:
        raise PlanSettingsError(
            f"{settings_file}: [plans] path resolves inside a fitdocs-owned "
            f"location ({resolved}); the plan-source directory must lie "
            f"outside every owned path"
        )

    return resolved
