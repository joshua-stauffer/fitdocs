"""Picking one channel by order alone, and recording what the others were
(design: ``ChannelSelection``, Req 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4,
6.5, 6.6, 8.3, 8.4, 8.5, 8.9).

Two pure functions over a mapping of :data:`~fitdocs.load.channels.types.
ChannelOutcome` and a configured order. No activity, no profile, no
benchmark, no configuration reading -- every selection rule is provable from
a handful of constructed outcomes.

**Reads no value.** :func:`select` inspects only membership in ``order`` and
whether an outcome is a
:class:`~fitdocs.load.channels.types.ChannelLoad`. It never reads ``load``,
``intensity``, ``coverage`` or an anchor date (Req 6.5) -- the structural
guarantee behind Req 11.7: there is no place in this feature where two
channel values are in scope together for arithmetic.

:func:`non_selected_values` records every channel other than the selected
one exactly once, in the **canonical** order :data:`CANONICAL_CHANNELS`,
which is independent of the configured priority order, so two data roots
configured differently still produce diffable documents (Req 8.9).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, assert_never

from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
)
from fitdocs.load.types import NonSelectedValue
from fitdocs.model import Sport

CANONICAL_CHANNELS: Final[tuple[ChannelId, ...]] = (
    ChannelId.POWER,
    ChannelId.HEART_RATE,
    ChannelId.PACE,
)
"""The fixed record order for non-selected values (Req 8.9). Independent of
any configured priority order, so two differently-configured data roots
still produce diffable documents."""

CHANNEL_LABELS: Final[Mapping[ChannelId, str]] = {
    ChannelId.POWER: "Power",
    ChannelId.HEART_RATE: "Heart rate",
    ChannelId.PACE: "Pace",
}
"""Display labels for :data:`NonSelectedValue.label` and for the priority
reason string, keyed by :class:`ChannelId`."""


def select(
    outcomes: Mapping[ChannelId, ChannelOutcome], order: Sequence[ChannelId]
) -> ChannelId | None:
    """The first channel in ``order`` whose outcome is a computed load, or
    ``None`` when none is (Req 6.1, 6.2, 6.3, 6.7).

    Walks ``order`` -- not :data:`CANONICAL_CHANNELS`, not ``outcomes``'
    own iteration order -- and selects the first id whose outcome is a
    :class:`ChannelLoad`. A channel absent from ``order`` is never
    considered, even when it produced a computed load (Req 6.4). The walk
    inspects only ``isinstance(outcome, ChannelLoad)``; no field of either
    outcome variant is ever read (Req 6.5).

    Precondition: ``outcomes`` holds exactly one entry per
    :data:`CANONICAL_CHANNELS` member (Req 5.1).
    """
    for channel_id in order:
        outcome = outcomes[channel_id]
        if isinstance(outcome, ChannelLoad):
            return channel_id
    return None


def non_selected_values(
    outcomes: Mapping[ChannelId, ChannelOutcome],
    *,
    order: Sequence[ChannelId],
    selected: ChannelId | None,
    discipline: Sport,
) -> tuple[NonSelectedValue, ...]:
    """One :class:`NonSelectedValue` per channel other than ``selected``, in
    :data:`CANONICAL_CHANNELS` order regardless of ``order`` (Req 8.3, 8.9).

    - A computed channel that is in ``order`` (and lost to a higher-priority
      channel) carries its load and the reason naming the winning channel
      (Req 8.4).
    - A computed channel that is absent from ``order`` carries its load and
      the reason naming its absence from the configured order (Req 6.4,
      8.4).
    - An insufficient channel carries ``value=None`` and the channel
      layer's own ``detail`` verbatim, so the recorded reason is the one
      the channel actually reported (Req 5.6, 8.5); no entry ever carries
      ``0.0`` in place of an absent value (Req 8.5).

    The closed :data:`ChannelOutcome` union is folded exhaustively with
    ``assert_never`` so a future third variant is a static error rather
    than a silent gap (Req 5.7).
    """
    records: list[NonSelectedValue] = []
    for channel_id in CANONICAL_CHANNELS:
        if channel_id == selected:
            continue
        outcome = outcomes[channel_id]
        match outcome:
            case ChannelLoad(load=load):
                if channel_id in order:
                    # A computed channel that is in the configured order but
                    # was not selected implies some channel *was* selected --
                    # select() only returns None when no channel in order
                    # computed a load, which this channel's presence rules
                    # out. Structural, not a runtime guess (Req 6.2, 6.3).
                    assert selected is not None
                    reason = (
                        f"not selected: the configured order for {discipline} "
                        f"prefers {CHANNEL_LABELS[selected]}"
                    )
                else:
                    reason = (
                        "not selected: this channel is not in the configured "
                        f"order for {discipline}"
                    )
                value: float | None = load
            case ChannelInsufficient(detail=detail):
                value = None
                reason = detail
            case _:  # pragma: no cover - exhaustive over the closed outcome union
                assert_never(outcome)
        records.append(
            NonSelectedValue(
                key=channel_id.value,
                label=CHANNEL_LABELS[channel_id],
                value=value,
                reason=reason,
            )
        )
    return tuple(records)
