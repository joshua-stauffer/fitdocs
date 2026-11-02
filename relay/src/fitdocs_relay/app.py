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
from dataclasses import dataclass, field
from typing import Final

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match
from starlette.types import Message, Receive, Scope, Send

from fitdocs_relay.answers import (
    SCOPE_BODY_LIMIT,
    SCOPE_CODE,
    SCOPE_FAILURE,
    SCOPE_OUTCOME,
    SCOPE_TOKEN_ID,
    answer,
)
from fitdocs_relay.config import RelayConfig
from fitdocs_relay.crypto import Keyring
from fitdocs_relay.identity import TokenService
from fitdocs_relay.logs import failure_fields, log_event
from fitdocs_relay.outbound import Outbound, urllib_outbound
from fitdocs_relay.ratelimit import RateLimiter
from fitdocs_relay.routes import OFFERED_TARGETS, body_limit, core_routes, readiness
from fitdocs_relay.seam import (
    EXTENSION_ROUTE_PREFIX,
    SEAM_VERSION,
    ExtensionContext,
    ExtensionParts,
    IssuedToken,
    RegistrationProvider,
    RelayExtension,
    SeamError,
)
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import MAX_REQUEST_BYTES, SERVED_ENVELOPES
from fitdocs_relay.shared.relay_targets import STRAVA
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import (
    RevokeResult,
    Storage,
    StorageUnreachable,
)
from fitdocs_relay.strava.api import StravaApi
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import StravaConfig
from fitdocs_relay.strava.connect import ConnectFlow
from fitdocs_relay.strava.custody import Custody
from fitdocs_relay.strava.pages import Operator
from fitdocs_relay.strava.publish import StravaPublisher
from fitdocs_relay.strava.webhook import Webhook

_LOGGER = logging.getLogger("fitdocs_relay.app")
_VERSION_PREFIX: Final = re.compile(r"/v([0-9]+)(?:/|$)")
_SERVED: Final = frozenset(str(version) for version in SERVED_ENVELOPES)
_METHODS: Final = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
)


_EXTENSION_NAME: Final = re.compile(r"[a-z][a-z0-9-]{0,31}")
KEY_MAX_CHARACTERS: Final = 128
VALUE_MAX_BYTES: Final = 4096
TTL_MIN_S: Final = 1
TTL_MAX_S: Final = 2_592_000
_MSG_KEY: Final = "a record key is 0 to 128 characters"
_MSG_VALUE: Final = "a record value is 0 to 4096 bytes"
_MSG_TTL: Final = "a record expiry is 1 to 2592000 seconds"
_MSG_NAME: Final = (
    "its name is not 1 to 32 characters of lowercase letters, digits and hyphens,"
    " starting with a letter"
)
_MSG_VERSION: Final = (
    f"declares a seam version this relay does not implement"
    f" (it implements seam version {SEAM_VERSION})"
)


@dataclass(frozen=True)
class StravaServices:
    """The Strava target's parts, built when its configuration is present."""

    config: StravaConfig = field(repr=False)
    api: StravaApi
    budget: StravaBudget
    custody: Custody
    publisher: StravaPublisher
    connect: ConnectFlow
    webhook: Webhook
    operator: Operator


@dataclass
class RelayServices:
    storage: Storage
    tokens: TokenService
    limiter: RateLimiter
    clock: Callable[[], int]
    registration: RegistrationProvider | None
    ready: bool
    targets: tuple[str, ...] = ()
    strava: StravaServices | None = None


class _TokenIssuance:
    """The seam's token operations: the operator's `TokenService`, unchanged."""

    def __init__(self, tokens: TokenService) -> None:
        self._tokens = tokens

    def issue(self, *, principal_id: str | None, label: str | None) -> IssuedToken:
        minted = self._tokens.mint(principal_id=principal_id, label=label)
        return IssuedToken(minted.token_id, minted.principal_id, minted.token)

    def revoke(self, token_id: str) -> bool:
        """True when the token exists (now revoked), False when it is unknown."""
        return self._tokens.revoke(token_id) is not RevokeResult.UNKNOWN

    def delete_principal(self, principal_id: str) -> bool:
        return self._tokens.delete_principal(principal_id)


class _ExtensionRecords:
    """One extension's records: its name is the namespace, the limits are here."""

    def __init__(
        self, storage: Storage, namespace: str, clock: Callable[[], int]
    ) -> None:
        self._storage = storage
        self._namespace = namespace
        self._clock = clock

    @staticmethod
    def _checked_key(key: str) -> str:
        if not isinstance(key, str) or len(key) > KEY_MAX_CHARACTERS:
            raise ValueError(_MSG_KEY)
        return key

    def put(self, key: str, value: bytes, *, ttl_s: int) -> None:
        self._checked_key(key)
        if not isinstance(value, bytes) or len(value) > VALUE_MAX_BYTES:
            raise ValueError(_MSG_VALUE)
        if type(ttl_s) is not int or not TTL_MIN_S <= ttl_s <= TTL_MAX_S:
            raise ValueError(_MSG_TTL)
        now = self._clock()
        self._storage.put_record(
            namespace=self._namespace,
            key=key,
            value=value,
            expires_at=now + ttl_s,
            now=now,
        )

    def get(self, key: str) -> bytes | None:
        return self._storage.get_record(
            namespace=self._namespace, key=self._checked_key(key), now=self._clock()
        )

    def take(self, key: str) -> bytes | None:
        return self._storage.take_record(
            namespace=self._namespace, key=self._checked_key(key), now=self._clock()
        )

    def delete(self, key: str) -> bool:
        return self._storage.delete_record(
            namespace=self._namespace, key=self._checked_key(key)
        )


def _label(name: object) -> str:
    return ascii(name)[:50] if isinstance(name, str) else f"<{type(name).__name__}>"


def _install_extensions(
    services: RelayServices, extensions: Sequence[RelayExtension]
) -> list[BaseRoute]:
    """Build each extension, refusing (naming it and the reason) a wrong seam
    version, a bad or repeated name, a route outside `/x/<name>/` and a second
    registration provider; sets `services.registration`. Returns the routes."""
    routes: list[BaseRoute] = []
    names: set[str] = set()
    provider_from: str | None = None
    for extension in extensions:
        name = getattr(extension, "name", None)
        label = _label(name)
        version = getattr(extension, "seam_version", None)
        if type(version) is not int or version != SEAM_VERSION:
            raise SeamError(f"extension {label}: {_MSG_VERSION}")
        if not isinstance(name, str) or _EXTENSION_NAME.fullmatch(name) is None:
            raise SeamError(f"extension {label}: {_MSG_NAME}")
        if name in names:
            raise SeamError(
                f"extension {label}: its name is already used by another extension"
            )
        names.add(name)
        context = ExtensionContext(
            tokens=_TokenIssuance(services.tokens),
            records=_ExtensionRecords(services.storage, name, services.clock),
            clock=services.clock,
            logger=logging.getLogger(f"fitdocs_relay.extension.{name}"),
        )
        parts = extension.build(context)
        if not isinstance(parts, ExtensionParts):
            raise SeamError(f"extension {label}: build did not return ExtensionParts")
        prefix = f"{EXTENSION_ROUTE_PREFIX}{name}/"
        for route in parts.routes:
            path = getattr(route, "path", None)
            if not isinstance(path, str) or not path.startswith(prefix):
                raise SeamError(f"extension {label}: adds a route outside {prefix}")
            routes.append(route)
        if parts.registration is not None:
            if provider_from is not None:
                raise SeamError(
                    f"extension {label}: installs a registration provider, but"
                    f" extension {_label(provider_from)} already installed one"
                )
            provider_from = name
            services.registration = parts.registration
    return routes


def compute_ready(storage: Storage) -> bool:
    """True when the store is reachable and at this build's schema version."""
    return readiness(storage).status_code == 200


def _unavailable(request: Request, exc: Exception) -> Response:
    return answer(RelayCode.UNAVAILABLE)


def _not_offered(request: Request, exc: Exception) -> Response:
    return answer(RelayCode.NOT_OFFERED)


def _relay_failure(request: Request, exc: Exception) -> Response:
    return answer(RelayCode.RELAY_FAILURE)


async def _admit(
    scope: Scope, receive: Receive, *, per_route_limits: bool
) -> Response | Receive:
    """The body limit, then the version prefix: the answer to send, or a
    `receive` that replays the body already read. The limit is the route's
    when the target routes are served, else the default; it is left in the
    scope for the request reader."""
    limit = body_limit(scope["path"]) if per_route_limits else MAX_REQUEST_BYTES
    scope[SCOPE_BODY_LIMIT] = limit
    declared = dict(scope["headers"]).get(b"content-length", b"")
    digits = declared.lstrip(b"0")
    if declared.isdigit() and (
        len(digits) > len(str(limit)) or int(digits or b"0") > limit
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
        if size > limit:
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
    # Whether `ROUTE_BODY_LIMITS` applies (the target routes are served).
    per_route_limits: bool = False

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
            admitted = await _admit(
                scope, receive, per_route_limits=self.per_route_limits
            )
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
        if SCOPE_OUTCOME in scope:
            fields["outcome"] = scope[SCOPE_OUTCOME]
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
    app.per_route_limits = services.strava is not None
    return app


def _wall_clock() -> int:
    return int(time.time())


def _build_strava(
    config: RelayConfig,
    store: Storage,
    tokens: TokenService,
    *,
    clock: Callable[[], int],
    outbound: Outbound,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> StravaServices | None:
    targets, strava = config.targets, config.strava
    if targets is None or strava is None:
        return None
    api = StravaApi(strava, outbound=outbound)
    budget = StravaBudget(store, strava.limits, clock=clock)
    custody = Custody(
        store,
        Keyring(targets.keys),
        api,
        budget,
        pepper=config.pepper,
        clock=clock,
        monotonic=monotonic,
        sleep=sleep,
    )
    return StravaServices(
        config=strava,
        api=api,
        budget=budget,
        custody=custody,
        publisher=StravaPublisher(
            store,
            custody,
            api,
            budget,
            strava,
            clock=clock,
            monotonic=monotonic,
            sleep=sleep,
        ),
        connect=ConnectFlow(
            store,
            tokens,
            custody,
            api,
            budget,
            public_url=targets.public_url,
            clock=clock,
        ),
        webhook=Webhook(custody, secret=strava.webhook_token),
        operator=Operator(
            name=targets.operator_name,
            support_contact=targets.support_contact,
            policy_url=targets.privacy_policy_url,
        ),
    )


def make_services(
    config: RelayConfig,
    store: Storage,
    *,
    clock: Callable[[], int],
    outbound: Outbound | None = None,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> RelayServices:
    """The services of one app: the core ones, and the Strava ones when the
    target is configured (`targets` then lists it)."""
    tokens = TokenService(store, pepper=config.pepper, clock=clock)
    strava = _build_strava(
        config,
        store,
        tokens,
        clock=clock,
        outbound=urllib_outbound if outbound is None else outbound,
        monotonic=time.monotonic if monotonic is None else monotonic,
        sleep=time.sleep if sleep is None else sleep,
    )
    configured = {STRAVA: strava is not None}
    return RelayServices(
        storage=store,
        tokens=tokens,
        limiter=RateLimiter(
            store,
            pepper=config.pepper,
            clock=clock,
            token_limit=config.token_limit_per_minute,
            client_limit=config.client_limit_per_minute,
        ),
        clock=clock,
        registration=None,
        ready=False,
        targets=tuple(
            target for target in OFFERED_TARGETS if configured.get(target, False)
        ),
        strava=strava,
    )


def create_app(
    config: RelayConfig,
    *,
    extensions: Sequence[RelayExtension] = (),
    storage: Storage | None = None,
    clock: Callable[[], int] | None = None,
    outbound: Outbound | None = None,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Starlette:
    store = open_storage(config.database) if storage is None else storage
    now = _wall_clock if clock is None else clock
    try:
        services = make_services(
            config,
            store,
            clock=now,
            outbound=outbound,
            monotonic=monotonic,
            sleep=sleep,
        )
        extension_routes = _install_extensions(services, extensions)
    except BaseException:
        if storage is None:
            store.close()  # opened here; nothing else will close it
        raise
    return build_app(services, [*core_routes(services), *extension_routes])
