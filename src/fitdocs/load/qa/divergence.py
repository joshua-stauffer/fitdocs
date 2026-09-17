"""Cross-channel intensity divergence: does the channel that scored the
activity agree with heart rate about how hard it was (design:
DivergenceAnalysis, `src/fitdocs/load/qa/divergence.py`).

**Intensities only, never loads.** `load-channels` defines one shared,
dimensionless intensity semantic for all three channels -- exactly 1.0 at
threshold, and related to load by ``load == hours * intensity**2 * 100`` on
every channel alike (`ChannelLoad.intensity`'s own docstring). This module
reads only `.intensity` from the two channel outcomes it compares; it never
reads `.load`, `.coverage` or `.anchor` on either, which is the structural
guarantee that there is no point in this module where two load values are
ever in scope together (Req 3.4, 3.7).

**The premise this check restates, and the defect it replaces.** Before
`load-channels` Requirement 1.11 landed, heart-rate intensity was the
*square* of what power and pace reported for the same load, so the two
scales coincided only at exactly 1.0 (threshold) -- every sub-threshold
comparison was silently wrong in a direction that read *divergent on easy
aerobic sessions where the channels actually agreed*. That is fixed
upstream now: heart rate reports the square root of its impulse ratio, so
the shared relation holds identically on all three channels at every
effort, not only at threshold. This module's own regression test (Req 3.9)
pins the corrected premise with a sub-threshold fixture specifically
because a threshold-only fixture cannot distinguish the corrected
definition from the defective one -- see `tests/load/qa/test_divergence.py`.

**Never raises** (Req 1.10): every path returns a reading, including a
mapping that omits the heart-rate channel's outcome entirely -- Design's
Implementation Notes name this a revalidation trigger (`threshold-load`
evaluates all three channels unconditionally today; if that integration
ever became lazy, an omitted entry must still degrade to *not-assessed*
rather than raise, exactly as Req 1.10 requires for absent channel data).
The one exception is the documented precondition below, which is a
programming error, not a data condition -- matching
`channels.types.require_kind`'s precedent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
)

from .types import FlagSettings


class DivergenceOutcome(StrEnum):
    """The three-value verdict this check can reach (Req 1.2, 3.2, 3.5,
    3.6). Closed -- exactly these three."""

    DIVERGENT = "divergent"
    AGREED = "agreed"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class DivergenceReading:
    """This check's own typed result, before `FlagAssembly` maps it onto the
    contract's three-value verdict vocabulary (Req 3.3).

    ``selected_intensity``, ``heart_rate_intensity`` and ``delta`` are
    populated together for :data:`DivergenceOutcome.DIVERGENT` and
    :data:`DivergenceOutcome.AGREED`, and left ``None`` together for
    :data:`DivergenceOutcome.NOT_ASSESSED` -- there is no figure to report
    when the check could not run to completion (Req 1.5, 1.8). ``tolerance``
    is always the configured value, regardless of outcome. ``not_assessed_reason``
    is populated only for :data:`DivergenceOutcome.NOT_ASSESSED`.
    """

    outcome: DivergenceOutcome
    selected_channel: ChannelId
    selected_intensity: float | None
    heart_rate_intensity: float | None
    delta: float | None
    tolerance: float
    not_assessed_reason: str | None


def evaluate(
    outcomes: Mapping[ChannelId, ChannelOutcome],
    *,
    selected: ChannelId,
    settings: FlagSettings,
) -> DivergenceReading:
    """Compare ``selected``'s intensity against the heart-rate channel's
    (Req 3.1-3.9).

    **Precondition**: ``outcomes[selected]`` is a `ChannelLoad` -- the
    calculator only reaches this code after a successful channel selection.
    A caller that violates this (passing a `ChannelInsufficient` as the
    selected channel) gets an `AttributeError` from treating it as a
    `ChannelLoad`, matching `channels.types.require_kind`'s precedent: a
    programming error fails loudly rather than being computed from.

    **Gate order, exactly, short-circuiting** (Req 3.5, 3.6, 3.2, 1.10):

    1. ``selected is ChannelId.HEART_RATE`` -> *not-assessed*: there is no
       second channel to compare heart rate against.
    2. The heart-rate channel's outcome is absent from ``outcomes`` entirely
       -> *not-assessed*, stating that the heart-rate channel was not
       evaluated for this activity. Today `threshold-load` always evaluates
       all three channels, so this path is not reachable from the shipped
       calculator; it exists so an absent channel degrades gracefully
       instead of raising, per Req 1.10 and the revalidation trigger
       recorded on this module's docstring.
    3. The heart-rate channel is itself a `ChannelInsufficient` ->
       *not-assessed*, carrying that channel's own ``detail`` verbatim.
    4. Otherwise, compare intensities against ``settings
       .divergence_max_intensity_delta``: strictly greater than tolerance is
       *divergent*, everything else -- including exactly equal to tolerance
       -- is *agreed*.
    """
    tolerance = settings.divergence_max_intensity_delta

    if selected is ChannelId.HEART_RATE:
        return DivergenceReading(
            outcome=DivergenceOutcome.NOT_ASSESSED,
            selected_channel=selected,
            selected_intensity=None,
            heart_rate_intensity=None,
            delta=None,
            tolerance=tolerance,
            not_assessed_reason=(
                "the heart-rate channel is the selected channel; there is no "
                "second channel to compare it against"
            ),
        )

    hr_outcome = outcomes.get(ChannelId.HEART_RATE)
    if hr_outcome is None:
        return DivergenceReading(
            outcome=DivergenceOutcome.NOT_ASSESSED,
            selected_channel=selected,
            selected_intensity=None,
            heart_rate_intensity=None,
            delta=None,
            tolerance=tolerance,
            not_assessed_reason=(
                "the heart-rate channel was not evaluated for this activity"
            ),
        )

    heart_rate_intensity: float
    match hr_outcome:
        case ChannelInsufficient():
            return DivergenceReading(
                outcome=DivergenceOutcome.NOT_ASSESSED,
                selected_channel=selected,
                selected_intensity=None,
                heart_rate_intensity=None,
                delta=None,
                tolerance=tolerance,
                not_assessed_reason=hr_outcome.detail,
            )
        case ChannelLoad():
            heart_rate_intensity = hr_outcome.intensity
        case _:
            assert_never(hr_outcome)

    # Precondition: the calculator only calls this after a successful
    # selection, so `outcomes[selected]` is always a `ChannelLoad`. A
    # `ChannelInsufficient` here is a programming error and raises naturally
    # (AttributeError on `.intensity`) rather than being guarded against
    # explicitly, matching `channels.types.require_kind`'s precedent.
    selected_intensity: float = outcomes[selected].intensity  # type: ignore[union-attr]
    delta = abs(selected_intensity - heart_rate_intensity)

    outcome = (
        DivergenceOutcome.DIVERGENT if delta > tolerance else DivergenceOutcome.AGREED
    )
    return DivergenceReading(
        outcome=outcome,
        selected_channel=selected,
        selected_intensity=selected_intensity,
        heart_rate_intensity=heart_rate_intensity,
        delta=delta,
        tolerance=tolerance,
        not_assessed_reason=None,
    )
