"""ConnectFlow (task 3.9) on both backends, against the real record, token and
connection tables. Strava is the scripted outbound: the token endpoint is the
only call a connect makes, and a call nobody scripted raises.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlsplit

import pytest
from tests.strava.scripted_strava import ScriptedOutbound, reply

from fitdocs_relay.crypto import EncryptionKey, Keyring
from fitdocs_relay.identity import PreparedToken, TokenService
from fitdocs_relay.outbound import OutboundError, OutboundRequest, OutboundResponse
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import USER_CODE_RE
from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    Storage,
    UnknownPrincipal,
)
from fitdocs_relay.strava.api import StravaApi
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import Limits, LinkSetting, StravaConfig
from fitdocs_relay.strava.connect import (
    CLAIM_COOKIE,
    CONNECT_EXPIRES_IN_S,
    CONNECT_INTERVAL_S,
    CONNECTION_TOKEN_LABEL,
    RECORD_NAMESPACE,
    CallbackOutcome,
    ConnectFlow,
    PageOutcome,
    PollGranted,
    PollOutcome,
    ShowConsent,
    Started,
)
from fitdocs_relay.strava.custody import Custody, Usable

NOW = 1_700_000_000
OAUTH = "https://oauth.example/oauth"
TOKEN_URL = f"{OAUTH}/token"
PUBLIC = "https://relay.example"
HUGE = 1_000_000
CONFIG = StravaConfig(
    client_id="4711",
    client_secret="client-secret",
    webhook_token="w" * 40,
    api_url="https://api.example/v3",
    oauth_url=OAUTH,
    web_url="https://web.example",
    limits=Limits(HUGE, HUGE, HUGE, HUGE),
    links=LinkSetting.ACTIVITY,
)
PEPPER = b"connect-test-pepper-0123456789abcdefghijklmnop"
FULL = "read,activity:read_all,activity:write"
EXPIRES = NOW + 21600


def grant_body(access: str, athlete: int = 90210) -> dict[str, object]:
    return {
        "access_token": access,
        "refresh_token": "refresh-of-" + access,
        "expires_at": EXPIRES,
        "athlete": {"id": athlete},
    }


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> int:
        return self.now


class ScriptedTokens(TokenService):
    """A token service whose first `prepared` results are scripted."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.queue: list[PreparedToken] = []

    def prepare(self, *, label: str | None) -> PreparedToken:
        if self.queue:
            return self.queue.pop(0)
        return super().prepare(label=label)


@dataclass
class World:
    flow: ConnectFlow
    store: Storage
    outbound: ScriptedOutbound
    tokens: ScriptedTokens
    custody: Custody
    budget: StravaBudget
    clock: Clock

    def record(self, key: str, *, at: int | None = None) -> bytes | None:
        return self.store.get_record(
            namespace=RECORD_NAMESPACE, key=key, now=at if at is not None else NOW
        )

    def token_calls(self) -> int:
        return sum(1 for c in self.outbound.calls if c.request.url == TOKEN_URL)

    def script(self, *answers: object) -> None:
        self.outbound.expect("POST", TOKEN_URL, *answers)  # type: ignore[arg-type]

    def browser(self, started: Started, cookie: str | None = None) -> Browser:
        return Browser(self, started, cookie)

    def connection_tokens(self, principal: str) -> list[tuple[str, int | None]]:
        return [
            (t.token_id, t.revoked_at)
            for t in self.store.list_tokens(principal)
            if t.label == CONNECTION_TOKEN_LABEL
        ]


class _Own:
    """Marks an argument the browser fills in itself."""


OWN = _Own()


class Browser:
    """One browser: opens the page, keeps the claim cookie, calls back."""

    def __init__(self, world: World, started: Started, cookie: str | None) -> None:
        self.w = world
        self.started = started
        self.cookie = cookie
        self.state: str | None = None
        self.url: str | None = None

    def open(self) -> ShowConsent | PageOutcome:
        shown = self.w.flow.page(self.started.user_code, self.cookie)
        if isinstance(shown, ShowConsent):
            if shown.set_cookie is not None:
                self.cookie = cookie_value(shown.set_cookie)
            self.url = shown.authorize_url
            self.state = parse_qs(urlsplit(shown.authorize_url).query)["state"][0]
        return shown

    def call_back(
        self,
        *,
        scope: str | None = FULL,
        code: str | None = "the-code",
        error: str | None = None,
        state: str | None | _Own = OWN,
        cookie: str | None | _Own = OWN,
    ) -> CallbackOutcome:
        return self.w.flow.callback(
            state=self.state if isinstance(state, _Own) else state,
            code=code,
            scope=scope,
            error=error,
            cookie=self.cookie if isinstance(cookie, _Own) else cookie,
        )


def cookie_value(set_cookie: str) -> str:
    head = set_cookie.split(";")[0]
    name, _, value = head.partition("=")
    assert name == CLAIM_COOKIE
    return value


def build(
    store: Storage,
    *,
    limits: Limits | None = None,
    outbound: ScriptedOutbound | None = None,
    public_url: str = PUBLIC,
    codes: Callable[[], str] | None = None,
) -> World:
    clock = Clock()
    outbound = ScriptedOutbound() if outbound is None else outbound
    config = CONFIG if limits is None else _with_limits(limits)
    budget = StravaBudget(store, config.limits, clock=clock)
    custody = Custody(
        store,
        _keyring(),
        StravaApi(config, outbound=outbound),
        budget,
        pepper=PEPPER,
        clock=clock,
        monotonic=lambda: 0.0,
        sleep=lambda _s: None,
    )
    tokens = ScriptedTokens(store, pepper=PEPPER, clock=clock)
    flow = ConnectFlow(
        store,
        tokens,
        custody,
        StravaApi(config, outbound=outbound),
        budget,
        public_url=public_url,
        clock=clock,
        user_codes=codes,
    )
    return World(flow, store, outbound, tokens, custody, budget, clock)


def _with_limits(limits: Limits) -> StravaConfig:
    return replace(CONFIG, limits=limits)


def _keyring() -> Keyring:
    return Keyring((EncryptionKey("conn", bytes(range(32))),))


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    s = open_full_storage()
    for pid in ("ann", "bea"):
        s.create_principal(NewPrincipal(pid, None), now=1)
    return s


@pytest.fixture
def world(store: Storage) -> World:
    return build(store)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def connected(w: World, principal: str, access: str, athlete: int = 90210) -> Started:
    """Run one whole connect up to (and not including) the poll."""
    started = w.flow.start(principal)
    b = w.browser(started)
    assert isinstance(b.open(), ShowConsent)
    w.script(reply(200, grant_body(access, athlete)))
    assert b.call_back() is CallbackOutcome.GRANTED
    return started


# --- start (3.1) ----------------------------------------------------------------


def test_start_answers_with_a_session_that_lives_at_most_ten_minutes(
    world: World,
) -> None:
    started = world.flow.start("ann")
    assert re.fullmatch(USER_CODE_RE, started.user_code)
    assert len(started.poll_secret) == 43
    assert started.interval_s == CONNECT_INTERVAL_S == 3
    assert started.expires_in_s == CONNECT_EXPIRES_IN_S == 600
    assert started.poll_secret not in repr(started)
    key = f"session:{started.user_code}"
    assert world.record(key, at=NOW + 599) is not None
    assert world.record(key, at=NOW + 600) is None


def test_every_session_record_expires_with_the_session(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.script(reply(200, grant_body("A1")))
    b.call_back()
    code = started.user_code
    keys = [
        f"session:{code}",
        f"claim:{code}",
        f"poll:{sha(started.poll_secret)}",
        f"result:{sha(started.poll_secret)}",
    ]
    for key in keys:
        assert world.record(key, at=NOW + 599) is not None, key
        assert world.record(key, at=NOW + 600) is None, key


def test_the_unclaimed_and_state_records_expire_with_the_session(
    world: World,
) -> None:
    started = world.flow.start("ann")
    raw = world.record(f"session:{started.user_code}")
    assert raw is not None
    state_key = f"state:{sha(json.loads(raw)['state'])}"
    for key in (f"unclaimed:{started.user_code}", state_key):
        assert world.record(key, at=NOW + 599) is not None, key
        assert world.record(key, at=NOW + 600) is None, key


def test_the_session_holds_hashes_not_the_poll_secret(world: World) -> None:
    started = world.flow.start("ann")
    raw = world.record(f"session:{started.user_code}")
    assert raw is not None
    session = json.loads(raw)
    assert session["principal"] == "ann"
    assert session["target"] == "strava"
    assert session["poll"] == sha(started.poll_secret)
    assert started.poll_secret.encode() not in raw
    assert world.record(f"poll:{sha(started.poll_secret)}") is not None
    assert world.record(f"unclaimed:{started.user_code}") is not None
    state_hash = sha(session["state"])
    assert world.record(f"state:{state_hash}") is not None


def test_each_session_has_its_own_code_secret_and_state(world: World) -> None:
    sessions = [world.flow.start("ann") for _ in range(5)]
    assert len({s.user_code for s in sessions}) == 5
    assert len({s.poll_secret for s in sessions}) == 5
    states = []
    for s in sessions:
        raw = world.record(f"session:{s.user_code}")
        assert raw is not None
        state = json.loads(raw)["state"]
        assert len(state) == 43
        states.append(state)
    assert len(set(states)) == 5


def test_a_code_in_use_by_a_live_session_is_not_reused(store: Storage) -> None:
    queue = ["BCDF-GHJK", "BCDF-GHJK", "LMNP-QRST"]
    w = build(store, codes=lambda: queue.pop(0))
    first = w.flow.start("ann")
    second = w.flow.start("bea")
    assert (first.user_code, second.user_code) == ("BCDF-GHJK", "LMNP-QRST")
    raw = w.record("session:BCDF-GHJK")
    assert raw is not None
    assert json.loads(raw)["principal"] == "ann"
    assert w.flow.poll("ann", first.poll_secret) is PollOutcome.PENDING
    assert w.flow.poll("bea", second.poll_secret) is PollOutcome.PENDING


def test_an_expired_code_is_free_again(store: Storage) -> None:
    queue = ["BCDF-GHJK", "BCDF-GHJK"]
    w = build(store, codes=lambda: queue.pop(0))
    w.flow.start("ann")
    w.clock.now = NOW + 600
    again = w.flow.start("bea")
    assert again.user_code == "BCDF-GHJK"
    raw = w.record("session:BCDF-GHJK", at=NOW + 600)
    assert raw is not None
    assert json.loads(raw)["principal"] == "bea"


# --- the page and its claim (3.2, 3.4, 3.5) -------------------------------------


@pytest.mark.parametrize(
    "code", [None, "", "bcdf-ghjk", "BCDF-GHJ", "AEIO-AEIO", "BCDF-GHJK-X"]
)
def test_a_malformed_code_is_invalid(world: World, code: str | None) -> None:
    started = world.flow.start("ann")
    assert world.flow.page(code, None) is PageOutcome.INVALID
    assert world.record(f"unclaimed:{started.user_code}") is not None


def test_an_unknown_code_is_invalid_and_changes_nothing(world: World) -> None:
    started = world.flow.start("ann")
    other = "BCDF-GHJK" if started.user_code != "BCDF-GHJK" else "LMNP-QRST"
    assert world.flow.page(other, None) is PageOutcome.INVALID
    assert world.record(f"claim:{other}") is None
    assert world.record(f"unclaimed:{started.user_code}") is not None
    assert world.record(f"claim:{started.user_code}") is None


def test_an_expired_code_is_invalid(world: World) -> None:
    started = world.flow.start("ann")
    world.clock.now = NOW + 600
    assert world.flow.page(started.user_code, None) is PageOutcome.INVALID


def test_the_first_browser_claims_and_gets_the_authorize_link(world: World) -> None:
    started = world.flow.start("ann")
    shown = world.flow.page(started.user_code, None)
    assert isinstance(shown, ShowConsent)
    assert shown.user_code == started.user_code
    assert shown.set_cookie is not None
    cookie = cookie_value(shown.set_cookie)
    assert len(cookie) == 43
    assert cookie not in repr(shown)
    url = urlsplit(shown.authorize_url)
    query = parse_qs(url.query)
    assert f"{url.scheme}://{url.netloc}{url.path}" == f"{OAUTH}/authorize"
    assert query["redirect_uri"] == [f"{PUBLIC}/strava/callback"]
    assert query["scope"] == ["activity:read_all,activity:write"]
    raw = world.record(f"session:{started.user_code}")
    assert raw is not None
    assert query["state"] == [json.loads(raw)["state"]]
    claim = world.record(f"claim:{started.user_code}")
    assert claim == sha(cookie).encode()
    assert world.record(f"unclaimed:{started.user_code}") is None


def test_the_claim_cookie_is_bounded_to_the_session(world: World) -> None:
    started = world.flow.start("ann")
    world.clock.now = NOW + 100
    shown = world.flow.page(started.user_code, None)
    assert isinstance(shown, ShowConsent) and shown.set_cookie is not None
    attributes = [a.strip() for a in shown.set_cookie.split(";")[1:]]
    assert "Max-Age=500" in attributes
    assert "HttpOnly" in attributes
    assert "SameSite=Lax" in attributes
    assert "Path=/" in attributes
    assert "Secure" in attributes


def test_the_cookie_is_not_secure_over_plain_loopback(store: Storage) -> None:
    w = build(store, public_url="http://127.0.0.1:8080")
    shown = w.flow.page(w.flow.start("ann").user_code, None)
    assert isinstance(shown, ShowConsent) and shown.set_cookie is not None
    assert "Secure" not in shown.set_cookie
    url = parse_qs(urlsplit(shown.authorize_url).query)
    assert url["redirect_uri"] == ["http://127.0.0.1:8080/strava/callback"]


def test_a_second_browser_is_refused_and_the_first_keeps_the_session(
    world: World,
) -> None:
    started = world.flow.start("ann")
    first = world.browser(started)
    assert isinstance(first.open(), ShowConsent)
    for presented in (None, "", "not-the-cookie", sha(first.cookie or "")):
        assert world.flow.page(started.user_code, presented) is PageOutcome.IN_USE
    again = first.open()
    assert isinstance(again, ShowConsent)
    assert again.set_cookie is None
    assert again.authorize_url == first.url


def test_one_sessions_cookie_does_not_open_another_session(world: World) -> None:
    one = world.browser(world.flow.start("ann"))
    two = world.browser(world.flow.start("bea"))
    assert isinstance(one.open(), ShowConsent)
    assert isinstance(two.open(), ShowConsent)
    assert one.cookie != two.cookie
    assert world.flow.page(two.started.user_code, one.cookie) is PageOutcome.IN_USE
    assert world.flow.page(one.started.user_code, two.cookie) is PageOutcome.IN_USE


def test_a_page_after_the_session_is_used_is_invalid(world: World) -> None:
    started = connected(world, "ann", "A1")
    assert world.flow.poll("ann", started.poll_secret).__class__ is PollGranted
    assert world.flow.page(started.user_code, None) is PageOutcome.INVALID


# --- the callback (3.6, 3.7) ----------------------------------------------------


def test_the_callback_exchanges_once_and_stores_the_grant(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.PENDING
    world.script(reply(200, grant_body("A1")))
    assert b.call_back(code="the-code") is CallbackOutcome.GRANTED
    assert world.token_calls() == 1
    call = world.outbound.calls[0]
    assert call.request.method == "POST"
    assert call.form["code"] == "the-code"
    assert 0 < call.timeout <= 10
    stored = world.store.get_connection("ann", "strava")
    assert stored is not None
    assert world.store.get_connection("bea", "strava") is None
    usable = world.custody.access_token("ann", deadline=1e9)
    assert usable == Usable("ann", "A1")


def test_the_state_is_single_use(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.script(reply(200, grant_body("A1")))
    assert b.call_back() is CallbackOutcome.GRANTED
    assert b.call_back() is CallbackOutcome.INVALID
    assert world.token_calls() == 1


def test_a_callback_from_another_browser_leaves_the_state_usable(
    world: World,
) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    for cookie in (None, "", "another-browser"):
        assert b.call_back(cookie=cookie) is CallbackOutcome.INVALID
    assert world.token_calls() == 0
    assert world.store.get_connection("ann", "strava") is None
    world.script(reply(200, grant_body("A1")))
    assert b.call_back() is CallbackOutcome.GRANTED


def test_a_callback_before_any_browser_claimed_is_invalid_and_keeps_the_state(
    world: World,
) -> None:
    started = world.flow.start("ann")
    raw = world.record(f"session:{started.user_code}")
    assert raw is not None
    state = json.loads(raw)["state"]
    assert (
        world.flow.callback(state=state, code="c", scope=FULL, error=None, cookie="x")
        is CallbackOutcome.INVALID
    )
    assert world.record(f"state:{sha(state)}") is not None
    b = world.browser(started)
    b.open()
    world.script(reply(200, grant_body("A1")))
    assert b.call_back() is CallbackOutcome.GRANTED


@pytest.mark.parametrize("state", [None, "", "no-such-state"])
def test_an_unknown_state_is_invalid(world: World, state: str | None) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    assert b.call_back(state=state) is CallbackOutcome.INVALID
    assert world.token_calls() == 0
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.PENDING


def test_a_callback_after_the_session_expired_is_invalid(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.clock.now = NOW + 600
    assert b.call_back() is CallbackOutcome.INVALID
    assert world.token_calls() == 0


@pytest.mark.parametrize(
    "scope",
    [
        "read,activity:read_all",
        "read,activity:write",
        "read",
        "",
        None,
        "activity:read_all,activity:writeX",
        "activity:read_allX,activity:write",
        "activity:read_all activity:write",
    ],
)
def test_a_narrowed_scope_is_refused_with_no_exchange_and_no_token_stored(
    world: World, scope: str | None
) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    assert b.call_back(scope=scope) is CallbackOutcome.REFUSED
    assert world.token_calls() == 0
    assert world.store.get_connection("ann", "strava") is None
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED
    assert world.connection_tokens("ann") == []


def test_both_scopes_in_any_order_are_enough(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.script(reply(200, grant_body("A1")))
    outcome = b.call_back(scope="activity:write,activity:read_all")
    assert outcome is CallbackOutcome.GRANTED


def test_a_decline_is_refused_even_with_a_code_and_full_scope(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    assert b.call_back(error="access_denied") is CallbackOutcome.REFUSED
    assert world.token_calls() == 0
    assert world.store.get_connection("ann", "strava") is None
    assert b.call_back() is CallbackOutcome.INVALID  # the state was spent
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED


def test_a_callback_without_a_code_is_refused_without_an_exchange(
    world: World,
) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    assert b.call_back(code=None) is CallbackOutcome.REFUSED
    assert world.token_calls() == 0
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED


@pytest.mark.parametrize(
    "answer",
    [
        reply(400, {"message": "Bad Request"}),
        reply(500),
        reply(302, b"", {"location": "https://elsewhere.example"}),
        reply(200, {"access_token": "only"}),
        OutboundError("network"),
    ],
    ids=["400", "500", "302", "unreadable", "network"],
)
def test_a_failed_exchange_is_refused_once_and_stores_nothing(
    world: World, answer: object
) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.script(answer)
    assert b.call_back() is CallbackOutcome.REFUSED
    assert world.token_calls() == 1
    assert world.store.get_connection("ann", "strava") is None
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED


def test_the_exchange_spends_the_budget_once(store: Storage) -> None:
    # Only the read windows are tight: a spend of another kind, or one made
    # for a link, would not touch them and the following read would pass.
    w = build(store, limits=Limits(HUGE, HUGE, 1, 1))
    started = w.flow.start("ann")
    b = w.browser(started)
    b.open()
    w.script(reply(200, grant_body("A1")))
    assert b.call_back() is CallbackOutcome.GRANTED
    assert w.budget.spend("ann").allowed is False


def test_a_refused_budget_refuses_the_callback_with_no_exchange(
    store: Storage,
) -> None:
    w = build(store, limits=Limits(1, 1, 1, 1))
    assert w.budget.spend("ann").allowed is True
    started = w.flow.start("ann")
    b = w.browser(started)
    b.open()
    assert b.call_back() is CallbackOutcome.REFUSED
    assert w.token_calls() == 0
    assert w.store.get_connection("ann", "strava") is None
    assert w.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED


class HookedOutbound(ScriptedOutbound):
    """Runs `before_first` just before the first request is answered."""

    def __init__(self) -> None:
        super().__init__()
        self.before_first: Callable[[], None] | None = None

    def __call__(self, request: OutboundRequest, timeout: float) -> OutboundResponse:
        hook, self.before_first = self.before_first, None
        if hook is not None:
            hook()
        return super().__call__(request, timeout)


def test_a_callback_made_during_the_exchange_finds_the_state_taken(
    store: Storage,
) -> None:
    outbound = HookedOutbound()
    w = build(store, outbound=outbound)
    started = w.flow.start("ann")
    b = w.browser(started)
    b.open()
    w.script(reply(200, grant_body("A1")), reply(200, grant_body("A2")))
    inner: list[CallbackOutcome] = []
    outbound.before_first = lambda: inner.append(b.call_back())
    assert b.call_back() is CallbackOutcome.GRANTED
    assert inner == [CallbackOutcome.INVALID]
    assert w.token_calls() == 1


def test_two_simultaneous_callbacks_exchange_once(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.script(reply(200, grant_body("A1")))
    barrier = threading.Barrier(2)
    outcomes: list[CallbackOutcome] = []

    def go() -> None:
        barrier.wait()
        outcomes.append(b.call_back())

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(o.value for o in outcomes) == ["granted", "invalid"]
    assert world.token_calls() == 1


@pytest.mark.parametrize("daily", [False, True], ids=["short", "daily"])
def test_a_limited_exchange_marks_the_windows_strava_says_are_spent(
    store: Storage, daily: bool
) -> None:
    w = build(store)
    started = w.flow.start("ann")
    b = w.browser(started)
    b.open()
    usage = "1,2000000" if daily else "1,1"
    w.script(reply(429, headers={"X-RateLimit-Usage": usage}))
    assert b.call_back() is CallbackOutcome.REFUSED
    assert w.budget.spend("ann").allowed is False  # the short windows
    w.clock.now += 901
    assert w.budget.spend("ann").allowed is (not daily)  # the day, only if spent


def test_a_grant_that_cannot_be_stored_leaves_the_poll_a_refusal(
    store: Storage,
) -> None:
    outbound = HookedOutbound()
    world = build(store, outbound=outbound)
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    world.script(reply(200, grant_body("A1")))
    # the principal goes while Strava is answering, so only the store fails
    outbound.before_first = lambda: (world.store.delete_principal("ann"), None)[1]
    with pytest.raises(UnknownPrincipal):
        b.call_back()
    assert world.token_calls() == 1
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED


# --- the poll (3.8, 3.9) --------------------------------------------------------


def test_the_granted_answer_is_issued_exactly_once(world: World) -> None:
    started = world.flow.start("ann")
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.PENDING
    b = world.browser(started)
    b.open()
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.PENDING
    world.script(reply(200, grant_body("A1")))
    b.call_back()
    answer = world.flow.poll("ann", started.poll_secret)
    assert isinstance(answer, PollGranted)
    assert answer.token not in repr(answer)
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.EXPIRED
    assert len(world.connection_tokens("ann")) == 1
    authed = TokenService(world.store, pepper=PEPPER, clock=world.clock)
    got = authed.authenticate(answer.token)
    assert not isinstance(got, RelayCode)
    assert got.principal_id == "ann"
    assert world.connection_tokens("ann") == [(got.token_id, None)]


def test_the_connection_token_carries_its_label(world: World) -> None:
    assert CONNECTION_TOKEN_LABEL == "connection:strava"
    started = connected(world, "ann", "A1")
    answer = world.flow.poll("ann", started.poll_secret)
    assert isinstance(answer, PollGranted)
    labels = [t.label for t in world.store.list_tokens("ann")]
    assert labels == ["connection:strava"]


def test_a_poll_from_another_principal_answers_expired_and_changes_nothing(
    world: World,
) -> None:
    started = connected(world, "ann", "A1")
    assert world.flow.poll("bea", started.poll_secret) is PollOutcome.EXPIRED
    assert world.store.list_tokens("bea") == ()
    assert world.record(f"result:{sha(started.poll_secret)}") is not None
    assert isinstance(world.flow.poll("ann", started.poll_secret), PollGranted)


def test_a_poll_of_an_unknown_secret_answers_expired(world: World) -> None:
    started = connected(world, "ann", "A1")
    assert world.flow.poll("ann", "x" * 43) is PollOutcome.EXPIRED
    assert world.flow.poll("ann", "") is PollOutcome.EXPIRED
    assert isinstance(world.flow.poll("ann", started.poll_secret), PollGranted)


def test_a_poll_after_expiry_answers_expired(world: World) -> None:
    started = connected(world, "ann", "A1")
    world.clock.now = NOW + 600
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.EXPIRED
    assert world.connection_tokens("ann") == []


def test_a_refused_session_answers_refused_once(world: World) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    b.call_back(error="access_denied")
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.EXPIRED
    assert world.record(f"session:{started.user_code}") is None
    assert world.record(f"poll:{sha(started.poll_secret)}") is None


def test_a_refused_poll_from_another_principal_does_not_spend_the_answer(
    world: World,
) -> None:
    started = world.flow.start("ann")
    b = world.browser(started)
    b.open()
    b.call_back(error="access_denied")
    assert world.flow.poll("bea", started.poll_secret) is PollOutcome.EXPIRED
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.REFUSED


def test_granting_again_revokes_the_earlier_connection_token_only(
    world: World,
) -> None:
    other = TokenService(world.store, pepper=PEPPER, clock=world.clock).mint(
        principal_id="ann", label="laptop"
    )
    first = connected(world, "ann", "A1")
    one = world.flow.poll("ann", first.poll_secret)
    second = connected(world, "ann", "A2")
    two = world.flow.poll("ann", second.poll_secret)
    assert isinstance(one, PollGranted) and isinstance(two, PollGranted)
    service = TokenService(world.store, pepper=PEPPER, clock=world.clock)
    assert service.authenticate(one.token) == RelayCode.TOKEN_REVOKED
    assert not isinstance(service.authenticate(two.token), RelayCode)
    assert not isinstance(service.authenticate(other.token), RelayCode)
    assert world.custody.access_token("ann", deadline=1e9) == Usable("ann", "A2")


def test_a_poll_made_while_another_issues_does_not_issue_a_second_token(
    world: World,
) -> None:
    started = connected(world, "ann", "A1")
    inner: list[PollGranted | PollOutcome] = []
    original = world.tokens.prepare

    def interleaved(*, label: str | None) -> PreparedToken:
        if not inner:
            inner.append(world.flow.poll("ann", started.poll_secret))
        return original(label=label)

    world.tokens.prepare = interleaved  # type: ignore[method-assign]
    answer = world.flow.poll("ann", started.poll_secret)
    assert inner == [PollOutcome.PENDING]
    assert isinstance(answer, PollGranted)
    assert len(world.connection_tokens("ann")) == 1


def test_a_poll_for_a_connection_that_is_gone_answers_expired(world: World) -> None:
    started = connected(world, "ann", "A1")
    assert world.store.delete_connection("ann", "strava", generation=None, now=NOW)
    assert world.flow.poll("ann", started.poll_secret) is PollOutcome.EXPIRED
    assert world.connection_tokens("ann") == []
    assert world.record(f"session:{started.user_code}") is None


def test_moving_an_account_to_another_principal_revokes_the_first_token(
    world: World,
) -> None:
    first = connected(world, "ann", "A1", athlete=7)
    token = world.flow.poll("ann", first.poll_secret)
    assert isinstance(token, PollGranted)
    second = connected(world, "bea", "B1", athlete=7)
    assert world.store.get_connection("ann", "strava") is None
    assert world.store.get_connection("bea", "strava") is not None
    service = TokenService(world.store, pepper=PEPPER, clock=world.clock)
    assert service.authenticate(token.token) == RelayCode.TOKEN_REVOKED
    assert isinstance(world.flow.poll("bea", second.poll_secret), PollGranted)


def test_a_duplicate_token_id_is_retried_with_a_fresh_token(world: World) -> None:
    minted = TokenService(world.store, pepper=PEPPER, clock=world.clock).mint(
        principal_id="ann", label=None
    )
    taken = world.tokens.prepare(label=CONNECTION_TOKEN_LABEL)
    existing = world.store.find_token(minted.token_id)
    assert existing is not None
    world.tokens.queue.append(
        PreparedToken(
            type(taken.new_token)(minted.token_id, taken.new_token.verifier, "x"),
            taken.token,
        )
    )
    started = connected(world, "ann", "A1")
    answer = world.flow.poll("ann", started.poll_secret)
    assert isinstance(answer, PollGranted)
    assert answer.token != taken.token
    assert len(world.connection_tokens("ann")) == 1


def test_a_poll_that_fails_leaves_the_granted_answer_for_the_next_poll(
    world: World,
) -> None:
    minted = TokenService(world.store, pepper=PEPPER, clock=world.clock).mint(
        principal_id="ann", label=None
    )
    started = connected(world, "ann", "A1")
    clashes = [world.tokens.prepare(label=CONNECTION_TOKEN_LABEL) for _ in range(2)]
    for clash in clashes:
        world.tokens.queue.append(
            PreparedToken(
                type(clash.new_token)(minted.token_id, clash.new_token.verifier, "x"),
                clash.token,
            )
        )
    with pytest.raises(DuplicateIdentifier):
        world.flow.poll("ann", started.poll_secret)
    assert world.connection_tokens("ann") == []
    assert isinstance(world.flow.poll("ann", started.poll_secret), PollGranted)
