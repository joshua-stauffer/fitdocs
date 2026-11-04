"""The Strava publish flow (task 3.6) on both backends.

Strava is the scripted outbound: a request nobody scripted raises
`UnscriptedCall`, and the recorded calls are the count of Strava requests. The
monotonic clock is a fake that only the test and the scripted answers move.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import pytest
from tests.conformance.state_support import Target, raw
from tests.strava.scripted_strava import ScriptedOutbound, reply

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.crypto import EncryptionKey, Keyring
from fitdocs_relay.outbound import OutboundError, OutboundRequest
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_targets import PublishFacts
from fitdocs_relay.storage.interface import NewPrincipal, Storage
from fitdocs_relay.strava.api import Failure, Grant, Step, StravaApi
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import Limits, StravaConfig
from fitdocs_relay.strava.custody import Custody
from fitdocs_relay.strava.publish import (
    CALL_TIMEOUT_S,
    PUBLISH_DEADLINE_S,
    STEP_OUTCOMES,
    Landed,
    StravaPublisher,
    activity_page,
)
from fitdocs_relay.strava.resolve import LIST_PAGE_SIZE, LIST_WINDOW_S

NOW = 1_700_000_000
API = "https://api.example/v3"
OAUTH = "https://oauth.example/oauth"
WEB = "https://web.example"
HUGE = 1_000_000
CONFIG = StravaConfig(
    client_id="4711",
    client_secret="client-secret",
    webhook_token="w" * 40,
    api_url=API,
    oauth_url=OAUTH,
    web_url=WEB,
    limits=Limits(HUGE, HUGE, HUGE, HUGE),
)
PEPPER = b"publish-test-pepper-0123456789abcdef"
KEYRING = Keyring((EncryptionKey("newk", bytes(range(32))),))
ACCESS = "access-tok-AAA"
REFRESH = "refresh-tok-RRR"
FAR = NOW + 10_000  # the access token is good for hours
NEAR = NOW + 100  # inside the refresh margin

PLUS_2 = timezone(timedelta(hours=2))
# 10:00:00 at +02:00 is 08:00:00 UTC: a wall-clock compare sees two hours.
START = datetime(2026, 3, 1, 10, 0, 0, tzinfo=PLUS_2)
START_UTC = "2026-03-01T08:00:00Z"
START_S = int(START.timestamp())
PUB_ID = "a" * 32
OTHER_ID = "b" * 32
ACTIVITY_ID = 987654321012
LIST_URL = (
    f"{API}/athlete/activities?after={START_S - LIST_WINDOW_S}"
    f"&before={START_S + LIST_WINDOW_S}&per_page={LIST_PAGE_SIZE}&page=1"
)
UPDATE_URL = f"{API}/activities/{ACTIVITY_ID}"
TOKEN_URL = f"{OAUTH}/token"
FACTS = PublishFacts(
    publication_id=PUB_ID,
    sport="Run",
    start=START,
    elapsed_s=1800.0,
    distance_m=5000.0,
    title="Morning run",
    description="Easy 5k\nfelt good",
)


def entry(
    activity_id: int = ACTIVITY_ID,
    *,
    sport_type: str = "Run",
    start: str = START_UTC,
    elapsed: float = 1800.0,
    distance: float = 5000.0,
) -> dict[str, object]:
    return {
        "id": activity_id,
        "sport_type": sport_type,
        "start_date": start,
        "elapsed_time": elapsed,
        "distance": distance,
    }


def listing_url() -> str:
    return LIST_URL


class Mono:
    """A monotonic clock only the test and the scripted answers move."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.reads = 0
        self.jumps: dict[int, float] = {}

    def __call__(self) -> float:
        """The time; `jumps[n]` moves the clock on its n-th read, before it answers."""
        self.reads += 1
        self.now += self.jumps.get(self.reads, 0.0)
        return self.now


class TickingOutbound(ScriptedOutbound):
    """The scripted outbound that moves the fake clock as each request is made."""

    def __init__(self, mono: Mono) -> None:
        super().__init__()
        self._mono = mono
        self.ticks: dict[tuple[str, str], list[float]] = {}
        self.before_answer: Callable[[OutboundRequest], None] | None = None

    def tick(self, method: str, url: str, *seconds: float) -> None:
        self.ticks.setdefault((method, url), []).extend(seconds)

    def __call__(self, request, timeout):  # type: ignore[no-untyped-def]
        queue = self.ticks.get((request.method, request.url))
        if queue:
            self._mono.now += queue.pop(0)
        if self.before_answer is not None:
            self.before_answer(request)
        return super().__call__(request, timeout)


@dataclass
class World:
    publisher: StravaPublisher
    store: Storage
    outbound: TickingOutbound
    mono: Mono
    budget: StravaBudget
    custody: Custody

    def urls(self, method: str | None = None) -> list[str]:
        return [
            c.request.url
            for c in self.outbound.calls
            if method is None or c.request.method == method
        ]

    def updates(self) -> list[object]:
        return [c for c in self.outbound.calls if c.request.url == UPDATE_URL]


def build(
    store: Storage,
    *,
    limits: Limits | None = None,
    keyring: Keyring = KEYRING,
    web_url: str = WEB,
) -> World:
    mono = Mono()
    outbound = TickingOutbound(mono)
    config = replace(CONFIG, web_url=web_url)
    if limits is not None:
        config = replace(config, limits=limits)
    budget = StravaBudget(store, config.limits, clock=lambda: NOW)
    api = StravaApi(config, outbound=outbound)
    custody = Custody(
        store,
        keyring,
        api,
        budget,
        pepper=PEPPER,
        clock=lambda: NOW,
        monotonic=mono,
        sleep=lambda seconds: None,
    )
    publisher = StravaPublisher(custody, api, budget, config, monotonic=mono)
    return World(publisher, store, outbound, mono, budget, custody)


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    s = open_full_storage()
    for pid in ("ann", "bea"):
        s.create_principal(NewPrincipal(pid, None), now=1)
    return s


@pytest.fixture
def world(store: Storage) -> World:
    w = build(store)
    connect(w)
    return w


def connect(w: World, principal: str = "ann", *, expires: int = FAR) -> None:
    w.custody.store_grant(
        principal, Grant(ACCESS, REFRESH, expires, f"who-{principal}")
    )


def script_list(w: World, *entries: dict[str, object]) -> None:
    w.outbound.expect("GET", listing_url(), reply(200, list(entries)))


def script_update(w: World, *answers: object) -> None:
    w.outbound.expect("PUT", UPDATE_URL, *answers)  # type: ignore[arg-type]


def landed(result: object) -> Landed:
    assert isinstance(result, Landed), result
    return result


# --- the table ------------------------------------------------------------

COLUMNS = (Step.LIST, Step.UPDATE, Step.UPLOAD, Step.UPLOAD_STATUS, Step.REFRESH)
P = PublishCode
TABLE: dict[Failure, tuple[PublishCode | None, ...]] = {
    Failure.AUTH: (
        P.AUTH_REJECTED,
        P.AUTH_REJECTED,
        P.AUTH_REJECTED,
        P.UNCONFIRMED,
        P.AUTH_REJECTED,
    ),
    Failure.FORBIDDEN: (
        P.PERMISSION_DENIED,
        P.PERMISSION_DENIED,
        P.PERMISSION_DENIED,
        P.UNCONFIRMED,
        P.AUTH_REJECTED,
    ),
    Failure.MISSING: (
        P.UNAVAILABLE,
        P.NOT_UPDATABLE,
        P.REJECTED,
        P.UNCONFIRMED,
        P.UNAVAILABLE,
    ),
    Failure.LIMITED: (
        P.RATE_LIMITED,
        P.RATE_LIMITED,
        P.RATE_LIMITED,
        P.UNCONFIRMED,
        P.RATE_LIMITED,
    ),
    Failure.INVALID: (
        P.UNAVAILABLE,
        P.REJECTED,
        P.REJECTED,
        P.UNCONFIRMED,
        P.AUTH_REJECTED,
    ),
    Failure.SERVER: (
        P.UNAVAILABLE,
        P.UNAVAILABLE,
        P.UNCONFIRMED,
        P.UNCONFIRMED,
        P.UNAVAILABLE,
    ),
    Failure.NETWORK: (
        P.UNAVAILABLE,
        P.UNAVAILABLE,
        P.UNCONFIRMED,
        P.UNCONFIRMED,
        P.UNAVAILABLE,
    ),
    Failure.UNREADABLE: (
        P.UNAVAILABLE,
        None,
        P.UNCONFIRMED,
        P.UNCONFIRMED,
        P.UNAVAILABLE,
    ),
}
EXPECTED = {
    (step, failure): code
    for failure, row in TABLE.items()
    for step, code in zip(COLUMNS, row, strict=True)
    if code is not None
}


def test_the_step_outcome_table_is_these_39_rows_literally() -> None:
    assert len(EXPECTED) == 39  # 8 failures x 5 columns, minus (update, unreadable)
    assert dict(STEP_OUTCOMES) == EXPECTED
    assert (Step.UPDATE, Failure.UNREADABLE) not in STEP_OUTCOMES


def test_the_figures_are_these_literals() -> None:
    assert (PUBLISH_DEADLINE_S, CALL_TIMEOUT_S) == (20.0, 8.0)


def test_an_activity_page_is_the_web_base_then_activities_then_the_id() -> None:
    assert activity_page("https://w.example", "42") == "https://w.example/activities/42"
    assert activity_page("http://127.0.0.1:9", "7") == "http://127.0.0.1:9/activities/7"


# a failing answer per failure class (UNREADABLE only has a list/refresh form)
FAILING: dict[Failure, Callable[[], object]] = {
    Failure.AUTH: lambda: reply(401),
    Failure.FORBIDDEN: lambda: reply(403),
    Failure.MISSING: lambda: reply(404),
    Failure.LIMITED: lambda: reply(429),
    Failure.INVALID: lambda: reply(422),
    Failure.SERVER: lambda: reply(503),
    Failure.NETWORK: lambda: OutboundError("network"),
    Failure.UNREADABLE: lambda: reply(200, {"not": "a list"}),
}


# --- the common checks ---------------------------------------------------------


@pytest.mark.parametrize(
    ("elapsed", "distance", "proceeds"),
    [
        (None, None, False),
        (None, 5000.0, True),
        (1800.0, None, True),
        (0.0, None, True),  # zero is a value, not an absent fact
        (None, 0.0, True),
    ],
)
def test_both_facts_absent_is_activity_facts_missing_with_no_call(
    world: World, elapsed: float | None, distance: float | None, proceeds: bool
) -> None:
    facts = replace(FACTS, elapsed_s=elapsed, distance_m=distance)
    # a listing that holds the matching activity, so a proceeding request lands
    listed = entry(elapsed=1800.0 if elapsed is None else elapsed)
    listed["distance"] = distance
    script_list(world, listed)
    script_update(world, reply(200, {}))
    result = world.publisher.publish("ann", facts)
    if proceeds:
        assert landed(result).code is P.POSTED
        assert len(world.outbound.calls) == 2
    else:
        assert result is P.ACTIVITY_FACTS_MISSING
        assert world.outbound.calls == []
        assert world.outbound.unserved() == 2


def test_two_principals_can_publish_the_same_publication_id(world: World) -> None:
    connect(world, "bea")
    for _ in ("ann", "bea"):
        script_list(world, entry())
        script_update(world, reply(200, {}))

    first = world.publisher.publish("ann", FACTS)
    second = world.publisher.publish("bea", FACTS)

    assert landed(first).code is P.POSTED
    assert landed(second).code is P.POSTED
    assert len(world.updates()) == 2  # each one reached Strava


def test_a_landed_publish_leaves_nothing_about_the_workout_in_storage(
    world: World, database_target: Target
) -> None:
    before = stored_rows(database_target)
    assert before["target_connections"], "the precondition: ann is connected"
    script_list(world, entry())
    script_update(world, reply(200, {}))

    assert landed(world.publisher.publish("ann", FACTS)).code is P.POSTED

    assert len(world.updates()) == 1  # the publish really landed
    assert_only_budget_changed(before, stored_rows(database_target), PUB_ID)


def assert_only_budget_changed(
    before: dict[str, list[str]], after: dict[str, list[str]], publication_id: str
) -> None:
    """A request that landed spent budget and left no row about the workout."""
    assert after != before, "the request spent budget, so the dump must differ"
    assert {name for name in after if after[name] != before[name]} == {"budget_counts"}
    assert publication_id not in repr(after)


def test_the_facts_are_checked_before_the_token_is_read(
    store: Storage, database_target: Target
) -> None:
    """With neither fact, no connection is read and no budget is spent: an
    expiring token is not refreshed, and an unconnected principal still hears
    ACTIVITY_FACTS_MISSING rather than NOT_CONNECTED."""
    w = build(store)
    connect(w, expires=NEAR)
    facts = replace(FACTS, elapsed_s=None, distance_m=None)
    before = stored_rows(database_target)

    assert w.publisher.publish("ann", facts) is P.ACTIVITY_FACTS_MISSING
    assert w.publisher.publish("bea", facts) is P.ACTIVITY_FACTS_MISSING

    assert w.outbound.calls == []  # an expiring token was not refreshed
    assert stored_rows(database_target) == before


def test_a_post_stays_posted_when_the_connection_is_withdrawn_meanwhile(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))

    def withdraw(request: OutboundRequest) -> None:
        if request.url == UPDATE_URL:
            assert world.store.delete_connection(
                "ann", "strava", generation=None, now=NOW
            )

    world.outbound.before_answer = withdraw
    assert landed(world.publisher.publish("ann", FACTS)).code is P.POSTED
    assert len(world.updates()) == 1
    assert world.store.get_connection("ann", "strava") is None  # it was withdrawn


def stored_rows(target: Target) -> dict[str, list[str]]:
    """Every row of every table, as `repr` strings, by table name."""
    if isinstance(target, SqliteTarget):
        sql = (
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    else:
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        )
    names = sorted(str(r[0]) for r in raw(target, sql))
    return {
        name: sorted(repr(r) for r in raw(target, f"SELECT * FROM {name}"))
        for name in names
    }


def test_a_principal_with_no_connection_is_not_connected_with_no_call(
    store: Storage,
) -> None:
    w = build(store)
    assert w.publisher.publish("ann", FACTS) is P.NOT_CONNECTED
    assert w.outbound.calls == []


def test_an_unreadable_token_is_not_connected_with_no_call(store: Storage) -> None:
    connect(build(store))
    other = Keyring((EncryptionKey("othr", bytes(range(64, 96))),))
    w = build(store, keyring=other)
    assert w.publisher.publish("ann", FACTS) is P.NOT_CONNECTED
    assert w.outbound.calls == []


@pytest.mark.parametrize("failure", list(Failure), ids=lambda f: f.value)
def test_the_refresh_column_through_a_publish(store: Storage, failure: Failure) -> None:
    w = build(store)
    connect(w, expires=NEAR)
    w.outbound.expect("POST", TOKEN_URL, FAILING[failure]())  # type: ignore[arg-type]
    result = w.publisher.publish("ann", FACTS)
    assert result is EXPECTED[(Step.REFRESH, failure)]
    assert w.urls() == [TOKEN_URL]  # no list, no update


def test_a_refreshed_token_is_the_one_the_list_carries(store: Storage) -> None:
    w = build(store)
    connect(w, expires=NEAR)
    w.outbound.expect(
        "POST",
        TOKEN_URL,
        reply(
            200,
            {"access_token": "access-NEW", "refresh_token": "r2", "expires_at": FAR},
        ),
    )
    script_list(w, entry())
    script_update(w, reply(200, {}))
    assert landed(w.publisher.publish("ann", FACTS)).code is P.POSTED
    list_call, update_call = w.outbound.calls[1:]
    assert list_call.request.secret_headers["Authorization"] == "Bearer access-NEW"
    assert update_call.request.secret_headers["Authorization"] == "Bearer access-NEW"


# --- list and pick -------------------------------------------------------------


def test_the_listing_is_read_around_the_start_with_the_page_size(world: World) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.publisher.publish("ann", FACTS)
    first = world.outbound.calls[0]
    assert first.request.method == "GET"
    assert first.request.url == listing_url()
    assert first.request.secret_headers["Authorization"] == f"Bearer {ACCESS}"
    assert "after=" + str(START_S - 120) in first.request.url
    assert "before=" + str(START_S + 120) in first.request.url
    assert "per_page=30" in first.request.url


@pytest.mark.parametrize("failure", [f for f in Failure], ids=lambda f: f.value)
def test_the_list_column(world: World, failure: Failure) -> None:
    world.outbound.expect("GET", listing_url(), FAILING[failure]())  # type: ignore[arg-type]
    result = world.publisher.publish("ann", FACTS)
    assert result is EXPECTED[(Step.LIST, failure)]
    assert world.urls() == [listing_url()]  # the list was called once, nothing after


def probe_after(w: World, seconds: int) -> bool:
    """Whether the application's overall budget allows a spend `seconds` later."""
    later = StravaBudget(w.store, CONFIG.limits, clock=lambda: NOW + seconds)
    return later.spend("bea").allowed


def test_a_limited_listing_marks_the_quarter_hour_spent(world: World) -> None:
    assert probe_after(world, 0)
    world.outbound.expect("GET", listing_url(), reply(429))
    assert world.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert not probe_after(world, 0)
    assert probe_after(world, 901)  # only the quarter hour, not the day


def test_a_limited_listing_with_a_daily_figure_marks_the_day_spent(
    world: World,
) -> None:
    usage = {"x-ratelimit-usage": f"1,{HUGE}"}
    world.outbound.expect("GET", listing_url(), reply(429, headers=usage))
    assert world.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert not probe_after(world, 901)


def test_a_limited_update_marks_the_quarter_hour_spent(world: World) -> None:
    script_list(world, entry())
    script_update(world, reply(429))
    assert world.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert not probe_after(world, 0)
    assert probe_after(world, 901)


def test_a_limited_update_with_a_daily_figure_marks_the_day_spent(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(429, headers={"x-readratelimit-usage": f"1,{HUGE}"}))
    assert world.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert not probe_after(world, 901)


def test_a_non_limited_failure_does_not_mark_anything_spent(world: World) -> None:
    script_list(world, entry())
    script_update(world, reply(403))
    assert world.publisher.publish("ann", FACTS) is P.PERMISSION_DENIED
    assert probe_after(world, 0)


def test_no_match_is_not_found_and_nothing_is_updated(world: World) -> None:
    script_list(world)
    assert world.publisher.publish("ann", FACTS) is P.NOT_FOUND
    assert world.urls() == [listing_url()]


def test_two_matches_are_ambiguous_and_nothing_is_updated(world: World) -> None:
    script_list(world, entry(1), entry(2))
    assert world.publisher.publish("ann", FACTS) is P.AMBIGUOUS
    assert world.urls() == [listing_url()]


def test_a_full_listing_is_ambiguous_even_when_one_entry_matches(
    world: World,
) -> None:
    decoys = [
        entry(1000 + n, sport_type="Swim", distance=100.0 + n)
        for n in range(LIST_PAGE_SIZE - 1)
    ]
    script_list(world, entry(), *decoys)
    assert world.publisher.publish("ann", FACTS) is P.AMBIGUOUS
    assert world.urls() == [listing_url()]


def test_the_update_goes_to_the_picked_activity_not_the_first_listed(
    world: World,
) -> None:
    decoy = entry(111, sport_type="Swim")
    other_day = entry(222, start="2026-03-01T08:30:00Z")
    script_list(world, decoy, other_day, entry(), entry(333, distance=9999.0))
    script_update(world, reply(200, {}))
    result = world.publisher.publish("ann", FACTS)
    assert landed(result).code is P.POSTED
    assert world.urls("PUT") == [UPDATE_URL]


# --- the update -------------------------------------------------------------


def test_the_update_carries_the_title_and_description_and_the_bearer(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.publisher.publish("ann", FACTS)
    call = world.outbound.calls[1]
    assert call.request.method == "PUT"
    assert call.request.secret_headers["Authorization"] == f"Bearer {ACCESS}"
    assert call.request.body is not None
    assert json.loads(call.request.body) == {
        "name": "Morning run",
        "description": "Easy 5k\nfelt good",
    }


@pytest.mark.parametrize(
    "failure",
    [f for f in Failure if f is not Failure.UNREADABLE],
    ids=lambda f: f.value,
)
def test_the_update_column(world: World, failure: Failure) -> None:
    repeats = failure in (Failure.SERVER, Failure.NETWORK)
    script_list(world, entry())
    # three answers are scripted; a second repeat would be served by the third
    script_update(world, *[FAILING[failure]() for _ in range(3)])
    result = world.publisher.publish("ann", FACTS)
    assert result is EXPECTED[(Step.UPDATE, failure)]
    assert len(world.updates()) == (2 if repeats else 1)
    assert world.outbound.unserved() == (1 if repeats else 2)


def test_an_update_answered_with_a_2xx_is_posted_whatever_its_body_holds(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(200, b"\xff not json at all"))
    assert landed(world.publisher.publish("ann", FACTS)).code is P.POSTED


@pytest.mark.parametrize(
    "first", [Failure.SERVER, Failure.NETWORK], ids=lambda f: f.value
)
def test_a_repeated_update_that_lands_is_posted_and_is_identical(
    world: World, first: Failure
) -> None:
    script_list(world, entry())
    script_update(world, FAILING[first](), reply(200, {}))
    result = landed(world.publisher.publish("ann", FACTS))
    assert result.code is P.POSTED
    one, two = [c.request for c in world.outbound.calls[1:]]
    assert one == two and one.method == "PUT"
    assert len(world.updates()) == 2


@pytest.mark.parametrize(
    ("second", "code"),
    [(401, P.AUTH_REJECTED), (404, P.NOT_UPDATABLE), (429, P.RATE_LIMITED)],
)
def test_the_repeat_answer_is_mapped_by_the_column(
    world: World, second: int, code: PublishCode
) -> None:
    script_list(world, entry())
    script_update(world, reply(500), reply(second), reply(200, {}))
    assert world.publisher.publish("ann", FACTS) is code
    assert len(world.updates()) == 2
    assert world.outbound.unserved() == 1


def test_a_failure_that_is_not_server_or_network_is_never_repeated(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(422), reply(200, {}))
    assert world.publisher.publish("ann", FACTS) is P.REJECTED
    assert len(world.updates()) == 1


# --- the landed outcome -------------------------------------------------------


def test_a_posted_result_carries_the_updated_activitys_page_address(
    world: World,
) -> None:
    script_list(world, entry(111, sport_type="Swim"), entry())
    script_update(world, reply(200, {}))
    result = landed(world.publisher.publish("ann", FACTS))
    assert result.code is P.POSTED
    assert result.activity_page == f"{WEB}/activities/{ACTIVITY_ID}"
    assert result.activity_page == activity_page(WEB, str(ACTIVITY_ID))
    assert str(ACTIVITY_ID) not in repr(result)
    assert WEB not in repr(result)


def test_the_page_address_is_built_from_the_configured_web_base(store: Storage) -> None:
    w = build(store, web_url="http://127.0.0.1:9")
    connect(w)
    script_list(w, entry())
    script_update(w, reply(200, {}))
    result = landed(w.publisher.publish("ann", FACTS))
    assert result.activity_page == f"http://127.0.0.1:9/activities/{ACTIVITY_ID}"


def test_a_landed_publish_logs_neither_the_activity_id_nor_the_page(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))
    with caplog.at_level(logging.DEBUG):
        result = landed(world.publisher.publish("ann", FACTS))
    assert result.activity_page.endswith(str(ACTIVITY_ID))  # the thing not to log
    for record in caplog.records:
        text = record.getMessage() + " " + str(record.args) + " " + str(record.exc_text)
        assert str(ACTIVITY_ID) not in text
        assert result.activity_page not in text
    assert str(ACTIVITY_ID) not in caplog.text


# --- the deadline ---------------------------------------------------------------


def test_each_call_gets_the_per_call_timeout_while_the_deadline_is_far(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.publisher.publish("ann", FACTS)
    assert [c.timeout for c in world.outbound.calls] == [8.0, 8.0]


def test_a_call_gets_the_time_left_when_that_is_less_than_the_per_call_timeout(
    world: World,
) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.outbound.tick("GET", listing_url(), 15.0)
    world.publisher.publish("ann", FACTS)
    assert [c.timeout for c in world.outbound.calls] == [8.0, 5.0]


def test_the_deadline_is_twenty_seconds_from_the_start_of_the_request(
    world: World,
) -> None:
    world.mono.now = 5000.0
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.outbound.tick("GET", listing_url(), 19.5)
    assert landed(world.publisher.publish("ann", FACTS)).code is P.POSTED
    assert world.outbound.calls[1].timeout == pytest.approx(0.5)


def test_no_update_is_made_once_the_deadline_has_passed(world: World) -> None:
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.outbound.tick("GET", listing_url(), 20.0)  # exactly the deadline
    assert world.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert world.urls() == [listing_url()]


def test_no_repeat_is_made_once_the_deadline_has_passed(world: World) -> None:
    script_list(world, entry())
    script_update(world, reply(503), reply(200, {}))
    world.outbound.tick("PUT", UPDATE_URL, 20.0)
    assert world.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert len(world.updates()) == 1


def test_the_repeat_gets_the_time_left(world: World) -> None:
    script_list(world, entry())
    script_update(world, reply(503), reply(200, {}))
    world.outbound.tick("PUT", UPDATE_URL, 14.0)
    assert landed(world.publisher.publish("ann", FACTS)).code is P.POSTED
    assert [c.timeout for c in world.outbound.calls] == [8.0, 8.0, 6.0]


def test_no_listing_is_made_when_the_refresh_used_the_whole_deadline(
    store: Storage,
) -> None:
    w = build(store)
    connect(w, expires=NEAR)
    w.outbound.expect(
        "POST",
        TOKEN_URL,
        reply(200, {"access_token": "n", "refresh_token": "r", "expires_at": FAR}),
    )
    w.outbound.tick("POST", TOKEN_URL, 20.0)
    assert w.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert w.urls() == [TOKEN_URL]


def test_the_refresh_is_given_the_same_deadline_as_the_rest_of_the_request(
    store: Storage,
) -> None:
    w = build(store)
    connect(w, expires=NEAR)
    # read 1 sets the deadline, read 2 is the refresh's own look at the time left
    w.mono.jumps[2] = 15.0
    w.outbound.expect("POST", TOKEN_URL, reply(503))
    assert w.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert [c.timeout for c in w.outbound.calls] == [5.0]


# --- the budget --------------------------------------------------------------------


def test_a_budget_refusal_before_the_listing_is_rate_limited_with_no_call(
    world: World,
) -> None:
    world.budget.mark_spent(daily=False)
    assert world.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert world.outbound.calls == []


# ann's share of each window is half of 4: a listing and an update fit, a
# repeat does not; bea's share is separate.
TIGHT = Limits(4, 4, 4, 4)
TIGHTER = Limits(2, 2, 2, 2)  # ann's share is one call: the listing only


def test_the_update_is_counted_before_it_is_made(store: Storage) -> None:
    w = build(store, limits=TIGHTER)
    connect(w)
    script_list(w, entry())
    script_update(w, reply(200, {}))
    assert w.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert w.urls() == [listing_url()]
    assert w.budget.spend("bea").allowed  # a refusal is not a Strava limit


def test_the_listing_is_counted_before_it_is_made(store: Storage) -> None:
    w = build(store, limits=TIGHTER)
    connect(w)
    assert w.budget.spend("ann").allowed  # ann's one call is gone
    assert w.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert w.outbound.calls == []
    assert w.budget.spend("bea").allowed  # a refusal is not a Strava limit


def test_the_repeat_is_counted_before_it_is_made(store: Storage) -> None:
    w = build(store, limits=TIGHT)
    connect(w)
    script_list(w, entry())
    script_update(w, reply(503), reply(200, {}))
    assert w.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert len(w.updates()) == 1
    assert w.budget.spend("bea").allowed


def test_the_update_is_counted_as_a_non_upload_call(store: Storage) -> None:
    # wide overall windows, ann's non-upload share is 2: the listing and the
    # update use it, so the repeat is refused. An update counted as an upload
    # would leave the non-upload share alone and let the repeat through.
    w = build(store, limits=Limits(HUGE, HUGE, 4, 4))
    connect(w)
    script_list(w, entry())
    script_update(w, reply(503), reply(200, {}))
    assert w.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert len(w.updates()) == 1


def test_the_refresh_is_counted_against_the_publishing_ceiling(store: Storage) -> None:
    # ann's share is one call: the publishing ceiling admits the refresh; then
    # the list is refused.
    w = build(store, limits=TIGHTER)
    connect(w, expires=NEAR)
    w.outbound.expect(
        "POST",
        TOKEN_URL,
        reply(200, {"access_token": "n", "refresh_token": "r", "expires_at": FAR}),
    )
    script_list(w, entry())
    assert w.publisher.publish("ann", FACTS) is P.RATE_LIMITED
    assert w.urls() == [TOKEN_URL]


def test_no_listing_is_counted_once_the_deadline_has_passed(store: Storage) -> None:
    w = build(store, limits=TIGHT)  # ann's share is two calls
    connect(w, expires=NEAR)
    w.outbound.expect(
        "POST",
        TOKEN_URL,
        reply(200, {"access_token": "n", "refresh_token": "r", "expires_at": FAR}),
    )
    w.outbound.tick("POST", TOKEN_URL, 20.0)
    assert w.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert w.urls() == [TOKEN_URL]
    assert w.budget.spend(
        "ann"
    ).allowed  # the refresh took one; no listing took the other


def test_no_update_is_counted_once_the_deadline_has_passed(store: Storage) -> None:
    w = build(store, limits=TIGHT)  # ann's share is two calls
    connect(w)
    script_list(w, entry())
    script_update(w, reply(200, {}))
    w.outbound.tick("GET", listing_url(), 20.0)
    assert w.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert w.updates() == []
    assert w.budget.spend(
        "ann"
    ).allowed  # the listing took one; no update took the other


def test_no_repeat_is_counted_once_the_deadline_has_passed(store: Storage) -> None:
    w = build(store, limits=Limits(6, 6, 6, 6))  # ann's share is three calls
    connect(w)
    script_list(w, entry())
    script_update(w, reply(503), reply(200, {}))
    w.outbound.tick("PUT", UPDATE_URL, 20.0)
    assert w.publisher.publish("ann", FACTS) is P.UNAVAILABLE
    assert len(w.updates()) == 1
    assert w.budget.spend("ann").allowed  # the listing and the update took two
