"""Tests for the ``[plans]`` settings reader and the lexical plan-source
directory resolver (training-blocks spec, task 4.1; Req 1.8, 1.9, 8.3). See
the "PlanSettings (`src/fitdocs/plans/settings.py`)" component in
`.kiro/specs/training-blocks/design.md`.

Two things are pinned here:

* :func:`load_plan_settings` -- the peer table reader beside
  ``load_history_settings``, ``load_load_settings``,
  ``tile_settings_from_document``, ``load_inbox_settings`` and
  ``load_plugin_settings``. An absent file, an absent ``[plans]`` table and
  a present-but-empty one all yield :data:`DEFAULT_PLAN_SETTINGS` -- never
  an error; unknown keys are ignored; a non-string, empty or boolean
  ``path`` raises :class:`PlanSettingsError` naming the key.
* :func:`resolve_plans_dir` -- purely lexical: an absolute path used as
  given, a relative one resolved against the data root, normalised with no
  filesystem access. It refuses a result equal to the data root itself or
  lying inside any of :data:`fitdocs.layout.OWNED_PATHS`'s prefixes,
  compared by path component rather than by string prefix -- ``blocks-mine``
  is accepted where ``blocks`` is refused.

The reader never opens a file: every case here hands it an already-parsed
mapping (a plain ``dict``, matching what ``tomllib`` would produce) and a
representative ``settings_file`` path used only to name the file in errors.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from fitdocs.layout import (
    BLOCKS_DIR,
    DEFAULT_PLANS_DIR,
    HISTORY_ASSETS_SUBDIR,
    HISTORY_DIR,
    OWNED_PATHS,
    WORKOUTS_DIR,
)
from fitdocs.plans.settings import (
    DEFAULT_PLAN_SETTINGS,
    PLANS_TABLE,
    PlanSettings,
    PlanSettingsError,
    load_plan_settings,
    resolve_plans_dir,
)
from fitdocs.settings import SettingsError

DATA_ROOT = Path("/data-root")
SETTINGS_FILE = Path("/cfg/fitdocs.toml")
"""Deliberately *not* nested under `DATA_ROOT` and sharing no string prefix
with it (unlike `<data_root>/fitdocs.toml`, the real on-disk relationship) --
so `str(expected_resolved) in message` in the refused-locations sweep below
cannot be satisfied merely because `str(SETTINGS_FILE)` happens to already
contain `str(DATA_ROOT)` as a substring. A settings file living under the
data root would make every equals-root case's resolved-path assertion an
ever-present token in disguise, trivially true from the settings-file
mention alone."""


# --- PlanSettings: immutable ---------------------------------------------


def test_plan_settings_is_frozen() -> None:
    """`PlanSettings` is immutable -- assigning to `path` raises. Named
    mutation: drop `frozen=True` from the `@dataclass` decorator -- this
    assertion reds."""
    settings = PlanSettings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.path = "elsewhere"  # type: ignore[misc]


# --- load_plan_settings: absence is default, never an error --------------


def test_absent_file_yields_the_default_by_identity() -> None:
    """An empty document (the shared reader's absent-file case) yields
    `DEFAULT_PLAN_SETTINGS` -- checked by identity, not merely equality, so
    a reader that reconstructs an equal-but-fresh instance instead of
    returning the shared default fails this assertion."""
    result = load_plan_settings({}, SETTINGS_FILE)
    assert result is DEFAULT_PLAN_SETTINGS


def test_absent_plans_table_in_a_nonempty_document_yields_the_default() -> None:
    """A document with other tables (`[tiles]`, `[history]`, ...) but no
    `[plans]` key still yields the default -- the shared-file case this
    reader must never mistake for a malformed table."""
    document = {"tiles": {"enabled": True}, "history": {"tau_fitness_days": 5.0}}
    result = load_plan_settings(document, SETTINGS_FILE)
    assert result is DEFAULT_PLAN_SETTINGS


def test_empty_plans_table_yields_the_default_by_identity() -> None:
    """A present but empty `[plans]` table -- `path` absent -- yields
    `DEFAULT_PLAN_SETTINGS` by identity, not merely an equal instance.
    Named mutation: in the absent-key branch, construct and return a fresh
    `PlanSettings()` instead of the shared default -- equality still holds
    but this `is` assertion reds."""
    result = load_plan_settings({PLANS_TABLE: {}}, SETTINGS_FILE)
    assert result is DEFAULT_PLAN_SETTINGS


@pytest.mark.parametrize(
    "value",
    ["nope", 5, [{}]],
    ids=["string", "int", "array-of-tables"],
)
def test_non_table_plans_value_raises(value: object) -> None:
    """`[plans]` set to anything but a table raises `PlanSettingsError`,
    naming the settings file -- including a string, an int, and the
    `[[plans]]` array-of-tables shape (a `list`, which a mutant guard of
    `isinstance(table, (dict, list))` would wrongly accept)."""
    with pytest.raises(PlanSettingsError) as excinfo:
        load_plan_settings({PLANS_TABLE: value}, SETTINGS_FILE)
    assert str(SETTINGS_FILE) in str(excinfo.value)


def test_unknown_key_inside_plans_is_ignored() -> None:
    """An unrecognized key inside `[plans]` is ignored, not rejected -- the
    document is shared, and a later sibling table might one day claim it.
    Named mutation: raise on an unrecognized key -- this test reds, while
    the malformed-`path` tests below (which target the *recognized* `path`
    key with a bad value) stay green, discriminating this rule from those."""
    document = {PLANS_TABLE: {"totally_unknown_key": 123}}
    result = load_plan_settings(document, SETTINGS_FILE)
    assert result == DEFAULT_PLAN_SETTINGS


# --- load_plan_settings: valid configuration is projected -----------------


def test_valid_relative_path_is_kept_verbatim() -> None:
    result = load_plan_settings({PLANS_TABLE: {"path": "my-plans"}}, SETTINGS_FILE)
    assert result.path == "my-plans"


def test_valid_absolute_path_is_kept_verbatim() -> None:
    result = load_plan_settings(
        {PLANS_TABLE: {"path": "/elsewhere/plans"}}, SETTINGS_FILE
    )
    assert result.path == "/elsewhere/plans"


def test_plans_table_is_named_plans_in_the_settings_file() -> None:
    """The table an athlete writes is literally `[plans]` -- pinned with
    the string an athlete types, not with the constant imported from the
    module under test. Named mutation: `PLANS_TABLE = "plann"` in
    `settings.py` -- the literal-keyed document below then reads as an
    absent table, `path` comes back `None`, and this assertion reds."""
    assert PLANS_TABLE == "plans"
    result = load_plan_settings({"plans": {"path": "my-plans"}}, SETTINGS_FILE)
    assert result.path == "my-plans"


# --- load_plan_settings: absent path is None, never the default string ---


def test_absent_path_is_kept_as_none_not_defaulted_inside_the_settings_value() -> None:
    """An absent `path` is `None`, not the default directory name baked
    into the settings value -- `resolve_plans_dir` applies the default, not
    this reader. Named mutation: default `path` to `DEFAULT_PLANS_DIR`
    inside `load_plan_settings`'s absent-key branch (`return
    PlanSettings(path=DEFAULT_PLANS_DIR)` instead of `return
    DEFAULT_PLAN_SETTINGS`) -- this assertion reds directly on the field,
    and `test_empty_plans_table_yields_the_default_by_identity` above reds
    too, because that branch then returns a freshly constructed
    `PlanSettings` instance rather than the shared `DEFAULT_PLAN_SETTINGS`
    object, and `is` compares object identity, not field equality."""
    result = load_plan_settings({PLANS_TABLE: {}}, SETTINGS_FILE)
    assert result.path is None


# --- load_plan_settings: malformed path raises ----------------------------


def test_non_string_path_raises_naming_the_key() -> None:
    with pytest.raises(PlanSettingsError) as excinfo:
        load_plan_settings({PLANS_TABLE: {"path": 5}}, SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(SETTINGS_FILE) in message
    assert "path" in message


def test_empty_string_path_raises_naming_the_key() -> None:
    with pytest.raises(PlanSettingsError) as excinfo:
        load_plan_settings({PLANS_TABLE: {"path": ""}}, SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(SETTINGS_FILE) in message
    assert "path" in message


def test_boolean_path_raises_naming_the_key() -> None:
    """A boolean is rejected -- `bool` is not a `str` subclass in Python,
    so this is guarded by the plain `not isinstance(value, str)` type
    check rather than needing a separate explicit `isinstance(value,
    bool)` exclusion (unlike the numeric-field siblings in
    `history/settings.py`, where `bool` *is* an `int` subclass and the
    explicit exclusion is load-bearing). Named mutation: replace the whole
    guard with a truthiness-only check (`if not value:`) -- a naive reader
    that skips the `isinstance` check entirely would accept `True` (and
    any other non-string truthy value) since it never inspects the type,
    only the value's boolishness; this assertion reds together with
    `test_non_string_path_raises_naming_the_key` (both `True` and `5` are
    truthy), while `test_empty_string_path_raises_naming_the_key` stays
    green (`""` is falsy either way)."""
    with pytest.raises(PlanSettingsError) as excinfo:
        load_plan_settings({PLANS_TABLE: {"path": True}}, SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(SETTINGS_FILE) in message
    assert "path" in message


def test_plan_settings_error_is_a_settings_error() -> None:
    """`PlanSettingsError` subclasses the shared `SettingsError`, so the
    CLI's existing `except SettingsError` handler maps it with no new
    branch (Req 8.3). Named mutation: make `PlanSettingsError` subclass
    `Exception` directly instead -- this assertion reds."""
    assert issubclass(PlanSettingsError, SettingsError)


# --- resolve_plans_dir: postconditions ------------------------------------


def test_default_settings_resolve_to_root_slash_plans() -> None:
    """Design postcondition: `resolve_plans_dir(root, DEFAULT_PLAN_SETTINGS,
    f) == root / "plans"`. Named mutation: resolve the default directory
    name from a hard-coded `"plan"` literal instead of
    `layout.DEFAULT_PLANS_DIR` -- this assertion reds."""
    result = resolve_plans_dir(DATA_ROOT, DEFAULT_PLAN_SETTINGS, SETTINGS_FILE)
    assert result == DATA_ROOT / "plans"
    assert result == DATA_ROOT / DEFAULT_PLANS_DIR


# --- resolve_plans_dir: valid paths ----------------------------------------


def test_valid_relative_path_resolves_against_the_data_root() -> None:
    settings = PlanSettings(path="my-plans")
    result = resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert result == DATA_ROOT / "my-plans"


def test_valid_absolute_path_is_used_as_given() -> None:
    """An absolute `path` is used as given, never rooted under the data
    root. `pathlib`'s own `/` join already discards the left operand when
    the right one is absolute, so branching on `is_absolute()` before a
    `Path./`-join is not itself what this pins -- a hand-rolled
    string-concatenation join (`str(root) + str(candidate)`, never a
    `Path`-join) *would* wrongly prefix the data root even for an absolute
    `path`; this is the named mutation, and it reds this assertion (as well
    as every other resolution assertion in this module, since it replaces
    the one join both the relative and the absolute case share)."""
    settings = PlanSettings(path="/elsewhere/plans")
    result = resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert result == Path("/elsewhere/plans")
    assert not str(result).startswith(str(DATA_ROOT))


# --- resolve_plans_dir: refused locations ----------------------------------

_OWNED_TOP_LEVEL_NAMES: tuple[str, ...] = tuple(
    sorted({Path(prefix).parts[0] for prefix in OWNED_PATHS})
)
"""Every distinct top-level directory name `OWNED_PATHS` names, derived from
the constant itself (never hard-coded), so a fifth or sixth owned directory
added to `layout.py` is swept into the refusal parametrization below without
this test file changing. A hard-coded subset (e.g. `{"blocks", "workouts",
".fitdocs"}`) would leave `history/`, `history/assets/` and `fit-archive/`
unpinned -- this derivation is the guard against exactly that."""

_REFUSED_LOCATIONS: tuple[tuple[str, Path], ...] = (
    (".", DATA_ROOT),
    ("../elsewhere/../data-root", DATA_ROOT),
    *((name, DATA_ROOT / name) for name in _OWNED_TOP_LEVEL_NAMES),
    (f"{BLOCKS_DIR}/sub", DATA_ROOT / BLOCKS_DIR / "sub"),
    (
        f"{HISTORY_DIR}/{HISTORY_ASSETS_SUBDIR}",
        DATA_ROOT / HISTORY_DIR / HISTORY_ASSETS_SUBDIR,
    ),
)
"""Every case pairs the configured `path` with the resolved `Path` the
error message must name. The two equals-root cases (`.` and the
parent-traversal) resolve to `DATA_ROOT` itself; every owned-prefix case is
derived from `_OWNED_TOP_LEVEL_NAMES` (sweeping every entry of
`layout.OWNED_PATHS`, not a hand-picked subset) plus two cases the sweep
alone would not reach: a path *beneath* an owned top-level directory
(`blocks/sub`), and a *nested* owned entry (`history/assets`, which is its
own line in `OWNED_PATHS` distinct from the top-level `history/` line, even
though both are refused via the same first-path-component check)."""


@pytest.mark.parametrize(
    "path, expected_resolved",
    _REFUSED_LOCATIONS,
    ids=[case[0] for case in _REFUSED_LOCATIONS],
)
def test_refused_locations_raise_naming_the_key_and_the_resolved_path(
    path: str, expected_resolved: Path
) -> None:
    """Every one of these resolves either to the data root itself or
    beneath an owned prefix, and each must raise, naming the literal
    `[plans] path` key and the specific resolved path in the message --
    not merely the bare word "path", which also appears in the owned-prefix
    message's own trailing "...outside every owned path" clause and so
    would stay green under a key rename alone (an ever-present token); and
    not merely the settings file, which every one of these messages already
    names regardless of which case is under test."""
    settings = PlanSettings(path=path)
    with pytest.raises(PlanSettingsError) as excinfo:
        resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    message = str(excinfo.value)
    assert str(SETTINGS_FILE) in message
    assert "[plans] path" in message
    assert str(expected_resolved) in message


def test_dot_is_refused_even_if_only_the_equals_root_rule_is_active() -> None:
    """`.` resolves to the data root itself and is refused by the
    equals-root rule alone, independent of the owned-prefix rule -- pinned
    on its own (separately from `BLOCKS_DIR`'s owned-prefix refusal in the
    parametrized sweep above) so a mutation that drops only the
    `resolved == root` branch while leaving the owned-prefix check intact
    is distinguishable: this assertion would red while the `BLOCKS_DIR`
    case in the parametrized sweep stays green, since `BLOCKS_DIR` is never
    equal to `DATA_ROOT`, only beneath it."""
    with pytest.raises(PlanSettingsError):
        resolve_plans_dir(DATA_ROOT, PlanSettings(path="."), SETTINGS_FILE)


def test_directory_merely_starting_with_an_owned_name_is_accepted() -> None:
    """`blocks-mine` shares no path *component* with the owned `blocks/`
    prefix, only a string prefix -- it must be accepted. Named mutation:
    compare with `str(resolved).startswith(str(root / BLOCKS_DIR))` (or
    equivalently on the raw `path` string) instead of a path-component
    test -- this assertion reds, since the string `"blocks-mine"` does
    start with `"blocks"`."""
    settings = PlanSettings(path="blocks-mine")
    result = resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert result == DATA_ROOT / "blocks-mine"


@pytest.mark.parametrize(
    "path, expected",
    [
        (f"my-plans/{BLOCKS_DIR}", DATA_ROOT / "my-plans" / BLOCKS_DIR),
        (
            f"training/{WORKOUTS_DIR}/2026",
            DATA_ROOT / "training" / WORKOUTS_DIR / "2026",
        ),
    ],
    ids=["blocks-nested", "workouts-nested"],
)
def test_owned_name_below_a_non_owned_top_level_is_accepted(
    path: str, expected: Path
) -> None:
    """The owned-prefix check only ever inspects the resolved path's
    *first* component (`relative.parts[0]`) -- an owned name appearing one
    or more levels *below* a non-owned top-level directory is unrelated to
    the top-level `OWNED_PATHS` entry of the same name and must be
    accepted, the same over-refusal class as `blocks-mine` above, one
    level deeper. Named mutation: `if relative is not None and any(p in
    owned_names for p in relative.parts):` (refuse when *any* component,
    not only the first, is an owned name) -- this assertion reds for both
    parametrizations, while `test_refused_location_error_names_the_resolved_path`'s
    `blocks/sub` case (an owned name *as* the first component) stays
    refused either way, discriminating "first component only" from "any
    component"."""
    settings = PlanSettings(path=path)
    result = resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert result == expected


def test_refused_location_error_names_the_resolved_path() -> None:
    """The error names the *resolved* path, not merely the raw configured
    value -- distinguishing a message built from `settings.path` from one
    built from the actual `resolved` path, which differ once a relative
    value is joined onto the root. Named mutation: build the message from
    `settings.path` instead of the resolved `Path` -- the raw string
    `"blocks/sub"` never contains the full resolved path
    `/data-root/blocks/sub`, and this assertion reds."""
    settings = PlanSettings(path=f"{BLOCKS_DIR}/sub")
    with pytest.raises(PlanSettingsError) as excinfo:
        resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert str(DATA_ROOT / BLOCKS_DIR / "sub") in str(excinfo.value)


def test_absolute_path_outside_the_data_root_sharing_an_owned_name_is_accepted() -> (
    None
):
    """The owned-prefix rule is a property of *containment under the data
    root*, not of the resolved path's own trailing component name --
    an absolute `path` naming a directory called `blocks` that lives
    entirely outside `data_root` is unrelated to `layout.BLOCKS_DIR` under
    that root and must be accepted. Named mutation: check the owned prefix
    against `resolved`'s own last component regardless of containment
    under `root` -- this assertion reds."""
    settings = PlanSettings(path=f"/elsewhere/{BLOCKS_DIR}")
    result = resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert result == Path(f"/elsewhere/{BLOCKS_DIR}")


def test_absolute_path_resolving_inside_the_root_onto_an_owned_dir_is_refused() -> None:
    """The owned-prefix check applies to the *resolved* path's containment
    under the data root, regardless of whether the configured `path` was
    spelled relative or absolute -- an absolute `path` that happens to
    equal `data_root / BLOCKS_DIR` is exactly as unsafe as the bare
    relative `"blocks"` case above and must be refused too. Named mutation:
    guard the owned-prefix check with `if not candidate.is_absolute():`
    (skip it whenever the *configured* value was spelled absolute) -- this
    assertion reds, while the plain relative `blocks` case in the
    parametrized sweep stays green, discriminating "skip for absolute
    input" from the correct "check the resolved path's containment"."""
    settings = PlanSettings(path=str(DATA_ROOT / BLOCKS_DIR))
    with pytest.raises(PlanSettingsError) as excinfo:
        resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    message = str(excinfo.value)
    assert "[plans] path" in message
    assert str(DATA_ROOT / BLOCKS_DIR) in message


def test_accepted_relative_path_is_normalised_in_the_returned_value() -> None:
    """The *returned* path is normalised, not merely checked against a
    normalised copy internally -- `"./sub/../my-plans"` resolves to
    `DATA_ROOT / "my-plans"`, with no `.` or `..` component surviving into
    the result. Named mutation: `return joined` (the un-normalised join)
    instead of `return resolved` -- every other accepted-path fixture in
    this module is already normalised on the way in (no `.`/`..`
    component), so only a fixture like this one, whose raw and normalised
    forms differ, can catch a resolver that forgets to normalise its
    return value; this assertion reds under that mutation while every
    other accepted-path test stays green."""
    settings = PlanSettings(path="./sub/../my-plans")
    result = resolve_plans_dir(DATA_ROOT, settings, SETTINGS_FILE)
    assert result == DATA_ROOT / "my-plans"
    assert ".." not in result.parts
    # No separate assertion for a surviving "." component: `pathlib.Path`
    # strips a bare "." segment at construction time regardless of what
    # `resolve_plans_dir` does, so `"." not in result.parts` is true before
    # this call even runs and can never discriminate anything here -- the
    # `==` assertion above is what actually pins normalisation of "./".
