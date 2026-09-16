"""Tests for the package's one writing module (training-blocks spec, task
4.2; Req 1.1, 1.2, 1.10, 2.11, 3.9, 4.1, 4.9, 5.1, 5.5-5.7, 6.3, 7.8-7.10,
8.1, 8.4-8.7, 8.10). See "PlanEngine (`src/fitdocs/plans/engine.py`)" in
`.kiro/specs/training-blocks/design.md`.

Every plan source here is a **copy of `tests/plans/fixtures/{minimal,full}.toml`'s
own bytes**, written into a synthetic directory under `tmp_path` as fixture
setup -- `tests/plans/fixtures/*.toml` belongs to task 2.3 alone (tasks.md,
Test File Ownership), and the plan's hard rules forbid any write, in code or
in a test's assertions, under the resolved plan-source directory itself.
`run_plan` is never pointed at `tests/plans/fixtures/` directly: every
scenario below that creates a plan-source directory (every scenario except
the absent-directory and configured-non-directory ones, which have no
source directory to hash) hashes its bytes before and after the run
(`_snapshot`), asserting the snapshot is unchanged no matter what the run
does.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

import fitdocs.plans.engine as engine_module
from fitdocs.contract import GENERATED_PREFIX, NOTES_PLACEHOLDER
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.plans.engine import BlockOutcome, BlockStatus, PlanReport, run_plan
from fitdocs.plans.model import Block
from fitdocs.plans.resolution import (
    MesocycleResolution,
    Resolution,
    RowResolution,
    unresolved,
)
from fitdocs.plans.settings import PlanSettingsError
from fitdocs.plans.source import load_block

FIXTURES = Path(__file__).parent / "fixtures"
_MINIMAL = (FIXTURES / "minimal.toml").read_bytes()
_FULL = (FIXTURES / "full.toml").read_bytes()

_BLOCKS_DIR = "blocks"

_ZERO_ROW = b"""\
title = "Empty block"
starts = 2026-02-02
ends = 2026-02-08
goal = "No planned workouts yet."
mesocycle_days = 7
"""
"""A valid source with zero `[[workout]]` rows -- isolates the pages-
directory foreign check from the (empty) per-row planned-page foreign
loop, since a block with rows would also flag the same occupant through
its planned-page paths (masking the pages-directory check specifically)."""


# --- fixture-building helpers ------------------------------------------------


def _write_settings(root: Path, text: str = "") -> None:
    (root / "fitdocs.toml").write_text(text, encoding="utf-8")


def _plans_dir(root: Path, name: str = "plans") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _snapshot(directory: Path) -> dict[str, bytes]:
    """Every regular file's bytes under `directory`, keyed by its relative
    POSIX path -- a stand-in for a hash: two snapshots compare equal iff
    every file's content is byte-identical."""
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _one(report: PlanReport, block_id: str) -> BlockOutcome:
    matches = [outcome for outcome in report.blocks if outcome.block_id == block_id]
    assert len(matches) == 1, f"expected exactly one outcome for {block_id!r}"
    return matches[0]


# ==============================================================================
# The rendered/unchanged pair (Req 8.5). Named mutation: report `rendered`
# even when every target's bytes are equal.
# ==============================================================================


def test_rendered_then_unchanged_pair_is_byte_identical(tmp_path: Path) -> None:
    """First run renders; a *second* run over the same, untouched source
    reports `unchanged` and writes nothing -- and every file's bytes are
    identical across the two runs.

    Named mutation: in `_render_and_write`, change
    `status = BlockStatus.RENDERED if (written or removed) else
    BlockStatus.UNCHANGED` to always `BlockStatus.RENDERED` -- the second
    run's status assertion below reds (falsity in the start state: the
    FIRST run must actually observe `RENDERED`, or this pin would be
    trivially true)."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    first = run_plan(tmp_path)
    outcome_1 = _one(first, "a")
    assert outcome_1.status == BlockStatus.RENDERED
    assert outcome_1.written != ()
    block_bytes_1 = (tmp_path / _BLOCKS_DIR / "a.md").read_bytes()
    planned_bytes_1 = (tmp_path / _BLOCKS_DIR / "a" / "w1-mon.md").read_bytes()

    second = run_plan(tmp_path)
    outcome_2 = _one(second, "a")
    assert outcome_2.status == BlockStatus.UNCHANGED
    assert outcome_2.written == ()
    assert outcome_2.removed == ()
    assert (tmp_path / _BLOCKS_DIR / "a.md").read_bytes() == block_bytes_1
    assert (tmp_path / _BLOCKS_DIR / "a" / "w1-mon.md").read_bytes() == planned_bytes_1
    # A source that has at least one *discovered* .toml is never the "no
    # plan sources" no-op path, whether the block itself renders or is
    # merely unchanged.
    assert first.note is None
    assert second.note is None
    assert first.failed is False
    assert second.failed is False

    assert _snapshot(source_dir) == before


# ==============================================================================
# An invalid source beside a valid one (Req 2.11).
# ==============================================================================


def test_invalid_source_beside_valid_leaves_invalid_pages_untouched(
    tmp_path: Path,
) -> None:
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    (source_dir / "b.toml").write_text("not = [valid", encoding="utf-8")
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    # Pre-existing pages for the block that is ABOUT to be invalid this run
    # -- arbitrary bytes, standing in for whatever a prior valid render left
    # behind.
    stale_page = tmp_path / _BLOCKS_DIR / "b.md"
    stale_page.parent.mkdir(parents=True)
    stale_page.write_text("pre-existing content for b\n", encoding="utf-8")
    stale_bytes = stale_page.read_bytes()

    report = run_plan(tmp_path)

    outcome_a = _one(report, "a")
    outcome_b = _one(report, "b")
    assert outcome_a.status == BlockStatus.RENDERED
    assert outcome_b.status == BlockStatus.INVALID
    assert outcome_b.problems != ()
    assert stale_page.read_bytes() == stale_bytes
    # Req 7.10 negative: an invalid source's own id is still "discovered"
    # (it has a source file, just an invalid one), so its pre-existing
    # `blocks/b.md` must NOT be reported unsourced -- only a page with no
    # matching source AT ALL belongs in `unsourced`.
    assert report.unsourced == ()
    assert report.failed is True

    assert _snapshot(source_dir) == before


# ==============================================================================
# A foreign block page and, separately, a foreign planned page (Req 7.8).
# Named mutation: skip the foreign check for planned pages.
# ==============================================================================


def test_foreign_block_page_blocks_nothing_written(tmp_path: Path) -> None:
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    block_page = tmp_path / _BLOCKS_DIR / "a.md"
    block_page.parent.mkdir(parents=True)
    block_page.write_text("hand-written, not fitdocs'\n", encoding="utf-8")
    foreign_bytes = block_page.read_bytes()

    report = run_plan(tmp_path)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.BLOCKED
    assert outcome.foreign == ("blocks/a.md",)
    assert outcome.written == ()
    assert outcome.removed == ()
    assert block_page.read_bytes() == foreign_bytes
    assert not (tmp_path / _BLOCKS_DIR / "a").exists()
    assert report.failed is True

    assert _snapshot(source_dir) == before


def test_foreign_planned_page_blocks_nothing_written(tmp_path: Path) -> None:
    """A foreign occupant at the *planned* page path blocks the block even
    though the block page path itself is untouched -- this is the pin the
    "skip the foreign check for planned pages" mutation reds.

    Named mutation: delete the `for planned_path in planned_paths.values():
    if _is_foreign_occupant(...)` loop from `_render_and_write` -- the
    block would then proceed past the foreign check straight to a
    successful render, and `outcome.status == BlockStatus.BLOCKED` reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    planned_page = tmp_path / _BLOCKS_DIR / "a" / "w1-mon.md"
    planned_page.parent.mkdir(parents=True)
    planned_page.write_text("hand-written planned page\n", encoding="utf-8")
    foreign_bytes = planned_page.read_bytes()

    report = run_plan(tmp_path)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.BLOCKED
    assert outcome.foreign == ("blocks/a/w1-mon.md",)
    assert outcome.written == ()
    assert not (tmp_path / _BLOCKS_DIR / "a.md").exists()
    assert planned_page.read_bytes() == foreign_bytes

    assert _snapshot(source_dir) == before


def test_pages_directory_occupied_by_a_file_is_foreign(tmp_path: Path) -> None:
    """The pages directory itself must be absent or a real directory
    (Req 7.8) -- a plain *file* occupying `blocks/<id>` blocks the block,
    distinct from the block-page and planned-page foreign checks. Uses the
    zero-row source (`_ZERO_ROW`) deliberately: a block with rows would
    also flag the same occupant through a planned-page path (unreadable
    via `NotADirectoryError`), masking the pages-directory check on its
    own -- with zero rows, that loop is empty and cannot mask anything.

    Named mutation: delete the `if _pages_dir_is_foreign(pages_dir):
    foreign_blocking.append(...)` clause -- with zero rows, `_render_and_write`
    never even attempts `pages_dir.mkdir` (guarded by `if
    block.current.rows`), so the run falls straight through to a successful,
    empty write and reports `RENDERED` instead of `BLOCKED` -- the first
    assertion below reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_ZERO_ROW)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    occupant = tmp_path / _BLOCKS_DIR / "a"
    occupant.parent.mkdir(parents=True)
    occupant.write_text("a file where a directory belongs\n", encoding="utf-8")
    occupant_bytes = occupant.read_bytes()

    report = run_plan(tmp_path)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.BLOCKED
    assert outcome.foreign == ("blocks/a",)
    assert not (tmp_path / _BLOCKS_DIR / "a.md").exists()
    assert occupant.is_file()
    assert occupant.read_bytes() == occupant_bytes

    assert _snapshot(source_dir) == before


def test_symlinked_occupants_at_all_three_target_kinds_block_and_stay_symlinks(
    tmp_path: Path,
) -> None:
    """Req 7.8's "symlink -> foreign" rule, pinned at all three target
    shapes at once, each engineered so the underlying content/shape-based
    rule would otherwise classify it as NOT foreign -- isolating the
    `is_symlink()` checks themselves from the fallback that would
    otherwise confound them (a symlink to plain, non-generated text is
    already caught by the content check alone; that is NOT what this test
    pins).

    Named mutations:
    - delete `if path.is_symlink(): return True` from
      `_pages_dir_is_foreign` -- `blocks/a` (a symlink to a REAL directory
      outside the root) is then classified NOT foreign (`path.is_dir()` is
      True *through* the symlink), and `"blocks/a"` drops out of
      `outcome.foreign`.
    - delete `if path.is_symlink(): return True` from `_is_foreign_occupant`
      -- both `blocks/a.md` and `blocks/a/w1-mon.md` are symlinks to text
      that itself carries `GENERATED_PREFIX`, so without the symlink check
      `is_generated(text)` reads True *through* the symlink and both drop
      out of `outcome.foreign`.

    Either mutation shrinks `outcome.foreign` below the full three-path set
    asserted below, while `status == BLOCKED` alone would stay green (one
    of the three still catches it) -- the set-equality assertion, not the
    status alone, is what discriminates each."""
    data_root = tmp_path / "root"
    data_root.mkdir()
    source_dir = _plans_dir(data_root)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(data_root)
    before = _snapshot(source_dir)

    external = tmp_path / "external"
    external.mkdir()

    # 1) blocks/a.md -> a file OUTSIDE the root that carries the generated
    # marker -- without the symlink check, `is_generated` alone would call
    # this NOT foreign.
    generated_block = external / "generated-block.md"
    generated_block.write_text(f"{GENERATED_PREFIX} -->\nexternal\n", encoding="utf-8")
    generated_block_bytes = generated_block.read_bytes()
    block_page = data_root / _BLOCKS_DIR / "a.md"
    block_page.parent.mkdir(parents=True)
    block_page.symlink_to(generated_block)

    # 2) blocks/a -> a REAL directory outside the root -- without the
    # symlink check, `path.is_dir()` alone would call this NOT foreign.
    real_dir = external / "pages-target"
    real_dir.mkdir()
    pages_dir = data_root / _BLOCKS_DIR / "a"
    pages_dir.symlink_to(real_dir, target_is_directory=True)

    # 3) blocks/a/w1-mon.md -> (through the pages-dir symlink) a
    # generated-looking file -- the same "content alone says generated"
    # trap as (1), reached through a doubly-indirected path.
    generated_row = external / "generated-row.md"
    generated_row.write_text(
        f"{GENERATED_PREFIX} -->\nexternal row\n", encoding="utf-8"
    )
    generated_row_bytes = generated_row.read_bytes()
    (real_dir / "w1-mon.md").symlink_to(generated_row)

    report = run_plan(data_root)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.BLOCKED
    assert set(outcome.foreign) == {"blocks/a.md", "blocks/a", "blocks/a/w1-mon.md"}
    assert outcome.written == ()
    assert outcome.removed == ()

    # Nothing was replaced, retargeted, or dereferenced-and-rewritten.
    assert block_page.is_symlink()
    assert pages_dir.is_symlink()
    assert (data_root / _BLOCKS_DIR / "a" / "w1-mon.md").is_symlink()
    assert generated_block.read_bytes() == generated_block_bytes
    assert generated_row.read_bytes() == generated_row_bytes
    assert [p.name for p in real_dir.iterdir()] == ["w1-mon.md"]

    assert _snapshot(source_dir) == before


# ==============================================================================
# A stale generated planned page removed; a foreign markdown file kept and
# listed (Req 7.9). Named mutation: remove non-generated stale files too.
# ==============================================================================


def test_stale_generated_page_removed_foreign_page_kept_and_listed(
    tmp_path: Path,
) -> None:
    source_dir = _plans_dir(tmp_path)
    (source_dir / "blk.toml").write_bytes(_FULL)
    _write_settings(tmp_path)

    first = run_plan(tmp_path)
    outcome_1 = _one(first, "blk")
    assert outcome_1.status == BlockStatus.RENDERED
    pages_dir = tmp_path / _BLOCKS_DIR / "blk"
    assert pages_dir.is_dir()
    # Req 8.7's write ORDER, not merely "eventually written": on this
    # five-row block, every planned page precedes the block page in
    # `written`, and the block page is always last.
    assert len(outcome_1.written) == 6  # five planned pages + the block page
    assert outcome_1.written[-1] == "blocks/blk.md"
    assert all(path.startswith("blocks/blk/") for path in outcome_1.written[:-1])

    # A leftover generated page for a row that is no longer current --
    # written directly, standing in for a row an amendment removed.
    stale_generated = pages_dir / "old-row.md"
    stale_generated.write_text(
        f"{GENERATED_PREFIX} -->\nstale content\n", encoding="utf-8"
    )
    # A leftover file that carries no fitdocs marker at all.
    foreign_leftover = pages_dir / "manual.md"
    foreign_leftover.write_text("hand-written note\n", encoding="utf-8")
    foreign_bytes = foreign_leftover.read_bytes()

    before = _snapshot(source_dir)
    report = run_plan(tmp_path)

    outcome_2 = _one(report, "blk")
    assert outcome_2.removed == ("blocks/blk/old-row.md",)
    assert outcome_2.foreign == ("blocks/blk/manual.md",)
    assert not stale_generated.exists()
    assert foreign_leftover.exists()
    assert foreign_leftover.read_bytes() == foreign_bytes

    assert _snapshot(source_dir) == before


# ==============================================================================
# An unsourced page and directory reported and kept (Req 7.10); the
# declaration file never listed as unsourced on a second run. Named
# mutation: drop the `AGENTS.md` exclusion from the unsourced scan.
# ==============================================================================


def test_unsourced_page_and_directory_reported_and_kept(tmp_path: Path) -> None:
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)

    orphan_page = tmp_path / _BLOCKS_DIR / "orphan.md"
    orphan_page.parent.mkdir(parents=True)
    orphan_page.write_text("no matching source\n", encoding="utf-8")
    orphan_dir = tmp_path / _BLOCKS_DIR / "orphan-dir"
    orphan_dir.mkdir()
    (orphan_dir / "note.md").write_text("inside an orphaned dir\n", encoding="utf-8")

    before = _snapshot(source_dir)
    report = run_plan(tmp_path)

    assert sorted(report.unsourced) == ["blocks/orphan-dir", "blocks/orphan.md"]
    assert orphan_page.exists()
    assert orphan_dir.exists()

    assert _snapshot(source_dir) == before


def test_declaration_file_never_listed_as_unsourced_on_second_run(
    tmp_path: Path,
) -> None:
    """First run creates `blocks/AGENTS.md` (the ownership declaration,
    Req 8.10); a second run must not report it as unsourced.

    Named mutation: delete the `if child.name == DECLARATION_FILENAME:
    continue` line from `_unsourced` -- `blocks/AGENTS.md` then appears in
    `report.unsourced` on the second run, and the assertion below reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    run_plan(tmp_path)
    declaration_path = tmp_path / _BLOCKS_DIR / DECLARATION_FILENAME
    assert declaration_path.is_file()

    second = run_plan(tmp_path)

    assert declaration_path.name not in {Path(entry).name for entry in second.unsourced}
    assert "blocks/AGENTS.md" not in second.unsourced
    # Req 7.10 negative: a *sourced* block's own pages directory
    # (`blocks/a/`) must never appear in `unsourced` either -- distinct
    # from the AGENTS.md-exclusion pin above.
    assert second.unsourced == ()
    assert (tmp_path / _BLOCKS_DIR / "a").is_dir()

    assert _snapshot(source_dir) == before


# ==============================================================================
# A damaged notes region -> failed, untouched (Req 4.9).
# ==============================================================================


def test_damaged_notes_region_fails_and_leaves_the_page_untouched(
    tmp_path: Path,
) -> None:
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)

    run_plan(tmp_path)
    block_page = tmp_path / _BLOCKS_DIR / "a.md"
    original = block_page.read_text(encoding="utf-8")
    assert begin_marker("notes") in original
    assert end_marker("notes") in original
    # Damage the region: drop the end marker line, keeping the generated
    # marker line intact so the engine still treats this as "present and
    # generated" and attempts the merge.
    damaged = original.replace(end_marker("notes") + "\n", "")
    block_page.write_text(damaged, encoding="utf-8")
    damaged_bytes = block_page.read_bytes()

    before = _snapshot(source_dir)
    report = run_plan(tmp_path)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.FAILED
    assert len(outcome.failures) == 1
    failed_path, reason = outcome.failures[0]
    assert failed_path == "blocks/a.md"
    assert reason
    assert block_page.read_bytes() == damaged_bytes
    assert report.failed is True

    assert _snapshot(source_dir) == before


# ==============================================================================
# A notes body carried verbatim across a source change (Req 4.9).
# ==============================================================================


def test_notes_body_carried_verbatim_across_a_source_change(tmp_path: Path) -> None:
    source_dir = _plans_dir(tmp_path)
    source_path = source_dir / "a.toml"
    source_path.write_bytes(_MINIMAL)
    _write_settings(tmp_path)

    run_plan(tmp_path)
    block_page = tmp_path / _BLOCKS_DIR / "a.md"
    original = block_page.read_text(encoding="utf-8")
    assert NOTES_PLACEHOLDER in original
    custom_note = "This block is going great -- keep the tempo runs."
    edited = original.replace(NOTES_PLACEHOLDER, custom_note)
    assert edited != original
    block_page.write_text(edited, encoding="utf-8")

    # A genuine source change (a different goal), written as fixture setup
    # before the run whose bytes are hashed after it.
    changed_source = _MINIMAL.decode("utf-8").replace(
        "A minimal valid plan source.", "A minimal valid plan source, revised."
    )
    assert changed_source != _MINIMAL.decode("utf-8")
    source_path.write_text(changed_source, encoding="utf-8")
    before = _snapshot(source_dir)

    report = run_plan(tmp_path)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.RENDERED
    new_text = block_page.read_text(encoding="utf-8")
    assert custom_note in new_text
    assert NOTES_PLACEHOLDER not in new_text
    assert "revised" in new_text

    assert _snapshot(source_dir) == before


# ==============================================================================
# The absent-directory pair (Req 1.10).
# ==============================================================================


def test_default_absent_directory_notes_and_creates_nothing(tmp_path: Path) -> None:
    _write_settings(tmp_path)  # no [plans] table -> unconfigured, default name

    report = run_plan(tmp_path)

    assert report.note is not None
    assert "no plan source directory" in report.note
    assert report.blocks == ()
    assert not (tmp_path / _BLOCKS_DIR).exists()
    assert not (tmp_path / "plans").exists()


def test_configured_absent_directory_raises(tmp_path: Path) -> None:
    _write_settings(tmp_path, '[plans]\npath = "does-not-exist"\n')

    with pytest.raises(PlanSettingsError):
        run_plan(tmp_path)

    assert not (tmp_path / _BLOCKS_DIR).exists()


def test_empty_source_directory_notes_and_writes_nothing(tmp_path: Path) -> None:
    """Distinct from the *absent*-directory note above: the directory
    EXISTS but holds no `*.toml` entry at all -- a different message
    (`"no plan sources under ..."`, design.md's `PlanReport.note`
    docstring), and still a no-op (Req 8.9).

    Named mutation: in `run_plan`, change `note = None if entries else
    f"no plan sources under {source_report}"` to always `None` -- the
    first assertion below reds."""
    source_dir = _plans_dir(tmp_path)  # the default "plans" directory, but empty
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    report = run_plan(tmp_path)

    assert report.note is not None
    assert "no plan sources" in report.note
    assert report.blocks == ()
    assert report.failed is False
    assert not (tmp_path / _BLOCKS_DIR).exists()

    assert _snapshot(source_dir) == before


def test_configured_path_that_is_a_file_raises(tmp_path: Path) -> None:
    """ "Present but not a directory" (Req 1.10) applies to a *configured*
    path too, distinct from the absent-configured-path case above.

    Named mutation: delete the `if not source_dir.is_dir(): raise
    PlanSettingsError(...)` clause from `run_plan` -- the run would then
    attempt `(tmp_path / "plans").iterdir()` against a regular file,
    raising `NotADirectoryError` (an unhandled `OSError`, not
    `PlanSettingsError`), and `pytest.raises(PlanSettingsError)` below
    reds (a different, uncaught exception type escapes instead)."""
    (tmp_path / "plans").write_text("not a directory\n", encoding="utf-8")
    _write_settings(tmp_path, '[plans]\npath = "plans"\n')

    with pytest.raises(PlanSettingsError):
        run_plan(tmp_path)

    assert not (tmp_path / _BLOCKS_DIR).exists()


# ==============================================================================
# A symlinked source (invalid, one problem); no declaration created by an
# all-invalid run. Named mutation: refresh declarations on the all-invalid
# run.
# ==============================================================================


def test_symlinked_source_is_invalid_and_all_invalid_run_creates_no_declaration(
    tmp_path: Path,
) -> None:
    """Named mutation: change `if valid_blocks:` to an unconditional call to
    `ensure_declarations(data_root)` in `run_plan` -- `blocks/AGENTS.md`
    would then exist after this all-invalid run, and the last assertion
    below reds."""
    real_source = tmp_path / "elsewhere.toml"
    real_source.write_bytes(_MINIMAL)
    source_dir = _plans_dir(tmp_path)
    symlink = source_dir / "sym.toml"
    symlink.symlink_to(real_source)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    report = run_plan(tmp_path)

    outcome = _one(report, "sym")
    assert outcome.status == BlockStatus.INVALID
    assert len(outcome.problems) == 1
    assert not (tmp_path / _BLOCKS_DIR).exists()

    assert _snapshot(source_dir) == before


# ==============================================================================
# The resolver called exactly once per valid block, with the parsed Block;
# never for an invalid block.
# ==============================================================================


def test_resolver_called_once_per_valid_block_not_for_invalid(tmp_path: Path) -> None:
    source_dir = _plans_dir(tmp_path)
    source_path = source_dir / "a.toml"
    source_path.write_bytes(_MINIMAL)
    (source_dir / "b.toml").write_text("not = [valid", encoding="utf-8")
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    calls: list[Block] = []

    def _recording(block: Block) -> Resolution:
        calls.append(block)
        return unresolved()

    report = run_plan(tmp_path, resolve=_recording)

    assert _one(report, "a").status == BlockStatus.RENDERED
    assert _one(report, "b").status == BlockStatus.INVALID
    assert len(calls) == 1
    assert calls[0].id == "a"
    assert len(calls[0].current.rows) == 1  # non-vacuous: a real, parsed Block
    # The resolver receives the ACTUAL parsed block, not merely one sharing
    # an id -- full dataclass equality against an independent re-parse of
    # the same source (`load_block` never mutates or re-reads the file, so
    # this re-parse itself changes nothing on disk).
    assert calls[0] == load_block(source_path, block_id="a")

    assert _snapshot(source_dir) == before


def test_the_supplied_resolution_reaches_both_renderers(tmp_path: Path) -> None:
    """Seam item 3 (Cross-spec obligations, training-blocks <-> plan-
    resolution) and Req 6.1-6.2: the `Resolution` a caller's resolver
    returns must be the value passed to *both* `render_block_page` and
    `render_planned_page` -- not the default `unresolved()` -- and every
    slot the design names (row cell, planned-page section, a mesocycle's
    before/after-table lines, the block-level "## Resolution" lines) must
    carry it through, verbatim.

    Named mutations: in `_render_and_write`, replace the resolver's
    `resolution` with `unresolved()` in the call to `render_planned_page`
    -- the section-token assertion on the planned page reds; replace it
    with `unresolved()` in the call to `render_block_page` -- the four
    block-page token assertions red."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    sentinel = Resolution(
        rows={
            "w1-mon": RowResolution(cell="SENTINEL-CELL", section=("SENTINEL-SECTION",))
        },
        mesocycles={
            1: MesocycleResolution(
                before_table=("SENTINEL-BEFORE",), after_table=("SENTINEL-AFTER",)
            )
        },
        block_lines=("SENTINEL-BLOCK",),
    )

    report = run_plan(tmp_path, resolve=lambda block: sentinel)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.RENDERED
    block_text = (tmp_path / _BLOCKS_DIR / "a.md").read_text(encoding="utf-8")
    planned_text = (tmp_path / _BLOCKS_DIR / "a" / "w1-mon.md").read_text(
        encoding="utf-8"
    )
    assert "SENTINEL-CELL" in block_text
    assert "SENTINEL-BEFORE" in block_text
    assert "SENTINEL-AFTER" in block_text
    assert "SENTINEL-BLOCK" in block_text
    assert "SENTINEL-SECTION" in planned_text

    assert _snapshot(source_dir) == before


# ==============================================================================
# A read-only pages directory: failed, no partial file, the next block
# still rendered (Req 8.7).
# ==============================================================================


@pytest.fixture
def _restore_permissions() -> Iterator[list[Path]]:
    locked: list[Path] = []
    yield locked
    for path in locked:
        path.chmod(stat.S_IRWXU)


def test_read_only_pages_directory_fails_without_partial_file_next_block_renders(
    tmp_path: Path, _restore_permissions: list[Path]
) -> None:
    if hasattr(os, "getuid") and os.getuid() == 0:
        pytest.skip("chmod is ineffective when running as root")

    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_FULL)  # sorts before "b.toml"
    (source_dir / "b.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    pages_dir = tmp_path / _BLOCKS_DIR / "a"
    pages_dir.mkdir(parents=True)
    pages_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read + traverse, no write
    _restore_permissions.append(pages_dir)

    report = run_plan(tmp_path)

    outcome_a = _one(report, "a")
    assert outcome_a.status == BlockStatus.FAILED
    assert len(outcome_a.failures) == 1
    failed_path, reason = outcome_a.failures[0]
    assert failed_path.startswith("blocks/a/")
    assert reason
    assert not (tmp_path / _BLOCKS_DIR / "a.md").exists()
    assert list(pages_dir.iterdir()) == []  # no partial/temp file left behind

    outcome_b = _one(report, "b")
    assert outcome_b.status == BlockStatus.RENDERED
    assert (tmp_path / _BLOCKS_DIR / "b.md").exists()

    assert _snapshot(source_dir) == before


# ==============================================================================
# The torn-state pin: a write that fails on the second planned write must
# never let the block page be written. Named mutation: write the block page
# before the planned pages.
# ==============================================================================


def test_a_failure_on_the_second_planned_write_never_reaches_the_block_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: in `_render_and_write`, move the block-page write
    before the planned-page loop -- the mocked `_atomic_write` below would
    then see the block page as its FIRST call (always succeeding), and the
    "block page must not exist" assertion reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "blk.toml").write_bytes(_FULL)  # five current rows
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    real_atomic_write = engine_module._atomic_write
    call_count = {"n": 0}

    def _fake_atomic_write(path: Path, text: str) -> None:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated failure on the second planned write")
        real_atomic_write(path, text)

    monkeypatch.setattr(engine_module, "_atomic_write", _fake_atomic_write)

    report = run_plan(tmp_path)

    monkeypatch.setattr(engine_module, "_atomic_write", real_atomic_write)

    outcome = _one(report, "blk")
    assert outcome.status == BlockStatus.FAILED
    assert not (tmp_path / _BLOCKS_DIR / "blk.md").exists()
    pages_dir = tmp_path / _BLOCKS_DIR / "blk"
    written_planned = list(pages_dir.glob("*.md"))
    assert len(written_planned) == 1  # exactly the first, successful write
    assert len(outcome.written) == 1
    assert len(outcome.failures) == 1

    assert _snapshot(source_dir) == before


def test_atomic_write_leaves_no_partial_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_atomic_write`'s `except BaseException: tmp_path.unlink(missing_ok=True);
    raise` cleanup, pinned directly: `os.replace` fails AFTER
    `tempfile.mkstemp` has already created the temp file, so a passing
    assertion here actually exercises the cleanup line -- unlike the
    locked-directory scenario above, where `mkstemp` itself never
    succeeds and "no partial file" would hold trivially either way.

    Named mutation: delete `tmp_path.unlink(missing_ok=True)` from
    `_atomic_write`'s `except` clause -- the mocked failure below leaves a
    `.plans-*.tmp` file behind in the pages directory, and the last
    assertion reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    real_replace = os.replace

    def _failing_replace(src: object, dst: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _failing_replace)

    report = run_plan(tmp_path)

    monkeypatch.setattr(os, "replace", real_replace)

    outcome = _one(report, "a")
    assert outcome.status == BlockStatus.FAILED
    assert len(outcome.failures) == 1
    assert outcome.failures[0][0] == "blocks/a/w1-mon.md"
    pages_dir = tmp_path / _BLOCKS_DIR / "a"
    assert pages_dir.is_dir()
    assert list(pages_dir.iterdir()) == []  # the temp file was cleaned up
    assert not list(tmp_path.rglob(".plans-*"))

    assert _snapshot(source_dir) == before


# ==============================================================================
# Discovery: sorted by name, not filesystem order; no recursion into a
# subdirectory.
# ==============================================================================


def test_discovery_is_sorted_by_name_not_creation_order(tmp_path: Path) -> None:
    """`b.toml` is created before `a.toml`, so an unsorted `iterdir()`
    listing (on most filesystems) yields creation order -- `[b, a]`.

    Named mutation: delete `candidates.sort(key=lambda entry: entry.name)`
    from `_discover` -- the report's block order would then follow
    creation/filesystem order, and the assertion below reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "b.toml").write_bytes(_MINIMAL)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    report = run_plan(tmp_path)

    assert [outcome.block_id for outcome in report.blocks] == ["a", "b"]

    assert _snapshot(source_dir) == before


def test_discovery_never_recurses_into_a_subdirectory(tmp_path: Path) -> None:
    """Named mutation: change `_discover`'s `source_dir.iterdir()` to
    `source_dir.rglob(f"*{PLAN_SOURCE_SUFFIX}")` -- the nested source would
    then be discovered too, and `len(report.blocks) == 1` reds. Also
    pins the suffix filter directly: a `README.md` sitting beside the
    real source is never mistaken for one."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    (source_dir / "README.md").write_text("not a plan source\n", encoding="utf-8")
    nested = source_dir / "sub"
    nested.mkdir()
    (nested / "nested.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    report = run_plan(tmp_path)

    assert len(report.blocks) == 1
    assert report.blocks[0].block_id == "a"

    assert _snapshot(source_dir) == before


# ==============================================================================
# Report paths: absolute when the source directory lies outside the root.
# ==============================================================================


def test_report_paths_are_absolute_when_the_source_lies_outside_the_root(
    tmp_path: Path,
) -> None:
    """Named mutation: in `_report_path`, change the `except ValueError:
    return path.as_posix()` branch to `return path.name` -- the source
    directory's report path would collapse to a bare directory name, and
    the assertion below reds."""
    data_root = tmp_path / "root"
    data_root.mkdir()
    external_source = tmp_path / "external-plans"
    external_source.mkdir()
    (external_source / "a.toml").write_bytes(_MINIMAL)
    _write_settings(data_root, f'[plans]\npath = "{external_source}"\n')
    before = _snapshot(external_source)

    report = run_plan(data_root)

    assert report.source_dir == external_source.as_posix()
    outcome = _one(report, "a")
    assert outcome.source == (external_source / "a.toml").as_posix()

    assert _snapshot(external_source) == before


# ==============================================================================
# A failed block does not stop the next block from being reported.
# ==============================================================================


def test_a_failed_block_does_not_stop_the_next_block_from_being_reported(
    tmp_path: Path,
) -> None:
    """Named mutation: add a `break` right after a block's outcome is
    appended inside `run_plan`'s per-entry loop -- the second block's
    outcome would then never be appended, and `len(report.blocks) == 2`
    reds."""
    source_dir = _plans_dir(tmp_path)
    (source_dir / "a.toml").write_bytes(_MINIMAL)
    (source_dir / "b.toml").write_bytes(_MINIMAL)
    _write_settings(tmp_path)
    before = _snapshot(source_dir)

    # `resolve(block)` runs outside the render try/except, so a resolver
    # that raises would propagate straight out of `run_plan` rather than
    # producing a `failed` outcome; force a *renderer* failure instead, by
    # supplying a `Resolution` naming a row id the block does not have,
    # which `page.check_resolution` rejects with a `ValueError` the
    # renderer propagates -- the path a malformed resolver value hits.
    def _bad_resolution(block: Block) -> Resolution:
        if block.id == "a":
            return Resolution(
                rows={"no-such-row": RowResolution(cell="x", section=())},
                mesocycles={},
            )
        return unresolved()

    report = run_plan(tmp_path, resolve=_bad_resolution)

    assert len(report.blocks) == 2
    outcome_a = _one(report, "a")
    outcome_b = _one(report, "b")
    assert outcome_a.status == BlockStatus.FAILED
    assert len(outcome_a.failures) == 1
    assert outcome_a.failures[0][0] == "render"
    assert outcome_a.failures[0][1]  # a non-empty reason, not merely self-equal
    assert outcome_b.status == BlockStatus.RENDERED

    assert _snapshot(source_dir) == before
