"""One composed activity and its channel provenance from a base and extras.

Pure: no I/O, no clock. Extras donate only the units the base does not record
(channel-merge Req 1.1-1.5, 2.1-2.7, 3.10, 5.2, 5.4, 7.1; design.md § Composer).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from fitdocs.compose.alignment import align_extra
from fitdocs.compose.donation import (
    DONATION_UNITS,
    base_keeps,
    placed_values,
    records,
)
from fitdocs.compose.types import (
    ChannelProvenance,
    Composition,
    ExtraAlignment,
    SourceContribution,
)
from fitdocs.identity.kinds import source_kind
from fitdocs.model import Activity, Samples

_CHANNEL_ORDER: tuple[str, ...] = tuple(
    f.name for f in dataclasses.fields(Samples) if f.name != "time_s"
)


def _in_field_order(names: set[str]) -> tuple[str, ...]:
    return tuple(name for name in _CHANNEL_ORDER if name in names)


def _contribution(
    activity: Activity,
    channels: tuple[str, ...],
    alignment: ExtraAlignment | None,
) -> SourceContribution:
    return SourceContribution(
        sha256=activity.provenance.sha256,
        kind=source_kind(activity),
        manufacturer=activity.file_identity.manufacturer,
        devices=activity.devices,
        channels=channels,
        alignment=alignment,
    )


def _recorded_channels(activity: Activity) -> tuple[str, ...]:
    return _in_field_order(
        {name for name in _CHANNEL_ORDER if records(getattr(activity.samples, name))}
    )


def compose_activity(base: Activity, extras: Sequence[Activity]) -> Composition:
    """Compose ``base`` with ``extras`` (rank order, best first).

    With no extra the composition's activity is ``base`` itself. Otherwise each
    extra, in order, donates every still-open unit whose placed values record
    every channel of the unit; everything but the donated channels is the
    base's.
    """
    base_contribution = _contribution(base, _recorded_channels(base), None)
    if not extras:
        return Composition(
            activity=base,
            provenance=ChannelProvenance(base=base_contribution, extras=()),
        )

    open_units = [u for u in DONATION_UNITS if not base_keeps(u, base.samples)]
    donated: dict[str, tuple[object | None, ...]] = {}
    contributions: list[SourceContribution] = []
    for extra in extras:
        taken: set[str] = set()
        alignment: ExtraAlignment | None = None
        wanted = [
            u
            for u in open_units
            if any(records(getattr(extra.samples, name)) for name in u)
        ]
        if wanted:
            placement = align_extra(base, extra)
            for unit in wanted:
                values = {
                    name: placed_values(getattr(extra.samples, name), placement)
                    for name in unit
                }
                if all(records(v) for v in values.values()):
                    donated.update(values)
                    taken.update(unit)
                    open_units.remove(unit)
            if taken:
                alignment = placement.alignment
        contributions.append(_contribution(extra, _in_field_order(taken), alignment))

    activity = dataclasses.replace(
        base,
        samples=dataclasses.replace(base.samples, **donated),  # type: ignore[arg-type]
    )
    return Composition(
        activity=activity,
        provenance=ChannelProvenance(
            base=base_contribution, extras=tuple(contributions)
        ),
    )
