"""The one adapter that speaks Strava (StravaApi).

It returns typed values or a `StravaFailure` naming a failure class, never
text: no byte of an answer's body, header or status text outlives the call
except the fields a step needs, read by structure. The access and refresh
tokens travel in a request header or in the form body Strava documents for
the token and revoke endpoints, never in an address.

This module covers the authorization address, the code exchange, the refresh
and the revoke call, and `classify`, the one place an answer becomes a failure
class.
"""

from __future__ import annotations

import json
import re
from base64 import b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final
from urllib.parse import quote, urlencode

from fitdocs_relay.outbound import (
    Outbound,
    OutboundError,
    OutboundRequest,
    OutboundResponse,
)
from fitdocs_relay.strava.config import Limits, StravaConfig

REQUESTED_SCOPES: Final = ("activity:read_all", "activity:write")

MAX_TOKEN_CHARS: Final = 4096
MAX_EXPIRES_AT: Final = 10**12
MAX_ATHLETE_ID: Final = 10**18


class Step(StrEnum):
    EXCHANGE = "exchange"
    REFRESH = "refresh"
    REVOKE = "revoke"
    LIST = "list"
    UPDATE = "update"
    UPLOAD = "upload"
    UPLOAD_STATUS = "upload-status"
    SUBSCRIPTION = "subscription"


class Failure(StrEnum):
    AUTH = "auth"
    FORBIDDEN = "forbidden"
    MISSING = "missing"
    LIMITED = "limited"
    INVALID = "invalid"
    SERVER = "server"
    NETWORK = "network"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class StravaFailure:
    step: Step
    failure: Failure
    daily_spent: bool = False


@dataclass(frozen=True)
class Grant:
    access: str = field(repr=False)
    refresh: str = field(repr=False)
    expires_at: int
    athlete_id: str = field(repr=False)


@dataclass(frozen=True)
class TokenPair:
    access: str = field(repr=False)
    refresh: str = field(repr=False)
    expires_at: int


# --- reading an answer's body, by structure ----------------------------------


def _json(body: bytes) -> Any:
    """The body as JSON, or None when it is not readable JSON.

    Strict UTF-8; a nesting too deep or a number too long is "not readable",
    never an exception."""
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None


def _whole(value: object, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= high else None


def _token(value: object) -> str | None:
    if (
        isinstance(value, str)
        and 0 < len(value) <= MAX_TOKEN_CHARS
        and value.isascii()
        and value.isprintable()
        and not any(ch.isspace() for ch in value)
    ):
        return value
    return None


def _pair(payload: object) -> TokenPair | None:
    if not isinstance(payload, dict):
        return None
    access = _token(payload.get("access_token"))
    refresh = _token(payload.get("refresh_token"))
    expires_at = _whole(payload.get("expires_at"), MAX_EXPIRES_AT)
    if access is None or refresh is None or expires_at is None:
        return None
    return TokenPair(access, refresh, expires_at)


def _grant(payload: object) -> Grant | None:
    pair = _pair(payload)
    if pair is None or not isinstance(payload, dict):
        return None
    athlete = payload.get("athlete")
    athlete_id = (
        _whole(athlete.get("id"), MAX_ATHLETE_ID) if isinstance(athlete, dict) else None
    )
    if athlete_id is None:
        return None
    return Grant(pair.access, pair.refresh, pair.expires_at, str(athlete_id))


def _is_object(payload: object) -> bool:
    return isinstance(payload, dict)


def _is_object_with_id(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("id") is not None


def _is_list(payload: object) -> bool:
    return isinstance(payload, list)


# What a 2xx must hold for the step to count as answered. A step missing here
# (revoke, update, subscription) needs nothing from its body.
_NEEDS: Final[Mapping[Step, Callable[[object], bool]]] = {
    Step.EXCHANGE: lambda payload: _grant(payload) is not None,
    Step.REFRESH: lambda payload: _pair(payload) is not None,
    Step.LIST: _is_list,
    Step.UPLOAD: _is_object_with_id,
    Step.UPLOAD_STATUS: _is_object,
}


def classify(step: Step, response: OutboundResponse | OutboundError) -> Failure | None:
    """The failure class of an answer, or None when it succeeded.

    An `OutboundError` of any kind is NETWORK; 401 AUTH; 403 FORBIDDEN; 404
    MISSING; 429 LIMITED; any other 4xx (the token endpoint's 400 included)
    INVALID; 5xx SERVER. A 2xx whose body lacks what the step needs is
    UNREADABLE. Any other status (1xx, 3xx, outside 100 to 599) is INVALID: a
    request with a body never follows a redirect, so a 3xx is an answer that
    did nothing."""
    if isinstance(response, OutboundError):
        return Failure.NETWORK
    status = response.status
    if 200 <= status < 300:
        needs = _NEEDS.get(step)
        if needs is not None and not needs(_json(response.body)):
            return Failure.UNREADABLE
        return None
    if status == 401:
        return Failure.AUTH
    if status == 403:
        return Failure.FORBIDDEN
    if status == 404:
        return Failure.MISSING
    if status == 429:
        return Failure.LIMITED
    if 500 <= status < 600:
        return Failure.SERVER
    return Failure.INVALID


_USAGE: Final = re.compile(r"\s*([0-9]{1,12})\s*,\s*([0-9]{1,12})\s*")


def _daily_figure(headers: Mapping[str, str], name: str) -> int | None:
    match = _USAGE.fullmatch(headers.get(name, ""))
    return int(match.group(2)) if match else None


def daily_spent(response: OutboundResponse, limits: Limits) -> bool:
    """Whether a usage header's daily figure has reached its daily limit.

    `x-ratelimit-usage` is read against the overall daily limit and
    `x-readratelimit-usage` against the non-upload one; both report
    "<15 minutes>,<day>". Only the verdict leaves this function."""
    overall = _daily_figure(response.headers, "x-ratelimit-usage")
    read = _daily_figure(response.headers, "x-readratelimit-usage")
    return (overall is not None and overall >= limits.overall_day) or (
        read is not None and read >= limits.read_day
    )


class StravaApi:
    def __init__(self, config: StravaConfig, *, outbound: Outbound) -> None:
        self._config = config
        self._outbound = outbound

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        query = "&".join(
            (
                f"client_id={quote(self._config.client_id, safe='')}",
                f"redirect_uri={quote(redirect_uri, safe='')}",
                "response_type=code",
                "approval_prompt=auto",
                f"scope={','.join(REQUESTED_SCOPES)}",
                f"state={quote(state, safe='')}",
            )
        )
        return f"{self._config.oauth_url}/authorize?{query}"

    def exchange(self, code: str, *, timeout: float) -> Grant | StravaFailure:
        request = self._form(
            "token",
            {
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        answer = self._call(request, timeout)
        failure = self._failure(Step.EXCHANGE, answer)
        if failure is not None:
            return failure
        assert isinstance(answer, OutboundResponse)
        grant = _grant(_json(answer.body))
        assert grant is not None  # classify read the same body
        return grant

    def refresh(
        self, refresh_token: str, *, timeout: float
    ) -> TokenPair | StravaFailure:
        request = self._form(
            "token",
            {
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        answer = self._call(request, timeout)
        failure = self._failure(Step.REFRESH, answer)
        if failure is not None:
            return failure
        assert isinstance(answer, OutboundResponse)
        pair = _pair(_json(answer.body))
        assert pair is not None  # classify read the same body
        return pair

    def revoke(self, token: str, *, timeout: float) -> None | StravaFailure:
        basic = b64encode(
            f"{self._config.client_id}:{self._config.client_secret}".encode()
        ).decode("ascii")
        request = self._form(
            "revoke", {"token": token}, secret={"Authorization": f"Basic {basic}"}
        )
        return self._failure(Step.REVOKE, self._call(request, timeout))

    # --- plumbing -------------------------------------------------------

    def _form(
        self,
        path: str,
        fields: Mapping[str, str],
        *,
        secret: Mapping[str, str] | None = None,
    ) -> OutboundRequest:
        return OutboundRequest(
            method="POST",
            url=f"{self._config.oauth_url}/{path}",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            secret_headers=secret or {},
            body=urlencode(fields).encode("ascii"),
        )

    def _call(
        self, request: OutboundRequest, timeout: float
    ) -> OutboundResponse | OutboundError:
        try:
            return self._outbound(request, timeout)
        except OutboundError as error:
            return error

    def _failure(
        self, step: Step, answer: OutboundResponse | OutboundError
    ) -> StravaFailure | None:
        failure = classify(step, answer)
        if failure is None:
            return None
        spent = (
            failure is Failure.LIMITED
            and isinstance(answer, OutboundResponse)
            and daily_spent(answer, self._config.limits)
        )
        return StravaFailure(step, failure, spent)
