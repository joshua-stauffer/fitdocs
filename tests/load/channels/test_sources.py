"""Tests for the load-channels provenance vocabulary (``sources.py``).

Covers Requirements 3.10, 4.9, 6.8, 7.9, 8.1, 8.2, 8.3, 8.5, 8.8 -- see
``.kiro/specs/load-channels/requirements.md`` and the "Leaf --
src/fitdocs/load/channels/sources.py" component in design.md.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import pathlib
import re
import sys
from enum import Enum
from typing import Final

import pytest

from fitdocs.load.channels import sources
from fitdocs.load.channels.sources import (
    BANISTER_TRIMP,
    BLOCKED_CITATIONS,
    CITATIONS,
    COGGAN_TSS,
    DIVERGENCES,
    INTERVALS_ICU_HRSS,
    INTERVALS_ICU_PACE_LOAD,
    MINETTI_2002,
    TRAININGPEAKS_COVERAGE_GATE,
    Citation,
    Divergence,
    VerificationStatus,
)

# Whole-note backstop pins (see the six `test_*_note_matches_the_full_pinned_text`
# tests below, queue 2026-07-28-load-channel-citation-notes-unpinned). Each
# constant is the note's full text, re-verified character-for-character against
# `sources.py` at the time this backstop was written -- not derived from the
# module under test at import time, so a mutation to the module cannot silently
# drag its own backstop along with it. Mirrors the pattern established in
# `tests/metrics/test_sources.py` (queue 2026-07-28's "look for prior art").


def _normalized(text: str) -> str:
    """Collapse runs of whitespace to a single space, for the backstop
    comparisons below -- the module source wraps each note across many
    adjacent string literals, and this normalization must never do more than
    fold that wrapping back together. It must not, e.g., strip punctuation or
    case-fold, either of which could hide a falsification inside whitespace
    that looks identical either way."""
    return re.sub(r"\s+", " ", text).strip()


BACKSTOP_COGGAN_TSS_NOTE: Final[str] = (
    "Re-sourced 2026-07-27 (queue 2026-07-26-citation-vocabulary-diverges-"
    "across-layers): the book's own 2nd-edition (2010) text was still not "
    "obtained, but Coggan's own earlier chapter-length manuscript was found "
    "and opened in this session at "
    "ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf and is cited here in its"
    " place, since it is Coggan's own primary text defining the same formulas"
    " rather than a secondary summary of the book. It states NP is computed "
    "as: 1) a 30-second rolling average of power; 2) each value raised to the"
    " 4th power; 3) the average of those values; 4) the 4th root of that "
    'average. IF is defined as "the normalized power obtained in step 4 by '
    'the individual\'s power at LT". TSS is derived as "exercise duration x '
    'average power x a power-dependent intensity weighting factor", computed '
    "in the text's own steps 6-8 as normalized work (NP x duration in "
    "seconds) x IF, divided by (threshold power x 3600) x 100 -- i.e. TSS = "
    "duration_s * NP * IF / (FTP * 3600) * 100, which is the formula this "
    "package ships as fitdocs.metrics.stress.power_tss. (Corrected "
    "2026-08-23, queue 2026-07-29-coggan-note-names-a-power-channel-that-"
    "does-not-exist: this sentence previously said \"this package's power "
    'channel already implements". There is no power channel -- '
    "fitdocs/load/channels/ holds sources.py, sufficiency.py and types.py "
    "only, and the channel is load-channels task 3.1, not yet written. The "
    "formula itself has shipped in metrics/stress.py throughout.) The text "
    'also states the algorithm is derived "by analogy" to Banister\'s TRIMPS, '
    "and cites Banister, Calvert, Savage & Bach (1975) -- a different, "
    "earlier Banister paper than the one this package's BANISTER_TRIMP "
    "citation names -- for that analogy only, not for the IF/TSS formula "
    "itself."
)

BACKSTOP_BANISTER_TRIMP_NOTE: Final[str] = (
    "Re-sourced 2026-07-29 (queue "
    "2026-07-27-banister-morton-primary-texts-obtained): both the book chapter "
    "(Banister 1991, ch. 9, pp. 403-424) and its companion paper (Morton, "
    "Fitz-Clarke & Banister 1990, J Appl Physiol 69(3):1171-1177) were obtained "
    "and read in full 2026-07-27, extracted to "
    "docs/reference/banister-trimp-primary-sources.md with page and equation "
    'numbers. Banister (1991) p. 408 states the weighted training impulse as "y '
    '= 0.64e^1.92x (male)" and "y = 0.86e^1.67x (female)", x the '
    "delta-HR-reserve ratio during exercise. Morton et al. (1990) Eq. 2, p. "
    '1172, gives the same construction as "Y = e^bx", with b = 1.92 for men and '
    "1.67 for women -- the two texts agree exactly on both exponents and "
    "disagree on whether a leading coefficient exists at all: Morton's printed "
    "equation carries none. The maintainer ruled 2026-07-27 to keep Banister's "
    "0.64: it is what Banister's own text states, and it is what Morton's own "
    "worked example (~125 trimps for 1 h at HR 150 bpm, p. 1172) implies once "
    "solved for an ordinary HR_max, which Morton's coefficient-free equation "
    "does not (an HR_max of 210 versus the ordinary 182). No constant moves: "
    "metrics/stress.py already ships 0.64, so no migration-by-regen is owed. "
    "fitdocs applies the male exponent 1.92 to every athlete regardless of sex; "
    "both texts define distinct exponents per sex (1.92 male, 1.67 female), and "
    "Banister additionally carries a per-sex coefficient (0.64 male, 0.86 "
    "female) that Morton's own equation omits entirely, as stated above -- so "
    "fitdocs' sex-neutral application is a confirmed deviation from both primary "
    "texts' sex-specific exponent, not an artifact of either having been "
    "unobtainable. This package's heart-rate channel (not yet implemented as of "
    "this writing; src/fitdocs/load/channels/ today holds only sources.py and "
    "__init__.py) is designed to consume this same sex-neutral collapsed pair "
    "unchanged from metrics.stress.trimp (Req 8.6): it does not restate the "
    "coefficients, it consumes them from the single place they are already "
    "defined. If fit-ingest's own re-sourcing work makes the weighting "
    "sex-dependent, this feature's weighting seam would need an athlete-sex "
    "input it does not currently have -- design.md's own risk register, not yet "
    "realized. HRSS's ratio form, TRIMP_activity / TRIMP_one_hour_at_LTHR x 100, "
    "carries the 0.64 multiplicative coefficient in both numerator and "
    "denominator, so it cancels exactly and only the 1.92 exponent survives into "
    "that particular result. The citation's year, 1991, rests on the Internet "
    "Archive / OCLC 1150972541 library catalogue record rather than on the "
    "book's own pages -- the scanned copyright page carries a later printing's "
    "line and no year at all. Banister's own worked examples are not usable as "
    "test vectors: all three of his printed figure captions contradict his own "
    "equation (queue 2026-07-27-banister-figure-captions-unusable-as-vectors). "
    "Morton's own worked example likewise does not satisfy Morton's printed Eq. "
    "2 -- which is why it is evidence for the coefficient, not a test vector; "
    "its HR_max and HR_rest are unstated. Full extraction, discrepancies and "
    "page/equation numbers: docs/reference/banister-trimp-primary-sources.md."
)

BACKSTOP_BANISTER_TRIMP_LOCATOR: Final[str] = (
    "p. 408 (weighted training-impulse equation, both sexes); corroborated by "
    "Morton, Fitz-Clarke & Banister (1990) Eq. 2, p. 1172 (exponents agree; no "
    "multiplicative coefficient printed there)"
)

BACKSTOP_MINETTI_2002_NOTE: Final[str] = (
    "Re-sourced 2026-07-27 (queue "
    "2026-07-26-citation-vocabulary-diverges-across-layers): the paper's own "
    "text was obtained and read in this session (open-access PDF mirror at "
    "runscribe.com/wp-content/uploads/power/Minetti2002.pdf, matching the "
    "publisher's own pagination and figures). Fig. 1's caption gives both "
    "5th-order polynomial regressions as fitted to the paper's own data, "
    "gradient i in the range investigated (R^2 = 0.999 for both): Cw(i) = "
    "280.5*i^5 - 58.7*i^4 - 76.8*i^3 + 51.9*i^2 + 19.6*i + 2.5 (walking) and "
    "Cr(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6 "
    "(running), both in J*kg^-1*m^-1. The paper's walking form was read "
    "alongside the running form -- both appear in the same Fig. 1 caption -- but "
    "is still not implemented; this feature's grade adjustment remains defined "
    "for running only, a scope decision independent of sourcing."
)

BACKSTOP_INTERVALS_ICU_PACE_LOAD_NOTE: Final[str] = (
    "Re-verified 2026-07-27 (queue "
    "2026-07-26-citation-vocabulary-diverges-across-layers): the thread was "
    "re-opened and confirmed read, not merely attested to secondarily -- this "
    "citation was already correctly marked as opened in the prior session but "
    "held at SECONDARY_ATTESTATION because the read text does not support the "
    "full claim it was cited for. That reasoning still holds and the claim stays "
    "narrowed, matching TRAININGPEAKS_COVERAGE_GATE's honest-scope-gap pattern "
    'rather than a downgrade: no "intervals.icu Help Center" exists for this '
    "topic -- intervals.icu's own documentation of its calculations lives in "
    "founder-authored forum.intervals.icu posts, not a Zendesk-style help "
    "center. The founder's 2021-05-29 announcement states \"Intervals.icu now has "
    "gradient adjusted pace for running using the same model Strava uses. You "
    'can configure running to use GAP for training load." -- primary text '
    "confirming GAP-based pace training load exists and is configurable. It does "
    'not itself use the name "Pace Load" or state the moving-time / '
    "non-variability-normalized formulation this package's pace-channel "
    "divergence describes; that formulation is recorded separately as fitdocs' "
    "own implementation choice in DIVERGENCES' "
    "pace_load_not_variability_normalized entry, not claimed against this "
    "citation. What this citation verifies is narrower than what it was first "
    "cited for, which is exactly what PRIMARY_TEXT with a scope-gap note is for "
    "-- not a reason to hold it at SECONDARY_ATTESTATION when the text genuinely "
    "was read."
)

BACKSTOP_INTERVALS_ICU_HRSS_NOTE: Final[str] = (
    "Opened and read in this session. As with INTERVALS_ICU_PACE_LOAD, no "
    '"intervals.icu Help Center" exists; the corrected locator points to the '
    "founder's own announcement thread. Post 1 (david, 2020-03-21, the "
    'announcement itself) states: "You can now choose to estimate training load '
    "for activities with heart rate data only (no power) using HRSS (normalized "
    'TRIMP) as used in Elevate". Post 4 (david, 2020-03-26, a follow-up reply to '
    "a user question later in the same thread -- not the announcement post) adds "
    'that it is "normalised in a similar way to TSS (100 = 1h max effort)". '
    "Together these two posts support that intervals.icu's heart-rate load is "
    "HRSS (normalized TRIMP), scaled so that 100 corresponds to one hour at max "
    "effort. Neither post publishes HRSS's formula, so that is the extent of "
    "what the read text supports here; it does not establish that fitdocs' "
    "heart-rate load is a numerically exact interop match with intervals.icu's "
    "HRSS. Resolved 2026-07-26: the module docstring and DIVERGENCES' "
    "heart_rate_reported_intensity entry previously did assert an exact match "
    "for the load value, on this citation alone; both now claim only the shared "
    "scale, which is what this text supports. Same name and same scale do not "
    'establish numeric equivalence -- two implementations of "normalized TRIMP '
    'scaled to 100 = 1h max effort" can differ in the weighting, the smoothing '
    "window, the reserve basis or the rounding. Year and locator corrected from "
    "the prior unverified 2023 Help Center attribution to this dated, read "
    "source."
)

BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_NOTE: Final[str] = (
    "Opened and read in this session at "
    "http://web.archive.org/web/20160716234116/http://help.trainingpeaks"
    ".com:80/hc/en-us/articles/204071844, confirmed available via "
    "https://archive.org/wayback/available?url=help.trainingpeaks.com/hc/"
    "en-us/articles/204071844. "
    "The article's own text states: \"Bike TSS is incorrect or missing. Bike TSS "
    "requires power data. TrainingPeaks needs power data for at least 80% of "
    'your total workout time in order to calculate bike TSS." It further lists, '
    'per score type: "TSS - Bike TSS requires power data in watts for 80% of '
    'your ride time, power threshold set", "rTSS - Run TSS requires elevation '
    'data and threshold speed values set", "sTSS - Swim TSS requires workout '
    'duration, distance and threshold speed set", "hrTSS - Heart Rate TSS, '
    'requires HR data and threshold HR set", "tTSS - Trimps TSS requires workout '
    'duration and average heart rate". This is CONFIRMED PRIMARY FACT, not a '
    "hedge: TrainingPeaks' own text gives the 80%-power-data-coverage gate for "
    "bike/power-based TSS specifically, and gives rTSS, sTSS, hrTSS and tTSS "
    "each their own distinct data requirements with no 80%-coverage gate of "
    "their own. fitdocs applies the 0.80 default as a single cross-channel "
    "sufficiency minimum shared across the power, pace and heart-rate channels "
    "unless overridden per channel (Req 3.10) -- that is a real scope gap "
    "against this source, stated here rather than papered over: only the "
    "bike/power case is TrainingPeaks' own citable basis for 0.80, and applying "
    "the same figure to the pace and heart-rate channels is fitdocs' "
    "cross-channel default, not a requirement TrainingPeaks documents for those "
    "channels. Year corrected to 2016 (the year this Wayback snapshot was "
    "captured) from the prior unverified 2022 attribution."
)

# Whole-locator backstop pins for the remaining five citations (queue
# 2026-07-29-citation-locators-unpinned-and-undeclared). Each of the five
# constants below was retyped by hand from sources.py, not copied
# programmatically or via a clipboard equivalent -- a backstop generated from
# the value it pins asserts nothing. Unlike the six note pins above, the
# comparison against each of these five (and against
# BACKSTOP_BANISTER_TRIMP_LOCATOR, defined earlier) is a direct, unnormalized
# ``==`` (see BACKSTOP_BANISTER_TRIMP_LOCATOR's own comparison in
# test_banister_is_now_primary_text_and_blocked_citations_is_empty),
# deliberately stricter than the whitespace-normalized note pins.

BACKSTOP_COGGAN_TSS_LOCATOR: Final[str] = (
    '§3 "Analysis of power meter data" -> "Intensity factor (IF) and '
    'training stress score (TSS)", pp. 8-11 of the revised 25 March 2003 '
    "edition"
)

BACKSTOP_MINETTI_2002_LOCATOR: Final[str] = (
    "Journal of Applied Physiology, 93(3), 1039-1046, Fig. 1 caption (p. 1041)"
)

BACKSTOP_INTERVALS_ICU_PACE_LOAD_LOCATOR: Final[str] = (
    'forum.intervals.icu, "Gradient adjusted pace + Pace training load" '
    "(Announcements, thread 4031, posted by founder david, 2021-05-29)"
)

BACKSTOP_INTERVALS_ICU_HRSS_LOCATOR: Final[str] = (
    'forum.intervals.icu, "HRSS (normalized TRIMP) training load" '
    "(Announcements, thread 569, opening post 1 by founder david, "
    "2020-03-21; second quote below from post 4, same thread, 2020-03-26)"
)

BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_LOCATOR: Final[str] = (
    'help.trainingpeaks.com/hc/en-us/articles/204071844, "TSS Calculation '
    'Troubleshooting", read via Wayback Machine snapshot 20160716234116 '
    "(the live article returns HTTP 403 to automated fetches; the archived "
    "snapshot is reachable and was opened)"
)

# Registry-completeness map: every citation's key must have an entry here, or
# the guard test below reds. Built as a dict rather than a bare tuple/set so a
# citation added without a matching backstop entry is caught by key, not by
# position -- the "hardcoded tuple goes stale when a fourth record lands"
# trap is real, but it is not named in this queue item; it is recorded in the
# shared agent log (impl-fit-ingest WARN, 2026-07-30T00:17:05Z) and in
# .kiro/queue/closed/2026-07-27-design-md-enumeration-unguarded.md.
_LOCATOR_BACKSTOPS: Final[dict[str, str]] = {
    "coggan_tss": BACKSTOP_COGGAN_TSS_LOCATOR,
    "banister_trimp": BACKSTOP_BANISTER_TRIMP_LOCATOR,
    "minetti_2002": BACKSTOP_MINETTI_2002_LOCATOR,
    "intervals_icu_pace_load": BACKSTOP_INTERVALS_ICU_PACE_LOAD_LOCATOR,
    "intervals_icu_hrss": BACKSTOP_INTERVALS_ICU_HRSS_LOCATOR,
    "trainingpeaks_coverage_gate": BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_LOCATOR,
}

# --- Whole-record attribution backstop (queue
# 2026-07-30-citation-authors-year-work-unpinned) --------------------------
#
# `note` and `locator` are pinned field-by-field above. `authors`, `year`,
# `work` and `verification` were not, and were falsifiable with the full suite
# green -- mutating MINETTI_2002.year 2002 -> 2003, or .authors -> "Nobody,
# X.", or .work -> another title, each left the suite at 2297 passed.
#
# That gap had been closed one field at a time twice already (`note` on
# 2026-07-29, `locator` on 2026-07-30), and each round left the next field
# undefended. This is deliberately NOT a third per-field dict. It pins a
# fingerprint over **every field of `Citation` that does not already have a
# dedicated pin**, and it computes the field list by walking
# `dataclasses.fields(Citation)` rather than naming the fields here.
#
# The self-maintenance property that buys: adding a field to `Citation` changes
# every fingerprint, so all six backstops red and the new field cannot ship
# both unpinned and undeclared. Removing a dedicated pin has the same effect --
# the field falls back into the fingerprint, which reds until transcribed.
#
# The rendering is plain values, not `repr`, so a reviewer can read a
# fingerprint against `sources.py` directly. `verification` renders as its enum
# `.value`, which answers the queue item's second open question: a record
# silently downgraded from PRIMARY_TEXT now reds here.

_DEDICATED_FIELD_PINS: Final[frozenset[str]] = frozenset({"note", "locator"})
"""Fields of `Citation` pinned individually above, and so excluded from the
whole-record fingerprint -- pinning them twice would mean every note edit had
to be transcribed in two places, which is how a backstop falls out of date."""


def _attribution_fingerprint(citation: Citation) -> str:
    """Render every non-dedicated field of ``citation`` as ``name=value``.

    Walks ``dataclasses.fields(Citation)`` in declaration order so the field
    set is derived from the record type, never restated here. Enum values
    render as their ``.value``.
    """
    parts: list[str] = []
    for field in dataclasses.fields(Citation):
        if field.name in _DEDICATED_FIELD_PINS:
            continue
        value = getattr(citation, field.name)
        rendered = value.value if isinstance(value, Enum) else value
        parts.append(f"{field.name}={rendered}")
    return " | ".join(parts)


# Transcribed from `sources.py`. These are literals on purpose: deriving them
# from the module under test would make the comparison vacuous.
_ATTRIBUTION_BACKSTOPS: Final[dict[str, str]] = {
    "coggan_tss": (
        "key=coggan_tss | authors=Coggan, A.R. | year=2003 | work=Training "
        "and racing using a power meter: an introduction (USA Cycling "
        "coaching-education chapter; the basis for, and later folded into, "
        'Allen & Coggan\'s "Training and Racing with a Power Meter") | '
        "verification=primary_text"
    ),
    "banister_trimp": (
        "key=banister_trimp | authors=Banister, E.W. | year=1991 | "
        "work=Modeling Elite Athletic Performance, in: Physiological "
        "Testing of the High-Performance Athlete (2nd ed.), Human Kinetics "
        "| verification=primary_text"
    ),
    "minetti_2002": (
        "key=minetti_2002 | authors=Minetti, A.E., Moia, C., Roi, G.S., "
        "Susta, D. & Ferretti, G. | year=2002 | work=Energy cost of walking"
        " and running at extreme uphill and downhill slopes | "
        "verification=primary_text"
    ),
    "intervals_icu_pace_load": (
        "key=intervals_icu_pace_load | authors=intervals.icu | year=2021 | "
        "work=Pace-based training load (gradient-adjusted pace) "
        "announcement | verification=primary_text"
    ),
    "intervals_icu_hrss": (
        "key=intervals_icu_hrss | authors=intervals.icu | year=2020 | "
        "work=HRSS (normalized TRIMP) training load announcement | "
        "verification=primary_text"
    ),
    "trainingpeaks_coverage_gate": (
        "key=trainingpeaks_coverage_gate | authors=TrainingPeaks | "
        "year=2016 | work=TSS Calculation Troubleshooting | "
        "verification=primary_text"
    ),
}


def test_dedicated_field_pins_name_real_citation_fields() -> None:
    """``_DEDICATED_FIELD_PINS`` must name fields that exist.

    Without this, renaming ``note`` on ``Citation`` would leave a stale
    exclusion behind: the renamed field would enter the fingerprint (reddening
    loudly, which is fine) but the dead entry would silently keep excluding
    nothing, and the next reader would believe a field was pinned elsewhere
    when it was not.

    Measured mutation evidence (test-module counts, 38 tests in this file):
    adding ``"authors"`` to ``_DEDICATED_FIELD_PINS`` passes *here* but reds
    the fingerprint test below (1 failed) -- the two guards are complementary,
    not redundant. Misspelling an entry as ``"notes"`` reds **both** (2
    failed): this test on the stale name, and the fingerprint test because
    ``note`` is no longer excluded and falls back into the fingerprint.
    """
    field_names = {field.name for field in dataclasses.fields(Citation)}
    unknown = _DEDICATED_FIELD_PINS - field_names
    assert not unknown, (
        f"_DEDICATED_FIELD_PINS names fields Citation does not have: {sorted(unknown)}"
    )


def test_every_citation_attribution_is_pinned_by_a_backstop() -> None:
    """Registry-completeness guard for the whole-record attribution pins
    (queue 2026-07-30-citation-authors-year-work-unpinned).

    Same shape as ``test_every_citation_locator_is_pinned_by_a_backstop``:
    the registry is asserted non-empty first so the walk cannot pass having
    scanned nothing, then set-equality in **both** directions, so a seventh
    citation added without a backstop reds here rather than shipping unpinned.

    Mutation evidence (each applied to ``MINETTI_2002`` in ``sources.py`` and
    reverted): ``year`` 2002 -> 2003, ``authors`` -> "Nobody, X.", ``work`` ->
    another title, and ``verification`` PRIMARY_TEXT -> any other member each
    red the per-citation comparison. Deleting an entry from
    ``_ATTRIBUTION_BACKSTOPS``, or adding one with no matching citation, reds
    the set-equality assertion. Adding a field to ``Citation`` reds the
    per-citation comparison for all six citations (1 failed test, first
    citation reported). Downgrading ``verification`` from ``PRIMARY_TEXT``
    reds 4 tests, this one among them.

    All of the above were run and observed on this branch; none is asserted
    from reading.
    """
    assert len(CITATIONS) > 0, "the walk is looking at the wrong registry"
    citation_keys = {citation.key for citation in CITATIONS}
    assert citation_keys == set(_ATTRIBUTION_BACKSTOPS), (
        "a citation was added or removed in sources.py without a matching "
        "update to _ATTRIBUTION_BACKSTOPS in this test module"
    )
    for citation in CITATIONS:
        assert (
            _attribution_fingerprint(citation) == _ATTRIBUTION_BACKSTOPS[citation.key]
        ), citation.key


def test_package_imports_cleanly() -> None:
    """The channel package's ``__init__.py`` holds no logic and no import
    side effect (8.8 boundary; Req 9.7): every top-level statement is a
    docstring, a ``from __future__`` import, a plain re-export (``from
    fitdocs.load.channels.<leaf> import X as X``), or the single ``__all__``
    assignment listing string constants.

    Widened in task 4.1 from task 1.1's original ``["Expr", "ImportFrom"]``
    shape (a single ``from __future__ import annotations`` and nothing
    else): task 4.1's whole job is to populate this file with the layer's
    re-exports, which this test's original, narrower shape would now
    permanently forbid. The widening still rejects everything a "no logic"
    module must reject -- a ``Call``, an ``If``, a ``FunctionDef``, a
    ``ClassDef``, or an ``Assign`` to anything other than ``__all__`` -- and
    additionally requires every non-``__future__`` import to be an explicit
    ``X as X`` re-export (mypy strict's own re-export spelling) sourced from
    this package itself, so a wildcard import, a renamed import, or an
    import of unrelated logic from elsewhere in the tree still fails it.
    """
    spec = importlib.util.find_spec("fitdocs.load.channels")
    assert spec is not None and spec.origin is not None
    tree = ast.parse(pathlib.Path(spec.origin).read_text(), filename=spec.origin)
    nodes = list(ast.iter_child_nodes(tree))
    kinds = [type(node).__name__ for node in nodes]
    assert kinds[0] == "Expr", "the module docstring must be the first statement"
    assert set(kinds[1:]) <= {"ImportFrom", "Assign"}, (
        f"unexpected top-level statement kind(s) in fitdocs.load.channels: "
        f"{kinds!r} -- only ImportFrom and Assign are allowed after the "
        "docstring"
    )
    assign_count = kinds.count("Assign")
    assert assign_count == 1, (
        f"expected exactly one top-level Assign (__all__), found {assign_count}"
    )

    saw_future_import = False
    for node in nodes:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant)
            assert isinstance(node.value.value, str)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                saw_future_import = True
                continue
            assert node.module is not None and node.module.startswith(
                "fitdocs.load.channels."
            ), (
                f"{node.module!r} is not a fitdocs.load.channels.* leaf -- "
                "this package re-exports only its own leaves"
            )
            for alias in node.names:
                # The three ``compute`` entry points are deliberately
                # renamed under a channel-qualified name (task 4.1's own
                # instruction: "the three computation entry points under
                # channel-qualified names") so all three can be imported
                # from this one package without colliding on the bare name
                # -- power.py, heart_rate.py and pace.py each define their
                # own module-level ``compute`` (the package's other five
                # leaf modules do not) -- every other name must be the
                # mypy-strict 'X as X' re-export spelling.
                is_qualified_compute = alias.name == "compute" and alias.asname in {
                    "power_compute",
                    "heart_rate_compute",
                    "pace_compute",
                }
                assert alias.asname == alias.name or is_qualified_compute, (
                    f"{alias.name!r} is imported under a different name "
                    f"({alias.asname!r}) -- every re-export here must be "
                    "explicit 'X as X', matching mypy strict's own "
                    "no_implicit_reexport spelling, except the three "
                    "channel-qualified 'compute as <channel>_compute' imports"
                )
        elif isinstance(node, ast.Assign):
            assert len(node.targets) == 1
            target = node.targets[0]
            assert isinstance(target, ast.Name) and target.id == "__all__", (
                "the only top-level assignment allowed is __all__"
            )
            assert isinstance(node.value, ast.List)
            for element in node.value.elts:
                assert isinstance(element, ast.Constant)
                assert isinstance(element.value, str)
    assert saw_future_import, (
        "expected a 'from __future__ import annotations' among the top-level imports"
    )


def test_verification_status_has_all_three_members() -> None:
    """VerificationStatus defines exactly the three documented members (8.2)."""
    members = {member.value for member in VerificationStatus}
    assert members == {
        "primary_text",
        "secondary_attestation",
        "fitdocs_measured",
    }
    # Defined here even though this feature introduces no constant carrying
    # the third status -- the quality-flags feature is its only consumer.
    assert VerificationStatus.FITDOCS_MEASURED.value == "fitdocs_measured"


def test_named_citations_are_exported() -> None:
    """Every named citation constant from design.md is present and typed."""
    for citation in (
        COGGAN_TSS,
        BANISTER_TRIMP,
        MINETTI_2002,
        INTERVALS_ICU_PACE_LOAD,
        INTERVALS_ICU_HRSS,
        TRAININGPEAKS_COVERAGE_GATE,
    ):
        assert isinstance(citation, Citation)


def test_citations_have_nonempty_work_and_verification_status() -> None:
    """8.1, 8.3: every citation names its work and carries a verification status."""
    assert len(CITATIONS) >= 6
    for citation in CITATIONS:
        assert citation.authors.strip() != ""
        assert citation.year > 0
        assert citation.work.strip() != ""
        assert isinstance(citation.verification, VerificationStatus)


def test_banister_is_now_primary_text_and_blocked_citations_is_empty() -> None:
    """Req 8.9 (queue 2026-07-27-banister-morton-primary-texts-obtained):
    BANISTER_TRIMP was the last SECONDARY_ATTESTATION citation in this
    module -- COGGAN_TSS, MINETTI_2002 and INTERVALS_ICU_PACE_LOAD were
    already re-sourced to PRIMARY_TEXT (queue
    2026-07-26-citation-vocabulary-diverges-across-layers). It is now
    PRIMARY_TEXT too: both Banister (1991) and Morton, Fitz-Clarke &
    Banister (1990) were obtained and read in full 2026-07-27
    (docs/reference/banister-trimp-primary-sources.md), so the premise for
    its SECONDARY_ATTESTATION status and BLOCKED_CITATIONS membership no
    longer holds. This test replaces
    ``test_banister_is_the_sole_secondary_attestation_and_is_blocked``,
    which asserted the opposite of every one of these facts and would have
    been the mechanical catch for the stale note this queue item closes had
    it asserted note *content* rather than only non-emptiness."""
    assert BANISTER_TRIMP.verification is VerificationStatus.PRIMARY_TEXT
    assert BANISTER_TRIMP.locator is not None
    assert BANISTER_TRIMP.locator == BACKSTOP_BANISTER_TRIMP_LOCATOR
    assert BANISTER_TRIMP.key not in BLOCKED_CITATIONS
    assert frozenset() == BLOCKED_CITATIONS
    for citation in (COGGAN_TSS, MINETTI_2002, INTERVALS_ICU_PACE_LOAD):
        assert citation.verification is VerificationStatus.PRIMARY_TEXT


def test_banister_trimp_locator_mutation_evidence() -> None:
    """Discrimination evidence for the ``locator`` pin above (per
    change-protocol.md's Fixture Discrimination gate). A prior review found
    ``locator`` guarded only by ``assert ... is not None`` -- a vacuous
    introspection that a page moved to 508, an equation renumbered to 9, a
    page swapped to 1999, or the "no multiplicative coefficient printed
    there" clause inverted to its opposite would all survive. This test
    documents, in a form future maintenance can re-run by hand, that the
    equality pin above catches each:

    1. "p. 408" -> "p. 508" -- reds (the page is pinned).
    2. "Eq. 2" -> "Eq. 9" -- reds (the equation number is pinned).
    3. "no multiplicative coefficient printed there" -> "a multiplicative
       coefficient printed there" -- reds (the claim's polarity is
       pinned)."""
    locator = BANISTER_TRIMP.locator or ""
    moved_page = locator.replace("p. 408", "p. 508")
    assert moved_page != locator
    assert moved_page != BACKSTOP_BANISTER_TRIMP_LOCATOR

    renumbered_equation = locator.replace("Eq. 2", "Eq. 9")
    assert renumbered_equation != locator
    assert renumbered_equation != BACKSTOP_BANISTER_TRIMP_LOCATOR

    inverted_claim = locator.replace(
        "no multiplicative coefficient printed there",
        "a multiplicative coefficient printed there",
    )
    assert inverted_claim != locator
    assert inverted_claim != BACKSTOP_BANISTER_TRIMP_LOCATOR


def test_every_citation_locator_is_pinned_by_a_backstop() -> None:
    """Registry-completeness guard for the whole-locator pins (queue
    2026-07-29-citation-locators-unpinned-and-undeclared): pinning each
    locator individually is not the same as pinning the *relation* that every
    citation's locator has a backstop. This walks ``CITATIONS`` -- asserted
    non-empty first, so the walk cannot pass having scanned nothing (the
    "vacuous walk" anti-pattern) -- and requires ``_LOCATOR_BACKSTOPS`` to
    carry exactly the same set of keys, so a citation added later without a
    matching backstop entry fails here rather than silently going unpinned.
    Mutation evidence: deleting any one entry from ``_LOCATOR_BACKSTOPS`` (or
    adding an extra key with no matching citation) reds the set-equality
    assertion; changing any citation's ``locator`` in ``sources.py`` reds the
    per-citation equality assertion in the loop."""
    assert len(CITATIONS) > 0, "the walk is looking at the wrong registry"
    citation_keys = {citation.key for citation in CITATIONS}
    assert citation_keys == set(_LOCATOR_BACKSTOPS), (
        "a citation was added or removed in sources.py without a matching "
        "update to _LOCATOR_BACKSTOPS in this test module"
    )
    for citation in CITATIONS:
        assert citation.locator == _LOCATOR_BACKSTOPS[citation.key], citation.key


def test_coggan_tss_locator_matches_the_full_pinned_text() -> None:
    """Whole-locator backstop (queue
    2026-07-29-citation-locators-unpinned-and-undeclared). Unlike the note
    pins above, this comparison is a direct, unnormalized ``==`` -- see the
    module-level comment above ``BACKSTOP_COGGAN_TSS_LOCATOR``."""
    assert COGGAN_TSS.locator == BACKSTOP_COGGAN_TSS_LOCATOR


def test_coggan_tss_locator_mutation_evidence() -> None:
    """Discrimination evidence for the pin above. Falsifying the edition year
    the way the queue's own falsification did ("2003 edition" -> "2013
    edition") reds; so does changing the section marker."""
    locator = COGGAN_TSS.locator or ""
    edition_year_changed = locator.replace(
        "revised 25 March 2003 edition", "revised 25 March 2013 edition"
    )
    assert edition_year_changed != locator
    assert edition_year_changed != BACKSTOP_COGGAN_TSS_LOCATOR

    section_changed = locator.replace('§3 "Analysis', '§4 "Analysis')
    assert section_changed != locator
    assert section_changed != BACKSTOP_COGGAN_TSS_LOCATOR


def test_minetti_2002_locator_matches_the_full_pinned_text() -> None:
    """Whole-locator backstop (queue
    2026-07-29-citation-locators-unpinned-and-undeclared). Load-bearing: this
    citation's own note sources both published polynomials (walking and
    running) to this exact figure caption, so a drifted figure or page
    number here would leave the note's own attribution pointing somewhere
    that does not contain what it claims."""
    assert MINETTI_2002.locator == BACKSTOP_MINETTI_2002_LOCATOR


def test_minetti_2002_locator_mutation_evidence() -> None:
    """Discrimination evidence for the pin above -- the exact falsification
    the queue item recorded as a survivor at 2098 passed ("Fig. 1 caption
    (p. 1041)" -> "Fig. 7 caption (p. 9999)", plus a volume change) now reds
    against the pin."""
    locator = MINETTI_2002.locator or ""
    figure_and_page_changed = locator.replace(
        "Fig. 1 caption (p. 1041)", "Fig. 7 caption (p. 9999)"
    )
    assert figure_and_page_changed != locator
    assert figure_and_page_changed != BACKSTOP_MINETTI_2002_LOCATOR

    volume_changed = locator.replace("93(3), 1039-1046", "99(9), 1039-1046")
    assert volume_changed != locator
    assert volume_changed != BACKSTOP_MINETTI_2002_LOCATOR


def test_intervals_icu_pace_load_locator_matches_the_full_pinned_text() -> None:
    """Whole-locator backstop (queue
    2026-07-29-citation-locators-unpinned-and-undeclared)."""
    assert INTERVALS_ICU_PACE_LOAD.locator == BACKSTOP_INTERVALS_ICU_PACE_LOAD_LOCATOR


def test_intervals_icu_pace_load_locator_mutation_evidence() -> None:
    """Discrimination evidence for the pin above: the thread number and the
    posting date are both pinned."""
    locator = INTERVALS_ICU_PACE_LOAD.locator or ""
    thread_changed = locator.replace("thread 4031", "thread 9999")
    assert thread_changed != locator
    assert thread_changed != BACKSTOP_INTERVALS_ICU_PACE_LOAD_LOCATOR

    date_changed = locator.replace("2021-05-29", "2021-05-30")
    assert date_changed != locator
    assert date_changed != BACKSTOP_INTERVALS_ICU_PACE_LOAD_LOCATOR


def test_intervals_icu_hrss_locator_matches_the_full_pinned_text() -> None:
    """Whole-locator backstop (queue
    2026-07-29-citation-locators-unpinned-and-undeclared)."""
    assert INTERVALS_ICU_HRSS.locator == BACKSTOP_INTERVALS_ICU_HRSS_LOCATOR


def test_intervals_icu_hrss_locator_mutation_evidence() -> None:
    """Discrimination evidence for the pin above: the thread number and the
    opening-post date are both pinned."""
    locator = INTERVALS_ICU_HRSS.locator or ""
    thread_changed = locator.replace("thread 569", "thread 999")
    assert thread_changed != locator
    assert thread_changed != BACKSTOP_INTERVALS_ICU_HRSS_LOCATOR

    date_changed = locator.replace("2020-03-21", "2020-03-22")
    assert date_changed != locator
    assert date_changed != BACKSTOP_INTERVALS_ICU_HRSS_LOCATOR


def test_trainingpeaks_coverage_gate_locator_matches_the_full_pinned_text() -> None:
    """Whole-locator backstop (queue
    2026-07-29-citation-locators-unpinned-and-undeclared)."""
    assert (
        TRAININGPEAKS_COVERAGE_GATE.locator
        == BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_LOCATOR
    )


def test_trainingpeaks_coverage_gate_locator_mutation_evidence() -> None:
    """Discrimination evidence for the pin above: the Wayback snapshot id and
    the HTTP status code are both pinned."""
    locator = TRAININGPEAKS_COVERAGE_GATE.locator or ""
    snapshot_changed = locator.replace("20160716234116", "20160716999999")
    assert snapshot_changed != locator
    assert snapshot_changed != BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_LOCATOR

    status_changed = locator.replace("HTTP 403", "HTTP 404")
    assert status_changed != locator
    assert status_changed != BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_LOCATOR


def test_secondary_attestation_guard_discriminates_a_hypothetical_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 8.9's enforcement mechanism
    (``test_no_new_secondary_attestation_citations_exist`` below) now passes
    *vacuously*: no citation in ``CITATIONS`` carries ``SECONDARY_ATTESTATION``
    any more, and ``BLOCKED_CITATIONS`` is empty. A previous version of this
    module's sibling test asserted ``BLOCKED_CITATIONS`` was pinned to exactly
    ``{"banister_trimp"}`` and a "positive control" that at least one
    ``SECONDARY_ATTESTATION`` citation existed -- both of those became the
    wrong invariant to assert once the citation was legitimately re-sourced,
    which is exactly the trap named in queue
    2026-07-27-banister-morton-primary-texts-obtained: fixing a test to
    assert non-emptiness (or membership of a specific key) pins a transient
    fact, not the mechanism.

    This test asserts the mechanism instead -- and, per review, does so by
    *invoking the real guard test function*, not by re-implementing its
    filter. An earlier version of this test copied the guard's
    "SECONDARY_ATTESTATION and key not in BLOCKED_CITATIONS" filter inline;
    that copy could pass even after the real guard
    (``test_no_new_secondary_attestation_citations_exist``) was neutered, so
    it discriminated nothing about the guard itself. This version
    monkeypatches this test module's own ``CITATIONS`` binding -- the exact
    global name the real guard test reads -- to include a hypothetical
    untracked downgrade, then calls the real guard test function directly and
    asserts it raises. Neutering the real guard (e.g. dropping its
    ``in BLOCKED_CITATIONS`` check, or short-circuiting its loop) now reds
    this test, because it is exercising that function's own code path."""
    hypothetical = Citation(
        key="hypothetical_downgrade",
        authors="Nobody",
        year=1900,
        work="A citation that must never ship at SECONDARY_ATTESTATION untracked",
        locator=None,
        verification=VerificationStatus.SECONDARY_ATTESTATION,
        note="A hypothetical silent downgrade, not a real citation in this package.",
    )
    assert hypothetical.key not in BLOCKED_CITATIONS
    monkeypatch.setattr(sys.modules[__name__], "CITATIONS", (*CITATIONS, hypothetical))
    with pytest.raises(AssertionError):
        test_no_new_secondary_attestation_citations_exist()


def test_blocked_citation_notes_name_both_attempted_sources() -> None:
    """Req 8.10: an exception recorded under 8.9 must record *what was
    searched for* and *why the search did not succeed*, not merely carry a
    nonempty ``note``. This loop now runs zero iterations, since
    ``BLOCKED_CITATIONS`` is empty (queue
    2026-07-27-banister-morton-primary-texts-obtained) -- kept in place
    rather than deleted, since a future named exception must still satisfy
    the length floor below, not merely be present. What this test actually
    enforces, on any future entrant, is a length floor (over 200 characters),
    not a semantic read of the note's content: a note that happens to be long
    while saying something else entirely would still pass; this is a
    length-based floor, not a semantic guarantee that the note is accurate.
    (The prior BANISTER_TRIMP-specific substring checks this test carried
    moved to that citation's own whole-note backstop below once it was
    re-sourced to PRIMARY_TEXT and left BLOCKED_CITATIONS.)"""
    for key in BLOCKED_CITATIONS:
        matches = [citation for citation in CITATIONS if citation.key == key]
        assert matches, f"{key} is in BLOCKED_CITATIONS but absent from CITATIONS"
        note = matches[0].note
        assert note is not None and note.strip() != ""
        assert len(note) > 200, (
            f"{key}'s BLOCKED_CITATIONS note ({note!r}) is too short to "
            "record what was searched for and why it failed -- a "
            'placeholder like "x" must not satisfy Req 8.10'
        )


def test_every_secondary_attestation_citation_has_a_nonempty_note() -> None:
    """8.2, generalized: every citation recorded as SECONDARY_ATTESTATION
    states why its primary text was not obtained or otherwise supports the
    downgrade. A citation carrying this status with an empty note is a
    silent, unexplained downgrade. This currently runs over zero citations
    -- BANISTER_TRIMP was the last SECONDARY_ATTESTATION citation in this
    module and was re-sourced to PRIMARY_TEXT 2026-07-29 (queue
    2026-07-27-banister-morton-primary-texts-obtained) -- and is kept for
    the day a new SECONDARY_ATTESTATION citation is added; a previous
    version of this test asserted a "positive control" that at least one
    such citation must exist, which became the wrong invariant to assert
    once the last one was legitimately re-sourced away
    (test_secondary_attestation_guard_discriminates_a_hypothetical_downgrade
    above is what actually keeps this loop from being a false sense of
    coverage)."""
    secondary = [
        citation
        for citation in CITATIONS
        if citation.verification is VerificationStatus.SECONDARY_ATTESTATION
    ]
    for citation in secondary:
        assert citation.note is not None
        assert citation.note.strip() != ""


def test_no_new_secondary_attestation_citations_exist() -> None:
    """Req 8.9: the enforcement mechanism for the tightened bar. A citation
    may carry SECONDARY_ATTESTATION only if its key is a named, tracked
    exception in BLOCKED_CITATIONS -- anything else reddens this test,
    catching a future silent downgrade the way none of the original four
    were caught until this queue item."""
    for citation in CITATIONS:
        if citation.verification is VerificationStatus.SECONDARY_ATTESTATION:
            assert citation.key in BLOCKED_CITATIONS, (
                f"{citation.key} carries SECONDARY_ATTESTATION but is not "
                "in BLOCKED_CITATIONS -- either re-source it to PRIMARY_TEXT "
                "or add it to BLOCKED_CITATIONS with a note explaining the "
                "search that failed to obtain its primary text"
            )


def test_every_module_level_citation_is_registered_in_citations() -> None:
    """Registry-completeness guard (Req 8.9's enforcement, hardened): a
    RUNTIME namespace check over ``sources`` itself, not merely over
    ``CITATIONS``. Adding a new module-level ``Citation`` instance and
    forgetting to append it to ``CITATIONS`` is invisible to every other test
    in this module -- ``test_no_new_secondary_attestation_citations_exist``
    included -- because they all walk ``CITATIONS`` only, and a citation
    absent from that tuple was never a candidate for them to inspect.

    This previously walked the module's source with :mod:`ast`, restricted
    to ``ast.AnnAssign`` nodes whose value was a literal ``Citation(...)``
    call and whose ``CITATIONS`` right-hand side was itself a literal tuple
    of bare names. That walk saw exactly one spelling of "define a
    ``Citation``" and missed four others, each proved to leave this test
    (and the full suite) green while shipping an unregistered
    ``SECONDARY_ATTESTATION`` citation:

    - ``SNEAKY = Citation(...)`` -- no type annotation, so not an
      ``ast.AnnAssign``.
    - ``SNEAKY: Final[Citation] = _make(...)`` -- called through a
      differently-named factory, so ``node.value.func.id != "Citation"``.
    - the definition nested inside ``if True:`` or ``if TYPE_CHECKING:`` --
      ``ast.iter_child_nodes`` only sees top-level statements.
    - ``_C = Citation`` followed by ``_C(...)`` -- the constructor name is
      matched literally, so an aliased call is invisible.

    A runtime check closes all four in one line and needs no source
    parsing: every :class:`Citation` instance actually bound as a module
    attribute of ``sources``, by any syntax whatsoever, is a
    ``vars(sources)`` value, and the only question that matters is whether
    it is also a member of ``CITATIONS`` -- not how it was spelled. The AST
    walk is dropped rather than kept alongside this, since it enforced
    nothing this runtime check does not already enforce, and its false
    sense of completeness ("an AST walk over sources.py itself") is exactly
    what let the four evasions above ship unnoticed.

    Mutation evidence (verified against all five during remediation, see
    queue 2026-07-26-citation-vocabulary-diverges-across-layers): each of
    the four evasions above, plus the original mutation (a module-level
    ``Citation`` never appended to ``CITATIONS`` at all), reds this test.
    Mirrors fit-ingest's own planned registry-completeness check
    (design.md:336, ``test_sources.py`` NEW)."""
    module_citations = {
        value for value in vars(sources).values() if isinstance(value, Citation)
    }
    missing = module_citations - set(CITATIONS)
    assert not missing, (
        f"citation(s) bound as module attributes of sources.py but never "
        f"appended to CITATIONS, so no other test in this module can see "
        f"them: {missing}"
    )


def test_blocked_citations_is_pinned_to_empty() -> None:
    """BLOCKED_CITATIONS is pinned exactly, not just checked for absence of a
    specific key: silently adding a key here is how a future downgrade could
    evade test_no_new_secondary_attestation_citations_exist by widening the
    allowlist instead of re-sourcing or holding the line. Previously pinned
    to exactly ``{"banister_trimp"}``; empty since 2026-07-29 (queue
    2026-07-27-banister-morton-primary-texts-obtained), once BANISTER_TRIMP
    -- the sole citation that ever occupied this set -- was re-sourced to
    PRIMARY_TEXT. Asserting emptiness here pins a fact that is expected to
    change again the next time a citation is legitimately blocked; the
    *mechanism* that would catch a silent widening or a silent downgrade is
    pinned independently by
    test_secondary_attestation_guard_discriminates_a_hypothetical_downgrade,
    which does not depend on the set's current membership."""
    assert frozenset() == BLOCKED_CITATIONS


def test_primary_text_citations_are_pinned_exactly() -> None:
    """The PRIMARY_TEXT set is pinned exactly, not just non-empty: a citation
    silently re-upgraded (or downgraded) without actually being read from its
    source's own text must fail this test, since verification status is the
    entire distinction this module exists to protect (Req 8.2). Widened
    2026-07-27 (queue 2026-07-26-citation-vocabulary-diverges-across-layers)
    from {intervals_icu_hrss, trainingpeaks_coverage_gate} to also include
    coggan_tss, minetti_2002 and intervals_icu_pace_load; widened again
    2026-07-29 (queue 2026-07-27-banister-morton-primary-texts-obtained) to
    include banister_trimp, once Banister (1991) and Morton, Fitz-Clarke &
    Banister (1990) were obtained and read in full -- it is no longer
    deliberately absent."""
    primary_keys = {
        citation.key
        for citation in CITATIONS
        if citation.verification is VerificationStatus.PRIMARY_TEXT
    }
    assert primary_keys == {
        "coggan_tss",
        "banister_trimp",
        "minetti_2002",
        "intervals_icu_pace_load",
        "intervals_icu_hrss",
        "trainingpeaks_coverage_gate",
    }


def test_minetti_note_records_walking_form_not_implemented() -> None:
    """7.9 (amended 2026-07-27, queue
    2026-07-26-citation-vocabulary-diverges-across-layers): the Minetti
    citation records that the walking form was READ ALONGSIDE the running
    form -- both appear in the same Fig. 1 caption -- but remains
    unimplemented as a scope decision, not a sourcing gap. The original 7.9
    wording, and this test's own original docstring, both said the walking
    form "was not obtained"; that claim was falsified when `MINETTI_2002`
    was re-sourced to `PRIMARY_TEXT` and its note came to state the
    opposite.

    Mutation evidence: replacing the note's last sentence with "The paper's
    walking form was NOT OBTAINED and is therefore not implemented." left
    the prior two-substring assertion (``"walking" in note`` and
    ``"not implemented" in note``) green at 16/16 -- a grep for either
    phrasing passes either way, so it could not discriminate the true claim
    from its falsified predecessor. The assertion below adds a negative
    check ruling out the "not obtained" phrasing and a positive check for
    the "read alongside" phrasing, so that exact mutation now reds."""
    assert MINETTI_2002.note is not None
    note = MINETTI_2002.note.lower()
    assert "walking" in note
    assert "not implemented" in note
    assert "read alongside" in note
    assert "not obtained" not in note, (
        "the Minetti note claims the walking form was not obtained again -- "
        "it was read alongside the running form in the same Fig. 1 caption "
        "once MINETTI_2002 was re-sourced to PRIMARY_TEXT"
    )


def test_coggan_tss_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (queue 2026-07-28-load-channel-citation-notes-
    unpinned). Every targeted assertion elsewhere in this module pins a
    clause or a quoted substring of a note; none of them, individually or
    together, bounds the space of single-word or single-number
    substitutions elsewhere in the note. This test closes that space by
    requiring the *entire* note to equal a character-for-character copy of
    the text this package's own re-sourcing session verified (whitespace-
    normalized only to absorb how the module source wraps the string across
    adjacent literals -- no other normalization is applied, so no
    substitution of one word or number for another can hide inside it). It
    is deliberately brittle: any change to this provenance record other
    than whitespace re-wrapping must fail this test and force a human to
    read the diff, because the record makes a claim about a source this
    module does not itself re-verify on every run."""
    note = COGGAN_TSS.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_COGGAN_TSS_NOTE)


def test_banister_trimp_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (queue 2026-07-28-load-channel-citation-notes-
    unpinned, sequenced after queue 2026-07-27-banister-morton-primary-
    texts-obtained per that item's own "How to pick it up" step 5). Pins
    the note re-sourced against docs/reference/banister-trimp-primary-
    sources.md 2026-07-29: every quoted formula, page and equation number,
    and the maintainer's coefficient ruling, as one whole-value equality so
    that altering any single one of them reds this test rather than
    silently passing the weaker checks elsewhere in this module. See
    test_coggan_tss_note_matches_the_full_pinned_text's docstring for why a
    whole-note pin is needed at all, and
    test_banister_trimp_note_mutation_evidence below for the mutations this
    was verified to catch."""
    note = BANISTER_TRIMP.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_BANISTER_TRIMP_NOTE)


def test_banister_trimp_note_mutation_evidence() -> None:
    """Discrimination evidence for the backstop above (per
    change-protocol.md's Fixture Discrimination gate): three independent
    single-claim falsifications of BANISTER_TRIMP.note, each checked to red
    the whole-note backstop when substituted in isolation. This test does
    not itself assert on the falsified variants -- it documents, in a form
    future maintenance can re-run by hand, that the backstop discriminates
    each -- inverting the coefficient ruling, moving a page number, and
    swapping the quoted formula:

    1. "The maintainer ruled 2026-07-27 to keep Banister's 0.64" ->
       "...to keep Morton's 1.0" -- reds (the ruling and the value are both
       pinned).
    2. "Banister (1991) p. 408 states" -> "Banister (1991) p. 409 states" --
       reds (the page attribution is pinned).
    3. '"y = 0.64e^1.92x (male)"' -> '"y = 0.64e^1.92x (female)"' -- reds
       (the quoted formula's own sex label is pinned)."""
    note = BANISTER_TRIMP.note or ""
    inverted_ruling = note.replace(
        "The maintainer ruled 2026-07-27 to keep Banister's 0.64",
        "The maintainer ruled 2026-07-27 to keep Morton's 1.0",
    )
    assert inverted_ruling != note
    assert _normalized(inverted_ruling) != _normalized(BACKSTOP_BANISTER_TRIMP_NOTE)

    moved_page = note.replace(
        "Banister (1991) p. 408 states", "Banister (1991) p. 409 states"
    )
    assert moved_page != note
    assert _normalized(moved_page) != _normalized(BACKSTOP_BANISTER_TRIMP_NOTE)

    swapped_formula = note.replace(
        '"y = 0.64e^1.92x (male)"', '"y = 0.64e^1.92x (female)"'
    )
    assert swapped_formula != note
    assert _normalized(swapped_formula) != _normalized(BACKSTOP_BANISTER_TRIMP_NOTE)


def test_minetti_2002_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (queue 2026-07-28-load-channel-citation-notes-
    unpinned). See test_coggan_tss_note_matches_the_full_pinned_text's
    docstring for the general rationale."""
    note = MINETTI_2002.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_MINETTI_2002_NOTE)


def test_intervals_icu_pace_load_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (queue 2026-07-28-load-channel-citation-notes-
    unpinned). See test_coggan_tss_note_matches_the_full_pinned_text's
    docstring for the general rationale."""
    note = INTERVALS_ICU_PACE_LOAD.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_INTERVALS_ICU_PACE_LOAD_NOTE)


def test_intervals_icu_hrss_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (queue 2026-07-28-load-channel-citation-notes-
    unpinned). See test_coggan_tss_note_matches_the_full_pinned_text's
    docstring for the general rationale."""
    note = INTERVALS_ICU_HRSS.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_INTERVALS_ICU_HRSS_NOTE)


def test_trainingpeaks_coverage_gate_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (queue 2026-07-28-load-channel-citation-notes-
    unpinned). See test_coggan_tss_note_matches_the_full_pinned_text's
    docstring for the general rationale."""
    note = TRAININGPEAKS_COVERAGE_GATE.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_TRAININGPEAKS_COVERAGE_GATE_NOTE)


def test_no_citation_carries_fitdocs_measured_status() -> None:
    """8.2: this feature introduces no FITDOCS_MEASURED constant, though the
    status exists and is exported for a sibling feature to use."""
    assert all(
        citation.verification is not VerificationStatus.FITDOCS_MEASURED
        for citation in CITATIONS
    )


def test_citation_keys_are_unique() -> None:
    """8.8: citations are unique by key."""
    keys = [citation.key for citation in CITATIONS]
    assert len(keys) == len(set(keys))


def test_divergences_include_the_three_known_cases() -> None:
    """8.5: at least the three named divergences are recorded."""
    behaviors = {divergence.behavior for divergence in DIVERGENCES}
    assert len(DIVERGENCES) >= 3

    running_power = [
        d
        for d in DIVERGENCES
        if "running" in d.behavior.lower() and "power" in d.behavior.lower()
    ]
    assert running_power, behaviors
    assert "watts" in running_power[0].fitdocs.lower()
    assert "intervals.icu" in running_power[0].intervals_icu.lower()

    pace_variability = [d for d in DIVERGENCES if "variability" in d.behavior.lower()]
    assert pace_variability, behaviors
    pace_entry = pace_variability[0]
    assert pace_entry.reason.strip() != ""
    assert pace_entry.fitdocs.strip() != ""
    assert "variability" in pace_entry.reason.lower()
    assert "normaliz" in pace_entry.reason.lower()

    for divergence in DIVERGENCES:
        assert divergence.intervals_icu.strip() != ""
        assert divergence.fitdocs.strip() != ""
        assert divergence.reason.strip() != ""

    hr_intensity = [
        d
        for d in DIVERGENCES
        if "heart" in d.behavior.lower() and "intensity" in d.behavior.lower()
    ]
    assert hr_intensity, behaviors
    entry = hr_intensity[0]
    assert "load" in entry.fitdocs.lower() or "load" in entry.reason.lower()
    combined = f"{entry.fitdocs} {entry.reason}".lower()
    assert "intensity" in combined
    # The interop claim, pinned at the strength its citation actually supports.
    # This previously read `"exact" in combined and "match" in combined`,
    # pinning an "exact interop match with intervals.icu's HRSS" that rested
    # entirely on INTERVALS_ICU_HRSS -- a founder's announcement thread
    # establishing that intervals.icu's HR load is HRSS on a 100 = 1h-max-effort
    # scale, and publishing no formula at all. Same name and same scale do not
    # establish numeric equivalence. The entry now claims the scale; this pins
    # the scale claim AND the explicit disclaimer, so the overclaim cannot
    # return silently.
    assert "scale" in combined
    assert "comparable" in combined
    assert "not claimed" in combined
    assert "exact interop match" not in combined, (
        "the heart-rate divergence claims numeric identity with intervals.icu "
        "again; INTERVALS_ICU_HRSS publishes no formula and cannot support it"
    )


def test_divergence_behaviors_are_unique() -> None:
    """8.8: divergences are unique by behavior; Divergence carries no key field."""
    field_names = {field.name for field in dataclasses.fields(Divergence)}
    assert "key" not in field_names
    behaviors = [divergence.behavior for divergence in DIVERGENCES]
    assert len(behaviors) == len(set(behaviors))
