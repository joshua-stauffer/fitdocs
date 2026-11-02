"""The Strava resolver (task 3.4): sport families, the listing window and the
strict one-to-one pick."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from fitdocs_relay.shared.relay_targets import FITDOCS_SPORTS, PublishFacts
from fitdocs_relay.strava.api import Candidate, Listing
from fitdocs_relay.strava.resolve import (
    LIST_PAGE_SIZE,
    LIST_WINDOW_S,
    SPORT_FAMILIES,
    Pick,
    list_window,
    pick,
)

PLUS_2 = timezone(timedelta(hours=2))
# 10:00:00 at +02:00 is 08:00:00 UTC; a wall-clock compare would see two hours.
PAGE_START = datetime(2026, 3, 1, 10, 0, 0, tzinfo=PLUS_2)
UTC_START = datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)

EXPECTED_FAMILIES: dict[str, frozenset[str]] = {
    **dict.fromkeys(("Run", "TrailRun", "VirtualRun"), frozenset({"Run"})),
    **dict.fromkeys(
        (
            "Ride",
            "MountainBikeRide",
            "GravelRide",
            "VirtualRide",
            "Velomobile",
            "Handcycle",
        ),
        frozenset({"Ride"}),
    ),
    **dict.fromkeys(("EBikeRide", "EMountainBikeRide"), frozenset({"Ride", "Workout"})),
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
        frozenset({"Workout"}),
    ),
}


def facts(
    sport: str = "Run",
    *,
    start: datetime = PAGE_START,
    elapsed_s: float | None = 1800.0,
    distance_m: float | None = 5000.0,
) -> PublishFacts:
    return PublishFacts("pub-1", sport, start, elapsed_s, distance_m, "t", "d")


def cand(
    activity_id: str,
    sport_type: str | None = "Run",
    *,
    start: datetime = UTC_START,
    elapsed_s: float | None = 1800.0,
    distance_m: float | None = 5000.0,
) -> Candidate:
    return Candidate(activity_id, sport_type, start, elapsed_s, distance_m)


def listing(*candidates: Candidate, full: bool = False) -> Listing:
    return Listing(tuple(candidates), full)


# --- the table ---------------------------------------------------------------


def test_the_sport_family_table_is_exactly_the_designed_one() -> None:
    assert dict(SPORT_FAMILIES) == EXPECTED_FAMILIES


def test_every_family_value_is_a_fitdocs_sport_of_the_pinned_literal() -> None:
    assert SPORT_FAMILIES
    pinned = {
        "Ride",
        "Run",
        "Swim",
        "Walk",
        "Hike",
        "Rowing",
        "Workout",
    }
    assert pinned == FITDOCS_SPORTS
    for sport_type, family in SPORT_FAMILIES.items():
        assert family, sport_type
        assert family <= FITDOCS_SPORTS, sport_type


def test_the_table_cannot_be_edited_by_a_caller() -> None:
    with pytest.raises(TypeError):
        SPORT_FAMILIES["Run"] = frozenset({"Ride"})  # type: ignore[index]


# --- the window --------------------------------------------------------------


def test_the_window_constants() -> None:
    assert (LIST_WINDOW_S, LIST_PAGE_SIZE) == (120, 30)


def test_window_of_a_whole_second_start_is_the_instant_plus_and_minus_120() -> None:
    epoch = int(UTC_START.timestamp())
    assert epoch == 1772352000
    assert list_window(PAGE_START) == (epoch - 120, epoch + 120)


def test_window_floors_the_lower_edge_and_ceils_the_upper_one() -> None:
    epoch = 1772352000
    start = PAGE_START.replace(microsecond=400_000)
    assert list_window(start) == (epoch - 120, epoch + 1 + 120)
    late = PAGE_START.replace(microsecond=999_000)
    assert list_window(late) == (epoch - 120, epoch + 1 + 120)


# --- the pick ----------------------------------------------------------------


def test_no_candidate_is_none() -> None:
    assert pick(facts(), listing()) is Pick.NONE


def test_one_match_is_returned_among_decoys_wherever_it_stands() -> None:
    wanted = cand("wanted")
    decoys = (
        cand("late", start=UTC_START + timedelta(seconds=5)),
        cand("far", distance_m=9000.0),
        cand("ride", "Ride"),
    )
    assert pick(facts(), listing(wanted, *decoys)) is wanted
    assert pick(facts(), listing(*decoys, wanted)) is wanted
    assert pick(facts(), listing(decoys[0], wanted, *decoys[1:])) is wanted


def test_decoys_alone_are_none() -> None:
    decoys = (
        cand("late", start=UTC_START + timedelta(seconds=5)),
        cand("far", distance_m=9000.0),
        cand("ride", "Ride"),
    )
    assert pick(facts(), listing(*decoys)) is Pick.NONE


def test_two_matches_are_many_whatever_the_order() -> None:
    first = cand("a")
    second = cand("b", "TrailRun", distance_m=5010.0)
    assert pick(facts(), listing(first, second)) is Pick.MANY
    assert pick(facts(), listing(second, first)) is Pick.MANY


def test_two_matches_among_a_decoy_are_many() -> None:
    decoy = cand("far", distance_m=9000.0)
    assert pick(facts(), listing(cand("a"), decoy, cand("b"))) is Pick.MANY


def test_a_full_listing_is_many_even_when_one_candidate_matches() -> None:
    assert pick(facts(), listing(cand("a"), full=True)) is Pick.MANY
    assert pick(facts(), listing(full=True)) is Pick.MANY


def test_an_unknown_sport_type_never_matches() -> None:
    for sport in sorted(FITDOCS_SPORTS):
        unknown = listing(cand("x", "Teleporting"))
        assert pick(facts(sport), unknown) is Pick.NONE, sport


def test_a_candidate_without_a_sport_type_never_matches() -> None:
    for sport in sorted(FITDOCS_SPORTS):
        assert pick(facts(sport), listing(cand("x", None))) is Pick.NONE, sport


def test_an_unknown_sport_type_does_not_match_a_page_with_an_empty_sport() -> None:
    assert pick(facts(""), listing(cand("x", "Teleporting"))) is Pick.NONE
    assert pick(facts(""), listing(cand("x", None))) is Pick.NONE


def test_an_unknown_sport_type_does_not_make_a_match_ambiguous() -> None:
    wanted = cand("wanted")
    assert pick(facts(), listing(cand("x", "Teleporting"), wanted)) is wanted
    yoga = cand("yoga", "Yoga")
    for other in (cand("x", "Teleporting"), cand("y", None)):
        assert pick(facts("Workout"), listing(other, yoga)) is yoga


def test_a_sport_in_another_family_never_matches() -> None:
    assert pick(facts("Ride"), listing(cand("r", "Run"))) is Pick.NONE
    assert pick(facts("Run"), listing(cand("r", "Ride"))) is Pick.NONE


def test_a_family_member_matches_the_page_sport() -> None:
    for sport_type, family in EXPECTED_FAMILIES.items():
        for sport in sorted(family):
            found = cand("m", sport_type)
            assert pick(facts(sport), listing(found)) is found, (sport_type, sport)


def test_an_electric_ride_matches_a_ride_and_a_workout_but_not_a_run() -> None:
    electric = cand("e", "EBikeRide")
    assert pick(facts("Ride"), listing(electric)) is electric
    assert pick(facts("Workout"), listing(electric)) is electric
    assert pick(facts("Run"), listing(electric)) is Pick.NONE


def test_a_plain_ride_does_not_match_a_workout_page() -> None:
    assert pick(facts("Workout"), listing(cand("r", "Ride"))) is Pick.NONE


def test_start_is_compared_as_an_instant_not_a_wall_clock() -> None:
    wanted = cand("wanted")
    wall_clock_twin = cand("wall", start=UTC_START.replace(hour=10))
    assert pick(facts(), listing(wall_clock_twin, wanted)) is wanted
    assert pick(facts(), listing(wall_clock_twin)) is Pick.NONE


def test_a_start_one_second_off_matches_and_two_seconds_off_does_not() -> None:
    near = cand("near", start=UTC_START + timedelta(seconds=1))
    assert pick(facts(), listing(near)) is near
    assert pick(
        facts(), listing(cand("x", start=UTC_START + timedelta(seconds=2)))
    ) is (Pick.NONE)


def test_distance_is_compared_when_both_are_present_and_elapsed_is_not() -> None:
    near_distance_far_elapsed = cand("n", distance_m=5100.0, elapsed_s=99999.0)
    assert (
        pick(facts(), listing(near_distance_far_elapsed)) is near_distance_far_elapsed
    )
    far_distance_same_elapsed = cand("f", distance_m=7000.0)
    assert pick(facts(), listing(far_distance_same_elapsed)) is Pick.NONE


def test_a_missing_distance_falls_back_to_elapsed() -> None:
    page = facts(distance_m=None)
    close = cand("close", elapsed_s=1805.0)
    assert pick(page, listing(close)) is close
    assert pick(page, listing(cand("far", elapsed_s=1900.0))) is Pick.NONE
    listed_without = cand("without", distance_m=None, elapsed_s=1805.0)
    assert pick(facts(), listing(listed_without)) is listed_without
    assert pick(facts(), listing(cand("w2", distance_m=None, elapsed_s=1900.0))) is (
        Pick.NONE
    )


def test_absent_measures_on_both_sides_are_never_a_match() -> None:
    assert pick(facts(distance_m=None, elapsed_s=None), listing(cand("a"))) is Pick.NONE
    bare = cand("bare", distance_m=None, elapsed_s=None)
    assert pick(facts(), listing(bare)) is Pick.NONE
    assert pick(facts(distance_m=None), listing(bare)) is Pick.NONE
    assert pick(facts(distance_m=None), listing(cand("d", elapsed_s=None))) is Pick.NONE


def test_an_absent_elapsed_is_not_a_zero_that_a_short_session_could_match() -> None:
    short = 5.0
    listed_without = cand("w", distance_m=None, elapsed_s=None)
    assert pick(facts(distance_m=None, elapsed_s=short), listing(listed_without)) is (
        Pick.NONE
    )
    page_without = facts(distance_m=None, elapsed_s=None)
    assert pick(page_without, listing(cand("s", distance_m=None, elapsed_s=short))) is (
        Pick.NONE
    )
