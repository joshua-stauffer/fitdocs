"""Connect a browser-consent instance (strava-publish design.md
"BrowserConnectEngine", Requirements 2.1, 2.2, 2.4-2.9).

:func:`run_browser_connect` resolves the bound relay instance's token first;
an instance with none makes no request at all and returns
:class:`RelayNotConnected`. It then starts one consent through one
:class:`~fitdocs.connectors.http.CallMode.AUTH` client (one attempt per
request, never repeated), reports the started attempt through ``on_started``,
and polls once per interval until a final answer or the local deadline (the
started time plus the relay's ``expires_in_s``). Only ``connect-granted``
stores a token, through the credential store's atomic, owner-only ``save``;
every other ending stores nothing, and an interrupt raised from the injected
``sleep`` or from a request propagates with nothing stored.

Nothing the relay sent beyond its code and its stated wait
(``retry_after_s``) is carried into a result; the explanation and the next
step are fitdocs-written text per code. The consent operations are reached
only through the :class:`~fitdocs.connectors.protocol.BrowserConsentClient`
protocol.
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
    resolve_credentials,
)
from fitdocs.connectors.errors import NotConnectedError
from fitdocs.connectors.http import CallMode, HttpClient, Transport
from fitdocs.connectors.protocol import (
    AuthStyle,
    BrowserConsentClient,
    ConnectorSession,
    RelayRefused,
    TokenSet,
)
from fitdocs.connectors.relay import RelaySettings
from fitdocs.connectors.relay_codes import RelayCode, explain
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance

TOKEN_FIELD: Final = "token"

# A browser connect never reads or writes under a data root.
_NO_DATA_ROOT: Final[Path] = Path("browser-connect-has-no-data-root")


@dataclass(frozen=True)
class ConsentShown:
    instance: str
    page_url: str
    user_code: str
    expires_in_s: int


@dataclass(frozen=True)
class BrowserConnected:
    instance: str
    path: Path
    relay_url: str
    env_override: tuple[str, ...]


@dataclass(frozen=True)
class BrowserConnectFailed:
    instance: str
    code: RelayCode
    explanation: str
    next_step: str
    retry_after_s: int | None


@dataclass(frozen=True)
class RelayNotConnected:
    instance: str
    relay_instance: str
    next_step: str


class _NoCredentialAccess:
    """The ``credentials`` of a browser-connect session: the consent
    operations take the relay token as an argument, so any use of this is an
    authoring error."""

    def value(self, field: str) -> Secret:
        raise AssertionError("a browser connect provides no credential access")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("a browser connect provides no credential access")


_CONNECT_RELAY_FIRST: Final = (
    "Connect the relay instance first: run `fitdocs connect {relay}`."
)
_CHECK_RELAY: Final = (
    "Check the relay instance `{relay}` and try again later; if it persists, "
    "tell the relay's operator."
)


def consent_next_step(
    code: RelayCode, *, name: str, relay: str, retry_after_s: int | None
) -> str:
    """Fixed fitdocs-written text for ``code``; ``name`` is the Strava
    instance, ``relay`` the relay instance it uses and ``retry_after_s`` the
    wait the relay stated, if any."""
    if code in (
        RelayCode.TOKEN_MISSING,
        RelayCode.TOKEN_UNKNOWN,
        RelayCode.TOKEN_REVOKED,
    ):
        return _CONNECT_RELAY_FIRST.format(relay=relay)
    if code is RelayCode.NOT_OFFERED:
        return (
            f"Ask the operator of the relay instance `{relay}` to offer this "
            "target, or use another relay."
        )
    if code is RelayCode.CONNECT_REFUSED:
        return (
            f"Run `fitdocs connect {name}` again and allow every permission "
            "that is asked for."
        )
    if code is RelayCode.CONNECT_EXPIRED:
        return f"Run `fitdocs connect {name}` again and finish within ten minutes."
    if code is RelayCode.RATE_LIMITED:
        if retry_after_s is None:
            return "Wait a few minutes, then try again."
        unit = "second" if retry_after_s == 1 else "seconds"
        return f"Wait {retry_after_s} {unit}, then try again."
    return _CHECK_RELAY.format(relay=relay)


def _failed(
    instance: ConnectorInstance,
    relay_instance: ConnectorInstance,
    code: RelayCode,
    retry_after_s: int | None,
) -> BrowserConnectFailed:
    return BrowserConnectFailed(
        instance=instance.name,
        code=code,
        explanation=explain(code),
        next_step=consent_next_step(
            code,
            name=instance.name,
            relay=relay_instance.name,
            retry_after_s=retry_after_s,
        ),
        retry_after_s=retry_after_s,
    )


def _env_override(
    instance: ConnectorInstance, environ: Mapping[str, str]
) -> tuple[str, ...]:
    return tuple(
        var
        for field in instance.connector.credential_fields
        if environ.get(var := env_var_name(instance.name, field.name), "")
    )


def run_browser_connect(
    instance: ConnectorInstance,
    relay_instance: ConnectorInstance,
    *,
    store: CredentialStore,
    transport: Transport,
    environ: Mapping[str, str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    redactor: Redactor,
    on_started: Callable[[ConsentShown], None],
) -> BrowserConnected | BrowserConnectFailed | RelayNotConnected:
    """Run the browser-consent connect loop for ``instance`` through
    ``relay_instance`` and store a connection token only on a grant."""
    connector = instance.connector
    if connector.auth_style is not AuthStyle.OAUTH_BROWSER:
        raise AssertionError(
            f"{instance.name}'s connector is not a browser-consent connector; "
            "the CLI must refuse it before calling the browser connect engine"
        )
    relay_settings = relay_instance.settings
    if not isinstance(relay_settings, RelaySettings):
        raise AssertionError(f"{relay_instance.name} is not a relay instance")
    try:
        relay_token = resolve_credentials(
            relay_instance.name,
            relay_instance.connector,
            store,
            environ,
            redactor,
        ).value(TOKEN_FIELD)
    except NotConnectedError:
        return RelayNotConnected(
            instance=instance.name,
            relay_instance=relay_instance.name,
            next_step=consent_next_step(
                RelayCode.TOKEN_MISSING,
                name=instance.name,
                relay=relay_instance.name,
                retry_after_s=None,
            ),
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
    client = cast(BrowserConsentClient, connector)
    started = client.start_consent(session, relay_token)
    if isinstance(started, RelayRefused):
        return _failed(instance, relay_instance, started.code, started.retry_after_s)
    deadline = started.expires_at
    on_started(
        ConsentShown(
            instance=instance.name,
            page_url=started.page_url,
            user_code=started.user_code,
            expires_in_s=max(0, round((deadline - now()).total_seconds())),
        )
    )
    while True:
        sleep(started.interval_s)
        if now() >= deadline:
            return _failed(instance, relay_instance, RelayCode.CONNECT_EXPIRED, None)
        polled = client.poll_consent(session, started, relay_token)
        if isinstance(polled, RelayRefused):
            return _failed(instance, relay_instance, polled.code, polled.retry_after_s)
        if polled.code is RelayCode.CONNECT_GRANTED:
            if polled.token is None:
                return _failed(
                    instance, relay_instance, RelayCode.ANSWER_MALFORMED, None
                )
            path = store.save(
                instance.name,
                StoredCredentials(
                    connector_id=connector.connector_id,
                    auth_style=AuthStyle.OAUTH_BROWSER,
                    values={TOKEN_FIELD: polled.token},
                    expires_at=None,
                    scopes=None,
                ),
            )
            return BrowserConnected(
                instance=instance.name,
                path=path,
                relay_url=relay_settings.url,
                env_override=_env_override(instance, environ),
            )
        if polled.code is not RelayCode.CONNECT_PENDING:
            return _failed(instance, relay_instance, RelayCode.ANSWER_MALFORMED, None)
