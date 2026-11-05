"""The Garmin wellness listing and package (garmin-connector tasks 4.1, 4.2, 4.3).

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
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner, Result

import fitdocs.cli as cli_module
import fitdocs.connectors.garmin as garmin_module
from fitdocs.cli import app
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.delivery import wellness_package_problem
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.garmin import GarminConnector
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from fitdocs.connectors.ledger import load_ledger
from fitdocs.connectors.protocol import (
    ConnectorSession,
    CredentialAccess,
    Fetched,
    FetchResult,
    RemoteActivity,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.pull import InstancePullReport, PullOptions, run_pull
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from fitdocs.wellness import read_series
from fitdocs.wellness import registry as wellness_registry
from fitdocs.wellness.formats.garmin import PERSONAL_FORMAT
from fitdocs.wellness.model import Metric
from fitdocs.wellness.probe import CandidateProbe
from tests.connectors.test_garmin_pull import (
    FILE_ROUTE,
    HOST,
    LISTING_ROUTE,
    _Cli,
    _Garmin,
    _history,
)
from tests.wellness.builders_garmin import (
    garmin_file_bytes,
    garmin_file_name,
    garmin_uds_record,
)

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
        token: HttpResponse | TransportError | None = None,
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
                if isinstance(token, TransportError):
                    raise token
                return token if token is not None else _text(_TOKEN)
            section, start, end = _classify(request)
            answer = self.answers[section]
            if isinstance(answer, TransportError):
                raise answer
            if callable(answer):
                return answer(start or date.min, end or date.min)
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
# Failures of the request itself (task 4.3; Req 11.3-11.6, 4.7, 4.8, 6.8)
# --------------------------------------------------------------------------

_RESTART = "the next pull starts the wellness listing again"
_ROUTES = (*_SECTIONS, "probe")
_ROUTE_DISPLAY = {**_DISPLAY, "probe": "oldest activity"}


def _route_fails(
    route: str, answer: Answer, *, oldest: date | None = date(2026, 11, 1)
) -> tuple[_Rig, Exception]:
    """A listing whose ``route`` is answered with ``answer`` and which ends in
    an error. The probe is only asked when no earliest date is given."""
    rig = _Rig({route: answer})
    with pytest.raises(Exception) as excinfo:
        GarminConnector().list_wellness(
            rig.session, None if route == "probe" else oldest
        )
    return rig, excinfo.value


def _status(status: int, body: str = f"oops {_MARKER}") -> Answer:
    return lambda s, e: _text(body, status)


@pytest.mark.parametrize("route", _ROUTES)
def test_a_401_is_the_rejected_key_failure_with_the_new_key_step(route: str) -> None:
    rig, error = _route_fails(route, _status(401))
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.REJECTED
    assert "HTTP 401" in str(error)
    assert "Create a new key" in str(error)
    assert "fitdocs connect" in str(error)
    assert _MARKER not in str(error)
    # Not repeated: the one refused request is the last one made.
    assert _classify(rig.gets()[-1])[0] == route
    assert [_classify(r)[0] for r in rig.gets()].count(route) == 1


@pytest.mark.parametrize("route", _ROUTES)
def test_a_403_says_garmin_refused_its_terms_allow_it_and_names_wellness_false(
    route: str,
) -> None:
    rig, error = _route_fails(route, _status(403))
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.REJECTED
    text = str(error)
    assert "HTTP 403" in text
    assert "refused" in text
    assert "terms" in text
    assert "restrict access" in text
    assert "`wellness = false`" in text
    assert _ROUTE_DISPLAY[route] in text
    assert "bug" not in text.lower()
    assert _MARKER not in text
    assert [_classify(r)[0] for r in rig.gets()].count(route) == 1


@pytest.mark.parametrize("route", _ROUTES)
def test_a_429_past_the_waits_is_the_rate_limit_failure_with_the_restart_sentence(
    route: str,
) -> None:
    rig, error = _route_fails(route, _status(429))
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.RATE_LIMITED
    assert "HTTP 429" in str(error)
    assert _RESTART in str(error)
    assert "resumes where this one stopped" not in str(error)
    assert _MARKER not in str(error)
    assert rig.sleeps.count(30.0) >= 1 and 240.0 in rig.sleeps
    # One request, then a repeat after each of the four waits.
    assert [_classify(r)[0] for r in rig.gets()].count(route) == 5


def test_a_429_that_states_a_wait_too_long_to_honour_ends_the_pull() -> None:
    answer = HttpResponse(status=429, headers={"retry-after": "301"}, body=b"")
    rig, error = _route_fails("sleep", lambda s, e: answer)
    assert isinstance(error, AuthFailure)
    assert error.kind is AuthFailureKind.RATE_LIMITED
    assert error.retry_after_s == 301.0
    assert _RESTART in str(error)
    assert [s for s in rig.sleeps if s >= 30] == []


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("status", [500, 502, 503, 599])
def test_a_5xx_past_the_transports_retries_is_a_named_connector_error(
    route: str, status: int
) -> None:
    _, error = _route_fails(route, _status(status))
    assert type(error) is ConnectorError
    text = str(error)
    assert _ROUTE_DISPLAY[route] in text
    assert f"HTTP {status}" in text
    assert "unavailable" in text
    assert _RESTART in text
    assert _MARKER not in text


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("status", [400, 404, 418, 301])
def test_any_other_status_ends_the_pull_naming_the_route_the_status_and_the_restart(
    route: str, status: int
) -> None:
    _, error = _route_fails(route, _status(status))
    assert type(error) is ConnectorError
    text = str(error)
    assert _ROUTE_DISPLAY[route] in text
    assert f"HTTP {status}" in text
    assert "unexpected status" in text
    assert "unavailable" not in text
    assert _RESTART in text
    assert _MARKER not in text


@pytest.mark.parametrize("route", _ROUTES)
def test_a_transport_failure_names_the_route_and_the_restart(route: str) -> None:
    _, error = _route_fails(route, TransportError(f"down {_MARKER}"))
    assert type(error) is ConnectorError
    assert f"for the {_ROUTE_DISPLAY[route]} request" in str(error)
    assert _RESTART in str(error)
    assert _MARKER not in str(error)


@pytest.mark.parametrize("failing", [401, 403, 429, 500, 404])
def test_a_failure_on_a_later_route_delivers_no_day_from_the_earlier_ones(
    failing: int,
) -> None:
    rig = _Rig(
        {
            "daily": _body("daily", [_rec("daily", "2026-11-02")]),
            "sleep": _body("sleep", [_rec("sleep", "2026-11-03")]),
            "hrv": _body("hrv", [_rec("hrv", "2026-11-04")]),
            "weight": _status(failing),
        }
    )
    with pytest.raises(ConnectorError if failing in (500, 404) else AuthFailure):
        GarminConnector().list_wellness(rig.session, date(2026, 11, 1))
    # The earlier routes did answer, so the failure came after real records.
    assert rig.sections_in_order()[:3] == ["daily", "sleep", "hrv"]


def test_a_failure_on_a_later_window_of_a_route_delivers_no_listing() -> None:
    first = date(2026, 11, 5) - timedelta(days=100)
    rig = _Rig(
        {
            "sleep": lambda s, e: (
                _text("x", 500) if s > first + timedelta(days=60) else _empty("sleep")
            )
        }
    )
    with pytest.raises(ConnectorError):
        GarminConnector().list_wellness(rig.session, first)
    # The server error is asked again by the transport; the windows are the
    # distinct ones: two answered, the third failed, none after it.
    assert len(set(rig.windows("sleep"))) == 3
    assert rig.windows("hrv") == []


def test_a_429_waited_out_mid_listing_still_completes_the_listing() -> None:
    seen: list[date] = []

    def sleep_answer(start: date, end: date) -> HttpResponse:
        seen.append(start)
        if len(seen) == 2:
            return _text("slow down", 429)
        return _body("sleep", [_rec("sleep", start.isoformat())])

    rig, listing = _list({"sleep": sleep_answer}, oldest=date(2026, 9, 1))
    assert rig.sleeps.count(30.0) == 1
    assert len(seen) == 4
    assert len(set(rig.windows("sleep"))) == 3
    assert len(listing.days) == 3


def test_a_token_rate_limit_kept_from_activities_is_the_same_object_in_wellness() -> (
    None
):
    with tempfile.TemporaryDirectory() as root:
        rig = _Rig(data_root=Path(root), token=_text("slow down", 429))
        connector = GarminConnector()
        with pytest.raises(AuthFailure) as kept:
            connector.list_activities(rig.session, None)
        with pytest.raises(AuthFailure) as again:
            connector.list_wellness(rig.session, date(2026, 11, 1))
    assert again.value is kept.value
    assert rig.posts == 1


def test_the_activity_paths_rate_limit_wording_is_unchanged() -> None:
    # The activity paths' own sentence is untouched by the wellness wording.
    with tempfile.TemporaryDirectory() as root:
        rig = _Rig({"probe": _status(429)}, data_root=Path(root))
        with pytest.raises(AuthFailure) as excinfo:
            GarminConnector().list_activities(rig.session, None)
    assert "resumes where this one stopped" in str(excinfo.value)
    assert _RESTART not in str(excinfo.value)


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_transport_failure_ends_the_pull_with_a_named_error(section: str) -> None:
    _, error = _fails({section: TransportError(f"down {_MARKER}")})
    assert f"for the {_DISPLAY[section]} request" in str(error)
    assert _MARKER not in str(error)


def test_a_transport_failure_on_the_activity_probe_is_named() -> None:
    _, error = _fails({"probe": TransportError(f"down {_MARKER}")}, oldest=None)
    assert "for the oldest activity request" in str(error)
    assert _MARKER not in str(error)


# --- through the engine: a real ledger and inbox on disk -------------------


class _Engine:
    """Pulls through :func:`run_pull` against a routing transport, with the
    data root and inbox on disk and the clock set per pull. ``answers`` may be
    changed between pulls."""

    def __init__(self, root: Path, *, activities: list[object] | None = None) -> None:
        self.root = root
        self.inbox = root / "inbox"
        self.answers: dict[str, Answer] = {}
        self.activities = activities or []
        self.sleeps: list[float] = []
        self.requests: list[HttpRequest] = []

        class _Delivering(GarminConnector):
            def fetch_activity(
                self, session: ConnectorSession, activity: RemoteActivity
            ) -> FetchResult:
                return Fetched(
                    bytes([14, 16, 0, 0, 0, 0, 0, 0])
                    + b".FIT"
                    + activity.remote_id.encode()
                )

        self.instance = ConnectorInstance(
            "garmin", _Delivering(), 3, None, wellness=True
        )

    def transport(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        if request.method == "POST":
            return _text(_TOKEN)
        section, start, end = _classify(request)
        if section == "probe":
            answer = self.answers.get("probe")
            if answer is None:
                return _text(json.dumps(self.activities))
        else:
            answer = self.answers.get(section, _empty(section))
        if isinstance(answer, TransportError):
            raise answer
        if callable(answer):
            assert start is not None and end is not None
            return answer(start, end)
        return answer

    def pull(
        self, now: datetime, *, since: datetime | None = None
    ) -> InstancePullReport:
        report = run_pull(
            self.root,
            (self.instance,),
            inbox=self.inbox,
            store=None,
            transport=self.transport,
            options=PullOptions(since=since, dry_run=False),
            environ={env_var_name("garmin", "api_key"): _KEY},
            now=lambda: now,
            sleep=self.sleeps.append,
            redactor=Redactor(),
        )
        [one] = report.instances
        return one

    def mark(self) -> date | None:
        ledger = load_ledger(self.root, "garmin", connector_id="garmin")
        return None if ledger.wellness is None else ledger.wellness.through

    def ledger_days(self) -> list[date]:
        ledger = load_ledger(self.root, "garmin", connector_id="garmin")
        return [] if ledger.wellness is None else [e.day for e in ledger.wellness.days]

    def inbox_files(self) -> dict[str, bytes]:
        if not self.inbox.exists():
            return {}
        return {
            str(p.relative_to(self.inbox)): p.read_bytes()
            for p in sorted(self.inbox.rglob("*"))
            if p.is_file()
        }


_T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
_T1 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _records(section: str, first: date, last: date) -> Answer:
    """Answers each window with one record per day of it that lies in
    ``first`` to ``last``."""

    def answer(start: date, end: date) -> HttpResponse:
        days = [
            start + timedelta(days=n)
            for n in range((end - start).days + 1)
            if first <= start + timedelta(days=n) <= last
        ]
        return _body(section, [_rec(section, d.isoformat(), steps=d.day) for d in days])

    return answer


def _first_pull(tmp_path: Path) -> tuple[_Engine, InstancePullReport]:
    engine = _Engine(tmp_path)
    engine.answers = {"daily": _records("daily", date(2026, 11, 1), date(2026, 11, 4))}
    report = engine.pull(_T0)
    return engine, report


def test_the_first_successful_pull_delivers_days_and_moves_the_mark(
    tmp_path: Path,
) -> None:
    engine, report = _first_pull(tmp_path)
    assert report.error is None
    assert report.wellness is not None and report.wellness.error is None
    assert report.wellness.failed == ()
    assert engine.mark() == _T0.date() + timedelta(days=1)
    assert engine.ledger_days() == [date(2026, 11, d) for d in (1, 2, 3, 4)]
    assert len(engine.inbox_files()) == 1


_FAILURES: list[tuple[str, Answer]] = [
    ("401", _status(401)),
    ("403", _status(403)),
    ("429", _status(429)),
    ("500", _status(500)),
    ("502", _status(502)),
    ("404", _status(404)),
    ("transport", TransportError(f"down {_MARKER}")),
]


@pytest.mark.parametrize("label,failure", _FAILURES, ids=[f[0] for f in _FAILURES])
@pytest.mark.parametrize("route", _SECTIONS)
def test_a_failure_on_a_later_pull_keeps_the_earlier_deliveries_and_the_mark(
    tmp_path: Path, route: str, label: str, failure: Answer
) -> None:
    engine, first = _first_pull(tmp_path)
    mark = engine.mark()
    days = engine.ledger_days()
    files = engine.inbox_files()
    assert mark is not None and len(days) == 4 and len(files) == 1
    # The later pull would find new days on every route that answers, so a
    # delivery made before the failure would show in the inbox and ledger.
    engine.answers = {
        "daily": _records("daily", date(2026, 11, 1), date(2026, 11, 7)),
        "sleep": _records("sleep", date(2026, 11, 6), date(2026, 11, 7)),
        "hrv": _records("hrv", date(2026, 11, 6), date(2026, 11, 7)),
        "weight": _records("weight", date(2026, 11, 6), date(2026, 11, 7)),
    }
    engine.answers[route] = failure
    report = engine.pull(_T1)
    assert report.wellness is not None
    error = report.wellness.error
    assert error is not None
    assert _MARKER not in error.detail
    assert report.wellness.delivered == ()
    assert report.wellness.failed == ()
    assert engine.mark() == mark
    assert engine.ledger_days() == days
    assert engine.inbox_files() == files
    # The failing route was reached after the earlier routes had answered.
    order = [_classify(r)[0] for r in engine.requests if r.method == "GET"]
    assert order.count(route) >= 1
    assert "daily" in order


@pytest.mark.parametrize("label,failure", _FAILURES, ids=[f[0] for f in _FAILURES])
def test_a_failure_part_way_through_a_long_first_listing_leaves_no_mark_and_no_day(
    tmp_path: Path, label: str, failure: Answer
) -> None:
    engine = _Engine(tmp_path)
    since = datetime(2024, 1, 1, tzinfo=UTC)
    seen: list[date] = []

    def sleeping(start: date, end: date) -> HttpResponse:
        seen.append(start)
        if len(seen) > 20:
            if isinstance(failure, TransportError):
                raise failure
            assert callable(failure)
            return failure(start, end)
        return _body("sleep", [_rec("sleep", start.isoformat(), score=1)])

    engine.answers = {
        "daily": _records("daily", date(2024, 1, 1), date(2026, 11, 4)),
        "sleep": sleeping,
    }
    report = engine.pull(_T0, since=since)
    # Hundreds of days were listed first: 20 sleep windows of 31 days, and
    # the daily route's three windows, all before the failure.
    assert len(set(seen)) == 21
    assert report.wellness is not None and report.wellness.error is not None
    assert report.wellness.delivered == ()
    assert engine.mark() is None
    assert engine.ledger_days() == []
    assert engine.inbox_files() == {}


@pytest.mark.parametrize("label,failure", _FAILURES, ids=[f[0] for f in _FAILURES])
def test_a_failure_ends_the_listing_with_no_later_window_or_route_requested(
    label: str, failure: Answer
) -> None:
    # 67 days: sleep has later windows to go to, and HRV and weight follow it.
    first = date(2026, 9, 1)
    rig = _Rig({"sleep": failure})
    with pytest.raises((AuthFailure, ConnectorError)):
        GarminConnector().list_wellness(rig.session, first)
    asked = [_classify(request) for request in rig.gets()]
    assert asked[-1][0] == "sleep"
    assert {start for section, start, _ in asked if section == "sleep"} == {first}
    assert {section for section, _, _ in asked} == {"daily", "sleep"}


def test_a_wellness_429_meets_the_waits_activities_already_spent_this_pull(
    tmp_path: Path,
) -> None:
    # Three stated waits of 300 s spend the whole 900 s budget in activities.
    limited = iter(range(3))

    def listing(start: date, end: date) -> HttpResponse:
        if next(limited, None) is None:
            return _text("[]")
        return HttpResponse(status=429, headers={"retry-after": "300"}, body=b"")

    rig = _Rig({"probe": listing, "daily": _status(429)}, data_root=tmp_path)
    connector = GarminConnector()
    connector.list_activities(rig.session, None)
    assert [s for s in rig.sleeps if s > 1] == [300.0, 300.0, 300.0]
    with pytest.raises(AuthFailure) as excinfo:
        connector.list_wellness(rig.session, date(2026, 11, 1))
    assert excinfo.value.kind is AuthFailureKind.RATE_LIMITED
    assert _RESTART in str(excinfo.value)
    # The first 429 would wait 30 s with any budget left; none was slept.
    assert [s for s in rig.sleeps if s > 1] == [300.0, 300.0, 300.0]
    assert [_classify(r)[0] for r in rig.gets()].count("daily") == 1


def test_a_429_waited_out_mid_listing_still_delivers_and_moves_the_mark(
    tmp_path: Path,
) -> None:
    engine = _Engine(tmp_path)
    calls: list[date] = []

    def daily(start: date, end: date) -> HttpResponse:
        calls.append(start)
        if len(calls) == 2:
            return _text("slow down", 429)
        return _body("daily", [_rec("daily", "2026-11-03", steps=7)])

    engine.answers = {"daily": daily}
    report = engine.pull(_T0, since=datetime(2025, 6, 1, tzinfo=UTC))
    assert report.wellness is not None and report.wellness.error is None
    assert engine.sleeps.count(30.0) == 1
    assert engine.mark() == _T0.date() + timedelta(days=1)
    assert engine.ledger_days() == [date(2026, 11, 3)]
    assert len(engine.inbox_files()) == 1


def test_a_401_in_wellness_leaves_the_activities_delivered_this_pull(
    tmp_path: Path,
) -> None:
    entry = {
        "activityId": 4001,
        "startTimeGMT": "2026-11-04 10:00:00",
        "activityType": {"typeKey": "running"},
    }
    engine = _Engine(tmp_path, activities=[entry])
    engine.answers = {"daily": _status(401)}
    report = engine.pull(_T0)
    assert [d.remote_id for d in report.delivered] == ["4001"]
    assert report.error is None
    assert report.wellness is not None and report.wellness.error is not None
    assert "HTTP 401" in report.wellness.error.detail
    ledger = load_ledger(tmp_path, "garmin", connector_id="garmin")
    assert ledger.is_final("4001", None)
    assert engine.mark() is None
    names = list(engine.inbox_files())
    assert len(names) == 1 and names[0].endswith(".fit")
    assert (
        _classify([r for r in engine.requests if r.method == "GET"][-1])[0] == "daily"
    )


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


def test_a_token_failure_met_by_activities_reaches_wellness_with_one_token_request(
    tmp_path: Path,
) -> None:
    engine = _Engine(tmp_path)

    def refused(request: HttpRequest, timeout: float) -> HttpResponse:
        engine.requests.append(request)
        return _text("oops", 500)

    engine.transport = refused  # type: ignore[method-assign]
    report = engine.pull(_T0)
    assert report.error is not None
    assert report.wellness is not None and report.wellness.error is not None
    assert report.wellness.error.detail == report.error.detail
    assert [r.method for r in engine.requests] == ["POST"]


# --------------------------------------------------------------------------
# Through the real CLI: pull, ledger, inbox, drain and series (task 5.2;
# Req 9.1, 9.3, 10.8-10.12, 11.1, 11.2)
# --------------------------------------------------------------------------


_runner = CliRunner()
Sections = dict[str, dict[str, object]]
_PERSONAL_ID = "garmin-personal"
_CLI_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class _CliDatetime(datetime):
    """The CLI's ``datetime`` in this section: mid-June at noon, so the weeks
    before it share one year and no test crosses a midnight, and each read a
    second after the last, so a later delivery's stamp is later."""

    reads = 0

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
        cls.reads += 1
        moment = _CLI_NOW + timedelta(seconds=cls.reads)
        if tz is None:
            return moment.astimezone().replace(tzinfo=None)
        return moment.astimezone(tz)


class _WellnessGarmin(_Garmin):
    """The activity Garmin of the pull tests plus the four wellness routes.

    ``days`` maps a date to the sections Garmin holds for it; each route
    answers the dates inside the window it was asked for. ``fail`` makes a
    wellness route answer with a status, ``listing_status`` the activity
    listing and ``token_status`` the token request."""

    def __init__(self, history: dict[int, tuple[datetime, bytes]] | None = None):
        super().__init__(history or {})
        self.days: dict[date, Sections] = {}
        self.asked: list[str] = []
        self.probes = 0
        self.fail: dict[str, int] = {}
        self.listing_status: int | None = None
        self.token_status: int | None = None

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        parts = urlsplit(request.url)
        if request.method == "POST" and self.token_status is not None:
            self.seen.requests.append(request)
            self.seen.tokens += 1
            return _text("oops", self.token_status)
        if request.method == "GET" and parts.path == LISTING_ROUTE:
            if parse_qs(parts.query).get("limit") == ["1"]:
                self.probes += 1
            if self.listing_status is not None:
                self.seen.requests.append(request)
                return _text("oops", self.listing_status)
        if (
            request.method == "GET"
            and parts.path != LISTING_ROUTE
            and not parts.path.startswith(FILE_ROUTE)
        ):
            return self._wellness(request)
        return super().__call__(request, timeout)

    def _wellness(self, request: HttpRequest) -> HttpResponse:
        assert urlsplit(request.url).netloc == HOST
        assert request.secret_headers["Authorization"].reveal() == f"Bearer {_TOKEN}"
        self.seen.requests.append(request)
        section, first, last = _classify(request)
        assert first is not None and last is not None
        self.asked.append(section)
        if section in self.fail:
            return _text("oops", self.fail[section])
        records: list[object] = [
            _rec(section, day.isoformat(), **self.days[day][section])
            for day in sorted(self.days)
            if first <= day <= last and section in self.days[day]
        ]
        return _body(section, records)


def _today() -> date:
    return _CLI_NOW.date()


def _sections(k: int) -> Sections:
    """One day's records, every value a function of ``k``; among the ``k``
    any one test uses, no two values are equal."""
    return {
        "daily": {
            "heartRate": {"restingValue": 40 + k, "maxValue": 150 + k},
            "movement": {"steps": {"value": 5000 + 13 * k}},
        },
        "sleep": {
            "deepSleepSeconds": 3000 + 60 * k,
            "remSleepSeconds": 1500 + 70 * k,
        },
        "hrv": {"lastNightAvg": 30 + k},
        "weight": {"latestWeight": {"weight": 70000 + 100 * k}},
    }


def _expected(day_k: Mapping[date, int]) -> dict[tuple[date, str], float]:
    out: dict[tuple[date, str], float] = {}
    for day, k in day_k.items():
        out[(day, "resting_hr_bpm")] = 40 + k
        out[(day, "max_hr_bpm")] = 150 + k
        out[(day, "steps")] = 5000 + 13 * k
        out[(day, "sleep_deep_s")] = 3000 + 60 * k
        out[(day, "sleep_rem_s")] = 1500 + 70 * k
        out[(day, "sleep_s")] = 4500 + 130 * k
        out[(day, "hrv_rmssd_ms")] = 30 + k
        out[(day, "weight_kg")] = (70000 + 100 * k) / 1000
    return out


class _WellnessCli(_Cli):
    def __init__(self, root: Path, garmin: _WellnessGarmin, sleeps: list[float]):
        super().__init__(root, garmin, sleeps)
        self.wgarmin = garmin

    def configure(
        self, lookback_days: int | None = None, wellness: bool = True
    ) -> None:
        (self.root / "fitdocs.toml").write_text(
            f'[inbox]\npath = "inbox"\nsettle_seconds = 0\n\n'
            f"[connectors.garmin]\nwellness = {str(wellness).lower()}\n"
            f"lookback_days = {lookback_days or 5}\n",
            encoding="utf-8",
        )

    def run(self, *args: str, sync: bool = True) -> Result:
        flags = ["--sync"] if sync else []
        return _runner.invoke(
            app,
            ["pull", "garmin", *flags, "--no-prompt", "--out", str(self.root), *args],
        )

    def drain(self) -> Result:
        return _runner.invoke(app, ["sync", "--no-prompt", "--out", str(self.root)])

    def command(self, *args: str) -> Result:
        return _runner.invoke(app, [*args, "--out", str(self.root)])

    def personal(self) -> dict[tuple[date, str], float]:
        values = [v for v in read_series(self.root).values if v.source == _PERSONAL_ID]
        assert all(v.origin == "garmin" and v.canonical for v in values)
        return {(v.day, v.metric.value): v.value for v in values}

    def csv(self) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in sorted((self.root / "wellness").glob("*.csv"))
        }

    def archived(self) -> dict[str, dict[str, Any]]:
        folder = self.root / "wellness-archive" / _PERSONAL_ID
        return (
            {
                path.name: json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(folder.glob("*.json"))
            }
            if folder.exists()
            else {}
        )

    def ledger_wellness(self) -> Any:
        wellness = self.ledger().wellness
        assert wellness is not None
        return wellness


@pytest.fixture
def wcli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _WellnessCli:
    garmin = _WellnessGarmin()
    sleeps: list[float] = []
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: garmin)
    monkeypatch.setattr(cli_module, "datetime", _CliDatetime)
    monkeypatch.setattr(_CliDatetime, "reads", 0)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    monkeypatch.setenv(env_var_name("garmin", "api_key"), _KEY)
    root = tmp_path / "data-root"
    root.mkdir()
    cli = _WellnessCli(root, garmin, sleeps)
    cli.configure()
    return cli


def _ago(n: int) -> date:
    return _today() - timedelta(days=n)


def _table(output: str, label: str) -> int:
    """The count on the one row of ``output`` that carries ``label``."""
    [count] = re.findall(rf"│ {label}\s+│\s+(\d+) │", output)
    return int(count)


def test_no_wellness_request_unless_the_instance_enables_it(
    wcli: _WellnessCli,
) -> None:
    wcli.configure(wellness=False)
    wcli.wgarmin.days = {_ago(n): _sections(n) for n in (1, 2, 3)}

    off = wcli.run()

    assert off.exit_code == 0, off.output
    assert wcli.wgarmin.asked == [] and wcli.wgarmin.probes == 0
    assert wcli.ledger().wellness is None
    assert wcli.csv() == {} and wcli.archived() == {}

    # The same account with wellness enabled does ask: the quiet above is the
    # setting's, not an account with nothing to ask for.
    wcli.configure(wellness=True)
    on = wcli.run()
    assert on.exit_code == 0, on.output
    assert sorted(set(wcli.wgarmin.asked)) == ["daily", "hrv", "sleep", "weight"]
    assert wcli.wgarmin.probes == 1


def test_a_delivery_reaches_the_series_through_the_drain(wcli: _WellnessCli) -> None:
    ks = {_ago(n): n for n in (1, 2, 3, 10)}
    wcli.wgarmin.days = {day: _sections(k) for day, k in ks.items()}

    result = wcli.run()

    assert result.exit_code == 0, result.output
    assert wcli.personal() == _expected(ks)
    [(name, envelope)] = wcli.archived().items()
    assert [entry["date"] for entry in envelope["days"]] == sorted(
        day.isoformat() for day in ks
    )
    archived = wcli.root / "wellness-archive" / _PERSONAL_ID / name
    assert name == hashlib.sha256(archived.read_bytes()).hexdigest() + ".json"
    ledger = wcli.ledger_wellness()
    assert [entry.day for entry in ledger.days] == sorted(ks)
    assert ledger.through == _today() + timedelta(days=1)
    assert ledger.origins == ("garmin",)


def test_a_changed_day_is_delivered_again_and_an_unchanged_day_is_not(
    wcli: _WellnessCli,
) -> None:
    # lookback_days is 5: the second pull lists from the 5th day before the
    # mark, so day 10 is not listed again and days 3, 2 and 1 are.
    ks = {_ago(n): n for n in (1, 2, 3, 10)}
    wcli.wgarmin.days = {day: _sections(k) for day, k in ks.items()}
    assert wcli.run().exit_code == 0
    [(first_name, first)] = wcli.archived().items()
    before = {entry.day: entry for entry in wcli.ledger_wellness().days}

    # Day 3 changes its values and loses its HRV section; days 2 and 1 and 10
    # are as they were.
    changed = _sections(50)
    del changed["hrv"]
    wcli.wgarmin.days[_ago(3)] = changed
    second = wcli.run()

    assert second.exit_code == 0, second.output
    assert _table(second.output, "Days listed") == 3
    assert _table(second.output, "Days unchanged") == 2
    delivered = {n: e for n, e in wcli.archived().items() if n != first_name}
    [(second_name, envelope)] = delivered.items()
    assert [entry["date"] for entry in envelope["days"]] == [_ago(3).isoformat()]
    assert envelope["days"][0]["fetched_at"] > first["days"][0]["fetched_at"]
    after = {entry.day: entry for entry in wcli.ledger_wellness().days}
    assert after[_ago(3)].sha256 == second_name.removesuffix(".json")
    assert after[_ago(3)].revision != before[_ago(3)].revision
    for n in (1, 2, 10):
        assert after[_ago(n)] == before[_ago(n)]
    expected = _expected({day: k for day, k in ks.items() if k != 3})
    expected.update(
        {
            key: value
            for key, value in _expected({_ago(3): 50}).items()
            if key[1] != "hrv_rmssd_ms"
        }
    )
    assert (_ago(3), "hrv_rmssd_ms") not in expected
    assert wcli.personal() == expected


_ACTIVITY_REFUSALS = {
    401: "did not accept the Personal API key",
    403: "refused",
    429: "limiting requests",
}


@pytest.mark.parametrize("status", sorted(_ACTIVITY_REFUSALS))
def test_a_rejection_refusal_or_rate_limit_during_activities_suppresses_wellness(
    wcli: _WellnessCli, status: int
) -> None:
    wcli.wgarmin.days = {_ago(n): _sections(n) for n in (1, 2)}
    wcli.wgarmin.listing_status = status

    result = wcli.run()

    assert result.exit_code == 1, result.output
    assert _ACTIVITY_REFUSALS[status] in result.output
    assert wcli.wgarmin.asked == [] and wcli.wgarmin.probes == 0
    assert "garmin wellness" not in result.output
    methods = [(r.method, urlsplit(r.url).path) for r in wcli.wgarmin.seen.requests]
    assert {path for _, path in methods} == {
        garmin_module.TOKEN_PATH,
        LISTING_ROUTE,
    }
    assert wcli.ledger().wellness is None and wcli.csv() == {}


@pytest.mark.parametrize("status", [500, 502])
@pytest.mark.usefixtures("utc")
def test_a_listing_server_error_during_activities_still_runs_wellness(
    wcli: _WellnessCli, status: int
) -> None:
    ks = {_ago(n): n for n in (1, 2, 3)}
    wcli.wgarmin.days = {day: _sections(k) for day, k in ks.items()}
    wcli.wgarmin.listing_status = status

    result = wcli.run("--since", _ago(5).isoformat())

    assert result.exit_code == 1, result.output
    activities, wellness = result.output.split("fitdocs pull: garmin wellness")
    assert f"HTTP {status}" in activities
    assert _table(activities, "Error") == 1
    assert _table(wellness, "Error") == 0
    assert sorted(set(wcli.wgarmin.asked)) == ["daily", "hrv", "sleep", "weight"]
    assert wcli.personal() == _expected(ks)
    assert _table(wellness, "Days listed") == 3


@pytest.fixture
def utc(monkeypatch: pytest.MonkeyPatch) -> Any:
    """``--since`` is a local calendar day; pin the zone so the day it names
    is the UTC day the wellness listing starts from."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_a_token_server_error_ends_activities_and_wellness_with_one_token_request(
    wcli: _WellnessCli,
) -> None:
    wcli.wgarmin.days = {_ago(n): _sections(n) for n in (1, 2)}
    wcli.wgarmin.token_status = 500

    result = wcli.run()

    assert result.exit_code == 1, result.output
    activities, wellness = result.output.split("fitdocs pull: garmin wellness")
    [activity_error] = re.findall(r"Error:\n  (.+)\n", activities)
    [wellness_error] = re.findall(r"Error:\n  (.+)\n", wellness)
    assert "(HTTP 500) to the token request" in activity_error
    assert wellness_error == activity_error
    assert _table(activities, "Error") == 1 and _table(wellness, "Error") == 1
    assert wcli.wgarmin.seen.tokens == 1
    assert [r.method for r in wcli.wgarmin.seen.requests] == ["POST"]
    assert wcli.wgarmin.asked == [] and wcli.csv() == {}


def _export_files(inbox: Path, steps_day: date, steps: int) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    name = garmin_file_name("uds", steps_day, steps_day)
    (inbox / name).write_bytes(
        garmin_file_bytes(
            [garmin_uds_record(steps_day, totalSteps=steps, minHeartRate=33)]
        )
    )


def test_an_existing_series_rebuilds_once_with_no_value_lost(
    wcli: _WellnessCli, monkeypatch: pytest.MonkeyPatch
) -> None:
    exported, overlap = _ago(20), _ago(2)
    original = (wellness_registry.FORMATS, wellness_registry.SOURCES)
    # A data root as the version before this source built it: the registry
    # has neither the format nor the source.
    monkeypatch.setattr(
        wellness_registry,
        "FORMATS",
        tuple(f for f in original[0] if f is not PERSONAL_FORMAT),
    )
    monkeypatch.setattr(
        wellness_registry,
        "SOURCES",
        tuple(s for s in original[1] if s is not PERSONAL_FORMAT.source),
    )
    _export_files(wcli.root / "inbox", exported, 8123)
    _export_files(wcli.root / "inbox" / "again", overlap, 7777)
    old = wcli.drain()
    assert old.exit_code == 0, old.output
    before = wcli.csv()
    assert set(before) == {f"{exported.year}.csv"}
    exported_rows = [
        (v.day, v.metric.value, v.source, v.value)
        for v in read_series(wcli.root).values
    ]
    assert (exported, "steps", "garmin-export", 8123.0) in exported_rows
    assert (overlap, "steps", "garmin-export", 7777.0) in exported_rows

    monkeypatch.setattr(wellness_registry, "FORMATS", original[0])
    monkeypatch.setattr(wellness_registry, "SOURCES", original[1])

    assert wcli.command("check").exit_code == 1
    rebuilt = wcli.drain()
    assert rebuilt.exit_code == 0, rebuilt.output
    assert rebuilt.output.count("Wellness series: rebuilt") == 1
    assert "Values removed: 0" in rebuilt.output
    assert wcli.csv() == before
    assert wcli.command("check").exit_code == 0
    again = wcli.drain()
    assert again.exit_code == 0, again.output
    assert "Wellness series:" not in again.output
    assert wcli.csv() == before

    # The source then adds its own values beside the old ones; the export's
    # value stays the canonical one on the day both supply.
    wcli.wgarmin.days = {overlap: _sections(2), _ago(1): _sections(1)}
    pulled = wcli.run()
    assert pulled.exit_code == 0, pulled.output
    after = {
        (v.day, v.metric.value, v.source): (v.value, v.origin, v.canonical)
        for v in read_series(wcli.root).values
    }
    assert after[(exported, "steps", "garmin-export")] == (8123.0, "garmin", True)
    assert after[(overlap, "steps", "garmin-export")] == (7777.0, "garmin", True)
    assert after[(overlap, "steps", _PERSONAL_ID)] == (5026.0, "garmin", False)
    assert after[(_ago(1), "steps", _PERSONAL_ID)] == (5013.0, "garmin", True)


def test_a_delivery_that_cannot_be_read_is_named_and_leaves_the_series_unchanged(
    wcli: _WellnessCli,
) -> None:
    wcli.wgarmin.days = {_ago(n): _sections(n) for n in (1, 2, 3)}
    assert wcli.run().exit_code == 0
    before = wcli.csv()
    assert before and wcli.personal()

    # Day 2 changes; the delivery is pulled but not drained, then damaged in
    # the inbox where the pull put it: the envelope header is intact and one
    # day's fetch time is not in the fixed form.
    wcli.wgarmin.days[_ago(2)] = _sections(60)
    inbox_before = set((wcli.root / "inbox").rglob("*.json"))
    pulled = wcli.run(sync=False)
    assert pulled.exit_code == 0, pulled.output
    [path] = sorted(set((wcli.root / "inbox").rglob("*.json")) - inbox_before)
    rel = path.relative_to(wcli.root / "inbox").as_posix()
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert [entry["date"] for entry in envelope["days"]] == [_ago(2).isoformat()]
    envelope["days"][0]["fetched_at"] = "yesterday"
    damaged = json.dumps(envelope)
    path.write_text(damaged, encoding="utf-8")

    drained = wcli.drain()

    assert drained.exit_code == 1, drained.output
    assert _table(drained.output, "Wellness failed") == 1
    assert re.search(
        rf"Wellness failed:\n  {re.escape(rel)}\n"
        r"    invalid Garmin delivery fetch time\n",
        drained.output,
    )
    assert "Wellness series:" not in drained.output
    assert wcli.csv() == before
    assert len(wcli.archived()) == 1
    assert path.read_text(encoding="utf-8") == damaged


# --- a multi-year history (Req 9.2, 9.3, 11.6) -------------------------------

_YEARS_BACK = 1096


def _long_history(wcli: _WellnessCli, *, with_activity: bool) -> dict[date, int]:
    """Three years of daily steps, each day's value its own, and sleep on
    every tenth day; one activity on the first day when asked for."""
    ks = {_ago(n): n for n in range(1, _YEARS_BACK + 1)}
    days: dict[date, Sections] = {}
    for day, k in ks.items():
        days[day] = {"daily": {"movement": {"steps": {"value": 5000 + k}}}}
        if k % 10 == 0:
            days[day]["sleep"] = {"deepSleepSeconds": 3000 + k}
    wcli.wgarmin.days = days
    if with_activity:
        start = datetime.combine(_ago(_YEARS_BACK), datetime.min.time(), UTC)
        wcli.wgarmin.history = _history({7001: start + timedelta(hours=12)})
    return ks


def _steps(ks: Mapping[date, int]) -> dict[tuple[date, str], float]:
    out: dict[tuple[date, str], float] = {}
    for day, k in ks.items():
        out[(day, "steps")] = 5000 + k
        if k % 10 == 0:
            out[(day, "sleep_deep_s")] = 3000 + k
            out[(day, "sleep_s")] = 3000 + k
    return out


def _delivered_days(wcli: _WellnessCli, before: set[str]) -> list[str]:
    return sorted(
        entry["date"]
        for name, envelope in wcli.archived().items()
        if name not in before
        for entry in envelope["days"]
    )


def test_a_multi_year_history_is_delivered_by_one_plain_pull(
    wcli: _WellnessCli,
) -> None:
    ks = _long_history(wcli, with_activity=True)

    result = wcli.run()

    assert result.exit_code == 0, result.output
    assert wcli.wgarmin.probes == 1
    assert wcli.wgarmin.asked.count("daily") == 4  # 1,098 days, 365 to a window
    assert wcli.personal() == _steps(ks)
    assert _delivered_days(wcli, set()) == sorted(d.isoformat() for d in ks)
    ledger = wcli.ledger_wellness()
    assert [entry.day for entry in ledger.days] == sorted(ks)
    assert ledger.through is not None and ledger.through > max(ks)
    assert _table(result.output, "Days listed") == _YEARS_BACK
    wellness = result.output.split("fitdocs pull: garmin wellness")[1]
    assert _table(wellness.split("Inbox:")[0], "Failed") == 0


def test_a_second_pull_delivers_only_what_changed_and_lists_only_the_lookback(
    wcli: _WellnessCli,
) -> None:
    ks = _long_history(wcli, with_activity=True)
    assert wcli.run().exit_code == 0
    first = set(wcli.archived())
    asked, probes = len(wcli.wgarmin.asked), wcli.wgarmin.probes

    wcli.wgarmin.days[_ago(2)]["daily"] = {"movement": {"steps": {"value": 9999}}}
    second = wcli.run()

    assert second.exit_code == 0, second.output
    assert wcli.wgarmin.asked[asked:] == ["daily", "sleep", "hrv", "weight"]
    assert wcli.wgarmin.probes == probes
    assert _delivered_days(wcli, first) == [_ago(2).isoformat()]
    expected = _steps(ks)
    expected[(_ago(2), "steps")] = 9999
    assert wcli.personal() == expected
    assert (
        _table(second.output, "Days unchanged")
        == _table(second.output, "Days listed") - 1
    )


@pytest.mark.usefixtures("utc")
def test_a_since_older_than_the_recorded_coverage_fills_the_gap_in_one_pull(
    wcli: _WellnessCli,
) -> None:
    ks = _long_history(wcli, with_activity=False)
    assert wcli.run().exit_code == 0
    recorded = {entry.day for entry in wcli.ledger_wellness().days}
    oldest = min(recorded)
    assert (_today() - oldest).days == 365
    assert wcli.personal() == _steps({d: k for d, k in ks.items() if d in recorded})
    first = set(wcli.archived())
    through = wcli.ledger_wellness().through

    since = _ago(1000)
    result = wcli.run("--since", since.isoformat())

    assert result.exit_code == 0, result.output
    gap = sorted(d.isoformat() for d in ks if since <= d < oldest)
    assert len(gap) > 600
    assert _delivered_days(wcli, first) == gap
    assert wcli.personal() == _steps({d: k for d, k in ks.items() if d >= since})
    assert wcli.ledger_wellness().through == through
    assert wcli.wgarmin.probes == 1


def test_a_failed_pull_then_a_plain_pull_restarts_the_listing_and_completes(
    wcli: _WellnessCli,
) -> None:
    ks = _long_history(wcli, with_activity=True)
    wcli.wgarmin.fail["weight"] = 500

    failed = wcli.run()

    assert failed.exit_code == 1, failed.output
    assert "HTTP 500" in failed.output
    assert "the next pull starts the wellness listing again" in failed.output
    assert wcli.archived() == {} and wcli.csv() == {}
    ledger = wcli.ledger().wellness
    assert ledger is None or (ledger.through is None and ledger.days == ())

    del wcli.wgarmin.fail["weight"]
    again = wcli.run()

    assert again.exit_code == 0, again.output
    assert wcli.personal() == _steps(ks)
    assert wcli.ledger_wellness().through is not None
    assert [e.day for e in wcli.ledger_wellness().days] == sorted(ks)
