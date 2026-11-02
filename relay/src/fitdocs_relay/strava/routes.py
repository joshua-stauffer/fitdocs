"""The Strava target's HTTP surface: the envelope routes and `/go/`.

The envelope routes reuse the relay's authentication, per-token limit and strict
request reader, and every answer is built by `answer`. A route answers `ok`
with the outcome of its own pinned set; a result outside that set is a relay
failure, never an answer. The activity page address is the answer's `link`
under the `activity` link setting and appears nowhere under `relay`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import BaseRoute, Route

from fitdocs_relay.answers import answer, client_address, read_request
from fitdocs_relay.identity import Authenticated
from fitdocs_relay.routes import authorize
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import EnvelopeError, is_poll_secret
from fitdocs_relay.shared.relay_targets import (
    ACTION_CONNECT,
    ACTION_CONNECT_POLL,
    ACTION_DISCONNECT,
    ACTION_PUBLISH,
    ACTION_UPLOAD,
    LINK_FIELD,
    LINK_PREFIX,
    PUBLICATION_ID_RE,
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
from fitdocs_relay.strava.config import LinkSetting
from fitdocs_relay.strava.connect import PollGranted, PollOutcome
from fitdocs_relay.strava.pages import (
    PAGE_HEADERS,
    Page,
    not_found_page,
    try_later_page,
    unavailable_page,
)
from fitdocs_relay.strava.publish import Landed, LinkRefusal

if TYPE_CHECKING:
    from fitdocs_relay.app import RelayServices

_PUBLICATION_ID: Final = re.compile(PUBLICATION_ID_RE)
_POLL_ANSWERS: Final = {
    PollOutcome.PENDING: RelayCode.CONNECT_PENDING,
    PollOutcome.REFUSED: RelayCode.CONNECT_REFUSED,
    PollOutcome.EXPIRED: RelayCode.CONNECT_EXPIRED,
}


class OutcomeNotServed(Exception):
    """The publisher returned an outcome the route's set does not hold.

    Carries no text: the pipeline logs the failure by type and frames only.
    """


def _page(page: Page) -> Response:
    return HTMLResponse(page.html, status_code=page.status, headers=dict(PAGE_HEADERS))


def _landed_answer(
    result: PublishCode | Landed, allowed: frozenset[str], links: LinkSetting
) -> Response:
    code = result.code if isinstance(result, Landed) else result
    outcome = route_outcome(code.value, allowed)
    if outcome is None:
        raise OutcomeNotServed
    data: dict[str, object] = {}
    if isinstance(result, Landed) and links is LinkSetting.ACTIVITY:
        data[LINK_FIELD] = result.activity_page
    return answer(RelayCode.OK, data, outcome=outcome)


def strava_routes(services: RelayServices) -> list[BaseRoute]:
    """The Strava routes; none when the target is not configured, so every
    one of its paths is then `not-offered`."""
    strava = services.strava
    if strava is None:
        return []
    links = strava.config.links

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
        return _landed_answer(result, PUBLISH_OUTCOMES, links)

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
        return _landed_answer(result, UPLOAD_OUTCOMES, links)

    async def disconnect(request: Request) -> Response:
        gate = await admitted(request, required=frozenset(), allowed=frozenset())
        if isinstance(gate, Response):
            return gate
        # Revokes at Strava when it can, then deletes the connection and its
        # relay token whatever Strava answered; no connection is already done.
        await run_in_threadpool(strava.custody.withdraw, gate[0].principal_id)
        return answer(RelayCode.OK)

    def go(request: Request) -> Response:
        if not services.ready:
            return _page(unavailable_page(strava.operator))
        decision = services.limiter.check_client(client_address(request))
        if not decision.allowed:
            return _page(try_later_page(strava.operator))
        publication_id = request.path_params["publication_id"]
        if not _PUBLICATION_ID.fullmatch(publication_id):
            return _page(not_found_page(strava.operator))
        resolved = strava.publisher.resolve_link(publication_id)
        if resolved is LinkRefusal.TRY_LATER:
            return _page(try_later_page(strava.operator))
        if isinstance(resolved, LinkRefusal):
            return _page(not_found_page(strava.operator))
        return Response(status_code=302, headers={**PAGE_HEADERS, "Location": resolved})

    return [
        Route(target_route(STRAVA, ACTION_CONNECT), connect, methods=["POST"]),
        Route(
            target_route(STRAVA, ACTION_CONNECT_POLL), connect_poll, methods=["POST"]
        ),
        Route(target_route(STRAVA, ACTION_PUBLISH), publish, methods=["POST"]),
        Route(target_route(STRAVA, ACTION_UPLOAD), upload, methods=["POST"]),
        Route(target_route(STRAVA, ACTION_DISCONNECT), disconnect, methods=["POST"]),
        Route(f"{LINK_PREFIX}{{publication_id}}", go, methods=["GET"]),
    ]
