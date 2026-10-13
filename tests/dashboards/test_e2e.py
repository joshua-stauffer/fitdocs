"""The whole dashboards feature, end to end: a real index, and byte goldens.

Two halves. The live tests drive ``fitdocs sync``, ``regen``, ``index
--rebuild``, ``history``, ``plan`` and ``dashboard refresh`` over a copy of the
indexed fixture root. The golden tests run the engine over a fake source with a
fixed date and compare each page's bytes with ``golden/<case>.md``; the images
are compared with the chart kit's live ``render_chart`` output, never a stored
copy. Regenerate the goldens, and only them, with
``uv run python -m tests.dashboards.test_e2e``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli
from fitdocs.cli import app
from fitdocs.dashboards.engine import Action, RunRequest, run_dashboards
from fitdocs.dashboards.problems import DashboardCode, dashboard_problem
from fitdocs.render.charts.kit import ChartData, ChartRequest, render_chart
from fitdocs.units import unit_for_column
from tests.dashboards._helpers import (
    FakeSource,
    assert_untouched,
    chart_data,
    date_column,
    directive_block,
    make_data_root,
    number_column,
    page_text,
    snapshot_of,
    write_page,
)
from tests.dashboards.conftest import IndexedDashboardRoot, copy_dashboard_root

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_TODAY = date(2031, 4, 5)
MINIMAL_PLAN = (
    Path(__file__).resolve().parents[1] / "plans" / "fixtures" / "minimal.toml"
).read_bytes()
MARK = "<!-- fitdocs:generated -->"

# -- the live index ------------------------------------------------------------

SQL_WEEKLY = (
    "SELECT date_trunc('week', start_utc)::DATE AS week_start,\n"
    "       sum(distance_m) / 1000.0 AS distance_km\n"
    "FROM activities\n"
    "WHERE start_utc::DATE >= $today - 84\n"
    "GROUP BY 1\n"
    "ORDER BY 1"
)
SQL_SCATTER = (
    "SELECT distance_m / 1000.0 AS distance_km,\n"
    "       moving_time_s / 60.0 AS moving_min\n"
    "FROM activities\n"
    "ORDER BY start_utc"
)


def _indent(sql: str) -> str:
    return "|\n" + "\n".join(f"  {line}" for line in sql.split("\n"))


def weekly_directive() -> str:
    return directive_block(
        [
            ("id", "weekly"),
            ("kind", "bar"),
            ("mode", "relative"),
            ("title", "Weekly distance"),
            ("window", "last 12 weeks"),
            ("sql", _indent(SQL_WEEKLY)),
            ("channels", "\n  x: week_start\n  y: distance_km"),
        ]
    )


def scatter_directive() -> str:
    return directive_block(
        [
            ("id", "scatter"),
            ("kind", "scatter"),
            ("mode", "frozen"),
            ("title", "Distance against time"),
            ("sql", _indent(SQL_SCATTER)),
            ("channels", "\n  x: distance_km\n  y: moving_min"),
        ]
    )


def live_page(frontmatter: dict[str, str] | None = None) -> str:
    return page_text(
        "Prose before the charts.",
        weekly_directive(),
        "Prose between them.",
        scatter_directive(),
        "Prose after.",
        frontmatter=frontmatter,
    )


@dataclass
class Live:
    fixture: IndexedDashboardRoot
    runner: CliRunner

    @property
    def root(self) -> Path:
        return self.fixture.root

    @property
    def dashboards(self) -> Path:
        return self.fixture.root / "dashboards"

    def run(self, *args: str) -> tuple[int, str]:
        result = self.runner.invoke(app, list(args))
        return result.exit_code, result.output


@pytest.fixture
def live(
    indexed_dashboard_root: IndexedDashboardRoot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Live:
    fixture = copy_dashboard_root(indexed_dashboard_root, tmp_path)
    for name, value in fixture.environ.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(cli, "_today", lambda: fixture.today)
    return Live(fixture, CliRunner())


def sync_args(live: Live, tmp_path: Path) -> list[str]:
    source = tmp_path / "empty-source"
    source.mkdir(exist_ok=True)
    return ["sync", str(source), "--out", str(live.root), "--no-prompt"]


def generated_lines(text: str) -> list[str]:
    return [
        line for line in text.split("\n") if line.startswith("<!-- fitdocs:generated")
    ]


def test_sync_renders_both_charts_and_a_second_sync_changes_nothing(
    live: Live, tmp_path: Path
) -> None:
    page = write_page(live.root, "board", live_page())
    original = page.read_text(encoding="utf-8")
    assert "fitdocs:begin" not in original
    assert not (live.dashboards / "assets").exists()

    code, output = live.run(*sync_args(live, tmp_path))
    assert code == 0, output
    assert "Dashboards: 2 rendered, 0 unchanged, 0 failed." in output

    text = page.read_text(encoding="utf-8")
    assert "![Weekly distance](assets/board/weekly.svg)" in text
    assert "![Distance against time](assets/board/scatter.svg)" in text
    assert "<!-- fitdocs:snapshot assets/board/scatter.snapshot-1.json -->" in text
    # 2021-09-08 is a Wednesday; its week starts Monday 2021-09-06.
    assert "*last 12 weeks · through 2021-09-06*" in text
    assert "*Snapshot 2021-10-01 · through" not in text
    for name in ("weekly.svg", "scatter.svg"):
        image = (live.dashboards / "assets" / "board" / name).read_text(
            encoding="utf-8"
        )
        assert image.startswith(MARK + "\n<svg")
    # 1.6: images carry the mark, a page never does.
    assert generated_lines(text) == []
    assert (live.dashboards / "AGENTS.md").is_file()

    before = snapshot_of(live.dashboards)
    assert {
        "board.md",
        "assets/board/weekly.svg",
        "assets/board/scatter.svg",
        "assets/board/scatter.snapshot-1.json",
        "AGENTS.md",
    } <= set(before)
    code, output = live.run(*sync_args(live, tmp_path))
    assert code == 0, output
    assert "Dashboards:" not in output
    assert_untouched(before, snapshot_of(live.dashboards))


def test_regen_and_an_index_rebuild_leave_the_snapshot_byte_identical(
    live: Live, tmp_path: Path
) -> None:
    write_page(live.root, "board", live_page())
    code, output = live.run(*sync_args(live, tmp_path))
    assert code == 0, output
    snapshot = live.dashboards / "assets" / "board" / "scatter.snapshot-1.json"
    data, mtime = snapshot.read_bytes(), snapshot.stat().st_mtime_ns
    assert b'"rows"' in data
    for args in (
        ["regen", "--out", str(live.root)],
        ["index", "--rebuild", "--out", str(live.root)],
    ):
        code, output = live.run(*args)
        assert code == 0, output
        assert snapshot.read_bytes() == data
        assert snapshot.stat().st_mtime_ns == mtime
    names = sorted(p.name for p in snapshot.parent.iterdir() if "snapshot" in p.name)
    assert names == ["scatter.snapshot-1.json"]


def test_without_an_index_the_frozen_chart_renders_and_the_relative_one_is_reported(
    live: Live, tmp_path: Path
) -> None:
    write_page(live.root, "board", live_page())
    code, output = live.run(*sync_args(live, tmp_path))
    assert code == 0, output
    assets = live.dashboards / "assets" / "board"
    page = live.dashboards / "board.md"
    page_bytes = page.read_bytes()
    weekly = (assets / "weekly.svg").read_bytes()
    scatter = (assets / "scatter.svg").read_bytes()
    # Make the frozen chart's re-render observable: its image is gone first.
    (assets / "scatter.svg").unlink()
    moved = tmp_path / "moved-index"
    live.fixture.index_dir.rename(moved)
    assert not live.fixture.index_dir.exists()

    code, output = live.run(
        "dashboard", "refresh", "--format", "json", "--out", str(live.root)
    )
    assert code == 1, output
    report = json.loads(output)
    assert report["index"]["state"] == "not_built"
    by_chart = {c["id"]: c for p in report["pages"] for c in p["charts"]}
    assert [p["code"] for p in by_chart["weekly"]["problems"]] == [
        DashboardCode.INDEX_UNAVAILABLE.value
    ]
    assert by_chart["scatter"]["problems"] == []
    assert by_chart["scatter"]["outcome"] == "rendered"
    assert by_chart["weekly"]["outcome"] == "failed"
    assert (assets / "scatter.svg").read_bytes() == scatter
    assert (assets / "weekly.svg").read_bytes() == weekly
    assert page.read_bytes() == page_bytes


def tree_of(root: Path) -> dict[str, bytes]:
    """Bytes of every file under ``root`` except ``dashboards/``, by relative path."""
    found: dict[str, bytes] = {}
    for current, _dirs, names in os.walk(root):
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if not rel.startswith("dashboards/"):
                found[rel] = path.read_bytes()
    return found


def test_a_dashboard_page_typed_workout_is_untouched_outside_its_regions(
    live: Live, tmp_path: Path
) -> None:
    # A complete, dated workout frontmatter inside the plan's week: a history or
    # plan scan that wrongly read dashboards/ would take this page as a workout.
    frontmatter = {
        "type": "workout",
        "date": "'2026-02-02'",
        "sport": "Run",
        "modality": "run",
        "start_time": "'2026-02-02T07:00:00+00:00'",
    }
    plans = live.root / "plans"
    plans.mkdir()
    (plans / "minimal.toml").write_bytes(MINIMAL_PLAN)
    reference = tmp_path / "reference-root"
    shutil.copytree(live.root, reference, ignore=shutil.ignore_patterns("dashboards"))
    text = live_page(frontmatter)
    page = write_page(live.root, "board", text)
    workouts = sorted(p.name for p in (live.root / "workouts").iterdir())
    code, output = live.run(*sync_args(live, tmp_path))
    assert code == 0, output
    ref_code, ref_output = live.run(
        "sync", str(tmp_path / "empty-source"), "--out", str(reference), "--no-prompt"
    )
    assert ref_code == 0, ref_output
    after_sync = page.read_bytes()
    assert after_sync != text.encode()
    # Removing the two inserted regions gives the original page back.
    stripped = after_sync.decode()
    for chart in ("weekly", "scatter"):
        begin = stripped.index(f"<!-- fitdocs:begin:chart:{chart} -->")
        end_marker = f"<!-- fitdocs:end:chart:{chart} -->\n"
        end = stripped.index(end_marker) + len(end_marker)
        stripped = stripped[:begin] + stripped[end:]
    assert stripped == text
    before = snapshot_of(live.dashboards)
    mtime = page.stat().st_mtime_ns
    for args in (["history"], ["plan"]):
        code, output = live.run(*args, "--out", str(live.root))
        assert code == 0, output
        ref_code, ref_output = live.run(*args, "--out", str(reference))
        assert ref_code == 0, ref_output
        # The same command over a root without the page says the same.
        assert output.replace(str(live.root), "ROOT") == ref_output.replace(
            str(reference), "ROOT"
        )
        assert page.read_bytes() == after_sync
        assert page.stat().st_mtime_ns == mtime
    assert_untouched(before, snapshot_of(live.dashboards))
    live_tree = tree_of(live.root)
    reference_tree = tree_of(reference)
    assert "blocks/minimal.md" in reference_tree
    assert "Pages read       │      2" in ref_history_output(reference)
    assert live_tree == reference_tree
    assert sorted(p.name for p in (live.root / "workouts").iterdir()) == workouts
    assert not any("board" in name for name in workouts)


def ref_history_output(root: Path) -> str:
    result = CliRunner().invoke(app, ["history", "--out", str(root)])
    assert result.exit_code == 0, result.output
    return result.output


# -- the goldens ---------------------------------------------------------------


def _directive(
    chart_id: str,
    kind: str,
    mode: str,
    channels: str,
    *,
    window: str | None = None,
    show_rows: bool = False,
) -> str:
    keys = [
        ("id", chart_id),
        ("kind", kind),
        ("mode", mode),
        ("title", f"Title of {chart_id}"),
    ]
    if window is not None:
        keys.append(("window", window))
    if show_rows:
        keys.append(("show_rows", "true"))
    keys.append(("sql", f"|\n  select {chart_id}"))
    keys.append(("channels", channels))
    return directive_block(keys)


def _days(
    values: Sequence[tuple[date, float]], number: str, unit: str | None
) -> ChartData:
    return chart_data(
        (date_column("day"), number_column(number, unit=unit)),
        [(day, value) for day, value in values],
    )


RELATIVE_DATA = _days(
    [(date(2031, 3, 17), 40.5), (date(2031, 3, 3), 31.25), (date(2031, 3, 10), 52.0)],
    "distance_km",
    "km",
)
FROZEN_DATA = _days(
    [(date(2031, 2, 12), 8.0), (date(2031, 2, 2), 5.5), (date(2031, 2, 7), 6.75)],
    "distance_km",
    "km",
)
STAT_DATA = chart_data((number_column("weekly_km", unit="km"),), [(41.5,)])


def build_case(name: str) -> tuple[str, str, FakeSource, str, str]:
    """(page text, page name, source, chart id, kind) for one golden case."""
    prose = f"Prose before the {name} chart.\n"
    source = FakeSource()
    if name == "relative":
        block = _directive(
            "rel",
            "bar",
            "relative",
            "\n  x: day\n  y: distance_km",
            window="last 12 weeks",
        )
        source.queue("select rel\n", RELATIVE_DATA)
        chart = "rel"
    elif name == "frozen":
        block = _directive(
            "froz",
            "scatter",
            "frozen",
            "\n  x: day\n  y: distance_km",
            window="block 3",
        )
        source.queue("select froz\n", FROZEN_DATA)
        chart = "froz"
    elif name == "stat":
        block = _directive("headline", "stat", "relative", "\n  value: weekly_km")
        source.queue("select headline\n", STAT_DATA)
        chart = "headline"
    elif name == "rows":
        block = _directive(
            "listed",
            "bar",
            "relative",
            "\n  x: day\n  y: distance_km",
            window="last 3 weeks",
            show_rows=True,
        )
        source.queue("select listed\n", RELATIVE_DATA)
        chart = "listed"
    elif name == "note":
        block = _directive("broken", "bar", "relative", "\n  x: day\n  y: distance_km")
        source.queue(
            "select broken\n",
            (
                dashboard_problem(
                    DashboardCode.SQL_FAILED,
                    "Catalog Error: no table.",
                    "Fix the SQL.",
                    page=name,
                    chart="broken",
                ),
            ),
        )
        chart = "broken"
    else:
        raise AssertionError(name)
    kind = {
        "relative": "bar",
        "frozen": "scatter",
        "stat": "stat",
        "rows": "bar",
        "note": "bar",
    }[name]
    return page_text(prose, block, "Prose after.\n"), name, source, chart, kind


CASES = ("relative", "frozen", "stat", "rows", "note")


def run_case(name: str, root: Path) -> tuple[bytes, FakeSource]:
    text, page, source, _chart, _kind = build_case(name)
    write_page(root, page, text)
    report = run_dashboards(
        RunRequest(Action.REFRESH, root, (), GOLDEN_TODAY), source.opener()
    )
    assert report.failed == (name == "note")
    return (root / "dashboards" / f"{page}.md").read_bytes(), source


def expected_image(name: str) -> bytes | None:
    """The kit's live SVG for the case, with the mark; None for markdown kinds."""
    _text, page, _source, chart, kind = build_case(name)
    if kind == "stat" or name == "note":
        return None
    channels = {"x": "day", "y": "distance_km"}
    data = FROZEN_DATA if name == "frozen" else RELATIVE_DATA
    if name == "frozen":  # stored columns carry no unit; the engine re-derives it
        token = unit_for_column("distance_km")
        assert token is not None
        data = _days([(r[0], r[1]) for r in data.rows], "distance_km", token.token)  # type: ignore[misc]
    rendered = render_chart(
        ChartRequest(f"{page}:{chart}", kind, f"Title of {chart}", channels), data
    )
    return f"{MARK}\n{rendered.text}".encode()


@pytest.mark.parametrize("name", CASES)
def test_the_page_matches_its_golden_bytes(name: str, tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    produced, _source = run_case(name, root)
    golden = (GOLDEN_DIR / f"{name}.md").read_bytes()
    assert produced == golden
    expected = expected_image(name)
    images = sorted((root / "dashboards").glob("assets/*/*.svg"))
    if expected is None:
        assert images == []
    else:
        assert [p.read_bytes() for p in images] == [expected]


def main() -> None:
    """Rewrite every golden from the engine's current output."""
    import tempfile

    GOLDEN_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        for name in CASES:
            root = make_data_root(Path(scratch), name)
            produced, _source = run_case(name, root)
            (GOLDEN_DIR / f"{name}.md").write_bytes(produced)


if __name__ == "__main__":
    main()
    sys.stdout.write(f"wrote {len(CASES)} goldens to {GOLDEN_DIR}\n")
