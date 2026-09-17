"""Tests for the activity-qa-flags provenance record (``qa/sources.py``).

Covers Requirements 3.10, 4.3, 4.5, 6.10, 6.11, 8.3 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and the "Leaf --
src/fitdocs/load/qa/sources.py" / "FlagProvenance" component in design.md
(lines 739-836).

Task 1.2's whole footprint is this module and ``src/fitdocs/load/qa/sources.py``,
plus one pre-existing test module extended (not created) here:
``tests/load/test_packaging.py``, whose ``_LOAD_MODULE_ALLOWLIST`` gained the
new module path. This module does not touch ``tests/load/channels/test_sources.py``
(``load-channels``'s own test module) or ``qa/types.py``/``qa/__init__.py``
(task 1.1's, unmodified beyond what 1.1 already landed).
"""

from __future__ import annotations

import inspect
import re

import pytest

from fitdocs.load.channels import sources as channel_sources
from fitdocs.load.qa import sources, types
from fitdocs.load.qa.sources import (
    CITATIONS,
    DIVERGENCES,
    FITDOCS_CORPUS_2026_07_25,
    INTERVALS_ICU_DECOUPLING,
    PPG_CADENCE_ARTIFACT,
    PROVISIONAL_DEFAULTS,
    TRAININGPEAKS_DECOUPLING,
    Citation,
    Divergence,
    ProvisionalDefault,
    VerificationStatus,
)

_TYPES_MODULE_SOURCE = inspect.getsource(types)

_DEFAULT_CONSTANT_NAMES = (
    "DEFAULT_CADENCE_LOCK_MIN_CORRELATION",
    "DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM",
    "DEFAULT_CADENCE_LOCK_WINDOW_S",
    "DEFAULT_CADENCE_LOCK_MIN_DURATION_S",
    "DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE",
    "DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA",
    "DEFAULT_AEROBIC_DRIFT_MAX_PCT",
)


# ---------------------------------------------------------------------------
# Docstring introspection over ``qa/types.py`` -- anchored so a missing or
# malformed docstring fails on its own rather than sliding forward into a
# neighboring constant's docstring (Implementation Notes, 1.1 -> 1.2 trap 1).
#
# The trap: a pattern shaped like ``rf"{name}[^\"]*\"\"\"(.*?)\"\"\""`` lets
# ``[^\"]*`` cross newlines and consume arbitrary code between the named
# constant and *any later* triple-quoted string in the module, so a missing
# docstring on the named constant still "matches" -- the next constant's
# docstring, silently. This helper instead requires the docstring's opening
# ``\"\"\"`` to start on the line immediately following the constant's own
# assignment line: ``[^\n]*\n\"\"\"`` cannot cross a newline before the
# triple-quote, so a missing docstring (or one separated by a blank line, or
# any other layout ``qa/types.py`` does not actually use) fails to match at
# all, asserted explicitly below, rather than silently matching downstream
# content.
# ---------------------------------------------------------------------------


def _types_docstring_for(name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}:[^\n]*\n\"\"\"(.*?)\"\"\"",
        _TYPES_MODULE_SOURCE,
        re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"{name} has no immediately-following docstring"
    return match.group(1)


def test_docstring_helper_does_not_slide_forward_into_a_neighbors_docstring() -> None:
    """Proves the anchoring actually works, independent of the real module:
    a constant with no docstring of its own must fail to match rather than
    silently returning the next constant's docstring (the exact defect noted
    in tasks.md's Implementation Notes for 1.1 -> 1.2)."""
    fabricated_source = (
        "DEFAULT_FOO: Final[float] = 1.0\n"
        "\n"
        "DEFAULT_BAR: Final[float] = 2.0\n"
        '"""Measured: bar\'s own text, not foo\'s."""\n'
    )
    match = re.search(
        r"^DEFAULT_FOO:[^\n]*\n\"\"\"(.*?)\"\"\"",
        fabricated_source,
        re.DOTALL | re.MULTILINE,
    )
    assert match is None, (
        "the anchored pattern must not slide forward past DEFAULT_FOO's "
        "missing docstring into DEFAULT_BAR's"
    )


def _setting_name_for(default_constant_name: str) -> str:
    """``DEFAULT_CADENCE_LOCK_WINDOW_S`` -> ``cadence_lock_window_s``, the
    matching ``FlagSettings`` field name every ``DEFAULT_*`` constant in
    ``qa/types.py`` defaults."""
    assert default_constant_name.startswith("DEFAULT_")
    return default_constant_name[len("DEFAULT_") :].lower()


_MEASURED_MARKER = "Measured:"
_FITDOCS_OWN_MARKER = "fitdocs' own choice"
_PROVISIONAL_MARKER = "PROVISIONAL --"
_PUBLISHED_MARKER_RE = re.compile(r"^([A-Z][A-Za-z]*)-published:")


def _classify(doc: str) -> tuple[str, str | None]:
    """Reimplements task 1.1's closed-set classification locally (this test
    module may not import ``test_types.py``, which belongs to task 1.1), and
    additionally captures the publisher name for a "published" docstring so
    it can be cross-referenced against this module's own ``CITATIONS``.
    Returns ``(class, publisher_or_none)``."""
    stripped = doc.strip()
    published_match = _PUBLISHED_MARKER_RE.match(stripped)
    present = {
        "measured": stripped.startswith(_MEASURED_MARKER),
        "fitdocs_own": stripped.startswith(_FITDOCS_OWN_MARKER),
        "provisional": stripped.startswith(_PROVISIONAL_MARKER),
        "published": published_match is not None,
    }
    matched = [name for name, hit in present.items() if hit]
    assert len(matched) == 1, (
        f"docstring must open with exactly one closed-set provenance "
        f"marker, found {matched}: {doc!r}"
    )
    kind = matched[0]
    publisher = published_match.group(1) if published_match else None
    return kind, publisher


# ---------------------------------------------------------------------------
# 6.10, 6.11 -- cross-file postcondition: every DEFAULT_* constant in
# qa/types.py names either a citation present in this module's CITATIONS or
# an entry in PROVISIONAL_DEFAULTS, and never both. This introspects
# qa/types.py's own constants against qa/sources.py's own records, not just
# this module in isolation.
# ---------------------------------------------------------------------------


def test_every_measured_default_is_backed_by_a_fitdocs_measured_citation() -> None:
    """Every 'Measured:' constant in qa/types.py must be backed by at least
    one citation in this module's CITATIONS carrying VerificationStatus.
    FITDOCS_MEASURED -- mutating FITDOCS_CORPUS_2026_07_25's verification
    away from FITDOCS_MEASURED, or removing it from CITATIONS, breaks this."""
    measured_names = [
        name
        for name in _DEFAULT_CONSTANT_NAMES
        if _classify(_types_docstring_for(name))[0] == "measured"
    ]
    assert measured_names, "fixture sanity: at least one measured default exists"
    fitdocs_measured_citations = [
        c for c in CITATIONS if c.verification == VerificationStatus.FITDOCS_MEASURED
    ]
    assert len(fitdocs_measured_citations) == 1
    assert fitdocs_measured_citations[0] is FITDOCS_CORPUS_2026_07_25
    # None of the measured settings are also recorded as provisional.
    for name in measured_names:
        assert _setting_name_for(name) not in PROVISIONAL_DEFAULTS


def test_every_published_default_names_a_citation_by_its_publisher() -> None:
    """The single 'TrainingPeaks-published:' constant must be backed by a
    citation in this module's CITATIONS whose authors match the publisher
    named in the marker -- mutating TRAININGPEAKS_DECOUPLING's authors, or
    removing it from CITATIONS, breaks this."""
    published = [
        (name, _classify(_types_docstring_for(name)))
        for name in _DEFAULT_CONSTANT_NAMES
        if _classify(_types_docstring_for(name))[0] == "published"
    ]
    assert published, "fixture sanity: at least one published default exists"
    for name, (_kind, publisher) in published:
        assert publisher is not None
        matches = [c for c in CITATIONS if c.authors == publisher]
        assert matches, f"{name} names publisher {publisher!r}, no citation matches"
        assert all(
            c.verification != VerificationStatus.FITDOCS_MEASURED for c in matches
        )
        assert _setting_name_for(name) not in PROVISIONAL_DEFAULTS


def test_provisional_default_setting_name_matches_types_docstring() -> None:
    """The one PROVISIONAL constant's setting name, as this module's
    PROVISIONAL_DEFAULTS keys it, must be exactly the setting the
    corresponding qa/types.py docstring names -- proving the cross-file link
    by construction, not by coincidence of a shared literal."""
    name = "DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA"
    kind, _publisher = _classify(_types_docstring_for(name))
    assert kind == "provisional"
    setting_name = _setting_name_for(name)
    assert setting_name in PROVISIONAL_DEFAULTS
    assert setting_name == "divergence_max_intensity_delta"
    # Not also backed by a citation -- never both.
    assert not any(c.key == setting_name for c in CITATIONS)


def test_fitdocs_own_choice_defaults_are_exempt_from_both() -> None:
    """The two 'fitdocs' own choice' constants name neither a citation nor a
    PROVISIONAL_DEFAULTS entry -- a third category, distinct from both,
    that this cross-file check must not force into either bucket."""
    own_choice_names = [
        name
        for name in _DEFAULT_CONSTANT_NAMES
        if _classify(_types_docstring_for(name))[0] == "fitdocs_own"
    ]
    assert set(own_choice_names) == {
        "DEFAULT_CADENCE_LOCK_WINDOW_S",
        "DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE",
    }
    for name in own_choice_names:
        assert _setting_name_for(name) not in PROVISIONAL_DEFAULTS


def test_every_default_constant_classifies_to_exactly_one_of_the_three_buckets() -> (
    None
):
    """Totality check over all seven DEFAULT_* constants: each is measured,
    published, provisional or fitdocs_own (exactly one, enforced by
    ``_classify`` itself), and the provisional-or-cited buckets never
    overlap with each other."""
    cited_settings: set[str] = set()
    provisional_settings: set[str] = set()
    for name in _DEFAULT_CONSTANT_NAMES:
        kind, publisher = _classify(_types_docstring_for(name))
        setting = _setting_name_for(name)
        if kind == "provisional":
            provisional_settings.add(setting)
        elif kind in ("measured", "published"):
            cited_settings.add(setting)
        else:
            assert kind == "fitdocs_own"
    assert cited_settings & provisional_settings == set()
    assert provisional_settings == set(PROVISIONAL_DEFAULTS)


# ---------------------------------------------------------------------------
# 4.3 -- citation records this feature adds
# ---------------------------------------------------------------------------


def test_citations_are_the_four_documented_records() -> None:
    assert CITATIONS == (
        TRAININGPEAKS_DECOUPLING,
        INTERVALS_ICU_DECOUPLING,
        PPG_CADENCE_ARTIFACT,
        FITDOCS_CORPUS_2026_07_25,
    )
    assert len(CITATIONS) == 4


def test_every_citation_is_the_shared_channels_type() -> None:
    for citation in CITATIONS:
        assert isinstance(citation, Citation)
        assert isinstance(citation.verification, VerificationStatus)


def test_citation_keys_are_unique_across_this_module_and_channels_sources() -> None:
    """Uniqueness spans both provenance modules -- a citation key collision
    between this feature and load-channels would be silently ambiguous."""
    this_module_keys = [c.key for c in CITATIONS]
    assert len(this_module_keys) == len(set(this_module_keys))

    channel_keys = [c.key for c in channel_sources.CITATIONS]
    assert len(channel_keys) == len(set(channel_keys))

    combined = this_module_keys + channel_keys
    assert len(combined) == len(set(combined)), "citation key collides across modules"


def test_fitdocs_corpus_citation_names_its_measurement_in_its_note() -> None:
    """Req: every FITDOCS_MEASURED citation carries its measurement in its
    note -- there is exactly one such citation in this module."""
    assert FITDOCS_CORPUS_2026_07_25.verification == VerificationStatus.FITDOCS_MEASURED
    assert FITDOCS_CORPUS_2026_07_25.note is not None
    # The specific figures qa/types.py's measured defaults are pinned
    # against, so a future edit that silently drops the actual measurement
    # from the note (while keeping some other prose) still reds this test.
    for figure in ("0.605", "137", "9-90 bpm"):
        assert figure in FITDOCS_CORPUS_2026_07_25.note


def test_trainingpeaks_decoupling_citation_carries_the_5_percent_quote() -> None:
    assert TRAININGPEAKS_DECOUPLING.note is not None
    assert "less than 5%" in TRAININGPEAKS_DECOUPLING.note


def test_ppg_cadence_artifact_corroborates_the_phenomenon_only() -> None:
    """PPG_CADENCE_ARTIFACT is corroboration, not the source of any fitdocs
    constant -- no DEFAULT_* docstring in qa/types.py should classify as
    'measured' while citing this key (the only measured citation is the
    corpus measurement)."""
    assert PPG_CADENCE_ARTIFACT.note is not None
    assert "no fitdocs constant" in PPG_CADENCE_ARTIFACT.note
    assert PPG_CADENCE_ARTIFACT.verification != VerificationStatus.FITDOCS_MEASURED


# ---------------------------------------------------------------------------
# 4.3, 8.3 -- the six recorded divergences
# ---------------------------------------------------------------------------


def test_divergences_are_exactly_six() -> None:
    assert len(DIVERGENCES) == 6


def test_divergence_behaviors_are_unique() -> None:
    behaviors = [d.behavior for d in DIVERGENCES]
    assert len(behaviors) == len(set(behaviors))


def test_divergences_are_the_shared_channels_type_with_no_key_field() -> None:
    for divergence in DIVERGENCES:
        assert isinstance(divergence, Divergence)
        assert not hasattr(divergence, "key")
        assert divergence.reason  # non-empty stated reason for every entry


def test_divergences_cover_the_documented_six_behaviors() -> None:
    assert {d.behavior for d in DIVERGENCES} == {
        "decoupling_half_split",
        "decoupling_numerator_run",
        "decoupling_numerator_bike",
        "seiler_decoupling_variant",
        "decoupling_presentation",
        "coverage_basis",
    }


def test_coverage_basis_divergence_records_time_vs_sample_distinction() -> None:
    """8.3: the two coverage bases (load layer measures time, the document's
    coverage table counts samples) must both be named."""
    entry = next(d for d in DIVERGENCES if d.behavior == "coverage_basis")
    assert "time" in entry.fitdocs.lower()
    assert "sample" in entry.fitdocs.lower()


# ---------------------------------------------------------------------------
# 6.10, 6.11 -- the provisional-defaults record
# ---------------------------------------------------------------------------


def test_provisional_default_is_a_frozen_dataclass_with_the_four_fields() -> None:
    entry = PROVISIONAL_DEFAULTS["divergence_max_intensity_delta"]
    assert isinstance(entry, ProvisionalDefault)
    with pytest.raises(Exception):  # noqa: B017 -- frozen dataclass, exact type not load-bearing
        entry.reasoning = "mutated"  # type: ignore[misc]


def test_provisional_defaults_has_exactly_one_entry() -> None:
    """6.11: the divergence tolerance is the only provisional default today
    -- a second entry appearing here without a matching qa/types.py PROVISIONAL
    docstring would be an inconsistency this test catches."""
    assert list(PROVISIONAL_DEFAULTS) == ["divergence_max_intensity_delta"]


def test_provisional_default_reasoning_and_would_settle_it_are_non_empty() -> None:
    entry = PROVISIONAL_DEFAULTS["divergence_max_intensity_delta"]
    assert entry.reasoning.strip() != ""
    assert entry.would_settle_it.strip() != ""
    assert entry.setting == "divergence_max_intensity_delta"
    assert entry.value == "0.20"


def test_provisional_default_records_corrected_scale_and_no_distribution() -> None:
    """6.11: the entry must state (a) the value was originally chosen
    against a heart-rate intensity scale since corrected, and (b) the
    measured corpus computed no activity with two channels, so there is no
    agreement distribution to set a tolerance against.

    Both are checked as real substring assertions, not left as unbacked
    prose about what the record "proves" -- the Fixture Discrimination Gate
    from tasks.md's Implementation Notes (1.1 -> 1.2 trap 2) applies here:
    free prose inside a docstring's body is not policed beyond an explicit
    token search, so this test asserts only what it actually searches for,
    not a broader claim ("this proves the tolerance is never described as
    measured") that no assertion here backs."""
    entry = PROVISIONAL_DEFAULTS["divergence_max_intensity_delta"]
    assert "heart-rate intensity scale" in entry.reasoning
    assert "corrected" in entry.reasoning
    assert (
        "no activity" in entry.would_settle_it
        or "no agreement" in entry.would_settle_it
    )
    assert "74-file corpus" in entry.would_settle_it


def test_provisional_default_does_not_claim_measured_phrasing() -> None:
    """Narrow, honest check matching what task 1.1's own test already
    established for qa/types.py's docstring: the literal 'Measured:' token
    must not appear in this entry's reasoning or would_settle_it. This does
    NOT prove no measurement claim is smuggled in through different
    phrasing -- that limit is real and is recorded in tasks.md's
    Implementation Notes, not papered over by a broader assertion here."""
    entry = PROVISIONAL_DEFAULTS["divergence_max_intensity_delta"]
    assert "Measured:" not in entry.reasoning
    assert "Measured:" not in entry.would_settle_it


# ---------------------------------------------------------------------------
# 3.10, 4.5 -- the two withdrawn brief claims, and the unverified attribution
# ---------------------------------------------------------------------------


def test_module_docstring_states_the_anecdote_was_not_located_and_is_unused() -> None:
    """3.10: the module must record that the "19 versus 241" cross-channel
    scoring anecdote could not be located in any published source, is cited
    nowhere in this feature, and justifies no default."""
    doc = sources.__doc__
    assert doc is not None
    assert "19 versus 241" in doc
    assert "could not be located" in doc
    assert "cited nowhere" in doc
    assert "no default, verdict or threshold" in doc


def test_module_docstring_withdraws_efficiency_factor_as_a_standalone_signal() -> None:
    """4.5: the module must record that EF's framing as a signal in its own
    right is withdrawn, name why (no absolute reference point, units differ
    by sport), and state EF enters only as a decoupling constituent and a
    basis, never a verdict."""
    doc = sources.__doc__
    assert doc is not None
    assert "withdrawn" in doc
    assert "no absolute reference point" in doc
    assert "units differ by" in doc
    assert "sport" in doc
    assert "never" in doc and "verdict" in doc


def test_module_docstring_does_not_verify_or_claim_the_friel_attribution() -> None:
    doc = sources.__doc__
    assert doc is not None
    assert "Friel" in doc
    assert "not verified" in doc
    assert "not claimed" in doc


def test_no_default_or_divergence_references_the_unlocatable_anecdote() -> None:
    """Belt-and-braces: the anecdote's own numbers must not leak into any
    citation, divergence or provisional-default text as if they justified
    something."""
    haystacks = []
    for citation in CITATIONS:
        haystacks.append(citation.work)
        haystacks.append(citation.note or "")
    for divergence in DIVERGENCES:
        haystacks.append(divergence.reason)
        haystacks.append(divergence.fitdocs)
        haystacks.append(divergence.intervals_icu)
    for entry in PROVISIONAL_DEFAULTS.values():
        haystacks.append(entry.reasoning)
        haystacks.append(entry.would_settle_it)
    assert not any("19 versus 241" in text for text in haystacks)


# ---------------------------------------------------------------------------
# Task-boundary guards
# ---------------------------------------------------------------------------


def test_module_imports_channels_sources_rather_than_redefining_the_vocabulary() -> (
    None
):
    """Build-vs-adopt: Citation, Divergence and VerificationStatus must be
    the exact same objects channels/sources.py defines, not lookalikes."""
    assert sources.Citation is channel_sources.Citation
    assert sources.Divergence is channel_sources.Divergence
    assert sources.VerificationStatus is channel_sources.VerificationStatus


def test_module_does_not_import_any_check_module_or_flags() -> None:
    module_source = inspect.getsource(sources)
    for forbidden in (
        "qa.cadence",
        "qa.divergence",
        "qa.drift",
        "qa.staleness",
        "qa.flags",
    ):
        assert forbidden not in module_source
