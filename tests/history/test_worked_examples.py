"""Proves the recursion against the primary text's own published worked
figures (load-history spec, task 2.2; Req 2.1, 2.2, 2.3, 2.9, 2.10). See
`.kiro/specs/load-history/design.md`'s "FitnessModel" component,
Implementation Notes -- Validation, and `.kiro/specs/load-history/research.md`
("Morton et al.'s illustrative figures are an exact regression vector").

Morton, Fitz-Clarke & Banister (1990) drive their own recursion with a
constant daily training load of 100 for 60 days at tau1 = 45 d (fitness),
tau2 = 15 d (fatigue), k1 = 1, k2 = 2 and print the weighted day-60 pair
``k1*g(60) ~ 3351``, ``k2*h(60) ~ 3044``, their difference ``~307``, and eq.
(11)'s continuous-training asymptote ``~1449``. These are the paper's own
printed figures and the only ones in this literature usable as a vector
(``2026-07-27-banister-figure-captions-unusable-as-vectors``). The published
pair is the *weighted* raw accumulator, not the daily-average-scaled
``run_model`` series -- reading ``3,044`` as a raw fatigue accumulator (i.e.
without the ``k2 = 2`` weighting) is exactly the misreading `k2*h(60)`
forecloses, since only the weighted figure ties out.
"""

from __future__ import annotations

import pytest

from fitdocs.history.model import unscaled_accumulators
from fitdocs.history.sources import ConstantProvenance, ModelConstants

M90_CONSTANTS = ModelConstants(
    tau_fitness_days=45.0,
    tau_fatigue_days=15.0,
    k_fitness=1.0,
    k_fatigue=2.0,
    provenance=ConstantProvenance.SEEDS,
    origin="M90's own worked-example inputs, not the shipped k1/k2 (which "
    "are both 1) -- this fixture exists to reproduce the paper's printed "
    "figures, not to describe fitdocs' shipped defaults.",
)

CONSTANT_LOAD = 100.0
DAYS = 60


def _sixty_days_of_constant_load() -> list[float]:
    return [CONSTANT_LOAD] * DAYS


def test_day_60_weighted_fitness_matches_the_published_figure() -> None:
    """M90's printed ``k1*g(60) ~ 3,351``. Reproduced numerically at
    3350.8 (research.md). Mutation: use ``1/tau`` instead of
    ``1 - exp(-1/tau)`` for the decay factor -- the reciprocal form gives
    3331.5 at day 60, which is already off at the tens digit, let alone the
    third significant figure the tasks.md mutation names; the tight
    absolute tolerance below reds on that mutation while staying green for
    the true implementation."""
    fitness_acc, _ = unscaled_accumulators(
        _sixty_days_of_constant_load(), M90_CONSTANTS
    )
    k1_g60 = M90_CONSTANTS.k_fitness * fitness_acc[DAYS - 1]
    assert k1_g60 == pytest.approx(3350.8, abs=1.0)
    assert round(k1_g60) == 3351


def test_day_60_weighted_fatigue_matches_the_published_figure() -> None:
    """M90's printed ``k2*h(60) ~ 3,044``. Reproduced numerically at
    3044.3. This is the assertion the module docstring calls out: it is
    only true because ``k2 = 2`` is applied -- the raw, unweighted
    accumulator at day 60 is ~1522.2, nowhere near 3,044 -- so this pin
    forecloses reading the published figure as an unweighted accumulator.
    Mutation: drop the ``k2 *`` weighting (read the raw accumulator instead)
    -- this test reds because 1522.2 fails the tolerance against 3044.3,
    while the reciprocal-decay mutation above also reds this assertion
    independently (fatigue accumulates over more decay cycles at the
    shorter tau2, so the reciprocal bias is larger here: 2952.2 vs 3044.3)."""
    fitness_acc, fatigue_acc = unscaled_accumulators(
        _sixty_days_of_constant_load(), M90_CONSTANTS
    )
    k2_h60 = M90_CONSTANTS.k_fatigue * fatigue_acc[DAYS - 1]
    assert k2_h60 == pytest.approx(3044.3, abs=1.0)
    assert round(k2_h60) == 3044
    # Falsity-in-the-starting-state / the unweighted-reading foreclosure:
    # the raw (unweighted) accumulator must NOT itself already equal the
    # published figure, or the weighting could be dropped without this
    # test noticing.
    assert fatigue_acc[DAYS - 1] != pytest.approx(3044.3, abs=1.0)


def test_day_60_weighted_difference_matches_the_published_figure() -> None:
    """M90's printed difference ``~307``. Reproduced numerically at 306.5.
    Mutation: apply the weightings inside the recursion instead of at the
    combination step (tasks.md's named mutation) -- with k2 = 2 this makes
    the fatigue accumulator itself compound at twice the daily load, so
    ``k2*h(60)`` becomes ~6088.6 and the difference goes deeply negative
    (~-2738), nowhere near 306.5."""
    fitness_acc, fatigue_acc = unscaled_accumulators(
        _sixty_days_of_constant_load(), M90_CONSTANTS
    )
    k1_g60 = M90_CONSTANTS.k_fitness * fitness_acc[DAYS - 1]
    k2_h60 = M90_CONSTANTS.k_fatigue * fatigue_acc[DAYS - 1]
    difference = k1_g60 - k2_h60
    assert difference == pytest.approx(306.5, abs=1.0)


def test_continuous_training_asymptote_matches_equation_11() -> None:
    """M90 eq. (11)'s continuous-training asymptote, ``~1,449``. This is the
    weighted, *unscaled*-accumulator asymptote (``k1*g(inf) - k2*h(inf)``,
    reproduced numerically at 1449.07), a different quantity from the
    daily-average-scaled ``run_model`` series (which instead converges to
    ``k1*T`` -- see ``test_model.py``'s
    ``test_constant_load_converges_to_weighting_times_load``). Driven
    here by running the recursion far enough for the accumulators to settle
    to their own steady state under continuous constant training, exactly as
    the module's own recursion computes every other figure in this file --
    no closed-form shortcut. Mutation: use ``1/tau`` instead of
    ``1 - exp(-1/tau)`` -- the reciprocal decay converges to a different
    steady state (``T/(1/tau) = T*tau``: 4500/1500, weighted diff 1500)
    which fails this tolerance."""
    long_run = [CONSTANT_LOAD] * 5000
    fitness_acc, fatigue_acc = unscaled_accumulators(long_run, M90_CONSTANTS)
    asymptote = (
        M90_CONSTANTS.k_fitness * fitness_acc[-1]
        - M90_CONSTANTS.k_fatigue * fatigue_acc[-1]
    )
    assert asymptote == pytest.approx(1449.07, abs=0.5)
    assert round(asymptote) == 1449
    # Sole-failure / falsity-in-the-starting-state: at day 60 the recursion
    # has not yet converged, so day-60's own weighted difference (~306.5)
    # must differ from the asymptote -- otherwise this pin would hold
    # trivially against the day-60 test above rather than proving
    # convergence over a much longer run.
    day_60_difference = (
        M90_CONSTANTS.k_fitness * fitness_acc[DAYS - 1]
        - M90_CONSTANTS.k_fatigue * fatigue_acc[DAYS - 1]
    )
    assert day_60_difference != pytest.approx(1449.07, abs=0.5)
