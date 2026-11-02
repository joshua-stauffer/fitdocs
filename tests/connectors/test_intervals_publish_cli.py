"""``fitdocs publish --yes`` to an intervals.icu instance, end to end
(intervals-publish task 3.3; Req 1.3, 2.3, 5.3, 6.5, 9.1, 9.6).

Every scenario runs the installed CLI over a synced temporary data root with an
``[connectors.icu-main]`` table, the key in the instance's override variable
and ``cli._connector_transport`` patched to a scripted transport; the
connectors conftest's socket guard stays on. The transport records every
request before it answers or raises, and each test asserts the request count
itself rather than trusting a raise to surface (an engine may report a raise
as a target error).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from typer.testing import CliRunner, Result

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors.http import HttpRequest, HttpResponse
from fitdocs.connectors.ledger import Ledger, LedgerEntry, Outcome, save_ledger
from fitdocs.docio import read_document
from fitdocs.docmerge import extract_regions
from fitdocs.publish.ledger import load_ledgers
from fitdocs.publish.pages import completed_activity
from fitdocs.publish.request import CompletedActivity
from tests.connectors.conftest import FakeTransport
from tests.fixtures import builder
from tests.support import tiles as tile_factory

runner = CliRunner()


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fitdocs.tiles._default_fetch", tile_factory.fetch_stub())


def _add_frontmatter_key(text: str, line: str) -> str:
    """Insert ``line`` just before the closing frontmatter fence."""
    first = text.index("---\n")
    second = text.index("---\n", first + len("---\n"))
    return text[:second] + line + text[second:]


# Spelled out, not imported: a constant imported from the connector would move
# with it.
LINK_BASE = "https://intervals.icu/activities/"
LINK_LABEL = "intervals.icu"
INSTANCE = "icu-main"
KEY_VARIABLE = "FITDOCS_CONNECTOR_ICU_MAIN_API_KEY"
API_KEY = "cli-key-8c1f"
LISTED = "i4100001"
PULLED = "i4100002"
UPLOADED = "i4100003"
UPDATE_BODY = b'{"id":"i4100001","name":"updated"}'


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "data"
        self.root.mkdir()
        self.source = tmp_path / "src"
        self.transport = FakeTransport([])

    def script(self, *outcomes: HttpResponse) -> FakeTransport:
        """Replace the scripted transport; its requests are counted afresh."""
        self.transport = FakeTransport(list(outcomes))
        return self.transport

    def settings(self, upload: str | None) -> None:
        line = "" if upload is None else f"publish_upload = {upload}\n"
        (self.root / "fitdocs.toml").write_text(
            f'[connectors.{INSTANCE}]\nconnector = "intervals"\n{line}',
            encoding="utf-8",
        )

    def publish(self, *args: str) -> Result:
        return runner.invoke(
            app,
            ["publish", "--yes", "--format", "json", *args, "--out", str(self.root)],
        )

    @property
    def page(self) -> Path:
        (found,) = sorted((self.root / "workouts").glob("*-run-*.md"))
        return found

    @property
    def publish_ledger(self) -> Path:
        return self.root / ".fitdocs" / "publish" / f"{INSTANCE}.toml"

    @property
    def pull_ledger(self) -> Path:
        return self.root / ".fitdocs" / "connectors" / f"{INSTANCE}.toml"

    def subject(self) -> CompletedActivity:
        document = read_document(self.page)
        assert document is not None and document.frontmatter is not None
        activity = completed_activity(document.frontmatter, self.root)
        assert activity is not None
        return activity

    def pull_record(self, remote_id: str) -> None:
        """A pull record, written with the connectors ledger writer, naming
        ``remote_id`` for the page's base file."""
        subject = self.subject()
        save_ledger(
            self.root,
            INSTANCE,
            Ledger(
                connector_id="intervals",
                watermark=None,
                entries=(
                    LedgerEntry(
                        remote_id=remote_id,
                        outcome=Outcome.DELIVERED,
                        sha256=subject.source_shas[-1],
                        detail=None,
                    ),
                ),
            ),
        )

    def listing_entry(self, remote_id: str) -> dict[str, object]:
        """A listing entry strictly matching the page: same instant, same
        distance. The page's own start is not UTC, so the entry's
        ``start_date`` (an instant) and ``start_date_local`` (a wall clock)
        differ."""
        subject = self.subject()
        instant = subject.start.astimezone(UTC)
        return {
            "id": remote_id,
            "source": "GARMIN_CONNECT",
            "start_date": instant.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "start_date_local": subject.start.strftime("%Y-%m-%dT%H:%M:%S"),
            "distance": subject.distance_m,
            "elapsed_time": subject.elapsed_s,
            "external_id": None,
        }


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(KEY_VARIABLE, API_KEY)
    held = Rig(tmp_path)
    monkeypatch.setattr(
        cli_module, "_connector_transport", lambda: lambda r, t: held.transport(r, t)
    )
    # Syncing a page needs no transport; the scripted one starts empty.
    held.source.mkdir(parents=True, exist_ok=True)
    (held.source / "run.fit").write_bytes(builder.run_fit_bytes())
    synced = runner.invoke(app, ["sync", str(held.source), "--out", str(held.root)])
    assert synced.exit_code == 0, synced.output
    text = held.page.read_text(encoding="utf-8")
    held.page.write_text(
        _add_frontmatter_key(text, f"publish: [{INSTANCE}]\n"), encoding="utf-8"
    )
    yield held


def _ok(body: bytes) -> HttpResponse:
    return HttpResponse(status=200, headers={}, body=body)


def _created(activity_id: str) -> HttpResponse:
    body = json.dumps({"activities": [{"id": activity_id}]}).encode()
    return HttpResponse(status=201, headers={}, body=body)


def _listing(*entries: dict[str, object]) -> HttpResponse:
    return _ok(json.dumps(list(entries)).encode())


def _published(rig: Rig) -> str:
    return extract_regions(rig.page.read_text(encoding="utf-8"))["published"]


def _row(result: Result) -> dict[str, object]:
    report = json.loads(result.stdout)
    (row,) = report["results"]
    assert isinstance(row, dict)
    return row


def _methods(transport: FakeTransport) -> list[str]:
    return [request.method for request in transport.requests]


def _update_target(request: HttpRequest) -> str:
    return urlsplit(request.url).path.rsplit("/", 1)[1]


def test_the_fixture_page_has_a_non_utc_start_and_opts_in(rig: Rig) -> None:
    subject = rig.subject()
    offset = subject.start.utcoffset()
    assert offset is not None and offset.total_seconds() != 0
    assert subject.distance_m is not None
    assert subject.base_fit is not None
    assert not rig.publish_ledger.exists()
    assert _published(rig) == ""


def test_a_listing_then_an_update_records_posted_with_the_direct_link(
    rig: Rig,
) -> None:
    rig.settings(None)
    transport = rig.script(_listing(rig.listing_entry(LISTED)), _ok(UPDATE_BODY))

    result = rig.publish()

    assert result.exit_code == 0, result.output
    assert _methods(transport) == ["GET", "PUT"]
    assert _update_target(transport.requests[1]) == LISTED
    link = LINK_BASE + LISTED
    row = _row(result)
    assert row["code"] == "posted"
    assert row["link"] == link
    assert row["link_refused"] is False
    assert _published(rig) == f"Published: [{LINK_LABEL}]({link})"
    (ledger,) = load_ledgers(rig.root, {INSTANCE: "intervals"}).values()
    (record,) = ledger.records
    assert record.code == "posted"
    assert record.link == link
    assert record.label == LINK_LABEL


def test_a_second_run_sends_nothing(rig: Rig) -> None:
    rig.settings(None)
    rig.script(_listing(rig.listing_entry(LISTED)), _ok(UPDATE_BODY))
    first = rig.publish()
    assert first.exit_code == 0, first.output
    page_after = rig.page.read_bytes()
    ledger_after = rig.publish_ledger.read_bytes()
    assert LISTED.encode() in page_after and LISTED.encode() in ledger_after

    transport = rig.script()
    second = rig.publish()

    assert second.exit_code == 0, second.output
    assert transport.requests == []
    assert _row(second)["code"] == "unchanged"
    assert rig.page.read_bytes() == page_after
    assert rig.publish_ledger.read_bytes() == ledger_after


def test_a_pull_record_leads_to_an_update_with_no_listing(rig: Rig) -> None:
    rig.settings(None)
    rig.pull_record(PULLED)
    transport = rig.script(_ok(UPDATE_BODY))

    result = rig.publish()

    assert result.exit_code == 0, result.output
    assert _methods(transport) == ["PUT"]
    assert _update_target(transport.requests[0]) == PULLED
    row = _row(result)
    assert row["code"] == "posted"
    assert row["link"] == LINK_BASE + PULLED
    assert _published(rig) == f"Published: [{LINK_LABEL}]({LINK_BASE + PULLED})"


def test_uploads_on_and_nothing_listed_uploads_then_updates(rig: Rig) -> None:
    rig.settings("true")
    transport = rig.script(_listing(), _created(UPLOADED), _ok(UPDATE_BODY))

    result = rig.publish()

    assert result.exit_code == 0, result.output
    assert _methods(transport) == ["GET", "POST", "PUT"]
    assert _update_target(transport.requests[2]) == UPLOADED
    (ledger,) = load_ledgers(rig.root, {INSTANCE: "intervals"}).values()
    (record,) = ledger.records
    sent = parse_qs(urlsplit(transport.requests[1].url).query)["external_id"]
    assert sent == [record.publication_id]
    assert len(record.publication_id) == 32
    link = LINK_BASE + UPLOADED
    assert record.code == "uploaded"
    assert record.link == link
    row = _row(result)
    assert row["code"] == "uploaded"
    assert row["link"] == link
    assert row["link_refused"] is False
    assert _published(rig) == f"Published: [{LINK_LABEL}]({link})"


def _due_again(rig: Rig, upload: str) -> None:
    """Settings with ``publish_upload = upload`` and a changed title template,
    so that the already-published page is due for a new update."""
    rig.settings(upload)
    with (rig.root / "fitdocs.toml").open("a", encoding="utf-8") as handle:
        handle.write(f'\n[publish.targets.{INSTANCE}]\ntitle = "Changed {{title}}"\n')


def _published_once(rig: Rig) -> None:
    """A first posted run, leaving a publish ledger, a pull record and a linked
    page behind so that the byte-identical comparison has content."""
    rig.settings(None)
    rig.pull_record(PULLED)
    rig.script(_ok(UPDATE_BODY))
    first = rig.publish()
    assert first.exit_code == 0, first.output


def _snapshot(rig: Rig) -> dict[Path, bytes]:
    return {
        path: path.read_bytes()
        for path in (rig.page, rig.publish_ledger, rig.pull_ledger)
    }


def test_a_due_page_is_updated_again_when_publish_upload_is_valid(rig: Rig) -> None:
    """The control for the test below: the same state with a valid setting
    sends one update and changes the page's record."""
    _published_once(rig)
    _due_again(rig, "false")
    before = _snapshot(rig)
    transport = rig.script(_ok(UPDATE_BODY))

    result = rig.publish()

    assert result.exit_code == 0, result.output
    assert _methods(transport) == ["PUT"]
    assert _snapshot(rig) != before


def test_a_non_boolean_publish_upload_exits_2_and_changes_nothing(rig: Rig) -> None:
    _published_once(rig)
    _due_again(rig, '"yes"')
    snapshot = _snapshot(rig)
    assert all(snapshot.values())
    assert b"intervals.icu/activities/" in snapshot[rig.page]
    transport = rig.script()

    result = rig.publish()

    assert result.exit_code == 2, result.output
    assert transport.requests == []
    message = result.output
    assert str(rig.root / "fitdocs.toml") in message
    assert INSTANCE in message
    assert "publish_upload" in message
    assert "'yes'" in message
    assert _snapshot(rig) == snapshot
