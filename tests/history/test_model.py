"""Tests for the recursion's structural guards, its length/identity pins and
the exact relationship between the unscaled accumulators and the reported
series (load-history spec, task 2.2; Req 2.1, 2.2, 2.3, 2.10). The paper's
own worked figures are pinned separately in ``test_worked_examples.py``. See
the "FitnessModel (`src/fitdocs/history/model.py`)" component in
`.kiro/specs/load-history/design.md`.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from fitdocs.history.model import ModelSeries, run_model, unscaled_accumulators
from fitdocs.history.sources import ConstantProvenance, ModelConstants

CONSTANTS = ModelConstants(
    tau_fitness_days=45.0,
    tau_fatigue_days=15.0,
    k_fitness=1.0,
    k_fatigue=2.0,
    provenance=ConstantProvenance.SEEDS,
    origin="test fixture",
)


def _constants(**overrides: object) -> ModelConstants:
    fields = {
        "tau_fitness_days": CONSTANTS.tau_fitness_days,
        "tau_fatigue_days": CONSTANTS.tau_fatigue_days,
        "k_fitness": CONSTANTS.k_fitness,
        "k_fatigue": CONSTANTS.k_fatigue,
        "provenance": CONSTANTS.provenance,
        "origin": CONSTANTS.origin,
    }
    fields.update(overrides)
    return ModelConstants(**fields)  # type: ignore[arg-type]


# --- Structural guards (Req 2.1) --------------------------------------------


@pytest.mark.parametrize(
    "tau_fitness_days",
    [0.0, -45.0, math.nan, math.inf, -math.inf],
)
def test_nonpositive_or_nonfinite_fitness_time_constant_raises(
    tau_fitness_days: float,
) -> None:
    """A non-positive or non-finite fitness time constant raises before any
    accumulation happens. Mutation: delete the `tau <= 0` half of the guard
    condition (leaving only the finiteness check) -- the `0.0` and `-45.0`
    cases stop raising and this test reds."""
    with pytest.raises(ValueError, match="tau_fitness_days"):
        run_model([10.0, 20.0], _constants(tau_fitness_days=tau_fitness_days))


@pytest.mark.parametrize(
    "tau_fatigue_days",
    [0.0, -15.0, math.nan, math.inf],
)
def test_nonpositive_or_nonfinite_fatigue_time_constant_raises(
    tau_fatigue_days: float,
) -> None:
    """Same guard, the fatigue time constant. A distinct assertion from the
    fitness one above: mutating only the fatigue check (e.g. dropping its
    `<= 0` clause) reds this test while leaving the fitness test green,
    proving the two guards are independent, not one shared check that
    happens to run twice."""
    with pytest.raises(ValueError, match="tau_fatigue_days"):
        run_model([10.0, 20.0], _constants(tau_fatigue_days=tau_fatigue_days))


@pytest.mark.parametrize("k_fitness", [-1.0, math.nan, -math.inf])
def test_negative_or_nonfinite_fitness_weighting_raises(k_fitness: float) -> None:
    """A negative or non-finite fitness weighting raises. Mutation: change
    `value < 0` to `value <= 0` in the shared guard -- `k_fitness = 0.0`
    would then wrongly raise, which the next test below catches; changing it
    to drop the negative check entirely leaves `-1.0` un-raised and reds
    here."""
    with pytest.raises(ValueError, match="k_fitness"):
        run_model([10.0, 20.0], _constants(k_fitness=k_fitness))


@pytest.mark.parametrize("k_fatigue", [-2.0, math.nan])
def test_negative_or_nonfinite_fatigue_weighting_raises(k_fatigue: float) -> None:
    with pytest.raises(ValueError, match="k_fatigue"):
        run_model([10.0, 20.0], _constants(k_fatigue=k_fatigue))


def test_zero_weighting_is_permitted() -> None:
    """Falsity-in-the-starting-state / boundary check for the weighting
    guard: zero is non-negative and must NOT raise. Mutation: change the
    weighting guard's `< 0` to `<= 0` -- this test reds because `k_fitness=0`
    would then raise."""
    series = run_model([10.0, 20.0], _constants(k_fitness=0.0, k_fatigue=0.0))
    assert series.fitness == (0.0, 0.0)
    assert series.fatigue == (0.0, 0.0)


@pytest.mark.parametrize("bad_load", [-1.0, math.nan, -math.inf, math.inf])
def test_negative_or_nonfinite_load_raises(bad_load: float) -> None:
    """A negative or non-finite load raises, and a NaN load specifically
    must reach this guard rather than being caught (or silently accepted) by
    an earlier, constants-only check. Mutation: check only `load < 0` without
    `not math.isfinite(load)` -- `math.nan < 0` is `False` in Python, so the
    NaN case would slip through un-raised and this test reds while the
    `-1.0` case (still caught by `< 0`) stays green, proving the two clauses
    are independently exercised."""
    with pytest.raises(ValueError, match=r"daily_loads\[1\]"):
        run_model([10.0, bad_load], CONSTANTS)


def test_bad_load_is_reached_even_when_constants_are_valid() -> None:
    """Reachability check: valid constants alone must not short-circuit
    before the loads are validated. This is exercised by every
    `test_negative_or_nonfinite_load_raises` case above (CONSTANTS is always
    valid there); this test additionally pins that a good first day plus a
    bad second day identifies the offending index."""
    with pytest.raises(ValueError, match=r"daily_loads\[1\]"):
        unscaled_accumulators([5.0, -3.0, 7.0], CONSTANTS)


def test_zero_load_is_permitted() -> None:
    """Boundary check: zero is non-negative and must not raise."""
    series = run_model([0.0, 0.0], CONSTANTS)
    assert series.fitness[0] == 0.0
    assert series.fatigue[0] == 0.0


# --- Length and identity pins (Req 2.1, 2.2) --------------------------------


def test_all_three_output_tuples_have_the_input_length() -> None:
    """Mutation: drop the last day inside the loop (e.g. iterate
    `daily_loads[:-1]`) -- the length assertions red while the values for
    the remaining days are unaffected, isolating a length bug from a value
    bug."""
    loads = [12.0, 0.0, 45.0, 3.0, 8.0, 0.0, 19.0]
    series = run_model(loads, CONSTANTS)
    fitness_acc, fatigue_acc = unscaled_accumulators(loads, CONSTANTS)
    assert len(series.fitness) == len(loads)
    assert len(series.fatigue) == len(loads)
    assert len(series.form) == len(loads)
    assert len(fitness_acc) == len(loads)
    assert len(fatigue_acc) == len(loads)


def test_two_runs_on_the_same_inputs_are_bit_identical() -> None:
    """Determinism pin (design.md invariant): the same inputs give
    bit-identical outputs. Mutation: seed the accumulator from `id(loads)`
    or any other non-deterministic source instead of `0.0` -- this test
    reds because two separately-constructed but equal input lists would then
    diverge."""
    loads_a = [12.0, 0.0, 45.0, 3.0, 8.0]
    loads_b = [12.0, 0.0, 45.0, 3.0, 8.0]
    assert loads_a is not loads_b
    series_a = run_model(loads_a, CONSTANTS)
    series_b = run_model(loads_b, CONSTANTS)
    assert series_a == series_b


def test_reported_series_equals_unscaled_accumulators_times_constant_rescaling() -> (
    None
):
    """Postcondition pin (design.md): `run_model`'s fitness equals
    `unscaled_accumulators`' first tuple times
    `k1 * (1 - exp(-1/tau1))`, elementwise and exactly -- and the fatigue
    analogue. Mutation: compute `fitness_scale` from `tau_fatigue_days`
    instead of `tau_fitness_days` (or equivalently, `_rescale` returning
    `weighting * (1.0 + decay_factor)`) -- either changes the rescale factor
    used against the unscaled accumulators and this exact-equality check
    reds. Applying the weightings inside the recursion instead of at the
    rescaling step does NOT red this test: both `series.fitness` and
    `expected_fitness` would derive from the same already-weighted
    accumulators, so the equality still holds. That mutation is instead
    pinned by `test_worked_examples.py`'s day-60 weighted-difference test,
    which catches it because the fatigue accumulator there is checked
    against the paper's own independently-published figure, not recomputed
    from the same mutated accumulator."""
    loads = [100.0] * 10 + [0.0, 42.0, 0.0, 17.0, 200.0]
    constants = _constants(k_fitness=1.0, k_fatigue=2.0)
    series = run_model(loads, constants)
    fitness_acc, fatigue_acc = unscaled_accumulators(loads, constants)

    fitness_scale = constants.k_fitness * (
        1.0 - math.exp(-1.0 / constants.tau_fitness_days)
    )
    fatigue_scale = constants.k_fatigue * (
        1.0 - math.exp(-1.0 / constants.tau_fatigue_days)
    )
    expected_fitness = tuple(v * fitness_scale for v in fitness_acc)
    expected_fatigue = tuple(v * fatigue_scale for v in fatigue_acc)

    assert series.fitness == expected_fitness
    assert series.fatigue == expected_fatigue
    # Falsity-in-the-starting-state: the unscaled accumulator and the
    # reported series must actually differ (the rescale factor is not 1),
    # otherwise this equality would hold trivially either way.
    assert fitness_scale != 1.0
    assert fatigue_scale != 1.0
    assert fitness_acc != series.fitness
    assert fatigue_acc != series.fatigue


def test_form_is_fitness_minus_fatigue() -> None:
    """Req 2.3. Mutation: change `form` to `fitness + fatigue` -- this test
    reds because fitness and fatigue are both positive and non-zero for this
    fixture."""
    loads = [100.0, 50.0, 0.0, 200.0, 10.0]
    series = run_model(loads, _constants(k_fitness=1.0, k_fatigue=2.0))
    assert series.form == tuple(
        f - h for f, h in zip(series.fitness, series.fatigue, strict=True)
    )
    # The two operands must actually differ, or +/- would be indistinguishable.
    assert series.fitness != series.fatigue


def test_accumulators_start_at_zero_not_seeded_from_the_first_day_twice() -> None:
    """Off-by-one pin (tasks.md named mutation: seed the accumulators with
    the first day's load twice). A single day of load `T` produces an
    unscaled accumulator of exactly `T`, not `T + T*decay`."""
    loads = [100.0]
    fitness_acc, fatigue_acc = unscaled_accumulators(loads, CONSTANTS)
    assert fitness_acc == (100.0,)
    assert fatigue_acc == (100.0,)


# --- Asymptotic convergence (design.md FitnessModel postcondition) ---------


def test_constant_load_converges_to_weighting_times_load() -> None:
    """tasks.md 2.2 / design.md FitnessModel postcondition: "with constant
    load T the fitness series converges to k1*T" -- and, symmetrically, the
    fatigue series to k2*T. k_fitness != k_fatigue (1 vs 2) so a k1/k2 swap
    also reds this test, not just a scale-magnitude change. Mutation:
    `_rescale` returning `weighting * (1.0 + decay_factor)` or
    `weighting / (1.0 - decay_factor)` instead of `weighting * (1.0 -
    decay_factor)` -- both reroute the converged value away from `k*T` and
    this test reds."""
    load = 100.0
    days = 2000
    constants = _constants(k_fitness=1.0, k_fatigue=2.0)
    series = run_model([load] * days, constants)
    assert series.fitness[-1] == pytest.approx(constants.k_fitness * load, abs=1e-6)
    assert series.fatigue[-1] == pytest.approx(constants.k_fatigue * load, abs=1e-6)
    # Falsity-in-the-starting-state: day 0 (the very first accumulated
    # value, k*T*(1 - decay)) has not converged -- it must NOT already
    # equal k*T, or the postcondition would hold trivially even for a
    # constant series that never approaches its asymptote.
    assert series.fitness[0] != pytest.approx(constants.k_fitness * load, abs=1e-6)
    assert series.fatigue[0] != pytest.approx(constants.k_fatigue * load, abs=1e-6)


def test_series_is_a_frozen_dataclass_of_three_tuples() -> None:
    series = run_model([1.0, 2.0], CONSTANTS)
    assert isinstance(series, ModelSeries)
    with pytest.raises(dataclasses.FrozenInstanceError):
        series.fitness = (0.0, 0.0)  # type: ignore[misc]
