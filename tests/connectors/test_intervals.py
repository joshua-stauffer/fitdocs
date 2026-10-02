"""The intervals.icu connector's declaration, registration, settings and key
check (intervals-connector tasks 3.1 and 3.2).

Task 3.1 (Req 1.1, 1.5, 2.1-2.4, 5.6, 10.2, 10.4) covers what needs no
request: the declaration, the registry entry, the ``sources`` settings
parser, and the connector's own address admitted by the service-neutral scan.
Task 3.2 (Req 1.2, 1.3, 1.4, 5.7) covers ``verify``: the one listing request,
the Basic credential and its registration for redaction, the status mapping,
and the service-message helper. ``list_activities`` and ``fetch_activity``
are not exercised here yet.
"""

from __future__ import annotations

import subprocess
import sys
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
from fitdocs.connectors.connect import ConnectFailed, run_connect
from fitdocs.connectors.credentials import CredentialStore
from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
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
    IntervalsSettings,
    _service_message,
)
from fitdocs.connectors.protocol import ConnectorSession, TokenSet
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import (
    ConnectorInstance,
    ConnectorsSettingsError,
    load_connectors_settings,
)
from tests.connectors.conftest import FakeTransport


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
) -> ConnectorSession:
    redactor = redactor if redactor is not None else Redactor()
    return ConnectorSession(
        instance="intervals",
        settings=IntervalsSettings(sources=DEFAULT_SOURCES),
        http=HttpClient(
            transport,
            mode=CallMode.AUTH,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=_StubCredentials(),
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
