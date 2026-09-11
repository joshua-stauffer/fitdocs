"""Measure and pin every numeric figure `sources.py`'s provenance records
state (load-history spec, task 2.3; Req 3.4). See the "ModelSources
(`src/fitdocs/history/sources.py`)" component in
`.kiro/specs/load-history/design.md`, "Implementation Notes" -- "Who
measures what."

No stated number in `sources.py` ships unreproduced. This module reproduces
every one, using only the shipped model (`fitdocs.history.model.run_model`
and, for the per-step reciprocal-vs-exact divergence,
`fitdocs.history.model._decay`) and the shipped seed constants
(`fitdocs.history.sources.SEED_CONSTANTS`) -- it never reimplements the
day-over-day recursion or its per-step decay formula itself.

Two records carry a ``measurement`` field:

- ``COVERAGE_THRESHOLD_CHOICE`` states the relative understatement of
  daily-average fitness (2.198%) and of daily-average fatigue (6.449%) that
  exactly one uncomputed daily page causes at the seed time constants
  (tau1 = 45 d, tau2 = 15 d). Reproduced below by running the shipped model
  twice -- once over a long constant-load, fully-recorded archive, once over
  the same archive with its last day's page uncomputed (load 0.0 instead of
  the steady load) -- and comparing the last reported value both ways.
- ``RECURSION_FORM_CHOICE`` states the per-step divergence of the reciprocal
  weight ``1/tau`` against the exact ``1 - e^(-1/tau)`` at tau = 45 d
  (1.12%), tau = 42 d (1.20%, the blocked Performance Management Chart
  candidate) and, per this task's controller decision reconciling a tension
  between task 2.1/2.3's tasks.md text (which reads the divergence pair as
  stated "at both the fitness and the fatigue seed", i.e. tau = 45/15) and
  design.md's transcribed pair (tau = 45/42), tau = 15 d (3.37%, the fatigue
  seed) -- added to the sources-module string by this task under its
  measurement-string licence rather than silently dropped. The same three
  figures are restated a second time, in words, in
  `RECURSION_FORM_CHOICE.justification` ("1.12% at tau = 45 d, 1.20% at
  tau = 42 d"); the justification tests below read that copy independently
  of the measurement-field tests, so the two fields cannot silently drift
  apart.

`COVERAGE_THRESHOLD_CHOICE.justification` also states the shipped threshold
itself twice inline (as a fraction and as a percent, "0.80 (80% of a
period's...)"); a dedicated test below reads both numbers out of that
sentence and checks each against `COVERAGE_THRESHOLD.value` directly, so a
one-sided edit to either writing -- or to the underlying constant -- is
caught.

Two numeric mentions elsewhere in `sources.py` are citations to the primary
literature, not measurements this module can reproduce from the shipped
code, and are accounted for here by that description rather than by an
assertion: M90 Table 2's least-squares fit (tau1 = 50 d / 40 d, tau2 = 11 d
for both subjects, in the two `Corroboration` notes on
`TAU_FITNESS_SEED_DAYS` / `TAU_FATIGUE_SEED_DAYS`) and B91's own definition
of a time constant as the time for a decaying variable to fall to 37% of its
level (in `BANISTER_1991_TIME_CONSTANTS.note`) -- both are what the cited
works themselves say, not a property of fitdocs' shipped recursion.
`BLOCKED_PRESETS`' tau1 = 42 d / tau2 = 7 d pair is a structural preset
description (not a `%` or a measurement figure) already covered by
`test_sources.py`'s blocked-constant assertion.
"""

from __future__ import annotations

import math
import re

from fitdocs.history import model, sources
from fitdocs.history.model import ModelSeries, run_model

# A long, constant-load, fully-recorded archive: long enough that both seed
# time constants (tau = 45 d, tau = 15 d) have converged to their
# steady-state daily-average value. 400 days left the fitness (tau = 45 d)
# figure only ~0.0005 percentage points from the 2.1985 boundary at which
# the three-decimal rounding this module checks against would flip from
# 2.198 to 2.199; 2000 days converges the measured figure to the
# steady-state value (2.197712... percent, verified by hand against the
# closed-form (1 - e^(-1/tau)) asymptote) with room to spare.
_STEADY_STATE_DAYS = 2000
_STEADY_STATE_LOAD = 100.0


def _run_steady_state(*, gap_last_day: bool) -> ModelSeries:
    daily_loads = [_STEADY_STATE_LOAD] * _STEADY_STATE_DAYS
    if gap_last_day:
        daily_loads[-1] = 0.0
    return run_model(daily_loads, sources.SEED_CONSTANTS)


def _understatement_percent(which: str) -> float:
    """The relative understatement, in percent, that leaving the archive's
    last daily page uncomputed causes in that last day's reported
    daily-average ``which`` value (``"fitness"`` or ``"fatigue"``), relative
    to the same archive fully recorded -- both runs go through the shipped
    ``run_model``, never a reimplementation of its recursion."""
    full = getattr(_run_steady_state(gap_last_day=False), which)[-1]
    gapped = getattr(_run_steady_state(gap_last_day=True), which)[-1]
    assert full > 0.0, "the steady-state run produced no reported value to compare"
    assert full != gapped, "the gapped run must differ from the full run"
    return (full - gapped) / full * 100.0


def _reciprocal_divergence_percent(tau_days: float) -> float:
    """The per-step divergence, in percent, of the reciprocal weight
    ``1/tau`` over the exact ``1 - e^(-1/tau)`` -- the vendor approximation
    fitdocs' `RECURSION_FORM_CHOICE` declines, against the primary text's
    own form. Computed through `fitdocs.history.model._decay` itself
    (``exact = 1.0 - model._decay(tau_days)``), not a reimplementation of
    its ``e^(-1/tau)`` formula -- the same function `run_model` calls for
    both accumulators, which `test_model.py` and `test_worked_examples.py`
    already pin against the shipped recursion's own output. Neither vendor
    documentation nor `sources.py` names this divergence pair as a function
    fitdocs ships, so there is no shipped call to route the comparison
    itself through."""
    exact = 1.0 - model._decay(tau_days)
    reciprocal = 1.0 / tau_days
    return (reciprocal - exact) / exact * 100.0


def _quoted_percent(text: str, *, before: str) -> float:
    """Extract the numeric percentage immediately preceding the literal
    substring ``before`` inside ``text`` -- reads the actual quoted figure
    out of the sources-module string itself (never a value hand-copied into
    this test file) so that editing the string's number, not only its
    prose, is what a mutation to that figure means."""
    pattern = re.escape(before)
    match = re.search(r"([0-9]+\.[0-9]+)%\s+" + pattern, text)
    assert match is not None, (
        f"could not find a percentage immediately before {before!r} in: {text!r}"
    )
    return float(match.group(1))


def _quoted_percent_and_tau(text: str, *, before: str) -> tuple[float, float]:
    """Same extraction as `_quoted_percent`, plus the ``tau = N d`` label
    that immediately trails ``before`` in the same sentence -- reads both
    the percent figure and the specific time constant the string claims it
    was measured at out of the string itself, so a test can pin the label,
    not only the number."""
    pattern = re.escape(before)
    match = re.search(
        r"([0-9]+\.[0-9]+)%\s+" + pattern + r"\s*\(tau = ([0-9.]+) d", text
    )
    assert match is not None, (
        f"could not find a percentage and tau label immediately before "
        f"{before!r} in: {text!r}"
    )
    return float(match.group(1)), float(match.group(2))


# --- COVERAGE_THRESHOLD_CHOICE.measurement -----------------------------------


def test_coverage_threshold_measurement_states_the_fitness_figure_this_reproduces() -> (
    None
):
    """The exact figure `COVERAGE_THRESHOLD_CHOICE.measurement` quotes for
    fitness (read out of the string itself) must equal the shipped model's
    own measured understatement, to the record's own precision (three
    decimal places as a percent). Named mutation: edit the sources-module
    string's fitness figure alone (e.g. 2.198% -> 3.000%) -- this assertion
    reds while the fatigue assertion below stays green, since each reads
    its own figure out of its own position in the string."""
    stated = _quoted_percent(
        sources.COVERAGE_THRESHOLD_CHOICE.measurement or "",
        before="and the reported fatigue accumulator",
    )
    measured = _understatement_percent("fitness")
    assert round(measured, 3) == stated


def test_coverage_threshold_measurement_states_the_fatigue_figure_this_reproduces() -> (
    None
):
    """Same reproduction, the fatigue figure. A distinct measurement from
    the fitness one above -- computed at the fatigue seed's own tau (15 d,
    read from `sources.SEED_CONSTANTS` through `run_model`), not the
    fitness seed's (45 d). Fixture-discrimination check performed by hand
    (not asserted here): passing `"fatigue"` to `_understatement_percent`
    in the fitness test above in place of `"fitness"` produces 6.449, which
    fails that test's comparison against the 2.198 the string states for
    fitness -- the two figures are two distinct measurements, not the same
    number read twice."""
    stated = _quoted_percent(
        sources.COVERAGE_THRESHOLD_CHOICE.measurement or "",
        before="relative to what an equal-magnitude recorded page",
    )
    measured = _understatement_percent("fatigue")
    assert round(measured, 3) == stated


def test_coverage_threshold_measurement_states_the_seed_labels_this_ran_at() -> None:
    """`COVERAGE_THRESHOLD_CHOICE.measurement` opens by naming the seed
    constants the measurement below actually ran at ("tau1 = 45 d,
    tau2 = 15 d") -- pinned here against `sources.SEED_CONSTANTS` itself, so
    a label edit that no longer matches the constants `_run_steady_state`
    reads (via `sources.SEED_CONSTANTS`) reds even though the two `%`
    figures elsewhere in the string would still be internally consistent.
    Named mutation O8: "tau1 = 45 d" -> "tau1 = 54 d" reds."""
    match = re.search(
        r"tau1 = ([0-9.]+) d, tau2 = ([0-9.]+) d",
        sources.COVERAGE_THRESHOLD_CHOICE.measurement or "",
    )
    assert match is not None, (
        "could not find the seed-constant labels in "
        f"{sources.COVERAGE_THRESHOLD_CHOICE.measurement!r}"
    )
    assert float(match.group(1)) == sources.SEED_CONSTANTS.tau_fitness_days
    assert float(match.group(2)) == sources.SEED_CONSTANTS.tau_fatigue_days


def test_coverage_threshold_justification_states_the_threshold_consistently() -> None:
    """`COVERAGE_THRESHOLD_CHOICE.justification` opens with the threshold's
    own value written twice -- once as a fraction ("0.80"), once as a
    percent ("80%") -- and both must agree with `COVERAGE_THRESHOLD.value`
    itself, not merely with each other, so the two writings and the shipped
    constant cannot drift apart one at a time. Named mutations: "0.80 (80%"
    -> "0.85 (85%" reds (both readings move together, away from the shipped
    0.80); a one-sided edit to either the fraction or the percent alone
    would also red, since each is checked against `COVERAGE_THRESHOLD.value`
    independently."""
    match = re.search(
        r"([0-9]\.[0-9]+) \(([0-9]+)% of a",
        sources.COVERAGE_THRESHOLD_CHOICE.justification,
    )
    assert match is not None, (
        "could not find the threshold's fraction/percent pair in "
        f"{sources.COVERAGE_THRESHOLD_CHOICE.justification!r}"
    )
    assert float(match.group(1)) == sources.COVERAGE_THRESHOLD.value
    assert int(match.group(2)) == round(sources.COVERAGE_THRESHOLD.value * 100)


def test_coverage_threshold_admits_at_most_one_uncomputed_page_in_five() -> None:
    """`COVERAGE_THRESHOLD_CHOICE.justification` reads the shipped 0.80
    threshold as admitting at most one uncomputed page in five (Req 3.4):
    a period below 80% coverage is suppressed, i.e. a period is drawn only
    if at most 20% -- one in five -- of its pages are uncomputed. Pinned as
    an exact tie (not merely `<=`) so the threshold's own value and this
    reading cannot silently drift apart: a shipped threshold of 0.85 would
    still satisfy `<= one in five` (0.15 <= 0.20) without reding, but no
    longer matches the sentence the record makes, so the reading is checked
    for equality with 0.20, not merely a bound."""
    missing_fraction = 1.0 - sources.COVERAGE_THRESHOLD.value
    assert missing_fraction <= 0.20 + 1e-9, (
        "the shipped threshold must admit no more than one uncomputed page in five"
    )
    assert math.isclose(missing_fraction, 0.20, rel_tol=0.0, abs_tol=1e-9), (
        "the shipped threshold (0.80) is read as admitting exactly one "
        "uncomputed page in five; if the threshold changes, this reading "
        "(and the sources-module prose) must change with it"
    )


# --- RECURSION_FORM_CHOICE.justification --------------------------------------


def test_recursion_form_justification_states_the_fitness_seed_figure() -> None:
    """`RECURSION_FORM_CHOICE.justification` restates the divergence figures
    inline ("1.12% at tau = 45 d, 1.20% at tau = 42 d") -- a second quoted
    copy distinct from `.measurement`'s own copy, checked separately so the
    two fields cannot drift apart. Named mutation O6: editing only the
    justification's fitness figure (1.12% -> 1.50%) reds this test while
    leaving the `.measurement`-reading tests above green."""
    stated = _quoted_percent(
        sources.RECURSION_FORM_CHOICE.justification,
        before="at tau = 45 d",
    )
    measured = _reciprocal_divergence_percent(sources.TAU_FITNESS_SEED_DAYS.value)
    assert round(measured, 2) == stated


def test_recursion_form_justification_states_the_blocked_candidate_figure() -> None:
    """Same reproduction as the fitness figure above, read from
    `RECURSION_FORM_CHOICE.justification`'s own "at tau = 42 d" figure
    rather than `.measurement`'s copy."""
    stated = _quoted_percent(
        sources.RECURSION_FORM_CHOICE.justification,
        before="at tau = 42 d",
    )
    measured = _reciprocal_divergence_percent(42.0)
    assert round(measured, 2) == stated


# --- RECURSION_FORM_CHOICE.measurement ---------------------------------------


def test_recursion_form_measurement_states_the_fitness_seed_figure() -> None:
    """The figure `RECURSION_FORM_CHOICE.measurement` quotes at the shipped
    fitness seed (tau = 45 d) equals the reciprocal-vs-exact per-step
    divergence measured directly, and the ``(tau = N d)`` label the string
    attaches to that figure names the seed the measurement actually ran at.
    Named mutation R8: "(tau = 45 d)" -> "(tau = 54 d)" reds the tau
    assertion below while leaving the two sibling tau assertions (blocked
    candidate, fatigue seed) green, since each reads a different anchor out
    of the same string."""
    stated, stated_tau = _quoted_percent_and_tau(
        sources.RECURSION_FORM_CHOICE.measurement or "",
        before="at the shipped fitness seed",
    )
    assert stated_tau == sources.TAU_FITNESS_SEED_DAYS.value
    measured = _reciprocal_divergence_percent(sources.TAU_FITNESS_SEED_DAYS.value)
    assert round(measured, 2) == stated


def test_recursion_form_measurement_states_the_blocked_candidate_figure() -> None:
    """The figure quoted at the blocked 42-day Performance Management Chart
    candidate (`BLOCKED_PRESETS`) equals the same divergence measured at
    tau = 42 d -- a distinct time constant from the shipped fitness seed
    (45 d) and the fatigue seed (15 d) checked below, so a swap among the
    three would be caught: each reads a different `before` anchor out of
    the same string and compares against a different tau. The string also
    attaches a ``(tau = 42 d; ...)`` label to this figure, pinned here
    against the literal 42.0 the measurement below runs at. Named mutation
    R9b: "(tau = 42 d" -> "(tau = 24 d" reds this tau assertion alone."""
    stated, stated_tau = _quoted_percent_and_tau(
        sources.RECURSION_FORM_CHOICE.measurement or "",
        before="at the blocked Performance Management Chart candidate",
    )
    assert stated_tau == 42.0
    measured = _reciprocal_divergence_percent(42.0)
    assert round(measured, 2) == stated


def test_recursion_form_measurement_states_the_fatigue_seed_figure() -> None:
    """tasks.md's own text (2.1/2.3) reads the recursion-form divergence as
    stated 'at both the fitness and the fatigue seed' (tau = 45 d, 15 d);
    design.md transcribed the pair at tau = 45 d/42 d instead. Per this
    task's controller decision, the fatigue-seed (tau = 15 d) figure is
    computed here and added to `RECURSION_FORM_CHOICE.measurement` under
    this task's measurement-string licence, alongside (not replacing) the
    45 d/42 d pair design.md transcribed -- so both readings hold. Named
    mutation R9: "(tau = 15 d)" -> "(tau = 51 d)" reds the tau assertion
    below alone."""
    stated, stated_tau = _quoted_percent_and_tau(
        sources.RECURSION_FORM_CHOICE.measurement or "",
        before="at the fatigue seed",
    )
    assert stated_tau == sources.TAU_FATIGUE_SEED_DAYS.value
    measured = _reciprocal_divergence_percent(sources.TAU_FATIGUE_SEED_DAYS.value)
    assert round(measured, 2) == stated


# --- Every remaining numeric figure in sources.py is a citation, not a ------
# --- measurement, and is accounted for here rather than reproduced.  -------


def test_the_fitted_table_values_are_citations_not_measurements() -> None:
    """M90 Table 2's fitted values (tau1 = 50 d / 40 d, tau2 = 11 d), quoted
    in the two `Corroboration` notes on `TAU_FITNESS_SEED_DAYS` and
    `TAU_FATIGUE_SEED_DAYS`, are the cited paper's own published fit -- not
    a property of the shipped recursion this module could measure. Checked
    here only for presence (accounted for, not reproduced): the note names
    both fitted values in words, and each corroboration's `agreement` is
    `DIFFERS`, matching the fact that fitdocs ships unfitted seeds."""
    fitness_note = sources.TAU_FITNESS_SEED_DAYS.corroborators[0].note
    fatigue_note = sources.TAU_FATIGUE_SEED_DAYS.corroborators[0].note
    assert "50 d" in fitness_note and "40 d" in fitness_note
    assert "11 d" in fatigue_note


def test_the_time_constant_definition_percent_is_a_citation_not_a_measurement() -> None:
    """B91's own definition of a time constant -- the time for a decaying
    variable to fall to 37% of its level -- is quoted in
    `BANISTER_1991_TIME_CONSTANTS.note`. This is the primary text's own
    definitional statement (consistent with ``e^-1`` ~ 36.8%, rounded to
    the nearest percent), not a measurement of fitdocs' shipped recursion,
    so it is accounted for by presence here rather than reproduced as a
    model measurement."""
    note = sources.BANISTER_1991_TIME_CONSTANTS.note
    assert "37%" in note
    assert round(math.exp(-1.0) * 100.0) == 37
