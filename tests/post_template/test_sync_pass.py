"""The post-fill pass in the sync that creates the pages (post-templates task 5.1).

Requirements 1.3, 6.1, 6.4, 6.7, 6.9, 6.10, 6.11, 6.12, 6.13, 7.6, 8.1, 8.2, 8.3.
The gate tests call ``cli._index_gate`` directly on built reports. Every other
test drives a real command through ``CliRunner`` over a synthetic ``.fit`` file
and the real index. The index and post-fill passes are wrapped to record their
calls, and the dashboard pass is replaced by a recorder that never runs it.
``run_pass`` or the index refresh is replaced only where a test needs a failure
the real pieces cannot produce (a raising pass, a refresh that reports errors or
raises), and one baseline replaces the post-fill pass with the identity function.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import time
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from fitdocs import cli as cli_module
from fitdocs import contract
from fitdocs.cli import app
from fitdocs.docmerge import extract_regions
from fitdocs.index import refresh as refresh_module
from fitdocs.index.refresh import IndexReport, Outcome
from fitdocs.post_template import engine as engine_module
from fitdocs.post_template import resolve as resolve_module
from fitdocs.post_template.engine import IndexGate
from fitdocs.query.command import QueryEnvironment
from tests.fixtures import builder

runner = CliRunner()

TODAY = date(2021, 10, 1)
TEMPLATE = """\
since = 2021-01-01
title = "Run {n}"

[vars.n]
sql = "SELECT count(*)::INT FROM pages WHERE start_time_local <= $as_of"
"""
ENTRYPOINTS = ["sync", "drain", "pull-sync"]


# --------------------------------------------------------------------------- #
# The world
# --------------------------------------------------------------------------- #


class World:
    """A data root, a source folder and an inbox, with the seams set."""

    def __init__(
        self, make: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = make("sync-pass")
        self.root = base / "data"
        self.root.mkdir()
        (self.root / "fitdocs.toml").write_text(
            "[tiles]\nenabled = false\n[inbox]\nsettle_seconds = 0\n",
            encoding="utf-8",
        )
        self.source = base / "source"
        self.source.mkdir()
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        home = base / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(cli_module, "_today", lambda: TODAY)
        self.monkeypatch = monkeypatch

    def args(self, entrypoint: str) -> list[str]:
        root = str(self.root)
        return {
            "sync": ["sync", str(self.source), "--no-prompt", "--out", root],
            "drain": ["sync", "--no-prompt", "--out", root],
            "pull-sync": ["pull", "--sync", "--no-prompt", "--out", root],
        }[entrypoint]

    def run(self, *args: str) -> Result:
        return runner.invoke(app, [*args, "--out", str(self.root)])

    def add_run(self, entrypoint: str, *, name: str = "run.fit") -> None:
        folder = self.source if entrypoint == "sync" else self.inbox
        (folder / name).write_bytes(builder.run_fit_bytes())

    def add_ride(self, entrypoint: str) -> None:
        folder = self.source if entrypoint == "sync" else self.inbox
        (folder / "ride.fit").write_bytes(builder.ride_fit_bytes())

    def sync(self, entrypoint: str = "sync") -> Result:
        return runner.invoke(app, self.args(entrypoint))

    def build_index(self) -> None:
        built = self.run("index")
        assert built.exit_code == 0, built.output

    def template(self, text: str = TEMPLATE) -> None:
        (self.root / "post-template.toml").write_text(text, encoding="utf-8")

    def pages(self) -> list[Path]:
        return sorted(
            path
            for path in (self.root / "workouts").glob("*.md")
            if path.name != "AGENTS.md"
        )

    def post_region(self, page: Path) -> str:
        return extract_regions(page.read_text(encoding="utf-8"))["post"]

    def tree(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }


@pytest.fixture
def world(
    per_test_directory: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> World:
    return World(per_test_directory, monkeypatch)


def post_lines(result: Result) -> list[str]:
    return [
        line for line in result.stdout.splitlines() if line.startswith("Post template")
    ]


def fill_stamp_count(region: str) -> int:
    return sum(
        contract.POST_FILL_STAMP.fullmatch(line) is not None
        for line in region.splitlines()
    )


@dataclasses.dataclass
class Calls:
    """The order of the passes and what they were given and returned."""

    events: list[tuple[str, Any]] = dataclasses.field(default_factory=list)

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def of(self, name: str) -> list[Any]:
        return [value for event, value in self.events if event == name]


def record_passes(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Wrap the index and post-fill passes; stub the dashboard pass with a recorder."""
    calls = Calls()
    index_pass = cli_module._run_index_pass
    fill_pass = cli_module._run_post_fill_pass

    def index(data_root: Path, *, handoff: Any) -> Any:
        returned = index_pass(data_root, handoff=handoff)
        calls.events.append(("index", (returned, handoff)))
        return returned

    def fill(data_root: Path, report: Any) -> Any:
        returned = fill_pass(data_root, report)
        calls.events.append(("fill", (report, returned)))
        return returned

    def dashboard(data_root: Path, report: Any) -> None:
        calls.events.append(("dashboard", report))

    monkeypatch.setattr(cli_module, "_run_index_pass", index)
    monkeypatch.setattr(cli_module, "_run_post_fill_pass", fill)
    monkeypatch.setattr(cli_module, "_run_dashboard_pass", dashboard)
    return calls


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

_OPEN_OUTCOMES = [Outcome.REFRESHED, Outcome.UNCHANGED, Outcome.BUILT]
_REFUSED = {
    Outcome.NOT_BUILT: ("the index is not built", "run fitdocs index"),
    Outcome.NEEDS_REBUILD: (
        "the index needs a rebuild",
        "run fitdocs index",
    ),
    Outcome.BUSY: (
        "the index is busy",
        "run fitdocs sync again once the other command has finished",
    ),
    Outcome.STAGED: ("an index replacement is staged", "run fitdocs index"),
    Outcome.FAILED: ("the index refresh failed", "run fitdocs index"),
}
_ERRORS_REASON = "the index refresh reported errors, listed above"
_ERRORS_NEXT = "fix what it lists, then run fitdocs sync again"


def _result(
    *,
    pages: tuple[tuple[str, str], ...] = (),
    producers: tuple[tuple[str, str], ...] = (),
) -> refresh_module.RefreshResult:
    return refresh_module.RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(),
        page_errors=pages,
        producer_errors=producers,
        left_out=(),
        corpus_refreshed=(),
        pages_held=0,
    )


def _report(outcome: Outcome, result: Any = None) -> IndexReport:
    return IndexReport(outcome, None, None, None, result)


def test_every_outcome_is_classified_by_the_gate() -> None:
    assert set(_OPEN_OUTCOMES) | set(_REFUSED) == set(Outcome)
    assert not set(_OPEN_OUTCOMES) & set(_REFUSED)


@pytest.mark.parametrize("outcome", _OPEN_OUTCOMES)
def test_a_clean_refresh_opens_the_gate(outcome: Outcome) -> None:
    assert cli_module._index_gate(_report(outcome, _result())) == IndexGate(
        open=True, reason=None, next_step=None
    )


@pytest.mark.parametrize("outcome", _OPEN_OUTCOMES)
def test_a_refresh_with_no_result_opens_the_gate(outcome: Outcome) -> None:
    assert cli_module._index_gate(_report(outcome)).open is True


@pytest.mark.parametrize("outcome", _OPEN_OUTCOMES)
@pytest.mark.parametrize(
    "result",
    [
        _result(pages=(("a.md", "boom"),)),
        _result(pages=(("a.md", "boom"), ("b.md", "bang"))),
        _result(producers=(("p", "boom"),)),
        _result(producers=(("p", "boom"), ("q", "bang"))),
        _result(pages=(("a.md", "x"),), producers=(("p", "y"),)),
    ],
    ids=["page", "pages", "producer", "producers", "both"],
)
def test_a_refresh_that_reported_errors_closes_the_gate(
    outcome: Outcome, result: refresh_module.RefreshResult
) -> None:
    assert cli_module._index_gate(_report(outcome, result)) == IndexGate(
        open=False, reason=_ERRORS_REASON, next_step=_ERRORS_NEXT
    )


@pytest.mark.parametrize("outcome", list(_REFUSED))
def test_a_refused_refresh_closes_the_gate_with_the_dashboards_wording(
    outcome: Outcome,
) -> None:
    reason, next_step = _REFUSED[outcome]
    assert reason == cli_module._DASHBOARD_NOT_REFRESHED_REASONS[outcome.value]
    # Errors never mask a refusal: the refusal is what stopped the refresh.
    clean = cli_module._index_gate(_report(outcome, _result()))
    broken = cli_module._index_gate(_report(outcome, _result(pages=(("a", "b"),))))
    assert clean == broken == IndexGate(open=False, reason=reason, next_step=next_step)


def test_a_refresh_that_raised_closes_the_gate() -> None:
    assert cli_module._index_gate(None) == IndexGate(
        open=False,
        reason="the index refresh raised an error",
        next_step="run fitdocs index",
    )


# --------------------------------------------------------------------------- #
# No template file: nothing imported, nothing printed, nothing changed
# --------------------------------------------------------------------------- #


def _unload_post_template(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [m for m in sys.modules if m.startswith("fitdocs.post_template")]:
        monkeypatch.delitem(sys.modules, name)


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_with_no_template_file_nothing_is_imported_or_printed(
    world: World, monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    world.add_run(entrypoint)
    world.build_index()
    _unload_post_template(monkeypatch)
    calls = record_passes(monkeypatch)

    result = world.sync(entrypoint)

    assert result.exit_code == 0, result.output
    assert calls.names() == ["index", "fill", "dashboard"]
    report = calls.of("index")[0][0]
    assert report is not None and report.outcome is Outcome.REFRESHED
    assert calls.of("fill")[0][1] is calls.of("fill")[0][0], "returns its input"
    assert [m for m in sys.modules if m.startswith("fitdocs.post_template")] == []
    assert post_lines(result) == []
    assert "post" not in result.output.lower().replace("posts", "")


def _normalize(text: str, world: World) -> str:
    return text.replace(str(world.root), "<root>")


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_with_no_template_file_output_and_bytes_equal_the_pass_removed(
    per_test_directory: Callable[[str], Path],
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    baseline = World(per_test_directory, monkeypatch)
    baseline.add_run(entrypoint)
    baseline.add_ride(entrypoint)
    baseline.build_index()
    with monkeypatch.context() as removed:
        spy = record_passes(removed)
        removed.setattr(cli_module, "_run_post_fill_pass", lambda root, report: report)
        before = baseline.sync(entrypoint)
        assert spy.names() == ["index", "dashboard"]

    subject = World(per_test_directory, monkeypatch)
    subject.add_run(entrypoint)
    subject.add_ride(entrypoint)
    subject.build_index()
    spy = record_passes(monkeypatch)
    after = subject.sync(entrypoint)

    assert spy.names() == ["index", "fill", "dashboard"]
    assert before.exit_code == after.exit_code == 0
    assert len(baseline.pages()) == len(subject.pages()) == 2
    assert _normalize(before.output, baseline) == _normalize(after.output, subject)
    assert baseline.tree() == subject.tree()


# --------------------------------------------------------------------------- #
# Filling
# --------------------------------------------------------------------------- #


def test_sync_fills_a_new_page_and_a_second_sync_says_nothing(world: World) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()

    first = world.sync()

    assert first.exit_code == 0, first.output
    assert post_lines(first) == ["Post template: 1 filled, 0 waiting."]
    lines = first.stdout.splitlines()
    filled = lines.index("Post template: 1 filled, 0 waiting.")
    refreshes = [i for i, line in enumerate(lines) if line.startswith("Index:")]
    assert len(refreshes) == 2 and refreshes[0] < filled < refreshes[1], lines
    [page] = world.pages()
    region = world.post_region(page)
    assert region.splitlines()[-1] == "Run 1"
    assert fill_stamp_count(region) == 1
    assert contract.POST_PLACEHOLDER not in region

    drift = world.run("query", "--schema")
    assert drift.exit_code == 0, drift.output
    assert "Behind: false" in drift.output
    assert "Added: 0" in drift.output and "Changed: 0" in drift.output

    snapshot = world.tree()
    second = world.sync()

    assert second.exit_code == 0, second.output
    assert post_lines(second) == []
    assert "filled" not in second.output
    assert world.tree() == snapshot

    # Nothing about posts, not even a blank line: the same sync with the
    # template file gone prints exactly the same.
    (world.root / "post-template.toml").unlink()
    third = world.sync()
    assert third.output == second.output


def test_the_second_index_refresh_follows_a_write_and_only_a_write(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()
    calls = record_passes(monkeypatch)

    world.sync()

    names = calls.names()
    # index, [fill wraps the second index], dashboard: the second index call
    # happens inside the fill pass, so it is recorded before "fill".
    assert names == ["index", "index", "fill", "dashboard"]
    first, second = (value[0] for value in calls.of("index"))
    assert calls.of("index")[0][1] is not None, "the first refresh carries the handoff"
    assert calls.of("index")[1][1] is None, "the second refresh has no handoff"
    assert first is not second
    fill_input, fill_output = calls.of("fill")[0]
    assert fill_input is first
    assert fill_output is second
    assert calls.of("dashboard") == [second]

    calls.events.clear()
    world.sync()

    assert calls.names() == ["index", "fill", "dashboard"]
    [(only, _)] = calls.of("index")
    assert calls.of("fill")[0][1] is only is calls.of("dashboard")[0]


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_every_sync_path_fills_the_page_it_creates(
    world: World, entrypoint: str
) -> None:
    world.template()
    world.add_run(entrypoint)
    world.build_index()

    result = world.sync(entrypoint)

    assert result.exit_code == 0, result.output
    assert post_lines(result) == ["Post template: 1 filled, 0 waiting."]
    [page] = world.pages()
    assert world.post_region(page).splitlines()[-1] == "Run 1"


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_the_dashboard_pass_receives_the_second_index_report(
    world: World, monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    world.template()
    world.add_run(entrypoint)
    world.build_index()
    (world.root / "dashboards").mkdir()
    seen: list[IndexReport | None] = []
    monkeypatch.setattr(
        cli_module,
        "_run_dashboard_pass",
        lambda root, report: seen.append(report),
    )
    returned: list[IndexReport | None] = []
    original = cli_module._run_index_pass

    def index(data_root: Path, *, handoff: Any) -> IndexReport | None:
        report = original(data_root, handoff=handoff)
        returned.append(report)
        return report

    monkeypatch.setattr(cli_module, "_run_index_pass", index)

    result = world.sync(entrypoint)

    assert result.exit_code == 0, result.output
    assert len(returned) == 2
    assert seen[0] is returned[1]
    assert seen[0] is not returned[0]
    assert len(seen) == 1


# --------------------------------------------------------------------------- #
# The gate, end to end
# --------------------------------------------------------------------------- #


def test_an_unbuilt_index_gives_one_line_and_leaves_the_page_waiting(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    calls = record_passes(monkeypatch)

    result = world.sync()

    assert result.exit_code == 0, result.output
    assert post_lines(result) == [
        "Post template: 1 waiting; the index is not built. run fitdocs index."
    ]
    [page] = world.pages()
    assert world.post_region(page) == contract.POST_PLACEHOLDER
    assert calls.names() == ["index", "fill", "dashboard"]
    report = calls.of("index")[0][0]
    assert report.outcome is Outcome.NOT_BUILT
    assert calls.of("dashboard") == [report]


@pytest.mark.parametrize(
    "errors",
    [
        {"pages": (("workouts/x.md", "boom"),)},
        {"producers": (("producer", "boom"),)},
    ],
    ids=["page-error", "data-source-error"],
)
def test_an_index_with_errors_gives_one_line_and_leaves_the_page_waiting(
    world: World, monkeypatch: pytest.MonkeyPatch, errors: dict[str, Any]
) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()
    real = refresh_module.refresh_after_command

    def refresh(*args: Any, **kwargs: Any) -> IndexReport:
        report = real(*args, **kwargs)
        assert report.result is not None
        return dataclasses.replace(
            report, result=dataclasses.replace(report.result, **_fields(errors))
        )

    monkeypatch.setattr(refresh_module, "refresh_after_command", refresh)

    result = world.sync()

    assert result.exit_code == 0, result.output
    assert post_lines(result) == [
        "Post template: 1 waiting; the index refresh reported errors, "
        "listed above. fix what it lists, then run fitdocs sync again."
    ]
    [page] = world.pages()
    assert world.post_region(page) == contract.POST_PLACEHOLDER


def _fields(errors: Mapping[str, Any]) -> dict[str, Any]:
    return {
        {"pages": "page_errors", "producers": "producer_errors"}[key]: value
        for key, value in errors.items()
    }


def test_a_refresh_that_raised_leaves_the_page_waiting_and_says_so_once(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()

    def refresh(*args: Any, **kwargs: Any) -> IndexReport:
        raise RuntimeError("synthetic refresh failure")

    monkeypatch.setattr(refresh_module, "refresh_after_command", refresh)
    calls = record_passes(monkeypatch)

    result = world.sync()

    assert result.exit_code == 0, result.output
    assert post_lines(result) == [
        "Post template: 1 waiting; the index refresh raised an error. "
        "run fitdocs index."
    ]
    assert calls.names() == ["index", "fill", "dashboard"]
    assert calls.of("dashboard") == [None]
    [page] = world.pages()
    assert world.post_region(page) == contract.POST_PLACEHOLDER


def test_a_closed_gate_is_what_run_pass_receives(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    seen: list[Any] = []
    real = engine_module.run_pass

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(engine_module, "run_pass", spy)

    world.sync()

    [(args, kwargs)] = seen
    assert args[0] == world.root
    assert kwargs["gate"] == IndexGate(
        open=False, reason="the index is not built", next_step="run fitdocs index"
    )


# --------------------------------------------------------------------------- #
# What the pass is wired to
# --------------------------------------------------------------------------- #


def test_the_pass_is_given_the_real_resolver_opener_and_clock(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()
    seen: dict[str, Any] = {}
    real_pass = engine_module.run_pass
    real_open = resolve_module.open_resolver

    def spy_pass(*args: Any, **kwargs: Any) -> Any:
        seen["monotonic"] = kwargs["monotonic"]
        seen["template_path"] = args[1].path
        seen["gate"] = kwargs["gate"]
        return real_pass(*args, **kwargs)

    def spy_open(data_root: Path, env: QueryEnvironment) -> Any:
        seen["open"] = (data_root, env)
        return real_open(data_root, env)

    monkeypatch.setattr(engine_module, "run_pass", spy_pass)
    monkeypatch.setattr(resolve_module, "open_resolver", spy_open)

    result = world.sync()

    assert result.exit_code == 0, result.output
    assert seen["monotonic"] is time.monotonic
    assert seen["template_path"] == world.root / "post-template.toml"
    assert seen["gate"] == IndexGate(open=True, reason=None, next_step=None)
    data_root, env = seen["open"]
    assert data_root == world.root
    assert isinstance(env, QueryEnvironment)
    assert env.environ is os.environ
    assert env.home == Path.home()
    assert env.pid == os.getpid()
    assert env.monotonic is time.monotonic


# --------------------------------------------------------------------------- #
# Failures stay on one line and never change the exit code
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("failing", [False, True], ids=["clean-sync", "failing-sync"])
def test_a_refused_template_is_one_line_and_changes_nothing(
    world: World, monkeypatch: pytest.MonkeyPatch, failing: bool
) -> None:
    world.template('since = 2021-01-01\ntitle = "Run {nope}"\nzzz = 1\n')
    world.add_run("sync")
    if failing:
        (world.source / "bad.fit").write_bytes(b"not a fit file")
    world.build_index()
    calls = record_passes(monkeypatch)

    result = world.sync()

    assert result.exit_code == (1 if failing else 0), result.output
    [line] = post_lines(result)
    assert line.startswith("Post template: not filled; ")
    assert _normalize(line, world) == (
        "Post template: not filled; <root>/post-template.toml: zzz: "
        "not a recognized key (and 1 more); "
        "run fitdocs post-template check to see every problem."
    )
    [page] = world.pages()
    assert world.post_region(page) == contract.POST_PLACEHOLDER
    assert calls.names() == ["index", "fill", "dashboard"]
    report = calls.of("index")[0][0]
    assert calls.of("dashboard") == [report]


@pytest.mark.parametrize("failing", [False, True], ids=["clean-sync", "failing-sync"])
def test_an_error_in_the_pass_is_one_line_and_keeps_the_exit_code(
    world: World, monkeypatch: pytest.MonkeyPatch, failing: bool
) -> None:
    world.template()
    world.add_run("sync")
    if failing:
        (world.source / "bad.fit").write_bytes(b"not a fit file")
    world.build_index()

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("synthetic\npass  failure")

    monkeypatch.setattr(engine_module, "run_pass", boom)
    calls = record_passes(monkeypatch)

    result = world.sync()

    assert result.exit_code == (1 if failing else 0), result.output
    assert post_lines(result) == [
        "Post template: not filled; RuntimeError: synthetic pass failure."
    ]
    assert calls.names() == ["index", "fill", "dashboard"]
    report = calls.of("index")[0][0]
    assert calls.of("fill")[0][1] is report, "an error returns the input report"
    assert calls.of("dashboard") == [report]


def test_an_interrupt_in_the_pass_propagates(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()
    interrupt = KeyboardInterrupt()

    def stop(*args: Any, **kwargs: Any) -> Any:
        raise interrupt

    monkeypatch.setattr(engine_module, "run_pass", stop)
    calls = record_passes(monkeypatch)

    result = world.sync()

    assert result.exit_code == 130
    assert "not filled" not in result.output
    assert "dashboard" not in calls.names()


def test_a_system_exit_in_the_pass_is_not_swallowed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.template()
    world.add_run("sync")
    world.build_index()

    def leave(*args: Any, **kwargs: Any) -> Any:
        raise SystemExit(9)

    monkeypatch.setattr(engine_module, "run_pass", leave)

    result = world.sync()

    assert result.exit_code == 9
    assert post_lines(result) == []


# --------------------------------------------------------------------------- #
# What a fill survives
# --------------------------------------------------------------------------- #


def _fill_first_page(world: World) -> tuple[Path, str]:
    world.template()
    world.add_run("sync")
    world.build_index()
    assert world.sync().exit_code == 0
    [page] = world.pages()
    region = world.post_region(page)
    assert fill_stamp_count(region) == 1
    return page, region


def test_regen_with_the_index_deleted_keeps_the_filled_region(
    world: World, per_test_directory: Callable[[str], Path]
) -> None:
    page, region = _fill_first_page(world)
    index_dir = Path(os.environ["FITDOCS_INDEX_DIR"])
    assert index_dir.exists() and any(index_dir.iterdir())
    for path in sorted(index_dir.rglob("*"), reverse=True):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    assert not any(index_dir.iterdir())

    result = world.run("regen")

    assert result.exit_code == 0, result.output
    assert post_lines(result) == []
    [after] = world.pages()
    assert after == page
    assert world.post_region(after) == region


def test_a_later_workout_and_a_load_recompute_leave_the_filled_region(
    world: World,
) -> None:
    page, region = _fill_first_page(world)
    world.add_ride("sync")

    later = world.sync()

    assert later.exit_code == 0, later.output
    assert len(world.pages()) == 2
    assert post_lines(later) == ["Post template: 1 filled, 0 waiting."]
    assert world.post_region(page) == region
    other = next(p for p in world.pages() if p != page)
    assert world.post_region(other).splitlines()[-1] == "Run 2"

    loaded = world.run("load", "--recompute", "--no-prompt")

    assert loaded.exit_code == 0, loaded.output
    assert post_lines(loaded) == []
    assert world.post_region(page) == region
    assert world.post_region(other).splitlines()[-1] == "Run 2"


def test_regen_and_load_never_call_the_post_fill_pass(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fill_first_page(world)
    world.build_index()
    world.template(TEMPLATE.replace("Run {n}", "Changed {n}"))
    calls = record_passes(monkeypatch)

    regen = world.run("regen")
    loaded = world.run("load", "--no-prompt")

    assert regen.exit_code == loaded.exit_code == 0
    assert calls.of("fill") == []
    assert "fill" not in calls.names()


def test_a_template_that_is_a_dangling_symlink_is_a_refused_template(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    (world.root / "post-template.toml").symlink_to(world.root / "nowhere.toml")
    world.add_run("sync")
    world.build_index()

    result = world.sync()

    assert result.exit_code == 0, result.output
    assert [_normalize(line, world) for line in post_lines(result)] == [
        "Post template: not filled; <root>/post-template.toml: "
        "is a symlink, not a file; "
        "run fitdocs post-template check to see every problem."
    ]
    [page] = world.pages()
    assert world.post_region(page) == contract.POST_PLACEHOLDER


@pytest.mark.parametrize(
    ("extra", "suffix"),
    [("", ""), ("yyy = 2\nxxx = 3\n", " (and 2 more)")],
    ids=["one-problem", "three-problems"],
)
def test_the_refused_line_counts_the_problems_it_leaves_out(
    world: World, extra: str, suffix: str
) -> None:
    world.template(f'since = 2021-01-01\ntitle = "T"\nzzz = 1\n{extra}')
    world.add_run("sync")
    world.build_index()

    result = world.sync()

    assert [_normalize(line, world) for line in post_lines(result)] == [
        "Post template: not filled; <root>/post-template.toml: zzz: "
        f"not a recognized key{suffix}; "
        "run fitdocs post-template check to see every problem."
    ]
