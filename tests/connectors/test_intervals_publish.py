"""intervals-publish tasks 2.1-2.2: intervals.icu's answers mapped into publish
codes, and the activity found through the pull record.

Req 7.1-7.7 (the answer table, by request kind) and 8.2, 8.3 (the remote
identifier rule and the direct link); 3.1-3.4 (the recorded link and the pull
record). No transport is involved.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from fitdocs.connectors.intervals import (
    ACTIVITY_ID_PATTERN,
    ACTIVITY_LINK_BASE,
    ANSWER_CODES,
    INTERVALS_CONNECTOR_ID,
    SUCCESS_STATUSES,
    AnswerClass,
    CallKind,
    _activity_link,
    _answer_class,
    _answer_code,
    _linked_activity,
    _record_activity,
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
    PublishCode,
)
from fitdocs.connectors.secrets import Redactor

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
