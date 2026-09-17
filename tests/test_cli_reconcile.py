"""CLI tests for the reconciling pass chained after ``sync``/``regen`` and
run standalone by ``plan`` (plan-resolution spec, task 3.2). See
"CliChaining" (`src/fitdocs/cli.py`) in `.kiro/specs/plan-resolution/
design.md` (Req 4.3, 5.5, 8.1, 8.2, 8.3, 8.5, 8.6, 8.7).

Every plan source here is a hand-written minimal block, written into a
synthetic ``plans/`` directory under ``tmp_path`` -- the plan's hard rules
forbid any write, in code or in a test's assertions, under the resolved
plan-source directory itself, so every fixture below writes the source
before the run and never touches it afterward. The one ``.fit`` fixture
used is :func:`tests.fixtures.builder.run_fit_bytes`; its recorded local
date is read back off the generated document's own stem rather than
hardcoded, since the CLI threads the *system local* timezone into the
engine (mirrors ``tests/test_cli.py``'s ``_RUN_SLUG`` convention).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
import fitdocs.history as history_module
from fitdocs.cli import _report_reconcile, app
from fitdocs.plans import (
    BlockReconciliation,
    Confidence,
    MesocycleLoad,
    PlanReport,
    ReconcileProblem,
    ReconcileReport,
    RowOutcome,
    RowState,
    run_plan,
)
from fitdocs.sync import sync as sync_engine
from fitdocs.tiles import TileStore, load_tile_settings
from tests.fixtures import builder

runner = CliRunner()

_ZERO_SETTLE_TOML = "[inbox]\nsettle_seconds = 0\n"


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every CLI ``sync``/``regen`` network-free (mirrors
    ``tests/test_cli.py``)."""
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _put(directory: Path, name: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


def _logged_run_date(data_root: Path) -> date:
    """The recorded local date of the one workout document under
    ``workouts/`` -- read off the generated stem's leading ISO date rather
    than hardcoded, since document dates are system-timezone-dependent."""
    workouts = sorted(
        path
        for path in (data_root / "workouts").glob("*.md")
        if path.name != "AGENTS.md"
    )
    assert len(workouts) == 1, workouts
    return date.fromisoformat(workouts[0].stem[:10])


def _write_plan_source(
    plans_dir: Path,
    *,
    block_id: str,
    row_date: date,
    row_id: str = "w1",
    extra_override: str = "",
) -> Path:
    """A minimal, single-row plan source whose one ``Run`` row falls on
    ``row_date``, bounded by a week-wide block around it."""
    starts = row_date - timedelta(days=3)
    ends = row_date + timedelta(days=3)
    text = (
        'title = "Reconcile fixture block"\n'
        f"starts = {starts.isoformat()}\n"
        f"ends = {ends.isoformat()}\n"
        'goal = "Reconcile fixture."\n'
        "mesocycle_days = 7\n"
        "\n"
        "[[workout]]\n"
        f'id = "{row_id}"\n'
        f"date = {row_date.isoformat()}\n"
        'sport = "Run"\n'
        'title = "Easy run"\n'
        'summary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n'
        f"{extra_override}"
    )
    plans_dir.mkdir(parents=True, exist_ok=True)
    path = plans_dir / f"{block_id}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _first_sync(tmp_path: Path) -> tuple[Path, Path, date]:
    """Sync one run fixture into a fresh data root (no plan source yet) and
    return ``(data_root, source_dir, logged_date)``."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    return data_root, source, _logged_run_date(data_root)


# ==============================================================================
# The pass is chained after sync (explicit source), the drain, and regen: the
# block page carries the match text and the run prints "reconciled" (8.1, 8.2).
# ==============================================================================


def test_sync_explicit_source_chains_the_pass_and_prints_reconciled(
    tmp_path: Path,
) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert "reconciled b1" in result.output
    block_page = (data_root / "blocks" / "b1.md").read_text(encoding="utf-8")
    assert "matched:" in block_page
    # Req 8.1: the load pass runs (and prints) before the plan reconciling
    # pass -- pinned by the load table's own stable title, "fitdocs load",
    # ordered ahead of the reconciling pass's "reconciled b1" line.
    assert result.output.index("fitdocs load") < result.output.index("reconciled b1")
    # Req 8.6: within the plan pass itself, the wave-1 plan report's own
    # "rendered" line prints before the reconciling pass's "reconciled b1"
    # line -- the reconciling report always comes after the plan pass's own.
    assert result.output.index("rendered  plans/b1.toml") < result.output.index(
        "reconciled b1"
    )


def test_sync_drain_chains_the_pass_and_prints_reconciled(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    _put(data_root / "inbox", "run.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert first.exit_code == 0, first.output
    logged_date = _logged_run_date(data_root)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert second.exit_code == 0, second.output
    assert "reconciled b1" in second.output
    block_page = (data_root / "blocks" / "b1.md").read_text(encoding="utf-8")
    assert "matched:" in block_page
    # Req 8.1: the load pass runs (and prints) before the plan reconciling
    # pass on the drain path too, same ordering as the explicit-source path.
    assert second.output.index("fitdocs load") < second.output.index("reconciled b1")


def test_regen_chains_the_pass_and_prints_reconciled(tmp_path: Path) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert "reconciled b1" in result.output
    block_page = (data_root / "blocks" / "b1.md").read_text(encoding="utf-8")
    assert "matched:" in block_page
    # Req 8.1: the load pass runs (and prints) before the plan reconciling
    # pass on the regen path too, same ordering as the explicit-source path.
    assert result.output.index("fitdocs load") < result.output.index("reconciled b1")


# ==============================================================================
# Suppression rule (8.5): chained + no block/unsourced/foreign declaration is
# quiet -- byte-identical to a stubbed pass that prints nothing.
# ==============================================================================


def test_sync_with_no_plan_directory_is_quiet_and_byte_identical_to_a_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The baseline run is genuinely unstubbed end to end -- it exercises the
    real ``_run_plan_pass``, its quiet-gated ``_report_plan`` call, and its
    unconditional ``_report_reconcile`` call. The comparison run replaces
    ``cli_module._run_plan_pass`` itself (not the lower-level
    ``run_reconcile``), with a stub that calls the plan *engine* directly
    (never a CLI report function) and prints nothing at all -- so the two
    outputs can only agree if the real call site both (a) gates
    ``_report_plan`` on the quiet rule and (b) never prints anything of its
    own beyond that. A stub that stopped at ``run_reconcile`` instead would
    leave the real, unstubbed ``_report_reconcile`` running on both sides,
    silently passing even if it always printed something."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    baseline = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert baseline.exit_code == 0, baseline.output

    def _stub_run_plan_pass(
        data_root: Path, *, today: date, chained: bool
    ) -> ReconcileReport:
        plan = run_plan(data_root)
        return ReconcileReport(plan=plan, blocks=(), methodology=None)

    monkeypatch.setattr(cli_module, "_run_plan_pass", _stub_run_plan_pass)

    data_root_2 = tmp_path / "data2"
    data_root_2.mkdir()
    stubbed = runner.invoke(app, ["sync", str(source), "--out", str(data_root_2)])
    assert stubbed.exit_code == 0, stubbed.output

    assert baseline.output == stubbed.output
    # The suppression itself, not merely the stub-call shape: with no plan
    # directory at all, the wave-1 plan report's own "Source:" line never
    # appears in a chained run.
    assert "Source:" not in baseline.output


def test_sync_drain_with_no_plan_directory_is_quiet_and_byte_identical_to_a_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors the explicit-source quiet-stub pin above, but exercises the
    no-SOURCE drain branch's own ``chained=True`` call site instead: a
    ``chained=True -> chained=False`` mutation there is invisible to the
    explicit-source test (which never invokes the drain branch), so it needs
    its own baseline-vs-stub byte-identity comparison over a fresh data root
    that never had a plan-source directory."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    _put(data_root / "inbox", "run.fit", builder.run_fit_bytes())

    baseline = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert baseline.exit_code == 0, baseline.output

    def _stub_run_plan_pass(
        data_root: Path, *, today: date, chained: bool
    ) -> ReconcileReport:
        plan = run_plan(data_root)
        return ReconcileReport(plan=plan, blocks=(), methodology=None)

    monkeypatch.setattr(cli_module, "_run_plan_pass", _stub_run_plan_pass)

    data_root_2 = tmp_path / "data2"
    data_root_2.mkdir()
    (data_root_2 / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    _put(data_root_2 / "inbox", "run.fit", builder.run_fit_bytes())
    stubbed = runner.invoke(app, ["sync", "--out", str(data_root_2), "--no-prompt"])
    assert stubbed.exit_code == 0, stubbed.output

    # The two data roots print their own (differing, and differently-wrapped
    # -- rich soft-wraps the raw path across lines at the console width, so a
    # whole-string replace of the two differently-lengthed absolute paths
    # cannot undo it) absolute inbox path on the drain path's leading
    # "Inbox:" line, which is incidental to what this test pins. Drop that
    # one leading line (everything up to the "fitdocs sync" table, which
    # never carries a data-root-dependent path) before the byte-identity
    # comparison, which is otherwise exact.
    marker = "fitdocs sync"
    normalized_baseline = baseline.output[baseline.output.index(marker) :]
    normalized_stubbed = stubbed.output[stubbed.output.index(marker) :]
    assert normalized_baseline == normalized_stubbed
    assert "Source:" not in baseline.output
    assert "no plan source directory" not in baseline.output


def test_regen_with_no_plan_directory_is_quiet_and_byte_identical_to_a_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors the explicit-source quiet-stub pin above, but exercises
    ``regen_command``'s own ``chained=True`` call site: a ``chained=True ->
    chained=False`` mutation there is invisible to the explicit-source and
    drain tests (neither invokes ``regen``), so it needs its own
    baseline-vs-stub byte-identity comparison over a data root with archived
    sources but no plan-source directory."""
    root_one = tmp_path / "one"
    root_one.mkdir()
    data_root, _source, _logged_date = _first_sync(root_one)

    baseline = runner.invoke(app, ["regen", "--out", str(data_root)])
    assert baseline.exit_code == 0, baseline.output

    def _stub_run_plan_pass(
        data_root: Path, *, today: date, chained: bool
    ) -> ReconcileReport:
        plan = run_plan(data_root)
        return ReconcileReport(plan=plan, blocks=(), methodology=None)

    monkeypatch.setattr(cli_module, "_run_plan_pass", _stub_run_plan_pass)

    root_two = tmp_path / "two"
    root_two.mkdir()
    data_root_2, _source_2, _logged_date_2 = _first_sync(root_two)
    stubbed = runner.invoke(app, ["regen", "--out", str(data_root_2)])
    assert stubbed.exit_code == 0, stubbed.output

    assert baseline.output == stubbed.output
    assert "Source:" not in baseline.output
    assert "no plan source directory" not in baseline.output


# ==============================================================================
# A missing override stem exits with the per-file-failure status and prints
# the problem line (8.7).
# ==============================================================================


def _missing_stem_override(logged_date: date) -> str:
    """A ``[[override]]`` table whose one stem never matches a logged
    workout -- the one fixture shape every exit-fold pin below reuses, so
    a reconciling-pass override problem (``report.failed`` via
    ``BlockReconciliation.problems``, never ``plan.failed``) is present
    without the block itself failing to render."""
    return (
        "\n[[override]]\n"
        f"date = {logged_date.isoformat()}\n"
        'id = "w1"\n'
        'stems = ["no-such-stem"]\n'
        'reason = "Test override."\n'
    )


def test_missing_override_stem_exits_one_and_prints_the_problem_line(
    tmp_path: Path,
) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(
        data_root / "plans",
        block_id="b1",
        row_date=logged_date,
        extra_override=_missing_stem_override(logged_date),
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 1, result.output
    assert "stem `no-such-stem` not found among the logged workouts" in result.output


# ==============================================================================
# The same override-problem fixture, pinned separately at each of the three
# call sites that fold the reconciling pass's failure into the run's exit
# status: the drain path, ``regen``, and ``plan`` standalone. Each site folds
# independently (`plan_report.failed`/`report.failed` is OR'd in alongside
# the sync/load failure at its own call site), so a single explicit-source
# pin (above) cannot catch a fold dropped at any of these other three sites
# (plan-resolution Req 8.7).
# ==============================================================================


def test_missing_override_stem_exits_one_through_the_drain_path(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    _put(data_root / "inbox", "run.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert first.exit_code == 0, first.output
    logged_date = _logged_run_date(data_root)
    _write_plan_source(
        data_root / "plans",
        block_id="b1",
        row_date=logged_date,
        extra_override=_missing_stem_override(logged_date),
    )

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert second.exit_code == 1, second.output
    assert "stem `no-such-stem` not found among the logged workouts" in second.output


def test_missing_override_stem_exits_one_through_regen(tmp_path: Path) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(
        data_root / "plans",
        block_id="b1",
        row_date=logged_date,
        extra_override=_missing_stem_override(logged_date),
    )

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 1, result.output
    assert "stem `no-such-stem` not found among the logged workouts" in result.output


def test_missing_override_stem_exits_one_through_plan_standalone(
    tmp_path: Path,
) -> None:
    """``plan_command`` folds ``report.failed`` -- ``ReconcileReport.failed``,
    which ORs ``plan.failed`` with every block's own ``problems`` -- never
    ``report.plan.failed`` alone: the block here renders cleanly
    (``plan.failed`` is ``False``), so a fold that reads only
    ``report.plan.failed`` would wrongly exit ``0``."""
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(
        data_root / "plans",
        block_id="b1",
        row_date=logged_date,
        extra_override=_missing_stem_override(logged_date),
    )

    result = runner.invoke(app, ["plan", "--out", str(data_root)])

    assert result.exit_code == 1, result.output
    assert "stem `no-such-stem` not found among the logged workouts" in result.output


# ==============================================================================
# A malformed [history] table exits with the configuration status (8.7).
# ==============================================================================


def test_malformed_history_table_exits_two(tmp_path: Path) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)
    (data_root / "fitdocs.toml").write_text(
        "[history]\ntau_fitness_days = true\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 2, result.output


# ==============================================================================
# A malformed [load] table, reached only through `plan` standalone: `sync`
# and `regen` both map `LoadSettingsError` first, inside `_run_load_pass`
# (which runs before the reconciling pass), so only `plan` -- which never
# runs the load pass at all -- can pin `_run_plan_pass`'s own `except
# SettingsError` covering the reconciling pass's read of `[load]` (Req 8.7).
# ==============================================================================


def test_plan_standalone_malformed_load_table_exits_two(tmp_path: Path) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)
    (data_root / "fitdocs.toml").write_text(
        "[load]\ndefault_calculator = 7\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["plan", "--out", str(data_root)])

    assert result.exit_code == 2, result.output


# ==============================================================================
# load/history leave the rendered directory unchanged when a plan already ran
# and a matching workout page was added afterward (8.3).
# ==============================================================================


def test_load_and_history_leave_blocks_untouched(tmp_path: Path) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)

    plan_result = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert plan_result.exit_code == 0, plan_result.output
    blocks_dir = data_root / "blocks"
    before = {
        path.relative_to(data_root): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(blocks_dir.rglob("*"))
        if path.is_file()
    }
    assert before, "the plan run must have written at least the block page"

    # A second Run, on the SAME day as the plan's one row, added to
    # workouts/ after the plan run -- a matching page that WOULD change the
    # block page's text (matched -> matched (absorbed 2)) if the pass ran
    # again, so the byte comparison below is sensitive, not vacuous. Written
    # through the sync *engine* directly, deliberately bypassing the CLI, so
    # this setup step's own chained plan pass never touches ``blocks/``
    # before the ``load``/``history`` calls under test do.
    second_source = tmp_path / "src2"
    _put(
        second_source,
        "run2.fit",
        builder.small_sport_fit_bytes(9101, "running", timestamp_offset=3600),
    )
    engine_report = sync_engine(
        second_source,
        data_root,
        athlete=None,
        tz=cli_module._local_tz(),
        tiles=TileStore(data_root, load_tile_settings(data_root)),
    )
    assert not engine_report.failures, engine_report.failures
    workout_stems = sorted(
        p.stem for p in (data_root / "workouts").glob("*.md") if p.name != "AGENTS.md"
    )
    assert len(workout_stems) == 2, workout_stems
    assert all(stem.startswith(logged_date.isoformat()) for stem in workout_stems), (
        workout_stems
    )

    load_result = runner.invoke(app, ["load", "--out", str(data_root), "--no-prompt"])
    assert load_result.exit_code == 0, load_result.output
    history_result = runner.invoke(app, ["history", "--out", str(data_root)])
    assert history_result.exit_code == 0, history_result.output

    after = {
        path.relative_to(data_root): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(blocks_dir.rglob("*"))
        if path.is_file()
    }
    assert after == before


# ==============================================================================
# The quiet rule's third branch (8.5): chained + no block, but an unsourced
# ``blocks/`` page with no plan source at all, is NOT quiet -- the wave-1
# "No source:" line still prints. `quiet = chained and not plan.blocks`
# (dropping the `unsourced`/`declarations_foreign` legs) cannot tell this
# case from the genuinely-quiet no-plan-directory case above, since both
# have `plan.blocks == ()`.
# ==============================================================================


def test_sync_chained_prints_when_a_block_page_is_unsourced(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0, first.output

    # An empty, but existing, plan-source directory -- ``run_plan`` discovers
    # no blocks -- plus a stray rendered block page with no matching source
    # at all, so `plan.unsourced` is non-empty while `plan.blocks` stays
    # empty, same as the quiet no-plan-directory case.
    (data_root / "plans").mkdir()
    (data_root / "blocks").mkdir(exist_ok=True)
    (data_root / "blocks" / "stray.md").write_text("stray\n", encoding="utf-8")

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert "No source: blocks/stray.md" in result.output


# ==============================================================================
# `_report_reconcile` unit pin (Req 8.6): markup safety and unwrapped long
# lines on every line, in the shape `tests/test_cli_plan.py:507-550` uses for
# `_report_plan` -- a `ReconcileProblem` whose message carries a Rich markup
# tag prints it verbatim (Rich would otherwise render/strip `[bold]`), and a
# line built past 80 columns is never wrapped.
# ==============================================================================


def test_report_reconcile_prints_markup_literally_and_never_wraps(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pins `markup=False, highlight=False, soft_wrap=True` independently on
    the per-block summary line and on the per-problem detail line.

    Named mutations:
    - drop `markup=False, highlight=False, soft_wrap=True` from the summary
      line's own `console.print` call -> the long, `[bold]`-carrying block-id
      assertion reds (Rich would render/strip the tag and wrap the line).
    - drop the same kwargs from the per-problem `console.print` call -> the
      `[bold]`-carrying problem-message assertion reds, independently of the
      summary-line assertion.
    """
    long_block_id = "b-" + "x" * 90 + "-[bold]end[/bold]"
    reconciliation = _reconciliation(
        block_id=long_block_id,
        rows=(_row("r1", RowState.NOT_LOGGED),),
        problems=(
            ReconcileProblem(
                entry="override[0] (id a)",
                message="a [bold]problem[/bold] message",
            ),
        ),
    )
    report = _report(blocks=(reconciliation,))

    _report_reconcile(report)

    out = capsys.readouterr().out
    summary_line = f"reconciled {long_block_id}: 1 planned -- 1 not logged; 0 unplanned"
    assert summary_line in out.splitlines()
    assert "  override[0] (id a): a [bold]problem[/bold] message" in out.splitlines()


# ==============================================================================
# The plan command itself still exits success and its block page carries the
# match text (8.2, unchanged wave-1 behaviour).
# ==============================================================================


def test_plan_command_exits_success_and_block_page_carries_match_text(
    tmp_path: Path,
) -> None:
    data_root, source, logged_date = _first_sync(tmp_path)
    _write_plan_source(data_root / "plans", block_id="b1", row_date=logged_date)

    result = runner.invoke(app, ["plan", "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    block_page = (data_root / "blocks" / "b1.md").read_text(encoding="utf-8")
    assert "matched:" in block_page


# ==============================================================================
# `_report_reconcile` unit-level pins over hand-built `ReconcileReport`/
# `BlockReconciliation` values (round 2, Req 8.6). Round 1 declared the
# report grammar preserved-only -- the fixtures above exercise only
# `matched`/`overridden` counts and the no-methodology branch; these pin
# every remaining printed shape design.md states (design.md:1242-1336):
# zero-count states omitted from the summary line, the ambiguous
# parenthesis gated on count, the N == 0 block form, the mesocycle/
# ambiguous/problem detail lines, and the methodology line's two forms.
# `_report_reconcile` prints through a bare `Console()`, exactly as
# `_report_plan` does (`tests/test_cli_plan.py`), so `capsys` captures it
# with no `CliRunner` involved.
# ==============================================================================

_EMPTY_PLAN_REPORT = PlanReport(
    source_dir="plans", blocks=(), unsourced=(), declarations_foreign=(), note=None
)


def _row(
    row_id: str,
    state: RowState,
    *,
    confidence: Confidence | None = None,
    stems: tuple[str, ...] = (),
) -> RowOutcome:
    return RowOutcome(
        row_id=row_id,
        state=state,
        stems=stems,
        confidence=confidence,
        missing=(),
        override_index=None,
        override_date=None,
        reason=None,
        competitors=(),
        same_day=(),
    )


def _meso(number: int, *, methodology: str | None = "threshold") -> MesocycleLoad:
    """A mesocycle with no logged pages at all -- `actual_load_sentence`
    then reads only `methodology` (`None` -> the no-methodology sentence,
    a name with no pages -> the no-logged-workout sentence), so this
    fixture needs nothing from `plans.aggregate` itself."""
    return MesocycleLoad(
        number=number,
        target=None,
        methodology=methodology,
        pages=(),
        scored=(),
        unscored=(),
        excluded=(),
        unplanned=(),
    )


def _reconciliation(
    *,
    block_id: str = "b1",
    rows: tuple[RowOutcome, ...] = (),
    mesocycles: tuple[MesocycleLoad, ...] = (),
    methodology: (
        history_module.MethodologyChoice | history_module.MethodologyProblem | None
    ) = None,
    problems: tuple[ReconcileProblem, ...] = (),
) -> BlockReconciliation:
    return BlockReconciliation(
        block_id=block_id,
        rows=rows,
        mesocycles=mesocycles,
        # `BlockReconciliation.methodology` is never `None` in production
        # (`reconcile_block` always carries the run's `MethodologyChoice`
        # or `MethodologyProblem`); `_report_reconcile` itself reads only
        # `ReconcileReport.methodology` for the once-per-run line, so a
        # placeholder problem here is inert to every assertion below.
        methodology=methodology
        if methodology is not None
        else history_module.MethodologyProblem("placeholder, unread by any test below"),
        problems=problems,
    )


def _report(
    *,
    blocks: tuple[BlockReconciliation, ...],
    methodology: (
        history_module.MethodologyChoice | history_module.MethodologyProblem | None
    ) = None,
) -> ReconcileReport:
    return ReconcileReport(
        plan=_EMPTY_PLAN_REPORT, blocks=blocks, methodology=methodology
    )


def test_report_reconcile_omits_zero_count_states_from_the_summary_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A block with exactly one `NOT_LOGGED` row prints only that state --
    `matched`, `overridden`, `skipped` and `upcoming` (all zero) never
    appear (design.md:1242-1336, "the per-state list under the block
    page's own count-line rule ... zero-count states omitted").

    Named mutation (drop the `if n == 0: continue` guard in
    `_report_reconcile`'s per-state loop): the summary line below reds --
    it would read `"reconciled b1: 1 planned -- 1 matched, 1 overridden, 1
    skipped, 1 not logged, 1 upcoming; 0 unplanned"` instead."""
    reconciliation = _reconciliation(
        block_id="b1", rows=(_row("r1", RowState.NOT_LOGGED),)
    )
    report = _report(blocks=(reconciliation,))

    _report_reconcile(report)

    lines = capsys.readouterr().out.splitlines()
    assert "reconciled b1: 1 planned -- 1 not logged; 0 unplanned" in lines


def test_report_reconcile_prints_a_nonzero_unplanned_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Req 8.6's unplanned count is the sum over the mesocycles' unplanned
    listings, not a fixed `0`: two unplanned records on one mesocycle and
    one on another print `; 3 unplanned`. Every other report pin in this
    module carries `0 unplanned`, so a hard-coded zero survives them all;
    this one reds it."""
    from datetime import UTC
    from datetime import datetime as _dt

    from fitdocs.model import Sport
    from fitdocs.plans import LoggedWorkout

    def _logged(stem: str, day: date) -> LoggedWorkout:
        return LoggedWorkout(
            stem=stem,
            path=f"workouts/{stem}.md",
            day=day,
            sport=Sport.RUN,
            modality=None,
            indoor=None,
            start_time=_dt(day.year, day.month, day.day, 7, 0, tzinfo=UTC),
            load=None,
            methodology=None,
        )

    first = MesocycleLoad(
        number=1,
        target=None,
        methodology="threshold",
        pages=(),
        scored=(),
        unscored=(),
        excluded=(),
        unplanned=(_logged("a", date(2026, 3, 2)), _logged("b", date(2026, 3, 3))),
    )
    second = MesocycleLoad(
        number=2,
        target=None,
        methodology="threshold",
        pages=(),
        scored=(),
        unscored=(),
        excluded=(),
        unplanned=(_logged("c", date(2026, 3, 9)),),
    )
    reconciliation = _reconciliation(
        block_id="b1",
        rows=(_row("r1", RowState.NOT_LOGGED),),
        mesocycles=(first, second),
    )
    report = _report(blocks=(reconciliation,))

    _report_reconcile(report)

    lines = capsys.readouterr().out.splitlines()
    assert "reconciled b1: 1 planned -- 1 not logged; 3 unplanned" in lines


def test_report_reconcile_prints_ambiguous_parenthesis_only_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One `MATCHED`/`AMBIGUOUS` row prints `1 matched (1 ambiguous)`; one
    `MATCHED`/`EXACT` row prints plain `1 matched`, no parenthesis at all
    (design.md:1242-1336, "the ambiguous parenthesis only when `b >= 1`").

    Named mutation (print `f"{n} {state.value} ({len(ambiguous)}
    ambiguous)"` unconditionally for `state is RowState.MATCHED`): the
    second assertion below reds -- the exact-confidence line would carry a
    `(0 ambiguous)` parenthesis it must not have -- while the first
    assertion (genuinely ambiguous) stays green, showing this pin is
    caught specifically by the zero-ambiguous case."""
    ambiguous_report = _report(
        blocks=(
            _reconciliation(
                block_id="amb",
                rows=(
                    _row(
                        "r1",
                        RowState.MATCHED,
                        confidence=Confidence.AMBIGUOUS,
                        stems=("s1", "s2"),
                    ),
                ),
            ),
        )
    )
    _report_reconcile(ambiguous_report)
    ambiguous_lines = capsys.readouterr().out.splitlines()
    assert "reconciled amb: 1 planned -- 1 matched (1 ambiguous); 0 unplanned" in (
        ambiguous_lines
    )

    exact_report = _report(
        blocks=(
            _reconciliation(
                block_id="exact",
                rows=(
                    _row(
                        "r1",
                        RowState.MATCHED,
                        confidence=Confidence.EXACT,
                        stems=("s1",),
                    ),
                ),
            ),
        )
    )
    _report_reconcile(exact_report)
    exact_lines = capsys.readouterr().out.splitlines()
    assert "reconciled exact: 1 planned -- 1 matched; 0 unplanned" in exact_lines
    assert not any("ambiguous" in line for line in exact_lines)


def test_report_reconcile_no_rows_prints_the_zero_count_form(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A block with no current rows at all prints `reconciled <id>: 0
    planned; 0 unplanned` -- no ` -- ` and no per-state list (design.md:
    1242-1336, "no list when `N == 0`").

    Named mutation (drop the `if segments:` guard and always append `" --
    " + ", ".join(segments)`): the assertion below reds -- with no
    segments the line would carry a dangling `" -- "` with nothing after
    it (`"reconciled empty: 0 planned -- ; 0 unplanned"`)."""
    report = _report(blocks=(_reconciliation(block_id="empty", rows=()),))

    _report_reconcile(report)

    lines = capsys.readouterr().out.splitlines()
    assert "reconciled empty: 0 planned; 0 unplanned" in lines


def test_report_reconcile_prints_one_mesocycle_line_per_mesocycle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each mesocycle prints its own indented `mesocycle n: <actual_load_
    sentence>` line, in order, reusing `actual_load_sentence` verbatim
    (design.md:1242-1336).

    Named mutation (`enumerate(reconciliation.mesocycles, start=0)`): both
    assertions below red together (`mesocycle 0:`/`mesocycle 1:` instead of
    `mesocycle 1:`/`mesocycle 2:`)."""
    report = _report(
        blocks=(
            _reconciliation(
                block_id="b1",
                mesocycles=(
                    _meso(1, methodology=None),
                    _meso(2, methodology="banister"),
                ),
            ),
        )
    )

    _report_reconcile(report)

    lines = capsys.readouterr().out.splitlines()
    assert (
        "  mesocycle 1: Actual load: not computed -- no methodology chosen "
        "(see Resolution below)." in lines
    )
    assert (
        "  mesocycle 2: Actual load: not computed -- no logged workout in "
        "this window." in lines
    )


def test_report_reconcile_prints_ambiguous_ids_only_when_any(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`ambiguous: <ids>` prints, comma-joined, only when the block has at
    least one ambiguous row; a block with none prints no such line at all
    (design.md:1242-1336, "`ambiguous: <ids>` when the block has any").

    Named mutation (drop the `if ambiguous:` guard around the `ambiguous:`
    print): the second assertion below reds -- a block with no ambiguous
    rows would print `"  ambiguous: "` (an empty, dangling line) where
    nothing should print at all."""
    with_ambiguous = _report(
        blocks=(
            _reconciliation(
                block_id="b1",
                rows=(
                    _row(
                        "r1",
                        RowState.MATCHED,
                        confidence=Confidence.AMBIGUOUS,
                        stems=("s1", "s2"),
                    ),
                    _row(
                        "r2",
                        RowState.MATCHED,
                        confidence=Confidence.AMBIGUOUS,
                        stems=("s3", "s4"),
                    ),
                ),
            ),
        )
    )
    _report_reconcile(with_ambiguous)
    with_lines = capsys.readouterr().out.splitlines()
    assert "  ambiguous: r1, r2" in with_lines

    without_ambiguous = _report(
        blocks=(
            _reconciliation(
                block_id="b2",
                rows=(
                    _row(
                        "r1",
                        RowState.MATCHED,
                        confidence=Confidence.EXACT,
                        stems=("s1",),
                    ),
                ),
            ),
        )
    )
    _report_reconcile(without_ambiguous)
    without_lines = capsys.readouterr().out.splitlines()
    assert not any(line.strip().startswith("ambiguous:") for line in without_lines)


def test_report_reconcile_prints_one_describe_line_per_problem(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every `ReconcileProblem` in `problems` prints its own indented
    `describe()` line, in order (design.md:1242-1336, "one indented
    `describe()` per problem").

    Named mutation (`for problem in reconciliation.problems[:1]:`, print
    only the first): the second assertion below reds -- the second
    problem's line never prints -- while the first assertion stays green."""
    report = _report(
        blocks=(
            _reconciliation(
                block_id="b1",
                problems=(
                    ReconcileProblem(
                        entry="override[0] (id a)", message="first problem"
                    ),
                    ReconcileProblem(
                        entry="override[1] (id b)", message="second problem"
                    ),
                ),
            ),
        )
    )

    _report_reconcile(report)

    lines = capsys.readouterr().out.splitlines()
    assert "  override[0] (id a): first problem" in lines
    assert "  override[1] (id b): second problem" in lines


def test_report_reconcile_prints_the_methodology_line_once_in_each_form(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`methodology: <name> (<source>)` for a chosen methodology --
    `configured` and `inferred` both spelled verbatim from
    `MethodologyChoice.source` -- and `methodology: none chosen --
    <detail>` for a `MethodologyProblem`; the line prints exactly once,
    after every block (design.md:1242-1336).

    Named mutation (print the methodology line inside the per-block loop
    instead of once after it): the configured-case assertion below still
    holds textually but the line would repeat once per block -- pinned
    directly via `lines.count(...)` rather than mere membership, so a
    single-block report is not enough to catch it and a two-block report
    is used here."""
    configured = history_module.MethodologyChoice("threshold", "configured", ())
    report = _report(
        blocks=(_reconciliation(block_id="b1"), _reconciliation(block_id="b2")),
        methodology=configured,
    )
    _report_reconcile(report)
    lines = capsys.readouterr().out.splitlines()
    assert lines.count("methodology: threshold (configured)") == 1

    inferred = history_module.MethodologyChoice("banister", "inferred", ())
    report = _report(blocks=(_reconciliation(block_id="b1"),), methodology=inferred)
    _report_reconcile(report)
    lines = capsys.readouterr().out.splitlines()
    assert "methodology: banister (inferred)" in lines

    problem = history_module.MethodologyProblem(
        "no page in the archive records a methodology"
    )
    report = _report(blocks=(_reconciliation(block_id="b1"),), methodology=problem)
    _report_reconcile(report)
    lines = capsys.readouterr().out.splitlines()
    assert (
        "methodology: none chosen -- no page in the archive records a "
        "methodology" in lines
    )

    report = _report(blocks=(_reconciliation(block_id="b1"),), methodology=None)
    _report_reconcile(report)
    lines = capsys.readouterr().out.splitlines()
    assert not any(line.startswith("methodology:") for line in lines)


# ==============================================================================
# The quiet rule's foreign-declaration branch (8.5): chained + no block, no
# unsourced path, but a foreign declaration still prints -- pinned at unit
# level against `_run_plan_pass` itself, with `run_reconcile` monkeypatched
# so the fixture needs no real plan-source directory at all.
# ==============================================================================


def test_run_plan_pass_prints_when_a_declaration_is_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`quiet = chained and not plan.blocks and not plan.unsourced and not
    plan.declarations_foreign` -- dropping the last conjunct (`and not
    plan.declarations_foreign`) would wrongly suppress the plan report on a
    chained run whose only finding is a foreign declaration, with no block
    and no unsourced path at all."""
    plan = PlanReport(
        source_dir="plans",
        blocks=(),
        unsourced=(),
        declarations_foreign=("blocks/AGENTS.md",),
        note=None,
    )
    report = ReconcileReport(plan=plan, blocks=(), methodology=None)

    def _stub_run_reconcile(data_root: Path, *, today: date) -> ReconcileReport:
        return report

    monkeypatch.setattr(cli_module, "run_reconcile", _stub_run_reconcile)

    cli_module._run_plan_pass(tmp_path, today=date(2024, 1, 1), chained=True)

    output = capsys.readouterr().out
    assert "Declaration not placed (foreign): blocks/AGENTS.md" in output
