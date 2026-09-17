"""CLI tests for the ``plan`` command (training-blocks spec, task 4.3; Req
8.2, 8.3, 8.6, 8.8, 8.9). See the "PlanCommand (`src/fitdocs/cli.py`)"
component in `.kiro/specs/training-blocks/design.md`.

Every plan source here is a copy of `tests/plans/fixtures/{minimal,full}.toml`'s
own bytes, written into a synthetic ``plans/`` directory under ``tmp_path`` --
the plan's hard rules forbid any write, in code or in a test's assertions,
under the resolved plan-source directory itself, so every fixture below
writes the source *before* the run and never touches it afterward. No
``.fit`` file is read and no real wiki page is ever used.
"""

from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import cli as cli_module
from fitdocs.cli import _report_plan, app
from fitdocs.contract import DATE_KEY, GENERATED_PREFIX
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.plans.engine import BlockOutcome, BlockStatus, PlanReport
from fitdocs.plans.model import PlanProblem
from fitdocs.plans.source import PlanValidationError, load_block

runner = CliRunner()

FIXTURES = Path(__file__).parent / "plans" / "fixtures"
_MINIMAL = (FIXTURES / "minimal.toml").read_bytes()
_FULL = (FIXTURES / "full.toml").read_bytes()


def _plans_dir(root: Path, name: str = "plans") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _stage_w1_mon_override_stem(root: Path) -> Path:
    """A minimal, syntactically valid fitdocs workout document staged at
    `workouts/run-2026-01-06-am.md` -- the fixture's `w1-mon` override
    (`tests/plans/fixtures/full.toml`) names this stem; under
    plan-resolution's chained resolver (Req 8.2/8.7) a missing override
    stem is a per-file failure, so the page is staged to keep this a
    success run. Shape copied from `tests/plans/test_reconcile.py::_page`."""
    path = root / WORKOUTS_DIR / "run-2026-01-06-am.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "title: Test Workout",
                "type: workout",
                f'{DATE_KEY}: "2026-01-06"',
                "sport: Run",
                "---",
                "",
                "# Test Workout",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_settings(root: Path, text: str) -> Path:
    path = root / "fitdocs.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ==============================================================================
# Data-root precedence (Req 8.2)
# ==============================================================================


def test_missing_data_root_config_exits_two_listing_three_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors `tests/test_cli_history.py`'s own version of this test for
    `plan`: with no `--out`, no `FITDOCS_DATA`, and no `.fitdocs/data-root`
    pointer anywhere above the cwd, `plan` must resolve its data root
    through the same three-way precedence every other command uses.

    Named mutation (`data_root = out if out is not None else Path.cwd()` in
    `plan_command`, bypassing `_resolved_data_root`): `out` is `None` here,
    so this would resolve `data_root` to `cwd` instead of raising -- the
    exit-code assertion reds (`0 != 2`) and the message assertions red
    (none of the three option strings are ever printed on a successful
    run); those two are what the mutation actually catches."""
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    result = runner.invoke(app, ["plan"])

    assert result.exit_code == 2, result.output
    assert "--out" in result.output
    assert "FITDOCS_DATA" in result.output
    assert ".fitdocs/data-root" in result.output
    # A safety check, not itself the mutation's discriminating signal: under
    # the bypass mutation described above, `cwd` has no `plans/` directory
    # either, so the default-absent-and-unconfigured path would print a note
    # and exit 0 without creating `blocks/` -- the exit-code and message
    # assertions above are what actually catches the bypass.
    assert not (cwd / "blocks").exists()


# ==============================================================================
# The success path: the report, and the +n planned / -m removed counts
# (Req 8.6).
# ==============================================================================


def test_success_prints_every_outcome_line_and_the_counts(tmp_path: Path) -> None:
    """Two fresh sources -- `full.toml` (5 current rows) and `minimal.toml`
    (1 current row) -- each render for the first time, so every planned page
    and the block page are all newly written; the counts pin the exact
    `(+n planned, -m removed)` shape design.md states, and the fixed,
    sorted-by-name discovery order pins which line comes first.

    Named mutation (swap `outcome.removed` and `outcome.written` counts in
    the format string): both count assertions below red, since `full` has a
    non-zero planned count and a zero removed count while a swap would print
    them the other way around."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "full.toml").write_bytes(_FULL)
    (source_dir / "minimal.toml").write_bytes(_MINIMAL)
    _stage_w1_mon_override_stem(tmp_path)

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Source: plans" in result.output
    assert (
        "rendered  plans/full.toml -> blocks/full.md (+5 planned, -0 removed)"
        in result.output
    )
    assert (
        "rendered  plans/minimal.toml -> blocks/minimal.md (+1 planned, -0 removed)"
        in result.output
    )
    full_index = result.output.index("plans/full.toml")
    minimal_index = result.output.index("plans/minimal.toml")
    assert full_index < minimal_index
    assert (tmp_path / "blocks" / "full.md").exists()
    assert (tmp_path / "blocks" / "minimal.md").exists()


def test_second_run_planned_count_excludes_unwritten_block_page(
    tmp_path: Path,
) -> None:
    """`minimal.toml` records no amendments, so `w1-mon` is an *original*
    row with no `[[amendment.update]]` recording any change to it; neither
    the current-plan day table nor the "as first written" table ever prints
    a row's prescription text (only an amendment's own change bullets do),
    so editing `w1-mon`'s prescription in place between the two runs below
    rewrites the planned page but leaves the block page's bytes -- and so
    its membership in `written` -- unchanged. This directly pins the
    `+n planned` computation against the naive `len(written) - 1`, which
    would read 0 here instead of 1.

    Named mutation (`planned = len(outcome.written) - 1` in `_report_plan`
    instead of filtering `written` by the derived block-page path): this
    test's `+1 planned` assertion reds (the naive form prints `+0 planned`)
    while `test_success_prints_every_outcome_line_and_the_counts` -- a
    first-run, everything-new fixture where the naive and filtered forms
    agree -- stays green, showing the naive form is the one this test
    catches."""
    source_dir = _plans_dir(tmp_path)
    source = source_dir / "a.toml"
    source.write_bytes(_MINIMAL)

    first = runner.invoke(app, ["plan", "--out", str(tmp_path)])
    assert first.exit_code == 0, first.output
    block_page_bytes_before = (tmp_path / "blocks" / "a.md").read_bytes()

    changed = _MINIMAL.decode("utf-8").replace(
        'prescription = "30 minutes easy."',
        'prescription = "45 minutes easy, negative split."',
    )
    assert changed != _MINIMAL.decode("utf-8")
    source.write_text(changed, encoding="utf-8")

    second = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert second.exit_code == 0, second.output
    assert "rendered  plans/a.toml -> blocks/a.md (+1 planned, -0 removed)" in (
        second.output
    )
    assert (tmp_path / "blocks" / "a.md").read_bytes() == block_page_bytes_before


# ==============================================================================
# An invalid source (Req 8.6, 8.9).
# ==============================================================================


def test_invalid_source_exits_one_with_problems_printed_verbatim(
    tmp_path: Path,
) -> None:
    """Each `PlanProblem.describe()` line is printed indented, verbatim --
    pinned against the real problem text `load_block` itself produces for
    this exact malformed source, not a hand-written guess.

    Named mutation (drop the `for problem in outcome.problems:` loop from
    `_report_plan`): the describe()-text assertion reds while the
    `invalid   plans/bad.toml` line's own assertion stays green, since only
    the indented detail line depends on the dropped loop."""
    source_dir = _plans_dir(tmp_path)
    bad_source = source_dir / "bad.toml"
    bad_source.write_text("not = [valid", encoding="utf-8")

    with pytest.raises(PlanValidationError) as exc_info:
        load_block(bad_source, block_id="bad")
    (expected_problem,) = exc_info.value.problems

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "invalid   plans/bad.toml" in result.output
    assert f"  {expected_problem.describe()}" in result.output


# ==============================================================================
# A malformed [plans] table (Req 8.3): configuration exit, nothing created.
# ==============================================================================


def test_malformed_plans_table_exits_two_and_creates_no_blocks_dir(
    tmp_path: Path,
) -> None:
    """`path = true` is rejected outright (`bool` is not a `str`), by
    `load_plan_settings` itself, before any directory is ever resolved.

    Named mutation (map `PlanSettingsError` to `_finish(failed=True)`
    instead of `_config_error`): the exit-code assertion reds (`1 != 2`).
    The "nothing created" assertion does not discriminate this particular
    mutation -- `load_plan_settings` raises before any write either way --
    it instead guards the test's own premise (a malformed table truly
    writes nothing) against a future change to `run_plan`'s ordering."""
    _write_settings(tmp_path, "[plans]\npath = true\n")

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert not (tmp_path / "blocks").exists()
    # Req 8.3: the configuration error names the settings file and the
    # offending key -- matched on the filename rather than the full path,
    # since Rich may soft-wrap a long absolute path across lines.
    assert "fitdocs.toml" in result.output
    assert "path" in result.output


def test_configured_absent_directory_exits_two(tmp_path: Path) -> None:
    _write_settings(tmp_path, '[plans]\npath = "does-not-exist"\n')

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert not (tmp_path / "blocks").exists()
    assert "fitdocs.toml" in result.output
    assert "path" in result.output


def test_default_absent_directory_exits_zero_with_note(tmp_path: Path) -> None:
    """No `[plans]` table at all and no `plans/` directory present: the
    default-and-absent case is success with an explanatory note, not a
    configuration error (Req 1.10, 8.9) -- distinct from
    `test_configured_absent_directory_exits_two`, where the same absence is
    an error because the athlete named the path explicitly.

    Named mutation (drop the `if plan_settings.path is None:` branch in
    `plans.engine.run_plan`, always raising `PlanSettingsError`): out of
    boundary for this task (that branch belongs to task 4.2), but this test
    still pins the CLI's own report/finish wiring by asserting the note text
    the engine already returns actually reaches stdout and drives exit 0."""
    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "no plan source directory" in result.output
    assert not (tmp_path / "blocks").exists()


# ==============================================================================
# A blocked block (Req 7.8, 8.9).
# ==============================================================================


def test_blocked_block_exits_one_naming_the_path(tmp_path: Path) -> None:
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    foreign_block_page = tmp_path / "blocks" / "a.md"
    foreign_block_page.parent.mkdir(parents=True)
    foreign_block_page.write_text("hand-written, not fitdocs'\n", encoding="utf-8")

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "blocked   plans/a.toml: blocks/a.md" in result.output
    assert (
        foreign_block_page.read_text(encoding="utf-8") == "hand-written, not fitdocs'\n"
    )


# ==============================================================================
# A failed block (Req 8.6, 8.9): a write failure mid-block.
# ==============================================================================


def test_failed_block_exits_one_naming_path_and_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`os.replace` -- the atomic-write step's last call, inside
    `plans.engine._atomic_write` -- is patched to always raise, so the very
    first write (`blocks/a/w1-mon.md`, the only planned page `minimal.toml`
    has) fails; the block's outcome carries `(path, reason)` and the CLI
    must print it, not just carry it in the report object. Patches the real
    `os` module (the same object `fitdocs.plans.engine` imported) rather
    than `fitdocs.plans.engine.os`, so the patch target is unaffected by
    strict mypy's implicit-re-export rule.

    Named mutation (drop the `for path, reason in outcome.failures:` loop
    from `_report_plan`): the exact-line assertion reds while the
    exit-code assertion (driven by `report.failed`, computed by the engine
    regardless of what the CLI prints) stays green."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)

    def _raise_on_replace(*args: object, **kwargs: object) -> None:
        raise OSError("disk says no")

    monkeypatch.setattr(os, "replace", _raise_on_replace)

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert (
        "failed    plans/a.toml: blocks/a/w1-mon.md: OSError: disk says no"
        in result.output
    )


# ==============================================================================
# A kept-foreign page under a rendered or unchanged block (Req 7.9): not in
# design.md's PlanCommand line list -- flagged in this task's own status
# report for the controller to queue as a design-reconciliation follow-up
# under `.kiro/queue/`.
# ==============================================================================


def test_kept_foreign_page_is_reported_on_a_rendered_block(tmp_path: Path) -> None:
    """A non-generated file left alone in a block's pages directory is
    reported to the athlete, not just carried silently in
    `BlockOutcome.foreign` (Req 7.9) -- the engine already leaves it
    untouched and reports it there for RENDERED and UNCHANGED blocks alike;
    this pins that the CLI actually prints it.

    Named mutation (drop the `_print_kept_foreign(outcome.foreign)` call
    after the `rendered` line): the `kept (not fitdocs')` assertion reds
    while the `rendered` line's own assertion stays green, since dropping
    only that call changes nothing else about the printed report."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    pages_dir = tmp_path / "blocks" / "a"
    pages_dir.mkdir(parents=True)
    foreign_page = pages_dir / "mine.md"
    foreign_page.write_text("hand-written, not fitdocs'\n", encoding="utf-8")
    foreign_bytes = foreign_page.read_bytes()

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (
        "rendered  plans/a.toml -> blocks/a.md (+1 planned, -0 removed)"
        in result.output
    )
    assert "  kept (not fitdocs'): blocks/a/mine.md" in result.output
    assert foreign_page.read_bytes() == foreign_bytes


# ==============================================================================
# The removed count (Req 8.6): a stale generated planned page.
# ==============================================================================


def test_removed_count_reflects_stale_generated_page_removal(tmp_path: Path) -> None:
    """A stale generated planned page for a row no longer current is
    removed and counted; every other counts assertion in this module
    expects `-0 removed` (no fixture here pre-seeds a stale page), which a
    hard-coded `-0 removed` constant would satisfy just as well -- this is
    the one fixture that actually exercises a non-zero removed count.

    Named mutation (`f"-0 removed"` in place of
    `f"-{len(outcome.removed)} removed"`): this test's `-1 removed`
    assertion reds while every other counts assertion in this module stays
    green."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    pages_dir = tmp_path / "blocks" / "a"
    pages_dir.mkdir(parents=True)
    stale = pages_dir / "stale.md"
    stale.write_text(f"{GENERATED_PREFIX} -->\nstale content\n", encoding="utf-8")

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (
        "rendered  plans/a.toml -> blocks/a.md (+1 planned, -1 removed)"
        in result.output
    )
    assert not stale.exists()


# ==============================================================================
# `No source:` and `Declaration not placed (foreign):` lines (Req 8.6).
# ==============================================================================


def test_unsourced_page_is_reported(tmp_path: Path) -> None:
    """A stray `blocks/*.md` with no matching source is listed under `No
    source:` and left untouched -- the run still succeeds (no invalid,
    blocked or failed block).

    Named mutation (drop the `for path in report.unsourced:` loop from
    `_report_plan`): the `No source:` assertion reds while every other
    assertion in this module stays green, since dropping only that loop
    changes nothing else about the printed report."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    stray = tmp_path / "blocks" / "orphan.md"
    stray.parent.mkdir(parents=True)
    stray.write_text("<!-- fitdocs:generated by a prior run -->\n", encoding="utf-8")

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "No source: blocks/orphan.md" in result.output


def test_declaration_not_placed_foreign_is_reported(tmp_path: Path) -> None:
    """A non-generated `blocks/AGENTS.md` blocks that directory's
    declaration refresh; the block itself still renders and the run still
    succeeds -- a foreign declaration is reported, not a failure.

    Named mutation (drop the `for path in report.declarations_foreign:`
    loop from `_report_plan`): the `Declaration not placed` assertion reds
    while the exit-code and `rendered` assertions stay green, since
    dropping only that loop changes nothing else about the printed report
    or the run's outcome."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir(parents=True)
    (blocks_dir / "AGENTS.md").write_text(
        "hand-written, not fitdocs'\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Declaration not placed (foreign): blocks/AGENTS.md" in result.output
    assert (
        "rendered  plans/a.toml -> blocks/a.md (+1 planned, -0 removed)"
        in result.output
    )


# ==============================================================================
# `unchanged` is a distinct status from `rendered` (Req 8.6).
# ==============================================================================


def test_second_identical_run_reports_unchanged_not_rendered(tmp_path: Path) -> None:
    """Running the same source twice, unmodified, writes nothing the second
    time -- the block's status is `unchanged`, never `rendered`.

    Named mutation (print `rendered` unconditionally instead of branching on
    `outcome.status`): the `unchanged` assertion reds (the literal string
    never appears) while `test_success_prints_every_outcome_line_and_the_counts`
    stays green, since that test's first-run fixture is genuinely `rendered`
    either way."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)

    first = runner.invoke(app, ["plan", "--out", str(tmp_path)])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert second.exit_code == 0, second.output
    assert "unchanged plans/a.toml" in second.output
    assert "rendered" not in second.output


# ==============================================================================
# Report-rendering unit test (Req 8.6): a direct call against a hand-built
# `PlanReport`, in the shape `tests/test_cli_derive.py` uses for
# `_report_derive` -- markup safety on every print call, the `blocked`
# loop's full path listing (not just its first entry), and `soft_wrap`.
# ==============================================================================


def test_report_plan_prints_brackets_literally_and_lists_every_blocked_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hand-built `PlanReport` covering every status -- RENDERED (short
    and, separately, long-path), UNCHANGED, BLOCKED, INVALID and FAILED --
    each with a bracketed value somewhere in its own printed line (the
    source directory, a block id, a source path, a problem message, a
    failure reason, a kept-foreign path, the unsourced/declaration paths,
    and the note), so a `console.print` call missing `markup=False`
    anywhere in `_report_plan` is caught independently of every other call
    (Rich would render `[bold]` as bold and strip it from the captured
    text, breaking only that one exact-line assertion). The BLOCKED
    outcome carries TWO foreign paths, so a loop that prints only the
    first is caught independently of
    `test_blocked_block_exits_one_naming_the_path` (which seeds only one
    path and so cannot tell "all" from "first"). The UNCHANGED outcome
    also carries a `foreign` entry, pinning the second
    `_print_kept_foreign` call site (RENDERED's call site is pinned
    separately by `test_kept_foreign_page_is_reported_on_a_rendered_block`,
    an end-to-end test; dropping only the UNCHANGED call site here would
    otherwise survive every other test in this module). `_report_plan` is
    called directly against this synthetic report -- no CLI invocation, no
    real plan source, no filesystem write: `block_doc_path` is pure path
    composition, so `data_root` never needs to exist.

    `soft_wrap` is pinned by this test only on the RENDERED line, via the
    dedicated long-path outcome below (over 120 columns); the other
    bracketed lines are short and do not additionally pin `soft_wrap` at
    their own call sites -- each of those already has its own `soft_wrap`
    parameter, matching every other detail line's call shape in
    `_report_plan`, but no fixture here specifically exercises wrapping at
    every one of them.

    Named mutations:
    - drop `markup=False` from the `rendered` line's own `console.print`
      call -> the bracketed block-id line's exact-string assertion reds
      (Rich strips `[bold]` under markup) while every other line's
      assertion stays green.
    - drop `markup=False` from the `Source:` line -> only the `Source:`
      assertion reds.
    - drop `markup=False` from the `invalid` header line -> only the
      `invalid` line's assertion reds.
    - drop `markup=False` from the `unchanged` line, or from its
      `_print_kept_foreign` call -> only the corresponding assertion reds.
    - `for path in outcome.foreign[:1]:` in the BLOCKED branch instead of
      the full iteration -> the second bracketed foreign-path assertion
      reds while the first stays green.
    - drop the `_print_kept_foreign(outcome.foreign)` call after the
      `unchanged` line -> only the UNCHANGED kept-foreign assertion reds.
    - drop `soft_wrap=True` from the `rendered` line's `console.print`
      call -> the long-path line wraps across multiple output lines under
      Rich's default (non-tty, 80-column) width, so the exact-line
      assertion (which expects the whole path on one line) reds."""
    long_source = "plans/" + ("nested/" * 20) + "very-long-block-id.toml"
    assert len(long_source) > 120

    report = PlanReport(
        source_dir="[bold]plans",
        blocks=(
            BlockOutcome(
                source="plans/[bold]-rendered.toml",
                block_id="[bold]-rendered",
                status=BlockStatus.RENDERED,
                written=("blocks/[bold]-rendered/w1-mon.md",),
                removed=(),
                problems=(),
                foreign=(),
                failures=(),
            ),
            BlockOutcome(
                source=long_source,
                block_id="very-long-block-id",
                status=BlockStatus.RENDERED,
                written=(),
                removed=(),
                problems=(),
                foreign=(),
                failures=(),
            ),
            BlockOutcome(
                source="plans/[bold]-unchanged.toml",
                block_id="[bold]-unchanged",
                status=BlockStatus.UNCHANGED,
                written=(),
                removed=(),
                problems=(),
                foreign=("blocks/[bold]-unchanged/[kept].md",),
                failures=(),
            ),
            BlockOutcome(
                source="plans/blocked.toml",
                block_id="blocked",
                status=BlockStatus.BLOCKED,
                written=(),
                removed=(),
                problems=(),
                foreign=("blocks/[first].md", "blocks/[second].md"),
                failures=(),
            ),
            BlockOutcome(
                source="plans/[bold]-invalid.toml",
                block_id="invalid",
                status=BlockStatus.INVALID,
                written=(),
                removed=(),
                problems=(
                    PlanProblem(entry="file", field=None, message="a [bold] problem"),
                ),
                foreign=(),
                failures=(),
            ),
            BlockOutcome(
                source="plans/failed.toml",
                block_id="failed",
                status=BlockStatus.FAILED,
                written=(),
                removed=(),
                problems=(),
                foreign=(),
                failures=(("blocks/failed.md", "a [bold] reason"),),
            ),
        ),
        unsourced=("blocks/[x].md",),
        declarations_foreign=("blocks/[decl].md",),
        note="[bold]n[/bold]",
    )

    _report_plan(report, data_root=tmp_path)

    lines = capsys.readouterr().out.splitlines()

    assert "Source: [bold]plans" in lines
    assert (
        "rendered  plans/[bold]-rendered.toml -> blocks/[bold]-rendered.md "
        "(+1 planned, -0 removed)"
    ) in lines
    assert (
        f"rendered  {long_source} -> blocks/very-long-block-id.md "
        "(+0 planned, -0 removed)"
    ) in lines
    assert "unchanged plans/[bold]-unchanged.toml" in lines
    assert "  kept (not fitdocs'): blocks/[bold]-unchanged/[kept].md" in lines
    assert "blocked   plans/blocked.toml: blocks/[first].md" in lines
    assert "blocked   plans/blocked.toml: blocks/[second].md" in lines
    assert "invalid   plans/[bold]-invalid.toml" in lines
    assert "  file: a [bold] problem" in lines
    assert "failed    plans/failed.toml: blocks/failed.md: a [bold] reason" in lines
    assert "No source: blocks/[x].md" in lines
    assert "Declaration not placed (foreign): blocks/[decl].md" in lines
    assert "[bold]n[/bold]" in lines


# ==============================================================================
# The command's shape: help text, option set, and the AST pin (Req 8.8).
# ==============================================================================


def test_plan_is_a_distinctly_named_command_registered_on_the_app() -> None:
    result = runner.invoke(app, ["--help"])
    assert "plan" in result.output


def test_plan_command_has_only_the_out_option() -> None:
    """No `--force`, no `--dry-run` -- asserted directly against the
    command's own signature (Req 8.5), not merely against `--help` prose.

    Named mutation (add `force: bool = _FORCE_OPTION` to `plan_command`):
    the equality assertion reds (`{"out", "force"} != {"out"}`)."""
    source = inspect.getsource(cli_module)
    tree = ast.parse(source)
    plan_funcs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "plan_command"
    ]
    assert len(plan_funcs) == 1
    params = {arg.arg for arg in plan_funcs[0].args.args}
    assert params == {"out"}


def test_no_other_command_implementation_reaches_run_plan() -> None:
    """Structural absence test, closed module-wide (`ast.walk(tree)`
    everywhere below, never `tree.body` or a single function's own body), in
    the shape `tests/test_cli_history.py:660`'s `run_history` guard uses.

    **Re-anchored by `plan-resolution` task 3.2** (design.md, Cross-spec
    obligations (training-blocks <-> plan-resolution), item 5): the pass is
    now chained after `sync`'s and `regen`'s load pass, and `plan_command`
    runs it standalone through the same helper, so wave 1's engine function,
    `run_plan`, is no longer named anywhere in this module at all --
    `_run_plan_pass` calls `fitdocs.plans.run_reconcile` instead, which
    itself threads a resolver into `run_plan` from inside `fitdocs.plans`,
    not from `cli.py`. Three independent, module-wide guards:

    (a) Every `ast.Import`/`ast.ImportFrom` node anywhere in the module
        whose imported module or aliased name starts with `fitdocs.plans`
        is exactly one node: the module-level `from fitdocs.plans import
        BlockStatus, PlanReport, ReconcileReport, RowState,
        actual_load_sentence, run_reconcile`, pinned by equality on
        `(module, [(name, asname), ...])`.
    (b) Every `ast.Name` *load* of `run_reconcile` anywhere in the module
        numbers exactly one, and that one sits inside `_run_plan_pass`'s own
        body. Every `ast.Name` *load* of `run_plan` anywhere in the module
        numbers exactly zero.
    (c) Zero `ast.Attribute` nodes anywhere in the module have `attr ==
        "run_plan"` or `attr == "run_reconcile"`.

    Named mutations: call `run_reconcile` from `plan_command` directly
    (bypassing `_run_plan_pass`) -- guard (b) reds, since the one `ast.Name`
    load of `run_reconcile` now sits outside `_run_plan_pass`. Re-add
    `run_plan` to the module-level import and call it from `plan_command` --
    guard (a) reds (the import set no longer equals the pinned one) and the
    zero-`run_plan`-names half of guard (b) reds together."""
    source = inspect.getsource(cli_module)
    tree = ast.parse(source)

    plans_imports = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Import)
            and any(alias.name.startswith("fitdocs.plans") for alias in node.names)
        )
        or (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("fitdocs.plans")
        )
    ]
    assert len(plans_imports) == 1
    (only_plans_import,) = plans_imports
    assert isinstance(only_plans_import, ast.ImportFrom)
    assert only_plans_import.module == "fitdocs.plans"
    assert {(alias.name, alias.asname) for alias in only_plans_import.names} == {
        ("BlockStatus", None),
        ("PlanReport", None),
        ("ReconcileReport", None),
        ("RowState", None),
        ("actual_load_sentence", None),
        ("run_reconcile", None),
    }

    run_plan_pass = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_run_plan_pass"
    )
    all_run_plan_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "run_plan"
    ]
    assert all_run_plan_names == []

    all_run_reconcile_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "run_reconcile"
    ]
    assert len(all_run_reconcile_names) == 1
    names_inside_run_plan_pass = [
        node
        for node in ast.walk(run_plan_pass)
        if isinstance(node, ast.Name) and node.id == "run_reconcile"
    ]
    assert names_inside_run_plan_pass == all_run_reconcile_names

    forbidden_attrs = {"run_plan", "run_reconcile"}
    attribute_accesses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs
    ]
    assert attribute_accesses == []


def test_run_plan_pass_is_loaded_exactly_four_times() -> None:
    """`_run_plan_pass` is loaded exactly four times, module-wide: inside
    `sync_command` (twice -- the explicit-source branch and the drain
    branch), `regen_command`, and `plan_command`, and nowhere else (design.md,
    "CliChaining", the AST pin re-stated; plan-resolution task 3.2).

    Named mutation (call `_run_plan_pass` from `load_command` too): the
    count assertion below reds (5 != 4) and the containing-function-names
    assertion reds together (`load_command` is not one of the four named
    functions)."""
    source = inspect.getsource(cli_module)
    tree = ast.parse(source)

    named_functions = {"sync_command", "regen_command", "plan_command"}
    functions_by_name = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in named_functions
    }
    assert set(functions_by_name) == named_functions

    all_loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "_run_plan_pass"
    ]
    assert len(all_loads) == 4

    sync_loads = [
        node
        for node in ast.walk(functions_by_name["sync_command"])
        if isinstance(node, ast.Name) and node.id == "_run_plan_pass"
    ]
    assert len(sync_loads) == 2
    regen_loads = [
        node
        for node in ast.walk(functions_by_name["regen_command"])
        if isinstance(node, ast.Name) and node.id == "_run_plan_pass"
    ]
    assert len(regen_loads) == 1
    plan_loads = [
        node
        for node in ast.walk(functions_by_name["plan_command"])
        if isinstance(node, ast.Name) and node.id == "_run_plan_pass"
    ]
    assert len(plan_loads) == 1

    assert {id(node) for node in sync_loads + regen_loads + plan_loads} == {
        id(node) for node in all_loads
    }
