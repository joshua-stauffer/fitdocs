"""Resolving a link at click time (task 3.8) on both backends.

Strava is the scripted outbound; the recorded calls are the count of Strava
requests. A resolution writes nothing about its result and, without a token
refresh, changes only the budget's counts; a refresh changes target_connections
and a refused refresh deletes the connection and its records.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

import pytest
from tests.conformance.state_support import Target, raw
from tests.strava.scripted_strava import reply
from tests.strava.test_publish import (
    ACCESS,
    ACTIVITY_ID,
    CONFIG,
    FAILING,
    FAR,
    HUGE,
    NEAR,
    NOW,
    OTHER_ID,
    PUB_ID,
    REFRESH,
    START_S,
    TOKEN_URL,
    WEB,
    World,
    build,
    connect,
    entry,
    listing_url,
    probe_after,
    script_list,
)

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.outbound import OutboundError
from fitdocs_relay.storage.interface import NewPrincipal, Publication, Storage
from fitdocs_relay.strava.api import Failure, Grant, StravaApi
from fitdocs_relay.strava.config import Limits, LinkSetting
from fitdocs_relay.strava.publish import (
    CALL_TIMEOUT_S,
    PUBLISH_DEADLINE_S,
    LinkRefusal,
    StravaPublisher,
    activity_page,
)
from fitdocs_relay.strava.resolve import LIST_PAGE_SIZE

WEB_OTHER = "https://link-web.example"
BEA_ACCESS = "access-tok-BEA"
NEW_ACCESS = "access-tok-NEW"
R = LinkRefusal


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    s = open_full_storage()
    for pid in ("ann", "bea", "cat"):
        s.create_principal(NewPrincipal(pid, None), now=1)
    return s


def record(
    w: World,
    publication_id: str = PUB_ID,
    principal: str = "ann",
    *,
    sport: str = "Run",
    elapsed: float | None = 1800.0,
    distance: float | None = 5000.0,
) -> None:
    # created at second 1: a rewrite at NOW would change the row
    assert w.store.put_publication(
        Publication(
            "strava",
            publication_id,
            principal,
            sport,
            float(START_S),
            elapsed,
            distance,
        ),
        now=1,
    )


@pytest.fixture
def world(store: Storage) -> World:
    w = build(store, web_url=WEB_OTHER)
    connect(w)
    record(w)
    return w


def tables(target: Target) -> dict[str, list[str]]:
    """Every table of the database, each as its sorted rows."""
    if isinstance(target, SqliteTarget):
        names = raw(
            target,
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'",
        )
    else:
        names = raw(
            target,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()",
        )
    return {
        name: sorted(repr(row) for row in raw(target, f"SELECT * FROM {name}"))
        for (name,) in names
    }


def calls(w: World) -> int:
    return len(w.outbound.calls)


# --- one match -----------------------------------------------------------------


def test_one_match_gives_the_activity_page_built_by_activity_page(
    world: World,
) -> None:
    script_list(world, entry())
    result = world.publisher.resolve_link(PUB_ID)
    assert result == activity_page(WEB_OTHER, str(ACTIVITY_ID))
    assert result == f"{WEB_OTHER}/activities/{ACTIVITY_ID}"
    assert world.urls() == [listing_url()]


def test_the_match_is_made_on_the_recorded_facts_among_decoys(world: World) -> None:
    other = ACTIVITY_ID + 1
    script_list(
        world,
        entry(other, distance=9000.0),  # same start, other distance
        entry(other + 1, sport_type="Ride"),  # same facts, other sport
        entry(other + 2, start="2026-03-01T11:00:00Z"),  # other start
        entry(),
    )
    assert world.publisher.resolve_link(PUB_ID) == activity_page(
        WEB_OTHER, str(ACTIVITY_ID)
    )


def test_the_recorded_sport_decides_the_match(store: Storage) -> None:
    w = build(store)
    connect(w)
    record(w, sport="Ride")
    script_list(w, entry(sport_type="Run"), entry(ACTIVITY_ID + 1, sport_type="Ride"))
    assert w.publisher.resolve_link(PUB_ID) == activity_page(WEB, str(ACTIVITY_ID + 1))


def test_the_listing_uses_the_owners_token_and_the_call_timeout(store: Storage) -> None:
    w = build(store)
    w.custody.store_grant("ann", Grant(ACCESS, REFRESH, FAR, "who-ann"))
    w.custody.store_grant("bea", Grant(BEA_ACCESS, REFRESH, FAR, "who-bea"))
    record(w, principal="bea")
    script_list(w, entry())
    assert isinstance(w.publisher.resolve_link(PUB_ID), str)
    (call,) = w.outbound.calls
    assert call.request.secret_headers["Authorization"] == f"Bearer {BEA_ACCESS}"
    assert call.timeout == CALL_TIMEOUT_S


def test_either_link_setting_resolves(world: World) -> None:
    config = replace(CONFIG, web_url=WEB_OTHER, links=LinkSetting.RELAY)
    publisher = StravaPublisher(
        world.store,
        world.custody,
        StravaApi(config, outbound=world.outbound),
        world.budget,
        config,
        clock=lambda: NOW,
        monotonic=world.mono,
    )
    script_list(world, entry())
    assert publisher.resolve_link(PUB_ID) == activity_page(WEB_OTHER, str(ACTIVITY_ID))


# --- not found ---------------------------------------------------------------------


def test_no_activity_matching_is_not_found(world: World) -> None:
    script_list(world, entry(distance=9000.0))
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert calls(world) == 1


def test_an_empty_listing_is_not_found(world: World) -> None:
    script_list(world)
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND


def test_several_matches_are_not_found(world: World) -> None:
    script_list(world, entry(), entry(ACTIVITY_ID + 1))
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert calls(world) == 1


def test_a_full_listing_is_not_found_even_with_one_match(world: World) -> None:
    script_list(
        world,
        entry(),
        *[entry(ACTIVITY_ID + n, sport_type="Ride") for n in range(1, LIST_PAGE_SIZE)],
    )
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND


@pytest.mark.parametrize("publication_id", [OTHER_ID, "", "../etc", "A" * 32, "a" * 33])
def test_an_unknown_or_malformed_id_is_not_found_with_no_call(
    world: World, publication_id: str
) -> None:
    assert world.publisher.resolve_link(publication_id) is R.NOT_FOUND
    assert calls(world) == 0
    assert probe_after(world, 0)


def test_a_principal_with_no_connection_is_not_found_with_no_call(
    store: Storage,
) -> None:
    w = build(store)
    connect(w, "bea")  # someone else is connected; the owner is not
    record(w, principal="ann")
    assert w.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert calls(w) == 0


def test_a_withdrawn_connection_is_not_found(world: World) -> None:
    world.store.delete_connection("ann", "strava", generation=1, now=NOW)
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert calls(world) == 0


def test_a_refused_refresh_is_not_found_and_the_connection_goes(store: Storage) -> None:
    w = build(store)
    connect(w, expires=NEAR)
    record(w)
    w.outbound.expect("POST", TOKEN_URL, reply(400))
    assert w.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert store.get_connection("ann", "strava") is None
    assert w.urls("GET") == []


# --- try later ---------------------------------------------------------------


def use_up_link_headroom(w: World) -> None:
    # read_15m=10: the headroom leaves 8 for links, each principal's own is 4
    for principal in ("bea",) * 4 + ("cat",) * 4:
        assert w.budget.spend(principal, for_link=True).allowed
    assert not w.budget.spend("ann", for_link=True).allowed
    assert w.budget.spend("ann").allowed  # a non-link call still fits


@pytest.fixture
def tight(store: Storage) -> World:
    # read_15m=10: a link call has 8 application-wide and 4 per principal, a
    # non-link call 10 and 5
    w = build(store, limits=Limits(HUGE, HUGE, 10, HUGE))
    connect(w)
    record(w)
    return w


def test_the_links_headroom_gives_try_later_with_no_call(tight: World) -> None:
    for principal in ("bea",) * 4 + ("cat",) * 4:
        assert tight.budget.spend(principal, for_link=True).allowed
    script_list(tight, entry())
    assert tight.publisher.resolve_link(PUB_ID) is R.TRY_LATER
    assert calls(tight) == 0
    assert tight.budget.spend("ann").allowed  # the refused link left a call free


def test_a_link_inside_the_headroom_is_charged_as_a_link(tight: World) -> None:
    for principal in ("bea",) * 4 + ("cat",) * 3:
        assert tight.budget.spend(principal, for_link=True).allowed
    script_list(tight, entry())
    # 7 of the 8 link calls are used: this one takes the last ...
    assert isinstance(tight.publisher.resolve_link(PUB_ID), str)
    # ... so a second is refused by the link ceiling (a non-link ceiling of 10
    # would still have room) and makes no call
    assert tight.publisher.resolve_link(PUB_ID) is R.TRY_LATER
    assert calls(tight) == 1


def test_a_refresh_for_a_link_is_held_to_the_headroom(store: Storage) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 10, HUGE))
    connect(w, expires=NEAR)
    record(w)
    for principal in ("bea",) * 4 + ("cat",) * 4:
        assert w.budget.spend(principal, for_link=True).allowed
    w.outbound.expect("POST", TOKEN_URL, reply(200, {}))
    assert w.publisher.resolve_link(PUB_ID) is R.TRY_LATER
    assert calls(w) == 0


def test_a_near_expiry_token_is_refreshed_then_used(world: World) -> None:
    connect(world, expires=NEAR)
    world.outbound.expect(
        "POST",
        TOKEN_URL,
        reply(
            200,
            {
                "access_token": NEW_ACCESS,
                "refresh_token": "refresh-NEW",
                "expires_at": FAR,
            },
        ),
    )
    script_list(world, entry())
    assert world.publisher.resolve_link(PUB_ID) == activity_page(
        WEB_OTHER, str(ACTIVITY_ID)
    )
    token_call, list_call = world.outbound.calls
    assert token_call.request.url == TOKEN_URL
    assert list_call.request.secret_headers["Authorization"] == f"Bearer {NEW_ACCESS}"


@pytest.mark.parametrize("failure", [Failure.SERVER, Failure.NETWORK])
def test_a_near_expiry_refresh_that_is_unavailable_is_not_found(
    world: World, failure: Failure
) -> None:
    connect(world, expires=NEAR)
    world.outbound.expect("POST", TOKEN_URL, FAILING[failure]())  # type: ignore[arg-type]
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert world.urls() == [TOKEN_URL]


@pytest.mark.parametrize("failure", list(FAILING))
def test_a_failed_listing_is_not_found_unless_strava_limited(
    world: World, failure: Failure
) -> None:
    assert probe_after(world, 0)
    answer = FAILING[failure]()
    world.outbound.expect("GET", listing_url(), answer)  # type: ignore[arg-type]
    expected = R.TRY_LATER if failure is Failure.LIMITED else R.NOT_FOUND
    assert world.publisher.resolve_link(PUB_ID) is expected
    assert calls(world) == 1
    # only Strava's own 429 marks the application's window spent
    assert probe_after(world, 0) is (failure is not Failure.LIMITED)


def test_a_dropped_connection_while_listing_is_not_found(world: World) -> None:
    world.outbound.expect("GET", listing_url(), OutboundError("network"))
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND


# --- the deadline ------------------------------------------------------------------


def test_a_passed_deadline_ends_before_any_spend_or_call(
    world: World, database_target: Target
) -> None:
    before = tables(database_target)
    world.mono.jumps[world.mono.reads + 2] = PUBLISH_DEADLINE_S + 1
    script_list(world, entry())
    assert world.publisher.resolve_link(PUB_ID) is R.NOT_FOUND
    assert calls(world) == 0
    assert tables(database_target) == before


# --- storing nothing ---------------------------------------------------------


def test_a_resolution_changes_no_table_but_the_budget_counts(
    world: World, database_target: Target
) -> None:
    before = tables(database_target)
    assert before["target_publications"] and before["target_connections"]
    assert before["budget_counts"] == []
    script_list(world, entry())
    assert isinstance(world.publisher.resolve_link(PUB_ID), str)
    after = tables(database_target)
    assert after["budget_counts"]  # the spend is the one write
    assert {n for n in after if after[n] != before[n]} == {"budget_counts"}
    assert str(ACTIVITY_ID) not in repr(after)


@pytest.mark.parametrize("case", ["none", "many", "limited", "failed"])
def test_a_refusal_changes_no_table_but_the_budget_counts(
    world: World, database_target: Target, case: str
) -> None:
    before = tables(database_target)
    if case == "none":
        script_list(world)
    elif case == "many":
        script_list(world, entry(), entry(ACTIVITY_ID + 1))
    elif case == "limited":
        world.outbound.expect("GET", listing_url(), reply(429))
    else:
        world.outbound.expect("GET", listing_url(), reply(503))
    assert isinstance(world.publisher.resolve_link(PUB_ID), LinkRefusal)
    after = tables(database_target)
    changed = {n for n in after if after[n] != before[n]}
    assert changed == {"budget_counts"}


def test_an_unknown_id_changes_nothing(world: World, database_target: Target) -> None:
    before = tables(database_target)
    assert world.publisher.resolve_link(OTHER_ID) is R.NOT_FOUND
    assert tables(database_target) == before


@pytest.mark.parametrize("case", ["match", "none", "failed", "unknown"])
def test_nothing_is_logged(
    world: World, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    caplog.set_level(logging.DEBUG)
    publication_id = PUB_ID
    if case == "match":
        script_list(world, entry())
    elif case == "none":
        script_list(world)
    elif case == "failed":
        world.outbound.expect("GET", listing_url(), reply(503))
    else:
        publication_id = OTHER_ID
    world.publisher.resolve_link(publication_id)
    assert caplog.records == []


def test_a_record_with_no_distance_is_matched_on_its_elapsed_time(
    store: Storage,
) -> None:
    w = build(store)
    connect(w)
    record(w, distance=None)
    script_list(w, entry(ACTIVITY_ID + 1, elapsed=3000.0), entry())
    assert w.publisher.resolve_link(PUB_ID) == activity_page(WEB, str(ACTIVITY_ID))
