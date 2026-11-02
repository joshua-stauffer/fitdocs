"""``fitdocs publish`` end to end over a synced data root (publish-core 9.1;
Req 1.6, 2.2, 7.5, 8.3, 11.2, 13.5, 13.6, 14.2), driven through the installed
CLI with a scripted target registered in place of a real service.

Two scenarios share one harness (the CLI, a transport that records every call
and raises, a socket that raises, the tile fetch stubbed):

1. The lifecycle. Two synced pages opt in to one target. A dry run changes no
   byte of the data root and sends nothing; a posting run sends two requests,
   writes the ledger and each page's ``published`` region; a second posting run
   sends nothing and changes no byte. ``regen`` over damaged pages rewrites them
   and keeps the hand-written ``post`` region, the ``published`` region and the
   ``publish`` line; a page ``regen`` renames keeps its ledger record and its
   link, so the next run sends nothing for it either.
2. The sentinel. A target whose exceptions, refused links and non-result
   answers all carry one unique string: that string appears in no output, no
   ledger, no page and no file under the data root.
"""

from __future__ import annotations

import json
import re
import socket
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn, cast

import pytest
from typer.testing import CliRunner, Result

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.http import HttpRequest, HttpResponse
from fitdocs.connectors.protocol import ConnectorSession
from fitdocs.docmerge import extract_regions
from fitdocs.publish.ledger import load_ledgers
from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.request import PublishRequest, PublishResult
from tests.connectors.conftest import isolate_connector_environment
from tests.fixtures import builder
from tests.publish.conftest import ScriptedPublisher
from tests.test_effort_tags_e2e import (
    _add_frontmatter_key,
    _offline_tiles,
    _put,
    _set_region,
)

__all__ = ["_offline_tiles"]  # the autouse fixture must be visible in this module

runner = CliRunner()

CONNECTOR_ID = "scripted-alpha"
TARGET = "alpha"
LINK_BASE = "https://example.test/p/"
HAND_POST = "Hand title\n\nHand description line."
SENTINEL = "SENTINEL-7f3c9a1e-do-not-leak"


class LinkingPublisher(ScriptedPublisher):
    """Answers every request POSTED with a link made from its publication id."""

    def publish(
        self, session: ConnectorSession, request: PublishRequest
    ) -> PublishResult:
        self.publish_calls.append((session, request))
        return PublishResult(PublishCode.POSTED, LINK_BASE + request.publication_id)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "data"
        self.root.mkdir()
        self.source = tmp_path / "src"
        self.transport_calls: list[HttpRequest] = []
        self.socket_attempts = 0

    def invoke(self, *args: str) -> Result:
        return runner.invoke(app, [*args, "--out", str(self.root)])

    def sync(self) -> None:
        _put(self.source, "run.fit", builder.run_fit_bytes())
        _put(self.source, "ride.fit", builder.ride_fit_bytes())
        result = runner.invoke(app, ["sync", str(self.source), "--out", str(self.root)])
        assert result.exit_code == 0, result.output

    def configure(self) -> None:
        (self.root / "fitdocs.toml").write_text(
            f'[connectors.{TARGET}]\nconnector = "{CONNECTOR_ID}"\n', encoding="utf-8"
        )

    def page(self, kind: str) -> Path:
        (found,) = sorted((self.root / "workouts").glob(f"*-{kind}-*.md"))
        return found

    def tree(self) -> dict[str, bytes]:
        """Every file under the data root, by relative path, with its bytes."""
        files = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }
        assert files
        return files

    def ledger_file(self) -> Path:
        return self.root / ".fitdocs" / "publish" / f"{TARGET}.toml"


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    isolate_connector_environment(monkeypatch, tmp_path / "env")
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    monkeypatch.chdir(tmp_path)
    held = Harness(tmp_path)

    def refuse_socket(*args: object, **kwargs: object) -> NoReturn:
        held.socket_attempts += 1
        raise AssertionError("publish opened a socket")

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        held.transport_calls.append(request)
        raise AssertionError("publish used the connector transport")

    monkeypatch.setattr(socket, "socket", refuse_socket)
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: transport)
    yield held


def _register(publisher: ScriptedPublisher) -> None:
    connector_registry.register(publisher)


def _opted_in(harness: Harness) -> None:
    """Sync both pages and opt them in to the target; the run page also carries
    a hand-written ``post``."""
    harness.sync()
    harness.configure()
    for kind in ("run", "ride"):
        path = harness.page(kind)
        text = _add_frontmatter_key(
            path.read_text(encoding="utf-8"), f"publish: [{TARGET}]  # opted in\n"
        )
        if kind == "run":
            text = _set_region(text, "post", HAND_POST)
        path.write_text(text, encoding="utf-8")


def _published(path: Path) -> str:
    return extract_regions(path.read_text(encoding="utf-8"))["published"]


def _post(path: Path) -> str:
    return extract_regions(path.read_text(encoding="utf-8"))["post"]


def _retimed(page: Path) -> Path:
    """Move ``page`` to the name fitdocs would give it for a start an hour
    later, and record that start in it, so a later ``regen`` renames it back."""
    text = page.read_text(encoding="utf-8")
    recorded = re.search(r"^start_time: '(.+)'$", text, re.MULTILINE)
    assert recorded is not None
    shifted = datetime.fromisoformat(recorded.group(1)) + timedelta(hours=1)
    kind = page.stem.split("-")[3]
    moved = page.with_name(f"{shifted:%Y-%m-%d}-{kind}-{shifted:%H%M}.md")
    assert moved != page
    moved.write_text(
        text.replace(recorded.group(1), shifted.isoformat(), 1), encoding="utf-8"
    )
    page.unlink()
    return moved


def test_dry_run_posting_rerun_regen_and_rename_through_the_cli(
    harness: Harness,
) -> None:
    publisher = LinkingPublisher(connector_id=CONNECTOR_ID)
    _register(publisher)
    try:
        _opted_in(harness)
        run_page, ride_page = harness.page("run"), harness.page("ride")
        # The ride page is posted under a name that regen will change.
        ride_posted = _retimed(ride_page)
        assert not ride_page.exists()
        assert _published(run_page) == "" == _published(ride_posted)
        assert _post(run_page) == HAND_POST
        assert not harness.ledger_file().exists()

        # A dry run: both pages would post, and not one byte moves.
        before = harness.tree()
        dry = harness.invoke("publish")
        assert dry.exit_code == 0, dry.output
        # One report line per pair (the code also recurs in the tally and the
        # explanations, so a bare count could not tell one row from two).
        assert (
            len(re.findall(r"^workouts/\S+ -> alpha: would_post$", dry.stdout, re.M))
            == 2
        )
        assert harness.tree() == before
        assert publisher.publish_calls == []
        assert not harness.ledger_file().exists()
        assert not (harness.root / ".fitdocs" / "publish").exists()

        # The first posting run sends one request per page.
        posted = harness.invoke("publish", "--yes")
        assert posted.exit_code == 0, posted.output
        assert len(publisher.publish_calls) == 2
        sent = {call[1].publication_id: call[1] for call in publisher.publish_calls}
        assert len(sent) == 2
        by_title = {request.post.title: request for request in sent.values()}
        assert "Hand title" in by_title
        assert by_title["Hand title"].post.description == "Hand description line."
        (ledger,) = load_ledgers(harness.root, {TARGET: CONNECTOR_ID}).values()
        assert {record.publication_id for record in ledger.records} == set(sent)
        assert all(record.digest is not None for record in ledger.records)
        for page in (run_page, ride_posted):
            links = re.findall(re.escape(LINK_BASE) + r"[0-9a-f]{32}", _published(page))
            assert len(links) == 1
            assert links[0].removeprefix(LINK_BASE) in sent
        assert _post(run_page) == HAND_POST
        after_first = harness.tree()
        assert after_first != before

        # The second posting run: nothing sent, every byte as it was.
        again = harness.invoke("publish", "--yes")
        assert again.exit_code == 0, again.output
        assert (
            len(re.findall(r"^workouts/\S+ -> alpha: unchanged$", again.stdout, re.M))
            == 2
        )
        assert len(publisher.publish_calls) == 2
        assert harness.tree() == after_first

        # regen, over pages whose generated parts were damaged, keeps the
        # hand-written regions and the publish line.
        published_before = {page: _published(page) for page in (run_page, ride_posted)}
        assert all(published_before.values())
        for page in (run_page, ride_posted):
            damaged = page.read_text(encoding="utf-8").replace(
                "## Summary", "## Damaged summary", 1
            )
            assert "## Damaged summary" in damaged
            page.write_text(damaged, encoding="utf-8")
        ledger_bytes = harness.ledger_file().read_bytes()
        regenerated = harness.invoke("regen")
        assert regenerated.exit_code == 0, regenerated.output
        # regen gave the ride page its own name back; the other page kept its.
        assert not ride_posted.exists()
        assert ride_page.is_file()
        for page, before_path in ((run_page, run_page), (ride_page, ride_posted)):
            text = page.read_text(encoding="utf-8")
            assert "## Damaged summary" not in text
            assert "## Summary" in text
            assert _published(page) == published_before[before_path]
            assert f"publish: [{TARGET}]  # opted in\n" in text
        assert _post(run_page) == HAND_POST
        assert harness.ledger_file().read_bytes() == ledger_bytes
        assert (
            harness.ledger_file().read_bytes()
            == after_first[".fitdocs/publish/alpha.toml"]
        )

        # The record followed the page: the next run sends nothing for it.
        final_before = harness.tree()
        final = harness.invoke("publish", "--yes")
        assert final.exit_code == 0, final.output
        assert "workouts/" + ride_page.name + " -> alpha: unchanged" in final.stdout
        assert len(publisher.publish_calls) == 2
        assert harness.tree() == final_before
        assert harness.transport_calls == []
        assert harness.socket_attempts == 0
    finally:
        connector_registry.unregister(CONNECTOR_ID)


def test_nothing_a_target_says_reaches_an_output_a_ledger_or_a_page(
    harness: Harness,
) -> None:
    class Leaky(Exception):
        pass

    def leaky() -> Leaky:
        error = Leaky(f"upstream said {SENTINEL}")
        error.__cause__ = Leaky(f"cause {SENTINEL}")
        return error

    publisher = ScriptedPublisher(connector_id=CONNECTOR_ID)
    _register(publisher)
    try:
        _opted_in(harness)
        run_page, ride_page = harness.page("run"), harness.page("ride")
        refused_link = f"https://example.test/{SENTINEL} (bad)"
        publisher.publish_script.extend(
            [
                # Run 1: an exception on one page, a posted answer whose link is
                # unusable on the other.
                leaky(),
                PublishResult(PublishCode.POSTED, refused_link),
                # Run 2 (text): the failed page again, now answered with a thing
                # that is not a result at all.
                SENTINEL,
                # Run 3 (JSON): the same page again, a result with a code that is
                # not a code and a link carrying the sentinel.
                PublishResult(cast(PublishCode, SENTINEL), refused_link),
                # Run 4: an exception with a sentinel in its type name.
                type(SENTINEL, (Exception,), {})(SENTINEL),
            ]
        )
        outputs: list[str] = []
        runs = [
            ("publish", "--yes"),
            ("publish", "--yes"),
            ("publish", "--yes", "--format", "json"),
            ("publish", "--yes", "--format", "json"),
        ]
        for arguments in runs:
            result = harness.invoke(*arguments)
            outputs.append(result.stdout + result.stderr + result.output)
            assert result.exception is None or isinstance(result.exception, SystemExit)
            if "json" in arguments:
                json.loads(result.stdout)

        # Reachable: every scripted answer was consumed, the exception run
        # failed the page, and the unusable link was reported as refused.
        assert publisher.publish_script == []
        assert len(publisher.publish_calls) == 5
        assert "target_error" in outputs[0]
        assert "link: refused" in outputs[0]
        assert '"link_refused": true' in outputs[2]
        assert harness.ledger_file().is_file()
        assert SENTINEL in str(refused_link)

        for text in outputs:
            assert SENTINEL not in text
        leaks = [
            relative
            for relative, content in harness.tree().items()
            if SENTINEL.encode() in content
        ]
        assert leaks == []
        for page in (run_page, ride_page):
            assert SENTINEL not in page.read_text(encoding="utf-8")
        assert SENTINEL not in harness.ledger_file().read_text(encoding="utf-8")
        assert harness.transport_calls == []
    finally:
        connector_registry.unregister(CONNECTOR_ID)
