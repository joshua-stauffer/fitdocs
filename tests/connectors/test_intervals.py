"""The intervals.icu connector's declaration, registration, settings, key
check, listing and file download (intervals-connector tasks 3.1 to 3.4).

Task 3.1 (Req 1.1, 1.5, 2.1-2.4, 5.6, 10.2, 10.4) covers what needs no
request: the declaration, the registry entry, the ``sources`` settings
parser, and the connector's own address admitted by the service-neutral scan.
Task 3.2 (Req 1.2, 1.3, 1.4, 5.7) covers ``verify``: the one listing request,
the Basic credential and its registration for redaction, the status mapping,
and the service-message helper. Task 3.3 (Req 1.5, 3.1-3.8, 5.1-5.5, 5.7,
6.1) covers ``list_activities``: the date windows, the six-field request, the
entry mapping and the status mapping for a listing. Task 3.4 (Req 4.1-4.5,
4.7, 5.1-5.5, 5.7) covers ``fetch_activity``: the request, bounded
decompression, GPX and TCX recognition, the no-file declination and the
download branch of the status mapping.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
import zlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from fitdocs.connectors import (
    AuthStyle,
    Capability,
    CredentialField,
    SettingsContext,
    get,
    validate_connector,
)
from fitdocs.connectors import intervals as intervals_module
from fitdocs.connectors.connect import ConnectFailed, run_connect
from fitdocs.connectors.credentials import CredentialStore
from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    ConnectorSettingsError,
)
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    Transport,
)
from fitdocs.connectors.intervals import (
    DEFAULT_SOURCES,
    INTERVALS_CONNECTOR_ID,
    IntervalsConnector,
    IntervalsDownloadError,
    IntervalsSettings,
    _service_message,
)
from fitdocs.connectors.protocol import (
    ConnectorSession,
    CredentialAccess,
    Declined,
    Fetched,
    FetchResult,
    Listing,
    RemoteActivity,
    TokenSet,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import (
    ConnectorInstance,
    ConnectorsSettingsError,
    load_connectors_settings,
)
from tests.connectors.conftest import FakeTransport
from tests.fixtures import builder


def _context(tmp_path: Path) -> SettingsContext:
    return SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")


def _parse(tmp_path: Path, table: dict[str, object]) -> IntervalsSettings:
    return IntervalsConnector().parse_settings(table, _context(tmp_path))


# --------------------------------------------------------------------------
# Registration and declaration (Req 1.1, 1.5, 10.2)
# --------------------------------------------------------------------------


def test_the_registry_returns_the_connector_and_its_gate_accepts_it() -> None:
    connector = get("intervals")
    assert isinstance(connector, IntervalsConnector)
    assert INTERVALS_CONNECTOR_ID == "intervals"
    assert validate_connector(connector) is None


def test_a_fresh_import_registers_folder_then_intervals() -> None:
    probe = (
        "import fitdocs.connectors as c; "
        "print(','.join(x.connector_id for x in c.available()))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "folder,intervals"


def test_the_declaration_is_a_personal_key_pull_only_connector() -> None:
    connector = IntervalsConnector()
    assert connector.connector_id == "intervals"
    assert connector.display_name == "intervals.icu"
    assert connector.auth_style is AuthStyle.API_KEY
    assert connector.capabilities == frozenset({Capability.PULL_ACTIVITIES})
    assert connector.credential_fields == (
        CredentialField(
            "api_key", "intervals.icu API key (Settings, Developer Settings)", True
        ),
    )


def test_an_instance_table_without_a_connector_key_resolves_to_it(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "fitdocs.toml"
    instances = load_connectors_settings(
        {"connectors": {"intervals": {}}},
        settings_file=settings_file,
        context=_context(tmp_path),
    )
    assert len(instances) == 1
    assert instances[0].name == "intervals"
    assert instances[0].connector is get("intervals")
    assert instances[0].settings == IntervalsSettings(sources=DEFAULT_SOURCES)


# --------------------------------------------------------------------------
# Settings (Req 2.1-2.4)
# --------------------------------------------------------------------------


def test_absent_sources_gives_the_default(tmp_path: Path) -> None:
    assert frozenset({"GARMIN_CONNECT"}) == DEFAULT_SOURCES
    assert _parse(tmp_path, {}).sources == frozenset({"GARMIN_CONNECT"})


def test_a_two_name_list_is_read_as_a_set(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"sources": ["ZWIFT", "GARMIN_CONNECT"]})
    assert settings.sources == frozenset({"ZWIFT", "GARMIN_CONNECT"})


def test_an_unpublished_well_formed_name_is_accepted(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"sources": ["NOT_A_PUBLISHED_SOURCE_9"]})
    assert settings.sources == frozenset({"NOT_A_PUBLISHED_SOURCE_9"})


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ([], "[]"),
        ("GARMIN_CONNECT", "'GARMIN_CONNECT'"),
        (["garmin_connect"], "'garmin_connect'"),
        (["GARMIN_CONNECT", 7], "7"),
        (["GARMIN_CONNECT\n"], "'GARMIN_CONNECT\\n'"),
    ],
)
def test_a_malformed_sources_value_is_refused_naming_key_and_value(
    tmp_path: Path, value: object, shown: str
) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"sources": value})
    assert excinfo.value.key == "sources"
    assert shown in excinfo.value.message
    assert "GARMIN_CONNECT" in excinfo.value.message


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"colour": "teal", "sources": ["ZWIFT"]})
    assert settings == IntervalsSettings(sources=frozenset({"ZWIFT"}))


def test_an_empty_sources_list_in_a_settings_file_names_file_instance_and_key(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "fitdocs.toml"
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"intervals": {"sources": []}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    message = str(excinfo.value)
    assert message.startswith(f"{settings_file}: [connectors.intervals] sources: ")
    assert "[]" in message


# --------------------------------------------------------------------------
# The key check and the credential (task 3.2; Req 1.2, 1.3, 1.4, 5.7)
# --------------------------------------------------------------------------

_KEY = "ik-synthetic-7Q2x9"
# base64 of "API_KEY:ik-synthetic-7Q2x9", written as a literal.
_TOKEN = "QVBJX0tFWTppay1zeW50aGV0aWMtN1EyeDk="
_BASIC = f"Basic {_TOKEN}"
_CLOCK = datetime(2026, 3, 1, 0, 30, tzinfo=UTC)


class _StubCredentials:
    """A credential access that refuses value reads and stores (the check
    receives its value as an argument); its scopes and expiry read as
    absent."""

    def value(self, field: str) -> Secret:
        raise AssertionError("verify takes its values as an argument")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("verify stores nothing")


def _session(
    tmp_path: Path,
    transport: Transport,
    *,
    now: datetime = _CLOCK,
    redactor: Redactor | None = None,
    mode: CallMode = CallMode.AUTH,
    settings: IntervalsSettings | None = None,
    credentials: CredentialAccess | None = None,
) -> ConnectorSession:
    redactor = redactor if redactor is not None else Redactor()
    return ConnectorSession(
        instance="intervals",
        settings=settings
        if settings is not None
        else IntervalsSettings(sources=DEFAULT_SOURCES),
        http=HttpClient(
            transport,
            mode=mode,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=credentials if credentials is not None else _StubCredentials(),
        data_root=tmp_path,
        now=lambda: now,
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _verify(
    tmp_path: Path,
    responses: list[HttpResponse],
    *,
    now: datetime = _CLOCK,
) -> tuple[FakeTransport, ConnectorSession]:
    """Run the key check once against ``responses``; the key is registered
    with the redactor the way the connect engine registers an answer."""
    transport = FakeTransport(list(responses))
    session = _session(tmp_path, transport, now=now)
    IntervalsConnector().verify(session, {"api_key": session.secret(_KEY)})
    return transport, session


def _failure(
    tmp_path: Path, response: HttpResponse
) -> tuple[AuthFailure, FakeTransport]:
    transport = FakeTransport([response])
    session = _session(tmp_path, transport)
    with pytest.raises(AuthFailure) as excinfo:
        IntervalsConnector().verify(session, {"api_key": session.secret(_KEY)})
    return excinfo.value, transport


def _ok() -> HttpResponse:
    return HttpResponse(status=200, headers={}, body=b"[]")


def test_the_check_is_one_listing_request_for_athlete_zero(tmp_path: Path) -> None:
    # A surplus scripted answer, so a second request would be answered and
    # only the count below could notice it.
    transport, _ = _verify(tmp_path, [_ok(), _ok()])
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    parts = urlsplit(request.url)
    assert (parts.scheme, parts.netloc) == ("https", "intervals.icu")
    assert parts.path == "/api/v1/athlete/0/activities"
    assert parse_qs(parts.query, keep_blank_values=True) == {
        "oldest": ["2026-02-28"],
        "limit": ["1"],
        "fields": ["id"],
    }


def test_oldest_is_the_utc_day_before_a_clock_in_another_zone(
    tmp_path: Path,
) -> None:
    # 2026-03-10 05:00 at UTC+10 is 2026-03-09 19:00 UTC: the local date is
    # the 10th, the UTC date the 9th.
    ahead = datetime(2026, 3, 10, 5, 0, tzinfo=timezone(timedelta(hours=10)))
    transport, _ = _verify(tmp_path, [_ok()], now=ahead)
    query = parse_qs(urlsplit(transport.requests[0].url).query)
    assert query["oldest"] == ["2026-03-08"]


def test_the_credential_is_the_basic_form_of_the_key_sent_as_a_secret_header(
    tmp_path: Path,
) -> None:
    transport, _ = _verify(tmp_path, [_ok()])
    request = transport.requests[0]
    assert list(request.secret_headers) == ["Authorization"]
    assert request.secret_headers["Authorization"].reveal() == _BASIC
    assert {name.lower() for name in request.headers} <= {"user-agent"}
    assert _KEY not in request.url
    assert _TOKEN not in request.url


def test_success_grants_absent_scopes_not_an_empty_tuple(tmp_path: Path) -> None:
    transport = FakeTransport([_ok()])
    session = _session(tmp_path, transport)
    granted = IntervalsConnector().verify(session, {"api_key": session.secret(_KEY)})
    assert granted.scopes is None


@pytest.mark.parametrize(
    ("status", "headers", "kind", "retry_after_s", "message"),
    [
        (401, {}, AuthFailureKind.REJECTED, None, "no key here"),
        (403, {}, AuthFailureKind.BLOCKED, None, "no key here"),
        (
            429,
            {"retry-after": "7"},
            AuthFailureKind.RATE_LIMITED,
            7.0,
            "no key here",
        ),
        (503, {}, AuthFailureKind.UNAVAILABLE, None, "no key here"),
        (404, {}, AuthFailureKind.UNAVAILABLE, None, "HTTP 404: no key here"),
    ],
)
def test_each_status_maps_to_one_failure_after_one_request(
    tmp_path: Path,
    status: int,
    headers: dict[str, str],
    kind: AuthFailureKind,
    retry_after_s: float | None,
    message: str,
) -> None:
    failure, transport = _failure(
        tmp_path, HttpResponse(status=status, headers=headers, body=b"no key here")
    )
    assert len(transport.requests) == 1
    assert failure.kind is kind
    assert failure.retry_after_s == retry_after_s
    assert failure.service_message == message


def test_a_404_with_an_empty_body_says_the_status_once(tmp_path: Path) -> None:
    failure, _ = _failure(tmp_path, HttpResponse(status=404, headers={}, body=b""))
    assert failure.kind is AuthFailureKind.UNAVAILABLE
    assert failure.service_message == "HTTP 404"


def test_a_403_body_echoing_the_bare_token_is_redacted_in_the_failure(
    tmp_path: Path,
) -> None:
    body = f"denied for {_TOKEN} today".encode()
    failure, _ = _failure(tmp_path, HttpResponse(status=403, headers={}, body=body))
    assert failure.kind is AuthFailureKind.BLOCKED
    assert str(failure) == f"denied for {REDACTED} today"
    assert _TOKEN not in str(failure)


def test_a_403_body_echoing_the_raw_key_is_redacted_before_the_framework_sees_it(
    tmp_path: Path,
) -> None:
    body = f"bad key {_KEY}".encode()
    failure, _ = _failure(tmp_path, HttpResponse(status=403, headers={}, body=body))
    assert failure.service_message == f"bad key {REDACTED}"
    assert _KEY not in failure.service_message
    assert _KEY not in str(failure)


def test_the_header_value_and_the_bare_token_are_both_registered_before_use(
    tmp_path: Path,
) -> None:
    redactor = Redactor()
    inner = FakeTransport([_ok()])
    at_request_time: list[tuple[str, str]] = []

    def recording(request: HttpRequest, timeout: float) -> HttpResponse:
        at_request_time.append((redactor.redact(_TOKEN), redactor.redact(_BASIC)))
        return inner(request, timeout)

    session = _session(tmp_path, recording, redactor=redactor)
    assert redactor.redact(f"{_TOKEN} {_BASIC}") == f"{_TOKEN} {_BASIC}"
    IntervalsConnector().verify(session, {"api_key": Secret(_KEY)})
    # The header value is also registered by HttpClient._register_secrets, so
    # the second element pins the outcome, not the connector's own call; only
    # the bare token depends on the connector registering it.
    assert at_request_time == [(REDACTED, REDACTED)]
    assert redactor.redact(f"[{_BASIC}]") == f"[{REDACTED}]"


def test_the_service_message_collapses_whitespace_and_is_cut_to_300_characters(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, FakeTransport([]))
    spaced = HttpResponse(status=400, headers={}, body=b" a \n\t b\r\n  c ")
    assert _service_message(session, spaced) == "a b c"
    long = HttpResponse(status=400, headers={}, body=b"x" * 301 + b" tail")
    assert _service_message(session, long) == "x" * 300
    exact = HttpResponse(status=400, headers={}, body=b"y" * 300)
    assert _service_message(session, exact) == "y" * 300


def test_the_redaction_runs_before_the_cut_so_no_key_prefix_survives(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([])
    session = _session(tmp_path, transport)
    session.secret(_KEY)
    straddling = HttpResponse(status=400, headers={}, body=b"x" * 295 + _KEY.encode())
    message = _service_message(session, straddling)
    assert message == "x" * 295 + REDACTED[:5]
    assert _KEY[:5] not in message


def test_a_character_split_by_the_byte_bound_is_dropped(tmp_path: Path) -> None:
    # "é" is two bytes, at 4095-4096: the bound keeps only its first byte.
    body = b" " * 4093 + b"z " + "é".encode()
    assert len(body) == 4097
    session = _session(tmp_path, FakeTransport([]))
    assert (
        _service_message(session, HttpResponse(status=400, headers={}, body=body))
        == "z"
    )
    failure, _ = _failure(tmp_path, HttpResponse(status=404, headers={}, body=body))
    assert failure.service_message == "HTTP 404: z"


def test_a_secret_echoed_across_the_4096_byte_bound_leaves_no_prefix(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, FakeTransport([]))
    session.secret(_KEY)
    session.secret(_TOKEN)
    for secret in (_KEY, _TOKEN):
        # 4080 spaces, then a filler word, then the secret: the secret starts
        # a few bytes before byte 4096 and ends after it.
        body = b" " * 4080 + b"ab " + secret.encode()
        message = _service_message(
            session, HttpResponse(status=400, headers={}, body=body)
        )
        assert message == "ab " + REDACTED
        for k in range(4, len(secret)):
            assert secret[:k] not in message


def test_an_empty_service_message_falls_back_to_the_status(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeTransport([]))
    blank = HttpResponse(status=418, headers={}, body=b" \n ")
    assert _service_message(session, blank) == "HTTP 418"
    assert _service_message(session, HttpResponse(418, {}, b"")) == "HTTP 418"


def test_the_service_message_reads_only_the_first_4096_bytes(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeTransport([]))
    far = HttpResponse(status=400, headers={}, body=b" " * 4096 + b"late words")
    assert _service_message(session, far) == "HTTP 400"
    # The last byte inside the bound is read; the first byte past it is not.
    inside = HttpResponse(status=400, headers={}, body=b" " * 4095 + b"z" + b" late")
    assert _service_message(session, inside) == "z"
    # The bound counts bytes, not characters: 1365 three-byte ideographic
    # spaces fill 4095 bytes, so "z" is byte 4096 and " late" lies past it,
    # although the whole body is far fewer than 4096 characters.
    wide = "\u3000".encode() * 1365 + b"z late"
    assert len(wide) - len(b" late") == 4096
    assert len(wide.decode()) < 4096
    multibyte = HttpResponse(status=400, headers={}, body=wide)
    assert _service_message(session, multibyte) == "z"


def test_a_non_utf8_body_decodes_with_replacement(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeTransport([]))
    body = HttpResponse(status=400, headers={}, body=b"bad \xff byte")
    assert _service_message(session, body) == "bad \ufffd byte"


def test_a_403_with_a_non_utf8_body_is_still_a_blocked_failure(
    tmp_path: Path,
) -> None:
    failure, _ = _failure(
        tmp_path, HttpResponse(status=403, headers={}, body=b"bad \xff byte")
    )
    assert failure.kind is AuthFailureKind.BLOCKED
    assert failure.service_message == "bad \ufffd byte"


def test_a_scripted_429_through_the_connect_engine_is_one_request_and_stores_nothing(
    tmp_path: Path,
) -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status=429, headers={"retry-after": "7"}, body=f"slow {_KEY}".encode()
            )
        ]
    )
    credentials_dir = tmp_path / "creds"
    instance = ConnectorInstance(
        name="intervals",
        connector=IntervalsConnector(),
        lookback_days=30,
        settings=IntervalsSettings(sources=DEFAULT_SOURCES),
    )
    result = run_connect(
        instance,
        {"api_key": _KEY},
        store=CredentialStore(credentials_dir),
        transport=transport,
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )
    assert isinstance(result, ConnectFailed)
    assert result.kind is AuthFailureKind.RATE_LIMITED
    assert result.message == f"slow {REDACTED}"
    assert "7 seconds" in result.next_step
    assert len(transport.requests) == 1
    assert not credentials_dir.exists()


# --------------------------------------------------------------------------
# Listing (task 3.3; Req 1.5, 3.1-3.8, 5.1-5.5, 5.7, 6.1)
# --------------------------------------------------------------------------

_LISTING_FIELDS = "id,source,start_date,type,elapsed_time,file_type"
_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/0/activities"


class _KeyCredentials(_StubCredentials):
    """A credential access that hands out the synthetic key."""

    def value(self, field: str) -> Secret:
        assert field == "api_key"
        return Secret(_KEY)


def _json_ok(payload: object) -> HttpResponse:
    return HttpResponse(status=200, headers={}, body=json.dumps(payload).encode())


def _list(
    tmp_path: Path,
    responses: list[HttpResponse],
    *,
    since: datetime | None,
    sources: frozenset[str] = DEFAULT_SOURCES,
    settings: IntervalsSettings | None = None,
) -> tuple[Listing, FakeTransport]:
    transport = FakeTransport(list(responses))
    session = _session(
        tmp_path,
        transport,
        mode=CallMode.DATA,
        settings=settings if settings is not None else IntervalsSettings(sources),
        credentials=_KeyCredentials(),
    )
    session.secret(_KEY)
    return IntervalsConnector().list_activities(session, since), transport


def _queries(transport: FakeTransport) -> list[dict[str, list[str]]]:
    return [
        parse_qs(urlsplit(request.url).query, keep_blank_values=True)
        for request in transport.requests
    ]


def test_a_since_200_days_back_is_three_overlapping_windows(tmp_path: Path) -> None:
    since = _CLOCK - timedelta(days=200)
    assert since == datetime(2025, 8, 13, 0, 30, tzinfo=UTC)
    # A fourth scripted answer, so a surplus request would be answered and
    # only the count could notice it.
    listing, transport = _list(
        tmp_path, [_json_ok([]), _json_ok([]), _json_ok([]), _json_ok([])], since=since
    )
    assert listing.activities == ()
    assert [query.get("oldest") for query in _queries(transport)] == [
        ["2025-08-12T00:00:00"],
        ["2025-11-10T00:00:00"],
        ["2026-02-08T00:00:00"],
    ]
    assert [query.get("newest") for query in _queries(transport)] == [
        ["2025-11-11T00:00:00"],
        ["2026-02-09T00:00:00"],
        None,
    ]


def test_a_since_179_days_back_is_exactly_two_windows(tmp_path: Path) -> None:
    since = _CLOCK - timedelta(days=179)
    assert since == datetime(2025, 9, 3, 0, 30, tzinfo=UTC)
    _, transport = _list(
        tmp_path, [_json_ok([]), _json_ok([]), _json_ok([])], since=since
    )
    assert [query.get("oldest") for query in _queries(transport)] == [
        ["2025-09-02T00:00:00"],
        ["2025-12-01T00:00:00"],
    ]
    assert [query.get("newest") for query in _queries(transport)] == [
        ["2025-12-02T00:00:00"],
        None,
    ]


def test_no_since_is_one_window_from_31_days_before_the_clock(tmp_path: Path) -> None:
    _, transport = _list(tmp_path, [_json_ok([]), _json_ok([])], since=None)
    assert _queries(transport) == [
        {"oldest": ["2026-01-29T00:00:00"], "fields": [_LISTING_FIELDS]}
    ]


def test_with_no_since_the_earliest_is_the_clock_less_30_days(tmp_path: Path) -> None:
    assert _CLOCK - timedelta(days=30) == datetime(2026, 1, 30, 0, 30, tzinfo=UTC)
    window = [
        _entry("i9000001", start_date="2026-01-30T00:29:59Z"),
        _entry("i9000002", start_date="2026-01-30T00:30:00Z"),
    ]
    listing, transport = _list(tmp_path, [_json_ok(window)], since=None)
    assert len(transport.requests) == 1
    assert [a.remote_id for a in listing.activities] == ["i9000002"]


def test_the_first_bound_is_the_utc_day_of_since_less_one(tmp_path: Path) -> None:
    # 05:00 on 2025-08-13 at UTC+10 is 19:00 on 2025-08-12 UTC: the local date
    # is the 13th, the UTC date the 12th, so the first bound is the 11th.
    since = datetime(2025, 8, 13, 5, 0, tzinfo=timezone(timedelta(hours=10)))
    assert since.astimezone(UTC) == datetime(2025, 8, 12, 19, 0, tzinfo=UTC)
    _, transport = _list(
        tmp_path, [_json_ok([]), _json_ok([]), _json_ok([])], since=since
    )
    assert _queries(transport)[0]["oldest"] == ["2025-08-11T00:00:00"]


def test_every_request_asks_for_the_six_fields_and_carries_no_credential(
    tmp_path: Path,
) -> None:
    since = _CLOCK - timedelta(days=200)
    _, transport = _list(
        tmp_path, [_json_ok([]), _json_ok([]), _json_ok([])], since=since
    )
    assert len(transport.requests) == 3
    for request in transport.requests:
        parts = urlsplit(request.url)
        assert request.method == "GET"
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == _ACTIVITIES_URL
        assert parse_qs(parts.query)["fields"] == [_LISTING_FIELDS]
        assert set(parse_qs(parts.query)) <= {"oldest", "newest", "fields"}
        assert _KEY not in request.url
        assert _TOKEN not in request.url
        assert list(request.secret_headers) == ["Authorization"]
        assert request.secret_headers["Authorization"].reveal() == _BASIC


def test_athlete_and_api_base_keys_change_no_request(tmp_path: Path) -> None:
    table: dict[str, object] = {
        "athlete": "i5",
        "api_base": "https://example.org",
        "sources": ["GARMIN_CONNECT"],
    }
    settings = _parse(tmp_path, table)
    since = _CLOCK - timedelta(days=200)
    _, transport = _list(
        tmp_path,
        [_json_ok([]), _json_ok([]), _json_ok([])],
        since=since,
        settings=settings,
    )
    assert len(transport.requests) == 3
    for request in transport.requests:
        assert request.url.startswith(f"{_ACTIVITIES_URL}?")
        assert "i5" not in request.url
        assert "example.org" not in request.url


_BASE_START = "2025-10-01T08:00:00Z"


def _entry(identifier: str, **changes: object) -> dict[str, object]:
    """One listing entry: the base entry with ``changes`` applied; a value of
    ``None`` removes the key."""
    entry: dict[str, object] = {
        "id": identifier,
        "source": "GARMIN_CONNECT",
        "start_date": _BASE_START,
        "type": "Ride",
        "elapsed_time": 3600,
        "file_type": "fit",
    }
    for key, value in changes.items():
        if value is None:
            del entry[key]
        else:
            entry[key] = value
    return entry


def _expected(identifier: str, **changes: object) -> RemoteActivity:
    fields: dict[str, object] = {
        "remote_id": identifier,
        "original_available": True,
        "unavailable_reason": None,
        "start": datetime(2025, 10, 1, 8, 0, tzinfo=UTC),
        "sport": "Ride",
        "duration_s": 3600.0,
        "revision": None,
        "suggested_name": None,
    }
    fields.update(changes)
    return RemoteActivity(**fields)  # type: ignore[arg-type]


_STRAVA_TEXT = (
    "Strava-sourced: intervals.icu returns only a stub for Strava activities "
    "and shares no file for them"
)

_EARLIEST = "2025-08-13T00:30:00Z"

_WINDOW_ONE = [
    _entry("i9000001"),
    _entry("i9000002", source="OAUTH_CLIENT"),
    _entry("i9000003", source=None),
    _entry("i9000004", start_date="2025-08-13T00:29:59Z"),
    _entry("i9000005", start_date=None),
    _entry("i9000006", start_date=_EARLIEST),
    _entry("i9000014", start_date="2025-08-13T10:00:00+10:00"),
]
_WINDOW_TWO = [
    _entry("i9000001", type="Run"),
    _entry("i9000007", source="STRAVA"),
    _entry("i9000008", file_type="gpx"),
    _entry("i9000009", file_type=" TCX "),
    _entry("i9000015", start_date="2025-10-02T18:00:00+10:00"),
    # Two-property entries: an early start together with a rule that would
    # list the entry unavailable; the omission comes first.
    _entry("i9000022", source="STRAVA", start_date="2025-08-13T00:29:59Z"),
    _entry("i9000023", file_type="gpx", start_date="2025-08-13T00:29:59Z"),
]
_WINDOW_THREE = [
    _entry("i9000010", file_type="FIT"),
    _entry("i9000011", file_type=None),
    _entry("i9000012", start_date="2025-11-02T08:00:00"),
    _entry("i9000013", elapsed_time=True),
    _entry("i9000016", elapsed_time=-1),
    _entry("i9000017", elapsed_time="3600"),
    _entry("i9000018", elapsed_time=0),
    _entry("i9000019", elapsed_time=None),
    _entry("i9000020", type=None),
    _entry("i9000021", type=""),
    _entry("i9000024", file_type=""),
    _entry("i9000025", file_type="  "),
]


def _fixture_listing(
    tmp_path: Path, sources: frozenset[str]
) -> tuple[Listing, FakeTransport]:
    raw = [_WINDOW_ONE, _WINDOW_TWO, _WINDOW_THREE]
    # Preconditions: every category the expected lists omit or keep is in the
    # raw listing, and the id the second window repeats is in the first.
    assert sum(len(window) for window in raw) == 26
    assert {e["id"] for e in _WINDOW_ONE} & {e["id"] for e in _WINDOW_TWO} == {
        "i9000001"
    }
    since = _CLOCK - timedelta(days=200)
    return _list(
        tmp_path, [_json_ok(window) for window in raw], since=since, sources=sources
    )


_GPX_TEXT = "the original is a GPX file, not FIT; fitdocs ingests FIT files only"
_TCX_TEXT = "the original is a TCX file, not FIT; fitdocs ingests FIT files only"

_KEPT_BEFORE_STRAVA = [
    _expected("i9000001"),
    _expected("i9000005", start=None),
    _expected("i9000006", start=datetime(2025, 8, 13, 0, 30, tzinfo=UTC)),
]
_KEPT_AFTER_STRAVA = [
    _expected("i9000008", original_available=False, unavailable_reason=_GPX_TEXT),
    _expected("i9000009", original_available=False, unavailable_reason=_TCX_TEXT),
    _expected("i9000015", start=datetime(2025, 10, 2, 8, 0, tzinfo=UTC)),
    _expected("i9000010"),
    _expected("i9000011"),
    _expected("i9000012", start=None),
    _expected("i9000013", duration_s=None),
    _expected("i9000016", duration_s=None),
    _expected("i9000017", duration_s=None),
    _expected("i9000018", duration_s=0.0),
    _expected("i9000019", duration_s=None),
    _expected("i9000020", sport=None),
    _expected("i9000021", sport=None),
    _expected("i9000024"),
    _expected("i9000025"),
]


def test_the_fixture_listing_under_the_default_filter(tmp_path: Path) -> None:
    listing, transport = _fixture_listing(tmp_path, DEFAULT_SOURCES)
    assert len(transport.requests) == 3
    assert listing.deferred == ()
    assert list(listing.activities) == _KEPT_BEFORE_STRAVA + _KEPT_AFTER_STRAVA


def test_a_filter_naming_strava_lists_the_stub_unavailable_with_the_reason(
    tmp_path: Path,
) -> None:
    listing, _ = _fixture_listing(tmp_path, frozenset({"GARMIN_CONNECT", "STRAVA"}))
    strava = _expected(
        "i9000007", original_available=False, unavailable_reason=_STRAVA_TEXT
    )
    assert list(listing.activities) == (
        _KEPT_BEFORE_STRAVA + [strava] + _KEPT_AFTER_STRAVA
    )


def test_a_start_with_an_offset_is_stored_in_utc(tmp_path: Path) -> None:
    listing, _ = _fixture_listing(tmp_path, DEFAULT_SOURCES)
    shifted = next(a for a in listing.activities if a.remote_id == "i9000015")
    assert shifted.start is not None
    assert shifted.start.utcoffset() == timedelta(0)
    assert shifted.start.hour == 8


def test_every_listed_activity_has_the_service_id_and_no_revision(
    tmp_path: Path,
) -> None:
    listing, _ = _fixture_listing(tmp_path, frozenset({"GARMIN_CONNECT", "STRAVA"}))
    assert len(listing.activities) == 19
    expected_ids = [
        "i9000001",
        "i9000005",
        "i9000006",
        "i9000007",
        "i9000008",
        "i9000009",
        "i9000015",
        "i9000010",
        "i9000011",
        "i9000012",
        "i9000013",
        "i9000016",
        "i9000017",
        "i9000018",
        "i9000019",
        "i9000020",
        "i9000021",
        "i9000024",
        "i9000025",
    ]
    assert [a.remote_id for a in listing.activities] == expected_ids
    assert all(a.revision is None for a in listing.activities)
    assert all(a.suggested_name is None for a in listing.activities)


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        (b"not json at all", "not valid JSON"),
        (b'{"id": "i9000001"}', "not a JSON array"),
        (
            json.dumps([_entry("i9000001"), _entry("i9000002", id=None)]).encode(),
            "entry 1 has no text id",
        ),
        (
            json.dumps([_entry("i9000001"), _entry("i9000002", id=9000002)]).encode(),
            "entry 1 has no text id",
        ),
        (json.dumps(["i9000001"]).encode(), "entry 0 is not an object"),
        (
            json.dumps([_entry("i9000001"), _entry("i9000002", id="")]).encode(),
            "entry 1 has no text id",
        ),
        (
            json.dumps(
                [_entry("i9000001"), _entry("x", id=None, source="OAUTH_CLIENT")]
            ).encode(),
            "entry 1 has no text id",
        ),
    ],
    ids=[
        "not-json",
        "object",
        "no-id",
        "numeric-id",
        "not-an-entry-object",
        "empty-id",
        "no-id-outside-the-filter",
    ],
)
def test_a_malformed_listing_ends_the_instance_naming_the_problem(
    tmp_path: Path, body: bytes, problem: str
) -> None:
    since = _CLOCK - timedelta(days=200)
    transport = FakeTransport([HttpResponse(200, {}, body), _json_ok([])])
    session = _session(
        tmp_path, transport, mode=CallMode.DATA, credentials=_KeyCredentials()
    )
    with pytest.raises(ConnectorError) as excinfo:
        IntervalsConnector().list_activities(session, since)
    assert str(excinfo.value).startswith(
        "intervals.icu's activity listing is not in its documented form: "
    )
    assert problem in str(excinfo.value)
    assert len(transport.requests) == 1


def _failing_listing(
    tmp_path: Path, responses: list[HttpResponse]
) -> tuple[BaseException, FakeTransport]:
    transport = FakeTransport(list(responses))
    session = _session(
        tmp_path, transport, mode=CallMode.DATA, credentials=_KeyCredentials()
    )
    with pytest.raises((AuthFailure, ConnectorError)) as excinfo:
        IntervalsConnector().list_activities(session, None)
    return excinfo.value, transport


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, AuthFailureKind.REJECTED), (403, AuthFailureKind.BLOCKED)],
)
def test_a_listing_401_or_403_is_an_authentication_failure(
    tmp_path: Path, status: int, kind: AuthFailureKind
) -> None:
    error, transport = _failing_listing(
        tmp_path,
        [HttpResponse(status, {}, b"  go   away "), HttpResponse(status, {}, b"")],
    )
    assert type(error) is AuthFailure
    assert isinstance(error, AuthFailure)
    assert error.kind is kind
    assert error.service_message == "go away"
    assert len(transport.requests) == 1


def test_a_persistent_429_is_a_rate_limit_connector_error_after_three_requests(
    tmp_path: Path,
) -> None:
    error, transport = _failing_listing(tmp_path, [HttpResponse(429, {}, b"slow")] * 4)
    assert type(error) is ConnectorError
    assert str(error) == (
        "intervals.icu is limiting requests (HTTP 429) and still was after "
        "fitdocs's retries; this pull stopped, and the next pull resumes where "
        "it stopped"
    )
    assert len(transport.requests) == 3


def test_a_persistent_503_is_an_unavailable_connector_error_after_three_requests(
    tmp_path: Path,
) -> None:
    error, transport = _failing_listing(tmp_path, [HttpResponse(503, {}, b"down")] * 4)
    assert type(error) is ConnectorError
    assert str(error) == (
        "intervals.icu is unavailable (HTTP 503) after fitdocs's retries; "
        "this pull stopped, and the next pull resumes where it stopped"
    )
    assert len(transport.requests) == 3


def test_a_listing_418_names_the_status_and_the_service_words(tmp_path: Path) -> None:
    error, transport = _failing_listing(
        tmp_path, [HttpResponse(418, {}, b"short and stout"), _json_ok([])]
    )
    assert type(error) is ConnectorError
    assert str(error) == (
        "intervals.icu answered the activity listing with HTTP 418: short and stout"
    )
    assert len(transport.requests) == 1


def test_a_listing_418_echoing_the_bare_token_is_redacted(tmp_path: Path) -> None:
    error, _ = _failing_listing(
        tmp_path, [HttpResponse(418, {}, f"seen {_TOKEN} here".encode())]
    )
    assert str(error) == (
        f"intervals.icu answered the activity listing with HTTP 418: "
        f"seen {REDACTED} here"
    )
    assert _TOKEN not in str(error)


# --------------------------------------------------------------------------
# Task 3.4: the file download
# --------------------------------------------------------------------------

_FILE_URL = "https://intervals.icu/api/v1/activity/i9000001/file"
_NO_FILE = "intervals.icu holds no original file for this activity"
_GPX = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<gpx version="1.1" creator="synthetic"><trk><name>x</name></trk></gpx>'
)
_TCX = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b"<TrainingCenterDatabase><Activities/></TrainingCenterDatabase>"
)


def _remote(remote_id: str = "i9000001") -> RemoteActivity:
    return RemoteActivity(
        remote_id=remote_id,
        original_available=True,
        unavailable_reason=None,
        start=None,
        sport=None,
        duration_s=None,
        revision=None,
        suggested_name=None,
    )


def _body(body: bytes, status: int = 200) -> HttpResponse:
    return HttpResponse(status=status, headers={}, body=body)


def _fetch(
    tmp_path: Path,
    responses: list[HttpResponse],
    remote_id: str = "i9000001",
) -> tuple[FetchResult, FakeTransport]:
    transport = FakeTransport(list(responses))
    session = _session(
        tmp_path, transport, mode=CallMode.DATA, credentials=_KeyCredentials()
    )
    session.secret(_KEY)
    return IntervalsConnector().fetch_activity(session, _remote(remote_id)), transport


def _fetch_failure(
    tmp_path: Path, responses: list[HttpResponse]
) -> tuple[BaseException, FakeTransport]:
    transport = FakeTransport(list(responses))
    session = _session(
        tmp_path, transport, mode=CallMode.DATA, credentials=_KeyCredentials()
    )
    with pytest.raises((AuthFailure, ConnectorError, IntervalsDownloadError)) as exc:
        IntervalsConnector().fetch_activity(session, _remote())
    return exc.value, transport


def test_a_gzip_body_is_fetched_as_the_decompressed_original(tmp_path: Path) -> None:
    original = builder.ride_fit_bytes()
    compressed = gzip.compress(original)
    assert compressed != original
    assert compressed.startswith(b"\x1f\x8b")
    result, transport = _fetch(tmp_path, [_body(compressed)])
    assert result == Fetched(original)
    assert len(transport.requests) == 1


def test_an_uncompressed_body_is_fetched_unchanged(tmp_path: Path) -> None:
    original = builder.ride_fit_bytes()
    assert original[8:12] == b".FIT"
    result, _ = _fetch(tmp_path, [_body(original)])
    assert result == Fetched(original)


def test_gzip_magic_after_the_first_two_bytes_does_not_make_a_body_gzip(
    tmp_path: Path,
) -> None:
    body = b"\x0e\x10" + b"\x1f\x8b" + b"not compressed at all"
    result, _ = _fetch(tmp_path, [_body(body)])
    assert result == Fetched(body)


@pytest.mark.parametrize(
    "body",
    [b"\x1f\x00" + b"not compressed", b"\x00\x8b" + b"not compressed"],
    ids=["first-byte-only", "second-byte-only"],
)
def test_a_body_with_only_one_of_the_two_gzip_magic_bytes_is_not_gzip(
    tmp_path: Path, body: bytes
) -> None:
    result, _ = _fetch(tmp_path, [_body(body)])
    assert result == Fetched(body)


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (204, b"", "HTTP 204"),
        (206, b"partial", "partial"),
    ],
)
def test_a_2xx_other_than_200_fails_the_download_naming_the_status(
    tmp_path: Path, status: int, body: bytes, message: str
) -> None:
    error, transport = _fetch_failure(tmp_path, [_body(body, status), _body(b"x")])
    assert type(error) is IntervalsDownloadError
    assert str(error) == (
        f"intervals.icu answered HTTP {status} for the original file: {message}"
    )
    assert len(transport.requests) == 1


def test_the_request_is_a_get_of_the_original_file_with_the_credential(
    tmp_path: Path,
) -> None:
    _, transport = _fetch(tmp_path, [_body(builder.ride_fit_bytes())])
    (request,) = transport.requests
    assert request.method == "GET"
    assert request.url == _FILE_URL
    assert request.body is None
    assert {
        name: secret.reveal() for name, secret in request.secret_headers.items()
    } == {"Authorization": _BASIC}
    assert _KEY not in request.url
    assert _TOKEN not in request.url


def test_an_id_with_a_slash_is_quoted_into_one_path_segment(tmp_path: Path) -> None:
    _, transport = _fetch(
        tmp_path, [_body(builder.ride_fit_bytes())], remote_id="i9/00 1?x"
    )
    (request,) = transport.requests
    assert request.url == ("https://intervals.icu/api/v1/activity/i9%2F00%201%3Fx/file")


@pytest.mark.parametrize(
    ("document", "name"), [(_GPX, "GPX"), (_TCX, "TCX")], ids=["gpx", "tcx"]
)
@pytest.mark.parametrize("compressed", [True, False], ids=["gzip", "plain"])
def test_a_gpx_or_tcx_original_is_declined_naming_the_format(
    tmp_path: Path, document: bytes, name: str, compressed: bool
) -> None:
    body = gzip.compress(document) if compressed else document
    result, _ = _fetch(tmp_path, [_body(body)])
    assert result == Declined(
        f"the original is a {name} file, not FIT; fitdocs ingests FIT files only"
    )


@pytest.mark.parametrize(
    ("document", "name"),
    [
        (b"\xef\xbb\xbf" + _GPX, "GPX"),
        (b" \r\n\t " + _GPX, "GPX"),
        (b"\xef\xbb\xbf \n" + _TCX, "TCX"),
        (_GPX.upper(), "GPX"),
        (_TCX.replace(b"TrainingCenterDatabase", b"TRAININGCENTERDATABASE"), "TCX"),
        (b"<gpx>" + b" " * 1100, "GPX"),
        (b"<?xml?>" + b" " * 1000 + b"<gpx>", "GPX"),
        (b"<?xml?>" + b" " * 1030 + b"<gpx>", None),
        (b"<?xml?>" + b" " * 1016 + b"<gpx>", None),
        (b"\x0e\x10\x00\x00<gpx version", None),
        (b"\x0e\x10\x00\x00<TrainingCenterDatabase", None),
        (b"<kml><doc/></kml> but <gpx", "GPX"),
        (b"<html>a page</html>", None),
        (b"", None),
    ],
    ids=[
        "bom",
        "leading-whitespace",
        "bom-then-whitespace-tcx",
        "upper-case-gpx",
        "upper-case-tcx",
        "root-first-long-file",
        "root-inside-window",
        "root-past-window",
        "root-straddling-window",
        "fit-header-then-gpx-text",
        "fit-header-then-tcx-text",
        "root-not-first-element",
        "html-is-not-recognised",
        "empty",
    ],
)
def test_document_recognition_looks_at_the_first_1024_bytes_of_a_document(
    tmp_path: Path, document: bytes, name: str | None
) -> None:
    result, _ = _fetch(tmp_path, [_body(document)])
    if name is None:
        assert result == Fetched(document)
    else:
        assert isinstance(result, Declined)
        assert result.reason.startswith(f"the original is a {name} file")


def test_the_window_is_counted_before_the_bom_and_whitespace_are_removed(
    tmp_path: Path,
) -> None:
    inside = b"\xef\xbb\xbf" + b" " * 3 + b"<gpx" + b" " * 2000
    pad = 1024 - 3 - 4
    assert len(b"\xef\xbb\xbf" + b" " * pad + b"<gpx") == 1024
    exactly_in = b"\xef\xbb\xbf" + b" " * pad + b"<gpx" + b" " * 50
    one_past = b"\xef\xbb\xbf" + b" " * (pad + 1) + b"<gpx" + b" " * 50
    in_result, _ = _fetch(tmp_path, [_body(inside)])
    edge_result, _ = _fetch(tmp_path, [_body(exactly_in)])
    past_result, _ = _fetch(tmp_path, [_body(one_past)])
    assert isinstance(in_result, Declined)
    assert isinstance(edge_result, Declined)
    assert past_result == Fetched(one_past)


@pytest.mark.parametrize("status", [404, 422])
def test_a_missing_original_is_declined_without_naming_a_status(
    tmp_path: Path, status: int
) -> None:
    body = b'{"status":422,"error":"Activity has no original file to download"}'
    result, transport = _fetch(tmp_path, [_body(body, status), _body(b"x")])
    assert result == Declined(_NO_FILE)
    assert len(transport.requests) == 1


def test_a_410_is_a_failed_download_not_a_declination(tmp_path: Path) -> None:
    error, transport = _fetch_failure(tmp_path, [_body(b"gone", 410)])
    assert type(error) is IntervalsDownloadError
    assert str(error) == "intervals.icu answered HTTP 410 for the original file: gone"
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "tail",
    [
        pytest.param(-10, id="trailer-cut"),
        pytest.param(-100, id="mid-stream-cut"),
    ],
)
def test_a_truncated_gzip_fails_the_download(tmp_path: Path, tail: int) -> None:
    compressed = gzip.compress(builder.ride_fit_bytes())
    assert len(compressed) > 200
    error, transport = _fetch_failure(tmp_path, [_body(compressed[:tail])])
    assert type(error) is IntervalsDownloadError
    assert str(error) == (
        "the downloaded file is gzip data that could not be decompressed"
    )
    assert len(transport.requests) == 1


def test_a_corrupt_deflate_stream_fails_the_download(tmp_path: Path) -> None:
    compressed = gzip.compress(builder.ride_fit_bytes())
    corrupt = compressed[:10] + b"\xff" * 40 + compressed[50:]
    assert len(corrupt) == len(compressed)
    with pytest.raises(zlib.error):
        gzip.decompress(corrupt)
    error, _ = _fetch_failure(tmp_path, [_body(corrupt)])
    assert type(error) is IntervalsDownloadError
    assert str(error) == (
        "the downloaded file is gzip data that could not be decompressed"
    )


def test_decompression_reads_at_most_one_byte_past_the_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intervals_module, "MAX_FILE_BYTES", 64)
    sizes: list[int] = []
    real_read = gzip.GzipFile.read

    def spy(self: gzip.GzipFile, size: int = -1) -> bytes:
        sizes.append(size)
        return real_read(self, size)

    monkeypatch.setattr(gzip.GzipFile, "read", spy)
    error, _ = _fetch_failure(tmp_path, [_body(gzip.compress(b"\x00" * 100_000))])
    assert type(error) is IntervalsDownloadError
    assert sizes == [65]


def test_gzip_magic_followed_by_garbage_fails_the_download(tmp_path: Path) -> None:
    error, _ = _fetch_failure(tmp_path, [_body(b"\x1f\x8bthis is not a stream")])
    assert type(error) is IntervalsDownloadError


def test_a_gzip_expanding_past_the_bound_fails_and_one_at_it_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intervals_module, "MAX_FILE_BYTES", 64)
    at_bound = b"\x00" * 64
    past_bound = b"\x00" * 65
    ok, _ = _fetch(tmp_path, [_body(gzip.compress(at_bound))])
    assert ok == Fetched(at_bound)
    assert len(gzip.compress(past_bound)) < 64
    error, transport = _fetch_failure(tmp_path, [_body(gzip.compress(past_bound))])
    assert type(error) is IntervalsDownloadError
    assert str(error) == (
        "the downloaded file expands past the 64-byte size limit when decompressed"
    )
    assert len(transport.requests) == 1


def test_the_bound_applies_to_the_decompressed_size_not_the_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intervals_module, "MAX_FILE_BYTES", 200)
    original = bytes(range(190))
    compressed = gzip.compress(original)
    assert len(compressed) > 200 >= len(original)
    result, _ = _fetch(tmp_path, [_body(compressed)])
    assert result == Fetched(original)


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, AuthFailureKind.REJECTED), (403, AuthFailureKind.BLOCKED)],
)
def test_a_download_401_or_403_is_an_authentication_failure(
    tmp_path: Path, status: int, kind: AuthFailureKind
) -> None:
    error, transport = _fetch_failure(
        tmp_path, [_body(b"  go   away ", status), _body(b"")]
    )
    assert type(error) is AuthFailure
    assert isinstance(error, AuthFailure)
    assert error.kind is kind
    assert error.service_message == "go away"
    assert len(transport.requests) == 1


def test_a_persistent_download_429_is_a_rate_limit_error_after_three_requests(
    tmp_path: Path,
) -> None:
    error, transport = _fetch_failure(tmp_path, [_body(b"slow", 429)] * 4)
    assert type(error) is ConnectorError
    assert str(error) == (
        "intervals.icu is limiting requests (HTTP 429) and still was after "
        "fitdocs's retries; this pull stopped, and the next pull resumes where "
        "it stopped"
    )
    assert len(transport.requests) == 3


def test_a_persistent_download_503_is_an_unavailable_error_after_three_requests(
    tmp_path: Path,
) -> None:
    error, transport = _fetch_failure(tmp_path, [_body(b"down", 503)] * 4)
    assert type(error) is ConnectorError
    assert str(error) == (
        "intervals.icu is unavailable (HTTP 503) after fitdocs's retries; "
        "this pull stopped, and the next pull resumes where it stopped"
    )
    assert len(transport.requests) == 3


def test_a_download_418_fails_the_one_activity_naming_the_status(
    tmp_path: Path,
) -> None:
    error, transport = _fetch_failure(
        tmp_path, [_body(b"short and stout", 418), _body(b"next")]
    )
    assert type(error) is IntervalsDownloadError
    assert str(error) == (
        "intervals.icu answered HTTP 418 for the original file: short and stout"
    )
    assert len(transport.requests) == 1


def test_a_download_418_echoing_the_bare_token_is_redacted(tmp_path: Path) -> None:
    error, _ = _fetch_failure(tmp_path, [_body(f"seen {_TOKEN} here".encode(), 418)])
    assert type(error) is IntervalsDownloadError
    assert str(error) == (
        f"intervals.icu answered HTTP 418 for the original file: seen {REDACTED} here"
    )
    assert _TOKEN not in str(error)
