"""The one reader for the ``fitdocs.toml`` ``[history]`` table (design:
HistorySettings; Req 2.7, 3.4, 8.3, 8.4).

Peer of :func:`fitdocs.load.settings.load_load_settings`,
:func:`fitdocs.tiles.tile_settings_from_document`,
:func:`fitdocs.inbox.load_inbox_settings` and
:func:`fitdocs.plugins.load_plugin_settings`: it receives the mapping
:func:`fitdocs.settings.load_settings_document` already parsed for this
invocation and validates only its own ``[history]`` table. It never opens,
reads or parses a file itself, and it adds nothing to
``fitdocs.load.settings`` -- reading ``LoadSettings.default_calculator`` is a
read, never an extension of that module's table.

Every field defaults to unset, so an absent settings file or an absent
``[history]`` table both resolve to :data:`DEFAULT_HISTORY_SETTINGS` --
never an error (Req 8.3). Unknown keys and unknown sub-tables inside
``[history]`` are ignored, because the file is shared with ``[tiles]``,
``[inbox]``, ``[plugins]`` and ``[load]``.

:class:`HistorySettingsError` subclasses the shared
:class:`~fitdocs.settings.SettingsError`, so the CLI's existing
``except SettingsError`` handler maps a malformed table to exit 2 with no
new branch (Req 8.4).

:func:`resolve_constants` projects the four model-constant fields onto a
:class:`~fitdocs.history.sources.ModelConstants`. With nothing configured
the result *is* :data:`~fitdocs.history.sources.SEED_CONSTANTS`, by
identity. With any of the four configured, the result's provenance is
``CONFIGURED`` and its origin line names each configured key and each key
left at its seed -- a partially configured set is never labelled ``SEEDS``
(Req 2.7).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from fitdocs.history.sources import SEED_CONSTANTS, ConstantProvenance, ModelConstants
from fitdocs.settings import SettingsError

HISTORY_TABLE: Final[str] = "history"

_CONFIGURABLE_FIELDS: Final[tuple[str, ...]] = (
    "tau_fitness_days",
    "tau_fatigue_days",
    "k_fitness",
    "k_fatigue",
)
"""The four fields :func:`resolve_constants` may override, in the fixed
order both the origin line and the resolved set are built over."""


@dataclass(frozen=True)
class HistorySettings:
    """The resolved ``[history]`` configuration for a pass.

    Every field carries the default ``None`` -- "use the shipped seed" for
    the four model constants, "use
    :data:`~fitdocs.history.sources.COVERAGE_THRESHOLD`.value" for the
    coverage threshold, "use ``[load].default_calculator``" for the
    methodology -- so ``HistorySettings()`` with no arguments always equals
    :data:`DEFAULT_HISTORY_SETTINGS`.
    """

    tau_fitness_days: float | None = None
    tau_fatigue_days: float | None = None
    k_fitness: float | None = None
    k_fatigue: float | None = None
    coverage_threshold: float | None = None
    methodology: str | None = None


DEFAULT_HISTORY_SETTINGS: Final[HistorySettings] = HistorySettings()


class HistorySettingsError(SettingsError):
    """The ``fitdocs.toml`` ``[history]`` table exists but is not valid
    configuration.

    Raised for a non-table ``history`` value, a non-numeric or non-finite
    ``tau_*``/``k_*``/``coverage_threshold``, a ``tau_*`` that is not
    strictly positive, a ``k_*`` that is negative, a ``coverage_threshold``
    outside ``[0.0, 1.0]``, or a non-string/empty ``methodology``. A
    boolean is rejected everywhere a number is expected, because ``bool``
    is an ``int`` subclass in Python. An *absent* file or ``[history]``
    table is never an error -- it yields :data:`DEFAULT_HISTORY_SETTINGS`.

    This type subclasses the shared :class:`~fitdocs.settings.SettingsError`,
    so the CLI's existing ``except SettingsError`` handler maps it to exit 2
    with no new branch, exactly like a malformed ``[load]`` or ``[plugins]``
    table.
    """


def load_history_settings(
    document: Mapping[str, object], settings_file: Path
) -> HistorySettings:
    """Project the ``[history]`` table of an already-parsed settings document.

    ``document`` is the mapping :func:`~fitdocs.settings.load_settings_document`
    already returned for this invocation (empty when the settings file is
    absent); this reader never opens a file itself. ``settings_file`` is
    used only to name the file in error messages.

    Returns :data:`DEFAULT_HISTORY_SETTINGS` when the file or its
    ``[history]`` table is absent. Raises :class:`HistorySettingsError` when
    the table is malformed. Unknown keys inside ``[history]`` are ignored,
    because the document is shared with ``[tiles]``, ``[inbox]``,
    ``[plugins]`` and ``[load]``.
    """
    if HISTORY_TABLE not in document:
        return DEFAULT_HISTORY_SETTINGS
    table = document[HISTORY_TABLE]
    if not isinstance(table, dict):
        raise HistorySettingsError(
            f"{settings_file}: [history] must be a table, "
            f"got {table!r} ({type(table).__name__})"
        )

    return HistorySettings(
        tau_fitness_days=_positive_finite_float(
            table, "tau_fitness_days", settings_file
        ),
        tau_fatigue_days=_positive_finite_float(
            table, "tau_fatigue_days", settings_file
        ),
        k_fitness=_nonnegative_finite_float(table, "k_fitness", settings_file),
        k_fatigue=_nonnegative_finite_float(table, "k_fatigue", settings_file),
        coverage_threshold=_unit_interval_float(
            table, "coverage_threshold", settings_file
        ),
        methodology=_nonempty_string(table, "methodology", settings_file),
    )


def resolve_constants(settings: HistorySettings) -> ModelConstants:
    """Resolve ``settings``'s four model-constant fields onto a complete
    :class:`~fitdocs.history.sources.ModelConstants`.

    With nothing configured, the result *is* ``SEED_CONSTANTS`` -- returned
    by identity, not merely by equality. With any of the four fields
    configured, the result's provenance is ``ConstantProvenance.CONFIGURED``
    and its origin line names each configured field and each field left at
    its seed, so a partially configured set is never labelled ``SEEDS``.
    """
    configured = {
        name: value
        for name in _CONFIGURABLE_FIELDS
        if (value := getattr(settings, name)) is not None
    }
    if not configured:
        return SEED_CONSTANTS

    seeds: dict[str, float] = {
        "tau_fitness_days": SEED_CONSTANTS.tau_fitness_days,
        "tau_fatigue_days": SEED_CONSTANTS.tau_fatigue_days,
        "k_fitness": SEED_CONSTANTS.k_fitness,
        "k_fatigue": SEED_CONSTANTS.k_fatigue,
    }
    resolved = {
        name: configured.get(name, seeds[name]) for name in _CONFIGURABLE_FIELDS
    }
    configured_names = [name for name in _CONFIGURABLE_FIELDS if name in configured]
    seeded_names = [name for name in _CONFIGURABLE_FIELDS if name not in configured]

    origin_parts = [
        "the athlete's own configured constants ("
        + ", ".join(f"{name}={resolved[name]!r}" for name in configured_names)
        + ")"
    ]
    if seeded_names:
        origin_parts.append(
            "left at fitdocs' shipped seed for " + ", ".join(seeded_names)
        )
    origin = "; ".join(origin_parts) + "."

    return ModelConstants(
        tau_fitness_days=resolved["tau_fitness_days"],
        tau_fatigue_days=resolved["tau_fatigue_days"],
        k_fitness=resolved["k_fitness"],
        k_fatigue=resolved["k_fatigue"],
        provenance=ConstantProvenance.CONFIGURED,
        origin=origin,
    )


def _positive_finite_float(
    table: dict[str, Any], key: str, settings_file: Path
) -> float | None:
    """Map an optional strictly-positive finite time constant (a ``tau_*``
    key). ``bool`` is rejected explicitly, because it is an ``int``
    subclass and would otherwise pass ``isinstance(value, (int, float))``."""
    if key not in table:
        return None
    value = table[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise HistorySettingsError(
            f"{settings_file}: [history] {key} must be a finite number "
            f"greater than zero, got {value!r} ({type(value).__name__})"
        )
    return float(value)


def _nonnegative_finite_float(
    table: dict[str, Any], key: str, settings_file: Path
) -> float | None:
    """Map an optional non-negative finite weighting (a ``k_*`` key)."""
    if key not in table:
        return None
    value = table[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise HistorySettingsError(
            f"{settings_file}: [history] {key} must be a finite number "
            f"not less than zero, got {value!r} ({type(value).__name__})"
        )
    return float(value)


def _unit_interval_float(
    table: dict[str, Any], key: str, settings_file: Path
) -> float | None:
    """Map the optional ``coverage_threshold`` key, rejecting anything
    outside the closed unit interval."""
    if key not in table:
        return None
    value = table[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not (0.0 <= value <= 1.0)
    ):
        raise HistorySettingsError(
            f"{settings_file}: [history] {key} must be a finite number "
            f"between zero and one inclusive, got {value!r} "
            f"({type(value).__name__})"
        )
    return float(value)


def _nonempty_string(
    table: dict[str, Any], key: str, settings_file: Path
) -> str | None:
    """Map the optional ``methodology`` key, rejecting anything that is not
    a non-empty string."""
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str) or not value:
        raise HistorySettingsError(
            f"{settings_file}: [history] {key} must be a non-empty string, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value
