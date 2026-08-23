"""Provenance for every constant the metrics layer computes a reported metric
from (Amendment 1; Req 15, 16, 17).

This module holds no arithmetic and defines no metric of its own -- records
only, so a document or report can name the source of a number without
computing it (16.6). It imports the shared record shapes from
:mod:`fitdocs.citation`, and (as of task 9.4) the ``TrimpWeighting``
selection vocabulary from :mod:`fitdocs.metrics.types` that
:class:`WeightingPair` keys against. Importing this module necessarily first
runs ``fitdocs.metrics.__init__``, which -- outside this task's boundary --
already imports the arithmetic-bearing sibling modules ``aggregates``,
``power``, ``stress`` and ``zones``; that parent-package behavior is not
this module's own doing. What this module itself adds internally is
``fitdocs.citation`` and ``fitdocs.metrics.types``, and no metric is
computed at import time by this module -- ``weighting_for`` below resolves a
selection to a pair of already-bound constants; it does not compute a
metric. As it stands after task 9.4, this module is still importable in a
fresh interpreter without pulling in the ``garmin-fit-sdk``.

**Task 9.2's own three records.** ``NP_MIN_SPAN_CHOICE``,
``MOVING_THRESHOLD_CHOICE`` and ``ALTITUDE_WINDOW_CHOICE`` below each carry
a ``justification`` (why this value) and a ``search_basis`` (what was
searched and what was found, per Req 15.9) rather than an authors/year/work/
locator -- there is no published work to name for any of the three.
``NP_MIN_SPAN_CHOICE.search_basis`` says plainly that no live
literature-search tool was available in the session that wrote it, and
reports instead what review of the primary texts already obtained for this
layer found. ``MOVING_THRESHOLD_CHOICE`` and ``ALTITUDE_WINDOW_CHOICE`` were
each remediated in a later session with a live web-search tool; their
``search_basis`` fields name the queries actually run and what each source
found rather than claiming no tool was available, and each also discloses
that its value is inherited from fitdocs.ai (the reference application this
project otherwise borrows its parsing pipeline and metric formulas from --
see ``aggregates.py``) rather than originated in this layer, and that
fitdocs.ai is an application whose source this project read, not a
published work under criterion 15.1, so it is not itself treated as a
citable source. In every case, "no published work defines this" stays the
evidenced conclusion of a search performed and reported, not a cheaper
substitute for one. None
of the three rests on a measurement fitdocs itself took, so ``measurement``
is ``None`` on all three -- Req 15.8 requires recording a measurement only
where the choice rests on one.

Task 9.1 populated the three published-work records below -- one
:class:`~fitdocs.citation.Citation` per publishing work this layer's
classification names (design.md's "MetricsSources" Service Interface, 15.1
row). Task 9.2 adds the three :class:`~fitdocs.citation.FitdocsChoice`
records below that -- one per value design.md's classification table
resolves under 15.8, a value no published work defines. The ``ConstantGuard``
is still task 12.1 and does not exist here yet.

**Task 9.3** binds every value Req 15.6's enumeration names to exactly one of
the six records above via :class:`~fitdocs.citation.CitedConstant`, and
collects every one of them into ``CONSTANT_SOURCES``. The enumeration counts
the training-impulse weighting as one item naming two constants (the
coefficient and the exponent), and both are instantiated once per fitted
curve the weighting selection offers (male, female) rather than once each --
the resolver below (task 9.4) may return either curve, and every term a
``WeightingPair`` holds there is already present in this registry. That
makes ten ``CitedConstant`` bindings in all: four training-impulse terms
(``BANISTER_MALE_COEFFICIENT``, ``BANISTER_MALE_EXPONENT``,
``BANISTER_FEMALE_COEFFICIENT``, ``BANISTER_FEMALE_EXPONENT``) plus the six
non-weighting values below (``TSS_SCALE``, ``NP_ROLLING_WINDOW_S``,
``NP_AVERAGING_EXPONENT``, ``NP_MIN_SPAN_S``, ``MOVING_SPEED_THRESHOLD_MPS``,
``ALTITUDE_SMOOTHING_WINDOW``). Every governing ``source`` and every
corroborator below is bound by *identity* to one of the six records above,
not re-declared -- ``BANISTER_1991``, ``MORTON_1990`` and ``COGGAN_2003`` for
the four 15.1 items (five constants), ``NP_MIN_SPAN_CHOICE``,
``MOVING_THRESHOLD_CHOICE`` and
``ALTITUDE_WINDOW_CHOICE`` for the three 15.8 values. None of the ten values
differs from what ``stress.py``, ``power.py`` and ``aggregates.py`` already
ship (this task transcribes citations, it does not re-derive numbers), so
every ``previous_value`` is ``None`` and every ``departure`` is ``None`` --
16.5's ``DEPARTURES`` collection is task 9.4's, not this one's. This module
still holds no arithmetic: the values below are literals bound to records,
not computed.

**Verification, not transcription.** Each locator below was confirmed against
the named work's own primary text opened in this session -- the page scans
for Banister (1991), the publisher PDF for Morton, Fitz-Clarke & Banister
(1990), and Coggan's own 2003 manuscript -- never against any working
document. Req 15.5 forbids naming a working document under this repository's
reference-docs tree as the source of a constant this layer computes a
reported metric from; no record or note here does, and none is a permitted
substitute for reading the work named on the record.

**The one non-primary element.** :data:`BANISTER_1991`'s ``year`` (1991) rests
on the OCLC / Internet Archive catalogue record rather than the book's own
text -- its copyright page carries no year. The chapter's *content* (the
weighting equations at p. 408) is primary text; the year is flagged on the
record's own ``note`` rather than presented as equally primary.

**What the worked examples do not do.** Banister's own worked examples
(Figs. 9.5-9.6 captions, pp. 409-410) disagree with the equation on p. 408 by
8-370%, and one is not even internally consistent with itself. Neither
:data:`BANISTER_1991` nor its locator rests on those examples; they confirm
nothing about the constants and are not cited here for that purpose (task
12.3 handles worked examples, not this one).

**Task 9.4** adds :class:`WeightingPair`, ``WEIGHTING_PAIRS``,
``DEFAULT_TRIMP_WEIGHTING``, :func:`weighting_for` and ``DEPARTURES`` below.
``WEIGHTING_PAIRS`` keys the two fitted curves task 9.3 already registered
(the four ``BANISTER_*`` bindings above) by the :class:`~fitdocs.metrics.
types.TrimpWeighting` selection each curve belongs to -- reusing those four
``CitedConstant`` objects by identity rather than re-declaring their values.
``DEFAULT_TRIMP_WEIGHTING`` is ``TrimpWeighting.BANISTER_MALE`` as a
*consequence* of Req 17.2, not a preference: 17.2 pins the no-selection
default to the pair fitdocs applied before this amendment -- (0.64, 1.92),
the male curve -- which ``stress.py`` itself held as its own module
constants, ``_TRIMP_COEFFICIENT``/``_TRIMP_EXPONENT``, before task 11 removed
both in favor of the caller-resolved ``weighting`` parameter
:func:`fitdocs.metrics.stress.trimp` takes today. That pre-amendment value is
pinned today by value alone, not by re-deriving it through this module,
in ``tests/metrics/test_sources.py::
test_default_trimp_weighting_resolves_to_the_pre_amendment_stress_py_values``
(standalone ``== 0.64`` / ``== 1.92`` equalities). :func:`weighting_for` is
total over
``TrimpWeighting | None``: ``None`` resolves to the default (17.2), a
recognized selection resolves to its registered pair (17.1), and anything
else -- including a plain ``str`` that matches no defined selection's value,
reachable because ``TrimpWeighting`` is a ``StrEnum`` -- raises
:class:`ValueError` naming the rejected selection and every selection the
source defines, rather than silently substituting a pair (17.4). This
module still computes no metric: resolving a selection to an
already-registered pair of ``CitedConstant`` objects is a lookup, not
arithmetic. ``DEPARTURES`` records the three deliberate departures from the
cited primary texts that this amendment's weighting behavior makes (16.5) --
none of them is the NP rolling-window start condition, which was removed
in task 13.1 rather than recorded here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
from fitdocs.metrics.types import TrimpWeighting

BANISTER_1991: Final[Citation] = Citation(
    key="banister_1991",
    authors="Banister, E.W.",
    year=1991,
    work="Modeling Elite Athletic Performance, in: Physiological Testing of "
    "the High-Performance Athlete (2nd ed.), Human Kinetics",
    locator="p. 408",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="The training-impulse weighting's governing source for both the "
    "coefficient and the exponent, for both sexes. Opened in this session "
    "at the chapter's own page scan (page footer reads '408'): under 'the "
    "following equations', the printed page states "
    "'y = 0.64e^1.92x (male)' and 'y = 0.86e^1.67x (female)', both "
    "coefficient and exponent present together on this page for each sex. "
    "The same page defines 'e' as 'the Napierian logarithm having a value "
    "of 2.712' -- a misstatement of e (which is 2.71828...); that 2.712 "
    "figure is not recorded anywhere in this layer as a constant. The "
    "year, 1991, is the one element on this record that rests on the "
    "OCLC / Internet Archive catalogue entry rather than on the book's own "
    "pages -- the chapter carries no copyright-page year itself.",
)

MORTON_1990: Final[Citation] = Citation(
    key="morton_1990",
    authors="Morton, R.H., Fitz-Clarke, J.R., Banister, E.W.",
    year=1990,
    work="Modeling human performance in running, Journal of Applied "
    "Physiology 69(3):1171-1177",
    locator="Eq. 2, p. 1172",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="A corroborator of the training-impulse weighting's exponent, not "
    "a governing source -- Banister (1991) p. 408 governs both weighting "
    "terms. Opened in this session (publisher PDF, printed p. 1172): "
    "labeled equation (2) reads 'Y = e^bx', with the surrounding text "
    "giving 'b values for men (1.92) and women (1.67)'. No multiplicative "
    "coefficient appears anywhere in that equation or in the paragraph "
    "introducing it -- confirmed by reading the page, not merely its "
    "absence from a summary. This is why the coefficient's corroboration "
    "is OMITS while the exponent's is AGREES: the exponents (1.92, 1.67) "
    "match Banister (1991) p. 408 exactly; the coefficient this work "
    "simply does not state.",
)

COGGAN_2003: Final[Citation] = Citation(
    key="coggan_2003",
    authors="Coggan, A.R.",
    year=2003,
    work="Training and racing using a power meter: an introduction (USA "
    "Cycling coaching-education chapter; the basis for, and later folded "
    'into, Allen & Coggan\'s "Training and Racing with a Power Meter")',
    locator='§3 "Analysis of power meter data" -> "Intensity factor '
    '(IF) and training stress score (TSS)", pp. 8-11 of the revised 25 '
    "March 2003 edition",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="The governing source for the normalized-power rolling-window "
    "width, the normalized-power averaging exponent, and the "
    "training-stress-score scale -- the same work already shipping as "
    "COGGAN_TSS in fitdocs.load.channels.sources; this record reuses that "
    "identification rather than re-deriving it, since it is Coggan's own "
    "primary text rather than the Allen & Coggan book, which was never "
    "obtained. Opened in this session (printed pp. 8-11 of the revised 25 "
    "March 2003 edition): printed p. 8 carries the 'Intensity factor (IF) "
    "and training stress score (TSS)' heading and the TRIMPS equation "
    "'TRIMPS = exercise duration x average HR x a HR-dependent intensity "
    "weighting factor'; printed p. 9 proposes TSS 'by analogy' as "
    "'TSS = exercise duration x average power x a power-dependent "
    "intensity weighting factor' and states the averaging exponent 'was "
    "rounded from 3.90 to 4.00 for simplicity's sake'; printed p. 10 lists "
    "the eight computation steps verbatim, including step 1 ('starting at "
    "30 s, calculate a 30 second rolling average for power' -- the "
    "rolling-window width), steps 2-4 ('raise the values obtained in step "
    "1 to the 4th power' / 'take the average of all the values obtained "
    "in step 2' / 'take the 4th root of the number obtained in step 3' -- "
    'the averaging exponent), and step 8 (\'divide the "raw" TSS by the '
    "amount of work that could be performed in one hour at threshold "
    "power ... and multiply by 100 to obtain the final TSS' -- the TSS "
    "scale, 100).",
)

NP_MIN_SPAN_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="np_min_span_choice",
    justification="The minimum span is set equal to the width of the "
    "rolling-mean window Coggan (2003) itself specifies (30 s; COGGAN_2003 "
    "governs that width, not this record) -- but that window is 30 "
    "*samples* wide, and at this module's 1 Hz resample a 30-sample window "
    "spans only 29 s of elapsed offset (samples at offset 0 s through "
    "offset 29 s), not 30 s. A 29.0 s power-stream span already resamples "
    "to 30 one-second points and so already yields one complete windowed "
    "value from the cited procedure's own rolling-mean step (step 1); "
    "29.0 s, not 30.0 s, is the smallest span for which that step produces "
    "even a single complete value. This record nonetheless sets the "
    "threshold at 30.0 s -- one second above that smallest span -- because "
    "the threshold is stated in the same units the cited text itself uses "
    "for the window (seconds: '30 s' / '30 second', COGGAN_2003 step 1), "
    "rather than as a figure derived from this module's own sampling grid; "
    "reading the minimum span directly off the window width Coggan's text "
    "states, in the units that text states it, is the choice this record "
    "makes and states over the samples-vs-seconds arithmetic instead. No "
    "measurement was taken to arrive at 30.0 s; it is read directly off "
    "the window width Coggan's own text fixes elsewhere in this layer, in "
    "the seconds that text uses to state it.",
    search_basis="This session has no live literature-search tool "
    "available, so the search was a review of the three primary texts "
    "already obtained for this layer -- Banister (1991) p. 408, Morton "
    "(1990) Eq. 2 p. 1172, and Coggan (2003) pp. 8-11, all re-opened and "
    "quoted above at BANISTER_1991, MORTON_1990 and COGGAN_2003 -- for any "
    "stated minimum power-stream duration below which the procedure should "
    "be withheld. Coggan's own eight steps define the rolling-window "
    "width, the averaging exponent and the final scale but never state a "
    "minimum span; Banister's and Morton's texts concern the "
    "heart-rate-based training-impulse weighting only and do not address a "
    "power stream at all. The Allen & Coggan book this manuscript was "
    "folded into was never obtained (noted already on COGGAN_2003) and is "
    "not treated here as a substitute search target. No published work "
    "located in this review states a minimum span; the figure recorded "
    "here is derived from the window width these same texts do govern, "
    "not read from an independent published minimum.",
)

MOVING_THRESHOLD_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="moving_threshold_choice",
    justification="0.5 m/s is a value fitdocs inherits from fitdocs.ai, the "
    "reference application this project's parsing pipeline and metric "
    "formulas otherwise borrow directly (see aggregates.py); fitdocs took "
    "no measurement of its own to arrive at it, and states here its own "
    "reasoning for retaining the inherited value rather than presenting "
    "the number as originated in this layer. It is a slow-walking-pace "
    "floor below which a single instantaneous speed sample cannot be "
    "reliably distinguished from GPS noise at a standstill; "
    "treating a sample above it as 'moving' keeps brief stationary noise "
    "from being counted as movement without also discarding genuine slow "
    "walking. A pair that fails the speed test falls through to whether "
    "cumulative distance increased across it -- this is not restricted to "
    "a speed-less channel, so a present-but-low speed reaches the distance "
    "check too. (Corrected 2026-08-23, queue "
    "2026-07-29-moving-threshold-justification-over-narrows and "
    "2026-07-28-moving-fallback-not-speed-less-only: this parenthetical "
    "previously read 'or a cumulative-distance increase across the pair, "
    "for a speed-less channel', which described a narrower rule than "
    "aggregates.py implements. The identical wording was already corrected "
    "in aggregates.py's own docstring at task 10.1; this copy was ruled out "
    "of that task's boundary and left standing. The code is what Req 7.1 "
    "specifies -- 'session timer, else threshold + distance-increase "
    "fallback', with no speed-less qualifier -- so the record was the thing "
    "that drifted and no computed value moves. Consequence now stated "
    "rather than implied: on an activity with a speed channel and a noisy "
    "distance channel, a standing-still sample whose distance ticks up is "
    "counted as moving.) That reasoning is why fitdocs keeps "
    "the inherited value rather than replacing it: it is a judgment call "
    "about where that noise floor sits, not a value either fitdocs.ai or "
    "this layer read off measured data.",
    search_basis="A web literature search was run for a published "
    "GPS- or accelerometry-based moving/stopped speed threshold, using "
    "the queries 'GPS moving time speed threshold stationary detection "
    "published method m/s fitness tracking', '\"moving time\" algorithm "
    'speed threshold "0.5 m/s" OR "1 m/s" cycling running published '
    "standard', and 'accelerometry GPS speed cut-point classifying "
    "stationary versus ambulatory sports science threshold m/s "
    "validation'. The physical-activity/accelerometry cut-point "
    "literature defines intensity cut-points and walking-speed bands, not "
    "a moving/stopped floor for workout timing: a post-stroke ROC study "
    "sets ambulation bands of 0.41-0.8, 0.81-1.2 and >1.2 m/s; a "
    "chest-patch validation gives a sedentary-vs-ambulatory Mean "
    "Amplitude Deviation cut-point of 47.73 mG, an acceleration magnitude "
    "rather than a speed. GPS-based activity classification (the "
    "Personal Activity Location Measurement System) defines stationary "
    "time as under 25 m of displacement in a minute, a "
    "distance-over-interval rule rather than a per-sample speed "
    "comparison. Patent literature sets a moving-speed threshold near "
    "7.0 km/h (~1.94 m/s) for detecting running specifically, and "
    "elsewhere detects movement by consecutive GPS fixes over 5 m apart "
    "across 5 s; neither is a general moving-time floor, and both sit "
    "two to four times above 0.5 m/s. Consumer "
    "platforms (Strava's help centre, and similarly Garmin and "
    "TrainingPeaks) document that moving time uses a speed threshold "
    "without publishing the threshold or algorithm -- an unpublished "
    "implementation detail in a commercial product is not a published "
    "work under criterion 15.1, so none of them was treated as a "
    "candidate governing source. The value 0.5 m/s itself is inherited "
    "from fitdocs.ai, the reference application this project borrows its "
    "parsing pipeline and metric formulas from (see aggregates.py); "
    "fitdocs.ai is an application whose source this project read (linked "
    "from README.md), not a published work under criterion 15.1, so it is "
    "not treated as a citable source here either -- fitdocs states its "
    "own reasoning above for retaining the inherited value rather than "
    "crediting fitdocs.ai as the value's origin. No published work "
    "defining a per-sample moving/stopped speed threshold was located in "
    "this search. This was a web literature search, not an exhaustive "
    "survey of the sports-science and geodesy literature -- it did not "
    "reach paywalled full texts beyond abstracts and open-access "
    "articles, so it establishes that no such work is readily locatable, "
    "not that none exists.",
)

ALTITUDE_WINDOW_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="altitude_window_choice",
    justification="10 is a value fitdocs inherits from fitdocs.ai, the "
    "reference application this project's parsing pipeline and metric "
    "formulas otherwise borrow directly (see aggregates.py); fitdocs took "
    "no measurement of its own to arrive at it, and states here its own "
    "reasoning for retaining the inherited value rather than presenting "
    "the number as originated in this layer. A 10-sample trailing boxcar "
    "is wide enough to average out single-sample altimeter or barometric "
    "jitter before differencing for elevation gain and loss, while "
    "staying short enough, relative to a real sustained climb spanning "
    "many samples, that the climb itself is not smoothed away. That "
    "reasoning is why fitdocs keeps the inherited value rather than "
    "replacing it: it is a judgment call trading jitter suppression "
    "against climb fidelity, not a value either fitdocs.ai or this layer "
    "read off measured altitude data.",
    search_basis="A web literature search was run for a published "
    "altitude-smoothing window width, using the queries 'barometric "
    "altimetry filtering elevation gain computation moving average "
    "window samples validation study' and 'elevation gain calculation "
    "barometric altimeter smoothing window size algorithm published "
    "threshold'. The barometric-altimetry filtering literature "
    "characterises altimeter noise (Allan-variance style) and "
    "recommends simple exponential recursive filters rather than a "
    "fixed-width boxcar; window widths that do appear are incidental to "
    "other purposes and disagree with one another and with 10 -- a "
    "21-point median/moving-average in one patent's filter chain, a "
    "4-point moving average used before ARMA identification. "
    "Elevation-gain computation as shipped by a consumer platform "
    "(Strava) instead publishes an amplitude threshold -- a climb must "
    "be sustained over roughly 2 m (barometric) or 10 m "
    "(non-barometric) before it counts -- a different mechanism "
    "(thresholding accumulated amplitude) from smoothing the altitude "
    "series before differencing, not a window width. Patents describe "
    "smoothing/threshold schemes for altitude without fixing a "
    "sample-count window; several fuse barometric with GPS altitude, "
    "which fitdocs does not do. The value 10 itself is inherited from "
    "fitdocs.ai, the reference application this project borrows its "
    "parsing pipeline and metric formulas from (see aggregates.py); "
    "fitdocs.ai is an application whose source this project read (linked "
    "from README.md), not a published work under criterion 15.1, so it is "
    "not treated as a citable source here either -- fitdocs states its "
    "own reasoning above for retaining the inherited value rather than "
    "crediting fitdocs.ai as the value's origin. No published work "
    "defining an altitude-smoothing window width was located in this "
    "search. This was a web literature search, not an exhaustive survey "
    "of the barometric-altimetry and geodesy literature -- it did not "
    "reach paywalled full texts beyond abstracts and open-access "
    "articles, so it establishes that no such work is readily locatable, "
    "not that none exists.",
)

# --- power_absent_sample_choice: REMOVED (chore/power-absent-sample-fill,
#     2026-07-30 ruling) -----------------------------------------------------
#
# Task 12.2 recorded ``POWER_ABSENT_SAMPLE_CHOICE`` / ``POWER_ABSENT_SAMPLE_
# FILL`` (a ``FitdocsChoice`` of ``0.0``) here for the 1 Hz power resample's
# fill value on an unrecorded (``None``) power sample. The maintainer's
# 2026-07-30 ruling on
# ``.kiro/queue/2026-07-30-absent-power-sample-filled-with-zero.md``
# established two things in sequence:
#
# 1. An unrecorded power sample is a genuine device dropout, not a recorded
#    coasting zero -- ``fitdocs.ingest.records._int_channel`` returns a
#    present ``0`` verbatim for a rider who coasts, and ``None`` only when
#    the FIT record carries no power field at all -- so
#    :func:`fitdocs.metrics.power._resample_power_1hz` now forward-fills a
#    dropout as the most recently RECORDED power value rather than
#    fabricating ``0.0``, matching CLAUDE.md's absolute hard rule (absent
#    data is ``None``, never a fabricated ``0`` or default).
# 2. The one site that first ruling still left fabricating ``0.0`` -- the
#    dead air before the very first recorded power sample -- does not need
#    a fabricated value either: the resample grid can simply start where the
#    real data starts. Truncating a leading dropout preserves every later
#    rolling-window's width (nothing "shrinks" -- the omitted alternative
#    task 12.2 and the first half of this ruling both rejected was omitting
#    samples FROM AN OTHERWISE-CONTINUOUS grid, which does change window
#    membership; dropping samples that were never going to be forward-filled
#    from anyway does not) and reports a genuine ride's NP instead of
#    discarding it, or computing it from a fabricated segment.
#
# With both sites resolved, there is no remaining fill value for this record
# to govern, and no dead ``CitedConstant`` is kept around to look like it
# still does: ``POWER_ABSENT_SAMPLE_CHOICE`` and ``POWER_ABSENT_SAMPLE_FILL``
# are removed together, along with their whole-value backstops in
# ``tests/metrics/test_sources.py`` and the sourced-constant entry in
# ``tests/metrics/test_constant_guard.py``. This module is back to the three
# ``FitdocsChoice`` records task 9.2 originally added.


# --- CitedConstant bindings (task 9.3; Req 15.3, 15.6, 16.2) ----------------
#
# Every value Req 15.6's enumeration names, bound to exactly one governing
# source above. The training-impulse coefficient and exponent are each
# instantiated once per fitted curve the weighting selection offers (male,
# female) -- four bindings, not two -- because the ``weighting_for`` resolver
# below (task 9.4) may return either curve and every term a ``WeightingPair``
# holds is already present in ``CONSTANT_SOURCES``. None of the ten values below
# differs from what ``stress.py``, ``power.py`` and ``aggregates.py`` already
# ship, so every ``previous_value`` is ``None``.

BANISTER_MALE_COEFFICIENT: Final[CitedConstant[float]] = CitedConstant(
    name="trimp_coefficient_banister_male",
    value=0.64,
    source=BANISTER_1991,
    corroborators=(
        Corroboration(
            citation=MORTON_1990,
            locator="Eq. 2, p. 1172",
            agreement=Agreement.OMITS,
            note="Morton (1990) Eq. 2 p. 1172 gives 'Y = e^bx' for both sexes "
            "with no multiplicative coefficient anywhere in the equation or "
            "the paragraph introducing it -- confirmed by reading the page, "
            "not merely its absence from a summary. The coefficient 0.64 "
            "rests on Banister (1991) p. 408 alone; Morton (1990) simply "
            "does not state one, for either sex.",
        ),
    ),
)
"""The male curve's coefficient (B91 p. 408: ``y = 0.64e^1.92x``)."""

BANISTER_MALE_EXPONENT: Final[CitedConstant[float]] = CitedConstant(
    name="trimp_exponent_banister_male",
    value=1.92,
    source=BANISTER_1991,
    corroborators=(
        Corroboration(
            citation=MORTON_1990,
            locator="Eq. 2, p. 1172",
            agreement=Agreement.AGREES,
            note="Morton (1990) Eq. 2 p. 1172 states 'b values for men "
            "(1.92) and women (1.67)', matching Banister (1991) p. 408's "
            "male exponent exactly.",
        ),
    ),
)
"""The male curve's exponent (B91 p. 408: ``y = 0.64e^1.92x``)."""

BANISTER_FEMALE_COEFFICIENT: Final[CitedConstant[float]] = CitedConstant(
    name="trimp_coefficient_banister_female",
    value=0.86,
    source=BANISTER_1991,
    corroborators=(
        Corroboration(
            citation=MORTON_1990,
            locator="Eq. 2, p. 1172",
            agreement=Agreement.OMITS,
            note="Morton (1990) Eq. 2 p. 1172 gives 'Y = e^bx' for both sexes "
            "with no multiplicative coefficient anywhere in the equation or "
            "the paragraph introducing it -- confirmed by reading the page, "
            "not merely its absence from a summary. The coefficient 0.86 "
            "rests on Banister (1991) p. 408 alone; Morton (1990) simply "
            "does not state one, for either sex.",
        ),
    ),
)
"""The female curve's coefficient (B91 p. 408: ``y = 0.86e^1.67x``)."""

BANISTER_FEMALE_EXPONENT: Final[CitedConstant[float]] = CitedConstant(
    name="trimp_exponent_banister_female",
    value=1.67,
    source=BANISTER_1991,
    corroborators=(
        Corroboration(
            citation=MORTON_1990,
            locator="Eq. 2, p. 1172",
            agreement=Agreement.AGREES,
            note="Morton (1990) Eq. 2 p. 1172 states 'b values for men "
            "(1.92) and women (1.67)', matching Banister (1991) p. 408's "
            "female exponent exactly.",
        ),
    ),
)
"""The female curve's exponent (B91 p. 408: ``y = 0.86e^1.67x``)."""

TSS_SCALE: Final[CitedConstant[float]] = CitedConstant(
    name="tss_scale",
    value=100.0,
    source=COGGAN_2003,
)
"""The percentage scale so one hour at FTP yields a TSS of exactly 100
(COGGAN_2003 step 8, p. 10: 'multiply by 100 to obtain the final TSS')."""

NP_ROLLING_WINDOW_S: Final[CitedConstant[int]] = CitedConstant(
    name="np_rolling_window_s",
    value=30,
    source=COGGAN_2003,
)
"""The normalized-power rolling-mean window width in seconds (COGGAN_2003
step 1, p. 10: 'starting at 30 s, calculate a 30 second rolling average for
power')."""

NP_AVERAGING_EXPONENT: Final[CitedConstant[int]] = CitedConstant(
    name="np_averaging_exponent",
    value=4,
    source=COGGAN_2003,
)
"""The normalized-power fourth-power/fourth-root averaging exponent
(COGGAN_2003 steps 2-4, p. 10; rounded from 3.90 to 4.00 'for simplicity's
sake' on p. 9)."""

NP_MIN_SPAN_S: Final[CitedConstant[float]] = CitedConstant(
    name="np_min_span_s",
    value=30.0,
    source=NP_MIN_SPAN_CHOICE,
)
"""The minimum power-stream span below which normalized power is refused --
fitdocs' own choice (NP_MIN_SPAN_CHOICE), equal to the rolling-window width
COGGAN_2003 itself governs but not itself read from that text."""

MOVING_SPEED_THRESHOLD_MPS: Final[CitedConstant[float]] = CitedConstant(
    name="moving_speed_threshold_mps",
    value=0.5,
    source=MOVING_THRESHOLD_CHOICE,
)
"""The moving-time movement threshold in m/s -- fitdocs' own choice
(MOVING_THRESHOLD_CHOICE), inherited from fitdocs.ai."""

ALTITUDE_SMOOTHING_WINDOW: Final[CitedConstant[int]] = CitedConstant(
    name="altitude_smoothing_window",
    value=10,
    source=ALTITUDE_WINDOW_CHOICE,
)
"""The altitude-smoothing boxcar width in samples -- fitdocs' own choice
(ALTITUDE_WINDOW_CHOICE), inherited from fitdocs.ai."""

CONSTANT_SOURCES: Final[tuple[CitedConstant[int] | CitedConstant[float], ...]] = (
    BANISTER_MALE_COEFFICIENT,
    BANISTER_MALE_EXPONENT,
    BANISTER_FEMALE_COEFFICIENT,
    BANISTER_FEMALE_EXPONENT,
    TSS_SCALE,
    NP_ROLLING_WINDOW_S,
    NP_AVERAGING_EXPONENT,
    NP_MIN_SPAN_S,
    MOVING_SPEED_THRESHOLD_MPS,
    ALTITUDE_SMOOTHING_WINDOW,
)
"""Every value Req 15.6's enumeration names, ten in all (the training-impulse
coefficient and exponent instantiated once per fitted curve). Names are
unique; importing this module computes nothing (16.6)."""


# --- Weighting resolver (task 9.4; Req 16.5, 17.1, 17.2, 17.4) --------------
#
# WEIGHTING_PAIRS keys the two fitted curves above by the TrimpWeighting
# selection each belongs to, reusing the four BANISTER_* CitedConstant
# bindings by identity. weighting_for is total over TrimpWeighting | None;
# DEPARTURES records the three deliberate behavioral departures this
# amendment's weighting makes from what the cited primary texts specify.
# This does NOT wire the resolver into stress.trimp -- that threading is
# task 11, not this one.


@dataclass(frozen=True)
class WeightingPair:
    """One fitted training-impulse weighting curve: a selection paired with
    its own governing coefficient and exponent (Req 17.1, 17.2).

    ``coefficient`` and ``exponent`` are the exact :class:`~fitdocs.citation.
    CitedConstant` objects registered in :data:`CONSTANT_SOURCES` above, not
    fresh, equal-looking copies -- every term a ``WeightingPair`` holds also
    appears in the registry (design.md's own invariant)."""

    selection: TrimpWeighting
    coefficient: CitedConstant[float]
    exponent: CitedConstant[float]


WEIGHTING_PAIRS: Final[Mapping[TrimpWeighting, WeightingPair]] = {
    TrimpWeighting.BANISTER_MALE: WeightingPair(
        selection=TrimpWeighting.BANISTER_MALE,
        coefficient=BANISTER_MALE_COEFFICIENT,
        exponent=BANISTER_MALE_EXPONENT,
    ),
    TrimpWeighting.BANISTER_FEMALE: WeightingPair(
        selection=TrimpWeighting.BANISTER_FEMALE,
        coefficient=BANISTER_FEMALE_COEFFICIENT,
        exponent=BANISTER_FEMALE_EXPONENT,
    ),
}
"""Every :class:`TrimpWeighting` member mapped to its own fitted curve
(Req 17.1). Keys are exactly the enum's members -- both texts (B91 p. 408,
M90 Eq. 2 p. 1172) define the weighting per sex, so no third pair exists."""

DEFAULT_TRIMP_WEIGHTING: Final[TrimpWeighting] = TrimpWeighting.BANISTER_MALE
"""The selection ``weighting_for`` resolves to when the caller states none
(Req 17.2). This is a *consequence* of 17.2, not a preference: 17.2 pins the
no-selection default to the pair fitdocs applied before this amendment --
Banister's male curve, (0.64, 1.92) -- which ``stress.py`` held as its own
``_TRIMP_COEFFICIENT``/``_TRIMP_EXPONENT`` module constants before task 11
removed both in favor of the caller-resolved ``weighting`` parameter
:func:`fitdocs.metrics.stress.trimp` takes today; the pre-amendment value is
pinned today by value alone in ``tests/metrics/test_sources.py::
test_default_trimp_weighting_resolves_to_the_pre_amendment_stress_py_values``
(standalone ``== 0.64`` / ``== 1.92`` equalities) -- see ``DEPARTURES``'s
``trimp-weighting-sex-neutral-default`` entry for why that is a deliberate
departure rather than an incidental one."""


def weighting_for(selection: TrimpWeighting | None) -> WeightingPair:
    """Resolve a caller's weighting selection to its fitted curve.

    ``None`` resolves to :data:`DEFAULT_TRIMP_WEIGHTING` (Req 17.2). A
    recognized selection resolves to its own registered :class:`WeightingPair`
    (Req 17.1). Any other value -- including a plain ``str`` that matches no
    defined selection's value, reachable because :class:`TrimpWeighting` is a
    ``StrEnum`` and a caller is not statically bound to pass an actual enum
    member -- raises :class:`ValueError` naming the rejected selection and
    every selection the source defines, rather than silently substituting a
    pair (Req 17.4). Total over every reachable input: never returns without
    either a registered pair or this exception.
    """
    resolved = selection if selection is not None else DEFAULT_TRIMP_WEIGHTING
    try:
        return WEIGHTING_PAIRS[TrimpWeighting(resolved)]
    except (KeyError, ValueError):
        defined = ", ".join(member.value for member in TrimpWeighting)
        raise ValueError(
            f"Unrecognized training-impulse weighting selection {resolved!r}; "
            f"the source defines: {defined}"
        ) from None


DEPARTURES: Final[tuple[Departure, ...]] = (
    Departure(
        subject="trimp-weighting-sex-neutral-default",
        source_specifies=(
            "Banister (1991) p. 408 and Morton (1990) Eq. 2 p. 1172 both define "
            "the training-impulse weighting per sex -- Banister as a distinct "
            "coefficient and exponent pair per sex (0.64/1.92 male, 0.86/1.67 "
            "female), Morton as a distinct exponent per sex (b = 1.92 men, "
            "1.67 women) with no coefficient in either."
        ),
        fitdocs_does=(
            "fitdocs applies the BANISTER_MALE weighting pair to every athlete "
            "who supplies no weighting selection (Req 17.2), regardless of that "
            "athlete's sex."
        ),
        reason=(
            "Req 17.2 pins the no-selection default to the exact pair fitdocs "
            "computed with before this amendment -- stress.py's coefficient "
            "(0.64) and exponent (1.92), which are Banister's male curve -- so "
            "that no athlete's TRIMP changes by default when Amendment 1 lands; "
            "sex-neutrality is a stability guarantee for existing callers, not "
            "a claim that the male curve fits every athlete."
        ),
    ),
    Departure(
        subject="trimp-per-sample-integration",
        source_specifies=(
            "Both Banister (1991) p. 408 and Morton (1990) p. 1172 sum the "
            "training-impulse weighting over segments of near-constant "
            "heart rate, each segment contributing its own average heart rate "
            "to the sum."
        ),
        fitdocs_does=(
            "fitdocs integrates every consecutive sample pair in the "
            "heart-rate channel, applying the weighting to each pair's own "
            "duration and heart-rate reserve."
        ),
        reason=(
            "Per-sample-pair integration is the segment sum of the cited "
            "texts in the limit of segment width shrinking to one sample "
            "interval. It is not numerically identical to the texts' segment "
            "form: x*e^(1.92x) is convex on [0, 1], so by Jensen's "
            "inequality the per-sample sum is systematically greater than or "
            "equal to the segment-mean form whenever heart rate varies "
            "within a segment, and equal only when it does not. fitdocs "
            "takes the sample series the file records rather than "
            "reconstructing the texts' steady-state segments."
        ),
    ),
    Departure(
        subject="trimp-coefficient-over-morton",
        source_specifies=(
            "Morton (1990) Eq. 2 p. 1172 prints the training-impulse weighting "
            "as 'Y = e^bx' -- a bare exponential with no multiplicative "
            "coefficient anywhere in the equation or the paragraph introducing "
            "it."
        ),
        fitdocs_does=(
            "fitdocs ships Banister (1991) p. 408's multiplicative coefficient "
            "(0.64 for the male curve, 0.86 for the female curve) rather than "
            "Morton's uncoefficiented form, per the maintainer's 2026-07-27 "
            "ruling and Morton's own worked example."
        ),
        reason=(
            "The maintainer ruled on 2026-07-27 to keep Banister's coefficient "
            "because Morton's own worked example in the same paper implies a "
            "coefficient its printed equation omits, so a bare 'Y = e^bx' with "
            "no coefficient at all would compute a training-impulse value "
            "inconsistent with the ~125-trimp figure Morton's own worked "
            "example illustrates -- an inference from that one example, "
            "whose HR_max and HR_rest the paper leaves unstated, rather than "
            "a statement in either text."
        ),
    ),
)
"""The three deliberate departures this amendment's weighting behavior makes
from what the cited primary texts specify (Req 16.5). Subjects are unique.
Not where the NP rolling-window start condition lands -- that divergence
was removed in task 13.1, not recorded here (design.md)."""
