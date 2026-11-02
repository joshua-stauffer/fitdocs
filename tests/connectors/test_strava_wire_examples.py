"""The relay's recorded Strava exchanges decoded through the fitdocs client and
the Strava connector (strava-publish task 5.9; Requirements 5.6, 8.4).

``relay/contract/envelope-v1.json`` is recorded by the relay's own suite. Here
every ``strava-*`` exchange is fed through a fake transport that returns the
recorded status, headers and body, and the decoded result is compared with a
literal written in this file. The literals are not read from the recording, so
editing a recorded code, outcome or datum in the JSON no longer matches them.

The expectations table is keyed by exchange name, and a test compares its keys
with the names found in the recording: a new ``strava-*`` exchange with no
decode case reds that test. The recorded ``strava-publish-facts-missing``
request cannot be sent through ``StravaConnector.publish`` (the connector
answers that code locally and sends nothing), so it is decoded through
``RelayClient`` and the outcome table. The base URL is a documentation domain.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from fitdocs.connectors.http import CallMode, HttpClient, HttpResponse
from fitdocs.connectors.protocol import (
    CompletedActivity,
    ConnectorSession,
    ConsentPolled,
    ConsentStarted,
    Post,
    PublishCode,
    PublishRequest,
    PublishResult,
    RelayRefused,
    TokenSet,
)
from fitdocs.connectors.relay import RelayClient, RelaySettings
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.relay_targets import PUBLISH_OUTCOMES, route_outcome
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.strava import StravaConnector, StravaSettings
from tests.connectors.conftest import FakeTransport

_RECORDED = Path(__file__).resolve().parents[2] / "relay/contract/envelope-v1.json"
_BASE = "https://relay.example.com"
_NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_PRESENTED = "fdr1_" + "a" * 16 + "_" + "a" * 52
_ISSUED = "fdr1_" + "b" * 16 + "_" + "b" * 52
_POLL_SECRET = "a" * 43
_LINK = "https://strava.example.invalid/activities/1"
_RELAY_LINK = _BASE + "/go/" + "0" * 32
_PUBLISH_ROUTE = "/v1/targets/strava/publish"

_PREFIX = "strava-"


def _load() -> list[dict[str, Any]]:
    document = json.loads(_RECORDED.read_text(encoding="utf-8"))
    assert document["envelope"] == 1
    return [e for e in document["exchanges"] if e["name"].startswith(_PREFIX)]


EXCHANGES = _load()
BY_NAME: dict[str, dict[str, Any]] = {e["name"]: e for e in EXCHANGES}


class _Credentials:
    """The connection token a publish presents; consent operations take theirs
    as an argument and never reach this."""

    def value(self, field: str) -> Secret:
        assert field == "token"
        return Secret(_PRESENTED)

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("decoding stores nothing")


def _response(exchange: Mapping[str, Any]) -> HttpResponse:
    answer = exchange["answer"]
    assert isinstance(answer["body"], str)
    return HttpResponse(
        status=answer["status"],
        headers=dict(answer["headers"]),
        body=answer["body"].encode("utf-8"),
    )


def _session(transport: FakeTransport, *, upload: bool = False) -> ConnectorSession:
    redactor = Redactor()
    return ConnectorSession(
        instance="strava",
        settings=StravaSettings(
            relay_instance="home", upload=upload, relay=RelaySettings(url=_BASE)
        ),
        http=HttpClient(
            transport,
            mode=CallMode.DATA,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=_Credentials(),
        data_root=Path("unused"),
        now=lambda: _NOW,
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _body(exchange: Mapping[str, Any]) -> dict[str, Any]:
    parsed = json.loads(exchange["request"]["body"])
    assert isinstance(parsed, dict)
    return parsed


def _assert_sent(
    exchange: Mapping[str, Any], transport: FakeTransport, index: int = 0
) -> None:
    """The client sent the recorded request: route, token and body bytes."""
    sent = transport.requests[index]
    recorded = exchange["request"]
    assert sent.method == recorded["method"]
    assert sent.url == _BASE + recorded["path"]
    authorization = recorded["headers"]["Authorization"]
    assert authorization == "Bearer " + _PRESENTED
    assert sent.secret_headers["Authorization"].reveal() == authorization
    assert sent.body == recorded["body"].encode("utf-8")


# --------------------------------------------------------------------------
# Consent and disconnect through the connector
# --------------------------------------------------------------------------


def _consent_result(exchange: Mapping[str, Any]) -> object:
    transport = FakeTransport([_response(exchange)])
    session = _session(transport)
    connector = StravaConnector()
    token = session.secret(_PRESENTED)
    path = exchange["request"]["path"]
    result: object
    if path.endswith("/connect"):
        result = connector.start_consent(session, token)
    elif path.endswith("/connect/poll"):
        started = ConsentStarted(
            user_code="BCDF-GHJK",
            page_url=_BASE + "/connect/strava?code=BCDF-GHJK",
            poll_secret=session.secret(_body(exchange)["poll_secret"]),
            interval_s=3,
            expires_at=_NOW + timedelta(seconds=600),
        )
        result = connector.poll_consent(session, started, token)
    else:
        assert path.endswith("/disconnect")
        result = connector.withdraw_consent(session, token)
    assert len(transport.requests) == 1
    _assert_sent(exchange, transport)
    return result


def _started() -> ConsentStarted:
    return ConsentStarted(
        user_code="BCDF-GHJK",
        page_url=_BASE + "/connect/strava?code=BCDF-GHJK",
        poll_secret=Secret(_POLL_SECRET),
        interval_s=3,
        expires_at=_NOW + timedelta(seconds=600),
    )


_CONSENT: dict[str, Callable[[], object]] = {
    "strava-connect-started": _started,
    "strava-connect-not-offered": lambda: RelayRefused(RelayCode.NOT_OFFERED),
    "strava-connect-poll-pending": lambda: ConsentPolled(
        RelayCode.CONNECT_PENDING, None
    ),
    "strava-connect-poll-granted": lambda: ConsentPolled(
        RelayCode.CONNECT_GRANTED, Secret(_ISSUED)
    ),
    "strava-connect-poll-refused": lambda: RelayRefused(RelayCode.CONNECT_REFUSED),
    "strava-connect-poll-expired": lambda: RelayRefused(RelayCode.CONNECT_EXPIRED),
    "strava-disconnect-ok": lambda: None,
    "strava-disconnect-not-connected": lambda: None,
}


@pytest.mark.parametrize("name", sorted(_CONSENT))
def test_a_recorded_consent_or_disconnect_answer_decodes(name: str) -> None:
    got = _consent_result(BY_NAME[name])
    want = _CONSENT[name]()
    assert got == want
    assert type(got) is type(want)


# --------------------------------------------------------------------------
# Publish and upload through the connector
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Case:
    result: PublishResult
    upload: bool = False


_PUBLISH: dict[str, _Case] = {
    "strava-publish-posted": _Case(PublishResult(PublishCode.POSTED, _LINK)),
    "strava-publish-posted-relay-links": _Case(
        PublishResult(PublishCode.POSTED, _RELAY_LINK)
    ),
    "strava-publish-not-found": _Case(PublishResult(PublishCode.NOT_FOUND)),
    "strava-publish-ambiguous": _Case(PublishResult(PublishCode.AMBIGUOUS)),
    "strava-publish-rate-limited": _Case(PublishResult(PublishCode.RATE_LIMITED)),
    "strava-publish-not-connected": _Case(PublishResult(PublishCode.NOT_CONNECTED)),
    "strava-upload-uploaded": _Case(
        PublishResult(PublishCode.UPLOADED, _LINK), upload=True
    ),
    "strava-upload-uploaded-relay-links": _Case(
        PublishResult(PublishCode.UPLOADED, _RELAY_LINK), upload=True
    ),
    "strava-upload-posted": _Case(
        PublishResult(PublishCode.POSTED, _LINK), upload=True
    ),
    "strava-upload-unconfirmed": _Case(
        PublishResult(PublishCode.UNCONFIRMED), upload=True
    ),
    "strava-upload-not-connected": _Case(
        PublishResult(PublishCode.NOT_CONNECTED), upload=True
    ),
}

# Decoded through the client and the outcome table instead, with the reason.
_PUBLISH_CLIENT_ONLY: dict[str, PublishCode] = {
    "strava-publish-facts-missing": PublishCode.ACTIVITY_FACTS_MISSING,
}


def _request_from(exchange: Mapping[str, Any], base_fit: Path | None) -> PublishRequest:
    fields = _body(exchange)
    return PublishRequest(
        publication_id=fields["publication_id"],
        post=Post(title=fields["title"], description=fields["description"]),
        subject=CompletedActivity(
            sport=fields["sport"],
            start=datetime.fromisoformat(fields["start"]),
            elapsed_s=fields["elapsed_s"],
            distance_m=fields["distance_m"],
            source_shas=("a" * 64,),
            base_fit=base_fit,
        ),
        recorded_link=None,
    )


def _publish_result(
    exchange: Mapping[str, Any], tmp_path: Path
) -> tuple[PublishResult, FakeTransport]:
    upload = exchange["request"]["path"].endswith("/upload")
    if not upload:
        transport = FakeTransport([_response(exchange)])
        result = StravaConnector().publish(
            _session(transport), _request_from(exchange, None)
        )
        assert len(transport.requests) == 1
        _assert_sent(exchange, transport)
        return result, transport
    # The upload follows the relay's definite not-found publish answer; both
    # answers are recorded, and both requests are the recorded bytes.
    first = BY_NAME["strava-publish-not-found"]
    fit = tmp_path / "base.fit"
    fit.write_bytes(base64.b64decode(_body(exchange)["fit"], validate=True))
    transport = FakeTransport([_response(first), _response(exchange)])
    result = StravaConnector().publish(
        _session(transport, upload=True), _request_from(exchange, fit)
    )
    assert len(transport.requests) == 2
    assert transport.requests[0].url == _BASE + _PUBLISH_ROUTE
    _assert_sent(exchange, transport, 1)
    return result, transport


@pytest.mark.parametrize("name", sorted(_PUBLISH))
def test_a_recorded_publish_or_upload_answer_decodes(name: str, tmp_path: Path) -> None:
    result, _ = _publish_result(BY_NAME[name], tmp_path)
    assert result == _PUBLISH[name].result
    assert _PUBLISH[name].upload is BY_NAME[name]["request"]["path"].endswith("/upload")


def test_the_facts_missing_answer_decodes_through_the_client() -> None:
    exchange = BY_NAME["strava-publish-facts-missing"]
    fields = _body(exchange)
    # The precondition that keeps it off the connector: neither fact is sent.
    assert fields["elapsed_s"] is None and fields["distance_m"] is None
    transport = FakeTransport([_response(exchange)])
    session = _session(transport)
    client = RelayClient(
        settings=RelaySettings(url=_BASE), http=session.http, token=Secret(_PRESENTED)
    )
    reply = client.post(exchange["request"]["path"], fields)
    _assert_sent(exchange, transport)
    assert reply.code is RelayCode.OK
    assert reply.data == {}
    outcome = route_outcome(reply.outcome, PUBLISH_OUTCOMES)
    assert outcome is not None
    assert PublishCode(outcome) is _PUBLISH_CLIENT_ONLY["strava-publish-facts-missing"]

    # The connector answers the same code without sending anything.
    local = FakeTransport([])
    request = _request_from(exchange, None)
    assert (
        StravaConnector().publish(_session(local), request).code
        is PublishCode.ACTIVITY_FACTS_MISSING
    )
    assert local.requests == []


def test_the_recorded_not_offered_answer_reaches_the_mapping_rows(
    tmp_path: Path,
) -> None:
    """No recorded publish-route answer is a refusal, so the one refusal that
    names no route (a target the relay does not offer) is fed to the publish
    and the upload requests: both read it through their mapping rows."""
    refusal = BY_NAME["strava-connect-not-offered"]
    publish = BY_NAME["strava-publish-not-found"]
    assert json.loads(refusal["answer"]["body"])["code"] == "not-offered"

    transport = FakeTransport([_response(refusal)])
    result = StravaConnector().publish(
        _session(transport), _request_from(publish, None)
    )
    assert result == PublishResult(PublishCode.NOT_CONNECTED)
    assert len(transport.requests) == 1

    fit = tmp_path / "base.fit"
    fit.write_bytes(
        base64.b64decode(_body(BY_NAME["strava-upload-posted"])["fit"], validate=True)
    )
    transport = FakeTransport([_response(publish), _response(refusal)])
    result = StravaConnector().publish(
        _session(transport, upload=True), _request_from(publish, fit)
    )
    assert result == PublishResult(PublishCode.NOT_CONNECTED)
    assert len(transport.requests) == 2


# --------------------------------------------------------------------------
# The recording is covered whole
# --------------------------------------------------------------------------


def test_every_recorded_strava_exchange_has_a_decode_case() -> None:
    covered = set(_CONSENT) | set(_PUBLISH) | set(_PUBLISH_CLIENT_ONLY)
    recorded = {e["name"] for e in EXCHANGES}
    assert len(recorded) == len(EXCHANGES) >= 20
    assert recorded - covered == set(), "a recorded exchange has no decode case"
    assert covered - recorded == set(), "a decode case has no recorded exchange"
