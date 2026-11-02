"""The relay's recorded exchanges decoded through the fitdocs client
(relay-server task 6.8; Requirements 4.4, 15.3).

``relay/contract/envelope-v1.json`` is recorded by the relay's own suite. Here
every recorded answer is fed to :class:`RelayClient` and to the connector
operations through a fake transport that returns the recorded status, headers
and body for the recorded request, and the decoded code and parsed data are
checked per route. A recorded answer the client cannot decode as the relay
meant it is a contract mismatch between the two sides, and this suite reds on
it. ``state.profile`` and ``state.provider`` are the relay suite's setup keys
and are ignored. Loopback is not named: the base URL is a documentation
domain.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpResponse,
)
from fitdocs.connectors.protocol import (
    ConnectorSession,
    RegistrationPolled,
    RegistrationStarted,
    RelayCapabilities,
    RelayRefused,
    TokenSet,
)
from fitdocs.connectors.relay import (
    RelayClient,
    RelayConnector,
    RelayReply,
    RelaySettings,
)
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode
from fitdocs.connectors.relay_envelope import (
    ROUTE_CAPABILITIES,
    ROUTE_REGISTRATION_POLL,
    ROUTE_REGISTRATIONS,
    ROUTE_TOKEN,
    ROUTE_TOKEN_REVOKE,
    EnvelopeError,
    encode_request,
)
from fitdocs.connectors.secrets import Redactor, Secret
from tests.connectors.conftest import FakeTransport

_RECORDED = Path(__file__).resolve().parents[2] / "relay/contract/envelope-v1.json"
_BASE = "https://relay.example.com"
_NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_FAKE_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52

# Routes the connector operations cover; the rest (probes, the unserved
# version, an unmatched path) are decoded at the client level only.
_OPERATION_ROUTES = frozenset(
    {
        ("GET", ROUTE_TOKEN),
        ("POST", ROUTE_TOKEN_REVOKE),
        ("GET", ROUTE_CAPABILITIES),
        ("POST", ROUTE_REGISTRATIONS),
        ("POST", ROUTE_REGISTRATION_POLL),
    }
)


def _load() -> list[dict[str, Any]]:
    document = json.loads(_RECORDED.read_text(encoding="utf-8"))
    assert document["envelope"] == 1
    exchanges = document["exchanges"]
    assert isinstance(exchanges, list)
    return exchanges


EXCHANGES = _load()
BY_NAME: dict[str, dict[str, Any]] = {e["name"]: e for e in EXCHANGES}


class _NoCredentials:
    """A relay operation takes its token as an argument and stores nothing."""

    def value(self, field: str) -> Secret:
        raise AssertionError("a relay operation takes its token as an argument")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("a relay operation stores nothing")


def _recorded_response(exchange: Mapping[str, Any]) -> HttpResponse:
    answer = exchange["answer"]
    assert isinstance(answer["body"], str)  # answer bodies are plain text
    return HttpResponse(
        status=answer["status"],
        headers=dict(answer["headers"]),
        body=answer["body"].encode("utf-8"),
    )


def _session(transport: FakeTransport) -> ConnectorSession:
    redactor = Redactor()
    return ConnectorSession(
        instance="relay",
        settings=RelaySettings(url=_BASE),
        http=HttpClient(
            transport,
            mode=CallMode.AUTH,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=_NoCredentials(),
        data_root=Path("unused"),
        now=lambda: _NOW,
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _transport_for(exchange: Mapping[str, Any]) -> FakeTransport:
    return FakeTransport([_recorded_response(exchange)])


def _expected_code(exchange: Mapping[str, Any]) -> RelayCode:
    return RelayCode(json.loads(exchange["answer"]["body"])["code"])


def _expected_data(exchange: Mapping[str, Any]) -> dict[str, Any]:
    data = json.loads(exchange["answer"]["body"])["data"]
    assert isinstance(data, dict)
    return data


def _expected_retry_after(exchange: Mapping[str, Any]) -> int | None:
    if _expected_code(exchange) is not RelayCode.RATE_LIMITED:
        return None
    return int(_expected_data(exchange)["retry_after_s"])


def _request_fields(exchange: Mapping[str, Any]) -> dict[str, object] | None:
    """The request's JSON object when the recorded body is one; ``None`` for an
    empty body, the non-JSON body (``RelayClient.post`` takes a mapping, so
    non-JSON text cannot be expressed) and the {prefix, fill, count, suffix}
    oversize form (``encode_request`` refuses its expansion)."""
    body = exchange["request"]["body"]
    if not isinstance(body, str) or body == "":
        return None
    try:
        parsed = json.loads(body)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _client_reply(exchange: Mapping[str, Any]) -> tuple[RelayReply, FakeTransport]:
    request = exchange["request"]
    transport = _transport_for(exchange)
    session = _session(transport)
    authorization = request["headers"].get("Authorization")
    token = None
    if authorization is not None:
        assert authorization.startswith("Bearer ")
        token = Secret(authorization.removeprefix("Bearer "))
    client = RelayClient(
        settings=RelaySettings(url=_BASE), http=session.http, token=token
    )
    if request["method"] == "GET":
        return client.get(request["path"]), transport
    fields = _request_fields(exchange)
    return client.post(request["path"], fields if fields is not None else {}), transport


# --------------------------------------------------------------------------
# The file itself
# --------------------------------------------------------------------------


def test_the_recording_is_read_whole_and_names_are_unique() -> None:
    assert len(EXCHANGES) == len(BY_NAME) >= 29
    assert {e["request"]["method"] for e in EXCHANGES} == {"GET", "POST"}
    covered = {(e["request"]["method"], e["request"]["path"]) for e in EXCHANGES}
    assert covered >= _OPERATION_ROUTES


def test_every_answer_without_route_defined_data_carries_none() -> None:
    with_data = {
        RelayCode.OK,
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_ISSUED,
        RelayCode.CONNECT_STARTED,
        RelayCode.CONNECT_GRANTED,
        RelayCode.RATE_LIMITED,
        RelayCode.ENVELOPE_UNSUPPORTED,
        RelayCode.SCHEMA_BEHIND,
        RelayCode.SCHEMA_AHEAD,
    }
    checked = 0
    for exchange in EXCHANGES:
        if _expected_code(exchange) not in with_data:
            assert _expected_data(exchange) == {}, exchange["name"]
            checked += 1
    assert checked >= 15


@pytest.mark.parametrize("exchange", EXCHANGES, ids=lambda e: e["name"])
def test_a_recorded_answer_is_plain_text_in_the_published_shape(
    exchange: dict[str, Any],
) -> None:
    answer = exchange["answer"]
    body = answer["body"]
    assert isinstance(body, str)
    headers = answer["headers"]
    assert all(name == name.lower() for name in headers)
    assert headers["content-type"] == "application/json"
    assert headers["cache-control"] == "no-store"
    assert headers["content-length"] == str(len(body.encode("utf-8")))
    code = _expected_code(exchange)
    info = RELAY_CODES[code]
    assert info.origin is CodeOrigin.RELAY
    assert answer["status"] == info.http_status
    # A stated wait is carried twice, and the two agree.
    if "retry-after" in headers:
        assert code is RelayCode.RATE_LIMITED
        assert int(headers["retry-after"]) == _expected_retry_after(exchange)
    else:
        assert code is not RelayCode.RATE_LIMITED


# --------------------------------------------------------------------------
# Every recorded answer through the client
# --------------------------------------------------------------------------


@pytest.mark.parametrize("exchange", EXCHANGES, ids=lambda e: e["name"])
def test_the_client_decodes_each_recorded_answer(exchange: dict[str, Any]) -> None:
    reply, transport = _client_reply(exchange)
    assert len(transport.requests) == 1
    sent = transport.requests[0]
    recorded = exchange["request"]
    assert sent.method == recorded["method"]
    assert sent.url == _BASE + recorded["path"]
    authorization = recorded["headers"].get("Authorization")
    if authorization is None:
        assert "Authorization" not in sent.secret_headers
    else:
        assert sent.secret_headers["Authorization"].reveal() == authorization
    # The client never fabricates a code: it is the recorded one.
    assert reply.code is _expected_code(exchange)
    assert reply.data == _expected_data(exchange)
    assert reply.outcome == json.loads(exchange["answer"]["body"]).get("outcome")
    assert reply.retry_after_s == _expected_retry_after(exchange)


def test_a_sendable_recorded_request_is_what_the_client_sends() -> None:
    sendable = 0
    for exchange in EXCHANGES:
        fields = _request_fields(exchange)
        if exchange["request"]["method"] != "POST" or fields is None:
            continue
        _, transport = _client_reply(exchange)
        assert transport.requests[0].body == encode_request(fields)
        assert transport.requests[0].body == exchange["request"]["body"].encode()
        sendable += 1
    skipped = {
        e["name"]
        for e in EXCHANGES
        if e["request"]["method"] == "POST" and _request_fields(e) is None
    }
    assert skipped == {"registration-start-malformed", "registration-start-too-large"}
    assert sendable == sum(e["request"]["method"] == "POST" for e in EXCHANGES) - 2


def test_the_client_refuses_to_encode_the_oversize_request() -> None:
    too_large = BY_NAME["registration-start-too-large"]["request"]["body"]
    email = too_large["fill"] * too_large["count"]
    with pytest.raises(EnvelopeError):
        encode_request({"email": email + "@example.test"})


# --------------------------------------------------------------------------
# Every route through the connector operations
# --------------------------------------------------------------------------


def _operation_result(
    exchange: Mapping[str, Any],
) -> object:
    request = exchange["request"]
    route = (request["method"], request["path"])
    transport = _transport_for(exchange)
    session = _session(transport)
    connector = RelayConnector()
    token = session.secret(_FAKE_TOKEN)
    result: object
    if route == ("GET", ROUTE_TOKEN):
        result = connector.check_token(session, token)
    elif route == ("POST", ROUTE_TOKEN_REVOKE):
        result = connector.revoke_token(session, token)
    elif route == ("GET", ROUTE_CAPABILITIES):
        result = connector.read_capabilities(session)
    elif route == ("POST", ROUTE_REGISTRATIONS):
        result = connector.start_registration(session, "someone@example.test")
    else:
        assert route == ("POST", ROUTE_REGISTRATION_POLL)
        fields = _request_fields(exchange)
        assert fields is not None
        started = RegistrationStarted(
            user_code="BCDF-GHJK",
            poll_secret=session.secret(str(fields["poll_secret"])),
            interval_s=5,
            expires_at=_NOW + timedelta(seconds=600),
        )
        result = connector.poll_registration(session, started)
    assert len(transport.requests) == 1
    return result


def _expected_operation_result(exchange: Mapping[str, Any]) -> object:
    code = _expected_code(exchange)
    data = _expected_data(exchange)
    route = (exchange["request"]["method"], exchange["request"]["path"])
    refused = RelayRefused(code, _expected_retry_after(exchange))
    if route in {("GET", ROUTE_TOKEN), ("POST", ROUTE_TOKEN_REVOKE)}:
        return None if code is RelayCode.OK else refused
    if route == ("GET", ROUTE_CAPABILITIES):
        if code is not RelayCode.OK:
            return refused
        return RelayCapabilities(
            envelopes=tuple(data["envelopes"]),
            registration=data["registration"],
            targets=tuple(data["targets"]),
        )
    if route == ("POST", ROUTE_REGISTRATIONS):
        if code is not RelayCode.REGISTRATION_STARTED:
            return refused
        return RegistrationStarted(
            user_code=data["user_code"],
            poll_secret=Secret(data["poll_secret"]),
            interval_s=data["interval_s"],
            expires_at=_NOW + timedelta(seconds=data["expires_in_s"]),
        )
    if code in {RelayCode.REGISTRATION_PENDING, RelayCode.REGISTRATION_SLOW_DOWN}:
        return RegistrationPolled(code=code, token=None)
    if code is RelayCode.REGISTRATION_ISSUED:
        return RegistrationPolled(code=code, token=Secret(data["token"]))
    return refused


def test_every_operation_route_exchange_decodes_to_its_expected_result() -> None:
    decoded = [
        e
        for e in EXCHANGES
        if (e["request"]["method"], e["request"]["path"]) in _OPERATION_ROUTES
    ]
    assert len(decoded) >= 22
    for exchange in decoded:
        got = _operation_result(exchange)
        want = _expected_operation_result(exchange)
        assert got == want, exchange["name"]


def test_each_operation_route_has_a_success_and_a_refusal_recorded() -> None:
    results = {
        e["name"]: _operation_result(e)
        for e in EXCHANGES
        if (e["request"]["method"], e["request"]["path"]) in _OPERATION_ROUTES
    }
    assert results["token-check-ok"] is None
    assert results["token-revoke-ok"] is None
    assert results["token-check-missing"] == RelayRefused(RelayCode.TOKEN_MISSING)
    assert results["token-check-unknown"] == RelayRefused(RelayCode.TOKEN_UNKNOWN)
    assert results["token-check-revoked"] == RelayRefused(RelayCode.TOKEN_REVOKED)
    assert results["capabilities-with-registration"] == RelayCapabilities(
        envelopes=(1,), registration=True, targets=()
    )
    assert results["capabilities-without-registration"] == RelayCapabilities(
        envelopes=(1,), registration=False, targets=()
    )
    assert results["capabilities-rate-limited"] == RelayRefused(
        RelayCode.RATE_LIMITED, 60
    )
    assert results["capabilities-unavailable"] == RelayRefused(RelayCode.UNAVAILABLE)
    assert results["registration-start-rate-limited"] == RelayRefused(
        RelayCode.RATE_LIMITED, 7
    )
    assert results["registration-refused"] == RelayRefused(
        RelayCode.REGISTRATION_REFUSED
    )
    assert results["registration-start-malformed"] == RelayRefused(
        RelayCode.REQUEST_MALFORMED
    )
    assert results["registration-start-too-large"] == RelayRefused(
        RelayCode.REQUEST_TOO_LARGE
    )
    assert results["registration-start-failure"] == RelayRefused(
        RelayCode.RELAY_FAILURE
    )
    assert results["registration-start-not-offered"] == RelayRefused(
        RelayCode.NOT_OFFERED
    )
    started = results["registration-started"]
    assert isinstance(started, RegistrationStarted)
    assert started.user_code == "BCDF-GHJK"
    assert started.poll_secret.reveal() == "a" * 48
    assert started.interval_s == 5
    assert started.expires_at == _NOW + timedelta(seconds=600)
    assert results["poll-pending"] == RegistrationPolled(
        RelayCode.REGISTRATION_PENDING, None
    )
    assert results["poll-slow-down"] == RegistrationPolled(
        RelayCode.REGISTRATION_SLOW_DOWN, None
    )
    issued = results["poll-issued"]
    assert isinstance(issued, RegistrationPolled)
    assert issued.code is RelayCode.REGISTRATION_ISSUED
    assert issued.token is not None
    assert issued.token.reveal() == _FAKE_TOKEN
    assert results["poll-refused"] == RelayRefused(RelayCode.REGISTRATION_REFUSED)
    assert results["poll-expired"] == RelayRefused(RelayCode.REGISTRATION_EXPIRED)
    assert results["poll-not-offered"] == RelayRefused(RelayCode.NOT_OFFERED)


def test_the_unserved_version_and_unmatched_path_answers_carry_their_data() -> None:
    unsupported, _ = _client_reply(BY_NAME["envelope-unsupported"])
    assert unsupported.code is RelayCode.ENVELOPE_UNSUPPORTED
    assert unsupported.data == {"envelopes": [1]}
    unmatched, _ = _client_reply(BY_NAME["unmatched-not-offered"])
    assert unmatched.code is RelayCode.NOT_OFFERED
    assert unmatched.data == {}


def test_every_recorded_relay_code_is_decoded_by_some_exchange() -> None:
    seen = {_expected_code(e) for e in EXCHANGES}
    relay_codes = {
        code for code, info in RELAY_CODES.items() if info.origin is CodeOrigin.RELAY
    }
    # A code the recording lacks would be a code no decode test exercises.
    assert relay_codes - seen == set()
    assert seen - relay_codes == set()
