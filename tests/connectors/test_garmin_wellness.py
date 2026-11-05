"""The Garmin wellness listing and package (garmin-connector tasks 4.1, 4.2).

Everything runs against a routing transport: no network, a synthetic key, a
synthetic token. Each answer is built for the route it is sent to, so a test
sees exactly which windows were requested and in what order.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from fitdocs.connectors.delivery import wellness_package_problem
from fitdocs.connectors.errors import AuthFailure, ConnectorError
from fitdocs.connectors.garmin import GarminConnector
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.protocol import (
    ConnectorSession,
    CredentialAccess,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.wellness import registry as wellness_registry
from fitdocs.wellness.formats.garmin import PERSONAL_FORMAT
from fitdocs.wellness.model import Metric
from fitdocs.wellness.probe import CandidateProbe

_KEY = "gk-synthetic-4Vq8Zt"
_TOKEN = (
    "eyJhbGci_OiJ0-ZXN0In0.eyJzdWIi_OiJzeW50-aGV0aWMtNzczMSJ9.c2ln_LXN5bnRo-ZXRpYy0xMg"
)
_MARKER = "BODYMARKER-5521"
_BASE = "https://personal.connectapi.garmin.com"

# 23:30 on 5 November at UTC-8 is 07:30 on 6 November in UTC: the local date
# and the UTC date differ, so a local-date slip shows.
_WEST = timezone(timedelta(hours=-8))
_NOW = datetime(2026, 11, 5, 23, 30, tzinfo=_WEST)
_NEWEST = date(2026, 11, 7)

_PATHS = {
    "daily": "/usersummary-service/v2/dailysummaries",
    "sleep": "/sleep-service/sleep/dailySleepSummariesByDate",
    "hrv": "/hrv-service/hrv/daily/",
    "weight": "/weight-service/weight/range/",
    "probe": "/activitylist-service/activities/search/activities",
}
_LIMIT = {"daily": 365, "sleep": 31, "hrv": 28, "weight": 365}
_SECTIONS = ("daily", "sleep", "hrv", "weight")
_DATE_FIELD = {
    "daily": "calendarDate",
    "sleep": "calendarDate",
    "hrv": "calendarDate",
    "weight": "summaryDate",
}
_DISPLAY = {"daily": "daily", "sleep": "sleep", "hrv": "HRV", "weight": "weight"}

Answer = HttpResponse | TransportError | Callable[[date, date], HttpResponse]


def _text(body: str | bytes, status: int = 200) -> HttpResponse:
    raw = body.encode() if isinstance(body, str) else body
    return HttpResponse(status=status, headers={}, body=raw)


def _body(section: str, records: list[object]) -> HttpResponse:
    """A 200 answer in the section's documented form."""
    if section == "daily":
        return _text(json.dumps({"data": records}))
    if section == "sleep":
        return _text(json.dumps(records))
    if section == "hrv":
        return _text(json.dumps({"hrvSummaries": records}))
    return _text(json.dumps({"dailyWeightSummaries": records}))


def _empty(section: str) -> HttpResponse:
    return _body(section, [])


def _rec(section: str, day: str, **extra: object) -> dict[str, object]:
    return {_DATE_FIELD[section]: day, **extra}


def _classify(request: HttpRequest) -> tuple[str, date | None, date | None]:
    parts = urlsplit(request.url)
    path = parts.path
    query = parse_qs(parts.query)
    if path == _PATHS["daily"]:
        return (
            "daily",
            date.fromisoformat(query["startDate"][0]),
            date.fromisoformat(query["endDate"][0]),
        )
    if path == _PATHS["sleep"]:
        return (
            "sleep",
            date.fromisoformat(query["startDate"][0]),
            date.fromisoformat(query["endDate"][0]),
        )
    if path == _PATHS["probe"]:
        return "probe", None, None
    for section in ("hrv", "weight"):
        if path.startswith(_PATHS[section]):
            first, last = path[len(_PATHS[section]) :].split("/")
            return section, date.fromisoformat(first), date.fromisoformat(last)
    raise AssertionError(f"an unexpected route was requested: {path}")


class _Rig:
    """One pull's session over a routing transport."""

    def __init__(
        self,
        answers: Mapping[str, Answer] | None = None,
        *,
        now: datetime = _NOW,
        data_root: Path = Path("/nonexistent-data-root"),
        token: HttpResponse | None = None,
    ) -> None:
        self.answers: dict[str, Answer] = {
            **{section: _empty(section) for section in _SECTIONS},
            "probe": _text("[]"),
            **(answers or {}),
        }
        self.requests: list[HttpRequest] = []
        self.posts = 0
        self.sleeps: list[float] = []
        self.redactor = Redactor()

        def transport(request: HttpRequest, timeout: float) -> HttpResponse:
            self.requests.append(request)
            if request.method == "POST":
                self.posts += 1
                return token if token is not None else _text(_TOKEN)
            section, start, end = _classify(request)
            answer = self.answers[section]
            if isinstance(answer, TransportError):
                raise answer
            if callable(answer):
                assert start is not None and end is not None
                return answer(start, end)
            return answer

        class _Key:
            def value(self, field: str) -> Secret:
                assert field == "api_key"
                return Secret(_KEY)

            @property
            def scopes(self) -> tuple[str, ...] | None:
                return None

            @property
            def expires_at(self) -> datetime | None:
                return None

            def replace(self, tokens: object) -> None:
                raise AssertionError("a pull stores nothing")

        credentials: CredentialAccess = _Key()
        self.session = ConnectorSession(
            instance="garmin",
            settings=None,
            http=HttpClient(
                transport,
                mode=CallMode.DATA,
                redactor=self.redactor,
                sleep=lambda seconds: None,
            ),
            credentials=credentials,
            data_root=data_root,
            now=lambda: now,
            sleep=self.sleeps.append,
            redactor=self.redactor,
        )

    def gets(self) -> list[HttpRequest]:
        return [r for r in self.requests if r.method == "GET"]

    def windows(self, section: str) -> list[tuple[date, date]]:
        out: list[tuple[date, date]] = []
        for request in self.gets():
            kind, start, end = _classify(request)
            if kind == section:
                assert start is not None and end is not None
                out.append((start, end))
        return out

    def sections_in_order(self) -> list[str]:
        return [_classify(r)[0] for r in self.gets()]


def _list(
    answers: Mapping[str, Answer] | None = None,
    oldest: date | None = date(2026, 11, 1),
    *,
    now: datetime = _NOW,
) -> tuple[_Rig, WellnessListing]:
    rig = _Rig(answers, now=now)
    return rig, GarminConnector().list_wellness(rig.session, oldest)


def _fails(
    answers: Mapping[str, Answer] | None = None,
    oldest: date | None = date(2026, 11, 1),
) -> tuple[_Rig, ConnectorError]:
    rig = _Rig(answers)
    with pytest.raises(ConnectorError) as excinfo:
        GarminConnector().list_wellness(rig.session, oldest)
    assert not isinstance(excinfo.value, AuthFailure)
    return rig, excinfo.value


def _expected_windows(first: date, newest: date, size: int) -> list[tuple[date, date]]:
    """The windows an independent count of days gives: ``size`` days each,
    the last one cut at ``newest``."""
    days = (newest - first).days + 1
    return [
        (
            first + timedelta(days=i * size),
            min(first + timedelta(days=(i + 1) * size - 1), newest),
        )
        for i in range(math.ceil(days / size))
    ]


def _d(text: str) -> date:
    return date.fromisoformat(text)


# --------------------------------------------------------------------------
# The four routes (design.md "Service routes")
# --------------------------------------------------------------------------


def test_each_route_is_requested_in_its_documented_form_in_one_window() -> None:
    rig, listing = _list()
    urls = [r.url for r in rig.gets()]
    assert urls == [
        f"{_BASE}/usersummary-service/v2/dailysummaries"
        "?startDate=2026-11-01&endDate=2026-11-07",
        f"{_BASE}/sleep-service/sleep/dailySleepSummariesByDate"
        "?startDate=2026-11-01&endDate=2026-11-07",
        f"{_BASE}/hrv-service/hrv/daily/2026-11-01/2026-11-07",
        f"{_BASE}/weight-service/weight/range/2026-11-01/2026-11-07?includeAll=true",
    ]
    assert listing.days == ()
    assert (listing.oldest, listing.newest) == (date(2026, 11, 1), _NEWEST)


def test_every_wellness_request_is_a_get_with_the_pulls_one_bearer_and_json() -> None:
    rig, _ = _list()
    assert rig.posts == 1
    assert len(rig.gets()) == 4
    for request in rig.gets():
        assert request.method == "GET"
        assert request.headers["Accept"] == "application/json"
        assert request.secret_headers["Authorization"].reveal() == f"Bearer {_TOKEN}"


def test_requests_are_spaced_a_second_apart_through_the_shared_helper() -> None:
    rig, _ = _list()
    # The token request is the pull's first, so it is not spaced; each of the
    # four GETs after it waits one second.
    assert rig.sleeps == [1.0, 1.0, 1.0, 1.0]


@pytest.mark.parametrize(
    ("now", "newest"),
    [
        (_NOW, date(2026, 11, 7)),
        (
            datetime(2026, 11, 6, 6, 0, tzinfo=timezone(timedelta(hours=10))),
            _d("2026-11-06"),
        ),
    ],
)
def test_the_range_ends_the_day_after_the_utc_date_of_the_pull(
    now: datetime, newest: date
) -> None:
    rig, listing = _list(now=now)
    assert listing.newest == newest
    for section in _SECTIONS:
        assert rig.windows(section)[-1][1] == newest


def test_a_pull_that_listed_activities_first_still_mints_once() -> None:
    with tempfile.TemporaryDirectory() as root:
        rig = _Rig(
            {"probe": _text("[]")},
            data_root=Path(root),
        )
        connector = GarminConnector()
        connector.list_activities(rig.session, None)
        connector.list_wellness(rig.session, date(2026, 11, 1))
    assert rig.posts == 1
    assert [r.method for r in rig.requests].count("GET") == 5


@pytest.mark.parametrize("oldest", [date(2026, 11, 1), None])
def test_a_token_failure_kept_from_activities_is_raised_again_with_no_new_request(
    oldest: date | None,
) -> None:
    with tempfile.TemporaryDirectory() as root:
        rig = _Rig(data_root=Path(root), token=_text("oops", 500))
        connector = GarminConnector()
        with pytest.raises(ConnectorError) as kept:
            connector.list_activities(rig.session, None)
        with pytest.raises(ConnectorError) as again:
            connector.list_wellness(rig.session, oldest)
    assert again.value is kept.value
    assert rig.posts == 1
    assert rig.gets() == []


# --------------------------------------------------------------------------
# Windows (Req 9.4)
# --------------------------------------------------------------------------


def test_a_range_crossing_a_leap_day_is_cut_at_the_fixed_window_sizes() -> None:
    # 2024-02-15 to 2024-03-21: 36 days, with 29 February in it.
    rig, listing = _list(oldest=_d("2024-02-15"), now=datetime(2024, 3, 20, tzinfo=UTC))
    assert listing.newest == _d("2024-03-21")
    assert rig.windows("daily") == [(_d("2024-02-15"), _d("2024-03-21"))]
    assert rig.windows("weight") == [(_d("2024-02-15"), _d("2024-03-21"))]
    assert rig.windows("sleep") == [
        (_d("2024-02-15"), _d("2024-03-16")),
        (_d("2024-03-17"), _d("2024-03-21")),
    ]
    assert rig.windows("hrv") == [
        (_d("2024-02-15"), _d("2024-03-13")),
        (_d("2024-03-14"), _d("2024-03-21")),
    ]


def test_a_window_of_365_days_is_365_days_inclusive_across_a_leap_year() -> None:
    rig, _ = _list(oldest=_d("2024-01-01"), now=datetime(2025, 1, 2, tzinfo=UTC))
    expected = [
        (_d("2024-01-01"), _d("2024-12-30")),
        (_d("2024-12-31"), _d("2025-01-03")),
    ]
    assert rig.windows("daily") == expected
    assert rig.windows("weight") == expected
    assert (expected[0][1] - expected[0][0]).days + 1 == 365


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_range_of_exactly_one_window_is_one_request_and_one_more_day_is_two(
    section: str,
) -> None:
    size = _LIMIT[section]
    first = _d("2025-03-01")
    # newest = first + size - 1 fills the window exactly.
    exact = datetime.combine(
        first + timedelta(days=size - 2), datetime.min.time(), tzinfo=UTC
    )
    rig, listing = _list(oldest=first, now=exact)
    assert listing.newest == first + timedelta(days=size - 1)
    assert rig.windows(section) == [(first, first + timedelta(days=size - 1))]
    over = exact + timedelta(days=1)
    rig, listing = _list(oldest=first, now=over)
    assert rig.windows(section) == [
        (first, first + timedelta(days=size - 1)),
        (first + timedelta(days=size), first + timedelta(days=size)),
    ]


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_single_day_range_is_one_one_day_window_per_route(section: str) -> None:
    rig, listing = _list(oldest=_d("2026-11-07"))
    assert (listing.oldest, listing.newest) == (_d("2026-11-07"), _d("2026-11-07"))
    assert rig.windows(section) == [(_d("2026-11-07"), _d("2026-11-07"))]


def test_an_earliest_date_after_the_range_end_is_read_as_the_last_day() -> None:
    rig, listing = _list(oldest=_d("2026-12-25"))
    assert (listing.oldest, listing.newest) == (_NEWEST, _NEWEST)
    assert rig.windows("daily") == [(_NEWEST, _NEWEST)]


def test_a_multi_year_range_is_one_listing_of_contiguous_full_windows() -> None:
    first = _d("2014-06-01")
    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    rig, listing = _list(oldest=first, now=now)
    newest = _d("2026-11-06")
    assert (listing.oldest, listing.newest) == (first, newest)
    for section in _SECTIONS:
        windows = rig.windows(section)
        assert windows == _expected_windows(first, newest, _LIMIT[section])
        assert len(windows) > 1
        assert windows[0][0] == first
        assert windows[-1][1] == newest
        for (_, end), (start, _) in zip(windows, windows[1:], strict=False):
            assert start == end + timedelta(days=1)
        for start, end in windows[:-1]:
            assert (end - start).days + 1 == _LIMIT[section]
        assert (windows[-1][1] - windows[-1][0]).days + 1 <= _LIMIT[section]
    # 2014-06-01 through 2026-11-06 inclusive, by calendar arithmetic.
    assert (newest - first).days + 1 == 4_542
    assert [len(rig.windows(s)) for s in _SECTIONS] == [13, 147, 163, 13]
    # The route's windows follow one another, route after route.
    order = rig.sections_in_order()
    assert order == sorted(order, key=_SECTIONS.index)


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_multi_year_listing_holds_the_records_of_every_window(section: str) -> None:
    first = _d("2023-03-10")
    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    expected = _expected_windows(first, _d("2026-11-06"), _LIMIT[section])

    def answer(start: date, end: date) -> HttpResponse:
        return _body(section, [_rec(section, start.isoformat(), v=1)])

    _, listing = _list({section: answer}, oldest=first, now=now)
    assert len(expected) > 1
    assert [d.day for d in listing.days] == [start for start, _ in expected]
    assert [d.record for d in listing.days] == [
        {section: _rec(section, start.isoformat(), v=1)} for start, _ in expected
    ]


def test_a_year_and_a_day_is_thirty_requests() -> None:
    rig, _ = _list(oldest=_d("2025-01-01"), now=datetime(2025, 12, 31, tzinfo=UTC))
    assert [len(rig.windows(s)) for s in _SECTIONS] == [2, 12, 14, 2]
    assert len(rig.gets()) == 30


# --------------------------------------------------------------------------
# Where the range starts (Req 9.2)
# --------------------------------------------------------------------------


def test_a_given_earliest_date_makes_no_activity_request() -> None:
    rig, listing = _list(oldest=_d("2026-11-01"))
    assert listing.oldest == _d("2026-11-01")
    assert "probe" not in rig.sections_in_order()


def test_without_a_date_the_oldest_activity_is_asked_for_in_one_request() -> None:
    rig, listing = _list(
        {
            "probe": _text(
                json.dumps(
                    [
                        {
                            "activityId": 7,
                            "startTimeGMT": "2019-03-02 23:30:00",
                            "startTimeLocal": "2019-03-03 08:30:00",
                        }
                    ]
                )
            )
        },
        oldest=None,
    )
    first = rig.gets()[0]
    assert urlsplit(first.url).path == _PATHS["probe"]
    assert parse_qs(urlsplit(first.url).query) == {
        "start": ["0"],
        "limit": ["1"],
        "sortOrder": ["asc"],
        "startDate": ["1990-01-01"],
        "endDate": ["2026-11-07"],
    }
    assert first.headers["Accept"] == "application/json"
    assert [s for s in rig.sections_in_order() if s == "probe"] == ["probe"]
    # The UTC date of the start, not the athlete's local date.
    assert listing.oldest == _d("2019-03-02")
    assert rig.windows("daily")[0][0] == _d("2019-03-02")
    assert rig.posts == 1


def test_the_first_entry_of_the_ascending_activity_answer_is_the_oldest() -> None:
    entries = [
        {"activityId": 1, "startTimeGMT": "2019-03-02 23:30:00"},
        {"activityId": 2, "startTimeGMT": "2021-05-05 10:00:00"},
    ]
    _, listing = _list({"probe": _text(json.dumps(entries))}, oldest=None)
    assert listing.oldest == _d("2019-03-02")


@pytest.mark.parametrize("answer", [_text("[]"), _text("", 204)])
def test_an_account_with_no_activity_starts_one_year_before_the_pull(
    answer: HttpResponse,
) -> None:
    rig, listing = _list({"probe": answer}, oldest=None)
    # One year before the UTC date (6 November), not the local one.
    assert listing.oldest == _d("2025-11-06")
    assert rig.windows("daily")[0][0] == _d("2025-11-06")


def test_a_leap_day_pull_starts_on_the_28th_of_the_year_before() -> None:
    _, listing = _list(oldest=None, now=datetime(2028, 2, 29, 9, 0, tzinfo=UTC))
    assert listing.oldest == _d("2027-02-28")
    assert listing.newest == _d("2028-03-01")


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("not json", "not valid JSON"),
        ("[" * 200_000, "not valid JSON"),
        ("{}", "not a list"),
        ('{"startTimeGMT": "2019-03-02 23:30:00"}', "not a list"),
        ("[1]", "not an object"),
        ("[{}]", "no valid start"),
        ('[{"startTimeGMT": 20190302}]', "no valid start"),
        ('[{"startTimeGMT": null}]', "no valid start"),
        ('[{"startTimeGMT": "2019-03-02T23:30:00"}]', "no valid start"),
        ('[{"startTimeGMT": "2019-13-02 23:30:00"}]', "no valid start"),
        ('[{"startTimeLocal": "2019-03-02 23:30:00"}]', "no valid start"),
        ('[{"startTimeGMT": "2019-03-02 23:30:00", "x": NaN}]', "not valid JSON"),
        ('[{"startTimeGMT": "2019-03-02 23:30:00", "x": 1e999}]', "not valid JSON"),
    ],
    ids=lambda v: v[:40],
)
def test_a_malformed_oldest_activity_answer_is_named_and_not_quoted(
    body: str, problem: str
) -> None:
    marker_body = body.replace("{}", f'{{"note": "{_MARKER}"}}').replace(
        '{"s', f'{{"note": "{_MARKER}", "s'
    )
    rig, error = _fails({"probe": _text(marker_body)}, oldest=None)
    assert "oldest activity" in str(error)
    assert problem in str(error)
    assert _MARKER not in str(error)
    assert rig.sections_in_order() == ["probe"]


def test_an_activity_answer_with_a_marker_and_no_date_never_quotes_it() -> None:
    _, error = _fails(
        {"probe": _text(json.dumps([{"startTimeGMT": f"{_MARKER}"}]))}, oldest=None
    )
    assert _MARKER not in str(error)


# --------------------------------------------------------------------------
# What comes back (Req 9.5, 9.6, 9.7)
# --------------------------------------------------------------------------


def test_a_204_on_any_route_is_no_records_and_not_an_error() -> None:
    answers: dict[str, Answer] = {s: _text("", 204) for s in _SECTIONS}
    rig, listing = _list(answers)
    assert listing.days == ()
    assert (listing.oldest, listing.newest) == (_d("2026-11-01"), _NEWEST)
    assert len(rig.gets()) == 4


@pytest.mark.parametrize("silent", _SECTIONS)
def test_a_204_on_one_route_leaves_the_others_records_listed(silent: str) -> None:
    answers: dict[str, Answer] = {
        s: _body(s, [_rec(s, "2026-11-03", **{f"{s}Value": 1})])
        for s in _SECTIONS
        if s != silent
    }
    answers[silent] = _text("", 204)
    _, listing = _list(answers)
    assert len(listing.days) == 1
    assert set(listing.days[0].record) == set(_SECTIONS) - {silent}  # type: ignore[call-overload]


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_204_for_a_window_leaves_the_routes_later_windows_requested(
    section: str,
) -> None:
    first = _d("2024-01-01")
    newest = _d("2026-11-06")
    expected = _expected_windows(first, newest, _LIMIT[section])

    def answer(start: date, end: date) -> HttpResponse:
        if end == newest:
            return _body(section, [_rec(section, end.isoformat(), v=1)])
        return _text("", 204)

    rig, listing = _list(
        {section: answer}, oldest=first, now=datetime(2026, 11, 5, 12, tzinfo=UTC)
    )
    assert rig.windows(section) == expected
    assert [d.day for d in listing.days] == [newest]


@pytest.mark.parametrize("section", _SECTIONS)
@pytest.mark.parametrize("values", [{}, {"a": None, "b": None}], ids=["bare", "nulls"])
def test_a_record_with_a_date_and_no_values_is_still_a_record_garmin_returned(
    section: str, values: dict[str, object]
) -> None:
    record = _rec(section, "2026-11-03", **values)
    _, listing = _list({section: _body(section, [record])})
    assert [d.record for d in listing.days] == [{section: record}]
    assert listing.days[0].revision is not None


def test_a_date_is_merged_across_sections_and_a_date_with_no_record_is_not_listed() -> (
    None
):
    answers: dict[str, Answer] = {
        "daily": _body(
            "daily",
            [
                _rec("daily", "2026-11-05", steps=111),
                _rec("daily", "2026-11-02", steps=222),
            ],
        ),
        "sleep": _body("sleep", [_rec("sleep", "2026-11-05", score=333)]),
        "hrv": _body("hrv", [_rec("hrv", "2026-11-04", lastNightAvg=44)]),
        "weight": _body(
            "weight",
            [
                _rec("weight", "2026-11-05", weight=55555),
                _rec("weight", "2026-11-04", weight=66666),
            ],
        ),
    }
    _, listing = _list(answers)
    assert [d.day for d in listing.days] == [
        _d("2026-11-02"),
        _d("2026-11-04"),
        _d("2026-11-05"),
    ]
    by_day = {d.day: d.record for d in listing.days}
    assert by_day[_d("2026-11-05")] == {
        "daily": {"calendarDate": "2026-11-05", "steps": 111},
        "sleep": {"calendarDate": "2026-11-05", "score": 333},
        "weight": {"summaryDate": "2026-11-05", "weight": 55555},
    }
    assert by_day[_d("2026-11-04")] == {
        "hrv": {"calendarDate": "2026-11-04", "lastNightAvg": 44},
        "weight": {"summaryDate": "2026-11-04", "weight": 66666},
    }
    assert by_day[_d("2026-11-02")] == {
        "daily": {"calendarDate": "2026-11-02", "steps": 222}
    }
    assert _d("2026-11-03") not in by_day
    assert all(isinstance(d, WellnessDay) for d in listing.days)


def test_a_record_survives_verbatim_with_unknown_nested_and_non_ascii_fields() -> None:
    record = _rec(
        "daily",
        "2026-11-03",
        steps=0,
        unknownFuture={"deep": [1, 2.5, None, True, {"x": "café"}]},
        note="über",
        empty=[],
    )
    _, listing = _list({"daily": _body("daily", [record])})
    assert listing.days[0].record == {"daily": record}


def test_a_later_record_for_the_same_date_and_section_wins() -> None:
    # The second window answers for a date the first also answered for, twice.
    first = _d("2025-12-01")
    now = datetime(2026, 12, 31, tzinfo=UTC)

    def daily(start: date, end: date) -> HttpResponse:
        if start == first:
            return _body("daily", [_rec("daily", "2026-12-01", steps=1)])
        return _body(
            "daily",
            [
                _rec("daily", "2026-12-01", steps=2),
                _rec("daily", "2026-12-01", steps=3),
            ],
        )

    rig, listing = _list({"daily": daily}, oldest=first, now=now)
    assert len(rig.windows("daily")) == 2
    assert len(listing.days) == 1
    assert listing.days[0].record == {
        "daily": {"calendarDate": "2026-12-01", "steps": 3}
    }


@pytest.mark.parametrize("stated", ["2019-01-01", "2031-01-01"])
def test_a_date_outside_the_requested_range_is_kept_as_the_service_sent_it(
    stated: str,
) -> None:
    _, listing = _list({"daily": _body("daily", [_rec("daily", stated, s=1)])})
    assert [d.day for d in listing.days] == [_d(stated)]
    assert (listing.oldest, listing.newest) == (_d("2026-11-01"), _NEWEST)


def test_days_are_sorted_and_each_date_is_listed_once_across_windows() -> None:
    first = _d("2025-06-01")

    def sleep(start: date, end: date) -> HttpResponse:
        # Newest date first inside each window, and the same date again in
        # the next window.
        return _body(
            "sleep",
            [
                _rec("sleep", end.isoformat(), w=end.isoformat()),
                _rec("sleep", start.isoformat(), w=start.isoformat()),
                _rec("sleep", "2025-06-15", w="shared"),
            ],
        )

    rig, listing = _list(
        {"sleep": sleep}, oldest=first, now=datetime(2025, 8, 1, tzinfo=UTC)
    )
    assert len(rig.windows("sleep")) == 3
    days = [d.day for d in listing.days]
    assert days == sorted(set(days))
    assert len(days) == len(set(days))


# --------------------------------------------------------------------------
# The revision (Req 9.7)
# --------------------------------------------------------------------------


def _one_day(answers: Mapping[str, Answer]) -> WellnessDay:
    _, listing = _list(answers)
    assert len(listing.days) == 1
    return listing.days[0]


def _record_set(steps: int = 1, score: int = 2) -> dict[str, Answer]:
    return {
        "daily": _body("daily", [_rec("daily", "2026-11-03", steps=steps)]),
        "sleep": _body("sleep", [_rec("sleep", "2026-11-03", score=score)]),
    }


def test_the_revision_is_sha256_over_the_merged_records_canonical_form() -> None:
    day = _one_day(_record_set())
    canonical = (
        '{"daily":{"calendarDate":"2026-11-03","steps":1},'
        '"sleep":{"calendarDate":"2026-11-03","score":2}}'
    )
    assert day.revision == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", day.revision or "")
    assert day.revision == (
        "sha256:cfffba9fe197c83662b5dd8ae43df8bfca4908142e0ac248db778b221e6e019b"
    )


def test_a_non_ascii_value_is_hashed_in_its_escaped_form() -> None:
    day = _one_day(
        {"daily": _text('{"data":[{"calendarDate":"2026-11-03","n":"caf\u00e9"}]}')}
    )
    canonical = '{"daily":{"calendarDate":"2026-11-03","n":"caf\\u00e9"}}'
    assert day.revision == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def test_a_lone_surrogate_in_a_value_is_kept_and_hashed() -> None:
    day = _one_day(
        {"daily": _text('{"data":[{"calendarDate":"2026-11-03","n":"\\ud83d"}]}')}
    )
    assert day.record == {"daily": {"calendarDate": "2026-11-03", "n": "\ud83d"}}
    assert day.revision is not None


def test_a_repeated_listing_keeps_the_same_revision() -> None:
    first = _one_day(_record_set())
    # A later pull: a revision that read the clock would differ here.
    _, later = _list(_record_set(), now=_NOW + timedelta(days=1))
    assert first.revision == later.days[0].revision
    assert first.revision is not None


def test_key_order_in_the_response_does_not_change_the_revision() -> None:
    plain = _one_day(_record_set())
    reordered = _one_day(
        {
            "daily": _text('{"data":[{"steps":1,"calendarDate":"2026-11-03"}]}'),
            "sleep": _text('[{"score":2,"calendarDate":"2026-11-03"}]'),
        }
    )
    assert list(reordered.record)[0] == "daily"  # type: ignore[call-overload]
    assert reordered.revision == plain.revision


def test_a_changed_section_changes_the_revision_and_only_that_days() -> None:
    base = _one_day(_record_set())
    steps = _one_day(_record_set(steps=9))
    score = _one_day(_record_set(score=9))
    assert len({base.revision, steps.revision, score.revision}) == 3
    answers = _record_set()
    answers["sleep"] = _body(
        "sleep",
        [_rec("sleep", "2026-11-03", score=2), _rec("sleep", "2026-11-04", score=5)],
    )
    _, listing = _list(answers)
    by_day = {d.day: d.revision for d in listing.days}
    assert by_day[_d("2026-11-03")] == base.revision
    assert by_day[_d("2026-11-04")] != base.revision


def test_a_section_arriving_changes_the_revision() -> None:
    answers = _record_set()
    answers["hrv"] = _body("hrv", [_rec("hrv", "2026-11-03", avg=40)])
    assert _one_day(answers).revision != _one_day(_record_set()).revision


# --------------------------------------------------------------------------
# Malformed answers end the pull (Req 9.9)
# --------------------------------------------------------------------------


def _wrapped(section: str, record: str) -> str:
    """A 200 body in the section's documented form around one record's text."""
    return {
        "daily": f'{{"data": [{record}]}}',
        "sleep": f"[{record}]",
        "hrv": f'{{"hrvSummaries": [{record}]}}',
        "weight": f'{{"dailyWeightSummaries": [{record}]}}',
    }[section]


@pytest.mark.parametrize("section", _SECTIONS)
@pytest.mark.parametrize(
    "form",
    ["not json", "string", "number", "null", "wrong-container", "missing-key"],
)
def test_a_response_not_in_its_documented_form_ends_the_pull_naming_the_section(
    section: str, form: str
) -> None:
    list_form = section == "sleep"
    wrong_container = json.dumps({"data": []} if list_form else [{"note": _MARKER}])
    bodies = {
        "not json": f"not json {_MARKER}",
        "string": json.dumps(_MARKER),
        "number": "5",
        "null": "null",
        "wrong-container": wrong_container,
        "missing-key": json.dumps({"other": [_MARKER]}),
    }
    rig, error = _fails({section: _text(bodies[form])})
    assert _DISPLAY[section] in str(error)
    assert _MARKER not in str(error)
    assert rig.sections_in_order()[-1] == section
    if form == "not json":
        assert "not valid JSON" in str(error)


@pytest.mark.parametrize("section", _SECTIONS)
def test_nesting_too_deep_to_read_ends_the_pull_naming_the_section(
    section: str,
) -> None:
    _, error = _fails({section: _text("[" * 200_000)})
    assert _DISPLAY[section] in str(error)
    assert "not valid JSON" in str(error)


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_byte_that_is_not_utf8_inside_a_value_ends_the_pull(section: str) -> None:
    record = _wrapped(section, f'{{"{_DATE_FIELD[section]}": "2026-11-02", "v": "X"}}')
    _, error = _fails({section: _text(record.encode().replace(b"X", b"\xff"))})
    assert _DISPLAY[section] in str(error)
    assert "not valid JSON" in str(error)


@pytest.mark.parametrize("section", ["daily", "hrv", "weight"])
@pytest.mark.parametrize("held", [{"note": _MARKER}, None, 0, "", False, {}], ids=repr)
def test_a_key_holding_something_other_than_a_list_is_named(
    section: str, held: object
) -> None:
    key = {"daily": "data", "hrv": "hrvSummaries", "weight": "dailyWeightSummaries"}[
        section
    ]
    _, error = _fails({section: _text(json.dumps({key: held}))})
    assert _DISPLAY[section] in str(error)
    assert "the records are not a list" in str(error)
    assert _MARKER not in str(error)


@pytest.mark.parametrize("section", _SECTIONS)
@pytest.mark.parametrize("record", [1, "x", None, [], [{"note": 1}], True])
def test_a_record_that_is_not_an_object_ends_the_pull_naming_the_section(
    section: str, record: object
) -> None:
    good = _rec(section, "2026-11-02", note=_MARKER)
    rig, error = _fails({section: _body(section, [good, record])})
    assert _DISPLAY[section] in str(error)
    assert "record 2 is not an object" in str(error)
    assert _MARKER not in str(error)
    assert rig.sections_in_order()[-1] == section


_BAD_DATES: list[object] = [
    "2020-1-1",
    "20200101",
    "2020-13-01",
    "2020-02-30",
    "2021-02-29",
    "2020-01-01 ",
    "2020-01-01\n",
    "2020-01-01T00:00:00",
    "２０２０-01-01",
    "2020-W01-1",
    "",
    f"{_MARKER}",
    20200101,
    None,
    ["2020-01-01"],
]


@pytest.mark.parametrize("section", _SECTIONS)
@pytest.mark.parametrize("bad", _BAD_DATES, ids=lambda v: repr(v)[:24])
def test_an_invalid_date_ends_the_pull_naming_the_section_and_never_quoting_it(
    section: str, bad: object
) -> None:
    rig, error = _fails(
        {section: _body(section, [{_DATE_FIELD[section]: bad, "note": _MARKER}])}
    )
    assert _DISPLAY[section] in str(error)
    impossible = bad in ("2020-13-01", "2020-02-30", "2021-02-29")
    assert (
        "record 1 has an invalid calendar date"
        if impossible
        else "record 1 has no YYYY-MM-DD date"
    ) in str(error)
    assert _MARKER not in str(error)
    assert "2020" not in str(error)
    assert rig.sections_in_order()[-1] == section


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_record_without_its_date_field_ends_the_pull_whatever_other_date_it_has(
    section: str,
) -> None:
    decoy = "summaryDate" if _DATE_FIELD[section] == "calendarDate" else "calendarDate"
    _, error = _fails(
        {section: _body(section, [{decoy: "2026-11-02", "note": _MARKER}])}
    )
    assert _DISPLAY[section] in str(error)
    assert _MARKER not in str(error)


@pytest.mark.parametrize("section", _SECTIONS)
@pytest.mark.parametrize(
    "number",
    ["NaN", "Infinity", "-Infinity", "1e999", "-1E400", '{"w": [1e999]}', "9" * 5000],
    ids=lambda v: v[:12],
)
def test_a_number_that_cannot_be_held_is_a_named_problem_and_never_quoted(
    section: str, number: str
) -> None:
    field = _DATE_FIELD[section]
    record = f'{{"{field}": "2026-11-02", "v": {number}, "n": "{_MARKER}"}}'
    _, error = _fails({section: _text(_wrapped(section, record))})
    assert _DISPLAY[section] in str(error)
    assert "not valid JSON" in str(error)
    assert _MARKER not in str(error)


def test_a_malformed_later_window_leaves_no_partial_listing() -> None:
    first = _d("2025-01-01")

    def weight(start: date, end: date) -> HttpResponse:
        if start == first:
            return _body("weight", [_rec("weight", "2025-01-02", w=1)])
        return _text("not json")

    rig = _Rig({"weight": weight}, now=datetime(2026, 11, 5, tzinfo=UTC))
    with pytest.raises(ConnectorError) as excinfo:
        GarminConnector().list_wellness(rig.session, first)
    assert "weight" in str(excinfo.value)
    assert len(rig.windows("weight")) == 2


# --------------------------------------------------------------------------
# Statuses not yet mapped to a failure of their own (4.3 maps them)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("section", _SECTIONS)
@pytest.mark.parametrize("status", [400, 404, 500])
def test_any_other_status_ends_the_pull_naming_the_section_and_the_status(
    section: str, status: int
) -> None:
    _, error = _fails({section: lambda s, e: _text(f"oops {_MARKER}", status)})
    assert _DISPLAY[section] in str(error)
    assert str(status) in str(error)
    assert _MARKER not in str(error)


def test_a_status_the_activity_probe_does_not_expect_is_named() -> None:
    _, error = _fails({"probe": _text(f"oops {_MARKER}", 404)}, oldest=None)
    assert "oldest activity" in str(error)
    assert "404" in str(error)
    assert _MARKER not in str(error)


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_transport_failure_ends_the_pull_with_a_named_error(section: str) -> None:
    _, error = _fails({section: TransportError(f"down {_MARKER}")})
    assert f"for the {_DISPLAY[section]} request" in str(error)
    assert _MARKER not in str(error)


def test_a_transport_failure_on_the_activity_probe_is_named() -> None:
    _, error = _fails({"probe": TransportError(f"down {_MARKER}")}, oldest=None)
    assert "for the oldest activity request" in str(error)
    assert _MARKER not in str(error)


# --------------------------------------------------------------------------
# Packaging (task 4.2; Req 9.8)
# --------------------------------------------------------------------------

_ENVELOPE_FORMAT = "fitdocs.garmin-personal-wellness"
_FETCHED = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)


def _real_answers() -> dict[str, Answer]:
    return {
        "daily": _body(
            "daily",
            [
                _rec(
                    "daily",
                    "2026-11-03",
                    heartRate={"restingValue": 52, "minValue": 44, "maxValue": 131},
                    movement={"steps": {"value": 9871}},
                )
            ],
        ),
        "sleep": _body(
            "sleep",
            [_rec("sleep", "2026-11-03", deepSleepSeconds=5400, remSleepSeconds=5100)],
        ),
        "hrv": _body("hrv", [_rec("hrv", "2026-11-03", lastNightAvg=47)]),
        "weight": _body(
            "weight",
            [_rec("weight", "2026-11-03", latestWeight={"weight": 71234.5})],
        ),
    }


def _day_of(day: str, **record: object) -> WellnessDay:
    return WellnessDay(day=_d(day), revision="sha256:x", record=dict(record))


def _package(
    days: tuple[WellnessDay, ...], *, now: datetime = _NOW
) -> tuple[_Rig, WellnessPackage]:
    rig = _Rig(now=now)
    return rig, GarminConnector().package_wellness(rig.session, days)


def _envelope(package: WellnessPackage) -> dict[str, Any]:
    loaded = json.loads(package.data.decode("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_a_listed_day_is_packaged_claimed_by_one_format_and_read_back(
    tmp_path: Path,
) -> None:
    _, listing = _list(_real_answers())
    rig = _Rig(now=_NOW)
    package = GarminConnector().package_wellness(rig.session, listing.days)
    path = tmp_path / "wellness-2026-11-03_2026-11-03.json"
    path.write_bytes(package.data)
    probe = CandidateProbe.open(path)
    assert {f.id for f in wellness_registry.FORMATS if f.recognize(probe)} == {
        "garmin-personal"
    }
    assert wellness_registry.recognize(probe) == wellness_registry.Recognized(
        PERSONAL_FORMAT
    )
    (snapshot,) = tuple(PERSONAL_FORMAT.parse(io.BytesIO(package.data)))
    assert snapshot.day == _d("2026-11-03")
    values = snapshot.values
    assert values[Metric.RESTING_HR_BPM] == 52
    assert values[Metric.MIN_HR_BPM] == 44
    assert values[Metric.MAX_HR_BPM] == 131
    assert values[Metric.STEPS] == 9871
    assert values[Metric.HRV_RMSSD_MS] == 47
    assert values[Metric.WEIGHT_KG] == pytest.approx(71.2345)
    assert values[Metric.SLEEP_S] == 10500
    assert set(snapshot.origins.values()) == {"garmin"}
    assert set(snapshot.origins) == set(values)
    # 23:30 at UTC-8 on 5 November is 07:30 on 6 November in UTC.
    assert snapshot.revision == "2026-11-06T07:30:00.000000Z"


def test_the_framework_package_check_accepts_the_real_bytes() -> None:
    _, listing = _list(_real_answers())
    rig = _Rig()
    package = GarminConnector().package_wellness(rig.session, listing.days)
    assert (package.suffix, package.format) == (".json", "garmin-personal")
    assert package.origins == frozenset({"garmin"})
    assert (
        wellness_package_problem(
            package.data, package.suffix, package.format, package.origins
        )
        is None
    )
    # The check is live: a wrong format id or origin is a named problem.
    assert wellness_package_problem(
        package.data, package.suffix, "Garmin_Personal", package.origins
    )
    assert wellness_package_problem(
        package.data, package.suffix, package.format, frozenset({"Garmin"})
    )


def test_the_envelope_names_its_format_and_version_and_nothing_else() -> None:
    _, package = _package((_day_of("2026-11-03", daily={"a": 1}),))
    envelope = _envelope(package)
    assert set(envelope) == {"format", "version", "days"}
    assert envelope["format"] == _ENVELOPE_FORMAT
    assert envelope["version"] == 1 and type(envelope["version"]) is int


def test_days_are_sorted_by_date_whatever_order_they_arrive_in() -> None:
    days = tuple(
        _day_of(day, daily={"n": index})
        for index, day in enumerate(["2026-11-03", "2025-12-31", "2026-01-05"])
    )
    _, package = _package(days)
    assert [d["date"] for d in _envelope(package)["days"]] == [
        "2025-12-31",
        "2026-01-05",
        "2026-11-03",
    ]
    _, reversed_package = _package(tuple(reversed(days)))
    assert reversed_package.data == package.data


# A record's revision hashes its content, so a real repeat with other content
# has another revision.
@pytest.mark.parametrize("revision", ["sha256:x", "sha256:y"])
def test_a_repeated_date_is_refused_by_name_and_makes_no_request(
    revision: str,
) -> None:
    rig = _Rig()
    days = (
        _day_of("2026-11-03", daily={"n": 1}),
        _day_of("2026-11-04", daily={"n": 2}),
        WellnessDay(
            day=_d("2026-11-03"), revision=revision, record={"daily": {"n": 3}}
        ),
    )
    with pytest.raises(ConnectorError, match="2026-11-03") as excinfo:
        GarminConnector().package_wellness(rig.session, days)
    assert not isinstance(excinfo.value, AuthFailure)
    assert rig.requests == []


def test_each_day_is_stamped_with_the_clocks_utc_instant_with_six_digits() -> None:
    cases = [
        # microsecond 0 at a non-UTC offset: a plain isoformat() would drop
        # the fraction and keep the offset.
        (datetime(2026, 11, 5, 23, 30, 0, tzinfo=_WEST), "2026-11-06T07:30:00.000000Z"),
        (datetime(2026, 11, 5, 12, 0, 0, 7, tzinfo=UTC), "2026-11-05T12:00:00.000007Z"),
        (
            datetime(
                2026, 1, 1, 0, 0, 0, 123450, tzinfo=timezone(timedelta(hours=5.5))
            ),
            "2025-12-31T18:30:00.123450Z",
        ),
    ]
    days = (_day_of("2026-11-03", daily={}), _day_of("2026-11-04", daily={}))
    for now, expected in cases:
        _, package = _package(days, now=now)
        stamps = [d["fetched_at"] for d in _envelope(package)["days"]]
        assert stamps == [expected, expected]
        assert _FETCHED.fullmatch(stamps[0])


def test_a_later_clock_gives_a_later_stamp_down_to_the_microsecond() -> None:
    base = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)
    instants = [
        base,
        base + timedelta(microseconds=1),
        base + timedelta(microseconds=999999),
        base + timedelta(seconds=1),
        base + timedelta(days=400),
    ]
    stamps = []
    for now in instants:
        _, package = _package((_day_of("2026-11-03", daily={}),), now=now)
        stamps.append(_envelope(package)["days"][0]["fetched_at"])
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_sections_are_verbatim_and_an_absent_section_is_absent() -> None:
    record: dict[str, object] = {
        "sleep": {"deepSleepSeconds": 5400, "nested": {"note": "naïve — ✓"}},
        "weight": {"latestWeight": {"weight": 71234.5}},
    }
    _, package = _package((_day_of("2026-11-03", **record),))
    (day,) = _envelope(package)["days"]
    assert set(day) == {"date", "fetched_at", "sleep", "weight"}
    assert day["sleep"] == record["sleep"] and day["weight"] == record["weight"]


def test_a_section_field_named_date_stays_nested_and_cannot_override() -> None:
    record: dict[str, object] = {
        "daily": {"date": "1999-01-01", "fetched_at": "x"},
        "date": "1999-01-01",
        "fetched_at": "1999-01-01T00:00:00.000000Z",
    }
    _, package = _package((_day_of("2026-11-03", **record),))
    (day,) = _envelope(package)["days"]
    assert day["date"] == "2026-11-03"
    assert day["fetched_at"] == "2026-11-06T07:30:00.000000Z"
    assert day["daily"] == {"date": "1999-01-01", "fetched_at": "x"}


def test_the_serialization_is_canonical_utf8_and_repeatable() -> None:
    first = _day_of("2026-11-03", weight={"z": 1, "a": 2}, daily={"b": "é", "a": [1]})
    second = _day_of("2026-11-03", daily={"a": [1], "b": "é"}, weight={"a": 2, "z": 1})
    _, one = _package((first,))
    _, two = _package((second,))
    assert one.data == two.data
    assert one.data == (
        b'{"days":[{"daily":{"a":[1],"b":"\\u00e9"},"date":"2026-11-03",'
        b'"fetched_at":"2026-11-06T07:30:00.000000Z","weight":{"a":2,"z":1}}],'
        b'"format":"fitdocs.garmin-personal-wellness","version":1}'
    )
    one.data.decode("utf-8")


def test_a_lone_surrogate_in_a_value_still_packages_to_valid_utf8() -> None:
    _, package = _package((_day_of("2026-11-03", daily={"note": "\ud800"}),))
    assert _envelope(package)["days"][0]["daily"] == {"note": "\ud800"}


def test_a_record_that_is_not_an_object_is_refused_by_name() -> None:
    rig = _Rig()
    bad = WellnessDay(day=_d("2026-11-03"), revision="r", record=["x"])
    with pytest.raises(ConnectorError, match="2026-11-03"):
        GarminConnector().package_wellness(rig.session, (bad,))
    assert rig.requests == []


def test_no_days_is_a_valid_empty_envelope_the_check_and_reader_accept() -> None:
    rig, package = _package(())
    assert _envelope(package) == {
        "format": _ENVELOPE_FORMAT,
        "version": 1,
        "days": [],
    }
    assert (
        wellness_package_problem(
            package.data, package.suffix, package.format, package.origins
        )
        is None
    )
    assert tuple(PERSONAL_FORMAT.parse(io.BytesIO(package.data))) == ()
    assert rig.requests == [] and rig.posts == 0 and rig.sleeps == []


def test_packaging_makes_no_request_mints_no_token_and_never_sleeps() -> None:
    rig, _ = _package(
        (_day_of("2026-11-03", daily={"a": 1}), _day_of("2026-11-04", daily={}))
    )
    assert rig.requests == [] and rig.posts == 0 and rig.sleeps == []
