"""Morning report text and native command chaining over synthetic inputs."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.index.build import run_index_command
from fitdocs.morning import engine
from fitdocs.morning.block import MorningInputs, render_region
from fitdocs.morning.docedit import read_morning, replace_morning
from fitdocs.morning.engine import MorningPage, MorningReport, PageOutcome
from fitdocs.sync import sync
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileStore
from fitdocs.wellness import DEFAULT_WELLNESS_SETTINGS, Metric, read_series
from fitdocs.wellness.engine import rebuild_series
from fitdocs.wellness.intake import Archived, Identified, archive_identified, identify
from tests.fixtures.builder import run_fit_bytes
from tests.fixtures.zone import system_zone
from tests.morning.builders import series_value, stage_series, wellness_series
from tests.wellness.builders_intervals import intervals_delivery_bytes, intervals_record

runner = CliRunner()


@pytest.fixture(autouse=True)
def _cli_zone_is_utc() -> Iterator[None]:
    """Pin the CLI's system zone to the UTC the scenarios write pages in.

    Otherwise ``fitdocs regen`` dates each page in the host's zone, and a page
    fitdocs named follows its changed local start to a new filename
    (activity-identity A2.1), so the scenario's page path would depend on
    where the suite runs.
    """
    with system_zone("UTC"):
        yield


DAY = date(2021, 9, 8)
STALE = "stale morning content that the current series replaces"


def _root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "data"
    root.mkdir()
    (root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n[inbox]\nsettle_seconds = 0\n"
    )
    source = tmp_path / "source"
    source.mkdir()
    return root, source


def _stage(root: Path) -> None:
    stage_series(
        root,
        wellness_series(
            [
                series_value(
                    DAY,
                    47,
                    metric=Metric.RESTING_HR_BPM,
                    source="intervals-icu",
                    canonical=True,
                )
            ]
        ),
    )


def _scenario(tmp_path: Path, flow: str) -> tuple[Path, Path, Path]:
    root, source = _root(tmp_path)
    (source / "run.fit").write_bytes(run_fit_bytes())
    sync(
        source,
        root,
        athlete=None,
        tz=UTC,
        tiles=TileStore(root, replace(DEFAULT_TILE_SETTINGS, enabled=False)),
    )
    page = next(p for p in (root / "workouts").glob("*.md") if p.name != "AGENTS.md")
    page.write_text(replace_morning(page.read_text(), STALE))
    if flow == "source":
        _stage(root)
    else:
        delivery = tmp_path / "wellness.json"
        delivery.write_bytes(
            intervals_delivery_bytes([intervals_record(DAY, restingHR=47)])
        )
        identified = identify(delivery)
        if not isinstance(identified, Identified):
            raise AssertionError(identified)
        archived = archive_identified(root, delivery, identified, None)
        if not isinstance(archived, Archived):
            raise AssertionError(archived)
    return root, source, page


def _standalone_scenario(tmp_path: Path, command: str) -> tuple[Path, Path]:
    root, _source, page = _scenario(tmp_path, "drain")
    rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=True)
    if command == "plan":
        plans = root / "plans"
        plans.mkdir()
        fixture = Path(__file__).resolve().parents[1] / "plans/fixtures/minimal.toml"
        (plans / "minimal.toml").write_bytes(fixture.read_bytes())
    if command == "query":
        run_index_command(
            root,
            environ=os.environ,
            home=Path.home(),
            athlete=None,
            today=DAY,
            rebuild=False,
            progress=None,
        )
    return root, page


def _invoke(root: Path, source: Path, flow: str) -> Any:
    args = (
        ["sync", str(source), "--no-prompt"]
        if flow == "source"
        else ["sync", "--no-prompt"]
        if flow == "drain"
        else ["regen"]
    )
    return runner.invoke(cli.app, [*args, "--out", str(root)])


def _report(
    pages: tuple[MorningPage, ...] = (),
    *,
    without: int = 0,
    values: bool = True,
    unavailable: str | None = None,
) -> MorningReport:
    return MorningReport(
        tuple(sorted(pages, key=lambda page: page.doc)),
        3,
        without,
        2,
        values,
        unavailable,
    )


def _pages(outcome: PageOutcome, count: int) -> tuple[MorningPage, ...]:
    return tuple(
        MorningPage(f"workouts/{outcome.value}-{i}.md", outcome, None)
        for i in range(count)
    )


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (_report(_pages(PageOutcome.UPDATED, 1)), ["Morning of: 1 page updated."]),
        (_report(_pages(PageOutcome.UPDATED, 2)), ["Morning of: 2 pages updated."]),
        (_report(_pages(PageOutcome.REMOVED, 1)), ["Morning of: 1 block removed."]),
        (_report(_pages(PageOutcome.REMOVED, 2)), ["Morning of: 2 blocks removed."]),
        (
            _report(_pages(PageOutcome.UPDATED, 2) + _pages(PageOutcome.REMOVED, 1)),
            ["Morning of: 2 pages updated, 1 block removed."],
        ),
        (
            _report(_pages(PageOutcome.UPDATED, 1) + _pages(PageOutcome.REMOVED, 2)),
            ["Morning of: 1 page updated, 2 blocks removed."],
        ),
        (
            _report(without=1),
            [
                "Morning of: 1 page has no morning-of region (written by an older "
                "fitdocs, or the region markers were removed); run 'fitdocs regen' "
                "to add it."
            ],
        ),
        (
            _report(without=2),
            [
                "Morning of: 2 pages have no morning-of region (written by an older "
                "fitdocs, or the region markers were removed); run 'fitdocs regen' "
                "to add it."
            ],
        ),
        (_report(without=2, values=False), []),
        (_report(), []),
        (
            _report(values=False, unavailable="broken [bold]series[/bold]"),
            [
                "Morning of: not refreshed; the wellness series could not be read: "
                "broken [bold]series[/bold]."
            ],
        ),
        (
            _report(
                (
                    MorningPage(
                        "workouts/[bold]" + "x" * 200 + "[/bold].md",
                        PageOutcome.FAILED,
                        "permission [red]denied[/red]",
                    ),
                    MorningPage(
                        "workouts/second.md", PageOutcome.FAILED, "damaged markers"
                    ),
                )
            ),
            [
                "Morning of: could not update workouts/[bold]"
                + "x" * 200
                + "[/bold].md: permission [red]denied[/red]",
                "Morning of: could not update workouts/second.md: damaged markers",
            ],
        ),
        (
            _report(
                (
                    MorningPage("workouts/a-updated.md", PageOutcome.UPDATED, None),
                    MorningPage("workouts/b-removed.md", PageOutcome.REMOVED, None),
                    MorningPage(
                        "workouts/c-failed.md", PageOutcome.FAILED, "permission denied"
                    ),
                    MorningPage("workouts/d-removed.md", PageOutcome.REMOVED, None),
                    MorningPage(
                        "workouts/e-failed.md", PageOutcome.FAILED, "damaged markers"
                    ),
                    MorningPage("workouts/f-removed.md", PageOutcome.REMOVED, None),
                ),
                without=4,
                values=True,
            ),
            [
                "Morning of: 1 page updated, 3 blocks removed.",
                "Morning of: could not update workouts/c-failed.md: permission denied",
                "Morning of: could not update workouts/e-failed.md: damaged markers",
                "Morning of: 4 pages have no morning-of region (written by an older "
                "fitdocs, or the region markers were removed); run 'fitdocs regen' "
                "to add it.",
            ],
        ),
        (
            _report(
                (
                    MorningPage("workouts/b-removed.md", PageOutcome.REMOVED, None),
                    MorningPage(
                        "workouts/c-failed.md", PageOutcome.FAILED, "permission denied"
                    ),
                    MorningPage("workouts/d-removed.md", PageOutcome.REMOVED, None),
                    MorningPage(
                        "workouts/e-failed.md", PageOutcome.FAILED, "damaged markers"
                    ),
                    MorningPage("workouts/f-removed.md", PageOutcome.REMOVED, None),
                ),
                without=4,
                values=False,
            ),
            [
                "Morning of: 3 blocks removed.",
                "Morning of: could not update workouts/c-failed.md: permission denied",
                "Morning of: could not update workouts/e-failed.md: damaged markers",
            ],
        ),
    ],
    ids=[
        "updated-one",
        "updated-many",
        "removed-one",
        "removed-many",
        "both-2-1",
        "both-1-2",
        "without-one",
        "without-many",
        "without-empty",
        "unchanged",
        "unavailable",
        "failed-literal-long",
        "mixed-nonempty",
        "mixed-empty",
    ],
)
def test_report_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    report: MorningReport,
    expected: list[str],
) -> None:
    root, source = _root(tmp_path)
    _stage(root)
    monkeypatch.setattr(engine, "run_morning_pass", lambda _root: report)
    result = _invoke(root, source, "source")
    assert [
        line for line in result.stdout.splitlines() if line.startswith("Morning of:")
    ] == expected


@pytest.mark.parametrize("flow", ["source", "drain", "regen"])
@pytest.mark.parametrize("failed", [False, True], ids=["success", "failed-page"])
@pytest.mark.parametrize(
    "observable", ["exit", "line", "order", "once", "later-passes"]
)
def test_native_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flow: str,
    failed: bool,
    observable: str,
) -> None:
    root, source, page = _scenario(tmp_path, flow)
    events: list[str] = []
    original = engine.run_morning_pass

    def morning(data_root: Path) -> MorningReport:
        events.append("morning")
        return original(data_root)

    monkeypatch.setattr(engine, "run_morning_pass", morning)
    for name in ("load", "plan", "index", "dashboard"):
        original_pass = getattr(cli, f"_run_{name}_pass")

        def track(
            *a: Any, _name: str = name, _pass: Any = original_pass, **kw: Any
        ) -> Any:
            events.append(_name)
            return _pass(*a, **kw)

        monkeypatch.setattr(cli, f"_run_{name}_pass", track)
    if failed:

        def unwritable(_path: Path, _text: str) -> None:
            raise OSError("selected write denied")

        monkeypatch.setattr(engine, "_atomic_write", unwritable)
    result = _invoke(root, source, flow)
    expected = (
        f"Morning of: could not update workouts/{page.name}: selected write denied"
        if failed
        else "Morning of: 1 page updated."
    )
    if observable == "exit":
        assert result.exit_code == (1 if failed else 0), result.output
    if observable == "line":
        assert [
            line
            for line in result.stdout.splitlines()
            if line.startswith("Morning of:")
        ] == [expected]
    if observable == "order":
        before = (
            "Series written:"
            if flow == "regen"
            else "└"
            if flow == "source"
            else "Wellness series: rebuilt"
        )
        assert (
            result.stdout.index(before)
            < result.stdout.index(expected)
            < result.stdout.index("fitdocs load")
        ), result.output
    if observable == "once":
        assert events.count("morning") == 1
    if observable == "later-passes":
        assert events == ["morning", "load", "plan", "index", "dashboard"]


@pytest.mark.parametrize("flow", ["source", "drain", "regen"])
def test_current_block_after_native_flow(tmp_path: Path, flow: str) -> None:
    root, source, page = _scenario(tmp_path, flow)
    _invoke(root, source, flow)
    assert read_morning(page.read_text()) == render_region(
        MorningInputs.of(read_series(root)).block(DAY)
    )


@pytest.mark.parametrize("flow", ["source", "drain", "regen"])
@pytest.mark.parametrize("observable", ["exit", "line", "load", "later-passes"])
def test_unexpected_error_still_runs_later_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flow: str, observable: str
) -> None:
    root, source, _page = _scenario(tmp_path, flow)

    def broken(_root: Path) -> MorningReport:
        raise RuntimeError("unexpected [bold]failure[/bold]")

    monkeypatch.setattr(engine, "run_morning_pass", broken)
    events: list[str] = []
    for name in ("load", "plan", "index", "dashboard"):
        original_pass = getattr(cli, f"_run_{name}_pass")

        def track(
            *a: Any, _name: str = name, _pass: Any = original_pass, **kw: Any
        ) -> Any:
            events.append(_name)
            return _pass(*a, **kw)

        monkeypatch.setattr(cli, f"_run_{name}_pass", track)
    result = _invoke(root, source, flow)
    if observable == "exit":
        assert result.exit_code == 1, result.output
    if observable == "line":
        assert [
            line
            for line in result.stdout.splitlines()
            if line.startswith("Morning of:")
        ] == [
            "Morning of: not refreshed; RuntimeError: unexpected [bold]failure[/bold]."
        ]
    if observable == "load":
        assert "fitdocs load" in result.stdout
    if observable == "later-passes":
        assert events == ["load", "plan", "index", "dashboard"]


@pytest.mark.parametrize("observable", ["raises", "identity"])
def test_direct_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    interrupt = KeyboardInterrupt("preserve identity")

    def interrupted(_root: Path) -> MorningReport:
        raise interrupt

    monkeypatch.setattr(engine, "run_morning_pass", interrupted)
    if observable == "raises":
        with pytest.raises(KeyboardInterrupt):
            cli._run_morning_pass(tmp_path)
    else:
        with pytest.raises(KeyboardInterrupt) as raised:
            cli._run_morning_pass(tmp_path)
        assert raised.value is interrupt


@pytest.mark.parametrize("observable", ["exit", "no-report", "no-load"])
def test_cli_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    root, source, _page = _scenario(tmp_path, "drain")

    def interrupted(_root: Path) -> MorningReport:
        raise KeyboardInterrupt("preserve identity")

    monkeypatch.setattr(engine, "run_morning_pass", interrupted)
    result = _invoke(root, source, "drain")
    if observable == "exit":
        assert result.exit_code == 130, result.output
    if observable == "no-report":
        assert "not refreshed" not in result.stdout
    if observable == "no-load":
        assert "fitdocs load" not in result.stdout


@pytest.mark.parametrize(
    "command", ["load", "history", "plan", "check", "index", "query", "recovery"]
)
@pytest.mark.parametrize(
    "observable", ["stale-before", "bytes", "no-call", "exit", "result"]
)
def test_standalone_commands_leave_stale_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, observable: str
) -> None:
    root, page = _standalone_scenario(tmp_path, command)
    before = page.read_bytes()
    if observable == "stale-before":
        assert (
            read_morning(before.decode()) == STALE
            and render_region(MorningInputs.of(read_series(root)).block(DAY)) != STALE
        )
    spy = Mock(wraps=engine.run_morning_pass)
    monkeypatch.setattr(engine, "run_morning_pass", spy)
    args = [command, "--out", str(root)]
    if command == "query":
        args.append("--schema")
    if command == "load":
        args.append("--no-prompt")
    result = runner.invoke(cli.app, args)
    if observable == "exit":
        assert result.exit_code == 0, result.output
    if observable == "result":
        patterns = {
            "load": re.escape(f"workouts/{page.name}"),
            "history": r"│ Pages read\s*│\s*1\s*│",
            "plan": re.escape(
                "rendered  plans/minimal.toml -> blocks/minimal.md "
                "(+1 planned, -0 removed)"
            ),
            "check": r"│ Documents inspected\s*│\s*1\s*│",
            "index": r"│ Added\s*│\s*1\s*│",
            "query": re.escape("### `pages` (1 row)"),
            "recovery": re.escape("recovery/recovery.md: written"),
        }
        assert re.search(patterns[command], result.stdout), result.output
    if observable == "bytes":
        assert page.read_bytes() == before
    if observable == "no-call":
        assert spy.call_count == 0


@pytest.mark.parametrize("observable", ["helper", "line", "exit"])
def test_pull_sync_uses_native_drain_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    root, _source, _page = _scenario(tmp_path, "drain")
    spy = Mock(wraps=cli._run_drain_passes)
    monkeypatch.setattr(cli, "_run_drain_passes", spy)
    result = runner.invoke(
        cli.app, ["pull", "--sync", "--no-prompt", "--out", str(root)]
    )
    if observable == "helper":
        assert spy.call_count == 1 and spy.call_args.kwargs["command"] == "pull"
    if observable == "line":
        assert "Morning of: 1 page updated." in result.stdout
    if observable == "exit":
        assert result.exit_code == 0, result.output


@pytest.mark.parametrize("observable", ["exit", "line", "bytes"])
def test_unreadable_series_is_nonfatal_and_leaves_page(
    tmp_path: Path, observable: str
) -> None:
    root, source, page = _scenario(tmp_path, "source")
    (root / "wellness" / "2021.csv").write_text("wrong header\n")
    before = page.read_bytes()
    result = _invoke(root, source, "source")
    if observable == "exit":
        assert result.exit_code == 0, result.output
    if observable == "line":
        assert [
            line
            for line in result.stdout.splitlines()
            if line.startswith("Morning of:")
        ] == [
            "Morning of: not refreshed; the wellness series could not be read: "
            f"{root}/wellness/2021.csv:1: wrong series header."
        ]
    if observable == "bytes":
        assert page.read_bytes() == before
