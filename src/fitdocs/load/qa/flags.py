"""Assemble the four checks' readings into the load contract's quality
verdicts (design: FlagAssembly, `src/fitdocs/load/qa/flags.py`).

**The only module in this package that imports the load contract.** Every
other module here stays independent of `fitdocs.load.types`; this one reads
`QualityFlag` because it is the one place a reading is rendered into the
contract's `detected` / `not-detected` / `not-assessed` vocabulary. No cycle
guard of this feature's own is needed -- `training-load`'s
`TYPE_CHECKING`-only import of `LoadSettings` in `load/types.py` keeps
`load/settings.py` above `load/types.py`, which is what would otherwise
loop back here.

**Runs every check unconditionally** (Req 1.6): a check's absence from the
record must never be how a reader learns it did not apply -- only its own
*not-assessed* verdict says that. **Emits in `FLAG_ORDER`, always** (Req
1.7): the output tuple's order is fixed independently of the order the four
`evaluate`/`detect` calls happen to return in, and independently of which
verdicts were reached.

**The outcome-to-verdict mapping is total, explicit and per check** -- never
a name-based coincidence across the four different outcome enums. Each of
the four mapping functions below is a `match` over its own check's closed
`StrEnum`, folded with `typing.assert_never` on the catch-all branch, so a
future member added to any of the four outcome enums without a
corresponding `case` here is a type-checker error under `mypy --strict`
(unreachable `assert_never` call) and an `AssertionError` at runtime if it
is ever reached anyway -- never a silent fall-through.

**Basis strings are owned here, from typed reading fields only** (Req 1.4,
1.5, 1.8, 7.7): never a formatted or rendered representation of a result,
and never a fabricated figure standing in for one that was not measured.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Literal, assert_never

from fitdocs.load.channels.types import ChannelId, ChannelLoad, ChannelOutcome
from fitdocs.load.types import QualityFlag
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity

from . import cadence, divergence, drift, staleness
from .cadence import CadenceLockOutcome, CadenceLockReading
from .divergence import DivergenceOutcome, DivergenceReading
from .drift import DriftOutcome, DriftReading
from .staleness import StalenessOutcome, StalenessReading
from .types import FLAG_LABELS, FLAG_ORDER, FlagKey, FlagSettings

Verdict = Literal["detected", "not-detected", "not-assessed"]
"""Local alias for the contract's three-value verdict literal (matches
`fitdocs.load.types.QualityFlag.verdict` exactly)."""


# ---------------------------------------------------------------------------
# Outcome -> verdict, one total mapping function per check (Req 1.2, 3.8 --
# see module docstring for why each is a folded ``match``/``assert_never``
# rather than a dict lookup or name-based coincidence).
# ---------------------------------------------------------------------------


def _cadence_verdict(outcome: CadenceLockOutcome) -> Verdict:
    match outcome:
        case CadenceLockOutcome.LOCKED:
            return "detected"
        case CadenceLockOutcome.CLEAR:
            return "not-detected"
        case CadenceLockOutcome.NOT_ASSESSED:
            return "not-assessed"
        case _:  # pragma: no cover -- exhaustiveness guard, not a live path
            assert_never(outcome)


def _divergence_verdict(outcome: DivergenceOutcome) -> Verdict:
    match outcome:
        case DivergenceOutcome.DIVERGENT:
            return "detected"
        case DivergenceOutcome.AGREED:
            return "not-detected"
        case DivergenceOutcome.NOT_ASSESSED:
            return "not-assessed"
        case _:  # pragma: no cover -- exhaustiveness guard, not a live path
            assert_never(outcome)


def _drift_verdict(outcome: DriftOutcome) -> Verdict:
    match outcome:
        case DriftOutcome.DRIFTED:
            return "detected"
        case DriftOutcome.COUPLED:
            return "not-detected"
        case DriftOutcome.NOT_ASSESSED:
            return "not-assessed"
        case _:  # pragma: no cover -- exhaustiveness guard, not a live path
            assert_never(outcome)


def _staleness_verdict(outcome: StalenessOutcome) -> Verdict:
    match outcome:
        case StalenessOutcome.STALE:
            return "detected"
        case StalenessOutcome.CURRENT:
            return "not-detected"
        case StalenessOutcome.RETROACTIVE:
            # The check ran to completion and the anchor is not stale (Req
            # 3.8 of tasks.md's 3.1 bullet list, Req 5.8): a retroactive
            # anchor is a *reached* verdict, never not-assessed, and never
            # detected -- it is not the condition ("stale") this check looks
            # for.
            return "not-detected"
        case StalenessOutcome.NOT_ASSESSED:
            return "not-assessed"
        case _:  # pragma: no cover -- exhaustiveness guard, not a live path
            assert_never(outcome)


# ---------------------------------------------------------------------------
# Basis strings -- one builder per check, built only from that check's own
# typed reading fields (Req 1.4, 1.5, 1.8, 7.7).
# ---------------------------------------------------------------------------


def _cadence_detail(reading: CadenceLockReading) -> str:
    if reading.outcome is CadenceLockOutcome.NOT_ASSESSED:
        assert reading.not_assessed_reason is not None
        return reading.not_assessed_reason

    assert reading.locked_duration_s is not None
    parts = [
        f"heart rate and cadence were locked together for "
        f"{reading.locked_duration_s:.0f}s of the activity "
        f"(configured minimum {reading.required_duration_s}s), assessed "
        f"over {reading.spans_assessed} span(s)"
    ]
    if reading.paired_coverage is not None:
        parts.append(
            "time-weighted heart-rate/cadence paired coverage "
            f"{reading.paired_coverage.fraction:.1%} (measured over recorded "
            "time, not the document's own sample-count coverage table)"
        )
    return "; ".join(parts) + "."


def _divergence_detail(reading: DivergenceReading) -> str:
    if reading.outcome is DivergenceOutcome.NOT_ASSESSED:
        assert reading.not_assessed_reason is not None
        return reading.not_assessed_reason

    assert reading.selected_intensity is not None
    assert reading.heart_rate_intensity is not None
    assert reading.delta is not None
    return (
        f"selected channel ({reading.selected_channel.value}) intensity "
        f"{reading.selected_intensity:.3f} vs heart-rate intensity "
        f"{reading.heart_rate_intensity:.3f} (difference {reading.delta:.3f}, "
        f"configured tolerance {reading.tolerance:.3f})."
    )


def _drift_detail(reading: DriftReading) -> str:
    if reading.outcome is DriftOutcome.NOT_ASSESSED:
        assert reading.not_assessed_reason is not None
        return reading.not_assessed_reason

    assert reading.decoupling_pct is not None
    text = (
        f"aerobic decoupling {reading.decoupling_pct:.1f}% vs configured "
        f"reference {reading.reference_pct:.1f}%"
    )
    if reading.efficiency_factor is not None:
        text += f"; efficiency factor {reading.efficiency_factor:.3f}"
    return text + "."


def _staleness_detail(reading: StalenessReading) -> str:
    if reading.outcome is StalenessOutcome.NOT_ASSESSED:
        assert reading.not_assessed_reason is not None
        return reading.not_assessed_reason

    assert reading.age is not None
    measured_on = reading.anchor.measured_on.isoformat()

    if reading.outcome is StalenessOutcome.RETROACTIVE:
        days_after = -reading.age.age_days
        if reading.anchor.applies_from is not None:
            applies_from_clause = (
                "the athlete declared it applies from "
                f"{reading.anchor.applies_from.isoformat()}"
            )
        else:
            applies_from_clause = "the anchor carries no applies-from date"
        return (
            f"anchoring benchmark measured on {measured_on}, {days_after} "
            f"day(s) after the activity; {applies_from_clause}; configured "
            f"window {reading.age.window_days} days."
        )

    return (
        f"anchoring benchmark measured on {measured_on}, "
        f"{reading.age.age_days} day(s) old (configured window "
        f"{reading.age.window_days} days)."
    )


def evaluate_flags(
    *,
    activity: Activity,
    metrics: DerivedMetrics,
    outcomes: Mapping[ChannelId, ChannelOutcome],
    selected: ChannelId,
    activity_date: date | None,
    staleness_window_days: int,
    settings: FlagSettings,
) -> tuple[QualityFlag, ...]:
    """Run all four checks unconditionally and emit one `QualityFlag` per
    check, in `FLAG_ORDER` (Req 1.1, 1.6, 1.7, 1.9, 1.10, 3.8, 5.8, 7.6,
    7.7).

    **Precondition**: ``outcomes[selected]`` is a `ChannelLoad` -- the
    calculator only calls this after a successful channel selection, the
    same precondition `divergence.evaluate` and `staleness.evaluate`
    themselves document.

    **Order of the four checks called, matching `FLAG_ORDER`**: cadence
    lock, channel divergence, aerobic drift, benchmark staleness. Each is
    called with exactly the arguments this function receives -- no default
    threshold, no default window, no default activity date is substituted
    anywhere in this function.

    Pure: reads only its arguments, consults no clock, opens no file
    (Req 1.9). Equal inputs produce a string-for-string-equal tuple on
    repeat calls (Req 7.6) because every one of the four checks is itself
    pure and every basis string is built from that call's own typed reading.
    """
    cadence_reading = cadence.detect(
        activity.samples, modality=activity.modality, settings=settings
    )
    divergence_reading = divergence.evaluate(
        outcomes, selected=selected, settings=settings
    )
    drift_reading = drift.evaluate(metrics, settings=settings)
    # Precondition (documented above and on `staleness.evaluate` itself):
    # the calculator only reaches this code after a successful selection, so
    # `outcomes[selected]` is always a `ChannelLoad`.
    selected_load: ChannelLoad = outcomes[selected]  # type: ignore[assignment]
    staleness_reading = staleness.evaluate(
        selected_load,
        activity_date=activity_date,
        window_days=staleness_window_days,
    )

    by_key: dict[FlagKey, QualityFlag] = {
        FlagKey.CADENCE_LOCK: QualityFlag(
            key=FlagKey.CADENCE_LOCK.value,
            label=FLAG_LABELS[FlagKey.CADENCE_LOCK],
            verdict=_cadence_verdict(cadence_reading.outcome),
            detail=_cadence_detail(cadence_reading),
        ),
        FlagKey.CHANNEL_DIVERGENCE: QualityFlag(
            key=FlagKey.CHANNEL_DIVERGENCE.value,
            label=FLAG_LABELS[FlagKey.CHANNEL_DIVERGENCE],
            verdict=_divergence_verdict(divergence_reading.outcome),
            detail=_divergence_detail(divergence_reading),
        ),
        FlagKey.AEROBIC_DRIFT: QualityFlag(
            key=FlagKey.AEROBIC_DRIFT.value,
            label=FLAG_LABELS[FlagKey.AEROBIC_DRIFT],
            verdict=_drift_verdict(drift_reading.outcome),
            detail=_drift_detail(drift_reading),
        ),
        FlagKey.BENCHMARK_STALENESS: QualityFlag(
            key=FlagKey.BENCHMARK_STALENESS.value,
            label=FLAG_LABELS[FlagKey.BENCHMARK_STALENESS],
            verdict=_staleness_verdict(staleness_reading.outcome),
            detail=_staleness_detail(staleness_reading),
        ),
    }

    return tuple(by_key[key] for key in FLAG_ORDER)
