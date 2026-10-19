"""``docs/dashboards.md``: the live kinds block, the published contract, the examples.

Run ``uv run python -m tests.dashboards.test_docs_dashboards [PAGE]`` to rewrite
the page's kinds block from the chart registry.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from typer.core import TyperOption
from typer.main import get_command
from typer.testing import CliRunner

import fitdocs.cli as cli
from fitdocs.cli import app
from fitdocs.dashboards.directive import Directive, parse_directive
from fitdocs.dashboards.grammar import SLUG, scan_page
from fitdocs.dashboards.kinds import kinds_markdown
from fitdocs.render.charts.kit import describe_kinds, kind_names
from tests.dashboards._helpers import write_page
from tests.dashboards.conftest import IndexedDashboardRoot, copy_dashboard_root
from tests.query._helpers import FIXTURE_TODAY
from tests.test_docs_guarantees import _REQUIRED_ENTRY_POINT_LINKS

_START = "<!-- dashboard-kinds:start -->"
_END = "<!-- dashboard-kinds:end -->"


def regenerate_kinds_block(page_path: Path) -> None:
    """Rewrite the page's kinds block from the live registry; nothing else changes."""
    page = page_path.read_bytes().decode("utf-8")
    if page.count(_START) != 1 or page.count(_END) != 1:
        raise ValueError("kinds block must have one start and end marker")
    start = page.index(_START) + len(_START)
    end = page.index(_END)
    if start > end:
        raise ValueError("kinds block markers are reversed")
    updated = page[:start] + "\n" + kinds_markdown(describe_kinds()) + page[end:]
    page_path.write_bytes(updated.encode("utf-8"))


def _page_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "dashboards.md"


def _marked_block(page: str) -> str:
    return page.split(_START, 1)[1].split(_END, 1)[0].removeprefix("\n")


def _section(page: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", page)
    assert match is not None, heading
    return " ".join(match.group(1).split())


def _section_raw(page: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", page)
    assert match is not None, heading
    return match.group(1)


def _bash_fitdocs_invocations(page: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for block in re.findall(r"(?ms)^```bash\s*\n(.*?)^```", page):
        for line in block.splitlines():
            if line.lstrip().startswith("#"):
                continue
            tokens = shlex.split(line, comments=True)
            if "fitdocs" not in tokens:
                continue
            commands.append(tokens[tokens.index("fitdocs") + 1 :])
    return commands


def _directive_example(page: str) -> str:
    """The first fenced directive: its body, between the delimiter lines."""
    match = re.search(
        r"(?ms)^(`{3,})markdown\n<!-- fitdocs:chart\n(.*?)^-->\n\1$", page
    )
    assert match is not None, "the page has no fenced directive example"
    return match.group(2)


# -- the kinds block ------------------------------------------------------------------


def test_the_published_kinds_block_matches_the_registry() -> None:
    page = _page_path().read_text(encoding="utf-8")
    block = _marked_block(page)
    assert block
    assert block == kinds_markdown(describe_kinds())
    # Non-vacuous: the block names every registered kind as an H3.
    assert kind_names()
    assert re.findall(r"(?m)^### `(.+)`$", block) == list(kind_names())


def test_regeneration_rewrites_only_the_marked_block(tmp_path: Path) -> None:
    prefix = "prefix sentinel\n"
    suffix = "\nsuffix sentinel\n"
    page_path = tmp_path / "dashboards.md"
    page_path.write_text(
        prefix + _START + "\nstale\n" + _END + suffix, encoding="utf-8"
    )

    regenerate_kinds_block(page_path)

    text = page_path.read_text(encoding="utf-8")
    assert text.startswith(prefix + _START + "\n")
    assert text.endswith("\n" + _END + suffix)
    assert _marked_block(text) == kinds_markdown(describe_kinds())
    first = page_path.read_bytes()
    regenerate_kinds_block(page_path)
    assert page_path.read_bytes() == first


@pytest.mark.parametrize(
    "malformed",
    [
        "prefix\nstale\n" + _END + "\nsuffix\n",
        "prefix\n" + _START + "\nstale\nsuffix\n",
        "prefix\n" + _START + "\none\n" + _START + "\ntwo\n" + _END,
        "prefix\n" + _START + "\none\n" + _END + "\n" + _END,
        "prefix\n" + _END + "\nstale\n" + _START + "\nsuffix\n",
    ],
)
def test_malformed_markers_fail_before_writing(tmp_path: Path, malformed: str) -> None:
    page_path = tmp_path / "malformed.md"
    page_path.write_text(malformed, encoding="utf-8")
    original = page_path.read_bytes()

    with pytest.raises(ValueError):
        regenerate_kinds_block(page_path)

    assert page_path.read_bytes() == original


def test_the_module_entry_point_regenerates_the_named_page(tmp_path: Path) -> None:
    page_path = tmp_path / "page.md"
    page_path.write_text(
        "a\n" + _START + "\nstale\n" + _END + "\nz\n", encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "-m", "tests.dashboards.test_docs_dashboards", str(page_path)],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode == 0, result.stderr
    assert _marked_block(page_path.read_text(encoding="utf-8")) == kinds_markdown(
        describe_kinds()
    )


# -- the published contract -----------------------------------------------------------


def test_the_page_has_the_documented_sections() -> None:
    page = _page_path().read_text(encoding="utf-8")
    assert page.startswith("# Dashboards\n\n## Before you start\n")
    assert re.findall(r"(?m)^# (.+)$", page) == ["Dashboards"]
    assert re.findall(r"(?m)^## (.+)$", page) == [
        "Before you start",
        "A dashboard page",
        "The chart directive",
        "Chart regions and assets",
        "Relative and frozen charts",
        "Writing the SQL",
        "Checking a page",
        "The fitdocs dashboard command",
        "Chart kinds",
        "Who owns what",
        "Version control",
    ]
    kinds_section = _section(page, "Chart kinds")
    assert _START in kinds_section and _END in kinds_section


def test_the_directive_section_teaches_the_keys_and_the_traps() -> None:
    page = _page_path().read_text(encoding="utf-8")
    directive = _section(page, "The chart directive")
    for key in ("id", "kind", "mode", "title", "sql", "channels", "options"):
        assert f"`{key}`" in directive, key
    assert "`window`" in directive and "`show_rows`" in directive
    assert "exactly the first line of the example" in directive
    assert "column 0" in directive and "no indentation" in directive
    assert "`-->` and no `--!>`" in directive
    assert "`sql: |`" in directive and "literal block" in directive
    assert "reading view hides a directive" in directive
    assert "Live Preview" in directive and "dimmed source" in directive
    assert "ignores both inside backtick and tilde fences" in directive


def test_the_sql_section_carries_the_unit_pace_gap_and_non_finite_notes() -> None:
    page = _page_path().read_text(encoding="utf-8")
    sql = _section(page, "Writing the SQL")
    assert "`$today - 84`" in sql
    assert "`$today - INTERVAL 12 WEEK` is a timestamp, not a date" in sql
    assert "`AS distance_km`" in sql
    assert "fitdocs converts no unit" in sql
    assert "`1000.0 / NULLIF(speed_mps, 0) AS pace_s_per_km`" in sql
    assert "non-finite" in sql and "`non_finite`" in sql and "division by zero" in sql
    assert "A missing row is not an absent value" in sql
    assert "a row whose value is `NULL`" in sql
    assert "`COALESCE(sum(distance_m), 0)`" in sql
    assert "10,000 rows" in sql
    assert "A `TIMESTAMPTZ` column fails as a SQL error" in sql
    assert "hint to cast it to `TIMESTAMP`" in sql


def test_the_check_section_teaches_the_loop_and_the_problem_fields() -> None:
    page = _page_path().read_text(encoding="utf-8")
    checking = _section(page, "Checking a page")
    assert (
        "Write a directive, run `fitdocs dashboard check`, and fix what it reports"
        in checking
    )
    assert "`check` never writes or deletes a file" in checking
    assert "the JSON report's `option` field" in checking
    assert "when there are accepted values, its `accepted` list holds them" in checking
    assert "` Accepted: a, b, c.`" in checking
    checks = [
        each
        for each in _bash_fitdocs_invocations(_section_raw(page, "Checking a page"))
        if each[:2] == ["dashboard", "check"]
    ]
    assert checks
    assert any("--format" in each and "json" in each for each in checks)
    assert all(each[1] == "check" for each in checks)


def test_the_frozen_and_ownership_sections_state_the_snapshot_rules() -> None:
    page = _page_path().read_text(encoding="utf-8")
    frozen = _section(page, "Relative and frozen charts")
    assert "`mode: frozen`" in frozen and "`mode: relative`" in frozen
    assert "fitdocs dashboard freeze PAGE:CHART" in frozen
    assert ".snapshot-<n>.json" in frozen
    assert "never changes or deletes" in frozen

    regions = _section(page, "Chart regions and assets")
    assert "`dashboards/assets/<page name>/<chart id>.svg`" in regions
    assert "`Not rendered:`" in regions
    assert "is not written at all" in regions
    assert "A failing `freeze` writes no note" in regions
    assert "Links from outside `dashboards/` are not protected" in regions

    owns = _section(page, "Who owns what")
    assert "You own the page" in owns
    assert "the bytes between each region's begin and end markers" in owns
    assert "the chart images in `dashboards/assets/`" in owns

    versioning = _section(page, "Version control")
    assert "do not git-ignore" in versioning and "snapshot" in versioning


def test_the_regions_section_names_the_failures_that_leave_a_note_and_none() -> None:
    page = _page_path().read_text(encoding="utf-8")
    regions = _section(page, "Chart regions and assets")
    assert "fails in its query or its drawing" in regions
    assert "holds a value in its first frozen result that cannot be stored" in regions
    assert (
        "When a chart's image, snapshot or page cannot be written, its region is "
        "left as it was (a chart with no region still has none, and an earlier "
        "`Not rendered:` note stays) and the failure is reported"
    ) in regions
    assert "cannot be written gets no region" not in regions
    assert "its drawing or its writing" not in regions
    assert (
        "keeps its region exactly as it was, and its image too, unless the page "
        "changed during the run or could not be written after the chart's new "
        "image was written"
    ) in regions
    assert "keeps its region and image exactly as they were" not in regions


def test_no_new_data_keeps_a_chart_unchanged_only_without_today() -> None:
    """The guide said a day, or a sync, with no new data changes nothing on
    disk. Its own example window is ``$today - 84``, which moves each day, so
    both places now say the quiet tree holds only without ``$today``."""
    page = _page_path().read_text(encoding="utf-8")
    assert "$today - 84" in _directive_example(page)
    relative = _section(page, "Relative and frozen charts")
    assert "a run whose rows are unchanged changes nothing on disk" in relative
    assert (
        "A window written with `$today`, like the example above, moves each day"
    ) in relative
    assert "can change on a day with no new workouts" in relative
    assert "a day with no new data changes nothing on disk" not in relative
    versioning = _section(page, "Version control")
    assert (
        "A sync that brings no new data leaves the working tree clean only for "
        "charts whose SQL does not use `$today`."
    ) in versioning
    assert "so a sync that brings no new data leaves the working tree clean" not in (
        versioning
    )


def test_the_sql_section_calls_a_kinds_bound_a_size_bound_not_a_row_bound() -> None:
    counted = {
        cast("Mapping[str, object]", each["bound"])["counts"]
        for each in describe_kinds()
    }
    assert counted - {"rows"}, "a non-row bound is registered"
    page = _page_path().read_text(encoding="utf-8")
    sql = _section(page, "Writing the SQL")
    listed = re.search(r"has its own size bound \(([^)]*)\)", sql)
    assert listed is not None
    assert set(re.split(r", | or ", listed.group(1))) == counted
    assert "its own row bound" not in sql


def test_the_command_section_states_forms_targets_formats_and_exit_codes() -> None:
    page = _page_path().read_text(encoding="utf-8")
    command = _section(page, "The fitdocs dashboard command")
    for form in ("check", "refresh", "freeze", "kinds"):
        assert f"`{form}`" in command, form
    assert "`--format json`" in command and "`--out PATH`" in command
    assert (
        "exits 0 when every chart and page in scope checked or rendered "
        "without a problem"
    ) in command
    assert "1 when any problem was reported" in command
    assert "`Dashboards: <r> rendered, <u> unchanged, <f> failed.`" in command
    assert "`, <n> checked` when any chart was only checked" in command
    assert "2 for invalid input or configuration" in command
    assert "130 when you interrupt it" in command
    assert "no network request" in command
    assert "`fitdocs index` itself does not run the pass" in command


def test_the_page_is_linked_from_the_documentation_index() -> None:
    docs = Path(__file__).resolve().parents[2] / "docs" / "index.md"
    index = docs.read_text(encoding="utf-8")
    assert "dashboards.md" in _REQUIRED_ENTRY_POINT_LINKS
    analytics_row = index.index("| [Analytics](analytics.md) |")
    dashboards_row = index.index("| [Dashboards](dashboards.md) |")
    contributing_row = index.index("| [Contributing](../CONTRIBUTING.md) |")
    assert analytics_row < dashboards_row < contributing_row


# -- the examples ---------------------------------------------------------------------


def test_bash_fitdocs_lines_name_registered_commands_forms_and_options() -> None:
    page = _page_path().read_text(encoding="utf-8")
    root = get_command(app)
    root_commands = getattr(root, "commands", None)
    assert isinstance(root_commands, dict)
    invocations = _bash_fitdocs_invocations(page)
    assert any(each[0] == "dashboard" for each in invocations)
    forms = {form.value for form in cli._DashboardForm}
    target = re.compile(rf"{SLUG}(:{SLUG})?")

    for invocation in invocations:
        name, *arguments = invocation
        assert name in root_commands, invocation
        options: dict[str, TyperOption] = {}
        for parameter in root_commands[name].params:
            if isinstance(parameter, TyperOption):
                for spelling in (*parameter.opts, *parameter.secondary_opts):
                    options[spelling] = parameter
        positionals: list[str] = []
        index = 0
        while index < len(arguments):
            token = arguments[index]
            if (
                token.startswith("-")
                and len(token) > 1
                and token[1].isalpha()
                or (token.startswith("--"))
            ):
                spelling, separator, _value = token.partition("=")
                assert spelling in options, f"{name}: unregistered option {token!r}"
                if not options[spelling].is_flag and not separator:
                    index += 1
            else:
                positionals.append(token)
            index += 1
        if name == "dashboard":
            form, *targets = positionals
            assert form in forms, invocation
            for each in targets:
                assert target.fullmatch(each), invocation


def test_directive_examples_sit_inside_fences() -> None:
    page = _page_path().read_text(encoding="utf-8")
    scan = scan_page(page, page="dashboards")
    assert scan.lines
    assert scan.directives == ()
    assert scan.regions == ()
    assert scan.problems == ()
    # Positive control: the scanner sees the same example once it is unfenced.
    unfenced = "<!-- fitdocs:chart\n" + _directive_example(page) + "-->\n"
    assert len(scan_page(unfenced, page="dashboards").directives) == 1
    markers = re.findall(r"(?m)^<!-- fitdocs:(?:begin|end):chart:.*-->$", page)
    assert len(markers) == 2
    assert len(scan_page("\n".join(markers) + "\n", page="dashboards").regions) == 1


def test_the_directive_example_parses_without_problems() -> None:
    page = _page_path().read_text(encoding="utf-8")
    parsed = parse_directive(_directive_example(page), open_line=1, page="dashboards")
    assert isinstance(parsed, Directive), parsed
    assert parsed.chart_id == "weekly-km"
    assert parsed.window == "last 12 weeks"
    assert dict(parsed.channels) == {"x": "week_start", "y": "distance_km"}
    assert "$today - 84" in parsed.sql


def test_the_directive_example_checks_clean_against_a_real_index(
    indexed_dashboard_root: IndexedDashboardRoot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = copy_dashboard_root(indexed_dashboard_root, tmp_path)
    for name, value in fixture.environ.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(cli, "_today", lambda: FIXTURE_TODAY)
    page = _page_path().read_text(encoding="utf-8")
    example = "<!-- fitdocs:chart\n" + _directive_example(page) + "-->\n"
    write_page(fixture.root, "weekly-volume", "# Volume\n\n" + example)

    result = CliRunner().invoke(app, ["dashboard", "check", "--out", str(fixture.root)])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[-1] == (
        "Dashboards: 0 rendered, 0 unchanged, 0 failed, 1 checked."
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        regenerate_kinds_block(_page_path())
    elif len(sys.argv) == 2:
        regenerate_kinds_block(Path(sys.argv[1]))
    else:
        raise SystemExit(
            "usage: python -m tests.dashboards.test_docs_dashboards [PAGE]"
        )
