"""The Strava upload flow (task 3.7) on both backends.

Strava is the scripted outbound: a request nobody scripted raises
`UnscriptedCall`, and the recorded calls are the count of Strava requests. The
monotonic clock is a fake that moves only when the test, a scripted answer or
the publisher's sleep moves it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pytest
from tests.strava.scripted_strava import Call, reply
from tests.strava.test_publish import (
    ACCESS,
    API,
    CONFIG,
    EXPECTED,
    FACTS,
    FAILING,
    FAR,
    HUGE,
    KEYRING,
    NEAR,
    NOW,
    PEPPER,
    PUB_ID,
    REFRESH,
    START,
    TIGHTER,
    TOKEN_URL,
    UPDATE_URL,
    WEB,
    Mono,
    TickingOutbound,
    entry,
    landed,
    listing_url,
    probe_after,
    script_list,
    script_update,
)
from tests.strava.test_publish import (
    World as BaseWorld,
)

from fitdocs_relay.crypto import EncryptionKey, Keyring
from fitdocs_relay.outbound import OutboundError, OutboundRequest
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.storage.interface import NewPrincipal, Publication, Storage
from fitdocs_relay.strava.api import Failure, Grant, Step, StravaApi
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import Limits, StravaConfig
from fitdocs_relay.strava.custody import Custody
from fitdocs_relay.strava.publish import (
    MAX_UPLOAD_POLLS,
    UPLOAD_DEADLINE_S,
    UPLOAD_FOLLOW_UPS,
    UPLOAD_POLL_INTERVAL_S,
    StravaPublisher,
)
from fitdocs_relay.strava.resolve import LIST_PAGE_SIZE

P = PublishCode
UPLOAD_URL = f"{API}/uploads"
UPLOAD_ID = 5550001
STATUS_URL = f"{API}/uploads/{UPLOAD_ID}"
NEW_ID = 424242424242  # the activity an upload created
FIT = b"FIT-FILE-\x00\x01\x02-payload-bytes"
SECRET_TEXT = "secret-detail-9d3f"


@dataclass
class World(BaseWorld):
    sleeps: list[float] = field(default_factory=list)
    overshoot: list[float] = field(default_factory=list)

    def hits(self, url: str) -> list[Call]:
        return [c for c in self.outbound.calls if c.request.url == url]

    def uploads(self) -> list[Call]:
        return [c for c in self.outbound.calls if c.request.url == UPLOAD_URL]

    def polls(self) -> list[Call]:
        return self.hits(STATUS_URL)


def build(
    store: Storage, *, limits: Limits | None = None, keyring: Keyring = KEYRING
) -> World:
    mono = Mono()
    outbound = TickingOutbound(mono)
    config: StravaConfig = CONFIG if limits is None else replace(CONFIG, limits=limits)
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
    sleeps: list[float] = []
    overshoot: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        mono.now += seconds + (overshoot.pop(0) if overshoot else 0.0)

    publisher = StravaPublisher(
        store,
        custody,
        api,
        budget,
        config,
        clock=lambda: NOW,
        monotonic=mono,
        sleep=sleep,
    )
    return World(publisher, store, outbound, mono, budget, custody, sleeps, overshoot)


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    s = open_full_storage()
    for pid in ("ann", "bea"):
        s.create_principal(NewPrincipal(pid, None), now=1)
    return s


@pytest.fixture
def world(store: Storage) -> World:
    w = build(store)
    connect(w, "ann")
    return w


def connect(w: World, principal: str, *, expires: int = FAR) -> None:
    w.custody.store_grant(
        principal, Grant(ACCESS, REFRESH, expires, f"who-{principal}")
    )


def put_other(w: World) -> None:
    assert w.store.put_publication(
        Publication("strava", PUB_ID, "bea", "Run", 5.0, 1.0, 2.0), now=NOW
    )


def upload(w: World, facts=FACTS, principal: str = "ann"):  # type: ignore[no-untyped-def]
    return w.publisher.upload(principal, facts, FIT)


def script_upload(w: World, *answers: object) -> None:
    w.outbound.expect("POST", UPLOAD_URL, *answers)  # type: ignore[arg-type]


def created() -> object:
    return reply(201, {"id": UPLOAD_ID, "error": None, "activity_id": None})


def pending() -> object:
    return reply(200, {"id": UPLOAD_ID, "error": None, "activity_id": None})


def ready(activity_id: int = NEW_ID) -> object:
    return reply(200, {"id": UPLOAD_ID, "error": None, "activity_id": activity_id})


def failed() -> object:
    return reply(200, {"id": UPLOAD_ID, "error": "some words", "activity_id": None})


def script_status(w: World, *answers: object) -> None:
    w.outbound.expect("GET", STATUS_URL, *answers)  # type: ignore[arg-type]


def script_none_then_ready(w: World) -> None:
    script_list(w)
    script_upload(w, created())
    script_status(w, ready())


def spent(w: World) -> bool:
    """Whether Strava's 429 marked the application's quarter hour spent."""
    return not probe_after(w, 0)


# --- the figures ---


def test_the_figures_are_these_literals() -> None:
    assert (
        UPLOAD_DEADLINE_S,
        UPLOAD_POLL_INTERVAL_S,
        MAX_UPLOAD_POLLS,
        UPLOAD_FOLLOW_UPS,
    ) == (25.0, 2.0, 8, 2)


# --- the common start ---


def test_both_facts_absent_is_activity_facts_missing_with_no_call(world: World) -> None:
    facts = replace(FACTS, elapsed_s=None, distance_m=None)
    script_none_then_ready(world)
    assert upload(world, facts) is P.ACTIVITY_FACTS_MISSING
    assert world.outbound.calls == []
    assert world.outbound.unserved() == 3


def test_a_publication_id_owned_by_another_principal_is_rejected_with_no_call(
    world: World,
) -> None:
    connect(world, "bea")
    put_other(world)
    script_none_then_ready(world)
    assert upload(world) is P.REJECTED
    assert world.outbound.calls == []
    stored = world.store.get_publication("strava", PUB_ID)
    assert stored is not None and stored.principal_id == "bea"


def test_a_principal_with_no_connection_is_not_connected_with_no_call(
    store: Storage,
) -> None:
    w = build(store)
    script_none_then_ready(w)
    assert upload(w) is P.NOT_CONNECTED
    assert w.outbound.calls == []


def test_an_undecryptable_token_ends_the_request_before_any_call(
    store: Storage,
) -> None:
    connect(build(store), "ann")
    other = Keyring((EncryptionKey("othr", bytes(range(64, 96))),))
    w = build(store, keyring=other)
    script_none_then_ready(w)
    assert upload(w) is P.NOT_CONNECTED
    assert w.outbound.calls == []  # no listing, so no upload either
    assert w.outbound.unserved() == 3


@pytest.mark.parametrize("failure", list(Failure), ids=lambda f: f.value)
def test_the_refresh_column_through_an_upload(store: Storage, failure: Failure) -> None:
    w = build(store)
    connect(w, "ann", expires=NEAR)
    w.outbound.expect("POST", TOKEN_URL, FAILING[failure]())  # type: ignore[arg-type]
    script_none_then_ready(w)
    assert upload(w) is EXPECTED[(Step.REFRESH, failure)]
    assert w.urls() == [TOKEN_URL]


# --- the listing and the upload guard ---


@pytest.mark.parametrize("failure", list(Failure), ids=lambda f: f.value)
def test_the_list_column_never_reaches_the_upload(
    world: World, failure: Failure
) -> None:
    world.outbound.expect("GET", listing_url(), FAILING[failure]())  # type: ignore[arg-type]
    script_upload(world, created())
    assert upload(world) is EXPECTED[(Step.LIST, failure)]
    assert [c.request.url for c in world.outbound.calls] == [listing_url()]
    assert world.outbound.unserved() == 1  # the scripted upload was never served
    assert world.store.get_publication("strava", PUB_ID) is None


def test_a_listing_with_a_malformed_entry_is_unreadable_not_empty(
    world: World,
) -> None:
    # without the malformed entry nothing matches, which would upload
    script_list(world, entry(111, sport_type="Swim"), {"id": "not-a-number"})
    script_upload(world, created())
    assert upload(world) is P.UNAVAILABLE
    assert world.uploads() == []


def test_a_full_listing_is_ambiguous_and_never_uploads(world: World) -> None:
    decoys = [
        entry(1000 + n, sport_type="Swim", distance=100.0 + n)
        for n in range(LIST_PAGE_SIZE)
    ]
    script_list(world, *decoys)  # none matches: only fullness stops the upload
    script_upload(world, created())
    assert upload(world) is P.AMBIGUOUS
    assert world.uploads() == []


def test_two_matches_are_ambiguous_and_never_upload(world: World) -> None:
    script_list(world, entry(1), entry(2))
    script_upload(world, created())
    assert upload(world) is P.AMBIGUOUS
    assert world.uploads() == []


def test_a_storage_failure_reading_the_publication_ends_the_request_first(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError(SECRET_TEXT)

    monkeypatch.setattr(world.store, "get_publication", broken)
    script_none_then_ready(world)
    with pytest.raises(RuntimeError):
        upload(world)
    assert world.outbound.calls == []


def test_a_storage_failure_reserving_the_budget_ends_the_request_before_the_upload(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = world.store.spend_budget
    seen: list[int] = []

    def second_breaks(*args: object, **kwargs: object) -> object:
        seen.append(1)
        if len(seen) == 2:  # the listing's spend passes, the reservation breaks
            raise RuntimeError(SECRET_TEXT)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(world.store, "spend_budget", second_breaks)
    script_none_then_ready(world)
    with pytest.raises(RuntimeError):
        upload(world)
    assert [c.request.url for c in world.outbound.calls] == [listing_url()]


# --- a match found before any upload ---


def test_one_match_is_updated_and_posted_with_no_upload(world: World) -> None:
    script_list(world, entry(111, sport_type="Swim"), entry())
    script_update(world, reply(200, {}))
    script_upload(world, created())
    result = landed(upload(world))
    assert result.code is P.POSTED
    assert result.activity_page == f"{WEB}/activities/987654321012"
    assert world.uploads() == []
    assert world.store.get_publication("strava", PUB_ID) is not None


@pytest.mark.parametrize(
    "failure",
    [f for f in Failure if f is not Failure.UNREADABLE],
    ids=lambda f: f.value,
)
def test_the_update_column_through_an_upload(world: World, failure: Failure) -> None:
    repeats = failure in (Failure.SERVER, Failure.NETWORK)
    script_list(world, entry())
    script_update(world, *[FAILING[failure]() for _ in range(3)])
    assert upload(world) is EXPECTED[(Step.UPDATE, failure)]
    assert len(world.hits(UPDATE_URL)) == (2 if repeats else 1)
    assert world.uploads() == []


# --- the reservation ---


def test_the_upload_is_reserved_with_the_polls_and_follow_ups_in_one_operation(
    store: Storage,
) -> None:
    # ann's share of the non-upload windows is 11: the listing and the ten
    # reserved reads; the overall windows (share 12) also hold the upload itself.
    w = build(store, limits=Limits(24, 24, 22, 22))
    connect(w, "ann")
    script_none_then_ready(w)
    assert landed(upload(w)).code is P.UPLOADED
    assert not w.budget.spend("ann").allowed  # nothing is left of ann's share


def test_a_reservation_one_read_too_big_is_refused_with_no_upload(
    store: Storage,
) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 20, 20))  # share 10: 1 + 10 > 10
    connect(w, "ann")
    script_none_then_ready(w)
    assert upload(w) is P.RATE_LIMITED
    assert [c.request.url for c in w.outbound.calls] == [listing_url()]
    assert w.budget.spend("bea").allowed  # a refusal is not Strava's limit


def test_the_upload_itself_is_counted_in_the_overall_windows(store: Storage) -> None:
    # share 11 overall: the listing (1) + the reservation's upload and ten reads
    # (11) is 12, one too many
    w = build(store, limits=Limits(22, 22, HUGE, HUGE))
    connect(w, "ann")
    script_none_then_ready(w)
    assert upload(w) is P.RATE_LIMITED
    assert w.uploads() == []


def test_a_refused_reservation_is_not_a_strava_limit(store: Storage) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 20, 20))
    connect(w, "ann")
    script_none_then_ready(w)
    assert upload(w) is P.RATE_LIMITED
    assert probe_after(w, 0)  # the application's windows were not marked spent


def test_no_reservation_is_made_for_a_request_that_updates(store: Storage) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 4, 4))  # share 2: list + update
    connect(w, "ann")
    script_list(w, entry())
    script_update(w, reply(200, {}))
    assert landed(upload(w)).code is P.POSTED


# --- the upload call ---


def test_the_upload_is_one_multipart_post_of_the_file_with_the_posts_fields(
    world: World,
) -> None:
    script_none_then_ready(world)
    assert landed(upload(world)).code is P.UPLOADED
    (call,) = world.uploads()
    assert call.request.method == "POST"
    assert call.request.secret_headers["Authorization"] == f"Bearer {ACCESS}"
    body = call.request.body
    assert body is not None and FIT in body
    for field_name, value in (
        ("name", "Morning run"),
        ("description", "Easy 5k\nfelt good"),
        ("external_id", PUB_ID),
        ("data_type", "fit"),
    ):
        wanted = f'name="{field_name}"\r\n\r\n{value}\r\n'.encode()
        assert wanted in body, field_name


@pytest.mark.parametrize("failure", list(Failure), ids=lambda f: f.value)
def test_the_upload_column_and_the_upload_is_never_repeated(
    world: World, failure: Failure
) -> None:
    script_list(world)
    answer = {Failure.UNREADABLE: lambda: reply(200, {"no": "id"})}.get(
        failure, FAILING[failure]
    )()
    script_upload(world, answer, created(), created())  # a repeat would be served
    result = upload(world)
    assert result is EXPECTED[(Step.UPLOAD, failure)]
    assert len(world.uploads()) == 1
    assert world.outbound.unserved() == 2
    assert world.polls() == []
    assert world.store.get_publication("strava", PUB_ID) is None
    assert spent(world) is (failure is Failure.LIMITED)


def test_an_upload_answered_with_a_server_error_is_unconfirmed_after_one_hit(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, reply(503), created())
    assert upload(world) is P.UNCONFIRMED
    assert len(world.uploads()) == 1


def test_a_limited_upload_with_a_daily_figure_marks_the_day_spent(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, reply(429, headers={"x-ratelimit-usage": f"1,{HUGE}"}))
    assert upload(world) is P.RATE_LIMITED
    assert not probe_after(world, 901)


# --- the status polls ---


def test_a_ready_upload_is_uploaded_with_the_created_activitys_page_and_a_record(
    world: World,
) -> None:
    script_list(world, entry(111, sport_type="Swim"))
    script_upload(world, created())
    script_status(world, ready())
    assert world.store.get_publication("strava", PUB_ID) is None
    result = landed(upload(world))
    assert result.code is P.UPLOADED
    assert result.activity_page == f"{WEB}/activities/{NEW_ID}"
    assert str(NEW_ID) not in repr(result) and WEB not in repr(result)
    assert world.store.get_publication("strava", PUB_ID) == Publication(
        "strava", PUB_ID, "ann", "Run", START.timestamp(), 1800.0, 5000.0
    )


def test_pending_polls_wait_the_interval_before_each_poll_until_ready(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, pending(), pending(), ready(), ready())
    assert landed(upload(world)).code is P.UPLOADED
    assert len(world.polls()) == 3
    assert world.sleeps == [2.0, 2.0, 2.0]
    assert world.outbound.unserved() == 1
    assert all(c.request.method == "GET" for c in world.polls())
    assert all(
        c.request.secret_headers["Authorization"] == f"Bearer {ACCESS}"
        for c in world.polls()
    )


def test_a_poll_is_made_after_the_wait_not_before_it(world: World) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())
    world.outbound.before_answer = lambda request: (
        world.sleeps.append(-1.0) if request.url == STATUS_URL else None
    )
    upload(world)
    assert world.sleeps == [2.0, -1.0]  # the wait came first


def test_an_upload_still_pending_after_the_eighth_poll_is_unconfirmed(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, *[pending() for _ in range(MAX_UPLOAD_POLLS + 1)])
    assert upload(world) is P.UNCONFIRMED
    assert len(world.polls()) == 8
    assert world.outbound.unserved() == 1
    assert world.store.get_publication("strava", PUB_ID) is None


def test_an_upload_ready_on_the_eighth_poll_is_uploaded(world: World) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, *[pending() for _ in range(7)], ready())
    assert landed(upload(world)).code is P.UPLOADED
    assert len(world.polls()) == 8


@pytest.mark.parametrize("failure", list(Failure), ids=lambda f: f.value)
def test_the_status_column_is_unconfirmed_for_every_failure(
    world: World, failure: Failure
) -> None:
    script_list(world)
    script_upload(world, created())
    answer = {Failure.UNREADABLE: lambda: reply(200, [1])}.get(
        failure, FAILING[failure]
    )()
    script_status(world, answer, ready())
    assert upload(world) is EXPECTED[(Step.UPLOAD_STATUS, failure)] is P.UNCONFIRMED
    assert len(world.polls()) == 1
    assert world.store.get_publication("strava", PUB_ID) is None
    assert spent(world) is (failure is Failure.LIMITED)


# --- a failed upload resolves again ---


def failed_upload(w: World) -> None:
    script_list(w)
    script_upload(w, created())
    script_status(w, failed())


def test_a_failed_upload_with_one_match_updates_it_on_the_reserved_calls(
    store: Storage,
) -> None:
    # share 11 holds the first listing and the reservation: the second listing
    # and the update are counted nowhere, or this would be refused
    w = build(store, limits=Limits(24, 24, 22, 22))
    connect(w, "ann")
    failed_upload(w)
    script_list(w, entry(111, sport_type="Swim"), entry())
    script_update(w, reply(200, {}))
    result = landed(upload(w))
    assert result.code is P.POSTED
    assert result.activity_page == f"{WEB}/activities/987654321012"
    assert len(w.hits(listing_url())) == 2
    assert len(w.uploads()) == 1
    assert w.store.get_publication("strava", PUB_ID) is not None


def test_a_failed_upload_with_several_matches_is_ambiguous(world: World) -> None:
    failed_upload(world)
    script_list(world, entry(1), entry(2))
    assert upload(world) is P.AMBIGUOUS
    assert world.hits(UPDATE_URL) == []
    assert world.store.get_publication("strava", PUB_ID) is None


def test_a_failed_upload_with_a_full_listing_is_ambiguous(world: World) -> None:
    failed_upload(world)
    script_list(
        world,
        *[
            entry(1000 + n, sport_type="Swim", distance=100.0 + n)
            for n in range(LIST_PAGE_SIZE)
        ],
    )
    assert upload(world) is P.AMBIGUOUS


def test_a_failed_upload_with_no_match_is_rejected(world: World) -> None:
    failed_upload(world)
    script_list(world, entry(111, sport_type="Swim"))
    assert upload(world) is P.REJECTED
    assert len(world.uploads()) == 1
    assert world.store.get_publication("strava", PUB_ID) is None


@pytest.mark.parametrize("failure", list(Failure), ids=lambda f: f.value)
def test_a_listing_failure_after_the_upload_is_unconfirmed(
    world: World, failure: Failure
) -> None:
    failed_upload(world)
    world.outbound.expect("GET", listing_url(), FAILING[failure]())  # type: ignore[arg-type]
    assert upload(world) is P.UNCONFIRMED
    assert len(world.uploads()) == 1
    assert spent(world) is (failure is Failure.LIMITED)


@pytest.mark.parametrize(
    "failure",
    [f for f in Failure if f is not Failure.UNREADABLE],
    ids=lambda f: f.value,
)
def test_the_update_after_a_failed_upload_is_mapped_by_the_update_column_once(
    world: World, failure: Failure
) -> None:
    failed_upload(world)
    script_list(world, entry())
    script_update(world, FAILING[failure](), FAILING[failure]())
    assert upload(world) is EXPECTED[(Step.UPDATE, failure)]
    assert len(world.hits(UPDATE_URL)) == 1  # not repeated, even on a 5xx
    assert len(world.uploads()) == 1


# --- the deadline ---


def test_the_deadline_is_twenty_five_seconds_from_the_start(world: World) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())
    world.outbound.tick("GET", listing_url(), 24.5)
    assert upload(world) is P.UNCONFIRMED  # no time is left to poll
    assert world.uploads()[0].timeout == pytest.approx(0.5)


def test_no_upload_or_reservation_is_made_once_the_deadline_has_passed(
    store: Storage,
) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 22, 22))  # share 11
    connect(w, "ann")
    script_none_then_ready(w)
    w.outbound.tick("GET", listing_url(), 25.0)
    assert upload(w) is P.UNAVAILABLE
    assert [c.request.url for c in w.outbound.calls] == [listing_url()]
    # the reservation was not made: ten reads are still there to spend
    assert w.budget.spend("ann", count=10).allowed


def test_the_upload_and_the_polls_get_the_per_call_timeout_or_the_time_left(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, pending(), ready())
    world.outbound.tick("POST", UPLOAD_URL, 18.0)  # 7 s left; the wait takes 2
    assert landed(upload(world)).code is P.UPLOADED
    timeouts = [c.timeout for c in world.outbound.calls]
    assert timeouts == [8.0, 8.0, 5.0, pytest.approx(3.0)]  # list, upload, 2 polls


def test_a_poll_is_not_made_when_the_wait_would_reach_the_deadline(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())
    world.outbound.tick("POST", UPLOAD_URL, 23.0)  # exactly one interval left
    assert upload(world) is P.UNCONFIRMED
    assert world.polls() == []
    assert world.sleeps == []


def test_a_poll_is_made_when_the_wait_leaves_time_before_the_deadline(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())
    world.outbound.tick("POST", UPLOAD_URL, 22.5)  # 2.5 s left
    assert landed(upload(world)).code is P.UPLOADED
    assert world.polls()[0].timeout == pytest.approx(0.5)


def test_a_wait_that_overshoots_the_deadline_leaves_no_poll(world: World) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())
    world.overshoot.append(60.0)
    assert upload(world) is P.UNCONFIRMED
    assert world.polls() == []


def test_polling_stops_when_the_deadline_passes_between_polls(world: World) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, *[pending() for _ in range(8)])
    world.outbound.tick("GET", STATUS_URL, 9.0, 9.0, 9.0)
    assert upload(world) is P.UNCONFIRMED
    assert [c.timeout for c in world.polls()] == [8.0, 8.0, pytest.approx(1.0)]
    assert world.outbound.unserved() == 5


def test_the_deadline_after_a_failed_upload_leaves_no_second_listing(
    world: World,
) -> None:
    failed_upload(world)
    script_list(world, entry())
    world.outbound.tick("GET", STATUS_URL, 24.0)
    assert upload(world) is P.UNCONFIRMED
    assert len(world.hits(listing_url())) == 1


def test_the_deadline_after_the_second_listing_leaves_no_update(world: World) -> None:
    failed_upload(world)
    script_list(world, entry())
    script_update(world, reply(200, {}))
    world.outbound.tick("GET", listing_url(), 0.0, 24.0)
    assert upload(world) is P.UNCONFIRMED
    assert world.hits(UPDATE_URL) == []


# --- the record ---


def test_a_connection_withdrawn_before_the_record_leaves_no_record_but_is_uploaded(
    world: World,
) -> None:
    script_none_then_ready(world)

    def withdraw(request: OutboundRequest) -> None:
        if request.url == STATUS_URL:
            world.store.delete_connection("ann", "strava", generation=None, now=NOW)

    world.outbound.before_answer = withdraw
    assert landed(upload(world)).code is P.UPLOADED
    assert world.store.get_publication("strava", PUB_ID) is None


def test_a_record_another_principal_took_during_the_request_is_left_alone(
    world: World,
) -> None:
    script_none_then_ready(world)

    def take(request: OutboundRequest) -> None:
        if request.url == STATUS_URL:
            put_other(world)

    world.outbound.before_answer = take
    assert landed(upload(world)).code is P.UPLOADED
    stored = world.store.get_publication("strava", PUB_ID)
    assert stored == Publication("strava", PUB_ID, "bea", "Run", 5.0, 1.0, 2.0)


def test_an_absent_fact_is_stored_as_none_not_zero(world: World) -> None:
    facts = replace(FACTS, distance_m=None)
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())
    world.publisher.upload("ann", facts, FIT)
    stored = world.store.get_publication("strava", PUB_ID)
    assert stored is not None
    assert stored.distance_m is None and stored.elapsed_s == 1800.0


# --- after the upload call ---


def test_a_storage_failure_writing_the_record_after_the_upload_is_unconfirmed(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    script_none_then_ready(world)

    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError(SECRET_TEXT)

    monkeypatch.setattr(world.store, "put_publication", broken)
    with caplog.at_level(logging.DEBUG):
        assert upload(world) is P.UNCONFIRMED
    assert len(world.uploads()) == 1
    assert "RuntimeError" in caplog.text
    assert SECRET_TEXT not in caplog.text
    assert all(r.exc_info is None for r in caplog.records)


def test_a_storage_failure_reading_the_connection_after_the_upload_is_unconfirmed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    script_none_then_ready(world)
    real = world.store.get_connection

    def broken_once_uploaded(*args: object, **kwargs: object) -> object:
        if world.uploads():
            raise RuntimeError(SECRET_TEXT)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(world.store, "get_connection", broken_once_uploaded)
    assert upload(world) is P.UNCONFIRMED
    assert len(world.polls()) == 1  # it got as far as the record


def test_a_storage_failure_after_a_failed_uploads_update_is_unconfirmed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed_upload(world)
    script_list(world, entry())
    script_update(world, reply(200, {}))

    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError(SECRET_TEXT)

    monkeypatch.setattr(world.store, "put_publication", broken)
    assert upload(world) is P.UNCONFIRMED
    assert len(world.hits(UPDATE_URL)) == 1


def test_an_unexpected_exception_while_polling_is_unconfirmed_logged_by_type(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    script_list(world)
    script_upload(world, created())
    script_status(world, ready())

    def explode(request: OutboundRequest) -> None:
        if request.url == STATUS_URL:
            raise ValueError(SECRET_TEXT)

    world.outbound.before_answer = explode
    with caplog.at_level(logging.DEBUG):
        assert upload(world) is P.UNCONFIRMED
    assert "ValueError" in caplog.text and SECRET_TEXT not in caplog.text


def test_an_unexpected_exception_from_the_upload_call_is_unconfirmed_after_one_hit(
    world: World,
) -> None:
    script_list(world)
    script_upload(world, created())
    attempts: list[str] = []

    def explode(request: OutboundRequest) -> None:
        if request.url == UPLOAD_URL:
            attempts.append(request.url)
            raise KeyError(SECRET_TEXT)

    world.outbound.before_answer = explode
    assert upload(world) is P.UNCONFIRMED
    assert len(attempts) == 1
    assert world.polls() == []


def test_an_error_before_the_upload_is_not_answered_unconfirmed(
    world: World,
) -> None:
    def explode(request: OutboundRequest) -> None:
        raise KeyError(SECRET_TEXT)

    script_none_then_ready(world)
    world.outbound.before_answer = explode  # raised by the listing
    with pytest.raises(KeyError):
        upload(world)
    assert world.uploads() == []


def test_a_landed_upload_logs_neither_the_activity_id_nor_the_page(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    script_none_then_ready(world)
    with caplog.at_level(logging.DEBUG):
        result = landed(upload(world))
    assert result.activity_page.endswith(str(NEW_ID))
    assert str(NEW_ID) not in caplog.text and result.activity_page not in caplog.text


def test_a_network_error_answering_the_upload_is_unconfirmed(world: World) -> None:
    script_list(world)
    script_upload(world, OutboundError("network"), created())
    assert upload(world) is P.UNCONFIRMED
    assert len(world.uploads()) == 1


# --- counting in the upload flow ---


def test_the_refresh_is_counted_against_the_publishing_ceiling_in_an_upload(
    store: Storage,
) -> None:
    # ann's share is one call: the publishing ceiling admits the refresh; then
    # the list is refused.
    w = build(store, limits=TIGHTER)
    connect(w, "ann", expires=NEAR)
    w.outbound.expect(
        "POST",
        TOKEN_URL,
        reply(200, {"access_token": "n", "refresh_token": "r", "expires_at": FAR}),
    )
    script_none_then_ready(w)
    assert upload(w) is P.RATE_LIMITED
    assert w.urls() == [TOKEN_URL]


def test_the_update_of_a_match_found_before_any_upload_is_counted(
    store: Storage,
) -> None:
    # ann's share is one call: it admits the listing but not the update
    w = build(store, limits=TIGHTER)
    connect(w, "ann")
    script_list(w, entry())
    script_update(w, reply(200, {}))
    script_upload(w, created())
    assert upload(w) is P.RATE_LIMITED
    assert w.urls() == [listing_url()]
    assert w.budget.spend("bea").allowed  # a refusal is not a Strava limit


# --- the time left after the reservation ---


def slow_reservation(w: World, seconds: float) -> None:
    real = w.budget.reserve_upload

    def slow(*args, **kwargs):  # type: ignore[no-untyped-def]
        result = real(*args, **kwargs)
        w.mono.now += seconds
        return result

    w.budget.reserve_upload = slow  # type: ignore[method-assign]


def test_the_upload_gets_the_time_left_after_the_reservation(world: World) -> None:
    slow_reservation(world, 20.0)  # 5 s of the 25 are left for the upload
    script_none_then_ready(world)
    assert landed(upload(world)).code is P.UPLOADED
    (call,) = world.uploads()
    assert call.timeout == pytest.approx(5.0)


def test_no_upload_is_made_when_the_reservation_used_the_rest_of_the_time(
    world: World,
) -> None:
    slow_reservation(world, 25.0)
    script_none_then_ready(world)
    assert upload(world) is P.UNAVAILABLE
    assert world.uploads() == []


# --- one clock read between the deadline check and the update ---


def test_the_update_after_a_failed_upload_reads_the_clock_once_after_its_check(
    world: World,
) -> None:
    failed_upload(world)
    script_list(world, entry())
    script_update(world, reply(200, {}))

    def arm(request: OutboundRequest) -> None:
        # the clock reads that follow the second listing: the 2nd one jumps past
        # the deadline
        if request.url == listing_url() and len(world.hits(listing_url())) == 1:
            world.mono.jumps[world.mono.reads + 2] = 30.0

    world.outbound.before_answer = arm
    assert landed(upload(world)).code is P.POSTED
    assert len(world.hits(UPDATE_URL)) == 1
