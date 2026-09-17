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
imports ``fitdocs.load.*``. ``load/channels/types.py`` is the first of the
three to land (``load-channels``, Req 3.9): this module imports its
:class:`~fitdocs.load.channels.types.SufficiencySettings` and projects
``[load.sufficiency]`` onto it. ``load/priority.py`` is the second
(``threshold-load``, Req 7.2): this module imports its
:class:`~fitdocs.load.priority.ChannelPriority` and projects
``[load.priority]`` onto it, and neither module reverses the edge --
``load/priority.py`` stays a leaf, importing nothing under
``fitdocs.load.settings``. ``load/qa/types.py`` is the third
(``activity-qa-flags``, Req 6.1): this module imports its
:class:`~fitdocs.load.qa.types.FlagSettings` and projects
``[load.flags]`` onto it, and that module stays a leaf too, importing
nothing under ``fitdocs.load.settings``. The one edge that must never become a
runtime import is ``fitdocs.load.types``'s reference back to
:class:`LoadSettings` for ``LoadContext.settings``'s annotation, which stays
``TYPE_CHECKING``-only on that module's side. This module still imports
nothing from ``fitdocs.load.types`` itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from fitdocs.load.channels.types import ChannelId, SufficiencySettings
from fitdocs.load.priority import DEFAULT_CHANNEL_PRIORITY, ChannelPriority
from fitdocs.load.qa.types import FlagSettings
from fitdocs.model import Sport
from fitdocs.settings import SettingsError

LOAD_TABLE = "load"
SUFFICIENCY_TABLE = "sufficiency"
PRIORITY_TABLE = "priority"
FLAGS_TABLE = "flags"

_SUPPORTED_PRIORITY_SPORTS: Final[Mapping[str, Sport]] = MappingProxyType(
    {sport.value.lower(): sport for sport in DEFAULT_CHANNEL_PRIORITY}
)
_CHANNEL_BY_TOML_VALUE: Final[Mapping[str, ChannelId]] = MappingProxyType(
    {channel.value: channel for channel in ChannelId}
)

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
    sufficiency: SufficiencySettings = field(default_factory=SufficiencySettings)
    channel_priority: ChannelPriority = field(default_factory=ChannelPriority)
    flags: FlagSettings = field(default_factory=FlagSettings)


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
        sufficiency=_setting_sufficiency(table, settings_file),
        channel_priority=_setting_channel_priority(table, settings_file),
        flags=_setting_flags(table, settings_file),
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


def _setting_sufficiency(
    table: dict[str, Any], settings_file: Path
) -> SufficiencySettings:
    """Project the ``[load.sufficiency]`` sub-table (Req 3.1-3.8).

    Absent sub-table, or an absent individual key within a present one, both
    resolve to the documented default drawn from
    :class:`~fitdocs.load.channels.types.SufficiencySettings`'s own field
    defaults (Req 3.3) -- never an error. A present but non-table value
    raises, naming the ``load.sufficiency`` path (Req 3.6). Keys this reader
    does not recognize inside the sub-table are ignored, matching the
    ignore-unknown-keys behavior the enclosing ``[load]`` reader already has
    (Req 3.7).
    """
    default = DEFAULT_LOAD_SETTINGS.sufficiency
    if SUFFICIENCY_TABLE not in table:
        return default
    sub_table = table[SUFFICIENCY_TABLE]
    if not isinstance(sub_table, dict):
        raise LoadSettingsError(
            f"{settings_file}: [load.sufficiency] must be a table, "
            f"got {sub_table!r} ({type(sub_table).__name__})"
        )

    min_stream_coverage = _setting_coverage(
        sub_table,
        "min_stream_coverage",
        settings_file,
        default.min_stream_coverage,
    )
    assert min_stream_coverage is not None  # a non-None default always resolves

    return SufficiencySettings(
        min_duration_s=_setting_min_duration_s(sub_table, settings_file, default),
        min_stream_coverage=min_stream_coverage,
        power_min_stream_coverage=_setting_coverage(
            sub_table,
            "power_min_stream_coverage",
            settings_file,
            default.power_min_stream_coverage,
        ),
        hr_min_stream_coverage=_setting_coverage(
            sub_table,
            "hr_min_stream_coverage",
            settings_file,
            default.hr_min_stream_coverage,
        ),
        pace_min_stream_coverage=_setting_coverage(
            sub_table,
            "pace_min_stream_coverage",
            settings_file,
            default.pace_min_stream_coverage,
        ),
    )


def _setting_min_duration_s(
    sub_table: dict[str, Any], settings_file: Path, default: SufficiencySettings
) -> int:
    """Map optional ``min_duration_s``, rejecting non-positive whole seconds."""
    if "min_duration_s" not in sub_table:
        return default.min_duration_s
    value = sub_table["min_duration_s"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LoadSettingsError(
            f"{settings_file}: [load.sufficiency] min_duration_s must be a "
            f"positive whole number of seconds, got {value!r} "
            f"({type(value).__name__})"
        )
    return value


def _setting_coverage(
    sub_table: dict[str, Any],
    key: str,
    settings_file: Path,
    default: float | None,
) -> float | None:
    """Map an optional coverage key, rejecting anything outside ``(0, 1]``.

    Shared by the shared ``min_stream_coverage`` key and the three optional
    per-channel overrides (``power_``/``hr_``/``pace_min_stream_coverage``,
    Req 3.2) -- an absent override resolves to ``None``, which
    :meth:`~fitdocs.load.channels.types.SufficiencySettings.minimum_for`
    already treats as "use the shared value".
    """
    if key not in sub_table:
        return default
    value = sub_table[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not (0 < value <= 1)
    ):
        raise LoadSettingsError(
            f"{settings_file}: [load.sufficiency] {key} must be a number "
            f"above zero and at or below one, got {value!r} "
            f"({type(value).__name__})"
        )
    return float(value)


def _setting_channel_priority(
    table: dict[str, Any], settings_file: Path
) -> ChannelPriority:
    """Project the ``[load.priority]`` sub-table (Req 7.1-7.9).

    Absent sub-table, or an absent individual discipline key within a
    present one, both resolve to :data:`DEFAULT_CHANNEL_PRIORITY`'s order
    for that discipline (Req 7.3) -- never an error. A configured entry
    overrides only its own discipline; every other discipline keeps its
    documented default (Req 7.4), so the produced value is always complete
    over every supported discipline.

    A present but non-table ``[load.priority]`` value raises (Req 7.5-7.7,
    first form). A key that is not a lowercased supported-sport name --
    unrecognized entirely, or a recognized :class:`~fitdocs.model.Sport`
    this calculator does not support (``swim``, ``rowing``, ``workout``) --
    raises naming the file, the offending key and the supported disciplines
    (Req 7.5). A value that is not a list, that contains a non-string
    element, an unrecognized channel name, a repeated channel, or is empty
    each raise naming the file, the key and the offending value (Req
    7.6-7.7).

    A *valid but futile* order -- e.g. ``ride = ["pace"]``, a channel this
    calculator never computes for cycling -- is accepted without complaint
    (Req 7.9): this reader validates only that every named channel is one
    of the three recognized identifiers, never whether that channel can
    ever produce a value for the discipline it is configured under.
    """
    default = DEFAULT_LOAD_SETTINGS.channel_priority
    if PRIORITY_TABLE not in table:
        return default
    sub_table = table[PRIORITY_TABLE]
    if not isinstance(sub_table, dict):
        raise LoadSettingsError(
            f"{settings_file}: [load.priority] must be a table, "
            f"got {sub_table!r} ({type(sub_table).__name__})"
        )

    by_discipline: dict[Sport, tuple[ChannelId, ...]] = dict(default.by_discipline)
    for key, value in sub_table.items():
        sport = _SUPPORTED_PRIORITY_SPORTS.get(key)
        if sport is None:
            supported = ", ".join(sorted(_SUPPORTED_PRIORITY_SPORTS))
            raise LoadSettingsError(
                f"{settings_file}: [load.priority] key {key!r} is not a "
                f"supported discipline, got {key!r}; supported disciplines "
                f"are {supported}"
            )
        by_discipline[sport] = _channel_priority_order(key, value, settings_file)

    return ChannelPriority(by_discipline=MappingProxyType(by_discipline))


def _channel_priority_order(
    key: str, value: object, settings_file: Path
) -> tuple[ChannelId, ...]:
    """Validate and convert one ``[load.priority]`` discipline entry.

    Rejects a non-list value, a non-string element, an unrecognized channel
    name, a repeated channel, and an empty list -- each naming the file, the
    key and the offending value (Req 7.6, 7.7).
    """
    if not isinstance(value, list):
        raise LoadSettingsError(
            f"{settings_file}: [load.priority] {key} must be a list of "
            f"channel names, got {value!r} ({type(value).__name__})"
        )
    if not value:
        raise LoadSettingsError(
            f"{settings_file}: [load.priority] {key} must not be empty, got {value!r}"
        )

    channels: list[ChannelId] = []
    seen: set[ChannelId] = set()
    for element in value:
        if not isinstance(element, str):
            raise LoadSettingsError(
                f"{settings_file}: [load.priority] {key} entries must be "
                f"strings, got {element!r} ({type(element).__name__})"
            )
        channel = _CHANNEL_BY_TOML_VALUE.get(element)
        if channel is None:
            recognized = ", ".join(sorted(_CHANNEL_BY_TOML_VALUE))
            raise LoadSettingsError(
                f"{settings_file}: [load.priority] {key} names unrecognized "
                f"channel {element!r}; recognized channels are {recognized}"
            )
        if channel in seen:
            raise LoadSettingsError(
                f"{settings_file}: [load.priority] {key} repeats channel {element!r}"
            )
        seen.add(channel)
        channels.append(channel)
    return tuple(channels)


def _setting_flags(table: dict[str, Any], settings_file: Path) -> FlagSettings:
    """Project the ``[load.flags]`` sub-table (Req 6.1-6.9).

    Absent sub-table, or an absent individual key within a present one, both
    resolve to the documented default drawn from
    :class:`~fitdocs.load.qa.types.FlagSettings`'s own field defaults (Req
    6.3) -- never an error. A present but non-table value raises, naming the
    ``load.flags`` path (Req 6.6). Keys this reader does not recognize inside
    the sub-table are ignored, matching the ignore-unknown-keys behavior the
    enclosing ``[load]`` reader already has (Req 6.2).

    Reads no staleness window of its own: the benchmark store's own
    configured ``benchmark_staleness_days`` is the only one this feature uses
    (Req 6.9).

    ``cadence_lock_min_duration_s`` configured below ``cadence_lock_window_s``
    is accepted, not rejected -- a single locked span at least that long is
    enough to raise the flag, a coherent if aggressive choice, and this
    reader does not cross-validate the two keys against each other; rejecting
    it would be the tool overriding the athlete's own configuration.
    """
    default = DEFAULT_LOAD_SETTINGS.flags
    if FLAGS_TABLE not in table:
        return default
    sub_table = table[FLAGS_TABLE]
    if not isinstance(sub_table, dict):
        raise LoadSettingsError(
            f"{settings_file}: [load.flags] must be a table, "
            f"got {sub_table!r} ({type(sub_table).__name__})"
        )

    return FlagSettings(
        cadence_lock_min_correlation=_setting_flag_unit_float(
            sub_table,
            "cadence_lock_min_correlation",
            settings_file,
            default.cadence_lock_min_correlation,
        ),
        cadence_lock_max_delta_bpm=_setting_flag_positive_float(
            sub_table,
            "cadence_lock_max_delta_bpm",
            settings_file,
            default.cadence_lock_max_delta_bpm,
        ),
        cadence_lock_window_s=_setting_flag_window_s(
            sub_table, settings_file, default.cadence_lock_window_s
        ),
        cadence_lock_min_duration_s=_setting_flag_min_duration_s(
            sub_table, settings_file, default.cadence_lock_min_duration_s
        ),
        cadence_lock_min_paired_coverage=_setting_flag_unit_float(
            sub_table,
            "cadence_lock_min_paired_coverage",
            settings_file,
            default.cadence_lock_min_paired_coverage,
        ),
        divergence_max_intensity_delta=_setting_flag_positive_float(
            sub_table,
            "divergence_max_intensity_delta",
            settings_file,
            default.divergence_max_intensity_delta,
        ),
        aerobic_drift_max_pct=_setting_flag_positive_float(
            sub_table,
            "aerobic_drift_max_pct",
            settings_file,
            default.aerobic_drift_max_pct,
        ),
    )


def _setting_flag_unit_float(
    sub_table: dict[str, Any],
    key: str,
    settings_file: Path,
    default: float,
) -> float:
    """Map an optional ``[load.flags]`` key, rejecting anything outside
    ``(0, 1]`` -- shared by ``cadence_lock_min_correlation`` and
    ``cadence_lock_min_paired_coverage``."""
    if key not in sub_table:
        return default
    value = sub_table[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not (0 < value <= 1)
    ):
        raise LoadSettingsError(
            f"{settings_file}: [load.flags] {key} must be a number "
            f"above zero and at or below one, got {value!r} "
            f"({type(value).__name__})"
        )
    return float(value)


def _setting_flag_positive_float(
    sub_table: dict[str, Any],
    key: str,
    settings_file: Path,
    default: float,
) -> float:
    """Map an optional ``[load.flags]`` key, rejecting anything at or below
    zero -- shared by ``cadence_lock_max_delta_bpm``,
    ``divergence_max_intensity_delta`` and ``aerobic_drift_max_pct``."""
    if key not in sub_table:
        return default
    value = sub_table[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise LoadSettingsError(
            f"{settings_file}: [load.flags] {key} must be a number "
            f"above zero, got {value!r} ({type(value).__name__})"
        )
    return float(value)


def _setting_flag_window_s(
    sub_table: dict[str, Any], settings_file: Path, default: int
) -> int:
    """Map optional ``cadence_lock_window_s``, rejecting anything below 30
    whole seconds."""
    key = "cadence_lock_window_s"
    if key not in sub_table:
        return default
    value = sub_table[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 30:
        raise LoadSettingsError(
            f"{settings_file}: [load.flags] {key} must be a whole number of "
            f"seconds at or above 30, got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_flag_min_duration_s(
    sub_table: dict[str, Any], settings_file: Path, default: int
) -> int:
    """Map optional ``cadence_lock_min_duration_s``, rejecting non-positive
    whole seconds. Accepted even when configured below
    ``cadence_lock_window_s`` -- see :func:`_setting_flags`."""
    key = "cadence_lock_min_duration_s"
    if key not in sub_table:
        return default
    value = sub_table[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LoadSettingsError(
            f"{settings_file}: [load.flags] {key} must be a positive whole "
            f"number of seconds, got {value!r} ({type(value).__name__})"
        )
    return value
