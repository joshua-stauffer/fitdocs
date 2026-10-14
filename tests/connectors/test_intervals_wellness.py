"""Wellness listing windows, opaque records, revisions and failure mapping."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from fitdocs.connectors import intervals
from fitdocs.connectors.credentials import ResolvedCredentials
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.http import CallMode, HttpClient, HttpResponse
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    TokenSet,
    WellnessListing,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from tests.connectors.conftest import FakeTransport
from tests.fixtures import builder

_KEY = "ik-synthetic-7Q2x9"
_TOKEN = base64.b64encode(f"API_KEY:{_KEY}".encode()).decode()
_BASIC = f"Basic {_TOKEN}"
_CLOCK = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(
    seconds=builder.FIT_TIMESTAMP_BASE
)
_DAY = _CLOCK.date()


class _Credentials:
    def __init__(self, secret: Secret) -> None:
        self.secret = secret
        self.fields: list[str] = []

    def value(self, field: str) -> Secret:
        self.fields.append(field)
        assert field == "api_key"
        return self.secret

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("listing cannot replace credentials")


def _session(
    tmp_path: Path, transport: FakeTransport, now: datetime = _CLOCK
) -> ConnectorSession:
    redactor = Redactor()
    key = Secret(_KEY)
    redactor.add(key)
    return ConnectorSession(
        instance="intervals",
        settings=intervals.IntervalsSettings(sources=intervals.DEFAULT_SOURCES),
        http=HttpClient(
            transport, mode=CallMode.DATA, redactor=redactor, sleep=lambda _: None
        ),
        credentials=_Credentials(key),
        data_root=tmp_path,
        now=lambda: now,
        sleep=lambda _: None,
        redactor=redactor,
    )


def _ok(payload: object) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps(payload, ensure_ascii=False).encode())


def _run(
    tmp_path: Path,
    payload: object,
    *,
    oldest: date | None = _DAY,
    now: datetime = _CLOCK,
) -> tuple[WellnessListing, FakeTransport]:
    transport = FakeTransport([_ok(payload)] * 32)
    return intervals.IntervalsConnector().list_wellness(
        _session(tmp_path, transport, now), oldest
    ), transport


def _listing_failure(session: ConnectorSession, oldest: date) -> Exception | None:
    try:
        intervals.IntervalsConnector().list_wellness(session, oldest)
    except Exception as failure:
        return failure
    return None


def test_listing_selects_the_api_key_field(tmp_path: Path) -> None:
    transport = FakeTransport([_ok([])])
    session = _session(tmp_path, transport)
    credentials = _Credentials(session.secret(_KEY))
    before = tuple(credentials.fields)
    _listing_failure(replace(session, credentials=credentials), _DAY)
    assert (before, tuple(credentials.fields)) == ((), ("api_key",))


@pytest.fixture
def _real_credentials_listing(
    tmp_path: Path,
) -> tuple[WellnessListing | Exception, FakeTransport]:
    transport = FakeTransport([_ok([])])
    credentials = ResolvedCredentials(
        connector_id="intervals",
        auth_style=AuthStyle.API_KEY,
        values={"api_key": Secret(_KEY)},
        expires_at=None,
        scopes=None,
        store=None,
        instance_name="intervals",
    )
    session = replace(_session(tmp_path, transport), credentials=credentials)
    result: WellnessListing | Exception
    try:
        result = intervals.IntervalsConnector().list_wellness(session, _DAY)
    except Exception as failure:
        result = failure
    return result, transport


def test_real_api_key_credentials_return_a_listing(
    _real_credentials_listing: tuple[WellnessListing | Exception, FakeTransport],
) -> None:
    result, _ = _real_credentials_listing
    assert isinstance(result, WellnessListing), repr(result)


def test_real_api_key_credentials_request_wellness(
    _real_credentials_listing: tuple[WellnessListing | Exception, FakeTransport],
) -> None:
    _, transport = _real_credentials_listing
    assert [(r.method, r.url) for r in transport.requests] == [
        (
            "GET",
            f"{intervals.API_BASE}/athlete/0/wellness?oldest=2021-09-07&newest=2021-09-09",
        )
    ]


def test_empty_listing_has_no_days(tmp_path: Path) -> None:
    listing, _ = _run(tmp_path, [])
    assert listing.days == ()


@pytest.mark.parametrize("span", [0, 1, 364, 365, 729, 730, 1096])
def test_windows_exact_shape(span: int) -> None:
    end = _DAY + timedelta(days=span)
    first = _DAY - timedelta(days=1)
    expected = [
        (first + timedelta(days=n), min(first + timedelta(days=n + 366), end))
        for n in range(0, span + 1, 365)
    ]
    assert intervals._wellness_windows(_DAY, end) == expected


@pytest.mark.parametrize("span", [0, 1, 729, 1096])
def test_windows_cover_every_date_with_bounded_spans(span: int) -> None:
    end = _DAY + timedelta(days=span)
    windows = intervals._wellness_windows(_DAY, end)
    assert all(
        any(lo <= _DAY + timedelta(days=n) <= hi for lo, hi in windows)
        for n in range(-1, span + 1)
    )


def test_no_window_exceeds_366_days() -> None:
    windows = intervals._wellness_windows(_DAY, _DAY + timedelta(days=1096))
    assert max((hi - lo).days for lo, hi in windows) <= 366


@pytest.mark.parametrize(
    "inclusive_oldest,inclusive_newest",
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_window_overlap_covers_inner_dates(
    inclusive_oldest: bool, inclusive_newest: bool
) -> None:
    end = _DAY + timedelta(days=1096)
    windows = intervals._wellness_windows(_DAY, end)
    assert all(
        any(
            (lo <= day if inclusive_oldest else lo < day)
            and (day <= hi if inclusive_newest else day < hi)
            for lo, hi in windows
        )
        for day in (_DAY + timedelta(days=n) for n in range(1096))
    )


@pytest.mark.parametrize(
    "field,expected", [("oldest", date(2010, 1, 1)), ("newest", date(2021, 9, 9))]
)
def test_default_logical_coverage(tmp_path: Path, field: str, expected: date) -> None:
    listing, _ = _run(tmp_path, [], oldest=None)
    assert getattr(listing, field) == expected


def test_default_first_request_widens_history_start(tmp_path: Path) -> None:
    _, transport = _run(tmp_path, [], oldest=None)
    assert parse_qs(urlsplit(transport.requests[0].url).query)["oldest"] == [
        "2009-12-31"
    ]


def test_default_final_request_ends_utc_tomorrow(tmp_path: Path) -> None:
    _, transport = _run(tmp_path, [], oldest=None)
    assert parse_qs(urlsplit(transport.requests[-1].url).query)["newest"] == [
        "2021-09-09"
    ]


def test_one_get_per_window_and_exact_path_query(tmp_path: Path) -> None:
    _, transport = _run(tmp_path, [], oldest=_DAY - timedelta(days=729))
    assert [(r.method, r.url) for r in transport.requests] == [
        (
            "GET",
            f"{intervals.API_BASE}/athlete/0/wellness?oldest=2019-09-09&newest=2020-09-09",
        ),
        (
            "GET",
            f"{intervals.API_BASE}/athlete/0/wellness?oldest=2020-09-08&newest=2021-09-09",
        ),
        (
            "GET",
            f"{intervals.API_BASE}/athlete/0/wellness?oldest=2021-09-08&newest=2021-09-09",
        ),
    ]


@pytest.mark.parametrize(
    "offset,hour,day,expected",
    [(14, 0, 8, date(2021, 9, 8)), (-7, 23, 8, date(2021, 9, 10))],
)
def test_now_is_converted_to_utc(
    tmp_path: Path, offset: int, hour: int, day: int, expected: date
) -> None:
    now = datetime(2021, 9, day, hour, tzinfo=timezone(timedelta(hours=offset)))
    listing, _ = _run(tmp_path, [], oldest=_DAY - timedelta(days=1), now=now)
    assert listing.newest == expected


def test_future_oldest_is_clamped(tmp_path: Path) -> None:
    listing, _ = _run(tmp_path, [], oldest=_DAY + timedelta(days=30))
    assert listing.oldest == date(2021, 9, 9)


def test_future_oldest_still_requests_one_widened_day(tmp_path: Path) -> None:
    _, transport = _run(tmp_path, [], oldest=_DAY + timedelta(days=30))
    assert [r.url for r in transport.requests] == [
        f"{intervals.API_BASE}/athlete/0/wellness?oldest=2021-09-08&newest=2021-09-09"
    ]


def test_basic_auth_value_is_exact_secret_header(tmp_path: Path) -> None:
    _, transport = _run(tmp_path, [])
    assert transport.requests[0].secret_headers["Authorization"].reveal() == _BASIC


def test_authorization_is_absent_from_public_headers(tmp_path: Path) -> None:
    _, transport = _run(tmp_path, [])
    assert "Authorization" not in transport.requests[0].headers


@pytest.mark.parametrize(
    "secret", [_KEY, _TOKEN, _BASIC], ids=["key", "token", "basic"]
)
def test_no_secret_in_request_addresses(tmp_path: Path, secret: str) -> None:
    _, transport = _run(tmp_path, [], oldest=None)
    assert all(secret not in request.url for request in transport.requests)


def test_dates_sorted_without_sorting_by_revision_or_value(tmp_path: Path) -> None:
    records = [
        {"id": "2021-09-08", "updated": "c-revision", "weight": 12},
        {"id": "2021-09-06", "updated": "z-revision", "weight": 91},
        {"id": "2021-09-07", "updated": "a-revision", "weight": 37},
    ]
    before = copy.deepcopy(records)
    assert [r["id"] for r in before] != sorted(str(r["id"]) for r in before)
    listing, _ = _run(tmp_path, records, oldest=_DAY - timedelta(days=2))
    assert [(d.day.isoformat(), d.revision) for d in listing.days] == [
        ("2021-09-06", "z-revision"),
        ("2021-09-07", "a-revision"),
        ("2021-09-08", "c-revision"),
    ]


def test_earlier_window_duplicate_wins(tmp_path: Path) -> None:
    first = {"id": "2021-09-08", "updated": "earlier-z", "weight": 77}
    later = {"id": "2021-09-08", "updated": "later-a", "weight": 23}
    assert first != later
    transport = FakeTransport([_ok([first]), _ok([later])])
    listing = intervals.IntervalsConnector().list_wellness(
        _session(tmp_path, transport), _DAY - timedelta(days=365)
    )
    assert [(d.day, d.revision, d.record) for d in listing.days] == [
        (_DAY, "earlier-z", first)
    ]


@pytest.mark.parametrize("updated", ["2021-09-09T00:31:42Z", " opaque revision ", " "])
def test_nonempty_text_updated_preserved_exactly(tmp_path: Path, updated: str) -> None:
    listing, _ = _run(tmp_path, [{"id": _DAY.isoformat(), "updated": updated}])
    assert listing.days[0].revision == updated


@pytest.mark.parametrize("updated", [None, 194, True, "", [], {"nested": 71}])
def test_nontext_or_empty_updated_uses_whole_content_hash(
    tmp_path: Path, updated: object
) -> None:
    record = {
        "id": _DAY.isoformat(),
        "updated": updated,
        "weight": {"hostile": [None, "é", 73]},
    }
    expected = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    listing, _ = _run(tmp_path, [record])
    assert listing.days[0].revision == expected


def test_absent_updated_uses_content_hash(tmp_path: Path) -> None:
    listing, _ = _run(tmp_path, [{"id": _DAY.isoformat(), "x": "ñ"}])
    assert (
        listing.days[0].revision
        == "sha256:" + hashlib.sha256(b'{"id":"2021-09-08","x":"\xc3\xb1"}').hexdigest()
    )


def test_content_revision_is_independent_of_nested_key_order() -> None:
    left: dict[str, object] = {"z": {"b": 97, "a": "é"}, "id": "2021-09-08"}
    right: dict[str, object] = {"id": "2021-09-08", "z": {"a": "é", "b": 97}}
    assert list(left) != list(right)
    assert intervals._content_revision(left) == intervals._content_revision(right)


def test_content_revision_changes_with_arbitrary_field() -> None:
    left: dict[str, object] = {"id": "2021-09-08", "unused": {"value": 81}}
    right: dict[str, object] = {"id": "2021-09-08", "unused": {"value": 82}}
    assert intervals._content_revision(left) != intervals._content_revision(right)


def test_hostile_other_fields_retained_without_changes(tmp_path: Path) -> None:
    record = {
        "id": _DAY.isoformat(),
        "updated": "keep-record",
        "ctl": [None, {}],
        "atl": "hostile",
        "rampRate": False,
        "ctlLoad": {"x": [19]},
        "atlLoad": None,
        "sportInfo": ["é", 53],
        "weight": {"bad": True},
    }
    before = copy.deepcopy(record)
    listing, _ = _run(tmp_path, [record])
    assert listing.days[0].record == before


def test_only_id_and_updated_are_read_and_object_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class GuardedDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            if key not in ("id", "updated"):
                raise AssertionError(f"read opaque field {key}")
            return super().get(key, default)

    record = GuardedDict(
        id=_DAY.isoformat(), updated="opaque", ctl={"arbitrary": [None, 44]}
    )
    monkeypatch.setattr(json, "loads", lambda _: [record])
    listing, _ = _run(tmp_path, [])
    assert listing.days[0].record is record


@pytest.mark.parametrize(
    "body,problem",
    [
        (b"{", "the body is not valid JSON"),
        (b"\xff", "the body is not valid JSON"),
        (b"{}", "the body is not a JSON array"),
        (b"null", "the body is not a JSON array"),
        (b"3", "the body is not a JSON array"),
    ],
)
def test_malformed_body_refused(tmp_path: Path, body: bytes, problem: str) -> None:
    transport = FakeTransport([HttpResponse(200, {}, body)])
    failure = _listing_failure(_session(tmp_path, transport), _DAY)
    assert (
        isinstance(failure, ConnectorError)
        and str(failure)
        == "intervals.icu's wellness listing is not in its documented form: " + problem
    )


@pytest.mark.parametrize(
    "entry,problem",
    [
        (None, "not an object"),
        (31, "not an object"),
        ([], "not an object"),
        ({}, "no YYYY-MM-DD id"),
        ({"id": None}, "no YYYY-MM-DD id"),
        ({"id": 17}, "no YYYY-MM-DD id"),
        ({"id": ""}, "no YYYY-MM-DD id"),
        ({"id": "2026-1-5"}, "no YYYY-MM-DD id"),
        ({"id": "20210908"}, "no YYYY-MM-DD id"),
        ({"id": "2021-W36-3"}, "no YYYY-MM-DD id"),
        ({"id": "2026-02-30"}, "invalid calendar date"),
        ({"id": "0000-01-01"}, "invalid calendar date"),
    ],
)
def test_malformed_entry_names_window_relative_index(
    tmp_path: Path, entry: object, problem: str
) -> None:
    transport = FakeTransport(
        [_ok([]), _ok([{"id": "2021-09-06", "updated": "index-control"}, entry])]
    )
    failure = _listing_failure(
        _session(tmp_path, transport), _DAY - timedelta(days=365)
    )
    detail = "is not an object" if problem == "not an object" else "has " + problem
    assert (
        isinstance(failure, ConnectorError)
        and str(failure)
        == "intervals.icu's wellness listing is not in its documented form: entry 1 "
        + detail
    )


def _status(
    tmp_path: Path, status: int, body: bytes = b"service-sentinel"
) -> tuple[Exception, FakeTransport]:
    transport = FakeTransport([HttpResponse(status, {}, body)] * 8)
    try:
        intervals.IntervalsConnector().list_wellness(
            _session(tmp_path, transport), _DAY
        )
    except (ConnectorError, AuthFailure) as failure:
        return failure, transport
    raise AssertionError("non200 status accepted")


def test_401_is_rejected_auth_failure(tmp_path: Path) -> None:
    failure, _ = _status(tmp_path, 401)
    assert isinstance(failure, AuthFailure) and failure.kind is AuthFailureKind.REJECTED


@pytest.mark.parametrize("status", [401, 403])
def test_rejections_are_not_retried(tmp_path: Path, status: int) -> None:
    _, transport = _status(tmp_path, status)
    assert len(transport.requests) == 1


def test_403_is_connector_error_with_garmin_remedies(tmp_path: Path) -> None:
    failure, _ = _status(tmp_path, 403)
    assert isinstance(failure, ConnectorError) and str(failure) == (
        "intervals.icu refused the wellness listing (HTTP 403): service-sentinel. "
        "intervals.icu may be withholding data it received from Garmin. "
        "Set wellness = false in this instance's table to stop requesting wellness; "
        "Garmin's own data export is the route for Garmin wellness "
        "(see the wellness guide)."
    )


@pytest.mark.parametrize("status", [429, 500, 503, 599])
def test_retryable_status_messages(tmp_path: Path, status: int) -> None:
    failure, _ = _status(tmp_path, status)
    expected = (
        "intervals.icu is limiting requests (HTTP 429) and still was after "
        "fitdocs's retries; this pull stopped, and the next pull resumes "
        "where it stopped"
        if status == 429
        else f"intervals.icu is unavailable (HTTP {status}) after fitdocs's "
        "retries; this pull stopped, and the next pull resumes where it stopped"
    )
    assert isinstance(failure, ConnectorError) and str(failure) == expected


@pytest.mark.parametrize("status", [429, 500, 503])
def test_existing_client_retries_are_exhausted(tmp_path: Path, status: int) -> None:
    _, transport = _status(tmp_path, status)
    assert len(transport.requests) == 3


@pytest.mark.parametrize("status", [204, 302, 404, 499, 600])
def test_other_status_names_status_and_request(tmp_path: Path, status: int) -> None:
    failure, _ = _status(tmp_path, status)
    assert (
        isinstance(failure, ConnectorError)
        and str(failure)
        == f"intervals.icu answered the wellness listing with HTTP {status}: "
        "service-sentinel"
    )


@pytest.mark.parametrize(
    "request_name", ["wellness listing", "athlete settings request"]
)
def test_status_helper_preserves_request_context(
    tmp_path: Path, request_name: str
) -> None:
    transport = FakeTransport([])
    with pytest.raises(ConnectorError) as failure:
        intervals._raise_for_wellness_status(
            _session(tmp_path, transport),
            HttpResponse(404, {}, b"request-control"),
            request=request_name,
        )
    assert (
        str(failure.value)
        == f"intervals.icu answered the {request_name} with HTTP 404: request-control"
    )


@pytest.mark.parametrize("status", [401, 403, 404])
@pytest.mark.parametrize(
    "secret", [_KEY, _TOKEN, _BASIC], ids=["key", "token", "basic"]
)
def test_service_echo_cannot_expose_secrets(
    tmp_path: Path, status: int, secret: str
) -> None:
    failure, _ = _status(
        tmp_path, status, f"echo {_KEY} {_TOKEN} {_BASIC} tail".encode()
    )
    assert secret not in str(failure)


def test_service_echo_redaction_and_whitespace_are_visible(tmp_path: Path) -> None:
    failure, _ = _status(
        tmp_path, 404, f"  before\n{_KEY}\t{_BASIC} {_TOKEN}  after  ".encode()
    )
    assert (
        str(failure)
        == "intervals.icu answered the wellness listing with HTTP 404: before "
        f"{REDACTED} {REDACTED} {REDACTED} after"
    )


def test_service_message_is_bounded(tmp_path: Path) -> None:
    failure, _ = _status(tmp_path, 404, b"Z" * 301 + b"tail-sentinel")
    assert (
        str(failure)
        == "intervals.icu answered the wellness listing with HTTP 404: " + "Z" * 300
    )


def test_empty_service_message_uses_status(tmp_path: Path) -> None:
    failure, _ = _status(tmp_path, 404, b" \n\t")
    assert (
        str(failure)
        == "intervals.icu answered the wellness listing with HTTP 404: HTTP 404"
    )


@pytest.mark.parametrize(
    "updated",
    [
        pytest.param(None, id="null"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(194, id="positive-integer"),
        pytest.param(0, id="zero-integer"),
        pytest.param(-1, id="negative-integer"),
        pytest.param(2**64, id="large-integer"),
        pytest.param(0.5, id="positive-fraction"),
        pytest.param(-1.25, id="negative-fraction"),
        pytest.param(0.0, id="positive-zero"),
        pytest.param(-0.0, id="negative-zero"),
        pytest.param(1e100, id="exponent-float"),
        pytest.param("", id="empty-text"),
        pytest.param([], id="empty-array"),
        pytest.param({}, id="empty-object"),
        pytest.param({"nested": 71}, id="nested-object"),
    ],
)
def test_updated_json_types_have_exact_content_revisions(
    tmp_path: Path, updated: object
) -> None:
    record = {"id": _DAY.isoformat(), "updated": updated, "weight": 67}
    expected = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
    )
    listing, _ = _run(tmp_path, [record])
    assert listing.days[0].revision == expected


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="null"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(194, id="positive-integer"),
        pytest.param(0, id="zero-integer"),
        pytest.param(-1, id="negative-integer"),
        pytest.param(0.5, id="fraction"),
        pytest.param(0.0, id="zero-float"),
        pytest.param("", id="empty-text"),
        pytest.param("opaque", id="text"),
        pytest.param({}, id="object"),
    ],
)
def test_json_body_type_errors_are_exact(tmp_path: Path, payload: object) -> None:
    transport = FakeTransport([_ok(payload)])
    failure = _listing_failure(_session(tmp_path, transport), _DAY)
    assert (
        isinstance(failure, ConnectorError)
        and str(failure)
        == "intervals.icu's wellness listing is not in its documented form: "
        "the body is not a JSON array"
    )


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(None, id="null"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(194, id="positive-integer"),
        pytest.param(0, id="zero-integer"),
        pytest.param(-1, id="negative-integer"),
        pytest.param(0.5, id="fraction"),
        pytest.param(0.0, id="zero-float"),
        pytest.param("", id="empty-text"),
        pytest.param("opaque", id="text"),
        pytest.param([], id="array"),
    ],
)
def test_json_entry_type_errors_are_exact(tmp_path: Path, entry: object) -> None:
    transport = FakeTransport([_ok([entry])])
    failure = _listing_failure(_session(tmp_path, transport), _DAY)
    assert (
        isinstance(failure, ConnectorError)
        and str(failure)
        == "intervals.icu's wellness listing is not in its documented form: "
        "entry 0 is not an object"
    )


@pytest.mark.parametrize(
    "id_value",
    [
        pytest.param(None, id="null"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(194, id="positive-integer"),
        pytest.param(0, id="zero-integer"),
        pytest.param(-1, id="negative-integer"),
        pytest.param(0.5, id="fraction"),
        pytest.param(0.0, id="zero-float"),
        pytest.param([], id="empty-array"),
        pytest.param([71], id="array"),
        pytest.param({}, id="empty-object"),
        pytest.param({"nested": 71}, id="object"),
    ],
)
def test_json_id_type_errors_are_exact(tmp_path: Path, id_value: object) -> None:
    transport = FakeTransport([_ok([{"id": id_value}])])
    failure = _listing_failure(_session(tmp_path, transport), _DAY)
    assert (
        isinstance(failure, ConnectorError)
        and str(failure)
        == "intervals.icu's wellness listing is not in its documented form: "
        "entry 0 has no YYYY-MM-DD id"
    )
