"""The built-in ``relay`` connector and the envelope client it speaks through
(relay-server design.md "RelayConnector and RelayClient").

This module is the one module in the connectors package that names the
maintainer's relay address (the service-neutral scan admits it here and in its
own tests). It imports only the standard library and
``fitdocs.connectors.{errors,http,protocol,relay_codes,relay_envelope,secrets}``,
builds no HTTP client of its own, and reads no clock: ``session.now`` is the
only time source.

:class:`RelayClient` never raises for a relay's answer. The relay token
travels only as a secret (unredirected) credential header; a body that is not
a valid envelope falls back on the HTTP status; an answer's data is exposed
only so a caller can parse it with the codec's parsers, and is never printed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Final
from urllib.parse import urlsplit

from fitdocs.connectors.errors import ConnectorError, ConnectorSettingsError
from fitdocs.connectors.http import HttpClient, HttpResponse, TransportError
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    RegistrationPolled,
    RegistrationStarted,
    RelayCapabilities,
    RelayRefused,
    SettingsContext,
)
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.relay_envelope import (
    ROUTE_CAPABILITIES,
    ROUTE_REGISTRATION_POLL,
    ROUTE_REGISTRATIONS,
    ROUTE_TOKEN,
    ROUTE_TOKEN_REVOKE,
    EnvelopeError,
    decode_answer,
    encode_request,
    parse_capabilities,
    parse_issued,
    parse_retry_after,
    parse_started,
)
from fitdocs.connectors.secrets import Secret

RELAY_CONNECTOR_ID: Final = "relay"
DEFAULT_RELAY_URL: Final = "https://api.fitdocs.ai"
TOKEN_FIELD: Final = "token"

_LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})
_JSON: Final = "application/json"
_WHOLE_SECONDS: Final = re.compile(r"[0-9]+")

URL_NOT_ABSOLUTE_MESSAGE: Final = "url must be an absolute http or https URL"
URL_NOT_HTTPS_MESSAGE: Final = (
    "url must use https; http is accepted only for localhost, 127.0.0.1 and ::1"
)
URL_QUERY_MESSAGE: Final = "url must not carry a query"
URL_FRAGMENT_MESSAGE: Final = "url must not carry a fragment"
URL_USERINFO_MESSAGE: Final = "url must not carry user information"
URL_INVALID_MESSAGE: Final = "url is not a valid URL"

# Codes that mean "success" for some route: arriving where the route does not
# expect them, they are an answer of another route, not a refusal.
_SUCCESS_SHAPED: Final = frozenset(
    {
        RelayCode.OK,
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
    }
)


@dataclass(frozen=True)
class RelaySettings:
    """Validated ``[connectors.<instance>]`` configuration for a ``relay``
    instance."""

    url: str


@dataclass(frozen=True)
class RelayReply:
    """One relay answer, or the fitdocs-concluded code standing in for one.
    ``data`` is untrusted: callers parse it and never print it."""

    code: RelayCode
    data: Mapping[str, object]
    outcome: str | None
    retry_after_s: int | None


def _url_error(message: str) -> ConnectorSettingsError:
    # Never interpolates the value: a URL may carry a password.
    return ConnectorSettingsError("url", message)


def _normalised_url(value: object) -> str:
    """The URL the rules accept, trailing slash stripped; a refused value
    raises a :class:`ConnectorSettingsError` naming ``url`` that does not
    repeat the value."""
    if not isinstance(value, str):
        raise _url_error(URL_INVALID_MESSAGE)
    if any(ord(char) <= 0x20 or ord(char) >= 0x7F for char in value):
        raise _url_error(URL_INVALID_MESSAGE)
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise _url_error(URL_INVALID_MESSAGE) from None
    del port
    if not parts.scheme or not parts.netloc:
        raise _url_error(URL_NOT_ABSOLUTE_MESSAGE)
    if parts.scheme not in {"http", "https"}:
        raise _url_error(URL_NOT_HTTPS_MESSAGE)
    if "@" in parts.netloc:
        raise _url_error(URL_USERINFO_MESSAGE)
    host = parts.hostname
    if not host:
        raise _url_error(URL_NOT_ABSOLUTE_MESSAGE)
    if "#" in value:
        raise _url_error(URL_FRAGMENT_MESSAGE)
    if "?" in value:
        raise _url_error(URL_QUERY_MESSAGE)
    if parts.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise _url_error(URL_NOT_HTTPS_MESSAGE)
    return value.rstrip("/")


def _stated_wait(headers: Mapping[str, str]) -> int | None:
    """A ``Retry-After`` that is a whole number of seconds, else ``None``."""
    value = headers.get("retry-after")
    if value is None or _WHOLE_SECONDS.fullmatch(value.strip()) is None:
        return None
    return int(value.strip())


def _malformed() -> RelayReply:
    return RelayReply(RelayCode.ANSWER_MALFORMED, {}, None, None)


def _reply_from(response: HttpResponse) -> RelayReply:
    try:
        answer = decode_answer(response.body)
    except EnvelopeError:
        if response.status == 429:
            return RelayReply(
                RelayCode.RATE_LIMITED, {}, None, _stated_wait(response.headers)
            )
        if 500 <= response.status < 600:
            return RelayReply(RelayCode.UNAVAILABLE, {}, None, None)
        return _malformed()
    retry_after_s: int | None = None
    if answer.code is RelayCode.RATE_LIMITED:
        try:
            retry_after_s = parse_retry_after(answer.data)
        except EnvelopeError:
            return _malformed()
    return RelayReply(answer.code, answer.data, answer.outcome, retry_after_s)


class RelayClient:
    """Speaks envelope v1 through whatever :class:`HttpClient` its caller
    built; it never raises for a relay answer."""

    def __init__(
        self, *, settings: RelaySettings, http: HttpClient, token: Secret | None
    ) -> None:
        self._base = settings.url
        self._http = http
        self._secret_headers: dict[str, Secret] = (
            {"Authorization": Secret("Bearer " + token.reveal())}
            if token is not None
            else {}
        )

    def get(self, route: str) -> RelayReply:
        try:
            response = self._http.get(
                self._base + route,
                headers={"Accept": _JSON},
                secret_headers=self._secret_headers,
            )
        except TransportError:
            return RelayReply(RelayCode.RELAY_UNREACHABLE, {}, None, None)
        return _reply_from(response)

    def post(self, route: str, fields: Mapping[str, object]) -> RelayReply:
        body = encode_request(fields)  # an unencodable request is the caller's defect
        try:
            response = self._http.post(
                self._base + route,
                body=body,
                headers={"Accept": _JSON, "Content-Type": _JSON},
                secret_headers=self._secret_headers,
            )
        except TransportError:
            return RelayReply(RelayCode.RELAY_UNREACHABLE, {}, None, None)
        return _reply_from(response)


def _client(session: ConnectorSession, token: Secret | None) -> RelayClient:
    settings = session.settings
    if not isinstance(settings, RelaySettings):
        raise ConnectorError(
            "the relay connector was given another connector's settings"
        )
    if token is not None:
        session.redactor.add(token)
    return RelayClient(settings=settings, http=session.http, token=token)


def _refused(reply: RelayReply) -> RelayRefused:
    """The refusal for an answer the operation has no success reading of."""
    if reply.code in _SUCCESS_SHAPED:
        return RelayRefused(RelayCode.ANSWER_MALFORMED)
    return RelayRefused(reply.code, reply.retry_after_s)


def _empty_ok(reply: RelayReply) -> RelayRefused | None:
    if reply.code is RelayCode.OK and not reply.data:
        return None
    return _refused(reply)


class RelayConnector:
    """A fitdocs relay: one token, five operations, no capability."""

    connector_id = "relay"
    display_name = "fitdocs relay"
    auth_style = AuthStyle.RELAY_TOKEN
    capabilities: frozenset[Capability] = frozenset()
    credential_fields = (CredentialField("token", "Relay token", True),)

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> RelaySettings:
        """``url`` (optional): an absolute ``https`` URL, or ``http`` to this
        machine's loopback; no query, fragment or user information. A
        trailing slash is stripped. Every other key is ignored."""
        return RelaySettings(url=_normalised_url(table.get("url", DEFAULT_RELAY_URL)))

    def check_token(
        self, session: ConnectorSession, token: Secret
    ) -> RelayRefused | None:
        return _empty_ok(_client(session, token).get(ROUTE_TOKEN))

    def read_capabilities(
        self, session: ConnectorSession
    ) -> RelayCapabilities | RelayRefused:
        reply = _client(session, None).get(ROUTE_CAPABILITIES)
        if reply.code is not RelayCode.OK:
            return _refused(reply)
        try:
            data = parse_capabilities(reply.data)
        except EnvelopeError:
            return RelayRefused(RelayCode.ANSWER_MALFORMED)
        return RelayCapabilities(
            envelopes=data.envelopes,
            registration=data.registration,
            targets=data.targets,
        )

    def start_registration(
        self, session: ConnectorSession, email: str
    ) -> RegistrationStarted | RelayRefused:
        reply = _client(session, None).post(ROUTE_REGISTRATIONS, {"email": email})
        if reply.code is not RelayCode.REGISTRATION_STARTED:
            return _refused(reply)
        try:
            data = parse_started(reply.data)
        except EnvelopeError:
            return RelayRefused(RelayCode.ANSWER_MALFORMED)
        return RegistrationStarted(
            user_code=data.user_code,
            poll_secret=session.secret(data.poll_secret),
            interval_s=data.interval_s,
            expires_at=session.now() + timedelta(seconds=data.expires_in_s),
        )

    def poll_registration(
        self, session: ConnectorSession, started: RegistrationStarted
    ) -> RegistrationPolled | RelayRefused:
        reply = _client(session, None).post(
            ROUTE_REGISTRATION_POLL, {"poll_secret": started.poll_secret.reveal()}
        )
        if reply.code in {
            RelayCode.REGISTRATION_PENDING,
            RelayCode.REGISTRATION_SLOW_DOWN,
        }:
            if reply.data:
                return RelayRefused(RelayCode.ANSWER_MALFORMED)
            return RegistrationPolled(code=reply.code, token=None)
        if reply.code is RelayCode.REGISTRATION_ISSUED:
            try:
                token = parse_issued(reply.data)
            except EnvelopeError:
                return RelayRefused(RelayCode.ANSWER_MALFORMED)
            return RegistrationPolled(code=reply.code, token=session.secret(token))
        return _refused(reply)

    def revoke_token(
        self, session: ConnectorSession, token: Secret
    ) -> RelayRefused | None:
        return _empty_ok(_client(session, token).post(ROUTE_TOKEN_REVOKE, {}))
