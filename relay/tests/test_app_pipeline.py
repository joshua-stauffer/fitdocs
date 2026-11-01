"""The request pipeline: envelope answers, the stages in front of the routes, and
the one secret-free log record per request (Requirements 4.1, 4.5, 4.6, 4.7,
4.8, 4.10, 9.9)."""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import logging
import re
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import BaseRoute, Route
from starlette.testclient import TestClient

from fitdocs_relay import app as app_module
from fitdocs_relay import routes
from fitdocs_relay.answers import (
    answer,
    bearer_token,
    client_address,
    note_token_id,
    read_request,
)
from fitdocs_relay.app import RelayApp, RelayServices, build_app, create_app
from fitdocs_relay.config import RelayConfig, SqliteTarget
from fitdocs_relay.identity import Authenticated, TokenService
from fitdocs_relay.logs import configure_logging
from fitdocs_relay.ratelimit import RateLimiter
from fitdocs_relay.shared.relay_codes import RELAY_CODES, CodeOrigin, RelayCode
from fitdocs_relay.shared.relay_envelope import (
    MAX_REQUEST_BYTES,
    EnvelopeError,
    decode_answer,
)
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import Storage, StorageUnreachable

PEPPER = "pipeline-pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAeQ"
PASSWORD = "pipeline-db-passw0rd"
TOKEN = "fdr1_" + "abcdefghijklmnop" + "_" + "qrstuvwxyz234567" * 3 + "abcd"
CLIENT = ("203.0.113.9", 41234)
ASCII_TOKEN_SHAPED_METHOD = "FDR1_ABCDEFGHIJKLMNOP"


def body_of(code: str, data: str = "{}") -> bytes:
    return f'{{"envelope":1,"code":"{code}","data":{data}}}'.encode()


# --- the app under test -------------------------------------------------------


class Spy:
    """What the test routes saw."""

    def __init__(self) -> None:
        self.reached: list[str] = []


@pytest.fixture
def spy() -> Spy:
    return Spy()


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
def services(open_full_storage: Callable[[], Storage]) -> RelayServices:
    store = open_full_storage()
    pepper = PEPPER.encode()

    def clock() -> int:
        return 1_000

    return RelayServices(
        storage=store,
        tokens=TokenService(store, pepper=pepper, clock=clock),
        limiter=RateLimiter(
            store, pepper=pepper, clock=clock, token_limit=60, client_limit=20
        ),
        clock=clock,
        registration=None,
        ready=False,
    )


def make_routes(services: RelayServices, spy: Spy) -> list[BaseRoute]:
    def ok(request: Request) -> Response:
        spy.reached.append("ok")
        return answer(RelayCode.OK)

    def item(request: Request) -> Response:
        spy.reached.append("item")
        return answer(RelayCode.OK)

    async def echo(request: Request) -> Response:
        spy.reached.append("echo")
        fields = await read_request(
            request, required=frozenset({"a"}), allowed=frozenset({"a", "b"})
        )
        if isinstance(fields, Response):
            return fields
        return answer(RelayCode.OK, {"keys": sorted(fields)})

    def boom(request: Request) -> Response:
        spy.reached.append("boom")
        raise RuntimeError("message-with-a-secret " + TOKEN)

    def store(request: Request) -> Response:
        services.storage.ping()
        return answer(RelayCode.OK)

    def limited(request: Request) -> Response:
        return answer(RelayCode.RATE_LIMITED, retry_after_s=7)

    def client_code(request: Request) -> Response:
        return answer(RelayCode.RELAY_UNREACHABLE)

    def authed(request: Request) -> Response:
        note_token_id(request, "a" * 16)
        return answer(RelayCode.OK)

    def page(request: Request) -> Response:
        return PlainTextResponse("a page outside the envelope")

    def who(request: Request) -> Response:
        return answer(
            RelayCode.OK,
            {"address": client_address(request), "token": bearer_token(request)},
        )

    return [
        Route("/v1/ok", ok),
        Route("/v2/ok", ok),
        Route("/v1/items/{item_id}", item),
        Route("/v1/echo", echo, methods=["POST"]),
        Route("/v1/boom", boom),
        Route("/v1/store", store),
        Route("/v1/limited", limited),
        Route("/v1/client-code", client_code),
        Route("/v1/authed", authed),
        Route("/x/page", page),
        Route("/v1/who", who),
    ]


@pytest.fixture
def client(services: RelayServices, spy: Spy) -> Iterator[TestClient]:
    app = build_app(services, make_routes(services, spy))
    with TestClient(app, client=CLIENT) as test_client:
        yield test_client


# --- the answer helper --------------------------------------------------------

RELAY_ORIGIN = [c for c, i in RELAY_CODES.items() if i.origin is CodeOrigin.RELAY]
CLIENT_ORIGIN = [c for c, i in RELAY_CODES.items() if i.origin is CodeOrigin.CLIENT]


def test_the_vocabulary_has_both_origins() -> None:
    assert RELAY_ORIGIN and CLIENT_ORIGIN


@pytest.mark.parametrize("code", RELAY_ORIGIN)
def test_every_relay_code_answers_with_its_status_and_the_fixed_headers(
    code: RelayCode,
) -> None:
    response = answer(code)
    assert response.status_code == RELAY_CODES[code].http_status
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert "retry-after" not in response.headers
    assert decode_answer(bytes(response.body)).code is code


@pytest.mark.parametrize("code", CLIENT_ORIGIN)
def test_no_client_origin_code_can_be_emitted(code: RelayCode) -> None:
    with pytest.raises(EnvelopeError):
        answer(code)


def test_the_canonical_bytes_of_each_pipeline_answer() -> None:
    assert bytes(answer(RelayCode.OK).body) == body_of("ok")
    assert bytes(answer(RelayCode.NOT_OFFERED).body) == body_of("not-offered")
    assert bytes(answer(RelayCode.OK, {"x": [1, "é"]}).body) == (
        '{"envelope":1,"code":"ok","data":{"x":[1,"é"]}}'.encode()
    )
    assert bytes(answer(RelayCode.REGISTRATION_STARTED, outcome="sent").body) == (
        b'{"envelope":1,"code":"registration-started","data":{},"outcome":"sent"}'
    )


def test_rate_limited_carries_the_wait_in_data_and_in_a_header() -> None:
    response = answer(RelayCode.RATE_LIMITED, retry_after_s=7)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert bytes(response.body) == body_of("rate-limited", '{"retry_after_s":7}')


def test_rate_limited_without_a_stated_wait_states_none_not_zero() -> None:
    response = answer(RelayCode.RATE_LIMITED)
    assert "retry-after" not in response.headers
    assert bytes(response.body) == body_of("rate-limited")


@pytest.mark.parametrize(
    ("code", "wait"),
    [
        (RelayCode.OK, 5),
        (RelayCode.UNAVAILABLE, 5),
        (RelayCode.RATE_LIMITED, -1),
        (RelayCode.RATE_LIMITED, True),
    ],
)
def test_a_retry_wait_is_refused_off_rate_limited_or_when_not_a_count(
    code: RelayCode, wait: int
) -> None:
    with pytest.raises(ValueError):
        answer(code, retry_after_s=wait)


@pytest.mark.parametrize("code", [RelayCode.RATE_LIMITED, RelayCode.OK])
def test_a_wait_inside_the_data_is_refused_so_the_keyword_is_the_only_way(
    code: RelayCode,
) -> None:
    with pytest.raises(ValueError):
        answer(code, {"retry_after_s": 3})


def test_the_wait_cannot_be_stated_twice() -> None:
    with pytest.raises(ValueError):
        answer(RelayCode.RATE_LIMITED, {"retry_after_s": 1}, retry_after_s=2)


# --- bearer token and client address -----------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (f"Bearer {TOKEN}", TOKEN),
        (f"bearer {TOKEN}", TOKEN),
        (f"BEARER {TOKEN}", TOKEN),
        (f"Basic {TOKEN}", None),
        (TOKEN, None),
        ("Bearer", None),
        ("Bearer ", None),
        ("", None),
    ],
)
def test_bearer_token(client: TestClient, header: str, expected: str | None) -> None:
    sent = client.get("/v1/who", headers={"Authorization": header})
    assert json.loads(sent.content)["data"]["token"] == expected


def test_no_authorization_header_is_no_token(client: TestClient) -> None:
    assert json.loads(client.get("/v1/who").content)["data"]["token"] is None


def test_the_client_address_is_the_connection_peer_and_ignores_forwarding_headers(
    client: TestClient,
) -> None:
    sent = client.get(
        "/v1/who",
        headers={"X-Forwarded-For": "198.51.100.1", "Forwarded": "for=198.51.100.2"},
    )
    assert json.loads(sent.content)["data"]["address"] == CLIENT[0]


def test_no_peer_means_no_address() -> None:
    request = Request({"type": "http", "headers": [], "client": None})
    assert client_address(request) is None
    assert client_address(Request({"type": "http", "headers": []})) is None


# --- the strict request reader (no pipeline in front) -------------------------


def reader_client() -> TestClient:
    async def echo(request: Request) -> Response:
        fields = await read_request(
            request, required=frozenset({"a"}), allowed=frozenset({"a", "b"})
        )
        if isinstance(fields, Response):
            return fields
        return answer(RelayCode.OK, {"keys": sorted(fields)})

    from starlette.applications import Starlette

    return TestClient(Starlette(routes=[Route("/", echo, methods=["POST"])]))


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[]",
        b'{"b":1}',
        b'{"a":1,"c":2}',
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
    ],
)
def test_the_reader_refuses_a_request_that_is_not_a_valid_envelope_request(
    raw: bytes,
) -> None:
    sent = reader_client().post("/", content=raw)
    assert sent.status_code == 400
    assert sent.content == body_of("request-malformed")


def test_the_reader_returns_the_fields_of_a_valid_request() -> None:
    sent = reader_client().post("/", content=b'{"a":1,"b":2}')
    assert sent.status_code == 200
    assert json.loads(sent.content)["data"] == {"keys": ["a", "b"]}


def test_the_reader_refuses_an_oversize_body_as_too_large_not_malformed() -> None:
    padding = b"x" * MAX_REQUEST_BYTES
    sent = reader_client().post("/", content=b'{"a":"' + padding + b'"}')
    assert sent.status_code == 413
    assert sent.content == body_of("request-too-large")


# --- the stages in front of the routes ---------------------------------------


def exact_json(size: int) -> bytes:
    head, tail = b'{"a":"', b'"}'
    raw = head + b"x" * (size - len(head) - len(tail)) + tail
    assert len(raw) == size
    return raw


def test_a_body_of_exactly_the_limit_reaches_the_route(
    client: TestClient, spy: Spy
) -> None:
    sent = client.post("/v1/echo", content=exact_json(MAX_REQUEST_BYTES))
    assert sent.status_code == 200
    assert spy.reached == ["echo"]


def test_a_body_one_byte_over_is_too_large_before_the_route_or_any_decoding(
    client: TestClient, spy: Spy
) -> None:
    raw = exact_json(MAX_REQUEST_BYTES + 1)
    sent = client.post("/v1/echo", content=raw)
    assert sent.status_code == 413
    assert sent.content == body_of("request-too-large")
    assert sent.headers["cache-control"] == "no-store"
    assert spy.reached == []


def test_an_oversize_body_without_a_declared_length_is_too_large(
    client: TestClient, spy: Spy
) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_REQUEST_BYTES // 1000 + 2):
            yield b"x" * 1000

    request = client.build_request("POST", "/v1/echo", content=chunks())
    assert "content-length" not in request.headers
    sent = client.send(request)
    assert sent.status_code == 413
    assert sent.content == body_of("request-too-large")
    assert spy.reached == []


def test_a_chunked_body_within_the_limit_is_read_whole(
    client: TestClient, spy: Spy
) -> None:
    raw = exact_json(MAX_REQUEST_BYTES)

    def chunks() -> Iterator[bytes]:
        for start in range(0, len(raw), 1000):
            yield raw[start : start + 1000]

    request = client.build_request("POST", "/v1/echo", content=chunks())
    assert "content-length" not in request.headers
    sent = client.send(request)
    assert sent.status_code == 200
    assert spy.reached == ["echo"]


def test_the_size_limit_comes_before_the_version_check(client: TestClient) -> None:
    sent = client.post("/v9/anything", content=b"x" * (MAX_REQUEST_BYTES + 1))
    assert sent.status_code == 413
    assert sent.content == body_of("request-too-large")


@pytest.mark.parametrize(
    "path",
    [
        "/v2/ok",
        "/v0/ok",
        "/v9/anything",
        "/v2",
        "/v01/ok",
        "/v1000/",
        "/v" + "9" * 30 + "/x",
    ],
)
def test_an_unserved_version_answers_with_the_served_versions_even_where_a_route_exists(
    client: TestClient, spy: Spy, path: str
) -> None:
    sent = client.get(path)
    assert sent.status_code == 400
    assert sent.content == body_of("envelope-unsupported", '{"envelopes":[1]}')
    assert sent.headers["cache-control"] == "no-store"
    assert spy.reached == []


@pytest.mark.parametrize("path", ["/v1/ok", "/v1/items/abc"])
def test_a_served_version_reaches_the_route(
    client: TestClient, spy: Spy, path: str
) -> None:
    sent = client.get(path)
    assert sent.status_code == 200
    assert sent.content == body_of("ok")
    assert len(spy.reached) == 1


@pytest.mark.parametrize(
    "path",
    ["/nope", "/v1/nope", "/v/ok", "/vx/ok", "/version/1", "/", "/v1/ok/", "/v2ok"],
)
def test_an_unmatched_path_is_not_offered_without_a_redirect(
    client: TestClient, spy: Spy, path: str
) -> None:
    sent = client.get(path, follow_redirects=False)
    assert sent.status_code == 404
    assert sent.content == body_of("not-offered")
    assert sent.headers["cache-control"] == "no-store"
    assert "location" not in sent.headers
    assert spy.reached == []


def test_a_known_path_with_another_method_is_not_offered(
    client: TestClient, spy: Spy
) -> None:
    sent = client.get("/v1/echo")
    assert sent.status_code == 404
    assert sent.content == body_of("not-offered")
    assert "allow" not in sent.headers
    assert spy.reached == []


def test_an_unexpected_exception_answers_relay_failure(
    client: TestClient, spy: Spy
) -> None:
    sent = client.get("/v1/boom")
    assert spy.reached == ["boom"]
    assert sent.status_code == 500
    assert sent.content == body_of("relay-failure")
    assert sent.headers["cache-control"] == "no-store"
    assert sent.headers["content-type"] == "application/json"


def test_an_unreachable_store_answers_unavailable(
    client: TestClient, services: RelayServices
) -> None:
    assert client.get("/v1/store").status_code == 200
    services.storage.close()
    with pytest.raises(StorageUnreachable):
        services.storage.ping()
    sent = client.get("/v1/store")
    assert sent.status_code == 503
    assert sent.content == body_of("unavailable")
    assert sent.headers["cache-control"] == "no-store"


def test_a_handler_cannot_emit_a_client_origin_code(client: TestClient) -> None:
    sent = client.get("/v1/client-code")
    assert sent.status_code == 500
    assert sent.content == body_of("relay-failure")


def test_rate_limited_over_the_wire(client: TestClient) -> None:
    sent = client.get("/v1/limited")
    assert sent.status_code == 429
    assert sent.headers["retry-after"] == "7"
    assert sent.content == body_of("rate-limited", '{"retry_after_s":7}')


# --- the app factory and the lifespan ----------------------------------------


def config_for(path: Path) -> RelayConfig:
    return RelayConfig(
        database=SqliteTarget(path),
        pepper=PEPPER.encode(),
        host="127.0.0.1",
        port=8080,
        forwarded_allow_ips=(),
        token_limit_per_minute=60,
        client_limit_per_minute=20,
        shutdown_grace_s=20,
        log_level="info",
        extensions=(),
    )


def test_the_route_table_has_the_design_constants() -> None:
    assert routes.OFFERED_TARGETS == ()
    assert routes.RESERVED_PREFIXES == ("/v", "/livez", "/readyz", "/x/")


def test_startup_computes_readiness_and_shutdown_closes_storage(
    services: RelayServices, spy: Spy
) -> None:
    assert services.ready is False
    app = build_app(services, make_routes(services, spy))
    with TestClient(app):
        assert services.ready is True
    with pytest.raises(StorageUnreachable):
        services.storage.ping()


def test_an_unmigrated_database_is_not_ready_at_startup(
    database_target: Any, spy: Spy
) -> None:
    store = open_storage(database_target)
    pepper = PEPPER.encode()

    def clock() -> int:
        return 1

    unmigrated = RelayServices(
        storage=store,
        tokens=TokenService(store, pepper=pepper, clock=clock),
        limiter=RateLimiter(
            store, pepper=pepper, clock=clock, token_limit=1, client_limit=1
        ),
        clock=clock,
        registration=None,
        ready=True,
    )
    state = store.schema_state()
    assert state.current != state.expected
    with TestClient(build_app(unmigrated, [])):
        assert unmigrated.ready is False


def test_an_unreachable_store_is_not_ready_at_startup(
    services: RelayServices,
) -> None:
    services.ready = True
    services.storage.close()
    with TestClient(build_app(services, [])):
        assert services.ready is False


def test_create_app_wires_the_injected_store_clock_and_configured_limits(
    tmp_path: Path,
    open_full_storage: Callable[[], Storage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[RelayServices] = []

    def capture(services: RelayServices) -> list[BaseRoute]:
        captured.append(services)
        return []

    monkeypatch.setattr(app_module, "core_routes", capture)
    store = open_full_storage()
    database = tmp_path / "never-created.sqlite3"

    now = [5]

    def clock() -> int:
        return now[0]

    config = dataclasses.replace(
        config_for(database), token_limit_per_minute=2, client_limit_per_minute=3
    )
    with TestClient(create_app(config, storage=store, clock=clock)) as test_client:
        sent = test_client.get("/v1/anything")
        [services] = captured
        assert services.storage is store
        assert services.clock is clock
        assert [services.limiter.check_token("t1").allowed for _ in range(3)] == [
            True,
            True,
            False,
        ]
        now[0] = 65
        assert services.limiter.check_token("t1").allowed is True
        now[0] = 5
        assert [services.limiter.check_client("c1").allowed for _ in range(4)] == [
            True,
            True,
            True,
            False,
        ]
        minted = services.tokens.mint(principal_id=None, label=None)
        record = store.find_token(minted.token_id)
        assert record is not None and record.created_at == 5
        assert isinstance(services.tokens.authenticate(minted.token), Authenticated)
    assert sent.status_code == 404
    assert sent.content == body_of("not-offered")
    with pytest.raises(StorageUnreachable):
        store.ping()
    assert not database.exists()


def test_create_app_opens_the_configured_database_when_given_none(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(config_for(tmp_path / "relay.sqlite3"))) as test_client:
        sent = test_client.get("/v2/anything")
    assert sent.content == body_of("envelope-unsupported", '{"envelopes":[1]}')


# --- the request log ----------------------------------------------------------


class Raw(logging.Handler):
    """Every record's fields exactly as emitted, before any redaction filter."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.seen.append(dict(record.__dict__))


@pytest.fixture
def raw() -> Raw:
    handler = Raw()
    logging.getLogger().addHandler(handler)
    return handler


@pytest.fixture
def out(raw: Raw) -> io.StringIO:
    buffer = io.StringIO()
    configure_logging(pepper=PEPPER, password=PASSWORD, stream=buffer)
    # The test client's own library logs each request URL; that is not the relay.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return buffer


def records(out: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in out.getvalue().splitlines()]


REQUEST_KEYS = {
    "ts",
    "level",
    "event",
    "request_id",
    "method",
    "route",
    "status",
    "code",
    "duration_ms",
}


def test_one_request_record_with_the_route_template_status_and_code(
    client: TestClient, out: io.StringIO
) -> None:
    client.get("/v1/items/ITEM-ID-SENTINEL")
    [record] = records(out)
    assert set(record) == REQUEST_KEYS
    assert record["event"] == "request"
    assert record["level"] == "INFO"
    assert record["method"] == "GET"
    assert record["route"] == "/v1/items/{item_id}"
    assert record["status"] == 200
    assert record["code"] == "ok"
    assert isinstance(record["duration_ms"], int) and record["duration_ms"] >= 0
    assert re.fullmatch(r"[0-9a-f]{32}", record["request_id"])
    assert "ITEM-ID-SENTINEL" not in out.getvalue()


@pytest.mark.parametrize(
    ("method", "path", "status", "code", "route"),
    [
        ("GET", "/v1/ok", 200, "ok", "/v1/ok"),
        ("GET", "/nope/SENTINEL", 404, "not-offered", None),
        ("GET", "/v2/SENTINEL", 400, "envelope-unsupported", None),
        ("POST", "/v1/echo", 413, "request-too-large", None),
        ("GET", "/v1/echo", 404, "not-offered", "/v1/echo"),
        ("GET", "/v1/boom", 500, "relay-failure", "/v1/boom"),
        ("GET", "/v1/store", 503, "unavailable", "/v1/store"),
        ("GET", "/v1/limited", 429, "rate-limited", "/v1/limited"),
    ],
)
def test_every_pipeline_answer_writes_exactly_one_record_with_its_code(
    client: TestClient,
    services: RelayServices,
    out: io.StringIO,
    method: str,
    path: str,
    status: int,
    code: str,
    route: str | None,
) -> None:
    if path == "/v1/store":
        services.storage.close()
    content = b"x" * (MAX_REQUEST_BYTES + 1) if status == 413 else None
    sent = client.request(method, path, content=content)
    assert sent.status_code == status
    [record] = records(out)
    assert record["status"] == status
    assert record["code"] == code
    assert record["route"] == route
    assert record["event"] == "request"


def test_a_failure_record_carries_type_and_frames_only(
    client: TestClient, out: io.StringIO, raw: Raw
) -> None:
    client.get("/v1/boom")
    [record] = records(out)
    assert record["level"] == "ERROR"
    assert record["error_type"] == "RuntimeError"
    frames = record["frames"]
    assert frames and all(set(f) == {"file", "line", "function"} for f in frames)
    assert "boom" in [f["function"] for f in frames]
    assert "message-with-a-secret" not in out.getvalue()
    assert TOKEN not in out.getvalue()
    for seen in raw.seen:
        assert "message-with-a-secret" not in repr(seen)


def test_a_non_failure_record_has_no_failure_fields(
    client: TestClient, out: io.StringIO
) -> None:
    client.get("/nope")
    [record] = records(out)
    assert "error_type" not in record and "frames" not in record


def test_the_token_id_is_logged_when_a_handler_authenticated(
    client: TestClient, out: io.StringIO
) -> None:
    client.get("/v1/authed")
    client.get("/v1/ok")
    authed, anonymous = records(out)
    assert authed["token_id"] == "a" * 16
    assert "token_id" not in anonymous


def test_a_response_outside_the_envelope_logs_no_code(
    client: TestClient, out: io.StringIO
) -> None:
    sent = client.get("/x/page")
    assert sent.status_code == 200
    [record] = records(out)
    assert record["code"] is None
    assert record["status"] == 200
    assert record["route"] == "/x/page"


def test_request_ids_are_server_generated_and_never_the_clients(
    client: TestClient, out: io.StringIO
) -> None:
    for _ in range(3):
        client.get("/v1/ok", headers={"X-Request-Id": "client-chosen-id"})
    ids = [r["request_id"] for r in records(out)]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert "client-chosen-id" not in out.getvalue()


def test_a_nonstandard_method_is_logged_as_other(
    client: TestClient, out: io.StringIO
) -> None:
    client.request(ASCII_TOKEN_SHAPED_METHOD, "/v1/ok")
    [record] = records(out)
    assert record["method"] == "OTHER"


@pytest.mark.parametrize(
    "method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
)
def test_each_standard_method_is_logged_as_sent(
    client: TestClient, out: io.StringIO, method: str
) -> None:
    client.request(method, "/nope")
    [record] = records(out)
    assert record["method"] == method


def test_duration_is_the_elapsed_milliseconds_of_the_clock(
    client: TestClient, out: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter([100.0, 100.25])
    monkeypatch.setattr(
        app_module, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )
    client.get("/v1/ok")
    [record] = records(out)
    assert record["duration_ms"] == 250


PLANTED = [
    TOKEN,
    "PATH-SECRET-SENTINEL",
    "QUERY-SECRET-SENTINEL",
    "HEADER-SECRET-SENTINEL",
    "BODY-SECRET-SENTINEL",
    "COOKIE-SECRET-SENTINEL",
    "alice@example.invalid",
    CLIENT[0],
    str(CLIENT[1]),
]


@pytest.mark.parametrize("path", ["/v1/items/{}", "/nope/{}", "/v2/{}"])
def test_no_planted_secret_reaches_any_log_record(
    client: TestClient, out: io.StringIO, raw: Raw, path: str
) -> None:
    sent = client.post(
        path.format("PATH-SECRET-SENTINEL" + TOKEN),
        params={"q": "QUERY-SECRET-SENTINEL", "t": TOKEN},
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Other": "HEADER-SECRET-SENTINEL",
            "Cookie": "s=COOKIE-SECRET-SENTINEL",
            "X-Forwarded-For": "alice@example.invalid",
        },
        content=b'{"email":"alice@example.invalid","poll_secret":"BODY-SECRET-SENTINEL",'
        + TOKEN.encode()
        + b"}",
    )
    assert sent.status_code in (400, 404)
    written = out.getvalue()
    assert written.count("\n") == 1
    emitted = [s for s in raw.seen if s.get("event") == "request"]
    assert len(emitted) == 1
    for secret in PLANTED:
        assert secret not in written
        assert secret not in repr(emitted)
        assert secret not in repr(raw.seen)


def test_the_planted_secrets_are_really_sent(client: TestClient, spy: Spy) -> None:
    sent = client.get("/v1/who", headers={"Authorization": f"Bearer {TOKEN}"})
    data = json.loads(sent.content)["data"]
    assert data == {"address": CLIENT[0], "token": TOKEN}


def run_asgi(
    app: RelayApp,
    receive: Callable[[], Awaitable[dict[str, Any]]],
    headers: list[tuple[bytes, bytes]] | None = None,
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/echo",
        "headers": headers or [],
        "client": CLIENT,
    }
    asyncio.run(app(scope, receive, send))  # type: ignore[arg-type]
    return sent


def test_a_failure_before_routing_still_answers_relay_failure_and_logs_it(
    services: RelayServices, out: io.StringIO
) -> None:
    async def receive() -> dict[str, Any]:
        raise RuntimeError("receive-failed-SENTINEL")

    sent = run_asgi(build_app(services, []), receive)
    assert sent[0]["status"] == 500
    assert sent[1]["body"] == body_of("relay-failure")
    [record] = records(out)
    assert record["code"] == "relay-failure"
    assert record["status"] == 500
    assert record["error_type"] == "RuntimeError"
    assert "SENTINEL" not in out.getvalue()


def test_a_declared_oversize_length_is_refused_without_reading_the_body(
    services: RelayServices,
) -> None:
    async def receive() -> dict[str, Any]:
        raise AssertionError("the body was read")

    sent = run_asgi(
        build_app(services, []),
        receive,
        headers=[(b"content-length", str(MAX_REQUEST_BYTES + 1).encode())],
    )
    assert sent[0]["status"] == 413
    assert sent[1]["body"] == body_of("request-too-large")


def test_an_absurdly_long_declared_length_is_too_large_not_a_failure(
    services: RelayServices,
) -> None:
    async def receive() -> dict[str, Any]:
        raise AssertionError("the body was read")

    sent = run_asgi(
        build_app(services, []),
        receive,
        headers=[(b"content-length", b"9" * 5000)],
    )
    assert sent[0]["status"] == 413
    assert sent[1]["body"] == body_of("request-too-large")


def test_a_zero_padded_in_limit_length_is_not_refused(
    services: RelayServices,
) -> None:
    services.ready = True  # no lifespan runs here; a versioned path needs readiness

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = run_asgi(
        build_app(services, []),
        receive,
        headers=[(b"content-length", b"0" * 5000 + b"100")],
    )
    assert sent[0]["status"] == 404
    assert sent[1]["body"] == body_of("not-offered")


def test_a_client_that_disconnects_mid_request_gets_the_malformed_answer(
    services: RelayServices,
) -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    sent = run_asgi(build_app(services, []), receive)
    assert sent[0]["status"] == 400
    assert sent[1]["body"] == body_of("request-malformed")
