"""Every source, every constant, and the two blocked sets this feature reads
its numbers through (design: PerformanceSources; Req 2.9, 3.7, 4.8, 8.1, 8.2,
8.4, 8.5, 8.6, 8.8, 9.8).

This module holds **no arithmetic** -- the ``citation.py`` / ``channels.
sources`` / ``metrics.sources`` convention -- and imports only the shared
citation vocabulary (:mod:`fitdocs.citation`), the closed method vocabulary
1.1 published (:mod:`fitdocs.performance.types`), and the standard library.
It never imports ``fitdocs.load.channels.sources``: the comparison this
module's Coggan record needs against the shipped channels-layer Coggan
record (design's "Validation" note; 8.8) is a test-only concern, proved in
``tests/performance/test_sources.py``, which is the only place that import is
permitted (design.md's own statement of this rule, "PerformanceSources"
section, Validation note: "The test imports both; only the *test* may.").

**Six citations.** :data:`RIEGEL_1981` (the race-equivalence exponent and its
two validity-window bounds), :data:`DRAKE_2024` (a corroborator of the
exponent), :data:`MCGEHEE_2005` and :data:`DUMKE_2006` (corroborators of the
LTHR duration window), :data:`COGGAN_2003` (the FTP definition window's
governing source -- the same work already shipping as ``COGGAN_TSS`` in
``fitdocs.load.channels.sources``, identified here by identical authors, year
and work, carrying its own locator into the FTP-definition section of the
same manuscript rather than the TSS section that record cites), and
:data:`BORSZCZ_2018` (a corroborator carrying the measured limits of
agreement Req 4.8 asks a derived FTP entry's provenance to state).

**Honesty on what was actually read.** Of the six, only :data:`COGGAN_2003`
rests on primary text obtained and read in this package (the manuscript was
fetched by this session and its printed page 4 read, confirming the
FTP-definition sentence quoted in the record's own locator). Riegel's 1981
*American Scientist* text is JSTOR-only and has not been read. None of
:data:`DRAKE_2024`, :data:`MCGEHEE_2005`, :data:`DUMKE_2006` or
:data:`BORSZCZ_2018` has been read either -- each is recorded honestly as
:attr:`~fitdocs.citation.VerificationStatus.SECONDARY_ATTESTATION`, whether
or not it *governs* a constant (none of the four does; each appears only as
a :class:`~fitdocs.citation.Corroboration`). Design's PerformanceSources
names :data:`BLOCKED_CITATIONS` as every citation this module carries under
``SECONDARY_ATTESTATION``, governing or not, so all five unread citations --
``riegel_1981`` plus the four corroborators -- are named there as tracked,
non-silent exceptions (Req 8.4), each carrying its own note on what reading
would resolve it.

**Five fitdocs-choice records.** :data:`RIEGEL_SOLVE_TARGET_CHOICE` (the
one-hour solve target, Req 2.9), :data:`LTHR_DURATION_WINDOW_CHOICE` (the
sustained-effort duration window, governing both
:data:`LTHR_MIN_DURATION_S` and :data:`LTHR_MAX_DURATION_S`),
:data:`EFFORT_SPAN_TOLERANCE_CHOICE` (the effort-span tolerance),
:data:`FTP_SHORT_PROTOCOL_FLOOR_CHOICE` (the short-protocol routing floor),
and :data:`ROUNDING_HALF_OFFSET_CHOICE` (the rounding offset). None of the
five rests on a measurement fitdocs itself took, so ``measurement`` is
``None`` on all five.

**Eleven shipped constants,** each a :class:`~fitdocs.citation.CitedConstant`
bound to exactly one governing record, collected into
:data:`CONSTANT_SOURCES` -- see the design's own constant table
(design.md "PerformanceSources", the eleven-row table). The rounding offset
(``ROUNDING_HALF_OFFSET``) is among them: it is a cited constant whose
governing record is a :class:`~fitdocs.citation.FitdocsChoice`
(:data:`ROUNDING_HALF_OFFSET_CHOICE`), exactly like
:data:`RIEGEL_SOLVE_TARGET_S`, so the ``0.5`` the arithmetic module (task
1.3) reaches for is bound through a record rather than standing as a bare
literal its numeric-literal guard cannot classify (8.1, 8.3).

**One departure.** The coaching "final 20 of 30 minutes" protocol -- discard
the leading 10 minutes of a 30-minute time trial, average heart rate over the
remaining 20 -- is recorded in :data:`DEPARTURES` and is **not** implemented:
its 10-minute discard is unsourced, and both :data:`MCGEHEE_2005` and
:data:`DUMKE_2006` used the whole-effort average rather than a
partial-discard window.

**Two blocked sets.** :data:`BLOCKED_CITATIONS` names every citation this
module carries under ``SECONDARY_ATTESTATION`` -- governing or corroborator
-- as a tracked, non-silent exception (Req 8.4) -- today all five:
``riegel_1981``, ``drake_2024``, ``mcgehee_2005``, ``dumke_2006`` and
``borszcz_2018``. :data:`PENDING_CONSTANTS` names a constant that **may not be
written** because its locator is unverified -- today exactly one: the Allen &
Coggan 20-minute power-scaling factor. No numeric value for it appears
anywhere in this module -- not as a literal, not inside a note, not inside a
docstring (Req 8.5). :data:`BLOCKED_METHODS` names the
:class:`~fitdocs.performance.types.DerivationMethod` members that decline at
runtime because they depend on a pending constant --
``TWENTY_MINUTE_POWER_FACTOR`` today.
"""

from __future__ import annotations

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
from fitdocs.performance.types import DerivationMethod

# --- Citations (Req 8.1, 8.2, 8.4, 8.6, 8.8) ---------------------------------

RIEGEL_1981: Final[Citation] = Citation(
    key="riegel_1981",
    authors="Riegel, P.S.",
    year=1981,
    work="Athletic Records and Human Endurance, American Scientist 69(3):285-290",
    locator="JSTOR-only text; not read by this project. The 1.06 running "
    "exponent is attested by peer-reviewed downstream literature (Drake et "
    "al. (2024), which corroborates the exponent only), and the roughly "
    "3.5-minute to 3.83-hour validity window over which it was fitted is "
    "attested by this feature's own discovery viability check (2026-09-09), "
    'as recorded in .kiro/specs/performance-benchmarks/brief.md ("valid '
    'for efforts of 3.5-230 minutes"; research.md documents the same '
    "viability check without restating the window's own numbers), rather "
    "than either bound being read from Riegel's own pages.",
    verification=VerificationStatus.SECONDARY_ATTESTATION,
    note="Governs the race-equivalence exponent (RIEGEL_EXPONENT, 1.06) and "
    "both of its validity-window bounds (RIEGEL_MIN_DURATION_S, "
    "RIEGEL_MAX_DURATION_S). Not itself an equivalence-to-one-hour "
    "computation: Riegel's law relates the predicted times of *any* two "
    "distances through the same exponent, and solving it for the distance "
    "whose predicted time is exactly one hour is fitdocs' own further step, "
    "recorded separately at RIEGEL_SOLVE_TARGET_CHOICE (Req 2.9), not read "
    "from this citation. This record is named in BLOCKED_CITATIONS because "
    "the 1981 American Scientist text itself has never been opened in any "
    "session that produced this package -- the JSTOR paywall was not "
    "crossed -- and its exponent is instead attested here through Drake et "
    "al. (2024), a peer-reviewed corroborator that attests "
    "the same 1.06 value.",
)

DRAKE_2024: Final[Citation] = Citation(
    key="drake_2024",
    authors="Drake, K.M., Finke, A.J., Ferguson, R.A.",
    year=2024,
    work="European Journal of Applied Physiology 124:507-526",
    locator=None,
    verification=VerificationStatus.SECONDARY_ATTESTATION,
    note="Not read by this project; recorded here as a corroborator of the "
    "Riegel (1981) race-equivalence exponent from the bibliographic "
    "description carried in this feature's own research record "
    "(.kiro/specs/performance-benchmarks/research.md), not from an "
    "independent opening of the paper's own text. Corroborates the exponent "
    "only -- it governs nothing in this module. What would resolve this: "
    "obtaining European Journal of Applied Physiology 124:507-526 and "
    "reading its own stated review of Riegel's exponent against Riegel's "
    "original text.",
)

MCGEHEE_2005: Final[Citation] = Citation(
    key="mcgehee_2005",
    authors="McGehee, J.C., Tanner, C.J., Houmard, J.A.",
    year=2005,
    work="A comparison of methods for estimating the lactate threshold, "
    "Journal of Strength and Conditioning Research 19(3):553-558",
    locator=None,
    verification=VerificationStatus.SECONDARY_ATTESTATION,
    note="Not read by this project; recorded here as a corroborator of the "
    "sustained-effort duration window (LTHR_MIN_DURATION_S, "
    "LTHR_MAX_DURATION_S) from the bibliographic description carried in "
    "this feature's own research record, not from an independent opening "
    "of the paper's own text. Reports a 30-minute time-trial protocol "
    "comparing mean heart rate to heart rate at the 4 mmol/L lactate "
    "threshold; corroborates the window only -- it does not itself state a "
    "window and governs nothing in this module. What would resolve this: "
    "obtaining Journal of Strength and Conditioning Research 19(3):553-558 "
    "and reading its own stated protocol duration and heart-rate "
    "comparison method.",
)

DUMKE_2006: Final[Citation] = Citation(
    key="dumke_2006",
    authors="Dumke, C.L., et al.",
    year=2006,
    work="Journal of Strength and Conditioning Research 20(3):601-607",
    locator=None,
    verification=VerificationStatus.SECONDARY_ATTESTATION,
    note="Not read by this project; recorded here as a corroborator of the "
    "sustained-effort duration window (LTHR_MIN_DURATION_S, "
    "LTHR_MAX_DURATION_S) from the bibliographic description carried in "
    "this feature's own research record, not from an independent opening "
    "of the paper's own text. Reports a 60-minute time-trial protocol "
    "comparing heart rate to heart rate at the lactate threshold; "
    "corroborates the window only -- it does not itself state a window and "
    "governs nothing in this module. What would resolve this: obtaining "
    "Journal of Strength and Conditioning Research 20(3):601-607 and "
    "reading its own stated protocol duration and heart-rate comparison "
    "method.",
)

COGGAN_2003: Final[Citation] = Citation(
    key="performance_coggan_2003",
    authors="Coggan, A.R.",
    year=2003,
    work="Training and racing using a power meter: an introduction (USA "
    "Cycling coaching-education chapter; the basis for, and later folded "
    'into, Allen & Coggan\'s "Training and Racing with a Power Meter")',
    locator='§2 "Power-based training levels", run-in heading '
    '"Determination of LT power:", the paragraph beginning "Given the '
    'limitations of laboratory testing as discussed above" (the sentence '
    "\"probably the easiest and most direct way of estimating a rider's "
    "functional threshold power is therefore to simply measure their "
    'average power during a ~40 km (50-70 min) TT"), printed page 4 (PDF '
    "page 5) of the revised 25 March 2003 edition -- not the TSS section "
    "(the channels-layer citation of this same manuscript, COGGAN_TSS in "
    "fitdocs.load.channels.sources, cites a different section). No "
    '"Threshold power" subheading exists in this manuscript.',
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Identifies the same manuscript already shipping as COGGAN_TSS in "
    "fitdocs.load.channels.sources -- same authors, same year, same work. "
    "This session fetched the manuscript itself (the URL carried in "
    "COGGAN_TSS's own note, fitdocs.load.channels.sources) into the "
    "scratchpad and read printed page 4, confirming the FTP-definition "
    "sentence quoted in the locator above sits under the "
    '"Determination of LT power:" run-in heading in §2, not in a '
    '"Threshold power" subheading of §3 as an earlier, unverified draft of '
    "this record claimed. The same paragraph also states a distinct "
    "20 km time-trial correction factor for a shortened protocol -- that "
    "factor is NOT the 20-minute-test scaling factor Allen & Coggan's "
    "later book defines (see PENDING_CONSTANTS below) and is not itself "
    "bound to any constant in this module. The Allen & Coggan book this "
    "manuscript was folded into, which would govern the separate "
    "20-minute-test factor, was never obtained -- see PENDING_CONSTANTS.",
)

BORSZCZ_2018: Final[Citation] = Citation(
    key="borszcz_2018",
    authors="Borszcz, F.K., et al.",
    year=2018,
    work="International Journal of Sports Medicine 39(10):737-742",
    locator=None,
    verification=VerificationStatus.SECONDARY_ATTESTATION,
    note="Not read by this project; recorded here as a corroborator of the "
    "20-minute functional-threshold-power protocol from the bibliographic "
    "description carried in this feature's own research record, not from "
    "an independent opening of the paper's own text. Reports measured "
    "limits of agreement of roughly plus-or-minus 40 W between the "
    "20-minute-test estimate and a directly measured FTP -- the figure "
    "Req 4.8 asks a derived FTP entry's provenance to carry alongside the "
    "value. Corroborates the protocol's measured uncertainty only; it "
    "neither governs the FTP-definition window nor the pending 20-minute "
    "power-scaling factor, and states no locator for that factor itself "
    "(its own book locator is what is unverified; see PENDING_CONSTANTS). "
    "What would resolve this: obtaining International Journal of Sports "
    "Medicine 39(10):737-742 and reading its own stated limits of "
    "agreement between the 20-minute-test estimate and directly measured "
    "FTP.",
)


# --- Fitdocs-choice records (Req 8.2) ---------------------------------------

RIEGEL_SOLVE_TARGET_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="riegel_solve_target_choice",
    justification="Riegel (1981) states an equivalence between the "
    "predicted times of any two distances through a single exponent; it "
    "does not itself solve that equation for a distance whose predicted "
    "time is exactly one hour. Choosing the one-hour distance as the "
    "anchor for a threshold-pace derivation is fitdocs' own further step "
    "(Req 2.9), not a value Riegel's text states. 3600 s was chosen "
    "because a one-hour effort is the conventional anchor duration for a "
    "running or cycling threshold in the wider literature this feature "
    "otherwise cites (Coggan's own functional-threshold-power definition "
    "is likewise anchored to what an athlete can sustain for close to an "
    "hour), and because 3600 s lies inside Riegel's own validity window "
    "(210 s-13800 s) with wide margin on both sides, so the solve neither "
    "clamps nor extrapolates beyond the range the exponent was fitted "
    "over.",
    search_basis="This session reviewed Riegel's own validity window as "
    "recorded in this feature's own discovery viability check (2026-09-09; "
    "see RIEGEL_1981 and .kiro/specs/performance-benchmarks/brief.md) for "
    "any stated one-hour solve step; none exists in the "
    "reviewed material -- Riegel's law is stated as a two-distance "
    "equivalence, not as a single-distance threshold model, in every "
    "secondary description available to this session. No published work "
    "performs this solve for an explicit one-hour target; the step "
    "recorded here is fitdocs' own.",
)

LTHR_DURATION_WINDOW_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="lthr_duration_window_choice",
    justification="No published work states a validity window for a "
    "sustained maximal effort's whole-effort mean heart rate as an LTHR "
    "estimate. Two validated protocols are available: McGehee et al. "
    "(2005) at 30 minutes (1800 s) and Dumke et al. (2006) at 60 minutes "
    "(3600 s). This record brackets both validated durations -- 1500 s "
    "(25 minutes) to 4500 s (75 minutes) -- with an asymmetric margin: "
    "300 s (5 minutes) below the 1800 s protocol and 900 s (15 minutes) "
    "above the 3600 s protocol. These are the design's own stated bounds; "
    "no published work or design rationale in hand states why the margin "
    "above the 60-minute protocol is wider than the margin below the "
    "30-minute protocol, so this record states the margins as given rather "
    "than inventing a reason for the asymmetry. Both margins are wide "
    "enough that neither validated protocol sits at the window's own edge, "
    "without extending so far past either that an "
    "effort of a qualitatively different character (a short interval, a "
    "multi-hour long run) would be accepted as if it were a validated "
    "protocol.",
    search_basis="This session reviewed the bibliographic descriptions of "
    "McGehee et al. (2005) and Dumke et al. (2006) carried in this "
    "feature's own research record for any stated duration window "
    "spanning both protocols; neither paper's own description states a "
    "window -- each validates its own single duration. No published work "
    "reviewed states a combined window; the bracket recorded here is "
    "fitdocs' own choice, informed by both durations without being read "
    "from either paper's text.",
)

EFFORT_SPAN_TOLERANCE_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="effort_span_tolerance_choice",
    justification="Where a tag carries an official time, Req 3.6 requires "
    "declining the derivation when the activity's recorded span differs "
    "from that official time by more than a published tolerance -- because "
    "this feature cannot locate the effort inside a longer recording and "
    "locating it is out of scope. 0.05 (5%) was chosen as a tolerance wide "
    "enough to absorb ordinary recording noise (a device started a few "
    "seconds early or stopped a few seconds late relative to the official "
    "time) while remaining narrow enough that a recording covering a "
    "materially longer warm-up, cooldown, or unrelated second effort is "
    "correctly rejected rather than silently averaged over.",
    search_basis="No published work defines a tolerance for matching a "
    "race or test's official time against a device's recorded elapsed "
    "time -- this is a data-quality gate over fitdocs' own re-parsed "
    "archive, not a physiological constant, and no literature search was "
    "run for it on that basis: it is not the kind of value a sports-"
    "science publication would state.",
)

FTP_SHORT_PROTOCOL_FLOOR_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="ftp_short_protocol_floor_choice",
    justification="This is a *routing* floor, not Allen & Coggan's own "
    "20-minute-test number: it is the shortest cycling effort duration for "
    "which this feature will name the blocked short protocol as the reason "
    "a derivation is declined, rather than reporting the vaguer 'outside "
    "every window this feature covers' (Req 4.7). 900 s (15 minutes) was "
    "chosen as comfortably below the 20-minute (1200 s) protocol itself, "
    "so that a genuine 20-minute effort is always routed to the named, "
    "specifically-blocked reason even allowing for a few minutes of "
    "recording variance, while an effort meaningfully shorter than any "
    "known threshold-test protocol (a sprint interval, a short hill "
    "repeat) still falls through to the generic outside-every-window "
    "decline rather than being misrouted to the 20-minute block.",
    search_basis="No published work defines a routing floor for this "
    "purpose -- it is an internal reporting boundary of this feature's own "
    "decline vocabulary, not a physiological constant, and no literature "
    "search was run for it on that basis. It carries no relation to the "
    "unverified 20-minute power-scaling factor itself, which remains "
    "unwritten regardless of where this floor sits.",
)

ROUNDING_HALF_OFFSET_CHOICE: Final[FitdocsChoice] = FitdocsChoice(
    key="rounding_half_offset_choice",
    justification="Python's builtin round() rounds half to even (banker's "
    "rounding), which makes an integer result depend on the parity of the "
    "nearest whole numbers rather than on a fixed direction -- "
    "round(169.5) == 170 (170 is even) and round(170.5) == 170 (170 is "
    "again the even neighbor), so both half-integer inputs land on the "
    "same output despite lying on opposite sides of it. This record "
    "instead chooses round-half-away-from-zero -- "
    "adding 0.5 before flooring for a positive value -- so that every "
    "half-integer result rounds the same direction regardless of parity. "
    "This offset governs both whole beats per minute (a store requirement: "
    "lthr_bpm is an integral kind) and whole watts (not a store "
    "requirement -- ftp_watts accepts a float -- so rounding it is purely "
    "fitdocs' own choice for presentation consistency, and is recorded as "
    "one here rather than left as an unclassified literal).",
    search_basis="No published work defines a rounding convention for "
    "either quantity -- this is fitdocs' own presentation choice over its "
    "own arithmetic output, not a physiological or literature constant, "
    "and no literature search was run for it on that basis.",
)


# --- CitedConstant bindings (Req 8.1, 8.3, 9.8) -----------------------------
#
# Every value the design's constant table names, bound to exactly one
# governing record above. Eleven in all.

RIEGEL_EXPONENT: Final[CitedConstant[float]] = CitedConstant(
    name="riegel_exponent",
    value=1.06,
    source=RIEGEL_1981,
    corroborators=(
        Corroboration(
            citation=DRAKE_2024,
            locator="European Journal of Applied Physiology 124:507-526",
            agreement=Agreement.AGREES,
            note="Reported by this feature's own research record as a "
            "peer-reviewed attestation of the same 1.06 exponent; not "
            "independently re-opened by this session.",
        ),
    ),
)
"""Riegel's race-equivalence exponent."""

RIEGEL_MIN_DURATION_S: Final[CitedConstant[float]] = CitedConstant(
    name="riegel_min_duration_s",
    value=210.0,
    source=RIEGEL_1981,
)
"""The lower bound of Riegel's published validity window, in seconds."""

RIEGEL_MAX_DURATION_S: Final[CitedConstant[float]] = CitedConstant(
    name="riegel_max_duration_s",
    value=13800.0,
    source=RIEGEL_1981,
)
"""The upper bound of Riegel's published validity window, in seconds."""

RIEGEL_SOLVE_TARGET_S: Final[CitedConstant[float]] = CitedConstant(
    name="riegel_solve_target_s",
    value=3600.0,
    source=RIEGEL_SOLVE_TARGET_CHOICE,
)
"""The one-hour distance fitdocs solves Riegel's equivalence for -- fitdocs'
own step (Req 2.9), not a value Riegel's text states."""

LTHR_MIN_DURATION_S: Final[CitedConstant[float]] = CitedConstant(
    name="lthr_min_duration_s",
    value=1500.0,
    source=LTHR_DURATION_WINDOW_CHOICE,
    corroborators=(
        Corroboration(
            citation=MCGEHEE_2005,
            locator="Journal of Strength and Conditioning Research 19(3):553-558",
            agreement=Agreement.OMITS,
            note="Validates a single 30-minute (1800 s) protocol; does not "
            "itself state a duration window, so it informs but does not "
            "state this bound.",
        ),
        Corroboration(
            citation=DUMKE_2006,
            locator="Journal of Strength and Conditioning Research 20(3):601-607",
            agreement=Agreement.OMITS,
            note="Validates a single 60-minute (3600 s) protocol; does not "
            "itself state a duration window, so it informs but does not "
            "state this bound.",
        ),
    ),
)
"""The lower bound of the sustained-effort duration window -- fitdocs' own
choice informed by the two validated protocols, not read from either."""

LTHR_MAX_DURATION_S: Final[CitedConstant[float]] = CitedConstant(
    name="lthr_max_duration_s",
    value=4500.0,
    source=LTHR_DURATION_WINDOW_CHOICE,
    corroborators=(
        Corroboration(
            citation=MCGEHEE_2005,
            locator="Journal of Strength and Conditioning Research 19(3):553-558",
            agreement=Agreement.OMITS,
            note="Validates a single 30-minute (1800 s) protocol; does not "
            "itself state a duration window, so it informs but does not "
            "state this bound.",
        ),
        Corroboration(
            citation=DUMKE_2006,
            locator="Journal of Strength and Conditioning Research 20(3):601-607",
            agreement=Agreement.OMITS,
            note="Validates a single 60-minute (3600 s) protocol; does not "
            "itself state a duration window, so it informs but does not "
            "state this bound.",
        ),
    ),
)
"""The upper bound of the sustained-effort duration window -- fitdocs' own
choice informed by the two validated protocols, not read from either."""

EFFORT_SPAN_TOLERANCE: Final[CitedConstant[float]] = CitedConstant(
    name="effort_span_tolerance",
    value=0.05,
    source=EFFORT_SPAN_TOLERANCE_CHOICE,
)
"""The fractional tolerance between a tag's official time and the activity's
recorded elapsed time, above which the derivation declines (Req 3.6)."""

FTP_DEFINITION_MIN_DURATION_S: Final[CitedConstant[float]] = CitedConstant(
    name="ftp_definition_min_duration_s",
    value=3000.0,
    source=COGGAN_2003,
    corroborators=(
        Corroboration(
            citation=BORSZCZ_2018,
            locator="International Journal of Sports Medicine 39(10):737-742",
            agreement=Agreement.OMITS,
            note="Measures the 20-minute-test protocol's agreement with a "
            "directly measured FTP; does not itself state the "
            "definitional threshold-effort duration window, so it informs "
            "but does not state this bound.",
        ),
    ),
)
"""The lower bound of the duration window the FTP definition itself states
for a threshold effort, in seconds (50 minutes)."""

FTP_DEFINITION_MAX_DURATION_S: Final[CitedConstant[float]] = CitedConstant(
    name="ftp_definition_max_duration_s",
    value=4200.0,
    source=COGGAN_2003,
    corroborators=(
        Corroboration(
            citation=BORSZCZ_2018,
            locator="International Journal of Sports Medicine 39(10):737-742",
            agreement=Agreement.OMITS,
            note="Measures the 20-minute-test protocol's agreement with a "
            "directly measured FTP; does not itself state the "
            "definitional threshold-effort duration window, so it informs "
            "but does not state this bound.",
        ),
    ),
)
"""The upper bound of the duration window the FTP definition itself states
for a threshold effort, in seconds (70 minutes)."""

FTP_SHORT_PROTOCOL_FLOOR_S: Final[CitedConstant[float]] = CitedConstant(
    name="ftp_short_protocol_floor_s",
    value=900.0,
    source=FTP_SHORT_PROTOCOL_FLOOR_CHOICE,
)
"""The routing floor below which a cycling effort is reported as outside
every window this feature covers, rather than as the blocked short
protocol -- not Allen & Coggan's own 20-minute number."""

FTP_LIMITS_OF_AGREEMENT: Final[str] = (
    "Borszcz et al. (2018) reports limits of agreement of roughly "
    "plus-or-minus 40 W between the 20-minute-test protocol's FTP estimate "
    "and a directly measured FTP."
)
"""The short, derived-entry-facing statement of Borszcz et al.'s (2018)
measured limits of agreement (Req 4.8) -- deliberately distinct from
:attr:`BORSZCZ_2018.note`, which carries this module's own citation
bookkeeping (what was and was not read, what would resolve it) and is not
fit for embedding verbatim in an athlete's derived provenance. This is the
string a derived FTP entry's `note` field actually embeds."""

ROUNDING_HALF_OFFSET: Final[CitedConstant[float]] = CitedConstant(
    name="rounding_half_offset",
    value=0.5,
    source=ROUNDING_HALF_OFFSET_CHOICE,
)
"""The round-half-away-from-zero offset the arithmetic module (task 1.3)
reaches through this record rather than through a bare literal -- governs
both whole beats per minute and whole watts."""

CONSTANT_SOURCES: Final[tuple[CitedConstant[float], ...]] = (
    RIEGEL_EXPONENT,
    RIEGEL_MIN_DURATION_S,
    RIEGEL_MAX_DURATION_S,
    RIEGEL_SOLVE_TARGET_S,
    LTHR_MIN_DURATION_S,
    LTHR_MAX_DURATION_S,
    EFFORT_SPAN_TOLERANCE,
    FTP_DEFINITION_MIN_DURATION_S,
    FTP_DEFINITION_MAX_DURATION_S,
    FTP_SHORT_PROTOCOL_FLOOR_S,
    ROUNDING_HALF_OFFSET,
)
"""Every constant the design's table names, eleven in all. Names are unique;
importing this module computes nothing."""


# --- Departures (Req 3.2 by omission -- the coaching protocol not taken) ----

DEPARTURES: Final[tuple[Departure, ...]] = (
    Departure(
        subject="lthr-final-twenty-of-thirty-minutes-protocol",
        source_specifies=(
            "A commonly cited coaching protocol for estimating lactate-"
            "threshold heart rate has the athlete discard the first 10 "
            "minutes of a 30-minute time-trial effort and average heart "
            "rate over only the final 20 minutes."
        ),
        fitdocs_does=(
            "fitdocs computes the time-weighted mean heart rate over the "
            "whole recorded effort (Req 3.2), discarding no leading or "
            "trailing segment."
        ),
        reason=(
            "The 10-minute discard is not sourced to any citation this "
            "module carries with a verified locator -- it is a coaching "
            "convention, not a value read from a published work's own "
            "text -- and both McGehee et al. (2005) and Dumke et al. "
            "(2006), the two validated protocols this feature's duration "
            "window is informed by, used the whole-effort average rather "
            "than a partial-discard window. Departing from the whole-"
            "effort protocol to adopt an unsourced discard would trade a "
            "validated method for an unvalidated one."
        ),
    ),
)
"""The one deliberate departure this module records: the coaching protocol
described above is not implemented. Subjects are unique."""


# --- The two blocked sets (Req 8.4, 8.5) ------------------------------------

BLOCKED_CITATIONS: Final[frozenset[str]] = frozenset(
    {
        "riegel_1981",
        "drake_2024",
        "mcgehee_2005",
        "dumke_2006",
        "borszcz_2018",
    }
)
"""Every citation this module carries under
:attr:`~fitdocs.citation.VerificationStatus.SECONDARY_ATTESTATION`, named as
a tracked, non-silent exception (Req 8.4, design's PerformanceSources)
rather than an accepted terminal state -- today all five: ``riegel_1981``
(the 1981 American Scientist text has not been read; what would resolve it
is obtaining and reading that text past the JSTOR paywall), and the four
corroborators ``drake_2024``, ``mcgehee_2005``, ``dumke_2006`` and
``borszcz_2018`` (each carries its own "what would resolve this" note above
naming the work and reading needed). Design's PerformanceSources states this
set names *every* SECONDARY_ATTESTATION citation the module carries, not
only those that govern a constant -- a corroborator that has not been read
is still a tracked exception, not a silent one."""


@dataclass(frozen=True)
class PendingConstant:
    """A constant that **may not be written** because its locator has not
    been verified against the work itself (Req 8.5). Carries no numeric
    value anywhere -- not as a field, not inside a note -- so that an
    unverified figure cannot leak into this package by way of a record that
    merely describes it."""

    name: str
    suspected_work: str
    suspected_locator: str
    what_would_resolve: str
    blocks: DerivationMethod


PENDING_CONSTANTS: Final[tuple[PendingConstant, ...]] = (
    PendingConstant(
        name="ftp_twenty_minute_power_factor",
        suspected_work="Allen, H., Coggan, A.R. Training and Racing with a "
        "Power Meter, 2nd ed. (VeloPress, 2010)",
        suspected_locator="The chapter defining the 20-minute FTP test "
        "protocol; the specific page has not been confirmed against the "
        "book's own text, which has never been obtained by this project -- "
        "only Coggan's earlier 2003 manuscript (COGGAN_2003) has been "
        "read, and that manuscript does not itself state a 20-minute-test "
        "scaling factor.",
        what_would_resolve="Obtaining the Allen & Coggan book itself and "
        "reading the chapter's own stated factor together with its page "
        "number, so the factor can be bound to a verified locator rather "
        "than a suspected one.",
        blocks=DerivationMethod.TWENTY_MINUTE_POWER_FACTOR,
    ),
)
"""Every constant this feature would need but may not ship because its
locator is unverified -- today exactly one, the Allen & Coggan 20-minute
power factor. No numeric value for it appears anywhere in this module."""

BLOCKED_METHODS: Final[frozenset[DerivationMethod]] = frozenset(
    {DerivationMethod.TWENTY_MINUTE_POWER_FACTOR}
)
"""The :class:`~fitdocs.performance.types.DerivationMethod` members that
decline at runtime because they depend on a constant in
:data:`PENDING_CONSTANTS` -- today exactly ``TWENTY_MINUTE_POWER_FACTOR``,
while every other method in this feature continues to work (Req 8.5)."""
