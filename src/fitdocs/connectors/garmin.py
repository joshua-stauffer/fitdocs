"""The Garmin connector (design.md "GarminConnector").

Pulls a Garmin account's activities and daily wellness with the athlete's own
Connect Personal API key. This module is the one module in the connectors
package that names the Personal API host (the service-neutral scan admits it
here and in its own tests only). It imports only the standard library and
``fitdocs.connectors.{errors,http,protocol,secrets}``, builds no HTTP client
of its own, and reads no clock.

Task 3.1 declares the connector and implements the key check. The four pull
operations are placeholders that raise a named :class:`ConnectorError` and
make no request, because the registry requires them once the capabilities are
declared; later tasks replace them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Final

from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.http import HttpClient, auth_failure_from
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
    "Garmin is unavailable or answered unexpectedly (HTTP {status}) to the key check"
)
NOT_A_TOKEN_MESSAGE: Final[str] = (
    "Garmin's answer to the key check was not understood: it succeeded but "
    "was not a token"
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


def _not_built(operation: str) -> ConnectorError:
    return ConnectorError(NOT_BUILT_MESSAGE.format(operation=operation))


class GarminConnector:
    """Garmin activities and wellness through a Connect Personal API key."""

    connector_id = GARMIN_CONNECTOR_ID
    display_name = "Garmin"
    auth_style = AuthStyle.API_KEY
    capabilities = frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})
    credential_fields = (CredentialField("api_key", "Personal API key", True),)

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
