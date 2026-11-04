"""The Strava connector's publish operation and its registration
(strava-publish task 5.5; Requirements 1.1, 1.7, 5.1-5.4, 5.6-5.10, 7.8, 8.4).

Every request goes through a scripted ``FakeTransport``; nothing reaches a
network. Expected request bodies, mapping rows and links are literals.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

import fitdocs.connectors as connectors_package
from fitdocs.connectors import registry
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.protocol import (
    TARGET_CODES,
    CompletedActivity,
    ConnectorSession,
    Post,
    PostPublisher,
    PublishCode,
    PublishRequest,
    PublishResult,
    TokenSet,
)
from fitdocs.connectors.relay import RelayReply, RelaySettings
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode
from fitdocs.connectors.relay_envelope import Answer, encode_answer
from fitdocs.connectors.relay_targets import (
    MAX_DESCRIPTION_CHARS,
    MAX_FIT_BYTES,
    MAX_TITLE_CHARS,
    MAX_UPLOAD_REQUEST_BYTES,
    PUBLISH_OUTCOMES,
    UPLOAD_OUTCOMES,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.strava import (
    PUBLISH_MAPPING,
    UPLOAD_MAPPING,
    StravaConnector,
    StravaSettings,
    _link,
)
from fitdocs.docmerge import extract_regions
from fitdocs.publish.engine import run_publish
from fitdocs.publish.request import valid_label
from fitdocs.publish.targets import TargetChannel
from tests.connectors.conftest import FakeTransport
from tests.publish.test_engine import CLOCK as ENGINE_CLOCK
from tests.publish.test_engine import Env, _id

_CLOCK = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_BASE = "https://relay.example.com"
_TOKEN = "fdr1_" + "c" * 16 + "_" + "d" * 52
_ID = "0123456789abcdef0123456789abcdef"
_START = datetime(2026, 3, 4, 7, 5, tzinfo=timezone(timedelta(hours=2)))
_PUBLISH_URL = _BASE + "/v1/targets/strava/publish"
_UPLOAD_URL = _BASE + "/v1/targets/strava/upload"


def _fit(extra: int = 0) -> bytes:
    """A file the shared wire accepts as FIT: 12-byte header carrying ``.FIT``."""
    return (
        b"\x0e\x10\x00\x00\x07\x00\x00\x00.FIT"
        + b"\x01\x02\x03\x04" * 3
        + (b"\x05" * extra)
    )


class _Credentials:
    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor

    def value(self, field: str) -> Secret:
        assert field == "token"
        return Secret(_TOKEN)

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("publishing stores nothing")


def _session(
    transport: FakeTransport,
    *,
    upload: bool = False,
    url: str = _BASE,
    redactor: Redactor | None = None,
) -> ConnectorSession:
    redactor = redactor if redactor is not None else Redactor()
    return ConnectorSession(
        instance="strava",
        settings=StravaSettings(
            relay_instance="home", upload=upload, relay=RelaySettings(url=url)
        ),
        http=HttpClient(
            transport,
            mode=CallMode.DATA,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=_Credentials(redactor),
        data_root=Path("."),
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _request(
    *,
    fit: Path | None = None,
    elapsed_s: float | None = 3725.5,
    distance_m: float | None = 12500.25,
    title: str = "Morning Run",
    description: str = "Distance: 12.50 km\nTime: 58:20",
    recorded_link: str | None = None,
    start: datetime = _START,
    sport: str = "Run",
) -> PublishRequest:
    return PublishRequest(
        publication_id=_ID,
        post=Post(title=title, description=description),
        subject=CompletedActivity(
            sport=sport,
            start=start,
            elapsed_s=elapsed_s,
            distance_m=distance_m,
            source_shas=("a" * 64,),
            base_fit=fit,
        ),
        recorded_link=recorded_link,
    )


def _answer(
    code: RelayCode,
    outcome: str | None = None,
    data: Mapping[str, object] | None = None,
) -> HttpResponse:
    info = RELAY_CODES[code]
    assert info.origin is CodeOrigin.RELAY
    assert info.http_status is not None
    return HttpResponse(
        status=info.http_status,
        headers={},
        body=encode_answer(Answer(code=code, data=data or {}, outcome=outcome)),
    )


def _ok(outcome: str, data: Mapping[str, object] | None = None) -> HttpResponse:
    return _answer(RelayCode.OK, outcome, data)


def _gateway() -> HttpResponse:
    return HttpResponse(status=502, headers={}, body=b"<html>Bad Gateway</html>")


def _publish(
    script: list[HttpResponse | TransportError],
    request: PublishRequest | None = None,
    *,
    upload: bool = False,
    url: str = _BASE,
) -> tuple[PublishResult, FakeTransport]:
    transport = FakeTransport(script)
    result = StravaConnector().publish(
        _session(transport, upload=upload, url=url), request or _request()
    )
    return result, transport


def _fit_file(tmp_path: Path, data: bytes | None = None) -> Path:
    path = tmp_path / "base.fit"
    path.write_bytes(_fit() if data is None else data)
    return path


def _sparse_fit(tmp_path: Path, size: int) -> Path:
    path = tmp_path / "big.fit"
    with path.open("wb") as handle:
        handle.write(_fit())
        handle.truncate(size)
    return path


def _body(request: HttpRequest) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(request.body or b""))


# --------------------------------------------------------------------------
# The publish request (5.1, 5.2)
# --------------------------------------------------------------------------


def test_the_publish_request_is_one_literal_post_with_the_token() -> None:
    result, transport = _publish([_ok("posted")])
    assert result == PublishResult(PublishCode.POSTED, None)
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == _PUBLISH_URL
    assert request.single_attempt is True
    assert {k: v.reveal() for k, v in request.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }
    assert _body(request) == {
        "publication_id": _ID,
        "sport": "Run",
        "start": "2026-03-04T07:05:00+02:00",
        "elapsed_s": 3725.5,
        "distance_m": 12500.25,
        "title": "Morning Run",
        "description": "Distance: 12.50 km\nTime: 58:20",
    }


def test_sport_and_description_are_sent_verbatim() -> None:
    padded = "  padded \n body \n "
    _, transport = _publish(
        [_ok("posted")], _request(sport="VirtualRide", description=padded)
    )
    body = _body(transport.requests[0])
    assert body["sport"] == "VirtualRide"
    assert body["description"] == padded


def test_the_connection_token_is_registered_with_the_redactor() -> None:
    redactor = Redactor()
    transport = FakeTransport([_ok("posted")])
    StravaConnector().publish(_session(transport, redactor=redactor), _request())
    assert redactor.redact("x " + _TOKEN + " y") == "x " + REDACTED + " y"


@pytest.mark.parametrize(
    ("elapsed_s", "distance_m", "sent"),
    [(None, None, 0), (None, 100.0, 1), (60.0, None, 1), (0.0, 0.0, 1)],
)
def test_facts_missing_means_both_figures_absent_and_no_request(
    elapsed_s: float | None, distance_m: float | None, sent: int
) -> None:
    result, transport = _publish(
        [_ok("posted")] if sent else [],
        _request(elapsed_s=elapsed_s, distance_m=distance_m),
    )
    assert len(transport.requests) == sent
    if not sent:
        assert result == PublishResult(PublishCode.ACTIVITY_FACTS_MISSING)
    else:
        assert result.code is PublishCode.POSTED
        body = _body(transport.requests[0])
        assert body["elapsed_s"] == elapsed_s  # None is JSON null, never 0.0
        assert body["distance_m"] == distance_m
        assert (body["elapsed_s"] is None) == (elapsed_s is None)
        assert (body["distance_m"] is None) == (distance_m is None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "t" * (MAX_TITLE_CHARS + 1)},
        {"description": "d" * (MAX_DESCRIPTION_CHARS + 1)},
        {"title": ""},
        {"start": datetime(2026, 3, 4, 7, 5)},
    ],
)
def test_a_post_the_wire_refuses_is_rejected_without_a_request(
    overrides: dict[str, object],
) -> None:
    request = _request(**overrides)  # type: ignore[arg-type]
    result, transport = _publish([], request)
    assert result == PublishResult(PublishCode.REJECTED)
    assert transport.requests == []


def test_a_post_at_the_wire_limits_is_sent() -> None:
    result, transport = _publish(
        [_ok("posted")],
        _request(title="t" * MAX_TITLE_CHARS, description="d" * MAX_DESCRIPTION_CHARS),
    )
    assert result.code is PublishCode.POSTED
    assert len(transport.requests) == 1


# --------------------------------------------------------------------------
# The mapping tables, row by row (5.6, 8.4)
# --------------------------------------------------------------------------

_P = PublishCode
_R = RelayCode

# (relay code, publish-request code, upload-request code)
_ROWS: tuple[tuple[RelayCode, PublishCode, PublishCode], ...] = (
    (_R.OK, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.TOKEN_MISSING, _P.AUTH_REJECTED, _P.AUTH_REJECTED),
    (_R.TOKEN_UNKNOWN, _P.AUTH_REJECTED, _P.AUTH_REJECTED),
    (_R.TOKEN_REVOKED, _P.AUTH_REJECTED, _P.AUTH_REJECTED),
    (_R.ENVELOPE_UNSUPPORTED, _P.UNAVAILABLE, _P.UNAVAILABLE),
    (_R.REQUEST_MALFORMED, _P.REJECTED, _P.REJECTED),
    (_R.REQUEST_TOO_LARGE, _P.REJECTED, _P.REJECTED),
    (_R.NOT_OFFERED, _P.NOT_CONNECTED, _P.NOT_CONNECTED),
    (_R.RATE_LIMITED, _P.RATE_LIMITED, _P.RATE_LIMITED),
    (_R.UNAVAILABLE, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.RELAY_FAILURE, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.STORAGE_UNREACHABLE, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.SCHEMA_BEHIND, _P.UNAVAILABLE, _P.UNAVAILABLE),
    (_R.SCHEMA_AHEAD, _P.UNAVAILABLE, _P.UNAVAILABLE),
    (_R.REGISTRATION_STARTED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.REGISTRATION_PENDING, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.REGISTRATION_SLOW_DOWN, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.REGISTRATION_ISSUED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.REGISTRATION_REFUSED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.REGISTRATION_EXPIRED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.RELAY_UNREACHABLE, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.ANSWER_MALFORMED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.CONNECT_STARTED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.CONNECT_PENDING, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.CONNECT_GRANTED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.CONNECT_REFUSED, _P.UNAVAILABLE, _P.UNCONFIRMED),
    (_R.CONNECT_EXPIRED, _P.UNAVAILABLE, _P.UNCONFIRMED),
)


def test_the_literal_table_names_every_relay_code_once() -> None:
    assert [row[0] for row in _ROWS] == list(RelayCode)
    assert len(_ROWS) == 27
    assert len({row[0] for row in _ROWS}) == 27


def test_the_publish_mapping_is_the_literal_publish_column() -> None:
    assert dict(PUBLISH_MAPPING) == {row[0]: row[1] for row in _ROWS}


def test_the_upload_mapping_is_the_literal_upload_column() -> None:
    assert dict(UPLOAD_MAPPING) == {row[0]: row[2] for row in _ROWS}


def _relay_answer_for(code: RelayCode) -> HttpResponse | TransportError:
    """The scripted transport answer that makes the client conclude ``code``."""
    if code is RelayCode.RELAY_UNREACHABLE:
        return TransportError("down")
    if code is RelayCode.ANSWER_MALFORMED:
        return HttpResponse(status=200, headers={}, body=b"not an envelope")
    if code is RelayCode.RATE_LIMITED:
        return _answer(code, None, {})
    return _answer(code)


@pytest.mark.parametrize(("code", "expected", "_"), _ROWS)
def test_each_relay_code_on_the_publish_route_gives_its_publish_row(
    code: RelayCode, expected: PublishCode, _: PublishCode
) -> None:
    result, transport = _publish([_relay_answer_for(code)], upload=True)
    assert result == PublishResult(expected)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(("code", "_", "expected"), _ROWS)
def test_each_relay_code_on_the_upload_route_gives_its_upload_row(
    code: RelayCode, _: PublishCode, expected: PublishCode, tmp_path: Path
) -> None:
    result, transport = _publish(
        [_ok("not_found"), _relay_answer_for(code)],
        _request(fit=_fit_file(tmp_path)),
        upload=True,
    )
    assert result == PublishResult(expected)
    assert [r.url for r in transport.requests] == [_PUBLISH_URL, _UPLOAD_URL]


_PUBLISH_OUTCOME_ROWS = (
    ("posted", _P.POSTED),
    ("not_found", _P.NOT_FOUND),
    ("ambiguous", _P.AMBIGUOUS),
    ("not_updatable", _P.NOT_UPDATABLE),
    ("not_connected", _P.NOT_CONNECTED),
    ("auth_rejected", _P.AUTH_REJECTED),
    ("permission_denied", _P.PERMISSION_DENIED),
    ("rate_limited", _P.RATE_LIMITED),
    ("unavailable", _P.UNAVAILABLE),
    ("rejected", _P.REJECTED),
    ("activity_facts_missing", _P.ACTIVITY_FACTS_MISSING),
)
_UPLOAD_OUTCOME_ROWS = (
    ("posted", _P.POSTED),
    ("uploaded", _P.UPLOADED),
    ("ambiguous", _P.AMBIGUOUS),
    ("not_updatable", _P.NOT_UPDATABLE),
    ("not_connected", _P.NOT_CONNECTED),
    ("auth_rejected", _P.AUTH_REJECTED),
    ("permission_denied", _P.PERMISSION_DENIED),
    ("rate_limited", _P.RATE_LIMITED),
    ("unavailable", _P.UNAVAILABLE),
    ("rejected", _P.REJECTED),
    ("unconfirmed", _P.UNCONFIRMED),
    ("activity_facts_missing", _P.ACTIVITY_FACTS_MISSING),
)


def test_the_outcome_rows_cover_the_route_sets_exactly() -> None:
    assert {o for o, _ in _PUBLISH_OUTCOME_ROWS} == PUBLISH_OUTCOMES
    assert {o for o, _ in _UPLOAD_OUTCOME_ROWS} == UPLOAD_OUTCOMES
    assert len(_PUBLISH_OUTCOME_ROWS) == len(PUBLISH_OUTCOMES) == 11
    assert len(_UPLOAD_OUTCOME_ROWS) == len(UPLOAD_OUTCOMES) == 12
    for _, code in (*_PUBLISH_OUTCOME_ROWS, *_UPLOAD_OUTCOME_ROWS):
        assert code in TARGET_CODES


@pytest.mark.parametrize(("outcome", "expected"), _PUBLISH_OUTCOME_ROWS)
def test_an_ok_publish_outcome_in_the_set_is_that_code(
    outcome: str, expected: PublishCode
) -> None:
    result, transport = _publish([_ok(outcome, {"link": "https://x.example/1"})])
    assert result.code is expected
    assert len(transport.requests) == 1


@pytest.mark.parametrize(("outcome", "expected"), _UPLOAD_OUTCOME_ROWS)
def test_an_ok_upload_outcome_in_the_set_is_that_code(
    outcome: str, expected: PublishCode, tmp_path: Path
) -> None:
    result, _ = _publish(
        [_ok("not_found"), _ok(outcome, {"link": "https://x.example/1"})],
        _request(fit=_fit_file(tmp_path)),
        upload=True,
    )
    assert result.code is expected


@pytest.mark.parametrize("outcome", ["uploaded", "unconfirmed", "bogus", "POSTED"])
def test_an_upload_route_or_unknown_outcome_on_the_publish_route_is_unavailable(
    outcome: str, tmp_path: Path
) -> None:
    result, transport = _publish(
        [_ok(outcome)], _request(fit=_fit_file(tmp_path)), upload=True
    )
    assert result == PublishResult(PublishCode.UNAVAILABLE)
    assert len(transport.requests) == 1


@pytest.mark.parametrize("outcome", ["not_found", "bogus", "UPLOADED"])
def test_a_publish_route_or_unknown_outcome_on_the_upload_route_is_unconfirmed(
    outcome: str, tmp_path: Path
) -> None:
    result, _ = _publish(
        [_ok("not_found"), _ok(outcome)],
        _request(fit=_fit_file(tmp_path)),
        upload=True,
    )
    assert result == PublishResult(PublishCode.UNCONFIRMED)


def test_an_ok_answer_with_no_outcome_is_the_ok_row_on_each_route(
    tmp_path: Path,
) -> None:
    result, _ = _publish([_answer(RelayCode.OK)])
    assert result == PublishResult(PublishCode.UNAVAILABLE)
    result, _ = _publish(
        [_ok("not_found"), _answer(RelayCode.OK)],
        _request(fit=_fit_file(tmp_path)),
        upload=True,
    )
    assert result == PublishResult(PublishCode.UNCONFIRMED)


def test_a_non_envelope_502_on_the_upload_route_is_unconfirmed(
    tmp_path: Path,
) -> None:
    result, transport = _publish(
        [_ok("not_found"), _gateway()],
        _request(fit=_fit_file(tmp_path)),
        upload=True,
    )
    assert result == PublishResult(PublishCode.UNCONFIRMED)
    assert [r.url for r in transport.requests] == [_PUBLISH_URL, _UPLOAD_URL]


def test_the_same_502_on_the_publish_route_is_unavailable() -> None:
    result, transport = _publish([_gateway()], upload=True)
    assert result == PublishResult(PublishCode.UNAVAILABLE)
    assert len(transport.requests) == 1


# --------------------------------------------------------------------------
# The upload request (5.3, 5.4, 7.8)
# --------------------------------------------------------------------------


def test_not_found_without_uploads_is_the_code_and_one_request(
    tmp_path: Path,
) -> None:
    result, transport = _publish(
        [_ok("not_found")], _request(fit=_fit_file(tmp_path)), upload=False
    )
    assert result == PublishResult(PublishCode.NOT_FOUND)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "answer",
    [
        _ok("posted"),
        _ok("ambiguous"),
        _ok("rejected"),
        _answer(RelayCode.OK),
        _answer(RelayCode.UNAVAILABLE),
        _answer(RelayCode.RELAY_FAILURE),
        _answer(RelayCode.TOKEN_UNKNOWN),
        _answer(RelayCode.UNAVAILABLE, "not_found"),
        _answer(RelayCode.RELAY_FAILURE, "not_found"),
        _answer(RelayCode.TOKEN_UNKNOWN, "not_found"),
        _gateway(),
        HttpResponse(status=200, headers={}, body=b"not an envelope"),
        TransportError("down"),
    ],
)
def test_no_upload_follows_any_answer_but_a_definite_not_found(
    answer: HttpResponse | TransportError, tmp_path: Path
) -> None:
    _, transport = _publish([answer], _request(fit=_fit_file(tmp_path)), upload=True)
    assert [r.url for r in transport.requests] == [_PUBLISH_URL]


@pytest.mark.parametrize(
    "code", [RelayCode.UNAVAILABLE, RelayCode.RELAY_FAILURE, RelayCode.TOKEN_UNKNOWN]
)
def test_a_not_found_outcome_beside_a_failed_code_is_that_codes_row(
    code: RelayCode, tmp_path: Path
) -> None:
    row = next(r for r in _ROWS if r[0] is code)
    result, transport = _publish(
        [_answer(code, "not_found")], _request(fit=_fit_file(tmp_path)), upload=True
    )
    assert result.code is row[1]
    assert [r.url for r in transport.requests] == [_PUBLISH_URL]


def test_the_upload_request_carries_the_facts_and_the_file_in_base64(
    tmp_path: Path,
) -> None:
    data = _fit(extra=7)
    result, transport = _publish(
        [_ok("not_found"), _ok("uploaded", {"link": "https://s.example/a/1"})],
        _request(fit=_fit_file(tmp_path, data)),
        upload=True,
    )
    assert result == PublishResult(PublishCode.UPLOADED, "https://s.example/a/1")
    assert [r.url for r in transport.requests] == [_PUBLISH_URL, _UPLOAD_URL]
    upload = transport.requests[1]
    assert upload.method == "POST"
    assert upload.single_attempt is True
    assert {k: v.reveal() for k, v in upload.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }
    assert _body(upload) == {
        "publication_id": _ID,
        "sport": "Run",
        "start": "2026-03-04T07:05:00+02:00",
        "elapsed_s": 3725.5,
        "distance_m": 12500.25,
        "title": "Morning Run",
        "description": "Distance: 12.50 km\nTime: 58:20",
        "fit": base64.b64encode(data).decode("ascii"),
    }
    assert len(data) == 12 + 12 + 7


def test_the_upload_passes_the_larger_request_bound(tmp_path: Path) -> None:
    # A 10 MiB file encodes to well over the default request bound (65,536
    # bytes) and well under the upload bound.
    path = _sparse_fit(tmp_path, 10 * 1024 * 1024)
    result, transport = _publish(
        [_ok("not_found"), _ok("uploaded")], _request(fit=path), upload=True
    )
    assert result.code is PublishCode.UPLOADED
    size = len(transport.requests[1].body or b"")
    assert 65_536 < size < MAX_UPLOAD_REQUEST_BYTES


def test_the_largest_valid_upload_body_fits_the_upload_bound(
    tmp_path: Path,
) -> None:
    path = _sparse_fit(tmp_path, MAX_FIT_BYTES)
    assert path.stat().st_size == MAX_FIT_BYTES == 16 * 1024 * 1024
    four_byte = "\U0001f600"
    assert len(four_byte.encode("utf-8")) == 4
    request = _request(
        fit=path,
        title=four_byte * MAX_TITLE_CHARS,
        description=four_byte * MAX_DESCRIPTION_CHARS,
        elapsed_s=1.7976931348623157e308,
        distance_m=1.7976931348623157e308,
    )
    result, transport = _publish(
        [_ok("not_found"), _ok("uploaded")], request, upload=True
    )
    assert result.code is PublishCode.UPLOADED
    size = len(transport.requests[1].body or b"")
    base64_chars = 4 * ((MAX_FIT_BYTES + 2) // 3)
    text_bytes = 4 * (MAX_TITLE_CHARS + MAX_DESCRIPTION_CHARS)
    assert size > base64_chars + text_bytes
    assert size <= MAX_UPLOAD_REQUEST_BYTES
    assert MAX_UPLOAD_REQUEST_BYTES - size > 500_000


# --------------------------------------------------------------------------
# The file checks (5.4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["none", "missing", "directory"])
def test_an_absent_file_is_activity_file_missing_with_no_upload(
    which: str, tmp_path: Path
) -> None:
    fit: Path | None
    if which == "none":
        fit = None
    elif which == "missing":
        fit = tmp_path / "gone.fit"
    else:
        fit = tmp_path
    result, transport = _publish([_ok("not_found")], _request(fit=fit), upload=True)
    assert result == PublishResult(PublishCode.ACTIVITY_FILE_MISSING)
    assert [r.url for r in transport.requests] == [_PUBLISH_URL]


def test_an_unreadable_file_is_activity_file_missing(tmp_path: Path) -> None:
    path = _fit_file(tmp_path)
    path.chmod(0)
    try:
        result, transport = _publish(
            [_ok("not_found")], _request(fit=path), upload=True
        )
    finally:
        path.chmod(0o600)
    assert result == PublishResult(PublishCode.ACTIVITY_FILE_MISSING)
    assert len(transport.requests) == 1


def test_a_file_over_the_cap_is_rejected_unsent(tmp_path: Path) -> None:
    path = _sparse_fit(tmp_path, MAX_FIT_BYTES + 1)
    result, transport = _publish([_ok("not_found")], _request(fit=path), upload=True)
    assert result == PublishResult(PublishCode.REJECTED)
    assert [r.url for r in transport.requests] == [_PUBLISH_URL]


def test_a_file_exactly_at_the_cap_is_sent(tmp_path: Path) -> None:
    path = _sparse_fit(tmp_path, MAX_FIT_BYTES)
    result, transport = _publish(
        [_ok("not_found"), _ok("uploaded")], _request(fit=path), upload=True
    )
    assert result.code is PublishCode.UPLOADED
    assert len(transport.requests) == 2


def test_a_file_that_is_not_a_fit_file_is_rejected_unsent(tmp_path: Path) -> None:
    path = _fit_file(tmp_path, b"this is plainly not a FIT file")
    result, transport = _publish([_ok("not_found")], _request(fit=path), upload=True)
    assert result == PublishResult(PublishCode.REJECTED)
    assert len(transport.requests) == 1


def test_the_file_is_not_read_when_the_publish_answer_is_not_not_found(
    tmp_path: Path,
) -> None:
    # An absent file only matters after not_found.
    result, transport = _publish(
        [_ok("posted")], _request(fit=tmp_path / "gone.fit"), upload=True
    )
    assert result.code is PublishCode.POSTED
    assert len(transport.requests) == 1


# --------------------------------------------------------------------------
# The link (5.8, 5.9, 5.10)
# --------------------------------------------------------------------------

_LANDED_CALLS = (
    pytest.param("posted", False, id="posted-on-publish"),
    pytest.param("uploaded", True, id="uploaded-on-upload"),
)


def _landed(
    outcome: str,
    via_upload: bool,
    data: Mapping[str, object],
    tmp_path: Path,
    *,
    url: str = _BASE,
    request: PublishRequest | None = None,
) -> PublishResult:
    if via_upload:
        result, _ = _publish(
            [_ok("not_found"), _ok(outcome, data)],
            replace(request or _request(), subject=_with_fit(tmp_path)),
            upload=True,
            url=url,
        )
    else:
        result, _ = _publish([_ok(outcome, data)], request or _request(), url=url)
    return result


def _with_fit(tmp_path: Path) -> CompletedActivity:
    return replace(_request().subject, base_fit=_fit_file(tmp_path))


@pytest.mark.parametrize(("outcome", "via_upload"), _LANDED_CALLS)
def test_a_string_link_is_the_link(
    outcome: str, via_upload: bool, tmp_path: Path
) -> None:
    result = _landed(outcome, via_upload, {"link": "https://s.example/a/9"}, tmp_path)
    assert result.link == "https://s.example/a/9"


@pytest.mark.parametrize(("outcome", "via_upload"), _LANDED_CALLS)
def test_an_answer_without_the_link_field_gives_no_link(
    outcome: str, via_upload: bool, tmp_path: Path
) -> None:
    result = _landed(
        outcome,
        via_upload,
        {},
        tmp_path,
        url=_BASE + "/api",
        request=_request(recorded_link="https://old.example/recorded"),
    )
    assert result.code is PublishCode(outcome)
    assert result.link is None


def test_the_link_of_a_reply_is_its_string_field_and_otherwise_none() -> None:
    def reply(data: dict[str, object]) -> RelayReply:
        return RelayReply(
            code=RelayCode.OK, data=data, outcome="posted", retry_after_s=None
        )

    assert _link(reply({"link": "https://s.example/a/9"})) == "https://s.example/a/9"
    assert _link(reply({})) is None
    assert _link(reply({"other": "https://s.example/a/9"})) is None


@pytest.mark.parametrize("value", [5, None, ["x"], {"a": "b"}, True, 1.5])
@pytest.mark.parametrize(("outcome", "via_upload"), _LANDED_CALLS)
def test_a_link_that_is_not_a_string_is_no_link(
    outcome: str, via_upload: bool, value: object, tmp_path: Path
) -> None:
    result = _landed(outcome, via_upload, {"link": value}, tmp_path)
    assert result.code in {PublishCode.POSTED, PublishCode.UPLOADED}
    assert result.link is None


@pytest.mark.parametrize(
    "outcome",
    ["ambiguous", "not_updatable", "not_found", "rejected", "unavailable"],
)
def test_no_code_but_a_landed_one_carries_a_link(outcome: str) -> None:
    result, _ = _publish([_ok(outcome, {"link": "https://s.example/a/9"})])
    assert result.code is PublishCode(outcome)
    assert result.link is None


def test_a_non_landed_upload_answer_carries_no_link(tmp_path: Path) -> None:
    result, _ = _publish(
        [_ok("not_found"), _ok("unconfirmed", {"link": "https://s.example/a/9"})],
        _request(fit=_fit_file(tmp_path)),
        upload=True,
    )
    assert result == PublishResult(PublishCode.UNCONFIRMED)


def test_a_non_https_link_from_the_relay_is_refused_by_publish_core(
    tmp_path: Path,
) -> None:
    loopback = "http://localhost:8765/activities/9"
    refused = _run_through_the_engine(tmp_path / "refused", loopback)
    assert refused.code is PublishCode.POSTED
    assert refused.link is None
    assert refused.link_refused is True
    assert "View on Strava" not in refused.region
    assert refused.requests == 1

    link = "https://www.strava.com/activities/9"
    kept = _run_through_the_engine(tmp_path / "kept", link)
    assert kept.code is PublishCode.POSTED
    assert kept.link == link
    assert kept.link_refused is False
    assert f"[View on Strava]({link})" in kept.region


class _EngineOutcome:
    def __init__(
        self,
        code: PublishCode,
        link: str | None,
        link_refused: bool,
        region: str,
        requests: int,
    ) -> None:
        self.code = code
        self.link = link
        self.link_refused = link_refused
        self.region = region
        self.requests = requests


def _run_through_the_engine(root: Path, link: str) -> _EngineOutcome:
    root.mkdir()
    env = Env(root)
    page = env.write("a.md")
    transport = FakeTransport([_ok("posted", {"link": link})])
    session = _session(transport)
    connector = StravaConnector()

    def open_target(name: str) -> TargetChannel:
        return TargetChannel(
            name=name,
            label=connector.link_label,
            publisher=connector,
            session=session,
        )

    plan = env.plan(configured=("alpha",), posting=True)
    report = run_publish(
        plan,
        open_target=open_target,
        now=lambda: ENGINE_CLOCK,
        mint_id=lambda: _id(901),
    )
    (row,) = report.rows
    region = extract_regions(page.read_text(encoding="utf-8"))["published"]
    return _EngineOutcome(
        row.code, row.link, row.link_refused, region, len(transport.requests)
    )


# --------------------------------------------------------------------------
# Registration (1.1, 1.7)
# --------------------------------------------------------------------------


def test_strava_is_registered_as_a_publish_target_with_its_label() -> None:
    connector = registry.get("strava")
    assert isinstance(connector, StravaConnector)
    publisher: PostPublisher = connector  # the type checker pins the shape
    assert callable(publisher.publish)
    assert connector.link_label == "View on Strava"
    assert valid_label(connector.link_label)
    assert [c.connector_id for c in registry.available()] == [
        "folder",
        "intervals",
        "relay",
        "strava",
    ]


def test_the_connector_is_internal_not_a_published_name() -> None:
    assert "StravaConnector" not in connectors_package.__all__
    assert len(connectors_package.__all__) == 67
