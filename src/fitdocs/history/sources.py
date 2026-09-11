"""Every constant of the fitness/fatigue/form model, its provenance, and the
seam a caller-supplied (or eventually fitted) constant set plugs into
(load-history spec, task 2.1; Req 2.4, 2.5, 2.6, 2.8, 2.10, 3.4).

This module holds no arithmetic beyond the ``1 - e^(-1/tau)`` textual
description its choice records carry as prose -- it declares records, never
computes with them; :mod:`fitdocs.history.model` (task 2.2) is where the
recursion itself lives.

**Two new citations, not the metrics layer's.** :data:`MORTON_1990_RECURSION`
and :data:`BANISTER_1991_TIME_CONSTANTS` are declared here at the recursion's
own locators -- M90 eq. (4)/(5), p. 1173, and B91 pp. 413-414 -- and are
separate :class:`~fitdocs.citation.Citation` records from
:mod:`fitdocs.metrics.sources`' ``MORTON_1990`` (``Eq. 2, p. 1172``) and
``BANISTER_1991`` (``p. 408``), which cite the *training impulse* at
different pages of the same two works. Their ``authors``, ``year`` and
``work`` fields are identical to those records' -- a test
(``tests/history/test_sources.py``) asserts that field by field -- so the
bibliography can never drift into two versions of one book or one paper.

**The two time-constant seeds are stated as unfitted.** B91's 45 d / 15 d
pair is an *average starting value* by the primary text's own words, and
M90's own least-squares fit of its two subjects landed at tau1 = 50 (subject
EWB) / 40 (subject RHM) and tau2 = 11 for both -- not 45/15. This package
names no working document as a constant's source (the package-wide rule
against the reference-docs tree); every claim here rests on the two
:class:`~fitdocs.citation.Citation` records declared below, opened at their
own locators. :data:`TAU_FITNESS_SEED_DAYS` and :data:`TAU_FATIGUE_SEED_DAYS`
each carry a :class:`~fitdocs.citation.Corroboration` on M90's fitted table
with ``agreement=DIFFERS`` whose note states both the fitted values and, in
words, that the shipped value is an illustrative starting value B91 itself
presents as such, never fitted to any athlete.

**The two weighting seeds are fitdocs' own choice, not a citation.** M90
eq. (8) applies k1 = 1 and k2 = 2 once, at the combination step
``p(t) = k1*g(t) - k2*h(t)``; B91 p. 413 states the same illustrative values
("initially K1 = 1 for fitness and K2 = 2 for fatigue") as weights on the
training impulse. fitdocs instead ships both weightings at 1 and reports
``form = fitness - fatigue`` -- an equal-weighted difference rather than a
weighted combination -- because fitting k1/k2 to an athlete's own data is
the gated, not-yet-built ``performance-model-fit`` spec's job, and an
unfitted k2 = 2 is no better attested for any given athlete than an
unfitted k2 = 1.
:data:`K_FITNESS_SEED` and :data:`K_FATIGUE_SEED` are governed by
:data:`WEIGHTING_CHOICE`, a :class:`~fitdocs.citation.FitdocsChoice`, with
this departure recorded once in :data:`DEPARTURES`.

**The coverage threshold is a measured fitdocs choice.** No work in this
literature states a minimum-coverage rule for a period of missing daily
pages, so :data:`COVERAGE_THRESHOLD` is governed by
:data:`COVERAGE_THRESHOLD_CHOICE`, whose ``measurement`` records the
per-uncomputed-daily-page understatement the shipped recursion produces at
the seed constants. **Those figures are transcribed here from design.md and
are not yet verified against running code** -- this task (2.1) precedes the
recursion (2.2) and its own measurement test
(``tests/history/test_coverage_threshold_measurement.py``, task 2.3); 2.3
measures them directly and is the only later task licensed to correct this
module's ``measurement`` string if the reproduced figure differs from the
one transcribed here.

**The recursion-form choice is fitdocs' own, not an instruction taken from a
source.** M90/B91 print the exact exponential decay
``e^(-i/tau)``/``1 - e^(-i/tau)``; vendor documentation (TrainingPeaks) uses
the reciprocal approximation ``1/tau`` per step instead.
:data:`RECURSION_FORM_CHOICE` records fitdocs' choice of the exact form, with
the per-step divergence of the vendor approximation over the exact form
already established elsewhere in this spec's research (``1 - e^(-1/tau)``
against ``1/tau``): **1.12% at the shipped fitness seed (tau = 45 d)** and
**1.20% at the blocked 42-day Performance Management Chart candidate**
(:data:`BLOCKED_PRESETS`) -- the same systematic bias regardless of which of
the two fitness time constants this spec's design considered. These figures
are transcribed here, not freshly computed by this module (which holds no
arithmetic), and are to be reproduced by the same task-2.3 measurement test
that reproduces :data:`COVERAGE_THRESHOLD_CHOICE`'s figures, on the same
footing -- no stated number in this module ships unreproduced.

**The daily-average scale is fitdocs' own reporting choice.**
:data:`DAILY_AVERAGE_SCALE_CHOICE` records that fitness and fatigue are
reported at the recursion's asymptotic daily-average level -- each
accumulator times its weighting times ``(1 - e^(-1/tau))`` -- rather than as
the raw, unscaled accumulator, so the number on the page is in the same
per-day units as a single day's load, independent of how many days the
recursion has run.

**The blocked preset is a declared absence, not an omission.**
:data:`BLOCKED_PRESETS` names the 42-day / 7-day Performance Management
Chart pair fitdocs does **not** ship as a :class:`CitedConstant`: the trail
runs to a 2006 conference presentation, a TrainingPeaks marketing page, and
Allen & Coggan (2nd ed.) ch. 8 by reviewer account with the page locator
itself unverified against a primary copy. A test asserts no shipped
:class:`~fitdocs.citation.CitedConstant` in this module carries 42.0 or 7.0
as a time constant -- the same roadmap Direct Implementation Candidate (a
physical or PDF verification of the Allen & Coggan page) that blocks
``performance-benchmarks``' own ``PENDING_CONSTANTS``/``BLOCKED_METHODS``
blocks this preset too, so clearing it clears both files at once. An athlete
may still type 42 and 7 into settings; the resulting curve is then reported
as the athlete's own, uncited constants (Req 2.7), never as this preset.

**Holds no bare methodologically-significant numeric literal.** Every value
that could change the model's output is read from a :class:`CitedConstant`;
:data:`SEED_CONSTANTS` reads its four fields from the four
:class:`CitedConstant` objects' own ``.value`` rather than spelling a number,
and an independent literal scan (``tests/history/test_constant_guard.py``)
enforces this across the whole package, walking whatever modules exist under
it rather than a fixed list.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from fitdocs.citation import (
    Agreement,
    Citation,
    CitedConstant,
    Corroboration,
    Departure,
    FitdocsChoice,
    VerificationStatus,
)

# --- Citations (Req 2.4) -----------------------------------------------------
#
# Same works as fitdocs.metrics.sources' MORTON_1990 / BANISTER_1991, at the
# recursion's own locators rather than the training-impulse weighting's.
# authors/year/work are byte-identical to those records'; only key, locator
# and note differ (tests/history/test_sources.py pins the equality).

MORTON_1990_RECURSION: Final[Citation] = Citation(
    key="morton_1990_recursion",
    authors="Morton, R.H., Fitz-Clarke, J.R., Banister, E.W.",
    year=1990,
    work="Modeling human performance in running, Journal of Applied "
    "Physiology 69(3):1171-1177",
    locator="Eq. 4-5, p. 1173",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="The fitness/fatigue recursion's own governing source, distinct "
    "from fitdocs.metrics.sources.MORTON_1990 (Eq. 2, p. 1172), which cites "
    "the training-impulse weighting instead. Eq. (4) g(t) = g(t-i)*e^(-i/"
    "tau1) + w(t) and Eq. (5) h(t) = h(t-i)*e^(-i/tau2) + w(t) are the "
    "fitness and fatigue accumulators; Eq. (8) p(t) = k1*g(t) - k2*h(t) "
    "applies the weightings once, at the combination step, never inside "
    "the accumulators themselves.",
)

BANISTER_1991_TIME_CONSTANTS: Final[Citation] = Citation(
    key="banister_1991_time_constants",
    authors="Banister, E.W.",
    year=1991,
    work="Modeling Elite Athletic Performance, in: Physiological Testing of "
    "the High-Performance Athlete (2nd ed.), Human Kinetics",
    locator="pp. 413-414",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="The fitness/fatigue time constants' own governing source, "
    "distinct from fitdocs.metrics.sources.BANISTER_1991 (p. 408), which "
    "cites the training-impulse weighting instead. States the time "
    "constants, 'on average', as 45 d for fitness and 15 d for fatigue, "
    "and defines a time constant as the time for a decaying variable to "
    "fall to 37% of its level.",
)

# --- FitdocsChoices (Req 2.6, 2.8, 3.4) --------------------------------------

WEIGHTING_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="weighting_choice",
    justification="M90 eq. (8) applies k1 = 1 and k2 = 2 once, at the "
    "combination step p(t) = k1*g(t) - k2*h(t); B91 p. 413 states the same "
    "illustrative values ('initially K1 = 1 for fitness and K2 = 2 for "
    "fatigue') as weights on the training impulse -- both primary texts "
    "state these as illustrative starting weightings rather than a fitted "
    "result for any athlete. fitdocs ships both weightings at 1 instead "
    "and reports form = fitness - "
    "fatigue -- an equal, unweighted difference -- because fitting k1/k2 "
    "to an athlete's own data is the gated, not-yet-built "
    "performance-model-fit spec's job, not this spec's, and an unfitted "
    "k2 = 2 is no better attested for any given athlete than an unfitted "
    "k2 = 1. See DEPARTURES for the departure this records.",
    search_basis="No further search was needed: both primary texts already "
    "obtained for this layer (M90 eq. (8), B91 p. 413) state the "
    "weightings directly as illustrative starting values, so the question "
    "this record answers is not what value a source states, but whether "
    "to ship that illustrative value uncorroborated by any fit -- a "
    "judgment call this layer states as its own choice rather than as an "
    "instruction taken from a source.",
)

COVERAGE_THRESHOLD_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="coverage_threshold_choice",
    justification="A period whose share of load-recording pages falls "
    "below this threshold has its drawn curve suppressed (Req 3.3) rather "
    "than drawn from data too sparse to support it. 0.80 (80% of a "
    "period's pages recording a load) is fitdocs' own choice: high enough "
    "that a suppressed period is genuinely gap-heavy, low enough that an "
    "athlete's ordinary handful of unscored pages a month does not blank "
    "out reporting periods that are otherwise well covered.",
    search_basis="A review of the primary texts already obtained for this "
    "layer (Banister (1991) pp. 403-424, Morton, Fitz-Clarke & Banister "
    "(1990)) found no stated minimum-coverage rule for a period of missing "
    "daily training-load pages in either work -- both assume a "
    "continuously recorded training-impulse series and never address a "
    "gap-tolerance threshold at all. No published work in this literature "
    "defines one.",
    measurement="At the shipped seed constants (tau1 = 45 d, tau2 = 15 d), "
    "one uncomputed daily page understates the reported fitness accumulator "
    "by 2.198% and the reported fatigue accumulator by 6.449% relative to "
    "what an equal-magnitude recorded page at that day would have "
    "contributed, per day the page is missing. To be reproduced by task "
    "2.3's tests/history/test_coverage_threshold_measurement.py, which "
    "owns correcting this figure if the shipped recursion measures "
    "differently -- these numbers are transcribed here from design.md, not "
    "yet run.",
)

RECURSION_FORM_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="recursion_form_choice",
    justification="M90 eq. (4)/(5) and B91 pp. 413-414 print the exact "
    "exponential decay e^(-i/tau) (fitness accumulator factor) and "
    "1 - e^(-i/tau) (the constant-input asymptotic scale, M90 eq. (6)/(7)); "
    "vendor documentation (TrainingPeaks) instead uses the reciprocal "
    "approximation 1/tau per step. fitdocs uses the exact form because it "
    "is what the primary text prints and because a systematic bias of "
    "roughly 1.1-1.2% per step (1.12% at tau = 45 d, 1.20% at tau = 42 d) "
    "is not worth inheriting from a help page over a multi-year "
    "integration. This is fitdocs' own choice between "
    "two available forms, never an instruction taken from a source -- "
    "neither text mentions the reciprocal approximation at all.",
    search_basis="The vendor's own published help text (summarized in this "
    "spec's research) states the reciprocal approximation without citing a "
    "peer-reviewed source for preferring it over the primary texts' exact "
    "form; no published work in this literature recommends the "
    "approximation over the exact decay.",
    measurement="The reciprocal approximation 1/tau exceeds the exact "
    "1 - e^(-1/tau) by 1.12% at the shipped fitness seed (tau = 45 d) and "
    "by 1.20% at the blocked Performance Management Chart candidate "
    "(tau = 42 d; see BLOCKED_PRESETS) -- the same systematic bias at "
    "either time constant. To be reproduced by the same task-2.3 "
    "measurement test as COVERAGE_THRESHOLD_CHOICE, on the same footing: "
    "transcribed here, not yet run.",
)

DAILY_AVERAGE_SCALE_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="daily_average_scale_choice",
    justification="fitdocs reports fitness and fatigue at the recursion's "
    "asymptotic daily-average level -- each accumulator multiplied by its "
    "weighting and by (1 - e^(-1/tau)), M90 eq. (6)/(7)'s own constant-input "
    "scale factor -- rather than the raw, unscaled accumulator. This puts "
    "the reported number in the same per-day units as a single day's load, "
    "regardless of how many days the recursion has been running when the "
    "page is generated, which the raw accumulator does not: two archives "
    "identical in every day's load but differing in how long the archive "
    "runs would otherwise report different raw accumulator magnitudes for "
    "the same steady-state training pattern.",
    search_basis="Neither M90 nor B91 states a preferred reporting scale "
    "for the accumulators themselves; M90 eq. (6)/(7) derives the "
    "(1 - e^(-1/tau)) factor as the constant-input asymptote, which this "
    "choice reuses as a reporting convention rather than as an instruction "
    "the text gives for how to report the running series.",
)


# --- CitedConstant bindings (Req 2.4, 2.5, 2.8, 3.4) -------------------------

TAU_FITNESS_SEED_DAYS: Final[CitedConstant[float]] = CitedConstant(
    name="tau_fitness_seed_days",
    value=45.0,
    source=BANISTER_1991_TIME_CONSTANTS,
    corroborators=(
        Corroboration(
            citation=MORTON_1990_RECURSION,
            locator="Table 2",
            agreement=Agreement.DIFFERS,
            note="M90 Table 2's least-squares fit yields tau1 = 50 d "
            "(subject EWB) and 40 d (subject RHM), not 45 d. The shipped "
            "value, 45 d, is B91's own 'on average' illustrative starting "
            "value (pp. 413-414) -- an illustrative starting value never "
            "fitted to any athlete, in either primary text.",
        ),
    ),
)
"""The fitness time constant's shipped seed, in days (B91 pp. 413-414: 'on
average 45 d for fitness'). See DAILY_AVERAGE_SCALE_CHOICE for the reporting
scale this drives and WEIGHTING_CHOICE for the accompanying k1."""

TAU_FATIGUE_SEED_DAYS: Final[CitedConstant[float]] = CitedConstant(
    name="tau_fatigue_seed_days",
    value=15.0,
    source=BANISTER_1991_TIME_CONSTANTS,
    corroborators=(
        Corroboration(
            citation=MORTON_1990_RECURSION,
            locator="Table 2",
            agreement=Agreement.DIFFERS,
            note="M90 Table 2's least-squares fit yields tau2 = 11 d for "
            "both subjects (EWB and RHM), not 15 d. The shipped value, "
            "15 d, is B91's own 'on average' illustrative starting value "
            "(pp. 413-414) -- an illustrative starting value never fitted "
            "to any athlete, in either primary text.",
        ),
    ),
)
"""The fatigue time constant's shipped seed, in days (B91 pp. 413-414: 'on
average 15 d for fatigue')."""

TRIMP_WEIGHTING_SEEDS_DEPARTURE: Final[Departure] = Departure(
    subject="trimp_weighting_seeds",
    source_specifies="M90 eq. (8) applies k1 = 1 and k2 = 2 once, at the "
    "combination step p(t) = k1*g(t) - k2*h(t); B91 p. 413 states the same "
    "illustrative values ('initially K1 = 1 for fitness and K2 = 2 for "
    "fatigue') as weights on the training impulse -- both primary texts "
    "state these as illustrative starting weightings, k2 = 2 being the one "
    "that differs from fitdocs' shipped value.",
    fitdocs_does="fitdocs ships both k1 and k2 at 1 and reports "
    "form = fitness - fatigue, an equal, unweighted difference of the two "
    "accumulators, rather than the weighted combination p(t) = k1*g(t) - "
    "k2*h(t) the primary texts illustrate.",
    reason="Fitting k1/k2 to an athlete's own data is the gated, "
    "not-yet-built performance-model-fit spec's job, not this spec's. An "
    "unfitted k2 = 2 is no better attested for any given athlete than an "
    "unfitted k2 = 1, so fitdocs ships the equal weighting and reports the "
    "plain difference rather than presenting an arbitrary weighted "
    "combination as though it carried a fitted value's authority.",
)
"""The one departure both weighting seeds carry (Req 16.5) -- a single
shared record, not one per seed, because both CitedConstants below record
the same fitdocs-does-not-weight decision rather than two independent
departures."""

K_FITNESS_SEED: Final[CitedConstant[float]] = CitedConstant(
    name="k_fitness_seed",
    value=1.0,
    source=WEIGHTING_CHOICE,
    departure=TRIMP_WEIGHTING_SEEDS_DEPARTURE,
)
"""The fitness weighting's shipped seed (fitdocs' own choice: 1 -- equal to
B91's own illustrative k1 = 1, unlike K_FATIGUE_SEED, which departs from
B91's illustrative k2 = 2)."""

K_FATIGUE_SEED: Final[CitedConstant[float]] = CitedConstant(
    name="k_fatigue_seed",
    value=1.0,
    source=WEIGHTING_CHOICE,
    departure=TRIMP_WEIGHTING_SEEDS_DEPARTURE,
)
"""The fatigue weighting's shipped seed (fitdocs' own choice: 1, departing
from B91's illustrative k2 = 2 -- see TRIMP_WEIGHTING_SEEDS_DEPARTURE)."""

COVERAGE_THRESHOLD: Final[CitedConstant[float]] = CitedConstant(
    name="coverage_threshold",
    value=0.80,
    source=COVERAGE_THRESHOLD_CHOICE,
)
"""The shipped minimum share of a period's pages that must record a load
before its curve is drawn rather than suppressed (Req 3.3, 3.4)."""


CONSTANT_SOURCES: Final[tuple[CitedConstant[float], ...]] = (
    TAU_FITNESS_SEED_DAYS,
    TAU_FATIGUE_SEED_DAYS,
    K_FITNESS_SEED,
    K_FATIGUE_SEED,
    COVERAGE_THRESHOLD,
)
"""Every :class:`CitedConstant` this module declares, exactly once each
(Req 2.4). Registry-walked by ``tests/history/test_sources.py``."""

DEPARTURES: Final[tuple[Departure, ...]] = (TRIMP_WEIGHTING_SEEDS_DEPARTURE,)
"""Every deliberate departure this module's constants make from what the
cited primary texts specify (Req 16.5, carried from ``fitdocs.citation``).
Subjects are unique."""


# --- The blocked preset (Req 2.8) --------------------------------------------


@dataclass(frozen=True)
class BlockedPreset:
    """A named configuration preset this module deliberately does **not**
    ship as a :class:`~fitdocs.citation.CitedConstant`, and exactly what must
    be verified before it becomes one (Req 2.8) -- a declared absence, not an
    omission."""

    key: str
    values: str
    blocked_by: str


PERFORMANCE_MANAGEMENT_CHART_PRESET: Final[BlockedPreset] = BlockedPreset(
    key="performance_management_chart_42_7",
    values="tau1 = 42 d (fitness), tau2 = 7 d (fatigue) -- the "
    "Coggan/TrainingPeaks Performance Management Chart pair.",
    blocked_by="The trail runs to a 2006 conference presentation, a "
    "TrainingPeaks marketing page describing the pair as 'nominal values "
    "based on the scientific literature' while dropping k1/k2 from the "
    "model entirely, and Allen & Coggan (2nd ed.) ch. 8 by reviewer "
    "account only, with the page locator itself unverified against a "
    "primary copy. This module ships no CitedConstant for this pair until "
    "that locator is verified from a physical or PDF copy of Allen & "
    "Coggan (2nd ed.) ch. 8 -- the same roadmap Direct Implementation "
    "Candidate that blocks performance-benchmarks' own PENDING_CONSTANTS/"
    "BLOCKED_METHODS. An athlete may still configure 42 and 7 directly; "
    "the resulting curve is then reported as the athlete's own, uncited "
    "constants (Req 2.7), never as this preset.",
)

BLOCKED_PRESETS: Final[tuple[BlockedPreset, ...]] = (
    PERFORMANCE_MANAGEMENT_CHART_PRESET,
)
"""Every configuration preset this module deliberately withholds
(Req 2.8). A test asserts no CitedConstant in CONSTANT_SOURCES carries 42.0
or 7.0 as a time constant."""


# --- The constant set value object and its seed instance (Req 2.5, 2.10) ----


class ConstantProvenance(StrEnum):
    """Where a :class:`ModelConstants` set's values came from (Req 2.5,
    2.10)."""

    SEEDS = "seeds"
    """The shipped starting values this module declares (task 2.1)."""

    CONFIGURED = "configured"
    """Supplied by the athlete's own configuration (Req 2.7)."""

    FITTED = "fitted"
    """Produced by fitting a constant set to an athlete's own data. Declared
    here so the downstream, gated ``performance-model-fit`` spec adds no new
    member to this enumeration; no code in this plan ever constructs a
    :class:`ModelConstants` with this provenance."""


@dataclass(frozen=True)
class ModelConstants:
    """A complete constant set for the fitness/fatigue/form recursion, and
    the provenance a page states for it (Req 2.5, 2.7, 2.10)."""

    tau_fitness_days: float
    tau_fatigue_days: float
    k_fitness: float
    k_fatigue: float
    provenance: ConstantProvenance
    origin: str
    """One line, printed verbatim on the page (Req 2.7, 2.10)."""


SEED_CONSTANTS: Final[ModelConstants] = ModelConstants(
    tau_fitness_days=TAU_FITNESS_SEED_DAYS.value,
    tau_fatigue_days=TAU_FATIGUE_SEED_DAYS.value,
    k_fitness=K_FITNESS_SEED.value,
    k_fatigue=K_FATIGUE_SEED.value,
    provenance=ConstantProvenance.SEEDS,
    origin="fitdocs' shipped seed constants (Banister (1991) pp. 413-414 "
    "for the time constants; fitdocs' own equal-weighting choice for k1/k2 "
    "-- never fitted to any athlete).",
)
"""The shipped default constant set, read entirely from the four
:class:`CitedConstant` objects above -- no numeric literal of its own."""
