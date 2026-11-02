"""The one adapter that speaks Strava (StravaApi).

It returns typed values or a `StravaFailure` naming a failure class, never
text: no byte of an answer's body, header or status text outlives the call
except the fields a step needs, read by structure. The access and refresh
tokens travel in a request header or in the form body Strava documents for
the token and revoke endpoints, never in an address.

This module covers the authorization address, the code exchange, the refresh
and the revoke call, the activity listing and update, the upload and its
state, the subscription calls, and `classify`, the one place an answer
becomes a failure class.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from base64 import b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
MAX_STRAVA_ID: Final = 2**63
MAX_MEASURE: Final = 10**12


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


@dataclass(frozen=True)
class Candidate:
    activity_id: str = field(repr=False)
    sport_type: str | None
    start: datetime
    elapsed_s: float | None
    distance_m: float | None


@dataclass(frozen=True)
class Listing:
    candidates: tuple[Candidate, ...]
    full: bool


@dataclass(frozen=True)
class UploadState:
    activity_id: str | None = field(repr=False)
    failed: bool


class SubscriptionState(StrEnum):
    ABSENT = "absent"
    OURS = "ours"
    OTHER = "other"


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


def _strava_id(value: object) -> int | None:
    return _whole(value, MAX_STRAVA_ID)


_ABSENT: Final = object()


def _measure(entry: dict[str, Any], key: str) -> float | None | object:
    """A non-negative finite number, None when absent or null, `_ABSENT` when
    present but not such a number."""
    value = entry.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return _ABSENT
    if isinstance(value, int):
        return float(value) if 0 <= value <= MAX_MEASURE else _ABSENT
    return value if math.isfinite(value) and 0 <= value <= MAX_MEASURE else _ABSENT


def _start(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        return parsed.astimezone(UTC)
    except (OverflowError, ValueError):
        return None


def _candidate(entry: object) -> Candidate | None:
    """One listed activity; its id and start are needed, the rest may be absent."""
    if not isinstance(entry, dict):
        return None
    identifier = _strava_id(entry.get("id"))
    start = _start(entry.get("start_date"))
    sport = entry.get("sport_type")
    elapsed = _measure(entry, "elapsed_time")
    distance = _measure(entry, "distance")
    if identifier is None or start is None:
        return None
    if sport is not None and (not isinstance(sport, str) or len(sport) > 64):
        return None
    if elapsed is _ABSENT or distance is _ABSENT:
        return None
    assert elapsed is None or isinstance(elapsed, float)
    assert distance is None or isinstance(distance, float)
    return Candidate(str(identifier), sport, start, elapsed, distance)


def _candidates(payload: object) -> tuple[Candidate, ...] | None:
    if not isinstance(payload, list):
        return None
    found = tuple(_candidate(entry) for entry in payload)
    if any(candidate is None for candidate in found):
        return None
    return tuple(c for c in found if c is not None)


def _upload_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    identifier = _strava_id(payload.get("id"))
    return None if identifier is None else str(identifier)


def _upload_state(payload: object) -> UploadState | None:
    """Failed when `error` is non-null, whatever it says; otherwise ready when
    `activity_id` is a whole number and pending when it is null or absent;
    None (unreadable) for any other `activity_id` or a body that is not an
    object."""
    if not isinstance(payload, dict):
        return None
    if payload.get("error") is not None:
        return UploadState(None, True)
    activity = payload.get("activity_id")
    if activity is None:
        return UploadState(None, False)
    identifier = _strava_id(activity)
    return None if identifier is None else UploadState(str(identifier), False)


def _subscription_entries(payload: object) -> tuple[tuple[str, str], ...] | None:
    """(id, callback address) of each listed subscription."""
    if not isinstance(payload, list):
        return None
    found: list[tuple[str, str]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            return None
        identifier = _strava_id(entry.get("id"))
        callback = entry.get("callback_url")
        if identifier is None or not isinstance(callback, str):
            return None
        found.append((str(identifier), callback))
    return tuple(found)


# What a 2xx must hold for the step to count as answered. A step missing here
# (revoke, update, subscription) needs nothing from its body; the subscription
# view reads its list itself.
_NEEDS: Final[Mapping[Step, Callable[[object], bool]]] = {
    Step.EXCHANGE: lambda payload: _grant(payload) is not None,
    Step.REFRESH: lambda payload: _pair(payload) is not None,
    Step.LIST: lambda payload: _candidates(payload) is not None,
    Step.UPLOAD: lambda payload: _upload_id(payload) is not None,
    Step.UPLOAD_STATUS: lambda payload: _upload_state(payload) is not None,
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

    def list_activities(
        self, access: str, *, after: int, before: int, per_page: int, timeout: float
    ) -> Listing | StravaFailure:
        query = urlencode(
            {"after": after, "before": before, "per_page": per_page, "page": 1}
        )
        request = self._get(f"/athlete/activities?{query}", self._bearer(access))
        answer = self._call(request, timeout)
        failure = self._failure(Step.LIST, answer)
        if failure is not None:
            return failure
        assert isinstance(answer, OutboundResponse)
        found = _candidates(_json(answer.body))
        assert found is not None  # classify read the same body
        return Listing(found, len(found) >= per_page)

    def update_activity(
        self,
        access: str,
        activity_id: str,
        *,
        name: str,
        description: str,
        timeout: float,
    ) -> None | StravaFailure:
        request = OutboundRequest(
            method="PUT",
            url=f"{self._config.api_url}/activities/{quote(activity_id, safe='')}",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            secret_headers=self._bearer(access),
            body=json.dumps({"name": name, "description": description}).encode("utf-8"),
            url_is_secret=True,
        )
        return self._failure(Step.UPDATE, self._call(request, timeout))

    def create_upload(
        self,
        access: str,
        *,
        fit: bytes,
        name: str,
        description: str,
        external_id: str,
        timeout: float,
    ) -> str | StravaFailure:
        boundary, body = _multipart(
            [
                ("data_type", "fit"),
                ("name", name),
                ("description", description),
                ("external_id", external_id),
            ],
            fit,
        )
        request = OutboundRequest(
            method="POST",
            url=f"{self._config.api_url}/uploads",
            headers={
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            secret_headers=self._bearer(access),
            body=body,
        )
        answer = self._call(request, timeout)
        failure = self._failure(Step.UPLOAD, answer)
        if failure is not None:
            return failure
        assert isinstance(answer, OutboundResponse)
        upload = _upload_id(_json(answer.body))
        assert upload is not None  # classify read the same body
        return upload

    def upload_state(
        self, access: str, upload_id: str, *, timeout: float
    ) -> UploadState | StravaFailure:
        request = self._get(
            f"/uploads/{quote(upload_id, safe='')}",
            self._bearer(access),
            url_is_secret=True,
        )
        answer = self._call(request, timeout)
        failure = self._failure(Step.UPLOAD_STATUS, answer)
        if failure is not None:
            return failure
        assert isinstance(answer, OutboundResponse)
        state = _upload_state(_json(answer.body))
        assert state is not None  # classify read the same body
        return state

    def subscription_state(
        self, *, callback_url: str, timeout: float
    ) -> SubscriptionState | StravaFailure:
        entries = self._subscriptions(timeout)
        if isinstance(entries, StravaFailure):
            return entries
        if not entries:
            return SubscriptionState.ABSENT
        if all(callback == callback_url for _, callback in entries):
            return SubscriptionState.OURS
        return SubscriptionState.OTHER

    def create_subscription(
        self, *, callback_url: str, timeout: float
    ) -> None | StravaFailure:
        request = OutboundRequest(
            method="POST",
            url=f"{self._config.api_url}/push_subscriptions",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            secret_headers={},
            body=urlencode(
                {
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "callback_url": callback_url,
                    "verify_token": self._config.webhook_token,
                }
            ).encode("utf-8"),
        )
        return self._failure(Step.SUBSCRIPTION, self._call(request, timeout))

    def delete_subscription(self, *, timeout: float) -> bool | StravaFailure:
        entries = self._subscriptions(timeout)
        if isinstance(entries, StravaFailure):
            return entries
        for identifier, _ in entries:
            request = OutboundRequest(
                method="DELETE",
                url=f"{self._config.api_url}/push_subscriptions/{identifier}?"
                + self._client_query(),
                headers={"Accept": "application/json"},
                secret_headers={},
                url_is_secret=True,
            )
            failure = self._failure(Step.SUBSCRIPTION, self._call(request, timeout))
            if failure is not None:
                return failure
        return bool(entries)

    # --- plumbing -------------------------------------------------------

    def _subscriptions(
        self, timeout: float
    ) -> tuple[tuple[str, str], ...] | StravaFailure:
        request = OutboundRequest(
            method="GET",
            url=f"{self._config.api_url}/push_subscriptions?" + self._client_query(),
            headers={"Accept": "application/json"},
            secret_headers={},
            url_is_secret=True,
        )
        answer = self._call(request, timeout)
        failure = self._failure(Step.SUBSCRIPTION, answer)
        if failure is not None:
            return failure
        assert isinstance(answer, OutboundResponse)
        entries = _subscription_entries(_json(answer.body))
        if entries is None:
            return StravaFailure(Step.SUBSCRIPTION, Failure.UNREADABLE)
        return entries

    def _client_query(self) -> str:
        return urlencode(
            {
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
            }
        )

    @staticmethod
    def _bearer(access: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access}"}

    def _get(
        self, path: str, secret: Mapping[str, str], *, url_is_secret: bool = False
    ) -> OutboundRequest:
        return OutboundRequest(
            method="GET",
            url=f"{self._config.api_url}{path}",
            headers={"Accept": "application/json"},
            secret_headers=secret,
            url_is_secret=url_is_secret,
        )

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


def _multipart(fields: list[tuple[str, str]], fit: bytes) -> tuple[str, bytes]:
    """A multipart/form-data body: the text fields, then the file last."""
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii")
            + value.encode("utf-8")
        )
    parts.append(
        b'Content-Disposition: form-data; name="file"; filename="activity.fit"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n" + fit
    )
    while True:
        boundary = f"fitdocs-{uuid.uuid4().hex}"
        if not any(boundary.encode("ascii") in part for part in parts):
            break
    body = b"".join(
        b"--" + boundary.encode("ascii") + b"\r\n" + p + b"\r\n" for p in parts
    )
    return boundary, body + b"--" + boundary.encode("ascii") + b"--\r\n"
