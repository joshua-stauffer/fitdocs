"""Tests for the ``[load]`` settings reader (Req 10.1, 10.2, 14.1, 14.2, 14.3, 14.6).

This exercises :func:`fitdocs.load.settings.load_load_settings`, the *single*
per-table projection of an already-parsed ``<data-root>/fitdocs.toml`` ``[load]``
table onto the :class:`~fitdocs.load.settings.LoadSettings` contract (design:
"LoadSettings", ``src/fitdocs/load/settings.py``). It is pinned by Amendment 3
of the training-load spec: four sibling specs (``athlete-benchmarks``,
``load-channels``, ``threshold-load``, ``activity-qa-flags``) each extend this
exact module and this exact test file rather than opening a second reader or a
second test module.

Two invariants govern every case:

* *Every field is defaulted, so absent is never an error.* An empty document
  -- what the shared reader returns for an absent ``fitdocs.toml`` -- or a
  document with no ``[load]`` table yields
  :data:`~fitdocs.load.settings.DEFAULT_LOAD_SETTINGS`. Constructing
  :class:`~fitdocs.load.settings.LoadSettings` with no arguments always equals
  that default -- the additivity guard that reddens the moment a sibling spec
  adds an undefaulted field (Req 14.2).
* *Malformed fails loudly, and unknown is tolerated.* A non-table ``[load]``
  value, or a non-string/empty ``default_calculator``, raises
  :class:`~fitdocs.load.settings.LoadSettingsError` naming the settings file
  and the offending key (Req 14.6). Unknown keys inside ``[load]`` *and*
  unknown sub-tables beneath it are ignored (Req 14.3) -- the additivity
  contract that lets ``[load.sufficiency]``, ``[load.priority]`` and
  ``[load.flags]`` land without ever touching this reader.

The reader never opens a file: it validates only the mapping it is handed and
uses ``settings_file`` only to name the file in errors. Whether the configured
identifier is *registered* is deliberately not checked here (that is an
arbitration concern).
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from types import MappingProxyType

import pytest
from typer.testing import CliRunner

from fitdocs import Modality
from fitdocs.cli import app
from fitdocs.load import registry
from fitdocs.load import settings as load_settings_module
from fitdocs.load.channels.types import (
    DEFAULT_MIN_DURATION_S,
    DEFAULT_MIN_STREAM_COVERAGE,
    ChannelId,
    SufficiencySettings,
)
from fitdocs.load.priority import DEFAULT_CHANNEL_PRIORITY, ChannelPriority
from fitdocs.load.settings import (
    DEFAULT_LOAD_SETTINGS,
    LoadSettings,
    LoadSettingsError,
    load_load_settings,
)
from fitdocs.load.types import (
    Activity,
    AthleteField,
    Computed,
    DerivedMetrics,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
)
from fitdocs.model import Sport
from fitdocs.settings import SettingsError
from tests.fixtures import builder

# A representative settings-file path; the reader only ever names it in errors
# and never opens it, so it need not (and here does not) exist on disk.
_SETTINGS_FILE = Path("/vault/fitdocs.toml")


# --- The keyless default / additivity guard (Req 14.2) -----------------------


def test_default_load_settings_is_keyless_default_calculator_none() -> None:
    """The keyless default: no default calculator configured."""
    assert LoadSettings(default_calculator=None) == DEFAULT_LOAD_SETTINGS


def test_no_argument_construction_equals_module_default() -> None:
    """``LoadSettings()`` with no arguments equals ``DEFAULT_LOAD_SETTINGS``.

    This is the additivity guard four sibling specs depend on: a sibling
    adding a field must default it, or this assertion reddens.
    """
    assert LoadSettings() == DEFAULT_LOAD_SETTINGS


def test_default_staleness_window_is_84_days() -> None:
    """The documented staleness-window default is pinned to the literal 84."""
    assert DEFAULT_LOAD_SETTINGS.benchmark_staleness_days == 84


# --- Absent file / table -> defaults (never an error) (Req 14.2) -------------


def test_absent_file_returns_defaults() -> None:
    """An empty document (an absent ``fitdocs.toml``) -> the defaults."""
    assert load_load_settings({}, _SETTINGS_FILE) == DEFAULT_LOAD_SETTINGS


def test_absent_load_table_returns_defaults() -> None:
    """A document with other tables but no ``[load]`` -> the defaults."""
    document = {"tiles": {}, "plugins": {"enabled": False}}
    assert load_load_settings(document, _SETTINGS_FILE) == DEFAULT_LOAD_SETTINGS


# --- A valid key resolves (Req 10.1, 10.2) ------------------------------------


def test_configured_default_calculator_is_read() -> None:
    """A valid ``default_calculator`` string resolves onto the dataclass."""
    document = {"load": {"default_calculator": "threshold"}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


def test_absent_staleness_key_returns_documented_default() -> None:
    """A present ``[load]`` table without ``benchmark_staleness_days`` -> 84."""
    document = {"load": {"default_calculator": "threshold"}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.benchmark_staleness_days == 84


def test_configured_staleness_window_is_read() -> None:
    """A valid, non-default ``benchmark_staleness_days`` resolves onto the dataclass."""
    document = {"load": {"benchmark_staleness_days": 30}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(benchmark_staleness_days=30)
    assert result.benchmark_staleness_days == 30


# --- Malformed fails loudly, naming file and key (Req 14.6) ------------------


def test_non_table_load_value_is_rejected() -> None:
    document = {"load": "not-a-table"}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "load" in message


def test_non_string_default_calculator_is_rejected() -> None:
    document = {"load": {"default_calculator": 5}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "default_calculator" in message


def test_empty_string_default_calculator_is_rejected() -> None:
    document = {"load": {"default_calculator": ""}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "default_calculator" in message


def test_non_integer_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": "84"}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "84" in body


def test_float_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": 84.5}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "84.5" in body


def test_boolean_staleness_window_is_rejected() -> None:
    """``bool`` is an ``int`` subclass in Python -- must be rejected on its own."""
    document = {"load": {"benchmark_staleness_days": True}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "True" in body


def test_zero_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": 0}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "0" in body


def test_negative_staleness_window_is_rejected() -> None:
    document = {"load": {"benchmark_staleness_days": -7}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert "benchmark_staleness_days" in body
    assert "-7" in body


# --- [load.sufficiency] projection (Req 3.1-3.8, task 2.3) -------------------


def test_default_load_settings_sufficiency_equals_keyless_sufficiency_settings() -> (
    None
):
    """Pins the derivation, not a retyped literal: the default sufficiency
    member of :data:`DEFAULT_LOAD_SETTINGS` is exactly a keyless
    :class:`SufficiencySettings`, which in turn is built from that module's
    own default constants -- so mutating either module's constant reddens
    this rather than a hand-copied number here."""
    assert DEFAULT_LOAD_SETTINGS.sufficiency == SufficiencySettings()
    assert DEFAULT_LOAD_SETTINGS.sufficiency.min_duration_s == DEFAULT_MIN_DURATION_S
    assert (
        DEFAULT_LOAD_SETTINGS.sufficiency.min_stream_coverage
        == DEFAULT_MIN_STREAM_COVERAGE
    )
    assert DEFAULT_LOAD_SETTINGS.sufficiency.power_min_stream_coverage is None
    assert DEFAULT_LOAD_SETTINGS.sufficiency.hr_min_stream_coverage is None
    assert DEFAULT_LOAD_SETTINGS.sufficiency.pace_min_stream_coverage is None


def test_absent_sufficiency_sub_table_returns_documented_defaults() -> None:
    """A present ``[load]`` table with no ``[load.sufficiency]`` -> defaults."""
    document = {"load": {"default_calculator": "threshold"}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency == SufficiencySettings()


def test_empty_sufficiency_sub_table_returns_documented_defaults() -> None:
    """A present, empty ``[load.sufficiency]`` table -> the same defaults."""
    document = {"load": {"sufficiency": {}}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency == SufficiencySettings()


def test_shared_min_duration_and_coverage_are_read() -> None:
    document = {
        "load": {"sufficiency": {"min_duration_s": 120, "min_stream_coverage": 0.5}}
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency == SufficiencySettings(
        min_duration_s=120, min_stream_coverage=0.5
    )


def test_min_stream_coverage_accepts_value_of_exactly_one() -> None:
    """The documented range is inclusive at its top: exactly 1.0 is valid."""
    document = {"load": {"sufficiency": {"min_stream_coverage": 1.0}}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency.min_stream_coverage == 1.0


def test_three_per_channel_overrides_are_read_and_kept_distinct() -> None:
    """Pairwise-distinct per-channel values, permuted, so a wrong-channel
    assignment (e.g. power's value landing on hr) would redden this."""
    document = {
        "load": {
            "sufficiency": {
                "power_min_stream_coverage": 0.9,
                "hr_min_stream_coverage": 0.6,
                "pace_min_stream_coverage": 0.75,
            }
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency.power_min_stream_coverage == 0.9
    assert result.sufficiency.hr_min_stream_coverage == 0.6
    assert result.sufficiency.pace_min_stream_coverage == 0.75
    # a permutation of the same three values would not equal this result
    assert result.sufficiency != SufficiencySettings(
        power_min_stream_coverage=0.6,
        hr_min_stream_coverage=0.75,
        pace_min_stream_coverage=0.9,
    )


def test_unset_per_channel_overrides_stay_none() -> None:
    """An override absent from the sub-table stays ``None`` -- 'use the
    shared value' -- even when the shared minimum itself is configured."""
    document = {"load": {"sufficiency": {"min_stream_coverage": 0.65}}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency.power_min_stream_coverage is None
    assert result.sufficiency.hr_min_stream_coverage is None
    assert result.sufficiency.pace_min_stream_coverage is None


def test_unknown_key_inside_sufficiency_sub_table_parses_cleanly() -> None:
    document = {
        "load": {"sufficiency": {"min_duration_s": 90, "made_up_key": "ignored"}}
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.sufficiency == SufficiencySettings(min_duration_s=90)


# --- [load.sufficiency] malformed values (Req 3.4, 3.5, 3.6) -----------------


def test_non_table_sufficiency_value_is_rejected() -> None:
    document = {"load": {"sufficiency": "not-a-table"}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "sufficiency" in message


@pytest.mark.parametrize(
    "key",
    [
        "min_stream_coverage",
        "power_min_stream_coverage",
        "hr_min_stream_coverage",
        "pace_min_stream_coverage",
    ],
)
def test_non_numeric_coverage_is_rejected(key: str) -> None:
    document = {"load": {"sufficiency": {key: "high"}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert str(_SETTINGS_FILE) in str(excinfo.value)
    assert key in body
    assert "high" in body


@pytest.mark.parametrize(
    "key",
    [
        "min_stream_coverage",
        "power_min_stream_coverage",
        "hr_min_stream_coverage",
        "pace_min_stream_coverage",
    ],
)
def test_boolean_coverage_is_rejected(key: str) -> None:
    """``bool`` is an ``int`` subclass in Python -- must be rejected on its own."""
    document = {"load": {"sufficiency": {key: True}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert key in body
    assert "True" in body


@pytest.mark.parametrize(
    "key",
    [
        "min_stream_coverage",
        "power_min_stream_coverage",
        "hr_min_stream_coverage",
        "pace_min_stream_coverage",
    ],
)
def test_zero_coverage_is_rejected(key: str) -> None:
    """The range is above zero: 0.0 itself is out of range."""
    document = {"load": {"sufficiency": {key: 0.0}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert key in body
    assert "0.0" in body


@pytest.mark.parametrize(
    "key",
    [
        "min_stream_coverage",
        "power_min_stream_coverage",
        "hr_min_stream_coverage",
        "pace_min_stream_coverage",
    ],
)
def test_above_one_coverage_is_rejected(key: str) -> None:
    """The range is at or below one: anything greater is out of range."""
    document = {"load": {"sufficiency": {key: 1.01}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert key in body
    assert "1.01" in body


def test_non_integer_min_duration_s_is_rejected() -> None:
    document = {"load": {"sufficiency": {"min_duration_s": "60"}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    assert str(_SETTINGS_FILE) in str(excinfo.value)  # Req 3.5: names the file
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert "min_duration_s" in body
    assert "60" in body


def test_float_min_duration_s_is_rejected() -> None:
    document = {"load": {"sufficiency": {"min_duration_s": 60.5}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    assert str(_SETTINGS_FILE) in str(excinfo.value)  # Req 3.5: names the file
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert "min_duration_s" in body
    assert "60.5" in body


def test_boolean_min_duration_s_is_rejected() -> None:
    """``bool`` is an ``int`` subclass in Python -- must be rejected on its own."""
    document = {"load": {"sufficiency": {"min_duration_s": True}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    assert str(_SETTINGS_FILE) in str(excinfo.value)  # Req 3.5: names the file
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert "min_duration_s" in body
    assert "True" in body


def test_zero_min_duration_s_is_rejected() -> None:
    document = {"load": {"sufficiency": {"min_duration_s": 0}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    assert str(_SETTINGS_FILE) in str(excinfo.value)  # Req 3.5: names the file
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert "min_duration_s" in body
    assert "0" in body


def test_negative_min_duration_s_is_rejected() -> None:
    document = {"load": {"sufficiency": {"min_duration_s": -30}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    assert str(_SETTINGS_FILE) in str(excinfo.value)  # Req 3.5: names the file
    body = str(excinfo.value).replace(str(_SETTINGS_FILE), "<path>")
    assert "min_duration_s" in body
    assert "-30" in body


# --- Single-reader (Req 3.7) is covered by the module-wide sweeps below.
# "Opens no file of its own" (task bullet) is NOT covered by those sweeps --
# they pin that no *second reader of [load]* exists, which is orthogonal to
# whether *this* projection helper itself touches the filesystem. Pinned
# directly below instead.


def test_setting_sufficiency_opens_no_file_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``_setting_sufficiency`` (and everything it calls) must not read,
    open, or locate a settings file itself -- the task bullet says so
    explicitly, and the enclosing reader's own docstring already claims
    "never opens a file" for the whole of ``load_load_settings``.

    Uses a settings-file path that genuinely EXISTS on disk with real
    content, not ``_SETTINGS_FILE`` (``/vault/fitdocs.toml``, which never
    exists here) -- an ``if settings_file.exists(): settings_file.read_text(...)``
    inserted into the reader is a real violation of "opens no file of its
    own" in production (where the settings file routinely exists), but is
    invisible to a test whose path never exists: the ``exists()`` guard
    short-circuits before the monkeypatched raise is ever reached, so
    ``_SETTINGS_FILE`` alone cannot discriminate that mutation (measured,
    round 1 of remediation). This makes any filesystem read a hard failure
    by monkeypatching every read entry point this process actually has:
    ``Path.read_text``, ``Path.read_bytes``, ``Path.open``, builtin
    ``open`` -- and, round 2 of remediation, ``os.open`` and ``io.open``
    too, both missed round 1: ``io.open`` is *the same function object*
    builtin ``open`` is bound to, but ``monkeypatch.setattr("builtins.open",
    ...)`` only rebinds the name in the ``builtins`` module's namespace, not
    the separate, independent binding of that same object under
    ``io.open`` -- a stray ``io.open(settings_file)`` survives patching
    ``builtins.open`` alone. Against a settings file that is real and
    present, this then exercises every branch of ``[load.sufficiency]`` --
    absent, empty, populated, and malformed (caught) -- confirming none of
    them touch the filesystem even though the file is right there to touch.
    """
    settings_file = tmp_path / "fitdocs.toml"
    settings_file.write_text("[load]\n", encoding="utf-8")
    assert settings_file.exists()  # sanity: the exists()-gate would fire here

    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("load_load_settings must not touch the filesystem")

    monkeypatch.setattr(Path, "read_text", _forbidden)
    monkeypatch.setattr(Path, "read_bytes", _forbidden)
    monkeypatch.setattr(Path, "open", _forbidden)
    monkeypatch.setattr("builtins.open", _forbidden)
    monkeypatch.setattr("os.open", _forbidden)
    monkeypatch.setattr("io.open", _forbidden)

    assert load_load_settings({}, settings_file) == DEFAULT_LOAD_SETTINGS
    assert (
        load_load_settings({"load": {"sufficiency": {}}}, settings_file)
        == LoadSettings()
    )
    assert load_load_settings(
        {"load": {"sufficiency": {"min_duration_s": 90, "min_stream_coverage": 0.5}}},
        settings_file,
    ).sufficiency == SufficiencySettings(min_duration_s=90, min_stream_coverage=0.5)
    with pytest.raises(LoadSettingsError):
        load_load_settings({"load": {"sufficiency": "nope"}}, settings_file)


def test_sufficiency_settings_dependency_runs_settings_to_channel_types() -> None:
    """The dependency runs settings -> channel types, never the reverse
    (design note): the settings module imports ``SufficiencySettings`` from
    ``fitdocs.load.channels.types``, which is a plain leaf value type that
    itself imports no settings machinery.

    What this does and does not pin: the substring scan below is a coarse
    supplementary check, not the real guard against that module acquiring a
    settings dependency -- it is blind to e.g. ``from fitdocs import
    settings as s`` (no ``"fitdocs.settings"`` or ``"load.settings"``
    substring). The actual kill for that edge is task 1.2's own guard in
    ``tests/load/channels/test_types.py``, which this module does not
    duplicate. The vacuity assertion below at least confirms this scan is
    reading real, non-empty module source rather than passing on an empty
    string.
    """
    assert load_settings_module.SufficiencySettings is SufficiencySettings
    import fitdocs.load.channels.types as channels_types

    source = Path(channels_types.__file__).read_text(encoding="utf-8")
    assert "class SufficiencySettings" in source  # vacuity: real source, not empty
    assert "fitdocs.settings" not in source
    assert "load.settings" not in source


# --- Integration: a configuration error in [load.sufficiency] terminates the
# load pass before any document is written (Req 3.8) -------------------------


class _FieldFreeCalculator:
    """A RUN-only calculator requiring no athlete input, so it reaches
    ``Computed`` under ``CliRunner``'s non-interactive (``--no-prompt``)
    session with no scripted answers needed -- duplicated per test module
    from ``tests/load/test_cli_load.py``'s identical local class by this
    suite's own established convention, rather than imported, so this module
    stays a leaf that owns its own fixtures.

    Round 2 of remediation: every stub in ``tests.load.conftest``
    (including :class:`~tests.load.conftest.ComputingCalculator`, used here
    in round 1) declares a required athlete field, so forcing one of those
    under ``--no-prompt`` lands in ``MissingInputs`` and writes nothing even
    on an otherwise-valid pass -- exactly why the round-1 version of the
    write-suppression control below could not fail for the reason it
    existed. This calculator requires nothing, so a ``--no-prompt`` CLI
    invocation against a *valid* ``[load.sufficiency]`` genuinely reaches
    ``Computed`` and writes real bytes, through the *same* CLI entry point
    (``fitdocs load --out ... --no-prompt``) the invalid-config assertion
    itself uses -- not a different one, closing the "different entry point"
    gap in round 1's Half A.
    """

    calculator_id = "stub-field-free-settings"
    display_name = "Stub Field-Free Calculator (settings module)"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=42.0,
                basis="stub field-free basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


def test_invalid_sufficiency_value_in_data_root_aborts_load_pass_before_writing(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """An invalid ``[load.sufficiency]`` value in a real data root's
    ``fitdocs.toml`` makes ``fitdocs load`` exit at the configuration exit
    (2) before any document is created or modified -- exercising the same
    upstream wiring ``apply_load`` already uses for ``benchmark_staleness_days``
    (Req 3.8, relies on inherited engine behavior: the ``[load]`` table is
    read and validated in full before any document is scanned).

    A same-shaped *valid* config against the same fixture and calculator
    would also exit 0 with zero bytes changed if the calculator declines or
    is never reached -- so a naive "before == after" alone cannot
    distinguish "terminated before writing" from "had nothing to write".
    Half A measures the control directly: the *valid*-config run, through
    the identical CLI invocation (``fitdocs load --out ... --no-prompt``)
    Half B uses, registers :class:`_FieldFreeCalculator` (requires no
    athlete input, so it reaches ``Computed`` under ``--no-prompt`` with no
    prompting needed) and asserts bytes actually change. Half B then asserts
    the *invalid*-config run through that same path changes nothing.
    """
    runner = CliRunner()
    calc = _FieldFreeCalculator()
    try:
        # --- Half A: the control -- a VALID config through the same CLI
        # path must actually write, or Half B's negative result is vacuous.
        #
        # Registration happens AFTER sync, deliberately: ``fitdocs sync``
        # itself runs the load pass once as part of the sync command
        # (``cli.py``'s ``sync_command`` calls ``_run_load_pass``). Measured:
        # registering the calculator before ``_sync_one_run`` let *sync's
        # own* internal load pass compute the document, so the doc was
        # already ``COMPUTED`` before the ``load`` invocation below ever
        # ran -- that invocation then correctly reported ``Computed 0`` and
        # changed no bytes, for the *right* reason on the wrong statement:
        # it was a no-op restore of an already-correct result, not evidence
        # the ``load`` command's own path can write. Registering after sync
        # leaves the region in the honest ``unsupported`` state sync writes
        # with no calculator available, so the CLI ``load`` invocation is
        # the one that actually performs the write being measured.
        valid_root = tmp_path / "valid"
        valid_root.mkdir()
        _sync_one_run(tmp_path / "src_a", valid_root)
        before_valid = {
            p: p.read_bytes() for p in sorted(valid_root.rglob("*")) if p.is_file()
        }
        (valid_root / "fitdocs.toml").write_text(
            "[load.sufficiency]\nmin_stream_coverage = 0.5\n", encoding="utf-8"
        )
        registry.register(calc)

        valid_run = runner.invoke(
            app, ["load", "--out", str(valid_root), "--no-prompt"]
        )
        assert valid_run.exit_code == 0, valid_run.output
        assert "Computed" in valid_run.output
        after_valid = {
            p: p.read_bytes() for p in sorted(valid_root.rglob("*")) if p.is_file()
        }
        before_valid[valid_root / "fitdocs.toml"] = (
            valid_root / "fitdocs.toml"
        ).read_bytes()
        assert after_valid != before_valid, (
            "sanity: a valid-config run through this exact CLI path must "
            "change at least one byte, or the invalid-config assertion "
            "below cannot distinguish 'aborted before writing' from 'had "
            "nothing to write'"
        )

        # --- Half B: the real assertion -- invalid config writes nothing --
        # Same ordering discipline: sync first (registry empty), then
        # register, then the config-error ``load`` invocation.
        invalid_root = tmp_path / "invalid"
        invalid_root.mkdir()
        registry.unregister(calc.calculator_id)
        _sync_one_run(tmp_path / "src_b", invalid_root)
        before_invalid = {
            p: p.read_bytes() for p in sorted(invalid_root.rglob("*")) if p.is_file()
        }
        settings_file = invalid_root / "fitdocs.toml"
        settings_file.write_text(
            "[load.sufficiency]\nmin_stream_coverage = 1.5\n", encoding="utf-8"
        )
        registry.register(calc)

        invalid_run = runner.invoke(
            app, ["load", "--out", str(invalid_root), "--no-prompt"]
        )
        assert invalid_run.exit_code == 2, invalid_run.output
        after_invalid = {
            p: p.read_bytes() for p in sorted(invalid_root.rglob("*")) if p.is_file()
        }
        # settings_file itself was written by this test, not by the load
        # pass; exclude it from the "nothing changed" comparison.
        before_invalid[settings_file] = settings_file.read_bytes()
        assert after_invalid == before_invalid
    finally:
        registry.unregister(calc.calculator_id)


def _sync_one_run(source: Path, data_root: Path) -> None:
    """Sync a single running fixture into ``data_root`` via the real CLI
    pipeline and assert exactly one workout document lands, for the two
    halves of the integration test above."""
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    runner = CliRunner()
    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0, synced.output
    docs = sorted(
        p for p in (data_root / "workouts").glob("*.md") if p.stem[:4].isdigit()
    )
    assert len(docs) == 1, f"expected exactly one workout document, found {docs}"


# --- [load.priority] projection (Req 7.1-7.9, task 1.2) ----------------------


def test_default_load_settings_channel_priority_equals_keyless_channel_priority() -> (
    None
):
    """The default ``channel_priority`` member of :data:`DEFAULT_LOAD_SETTINGS`
    agrees in value with a keyless :class:`ChannelPriority` and with
    :data:`DEFAULT_CHANNEL_PRIORITY`.

    What this pins and what it does not: it catches a settings default whose
    *content* stops matching the priority module's table -- an empty default,
    or a differently-ordered one (measured: ``default_factory=lambda:
    ChannelPriority(by_discipline={})`` reds this and four more). It does
    **not** catch a hand-copied literal equal to that table, in either module,
    because both sides of both assertions dereference the same constant
    (measured: replacing either ``default_factory`` with an equal literal
    leaves the whole suite green). Nor is it a mutation test of
    :data:`DEFAULT_CHANNEL_PRIORITY`'s *contents* -- that is
    :mod:`tests.load.test_priority`'s job."""
    assert DEFAULT_LOAD_SETTINGS.channel_priority == ChannelPriority()
    assert DEFAULT_LOAD_SETTINGS.channel_priority.by_discipline == (
        DEFAULT_CHANNEL_PRIORITY
    )


def test_absent_priority_sub_table_returns_documented_defaults() -> None:
    """A present ``[load]`` table with no ``[load.priority]`` -> the
    documented default order for every supported discipline (Req 7.3, 7.4)."""
    document = {"load": {"default_calculator": "threshold"}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.channel_priority == ChannelPriority()
    for sport in (Sport.RUN, Sport.RIDE, Sport.WALK, Sport.HIKE):
        assert (
            result.channel_priority.for_discipline(sport)
            == DEFAULT_CHANNEL_PRIORITY[sport]
        )
        assert len(result.channel_priority.for_discipline(sport)) >= 1


def test_empty_priority_sub_table_returns_documented_defaults() -> None:
    """A present, empty ``[load.priority]`` table -> the same defaults."""
    document = {"load": {"priority": {}}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.channel_priority == ChannelPriority()


def test_configured_entry_overrides_default_for_its_discipline_only() -> None:
    """A configured order -- deliberately the reverse of the documented
    default for ride -- overrides only ride; run, walk and hike keep their
    own documented defaults untouched (Req 7.3, 7.4). Using an order that
    differs from the default is deliberate: a fixture whose configured value
    equals the default would pin nothing about override behavior."""
    assert DEFAULT_CHANNEL_PRIORITY[Sport.RIDE] == (
        ChannelId.POWER,
        ChannelId.HEART_RATE,
    )
    document = {
        "load": {"priority": {"ride": ["heart_rate", "power"]}},
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.channel_priority.for_discipline(Sport.RIDE) == (
        ChannelId.HEART_RATE,
        ChannelId.POWER,
    )
    for sport in (Sport.RUN, Sport.WALK, Sport.HIKE):
        assert (
            result.channel_priority.for_discipline(sport)
            == DEFAULT_CHANNEL_PRIORITY[sport]
        )


def test_all_four_disciplines_are_independently_configurable() -> None:
    """Each of the four supported disciplines accepts its own configured
    order, and each ends up on its own discipline (not shuffled, not
    shared) -- a pairwise-distinct fixture per Req 3.2's sibling
    convention above, so a wrong-discipline assignment (e.g. walk and hike
    swapped) would redden this. All four orders below are valid per Req
    7.9 (a futile order is accepted, not an error) and no two disciplines
    share the same value, so a mixup between any pair is detectable."""
    document = {
        "load": {
            "priority": {
                "run": ["power"],
                "ride": ["pace"],
                "walk": ["heart_rate", "power"],
                "hike": ["power", "heart_rate"],
            }
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.channel_priority.for_discipline(Sport.RUN) == (ChannelId.POWER,)
    assert result.channel_priority.for_discipline(Sport.RIDE) == (ChannelId.PACE,)
    assert result.channel_priority.for_discipline(Sport.WALK) == (
        ChannelId.HEART_RATE,
        ChannelId.POWER,
    )
    assert result.channel_priority.for_discipline(Sport.HIKE) == (
        ChannelId.POWER,
        ChannelId.HEART_RATE,
    )
    # Implied by the four assertions above -- kept as documentation of the
    # substitution the pairwise-distinct fixture exists to defeat, not as
    # independent coverage: no reader mutation reds this without reddening
    # one of them first.
    assert result.channel_priority != ChannelPriority(
        by_discipline=MappingProxyType(
            {
                Sport.RUN: (ChannelId.POWER,),
                Sport.RIDE: (ChannelId.PACE,),
                Sport.WALK: (ChannelId.POWER, ChannelId.HEART_RATE),
                Sport.HIKE: (ChannelId.HEART_RATE, ChannelId.POWER),
            }
        )
    )


def test_futile_configured_order_is_accepted_not_an_error() -> None:
    """Req 7.9: a valid-but-futile order -- pace configured for cycling, a
    channel the calculator never computes for that discipline -- is accepted
    without complaint. This reader validates only that the named channel is
    one of the three recognized identifiers, never whether it can ever
    produce a value for the discipline it is configured under."""
    document = {"load": {"priority": {"ride": ["pace"]}}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.channel_priority.for_discipline(Sport.RIDE) == (ChannelId.PACE,)


# --- [load.priority] malformed values (Req 7.5, 7.6, 7.7) --------------------


def test_non_table_priority_value_is_rejected() -> None:
    document = {"load": {"priority": "not-a-table"}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "priority" in message
    assert "not-a-table" in message


def test_unrecognized_discipline_key_is_rejected() -> None:
    """A key that names no ``Sport`` at all (Req 7.5, first form)."""
    document = {"load": {"priority": {"cycling": ["power"]}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "cycling" in message
    assert "run" in message  # names the supported disciplines


def test_unsupported_sport_key_is_rejected() -> None:
    """A key that names a recognized ``Sport`` this calculator does not
    support -- swim, rowing, workout -- is rejected the same way an
    unrecognized name is (Req 7.5, second form): distinct fixture from the
    unrecognized-name case above so each guard is reached on its own."""
    document = {"load": {"priority": {"swim": ["power"]}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "swim" in message
    assert "run" in message  # names the supported disciplines


def test_non_list_priority_value_is_rejected() -> None:
    document = {"load": {"priority": {"run": "power"}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "run" in message
    # Deliberately checks the QUOTED, whole-string repr rather than a bare
    # "power" substring: "power" is also one of the *recognized* channel
    # names this reader would list if it instead (wrongly) iterated the
    # string char-by-char and rejected the first character as an
    # unrecognized channel -- a bare substring check cannot tell "the
    # offending value was reported" from "the word 'power' merely appears
    # somewhere in this unrelated error", so it would pass vacuously
    # against that wrong implementation (measured).
    assert "'power'" in message
    assert "must be a list" in message


def test_non_string_element_is_rejected() -> None:
    document = {"load": {"priority": {"run": [5, "power"]}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "run" in message
    # Deliberately requires the *type*-rejection wording, not merely "some
    # LoadSettingsError naming 5" -- an implementation that drops this
    # element's own type guard but still coincidentally raises through the
    # "unrecognized channel" guard below it (because a non-string element
    # is never a key of the recognized-channel mapping either) would also
    # produce a LoadSettingsError naming "5" and "run", so that alone pins
    # nothing about *this* guard specifically (measured: deleting only the
    # ``isinstance(element, str)`` check, while keeping the unrecognized-
    # channel guard, left a bare "5"/"run" assertion here green). The
    # "entries must be strings" wording only comes from this guard's own
    # branch, not from the unrecognized-channel one.
    assert "entries must be strings" in message
    assert "int" in message
    assert "5" in message


def test_unrecognized_channel_name_is_rejected() -> None:
    """Req 7.6: the message names the file, the key, the offending value,
    and the recognized channels."""
    document = {"load": {"priority": {"run": ["cadence"]}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "run" in message
    assert "cadence" in message
    assert "recognized channels" in message
    for name in ("power", "heart_rate", "pace"):
        assert name in message


def test_repeated_channel_is_rejected() -> None:
    document = {"load": {"priority": {"run": ["power", "power"]}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "run" in message
    assert "power" in message


def test_empty_priority_list_is_rejected() -> None:
    """Req 7.7: the message names the file, the key, the offending
    value (the empty list itself), and this guard's own wording."""
    document = {"load": {"priority": {"run": []}}}
    with pytest.raises(LoadSettingsError) as excinfo:
        load_load_settings(document, _SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(_SETTINGS_FILE) in message
    assert "run" in message
    assert "must not be empty" in message
    assert "[]" in message


# --- 7.8: validated before any document is written ---------------------------


def test_invalid_priority_value_in_data_root_aborts_load_pass_before_writing(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """An invalid ``[load.priority]`` value in a real data root's
    ``fitdocs.toml`` makes ``fitdocs load`` exit at the configuration exit
    (2) before any document is created or modified (Req 7.8) -- mirrors
    :func:`test_invalid_sufficiency_value_in_data_root_aborts_load_pass_before_writing`
    above, exercising the same upstream wiring for a different ``[load.*]``
    sub-table. Half A (a *valid* ``[load.priority]`` config through the
    identical CLI path) is the control proving a write can happen at all, so
    Half B's "nothing changed" is not vacuous.
    """
    runner = CliRunner()
    calc = _FieldFreeCalculator()
    try:
        valid_root = tmp_path / "valid"
        valid_root.mkdir()
        _sync_one_run(tmp_path / "src_a", valid_root)
        before_valid = {
            p: p.read_bytes() for p in sorted(valid_root.rglob("*")) if p.is_file()
        }
        (valid_root / "fitdocs.toml").write_text(
            '[load.priority]\nrun = ["power", "pace"]\n', encoding="utf-8"
        )
        registry.register(calc)

        valid_run = runner.invoke(
            app, ["load", "--out", str(valid_root), "--no-prompt"]
        )
        assert valid_run.exit_code == 0, valid_run.output
        assert "Computed" in valid_run.output
        after_valid = {
            p: p.read_bytes() for p in sorted(valid_root.rglob("*")) if p.is_file()
        }
        before_valid[valid_root / "fitdocs.toml"] = (
            valid_root / "fitdocs.toml"
        ).read_bytes()
        assert after_valid != before_valid, (
            "sanity: a valid-config run through this exact CLI path must "
            "change at least one byte, or the invalid-config assertion "
            "below cannot distinguish 'aborted before writing' from 'had "
            "nothing to write'"
        )

        invalid_root = tmp_path / "invalid"
        invalid_root.mkdir()
        registry.unregister(calc.calculator_id)
        _sync_one_run(tmp_path / "src_b", invalid_root)
        before_invalid = {
            p: p.read_bytes() for p in sorted(invalid_root.rglob("*")) if p.is_file()
        }
        settings_file = invalid_root / "fitdocs.toml"
        settings_file.write_text("[load.priority]\nrun = []\n", encoding="utf-8")
        registry.register(calc)

        invalid_run = runner.invoke(
            app, ["load", "--out", str(invalid_root), "--no-prompt"]
        )
        assert invalid_run.exit_code == 2, invalid_run.output
        after_invalid = {
            p: p.read_bytes() for p in sorted(invalid_root.rglob("*")) if p.is_file()
        }
        before_invalid[settings_file] = settings_file.read_bytes()
        assert after_invalid == before_invalid
    finally:
        registry.unregister(calc.calculator_id)


# --- Additivity: [load.priority] alongside its siblings (design.md Validation)


def test_priority_sufficiency_flags_and_default_calculator_parse_cleanly() -> None:
    """A document carrying ``[load.priority]``, ``[load.sufficiency]``,
    ``[load.flags]`` (an unlanded sibling table) and ``default_calculator``
    together parses cleanly, each sub-table validated independently --
    design.md's own stated additivity guard from this side."""
    document = {
        "load": {
            "default_calculator": "threshold",
            "priority": {"ride": ["heart_rate", "power"]},
            "sufficiency": {"min_duration_s": 120},
            "flags": {"staleness_days": 30},
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result.default_calculator == "threshold"
    assert result.sufficiency == SufficiencySettings(min_duration_s=120)
    assert result.channel_priority.for_discipline(Sport.RIDE) == (
        ChannelId.HEART_RATE,
        ChannelId.POWER,
    )
    # unconfigured disciplines keep their documented defaults even though
    # this document configures other [load.*] sub-tables too
    assert (
        result.channel_priority.for_discipline(Sport.RUN)
        == DEFAULT_CHANNEL_PRIORITY[Sport.RUN]
    )


# --- Additivity: unknown keys and unknown sub-tables ignored (Req 14.3) ------


def test_unknown_key_in_load_table_is_ignored() -> None:
    document = {"load": {"default_calculator": "threshold", "made_up_key": 42}}
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


def test_two_unknown_downstream_sub_tables_parse_cleanly() -> None:
    """Two sub-tables not yet owned by this reader parse without error.

    ``[load.flags]`` (``activity-qa-flags``, not yet landed in this
    checkout) is a genuinely-owned-but-unrecognized-here sub-table.
    ``[load.qa]`` is a synthetic, never-owned name used only to stand in
    for "a sub-table this reader has never heard of" -- ``activity-qa-flags``
    does not read a ``[load.qa]`` table. Both land additively without
    touching this module. ``[load.priority]`` (``threshold-load``) is now a
    *recognized* sub-table (this task) and is exercised on its own above,
    not here.
    """
    document = {
        "load": {
            "default_calculator": "threshold",
            "qa": {"cadence_lock_threshold": 0.5},
            "flags": {"staleness_days": 30},
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


def test_unknown_sub_table_alongside_configured_staleness_is_ignored() -> None:
    """An unknown ``[load.*]`` sub-table does not shadow the staleness key.

    ``[load.sufficiency]`` and ``[load.priority]`` are now *recognized*
    sub-tables (this task and its predecessor), so this uses ``[load.flags]``
    (``activity-qa-flags``, not yet landed in this checkout) as the
    genuinely-unknown one instead.
    """
    document = {
        "load": {
            "benchmark_staleness_days": 30,
            "flags": {"staleness_days": 30},
        }
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(benchmark_staleness_days=30)


def test_unknown_sibling_table_outside_load_is_ignored() -> None:
    """A sibling top-level table (``[tiles]``) alongside ``[load]`` is ignored."""
    document = {
        "tiles": {"some_tile": {}},
        "load": {"default_calculator": "threshold"},
    }
    result = load_load_settings(document, _SETTINGS_FILE)
    assert result == LoadSettings(default_calculator="threshold")


# --- The error is a configuration error the CLI already maps (Req 14.6) -----


def test_load_settings_error_is_a_settings_error() -> None:
    assert issubclass(LoadSettingsError, SettingsError)


# --- Import direction: this module does not import types.py at runtime ------
# (corrected 2026-07-25 by the import-direction ruling; Req 14.7. Rewritten
# round 1 of remediation: the previous subprocess/sys.modules-isolation
# version stopped discriminating once this task added the sanctioned
# ``fitdocs.load.channels.types`` import -- any ``fitdocs.load.*`` submodule
# import necessarily triggers the parent package's pre-existing eager
# ``registry -> types`` chain, landing ``fitdocs.load.types`` in
# ``sys.modules`` regardless of what ``settings.py`` itself does.)
#
# Two guards below, because neither subsumes the other:
#
# * A **static** AST walk (``_forbidden_load_types_imports``) resolving
#   every import form -- absolute, relative (``from .types import X`` /
#   ``from ..types import X``), and the "import the parent, reach the
#   submodule as an attribute" form (``from fitdocs.load import types``) --
#   to its fully-qualified target via ``importlib.util.resolve_name``,
#   rather than a literal ``node.module == "fitdocs.load.types"`` string
#   match. A literal match is exactly the defect this spec's own
#   Implementation Notes record shipping green on task 1.2: it is blind to
#   any spelling that does not literally write the four-token dotted name in
#   the ``ImportFrom.module`` slot.
# * A **runtime** guard (``test_settings_module_leaks_no_dynamic_import_of_load_types``)
#   that pre-seeds stub packages and execs ``settings.py`` off disk, because
#   a dynamic import (``importlib.import_module("fitdocs.load.types")``) has
#   no distinguishing AST shape at all -- a static walk cannot see it by
#   construction, regardless of how thorough its resolution logic is.


def _forbidden_load_types_imports(
    source: str, *, package: str = "fitdocs.load"
) -> tuple[list[str], bool]:
    """Every import in ``source`` that resolves to ``fitdocs.load.types``,
    plus whether the source also contains the one sanctioned import this
    task adds (``fitdocs.load.channels.types``) -- the vacuity signal that
    proves this function inspected real content rather than trivially
    passing on empty or unrelated source.

    Resolves three static forms to their fully-qualified target:

    * ``import fitdocs.load.types`` (or ``as`` any alias) -- absolute,
      matched directly against the dotted name.
    * ``from fitdocs.load.types import ...`` -- absolute ``ImportFrom``,
      matched directly against ``node.module``.
    * ``from .types import ...`` / ``from ..types import ...`` -- relative
      ``ImportFrom`` (``node.level > 0``), resolved via
      ``importlib.util.resolve_name`` against ``package`` (this module's own
      ``__package__``, ``"fitdocs.load"``) exactly as the real import system
      would resolve it at runtime.
    * ``from fitdocs.load import types`` -- the parent package imported and
      the submodule reached as one of its attributes/names, rather than
      imported by its own dotted path. Caught by checking whether the
      resolved module *is* ``"fitdocs.load"`` (or ``"fitdocs.load.channels"``
      for the one-level-deeper sibling form) and ``"types"`` is among the
      names imported from it.

    Does **not** resolve a dynamic import (``importlib.import_module(...)``,
    ``__import__(...)``, or any string built at runtime) -- no static walk
    can, by construction; that is why the runtime companion guard exists
    alongside this one.
    """
    tree = ast.parse(source)
    forbidden: list[str] = []
    saw_sanctioned_import = False

    def _resolve(node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        dots = "." * node.level
        name = dots + (node.module or "")
        try:
            return importlib.util.resolve_name(name, package)
        except ImportError:
            return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fitdocs.load.types":
                    forbidden.append(f"import fitdocs.load.types (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve(node)
            imported_names = {alias.name for alias in node.names}
            if resolved == "fitdocs.load.types":
                spelling = ("." * node.level) + (node.module or "")
                forbidden.append(
                    f"from {spelling} import ... "
                    f"(resolves to fitdocs.load.types, line {node.lineno})"
                )
            elif resolved == "fitdocs.load" and "types" in imported_names:
                forbidden.append(f"from fitdocs.load import types (line {node.lineno})")
            elif (
                resolved == "fitdocs.load.channels.types"
                and "SufficiencySettings" in imported_names
            ):
                saw_sanctioned_import = True

    return forbidden, saw_sanctioned_import


def test_settings_module_does_not_import_load_types_at_runtime() -> None:
    """``settings.py`` never directly imports ``fitdocs.load.types`` -- the
    one edge Req 14.7 forbids (``LoadContext.settings``'s reference back to
    :class:`LoadSettings` must stay ``TYPE_CHECKING``-only on *that*
    module's side, never a runtime import the other way here).

    Uses :func:`_forbidden_load_types_imports` against ``settings.py``'s own
    source on disk, resolving every static import form rather than matching
    one literal spelling -- see that function's docstring and
    :func:`test_load_types_import_detection_catches_the_four_reported_spellings`
    for the spellings this closes and the one it structurally cannot
    (a dynamic import, closed instead by
    :func:`test_settings_module_leaks_no_dynamic_import_of_load_types`
    below).
    """
    settings_path = (
        Path(__file__).resolve().parents[2] / "src" / "fitdocs" / "load" / "settings.py"
    )
    source = settings_path.read_text(encoding="utf-8")
    forbidden, saw_sanctioned_import = _forbidden_load_types_imports(source)
    assert saw_sanctioned_import, (
        "vacuity check failed: did not find this task's own sanctioned "
        "'from fitdocs.load.channels.types import SufficiencySettings' -- "
        "the scan is not inspecting settings.py's real content"
    )
    assert forbidden == [], (
        f"settings.py must not import fitdocs.load.types directly: {forbidden}"
    )


def test_load_types_import_detection_catches_the_four_reported_spellings() -> None:
    """Fixture-discrimination companion for
    :func:`_forbidden_load_types_imports`, run against synthetic sources
    rather than by hand-editing and reverting the real shipped module -- the
    same convention
    :func:`test_literal_load_table_detection_catches_the_reported_spellings`
    below already uses for the sibling single-reader walk.

    Of the four spellings named in review round 1, **three** actually
    escaped the previous literal-``node.module``-match version of this
    guard: two are closed here, and the third is closed by the runtime
    companion instead.

    Closed here (static, ``ast.ImportFrom``-resolvable):

    * ``from fitdocs.load import types as _lt`` (the parent-package-then-
      attribute form)
    * ``from .types import LoadContext as _LC`` (relative, level 1)

    Closed by :func:`test_settings_module_leaks_no_dynamic_import_of_load_types`
    instead, not this function: ``importlib.import_module("fitdocs.load.types")``
    -- no static AST walk can see a dynamically-constructed import by
    construction.

    A fourth offender, ``import fitdocs.load.types`` (a plain
    ``ast.Import``, not ``ast.ImportFrom``), is added here too -- not one of
    the three that escaped review round 1 (the previous literal-match guard
    already caught this exact spelling), but its own offender because the
    previous version of this companion had no ``ast.Import`` fixture at
    all, so deleting that clause from the detector left the full suite
    green (measured, round 2 of remediation).

    ``from fitdocs.load.types import LoadContext as _LC2`` is included as a
    **positive control**: the previous literal-match guard already caught
    this exact spelling too; it is kept here so a future edit cannot
    silently narrow the walk back to missing it.

    Two controls guard the detector's own signal integrity rather than only
    its positive hits:

    * A negative control (the real, sanctioned
      ``from fitdocs.load.channels.types import SufficiencySettings`` alone)
      proves a future widening of the walk cannot start flagging the
      legitimate import.
    * A vacuity-negative control (an offender with **no** sanctioned import
      present at all) proves ``saw_sanctioned_import`` is a real read of the
      source, not a value that is always ``True`` regardless of content --
      measured: hard-coding ``saw_sanctioned_import = True`` inside
      :func:`_forbidden_load_types_imports` leaves every *other* assertion
      in this test suite green and is caught only by this one.
    """
    sanctioned_import = "from fitdocs.load.channels.types import SufficiencySettings\n"

    offenders = {
        "parent_then_attribute": (
            sanctioned_import + "from fitdocs.load import types as _lt\n"
        ),
        "relative_level_1": sanctioned_import
        + "from .types import LoadContext as _LC\n",
        "plain_ast_import": sanctioned_import + "import fitdocs.load.types\n",
    }
    for label, source in offenders.items():
        forbidden, saw_sanctioned_import = _forbidden_load_types_imports(source)
        assert saw_sanctioned_import, f"{label}: vacuity check itself failed"
        assert forbidden != [], f"{label}: offending import was not caught"

    # positive control: the one spelling the previous literal-match guard
    # already caught -- must still be caught after the resolver rewrite.
    positive_control_source = (
        sanctioned_import + "from fitdocs.load.types import LoadContext as _LC2\n"
    )
    positive_control_forbidden, positive_control_saw = _forbidden_load_types_imports(
        positive_control_source
    )
    assert positive_control_saw
    assert positive_control_forbidden != []

    negative_control_forbidden, negative_control_saw = _forbidden_load_types_imports(
        sanctioned_import
    )
    assert negative_control_saw
    assert negative_control_forbidden == [], (
        f"false positive on the sanctioned import alone: {negative_control_forbidden}"
    )

    # vacuity-negative control: no sanctioned import anywhere in the source,
    # so the vacuity signal itself must read False, not always True.
    vacuity_negative_forbidden, vacuity_negative_saw = _forbidden_load_types_imports(
        "from fitdocs.load import types as _lt\n"
    )
    assert not vacuity_negative_saw, (
        "vacuity signal is not discriminating: reported True with no "
        "sanctioned import anywhere in the source"
    )
    assert vacuity_negative_forbidden != []  # still catches the real offense


def test_settings_module_leaks_no_dynamic_import_of_load_types(
    tmp_path: Path,
) -> None:
    """Runtime companion to the static walk above, closing spellings no AST
    walk can see (a dynamic ``importlib.import_module("fitdocs.load.types")``,
    a lazy function-body import).

    Execs ``settings.py`` directly off disk under a synthetic module name in
    a subprocess, with ``fitdocs.load`` and ``fitdocs.load.channels`` first
    seeded in ``sys.modules`` as stub packages carrying their **real**
    ``__path__`` (round 2 of remediation -- an empty ``__path__ = []`` made
    every ``fitdocs.load.*`` resolution, forbidden or not, die with
    ``ImportError``/``ModuleNotFoundError`` during ``exec_module`` itself,
    so ``assert not leaked`` was unreachable for every violating spelling
    and the guard's actual, sole discriminator was
    ``completed.returncode == 0`` -- which reds identically for a genuine
    violation, an unrelated ``fitdocs.load.*`` import, and a plain typo, so
    it could not tell any of them apart. Measured: with the real path, a
    forbidden module-level import resolves successfully, lands in
    ``sys.modules``, and is caught by the actual ``assert not leaked`` this
    docstring claims) and ``fitdocs.load.channels.types`` seeded with a
    stand-in ``SufficiencySettings`` -- so this task's own sanctioned
    ``from fitdocs.load.channels.types import SufficiencySettings`` resolves
    against the stub rather than triggering the real package's own
    ``registry -> types`` chain (which would otherwise land the real
    ``fitdocs.load.types`` in ``sys.modules`` regardless of what
    ``settings.py`` itself does, making this guard unable to discriminate --
    exactly the defect the previous version of
    :func:`test_settings_module_does_not_import_load_types_at_runtime`
    round-tripped through). After exec, asserts ``fitdocs.load.types``
    never landed in ``sys.modules``.

    A lazy, function-body import (``def f(): from fitdocs.load.types import
    X``) is caught by the static walk above (it inspects the whole AST, not
    only module level) but is structurally invisible here: this guard only
    execs the module's top level and never calls anything defined inside
    it, so a deferred import inside a function body never runs. Measured
    directly (not via a companion test below -- the only synthetic-source
    companion in this module, at
    :func:`test_literal_load_table_detection_catches_the_reported_spellings`,
    belongs to the sibling single-reader walk, not this one): inserting such
    a lazy import into ``settings.py`` reddens the static walk above as a
    sole failure and leaves this runtime guard green -- the concrete case
    proving "neither guard subsumes the other" rather than merely asserting
    it.
    """
    repo_root = Path(__file__).resolve().parents[2]
    settings_path = repo_root / "src" / "fitdocs" / "load" / "settings.py"
    load_src_dir = repo_root / "src" / "fitdocs" / "load"
    channels_src_dir = load_src_dir / "channels"
    script = f"""
import sys
import types
import importlib.util

pkg_load = types.ModuleType("fitdocs.load")
pkg_load.__path__ = [{str(load_src_dir)!r}]
sys.modules["fitdocs.load"] = pkg_load

pkg_channels = types.ModuleType("fitdocs.load.channels")
pkg_channels.__path__ = [{str(channels_src_dir)!r}]
sys.modules["fitdocs.load.channels"] = pkg_channels

stub_types_mod = types.ModuleType("fitdocs.load.channels.types")


class SufficiencySettings:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


import enum


class ChannelId(str, enum.Enum):
    POWER = "power"
    HEART_RATE = "heart_rate"
    PACE = "pace"


stub_types_mod.SufficiencySettings = SufficiencySettings
stub_types_mod.ChannelId = ChannelId
sys.modules["fitdocs.load.channels.types"] = stub_types_mod

spec = importlib.util.spec_from_file_location(
    "_isolated_load_settings", {str(settings_path)!r}
)
module = importlib.util.module_from_spec(spec)
sys.modules["_isolated_load_settings"] = module
spec.loader.exec_module(module)

leaked = [m for m in sys.modules if m == "fitdocs.load.types"]
assert not leaked, f"leaked={{leaked!r}}"
print("OK")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK" in completed.stdout


# --- Single-reader rule (task 6.4, Req 14.1): package-wide, not just the CLI -
#
# ``tests/test_cli.py::test_cli_module_holds_no_load_settings_type_or_reader``
# already pins this for the command surface specifically (task 4.2). This is
# the module's own docstring obligation stated more broadly: "no second
# reader of ``[load]`` may exist *anywhere in the tool*" -- so the guard below
# scans every module under ``src/fitdocs``, not only ``cli.py``.
#
# A resolution-based AST walk rather than a literal import match, per task
# 4.2's finding that ``ast.ImportFrom`` module-name matching is defeated by
# alternate spellings: this instead looks for a *call site* naming
# ``load_load_settings`` -- as a bare name (``load_load_settings(...)``) or as
# an attribute access (``anything.load_load_settings(...)``) -- and, per task
# 6.4 round 3, any per-file ``from ... import load_load_settings as <alias>``
# binding, matched against that file's own alias set rather than the literal
# string. This is spelling-proof to a plain ``from x import y`` / ``from x
# import y as z`` / ``import x`` then ``x.load_load_settings(...)`` -- but
# not to every spelling; see below.
#
# It is not proof against every spelling, though (corrected 2026-07-26, task
# 6.4 round 2; extended 2026-07-26, task 6.4 round 3): this walk only
# inspects ``ast.Call.func`` and ``ast.ImportFrom`` aliases naming
# ``load_load_settings`` directly, so a call *site* that names something the
# walk cannot trace back to that literal import still defeats it -- e.g.
# ``importlib.import_module`` plus ``getattr`` (the ``func`` is a
# ``getattr(...)`` call, not a ``load_load_settings``-named node), or a
# plain non-import alias (``reader = load_load_settings`` followed by
# ``reader({}, path)``, where the call site names only ``reader`` and no
# ``ImportFrom`` alias exists to resolve it). All three spellings -- the
# ``importlib``/``getattr`` form, the plain-assignment alias, and the
# ``from ... import ... as`` alias this round closes -- were run against
# this guard; the first two still leave it green (and the rest of the
# 1850-test suite green), the third now reddens it directly. The behavioral
# companion below, which spies on the reader itself rather than parsing call
# sites, is what actually closes all three spellings; this walk still catches
# the ordinary cases (a literal second call, or a ``from ... import ...
# as``-aliased one, naming ``load_load_settings``) cheaply and without
# needing to run anything.


def _modules_calling_load_load_settings() -> set[Path]:
    """Files under ``src/fitdocs`` containing a call site that reaches
    ``load_load_settings``, matched against a *per-file* set of matched
    names rather than the literal string ``"load_load_settings"`` (corrected
    task 6.4 round 3, finding 1): a ``from fitdocs.load.settings import
    load_load_settings as _reader`` import binds the reader under a local
    alias, and the previous version of this walk -- comparing the call
    site's own spelling directly against the literal name -- never matched
    ``_reader(...)``. Each module's own ``ast.ImportFrom`` aliases for
    ``load_load_settings`` are collected first (``.asname or .name``), and
    call sites in *that* module are matched against that module's own
    matched-name set, not a single global name.
    """
    src_root = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
    callers: set[Path] = set()
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        matched_names = {"load_load_settings"}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for alias in node.names:
                if alias.name == "load_load_settings":
                    matched_names.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in matched_names:
                callers.add(path.relative_to(src_root))
                break
    return callers


def test_load_load_settings_is_called_from_exactly_the_licensed_modules() -> None:
    """Req 14.1: the reader itself stays singular even though three *passes*
    now consume it. Training-load's own pass (``load/engine.py``), the
    load-history engine (``history/engine.py``, which reads ``[load]``'s
    ``default_calculator`` as the configured methodology -- load-history
    design, "Allowed Dependencies") and ``performance-benchmarks``'
    derivation pass (``performance/engine.py``, landed by that spec's task
    4.2, which needs ``LoadSettings.sufficiency`` for the same
    ``[load.sufficiency]`` table the load pass already reads) are the
    exactly-three sanctioned callers -- Req 14.1's guarantee is "the
    ``[load]`` table is parsed from exactly one place", not "called from
    exactly one call site"; a further *pass* reading it through the same
    single reader is the sanctioned resolution recorded in
    ``.kiro/queue/closed/2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard.md``,
    not a violation of it. Nowhere else -- the command surface, the document
    editor, the profile store, or any other module tempted to read
    ``[load]`` directly -- may call it.

    Mutation caught: adding a *fourth*, real call site (e.g. a guarded
    ``load_load_settings(...)`` invocation added to ``fitdocs/load/docedit.py``,
    reached only behind an always-false condition so it changes no
    behavior) reddens this test by naming all four callers, while leaving
    the rest of the suite green -- the same shape task 4.2's reviewer proved
    against the CLI-specific version of this guard.
    """
    callers = _modules_calling_load_load_settings()
    assert callers == {
        Path("load/engine.py"),
        Path("history/engine.py"),
        Path("performance/engine.py"),
    }, (
        f"load_load_settings is called from {sorted(str(p) for p in callers)}, "
        "expected exactly ['history/engine.py', 'load/engine.py', "
        "'performance/engine.py']"
    )


def _reads_load_table_literally(tree: ast.AST) -> bool:
    """True if ``tree`` contains either of the literal-key spellings this
    guard treats as a second reader of the top-level ``[load]`` table:

    * ``ast.Subscript`` keyed by the constant ``"load"`` (``doc["load"]``);
    * an ``ast.Call`` to an attribute named ``get`` carrying the constant
      ``"load"`` in the one argument position that can actually *be* the
      key: ``args[0]`` for the bound form (``doc.get("load")``), or
      ``args[1]`` -- and only when the receiver is the literal name
      ``dict`` -- for the unbound-method form (``dict.get(document,
      "load")``, queue item
      2026-07-26-second-load-reader-spellings-escape-guards, spelling 2).

    Narrower than the version review round 1 shipped, on two counts, both
    findings from round 2:

    * **Any-positional-argument matching false-positived on the *value*, not
      the key.** ``options.get("mode", "load")`` reads key ``"mode"`` with
      default value ``"load"`` -- the exact opposite of a ``[load]`` read --
      but matched because the check scanned every argument position rather
      than the one that can hold a key. Pinning the key to its own position
      (``args[0]`` bound, ``args[1]`` unbound-and-only-when-the-receiver-is-
      literally-``dict``) removes it: a default value can never land in the
      position this now checks.
    * **``.pop`` and ``ast.Compare(==)`` are dropped, not narrowed, because
      no argument-position fix removes their false positives.** ``"load"``
      is already three unrelated namespaces in this repo:
      :data:`fitdocs.contract.LOAD_REGION` (a rendered document region),
      the ``@app.command("load")`` CLI verb, and this settings table. A
      bound ``X.pop("load")`` is syntactically identical whether ``X`` is a
      settings document (spelling 3, a real second reader) or the
      ``regions`` mapping :func:`fitdocs.load.docedit._load_region_content`
      already legitimately pops/subscripts by this same literal key
      (``src/fitdocs/load/docedit.py``, which reads ``regions[LOAD_REGION]``
      today but is one literal-instead-of-constant edit away from
      ``regions.pop("load")``) -- no receiver-position or argument-position
      rule distinguishes them, because both really are ``X.pop("load")``.
      Likewise ``ast.Compare(==)`` matched ``command_name == "load"`` (CLI
      dispatch) exactly as readily as a settings-document key comparison.
      Measured: both constructs, added as real code, left the full suite,
      ruff and mypy green under the *narrowed* positional check -- proving
      position alone does not save them -- and both are now included as
      negative controls below to keep it that way. The two spellings this
      costs -- (1) dict iteration (``for k, v in doc.items(): if k ==
      "load"``) and (3) ``document.pop("load")`` -- are accepted residuals,
      alongside the pre-existing aliased-key residual below: a guard that
      flags every ``.pop("load")`` and every ``== "load"`` in the tool is
      not a Req 14.1 guard, it is a ban on writing ``"load"`` as a Python
      string literal anywhere in ``src/fitdocs``.

    Deliberately does not chase the aliased-key spelling (``_T = "load"``;
    ``doc.get(_T)``): that is the accepted residual recorded in tasks.md's
    task 6.4 notes (a module-level alias still evades any literal-key AST
    check; only the behavioural companion below, which spies on the real
    reader, closes that spelling).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            index = node.slice
            if isinstance(index, ast.Constant) and index.value == "load":
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get":
                receiver = func.value
                if isinstance(receiver, ast.Name) and receiver.id == "dict":
                    if (
                        len(node.args) >= 2
                        and isinstance(node.args[1], ast.Constant)
                        and node.args[1].value == "load"
                    ):
                        return True
                elif (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "load"
                ):
                    return True
    return False


def _modules_parsing_load_table_literally(src_root: Path | None = None) -> set[Path]:
    """Files under ``src_root`` (every ``*.py``, package-wide -- not just
    ``cli.py``) containing a node :func:`_reads_load_table_literally`
    recognises as a literal read of the ``[load]`` table.

    Defaults to the real ``src/fitdocs`` tree. A caller may pass a synthetic
    tree instead (see
    ``test_literal_load_table_detection_catches_the_reported_spellings``
    below) to exercise the detection logic without touching shipped source;
    the positive-control and allowlist assertions that guard against a
    silently-vacuous walk live in the real-tree test, not here, since they
    only mean something against the real tree.

    ``load/settings.py`` -- the sole legitimate parser, :func:`load_load_settings`
    itself -- is allowlisted when present; every other module's match is a
    second reader Req 14.1 forbids ("no second reader of that table shall
    exist anywhere in the tool"), which is strictly wider than task 4.2's
    CLI-only guard.
    """
    if src_root is None:
        src_root = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
    allowlisted = src_root / "load" / "settings.py"
    scanned = sorted(src_root.rglob("*.py"))
    offenders: set[Path] = set()
    for path in scanned:
        if path == allowlisted:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _reads_load_table_literally(tree):
            offenders.add(path.relative_to(src_root))
    return offenders


def test_no_module_other_than_load_settings_parses_the_load_table_literally() -> None:
    """Req 14.1's other half, package-wide: "no second reader of that table
    shall exist anywhere in the tool" -- not just "the command surface holds
    no reader" (task 4.2's original, narrower scope).

    Every earlier guard in this module keys on the *function*
    ``load_load_settings``; a module that parses ``[load]`` directly off an
    already-loaded settings document, never calling that function, is
    invisible to all of them. Confirmed by the reviewer's exact probe: a
    block added to ``src/fitdocs/audit.py`` that calls
    ``load_settings_document(data_root)``, reads ``.get("load")``, and
    validates ``default_calculator`` itself -- a real second reader with its
    own validation, never touching :func:`fitdocs.load.settings.load_load_settings`
    -- passes the full suite, ruff, and mypy with every other guard in this
    module green. This walk is what catches it.

    Mutation caught: the probe above, added to ``audit.py``, names
    ``audit.py`` as the sole offender here while leaving every other test in
    the suite green (verified by running it, not by inspection).
    """
    src_root = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
    allowlisted = src_root / "load" / "settings.py"
    scanned = sorted(src_root.rglob("*.py"))
    # Positive control. Without it this walk passes green having visited zero
    # files: ``parents[2]`` is depth-sensitive, so moving this test one
    # directory deeper silently points ``src_root`` at ``tests/src/fitdocs``
    # and the guard is permanently vacuous. The sibling steering guard in
    # ``tests/test_docs_guarantees.py`` was rejected for exactly this.
    assert scanned, (
        f"no modules scanned under {src_root} -- the walk is looking at the "
        "wrong directory, so this guard proves nothing"
    )
    assert allowlisted.is_file(), (
        f"the sole legitimate parser {allowlisted} is missing -- the allowlist "
        "has drifted and offenders would be misattributed"
    )
    offenders = _modules_parsing_load_table_literally()
    assert not offenders, (
        f"modules parsing the [load] table by literal key outside "
        f"load/settings.py: {sorted(str(p) for p in offenders)}"
    )


def test_literal_load_table_detection_catches_the_reported_spellings(
    tmp_path: Path,
) -> None:
    """Fixture-discrimination companion for
    :func:`_modules_parsing_load_table_literally`'s detection, run against a
    synthetic source tree rather than by editing real shipped modules -- a
    temporary, reviewable fixture instead of a hand-edit/revert cycle.

    **Closes**, of the four spellings named in queue item
    2026-07-26-second-load-reader-spellings-escape-guards:

    * a direct subscript, ``document["load"]`` (not itself one of the four
      queue spellings, but the walk's oldest and most load-bearing clause --
      pinned here per review round 2, which found no offender for it
      anywhere in this fixture);
    * spelling (2), the mapping passed positionally rather than as the
      receiver: ``dict.get(document, "load")``.

    **Accepted as residual, not closed here** (see
    :func:`_reads_load_table_literally`'s docstring for why, review round 2):

    * spelling (1), dict iteration: ``for k, v in doc.items(): if k ==
      "load"`` -- the ``ast.Compare(==)`` clause that would catch it also
      matched CLI dispatch (``command_name == "load"``), so it was dropped;
    * spelling (3), ``document.pop("load")`` -- syntactically identical to
      the legitimate ``regions.pop("load")`` a rendered-document region
      helper could just as well write, so the ``.pop`` half of the ``get``/
      ``pop`` clause was dropped too;
    * spelling (4), a default-parameter capture -- a different guard's
      concern entirely (the ``sys.modules`` behavioural spy below, not this
      literal-key walk); see that spy's own docstring for how it is closed.

    Three FALSE-POSITIVE constructs, measured against review round 1's wider
    version of this walk and confirmed still real in the repo today (``load``
    is simultaneously the settings table, :data:`fitdocs.contract.LOAD_REGION`,
    and the ``@app.command("load")`` CLI verb), are included as NEGATIVE
    CONTROLS so a future widening cannot silently reintroduce them:

    * ``options.get("mode", "load")`` -- ``"load"`` is the *default value*
      for key ``"mode"``, not a key read, and false-positived under the
      original any-positional-argument ``.get``/``.pop`` check;
    * ``if command_name == "load": ...`` -- ordinary CLI dispatch, false-
      positived under the dropped ``ast.Compare(==)`` clause;
    * ``regions.pop("load")`` -- removing the rendered ``load`` region
      (``src/fitdocs/load/docedit.py`` already reads ``regions[LOAD_REGION]``
      by this same string, one literal-instead-of-constant edit away), false-
      positived under the original ``.pop`` matching and the reason ``.pop``
      is dropped rather than narrowed.

    A fifth, innocent module using ``.get`` for an unrelated key is also
    included: the detection must not start flagging every ``.get`` call in
    the tree.

    Mutation caught: narrowing ``_reads_load_table_literally`` back to
    matching only ``ast.Subscript`` (dropping the ``.get`` clause entirely)
    reddens this test, because the unbound-``.get`` offender no longer
    matches while every negative control still correctly does not appear.
    Widening it back to the original any-positional-argument ``.get``/``.pop``
    plus ``ast.Compare(==)`` shape also reddens this test, because the three
    negative controls then incorrectly appear in ``offenders``.
    """
    src_root = tmp_path / "fitdocs"
    (src_root / "load").mkdir(parents=True)
    (src_root / "load" / "settings.py").write_text(
        "# allowlisted -- the sole legitimate parser\n", encoding="utf-8"
    )
    (src_root / "load" / "__init__.py").write_text("", encoding="utf-8")
    (src_root / "__init__.py").write_text("", encoding="utf-8")

    # --- offenders: still closed ------------------------------------------
    (src_root / "subscript_reader.py").write_text(
        "def scan(doc):\n    return doc['load']['channels']\n",
        encoding="utf-8",
    )
    (src_root / "unbound_get_reader.py").write_text(
        "def scan(doc):\n    return dict.get(doc, 'load')\n",
        encoding="utf-8",
    )
    (src_root / "bound_get_reader.py").write_text(
        "def scan(doc):\n    return doc.get('load')\n",
        encoding="utf-8",
    )

    # --- accepted residuals: not offenders under this walk -----------------
    (src_root / "iter_reader.py").write_text(
        "def scan(doc):\n"
        "    for k, v in doc.items():\n"
        "        if k == 'load':\n"
        "            return v\n"
        "    return None\n",
        encoding="utf-8",
    )
    (src_root / "pop_reader.py").write_text(
        "def scan(doc):\n    return doc.pop('load')\n",
        encoding="utf-8",
    )

    # --- negative controls: real constructs that must never be flagged -----
    (src_root / "default_value_reader.py").write_text(
        "def scan(options):\n    return options.get('mode', 'load')\n",
        encoding="utf-8",
    )
    (src_root / "cli_dispatch.py").write_text(
        "def dispatch(command_name):\n"
        "    if command_name == 'load':\n"
        "        return 'dispatched'\n"
        "    return None\n",
        encoding="utf-8",
    )
    (src_root / "region_pop.py").write_text(
        "def drop_load_region(regions):\n    return regions.pop('load')\n",
        encoding="utf-8",
    )

    # --- innocent: unrelated key ------------------------------------------
    (src_root / "innocent.py").write_text(
        "def unrelated(doc):\n    return doc.get('other')\n",
        encoding="utf-8",
    )

    offenders = _modules_parsing_load_table_literally(src_root)
    assert offenders == {
        Path("subscript_reader.py"),
        Path("unbound_get_reader.py"),
        Path("bound_get_reader.py"),
    }, (
        f"expected exactly the three synthetic offenders (subscript, "
        f"unbound-get, bound-get), got {sorted(str(p) for p in offenders)}"
    )


# --- Package-wide behavioral companion (task 6.4 round 2, Req 14.1) ---------
#
# The AST walk above is a call-*site* check: it can only see a call that its
# own resolution logic can trace back to ``load_load_settings`` (a literal
# name, or a per-file ``ImportFrom`` alias of it). It is provably bypassable
# by spellings that still reach the real reader without ever writing a name
# the walk can resolve -- ``importlib.import_module(...)`` + ``getattr(...)``,
# a plain non-import alias (``reader = load_load_settings`` then
# ``reader(...)``), and a *module-level* ``from x import y as z`` import
# whose call site names only ``z`` -- all of which leave the walk above
# green (the last one only as of task 6.4 round 3; the fix in this module
# closes it for the AST walk directly). This behavioral companion covers
# every *module-level* binding, under any local name, in any ``fitdocs.*``
# module, plus every default-parameter capture (positional or keyword-only)
# reachable from one -- the scope stated at the sweep itself below.
# ``tests/test_cli.py::test_load_command_calls_load_load_settings_exactly_once``
# also spies on the reader, but only for ``fitdocs load`` and only across the
# two binding surfaces it patches by hand -- so it closes every spelling
# *that routes through those two modules*, not every spelling. Measured: a
# module-level ``from fitdocs.load.settings import load_load_settings as _r2``
# in ``src/fitdocs/load/arbitrate.py`` plus a call in ``validate_configured``
# -- a real second read on the ``fitdocs load`` path -- leaves
# ``tests/test_cli.py`` fully green at 36 passed, while the sweep below
# reddens. That is why this sweep is not redundant with it: do not delete
# this in favour of that one.


def test_load_load_settings_is_called_the_documented_number_of_times_per_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 14.1, package-wide: ``load_load_settings`` is called exactly once
    per ``fitdocs sync``, ``fitdocs regen``, ``fitdocs load``, and
    ``fitdocs derive-benchmarks`` invocation (the single read inside
    ``apply_load`` itself, task 4.1, and inside
    ``fitdocs.performance.engine.derive_benchmarks`` itself,
    performance-benchmarks task 4.2 -- see the controller ruling recorded
    against this test in ``.kiro/specs/performance-benchmarks/tasks.md``
    Implementation Notes ``(4.1 -> 4.2)``) and exactly zero times for
    ``fitdocs check`` (the command that runs the read-only contract audit,
    ``src/fitdocs/audit.py``) -- ``audit()`` never touches the load engine or
    the ``[load]`` table at all.

    Sweeps *every* already-imported ``fitdocs.*`` module rather than
    hand-listing the two binding surfaces this test used to spy on
    (corrected task 6.4 round 3, finding 1): a ``from x import y`` binds the
    original function object into the importing module's own namespace, at
    import time, under whatever local name that module chose -- there are as
    many such binding surfaces as there are importing modules, not two, and
    a hand-picked pair (``fitdocs.load.settings`` and ``fitdocs.load.engine``)
    is blind to a binding anywhere else, including an aliased one (``from
    fitdocs.load.settings import load_load_settings as _reader``) added to a
    third module such as ``fitdocs.audit``. This walks ``sys.modules`` for
    every module whose name starts with ``fitdocs.``, and for every
    attribute on it that ``is`` the real (pre-patch) function, patches it to
    the spy -- so any *module-level* binding, under any local name, in any
    module, is caught regardless of where it lives or what it is called
    there. A default-parameter capture -- ``def audit(data_root: Path, _r:
    object = load_load_settings)`` followed by a call to ``_r(...)`` -- is
    never a *module* attribute either, but the binding still lives one
    dereference away: on the function object's own ``__defaults__`` (or
    ``__kwdefaults__`` for a keyword-only parameter, ``def audit(data_root,
    *, _r=load_load_settings)``), both of which are ordinary writable
    attributes. For every already-swept ``fitdocs.*`` module-level function,
    this also inspects its ``__defaults__``/``__kwdefaults__`` for the real
    reader and patches whichever tuple/dict entry holds it, closing that
    spelling too -- no call-time interception or caller-frame instrumentation
    required. A call-time rebinding inside another module (``from
    fitdocs.load.settings import load_load_settings`` executed *inside a
    function body* rather than at module import time, or
    ``getattr(importlib.import_module(...), ...)``) still resolves the
    current, patched module attribute at call time, so this spy catches
    those too -- unlike the AST walk above.

    Mutation caught (verified by running each, not by inspection): adding
    any of the bypass spellings above as a real, reachable call inside
    ``src/fitdocs/audit.py`` -- including a module-level ``from
    fitdocs.load.settings import load_load_settings as _reader`` plus a call
    to ``_reader(...)`` inside ``audit()``, and the two default-parameter
    capture forms (positional and keyword-only) -- so that ``fitdocs check``
    invokes the reader once where zero is documented, reddens this test's
    ``fitdocs check`` assertion as a sole failure in every case (verified by
    running each mutation through the full suite, not by inspection).
    """
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )
    runner = CliRunner()
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())

    calls: list[object] = []
    original = load_settings_module.load_load_settings

    def _spy(document: object, settings_file: object) -> object:
        calls.append(document)
        return original(document, settings_file)  # type: ignore[arg-type]

    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("fitdocs."):
            continue
        for attr_name in list(vars(module)):
            value = getattr(module, attr_name, None)
            if value is original:
                monkeypatch.setattr(module, attr_name, _spy)
                continue
            if not isinstance(value, types.FunctionType):
                continue
            # A default-parameter capture (``def f(..., _r=load_load_settings)``)
            # never becomes a *module* attribute, so the ``vars(module)`` walk
            # above is structurally blind to it -- but the default lives in the
            # function object's own ``__defaults__``/``__kwdefaults__``, one
            # dereference from a module attribute and just as writable. Patch
            # any default (positional or keyword-only) that is the real reader.
            if value.__defaults__ and any(d is original for d in value.__defaults__):
                monkeypatch.setattr(
                    value,
                    "__defaults__",
                    tuple(_spy if d is original else d for d in value.__defaults__),
                )
            if value.__kwdefaults__ and any(
                d is original for d in value.__kwdefaults__.values()
            ):
                monkeypatch.setattr(
                    value,
                    "__kwdefaults__",
                    {
                        k: (_spy if v is original else v)
                        for k, v in value.__kwdefaults__.items()
                    },
                )

    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0, synced.output
    assert len(calls) == 1, (
        f"fitdocs sync called load_load_settings {len(calls)} times, expected 1"
    )
    calls.clear()

    regenerated = runner.invoke(app, ["regen", "--out", str(data_root)])
    assert regenerated.exit_code == 0, regenerated.output
    assert len(calls) == 1, (
        f"fitdocs regen called load_load_settings {len(calls)} times, expected 1"
    )
    calls.clear()

    loaded = runner.invoke(app, ["load", "--out", str(data_root)])
    assert loaded.exit_code == 0, loaded.output
    assert len(calls) == 1, (
        f"fitdocs load called load_load_settings {len(calls)} times, expected 1"
    )
    calls.clear()

    checked = runner.invoke(app, ["check", "--out", str(data_root)])
    assert checked.exit_code == 0, checked.output
    assert len(calls) == 0, (
        f"fitdocs check called load_load_settings {len(calls)} times, expected 0"
    )
    calls.clear()

    derived = runner.invoke(app, ["derive-benchmarks", "--out", str(data_root)])
    assert derived.exit_code == 0, derived.output
    assert len(calls) == 1, (
        f"fitdocs derive-benchmarks called load_load_settings {len(calls)} "
        "times, expected 1"
    )
