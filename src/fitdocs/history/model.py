"""The fitness/fatigue/form recursion itself, and nothing else (load-history
spec, task 2.2; Req 2.1, 2.2, 2.3, 2.9, 2.10). See the "FitnessModel
(`src/fitdocs/history/model.py`)" component in
`.kiro/specs/load-history/design.md`.

This module is pure, stdlib-only (``math.exp``), has no I/O, no clock, no
``Path`` and no document type. It runs the exact exponential recursion
Morton, Fitz-Clarke & Banister (1990) print at eq. (4)/(5) -- one step per
element of the caller's input sequence, which the caller guarantees is one
element per calendar day of the span -- and reports the recursion's own
constant-input asymptotic rescaling (M90 eq. (6)/(7)), never the raw
accumulator. It imports the constant set from
:mod:`fitdocs.history.sources` (task 2.1) and holds no numeric literal of its
own beyond five arithmetic identities: the exponent's own ``-1``, the ``1``
the constant-input rescaling subtracts from, the ``0`` two structural
accumulators start from because the archive begins with no accumulated
history, and the ``0`` each of the two structural guards compares its input
against (``value <= 0`` for a time constant, ``value < 0`` for a weighting
or a load). Each is exempted by site in
``tests/history/test_constant_guard.py``, which this task appends to and
nothing else.

The recursion runs over every day of the span with no knowledge of coverage
or suppression -- Req 3.7's "the recursion continues across a suppressed
period" is exactly this module doing nothing special for one. Suppression is
a reporting decision :mod:`fitdocs.history.series` (a later task) applies
afterwards; this module has no notion of it at all.

Task 2.1's ``sources.py`` already states the weighted combination
(``p(t) = k1*g(t) - k2*h(t)``, M90 eq. (8)) applies the weightings once, at
the combination step, never inside the accumulators -- ``unscaled_accumulators``
below is exactly M90 eq. (4)/(5), unweighted, and ``run_model`` applies each
weighting once, at the point each accumulator is rescaled to the reported
daily-average series.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fitdocs.history.sources import ModelConstants


@dataclass(frozen=True)
class ModelSeries:
    """The reported fitness, fatigue and form series, all three on the
    daily-average scale (Req 2.2) and all three the same length as the
    caller's input sequence."""

    fitness: tuple[float, ...]
    fatigue: tuple[float, ...]
    form: tuple[float, ...]


def _require_positive_finite(name: str, value: float) -> None:
    """Structural guard for a time constant (Req 2.1): a non-positive or
    non-finite value raises. This is a second, structural check -- the
    settings reader (a later task) has already rejected these at the
    user-facing boundary; this module guards its own inputs regardless of
    who calls it."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite, positive number, got {value!r}")


def _require_nonnegative_finite(name: str, value: float) -> None:
    """Structural guard for a weighting or a load (Req 2.1): a negative or
    non-finite value raises."""
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number, got {value!r}")


def _validate_inputs(daily_loads: Sequence[float], constants: ModelConstants) -> None:
    _require_positive_finite("tau_fitness_days", constants.tau_fitness_days)
    _require_positive_finite("tau_fatigue_days", constants.tau_fatigue_days)
    _require_nonnegative_finite("k_fitness", constants.k_fitness)
    _require_nonnegative_finite("k_fatigue", constants.k_fatigue)
    for index, load in enumerate(daily_loads):
        _require_nonnegative_finite(f"daily_loads[{index}]", load)


def _decay(tau_days: float) -> float:
    """M90 eq. (4)/(5)'s own per-step decay factor, ``e^(-1/tau)`` -- the
    exact exponential the primary text prints, never the reciprocal
    approximation vendor documentation uses instead
    (``sources.RECURSION_FORM_CHOICE``)."""
    return math.exp(-1.0 / tau_days)


def _rescale(weighting: float, decay_factor: float) -> float:
    """M90 eq. (6)/(7)'s constant-input asymptotic scale, applied as a
    reporting convention (``sources.DAILY_AVERAGE_SCALE_CHOICE``): a
    weighting times one minus the accumulator's own decay factor."""
    return weighting * (1.0 - decay_factor)


def unscaled_accumulators(
    daily_loads: Sequence[float], constants: ModelConstants
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """M90 eq. (4)/(5), exactly: one step per element of ``daily_loads``,
    each accumulator decaying by ``e^(-1/tau)`` and then adding the day's
    load. Both accumulators start at zero -- the archive begins with no
    accumulated history. Unweighted: the weightings are applied only at
    :func:`run_model`'s combination step, never here."""
    _validate_inputs(daily_loads, constants)
    decay_fitness = _decay(constants.tau_fitness_days)
    decay_fatigue = _decay(constants.tau_fatigue_days)
    fitness_accumulator = fatigue_accumulator = 0.0
    fitness_values: list[float] = []
    fatigue_values: list[float] = []
    for load in daily_loads:
        fitness_accumulator = fitness_accumulator * decay_fitness + load
        fatigue_accumulator = fatigue_accumulator * decay_fatigue + load
        fitness_values.append(fitness_accumulator)
        fatigue_values.append(fatigue_accumulator)
    return tuple(fitness_values), tuple(fatigue_values)


def run_model(daily_loads: Sequence[float], constants: ModelConstants) -> ModelSeries:
    """The reported series (Req 2.2, 2.3): fitness and fatigue on the
    daily-average scale -- each unscaled accumulator times its weighting
    times one minus its own decay factor -- and form as fitness minus
    fatigue. Delegates the recursion itself to
    :func:`unscaled_accumulators`; this function only rescales and
    combines."""
    fitness_accumulators, fatigue_accumulators = unscaled_accumulators(
        daily_loads, constants
    )
    fitness_scale = _rescale(constants.k_fitness, _decay(constants.tau_fitness_days))
    fatigue_scale = _rescale(constants.k_fatigue, _decay(constants.tau_fatigue_days))
    fitness = tuple(value * fitness_scale for value in fitness_accumulators)
    fatigue = tuple(value * fatigue_scale for value in fatigue_accumulators)
    form = tuple(f - h for f, h in zip(fitness, fatigue, strict=True))
    return ModelSeries(fitness=fitness, fatigue=fatigue, form=form)
