"""The relay app: services, the request pipeline, the lifespan and the factory.

The pipeline wraps the whole Starlette app (outermost, so it sees the answers
Starlette's own error middleware produces): body limit, then version prefix,
then Starlette routing; and it writes the one request log record. Failures
become envelope answers: no route or method is `not-offered`, a store that
cannot be reached is `unavailable`, anything else is `relay-failure`, logged by
type and frames only.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match
from starlette.types import Message, Receive, Scope, Send

from fitdocs_relay.answers import (
    SCOPE_CODE,
    SCOPE_FAILURE,
    SCOPE_TOKEN_ID,
    answer,
)
from fitdocs_relay.config import RelayConfig
from fitdocs_relay.identity import TokenService
from fitdocs_relay.logs import failure_fields, log_event
from fitdocs_relay.ratelimit import RateLimiter
from fitdocs_relay.routes import core_routes, readiness
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import MAX_REQUEST_BYTES, SERVED_ENVELOPES
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import Storage, StorageUnreachable

_LOGGER = logging.getLogger("fitdocs_relay.app")
_VERSION_PREFIX: Final = re.compile(r"/v([0-9]+)(?:/|$)")
_SERVED: Final = frozenset(str(version) for version in SERVED_ENVELOPES)
_METHODS: Final = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
)


@dataclass
class RelayServices:
    storage: Storage
    tokens: TokenService
    limiter: RateLimiter
    clock: Callable[[], int]
    ready: bool


def compute_ready(storage: Storage) -> bool:
    """True when the store is reachable and at this build's schema version."""
    return readiness(storage).status_code == 200


def _unavailable(request: Request, exc: Exception) -> Response:
    return answer(RelayCode.UNAVAILABLE)


def _not_offered(request: Request, exc: Exception) -> Response:
    return answer(RelayCode.NOT_OFFERED)


def _relay_failure(request: Request, exc: Exception) -> Response:
    return answer(RelayCode.RELAY_FAILURE)


async def _admit(scope: Scope, receive: Receive) -> Response | Receive:
    """The body limit, then the version prefix: the answer to send, or a
    `receive` that replays the body already read."""
    declared = dict(scope["headers"]).get(b"content-length", b"")
    digits = declared.lstrip(b"0")
    if declared.isdigit() and (
        len(digits) > len(str(MAX_REQUEST_BYTES))
        or int(digits or b"0") > MAX_REQUEST_BYTES
    ):
        return answer(RelayCode.REQUEST_TOO_LARGE)
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            return answer(RelayCode.REQUEST_MALFORMED)  # the client went away
        chunk: bytes = message.get("body", b"")
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            return answer(RelayCode.REQUEST_TOO_LARGE)
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    prefix = _VERSION_PREFIX.match(scope["path"])
    if prefix is not None and prefix.group(1) not in _SERVED:
        return answer(
            RelayCode.ENVELOPE_UNSUPPORTED, {"envelopes": list(SERVED_ENVELOPES)}
        )
    body = b"".join(chunks)
    replayed = False

    async def replay() -> Message:
        nonlocal replayed
        if not replayed:
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


class RelayApp(Starlette):
    """Starlette with the relay's pipeline in front of its routing."""

    # Whether the store is ready to serve; the factory points it at the services.
    is_ready: Callable[[], bool] = staticmethod(lambda: False)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        status: int | None = None

        async def watched_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            admitted = await _admit(scope, receive)
            if isinstance(admitted, Response):
                await admitted(scope, receive, watched_send)
            elif (
                _VERSION_PREFIX.match(scope["path"])
                and not self.is_ready()
                and self._match(scope)
            ):
                # After matching, before the handler: a versioned route waits
                # for readiness, the probes do not, and a path with no route
                # (or the wrong method) is still `not-offered`.
                await answer(RelayCode.UNAVAILABLE)(scope, receive, watched_send)
            else:
                await super().__call__(scope, admitted, watched_send)
        except Exception:
            # Starlette's error middleware has already answered `relay-failure`
            # and re-raised for the server; this records the failure by type and
            # frames, and keeps the exception from the server's own log.
            scope.setdefault(SCOPE_FAILURE, failure_fields(sys.exc_info()))
            if status is None:
                # If the connection is gone there is nothing more to send.
                with contextlib.suppress(Exception):
                    await answer(RelayCode.RELAY_FAILURE)(scope, receive, watched_send)
        finally:
            self._log(scope, request_id, status, started)

    def _match(self, scope: Scope) -> bool:
        """True (and the route noted in the scope for the log) when a route
        matches the request fully."""
        for route in self.router.routes:
            if route.matches(scope)[0] is Match.FULL:
                scope["route"] = route
                return True
        return False

    @staticmethod
    def _log(scope: Scope, request_id: str, status: int | None, started: float) -> None:
        method = scope["method"]
        fields: dict[str, object] = {
            "request_id": request_id,
            "method": method if method in _METHODS else "OTHER",
            "route": getattr(scope.get("route"), "path", None),
            "status": status,
            "code": scope.get(SCOPE_CODE),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        if SCOPE_TOKEN_ID in scope:
            fields["token_id"] = scope[SCOPE_TOKEN_ID]
        failure = scope.get(SCOPE_FAILURE)
        if failure is not None:
            fields.update(failure)
        log_event(
            _LOGGER,
            "request",
            level=logging.ERROR if failure is not None else logging.INFO,
            **fields,
        )


def build_app(services: RelayServices, routes: Sequence[BaseRoute]) -> RelayApp:
    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        services.ready = compute_ready(services.storage)
        try:
            yield
        finally:
            services.storage.close()

    app = RelayApp(
        routes=list(routes),
        exception_handlers={
            HTTPException: _not_offered,
            StorageUnreachable: _unavailable,
            Exception: _relay_failure,
        },
        lifespan=lifespan,
    )
    app.router.redirect_slashes = False
    app.is_ready = lambda: services.ready
    return app


def _wall_clock() -> int:
    return int(time.time())


def create_app(
    config: RelayConfig,
    *,
    storage: Storage | None = None,
    clock: Callable[[], int] | None = None,
) -> Starlette:
    store = open_storage(config.database) if storage is None else storage
    now = _wall_clock if clock is None else clock
    services = RelayServices(
        storage=store,
        tokens=TokenService(store, pepper=config.pepper, clock=now),
        limiter=RateLimiter(
            store,
            pepper=config.pepper,
            clock=now,
            token_limit=config.token_limit_per_minute,
            client_limit=config.client_limit_per_minute,
        ),
        clock=now,
        ready=False,
    )
    return build_app(services, core_routes(services))
