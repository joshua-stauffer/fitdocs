"""Tests for the read-only ``[plugins]`` settings reader (Req 1.8, 2.1, 2.4, 2.5, 2.7).

These exercise :func:`fitdocs.plugins.load_plugin_settings`, the typed per-table
projection of an *already-parsed* ``<data-root>/fitdocs.toml`` ``[plugins]`` table
onto the :class:`~fitdocs.plugins.PluginSettings` contract (design: "PluginSettings
+ ``load_plugin_settings``", ``src/fitdocs/plugins.py``). It is the settings sibling
of :func:`fitdocs.tiles.tile_settings_from_document`, and these tests mirror
``tests/test_tiles.py``'s structure.

Two invariants govern every case:

* *Absent is the default, never an error.* An empty document -- what the shared
  reader returns for an absent ``fitdocs.toml`` -- or a document with no
  ``[plugins]`` table yields :data:`~fitdocs.plugins.DEFAULT_PLUGIN_SETTINGS`
  (discovery enabled, no local path). Each key defaults independently, so a partial
  ``[plugins]`` table fills only the keys it names (Req 2.5).
* *Malformed fails loudly.* A non-boolean ``enabled`` (Req 1.8), an empty or
  non-string ``path``, or a non-table ``[plugins]`` value raises
  :class:`~fitdocs.plugins.PluginSettingsError` naming the settings file and the
  offending key (Req 2.7). Path *existence* is deliberately not checked -- a missing
  path is a plugin load error (Req 2.6), not a configuration error.

The reader never opens a file: it validates only the mapping it is handed and uses
``settings_file`` only to name the file in errors. Unknown keys within ``[plugins]``
and unknown sibling tables are ignored so the shared file can carry ``[tiles]``,
``[inbox]``, and future tables.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest

from fitdocs import Modality
from fitdocs.load import registry
from fitdocs.load.types import AthleteField, LoadOutcome, Unsupported
from fitdocs.plugins import (
    DEFAULT_PLUGIN_SETTINGS,
    ENTRY_POINT_GROUP,
    BuiltIn,
    Distribution,
    LocalFile,
    PluginInfo,
    PluginLoadError,
    PluginReport,
    PluginSettings,
    PluginSettingsError,
    discover,
    load_plugin_settings,
    reset,
)
from fitdocs.settings import SettingsError

# A representative settings-file path; the reader only ever names it in errors and
# never opens it, so it need not (and here does not) exist on disk.
_SETTINGS_FILE = Path("/vault/fitdocs.toml")


# --- The keyless default (Req 2.5) ------------------------------------------


def test_default_plugin_settings_is_enabled_with_no_local_path() -> None:
    """The keyless default: discovery enabled on both channels, no local path."""
    assert PluginSettings(enabled=True, path=None) == DEFAULT_PLUGIN_SETTINGS


# --- Absent file / table -> defaults (never an error) (Req 2.5) -------------


def test_absent_file_returns_defaults() -> None:
    """An empty document (an absent ``fitdocs.toml``) -> the defaults."""
    assert load_plugin_settings({}, _SETTINGS_FILE) == DEFAULT_PLUGIN_SETTINGS


def test_absent_plugins_table_returns_defaults() -> None:
    """A document with other tables but no ``[plugins]`` -> the defaults."""
    document = {"tiles": {"enabled": False}}
    assert load_plugin_settings(document, _SETTINGS_FILE) == DEFAULT_PLUGIN_SETTINGS


# --- Each key defaults independently (Req 2.5) ------------------------------


def test_partial_table_enabled_only_keeps_default_path() -> None:
    """``[plugins] enabled = false`` alone leaves ``path`` at its default ``None``."""
    settings = load_plugin_settings({"plugins": {"enabled": False}}, _SETTINGS_FILE)
    assert settings == PluginSettings(enabled=False, path=None)


def test_partial_table_path_only_keeps_default_enabled() -> None:
    """``[plugins] path = "p"`` alone leaves ``enabled`` at its default ``True``."""
    settings = load_plugin_settings({"plugins": {"path": "p"}}, _SETTINGS_FILE)
    assert settings == PluginSettings(enabled=True, path="p")


def test_both_keys_present_are_both_read() -> None:
    """Both keys present are both projected onto the settings object."""
    settings = load_plugin_settings(
        {"plugins": {"enabled": False, "path": "calc.py"}}, _SETTINGS_FILE
    )
    assert settings == PluginSettings(enabled=False, path="calc.py")


# --- Loud validation: enabled must be a real bool (Req 1.8, 2.7) ------------


def test_enabled_as_integer_is_rejected() -> None:
    """A TOML integer is not a bool: ``enabled = 1`` is rejected, not coerced."""
    with pytest.raises(PluginSettingsError) as excinfo:
        load_plugin_settings({"plugins": {"enabled": 1}}, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "enabled" in message


def test_enabled_as_string_is_rejected() -> None:
    """``enabled = "true"`` is a string, not a bool -> rejected."""
    with pytest.raises(PluginSettingsError) as excinfo:
        load_plugin_settings({"plugins": {"enabled": "true"}}, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "enabled" in message


# --- Loud validation: path must be a non-empty string (Req 2.7) -------------


def test_empty_path_is_rejected() -> None:
    """An empty ``path`` names nothing loadable -> rejected."""
    with pytest.raises(PluginSettingsError) as excinfo:
        load_plugin_settings({"plugins": {"path": ""}}, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "path" in message


def test_non_string_path_is_rejected() -> None:
    """A non-string ``path`` (here an int) is rejected, never coerced."""
    with pytest.raises(PluginSettingsError) as excinfo:
        load_plugin_settings({"plugins": {"path": 3}}, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "path" in message


def test_non_table_plugins_value_is_rejected() -> None:
    """A scalar where the ``[plugins]`` table belongs is rejected (Req 2.7)."""
    with pytest.raises(PluginSettingsError) as excinfo:
        load_plugin_settings({"plugins": "yes"}, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "plugins" in message


# --- Unknown keys / tables are tolerated (shared file) (Req 2.1) ------------


def test_unknown_key_in_plugins_table_is_ignored() -> None:
    """An unknown key inside ``[plugins]`` is ignored, not an error."""
    settings = load_plugin_settings(
        {"plugins": {"enabled": True, "future_key": "x"}}, _SETTINGS_FILE
    )
    assert settings == PluginSettings(enabled=True, path=None)


def test_unknown_sibling_table_is_ignored() -> None:
    """An unknown top-level table is ignored -- the file is shared."""
    document = {"plugins": {"path": "p"}, "unknown_table": {"k": "v"}}
    settings = load_plugin_settings(document, _SETTINGS_FILE)
    assert settings == PluginSettings(enabled=True, path="p")


# --- Path existence is NOT checked here (Req 2.6 stays a load error) ---------


def test_nonexistent_path_parses_cleanly() -> None:
    """A ``path`` naming something that does not exist still parses (Req 2.6)."""
    settings = load_plugin_settings(
        {"plugins": {"path": "/nowhere/does-not-exist"}}, _SETTINGS_FILE
    )
    assert settings.path == "/nowhere/does-not-exist"


def test_reader_opens_no_file_even_when_settings_file_is_missing() -> None:
    """The reader names ``settings_file`` but never opens it, so a path that does
    not exist on disk is fine -- proving the reader performs no file I/O."""
    missing = Path("/definitely/not/a/real/vault/fitdocs.toml")
    assert not missing.exists()
    settings = load_plugin_settings({"plugins": {"path": "p"}}, missing)
    assert settings == PluginSettings(enabled=True, path="p")


# --- resolved_path: relative vs absolute (Req 2.4) --------------------------


def test_resolved_path_is_none_when_no_path_configured(tmp_path: Path) -> None:
    """No configured ``path`` -> ``resolved_path`` is ``None``."""
    assert DEFAULT_PLUGIN_SETTINGS.resolved_path(tmp_path) is None


def test_relative_path_resolves_against_data_root(tmp_path: Path) -> None:
    """A relative ``path`` resolves under the data root so a vault stays portable."""
    settings = PluginSettings(enabled=True, path="plugins")
    assert settings.resolved_path(tmp_path) == tmp_path / "plugins"


def test_relative_nested_path_resolves_against_data_root(tmp_path: Path) -> None:
    """A relative multi-segment ``path`` also resolves under the data root."""
    settings = PluginSettings(enabled=True, path="sub/calc.py")
    assert settings.resolved_path(tmp_path) == tmp_path / "sub" / "calc.py"


def test_absolute_path_is_used_as_given(tmp_path: Path) -> None:
    """An absolute ``path`` is used verbatim, not re-rooted under the data root."""
    absolute = tmp_path.parent / "elsewhere" / "calc.py"
    settings = PluginSettings(enabled=True, path=str(absolute))
    assert settings.resolved_path(tmp_path) == absolute


# --- Error type integrates with the shared settings boundary (deviation) ----


def test_plugin_settings_error_is_a_settings_error() -> None:
    """``PluginSettingsError`` subclasses the shared ``SettingsError`` so a CLI
    ``except SettingsError`` catches a malformed ``[plugins]`` table too."""
    assert issubclass(PluginSettingsError, SettingsError)
    with pytest.raises(SettingsError):
        load_plugin_settings({"plugins": {"enabled": 1}}, _SETTINGS_FILE)


# =============================================================================
# Discovery: the entry-point channel (task 2.2)
#
# These exercise :func:`fitdocs.plugins.discover` and :func:`fitdocs.plugins.reset`
# -- the entry-point channel only (design: "PluginDiscovery",
# ``src/fitdocs/plugins.py``). Local plugin file/directory loading (task 2.3) and
# per-invocation caching (task 2.4) are intentionally not exercised here: every
# test below passes ``PluginSettings(path=None)`` and calls ``discover()`` fresh.
#
# The autouse ``_reset_plugin_discovery`` fixture in ``tests/conftest.py`` calls
# :func:`reset` around every test in the suite, so these tests never leak plugin
# registrations into each other or into unrelated tests.
# =============================================================================

_BUILTIN_ID = "stub-builtin"


class _FakeDist:
    """A minimal stand-in for ``importlib.metadata.Distribution`` metadata."""

    def __init__(self, name: str, version: str) -> None:
        self.name = name
        self.version = version


class _FakeEntryPoint:
    """A minimal stand-in for ``importlib.metadata.EntryPoint``.

    Exposes exactly what :func:`fitdocs.plugins.discover` touches: ``.name``,
    ``.value``, ``.load()``, and ``.dist``. Not a real ``EntryPoint`` -- the
    design's injected ``entry_points_fn`` parameter exists precisely so tests
    can drive ordering, coercion, and isolation without installing anything.
    """

    def __init__(
        self,
        name: str,
        value: str,
        loader: Any,
        dist: _FakeDist | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self._loader = loader
        self.dist = dist

    def load(self) -> Any:
        return self._loader()


def _entry_points_fn(
    entries: list[_FakeEntryPoint],
) -> Any:
    """Build an ``entry_points_fn`` returning *entries* only for fitdocs' group."""

    def _fn(*, group: str) -> Iterable[_FakeEntryPoint]:
        assert group == ENTRY_POINT_GROUP
        return entries

    return _fn


class _FakeCalculator:
    """A minimal, valid :class:`~fitdocs.load.types.LoadCalculator`.

    ``compute`` carries the real 5-parameter shape (``context`` included) even
    though this module never calls it -- only registers and discovers it --
    so the stub does not silently drift from the actual contract shape.
    """

    def __init__(
        self,
        calculator_id: str = "fake",
        display_name: str = "Fake Calculator",
        modalities: tuple[Modality, ...] = (Modality.RUN,),
    ) -> None:
        self.calculator_id = calculator_id
        self.display_name = display_name
        self.supported_modalities = frozenset(modalities)

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self, activity: Any, metrics: Any, profile: Any, session: Any, context: Any
    ) -> LoadOutcome:
        return Unsupported(reason="fake calculator never computes in tests")


def _calc_class(
    calculator_id: str, modalities: tuple[Modality, ...] = (Modality.BIKE,)
) -> type:
    """A class value an entry point can resolve to (the "class" coercion shape)."""

    class _Calc(_FakeCalculator):
        def __init__(self) -> None:
            super().__init__(calculator_id=calculator_id, modalities=modalities)

    return _Calc


def _calc_instance(
    calculator_id: str, modalities: tuple[Modality, ...] = (Modality.RUN,)
) -> _FakeCalculator:
    """An instance value an entry point can resolve to (the "instance" shape)."""
    return _FakeCalculator(calculator_id=calculator_id, modalities=modalities)


def _calc_factory(
    calculator_id: str, modalities: tuple[Modality, ...] = (Modality.SWIM,)
) -> Any:
    """A zero-argument factory callable (the "factory" coercion shape)."""

    def _factory() -> _FakeCalculator:
        return _FakeCalculator(calculator_id=calculator_id, modalities=modalities)

    return _factory


def _raise_on_import() -> Any:
    raise ImportError("simulated import failure: missing dependency 'widget'")


def _registered_ids() -> tuple[str, ...]:
    return tuple(calculator.calculator_id for calculator in registry.available())


@pytest.fixture(autouse=True)
def _builtin_calculator() -> Iterator[None]:
    """Register a stub calculator directly, standing in for a shipped built-in.

    fitdocs ships no calculator of its own (Amendment 2), so this suite's
    premise -- discovery ordering and attribution around a calculator that is
    *already registered* when ``discover()`` runs -- needs a stand-in. This
    fixture registers one directly (bypassing ``discover()``/``reset()``)
    before every test in this module and unregisters it after, so it always
    occupies the first registry slot exactly as a real built-in would.
    ``discover()`` attributes it ``BuiltIn()`` origin purely because it is
    absent from ``_plugin_origins`` -- origin is assigned by discovery
    channel, never by special-casing an id (design: "TestCalculators",
    cross-spec with ``plugin-api``: the built-in anchor becomes a directly
    registered stub, still attributed a built-in origin).

    The whole registry is snapshotted, cleared, and restored around each test
    -- not just this one id -- so anything a prior test left registered is
    never a second, uncontrolled baseline entry alongside the stub.
    """
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    registry.register(_calc_instance(_BUILTIN_ID, modalities=(Modality.RUN,)))
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)


# --- discover() returns builtins-only with an empty source (Req 1.7, 7.1) ---


def test_no_plugins_reports_builtins_only_and_registry_unchanged() -> None:
    """An empty entry-point source: report and registry hold builtins only."""
    baseline = _registered_ids()
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([]),
    )
    assert isinstance(report, PluginReport)
    assert report.errors == ()
    assert tuple(info.calculator_id for info in report.calculators) == baseline
    assert _registered_ids() == baseline
    assert all(isinstance(info.origin, BuiltIn) for info in report.calculators)


# --- Ordering: builtins first, then (name, dist, value) sorted (Req 1.3) ----


def test_ordering_registers_builtins_first_then_sorted_by_advertised_name() -> None:
    """Deliberately unsorted entries still register in ``(name, dist, value)`` order."""
    zeta = _FakeEntryPoint(
        "zeta",
        "zeta_pkg:Zeta",
        _calc_class("zeta-calc"),
        dist=_FakeDist("zeta-dist", "1.0"),
    )
    alpha = _FakeEntryPoint(
        "alpha",
        "alpha_pkg:Alpha",
        _calc_class("alpha-calc"),
        dist=_FakeDist("alpha-dist", "2.0"),
    )
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([zeta, alpha]),
    )
    assert report.errors == ()
    assert _registered_ids() == (_BUILTIN_ID, "alpha-calc", "zeta-calc")
    assert tuple(info.calculator_id for info in report.calculators) == (
        _BUILTIN_ID,
        "alpha-calc",
        "zeta-calc",
    )


# --- Coercion: class / instance / factory register; module is rejected -----


def test_coercion_class_instance_and_factory_all_register() -> None:
    """Each of the three coercion shapes resolves to a registered calculator."""
    class_ep = _FakeEntryPoint("c-class", "pkg:Class", _calc_class("plugin-class"))
    instance_ep = _FakeEntryPoint(
        "c-instance", "pkg:instance", lambda: _calc_instance("plugin-instance")
    )
    factory_ep = _FakeEntryPoint(
        "c-factory", "pkg:factory", lambda: _calc_factory("plugin-factory")()
    )
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([class_ep, instance_ep, factory_ep]),
    )
    assert report.errors == ()
    assert set(_registered_ids()) == {
        _BUILTIN_ID,
        "plugin-class",
        "plugin-instance",
        "plugin-factory",
    }


def test_coercion_module_value_is_rejected_naming_expected_shapes() -> None:
    """An entry point resolving to a module is rejected, not silently skipped."""
    module_ep = _FakeEntryPoint(
        "bad-module", "pkg:module", lambda: types.ModuleType("pkg")
    )
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([module_ep]),
    )
    assert _registered_ids() == (_BUILTIN_ID,)
    assert len(report.errors) == 1
    error = report.errors[0]
    assert isinstance(error, PluginLoadError)
    assert error.subject == "bad-module"
    assert "class" in error.detail
    assert "factory" in error.detail
    assert "instance" in error.detail


# --- Isolation: the Observable's headline case (Req 3.2, 3.4) ---------------


def test_isolation_failures_reported_healthy_plugins_register_builtin_survives() -> (
    None
):
    """One raising, one non-calculator, one duplicate id -- three errors, healthy
    plugins register after the builtins, the built-in stub is untouched, discover()
    does not raise, and reset() restores builtins only."""
    original_builtin = registry.get(_BUILTIN_ID)

    raising_ep = _FakeEntryPoint(
        "n-raises",
        "broken_pkg:Thing",
        _raise_on_import,
        dist=_FakeDist("broken-dist", "0.1"),
    )
    non_calculator_ep = _FakeEntryPoint(
        "n-bad-shape",
        "shape_pkg:thing",
        lambda: object(),
        dist=_FakeDist("shape-dist", "0.1"),
    )
    duplicate_ep = _FakeEntryPoint(
        "n-duplicate",
        "dup_pkg:Dup",
        lambda: _calc_instance(_BUILTIN_ID),
        dist=_FakeDist("dup-dist", "0.1"),
    )
    healthy_a = _FakeEntryPoint("z-healthy-a", "pkg_a:A", _calc_class("healthy-a"))
    healthy_b = _FakeEntryPoint("z-healthy-b", "pkg_b:B", _calc_class("healthy-b"))

    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn(
            [raising_ep, non_calculator_ep, duplicate_ep, healthy_a, healthy_b]
        ),
    )

    assert len(report.errors) == 3
    subjects = {error.subject for error in report.errors}
    assert subjects == {
        "broken-dist: n-raises",
        "shape-dist: n-bad-shape",
        "dup-dist: n-duplicate",
    }

    assert _registered_ids() == (_BUILTIN_ID, "healthy-a", "healthy-b")
    assert registry.get(_BUILTIN_ID) is original_builtin

    reset()
    assert _registered_ids() == (_BUILTIN_ID,)
    assert registry.get(_BUILTIN_ID) is original_builtin


# --- Duplicate id: the load error names BOTH origins (Req 3.3) ---------------


def test_duplicate_entry_point_id_load_error_names_the_incumbent_builtin() -> None:
    """A plugin claiming the shipped id is rejected with a load error naming
    BOTH origins: the rejected newcomer (the error ``subject``) and the built-in
    incumbent (named in ``detail``) -- Req 3.3's 'names the id and both origins',
    with the incumbent left in place."""
    duplicate_ep = _FakeEntryPoint(
        "n-dup",
        "pkg:Dup",
        lambda: _calc_instance(_BUILTIN_ID),
        dist=_FakeDist("fitdocs-dup", "1.0.0"),
    )
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([duplicate_ep]),
    )

    assert _registered_ids() == (_BUILTIN_ID,)
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.subject == "fitdocs-dup: n-dup"  # the rejected newcomer origin
    assert _BUILTIN_ID in error.detail  # the contested id
    assert "built-in" in error.detail  # the incumbent origin


def test_duplicate_id_load_error_names_the_incumbent_distribution() -> None:
    """When the incumbent is itself a plugin, the duplicate's load error names
    that plugin's distribution origin, not merely 'built-in' (Req 3.3)."""
    first = _FakeEntryPoint(
        "a-first",
        "pkg:First",
        lambda: _calc_instance("shared-id"),
        dist=_FakeDist("fitdocs-first", "2.0.0"),
    )
    second = _FakeEntryPoint(
        "b-second",
        "pkg:Second",
        lambda: _calc_instance("shared-id"),
        dist=_FakeDist("fitdocs-second", "3.0.0"),
    )
    # 'a-first' sorts before 'b-second', so first wins the id and second loses.
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([first, second]),
    )

    assert "shared-id" in _registered_ids()
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.subject == "fitdocs-second: b-second"  # rejected newcomer
    assert "shared-id" in error.detail  # the contested id
    assert "fitdocs-first" in error.detail  # the incumbent distribution


def test_local_duplicate_id_load_error_names_the_incumbent(tmp_path: Path) -> None:
    """A local plugin file registering an already-taken id is rejected with a
    load error naming the incumbent origin -- exercising
    ``DuplicateCalculatorIdError.calculator_id``, since the local channel does
    not otherwise hold the offending id (Req 3.3)."""
    plugins_dir = tmp_path / "plugins"
    dup_path = _write_plugin_file(plugins_dir, "dup.py", _plugin_source(_BUILTIN_ID))

    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert _registered_ids() == (_BUILTIN_ID,)
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.subject == str(dup_path)  # the rejected newcomer file
    assert _BUILTIN_ID in error.detail  # the contested id
    assert "built-in" in error.detail  # the incumbent origin


# --- Provenance / version (Req 4.2, 4.3) ------------------------------------


def test_distribution_plugin_records_distribution_origin_and_version() -> None:
    """A distribution-backed entry records ``Distribution`` and its version."""
    ep = _FakeEntryPoint(
        "prov",
        "prov_pkg:Prov",
        _calc_class("prov-calc", modalities=(Modality.BIKE, Modality.RUN)),
        dist=_FakeDist("fitdocs-prov", "3.2.1"),
    )
    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([ep]),
    )
    info_by_id = {info.calculator_id: info for info in report.calculators}
    prov_info = info_by_id["prov-calc"]
    assert isinstance(prov_info, PluginInfo)
    assert prov_info.origin == Distribution(name="fitdocs-prov", entry_point="prov")
    assert prov_info.version == "3.2.1"
    assert prov_info.modalities == ("bike", "run")


def test_builtin_records_builtin_origin_and_installed_fitdocs_version() -> None:
    """The shipped builtin records ``BuiltIn()`` and the installed fitdocs version."""
    import importlib.metadata

    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([]),
    )
    builtin_info = next(
        info for info in report.calculators if info.calculator_id == _BUILTIN_ID
    )
    assert builtin_info.origin == BuiltIn()
    assert builtin_info.version == importlib.metadata.version("fitdocs")
    assert builtin_info.modalities == tuple(sorted(builtin_info.modalities))


def test_builtin_version_is_none_rather_than_unknown_token_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The built-in's reported version stays ``None`` -- never the fabricated
    ``"unknown"`` display token -- when the distribution is not installed
    (Req 2.4, plugin-api Req 4.3: the listing forbids fabricating a version).

    ``_plugin_info`` must call :func:`fitdocs.version.tool_version` directly,
    not :func:`fitdocs.version.version_display`, which would substitute the
    token here.
    """
    import importlib.metadata

    import fitdocs.version as version_module

    def _raise(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "version", _raise)

    report = discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([]),
    )
    builtin_info = next(
        info for info in report.calculators if info.calculator_id == _BUILTIN_ID
    )
    assert builtin_info.version is None


# --- Disable switch (Req 1.8) ------------------------------------------------


def test_disabled_settings_loads_nothing_even_with_a_populated_source() -> None:
    """``enabled=False`` loads no entry point; report is builtins only."""
    baseline = _registered_ids()
    populated_ep = _FakeEntryPoint(
        "would-load", "pkg:Would", _calc_class("would-register")
    )
    report = discover(
        None,
        PluginSettings(enabled=False, path=None),
        entry_points_fn=_entry_points_fn([populated_ep]),
    )
    assert report.errors == ()
    assert _registered_ids() == baseline
    assert tuple(info.calculator_id for info in report.calculators) == baseline


# --- reset() -----------------------------------------------------------------


def test_reset_unregisters_exactly_the_plugin_ids_never_a_builtin() -> None:
    """``reset()`` unregisters only the ids attributed to a plugin channel."""
    ep = _FakeEntryPoint("to-reset", "pkg:ToReset", _calc_class("to-reset-calc"))
    discover(
        None,
        PluginSettings(enabled=True, path=None),
        entry_points_fn=_entry_points_fn([ep]),
    )
    assert "to-reset-calc" in _registered_ids()
    reset()
    assert _registered_ids() == (_BUILTIN_ID,)


def test_reset_with_nothing_to_undo_is_a_safe_no_op() -> None:
    """Calling ``reset()`` with no prior discovery does nothing harmful."""
    baseline = _registered_ids()
    reset()
    assert _registered_ids() == baseline


# =============================================================================
# Discovery: the local plugin file/directory channel (task 2.3)
#
# These exercise the local half of :func:`fitdocs.plugins.discover` -- loading
# a user-configured local plugin file or directory (design: "PluginDiscovery",
# "Local-file resolution", ``src/fitdocs/plugins.py``). Every case passes a
# real ``entry_points_fn`` returning no entries, isolating the local channel
# from the entry-point channel task 2.2 already covers.
# =============================================================================


def _plugin_source(calculator_id: str, modality: str = "RUN") -> str:
    """Self-contained source for a healthy local calculator file.

    Registers itself via ``fitdocs.load.register`` on import, exactly as
    ``docs/contributing-calculators.md`` documents. No import of the test
    module itself -- the file must stand alone when ``exec_module``'d under
    the reserved namespace.
    """
    return f'''\
from fitdocs import Modality
from fitdocs.load import Unsupported, register


class _LocalCalculator:
    calculator_id = "{calculator_id}"
    display_name = "{calculator_id} calculator"
    supported_modalities = frozenset({{Modality.{modality}}})

    def required_athlete_fields(self):
        return ()

    def compute(self, activity, metrics, profile, session, context):
        return Unsupported(reason="test calculator never computes")


register(_LocalCalculator())
'''


def _broken_plugin_source() -> str:
    """Source for a local file that raises at import time, registering nothing."""
    return "raise RuntimeError('simulated local plugin import failure')\n"


def _partial_then_raise_source(calculator_id: str) -> str:
    """Source that registers one calculator, then raises mid-import."""
    return _plugin_source(calculator_id) + (
        "\nraise RuntimeError('simulated mid-import failure after registering')\n"
    )


def _write_plugin_file(directory: Path, filename: str, source: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / filename
    file_path.write_text(source)
    return file_path


def _no_entry_points() -> Any:
    return _entry_points_fn([])


# --- The headline Observable (Req 2.1, 2.2, 2.6) -----------------------------


def test_local_headline_order_skip_underscore_and_isolation(tmp_path: Path) -> None:
    """Two healthy files register in filename order, the underscore-prefixed
    helper is skipped, and exactly one error names the failing file."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "a.py", _plugin_source("local-a"))
    _write_plugin_file(plugins_dir, "b.py", _plugin_source("local-b"))
    _write_plugin_file(plugins_dir, "_helper.py", _plugin_source("helper-calc"))
    broken_path = _write_plugin_file(plugins_dir, "broken.py", _broken_plugin_source())

    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert _registered_ids() == (_BUILTIN_ID, "local-a", "local-b")
    assert tuple(info.calculator_id for info in report.calculators) == (
        _BUILTIN_ID,
        "local-a",
        "local-b",
    )
    assert "helper-calc" not in _registered_ids()

    assert len(report.errors) == 1
    error = report.errors[0]
    assert isinstance(error, PluginLoadError)
    assert error.subject == str(broken_path)


# --- Single-file path (Req 2.3) ----------------------------------------------


def test_single_file_path_loads_exactly_that_file(tmp_path: Path) -> None:
    """A ``path`` naming one file loads exactly that file."""
    directory = tmp_path / "calcs"
    file_path = _write_plugin_file(directory, "solo.py", _plugin_source("solo-calc"))

    settings = PluginSettings(enabled=True, path=str(file_path))
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert _registered_ids() == (_BUILTIN_ID, "solo-calc")


# --- Relative path resolves under the data root (Req 2.4) -------------------


def test_relative_directory_path_resolves_under_data_root(tmp_path: Path) -> None:
    """A relative ``path`` names a directory resolved under the data root."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "rel.py", _plugin_source("rel-calc"))

    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert "rel-calc" in _registered_ids()


def test_absolute_directory_path_is_used_as_given(tmp_path: Path) -> None:
    """An absolute ``path`` loads from that directory, not re-rooted."""
    elsewhere = tmp_path / "elsewhere"
    _write_plugin_file(elsewhere, "abs.py", _plugin_source("abs-calc"))
    data_root = tmp_path / "data-root"
    data_root.mkdir()

    settings = PluginSettings(enabled=True, path=str(elsewhere))
    report = discover(data_root, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert "abs-calc" in _registered_ids()


# --- No subdirectory descent (Req 2.2) ---------------------------------------


def test_directory_does_not_descend_into_subdirectories(tmp_path: Path) -> None:
    """A ``.py`` file nested in a subdirectory of the plugin dir is not loaded."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "top.py", _plugin_source("top-calc"))
    nested_dir = plugins_dir / "nested"
    _write_plugin_file(nested_dir, "deep.py", _plugin_source("deep-calc"))

    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert _registered_ids() == (_BUILTIN_ID, "top-calc")
    assert "deep-calc" not in _registered_ids()


# --- Missing/unreadable path (Req 2.6) ---------------------------------------


def test_missing_local_path_records_one_error_and_continues(tmp_path: Path) -> None:
    """A configured ``path`` that does not exist -> one error naming it; the run
    continues with built-ins registered and no other anomaly raised here."""
    missing = tmp_path / "does-not-exist"
    settings = PluginSettings(enabled=True, path="does-not-exist")

    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert _registered_ids() == (_BUILTIN_ID,)
    assert len(report.errors) == 1
    error = report.errors[0]
    assert isinstance(error, PluginLoadError)
    assert str(missing) in error.subject


def test_unreadable_directory_records_one_error_and_continues(tmp_path: Path) -> None:
    """A directory that exists but cannot be listed -> one error naming it and a
    normal return, never a ``PermissionError`` propagating out of ``discover()``
    (Req 2.6's "cannot be read" for the directory case)."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "would.py", _plugin_source("would-register"))
    plugins_dir.chmod(0o000)
    try:
        # If the OS still lets us list it (e.g. running as root), the case under
        # test cannot occur -- skip rather than assert a false guarantee.
        try:
            next(iter(plugins_dir.iterdir()), None)
            skip = True
        except OSError:
            skip = False
        if skip:
            pytest.skip("directory remained listable despite chmod 000 (likely root)")

        settings = PluginSettings(enabled=True, path="plugins")
        report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

        assert _registered_ids() == (_BUILTIN_ID,)
        assert len(report.errors) == 1
        error = report.errors[0]
        assert isinstance(error, PluginLoadError)
        assert error.subject == str(plugins_dir)
    finally:
        plugins_dir.chmod(0o755)


# --- Partial registration kept on a mid-import raise (Req 2.6, 3.2) ---------


def test_partial_registration_survives_a_mid_import_raise(tmp_path: Path) -> None:
    """A file that registers one calculator and then raises keeps that
    calculator registered, attributed to the file, and records one error."""
    plugins_dir = tmp_path / "plugins"
    broken_path = _write_plugin_file(
        plugins_dir, "partial.py", _partial_then_raise_source("partial-calc")
    )

    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert "partial-calc" in _registered_ids()
    info_by_id = {info.calculator_id: info for info in report.calculators}
    assert info_by_id["partial-calc"].origin == LocalFile(path=str(broken_path))

    assert len(report.errors) == 1
    assert report.errors[0].subject == str(broken_path)


# --- Provenance: LocalFile origin, version None, sorted modalities (Req 4.2, 4.3) --


def test_local_calculator_records_local_file_origin_and_none_version(
    tmp_path: Path,
) -> None:
    """A locally-loaded calculator's origin is ``LocalFile`` and its version is
    ``None`` -- never fabricated."""
    plugins_dir = tmp_path / "plugins"
    file_path = _write_plugin_file(
        plugins_dir, "prov.py", _plugin_source("prov-local", modality="BIKE")
    )

    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    info_by_id = {info.calculator_id: info for info in report.calculators}
    prov_info = info_by_id["prov-local"]
    assert prov_info.origin == LocalFile(path=str(file_path))
    assert prov_info.version is None
    assert prov_info.modalities == tuple(sorted(prov_info.modalities))


# --- reset() unregisters local ids, keeps built-ins --------------------------


def test_reset_unregisters_local_plugin_ids(tmp_path: Path) -> None:
    """``reset()`` unregisters a local file's ids and leaves built-ins alone."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "toreset.py", _plugin_source("local-to-reset"))

    settings = PluginSettings(enabled=True, path="plugins")
    discover(tmp_path, settings, entry_points_fn=_no_entry_points())
    assert "local-to-reset" in _registered_ids()

    reset()
    assert _registered_ids() == (_BUILTIN_ID,)


# --- sys.path is never mutated (design: Technology Stack "Local loading") ----


def test_local_loading_never_mutates_sys_path(tmp_path: Path) -> None:
    """Local plugin loading never appends to or otherwise mutates ``sys.path``."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "syspath.py", _plugin_source("syspath-calc"))

    before = list(sys.path)
    settings = PluginSettings(enabled=True, path="plugins")
    discover(tmp_path, settings, entry_points_fn=_no_entry_points())
    after = list(sys.path)

    assert before == after


# --- Disable switch also disables the local channel (Req 1.8) --------------


def test_disabled_settings_loads_no_local_plugin_either(tmp_path: Path) -> None:
    """``enabled=False`` skips the local channel even with a populated directory."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "would.py", _plugin_source("would-register-local"))

    settings = PluginSettings(enabled=False, path="plugins")
    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert _registered_ids() == (_BUILTIN_ID,)


# --- Local channel is skipped entirely when data_root is None (Req 4.7) ------


def test_local_channel_skipped_when_data_root_is_none(tmp_path: Path) -> None:
    """A ``None`` data root -- the degraded ``plugins``-listing path -- skips the
    local channel entirely rather than erroring."""
    # A populated path is configured, but discover() is called without a data
    # root, so there is nothing to resolve it against.
    settings = PluginSettings(enabled=True, path="plugins")
    report = discover(None, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert _registered_ids() == (_BUILTIN_ID,)


# =============================================================================
# Discovery: per-invocation caching (task 2.4)
#
# These exercise the caching layer of :func:`fitdocs.plugins.discover`: the
# first discover() for a given (data_root, settings) pair runs normally, a
# later call naming the SAME pair returns the cached report without
# re-registering anything, and a call naming a DIFFERENT pair is a new
# invocation -- the previous registrations are dropped (via reset()) and
# discovery runs again (design: "PluginDiscovery", "State Management";
# Req 1.2).
# =============================================================================


def test_identical_calls_return_equal_report_and_register_once(
    tmp_path: Path,
) -> None:
    """Two identical ``discover()`` calls (same data_root + settings) return an
    EQUAL report, and the plugin id is registered exactly once -- the second
    call re-registers nothing and records no duplicate-id error."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "cached.py", _plugin_source("cached-calc"))
    settings = PluginSettings(enabled=True, path="plugins")

    first = discover(tmp_path, settings, entry_points_fn=_no_entry_points())
    second = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert first == second
    assert first.errors == ()
    assert second.errors == ()
    assert _registered_ids() == (_BUILTIN_ID, "cached-calc")


def test_different_data_root_is_a_new_invocation(tmp_path: Path) -> None:
    """A second ``discover()`` naming a DIFFERENT data root drops the first
    root's local plugin and registers the second root's instead -- proving
    reset-on-key-change rather than silent cache reuse."""
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    _write_plugin_file(root_a / "plugins", "a.py", _plugin_source("root-a-calc"))
    _write_plugin_file(root_b / "plugins", "b.py", _plugin_source("root-b-calc"))
    settings = PluginSettings(enabled=True, path="plugins")

    report_a = discover(root_a, settings, entry_points_fn=_no_entry_points())
    assert "root-a-calc" in _registered_ids()

    report_b = discover(root_b, settings, entry_points_fn=_no_entry_points())

    assert "root-a-calc" not in _registered_ids()
    assert _registered_ids() == (_BUILTIN_ID, "root-b-calc")
    assert tuple(info.calculator_id for info in report_b.calculators) == (
        _BUILTIN_ID,
        "root-b-calc",
    )
    assert report_a != report_b


def test_reset_clears_the_cache_so_an_identical_call_rediscovers(
    tmp_path: Path,
) -> None:
    """``reset()`` clears the cache too: after a cached ``discover()``,
    ``reset()``, then an identical ``discover()`` re-runs discovery and
    re-registers the plugin (report still correct, id present exactly once)."""
    plugins_dir = tmp_path / "plugins"
    _write_plugin_file(plugins_dir, "again.py", _plugin_source("again-calc"))
    settings = PluginSettings(enabled=True, path="plugins")

    discover(tmp_path, settings, entry_points_fn=_no_entry_points())
    reset()
    assert _registered_ids() == (_BUILTIN_ID,)

    report = discover(tmp_path, settings, entry_points_fn=_no_entry_points())

    assert report.errors == ()
    assert _registered_ids() == (_BUILTIN_ID, "again-calc")
