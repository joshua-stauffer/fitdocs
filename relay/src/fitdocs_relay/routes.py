"""The relay's route table: the reserved paths and the core routes.

The probes, the capabilities route, the token routes and the registration
routes live here. The registration routes are served through the provider a
wrapper installed; every answer the provider gives is validated against the
shared wire format before it is encoded.
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
from fitdocs_relay.seam import (
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
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import (
    ROUTE_CAPABILITIES,
    ROUTE_LIVEZ,
    ROUTE_READYZ,
    ROUTE_REGISTRATION_POLL,
    ROUTE_REGISTRATIONS,
    ROUTE_TOKEN,
    ROUTE_TOKEN_REVOKE,
    SERVED_ENVELOPES,
    EnvelopeError,
    is_email,
    is_poll_secret,
    parse_retry_after,
    parse_started,
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


class ProviderAnswerError(Exception):
    """A registration provider answered outside the wire format.

    Carries no text: the pipeline logs the failure by type and frames only, so
    nothing the provider returned can reach a log through it.
    """


_POLL_WITHOUT_DATA: Final = {
    PollPending: RelayCode.REGISTRATION_PENDING,
    PollSlowDown: RelayCode.REGISTRATION_SLOW_DOWN,
    PollRefused: RelayCode.REGISTRATION_REFUSED,
    PollExpired: RelayCode.REGISTRATION_EXPIRED,
}


def _provider_limit(given: RateLimitedAnswer) -> Response:
    try:
        wait = parse_retry_after({"retry_after_s": given.retry_after_s})
    except EnvelopeError:
        raise ProviderAnswerError from None
    return answer(RelayCode.RATE_LIMITED, retry_after_s=wait)


def _start_response(given: object) -> Response:
    """The envelope answer for a provider's start answer, or a ProviderAnswerError."""
    if isinstance(given, StartRefused):
        return answer(RelayCode.REGISTRATION_REFUSED)
    if isinstance(given, RateLimitedAnswer):
        return _provider_limit(given)
    if not isinstance(given, StartAccepted):
        raise ProviderAnswerError
    data = {
        "user_code": given.user_code,
        "poll_secret": given.poll_secret,
        "interval_s": given.interval_s,
        "expires_in_s": given.expires_in_s,
    }
    try:
        started = parse_started(data)
    except EnvelopeError:
        raise ProviderAnswerError from None
    return answer(
        RelayCode.REGISTRATION_STARTED,
        {
            "user_code": started.user_code,
            "poll_secret": started.poll_secret,
            "interval_s": started.interval_s,
            "expires_in_s": started.expires_in_s,
        },
    )


def _poll_response(services: RelayServices, given: object) -> Response:
    """The envelope answer for a provider's poll answer, or a ProviderAnswerError."""
    if isinstance(given, RateLimitedAnswer):
        return _provider_limit(given)
    for kind, code in _POLL_WITHOUT_DATA.items():
        if isinstance(given, kind):
            return answer(code)
    if not isinstance(given, PollIssued):
        raise ProviderAnswerError
    issued = given.token
    if not isinstance(issued, IssuedToken):
        raise ProviderAnswerError
    # A token the seam did not issue (or a malformed one) does not authenticate;
    # one that does must be the one the provider says it is.
    outcome = services.tokens.authenticate(issued.token)
    if (
        not isinstance(outcome, Authenticated)
        or outcome.token_id != issued.token_id
        or outcome.principal_id != issued.principal_id
    ):
        raise ProviderAnswerError
    return answer(RelayCode.REGISTRATION_ISSUED, {"token": issued.token})


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
                "registration": services.registration is not None,
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

    def _client_limit(request: Request) -> Response | None:
        decision = services.limiter.check_client(client_address(request))
        return None if decision.allowed else _limited(decision)

    async def registration_start(request: Request) -> Response:
        provider = services.registration
        if provider is None:
            return answer(RelayCode.NOT_OFFERED)
        limited = await run_in_threadpool(_client_limit, request)
        if limited is not None:
            return limited
        fields = await read_request(
            request, required=frozenset({"email"}), allowed=frozenset({"email"})
        )
        if isinstance(fields, Response):
            return fields
        email = fields["email"]
        if not isinstance(email, str) or not is_email(email):
            return answer(RelayCode.REQUEST_MALFORMED)
        given = await run_in_threadpool(provider.start, email)
        return _start_response(given)

    async def registration_poll(request: Request) -> Response:
        provider = services.registration
        if provider is None:
            return answer(RelayCode.NOT_OFFERED)
        limited = await run_in_threadpool(_client_limit, request)
        if limited is not None:
            return limited
        fields = await read_request(
            request,
            required=frozenset({"poll_secret"}),
            allowed=frozenset({"poll_secret"}),
        )
        if isinstance(fields, Response):
            return fields
        secret = fields["poll_secret"]
        if not isinstance(secret, str) or not is_poll_secret(secret):
            return answer(RelayCode.REQUEST_MALFORMED)
        given = await run_in_threadpool(provider.poll, secret)
        return await run_in_threadpool(_poll_response, services, given)

    return [
        Route(ROUTE_LIVEZ, livez),
        Route(ROUTE_READYZ, readyz),
        Route(ROUTE_CAPABILITIES, capabilities),
        Route(ROUTE_TOKEN, token_check),
        Route(ROUTE_TOKEN_REVOKE, token_revoke, methods=["POST"]),
        Route(ROUTE_REGISTRATIONS, registration_start, methods=["POST"]),
        Route(ROUTE_REGISTRATION_POLL, registration_poll, methods=["POST"]),
    ]
