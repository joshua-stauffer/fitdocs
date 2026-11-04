"""The Strava target's HTTP surface: the envelope routes, the browser pages
and the webhook.

The envelope routes reuse the relay's authentication, per-token limit and strict
request reader, and every answer is built by `answer`. A route answers `ok`
with the outcome of its own pinned set; a result outside that set is a relay
failure, never an answer. The activity page address is the answer's `link`.

Every page route answers a fitdocs-written page, also when the store is
unreachable or something unexpected is raised (an unexpected one is recorded by
type and frames in the request log). A browser route does nothing for HEAD:
the connect page and the callback each change state. The webhook echoes Strava's
challenge as `{"hub.challenge": ...}` and acknowledges an event with an empty
200; its refusals are envelope answers.
"""

from __future__ import annotations

import hmac
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route

from fitdocs_relay.answers import (
    SCOPE_FAILURE,
    answer,
    client_address,
    read_request,
)
from fitdocs_relay.identity import Authenticated
from fitdocs_relay.logs import failure_fields
from fitdocs_relay.routes import authorize, limited_answer
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import EnvelopeError, is_poll_secret
from fitdocs_relay.shared.relay_targets import (
    ACTION_CONNECT,
    ACTION_CONNECT_POLL,
    ACTION_DISCONNECT,
    ACTION_PUBLISH,
    ACTION_UPLOAD,
    CONNECT_PAGE_PREFIX,
    LINK_FIELD,
    PUBLISH_FIELDS,
    PUBLISH_OUTCOMES,
    STRAVA,
    UPLOAD_FIELDS,
    UPLOAD_OUTCOMES,
    parse_publish_fields,
    parse_upload_fields,
    route_outcome,
    target_route,
)
from fitdocs_relay.storage.interface import StorageUnreachable
from fitdocs_relay.strava.connect import (
    CALLBACK_PATH,
    CLAIM_COOKIE,
    CallbackOutcome,
    PageOutcome,
    PollGranted,
    PollOutcome,
    ShowConsent,
)
from fitdocs_relay.strava.pages import (
    PAGE_HEADERS,
    Page,
    connect_page,
    granted_page,
    in_use_page,
    invalid_code_page,
    privacy_page,
    refused_page,
    try_later_page,
    unavailable_page,
)
from fitdocs_relay.strava.publish import Landed
from fitdocs_relay.strava.webhook import WEBHOOK_PATH

if TYPE_CHECKING:
    from fitdocs_relay.app import RelayServices

_POLL_ANSWERS: Final = {
    PollOutcome.PENDING: RelayCode.CONNECT_PENDING,
    PollOutcome.REFUSED: RelayCode.CONNECT_REFUSED,
    PollOutcome.EXPIRED: RelayCode.CONNECT_EXPIRED,
}


CONNECT_PAGE_PATH: Final = f"{CONNECT_PAGE_PREFIX}{STRAVA}"
PRIVACY_PATH: Final = "/privacy"
MAX_CHALLENGE_CHARS: Final = 256


class OutcomeNotServed(Exception):
    """The publisher returned an outcome the route's set does not hold.

    Carries no text: the pipeline logs the failure by type and frames only.
    """


def _page(page: Page) -> Response:
    return HTMLResponse(page.html, status_code=page.status, headers=dict(PAGE_HEADERS))


def _landed_answer(result: PublishCode | Landed, allowed: frozenset[str]) -> Response:
    code = result.code if isinstance(result, Landed) else result
    outcome = route_outcome(code.value, allowed)
    if outcome is None:
        raise OutcomeNotServed
    data: dict[str, object] = {}
    if isinstance(result, Landed):
        data[LINK_FIELD] = result.activity_page
    return answer(RelayCode.OK, data, outcome=outcome)


def strava_routes(services: RelayServices) -> list[BaseRoute]:
    """The Strava routes; none when the target is not configured, so every
    one of its paths is then `not-offered`."""
    strava = services.strava
    if strava is None:
        return []

    async def admitted(
        request: Request, *, required: frozenset[str], allowed: frozenset[str]
    ) -> tuple[Authenticated, dict[str, object]] | Response:
        """The authenticated principal and the strictly read fields, or the
        answer to send instead (authentication and the token limit first)."""
        checked = await run_in_threadpool(authorize, services, request)
        if isinstance(checked, Response):
            return checked
        fields = await read_request(request, required=required, allowed=allowed)
        if isinstance(fields, Response):
            return fields
        return checked, fields

    async def connect(request: Request) -> Response:
        gate = await admitted(request, required=frozenset(), allowed=frozenset())
        if isinstance(gate, Response):
            return gate
        started = await run_in_threadpool(strava.connect.start, gate[0].principal_id)
        return answer(
            RelayCode.CONNECT_STARTED,
            {
                "user_code": started.user_code,
                "poll_secret": started.poll_secret,
                "interval_s": started.interval_s,
                "expires_in_s": started.expires_in_s,
            },
        )

    async def connect_poll(request: Request) -> Response:
        gate = await admitted(
            request,
            required=frozenset({"poll_secret"}),
            allowed=frozenset({"poll_secret"}),
        )
        if isinstance(gate, Response):
            return gate
        who, fields = gate
        secret = fields["poll_secret"]
        if not isinstance(secret, str) or not is_poll_secret(secret):
            return answer(RelayCode.REQUEST_MALFORMED)
        polled = await run_in_threadpool(strava.connect.poll, who.principal_id, secret)
        if isinstance(polled, PollGranted):
            return answer(RelayCode.CONNECT_GRANTED, {"token": polled.token})
        return answer(_POLL_ANSWERS[polled])

    async def publish(request: Request) -> Response:
        gate = await admitted(request, required=PUBLISH_FIELDS, allowed=PUBLISH_FIELDS)
        if isinstance(gate, Response):
            return gate
        who, fields = gate
        try:
            facts = parse_publish_fields(fields)
        except EnvelopeError:
            return answer(RelayCode.REQUEST_MALFORMED)
        result = await run_in_threadpool(
            strava.publisher.publish, who.principal_id, facts
        )
        return _landed_answer(result, PUBLISH_OUTCOMES)

    async def upload(request: Request) -> Response:
        gate = await admitted(request, required=UPLOAD_FIELDS, allowed=UPLOAD_FIELDS)
        if isinstance(gate, Response):
            return gate
        who, fields = gate
        try:
            facts, fit = parse_upload_fields(fields)
        except EnvelopeError:
            return answer(RelayCode.REQUEST_MALFORMED)
        result = await run_in_threadpool(
            strava.publisher.upload, who.principal_id, facts, fit
        )
        return _landed_answer(result, UPLOAD_OUTCOMES)

    async def disconnect(request: Request) -> Response:
        gate = await admitted(request, required=frozenset(), allowed=frozenset())
        if isinstance(gate, Response):
            return gate
        # Revokes at Strava when it can, then deletes the connection and its
        # relay token whatever Strava answered; no connection is already done.
        await run_in_threadpool(strava.custody.withdraw, gate[0].principal_id)
        return answer(RelayCode.OK)

    def browser(
        serve: Callable[[Request], Response],
    ) -> Callable[[Request], Response]:
        """A page route: nothing for HEAD, the unavailable page while the relay
        is not ready, the try-later page over the client limit, and the
        unavailable page for a store or an unexpected failure."""

        def guarded(request: Request) -> Response:
            if request.method == "HEAD":
                return Response(
                    status_code=405, headers={**PAGE_HEADERS, "Allow": "GET"}
                )
            try:
                if not services.ready:
                    return _page(unavailable_page(strava.operator))
                decision = services.limiter.check_client(client_address(request))
                if not decision.allowed:
                    return _page(try_later_page(strava.operator))
                return serve(request)
            except StorageUnreachable:
                return _page(unavailable_page(strava.operator))
            except Exception:
                request.scope.setdefault(SCOPE_FAILURE, failure_fields(sys.exc_info()))
                return _page(unavailable_page(strava.operator))

        return guarded

    def connect_view(request: Request) -> Response:
        shown = strava.connect.page(
            request.query_params.get("code"), request.cookies.get(CLAIM_COOKIE)
        )
        if isinstance(shown, ShowConsent):
            response = _page(
                connect_page(
                    user_code=shown.user_code,
                    authorize_url=shown.authorize_url,
                    operator=strava.operator,
                )
            )
            if shown.set_cookie is not None:
                response.headers.append("Set-Cookie", shown.set_cookie)
            return response
        if shown is PageOutcome.IN_USE:
            return _page(in_use_page(strava.operator))
        return _page(invalid_code_page(strava.operator))

    def callback_view(request: Request) -> Response:
        query = request.query_params
        outcome = strava.connect.callback(
            state=query.get("state"),
            code=query.get("code"),
            scope=query.get("scope"),
            error=query.get("error"),
            cookie=request.cookies.get(CLAIM_COOKIE),
        )
        if outcome is CallbackOutcome.GRANTED:
            return _page(granted_page(strava.operator))
        if outcome is CallbackOutcome.REFUSED:
            return _page(refused_page(strava.operator))
        return _page(invalid_code_page(strava.operator))

    def privacy_view(request: Request) -> Response:
        return _page(privacy_page(strava.operator))

    webhook_secret = strava.config.webhook_token.encode("utf-8")

    async def webhook_endpoint(request: Request) -> Response:
        presented = request.path_params["secret"].encode("utf-8", "replace")
        if not hmac.compare_digest(presented, webhook_secret):
            decision = await run_in_threadpool(
                services.limiter.check_client, client_address(request)
            )
            if not decision.allowed:
                return limited_answer(decision)
            return answer(RelayCode.NOT_OFFERED)
        if request.method == "POST":
            # The pipeline has already bounded the body it replays here.
            await run_in_threadpool(strava.webhook.event, await request.body())
            return Response(status_code=200)
        query = request.query_params
        challenge = query.get("hub.challenge")
        if challenge is not None and len(challenge) > MAX_CHALLENGE_CHARS:
            return answer(RelayCode.NOT_OFFERED)
        echoed = strava.webhook.validate(
            query.get("hub.mode"), challenge, query.get("hub.verify_token")
        )
        if echoed is None:
            return answer(RelayCode.NOT_OFFERED)
        return JSONResponse(echoed)

    return [
        Route(target_route(STRAVA, ACTION_CONNECT), connect, methods=["POST"]),
        Route(
            target_route(STRAVA, ACTION_CONNECT_POLL), connect_poll, methods=["POST"]
        ),
        Route(target_route(STRAVA, ACTION_PUBLISH), publish, methods=["POST"]),
        Route(target_route(STRAVA, ACTION_UPLOAD), upload, methods=["POST"]),
        Route(target_route(STRAVA, ACTION_DISCONNECT), disconnect, methods=["POST"]),
        Route(CONNECT_PAGE_PATH, browser(connect_view), methods=["GET"]),
        Route(CALLBACK_PATH, browser(callback_view), methods=["GET"]),
        Route(PRIVACY_PATH, browser(privacy_view), methods=["GET"]),
        Route(f"{WEBHOOK_PATH}/{{secret}}", webhook_endpoint, methods=["GET", "POST"]),
    ]
