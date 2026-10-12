"""``fitdocs dashboard``: the four forms, targets, output formats and exit codes.

Most tests replace ``fitdocs.dashboards.binding.source_opener`` (the command
imports it when it runs) with one that hands out a ``FakeSource``; the last test
runs the real index. Data roots are ``tmp_path`` directories named by
``--out`` or ``FITDOCS_DATA``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

import fitdocs.cli as cli
from fitdocs.cli import app
from fitdocs.dashboards import engine
from fitdocs.dashboards.engine import Action, RunReport, RunRequest, Target
from fitdocs.dashboards.kinds import kinds_text
from fitdocs.dashboards.problems import DashboardCode
from fitdocs.dashboards.report import render_json, render_text
from fitdocs.dashboards.source import ChartSource, SourceOpener, SourceUnavailable
from fitdocs.index.location import IndexLocationError
from fitdocs.query.command import QueryEnvironment
from fitdocs.render.charts.kit import describe_kinds
from tests.dashboards._helpers import (
    FakeSource,
    assert_untouched,
    category_number_data,
    directive_block,
    make_data_root,
    page_text,
    query_environment,
    region_block,
    snapshot_of,
    write_page,
)
from tests.dashboards.conftest import IndexedDashboardRoot, copy_dashboard_root

TODAY = date(2026, 10, 12)
SQL_ONE = "select one"
SQL_TWO = "select two"


def fetched_as(sql: str) -> str:
    """The SQL as the source receives it: the block scalar ends with a newline."""
    return sql + "\n"


OPENER = "<!-- fitdocs:chart"


def keys(chart_id: str, sql: str) -> list[tuple[str, str]]:
    return [
        ("id", chart_id),
        ("kind", "bar"),
        ("mode", "relative"),
        ("title", f"Title of {chart_id}"),
        ("sql", f"|\n  {sql}"),
        ("channels", "\n  x: label\n  y: value"),
    ]


def good(chart_id: str, sql: str) -> str:
    return directive_block(keys(chart_id, sql))


def invoke(args: list[str], env: dict[str, str] | None = None) -> Result:
    return CliRunner().invoke(app, ["dashboard", *args], env=env)


def must_not_open_source() -> ChartSource | SourceUnavailable:
    raise AssertionError("the source was opened")


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_today", lambda: TODAY)


def use_opener(monkeypatch: pytest.MonkeyPatch, opener: SourceOpener) -> None:
    def source_opener(data_root: Path, env: QueryEnvironment) -> SourceOpener:
        return opener

    monkeypatch.setattr("fitdocs.dashboards.binding.source_opener", source_opener)


def fake_source(monkeypatch: pytest.MonkeyPatch) -> FakeSource:
    source = FakeSource()
    source.queue(
        fetched_as(SQL_ONE), category_number_data([("a", 3.0), ("b", 1.0), ("c", 2.0)])
    )
    source.queue(fetched_as(SQL_TWO), category_number_data([("x", 5.0), ("y", 7.0)]))
    use_opener(monkeypatch, source.opener())
    return source


@pytest.fixture
def no_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory and HOME with no data root configured anywhere."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    return work


# -- kinds ---------------------------------------------------------------------------


def test_kinds_exits_0_with_no_data_root_configured_and_never_resolves_one(
    no_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def resolved(out: Path | None) -> Path:
        raise AssertionError("the data root was resolved for kinds")

    monkeypatch.setattr(cli, "_resolved_data_root", resolved)
    result = invoke(["kinds"])
    assert result.exit_code == 0, result.output
    listings = describe_kinds()
    assert listings, "the registry is empty, so the comparison below is trivial"
    assert result.stdout == kinds_text(listings)


def test_the_same_environment_fails_a_form_that_needs_the_data_root(
    no_data_root: Path,
) -> None:
    result = invoke(["check"])
    assert result.exit_code == 2
    assert "FITDOCS_DATA" in result.stderr
    assert result.stdout == ""


def test_kinds_json_is_the_registry_description(no_data_root: Path) -> None:
    result = invoke(["kinds", "--format", "json"])
    assert result.exit_code == 0, result.output
    expected = json.loads(json.dumps(describe_kinds()))
    assert expected, "the registry is empty, so the comparison below is trivial"
    assert json.loads(result.stdout) == expected
    assert (
        result.stdout
        == json.dumps(describe_kinds(), indent=2, ensure_ascii=False) + "\n"
    )


def test_kinds_reads_the_registry_when_the_command_runs(
    no_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel: list[dict[str, Any]] = [
        {
            "name": "sentinel-kind",
            "output": "svg",
            "description": "A kind only this test registers.",
            "channels": [],
            "options": [],
            "bound": {"limit": 3, "counts": "rows", "over": "rows", "rule": "r"},
            "max_series": None,
        }
    ]
    monkeypatch.setattr("fitdocs.render.charts.kit.describe_kinds", lambda: sentinel)
    as_text = invoke(["kinds"])
    as_json = invoke(["kinds", "--format", "json"])
    assert "sentinel-kind" in as_text.stdout
    assert [each["name"] for each in json.loads(as_json.stdout)] == ["sentinel-kind"]


@pytest.mark.parametrize("args", [["kinds", "x"], ["kinds", "--format", "json", "p:c"]])
def test_kinds_with_a_target_exits_2_and_prints_no_listing(
    no_data_root: Path, args: list[str]
) -> None:
    result = invoke(args)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "kinds" in result.stderr


# -- targets and the data root -------------------------------------------------------


def test_freeze_without_a_target_exits_2_before_the_source_or_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    use_opener(monkeypatch, must_not_open_source)
    before = snapshot_of(root)
    result = invoke(["freeze", "--out", str(root)])
    assert result.exit_code == 2
    assert "freeze" in result.stderr and "target" in result.stderr
    assert result.stdout == ""
    assert_untouched(before, snapshot_of(root))


@pytest.mark.parametrize("form", ["check", "refresh"])
def test_a_form_other_than_freeze_takes_no_target_to_mean_every_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    write_page(root, "q", page_text(good("two", SQL_TWO)))
    source = fake_source(monkeypatch)
    result = invoke([form, "--out", str(root)])
    assert result.exit_code == 0, result.output
    assert sorted(call.sql for call in source.calls) == [
        fetched_as(SQL_ONE),
        fetched_as(SQL_TWO),
    ]


def test_an_unknown_page_exits_2_listing_the_pages_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "gamma", page_text(good("one", SQL_ONE)))
    write_page(root, "alpha", page_text(good("two", SQL_TWO)))
    write_page(root, "beta", page_text(good("three", SQL_ONE)))
    use_opener(monkeypatch, must_not_open_source)
    before = snapshot_of(root)
    result = invoke(["refresh", "gamma", "nope", "--out", str(root)])
    assert result.exit_code == 2
    assert "alpha, beta, gamma" in result.stderr
    assert result.stdout == ""
    assert_untouched(before, snapshot_of(root))


def test_an_unknown_chart_exits_2_listing_that_pages_charts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("zulu", SQL_ONE), good("alpha", SQL_TWO)))
    use_opener(monkeypatch, must_not_open_source)
    before = snapshot_of(root)
    result = invoke(["check", "p:missing", "--out", str(root)])
    assert result.exit_code == 2
    assert "zulu, alpha" in result.stderr
    assert_untouched(before, snapshot_of(root))


def test_a_malformed_target_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    use_opener(monkeypatch, must_not_open_source)
    result = invoke(["check", "p:a:b", "--out", str(root)])
    assert result.exit_code == 2
    assert "p:a:b" in result.stderr


def test_an_unknown_format_exits_2(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    assert invoke(["check", "--format", "yaml", "--out", str(root)]).exit_code == 2
    assert invoke(["kinds", "--format", "yaml"]).exit_code == 2


def test_the_format_name_is_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    fake_source(monkeypatch)
    result = invoke(["check", "--format", "JSON", "--out", str(root)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["action"] == "check"


def test_an_unknown_form_exits_2(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    assert invoke(["explode", "--out", str(root)]).exit_code == 2


def test_out_wins_over_the_environment_and_the_environment_names_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = make_data_root(tmp_path, "real")
    decoy = make_data_root(tmp_path, "decoy")
    write_page(real, "real-page", page_text(good("one", SQL_ONE)))
    write_page(decoy, "decoy-page", page_text(good("one", SQL_ONE)))
    use_opener(monkeypatch, must_not_open_source)
    explicit = invoke(
        ["check", "nope", "--out", str(real)], env={"FITDOCS_DATA": str(decoy)}
    )
    assert explicit.exit_code == 2
    assert "real-page" in explicit.stderr and "decoy-page" not in explicit.stderr
    implicit = invoke(["check", "nope"], env={"FITDOCS_DATA": str(decoy)})
    assert implicit.exit_code == 2
    assert "decoy-page" in implicit.stderr and "real-page" not in implicit.stderr


# -- dispatch ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("form", "action"),
    [
        ("check", Action.CHECK),
        ("refresh", Action.REFRESH),
        ("freeze", Action.FREEZE),
    ],
)
def test_each_form_runs_its_action_over_the_resolved_targets_and_the_run_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str, action: Action
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    write_page(root, "q", page_text(good("two", SQL_TWO), good("three", SQL_ONE)))
    seen: list[tuple[RunRequest, SourceOpener]] = []
    report = RunReport(action, "not_needed", None, (), (), ())

    def capture(request: RunRequest, open_source: SourceOpener) -> RunReport:
        seen.append((request, open_source))
        return report

    opened: list[tuple[Path, QueryEnvironment]] = []
    environment = query_environment({"HOME": str(tmp_path)}, tmp_path)

    def source_opener(data_root: Path, env: QueryEnvironment) -> SourceOpener:
        opened.append((data_root, env))
        return must_not_open_source

    monkeypatch.setattr(engine, "run_dashboards", capture)
    monkeypatch.setattr("fitdocs.dashboards.binding.source_opener", source_opener)
    monkeypatch.setattr(cli, "_query_environment", lambda: environment)
    result = invoke([form, "q:three", "p", "--out", str(root)])
    assert result.exit_code == 0, result.output
    ((request, open_source),) = seen
    assert request == RunRequest(
        action,
        root,
        (Target("p", None), Target("q", "three")),
        TODAY,
    )
    assert open_source is must_not_open_source
    assert opened == [(root, environment)]
    assert opened[0][1] is environment
    assert result.stdout == render_text(report, chained=False) + "\n"


def test_query_command_reads_its_environment_from_the_shared_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    environment = query_environment({"HOME": str(tmp_path)}, tmp_path)
    seen: list[QueryEnvironment] = []

    def run_query(request: object, env: QueryEnvironment) -> object:
        seen.append(env)
        raise IndexLocationError("stop here")

    monkeypatch.setattr(cli, "_query_environment", lambda: environment)
    monkeypatch.setattr(cli, "run_query", run_query)
    result = CliRunner().invoke(app, ["query", "SELECT 1", "--out", str(root)])
    assert result.exit_code == 2
    assert seen == [environment] and seen[0] is environment


def test_the_query_environment_is_the_process_environment() -> None:
    environment = cli._query_environment()
    assert environment.environ is os.environ
    assert environment.home == Path.home()
    assert environment.pid == os.getpid()


# -- check, refresh and exit codes ---------------------------------------------------


def broken_page() -> str:
    """A good chart first, then a directive with a missing key."""
    return page_text(
        "# Page",
        good("one", SQL_ONE),
        "prose",
        f"{OPENER}\nid: bad\nkind: bar\n-->\n",
    )


def test_check_with_one_bad_directive_exits_1_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", broken_page())
    source = fake_source(monkeypatch)
    before = snapshot_of(root)
    result = invoke(["check", "--out", str(root)])
    assert result.exit_code == 1, result.output
    assert [call.sql for call in source.calls] == [fetched_as(SQL_ONE)], (
        "the good chart was drawn"
    )
    assert_untouched(before, snapshot_of(root))
    lines = result.stdout.splitlines()
    assert lines[-1].startswith("Dashboards: ")
    assert "1 failed" in lines[-1]
    assert any(line.startswith("p:") and line.endswith("bad failed") for line in lines)
    assert DashboardCode.MISSING_KEY.value in result.stdout


def test_refresh_of_a_healthy_page_exits_0_and_writes_the_region_and_the_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    original = page_text("# Page", good("one", SQL_ONE), "prose")
    page = write_page(root, "p", original)
    source = fake_source(monkeypatch)
    assert not (root / "dashboards" / "assets").exists()
    result = invoke(["refresh", "p", "--out", str(root)])
    assert result.exit_code == 0, result.output
    assert page.read_text(encoding="utf-8") != original
    assert "fitdocs:begin:chart:one" in page.read_text(encoding="utf-8")
    assert (root / "dashboards" / "assets" / "p" / "one.svg").is_file()
    assert [call.today for call in source.calls] == [TODAY]
    lines = result.stdout.splitlines()
    assert lines[-1] == "Dashboards: 1 rendered, 0 unchanged, 0 failed."


def test_a_second_refresh_changes_no_byte_and_still_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    fake_source(monkeypatch)
    assert invoke(["refresh", "--out", str(root)]).exit_code == 0
    os.utime(root / "dashboards" / "p.md", ns=(1, 1))
    before = snapshot_of(root)
    again = invoke(["refresh", "--out", str(root)])
    assert again.exit_code == 0, again.output
    assert_untouched(before, snapshot_of(root))
    assert again.stdout.splitlines()[-1] == (
        "Dashboards: 0 rendered, 1 unchanged, 0 failed."
    )


def test_a_notice_alone_exits_0_in_every_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(
        root,
        "p",
        page_text(
            good("one", SQL_ONE),
            region_block("one", "kept"),
            "prose",
            region_block("ghost", "left alone"),
        ),
    )
    fake_source(monkeypatch)
    text = invoke(["check", "--out", str(root)])
    assert text.exit_code == 0, text.output
    assert DashboardCode.REGION_ORPHANED.value in text.stdout
    as_json = invoke(["check", "--format", "json", "--out", str(root)])
    assert as_json.exit_code == 0, as_json.output
    document = json.loads(as_json.stdout)
    (notice,) = document["pages"][0]["notices"]
    assert notice["code"] == DashboardCode.REGION_ORPHANED.value
    assert document["pages"][0]["problems"] == []


def test_json_is_one_document_with_the_problems_and_a_trailing_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", broken_page())
    fake_source(monkeypatch)
    result = invoke(["check", "--format", "json", "--out", str(root)])
    assert result.exit_code == 1, result.output
    assert result.stdout.endswith("}\n") and not result.stdout.endswith("\n\n")
    document = json.loads(result.stdout)
    assert document["action"] == "check"
    assert document["summary"] == {
        "charts": 2,
        "rendered": 0,
        "unchanged": 0,
        "failed": 1,
    }
    by_id = {chart["id"]: chart for chart in document["pages"][0]["charts"]}
    assert by_id["one"]["problems"] == []
    codes = [problem["code"] for problem in by_id["bad"]["problems"]]
    assert DashboardCode.MISSING_KEY.value in codes
    assert not result.stdout.startswith("Dashboards")


def test_text_is_the_default_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    fake_source(monkeypatch)
    default = invoke(["check", "--out", str(root)])
    explicit = invoke(["check", "--format", "text", "--out", str(root)])
    assert default.stdout == explicit.stdout
    assert default.stdout.endswith("checked.\n")
    with pytest.raises(json.JSONDecodeError):
        json.loads(default.stdout)


def test_json_output_equals_render_json_of_the_report_with_a_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    report = RunReport(Action.CHECK, "not_needed", None, (), (), ())
    monkeypatch.setattr(engine, "run_dashboards", lambda request, opener: report)
    monkeypatch.setattr(
        "fitdocs.dashboards.binding.source_opener",
        lambda data_root, env: must_not_open_source,
    )
    result = invoke(["check", "--format", "json", "--out", str(root)])
    assert result.exit_code == 0
    assert result.stdout == render_json(report) + "\n"


# -- configuration errors and interrupts ---------------------------------------------


def test_an_index_location_error_exits_2_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    before = snapshot_of(root)
    inside = root / "index-inside-the-root"
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(inside))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    result = invoke(["refresh", "--out", str(root)])
    assert result.exit_code == 2, result.output
    assert "data root" in result.stderr
    assert result.stdout == ""
    assert_untouched(before, snapshot_of(root))


def raising(error: BaseException) -> SourceOpener:
    def open_source() -> ChartSource | SourceUnavailable:
        raise error

    return open_source


def test_an_index_location_error_from_the_opener_is_a_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    use_opener(monkeypatch, raising(IndexLocationError("the index lies in the root")))
    before = snapshot_of(root)
    result = invoke(["refresh", "--out", str(root)])
    assert result.exit_code == 2
    assert "the index lies in the root" in result.stderr
    assert_untouched(before, snapshot_of(root))


def test_an_interrupt_exits_130_with_one_stderr_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    use_opener(monkeypatch, raising(KeyboardInterrupt()))
    before = snapshot_of(root)
    result = invoke(["refresh", "--out", str(root)])
    assert result.exit_code == 130
    assert result.stderr == "Dashboard run interrupted.\n"
    assert result.stdout == ""
    assert_untouched(before, snapshot_of(root))


def test_a_location_problem_alone_exits_1_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "p.md").write_text(page_text(good("one", SQL_ONE)), encoding="utf-8")
    (root / "dashboards").symlink_to(elsewhere, target_is_directory=True)
    use_opener(monkeypatch, must_not_open_source)
    before = snapshot_of(elsewhere)
    result = invoke(["refresh", "--format", "json", "--out", str(root)])
    assert result.exit_code == 1, result.output
    document = json.loads(result.stdout)
    assert [each["code"] for each in document["location_problems"]] == [
        DashboardCode.LOCATION_FOREIGN.value
    ]
    assert document["pages"] == []
    assert_untouched(before, snapshot_of(elsewhere))


def test_importing_the_cli_loads_no_dashboards_module(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "import fitdocs.cli\n"
        "prefix = 'fitdocs.dashboards'\n"
        "loaded = sorted(n for n in sys.modules if n.startswith(prefix))\n"
        "print(loaded, 'duckdb' in sys.modules)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[] False"


def test_an_unavailable_index_is_a_reported_problem_and_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(good("one", SQL_ONE)))
    unavailable = SourceUnavailable("not_built", "no index yet", "fitdocs index")
    use_opener(monkeypatch, lambda: unavailable)
    result = invoke(["check", "--out", str(root)])
    assert result.exit_code == 1, result.output
    assert DashboardCode.INDEX_UNAVAILABLE.value in result.stdout


# -- the real index ------------------------------------------------------------------


def test_refresh_over_a_real_index(
    indexed_dashboard_root: IndexedDashboardRoot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = copy_dashboard_root(indexed_dashboard_root, tmp_path)
    for name, value in fixture.environ.items():
        monkeypatch.setenv(name, value)
    sql = (
        "SELECT CAST(row_number() OVER (ORDER BY start_utc) AS VARCHAR) AS label, "
        "1.0 AS value FROM activities"
    )
    write_page(fixture.root, "p", page_text(good("runs", sql)))
    result = invoke(["refresh", "--out", str(fixture.root)])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[-1] == (
        "Dashboards: 1 rendered, 0 unchanged, 0 failed."
    )
    assert (fixture.root / "dashboards" / "assets" / "p" / "runs.svg").is_file()
