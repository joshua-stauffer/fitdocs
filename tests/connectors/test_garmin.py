"""The Garmin connector's declaration, registration, settings and key check
(garmin-connector task 3.1; Req 1.1-1.7, 2.1, 2.2, 7.1, 14.2, 14.5), and its
per-pull state, pacing and rate-limit waits (task 3.2; Req 2.3, 4.1, 4.7-4.9,
6.1, 6.3, 7.2-7.4).

Everything runs against a scripted transport: no network, a synthetic key,
a synthetic token.
"""

from __future__ import annotations

import dataclasses
import gc
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
from fitdocs.connectors.garmin import GarminConnector, _mint, _PullState
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
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
    assert len(connector._pulls) == 0
    assert set(vars(connector)) == {"_pulls"}
    assert _TOKEN not in repr(vars(connector))
    assert "Bearer" not in repr(vars(connector))
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
    assert "key check" in failure.service_message
    assert "next pull" not in failure.service_message
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


# --------------------------------------------------------------------------
# The per-pull state, pacing and waits (task 3.2; Req 2.3, 4.1, 4.7, 4.8, 4.9,
# 6.1, 6.3, 7.2, 7.3, 7.4)
# --------------------------------------------------------------------------

_LIST_URL = "https://personal.connectapi.garmin.com/activitylist-service/x"
_OTHER_URL = "https://personal.connectapi.garmin.com/sleep-service/y"
_ACCEPT = {"Accept": "application/json"}


class _Pull:
    """One pull's session over a scripted transport. ``log`` interleaves the
    requests the transport saw with the sleeps the connector made; the
    client's own sleep is separate, so a transport-level wait would show up as
    ``http_sleeps`` and never as a connector sleep."""

    def __init__(
        self,
        script: list[HttpResponse | TransportError],
        *,
        token: str = _TOKEN,
    ) -> None:
        self.fake = FakeTransport(script)
        self.log: list[str] = []
        self.sleeps: list[float] = []
        self.http_sleeps: list[float] = []
        self.redacted_at_get: list[bool] = []
        self.token = token
        self.redactor = Redactor()

        def transport(request: HttpRequest, timeout: float) -> HttpResponse:
            method = request.method
            self.log.append(method)
            if method == "GET":
                self.redacted_at_get.append(
                    self.redactor.redact(f"Bearer {self.token}") == REDACTED
                    and self.redactor.redact(self.token) == REDACTED
                )
            return self.fake(request, timeout)

        def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.log.append(f"sleep {seconds:g}")

        class _Key:
            def value(self, field: str) -> Secret:
                assert field == "api_key"
                return Secret(_KEY)

            @property
            def scopes(self) -> tuple[str, ...] | None:
                return None

            @property
            def expires_at(self) -> datetime | None:
                return None

            def replace(self, tokens: object) -> None:
                raise AssertionError("a pull stores nothing")

        credentials: CredentialAccess = _Key()
        self.session = ConnectorSession(
            instance="garmin",
            settings=None,
            http=HttpClient(
                transport,
                mode=CallMode.DATA,
                redactor=self.redactor,
                sleep=self.http_sleeps.append,
            ),
            credentials=credentials,
            data_root=Path("/nonexistent-data-root"),
            now=lambda: _CLOCK,
            sleep=sleep,
            redactor=self.redactor,
        )

    def gets(self) -> list[HttpRequest]:
        return [r for r in self.fake.requests if r.method == "GET"]


def _limited(**headers: str) -> HttpResponse:
    return _text(f"slow {_MARKER}", 429, **headers)


def _ok(body: str = "[]") -> HttpResponse:
    return _text(body)


def test_distinct_requests_are_spaced_a_second_with_none_before_the_first() -> None:
    pull = _Pull([_token_ok(), _ok("a"), _ok("b"), _ok("c")])
    connector = GarminConnector()
    first = connector._get(pull.session, _LIST_URL, _ACCEPT)
    second = connector._get(pull.session, _OTHER_URL, _ACCEPT)
    third = connector._get(pull.session, _LIST_URL, _ACCEPT)
    assert [r.body for r in (first, second, third)] == [b"a", b"b", b"c"]
    assert pull.log == [
        "POST",
        "sleep 1",
        "GET",
        "sleep 1",
        "GET",
        "sleep 1",
        "GET",
    ]
    assert pull.http_sleeps == []


def test_the_get_carries_the_bearer_and_the_callers_headers_and_no_429_retry() -> None:
    pull = _Pull([_token_ok(), _ok()])
    GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    request = pull.fake.requests[1]
    assert request.method == "GET"
    assert request.url == _LIST_URL
    assert request.headers["Accept"] == "application/json"
    assert request.retry_rate_limits is False
    assert set(request.secret_headers) == {"Authorization"}
    assert request.secret_headers["Authorization"].reveal() == f"Bearer {_TOKEN}"
    assert _TOKEN not in request.url
    assert _TOKEN not in repr(request.headers)
    assert pull.redacted_at_get == [True]


def test_a_429_is_returned_to_the_helper_and_never_retried_by_the_transport() -> None:
    pull = _Pull([_token_ok(), _limited(**{"retry-after": "9"}), _ok()])
    GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    # The transport would have waited on its own sleep and retried itself.
    assert pull.http_sleeps == []
    assert [r.retry_rate_limits for r in pull.gets()] == [False, False]


@pytest.mark.parametrize("status", [404, 401, 403, 204, 418])
def test_any_other_answer_goes_back_to_the_caller_unchanged(status: int) -> None:
    answer = _text(f"body {_MARKER}", status, **{"x-marker": "kept"})
    pull = _Pull([_token_ok(), answer])
    response = GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert response is answer
    assert pull.sleeps == [1.0]
    assert len(pull.fake.requests) == 2


def test_the_default_waits_are_30_60_120_240_with_no_extra_spacing_after_a_wait() -> (
    None
):
    pull = _Pull([_token_ok(), *[_limited() for _ in range(4)], _ok("done")])
    response = GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert response.body == b"done"
    assert pull.sleeps == [1.0, 30.0, 60.0, 120.0, 240.0]
    assert len(pull.gets()) == 5


def test_a_fifth_429_stops_with_the_rate_limit_failure_and_no_further_wait() -> None:
    pull = _Pull([_token_ok(), *[_limited() for _ in range(5)], _ok()])
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    failure = excinfo.value
    assert failure.kind is AuthFailureKind.RATE_LIMITED
    assert failure.retry_after_s is None
    assert "limiting requests" in failure.service_message
    assert "next pull resumes where this one stopped" in failure.service_message
    assert _MARKER not in failure.service_message
    assert pull.sleeps == [1.0, 30.0, 60.0, 120.0, 240.0]
    assert len(pull.gets()) == 5
    assert pull.log[-1] == "GET"


def test_a_stated_wait_is_honoured_in_seconds_or_as_an_http_date() -> None:
    pull = _Pull(
        [
            _token_ok(),
            _limited(**{"retry-after": "7"}),
            _limited(
                **{
                    "retry-after": "Wed, 04 Nov 2026 09:00:45 GMT",
                    "date": "Wed, 04 Nov 2026 09:00:00 GMT",
                }
            ),
            _ok(),
        ]
    )
    GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert pull.sleeps == [1.0, 7.0, 45.0]


def test_a_stated_wait_of_exactly_5_minutes_is_honoured() -> None:
    pull = _Pull([_token_ok(), _limited(**{"retry-after": "300"}), _ok()])
    GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert pull.sleeps == [1.0, 300.0]


@pytest.mark.parametrize("stated", ["301", "100000", "Wed, 04 Nov 2026 09:10:00 GMT"])
def test_a_stated_wait_over_5_minutes_stops_at_once_without_sleeping(
    stated: str,
) -> None:
    headers = {"retry-after": stated, "date": "Wed, 04 Nov 2026 09:00:00 GMT"}
    pull = _Pull([_token_ok(), _limited(**headers), _ok()])
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert excinfo.value.retry_after_s is not None
    assert excinfo.value.retry_after_s > 300.0
    assert pull.sleeps == [1.0]
    assert len(pull.gets()) == 1


def test_a_stated_wait_after_unstated_ones_follows_the_answer_position() -> None:
    pull = _Pull(
        [
            _token_ok(),
            _limited(),
            _limited(**{"retry-after": "7"}),
            _limited(),
            _ok(),
        ]
    )
    GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert pull.sleeps == [1.0, 30.0, 7.0, 120.0]


@pytest.mark.parametrize("stated", ["2", "0"])
def test_a_repeating_short_stated_wait_stops_after_four_repeats(stated: str) -> None:
    pull = _Pull(
        [_token_ok(), *[_limited(**{"retry-after": stated}) for _ in range(6)]]
    )
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert excinfo.value.retry_after_s == float(stated)
    assert pull.sleeps == [
        1.0,
        float(stated),
        float(stated),
        float(stated),
        float(stated),
    ]
    assert len(pull.gets()) == 5


def test_the_15_minute_budget_stops_across_requests_without_sleeping() -> None:
    long = {"retry-after": "300"}
    pull = _Pull(
        [
            _token_ok(),
            _limited(**long),
            _limited(**long),
            _ok("first"),
            _limited(**long),  # the pull's waits reach exactly 900 s here
            _limited(**{"retry-after": "1"}),
            _ok("never reached"),
        ]
    )
    connector = GarminConnector()
    assert connector._get(pull.session, _LIST_URL, _ACCEPT).body == b"first"
    with pytest.raises(AuthFailure) as excinfo:
        connector._get(pull.session, _OTHER_URL, _ACCEPT)
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert excinfo.value.retry_after_s == 1.0
    assert pull.sleeps == [1.0, 300.0, 300.0, 1.0, 300.0]
    assert len(pull.gets()) == 5
    state = connector._pulls[pull.session.http]
    assert state.waited_s == 900.0


def test_a_success_restarts_the_schedule_but_not_the_pull_budget() -> None:
    pull = _Pull(
        [
            _token_ok(),
            _limited(),
            _limited(),
            _ok("a"),
            _limited(),
            _ok("b"),
            _limited(),
            _limited(),
            _ok("c"),
        ]
    )
    connector = GarminConnector()
    for url in (_LIST_URL, _OTHER_URL, _LIST_URL):
        connector._get(pull.session, url, _ACCEPT)
    assert pull.sleeps == [1.0, 30.0, 60.0, 1.0, 30.0, 1.0, 30.0, 60.0]
    assert connector._pulls[pull.session.http].waited_s == 30 + 60 + 30 + 30 + 60


def test_the_repeat_count_is_per_request_not_per_pull() -> None:
    answers: list[HttpResponse | TransportError] = [_token_ok()]
    for _ in range(3):
        answers += [_limited(**{"retry-after": "1"}) for _ in range(3)] + [_ok()]
    pull = _Pull(answers)
    connector = GarminConnector()
    for _ in range(3):
        connector._get(pull.session, _LIST_URL, _ACCEPT)
    assert len(pull.gets()) == 12


# -- the token in a pull ------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_a_token_refusal_in_a_pull_is_the_rejected_key_failure(status: int) -> None:
    pull = _Pull([_text(f"no {_MARKER}", status), _token_ok(), _ok()])
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert excinfo.value.kind is AuthFailureKind.REJECTED
    assert "`fitdocs connect`" in excinfo.value.service_message
    assert _MARKER not in excinfo.value.service_message
    assert pull.log == ["POST"]


@pytest.mark.parametrize(("headers", "wait"), [({"retry-after": "7"}, 7.0), ({}, None)])
def test_a_token_429_in_a_pull_is_the_rate_limit_failure_with_no_wait(
    headers: dict[str, str], wait: float | None
) -> None:
    pull = _Pull([_text(f"slow {_MARKER}", 429, **headers), _token_ok(), _ok()])
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    failure = excinfo.value
    assert failure.kind is AuthFailureKind.RATE_LIMITED
    assert failure.retry_after_s == wait
    assert "limiting requests" in failure.service_message
    assert "next pull resumes where this one stopped" in failure.service_message
    assert _MARKER not in failure.service_message
    assert pull.log == ["POST"]


_NOT_A_TOKEN = [
    (_text(f"{_MARKER}"), "not understood"),
    (_text(f"{_TOKEN}.extra"), "not understood"),
    (_text(""), "not understood"),
]
_TOKEN_TROUBLES: list[tuple[HttpResponse | TransportError, str]] = [
    *[
        (_text(f"oops {_MARKER}", s), f"HTTP {s}")
        for s in (500, 502, 503, 404, 400, 418, 301, 204)
    ],
    *_NOT_A_TOKEN,
    (TransportError(f"timed out {_MARKER}"), "could not be reached"),
]


@pytest.mark.parametrize(("trouble", "says"), _TOKEN_TROUBLES)
def test_any_other_token_trouble_in_a_pull_is_the_kept_connector_error(
    trouble: HttpResponse | TransportError, says: str
) -> None:
    pull = _Pull([trouble, _token_ok(), _ok()])
    with pytest.raises(ConnectorError) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert not isinstance(excinfo.value, AuthFailure)
    assert type(excinfo.value) is ConnectorError
    assert says in str(excinfo.value)
    assert _MARKER not in str(excinfo.value)
    assert _MARKER not in repr(excinfo.value)
    assert pull.log == ["POST"]


_FAILED_TOKENS: list[HttpResponse | TransportError] = [
    _text("x", 401),
    _text("x", 403),
    _text("x", 429),
    _text("x", 500),
    _text("x", 200),
    TransportError("timed out"),
]


@pytest.mark.parametrize("trouble", _FAILED_TOKENS)
def test_a_failed_mint_raises_the_same_error_again_with_no_second_request(
    trouble: HttpResponse | TransportError,
) -> None:
    pull = _Pull([trouble, _token_ok(), _ok(), _ok()])
    connector = GarminConnector()
    with pytest.raises((AuthFailure, ConnectorError)) as first:
        connector._get(pull.session, _LIST_URL, _ACCEPT)
    for url in (_OTHER_URL, _LIST_URL):
        with pytest.raises((AuthFailure, ConnectorError)) as again:
            connector._get(pull.session, url, _ACCEPT)
        assert again.value is first.value
    assert pull.log == ["POST"]
    assert connector._pulls[pull.session.http].bearer is None


def test_one_token_request_serves_every_request_of_the_pull_even_after_waits() -> None:
    pull = _Pull([_token_ok(), _limited(), _ok(), _ok(), _ok()])
    connector = GarminConnector()
    for url in (_LIST_URL, _OTHER_URL, _LIST_URL):
        connector._get(pull.session, url, _ACCEPT)
    assert pull.log.count("POST") == 1
    assert len(pull.gets()) == 4


def test_two_pulls_mint_once_each_and_never_share_a_token() -> None:
    other_token = _TOKEN.replace("eyJhbGci", "ZXlKaGJHY2k")
    assert other_token != _TOKEN
    one = _Pull([_token_ok(), _ok(), _ok()])
    two = _Pull([_text(other_token), _ok(), _ok()], token=other_token)
    connector = GarminConnector()
    for _ in range(2):
        connector._get(one.session, _LIST_URL, _ACCEPT)
        connector._get(two.session, _LIST_URL, _ACCEPT)
    assert one.log.count("POST") == 1
    assert two.log.count("POST") == 1
    assert one.log.count("sleep 1") == 2
    assert two.log.count("sleep 1") == 2
    for pull, token in ((one, _TOKEN), (two, other_token)):
        sent = [
            r.secret_headers["Authorization"].reveal()
            for r in pull.fake.requests
            if r.method == "GET"
        ]
        assert sent == [f"Bearer {token}"] * 2


def test_a_pulls_state_goes_when_its_client_does() -> None:
    connector = GarminConnector()
    pull = _Pull([_token_ok(), _ok()])
    connector._get(pull.session, _LIST_URL, _ACCEPT)
    assert len(connector._pulls) == 1
    del pull
    gc.collect()
    assert len(connector._pulls) == 0


def test_the_state_never_shows_the_token_the_bearer_or_the_key() -> None:
    pull = _Pull([_token_ok(), _limited(), _ok()])
    connector = GarminConnector()
    connector._get(pull.session, _LIST_URL, _ACCEPT)
    state = connector._pulls[pull.session.http]
    assert isinstance(state.bearer, Secret)
    assert state.bearer.reveal() == f"Bearer {_TOKEN}"
    assert state.used is True
    assert state.consecutive_failures == 0
    rendered = repr(state) + repr(vars(connector))
    for secret in (_TOKEN, "Bearer", _KEY):
        assert secret not in rendered
    assert [f.name for f in dataclasses.fields(_PullState)] == [
        "bearer",
        "mint_error",
        "used",
        "waited_s",
        "consecutive_failures",
    ]


def test_the_key_check_neither_waits_nor_touches_the_pull_state() -> None:
    pull = _Pull([_token_ok(), _token_ok(), _ok()])
    connector = GarminConnector()
    connector.verify(pull.session, {"api_key": pull.session.secret(_KEY)})
    assert pull.sleeps == []
    assert len(connector._pulls) == 0
    connector._get(pull.session, _LIST_URL, _ACCEPT)
    # The pull minted its own token: the check kept none for it.
    assert pull.log == ["POST", "POST", "sleep 1", "GET"]


def test_the_token_and_a_throttled_answer_never_reach_an_exception_text() -> None:
    pull = _Pull(
        [_token_ok(), *[_text(f"{_TOKEN} {_KEY} {_MARKER}", 429) for _ in range(5)]]
    )
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    for form in (str(excinfo.value), repr(excinfo.value), repr(excinfo.value.args)):
        for secret in (_TOKEN, _KEY, _MARKER):
            assert secret not in form


def test_the_schedule_alone_reaches_the_budget_across_requests() -> None:
    # 30 + 60 + 120 + 240 = 450 a request: exactly 900 after two, and the
    # third request's 30 would cross it.
    answers: list[HttpResponse | TransportError] = [_token_ok()]
    for _ in range(2):
        answers += [*[_limited() for _ in range(4)], _ok()]
    pull = _Pull([*answers, _limited(), _ok("never reached")])
    connector = GarminConnector()
    for _ in range(2):
        connector._get(pull.session, _LIST_URL, _ACCEPT)
    with pytest.raises(AuthFailure) as excinfo:
        connector._get(pull.session, _LIST_URL, _ACCEPT)
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert excinfo.value.retry_after_s is None
    schedule = [30.0, 60.0, 120.0, 240.0]
    assert pull.sleeps == [1.0, *schedule, 1.0, *schedule, 1.0]
    assert len(pull.gets()) == 11


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_server_error_is_retried_by_the_transport_then_goes_back(status: int) -> None:
    answers = [_text(f"down {_MARKER}", status) for _ in range(3)]
    pull = _Pull([_token_ok(), *answers, _ok("never reached")])
    response = GarminConnector()._get(pull.session, _LIST_URL, _ACCEPT)
    assert response is answers[-1]
    assert pull.http_sleeps == [2.0, 4.0]
    assert pull.sleeps == [1.0]
    assert len(pull.gets()) == 3


def test_a_transport_failure_goes_back_unchanged_and_the_next_request_is_spaced() -> (
    None
):
    failure = TransportError("timed out")
    pull = _Pull([_token_ok(), failure, failure, failure, _ok("next")])
    connector = GarminConnector()
    with pytest.raises(TransportError) as excinfo:
        connector._get(pull.session, _LIST_URL, _ACCEPT)
    assert excinfo.value is failure
    assert pull.http_sleeps == [2.0, 4.0]
    assert connector._get(pull.session, _OTHER_URL, _ACCEPT).body == b"next"
    assert pull.log == ["POST", "sleep 1", "GET", "GET", "GET", "sleep 1", "GET"]


@pytest.mark.parametrize(
    ("last", "stated"), [({"retry-after": "21"}, 21.0), ({}, None)], ids=["21s", "60s"]
)
def test_a_wait_that_would_cross_the_budget_from_below_stops_without_sleeping(
    last: dict[str, str], stated: float | None
) -> None:
    long = {"retry-after": "300"}
    pull = _Pull(
        [
            _token_ok(),
            _limited(**long),
            _limited(**long),
            _ok("first"),
            _limited(**{"retry-after": "280"}),  # the pull's waits are now 880 s
            _limited(**last),
            _ok("never reached"),
        ]
    )
    connector = GarminConnector()
    connector._get(pull.session, _LIST_URL, _ACCEPT)
    with pytest.raises(AuthFailure) as excinfo:
        connector._get(pull.session, _OTHER_URL, _ACCEPT)
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert excinfo.value.retry_after_s == stated
    assert pull.sleeps == [1.0, 300.0, 300.0, 1.0, 280.0]
    assert connector._pulls[pull.session.http].waited_s == 880.0
