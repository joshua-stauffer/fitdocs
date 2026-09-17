"""Tests for the activity-qa-flags flag vocabulary (``qa/types.py``).

Covers Requirements 1.1, 1.7, 6.4, 6.9, 6.10, 6.11 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and the "Leaf --
src/fitdocs/load/qa/types.py" / "FlagVocabulary" component in design.md
(lines 636-738).

Task 1.1's whole footprint is this module, ``tests/load/qa/__init__.py``,
``src/fitdocs/load/qa/types.py`` and ``src/fitdocs/load/qa/__init__.py``, plus
one pre-existing test module extended (not created) here:
``tests/load/test_packaging.py``, whose ``_LOAD_MODULE_ALLOWLIST`` gained the
two new module paths so the wheel-contents guard stays accurate.
No check module (``cadence.py``, ``divergence.py``, ``drift.py``,
``staleness.py``), ``sources.py`` or ``flags.py`` exists yet -- those are
later tasks (1.2, 2.x, 3.1) and this module never imports them.
"""

from __future__ import annotations

import dataclasses
import inspect
import re

import pytest

from fitdocs.load import qa
from fitdocs.load.qa import types
from fitdocs.load.qa.types import (
    DEFAULT_AEROBIC_DRIFT_MAX_PCT,
    DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM,
    DEFAULT_CADENCE_LOCK_MIN_CORRELATION,
    DEFAULT_CADENCE_LOCK_MIN_DURATION_S,
    DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE,
    DEFAULT_CADENCE_LOCK_WINDOW_S,
    DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA,
    FLAG_LABELS,
    FLAG_ORDER,
    STEPS_PER_CADENCE_REVOLUTION,
    FlagKey,
    FlagSettings,
)

_MODULE_SOURCE = inspect.getsource(types)

# The literal expected emission order, defined here as plain strings rather
# than by indexing FLAG_ORDER/FlagKey or referencing FlagKey attributes --
# see the parametrize trap note below. Using plain strings (not
# ``FlagKey.CADENCE_LOCK`` etc.) matters at *module* scope specifically: an
# attribute reference here would be resolved once, at test-collection time,
# so a FlagKey member actually removed from production would raise
# AttributeError while this module is being collected -- aborting every test
# in the file, not just the one test that names the missing entry. Plain
# strings defer that comparison into the test body, where a single
# assertion can fail instead of the whole module failing to collect.
_EXPECTED_ORDER_VALUES = (
    "cadence-lock",
    "channel-divergence",
    "aerobic-drift",
    "benchmark-staleness",
)


# ---------------------------------------------------------------------------
# 1.1 -- four identified checks, closed set
# ---------------------------------------------------------------------------


def test_flag_key_is_the_closed_four_member_set() -> None:
    assert {member.value for member in FlagKey} == {
        "cadence-lock",
        "channel-divergence",
        "aerobic-drift",
        "benchmark-staleness",
    }
    assert len(FlagKey) == 4


def test_flag_key_members_are_directly_comparable_to_plain_strings() -> None:
    """StrEnum, not plain Enum: a caller comparing a member directly against
    a plain string (no ``.value``) must work. ``{member.value ...}`` above
    reads identically under either base, so that assertion alone would not
    catch a regression to plain ``Enum`` -- this compares a member
    directly."""
    assert FlagKey.CADENCE_LOCK == "cadence-lock"
    assert isinstance(FlagKey.CADENCE_LOCK, str)


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (0, "cadence-lock"),
        (1, "channel-divergence"),
        (2, "aerobic-drift"),
        (3, "benchmark-staleness"),
    ],
)
def test_flag_key_exact_string_values(member: int, value: str) -> None:
    """Pins the exact wire/display string for each key -- these values are
    user-visible (rendered into the document) and load-bearing for any
    external consumer, so a rename must be a deliberate, visible diff here."""
    assert list(FlagKey)[member].value == value


# ---------------------------------------------------------------------------
# 1.1 -- FLAG_LABELS is total over FlagKey
# ---------------------------------------------------------------------------


def test_flag_labels_is_total_over_flag_key() -> None:
    assert set(FLAG_LABELS.keys()) == set(FlagKey)


def test_flag_labels_values_are_non_empty_strings() -> None:
    for label in FLAG_LABELS.values():
        assert isinstance(label, str)
        assert label.strip() != ""


def test_flag_labels_exact_display_strings() -> None:
    """Pins the exact display label design.md:673 documents for each check
    -- these are rendered verbatim into the training-load section, so a
    rename is a deliberate, visible diff here rather than something a
    non-emptiness check alone would catch."""
    assert FLAG_LABELS[FlagKey.CADENCE_LOCK] == "Cadence lock"
    assert FLAG_LABELS[FlagKey.CHANNEL_DIVERGENCE] == "Channel divergence"
    assert FLAG_LABELS[FlagKey.AEROBIC_DRIFT] == "Aerobic drift"
    assert FLAG_LABELS[FlagKey.BENCHMARK_STALENESS] == "Benchmark staleness"


# ---------------------------------------------------------------------------
# 1.7 -- FLAG_ORDER: a fixed tuple, exactly-once over FlagKey
# ---------------------------------------------------------------------------


def test_flag_order_is_a_tuple() -> None:
    assert isinstance(FLAG_ORDER, tuple)


def test_flag_order_contains_every_flag_key_exactly_once() -> None:
    """Defensive against vacuous introspection (change-protocol.md 'Fixture
    Discrimination'): asserts against the *actual* FlagKey membership rather
    than merely asserting FLAG_ORDER is non-empty, so an entry dropped from
    or duplicated within FLAG_ORDER (with FlagKey itself unchanged) reds
    this test. Removing a member from FlagKey itself is a different, more
    drastic mutation: production's own FLAG_ORDER tuple references FlagKey
    members by attribute, so that mutation breaks ``qa/types.py`` at import
    time -- this test module fails to collect at all, independent of
    anything in this file."""
    assert set(FLAG_ORDER) == set(FlagKey)
    assert len(FLAG_ORDER) == len(set(FLAG_ORDER))
    assert len(FLAG_ORDER) == len(FlagKey)


def test_flag_order_matches_the_documented_fixed_order() -> None:
    """Parametrizing over ``enumerate(FLAG_ORDER)`` or ``FLAG_ORDER[i]``
    inside the decorator would run at collection time: removing or
    reordering one entry would abort collection for the whole module with an
    opaque IndexError instead of reddening one assertion (the trap recorded
    against this exact flag set). Comparing against a literal expected order
    defined in this file avoids that -- and that literal is built from plain
    strings (``_EXPECTED_ORDER_VALUES``), not ``FlagKey`` attribute
    references, so this comparison itself never touches ``FlagKey`` at
    collection time either."""
    assert tuple(member.value for member in FLAG_ORDER) == _EXPECTED_ORDER_VALUES


# ---------------------------------------------------------------------------
# STEPS_PER_CADENCE_REVOLUTION -- ingest semantic conversion factor
# ---------------------------------------------------------------------------


def test_steps_per_cadence_revolution_value() -> None:
    assert STEPS_PER_CADENCE_REVOLUTION == 2


def test_steps_per_cadence_revolution_is_int() -> None:
    assert isinstance(STEPS_PER_CADENCE_REVOLUTION, int)


def test_steps_per_cadence_revolution_docstring_names_ingest_semantic_and_trigger() -> (
    None
):
    """6.4 / design Risks: the docstring must name the FIT per-limb cadence
    ingest semantic this constant depends on and the revalidation trigger if
    that semantic ever changes."""
    match = re.search(
        r"STEPS_PER_CADENCE_REVOLUTION[^\"]*\"\"\"(.*?)\"\"\"",
        _MODULE_SOURCE,
        re.DOTALL,
    )
    assert match is not None
    doc = match.group(1)
    assert "per limb" in doc or "per-limb" in doc
    assert "cadence" in doc.lower()
    # Names the revalidation trigger explicitly.
    assert "ingest" in doc.lower() or "semantic" in doc.lower()


# ---------------------------------------------------------------------------
# 6.4 -- the seven tunable defaults and their documented values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("constant", "expected"),
    [
        (DEFAULT_CADENCE_LOCK_MIN_CORRELATION, 0.90),
        (DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM, 5.0),
        (DEFAULT_CADENCE_LOCK_WINDOW_S, 120),
        (DEFAULT_CADENCE_LOCK_MIN_DURATION_S, 300),
        (DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE, 0.50),
        (DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA, 0.20),
        (DEFAULT_AEROBIC_DRIFT_MAX_PCT, 5.0),
    ],
)
def test_default_constant_values(constant: float, expected: float) -> None:
    assert constant == expected


def test_cadence_lock_window_and_duration_are_int() -> None:
    """Span width and minimum duration are second counts, not fractional --
    distinguishes them from the float thresholds by type, not just value."""
    assert isinstance(DEFAULT_CADENCE_LOCK_WINDOW_S, int)
    assert isinstance(DEFAULT_CADENCE_LOCK_MIN_DURATION_S, int)


# ---------------------------------------------------------------------------
# 6.10, 6.11 -- every default's provenance is greppable from its own
# docstring; the divergence tolerance alone is provisional
# ---------------------------------------------------------------------------

# The closed set of provenance markers Req 6.10 distinguishes between: a
# measured value, a fitdocs-chosen value, a published value (named by
# publisher), and (divergence tolerance alone) an explicit provisional
# marker. Each is matched at the *start* of the docstring -- not as an
# unanchored substring -- specifically so a docstring cannot satisfy two
# classes at once and cannot pass by accidentally containing an unrelated
# token (a stray digit, the word "fitdocs" appearing anywhere).
_MEASURED_MARKER = "Measured:"
_FITDOCS_OWN_MARKER = "fitdocs' own choice"
_PROVISIONAL_MARKER = "PROVISIONAL --"
_PUBLISHED_MARKER_RE = re.compile(r"^[A-Z][A-Za-z]*-published:")


def _docstring_for(name: str) -> str:
    match = re.search(rf"{name}[^\"]*\"\"\"(.*?)\"\"\"", _MODULE_SOURCE, re.DOTALL)
    assert match is not None, f"{name} has no docstring in source"
    return match.group(1)


def _classify_provenance(doc: str) -> str:
    """Classifies a constant's docstring into exactly one of the closed set
    Req 6.10 requires. Asserts mutual exclusivity itself (a docstring
    carrying two markers, or none, fails here) rather than leaving that to
    callers."""
    stripped = doc.strip()
    present = {
        "measured": stripped.startswith(_MEASURED_MARKER),
        "fitdocs_own": stripped.startswith(_FITDOCS_OWN_MARKER),
        "provisional": stripped.startswith(_PROVISIONAL_MARKER),
        "published": bool(_PUBLISHED_MARKER_RE.match(stripped)),
    }
    matched = [name for name, hit in present.items() if hit]
    assert len(matched) == 1, (
        f"docstring must open with exactly one closed-set provenance "
        f"marker (measured / fitdocs' own choice / provisional / "
        f"<Publisher>-published), found {matched}: {doc!r}"
    )
    return matched[0]


@pytest.mark.parametrize(
    ("name", "expected_substring", "expected_class"),
    [
        ("DEFAULT_CADENCE_LOCK_MIN_CORRELATION", "0.605", "measured"),
        ("DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM", "9", "measured"),
        ("DEFAULT_CADENCE_LOCK_WINDOW_S", "fitdocs", "fitdocs_own"),
        ("DEFAULT_CADENCE_LOCK_MIN_DURATION_S", "137", "measured"),
        ("DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE", "fitdocs", "fitdocs_own"),
        ("DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA", "PROVISIONAL --", "provisional"),
        ("DEFAULT_AEROBIC_DRIFT_MAX_PCT", "TrainingPeaks", "published"),
    ],
)
def test_default_constant_docstring_carries_its_provenance(
    name: str, expected_substring: str, expected_class: str
) -> None:
    """Each constant's own docstring must name its provenance -- a
    measurement, a publisher, or (divergence tolerance alone) an explicit
    PROVISIONAL marker naming the record task 1.2 will land. The substring
    check alone is incidental evidence (an exact figure or token); the
    classification check is the one that actually pins Req 6.10's
    measured-vs-fitdocs'-own-vs-published-vs-provisional distinction."""
    doc = _docstring_for(name)
    assert expected_substring in doc
    assert _classify_provenance(doc) == expected_class


def test_only_the_divergence_tolerance_is_marked_provisional() -> None:
    """6.10/6.11: exactly one default (the divergence tolerance) is
    provisional; the other six must not carry the PROVISIONAL marker, so a
    reader can trust its absence to mean the value is sourced."""
    non_provisional = [
        "DEFAULT_CADENCE_LOCK_MIN_CORRELATION",
        "DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM",
        "DEFAULT_CADENCE_LOCK_WINDOW_S",
        "DEFAULT_CADENCE_LOCK_MIN_DURATION_S",
        "DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE",
        "DEFAULT_AEROBIC_DRIFT_MAX_PCT",
    ]
    for name in non_provisional:
        doc = _docstring_for(name)
        assert "PROVISIONAL" not in doc
        assert _classify_provenance(doc) != "provisional"


def test_divergence_tolerance_docstring_points_at_provisional_defaults_entry() -> None:
    """6.11: the docstring must name the PROVISIONAL_DEFAULTS entry key that
    task 1.2's sources.py will define, and must not claim the value is
    measured -- checked directly, not merely by the presence of the
    PROVISIONAL marker, so a docstring that keeps that marker while also
    fabricating a "Measured: ..." sentence still reds this test."""
    doc = _docstring_for("DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA")
    assert "PROVISIONAL_DEFAULTS" in doc
    assert "divergence_max_intensity_delta" in doc
    assert "Measured:" not in doc


def test_module_never_imports_a_check_module_or_sources() -> None:
    """Task-boundary guard: this task creates only the leaf vocabulary. It
    must not import qa.sources, qa.cadence, qa.divergence, qa.drift,
    qa.staleness or qa.flags -- none of those modules exist yet, and a
    docstring is allowed to *name* task 1.2's sources.py prospectively but
    the module must not import it."""
    for forbidden in (
        "qa.sources",
        "qa.cadence",
        "qa.divergence",
        "qa.drift",
        "qa.staleness",
        "qa.flags",
    ):
        assert f"from fitdocs.load.{forbidden}" not in _MODULE_SOURCE
        assert f"import fitdocs.load.{forbidden}" not in _MODULE_SOURCE


def test_module_does_not_carry_a_staleness_window_constant() -> None:
    """6.9: no staleness-window default belongs in this module -- the
    benchmark store's own configured window is the only one."""
    assert "STALENESS_WINDOW" not in _MODULE_SOURCE
    assert "staleness_window" not in _MODULE_SOURCE.lower().replace(
        "benchmark_staleness", ""
    )


# ---------------------------------------------------------------------------
# FlagSettings -- frozen dataclass, seven fields, defaults match constants
# ---------------------------------------------------------------------------


def test_flag_settings_is_frozen() -> None:
    assert dataclasses.is_dataclass(FlagSettings)
    settings = FlagSettings()
    field_name = dataclasses.fields(FlagSettings)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(settings, field_name, 0.0)


def test_flag_settings_has_exactly_seven_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(FlagSettings)}
    assert field_names == {
        "cadence_lock_min_correlation",
        "cadence_lock_max_delta_bpm",
        "cadence_lock_window_s",
        "cadence_lock_min_duration_s",
        "cadence_lock_min_paired_coverage",
        "divergence_max_intensity_delta",
        "aerobic_drift_max_pct",
    }
    assert len(field_names) == 7


def test_flag_settings_carries_no_staleness_window_field() -> None:
    """6.9: negative assertion pinned as its own test so a future field
    addition to FlagSettings is caught by name, not just by the exact-set
    assertion above happening to also cover it."""
    field_names = {f.name for f in dataclasses.fields(FlagSettings)}
    assert not any("stale" in name for name in field_names)
    # "window" alone is not forbidden -- cadence_lock_window_s is a
    # legitimate span-width field, not a staleness window; only a
    # staleness-specific window is disallowed (Req 6.9).
    assert not any("staleness_window" in name for name in field_names)


def test_flag_settings_defaults_match_the_documented_constants() -> None:
    settings = FlagSettings()
    assert settings.cadence_lock_min_correlation == DEFAULT_CADENCE_LOCK_MIN_CORRELATION
    assert settings.cadence_lock_max_delta_bpm == DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM
    assert settings.cadence_lock_window_s == DEFAULT_CADENCE_LOCK_WINDOW_S
    assert settings.cadence_lock_min_duration_s == DEFAULT_CADENCE_LOCK_MIN_DURATION_S
    assert (
        settings.cadence_lock_min_paired_coverage
        == DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE
    )
    assert (
        settings.divergence_max_intensity_delta
        == DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA
    )
    assert settings.aerobic_drift_max_pct == DEFAULT_AEROBIC_DRIFT_MAX_PCT


def test_flag_settings_construction_validates_nothing() -> None:
    """Design postcondition: construction validates nothing -- validation is
    the settings reader's job (task 1.3), not this dataclass's. An
    out-of-range value must be accepted here."""
    settings = FlagSettings(cadence_lock_min_correlation=-5.0)
    assert settings.cadence_lock_min_correlation == -5.0


# ---------------------------------------------------------------------------
# Package initializer -- ordinary eager re-export, no lazy __getattr__
# ---------------------------------------------------------------------------


def test_package_reexports_flag_vocabulary_names() -> None:
    assert qa.FlagKey is FlagKey
    assert qa.FLAG_LABELS is FLAG_LABELS
    assert qa.FLAG_ORDER is FLAG_ORDER
    assert qa.FlagSettings is FlagSettings
    assert qa.STEPS_PER_CADENCE_REVOLUTION is STEPS_PER_CADENCE_REVOLUTION
    assert (
        qa.DEFAULT_CADENCE_LOCK_MIN_CORRELATION == DEFAULT_CADENCE_LOCK_MIN_CORRELATION
    )
    assert qa.DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM == DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM
    assert qa.DEFAULT_CADENCE_LOCK_WINDOW_S == DEFAULT_CADENCE_LOCK_WINDOW_S
    assert qa.DEFAULT_CADENCE_LOCK_MIN_DURATION_S == DEFAULT_CADENCE_LOCK_MIN_DURATION_S
    assert (
        qa.DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE
        == DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE
    )
    assert (
        qa.DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA
        == DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA
    )
    assert qa.DEFAULT_AEROBIC_DRIFT_MAX_PCT == DEFAULT_AEROBIC_DRIFT_MAX_PCT


def test_package_init_has_no_lazy_getattr() -> None:
    """The import-cycle invariant that would have required a lazy
    __getattr__ is withdrawn (design Amendment 3 / tasks.md Amendments):
    this is an ordinary eager package initializer."""
    init_source = inspect.getsource(qa)
    assert "def __getattr__" not in init_source
    assert "import TYPE_CHECKING" not in init_source
    assert "if TYPE_CHECKING" not in init_source
