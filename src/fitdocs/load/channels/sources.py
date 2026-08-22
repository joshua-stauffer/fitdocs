"""The provenance record: every constant this layer introduces points here.

``metrics/stress.py`` shipped a Banister TRIMP formula cited only to
``docs/reference/fitdocs-ai-reference.md`` -- a secondary web source presented
without qualification -- and that exact coefficient string was refuted 0-3 in
adversarial verification. This module exists so that episode cannot repeat
silently (Req 8): every numeric constant elsewhere in this package names one
of the :class:`Citation` records below in its own docstring, and every
intentional divergence from intervals.icu's established behavior is recorded
as a :class:`Divergence`, both as typed, testable artifacts rather than as a
comment convention. This module holds no arithmetic of its own.

**Verification status.** :class:`VerificationStatus` distinguishes a value
*read from the cited work's own text* from one only *attested by consistent
secondary literature* -- exactly the distinction the refuted-coefficient
episode collapsed. It is defined once, in the shared :mod:`fitdocs.citation`
vocabulary, and imported and re-exported here rather than declared locally
(task 8.2, design.md Decision D2), so that every existing
``from fitdocs.load.channels.sources import VerificationStatus`` import path
keeps working unchanged. Its third member, ``FITDOCS_MEASURED``, is carried
in full even though no citation in *this* package carries it: the
``activity-qa-flags`` feature is its only consumer, and widening this enum
after the fact -- or reaching into this package's own test module to add a
case for it -- is exactly the boundary violation this task is written to
prevent. Every citation in this package stays at whatever verification
status its own provenance record below actually earns (none carries
``FITDOCS_MEASURED``), keeping this feature's postconditions unchanged by
the sibling feature's need.

**A named-exception variant of fit-ingest's bar (Req 8.9, 8.10; queue
2026-07-26-citation-vocabulary-diverges-across-layers).** fit-ingest
Requirement 15.4 forbids recording a ``SECONDARY_ATTESTATION`` in place of a
primary-text verification for any constant a published work defines: an
unobtainable primary text blocks that feature's completion rather than
shipping under a weaker status, with no exception set. This layer holds
itself to a variant of that bar, not the identical bar: Req 8.9 forbids a
*new* ``SECONDARY_ATTESTATION`` where a defining work exists, but Req 8.10
lets an unobtainable primary text be recorded as a named, tracked exception
in :data:`BLOCKED_CITATIONS` rather than blocking this feature's completion
the way 15.4 blocks fit-ingest's. That residual difference is a maintainer
decision (queue 2026-07-26-citation-vocabulary-diverges-across-layers), not
an oversight, and is recorded here rather than left to look identical to
15.4. It replaces the weaker one ``channel-citations-unverified`` step 4
originally recommended. All four of this module's former
``SECONDARY_ATTESTATION`` citations have since been re-sourced to
``PRIMARY_TEXT`` -- :data:`COGGAN_TSS`, :data:`MINETTI_2002` and
:data:`INTERVALS_ICU_PACE_LOAD` on 2026-07-27, and :data:`BANISTER_TRIMP` on
2026-07-29 once both Banister (1991) and Morton, Fitz-Clarke & Banister
(1990) were obtained and read in full (queue
2026-07-27-banister-morton-primary-texts-obtained;
``docs/reference/banister-trimp-primary-sources.md``) -- see each citation's
own note for what was read and where. :data:`BLOCKED_CITATIONS` is the
honest remainder: it names every citation that still carries
``SECONDARY_ATTESTATION`` as a tracked, non-silent exception to the new bar,
not an accepted terminal state. That set is empty today -- no citation in
this module currently carries ``SECONDARY_ATTESTATION`` -- and stays defined
rather than removed, because the mechanism it names (a future downgrade
lands only as a named, tracked exception, never silently) is still live.
``test_no_new_secondary_attestation_citations_exist`` in
``tests/load/channels/test_sources.py`` is the enforcement mechanism: any
citation carrying ``SECONDARY_ATTESTATION`` whose key is not in
:data:`BLOCKED_CITATIONS` fails the suite, so a future downgrade cannot land
quietly the way the original four did.

**Divergences.** Where fitdocs' behavior intentionally departs from
intervals.icu's established behavior, the departure is recorded here with its
reason, not left implicit in the arithmetic. :data:`DIVERGENCES` records at
least: running power computed from the watts a device recorded, which
intervals.icu does not ingest natively; a pace formulation that does not
variability-normalize the way an alternative published method does; and the
heart-rate channel's reported *intensity*, where intervals.icu publishes a
heart-rate load definition but no heart-rate intensity definition of its own
-- fitdocs reports the square root of the impulse ratio so that one intensity
semantic (``load == hours x intensity**2 x 100``) spans all three channels.
The heart-rate *load* itself is defined on the scale intervals.icu states for
HRSS -- normalized TRIMP, with 100 corresponding to one hour at max effort --
so the two are directly comparable; only the reported intensity differs. That
is the extent of what the cited source supports. It publishes no HRSS formula,
so numeric identity is deliberately *not* claimed: two implementations of
"normalized TRIMP scaled to 100 = 1h max effort" can differ in the training-
impulse weighting, the smoothing window, the reserve basis or the rounding and
still both answer to that description.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs.citation import Citation as Citation
from fitdocs.citation import VerificationStatus as VerificationStatus

# ``VerificationStatus`` and ``Citation`` are the shared citation vocabulary
# (Amendment 1, task 8.2): this module imports and re-exports them from
# ``fitdocs.citation`` rather than declaring its own (design.md Decision D2).
# The explicit ``as`` aliases above mark both as intentional re-exports, not
# unused imports, under mypy strict's ``no_implicit_reexport`` -- every
# existing ``from fitdocs.load.channels.sources import VerificationStatus``
# (or ``Citation``) import path keeps working unchanged. ``Divergence`` below
# is this module's own type and does not move.


@dataclass(frozen=True)
class Divergence:
    """One place fitdocs intentionally departs from intervals.icu's behavior,
    or, where a recorded contrast is with an alternative published method
    rather than with intervals.icu, states so explicitly.

    Carries no ``key`` field; a consumer names a divergence by its
    :attr:`behavior`, which is asserted unique instead (Req 8.8).
    """

    behavior: str
    intervals_icu: str
    fitdocs: str
    reason: str


COGGAN_TSS: Final[Citation] = Citation(
    key="coggan_tss",
    authors="Coggan, A.R.",
    year=2003,
    work="Training and racing using a power meter: an introduction "
    "(USA Cycling coaching-education chapter; the basis for, and later "
    "folded into, Allen & Coggan's \"Training and Racing with a Power "
    'Meter")',
    locator='§3 "Analysis of power meter data" -> "Intensity '
    'factor (IF) and training stress score (TSS)", pp. 8-11 of the '
    "revised 25 March 2003 edition",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Re-sourced 2026-07-27 (queue "
    "2026-07-26-citation-vocabulary-diverges-across-layers): the book's "
    "own 2nd-edition (2010) text was still not obtained, but Coggan's own "
    "earlier chapter-length manuscript was found and opened in this "
    "session at ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf and is "
    "cited here in its place, since it is Coggan's own primary text "
    "defining the same formulas rather than a secondary summary of the "
    "book. It states NP is computed as: 1) a 30-second rolling average of "
    "power; 2) each value raised to the 4th power; 3) the average of "
    'those values; 4) the 4th root of that average. IF is defined as "the '
    "normalized power obtained in step 4 by the individual's power at "
    'LT". TSS is derived as "exercise duration x average power x a '
    "power-dependent intensity weighting factor\", computed in the text's "
    "own steps 6-8 as normalized work (NP x duration in seconds) x IF, "
    "divided by (threshold power x 3600) x 100 -- i.e. "
    "TSS = duration_s * NP * IF / (FTP * 3600) * 100, matching the "
    "formula this package's power channel already implements. The text "
    'also states the algorithm is derived "by analogy" to Banister\'s '
    "TRIMPS, and cites Banister, Calvert, Savage & Bach (1975) -- a "
    "different, earlier Banister paper than the one this package's "
    "BANISTER_TRIMP citation names -- for that analogy only, not for the "
    "IF/TSS formula itself.",
)

BLOCKED_CITATIONS: Final[frozenset[str]] = frozenset()
"""Citations recorded under ``SECONDARY_ATTESTATION`` as a tracked, named
exception to Req 8.9's new bar (see the module docstring's "A named-exception
variant of fit-ingest's bar" section), rather than as an accepted terminal
state. A
citation's key belongs here only when a published work is known to define
its value and that work's own primary text could not be obtained after a
search recorded on the citation's ``note``. Guarded by
``test_no_new_secondary_attestation_citations_exist`` in
``tests/load/channels/test_sources.py`` -- any ``SECONDARY_ATTESTATION``
citation whose key is absent from this set fails the suite. Empty as of
2026-07-29 (queue 2026-07-27-banister-morton-primary-texts-obtained):
``BANISTER_TRIMP``, the sole citation that ever occupied this set, was
re-sourced to ``PRIMARY_TEXT`` once both Banister (1991) and Morton,
Fitz-Clarke & Banister (1990) were obtained and read in full -- see
``docs/reference/banister-trimp-primary-sources.md``. The frozenset is kept
in place, empty, rather than deleted: it is still the honest record of what
this package's Req 8.9/8.10 exception mechanism holds today (nothing), and
``test_no_new_secondary_attestation_citations_exist`` still fails the suite
the moment a future ``SECONDARY_ATTESTATION`` citation lands outside it."""

BANISTER_TRIMP: Final[Citation] = Citation(
    key="banister_trimp",
    authors="Banister, E.W.",
    year=1991,
    work="Modeling Elite Athletic Performance, in: Physiological Testing "
    "of the High-Performance Athlete (2nd ed.), Human Kinetics",
    locator="p. 408 (weighted training-impulse equation, both sexes); "
    "corroborated by Morton, Fitz-Clarke & Banister (1990) Eq. 2, p. 1172 "
    "(exponents agree; no multiplicative coefficient printed there)",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Re-sourced 2026-07-29 (queue "
    "2026-07-27-banister-morton-primary-texts-obtained): both the book "
    "chapter (Banister 1991, ch. 9, pp. 403-424) and its companion paper "
    "(Morton, Fitz-Clarke & Banister 1990, J Appl Physiol "
    "69(3):1171-1177) were obtained and read in full 2026-07-27, extracted "
    "to docs/reference/banister-trimp-primary-sources.md with page and "
    "equation numbers. Banister (1991) p. 408 states the weighted training "
    'impulse as "y = 0.64e^1.92x (male)" and "y = 0.86e^1.67x (female)", '
    "x the delta-HR-reserve ratio during exercise. Morton et al. (1990) Eq. "
    '2, p. 1172, gives the same construction as "Y = e^bx", with b = 1.92 '
    "for men and 1.67 for women -- the two texts agree exactly on both "
    "exponents and disagree on whether a leading coefficient exists at "
    "all: Morton's printed equation carries none. The maintainer ruled "
    "2026-07-27 to keep Banister's 0.64: it is what Banister's own text "
    "states, and it is what Morton's own worked example (~125 trimps for "
    "1 h at HR 150 bpm, p. 1172) implies once solved for an ordinary "
    "HR_max, which Morton's coefficient-free equation does not (an HR_max "
    "of 210 versus the ordinary 182). No constant moves: metrics/stress.py "
    "already ships 0.64, so no migration-by-regen is owed. fitdocs applies "
    "the male exponent 1.92 to every athlete regardless of sex; both texts "
    "define distinct exponents per sex (1.92 male, 1.67 female), and "
    "Banister additionally carries a per-sex coefficient (0.64 male, 0.86 "
    "female) that Morton's own equation omits entirely, as stated above -- "
    "so fitdocs' sex-neutral application is a confirmed deviation from "
    "both primary texts' sex-specific exponent, not an artifact of either "
    "having been unobtainable. This package's heart-rate channel (not yet "
    "implemented as of this writing; src/fitdocs/load/channels/ today "
    "holds only sources.py and __init__.py) is designed to consume this "
    "same sex-neutral collapsed pair unchanged from metrics.stress.trimp "
    "(Req 8.6): it does not restate the coefficients, it consumes them "
    "from the single place they are already defined. If fit-ingest's own "
    "re-sourcing work makes "
    "the weighting sex-dependent, this feature's weighting seam would need "
    "an athlete-sex input it does not currently have -- design.md's own "
    "risk register, not yet realized. HRSS's ratio form, TRIMP_activity / "
    "TRIMP_one_hour_at_LTHR x 100, carries the 0.64 multiplicative "
    "coefficient in both numerator and denominator, so it cancels exactly "
    "and only the 1.92 exponent survives into that particular result. The "
    "citation's year, 1991, rests on the Internet Archive / OCLC "
    "1150972541 library catalogue record rather than on the book's own "
    "pages -- the scanned copyright page carries a later printing's line "
    "and no year at all. Banister's own worked examples are not usable as "
    "test vectors: all three of his printed figure captions contradict "
    "his own equation (queue "
    "2026-07-27-banister-figure-captions-unusable-as-vectors). Morton's "
    "own worked example likewise does not satisfy Morton's printed Eq. 2 "
    "-- which is why it is evidence for the coefficient, not a test "
    "vector; its HR_max and HR_rest are unstated. Full extraction, "
    "discrepancies and page/equation numbers: "
    "docs/reference/banister-trimp-primary-sources.md.",
)

MINETTI_2002: Final[Citation] = Citation(
    key="minetti_2002",
    authors="Minetti, A.E., Moia, C., Roi, G.S., Susta, D. & Ferretti, G.",
    year=2002,
    work="Energy cost of walking and running at extreme uphill and downhill slopes",
    locator="Journal of Applied Physiology, 93(3), 1039-1046, Fig. 1 caption (p. 1041)",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Re-sourced 2026-07-27 (queue "
    "2026-07-26-citation-vocabulary-diverges-across-layers): the paper's "
    "own text was obtained and read in this session (open-access PDF "
    "mirror at runscribe.com/wp-content/uploads/power/Minetti2002.pdf, "
    "matching the publisher's own pagination and figures). Fig. 1's "
    "caption gives both 5th-order polynomial regressions as fitted to "
    "the paper's own data, gradient i in the range investigated "
    "(R^2 = 0.999 for both): "
    "Cw(i) = 280.5*i^5 - 58.7*i^4 - 76.8*i^3 + 51.9*i^2 + 19.6*i + 2.5 "
    "(walking) and "
    "Cr(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6 "
    "(running), both in J*kg^-1*m^-1. The paper's walking form was read "
    "alongside the running form -- both appear in the same Fig. 1 caption "
    "-- but is still not implemented; this feature's grade adjustment "
    "remains defined for running only, a scope decision independent of "
    "sourcing.",
)

INTERVALS_ICU_PACE_LOAD: Final[Citation] = Citation(
    key="intervals_icu_pace_load",
    authors="intervals.icu",
    year=2021,
    work="Pace-based training load (gradient-adjusted pace) announcement",
    locator='forum.intervals.icu, "Gradient adjusted pace + Pace training '
    'load" (Announcements, thread 4031, posted by founder david, '
    "2021-05-29)",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Re-verified 2026-07-27 (queue "
    "2026-07-26-citation-vocabulary-diverges-across-layers): the thread "
    "was re-opened and confirmed read, not merely attested to secondarily "
    "-- this citation was already correctly marked as opened in the prior "
    "session but held at SECONDARY_ATTESTATION because the read text does "
    "not support the full claim it was cited for. That reasoning still "
    "holds and the claim stays narrowed, matching TRAININGPEAKS_COVERAGE_"
    "GATE's honest-scope-gap pattern rather than a downgrade: no "
    '"intervals.icu Help Center" exists for this topic -- intervals.icu\'s '
    "own documentation of its calculations lives in founder-authored "
    "forum.intervals.icu posts, not a Zendesk-style help center. The "
    "founder's 2021-05-29 announcement states \"Intervals.icu now has "
    "gradient adjusted pace for running using the same model Strava uses. "
    'You can configure running to use GAP for training load." -- primary '
    "text confirming GAP-based pace training load exists and is "
    'configurable. It does not itself use the name "Pace Load" or state '
    "the moving-time / non-variability-normalized formulation this "
    "package's pace-channel divergence describes; that formulation is "
    "recorded separately as fitdocs' own implementation choice in "
    "DIVERGENCES' pace_load_not_variability_normalized entry, not claimed "
    "against this citation. What this citation verifies is narrower than "
    "what it was first cited for, which is exactly what PRIMARY_TEXT with "
    "a scope-gap note is for -- not a reason to hold it at "
    "SECONDARY_ATTESTATION when the text genuinely was read.",
)

INTERVALS_ICU_HRSS: Final[Citation] = Citation(
    key="intervals_icu_hrss",
    authors="intervals.icu",
    year=2020,
    work="HRSS (normalized TRIMP) training load announcement",
    locator='forum.intervals.icu, "HRSS (normalized TRIMP) training load" '
    "(Announcements, thread 569, opening post 1 by founder david, "
    "2020-03-21; second quote below from post 4, same thread, 2020-03-26)",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Opened and read in this session. As with "
    'INTERVALS_ICU_PACE_LOAD, no "intervals.icu Help Center" exists; the '
    "corrected locator points to the founder's own announcement thread. "
    'Post 1 (david, 2020-03-21, the announcement itself) states: "You can '
    "now choose to estimate training load for activities with heart rate "
    "data only (no power) using HRSS (normalized TRIMP) as used in "
    'Elevate". Post 4 (david, 2020-03-26, a follow-up reply to a user '
    "question later in the same thread -- not the announcement post) adds "
    'that it is "normalised in a similar way to TSS (100 = 1h max '
    "effort)\". Together these two posts support that intervals.icu's "
    "heart-rate load is HRSS (normalized TRIMP), scaled so that 100 "
    "corresponds to one hour at max effort. Neither post publishes HRSS's "
    "formula, so that is the extent of what the read text supports here; "
    "it does not establish that fitdocs' heart-rate load is a numerically "
    "exact interop match with intervals.icu's HRSS. Resolved 2026-07-26: "
    "the module docstring and DIVERGENCES' heart_rate_reported_intensity "
    "entry previously did assert an exact match for the load value, on "
    "this citation alone; both now claim only the shared scale, which is "
    "what this text supports. Same name and same scale do not establish "
    'numeric equivalence -- two implementations of "normalized TRIMP '
    'scaled to 100 = 1h max effort" can differ in the weighting, the '
    "smoothing window, the reserve basis or the rounding. Year and locator "
    "corrected from the prior unverified 2023 Help Center attribution to "
    "this dated, read source.",
)

TRAININGPEAKS_COVERAGE_GATE: Final[Citation] = Citation(
    key="trainingpeaks_coverage_gate",
    authors="TrainingPeaks",
    year=2016,
    work="TSS Calculation Troubleshooting",
    locator='help.trainingpeaks.com/hc/en-us/articles/204071844, "TSS '
    'Calculation Troubleshooting", read via Wayback Machine snapshot '
    "20160716234116 (the live article returns HTTP 403 to automated "
    "fetches; the archived snapshot is reachable and was opened)",
    verification=VerificationStatus.PRIMARY_TEXT,
    note="Opened and read in this session at "
    "http://web.archive.org/web/20160716234116/http://help.trainingpeaks"
    ".com:80/hc/en-us/articles/204071844, confirmed available via "
    "https://archive.org/wayback/available?url=help.trainingpeaks.com/hc/"
    "en-us/articles/204071844. The article's own text states: \"Bike TSS "
    "is incorrect or missing. Bike TSS requires power data. TrainingPeaks "
    "needs power data for at least 80% of your total workout time in "
    'order to calculate bike TSS." It further lists, per score type: '
    '"TSS - Bike TSS requires power data in watts for 80% of your ride '
    'time, power threshold set", "rTSS - Run TSS requires elevation '
    'data and threshold speed values set", "sTSS - Swim TSS requires '
    'workout duration, distance and threshold speed set", "hrTSS - '
    'Heart Rate TSS, requires HR data and threshold HR set", "tTSS - '
    'Trimps TSS requires workout duration and average heart rate". This '
    "is CONFIRMED PRIMARY FACT, not a hedge: TrainingPeaks' own text "
    "gives the 80%-power-data-coverage gate for bike/power-based TSS "
    "specifically, and gives rTSS, sTSS, hrTSS and tTSS each their own "
    "distinct data requirements with no 80%-coverage gate of their own. "
    "fitdocs applies the 0.80 default as a single cross-channel "
    "sufficiency minimum shared across the power, pace and heart-rate "
    "channels unless overridden per channel (Req 3.10) -- that is a real "
    "scope gap against this source, stated here rather than papered "
    "over: only the bike/power case is TrainingPeaks' own citable basis "
    "for 0.80, and applying the same figure to the pace and heart-rate "
    "channels is fitdocs' cross-channel default, not a requirement "
    "TrainingPeaks documents for those channels. Year corrected to 2016 "
    "(the year this Wayback snapshot was captured) from the prior "
    "unverified 2022 attribution.",
)

CITATIONS: Final[tuple[Citation, ...]] = (
    COGGAN_TSS,
    BANISTER_TRIMP,
    MINETTI_2002,
    INTERVALS_ICU_PACE_LOAD,
    INTERVALS_ICU_HRSS,
    TRAININGPEAKS_COVERAGE_GATE,
)

DIVERGENCES: Final[tuple[Divergence, ...]] = (
    Divergence(
        behavior="running_power_from_recorded_watts",
        intervals_icu="intervals.icu does not natively ingest a device's "
        "recorded running-power fields.",
        fitdocs="fitdocs computes the running power channel directly from "
        "the watts the device recorded, when present.",
        reason="Running power meters and watches increasingly record watts "
        "directly; refusing to score them because one platform does not "
        "ingest the field would fabricate an absence that is not real. No "
        "running-power model (Stryd RSS, GOVSS, Skiba) is implemented -- "
        "only the recorded watts are consumed.",
    ),
    Divergence(
        behavior="pace_load_not_variability_normalized",
        intervals_icu="intervals.icu's Pace Load is computed from "
        "grade-adjusted pace over moving time, with no variability-index "
        "normalization step.",
        fitdocs="fitdocs matches intervals.icu exactly here: grade-adjusted "
        "pace over moving time, unnormalized for pace variability.",
        reason="An alternative published running-load family normalizes for "
        "pace variability (analogous to power's normalized-power "
        "treatment); intervals.icu's own formulation, which this channel "
        "matches, does not. Recording the divergence here documents that "
        "fitdocs' pace load is not variability-normalized like that "
        'alternative method, even though both are called a "pace load".',
    ),
    Divergence(
        behavior="heart_rate_reported_intensity",
        intervals_icu="intervals.icu publishes a heart-rate load (HRSS) "
        "definition but no heart-rate intensity definition.",
        fitdocs="fitdocs reports the square root of the ratio between the "
        "activity's mean training-impulse rate and the training-impulse "
        "rate of one hour at threshold, so its intensity obeys the same "
        "load == hours x intensity**2 x 100 relation as the power and pace "
        "channels rather than being that intensity squared.",
        reason="One intensity semantic must span all three channels so a "
        "downstream comparison of two channels' intensities compares like "
        "with like at every effort, not only at threshold. The heart-rate "
        "load value itself is on the same scale intervals.icu states for "
        "HRSS -- normalized TRIMP, 100 = one hour at max effort -- so the "
        "two are directly comparable; only the reported intensity differs. "
        "Numeric identity is not claimed: the cited source publishes no "
        "HRSS formula, so the comparison is of scale and definition, not of "
        "arithmetic.",
    ),
)
