"""The relay pipeline extended for targets (strava-publish 4.1).

Capabilities listing only configured targets, the Strava services built from
configuration, the per-route body limit, the closed outcome vocabulary on an
answer, the outcome on the request record, and the secrets the log filter
redacts when a target is configured.
"""

from __future__ import annotations

import ast
import base64
import io
import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from tests.conformance.state_support import raw
from tests.strava.scripted_strava import ScriptedOutbound, UnscriptedCall, reply
from tests.strava.test_publish import API, FACTS, LIST_URL
from tests.strava.test_publish_upload import FIT, STATUS_URL, UPLOAD_ID, UPLOAD_URL
from tests.test_config_strava import KEY_ONE, KEY_TWO, SECRET, TOKEN
from tests.test_config_strava import env as strava_env

from fitdocs_relay import routes as routes_module
from fitdocs_relay import serve
from fitdocs_relay.answers import answer, read_request
from fitdocs_relay.app import (
    RelayServices,
    StravaServices,
    build_app,
    create_app,
    make_services,
)
from fitdocs_relay.config import RelayConfig, load_config
from fitdocs_relay.crypto import Keyring, parse_keys
from fitdocs_relay.identity import TokenService
from fitdocs_relay.logs import configure_logging
from fitdocs_relay.ratelimit import RateLimiter
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import (
    MAX_REQUEST_BYTES,
    SERVED_ENVELOPES,
    CapabilitiesData,
    decode_answer,
    encode_request,
    parse_capabilities,
)
from fitdocs_relay.shared.relay_targets import (
    ACTION_UPLOAD,
    MAX_DESCRIPTION_CHARS,
    MAX_FIT_BYTES,
    MAX_TITLE_CHARS,
    MAX_UPLOAD_REQUEST_BYTES,
    STRAVA,
    PublishFacts,
    target_route,
    upload_fields,
)
from fitdocs_relay.storage.interface import (
    NewConnection,
    NewPrincipal,
    SealedTokens,
    Storage,
)
from fitdocs_relay.strava import cli as strava_cli
from fitdocs_relay.strava import webhook as webhook_module
from fitdocs_relay.strava.api import Grant, StravaApi
from fitdocs_relay.strava.budget import SHORT_WINDOW_S, StravaBudget
from fitdocs_relay.strava.connect import CONNECT_EXPIRES_IN_S, ConnectFlow, ShowConsent
from fitdocs_relay.strava.custody import (
    LEASE_POLL_S,
    LEASE_S,
    Custody,
    Usable,
    account_key,
)
from fitdocs_relay.strava.custody import context as seal_context
from fitdocs_relay.strava.publish import UPLOAD_POLL_INTERVAL_S, Landed, StravaPublisher
from fitdocs_relay.strava.webhook import Webhook

UPLOAD_PATH = "/v1/targets/strava/upload"
MIB = 1024 * 1024


def clock() -> int:
    return 1_700_000_040


def config_for(database: Any, *, strava: bool) -> RelayConfig:
    environ = (
        strava_env()
        if strava
        else {
            "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
            "FITDOCS_RELAY_TOKEN_PEPPER": "p" * 43,
        }
    )
    return replace(load_config(environ), database=database)


@pytest.fixture
def outbound() -> ScriptedOutbound:
    return ScriptedOutbound()


@pytest.fixture
def make_app(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> Callable[..., TestClient]:
    def make(*, strava: bool, scripted: ScriptedOutbound | None = None) -> TestClient:
        app = create_app(
            config_for(database_target, strava=strava),
            storage=open_full_storage(),
            clock=clock,
            outbound=scripted,
        )
        return TestClient(app, client=("203.0.113.9", 4711))

    return make


# --- capabilities -----------------------------------------------------------


def targets_listed(client: TestClient) -> tuple[str, ...]:
    with client:
        sent = client.get("/v1/capabilities")
    assert sent.status_code == 200
    data = parse_capabilities(decode_answer(sent.content).data)
    assert data == CapabilitiesData(
        envelopes=SERVED_ENVELOPES, registration=False, targets=data.targets
    )
    return data.targets


def test_capabilities_list_no_target_without_the_strava_configuration(
    make_app: Callable[..., TestClient],
) -> None:
    assert routes_module.OFFERED_TARGETS == ("strava",)  # the decoy is on offer
    assert targets_listed(make_app(strava=False)) == ()


def test_capabilities_list_strava_with_the_strava_configuration(
    make_app: Callable[..., TestClient],
) -> None:
    assert targets_listed(make_app(strava=True)) == ("strava",)


def test_the_route_table_constants_are_the_designed_literals() -> None:
    assert routes_module.RESERVED_PREFIXES == (
        "/v",
        "/livez",
        "/readyz",
        "/x/",
        "/connect/",
        "/strava/",
        "/go/",
        "/privacy",
        "/robots.txt",
    )
    assert routes_module.ROUTE_BODY_LIMITS == {UPLOAD_PATH: 22 * MIB}
    assert target_route(STRAVA, ACTION_UPLOAD) == UPLOAD_PATH


# --- the services -----------------------------------------------------------


def services_for(
    database: Any,
    store: Storage,
    *,
    strava: bool,
    scripted: ScriptedOutbound,
) -> RelayServices:
    return make_services(
        config_for(database, strava=strava),
        store,
        clock=clock,
        outbound=scripted,
        monotonic=lambda: 0.0,
        sleep=lambda seconds: None,
    )


def test_no_strava_services_are_built_without_the_configuration(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    services = services_for(
        database_target, open_full_storage(), strava=False, scripted=outbound
    )
    assert services.strava is None
    assert services.targets == ()


def test_the_strava_services_are_built_from_the_configuration(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    services = services_for(
        database_target, open_full_storage(), strava=True, scripted=outbound
    )
    assert services.targets == ("strava",)
    strava = services.strava
    assert isinstance(strava, StravaServices)
    assert strava.config.client_id == "12345"
    assert isinstance(strava.api, StravaApi)
    assert isinstance(strava.budget, StravaBudget)
    assert isinstance(strava.custody, Custody)
    assert isinstance(strava.publisher, StravaPublisher)
    assert isinstance(strava.connect, ConnectFlow)
    assert isinstance(strava.webhook, Webhook)
    assert strava.operator.name == "Example Operator"
    assert strava.operator.support_contact == "help@example.org"
    assert strava.operator.policy_url is None
    # The api speaks through the injected outbound: its request lands there.
    assert outbound.calls == []
    with pytest.raises(UnscriptedCall):
        strava.api.delete_subscription(timeout=1.0)
    assert len(outbound.calls) == 1


def test_the_operator_carries_the_configured_policy_address(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    config = replace(
        load_config(
            strava_env(
                {"FITDOCS_RELAY_PRIVACY_POLICY_URL": "https://policy.example.org/p"}
            )
        ),
        database=database_target,
    )
    services = make_services(
        config, open_full_storage(), clock=clock, outbound=outbound
    )
    assert services.strava is not None
    assert services.strava.operator.policy_url == "https://policy.example.org/p"


# --- the services are wired from the configuration and the injected parts ----

DAY = 86_400
ATHLETE = "90210123"


def built(
    database: Any,
    store: Storage,
    scripted: ScriptedOutbound,
    *,
    changes: dict[str, str] | None = None,
    now: Callable[[], int] = clock,
    monotonic: Callable[[], float] = lambda: 0.0,
    sleep: Callable[[float], None] = lambda seconds: None,
) -> StravaServices:
    config = replace(load_config(strava_env(changes)), database=database)
    services = make_services(
        config, store, clock=now, outbound=scripted, monotonic=monotonic, sleep=sleep
    )
    assert services.strava is not None
    return services.strava


def with_principal(store: Storage, principal: str = "ann") -> Storage:
    store.create_principal(NewPrincipal(principal, None), now=1)
    return store


class Stepping:
    """A monotonic clock that moves one second per reading, so a loop that
    reads it ends; it fails the test after too many readings."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.readings = 0

    def __call__(self) -> float:
        self.readings += 1
        assert self.readings < 200, "the monotonic clock is being polled forever"
        self.now += 1.0
        return self.now - 1.0


class Sleeps:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)
        assert len(self.slept) < 100, "the sleep is being called forever"


def test_the_built_webhook_answers_a_validation_with_the_configured_token_only(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    strava = built(
        database_target,
        open_full_storage(),
        outbound,
        changes={"FITDOCS_RELAY_STRAVA_CLIENT_SECRET": SECRET},
    )
    assert SECRET != TOKEN  # the decoy: the client secret is another value
    assert strava.webhook.validate("subscribe", "c", TOKEN) == {"hub.challenge": "c"}
    assert strava.webhook.validate("subscribe", "c", SECRET) is None


def test_the_built_connect_page_names_the_configured_public_address(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    strava = built(database_target, open_full_storage(), outbound)
    started = strava.connect.start("ann")
    shown = strava.connect.page(started.user_code, None)
    assert isinstance(shown, ShowConsent)
    query = parse_qs(urlsplit(shown.authorize_url).query)
    assert query["redirect_uri"] == ["https://relay.example.org/strava/callback"]


def test_a_built_connect_session_expires_by_the_injected_clock(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = open_full_storage()
    strava = built(database_target, store, outbound)
    started = strava.connect.start("ann")
    raw = store.get_record(
        namespace="core.connect", key=f"session:{started.user_code}", now=clock()
    )
    assert raw is not None
    assert json.loads(raw)["expires_at"] == clock() + CONNECT_EXPIRES_IN_S
    assert clock() < time.time() - DAY  # the injected clock is not the wall clock


def test_the_built_custody_reads_a_token_sealed_under_the_second_key(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    strava = built(
        database_target,
        store,
        outbound,
        changes={"FITDOCS_RELAY_ENCRYPTION_KEYS": f"{KEY_ONE},{KEY_TWO}"},
    )
    second = Keyring(parse_keys(KEY_TWO))
    store.put_connection(
        NewConnection(
            "ann",
            STRAVA,
            "account",
            SealedTokens(
                second.seal("access", context=seal_context("ann", "access")),
                second.seal("refresh", context=seal_context("ann", "refresh")),
                clock() + DAY,
            ),
        ),
        now=1,
    )
    # Written under k2, which is not the current key: one is re-sealed under k1.
    assert strava.custody.reencrypt_all() == (1, 0)
    resealed = store.get_connection("ann", STRAVA)
    assert resealed is not None
    assert (
        Keyring(parse_keys(KEY_ONE)).open(
            resealed.tokens.access, context=seal_context("ann", "access")
        )
        == "access"
    )


def test_the_built_custody_keys_the_account_hash_with_the_configured_pepper(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    strava = built(database_target, store, outbound)
    strava.custody.store_grant("ann", Grant("a", "r", clock() + DAY, ATHLETE))
    stored = store.get_connection("ann", STRAVA)
    assert stored is not None
    pepper = load_config(strava_env()).pepper
    assert stored.account_key == account_key(pepper, STRAVA, ATHLETE)
    assert stored.account_key != account_key(b"x" * 43, STRAVA, ATHLETE)


def test_the_built_custody_decides_expiry_and_stamps_rows_by_the_injected_clock(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    strava = built(database_target, store, outbound)
    # Not near expiry by the injected clock, long past by the wall clock.
    strava.custody.store_grant("ann", Grant("a", "r", clock() + DAY, ATHLETE))
    stored = store.get_connection("ann", STRAVA)
    assert stored is not None
    assert stored.created_at == clock()
    assert clock() + DAY < time.time()
    got = strava.custody.access_token("ann", deadline=10.0**9)
    assert got == Usable("ann", "a")
    assert outbound.calls == []


def test_the_built_custody_waits_on_the_injected_monotonic_clock_and_sleep(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    mono, sleeps = Stepping(), Sleeps()
    strava = built(database_target, store, outbound, monotonic=mono, sleep=sleeps)
    strava.custody.store_grant("ann", Grant("a", "r", clock() + 100, ATHLETE))
    held = store.get_connection("ann", STRAVA)
    assert held is not None
    assert store.claim_refresh(
        "ann",
        STRAVA,
        generation=held.generation,
        lease_id="another-holder",
        lease_until=clock() + LEASE_S,
        now=clock(),
    )
    got = strava.custody.access_token("ann", deadline=mono.now + 30)
    assert got is PublishCode.UNAVAILABLE
    # The wait's stop is five readings away: four polls, each sleeping one step.
    assert sleeps.slept == [LEASE_POLL_S] * 4
    assert outbound.calls == []


def test_the_built_budget_counts_its_windows_by_the_injected_clock(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    moment = [clock()]
    strava = built(
        database_target,
        store,
        outbound,
        changes={
            "FITDOCS_RELAY_STRAVA_RATE_LIMIT": "2,100",
            "FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT": "2,100",
        },
        now=lambda: moment[0],
    )
    assert strava.budget.spend("ann").allowed  # a principal holds half: one call
    assert not strava.budget.spend("ann").allowed
    moment[0] += 2 * SHORT_WINDOW_S
    assert strava.budget.spend("ann").allowed


def test_the_built_publisher_reads_its_deadline_from_the_injected_monotonic(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    readings = iter([1000.0])

    def monotonic() -> float:
        return next(readings, 10.0**9)  # the deadline is read once, then long past

    strava = built(database_target, store, outbound, monotonic=monotonic)
    strava.custody.store_grant("ann", Grant("a", "r", clock() + DAY, ATHLETE))
    facts = PublishFacts(
        publication_id="p" * 16,
        sport="Run",
        start=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        elapsed_s=1800.0,
        distance_m=5000.0,
        title="t",
        description="d",
    )
    assert strava.publisher.publish("ann", facts) is PublishCode.UNAVAILABLE
    assert outbound.calls == []


def test_the_built_publisher_polls_with_the_injected_sleep_and_stamps_by_its_clock(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    outbound: ScriptedOutbound,
) -> None:
    store = with_principal(open_full_storage())
    sleeps = Sleeps()
    strava = built(
        database_target,
        store,
        outbound,
        changes={"FITDOCS_RELAY_STRAVA_API_URL": API},
        sleep=sleeps,
    )
    strava.custody.store_grant("ann", Grant("a", "r", clock() + DAY, ATHLETE))
    outbound.expect("GET", LIST_URL, reply(200, []))
    status = {"id": UPLOAD_ID, "error": None}
    outbound.expect("POST", UPLOAD_URL, reply(201, status | {"activity_id": None}))
    outbound.expect(
        "GET",
        STATUS_URL,
        reply(200, status | {"activity_id": None}),
        reply(200, status | {"activity_id": 424242}),
    )
    landed = strava.publisher.upload("ann", FACTS, FIT)
    assert isinstance(landed, Landed) and landed.code is PublishCode.UPLOADED
    assert sleeps.slept == [UPLOAD_POLL_INTERVAL_S] * 2
    assert raw(database_target, "SELECT created_at FROM target_publications") == [
        (clock(),)
    ]


# --- the body limit, per route ----------------------------------------------


def body_limit_client(database: Any, store: Storage, *, strava: bool) -> TestClient:
    services = services_for(database, store, strava=strava, scripted=ScriptedOutbound())

    async def echo(request: Request) -> Response:
        fields = await read_request(
            request, required=frozenset({"a"}), allowed=frozenset({"a"})
        )
        if isinstance(fields, Response):
            return fields
        return answer(RelayCode.OK, {"size": len(str(fields["a"]))})

    app = build_app(
        services,
        [
            Route(UPLOAD_PATH, echo, methods=["POST"]),
            Route("/v1/other", echo, methods=["POST"]),
        ],
    )
    return TestClient(app)


def json_body(size: int) -> bytes:
    head, tail = b'{"a":"', b'"}'
    raw = head + b"x" * (size - len(head) - len(tail)) + tail
    assert len(raw) == size
    return raw


def test_the_lookup_gives_the_upload_route_its_bound_and_every_other_the_default() -> (
    None
):
    assert routes_module.body_limit(UPLOAD_PATH) == MAX_UPLOAD_REQUEST_BYTES
    assert routes_module.body_limit("/v1/other") == MAX_REQUEST_BYTES
    assert routes_module.body_limit(UPLOAD_PATH + "/") == MAX_REQUEST_BYTES
    assert routes_module.body_limit("/v1/targets/strava/publish") == MAX_REQUEST_BYTES
    assert MAX_UPLOAD_REQUEST_BYTES > MAX_REQUEST_BYTES


def test_the_upload_route_reads_a_body_the_default_would_refuse(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    size = MAX_REQUEST_BYTES + 1024
    with body_limit_client(database_target, open_full_storage(), strava=True) as client:
        sent = client.post(UPLOAD_PATH, content=json_body(size))
    assert sent.status_code == 200
    assert json.loads(sent.content)["data"] == {"size": size - len('{"a":""}')}


def test_the_upload_route_refuses_a_body_over_its_own_bound(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    exact = MAX_UPLOAD_REQUEST_BYTES
    with body_limit_client(database_target, open_full_storage(), strava=True) as client:
        at_bound = client.post(UPLOAD_PATH, content=json_body(exact))
        over = client.post(UPLOAD_PATH, content=json_body(exact + 1))
    assert at_bound.status_code == 200
    assert over.status_code == 413
    assert decode_answer(over.content).code is RelayCode.REQUEST_TOO_LARGE


def test_a_chunked_upload_body_is_bounded_by_the_upload_route_too(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    def sent_in_chunks(client: TestClient, size: int) -> Any:
        raw = json_body(size)

        def chunks() -> Iterator[bytes]:
            for start in range(0, len(raw), 65536):
                yield raw[start : start + 65536]

        request = client.build_request("POST", UPLOAD_PATH, content=chunks())
        assert "content-length" not in request.headers
        return client.send(request)

    with body_limit_client(database_target, open_full_storage(), strava=True) as client:
        within = sent_in_chunks(client, MAX_REQUEST_BYTES + 1024)
        over = sent_in_chunks(client, MAX_UPLOAD_REQUEST_BYTES + 1)
    assert within.status_code == 200
    assert over.status_code == 413


def test_every_other_route_keeps_the_default_bound(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    with body_limit_client(database_target, open_full_storage(), strava=True) as client:
        at_bound = client.post("/v1/other", content=json_body(MAX_REQUEST_BYTES))
        over = client.post("/v1/other", content=json_body(MAX_REQUEST_BYTES + 1))
    assert at_bound.status_code == 200
    assert over.status_code == 413


def test_without_the_strava_target_the_upload_path_keeps_the_default_bound(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    with body_limit_client(
        database_target, open_full_storage(), strava=False
    ) as client:
        sent = client.post(UPLOAD_PATH, content=json_body(MAX_REQUEST_BYTES + 1))
    assert sent.status_code == 413


def test_the_reader_alone_applies_the_route_bound_to_the_codec(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    # Between the two bounds the admission stage lets the body through, so only
    # the reader can still refuse it.
    size = MAX_REQUEST_BYTES + 1
    assert size < MAX_UPLOAD_REQUEST_BYTES
    with body_limit_client(database_target, open_full_storage(), strava=True) as client:
        sent = client.post(UPLOAD_PATH, content=json_body(size))
    assert decode_answer(sent.content).code is RelayCode.OK


def largest_upload_body() -> bytes:
    four_byte = "\U0001f600"
    facts = PublishFacts(
        publication_id="a" * 32,
        sport="Workout",
        start=datetime.fromisoformat("2026-01-01T00:00:00+14:00"),
        elapsed_s=1e300,
        distance_m=1e300,
        title=four_byte * MAX_TITLE_CHARS,
        description=four_byte * MAX_DESCRIPTION_CHARS,
    )
    fit = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT" + b"\xff" * (MAX_FIT_BYTES - 12)
    assert len(fit) == MAX_FIT_BYTES
    return encode_request(upload_fields(facts, fit), max_bytes=MAX_UPLOAD_REQUEST_BYTES)


def test_the_largest_valid_upload_fits_the_upload_bound_and_not_the_default() -> None:
    body = largest_upload_body()
    assert MAX_REQUEST_BYTES < len(body) <= MAX_UPLOAD_REQUEST_BYTES
    assert len(body) > MAX_UPLOAD_REQUEST_BYTES - 2 * MIB  # not a trivially small case


def test_the_largest_valid_upload_travels_through_the_upload_route(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> None:
    body = largest_upload_body()
    store = open_full_storage()
    services = services_for(
        database_target, store, strava=True, scripted=ScriptedOutbound()
    )

    async def take(request: Request) -> Response:
        fields = await read_request(
            request,
            required=frozenset(),
            allowed=frozenset(
                {"publication_id", "sport", "start", "elapsed_s", "distance_m"}
                | {"title", "description", "fit"}
            ),
        )
        if isinstance(fields, Response):
            return fields
        return answer(RelayCode.OK, {"fields": len(fields)})

    app = build_app(services, [Route(UPLOAD_PATH, take, methods=["POST"])])
    with TestClient(app) as client:
        sent = client.post(UPLOAD_PATH, content=body)
    assert sent.status_code == 200
    assert json.loads(sent.content)["data"] == {"fields": 8}


# --- the outcome vocabulary and the request record -------------------------------


@pytest.fixture
def outcome_client(
    open_full_storage: Callable[[], Storage],
) -> Iterator[Callable[[str | None], TestClient]]:
    store = open_full_storage()
    pepper = b"o" * 43
    services = RelayServices(
        storage=store,
        tokens=TokenService(store, pepper=pepper, clock=clock),
        limiter=RateLimiter(
            store, pepper=pepper, clock=clock, token_limit=60, client_limit=20
        ),
        clock=clock,
        registration=None,
        ready=False,
    )

    def make(outcome: str | None) -> TestClient:
        def handler(request: Request) -> Response:
            return answer(RelayCode.OK, outcome=outcome)

        return TestClient(build_app(services, [Route("/v1/x", handler)]))

    yield make


@pytest.mark.parametrize("member", [code.value for code in PublishCode])
def test_every_member_of_the_pinned_vocabulary_is_an_answerable_outcome(
    member: str, outcome_client: Callable[[str | None], TestClient]
) -> None:
    with outcome_client(member) as client:
        sent = client.get("/v1/x")
    assert sent.status_code == 200
    assert decode_answer(sent.content).outcome == member


@pytest.mark.parametrize(
    "outcome",
    ["rate-limited", "POSTED", "posted ", "", "made_up", "ok", "relay-failure"],
)
def test_a_non_member_outcome_cannot_be_built(outcome: str) -> None:
    with pytest.raises(ValueError):
        answer(RelayCode.OK, outcome=outcome)


def test_a_non_member_outcome_answers_relay_failure(
    outcome_client: Callable[[str | None], TestClient],
) -> None:
    with outcome_client("rate-limited") as client:
        client.raise_server_exceptions = False
        sent = client.get("/v1/x")
    assert sent.status_code == 500
    decoded = decode_answer(sent.content)
    assert decoded.code is RelayCode.RELAY_FAILURE
    assert decoded.outcome is None


def request_records(stream: io.StringIO) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    return [line for line in lines if line["event"] == "request"]


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    stream = io.StringIO()
    configure_logging(pepper="p" * 43, password=None, stream=stream)
    yield stream
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])


def test_the_request_record_carries_the_outcome_when_the_answer_has_one(
    outcome_client: Callable[[str | None], TestClient], log_stream: io.StringIO
) -> None:
    with outcome_client("uploaded") as client:
        client.get("/v1/x")
    (record,) = request_records(log_stream)
    assert record["outcome"] == "uploaded"
    assert record["code"] == "ok"


def test_the_request_record_has_no_outcome_when_the_answer_has_none(
    outcome_client: Callable[[str | None], TestClient], log_stream: io.StringIO
) -> None:
    with outcome_client(None) as client:
        client.get("/v1/x")
    (record,) = request_records(log_stream)
    assert "outcome" not in record


def test_a_refused_outcome_is_not_recorded_as_the_requests_outcome(
    outcome_client: Callable[[str | None], TestClient], log_stream: io.StringIO
) -> None:
    with outcome_client("rate-limited") as client:
        client.raise_server_exceptions = False
        client.get("/v1/x")
    (record,) = request_records(log_stream)
    assert "outcome" not in record
    assert record["code"] == "relay-failure"
    assert record["error_type"] == "ValueError"


# --- the log filter ----------------------------------------------------------


def key_text(entry: str) -> str:
    return entry.split(":", 1)[1]


def test_the_secrets_to_redact_are_the_configured_target_secrets() -> None:
    environ = strava_env(
        {
            "FITDOCS_RELAY_STRAVA_CLIENT_SECRET": SECRET,
            "FITDOCS_RELAY_ENCRYPTION_KEYS": f"{KEY_ONE},{KEY_TWO}",
        }
    )
    config = load_config(environ)
    found = serve.target_secrets(config)
    assert set(found) == {
        SECRET,
        TOKEN,
        key_text(KEY_ONE),
        key_text(KEY_TWO),
        KEY_ONE,
        KEY_TWO,
    }
    assert len(found) == len(set(found))
    assert serve.target_secrets(load_config(strava_env(without=_STRAVA_ONLY))) == ()


_STRAVA_ONLY = (
    "FITDOCS_RELAY_STRAVA_CLIENT_ID",
    "FITDOCS_RELAY_STRAVA_CLIENT_SECRET",
    "FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN",
    "FITDOCS_RELAY_PUBLIC_URL",
    "FITDOCS_RELAY_ENCRYPTION_KEYS",
    "FITDOCS_RELAY_OPERATOR_NAME",
    "FITDOCS_RELAY_SUPPORT_CONTACT",
)


def test_the_key_text_is_the_unpadded_base64url_of_the_key_material() -> None:
    config = load_config(strava_env({"FITDOCS_RELAY_ENCRYPTION_KEYS": KEY_TWO}))
    assert config.targets is not None
    (key,) = config.targets.keys
    assert base64.urlsafe_b64encode(key.material).decode().rstrip("=") == key_text(
        KEY_TWO
    )
    assert key_text(KEY_TWO) in serve.target_secrets(config)


def test_run_server_registers_the_target_secrets_with_the_log_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def spy(**kwargs: Any) -> logging.Handler:
        seen.update(kwargs)
        raise RuntimeError("stop after logging is configured")

    monkeypatch.setattr(serve, "configure_logging", spy)
    config = load_config(strava_env({"FITDOCS_RELAY_STRAVA_CLIENT_SECRET": SECRET}))
    with pytest.raises(RuntimeError, match="stop after logging"):
        serve.run_server(config)
    assert {SECRET, TOKEN, key_text(KEY_ONE)} <= set(seen["extra_secrets"])


def test_a_planted_client_secret_is_absent_from_captured_logs() -> None:
    config = load_config(
        strava_env(
            {
                "FITDOCS_RELAY_STRAVA_CLIENT_SECRET": SECRET,
                "FITDOCS_RELAY_ENCRYPTION_KEYS": KEY_ONE,
            }
        )
    )
    stream = io.StringIO()
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    try:
        configure_logging(
            pepper=config.pepper,
            password=None,
            extra_secrets=serve.target_secrets(config),
            stream=stream,
        )
        logger = logging.getLogger("fitdocs_relay.test")
        logger.error("client secret %s", SECRET)
        logger.error("webhook /strava/webhook/%s", TOKEN)
        logger.error("keys %s and %s", KEY_ONE, key_text(KEY_ONE))
        logger.error("planted", extra={"event": "planted", "route": SECRET})
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
    text = stream.getvalue()
    assert text.count("[redacted]") >= 5
    for secret in (SECRET, TOKEN, KEY_ONE, key_text(KEY_ONE)):
        assert secret not in text


# --- the webhook path --------------------------------------------------------


def test_the_webhook_path_is_defined_by_the_webhook_module_alone() -> None:
    assert webhook_module.WEBHOOK_PATH == "/strava/webhook"
    config = load_config(strava_env())
    assert config.targets is not None and config.strava is not None
    assert strava_cli.webhook_callback(config.targets, config.strava) == (
        f"https://relay.example.org/strava/webhook/{TOKEN}"
    )
    cli_source = Path(strava_cli.__file__).read_text(encoding="utf-8")
    assigned = [
        node
        for node in ast.walk(ast.parse(cli_source))
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "WEBHOOK_PATH"
    ]
    assert assigned == []
