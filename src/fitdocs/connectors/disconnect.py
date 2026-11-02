"""Disconnect an instance per authentication style (relay-server design.md
"DisconnectEngine", Requirements 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 15.2;
strava-publish design.md "DisconnectAmendment", Requirements 11.1-11.4).

A relay instance with a stored token revokes it first: one request through one
:attr:`~fitdocs.connectors.http.CallMode.AUTH` client (the mode that makes
exactly one request whatever the response and never retries), carrying the
stored token and never the environment override. ``ok``, ``token-unknown`` and
``token-revoked`` remove the credentials file; any other answer keeps it
byte-identical and returns the code with a fitdocs-written explanation and
next step. Nothing the relay sent beyond its code is carried into a result.

A browser-consent instance does the same through ``withdraw_consent``; the
answers ``token-unknown`` and ``token-revoked`` remove the file with a note
that a remaining connection can be revoked in Strava's settings.

``local_only``, and the personal-key and login styles, remove the file with no
request and say the credential stays valid where it was issued. Only the named
instance's own file is ever removed: never the directory, never another
instance's file, nothing under a data root.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from fitdocs.connectors.credentials import (
    CredentialStore,
    CredentialStoreError,
    env_var_name,
)
from fitdocs.connectors.http import CallMode, HttpClient, Transport
from fitdocs.connectors.protocol import (
    AuthStyle,
    BrowserConsentClient,
    ConnectorSession,
    RelayTokenClient,
    TokenSet,
)
from fitdocs.connectors.relay_codes import RelayCode, explain
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance

TOKEN_FIELD: Final = "token"

LOCAL_ONLY_NOTE: Final = (
    "the token stays valid at the relay until its operator revokes it"
)
SERVICE_NOTE: Final = "the credential remains valid at the service"
CONSENT_LOCAL_ONLY_NOTE: Final = (
    "the Strava connection stays at the relay until this instance is connected "
    "and disconnected again, or access is revoked in Strava's settings"
)
CONSENT_UNKNOWN_NOTE: Final = (
    "the relay no longer knows this token; a remaining Strava connection can "
    "be revoked in Strava's settings"
)

_REMOVES_FILE: Final = frozenset(
    {RelayCode.OK, RelayCode.TOKEN_UNKNOWN, RelayCode.TOKEN_REVOKED}
)

_REVOKING_STYLES: Final = frozenset({AuthStyle.RELAY_TOKEN, AuthStyle.OAUTH_BROWSER})

_LOCAL_ONLY_NOTES: Final = {
    AuthStyle.RELAY_TOKEN: LOCAL_ONLY_NOTE,
    AuthStyle.OAUTH_BROWSER: CONSENT_LOCAL_ONLY_NOTE,
}

# A disconnect never reads or writes under a data root.
_NO_DATA_ROOT: Final[Path] = Path("disconnect-has-no-data-root")


@dataclass(frozen=True)
class Disconnected:
    instance: str
    path: Path
    code: RelayCode | None
    remote_revoked: bool
    note: str | None


@dataclass(frozen=True)
class NothingToDisconnect:
    instance: str
    env_override: tuple[str, ...]


@dataclass(frozen=True)
class DisconnectFailed:
    instance: str
    code: RelayCode
    explanation: str
    next_step: str


class UnsupportedDisconnect(ValueError):
    """A reserved style; the CLI exits 2. No current style raises it; it is kept
    for a future reserved style."""


class _NoCredentialAccess:
    """The ``credentials`` of a disconnect session: the revocation takes the
    token as an argument, so any use of this is an authoring error."""

    def value(self, field: str) -> Secret:
        raise AssertionError("a disconnect provides no credential access")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("a disconnect provides no credential access")


def _next_step(name: str) -> str:
    return (
        f"Run `fitdocs disconnect {name}` again to retry, or add `--local-only` "
        "to forget the stored token without asking the relay."
    )


def _env_override(
    instance: ConnectorInstance, environ: Mapping[str, str]
) -> tuple[str, ...]:
    return tuple(
        var
        for field in instance.connector.credential_fields
        if environ.get(var := env_var_name(instance.name, field.name), "")
    )


def _removed(
    instance: ConnectorInstance,
    store: CredentialStore,
    *,
    code: RelayCode | None,
    remote_revoked: bool,
    note: str | None,
) -> Disconnected:
    return Disconnected(
        instance=instance.name,
        path=store.path_for(instance.name),
        code=code,
        remote_revoked=remote_revoked,
        note=note,
    )


def _revoke_then_remove(
    instance: ConnectorInstance,
    *,
    store: CredentialStore,
    transport: Transport,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
) -> Disconnected | NothingToDisconnect | DisconnectFailed:
    stored = store.load(instance.name)
    if stored is None:
        return NothingToDisconnect(instance=instance.name, env_override=())
    token = stored.values.get(TOKEN_FIELD)
    if token is None:
        held = (
            "connection token"
            if instance.connector.auth_style is AuthStyle.OAUTH_BROWSER
            else "relay token"
        )
        raise CredentialStoreError(
            f"{store.path_for(instance.name)} holds no {held}; "
            f"run: fitdocs disconnect {instance.name} --local-only"
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
    if instance.connector.auth_style is AuthStyle.OAUTH_BROWSER:
        refused = cast(BrowserConsentClient, instance.connector).withdraw_consent(
            session, token
        )
    else:
        refused = cast(RelayTokenClient, instance.connector).revoke_token(
            session, token
        )
    code = RelayCode.OK if refused is None else refused.code
    if code not in _REMOVES_FILE:
        return DisconnectFailed(
            instance=instance.name,
            code=code,
            explanation=explain(code),
            next_step=_next_step(instance.name),
        )
    store.remove(instance.name)
    forgotten = (
        CONSENT_UNKNOWN_NOTE
        if instance.connector.auth_style is AuthStyle.OAUTH_BROWSER
        and code is not RelayCode.OK
        else None
    )
    return _removed(
        instance,
        store,
        code=code,
        remote_revoked=code is RelayCode.OK,
        note=forgotten,
    )


def run_disconnect(
    instance: ConnectorInstance,
    *,
    local_only: bool,
    store: CredentialStore,
    transport: Transport,
    environ: Mapping[str, str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
) -> Disconnected | NothingToDisconnect | DisconnectFailed:
    """Forget ``instance``'s stored credentials, revoking first where the
    style allows."""
    style = instance.connector.auth_style
    if style is AuthStyle.NONE:
        return NothingToDisconnect(instance=instance.name, env_override=())
    if style in _REVOKING_STYLES and not local_only:
        result = _revoke_then_remove(
            instance,
            store=store,
            transport=transport,
            now=now,
            sleep=sleep,
            redactor=redactor,
        )
        if isinstance(result, NothingToDisconnect):
            return NothingToDisconnect(
                instance=instance.name,
                env_override=_env_override(instance, environ),
            )
        return result
    if not store.remove(instance.name):
        return NothingToDisconnect(
            instance=instance.name, env_override=_env_override(instance, environ)
        )
    note = _LOCAL_ONLY_NOTES.get(style, SERVICE_NOTE)
    return _removed(instance, store, code=None, remote_revoked=False, note=note)
