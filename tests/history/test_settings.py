"""Tests for the ``[history]`` settings reader and constant resolver
(load-history spec, task 5.1; Req 2.7, 3.4, 8.3, 8.4). See the
"HistorySettings (`src/fitdocs/history/settings.py`)" component in
`.kiro/specs/load-history/design.md`.

Two things are pinned here:

* :func:`load_history_settings` -- the peer table reader beside
  ``load_load_settings``, ``tile_settings_from_document``,
  ``load_inbox_settings`` and ``load_plugin_settings``. Every field
  defaults to unset (absent file or table -> :data:`DEFAULT_HISTORY_SETTINGS`,
  never an error); unknown keys and sub-tables are ignored; each numeric
  field is validated to its own rule, with ``bool`` rejected explicitly
  everywhere a number is expected (Req 8.3, 8.4).
* :func:`resolve_constants` -- with nothing configured the result *is*
  ``SEED_CONSTANTS`` by identity; with any of the four constants
  configured, the provenance is ``CONFIGURED`` and the origin line names
  each configured key and each key left at its seed, so a partially
  configured set is never labelled ``SEEDS`` (Req 2.7, 3.4).

The reader never opens a file: every case here hands it an already-parsed
mapping (a plain ``dict``, matching what ``tomllib`` would produce) and a
representative ``settings_file`` path used only to name the file in errors.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from fitdocs.history.settings import (
    DEFAULT_HISTORY_SETTINGS,
    HISTORY_TABLE,
    HistorySettings,
    HistorySettingsError,
    load_history_settings,
    resolve_constants,
)
from fitdocs.history.sources import SEED_CONSTANTS, ConstantProvenance
from fitdocs.settings import SettingsError

SETTINGS_FILE = Path("/data-root/fitdocs.toml")


# --- HistorySettings: immutable -----------------------------------------


def test_history_settings_is_frozen() -> None:
    """`HistorySettings` is immutable -- assigning to a field raises.
    Named mutation: drop `frozen=True` from the `@dataclass` decorator --
    this assertion reds."""
    settings = HistorySettings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.tau_fitness_days = 1.0  # type: ignore[misc]


# --- load_history_settings: absence is default, never an error --------------


def test_absent_history_table_yields_the_default_by_identity() -> None:
    """An empty document (the shared reader's absent-file case) yields
    `DEFAULT_HISTORY_SETTINGS` -- checked by identity, not merely equality,
    so a reader that reconstructs an equal-but-fresh instance instead of
    returning the shared default fails this assertion."""
    result = load_history_settings({}, SETTINGS_FILE)
    assert result is DEFAULT_HISTORY_SETTINGS


def test_absent_history_key_in_a_nonempty_document_yields_the_default() -> None:
    """A document with other tables (`[tiles]`, `[load]`, ...) but no
    `[history]` key still yields the default -- the shared-file case this
    reader must never mistake for a malformed table."""
    document = {"tiles": {"enabled": True}, "load": {"default_calculator": "x"}}
    result = load_history_settings(document, SETTINGS_FILE)
    assert result is DEFAULT_HISTORY_SETTINGS


def test_empty_history_table_yields_a_settings_equal_to_the_default() -> None:
    """A present but empty `[history]` table -- every key absent -- projects
    a `HistorySettings` equal to the default in every field (matching the
    `[load]` peer reader's own present-but-empty behavior, which still
    projects through its field readers rather than special-casing an empty
    table by identity). Named mutation: in the absent-key return of one of
    the per-field helpers (e.g. `_nonnegative_finite_float`), leave
    `k_fitness` resolved to some other sentinel (e.g. `0.0`) instead of
    `None` -- this equality assertion reds."""
    result = load_history_settings({HISTORY_TABLE: {}}, SETTINGS_FILE)
    assert result == DEFAULT_HISTORY_SETTINGS


@pytest.mark.parametrize(
    "value",
    ["nope", 5, [{}]],
    ids=["string", "int", "array-of-tables"],
)
def test_non_table_history_value_raises(value: object) -> None:
    """`[history]` set to anything but a table raises `HistorySettingsError`,
    naming the settings file -- including a string, an int, and the
    `[[history]]` array-of-tables shape (a `list`, which a mutant guard of
    `isinstance(table, (dict, list))` would wrongly accept)."""
    with pytest.raises(HistorySettingsError) as excinfo:
        load_history_settings({HISTORY_TABLE: value}, SETTINGS_FILE)
    assert str(SETTINGS_FILE) in str(excinfo.value)


def test_unknown_key_inside_history_is_ignored() -> None:
    """An unrecognized key inside `[history]` is ignored, not rejected --
    the document is shared, and a later sibling table might one day claim
    it. Named mutation: raise on an unrecognized key -- this test reds,
    while the malformed-value tests below (which target a *recognized*
    key with a *bad* value) stay green, discriminating this rule from
    those."""
    document = {HISTORY_TABLE: {"totally_unknown_key": 123}}
    result = load_history_settings(document, SETTINGS_FILE)
    assert result == DEFAULT_HISTORY_SETTINGS


def test_unknown_subtable_inside_history_is_ignored() -> None:
    """An unrecognized sub-table beneath `[history]` is ignored."""
    document = {HISTORY_TABLE: {"future": {"nested": True}}}
    result = load_history_settings(document, SETTINGS_FILE)
    assert result == DEFAULT_HISTORY_SETTINGS


# --- load_history_settings: valid configuration is projected -----------------


def test_every_field_valid_is_projected_verbatim() -> None:
    """Every key present with a valid value is carried onto the matching
    field, pairwise-distinct so no two fields could swap and pass."""
    document = {
        HISTORY_TABLE: {
            "tau_fitness_days": 50.0,
            "tau_fatigue_days": 12.0,
            "k_fitness": 2.0,
            "k_fatigue": 3.0,
            "coverage_threshold": 0.65,
            "methodology": "threshold",
        }
    }
    result = load_history_settings(document, SETTINGS_FILE)
    assert result.tau_fitness_days == 50.0
    assert result.tau_fatigue_days == 12.0
    assert result.k_fitness == 2.0
    assert result.k_fatigue == 3.0
    assert result.coverage_threshold == 0.65
    assert result.methodology == "threshold"


def test_integer_valued_numeric_fields_are_accepted_and_coerced_to_float() -> None:
    """A TOML integer (e.g. `tau_fitness_days = 50`) is a valid number, not
    a type error -- `isinstance(True, int)` is the trap this guards
    against elsewhere, not plain `int`. Named mutation: in
    `_nonnegative_finite_float`, `return value` instead of
    `return float(value)` -- with `k_fitness = 0` (an `int`), the returned
    value stays an `int` and the `isinstance(result.k_fitness, float)`
    assertion below reds."""
    document = {
        HISTORY_TABLE: {"tau_fitness_days": 50, "k_fitness": 0, "coverage_threshold": 1}
    }
    result = load_history_settings(document, SETTINGS_FILE)
    assert result.tau_fitness_days == 50.0
    assert isinstance(result.tau_fitness_days, float)
    assert result.k_fitness == 0.0
    assert isinstance(result.k_fitness, float)
    assert result.coverage_threshold == 1.0
    # Same named mutation in `_unit_interval_float` (`return value` instead of
    # `return float(value)`): `coverage_threshold = 1` stays an `int`; the
    # equality above still holds (`1 == 1.0`) and it is this `isinstance`
    # assertion that reds.
    assert isinstance(result.coverage_threshold, float)


def test_history_table_is_named_history_in_the_settings_file() -> None:
    """The table an athlete writes is literally `[history]` -- pinned with the
    string an athlete types, not with the constant imported from the module
    under test (every other document in this file is built from
    `HISTORY_TABLE`, which would follow a renamed constant silently). Named
    mutation: `HISTORY_TABLE = "histry"` in `settings.py` -- the literal-keyed
    document below then reads as an absent table, `tau_fitness_days` comes
    back `None`, and this assertion reds."""
    assert HISTORY_TABLE == "history"
    result = load_history_settings(
        {"history": {"tau_fitness_days": 50.0}}, SETTINGS_FILE
    )
    assert result.tau_fitness_days == 50.0


def test_coverage_threshold_boundary_values_zero_and_one_are_accepted() -> None:
    """The interval is closed: both 0.0 and 1.0 are valid, not merely the
    open interval. Named mutation: use a strict `<` / `>` bound instead of
    `<=` / `>=` -- these two cases red while the interior/out-of-range
    cases elsewhere stay unaffected, discriminating open from closed."""
    lower = load_history_settings(
        {HISTORY_TABLE: {"coverage_threshold": 0.0}}, SETTINGS_FILE
    )
    upper = load_history_settings(
        {HISTORY_TABLE: {"coverage_threshold": 1.0}}, SETTINGS_FILE
    )
    assert lower.coverage_threshold == 0.0
    assert upper.coverage_threshold == 1.0


# --- load_history_settings: malformed values raise ---------------------------


@pytest.mark.parametrize("key", ["tau_fitness_days", "tau_fatigue_days"])
def test_time_constant_zero_or_negative_raises(key: str) -> None:
    """A `tau_*` must be strictly greater than zero -- zero itself, and a
    negative value, both raise."""
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: 0.0}}, SETTINGS_FILE)
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: -5.0}}, SETTINGS_FILE)


@pytest.mark.parametrize(
    "key",
    [
        "tau_fitness_days",
        "tau_fatigue_days",
        "k_fitness",
        "k_fatigue",
        "coverage_threshold",
    ],
)
def test_time_constant_non_finite_raises(key: str) -> None:
    """`inf` and `nan` both raise for every numeric field. For the four
    `tau_*`/`k_*` helpers the finiteness check is load-bearing on its own:
    `nan <= 0` and `nan < 0` are both `False` in Python, so a reader that
    dropped the finiteness check in one of those helpers would wrongly
    accept `nan` there. For `coverage_threshold` the finiteness check is
    redundant by construction -- `0.0 <= nan <= 1.0` is also `False`, so the
    range check alone already raises on `nan` even with no finiteness check
    at all; that field's `inf`/`nan` cases are still pinned here for
    completeness, but dropping only its finiteness check is an equivalent
    mutant, not a red."""
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: float("inf")}}, SETTINGS_FILE)
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: float("nan")}}, SETTINGS_FILE)


@pytest.mark.parametrize("key", ["tau_fitness_days", "tau_fatigue_days"])
def test_time_constant_boolean_raises(key: str) -> None:
    """A boolean is rejected as a time constant even though `bool` is an
    `int` subclass and `True == 1`, `False == 0` would otherwise pass a
    naive `isinstance(value, (int, float))` and `value > 0` check. Named
    mutation: drop the `isinstance(value, bool)` guard -- `True` (a
    positive int) passes the range check and this assertion reds."""
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: True}}, SETTINGS_FILE)


@pytest.mark.parametrize(
    "key",
    [
        "tau_fitness_days",
        "tau_fatigue_days",
        "k_fitness",
        "k_fatigue",
        "coverage_threshold",
    ],
)
@pytest.mark.parametrize("value", ["1", "0.5"])
def test_time_constant_non_numeric_raises(key: str, value: str) -> None:
    """A numeric-looking string raises `HistorySettingsError`, not `TypeError`
    and not a silently-coerced float, for every numeric field. Named
    mutation: coerce a numeric string to `float` before the `isinstance`
    check in the `k_*` / `coverage_threshold` helpers -- `"1"` and `"0.5"`
    would then parse cleanly and this assertion reds."""
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: value}}, SETTINGS_FILE)


@pytest.mark.parametrize("key", ["k_fitness", "k_fatigue"])
def test_weighting_negative_raises_but_zero_is_valid(key: str) -> None:
    """A `k_*` must be `>= 0`, not `> 0`: zero is a valid (if degenerate)
    weighting and must be accepted, while a negative value must raise --
    the pair discriminates `>= 0` from the stricter `tau_*` rule of `> 0`."""
    result = load_history_settings({HISTORY_TABLE: {key: 0.0}}, SETTINGS_FILE)
    assert getattr(result, key) == 0.0
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: -0.5}}, SETTINGS_FILE)


@pytest.mark.parametrize("key", ["k_fitness", "k_fatigue"])
def test_weighting_boolean_raises(key: str) -> None:
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {key: False}}, SETTINGS_FILE)


def test_coverage_threshold_out_of_range_raises() -> None:
    """1.5 is well outside `[0.0, 1.0]` and must raise -- the canonical
    "drop the range check" mutation target."""
    with pytest.raises(HistorySettingsError):
        load_history_settings(
            {HISTORY_TABLE: {"coverage_threshold": 1.5}}, SETTINGS_FILE
        )
    with pytest.raises(HistorySettingsError):
        load_history_settings(
            {HISTORY_TABLE: {"coverage_threshold": -0.1}}, SETTINGS_FILE
        )


def test_coverage_threshold_boolean_raises() -> None:
    with pytest.raises(HistorySettingsError):
        load_history_settings(
            {HISTORY_TABLE: {"coverage_threshold": True}}, SETTINGS_FILE
        )


def test_methodology_empty_string_raises() -> None:
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {"methodology": ""}}, SETTINGS_FILE)


def test_methodology_non_string_raises() -> None:
    with pytest.raises(HistorySettingsError):
        load_history_settings({HISTORY_TABLE: {"methodology": 5}}, SETTINGS_FILE)


@pytest.mark.parametrize(
    "key, value",
    [
        ("tau_fitness_days", -1.0),
        ("tau_fatigue_days", 0),
        ("k_fitness", -0.5),
        ("k_fatigue", "x"),
        ("coverage_threshold", 1.5),
        ("methodology", ""),
        ("methodology", 123),
    ],
)
def test_malformed_error_names_the_settings_file_and_the_offending_key(
    key: str, value: object
) -> None:
    """The raised message names both the settings file and the offending
    key, so an athlete can find and fix the problem (Req 8.4) -- pinned for
    every field's own helper, not only `coverage_threshold`'s. Named
    mutation: drop `{key}` from the `tau_*` helper's message (~207) -- the
    `tau_fitness_days`/`tau_fatigue_days` cases red on the key assertion.
    Named mutation: drop both `{settings_file}` and `{key}` from the `k_*`
    helper's message (~227) -- the `k_fitness`/`k_fatigue` cases red on
    both assertions. Named mutation: reduce the `methodology` helper's
    message (~265) to omit the key -- the `methodology` case reds on the
    key assertion."""
    with pytest.raises(HistorySettingsError) as excinfo:
        load_history_settings({HISTORY_TABLE: {key: value}}, SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(SETTINGS_FILE) in message
    assert key in message


def test_history_settings_error_is_a_settings_error() -> None:
    """`HistorySettingsError` subclasses the shared `SettingsError`, so the
    CLI's existing `except SettingsError` handler maps it with no new
    branch (Req 8.4). Named mutation: make `HistorySettingsError` subclass
    `Exception` directly instead -- this assertion reds."""
    assert issubclass(HistorySettingsError, SettingsError)


# --- resolve_constants: nothing configured is the seed, by identity ---------


def test_resolve_constants_of_the_default_is_the_seed_by_identity() -> None:
    """Nothing configured -> the result *is* `SEED_CONSTANTS`, by identity,
    not merely an equal-but-fresh copy. Named mutation: build and return a
    fresh `ModelConstants(**dataclasses.asdict(SEED_CONSTANTS))` from the
    unconfigured branch instead of returning `SEED_CONSTANTS` itself --
    equality still holds but `is` reds."""
    result = resolve_constants(DEFAULT_HISTORY_SETTINGS)
    assert result is SEED_CONSTANTS


# --- resolve_constants: any of the four configured is CONFIGURED ------------


def test_resolve_constants_all_four_configured() -> None:
    settings = HistorySettings(
        tau_fitness_days=50.0, tau_fatigue_days=12.0, k_fitness=2.0, k_fatigue=3.0
    )
    result = resolve_constants(settings)
    assert result.tau_fitness_days == 50.0
    assert result.tau_fatigue_days == 12.0
    assert result.k_fitness == 2.0
    assert result.k_fatigue == 3.0
    assert result.provenance is ConstantProvenance.CONFIGURED


def test_resolve_constants_one_configured_keeps_the_other_three_at_seed() -> None:
    """Configuring only `tau_fitness_days` resolves the other three at
    their seed values -- pairwise-distinct from the configured one, so a
    reader that broadcast the single configured value across all four
    fields would be caught."""
    settings = HistorySettings(tau_fitness_days=99.0)
    result = resolve_constants(settings)
    assert result.tau_fitness_days == 99.0
    assert result.tau_fatigue_days == SEED_CONSTANTS.tau_fatigue_days
    assert result.k_fitness == SEED_CONSTANTS.k_fitness
    assert result.k_fatigue == SEED_CONSTANTS.k_fatigue
    assert result.provenance is ConstantProvenance.CONFIGURED


def test_resolve_constants_configured_equal_to_seed_is_still_configured() -> None:
    """Configuring a field to a value numerically equal to its own seed is
    still CONFIGURED -- provenance tracks whether the field was *set*, not
    whether the resulting value happens to differ from the seed. Named
    mutation: short-circuit and return `SEED_CONSTANTS` whenever every
    resolved field equals its seed -- this reds because the result must not
    be `SEED_CONSTANTS` by identity, and provenance must still be
    CONFIGURED, even though the value is numerically unchanged."""
    settings = HistorySettings(tau_fitness_days=SEED_CONSTANTS.tau_fitness_days)
    result = resolve_constants(settings)
    assert result is not SEED_CONSTANTS
    assert result.provenance is ConstantProvenance.CONFIGURED
    assert "tau_fitness_days" in result.origin


def test_resolve_constants_configured_zero_weighting_is_configured() -> None:
    """`k_fitness=0.0` is a legitimate configured value, not indistinguishable
    from "absent". Named mutation: replace the `is not None` presence check
    with a truthiness check -- `0.0` is falsy, so a mutant reader would treat
    this as unconfigured and return `SEED_CONSTANTS` by identity instead of a
    fresh CONFIGURED result."""
    settings = HistorySettings(k_fitness=0.0)
    result = resolve_constants(settings)
    assert result.provenance is ConstantProvenance.CONFIGURED
    assert result.k_fitness == 0.0
    assert result is not SEED_CONSTANTS


def test_resolve_constants_partial_set_is_never_labelled_seeds() -> None:
    """The central rule: a partially configured set's *provenance* is never
    `SEEDS`, even though three of its four values are numerically
    identical to the seed. Named mutation: label the result `SEEDS`
    whenever any field still equals its seed value -- this assertion
    reds, discriminating provenance from mere numeric coincidence."""
    settings = HistorySettings(k_fatigue=SEED_CONSTANTS.k_fatigue + 1.0)
    result = resolve_constants(settings)
    assert result.provenance is not ConstantProvenance.SEEDS
    assert result.provenance is ConstantProvenance.CONFIGURED


def test_resolve_constants_origin_names_each_configured_and_each_seeded_key() -> None:
    """The origin line names each configured key together with its value
    (not only by name, since a value could coincidentally match another
    field's own default) and separately names each key left at its seed,
    without a value attached, in the seeded half of the line. Named
    mutation: build the origin line from only the configured keys, saying
    nothing about which keys were left at seed -- the seeded-half
    assertions below red while the configured-half assertions stay green,
    discriminating the two halves of the rule. Named mutation: build
    `seeded_names` from the full `_CONFIGURABLE_FIELDS` list instead of
    filtering to keys not in `configured` (i.e. `seeded_names =
    list(_CONFIGURABLE_FIELDS)`) -- every configured key then also appears
    in the seeded clause, and the assertions above pinning
    `tau_fitness_days` and `k_fatigue` absent from the seeded clause red.
    Named mutation: the same substitution for `configured_names`
    (`configured_names = list(_CONFIGURABLE_FIELDS)`) -- every seeded key
    then also appears with a value in the configured clause, and the
    assertions above pinning `tau_fatigue_days=` and `k_fitness=` absent
    from the configured clause red."""
    settings = HistorySettings(tau_fitness_days=50.0, k_fatigue=4.0)
    result = resolve_constants(settings)

    configured_clause, _, seeded_clause = result.origin.partition(
        "left at fitdocs' shipped seed for "
    )
    assert "tau_fitness_days=50.0" in configured_clause
    assert "k_fatigue=4.0" in configured_clause
    assert "tau_fatigue_days=" not in configured_clause
    assert "k_fitness=" not in configured_clause

    assert seeded_clause, "origin line must name the keys left at their seed"
    assert "tau_fatigue_days" in seeded_clause
    assert "tau_fatigue_days=" not in seeded_clause
    assert "k_fitness" in seeded_clause
    assert "k_fitness=" not in seeded_clause
    assert "tau_fitness_days" not in seeded_clause
    assert "k_fatigue" not in seeded_clause


def test_resolve_constants_is_pure_and_does_not_mutate_seed_constants() -> None:
    """Calling `resolve_constants` with a configured setting must not alter
    the shared `SEED_CONSTANTS` singleton other callers read."""
    before = SEED_CONSTANTS.tau_fitness_days
    resolve_constants(HistorySettings(tau_fitness_days=999.0))
    assert SEED_CONSTANTS.tau_fitness_days == before
