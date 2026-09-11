"""Tests for `fitdocs.performance.models` (design: PerformanceModels; task
1.3; Req 2.1, 3.2, 3.7, 4.2, 8.3).

Covers: the Riegel race-equivalence solve and the pace that follows from it,
reproduced against a hand-computed worked example; the time-weighted mean's
consecutive-pair, earlier-sample-credited domain (and its distinction from a
sample-count mean); the recorded span as a sum of positive timestamp deltas;
the round-half-away-from-zero rule for whole bpm and whole watts; and the
absent-value rule (`None`, never a raise or a fabricated zero) for every
input that cannot support a result.
"""

from __future__ import annotations

import math

from fitdocs.model import Samples
from fitdocs.performance import models


def _samples(time_s: tuple[float, ...]) -> Samples:
    """A `Samples` value carrying only `time_s`; the other nine channel
    arrays are irrelevant to every function under test here, which either
    takes `values` as its own separate argument or reads `time_s` alone."""
    return Samples(
        time_s=time_s,
        heart_rate_bpm=(),
        power_w=(),
        cadence_rpm=(),
        speed_mps=(),
        distance_m=(),
        altitude_m=(),
        latitude_deg=(),
        longitude_deg=(),
        temperature_c=(),
    )


# --- riegel_equivalent_distance_m / threshold_pace_s_per_km -----------------


def test_riegel_equivalent_distance_worked_example() -> None:
    """A 5 000 m race in 1 200 s (design's own worked example): the
    one-hour-equivalent distance is `5000 * (3600 / 1200) ** (1 / 1.06)`,
    hand-computed here independently of the module under test at
    ~14095.63 m. Mutation this dies on: the exponent moving from 1.06 to
    1.0, which would instead produce exactly 15000.0 m -- far outside the
    stated tolerance."""
    expected = 5000.0 * (3600.0 / 1200.0) ** (1.0 / 1.06)
    result = models.riegel_equivalent_distance_m(distance_m=5000.0, time_s=1200.0)
    assert result is not None
    assert math.isclose(result, expected, rel_tol=1e-9)
    assert math.isclose(result, 14095.626893163919, rel_tol=1e-6)
    # Falsity in the starting state: the exponent-1.0 mutant's output is far
    # outside the tolerance this assertion enforces.
    assert not math.isclose(result, 15000.0, rel_tol=1e-3)


def test_threshold_pace_composes_the_same_worked_example() -> None:
    """The pace that follows from the same worked example: the one-hour
    solve target (3600 s) divided by the equivalent distance in kilometres,
    `3600 / (14095.626893163919 / 1000)` ~= 255.398 s/km."""
    expected = 3600.0 / (14095.626893163919 / 1000.0)
    result = models.threshold_pace_s_per_km(distance_m=5000.0, time_s=1200.0)
    assert result is not None
    assert math.isclose(result, expected, rel_tol=1e-9)


def test_riegel_equivalent_distance_none_for_non_positive_distance() -> None:
    assert models.riegel_equivalent_distance_m(distance_m=0.0, time_s=1200.0) is None
    assert models.riegel_equivalent_distance_m(distance_m=-5.0, time_s=1200.0) is None


def test_riegel_equivalent_distance_none_for_non_positive_time() -> None:
    assert models.riegel_equivalent_distance_m(distance_m=5000.0, time_s=0.0) is None
    assert models.riegel_equivalent_distance_m(distance_m=5000.0, time_s=-1.0) is None


def test_riegel_equivalent_distance_none_for_non_finite_inputs() -> None:
    assert (
        models.riegel_equivalent_distance_m(distance_m=math.nan, time_s=1200.0) is None
    )
    assert (
        models.riegel_equivalent_distance_m(distance_m=math.inf, time_s=1200.0) is None
    )
    assert (
        models.riegel_equivalent_distance_m(distance_m=5000.0, time_s=math.nan) is None
    )


def test_threshold_pace_none_propagates_from_the_riegel_solve() -> None:
    assert models.threshold_pace_s_per_km(distance_m=0.0, time_s=1200.0) is None
    assert models.threshold_pace_s_per_km(distance_m=5000.0, time_s=0.0) is None


# --- time_weighted_mean -------------------------------------------------


def test_time_weighted_mean_credits_the_earlier_sample() -> None:
    """Three samples, uneven spacing (dt 10 then 30), all three values
    distinct and pairwise different -- built to defeat both a sample-count
    mean (which would give (100+200+300)/3 = 200.0, not 175.0) and a
    later-sample-credit implementation (which would pair dt=10 with 200 and
    dt=30 with 300, giving 275.0, not 175.0). Mutation this dies on:
    crediting `values[i + 1]` instead of `values[i]` to each interval."""
    samples = _samples((0.0, 10.0, 40.0))
    result = models.time_weighted_mean(samples, (100.0, 200.0, 300.0))
    assert result is not None
    assert math.isclose(result, 175.0, rel_tol=1e-9)
    # Falsity in the starting state / sole-failure check: the later-credit
    # and sample-count alternatives are both different values than 175.0.
    assert not math.isclose(result, 275.0, rel_tol=1e-9)
    assert not math.isclose(result, 200.0, rel_tol=1e-9)


def test_time_weighted_mean_skips_none_rather_than_treating_it_as_zero() -> None:
    """A `None` in the middle of the array: the interval it earlier-credits
    is excluded from both the weight and the sum entirely, rather than
    being folded in as a recorded zero. Fixture distinguishes the two: if
    the `None` interval were instead counted with value 0.0, the mean would
    be 4000.0 / 30.0 ~= 133.33, not the correct 4000.0 / 20.0 = 200.0."""
    samples = _samples((0.0, 10.0, 20.0, 30.0))
    result = models.time_weighted_mean(samples, (100.0, None, 300.0, 50.0))
    assert result is not None
    assert math.isclose(result, 200.0, rel_tol=1e-9)
    assert not math.isclose(result, 4000.0 / 30.0, rel_tol=1e-9)


def test_time_weighted_mean_none_for_fewer_than_two_samples() -> None:
    samples = _samples((5.0,))
    result = models.time_weighted_mean(samples, (10.0,))
    assert result is None


def test_time_weighted_mean_none_for_zero_span() -> None:
    samples = _samples((5.0, 5.0, 5.0))
    result = models.time_weighted_mean(samples, (1.0, 2.0, 3.0))
    assert result is None


def test_time_weighted_mean_none_for_wholly_unrecorded_stream() -> None:
    samples = _samples((0.0, 10.0, 20.0))
    result = models.time_weighted_mean(samples, (None, None, None))
    assert result is None


# --- recorded_span_s ------------------------------------------------------


def test_recorded_span_sums_positive_deltas_from_timestamps() -> None:
    """Uneven spacing (10 then 15): a sample-count-based implementation
    (e.g. returning the number of intervals, 2) would produce a value
    indistinguishable in *type* but wrong in *value* -- 2.0 instead of
    25.0. Mutation this dies on: computing span from `len(time_s)` rather
    than from the timestamps themselves."""
    samples = _samples((0.0, 10.0, 25.0))
    result = models.recorded_span_s(samples)
    assert result is not None
    assert math.isclose(result, 25.0, rel_tol=1e-9)
    assert not math.isclose(result, 2.0, rel_tol=1e-9)


def test_recorded_span_skips_non_positive_deltas() -> None:
    """A non-monotonic timestamp array: the middle interval's delta is
    negative and must not contribute (nor subtract). Correct: 10 + 15 = 25.0
    (skipping the -5 interval). A naive `time_s[-1] - time_s[0]` would give
    20.0; a naive sum-including-negative would give 20.0 too -- both wrong
    and both distinct from 25.0."""
    samples = _samples((0.0, 10.0, 5.0, 20.0))
    result = models.recorded_span_s(samples)
    assert result is not None
    assert math.isclose(result, 25.0, rel_tol=1e-9)
    assert not math.isclose(result, 20.0, rel_tol=1e-9)


def test_recorded_span_none_for_fewer_than_two_samples() -> None:
    assert models.recorded_span_s(_samples((5.0,))) is None


def test_recorded_span_none_for_zero_span() -> None:
    assert models.recorded_span_s(_samples((5.0, 5.0, 5.0))) is None


# --- whole_bpm / whole_watts ------------------------------------------------


def test_whole_bpm_rounds_both_halves_away_from_zero() -> None:
    """169.5 and 170.5 both move away from zero (up, since both are
    positive): 169.5 -> 170, 170.5 -> 171. `170.5` is the discriminating
    case against the builtin `round`, which ties to even and would send it
    to 170 instead -- the exact case the design calls out. Mutation this
    dies on: `whole_bpm`/`_round_half_away_from_zero` calling `round()`
    instead of applying the cited offset."""
    assert models.whole_bpm(169.5) == 170
    assert models.whole_bpm(170.5) == 171
    assert round(170.5) == 170  # confirms round() disagrees with this rule


def test_whole_bpm_rounds_a_negative_half_away_from_zero() -> None:
    """-170.5 moves away from zero (down, more negative) to -171, while the
    builtin `round` ties to even and lands on -170 -- confirms the rule is
    symmetric, not merely "round up"."""
    assert models.whole_bpm(-170.5) == -171
    assert round(-170.5) == -170


def test_whole_watts_rounds_both_halves_away_from_zero() -> None:
    assert models.whole_watts(219.5) == 220
    assert models.whole_watts(220.5) == 221
    assert round(220.5) == 220
