"""The closed, append-only relay code vocabulary.

Standard library only, and self-contained: this file is byte-copied into the
relay, so it imports nothing from `fitdocs` and never `http`. Declaration
order is the pinned prefix; a later change only appends.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class CodeOrigin(StrEnum):
    RELAY = "relay"  # the relay may send it
    CLIENT = "client"  # only the fitdocs client concludes it; never on the wire


class RelayCode(StrEnum):
    OK = "ok"
    TOKEN_MISSING = "token-missing"
    TOKEN_UNKNOWN = "token-unknown"
    TOKEN_REVOKED = "token-revoked"
    ENVELOPE_UNSUPPORTED = "envelope-unsupported"
    REQUEST_MALFORMED = "request-malformed"
    REQUEST_TOO_LARGE = "request-too-large"
    NOT_OFFERED = "not-offered"
    RATE_LIMITED = "rate-limited"
    UNAVAILABLE = "unavailable"
    RELAY_FAILURE = "relay-failure"
    STORAGE_UNREACHABLE = "storage-unreachable"
    SCHEMA_BEHIND = "schema-behind"
    SCHEMA_AHEAD = "schema-ahead"
    REGISTRATION_STARTED = "registration-started"
    REGISTRATION_PENDING = "registration-pending"
    REGISTRATION_SLOW_DOWN = "registration-slow-down"
    REGISTRATION_ISSUED = "registration-issued"
    REGISTRATION_REFUSED = "registration-refused"
    REGISTRATION_EXPIRED = "registration-expired"
    RELAY_UNREACHABLE = "relay-unreachable"
    ANSWER_MALFORMED = "answer-malformed"
    CONNECT_STARTED = "connect-started"
    CONNECT_PENDING = "connect-pending"
    CONNECT_GRANTED = "connect-granted"
    CONNECT_REFUSED = "connect-refused"
    CONNECT_EXPIRED = "connect-expired"


@dataclass(frozen=True)
class RelayCodeInfo:
    code: RelayCode
    explanation: str  # fitdocs-written, one sentence
    http_status: int | None  # None exactly when origin is CLIENT
    origin: CodeOrigin


def _relay(code: RelayCode, status: int, explanation: str) -> RelayCodeInfo:
    return RelayCodeInfo(code, explanation, status, CodeOrigin.RELAY)


def _client(code: RelayCode, explanation: str) -> RelayCodeInfo:
    return RelayCodeInfo(code, explanation, None, CodeOrigin.CLIENT)


_C = RelayCode

_INFOS: Final[tuple[RelayCodeInfo, ...]] = (
    _relay(_C.OK, 200, "The relay accepted the request."),
    _relay(_C.TOKEN_MISSING, 401, "The request carried no relay token."),
    _relay(_C.TOKEN_UNKNOWN, 401, "The relay does not recognise this token."),
    _relay(_C.TOKEN_REVOKED, 401, "This relay token has been revoked."),
    _relay(
        _C.ENVELOPE_UNSUPPORTED,
        400,
        "The relay does not serve this envelope version.",
    ),
    _relay(_C.REQUEST_MALFORMED, 400, "The relay could not read the request."),
    _relay(_C.REQUEST_TOO_LARGE, 413, "The request is larger than the relay accepts."),
    _relay(_C.NOT_OFFERED, 404, "This relay does not offer that."),
    _relay(
        _C.RATE_LIMITED,
        429,
        "The relay is limiting requests; wait before trying again.",
    ),
    _relay(_C.UNAVAILABLE, 503, "The relay is temporarily unavailable."),
    _relay(_C.RELAY_FAILURE, 500, "The relay failed while handling the request."),
    _relay(_C.STORAGE_UNREACHABLE, 503, "The relay cannot reach its database."),
    _relay(_C.SCHEMA_BEHIND, 503, "The relay's database needs migrating."),
    _relay(
        _C.SCHEMA_AHEAD,
        503,
        "The relay's database was migrated by a newer relay.",
    ),
    _relay(_C.REGISTRATION_STARTED, 200, "The relay started the registration."),
    _relay(
        _C.REGISTRATION_PENDING,
        200,
        "The registration is waiting for confirmation.",
    ),
    _relay(
        _C.REGISTRATION_SLOW_DOWN,
        200,
        "The relay asked fitdocs to poll less often.",
    ),
    _relay(_C.REGISTRATION_ISSUED, 200, "The relay issued a relay token."),
    _relay(_C.REGISTRATION_REFUSED, 403, "The relay refused the registration."),
    _relay(
        _C.REGISTRATION_EXPIRED,
        410,
        "The registration expired before it was confirmed.",
    ),
    _client(_C.RELAY_UNREACHABLE, "fitdocs could not reach the relay."),
    _client(
        _C.ANSWER_MALFORMED,
        "The relay's answer was not a valid fitdocs relay answer.",
    ),
    _relay(_C.CONNECT_STARTED, 200, "The relay started connecting this target."),
    _relay(
        _C.CONNECT_PENDING,
        200,
        "The connection is waiting for the step in the browser.",
    ),
    _relay(
        _C.CONNECT_GRANTED,
        200,
        "The connection is made, and the relay issued this instance's token.",
    ),
    _relay(
        _C.CONNECT_REFUSED,
        403,
        "The connection was declined, or was not given every permission it needs.",
    ),
    _relay(
        _C.CONNECT_EXPIRED,
        410,
        "The connection attempt expired or is not known to the relay.",
    ),
)

RELAY_CODES: Final[Mapping[RelayCode, RelayCodeInfo]] = {
    info.code: info for info in _INFOS
}


def explain(code: RelayCode) -> str:
    return RELAY_CODES[code].explanation
