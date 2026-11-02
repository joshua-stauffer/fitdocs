"""Envelope answers and request reading for the relay's HTTP layer.

Every answer is built by `answer`, which encodes through the shared codec (the
only encoder there is), so a client-origin code cannot be emitted (Requirement
4.10). The client address is the connection's peer as the server reports it:
forwarding headers are honoured only by uvicorn, and only for the proxy
addresses the operator configured, never read here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from .shared.relay_codes import RELAY_CODES, RelayCode
from .shared.relay_envelope import (
    MAX_REQUEST_BYTES,
    Answer,
    EnvelopeError,
    decode_request,
    encode_answer,
)

# Keys the answer, the failure handler and a route leave in the ASGI scope for
# the request log (the code is what was actually sent; the token id is the
# authenticated token's public id).
SCOPE_CODE: Final = "fitdocs_relay.code"
SCOPE_TOKEN_ID: Final = "fitdocs_relay.token_id"
SCOPE_FAILURE: Final = "fitdocs_relay.failure"

_BEARER: Final = "bearer"
_MSG_NO_STATUS: Final = "The code has no HTTP status."
_MSG_WAIT: Final = "A retry wait is a non-negative count on a rate-limited answer."


class EnvelopeResponse(Response):
    """An envelope answer; records the code it carries for the request log."""

    media_type = "application/json"

    def __init__(
        self, code: RelayCode, body: bytes, status: int, headers: Mapping[str, str]
    ) -> None:
        super().__init__(content=body, status_code=status, headers=dict(headers))
        self.code = code

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope[SCOPE_CODE] = self.code.value
        await super().__call__(scope, receive, send)


def answer(
    code: RelayCode,
    data: Mapping[str, object] | None = None,
    *,
    outcome: str | None = None,
    retry_after_s: int | None = None,
) -> Response:
    """The envelope answer for `code`: its status, `no-store`, and for
    `rate-limited` the wait, in the data and in `Retry-After`."""
    fields: dict[str, object] = {} if data is None else dict(data)
    headers = {"Cache-Control": "no-store"}
    if "retry_after_s" in fields:
        raise ValueError(_MSG_WAIT)  # the keyword is the only way to state a wait
    if retry_after_s is not None:
        if (
            code is not RelayCode.RATE_LIMITED
            or isinstance(retry_after_s, bool)
            or not isinstance(retry_after_s, int)
            or retry_after_s < 0
        ):
            raise ValueError(_MSG_WAIT)
        fields["retry_after_s"] = retry_after_s
        headers["Retry-After"] = str(retry_after_s)
    body = encode_answer(Answer(code=code, data=fields, outcome=outcome))
    status = RELAY_CODES[code].http_status
    if status is None:
        raise EnvelopeError(_MSG_NO_STATUS)
    return EnvelopeResponse(code, body, status, headers)


def note_token_id(request: Request, token_id: str) -> None:
    """Record the authenticated token's public id for the request log."""
    request.scope[SCOPE_TOKEN_ID] = token_id


def bearer_token(request: Request) -> str | None:
    """The token after `Authorization: Bearer `, else None (absent or other scheme)."""
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, rest = header.partition(" ")
    rest = rest.lstrip(" ")  # RFC 6750: the scheme and the token are split by 1*SP
    if scheme.lower() != _BEARER or not rest:
        return None
    return rest


def client_address(request: Request) -> str | None:
    """The connection peer's address, or None when the server reported none."""
    if request.client is None:
        return None
    return request.client.host


async def read_request(
    request: Request, *, required: frozenset[str], allowed: frozenset[str]
) -> dict[str, object] | Response:
    """The request's fields, or the answer to send instead.

    A body over the limit is `request-too-large`; anything the strict codec
    refuses is `request-malformed`. Nothing is read from the fields here.
    """
    raw = await request.body()
    if len(raw) > MAX_REQUEST_BYTES:
        return answer(RelayCode.REQUEST_TOO_LARGE)
    try:
        return decode_request(raw, required=required, allowed=allowed)
    except EnvelopeError:
        return answer(RelayCode.REQUEST_MALFORMED)
