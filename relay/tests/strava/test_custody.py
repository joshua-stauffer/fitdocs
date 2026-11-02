"""Custody (task 3.5) on both backends, against the real connection tables.

Strava is the scripted outbound: a refresh or revoke nobody scripted raises
`UnscriptedCall`, and the recorded calls are the count of Strava requests.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

import pytest
from tests.conformance.state_support import Target, raw
from tests.strava.scripted_strava import ScriptedOutbound, UnscriptedCall, reply

from fitdocs_relay.crypto import EncryptionKey, Keyring
from fitdocs_relay.outbound import OutboundError
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.storage.interface import (
    NewConnection,
    NewPrincipal,
    NewToken,
    SealedTokens,
    Storage,
    StoredConnection,
)
from fitdocs_relay.strava.api import Grant, StravaApi
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import Limits, LinkSetting, StravaConfig
from fitdocs_relay.strava.custody import (
    LEASE_POLL_S,
    LEASE_S,
    LEASE_WAIT_S,
    REFRESH_MARGIN_S,
    REFRESH_TIMEOUT_S,
    Custody,
    Usable,
    account_key,
)

NOW = 1_700_000_000
OAUTH = "https://oauth.example/oauth"
TOKEN_URL = f"{OAUTH}/token"
REVOKE_URL = f"{OAUTH}/revoke"
HUGE = 1_000_000
LIMITS = Limits(HUGE, HUGE, HUGE, HUGE)
CONFIG = StravaConfig(
    client_id="4711",
    client_secret="client-secret",
    webhook_token="w" * 40,
    api_url="https://api.example/v3",
    oauth_url=OAUTH,
    web_url="https://web.example",
    limits=LIMITS,
    links=LinkSetting.ACTIVITY,
)
PEPPER = b"custody-test-pepper-0123456789abcdef"
ATHLETE = "90210123"

ACCESS = "access-tok-AAA"
REFRESH = "refresh-tok-RRR"
NEW_ACCESS = "access-tok-NEW"
NEW_REFRESH = "refresh-tok-NEW"
NEW_EXPIRY = NOW + 21600
NEAR = NOW + 100  # inside the margin

KEY_NEW = EncryptionKey("newk", bytes(range(32)))
KEY_OLD = EncryptionKey("oldk", bytes(range(32, 64)))
KEY_OTHER = EncryptionKey("othr", bytes(range(64, 96)))
CURRENT = Keyring((KEY_NEW, KEY_OLD))
OLD_ONLY = Keyring((KEY_OLD,))
UNKNOWN = Keyring((KEY_OTHER,))


def ctx(principal: str, field_name: str) -> str:
    return f"fitdocs-relay:v1:strava:{principal}:{field_name}"


def refreshed(**changes: object) -> object:
    body: dict[str, object] = {
        "access_token": NEW_ACCESS,
        "refresh_token": NEW_REFRESH,
        "expires_at": NEW_EXPIRY,
    }
    return body | changes


class Mono:
    """A monotonic clock only the test and `sleep` move."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@dataclass
class World:
    custody: Custody
    store: Storage
    outbound: ScriptedOutbound
    mono: Mono
    budget: StravaBudget

    def deadline(self, seconds: float = 30.0) -> float:
        return self.mono.now + seconds

    def get(self, principal: str = "ann") -> StoredConnection:
        found = self.store.get_connection(principal, "strava")
        assert found is not None
        return found

    def refresh_calls(self) -> int:
        return sum(1 for c in self.outbound.calls if c.request.url == TOKEN_URL)

    def revoke_calls(self) -> int:
        return sum(1 for c in self.outbound.calls if c.request.url == REVOKE_URL)


def build(
    store: Storage,
    *,
    limits: Limits = LIMITS,
    keyring: Keyring = CURRENT,
    sleep: Callable[[float], None] | None = None,
    mono: Mono | None = None,
) -> World:
    outbound = ScriptedOutbound()
    clock = mono or Mono()
    budget = StravaBudget(store, limits, clock=lambda: NOW)
    custody = Custody(
        store,
        keyring,
        StravaApi(CONFIG, outbound=outbound),
        budget,
        pepper=PEPPER,
        clock=lambda: NOW,
        monotonic=clock,
        sleep=sleep or clock.sleep,
    )
    return World(custody, store, outbound, clock, budget)


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    s = open_full_storage()
    for pid in ("ann", "bea", "cat", "dee", "eve", "fay", "gus"):
        s.create_principal(NewPrincipal(pid, None), now=1)
    return s


@pytest.fixture
def world(store: Storage) -> World:
    return build(store)


def connect(w: World, principal: str = "ann", *, expires: int = NEAR) -> None:
    w.custody.store_grant(
        principal, Grant(ACCESS, REFRESH, expires, f"athlete-of-{principal}")
    )


def put_raw(
    store: Storage,
    principal: str,
    keyring: Keyring,
    *,
    access: str = ACCESS,
    refresh: str | None = REFRESH,
    expires: int | None = NEAR,
    access_ctx: str | None = None,
    refresh_ctx: str | None = None,
) -> None:
    """A connection sealed by hand, to build rows storage-side."""
    store.put_connection(
        NewConnection(
            principal,
            "strava",
            f"acct-{principal}",
            SealedTokens(
                keyring.seal(access, context=access_ctx or ctx(principal, "access")),
                None
                if refresh is None
                else keyring.seal(
                    refresh, context=refresh_ctx or ctx(principal, "refresh")
                ),
                expires,
            ),
        ),
        now=1,
    )


def usable(result: object) -> str:
    assert isinstance(result, Usable), result
    return result.access


# --- store_grant ------------------------------------------------------------


def test_a_grant_is_sealed_under_the_connections_context_with_a_keyed_account_hash(
    database_target: Target, world: World
) -> None:
    world.custody.store_grant("ann", Grant(ACCESS, REFRESH, NEAR, ATHLETE))
    row = world.get()
    expected = hmac.new(
        PEPPER, b"fitdocs-relay-account-v1\0strava\0" + ATHLETE.encode(), hashlib.sha256
    ).hexdigest()
    assert row.account_key == expected
    assert row.account_key == account_key(PEPPER, "strava", ATHLETE)
    assert row.account_key != account_key(PEPPER, "strava", "90210124")
    assert row.account_key != account_key(PEPPER + b"x", "strava", ATHLETE)
    assert row.account_key != account_key(PEPPER, "other", ATHLETE)
    assert row.tokens.access_expires_at == NEAR
    assert row.generation == 1 and row.lease_id is None
    # sealed under the current (first) key, bound to principal, target and field
    assert row.tokens.refresh is not None
    assert CURRENT.key_id_of(row.tokens.access) == "newk"
    assert CURRENT.key_id_of(row.tokens.refresh) == "newk"
    assert CURRENT.open(row.tokens.access, context=ctx("ann", "access")) == ACCESS
    assert CURRENT.open(row.tokens.refresh, context=ctx("ann", "refresh")) == REFRESH
    assert CURRENT.open(row.tokens.access, context=ctx("ann", "refresh")) is None
    assert CURRENT.open(row.tokens.refresh, context=ctx("ann", "access")) is None
    assert CURRENT.open(row.tokens.access, context=ctx("bea", "access")) is None
    # nothing readable in the table: no athlete id, no token
    dump = repr(raw(database_target, "SELECT * FROM target_connections"))
    assert "ann" in dump  # the row is there
    for secret in (ATHLETE, ACCESS, REFRESH):
        assert secret not in dump


# --- access_token: when no refresh happens ---------------------------------


def test_the_documented_figures_are_these_literals() -> None:
    assert (REFRESH_MARGIN_S, LEASE_S, LEASE_WAIT_S, LEASE_POLL_S) == (
        300,
        60,
        5.0,
        0.25,
    )
    assert REFRESH_TIMEOUT_S == 8.0


def test_no_connection_is_not_connected(world: World) -> None:
    assert (
        world.custody.access_token("ann", deadline=world.deadline())
        is PublishCode.NOT_CONNECTED
    )
    assert world.outbound.calls == []


def test_a_token_valid_beyond_the_margin_is_returned_without_a_call(
    world: World,
) -> None:
    connect(world, expires=NOW + REFRESH_MARGIN_S + 1)
    result = world.custody.access_token("ann", deadline=world.deadline())
    assert usable(result) == ACCESS
    assert result == Usable("ann", ACCESS)
    assert world.outbound.calls == []
    assert world.get().generation == 1


def test_a_token_expiring_exactly_at_the_margin_is_refreshed(world: World) -> None:
    connect(world, expires=NOW + REFRESH_MARGIN_S)
    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    assert usable(world.custody.access_token("ann", deadline=world.deadline())) == (
        NEW_ACCESS
    )
    assert world.refresh_calls() == 1


def test_a_connection_with_no_access_expiry_is_used_with_no_refresh_call(
    world: World,
) -> None:
    put_raw(world.store, "ann", CURRENT, expires=None)
    assert world.get().tokens.access_expires_at is None
    assert usable(world.custody.access_token("ann", deadline=world.deadline())) == (
        ACCESS
    )
    assert world.outbound.calls == []
    assert world.get().generation == 1


# --- access_token: the refresh ----------------------------------------------


def test_a_refresh_swaps_the_tokens_and_the_next_request_uses_them(
    world: World,
) -> None:
    connect(world)
    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    deadline = world.deadline(2.0)
    assert usable(world.custody.access_token("ann", deadline=deadline)) == NEW_ACCESS

    (call,) = world.outbound.calls
    assert call.form["grant_type"] == "refresh_token"
    assert call.form["refresh_token"] == REFRESH
    assert call.timeout == 2.0  # the time left, shorter than the cap
    row = world.get()
    assert (row.generation, row.lease_id, row.lease_until) == (2, None, None)
    assert row.tokens.access_expires_at == NEW_EXPIRY
    assert row.tokens.refresh is not None
    assert CURRENT.open(row.tokens.access, context=ctx("ann", "access")) == NEW_ACCESS
    assert (
        CURRENT.open(row.tokens.refresh, context=ctx("ann", "refresh")) == NEW_REFRESH
    )
    # the new expiry is far: the next request makes no call
    assert usable(world.custody.access_token("ann", deadline=deadline)) == NEW_ACCESS
    assert len(world.outbound.calls) == 1


def test_a_refresh_timeout_is_capped_and_shorter_than_the_lease(world: World) -> None:
    assert REFRESH_TIMEOUT_S < LEASE_S
    connect(world)
    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    world.custody.access_token("ann", deadline=world.deadline(1000.0))
    assert world.outbound.calls[0].timeout == REFRESH_TIMEOUT_S


def test_the_refresh_is_made_under_a_lease_of_the_documented_length(
    world: World,
) -> None:
    connect(world)
    inner = world.outbound.__call__
    seen: list[tuple[str | None, int | None]] = []

    def look(request, timeout):  # type: ignore[no-untyped-def]
        held = world.get()
        seen.append((held.lease_id, held.lease_until))
        return inner(request, timeout)

    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    world.custody._api = StravaApi(CONFIG, outbound=look)  # noqa: SLF001
    world.custody.access_token("ann", deadline=world.deadline())
    ((lease_id, lease_until),) = seen
    assert lease_id is not None
    assert lease_until == NOW + LEASE_S


def test_a_refresh_spends_one_read_of_the_budget_or_the_links_share(
    database_target: Target, world: World
) -> None:
    connect(world)
    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]
    world.custody.access_token("ann", deadline=world.deadline())
    counts = dict(raw(database_target, "SELECT key, count FROM budget_counts"))
    assert counts["strava:read:900"] == 1
    assert counts["strava:p:ann:read:900"] == 1


def test_a_refresh_for_a_link_is_charged_against_the_links_headroom(
    store: Storage,
) -> None:
    # read_15m=5: the headroom leaves 4 for links, floor(5 * 0.8)
    w = build(store, limits=Limits(HUGE, HUGE, 5, HUGE))
    for principal in ("bea", "bea", "cat", "cat"):  # each holds 2, floor(5 x .5 x .8)
        assert w.budget.spend(principal, for_link=True).allowed
    connect(w)
    # the application window now holds 4: a link refresh is refused ...
    assert (
        w.custody.access_token("ann", deadline=w.deadline(), for_link=True)
        is PublishCode.RATE_LIMITED
    )
    # ... where a non-link one still fits
    w.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    assert usable(w.custody.access_token("ann", deadline=w.deadline())) == NEW_ACCESS


def test_a_deadline_already_passed_ends_before_any_spend_or_call(
    database_target: Target, world: World
) -> None:
    connect(world)
    result = world.custody.access_token("ann", deadline=world.mono.now)
    assert result is PublishCode.UNAVAILABLE
    assert world.outbound.calls == []
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]
    row = world.get()
    assert (row.generation, row.lease_id) == (1, None)


@pytest.mark.parametrize("status", [401, 403, 400])
def test_a_refused_refresh_deletes_the_connection_and_revokes_its_token(
    world: World, status: int
) -> None:
    connect(world)
    connect(world, "bea")
    assert world.store.issue_connection_token(
        "ann", "strava", NewToken("tok-ann", "v", None), now=NOW
    )
    assert world.store.issue_connection_token(
        "bea", "strava", NewToken("tok-bea", "v", None), now=NOW
    )
    world.outbound.expect("POST", TOKEN_URL, reply(status, {"message": "no"}))
    result = world.custody.access_token("ann", deadline=world.deadline())
    assert result is PublishCode.AUTH_REJECTED
    assert world.store.get_connection("ann", "strava") is None
    record = world.store.find_token("tok-ann")
    assert record is not None and record.revoked_at is not None
    # the neighbour is untouched
    assert world.store.get_connection("bea", "strava") is not None
    other = world.store.find_token("tok-bea")
    assert other is not None and other.revoked_at is None


@pytest.mark.parametrize(
    "answer",
    [
        reply(500),
        reply(503),
        reply(404),
        reply(200, b"not json"),
        OutboundError("timeout"),
    ],
    ids=["500", "503", "404", "unreadable", "network"],
)
def test_a_transient_refresh_failure_keeps_the_tokens_and_the_lease_is_released(
    world: World, answer: object
) -> None:
    connect(world)
    before = world.get()
    world.outbound.expect("POST", TOKEN_URL, answer)  # type: ignore[arg-type]
    assert (
        world.custody.access_token("ann", deadline=world.deadline())
        is PublishCode.UNAVAILABLE
    )
    assert world.get() == replace(before, lease_id=None, lease_until=None)
    assert world.get().lease_id is None
    # released: the next request can refresh at once
    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    assert usable(world.custody.access_token("ann", deadline=world.deadline())) == (
        NEW_ACCESS
    )


def test_a_limited_refresh_is_rate_limited_and_marks_the_windows_spent(
    database_target: Target, world: World
) -> None:
    connect(world)
    before = world.get()
    world.outbound.expect(
        "POST", TOKEN_URL, reply(429, headers={"X-RateLimit-Usage": "1,2000000"})
    )
    assert (
        world.custody.access_token("ann", deadline=world.deadline())
        is PublishCode.RATE_LIMITED
    )
    assert world.get() == before
    counts = dict(raw(database_target, "SELECT key, count FROM budget_counts"))
    assert counts["strava:all:900"] == HUGE and counts["strava:read:900"] == HUGE
    assert counts["strava:all:86400"] == HUGE  # the daily figure reached its limit


def test_a_limited_refresh_without_a_spent_day_marks_only_the_short_windows(
    database_target: Target, world: World
) -> None:
    connect(world)
    world.outbound.expect("POST", TOKEN_URL, reply(429))
    world.custody.access_token("ann", deadline=world.deadline())
    counts = dict(raw(database_target, "SELECT key, count FROM budget_counts"))
    assert counts["strava:all:900"] == HUGE
    assert counts["strava:all:86400"] == 1  # only the refresh's own spend


def test_a_budget_refusal_makes_no_call_and_gives_the_lease_back(
    store: Storage,
) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 0, HUGE))
    connect(w)
    before = w.get()
    assert (
        w.custody.access_token("ann", deadline=w.deadline()) is PublishCode.RATE_LIMITED
    )
    assert w.outbound.calls == []
    assert w.get() == before
    assert w.get().lease_id is None


def test_a_refresh_that_raises_gives_the_lease_back(world: World) -> None:
    connect(world)
    # nothing scripted: the outbound raises UnscriptedCall inside refresh
    with pytest.raises(UnscriptedCall):
        world.custody.access_token("ann", deadline=world.deadline())
    assert world.get().lease_id is None


class ExplodingBudget:
    def spend(self, principal_id: str, *, for_link: bool = False) -> object:
        raise RuntimeError("storage is down")


def test_a_budget_that_raises_gives_the_lease_back(world: World) -> None:
    connect(world)
    world.custody._budget = ExplodingBudget()  # type: ignore[assignment]  # noqa: SLF001
    with pytest.raises(RuntimeError, match="storage is down"):
        world.custody.access_token("ann", deadline=world.deadline())
    assert world.outbound.calls == []
    assert world.get().lease_id is None


def test_a_redirect_on_refresh_is_transient_and_keeps_the_connection(
    world: World,
) -> None:
    connect(world)
    before = world.get()
    world.outbound.expect(
        "POST", TOKEN_URL, reply(302, b"", {"location": "https://elsewhere.example/"})
    )
    result = world.custody.access_token("ann", deadline=world.deadline())
    assert result is PublishCode.UNAVAILABLE
    assert world.get() == replace(before, lease_id=None, lease_until=None)
    # not refused for good: the next request refreshes
    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    assert usable(world.custody.access_token("ann", deadline=world.deadline())) == (
        NEW_ACCESS
    )


def test_a_reconnection_during_the_refresh_is_not_deleted_by_a_refusal(
    world: World,
) -> None:
    connect(world)
    assert world.get().generation == 1
    inner = world.outbound.__call__

    def reconnect_then_refuse(request, timeout):  # type: ignore[no-untyped-def]
        # the athlete connects again while the refresh is in flight: a new
        # row at generation 1, the same generation the holder claimed
        world.custody.store_grant(
            "ann",
            Grant("fresh-access", "fresh-refresh", NEAR + 99999, "athlete-of-ann"),
        )
        fresh = world.get()
        assert (fresh.generation, fresh.lease_id) == (1, None)
        return inner(request, timeout)

    world.outbound.expect("POST", TOKEN_URL, reply(400, {"message": "bad"}))
    world.custody._api = StravaApi(CONFIG, outbound=reconnect_then_refuse)  # noqa: SLF001
    result = world.custody.access_token("ann", deadline=world.deadline())
    assert result is PublishCode.AUTH_REJECTED
    kept = world.get()
    assert CURRENT.open(kept.tokens.access, context=ctx("ann", "access")) == (
        "fresh-access"
    )


def test_a_connection_changed_during_the_refresh_is_not_deleted_by_a_refusal(
    world: World,
) -> None:
    connect(world)
    outbound = world.outbound
    inner = outbound.__call__

    def bump_then_refuse(request, timeout):  # type: ignore[no-untyped-def]
        held = world.get()
        assert held.lease_id is not None
        assert world.store.swap_tokens(
            "ann",
            "strava",
            generation=held.generation,
            lease_id=held.lease_id,
            tokens=held.tokens,
            now=NOW,
        )
        return inner(request, timeout)

    outbound.expect("POST", TOKEN_URL, reply(401))
    world.custody._api = StravaApi(CONFIG, outbound=bump_then_refuse)  # noqa: SLF001
    result = world.custody.access_token("ann", deadline=world.deadline())
    assert result is PublishCode.AUTH_REJECTED
    assert world.get().generation == 2  # the connection stands


def test_a_swap_refused_because_the_connection_changed_is_unavailable(
    world: World,
) -> None:
    connect(world)
    inner = world.outbound.__call__

    def bump_then_answer(request, timeout):  # type: ignore[no-untyped-def]
        held = world.get()
        assert held.lease_id is not None
        assert world.store.swap_tokens(
            "ann",
            "strava",
            generation=held.generation,
            lease_id=held.lease_id,
            tokens=SealedTokens(held.tokens.access, held.tokens.refresh, NOW + 5),
            now=NOW,
        )
        return inner(request, timeout)

    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    world.custody._api = StravaApi(CONFIG, outbound=bump_then_answer)  # noqa: SLF001
    result = world.custody.access_token("ann", deadline=world.deadline())
    assert result is PublishCode.UNAVAILABLE
    row = world.get()
    assert row.generation == 2
    assert row.tokens.access_expires_at == NOW + 5  # Strava's answer was not stored


def test_a_connection_deleted_during_the_refresh_is_not_connected(
    world: World,
) -> None:
    connect(world)
    inner = world.outbound.__call__

    def delete_then_answer(request, timeout):  # type: ignore[no-untyped-def]
        assert world.store.delete_connection("ann", "strava", generation=None, now=NOW)
        return inner(request, timeout)

    world.outbound.expect("POST", TOKEN_URL, reply(200, refreshed()))
    world.custody._api = StravaApi(CONFIG, outbound=delete_then_answer)  # noqa: SLF001
    assert (
        world.custody.access_token("ann", deadline=world.deadline())
        is PublishCode.NOT_CONNECTED
    )


# --- access_token: unreadable tokens ----------------------------------------


def test_tokens_no_key_opens_read_as_not_connected(world: World) -> None:
    put_raw(world.store, "ann", CURRENT, expires=NOW + 10_000)
    assert usable(world.custody.access_token("ann", deadline=world.deadline())) == (
        ACCESS
    )  # the same row, readable: the decoys below differ in one thing each
    decoys = {
        "bea": dict(keyring=UNKNOWN, expires=NOW + 10_000),
        "cat": dict(
            keyring=CURRENT, expires=NOW + 10_000, access_ctx=ctx("ann", "access")
        ),
        "dee": dict(
            keyring=CURRENT, expires=NOW + 10_000, access_ctx=ctx("dee", "refresh")
        ),
    }
    for principal, options in decoys.items():
        put_raw(world.store, principal, **options)  # type: ignore[arg-type]
        assert (
            world.custody.access_token(principal, deadline=world.deadline())
            is PublishCode.NOT_CONNECTED
        ), principal
    assert world.outbound.calls == []


def test_a_near_expiry_connection_with_an_unreadable_refresh_token_is_not_connected(
    world: World,
) -> None:
    put_raw(world.store, "ann", CURRENT, refresh_ctx=ctx("bea", "refresh"))
    put_raw(world.store, "bea", CURRENT, refresh=None)
    for principal in ("ann", "bea"):
        assert (
            world.custody.access_token(principal, deadline=world.deadline())
            is PublishCode.NOT_CONNECTED
        )
    assert world.outbound.calls == []


# --- access_token: waiting on another holder --------------------------------


def hold_lease(w: World, principal: str = "ann") -> StoredConnection:
    held = w.get(principal)
    assert w.store.claim_refresh(
        principal,
        "strava",
        generation=held.generation,
        lease_id="other-holder",
        lease_until=NOW + LEASE_S,
        now=NOW,
    )
    return w.get(principal)


def test_a_waiting_request_uses_the_tokens_the_holder_stored(world: World) -> None:
    connect(world)
    held = hold_lease(world)
    new_tokens = SealedTokens(
        CURRENT.seal(NEW_ACCESS, context=ctx("ann", "access")),
        CURRENT.seal(NEW_REFRESH, context=ctx("ann", "refresh")),
        NEW_EXPIRY,
    )

    def sleep(seconds: float) -> None:
        world.mono.sleep(seconds)
        if len(world.mono.slept) == 3:  # the holder finishes on the third poll
            assert world.store.swap_tokens(
                "ann",
                "strava",
                generation=held.generation,
                lease_id="other-holder",
                tokens=new_tokens,
                now=NOW,
            )

    waiting = build(world.store, sleep=sleep, mono=world.mono)
    result = waiting.custody.access_token("ann", deadline=waiting.deadline())
    assert usable(result) == NEW_ACCESS
    assert world.mono.slept == [LEASE_POLL_S] * 3
    assert world.outbound.calls == [] and waiting.outbound.calls == []


def test_a_wait_ends_unavailable_after_the_lease_wait(world: World) -> None:
    connect(world)
    hold_lease(world)
    start = world.mono.now
    result = world.custody.access_token("ann", deadline=world.deadline(100.0))
    assert result is PublishCode.UNAVAILABLE
    assert world.mono.slept == [LEASE_POLL_S] * int(LEASE_WAIT_S / LEASE_POLL_S)
    assert world.mono.now == start + LEASE_WAIT_S
    assert world.outbound.calls == []


def test_a_holder_that_gives_the_lease_up_without_a_swap_leaves_the_waiter_unavailable(
    world: World,
) -> None:
    connect(world)
    hold_lease(world)

    def sleep(seconds: float) -> None:
        world.mono.sleep(seconds)
        if len(world.mono.slept) == 3:  # the holder gives up on the third poll
            world.store.release_refresh("ann", "strava", lease_id="other-holder")

    waiting = build(world.store, sleep=sleep, mono=world.mono)
    result = waiting.custody.access_token("ann", deadline=waiting.deadline(100.0))
    assert result is PublishCode.UNAVAILABLE
    assert world.get().lease_id is None  # the lease really was given back
    assert len(world.mono.slept) == int(LEASE_WAIT_S / LEASE_POLL_S)
    assert world.outbound.calls == [] and waiting.outbound.calls == []


def test_a_wait_never_outlasts_the_deadline(world: World) -> None:
    connect(world)
    hold_lease(world)
    result = world.custody.access_token("ann", deadline=world.deadline(1.0))
    assert result is PublishCode.UNAVAILABLE
    assert world.mono.slept == [LEASE_POLL_S] * 4


def test_a_connection_deleted_while_waiting_is_not_connected(world: World) -> None:
    connect(world)
    hold_lease(world)

    def sleep(seconds: float) -> None:
        world.mono.sleep(seconds)
        world.store.delete_connection("ann", "strava", generation=None, now=NOW)

    waiting = build(world.store, sleep=sleep, mono=world.mono)
    assert (
        waiting.custody.access_token("ann", deadline=waiting.deadline())
        is PublishCode.NOT_CONNECTED
    )
    assert len(world.mono.slept) == 1


def test_concurrent_requests_on_an_expiring_token_cause_one_refresh_call(
    open_full_storage: Callable[[], Storage],
    store: Storage,
) -> None:
    threads = 6
    shared = store
    w = build(shared)
    connect(w)
    waiting = threading.Semaphore(0)
    started = threading.Barrier(threads)

    def sleep(seconds: float) -> None:
        waiting.release()
        time.sleep(0.005)

    inner = w.outbound

    def slow_refresh(request, timeout):  # type: ignore[no-untyped-def]
        # answer only once every other request is waiting on the lease
        for _ in range(threads - 1):
            assert waiting.acquire(timeout=20), "a request never waited"
        return inner(request, timeout)

    inner.expect("POST", TOKEN_URL, reply(200, refreshed()))
    custody = Custody(
        shared,
        CURRENT,
        StravaApi(CONFIG, outbound=slow_refresh),
        w.budget,
        pepper=PEPPER,
        clock=lambda: NOW,
        monotonic=time.monotonic,
        sleep=sleep,
    )
    results: list[object] = [None] * threads

    def run(i: int) -> None:
        started.wait()
        try:
            results[i] = custody.access_token("ann", deadline=time.monotonic() + 60.0)
        except BaseException as error:  # noqa: BLE001 - reported below
            results[i] = error

    pool = [
        threading.Thread(target=run, args=(i,), daemon=True) for i in range(threads)
    ]
    for t in pool:
        t.start()
    for t in pool:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in pool), "a request hung"
    assert results == [Usable("ann", NEW_ACCESS)] * threads
    assert len(inner.calls) == 1
    assert w.get().generation == 2


# --- withdraw ----------------------------------------------------------------


def test_withdraw_revokes_once_with_the_refresh_token_then_deletes(
    world: World,
) -> None:
    connect(world)
    connect(world, "bea")
    assert world.store.issue_connection_token(
        "ann", "strava", NewToken("tok-ann", "v", None), now=NOW
    )
    world.outbound.expect("POST", REVOKE_URL, reply(200, {}))
    world.custody.withdraw("ann")
    assert world.revoke_calls() == 1 and len(world.outbound.calls) == 1
    (call,) = world.outbound.calls
    assert call.form == {"token": REFRESH}
    assert call.timeout <= 10
    assert world.store.get_connection("ann", "strava") is None
    record = world.store.find_token("tok-ann")
    assert record is not None and record.revoked_at is not None
    assert world.store.get_connection("bea", "strava") is not None


@pytest.mark.parametrize(
    "answer",
    [reply(500), reply(401), reply(429), OutboundError("timeout")],
    ids=["500", "401", "429", "network"],
)
def test_withdraw_deletes_whatever_strava_answered(
    world: World, answer: object
) -> None:
    connect(world)
    world.outbound.expect("POST", REVOKE_URL, answer)  # type: ignore[arg-type]
    world.custody.withdraw("ann")
    assert world.revoke_calls() == 1
    assert world.store.get_connection("ann", "strava") is None


def test_withdraw_deletes_even_when_the_revoke_call_raises(world: World) -> None:
    connect(world)
    with pytest.raises(UnscriptedCall):
        world.custody.withdraw("ann")
    assert world.store.get_connection("ann", "strava") is None


def test_withdraw_makes_no_call_when_the_budget_refuses_and_still_deletes(
    store: Storage,
) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 0, HUGE))
    connect(w)
    w.custody.withdraw("ann")
    assert w.outbound.calls == []
    assert store.get_connection("ann", "strava") is None


def test_withdraws_revoke_is_not_charged_against_the_links_headroom(
    store: Storage,
) -> None:
    w = build(store, limits=Limits(HUGE, HUGE, 5, HUGE))
    for principal in ("bea", "bea", "cat", "cat"):
        assert w.budget.spend(principal, for_link=True).allowed
    connect(w)
    # the links' headroom is used up, a plain read still fits
    assert not w.budget.spend("ann", for_link=True).allowed
    w.outbound.expect("POST", REVOKE_URL, reply(200, {}))
    w.custody.withdraw("ann")
    assert w.revoke_calls() == 1
    assert store.get_connection("ann", "strava") is None


def test_withdraw_of_unreadable_tokens_makes_no_call_and_deletes(
    world: World,
) -> None:
    put_raw(world.store, "ann", UNKNOWN)
    put_raw(world.store, "bea", CURRENT, refresh=None)
    world.custody.withdraw("ann")
    world.custody.withdraw("bea")
    assert world.outbound.calls == []
    assert world.store.get_connection("ann", "strava") is None
    assert world.store.get_connection("bea", "strava") is None


def test_withdraw_without_a_connection_calls_nothing_and_changes_nothing(
    world: World,
) -> None:
    connect(world, "bea")
    world.custody.withdraw("ann")
    assert world.outbound.calls == []
    assert world.store.get_connection("bea", "strava") is not None


# --- forget_account ---------------------------------------------------------


def test_forgetting_an_account_deletes_exactly_its_connection(world: World) -> None:
    world.custody.store_grant("ann", Grant(ACCESS, REFRESH, NEAR, ATHLETE))
    world.custody.store_grant("bea", Grant(ACCESS, REFRESH, NEAR, "5551"))
    assert world.store.issue_connection_token(
        "ann", "strava", NewToken("tok-ann", "v", None), now=NOW
    )
    assert world.custody.forget_account("77") is False
    assert world.store.get_connection("ann", "strava") is not None
    assert world.custody.forget_account(ATHLETE) is True
    assert world.store.get_connection("ann", "strava") is None
    assert world.store.get_connection("bea", "strava") is not None
    record = world.store.find_token("tok-ann")
    assert record is not None and record.revoked_at is not None
    assert world.custody.forget_account(ATHLETE) is False
    assert world.outbound.calls == []


# --- reencrypt_all ------------------------------------------------------------


def snapshot(w: World, principal: str) -> StoredConnection:
    return w.get(principal)


def test_reencryption_counts_an_unreadable_row_and_leaves_it_unchanged(
    world: World,
) -> None:
    # ann: both fields under the old key; bea: already current;
    # cat: only the refresh under the old key; dee: no key opens the access;
    # eve: the refresh is bound to another principal; fay: a live lease holds it.
    put_raw(world.store, "ann", OLD_ONLY, expires=NOW + 7)
    put_raw(world.store, "bea", CURRENT)
    cat_access = CURRENT.seal(ACCESS, context=ctx("cat", "access"))
    world.store.put_connection(
        NewConnection(
            "cat",
            "strava",
            "acct-cat",
            SealedTokens(
                cat_access, OLD_ONLY.seal(REFRESH, context=ctx("cat", "refresh")), None
            ),
        ),
        now=1,
    )
    put_raw(world.store, "dee", UNKNOWN)
    put_raw(world.store, "eve", OLD_ONLY, refresh_ctx=ctx("ann", "refresh"))
    put_raw(world.store, "fay", OLD_ONLY)
    hold_lease(world, "fay")
    # gus: only the access token under the old key
    world.store.put_connection(
        NewConnection(
            "gus",
            "strava",
            "acct-gus",
            SealedTokens(
                OLD_ONLY.seal(ACCESS, context=ctx("gus", "access")),
                CURRENT.seal(REFRESH, context=ctx("gus", "refresh")),
                NEAR,
            ),
        ),
        now=1,
    )
    names = ("ann", "bea", "cat", "dee", "eve", "fay", "gus")
    before = {p: snapshot(world, p) for p in names}

    start = world.mono.now
    assert world.custody.reencrypt_all() == (3, 2)  # fay is in neither number
    # the leased row was retried for LEASE_S, poll by poll, and then left
    assert world.mono.slept == [LEASE_POLL_S] * int(LEASE_S / LEASE_POLL_S)
    assert world.mono.now == start + LEASE_S

    for principal in ("ann", "cat", "gus"):
        row = world.get(principal)
        assert row.tokens.refresh is not None
        assert CURRENT.key_id_of(row.tokens.access) == "newk"
        assert CURRENT.key_id_of(row.tokens.refresh) == "newk"
        assert CURRENT.open(row.tokens.access, context=ctx(principal, "access")) == (
            ACCESS
        )
        assert CURRENT.open(row.tokens.refresh, context=ctx(principal, "refresh")) == (
            REFRESH
        )
        assert row.generation == before[principal].generation + 1
        assert (
            row.tokens.access_expires_at == before[principal].tokens.access_expires_at
        )
        assert row.lease_id is None
    assert world.get("ann").tokens.access_expires_at == NOW + 7
    assert world.get("cat").tokens.access_expires_at is None
    for principal in ("bea", "dee", "eve", "fay"):
        assert world.get(principal) == before[principal], principal
    assert world.outbound.calls == []

    # the held row is swapped once its lease is given back, and the others stay
    world.store.release_refresh("fay", "strava", lease_id="other-holder")
    world.mono.slept.clear()
    assert world.custody.reencrypt_all() == (1, 2)
    assert world.mono.slept == []  # nothing left to wait for
    fay = world.get("fay")
    assert CURRENT.key_id_of(fay.tokens.access) == "newk"
    assert fay.tokens.refresh is not None
    assert CURRENT.key_id_of(fay.tokens.refresh) == "newk"
    assert world.get("dee") == before["dee"] and world.get("eve") == before["eve"]
    assert world.custody.reencrypt_all() == (0, 2)


def test_reencryption_of_nothing_is_zero_and_zero(world: World) -> None:
    assert world.custody.reencrypt_all() == (0, 0)


def test_a_reencryption_waits_for_a_lease_and_swaps_once_it_is_given_back(
    world: World,
) -> None:
    put_raw(world.store, "ann", OLD_ONLY)
    hold_lease(world)

    def sleep(seconds: float) -> None:
        world.mono.sleep(seconds)
        if len(world.mono.slept) == 3:
            world.store.release_refresh("ann", "strava", lease_id="other-holder")

    again = build(world.store, sleep=sleep, mono=world.mono)
    assert again.custody.reencrypt_all() == (1, 0)
    assert world.mono.slept == [LEASE_POLL_S] * 3
    row = world.get()
    assert row.tokens.refresh is not None
    assert CURRENT.key_id_of(row.tokens.access) == "newk"
    assert CURRENT.key_id_of(row.tokens.refresh) == "newk"


def test_a_row_the_lease_holder_seals_under_the_current_key_is_counted_in_neither(
    world: World,
) -> None:
    put_raw(world.store, "ann", OLD_ONLY)
    held = hold_lease(world)
    sealed = SealedTokens(
        CURRENT.seal(NEW_ACCESS, context=ctx("ann", "access")),
        CURRENT.seal(NEW_REFRESH, context=ctx("ann", "refresh")),
        NEW_EXPIRY,
    )

    def sleep(seconds: float) -> None:
        world.mono.sleep(seconds)
        assert world.store.swap_tokens(
            "ann",
            "strava",
            generation=held.generation,
            lease_id="other-holder",
            tokens=sealed,
            now=NOW,
        )

    again = build(world.store, sleep=sleep, mono=world.mono)
    assert again.custody.reencrypt_all() == (0, 0)
    assert world.get().tokens == sealed  # nobody re-sealed it a second time
    assert world.get().generation == held.generation + 1


def test_a_row_deleted_while_the_reencryption_waits_is_counted_in_neither(
    world: World,
) -> None:
    put_raw(world.store, "ann", OLD_ONLY)
    hold_lease(world)

    def sleep(seconds: float) -> None:
        world.mono.sleep(seconds)
        assert world.store.delete_connection("ann", "strava", generation=None, now=NOW)

    again = build(world.store, sleep=sleep, mono=world.mono)
    assert again.custody.reencrypt_all() == (0, 0)
    assert world.mono.slept == [LEASE_POLL_S]  # polling stopped after that sleep
    assert world.store.get_connection("ann", "strava") is None


def test_a_row_made_current_by_someone_else_is_not_counted_unreadable(
    world: World,
) -> None:
    put_raw(world.store, "ann", OLD_ONLY)
    stale = world.store.list_connections("strava")
    assert [c.principal_id for c in stale] == ["ann"]
    assert not world.custody._current(stale[0])  # noqa: SLF001
    # another process re-encrypts it between the listing and our swap
    assert world.store.swap_tokens(
        "ann",
        "strava",
        generation=stale[0].generation,
        lease_id=None,
        tokens=SealedTokens(
            CURRENT.seal(ACCESS, context=ctx("ann", "access")),
            CURRENT.seal(REFRESH, context=ctx("ann", "refresh")),
            NEAR,
        ),
        now=NOW,
    )
    world.store.list_connections = lambda target: stale  # type: ignore[method-assign]  # noqa: ARG005
    assert world.custody.reencrypt_all() == (0, 0)
    assert world.mono.slept == []
