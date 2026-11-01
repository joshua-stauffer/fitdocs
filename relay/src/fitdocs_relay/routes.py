"""The relay's route table: the reserved paths and the core routes.

The probes, the capabilities route and the token routes live here; the
registration routes are added to `core_routes` by the task that serves them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from fitdocs_relay.answers import (
    answer,
    bearer_token,
    client_address,
    note_token_id,
    read_request,
)
from fitdocs_relay.identity import Authenticated
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import (
    ROUTE_CAPABILITIES,
    ROUTE_LIVEZ,
    ROUTE_READYZ,
    ROUTE_TOKEN,
    ROUTE_TOKEN_REVOKE,
    SERVED_ENVELOPES,
)
from fitdocs_relay.storage.interface import (
    RateDecision,
    RevokeResult,
    Storage,
    StorageUnreachable,
)

if TYPE_CHECKING:
    from fitdocs_relay.app import RelayServices

OFFERED_TARGETS: tuple[str, ...] = ()  # later specs append target ids here
RESERVED_PREFIXES: Final = ("/v", "/livez", "/readyz", "/x/")


def readiness(storage: Storage) -> Response:
    """The readiness answer: `ok` only when the store is reachable and at this
    build's schema version, else the code naming the failing condition."""
    try:
        storage.ping()
        state = storage.schema_state()
    except StorageUnreachable:
        return answer(RelayCode.STORAGE_UNREACHABLE)
    if state.current < state.expected:
        code = RelayCode.SCHEMA_BEHIND
    elif state.current > state.expected:
        code = RelayCode.SCHEMA_AHEAD
    else:
        code = RelayCode.OK
    return answer(
        code, {"schema": {"current": state.current, "expected": state.expected}}
    )


def _limited(decision: RateDecision) -> Response:
    # A refused decision always carries its wait; an allowed one never reaches here.
    return answer(RelayCode.RATE_LIMITED, retry_after_s=decision.retry_after_s)


def _authorize(services: RelayServices, request: Request) -> Authenticated | Response:
    """Authenticate the presenting token, then count it against its own limit.

    A failed authentication counts against the client first and only then
    answers its token code (or `rate-limited` once the client is over its limit);
    a valid token is counted per token and never against the client.
    """
    outcome = services.tokens.authenticate(bearer_token(request))
    if not isinstance(outcome, Authenticated):
        decision = services.limiter.check_client(client_address(request))
        return answer(outcome) if decision.allowed else _limited(decision)
    note_token_id(request, outcome.token_id)
    decision = services.limiter.check_token(outcome.token_id)
    return outcome if decision.allowed else _limited(decision)


def _registration_offered(services: RelayServices) -> bool:
    return False  # the registration provider arrives with the seam (task 4.5)


def core_routes(services: RelayServices) -> list[BaseRoute]:
    def livez(request: Request) -> Response:
        return answer(RelayCode.OK)

    def readyz(request: Request) -> Response:
        try:
            response = readiness(services.storage)
        except Exception:
            services.ready = False  # a probe that fails is not a ready store
            raise
        services.ready = response.status_code == 200
        return response

    def capabilities(request: Request) -> Response:
        decision = services.limiter.check_client(client_address(request))
        if not decision.allowed:
            return _limited(decision)
        return answer(
            RelayCode.OK,
            {
                "envelopes": list(SERVED_ENVELOPES),
                "registration": _registration_offered(services),
                "targets": list(OFFERED_TARGETS),
            },
        )

    def token_check(request: Request) -> Response:
        checked = _authorize(services, request)
        return checked if isinstance(checked, Response) else answer(RelayCode.OK)

    async def token_revoke(request: Request) -> Response:
        checked = await run_in_threadpool(_authorize, services, request)
        if isinstance(checked, Response):
            return checked
        fields = await read_request(request, required=frozenset(), allowed=frozenset())
        if isinstance(fields, Response):
            return fields
        result = await run_in_threadpool(services.tokens.revoke, checked.token_id)
        if result is RevokeResult.UNKNOWN:
            return answer(RelayCode.TOKEN_UNKNOWN)
        return answer(RelayCode.OK)

    return [
        Route(ROUTE_LIVEZ, livez),
        Route(ROUTE_READYZ, readyz),
        Route(ROUTE_CAPABILITIES, capabilities),
        Route(ROUTE_TOKEN, token_check),
        Route(ROUTE_TOKEN_REVOKE, token_revoke, methods=["POST"]),
    ]
