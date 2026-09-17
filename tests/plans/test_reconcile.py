"""Tests for `fitdocs.plans.reconcile` (plan-resolution spec, task 3.1). See
"ReconcilePass" (`src/fitdocs/plans/reconcile.py`) in
`.kiro/specs/plan-resolution/design.md` (Req 2.6, 4.3, 4.6, 5.1, 5.2, 5.4,
6.2, 6.6, 8.4, 8.6, 8.9).

Every plan source here is a synthetic `plans/*.toml` file, written into a
synthetic `plans/` directory under `tmp_path` before the run; the plan's
hard rules forbid any write, in code or in a test's assertions, under the
resolved plan-source directory itself, so every scenario writes its
sources first and hashes them (or the whole directory) after. Every
workout page is a synthetically written page tree under `tmp_path`, built
from real frontmatter fences and real `fitdocs.contract` vocabulary --
`tests/plans/test_corpus.py::_page`'s own pattern, extended with nothing
new. No `.fit` file is read and no real wiki page is ever used.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import fitdocs.plans.reconcile as reconcile_module
from fitdocs import layout
from fitdocs.contract import DATE_KEY
from fitdocs.history import MethodologyChoice, MethodologyProblem
from fitdocs.layout import BLOCKS_DIR, WORKOUTS_DIR
from fitdocs.plans.corpus import scan_corpus as _real_scan_corpus
from fitdocs.plans.engine import BlockStatus
from fitdocs.plans.matching import RowState
from fitdocs.plans.reconcile import ReconcileReport, reconcile_block, run_reconcile
from fitdocs.settings import SettingsError

# ===========================================================================
# Fixture builders
# ===========================================================================


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(
    *,
    day: str = "2026-04-06",
    sport: str | None = "Run",
    modality: str | None = None,
    indoor: bool | None = None,
    start_time: str | None = None,
    load_value: float | None = None,
    load_methodology: str | None = None,
) -> str:
    """A minimal, syntactically valid fitdocs workout document -- the same
    shape `tests/plans/test_corpus.py::_page` and
    `tests/history/test_engine.py::_page` build, extended with the
    sport/modality/indoor/start_time lines this run's corpus scan reads."""
    lines = ["---", "title: Test Workout", "type: workout", f'{DATE_KEY}: "{day}"']
    if sport is not None:
        lines.append(f"sport: {sport}")
    if modality is not None:
        lines.append(f"modality: {modality}")
    if indoor is not None:
        lines.append(f"indoor: {'true' if indoor else 'false'}")
    if start_time is not None:
        lines.append(f'start_time: "{start_time}"')
    if load_value is not None:
        lines.append(f"load_value: {load_value}")
    if load_methodology is not None:
        lines.append(f"load_methodology: {load_methodology}")
    lines.append("---")
    lines.append("")
    lines.append("# Test Workout")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_workout_page(
    root: Path, name: str, *, day: str, sport: str | None = "Run"
) -> Path:
    return _write(root, f"{WORKOUTS_DIR}/{name}.md", _page(day=day, sport=sport))


#: A block source with three current rows and one override, built once and
#: reused by every scenario that does not need its own bespoke shape:
#: - "not-logged-row" (2026-04-06, Run): no logged page matches it, dated
#:   before `TODAY` -- resolves NOT_LOGGED unless a matching page is added.
#: - "override-row" (2026-04-07, Run): an effective override names a stem
#:   the corpus never carries -- resolves OVERRIDDEN with one missing stem,
#:   a reported problem.
#: - "today-row" (2026-04-10, Run): dated exactly `TODAY` -- resolves
#:   UPCOMING (Req 2.5).
_BLOCK_ID = "recon"
TODAY = date(2026, 4, 10)

_BASE_SOURCE = """\
title = "Recon smoke block"
starts = 2026-04-06
ends = 2026-04-12
goal = "A block built to exercise run_reconcile's own pins."
mesocycle_days = 7

[[mesocycle]]
number = 1
target_load = 100
focus = "Base"

[[workout]]
id = "not-logged-row"
date = 2026-04-06
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."

[[workout]]
id = "override-row"
date = 2026-04-07
sport = "Run"
title = "Planned run"
summary = "Zone 2"
prescription = "30 minutes easy."

[[workout]]
id = "today-row"
date = 2026-04-10
sport = "Run"
title = "Maybe today"
summary = "Zone 2"
prescription = "20 minutes easy."

[[override]]
date = 2026-04-01
id = "override-row"
stems = ["missing-log"]
reason = "Testing a missing stem"
"""


def _write_base_block(root: Path) -> Path:
    return _write(root, f"plans/{_BLOCK_ID}.toml", _BASE_SOURCE)


#: A block with no override at all, so no run over it ever carries an
#: override problem -- used by scenarios that need `report.failed` to
#: isolate one specific failure source (a `MethodologyProblem` alone is
#: never a failure, Req 6.6) from `_BASE_SOURCE`'s own deliberate missing
#: override stem.
_CLEAN_ID = "clean"
_CLEAN_SOURCE = """\
title = "Clean block"
starts = 2026-05-04
ends = 2026-05-10
goal = "A block with no override problems."
mesocycle_days = 7

[[mesocycle]]
number = 1
target_load = 50
focus = "Base"

[[workout]]
id = "row-a"
date = 2026-05-04
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."
"""


def _write_clean_block(root: Path) -> Path:
    return _write(root, f"plans/{_CLEAN_ID}.toml", _CLEAN_SOURCE)


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Every regular file's bytes under `directory`, keyed by its relative
    POSIX path -- mirrors `tests/test_plan_e2e.py::_snapshot`, reimplemented
    locally since that helper is private to its own test module."""
    if not directory.is_dir():
        return {}
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _row_state(report: ReconcileReport, block_id: str, row_id: str) -> RowState:
    (block,) = (b for b in report.blocks if b.block_id == block_id)
    (row,) = (r for r in block.rows if r.row_id == row_id)
    return row.state


def _block_status(report: ReconcileReport, block_id: str) -> BlockStatus:
    (outcome,) = (o for o in report.plan.blocks if o.block_id == block_id)
    return outcome.status


def _block_page_text(root: Path, block_id: str) -> str:
    return layout.block_doc_path(root, block_id).read_text(encoding="utf-8")


# ===========================================================================
# The rendered block page carries the placed text (Req 7.1, 7.2)
# ===========================================================================


def test_matched_row_places_matched_text_on_the_rendered_block_page(
    tmp_path: Path,
) -> None:
    """A row with a fulfilling logged workout renders `matched:` on the
    block page -- the placed resolution text, not the wave-1 unresolved
    default (which prints no such word)."""
    _write_base_block(tmp_path)
    _write_workout_page(tmp_path, "not-logged-log", day="2026-04-06", sport="Run")

    run_reconcile(tmp_path, today=TODAY)

    text = _block_page_text(tmp_path, _BLOCK_ID)
    assert "matched:" in text


# ===========================================================================
# `claimed=match.claimed` actually reaches `aggregate_mesocycles`: a matched
# page's stem is excluded from every mesocycle's `unplanned` -- named
# mutation: `claimed=frozenset()`
# ===========================================================================


def test_matched_page_stem_is_excluded_from_every_mesocycles_unplanned(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)
    _write_workout_page(tmp_path, "not-logged-log", day="2026-04-06", sport="Run")

    report = run_reconcile(tmp_path, today=TODAY)

    (block,) = report.blocks
    assert block.mesocycles, "the fixture must carry at least one mesocycle"
    for mesocycle in block.mesocycles:
        assert "not-logged-log" not in {page.stem for page in mesocycle.unplanned}
    assert any(
        "not-logged-log" in {page.stem for page in mesocycle.pages}
        for mesocycle in block.mesocycles
    ), "the matched page must still be seen by the window scan"


# ===========================================================================
# A page added between runs flips a row; removing it flips back (two pins)
# ===========================================================================


def test_a_page_added_between_runs_flips_not_logged_to_matched_and_renders(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)

    first = run_reconcile(tmp_path, today=TODAY)
    assert _row_state(first, _BLOCK_ID, "not-logged-row") is RowState.NOT_LOGGED
    assert _block_status(first, _BLOCK_ID) is BlockStatus.RENDERED

    second = run_reconcile(tmp_path, today=TODAY)
    assert _block_status(second, _BLOCK_ID) is BlockStatus.UNCHANGED

    _write_workout_page(tmp_path, "not-logged-log", day="2026-04-06", sport="Run")
    third = run_reconcile(tmp_path, today=TODAY)
    assert _row_state(third, _BLOCK_ID, "not-logged-row") is RowState.MATCHED
    assert _block_status(third, _BLOCK_ID) is BlockStatus.RENDERED


def test_removing_that_page_flips_matched_back_to_not_logged_and_renders(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)
    page_path = _write_workout_page(
        tmp_path, "not-logged-log", day="2026-04-06", sport="Run"
    )
    first = run_reconcile(tmp_path, today=TODAY)
    assert _row_state(first, _BLOCK_ID, "not-logged-row") is RowState.MATCHED

    page_path.unlink()
    second = run_reconcile(tmp_path, today=TODAY)
    assert _row_state(second, _BLOCK_ID, "not-logged-row") is RowState.NOT_LOGGED
    assert _block_status(second, _BLOCK_ID) is BlockStatus.RENDERED


# ===========================================================================
# An override naming a missing stem: failed True, block still rendered
# (Req 4.3, 8.9) -- named mutation: compute `failed` from `plan.failed` alone
# ===========================================================================


def test_missing_override_stem_fails_the_report_but_still_renders_the_block(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)

    report = run_reconcile(tmp_path, today=TODAY)

    assert report.failed is True
    assert _block_status(report, _BLOCK_ID) is BlockStatus.RENDERED
    assert _row_state(report, _BLOCK_ID, "override-row") is RowState.OVERRIDDEN


# ===========================================================================
# A configured methodology no page records: every mesocycle not computed,
# the report carries the problem, failed is false, every row still resolved
# (Req 6.6) -- named mutation: raise on a MethodologyProblem
# ===========================================================================


def test_configured_methodology_absent_leaves_every_mesocycle_not_computed(
    tmp_path: Path,
) -> None:
    _write_clean_block(tmp_path)
    _write(
        tmp_path,
        "fitdocs.toml",
        '[history]\nmethodology = "nonexistent"\n',
    )
    # A page exists so the corpus is non-empty, but it records no load at
    # all -- "nonexistent" is still recorded by no page.
    _write_workout_page(tmp_path, "some-log", day="2026-05-04", sport="Run")

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert isinstance(report.methodology, MethodologyProblem)
    (block,) = report.blocks
    assert block.mesocycles, "the fixture must carry at least one mesocycle"
    for mesocycle in block.mesocycles:
        assert mesocycle.methodology is None
        assert mesocycle.total is None
    assert report.failed is False
    assert len(block.rows) == 1, "every current row must still be resolved"


# ===========================================================================
# The configured name is actually threaded to select_methodology -- named
# mutation: `configured=self._configured` -> `configured=None`
# ===========================================================================


def test_configured_name_is_actually_threaded_not_dropped(tmp_path: Path) -> None:
    """A corpus that records a real, single methodology ("x") but a
    `[history].methodology` naming a *different*, unrecorded one
    ("nonexistent"): with the configured name actually threaded through,
    `select_methodology` rejects "nonexistent" as unrecorded and the run
    carries a `MethodologyProblem`. Dropping the configured name
    (`configured=None`) would instead fall through to the single-observed-
    methodology rule and infer "x" -- a `MethodologyChoice`, not a
    problem -- so this discriminates the two."""
    _write_clean_block(tmp_path)
    _write(
        tmp_path,
        "fitdocs.toml",
        '[history]\nmethodology = "nonexistent"\n',
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/logged-x.md",
        _page(day="2026-05-04", sport="Run", load_value=50.0, load_methodology="x"),
    )

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert isinstance(report.methodology, MethodologyProblem)


# ===========================================================================
# `configured = history.methodology or load.default_calculator`: history
# wins when both are set to different, both-recorded methodologies -- named
# mutation: `load.default_calculator or history.methodology`
# ===========================================================================


def test_history_methodology_takes_precedence_over_load_default_calculator(
    tmp_path: Path,
) -> None:
    _write_clean_block(tmp_path)
    _write(
        tmp_path,
        "fitdocs.toml",
        '[history]\nmethodology = "x"\n\n[load]\ndefault_calculator = "y"\n',
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/logged-x.md",
        _page(day="2026-05-04", sport="Run", load_value=10.0, load_methodology="x"),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/logged-y.md",
        _page(day="2026-05-05", sport="Run", load_value=20.0, load_methodology="y"),
    )

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert isinstance(report.methodology, MethodologyChoice)
    assert report.methodology.methodology == "x"
    # The configured name reaches `select_methodology` as `configured=`, not
    # `requested=`: the choice's source is what the block page prints after
    # the methodology name (Req 7.4 "how it was chosen").
    assert report.methodology.source == "configured"


def test_load_default_calculator_alone_configures_the_methodology(
    tmp_path: Path,
) -> None:
    """Req 6.2's middle branch on its own: no `[history]` table, only
    `[load].default_calculator`, and pages recorded under both `x` and `y`
    (ambiguous without a configured name) -- the choice is the load
    table's `x`, as configured. Dropping the `or load_settings.default_calculator`
    fallback from the composition in `run_reconcile` turns this into a
    MethodologyProblem and reds it; the precedence test above cannot see
    that mutation because it sets both tables."""
    _write_clean_block(tmp_path)
    _write(tmp_path, "fitdocs.toml", '[load]\ndefault_calculator = "x"\n')
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/logged-x.md",
        _page(day="2026-05-04", sport="Run", load_value=10.0, load_methodology="x"),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/logged-y.md",
        _page(day="2026-05-05", sport="Run", load_value=20.0, load_methodology="y"),
    )

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert isinstance(report.methodology, MethodologyChoice)
    assert report.methodology.methodology == "x"
    assert report.methodology.source == "configured"


# ===========================================================================
# A malformed [history] table raises before anything is written
# ===========================================================================


def test_malformed_history_table_raises_before_run_plan_and_writes_nothing(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)
    _write(tmp_path, "fitdocs.toml", "[history]\nmethodology = 42\n")

    source_before = _snapshot(tmp_path / "plans")
    blocks_before = _snapshot(tmp_path / BLOCKS_DIR)

    with pytest.raises(SettingsError):
        run_reconcile(tmp_path, today=TODAY)

    assert _snapshot(tmp_path / "plans") == source_before
    assert _snapshot(tmp_path / BLOCKS_DIR) == blocks_before


# ===========================================================================
# A malformed [load] table raises before anything is written, exactly like
# a malformed [history] table -- named mutation: wrapping the `[load]`
# projection in try/except SettingsError defaulting to None
# ===========================================================================


def test_malformed_load_table_raises_before_run_plan_and_writes_nothing(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)
    _write(tmp_path, "fitdocs.toml", "[load]\ndefault_calculator = 42\n")

    source_before = _snapshot(tmp_path / "plans")
    blocks_before = _snapshot(tmp_path / BLOCKS_DIR)

    with pytest.raises(SettingsError):
        run_reconcile(tmp_path, today=TODAY)

    assert _snapshot(tmp_path / "plans") == source_before
    assert _snapshot(tmp_path / BLOCKS_DIR) == blocks_before


# ===========================================================================
# No plan directory: the corpus is never scanned (counting stub); a run
# WITH a valid block proves the stub is live (>= 1)
# ===========================================================================


def test_no_plan_directory_never_scans_the_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def _counting_scan_corpus(data_root: Path) -> object:
        calls["n"] += 1
        return _real_scan_corpus(data_root)

    monkeypatch.setattr(reconcile_module, "scan_corpus", _counting_scan_corpus)

    report = run_reconcile(tmp_path, today=TODAY)

    assert calls["n"] == 0
    assert report.plan.blocks == ()
    assert report.methodology is None


def test_a_run_with_a_valid_block_does_scan_the_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control for the stub above: proven live over a root that
    does carry a valid block."""
    calls = {"n": 0}

    def _counting_scan_corpus(data_root: Path) -> object:
        calls["n"] += 1
        return _real_scan_corpus(data_root)

    monkeypatch.setattr(reconcile_module, "scan_corpus", _counting_scan_corpus)
    _write_base_block(tmp_path)

    run_reconcile(tmp_path, today=TODAY)

    assert calls["n"] >= 1


def test_two_valid_blocks_scan_the_corpus_exactly_once_and_keep_plan_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the once-per-run scan precisely (`== 1`, not merely `>= 1`) over
    two valid blocks, and pins that `report.blocks` carries them in
    `report.plan.blocks`' own order -- discovery order, sorted by filename
    (`fitdocs.plans.engine`'s own rule), never the order the test happens
    to declare them in. The two files are written zblock-then-ablock, the
    reverse of their sorted discovery order, so a test that quietly matched
    declaration order instead of plan order would be caught."""
    calls = {"n": 0}

    def _counting_scan_corpus(data_root: Path) -> object:
        calls["n"] += 1
        return _real_scan_corpus(data_root)

    monkeypatch.setattr(reconcile_module, "scan_corpus", _counting_scan_corpus)
    _write(tmp_path, "plans/zblock.toml", _CLEAN_SOURCE)
    _write(tmp_path, "plans/ablock.toml", _CLEAN_SOURCE)

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert calls["n"] == 1
    assert [o.block_id for o in report.plan.blocks] == ["ablock", "zblock"]
    assert [b.block_id for b in report.blocks] == [
        o.block_id for o in report.plan.blocks
    ]


# ===========================================================================
# Two sources, one invalid: one reconciliation
# ===========================================================================


def test_two_sources_one_invalid_reconciles_only_the_valid_one(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)
    _write(tmp_path, "plans/broken.toml", "this is not valid toml [[[\n")

    report = run_reconcile(tmp_path, today=TODAY)

    assert len(report.blocks) == 1
    assert report.blocks[0].block_id == _BLOCK_ID
    assert len(report.plan.blocks) == 2


# ===========================================================================
# A row dated today renders upcoming (Req 2.5)
# ===========================================================================


def test_a_row_dated_today_renders_upcoming(tmp_path: Path) -> None:
    _write_base_block(tmp_path)

    report = run_reconcile(tmp_path, today=TODAY)

    assert _row_state(report, _BLOCK_ID, "today-row") is RowState.UPCOMING


# ===========================================================================
# Two runs, equal inputs: byte-identical pages, every block unchanged on
# the second (assert rendered on the first)
# ===========================================================================


def test_two_runs_with_equal_inputs_are_byte_identical_and_unchanged_second(
    tmp_path: Path,
) -> None:
    _write_base_block(tmp_path)
    _write_workout_page(tmp_path, "not-logged-log", day="2026-04-06", sport="Run")

    first = run_reconcile(tmp_path, today=TODAY)
    assert _block_status(first, _BLOCK_ID) is BlockStatus.RENDERED
    after_first = _snapshot(tmp_path / BLOCKS_DIR)

    second = run_reconcile(tmp_path, today=TODAY)
    assert _block_status(second, _BLOCK_ID) is BlockStatus.UNCHANGED
    after_second = _snapshot(tmp_path / BLOCKS_DIR)

    assert after_first == after_second


# ===========================================================================
# reconcile_block: the pure per-block composition (Req 2.6, 4.3, 6.2)
# ===========================================================================


def test_reconcile_block_composes_match_rows_and_aggregate_mesocycles(
    tmp_path: Path,
) -> None:
    from fitdocs.plans.corpus import Corpus
    from fitdocs.plans.source import parse_block

    block = parse_block(_BASE_SOURCE, block_id=_BLOCK_ID)
    corpus = Corpus(workouts=())
    methodology = MethodologyProblem(detail="no page records a methodology")

    reconciliation = reconcile_block(
        block, corpus, today=TODAY, methodology=methodology
    )

    assert reconciliation.block_id == _BLOCK_ID
    assert {row.row_id for row in reconciliation.rows} == {
        "not-logged-row",
        "override-row",
        "today-row",
    }
    assert reconciliation.methodology is methodology
    assert reconciliation.problems, "the missing override stem must be reported"


# ===========================================================================
# ReconcileReport.failed (Req 8.9)
# ===========================================================================


def test_report_failed_is_false_with_no_plan_failure_and_no_block_problems(
    tmp_path: Path,
) -> None:
    _write_clean_block(tmp_path)

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert report.failed is False


def test_report_failed_is_true_on_a_plan_failure_with_problem_free_blocks(
    tmp_path: Path,
) -> None:
    """The other half of `failed` (Req 8.7): the plan pass's own failure --
    here an unparseable second source -- makes the report failed even when
    every reconciled block is problem-free, so `failed` cannot be derived
    from the blocks' problems alone."""
    _write_clean_block(tmp_path)
    _write(tmp_path, "plans/broken.toml", "this is not valid toml [[[\n")

    report = run_reconcile(tmp_path, today=date(2026, 5, 1))

    assert len(report.blocks) == 1
    assert not any(block.problems for block in report.blocks)
    assert report.plan.failed is True
    assert report.failed is True
