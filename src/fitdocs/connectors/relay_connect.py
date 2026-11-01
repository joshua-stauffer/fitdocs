"""Connect to a relay with a pasted token (relay-server design.md
"RelayConnectEngine", Requirements 12.2, 12.3, 12.4, 12.6, 15.2, 15.4).

:func:`run_relay_connect` checks the token's documented format with the
envelope module's own :func:`~fitdocs.connectors.relay_envelope.
split_relay_token` before any request, makes exactly one token check through
one :class:`~fitdocs.connectors.http.CallMode.AUTH` client (the mode that
makes exactly one request whatever the response and never retries), and
stores the token only when the relay answers ``ok``. Any other answer returns
the relay code, its fitdocs-written explanation and a fixed fitdocs-written
next step; nothing the relay sent beyond its code is carried into the
result. Storing replaces any earlier file atomically and revokes nothing.

The instance's connector is reached only through the
:class:`~fitdocs.connectors.protocol.RelayTokenClient` protocol.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from fitdocs.connectors.credentials import (
    CredentialStore,
    StoredCredentials,
    env_var_name,
)
from fitdocs.connectors.http import CallMode, HttpClient, Transport
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    RelayTokenClient,
    TokenSet,
)
from fitdocs.connectors.relay_codes import RelayCode, explain
from fitdocs.connectors.relay_envelope import split_relay_token
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance

TOKEN_FIELD: Final = "token"

TOKEN_FORMAT_MESSAGE: Final = (
    "That is not a relay token: a relay token looks like "
    "fdr1_<16 characters>_<52 characters>."
)

# A relay connect never reads or writes under a data root.
_NO_DATA_ROOT: Final[Path] = Path("relay-connect-has-no-data-root")


@dataclass(frozen=True)
class RelayConnected:
    instance: str
    path: Path
    env_override: tuple[str, ...]


@dataclass(frozen=True)
class RelayConnectFailed:
    instance: str
    code: RelayCode
    explanation: str
    next_step: str
    retry_after_s: int | None


class RelayTokenFormatError(ValueError):
    """Raised before any request; the CLI exits 2. The message never repeats
    the value."""


class _NoCredentialAccess:
    """The ``credentials`` of a relay-connect session: the relay operations
    take the token as an argument, so any use of this is an authoring error."""

    def value(self, field: str) -> Secret:
        raise AssertionError("a relay connect provides no credential access")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("a relay connect provides no credential access")


_RETRY_LATER = "Try again in a few minutes."
_TELL_OPERATOR = "Tell the relay's operator; nothing in fitdocs can change this."
_UPDATE_FITDOCS = "Update fitdocs; if it is already current, tell the relay's operator."


def relay_next_step(code: RelayCode, *, name: str, retry_after_s: int | None) -> str:
    """Fixed fitdocs-written text for ``code``; ``name`` is the instance, and
    ``retry_after_s`` is the wait the relay stated, if any."""
    connect = f"`fitdocs connect {name}`"
    register = f"`fitdocs connect {name} --register`"
    if code is RelayCode.RATE_LIMITED:
        if retry_after_s is None:
            return "Wait a few minutes, then try again."
        unit = "second" if retry_after_s == 1 else "seconds"
        return f"Wait {retry_after_s} {unit}, then try again."
    return _NEXT_STEPS[code].format(connect=connect, register=register)


_NEXT_STEPS: Final[Mapping[RelayCode, str]] = {
    RelayCode.OK: "Nothing more to do.",
    RelayCode.TOKEN_MISSING: "Run {connect} and paste your relay token.",
    RelayCode.TOKEN_UNKNOWN: (
        "Check the token you pasted, or ask the relay's operator for a new one, "
        "then run {connect}."
    ),
    RelayCode.TOKEN_REVOKED: (
        "Ask the relay's operator for a new token, or run {register} "
        "if the relay offers registration."
    ),
    RelayCode.ENVELOPE_UNSUPPORTED: _UPDATE_FITDOCS,
    RelayCode.REQUEST_MALFORMED: _UPDATE_FITDOCS,
    RelayCode.REQUEST_TOO_LARGE: _UPDATE_FITDOCS,
    RelayCode.NOT_OFFERED: "Ask the relay's operator for a token.",
    RelayCode.RATE_LIMITED: "Wait a few minutes, then try again.",
    RelayCode.UNAVAILABLE: _RETRY_LATER + " If it persists, tell the relay's operator.",
    RelayCode.RELAY_FAILURE: _RETRY_LATER
    + " If it persists, tell the relay's operator.",
    RelayCode.STORAGE_UNREACHABLE: _TELL_OPERATOR,
    RelayCode.SCHEMA_BEHIND: _TELL_OPERATOR,
    RelayCode.SCHEMA_AHEAD: _TELL_OPERATOR,
    RelayCode.REGISTRATION_STARTED: "Run {connect} again; if this repeats, "
    "tell the relay's operator.",
    RelayCode.REGISTRATION_PENDING: "Run {connect} again; if this repeats, "
    "tell the relay's operator.",
    RelayCode.REGISTRATION_SLOW_DOWN: "Run {connect} again; if this repeats, "
    "tell the relay's operator.",
    RelayCode.REGISTRATION_ISSUED: "Run {connect} again; if this repeats, "
    "tell the relay's operator.",
    RelayCode.REGISTRATION_REFUSED: "Ask the relay's operator for a token.",
    RelayCode.REGISTRATION_EXPIRED: "Run {register} again.",
    RelayCode.RELAY_UNREACHABLE: (
        "Check your network connection and the relay's url in your fitdocs "
        "settings, then try again."
    ),
    RelayCode.ANSWER_MALFORMED: (
        "Check the relay's url in your fitdocs settings. If it is right, "
        "tell the relay's operator."
    ),
}


def _env_override(
    instance: ConnectorInstance, environ: Mapping[str, str]
) -> tuple[str, ...]:
    return tuple(
        var
        for field in instance.connector.credential_fields
        if environ.get(var := env_var_name(instance.name, field.name), "")
    )


def run_relay_connect(
    instance: ConnectorInstance,
    token_text: str,
    *,
    store: CredentialStore,
    transport: Transport,
    environ: Mapping[str, str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
) -> RelayConnected | RelayConnectFailed:
    """Check a pasted ``token_text`` once and store it only on ``ok``."""
    redactor.add(token_text)
    if split_relay_token(token_text) is None:
        raise RelayTokenFormatError(TOKEN_FORMAT_MESSAGE)
    connector = instance.connector
    if connector.auth_style is not AuthStyle.RELAY_TOKEN:
        raise AssertionError(
            f"{instance.name}'s connector is not a relay-token connector; "
            "the CLI must refuse it before calling run_relay_connect"
        )
    http = HttpClient(transport, mode=CallMode.AUTH, redactor=redactor, sleep=sleep)
    session = ConnectorSession(
        instance=instance.name,
        settings=instance.settings,
        http=http,
        credentials=_NoCredentialAccess(),
        data_root=_NO_DATA_ROOT,
        now=now,
        sleep=sleep,
        redactor=redactor,
    )
    token = session.secret(token_text)
    refused = cast(RelayTokenClient, connector).check_token(session, token)
    if refused is not None:
        return RelayConnectFailed(
            instance=instance.name,
            code=refused.code,
            explanation=explain(refused.code),
            next_step=relay_next_step(
                refused.code, name=instance.name, retry_after_s=refused.retry_after_s
            ),
            retry_after_s=refused.retry_after_s,
        )
    path = store.save(
        instance.name,
        StoredCredentials(
            connector_id=connector.connector_id,
            auth_style=AuthStyle.RELAY_TOKEN,
            values={TOKEN_FIELD: token},
            expires_at=None,
            scopes=None,
        ),
    )
    return RelayConnected(
        instance=instance.name,
        path=path,
        env_override=_env_override(instance, environ),
    )
