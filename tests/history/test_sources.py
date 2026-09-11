"""Tests for the model's citation records, seed constants, choices and the
blocked preset (load-history spec, task 2.1; Req 2.4, 2.5, 2.6, 2.8, 2.10,
3.4). See the "ModelSources (`src/fitdocs/history/sources.py`)" component in
`.kiro/specs/load-history/design.md`.

This module walks the registry (`CONSTANT_SOURCES`, `DEPARTURES`,
`BLOCKED_PRESETS`) and pins the two new bibliographic records' field-by-field
equality against `fitdocs.metrics.sources`'. The independent numeric-literal
scan and the `docs/reference` string scan live in
`tests/history/test_constant_guard.py`, a separate module by design (a
registry walk can only ever see what somebody already registered; the
literal scan can see a value that was never registered at all).
"""

from __future__ import annotations

import dataclasses

import fitdocs.history.sources as sources
import fitdocs.metrics.sources as metrics_sources
from fitdocs.citation import Agreement, Citation, FitdocsChoice


def test_constant_sources_has_no_duplicate_names() -> None:
    """Req 2.4: every `CitedConstant` in `CONSTANT_SOURCES` has a unique
    `name`. A duplicate name would let one registry entry silently shadow
    another's provenance when looked up by name."""
    names = [c.name for c in sources.CONSTANT_SOURCES]
    assert names, "the walk found no constants to check"
    assert len(names) == len(set(names)), names


def test_constant_sources_contains_exactly_the_five_declared_constants() -> None:
    """Every `CitedConstant` this module declares appears in `CONSTANT_SOURCES`
    exactly once -- five in all (two time constants, two weightings, the
    coverage threshold). Checked by identity, not just by count, so a
    constant declared but never registered (or registered twice) is caught."""
    expected = {
        id(sources.TAU_FITNESS_SEED_DAYS),
        id(sources.TAU_FATIGUE_SEED_DAYS),
        id(sources.K_FITNESS_SEED),
        id(sources.K_FATIGUE_SEED),
        id(sources.COVERAGE_THRESHOLD),
    }
    found = [id(c) for c in sources.CONSTANT_SOURCES]
    assert len(found) == len(set(found)), "a constant is registered twice"
    assert set(found) == expected, (found, expected)


def test_every_non_agreeing_corroboration_carries_a_note() -> None:
    """A `Corroboration` whose `agreement` is not `AGREES` must carry a
    `note` in words -- the registry-walk invariant design.md states. Both
    time-constant seeds carry a `DIFFERS` corroboration on M90's fitted
    table; neither may have a `None` note."""
    checked = 0
    for constant in sources.CONSTANT_SOURCES:
        for corroboration in constant.corroborators:
            checked += 1
            if corroboration.agreement is not Agreement.AGREES:
                assert corroboration.note is not None, (
                    constant.name,
                    corroboration.citation.key,
                )
    assert checked, "the walk found no corroborations to check"


def test_time_constant_seeds_are_corroborated_as_differing_from_the_fitted_table() -> (
    None
):
    """Req 2.5: each of the two time-constant seeds carries a
    `Corroboration` on M90's fitted table with `agreement=DIFFERS` -- the
    record itself must state that the shipped seed is not what fitting
    produced, not merely have a note *if* such a corroboration happens to be
    present. Named mutation: remove `TAU_FITNESS_SEED_DAYS`'s
    `corroborators` tuple entirely in the module under test -- this
    assertion reds; `test_every_non_agreeing_corroboration_carries_a_note`
    does not (it only checks corroborations that exist), which is exactly
    why this assertion exists as a separate check for presence, not only
    for well-formedness."""
    for constant in (sources.TAU_FITNESS_SEED_DAYS, sources.TAU_FATIGUE_SEED_DAYS):
        assert any(c.agreement is Agreement.DIFFERS for c in constant.corroborators), (
            constant.name
        )


def test_every_departure_subject_is_unique() -> None:
    """Req 16.5: no two `Departure` records in `DEPARTURES` share a
    `subject`."""
    subjects = [d.subject for d in sources.DEPARTURES]
    assert subjects, "the walk found no departures to check"
    assert len(subjects) == len(set(subjects)), subjects


def test_seed_constants_time_constants_read_the_cited_constants_values() -> None:
    """`SEED_CONSTANTS`'s four fields equal the four `CitedConstant` objects'
    own `.value` -- the registry-walk half of "never spells a number"; the
    other half (that this is a genuine attribute read, not a literal that
    happens to match) is `test_constant_guard.py`'s job. Named mutation:
    hardcode `SEED_CONSTANTS.tau_fitness_days` to a value that disagrees with
    `TAU_FITNESS_SEED_DAYS.value` (e.g. 44.0) -- this assertion reds (the
    literal scan also reds on the new literal)."""
    assert (
        sources.SEED_CONSTANTS.tau_fitness_days == sources.TAU_FITNESS_SEED_DAYS.value
    )
    assert (
        sources.SEED_CONSTANTS.tau_fatigue_days == sources.TAU_FATIGUE_SEED_DAYS.value
    )
    assert sources.SEED_CONSTANTS.k_fitness == sources.K_FITNESS_SEED.value
    assert sources.SEED_CONSTANTS.k_fatigue == sources.K_FATIGUE_SEED.value


def test_seed_constants_provenance_is_seeds() -> None:
    """The seed instance's own provenance is `ConstantProvenance.SEEDS`, not
    `CONFIGURED` or `FITTED` -- what a page's constants paragraph reads to
    decide whether to print the "never fitted to any athlete" language
    (Req 2.5)."""
    assert sources.SEED_CONSTANTS.provenance is sources.ConstantProvenance.SEEDS


def test_no_shipped_constant_carries_42_or_7_as_a_time_constant() -> None:
    """Req 2.8: the blocked Performance Management Chart pair (42 d / 7 d)
    must never appear as a shipped, cited value. Checked against every
    registered constant's own value -- not only the two named time
    constants -- so a 42 or 7 landing on any registered constant is caught,
    not only one placed under the expected name. Named mutation: change
    `TAU_FITNESS_SEED_DAYS.value` to `42.0` in the module under test -- this
    assertion reds."""
    values = [c.value for c in sources.CONSTANT_SOURCES]
    assert values, "the walk found no constants to check"
    assert 42.0 not in values, values
    assert 7.0 not in values, values


def test_blocked_presets_names_the_performance_management_chart_pair() -> None:
    """Req 2.8: `BLOCKED_PRESETS` declares the 42/7 pair as blocked, not
    shipped -- a declared absence, not an omission. Checked against the
    record's own text, not only its presence: both figures the preset
    withholds must actually appear in `values`, and `blocked_by` must be
    non-empty prose, not a placeholder."""
    assert len(sources.BLOCKED_PRESETS) == 1
    preset = sources.BLOCKED_PRESETS[0]
    assert "42" in preset.values
    assert "7" in preset.values
    assert preset.blocked_by.strip(), "blocked_by is empty"


def _citation_fields_excluding(
    citation: Citation, excluded: set[str]
) -> dict[str, object]:
    return {
        f.name: getattr(citation, f.name)
        for f in dataclasses.fields(citation)
        if f.name not in excluded
    }


def test_morton_1990_recursion_matches_metrics_morton_1990_field_for_field() -> None:
    """Req 2.4: `MORTON_1990_RECURSION`'s `authors`, `year`, `work` and
    `verification` fields are identical to `fitdocs.metrics.sources.
    MORTON_1990`'s, excluding `key`, `locator` and `note` -- the two records
    name the same published work at different locators, so the bibliography
    (everything but where in the work, and what this record says about that
    place) can never drift into two versions of one paper. Named mutation:
    change `MORTON_1990_RECURSION.work`'s string by one character in the
    module under test -- this assertion reds."""
    excluded = {"key", "locator", "note"}
    got = _citation_fields_excluding(sources.MORTON_1990_RECURSION, excluded)
    want = _citation_fields_excluding(metrics_sources.MORTON_1990, excluded)
    assert got == want


def test_banister_1991_time_constants_matches_metrics_field_for_field() -> None:
    """Req 2.4: `BANISTER_1991_TIME_CONSTANTS`'s `authors`, `year`, `work`
    and `verification` fields are identical to `fitdocs.metrics.sources.
    BANISTER_1991`'s, excluding `key`, `locator` and `note`. Named mutation:
    change `BANISTER_1991_TIME_CONSTANTS.year` in the module under test --
    this assertion reds."""
    excluded = {"key", "locator", "note"}
    got = _citation_fields_excluding(sources.BANISTER_1991_TIME_CONSTANTS, excluded)
    want = _citation_fields_excluding(metrics_sources.BANISTER_1991, excluded)
    assert got == want


def test_the_two_new_citations_have_their_own_locators_distinct_from_metrics() -> None:
    """The falsifying half of the equality tests above: the two new records
    must NOT be byte-identical to the metrics-layer records overall -- their
    locators are deliberately different (the recursion's own equations/pages,
    not the training-impulse weighting's). This guards against a
    reviewer-plausible wrong implementation that re-exports the metrics
    records verbatim instead of declaring new ones at new locators, which
    would pass the field-equality tests above trivially (identity implies
    field equality) but would violate Req 2.4's requirement for the
    recursion's own locator."""
    assert sources.MORTON_1990_RECURSION.locator != metrics_sources.MORTON_1990.locator
    assert (
        sources.BANISTER_1991_TIME_CONSTANTS.locator
        != metrics_sources.BANISTER_1991.locator
    )
    assert sources.MORTON_1990_RECURSION.key != metrics_sources.MORTON_1990.key
    assert sources.BANISTER_1991_TIME_CONSTANTS.key != metrics_sources.BANISTER_1991.key


def test_the_four_fitdocs_choices_carry_non_empty_justification_and_search_basis() -> (
    None
):
    """Req 2.6, 2.8, 3.4: `RECURSION_FORM_CHOICE`, `DAILY_AVERAGE_SCALE_CHOICE`,
    `WEIGHTING_CHOICE` and `COVERAGE_THRESHOLD_CHOICE` are the module's own
    declared `FitdocsChoice` records -- none is a citation, so `verification`
    is pinned `FITDOCS_MEASURED` by the type itself (`fitdocs.citation`), but
    nothing else checks that these four names exist and actually carry
    prose. Checked against non-trivial content, not mere presence: a choice
    with an empty `justification` is exactly as undocumented as a missing
    one. Named mutation: set `RECURSION_FORM_CHOICE.justification` to `""`
    in the module under test -- this assertion reds."""
    from fitdocs.citation import FitdocsChoice, VerificationStatus

    choices = (
        sources.RECURSION_FORM_CHOICE,
        sources.DAILY_AVERAGE_SCALE_CHOICE,
        sources.WEIGHTING_CHOICE,
        sources.COVERAGE_THRESHOLD_CHOICE,
    )
    for choice in choices:
        assert isinstance(choice, FitdocsChoice), choice
        assert choice.verification is VerificationStatus.FITDOCS_MEASURED
        assert choice.justification.strip(), choice.key
        assert choice.search_basis.strip(), choice.key


def test_recursion_form_and_coverage_threshold_choices_carry_a_measurement() -> None:
    """Req 3.4: the coverage threshold "shipped default is recorded as a
    measured choice with the measurement stated" -- `measurement` must be
    non-``None`` and non-empty prose, not merely present. `RECURSION_FORM_
    CHOICE` carries the same kind of measured figure on the same footing
    (design.md). Named mutation: set `COVERAGE_THRESHOLD_CHOICE.measurement`
    to `None` in the module under test -- this assertion reds."""
    for choice in (sources.RECURSION_FORM_CHOICE, sources.COVERAGE_THRESHOLD_CHOICE):
        assert choice.measurement is not None, choice.key
        assert choice.measurement.strip(), choice.key


def test_weighting_and_daily_average_scale_choices_carry_no_measurement() -> None:
    """`WEIGHTING_CHOICE` and `DAILY_AVERAGE_SCALE_CHOICE` rest on no
    measurement fitdocs itself took -- `measurement` is `None` on both,
    distinguishing them from the two choices above. Named mutation: set
    `WEIGHTING_CHOICE.measurement` to a non-`None` string in the module
    under test -- this assertion reds."""
    assert sources.WEIGHTING_CHOICE.measurement is None
    assert sources.DAILY_AVERAGE_SCALE_CHOICE.measurement is None


def test_constant_provenance_declares_seeds_configured_and_fitted() -> None:
    """Req 2.10: `ConstantProvenance` declares all three members this spec
    and its downstream, gated `performance-model-fit` spec need -- `SEEDS`
    (this task), `CONFIGURED` (Req 2.7, a later task) and `FITTED` (declared
    here so the downstream spec adds no new enum member). Checked against
    the exact member set, not merely that `SEEDS` exists, so a missing
    `CONFIGURED` or `FITTED` is caught too. Named mutation: remove the
    `FITTED` member from `ConstantProvenance` in the module under test --
    this assertion reds."""
    assert {member.value for member in sources.ConstantProvenance} == {
        "seeds",
        "configured",
        "fitted",
    }


def test_model_constants_accepts_a_caller_supplied_configured_set() -> None:
    """Req 2.10: `ModelConstants` is the seam a caller-supplied constant set
    plugs into -- constructible with the athlete's own values and a
    `CONFIGURED` provenance, independent of `SEED_CONSTANTS`. Checked with
    values that actually differ from every seed field, so a construction
    that silently ignored the caller's arguments and echoed the seeds back
    could not pass this by accident. Named mutation: hardcode
    `ModelConstants.tau_fitness_days` to always equal `SEED_CONSTANTS.
    tau_fitness_days` (i.e. remove the field from `__init__`) in the module
    under test -- this assertion reds."""
    configured = sources.ModelConstants(
        tau_fitness_days=30.0,
        tau_fatigue_days=8.0,
        k_fitness=2.0,
        k_fatigue=3.0,
        provenance=sources.ConstantProvenance.CONFIGURED,
        origin="the athlete's own configured constants",
    )
    assert (
        configured.tau_fitness_days == 30.0 != sources.SEED_CONSTANTS.tau_fitness_days
    )
    assert configured.tau_fatigue_days == 8.0 != sources.SEED_CONSTANTS.tau_fatigue_days
    assert configured.k_fitness == 2.0 != sources.SEED_CONSTANTS.k_fitness
    assert configured.k_fatigue == 3.0 != sources.SEED_CONSTANTS.k_fatigue
    assert configured.provenance is sources.ConstantProvenance.CONFIGURED
    assert configured.origin == "the athlete's own configured constants"


def test_seed_time_constants_have_the_expected_shipped_values() -> None:
    """The task's own observable: importing the seed constant set yields the
    two time constants 45.0 and 15.0. Checked directly against the
    `CitedConstant` values, not only the derived `SEED_CONSTANTS` (a separate
    test above already ties those together)."""
    assert sources.TAU_FITNESS_SEED_DAYS.value == 45.0
    assert sources.TAU_FATIGUE_SEED_DAYS.value == 15.0


def test_each_constant_is_bound_to_its_governing_source_by_identity() -> None:
    """Req 2.4, 2.6: exactly one governing source per constant, checked by
    identity (`is`) rather than equality -- two records could coincidally
    compare equal, but identity is what actually proves the registry points
    at *the* shared module-level record rather than a freshly constructed
    look-alike. The two time constants are governed by the `Citation`;
    the two weightings and the coverage threshold are governed by a
    `FitdocsChoice`, never a `Citation` -- checked by `isinstance` in
    addition to identity, as a second, type-level statement of the same
    invariant the `is` checks above already pin. Named mutation:
    `K_FITNESS_SEED.source=BANISTER_1991_TIME_CONSTANTS` in the module under
    test -- this assertion reds (M8). Named mutation:
    `TAU_FITNESS_SEED_DAYS.source=MORTON_1990_RECURSION` -- this assertion
    reds (M9)."""
    assert sources.TAU_FITNESS_SEED_DAYS.source is sources.BANISTER_1991_TIME_CONSTANTS
    assert sources.TAU_FATIGUE_SEED_DAYS.source is sources.BANISTER_1991_TIME_CONSTANTS
    assert sources.K_FITNESS_SEED.source is sources.WEIGHTING_CHOICE
    assert sources.K_FATIGUE_SEED.source is sources.WEIGHTING_CHOICE
    assert sources.COVERAGE_THRESHOLD.source is sources.COVERAGE_THRESHOLD_CHOICE

    for citation_governed in (
        sources.TAU_FITNESS_SEED_DAYS,
        sources.TAU_FATIGUE_SEED_DAYS,
    ):
        assert isinstance(citation_governed.source, Citation), citation_governed.name

    for choice_governed in (
        sources.K_FITNESS_SEED,
        sources.K_FATIGUE_SEED,
        sources.COVERAGE_THRESHOLD,
    ):
        assert isinstance(choice_governed.source, FitdocsChoice), choice_governed.name


def test_weighting_seeds_departure_is_registered_and_matches_by_identity() -> None:
    """Req 16.5: both weighting seeds' `departure` field is set (not `None`)
    and the exact object registered in `DEPARTURES`, checked by identity.
    Also confirms every registered constant's non-`None` departure is one
    that `DEPARTURES` actually holds -- a constant carrying a `Departure`
    object that was never added to the registry would otherwise go
    unnoticed. Named mutation: `K_FATIGUE_SEED.departure=None` in the module
    under test -- this assertion reds (M7). Named mutation: swap
    `DEPARTURES` to hold an unrelated `Departure` instead of
    `TRIMP_WEIGHTING_SEEDS_DEPARTURE` -- this assertion reds (M13)."""
    assert sources.K_FITNESS_SEED.departure is not None
    assert sources.K_FATIGUE_SEED.departure is not None
    assert sources.K_FITNESS_SEED.departure is sources.TRIMP_WEIGHTING_SEEDS_DEPARTURE
    assert sources.K_FATIGUE_SEED.departure is sources.TRIMP_WEIGHTING_SEEDS_DEPARTURE

    departure_ids = {id(d) for d in sources.DEPARTURES}
    for constant in sources.CONSTANT_SOURCES:
        if constant.departure is not None:
            assert id(constant.departure) in departure_ids, constant.name


def test_weighting_seed_and_coverage_threshold_values_are_pinned() -> None:
    """Value pin on the three non-time-constant `CitedConstant`s -- the
    time constants are already pinned by
    `test_seed_time_constants_have_the_expected_shipped_values`. Named
    mutation: `K_FATIGUE_SEED.value=2.0` in the module under test -- this
    assertion reds (M12)."""
    assert sources.K_FITNESS_SEED.value == 1.0
    assert sources.K_FATIGUE_SEED.value == 1.0
    assert sources.COVERAGE_THRESHOLD.value == 0.80


def test_the_two_new_citations_have_the_pinned_locators() -> None:
    """Locator content pin, distinct from the "has its own locator, distinct
    from metrics" inequality check above -- this pins the exact string, not
    merely that it differs. Named mutation: swap the two locators (assign
    `MORTON_1990_RECURSION.locator = "pp. 413-414"` and
    `BANISTER_1991_TIME_CONSTANTS.locator = "Eq. 4-5, p. 1173"`) in the
    module under test -- this assertion reds (M5)."""
    assert sources.MORTON_1990_RECURSION.locator == "Eq. 4-5, p. 1173"
    assert sources.BANISTER_1991_TIME_CONSTANTS.locator == "pp. 413-414"


def test_tau_corroborations_cite_morton_table_2() -> None:
    """Both time-constant seeds' `DIFFERS` corroboration is opened at M90's
    own `Table 2`, the fitted-values table -- pinned by exact string, not
    merely non-empty. Checked against the seed's own `DIFFERS` corroboration
    specifically, not merely against whichever corroboration happens to cite
    `MORTON_1990_RECURSION`: exactly one `DIFFERS` corroboration must exist
    per seed, and that one must cite `MORTON_1990_RECURSION` at `Table 2`.
    Named mutation: set either seed's `DIFFERS` corroboration's `citation`
    to `BANISTER_1991_TIME_CONSTANTS` (self-corroboration on its own
    governing source) in the module under test -- this assertion reds for
    that seed."""
    for constant in (sources.TAU_FITNESS_SEED_DAYS, sources.TAU_FATIGUE_SEED_DAYS):
        differing = [
            c for c in constant.corroborators if c.agreement is Agreement.DIFFERS
        ]
        assert len(differing) == 1, (constant.name, differing)
        corroboration = differing[0]
        assert corroboration.citation is sources.MORTON_1990_RECURSION, constant.name
        assert corroboration.locator == "Table 2", constant.name


def test_tau_corroboration_notes_state_the_unfitted_illustrative_ruling() -> None:
    """Req 2.5: each time-constant seed's `DIFFERS` corroboration `note`
    states, in words, both that the shipped value was never fitted to any
    athlete and that it is an illustrative starting value -- not merely
    that a note exists (`test_every_non_agreeing_corroboration_carries_a_note`
    already checks presence). Named mutation: delete the "never fitted to
    any athlete" clause from `TAU_FITNESS_SEED_DAYS`'s corroboration note in
    the module under test -- this assertion reds."""
    for constant in (sources.TAU_FITNESS_SEED_DAYS, sources.TAU_FATIGUE_SEED_DAYS):
        differing = [
            c for c in constant.corroborators if c.agreement is Agreement.DIFFERS
        ]
        assert differing, constant.name
        for corroboration in differing:
            note = corroboration.note
            assert note is not None, constant.name
            assert "never fitted to any athlete" in note, constant.name
            assert "illustrative starting value" in note, constant.name


def test_seed_constants_origin_is_non_empty() -> None:
    """`SEED_CONSTANTS.origin` is the one line printed verbatim on a page
    (Req 2.7, 2.10) -- must be non-empty prose. Named mutation:
    `SEED_CONSTANTS.origin=""` in the module under test -- this assertion
    reds (M6)."""
    assert sources.SEED_CONSTANTS.origin.strip()
