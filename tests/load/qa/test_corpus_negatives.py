"""Regression fixtures pinning the shipped cadence-lock defaults' false-positive
headroom against the statistics measured over the athlete's real 74-file
corpus (design: CadenceLockDetector; research: ".kiro/specs/activity-qa-flags/
research.md", "Cadence lock" sections and the "Direct measurement over the
real corpus" table).

**These are reconstructed statistics, not the corpus itself.** Every value
built in this module is a constructed :class:`fitdocs.model.Samples` stream
that reproduces the *shape* of a number already published in
``research.md`` -- a correlation, a delta, a duration. The athlete's real
``.fit`` corpus is never added to, referenced by, or read from this
repository (Req 2.11); no file, filename or personal figure beyond the four
aggregate statistics already recorded in ``research.md`` appears here.

Covers Requirement 2.9 (correlated-effort regression) and Requirement 2.11
(constructed-corpus-statistics regression) -- see
``.kiro/specs/activity-qa-flags/requirements.md``.

This module owns the four fixtures below and nothing else; it does not
touch ``test_cadence.py`` or ``test_cadence_spans.py``, whose own
boundaries and coverage are unaffected by this task. Per the "Shared test
fixture" note in ``tasks.md``, this is the one task (besides 2.1) permitted
to extend ``tests/load/qa/conftest.py`` -- this module ends up not needing
to, since ``make_time_s`` and ``make_samples`` are sufficient once combined
with this module's own local construction helpers.

**Fixture-discrimination note for reviewers (fixtures 1-3, the Req 2.11
headroom fixtures only -- fixture 4 is a different species, see its own
docstring).** Each of fixtures 1-3 is built so that exactly *one* of the
two conjunctive conditions (association, closeness) is the reason it
stays CLEAR at the shipped defaults, and so that loosening the *other*
default is a no-op mutation that fixture cannot catch. Precisely one
shipped default is what stands between each of fixtures 1-3 and a LOCKED
verdict; each of their docstrings names, and was verified against, the
specific loosening mutation that flips it.

Fixture 4 (the Req 2.9 correlated-effort regression case) is not built to
this same one-default-away shape -- it is a physiological scenario, not a
corpus-extremum reproduction, and its own docstring states the discrimination
envelope actually measured for it, which involves two defaults rather than
one.
"""

from __future__ import annotations

import math
import statistics

import pytest

from fitdocs.load.qa.cadence import detect
from fitdocs.load.qa.types import (
    DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM,
    DEFAULT_CADENCE_LOCK_MIN_CORRELATION,
    DEFAULT_CADENCE_LOCK_MIN_DURATION_S,
    FlagSettings,
)
from fitdocs.model import Modality
from tests.load.qa.conftest import make_samples, make_time_s

# ---------------------------------------------------------------------------
# Fixture 1 (Req 2.11): the highest whole-activity association observed on
# any real file -- Pearson r = 0.605 (measured on a Ride; Run max was 0.552,
# Run median 0.157) -- held throughout a single configured-width span.
# ---------------------------------------------------------------------------


def _correlated_pair(n: int, *, r: float) -> tuple[list[float], list[float]]:
    """Two length-``n`` series whose Pearson correlation is exactly ``r`` (up
    to the integer rounding the caller applies to one of them), built from
    two mean-zero, unit-scaled vectors that are exactly orthogonal by
    construction: an odd (index-centered, linear) vector ``u`` and an even
    (centered-quadratic) vector ``v``. Over a symmetric index range,
    ``sum(odd * even) == 0`` exactly, so ``corr(u, r*u + sqrt(1-r**2)*v) ==
    r`` holds by the standard two-orthogonal-component construction --
    correlation is invariant to the positive affine rescaling each series
    gets afterward, so the ``r`` achieved here does not depend on the
    caller's chosen offset or scale.
    """
    centered = [i - (n - 1) / 2 for i in range(n)]
    quadratic = [x * x for x in centered]
    mean_quadratic = sum(quadratic) / n
    v = [x - mean_quadratic for x in quadratic]

    assert abs(sum(a * b for a, b in zip(centered, v, strict=True))) < 1e-6, (
        "orthogonality construction violated"
    )

    std_u = statistics.stdev(centered)
    std_v = statistics.stdev(v)
    u_n = [x / std_u for x in centered]
    v_n = [x / std_v for x in v]

    combined = [r * a + math.sqrt(1 - r**2) * b for a, b in zip(u_n, v_n, strict=True)]
    return u_n, combined


def test_max_observed_whole_activity_correlation_stays_clear() -> None:
    """Three successive 120s spans (the default ``cadence_lock_window_s``,
    sustained long enough to clear the default 300s minimum *if* it were
    to lock) whose heart-rate/cadence association is held at r = 0.605 in
    every span -- the highest whole-activity Pearson correlation observed
    on any real file in the corpus (a Ride; the real-run max was 0.552, run
    median 0.157; ``research.md``, "Direct measurement over the real
    corpus"). The numerical closeness condition is also satisfied in every
    span (median delta ~4.3 bpm, under the 5.0 bpm default) so that only
    the correlation threshold is what keeps this fixture CLEAR -- proving
    the fixture genuinely discriminates on
    ``DEFAULT_CADENCE_LOCK_MIN_CORRELATION`` (Req 2.11). Three spans, all
    at the shipped defaults with no override, is deliberate: a single
    locked 120s span would still read CLEAR against the shipped 300s
    minimum regardless of the correlation threshold, which would make the
    fixture's outcome insensitive to the very default it is meant to pin.

    Margin recorded: the shipped default is 0.90; the corpus's own highest
    observed association is 0.605, leaving 0.90 - 0.605 = 0.295 of headroom
    -- more than 30% of the threshold's own value.

    Discrimination mutation (independently re-verified in isolation --
    see the implementer's self-review): lowering
    ``DEFAULT_CADENCE_LOCK_MIN_CORRELATION`` to 0.5 (below the ~0.605 this
    fixture achieves) flips the outcome to LOCKED (locked_duration_s =
    360.0 >= the shipped 300s minimum), because the closeness condition is
    already satisfied in every span of this fixture.
    """
    r_target = 0.605
    span_count = 3
    window_s = 120  # DEFAULT_CADENCE_LOCK_WINDOW_S
    n = span_count * window_s + 1
    time_s = make_time_s(n, dt=1.0)

    offset = 175.0
    scale = 6.0
    full_cycle = [0.0] * n
    heart_rate_bpm_list = [0] * n
    for span_index in range(span_count):
        u_n, combined = _correlated_pair(window_s, r=r_target)
        for j in range(window_s):
            gi = span_index * window_s + j
            full_cycle[gi] = offset + scale * u_n[j]
            heart_rate_bpm_list[gi] = round(offset + scale * combined[j])
    # The trailing sample (index n - 1) falls outside every full-width span
    # (span_statistics's own half-open [start, start + window_s) rule) --
    # its value is never read by the detector, but every channel still
    # needs a concrete value rather than a fabricated gap.
    full_cycle[-1] = offset
    heart_rate_bpm_list[-1] = round(offset)

    cadence_rpm = tuple(v / 2 for v in full_cycle)
    heart_rate_bpm = tuple(heart_rate_bpm_list)

    samples = make_samples(
        time_s, heart_rate_bpm=heart_rate_bpm, cadence_rpm=cadence_rpm
    )

    # Check the statistics achieved within the first span only (every span
    # is built from the same construction and is statistically identical).
    r_actual = statistics.correlation(heart_rate_bpm[:window_s], full_cycle[:window_s])
    deltas = [
        abs(h - c)
        for h, c in zip(heart_rate_bpm[:window_s], full_cycle[:window_s], strict=True)
    ]
    median_delta = statistics.median(deltas)

    assert r_actual == pytest.approx(r_target, abs=0.02)
    assert median_delta <= DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM

    margin = DEFAULT_CADENCE_LOCK_MIN_CORRELATION - r_actual
    assert margin > 0.30 * DEFAULT_CADENCE_LOCK_MIN_CORRELATION

    reading = detect(samples, modality=Modality.RUN, settings=FlagSettings())

    assert reading.spans_assessed == span_count
    assert reading.locked_duration_s == 0.0
    assert reading.outcome.value == "clear"


# ---------------------------------------------------------------------------
# Fixture 2 (Req 2.11): the smallest per-file median separation between HR
# and full-cycle cadence observed on any real file -- 9 bpm (the per-run
# range was 9-90 bpm median |HR - 2*cadence|) -- held throughout.
# ---------------------------------------------------------------------------


def test_min_observed_median_delta_stays_clear() -> None:
    """A stream whose |HR - full-cycle cadence| is held at exactly 9 bpm
    throughout -- the smallest per-file median separation observed on any
    real run in the corpus (the per-run range was 9-90 bpm;
    ``research.md``, "Direct measurement over the real corpus"). The
    association is held at a perfect r = 1.0 (HR is a constant 9 bpm offset
    from full-cycle cadence, and correlation is invariant to a constant
    shift) so that only the closeness threshold is what keeps this fixture
    CLEAR -- proving the fixture genuinely discriminates on
    ``DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM`` (Req 2.11).

    Margin recorded: the shipped default is 5.0 bpm; the corpus's own
    smallest observed separation is 9 bpm, a 4 bpm gap the real corpus
    never closed.

    Built as three successive 120s spans (the default
    ``cadence_lock_window_s``) -- 360s total -- rather than one, and
    evaluated with no settings override at all (every threshold, including
    the 300s minimum duration, is the shipped default). A single locked
    120s span would still read CLEAR regardless of the closeness threshold,
    which would make the fixture insensitive to the very default under
    test; three spans make the outcome genuinely depend on it.

    Discrimination mutation (independently re-verified in isolation --
    see the implementer's self-review): raising
    ``DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM`` to 10.0 (above the 9 bpm this
    fixture holds) flips the outcome to LOCKED (locked_duration_s = 360.0
    >= the shipped 300s minimum), because the association condition is
    already satisfied (r = 1.0) in every span of this fixture.
    """
    span_count = 3
    window_s = 120  # DEFAULT_CADENCE_LOCK_WINDOW_S
    n = span_count * window_s + 1
    time_s = make_time_s(n, dt=1.0)
    cadence_rpm = tuple(80.0 + (i % 10) * 0.5 for i in range(n))
    full_cycle = [c * 2 for c in cadence_rpm]
    heart_rate_bpm = tuple(int(fc) + 9 for fc in full_cycle)

    samples = make_samples(
        time_s, heart_rate_bpm=heart_rate_bpm, cadence_rpm=cadence_rpm
    )

    r_actual = statistics.correlation(heart_rate_bpm[:window_s], full_cycle[:window_s])
    deltas = [
        abs(h - c)
        for h, c in zip(heart_rate_bpm[:window_s], full_cycle[:window_s], strict=True)
    ]
    median_delta = statistics.median(deltas)

    assert r_actual == pytest.approx(1.0)
    assert median_delta == pytest.approx(9.0)
    assert r_actual >= DEFAULT_CADENCE_LOCK_MIN_CORRELATION

    margin = median_delta - DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM
    assert margin == pytest.approx(4.0)

    reading = detect(samples, modality=Modality.RUN, settings=FlagSettings())

    assert reading.spans_assessed == span_count
    assert reading.locked_duration_s == 0.0
    assert reading.outcome.value == "clear"


# ---------------------------------------------------------------------------
# Fixture 3 (Req 2.11): the worst-case locked-duration accumulation observed
# anywhere in the real corpus under the conjunctive rule -- 137s -- against
# the shipped 300s minimum (design's own "better than 2x headroom" claim in
# qa/types.py's DEFAULT_CADENCE_LOCK_MIN_DURATION_S docstring).
# ---------------------------------------------------------------------------


def test_max_observed_locked_duration_stays_clear() -> None:
    """137 seconds of spans that meet both the association and the
    closeness conditions -- the worst-case locked-duration accumulation
    observed anywhere in the real corpus under the conjunctive rule
    (``research.md``, "Direct measurement over the real corpus": "invariant
    across r in {0.80, 0.90, 0.95} and delta in {3, 5, 10}").

    Reproduced exactly (not merely approximated) using 137 successive
    ``window_s = 1`` second spans -- the narrowest span width the shipped
    conjunctive rule can be evaluated at, and the only one that lets a
    whole-second sum land on 137 exactly rather than rounding to the
    nearest multiple of the shipped 120s default width. The minimum lock
    *duration* under test is still the shipped default, 300s -- only the
    span *width* is narrowed to hit the measured figure exactly; the
    conjunctive per-span rule itself (association >= 0.90 and delta <= 5.0
    bpm, both at their shipped defaults) is untouched.

    This is the test that backs the "better than 2x headroom" claim already
    written into ``DEFAULT_CADENCE_LOCK_MIN_DURATION_S``'s own docstring in
    ``qa/types.py`` -- before this task, that claim rested on prose alone.

    Margin recorded: 300 - 137 = 163s, i.e. better than 2x the measured
    worst case, matching the docstring's claim.

    Discrimination mutation (independently re-verified in isolation -- see
    the implementer's self-review): lowering
    ``DEFAULT_CADENCE_LOCK_MIN_DURATION_S`` to anything at or below 137
    flips the outcome to LOCKED, since every one of this fixture's 137
    one-second spans is independently locked (r = 1.0, delta = 0 bpm, both
    comfortably inside the shipped per-span thresholds).
    """
    dt = 0.5
    total_span_count = 137
    # +1 sample so the last span's end boundary (t=137.0) is reached.
    n = total_span_count * 2 + 1
    time_s = make_time_s(n, dt=dt)
    # Full-cycle cadence increments by 1.0 bpm every sample (0.5 per
    # half-second step), so every 1s span holds two *distinct* integer
    # full-cycle values -- correlation is non-degenerate (r = 1.0 for any
    # two distinct points) and HR tracks it exactly (delta = 0).
    cadence_rpm = tuple(80.0 + i * 0.5 for i in range(n))
    full_cycle = [c * 2 for c in cadence_rpm]
    heart_rate_bpm = tuple(int(fc) for fc in full_cycle)

    samples = make_samples(
        time_s, heart_rate_bpm=heart_rate_bpm, cadence_rpm=cadence_rpm
    )

    settings = FlagSettings(cadence_lock_window_s=1)  # min_duration_s left at default
    reading = detect(samples, modality=Modality.RUN, settings=settings)

    assert reading.spans_assessed == total_span_count
    assert reading.locked_duration_s == pytest.approx(float(total_span_count))
    assert reading.required_duration_s == DEFAULT_CADENCE_LOCK_MIN_DURATION_S
    assert reading.outcome.value == "clear"

    margin = DEFAULT_CADENCE_LOCK_MIN_DURATION_S - total_span_count
    assert margin == 163
    assert margin > DEFAULT_CADENCE_LOCK_MIN_DURATION_S / 2


# ---------------------------------------------------------------------------
# Fixture 4 (Req 2.9): the correlated-effort case, explicitly -- heart rate
# and cadence both rise and fall together as a genuine consequence of
# effort, distinct from a flat whole-activity-correlation fixture.
# ---------------------------------------------------------------------------


def test_correlated_effort_rises_and_falls_together_stays_clear() -> None:
    """Heart rate and full-cycle cadence both ramp up together over the
    first half of the activity and back down over the second half -- the
    physiological shape of a genuinely hard, correlated effort, not a flat
    sensor-artifact correlation (Req 2.9). Cadence moves in a narrow band
    (165 to 180 steps/min, typical of running) while heart rate moves in a
    much wider band (110 to 165 bpm, typical of a hard effort); both climb
    and fall on the same triangular time course, so every 120s span's
    correlation is very high (>0.99, well above the 0.90 threshold on its
    own) -- yet the two series never come numerically close (the smallest
    observed gap across the whole activity is far above 5 bpm), so the
    conjunctive rule's closeness condition is what correctly keeps this
    CLEAR. This is the case a naive whole-activity-correlation-only
    detector (rejected by this feature's per-span, conjunctive design)
    would most plausibly misfire on.

    Unlike fixtures 1-3, this fixture is not a corpus-extremum reproduction
    held exactly one default away from LOCKED -- it is a physiological
    scenario, and its actual discrimination envelope (measured directly,
    per span) is wider and involves two shipped defaults, not one:
    - The fixture's own ``min_gap`` self-check below -- the smallest
      |HR - full-cycle cadence| gap anywhere in the whole stream, measured
      at ~14.9 bpm -- is the most sensitive guard: it reds as soon as
      ``cadence_lock_max_delta_bpm`` is loosened to 14.9 or above, before
      any span would actually lock.
    - The detector's own ``locked_duration_s == 0.0`` assertion is the
      next: the middle span's own *median* delta (18.75 bpm, a looser
      figure than the raw minimum gap because a median discards the more
      extreme points within the span) is what it takes for one span to
      lock (120s) -- reds once ``cadence_lock_max_delta_bpm`` is loosened
      to 18.75 or above.
    - The *outcome* itself does not flip to LOCKED until a third span also
      clears its own (higher) median delta, which needs
      ``cadence_lock_max_delta_bpm`` loosened past 31.025 (measured: CLEAR
      with locked_duration_s=240.0 at 31.025, LOCKED with
      locked_duration_s=360.0 at 31.03) -- only then does the accumulated
      360s clear the shipped 300s minimum duration default too.
    """
    n = 600 + 1  # 600s at 1Hz -> five full 120s spans
    time_s = make_time_s(n, dt=1.0)
    mid = n // 2

    def effort(i: int) -> float:
        if i <= mid:
            return i / mid
        return (n - 1 - i) / (n - 1 - mid)

    cadence_steps = [165.0 + 15.0 * effort(i) for i in range(n)]  # 165 -> 180 -> 165
    cadence_rpm = tuple(c / 2 for c in cadence_steps)
    heart_rate_bpm = tuple(
        round(110.0 + 55.0 * effort(i)) for i in range(n)
    )  # 110 -> 165 -> 110

    min_gap = min(
        abs(h - c) for h, c in zip(heart_rate_bpm, cadence_steps, strict=True)
    )
    assert min_gap > DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM

    samples = make_samples(
        time_s, heart_rate_bpm=heart_rate_bpm, cadence_rpm=cadence_rpm
    )

    reading = detect(samples, modality=Modality.RUN, settings=FlagSettings())

    assert reading.spans_assessed == 5
    assert reading.locked_duration_s == 0.0
    assert reading.outcome.value == "clear"

    # Confirm the correlation genuinely was high enough that only the
    # closeness condition -- not the association condition -- is doing the
    # discriminating work here (otherwise this would coincide with fixture
    # 1's test rather than being its own regression case, per Req 2.9).
    r_first_span = statistics.correlation(heart_rate_bpm[:120], cadence_steps[:120])
    assert r_first_span >= DEFAULT_CADENCE_LOCK_MIN_CORRELATION
