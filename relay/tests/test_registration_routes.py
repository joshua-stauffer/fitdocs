"""The registration routes, served through a scripted provider installed by an
extension (the seam's own path), on `create_app` with a real config and clock.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import logging
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

import pytest
from starlette.testclient import TestClient
from tests.conformance.state_support import Target, raw

from fitdocs_relay import seam
from fitdocs_relay.app import create_app
from fitdocs_relay.config import RelayConfig, load_config
from fitdocs_relay.identity import TokenService
from fitdocs_relay.logs import configure_logging
from fitdocs_relay.ratelimit import WINDOW_S
from fitdocs_relay.seam import (
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
from fitdocs_relay.shared.relay_envelope import (
    MAX_EMAIL_CHARS,
    MAX_EXPIRES_IN_S,
    MAX_POLL_INTERVAL_S,
    MAX_REQUEST_BYTES,
    MIN_EXPIRES_IN_S,
    MIN_POLL_INTERVAL_S,
    SERVED_ENVELOPES,
    CapabilitiesData,
    StartedData,
    decode_answer,
    encode_request,
    parse_capabilities,
    parse_issued,
    parse_started,
)
from fitdocs_relay.storage.interface import Storage

PEPPER = "registration-routes-pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAe"
START_TIME = 1_700_000_040  # a multiple of 60
HIGH = 100_000
CLIENT = ("203.0.113.9", 4711)
OTHER_CLIENT = ("203.0.113.10", 4712)
START_PATH = "/v1/registrations"
POLL_PATH = "/v1/registrations/poll"

EMAIL = "Plant.Zq9@Example.test"
POLL_SECRET = "Pq7-planted_poll-secret_Zk3wLm9xRv2Tb5Nc8Hd4Ys1Jf6"  # 48 chars
USER_CODE = "BCDF-GHJK"
INTERVAL = 5
EXPIRES = 600
ALL_A_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52

STARTED_BYTES = (
    b'{"envelope":1,"code":"registration-started","data":{'
    b'"user_code":"BCDF-GHJK","poll_secret":"' + POLL_SECRET.encode() + b'",'
    b'"interval_s":5,"expires_in_s":600}}'
)
FAILURE_BYTES = b'{"envelope":1,"code":"relay-failure","data":{}}'
MALFORMED_BYTES = b'{"envelope":1,"code":"request-malformed","data":{}}'
NOT_OFFERED_BYTES = b'{"envelope":1,"code":"not-offered","data":{}}'


def envelope(code: str, data: str = "{}") -> bytes:
    return f'{{"envelope":1,"code":"{code}","data":{data}}}'.encode()


def limited(wait: int) -> bytes:
    return envelope("rate-limited", f'{{"retry_after_s":{wait}}}')


class Clock:
    def __init__(self) -> None:
        self.now = START_TIME

    def __call__(self) -> int:
        return self.now


class Scripted:
    """The provider: answers whatever it is told to, remembers what it was asked."""

    def __init__(self, context: ExtensionContext) -> None:
        self.context = context
        self.start_answer: Any = StartRefused()
        self.poll_answer: Any = PollPending()
        self.raises: Exception | None = None
        self.started: list[str] = []
        self.polled: list[str] = []

    def start(self, email: str) -> Any:
        self.started.append(email)
        if self.raises is not None:
            raise self.raises
        return self.start_answer

    def poll(self, poll_secret: str) -> Any:
        self.polled.append(poll_secret)
        if self.raises is not None:
            raise self.raises
        return self.poll_answer


@dataclass
class Extension:
    name: str = "scripted"
    seam_version: int = seam.SEAM_VERSION
    provider: Scripted | None = None

    def build(self, context: ExtensionContext) -> ExtensionParts:
        self.provider = Scripted(context)
        return ExtensionParts(registration=self.provider)


@dataclass
class Relay:
    target: Target
    store: Storage
    clock: Clock
    tokens: TokenService
    app: Any
    config: RelayConfig
    extension: Extension | None
    stack: contextlib.ExitStack
    clients: dict[tuple[str, int], TestClient]

    @property
    def provider(self) -> Scripted:
        assert self.extension is not None and self.extension.provider is not None
        return self.extension.provider

    def client(self, address: tuple[str, int] = CLIENT) -> TestClient:
        """One started client per address for the whole test: the app closes its
        store when a client's lifespan ends, so each stays open to the test's end."""
        if address not in self.clients:
            self.clients[address] = self.stack.enter_context(
                TestClient(self.app, client=address)
            )
        return self.clients[address]

    def counts(self) -> dict[str, int]:
        rows = raw(self.target, "SELECT key, count FROM rate_counts")
        return {str(key): int(count) for key, count in rows}

    def issue(self, *, principal_id: str | None = None) -> IssuedToken:
        return self.provider.context.tokens.issue(principal_id=principal_id, label=None)


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
) -> Iterator[Callable[..., Relay]]:
    stack = contextlib.ExitStack()

    def make(*, provider: bool = True, client_limit: int | None = None) -> Relay:
        store = open_full_storage()
        clock = Clock()
        loaded = load_config(
            {
                "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
                "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
            }
        )
        config = replace(
            loaded,
            database=database_target,
            token_limit_per_minute=HIGH,
            client_limit_per_minute=client_limit or HIGH,
        )
        extension = Extension() if provider else None
        app = create_app(
            config,
            extensions=() if extension is None else (extension,),
            storage=store,
            clock=clock,
        )
        return Relay(
            database_target,
            store,
            clock,
            TokenService(store, pepper=config.pepper, clock=clock),
            app,
            config,
            extension,
            stack,
            {},
        )

    with stack:
        yield make


@pytest.fixture
def relay(make_relay: Callable[..., Relay]) -> Relay:
    return make_relay()


def start(relay: Relay, email: object = EMAIL) -> Any:
    return relay.client().post(START_PATH, content=encode_request({"email": email}))


def poll(relay: Relay, secret: object = POLL_SECRET) -> Any:
    return relay.client().post(
        POLL_PATH, content=encode_request({"poll_secret": secret})
    )


def accepted(**changes: Any) -> StartAccepted:
    return replace(StartAccepted(USER_CODE, POLL_SECRET, INTERVAL, EXPIRES), **changes)


# --- not offered without a provider ---------------------------------------------


def test_without_a_provider_both_routes_are_not_offered_and_uncounted(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(provider=False)
    started, polled = start(relay), poll(relay)
    for sent in (started, polled):
        assert (sent.status_code, sent.content) == (404, NOT_OFFERED_BYTES)
    assert relay.counts() == {}


def test_without_a_provider_a_malformed_request_is_still_not_offered(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(provider=False)
    client = relay.client()
    sent = client.post(START_PATH, content=b"not json")
    assert (sent.status_code, sent.content) == (404, NOT_OFFERED_BYTES)


def test_the_registration_routes_take_post_only(relay: Relay) -> None:
    client = relay.client()
    got = [client.get(START_PATH), client.get(POLL_PATH)]
    for sent in got:
        assert (sent.status_code, sent.content) == (404, NOT_OFFERED_BYTES)
    assert relay.provider.started == [] and relay.provider.polled == []


# --- capabilities ---------------------------------------------------------------


def test_capabilities_advertise_registration_exactly_when_a_provider_is_installed(
    make_relay: Callable[..., Relay],
) -> None:
    seen: list[bool] = []
    for installed in (False, True):
        relay = make_relay(provider=installed)
        client = relay.client()
        sent = client.get("/v1/capabilities")
        data = parse_capabilities(decode_answer(sent.content).data)
        assert data == CapabilitiesData(SERVED_ENVELOPES, installed, ())
        seen.append(data.registration)
    assert seen == [False, True]


# --- every start answer ---------------------------------------------------------


def test_started_answers_with_the_four_fields_and_round_trips(relay: Relay) -> None:
    relay.provider.start_answer = accepted()
    sent = start(relay)
    assert (sent.status_code, sent.content) == (200, STARTED_BYTES)
    assert sent.headers["content-type"] == "application/json"
    assert sent.headers["cache-control"] == "no-store"
    assert parse_started(decode_answer(sent.content).data) == StartedData(
        USER_CODE, POLL_SECRET, INTERVAL, EXPIRES
    )
    assert relay.provider.started == [EMAIL]
    assert relay.provider.polled == []


def test_a_refused_start_answers_registration_refused_with_empty_data(
    relay: Relay,
) -> None:
    relay.provider.start_answer = StartRefused()
    sent = start(relay)
    assert (sent.status_code, sent.content) == (403, envelope("registration-refused"))
    assert relay.provider.started == [EMAIL]


@pytest.mark.parametrize("wait", [0, 7, 3600])
def test_a_provider_rate_limit_on_start_carries_its_wait(
    relay: Relay, wait: int
) -> None:
    relay.provider.start_answer = RateLimitedAnswer(wait)
    sent = start(relay)
    assert (sent.status_code, sent.content) == (429, limited(wait))
    assert sent.headers["retry-after"] == str(wait)


# --- every poll answer ----------------------------------------------------------


@pytest.mark.parametrize(
    ("answer_", "status", "code"),
    [
        (PollPending(), 200, "registration-pending"),
        (PollSlowDown(), 200, "registration-slow-down"),
        (PollRefused(), 403, "registration-refused"),
        (PollExpired(), 410, "registration-expired"),
    ],
)
def test_poll_outcomes_without_data_answer_empty_data(
    relay: Relay, answer_: Any, status: int, code: str
) -> None:
    relay.provider.poll_answer = answer_
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (status, envelope(code))
    assert relay.provider.polled == [POLL_SECRET]
    assert relay.provider.started == []


@pytest.mark.parametrize("wait", [0, 11])
def test_a_provider_rate_limit_on_poll_carries_its_wait(
    relay: Relay, wait: int
) -> None:
    relay.provider.poll_answer = RateLimitedAnswer(wait)
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (429, limited(wait))
    assert sent.headers["retry-after"] == str(wait)


def test_an_issued_token_answers_with_exactly_the_token_and_round_trips(
    relay: Relay,
) -> None:
    issued = relay.issue()
    relay.provider.poll_answer = PollIssued(issued)
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (
        200,
        envelope("registration-issued", f'{{"token":"{issued.token}"}}'),
    )
    assert parse_issued(decode_answer(sent.content).data) == issued.token
    assert relay.tokens.authenticate(issued.token) is not None


def test_the_seams_answer_unions_are_these_types() -> None:
    """Pins the seam's two answer unions to these literals, so a type added to
    either fails here and must be given cases in this file."""
    start_types = set(typing.get_args(seam.StartAnswer))
    poll_types = set(typing.get_args(seam.PollAnswer))
    assert start_types == {StartAccepted, StartRefused, RateLimitedAnswer}
    assert poll_types == {
        PollPending,
        PollSlowDown,
        PollIssued,
        PollRefused,
        PollExpired,
        RateLimitedAnswer,
    }


def all_poll_answers(relay: Relay) -> list[Any]:
    return [
        PollPending(),
        PollSlowDown(),
        PollIssued(relay.issue()),
        PollRefused(),
        PollExpired(),
        RateLimitedAnswer(1),
    ]


def test_an_answer_of_the_other_route_is_a_failure(relay: Relay) -> None:
    for wrong_for_start in all_poll_answers(relay):
        if isinstance(wrong_for_start, RateLimitedAnswer):
            continue  # a member of both unions
        relay.provider.start_answer = wrong_for_start
        sent = start(relay)
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES), wrong_for_start
    for wrong_for_poll in (accepted(), StartRefused()):
        relay.provider.poll_answer = wrong_for_poll
        sent = poll(relay)
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES), wrong_for_poll


@pytest.mark.parametrize(
    "garbage", [None, "registration-started", {"user_code": USER_CODE}, 3, object()]
)
def test_an_answer_that_is_not_an_answer_type_is_a_failure(
    relay: Relay, garbage: Any
) -> None:
    relay.provider.start_answer = garbage
    relay.provider.poll_answer = garbage
    for sent in (start(relay), poll(relay)):
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


# --- the bounds on StartAccepted ------------------------------------------------

GOOD_CODES = ["BCDF-GHJK", "ZXWV-TSRQ", "BBBB-ZZZZ"]
BAD_CODES = [
    "ACDF-GHJK",  # a vowel in the first half
    "BCDF-GHJA",  # a vowel in the second half
    "BCDF-GHJE",
    "BCDI-GHJK",
    "BCDF-GHOK",
    "BCDF-GHJU",
    "BCDF-GHJY",  # Y is not in the alphabet
    "bcdf-ghjk",
    "BCDFGHJK",
    "BCD-FGHJK",
    "BCDF-GHJ",
    "BCDF-GHJKL",
    "BCDF_GHJK",
    "BCDF-GHJK\n",
    " BCDF-GHJK",
    "",
]
GOOD_SECRETS = ["a" * 32, "A" * 128, "-_09azAZ" * 4, POLL_SECRET]
BAD_SECRETS = [
    "a" * 31,
    "a" * 129,
    "a" * 31 + "=",
    "a" * 31 + " ",
    "a" * 31 + "+",
    "a" * 31 + "/",
    "a" * 31 + "\n",
    "",
]


@pytest.mark.parametrize("user_code", GOOD_CODES)
def test_valid_user_codes_are_served(relay: Relay, user_code: str) -> None:
    relay.provider.start_answer = accepted(user_code=user_code)
    sent = start(relay)
    assert sent.status_code == 200
    assert parse_started(decode_answer(sent.content).data).user_code == user_code


@pytest.mark.parametrize("user_code", BAD_CODES)
def test_an_invalid_user_code_is_a_failure(relay: Relay, user_code: str) -> None:
    relay.provider.start_answer = accepted(user_code=user_code)
    sent = start(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


@pytest.mark.parametrize("secret", GOOD_SECRETS)
def test_valid_poll_secrets_are_served(relay: Relay, secret: str) -> None:
    relay.provider.start_answer = accepted(poll_secret=secret)
    sent = start(relay)
    assert sent.status_code == 200
    assert parse_started(decode_answer(sent.content).data).poll_secret == secret


@pytest.mark.parametrize("secret", BAD_SECRETS)
def test_an_invalid_poll_secret_is_a_failure(relay: Relay, secret: str) -> None:
    relay.provider.start_answer = accepted(poll_secret=secret)
    sent = start(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


@pytest.mark.parametrize("interval", [MIN_POLL_INTERVAL_S, 30, MAX_POLL_INTERVAL_S])
def test_intervals_in_bounds_are_served(relay: Relay, interval: int) -> None:
    relay.provider.start_answer = accepted(interval_s=interval)
    sent = start(relay)
    assert sent.status_code == 200
    assert parse_started(decode_answer(sent.content).data).interval_s == interval


@pytest.mark.parametrize(
    "interval",
    [MIN_POLL_INTERVAL_S - 1, MAX_POLL_INTERVAL_S + 1, -1, 5.0, True, "5", None],
)
def test_intervals_out_of_bounds_or_not_integers_are_a_failure(
    relay: Relay, interval: Any
) -> None:
    relay.provider.start_answer = accepted(interval_s=interval)
    sent = start(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


@pytest.mark.parametrize("expires", [MIN_EXPIRES_IN_S, 1800, MAX_EXPIRES_IN_S])
def test_expiries_in_bounds_are_served(relay: Relay, expires: int) -> None:
    relay.provider.start_answer = accepted(expires_in_s=expires)
    sent = start(relay)
    assert sent.status_code == 200
    assert parse_started(decode_answer(sent.content).data).expires_in_s == expires


@pytest.mark.parametrize(
    "expires",
    [MIN_EXPIRES_IN_S - 1, MAX_EXPIRES_IN_S + 1, 0, 600.0, True, "600", None],
)
def test_expiries_out_of_bounds_or_not_integers_are_a_failure(
    relay: Relay, expires: Any
) -> None:
    relay.provider.start_answer = accepted(expires_in_s=expires)
    sent = start(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


@pytest.mark.parametrize("field", ["user_code", "poll_secret"])
def test_non_text_user_code_and_poll_secret_are_a_failure(
    relay: Relay, field: str
) -> None:
    for value in (None, 12345678, b"BCDF-GHJK", ["BCDF-GHJK"]):
        relay.provider.start_answer = accepted(**{field: value})
        sent = start(relay)
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


@pytest.mark.parametrize("wait", [-1, True, 1.5, "7", None])
def test_a_bad_provider_wait_is_a_failure(relay: Relay, wait: Any) -> None:
    relay.provider.start_answer = RateLimitedAnswer(wait)
    relay.provider.poll_answer = RateLimitedAnswer(wait)
    for sent in (start(relay), poll(relay)):
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)
        assert "retry-after" not in sent.headers


# --- an issued token must authenticate to its stated id -------------------------


def test_an_unissued_token_is_a_failure(relay: Relay) -> None:
    relay.provider.poll_answer = PollIssued(
        IssuedToken("a" * 16, "principal-1", ALL_A_TOKEN)
    )
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


def test_a_token_with_a_wrong_secret_is_a_failure(relay: Relay) -> None:
    real = relay.issue()
    forged = real.token[:-1] + ("b" if real.token[-1] != "b" else "c")
    assert relay.tokens.authenticate(real.token) is not None
    relay.provider.poll_answer = PollIssued(replace(real, token=forged))
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


def test_a_token_stated_with_another_tokens_id_is_a_failure(relay: Relay) -> None:
    first, second = relay.issue(), relay.issue()
    relay.provider.poll_answer = PollIssued(replace(first, token_id=second.token_id))
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


def test_a_token_stated_with_another_principal_is_a_failure(relay: Relay) -> None:
    first, second = relay.issue(), relay.issue()
    assert first.principal_id != second.principal_id
    relay.provider.poll_answer = PollIssued(
        replace(first, principal_id=second.principal_id)
    )
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


def test_a_revoked_token_is_a_failure(relay: Relay) -> None:
    issued = relay.issue()
    relay.provider.context.tokens.revoke(issued.token_id)
    relay.provider.poll_answer = PollIssued(issued)
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


@pytest.mark.parametrize("token", ["nonsense", "", None, 7])
def test_a_malformed_token_is_a_failure(relay: Relay, token: Any) -> None:
    issued = relay.issue()
    relay.provider.poll_answer = PollIssued(replace(issued, token=token))
    sent = poll(relay)
    assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)


# --- what the routes read -------------------------------------------------------


def email_of(length: int) -> str:
    local = "a" * 64
    domain = "d" * (length - len(local) - len("@") - len(".io")) + ".io"
    value = f"{local}@{domain}"
    assert len(value) == length
    return value


@pytest.mark.parametrize(
    "email",
    [
        EMAIL,
        "a@b.c",
        "a" * 64 + "@example.test",
        email_of(MAX_EMAIL_CHARS),
    ],
)
def test_start_reads_a_valid_email(relay: Relay, email: str) -> None:
    sent = start(relay, email)
    assert sent.status_code == 403
    assert relay.provider.started == [email]


@pytest.mark.parametrize(
    "email",
    [
        "a" * 65 + "@example.test",
        email_of(MAX_EMAIL_CHARS + 1),
        "no-at-sign.example",
        "two@@example.test",
        "a@b@example.test",
        "@example.test",
        "a@nodot",
        "a b@example.test",
        "a@exa mple.test",
        "a@example.test\n",
        "",
        None,
        42,
        ["a@example.test"],
    ],
)
def test_start_refuses_anything_that_is_not_an_email(relay: Relay, email: Any) -> None:
    sent = start(relay, email)
    assert (sent.status_code, sent.content) == (400, MALFORMED_BYTES)
    assert relay.provider.started == []


@pytest.mark.parametrize("secret", GOOD_SECRETS)
def test_poll_reads_a_valid_poll_secret(relay: Relay, secret: str) -> None:
    sent = poll(relay, secret)
    assert sent.status_code == 200
    assert relay.provider.polled == [secret]


@pytest.mark.parametrize("secret", [*BAD_SECRETS, None, 12345, ["a" * 32]])
def test_poll_refuses_anything_that_is_not_a_poll_secret(
    relay: Relay, secret: Any
) -> None:
    sent = poll(relay, secret)
    assert (sent.status_code, sent.content) == (400, MALFORMED_BYTES)
    assert relay.provider.polled == []


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"[]",
        b"{}",
        b'{"email":"a@b.c","poll_secret":"' + b"a" * 32 + b'"}',
        b'{"email":"a@b.c","extra":1}',
        b'{"poll_secret":"' + b"a" * 32 + b'"}',
        b'{"email":"a@b.c","email":"a@b.c"}',
    ],
)
def test_start_reads_exactly_an_email_field(relay: Relay, body: bytes) -> None:
    client = relay.client()
    sent = client.post(START_PATH, content=body)
    assert (sent.status_code, sent.content) == (400, MALFORMED_BYTES)
    assert relay.provider.started == []


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"{}",
        b'{"email":"a@b.c"}',
        b'{"poll_secret":"' + b"a" * 32 + b'","email":"a@b.c"}',
        b'{"poll_secret":"' + b"a" * 32 + b'","extra":null}',
    ],
)
def test_poll_reads_exactly_a_poll_secret_field(relay: Relay, body: bytes) -> None:
    client = relay.client()
    sent = client.post(POLL_PATH, content=body)
    assert (sent.status_code, sent.content) == (400, MALFORMED_BYTES)
    assert relay.provider.polled == []


def test_an_oversized_body_is_request_too_large_and_never_reaches_the_provider(
    relay: Relay,
) -> None:
    body = b'{"email":"' + b"a" * MAX_REQUEST_BYTES + b'@b.c"}'
    client = relay.client()
    sent = client.post(START_PATH, content=body)
    assert (sent.status_code, sent.content) == (413, envelope("request-too-large"))
    assert relay.provider.started == []


# --- limits ---------------------------------------------------------------------


def test_registration_requests_are_counted_per_client_before_the_provider_runs(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(client_limit=4)
    relay.provider.start_answer = accepted()
    first = [start(relay), poll(relay), start(relay, "not an email")]
    assert [s.status_code for s in first] == [200, 200, 400]
    assert relay.counts() == {client_key(CLIENT[0]): 3}
    fourth = start(relay)
    fifth = poll(relay)
    sixth = start(relay)
    assert fourth.status_code == 200
    assert [(s.status_code, s.content) for s in (fifth, sixth)] == [
        (429, limited(WINDOW_S))
    ] * 2
    assert fifth.headers["retry-after"] == str(WINDOW_S)
    assert relay.provider.started == [EMAIL, EMAIL]  # not run once over the limit
    assert relay.provider.polled == [POLL_SECRET]
    other = relay.client(OTHER_CLIENT)
    elsewhere = other.post(START_PATH, content=encode_request({"email": EMAIL}))
    assert elsewhere.status_code == 200


@pytest.mark.parametrize(
    ("path", "bodies"),
    [
        (START_PATH, [b"not json", b'{"email":"a@b.c","extra":1}']),
        (POLL_PATH, [b"{}", b'{"poll_secret":"' + b"a" * 32 + b'","extra":1}']),
    ],
)
def test_malformed_bodies_are_counted_against_the_client_before_they_are_read(
    make_relay: Callable[..., Relay], path: str, bodies: list[bytes]
) -> None:
    relay = make_relay(client_limit=2)
    client = relay.client()
    sent = [client.post(path, content=body) for body in bodies]
    assert [(s.status_code, s.content) for s in sent] == [(400, MALFORMED_BYTES)] * 2
    assert relay.counts() == {client_key(CLIENT[0]): 2}
    over = client.post(path, content=bodies[0])
    assert (over.status_code, over.content) == (429, limited(WINDOW_S))
    assert relay.provider.started == [] and relay.provider.polled == []


def test_registration_requests_share_the_clients_count_with_capabilities(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(client_limit=2)
    client = relay.client()
    client.get("/v1/capabilities")
    sent = client.post(START_PATH, content=encode_request({"email": EMAIL}))
    over = client.get("/v1/capabilities")
    assert sent.status_code == 403
    assert over.status_code == 429
    assert relay.counts() == {client_key(CLIENT[0]): 3}


def test_a_provider_that_limits_does_not_use_up_the_relays_own_limit(
    make_relay: Callable[..., Relay],
) -> None:
    relay = make_relay(client_limit=2)
    relay.provider.start_answer = RateLimitedAnswer(9)
    assert start(relay).content == limited(9)
    assert relay.counts() == {client_key(CLIENT[0]): 1}


# --- a failing provider ---------------------------------------------------------


def test_a_provider_that_raises_is_a_failure(relay: Relay) -> None:
    relay.provider.raises = RuntimeError("secret provider text")
    for sent in (start(relay), poll(relay)):
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES)
        assert b"secret provider text" not in sent.content


def invalid_answers(relay: Relay) -> list[tuple[str, Any]]:
    """Every kind of invalid provider answer: (route, answer)."""
    bad_waits: list[Any] = [-1, True, 1.5, "7", None]
    bad_tokens: list[Any] = ["nonsense", "", None, 7]
    first, second = relay.issue(), relay.issue()
    revoked = relay.issue()
    relay.provider.context.tokens.revoke(revoked.token_id)
    wrong_secret = first.token[:-1] + ("b" if first.token[-1] != "b" else "c")
    starts: list[Any] = [
        *[a for a in all_poll_answers(relay) if not isinstance(a, RateLimitedAnswer)],
        None,
        "registration-started",
        object(),
        accepted(user_code="ACDF-GHJK"),
        accepted(poll_secret="a" * 31),
        accepted(interval_s=MAX_POLL_INTERVAL_S + 1),
        accepted(interval_s=True),
        accepted(expires_in_s=MIN_EXPIRES_IN_S - 1),
        accepted(expires_in_s=MAX_EXPIRES_IN_S + 1),
        accepted(user_code=None),
        *[RateLimitedAnswer(w) for w in bad_waits],
    ]
    polls: list[Any] = [
        accepted(),
        StartRefused(),
        None,
        object(),
        *[RateLimitedAnswer(w) for w in bad_waits],
        PollIssued(IssuedToken("a" * 16, "p", ALL_A_TOKEN)),
        PollIssued(first.token),  # type: ignore[arg-type]
        PollIssued(None),  # type: ignore[arg-type]
        PollIssued(replace(first, token_id=second.token_id)),
        PollIssued(replace(first, principal_id=second.principal_id)),
        PollIssued(revoked),
        PollIssued(replace(first, token=wrong_secret)),
        *[PollIssued(replace(first, token=t)) for t in bad_tokens],
    ]
    return [("start", a) for a in starts] + [("poll", a) for a in polls]


def test_every_invalid_answer_is_logged_as_a_provider_answer_error(
    relay: Relay,
) -> None:
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password="registration-db-passw0rd", stream=out)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cases = invalid_answers(relay)
    assert len(cases) == 40
    seen: list[tuple[str, str, object]] = []
    for route, given in cases:
        if route == "start":
            relay.provider.start_answer = given
            sent = start(relay)
        else:
            relay.provider.poll_answer = given
            sent = poll(relay)
        assert (sent.status_code, sent.content) == (500, FAILURE_BYTES), (route, given)
        last = json.loads(out.getvalue().splitlines()[-1])
        seen.append((route, last["code"], last["error_type"]))
    assert seen == [
        (route, "relay-failure", "ProviderAnswerError") for route, _ in cases
    ]


# --- the logs -------------------------------------------------------------------


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_no_email_or_poll_secret_reaches_any_log(relay: Relay) -> None:
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password="registration-db-passw0rd", stream=out)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    capture = Capture()
    logging.getLogger().addHandler(capture)
    secret_in_failure = "Zz9-planted-provider-secret_Aa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8Ii9"
    issued = relay.issue()
    leaked_secret = "Qq8-leaked_poll_secret-Xx7Ww6Vv5Uu4Tt3Ss2Rr1Pp0Oo9Nn"
    try:
        client = relay.client()
        relay.provider.start_answer = accepted()
        client.post(START_PATH, content=encode_request({"email": EMAIL}))
        client.post(START_PATH, content=encode_request({"email": "x" + EMAIL}))
        client.post(START_PATH, content=encode_request({"email": EMAIL + "!"}))
        relay.provider.start_answer = accepted(user_code="ACDF-GHJK")
        client.post(START_PATH, content=encode_request({"email": EMAIL}))
        relay.provider.start_answer = accepted(poll_secret=leaked_secret + "=")
        client.post(START_PATH, content=encode_request({"email": EMAIL}))
        relay.provider.poll_answer = PollIssued(issued)
        client.post(POLL_PATH, content=encode_request({"poll_secret": POLL_SECRET}))
        relay.provider.poll_answer = PollIssued(IssuedToken("a" * 16, "p", ALL_A_TOKEN))
        client.post(POLL_PATH, content=encode_request({"poll_secret": POLL_SECRET}))
        client.post(POLL_PATH, content=encode_request({"poll_secret": "short"}))
        relay.provider.raises = RuntimeError(f"{EMAIL} {secret_in_failure}")
        client.post(START_PATH, content=encode_request({"email": EMAIL}))
        client.post(POLL_PATH, content=encode_request({"poll_secret": POLL_SECRET}))
    finally:
        logging.getLogger().removeHandler(capture)
    text = out.getvalue()
    records = [json.loads(line) for line in text.splitlines()]
    requests = [r for r in records if r["event"] == "request"]
    registration = [r for r in requests if str(r["route"]).startswith(START_PATH)]
    assert len(registration) == 10  # the scenario ran: every request logged once
    raw_dump = "\n".join(
        f"{r.getMessage()}|{sorted(r.__dict__.items(), key=str)}"
        for r in capture.records
    )
    assert "request" in raw_dump  # the raw records are non-trivial
    for planted in (
        EMAIL,
        POLL_SECRET,
        leaked_secret,
        secret_in_failure,
        issued.token,
        "ACDF-GHJK",
    ):
        assert planted not in text, planted
        assert planted not in raw_dump, planted
    failures = [r for r in registration if r["code"] == "relay-failure"]
    assert len(failures) == 5
    assert {r["error_type"] for r in failures} == {
        "ProviderAnswerError",
        "RuntimeError",
    }
    for record in failures:
        assert record["status"] == 500
        assert record["frames"]
        assert set(record["frames"][0]) == {"file", "line", "function"}
