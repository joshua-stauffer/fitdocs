"""Plugin settings and discovery: third-party training-load calculators.

This module owns third-party calculator discovery end to end: entry-point
resolution, local plugin file/directory loading, provenance, and the
``fitdocs plugins`` command's backing report. It holds two halves:

* **Settings** -- :class:`PluginSettings` and :func:`load_plugin_settings`,
  the per-table projection of the already-parsed ``[plugins]`` table (design:
  "PluginSettings + ``load_plugin_settings``", ``src/fitdocs/plugins.py``).
* **Discovery** -- :func:`discover` and :func:`reset`, which load, validate,
  register, and attribute every third-party calculator, isolating each
  plugin's failure from the rest of the run (design: "PluginDiscovery",
  ``src/fitdocs/plugins.py``). Two channels feed it: the entry-point channel
  for calculators advertised by an installed distribution, then the local
  channel that executes the plugin file(s) named by ``settings.resolved_path``.
  Discovery is cached per process, keyed on ``(data_root, settings)``: a
  repeat call with the same key returns the cached report without
  re-registering anything, and a call with a different key drops the previous
  registrations via :func:`reset` before running discovery again.

This reader never opens, reads, or parses a file itself. settings-foundation's
shared reader (:func:`fitdocs.settings.load_settings_document`) locates,
reads, and parses ``<data-root>/fitdocs.toml`` exactly once per invocation,
raising the single shared :class:`~fitdocs.settings.SettingsError` for
file-level problems (an unreadable file, invalid TOML). This module receives
only the mapping that reader already produced and validates just its own
table, exactly as :func:`fitdocs.tiles.tile_settings_from_document` does for
``[tiles]``.

Two invariants shape the reader:

* **Defaulted, never an error.** An absent settings file -- which reaches this
  reader as an empty mapping -- or a file with no ``[plugins]`` table yields
  :data:`DEFAULT_PLUGIN_SETTINGS`. Each key defaults *independently*, so a
  partial ``[plugins]`` table fills only the keys it names.
* **Loud, never lossy.** A malformed ``[plugins]`` table -- a non-boolean
  ``enabled``, an empty or non-string ``path``, or a non-table ``[plugins]``
  value -- raises :class:`PluginSettingsError` naming the settings file and the
  offending key. Path *existence* is deliberately not checked here: a missing
  path is a plugin load error (requirement 2.6, a later task), not a
  configuration error (requirement 2.7).

The file is **user-owned and read-only to fitdocs**: this reader never
creates it, never prompts, and writes nothing on any path. Unknown keys within
``[plugins]`` and unknown top-level tables are ignored, because the file is
shared with ``[tiles]``, ``[inbox]``, and future tables.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any, Final, cast

from fitdocs.load import registry
from fitdocs.load.types import LoadCalculator
from fitdocs.settings import SettingsError

PLUGINS_TABLE: Final[str] = "plugins"


@dataclass(frozen=True)
class PluginSettings:
    """Validated ``[plugins]`` configuration (design: PluginSettings).

    Every field has a default (see :data:`DEFAULT_PLUGIN_SETTINGS`); a
    ``[plugins]`` table overrides them per key.
    """

    enabled: bool
    """``False`` disables both discovery channels (entry-point AND local)."""

    path: str | None
    """Local plugin file or directory; ``None`` means no local plugins."""

    def resolved_path(self, data_root: Path) -> Path | None:
        """The local plugin path resolved against *data_root*.

        Returns ``None`` when :attr:`path` is ``None``. A relative
        :attr:`path` resolves against *data_root* so a vault stays portable
        between machines; an absolute path is used as given. Existence is
        never checked here.
        """
        if self.path is None:
            return None
        candidate = Path(self.path)
        if candidate.is_absolute():
            return candidate
        return data_root / candidate


#: The keyless default: discovery enabled on both channels, no local plugin
#: path configured. Used whenever ``fitdocs.toml`` or its ``[plugins]`` table
#: is absent.
DEFAULT_PLUGIN_SETTINGS: Final[PluginSettings] = PluginSettings(enabled=True, path=None)


class PluginSettingsError(SettingsError):
    """The ``fitdocs.toml`` ``[plugins]`` table exists but is not valid configuration.

    Raised for a non-boolean ``enabled``, an empty or non-string ``path``, or a
    non-table ``plugins`` value -- faults that belong to *this table*. An
    *absent* file or ``[plugins]`` table is never an error -- it yields
    :data:`DEFAULT_PLUGIN_SETTINGS`. The message names the settings file and
    the offending key so a user can correct the configuration (the CLI maps
    this to a loud exit-2 failure, exactly like a malformed ``[tiles]``
    table).

    File-level faults -- an unreadable file, invalid TOML -- are *not* raised
    here: they belong to the file rather than to any one table and surface as
    the shared :class:`~fitdocs.settings.SettingsError`, so a user with a
    stray bracket gets one message instead of whichever table happened to be
    read first. This type subclasses it, so ``except SettingsError`` still
    catches both.
    """


def load_plugin_settings(
    document: Mapping[str, object], settings_file: Path
) -> PluginSettings:
    """Project the ``[plugins]`` table of an already-parsed settings document.

    The per-table reader: it validates only ``[plugins]`` and never opens a
    file -- ``document`` is the mapping
    :func:`~fitdocs.settings.load_settings_document` already returned for this
    invocation (empty when the settings file is absent), and ``settings_file``
    -- obtained by the caller from :func:`fitdocs.layout.settings_path` -- is
    used only to name the file in error messages.

    Returns :data:`DEFAULT_PLUGIN_SETTINGS` when the file or its ``[plugins]``
    table is absent; each key defaults independently. Raises
    :class:`PluginSettingsError` when the ``[plugins]`` table is malformed: a
    non-table ``plugins`` value, a non-boolean ``enabled``, or an empty or
    non-string ``path``. Unknown keys inside ``[plugins]`` and unknown
    top-level tables are ignored, because the document is shared with
    ``[tiles]``, ``[inbox]``, and future tables. Path existence is
    deliberately not checked -- a missing path is a plugin load error, not a
    configuration error.
    """
    if PLUGINS_TABLE not in document:
        return DEFAULT_PLUGIN_SETTINGS
    table = document[PLUGINS_TABLE]
    if not isinstance(table, dict):
        raise PluginSettingsError(
            f"{settings_file}: [plugins] must be a table, "
            f"got {table!r} ({type(table).__name__})"
        )

    return PluginSettings(
        enabled=_setting_bool(
            table, "enabled", DEFAULT_PLUGIN_SETTINGS.enabled, settings_file
        ),
        path=_setting_path(table, settings_file),
    )


def _setting_bool(
    table: dict[str, Any], key: str, default: bool, settings_file: Path
) -> bool:
    """Map an optional boolean key; reject non-bools (a TOML int is not a bool)."""
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise PluginSettingsError(
            f"{settings_file}: [plugins] {key} must be a boolean, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_path(table: dict[str, Any], settings_file: Path) -> str | None:
    """Map the optional ``path`` key, rejecting a non-string or empty value."""
    if "path" not in table:
        return DEFAULT_PLUGIN_SETTINGS.path
    value = table["path"]
    if not isinstance(value, str) or not value:
        raise PluginSettingsError(
            f"{settings_file}: [plugins] path must be a non-empty string, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value


# --- Discovery (design: "PluginDiscovery") ----------------------------------
#
# The entry-point channel: importing an installed distribution's advertised
# calculator, coercing it to an instance, registering it through the 1.2 gate,
# and isolating every per-plugin failure so one broken plugin never costs the
# rest of the run its calculators (Req 1.1, 1.3, 1.7-1.9, 3.2, 3.4, 4.2, 4.3,
# 7.1, 7.5).
#
# Local plugin file/directory loading (``settings.resolved_path``) runs after
# the entry-point channel, so local calculators occupy registry slots after
# packaged plugins and after anything already registered by other means
# (Req 2.1-2.4, 2.6). Per-invocation
# caching (task 2.4) keys the report on ``(data_root, settings)``: a repeat
# call with the same key returns the cached report untouched, and a call with
# a different key resets the previous registrations before running again.

ENTRY_POINT_GROUP: Final[str] = "fitdocs.load_calculators"
"""The extension group advertised by a third-party calculator distribution."""

LOCAL_MODULE_PREFIX: Final[str] = "fitdocs_local_plugins"
"""Reserved module-name prefix for the local plugin channel (task 2.3)."""


@dataclass(frozen=True)
class BuiltIn:
    """Origin: a calculator no plugin channel accounted for.

    Origin is assigned by *discovery channel*, so this is the fallback for
    any calculator registered outside the entry-point and local-file
    channels. fitdocs ships exactly one built-in, ``threshold``, registered
    by :mod:`fitdocs.load`'s initializer (Req 1.1-1.3); it carries this
    origin, as does anything else registered directly -- by a test or by a
    downstream spec -- rather than through a plugin channel. The name is
    retained because the channel distinction it draws is real and is what
    :func:`_incumbent_origin_text` reports on a duplicate id.
    """


@dataclass(frozen=True)
class Distribution:
    """Origin: a calculator advertised by an installed distribution."""

    name: str
    """The advertising distribution's name, e.g. ``"fitdocs-mycalc"``."""
    entry_point: str
    """The entry-point name within :data:`ENTRY_POINT_GROUP`."""


@dataclass(frozen=True)
class LocalFile:
    """Origin: a calculator registered by a local plugin file (task 2.3)."""

    path: str
    """The file that registered the calculator."""


Origin = BuiltIn | Distribution | LocalFile
"""The closed set of places a registered calculator can have come from."""


@dataclass(frozen=True)
class PluginInfo:
    """One registered calculator's identity, provenance, and coverage.

    Populated entirely by :func:`discover`; the ``fitdocs plugins`` listing
    command (a later task) only formats what this record already carries.
    """

    calculator_id: str
    display_name: str
    version: str | None
    """``None`` means unknown -- never a fabricated value (Req 4.3)."""
    origin: Origin
    modalities: tuple[str, ...]
    """Sorted modality values, e.g. ``("bike", "run")``."""


@dataclass(frozen=True)
class PluginLoadError:
    """One plugin's failure to load, validate, or register.

    Follows the Phase 3 report-type vocabulary: ``subject`` names *what*
    failed (an entry point as ``"<dist>: <entry point name>"``, or, for a
    local file (task 2.3), its path); ``detail`` says *why*, in user-facing
    words.
    """

    subject: str
    detail: str


@dataclass(frozen=True)
class PluginReport:
    """Everything one ``discover()`` call learned."""

    calculators: tuple[PluginInfo, ...]
    """Every registered calculator, in registration order.

    No ordering privilege is implied: fitdocs's one built-in, ``threshold``,
    carries no leading-slot privilege over anything a plugin author
    registers (``registry.py``'s own documented rule). This used to carry a
    parenthetical granting bundled calculators the leading slots, which told
    a plugin author they exist and outrank theirs -- the wrong mental model
    then and now. That wording is now forbidden by
    ``tests/test_plugin_regression.py::test_plugins_module_prose_never_asserts_multiple_bundled_calculators_or_an_ordering_privilege``.
    """
    errors: tuple[PluginLoadError, ...]
    """Every plugin load failure, in discovery order."""


#: id -> (origin, version) for every calculator this module registered from a
#: plugin channel. Never holds a built-in id. Cleared, and used to drive
#: unregistration, only by :func:`reset`.
_plugin_origins: dict[str, tuple[Origin, str | None]] = {}

#: The ``(data_root, settings)`` key the cached report below was computed for,
#: and the report itself. ``entry_points_fn`` is deliberately not part of the
#: key (design: "discovery is cached per process, keyed on
#: ``(data_root, settings)``"). Both are cleared only by :func:`reset`.
_cached_key: tuple[Path | None, PluginSettings] | None = None
_cached_report: PluginReport | None = None


def discover(
    data_root: Path | None,
    settings: PluginSettings,
    *,
    entry_points_fn: Callable[
        ..., Iterable[EntryPoint]
    ] = importlib.metadata.entry_points,
) -> PluginReport:
    """Discover, validate, register, and attribute third-party calculators.

    Importing ``fitdocs.load`` registers its one built-in, ``threshold``
    (Req 1.1-1.3), so on a fresh interpreter this runs against a registry
    already holding that single calculator -- it carries no ordering
    privilege over anything registered afterwards. When ``settings.enabled``
    is ``False`` no entry point is loaded at all (Req 1.8); the returned report
    then describes only whatever was already registered by other means, which
    for a plain run is fitdocs' own ``threshold`` built-in and nothing else.
    Otherwise every entry advertised under
    :data:`ENTRY_POINT_GROUP` is processed in an order derived only from the
    advertised names -- sorted by ``(entry_point.name, distribution name,
    entry_point.value)`` -- so automatic calculator selection is reproducible
    across machines and installation orders (Req 1.3). Only distributions
    that advertise the group are ever imported (Req 1.9); no network access
    and no write to ``data_root`` ever occurs (Req 7.1).

    Every per-plugin step is isolated: a failure anywhere in loading,
    coercing, or registering one entry point becomes one
    :class:`PluginLoadError` and discovery continues with the remaining
    entries (Req 3.2); calculators registered outside the plugin channels stay
    registered regardless of how many plugins fail (Req 3.4).

    After the entry-point channel, when a local plugin ``path`` is configured
    and ``data_root`` resolves it, the local channel loads plugin file(s) from
    that path (Req 2.1-2.4); each file's failure is isolated the same way and
    named by its path (Req 2.6). ``settings.enabled`` is ``False`` disables
    both channels (Req 1.8); a ``None`` ``data_root`` -- the degraded
    ``plugins``-listing path -- skips the local channel entirely rather than
    erroring (Req 4.7).

    Discovery is cached per process, keyed on ``(data_root, settings)`` --
    ``entry_points_fn`` is not part of the key. A call naming the same pair as
    the last one returns that cached report unchanged, registering nothing a
    second time (Req 1.2): this makes discovery exactly once per invocation no
    matter how many callers ask. A call naming a *different* pair is a new
    invocation: the previous plugin registrations are dropped through
    :func:`reset` and discovery runs again, keeping the existing in-process
    command tests honest where one process invokes commands against several
    temporary data roots in turn.

    Returns a :class:`PluginReport` whose ``calculators`` mirrors the
    registry's current registration order and whose ``errors`` lists every
    load failure in discovery order. Never raises for a plugin's own
    failure.
    """
    global _cached_key, _cached_report

    key = (data_root, settings)
    if _cached_report is not None and _cached_key == key:
        return _cached_report

    if _cached_report is not None:
        reset()

    errors: list[PluginLoadError] = []

    if settings.enabled:
        entries = sorted(
            entry_points_fn(group=ENTRY_POINT_GROUP), key=_entry_point_sort_key
        )
        for entry_point in entries:
            _load_entry_point(entry_point, errors)

        if data_root is not None:
            resolved = settings.resolved_path(data_root)
            if resolved is not None:
                _load_local_channel(resolved, errors)

    calculators = tuple(_plugin_info(calculator) for calculator in registry.available())
    report = PluginReport(calculators=calculators, errors=tuple(errors))
    _cached_key = key
    _cached_report = report
    return report


def reset() -> None:
    """Test support: unregister every plugin-attributed id and forget them.

    Unregisters exactly the ids :func:`discover` attributed to a plugin --
    never a built-in id -- via :func:`fitdocs.load.registry.unregister`, then
    clears the id-to-origin map. Also clears the cached report and the
    ``(data_root, settings)`` key it was computed for (task 2.4), so a
    subsequent :func:`discover` call -- even with the same key -- re-runs
    discovery rather than returning stale state. A safe no-op when nothing was
    registered or cached. Called by the suite's autouse fixture so discovery
    state never leaks between tests, and by :func:`discover` itself when a new
    ``(data_root, settings)`` pair supersedes the cached one.
    """
    global _cached_key, _cached_report

    for calculator_id in list(_plugin_origins):
        registry.unregister(calculator_id)
    _plugin_origins.clear()
    _cached_key = None
    _cached_report = None


def _entry_point_sort_key(entry_point: EntryPoint) -> tuple[str, str, str]:
    """``(name, distribution name or "", value)`` -- advertised names only."""
    return (entry_point.name, _dist_name(entry_point), entry_point.value)


def _dist_name(entry_point: EntryPoint) -> str:
    """The advertising distribution's name, or ``""`` when unknown."""
    dist = getattr(entry_point, "dist", None)
    name = getattr(dist, "name", None)
    return name if isinstance(name, str) else ""


def _dist_version(entry_point: EntryPoint) -> str | None:
    """The advertising distribution's version, or ``None`` when unknown --
    never fabricated (Req 4.3)."""
    dist = getattr(entry_point, "dist", None)
    version = getattr(dist, "version", None)
    return version if isinstance(version, str) else None


def _load_entry_point(entry_point: EntryPoint, errors: list[PluginLoadError]) -> None:
    """Load, coerce, and register one entry point, isolating every failure.

    Each step -- ``entry_point.load()``, coercion/instantiation, and
    ``registry.register()`` -- runs inside its own ``except Exception`` (Req
    3.2): a bad shape, a contract violation (``InvalidCalculatorError``), and
    a duplicate id (``DuplicateCalculatorIdError``) are both ``ValueError``
    subclasses but are caught by the same broad boundary, since a hostile
    descriptor or a raising ``__repr__`` can propagate a non-``ValueError``
    exception through validation or registration.
    """
    dist_name = _dist_name(entry_point)
    subject = f"{dist_name}: {entry_point.name}" if dist_name else entry_point.name

    try:
        value = entry_point.load()
    except Exception as exc:
        errors.append(PluginLoadError(subject=subject, detail=str(exc)))
        return

    try:
        resolved = _coerce_entry_point_value(value)
    except Exception as exc:
        errors.append(PluginLoadError(subject=subject, detail=str(exc)))
        return

    try:
        registry.register(resolved)
    except registry.DuplicateCalculatorIdError as exc:
        errors.append(
            PluginLoadError(
                subject=subject,
                detail=f"{exc}; kept the {_incumbent_origin_text(exc.calculator_id)}",
            )
        )
        return
    except Exception as exc:
        errors.append(PluginLoadError(subject=subject, detail=str(exc)))
        return

    _plugin_origins[resolved.calculator_id] = (
        Distribution(name=dist_name, entry_point=entry_point.name),
        _dist_version(entry_point),
    )


def _coerce_entry_point_value(value: object) -> LoadCalculator:
    """Resolve an entry point's loaded value to a calculator instance.

    A class is instantiated with no arguments; an object that already
    satisfies the calculator contract is used as-is; a non-calculator
    callable (a zero-argument factory) is called with no arguments. Anything
    else -- most commonly a module, a common authoring mistake -- is rejected
    with a reason naming the expected shapes.
    """
    if isinstance(value, type):
        return cast(LoadCalculator, value())
    if registry.validate_calculator(value) is None:
        return cast(LoadCalculator, value)
    if callable(value):
        return cast(LoadCalculator, value())
    raise TypeError(
        "entry point value must be a calculator class, a zero-argument "
        "factory callable, or a calculator instance satisfying the "
        f"contract; got {value!r} ({type(value).__name__})"
    )


def _plugin_info(calculator: LoadCalculator) -> PluginInfo:
    """Build the :class:`PluginInfo` for one currently-registered calculator."""
    entry = _plugin_origins.get(calculator.calculator_id)
    if entry is None:
        origin: Origin = BuiltIn()
        version: str | None = importlib.metadata.version("fitdocs")
    else:
        origin, version = entry
    return PluginInfo(
        calculator_id=calculator.calculator_id,
        display_name=calculator.display_name,
        version=version,
        origin=origin,
        modalities=tuple(sorted(m.value for m in calculator.supported_modalities)),
    )


def _local_files(resolved: Path) -> list[Path]:
    """The plugin file(s) a resolved local path contributes, in load order.

    A single file is loaded as itself (Req 2.3). A directory contributes its
    **top-level** ``*.py`` files in alphabetical filename order (Req 2.2),
    skipping names beginning with ``_`` (private helpers) and never descending
    into subdirectories. A path that is neither a file nor a directory (it does
    not exist, or cannot be read) yields no files; the caller turns that into a
    single named load error (Req 2.6).
    """
    if resolved.is_file():
        return [resolved]
    if resolved.is_dir():
        return sorted(
            child
            for child in resolved.iterdir()
            if child.is_file()
            and child.suffix == ".py"
            and not child.name.startswith("_")
        )
    return []


def _load_local_channel(resolved: Path, errors: list[PluginLoadError]) -> None:
    """Load every local plugin file the resolved path contributes.

    A configured path that cannot be enumerated -- it is missing, or it is a
    directory that exists but cannot be listed (a permission error from
    ``iterdir()``) -- is one :class:`PluginLoadError` naming the path, after
    which the run continues with whatever is already registered (Req 2.6). Each
    contributed file is then loaded inside its own failure boundary by
    :func:`_load_local_file`.
    """
    if not resolved.exists():
        errors.append(
            PluginLoadError(
                subject=str(resolved),
                detail="local plugin path does not exist or cannot be read",
            )
        )
        return
    try:
        files = _local_files(resolved)
    except OSError as exc:
        errors.append(
            PluginLoadError(
                subject=str(resolved),
                detail=f"local plugin path could not be read: {exc}",
            )
        )
        return
    for file_path in files:
        _load_local_file(file_path, errors)


def _load_local_file(file_path: Path, errors: list[PluginLoadError]) -> None:
    """Execute one local plugin file, attributing and isolating it.

    The file is executed under the reserved module name
    ``fitdocs_local_plugins.<stem>`` via
    :func:`importlib.util.spec_from_file_location` and ``exec_module``;
    ``sys.path`` is never mutated, so each file must be self-contained. The
    file registers its own calculators by calling
    :func:`fitdocs.load.register` itself, exactly as
    ``docs/contributing-calculators.md`` documents; the ids that newly appear
    in the registry across the execution are attributed to this file's path
    (Req 2.1) with an unknown (``None``) version -- never fabricated (Req 4.3).

    Every failure -- an import or syntax error, or an error raised part-way
    through the module -- becomes one :class:`PluginLoadError` named by the
    file's path (Req 2.6). Ids the file registered *before* it raised stay
    registered and attributed, so a partially-loading file still contributes
    what it managed to register.
    """
    before = _registered_ids()
    module_name = f"{LOCAL_MODULE_PREFIX}.{file_path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load local plugin file {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            _attribute_local_ids(before, file_path)
    except registry.DuplicateCalculatorIdError as exc:
        errors.append(
            PluginLoadError(
                subject=str(file_path),
                detail=f"{exc}; kept the {_incumbent_origin_text(exc.calculator_id)}",
            )
        )
    except Exception as exc:
        errors.append(PluginLoadError(subject=str(file_path), detail=str(exc)))


def _incumbent_origin_text(calculator_id: str) -> str:
    """Describe the origin of the calculator already registered under
    ``calculator_id`` -- the incumbent a duplicate registration is rejected in
    favor of, so the load error names *both* origins: the rejected newcomer (the
    error's ``subject``) and the incumbent named here (Req 3.3).

    A built-in incumbent (no plugin origin recorded) is named as such; a plugin
    incumbent is named by its distribution-and-entry-point or its local file
    path. Reads only the already-recorded :data:`_plugin_origins` and the
    validated id string -- never the newcomer's ``__repr__`` -- so it is safe to
    call inside the duplicate-id failure boundary.
    """
    entry = _plugin_origins.get(calculator_id)
    origin: Origin = entry[0] if entry is not None else BuiltIn()
    if isinstance(origin, Distribution):
        return f"registration from {origin.name}: {origin.entry_point}"
    if isinstance(origin, LocalFile):
        return f"registration from local file {origin.path}"
    return "built-in registration"


def _attribute_local_ids(before: set[str], file_path: Path) -> None:
    """Attribute every id that appeared since *before* to *file_path*."""
    for calculator_id in _registered_ids():
        if calculator_id not in before and calculator_id not in _plugin_origins:
            _plugin_origins[calculator_id] = (LocalFile(path=str(file_path)), None)


def _registered_ids() -> set[str]:
    """The ids currently in the registry, for local-file attribution diffing."""
    return {calculator.calculator_id for calculator in registry.available()}
