"""One authentication attempt at connect; store only on success (design.md
"ConnectEngine", Requirements 4.6, 4.8, 5.5, 5.6, 5.7, 5.8, 10.2).

:func:`run_connect` is the whole engine: it wraps every answer the user typed
in a :class:`~fitdocs.connectors.secrets.Secret`, registers it with the
caller's :class:`~fitdocs.connectors.secrets.Redactor`, and builds exactly one
:class:`~fitdocs.connectors.http.CallMode.AUTH` session -- the mode that makes
exactly one request whatever the response and never retries (Req 5.7,
``connectors/http.py``). A personal-key connector's declared
:meth:`~fitdocs.connectors.protocol.KeyVerifier.verify` is called with the
answers directly (never through ``session.credentials``, which this module
never populates with a usable value -- see :class:`_NoCredentialAccess`); on
acceptance the answers and the granted scopes are stored (Req 4.8). A
login-style connector's :meth:`~fitdocs.connectors.protocol.TokenIssuer.login`
is called the same way; only the returned token set -- never the answers, so
never the password -- is stored (Req 4.6).

An :class:`~fitdocs.connectors.errors.AuthFailure` or a
:class:`~fitdocs.connectors.http.TransportError` raised by ``verify``/
``login`` becomes a :class:`ConnectFailed` naming the failure kind, the
service's own message with every registered secret redacted (Req 10.2), and
the next step from :func:`fitdocs.connectors.errors.next_step`; nothing is
stored in either case (Req 5.6). :meth:`~fitdocs.connectors.credentials.
CredentialStore.save` on acceptance already replaces any existing file for
the instance atomically (Req 5.8).

``run_connect`` reads only an instance's ``name`` and ``connector`` from
:class:`fitdocs.connectors.settings.ConnectorInstance`.
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
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, next_step
from fitdocs.connectors.http import CallMode, HttpClient, Transport, TransportError
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    KeyVerifier,
    TokenIssuer,
    TokenSet,
)
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance

# A placeholder for ``ConnectorSession.data_root``: ``run_connect`` never
# reads or writes under a data root (Req 5.9), and neither ``KeyVerifier.
# verify`` nor ``TokenIssuer.login`` receives one to use -- only
# ``ActivityPuller`` operations (a later pull, not this connect) do.
_NO_DATA_ROOT: Final[Path] = Path("connect-has-no-data-root")


@dataclass(frozen=True)
class Connected:
    """A successful connect (Req 5.5, 5.8)."""

    instance: str
    path: Path
    scopes: tuple[str, ...] | None
    env_override: tuple[str, ...]


@dataclass(frozen=True)
class ConnectFailed:
    """A refused or unreachable connect attempt; nothing was stored (Req 5.6)."""

    instance: str
    kind: AuthFailureKind
    message: str
    next_step: str


class _NoCredentialAccess:
    """The ``credentials`` a connect-time session hands a connector.

    ``verify``/``login`` receive the user's answers as an explicit argument
    and never need this; it exists only because
    :class:`~fitdocs.connectors.protocol.ConnectorSession` requires a
    :class:`~fitdocs.connectors.protocol.CredentialAccess`. Any use of it
    during connect is a connector authoring error, so every method refuses
    rather than silently returning a placeholder value that could be stored
    or reported.
    """

    def value(self, field: str) -> Secret:
        raise AssertionError(
            f"connect does not provide credential access; {field!r} must come "
            "from the answers argument verify()/login() already received"
        )

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError(
            "connect does not provide credential access; nothing to replace"
        )


def _env_override(
    instance: ConnectorInstance, environ: Mapping[str, str]
) -> tuple[str, ...]:
    """The variables that will override the stored values during a pull.

    Only a personal-key (``API_KEY``) connector's fields are ever overridden
    by the environment (``connectors/credentials.py``'s ``resolve_credentials``);
    a login-style connector's ``resolve_credentials`` reads only the store.
    """

    if instance.connector.auth_style is not AuthStyle.API_KEY:
        return ()
    overridden: list[str] = []
    for field in instance.connector.credential_fields:
        var_name = env_var_name(instance.name, field.name)
        if environ.get(var_name, ""):
            overridden.append(var_name)
    return tuple(overridden)


def run_connect(
    instance: ConnectorInstance,
    answers: Mapping[str, str],
    *,
    store: CredentialStore,
    transport: Transport,
    environ: Mapping[str, str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
) -> Connected | ConnectFailed:
    """Make one authentication attempt for ``instance`` and store only on
    success (Req 4.6, 4.8, 5.5-5.8, 10.2). ``answers`` is a plain mapping of
    field name to the value the user typed; the CLI layer (task 5.1) is
    responsible for prompting and for refusing an instance whose connector
    needs no authentication or declares a reserved style before calling
    this.
    """

    http = HttpClient(transport, mode=CallMode.AUTH, redactor=redactor, sleep=sleep)
    session = ConnectorSession(
        instance=instance.name,
        settings=None,
        http=http,
        credentials=_NoCredentialAccess(),
        data_root=_NO_DATA_ROOT,
        now=now,
        sleep=sleep,
        redactor=redactor,
    )
    values = {field: session.secret(raw) for field, raw in answers.items()}
    connector = instance.connector

    try:
        if connector.auth_style is AuthStyle.API_KEY:
            granted = cast(KeyVerifier, connector).verify(session, values)
            stored = StoredCredentials(
                connector_id=connector.connector_id,
                auth_style=AuthStyle.API_KEY,
                values=values,
                expires_at=None,
                scopes=granted.scopes,
            )
            path = store.save(instance.name, stored)
            return Connected(
                instance=instance.name,
                path=path,
                scopes=granted.scopes,
                env_override=_env_override(instance, environ),
            )

        if connector.auth_style is AuthStyle.LOGIN:
            tokens = cast(TokenIssuer, connector).login(session, values)
            stored = StoredCredentials(
                connector_id=connector.connector_id,
                auth_style=AuthStyle.LOGIN,
                values=tokens.values,
                expires_at=tokens.expires_at,
                scopes=tokens.scopes,
            )
            path = store.save(instance.name, stored)
            return Connected(
                instance=instance.name,
                path=path,
                scopes=tokens.scopes,
                env_override=(),
            )
    except AuthFailure as exc:
        message = redactor.redact(exc.service_message)
        return ConnectFailed(
            instance=instance.name,
            kind=exc.kind,
            message=message,
            next_step=next_step(
                exc.kind, name=instance.name, retry_after_s=exc.retry_after_s
            ),
        )
    except TransportError as exc:
        message = redactor.redact(str(exc))
        return ConnectFailed(
            instance=instance.name,
            kind=AuthFailureKind.UNAVAILABLE,
            message=message,
            next_step=next_step(
                AuthFailureKind.UNAVAILABLE, name=instance.name, retry_after_s=None
            ),
        )

    raise AssertionError(
        f"{instance.name}'s connector uses an authentication style "
        f"({connector.auth_style!r}) run_connect does not support; the CLI "
        "must refuse it before calling run_connect"
    )
