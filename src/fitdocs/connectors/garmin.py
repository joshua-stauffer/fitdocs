"""The Garmin connector (design.md "GarminConnector").

Pulls a Garmin account's activities and daily wellness with the athlete's own
Connect Personal API key. This module is the one module in the connectors
package that names the Personal API host (the service-neutral scan admits it
here and in its own tests only). It imports only the standard library and
``fitdocs.connectors.{errors,http,protocol,secrets}``, builds no HTTP client
of its own, and reads no clock.

Task 3.1 declares the connector and implements the key check. Task 3.2 adds
the per-pull state (one token, spacing, rate-limit waits) and the one helper
every Garmin GET goes through. The four pull operations are placeholders that
raise a named :class:`ConnectorError` and make no request, because the
registry requires them once the capabilities are declared; later tasks
replace them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final
from weakref import WeakKeyDictionary

from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.http import (
    HttpClient,
    HttpResponse,
    TransportError,
    auth_failure_from,
)
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    FetchResult,
    Granted,
    Listing,
    RemoteActivity,
    SettingsContext,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.secrets import Secret

GARMIN_CONNECTOR_ID: Final[str] = "garmin"
API_BASE: Final[str] = "https://personal.connectapi.garmin.com"
TOKEN_PATH: Final[str] = "/personalapitoken-service/personal-api/personal-api-key/token"
MAX_TOKEN_BYTES: Final[int] = 16 * 1024
REQUEST_SPACING_S: Final[float] = 1.0
RATE_LIMIT_WAITS_S: Final[tuple[float, ...]] = (30.0, 60.0, 120.0, 240.0)
MAX_STATED_WAIT_S: Final[float] = 300.0
MAX_WAITS_PER_PULL_S: Final[float] = 900.0

_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

REJECTED_MESSAGE: Final[str] = (
    "Garmin did not accept the Personal API key (HTTP {status}); the key may "
    "be wrong, expired or deleted. Create a new key on Garmin Connect, then "
    "run `fitdocs connect` again"
)
RATE_LIMITED_MESSAGE: Final[str] = (
    "Garmin is limiting requests (HTTP 429) and refused the key check"
)
UNAVAILABLE_MESSAGE: Final[str] = (
    "Garmin is unavailable or answered unexpectedly (HTTP {status}) to the token "
    "request"
)
NOT_A_TOKEN_MESSAGE: Final[str] = (
    "Garmin's answer to the token request was not understood: it succeeded but "
    "was not a token"
)
PULL_RATE_LIMITED_MESSAGE: Final[str] = (
    "Garmin is limiting requests (HTTP 429); the next pull resumes where this "
    "one stopped"
)
TOKEN_UNREACHABLE_MESSAGE: Final[str] = (
    "Garmin could not be reached for the token request; the next pull resumes "
    "where this one stopped"
)
NOT_BUILT_MESSAGE: Final[str] = (
    "the Garmin connector does not implement {operation} yet"
)


def _mint(session: ConnectorSession, client: HttpClient, key: Secret) -> Secret:
    """One token request with ``key``, in a single attempt (Req 1.2, 7.1, 7.2).

    Takes the client and the key as arguments because a connect session
    refuses ``credentials``. Returns the ``Bearer`` header value with both the
    bare token and that value registered with the session's redactor; every
    other answer is an :class:`AuthFailure` that never quotes the body."""
    response = client.post(
        API_BASE + TOKEN_PATH,
        body=b"",
        headers={"Accept": "*/*"},
        secret_headers={"Authorization": session.secret(f"ApiKey {key.reveal()}")},
        single_attempt=True,
    )
    if response.status == 200:
        token = _token_text(response.body)
        if token is None:
            raise AuthFailure(AuthFailureKind.UNAVAILABLE, NOT_A_TOKEN_MESSAGE)
        session.secret(token)
        return session.secret(f"Bearer {token}")
    if response.status in (401, 403):
        raise AuthFailure(
            AuthFailureKind.REJECTED, REJECTED_MESSAGE.format(status=response.status)
        )
    if response.status == 429:
        limited = auth_failure_from(response, service_message=RATE_LIMITED_MESSAGE)
        retry_after = limited.retry_after_s if limited is not None else None
        raise AuthFailure(
            AuthFailureKind.RATE_LIMITED, RATE_LIMITED_MESSAGE, retry_after
        )
    raise AuthFailure(
        AuthFailureKind.UNAVAILABLE, UNAVAILABLE_MESSAGE.format(status=response.status)
    )


def _token_text(body: bytes) -> str | None:
    """The token when ``body`` is three dot-separated base64url segments of at
    most :data:`MAX_TOKEN_BYTES`, else ``None``."""
    if len(body) > MAX_TOKEN_BYTES:
        return None
    try:
        text = body.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    return text if _TOKEN_RE.fullmatch(text) else None


@dataclass
class _PullState:
    """What one pull keeps between its requests (design.md "State
    Management"). Nothing here is ever written to disk. ``bearer`` is kept out
    of the repr, though a :class:`Secret` already masks itself."""

    bearer: Secret | None = field(default=None, repr=False)
    mint_error: ConnectorError | AuthFailure | None = None
    used: bool = False
    waited_s: float = 0.0
    consecutive_failures: int = 0


def _rate_limit_wait(
    stated: float | None, repeats: int, waited_s: float
) -> float | None:
    """The wait before repeating a request Garmin answered 429, or ``None``
    when waiting must stop (Req 4.7, 4.8): at most 4 repeats of one request,
    a stated wait of at most 5 minutes, and at most 15 minutes in the pull."""
    if repeats >= len(RATE_LIMIT_WAITS_S):
        return None
    if stated is None:
        wait = RATE_LIMIT_WAITS_S[repeats]
    elif stated > MAX_STATED_WAIT_S:
        return None
    else:
        wait = stated
    if waited_s + wait > MAX_WAITS_PER_PULL_S:
        return None
    return wait


def _not_built(operation: str) -> ConnectorError:
    return ConnectorError(NOT_BUILT_MESSAGE.format(operation=operation))


class GarminConnector:
    """Garmin activities and wellness through a Connect Personal API key."""

    connector_id = GARMIN_CONNECTOR_ID
    display_name = "Garmin"
    auth_style = AuthStyle.API_KEY
    capabilities = frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})
    credential_fields = (CredentialField("api_key", "Personal API key", True),)

    def __init__(self) -> None:
        # Keyed by the session's client, held weakly: after a successful mint
        # a pull's state goes with its client (Req 7.2). A failed mint's kept
        # error holds traceback frames that retain the client, so that state
        # stays until the process ends, which is harmless in a one-shot pull.
        self._pulls: WeakKeyDictionary[HttpClient, _PullState] = WeakKeyDictionary()

    def _state(self, session: ConnectorSession) -> _PullState:
        state = self._pulls.get(session.http)
        if state is None:
            state = _PullState()
            self._pulls[session.http] = state
        return state

    @staticmethod
    def _space(session: ConnectorSession, state: _PullState) -> None:
        """One second between distinct requests, none before the pull's first
        (Req 4.1)."""
        if state.used:
            session.sleep(REQUEST_SPACING_S)
        state.used = True

    def _bearer(self, session: ConnectorSession, state: _PullState) -> Secret:
        """The pull's ``Bearer`` header value: one token request at most, and
        a failed one is kept and raised again with no second request (Req 7.2).

        A 401 or 403 answer is the rejected-key failure and a 429 the
        rate-limit failure, so wellness is suppressed after those; anything
        else is a :class:`ConnectorError`."""
        if state.mint_error is not None:
            raise state.mint_error
        if state.bearer is not None:
            return state.bearer
        self._space(session, state)
        try:
            state.bearer = _mint(
                session, session.http, session.credentials.value("api_key")
            )
        except AuthFailure as failure:
            if failure.kind is AuthFailureKind.RATE_LIMITED:
                state.mint_error = AuthFailure(
                    AuthFailureKind.RATE_LIMITED,
                    PULL_RATE_LIMITED_MESSAGE,
                    failure.retry_after_s,
                )
            elif failure.kind is AuthFailureKind.REJECTED:
                state.mint_error = failure
            else:
                state.mint_error = ConnectorError(failure.service_message)
            raise state.mint_error from None
        except TransportError:
            state.mint_error = ConnectorError(TOKEN_UNREACHABLE_MESSAGE)
            raise state.mint_error from None
        return state.bearer

    def _get(
        self,
        session: ConnectorSession,
        url: str,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        """Every Garmin GET: the pull's token, 1 s of spacing, the transport's
        429 retries off, and the rate-limit waits of Req 4.7 to 4.9.

        Any answer but 429 goes back to the caller. A repeat after a wait gets
        no extra spacing."""
        state = self._state(session)
        bearer = self._bearer(session, state)
        self._space(session, state)
        repeats = 0
        while True:
            response = session.http.get(
                url,
                headers=headers,
                secret_headers={"Authorization": bearer},
                retry_rate_limits=False,
            )
            if response.status != 429:
                return response
            limited = auth_failure_from(response)
            stated = limited.retry_after_s if limited is not None else None
            wait = _rate_limit_wait(stated, repeats, state.waited_s)
            if wait is None:
                raise AuthFailure(
                    AuthFailureKind.RATE_LIMITED, PULL_RATE_LIMITED_MESSAGE, stated
                )
            session.sleep(wait)
            state.waited_s += wait
            repeats += 1

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> None:
        """Accepts nothing and ignores every key (Req 1.7, 2.1, 2.2)."""
        return None

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        """Mint one token with the key and discard it (Req 1.2, 1.3): scopes
        are absent, not empty, and a key's expiry is never known."""
        _mint(session, session.http, values["api_key"])
        return Granted(scopes=None)

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        raise _not_built("the activity listing")

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        raise _not_built("the activity download")

    def list_wellness(
        self, session: ConnectorSession, oldest: date | None
    ) -> WellnessListing:
        raise _not_built("the wellness listing")

    def package_wellness(
        self, session: ConnectorSession, days: tuple[WellnessDay, ...]
    ) -> WellnessPackage:
        raise _not_built("wellness packaging")
