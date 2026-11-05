"""The Garmin connector's activities through ``fitdocs pull`` (garmin-connector
task 5.1; Req 4.4, 4.5, 4.6, 8.2, 8.3).

Every test drives the real CLI (``fitdocs pull garmin ...``) in a temporary
data root: the real pull engine, ledger, inbox and drain, with the CLI's
transport seam patched to a scripted Garmin and the CLI's sleep patched to a
recorder so the one-second spacing costs no time. The scripted Garmin answers
only the routes the design names, checks the host and the credentials of every
request, honours ``start``, ``limit``, ``startDate`` and ``endDate``, and fails
on any other request. Wellness is off throughout (the instance's default).
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
import fitdocs.connectors.garmin as garmin_module
from fitdocs import layout
from fitdocs.cli import app
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.http import HttpRequest, HttpResponse
from fitdocs.connectors.ledger import Ledger, Outcome, load_ledger
from tests.fixtures import builder

runner = CliRunner()

INSTANCE = "garmin"
KEY = "gk-synthetic-4Vq8Zt"
TOKEN = (
    "eyJhbGci_OiJ0-ZXN0In0.eyJzdWIi_OiJzeW50-aGV0aWMtNzczMSJ9.c2ln_LXN5bnRo-ZXRpYy0xMg"
)
HOST = "personal.connectapi.garmin.com"
LOCAL_OFFSET = timedelta(hours=-5)
LISTING_ROUTE = "/activitylist-service/activities/search/activities"
FILE_ROUTE = "/download-service/files/activity/"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip(name: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, data)
    return buffer.getvalue()


@dataclass
class _Seen:
    """What one scripted Garmin saw: every request in order, by route."""

    requests: list[HttpRequest] = field(default_factory=list)
    tokens: int = 0
    listings: list[dict[str, str]] = field(default_factory=list)
    files: list[int] = field(default_factory=list)


class _Garmin:
    """A scripted Garmin: ``history`` maps an activity id to its UTC start and
    its FIT bytes. Local start is the UTC start shifted by ``LOCAL_OFFSET``."""

    def __init__(self, history: dict[int, tuple[datetime, bytes]]) -> None:
        self.history = history
        self.seen = _Seen()

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.seen.requests.append(request)
        parts = urlsplit(request.url)
        assert parts.scheme == "https", request.url
        assert parts.netloc == HOST, request.url
        authorization = request.secret_headers["Authorization"].reveal()
        if request.method == "POST":
            assert parts.path == garmin_module.TOKEN_PATH, request.url
            assert parts.query == ""
            assert authorization == f"ApiKey {KEY}"
            self.seen.tokens += 1
            return HttpResponse(200, {}, TOKEN.encode("ascii"))
        assert request.method == "GET", request.method
        assert authorization == f"Bearer {TOKEN}"
        if parts.path == LISTING_ROUTE:
            return self._listing(parse_qs(parts.query, strict_parsing=True))
        if parts.path.startswith(FILE_ROUTE):
            activity_id = int(parts.path[len(FILE_ROUTE) :])
            self.seen.files.append(activity_id)
            _, fit = self.history[activity_id]
            return HttpResponse(200, {}, _zip(f"{activity_id}_ACTIVITY.fit", fit))
        raise AssertionError(f"unscripted request {request.method} {request.url}")

    def _listing(self, query: dict[str, list[str]]) -> HttpResponse:
        single = {name: values[0] for name, values in query.items()}
        assert all(len(values) == 1 for values in query.values()), query
        self.seen.listings.append(single)
        assert single["sortOrder"] == "asc"
        first = date.fromisoformat(single["startDate"])
        last = date.fromisoformat(single["endDate"])
        offset = int(single["start"])
        limit = int(single["limit"])
        rows = sorted(
            (start, activity_id)
            for activity_id, (start, _) in self.history.items()
            if first <= (start + LOCAL_OFFSET).date() <= last
        )
        page = rows[offset : offset + limit]
        body = [
            {
                "activityId": activity_id,
                "startTimeGMT": start.strftime("%Y-%m-%d %H:%M:%S"),
                "startTimeLocal": (start + LOCAL_OFFSET).strftime("%Y-%m-%d %H:%M:%S"),
                "activityType": {"typeId": 1, "typeKey": "running"},
                "elapsedDuration": 1800.5,
            }
            for start, activity_id in page
        ]
        return HttpResponse(200, {}, json.dumps(body).encode("utf-8"))


@dataclass
class _Run:
    """One ``fitdocs pull`` invocation's result and what it asked Garmin."""

    exit_code: int
    output: str
    fetched: list[int]
    listings: list[dict[str, str]]


class _Cli:
    def __init__(self, root: Path, garmin: _Garmin, sleeps: list[float]) -> None:
        self.root = root
        self.garmin = garmin
        self.sleeps = sleeps

    def configure(self, lookback_days: int | None = None) -> None:
        lookback = "" if lookback_days is None else f"lookback_days = {lookback_days}\n"
        (self.root / "fitdocs.toml").write_text(
            f'[inbox]\npath = "inbox"\nsettle_seconds = 0\n\n'
            f"[connectors.{INSTANCE}]\n{lookback}",
            encoding="utf-8",
        )

    def pull(self, *args: str) -> _Run:
        files_before = len(self.garmin.seen.files)
        listings_before = len(self.garmin.seen.listings)
        result = runner.invoke(
            app,
            ["pull", INSTANCE, "--sync", "--no-prompt", "--out", str(self.root), *args],
        )
        return _Run(
            result.exit_code,
            result.output,
            self.garmin.seen.files[files_before:],
            self.garmin.seen.listings[listings_before:],
        )

    def pages(self) -> list[Path]:
        return sorted(
            page
            for page in (self.root / "workouts").glob("*.md")
            if page.name != "AGENTS.md"
        )

    def ledger(self) -> Ledger:
        return load_ledger(self.root, INSTANCE, connector_id=INSTANCE)


MakeCli = Callable[[dict[int, tuple[datetime, bytes]]], _Cli]


@pytest.fixture
def make_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[dict[int, tuple[datetime, bytes]]], _Cli]:
    return lambda history: _make(tmp_path, monkeypatch, history)


def _make(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history: dict[int, tuple[datetime, bytes]],
) -> _Cli:
    garmin = _Garmin(history)
    sleeps: list[float] = []
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: garmin)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    monkeypatch.setenv(env_var_name(INSTANCE, "api_key"), KEY)
    root = tmp_path / "data-root"
    root.mkdir()
    cli = _Cli(root, garmin, sleeps)
    cli.configure()
    return cli


@pytest.fixture
def utc(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """``--since`` is a local calendar day; pin the zone so the decoys below sit
    where the comments say, whatever the machine's zone is."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _run_fit(serial: int, day: int) -> bytes:
    return builder.small_sport_fit_bytes(
        serial, "running", timestamp_offset=day * 86400
    )


def _history(
    starts: dict[int, datetime],
) -> dict[int, tuple[datetime, bytes]]:
    return {
        activity_id: (start, _run_fit(9000 + index, index))
        for index, (activity_id, start) in enumerate(sorted(starts.items()))
    }


def _day(n: int, hour: int = 12) -> datetime:
    return datetime(2025, 1, 1, hour, tzinfo=UTC) + timedelta(days=n)


def _attribution_line(page: Path) -> str:
    lines = page.read_text(encoding="utf-8").splitlines()
    h1 = next(i for i, line in enumerate(lines) if line.startswith("# "))
    return next(line for line in lines[h1 + 1 :] if line.strip())


# --------------------------------------------------------------------------
# The first pull, the second pull, a byte-identical file (Req 8.2, 8.3)
# --------------------------------------------------------------------------


def test_pull_sync_writes_an_attributed_page_and_archives_the_bytes_unchanged(
    make_cli: MakeCli,
) -> None:
    ride = builder.garmin_devices_ride_fit_bytes()
    cli = make_cli({7001: (_day(0), ride)})

    first = cli.pull()

    assert first.exit_code == 0, first.output
    assert first.fetched == [7001]
    assert cli.garmin.seen.tokens == 1
    assert cli.sleeps == [garmin_module.REQUEST_SPACING_S] * (
        len(cli.garmin.seen.requests) - 1
    )
    archived = layout.archive_path(cli.root, _sha256(ride))
    assert archived.read_bytes() == ride
    pages = cli.pages()
    assert len(pages) == 1, pages
    assert _attribution_line(pages[0]) == "Data source: Garmin edge_1040"
    entry = cli.ledger().get("7001")
    assert entry is not None
    assert entry.outcome is Outcome.DELIVERED
    assert entry.sha256 == _sha256(ride)


def test_a_second_pull_lists_again_and_downloads_nothing(
    make_cli: MakeCli,
) -> None:
    ride = builder.garmin_devices_ride_fit_bytes()
    cli = make_cli({7001: (_day(0), ride)})
    first = cli.pull()
    assert first.exit_code == 0, first.output
    assert first.fetched == [7001]
    pages_before = [page.read_bytes() for page in cli.pages()]
    assert len(pages_before) == 1

    second = cli.pull()

    assert second.exit_code == 0, second.output
    assert len(second.listings) >= 1
    assert second.fetched == []
    assert [page.read_bytes() for page in cli.pages()] == pages_before
    entry = cli.ledger().get("7001")
    assert entry is not None
    assert entry.outcome is Outcome.DELIVERED


def test_a_file_already_in_the_archive_is_recorded_held_and_not_delivered(
    make_cli: MakeCli,
    tmp_path: Path,
) -> None:
    held = _run_fit(9101, 0)
    fresh = _run_fit(9102, 1)
    cli = make_cli({7101: (_day(0), held), 7102: (_day(1), fresh)})
    dropped = tmp_path / "hand-dropped"
    dropped.mkdir()
    (dropped / "run.fit").write_bytes(held)
    sync = runner.invoke(
        app, ["sync", str(dropped), "--no-prompt", "--out", str(cli.root)]
    )
    assert sync.exit_code == 0, sync.output
    assert layout.archive_path(cli.root, _sha256(held)).read_bytes() == held
    assert len(cli.pages()) == 1
    assert cli.ledger().entries == ()

    run = cli.pull()

    assert run.exit_code == 0, run.output
    assert run.fetched == [7101, 7102]
    ledger = cli.ledger()
    held_entry = ledger.get("7101")
    assert held_entry is not None
    assert held_entry.outcome is Outcome.ALREADY_HELD
    assert held_entry.sha256 == _sha256(held)
    assert held_entry.pending is None
    fresh_entry = ledger.get("7102")
    assert fresh_entry is not None
    assert fresh_entry.outcome is Outcome.DELIVERED
    # One page from the hand-drop, one from the fresh delivery: the held file
    # made no second page.
    assert len(cli.pages()) == 2
    assert not (cli.root / "inbox" / INSTANCE / "7101.fit").exists()


# --------------------------------------------------------------------------
# The per-pull limit (Req 4.4, 4.5)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lookback_days", [None, 0])
def test_a_first_pull_over_the_limit_succeeds_and_later_pulls_reach_the_end(
    make_cli: MakeCli,
    monkeypatch: pytest.MonkeyPatch,
    lookback_days: int | None,
) -> None:
    monkeypatch.setattr(garmin_module, "ACTIVITIES_PER_PULL", 3)
    # Starts one day apart; the ids are scrambled against the starts, so
    # the order fetched is the start order, not the id order.
    ids = [7305, 7301, 7308, 7303, 7307, 7302, 7306, 7304]
    cli = make_cli(
        _history({activity_id: _day(n) for n, activity_id in enumerate(ids)})
    )
    cli.configure(lookback_days)

    first = cli.pull()
    assert first.exit_code == 0, first.output
    assert first.fetched == ids[:3]
    assert "5 more activities left for a later pull" in first.output
    assert len(cli.pages()) == 3

    second = cli.pull()
    assert second.exit_code == 0, second.output
    assert second.fetched == ids[3:6]
    # The window opens at the watermark (the third start) less the look-back,
    # and the listing's own date filter starts a day earlier still.
    opened = _day(2) - timedelta(days=30 if lookback_days is None else lookback_days)
    assert (
        second.listings[0]["startDate"]
        == (opened - timedelta(days=1)).date().isoformat()
    )
    assert "2 more activities left for a later pull" in second.output
    assert len(cli.pages()) == 6

    third = cli.pull()
    assert third.exit_code == 0, third.output
    assert third.fetched == ids[6:]
    assert "more activit" not in third.output
    assert "left for a later pull" not in third.output
    assert len(cli.pages()) == 8

    fourth = cli.pull()
    assert fourth.exit_code == 0, fourth.output
    assert fourth.fetched == []
    assert len(cli.pages()) == 8
    ledger = cli.ledger()
    assert sorted(entry.remote_id for entry in ledger.entries) == sorted(
        str(activity_id) for activity_id in ids
    )
    assert all(entry.outcome is Outcome.DELIVERED for entry in ledger.entries)


# --------------------------------------------------------------------------
# --since (Req 4.6, and the deferral wording of Req 4.3)
# --------------------------------------------------------------------------

# History, 45 days apart so a plain pull's 30-day look-back never reaches the
# previous entry: A, B, C old; X one hour before the since day starts (it sits
# inside the listing's one-day slack, so the date filter lists it and the
# connector's own cut is what drops it); D, E, F the recent run.
_A, _B, _C, _X, _D, _E, _F = 7401, 7402, 7403, 7404, 7405, 7406, 7407


def _since_history() -> dict[int, tuple[datetime, bytes]]:
    return _history(
        {
            _A: _day(0),
            _B: _day(45),
            _C: _day(90),
            _X: _day(134, hour=23),
            _D: _day(135),
            _E: _day(180),
            _F: _day(225),
        }
    )


_SINCE_D = _day(135).date().isoformat()
_SINCE_A = _day(0).date().isoformat()


@pytest.mark.usefixtures("utc")
def test_a_first_pull_with_since_lists_only_from_that_date(
    make_cli: MakeCli,
) -> None:
    cli = make_cli(_since_history())

    first = cli.pull("--since", _SINCE_D)

    assert first.exit_code == 0, first.output
    assert first.fetched == [_D, _E, _F]
    assert all(
        date.fromisoformat(listing["startDate"]) >= _day(134).date()
        for listing in first.listings
    )
    assert len(cli.pages()) == 3
    ledger = cli.ledger()
    assert sorted(entry.remote_id for entry in ledger.entries) == [
        str(_D),
        str(_E),
        str(_F),
    ]

    # The watermark is F, and its 30-day look-back holds nothing unrecorded.
    later = cli.pull()
    assert later.exit_code == 0, later.output
    assert later.fetched == []
    assert len(cli.pages()) == 3


@pytest.mark.usefixtures("utc")
def test_a_since_backfill_behind_the_watermark_continues_only_with_the_same_since(
    make_cli: MakeCli,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(garmin_module, "ACTIVITIES_PER_PULL", 2)
    cli = make_cli(_since_history())

    # The watermark: D and E delivered, F left over, X and the old ones unseen.
    first = cli.pull("--since", _SINCE_D)
    assert first.exit_code == 0, first.output
    assert first.fetched == [_D, _E]
    assert "1 more activity left for a later pull" in first.output
    assert "continues only with the same `--since`" in first.output
    watermark = cli.ledger().watermark
    assert watermark == _day(180)

    # Behind it: only --since A reaches the old history, two per pull.
    behind = cli.pull("--since", _SINCE_A)
    assert behind.exit_code == 0, behind.output
    assert behind.fetched == [_A, _B]
    assert "3 more activities left for a later pull" in behind.output
    assert cli.ledger().watermark == watermark

    # A plain pull opens at the watermark less its 30-day look-back: it takes F
    # and nothing older.
    plain = cli.pull()
    assert plain.exit_code == 0, plain.output
    assert plain.fetched == [_F]
    assert "left for a later pull" not in plain.output

    still_behind = cli.pull()
    assert still_behind.exit_code == 0, still_behind.output
    assert still_behind.fetched == []

    # The same --since carries on to the old entries the plain pull skipped.
    same = cli.pull("--since", _SINCE_A)
    assert same.exit_code == 0, same.output
    assert same.fetched == [_C, _X]
    assert "left for a later pull" not in same.output
    assert len(cli.pages()) == 7

    done = cli.pull("--since", _SINCE_A)
    assert done.exit_code == 0, done.output
    assert done.fetched == []
    assert len(cli.pages()) == 7
