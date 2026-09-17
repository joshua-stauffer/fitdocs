"""The provenance record for this feature's defaults and divergences (design:
FlagProvenance).

Every default constant `qa/types.py` defines names either a citation in
:data:`CITATIONS` or an entry in :data:`PROVISIONAL_DEFAULTS`, never both, so
"we chose this and cannot yet defend it" is a typed, testable statement rather
than a silence (Req 6.10, 6.11). Every intentional departure from established
platform behavior -- TrainingPeaks' or intervals.icu's -- is recorded in
:data:`DIVERGENCES` with its stated reason (Req 4.3, 8.3), the same discipline
`channels/sources.py` already holds itself to for the channel layer.

**Consume, do not extend, the shared provenance vocabulary.** :class:`Citation`
and :class:`VerificationStatus` (all three members) are `load-channels`'s own
foundation-task types, imported and re-exported here rather than redeclared, so
that a citation from either layer is the same shape. `VerificationStatus`'s
third member, ``FITDOCS_MEASURED``, is the status this feature actually uses
(:data:`FITDOCS_CORPUS_2026_07_25` carries it); no `channels/sources.py`
citation does, and this module edits nothing in that module or in its test
module (`tests/load/channels/test_sources.py`). :class:`Divergence` is the same
type `channels/sources.py` defines for the identical purpose one layer down;
this module records this feature's own six entries under it rather than
inventing a second divergence type.

**Two brief claims are withdrawn, stated here so they cannot resurface
(2026-07-25 cross-spec review, Amendment finding 5):**

1. The "19 versus 241" cross-channel scoring anecdote quoted in the feature
   brief could not be located in any published source consulted during this
   feature's research pass (TrainingPeaks Help Centre, the intervals.icu forum
   and feature pages, and the coaching blogs surveyed for the "under 5%"
   figure's attribution). It is cited nowhere in this feature's design, code
   or tests, and no default, verdict or threshold in this module or elsewhere
   in the package depends on it (Req 3.10).
2. The brief's framing of Efficiency Factor as a signal in its own right is
   **withdrawn**. EF has no absolute reference point and its units differ by
   sport -- W/bpm on the bike, m*s^-1/bpm on the run -- so a single activity's
   EF value admits no threshold. EF enters this feature only as a constituent
   of the decoupling percentage :data:`TRAININGPEAKS_DECOUPLING` and
   :data:`INTERVALS_ICU_DECOUPLING` describe, and as a stated part of a
   verdict's basis; it is never itself thresholded into a verdict (Req 4.5).

**A third, narrower claim is also not made.** The "under 5%" decoupling
reference point is published by TrainingPeaks in its own words (see
:data:`TRAININGPEAKS_DECOUPLING`'s note). Its widespread attribution, across
coaching blogs, to a named coach (Joe Friel) was searched for and not
confirmed against that coach's own published text in this feature's research
pass; that attribution is not verified and is not claimed anywhere in this
module, in :data:`DEFAULT_AEROBIC_DRIFT_MAX_PCT`'s docstring, or in this
feature's design.

This module holds no arithmetic of its own -- only typed provenance records.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from fitdocs.load.channels.sources import Citation as Citation
from fitdocs.load.channels.sources import Divergence as Divergence
from fitdocs.load.channels.sources import VerificationStatus as VerificationStatus

# ``Citation``, ``Divergence`` and ``VerificationStatus`` are re-exported so a
# consumer of this module can read the full provenance shape from one import
# path, matching how ``channels/sources.py`` re-exports ``VerificationStatus``
# from ``fitdocs.citation`` rather than declaring a second copy. The explicit
# ``as`` aliases mark all three as intentional re-exports under mypy strict's
# ``no_implicit_reexport``.


TRAININGPEAKS_DECOUPLING: Final[Citation] = Citation(
    key="trainingpeaks_decoupling",
    authors="TrainingPeaks",
    year=2026,
    work="Aerobic Decoupling (Pw:Hr and Pa:HR) and Efficiency Factor (EF)",
    locator="help.trainingpeaks.com/hc/en-us/articles/204071724-Aerobic-"
    "Decoupling-Pw-Hr-and-Pa-HR-and-Efficiency-Factor-EF",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Read during this feature's 2026-07-25 research pass (year above is "
    "that research pass, not a confirmed publication date -- the article's "
    'own text carries none). Its own words: "a smaller change in EF (less '
    'than 5%)" indicates a well-coupled aerobic effort -- the published '
    "figure :data:`~fitdocs.load.qa.types.DEFAULT_AEROBIC_DRIFT_MAX_PCT` "
    "ships as 5.0. TrainingPeaks' own EF definition uses normalized power on "
    "the bike and normalized **graded** pace on the run; fitdocs' shipped "
    "EF and decoupling (``fitdocs.metrics.power``) use raw power for "
    "decoupling on the bike and raw speed (not graded) on the run -- see "
    "DIVERGENCES' decoupling_numerator_run and decoupling_numerator_bike "
    "entries. The widespread attribution of the 5% figure to Joe Friel "
    "personally is secondary-attestation only and was not confirmed against "
    "Friel's own published text; it is not claimed here.",
)

INTERVALS_ICU_DECOUPLING: Final[Citation] = Citation(
    key="intervals_icu_decoupling",
    authors="intervals.icu",
    year=2026,
    work="Aerobic decoupling calculation question (forum thread) and the "
    "decoupling feature page",
    locator="forum.intervals.icu/t/aerobic-decoupling-calculation-"
    "question/1823; intervals.icu/features/decoupling/",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Read during this feature's 2026-07-25 research pass (year above is "
    "that research pass, not a confirmed post date). States the formula "
    "``(ef1 - ef2) * 100 / ef1`` with the activity split into two halves at "
    "the **sample-index** midpoint, and a numerator of raw average power -- "
    "see DIVERGENCES' decoupling_half_split and decoupling_numerator_bike "
    "entries for how fitdocs' shipped `decoupling_pct` (elapsed-time "
    "midpoint) differs. The feature page separately documents a distinct "
    "'Seiler Decoupling' variant using 60 s moving averages over %HRR and "
    "%power reserve -- see DIVERGENCES' seiler_decoupling_variant entry; "
    "fitdocs implements neither.",
)

PPG_CADENCE_ARTIFACT: Final[Citation] = Citation(
    key="ppg_cadence_artifact",
    authors="Salehizadeh, S.M.A., Dao, D., Bolkhovsky, J., Cho, C., "
    "Mendelson, Y. & Chon, K.H.",
    year=2016,
    work="A Novel Time-Varying Spectral Filtering Algorithm for "
    "Reconstruction of Motion Artifact Corrupted Heart Rate Signals During "
    "Intense Physical Activities Using a Wearable Photoplethysmogram Sensor "
    "(SpaMA)",
    locator="Sensors 16(1), 10; PMC4732043",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Primary, peer-reviewed confirmation that motion cadence can become "
    "the dominant PPG spectral peak during intense activity -- the "
    "phenomenon behind cadence lock -- using 20 Hz sampling, an 8 s "
    "analysis window with a 2 s shift, and a 0.5-3 Hz heart-rate search "
    "band. It describes a real-time onboard signal-processing pipeline, not "
    "a retrospective file-level detector, and no published source gives a "
    "correlation threshold, a window width or a minimum-duration figure for "
    "one. Corroborates the phenomenon only; no fitdocs constant in "
    "``qa/types.py`` derives its value from this citation -- every "
    "cadence-lock default is instead measured against the real corpus and "
    "cites :data:`FITDOCS_CORPUS_2026_07_25`.",
)

FITDOCS_CORPUS_2026_07_25: Final[Citation] = Citation(
    key="fitdocs_corpus_2026_07_25",
    authors="fitdocs",
    year=2026,
    work="Direct measurement over the athlete's real activity corpus",
    locator=".kiro/specs/activity-qa-flags/research.md, "
    "'Direct measurement over the real corpus'",
    verification=VerificationStatus.FITDOCS_MEASURED,
    note="Measured 2026-07-25 against 74 parsed .fit files (50 Run, 10 Ride, "
    "4 Hike, 3 Walk, 7 Workout by normalized sport; the corpus itself never "
    "enters this repository, only these aggregate figures). Whole-activity "
    "Pearson r between heart rate and full-cycle cadence: run min -0.225, "
    "median 0.157, max 0.552 (n=40 assessable runs); ride max 0.605. Median "
    "|HR - 2xcadence| per run spans 9-90 bpm. The worst-case locked duration "
    "the conjunctive association-and-closeness rule found anywhere in the "
    "corpus is 137 seconds, invariant across the correlation thresholds "
    "{0.80, 0.90, 0.95} and the delta thresholds {3, 5, 10} bpm tried. This "
    "single citation is the measurement named by every 'Measured:' default "
    "in ``qa/types.py`` -- ``DEFAULT_CADENCE_LOCK_MIN_CORRELATION`` (0.605 "
    "ceiling), ``DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM`` (9 bpm floor) and "
    "``DEFAULT_CADENCE_LOCK_MIN_DURATION_S`` (137 s worst case) each cite "
    "this same measurement pass, not three separate ones. No activity in "
    "this corpus computed two channels' intensities at once, which is why "
    "the divergence tolerance is recorded in :data:`PROVISIONAL_DEFAULTS` "
    "rather than here.",
)

CITATIONS: Final[tuple[Citation, ...]] = (
    TRAININGPEAKS_DECOUPLING,
    INTERVALS_ICU_DECOUPLING,
    PPG_CADENCE_ARTIFACT,
    FITDOCS_CORPUS_2026_07_25,
)
"""Every citation this feature's own defaults depend on (Req 4.3). Every key
is asserted unique across this tuple **and** ``channels/sources.py``'s own
``CITATIONS`` (Req 4.3) -- the two provenance modules share one namespace of
citation keys even though neither imports the other's constants."""


@dataclass(frozen=True)
class ProvisionalDefault:
    """A default justified by neither a published figure nor a recorded
    measurement, recorded as a typed, testable statement rather than a
    silence (Req 6.10, 6.11).

    ``reasoning`` is why the shipped value was chosen in the absence of
    either source; ``would_settle_it`` is the measurement that would replace
    that reasoning with evidence. Both are required and non-empty -- a
    provisional default cannot be recorded without naming what would retire
    it.
    """

    setting: str
    value: str
    reasoning: str
    would_settle_it: str


PROVISIONAL_DEFAULTS: Final[Mapping[str, ProvisionalDefault]] = {
    "divergence_max_intensity_delta": ProvisionalDefault(
        setting="divergence_max_intensity_delta",
        value="0.20",
        reasoning="Under the shared intensity semantic (Req 3.1; "
        "`load-channels` Requirement 1.11) every channel reports an "
        "intensity-factor-like ratio, exactly 1.0 at threshold, so 0.20 is a "
        "disagreement of roughly a fifth of threshold effort -- about the "
        "width of one conventional training zone. At the shipped value this "
        "is a conservative tolerance that favours the not-detected (agreed) "
        "verdict over a false detected. The value was originally chosen "
        "against a heart-rate intensity scale that has since been corrected "
        "(`load-channels` Requirement 1.11, Amendment finding 1); the "
        "correction changed what the value *means* -- what a 0.20 "
        "difference now represents under the corrected shared semantic -- "
        "without changing the shipped number itself, and it is carried "
        "forward under the corrected semantic as this same stated judgment "
        "call, not as a measurement.",
        would_settle_it="For each activity on which two channels both "
        "computed a value, record abs(selected.intensity - hr.intensity); "
        "over a sample large enough to have a shape, set the tolerance at a "
        "stated percentile of that distribution. This measurement is "
        "unavailable today: the 74-file corpus "
        "(:data:`FITDOCS_CORPUS_2026_07_25`) computed no activity for which "
        "two channels both produced a value, so there is no agreement "
        "distribution yet to set a tolerance against.",
    ),
}
"""Currently exactly one entry: the divergence tolerance is the only default
today that rests on neither a published figure nor a recorded measurement
(Req 6.11). Keyed by the :class:`~fitdocs.load.qa.types.FlagSettings` field
name it defaults, matching how a reader would look it up."""


DIVERGENCES: Final[tuple[Divergence, ...]] = (
    Divergence(
        behavior="decoupling_half_split",
        intervals_icu="Splits the activity into two halves at the "
        "sample-index midpoint (see :data:`INTERVALS_ICU_DECOUPLING`).",
        fitdocs="The shipped ``fitdocs.metrics.power.decoupling_pct`` splits "
        "at the elapsed-time midpoint instead.",
        reason="The shipped decoupling function is fit-ingest's own "
        "definition, not this feature's to fork. The two split conventions "
        "are identical under uniform sampling; forking a second decoupling "
        "implementation here, just to match the sample-index convention, "
        "would give the tool two different decoupling figures instead of "
        "one. Reported upward as fit-ingest's to resolve, not worked around "
        "here.",
    ),
    Divergence(
        behavior="decoupling_numerator_run",
        intervals_icu="TrainingPeaks' Efficiency Factor uses normalized "
        "**graded** pace as the run numerator (see "
        ":data:`TRAININGPEAKS_DECOUPLING`).",
        fitdocs="fitdocs' shipped decoupling numerator on a run is raw "
        "speed, not grade-adjusted.",
        reason="A known confound on hilly runs -- a route with a harder "
        "second half by grade alone can register as decoupling that never "
        "happened effort-wise. This is fit-ingest's own module to correct; "
        "reported to fit-ingest, which now has `load-channels`' grade-"
        "adjustment unit available to it if it chooses to use it. This "
        "feature consumes the metric as shipped and changes nothing about "
        "it (Req 4.1, 9.8).",
    ),
    Divergence(
        behavior="decoupling_numerator_bike",
        intervals_icu="intervals.icu's published decoupling uses raw "
        "average power; TrainingPeaks' EF uses normalized power (NP) "
        "instead (see :data:`INTERVALS_ICU_DECOUPLING`, "
        ":data:`TRAININGPEAKS_DECOUPLING`).",
        fitdocs="fitdocs' own shipped functions are themselves "
        "inconsistent with each other: `decoupling_pct` uses raw power on "
        "the bike, while `efficiency_factor` uses NP.",
        reason="A pre-existing inconsistency inside a fit-ingest-owned "
        "module (``fitdocs.metrics.power``), not introduced by this "
        "feature. Reported upward, not forked or reconciled here -- this "
        "feature consumes both metrics verbatim (Req 4.1, 9.8).",
    ),
    Divergence(
        behavior="seiler_decoupling_variant",
        intervals_icu="intervals.icu's feature page documents a distinct "
        "'Seiler Decoupling' variant computed from 60 s moving averages "
        "expressed as %HRR (heart-rate reserve) and %power reserve (see "
        ":data:`INTERVALS_ICU_DECOUPLING`).",
        fitdocs="Not implemented in fitdocs in any form.",
        reason="Requires an athlete-wide heart-rate and power reserve model "
        "this feature does not have and this spec does not add. Recorded as "
        "an open question rather than silently absent.",
    ),
    Divergence(
        behavior="decoupling_presentation",
        intervals_icu="Every platform surveyed (TrainingPeaks, "
        "intervals.icu) presents decoupling and EF as a displayed number or "
        "chart for the athlete to interpret.",
        fitdocs="fitdocs' aerobic-drift check turns the displayed "
        "decoupling percentage into a typed verdict against a configured "
        "reference point.",
        reason="This feature exists precisely to turn diagnostics into "
        "verdicts (Req 4). No platform surveyed during this feature's "
        "research pass stores a per-activity quality verdict of this kind, "
        "so there is no established behavior to match here -- only a "
        "displayed figure to compare against.",
    ),
    Divergence(
        behavior="coverage_basis",
        intervals_icu="Not applicable to any single surveyed platform -- "
        "this is an internal fitdocs inconsistency between two figures this "
        "tool itself renders, not a comparison against TrainingPeaks or "
        "intervals.icu.",
        fitdocs="The quality-flag layer's coverage and proportion figures "
        "(Req 8.1) are measured over recorded **time** (reusing "
        "`channels.sufficiency.stream_coverage`), while the workout "
        "document's own coverage table counts **samples**.",
        reason="Both figures are correct for the question they answer: a "
        "time-weighted basis answers 'how much of the activity's duration "
        "was covered', while a sample-count basis answers 'how many "
        "recorded points were covered'. The two can differ under "
        "non-uniform sampling. Unifying them would change shipped rendered "
        "output in a file this spec does not own (Req 8.2, 8.3, 8.4) -- "
        "recorded here rather than worked around.",
    ),
)
"""The six recorded departures from established platform behavior this
feature introduces or documents (Req 4.3, 8.3). Uniqueness is asserted over
``.behavior`` -- :class:`Divergence` deliberately has no ``key`` field,
matching `channels/sources.py`'s identical resolution of the same earlier
defect, so a consumer names a divergence by its ``behavior`` string instead."""
