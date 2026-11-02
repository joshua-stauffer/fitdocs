"""The built-in Strava connector: its settings and consent operations
(strava-publish design.md "StravaConnector", Requirements 1.1-1.4, 2.4).

A Strava instance reaches Strava only through the relay instance it names, so
this module holds no Strava address. Each consent operation is one
:class:`~fitdocs.connectors.relay.RelayClient` request over the session's
HTTP client. The connect page's address is composed here, from the bound
relay's URL and a user code that passed the codec's format check; no other
value the relay returned is part of that address. The poll secret and every
token are registered with the session's redactor before any request that
carries them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Final

from fitdocs.connectors.errors import ConnectorError, ConnectorSettingsError
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    ConsentPolled,
    ConsentStarted,
    CredentialField,
    RelayRefused,
    SettingsContext,
)
from fitdocs.connectors.relay import RelayClient, RelayReply, RelaySettings
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.relay_envelope import (
    EnvelopeError,
    parse_issued,
    parse_started,
)
from fitdocs.connectors.relay_targets import (
    ACTION_CONNECT,
    ACTION_CONNECT_POLL,
    ACTION_DISCONNECT,
    STRAVA,
    connect_page_path,
    target_route,
)
from fitdocs.connectors.secrets import Secret

STRAVA_CONNECTOR_ID: Final = "strava"
STRAVA_LINK_LABEL: Final = "View on Strava"
TOKEN_FIELD: Final = "token"

RELAY_KEY_MESSAGE: Final = (
    "relay must be the name of a configured relay instance, a non-empty string"
)
UPLOAD_KEY_MESSAGE: Final = "upload must be true or false"
NOT_A_RELAY_MESSAGE: Final = "relay must name an instance of the relay connector"

# Answers that mean "success" on some route: arriving where the route does
# not expect them they are another route's answer, not a refusal.
_SUCCESS_SHAPED: Final = frozenset(
    {
        RelayCode.OK,
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
        RelayCode.CONNECT_STARTED,
        RelayCode.CONNECT_PENDING,
        RelayCode.CONNECT_GRANTED,
    }
)


@dataclass(frozen=True)
class StravaSettings:
    """Validated ``[connectors.<instance>]`` configuration for a Strava
    instance. ``relay`` is set by the settings loader's binding pass."""

    relay_instance: str
    upload: bool
    relay: RelaySettings | None = None

    def bound(self, relay_settings: object) -> StravaSettings:
        if not isinstance(relay_settings, RelaySettings):
            raise ConnectorSettingsError("relay", NOT_A_RELAY_MESSAGE)
        return replace(self, relay=relay_settings)


def _client(session: ConnectorSession, token: Secret) -> RelayClient:
    settings = session.settings
    if not isinstance(settings, StravaSettings):
        raise ConnectorError(
            "the Strava connector was given another connector's settings"
        )
    if settings.relay is None:
        raise ConnectorError("the Strava instance is not bound to a relay instance")
    session.redactor.add(token)
    return RelayClient(settings=settings.relay, http=session.http, token=token)


def _refused(reply: RelayReply) -> RelayRefused:
    """The refusal for an answer the operation has no success reading of."""
    if reply.code in _SUCCESS_SHAPED:
        return RelayRefused(RelayCode.ANSWER_MALFORMED)
    return RelayRefused(reply.code, reply.retry_after_s)


class StravaConnector:
    """The Strava target: settings and consent operations."""

    connector_id = STRAVA_CONNECTOR_ID
    display_name = "Strava"
    auth_style = AuthStyle.OAUTH_BROWSER
    capabilities: frozenset[Capability] = frozenset(
        {
            Capability.RESOLVE_REMOTE_ACTIVITY,
            Capability.ANNOTATE_REMOTE_ACTIVITY,
            Capability.PUSH_ACTIVITY,
        }
    )
    credential_fields = (CredentialField(TOKEN_FIELD, "Connection token", True),)
    link_label = STRAVA_LINK_LABEL

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> StravaSettings:
        """``relay`` (required): a non-empty string naming a relay instance;
        ``upload`` (optional): a boolean, default false. Every other key is
        ignored."""
        relay = table.get("relay")
        if not isinstance(relay, str) or not relay:
            raise ConnectorSettingsError("relay", RELAY_KEY_MESSAGE)
        upload = table.get("upload", False)
        if not isinstance(upload, bool):
            raise ConnectorSettingsError("upload", UPLOAD_KEY_MESSAGE)
        return StravaSettings(relay_instance=relay, upload=upload)

    def start_consent(
        self, session: ConnectorSession, relay_token: Secret
    ) -> ConsentStarted | RelayRefused:
        client = _client(session, relay_token)
        reply = client.post(target_route(STRAVA, ACTION_CONNECT), {})
        if reply.code is not RelayCode.CONNECT_STARTED:
            return _refused(reply)
        try:
            data = parse_started(reply.data)
            page_path = connect_page_path(STRAVA, data.user_code)
        except EnvelopeError:
            return RelayRefused(RelayCode.ANSWER_MALFORMED)
        settings = session.settings
        assert isinstance(settings, StravaSettings) and settings.relay is not None
        return ConsentStarted(
            user_code=data.user_code,
            page_url=settings.relay.url + page_path,
            poll_secret=session.secret(data.poll_secret),
            interval_s=data.interval_s,
            expires_at=session.now() + timedelta(seconds=data.expires_in_s),
        )

    def poll_consent(
        self,
        session: ConnectorSession,
        started: ConsentStarted,
        relay_token: Secret,
    ) -> ConsentPolled | RelayRefused:
        client = _client(session, relay_token)
        session.redactor.add(started.poll_secret)
        reply = client.post(
            target_route(STRAVA, ACTION_CONNECT_POLL),
            {"poll_secret": started.poll_secret.reveal()},
        )
        if reply.code is RelayCode.CONNECT_PENDING:
            if reply.data:
                return RelayRefused(RelayCode.ANSWER_MALFORMED)
            return ConsentPolled(code=reply.code, token=None)
        if reply.code is RelayCode.CONNECT_GRANTED:
            try:
                token = parse_issued(reply.data)
            except EnvelopeError:
                return RelayRefused(RelayCode.ANSWER_MALFORMED)
            return ConsentPolled(code=reply.code, token=session.secret(token))
        return _refused(reply)

    def withdraw_consent(
        self, session: ConnectorSession, token: Secret
    ) -> RelayRefused | None:
        reply = _client(session, token).post(
            target_route(STRAVA, ACTION_DISCONNECT), {}
        )
        if reply.code is RelayCode.OK and not reply.data:
            return None
        return _refused(reply)
