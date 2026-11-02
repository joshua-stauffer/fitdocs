"""Pick the one Strava activity that is a page's session (the strict rule).

The listing is read around the page's start; each listed activity becomes
strict-tier facts, with the sport compared by family, and the pinned strict
match decides. Exactly one match is a pick; the listing's order never decides.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from fitdocs_relay.shared.relay_targets import PublishFacts
from fitdocs_relay.shared.strict import StrictFacts, strict_match
from fitdocs_relay.strava.api import Candidate, Listing

__all__ = [
    "LIST_PAGE_SIZE",
    "LIST_WINDOW_S",
    "SPORT_FAMILIES",
    "Pick",
    "list_window",
    "pick",
]

LIST_WINDOW_S: Final = 120
LIST_PAGE_SIZE: Final = 30

_RUN: Final = frozenset({"Run"})
_RIDE: Final = frozenset({"Ride"})
_E_RIDE: Final = frozenset({"Ride", "Workout"})
_WORKOUT: Final = frozenset({"Workout"})

# fitdocs labels every FIT sport it does not name as Workout, so every other
# sport type in Strava's documented list belongs to that family.
_FAMILIES: Final[dict[str, frozenset[str]]] = {
    **dict.fromkeys(("Run", "TrailRun", "VirtualRun"), _RUN),
    **dict.fromkeys(
        (
            "Ride",
            "MountainBikeRide",
            "GravelRide",
            "VirtualRide",
            "Velomobile",
            "Handcycle",
        ),
        _RIDE,
    ),
    **dict.fromkeys(("EBikeRide", "EMountainBikeRide"), _E_RIDE),
    "Swim": frozenset({"Swim"}),
    "Walk": frozenset({"Walk"}),
    "Hike": frozenset({"Hike"}),
    **dict.fromkeys(("Rowing", "VirtualRow"), frozenset({"Rowing"})),
    **dict.fromkeys(
        (
            "AlpineSki",
            "BackcountrySki",
            "Badminton",
            "Canoeing",
            "Crossfit",
            "Elliptical",
            "Golf",
            "HighIntensityIntervalTraining",
            "IceSkate",
            "InlineSkate",
            "Kayaking",
            "Kitesurf",
            "NordicSki",
            "Pickleball",
            "Pilates",
            "Racquetball",
            "RockClimbing",
            "RollerSki",
            "Sail",
            "Skateboard",
            "Snowboard",
            "Snowshoe",
            "Soccer",
            "Squash",
            "StairStepper",
            "StandUpPaddling",
            "Surfing",
            "TableTennis",
            "Tennis",
            "WeightTraining",
            "Wheelchair",
            "Windsurf",
            "Workout",
            "Yoga",
        ),
        _WORKOUT,
    ),
}
SPORT_FAMILIES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(_FAMILIES)


class Pick(StrEnum):
    NONE = "none"
    MANY = "many"


def list_window(start: datetime) -> tuple[int, int]:
    """The listing's (after, before) in epoch seconds around ``start``."""
    seconds = start.timestamp()
    return (math.floor(seconds) - LIST_WINDOW_S, math.ceil(seconds) + LIST_WINDOW_S)


def _facts(facts: PublishFacts, candidate: Candidate) -> StrictFacts | None:
    family = SPORT_FAMILIES.get(candidate.sport_type or "")
    if family is None or facts.sport not in family:
        return None
    return StrictFacts(
        sport=facts.sport,
        start=candidate.start,
        elapsed_s=candidate.elapsed_s,
        distance_m=candidate.distance_m,
    )


def pick(facts: PublishFacts, listing: Listing) -> Candidate | Pick:
    """The one candidate that is the page's session, or why there is none."""
    if listing.full:
        return Pick.MANY
    page = StrictFacts(facts.sport, facts.start, facts.elapsed_s, facts.distance_m)
    matches: list[Candidate] = []
    for candidate in listing.candidates:
        theirs = _facts(facts, candidate)
        if theirs is not None and strict_match(page, theirs):
            matches.append(candidate)
    if not matches:
        return Pick.NONE
    return matches[0] if len(matches) == 1 else Pick.MANY
