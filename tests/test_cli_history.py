"""CLI tests for the ``history`` command (load-history spec, task 5.3;
Req 4.2, 4.4, 4.5, 8.1, 8.2, 8.4, 8.6, 8.7, 8.8). See the "HistoryCommand
(`src/fitdocs/cli.py`)" component in `.kiro/specs/load-history/design.md`.

Every fixture here is a synthetically written page tree under ``tmp_path``,
built from real frontmatter fences and real ``fitdocs.contract`` vocabulary --
the same pattern ``tests/history/test_engine.py`` uses, driven end-to-end
through ``typer.testing.CliRunner`` and the real ``fitdocs history``
command. No ``.fit`` file is read and no real wiki page is ever used.
"""

from __future__ import annotations

import ast
import inspect
import re
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import cli as cli_module
from fitdocs.cli import app
from fitdocs.layout import WORKOUTS_DIR

runner = CliRunner()

_DOC_REL = "history/training-load-history.md"
_CHART_REL = "history/assets/training-load-history-fitness.svg"


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(
    *,
    day: str,
    load_value: float | None = None,
    load_methodology: str | None = None,
    effort_lines: str = "",
) -> str:
    """A minimal, syntactically valid fitdocs workout document -- matching
    `tests/history/test_engine.py`'s own `_page` fixture builder byte for
    byte, so the archives this module writes are read by the same real
    pipeline that module's engine-level tests exercise."""
    lines = ["---", "title: Test Workout", "type: workout", f'date: "{day}"']
    if load_value is not None:
        lines.append(f"load_value: {load_value}")
    if load_methodology is not None:
        lines.append(f"load_methodology: {load_methodology}")
    if effort_lines:
        lines.append(effort_lines)
    lines.append("---")
    lines.append("")
    lines.append("# Test Workout")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_page(
    root: Path,
    name: str,
    *,
    day: str,
    load_value: float | None = None,
    load_methodology: str | None = None,
    effort_lines: str = "",
) -> Path:
    return _write(
        root,
        f"{WORKOUTS_DIR}/{name}.md",
        _page(
            day=day,
            load_value=load_value,
            load_methodology=load_methodology,
            effort_lines=effort_lines,
        ),
    )


def _write_settings(root: Path, text: str) -> Path:
    return _write(root, "fitdocs.toml", text)


def _write_mixed_archive(root: Path) -> None:
    """Four contributing pages under `banister_1991` -- p1 on 2024-01-01,
    p2 on 2024-01-05 (tagged a race, a criterion point), p9-banister-extra
    on 2024-01-06 and p12-banister-extra2 on 2024-01-09 (tagged a test, a
    second criterion point -- the "more `banister_1991` pages" pages) --
    fixing the series span at 2024-01-01..2024-01-09. Three pages record no
    load at all: p3-unscored-inspan on 2024-01-03 falls strictly between
    p1 and p2 and so is *in* that span (without-load, not out-of-span), while
    p4-unscored-outofspan on 2023-12-25 and p11-unscored-outofspan2 on
    2023-12-20 both fall before the span's own start and so *are*
    out-of-span -- the two counts this fixture keeps apart are "without a
    load" (3: p3, p4, p11) and "out of span" (2: p4, p11 only).

    Three further pages record two excluded methodologies, each with a
    different page count (2 vs 1), so a report that names an excluded
    methodology but drops its count cannot be confused with one that also
    drops the second excluded group; five pages in total carry their own
    race/test criterion tag (p2, p12, p5, p6, p7), deliberately spread
    across contributing and excluded-methodology pages alike, since a
    criterion point is a fact about the tag, not about which methodology
    (if any) the page's own load was recorded under.

    Every one of the six numeric report rows this archive drives is a
    distinct value: pages read 10, contributing 4, without a load 3, out of
    span 2, suppressed weeks 1, criterion points 5 -- so a printer that
    swaps two rows' values, or prints one row's count for another, cannot
    hide behind a coincidental match. Re-derived from a real run of this
    exact fixture:

        ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
        ┃ Result           ┃ Count ┃
        ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
        │ Pages read       │    10 │
        │ Contributing     │     4 │
        │ Without a load   │     3 │
        │ Out of span      │     2 │
        │ Suppressed weeks │     1 │
        │ Criterion points │     5 │
        └──────────────────┴───────┘

    (`p3-unscored-inspan`'s week, 2024-01-01 through 2024-01-07 (ISO week
    2024-W01), has 4 pages
    and 3 with a load -- 0.75 coverage, below the shipped 0.80 threshold --
    which is why `Suppressed weeks` is 1 here, not 0.)"""
    _write_page(
        root, "p1", day="2024-01-01", load_value=5.0, load_methodology="banister_1991"
    )
    _write_page(
        root,
        "p2",
        day="2024-01-05",
        load_value=5.0,
        load_methodology="banister_1991",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1200",
    )
    _write_page(
        root,
        "p9-banister-extra",
        day="2024-01-06",
        load_value=4.0,
        load_methodology="banister_1991",
    )
    _write_page(
        root,
        "p12-banister-extra2",
        day="2024-01-09",
        load_value=2.0,
        load_methodology="banister_1991",
        effort_lines="effort: test\neffort_distance_m: 3000\neffort_time_s: 700",
    )
    _write_page(root, "p3-unscored-inspan", day="2024-01-03")
    _write_page(root, "p4-unscored-outofspan", day="2023-12-25")
    _write_page(root, "p11-unscored-outofspan2", day="2023-12-20")
    _write_page(
        root,
        "p5-trimp-a",
        day="2024-01-11",
        load_value=3.0,
        load_methodology="trimp_legacy",
        effort_lines="effort: race\neffort_distance_m: 5000\neffort_time_s: 1300",
    )
    _write_page(
        root,
        "p6-trimp-b",
        day="2024-01-12",
        load_value=3.0,
        load_methodology="trimp_legacy",
        effort_lines="effort: test\neffort_distance_m: 1000\neffort_time_s: 200",
    )
    _write_page(
        root,
        "p7-other-calc",
        day="2024-01-13",
        load_value=1.0,
        load_methodology="other_calc",
        effort_lines="effort: race\neffort_distance_m: 400\neffort_time_s: 60",
    )
    _write(
        root, f"{WORKOUTS_DIR}/p8-undated.md", _page(day="").replace('date: ""\n', "")
    )
    _write(
        root,
        f"{WORKOUTS_DIR}/p10-undated-second.md",
        _page(day="").replace('date: ""\n', ""),
    )


# ==============================================================================
# Data-root precedence (Req 8.2)
# ==============================================================================


def test_missing_data_root_config_exits_two_listing_three_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors `tests/test_cli.py`'s own `sync`-command version of this test
    (`test_missing_data_root_config_exits_two_listing_three_options`) for
    `history`: with no `--out`, no `FITDOCS_DATA`, and no `.fitdocs/data-root`
    pointer anywhere above the cwd, `history` must resolve its data root
    through the same three-way precedence every other command uses, not
    default to the current directory.

    Named mutation N9 (`data_root = out if out is not None else Path.cwd()`
    in `history_command`, bypassing `_resolved_data_root`): `out` is `None`
    here, so this would resolve `data_root` to `cwd` instead of raising --
    the exit-code assertion reds (`0 != 2`), the message assertions red
    (none of the three option strings are ever printed on a successful run),
    and the archive-untouched assertion reds too, since a `cwd`-rooted run
    would create `cwd / "history"` for this fixture's own page."""
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"  # a directory with no .fitdocs/data-root pointer
    cwd.mkdir()
    # One scored page lives under cwd so a cwd-rooted run would have something
    # to write -- without it the empty-archive path writes nothing and the
    # untouched assertion below could not red under N9.
    _write_page(
        cwd, "a", day="2024-01-01", load_value=5.0, load_methodology="banister_1991"
    )
    monkeypatch.chdir(cwd)

    result = runner.invoke(app, ["history"])

    assert result.exit_code == 2, result.output
    assert "--out" in result.output
    assert "FITDOCS_DATA" in result.output
    assert ".fitdocs/data-root" in result.output
    assert not (cwd / "history").exists()


# ==============================================================================
# Success path (Req 8.1, 8.2, 8.6)
# ==============================================================================


def _row(output: str, label: str) -> str:
    """Return the value cell of the report table row whose left cell is
    ``label``, read directly off the rendered ``rich`` table line (e.g. the
    line ``"│ Pages read       │             7 │"`` for ``label="Pages
    read"``). The pattern is left-anchored on the cell's own opening
    ``│`` (``│\\s*{label}``), not merely on the label text, so a label that
    happens to be a suffix of another row's own label (e.g. a hypothetical
    "Not Pages read" row) can never satisfy a match meant for "Pages read".
    Row-level, not a bare digit-presence check against the whole output: it
    fails if that row's own cell is missing or wrong even when the same
    digit appears elsewhere in the report (another row, an
    excluded-methodology count, a path)."""
    match = re.search(rf"│\s*{re.escape(label)}\s*│\s*(\S+)\s*│", output)
    assert match, f"no report row for {label!r} in:\n{output}"
    return match.group(1)


def test_success_writes_both_outputs_and_prints_the_full_report(
    tmp_path: Path,
) -> None:
    """Every field tasks.md's report bullet lists appears in the printed
    output, with the counts this fixture was built to produce -- pages read
    10, contributing 4, without a load 3, out of span 2, suppressed weeks 1,
    criterion points 5 (see `_write_mixed_archive`'s own docstring for the
    per-page accounting and the real-run table it was checked against) --
    plus one excluded methodology group of 2 (`trimp_legacy`) and one of 1
    (`other_calc`), and two skipped (undated) pages.

    Every one of the six numeric rows above is a distinct integer, so a
    report printer that swaps two rows' underlying fields (e.g. prints
    `pages_out_of_span` under `Contributing`) changes what a specific `_row`
    assertion below reads and reds it, rather than silently matching by
    coincidence.

    Each row assertion below is pinned to its own table line via `_row`, so
    a report printer that drops or corrupts one row cannot hide behind a
    neighbouring row's still-correct digit. Named mutations: R1 (print
    `str(0)` for `criterion_points` regardless of the report value) reds the
    `Criterion points` assertion; R2-R5 (drop the `Contributing` /
    `Without a load` / `Out of span` / `Suppressed weeks` row from the
    printer) each reds exactly its own `_row` assertion below and none of
    the others, since every row is pinned independently; R7 (drop the
    skipped-reason `console.print` line) reds a reason-line check while
    leaving the corresponding skipped path's own assertion untouched, since
    a path and its reason are printed on two separate lines; M1 (swap the
    `Contributing`/`Out of span` fields behind their own rows) reds both the
    `Contributing` and `Out of span` assertions, since `4 != 2` and
    `2 != 4`; M2 (`Without a load` row prints `pages_contributing` instead
    of `pages_without_load`) reds the `Without a load` assertion, since
    `4 != 3`."""
    _write_mixed_archive(tmp_path)

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "banister_1991"]
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / _DOC_REL).exists()
    assert (tmp_path / _CHART_REL).exists()

    output = result.output
    # Named mutation N1b (swap the fields behind the two lines, e.g. print
    # the chart path under "Document:" and the document path under
    # "Chart:"): the exact-label assertions below distinguish the two
    # lines by which label each path sits behind, not merely by the
    # paths' presence somewhere in the output -- the swap reds whichever
    # of the two document/chart fixtures actually differ in string, and
    # since `_DOC_REL` and `_CHART_REL` are distinct strings here, both
    # assertions red under the swap.
    assert f"Document: {_DOC_REL}" in output
    assert f"Chart: {_CHART_REL}" in output

    assert _row(output, "Pages read") == "10"
    assert _row(output, "Contributing") == "4"
    assert _row(output, "Without a load") == "3"
    assert _row(output, "Out of span") == "2"
    assert _row(output, "Suppressed weeks") == "1"
    assert _row(output, "Criterion points") == "5"
    assert _row(output, "Methodology") == "banister_1991"

    # Excluded methodologies, each named with its own distinct count.
    assert "trimp_legacy: 2" in output
    assert "other_calc: 1" in output

    # p8-undated.md and p10-undated-second.md are the two skipped pages;
    # the line right after each path is that page's own skip reason, not
    # some other page's or an unrelated line -- both are checked so a
    # printer that renders only the first skip cannot pass by covering one.
    lines = output.splitlines()
    for skipped_name in ("p8-undated.md", "p10-undated-second.md"):
        skip_index = next(i for i, line in enumerate(lines) if skipped_name in line)
        assert lines[skip_index + 1].strip() == (
            "the document's recorded date could not be read"
        )

    # The empty-archive note is a success-path-only field; it must never
    # print on this (non-empty) run. Named mutation M7 (drop the
    # `if report.note is not None:` guard around the note's own
    # `console.print` call): `report.note` is `None` here, so the bare
    # print no longer emits the note's own prose (the substring check
    # above would stay green either way) -- it emits the literal string
    # "None" as its own line, and as the very last thing this report
    # prints, since nothing in `_report_history` runs after the note
    # block. Both assertions below name that: no line is the bare
    # literal "None", and the output's last non-empty line is still the
    # final skipped page's own reason line, not a stray "None" appended
    # after it.
    lines_for_note = [line for line in output.splitlines() if line.strip() != ""]
    assert "None" not in [line.strip() for line in lines_for_note]
    assert lines_for_note[-1].strip() == (
        "the document's recorded date could not be read"
    )


def test_excluded_methodology_counts_survive_a_dropped_count_mutation(
    tmp_path: Path,
) -> None:
    """An isolation test, not an extra-discrimination one: the success test
    above already asserts the count-bearing strings `"trimp_legacy: 2"` and
    `"other_calc: 1"` (not a bare `"trimp_legacy" in output"` substring
    check), so both tests already red under the named mutation below. This
    one exists to pin the excluded-methodology bullet on its own, isolated
    from the success test's dozen other assertions -- so a failure here
    means the excluded-methodology count line specifically broke,
    without needing to first rule out every other row on the report.

    Named mutation: change the excluded-methodology print line from
    ``f"  {name}: {count}"`` to ``f"  {name}"`` -- `"trimp_legacy: 2"` and
    `"other_calc: 1"` both vanish from the output and this test reds."""
    _write_mixed_archive(tmp_path)

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "banister_1991"]
    )

    assert result.exit_code == 0, result.output
    assert "trimp_legacy: 2" in result.output
    assert "other_calc: 1" in result.output


# ==============================================================================
# --methodology option (Req 4.4)
# ==============================================================================


def test_methodology_option_selects_named_methodology(tmp_path: Path) -> None:
    """Two methodologies are present (ambiguous without a choice); naming one
    via `--methodology` resolves it rather than erroring.

    Named mutation: drop the `methodology=methodology` keyword from the
    `run_history(...)` call in `history_command` (or otherwise fail to
    thread the option through) -- the run would then see no requested and no
    configured methodology, `select_methodology` would return a
    `MethodologyProblem` for the still-ambiguous archive, and this test's
    `exit_code == 0` assertion reds."""
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path, "b", day="2024-01-02", load_value=5.0, load_methodology="trimp_legacy"
    )

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "trimp_legacy"]
    )

    assert result.exit_code == 0, result.output
    assert "trimp_legacy" in result.output
    doc_text = (tmp_path / _DOC_REL).read_text(encoding="utf-8")
    assert "trimp_legacy" in doc_text


# ==============================================================================
# Ambiguous-methodology path (Req 4.4, 8.4): configuration exit, nothing
# written, both identifiers AND their counts in the message.
# ==============================================================================


def test_ambiguous_methodology_exits_two_writes_nothing_names_ids_and_counts(
    tmp_path: Path,
) -> None:
    """Two methodologies, each recorded by a *different* page count (1 vs 2),
    so a message that names both ids but reports the wrong count -- or the
    same count for both -- is distinguishable from a correct one.

    Named mutation (from the task's own list): map the
    `MethodologyConfigurationError` to the failure exit (1) instead of the
    configuration exit (2) -- the exit-code assertion below reds while the
    message-content assertions stay green, which is exactly why both are
    asserted here rather than exit code alone."""
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_page(
        tmp_path, "b", day="2024-01-02", load_value=5.0, load_methodology="trimp_legacy"
    )
    _write_page(
        tmp_path, "c", day="2024-01-03", load_value=5.0, load_methodology="trimp_legacy"
    )

    result = runner.invoke(app, ["history", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert "'banister_1991' (1 pages)" in result.output
    assert "'trimp_legacy' (2 pages)" in result.output
    assert not (tmp_path / "history").exists()


# ==============================================================================
# Requested-but-absent methodology path (Req 4.5, 8.4): configuration exit,
# nothing written, both the requested id and the present ones named.
# ==============================================================================


def test_requested_methodology_absent_from_archive_exits_two_names_both(
    tmp_path: Path,
) -> None:
    """A single-methodology archive (`banister_1991`); the run requests a
    methodology no page in the archive records at all (`nope`). Req 4.5
    requires the error to name both the requested id and the methodologies
    that are actually present, and to write no page.

    Named mutation: drop the "methodologies present" clause from the
    `MethodologyConfigurationError` message (name only the requested id) --
    the `'banister_1991' (1 pages)` assertion below reds while the
    `'nope'` assertion stays green, which is exactly why both are
    asserted."""
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "nope"]
    )

    assert result.exit_code == 2, result.output
    assert "'nope'" in result.output
    assert "'banister_1991' (1 pages)" in result.output
    assert not (tmp_path / "history").exists()


# ==============================================================================
# Malformed-settings path (Req 8.4): configuration exit.
# ==============================================================================


def test_malformed_history_settings_table_exits_two_writes_nothing(
    tmp_path: Path,
) -> None:
    _write_page(
        tmp_path,
        "a",
        day="2024-01-01",
        load_value=5.0,
        load_methodology="banister_1991",
    )
    _write_settings(tmp_path, "[history]\ntau_fitness_days = true\n")

    result = runner.invoke(app, ["history", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert not (tmp_path / "history").exists()


# ==============================================================================
# Empty-archive path (Req 1.10 via the engine; 8.8 "not on their own a
# failure"): success exit, note printed.
# ==============================================================================


def test_empty_archive_exits_zero_and_prints_the_note(tmp_path: Path) -> None:
    """Named mutation (the note not printed on the empty path): delete the
    `if report.note is not None: console.print(report.note)` block (or
    equivalent) from the CLI's report printer -- `report.note` itself is
    non-empty prose this fixture is built to make non-trivial, so the string
    below is never emitted by anything else in this run's output, and the
    assertion reds."""
    _write_page(tmp_path, "unscored", day="2024-01-01")

    result = runner.invoke(app, ["history", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "no page in the archive records a load" in result.output
    assert not (tmp_path / "history").exists()


# ==============================================================================
# Write-failure path (Req 8.8): failure exit.
# ==============================================================================


@pytest.fixture
def _restore_permissions() -> Iterator[list[Path]]:
    locked: list[Path] = []
    yield locked
    for path in locked:
        path.chmod(stat.S_IRWXU)


def test_write_failure_exits_one_and_reports_it(
    tmp_path: Path, _restore_permissions: list[Path]
) -> None:
    """The chart's own directory is unwritable; the run must exit failure (1),
    not success.

    Named mutation (from the task's own list, restated for the CLI's own
    exit computation rather than the engine's): replace
    `bool(history_report.failures)` with `False` in the CLI's `_finish(...)`
    call for this command -- the run would still fail internally (the engine
    reports one failure and writes no document) but the process would exit
    `0`, and the exit-code assertion below reds.

    Named mutation N7 (drop the `f"    {reason}"` print for the failed
    chart's own line in `_report_history`): the path assertion alone
    still holds (the failed path's own line is unaffected), so the
    reason assertion below is pinned separately -- with the line right
    after the chart path gone, `lines[chart_index + 1]` either raises
    an `IndexError` (the chart path was the report's last line) or
    reads some unrelated later line that does not carry the OS error
    text, and either way the `Permission denied` check reds."""
    _write_mixed_archive(tmp_path)
    assets_dir = tmp_path / "history" / "assets"
    assets_dir.mkdir(parents=True)
    assets_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+traverse, no write
    _restore_permissions.append(assets_dir)

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "banister_1991"]
    )

    assert result.exit_code == 1, result.output
    assert _CHART_REL in result.output
    lines = result.output.splitlines()
    chart_index = next(i for i, line in enumerate(lines) if _CHART_REL in line)
    assert "Permission denied" in lines[chart_index + 1]


# ==============================================================================
# Foreign-path reporting (Req 7.6, tasks.md's own bullet "each foreign path").
# ==============================================================================


def test_foreign_paths_are_each_named_in_the_report(tmp_path: Path) -> None:
    """Both output paths are pre-occupied by files this tool never wrote (no
    generated-provenance marker); the run writes neither and names both.

    Named mutation (a foreign path not printed): print only the first entry
    of the foreign-path list (e.g. slice `[:1]`) instead of iterating all of
    it -- since this fixture pre-occupies *both* the document and the chart
    path, exactly one of the two path assertions below reds while the other
    stays green, distinguishing a partial listing from a correct one."""
    _write_mixed_archive(tmp_path)
    _write(tmp_path, _DOC_REL, "not fitdocs content\n")
    _write(tmp_path, _CHART_REL, "<svg></svg>\n")

    result = runner.invoke(
        app, ["history", "--out", str(tmp_path), "--methodology", "banister_1991"]
    )

    assert result.exit_code == 0, result.output
    assert _DOC_REL in result.output
    assert _CHART_REL in result.output
    assert (tmp_path / _DOC_REL).read_text(encoding="utf-8") == "not fitdocs content\n"
    assert (tmp_path / _CHART_REL).read_text(encoding="utf-8") == "<svg></svg>\n"


# ==============================================================================
# Option set: no --force, no --recompute (design.md HistoryCommand).
# ==============================================================================


def test_history_command_has_no_force_or_recompute_option() -> None:
    """The page is always rebuilt in full -- asserted directly against the
    command's own signature, not merely against `--help` prose.

    Named mutation: add a `force: bool = _FORCE_OPTION` (or `recompute`)
    parameter to `history_command` -- the forbidden-name assertion below
    reds."""
    source = inspect.getsource(cli_module)
    tree = ast.parse(source)
    history_funcs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "history_command"
    ]
    assert len(history_funcs) == 1
    params = {arg.arg for arg in history_funcs[0].args.args}
    assert "force" not in params
    assert "recompute" not in params
    assert params == {"out", "methodology"}


def test_history_is_a_distinctly_named_command_registered_on_the_app() -> None:
    result = runner.invoke(app, ["--help"])
    assert "history" in result.output


# ==============================================================================
# 8.7: not chained onto sync, regen or load -- only `history_command`'s own
# body may reach `run_history`.
# ==============================================================================


def test_no_other_command_implementation_reaches_run_history() -> None:
    """Structural absence test, closed module-wide (`ast.walk(tree)`
    everywhere below, never `tree.body` or a single function's own body) so
    a routing-around call site cannot hide merely by sitting outside the
    three named command functions the original, per-function version of
    this guard inspected.

    Three independent, module-wide guards:

    (a) Every `ast.Import`/`ast.ImportFrom` node ANYWHERE in the module
        whose imported module or aliased name starts with
        `fitdocs.history` is exactly one node: the module-level
        `from fitdocs.history.engine import HistoryReport, run_history`,
        pinned by equality on `(module, [(name, asname), ...])` -- not just
        counted, but matched exactly, so a second such import (local,
        aliased, or a plain `import fitdocs.history...`) anywhere in the
        module -- not only inside `sync_command`/`regen_command`/
        `load_command` -- fails this assertion regardless of whether its
        call site is ever reached as an `ast.Name` or an `ast.Attribute`.
    (b) Every `ast.Name` *load* of `run_history` anywhere in the module
        numbers exactly one, and that one sits inside `history_command`'s
        own body -- ruling out both a second call site under the plain name
        anywhere else, and a module-level alias (`_x = run_history`) that a
        per-function `ast.Call` scan would never see, since the bare name
        reference itself is what this guard counts, not just its use as a
        call.
    (c) Zero `ast.Attribute` nodes anywhere in the module have `attr ==
        "run_history"` -- ruling out routing through an attribute access on
        any bound object (`_he.run_history(...)`, `cli_module.run_history`,
        etc.), from any function, at any nesting depth.

    Named mutations: A6 (module-level
    `from fitdocs.history import run_history as _rh3` plus
    `_rh3(data_root)` in `load_command`) reds guard (a) -- a second history
    import now exists, regardless of its call site never appearing as
    `run_history` by name. A7 (module-level `_rh4 = run_history` plus
    `_rh4(data_root)` in `load_command`) reds guard (b) -- the assignment's
    own right-hand side is a second `ast.Name` load of `run_history`,
    outside `history_command`, even though the actual call site uses the
    alias `_rh4` and so is invisible to a scan that only counts `ast.Call`
    nodes."""
    source = inspect.getsource(cli_module)
    tree = ast.parse(source)

    # (a) Every history-family import anywhere is exactly the one expected
    # module-level import.
    history_imports = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Import)
            and any(alias.name.startswith("fitdocs.history") for alias in node.names)
        )
        or (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("fitdocs.history")
        )
    ]
    assert len(history_imports) == 1
    (only_history_import,) = history_imports
    assert isinstance(only_history_import, ast.ImportFrom)
    assert only_history_import.module == "fitdocs.history.engine"
    assert [(alias.name, alias.asname) for alias in only_history_import.names] == [
        ("HistoryReport", None),
        ("run_history", None),
    ]

    # (b) Every ast.Name load of run_history, anywhere, numbers exactly
    # one, and it sits inside history_command's own body.
    history_command = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "history_command"
    )
    all_run_history_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "run_history"
    ]
    assert len(all_run_history_names) == 1
    names_inside_history_command = [
        node
        for node in ast.walk(history_command)
        if isinstance(node, ast.Name) and node.id == "run_history"
    ]
    assert names_inside_history_command == all_run_history_names

    # (c) Zero attribute accesses named run_history, anywhere.
    attribute_accesses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "run_history"
    ]
    assert attribute_accesses == []
