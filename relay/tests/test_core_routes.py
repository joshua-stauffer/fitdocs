"""Capabilities, token check and token revocation, served through `create_app`.

Every app here comes from `create_app` with a real config (limits, pepper) and an
injected clock, on both backends, so the config -> limiter wiring is exercised.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

import pytest
from starlette.testclient import TestClient
from tests.conformance.state_support import Target, raw

from fitdocs_relay import routes as routes_module
from fitdocs_relay.app import create_app
from fitdocs_relay.config import RelayConfig, load_config
from fitdocs_relay.identity import MintedToken, TokenService
from fitdocs_relay.logs import configure_logging
from fitdocs_relay.ratelimit import WINDOW_S
from fitdocs_relay.shared.relay_envelope import (
    SERVED_ENVELOPES,
    CapabilitiesData,
    decode_answer,
    parse_capabilities,
)
from fitdocs_relay.storage.interface import Storage

PEPPER = "core-routes-pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAeQ"
START = 1_700_000_040  # a multiple of 60
DEFAULT_TOKEN_LIMIT = 60
DEFAULT_CLIENT_LIMIT = 20
HIGH = 100_000
CLIENT = ("203.0.113.9", 4711)
OTHER_CLIENT = ("203.0.113.10", 4712)
UNKNOWN_ID = "a" * 16
UNKNOWN_SECRET = "a" * 52

OK_EMPTY = b'{"envelope":1,"code":"ok","data":{}}'
CAPABILITIES_NONE = (
    b'{"envelope":1,"code":"ok","data":'
    b'{"envelopes":[1],"registration":false,"targets":[]}}'
)


def envelope(code: str, data: str = "{}") -> bytes:
    return f'{{"envelope":1,"code":"{code}","data":{data}}}'.encode()


def limited(wait: int) -> bytes:
    return envelope("rate-limited", f'{{"retry_after_s":{wait}}}')


class Clock:
    def __init__(self, now: int = START) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


@dataclass
class Relay:
    target: Target
    store: Storage
    clock: Clock
    tokens: TokenService
    app: Any
    config: RelayConfig

    def client(self, address: tuple[str, int] = CLIENT) -> TestClient:
        return TestClient(self.app, client=address)

    def mint(self, *, principal_id: str | None = None) -> MintedToken:
        return self.tokens.mint(principal_id=principal_id, label=None)

    def counts(self) -> dict[str, int]:
        rows = raw(self.target, "SELECT key, count FROM rate_counts")
        return {str(key): int(count) for key, count in rows}

    def state(self) -> dict[str, list[Any]]:
        """Everything but the rate counts, row for row."""
        return {
            table: [
                list(row)
                for row in raw(self.target, f"SELECT * FROM {table} ORDER BY 1, 2")
            ]
            for table in ("principals", "tokens", "records")
        }


def client_key(address: str) -> str:
    digest = hmac.new(PEPPER.encode(), b"client\0" + address.encode(), hashlib.sha256)
    return "c:" + digest.hexdigest()[:32]


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"]
    saved = [
        (n, list(logging.getLogger(n).handlers), logging.getLogger(n).level)
        for n in names
    ]
    propagate = {n: logging.getLogger(n).propagate for n in names}
    yield
    for name, handlers, level in saved:
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
    for name, value in propagate.items():
        logging.getLogger(name).propagate = value


@pytest.fixture
def make_relay(
    database_target: Target, open_full_storage: Callable[[], Storage]
) -> Callable[..., Relay]:
    def make(
        *, token_limit: int | None = None, client_limit: int | None = None
    ) -> Relay:
        store = open_full_storage()
        clock = Clock()
        # The limits not named here are the ones load_config defaults to.
        loaded = load_config(
            {
                "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
                "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
            }
        )
        config = replace(
            loaded,
            database=database_target,
            token_limit_per_minute=token_limit or loaded.token_limit_per_minute,
            client_limit_per_minute=client_limit or loaded.client_limit_per_minute,
        )
        return Relay(
            target=database_target,
            store=store,
            clock=clock,
            tokens=TokenService(store, pepper=config.pepper, clock=clock),
            app=create_app(config, storage=store, clock=clock),
            config=config,
        )

    return make


@pytest.fixture
def relay(make_relay: Callable[..., Relay]) -> Relay:
    return make_relay(token_limit=HIGH, client_limit=HIGH)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- capabilities ---------------------------------------------------------------


def test_capabilities_with_no_target_and_registration_false(relay: Relay) -> None:
    with relay.client() as client:
        sent = client.get("/v1/capabilities")
    assert (sent.status_code, sent.content) == (200, CAPABILITIES_NONE)
    assert sent.headers["content-type"] == "application/json"
    assert sent.headers["cache-control"] == "no-store"
    assert "retry-after" not in sent.headers


def test_capabilities_round_trip_through_the_shared_parser(
    relay: Relay, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_module, "OFFERED_TARGETS", ("zeta", "alpha-2"))
    with relay.client() as client:
        sent = client.get("/v1/capabilities")
    decoded = decode_answer(sent.content)
    assert parse_capabilities(decoded.data) == CapabilitiesData(
        envelopes=SERVED_ENVELOPES, registration=False, targets=("zeta", "alpha-2")
    )


def test_capabilities_need_no_token_and_ignore_a_bad_one(relay: Relay) -> None:
    with relay.client() as client:
        bare = client.get("/v1/capabilities")
        bad = client.get("/v1/capabilities", headers=auth("nonsense"))
        revoked = relay.mint()
        relay.tokens.revoke(revoked.token_id)
        gone = client.get("/v1/capabilities", headers=auth(revoked.token))
        valid = relay.mint()
        presented = client.get("/v1/capabilities", headers=auth(valid.token))
    assert [s.content for s in (bare, bad, gone, presented)] == [CAPABILITIES_NONE] * 4
    # only the client is counted: a presented valid token gets no count of its own
    assert relay.counts() == {client_key(CLIENT[0]): 4}
    assert "t:" + valid.token_id not in relay.counts()


def test_capabilities_are_limited_per_client(make_relay: Callable[..., Relay]) -> None:
    relay = make_relay(token_limit=HIGH, client_limit=3)
    with relay.client() as mine, relay.client(OTHER_CLIENT) as other:
        first = [mine.get("/v1/capabilities") for _ in range(3)]
        fourth = mine.get("/v1/capabilities")
        elsewhere = other.get("/v1/capabilities")
    assert [s.content for s in first] == [CAPABILITIES_NONE] * 3
    assert (fourth.status_code, fourth.content) == (429, limited(WINDOW_S))
    assert fourth.headers["retry-after"] == str(WINDOW_S)
    assert elsewhere.content == CAPABILITIES_NONE


# --- token check ----------------------------------------------------------------


def test_a_valid_token_checks_ok_with_empty_data(relay: Relay) -> None:
    token = relay.mint()
    with relay.client() as client:
        sent = client.get("/v1/token", headers=auth(token.token))
    assert (sent.status_code, sent.content) == (200, OK_EMPTY)
    assert sent.headers["cache-control"] == "no-store"


def test_the_token_check_changes_nothing_but_the_tokens_own_count(
    relay: Relay,
) -> None:
    token = relay.mint()
    sibling = relay.mint(principal_id=token.principal_id)
    before = relay.state()
    assert len(before["tokens"]) == 2
    assert relay.counts() == {}
    with relay.client() as client:
        sent = client.get("/v1/token", headers=auth(token.token))
    assert sent.content == OK_EMPTY
    assert relay.state() == before
    assert relay.counts() == {"t:" + token.token_id: 1}
    assert sibling.token_id != token.token_id


def test_a_missing_token_answers_token_missing(relay: Relay) -> None:
    with relay.client() as client:
        bare = client.get("/v1/token")
        wrong_scheme = client.get(
            "/v1/token", headers={"Authorization": "Basic dXNlcjpwdw=="}
        )
        empty = client.get("/v1/token", headers={"Authorization": "Bearer"})
        spaces = client.get("/v1/token", headers={"Authorization": "Bearer    "})
    for sent in (bare, wrong_scheme, empty, spaces):
        assert (sent.status_code, sent.content) == (401, envelope("token-missing"))


def test_an_unknown_or_malformed_token_answers_token_unknown(relay: Relay) -> None:
    real = relay.mint()
    wrong_secret = real.token[:-1] + ("b" if real.token[-1] != "b" else "c")
    guesses = [
        "nonsense",
        f"fdr1_{UNKNOWN_ID}_{UNKNOWN_SECRET}",
        wrong_secret,
    ]
    with relay.client() as client:
        sent = [client.get("/v1/token", headers=auth(t)) for t in guesses]
    for each in sent:
        assert (each.status_code, each.content) == (401, envelope("token-unknown"))


def test_a_revoked_token_answers_token_revoked_on_the_next_request(
    relay: Relay,
) -> None:
    token = relay.mint()
    with relay.client() as client:
        before = client.get("/v1/token", headers=auth(token.token))
        revoked = client.post(
            "/v1/token/revoke", headers=auth(token.token), content=b"{}"
        )
        check = client.get("/v1/token", headers=auth(token.token))
        again = client.post(
            "/v1/token/revoke", headers=auth(token.token), content=b"{}"
        )
    assert before.content == OK_EMPTY
    assert (revoked.status_code, revoked.content) == (200, OK_EMPTY)
    assert (check.status_code, check.content) == (401, envelope("token-revoked"))
    assert (again.status_code, again.content) == (401, envelope("token-revoked"))


def test_a_multi_space_bearer_header_is_the_token(relay: Relay) -> None:
    token = relay.mint()
    with relay.client() as client:
        for spacing in (" ", "   ", "          "):
            sent = client.get(
                "/v1/token", headers={"Authorization": f"Bearer{spacing}{token.token}"}
            )
            assert sent.content == OK_EMPTY, spacing


def test_only_spaces_separate_the_bearer_scheme_from_the_token(relay: Relay) -> None:
    token = relay.mint()
    with relay.client() as client:
        tab = client.get(
            "/v1/token", headers={"Authorization": f"Bearer\t{token.token}"}
        )
        space_then_tab = client.get(
            "/v1/token", headers={"Authorization": f"Bearer \t{token.token}"}
        )
    assert tab.content == envelope("token-missing")
    assert space_then_tab.content == envelope("token-unknown")


# --- revocation -----------------------------------------------------------------


def test_revocation_revokes_only_the_presenting_token(relay: Relay) -> None:
    first = relay.mint()
    second = relay.mint(principal_id=first.principal_id)
    other_principal = relay.mint()
    with relay.client() as client:
        assert client.get("/v1/token", headers=auth(second.token)).content == OK_EMPTY
        sent = client.post("/v1/token/revoke", headers=auth(first.token), content=b"{}")
        assert sent.content == OK_EMPTY
        assert client.get("/v1/token", headers=auth(first.token)).content == envelope(
            "token-revoked"
        )
        assert client.get("/v1/token", headers=auth(second.token)).content == OK_EMPTY
        assert (
            client.get("/v1/token", headers=auth(other_principal.token)).content
            == OK_EMPTY
        )
    revoked = {
        str(token_id): revoked_at is not None
        for token_id, revoked_at in raw(
            relay.target, "SELECT token_id, revoked_at FROM tokens"
        )
    }
    assert revoked == {
        first.token_id: True,
        second.token_id: False,
        other_principal.token_id: False,
    }


def test_revocation_with_a_bad_body_revokes_nothing(relay: Relay) -> None:
    token = relay.mint()
    before = relay.state()
    with relay.client() as client:
        extra = client.post(
            "/v1/token/revoke", headers=auth(token.token), content=b'{"a":1}'
        )
        junk = client.post("/v1/token/revoke", headers=auth(token.token), content=b"x")
        empty = client.post("/v1/token/revoke", headers=auth(token.token), content=b"")
        check = client.get("/v1/token", headers=auth(token.token))
    assert [s.content for s in (extra, junk, empty)] == [
        envelope("request-malformed")
    ] * 3
    assert check.content == OK_EMPTY
    assert relay.state() == before


def test_revocation_authenticates_before_it_reads_the_body(relay: Relay) -> None:
    with relay.client() as client:
        sent = client.post("/v1/token/revoke", content=b"x")
    assert sent.content == envelope("token-missing")


def test_a_revocation_that_finds_no_token_after_authenticating_answers_unknown(
    relay: Relay, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs_relay.storage.interface import RevokeResult

    token = relay.mint()
    seen: list[str] = []

    def vanished(self: TokenService, token_id: str) -> RevokeResult:
        seen.append(token_id)
        return RevokeResult.UNKNOWN

    monkeypatch.setattr(TokenService, "revoke", vanished)
    with relay.client() as client:
        sent = client.post("/v1/token/revoke", headers=auth(token.token), content=b"{}")
    assert seen == [token.token_id]
    assert sent.content == envelope("token-unknown")


def test_revoking_an_already_revoked_token_in_a_race_still_answers_ok(
    relay: Relay, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs_relay.storage.interface import RevokeResult

    token = relay.mint()
    monkeypatch.setattr(
        TokenService, "revoke", lambda self, token_id: RevokeResult.ALREADY_REVOKED
    )
    with relay.client() as client:
        sent = client.post("/v1/token/revoke", headers=auth(token.token), content=b"{}")
    assert sent.content == OK_EMPTY


def test_the_routes_answer_only_their_own_methods(relay: Relay) -> None:
    token = relay.mint()
    before = relay.state()
    with relay.client() as client:
        revoke_by_get = client.get("/v1/token/revoke", headers=auth(token.token))
        check_by_post = client.post(
            "/v1/token", headers=auth(token.token), content=b"{}"
        )
        capabilities_by_post = client.post("/v1/capabilities", content=b"{}")
        check = client.get("/v1/token", headers=auth(token.token))
    for sent in (revoke_by_get, check_by_post, capabilities_by_post):
        assert (sent.status_code, sent.content) == (404, envelope("not-offered"))
    assert check.content == OK_EMPTY
    assert relay.state() == before
    assert relay.counts() == {"t:" + token.token_id: 1}


# --- limits ---------------------------------------------------------------------


def test_the_sixty_first_request_is_rate_limited_with_header_and_data(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay()  # the documented defaults: 60 per token, 20 per client
    assert (
        relay.config.token_limit_per_minute,
        relay.config.client_limit_per_minute,
    ) == (
        DEFAULT_TOKEN_LIMIT,
        DEFAULT_CLIENT_LIMIT,
    )
    token = relay.mint()
    other = relay.mint()
    relay.clock.now = START + 5
    with relay.client() as client:
        sent = [client.get("/v1/token", headers=auth(token.token)) for _ in range(60)]
        sixty_first = client.get("/v1/token", headers=auth(token.token))
        elsewhere = client.get("/v1/token", headers=auth(other.token))
    assert [s.content for s in sent] == [OK_EMPTY] * 60
    assert (sixty_first.status_code, sixty_first.content) == (429, limited(55))
    assert sixty_first.headers["retry-after"] == "55"
    assert sixty_first.headers["cache-control"] == "no-store"
    assert elsewhere.content == OK_EMPTY
    assert relay.counts() == {"t:" + token.token_id: 61, "t:" + other.token_id: 1}


def test_the_token_limit_comes_from_the_config_and_resets_with_the_window(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(token_limit=2, client_limit=HIGH)
    token = relay.mint()
    with relay.client() as client:
        results = [client.get("/v1/token", headers=auth(token.token)) for _ in range(3)]
        relay.clock.now = START + WINDOW_S
        later = client.get("/v1/token", headers=auth(token.token))
    assert [s.content for s in results] == [OK_EMPTY, OK_EMPTY, limited(WINDOW_S)]
    assert later.content == OK_EMPTY


def test_a_rate_limited_request_does_not_run_and_changes_nothing(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(token_limit=1, client_limit=HIGH)
    token = relay.mint()
    with relay.client() as client:
        assert client.get("/v1/token", headers=auth(token.token)).content == OK_EMPTY
        before = relay.state()
        blocked = client.post(
            "/v1/token/revoke", headers=auth(token.token), content=b"{}"
        )
        assert blocked.content == limited(WINDOW_S)
        assert relay.state() == before
        relay.clock.now = START + WINDOW_S
        after = client.get("/v1/token", headers=auth(token.token))
    assert after.content == OK_EMPTY  # the blocked revocation never ran
    assert relay.counts().get(client_key(CLIENT[0])) is None


def test_a_valid_token_is_authenticated_before_its_limit_and_costs_the_client_nothing(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(token_limit=1, client_limit=1)
    token = relay.mint()
    with relay.client() as client:
        for _ in range(4):
            client.get("/v1/token", headers=auth(token.token))
    assert relay.counts() == {"t:" + token.token_id: 4}


def test_failed_authentications_count_per_client_before_answering(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(token_limit=HIGH, client_limit=3)
    good = relay.mint()
    revoked = relay.mint()
    relay.tokens.revoke(revoked.token_id)
    with relay.client() as mine, relay.client(OTHER_CLIENT) as other:
        failures = [
            mine.get("/v1/token"),  # missing
            mine.get("/v1/token", headers=auth(f"fdr1_{UNKNOWN_ID}_{UNKNOWN_SECRET}")),
            mine.get("/v1/token", headers=auth(revoked.token)),
        ]
        assert relay.counts()[client_key(CLIENT[0])] == 3
        blocked_missing = mine.get("/v1/token")
        blocked_unknown = mine.get("/v1/token", headers=auth("nonsense"))
        blocked_revoked = mine.get("/v1/token", headers=auth(revoked.token))
        still_good = mine.get("/v1/token", headers=auth(good.token))
        elsewhere = other.get("/v1/token")
    assert [s.content for s in failures] == [
        envelope("token-missing"),
        envelope("token-unknown"),
        envelope("token-revoked"),
    ]
    for sent in (blocked_missing, blocked_unknown, blocked_revoked):
        assert (sent.status_code, sent.content) == (429, limited(WINDOW_S))
        assert sent.headers["retry-after"] == str(WINDOW_S)
    assert still_good.content == OK_EMPTY  # a valid token is not a failed attempt
    assert elsewhere.content == envelope("token-missing")
    assert relay.counts()[client_key(CLIENT[0])] == 6
    assert relay.counts()[client_key(OTHER_CLIENT[0])] == 1


def test_failed_authentications_never_touch_a_token_count(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(token_limit=1, client_limit=HIGH)
    revoked = relay.mint()
    relay.tokens.revoke(revoked.token_id)
    wrong = revoked.token[:-1] + ("b" if revoked.token[-1] != "b" else "c")
    with relay.client() as client:
        for _ in range(3):
            client.get("/v1/token", headers=auth(revoked.token))
            client.get("/v1/token", headers=auth(wrong))
    assert set(relay.counts()) == {client_key(CLIENT[0])}
    assert relay.counts()[client_key(CLIENT[0])] == 6


# --- the request log ------------------------------------------------------------


def test_the_log_carries_the_token_id_only_for_an_authenticated_request(
    relay: Relay,
) -> None:
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password="core-routes-db-passw0rd", stream=out)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = relay.mint()
    with relay.client() as client:
        client.get("/v1/token", headers=auth(token.token))
        client.get("/v1/token", headers=auth("nonsense"))
        client.get("/v1/capabilities")
    records = [json.loads(line) for line in out.getvalue().splitlines()]
    requests = [
        r for r in records if r["event"] == "request" and r["route"] != "/readyz"
    ]
    assert [(r["route"], r["code"], r.get("token_id")) for r in requests] == [
        ("/v1/token", "ok", token.token_id),
        ("/v1/token", "token-unknown", None),
        ("/v1/capabilities", "ok", None),
    ]
    assert all("token_id" not in r for r in requests[1:])


def test_a_rate_limited_authenticated_request_still_logs_its_token_id(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(token_limit=1, client_limit=HIGH)
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password="core-routes-db-passw0rd", stream=out)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = relay.mint()
    with relay.client() as client:
        client.get("/v1/token", headers=auth(token.token))
        client.get("/v1/token", headers=auth(token.token))
    records = [json.loads(line) for line in out.getvalue().splitlines()]
    codes = [
        (r["code"], r.get("token_id")) for r in records if r["route"] == "/v1/token"
    ]
    assert codes == [("ok", token.token_id), ("rate-limited", token.token_id)]
