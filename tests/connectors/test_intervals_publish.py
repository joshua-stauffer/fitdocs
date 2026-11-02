"""intervals-publish tasks 2.1-2.3: intervals.icu's answers mapped into publish
codes, and the activity found through the pull record.

Req 7.1-7.7 (the answer table, by request kind) and 8.2, 8.3 (the remote
identifier rule and the direct link); 3.1-3.4 (the recorded link and the pull
record); 3.5, 7.4, 9.3, 9.5 (the listing around the page's start, through a
scripted transport).
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from urllib.parse import parse_qs, urlsplit

import pytest

from fitdocs.connectors.http import HttpRequest, HttpResponse, TransportError
from fitdocs.connectors.intervals import (
    ACTIVITY_ID_PATTERN,
    ACTIVITY_LINK_BASE,
    ANSWER_CODES,
    INTERVALS_CONNECTOR_ID,
    RESOLVE_FIELDS,
    SUCCESS_STATUSES,
    AnswerClass,
    CallKind,
    ListedActivity,
    UpdateResult,
    _activity_link,
    _answer_class,
    _answer_code,
    _auth_headers,
    _linked_activity,
    _list,
    _listed_activities,
    _listing_window,
    _match_listing,
    _record_activity,
    _update,
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
    TARGET_CODES,
    CompletedActivity,
    ConnectorSession,
    Post,
    PublishCode,
)
from fitdocs.connectors.secrets import Redactor, Secret

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


def test_the_answer_body_is_never_read(tmp_path: Path) -> None:
    # Buffer-protocol reads (memoryview, hashlib, zlib, bytearray) cannot be
    # intercepted on 3.11, so the per-status result check below is the backstop.
    def refuse(what: str) -> object:
        def raiser(self: object, *args: object, **kwargs: object) -> object:
            raise AssertionError(f"body touched via {what}")

        return raiser

    class _Tripwire(bytes):
        def __getattribute__(self, name: str) -> object:
            if not name.startswith("__"):
                raise AssertionError(f"body touched via {name}")
            return super().__getattribute__(name)

    for dunder in (
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
        setattr(_Tripwire, f"__{dunder}__", refuse(dunder))

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
