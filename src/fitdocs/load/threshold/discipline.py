"""Which activities the threshold calculator scores, and which discipline's
benchmark anchors each of its channels (design: ``DisciplineSupport``, Req
2.1, 2.4, 2.6, 3.1, 3.2, 3.5).

Pure data plus two lookups. No ``ProfileView``, no ``Activity``, no I/O -- the
entire support-and-anchoring policy is reviewable and testable as a table.

**The sport set is authoritative; the modality set is a coarse pre-filter.**
``Modality.OTHER`` holds Walk and Hike *and* Rowing, Workout and every
unrecognized sport, so declaring it is the only way Walk and Hike reach
``compute`` at all -- the calculator must then refuse the others (Rowing,
Workout, ...) by sport (Req 2.5). ``SUPPORTED_SPORTS`` is what the
calculator's ``supports(activity)`` answer reads, so that refusal happens
before the athlete is ever prompted for input (Req 2.7).

``Modality.STRENGTH`` is deliberately **not** declared, so a strength
activity never reaches ``compute`` and takes the engine's unsupported path
directly -- the cheapest honest refusal (Req 2.2).

An anchor chain is ordered: the activity's own discipline first, then any
fallback. An **empty** chain means "this quantity does not anchor this
sport" (Req 3.5).

*Rationale for the Walk/Hike heart-rate chains*: the benchmark store never
falls back across disciplines, so without an explicit chain, scoring Walk and
Hike via the heart-rate channel is unrealizable for any athlete who has not
tested a walking or hiking LTHR. The chain prefers the athlete's own walk or
hike threshold when one is on file and borrows the running one otherwise.

*Rationale for the empty power and pace chains*: anchoring walking watts to a
running FTP -- or walking pace to a running threshold pace -- would produce
exactly the computable-but-meaningless number strength training was refused
for. An absent anchor yields the channel's own no-benchmark reason instead,
which is honest.

The athlete-wide quantities -- maximum and resting heart rate -- carry no
discipline and so appear in no chain here at all (Req 3.6); they are anchored
directly on the athlete-wide benchmark, not through this table.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from fitdocs.model import Modality, Sport

SUPPORTED_SPORTS: Final[frozenset[Sport]] = frozenset(
    {Sport.RUN, Sport.RIDE, Sport.WALK, Sport.HIKE}
)
"""The activities the threshold calculator scores at all (Req 2.1). Strength
training is deliberately absent; a strength activity is refused by the
undeclared ``Modality.STRENGTH`` below, not by this set -- ``Sport`` has no
strength member, and ``detect_sport("running", "strength_training")`` yields
``(Sport.RUN, Modality.STRENGTH)``, which this set alone would admit."""

DECLARED_MODALITIES: Final[frozenset[Modality]] = frozenset(
    {Modality.RUN, Modality.BIKE, Modality.OTHER}
)
"""The coarse pre-filter the load pass consults to route an unsupported
activity to the honest unsupported state without invoking the calculator
(Req 2.4). Coarser than ``SUPPORTED_SPORTS``: ``Modality.OTHER`` also holds
Rowing, Workout and every other unrecognized sport, which the calculator
still refuses by sport (Req 2.5). ``Modality.STRENGTH`` is absent (Req 2.2)
and ``Modality.SWIM`` is absent -- Swim is not a supported sport either."""


@dataclass(frozen=True)
class AnchorPlan:
    """Ordered discipline chains per quantity. ``()`` == no anchor for this
    sport."""

    ftp: tuple[Sport, ...]
    lthr: tuple[Sport, ...]
    threshold_pace: tuple[Sport, ...]


ANCHOR_PLANS: Final[Mapping[Sport, AnchorPlan]] = MappingProxyType(
    {
        Sport.RUN: AnchorPlan(
            ftp=(Sport.RUN,), lthr=(Sport.RUN,), threshold_pace=(Sport.RUN,)
        ),
        Sport.RIDE: AnchorPlan(
            ftp=(Sport.RIDE,), lthr=(Sport.RIDE,), threshold_pace=()
        ),
        Sport.WALK: AnchorPlan(ftp=(), lthr=(Sport.WALK, Sport.RUN), threshold_pace=()),
        Sport.HIKE: AnchorPlan(ftp=(), lthr=(Sport.HIKE, Sport.RUN), threshold_pace=()),
    }
)
"""The anchor plan for every supported sport (Req 3.1, 3.2, 3.5). Key set is
identical to :data:`SUPPORTED_SPORTS` -- a sport can never be supported
without an anchoring policy."""

assert frozenset(ANCHOR_PLANS.keys()) == SUPPORTED_SPORTS, (
    "SUPPORTED_SPORTS and ANCHOR_PLANS must declare exactly the same sports"
)


def is_supported(sport: Sport) -> bool:
    """Whether the threshold calculator scores this sport at all (Req
    2.1, 2.6). Determined from the sport label alone -- no data stream is
    consulted."""
    return sport in SUPPORTED_SPORTS


def anchor_plan(sport: Sport) -> AnchorPlan:
    """The anchor plan for a supported sport.

    Precondition: ``sport`` is supported (``is_supported(sport)``). The
    calculator refuses an unsupported sport before this is ever called, so
    an unsupported sport reaching here is a programming error, not a
    reportable outcome -- this deliberately raises ``KeyError`` rather than
    returning a default or ``None``.
    """
    return ANCHOR_PLANS[sport]
