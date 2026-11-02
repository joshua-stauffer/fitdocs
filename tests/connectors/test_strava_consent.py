"""The Strava connector's settings and consent operations
(strava-publish task 5.4; Requirements 1.1-1.4, 2.4).

Every request goes through a scripted ``FakeTransport``; nothing reaches a
network.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import fitdocs.connectors.strava as strava_module
from fitdocs.connectors.errors import ConnectorError, ConnectorSettingsError
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpResponse,
    Transport,
    TransportError,
)
from fitdocs.connectors.protocol import (
    Capability,
    ConnectorSession,
    ConsentPolled,
    ConsentStarted,
    CredentialField,
    RelayBound,
    RelayRefused,
    SettingsContext,
    TokenSet,
)
from fitdocs.connectors.relay import RelaySettings
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode
from fitdocs.connectors.relay_envelope import Answer, encode_answer
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.strava import StravaConnector, StravaSettings
from tests.connectors.conftest import FakeTransport

_CLOCK = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_BASE = "https://relay.example.com"
_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52
_CONNECTION_TOKEN = "fdr1_" + "c" * 16 + "_" + "d" * 52
_POLL_SECRET = "p" * 40
_USER_CODE = "BCDF-GHJK"
_STRAVA_ROUTE = "/v1/targets/strava/"


def _context(tmp_path: Path) -> SettingsContext:
    return SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")


def _parse(tmp_path: Path, table: dict[str, object]) -> StravaSettings:
    return StravaConnector().parse_settings(table, _context(tmp_path))


class _StubCredentials:
    def value(self, field: str) -> Secret:
        raise AssertionError("a consent operation takes its token as an argument")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("a consent operation stores nothing")


def _session(
    tmp_path: Path,
    transport: Transport,
    *,
    url: str = _BASE,
    redactor: Redactor | None = None,
    bound: bool = True,
) -> ConnectorSession:
    redactor = redactor if redactor is not None else Redactor()
    settings = StravaSettings(
        relay_instance="home",
        upload=False,
        relay=RelaySettings(url=url) if bound else None,
    )
    return ConnectorSession(
        instance="strava",
        settings=settings,
        http=HttpClient(
            transport,
            mode=CallMode.AUTH,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=_StubCredentials(),
        data_root=tmp_path,
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
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


def _started_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "user_code": _USER_CODE,
        "poll_secret": _POLL_SECRET,
        "interval_s": 7,
        "expires_in_s": 600,
    }
    data.update(overrides)
    return data


def _started(session: ConnectorSession) -> ConsentStarted:
    return ConsentStarted(
        user_code=_USER_CODE,
        page_url=_BASE + "/connect/strava?code=" + _USER_CODE,
        poll_secret=session.secret(_POLL_SECRET),
        interval_s=7,
        expires_at=_CLOCK + timedelta(seconds=600),
    )


# --------------------------------------------------------------------------
# Settings (Req 1.1, 1.2, 1.3)
# --------------------------------------------------------------------------


def test_the_declaration_is_a_browser_consent_connector() -> None:
    connector = StravaConnector()
    assert connector.connector_id == "strava"
    assert connector.display_name == "Strava"
    assert connector.auth_style.value == "oauth-browser"
    assert connector.link_label == "View on Strava"
    assert connector.credential_fields == (
        CredentialField("token", "Connection token", True),
    )
    assert connector.credential_fields[0].secret is True
    assert connector.capabilities == frozenset(
        {
            Capability.RESOLVE_REMOTE_ACTIVITY,
            Capability.ANNOTATE_REMOTE_ACTIVITY,
            Capability.PUSH_ACTIVITY,
        }
    )


def test_relay_alone_gives_upload_false_and_no_bound_relay(tmp_path: Path) -> None:
    assert _parse(tmp_path, {"relay": "home"}) == StravaSettings(
        relay_instance="home", upload=False, relay=None
    )


def test_upload_true_is_kept(tmp_path: Path) -> None:
    assert _parse(tmp_path, {"relay": "home", "upload": True}).upload is True


def test_other_keys_are_ignored(tmp_path: Path) -> None:
    table: dict[str, object] = {"relay": "home", "url": 3, "colour": ["x"]}
    assert _parse(tmp_path, table) == _parse(tmp_path, {"relay": "home"})


@pytest.mark.parametrize("given", [None, 3, True, ["home"], ""])
def test_a_relay_that_is_not_a_non_empty_string_is_refused(
    tmp_path: Path, given: object
) -> None:
    with pytest.raises(ConnectorSettingsError) as caught:
        _parse(tmp_path, {"relay": given})
    assert caught.value.key == "relay"


def test_a_missing_relay_is_refused_naming_relay(tmp_path: Path) -> None:
    with pytest.raises(ConnectorSettingsError) as caught:
        _parse(tmp_path, {"upload": True})
    assert caught.value.key == "relay"


@pytest.mark.parametrize("given", [1, 0, "true", "", None, ["x"]])
def test_an_upload_that_is_not_a_boolean_is_refused(
    tmp_path: Path, given: object
) -> None:
    with pytest.raises(ConnectorSettingsError) as caught:
        _parse(tmp_path, {"relay": "home", "upload": given})
    assert caught.value.key == "upload"


def test_a_bad_relay_is_named_before_a_bad_upload(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConnectorSettingsError) as caught:
        _parse(tmp_path, {"relay": 5, "upload": 5})
    assert caught.value.key == "relay"


def test_the_settings_implement_the_relay_bound_protocol(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"relay": "home"})
    assert isinstance(settings, RelayBound)
    assert settings.relay_instance == "home"


def test_bound_accepts_relay_settings_and_keeps_the_rest(tmp_path: Path) -> None:
    unbound = _parse(tmp_path, {"relay": "home", "upload": True})
    relay = RelaySettings(url=_BASE)
    bound = unbound.bound(relay)
    assert bound == dataclasses.replace(unbound, relay=relay)
    assert bound.relay is relay
    assert unbound.relay is None


@pytest.mark.parametrize(
    "other", [None, {"url": _BASE}, _BASE, StravaSettings("home", False)]
)
def test_bound_refuses_anything_but_relay_settings(
    tmp_path: Path, other: object
) -> None:
    unbound = _parse(tmp_path, {"relay": "home"})
    with pytest.raises(ConnectorSettingsError) as caught:
        unbound.bound(other)
    assert caught.value.key == "relay"
    assert _BASE not in caught.value.message


# --------------------------------------------------------------------------
# start_consent (Req 2.4)
# --------------------------------------------------------------------------


def test_start_consent_posts_empty_fields_to_the_connect_route_with_the_token(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([_envelope(RelayCode.CONNECT_STARTED, _started_data())])
    session = _session(tmp_path, transport)
    StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == _BASE + _STRAVA_ROUTE + "connect"
    assert json.loads(request.body or b"") == {}
    assert request.single_attempt is True
    assert {k: v.reveal() for k, v in request.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }


def test_a_started_answer_is_parsed_and_the_page_address_composed(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([_envelope(RelayCode.CONNECT_STARTED, _started_data())])
    session = _session(tmp_path, transport, url=_BASE + "/api")
    result = StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert isinstance(result, ConsentStarted)
    assert result.user_code == _USER_CODE
    assert result.page_url == _BASE + "/api/connect/strava?code=BCDF-GHJK"
    assert result.poll_secret.reveal() == _POLL_SECRET
    assert result.interval_s == 7
    assert result.expires_at == _CLOCK + timedelta(seconds=600)


def test_started_data_naming_an_address_is_malformed(
    tmp_path: Path,
) -> None:
    data = _started_data(page_url="https://evil.example/x", url="https://evil.example")
    transport = FakeTransport([_envelope(RelayCode.CONNECT_STARTED, data)])
    session = _session(tmp_path, transport)
    result = StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert result == RelayRefused(RelayCode.ANSWER_MALFORMED)


@pytest.mark.parametrize(
    "code",
    ["BCDF-GHJA", "ECDF-GHJK", "BCDF-GHJU", "BCDF-GHJO", "BCDF-GHJI", "BCDF-GHJy"],
)
def test_a_user_code_with_a_vowel_is_malformed(tmp_path: Path, code: str) -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.CONNECT_STARTED, _started_data(user_code=code))]
    )
    session = _session(tmp_path, transport)
    result = StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert result == RelayRefused(RelayCode.ANSWER_MALFORMED)


@pytest.mark.parametrize(
    "overrides",
    [
        {"user_code": "bcdf-ghjk"},
        {"user_code": "BCDFGHJK"},
        {"user_code": 12},
        {"poll_secret": "short"},
        {"interval_s": 0},
        {"interval_s": 61},
        {"expires_in_s": 59},
        {"expires_in_s": 3601},
    ],
)
def test_other_out_of_format_started_fields_are_malformed(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.CONNECT_STARTED, _started_data(**overrides))]
    )
    session = _session(tmp_path, transport)
    assert StravaConnector().start_consent(
        session, session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.ANSWER_MALFORMED)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (RelayCode.TOKEN_UNKNOWN, RelayCode.TOKEN_UNKNOWN),
        (RelayCode.NOT_OFFERED, RelayCode.NOT_OFFERED),
        (RelayCode.CONNECT_REFUSED, RelayCode.CONNECT_REFUSED),
        (RelayCode.UNAVAILABLE, RelayCode.UNAVAILABLE),
        (RelayCode.OK, RelayCode.ANSWER_MALFORMED),
        (RelayCode.CONNECT_PENDING, RelayCode.ANSWER_MALFORMED),
        (RelayCode.CONNECT_GRANTED, RelayCode.ANSWER_MALFORMED),
        (RelayCode.REGISTRATION_STARTED, RelayCode.ANSWER_MALFORMED),
    ],
)
def test_start_consent_refusals_by_code(
    tmp_path: Path, code: RelayCode, expected: RelayCode
) -> None:
    transport = FakeTransport([_envelope(code, {})])
    session = _session(tmp_path, transport)
    result = StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert result == RelayRefused(expected)


# Every code a relay answers with on some route's success, written out here:
# arriving on the start route (other than its own connect-started) each is
# another route's answer, so it reads as malformed rather than as a refusal.
_OTHER_ROUTES_SUCCESS_CODES = frozenset(
    {
        RelayCode.OK,
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
        RelayCode.CONNECT_PENDING,
        RelayCode.CONNECT_GRANTED,
    }
)


@pytest.mark.parametrize(
    "code",
    [
        c
        for c in RelayCode
        if c
        not in (
            RelayCode.CONNECT_STARTED,
            RelayCode.RATE_LIMITED,
            # client-origin codes: no relay sends them
            RelayCode.RELAY_UNREACHABLE,
            RelayCode.ANSWER_MALFORMED,
        )
    ],
    ids=lambda c: c.value,
)
def test_start_consent_reads_every_other_code_by_its_kind(
    tmp_path: Path, code: RelayCode
) -> None:
    transport = FakeTransport([_envelope(code, {})])
    session = _session(tmp_path, transport)
    result = StravaConnector().start_consent(session, session.secret(_TOKEN))
    expected = (
        RelayCode.ANSWER_MALFORMED if code in _OTHER_ROUTES_SUCCESS_CODES else code
    )
    assert result == RelayRefused(expected)


def test_a_rate_limited_start_carries_the_stated_wait(tmp_path: Path) -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 42})]
    )
    session = _session(tmp_path, transport)
    result = StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert result == RelayRefused(RelayCode.RATE_LIMITED, 42)


def test_an_unreachable_relay_and_a_non_envelope_body(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeTransport([TransportError("down")]))
    assert StravaConnector().start_consent(
        session, session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.RELAY_UNREACHABLE)
    session = _session(
        tmp_path, FakeTransport([HttpResponse(200, {}, b"<html>not json</html>")])
    )
    assert StravaConnector().start_consent(
        session, session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.ANSWER_MALFORMED)


@pytest.mark.parametrize(
    "body",
    [
        b"[" * 100_000 + b"]" * 100_000,
        b'{"envelope":1,"code":"connect-started","data":{"interval_s":'
        + b"9" * 5000
        + b"}}",
        b"\xff\xfe\x00 not utf-8",
    ],
    ids=["deep-nesting", "huge-int", "non-utf8"],
)
def test_a_hostile_200_body_is_malformed_not_a_crash(
    tmp_path: Path, body: bytes
) -> None:
    session = _session(tmp_path, FakeTransport([HttpResponse(200, {}, body)]))
    assert StravaConnector().start_consent(
        session, session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.ANSWER_MALFORMED)


def test_start_consent_on_unbound_settings_is_an_authoring_error(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([])
    session = _session(tmp_path, transport, bound=False)
    with pytest.raises(ConnectorError):
        StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert transport.requests == []


def test_start_consent_refuses_other_settings_before_any_request(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([])
    session = dataclasses.replace(
        _session(tmp_path, transport), settings=RelaySettings(url=_BASE)
    )
    with pytest.raises(ConnectorError):
        StravaConnector().start_consent(session, session.secret(_TOKEN))
    assert transport.requests == []


# --------------------------------------------------------------------------
# poll_consent (Req 2.4)
# --------------------------------------------------------------------------


def test_poll_consent_posts_the_poll_secret_to_the_poll_route(tmp_path: Path) -> None:
    transport = FakeTransport([_envelope(RelayCode.CONNECT_PENDING)])
    session = _session(tmp_path, transport)
    StravaConnector().poll_consent(session, _started(session), session.secret(_TOKEN))
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == _BASE + _STRAVA_ROUTE + "connect/poll"
    assert json.loads(request.body or b"") == {"poll_secret": _POLL_SECRET}
    assert request.single_attempt is True
    assert request.secret_headers["Authorization"].reveal() == "Bearer " + _TOKEN


def test_a_pending_answer_is_parsed(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeTransport([_envelope(RelayCode.CONNECT_PENDING)]))
    result = StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    )
    assert result == ConsentPolled(code=RelayCode.CONNECT_PENDING, token=None)


def test_a_pending_answer_with_data_is_malformed(tmp_path: Path) -> None:
    session = _session(
        tmp_path,
        FakeTransport([_envelope(RelayCode.CONNECT_PENDING, {"note": "hi"})]),
    )
    assert StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.ANSWER_MALFORMED)


def test_a_granted_answer_gives_the_connection_token(tmp_path: Path) -> None:
    session = _session(
        tmp_path,
        FakeTransport(
            [_envelope(RelayCode.CONNECT_GRANTED, {"token": _CONNECTION_TOKEN})]
        ),
    )
    result = StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    )
    assert isinstance(result, ConsentPolled)
    assert result.code is RelayCode.CONNECT_GRANTED
    assert result.token is not None
    assert result.token.reveal() == _CONNECTION_TOKEN


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"token": "not-a-token"},
        {"token": _CONNECTION_TOKEN.upper()},
        {"token": 5},
        {"token": _CONNECTION_TOKEN, "extra": 1},
    ],
)
def test_a_granted_answer_without_a_valid_token_is_malformed(
    tmp_path: Path, data: dict[str, object]
) -> None:
    session = _session(
        tmp_path, FakeTransport([_envelope(RelayCode.CONNECT_GRANTED, data)])
    )
    assert StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.ANSWER_MALFORMED)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (RelayCode.CONNECT_REFUSED, RelayCode.CONNECT_REFUSED),
        (RelayCode.CONNECT_EXPIRED, RelayCode.CONNECT_EXPIRED),
        (RelayCode.TOKEN_REVOKED, RelayCode.TOKEN_REVOKED),
        (RelayCode.STORAGE_UNREACHABLE, RelayCode.STORAGE_UNREACHABLE),
        (RelayCode.OK, RelayCode.ANSWER_MALFORMED),
        (RelayCode.CONNECT_STARTED, RelayCode.ANSWER_MALFORMED),
        (RelayCode.REGISTRATION_PENDING, RelayCode.ANSWER_MALFORMED),
    ],
)
def test_poll_refusals_by_code(
    tmp_path: Path, code: RelayCode, expected: RelayCode
) -> None:
    session = _session(tmp_path, FakeTransport([_envelope(code, {})]))
    result = StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    )
    assert result == RelayRefused(expected)


def test_a_poll_is_not_repeated_after_a_failure(tmp_path: Path) -> None:
    transport = FakeTransport([HttpResponse(503, {}, b"<html>")] * 3)
    session = _session(tmp_path, transport)
    result = StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    )
    assert result == RelayRefused(RelayCode.UNAVAILABLE)
    assert len(transport.requests) == 1


def test_poll_hostile_granted_body_is_malformed(tmp_path: Path) -> None:
    session = _session(
        tmp_path,
        FakeTransport([HttpResponse(200, {}, b"[" * 100_000 + b"]" * 100_000)]),
    )
    assert StravaConnector().poll_consent(
        session, _started(session), session.secret(_TOKEN)
    ) == RelayRefused(RelayCode.ANSWER_MALFORMED)


# --------------------------------------------------------------------------
# withdraw_consent (Req 2.4 operations)
# --------------------------------------------------------------------------


def test_withdraw_posts_empty_fields_to_the_disconnect_route(tmp_path: Path) -> None:
    transport = FakeTransport([_envelope(RelayCode.OK)])
    session = _session(tmp_path, transport)
    result = StravaConnector().withdraw_consent(
        session, session.secret(_CONNECTION_TOKEN)
    )
    assert result is None
    request = transport.requests[0]
    assert len(transport.requests) == 1
    assert request.url == _BASE + _STRAVA_ROUTE + "disconnect"
    assert json.loads(request.body or b"") == {}
    assert request.single_attempt is True
    assert (
        request.secret_headers["Authorization"].reveal()
        == "Bearer " + _CONNECTION_TOKEN
    )


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_envelope(RelayCode.OK, {"x": 1}), RelayRefused(RelayCode.ANSWER_MALFORMED)),
        (_envelope(RelayCode.TOKEN_REVOKED), RelayRefused(RelayCode.TOKEN_REVOKED)),
        (_envelope(RelayCode.NOT_OFFERED), RelayRefused(RelayCode.NOT_OFFERED)),
        (
            _envelope(RelayCode.CONNECT_GRANTED, {"token": _CONNECTION_TOKEN}),
            RelayRefused(RelayCode.ANSWER_MALFORMED),
        ),
        (
            _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 9}),
            RelayRefused(RelayCode.RATE_LIMITED, 9),
        ),
    ],
)
def test_withdraw_refusals(
    tmp_path: Path, response: HttpResponse, expected: RelayRefused
) -> None:
    session = _session(tmp_path, FakeTransport([response]))
    assert (
        StravaConnector().withdraw_consent(session, session.secret(_CONNECTION_TOKEN))
        == expected
    )


def test_withdraw_when_unreachable(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeTransport([TransportError("down")]))
    assert StravaConnector().withdraw_consent(
        session, session.secret(_CONNECTION_TOKEN)
    ) == RelayRefused(RelayCode.RELAY_UNREACHABLE)


# --------------------------------------------------------------------------
# Secrets reach the redactor
# --------------------------------------------------------------------------


def test_the_relay_token_is_registered_even_when_passed_as_a_bare_secret(
    tmp_path: Path,
) -> None:
    redactor = Redactor()
    session = _session(
        tmp_path, FakeTransport([_envelope(RelayCode.TOKEN_UNKNOWN)]), redactor=redactor
    )
    # a Secret built directly is not registered by construction
    StravaConnector().start_consent(session, Secret(_TOKEN))
    assert redactor.redact("see " + _TOKEN) == "see " + REDACTED


def test_the_poll_secret_and_connection_token_are_registered(tmp_path: Path) -> None:
    redactor = Redactor()
    session = _session(
        tmp_path,
        FakeTransport([_envelope(RelayCode.CONNECT_STARTED, _started_data())]),
        redactor=redactor,
    )
    assert redactor.redact(_POLL_SECRET) == _POLL_SECRET
    StravaConnector().start_consent(session, Secret(_TOKEN))
    assert redactor.redact(_POLL_SECRET) == REDACTED

    redactor = Redactor()
    session = _session(
        tmp_path,
        FakeTransport(
            [_envelope(RelayCode.CONNECT_GRANTED, {"token": _CONNECTION_TOKEN})]
        ),
        redactor=redactor,
    )
    unregistered = ConsentStarted(
        user_code=_USER_CODE,
        page_url="x",
        poll_secret=Secret(_POLL_SECRET),
        interval_s=7,
        expires_at=_CLOCK,
    )
    StravaConnector().poll_consent(session, unregistered, Secret(_TOKEN))
    assert redactor.redact(_CONNECTION_TOKEN) == REDACTED
    assert redactor.redact(_POLL_SECRET) == REDACTED


def test_withdraw_registers_the_token(tmp_path: Path) -> None:
    redactor = Redactor()
    session = _session(
        tmp_path, FakeTransport([_envelope(RelayCode.OK)]), redactor=redactor
    )
    StravaConnector().withdraw_consent(session, Secret(_CONNECTION_TOKEN))
    assert redactor.redact(_CONNECTION_TOKEN) == REDACTED


# --------------------------------------------------------------------------
# The source names no Strava host (Req 1.4)
# --------------------------------------------------------------------------


def test_the_source_names_no_strava_host() -> None:
    source = Path(strava_module.__file__).read_text(encoding="utf-8")
    assert "STRAVA" in source  # the walk reads the real, non-empty file
    assert not re.search(r"https?://", source)
    assert not re.search(r"strava\.com|strava\.cloud|strava\.net", source, re.I)
    assert not re.search(r"\b(?:www|api|oauth)\.", source)
