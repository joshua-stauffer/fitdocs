"""End-to-end and feature-level validation for the plan-resolution spec as a
whole (task 3.5). See "The reconciling pass, end to end" and "E2E / CLI
Tests" in `.kiro/specs/plan-resolution/design.md` (Req 4.3, 4.6, 5.2, 5.3,
5.4, 8.1, 8.3, 8.6, 8.7). Sibling e2e modules this one mirrors:
`tests/test_plan_e2e.py` (the byte-identity-across-fake-dates and the
`_stage_w1_mon_override_stem`/`_snapshot` shapes), `tests/test_history_e2e.py`
(the `_fake_system_date` context manager, imported rather than copied per
tasks.md 3.5's own instruction), and `tests/test_cli_reconcile.py` (the
CLI-chaining report-order shapes and the load/history-untouched
precondition).

Every plan source here is either a copy of
`tests/plans/fixtures/{full,minimal}.toml`'s own bytes or a small
hand-written TOML block built directly in a test, written into a synthetic
`plans/` directory under `tmp_path` before the run -- the plan's hard rules
forbid any write under the resolved plan-source directory itself, so every
scenario snapshots that directory's bytes before and after (`_snapshot`,
`_assert_untouched`) and asserts the snapshot never moves. `workouts/`,
all files (not only `.md`), is bracketed the same way around every run
under test in every scenario: the one file the pass may add there is the
ownership declaration, `workouts/AGENTS.md`, refreshed whenever a run
has at least one valid block; `_assert_untouched`'s `allow_new` names it
explicitly rather than filtering it out silently. Where a plain `sync`
also runs in the same scenario (its own file names -- the workout page,
its assets -- cannot be enumerated in advance), that bracket uses the
looser `_assert_no_stray_workout_files` instead, which checks file names
only (`.md`, `assets/`, `AGENTS.md`): it sees a stray file of any other
name, but not an idempotent rewrite of an existing page or a file placed
under `assets/` during that setup sync -- those two shapes are pinned by
the plan-only scenarios' `_assert_untouched` brackets (3 and 5 of the 8
scenarios red under them, respectively). Every synthetic
workout page is built by `_page` below, the same minimal frontmatter
shape `tests/plans/test_reconcile.py`'s own `_page` builds. The `.fit`
fixtures used are `tests.fixtures.builder.run_fit_bytes` and, in one
scenario, `tests.fixtures.builder.small_sport_fit_bytes`.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs import layout
from fitdocs.cli import app
from fitdocs.contract import DATE_KEY
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.sync import sync as sync_engine
from fitdocs.tiles import TileStore, load_tile_settings
from tests.fixtures import builder
from tests.test_history_e2e import _fake_system_date

runner = CliRunner()

FIXTURES = Path(__file__).parent / "plans" / "fixtures"
_FULL = (FIXTURES / "full.toml").read_bytes()
_MINIMAL = (FIXTURES / "minimal.toml").read_bytes()

_LINK_RE = re.compile(r"\]\((\.\./(?:\.\./)?workouts/[^)]+)\)")


# ==============================================================================
# Shared fixture helpers
# ==============================================================================


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every `fitdocs sync` network-free (mirrors `tests/test_cli.py`
    and `tests/test_cli_reconcile.py`)."""
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _page(
    *,
    day: str,
    sport: str | None = "Run",
    load_value: float | None = None,
    load_methodology: str | None = None,
) -> str:
    """A minimal, syntactically valid fitdocs workout document -- the same
    shape `tests/plans/test_reconcile.py::_page` builds."""
    lines = ["---", "title: Test Workout", "type: workout", f'{DATE_KEY}: "{day}"']
    if sport is not None:
        lines.append(f"sport: {sport}")
    if load_value is not None:
        lines.append(f"load_value: {load_value}")
    if load_methodology is not None:
        lines.append(f"load_methodology: {load_methodology}")
    lines.append("---")
    lines.append("")
    lines.append("# Test Workout")
    lines.append("")
    return "\n".join(lines) + "\n"


def _write_page(root: Path, name: str, **kwargs: object) -> Path:
    path = root / WORKOUTS_DIR / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_page(**kwargs), encoding="utf-8")  # type: ignore[arg-type]
    return path


def _stage_w1_mon_override_stem(root: Path) -> Path:
    """Stage `workouts/run-2026-01-06-am.md` -- `full.toml`'s `w1-mon`
    override names this exact stem (see `tests/test_plan_e2e.py`'s own
    helper of the same name, mirrored here since that module's helper is
    private to its own module); without it the override's stem is missing
    and the reconciling pass reports a per-file failure."""
    return _write_page(root, "run-2026-01-06-am", day="2026-01-06", sport="Run")


def _plans_dir(root: Path) -> Path:
    directory = root / "plans"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Every regular file's bytes under `directory`, keyed by its relative
    POSIX path (mirrors `tests/test_plan_e2e.py::_snapshot`)."""
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _mtime_snapshot(directory: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path.relative_to(directory): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _assert_no_stray_workout_files(
    directory: Path, *, allow: frozenset[str] = frozenset({"AGENTS.md"})
) -> None:
    """Every file under `directory` (a `workouts/` directory) is either
    named in `allow`, ends with `.md`, or sits under an `assets/`
    subdirectory -- sync's own legitimate, dynamically-named outputs. Used
    around a sync whose own file names cannot be enumerated in advance
    (the reconciling pass still runs on this call, quietly, whether or not
    a plan source is configured -- Req 8.5). A names-only check: a stray
    file of any other name (a dotfile marker, for instance) fails it; an
    idempotent rewrite of an existing page or a file placed under `assets/`
    does not, and those are pinned by the plan-only scenarios'
    `_assert_untouched` brackets instead."""
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(directory).as_posix()
        if rel in allow or rel.endswith(".md") or rel.startswith("assets/"):
            continue
        raise AssertionError(f"unexpected file under {directory}: {rel}")


def _assert_untouched(
    before: dict[str, bytes],
    directory: Path,
    *,
    allow_new: frozenset[str] = frozenset(),
) -> None:
    """Every file present in `before` is still present under `directory`
    with the same bytes, and no file appears that was not there before
    except one named in `allow_new` -- no silent key filter (a key present
    only in `before`, or a changed key, or an unexplained new key, all
    fail this). `allow_new` exists for exactly one reason across this
    module: `workouts/AGENTS.md`, the one file the plan pass may create
    there (the reconciling pass never writes a *workout* page, but a run
    with at least one valid block refreshes every declared directory's
    ownership declaration, `workouts/` included)."""
    after = _snapshot(directory)
    for key, value in before.items():
        assert key in after, f"{key} disappeared from {directory}"
        assert after[key] == value, f"{key} changed under {directory}"
    extra = set(after) - set(before)
    assert extra <= allow_new, f"unexplained new file(s) under {directory}: {extra}"


def _links_in(text: str) -> list[str]:
    return _LINK_RE.findall(text)


def _assert_every_link_resolves(page_path: Path, data_root: Path) -> int:
    """Every `](../workouts/...)` / `](../../workouts/...)` link in
    `page_path`'s text resolves, relative to `page_path`'s own directory,
    to an existing file. Returns the count of links checked."""
    text = page_path.read_text(encoding="utf-8")
    links = _links_in(text)
    for href in links:
        target = (page_path.parent / href).resolve()
        assert target.is_file(), (
            f"{page_path.relative_to(data_root)}: link {href!r} does not "
            f"resolve to an existing file (resolved to {target})"
        )
    return len(links)


def _all_block_and_planned_pages(data_root: Path) -> list[Path]:
    blocks_dir = data_root / "blocks"
    return sorted(p for p in blocks_dir.rglob("*.md") if p.is_file())


def _mesocycle_section_lines(lines: list[str], number: int) -> list[str]:
    """The block page's `## Mesocycle <number> -- ...` section, as a slice
    of `lines`: from its own heading up to (not including) the next `## `
    heading that is not another `## Mesocycle` heading (`## Resolution` or
    `## Revision record`)."""
    start_prefix = f"## Mesocycle {number} --"
    start = next(i for i, line in enumerate(lines) if line.startswith(start_prefix))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## ") and not lines[i].startswith("## Mesocycle"):
            end = i
            break
    return lines[start:end]


def _actual_load_line(lines: list[str], number: int) -> str:
    """The one `Actual load:` line inside mesocycle `number`'s own
    section -- distinct from any other mesocycle's own `Actual load:`
    line, which is why a plain `"Actual load:" in text` substring check
    cannot tell them apart in a block with more than one mesocycle."""
    return next(
        line
        for line in _mesocycle_section_lines(lines, number)
        if line.startswith("Actual load:")
    )


# ==============================================================================
# Success over a synthetic root with two plan sources and a synthetic corpus:
# block pages carry the placed text, every planned page carries its
# `## Resolution` section, every link resolves, and the reconciled report
# lines follow the plan pass's own (Req 4.3, 5.2, 5.3, 8.1, 8.6).
# ==============================================================================


def test_two_sources_with_synthetic_corpus_reconcile_end_to_end(
    tmp_path: Path,
) -> None:
    """Two plan sources (`full.toml`, `minimal.toml`) plus a synthetic
    corpus of a few workout pages, run through standalone `fitdocs plan`
    (the chained-through-`sync` ordering criterion has its own dedicated
    test below, since a hand-written synthetic workout page has no `load`
    region and `fitdocs load` -- chained ahead of the reconciling pass --
    rejects any recognized workout document lacking one; only a
    `.fit`-generated document carries one, so the synthetic-corpus
    scenario and the `sync`-chaining scenario are necessarily two
    different runs): block pages carry the placed match text, every
    planned page carries a `## Resolution` section, every relative link on
    every block/planned page resolves to an existing workout page, and the
    source directory plus every workout page is byte-identical before and
    after the run.

    Named mutation (`placement._fulfilling_bullet`: use `_block_link`
    instead of `_planned_link`): the every-link-resolves assertion below
    reds. `_all_block_and_planned_pages` walks in path-sorted order, and
    `blocks/full/w1-mon.md` -- the overridden row, whose fulfilling bullet
    is built by `_overridden_section`, also through `_fulfilling_bullet`
    -- sorts first among the affected planned pages, so it is the first
    one this assertion actually fails on: the block-depth
    `../workouts/...` href, read from planned-page depth
    (`blocks/<block>/<row>.md`), resolves one directory short, to
    `blocks/workouts/...`, which does not exist. Every other page with a
    fulfilling bullet (`blocks/full/w1-thu-b.md`, `blocks/minimal/w1-mon.md`)
    reds the same way.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    plans_dir = _plans_dir(data_root)
    (plans_dir / "full.toml").write_bytes(_FULL)
    (plans_dir / "minimal.toml").write_bytes(_MINIMAL)
    _stage_w1_mon_override_stem(data_root)
    # A synthetic corpus of a few workout pages: one matching `full`'s
    # "w1-thu-b" (2026-01-08, Run) and one matching `minimal`'s "w1-mon"
    # (2026-02-02, Run), so both blocks render at least one `matched:` row.
    _write_page(
        data_root,
        "matched-full-thu",
        day="2026-01-08",
        sport="Run",
        load_value=40.0,
        load_methodology="banister_1991",
    )
    _write_page(
        data_root,
        "matched-minimal-mon",
        day="2026-02-02",
        sport="Run",
        load_value=25.0,
        load_methodology="banister_1991",
    )
    before_source = _snapshot(plans_dir)
    before_workouts_synthetic = _snapshot(data_root / WORKOUTS_DIR)

    result = runner.invoke(app, ["plan", "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert "rendered  plans/full.toml" in result.output
    assert "rendered  plans/minimal.toml" in result.output

    full_block_page = layout.block_doc_path(data_root, "full").read_text(
        encoding="utf-8"
    )
    minimal_block_page = layout.block_doc_path(data_root, "minimal").read_text(
        encoding="utf-8"
    )
    assert "matched:" in full_block_page
    assert "overridden:" in full_block_page
    assert "matched:" in minimal_block_page

    # Every planned page of both blocks carries a `## Resolution` section.
    for row_id in ("w1-mon", "w1-thu-b", "w1-thu-a", "w1-fri", "w1-sun"):
        text = layout.planned_doc_path(data_root, "full", row_id).read_text(
            encoding="utf-8"
        )
        assert "## Resolution" in text, row_id
    minimal_planned = layout.planned_doc_path(data_root, "minimal", "w1-mon")
    assert "## Resolution" in minimal_planned.read_text(encoding="utf-8")

    # Every link on every block/planned page resolves.
    links_found = 0
    for page_path in _all_block_and_planned_pages(data_root):
        links_found += _assert_every_link_resolves(page_path, data_root)
    assert links_found >= 4, "the scan must have actually found real links"

    _assert_untouched(before_source, plans_dir)
    # The staged override-stem page and the two synthetic matched pages
    # must be untouched -- the reconciling pass never writes a *workout*
    # page; the only file it may add under `workouts/` is the ownership
    # declaration (`AGENTS.md`), refreshed because this run rendered a
    # block.
    _assert_untouched(
        before_workouts_synthetic,
        data_root / WORKOUTS_DIR,
        allow_new=frozenset({"AGENTS.md"}),
    )


def test_sync_from_fit_source_chains_the_pass_in_report_order(
    tmp_path: Path,
) -> None:
    """`fitdocs sync` from the `.fit` fixture source: the reconciling pass
    is chained after the wave-1 plan pass and after the load pass, in that
    printed order, and the block page carries the placed match text (Req
    4.3, 8.1, 8.6). Mirrors `tests/test_cli_reconcile.py`'s own chaining
    pins, matching a single-row plan source against the real synced
    document's own logged date (never a hand-written page, so the load
    pass -- also chained here -- never rejects it for lacking a `load`
    region).

    Named mutation (`cli._run_plan_pass`: swap the order of `_report_plan`
    and `_report_reconcile`): the "reconciled ... after rendered ..." order
    assertion below reds -- `_report_reconcile`'s "reconciled b1" line
    would print before the wave-1 plan report's own
    "rendered  plans/b1.toml" line.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    (source / "run.fit").parent.mkdir(parents=True, exist_ok=True)
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0, first.output
    _assert_no_stray_workout_files(data_root / WORKOUTS_DIR)
    workouts = sorted(
        p for p in (data_root / WORKOUTS_DIR).glob("*.md") if p.name != "AGENTS.md"
    )
    assert len(workouts) == 1, workouts
    logged_date = date.fromisoformat(workouts[0].stem[:10])

    plans_dir = _plans_dir(data_root)
    text = (
        'title = "Chain order fixture block"\n'
        f"starts = {(logged_date - timedelta(days=3)).isoformat()}\n"
        f"ends = {(logged_date + timedelta(days=3)).isoformat()}\n"
        'goal = "Chain-order fixture."\n'
        "mesocycle_days = 7\n\n"
        "[[workout]]\n"
        'id = "w1"\n'
        f"date = {logged_date.isoformat()}\n"
        'sport = "Run"\n'
        'title = "Easy run"\n'
        'summary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n'
    )
    (plans_dir / "b1.toml").write_text(text, encoding="utf-8")
    before_source = _snapshot(plans_dir)
    before_workouts = _snapshot(data_root / WORKOUTS_DIR)

    second = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert second.exit_code == 0, second.output
    out = second.output
    assert out.index("fitdocs load") < out.index("rendered  plans/b1.toml")
    assert out.index("rendered  plans/b1.toml") < out.index("reconciled b1")
    block_page = layout.block_doc_path(data_root, "b1").read_text(encoding="utf-8")
    assert "matched:" in block_page
    links_found = _assert_every_link_resolves(
        layout.block_doc_path(data_root, "b1"), data_root
    )
    assert links_found >= 1
    _assert_untouched(before_source, plans_dir)
    _assert_untouched(
        before_workouts, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )


# ==============================================================================
# Byte-identical pages across two runs: the second run reports `unchanged`
# for both blocks (plan-resolution Req 8.9 -- the reconciling pass reuses
# the plan pass's own byte comparison and unchanged report; training-blocks
# Req 8.4 is the underlying wave-1 byte-identity guarantee this extends).
# ==============================================================================


def test_two_runs_are_byte_identical_and_report_unchanged(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    plans_dir = _plans_dir(data_root)
    (plans_dir / "full.toml").write_bytes(_FULL)
    (plans_dir / "minimal.toml").write_bytes(_MINIMAL)
    _stage_w1_mon_override_stem(data_root)
    before_source = _snapshot(plans_dir)
    before_workouts_1 = _snapshot(data_root / WORKOUTS_DIR)

    first = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert first.exit_code == 0, first.output
    assert "rendered" in first.output
    blocks_snapshot_1 = _snapshot(data_root / "blocks")
    assert blocks_snapshot_1, "the first run must actually have written files"
    _assert_untouched(
        before_workouts_1, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )
    before_workouts_2 = _snapshot(data_root / WORKOUTS_DIR)

    second = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert second.exit_code == 0, second.output
    assert "unchanged plans/full.toml" in second.output
    assert "unchanged plans/minimal.toml" in second.output
    assert "rendered" not in second.output
    blocks_snapshot_2 = _snapshot(data_root / "blocks")
    assert blocks_snapshot_2 == blocks_snapshot_1
    _assert_untouched(
        before_workouts_2, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )

    _assert_untouched(before_source, plans_dir)


# ==============================================================================
# Byte-identical across two fake system dates on the same side of every
# fixture row, and a scan across a fake date that crosses exactly one row
# (Req 5.2: "when only today changes, the pages shall differ only in the
# planned workouts whose state changes") -- the only pin of `cli._today`
# via `date.today()` vs `datetime.now()` (tasks.md 3.2's implementation
# note).
# ==============================================================================

_CROSS_BLOCK_ID = "cross"
_CROSS_ROWS = (
    ("r1", date(2030, 6, 3)),
    ("r2", date(2030, 6, 8)),
    ("r3", date(2030, 6, 13)),
)


def _write_cross_source(plans_dir: Path) -> Path:
    """Three current rows, none logged (an empty corpus), spanning three
    widely separated dates within one 15-day mesocycle -- built so a
    single `today` value can be chosen strictly between any two of the
    three dates, splitting them cleanly into a `NOT_LOGGED` side and an
    `UPCOMING` side (`plans.matching._split_state`)."""
    rows = "\n".join(
        f'[[workout]]\nid = "{row_id}"\ndate = {row_date.isoformat()}\n'
        'sport = "Run"\ntitle = "Cross row"\nsummary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n'
        for row_id, row_date in _CROSS_ROWS
    )
    text = (
        'title = "Cross fixture block"\n'
        "starts = 2030-06-01\n"
        "ends = 2030-06-15\n"
        'goal = "Crossing-row fixture."\n'
        "mesocycle_days = 15\n\n" + rows
    )
    path = plans_dir / f"{_CROSS_BLOCK_ID}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _epoch_utc_noon(day: date) -> float:
    return datetime.combine(day, time(12, 0), tzinfo=UTC).timestamp()


def _assert_precondition_same_side(today: date) -> None:
    """`today` puts every fixture row on the same side (`UPCOMING`): every
    row's date is `>= today` -- the precondition the byte-identity pin
    needs to be non-vacuous."""
    for _row_id, row_date in _CROSS_ROWS:
        assert row_date >= today, (row_date, today)


def test_two_fake_dates_on_the_same_side_are_byte_identical(
    tmp_path: Path,
) -> None:
    """Two fake system dates, both before every fixture row (so every row
    resolves `UPCOMING` under both): the rendered block and planned pages
    are byte-identical across the two runs.

    Named mutation (`placement._block_lines`: append `date.today().isoformat()`
    to the block-level lines, a clock read placement.py's own docstring
    forbids): this assertion reds -- `time.time` is faked to a different
    instant under each run (`_fake_system_date` hooks it), so
    `date.today()` reads a different calendar date each time even though
    both lie on the same side of every row.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    plans_dir = _plans_dir(data_root)
    _write_cross_source(plans_dir)
    before_source = _snapshot(plans_dir)
    before_workouts_1 = _snapshot(data_root / WORKOUTS_DIR)

    with _fake_system_date(_epoch_utc_noon(date(2030, 5, 30)), tz="UTC"):
        assert date.today() == date(2030, 5, 30)
        _assert_precondition_same_side(date.today())
        first = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert first.exit_code == 0, first.output
    snapshot_1 = _snapshot(data_root / "blocks")
    assert snapshot_1, "the first dated run must actually have written files"
    _assert_untouched(
        before_workouts_1, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )
    before_workouts_2 = _snapshot(data_root / WORKOUTS_DIR)

    (data_root / "blocks").rename(tmp_path / "blocks-1")
    with _fake_system_date(_epoch_utc_noon(date(2030, 6, 1)), tz="UTC"):
        assert date.today() == date(2030, 6, 1)
        _assert_precondition_same_side(date.today())
        second = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert second.exit_code == 0, second.output
    snapshot_2 = _snapshot(data_root / "blocks")
    assert snapshot_2, "the second dated run must actually have written files"
    _assert_untouched(
        before_workouts_2, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )

    assert snapshot_1 == snapshot_2
    _assert_untouched(before_source, plans_dir)


def test_a_fake_date_crossing_exactly_one_row_changes_exactly_that_row(
    tmp_path: Path,
) -> None:
    """A fake date strictly between `r1`'s date (2030-06-03) and `r2`'s
    (2030-06-08): `r1` crosses from `UPCOMING` to `NOT_LOGGED` while `r2`
    and `r3` stay `UPCOMING` -- exactly `r1`'s block-page table row and
    `r1`'s planned-page `## Resolution` section change, the block page's
    per-state count line necessarily moves with it (it was "3 upcoming",
    now "1 not logged, 2 upcoming"), and every other line of both the
    block page and every other planned page is byte-identical.

    Named mutation (`cli._today`: `datetime.now(_local_tz()).date()`
    instead of `date.today()`): the fake-date hook (`time.time`) never
    reaches `datetime.now()`, so both runs below read the *real* wall-clock
    date instead of the faked ones and the pass sees the same `today` both
    times -- `r1` never crosses and the diff assertions below (which
    require r1's row/section to actually change) red. THIS is the only pin
    of that mechanism in the repo (tasks.md 3.2's implementation note).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    plans_dir = _plans_dir(data_root)
    _write_cross_source(plans_dir)
    before_source = _snapshot(plans_dir)
    before_workouts_1 = _snapshot(data_root / WORKOUTS_DIR)
    block_page_path = layout.block_doc_path(data_root, _CROSS_BLOCK_ID)
    r1_path = layout.planned_doc_path(data_root, _CROSS_BLOCK_ID, "r1")
    r2_path = layout.planned_doc_path(data_root, _CROSS_BLOCK_ID, "r2")
    r3_path = layout.planned_doc_path(data_root, _CROSS_BLOCK_ID, "r3")

    before_today = date(2030, 6, 1)
    with _fake_system_date(_epoch_utc_noon(before_today), tz="UTC"):
        assert date.today() == before_today
        for _row_id, row_date in _CROSS_ROWS:
            assert row_date >= before_today
        before = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert before.exit_code == 0, before.output
    block_before = block_page_path.read_text(encoding="utf-8").splitlines()
    r1_before = r1_path.read_text(encoding="utf-8").splitlines()
    r2_before = r2_path.read_text(encoding="utf-8").splitlines()
    r3_before = r3_path.read_text(encoding="utf-8").splitlines()
    assert "Planned workouts: 3 -- 3 upcoming." in block_before
    assert sum(line.rstrip().endswith("| upcoming |") for line in block_before) == 3
    _assert_untouched(
        before_workouts_1, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )
    before_workouts_2 = _snapshot(data_root / WORKOUTS_DIR)

    crossing_today = date(2030, 6, 5)
    with _fake_system_date(_epoch_utc_noon(crossing_today), tz="UTC"):
        assert date.today() == crossing_today
        # Precondition: exactly one fixture row is `< today` (r1) while the
        # other two are `>= today` (r2, r3).
        sides = [row_date < crossing_today for _row_id, row_date in _CROSS_ROWS]
        assert sides == [True, False, False], sides
        after = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert after.exit_code == 0, after.output
    _assert_untouched(
        before_workouts_2, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )
    block_after = block_page_path.read_text(encoding="utf-8").splitlines()
    r1_after = r1_path.read_text(encoding="utf-8").splitlines()
    r2_after = r2_path.read_text(encoding="utf-8").splitlines()
    r3_after = r3_path.read_text(encoding="utf-8").splitlines()

    # r2 and r3's planned pages are wholly untouched.
    assert r2_after == r2_before
    assert r3_after == r3_before

    # r1's planned page: exactly its one-line `## Resolution` section
    # differs (`"Upcoming."` -> `"Not logged: ..."`), everything else
    # byte-identical.
    assert r1_before != r1_after
    assert "Upcoming." in r1_before
    assert "Not logged: no logged workout on 2030-06-03 is of this type." in r1_after
    diff_lines_r1 = [
        (i, b, a)
        for i, (b, a) in enumerate(zip(r1_before, r1_after, strict=True))
        if b != a
    ]
    assert len(r1_before) == len(r1_after)
    assert [b for _, b, _ in diff_lines_r1] == ["Upcoming."]
    assert [a for _, _, a in diff_lines_r1] == [
        "Not logged: no logged workout on 2030-06-03 is of this type."
    ]

    # The block page: exactly r1's table row and the block-level count
    # line change; the count line necessarily moves with the row (3
    # upcoming -> 1 not logged, 2 upcoming), so "nothing else changes"
    # would be unsatisfiable -- both named lines are asserted explicitly.
    assert len(block_before) == len(block_after)
    diff_lines_block = [
        (i, b, a)
        for i, (b, a) in enumerate(zip(block_before, block_after, strict=True))
        if b != a
    ]
    changed_before = {b for _, b, _ in diff_lines_block}
    changed_after = {a for _, _, a in diff_lines_block}
    assert "Planned workouts: 3 -- 3 upcoming." in changed_before
    assert "Planned workouts: 3 -- 1 not logged, 2 upcoming." in changed_after
    r1_row_before = next(
        line for line in block_before if "2030-06-03" in line and "upcoming" in line
    )
    assert r1_row_before in changed_before
    r1_row_after = next(
        line for line in block_after if "2030-06-03" in line and "not logged" in line
    )
    assert r1_row_after in changed_after
    # Exactly two lines differ: the count line and r1's table row.
    assert len(diff_lines_block) == 2

    _assert_untouched(before_source, plans_dir)


# ==============================================================================
# A page added to the corpus between runs changes exactly the row it
# matches (cell + section) and the mesocycle sum whose window contains it
# -- and nothing belonging to any other row or any other mesocycle (Req
# 5.4, 6.3-6.7). Two rows in two different mesocycles, one already matched
# before the first run (so methodology is already chosen and stays put),
# isolate that from the block-level count line, which necessarily moves
# with the newly-matched row's own state.
# ==============================================================================


def test_page_added_between_runs_changes_exactly_its_row_and_the_sum(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    plans_dir = _plans_dir(data_root)
    block_id = "added"
    # Two 7-day mesocycles (2020-01-01..07, 2020-01-08..14); r1 in the
    # first, r2 in the second -- both safely in the past, `NOT_LOGGED`
    # under any real wall-clock `today` this suite ever runs under, absent
    # a match.
    r1_date = date(2020, 1, 5)
    r2_date = date(2020, 1, 12)
    text = (
        'title = "Added-page fixture block"\n'
        "starts = 2020-01-01\n"
        "ends = 2020-01-14\n"
        'goal = "Added-page fixture."\n'
        "mesocycle_days = 7\n\n"
        "[[workout]]\n"
        'id = "r1"\n'
        f"date = {r1_date.isoformat()}\n"
        'sport = "Run"\n'
        'title = "Added row one"\n'
        'summary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n\n'
        "[[workout]]\n"
        'id = "r2"\n'
        f"date = {r2_date.isoformat()}\n"
        'sport = "Run"\n'
        'title = "Added row two"\n'
        'summary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n'
    )
    (plans_dir / f"{block_id}.toml").write_text(text, encoding="utf-8")
    before_source = _snapshot(plans_dir)
    block_page_path = layout.block_doc_path(data_root, block_id)
    r1_path = layout.planned_doc_path(data_root, block_id, "r1")
    r2_path = layout.planned_doc_path(data_root, block_id, "r2")

    # r1 already has a matching logged, scored page BEFORE the first run --
    # this is the corpus's only logged workout at that point, so the
    # block's methodology is already chosen (and stays chosen) by the time
    # r2's own match is added between runs.
    _write_page(
        data_root,
        "matched-r1",
        day=r1_date.isoformat(),
        sport="Run",
        load_value=40.0,
        load_methodology="banister_1991",
    )
    before_workouts_1 = _snapshot(data_root / WORKOUTS_DIR)

    first = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert first.exit_code == 0, first.output
    _assert_untouched(
        before_workouts_1, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )
    block_before = block_page_path.read_text(encoding="utf-8").splitlines()
    r1_before = r1_path.read_text(encoding="utf-8").splitlines()
    r2_before = r2_path.read_text(encoding="utf-8").splitlines()
    assert "Matched (exact):" in r1_path.read_text(encoding="utf-8")
    assert "Not logged:" in r2_path.read_text(encoding="utf-8")
    meso1_before = _actual_load_line(block_before, 1)
    meso2_before = _actual_load_line(block_before, 2)
    assert meso1_before.startswith("Actual load: 40 --")
    # Precondition: r2 is not yet matched, and its mesocycle's total is
    # absent -- the run under test must actually change something.
    assert meso2_before.startswith("Actual load: not computed")
    methodology_before = next(
        line for line in block_before if line.startswith("Methodology:")
    )
    assert methodology_before.startswith("Methodology: banister_1991")

    # A logged page matching r2's day and sport, added to the corpus
    # between runs.
    _write_page(
        data_root,
        "matched-r2",
        day=r2_date.isoformat(),
        sport="Run",
        load_value=50.0,
        load_methodology="banister_1991",
    )
    before_workouts_2 = _snapshot(data_root / WORKOUTS_DIR)

    second = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert second.exit_code == 0, second.output
    _assert_untouched(
        before_workouts_2, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )
    block_after = block_page_path.read_text(encoding="utf-8").splitlines()
    r1_after = r1_path.read_text(encoding="utf-8").splitlines()
    r2_after = r2_path.read_text(encoding="utf-8").splitlines()

    assert "Matched (exact):" in r2_path.read_text(encoding="utf-8")
    meso2_after = _actual_load_line(block_after, 2)
    assert meso2_after.startswith("Actual load: 50 --")

    # r1's planned page: wholly untouched -- r2's own match cannot affect
    # a row it does not belong to.
    assert r1_after == r1_before

    # r2's planned page: only its `## Resolution` section content changed.
    assert len(r2_before) != len(r2_after)  # the matched section gains a bullet
    assert (
        r2_before[: r2_before.index("## Resolution")]
        == r2_after[: r2_after.index("## Resolution")]
    )

    # The block page: exactly r2's table row, the block-level count line,
    # and mesocycle 2's `Actual load:` line change. Mesocycle 1's own
    # `Actual load:` line and the block's `Methodology:` line -- already
    # settled by r1's pre-existing match -- are byte-identical.
    assert len(block_before) == len(block_after)
    diff = [(b, a) for b, a in zip(block_before, block_after, strict=True) if b != a]
    changed_before = {b for b, _ in diff}
    changed_after = {a for _, a in diff}
    assert any(line.startswith("Planned workouts: 2 --") for line in changed_before)
    assert any(line.startswith("Planned workouts: 2 --") for line in changed_after)
    assert meso2_before in changed_before
    assert meso2_after in changed_after
    assert any("not logged" in line for line in changed_before)
    assert any("matched:" in line for line in changed_after)
    assert len(diff) == 3
    assert methodology_before not in changed_before
    assert _actual_load_line(block_after, 1) == meso1_before

    _assert_untouched(before_source, plans_dir)


# ==============================================================================
# A missing override stem through `sync`: exit 1 (per-file failure) while
# the block still renders (Req 8.7).
# ==============================================================================


def test_missing_override_stem_through_sync_exits_one_and_still_renders(
    tmp_path: Path,
) -> None:
    """Named mutation (`cli.sync_command`: drop `or plan_report.failed` from
    the explicit-source `_finish` call): the exit-code assertion below reds
    (`1 != 0`) -- an override problem the reconciling pass finds would no
    longer fold into the run's exit status."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    (source / "run.fit").parent.mkdir(parents=True, exist_ok=True)
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    _assert_no_stray_workout_files(data_root / WORKOUTS_DIR)
    workouts = sorted(
        p for p in (data_root / WORKOUTS_DIR).glob("*.md") if p.name != "AGENTS.md"
    )
    assert len(workouts) == 1, workouts
    logged_date = date.fromisoformat(workouts[0].stem[:10])

    plans_dir = _plans_dir(data_root)
    text = (
        'title = "Missing stem fixture block"\n'
        f"starts = {(logged_date.replace(day=1)).isoformat()}\n"
        f"ends = {logged_date.isoformat()}\n"
        'goal = "Missing-stem fixture."\n'
        "mesocycle_days = 7\n\n"
        "[[workout]]\n"
        'id = "w1"\n'
        f"date = {logged_date.isoformat()}\n"
        'sport = "Run"\n'
        'title = "Easy run"\n'
        'summary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n\n'
        "[[override]]\n"
        f"date = {logged_date.isoformat()}\n"
        'id = "w1"\n'
        'stems = ["no-such-stem"]\n'
        'reason = "Test override."\n'
    )
    (plans_dir / "missing.toml").write_text(text, encoding="utf-8")
    before_source = _snapshot(plans_dir)
    before_workouts = _snapshot(data_root / WORKOUTS_DIR)

    result2 = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result2.exit_code == 1, result2.output
    assert "stem `no-such-stem` not found among the logged workouts" in result2.output
    block_page = layout.block_doc_path(data_root, "missing")
    assert block_page.is_file()
    assert block_page.stat().st_size > 0
    _assert_untouched(before_source, plans_dir)
    _assert_untouched(
        before_workouts, data_root / WORKOUTS_DIR, allow_new=frozenset({"AGENTS.md"})
    )


# ==============================================================================
# `load` and `history` leave `blocks/` untouched (Req 4.6, 8.3).
# ==============================================================================


def test_load_and_history_leave_blocks_untouched(tmp_path: Path) -> None:
    """Mirrors `tests/test_cli_reconcile.py::test_load_and_history_leave_
    blocks_untouched`'s own two preconditions: (1) the plan run must have
    actually written at least the block page, and (2) a second matching
    logged page, added to the corpus after the plan run but before `load`/
    `history`, WOULD change the block page's text if the pass ran again
    (`matched:` -> `matched (absorbed 2):`) -- so the byte comparison below
    is sensitive, not vacuous."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    (source / "run.fit").parent.mkdir(parents=True, exist_ok=True)
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    _assert_no_stray_workout_files(data_root / WORKOUTS_DIR)
    workouts = sorted(
        p for p in (data_root / WORKOUTS_DIR).glob("*.md") if p.name != "AGENTS.md"
    )
    logged_date = date.fromisoformat(workouts[0].stem[:10])

    plans_dir = _plans_dir(data_root)
    text = (
        'title = "Load/history fixture block"\n'
        f"starts = {(logged_date.replace(day=1)).isoformat()}\n"
        f"ends = {logged_date.isoformat()}\n"
        'goal = "Load/history fixture."\n'
        "mesocycle_days = 7\n\n"
        "[[workout]]\n"
        'id = "w1"\n'
        f"date = {logged_date.isoformat()}\n"
        'sport = "Run"\n'
        'title = "Easy run"\n'
        'summary = "Zone 2"\n'
        'prescription = "30 minutes easy."\n'
    )
    (plans_dir / "lh.toml").write_text(text, encoding="utf-8")
    before_source = _snapshot(plans_dir)
    before_workouts_plan = _snapshot(data_root / WORKOUTS_DIR)

    plan_result = runner.invoke(app, ["plan", "--out", str(data_root)])
    assert plan_result.exit_code == 0, plan_result.output
    _assert_untouched(
        before_workouts_plan,
        data_root / WORKOUTS_DIR,
        allow_new=frozenset({"AGENTS.md"}),
    )
    blocks_dir = data_root / "blocks"
    before = _mtime_snapshot(blocks_dir)
    assert before, "the plan run must have written at least the block page"

    # A second, real .fit-derived logged workout on the SAME day as the
    # plan's one row, added to the corpus after the plan run -- a matching
    # page that WOULD change the block page's text (matched -> matched
    # (absorbed 2)) if the pass ran again. Written through the sync
    # *engine* directly (never a hand-written frontmatter page, which
    # `fitdocs load` -- chained ahead of the reconciling pass, and reached
    # again by the `load`/`history` calls below -- would reject for
    # lacking a `load` region), deliberately bypassing the CLI, so this
    # setup step's own chained plan pass never touches `blocks/` before
    # `load`/`history` do.
    second_source = tmp_path / "src2"
    (second_source).mkdir(parents=True, exist_ok=True)
    (second_source / "run2.fit").write_bytes(
        builder.small_sport_fit_bytes(9101, "running", timestamp_offset=3600)
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
        p.stem for p in (data_root / WORKOUTS_DIR).glob("*.md") if p.name != "AGENTS.md"
    )
    assert len(workout_stems) == 2, workout_stems
    assert all(stem.startswith(logged_date.isoformat()) for stem in workout_stems), (
        workout_stems
    )
    # After the engine sync (the point tasks.md 3.5 names for this
    # scenario), `load`/`history` must not write under `workouts/` or the
    # plan source either.
    before_workouts_lh = _snapshot(data_root / WORKOUTS_DIR)

    load_result = runner.invoke(app, ["load", "--out", str(data_root), "--no-prompt"])
    assert load_result.exit_code == 0, load_result.output
    history_result = runner.invoke(app, ["history", "--out", str(data_root)])
    assert history_result.exit_code == 0, history_result.output

    after = _mtime_snapshot(blocks_dir)
    assert after == before
    _assert_untouched(before_workouts_lh, data_root / WORKOUTS_DIR)
    _assert_untouched(before_source, plans_dir)
