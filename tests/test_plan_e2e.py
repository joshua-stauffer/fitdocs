"""End-to-end and feature-level validation for the `plan` command
(training-blocks spec, task 4.6; Req 1.2, 1.10, 2.11, 7.8, 8.1, 8.4, 8.6,
8.9). See "E2E / CLI Tests" and "Cross-spec obligations (training-blocks ↔
plan-resolution)" item 5 in `.kiro/specs/training-blocks/design.md`.

Every plan source here is a copy of `tests/plans/fixtures/{minimal,full}.toml`'s
own bytes, written into a synthetic ``plans/`` directory under ``tmp_path`` --
the plan's hard rules forbid any write, in code or in a test's assertions,
under the resolved plan-source directory itself, so every scenario below
writes each source *before* the run and hashes the whole directory's bytes
before and after, asserting the snapshot never moves. No ``.fit`` file is
read and no real wiki page is ever used.

Every scenario below that has a `plans/` directory carries its own
`_snapshot(source_dir) == before` assertion (Req 1.2). Named mutation, run
once against the whole module rather than per-scenario (`plans.engine.run_plan`,
immediately after `source_dir` is resolved: insert `(source_dir /
"MUTATION_TOUCH").write_text("x")`): every one of those assertions reds
together (the extra file changes each snapshot's key set), confirming the
comparison is sensitive to a real write into the source directory and not
merely a no-op check over code that never approaches it; the two
absent-directory scenarios, which have no `plans/` directory to snapshot,
are unaffected.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.plans.engine as plans_engine_module
from fitdocs import layout
from fitdocs.cli import app
from fitdocs.contract import document_date, parse_frontmatter
from fitdocs.plans.source import PlanValidationError, load_block
from tests.test_history_e2e import _fake_system_date

runner = CliRunner()

FIXTURES = Path(__file__).parent / "plans" / "fixtures"
_MINIMAL = (FIXTURES / "minimal.toml").read_bytes()
_FULL = (FIXTURES / "full.toml").read_bytes()


def _plans_dir(root: Path, name: str = "plans") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Every regular file's bytes under `directory`, keyed by its relative
    POSIX path -- a stand-in for a per-file hash: two snapshots compare
    equal iff every file's content is byte-identical (mirrors
    `tests/plans/test_engine.py`'s own `_snapshot`, reimplemented locally
    here rather than imported, since that module's helper is private to its
    own test module and this file must not couple to it)."""
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _current_row_ids(source: Path, *, block_id: str) -> list[str]:
    """The block's current planned-workout ids, read through the real
    parser rather than hard-coded, so a renumbering of the fixture cannot
    silently desync this test's expected-path derivation from the engine's
    own."""
    block = load_block(source, block_id=block_id)
    return [row.id for row in block.current.rows]


# ==============================================================================
# Success over a synthetic root with two sources: exit 0, every owned path
# present, the report lines, and a planned page's frontmatter reads back
# through the contract's parser (Req 1.2, 8.1, 8.6).
# ==============================================================================


def test_two_sources_render_every_owned_page_with_report_and_frontmatter(
    tmp_path: Path,
) -> None:
    """Two fresh sources render for the first time: every block page and
    every planned page exists at its owned path, the report names the
    source directory and both `rendered` lines with their counts, and a
    planned page's frontmatter -- one row with no optional keys stated
    (`w1-mon`) and one with both (`w1-fri`) -- reads back through
    `contract.parse_frontmatter` with exactly the stated keys and types,
    and `contract.document_date` recovers the row's own date.

    Named mutation (`engine._render_and_write`: `for row in
    block.current.rows:` -> `for row in ():` in the planned-write loop):
    every planned-page-exists assertion below reds, and both `+n planned`
    report-count assertions red (`+5` and `+1` become unreachable since no
    planned path exists to assert against, and the printed counts drop to
    `+0`), while the block-page-exists and `Source:` assertions stay
    green -- the mutation touches only the planned-page write path."""
    source_dir = _plans_dir(tmp_path)
    full_source = source_dir / "full.toml"
    minimal_source = source_dir / "minimal.toml"
    full_source.write_bytes(_FULL)
    minimal_source.write_bytes(_MINIMAL)
    before = _snapshot(source_dir)

    full_row_ids = _current_row_ids(full_source, block_id="full")
    minimal_row_ids = _current_row_ids(minimal_source, block_id="minimal")
    assert full_row_ids, "the full fixture must carry at least one current row"
    assert minimal_row_ids, "the minimal fixture must carry at least one current row"

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Source: plans" in result.output
    assert (
        "rendered  plans/full.toml -> blocks/full.md "
        f"(+{len(full_row_ids)} planned, -0 removed)" in result.output
    )
    assert (
        "rendered  plans/minimal.toml -> blocks/minimal.md "
        f"(+{len(minimal_row_ids)} planned, -0 removed)" in result.output
    )

    assert layout.block_doc_path(tmp_path, "full").is_file()
    assert layout.block_doc_path(tmp_path, "minimal").is_file()
    for row_id in full_row_ids:
        assert layout.planned_doc_path(tmp_path, "full", row_id).is_file()
    for row_id in minimal_row_ids:
        assert layout.planned_doc_path(tmp_path, "minimal", row_id).is_file()

    # `w1-mon`: neither optional key stated.
    mon_text = layout.planned_doc_path(tmp_path, "full", "w1-mon").read_text(
        encoding="utf-8"
    )
    mon_front = parse_frontmatter(mon_text)
    assert mon_front is not None
    assert set(mon_front) == {
        "title",
        "type",
        "generator",
        "planned_version",
        "block",
        "planned_id",
        "mesocycle",
        "date",
        "sport",
    }
    assert isinstance(mon_front["title"], str)
    assert isinstance(mon_front["type"], str)
    assert isinstance(mon_front["generator"], str)
    assert isinstance(mon_front["planned_version"], int)
    assert isinstance(mon_front["block"], str)
    assert isinstance(mon_front["planned_id"], str)
    assert isinstance(mon_front["mesocycle"], int)
    assert isinstance(mon_front["date"], str)
    assert isinstance(mon_front["sport"], str)
    assert mon_front["planned_id"] == "w1-mon"
    assert mon_front["block"] == "full"

    # `w1-fri`: both optional keys stated (modality = "strength", indoor).
    fri_text = layout.planned_doc_path(tmp_path, "full", "w1-fri").read_text(
        encoding="utf-8"
    )
    fri_front = parse_frontmatter(fri_text)
    assert fri_front is not None
    assert set(fri_front) == {
        "title",
        "type",
        "generator",
        "planned_version",
        "block",
        "planned_id",
        "mesocycle",
        "date",
        "sport",
        "modality",
        "indoor",
    }
    assert isinstance(fri_front["modality"], str)
    assert isinstance(fri_front["indoor"], bool)
    assert fri_front["indoor"] is True

    full_block = load_block(full_source, block_id="full")
    mon_row = next(row for row in full_block.current.rows if row.id == "w1-mon")
    fri_row = next(row for row in full_block.current.rows if row.id == "w1-fri")
    assert document_date(mon_front) == mon_row.date
    assert document_date(fri_front) == fri_row.date

    assert _snapshot(source_dir) == before


# ==============================================================================
# Byte-identical pages across two plain runs; the second report says
# `unchanged` for both blocks (Req 8.4, 8.6).
# ==============================================================================


def test_two_plain_runs_are_byte_identical_and_report_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first run renders both blocks; a second, unmodified run reports
    `unchanged` for each and every rendered file's bytes are identical
    across the two runs. "Writes nothing" is pinned directly, not merely
    inferred from byte-identity (which an unconditional rewrite-with-
    identical-bytes would also satisfy): the second run is wrapped around a
    counting patch of `engine._atomic_write` and the count must be zero.

    Named mutations:
    - `engine._render_and_write`: `status = BlockStatus.RENDERED if (written
      or removed) else BlockStatus.UNCHANGED` -> always
      `BlockStatus.RENDERED`: the second run's `unchanged` assertions below
      red (falsity in the start state: the first run genuinely observes
      `rendered`, established earlier in this same test, so this pin is not
      trivially true either).
    - `engine._render_and_write`: gate `written.append(...)` on nothing (call
      `_atomic_write` unconditionally for every current row and the block
      page, regardless of the byte comparison against the existing file):
      the `_atomic_write_calls == 0` assertion below reds on the second run
      while the byte-identity and `unchanged`-line assertions stay green
      (an unconditional rewrite with identical bytes still produces
      identical bytes and still may report `unchanged` if the status branch
      is untouched), showing this assertion is the one that catches a
      rewrite the others cannot."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "full.toml").write_bytes(_FULL)
    (source_dir / "minimal.toml").write_bytes(_MINIMAL)
    before = _snapshot(source_dir)

    first = runner.invoke(app, ["plan", "--out", str(tmp_path)])
    assert first.exit_code == 0, first.output
    assert "rendered  plans/full.toml" in first.output
    assert "rendered  plans/minimal.toml" in first.output
    blocks_dir = tmp_path / "blocks"
    snapshot_after_first = _snapshot(blocks_dir)
    assert snapshot_after_first, "the first run must actually have written files"

    atomic_write_calls = 0
    original_atomic_write = plans_engine_module._atomic_write

    def _counting_atomic_write(path: Path, text: str) -> None:
        nonlocal atomic_write_calls
        atomic_write_calls += 1
        original_atomic_write(path, text)

    monkeypatch.setattr(plans_engine_module, "_atomic_write", _counting_atomic_write)

    second = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert second.exit_code == 0, second.output
    assert "unchanged plans/full.toml" in second.output
    assert "unchanged plans/minimal.toml" in second.output
    assert "rendered" not in second.output
    assert atomic_write_calls == 0
    assert _snapshot(blocks_dir) == snapshot_after_first
    assert _snapshot(source_dir) == before


# ==============================================================================
# Byte-identical across two runs executed under two different fake system
# dates AND time zones -- the behavioural half of Req 8.4's clock scan.
# ==============================================================================


def test_two_fake_dates_and_timezones_are_byte_identical(tmp_path: Path) -> None:
    """With the default (unresolved) resolution, `fitdocs plan` reads no
    clock, so two runs under two different fake system dates -- each also
    in a different IANA time zone, since a `TZ` change alone can cross
    midnight -- must still produce byte-identical pages.

    **Written knowing it moves** (design.md, Cross-spec obligations
    (training-blocks ↔ plan-resolution), item 5): once `plan-resolution`
    passes a resolver that reads the pass's `today`, a row's rendered state
    depends on `today` through the not-logged/upcoming split, and
    byte-identity across two dates then holds only for dates that lie on
    the same side of every fixture row. Both fake local dates chosen below
    -- 2026-03-01 (Pacific/Auckland) and 2027-06-15 (America/Los_Angeles),
    each taken as the *local* date under its own (timestamp, `TZ`) pair,
    since a `TZ` change alone can cross midnight relative to the UTC
    timestamp -- already lie *after* the last day of both fixtures
    (`full.toml` ends 2026-01-22; `minimal.toml` ends 2026-02-08), so this
    test's premise keeps holding once that spec adds the precondition; with
    the default resolver here, any two dates would prove the same thing,
    but these two are chosen so the choice needs no revisiting. Each pair's
    UTC timestamp is chosen so the local date does not roll over across the
    IANA zone's own offset (`Pacific/Auckland` is UTC+13 in March,
    `America/Los_Angeles` is UTC-7 in June); the precondition below asserts
    the actual local date directly, through the same `date.today()` call
    `render_block_page` would use if it read the clock, rather than trusting
    the timestamp arithmetic in this comment.

    Named mutation (`block_page.render_block_page`: `f"# {block.title}"` ->
    `f"# {block.title} {date.today().year}"`, a clock read): the
    byte-identity assertion below reds -- 2026 vs 2027 differ in the
    rendered heading -- while `test_two_plain_runs_are_byte_identical_and_
    report_unchanged` (no fake-date wrapping, real wall-clock year held
    constant across its own two runs) stays green, showing this mutation is
    caught specifically by the cross-date comparison, not merely by any
    two-run comparison."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "full.toml").write_bytes(_FULL)
    (source_dir / "minimal.toml").write_bytes(_MINIMAL)
    before = _snapshot(source_dir)
    blocks_dir = tmp_path / "blocks"

    with _fake_system_date(1772323200.0, tz="Pacific/Auckland"):  # local 2026-03-01
        assert date.today() > date(2026, 2, 8)
        first = runner.invoke(app, ["plan", "--out", str(tmp_path)])
    assert first.exit_code == 0, first.output
    snapshot_1 = _snapshot(blocks_dir)
    assert snapshot_1, "the first dated run must actually have written files"

    (blocks_dir).rename(tmp_path / "blocks-1")
    with _fake_system_date(1813089600.0, tz="America/Los_Angeles"):  # local 2027-06-15
        assert date.today() > date(2026, 2, 8)
        second = runner.invoke(app, ["plan", "--out", str(tmp_path)])
    assert second.exit_code == 0, second.output
    snapshot_2 = _snapshot(blocks_dir)
    assert snapshot_2, "the second dated run must actually have written files"

    assert snapshot_1 == snapshot_2
    assert _snapshot(source_dir) == before


# ==============================================================================
# Invalid beside valid: exit 1, the valid block still rendered, every
# problem printed (Req 2.11, 8.6, 8.9).
# ==============================================================================


def test_invalid_source_beside_valid_still_renders_the_valid_one(
    tmp_path: Path,
) -> None:
    """A malformed third source sits beside the two valid ones: the run
    exits 1, the invalid source is reported with its problem lines --
    matched against the real `PlanProblem.describe()` text `load_block`
    itself produces for this exact malformed source, not a hand-written
    guess (mirrors `tests/test_cli_plan.py`'s own version of this check) --
    and both valid blocks still render in full.

    Named mutation (`PlanReport.failed`: drop `BlockStatus.INVALID` from the
    status tuple): the exit-code assertion below reds (`0 != 1`) while the
    `rendered` and `invalid` line assertions -- driven by `_report_plan`
    printing `outcome.status` directly, untouched by this mutation -- stay
    green, showing the exit code specifically depends on `failed`'s
    membership test.

    Named mutation (`_report_plan`: drop the `for problem in
    outcome.problems:` loop): the `describe()`-text assertion below reds
    while the `invalid   plans/bad.toml` header line's own assertion stays
    green, since only the indented detail line depends on the dropped
    loop."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "full.toml").write_bytes(_FULL)
    (source_dir / "minimal.toml").write_bytes(_MINIMAL)
    bad_source = source_dir / "bad.toml"
    bad_source.write_text("not = [valid", encoding="utf-8")
    before = _snapshot(source_dir)

    with pytest.raises(PlanValidationError) as exc_info:
        load_block(bad_source, block_id="bad")
    (expected_problem,) = exc_info.value.problems

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "invalid   plans/bad.toml" in result.output
    assert f"  {expected_problem.describe()}" in result.output
    assert "rendered  plans/full.toml" in result.output
    assert "rendered  plans/minimal.toml" in result.output
    assert layout.block_doc_path(tmp_path, "full").is_file()
    assert layout.block_doc_path(tmp_path, "minimal").is_file()
    assert not layout.block_doc_path(tmp_path, "bad").exists()

    assert _snapshot(source_dir) == before


# ==============================================================================
# A foreign occupant at a block page path: exit 1, the run blocked, the
# occupant untouched, the path named (Req 7.8, 8.6, 8.9).
# ==============================================================================


def test_foreign_block_page_blocks_exit_one_and_leaves_file_untouched(
    tmp_path: Path,
) -> None:
    """A hand-written, non-generated file already occupies
    `blocks/minimal.md`: the run reports that block `blocked`, exits 1, and
    leaves the foreign file's bytes untouched -- the other source (`full`)
    still renders normally.

    Named mutation (`engine._is_foreign_occupant`: `return not
    is_generated(text)` -> `return False`): the `blocked` line and
    untouched-bytes assertions below red -- the hand-written file would
    instead be silently overwritten by the fresh render -- while
    `test_invalid_source_beside_valid_still_renders_the_valid_one`'s
    assertions stay green: that test's fixture places no foreign occupant
    at any write target, so `_is_foreign_occupant` is reached there too
    (every valid block's write targets go through it, absent or not) but
    already answers `False` for every one of them before the mutation
    (absence is never foreign, per the function's own `FileNotFoundError`
    branch), so forcing it to always answer `False` changes nothing for
    that test's outcome."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "full.toml").write_bytes(_FULL)
    (source_dir / "minimal.toml").write_bytes(_MINIMAL)
    before = _snapshot(source_dir)

    foreign_block_page = layout.block_doc_path(tmp_path, "minimal")
    foreign_block_page.parent.mkdir(parents=True, exist_ok=True)
    foreign_block_page.write_text("hand-written, not fitdocs'\n", encoding="utf-8")
    foreign_bytes = foreign_block_page.read_bytes()

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "blocked   plans/minimal.toml: blocks/minimal.md" in result.output
    assert "rendered  plans/full.toml" in result.output
    assert foreign_block_page.read_bytes() == foreign_bytes
    assert layout.block_doc_path(tmp_path, "full").is_file()

    assert _snapshot(source_dir) == before


# ==============================================================================
# The default-absent and configured-absent directory cases (Req 1.10, 8.9).
# ==============================================================================


def test_default_absent_plan_dir_exits_zero_with_note_and_no_blocks_dir(
    tmp_path: Path,
) -> None:
    """No `[plans]` table and no `plans/` directory at all: success with an
    explanatory note, and `blocks/` is never created.

    Named mutation (`plans.engine.run_plan`: `if plan_settings.path is
    None:` -> `if plan_settings.path is not None:`, inverting which branch
    is the note-and-succeed path): this test's exit-code assertion (`0 !=
    2`, since the inverted condition now falls through to the "configured"
    branch and raises `PlanSettingsError`) reds, while
    `test_configured_absent_plan_dir_exits_two` -- the inverted mutation's
    *other* branch -- reds its own exit-code assertion the opposite way
    (`2 != 0`), showing the two tests pin the same `if` from both sides."""
    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "no plan source directory" in result.output
    assert not (tmp_path / "blocks").exists()
    assert not (tmp_path / "plans").exists()


def test_configured_absent_plan_dir_exits_two(tmp_path: Path) -> None:
    """`[plans] path` names a directory that does not exist: a
    configuration error (distinct from the default-absent case above,
    where the same absence is silent success), exit 2, `blocks/` never
    created, and the resolved path itself is named in the error -- Req
    1.10's "naming the path", checked against the configured directory
    name rather than the ever-present `"path"` substring (which also
    matches the `[plans] path` key literal and so cannot tell a message
    that drops the resolved path from one that keeps it).

    Named mutation: the same `if plan_settings.path is None:` inversion
    named above reds this test's exit-code assertion the other way (`2 !=
    0`, since the inverted condition now takes the note-and-succeed branch
    for a *configured* path too).

    Named mutation (`plans.engine.run_plan`'s configured-absent-directory
    message: drop `{source_dir}` from the f-string, e.g. `f"{settings_file}:
    [plans] path resolves to a missing directory"`): the `"elsewhere" in
    result.output` assertion below reds
    while every other assertion in this test stays green -- confirming this
    assertion, unlike a bare `"path" in result.output`, actually depends on
    the resolved path being named."""
    (tmp_path / "fitdocs.toml").write_text(
        '[plans]\npath = "elsewhere"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["plan", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output
    assert not (tmp_path / "blocks").exists()
    assert "fitdocs.toml" in result.output
    assert "elsewhere" in result.output
