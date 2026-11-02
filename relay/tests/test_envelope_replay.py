"""Replay of the recorded envelope exchanges (`relay/contract/envelope-v1.json`).

Each exchange names the state it was recorded against, carries the request as
sent and the answer as received. The relay is rebuilt in that state through
`create_app` and the request replayed; the answer must match status, headers
and body byte for byte. Task 6.8 feeds the same file through the fitdocs client.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from starlette.routing import Route
from starlette.testclient import TestClient
from tests.conformance.state_support import Target

from fitdocs_relay.app import create_app
from fitdocs_relay.config import RelayConfig, load_config
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
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import (
    NewPrincipal,
    NewToken,
    SchemaChange,
    Storage,
)
from fitdocs_relay.storage.migrate import migrate

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


def config_for(target: Target, *, client_limit: int) -> RelayConfig:
    loaded = load_config(
        {
            "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
            "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
        }
    )
    return replace(
        loaded,
        database=target,
        token_limit_per_minute=HIGH,
        client_limit_per_minute=client_limit,
    )


@pytest.fixture
def started_client(
    database_target: Target,
) -> Iterator[Callable[[str, dict[str, str]], TestClient]]:
    stack = contextlib.ExitStack()
    opened: list[Storage] = []

    def start(profile: str, provider: dict[str, str]) -> TestClient:
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
    started_client: Callable[[str, dict[str, str]], TestClient],
) -> None:
    state = exchange["state"]
    client = started_client(
        state["profile"], state.get("provider", {"start": "refused", "poll": "pending"})
    )
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


# --- coverage: derived from the whole collections, never listed by hand ---------


def answer_code(exchange: dict[str, Any]) -> str:
    decoded = json.loads(body_bytes(exchange["answer"]["body"]))
    code: str = decoded["code"]
    return code


# strava-publish task 1.3 appends these; their routes arrive in the relay
# tasks and strava-publish task 4.4 records their exchanges, so until then the
# recording legitimately lacks them. Task 4.4 deletes this set.
_CONNECT_CODES_RECORDED_BY_4_4 = frozenset(
    {
        "connect-started",
        "connect-pending",
        "connect-granted",
        "connect-refused",
        "connect-expired",
    }
)


def test_every_relay_origin_code_is_recorded_with_its_status() -> None:
    relay_codes = {
        info.code.value: info.http_status
        for info in RELAY_CODES.values()
        if info.origin is CodeOrigin.RELAY
        and info.code.value not in _CONNECT_CODES_RECORDED_BY_4_4
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
    store = open_storage(database_target)
    try:
        app = create_app(config_for(database_target, client_limit=HIGH), storage=store)
        routes = [r for r in app.routes if isinstance(r, Route)]
        assert len(routes) >= 7
        assert all(r.methods is not None for r in routes)
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


def test_every_recorded_token_is_the_visibly_fake_all_a_token() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    found = FAKE_TOKEN_SHAPE.findall(text)
    assert found
    assert set(found) == {TOKEN}
    for exchange in EXCHANGES:
        auth = exchange["request"]["headers"].get("Authorization")
        assert auth in (None, f"Bearer {TOKEN}")
