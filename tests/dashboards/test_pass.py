"""The dashboard pass chained after the index refresh of the writing commands.

Every test drives a real command through ``CliRunner`` with the index refresh
monkeypatched to a chosen outcome (the entry-point harness of
``tests/index/test_cli_post_pass.py``: same five entry points, same refresh
seam) and the chart source replaced by a ``FakeSource``, so no index is read.
The pass is observed on a data root holding one dashboard page whose second
chart is the one that matters.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from fitdocs import cli as cli_module
from fitdocs.cli import app
from fitdocs.dashboards import engine
from fitdocs.dashboards.source import SourceOpener
from fitdocs.index import refresh as refresh_module
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.refresh import IndexReport, Outcome, ProgressCallback
from tests.dashboards._helpers import (
    FakeSource,
    MustNotOpen,
    assert_untouched,
    category_number_data,
    directive_block,
    page_text,
    snapshot_of,
    write_page,
)
from tests.fixtures import builder

runner = CliRunner()

ENTRYPOINTS = ["sync", "drain", "pull-sync", "regen", "load"]
TODAY = date(2031, 4, 5)
SQL_FIRST = "select first"
SQL_SECOND = "select second"

# Every Outcome member, classified exactly once. A new member has no entry
# here, so test_the_table_classifies_every_outcome_member reds until it is.
RUNS: dict[Outcome, bool] = {
    Outcome.REFRESHED: True,
    Outcome.UNCHANGED: True,
    Outcome.BUILT: True,
    Outcome.NOT_BUILT: False,
    Outcome.NEEDS_REBUILD: False,
    Outcome.BUSY: False,
    Outcome.STAGED: False,
    Outcome.FAILED: False,
}
RUNNING = [outcome for outcome, runs in RUNS.items() if runs]
NOT_RUNNING = [outcome for outcome, runs in RUNS.items() if not runs]

# The reason each refusing outcome gives, and the one a raising refresh gives.
REASONS: dict[Outcome, str] = {
    Outcome.NOT_BUILT: "the index is not built",
    Outcome.NEEDS_REBUILD: "the index needs a rebuild",
    Outcome.BUSY: "the index is busy",
    Outcome.STAGED: "an index replacement is staged",
    Outcome.FAILED: "the index refresh failed",
}
RAISED_REASON = "the index refresh raised an error"


def directive_for(chart_id: str, sql: str) -> str:
    return directive_block(
        [
            ("id", chart_id),
            ("kind", "bar"),
            ("mode", "relative"),
            ("title", f"Title of {chart_id}"),
            ("sql", f"|\n  {sql}"),
            ("channels", "\n  x: label\n  y: value"),
        ]
    )


def staged_page() -> str:
    return page_text(
        directive_for("first", SQL_FIRST), directive_for("second", SQL_SECOND)
    )


def fetched_as(sql: str) -> str:
    return sql + "\n"


class Fixture:
    """A data root for one entry point, with the page staged and the seams set."""

    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str
    ) -> None:
        self.entrypoint = entrypoint
        self.root = tmp_path / "data"
        self.root.mkdir(parents=True)
        (self.root / "fitdocs.toml").write_text(
            "[inbox]\nsettle_seconds = 0\n", encoding="utf-8"
        )
        self.source_dir = tmp_path / "source"
        self.source_dir.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        self.index_cache = tmp_path / "index-cache"
        monkeypatch.setenv("FITDOCS_INDEX_DIR", str(self.index_cache))
        monkeypatch.setattr(cli_module, "_today", lambda: TODAY)
        self.chart_source = FakeSource()
        self.chart_source.queue(
            fetched_as(SQL_FIRST), category_number_data([("a", 3.0), ("b", 1.0)])
        )
        self.chart_source.queue(
            fetched_as(SQL_SECOND),
            category_number_data([("x", 5.0), ("y", 7.0), ("z", 6.0)]),
        )
        self.blocked = MustNotOpen()
        self.monkeypatch = monkeypatch

    def args(self) -> list[str]:
        root = str(self.root)
        if self.entrypoint == "sync":
            return ["sync", str(self.source_dir), "--out", root]
        if self.entrypoint == "drain":
            return ["sync", "--no-prompt", "--out", root]
        if self.entrypoint == "pull-sync":
            return ["pull", "--sync", "--no-prompt", "--out", root]
        if self.entrypoint == "regen":
            return ["regen", "--out", root]
        return ["load", "--out", root]

    def stage(self) -> Path:
        return write_page(self.root, "p", staged_page())

    def use_source(self, opener: SourceOpener) -> None:
        def source_opener(data_root: Path, env: object) -> SourceOpener:
            return opener

        self.monkeypatch.setattr(
            "fitdocs.dashboards.binding.source_opener", source_opener
        )

    def refresh_gives(self, outcome: Outcome | None) -> None:
        """Replace the index refresh: ``None`` raises, anything else reports."""

        def refresh(
            data_root: Path,
            *,
            environ: Mapping[str, str],
            home: Path,
            handoff: HandoffCollector | None,
            today: date,
            progress: ProgressCallback | None,
        ) -> IndexReport:
            if outcome is None:
                raise RuntimeError("synthetic refresh failure")
            return IndexReport(outcome, None, None, None, None)

        self.monkeypatch.setattr(refresh_module, "refresh_after_command", refresh)

    def run(self) -> Result:
        return runner.invoke(app, self.args())

    def dashboard_files(self) -> dict[str, tuple[bytes, int]]:
        """Bytes and mtime of every dashboards/ file but the generated AGENTS.md.

        sync, drain, pull --sync and regen write that declaration themselves,
        pass or no pass; load does not.
        """
        files = snapshot_of(self.root / "dashboards")
        files.pop("AGENTS.md", None)
        return files

    def assets(self) -> list[str]:
        directory = self.root / "dashboards" / "assets"
        if not directory.exists():
            return []
        return sorted(
            path.relative_to(directory).as_posix() for path in directory.rglob("*.svg")
        )


@pytest.fixture(params=ENTRYPOINTS)
def fixture(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Fixture:
    return Fixture(tmp_path, monkeypatch, request.param)


def dashboard_lines(result: Result) -> list[str]:
    return [
        line for line in result.output.splitlines() if line.startswith("Dashboards")
    ]


# -- the partition ---------------------------------------------------------------


def test_the_table_classifies_every_outcome_member() -> None:
    assert set(RUNS) == set(Outcome)
    assert set(REASONS) == set(NOT_RUNNING)
    assert RUNNING and NOT_RUNNING


@pytest.mark.parametrize("outcome", RUNNING, ids=lambda outcome: outcome.value)
def test_a_successful_refresh_runs_the_pass_over_the_page(
    fixture: Fixture, outcome: Outcome
) -> None:
    page = fixture.stage()
    before = page.read_bytes()
    assert fixture.assets() == []
    fixture.refresh_gives(outcome)
    fixture.use_source(fixture.chart_source.opener())

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert fixture.assets() == ["p/first.svg", "p/second.svg"]
    assert page.read_bytes() != before
    assert "<!-- fitdocs:begin:chart:second -->" in page.read_text(encoding="utf-8")
    assert sorted(call.sql for call in fixture.chart_source.calls) == [
        fetched_as(SQL_FIRST),
        fetched_as(SQL_SECOND),
    ]
    assert dashboard_lines(result) == ["Dashboards: 2 rendered, 0 unchanged, 0 failed."]
    assert result.output.endswith("0 failed.\n")
    assert {call.today for call in fixture.chart_source.calls} == {TODAY}


@pytest.mark.parametrize("outcome", NOT_RUNNING, ids=lambda outcome: outcome.value)
def test_a_refresh_that_did_not_succeed_changes_nothing_and_says_so_once(
    fixture: Fixture, outcome: Outcome
) -> None:
    fixture.stage()
    fixture.refresh_gives(outcome)
    fixture.use_source(fixture.blocked)
    before = fixture.dashboard_files()
    assert list(before) == ["p.md"]
    assert not fixture.index_cache.exists()

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert dashboard_lines(result) == [
        f"Dashboards: not refreshed; {REASONS[outcome]}."
    ]
    assert fixture.blocked.attempts == 0
    assert_untouched(before, fixture.dashboard_files())
    assert not fixture.index_cache.exists(), "the pass built an index"


def test_a_raising_refresh_changes_nothing_and_says_so_once(fixture: Fixture) -> None:
    fixture.stage()
    fixture.refresh_gives(None)
    fixture.use_source(fixture.blocked)
    before = fixture.dashboard_files()
    assert list(before) == ["p.md"]
    assert not fixture.index_cache.exists()

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert "Index: not refreshed; RuntimeError: synthetic refresh failure." in (
        result.output
    )
    assert dashboard_lines(result) == [f"Dashboards: not refreshed; {RAISED_REASON}."]
    assert fixture.blocked.attempts == 0
    assert_untouched(before, fixture.dashboard_files())
    assert not fixture.index_cache.exists(), "the pass built an index"


@pytest.mark.parametrize(
    "outcome",
    [*RUNNING, *NOT_RUNNING, None],
    ids=lambda o: getattr(o, "value", "raised"),
)
def test_with_no_dashboard_page_the_pass_prints_nothing(
    fixture: Fixture, outcome: Outcome | None
) -> None:
    assert not (fixture.root / "dashboards").exists()
    fixture.refresh_gives(outcome)
    fixture.use_source(fixture.blocked)

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert "Dashboards" not in result.output
    assert fixture.blocked.attempts == 0
    assert fixture.assets() == []


# -- the pass never changes the exit code ------------------------------------------


def _exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
    name: str,
    *,
    bad_file: bool,
    pass_raises: bool,
) -> tuple[int, Result]:
    fixture = Fixture(tmp_path / name, monkeypatch, entrypoint)
    if bad_file:
        (fixture.source_dir / "bad.fit").write_bytes(builder.non_fit_bytes())
    fixture.stage()
    fixture.refresh_gives(Outcome.REFRESHED)
    fixture.use_source(fixture.chart_source.opener())
    if pass_raises:

        def failing(request: object, open_source: object) -> object:
            raise RuntimeError("synthetic pass failure")

        monkeypatch.setattr(engine, "run_dashboards", failing)
    else:
        monkeypatch.setattr(
            cli_module, "_run_dashboard_pass", lambda data_root, index_report: None
        )
    result = fixture.run()
    monkeypatch.undo()
    return result.exit_code, result


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_a_raising_pass_prints_one_line_and_keeps_the_exit_code_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    without, _ = _exit_code(
        tmp_path, monkeypatch, entrypoint, "without", bad_file=False, pass_raises=False
    )
    with_pass, result = _exit_code(
        tmp_path, monkeypatch, entrypoint, "raising", bad_file=False, pass_raises=True
    )
    assert without == 0
    assert with_pass == without
    assert dashboard_lines(result) == [
        "Dashboards: not refreshed; RuntimeError: synthetic pass failure."
    ]


def test_a_raising_pass_keeps_a_failing_command_failing_with_the_same_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    without, _ = _exit_code(
        tmp_path, monkeypatch, "sync", "without", bad_file=True, pass_raises=False
    )
    with_pass, result = _exit_code(
        tmp_path, monkeypatch, "sync", "raising", bad_file=True, pass_raises=True
    )
    assert without == 1
    assert with_pass == without
    assert len(dashboard_lines(result)) == 1


def test_a_pass_that_cannot_decide_whether_pages_exist_reports_and_keeps_the_code(
    fixture: Fixture,
) -> None:
    fixture.stage()
    fixture.refresh_gives(Outcome.REFRESHED)
    fixture.use_source(fixture.chart_source.opener())

    def failing(data_root: Path) -> bool:
        raise OSError("synthetic listing failure")

    fixture.monkeypatch.setattr(engine, "has_dashboards", failing)
    result = fixture.run()
    assert result.exit_code == 0, result.output
    assert dashboard_lines(result) == [
        "Dashboards: not refreshed; OSError: synthetic listing failure."
    ]
    assert fixture.assets() == []


# -- an interrupt is not swallowed -------------------------------------------------


def _index_report() -> IndexReport:
    return IndexReport(Outcome.REFRESHED, None, None, None, None)


@pytest.mark.parametrize("report", [_index_report(), None], ids=["report", "none"])
@pytest.mark.parametrize("interrupt", [KeyboardInterrupt("keep me"), SystemExit(7)])
def test_an_interrupt_in_the_pass_propagates_with_its_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt: BaseException,
    report: IndexReport | None,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    write_page(root, "p", staged_page())

    def interrupted(data_root: Path) -> bool:
        raise interrupt

    monkeypatch.setattr(engine, "has_dashboards", interrupted)
    with pytest.raises(type(interrupt)) as raised:
        cli_module._run_dashboard_pass(root, report)
    assert raised.value is interrupt


def test_an_interrupt_while_drawing_propagates_with_its_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    write_page(root, "p", staged_page())
    interrupt = KeyboardInterrupt("keep me too")

    def interrupted(request: object, open_source: object) -> object:
        raise interrupt

    monkeypatch.setattr(engine, "run_dashboards", interrupted)
    with pytest.raises(KeyboardInterrupt) as raised:
        cli_module._run_dashboard_pass(root, _index_report())
    assert raised.value is interrupt


# -- where the pass sits ------------------------------------------------------------


def test_the_index_pass_returns_what_the_dashboard_pass_receives(
    fixture: Fixture,
) -> None:
    fixture.refresh_gives(Outcome.BUSY)
    events: list[tuple[str, object]] = []
    original = cli_module._run_index_pass

    def index_pass(data_root: Path, *, handoff: HandoffCollector | None) -> object:
        returned = original(data_root, handoff=handoff)
        events.append(("index", returned))
        return returned

    def dashboard_pass(data_root: Path, index_report: object) -> None:
        events.append(("dashboard", index_report))

    fixture.monkeypatch.setattr(cli_module, "_run_index_pass", index_pass)
    fixture.monkeypatch.setattr(cli_module, "_run_dashboard_pass", dashboard_pass)

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert [name for name, _ in events] == ["index", "dashboard"]
    assert events[0][1] == IndexReport(Outcome.BUSY, None, None, None, None)
    assert events[1][1] is events[0][1]


def test_the_dashboard_pass_gets_none_when_the_index_pass_raised(
    fixture: Fixture,
) -> None:
    fixture.refresh_gives(None)
    received: list[object] = []
    fixture.monkeypatch.setattr(
        cli_module,
        "_run_dashboard_pass",
        lambda data_root, index_report: received.append((data_root, index_report)),
    )
    result = fixture.run()
    assert result.exit_code == 0, result.output
    assert received == [(fixture.root, None)]


def _spied(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, object]]:
    calls: list[tuple[Path, object]] = []
    monkeypatch.setattr(
        cli_module,
        "_run_dashboard_pass",
        lambda data_root, index_report: calls.append((data_root, index_report)),
    )
    return calls


NON_CHAINING: dict[str, Callable[[Path], list[str]]] = {
    "history": lambda root: ["history", "--out", str(root)],
    "plan": lambda root: ["plan", "--out", str(root)],
    "check": lambda root: ["check", "--out", str(root)],
    "index": lambda root: ["index", "--out", str(root)],
    "query": lambda root: ["query", "select 1 as one", "--out", str(root)],
}


@pytest.mark.parametrize("command", sorted(NON_CHAINING))
def test_the_other_commands_never_call_the_dashboard_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    fixture = Fixture(tmp_path, monkeypatch, "sync")
    fixture.stage()
    fixture.use_source(fixture.blocked)
    if command in ("query", "check"):
        # query needs a built index; check needs the declarations a sync writes.
        for prior in (["sync", str(fixture.source_dir)], ["index"]):
            made = runner.invoke(app, [*prior, "--out", str(fixture.root)])
            assert made.exit_code == 0, made.output
    calls = _spied(monkeypatch)

    result = runner.invoke(app, NON_CHAINING[command](fixture.root))

    assert result.exit_code == 0, result.output
    if command == "query":
        assert "one" in result.output
    assert calls == []
    assert fixture.blocked.attempts == 0


def test_the_spy_sees_a_chaining_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch, "sync")
    fixture.stage()
    calls = _spied(monkeypatch)
    result = fixture.run()
    assert result.exit_code == 0, result.output
    assert [root for root, _ in calls] == [fixture.root]


# -- what the pass prints -------------------------------------------------------------


def test_a_pass_that_wrote_nothing_and_found_nothing_prints_nothing(
    fixture: Fixture,
) -> None:
    fixture.stage()
    fixture.refresh_gives(Outcome.UNCHANGED)
    fixture.use_source(fixture.chart_source.opener())
    first = fixture.run()
    assert dashboard_lines(first) == ["Dashboards: 2 rendered, 0 unchanged, 0 failed."]
    page = fixture.root / "dashboards" / "p.md"
    settled = page.read_bytes()

    second = fixture.run()

    assert second.exit_code == 0, second.output
    assert page.read_bytes() == settled
    assert len(fixture.chart_source.calls) == 4, "the second run did not draw"
    fixture.monkeypatch.setattr(
        cli_module, "_run_dashboard_pass", lambda data_root, index_report: None
    )
    without = fixture.run()
    assert second.output == without.output
    assert "Dashboards" not in second.output


def test_a_chart_problem_is_printed_and_does_not_change_the_exit_code(
    fixture: Fixture,
) -> None:
    broken = directive_for("broken", SQL_FIRST).replace("title: Title of broken\n", "")
    assert "title:" not in broken
    page = write_page(
        fixture.root, "p", page_text(broken, directive_for("ok", SQL_SECOND))
    )
    before = page.read_bytes()
    fixture.refresh_gives(Outcome.BUILT)
    fixture.use_source(fixture.chart_source.opener())

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert dashboard_lines(result) == ["Dashboards: 1 rendered, 0 unchanged, 1 failed."]
    assert "missing_key" in result.output
    assert page.read_bytes() != before
    assert fixture.assets() == ["p/ok.svg"]


def test_a_key_that_looks_like_an_emoji_code_prints_verbatim(fixture: Fixture) -> None:
    odd = directive_for("odd", SQL_FIRST).replace("-->\n", '":a:": 1\n-->\n')
    assert '":a:": 1' in odd
    write_page(fixture.root, "p", page_text(directive_for("ok", SQL_SECOND), odd))
    fixture.refresh_gives(Outcome.REFRESHED)
    fixture.use_source(fixture.chart_source.opener())

    result = fixture.run()

    assert result.exit_code == 0, result.output
    assert "The directive key `:a:` is not accepted." in result.output
    assert "\U0001f170" not in result.output


def test_an_error_message_with_a_newline_stays_on_one_line(fixture: Fixture) -> None:
    fixture.stage()
    fixture.refresh_gives(Outcome.REFRESHED)
    fixture.use_source(fixture.chart_source.opener())

    def failing(request: object, open_source: object) -> object:
        raise RuntimeError("first line\n  :a:   second")

    fixture.monkeypatch.setattr(engine, "run_dashboards", failing)
    result = fixture.run()
    assert dashboard_lines(result) == [
        "Dashboards: not refreshed; RuntimeError: first line :a: second."
    ]
