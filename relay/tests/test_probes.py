"""Liveness, readiness and the readiness gate on the API (Requirement 9.5).

Every app here is built through `create_app`, on both backends.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route
from starlette.testclient import TestClient

from fitdocs_relay import app as app_module
from fitdocs_relay.answers import answer
from fitdocs_relay.app import RelayServices, create_app
from fitdocs_relay.config import PostgresTarget, RelayConfig, SqliteTarget
from fitdocs_relay.logs import configure_logging
from fitdocs_relay.routes import core_routes as real_core_routes
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import SchemaChange, Storage, StorageError
from fitdocs_relay.storage.migrate import migrate, schema_changes

PEPPER = "probe-pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAeQ"
PASSWORD = "probe-db-passw0rd"


def config_for(database: SqliteTarget | PostgresTarget) -> RelayConfig:
    return RelayConfig(
        database=database,
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


def body(code: str, data: str = "{}") -> bytes:
    return f'{{"envelope":1,"code":"{code}","data":{data}}}'.encode()


def schema_body(code: str, current: int, expected: int) -> bytes:
    return body(code, f'{{"schema":{{"current":{current},"expected":{expected}}}}}')


class Recording:
    """A storage that records every attribute touched on it, then delegates."""

    def __init__(self, inner: Storage) -> None:
        self._inner = inner
        self.touched: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.touched.append(name)
        return getattr(self._inner, name)


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


class Harness:
    def __init__(
        self,
        database: SqliteTarget | PostgresTarget,
        store: Storage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.store = store
        self.expected = len(schema_changes(store.backend))
        self.captured: list[RelayServices] = []
        self.reached: list[str] = []
        harness = self

        def versioned(request: Request) -> Response:
            harness.reached.append("versioned")
            return answer(RelayCode.OK)

        def core(services: RelayServices) -> list[BaseRoute]:
            harness.captured.append(services)
            return [*real_core_routes(services), Route("/v1/probe-test", versioned)]

        monkeypatch.setattr(app_module, "core_routes", core)
        self.app = create_app(config_for(database), storage=store)

    @property
    def services(self) -> RelayServices:
        [services] = self.captured
        return services


@pytest.fixture
def make_harness(
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., Harness]]:
    opened: list[Storage] = []

    def make(
        *, migrated: bool, recording: bool = False, failing: str | None = None
    ) -> Harness:
        store = open_storage(database_target)
        opened.append(store)
        if migrated:
            migrate(store, now=1)
        return Harness(
            database_target,
            cast(Storage, Failing(store, failing))
            if failing is not None
            else cast(Storage, Recording(store))
            if recording
            else store,
            monkeypatch,
        )

    yield make
    for store in opened:
        store.close()


def assert_envelope_headers(sent: Any) -> None:
    assert sent.headers["content-type"] == "application/json"
    assert sent.headers["cache-control"] == "no-store"
    assert "retry-after" not in sent.headers


def test_a_migrated_database_is_ready_and_the_api_is_served(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=True)
    assert h.expected >= 1
    with TestClient(h.app) as client:
        ready = client.get("/readyz")
        served = client.get("/v1/probe-test")
    assert (ready.status_code, ready.content) == (
        200,
        schema_body("ok", h.expected, h.expected),
    )
    assert_envelope_headers(ready)
    assert (served.status_code, served.content) == (200, body("ok"))
    assert h.reached == ["versioned"]


def test_liveness_answers_ok_with_no_storage_access(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=True, recording=True)
    recording = h.store
    assert isinstance(recording, Recording)
    with TestClient(h.app) as client:
        assert recording.touched  # startup readiness did use the store
        recording.touched.clear()
        live = client.get("/livez")
        assert recording.touched == []
        ready = client.get("/readyz")
        assert recording.touched  # the spy sees storage use when there is some
    assert (live.status_code, live.content) == (200, body("ok"))
    assert_envelope_headers(live)
    assert ready.status_code == 200


def test_an_unmigrated_database_is_schema_behind_and_the_api_is_unavailable(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=False)
    with TestClient(h.app) as client:
        assert h.services.ready is False
        ready = client.get("/readyz")
        gated = client.get("/v1/probe-test")
        unmatched = client.get("/v1/nothing-here")
        wrong_method = client.post("/v1/probe-test")
        live = client.get("/livez")
    assert (ready.status_code, ready.content) == (
        503,
        schema_body("schema-behind", 0, h.expected),
    )
    assert_envelope_headers(ready)
    assert (gated.status_code, gated.content) == (503, body("unavailable"))
    assert_envelope_headers(gated)
    # Matching comes first: no route, or the wrong method, is not-offered.
    for sent in (unmatched, wrong_method):
        assert (sent.status_code, sent.content) == (404, body("not-offered"))
    assert h.reached == []
    assert (live.status_code, live.content) == (200, body("ok"))


def test_migrating_restores_service_only_when_readiness_is_probed(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=False)
    with TestClient(h.app) as client:
        assert client.get("/v1/probe-test").content == body("unavailable")
        migrate(h.store, now=1)
        # The flag is refreshed by the probe, not by the database changing.
        assert h.services.ready is False
        assert client.get("/v1/probe-test").content == body("unavailable")
        ready = client.get("/readyz")
        assert h.services.ready is True
        served = client.get("/v1/probe-test")
    assert ready.content == schema_body("ok", h.expected, h.expected)
    assert (served.status_code, served.content) == (200, body("ok"))


def _ahead(h: Harness) -> None:
    h.store.apply_schema_change(
        SchemaChange(
            version=h.expected + 1,
            name="9999_from_a_newer_build",
            sql="CREATE TABLE newer_build_marker (x integer)",
        ),
        now=2,
    )


def test_a_newer_schema_is_schema_ahead_and_withdraws_service(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=True)
    with TestClient(h.app) as client:
        assert client.get("/v1/probe-test").content == body("ok")
        assert h.services.ready is True
        _ahead(h)
        ready = client.get("/readyz")
        gated = client.get("/v1/probe-test")
        assert h.services.ready is False
    assert (ready.status_code, ready.content) == (
        503,
        schema_body("schema-ahead", h.expected + 1, h.expected),
    )
    assert_envelope_headers(ready)
    assert (gated.status_code, gated.content) == (503, body("unavailable"))


def test_a_closed_store_is_storage_unreachable_while_liveness_stays_ok(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=True)
    with TestClient(h.app) as client:
        assert h.services.ready is True
        h.store.close()
        ready = client.get("/readyz")
        live = client.get("/livez")
        gated = client.get("/v1/probe-test")
        assert h.services.ready is False
    assert (ready.status_code, ready.content) == (503, body("storage-unreachable"))
    assert_envelope_headers(ready)
    assert (live.status_code, live.content) == (200, body("ok"))
    assert (gated.status_code, gated.content) == (503, body("unavailable"))


def test_a_store_that_comes_back_restores_service_on_the_next_probe(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=False)
    with TestClient(h.app) as client:
        assert client.get("/readyz").status_code == 503
        migrate(h.store, now=1)
        assert client.get("/readyz").status_code == 200
        _ahead(h)
        assert client.get("/readyz").status_code == 503
        assert client.get("/v1/probe-test").status_code == 503


def test_the_probes_are_not_gated_and_other_paths_are_not_versioned(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(migrated=False)
    with TestClient(h.app) as client:
        assert client.get("/livez").content == body("ok")
        assert client.get("/readyz").status_code == 503
        # Not under a served version: the pipeline answers as before.
        assert client.get("/nowhere").content == body("not-offered")
        assert client.get("/v2/anything").content == body(
            "envelope-unsupported", '{"envelopes":[1]}'
        )
        assert client.get("/vx/anything").content == body("not-offered")


def test_probes_are_logged_with_their_route_and_code(
    make_harness: Callable[..., Harness],
) -> None:
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password=PASSWORD, stream=out)
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    h = make_harness(migrated=False)
    with TestClient(h.app) as client:
        client.get("/livez")
        client.get("/readyz")
        client.get("/v1/probe-test")
        # Unmatched and wrong-method while not ready: routing answers, and an
        # unmatched request carries no route template (a stale scope["route"]
        # from the gate's matching would log a false one).
        client.get("/v1/nothing-here")
        client.post("/v1/probe-test")
    seen = [
        (r["route"], r["status"], r["code"])
        for r in map(json.loads, out.getvalue().splitlines())
        if r["event"] == "request"
    ]
    assert seen == [
        ("/livez", 200, "ok"),
        ("/readyz", 503, "schema-behind"),
        ("/v1/probe-test", 503, "unavailable"),
        (None, 404, "not-offered"),
        ("/v1/probe-test", 404, "not-offered"),
    ]


class Failing:
    """A storage whose named operation raises a plain `StorageError`."""

    def __init__(self, inner: Storage, operation: str) -> None:
        self._inner = inner
        self._operation = operation
        self.failing = False

    def __getattr__(self, name: str) -> Any:
        if self.failing and name == self._operation:

            def fail(*args: object, **kwargs: object) -> None:
                raise StorageError("an unexpected backend failure")

            return fail
        return getattr(self._inner, name)


@pytest.mark.parametrize("operation", ["ping", "schema_state"])
def test_an_unexpected_storage_failure_in_readiness_is_relay_failure_and_not_ready(
    make_harness: Callable[..., Harness], operation: str
) -> None:
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password=PASSWORD, stream=out)
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    h = make_harness(migrated=True, failing=operation)
    failing = h.store
    assert isinstance(failing, Failing)
    with TestClient(h.app) as client:
        assert h.services.ready is True
        assert client.get("/v1/probe-test").content == body("ok")
        failing.failing = True
        ready = client.get("/readyz")
        assert h.services.ready is False
        gated = client.get("/v1/probe-test")
    assert (ready.status_code, ready.content) == (500, body("relay-failure"))
    assert_envelope_headers(ready)
    assert (gated.status_code, gated.content) == (503, body("unavailable"))
    failed = [
        r
        for r in map(json.loads, out.getvalue().splitlines())
        if r.get("route") == "/readyz"
    ]
    [record] = failed
    assert record["code"] == "relay-failure"
    assert record["error_type"] == "StorageError"
    assert record["frames"]
