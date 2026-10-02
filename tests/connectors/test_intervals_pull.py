"""The intervals.icu connector through the pull engine and the CLI
(intervals-connector task 4.1; Req 3.4, 4.6, 4.7, 5.6, 5.8, 6.1, 6.2, 6.3,
8.1, 8.5, 8.6).

Engine level: the registered connector, a scripted service behind the engine's
transport argument and a synthetic data root. CLI level: ``fitdocs pull
intervals --sync --no-prompt`` with the CLI's transport seam patched to the
same scripted service. Every request reaches only the scripted service; the
package conftest's socket guard is active throughout.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs import layout
from fitdocs.cli import app
from fitdocs.connectors import SettingsContext, get
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.http import HttpRequest, HttpResponse
from fitdocs.connectors.ledger import Outcome, load_ledger
from fitdocs.connectors.pull import (
    Delivered,
    PullNote,
    PullOptions,
    PullReport,
    run_pull,
)
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import load_connectors_settings
from fitdocs.contract import DOC_BANNER
from fitdocs.version import user_agent
from tests.fixtures import builder

runner = CliRunner()

KEY = "ik-synthetic-7Q2x9"
INSTANCE = "intervals"
BASE = "https://intervals.icu/api/v1"

RIDE_ID = "i9000001"
GPX_ID = "i9000002"
NOT_FIT_ID = "i9000003"
UPLOAD_ID = "i9000004"
HELD_ID = "i9000005"

GPX_REASON = "the original is a GPX file, not FIT; fitdocs ingests FIT files only"
NOT_FIT_BODY = b"synthetic body that is neither FIT nor GPX nor TCX"

_FIRST_NOW = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(
    seconds=builder.FIT_TIMESTAMP_BASE + 3 * 3600
)
_SECOND_NOW = _FIRST_NOW + timedelta(hours=2)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _listing(first_start: datetime) -> list[dict[str, object]]:
    """The four-entry listing: a Garmin Connect FIT ride, a Garmin Connect
    GPX-typed entry, a Garmin Connect entry whose body is not an activity
    file, and an upload."""

    def entry(
        remote_id: str, source: str, minutes: int, file_type: str
    ) -> dict[str, object]:
        start = first_start + timedelta(minutes=minutes)
        return {
            "id": remote_id,
            "source": source,
            "start_date": start.isoformat(),
            "type": "Ride",
            "elapsed_time": 3600,
            "file_type": file_type,
        }

    return [
        entry(RIDE_ID, "GARMIN_CONNECT", 0, "fit"),
        entry(GPX_ID, "GARMIN_CONNECT", 10, "gpx"),
        entry(NOT_FIT_ID, "GARMIN_CONNECT", 20, "fit"),
        entry(UPLOAD_ID, "UPLOAD", 30, "fit"),
    ]


class _Service:
    """A scripted intervals.icu: one listing body for every listing request,
    one file body per activity id; any other request fails the test."""

    def __init__(
        self, listing: list[dict[str, object]], files: dict[str, bytes]
    ) -> None:
        self._listing = listing
        self._files = files
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        path = urlsplit(request.url).path
        if path == "/api/v1/athlete/0/activities":
            return HttpResponse(200, {}, json.dumps(self._listing).encode("utf-8"))
        parts = path.split("/")
        if parts[:4] == ["", "api", "v1", "activity"] and parts[5:] == ["file"]:
            return HttpResponse(200, {}, self._files[parts[4]])
        raise AssertionError(f"unscripted request {request.url}")

    @property
    def urls(self) -> list[str]:
        return [request.url for request in self.requests]


def _files(ride_body: bytes) -> dict[str, bytes]:
    return {
        RIDE_ID: ride_body,
        NOT_FIT_ID: NOT_FIT_BODY,
        # The upload is served so that fetching it would deliver a file.
        UPLOAD_ID: gzip.compress(builder.strength_fit_bytes()),
    }


def _pull(
    root: Path, service: _Service, now: datetime, *, dry_run: bool = False
) -> PullReport:
    instances = load_connectors_settings(
        {"connectors": {INSTANCE: {}}},
        settings_file=root / "fitdocs.toml",
        context=SettingsContext(data_root=root, inbox=root / "inbox"),
    )
    assert [instance.connector for instance in instances] == [get(INSTANCE)]
    return run_pull(
        root,
        instances,
        inbox=root / "inbox",
        store=None,
        transport=service,
        options=PullOptions(since=None, dry_run=dry_run),
        environ={env_var_name(INSTANCE, "api_key"): KEY},
        now=lambda: now,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )


def _ledger_bytes(root: Path) -> bytes:
    return layout.connector_ledger_path(root, INSTANCE).read_bytes()


def test_first_pull_delivers_the_ride_and_records_each_other_entry(
    tmp_path: Path,
) -> None:
    ride = builder.garmin_devices_ride_fit_bytes()
    service = _Service(_listing(_FIRST_NOW), _files(gzip.compress(ride)))

    report = _pull(tmp_path, service, _FIRST_NOW).instances[0]

    assert report.error is None
    assert report.listed == 3  # the upload is filtered before the engine
    assert report.delivered == (Delivered(RIDE_ID, f"{INSTANCE}/{RIDE_ID}.fit"),)
    assert report.skipped == (
        PullNote(GPX_ID, GPX_REASON),
        PullNote(NOT_FIT_ID, "not a FIT file"),
    )
    assert report.failed == ()
    assert report.held == ()
    delivered_file = tmp_path / "inbox" / INSTANCE / f"{RIDE_ID}.fit"
    assert delivered_file.read_bytes() == ride
    assert sorted(p.name for p in (tmp_path / "inbox" / INSTANCE).iterdir()) == [
        f"{RIDE_ID}.fit"
    ]

    ledger = load_ledger(tmp_path, INSTANCE, connector_id=INSTANCE)
    assert [entry.remote_id for entry in ledger.entries] == [
        RIDE_ID,
        GPX_ID,
        NOT_FIT_ID,
    ]
    ride_entry = ledger.get(RIDE_ID)
    assert ride_entry is not None
    assert ride_entry.outcome is Outcome.DELIVERED
    assert ride_entry.sha256 == _sha256(ride)
    assert ride_entry.pending == f"{INSTANCE}/{RIDE_ID}.fit"
    gpx_entry = ledger.get(GPX_ID)
    assert gpx_entry is not None
    assert gpx_entry.outcome is Outcome.SKIPPED
    assert gpx_entry.sha256 is None
    assert gpx_entry.detail == GPX_REASON
    not_fit_entry = ledger.get(NOT_FIT_ID)
    assert not_fit_entry is not None
    assert not_fit_entry.outcome is Outcome.SKIPPED
    assert not_fit_entry.sha256 == _sha256(NOT_FIT_BODY)
    assert not_fit_entry.detail == "not a FIT file"
    assert ledger.get(UPLOAD_ID) is None
    assert all(entry.revision is None for entry in ledger.entries)

    assert service.urls == [
        service.urls[0],
        f"{BASE}/activity/{RIDE_ID}/file",
        f"{BASE}/activity/{NOT_FIT_ID}/file",
    ]
    assert urlsplit(service.urls[0]).path == "/api/v1/athlete/0/activities"
    for request in service.requests:
        assert request.headers["User-Agent"] == user_agent()
        assert not any("Python-urllib" in v for v in request.headers.values())


def test_second_pull_makes_listing_requests_only_and_keeps_the_ledger(
    tmp_path: Path,
) -> None:
    ride = builder.garmin_devices_ride_fit_bytes()
    first_service = _Service(_listing(_FIRST_NOW), _files(gzip.compress(ride)))
    _pull(tmp_path, first_service, _FIRST_NOW)
    first_ledger = _ledger_bytes(tmp_path)
    # The comparison below needs a ledger that records something.
    assert first_ledger.count(b"[[") >= 3, first_ledger
    assert (tmp_path / "inbox" / INSTANCE / f"{RIDE_ID}.fit").is_file()

    second_service = _Service(_listing(_FIRST_NOW), _files(gzip.compress(ride)))
    report = _pull(tmp_path, second_service, _SECOND_NOW).instances[0]

    assert report.error is None
    # Every kept entry was listed again and found final; none was fetched.
    assert report.listed == 3
    assert report.held == (RIDE_ID, GPX_ID, NOT_FIT_ID)
    assert report.delivered == ()
    assert len(second_service.requests) >= 1
    assert all(
        urlsplit(url).path == "/api/v1/athlete/0/activities"
        for url in second_service.urls
    )
    assert _ledger_bytes(tmp_path) == first_ledger


def test_bytes_already_in_the_archive_are_recorded_held_and_not_delivered(
    tmp_path: Path,
) -> None:
    held_bytes = builder.ride_no_power_fit_bytes()
    held_sha = _sha256(held_bytes)
    archived = layout.archive_path(tmp_path, held_sha)
    archived.parent.mkdir(parents=True)
    archived.write_bytes(held_bytes)
    # Precondition: no pending delivery carries these bytes, so the engine's
    # pending-delivery branch cannot be what answers.
    before = load_ledger(tmp_path, INSTANCE, connector_id=INSTANCE)
    assert [e.sha256 for e in before.pending_entries()] == []
    assert not (tmp_path / "inbox").exists()

    entry = {
        "id": HELD_ID,
        "source": "GARMIN_CONNECT",
        "start_date": (_FIRST_NOW + timedelta(minutes=40)).isoformat(),
        "type": "Ride",
        "elapsed_time": 3600,
        "file_type": "fit",
    }
    service = _Service([entry], {HELD_ID: gzip.compress(held_bytes)})

    report = _pull(tmp_path, service, _FIRST_NOW).instances[0]

    assert report.error is None
    assert report.held == (HELD_ID,)
    assert report.delivered == ()
    assert service.urls[-1] == f"{BASE}/activity/{HELD_ID}/file"
    ledger = load_ledger(tmp_path, INSTANCE, connector_id=INSTANCE)
    held_entry = ledger.get(HELD_ID)
    assert held_entry is not None
    assert held_entry.outcome is Outcome.ALREADY_HELD
    assert held_entry.sha256 == held_sha
    assert held_entry.pending is None
    assert not (tmp_path / "inbox" / INSTANCE).exists() or not list(
        (tmp_path / "inbox" / INSTANCE).iterdir()
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _workout_pages(root: Path) -> list[Path]:
    return sorted(p for p in (root / "workouts").glob("*.md") if p.name != "AGENTS.md")


def _below_banner(page: Path) -> str:
    text = page.read_text(encoding="utf-8")
    assert text.count(DOC_BANNER) == 1
    return text.split(DOC_BANNER, 1)[1]


@pytest.mark.parametrize("encoding", ["gzip", "raw"])
def test_cli_pull_sync_writes_an_attributed_page_equal_to_a_hand_drop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, encoding: str
) -> None:
    ride = builder.garmin_devices_ride_fit_bytes()
    body = gzip.compress(ride) if encoding == "gzip" else ride
    # The CLI reads the real clock and the connector drops entries older than
    # its first-pull window, so the listing is dated against the real clock.
    start = datetime.now(UTC) - timedelta(hours=6)
    service = _Service(_listing(start), _files(body))
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: service)
    monkeypatch.setenv(env_var_name(INSTANCE, "api_key"), KEY)
    root = tmp_path / "pulled"
    root.mkdir()
    (root / "fitdocs.toml").write_text(
        f'[inbox]\npath = "inbox"\nsettle_seconds = 0\n\n[connectors.{INSTANCE}]\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["pull", INSTANCE, "--sync", "--no-prompt", "--out", str(root)]
    )

    assert result.exit_code == 0, result.output
    pages = _workout_pages(root)
    assert len(pages) == 1, pages
    lines = pages[0].read_text(encoding="utf-8").splitlines()
    h1 = next(i for i, line in enumerate(lines) if line.startswith("# "))
    after_h1 = [line for line in lines[h1 + 1 :] if line.strip()]
    assert after_h1[0] == "Data source: Garmin edge_1040"
    devices = pages[0].read_text(encoding="utf-8").split("## Device & Data Quality")[1]
    rows = [line for line in devices.splitlines() if line.startswith("| ")]
    assert any(row.startswith("| edge_1040 ") for row in rows)
    assert any(row.startswith("| hrm_pro ") for row in rows)

    dropped = tmp_path / "hand-dropped"
    dropped.mkdir()
    (dropped / "ride.fit").write_bytes(ride)
    second_root = tmp_path / "hand-root"
    second_root.mkdir()
    sync = runner.invoke(
        app, ["sync", str(dropped), "--no-prompt", "--out", str(second_root)]
    )
    assert sync.exit_code == 0, sync.output
    hand_pages = _workout_pages(second_root)
    assert len(hand_pages) == 1, hand_pages
    pulled_body = _below_banner(pages[0])
    assert "## Device & Data Quality" in pulled_body
    assert len(pulled_body) > 1000
    assert pulled_body == _below_banner(hand_pages[0])
