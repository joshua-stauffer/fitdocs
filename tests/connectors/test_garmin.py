"""The Garmin connector's declaration, registration, settings and key check
(garmin-connector task 3.1; Req 1.1-1.7, 2.1, 2.2, 7.1, 14.2, 14.5).

Everything runs against a scripted transport: no network, a synthetic key,
a synthetic token.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

import fitdocs.connectors as connectors_package
from fitdocs.connectors import (
    AuthStyle,
    Capability,
    CredentialField,
    SettingsContext,
    get,
    validate_connector,
)
from fitdocs.connectors.connect import Connected, ConnectFailed, run_connect
from fitdocs.connectors.credentials import CredentialStore
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.garmin import GarminConnector, _mint
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.protocol import (
    ConnectorSession,
    CredentialAccess,
    Granted,
    RemoteActivity,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import FakeTransport

_KEY = "gk-synthetic-4Vq8Zt"
# Three dot-separated base64url segments, each containing both `_` and `-`.
_TOKEN = (
    "eyJhbGci_OiJ0-ZXN0In0.eyJzdWIi_OiJzeW50-aGV0aWMtNzczMSJ9.c2ln_LXN5bnRo-ZXRpYy0xMg"
)
_MARKER = "BODYMARKER-5521"
_CLOCK = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
_TOKEN_URL = (
    "https://personal.connectapi.garmin.com"
    "/personalapitoken-service/personal-api/personal-api-key/token"
)


class _NoCredentials:
    def value(self, field: str) -> Secret:
        raise AssertionError("a key check takes its value as an argument")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: object) -> None:
        raise AssertionError("a key check stores nothing")


def _session(
    transport: FakeTransport, redactor: Redactor | None = None
) -> ConnectorSession:
    redactor = redactor if redactor is not None else Redactor()
    credentials: CredentialAccess = _NoCredentials()
    return ConnectorSession(
        instance="garmin",
        settings=None,
        http=HttpClient(
            transport,
            mode=CallMode.AUTH,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=credentials,
        data_root=Path("/nonexistent-data-root"),
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _text(body: str | bytes, status: int = 200, **headers: str) -> HttpResponse:
    raw = body.encode() if isinstance(body, str) else body
    return HttpResponse(status=status, headers=headers, body=raw)


def _token_ok() -> HttpResponse:
    return _text(_TOKEN)


def _verify(
    script: list[HttpResponse | TransportError],
) -> tuple[Granted, FakeTransport, ConnectorSession]:
    transport = FakeTransport(script)
    session = _session(transport)
    result = GarminConnector().verify(session, {"api_key": session.secret(_KEY)})
    return result, transport, session


def _refused(
    script: list[HttpResponse | TransportError],
) -> tuple[AuthFailure, FakeTransport]:
    transport = FakeTransport(script)
    session = _session(transport)
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector().verify(session, {"api_key": session.secret(_KEY)})
    return excinfo.value, transport


# --------------------------------------------------------------------------
# Declaration and registration (Req 1.1, 2.1, 2.2, 14.5)
# --------------------------------------------------------------------------


def test_the_declaration_is_one_secret_field_and_the_two_pull_capabilities() -> None:
    connector = GarminConnector()
    assert connector.connector_id == "garmin"
    assert connector.display_name == "Garmin"
    assert connector.auth_style is AuthStyle.API_KEY
    assert connector.capabilities == frozenset(
        {Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS}
    )
    assert connector.credential_fields == (
        CredentialField("api_key", "Personal API key", True),
    )
    assert validate_connector(connector) is None


def test_it_is_registered_after_strava_and_kept_out_of_the_public_names() -> None:
    assert isinstance(get("garmin"), GarminConnector)
    ids = [c.connector_id for c in connectors_package.available()]
    assert ids == ["folder", "intervals", "relay", "strava", "garmin"]
    assert "GarminConnector" not in connectors_package.__all__


def test_settings_accept_nothing_and_ignore_every_key(tmp_path: Path) -> None:
    context = SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")
    parse: Callable[[Mapping[str, object], SettingsContext], object] = (
        GarminConnector().parse_settings
    )
    assert parse({}, context) is None
    table = {
        "api_url": "https://elsewhere.invalid/",
        "account": "someone",
        "api_key": "from-the-file",
        "unknown": [1, 2],
    }
    assert parse(table, context) is None


# --------------------------------------------------------------------------
# The key check: one request, nothing kept (Req 1.2, 1.3, 7.1)
# --------------------------------------------------------------------------


def test_the_check_is_one_token_request_with_the_key_and_nothing_else() -> None:
    # A surplus scripted answer, so a repeated request would be answered and
    # only the count could notice it.
    _, transport, _ = _verify([_token_ok(), _token_ok()])
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == _TOKEN_URL
    assert not request.body
    assert request.single_attempt is True
    assert request.headers["Accept"] == "*/*"
    assert set(request.secret_headers) == {"Authorization"}
    assert request.secret_headers["Authorization"].reveal() == f"ApiKey {_KEY}"
    assert _KEY not in request.url
    assert _KEY not in repr(request.headers)


def test_a_token_is_discarded_and_scopes_and_expiry_are_absent() -> None:
    transport = FakeTransport([_token_ok()])
    session = _session(transport)
    connector = GarminConnector()
    result = connector.verify(session, {"api_key": session.secret(_KEY)})
    assert vars(connector) == {}
    assert result == Granted(scopes=None)
    assert result.scopes is None
    assert [f.name for f in dataclasses.fields(result)] == ["scopes"]
    assert _TOKEN not in repr(result)
    # Both token forms end up registered.
    assert session.redactor.redact(f"{_TOKEN} Bearer {_TOKEN}") == (
        f"{REDACTED} {REDACTED}"
    )


def test_a_token_with_surrounding_whitespace_is_accepted() -> None:
    result, transport, _ = _verify([_text(f"  {_TOKEN}\n")])
    assert result == Granted(scopes=None)
    assert len(transport.requests) == 1


def test_the_largest_accepted_token_is_16_kib() -> None:
    segment = "A" * ((16 * 1024 - 2) // 3)
    body = f"{segment}.{segment}.{segment}"
    body += "A" * (16 * 1024 - len(body))
    assert len(body) == 16 * 1024
    result, _, _ = _verify([_text(body)])
    assert result == Granted(scopes=None)


# --------------------------------------------------------------------------
# Each answer, per the design's error table (Req 1.4, 1.5, 1.6)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_says_wrong_expired_or_deleted_and_names_the_next_step(
    status: int,
) -> None:
    failure, transport = _refused([_text(f"nope {_MARKER}", status), _token_ok()])
    assert failure.kind is AuthFailureKind.REJECTED
    assert "wrong, expired or deleted" in failure.service_message
    assert "Create a new key on Garmin Connect" in failure.service_message
    assert "`fitdocs connect`" in failure.service_message
    assert str(status) in failure.service_message
    assert _MARKER not in failure.service_message
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("headers", "wait"),
    [
        ({"retry-after": "7"}, 7.0),
        (
            {
                "retry-after": "Wed, 04 Nov 2026 09:00:30 GMT",
                "date": "Wed, 04 Nov 2026 09:00:00 GMT",
            },
            30.0,
        ),
        ({"retry-after": "soon"}, None),
        ({}, None),
    ],
    ids=["seconds", "http-date", "unparseable", "absent"],
)
def test_a_rate_limit_carries_the_wait_garmin_states_and_is_not_retried(
    headers: dict[str, str], wait: float | None
) -> None:
    failure, transport = _refused(
        [_text(f"slow {_MARKER}", 429, **headers), _token_ok()]
    )
    assert failure.kind is AuthFailureKind.RATE_LIMITED
    assert failure.retry_after_s == wait
    assert "429" in failure.service_message
    assert _MARKER not in failure.service_message
    assert len(transport.requests) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 404, 400, 418, 301, 204])
def test_a_server_error_or_any_other_status_is_unavailable_naming_it(
    status: int,
) -> None:
    failure, transport = _refused([_text(f"oops {_MARKER}", status), _token_ok()])
    assert failure.kind is AuthFailureKind.UNAVAILABLE
    assert f"HTTP {status}" in failure.service_message
    assert _MARKER not in failure.service_message
    assert len(transport.requests) == 1


_SEGMENT = "abc_DEF-123"


@pytest.mark.parametrize(
    "body",
    [
        _MARKER,
        "",
        "   \n",
        f"{_SEGMENT}.{_SEGMENT}",
        f"{_SEGMENT}.{_SEGMENT}.{_SEGMENT}.{_SEGMENT}",
        f"{_SEGMENT}..{_SEGMENT}",
        f".{_SEGMENT}.{_SEGMENT}",
        f"{_SEGMENT}.{_SEGMENT}.{_SEGMENT}=",
        f"{_SEGMENT}.{_SEGMENT}.a b",
        f"{_SEGMENT}.{_SEGMENT}.{_SEGMENT}\n{_MARKER}",
        f'{{"token": "{_SEGMENT}.{_SEGMENT}.{_SEGMENT}", "m": "{_MARKER}"}}',
        b"\xff\xfe" + f"{_SEGMENT}.{_SEGMENT}.{_SEGMENT}".encode(),
        "A" * (16 * 1024 + 1 - 4) + ".b.c",
    ],
    ids=[
        "marker",
        "empty",
        "blank",
        "two-segments",
        "four-segments",
        "empty-middle",
        "empty-first",
        "padding",
        "space",
        "trailing-line",
        "json",
        "non-ascii",
        "oversize-short-segments",
    ],
)
def test_a_success_that_is_not_a_token_is_not_understood_and_never_quoted(
    body: str | bytes,
) -> None:
    failure, transport = _refused([_text(body), _token_ok()])
    assert failure.kind is AuthFailureKind.UNAVAILABLE
    assert "not understood" in failure.service_message
    assert _MARKER not in failure.service_message
    assert _SEGMENT not in failure.service_message
    assert len(transport.requests) == 1


def test_an_oversize_body_made_of_valid_segments_is_not_a_token() -> None:
    segment = "A" * 5461
    body = f"{segment}.{segment}.{segment}"
    assert len(body) == 16 * 1024 + 1
    failure, _ = _refused([_text(body)])
    assert "not understood" in failure.service_message


def test_the_minted_value_is_the_bearer_header_form_of_the_token() -> None:
    transport = FakeTransport([_token_ok()])
    session = _session(transport)
    minted = _mint(session, session.http, session.secret(_KEY))
    assert minted.reveal() == f"Bearer {_TOKEN}"


def test_a_transport_failure_is_one_request_and_reaches_connect_as_unavailable(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([TransportError("timed out"), _token_ok()])
    session = _session(transport)
    with pytest.raises(TransportError):
        GarminConnector().verify(session, {"api_key": session.secret(_KEY)})
    assert len(transport.requests) == 1

    transport = FakeTransport([TransportError("timed out"), _token_ok()])
    result = _connect(tmp_path, transport, key=_KEY)
    assert isinstance(result, ConnectFailed)
    assert result.kind is AuthFailureKind.UNAVAILABLE
    assert len(transport.requests) == 1


# --------------------------------------------------------------------------
# Through `fitdocs connect`'s engine (Req 1.2, 7.3 as far as 3.1 reaches)
# --------------------------------------------------------------------------


def _connect(
    tmp_path: Path, transport: FakeTransport, *, key: str
) -> Connected | ConnectFailed:
    instance = ConnectorInstance(
        name="garmin",
        connector=GarminConnector(),
        lookback_days=30,
        settings=None,
    )
    return run_connect(
        instance,
        {"api_key": key},
        store=CredentialStore(tmp_path / "creds"),
        transport=transport,
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )


def test_connect_stores_the_key_after_one_request_and_not_the_token(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([_token_ok(), _token_ok()])
    result = _connect(tmp_path, transport, key=_KEY)
    assert isinstance(result, Connected)
    assert len(transport.requests) == 1
    assert result.scopes is None
    stored = CredentialStore(tmp_path / "creds").load("garmin")
    assert stored is not None
    assert stored.scopes is None
    assert stored.expires_at is None
    assert {name: value.reveal() for name, value in stored.values.items()} == {
        "api_key": _KEY
    }
    saved = result.path.read_text(encoding="utf-8")
    assert _TOKEN not in saved
    assert _TOKEN not in repr(result)


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, AuthFailureKind.REJECTED),
        (403, AuthFailureKind.REJECTED),
        (429, AuthFailureKind.RATE_LIMITED),
        (503, AuthFailureKind.UNAVAILABLE),
        (200, AuthFailureKind.UNAVAILABLE),
    ],
)
def test_connect_with_a_refused_key_reports_it_once_and_stores_nothing(
    tmp_path: Path, status: int, kind: AuthFailureKind
) -> None:
    # Every answer echoes the key, a near-token and a marker, to be scrubbed
    # or never quoted.
    transport = FakeTransport(
        [_text(f"echo {_KEY} {_TOKEN[:-3]} {_MARKER}", status), _token_ok()]
    )
    result = _connect(tmp_path, transport, key=_KEY)
    assert isinstance(result, ConnectFailed)
    assert result.kind is kind
    assert len(transport.requests) == 1
    assert not (tmp_path / "creds").exists()
    rendered = f"{result.message} | {result.next_step} | {result!r}"
    assert _KEY not in rendered
    assert _MARKER not in rendered
    assert _TOKEN[:-3] not in rendered


# --------------------------------------------------------------------------
# The key appears in no exception (Req 7.3 as far as 3.1 reaches)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        _text(f"{_KEY} {_MARKER}", 401),
        _text(f"{_KEY}", 403),
        _text(f"{_KEY}", 429, **{"retry-after": "3"}),
        _text(f"{_KEY}", 500),
        _text(f"{_KEY}", 200),
        _text(f"{_KEY}.{_KEY}", 200),
    ],
)
def test_the_key_is_in_no_exception_text_or_repr(answer: HttpResponse) -> None:
    failure, _ = _refused([answer])
    for form in (
        str(failure),
        repr(failure),
        failure.service_message,
        repr(failure.args),
    ):
        assert _KEY not in form


# --------------------------------------------------------------------------
# The pull operations wait for later tasks (registry requires them)
# --------------------------------------------------------------------------


def test_the_four_pull_operations_are_named_connector_errors_that_make_no_request() -> (
    None
):
    transport = FakeTransport([_token_ok()])
    session = _session(transport)
    connector = GarminConnector()
    activity = RemoteActivity(remote_id="1", original_available=True)
    calls = (
        lambda: connector.list_activities(session, None),
        lambda: connector.fetch_activity(session, activity),
        lambda: connector.list_wellness(session, None),
        lambda: connector.package_wellness(session, ()),
    )
    for call in calls:
        with pytest.raises(ConnectorError) as excinfo:
            call()
        assert str(excinfo.value)
    assert transport.requests == []
