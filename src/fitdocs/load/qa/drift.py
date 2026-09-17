"""Aerobic-decoupling verdict against the published reference point (design:
AerobicDriftCheck, `src/fitdocs/load/qa/drift.py`).

**Consumes the shipped metric verbatim.** This module reads
``DerivedMetrics.decoupling_pct`` and ``.efficiency_factor`` exactly as
`fitdocs.metrics` computed them and recomputes neither (Req 4.1, 9.8). It is
not this feature's module to correct the shipped decoupling definition; the
known confounds (raw speed instead of grade-adjusted pace on a hilly run, the
numerator inconsistencies between the two shipped functions) are recorded in
``qa/sources.py``'s ``DIVERGENCES`` and reported upward to `fit-ingest`, not
forked here.

**Efficiency factor is a basis, never a verdict of its own.** EF has no
absolute reference point and its units differ by sport -- W/bpm on the bike,
m*s^-1/bpm on the run -- so a single activity's EF value admits no threshold.
The feature brief's framing of EF as a signal in its own right is withdrawn;
the withdrawal and its reason are recorded in ``qa/sources.py``. EF is
carried on the reading whenever `DerivedMetrics.efficiency_factor` is
present, independently of whether ``decoupling_pct`` is present -- the two
fields are independently ``None``-able on `DerivedMetrics`, and this module
never fabricates a ``0`` stand-in for either (Req 1.8, 4.5).

**Never raises, depends on no other check** (Req 1.10, 4.7): the reading is
a pure function of ``metrics`` and ``settings`` alone, and nothing is
written back to ``metrics`` (Req 4.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fitdocs.metrics.types import DerivedMetrics

from .types import FlagSettings


class DriftOutcome(StrEnum):
    """The three-value verdict this check can reach (Req 4.2, 4.4). Closed --
    exactly these three."""

    DRIFTED = "drifted"
    COUPLED = "coupled"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class DriftReading:
    """This check's own typed result, before `FlagAssembly` maps it onto the
    contract's three-value verdict vocabulary.

    ``decoupling_pct`` is populated for :data:`DriftOutcome.DRIFTED` and
    :data:`DriftOutcome.COUPLED`, and left ``None`` for
    :data:`DriftOutcome.NOT_ASSESSED` -- there is no figure to report when
    the shipped metric never computed one (Req 1.5, 1.8). ``reference_pct``
    is always the configured threshold, regardless of outcome (Req 4.2).
    ``efficiency_factor`` is carried whenever `DerivedMetrics.efficiency_factor`
    is present, independently of ``decoupling_pct`` and of ``outcome`` --
    never rendered as a fabricated ``0`` (Req 1.8, 4.5). ``not_assessed_reason``
    is populated only for :data:`DriftOutcome.NOT_ASSESSED`.
    """

    outcome: DriftOutcome
    decoupling_pct: float | None
    reference_pct: float
    efficiency_factor: float | None
    not_assessed_reason: str | None


def evaluate(metrics: DerivedMetrics, *, settings: FlagSettings) -> DriftReading:
    """Turn ``metrics.decoupling_pct`` into a verdict against
    ``settings.aerobic_drift_max_pct`` (Req 4.1-4.7).

    **Gate order, exactly** (Req 4.4, 4.2):

    1. ``metrics.decoupling_pct is None`` -> *not-assessed*, stating both
       that the shipped metric was unavailable for this activity and that it
       is defined for the running and cycling modalities only (Req 4.4).
    2. Otherwise, compare against ``settings.aerobic_drift_max_pct``:
       strictly greater than the reference is *drifted*; everything else --
       including exactly equal to the reference -- is *coupled* (Req 4.2).

    ``efficiency_factor`` is carried through from ``metrics.efficiency_factor``
    on every path, independently of which branch above is taken (Req 4.5).
    Pure: reads only ``metrics`` and ``settings``, depends on no other
    check's result, and writes nothing back to ``metrics`` (Req 4.6, 4.7).
    """
    reference_pct = settings.aerobic_drift_max_pct
    efficiency_factor = metrics.efficiency_factor

    if metrics.decoupling_pct is None:
        return DriftReading(
            outcome=DriftOutcome.NOT_ASSESSED,
            decoupling_pct=None,
            reference_pct=reference_pct,
            efficiency_factor=efficiency_factor,
            not_assessed_reason=(
                "the shipped aerobic-decoupling metric was unavailable for "
                "this activity; it is defined for running and cycling only"
            ),
        )

    decoupling_pct = metrics.decoupling_pct
    outcome = (
        DriftOutcome.DRIFTED if decoupling_pct > reference_pct else DriftOutcome.COUPLED
    )
    return DriftReading(
        outcome=outcome,
        decoupling_pct=decoupling_pct,
        reference_pct=reference_pct,
        efficiency_factor=efficiency_factor,
        not_assessed_reason=None,
    )
