"""The Garmin connector's declaration, registration, settings and key check
(garmin-connector task 3.1; Req 1.1-1.7, 2.1, 2.2, 7.1, 14.2, 14.5), and its
per-pull state, pacing and rate-limit waits (task 3.2; Req 2.3, 4.1, 4.7-4.9,
6.1, 6.3, 7.2-7.4), and the activity listing (task 3.3; Req 3.1-3.7, 6.1-6.4,
6.7, 6.8, 7.5, 8.1).

Everything runs against a scripted transport: no network, a synthetic key,
a synthetic token.
"""

from __future__ import annotations

import dataclasses
import gc
import json
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import fitdocs.connectors as connectors_package
import fitdocs.connectors.garmin as garmin_module
from fitdocs import layout
from fitdocs.connectors import (
    AuthStyle,
    Capability,
    CredentialField,
    SettingsContext,
    get,
    validate_connector,
)
from fitdocs.connectors.connect import Connected, ConnectFailed, run_connect
from fitdocs.connectors.credentials import CredentialStore, env_var_name
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.garmin import (
    GarminConnector,
    _mint,
    _PullState,
)
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.ledger import (
    Ledger,
    LedgerEntry,
    Outcome,
    load_ledger,
    save_ledger,
)
from fitdocs.connectors.protocol import (
    ConnectorSession,
    CredentialAccess,
    Fetched,
    FetchResult,
    Granted,
    ListingDeferral,
    RemoteActivity,
)
from fitdocs.connectors.pull import InstancePullReport, PullOptions, run_pull
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance, load_connectors_settings
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


def test_the_three_later_operations_are_named_connector_errors_with_no_request() -> (
    None
):
    transport = FakeTransport([_token_ok()])
    session = _session(transport)
    connector = GarminConnector()
    activity = RemoteActivity(remote_id="1", original_available=True)
    calls = (
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
        now: datetime = _CLOCK,
        data_root: Path = Path("/nonexistent-data-root"),
        instance: str = "garmin",
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
            instance=instance,
            settings=None,
            http=HttpClient(
                transport,
                mode=CallMode.DATA,
                redactor=self.redactor,
                sleep=self.http_sleeps.append,
            ),
            credentials=credentials,
            data_root=data_root,
            now=lambda: now,
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


# --------------------------------------------------------------------------
# Listing activities (task 3.3; Req 3.1-3.7, 6.1-6.4, 6.7, 6.8, 7.5, 8.1)
# --------------------------------------------------------------------------

_LISTING_PATH = "/activitylist-service/activities/search/activities"
_GMT = "2026-03-01 08:00:00"
# The athlete's wall clock, deliberately not the UTC instant.
_LOCAL = "2026-03-01 03:00:00"


def _entry(
    activity_id: object = 4001,
    gmt: object = _GMT,
    *,
    type_key: object = "running",
    elapsed: object = 1800.5,
) -> dict[str, object]:
    """A listing entry carrying values a wrong field choice would show: the
    local start, a different `duration`, the name and owner, and a summary."""
    return {
        "activityId": activity_id,
        "activityName": f"Morning Run {_MARKER}",
        "startTimeLocal": _LOCAL,
        "startTimeGMT": gmt,
        "activityType": {"typeId": 1, "typeKey": type_key},
        "duration": 1650.25,
        "elapsedDuration": elapsed,
        "movingDuration": 1600.75,
        "distance": 9876.5,
        "calories": 777.0,
        "ownerId": 31337,
        "ownerDisplayName": "owner-display-xyz",
        "ownerFullName": "Owner Fullname Xyz",
        "locationName": "Locationville",
    }


def _page(*entries: object) -> HttpResponse:
    return _text(json.dumps(list(entries)))


def _ids(listing_activities: tuple[RemoteActivity, ...]) -> list[str]:
    return [a.remote_id for a in listing_activities]


def _numbered(first: int, count: int) -> list[dict[str, object]]:
    """Entries whose starts rise with the identifier, one minute apart."""
    return [_entry(first + i, gmt=_numbered_start(first + i)) for i in range(count)]


def _numbered_start(n: int) -> str:
    return (datetime(2026, 3, 1, 8, 0, tzinfo=UTC) + timedelta(minutes=n)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _query(request: HttpRequest) -> dict[str, list[str]]:
    return parse_qs(urlsplit(request.url).query, keep_blank_values=True)


def _list(
    script: list[HttpResponse | TransportError],
    since: datetime | None = None,
    *,
    now: datetime = _CLOCK,
) -> tuple[_Pull, tuple[RemoteActivity, ...]]:
    # Every identifier the script lists is recorded final, so the per-pull
    # limit keeps all of them and these tests see exactly what was paged.
    seen = [
        entry["activityId"]
        for answer in script
        if isinstance(answer, HttpResponse) and answer.status == 200
        for entry in json.loads(answer.body)
        if isinstance(entry, dict) and isinstance(entry.get("activityId"), int)
    ]
    with tempfile.TemporaryDirectory() as root:
        _record(Path(root), "garmin", dict.fromkeys(seen))
        pull = _Pull([_token_ok(), *script], now=now, data_root=Path(root))
        listing = GarminConnector().list_activities(pull.session, since)
    return pull, listing.activities


def _list_error(
    script: list[HttpResponse | TransportError],
    since: datetime | None = None,
) -> tuple[_Pull, Exception]:
    pull = _Pull([_token_ok(), *script])
    with pytest.raises((ConnectorError, AuthFailure)) as excinfo:
        GarminConnector().list_activities(pull.session, since)
    return pull, excinfo.value


def test_the_first_request_is_the_measured_form_with_both_date_filters() -> None:
    pull, activities = _list([_page(_entry())])
    [request] = pull.gets()
    parts = urlsplit(request.url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == (
        "https://personal.connectapi.garmin.com" + _LISTING_PATH
    )
    assert _query(request) == {
        "start": ["0"],
        "limit": ["200"],
        "sortOrder": ["asc"],
        "startDate": ["1990-01-01"],
        "endDate": ["2026-11-06"],
    }
    assert request.method == "GET"
    assert request.headers["Accept"] == "application/json"
    assert request.secret_headers["Authorization"].reveal() == f"Bearer {_TOKEN}"
    assert _ids(activities) == ["4001"]


def test_the_whole_history_is_paged_oldest_first_by_200_with_one_token() -> None:
    pull, activities = _list(
        [
            _page(*_numbered(1, 200)),
            _page(*_numbered(201, 200)),
            _page(*_numbered(401, 199)),
        ]
    )
    assert [_query(r)["start"] for r in pull.gets()] == [["0"], ["200"], ["400"]]
    assert all(_query(r)["limit"] == ["200"] for r in pull.gets())
    assert all(_query(r)["sortOrder"] == ["asc"] for r in pull.gets())
    assert all(_query(r)["startDate"] == ["1990-01-01"] for r in pull.gets())
    assert all(_query(r)["endDate"] == ["2026-11-06"] for r in pull.gets())
    assert all("excludeChildren" not in _query(r) for r in pull.gets())
    assert _ids(activities) == [str(n) for n in range(1, 600)]
    assert [r.method for r in pull.fake.requests] == ["POST", "GET", "GET", "GET"]
    assert pull.log == ["POST", "sleep 1", "GET", "sleep 1", "GET", "sleep 1", "GET"]


def test_a_full_page_followed_by_an_empty_one_ends() -> None:
    pull, activities = _list([_page(*_numbered(1, 200)), _page()])
    assert len(pull.gets()) == 2
    assert len(activities) == 200


def test_a_page_of_199_ends_with_no_further_request() -> None:
    pull, activities = _list([_page(*_numbered(1, 199))])
    assert len(pull.gets()) == 1
    assert len(activities) == 199


def test_an_empty_history_is_one_request_and_an_empty_listing() -> None:
    pull = _Pull([_token_ok(), _page()])
    listing = GarminConnector().list_activities(pull.session, None)
    assert len(pull.gets()) == 1
    assert listing.activities == ()
    assert listing.deferred == ()


def test_the_window_around_a_near_midnight_start_is_cut_on_the_utc_date() -> None:
    plus_five = timezone(timedelta(hours=5))
    # 2026-03-02 01:30 at +05:00 is 2026-03-01 20:30 UTC: the local date
    # (03-02) and the UTC date (03-01) differ, so a local-date slip shows.
    since = datetime(2026, 3, 2, 1, 30, tzinfo=plus_five)
    pull, activities = _list(
        [
            _page(
                _entry(1, "2026-03-01 20:29:59"),
                _entry(2, "2026-03-01 20:30:00"),
                _entry(3, "2026-03-01 20:30:01"),
                _entry(4, "2026-02-28 23:00:00"),
                _entry(5, "2026-03-02 00:00:00"),
                _entry(6, None),
                _entry(7, "not a time"),
            )
        ],
        since,
    )
    [request] = pull.gets()
    assert _query(request)["startDate"] == ["2026-02-28"]
    # The local-time listing of 2026-03-01 is why the window opens a day early;
    # the exact cut is the UTC start, equal kept.
    assert _ids(activities) == ["2", "3", "5", "6", "7"]


def test_the_end_date_is_the_day_after_the_utc_date_of_the_pull() -> None:
    minus_five = timezone(timedelta(hours=-5))
    # 23:30 at -05:00 on 11-05 is 04:30 UTC on 11-06: the end is 11-07.
    pull, _ = _list([_page()], now=datetime(2026, 11, 5, 23, 30, tzinfo=minus_five))
    assert _query(pull.gets()[0])["endDate"] == ["2026-11-07"]


def test_a_since_given_without_a_zone_is_read_as_utc() -> None:
    pull, activities = _list(
        [_page(_entry(1, "2026-03-01 20:29:59"), _entry(2, "2026-03-01 20:30:00"))],
        datetime(2026, 3, 1, 20, 30),
    )
    assert _query(pull.gets()[0])["startDate"] == ["2026-02-28"]
    assert _ids(activities) == ["2"]


def test_the_filter_applies_to_every_page_not_only_the_first() -> None:
    old = [_entry(n, "2026-01-01 00:00:00") for n in range(1, 201)]
    new = [_entry(n, "2026-03-05 00:00:00") for n in range(201, 206)]
    new.append(_entry(206, "2026-01-02 00:00:00"))
    pull, activities = _list(
        [_page(*old), _page(*new)], datetime(2026, 3, 1, tzinfo=UTC)
    )
    assert len(pull.gets()) == 2
    assert all(_query(r)["startDate"] == ["2026-02-28"] for r in pull.gets())
    assert all(_query(r)["endDate"] == ["2026-11-06"] for r in pull.gets())
    assert _ids(activities) == ["201", "202", "203", "204", "205"]


def test_a_repeated_identifier_across_pages_is_listed_once_keeping_the_first() -> None:
    first = _numbered(1, 200)
    repeat = _entry(200, "2026-04-01 09:00:00", type_key="cycling")
    pull, activities = _list(
        [
            _page(*first),
            _page(repeat, *_numbered(201, 199)),
            _page(_entry(400, _numbered_start(400))),
        ]
    )
    # The second page had 200 raw entries, one a repeat, so paging went on.
    assert len(pull.gets()) == 3
    ids = _ids(activities)
    assert ids == [str(n) for n in range(1, 401)]
    kept = next(a for a in activities if a.remote_id == "200")
    assert kept.sport == "running"
    assert kept.start == datetime(2026, 3, 1, 11, 20, tzinfo=UTC)


def test_a_repeated_identifier_within_a_page_is_listed_once() -> None:
    _, activities = _list([_page(_entry(5), _entry(6), _entry(5, type_key="cycling"))])
    assert _ids(activities) == ["5", "6"]
    assert activities[0].sport == "running"


def test_a_full_page_with_a_repeat_in_it_still_continues_to_the_next_page() -> None:
    page = [*_numbered(1, 199), _entry(1)]
    pull, activities = _list([_page(*page), _page(*_numbered(200, 3))])
    assert len(pull.gets()) == 2
    assert _ids(activities) == [str(n) for n in range(1, 203)]


def test_a_full_page_adding_a_single_new_identifier_continues() -> None:
    # The one new id sits between repeats: neither the page's edges nor a share
    # of new ids can stand in for "at least one".
    repeats = _numbered(1, 199)
    second = [*repeats[:100], _entry(500, "2026-03-02 00:00:00"), *repeats[100:]]
    pull, activities = _list(
        [
            _page(*_numbered(1, 200)),
            _page(*second),
            _page(_entry(600, "2026-03-03 00:00:00")),
        ]
    )
    assert [_query(r)["start"] for r in pull.gets()] == [["0"], ["200"], ["400"]]
    assert _ids(activities) == [*(str(n) for n in range(1, 201)), "500", "600"]


def test_an_entry_maps_to_a_remote_activity_and_nothing_else() -> None:
    _, activities = _list([_page(_entry(12345678901))])
    assert activities == (
        RemoteActivity(
            remote_id="12345678901",
            original_available=True,
            unavailable_reason=None,
            start=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
            sport="running",
            duration_s=1800.5,
            revision=None,
            suggested_name=None,
        ),
    )
    assert activities[0].start is not None
    assert activities[0].start.utcoffset() == timedelta(0)


def test_a_listing_entrys_name_owner_location_and_summary_reach_nothing() -> None:
    pull = _Pull([_token_ok(), _page(_entry())])
    listing = GarminConnector().list_activities(pull.session, None)
    assert [f.name for f in dataclasses.fields(RemoteActivity)] == [
        "remote_id",
        "original_available",
        "unavailable_reason",
        "start",
        "sport",
        "duration_s",
        "revision",
        "suggested_name",
    ]
    shown = repr(listing) + str(dataclasses.asdict(listing))
    for decoy in (
        "Morning Run",
        _MARKER,
        "owner-display-xyz",
        "Owner Fullname Xyz",
        "Locationville",
        "777",
        "9876",
        "31337",
        "1650",
        "1600",
    ):
        assert decoy not in shown
    assert listing.deferred == ()
    [activity] = listing.activities
    assert activity.suggested_name is None
    assert activity.revision is None
    assert activity.original_available is True


@pytest.mark.parametrize(
    "gmt",
    [
        None,
        20260301,
        "",
        "2026-13-45 12:00:00",
        "2026-02-30 12:00:00",
        "2026-03-01 25:00:00",
        "2026-03-01 08:00:60",
        "2026-03-01T08:00:00",
        "2026-03-01 08:00:00Z",
        "2026-03-01 08:00:00.5",
        " 2026-03-01 08:00:00",
        "2026-03-01 08:00:00\n",
        "2026-3-1 08:00:00",
        "2026-03-01 08:00",
        "٢٠٢٦-٠٣-٠١ ٠٨:٠٠:٠٠",
        "0000-01-01 00:00:00",
    ],
)
def test_a_start_that_is_not_a_valid_stated_instant_is_absent_not_an_error(
    gmt: object,
) -> None:
    _, activities = _list([_page(_entry(1, gmt))])
    assert activities[0].start is None
    assert activities[0].remote_id == "1"


def test_a_missing_start_key_is_absent() -> None:
    entry = _entry(1)
    del entry["startTimeGMT"]
    _, activities = _list([_page(entry)])
    assert activities[0].start is None


@pytest.mark.parametrize(
    "activity_type",
    [
        None,
        "running",
        ["running"],
        7,
        {},
        {"typeKey": None},
        {"typeKey": 5},
        {"typeKey": ""},
        {"typeKey": "  "},
        {"typeKey": ["running"]},
    ],
)
def test_a_sport_that_is_not_stated_text_is_absent(activity_type: object) -> None:
    entry = _entry(1)
    entry["activityType"] = activity_type
    _, activities = _list([_page(entry)])
    assert activities[0].sport is None
    assert activities[0].duration_s == 1800.5


def test_a_missing_activity_type_is_absent() -> None:
    entry = _entry(1)
    del entry["activityType"]
    _, activities = _list([_page(entry)])
    assert activities[0].sport is None


@pytest.mark.parametrize(
    "elapsed",
    [
        True,
        False,
        "1800",
        None,
        [1800],
        {"v": 1},
        float("nan"),
        float("inf"),
        float("-inf"),
        -1,
        -0.5,
        10**400,
    ],
)
def test_an_elapsed_duration_not_finite_and_non_negative_is_absent(
    elapsed: object,
) -> None:
    pull = _Pull([_token_ok(), _text(json.dumps([_entry(1, elapsed=elapsed)]))])
    activities = GarminConnector().list_activities(pull.session, None).activities
    assert activities[0].duration_s is None
    assert activities[0].sport == "running"


def test_a_missing_elapsed_duration_is_absent_even_with_a_duration_stated() -> None:
    entry = _entry(1)
    del entry["elapsedDuration"]
    _, activities = _list([_page(entry)])
    assert entry["duration"] == 1650.25
    assert activities[0].duration_s is None


def test_a_stated_zero_and_a_whole_number_elapsed_duration_are_kept_as_stated() -> None:
    _, activities = _list([_page(_entry(1, elapsed=0), _entry(2, elapsed=1800))])
    assert [a.duration_s for a in activities] == [0.0, 1800.0]
    assert all(isinstance(a.duration_s, float) for a in activities)


_BAD_IDS: list[object] = [
    1.0,
    4001.5,
    True,
    False,
    0,
    -7,
    "4001",
    f"id-{_MARKER}",
    "",
    None,
    [4001],
    {"id": 4001},
    float("nan"),
    "__missing__",
]


@pytest.mark.parametrize("bad", _BAD_IDS, ids=repr)
def test_an_entry_without_a_positive_whole_number_id_ends_the_pull_naming_it(
    bad: object,
) -> None:
    broken = _entry(1)
    if bad == "__missing__":
        del broken["activityId"]
    else:
        broken["activityId"] = bad
    pull, error = _list_error([_page(_entry(11), _entry(12), broken, _entry(14))])
    assert type(error) is ConnectorError
    assert "entry 3 has no positive whole-number identifier" in str(error)
    # The broken entry carries the marker in its name: quoting it shows here.
    assert _MARKER not in str(error)
    assert len(pull.gets()) == 1


def test_a_malformed_entry_is_named_by_its_position_in_the_whole_listing() -> None:
    pull, error = _list_error(
        [
            _page(*_numbered(1, 200)),
            _page(_entry(201), _entry("x"), _entry(203)),
            _page(),
        ]
    )
    assert "entry 202" in str(error)
    assert len(pull.gets()) == 2


def test_a_malformed_entry_that_the_window_would_drop_still_ends_the_pull() -> None:
    old = _entry(1, "2020-01-01 00:00:00")
    old["activityId"] = None
    _, error = _list_error([_page(old)], datetime(2026, 1, 1, tzinfo=UTC))
    assert type(error) is ConnectorError


@pytest.mark.parametrize(
    "body",
    [
        json.dumps({"activities": [_entry()]}),
        json.dumps(_entry()),
        json.dumps(_MARKER),
        "null",
        "7",
        "true",
        "",
        f"not json {_MARKER}",
        f"[{_MARKER}",
        f"[1, 2 {_MARKER}",
        f"<html>{_MARKER}</html>",
        "[" * 100000,
    ],
    ids=[
        "object-of-list",
        "one-object",
        "string",
        "null",
        "number",
        "bool",
        "empty",
        "text",
        "open",
        "truncated",
        "html",
        "deeply-nested",
    ],
)
def test_a_body_that_is_not_a_list_of_activity_objects_is_named_and_not_quoted(
    body: str,
) -> None:
    pull, error = _list_error([_text(body)])
    assert type(error) is ConnectorError
    assert _MARKER not in str(error)
    assert "listing" in str(error)
    assert "not a list" in str(error)
    assert len(pull.gets()) == 1


@pytest.mark.parametrize(
    "entry",
    [None, 7, f"text {_MARKER}", [_MARKER], True, 1.5],
    ids=["null", "number", "text", "list", "bool", "float"],
)
def test_an_entry_that_is_not_an_object_ends_the_pull_naming_its_position(
    entry: object,
) -> None:
    _, error = _list_error([_page(_entry(1), entry)])
    assert type(error) is ConnectorError
    assert "entry 2 is not an object" in str(error)
    assert _MARKER not in str(error)


def test_a_body_that_is_not_utf8_is_named_and_not_quoted() -> None:
    # Valid UTF-16 JSON: a decoder that guesses the encoding would accept it.
    body = json.dumps([_entry()]).encode("utf-16")
    _, error = _list_error([_text(body)])
    assert type(error) is ConnectorError
    assert "listing" in str(error)
    _, error = _list_error([_text(b"[\xff\xfe" + _MARKER.encode())])
    assert type(error) is ConnectorError
    assert _MARKER not in str(error)


def test_a_malformed_second_page_ends_the_pull_with_no_partial_listing() -> None:
    pull = _Pull([_token_ok(), _page(*_numbered(1, 200)), _text(f"oops {_MARKER}")])
    with pytest.raises(ConnectorError) as excinfo:
        GarminConnector().list_activities(pull.session, None)
    assert _MARKER not in str(excinfo.value)
    assert len(pull.gets()) == 2


def test_a_401_is_the_rejected_key_failure_and_is_not_repeated() -> None:
    pull, error = _list_error([_text(f"no {_MARKER}", 401), _page()])
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.REJECTED
    assert "401" in str(error)
    assert "wrong, expired or deleted" in str(error)
    assert "Create a new key on Garmin Connect" in str(error)
    assert "`fitdocs connect`" in str(error)
    # The engine appends the next step directly after this text.
    assert str(error).endswith(".")
    assert _MARKER not in str(error)
    assert len(pull.gets()) == 1


def test_a_403_is_rejected_with_the_refused_wording_and_no_bug_report() -> None:
    pull, error = _list_error([_text(f"no {_MARKER}", 403), _page()])
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.REJECTED
    text = str(error)
    assert "403" in text
    assert "refused" in text
    assert "terms" in text
    assert "restrict" in text
    assert "key's status on Garmin Connect" in text
    assert text.endswith(".")
    assert "report" not in text.lower()
    assert "bug" not in text.lower()
    assert "github" not in text.lower()
    assert _MARKER not in text
    assert len(pull.gets()) == 1


def test_a_429_past_the_waits_is_the_rate_limit_failure_naming_the_resume() -> None:
    pull, error = _list_error([*(_limited() for _ in range(5)), _page()])
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.RATE_LIMITED
    assert "429" in str(error)
    assert "next pull resumes" in str(error)
    assert str(error).endswith(".")
    assert _MARKER not in str(error)
    assert pull.sleeps == [1.0, 30.0, 60.0, 120.0, 240.0]


def test_a_short_stated_wait_on_a_later_page_is_waited_out_and_that_page_repeated() -> (
    None
):
    pull, activities = _list(
        [
            _page(*_numbered(1, 200)),
            _limited(**{"retry-after": "7"}),
            _page(*_numbered(201, 3)),
        ]
    )
    assert len(activities) == 203
    assert pull.sleeps == [1.0, 1.0, 7.0]
    assert [_query(r)["start"] for r in pull.gets()] == [["0"], ["200"], ["200"]]


def test_a_429_past_the_waits_on_a_later_page_ends_the_pull() -> None:
    pull = _Pull(
        [_token_ok(), _page(*_numbered(1, 200)), *(_limited() for _ in range(5))]
    )
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector().list_activities(pull.session, None)
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert [_query(r)["start"] for r in pull.gets()] == [["0"], *[["200"]] * 5]


def test_an_arrival_at_the_end_during_the_listing_is_listed_once() -> None:
    # 399 activities when the listing starts, so the second page would be short;
    # one more arrives after the first page and fills it, which needs a third.
    pull, activities = _list(
        [_page(*_numbered(1, 200)), _page(*_numbered(201, 200)), _page()]
    )
    assert [_query(r)["start"] for r in pull.gets()] == [["0"], ["200"], ["400"]]
    assert _ids(activities) == [str(n) for n in range(1, 401)]


def test_an_arrival_that_shifts_the_listing_repeats_nothing() -> None:
    # An older activity syncs after the first page: every later position moves
    # up one, so the first page's last entry opens the second page again.
    pull, activities = _list(
        [_page(*_numbered(1, 200)), _page(_numbered(200, 1)[0], *_numbered(201, 5))]
    )
    assert len(pull.gets()) == 2
    assert _ids(activities) == [str(n) for n in range(1, 206)]


def test_a_full_page_that_adds_no_new_identifier_ends_the_pull_naming_it() -> None:
    # Garmin answering the same full page whatever `start` says would otherwise
    # be paged at one request a second forever.
    pull, error = _list_error(
        [
            _page(*_numbered(1, 200)),
            _page(*_numbered(1, 200)),
            _page(*_numbered(1, 200)),
            _page(*_numbered(1, 200)),
        ]
    )
    assert type(error) is ConnectorError
    assert str(error) == (
        "Garmin's activity listing was not understood: a full page repeated "
        "activities already listed"
    )
    assert [_query(r)["start"] for r in pull.gets()] == [["0"], ["200"]]


def test_a_short_page_of_only_repeats_ends_the_listing_normally() -> None:
    pull, activities = _list([_page(*_numbered(1, 200)), _page(*_numbered(1, 3))])
    assert len(pull.gets()) == 2
    assert _ids(activities) == [str(n) for n in range(1, 201)]


@pytest.mark.parametrize("status", [500, 501, 502, 503, 504, 599])
def test_a_server_error_after_the_transports_retries_is_unavailable_with_the_resume(
    status: int,
) -> None:
    answers = [_text(f"down {_MARKER}", status) for _ in range(3)]
    pull, error = _list_error([*answers, _page(_entry())])
    assert type(error) is ConnectorError
    text = str(error)
    assert str(status) in text
    assert "unavailable" in text
    assert "next pull resumes" in text
    assert _MARKER not in text
    retried = status in (500, 502, 503, 504)
    assert len(pull.gets()) == (3 if retried else 1)
    assert pull.http_sleeps == ([2.0, 4.0] if retried else [])


def test_a_server_error_on_a_later_page_ends_the_pull() -> None:
    answers = [_text("x", 503) for _ in range(3)]
    pull = _Pull([_token_ok(), _page(*_numbered(1, 200)), *answers])
    with pytest.raises(ConnectorError) as excinfo:
        GarminConnector().list_activities(pull.session, None)
    assert "503" in str(excinfo.value)


@pytest.mark.parametrize("status", [204, 301, 400, 404, 410, 418, 422, 100])
def test_any_other_status_ends_the_pull_naming_the_status(status: int) -> None:
    pull, error = _list_error([_text(f"odd {_MARKER}", status), _page()])
    assert type(error) is ConnectorError
    assert str(status) in str(error)
    assert "unavailable" not in str(error)
    assert _MARKER not in str(error)
    assert len(pull.gets()) == 1


def test_a_transport_failure_is_the_unavailable_connector_error() -> None:
    failure = TransportError("timed out")
    pull, error = _list_error([failure, failure, failure, _page()])
    assert type(error) is ConnectorError
    assert "unavailable" in str(error)
    assert "could not be reached" in str(error)
    assert "next pull resumes" in str(error)
    assert len(pull.gets()) == 3


def test_a_refused_token_in_a_pull_ends_the_listing_with_no_listing_request() -> None:
    pull = _Pull([_text(f"no {_MARKER}", 401), _page()])
    with pytest.raises(AuthFailure) as excinfo:
        GarminConnector().list_activities(pull.session, None)
    assert excinfo.value.kind is AuthFailureKind.REJECTED
    assert pull.gets() == []


def test_an_unusable_token_answer_is_a_connector_error_with_no_listing_request() -> (
    None
):
    pull = _Pull([_text("not a token", 200), _page()])
    with pytest.raises(ConnectorError):
        GarminConnector().list_activities(pull.session, None)
    assert pull.gets() == []


def test_a_listing_request_has_the_token_only_as_authorization_and_never_the_key() -> (
    None
):
    pull, _ = _list([_page(*_numbered(1, 200)), _page()])
    for request in pull.gets():
        assert _KEY not in request.url
        assert _TOKEN not in request.url
        assert _KEY not in repr(request.headers)
        assert _TOKEN not in repr(request.headers)
        assert set(request.secret_headers) == {"Authorization"}
        assert request.secret_headers["Authorization"].reveal() == f"Bearer {_TOKEN}"
        assert request.headers["Accept"] == "application/json"
    assert [r.method for r in pull.fake.requests].count("POST") == 1


# --------------------------------------------------------------------------
# Task 3.4: the per-pull limit (Req 4.2, 4.3, 4.6)
# --------------------------------------------------------------------------

_INSTANCE = "garmin-work"
_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _at(minutes: int) -> str:
    return (_BASE + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _pages(entries: list[dict[str, object]]) -> list[HttpResponse | TransportError]:
    """The listing as Garmin pages it: 200 per page and a short last page, or
    an empty one after a full last page."""
    pages = [_page(*entries[i : i + 200]) for i in range(0, len(entries), 200)]
    if len(entries) % 200 == 0:
        pages.append(_page())
    return list(pages)


def _record(root: Path, instance: str, known: dict[int, str | None]) -> None:
    """A ledger holding one entry per id at the given revision (``None`` is the
    revision a Garmin listing states, so those entries are final)."""
    entries = tuple(
        LedgerEntry(str(n), Outcome.SKIPPED, revision=rev, detail="recorded")
        for n, rev in sorted(known.items(), key=lambda item: str(item[0]))
    )
    save_ledger(root, instance, Ledger("garmin", None, entries))


def _limited_list(
    root: Path, entries: list[dict[str, object]]
) -> tuple[_Pull, tuple[RemoteActivity, ...], tuple[object, ...]]:
    pull = _Pull([_token_ok(), *_pages(entries)], data_root=root, instance=_INSTANCE)
    listing = GarminConnector().list_activities(pull.session, None)
    return pull, listing.activities, listing.deferred


def _dated(ids: range, minute_of: Callable[[int], int]) -> list[dict[str, object]]:
    return [_entry(n, gmt=_at(minute_of(n))) for n in ids]


def test_the_limit_counts_only_the_not_final_in_start_order_and_stops_at_the_cut(
    tmp_path: Path,
) -> None:
    def minute(n: int) -> int:
        return (n * 37) % 260  # a permutation of 0..259: arrival is not start order

    entries = _dated(range(1, 261), minute)
    newest = next(n for n in range(1, 261) if minute(n) == 259)
    oldest = next(n for n in range(1, 261) if minute(n) == 0)
    at = {minute(n): n for n in range(1, 261)}
    # Minutes 235 and 245 are certainly after the cut, 259 is the newest.
    finals = {5, 17, 60, 101, 150, 199, 230, 260, newest, oldest, at[235], at[245]}
    by_start = sorted((n for n in range(1, 261) if n not in finals), key=minute)
    # Recorded at another revision, so not final: inside the first 200 (one of
    # them the very last kept) and so counted against the limit.
    stale = {by_start[0]: "r1", by_start[120]: "r2", by_start[199]: "r3"}
    _record(tmp_path, _INSTANCE, {**dict.fromkeys(finals), **stale})
    # Another instance's ledger must not be the one read.
    _record(tmp_path, "garmin", dict.fromkeys(by_start[:40]))

    pull, activities, deferred = _limited_list(tmp_path, entries)

    cut = by_start[200]  # the 201st not-final: the first thing withheld
    early = {f for f in finals if minute(f) < minute(cut)}
    late = finals - early
    # Finals before the cut are listed and uncounted; finals after it are
    # withheld with the rest, so the engine's watermark cannot pass them.
    assert newest in late and oldest in early and len(early) > 1 and len(late) > 1
    kept = early | set(by_start[:200])
    assert len(_ids(activities)) == len(kept) == 200 + len(early)
    assert set(_ids(activities)) == {str(n) for n in kept}
    assert _ids(activities) == [str(n) for n in sorted(kept, key=minute)]
    assert len(deferred) == 1
    note = deferred[0]
    assert isinstance(note, ListingDeferral)
    assert note.subject == _INSTANCE
    # Only the not-final among the withheld are counted, not the late finals.
    withheld = len(by_start) - 200
    assert withheld == 49
    assert note.reason.startswith(f"{withheld} more activities")
    assert len(pull.gets()) == 2


def test_finals_after_the_last_kept_not_final_stay_listed_when_nothing_is_withheld(
    tmp_path: Path,
) -> None:
    entries = [
        *_dated(range(1, 201), lambda n: n),
        *_dated(range(201, 211), lambda n: n),
    ]
    _record(tmp_path, _INSTANCE, dict.fromkeys(range(201, 211)))
    _, activities, deferred = _limited_list(tmp_path, entries)
    assert _ids(activities) == [str(n) for n in range(1, 211)]
    assert deferred == ()


def test_the_cut_is_the_first_not_final_past_the_limit_and_nothing_else(
    tmp_path: Path,
) -> None:
    entries = [
        *_dated(range(1, 201), lambda n: n),
        _entry(301, gmt=_at(300)),  # final, after the last kept: still before the cut
        _entry(401, gmt=_at(400)),  # final, tied with the cut and sorting before it
        _entry(402, gmt=_at(400)),  # not final: the 201st, so the cut
        _entry(403, gmt=_at(400)),  # final, tied with the cut and sorting after it
        _entry(900, gmt=None),  # final, with no start, so last of all
    ]
    _record(tmp_path, _INSTANCE, dict.fromkeys([301, 401, 403, 900]))
    _, activities, deferred = _limited_list(tmp_path, entries)
    assert _ids(activities) == [*(str(n) for n in range(1, 201)), "301", "401"]
    [note] = deferred
    assert isinstance(note, ListingDeferral)
    assert note.reason.startswith("1 more activity left")


def test_the_deferral_names_the_count_and_both_ways_to_continue(
    tmp_path: Path,
) -> None:
    entries = _dated(range(1, 202), lambda n: n)
    _, activities, deferred = _limited_list(tmp_path, entries)
    assert _ids(activities) == [str(n) for n in range(1, 201)]
    [note] = deferred
    assert isinstance(note, ListingDeferral)
    assert note.reason == (
        "1 more activity left for a later pull: the next `fitdocs pull` continues "
        "there, and a pull started with `--since` continues only with the same "
        "`--since`"
    )
    assert note.subject == _INSTANCE


def test_a_since_pull_limits_only_what_its_window_holds(tmp_path: Path) -> None:
    # Req 4.6: below the floor neither counts nor defers, and a final entry on
    # either side of the floor is not counted.
    entries = _dated(range(1, 241), lambda n: n)
    _record(tmp_path, _INSTANCE, dict.fromkeys([5, 30]))
    pull = _Pull(
        [_token_ok(), *_pages(entries)], data_root=tmp_path, instance=_INSTANCE
    )
    listing = GarminConnector().list_activities(
        pull.session, _BASE + timedelta(minutes=21)
    )
    assert _ids(listing.activities) == [str(n) for n in range(21, 222)]
    [note] = listing.deferred
    assert note.reason.startswith("19 more activities")


def test_every_final_outcome_is_left_out_of_the_count(tmp_path: Path) -> None:
    # A delivery still pending in the inbox is the state a real pull leaves.
    sha = "a" * 64
    entries = (
        LedgerEntry("1", Outcome.DELIVERED, sha256=sha, pending=f"{_INSTANCE}/1.fit"),
        LedgerEntry("2", Outcome.ALREADY_HELD, sha256=sha),
        LedgerEntry("3", Outcome.SKIPPED, detail="recorded"),
    )
    save_ledger(tmp_path, _INSTANCE, Ledger("garmin", None, entries))
    _, activities, deferred = _limited_list(
        tmp_path, _dated(range(1, 204), lambda n: n)
    )
    assert len(activities) == 203
    assert deferred == ()


def test_exactly_the_limit_of_not_final_activities_defers_nothing(
    tmp_path: Path,
) -> None:
    entries = _dated(range(1, 201), lambda n: n)
    _, activities, deferred = _limited_list(tmp_path, entries)
    assert len(activities) == 200
    assert deferred == ()


def test_finals_do_not_count_toward_the_limit_that_defers_nothing(
    tmp_path: Path,
) -> None:
    entries = _dated(range(1, 251), lambda n: (n * 7) % 250)
    _record(tmp_path, _INSTANCE, dict.fromkeys(range(201, 251)))
    _, activities, deferred = _limited_list(tmp_path, entries)
    assert _ids(activities) == [
        str(n) for n in sorted(range(1, 251), key=lambda n: (n * 7) % 250)
    ]
    assert deferred == ()


def test_an_activity_with_no_start_sorts_last_and_falls_into_the_remainder(
    tmp_path: Path,
) -> None:
    entries = [_entry(900, gmt=None), *_dated(range(1, 201), lambda n: n)]
    assert len(entries) == 201
    _, activities, deferred = _limited_list(tmp_path, entries)
    assert _ids(activities) == [str(n) for n in range(1, 201)]
    [note] = deferred
    assert isinstance(note, ListingDeferral)
    assert note.reason.startswith("1 more activity")


def test_activities_with_no_start_follow_the_dated_ones_in_the_engines_tie_order(
    tmp_path: Path,
) -> None:
    undated = [_entry(n, gmt=None) for n in range(990, 1050)]
    dated = _dated(range(1, 151), lambda n: 500 - n)
    _, activities, deferred = _limited_list(tmp_path, [*undated, *dated])
    # Dated first (oldest start first), then the undated by identifier text,
    # which is the engine's own order: "1000" sorts before "990".
    expected = [str(n) for n in range(150, 0, -1)] + [
        str(n) for n in sorted(range(990, 1050), key=str)[:50]
    ]
    assert _ids(activities) == expected
    [note] = deferred
    assert isinstance(note, ListingDeferral)
    assert note.reason.startswith("10 more activities")


@pytest.mark.parametrize(
    "content",
    [
        f'ledger_version = "{_MARKER}\nnot toml',
        f'ledger_version = 1\nconnector = "{_MARKER}"\n',
    ],
    ids=["not-toml", "another-connectors-ledger"],
)
def test_an_unreadable_ledger_ends_the_pull_with_a_named_error(
    tmp_path: Path, content: str
) -> None:
    path = layout.connector_ledger_path(tmp_path, _INSTANCE)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    pull = _Pull([_token_ok(), _page(_entry())], data_root=tmp_path, instance=_INSTANCE)
    with pytest.raises(ConnectorError) as excinfo:
        GarminConnector().list_activities(pull.session, None)
    error = excinfo.value
    assert type(error) is ConnectorError
    assert "ledger" in str(error)
    assert _MARKER not in str(error)
    assert _MARKER not in repr(error)
    assert error.__cause__ is None
    assert error.__suppress_context__


def test_a_deferral_alone_is_no_failure_when_the_engine_runs_the_pull(
    tmp_path: Path,
) -> None:
    entries = _dated(range(1, 202), lambda n: 1000 - n)

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        if request.method == "POST":
            return _token_ok()
        assert request.method == "GET"
        start = int(_query(request)["start"][0])
        return _page(*entries[start : start + 200])

    instances = load_connectors_settings(
        {"connectors": {"garmin": {}}},
        settings_file=tmp_path / "fitdocs.toml",
        context=SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox"),
    )
    report = run_pull(
        tmp_path,
        instances,
        inbox=tmp_path / "inbox",
        store=None,
        transport=transport,
        options=PullOptions(since=None, dry_run=True),
        environ={env_var_name("garmin", "api_key"): _KEY},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )
    [instance] = report.instances
    assert instance.error is None
    assert instance.failed == ()
    assert not report.failed
    assert instance.listed == 200
    assert instance.would_fetch == tuple(sorted(str(n) for n in range(2, 202)))
    [note] = instance.deferred
    assert note.subject == "garmin"
    assert note.detail.startswith("1 more activity")
    assert "`--since`" in note.detail


def test_a_since_pull_that_defers_is_followed_by_plain_pulls_that_reach_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The watermark is computed over the listing, so a listing that kept the
    # finals beyond its cut would let it jump past the deferred remainder and
    # strand the history between. Small scale: the limit is 5, there are 14
    # activities, `--since` starts at the 8th and its oldest fails once.
    monkeypatch.setattr(garmin_module, "ACTIVITIES_PER_PULL", 5)
    entries = _dated(range(1, 15), lambda n: n * 1440)
    fetched: list[str] = []
    failing = {"8"}

    class _Delivering(GarminConnector):
        def fetch_activity(
            self, session: ConnectorSession, activity: RemoteActivity
        ) -> FetchResult:
            if activity.remote_id in failing:
                failing.discard(activity.remote_id)
                raise RuntimeError("one bad download")
            fetched.append(activity.remote_id)
            return Fetched(
                bytes([14, 16, 0, 0, 0, 0, 0, 0])
                + b".FIT"
                + activity.remote_id.encode()
            )

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        if request.method == "POST":
            return _token_ok()
        start = int(_query(request)["start"][0])
        return _page(*entries[start : start + 200])

    instance = ConnectorInstance("garmin", _Delivering(), 0, None)

    def pull(since: datetime | None) -> InstancePullReport:
        report = run_pull(
            tmp_path,
            (instance,),
            inbox=tmp_path / "inbox",
            store=None,
            transport=transport,
            options=PullOptions(since=since, dry_run=False),
            environ={env_var_name("garmin", "api_key"): _KEY},
            now=lambda: _BASE + timedelta(days=30),
            sleep=lambda seconds: None,
            redactor=Redactor(),
        )
        [one] = report.instances
        assert one.error is None
        return one

    first = pull(_BASE + timedelta(days=8))
    assert [note.subject for note in first.failed] == ["8"]
    assert first.deferred[0].detail.startswith("2 more activities")
    assert fetched == ["9", "10", "11", "12"]
    for _ in range(4):
        last = pull(None)
        if not last.deferred:
            break
    assert last.deferred == ()
    assert sorted(fetched, key=int) == [str(n) for n in range(1, 15)]
    assert len(fetched) == 14
    again = pull(None)
    assert again.delivered == () and again.failed == ()
    ledger = load_ledger(tmp_path, "garmin", connector_id="garmin")
    assert all(ledger.is_final(str(n), None) for n in range(1, 15))
