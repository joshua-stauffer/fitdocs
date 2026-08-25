"""The per-discipline channel-priority value and its documented defaults
(design: ChannelPriorityValue, Req 7.3, 7.4).

This leaf module holds the **value** -- an immutable, comparable mapping
from :class:`~fitdocs.model.Sport` to an ordered tuple of
:class:`~fitdocs.load.channels.types.ChannelId`. *Reading* one of these from
the data root's settings file is ``load/settings.py``'s job, outside this
module, which is what lets the settings reader import this type without
pulling in the calculator (Req 7.3).

Defaults are applied at construction, not at lookup time: a bare
``ChannelPriority()`` already equals the value an unconfigured data root
would produce, so tests and production agree without a separate "resolve
the defaults" step.

**Why running does not default to power.** fitdocs reads a running power
stream that intervals.icu -- the interop target this feature is scored
against -- does not ingest. Defaulting running to power first would make
every run's headline load unreproducible on that target, so running's
documented default anchors on pace instead, with power and heart rate as
fallbacks (Req 7.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from fitdocs.load.channels.types import ChannelId
from fitdocs.model import Sport

# Revalidation trigger (design.md Implementation Notes): changing a default
# below changes every previously computed document's selected channel, since
# the threshold calculator re-derives its choice from this table each run.
DEFAULT_CHANNEL_PRIORITY: Final[MappingProxyType[Sport, tuple[ChannelId, ...]]] = (
    MappingProxyType(
        {
            Sport.RUN: (ChannelId.PACE, ChannelId.POWER, ChannelId.HEART_RATE),
            Sport.RIDE: (ChannelId.POWER, ChannelId.HEART_RATE),
            Sport.WALK: (ChannelId.HEART_RATE,),
            Sport.HIKE: (ChannelId.HEART_RATE,),
        }
    )
)


@dataclass(frozen=True)
class ChannelPriority:
    """The per-discipline channel ordering, defaulted and immutable.

    ``by_discipline`` maps a supported :class:`~fitdocs.model.Sport` to the
    ordered tuple of channels the threshold calculator should try, highest
    priority first. Defaults to :data:`DEFAULT_CHANNEL_PRIORITY` so that a
    default-constructed value equals the documented defaults (Req 7.3).
    """

    by_discipline: Mapping[Sport, tuple[ChannelId, ...]] = field(
        default_factory=lambda: DEFAULT_CHANNEL_PRIORITY
    )

    def for_discipline(self, sport: Sport) -> tuple[ChannelId, ...]:
        """The configured order for ``sport``, or the empty tuple for a
        discipline this calculator does not support."""
        return self.by_discipline.get(sport, ())
