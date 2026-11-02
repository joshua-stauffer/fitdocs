"""Connect sessions, the page claim, the callback and the poll (ConnectFlow).

A session is a handful of expiring records in the `core.connect` namespace of
the record store, all ending together at the session's expiry. A browser claims
a session by opening its page; only that browser's callback is accepted, and the
callback is checked against the claim before its state is taken, so another
browser cannot spend a session's state. The poll issues the connection token
once. The state is taken before the code is exchanged, so a second callback
with the same state finds it gone; a limited answer to the exchange is recorded
in the budget, and a failure after the state is taken leaves the poll a refusal.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from fitdocs_relay.identity import TokenService
from fitdocs_relay.shared.relay_envelope import is_user_code
from fitdocs_relay.shared.relay_targets import STRAVA
from fitdocs_relay.storage.interface import DuplicateIdentifier, Storage
from fitdocs_relay.strava.api import (
    REQUESTED_SCOPES,
    Failure,
    StravaApi,
    StravaFailure,
)
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.custody import Custody

CONNECT_INTERVAL_S: Final = 3
CONNECT_EXPIRES_IN_S: Final = 600
RECORD_NAMESPACE: Final = "core.connect"
CLAIM_COOKIE: Final = "fitdocs_connect"
CONNECTION_TOKEN_LABEL: Final = "connection:strava"
EXCHANGE_TIMEOUT_S: Final = 8.0
CALLBACK_PATH: Final = "/strava/callback"

_CODE_ALPHABET: Final = "BCDFGHJKLMNPQRSTVWXZ"
_CODE_ATTEMPTS: Final = 16
_GRANTED: Final = b"granted"
_REFUSED: Final = b"refused"


@dataclass(frozen=True)
class Started:
    user_code: str
    poll_secret: str = field(repr=False)
    interval_s: int
    expires_in_s: int


@dataclass(frozen=True)
class ShowConsent:
    """The page to show. `set_cookie` is a whole `Set-Cookie` header value, given
    to the browser that has just claimed the session and to no other."""

    user_code: str
    authorize_url: str
    set_cookie: str | None = field(repr=False)


class PageOutcome(StrEnum):
    INVALID = "invalid"
    IN_USE = "in-use"


class CallbackOutcome(StrEnum):
    GRANTED = "granted"
    REFUSED = "refused"
    INVALID = "invalid"


@dataclass(frozen=True)
class PollGranted:
    token: str = field(repr=False)


class PollOutcome(StrEnum):
    PENDING = "pending"
    REFUSED = "refused"
    EXPIRED = "expired"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _random_code() -> str:
    left = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    right = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
    return f"{left}-{right}"


@dataclass(frozen=True)
class _Session:
    user_code: str
    principal_id: str
    poll_hash: str
    state: str
    expires_at: int


class ConnectFlow:
    def __init__(
        self,
        storage: Storage,
        tokens: TokenService,
        custody: Custody,
        api: StravaApi,
        budget: StravaBudget,
        *,
        public_url: str,
        clock: Callable[[], int],
        user_codes: Callable[[], str] | None = None,
    ) -> None:
        self._storage = storage
        self._tokens = tokens
        self._custody = custody
        self._api = api
        self._budget = budget
        self._base = public_url.rstrip("/")
        self._clock = clock
        self._user_codes = user_codes or _random_code

    # --- records ---------------------------------------------------------

    def _put(self, key: str, value: bytes, expires_at: int) -> None:
        self._storage.put_record(
            namespace=RECORD_NAMESPACE,
            key=key,
            value=value,
            expires_at=expires_at,
            now=self._clock(),
        )

    def _get(self, key: str) -> bytes | None:
        return self._storage.get_record(
            namespace=RECORD_NAMESPACE, key=key, now=self._clock()
        )

    def _take(self, key: str) -> bytes | None:
        return self._storage.take_record(
            namespace=RECORD_NAMESPACE, key=key, now=self._clock()
        )

    def _delete(self, key: str) -> None:
        self._storage.delete_record(namespace=RECORD_NAMESPACE, key=key)

    def _session(self, user_code: str) -> _Session | None:
        raw = self._get(f"session:{user_code}")
        if raw is None:
            return None
        body: Any = json.loads(raw)
        return _Session(
            user_code,
            body["principal"],
            body["poll"],
            body["state"],
            body["expires_at"],
        )

    def _end(self, session: _Session) -> None:
        for key in (
            f"session:{session.user_code}",
            f"unclaimed:{session.user_code}",
            f"claim:{session.user_code}",
            f"poll:{session.poll_hash}",
            f"state:{_hash(session.state)}",
            f"result:{session.poll_hash}",
        ):
            self._delete(key)

    def _claimed_by(self, user_code: str, cookie: str | None) -> bool:
        claim = self._get(f"claim:{user_code}")
        if claim is None or cookie is None:
            return False
        return hmac.compare_digest(_hash(cookie).encode("ascii"), claim)

    # --- the flow --------------------------------------------------------

    def start(self, principal_id: str) -> Started:
        now = self._clock()
        expires_at = now + CONNECT_EXPIRES_IN_S
        for _ in range(_CODE_ATTEMPTS):
            user_code = self._user_codes()
            if self._get(f"session:{user_code}") is None:
                break
        else:
            raise RuntimeError("no free user code")
        poll_secret = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        poll_hash = _hash(poll_secret)
        session = json.dumps(
            {
                "principal": principal_id,
                "target": STRAVA,
                "poll": poll_hash,
                "state": state,
                "expires_at": expires_at,
            }
        ).encode("utf-8")
        self._put(f"session:{user_code}", session, expires_at)
        self._put(f"unclaimed:{user_code}", b"1", expires_at)
        self._put(f"poll:{poll_hash}", user_code.encode("ascii"), expires_at)
        self._put(f"state:{_hash(state)}", user_code.encode("ascii"), expires_at)
        return Started(user_code, poll_secret, CONNECT_INTERVAL_S, CONNECT_EXPIRES_IN_S)

    def _consent(self, session: _Session, set_cookie: str | None) -> ShowConsent:
        url = self._api.authorize_url(
            state=session.state, redirect_uri=f"{self._base}{CALLBACK_PATH}"
        )
        return ShowConsent(session.user_code, url, set_cookie)

    def page(
        self, user_code: str | None, cookie: str | None
    ) -> ShowConsent | PageOutcome:
        if user_code is None or not is_user_code(user_code):
            return PageOutcome.INVALID
        session = self._session(user_code)
        if session is None:
            return PageOutcome.INVALID
        if self._take(f"unclaimed:{user_code}") is not None:
            fresh = secrets.token_urlsafe(32)
            self._put(
                f"claim:{user_code}", _hash(fresh).encode("ascii"), session.expires_at
            )
            return self._consent(session, self._set_cookie(fresh, session.expires_at))
        if self._claimed_by(user_code, cookie):
            return self._consent(session, None)
        return PageOutcome.IN_USE

    def _set_cookie(self, value: str, expires_at: int) -> str:
        attributes = [
            f"{CLAIM_COOKIE}={value}",
            f"Max-Age={expires_at - self._clock()}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self._base.startswith("https://"):
            attributes.append("Secure")
        return "; ".join(attributes)

    def callback(
        self,
        *,
        state: str | None,
        code: str | None,
        scope: str | None,
        error: str | None,
        cookie: str | None,
    ) -> CallbackOutcome:
        if not state:
            return CallbackOutcome.INVALID
        state_hash = _hash(state)
        found = self._get(f"state:{state_hash}")
        if found is None:
            return CallbackOutcome.INVALID
        user_code = found.decode("ascii")
        session = self._session(user_code)
        if session is None or not self._claimed_by(user_code, cookie):
            return CallbackOutcome.INVALID
        if self._take(f"state:{state_hash}") is None:
            return CallbackOutcome.INVALID
        try:
            if self._granted(session, code, scope, error):
                self._put(f"result:{session.poll_hash}", _GRANTED, session.expires_at)
                return CallbackOutcome.GRANTED
        except BaseException:
            # The state is already taken: leave the poll a refusal to answer
            # rather than a session that can only wait for its expiry.
            with suppress(Exception):
                self._put(f"result:{session.poll_hash}", _REFUSED, session.expires_at)
            raise
        self._put(f"result:{session.poll_hash}", _REFUSED, session.expires_at)
        return CallbackOutcome.REFUSED

    def _granted(
        self, session: _Session, code: str | None, scope: str | None, error: str | None
    ) -> bool:
        if error is not None or code is None or scope is None:
            return False
        if not set(REQUESTED_SCOPES) <= set(scope.split(",")):
            return False
        if not self._budget.spend(session.principal_id).allowed:
            return False
        grant = self._api.exchange(code, timeout=EXCHANGE_TIMEOUT_S)
        if isinstance(grant, StravaFailure):
            if grant.failure is Failure.LIMITED:
                self._budget.mark_spent(daily=grant.daily_spent)
            return False
        self._custody.store_grant(session.principal_id, grant)
        return True

    def poll(self, principal_id: str, poll_secret: str) -> PollGranted | PollOutcome:
        poll_hash = _hash(poll_secret)
        found = self._get(f"poll:{poll_hash}")
        if found is None:
            return PollOutcome.EXPIRED
        session = self._session(found.decode("ascii"))
        if session is None or session.principal_id != principal_id:
            return PollOutcome.EXPIRED
        result = self._take(f"result:{poll_hash}")
        if result is None:
            return PollOutcome.PENDING
        if result != _GRANTED:
            self._end(session)
            return PollOutcome.REFUSED
        try:
            issued = self._issue(principal_id)
        except BaseException:
            self._put(f"result:{poll_hash}", result, session.expires_at)
            raise
        self._end(session)
        return PollOutcome.EXPIRED if issued is None else PollGranted(issued)

    def _issue(self, principal_id: str) -> str | None:
        """The new connection token, or None when the principal has no connection."""
        try:
            return self._issue_once(principal_id)
        except DuplicateIdentifier:
            return self._issue_once(principal_id)

    def _issue_once(self, principal_id: str) -> str | None:
        prepared = self._tokens.prepare(label=CONNECTION_TOKEN_LABEL)
        record = self._storage.issue_connection_token(
            principal_id, STRAVA, prepared.new_token, now=self._clock()
        )
        return None if record is None else prepared.token
