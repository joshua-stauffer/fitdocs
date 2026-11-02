"""The browser-consent connect loop (strava-publish task 5.6; Requirements
2.1, 2.2, 2.5, 2.6, 2.7, 2.8, 2.9).

Every request goes through a scripted transport and every wait through a fake
clock, so nothing sleeps and nothing reaches a network. The Strava connector
and the relay connector are the real ones; the credential store is a real
``CredentialStore`` in a temporary directory. The fake clock runs at +02:00.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import pytest

from fitdocs.connectors.browser_connect import (
    BrowserConnected,
    BrowserConnectFailed,
    ConsentShown,
    RelayNotConnected,
    consent_next_step,
    run_browser_connect,
)
from fitdocs.connectors.credentials import (
    CredentialStore,
    StoredCredentials,
    env_var_name,
)
from fitdocs.connectors.http import (
    CallMode,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    ConsentPolled,
    ConsentStarted,
    RelayRefused,
    TokenSet,
)
from fitdocs.connectors.relay import RelayConnector, RelaySettings
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode, explain
from fitdocs.connectors.relay_envelope import Answer, encode_answer
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from fitdocs.connectors.strava import StravaConnector, StravaSettings
from tests.connectors.conftest import FakeTransport

_BASE = "https://relay.example.com"
_RELAY_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52
_OTHER_RELAY_TOKEN = "fdr1_" + "e" * 16 + "_" + "e" * 52
_OLD_CONNECTION = "fdr1_" + "b" * 16 + "_" + "b" * 52
_CONNECTION_TOKEN = "fdr1_" + "c" * 16 + "_" + "d" * 52
_POLL_SECRET = "p" * 40
_USER_CODE = "BCDF-GHJK"
_START_URL = _BASE + "/v1/targets/strava/connect"
_POLL_URL = _BASE + "/v1/targets/strava/connect/poll"
_PLUS_TWO = timezone(timedelta(hours=2))


class _Clock:
    """A fake clock at +02:00 whose sleep advances it and is logged."""

    def __init__(self, events: list[str]) -> None:
        self.at = datetime(2026, 3, 1, 12, 0, tzinfo=_PLUS_TWO)
        self._events = events
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.at

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._events.append(f"sleep {seconds:g}")
        self.at += timedelta(seconds=seconds)


def _strava(*, name: str = "strava") -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=StravaConnector(),
        lookback_days=30,
        settings=StravaSettings(
            relay_instance="home", upload=False, relay=RelaySettings(url=_BASE)
        ),
    )


def _relay(name: str = "home") -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=RelayConnector(),
        lookback_days=30,
        settings=RelaySettings(url=_BASE),
    )


def _store(tmp_path: Path) -> CredentialStore:
    return CredentialStore(tmp_path / "credentials")


def _save_relay_token(store: CredentialStore, token: str = _RELAY_TOKEN) -> None:
    store.save(
        "home",
        StoredCredentials(
            connector_id="relay",
            auth_style=AuthStyle.RELAY_TOKEN,
            values={"token": Secret(token)},
            expires_at=None,
            scopes=None,
        ),
    )


def _save_old_connection(store: CredentialStore) -> Path:
    return store.save(
        "strava",
        StoredCredentials(
            connector_id="strava",
            auth_style=AuthStyle.OAUTH_BROWSER,
            values={"token": Secret(_OLD_CONNECTION)},
            expires_at=None,
            scopes=None,
        ),
    )


def _envelope(
    code: RelayCode, data: Mapping[str, object] | None = None
) -> HttpResponse:
    info = RELAY_CODES[code]
    assert info.origin is CodeOrigin.RELAY
    assert info.http_status is not None
    return HttpResponse(
        status=info.http_status,
        headers={},
        body=encode_answer(Answer(code=code, data=data or {}, outcome=None)),
    )


def _started(*, interval_s: int = 7, expires_in_s: int = 600) -> HttpResponse:
    return _envelope(
        RelayCode.CONNECT_STARTED,
        {
            "user_code": _USER_CODE,
            "poll_secret": _POLL_SECRET,
            "interval_s": interval_s,
            "expires_in_s": expires_in_s,
        },
    )


def _pending() -> HttpResponse:
    return _envelope(RelayCode.CONNECT_PENDING)


def _granted(token: str = _CONNECTION_TOKEN) -> HttpResponse:
    return _envelope(RelayCode.CONNECT_GRANTED, {"token": token})


def _bare(status: int) -> HttpResponse:
    return HttpResponse(status=status, headers={}, body=b"")


@dataclass
class _Run:
    result: BrowserConnected | BrowserConnectFailed | RelayNotConnected
    events: list[str]
    shown: list[ConsentShown]
    transport: FakeTransport
    clock: _Clock
    redactor: Redactor
    store: CredentialStore


def _run(
    tmp_path: Path,
    script: Sequence[HttpResponse | TransportError],
    *,
    relay_connected: bool = True,
    environ: dict[str, str] | None = None,
    store_old: bool = False,
    strava: ConnectorInstance | None = None,
    before_request: Callable[[HttpRequest], None] | None = None,
    sleep_hook: Callable[[int], None] | None = None,
) -> _Run:
    store = _store(tmp_path)
    if relay_connected:
        _save_relay_token(store)
    if store_old:
        _save_old_connection(store)
    events: list[str] = []
    clock = _Clock(events)
    inner = FakeTransport(list(script))
    shown: list[ConsentShown] = []

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        events.append(f"request {request.method} {request.url}")
        if before_request is not None:
            before_request(request)
        return inner(request, timeout)

    def sleep(seconds: float) -> None:
        if sleep_hook is not None:
            sleep_hook(len(clock.sleeps) + 1)
        clock.sleep(seconds)

    def on_started(info: ConsentShown) -> None:
        events.append("started")
        shown.append(info)

    redactor = Redactor()
    result = run_browser_connect(
        strava if strava is not None else _strava(),
        _relay(),
        store=store,
        transport=transport,
        environ=environ or {},
        now=clock.now,
        sleep=sleep,
        redactor=redactor,
        on_started=on_started,
    )
    return _Run(result, events, shown, inner, clock, redactor, store)


def _files(tmp_path: Path) -> list[str]:
    directory = tmp_path / "credentials"
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


# --------------------------------------------------------------------------
# Grant (2.1, 2.2, 2.5, 2.6)
# --------------------------------------------------------------------------


def test_a_grant_stores_the_connection_token_owner_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _save_relay_token(store)
    assert store.load("strava") is None  # the starting state: no Strava file
    run = _run(tmp_path, [_started(), _pending(), _granted()])
    result = run.result
    assert isinstance(result, BrowserConnected)
    assert result.instance == "strava"
    assert result.path == store.path_for("strava")
    assert result.relay_url == _BASE
    assert result.env_override == ()
    assert stat.S_IMODE(result.path.stat().st_mode) == 0o600
    stored = store.load("strava")
    assert stored is not None
    assert stored.connector_id == "strava"
    assert stored.auth_style is AuthStyle.OAUTH_BROWSER
    assert set(stored.values) == {"token"}
    assert stored.values["token"].reveal() == _CONNECTION_TOKEN
    assert stored.expires_at is None
    assert stored.scopes is None


def test_the_order_is_start_then_the_callback_then_one_wait_before_each_poll(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, [_started(interval_s=7), _pending(), _pending(), _granted()])
    assert isinstance(run.result, BrowserConnected)
    assert run.events == [
        f"request POST {_START_URL}",
        "started",
        "sleep 7",
        f"request POST {_POLL_URL}",
        "sleep 7",
        f"request POST {_POLL_URL}",
        "sleep 7",
        f"request POST {_POLL_URL}",
    ]


def test_every_request_carries_the_relay_instances_token(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), _pending(), _granted()])
    assert isinstance(run.result, BrowserConnected)
    assert len(run.transport.requests) == 3
    for request in run.transport.requests:
        assert request.secret_headers["Authorization"].reveal() == (
            "Bearer " + _RELAY_TOKEN
        )
    assert json.loads(run.transport.requests[1].body or b"") == {
        "poll_secret": _POLL_SECRET
    }


def test_the_callback_receives_the_page_the_code_and_the_remaining_time(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, [_started(expires_in_s=540), _granted()])
    assert run.shown == [
        ConsentShown(
            instance="strava",
            page_url=_BASE + "/connect/strava?code=" + _USER_CODE,
            user_code=_USER_CODE,
            expires_in_s=540,
        )
    ]


def test_a_grant_replaces_an_earlier_connection(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), _granted()], store_old=True)
    assert isinstance(run.result, BrowserConnected)
    stored = run.store.load("strava")
    assert stored is not None
    assert stored.values["token"].reveal() == _CONNECTION_TOKEN


def test_the_result_names_a_set_override_variable(tmp_path: Path) -> None:
    variable = env_var_name("strava", "token")
    run = _run(tmp_path, [_started(), _granted()], environ={variable: "x" * 20})
    assert isinstance(run.result, BrowserConnected)
    assert run.result.env_override == (variable,)
    # The override is only reported; the granted token is still stored.
    stored = run.store.load("strava")
    assert stored is not None
    assert stored.values["token"].reveal() == _CONNECTION_TOKEN
    assert run.result.path == run.store.path_for("strava")


def test_the_relay_token_may_come_from_the_environment(tmp_path: Path) -> None:
    variable = env_var_name("home", "token")
    run = _run(
        tmp_path,
        [_started(), _granted()],
        relay_connected=False,
        environ={variable: _OTHER_RELAY_TOKEN},
    )
    assert isinstance(run.result, BrowserConnected)
    assert run.transport.requests[0].secret_headers["Authorization"].reveal() == (
        "Bearer " + _OTHER_RELAY_TOKEN
    )


def test_the_new_secrets_are_registered_with_the_redactor(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), _granted()])
    for secret in (_RELAY_TOKEN, _POLL_SECRET, _CONNECTION_TOKEN):
        assert run.redactor.redact("x " + secret + " y") == "x " + REDACTED + " y"


# --------------------------------------------------------------------------
# Relay instance with no token (2.1)
# --------------------------------------------------------------------------


def test_a_relay_instance_with_no_token_makes_no_request(tmp_path: Path) -> None:
    run = _run(tmp_path, [], relay_connected=False)
    assert run.result == RelayNotConnected(
        instance="strava",
        relay_instance="home",
        next_step="Connect the relay instance first: run `fitdocs connect home`.",
    )
    assert run.transport.requests == []
    assert run.events == []
    assert run.shown == []
    assert _files(tmp_path) == []


def test_a_relay_instance_with_no_token_leaves_an_earlier_connection(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    path = _save_old_connection(store)
    before = path.read_bytes()
    run = _run(tmp_path, [], relay_connected=False)
    assert isinstance(run.result, RelayNotConnected)
    assert path.read_bytes() == before


# --------------------------------------------------------------------------
# Refused, expired and failed endings store nothing (2.7, 2.8)
# --------------------------------------------------------------------------


def test_a_refusal_stores_nothing_and_says_what_to_do(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), _pending(), _envelope(RelayCode.CONNECT_REFUSED)])
    assert run.result == BrowserConnectFailed(
        instance="strava",
        code=RelayCode.CONNECT_REFUSED,
        explanation=explain(RelayCode.CONNECT_REFUSED),
        next_step=(
            "Run `fitdocs connect strava` again and allow every permission "
            "that is asked for."
        ),
        retry_after_s=None,
    )
    assert len(run.transport.requests) == 3
    assert _files(tmp_path) == ["home.toml"]


def test_a_refusal_leaves_an_earlier_connection_untouched(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = _save_old_connection(store)
    before = path.read_bytes()
    run = _run(
        tmp_path, [_started(), _envelope(RelayCode.CONNECT_REFUSED)], store_old=False
    )
    assert isinstance(run.result, BrowserConnectFailed)
    assert path.read_bytes() == before


def test_the_local_deadline_ends_the_attempt_without_asking_again(
    tmp_path: Path,
) -> None:
    # expires_in_s 60 and interval 20: the third wait lands exactly on the
    # deadline. The grant scripted after it stays unread.
    script = [
        _started(interval_s=20, expires_in_s=60),
        _pending(),
        _pending(),
        _granted(),
    ]
    run = _run(tmp_path, script)
    assert run.result == BrowserConnectFailed(
        instance="strava",
        code=RelayCode.CONNECT_EXPIRED,
        explanation=explain(RelayCode.CONNECT_EXPIRED),
        next_step="Run `fitdocs connect strava` again and finish within ten minutes.",
        retry_after_s=None,
    )
    assert run.clock.sleeps == [20, 20, 20]
    assert len(run.transport.requests) == 3
    assert _files(tmp_path) == ["home.toml"]


def test_a_wait_that_overshoots_the_deadline_also_expires(tmp_path: Path) -> None:
    script = [
        _started(interval_s=25, expires_in_s=60),
        _pending(),
        _pending(),
        _granted(),
    ]
    run = _run(tmp_path, script)
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.CONNECT_EXPIRED
    assert run.clock.sleeps == [25, 25, 25]
    assert len(run.transport.requests) == 3


def test_the_instant_before_the_deadline_still_polls(tmp_path: Path) -> None:
    script = [
        _started(interval_s=20, expires_in_s=61),
        _pending(),
        _pending(),
        _granted(),
    ]
    run = _run(tmp_path, script)
    assert isinstance(run.result, BrowserConnected)
    assert run.clock.sleeps == [20, 20, 20]


def test_a_refused_start_stores_nothing_and_never_calls_back(tmp_path: Path) -> None:
    run = _run(tmp_path, [_envelope(RelayCode.TOKEN_REVOKED)])
    assert run.result == BrowserConnectFailed(
        instance="strava",
        code=RelayCode.TOKEN_REVOKED,
        explanation=explain(RelayCode.TOKEN_REVOKED),
        next_step="Connect the relay instance first: run `fitdocs connect home`.",
        retry_after_s=None,
    )
    assert run.shown == []
    assert run.clock.sleeps == []
    assert _files(tmp_path) == ["home.toml"]


def test_a_malformed_started_answer_stores_nothing(tmp_path: Path) -> None:
    started = _envelope(RelayCode.CONNECT_STARTED, {"user_code": _USER_CODE})
    run = _run(tmp_path, [started])
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.ANSWER_MALFORMED
    assert run.shown == []
    assert _files(tmp_path) == ["home.toml"]


def test_a_rate_limit_carries_the_stated_wait(tmp_path: Path) -> None:
    limited = _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 9})
    run = _run(tmp_path, [_started(), limited])
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.RATE_LIMITED
    assert run.result.retry_after_s == 9
    assert run.result.next_step == "Wait 9 seconds, then try again."


def test_a_rate_limited_start_carries_the_stated_wait(tmp_path: Path) -> None:
    limited = _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 4})
    run = _run(tmp_path, [limited])
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.retry_after_s == 4
    assert run.result.next_step == "Wait 4 seconds, then try again."
    assert run.shown == []


def test_a_failed_poll_is_one_request_and_the_attempt_ends(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), _pending(), _bare(503)])
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.UNAVAILABLE
    assert len(run.transport.requests) == 3
    assert _files(tmp_path) == ["home.toml"]


def test_an_unreachable_relay_ends_the_attempt(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), TransportError("connection refused")])
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.RELAY_UNREACHABLE
    assert _files(tmp_path) == ["home.toml"]


def test_a_pending_answer_with_data_is_malformed(tmp_path: Path) -> None:
    run = _run(tmp_path, [_started(), _envelope(RelayCode.CONNECT_PENDING, {"a": 1})])
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.ANSWER_MALFORMED


def _interrupt_at_second_wait(number: int) -> None:
    if number == 2:
        raise KeyboardInterrupt


def _interrupt_at_poll(request: HttpRequest) -> None:
    if request.url == _POLL_URL:
        raise KeyboardInterrupt


_NON_GRANT_ENDINGS: Final[
    dict[
        str,
        tuple[
            list[Callable[[], HttpResponse | TransportError]],
            Callable[[], dict[str, Any]],
            bool,
        ],
    ]
] = {
    "refused start": ([lambda: _envelope(RelayCode.TOKEN_REVOKED)], dict, False),
    "malformed started answer": (
        [lambda: _envelope(RelayCode.CONNECT_STARTED, {"user_code": _USER_CODE})],
        dict,
        False,
    ),
    "refused poll": (
        [_started, lambda: _envelope(RelayCode.CONNECT_REFUSED)],
        dict,
        False,
    ),
    "malformed poll": (
        [_started, lambda: _envelope(RelayCode.CONNECT_PENDING, {"a": 1})],
        dict,
        False,
    ),
    "unreachable poll": ([_started, lambda: TransportError("refused")], dict, False),
    "local deadline": (
        [
            lambda: _started(interval_s=20, expires_in_s=60),
            _pending,
            _pending,
            _granted,
        ],
        dict,
        False,
    ),
    "poll answer outside the contract": (
        [],
        lambda: {
            "strava": _scripted_instance(
                ConsentPolled(code=RelayCode.REGISTRATION_ISSUED, token=None)
            )
        },
        False,
    ),
    "grant without a token": (
        [],
        lambda: {
            "strava": _scripted_instance(
                ConsentPolled(code=RelayCode.CONNECT_GRANTED, token=None)
            )
        },
        False,
    ),
    "interrupt during the wait": (
        [_started, _pending, _granted],
        lambda: {"sleep_hook": _interrupt_at_second_wait},
        True,
    ),
    "interrupt during the poll": (
        [_started, _granted],
        lambda: {"before_request": _interrupt_at_poll},
        True,
    ),
}


@pytest.mark.parametrize("ending", list(_NON_GRANT_ENDINGS))
def test_no_ending_but_a_grant_touches_an_earlier_connection(
    tmp_path: Path, ending: str
) -> None:
    makers, make_hooks, interrupts = _NON_GRANT_ENDINGS[ending]
    hooks = make_hooks()
    script = [make() for make in makers]
    store = _store(tmp_path)
    path = _save_old_connection(store)
    before = path.read_bytes()
    assert _OLD_CONNECTION.encode() in before  # the starting state: a connection
    if interrupts:
        with pytest.raises(KeyboardInterrupt):
            _run(tmp_path, script, **hooks)
    else:
        run = _run(tmp_path, script, **hooks)
        assert isinstance(run.result, BrowserConnectFailed)
    assert path.read_bytes() == before
    assert _files(tmp_path) == ["home.toml", "strava.toml"]


# --------------------------------------------------------------------------
# Interrupt (2.9)
# --------------------------------------------------------------------------


def test_an_interrupt_during_a_wait_stores_nothing(tmp_path: Path) -> None:
    def interrupt(number: int) -> None:
        if number == 2:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, [_started(), _pending(), _granted()], sleep_hook=interrupt)
    assert _files(tmp_path) == ["home.toml"]


def test_an_interrupt_during_a_poll_request_stores_nothing_and_keeps_the_old_file(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    path = _save_old_connection(store)
    before = path.read_bytes()

    def interrupt(request: HttpRequest) -> None:
        if request.url == _POLL_URL:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, [_started(), _granted()], before_request=interrupt)
    assert path.read_bytes() == before
    assert _files(tmp_path) == ["home.toml", "strava.toml"]


# --------------------------------------------------------------------------
# A connector that answers outside the contract
# --------------------------------------------------------------------------


class _Scripted:
    """A browser-consent connector whose poll answers are given."""

    connector_id = "strava"
    display_name = "Scripted"
    auth_style = AuthStyle.OAUTH_BROWSER
    capabilities: frozenset[object] = frozenset()
    credential_fields = StravaConnector.credential_fields

    def __init__(self, polled: ConsentPolled | RelayRefused) -> None:
        self._polled = polled

    def start_consent(
        self, session: ConnectorSession, relay_token: Secret
    ) -> ConsentStarted:
        return ConsentStarted(
            user_code=_USER_CODE,
            page_url=_BASE + "/connect/strava?code=" + _USER_CODE,
            poll_secret=Secret(_POLL_SECRET),
            interval_s=3,
            expires_at=session.now() + timedelta(seconds=600),
        )

    def poll_consent(
        self, session: ConnectorSession, started: ConsentStarted, relay_token: Secret
    ) -> ConsentPolled | RelayRefused:
        return self._polled


def _scripted_instance(polled: ConsentPolled | RelayRefused) -> ConnectorInstance:
    return ConnectorInstance(
        name="strava",
        connector=_Scripted(polled),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )


@pytest.mark.parametrize(
    "polled",
    [
        ConsentPolled(code=RelayCode.CONNECT_GRANTED, token=None),
        ConsentPolled(code=RelayCode.REGISTRATION_ISSUED, token=Secret("x" * 20)),
    ],
)
def test_a_poll_answer_that_is_not_pending_or_a_usable_grant_is_malformed(
    tmp_path: Path, polled: ConsentPolled
) -> None:
    run = _run(tmp_path, [], strava=_scripted_instance(polled))
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.code is RelayCode.ANSWER_MALFORMED
    assert _files(tmp_path) == ["home.toml"]


def test_a_refusal_the_connector_returns_is_reported_with_its_wait(
    tmp_path: Path,
) -> None:
    refused = RelayRefused(RelayCode.RATE_LIMITED, 1)
    run = _run(tmp_path, [], strava=_scripted_instance(refused))
    assert isinstance(run.result, BrowserConnectFailed)
    assert run.result.next_step == "Wait 1 second, then try again."


def test_a_connector_that_is_not_browser_consent_is_refused_untouched(
    tmp_path: Path,
) -> None:
    instance = ConnectorInstance(
        name="home",
        connector=RelayConnector(),
        lookback_days=30,
        settings=RelaySettings(url=_BASE),
    )
    with pytest.raises(AssertionError, match="not a browser-consent connector"):
        _run(tmp_path, [], strava=instance)
    assert _files(tmp_path) == ["home.toml"]


def test_the_session_gives_the_connector_no_credential_access(
    tmp_path: Path,
) -> None:
    seen: list[object] = []

    class _Probe(_Scripted):
        def poll_consent(
            self,
            session: ConnectorSession,
            started: ConsentStarted,
            relay_token: Secret,
        ) -> ConsentPolled | RelayRefused:
            seen.extend(
                [
                    session.credentials.scopes,
                    session.credentials.expires_at,
                    session.http.mode,
                ]
            )
            with pytest.raises(AssertionError):
                session.credentials.value("token")
            with pytest.raises(AssertionError):
                session.credentials.replace(
                    TokenSet(values={}, expires_at=None, scopes=None)
                )
            return ConsentPolled(code=RelayCode.CONNECT_PENDING, token=None)

    instance = ConnectorInstance(
        name="strava",
        connector=_Probe(RelayRefused(RelayCode.UNAVAILABLE)),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )
    run = _run(tmp_path, [], strava=instance, sleep_hook=None)
    assert seen[:3] == [None, None, CallMode.AUTH]
    assert isinstance(run.result, BrowserConnectFailed)


def test_a_relay_instance_that_is_not_a_relay_is_refused_untouched(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _save_relay_token(store)
    not_a_relay = ConnectorInstance(
        name="home",
        connector=RelayConnector(),
        lookback_days=30,
        settings=None,
    )
    with pytest.raises(AssertionError, match="not a relay instance"):
        run_browser_connect(
            _strava(),
            not_a_relay,
            store=store,
            transport=FakeTransport([]),
            environ={},
            now=lambda: datetime(2026, 3, 1, tzinfo=_PLUS_TWO),
            sleep=lambda seconds: None,
            redactor=Redactor(),
            on_started=lambda info: None,
        )


# --------------------------------------------------------------------------
# The fixed next steps
# --------------------------------------------------------------------------

_CHECK = (
    "Check the relay instance `home` and try again later; if it persists, "
    "tell the relay's operator."
)
_FIRST = "Connect the relay instance first: run `fitdocs connect home`."
_SPECIFIC: dict[RelayCode, str] = {
    RelayCode.TOKEN_MISSING: _FIRST,
    RelayCode.TOKEN_UNKNOWN: _FIRST,
    RelayCode.TOKEN_REVOKED: _FIRST,
    RelayCode.NOT_OFFERED: (
        "Ask the operator of the relay instance `home` to offer this target, "
        "or use another relay."
    ),
    RelayCode.CONNECT_REFUSED: (
        "Run `fitdocs connect strava` again and allow every permission "
        "that is asked for."
    ),
    RelayCode.CONNECT_EXPIRED: (
        "Run `fitdocs connect strava` again and finish within ten minutes."
    ),
    RelayCode.RATE_LIMITED: "Wait a few minutes, then try again.",
}


@pytest.mark.parametrize("code", list(RelayCode), ids=lambda c: c.value)
def test_every_code_has_its_fixed_next_step(code: RelayCode) -> None:
    step = consent_next_step(code, name="strava", relay="home", retry_after_s=None)
    assert step == _SPECIFIC.get(code, _CHECK)


def test_only_the_rate_limit_next_step_depends_on_the_stated_wait() -> None:
    for code in RelayCode:
        with_wait = consent_next_step(
            code, name="strava", relay="home", retry_after_s=5
        )
        without = consent_next_step(
            code, name="strava", relay="home", retry_after_s=None
        )
        assert (with_wait == without) is (code is not RelayCode.RATE_LIMITED)
    assert (
        consent_next_step(
            RelayCode.RATE_LIMITED, name="strava", relay="home", retry_after_s=5
        )
        == "Wait 5 seconds, then try again."
    )


def test_the_next_step_names_the_instances_it_was_given() -> None:
    assert "`fitdocs connect other`" in consent_next_step(
        RelayCode.TOKEN_MISSING, name="n", relay="other", retry_after_s=None
    )
    assert "`fitdocs connect mine`" in consent_next_step(
        RelayCode.CONNECT_REFUSED, name="mine", relay="r", retry_after_s=None
    )
