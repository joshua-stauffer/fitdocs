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
    Capability,
    ConnectorSession,
    TokenSet,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.wellness.formats import intervals as wellness_intervals
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.registry import Recognized, recognize
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


# Packaging and the real wellness-store delivery contract.
_JSON_NON_OBJECTS = [
    None,
    True,
    False,
    194,
    0,
    -1,
    0.5,
    0.0,
    -1.25,
    "",
    "text",
    [],
    [71],
]
_JSON_VALUES = [
    None,
    True,
    False,
    194,
    0,
    -1,
    0.5,
    0.0,
    -1.25,
    "",
    "text",
    [],
    [71],
    {},
    {"x": 73},
]


def _chosen(records: list[dict[str, object]]) -> tuple[WellnessDay, ...]:
    return tuple(
        WellnessDay(
            date.fromisoformat(str(record["id"])), str(record.get("updated")), record
        )
        for record in records
    )


def _package(
    tmp_path: Path, athlete: object, records: list[dict[str, object]] | None = None
) -> tuple[WellnessPackage, FakeTransport]:
    transport = FakeTransport([_ok(athlete)])
    chosen = [] if records is None else records
    return intervals.IntervalsConnector().package_wellness(
        _session(tmp_path, transport), _chosen(chosen)
    ), transport


def _package_outcome(
    session: ConnectorSession, days: tuple[WellnessDay, ...] = ()
) -> object:
    try:
        return intervals.IntervalsConnector().package_wellness(session, days)
    except Exception as failure:
        return failure


@pytest.mark.parametrize(
    "name,expected",
    [
        ("WELLNESS_FORMAT", wellness_intervals.FORMAT.id),
        ("WELLNESS_SUFFIX", wellness_intervals.FORMAT.archived_suffix),
        ("WELLNESS_DELIVERY_FORMAT", wellness_intervals.DELIVERY_FORMAT),
        ("WELLNESS_DELIVERY_VERSION", wellness_intervals.DELIVERY_VERSION),
        ("WELLNESS_KEYS_PATTERN", r"^(?:icu_)?([a-z0-9_]+?)_wellness_keys$"),
        (
            "ATHLETE_FORM_MESSAGE",
            "intervals.icu's athlete settings are not in their documented form: "
            "{problem}",
        ),
    ],
)
def test_packaging_public_constant_values(name: str, expected: object) -> None:
    value = getattr(intervals, name)
    assert (type(value), value) == (type(expected), expected)


@pytest.mark.parametrize(
    "name,expected",
    [
        (name, "Final[str]")
        for name in (
            "WELLNESS_FORMAT",
            "WELLNESS_SUFFIX",
            "WELLNESS_DELIVERY_FORMAT",
            "WELLNESS_KEYS_PATTERN",
            "ATHLETE_FORM_MESSAGE",
        )
    ]
    + [("WELLNESS_DELIVERY_VERSION", "Final[int]")],
)
def test_packaging_public_constant_annotations(name: str, expected: str) -> None:
    assert intervals.__annotations__.get(name) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("session", "ConnectorSession"),
        ("days", "tuple[WellnessDay, ...]"),
        ("return", "WellnessPackage"),
    ],
)
def test_package_signature_annotations(name: str, expected: str) -> None:
    assert (
        intervals.IntervalsConnector.package_wellness.__annotations__.get(name)
        == expected
    )


def test_packaging_capabilities_are_exact() -> None:
    assert intervals.IntervalsConnector.capabilities == frozenset(
        {Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS}
    )


@pytest.mark.parametrize("facet", ["data", "suffix", "format", "origins"])
def test_package_golden_and_metadata(tmp_path: Path, facet: str) -> None:
    records: list[dict[str, object]] = [
        {
            "updated": "a-revision",
            "id": "2021-09-08",
            "weight": 37,
            "sportInfo": {"z": "é", "a": [False, None]},
            "ctl": 19,
        },
        {
            "updated": "z-revision",
            "id": "2021-09-06",
            "weight": 91,
            "atl": 23,
            "rampRate": None,
            "ctlLoad": {"z": 7, "a": 3},
            "atlLoad": False,
            "unknown": [],
        },
        {"updated": "m-revision", "id": "2021-09-07", "weight": 12, "restingHR": None},
    ]
    package, _ = _package(
        tmp_path,
        {"garmin_wellness_keys": ["weight"], "oura_wellness_keys": ["restingHR"]},
        records,
    )
    golden = (
        '{"format":"fitdocs.intervals-icu-wellness","origins":{"restingHR":"oura","weight":"garmin"},'
        '"records":[{"atl":23,"atlLoad":false,"ctlLoad":{"a":3,"z":7},"id":"2021-09-06","rampRate":null,"unknown":[],"updated":"z-revision","weight":91},'
        '{"id":"2021-09-07","restingHR":null,"updated":"m-revision","weight":12},'
        '{"ctl":19,"id":"2021-09-08","sportInfo":{"a":[false,null],"z":"é"},"updated":"a-revision","weight":37}],"version":1}\n'
    ).encode()
    expected = {
        "data": golden,
        "suffix": ".json",
        "format": "intervals-icu",
        "origins": frozenset({"garmin", "oura"}),
    }
    assert getattr(package, facet) == expected[facet]


@pytest.mark.parametrize("records", [[], [{"id": "2021-09-08", "weight": 71}]])
def test_package_omits_empty_origins(
    tmp_path: Path, records: list[dict[str, object]]
) -> None:
    package, _ = _package(tmp_path, {}, records)
    assert json.loads(package.data) == {
        "format": "fitdocs.intervals-icu-wellness",
        "version": 1,
        "records": records,
    }


@pytest.mark.parametrize("value", _JSON_VALUES)
def test_package_retains_every_record_value(tmp_path: Path, value: object) -> None:
    records: list[dict[str, object]] = [
        {
            "id": _DAY.isoformat(),
            "ctl": value,
            "atl": value,
            "rampRate": value,
            "ctlLoad": value,
            "atlLoad": value,
            "sportInfo": value,
            "weight": value,
            "unknown": value,
            "nested": {"dict": {"leaf": value}, "list": [value, {"deep": value}]},
        }
    ]
    expected = _canonical_json(records)
    package, _ = _package(
        tmp_path, {"garmin_wellness_keys": ["weight", "absent"]}, records
    )
    assert _canonical_json(json.loads(package.data)["records"]) == expected


def test_package_keeps_input_objects_unmodified(tmp_path: Path) -> None:
    records: list[dict[str, object]] = [
        {
            "id": "2021-09-08",
            "unknown": {
                "z": [73, None, False, True, 0, 1, 0.0, -0.0, 1.0],
                "a": "é",
            },
        }
    ]
    athlete = {"garmin_wellness_keys": ["weight", "weight"], "unrelated": {"z": 97}}
    expected = _canonical_json([records, athlete])
    _package(tmp_path, athlete, records)
    assert _canonical_json([records, athlete]) == expected


def test_package_does_not_read_metric_values(tmp_path: Path) -> None:
    class Record(dict[str, object]):
        def __getitem__(self, key: str) -> object:
            if key != "id":
                raise AssertionError(f"read metric {key}")
            return super().__getitem__(key)

        def get(self, key: str, default: object = None) -> object:
            if key not in ("id", "updated"):
                raise AssertionError(f"read metric {key}")
            return super().get(key, default)

    record = Record(id=_DAY.isoformat(), weight=None, ctl={"opaque": [73]})
    transport = FakeTransport([_ok({"garmin_wellness_keys": ["weight"]})])
    outcome = _package_outcome(
        _session(tmp_path, transport), (WellnessDay(_DAY, "rev", record),)
    )
    assert isinstance(outcome, WellnessPackage), repr(outcome)


@pytest.mark.parametrize("record", _JSON_NON_OBJECTS)
def test_package_rejects_nondict_records(tmp_path: Path, record: object) -> None:
    outcome = _package_outcome(
        _session(tmp_path, FakeTransport([_ok({})])), (WellnessDay(_DAY, None, record),)
    )
    assert (
        isinstance(outcome, ConnectorError)
        and str(outcome) == "intervals.icu's wellness package record 0 is not an object"
    )


@pytest.mark.parametrize(
    "body,problem",
    [(b"{", "the body is not valid JSON"), (b"\xff", "the body is not valid JSON")]
    + [
        (json.dumps(value).encode(), "the body is not a JSON object")
        for value in _JSON_NON_OBJECTS
    ],
)
def test_athlete_body_requires_json_object(
    tmp_path: Path, body: bytes, problem: str
) -> None:
    outcome = _package_outcome(
        _session(tmp_path, FakeTransport([HttpResponse(200, {}, body)]))
    )
    assert (
        isinstance(outcome, ConnectorError)
        and str(outcome)
        == "intervals.icu's athlete settings are not in their documented form: "
        + problem
    )


@pytest.mark.parametrize("athlete", [{}, {"unrelated": 71}])
def test_athlete_object_without_claims_is_valid(
    tmp_path: Path, athlete: dict[str, object]
) -> None:
    outcome = _package_outcome(_session(tmp_path, FakeTransport([_ok(athlete)])))
    assert isinstance(outcome, WellnessPackage), repr(outcome)


def _origins_outcome(
    tmp_path: Path, athlete: object, records: list[dict[str, object]] | None = None
) -> object:
    try:
        package, _ = _package(tmp_path, athlete, records)
        return json.loads(package.data).get("origins", {})
    except Exception as failure:
        return failure


@pytest.mark.parametrize(
    "athlete,expected",
    [
        (
            {"garmin_wellness_keys": ["weight", "restingHR"]},
            {"weight": "garmin", "restingHR": "garmin"},
        ),
        (
            {
                "garmin_wellness_keys": ["weight", "restingHR"],
                "oura_wellness_keys": ["weight", "hrv"],
            },
            {"restingHR": "garmin", "hrv": "oura"},
        ),
        (
            {
                "garmin_wellness_keys": ["weight", "weight"],
                "icu_garmin_wellness_keys": ["weight", "steps"],
            },
            {"weight": "garmin", "steps": "garmin"},
        ),
        (
            {
                "garmin_wellness_keys": ["weight"],
                "oura_wellness_keys": ["weight"],
                "fitbit_wellness_keys": ["weight", "steps"],
            },
            {"steps": "fitbit"},
        ),
        ({"icu_wellness_keys": ["weight"], "icu_icu_wellness_keys": ["hrv"]}, {}),
        (
            {
                "google_fit_wellness_keys": ["weight"],
                "icu_google_fit_wellness_keys": ["hrv"],
            },
            {"weight": "google-fit", "hrv": "google-fit"},
        ),
        ({"123_wellness_keys": ["steps"]}, {"steps": "123"}),
        ({"private_wellness_keys": ["weight"]}, {}),
    ],
)
def test_settings_claim_cardinality_and_platform_names(
    tmp_path: Path, athlete: dict[str, object], expected: dict[str, str]
) -> None:
    origins = _origins_outcome(tmp_path, athlete)
    assert origins == expected


@pytest.mark.parametrize(
    "name",
    [
        "GARMIN",
        "Garmin",
        "",
        "_garmin",
        "garmin_",
        "google__fit",
        "google-fit",
        "garmin!",
        "garminé",
        "garmin wellness",
        "garmin/fit",
    ],
)
def test_invalid_platform_names_make_no_claim(tmp_path: Path, name: str) -> None:
    origins = _origins_outcome(tmp_path, {name + "_wellness_keys": ["weight"]})
    assert origins == {}


@pytest.mark.parametrize(
    "key",
    [
        "garmin_wellness_key",
        "garmin_wellness_keys_extra",
        "garmin_wellness_keys\n",
        "pre.garmin_wellness_keys",
        "garmin_activity_keys",
        "wellness_keys",
    ],
)
def test_unmatched_setting_names_make_no_claim(tmp_path: Path, key: str) -> None:
    origins = _origins_outcome(tmp_path, {key: ["weight"]})
    assert origins == {}


@pytest.mark.parametrize("value", _JSON_VALUES)
def test_only_list_setting_values_create_claims(tmp_path: Path, value: object) -> None:
    origins = _origins_outcome(tmp_path, {"garmin_wellness_keys": value})
    assert origins == {}


@pytest.mark.parametrize("element", _JSON_VALUES)
def test_only_nonempty_string_list_elements_create_claims(
    tmp_path: Path, element: object
) -> None:
    expected = {"text": "garmin"} if isinstance(element, str) and element else {}
    origins = _origins_outcome(tmp_path, {"garmin_wellness_keys": [element]})
    assert origins == expected


@pytest.mark.parametrize("value", _JSON_VALUES)
def test_attribution_uses_settings_without_metric_value_filter(
    tmp_path: Path, value: object
) -> None:
    origins = _origins_outcome(
        tmp_path,
        {"garmin_wellness_keys": ["weight", "missing"]},
        [{"id": _DAY.isoformat(), "weight": value}],
    )
    assert origins == {
        "missing": "garmin",
        "weight": "garmin",
    }


def test_attribution_retains_valid_fields_beside_invalid_elements(
    tmp_path: Path,
) -> None:
    origins = _origins_outcome(
        tmp_path, {"garmin_wellness_keys": [None, 73, False, [], {}, "", "weight", " "]}
    )
    assert origins == {" ": "garmin", "weight": "garmin"}


@pytest.mark.parametrize(
    "facet", ["count", "method_url", "secret", "public", "credential"]
)
def test_athlete_request_contract(tmp_path: Path, facet: str) -> None:
    transport = FakeTransport([_ok({}), _ok({})])
    session = _session(tmp_path, transport)

    class Credentials(_Credentials):
        def value(self, field: str) -> Secret:
            self.fields.append(field)
            return self.secret

    credentials = Credentials(session.secret(_KEY))
    session = replace(session, credentials=credentials)
    for _ in range(2):
        _package_outcome(session)
    observed = {
        "count": len(transport.requests),
        "method_url": [(r.method, r.url) for r in transport.requests],
        "secret": [
            r.secret_headers.get("Authorization", Secret("absent")).reveal()
            for r in transport.requests
        ],
        "public": ["Authorization" in r.headers for r in transport.requests],
        "credential": credentials.fields,
    }
    expected = {
        "count": 2,
        "method_url": [("GET", f"{intervals.API_BASE}/athlete/0")] * 2,
        "secret": [_BASIC] * 2,
        "public": [False, False],
        "credential": ["api_key", "api_key"],
    }
    assert observed[facet] == expected[facet]


def test_package_accepts_actual_api_key_only_credentials(tmp_path: Path) -> None:
    transport = FakeTransport([_ok({})])
    credentials = ResolvedCredentials(
        connector_id="intervals",
        auth_style=AuthStyle.API_KEY,
        values={"api_key": Secret(_KEY)},
        expires_at=None,
        scopes=None,
        store=None,
        instance_name="intervals",
    )
    outcome = _package_outcome(
        replace(_session(tmp_path, transport), credentials=credentials)
    )
    assert isinstance(outcome, WellnessPackage), repr(outcome)


@pytest.mark.parametrize(
    "status", [401, 403, 429, 500, 503, 599, 204, 302, 404, 499, 600]
)
def test_athlete_status_mapping(tmp_path: Path, status: int) -> None:
    transport = FakeTransport([HttpResponse(status, {}, b"service-sentinel")] * 8)
    outcome = _package_outcome(_session(tmp_path, transport))
    expected: tuple[type[Exception], object]
    if status == 401:
        observed = (type(outcome), getattr(outcome, "kind", None))
        expected = (AuthFailure, AuthFailureKind.REJECTED)
    else:
        observed = (type(outcome), str(outcome))
        expected_message = (
            "intervals.icu refused the athlete settings request (HTTP 403): "
            "service-sentinel. intervals.icu may be withholding data it received "
            "from Garmin. Set wellness = false in this instance's table to stop "
            "requesting wellness; Garmin's own data export is the route for Garmin "
            "wellness (see the wellness guide)."
            if status == 403
            else "intervals.icu is limiting requests (HTTP 429) and still was after "
            "fitdocs's retries; this pull stopped, and the next pull resumes "
            "where it stopped"
            if status == 429
            else f"intervals.icu is unavailable (HTTP {status}) after fitdocs's "
            "retries; this pull stopped, and the next pull resumes where it stopped"
            if 500 <= status < 600
            else "intervals.icu answered the athlete settings request "
            f"with HTTP {status}: "
            "service-sentinel"
        )
        expected = (ConnectorError, expected_message)
    assert observed == expected


@pytest.mark.parametrize(
    "status,count",
    [(401, 1), (403, 1), (429, 3), (500, 3), (503, 3), (599, 1), (404, 1), (600, 1)],
)
def test_athlete_request_retry_count(tmp_path: Path, status: int, count: int) -> None:
    transport = FakeTransport([HttpResponse(status, {}, b"retry-control")] * 8)
    _package_outcome(_session(tmp_path, transport))
    assert len(transport.requests) == count


@pytest.mark.parametrize("status", [401, 403, 404])
@pytest.mark.parametrize(
    "secret", [_KEY, _TOKEN, _BASIC], ids=["key", "token", "basic"]
)
def test_athlete_status_redacts_every_credential_form(
    tmp_path: Path, status: int, secret: str
) -> None:
    transport = FakeTransport(
        [HttpResponse(status, {}, f"echo {secret} tail".encode())]
    )
    outcome = _package_outcome(_session(tmp_path, transport))
    message = f"echo {REDACTED} tail"
    expected = (
        (AuthFailure, message)
        if status == 401
        else (
            ConnectorError,
            "intervals.icu refused the athlete settings request (HTTP 403): "
            + message
            + ". intervals.icu may be withholding data it received from Garmin. "
            "Set wellness = false in this instance's table to stop requesting "
            "wellness; Garmin's own data export is the route for Garmin wellness "
            "(see the wellness guide).",
        )
        if status == 403
        else (
            ConnectorError,
            "intervals.icu answered the athlete settings request with HTTP 404: "
            + message,
        )
    )
    assert (type(outcome), str(outcome)) == expected


@pytest.mark.parametrize(
    "facet", ["recognized", "dates", "value", "origin", "computed"]
)
def test_real_wellness_parser_reads_package(tmp_path: Path, facet: str) -> None:
    package, _ = _package(
        tmp_path,
        {"garmin_wellness_keys": ["weight"]},
        [
            {"id": "2021-09-08", "weight": 37, "ctl": 19},
            {"id": "2021-09-06", "weight": 91, "atl": 23},
        ],
    )
    path = tmp_path / "contract.json"
    path.write_bytes(package.data)
    recognition = recognize(CandidateProbe.open(path))
    snapshots: tuple[DaySnapshot, ...] = ()
    if facet != "recognized":
        with path.open("rb") as stream:
            snapshots = tuple(wellness_intervals.FORMAT.parse(stream))
    observed = {
        "recognized": recognition.format.id
        if isinstance(recognition, Recognized)
        else recognition,
        "dates": [s.day for s in snapshots],
        "value": [s.values.get(Metric.WEIGHT_KG) for s in snapshots],
        "origin": [dict(s.origins) for s in snapshots],
        "computed": [set(s.values) for s in snapshots],
    }
    expected = {
        "recognized": "intervals-icu",
        "dates": [date(2021, 9, 6), date(2021, 9, 8)],
        "value": [91.0, 37.0],
        "origin": [{Metric.WEIGHT_KG: "garmin"}] * 2,
        "computed": [{Metric.WEIGHT_KG}] * 2,
    }
    assert observed[facet] == expected[facet]


def test_package_bytes_do_not_depend_on_clock_or_machine(tmp_path: Path) -> None:
    transport = FakeTransport([_ok({}), _ok({})])
    session = _session(tmp_path, transport)
    days = _chosen([{"id": _DAY.isoformat(), "unknown": {"z": 71, "a": "ñ"}}])
    expected = intervals.IntervalsConnector().package_wellness(session, days).data
    second = replace(
        session,
        data_root=tmp_path / "other-machine",
        now=lambda: _CLOCK + timedelta(days=17),
    )
    assert (
        intervals.IntervalsConnector().package_wellness(second, days).data == expected
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _package_listed_records(
    tmp_path: Path, athlete: dict[str, object], records: list[dict[str, object]]
) -> tuple[WellnessPackage, list[object]]:
    transport = FakeTransport([_ok(records), _ok(athlete)])
    session = _session(tmp_path, transport)
    connector = intervals.IntervalsConnector()
    listing = connector.list_wellness(session, _DAY)
    package = connector.package_wellness(session, listing.days)
    return package, [day.record for day in listing.days]


@pytest.mark.parametrize("facet", ["envelope", "metadata"])
@pytest.mark.parametrize(
    "athlete,records,expected_map,expected_platforms",
    [
        pytest.param(
            {"oura_wellness_keys": ["missing"]},
            [{"id": _DAY.isoformat(), "weight": None}],
            {"missing": "oura"},
            frozenset({"oura"}),
            id="absent-only",
        ),
        pytest.param(
            {
                "garmin_wellness_keys": ["weight", "steps"],
                "oura_wellness_keys": ["missing"],
                "fitbit_wellness_keys": ["steps"],
            },
            [{"id": _DAY.isoformat(), "weight": None, "steps": 97}],
            {"weight": "garmin", "missing": "oura"},
            frozenset({"garmin", "oura"}),
            id="mixed-present-absent-ambiguous",
        ),
        pytest.param(
            {"garmin_wellness_keys": ["weight"], "oura_wellness_keys": ["missing"]},
            [],
            {"weight": "garmin", "missing": "oura"},
            frozenset({"garmin", "oura"}),
            id="empty-selected-records",
        ),
        pytest.param(
            {"garmin_wellness_keys": ["weight"], "oura_wellness_keys": ["weight"]},
            [{"id": _DAY.isoformat(), "weight": None}],
            {},
            frozenset(),
            id="ambiguous-only",
        ),
        pytest.param(
            {},
            [{"id": _DAY.isoformat(), "weight": None}],
            {},
            frozenset(),
            id="no-claims",
        ),
    ],
)
def test_listed_package_attribution_has_independent_envelope_and_metadata(
    tmp_path: Path,
    facet: str,
    athlete: dict[str, object],
    records: list[dict[str, object]],
    expected_map: dict[str, str],
    expected_platforms: frozenset[str],
) -> None:
    expected: tuple[type[object], object] = (
        (dict, copy.deepcopy(expected_map))
        if facet == "envelope"
        else (frozenset, expected_platforms)
    )
    package, _ = _package_listed_records(tmp_path, athlete, records)
    observed = (
        json.loads(package.data).get("origins", {})
        if facet == "envelope"
        else package.origins
    )
    assert (type(observed), observed) == expected


_OPAQUE_FIELDS = (
    "ctl",
    "atl",
    "rampRate",
    "ctlLoad",
    "atlLoad",
    "sportInfo",
    "weight",
    "unknown",
)
_TYPE_ALIASES = [
    pytest.param(False, id="false"),
    pytest.param(True, id="true"),
    pytest.param(0, id="zero-int"),
    pytest.param(1, id="positive-int"),
    pytest.param(-1, id="negative-int"),
    pytest.param(0.0, id="zero-float"),
    pytest.param(-0.0, id="negative-zero"),
    pytest.param(1.0, id="positive-float"),
    pytest.param(-1.0, id="negative-float"),
]


@pytest.mark.parametrize("field", _OPAQUE_FIELDS)
@pytest.mark.parametrize("nested", [False, True], ids=["flat", "nested"])
@pytest.mark.parametrize("value", _TYPE_ALIASES)
@pytest.mark.parametrize("facet", ["records", "input"])
def test_listed_package_preserves_json_types_by_field_and_role(
    tmp_path: Path, field: str, nested: bool, value: object, facet: str
) -> None:
    record: dict[str, object] = {"id": _DAY.isoformat()}
    record.update({name: "control-" + name for name in _OPAQUE_FIELDS})
    record[field] = (
        {"z": ["é-control", {"leaf": value}], "a": "ñ-control"} if nested else value
    )
    records = [record]
    expected = _canonical_json(records)
    package, listed_records = _package_listed_records(
        tmp_path, {"garmin_wellness_keys": ["weight"]}, records
    )
    observed = (
        json.loads(package.data)["records"] if facet == "records" else listed_records
    )
    assert _canonical_json(observed) == expected


_UPDATED_PACKAGE_VALUES = [
    pytest.param(None, id="null"),
    pytest.param(False, id="false"),
    pytest.param(True, id="true"),
    pytest.param(0, id="zero-int"),
    pytest.param(1, id="positive-int"),
    pytest.param(-1, id="negative-int"),
    pytest.param(2**64, id="large-int"),
    pytest.param(0.0, id="zero-float"),
    pytest.param(-0.0, id="negative-zero"),
    pytest.param(1.0, id="positive-float"),
    pytest.param(-1.0, id="negative-float"),
    pytest.param(0.5, id="positive-fraction"),
    pytest.param(-1.25, id="negative-fraction"),
    pytest.param(1e100, id="positive-exponent"),
    pytest.param(-1e100, id="negative-exponent"),
    pytest.param("", id="empty-string"),
    pytest.param("opaque", id="ordinary-string"),
    pytest.param("ñ", id="unicode-string"),
    pytest.param(" ", id="whitespace-string"),
    pytest.param(" opaque revision ", id="untrimmed-string"),
    pytest.param([], id="empty-list"),
    pytest.param([False, True, 0, 1, 0.0, -0.0, 1.0, None, "é"], id="nonempty-list"),
    pytest.param({}, id="empty-object"),
    pytest.param({"z": [False, -0.0], "a": {"leaf": None}}, id="nonempty-object"),
]


def _updated_package_records(value: object, nested: bool) -> list[dict[str, object]]:
    record: dict[str, object] = {"id": _DAY.isoformat()}
    record.update({name: "updated-control-" + name for name in _OPAQUE_FIELDS})
    record["weight"] = 37
    record["updated"] = (
        {"z": ["é-control", {"leaf": value}], "a": "ñ-control"} if nested else value
    )
    return [record]


@pytest.mark.parametrize("nested", [False, True], ids=["flat", "nested"])
@pytest.mark.parametrize("value", _UPDATED_PACKAGE_VALUES)
@pytest.mark.parametrize("facet", ["records", "input"])
def test_listed_package_preserves_updated_value_and_role(
    tmp_path: Path, nested: bool, value: object, facet: str
) -> None:
    records = _updated_package_records(value, nested)
    expected = _canonical_json(records)
    package, caller_records = _package_listed_records(
        tmp_path, {"garmin_wellness_keys": ["weight"]}, records
    )
    observed = (
        json.loads(package.data)["records"] if facet == "records" else caller_records
    )
    assert _canonical_json(observed) == expected


@pytest.mark.parametrize("facet", ["records", "input"])
def test_listed_package_preserves_missing_updated(tmp_path: Path, facet: str) -> None:
    records = _updated_package_records(None, False)
    records[0].pop("updated")
    expected = _canonical_json(records)
    package, caller_records = _package_listed_records(
        tmp_path, {"garmin_wellness_keys": ["weight"]}, records
    )
    observed = (
        json.loads(package.data)["records"] if facet == "records" else caller_records
    )
    assert _canonical_json(observed) == expected


@pytest.mark.parametrize("nested", [False, True], ids=["flat", "nested"])
@pytest.mark.parametrize("facet", ["records", "input"])
def test_updated_packaging_keeps_other_field_controls(
    tmp_path: Path, nested: bool, facet: str
) -> None:
    from typing import cast

    records = _updated_package_records(False, nested)
    expected = _canonical_json(
        [{key: value for key, value in records[0].items() if key != "updated"}]
    )
    package, caller_records = _package_listed_records(
        tmp_path, {"garmin_wellness_keys": ["weight"]}, records
    )
    observed = (
        json.loads(package.data)["records"] if facet == "records" else caller_records
    )
    controls = [
        {key: value for key, value in record.items() if key != "updated"}
        for record in cast(list[dict[str, object]], observed)
    ]
    assert _canonical_json(controls) == expected
