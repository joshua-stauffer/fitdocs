"""Reproduces each published work's own worked example for every Req 15.1
(``Citation``-sourced) constant task 9.3's ``CONSTANT_SOURCES`` registers
(task 12.3; Req 15.1). Boundary: :mod:`fitdocs.metrics.stress`
(``StressMetrics``) and :mod:`fitdocs.metrics.power` (``PowerSeriesMetrics``).

**Scope.** ``CONSTANT_SOURCES`` binds ten values to five records; three --
``NP_MIN_SPAN_S``, ``MOVING_SPEED_THRESHOLD_MPS``, ``ALTITUDE_SMOOTHING_WINDOW``
-- are ``FitdocsChoice``-sourced (no published work to quote, so no worked
example is owed to them; see their own ``search_basis`` fields in
``fitdocs.metrics.sources``). The remaining seven are ``Citation``-sourced:
the four training-impulse terms (``BANISTER_MALE_COEFFICIENT/EXPONENT``,
``BANISTER_FEMALE_COEFFICIENT/EXPONENT``, all governed by ``BANISTER_1991``)
and three power/TSS terms (``TSS_SCALE``, ``NP_ROLLING_WINDOW_S``,
``NP_AVERAGING_EXPONENT``, all governed by ``COGGAN_2003``). ``MORTON_1990``
is a corroborator only and governs none of the ten -- confirmed below rather
than assumed.

**Banister (1991) is a trap, not an omission.** B91 p. 408 states the formula
(``y = 0.64e^1.92x`` male, ``y = 0.86e^1.67x`` female,
``w(t) = T * DeltaHR_ratio * y``) and Figs. 9.5/9.6 (pp. 409-410) print three
worked examples -- none of which names a sex or either curve at all; the
captions state only inputs, a stated "y multiplier", and a stated result.
Two of the three captions are internally consistent with their own stated
multiplier and inputs: Fig. 9.6's first example exactly
(``60 * 0.6 * 1.8 = 64.8``), and Fig. 9.5's to the precision its own
"about" claims (``10 * 0.6667 * 2.5 = 16.667`` against a stated ~16.6).
Neither is recomputed by an assertion in this file -- only Fig. 9.6's second
example is, by the third-caption test below, because it is the one that
fails: it is not consistent with its own stated multiplier
(``18 * 0.2 * 0.2 = 0.72``, not the caption's stated ``0.9``). Per
design.md's "Worked examples" gate and this session's own read of the page
scans (``bannister_physiological_testing_of_the_high_performance_athlete/
Screenshot 2026-07-27 at 22.42.24.png``, pp. 408-409), the worked examples
below are **computed from the formula under test and labelled as computed**,
citing B91 for the *formula* only and explicitly not for the caption's
*numbers* -- reading the exponential base as Python's ``math.e``, never B91's
misprinted ``2.712`` (p. 408).

**Coggan (2003) publishes no worked numeric IF/TSS example.** This session
fetched and read the manuscript ``COGGAN_2003`` cites
(ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf, printed pp. 8-11, 22 pages
total) end to end: it states the eight computation steps (already quoted
verbatim on ``COGGAN_2003.note``) and two qualitative band tables -- IF
(``<0.75`` recovery ... ``>1.15`` level 5) and TSS severity
(``<150`` low ... ``>450`` epic) -- but at no point states a worked numeric
example computing a specific IF or TSS value from concrete power figures; a
search of the full text for a wattage pairing that would produce one (for
example ``210``/``280``, a round pair yielding IF ``0.75``) found neither
figure anywhere in the document. Per tasks.md 12.3 / design.md's "Worked
examples" gate (design.md:1691) -- "where the work publishes no worked
example, the test records that explicitly rather than inventing one" -- no
substitute numeric example is manufactured for these three
constants below; the record's own text is instead pinned as the steps that
ARE stated (the actual guard against a future editor planting a fabricated
worked example into the record is ``test_sources.py``'s whole-note pin,
``test_coggan_2003_note_matches_the_full_pinned_text`` -- see that test's
own PRESERVED-ONLY note below for why this file's local substring checks do
not themselves discriminate a fabrication).
"""

from __future__ import annotations

import math

import pytest

from fitdocs.citation import Citation, FitdocsChoice
from fitdocs.metrics import sources, stress
from fitdocs.metrics.types import TrimpWeighting
from fitdocs.model import Samples

_MALE_PAIR = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]
_FEMALE_PAIR = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_FEMALE]


def _samples(
    time_s: tuple[float, ...], heart_rate_bpm: tuple[int | None, ...]
) -> Samples:
    """A ``Samples`` with only the heart-rate channel populated -- every
    other channel is an all-``None`` array of the same length as ``time_s``,
    matching :mod:`tests.metrics.test_stress`'s own builder."""
    n = len(time_s)
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm,
        power_w=(None,) * n,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


# --- 0. Scope: which of the ten CONSTANT_SOURCES bindings this task owes ----


def test_citation_sourced_constants_are_the_seven_banister_and_coggan_terms() -> None:
    """``CONSTANT_SOURCES`` holds ten bindings; the ``Citation``-sourced
    subset -- the ones tasks.md 12.3's worked-example clause applies to -- must
    be exactly the four Banister training-impulse terms plus the three Coggan
    power/TSS terms, never more (a FitdocsChoice value would be misclassified
    as owing a published-work example) and never fewer (a Citation-sourced
    value silently dropped from this test's scope)."""
    citation_sourced = {
        c.name for c in sources.CONSTANT_SOURCES if isinstance(c.source, Citation)
    }
    fitdocs_chosen = {
        c.name for c in sources.CONSTANT_SOURCES if isinstance(c.source, FitdocsChoice)
    }
    assert citation_sourced, "CONSTANT_SOURCES scan found no Citation-sourced constant"
    assert citation_sourced == {
        "trimp_coefficient_banister_male",
        "trimp_exponent_banister_male",
        "trimp_coefficient_banister_female",
        "trimp_exponent_banister_female",
        "tss_scale",
        "np_rolling_window_s",
        "np_averaging_exponent",
    }
    # The three FitdocsChoice values carry no published work to quote and are
    # excluded from this file's scope by design -- named, not merely absent.
    assert fitdocs_chosen == {
        "np_min_span_s",
        "moving_speed_threshold_mps",
        "altitude_smoothing_window",
    }
    # Every constant is one or the other -- no third, unclassified shape.
    all_names = {c.name for c in sources.CONSTANT_SOURCES}
    assert citation_sourced | fitdocs_chosen == all_names


def test_banister_1991_governs_exactly_the_four_trimp_terms() -> None:
    governed = {
        c.name for c in sources.CONSTANT_SOURCES if c.source is sources.BANISTER_1991
    }
    assert governed == {
        "trimp_coefficient_banister_male",
        "trimp_exponent_banister_male",
        "trimp_coefficient_banister_female",
        "trimp_exponent_banister_female",
    }


def test_coggan_2003_governs_exactly_the_three_np_tss_terms() -> None:
    governed = {
        c.name for c in sources.CONSTANT_SOURCES if c.source is sources.COGGAN_2003
    }
    assert governed == {"tss_scale", "np_rolling_window_s", "np_averaging_exponent"}


def test_morton_1990_governs_no_constant_but_is_not_unreachable() -> None:
    """MORTON_1990 is a corroborator only (task 12.3's task description) --
    it must govern zero entries in the registry, but it must still be
    *reachable* as a corroborator (otherwise "corroborator only" would be
    indistinguishable from "absent entirely", the vacuous-walk trap)."""
    governed = [
        c.name for c in sources.CONSTANT_SOURCES if c.source is sources.MORTON_1990
    ]
    assert governed == []
    corroborating_keys = {
        corroboration.citation.key
        for c in sources.CONSTANT_SOURCES
        for corroboration in c.corroborators
    }
    assert corroborating_keys, "no corroborator reachable in the registry at all"
    assert "morton_1990" in corroborating_keys


# --- 1. Banister (1991) TRIMP worked example -- computed, not captioned ----


def test_banister_male_worked_example_is_computed_not_the_contradicting_caption() -> (
    None
):
    """Source: Banister (1991) p. 408 -- formula only
    (``y = 0.64e^1.92x``, ``w(t) = T * DeltaHR_ratio * y``); Fig. 9.5's
    caption (p. 409) supplies the *inputs* only (T=10 min, HR=150 bpm,
    HR_max=200 bpm assumed, HR_rest=50 bpm assumed) -- its own stated outputs
    (``y multiplier = 2.5``, "training impulses of about 16.6 units") are
    NOT used: they contradict the formula on the page before them (verified
    by hand below), which is the trap task 12.3 exists to avoid pinning.

    Inputs: T=10 min (dt=600 s, one sample pair), HR=150, HR_max=200,
    HR_rest=50.
    Expected result (computed from the formula, not quoted from the caption):
        x = (150 - 50) / (200 - 50) = 0.6666666666666666
        y = 0.64 * e^(1.92 * x) = 2.30184942436434
        trimp = 10 * x * y = 15.345662829095598
    """
    x = (150.0 - 50.0) / (200.0 - 50.0)
    expected = 10.0 * x * (0.64 * math.exp(1.92 * x))
    assert expected == pytest.approx(15.345662829095598, rel=1e-12)

    samples = _samples((0.0, 600.0), heart_rate_bpm=(150, None))
    result = stress.trimp(samples, resting_hr=50, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(expected, rel=1e-12)
    # For the record, not as a second pin: the caption's own stated result
    # (~16.6) is not what the cited formula produces -- 15.3457 sits 7.56%
    # away from it. An `assert result.value != approx(16.6)` here would be
    # a tautology over the value the line above already pins to 1e-12, so it
    # would read as discrimination while being unable to fail on its own.


def test_banister_female_worked_example_is_computed_b91_prints_none() -> None:
    """Source: Banister (1991) p. 408 -- formula only
    (``y = 0.86e^1.67x``, ``w(t) = T * DeltaHR_ratio * y``). B91 prints no
    worked *example* for the female curve anywhere: Fig. 9.4 plots the curve
    shape only, and Figs. 9.5/9.6's captions name no sex and no curve at
    all -- they state only inputs, a "y multiplier", and a result. None of
    the three stated multipliers (2.5, 1.8, 0.2) reproduces either curve's
    own formula output at the caption's own x: at Fig. 9.5's x = 0.6667 the
    male formula gives 2.3018 (|Delta| = 0.198 from the caption's 2.5) and
    the female formula gives 2.6183 (|Delta| = 0.118) -- the female curve is
    numerically the *closer* of the two, not the male curve, so "the
    captions are the male curve" is not a claim these numbers support
    either way. No B91 caption is therefore usable as a female-curve
    worked example on any reading. This is instead computed from the
    formula under test using the same inputs as the male example above,
    for direct comparison, and labelled as computed -- not reproducing any
    B91 caption, because none exists for this curve.

    Inputs (same as the male example, for comparability): T=10 min, HR=150,
    HR_max=200, HR_rest=50.
    Expected result:
        x = 0.6666666666666666 (unchanged)
        y = 0.86 * e^(1.67 * x) = 2.6182612268905916
        trimp = 10 * x * y = 17.455074845937276
    """
    x = (150.0 - 50.0) / (200.0 - 50.0)
    expected = 10.0 * x * (0.86 * math.exp(1.67 * x))
    assert expected == pytest.approx(17.455074845937276, rel=1e-12)

    samples = _samples((0.0, 600.0), heart_rate_bpm=(150, None))
    result = stress.trimp(samples, resting_hr=50, max_hr=200, weighting=_FEMALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(expected, rel=1e-12)
    # Distinguishes the female curve's output from the male curve's for the
    # identical input -- proves the selected pair's own coefficient/exponent
    # drove the number, not a shared/default pair.
    male_x = x
    male_expected = 10.0 * male_x * (0.64 * math.exp(1.92 * male_x))
    assert result.value != pytest.approx(male_expected, rel=1e-9)


def test_banister_third_caption_is_not_even_internally_consistent() -> None:
    """Fig. 9.6's third worked example (p. 410) states T=18 min, HR=80 bpm,
    HR_max=200, HR_rest=50, "y multiplier = 0.2", "score only 0.9 units per
    interval" -- but the caption's OWN arithmetic does not reproduce its own
    stated result: T * x * y = 18 * 0.2 * 0.2 = 0.72, not the caption's
    stated 0.9. This is verified directly (not quoting a summary) and is a
    second, independent reason (beyond disagreeing with the p. 408 formula)
    that no B91 caption number is trusted as a test vector anywhere in this
    file."""
    caption_x = 0.2
    caption_y = 0.2
    caption_t = 18
    caption_stated_trimp = 0.9
    reproduced_from_captions_own_terms = caption_t * caption_x * caption_y
    assert reproduced_from_captions_own_terms == pytest.approx(0.72, rel=1e-9)
    assert reproduced_from_captions_own_terms != pytest.approx(
        caption_stated_trimp, rel=1e-9
    )


# --- 2. Coggan (2003) -- no worked numeric IF/TSS example is published -----


def test_coggan_2003_note_states_the_eight_steps_and_no_numeric_example() -> None:
    """``COGGAN_2003.note`` already transcribes the eight computation steps
    (this session's own read of pp. 8-11, verified against the fetched
    manuscript) -- pinned here as the steps that ARE stated. No worked
    numeric IF or TSS example (a stated NP/FTP pair computing to a specific
    IF, or a stated work/threshold pair computing to a specific TSS) is
    stated anywhere in the manuscript.

    PRESERVED-ONLY, not pinned here: the actual guard against a future
    editor silently attributing a fabricated worked example to Coggan
    (2003) is ``test_sources.py::
    test_coggan_2003_note_matches_the_full_pinned_text``, which requires
    the *entire* note to equal a character-for-character copy of the text
    this session read from pp. 8-11 -- any inserted numeric example, of
    any wording, reds that whole-note pin. This test's own substring
    checks below do not themselves catch a fabricated example (a mutation
    that appends unrelated fabricated prose leaves them all green); they
    exist only to pin the steps that ARE stated, not to guard against
    invented ones. There is deliberately no local "no fabricated example"
    substring assertion here: Coggan p. 11 legitimately prints ``<0.75``
    in its IF band table, so a substring check against that literal would
    red on a truthful future transcription of that table, not only on a
    fabrication."""
    note = sources.COGGAN_2003.note
    assert note is not None
    assert "starting at 30 s, calculate a 30 second rolling average" in note
    assert "4th power" in note
    assert "4th root" in note
    assert "multiply by 100" in note


def test_tss_scale_np_window_and_np_exponent_have_no_worked_example_owed() -> None:
    """Documents, rather than invents, the "no worked example" outcome for
    all three Coggan-governed constants at once: each is read directly off
    one of the eight steps quoted on ``COGGAN_2003.note`` (the window width
    off step 1, the averaging exponent off steps 2-4, the scale off step 8)
    rather than off any worked numeric example, because the manuscript
    states none. This is a legitimate, required outcome under tasks.md
    12.3 / design.md's "Worked examples" gate (design.md:1691) -- not a gap
    silently left unaddressed."""
    assert sources.TSS_SCALE.source is sources.COGGAN_2003
    assert sources.NP_ROLLING_WINDOW_S.source is sources.COGGAN_2003
    assert sources.NP_AVERAGING_EXPONENT.source is sources.COGGAN_2003
    assert sources.TSS_SCALE.value == 100.0
    assert sources.NP_ROLLING_WINDOW_S.value == 30
    assert sources.NP_AVERAGING_EXPONENT.value == 4
