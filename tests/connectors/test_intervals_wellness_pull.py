from __future__ import annotations

import base64
import hashlib
import json
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest

from fitdocs import layout
from fitdocs.connectors import get, intervals
from fitdocs.connectors.credentials import ResolvedCredentials, env_var_name
from fitdocs.connectors.http import CallMode, HttpClient, HttpResponse
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    WellnessDay,
    WellnessPuller,
)
from fitdocs.connectors.pull import (
    PullNote,
    PullOptions,
    PullReport,
    WellnessPullReport,
    run_pull,
)
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import FakeTransport
from tests.fixtures import builder

_KEY = "ik-synthetic-7Q2x9"
_TOKEN = base64.b64encode(f"API_KEY:{_KEY}".encode()).decode()
_BASIC = f"Basic {_TOKEN}"
_NOW = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(
    seconds=builder.FIT_TIMESTAMP_BASE
)
_NOW = _NOW.astimezone(timezone(timedelta(hours=-7)))
_ATHLETE = {"garmin_wellness_keys": ["weight"], "oura_wellness_keys": ["hrv"]}
_RECORDS = [
    {"id": "2020-12-29", "updated": "revision-z", "weight": 73, "ctl": None},
    {
        "id": "2021-09-06",
        "updated": "revision-a",
        "weight": 61,
        "hrv": 47,
        "atl": {"opaque": [False, 0.0, "ñ"]},
    },
    {"id": "2021-09-08", "updated": "revision-m", "weight": 89, "steps": 321},
]
_WINDOWS = [
    ("2009-12-31", "2011-01-01"),
    ("2010-12-31", "2012-01-01"),
    ("2011-12-31", "2012-12-31"),
    ("2012-12-30", "2013-12-31"),
    ("2013-12-30", "2014-12-31"),
    ("2014-12-30", "2015-12-31"),
    ("2015-12-30", "2016-12-30"),
    ("2016-12-29", "2017-12-30"),
    ("2017-12-29", "2018-12-30"),
    ("2018-12-29", "2019-12-30"),
    ("2019-12-29", "2020-12-29"),
    ("2020-12-28", "2021-09-09"),
]
_FIRST_PATHS = [
    "lab/wellness-2020-12-29_2020-12-29.json",
    "lab/wellness-2021-09-06_2021-09-08.json",
]
_REVISED_PATH = "lab/wellness-2021-09-06_2021-09-06.json"
_FIT = bytes([12, 0x10, 0, 0, 0, 0, 0, 0]) + b".FIT" + b"synthetic-original"


def _transport(responses: Sequence[HttpResponse]) -> FakeTransport:
    return FakeTransport(list(responses))


def _ok(value: object) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps(value, ensure_ascii=False).encode())


def _envelope(records: list[dict[str, object]]) -> bytes:
    return (
        json.dumps(
            {
                "format": "fitdocs.intervals-icu-wellness",
                "version": 1,
                "origins": {"weight": "garmin", "hrv": "oura"},
                "records": records,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        + b"\n"
    )


def _run(root: Path, transport: FakeTransport, *, later: bool = False) -> PullReport:
    return run_pull(
        root,
        [
            ConnectorInstance(
                name="lab",
                connector=get("intervals"),
                lookback_days=11,
                settings=intervals.IntervalsSettings(sources=intervals.DEFAULT_SOURCES),
                wellness=True,
            )
        ],
        inbox=root / "inbox",
        store=None,
        transport=transport,
        options=PullOptions(since=None, dry_run=False),
        environ={env_var_name("lab", "api_key"): _KEY},
        now=lambda: _NOW + timedelta(days=int(later)),
        sleep=lambda _: None,
        redactor=Redactor(),
    )


def _files(root: Path) -> dict[str, bytes]:
    inbox = root / "inbox"
    return {
        path.relative_to(inbox).as_posix(): path.read_bytes()
        for path in sorted(inbox.rglob("*"))
        if path.is_file()
    }


def _state(root: Path) -> dict[str, Any]:
    path = layout.connector_ledger_path(root, "lab")
    return tomllib.loads(path.read_text()) if path.is_file() else {}


def _requests(transport: FakeTransport) -> list[tuple[str, str, dict[str, list[str]]]]:
    return [
        (r.method, urlsplit(r.url).path, parse_qs(urlsplit(r.url).query))
        for r in transport.requests
        if not urlsplit(r.url).path.endswith("/activities")
    ]


def _wellness_requests(
    windows: list[tuple[str, str]], packages: int
) -> list[tuple[str, str, dict[str, list[str]]]]:
    return [
        ("GET", "/api/v1/athlete/0/wellness", {"oldest": [a], "newest": [b]})
        for a, b in windows
    ] + [("GET", "/api/v1/athlete/0", {})] * packages


def _expected_state(
    records: list[dict[str, object]], files: dict[str, bytes], *, through: date
) -> dict[str, Any]:
    return {
        "through": through,
        "origins": ["garmin", "oura"],
        "days": [
            {
                "day": date.fromisoformat(str(record["id"])),
                "revision": record["updated"],
                "sha256": hashlib.sha256(
                    _envelope(
                        [
                            other
                            for other in records
                            if str(other["id"])[:4] == str(record["id"])[:4]
                        ]
                    )
                ).hexdigest(),
            }
            for record in records
        ],
        "pending": [
            {
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "format": "intervals-icu",
                "suffix": ".json",
            }
            for path, data in sorted(files.items())
        ],
    }


@dataclass
class _History:
    observed: dict[tuple[str, str], object]
    expected: dict[tuple[str, str], object]


@pytest.fixture
def _history(tmp_path: Path) -> _History:
    root = tmp_path / "root"
    before = (_files(root), _state(root))
    first_transport = _transport(
        [_ok([])]
        + [_ok([])] * 10
        + [_ok([_RECORDS[0]]), _ok(list(reversed(_RECORDS)))]
        + [_ok(_ATHLETE)] * 8
    )
    first = _run(root, first_transport)
    first_w = cast(WellnessPullReport, first.instances[0].wellness)
    first_files = _files(root)
    first_state = _state(root)
    first_ledger = layout.connector_ledger_path(root, "lab").read_bytes()
    first_expected = dict(
        zip(
            _FIRST_PATHS,
            [_envelope(_RECORDS[:1]), _envelope(_RECORDS[1:])],
            strict=True,
        )
    )
    expected_state = _expected_state(_RECORDS, first_expected, through=date(2021, 9, 9))
    equivalent: dict[str, bytes] = {}
    connector = cast(WellnessPuller, get("intervals"))
    package_transport = _transport([_ok(_ATHLETE)] * 8)
    session = ConnectorSession(
        instance="lab",
        settings=intervals.IntervalsSettings(sources=intervals.DEFAULT_SOURCES),
        http=HttpClient(
            package_transport,
            mode=CallMode.DATA,
            redactor=Redactor(),
            sleep=lambda _: None,
        ),
        credentials=ResolvedCredentials(
            connector_id="intervals",
            auth_style=AuthStyle.API_KEY,
            values={"api_key": Secret(_KEY)},
            expires_at=None,
            scopes=None,
            store=None,
            instance_name="lab",
        ),
        data_root=root,
        now=lambda: _NOW,
        sleep=lambda _: None,
        redactor=Redactor(),
    )
    for path, records in zip(_FIRST_PATHS, [_RECORDS[:1], _RECORDS[1:]], strict=True):
        days = tuple(
            WellnessDay(date.fromisoformat(str(r["id"])), str(r["updated"]), r)
            for r in records
        )
        equivalent[path] = connector.package_wellness(session, days).data
    archive_before = sorted((root / "wellness-archive").rglob("*.json"))
    for data in first_files.values():
        sha = hashlib.sha256(data).hexdigest()
        archive = layout.wellness_archive_path(root, "intervals-icu", sha, ".json")
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
    archive_files = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted((root / "wellness-archive").rglob("*.json"))
    }
    second_transport = _transport([_ok([]), _ok(_RECORDS[1:])] + [_ok(_ATHLETE)] * 8)
    second = _run(root, second_transport)
    second_w = cast(WellnessPullReport, second.instances[0].wellness)
    second_files = _files(root)
    second_state = _state(root)
    second_ledger = layout.connector_ledger_path(root, "lab").read_bytes()
    revised = dict(_RECORDS[1], updated="revision-corrected")
    third_transport = _transport(
        [_ok([]), _ok([_RECORDS[2], revised])] + [_ok(_ATHLETE)] * 8
    )
    third = _run(root, third_transport, later=True)
    third_w = cast(WellnessPullReport, third.instances[0].wellness)
    third_files = _files(root)
    third_state = _state(root)
    third_ledger = layout.connector_ledger_path(root, "lab").read_bytes()
    third_expected = {_REVISED_PATH: _envelope([revised])}
    revised_state = _expected_state(
        [revised], third_expected, through=date(2021, 9, 10)
    )
    revised_state["days"] = [
        expected_state["days"][0],
        revised_state["days"][0],
        expected_state["days"][2],
    ]
    observed: dict[tuple[str, str], object] = {
        ("first", "requests"): _requests(first_transport),
        ("first", "headers"): [
            (
                r.secret_headers.get("Authorization", Secret("")).reveal(),
                "Authorization" in r.headers,
            )
            for r in first_transport.requests
        ],
        ("first", "files"): (
            before,
            first_files,
            [(d.span, d.days, d.path) for d in first_w.delivered],
        ),
        ("first", "package-equivalence"): first_files,
        ("first", "state"): first_state.get("wellness"),
        ("second", "requests"): _requests(second_transport),
        ("second", "removed"): (tuple(first_files), second.instances[0].removed),
        ("second", "files"): (
            second_files,
            second_w.delivered,
            second_w.unchanged,
            archive_before,
            archive_files,
        ),
        ("second", "state"): second_state.get("wellness"),
        ("revised", "requests"): _requests(third_transport),
        ("revised", "files"): (
            third_files,
            [(d.span, d.days, d.path) for d in third_w.delivered],
            third_w.unchanged,
        ),
        ("revised", "state"): third_state.get("wellness"),
        ("all", "privacy"): [
            (secret, location)
            for secret in (_KEY.encode(), _TOKEN.encode(), _BASIC.encode())
            for location, payload in [
                ("reports", repr((first, second, third)).encode()),
                ("first-ledger", first_ledger),
                ("second-ledger", second_ledger),
                ("third-ledger", third_ledger),
                *first_files.items(),
                *third_files.items(),
                *[
                    ("url", r.url.encode())
                    for transport in (
                        first_transport,
                        second_transport,
                        third_transport,
                    )
                    for r in transport.requests
                ],
            ]
            if secret in payload
        ],
    }
    expected: dict[tuple[str, str], object] = {
        ("first", "requests"): _wellness_requests(_WINDOWS, 2),
        ("first", "headers"): [(_BASIC, False)] * 15,
        ("first", "files"): (
            ({}, {}),
            first_expected,
            [
                ("2020-12-29..2020-12-29", 1, _FIRST_PATHS[0]),
                ("2021-09-06..2021-09-08", 2, _FIRST_PATHS[1]),
            ],
        ),
        ("first", "package-equivalence"): equivalent,
        ("first", "state"): expected_state,
        ("second", "requests"): _wellness_requests([("2021-08-28", "2021-09-09")], 0),
        ("second", "removed"): (tuple(_FIRST_PATHS), tuple(_FIRST_PATHS)),
        ("second", "files"): (
            {},
            (),
            2,
            [],
            {
                "wellness-archive/intervals-icu/"
                + hashlib.sha256(data).hexdigest()
                + ".json": data
                for data in first_expected.values()
            },
        ),
        ("second", "state"): dict(expected_state, pending=[]),
        ("revised", "requests"): _wellness_requests([("2021-08-28", "2021-09-10")], 1),
        ("revised", "files"): (
            third_expected,
            [("2021-09-06..2021-09-06", 1, _REVISED_PATH)],
            1,
        ),
        ("revised", "state"): revised_state,
        ("all", "privacy"): [],
    }
    return _History(observed, expected)


@pytest.mark.parametrize(
    "phase,facet",
    [
        ("first", "requests"),
        ("first", "headers"),
        ("first", "files"),
        ("first", "package-equivalence"),
        ("first", "state"),
        ("second", "requests"),
        ("second", "removed"),
        ("second", "files"),
        ("second", "state"),
        ("revised", "requests"),
        ("revised", "files"),
        ("revised", "state"),
        ("all", "privacy"),
    ],
)
def test_registered_intervals_wellness_lifecycle(
    _history: _History, phase: str, facet: str
) -> None:
    assert _history.observed[phase, facet] == _history.expected[phase, facet]


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("facet", ["error", "activity", "requests", "privacy"])
def test_wellness_listing_refusal_keeps_delivered_activity(
    tmp_path: Path, status: int, facet: str
) -> None:
    root = tmp_path / "root"
    before = (_files(root), _state(root))
    message = f"service says {_KEY} / {_TOKEN} / {_BASIC} tail"
    transport = _transport(
        [
            _ok(
                [
                    {
                        "id": "synthetic-original",
                        "source": "GARMIN_CONNECT",
                        "start_date": "2021-09-07T04:05:06Z",
                        "file_type": "fit",
                    }
                ]
            ),
            HttpResponse(200, {}, _FIT),
            HttpResponse(status, {}, message.encode()),
        ]
        + [_ok([])] * 16
    )
    report = _run(root, transport)
    instance = report.instances[0]
    wellness = cast(WellnessPullReport, instance.wellness)
    redacted = "service says <redacted> / <redacted> / <redacted> tail"
    detail = (
        "AuthFailure: "
        + redacted
        + " Check the credentials and run `fitdocs connect lab` again."
        if status == 401
        else "ConnectorError: intervals.icu refused the wellness listing (HTTP 403): "
        + redacted
        + ". intervals.icu may be withholding data it received from Garmin. "
        "Set wellness = false in this instance's table to stop requesting wellness; "
        "Garmin's own data export is the route for Garmin wellness "
        "(see the wellness guide)."
    )
    state = _state(root)
    files = _files(root)
    ledger_bytes = layout.connector_ledger_path(root, "lab").read_bytes()
    observed = {
        "error": (
            report.failed,
            instance.error,
            wellness.error,
            wellness.delivered,
            wellness.failed,
        ),
        "activity": (
            before,
            [(d.remote_id, d.path) for d in instance.delivered],
            files,
            state.get("entries"),
            state.get("wellness"),
        ),
        "requests": [(r.method, urlsplit(r.url).path) for r in transport.requests],
        "privacy": [
            (secret, location)
            for secret in (_KEY.encode(), _TOKEN.encode(), _BASIC.encode())
            for location, payload in [
                ("report", repr(report).encode()),
                ("ledger", ledger_bytes),
                *files.items(),
                *[("url", r.url.encode()) for r in transport.requests],
            ]
            if secret in payload
        ],
    }
    expected = {
        "error": (True, None, PullNote("lab", detail), (), ()),
        "activity": (
            ({}, {}),
            [("synthetic-original", "lab/synthetic-original.fit")],
            {"lab/synthetic-original.fit": _FIT},
            [
                {
                    "remote_id": "synthetic-original",
                    "outcome": "delivered",
                    "sha256": hashlib.sha256(_FIT).hexdigest(),
                    "pending": "lab/synthetic-original.fit",
                }
            ],
            None,
        ),
        "requests": [
            ("GET", "/api/v1/athlete/0/activities"),
            ("GET", "/api/v1/activity/synthetic-original/file"),
            ("GET", "/api/v1/athlete/0/wellness"),
        ],
        "privacy": [],
    }
    assert observed[facet] == expected[facet]
