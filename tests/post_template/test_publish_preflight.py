"""``fitdocs publish`` reads the post template's ``since`` (post-templates task 5.3).

Requirements 1.3, 8.6, 12.1, 12.2, 12.8, 12.10. The data root is the one the
sync tests build (``tests.post_template.test_sync_pass.World``): a synthetic
``.fit`` file, the real index and the real sync. One scripted publish target
named ``alpha`` is added to it, and the page the sync wrote is opted in to it.
Sockets are forbidden, and ``run_publish`` is wrapped to record its plan.
"""

from __future__ import annotations

import json
import socket
import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

import pytest
from typer.testing import Result

from fitdocs import cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry
from fitdocs.layout import publish_ledger_path
from fitdocs.publish import engine as publish_engine
from fitdocs.publish import targets as targets_module
from tests.post_template.test_sync_pass import TEMPLATE as _SYNC_TEMPLATE
from tests.post_template.test_sync_pass import World as SyncWorld
from tests.post_template.test_sync_pass import runner
from tests.publish.conftest import ScriptedPublisher
from tests.publish.test_engine import _snapshot

PAGE_DATE = date(2021, 9, 8)
FILLED_TITLE = "Run 1"
FILLED_DESCRIPTION = "Counted 1 so far"
TEMPLATE = _SYNC_TEMPLATE.replace(
    'title = "Run {n}"\n', 'title = "Run {n}"\ndescription = "Counted {n} so far"\n'
)
BROKEN = {
    "syntax": ('title = "unterminated\n', ["is not valid TOML: Illegal character"]),
    "unknown-key": (
        TEMPLATE + 'colour = "red"\n',
        ["vars.n: holds the unknown key 'colour'"],
    ),
    "two-problems": (
        'since = "x"\ncolour = "red"\ntitle = "t"\n',
        [
            "colour: not a recognized key",
            "since: must be a TOML date without a time",
        ],
    ),
}


class PublishWorld(SyncWorld):
    """The sync world with one scripted publish target."""

    publisher: ScriptedPublisher
    plans: list[publish_engine.PublishPlan]
    opened: list[str]

    def template(self, text: str = TEMPLATE) -> None:
        super().template(text)

    def publish(self, *args: str) -> Result:
        return runner.invoke(app, ["publish", *args, "--out", str(self.root)])

    def opt_in(self) -> Path:
        [page] = self.pages()
        text = page.read_text(encoding="utf-8")
        marker = "generator: fitdocs\n"
        assert text.count(marker) == 1
        page.write_text(
            text.replace(marker, marker + "publish: alpha\n"), encoding="utf-8"
        )
        return page

    def rows(self, result: Result) -> list[dict[str, Any]]:
        assert result.exit_code in (0, 1), result.output
        found: list[dict[str, Any]] = json.loads(result.stdout)["results"]
        return found


@pytest.fixture
def pw(
    per_test_directory: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[PublishWorld]:
    held = PublishWorld(per_test_directory, monkeypatch)
    held.publisher = ScriptedPublisher(connector_id="scripted-alpha")
    held.plans = []
    held.opened = []
    registry.register(held.publisher)
    settings = held.root / "fitdocs.toml"
    settings.write_text(
        settings.read_text(encoding="utf-8")
        + '[connectors.alpha]\nconnector = "scripted-alpha"\n',
        encoding="utf-8",
    )

    def forbidden_socket(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("publish opened a socket")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    real_run = publish_engine.run_publish

    def recording_run(plan: publish_engine.PublishPlan, **kwargs: Any) -> Any:
        held.plans.append(plan)
        return real_run(plan, **kwargs)

    monkeypatch.setattr(publish_engine, "run_publish", recording_run)
    real_prepare = targets_module.prepare_target

    def recording_prepare(instance: Any, **kwargs: Any) -> Any:
        held.opened.append(instance.name)
        return real_prepare(instance, **kwargs)

    monkeypatch.setattr(targets_module, "prepare_target", recording_prepare)
    try:
        yield held
    finally:
        registry.unregister(held.publisher.connector_id)


def only_row(world: PublishWorld, result: Result) -> dict[str, Any]:
    [row] = world.rows(result)
    return row


# --------------------------------------------------------------------------- #
# The refusal and the fill, end to end
# --------------------------------------------------------------------------- #


def test_a_page_synced_before_the_index_is_refused_as_waiting(pw: PublishWorld) -> None:
    pw.template()
    pw.add_run("sync")
    synced = pw.sync()
    assert "the index is not built" in synced.output
    pw.opt_in()

    result = pw.publish("--format", "json")

    assert result.exit_code == 1, result.output
    row = only_row(pw, result)
    assert row["code"] == "post_waiting"
    assert row["decision"] != "would_post"
    assert row["page"].endswith(".md")
    assert pw.plans[0].post_template_since == date(2021, 1, 1)
    assert pw.publisher.publish_calls == []
    text = pw.publish().stdout
    assert "-> alpha: post_waiting" in text
    assert "would_post" not in text


def test_after_the_index_and_a_sync_the_page_would_post_the_filled_text(
    pw: PublishWorld,
) -> None:
    pw.template()
    pw.add_run("sync")
    pw.sync()
    pw.build_index()
    refilled = pw.sync()
    assert "Post template: 1 filled" in refilled.output
    page = pw.opt_in()
    assert FILLED_TITLE in pw.post_region(page)

    result = pw.publish("--format", "json")

    assert result.exit_code == 0, result.output
    row = only_row(pw, result)
    assert row["code"] == "would_post"
    assert (row["title"], row["description"]) == (FILLED_TITLE, FILLED_DESCRIPTION)
    assert "post_waiting" not in result.stdout
    assert not publish_ledger_path(pw.root, "alpha").exists()


def test_the_post_is_the_filled_region_not_the_generated_facts(
    pw: PublishWorld,
) -> None:
    pw.template()
    pw.add_run("sync")
    pw.build_index()
    pw.sync()
    page = pw.opt_in()
    region = pw.post_region(page)

    row = only_row(pw, pw.publish("--format", "json"))

    assert row["code"] == "would_post"
    assert FILLED_TITLE in region and FILLED_DESCRIPTION in region
    assert row["title"] == FILLED_TITLE
    assert row["description"] == FILLED_DESCRIPTION


# --------------------------------------------------------------------------- #
# `since` reaches the plan and the engine uses it
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("since", ["2021-03-05", "2021-09-08", "2021-09-09"])
def test_the_templates_since_is_the_plans(pw: PublishWorld, since: str) -> None:
    pw.template(TEMPLATE.replace("2021-01-01", since))
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()

    result = pw.publish("--format", "json")

    [plan] = pw.plans
    assert plan.post_template_since == date.fromisoformat(since)
    assert plan.post_template_since not in (None, cli_module._today())
    expected = "post_waiting" if date.fromisoformat(since) <= PAGE_DATE else None
    row = only_row(pw, result)
    if expected is None:
        assert row["code"] != "post_waiting", "a page before the window is not held"
    else:
        assert row["code"] == expected


# --------------------------------------------------------------------------- #
# A refused template
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("args", [[], ["--targets"], ["--yes"]], ids=str)
@pytest.mark.parametrize("broken", sorted(BROKEN))
def test_a_refused_template_stops_publish_before_anything(
    pw: PublishWorld, broken: str, args: list[str]
) -> None:
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()
    text, problems = BROKEN[broken]
    pw.template(text)
    before = _snapshot(pw.root)
    listed: list[object] = []
    real_list = targets_module.list_targets
    pw.monkeypatch.setattr(
        targets_module,
        "list_targets",
        lambda *a, **k: listed.append(a) or real_list(*a, **k),
    )

    result = pw.publish(*args)

    assert result.exit_code == 2, result.output
    path = str(pw.root / "post-template.toml")
    for problem in problems:
        assert f"{path}: {problem}" in result.stderr, result.stderr
    assert len(result.stderr.strip().splitlines()) == len(problems), result.stderr
    assert result.stdout == ""
    assert _snapshot(pw.root) == before
    assert pw.plans == []
    assert pw.opened == []
    assert listed == []
    assert pw.publisher.publish_calls == []
    assert not publish_ledger_path(pw.root, "alpha").exists()


def test_a_dangling_template_symlink_is_a_refused_template(pw: PublishWorld) -> None:
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()
    (pw.root / "post-template.toml").symlink_to(pw.root / "nowhere.toml")

    result = pw.publish("--targets")

    assert result.exit_code == 2, result.output
    assert "post-template.toml" in result.stderr


def test_a_good_template_leaves_targets_listing_as_it_was(pw: PublishWorld) -> None:
    pw.add_run("sync")
    pw.sync()
    without = pw.publish("--targets")
    pw.template()
    with_template = pw.publish("--targets")

    assert without.exit_code == with_template.exit_code == 0, without.output
    assert "alpha" in with_template.stdout
    assert with_template.stdout == without.stdout
    assert with_template.stderr == without.stderr


def test_a_valid_template_with_no_waiting_page_changes_nothing_printed(
    pw: PublishWorld,
) -> None:
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()
    without = pw.publish()
    without_json = pw.publish("--format", "json")
    # The window starts after the page, so no page is held.
    pw.template(TEMPLATE.replace("2021-01-01", "2021-09-09"))
    with_template = pw.publish()
    with_json = pw.publish("--format", "json")

    assert without.exit_code == with_template.exit_code == 0, without.output
    assert with_template.stdout == without.stdout
    assert with_template.stderr == without.stderr == ""
    assert with_json.stdout == without_json.stdout
    assert with_json.stderr == without_json.stderr == ""


def test_yes_with_a_waiting_page_posts_nothing_and_writes_no_ledger(
    pw: PublishWorld,
) -> None:
    pw.template()
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()
    pw.publisher.publish_script.append(object())

    result = pw.publish("--yes", "--format", "json")

    assert result.exit_code == 1, result.output
    assert only_row(pw, result)["code"] == "post_waiting"
    assert pw.publisher.publish_calls == []
    assert pw.plans[0].posting is True
    assert pw.plans[0].post_template_since == date(2021, 1, 1)
    assert not publish_ledger_path(pw.root, "alpha").exists()


# --------------------------------------------------------------------------- #
# No template, or a template that is gone
# --------------------------------------------------------------------------- #


def _unload_post_template(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [m for m in sys.modules if m.startswith("fitdocs.post_template")]:
        monkeypatch.delitem(sys.modules, name)


@pytest.mark.parametrize("args", [[], ["--format", "json"], ["--targets"]], ids=str)
def test_with_no_template_publish_imports_nothing_and_plans_no_window(
    pw: PublishWorld, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()
    _unload_post_template(monkeypatch)

    result = pw.publish(*args)

    assert result.exit_code == 0, result.output
    assert [m for m in sys.modules if m.startswith("fitdocs.post_template")] == []
    if args != ["--targets"]:
        [plan] = pw.plans
        assert plan.post_template_since is None
        assert "post_waiting" not in result.stdout
        assert "would_post" in result.stdout
    assert not publish_ledger_path(pw.root, "alpha").exists()


def test_with_no_template_the_output_equals_the_run_with_the_window_removed(
    pw: PublishWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    pw.add_run("sync")
    pw.sync()
    pw.opt_in()
    after = pw.publish()
    pw.plans.clear()
    real_run = publish_engine.run_publish
    import dataclasses

    monkeypatch.setattr(
        publish_engine,
        "run_publish",
        lambda plan, **kw: real_run(
            dataclasses.replace(plan, post_template_since=None), **kw
        ),
    )
    before = pw.publish()
    assert before.exit_code == after.exit_code == 0
    assert before.output == after.output


def test_a_filled_page_whose_template_is_deleted_keeps_its_text(
    pw: PublishWorld,
) -> None:
    pw.template()
    pw.add_run("sync")
    pw.build_index()
    pw.sync()
    page = pw.opt_in()
    with_template = only_row(pw, pw.publish("--format", "json"))
    filled = pw.post_region(page)
    (pw.root / "post-template.toml").unlink()
    pw.plans.clear()
    resynced = pw.sync()
    assert resynced.exit_code == 0, resynced.output
    assert pw.post_region(page) == filled

    result = pw.publish("--format", "json")

    assert pw.post_region(page) == filled
    assert FILLED_TITLE in filled and FILLED_DESCRIPTION in filled
    row = only_row(pw, result)
    assert row["code"] == "would_post"
    assert (row["title"], row["description"]) == (FILLED_TITLE, FILLED_DESCRIPTION)
    assert row == with_template
    assert "post_waiting" not in result.stdout
    [plan] = pw.plans
    assert plan.post_template_since is None
