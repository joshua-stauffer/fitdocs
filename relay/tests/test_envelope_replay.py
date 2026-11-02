"""Replay of the recorded envelope exchanges (`relay/contract/envelope-v1.json`).

Each exchange names the state it was recorded against, carries the request as
sent and the answer as received. The relay is rebuilt in that state and the
request replayed; the answer must match status, headers and body byte for byte.
The core states go through `create_app`; the Strava states (profile `strava`,
a named scenario) build the same app from `make_services` with Strava scripted
at the outbound seam, a fixed clock, and the randomness of the connect flow and
of token issuing fixed, so the answer is reproducible. The fitdocs suite feeds
the same file through the fitdocs client.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import itertools
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.routing import Route
from starlette.testclient import TestClient
from tests.conformance.state_support import Target
from tests.strava.scripted_strava import ScriptedOutbound, reply
from tests.strava.test_connect import cookie_value
from tests.test_config_strava import env as strava_env

from fitdocs_relay import identity
from fitdocs_relay.app import RelayServices, build_app, create_app, make_services
from fitdocs_relay.config import RelayConfig, load_config
from fitdocs_relay.routes import core_routes
from fitdocs_relay.seam import (
    SEAM_VERSION,
    ExtensionContext,
    ExtensionParts,
    IssuedToken,
    PollExpired,
    PollIssued,
    PollPending,
    PollRefused,
    PollSlowDown,
    RateLimitedAnswer,
    StartAccepted,
    StartRefused,
)
from fitdocs_relay.shared.relay_codes import RELAY_CODES, CodeOrigin
from fitdocs_relay.shared.relay_targets import (
    ACTION_PUBLISH,
    ACTION_UPLOAD,
    PUBLISH_OUTCOMES,
    STRAVA,
    UPLOAD_OUTCOMES,
    target_route,
)
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import (
    NewPrincipal,
    NewToken,
    SchemaChange,
    Storage,
)
from fitdocs_relay.storage.migrate import migrate
from fitdocs_relay.strava import connect as connect_flow
from fitdocs_relay.strava.api import Grant
from fitdocs_relay.strava.resolve import LIST_PAGE_SIZE, LIST_WINDOW_S

CONTRACT = Path(__file__).resolve().parents[1] / "contract" / "envelope-v1.json"
PEPPER = "envelope-replay-pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAe"
START_TIME = 1_700_000_040  # a multiple of 60: a rate wait is a whole window
HIGH = 100_000
CLIENT = ("203.0.113.9", 4711)
TOKEN_ID = "a" * 16
TOKEN_SECRET = "a" * 52
TOKEN = f"fdr1_{TOKEN_ID}_{TOKEN_SECRET}"
PRINCIPAL_ID = "prn_" + "a" * 16
FAKE_TOKEN_SHAPE = re.compile(r"fdr1_[A-Za-z0-9_]*")
PROFILES = frozenset(
    {
        "default",
        "no-provider",
        "unseeded",
        "token-revoked",
        "client-limit-spent",
        "store-closed",
        "schema-behind",
        "schema-ahead",
    }
)
START_ANSWERS: dict[str, Any] = {
    "accepted": StartAccepted("BCDF-GHJK", "a" * 48, 5, 600),
    "refused": StartRefused(),
    "rate-limited": RateLimitedAnswer(7),
}
POLL_ANSWERS: dict[str, Any] = {
    "pending": PollPending(),
    "slow-down": PollSlowDown(),
    "issued": PollIssued(IssuedToken(TOKEN_ID, PRINCIPAL_ID, TOKEN)),
    "refused": PollRefused(),
    "expired": PollExpired(),
}
RAISES = "raises"

# --- the Strava states --------------------------------------------------------
# Visibly fake hosts, tokens and ids; the only host that reaches a recorded
# answer is the web host in a link.
STRAVA_PROFILE = "strava"
STRAVA_API = "https://api.strava.example.invalid/v3"
STRAVA_OAUTH = "https://oauth.strava.example.invalid/oauth"
STRAVA_WEB = "https://strava.example.invalid"
CONNECTION_TOKEN = "fdr1_" + "b" * 16 + "_" + "b" * 52
USER_CODE = "BCDF-GHJK"
POLL_SECRET = "a" * 43
CLAIM_COOKIE_VALUE = "c" * 43
FULL_SCOPE = "read,activity:read_all,activity:write"
HUGE_LIMIT = "1000000,1000000"
PLUS_2 = timezone(timedelta(hours=2))
ACTIVITY_START = datetime(2026, 3, 1, 10, 0, 0, tzinfo=PLUS_2)
ACTIVITY_START_UTC = "2026-03-01T08:00:00Z"
START_S = int(ACTIVITY_START.timestamp())
LIST_URL = (
    f"{STRAVA_API}/athlete/activities?after={START_S - LIST_WINDOW_S}"
    f"&before={START_S + LIST_WINDOW_S}&per_page={LIST_PAGE_SIZE}&page=1"
)
UPLOAD_URL = f"{STRAVA_API}/uploads"
UPLOAD_ID = 5550001
STATUS_URL = f"{UPLOAD_URL}/{UPLOAD_ID}"
REVOKE_URL = f"{STRAVA_OAUTH}/revoke"
TOKEN_URL = f"{STRAVA_OAUTH}/token"


@dataclass
class StravaSetup:
    services: RelayServices
    outbound: ScriptedOutbound

    def connected(self) -> None:
        assert self.services.strava is not None
        self.services.strava.custody.store_grant(
            PRINCIPAL_ID,
            Grant("access-token-fake", "refresh-token-fake", START_TIME + 86_400, "x"),
        )

    def listing(self, *ids: int) -> None:
        entries = [
            {
                "id": activity_id,
                "sport_type": "Run",
                "start_date": ACTIVITY_START_UTC,
                "elapsed_time": 1800.0,
                "distance": 5000.0,
            }
            for activity_id in ids
        ]
        self.outbound.expect("GET", LIST_URL, reply(200, entries))

    def updates(self, activity_id: int = 1) -> None:
        self.outbound.expect(
            "PUT", f"{STRAVA_API}/activities/{activity_id}", reply(200, {})
        )

    def session(self) -> Any:
        assert self.services.strava is not None
        return self.services.strava.connect.start(PRINCIPAL_ID)

    def browser(self, started: Any, *, approve: bool) -> None:
        assert self.services.strava is not None
        flow = self.services.strava.connect
        shown = flow.page(started.user_code, None)
        assert not isinstance(shown, connect_flow.PageOutcome)
        assert shown.set_cookie is not None
        state = parse_qs(urlsplit(shown.authorize_url).query)["state"][0]
        if approve:
            body = {
                "access_token": "access-token-fake",
                "refresh_token": "refresh-token-fake",
                "expires_at": START_TIME + 21_600,
                "athlete": {"id": 1},
            }
            self.outbound.expect("POST", TOKEN_URL, reply(200, body))
        flow.callback(
            state=state,
            code="code-fake" if approve else None,
            scope=FULL_SCOPE,
            error=None if approve else "access_denied",
            cookie=cookie_value(shown.set_cookie),
        )


def _nothing(setup: StravaSetup) -> None:
    return None


def _uploads(setup: StravaSetup, status: Any) -> None:
    setup.connected()
    setup.listing()
    setup.outbound.expect("POST", UPLOAD_URL, reply(201, {"id": UPLOAD_ID}))
    setup.outbound.expect("GET", STATUS_URL, status)


def _a_session_awaiting_the_browser(setup: StravaSetup) -> None:
    setup.session()


def _a_granted_session(setup: StravaSetup) -> None:
    setup.browser(setup.session(), approve=True)


def _a_declined_session(setup: StravaSetup) -> None:
    setup.browser(setup.session(), approve=False)


def _a_connection(setup: StravaSetup) -> None:
    setup.connected()


def _a_connection_and_one_match(setup: StravaSetup) -> None:
    setup.connected()
    setup.listing(1)
    setup.updates()


def _a_connection_and_no_match(setup: StravaSetup) -> None:
    setup.connected()
    setup.listing()


def _a_connection_and_two_matches(setup: StravaSetup) -> None:
    setup.connected()
    setup.listing(1, 2)


def _a_connection_and_a_strava_limit(setup: StravaSetup) -> None:
    setup.connected()
    setup.outbound.expect("GET", LIST_URL, reply(429))


def _a_connection_to_revoke(setup: StravaSetup) -> None:
    setup.connected()
    setup.outbound.expect("POST", REVOKE_URL, reply(200, {}))


# scenario name -> (the relay's link setting, the state the request meets)
STRAVA_SCENARIOS: dict[str, tuple[str, Callable[[StravaSetup], None]]] = {
    "nothing": ("activity", _nothing),
    "session-awaiting-browser": ("activity", _a_session_awaiting_the_browser),
    "session-granted": ("activity", _a_granted_session),
    "session-declined": ("activity", _a_declined_session),
    "connected-one-match": ("activity", _a_connection_and_one_match),
    "connected-one-match-relay-links": ("relay", _a_connection_and_one_match),
    "connected-no-match": ("activity", _a_connection_and_no_match),
    "connected-no-facts": ("activity", _a_connection),
    "connected-two-matches": ("activity", _a_connection_and_two_matches),
    "connected-strava-limit": ("activity", _a_connection_and_a_strava_limit),
    "connected-new-upload": (
        "activity",
        lambda setup: _uploads(setup, reply(200, {"id": UPLOAD_ID, "activity_id": 1})),
    ),
    "connected-new-upload-relay-links": (
        "relay",
        lambda setup: _uploads(setup, reply(200, {"id": UPLOAD_ID, "activity_id": 1})),
    ),
    "connected-upload-unconfirmed": (
        "activity",
        lambda setup: _uploads(setup, reply(500)),
    ),
    "connected-to-revoke": ("activity", _a_connection_to_revoke),
}


def load_exchanges() -> list[dict[str, Any]]:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["envelope"] == 1
    exchanges: list[dict[str, Any]] = document["exchanges"]
    return exchanges


def body_bytes(body: str | dict[str, Any]) -> bytes:
    """A recorded body: text, or a prefix, a repeated filler and a suffix."""
    if isinstance(body, str):
        return body.encode("utf-8")
    filler = str(body["fill"]) * int(body["count"])
    return (str(body["prefix"]) + filler + str(body["suffix"])).encode()


class Scripted:
    def __init__(self, start: str, poll: str) -> None:
        self.start_name = start
        self.poll_name = poll

    def start(self, email: str) -> Any:
        if self.start_name == RAISES:
            raise RuntimeError("the provider failed")
        return START_ANSWERS[self.start_name]

    def poll(self, poll_secret: str) -> Any:
        if self.poll_name == RAISES:
            raise RuntimeError("the provider failed")
        return POLL_ANSWERS[self.poll_name]


@dataclass
class Extension:
    provider: Scripted
    name: str = "scripted"
    seam_version: int = SEAM_VERSION

    def build(self, context: ExtensionContext) -> ExtensionParts:
        return ExtensionParts(registration=self.provider)


def verifier(token_id: str, secret: str) -> str:
    """The stored verifier, computed from the pepper as the design states it."""
    message = b"fitdocs-relay-token-v1\0" + token_id.encode() + b"\0" + secret.encode()
    return hmac.new(PEPPER.encode(), message, hashlib.sha256).hexdigest()


def config_for(
    target: Target, *, client_limit: int, links: str | None = None
) -> RelayConfig:
    environ = {
        "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
        "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
    }
    if links is not None:
        environ = strava_env(
            {
                "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
                "FITDOCS_RELAY_STRAVA_API_URL": STRAVA_API,
                "FITDOCS_RELAY_STRAVA_OAUTH_URL": STRAVA_OAUTH,
                "FITDOCS_RELAY_STRAVA_WEB_URL": STRAVA_WEB,
                "FITDOCS_RELAY_STRAVA_LINKS": links,
                "FITDOCS_RELAY_STRAVA_RATE_LIMIT": HUGE_LIMIT,
                "FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT": HUGE_LIMIT,
            }
        )
    loaded = load_config(environ)
    return replace(
        loaded,
        database=target,
        token_limit_per_minute=HIGH,
        client_limit_per_minute=client_limit,
    )


@pytest.fixture
def scripted_outbounds() -> list[ScriptedOutbound]:
    """The scripted Strava outbound of every Strava state a test started."""
    return []


@pytest.fixture
def started_client(
    database_target: Target,
    monkeypatch: pytest.MonkeyPatch,
    scripted_outbounds: list[ScriptedOutbound],
) -> Iterator[Callable[[dict[str, Any]], TestClient]]:
    stack = contextlib.ExitStack()
    opened: list[Storage] = []

    def start_strava(scenario: str) -> TestClient:
        links, prepare = STRAVA_SCENARIOS[scenario]
        store = open_storage(database_target)
        opened.append(store)
        migrate(store, now=1)
        store.mint_token(
            NewToken(TOKEN_ID, verifier(TOKEN_ID, TOKEN_SECRET), None),
            principal_id=None,
            new_principal=NewPrincipal(PRINCIPAL_ID, None),
            now=1,
        )
        drawn = itertools.cycle((POLL_SECRET, "b" * 43, CLAIM_COOKIE_VALUE))
        monkeypatch.setattr(connect_flow, "_random_code", lambda: USER_CODE)
        monkeypatch.setattr(
            connect_flow,
            "secrets",
            SimpleNamespace(token_urlsafe=lambda nbytes: next(drawn)),
        )
        monkeypatch.setattr(identity, "_random", lambda length: "b" * length)
        outbound = ScriptedOutbound()
        scripted_outbounds.append(outbound)
        services = make_services(
            config_for(database_target, client_limit=HIGH, links=links),
            store,
            clock=lambda: START_TIME,
            outbound=outbound,
            monotonic=lambda: 0.0,
            sleep=lambda seconds: None,
        )
        prepare(StravaSetup(services, outbound))
        app = build_app(services, core_routes(services))
        return stack.enter_context(TestClient(app, client=CLIENT))

    def start(state: dict[str, Any]) -> TestClient:
        profile = state["profile"]
        if profile == STRAVA_PROFILE:
            return start_strava(state["scenario"])
        provider = state.get("provider", {"start": "refused", "poll": "pending"})
        assert profile in PROFILES
        store = open_storage(database_target)
        opened.append(store)
        if profile != "schema-behind":
            migrate(store, now=1)
        if profile == "schema-ahead":
            expected = store.schema_state().expected
            store.apply_schema_change(
                SchemaChange(
                    expected + 1, "9999_newer", "CREATE TABLE newer (x integer)"
                ),
                now=2,
            )
        if profile not in ("unseeded", "schema-behind", "schema-ahead"):
            store.mint_token(
                NewToken(TOKEN_ID, verifier(TOKEN_ID, TOKEN_SECRET), None),
                principal_id=None,
                new_principal=NewPrincipal(PRINCIPAL_ID, None),
                now=1,
            )
        if profile == "token-revoked":
            store.revoke_token(TOKEN_ID, now=2)
        extensions = (
            ()
            if profile == "no-provider"
            else (Extension(Scripted(provider["start"], provider["poll"])),)
        )
        limit = 1 if profile == "client-limit-spent" else HIGH
        app = create_app(
            config_for(database_target, client_limit=limit),
            extensions=extensions,
            storage=store,
            clock=lambda: START_TIME,
        )
        client = stack.enter_context(TestClient(app, client=CLIENT))
        if profile == "client-limit-spent":
            assert client.get("/v1/capabilities").status_code == 200
        if profile == "store-closed":
            store.close()
        return client

    with stack:
        yield start
    for store in opened:
        store.close()


EXCHANGES = load_exchanges()


def test_the_recording_is_not_empty() -> None:
    assert len(EXCHANGES) >= len(RELAY_CODES) - 2
    assert len({e["name"] for e in EXCHANGES}) == len(EXCHANGES)


@pytest.mark.parametrize("exchange", EXCHANGES, ids=[e["name"] for e in EXCHANGES])
def test_the_relay_replays_the_recorded_exchange(
    exchange: dict[str, Any],
    started_client: Callable[[dict[str, Any]], TestClient],
    scripted_outbounds: list[ScriptedOutbound],
) -> None:
    client = started_client(exchange["state"])
    asked = exchange["request"]
    sent = client.request(
        asked["method"],
        asked["path"],
        headers=asked["headers"],
        content=body_bytes(asked["body"]),
    )
    given = exchange["answer"]
    assert sent.status_code == given["status"]
    assert sent.content == body_bytes(given["body"])
    assert dict(sent.headers) == given["headers"]
    # A Strava scenario scripts the Strava exchange its answer depends on; one
    # left unserved means the replay never made it.
    assert [o.unserved() for o in scripted_outbounds] == [0] * len(scripted_outbounds)


# --- coverage: derived from the whole collections, never listed by hand ---------


def answer_code(exchange: dict[str, Any]) -> str:
    decoded = json.loads(body_bytes(exchange["answer"]["body"]))
    code: str = decoded["code"]
    return code


def test_every_relay_origin_code_is_recorded_with_its_status() -> None:
    relay_codes = {
        info.code.value: info.http_status
        for info in RELAY_CODES.values()
        if info.origin is CodeOrigin.RELAY
    }
    assert len(relay_codes) >= 20
    recorded: dict[str, set[int]] = {}
    for exchange in EXCHANGES:
        recorded.setdefault(answer_code(exchange), set()).add(
            exchange["answer"]["status"]
        )
    for code, status in relay_codes.items():
        assert recorded.get(code) == {status}, code
    assert set(recorded) <= set(relay_codes)  # no client-origin code on the wire


def test_every_route_is_recorded_on_a_request_it_serves(
    database_target: Target,
) -> None:
    """Every envelope route (path under /v1/) of the app with Strava configured."""
    store = open_storage(database_target)
    try:
        app = create_app(
            config_for(database_target, client_limit=HIGH, links="activity"),
            storage=store,
        )
        routes = [
            r for r in app.routes if isinstance(r, Route) and r.path.startswith("/v1/")
        ]
        assert len(routes) >= 10
        assert any(r.path == target_route(STRAVA, ACTION_PUBLISH) for r in routes)
        for route in routes:
            assert route.methods is not None
            served = [
                e
                for e in EXCHANGES
                if e["request"]["path"] == route.path
                and e["request"]["method"] in route.methods
                and answer_code(e) not in ("not-offered", "envelope-unsupported")
            ]
            assert served, route.path
    finally:
        store.close()


def test_every_recorded_token_is_one_of_the_two_visibly_fake_tokens() -> None:
    # The connection token issued at the end of a connect cannot be the
    # presented token: the two are different rows of one principal.
    text = CONTRACT.read_text(encoding="utf-8")
    found = FAKE_TOKEN_SHAPE.findall(text)
    assert found
    assert set(found) == {TOKEN, CONNECTION_TOKEN}
    for exchange in EXCHANGES:
        auth = exchange["request"]["headers"].get("Authorization")
        assert auth in (None, f"Bearer {TOKEN}")


# --- the Strava exchanges -----------------------------------------------------


def strava_exchanges(action: str) -> list[dict[str, Any]]:
    path = target_route(STRAVA, action)
    return [e for e in EXCHANGES if e["request"]["path"] == path]


def answered(exchange: dict[str, Any]) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(body_bytes(exchange["answer"]["body"]))
    return decoded


def test_every_scenario_is_recorded_and_every_recorded_scenario_exists() -> None:
    named = {e["state"]["scenario"] for e in EXCHANGES if "scenario" in e["state"]}
    assert named == set(STRAVA_SCENARIOS)


def test_the_publish_and_upload_routes_record_the_outcomes_they_can_give() -> None:
    publish = {answered(e).get("outcome") for e in strava_exchanges(ACTION_PUBLISH)}
    upload = {answered(e).get("outcome") for e in strava_exchanges(ACTION_UPLOAD)}
    assert publish == {
        "posted",
        "not_found",
        "ambiguous",
        "rate_limited",
        "not_connected",
        "activity_facts_missing",
    }
    assert upload == {"uploaded", "posted", "unconfirmed", "not_connected"}
    assert publish <= PUBLISH_OUTCOMES
    assert upload <= UPLOAD_OUTCOMES


def test_a_posted_answer_is_recorded_under_each_link_setting() -> None:
    link = f"{STRAVA_WEB}/activities/1"
    for action in (ACTION_PUBLISH, ACTION_UPLOAD):
        data = {
            e["state"]["scenario"]: answered(e)["data"]
            for e in strava_exchanges(action)
            if answered(e).get("outcome") in ("posted", "uploaded")
        }
        assert {k for k, v in data.items() if v == {"link": link}}
        assert {k for k, v in data.items() if v == {}}


def test_the_recording_names_no_real_strava_host() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "strava.com" not in text
    assert "strava.example.invalid" in text
    for match in re.findall(r"https?://[^\\\"]+", text):
        assert match.startswith(STRAVA_WEB + "/activities/"), match
