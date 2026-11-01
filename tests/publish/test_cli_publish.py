"""``fitdocs publish`` through the CLI (publish-core task 7.1).

Requirements 4.6, 4.8, 7.1, 7.3, 7.4, 7.10, 7.11 and 8.9, over a temporary
data root, the scripted publishing connector registered under the instance
names ``alpha`` and ``beta``, and a transport that records every call and
raises unless the test allows it (only the test of the transport wiring does).
The engine reports that raise as ``target_error``, so it does not fail a test by
itself: a test that must see no request asserts ``transport_calls == []`` (or
``world.calls() == 0``) explicitly.

The refusals of ``TestPreflight`` that go through ``assert_refused`` are pinned
by what they left behind: exit 2, a message naming what to fix, the data
root's bytes and mtimes unchanged, no call to the scripted connector, none to
the transport and an empty credentials directory. The ordering tests assert
only which of two messages is printed.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

import pytest
from typer.testing import CliRunner, Result

import fitdocs
import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry
from fitdocs.connectors.credentials import (
    CredentialStore,
    StoredCredentials,
    env_var_name,
)
from fitdocs.connectors.http import HttpRequest, HttpResponse
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    Granted,
)
from fitdocs.connectors.secrets import Secret
from fitdocs.docmerge import extract_regions
from fitdocs.layout import publish_ledger_path
from fitdocs.publish.ledger import PublishLedger, load_ledgers
from fitdocs.publish.outcomes import PublishCode, explanation
from fitdocs.publish.request import PublishRequest, PublishResult
from tests.connectors.conftest import isolate_connector_environment
from tests.publish.conftest import ScriptedPublisher
from tests.publish.test_engine import (
    DEFAULT_POST,
    SHA_A,
    SHA_B,
    Env,
    _fm,
    _ref,
    _snapshot,
)

runner = CliRunner()
LINK = "https://example.org/a/1"
POSTED = PublishResult(PublishCode.POSTED, LINK)
ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def invoke(args: list[str]) -> Result:
    return runner.invoke(app, ["publish", *args])


class KeyedPublisher(ScriptedPublisher):
    """A scripted publisher that authenticates with one API key."""

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        raise AssertionError("publish never verifies credentials")


class SendingPublisher(ScriptedPublisher):
    """A scripted publisher that makes one request through its session first."""

    def publish(
        self, session: ConnectorSession, request: PublishRequest
    ) -> PublishResult:
        session.http.send(HttpRequest("GET", "https://example.org/probe"))
        return super().publish(session, request)


class World:
    """A data root, its credentials directory and the scripted targets."""

    def __init__(self, root: Path, credentials: Path) -> None:
        self.root = root
        self.credentials = credentials
        self.targets: dict[str, ScriptedPublisher] = {}
        self.transport_calls: list[HttpRequest] = []
        self.transport_allowed = False
        self.pages = Env(root)

    def target(
        self, name: str, *, auth: bool = False, publish: bool = True
    ) -> ScriptedPublisher:
        options: dict[str, object] = {"connector_id": f"scripted-{name}"}
        if auth:
            options["auth_style"] = AuthStyle.API_KEY
            options["credential_fields"] = (CredentialField("api_key", "Key", True),)
        if not publish:
            options["capabilities"] = frozenset({Capability.PULL_THRESHOLDS})
        publisher = (KeyedPublisher if auth else ScriptedPublisher)(**options)  # type: ignore[arg-type]
        self.targets[name] = publisher
        return publisher

    def sending_target(self, name: str) -> ScriptedPublisher:
        publisher = SendingPublisher(connector_id=f"scripted-{name}")
        self.targets[name] = publisher
        return publisher

    def settings(self, extra: str = "") -> None:
        tables = "".join(
            f'[connectors.{name}]\nconnector = "{publisher.connector_id}"\n\n'
            for name, publisher in self.targets.items()
        )
        (self.root / "fitdocs.toml").write_text(tables + extra, encoding="utf-8")

    def page(self, name: str, sha: str, publish: str | None = "alpha") -> Path:
        return self.pages.write(name, _fm(sources=[_ref(sha)], publish=publish))

    def calls(self) -> int:
        return sum(len(each.publish_calls) for each in self.targets.values())

    def ledgers(self) -> dict[str, PublishLedger]:
        return load_ledgers(
            self.root,
            {name: each.connector_id for name, each in self.targets.items()},
        )


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    isolate_connector_environment(monkeypatch, tmp_path / "env")
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    monkeypatch.chdir(tmp_path)
    held = World(root, tmp_path / "env" / "credentials-dir")

    def forbidden_socket(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("publish opened a socket")

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        held.transport_calls.append(request)
        if not held.transport_allowed:
            raise AssertionError("publish used the connector transport")
        return HttpResponse(200, {}, b"")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: transport)
    try:
        yield held
    finally:
        for publisher in held.targets.values():
            if any(
                c.connector_id == publisher.connector_id for c in registry.available()
            ):
                registry.unregister(publisher.connector_id)


def register(held: World) -> None:
    held_ids = {each.connector_id for each in registry.available()}
    for publisher in held.targets.values():
        if publisher.connector_id not in held_ids:
            registry.register(publisher)


def ready(held: World, *names: str, auth: bool = False) -> None:
    """Configure ``names`` as publish targets and register them."""
    for name in names:
        held.target(name, auth=auth)
    held.settings()
    register(held)


def arm(held: World, name: str = "alpha") -> None:
    """Script one successful post so a refused run could really have posted."""
    held.targets[name].publish_script.append(POSTED)


def assert_refused(
    held: World, result: Result, before: object, *, mentions: str
) -> None:
    assert result.exit_code == 2, result.output
    assert mentions in result.stderr, result.stderr
    assert result.stdout == ""
    assert _snapshot(held.root) == before
    assert held.calls() == 0
    assert held.transport_calls == []
    assert list(held.credentials.iterdir()) == []


DRY_RUN_TEXT = (
    "fitdocs publish: dry run; nothing is sent (add --yes to post).\n"
    "workouts/a.md -> alpha: would_post\n"
    "  title: Morning Run\n"
    "  description:\n"
    "    Distance: 12.50 km\n"
    "    Time: 58:20\n"
    "    Pace: 4:40 /km\n"
    "    Average heart rate: 149 bpm\n"
    "    Average power: 231 W\n"
    "    Elevation gain: 88 m\n"
    "1 would_post; 0 pages opted in to no selected target.\n"
    "\n"
)


class TestDryRun:
    def test_prints_the_post_and_sends_and_writes_nothing(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        before = _snapshot(world.root)
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert result.stdout == DRY_RUN_TEXT + (
            f"would_post: {explanation(PublishCode.WOULD_POST)}\n"
        )
        assert DEFAULT_POST.title == "Morning Run"
        assert _snapshot(world.root) == before
        assert world.calls() == 0
        assert world.transport_calls == []
        assert list(world.credentials.iterdir()) == []
        assert not publish_ledger_path(world.root, "alpha").exists()

    def test_json_holds_the_same_result(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        result = invoke(["--format", "json", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {
            "format": 1,
            "posting": False,
            "results": [
                {
                    "page": "workouts/a.md",
                    "target": "alpha",
                    "code": "would_post",
                    "decision": "would_post",
                    "title": "Morning Run",
                    "description": DEFAULT_POST.description,
                    "link": None,
                    "link_refused": False,
                    "detail": None,
                }
            ],
            "counts": {"would_post": 1},
            "not_opted_in": 0,
            "explanations": {"would_post": explanation(PublishCode.WOULD_POST)},
        }
        assert result.stdout.endswith("}\n")

    def test_json_is_chosen_whatever_the_case_of_the_name(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        result = invoke(["--format", "JSON", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["posting"] is False

    def test_a_failure_code_in_a_dry_run_exits_1(self, world: World) -> None:
        ready(world, "alpha")
        world.pages.write("a.md", _fm(sources=[_ref(SHA_A)], publish=5))
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 1, result.output
        assert "opt_in_invalid" in result.stdout

    def test_a_named_page_that_opts_in_to_nothing_exits_0(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A, publish=None)
        result = invoke(["a.md", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert "workouts/a.md: not_opted_in" in result.stdout
        assert "No publish target is configured." not in result.stdout

    def test_without_pages_and_no_opt_in_the_output_is_pinned(
        self, world: World
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A, publish=None)
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert result.stdout == (
            "fitdocs publish: dry run; nothing is sent (add --yes to post).\n"
            "no results; 1 page opted in to no selected target.\n"
        )

    def test_out_chooses_the_data_root(
        self, world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        decoy = tmp_path / "decoy"
        decoy.mkdir()
        monkeypatch.setenv("FITDOCS_DATA", str(decoy))
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert "workouts/a.md -> alpha: would_post" in result.stdout

    def test_a_path_is_taken_from_the_working_directory(
        self, world: World, tmp_path: Path
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.page("b.md", SHA_B)
        result = invoke(["data/workouts/b.md", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert re.findall(r"^(\S+ -> \w+): would_post$", result.stdout, re.M) == [
            "workouts/b.md -> alpha"
        ]

    def test_an_unknown_name_is_reported_only_when_to_does_not_exclude_it(
        self, world: World
    ) -> None:
        ready(world, "alpha", "beta")
        world.pages.write(
            "a.md", _fm(sources=[_ref(SHA_A)], publish=["alpha", "ghost"])
        )
        full = invoke(["--out", str(world.root)])
        assert full.exit_code == 1, full.output
        assert "workouts/a.md -> ghost: unknown_target" in full.stdout
        narrowed = invoke(["--to", "alpha", "--out", str(world.root)])
        assert narrowed.exit_code == 0, narrowed.output
        assert "unknown_target" not in narrowed.stdout

    def test_pages_and_to_narrow_the_run(self, world: World) -> None:
        ready(world, "alpha", "beta")
        world.pages.write("a.md", _fm(sources=[_ref(SHA_A)], publish=["alpha", "beta"]))
        world.pages.write("b.md", _fm(sources=[_ref(SHA_B)], publish=["alpha", "beta"]))
        everything = invoke(["--out", str(world.root)])
        assert re.findall(r"^(\S+ -> \w+): would_post$", everything.stdout, re.M) == [
            "workouts/a.md -> alpha",
            "workouts/a.md -> beta",
            "workouts/b.md -> alpha",
            "workouts/b.md -> beta",
        ]
        narrowed = invoke(["b", "--to", "beta", "--out", str(world.root)])
        assert narrowed.exit_code == 0, narrowed.output
        assert re.findall(r"^(\S+ -> \w+): would_post$", narrowed.stdout, re.M) == [
            "workouts/b.md -> beta"
        ]
        two = invoke(
            ["--to", "beta", "--to", "alpha", "b.md", "--out", str(world.root)]
        )
        assert re.findall(r"^(\S+ -> \w+): would_post$", two.stdout, re.M) == [
            "workouts/b.md -> alpha",
            "workouts/b.md -> beta",
        ]


class TestNoTarget:
    def test_it_says_so_and_exits_0(self, world: World) -> None:
        world.page("a.md", SHA_A, publish=None)
        before = _snapshot(world.root)
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert result.stdout == "No publish target is configured.\n"
        assert _snapshot(world.root) == before
        assert world.transport_calls == []

    def test_a_named_page_is_listed_and_the_sentence_follows(
        self, world: World
    ) -> None:
        world.page("a.md", SHA_A, publish=None)
        result = invoke(["a.md", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert "workouts/a.md: not_opted_in" in result.stdout
        assert result.stdout.endswith("\nNo publish target is configured.\n")

    def test_a_page_that_opts_in_to_a_missing_target_fails(self, world: World) -> None:
        world.page("a.md", SHA_A, publish="alpha")
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 1, result.output
        assert "workouts/a.md -> alpha: unknown_target" in result.stdout
        assert "No publish target is configured." not in result.stdout

    def test_a_connector_that_is_not_a_publish_target_is_not_one(
        self, world: World
    ) -> None:
        world.target("alpha", publish=False)
        world.settings()
        register(world)
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert result.stdout == "No publish target is configured.\n"

    def test_json_keeps_its_shape(self, world: World) -> None:
        result = invoke(["--format", "json", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["results"] == []


class TestPosting:
    def test_posts_records_and_links(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.page("b.md", SHA_B)
        publisher = world.targets["alpha"]
        publisher.publish_script.extend([POSTED, PublishResult(PublishCode.POSTED)])
        started = datetime.now(UTC)
        result = invoke(["--yes", "--out", str(world.root)])
        finished = datetime.now(UTC)
        assert result.exit_code == 0, result.output
        assert result.stdout.splitlines()[:1] == ["fitdocs publish: posting."]
        assert "workouts/a.md -> alpha: posted\n  link: " + LINK in result.stdout
        assert "2 posted; 0 pages opted in to no selected target." in result.stdout
        requests: list[PublishRequest] = [call[1] for call in publisher.publish_calls]
        assert [r.post.title for r in requests] == ["Morning Run"] * 2
        assert [r.post.description for r in requests] == [DEFAULT_POST.description] * 2
        records = world.ledgers()["alpha"].records
        assert len(records) == 2
        ids = [record.publication_id for record in records]
        assert all(ID_PATTERN.fullmatch(each) for each in ids)
        assert len(set(ids)) == 2
        session = publisher.publish_calls[0][0]
        assert session.instance == "alpha"
        assert session.data_root == world.root
        assert session.sleep is time.sleep
        assert started <= session.now() <= datetime.now(UTC)
        assert sorted(r.publication_id for r in requests) == sorted(ids)
        for record in records:
            assert record.code == "posted"
            assert record.at is not None
            assert started <= record.at <= finished
            assert record.digest is not None
        region = extract_regions(
            (world.root / "workouts" / "a.md").read_text(encoding="utf-8")
        )["published"]
        assert LINK in region
        assert world.transport_calls == []

    def test_json_reports_the_posting_run(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        result = invoke(["--yes", "--format", "json", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        document = json.loads(result.stdout)
        assert document["posting"] is True
        assert [(r["code"], r["link"]) for r in document["results"]] == [
            ("posted", LINK)
        ]
        assert document["counts"] == {"posted": 1}

    def test_a_second_run_sends_nothing(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        assert invoke(["--yes", "--out", str(world.root)]).exit_code == 0
        before = _snapshot(world.root)
        again = invoke(["--yes", "--out", str(world.root)])
        assert again.exit_code == 0, again.output
        assert "workouts/a.md -> alpha: unchanged" in again.stdout
        assert len(world.targets["alpha"].publish_calls) == 1
        assert world.transport_calls == []
        assert {k: v[2] for k, v in _snapshot(world.root).items()} == {
            k: v[2] for k, v in before.items()
        }

    def test_a_failure_code_exits_1_and_is_recorded(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(
            PublishResult(PublishCode.UNAVAILABLE)
        )
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 1, result.output
        assert "workouts/a.md -> alpha: unavailable" in result.stdout
        (record,) = world.ledgers()["alpha"].records
        assert record.code == "unavailable"
        assert record.digest is None

    def test_a_target_needing_credentials_uses_the_store(self, world: World) -> None:
        ready(world, "alpha", auth=True)
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        CredentialStore(world.credentials).save(
            "alpha",
            StoredCredentials(
                connector_id="scripted-alpha",
                auth_style=AuthStyle.API_KEY,
                values={"api_key": Secret("stored-key")},
                expires_at=None,
                scopes=None,
            ),
        )
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert len(world.targets["alpha"].publish_calls) == 1
        assert "stored-key" not in result.output

    def test_a_target_uses_environment_credentials(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha", auth=True)
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        monkeypatch.setenv(env_var_name("alpha", "api_key"), "env-key")
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert len(world.targets["alpha"].publish_calls) == 1
        assert "env-key" not in result.output

    def test_a_target_sends_through_the_connector_transport(self, world: World) -> None:
        publisher = world.sending_target("alpha")
        world.settings()
        register(world)
        world.page("a.md", SHA_A)
        publisher.publish_script.append(POSTED)
        world.transport_allowed = True
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert [call.url for call in world.transport_calls] == [
            "https://example.org/probe"
        ]

    def test_a_target_without_credentials_is_not_connected(self, world: World) -> None:
        ready(world, "alpha", auth=True)
        world.page("a.md", SHA_A)
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 1, result.output
        assert "workouts/a.md -> alpha: not_connected" in result.stdout
        assert world.calls() == 0
        assert world.transport_calls == []

    def test_an_interrupt_exits_130_and_keeps_the_received_outcome(
        self, world: World
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.page("b.md", SHA_B)
        world.targets["alpha"].publish_script.extend([POSTED, KeyboardInterrupt()])
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 130, result.output
        assert (
            "Publish run interrupted; every outcome already received is recorded."
            in result.stderr
        )
        assert result.stdout == ""
        assert len(world.targets["alpha"].publish_calls) == 2
        records = {r.page: r for r in world.ledgers()["alpha"].records}
        assert len(records) == 2
        first = next(r for r in records.values() if r.code == "posted")
        assert first.link == LINK
        assert first.digest is not None
        other = next(r for r in records.values() if r is not first)
        assert (other.code, other.digest) == (None, None)
        region = extract_regions(
            (world.root / "workouts" / "a.md").read_text(encoding="utf-8")
        )["published"]
        assert LINK in region


class TestPreflight:
    def test_no_data_root(
        self, world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = tmp_path / "elsewhere"
        empty.mkdir()
        monkeypatch.chdir(empty)
        result = invoke([])
        assert result.exit_code == 2, result.output
        assert "FITDOCS_DATA" in result.stderr
        assert result.stdout == ""

    def test_a_malformed_settings_document(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        (world.root / "fitdocs.toml").write_text("[connectors\n", encoding="utf-8")
        before = _snapshot(world.root)
        result = invoke(["--out", str(world.root)])
        assert_refused(world, result, before, mentions="fitdocs.toml")

    def test_a_malformed_inbox_table(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        arm(world)
        world.settings("[inbox]\npath = 7\n")
        before = _snapshot(world.root)
        result = invoke(["--yes", "--out", str(world.root)])
        assert_refused(world, result, before, mentions="inbox")

    def test_a_malformed_connectors_table(self, world: World) -> None:
        ready(world, "alpha")
        (world.root / "fitdocs.toml").write_text(
            "[connectors]\nalpha = 7\n", encoding="utf-8"
        )
        before = _snapshot(world.root)
        result = invoke(["--out", str(world.root)])
        assert_refused(world, result, before, mentions="[connectors")

    @pytest.mark.parametrize(
        ("table", "mentions"),
        [
            ("[publish]\nbogus = 1\n", "[publish] has unknown key 'bogus'"),
            ("[publish]\ntitle = 5\n", "[publish] title must be text"),
            ("[publish]\ntitle = '{nope}'\n", "[publish] title: invalid template"),
            ('[publish]\ntitle = "a\\nb"\n', "[publish] title must be a single line"),
            (
                "[publish.targets.ghost]\ntitle = 'x'\n",
                "not a configured publish target",
            ),
        ],
    )
    @pytest.mark.parametrize("posting", [False, True])
    def test_a_bad_publish_table_even_when_no_page_opts_in(
        self, world: World, table: str, mentions: str, posting: bool
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A, publish=None)
        world.settings(table)
        before = _snapshot(world.root)
        args = ["--yes"] if posting else []
        result = invoke([*args, "--out", str(world.root)])
        assert_refused(world, result, before, mentions=mentions)
        assert "fitdocs.toml" in result.stderr

    def test_a_bad_publish_table_is_checked_with_no_target_configured(
        self, world: World
    ) -> None:
        world.settings("[publish]\nbogus = 1\n")
        before = _snapshot(world.root)
        result = invoke(["--out", str(world.root)])
        assert_refused(world, result, before, mentions="unknown key 'bogus'")

    def test_an_unknown_to_name_lists_every_publish_target(self, world: World) -> None:
        ready(world, "alpha", "beta")
        world.target("gamma", publish=False)
        world.settings()
        register(world)
        world.page("a.md", SHA_A)
        arm(world)
        before = _snapshot(world.root)
        result = invoke(
            ["--yes", "--to", "alpha", "--to", "nope", "--out", str(world.root)]
        )
        assert_refused(world, result, before, mentions="'nope'")
        assert "configured publish targets: alpha, beta" in result.stderr
        assert "gamma" not in result.stderr

    def test_a_publish_table_for_a_connector_that_is_not_a_publish_target(
        self, world: World
    ) -> None:
        ready(world, "alpha")
        world.target("gamma", publish=False)
        world.settings("[publish.targets.gamma]\ntitle = 'x'\n")
        register(world)
        world.page("a.md", SHA_A)
        before = _snapshot(world.root)
        result = invoke(["--yes", "--out", str(world.root)])
        assert_refused(
            world, result, before, mentions="not a configured publish target"
        )

    def test_an_inbox_path_that_cannot_be_used(
        self, world: World, tmp_path: Path
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        outside = tmp_path / "elsewhere" / "inbox"
        world.settings(f"[inbox]\npath = '{outside}'\n")
        assert not outside.exists()
        before = _snapshot(world.root)
        result = invoke(["--yes", "--out", str(world.root)])
        assert_refused(world, result, before, mentions=str(outside))
        assert not outside.exists()

    def test_a_to_name_that_is_not_a_publish_target(self, world: World) -> None:
        ready(world, "alpha")
        world.target("gamma", publish=False)
        world.settings()
        register(world)
        world.page("a.md", SHA_A)
        arm(world)
        before = _snapshot(world.root)
        result = invoke(["--yes", "--to", "gamma", "--out", str(world.root)])
        assert_refused(world, result, before, mentions="'gamma'")

    def test_a_named_page_that_does_not_exist(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        arm(world)
        before = _snapshot(world.root)
        result = invoke(["--yes", "missing.md", "--out", str(world.root)])
        assert_refused(world, result, before, mentions="missing.md")

    def test_a_named_page_that_is_not_a_workout_page(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.pages.write("note.md", {"type": "note"})
        arm(world)
        before = _snapshot(world.root)
        result = invoke(["--yes", "note.md", "--out", str(world.root)])
        assert_refused(world, result, before, mentions="note.md: is not a workout page")

    def test_an_unusable_ledger(self, world: World) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        path = publish_ledger_path(world.root, "alpha")
        path.parent.mkdir(parents=True)
        path.write_text("ledger_version = 99\n", encoding="utf-8")
        before = _snapshot(world.root)
        result = invoke(["--yes", "--out", str(world.root)])
        assert_refused(world, result, before, mentions=str(path))

    def test_a_credentials_directory_inside_the_data_root(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha", auth=True)
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        monkeypatch.setenv(env_var_name("alpha", "api_key"), "env-key")
        monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(world.root / "creds"))
        before = _snapshot(world.root)
        result = invoke(["--yes", "--out", str(world.root)])
        assert_refused(world, result, before, mentions="credentials directory")

    def test_one_authenticating_target_among_the_selected_is_enough(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha")
        world.target("beta", auth=True)
        world.settings()
        register(world)
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(world.root / "creds"))
        before = _snapshot(world.root)
        result = invoke(["--yes", "--out", str(world.root)])
        assert_refused(world, result, before, mentions="credentials directory")

    def test_a_ledger_of_an_unselected_target_is_still_checked(
        self, world: World
    ) -> None:
        ready(world, "alpha", "beta")
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        path = publish_ledger_path(world.root, "beta")
        path.parent.mkdir(parents=True)
        path.write_text('ledger_version = 1\nconnector = "other"\n', encoding="utf-8")
        before = _snapshot(world.root)
        result = invoke(["--yes", "--to", "alpha", "--out", str(world.root)])
        assert_refused(world, result, before, mentions=str(path))

    def test_the_credentials_directory_is_not_checked_for_a_dry_run(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha", auth=True)
        world.page("a.md", SHA_A)
        monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(world.root / "creds"))
        result = invoke(["--out", str(world.root)])
        assert result.exit_code == 0, result.output
        assert "workouts/a.md -> alpha: would_post" in result.stdout

    def test_the_credentials_directory_is_not_checked_without_an_authenticating_target(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha")
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(world.root / "creds"))
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 0, result.output

    def test_the_credentials_directory_is_not_checked_for_an_unselected_target(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha")
        world.target("beta", auth=True)
        world.settings()
        register(world)
        world.page("a.md", SHA_A)
        world.targets["alpha"].publish_script.append(POSTED)
        monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(world.root / "creds"))
        result = invoke(["--yes", "--to", "alpha", "--out", str(world.root)])
        assert result.exit_code == 0, result.output

    # The design's order: settings (3), [publish] (4), --to (6), PAGES (7),
    # ledgers (8), credentials directory (9). Each case holds two defects and
    # shows that the earlier step's message is the one printed.
    def test_publish_table_before_to(self, world: World) -> None:
        ready(world, "alpha")
        world.settings("[publish]\nbogus = 1\n")
        result = invoke(["--to", "nope", "--out", str(world.root)])
        assert result.exit_code == 2
        assert "unknown key 'bogus'" in result.stderr
        assert "nope" not in result.stderr

    def test_to_before_pages(self, world: World) -> None:
        ready(world, "alpha")
        result = invoke(["missing.md", "--to", "nope", "--out", str(world.root)])
        assert result.exit_code == 2
        assert "'nope'" in result.stderr
        assert "missing.md" not in result.stderr

    def test_pages_before_ledgers(self, world: World) -> None:
        ready(world, "alpha")
        path = publish_ledger_path(world.root, "alpha")
        path.parent.mkdir(parents=True)
        path.write_text("ledger_version = 99\n", encoding="utf-8")
        result = invoke(["missing.md", "--out", str(world.root)])
        assert result.exit_code == 2
        assert "missing.md" in result.stderr
        assert str(path) not in result.stderr

    def test_ledgers_before_credentials(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ready(world, "alpha", auth=True)
        path = publish_ledger_path(world.root, "alpha")
        path.parent.mkdir(parents=True)
        path.write_text("ledger_version = 99\n", encoding="utf-8")
        monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(world.root / "creds"))
        result = invoke(["--yes", "--out", str(world.root)])
        assert result.exit_code == 2
        assert str(path) in result.stderr
        assert "credentials directory" not in result.stderr


def test_importing_the_cli_loads_only_the_leaves_of_the_publish_package() -> None:
    source = Path(fitdocs.__file__).parent.parent
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(source)!r})\n"
        "import fitdocs.cli\n"
        "assert sys.modules['fitdocs'].__file__.startswith("
        f"{str(source)!r}), sys.modules['fitdocs'].__file__\n"
        "print(sorted(n for n in sys.modules if n.startswith('fitdocs.publish')))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(
        ["fitdocs.publish", "fitdocs.publish.outcomes", "fitdocs.publish.request"]
    )
