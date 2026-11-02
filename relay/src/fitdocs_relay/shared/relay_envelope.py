"""Envelope v1: the relay wire codec, shared by the client and the relay.

Standard library only, plus one relative import of the vocabulary: this file
is byte-copied into the relay, where the same relative import resolves to the
copied vocabulary. Error messages are fixed text that never interpolates the
input, so nothing a peer sent can reach a log or a terminal through them.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from .relay_codes import RELAY_CODES, CodeOrigin, RelayCode

ENVELOPE_VERSION: Final = 1
SERVED_ENVELOPES: Final[tuple[int, ...]] = (1,)

ROUTE_LIVEZ: Final = "/livez"
ROUTE_READYZ: Final = "/readyz"
ROUTE_CAPABILITIES: Final = "/v1/capabilities"
ROUTE_TOKEN: Final = "/v1/token"
ROUTE_TOKEN_REVOKE: Final = "/v1/token/revoke"
ROUTE_REGISTRATIONS: Final = "/v1/registrations"
ROUTE_REGISTRATION_POLL: Final = "/v1/registrations/poll"

TOKEN_PREFIX: Final = "fdr1"
TOKEN_RE: Final = r"^fdr1_([a-z2-7]{16})_([a-z2-7]{52})$"
USER_CODE_RE: Final = r"^[BCDFGHJKLMNPQRSTVWXZ]{4}-[BCDFGHJKLMNPQRSTVWXZ]{4}$"
POLL_SECRET_RE: Final = r"^[A-Za-z0-9_-]{32,128}$"
TARGET_ID_RE: Final = r"^[a-z][a-z0-9-]{0,31}$"
EMAIL_RE: Final = r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$"
MAX_EMAIL_CHARS: Final = 254

MIN_POLL_INTERVAL_S: Final = 1
MAX_POLL_INTERVAL_S: Final = 60
SLOW_DOWN_STEP_S: Final = 5
MIN_EXPIRES_IN_S: Final = 60
MAX_EXPIRES_IN_S: Final = 3600
MAX_REQUEST_BYTES: Final = 65_536
MAX_ANSWER_BYTES: Final = 65_536

_TOKEN = re.compile(TOKEN_RE)
_USER_CODE = re.compile(USER_CODE_RE)
_POLL_SECRET = re.compile(POLL_SECRET_RE)
_TARGET_ID = re.compile(TARGET_ID_RE)
_EMAIL = re.compile(EMAIL_RE)

_ANSWER_KEYS: Final = frozenset({"envelope", "code", "data", "outcome"})
_REQUIRED_ANSWER_KEYS: Final = frozenset({"envelope", "code", "data"})

_MSG_NOT_JSON: Final = "The body is not a valid envelope JSON object."
_MSG_TOO_LARGE: Final = "The body is larger than the envelope allows."
_MSG_ANSWER: Final = "The answer is not a valid envelope v1 answer."
_MSG_REQUEST: Final = "The request is not a valid envelope v1 request."
_MSG_DATA: Final = "The answer data does not match its route's schema."
_MSG_ENCODE: Final = "The value cannot be encoded as an envelope v1 body."


class EnvelopeError(ValueError):
    """A body that is not valid envelope v1. The message is fixed text."""


@dataclass(frozen=True)
class Answer:
    code: RelayCode
    data: Mapping[str, object]
    outcome: str | None = None


@dataclass(frozen=True)
class CapabilitiesData:
    envelopes: tuple[int, ...]
    registration: bool
    targets: tuple[str, ...]


@dataclass(frozen=True)
class StartedData:
    user_code: str
    poll_secret: str
    interval_s: int
    expires_in_s: int


# --------------------------------------------------------------------------- #
# Field formats
# --------------------------------------------------------------------------- #


def split_relay_token(value: str) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    match = _TOKEN.fullmatch(value)
    if match is None:
        return None
    return match.group(1), match.group(2)


def is_user_code(value: object) -> bool:
    return isinstance(value, str) and _USER_CODE.fullmatch(value) is not None


def is_poll_secret(value: object) -> bool:
    return isinstance(value, str) and _POLL_SECRET.fullmatch(value) is not None


def is_target_id(value: object) -> bool:
    return isinstance(value, str) and _TARGET_ID.fullmatch(value) is not None


def is_email(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_EMAIL_CHARS
        and _EMAIL.fullmatch(value) is not None
    )


# --------------------------------------------------------------------------- #
# Strict JSON
# --------------------------------------------------------------------------- #


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EnvelopeError(_MSG_NOT_JSON)
        result[key] = value
    return result


def _refuse_constant(_name: str) -> object:
    raise EnvelopeError(_MSG_NOT_JSON)


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise EnvelopeError(_MSG_NOT_JSON)
    return value


def _load_object(raw: bytes, limit: int) -> dict[str, object]:
    if not isinstance(raw, bytes | bytearray):
        raise EnvelopeError(_MSG_NOT_JSON)
    if len(raw) > limit:
        raise EnvelopeError(_MSG_TOO_LARGE)
    try:
        text = bytes(raw).decode("utf-8")
        loaded = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_refuse_constant,
            parse_float=_finite_float,
        )
    except EnvelopeError:
        raise
    except (ValueError, RecursionError):
        raise EnvelopeError(_MSG_NOT_JSON) from None
    if not isinstance(loaded, dict):
        raise EnvelopeError(_MSG_NOT_JSON)
    return loaded


def _check_keys(value: object) -> None:
    """Every object key at any depth must be a string; `json.dumps` would
    otherwise coerce `1` and `"1"` into duplicate keys."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EnvelopeError(_MSG_ENCODE)
            _check_keys(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _check_keys(item)


def _dump(value: object, limit: int) -> bytes:
    try:
        _check_keys(value)
        raw = json.dumps(
            value, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise EnvelopeError(_MSG_ENCODE) from None
    if len(raw) > limit:
        raise EnvelopeError(_MSG_TOO_LARGE)
    return raw


# --------------------------------------------------------------------------- #
# Answers
# --------------------------------------------------------------------------- #


def encode_answer(answer: Answer) -> bytes:
    if (
        not isinstance(answer.code, RelayCode)
        or RELAY_CODES[answer.code].origin is not CodeOrigin.RELAY
    ):
        raise EnvelopeError(_MSG_ANSWER)
    body: dict[str, object] = {
        "envelope": ENVELOPE_VERSION,
        "code": answer.code.value,
        "data": dict(answer.data),
    }
    if answer.outcome is not None:
        if not isinstance(answer.outcome, str) or answer.outcome == "":
            raise EnvelopeError(_MSG_ANSWER)
        body["outcome"] = answer.outcome
    return _dump(body, MAX_ANSWER_BYTES)


def decode_answer(raw: bytes) -> Answer:
    body = _load_object(raw, MAX_ANSWER_BYTES)
    keys = body.keys()
    if not keys >= _REQUIRED_ANSWER_KEYS or not keys <= _ANSWER_KEYS:
        raise EnvelopeError(_MSG_ANSWER)
    envelope = body["envelope"]
    if (
        isinstance(envelope, bool)
        or not isinstance(envelope, int)
        or envelope not in SERVED_ENVELOPES
    ):
        raise EnvelopeError(_MSG_ANSWER)
    code_value = body["code"]
    if not isinstance(code_value, str):
        raise EnvelopeError(_MSG_ANSWER)
    try:
        code = RelayCode(code_value)
    except ValueError:
        raise EnvelopeError(_MSG_ANSWER) from None
    if RELAY_CODES[code].origin is not CodeOrigin.RELAY:
        raise EnvelopeError(_MSG_ANSWER)
    data = body["data"]
    if not isinstance(data, dict):
        raise EnvelopeError(_MSG_ANSWER)
    outcome: str | None = None
    if "outcome" in body:
        value = body["outcome"]
        if not isinstance(value, str) or value == "":
            raise EnvelopeError(_MSG_ANSWER)
        outcome = value
    return Answer(code=code, data=data, outcome=outcome)


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #


def encode_request(fields: Mapping[str, object]) -> bytes:
    return _dump(dict(fields), MAX_REQUEST_BYTES)


def decode_request(
    raw: bytes, *, required: frozenset[str], allowed: frozenset[str]
) -> dict[str, object]:
    body = _load_object(raw, MAX_REQUEST_BYTES)
    keys = body.keys()
    if not required <= keys or not keys <= allowed:
        raise EnvelopeError(_MSG_REQUEST)
    return body


# --------------------------------------------------------------------------- #
# Per-route data parsers
# --------------------------------------------------------------------------- #


def _exact(data: Mapping[str, object], keys: frozenset[str]) -> None:
    if not isinstance(data, Mapping) or data.keys() != keys:
        raise EnvelopeError(_MSG_DATA)


def _int_in(value: object, low: int, high: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise EnvelopeError(_MSG_DATA)
    if high is not None and value > high:
        raise EnvelopeError(_MSG_DATA)
    return value


def _envelope_list(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise EnvelopeError(_MSG_DATA)
    return tuple(_int_in(item, 1, None) for item in value)


def parse_envelopes(data: Mapping[str, object]) -> tuple[int, ...]:
    _exact(data, frozenset({"envelopes"}))
    return _envelope_list(data["envelopes"])


def parse_capabilities(data: Mapping[str, object]) -> CapabilitiesData:
    _exact(data, frozenset({"envelopes", "registration", "targets"}))
    registration = data["registration"]
    targets = data["targets"]
    if not isinstance(registration, bool) or not isinstance(targets, list):
        raise EnvelopeError(_MSG_DATA)
    if not all(is_target_id(item) for item in targets):
        raise EnvelopeError(_MSG_DATA)
    return CapabilitiesData(
        envelopes=_envelope_list(data["envelopes"]),
        registration=registration,
        targets=tuple(str(item) for item in targets),
    )


def parse_started(data: Mapping[str, object]) -> StartedData:
    _exact(data, frozenset({"user_code", "poll_secret", "interval_s", "expires_in_s"}))
    user_code = data["user_code"]
    poll_secret = data["poll_secret"]
    if not isinstance(user_code, str) or not is_user_code(user_code):
        raise EnvelopeError(_MSG_DATA)
    if not isinstance(poll_secret, str) or not is_poll_secret(poll_secret):
        raise EnvelopeError(_MSG_DATA)
    return StartedData(
        user_code=user_code,
        poll_secret=poll_secret,
        interval_s=_int_in(
            data["interval_s"], MIN_POLL_INTERVAL_S, MAX_POLL_INTERVAL_S
        ),
        expires_in_s=_int_in(data["expires_in_s"], MIN_EXPIRES_IN_S, MAX_EXPIRES_IN_S),
    )


def parse_issued(data: Mapping[str, object]) -> str:
    _exact(data, frozenset({"token"}))
    token = data["token"]
    if not isinstance(token, str) or split_relay_token(token) is None:
        raise EnvelopeError(_MSG_DATA)
    return token


def parse_retry_after(data: Mapping[str, object]) -> int | None:
    """`{}` is a relay that stated none (`None`); otherwise exactly
    `{"retry_after_s": <non-negative int>}`."""
    if isinstance(data, Mapping) and not data:
        return None
    _exact(data, frozenset({"retry_after_s"}))
    return _int_in(data["retry_after_s"], 0, None)
