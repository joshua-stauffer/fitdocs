"""StravaApi's activity, upload and subscription calls (task 3.2), against a
scripted Outbound."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from email.message import MIMEPart
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs, urlsplit

import pytest
from tests.strava.scripted_strava import ScriptedOutbound, reply

from fitdocs_relay.outbound import OutboundError, OutboundRequest, OutboundResponse
from fitdocs_relay.strava.api import (
    Candidate,
    Failure,
    Listing,
    Step,
    StravaApi,
    StravaFailure,
    SubscriptionState,
    UploadState,
)
from fitdocs_relay.strava.config import Limits, LinkSetting, StravaConfig

CLIENT_ID = "4711"
CLIENT_SECRET = "client-secret-SENTINEL"
WEBHOOK_TOKEN = "verify-token-" + "w" * 27
API = "https://api.example/v3"
CONFIG = StravaConfig(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    webhook_token=WEBHOOK_TOKEN,
    api_url=API,
    oauth_url="https://oauth.example/oauth",
    web_url="https://web.example",
    limits=Limits(overall_15m=200, overall_day=2000, read_15m=100, read_day=1000),
    links=LinkSetting.ACTIVITY,
)
ACCESS = "access-tok-AAA"
SENTINEL = "STRAVA-ERROR-TEXT-SENTINEL"
CALLBACK = "https://relay.example/hooks/strava"
TIMEOUT = 3.5


def make() -> tuple[StravaApi, ScriptedOutbound]:
    fake = ScriptedOutbound()
    return StravaApi(CONFIG, outbound=fake), fake


def _entry(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": 12345678901,
        "sport_type": "Run",
        "start_date": "2026-03-04T05:06:07Z",
        "start_date_local": "2026-03-04T07:08:09Z",
        "elapsed_time": 1800,
        "distance": 5000.5,
    }
    entry.update(changes)
    return entry


def _without(entry: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in entry.items() if k != key}


def _bearer(request: OutboundRequest) -> str:
    return dict(request.secret_headers)["Authorization"]


# --- list_activities -----------------------------------------------------------


def test_list_is_a_get_with_the_window_page_size_and_page_one() -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1000&before=2240&per_page=30&page=1",
        reply(200, []),
    )
    result = api.list_activities(
        ACCESS, after=1000, before=2240, per_page=30, timeout=TIMEOUT
    )
    assert result == Listing((), False)
    (call,) = fake.calls
    assert call.timeout == TIMEOUT
    assert call.request.method == "GET"
    parts = urlsplit(call.request.url)
    assert parts.path == "/v3/athlete/activities"
    assert parse_qs(parts.query) == {
        "after": ["1000"],
        "before": ["2240"],
        "per_page": ["30"],
        "page": ["1"],
    }
    assert call.request.body is None
    assert _bearer(call.request) == f"Bearer {ACCESS}"
    assert ACCESS not in call.request.url
    assert ACCESS not in str(dict(call.request.headers))
    assert ACCESS not in repr(call.request)


def test_list_reads_each_candidate_by_structure() -> None:
    api, fake = make()
    plus_two = timezone(timedelta(hours=2))
    entries = [
        _entry(),
        _entry(
            id=22,
            sport_type="Ride",
            start_date=datetime(2026, 3, 4, 9, 0, 0, tzinfo=plus_two).isoformat(),
            start_date_local="2026-03-04T11:12:13Z",
            elapsed_time=61,
            distance=12.25,
            name=SENTINEL,
        ),
    ]
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(200, entries),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert result == Listing(
        (
            Candidate(
                "12345678901",
                "Run",
                datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC),
                1800.0,
                5000.5,
            ),
            Candidate(
                "22", "Ride", datetime(2026, 3, 4, 7, 0, 0, tzinfo=UTC), 61.0, 12.25
            ),
        ),
        False,
    )
    assert isinstance(result, Listing)
    # the +02:00 entry is the same instant as 07:00 UTC, not 09:00 UTC
    assert result.candidates[1].start == datetime(2026, 3, 4, 7, 0, tzinfo=UTC)
    assert result.candidates[1].start.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("count", "per_page", "full"),
    [(0, 3, False), (2, 3, False), (3, 3, True), (4, 3, True), (1, 1, True)],
)
def test_list_is_full_when_a_page_holds_the_page_size(
    count: int, per_page: int, full: bool
) -> None:
    api, fake = make()
    entries = [_entry(id=n + 1) for n in range(count)]
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page={per_page}&page=1",
        reply(200, entries),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=per_page, timeout=TIMEOUT
    )
    assert isinstance(result, Listing)
    assert len(result.candidates) == count
    assert result.full is full


def test_list_optional_fields_absent_are_none_not_zero() -> None:
    api, fake = make()
    bare = {"id": 5, "start_date": "2026-03-04T05:06:07Z"}
    nulls = _entry(id=6, sport_type=None, elapsed_time=None, distance=None)
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(200, [bare, nulls]),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert isinstance(result, Listing)
    start = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert result.candidates == (
        Candidate("5", None, start, None, None),
        Candidate("6", None, start, None, None),
    )


def test_list_a_zero_measure_is_kept_as_zero() -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(200, [_entry(elapsed_time=0, distance=0)]),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert isinstance(result, Listing)
    assert (result.candidates[0].elapsed_s, result.candidates[0].distance_m) == (
        0.0,
        0.0,
    )


# 64 characters is read, 65 is not; both forms parse as a datetime on their own.
AT_LIMIT_START = "2026-03-04T05:06:07." + "0" * 38 + "+00:00"
OVERLONG_START = "2026-03-04T05:06:07." + "0" * 39 + "+00:00"


def test_list_reads_every_field_at_its_bound() -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(
            200,
            [
                _entry(
                    id=2**63,
                    sport_type="R" * 64,
                    start_date=AT_LIMIT_START,
                    elapsed_time=10**12,
                    distance=1e12,
                )
            ],
        ),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert isinstance(result, Listing)
    (candidate,) = result.candidates
    assert candidate == Candidate(
        str(2**63),
        "R" * 64,
        datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC),
        1e12,
        1e12,
    )
    assert len(AT_LIMIT_START) == 64
    assert len(OVERLONG_START) == 65
    for form in (AT_LIMIT_START, OVERLONG_START):
        assert datetime.fromisoformat(form).utcoffset() == timedelta(0)


UNREADABLE_ENTRIES = {
    "no id": _without(_entry(), "id"),
    "null id": _entry(id=None),
    "string id": _entry(id="123"),
    "bool id": _entry(id=True),
    "zero id": _entry(id=0),
    "negative id": _entry(id=-4),
    "float id": _entry(id=1.5),
    "no start": _without(_entry(), "start_date"),
    "null start": _entry(start_date=None),
    "number start": _entry(start_date=1700000000),
    "garbage start": _entry(start_date="yesterday"),
    "naive start": _entry(start_date="2026-03-04T05:06:07"),
    "bool sport": _entry(sport_type=True),
    "list sport": _entry(sport_type=["Run"]),
    "bool distance": _entry(distance=True),
    "string distance": _entry(distance="5000"),
    "negative distance": _entry(distance=-1),
    "negative float distance": _entry(distance=-0.5),
    "negative elapsed": _entry(elapsed_time=-1),
    "string elapsed": _entry(elapsed_time="60"),
    "start overflows on conversion": _entry(start_date="0001-01-01T00:00:00+01:00"),
    "start overflows on conversion, far side": _entry(
        start_date="9999-12-31T23:59:59-01:00"
    ),
    "sport over 64 chars": _entry(sport_type="R" * 65),
    "start over 64 chars": _entry(start_date=OVERLONG_START),
    "distance over the bound": _entry(distance=10**12 + 1),
    "float elapsed over the bound": _entry(elapsed_time=1e12 + 1024.0),
    "id over the bound": _entry(id=2**63 + 1),
    "not an object": 7,
}


@pytest.mark.parametrize("name", UNREADABLE_ENTRIES)
def test_a_listing_entry_missing_or_misreading_a_needed_field_is_unreadable(
    name: str,
) -> None:
    api, fake = make()
    # a good entry beside it: one bad entry spoils the whole answer
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(200, [_entry(id=9), UNREADABLE_ENTRIES[name]]),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert result == StravaFailure(Step.LIST, Failure.UNREADABLE)


@pytest.mark.parametrize(
    "body",
    [
        b"1e999",
        b'[{"id": 1, "start_date": "2026-03-04T05:06:07Z", "distance": 1e999}]',
        b'{"id": 1}',
        b"\xff",
        b"",
        b"[" * 100000,
    ],
)
def test_a_listing_that_is_not_a_readable_array_is_unreadable(body: bytes) -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(200, body),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert result == StravaFailure(Step.LIST, Failure.UNREADABLE)


# --- update_activity -----------------------------------------------------------


def test_update_puts_only_the_name_and_the_description() -> None:
    api, fake = make()
    fake.expect(
        "PUT", f"{API}/activities/987", reply(200, {"id": 987, "name": SENTINEL})
    )
    result = api.update_activity(
        ACCESS,
        "987",
        name="Morning run",
        description="line one\nline two",
        timeout=TIMEOUT,
    )
    assert result is None
    (call,) = fake.calls
    assert call.timeout == TIMEOUT
    assert call.request.method == "PUT"
    assert urlsplit(call.request.url).path == "/v3/activities/987"
    assert urlsplit(call.request.url).query == ""
    assert dict(call.request.headers)["Content-Type"] == "application/json"
    assert call.request.body is not None
    sent = json.loads(call.request.body)
    assert sent == {"name": "Morning run", "description": "line one\nline two"}
    assert _bearer(call.request) == f"Bearer {ACCESS}"
    assert ACCESS not in call.request.url
    assert ACCESS not in call.request.body.decode()


def test_update_quotes_the_activity_id_into_one_path_segment() -> None:
    api, fake = make()
    fake.expect("PUT", f"{API}/activities/1%2F..%2F2%3Fx", reply(200, {}))
    assert (
        api.update_activity(
            ACCESS, "1/../2?x", name="n", description="d", timeout=TIMEOUT
        )
        is None
    )


# --- create_upload -------------------------------------------------------------

FIT = b".\x0e\x10\x00FIT\r\n--not-a-boundary\r\n\x00\xff\r\n"


def _parts(request: OutboundRequest) -> Mapping[str, MIMEPart]:
    assert request.body is not None
    content_type = dict(request.headers)["Content-Type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    raw = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + request.body
    )
    message = BytesParser(policy=default).parsebytes(raw)
    parts = {
        str(part.get_param("name", header="content-disposition")): part
        for part in message.iter_parts()
    }
    assert len(parts) == len(list(message.iter_parts()))
    return parts


def _text(part: MIMEPart) -> str:
    payload = part.get_payload(decode=True)
    assert isinstance(payload, bytes)
    return payload.decode("utf-8")


def test_upload_posts_multipart_with_the_publication_id_as_external_id() -> None:
    api, fake = make()
    fake.expect(
        "POST",
        f"{API}/uploads",
        reply(201, {"id": 4242, "id_str": "4242", "error": None, "status": SENTINEL}),
    )
    result = api.create_upload(
        ACCESS,
        fit=FIT,
        name="Run",
        description="a\nb",
        external_id="pub-0123456789abcdef",
        timeout=TIMEOUT,
    )
    assert result == "4242"
    (call,) = fake.calls
    assert call.timeout == TIMEOUT
    assert call.request.method == "POST"
    assert urlsplit(call.request.url).path == "/v3/uploads"
    assert urlsplit(call.request.url).query == ""
    assert _bearer(call.request) == f"Bearer {ACCESS}"
    parts = _parts(call.request)
    assert set(parts) == {"file", "data_type", "name", "description", "external_id"}
    assert _text(parts["data_type"]) == "fit"
    assert _text(parts["name"]) == "Run"
    assert _text(parts["description"]) == "a\nb"
    assert _text(parts["external_id"]) == "pub-0123456789abcdef"
    assert parts["file"].get_payload(decode=True) == FIT
    assert parts["file"].get_filename() == "activity.fit"
    assert ACCESS not in call.request.url
    assert (
        ACCESS not in call.request.body.decode("latin-1")
        if call.request.body
        else False
    )


def test_upload_text_fields_may_be_non_ascii() -> None:
    api, fake = make()
    fake.expect("POST", f"{API}/uploads", reply(201, {"id": 1}))
    api.create_upload(
        ACCESS,
        fit=FIT,
        name="Lauf über",
        description="走",
        external_id="p",
        timeout=TIMEOUT,
    )
    parts = _parts(fake.calls[0].request)
    assert _text(parts["name"]) == "Lauf über"
    assert _text(parts["description"]) == "走"


@pytest.mark.parametrize(
    "body",
    [{}, {"id": None}, {"id": "7"}, {"id": True}, {"id": 0}, [{"id": 7}], b"\xff", b""],
)
def test_an_upload_answer_without_a_readable_id_is_unreadable(body: object) -> None:
    api, fake = make()
    fake.expect("POST", f"{API}/uploads", reply(201, body))
    result = api.create_upload(
        ACCESS, fit=FIT, name="n", description="d", external_id="p", timeout=TIMEOUT
    )
    assert result == StravaFailure(Step.UPLOAD, Failure.UNREADABLE)


# --- upload_state --------------------------------------------------------------


def test_upload_state_is_a_get_of_the_upload() -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/uploads/4242",
        reply(200, {"id": 4242, "error": None, "activity_id": 777}),
    )
    assert api.upload_state(ACCESS, "4242", timeout=TIMEOUT) == UploadState(
        "777", False
    )
    (call,) = fake.calls
    assert call.request.method == "GET"
    assert urlsplit(call.request.url).path == "/v3/uploads/4242"
    assert call.request.body is None
    assert _bearer(call.request) == f"Bearer {ACCESS}"
    assert call.timeout == TIMEOUT


def test_upload_state_quotes_the_upload_id_into_one_path_segment() -> None:
    api, fake = make()
    fake.expect("GET", f"{API}/uploads/1%2F..%2F2%3Fx", reply(200, {}))
    assert api.upload_state(ACCESS, "1/../2?x", timeout=TIMEOUT) == UploadState(
        None, False
    )


@pytest.mark.parametrize(
    "error",
    [
        "duplicate of activity 5",
        "Your activity is still being processed.",
        "processed successfully",
        "",
        0,
        False,
        {"message": "ok"},
        ["fine"],
    ],
)
@pytest.mark.parametrize("activity", [None, 777])
def test_a_non_null_upload_error_is_failed_whatever_it_says(
    error: object, activity: int | None
) -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/uploads/9",
        reply(
            200,
            {
                "id": 9,
                "error": error,
                "activity_id": activity,
                "status": "Your activity is ready.",
            },
        ),
    )
    result = api.upload_state(ACCESS, "9", timeout=TIMEOUT)
    assert result == UploadState(None, True)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"id": 9, "activity_id": 31}, UploadState("31", False)),
        (
            {"id": 9, "error": None, "activity_id": 31, "status": SENTINEL},
            UploadState("31", False),
        ),
        (
            {
                "id": 9,
                "error": None,
                "activity_id": None,
                "status": "Your activity is ready.",
            },
            UploadState(None, False),
        ),
        ({"id": 9}, UploadState(None, False)),
        ({}, UploadState(None, False)),
    ],
)
def test_an_upload_is_ready_when_it_has_an_activity_and_pending_otherwise(
    body: dict[str, object], expected: UploadState
) -> None:
    api, fake = make()
    fake.expect("GET", f"{API}/uploads/9", reply(200, body))
    assert api.upload_state(ACCESS, "9", timeout=TIMEOUT) == expected


@pytest.mark.parametrize("activity", ["31", True, 0, -3, 1.5, [31]])
def test_a_malformed_activity_id_with_no_error_is_unreadable(activity: object) -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/uploads/9",
        reply(200, {"id": 9, "error": None, "activity_id": activity}),
    )
    assert api.upload_state(ACCESS, "9", timeout=TIMEOUT) == StravaFailure(
        Step.UPLOAD_STATUS, Failure.UNREADABLE
    )


@pytest.mark.parametrize("body", [[], b"{", b"\xff", b"null", b'"ok"'])
def test_an_upload_state_that_is_not_an_object_is_unreadable(body: object) -> None:
    api, fake = make()
    fake.expect("GET", f"{API}/uploads/9", reply(200, body))
    assert api.upload_state(ACCESS, "9", timeout=TIMEOUT) == StravaFailure(
        Step.UPLOAD_STATUS, Failure.UNREADABLE
    )


# --- subscriptions -------------------------------------------------------------

VIEW = f"{API}/push_subscriptions?client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}"


def _subscription(**changes: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": 555,
        "callback_url": CALLBACK,
        "application_id": 1,
    }
    entry.update(changes)
    return entry


def test_subscription_state_views_with_client_credentials_in_a_secret_address() -> None:
    api, fake = make()
    fake.expect("GET", VIEW, reply(200, []))
    assert (
        api.subscription_state(callback_url=CALLBACK, timeout=TIMEOUT)
        is SubscriptionState.ABSENT
    )
    (call,) = fake.calls
    assert call.request.method == "GET"
    assert call.request.url_is_secret is True
    assert call.request.body is None
    assert call.timeout == TIMEOUT
    assert parse_qs(urlsplit(call.request.url).query) == {
        "client_id": [CLIENT_ID],
        "client_secret": [CLIENT_SECRET],
    }
    assert CLIENT_SECRET not in repr(call.request)


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([], SubscriptionState.ABSENT),
        ([_subscription()], SubscriptionState.OURS),
        (
            [_subscription(callback_url="https://elsewhere.example/hook")],
            SubscriptionState.OTHER,
        ),
        ([_subscription(callback_url=CALLBACK + "/")], SubscriptionState.OTHER),
        (
            [
                _subscription(),
                _subscription(id=556, callback_url="https://elsewhere.example/hook"),
            ],
            SubscriptionState.OTHER,
        ),
        (
            [
                _subscription(callback_url="https://elsewhere.example/hook"),
                _subscription(id=556),
            ],
            SubscriptionState.OTHER,
        ),
    ],
)
def test_subscription_state_is_ours_only_when_every_subscription_is_ours(
    entries: list[object], expected: SubscriptionState
) -> None:
    api, fake = make()
    fake.expect("GET", VIEW, reply(200, entries))
    assert api.subscription_state(callback_url=CALLBACK, timeout=TIMEOUT) is expected


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"id": 1},
        [7],
        [{"callback_url": CALLBACK}],
        [{"id": 5}],
        [{"id": "5", "callback_url": CALLBACK}],
        [{"id": 5, "callback_url": None}],
        b"\xff",
        b"",
    ],
)
def test_an_unreadable_subscription_view_is_unreadable(body: object) -> None:
    api, fake = make()
    fake.expect("GET", VIEW, reply(200, body))
    assert api.subscription_state(
        callback_url=CALLBACK, timeout=TIMEOUT
    ) == StravaFailure(Step.SUBSCRIPTION, Failure.UNREADABLE)


def test_create_subscription_posts_the_form_with_the_verify_token() -> None:
    api, fake = make()
    fake.expect("POST", f"{API}/push_subscriptions", reply(201, {"id": 555}))
    assert api.create_subscription(callback_url=CALLBACK, timeout=TIMEOUT) is None
    (call,) = fake.calls
    assert call.request.method == "POST"
    assert call.timeout == TIMEOUT
    assert urlsplit(call.request.url).query == ""
    assert call.form == {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "callback_url": CALLBACK,
        "verify_token": WEBHOOK_TOKEN,
    }
    assert (
        dict(call.request.headers)["Content-Type"]
        == "application/x-www-form-urlencoded"
    )
    assert CLIENT_SECRET not in call.request.url
    assert WEBHOOK_TOKEN not in call.request.url
    assert CLIENT_SECRET not in repr(call.request)


def test_create_subscription_accepts_any_2xx_body() -> None:
    api, fake = make()
    fake.expect(
        "POST", f"{API}/push_subscriptions", reply(201, b"\xff"), reply(200, b"")
    )
    assert api.create_subscription(callback_url=CALLBACK, timeout=TIMEOUT) is None
    assert api.create_subscription(callback_url=CALLBACK, timeout=TIMEOUT) is None


def test_delete_subscription_views_then_deletes_by_id_in_a_secret_address() -> None:
    api, fake = make()
    delete_url = (
        f"{API}/push_subscriptions/555?"
        f"client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}"
    )
    fake.expect("GET", VIEW, reply(200, [_subscription()]))
    fake.expect("DELETE", delete_url, reply(204))
    assert api.delete_subscription(timeout=TIMEOUT) is True
    view, delete = fake.calls
    assert (view.request.method, delete.request.method) == ("GET", "DELETE")
    assert view.request.url_is_secret and delete.request.url_is_secret
    assert delete.request.body is None
    assert delete.timeout == TIMEOUT
    assert CLIENT_SECRET not in repr(delete.request)
    assert parse_qs(urlsplit(delete.request.url).query) == {
        "client_id": [CLIENT_ID],
        "client_secret": [CLIENT_SECRET],
    }


def test_delete_subscription_with_none_existing_deletes_nothing() -> None:
    api, fake = make()
    fake.expect("GET", VIEW, reply(200, []))
    assert api.delete_subscription(timeout=TIMEOUT) is False
    assert [c.request.method for c in fake.calls] == ["GET"]


def test_delete_subscription_deletes_each_listed_subscription() -> None:
    api, fake = make()
    fake.expect("GET", VIEW, reply(200, [_subscription(id=11), _subscription(id=22)]))
    for number in (11, 22):
        fake.expect(
            "DELETE",
            f"{API}/push_subscriptions/{number}?client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}",
            reply(204),
        )
    assert api.delete_subscription(timeout=TIMEOUT) is True
    assert [c.request.method for c in fake.calls] == ["GET", "DELETE", "DELETE"]
    assert fake.unserved() == 0


def test_delete_subscription_reports_the_failing_step() -> None:
    api, fake = make()
    fake.expect("GET", VIEW, reply(500, {}))
    assert api.delete_subscription(timeout=TIMEOUT) == StravaFailure(
        Step.SUBSCRIPTION, Failure.SERVER
    )
    api, fake = make()
    fake.expect("GET", VIEW, reply(200, [_subscription()]))
    fake.expect(
        "DELETE",
        f"{API}/push_subscriptions/555?client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}",
        reply(404, {}),
    )
    assert api.delete_subscription(timeout=TIMEOUT) == StravaFailure(
        Step.SUBSCRIPTION, Failure.MISSING
    )


# --- every call maps status and errors through classify -------------------------


def _all_calls(api: StravaApi) -> list[object]:
    return [
        api.list_activities(ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT),
        api.update_activity(ACCESS, "9", name="n", description="d", timeout=TIMEOUT),
        api.create_upload(
            ACCESS, fit=FIT, name="n", description="d", external_id="p", timeout=TIMEOUT
        ),
        api.upload_state(ACCESS, "9", timeout=TIMEOUT),
        api.subscription_state(callback_url=CALLBACK, timeout=TIMEOUT),
        api.create_subscription(callback_url=CALLBACK, timeout=TIMEOUT),
        api.delete_subscription(timeout=TIMEOUT),
    ]


CALL_STEPS = [
    Step.LIST,
    Step.UPDATE,
    Step.UPLOAD,
    Step.UPLOAD_STATUS,
    Step.SUBSCRIPTION,
    Step.SUBSCRIPTION,
    Step.SUBSCRIPTION,
]


def _script_everything(
    fake: ScriptedOutbound, answer: OutboundResponse | OutboundError
) -> None:
    fake.expect(
        "GET", f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1", answer
    )
    fake.expect("PUT", f"{API}/activities/9", answer)
    fake.expect("POST", f"{API}/uploads", answer)
    fake.expect("GET", f"{API}/uploads/9", answer)
    fake.expect("GET", VIEW, answer, answer, answer)
    fake.expect("POST", f"{API}/push_subscriptions", answer)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, Failure.AUTH),
        (403, Failure.FORBIDDEN),
        (404, Failure.MISSING),
        (422, Failure.INVALID),
        (429, Failure.LIMITED),
        (503, Failure.SERVER),
        (302, Failure.SERVER),  # a redirect is transient (3.5 ruling B)
    ],
)
def test_every_call_maps_status_through_classify(
    status: int, expected: Failure
) -> None:
    api, fake = make()
    _script_everything(fake, reply(status, {}))
    results = _all_calls(api)
    assert results == [StravaFailure(step, expected) for step in CALL_STEPS]


@pytest.mark.parametrize("kind", ["timeout", "network", "invalid", "too-large"])
def test_every_call_reports_an_outbound_error_as_network(kind: str) -> None:
    api, fake = make()
    _script_everything(fake, OutboundError(kind))  # type: ignore[arg-type]
    assert _all_calls(api) == [
        StravaFailure(step, Failure.NETWORK) for step in CALL_STEPS
    ]


def test_a_daily_spent_usage_header_is_read_on_a_limited_listing() -> None:
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(429, {}, {"X-ReadRateLimit-Usage": "5,1000"}),
    )
    result = api.list_activities(
        ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT
    )
    assert result == StravaFailure(Step.LIST, Failure.LIMITED, True)


# --- nothing Strava says comes back --------------------------------------------


def test_a_sentinel_in_any_answer_appears_in_no_returned_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    leak = {
        "message": SENTINEL,
        "errors": [{"code": SENTINEL}],
        "error": SENTINEL,
        "status": SENTINEL,
    }
    results: list[object] = []
    for status in (400, 401, 403, 404, 422, 429, 500, 302):
        api, fake = make()
        _script_everything(
            fake,
            reply(
                status,
                leak,
                {"www-authenticate": SENTINEL, "x-ratelimit-usage": "1,2000"},
            ),
        )
        results += _all_calls(api)
    # readable answers whose free-text fields carry the sentinel
    api, fake = make()
    fake.expect(
        "GET",
        f"{API}/athlete/activities?after=1&before=2&per_page=30&page=1",
        reply(200, [_entry(name=SENTINEL, sport_type="Run")]),
    )
    fake.expect("PUT", f"{API}/activities/9", reply(200, leak))
    fake.expect("POST", f"{API}/uploads", reply(201, {**leak, "id": 9}))
    fake.expect("GET", f"{API}/uploads/9", reply(200, {"id": 9, "error": SENTINEL}))
    fake.expect(
        "GET",
        VIEW,
        reply(
            200,
            [
                _subscription(
                    callback_url="https://x.example/" + SENTINEL[:5], note=SENTINEL
                )
            ],
        ),
    )
    fake.expect("POST", f"{API}/push_subscriptions", reply(201, leak))
    results += [
        api.list_activities(ACCESS, after=1, before=2, per_page=30, timeout=TIMEOUT),
        api.update_activity(ACCESS, "9", name="n", description="d", timeout=TIMEOUT),
        api.create_upload(
            ACCESS, fit=FIT, name="n", description="d", external_id="p", timeout=TIMEOUT
        ),
        api.upload_state(ACCESS, "9", timeout=TIMEOUT),
        api.subscription_state(callback_url=CALLBACK, timeout=TIMEOUT),
        api.create_subscription(callback_url=CALLBACK, timeout=TIMEOUT),
    ]
    assert len(results) == 8 * 7 + 6
    assert sum(isinstance(r, StravaFailure) for r in results) == 8 * 7
    assert (
        sum(r is None for r in results) == 2
    )  # the update and the subscription create
    for result in results:
        assert SENTINEL not in repr(result)
        assert (
            SENTINEL not in str(vars(result)) if hasattr(result, "__dict__") else True
        )
    assert SENTINEL not in caplog.text


# --- a Strava identifier never reaches a log line ---------------------------------


def test_a_request_whose_address_carries_a_strava_id_hides_its_address() -> None:
    api, fake = make()
    fake.expect("PUT", f"{API}/activities/987654321", reply(200, {}))
    fake.expect("GET", f"{API}/uploads/555444333", reply(200, {"id": 555444333}))
    assert (
        api.update_activity(ACCESS, "987654321", name="n", description="d", timeout=1)
        is None
    )
    assert isinstance(api.upload_state(ACCESS, "555444333", timeout=1), UploadState)
    update, status = (call.request for call in fake.calls)
    assert "987654321" in update.url and "555444333" in status.url
    for request in (update, status):
        assert request.url_is_secret
        assert "987654321" not in repr(request)
        assert "555444333" not in repr(request)
        assert "activities" not in repr(request)
        assert "uploads" not in repr(request)
