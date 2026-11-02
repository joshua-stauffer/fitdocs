"""intervals-publish tasks 2.1-2.3: intervals.icu's answers mapped into publish
codes, and the activity found through the pull record.

Req 7.1-7.7 (the answer table, by request kind) and 8.2, 8.3 (the remote
identifier rule and the direct link); 3.1-3.4 (the recorded link and the pull
record); 3.5, 7.4, 9.3, 9.5 (the listing around the page's start, through a
scripted transport).
"""

from __future__ import annotations

import ast
import base64
import dataclasses
import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from urllib.parse import parse_qs, urlsplit

import pytest

from fitdocs.connectors import intervals
from fitdocs.connectors.errors import ConnectorError
from fitdocs.connectors.http import (
    MAX_DATA_ATTEMPTS,
    RETRYABLE_STATUSES,
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.intervals import (
    ACTIVITY_ID_PATTERN,
    ACTIVITY_LINK_BASE,
    ANSWER_CODES,
    INTERVALS_CONNECTOR_ID,
    LINK_LABEL,
    RESOLVE_FIELDS,
    SUCCESS_STATUSES,
    AnswerClass,
    CallKind,
    IntervalsConnector,
    IntervalsSettings,
    ListedActivity,
    UpdateResult,
    UploadAnswer,
    _activity_link,
    _answer_class,
    _answer_code,
    _auth_headers,
    _base_file,
    _linked_activity,
    _list,
    _listed_activities,
    _listing_window,
    _match_listing,
    _multipart_body,
    _record_activity,
    _update,
    _upload,
    _uploaded_activity,
    _usable_activity_id,
)
from fitdocs.connectors.ledger import (
    Ledger,
    LedgerEntry,
    Outcome,
    load_ledger,
    save_ledger,
)
from fitdocs.connectors.protocol import (
    PUBLISH_CAPABILITIES,
    TARGET_CODES,
    Capability,
    CompletedActivity,
    ConnectorSession,
    Post,
    PublishCode,
    PublishRequest,
    PublishResult,
)
from fitdocs.connectors.registry import validate_connector
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from fitdocs.publish.request import valid_label, valid_link
from fitdocs.publish.targets import list_targets

C = PublishCode
K = CallKind
A = AnswerClass

# The design's answer table, spelled out cell by cell (None: the flow decides).
TABLE: dict[AnswerClass, dict[CallKind, PublishCode | None]] = {
    A.SUCCESS: {K.READ: None, K.UPDATE: None, K.CREATE: None},
    A.UNAUTHORIZED: {
        K.READ: C.AUTH_REJECTED,
        K.UPDATE: C.AUTH_REJECTED,
        K.CREATE: C.AUTH_REJECTED,
    },
    A.FORBIDDEN: {
        K.READ: C.PERMISSION_DENIED,
        K.UPDATE: C.PERMISSION_DENIED,
        K.CREATE: C.PERMISSION_DENIED,
    },
    A.NOT_FOUND: {K.READ: C.REJECTED, K.UPDATE: None, K.CREATE: C.REJECTED},
    A.RATE_LIMITED: {
        K.READ: C.RATE_LIMITED,
        K.UPDATE: C.RATE_LIMITED,
        K.CREATE: C.RATE_LIMITED,
    },
    A.CLIENT_ERROR: {K.READ: C.REJECTED, K.UPDATE: C.REJECTED, K.CREATE: C.REJECTED},
    A.SERVER_ERROR: {
        K.READ: C.UNAVAILABLE,
        K.UPDATE: C.UNAVAILABLE,
        K.CREATE: C.UNCONFIRMED,
    },
    A.OTHER: {K.READ: C.UNAVAILABLE, K.UPDATE: C.UNCONFIRMED, K.CREATE: C.UNCONFIRMED},
    A.NETWORK_FAILURE: {
        K.READ: C.UNAVAILABLE,
        K.UPDATE: C.UNAVAILABLE,
        K.CREATE: C.UNCONFIRMED,
    },
}


def test_answer_table_is_the_literal_table() -> None:
    assert isinstance(ANSWER_CODES, MappingProxyType)
    assert set(ANSWER_CODES) == set(AnswerClass)
    for answer, row in TABLE.items():
        assert isinstance(ANSWER_CODES[answer], MappingProxyType)
        assert dict(ANSWER_CODES[answer]) == row, answer
    assert {k.value for k in CallKind} == {"read", "update", "create"}


def test_every_cell_is_a_target_code_and_none_is_posted_or_uploaded() -> None:
    cells = [c for row in ANSWER_CODES.values() for c in row.values() if c is not None]
    assert len(cells) == 23  # 27 cells, four left to the flow
    for code in cells:
        assert code in TARGET_CODES
        assert code not in (C.POSTED, C.UPLOADED)


def test_success_statuses_per_kind() -> None:
    assert SUCCESS_STATUSES[K.READ] == frozenset({200})
    assert SUCCESS_STATUSES[K.UPDATE] == frozenset({200})
    assert SUCCESS_STATUSES[K.CREATE] == frozenset({200, 201})


_STATUSES = (
    *(200, 201, 202, 204, 301, 307, 400, 401, 403, 404, 409, 413, 415),
    *(422, 429, 500, 502, 503, 504),
)

_EXPECTED: dict[int, tuple[AnswerClass, AnswerClass, AnswerClass]] = {
    # status: (read, update, create)
    200: (A.SUCCESS, A.SUCCESS, A.SUCCESS),
    201: (A.OTHER, A.OTHER, A.SUCCESS),
    202: (A.OTHER, A.OTHER, A.OTHER),
    204: (A.OTHER, A.OTHER, A.OTHER),
    301: (A.OTHER, A.OTHER, A.OTHER),
    307: (A.OTHER, A.OTHER, A.OTHER),
    400: (A.CLIENT_ERROR,) * 3,
    401: (A.UNAUTHORIZED,) * 3,
    403: (A.FORBIDDEN,) * 3,
    404: (A.NOT_FOUND,) * 3,
    409: (A.CLIENT_ERROR,) * 3,
    413: (A.CLIENT_ERROR,) * 3,
    415: (A.CLIENT_ERROR,) * 3,
    422: (A.CLIENT_ERROR,) * 3,
    429: (A.RATE_LIMITED,) * 3,
    500: (A.SERVER_ERROR,) * 3,
    502: (A.SERVER_ERROR,) * 3,
    503: (A.SERVER_ERROR,) * 3,
    504: (A.SERVER_ERROR,) * 3,
}


@pytest.mark.parametrize("status", _STATUSES)
def test_answer_class_per_kind(status: int) -> None:
    got = tuple(_answer_class(kind, status) for kind in (K.READ, K.UPDATE, K.CREATE))
    assert got == _EXPECTED[status]


def test_answer_class_range_edges() -> None:
    assert _answer_class(K.READ, 399) is A.OTHER
    assert _answer_class(K.READ, 400) is A.CLIENT_ERROR
    assert _answer_class(K.READ, 499) is A.CLIENT_ERROR
    assert _answer_class(K.READ, 500) is A.SERVER_ERROR
    assert _answer_class(K.READ, 599) is A.SERVER_ERROR
    assert _answer_class(K.READ, 600) is A.OTHER
    assert _answer_class(K.READ, 100) is A.OTHER


def test_answer_code_reads_the_table() -> None:
    for answer, row in TABLE.items():
        for kind, code in row.items():
            assert _answer_code(kind, answer) is code


def test_status_to_code_end_to_end() -> None:
    # A 5xx after a creation may follow a completed creation; for the other
    # kinds it is plain unavailability.
    assert _answer_code(K.CREATE, _answer_class(K.CREATE, 503)) is C.UNCONFIRMED
    assert _answer_code(K.UPDATE, _answer_class(K.UPDATE, 503)) is C.UNAVAILABLE
    # 201 confirms a creation but is an unexpected status for an update.
    assert _answer_code(K.CREATE, _answer_class(K.CREATE, 201)) is None
    assert _answer_code(K.UPDATE, _answer_class(K.UPDATE, 201)) is C.UNCONFIRMED


# --- identifier and link --------------------------------------------------

_BASE = "https://intervals.icu/activities/"


def test_link_base_literal() -> None:
    assert ACTIVITY_LINK_BASE == _BASE
    assert ACTIVITY_ID_PATTERN == r"^[A-Za-z0-9]{1,64}$"


@pytest.mark.parametrize("activity_id", ["i9000001", "1", "A", "a" * 64, "I0Z9"])
def test_usable_ids_round_trip(activity_id: str) -> None:
    link = _activity_link(activity_id)
    assert link == _BASE + activity_id
    assert _linked_activity(link) == activity_id


@pytest.mark.parametrize(
    "bad",
    [
        "i9/1",
        "i 1",
        "",
        "a" * 65,
        "i-1",
        "i.1",
        "i1\n",
        "é1",
        "i1/",
    ],
)
def test_unusable_ids_refused_in_a_link(bad: str) -> None:
    assert re.fullmatch(ACTIVITY_ID_PATTERN, bad) is None
    assert _linked_activity(_BASE + bad) is None


@pytest.mark.parametrize(
    "link",
    [
        None,
        "",
        "http://intervals.icu/activities/i9000001",
        "https://intervals.icu/activities/i9000001?x=1",
        "https://intervals.icu/activities/i9000001#top",
        "https://intervals.icu/activities/i9000001/",
        "https://intervals.icu/activities/i9000001 ",
        " https://intervals.icu/activities/i9000001",
        "https://INTERVALS.icu/activities/i9000001",
        "https://intervals.icu/activity/i9000001",
        "https://intervals.icu/activities/",
        "https://intervals.icu/activities/i1/x",
        "https://example.com/activities/i9000001",
        "https://interval.test/activities/i9000001",
        "i9000001",
    ],
)
def test_links_not_of_exactly_the_form_name_nothing(link: str | None) -> None:
    assert _linked_activity(link) is None


def test_the_good_link_is_accepted() -> None:
    assert _linked_activity("https://intervals.icu/activities/i9000001") == "i9000001"


# --- Task 2.2: the pull record (Req 3.2, 3.3, 3.4, 8.3) ----------------------

_BASE_SHA = "b" * 64
_EXTRA_1 = "1" * 64
_EXTRA_2 = "2" * 64
_UNRELATED = "9" * 64


def _entry(
    remote_id: str, sha: str | None, outcome: Outcome = Outcome.DELIVERED
) -> LedgerEntry:
    detail = "not wanted" if outcome is Outcome.SKIPPED else None
    return LedgerEntry(remote_id=remote_id, outcome=outcome, sha256=sha, detail=detail)


INSTANCE = "icu-main"  # differs from INTERVALS_CONNECTOR_ID on purpose
HAND_NOTE = b"# kept by hand\n"


def _path(data_root: Path, instance: str = INSTANCE) -> Path:
    return data_root / ".fitdocs" / "connectors" / f"{instance}.toml"


def _write(data_root: Path, *entries: LedgerEntry, instance: str = INSTANCE) -> bytes:
    """Save the ledger with the writer, then append a line the writer would
    not produce, so that any rewrite of the file changes its bytes."""
    ledger = Ledger(
        connector_id="intervals",
        watermark=None,
        entries=tuple(sorted(entries, key=lambda e: e.remote_id)),
    )
    save_ledger(data_root, instance, ledger)
    path = _path(data_root, instance)
    path.write_bytes(path.read_bytes() + HAND_NOTE)
    assert load_ledger(data_root, instance, connector_id="intervals").entries
    return path.read_bytes()


def _snapshot(path: Path) -> tuple[bytes, int, int]:
    st = path.stat()
    return path.read_bytes(), st.st_ino, st.st_mtime_ns


class _NoTransport:
    def __call__(self, request: object, timeout: float) -> object:
        raise AssertionError("the pull record is read without a request")


def _session(data_root: Path) -> ConnectorSession:
    from fitdocs.connectors.http import CallMode, HttpClient

    redactor = Redactor()
    return ConnectorSession(
        instance=INSTANCE,
        settings=object(),
        http=HttpClient(
            _NoTransport(),  # type: ignore[arg-type]
            mode=CallMode.DATA,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=None,  # type: ignore[arg-type]
        data_root=data_root,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _subject(*shas: str) -> CompletedActivity:
    return CompletedActivity(
        sport="Run",
        start=datetime(2026, 3, 1, 7, 0, tzinfo=UTC),
        elapsed_s=1800.0,
        distance_m=5000.0,
        source_shas=shas,
        base_fit=None,
    )


def test_base_digest_mapped_and_the_record_is_not_rewritten(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i1", _BASE_SHA), _entry("i2", _UNRELATED))
    before = _snapshot(_path(tmp_path))
    assert before[0].endswith(HAND_NOTE)
    assert _record_activity(_session(tmp_path), _subject(_EXTRA_1, _BASE_SHA)) == "i1"
    assert _snapshot(_path(tmp_path)) == before


def test_only_an_extra_mapped(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i1", _EXTRA_1), _entry("i2", _UNRELATED))
    assert _record_activity(_session(tmp_path), _subject(_EXTRA_1, _BASE_SHA)) == "i1"


def test_the_base_wins_over_an_extra_with_another_activity(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i1", _BASE_SHA), _entry("i2", _EXTRA_1))
    assert _record_activity(_session(tmp_path), _subject(_EXTRA_1, _BASE_SHA)) == "i1"


def test_a_tier_with_two_activities_is_ambiguous_even_when_the_other_tier_has_one(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        _entry("i1", _BASE_SHA),
        _entry("i2", _BASE_SHA),
        _entry("i3", _EXTRA_1),
    )
    got = _record_activity(_session(tmp_path), _subject(_EXTRA_1, _BASE_SHA))
    assert got is PublishCode.AMBIGUOUS


def test_two_activities_among_the_extras_with_none_for_the_base_are_ambiguous(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        _entry("i1", _EXTRA_1),
        _entry("i2", _EXTRA_2),
        _entry("i3", _UNRELATED),
    )
    got = _record_activity(_session(tmp_path), _subject(_EXTRA_1, _EXTRA_2, _BASE_SHA))
    assert got is PublishCode.AMBIGUOUS


def test_one_extra_digest_among_several_names_its_activity(
    tmp_path: Path,
) -> None:
    # only the second extra is in the ledger; the first and the base are not
    _write(tmp_path, _entry("i1", _EXTRA_2), _entry("i2", _UNRELATED))
    got = _record_activity(_session(tmp_path), _subject(_EXTRA_1, _EXTRA_2, _BASE_SHA))
    assert got == "i1"


@pytest.mark.parametrize(
    "outcome", [Outcome.DELIVERED, Outcome.ALREADY_HELD, Outcome.SKIPPED]
)
def test_an_entrys_outcome_does_not_matter(tmp_path: Path, outcome: Outcome) -> None:
    _write(tmp_path, _entry("i1", _BASE_SHA, outcome))
    assert _record_activity(_session(tmp_path), _subject(_BASE_SHA)) == "i1"


def test_an_absent_record_names_no_activity_and_is_not_created(tmp_path: Path) -> None:
    assert _record_activity(_session(tmp_path), _subject(_BASE_SHA)) is None
    assert not (tmp_path / ".fitdocs").exists()


def test_a_record_with_no_matching_digest_names_nothing(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i1", _UNRELATED))
    before = _snapshot(_path(tmp_path))
    assert before[0].endswith(HAND_NOTE)
    assert _record_activity(_session(tmp_path), _subject(_BASE_SHA)) is None
    assert _snapshot(_path(tmp_path)) == before


def test_no_source_digests_name_nothing(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i1", _BASE_SHA))
    assert _record_activity(_session(tmp_path), _subject()) is None


def test_an_unreadable_record_is_reported_and_left_unchanged(tmp_path: Path) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"this = [is not valid toml\n")
    before = path.read_bytes()
    got = _record_activity(_session(tmp_path), _subject(_BASE_SHA))
    assert got is PublishCode.LOCAL_RECORD_UNREADABLE
    assert path.read_bytes() == before


def test_a_malformed_identifier_names_nothing(tmp_path: Path) -> None:
    # the precondition: the ledger writer accepts the id, the digest matches
    _write(tmp_path, _entry("i1/x", _BASE_SHA))
    assert _usable_activity_id("i1/x") is False
    assert _record_activity(_session(tmp_path), _subject(_BASE_SHA)) is None


def test_a_malformed_identifier_in_a_tier_does_not_count_toward_ambiguity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry("i1", _BASE_SHA), _entry("i1/x", _BASE_SHA))
    assert _record_activity(_session(tmp_path), _subject(_BASE_SHA)) == "i1"


def test_a_malformed_base_identifier_does_not_hide_the_extra_tier(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry("i1/x", _BASE_SHA), _entry("i2", _EXTRA_1))
    assert _record_activity(_session(tmp_path), _subject(_EXTRA_1, _BASE_SHA)) == "i2"


def test_a_malformed_extra_identifier_names_nothing(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i1/x", _EXTRA_1))
    assert _record_activity(_session(tmp_path), _subject(_EXTRA_1, _BASE_SHA)) is None


def test_a_malformed_extra_identifier_does_not_count_toward_ambiguity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry("i1", _EXTRA_1), _entry("i2/x", _EXTRA_2))
    assert (
        _record_activity(_session(tmp_path), _subject(_EXTRA_1, _EXTRA_2, _BASE_SHA))
        == "i1"
    )


def test_a_tier_two_ambiguity_does_not_override_a_single_base_activity(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        _entry("i1", _BASE_SHA),
        _entry("i2", _EXTRA_1),
        _entry("i3", _EXTRA_2),
    )
    got = _record_activity(_session(tmp_path), _subject(_EXTRA_1, _EXTRA_2, _BASE_SHA))
    assert got == "i1"


def test_the_record_read_is_the_sessions_instance_not_the_connector_id(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry("i8", _BASE_SHA), instance=INTERVALS_CONNECTOR_ID)
    _write(tmp_path, _entry("i1", _BASE_SHA))
    assert INSTANCE != INTERVALS_CONNECTOR_ID
    assert _record_activity(_session(tmp_path), _subject(_BASE_SHA)) == "i1"


# --- 2.3: the listing around the page's start ----------------------------------

_API_KEY = "k-secret-123"


class _Scripted:
    """A transport that records requests and answers every one the same way."""

    def __init__(self, response: HttpResponse | TransportError) -> None:
        self.response = response
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        if isinstance(self.response, TransportError):
            raise self.response
        return self.response


def _listing_session(transport: _Scripted, data_root: Path) -> ConnectorSession:
    from fitdocs.connectors.http import CallMode, HttpClient

    redactor = Redactor()
    return ConnectorSession(
        instance=INSTANCE,
        settings=object(),
        http=HttpClient(
            transport,
            mode=CallMode.DATA,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=None,  # type: ignore[arg-type]
        data_root=data_root,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _run(
    tmp_path: Path, response: HttpResponse | TransportError, subject: CompletedActivity
) -> tuple[object, _Scripted]:
    transport = _Scripted(response)
    session = _listing_session(transport, tmp_path)
    headers = _auth_headers(session, Secret(_API_KEY))
    return _list(session, headers, subject), transport


def _ok(payload: object) -> HttpResponse:
    return HttpResponse(status=200, headers={}, body=json.dumps(payload).encode())


def _entries(*entries: dict[str, object]) -> HttpResponse:
    return _ok(list(entries))


def test_request_address_query_and_header_names(tmp_path: Path) -> None:
    result, transport = _run(tmp_path, _ok([]), _subject())
    assert result == ()
    (request,) = transport.requests
    parts = urlsplit(request.url)
    assert request.method == "GET"
    assert (parts.scheme, parts.netloc) == ("https", "intervals.icu")
    assert parts.path == "/api/v1/athlete/0/activities"
    # _subject() starts 2026-03-01T07:00Z
    assert parse_qs(parts.query, keep_blank_values=True) == {
        "oldest": ["2026-02-28T00:00:00"],
        "newest": ["2026-03-03T00:00:00"],
        "fields": [
            "id,source,start_date,start_date_local,distance,elapsed_time,external_id"
        ],
    }
    assert request.body is None
    assert list(request.secret_headers) == ["Authorization"]
    token = base64.b64encode(f"API_KEY:{_API_KEY}".encode()).decode()
    assert request.secret_headers["Authorization"].reveal() == f"Basic {token}"
    sent = {name.lower() for name in request.headers}
    assert "authorization" not in sent
    assert _API_KEY not in request.url


def test_the_resolve_fields_are_the_designs_seven() -> None:
    assert RESOLVE_FIELDS == (
        "id",
        "source",
        "start_date",
        "start_date_local",
        "distance",
        "elapsed_time",
        "external_id",
    )


def test_window_exact_strings_and_calendar_rollover() -> None:
    assert _listing_window(datetime(2026, 3, 1, 7, 0, tzinfo=UTC)) == (
        "2026-02-28T00:00:00",
        "2026-03-03T00:00:00",
    )
    assert _listing_window(datetime(2026, 12, 31, 12, 0, tzinfo=UTC)) == (
        "2026-12-30T00:00:00",
        "2027-01-02T00:00:00",
    )


def test_window_is_anchored_on_the_utc_date_not_the_starts_own_zone() -> None:
    # 2026-03-01T23:30-05:00 is 2026-03-02T04:30Z: the UTC date is the 2nd.
    start = datetime(2026, 3, 1, 23, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert _listing_window(start) == ("2026-03-01T00:00:00", "2026-03-04T00:00:00")


@pytest.mark.parametrize("offset_hours", range(-12, 15))
@pytest.mark.parametrize("utc_clock", [(0, 30), (23, 30)])
def test_window_holds_the_local_wall_clock_start_at_every_offset(
    offset_hours: int, utc_clock: tuple[int, int]
) -> None:
    start = datetime(2026, 3, 15, *utc_clock, tzinfo=UTC)
    local = start.astimezone(timezone(timedelta(hours=offset_hours))).replace(
        tzinfo=None
    )
    oldest, newest = (datetime.fromisoformat(v) for v in _listing_window(start))
    assert oldest <= local <= newest


_FULL: dict[str, object] = {
    "id": "i9000001",
    "source": "GARMIN_CONNECT",
    "start_date": "2026-03-01T05:00:00+02:00",
    "start_date_local": "2026-03-01T09:15:30",
    "distance": 1234.5,
    "elapsed_time": 987,
    "external_id": "pub-xyz",
}


def _one(entry: dict[str, object]) -> ListedActivity:
    listed = _listed_activities(json.dumps([entry]).encode())
    assert listed is not None
    (only,) = listed
    return only


def test_a_fully_present_entry_parses_every_field_distinctly() -> None:
    assert _one(_FULL) == ListedActivity(
        activity_id="i9000001",
        strava=False,
        start=datetime(2026, 3, 1, 3, 0, tzinfo=UTC),
        local_start=datetime(2026, 3, 1, 9, 15, 30),
        distance_m=1234.5,
        elapsed_s=987.0,
        external_id="pub-xyz",
    )


def test_an_entry_with_only_an_id_has_every_other_field_absent() -> None:
    assert _one({"id": "i9000001"}) == ListedActivity(
        activity_id="i9000001",
        strava=False,
        start=None,
        local_start=None,
        distance_m=None,
        elapsed_s=None,
        external_id=None,
    )


def test_source_strava_is_the_exact_source_name() -> None:
    assert _one({**_FULL, "source": "STRAVA"}).strava is True
    for other in ("strava", "GARMIN_CONNECT", "STRAVA2", "", None, 5):
        assert _one({**_FULL, "source": other}).strava is False


def test_start_date_without_an_offset_is_absent_not_utc_and_not_local() -> None:
    assert _one({**_FULL, "start_date": "2026-03-01T05:00:00"}).start is None


def test_start_date_with_z_or_an_offset_is_utc() -> None:
    assert _one({**_FULL, "start_date": "2026-03-01T05:00:00Z"}).start == datetime(
        2026, 3, 1, 5, 0, tzinfo=UTC
    )
    assert _one({**_FULL, "start_date": "2026-03-01T05:00:00-03:30"}).start == (
        datetime(2026, 3, 1, 8, 30, tzinfo=UTC)
    )


@pytest.mark.parametrize("bad", ["garbage", "", 5, 20260301, 1.5, True, None, [], {}])
def test_malformed_start_date_is_absent(bad: object) -> None:
    assert _one({**_FULL, "start_date": bad}).start is None


def test_start_date_local_keeps_the_wall_clock_and_drops_any_offset() -> None:
    assert _one({**_FULL, "start_date_local": "2026-03-01T09:15:30+05:00"}) == (
        _one({**_FULL, "start_date_local": "2026-03-01T09:15:30"})
    )
    assert _one(
        {**_FULL, "start_date_local": "2026-03-01T09:15:30+05:00"}
    ).local_start == datetime(2026, 3, 1, 9, 15, 30)


@pytest.mark.parametrize("bad", ["garbage", "", 5, 20260301, True, None, [], {}])
def test_malformed_start_date_local_is_absent(bad: object) -> None:
    assert _one({**_FULL, "start_date_local": bad}).local_start is None


def test_zero_is_a_present_distance_and_elapsed_time() -> None:
    entry = _one({**_FULL, "distance": 0, "elapsed_time": 0})
    assert entry.distance_m == 0.0
    assert entry.elapsed_s == 0.0
    assert _one({**_FULL, "distance": 0.0}).distance_m == 0.0


@pytest.mark.parametrize(
    "bad",
    ["5000", "", -1, -0.5, True, False, None, [], {}, float("nan"), 10**400],
)
def test_malformed_distance_is_absent_never_zero(bad: object) -> None:
    body = json.dumps([{**_FULL, "distance": bad}], allow_nan=True).encode()
    listed = _listed_activities(body)
    assert listed is not None
    assert listed[0].distance_m is None


def test_an_infinite_distance_is_absent() -> None:
    body = b'[{"id": "i9000001", "distance": Infinity}]'
    listed = _listed_activities(body)
    assert listed is not None
    assert listed[0].distance_m is None


@pytest.mark.parametrize(
    "bad", ["60", "", -1, 12.5, 60.0, True, False, None, [], {}, 10**400]
)
def test_malformed_elapsed_time_is_absent_never_zero(bad: object) -> None:
    assert _one({**_FULL, "elapsed_time": bad}).elapsed_s is None


@pytest.mark.parametrize("bad", ["", 5, 20260301, 1.5, True, None, [], {}])
def test_malformed_external_id_is_absent(bad: object) -> None:
    assert _one({**_FULL, "external_id": bad}).external_id is None


def test_a_repeated_identifier_is_kept_once_first_wins_in_order() -> None:
    body = json.dumps(
        [
            {**_FULL, "id": "iB", "distance": 1.0},
            {**_FULL, "id": "iA", "distance": 2.0},
            {**_FULL, "id": "iB", "distance": 3.0},
        ]
    ).encode()
    listed = _listed_activities(body)
    assert listed is not None
    assert [(e.activity_id, e.distance_m) for e in listed] == [("iB", 1.0), ("iA", 2.0)]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"\xff\xfe",
        json.dumps([{"id": "i9000001"}]).encode("utf-16"),
        b'[{"id": "i9000001", "external_id": "caf\xe9"}]',
        b"[" * 200000,
        b"null",
        b'"text"',
        b"5",
        b'{"id": "i9000001"}',
        b'{"activities": []}',
        b"[5]",
        b'["i9000001"]',
        b"[null]",
        b"[[]]",
        b"[{}]",
        b'[{"id": null}]',
        b'[{"id": 9000001}]',
        b'[{"id": true}]',
        b'[{"id": ""}]',
        b'[{"id": "i9/1"}]',
        b'[{"id": "i 1"}]',
        b'[{"id": "' + b"a" * 65 + b'"}]',
        b'[{"id": "i9000001"}, {"id": "i/2"}]',
        b'[{"id": "i9000001"}, 7]',
    ],
)
def test_a_body_not_an_array_of_objects_with_usable_ids_is_not_documented(
    body: bytes,
) -> None:
    assert _listed_activities(body) is None


def test_an_external_id_is_kept_exactly_as_given() -> None:
    assert _one({**_FULL, "external_id": " pub-xyz "}).external_id == " pub-xyz "


def test_an_empty_array_is_a_listing_of_nothing() -> None:
    assert _listed_activities(b"[]") == ()


def test_a_sixty_four_character_id_is_usable() -> None:
    assert _one({"id": "a" * 64}).activity_id == "a" * 64


def test_the_listing_returns_the_parsed_entries(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, _entries(_FULL), _subject())
    assert result == (_one(_FULL),)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, C.AUTH_REJECTED),
        (403, C.PERMISSION_DENIED),
        (404, C.REJECTED),
        (418, C.REJECTED),
        (429, C.RATE_LIMITED),
        (500, C.UNAVAILABLE),
        (503, C.UNAVAILABLE),
        (204, C.UNAVAILABLE),
        (302, C.UNAVAILABLE),
    ],
)
def test_each_failing_status_answers_the_read_codes(
    tmp_path: Path, status: int, code: PublishCode
) -> None:
    response = HttpResponse(status=status, headers={}, body=b"[]")
    result, transport = _run(tmp_path, response, _subject())
    assert result == code
    assert transport.requests


def test_a_transport_failure_is_unavailable(tmp_path: Path) -> None:
    result, transport = _run(tmp_path, TransportError("timed out"), _subject())
    assert result == C.UNAVAILABLE
    assert transport.requests


@pytest.mark.parametrize("body", [b"not json", b"{}", b'[{"id": "i/1"}]'])
def test_a_200_body_not_in_documented_form_is_unavailable(
    tmp_path: Path, body: bytes
) -> None:
    response = HttpResponse(status=200, headers={}, body=body)
    result, _ = _run(tmp_path, response, _subject())
    assert result == C.UNAVAILABLE


def test_an_error_status_is_judged_by_status_not_by_body(tmp_path: Path) -> None:
    good_body = json.dumps([_FULL]).encode()
    result, _ = _run(
        tmp_path, HttpResponse(status=403, headers={}, body=good_body), _subject()
    )
    assert result == C.PERMISSION_DENIED


# --- Matching the listing one-to-one (Req 3.6-3.8, 4.1, 4.2) ------------------

PUBLICATION_ID = "0123456789abcdef0123456789abcdef"
PAGE_START = datetime(2026, 3, 1, 7, 0, tzinfo=UTC)


def _page(
    *,
    sport: str = "Run",
    start: datetime = PAGE_START,
    distance_m: float | None = 5000.0,
    elapsed_s: float | None = 1800.0,
) -> CompletedActivity:
    return CompletedActivity(
        sport=sport,
        start=start,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
        source_shas=(),
        base_fit=None,
    )


def _listed(
    activity_id: str,
    *,
    strava: bool = False,
    start: datetime | None = PAGE_START,
    local_start: datetime | None = None,
    distance_m: float | None = None,
    elapsed_s: float | None = None,
    external_id: str | None = None,
) -> ListedActivity:
    return ListedActivity(
        activity_id=activity_id,
        strava=strava,
        start=start,
        local_start=local_start,
        distance_m=distance_m,
        elapsed_s=elapsed_s,
        external_id=external_id,
    )


def _match(
    listed: list[ListedActivity],
    subject: CompletedActivity | None = None,
    *,
    absent: frozenset[str] = frozenset(),
) -> str | PublishCode | None:
    return _match_listing(listed, subject or _page(), PUBLICATION_ID, absent=absent)


def test_an_external_id_match_beats_a_strict_match() -> None:
    strict = _listed("i9000002", distance_m=5000.0, elapsed_s=1800.0)
    by_id = _listed(
        "i9000001",
        start=PAGE_START + timedelta(hours=5),
        distance_m=42000.0,
        external_id=PUBLICATION_ID,
    )
    assert _match([strict]) == "i9000002"  # the strict entry does match alone
    assert _match([strict, by_id]) == "i9000001"
    assert _match([by_id, strict]) == "i9000001"


def test_an_external_id_other_than_the_publication_id_names_nothing() -> None:
    other = _listed(
        "i9000001", start=PAGE_START + timedelta(hours=5), external_id="x" * 32
    )
    assert _match([other]) is None


def test_two_external_id_matches_are_ambiguous() -> None:
    first = _listed("i9000001", start=None, external_id=PUBLICATION_ID)
    second = _listed("i9000002", start=None, external_id=PUBLICATION_ID)
    assert _match([first, second]) == C.AMBIGUOUS


def test_two_external_id_matches_beat_a_single_strict_match() -> None:
    strict = _listed("i9000003", distance_m=5000.0)
    first = _listed("i9000001", start=None, external_id=PUBLICATION_ID)
    second = _listed("i9000002", start=None, external_id=PUBLICATION_ID)
    assert _match([strict, first, second]) == C.AMBIGUOUS


def test_a_strict_match_by_distance_ignores_elapsed_time() -> None:
    entry = _listed("i9000001", distance_m=5100.0, elapsed_s=100.0)
    far = _listed("i9000002", distance_m=7000.0, elapsed_s=1800.0)
    assert _match([far]) is None  # 2000 m apart is outside the tolerance
    assert _match([far, entry]) == "i9000001"


def test_a_strict_match_needs_the_start_to_agree() -> None:
    late = _listed(
        "i9000001", start=PAGE_START + timedelta(seconds=2), distance_m=5000.0
    )
    edge = _listed(
        "i9000002", start=PAGE_START + timedelta(seconds=1), distance_m=5000.0
    )
    assert _match([late]) is None
    assert _match([late, edge]) == "i9000002"


def test_a_strict_match_by_elapsed_time_when_the_listed_distance_is_missing() -> None:
    near = _listed("i9000001", distance_m=None, elapsed_s=1805.0)
    off = _listed("i9000002", distance_m=None, elapsed_s=1815.0)
    assert _match([off]) is None
    assert _match([off, near]) == "i9000001"


def test_a_strict_match_by_elapsed_time_when_the_page_distance_is_missing() -> None:
    page = _page(distance_m=None)
    near = _listed("i9000001", distance_m=5000.0, elapsed_s=1805.0)
    off = _listed("i9000002", distance_m=5000.0, elapsed_s=1815.0)
    assert _match([off], page) is None
    assert _match([off, near], page) == "i9000001"


def test_no_match_when_the_evidence_is_missing_on_both_sides() -> None:
    bare = _listed("i9000001", distance_m=None, elapsed_s=None)
    assert _match([bare], _page(distance_m=None)) is None
    assert _match([bare], _page(distance_m=None, elapsed_s=None)) is None
    with_distance = _listed("i9000002", distance_m=5000.0, elapsed_s=None)
    assert _match([with_distance], _page(distance_m=None, elapsed_s=None)) is None
    assert _match([with_distance]) == "i9000002"  # distance alone is enough


def test_an_entry_with_no_instant_start_is_never_a_strict_match() -> None:
    entry = _listed(
        "i9000001",
        start=None,
        local_start=PAGE_START.replace(tzinfo=None),
        distance_m=5000.0,
        elapsed_s=1800.0,
    )
    assert _match([entry]) is None


@pytest.mark.parametrize("sport", ["Run", "Ride", "WeightTraining", "Swim"])
def test_the_sport_is_not_compared(sport: str) -> None:
    entry = _listed("i9000001", distance_m=5000.0)
    assert _match([entry], _page(sport=sport)) == "i9000001"


def test_the_shifted_tier_is_not_a_match() -> None:
    # An hour apart with the same distance and elapsed time: only the shifted
    # tier could hold, and only for a phone copy, which a listing never is.
    shifted = _listed(
        "i9000001",
        start=PAGE_START + timedelta(hours=1),
        distance_m=5000.0,
        elapsed_s=1800.0,
    )
    assert _match([shifted]) is None


def test_the_keys_compared_carry_the_page_sport_and_no_device_or_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitdocs.identity import matching

    real = matching.pair_evidence
    seen: list[tuple[matching.SessionKey, matching.SessionKey]] = []

    def spy(a: matching.SessionKey, b: matching.SessionKey) -> matching.Evidence | None:
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(matching, "pair_evidence", spy)
    entry = _listed("i9000001", distance_m=5000.0, elapsed_s=1800.0)
    assert _match([entry], _page(sport="Ride")) == "i9000001"
    assert len(seen) == 1, "the rule was not consulted exactly once"
    for key in seen[0]:
        assert key.sport == "Ride"
        assert key.device is None
        assert key.kind is None
    assert seen[0][0].start == PAGE_START
    assert seen[0][1].start == PAGE_START
    assert {seen[0][0].distance_m, seen[0][1].distance_m} == {5000.0}


def test_two_strict_matches_are_ambiguous() -> None:
    first = _listed("i9000001", distance_m=5000.0)
    second = _listed("i9000002", distance_m=5010.0)
    assert _match([first]) == "i9000001"
    assert _match([first, second]) == C.AMBIGUOUS
    assert _match([second, first]) == C.AMBIGUOUS


def test_an_entry_answered_absent_is_excluded_from_both_steps() -> None:
    by_id = _listed("i9000001", start=None, external_id=PUBLICATION_ID)
    strict = _listed("i9000002", distance_m=5000.0)
    other = _listed("i9000003", distance_m=5000.0)
    gone = frozenset({"i9000001"})
    assert _match([by_id, strict], absent=gone) == "i9000002"
    assert _match([by_id], absent=gone) is None
    assert _match([strict, other]) == C.AMBIGUOUS
    assert _match([strict, other], absent=frozenset({"i9000002"})) == "i9000003"
    assert _match([strict], absent=frozenset({"i9000002"})) is None


def test_a_strava_entry_is_never_matched_and_is_not_updatable() -> None:
    # Otherwise a perfect strict match.
    strava = _listed("i9000001", strava=True, distance_m=5000.0, elapsed_s=1800.0)
    assert _match([strava]) == C.NOT_UPDATABLE
    clone = _listed("i9000002", strava=False, distance_m=5000.0, elapsed_s=1800.0)
    assert _match([strava, clone]) == "i9000002"  # the other source still matches


def test_a_strava_entry_with_the_external_id_is_not_matched() -> None:
    far = PAGE_START + timedelta(hours=5)
    strava = _listed("i9000001", strava=True, start=far, external_id=PUBLICATION_ID)
    assert _match([strava]) is None


def test_a_strava_entry_is_reported_by_its_instant_start() -> None:
    page = _page()
    within = _listed("i9000001", strava=True, start=PAGE_START + timedelta(seconds=1))
    outside = _listed("i9000002", strava=True, start=PAGE_START + timedelta(seconds=2))
    assert _match([within], page) == C.NOT_UPDATABLE
    assert _match([outside], page) is None
    before = _listed("i9000003", strava=True, start=PAGE_START - timedelta(seconds=1))
    assert _match([before], page) == C.NOT_UPDATABLE


def test_the_instant_start_decides_when_the_local_start_disagrees() -> None:
    page = _page()
    wall = PAGE_START.replace(tzinfo=None)
    far = _listed(
        "i9000001",
        strava=True,
        start=PAGE_START + timedelta(hours=1),
        local_start=wall,
    )
    assert _match([far], page) is None


def test_a_strava_entry_without_an_instant_start_is_reported_by_local_start() -> None:
    plus_two = timezone(timedelta(hours=2))
    page = _page(start=datetime(2026, 3, 1, 9, 0, tzinfo=plus_two))  # 07:00 UTC
    wall = datetime(2026, 3, 1, 9, 0)
    on_wall = _listed("i9000001", strava=True, start=None, local_start=wall)
    on_utc = _listed(
        "i9000002",
        strava=True,
        start=None,
        local_start=datetime(2026, 3, 1, 7, 0),
    )
    off_by_two = _listed(
        "i9000003",
        strava=True,
        start=None,
        local_start=wall + timedelta(seconds=2),
    )
    assert _match([on_wall], page) == C.NOT_UPDATABLE
    assert _match([on_utc], page) is None
    assert _match([off_by_two], page) is None
    nothing = _listed("i9000004", strava=True, start=None, local_start=None)
    assert _match([nothing], page) is None


def test_a_non_strava_local_start_never_reports_not_updatable() -> None:
    entry = _listed("i9000001", start=None, local_start=PAGE_START.replace(tzinfo=None))
    assert _match([entry]) is None


def test_a_strava_entry_answered_absent_is_not_reported() -> None:
    strava = _listed("i9000001", strava=True)
    assert _match([strava]) == C.NOT_UPDATABLE
    assert _match([strava], absent=frozenset({"i9000001"})) is None


def test_a_match_beats_a_strava_entry_at_the_same_start() -> None:
    strava = _listed("i9000001", strava=True)
    mine = _listed("i9000002", distance_m=5000.0)
    assert _match([strava, mine]) == "i9000002"


def test_an_empty_listing_names_nothing() -> None:
    assert _match([]) is None


def test_importing_the_connectors_package_loads_no_identity_module() -> None:
    code = (
        "import sys\n"
        "import fitdocs.connectors\n"
        "print(sorted(m for m in sys.modules\n"
        "             if m == 'fitdocs.identity'\n"
        "             or m.startswith('fitdocs.identity.')))\n"
        "print('fitdocs.connectors.intervals' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded, imported = result.stdout.strip().splitlines()
    assert imported == "True", "the intervals module was not imported at all"
    assert loaded == "[]"


def test_only_the_strict_tier_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitdocs.identity import matching

    entry = _listed("i9000001", distance_m=5000.0)
    outcomes: dict[str, matching.Evidence] = {}
    for tier in (matching.Evidence.SHIFTED, matching.Evidence.DEVICE):
        outcomes[tier.value] = tier
    for name, tier in outcomes.items():
        monkeypatch.setattr(matching, "pair_evidence", lambda a, b, t=tier: t)
        assert _match([entry]) is None, name
    monkeypatch.setattr(
        matching, "pair_evidence", lambda a, b: matching.Evidence.STRICT
    )
    assert _match([entry]) == "i9000001"


def test_the_strict_start_is_compared_as_instants() -> None:
    page = _page(start=datetime(2026, 3, 1, 9, 0, tzinfo=timezone(timedelta(hours=2))))
    same_instant = _listed(
        "i9000001", start=datetime(2026, 3, 1, 7, 0, tzinfo=UTC), distance_m=5000.0
    )
    same_clock = _listed(
        "i9000002", start=datetime(2026, 3, 1, 9, 0, tzinfo=UTC), distance_m=5000.0
    )
    assert _match([same_clock], page) is None
    assert _match([same_clock, same_instant], page) == "i9000001"


def test_a_strava_instant_start_is_compared_as_instants_against_an_offset_page() -> (
    None
):
    page = _page(start=datetime(2026, 3, 1, 9, 0, tzinfo=timezone(timedelta(hours=2))))
    same_instant = _listed(
        "i9000001", strava=True, start=datetime(2026, 3, 1, 7, 0, tzinfo=UTC)
    )
    same_clock = _listed(
        "i9000002", strava=True, start=datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    )
    assert _match([same_instant], page) == C.NOT_UPDATABLE
    assert _match([same_clock], page) is None


# --- Updating an activity's name and description (Req 5.1, 5.2, 5.4-5.6, 9.2, 9.5)


ACTIVITY = "i4242"
TITLE = "Morning tempo, Ünïcode"
DESCRIPTION = "Line one\nLine two"
_SENTINEL = b"SENTINEL-ANSWER-BODY"


class _Sequence:
    """A transport answering from a script, one entry per request, recording each."""

    def __init__(self, *script: HttpResponse | TransportError) -> None:
        self.script = list(script)
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        step = self.script[min(len(self.requests), len(self.script)) - 1]
        if isinstance(step, TransportError):
            raise step
        return step


def _answer(status: int, body: bytes = b"") -> HttpResponse:
    return HttpResponse(status=status, headers={}, body=body)


def _push(
    tmp_path: Path,
    *script: HttpResponse | TransportError,
    post: Post | None = None,
    activity_id: str = ACTIVITY,
) -> tuple[object, _Sequence]:
    transport = _Sequence(*script)
    session = _listing_session(transport, tmp_path)  # type: ignore[arg-type]
    headers = _auth_headers(session, Secret(_API_KEY))
    result = _update(
        session,
        headers,
        activity_id,
        post or Post(title=TITLE, description=DESCRIPTION),
    )
    return result, transport


def test_the_update_request_method_address_body_and_headers(tmp_path: Path) -> None:
    result, transport = _push(tmp_path, _answer(200))
    assert result is UpdateResult.CONFIRMED
    (request,) = transport.requests
    assert request.method == "PUT"
    parts = urlsplit(request.url)
    assert (parts.scheme, parts.netloc) == ("https", "intervals.icu")
    assert parts.path == f"/api/v1/activity/{ACTIVITY}"
    assert (parts.query, parts.fragment) == ("", "")
    assert request.single_attempt is False
    assert request.body is not None
    assert json.loads(request.body.decode("utf-8")) == {
        "name": TITLE,
        "description": DESCRIPTION,
    }
    assert set(json.loads(request.body)) == {"name", "description"}
    assert request.headers["Content-Type"] == "application/json"
    assert "authorization" not in {name.lower() for name in request.headers}


def test_title_and_description_are_distinct_and_not_swapped(tmp_path: Path) -> None:
    assert TITLE != DESCRIPTION
    _, transport = _push(tmp_path, _answer(200))
    body = json.loads(transport.requests[0].body or b"")
    assert body["name"] == TITLE
    assert body["description"] != TITLE


def test_an_empty_description_is_sent_empty_not_omitted_or_null(tmp_path: Path) -> None:
    _, transport = _push(tmp_path, _answer(200), post=Post(title=TITLE, description=""))
    body = json.loads(transport.requests[0].body or b"")
    assert body == {"name": TITLE, "description": ""}
    assert body["description"] == ""


def test_the_body_is_utf_8_compact_json(tmp_path: Path) -> None:
    _, transport = _push(tmp_path, _answer(200))
    raw = transport.requests[0].body
    assert raw == (
        json.dumps(
            {"name": TITLE, "description": DESCRIPTION},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert "Ünïcode".encode() in raw


def test_the_text_is_in_no_address_and_the_key_only_in_secret_headers(
    tmp_path: Path,
) -> None:
    _, transport = _push(tmp_path, _answer(200))
    (request,) = transport.requests
    token = base64.b64encode(f"API_KEY:{_API_KEY}".encode()).decode()
    for needle in (TITLE, "Line one", "Line two", "Morning", _API_KEY, token):
        assert needle not in request.url
    assert list(request.secret_headers) == ["Authorization"]
    assert request.secret_headers["Authorization"].reveal() == f"Basic {token}"
    visible = " ".join(f"{k}:{v}" for k, v in request.headers.items())
    assert _API_KEY not in visible and token not in visible
    assert request.body is not None
    assert _API_KEY.encode() not in request.body
    assert token.encode() not in request.body


def test_the_activity_id_is_percent_quoted_in_the_address(tmp_path: Path) -> None:
    _, transport = _push(tmp_path, _answer(200), activity_id="a/b?c")
    assert urlsplit(transport.requests[0].url).path == "/api/v1/activity/a%2Fb%3Fc"


def test_503_503_200_is_confirmed_after_three_requests(tmp_path: Path) -> None:
    result, transport = _push(tmp_path, _answer(503), _answer(503), _answer(200))
    assert result is UpdateResult.CONFIRMED
    assert len(transport.requests) == 3
    assert {r.method for r in transport.requests} == {"PUT"}
    assert len({r.body for r in transport.requests}) == 1


def test_a_persistent_503_is_unavailable_after_the_retries(tmp_path: Path) -> None:
    result, transport = _push(tmp_path, _answer(503))
    assert result == C.UNAVAILABLE
    assert len(transport.requests) == 3


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, UpdateResult.CONFIRMED),
        (404, UpdateResult.ABSENT),
        (401, C.AUTH_REJECTED),
        (403, C.PERMISSION_DENIED),
        (400, C.REJECTED),
        (410, C.REJECTED),
        (422, C.REJECTED),
        (429, C.RATE_LIMITED),
        (500, C.UNAVAILABLE),
        (201, C.UNCONFIRMED),
        (204, C.UNCONFIRMED),
        (302, C.UNCONFIRMED),
    ],
)
def test_each_answer_maps_to_its_update_result(
    tmp_path: Path, status: int, expected: object
) -> None:
    body = b'{"id":"i4242","error":"x"}'
    result, transport = _push(tmp_path, _answer(status, body))
    assert result == expected
    assert type(result) is type(expected)
    assert transport.requests


def test_a_transport_failure_is_unavailable_after_retries(tmp_path: Path) -> None:
    result, transport = _push(tmp_path, TransportError("down"))
    assert result == C.UNAVAILABLE
    assert len(transport.requests) == 3


def _refuse(what: str) -> object:
    def raiser(self: object, *args: object, **kwargs: object) -> object:
        raise AssertionError(f"body touched via {what}")

    return raiser


class _Tripwire(bytes):
    def __getattribute__(self, name: str) -> object:
        if not name.startswith("__"):
            raise AssertionError(f"body touched via {name}")
        return super().__getattribute__(name)


for _dunder in (
    "bool",
    "len",
    "getitem",
    "iter",
    "eq",
    "ne",
    "contains",
    "hash",
    "bytes",
    "str",
    "repr",
    "format",
):
    setattr(_Tripwire, f"__{_dunder}__", _refuse(_dunder))


def test_the_answer_body_is_never_read(tmp_path: Path) -> None:
    # Buffer-protocol reads (memoryview, hashlib, zlib, bytearray) cannot be
    # intercepted on 3.11, so the per-status result check below is the backstop.
    expected: dict[int, object] = {
        200: UpdateResult.CONFIRMED,
        404: UpdateResult.ABSENT,
        401: C.AUTH_REJECTED,
        403: C.PERMISSION_DENIED,
        400: C.REJECTED,
        429: C.RATE_LIMITED,
        500: C.UNAVAILABLE,
        204: C.UNCONFIRMED,
    }
    for status, want in expected.items():
        response = HttpResponse(status=status, headers={}, body=_Tripwire(_SENTINEL))
        result, _ = _push(tmp_path, response)
        assert result == want, status


# --- 2.6: the base file and the one upload ---------------------------------

PUBLICATION_ID = "0123456789abcdef0123456789abcdef"
FILE_BYTES = b".FIT\x0e\x10\r\n\x00\xff line\nbreak\rcr \x80 end"


def _archive(root: Path, data: bytes = FILE_BYTES) -> tuple[Path, str]:
    sha = hashlib.sha256(data).hexdigest()
    path = root / "fit-archive" / f"{sha}.fit"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, sha


def _with_file(path: Path | None, *shas: str) -> CompletedActivity:
    return CompletedActivity(
        sport="Run",
        start=datetime(2026, 3, 1, 7, 0, tzinfo=UTC),
        elapsed_s=1800.0,
        distance_m=5000.0,
        source_shas=shas,
        base_fit=path,
    )


def test_the_base_file_is_read_when_present_readable_and_the_base_digest(
    tmp_path: Path,
) -> None:
    path, sha = _archive(tmp_path)
    assert _base_file(_with_file(path, "e" * 64, sha)) == FILE_BYTES


def test_a_tampered_but_readable_archive_file_is_not_uploaded(tmp_path: Path) -> None:
    path, sha = _archive(tmp_path)
    path.write_bytes(FILE_BYTES + b"tampered")
    assert path.read_bytes() != FILE_BYTES
    assert hashlib.sha256(path.read_bytes()).hexdigest() != sha
    assert _base_file(_with_file(path, sha)) is None


def test_a_file_hashing_to_an_earlier_digest_only_is_not_the_base(
    tmp_path: Path,
) -> None:
    path, sha = _archive(tmp_path)
    assert _base_file(_with_file(path, sha, "e" * 64)) is None


def test_no_file_when_the_path_or_the_digests_are_missing(tmp_path: Path) -> None:
    path, sha = _archive(tmp_path)
    assert _base_file(_with_file(None, sha)) is None
    assert _base_file(_with_file(path)) is None
    assert _base_file(_with_file(tmp_path / "fit-archive" / "gone.fit", sha)) is None
    assert _base_file(_with_file(tmp_path / "fit-archive", sha)) is None


def _split(body: bytes, content_type: str) -> tuple[str, bytes, bytes]:
    """(boundary, the part's header block, the part's data) read independently
    of the code under test."""
    prefix = "multipart/form-data; boundary="
    assert content_type.startswith(prefix)
    boundary = content_type[len(prefix) :]
    opening = f"--{boundary}\r\n".encode()
    closing = f"\r\n--{boundary}--\r\n".encode()
    assert body.startswith(opening) and body.endswith(closing)
    inner = body[len(opening) : -len(closing)]
    head, separator, data = inner.partition(b"\r\n\r\n")
    assert separator
    return boundary, head, data


def test_the_multipart_body_is_one_part_holding_the_file_bytes_unmodified() -> None:
    body, content_type = _multipart_body(FILE_BYTES, PUBLICATION_ID)
    boundary, head, data = _split(body, content_type)
    assert boundary == f"fitdocs-{PUBLICATION_ID}"
    assert head == (
        b'Content-Disposition: form-data; name="file"; filename="activity.fit"'
        b"\r\nContent-Type: application/octet-stream"
    )
    assert data == FILE_BYTES
    assert b"\r\n" in FILE_BYTES and b"\r" in FILE_BYTES.replace(b"\r\n", b"")
    assert body.count(f"--{boundary}".encode()) == 2


def test_the_multipart_body_is_deterministic() -> None:
    assert _multipart_body(FILE_BYTES, PUBLICATION_ID) == _multipart_body(
        FILE_BYTES, PUBLICATION_ID
    )
    other = _multipart_body(FILE_BYTES, "f" * 32)
    assert other != _multipart_body(FILE_BYTES, PUBLICATION_ID)


def test_the_boundary_is_rechosen_when_the_file_holds_the_first_delimiter() -> None:
    first = f"--fitdocs-{PUBLICATION_ID}".encode()
    data = b"head\r\n" + first + b"\r\ntail"
    assert first in data
    body, content_type = _multipart_body(data, PUBLICATION_ID)
    boundary, _, part = _split(body, content_type)
    assert boundary == f"fitdocs-{PUBLICATION_ID}-1"
    assert part == data
    assert f"--{boundary}".encode() not in data


def test_the_boundary_walks_on_until_one_is_absent_from_the_file() -> None:
    delimiters = [
        f"--fitdocs-{PUBLICATION_ID}".encode(),
        f"--fitdocs-{PUBLICATION_ID}-1".encode(),
    ]
    data = b"\r\n".join(delimiters)
    body, content_type = _multipart_body(data, PUBLICATION_ID)
    boundary, _, part = _split(body, content_type)
    assert boundary == f"fitdocs-{PUBLICATION_ID}-2"
    assert part == data


def test_the_first_boundary_is_kept_when_the_file_holds_another_ids_delimiter() -> None:
    other = f"--fitdocs-{'a' * 32}".encode()
    assert f"--fitdocs-{PUBLICATION_ID}".encode() not in other
    body, content_type = _multipart_body(other, PUBLICATION_ID)
    boundary, _, part = _split(body, content_type)
    assert boundary == f"fitdocs-{PUBLICATION_ID}"
    assert part == other


def _send(
    tmp_path: Path,
    *script: HttpResponse | TransportError,
    data: bytes = FILE_BYTES,
) -> tuple[object, _Sequence]:
    transport = _Sequence(*script)
    session = _listing_session(transport, tmp_path)  # type: ignore[arg-type]
    headers = _auth_headers(session, Secret(_API_KEY))
    return _upload(session, headers, data, PUBLICATION_ID), transport


_ONE = json.dumps({"activities": [{"id": "i777"}]}).encode()


def test_the_upload_request_address_decoded_query_body_and_headers(
    tmp_path: Path,
) -> None:
    result, transport = _send(tmp_path, _answer(201, _ONE))
    assert result == UploadAnswer(created=True, activity_id="i777")
    (request,) = transport.requests
    assert request.method == "POST"
    parts = urlsplit(request.url)
    assert (parts.scheme, parts.netloc) == ("https", "intervals.icu")
    assert parts.path == "/api/v1/athlete/0/activities"
    assert parse_qs(parts.query, keep_blank_values=True) == {
        "external_id": [PUBLICATION_ID]
    }
    assert parts.fragment == ""
    assert request.single_attempt is True
    assert request.body is not None
    expected_body, content_type = _multipart_body(FILE_BYTES, PUBLICATION_ID)
    assert request.body == expected_body
    assert request.headers["Content-Type"] == content_type
    _, _, part = _split(request.body, request.headers["Content-Type"])
    assert part == FILE_BYTES
    token = base64.b64encode(f"API_KEY:{_API_KEY}".encode()).decode()
    assert list(request.secret_headers) == ["Authorization"]
    assert request.secret_headers["Authorization"].reveal() == f"Basic {token}"
    assert _API_KEY not in request.url and token not in request.url


def test_no_title_or_description_is_in_the_upload_address(tmp_path: Path) -> None:
    # The title, description and publication id are three different strings.
    assert len({TITLE, DESCRIPTION, PUBLICATION_ID}) == 3
    _, transport = _send(tmp_path, _answer(200, _ONE))
    url = transport.requests[0].url
    for needle in (TITLE, "Line one", "Morning", "name=", "description="):
        assert needle not in url
    assert list(parse_qs(urlsplit(url).query)) == ["external_id"]


def test_the_boundary_collision_reaches_the_wire(tmp_path: Path) -> None:
    data = f"x--fitdocs-{PUBLICATION_ID}y".encode()
    _, transport = _send(tmp_path, _answer(200, _ONE), data=data)
    (request,) = transport.requests
    content_type = request.headers["Content-Type"]
    assert content_type.endswith(f"boundary=fitdocs-{PUBLICATION_ID}-1")
    assert request.body is not None
    assert _split(request.body, content_type)[2] == data


def test_200_is_not_created_and_201_is_created(tmp_path: Path) -> None:
    updated, _ = _send(tmp_path, _answer(200, _ONE))
    created, _ = _send(tmp_path, _answer(201, _ONE))
    assert updated == UploadAnswer(created=False, activity_id="i777")
    assert created == UploadAnswer(created=True, activity_id="i777")


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (_answer(503), C.UNCONFIRMED),
        (_answer(429), C.RATE_LIMITED),
        (TransportError("down"), C.UNCONFIRMED),
    ],
)
def test_a_retryable_failure_makes_exactly_one_transport_call(
    tmp_path: Path, script: HttpResponse | TransportError, expected: PublishCode
) -> None:
    result, transport = _send(tmp_path, script)
    assert result == expected
    assert type(result) is PublishCode
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, C.AUTH_REJECTED),
        (403, C.PERMISSION_DENIED),
        (404, C.REJECTED),
        (400, C.REJECTED),
        (422, C.REJECTED),
        (429, C.RATE_LIMITED),
        (500, C.UNCONFIRMED),
        (502, C.UNCONFIRMED),
        (204, C.UNCONFIRMED),
        (302, C.UNCONFIRMED),
    ],
)
def test_each_failing_status_answers_the_creation_column(
    tmp_path: Path, status: int, expected: PublishCode
) -> None:
    result, transport = _send(tmp_path, _answer(status, _ONE))
    assert result == expected
    assert len(transport.requests) == 1


def _activities(*ids: object) -> bytes:
    return json.dumps({"activities": [{"id": i} for i in ids]}).encode()


def test_one_usable_id_is_named() -> None:
    assert _uploaded_activity(_activities("i123")) == "i123"


def test_the_same_id_repeated_is_one_id() -> None:
    assert _uploaded_activity(_activities("i123", "i123")) == "i123"


def test_two_distinct_ids_name_none() -> None:
    assert _uploaded_activity(_activities("i123", "i124")) is None
    assert _uploaded_activity(_activities("i124", "i123")) is None


@pytest.mark.parametrize(
    "body",
    [
        _activities(),
        _activities("i/1"),
        _activities(""),
        _activities("a" * 65),
        _activities("i 1"),
        _activities(5),
        _activities(None),
        _activities("i123", "i/1"),
        _activities("i/1", "i123"),
        _activities("i123", 5),
        json.dumps({"activities": [{}]}).encode(),
        json.dumps({"activities": ["i123"]}).encode(),
        json.dumps({"activities": [{"id": "i123"}, 5]}).encode(),
        json.dumps({"activities": [5, {"id": "i123"}]}).encode(),
        json.dumps({"activities": {"id": "i123"}}).encode(),
        json.dumps({"activities": None}).encode(),
        json.dumps({"id": "i123"}).encode(),
        json.dumps({"activity": [{"id": "i123"}]}).encode(),
        json.dumps({}).encode(),
        b"[]",
        b'[{"id": "i123"}]',
        b"null",
        b'"i123"',
        b"5",
        b"",
        b"not json",
        b"\xff\xfe",
        json.dumps({"activities": [{"id": "i123"}]}).encode("utf-16"),
        b'{"activities": [{"id": "i123", "x": "caf\xe9"}]}',
        b"[" * 200000,
        b'{"activities":' * 100000,
    ],
)
def test_an_answer_without_one_usable_id_names_none(body: bytes) -> None:
    assert _uploaded_activity(body) is None


def test_the_answer_parser_runs_on_a_201_body_and_none_is_still_created(
    tmp_path: Path,
) -> None:
    result, _ = _send(tmp_path, _answer(201, b"[]"))
    assert result == UploadAnswer(created=True, activity_id=None)
    result, _ = _send(tmp_path, _answer(200, _activities("i1", "i2")))
    assert result == UploadAnswer(created=False, activity_id=None)


def test_an_error_status_is_judged_by_status_not_by_its_body(tmp_path: Path) -> None:
    result, _ = _send(tmp_path, _answer(500, _ONE))
    assert result == C.UNCONFIRMED


def test_the_boundary_check_is_on_the_delimiter_not_the_bare_boundary() -> None:
    data = f"x-fitdocs-{PUBLICATION_ID}y fitdocs-{PUBLICATION_ID}".encode()
    assert f"fitdocs-{PUBLICATION_ID}".encode() in data
    assert f"--fitdocs-{PUBLICATION_ID}".encode() not in data
    body, content_type = _multipart_body(data, PUBLICATION_ID)
    boundary, _, part = _split(body, content_type)
    assert boundary == f"fitdocs-{PUBLICATION_ID}"
    assert part == data


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, C.AUTH_REJECTED),
        (403, C.PERMISSION_DENIED),
        (404, C.REJECTED),
        (400, C.REJECTED),
        (429, C.RATE_LIMITED),
        (500, C.UNCONFIRMED),
        (204, C.UNCONFIRMED),
        (302, C.UNCONFIRMED),
    ],
)
def test_the_body_of_a_failing_upload_answer_is_never_read(
    tmp_path: Path, status: int, expected: PublishCode
) -> None:
    response = HttpResponse(status=status, headers={}, body=_Tripwire(_SENTINEL))
    result, transport = _send(tmp_path, response)
    assert result == expected
    assert len(transport.requests) == 1


# --- 3.1: the publish operation, branch by branch ---------------------------

_LANDED = (C.POSTED, C.UPLOADED)
_OK_UPDATE_BODY = b'{"id":"i1","name":"Morning tempo"}'
_PLUS_TWO = timezone(timedelta(hours=2))
# 09:00+02:00 is 07:00Z: a non-UTC page start, so instant and wall clock differ.
_FLOW_START = datetime(2026, 3, 1, 9, 0, tzinfo=_PLUS_TWO)
_LINK = ACTIVITY_LINK_BASE
_LISTED = "i9000001"
_OTHER = "i9000002"
_STALE = "i8000001"
_RECORDED = "i5001"
_UPLOADED_ID = "i7000001"


class _Flow:
    """A transport routing by method: GET is the listing, PUT an update (by
    activity id), POST the upload. Each route answers from its own script, the
    last entry repeating; an unscripted route fails the test."""

    def __init__(
        self,
        *,
        listing: tuple[HttpResponse | TransportError, ...] = (),
        updates: dict[str, tuple[HttpResponse | TransportError, ...]] | None = None,
        upload: tuple[HttpResponse | TransportError, ...] = (),
    ) -> None:
        self.listing = listing
        self.updates = updates or {}
        self.upload = upload
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        path = urlsplit(request.url).path
        if request.method == "GET":
            script = self.listing
        elif request.method == "PUT":
            script = self.updates.get(path.rsplit("/", 1)[1], ())
        elif request.method == "POST":
            script = self.upload
        else:
            raise AssertionError(f"unexpected method {request.method}")
        if not script:
            raise AssertionError(f"unscripted request {request.method} {path}")
        calls = sum(
            1
            for r in self.requests
            if r.method == request.method and urlsplit(r.url).path == path
        )
        step = script[min(calls, len(script)) - 1]
        if isinstance(step, TransportError):
            raise step
        return step

    @property
    def gets(self) -> list[HttpRequest]:
        return [r for r in self.requests if r.method == "GET"]

    @property
    def puts(self) -> list[str]:
        """The activities updated, each once, in first-request order (the
        per-address raw counts are checked by ``assert_attempts``)."""
        ids: list[str] = []
        for r in self.requests:
            if r.method == "PUT":
                activity = urlsplit(r.url).path.rsplit("/", 1)[1]
                if activity not in ids:
                    ids.append(activity)
        return ids

    @property
    def posts(self) -> list[HttpRequest]:
        return [r for r in self.requests if r.method == "POST"]

    def _attempts(
        self, script: tuple[HttpResponse | TransportError, ...], once: bool
    ) -> int:
        """The raw requests one logical request makes against this script:
        the client repeats on a retryable answer, up to MAX_DATA_ATTEMPTS."""
        limit = 1 if once else MAX_DATA_ATTEMPTS
        for attempt in range(1, limit + 1):
            step = script[min(attempt, len(script)) - 1]
            retryable = isinstance(step, TransportError) or (
                step.status in RETRYABLE_STATUSES
            )
            if not retryable:
                return attempt
        return limit

    def assert_attempts(self) -> None:
        """Every address was requested exactly as often as ONE logical
        request makes raw requests: a second listing, update or upload
        doubles the count; an upload (single attempt) is never repeated."""
        seen: dict[tuple[str, str], int] = {}
        for r in self.requests:
            key = (r.method, urlsplit(r.url).path)
            seen[key] = seen.get(key, 0) + 1
        for (method, path), count in seen.items():
            if method == "GET":
                script, once = self.listing, False
            elif method == "PUT":
                script, once = self.updates[path.rsplit("/", 1)[1]], False
            else:
                script, once = self.upload, True
            assert count == self._attempts(script, once), (method, path, count)


class _Creds:
    scopes: tuple[str, ...] | None = None
    expires_at: datetime | None = None

    def value(self, field: str) -> Secret:
        assert field == "api_key"
        return Secret(_API_KEY)

    def replace(self, tokens: object) -> None:
        raise AssertionError("a publish never rotates credentials")


def _flow_session(
    transport: _Flow, root: Path, *, upload: bool = False, settings: object = None
) -> ConnectorSession:
    redactor = Redactor()
    return ConnectorSession(
        instance=INSTANCE,
        settings=IntervalsSettings(sources=frozenset({"X"}), publish_upload=upload)
        if settings is None
        else settings,
        http=HttpClient(
            transport,
            mode=CallMode.DATA,
            redactor=redactor,
            sleep=lambda seconds: None,
        ),
        credentials=_Creds(),
        data_root=root,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _flow_subject(
    *shas: str,
    distance_m: float | None = 5000.0,
    elapsed_s: float | None = 1800.0,
    start: datetime = _FLOW_START,
    base_fit: Path | None = None,
) -> CompletedActivity:
    return CompletedActivity(
        sport="Run",
        start=start,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
        source_shas=shas,
        base_fit=base_fit,
    )


def _publish(
    root: Path,
    flow: _Flow,
    subject: CompletedActivity | None = None,
    *,
    link: str | None = None,
    upload: bool = False,
) -> PublishResult:
    request = PublishRequest(
        publication_id=PUBLICATION_ID,
        post=Post(title=TITLE, description=DESCRIPTION),
        subject=subject or _flow_subject(),
        recorded_link=link,
    )
    result = IntervalsConnector().publish(
        _flow_session(flow, root, upload=upload), request
    )
    # What every answer must satisfy, whatever branch gave it.
    assert result.code in TARGET_CODES
    assert (result.link is not None) == (result.code in _LANDED), result
    if result.link is not None:
        assert valid_link(result.link)
    flow.assert_attempts()
    _assert_credentials_only_in_secret_headers(flow)
    return result


def _assert_credentials_only_in_secret_headers(flow: _Flow) -> None:
    token = base64.b64encode(f"API_KEY:{_API_KEY}".encode()).decode()
    for request in flow.requests:
        assert list(request.secret_headers) == ["Authorization"]
        assert request.secret_headers["Authorization"].reveal() == f"Basic {token}"
        assert _API_KEY not in request.url and token not in request.url
        for name, value in request.headers.items():
            assert name.lower() != "authorization"
            assert _API_KEY not in value and token not in value


def _ok_update() -> tuple[HttpResponse, ...]:
    return (_answer(200, _OK_UPDATE_BODY),)


def _gone() -> tuple[HttpResponse, ...]:
    return (_answer(404, b'{"error":"Not found"}'),)


def _strict_entry(activity_id: str = _LISTED) -> dict[str, object]:
    return {
        "id": activity_id,
        "source": "GARMIN_CONNECT",
        "start_date": "2026-03-01T07:00:00Z",
        "start_date_local": "2026-03-01T09:00:00",
        "distance": 5000.0,
        "elapsed_time": 1800,
        "external_id": None,
    }


def _listing_of(*entries: dict[str, object]) -> tuple[HttpResponse, ...]:
    return (_ok(list(entries)),)


def _created(activity_id: str = _UPLOADED_ID, status: int = 201) -> HttpResponse:
    return _answer(status, json.dumps({"activities": [{"id": activity_id}]}).encode())


def _unreadable_record(root: Path) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this = is [not a ledger\n")
    assert _record_activity(_session(root), _flow_subject(_BASE_SHA)) == (
        C.LOCAL_RECORD_UNREADABLE
    )


def _fail_if_called(*args: object, **kwargs: object) -> object:
    raise AssertionError("the base file was read")


# The link, the pull record and the facts check


def test_a_recorded_link_updates_that_activity_and_returns_the_link(
    tmp_path: Path,
) -> None:
    flow = _Flow(updates={_STALE: _ok_update()})
    result = _publish(tmp_path, flow, link=_LINK + _STALE)
    assert result == PublishResult(C.POSTED, _LINK + _STALE)
    assert flow.puts == [_STALE]
    assert flow.gets == [] and flow.posts == []
    sent = json.loads(flow.requests[0].body or b"")
    assert sent == {"name": TITLE, "description": DESCRIPTION}


def test_a_recorded_link_of_another_form_names_nothing(tmp_path: Path) -> None:
    for link in (
        "https://example.org/activities/i1",
        _LINK + "a/b",
        _LINK + "i1?x=1",
        _LINK,
    ):
        flow = _Flow(listing=_listing_of())
        result = _publish(tmp_path, flow, link=link)
        assert result.code is C.NOT_FOUND
        assert flow.puts == [] and len(flow.gets) == 1


def test_any_other_answer_to_the_linked_update_is_its_code_and_stops(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry(_RECORDED, _BASE_SHA))
    flow = _Flow(updates={_STALE: (_answer(403),), _RECORDED: _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), link=_LINK + _STALE)
    assert result == PublishResult(C.PERMISSION_DENIED)
    assert flow.puts == [_STALE]
    assert flow.gets == [] and flow.posts == []


def test_a_linked_activity_gone_falls_through_to_the_record(tmp_path: Path) -> None:
    _write(tmp_path, _entry(_RECORDED, _BASE_SHA))
    flow = _Flow(updates={_STALE: _gone(), _RECORDED: _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), link=_LINK + _STALE)
    assert result == PublishResult(C.POSTED, _LINK + _RECORDED)
    assert flow.puts == [_STALE, _RECORDED]
    assert flow.gets == []


def test_a_stale_identifier_the_record_names_is_not_updated_twice(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry(_STALE, _BASE_SHA))
    flow = _Flow(updates={_STALE: _gone()}, listing=_listing_of())
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), link=_LINK + _STALE)
    assert result.code is C.NOT_FOUND
    assert flow.puts == [_STALE]


def test_a_stale_identifier_the_listing_matches_is_not_updated_twice(
    tmp_path: Path,
) -> None:
    flow = _Flow(updates={_STALE: _gone()}, listing=_listing_of(_strict_entry(_STALE)))
    result = _publish(tmp_path, flow, link=_LINK + _STALE)
    assert result.code is C.NOT_FOUND
    assert flow.puts == [_STALE]
    assert len(flow.gets) == 1


def test_a_stale_record_identifier_the_listing_matches_is_not_updated_twice(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry(_STALE, _BASE_SHA))
    flow = _Flow(updates={_STALE: _gone()}, listing=_listing_of(_strict_entry(_STALE)))
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA))
    assert result.code is C.NOT_FOUND
    assert flow.puts == [_STALE]


def test_an_ambiguous_record_stops_before_any_request(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i5001", _BASE_SHA), _entry("i5002", _BASE_SHA))
    flow = _Flow(updates={"i5001": _ok_update(), "i5002": _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA))
    assert result == PublishResult(C.AMBIGUOUS)
    assert flow.requests == []


def test_the_record_updates_with_no_listing_and_the_ledger_is_untouched(
    tmp_path: Path,
) -> None:
    before = _write(tmp_path, _entry(_RECORDED, _BASE_SHA))
    snapshot = _snapshot(_path(tmp_path))
    flow = _Flow(updates={_RECORDED: _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA))
    assert result == PublishResult(C.POSTED, _LINK + _RECORDED)
    assert flow.gets == []
    assert _snapshot(_path(tmp_path)) == snapshot
    assert _path(tmp_path).read_bytes() == before


def test_the_pull_record_comes_before_the_facts_check(tmp_path: Path) -> None:
    _write(tmp_path, _entry(_RECORDED, _BASE_SHA))
    flow = _Flow(updates={_RECORDED: _ok_update()})
    page = _flow_subject(_BASE_SHA, distance_m=None, elapsed_s=None)
    result = _publish(tmp_path, flow, page)
    assert result == PublishResult(C.POSTED, _LINK + _RECORDED)
    assert flow.gets == []


def test_the_recorded_link_comes_before_the_facts_check(tmp_path: Path) -> None:
    flow = _Flow(updates={_STALE: _ok_update()})
    page = _flow_subject(distance_m=None, elapsed_s=None)
    result = _publish(tmp_path, flow, page, link=_LINK + _STALE)
    assert result == PublishResult(C.POSTED, _LINK + _STALE)


def test_a_page_without_facts_that_nothing_resolves_is_facts_missing(
    tmp_path: Path,
) -> None:
    _write(tmp_path, _entry(_RECORDED, _BASE_SHA))
    flow = _Flow(updates={_RECORDED: _gone()})
    page = _flow_subject(_BASE_SHA, distance_m=None, elapsed_s=None)
    result = _publish(tmp_path, flow, page, upload=True)
    assert result == PublishResult(C.ACTIVITY_FACTS_MISSING)
    assert flow.puts == [_RECORDED]
    assert flow.gets == [] and flow.posts == []


def test_one_fact_is_enough_to_list_and_none_is_not(tmp_path: Path) -> None:
    for distance_m, elapsed_s, listed in (
        (None, 1800.0, True),
        (5000.0, None, True),
        (None, None, False),
    ):
        flow = _Flow(listing=_listing_of())
        page = _flow_subject(distance_m=distance_m, elapsed_s=elapsed_s)
        result = _publish(tmp_path, flow, page)
        assert (len(flow.gets) == 1) is listed, (distance_m, elapsed_s)
        assert result.code is (C.NOT_FOUND if listed else C.ACTIVITY_FACTS_MISSING)


def test_a_start_without_an_offset_is_facts_missing(tmp_path: Path) -> None:
    flow = _Flow()
    page = _flow_subject(start=datetime(2026, 3, 1, 9, 0))
    assert _publish(tmp_path, flow, page).code is C.ACTIVITY_FACTS_MISSING
    assert flow.requests == []


# The listing match


def test_a_failed_listing_is_its_code(tmp_path: Path) -> None:
    for status, code, raw in (
        (403, C.PERMISSION_DENIED, 1),
        (429, C.RATE_LIMITED, MAX_DATA_ATTEMPTS),
    ):
        flow = _Flow(listing=(_answer(status),))
        assert _publish(tmp_path, flow, upload=True).code is code
        assert len(flow.gets) == raw and flow.posts == [] and flow.puts == []


def test_a_listing_not_in_documented_form_is_unavailable(tmp_path: Path) -> None:
    flow = _Flow(listing=(_answer(200, b'{"not":"a list"}'),))
    assert _publish(tmp_path, flow, upload=True).code is C.UNAVAILABLE
    assert flow.posts == []


def test_a_strict_listing_match_is_updated_through_the_listing(tmp_path: Path) -> None:
    flow = _Flow(listing=_listing_of(_strict_entry()), updates={_LISTED: _ok_update()})
    result = _publish(tmp_path, flow)
    assert result == PublishResult(C.POSTED, _LINK + _LISTED)
    assert flow.puts == [_LISTED] and len(flow.gets) == 1


def test_the_publication_id_matches_where_the_facts_do_not(tmp_path: Path) -> None:
    far = {**_strict_entry(_OTHER), "start_date": "2026-03-01T12:00:00Z"}
    far["start_date_local"] = "2026-03-01T14:00:00"
    far["external_id"] = PUBLICATION_ID
    flow = _Flow(listing=_listing_of(far), updates={_OTHER: _ok_update()})
    assert _publish(tmp_path, flow).link == _LINK + _OTHER


def test_two_listing_matches_are_ambiguous_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    flow = _Flow(
        listing=_listing_of(_strict_entry(_LISTED), _strict_entry(_OTHER)),
        updates={_LISTED: _ok_update(), _OTHER: _ok_update()},
    )
    result = _publish(tmp_path, flow, upload=True)
    assert result == PublishResult(C.AMBIGUOUS)
    assert flow.puts == [] and flow.posts == []


def test_a_strava_import_at_the_start_is_not_updatable_even_with_uploads(
    tmp_path: Path,
) -> None:
    strava = {**_strict_entry(_OTHER), "source": "STRAVA"}
    flow = _Flow(listing=_listing_of(strava))
    assert _publish(tmp_path, flow, upload=True).code is C.NOT_UPDATABLE
    assert flow.puts == [] and flow.posts == []


def test_a_listing_match_that_answers_other_than_ok_is_its_code(
    tmp_path: Path,
) -> None:
    flow = _Flow(
        listing=_listing_of(_strict_entry()), updates={_LISTED: (_answer(401),)}
    )
    assert _publish(tmp_path, flow, upload=True).code is C.AUTH_REJECTED
    assert flow.posts == []


# The absent branch


def test_nothing_found_with_uploads_off_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intervals, "_base_file", _fail_if_called)
    flow = _Flow(listing=_listing_of())
    assert _publish(tmp_path, flow).code is C.NOT_FOUND
    assert flow.posts == [] and flow.puts == []


def test_a_listing_match_gone_with_uploads_off_is_not_found(tmp_path: Path) -> None:
    flow = _Flow(listing=_listing_of(_strict_entry()), updates={_LISTED: _gone()})
    assert _publish(tmp_path, flow).code is C.NOT_FOUND
    assert flow.puts == [_LISTED] and flow.posts == []


def test_a_missing_base_file_is_activity_file_missing(tmp_path: Path) -> None:
    flow = _Flow(listing=_listing_of())
    result = _publish(tmp_path, flow, _flow_subject(base_fit=None), upload=True)
    assert result.code is C.ACTIVITY_FILE_MISSING
    assert flow.posts == []


def test_a_tampered_base_file_is_activity_file_missing(tmp_path: Path) -> None:
    path, _ = _archive(tmp_path)
    flow = _Flow(listing=_listing_of())
    page = _flow_subject("e" * 64, base_fit=path)
    assert _publish(tmp_path, flow, page, upload=True).code is C.ACTIVITY_FILE_MISSING
    assert flow.posts == []


def _uploadable(root: Path) -> CompletedActivity:
    path, sha = _archive(root)
    return _flow_subject(sha, base_fit=path)


def test_a_created_upload_confirmed_is_uploaded_with_the_link(tmp_path: Path) -> None:
    flow = _Flow(
        listing=_listing_of(),
        upload=(_created(),),
        updates={_UPLOADED_ID: _ok_update()},
    )
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(C.UPLOADED, _LINK + _UPLOADED_ID)
    assert flow.puts == [_UPLOADED_ID] and len(flow.gets) == 1 and len(flow.posts) == 1
    (post,) = flow.posts
    assert parse_qs(urlsplit(post.url).query) == {"external_id": [PUBLICATION_ID]}
    assert flow.requests.index(post) > flow.requests.index(flow.gets[0])


def test_a_duplicate_upload_confirmed_is_posted_with_the_link(tmp_path: Path) -> None:
    flow = _Flow(
        listing=_listing_of(),
        upload=(_created(status=200),),
        updates={_UPLOADED_ID: _ok_update()},
    )
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(C.POSTED, _LINK + _UPLOADED_ID)


@pytest.mark.parametrize(
    "confirm",
    [
        _gone(),
        (_answer(403),),
        (_answer(401),),
        (_answer(429),),
        (_answer(400),),
        (_answer(500),),
        (TransportError("down"),),
        (_answer(204),),
    ],
    ids=["404", "403", "401", "429", "400", "500", "transport", "204"],
)
def test_any_failed_confirmation_after_a_creation_is_unconfirmed(
    tmp_path: Path, confirm: tuple[HttpResponse | TransportError, ...]
) -> None:
    flow = _Flow(
        listing=_listing_of(), upload=(_created(),), updates={_UPLOADED_ID: confirm}
    )
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(C.UNCONFIRMED)
    assert len(flow.posts) == 1


@pytest.mark.parametrize(
    ("confirm", "code"),
    [
        (_gone(), C.UNCONFIRMED),
        ((_answer(403),), C.PERMISSION_DENIED),
        ((_answer(500),), C.UNAVAILABLE),
        ((_answer(429),), C.RATE_LIMITED),
    ],
    ids=["404", "403", "500", "429"],
)
def test_a_failed_confirmation_after_a_duplicate_maps_as_any_update(
    tmp_path: Path, confirm: tuple[HttpResponse, ...], code: PublishCode
) -> None:
    flow = _Flow(
        listing=_listing_of(),
        upload=(_created(status=200),),
        updates={_UPLOADED_ID: confirm},
    )
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(code)


@pytest.mark.parametrize(
    "answer",
    [
        _answer(201, b'{"activities":[]}'),
        _answer(201, b"not json"),
        _answer(201, json.dumps({"activities": [{"id": "i1"}, {"id": "i2"}]}).encode()),
        _answer(200, b'{"activities":[{"id":"bad id"}]}'),
    ],
    ids=["empty", "not-json", "two-ids", "bad-id"],
)
def test_an_upload_answer_naming_no_usable_activity_is_unconfirmed(
    tmp_path: Path, answer: HttpResponse
) -> None:
    flow = _Flow(listing=_listing_of(), upload=(answer,))
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(C.UNCONFIRMED)
    assert flow.puts == []


def test_an_upload_naming_an_activity_already_answered_absent_is_unconfirmed(
    tmp_path: Path,
) -> None:
    flow = _Flow(
        listing=_listing_of(),
        upload=(_created(_STALE),),
        updates={_STALE: _gone()},
    )
    page = _uploadable(tmp_path)
    result = _publish(tmp_path, flow, page, link=_LINK + _STALE, upload=True)
    assert result == PublishResult(C.UNCONFIRMED)
    assert flow.puts == [_STALE]
    assert len(flow.posts) == 1


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (_answer(403), C.PERMISSION_DENIED),
        (_answer(401), C.AUTH_REJECTED),
        (_answer(400), C.REJECTED),
        (_answer(500), C.UNCONFIRMED),
        (TransportError("down"), C.UNCONFIRMED),
    ],
    ids=["403", "401", "400", "500", "transport"],
)
def test_a_failed_upload_is_its_code_and_is_sent_in_one_request(
    tmp_path: Path, answer: HttpResponse | TransportError, code: PublishCode
) -> None:
    flow = _Flow(listing=_listing_of(), upload=(answer,))
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(code)
    assert len(flow.requests) == 2  # one listing, one upload: no repeat
    assert len(flow.posts) == 1 and flow.puts == []


def test_an_activity_listed_and_gone_may_still_be_created(tmp_path: Path) -> None:
    flow = _Flow(
        listing=_listing_of(_strict_entry()),
        updates={_LISTED: _gone(), _UPLOADED_ID: _ok_update()},
        upload=(_created(),),
    )
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(C.UPLOADED, _LINK + _UPLOADED_ID)
    assert flow.puts == [_LISTED, _UPLOADED_ID]


# An unreadable pull record


@pytest.mark.parametrize("uploads", [True, False])
def test_an_unreadable_record_with_nothing_else_resolving_never_uploads_or_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uploads: bool
) -> None:
    page = _uploadable(tmp_path)
    _unreadable_record(tmp_path)
    monkeypatch.setattr(intervals, "_base_file", _fail_if_called)
    flow = _Flow(listing=_listing_of(), upload=(_created(),))
    result = _publish(tmp_path, flow, page, upload=uploads)
    assert result == PublishResult(C.LOCAL_RECORD_UNREADABLE)
    assert len(flow.gets) == 1
    assert flow.posts == [] and flow.puts == []


def test_an_unreadable_record_does_not_stop_the_recorded_link(tmp_path: Path) -> None:
    _unreadable_record(tmp_path)
    flow = _Flow(updates={_STALE: _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), link=_LINK + _STALE)
    assert result == PublishResult(C.POSTED, _LINK + _STALE)
    assert flow.gets == []


def test_an_unreadable_record_does_not_stop_a_listing_match(tmp_path: Path) -> None:
    _unreadable_record(tmp_path)
    flow = _Flow(listing=_listing_of(_strict_entry()), updates={_LISTED: _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), upload=True)
    assert result == PublishResult(C.POSTED, _LINK + _LISTED)


def test_an_unreadable_record_and_a_vanished_listing_match_is_unreadable(
    tmp_path: Path,
) -> None:
    _unreadable_record(tmp_path)
    flow = _Flow(listing=_listing_of(_strict_entry()), updates={_LISTED: _gone()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), upload=True)
    assert result == PublishResult(C.LOCAL_RECORD_UNREADABLE)
    assert flow.posts == []


def test_an_unreadable_record_and_a_vanished_link_is_unreadable(tmp_path: Path) -> None:
    _unreadable_record(tmp_path)
    flow = _Flow(updates={_STALE: _gone()}, listing=_listing_of())
    result = _publish(
        tmp_path, flow, _flow_subject(_BASE_SHA), link=_LINK + _STALE, upload=True
    )
    assert result == PublishResult(C.LOCAL_RECORD_UNREADABLE)
    assert flow.puts == [_STALE] and flow.posts == []


def test_an_unreadable_record_does_not_hide_ambiguity_or_listing_failure(
    tmp_path: Path,
) -> None:
    _unreadable_record(tmp_path)
    flow = _Flow(listing=(_answer(403),))
    assert _publish(tmp_path, flow, _flow_subject(_BASE_SHA)).code is (
        C.PERMISSION_DENIED
    )


def test_an_unreadable_record_with_a_page_lacking_facts_is_facts_missing(
    tmp_path: Path,
) -> None:
    _unreadable_record(tmp_path)
    flow = _Flow()
    page = _flow_subject(_BASE_SHA, distance_m=None, elapsed_s=None)
    assert _publish(tmp_path, flow, page).code is C.ACTIVITY_FACTS_MISSING
    assert flow.requests == []


# Identifiers, links and the declaration


def test_an_identifier_that_is_not_usable_is_neither_updated_nor_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(intervals, "_match_listing", lambda *a, **k: "bad id/x")
    flow = _Flow(listing=_listing_of())
    result = _publish(tmp_path, flow)
    assert result.code is C.NOT_FOUND
    assert flow.puts == []


def test_every_link_built_passes_the_engines_link_rule() -> None:
    for activity_id in ("i1", "A" * 64, "0", "i9000001", "abcXYZ019"):
        assert _usable_activity_id(activity_id)
        link = _activity_link(activity_id)
        assert valid_link(link)
        assert _linked_activity(link) == activity_id


def test_a_page_with_another_connectors_settings_is_a_defect(tmp_path: Path) -> None:
    request = PublishRequest(
        publication_id=PUBLICATION_ID,
        post=Post(title=TITLE, description=DESCRIPTION),
        subject=_flow_subject(),
        recorded_link=None,
    )
    flow = _Flow()
    session = _flow_session(flow, tmp_path, settings=object())
    with pytest.raises(ConnectorError):
        IntervalsConnector().publish(session, request)
    assert flow.requests == []


def test_the_declaration_has_five_capabilities_and_the_fixed_label() -> None:
    connector = IntervalsConnector()
    assert connector.capabilities == frozenset(
        {
            Capability.PULL_ACTIVITIES,
            Capability.PULL_WELLNESS,
            Capability.PUSH_ACTIVITY,
            Capability.ANNOTATE_REMOTE_ACTIVITY,
            Capability.RESOLVE_REMOTE_ACTIVITY,
        }
    )
    assert connector.capabilities & PUBLISH_CAPABILITIES == PUBLISH_CAPABILITIES
    assert connector.link_label == LINK_LABEL == "intervals.icu"
    assert valid_label(connector.link_label)


def test_the_connector_passes_registration_and_is_listed_as_a_target() -> None:
    connector = IntervalsConnector()
    assert validate_connector(connector) is None
    instance = ConnectorInstance(
        name="icu-main",
        connector=connector,
        lookback_days=30,
        settings=IntervalsSettings(sources=frozenset({"X"})),
    )
    (row,) = list_targets([instance], store=None, environ={})
    assert row.name == "icu-main" and row.connector == "intervals"
    assert row.capabilities == (
        "push-activity",
        "annotate-remote-activity",
        "resolve-remote-activity",
    )


def test_the_module_docstring_says_it_publishes_posts() -> None:
    opening = " ".join((intervals.__doc__ or "").split("\n\n")[1].split())
    assert opening.startswith("Lists, filters and fetches")
    assert "publishes posts" in opening


# Retryable answers: the client's own repeats are the only repeats


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (_answer(500), C.UNAVAILABLE),
        (_answer(429), C.RATE_LIMITED),
        (TransportError("down"), C.UNAVAILABLE),
    ],
    ids=["500", "429", "transport"],
)
def test_a_retryable_answer_to_the_linked_update_is_repeated_only_by_the_client(
    tmp_path: Path, answer: HttpResponse | TransportError, code: PublishCode
) -> None:
    flow = _Flow(updates={_STALE: (answer,)})
    result = _publish(tmp_path, flow, link=_LINK + _STALE)
    assert result == PublishResult(code)
    assert len(flow.requests) == MAX_DATA_ATTEMPTS
    assert flow.puts == [_STALE] and flow.gets == []


@pytest.mark.parametrize(
    ("answer", "code"),
    [(_answer(429), C.RATE_LIMITED), (_answer(503), C.UNAVAILABLE)],
    ids=["429", "503"],
)
def test_a_retryable_answer_to_the_record_update_is_repeated_only_by_the_client(
    tmp_path: Path, answer: HttpResponse, code: PublishCode
) -> None:
    _write(tmp_path, _entry(_RECORDED, _BASE_SHA))
    flow = _Flow(updates={_RECORDED: (answer,)})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA))
    assert result == PublishResult(code)
    assert len(flow.requests) == MAX_DATA_ATTEMPTS
    assert flow.gets == []


def test_a_retryable_answer_to_the_listing_update_is_repeated_only_by_the_client(
    tmp_path: Path,
) -> None:
    flow = _Flow(
        listing=_listing_of(_strict_entry()), updates={_LISTED: (_answer(502),)}
    )
    result = _publish(tmp_path, flow, upload=True)
    assert result == PublishResult(C.UNAVAILABLE)
    assert len(flow.requests) == 1 + MAX_DATA_ATTEMPTS
    assert flow.posts == []


def test_a_retryable_confirmation_after_a_creation_is_repeated_only_by_the_client(
    tmp_path: Path,
) -> None:
    flow = _Flow(
        listing=_listing_of(),
        upload=(_created(),),
        updates={_UPLOADED_ID: (_answer(503),)},
    )
    result = _publish(tmp_path, flow, _uploadable(tmp_path), upload=True)
    assert result == PublishResult(C.UNCONFIRMED)
    assert len(flow.posts) == 1
    assert len(flow.requests) == 2 + MAX_DATA_ATTEMPTS


def test_an_ambiguous_record_does_not_stop_the_recorded_link(tmp_path: Path) -> None:
    _write(tmp_path, _entry("i5001", _BASE_SHA), _entry("i5002", _BASE_SHA))
    flow = _Flow(updates={_STALE: _ok_update()})
    result = _publish(tmp_path, flow, _flow_subject(_BASE_SHA), link=_LINK + _STALE)
    assert result == PublishResult(C.POSTED, _LINK + _STALE)
    assert flow.puts == [_STALE]


# --- 3.2: the publish path carries no service text (Req 8.1) ----------------

_FORBIDDEN_ON_PUBLISH = (
    "_service_text",
    "_service_message",
    "_raise_for_status",
    "_raise_for_wellness_status",
    "auth_failure_from",
)
_REACHABLE_ON_PUBLISH = ("_update", "_list", "_upload", "_auth_headers")
# Four levels below publish (publish -> _list -> _listed_activities ->
# _listed_activity -> here), the deepest helper the walk reaches.
_DEEP_REACHABLE = "_local_wall_clock"


def _reachable(
    tree: ast.Module, class_name: str, method: str
) -> tuple[dict[str, int], set[str]]:
    """Every module-level function and class (and sibling method, through
    ``self``) reachable from ``class_name.method`` by naming it anywhere in a
    reachable body (a call, a callback, a nested function, ``Cls.m()``), with
    its distance from the start; and every name or attribute any reachable
    body mentions, imported ones and ``module.name`` ones too. A reached class
    is walked whole, every method of it."""
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    methods = {
        node.name: node
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == class_name
        for node in cls.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name != class_name
    }
    depth = {f"{class_name}.{method}": 0}
    mentioned: set[str] = set()
    queue: list[tuple[ast.AST, int]] = [(methods[method], 0)]
    while queue:
        node, distance = queue.pop(0)
        for sub in ast.walk(node):
            targets: list[tuple[str, ast.AST | None]] = []
            if isinstance(sub, ast.Name):
                mentioned.add(sub.id)
                targets.append((sub.id, functions.get(sub.id) or classes.get(sub.id)))
            elif isinstance(sub, ast.Attribute):
                mentioned.add(sub.attr)
                if isinstance(sub.value, ast.Name) and sub.value.id == "self":
                    targets.append((f"{class_name}.{sub.attr}", methods.get(sub.attr)))
            for name, target in targets:
                if target is not None and name not in depth:
                    depth[name] = distance + 1
                    queue.append((target, distance + 1))
    return depth, mentioned


def test_the_walk_finds_what_it_must_and_only_that() -> None:
    # The walker itself, on a module whose answer is known.
    tree = ast.parse(
        "from lib import imported\n"
        "def a(): return b()\n"
        "def b(): return c\n"
        "def c(): return deep()\n"
        "def deep(): return imported()\n"
        "def decoy(): return a()\n"
        "def forbidden(): pass\n"
        "def hidden(): return mod.forbidden()\n"
        "class Helper:\n"
        "    @staticmethod\n"
        "    def m(): return hidden()\n"
        "def callback(): pass\n"
        "def nested_target(): pass\n"
        "def via_method(): pass\n"
        "class K:\n"
        "    def start(self):\n"
        "        def inner(): return nested_target()\n"
        "        Helper.m()\n"
        "        return map(callback, [a, self.other()])\n"
        "    def other(self): return via_method()\n"
        "    def unused(self): return decoy()\n"
    )
    depth, mentioned = _reachable(tree, "K", "start")
    assert depth == {
        "K.start": 0,
        "callback": 1,
        "a": 1,
        "nested_target": 1,
        "K.other": 1,
        "b": 2,
        "via_method": 2,
        "c": 3,
        "deep": 4,
        "Helper": 1,
        "hidden": 2,
    }
    assert "imported" in mentioned and "decoy" not in mentioned
    # a qualified call is a mention of its attribute, whatever the module
    assert "forbidden" in mentioned


def test_the_publish_path_never_reaches_the_service_text_helpers() -> None:
    source = Path(intervals.__file__).read_text(encoding="utf-8")
    depth, mentioned = _reachable(ast.parse(source), "IntervalsConnector", "publish")
    # Not vacuous: the walk went through the module, several levels deep.
    assert len(depth) >= 18, sorted(depth)
    assert max(depth.values()) >= 3, depth
    for name in _REACHABLE_ON_PUBLISH:
        assert name in depth, f"{name} is not reached: the walk is wrong"
    assert depth.get(_DEEP_REACHABLE, 0) >= 3, depth
    for name in _FORBIDDEN_ON_PUBLISH:
        assert name not in mentioned, f"the publish path reaches {name}"
    # The forbidden names are real: each is defined or imported in the module.
    module_tree = ast.parse(source)
    defined = {
        node.name for node in module_tree.body if isinstance(node, ast.FunctionDef)
    } | {
        alias.asname or alias.name
        for node in module_tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert set(_FORBIDDEN_ON_PUBLISH) <= defined


_SENT = "Sentinel7Leak"  # alphanumeric: it would pass for an activity id
_LOUD_STEPS = ("linked", "recorded", "listing", "matched", "upload", "confirm")
_LOUD_ROUTES = {
    "linked": ("PUT", _STALE),
    "recorded": ("PUT", _RECORDED),
    "listing": ("GET", None),
    "matched": ("PUT", _LISTED),
    "upload": ("POST", None),
    "confirm": ("PUT", _UPLOADED_ID),
}
_LOUD_STATUSES: tuple[int | None, ...] = (
    *(200, 201, 204, 400, 401, 403, 404, 429, 500, 503),
    None,  # a transport failure
)
_LOUD_BODIES = ("json", "text")


class _LoudFlow(_Flow):
    """A flow that remembers what it served to which request."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.served: list[tuple[HttpRequest, HttpResponse | TransportError]] = []

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        try:
            step = super().__call__(request, timeout)
        except TransportError as error:
            self.served.append((request, error))
            raise
        self.served.append((request, step))
        return step


def _loud(step: str, status: int | None, kind: str) -> HttpResponse | TransportError:
    """An answer whose body and every header carry the sentinel."""
    if status is None:
        return TransportError(f"connection lost: {_SENT}")
    body: object
    if kind == "text":
        body = None
    elif status == 200 and step == "listing":
        body = [{**_strict_entry(), "name": _SENT, "description": _SENT}]
    elif status in (200, 201) and step == "upload":
        body = {"activities": [{"id": _UPLOADED_ID, "name": _SENT}], "message": _SENT}
    elif status == 200:
        body = {"id": "i1", "name": _SENT}
    else:
        body = {"error": _SENT, "message": _SENT}
    return HttpResponse(
        status=status,
        headers={
            "x-sentinel": _SENT,
            "x-error": _SENT,
            "location": ACTIVITY_LINK_BASE + _SENT,
        },
        body=f"{_SENT} {_SENT}".encode() if body is None else json.dumps(body).encode(),
    )


def _loud_defaults() -> dict[str, HttpResponse | TransportError]:
    """Every step answers so that the flow goes on to the next one."""
    return {
        "linked": _loud("linked", 404, "json"),
        "recorded": _loud("recorded", 404, "json"),
        "listing": _loud("listing", 200, "json"),
        "matched": _loud("matched", 404, "json"),
        "upload": _loud("upload", 201, "json"),
        "confirm": _loud("confirm", 200, "json"),
    }


def _loud_run(
    root: Path, step: str, status: int | None, kind: str
) -> tuple[PublishResult, _LoudFlow, HttpResponse | TransportError]:
    root.mkdir(parents=True, exist_ok=True)
    path, sha = _archive(root)
    _write(root, _entry(_RECORDED, sha))
    target = _loud(step, status, kind)
    steps = {**_loud_defaults(), step: target}
    flow = _LoudFlow(
        listing=(steps["listing"],),
        updates={
            _STALE: (steps["linked"],),
            _RECORDED: (steps["recorded"],),
            _LISTED: (steps["matched"],),
            _UPLOADED_ID: (steps["confirm"],),
            # an identifier taken from a header would be updated and linked
            _SENT: (_loud("confirm", 200, "json"),),
        },
        upload=(steps["upload"],),
    )
    result = _publish(
        root, flow, _flow_subject(sha, base_fit=path), link=_LINK + _STALE, upload=True
    )
    return result, flow, target


def _assert_no_sentinel(result: PublishResult) -> None:
    fields = dataclasses.fields(result)
    assert len(fields) >= 2  # the code and the link, at least
    for field in fields:
        value = getattr(result, field.name)
        assert _SENT not in str(value) and _SENT not in repr(value), field.name
    assert _SENT not in repr(result)


def _assert_reached_with_sentinel(
    flow: _LoudFlow, step: str, target: HttpResponse | TransportError
) -> None:
    method, activity = _LOUD_ROUTES[step]
    to_step = [
        answer
        for request, answer in flow.served
        if request.method == method
        and (activity is None or urlsplit(request.url).path.endswith("/" + activity))
    ]
    assert to_step and all(answer is target for answer in to_step), step
    for _, answer in flow.served:
        if isinstance(answer, TransportError):
            assert _SENT in str(answer)
        else:
            assert _SENT.encode() in answer.body
            assert answer.headers and all(
                _SENT in value for value in answer.headers.values()
            )


@pytest.mark.parametrize("kind", _LOUD_BODIES)
@pytest.mark.parametrize("status", _LOUD_STATUSES)
@pytest.mark.parametrize("step", _LOUD_STEPS)
def test_no_answer_at_any_step_leaves_service_text_in_the_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    step: str,
    status: int | None,
    kind: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    result, flow, target = _loud_run(tmp_path, step, status, kind)
    _assert_reached_with_sentinel(flow, step, target)
    _assert_no_sentinel(result)
    captured = capsys.readouterr()
    assert _SENT not in captured.out and _SENT not in captured.err
    assert _SENT not in caplog.text


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, C.AUTH_REJECTED),
        (403, C.PERMISSION_DENIED),
        (404, C.REJECTED),
        (400, C.REJECTED),
        (429, C.RATE_LIMITED),
        (500, C.UNAVAILABLE),
        (204, C.UNAVAILABLE),
        (302, C.UNAVAILABLE),
    ],
)
def test_the_body_of_a_failing_listing_is_never_read(
    tmp_path: Path, status: int, code: PublishCode
) -> None:
    # Buffer-protocol reads cannot be intercepted on 3.11 (see the update
    # test above); the per-status code is the backstop.
    answer = HttpResponse(
        status=status, headers={"x-sentinel": _SENT}, body=_Tripwire(_SENT.encode())
    )
    flow = _Flow(listing=(answer,))
    assert _publish(tmp_path, flow) == PublishResult(code)
    assert flow.gets and not flow.puts and not flow.posts


def test_the_sentinel_runs_cover_every_answer_class_and_many_outcomes(
    tmp_path: Path,
) -> None:
    classes = {
        _answer_class(kind, status)
        for kind in (K.READ, K.UPDATE, K.CREATE)
        for status in _LOUD_STATUSES
        if status is not None
    } | {A.NETWORK_FAILURE}
    assert classes == set(AnswerClass)
    codes: set[PublishCode] = set()
    runs = 0
    for step in _LOUD_STEPS:
        for status in _LOUD_STATUSES:
            for kind in _LOUD_BODIES:
                root = tmp_path / f"{runs}"
                codes.add(_loud_run(root, step, status, kind)[0].code)
                runs += 1
    assert runs == len(_LOUD_STEPS) * len(_LOUD_STATUSES) * len(_LOUD_BODIES)
    # Uploads are on and every step is reached, so not-found never answers.
    assert codes == {
        C.POSTED,
        C.UPLOADED,
        C.UNCONFIRMED,
        C.UNAVAILABLE,
        C.REJECTED,
        C.AUTH_REJECTED,
        C.PERMISSION_DENIED,
        C.RATE_LIMITED,
    }
