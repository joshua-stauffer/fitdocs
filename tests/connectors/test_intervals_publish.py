"""intervals-publish task 2.1: intervals.icu's answers mapped into publish codes.

Req 7.1-7.7 (the answer table, by request kind) and 8.2, 8.3 (the remote
identifier rule and the direct link). Pure functions and constants; no
transport is involved.
"""

from __future__ import annotations

import re
from types import MappingProxyType

import pytest

from fitdocs.connectors.intervals import (
    ACTIVITY_ID_PATTERN,
    ACTIVITY_LINK_BASE,
    ANSWER_CODES,
    SUCCESS_STATUSES,
    AnswerClass,
    CallKind,
    _activity_link,
    _answer_class,
    _answer_code,
    _linked_activity,
)
from fitdocs.connectors.protocol import TARGET_CODES, PublishCode

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
