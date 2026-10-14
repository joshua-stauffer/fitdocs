"""Counts and per-channel detail in the CLI drain report."""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import pytest

from fitdocs.cli import _report, _report_drain
from fitdocs.inbox import InboxNote
from fitdocs.sync import DocWarning, DrainReport, FileFailure, SyncReport

# The last commit that touched ``src/fitdocs/cli.py`` *before* this task's
# edit -- an immutable historical reference, not a moving pointer at HEAD.
# Deliberately pinned rather than resolved dynamically: it must keep naming
# the pre-task state of ``_report`` even after later commits touch cli.py.
#
# The baseline source itself is vendored at
# ``tests/fixtures/report_baseline_faa6d09.py`` rather than fetched from git
# history at test time: a depth-limited clone (e.g. CI's default
# ``actions/checkout`` at ``fetch-depth: 1``) does not carry this object, and
# a test that shells out to ``git show`` for it would fail with a
# missing-object error instead of reporting the drift it exists to catch.
#
# ``faa6d09`` is a pre-replacement commit identifier (encumbered-content-purge,
# ``docs/reference/history-rewrites.md`` Sec 3, 2026-08-22): it is retained
# here as historical fact, permanently unresolvable in this repository, not a
# live pointer. The retired plan would have had this note point to a
# forthcoming commit map instead; that pointer is cancelled -- no map exists
# or ever will, by construction.
_PRE_TASK_CLI_COMMIT = "faa6d09"
_BASELINE_FIXTURE = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "report_baseline_faa6d09.py"
)


def _empty_sync_report() -> SyncReport:
    return SyncReport(written=(), skipped=(), failures=(), warnings=())


def _drain_report(
    *,
    inbox: str = "inbox",
    sync: SyncReport | None = None,
    deferred: tuple[InboxNote, ...] = (),
    quarantined: tuple[InboxNote, ...] = (),
    moved: tuple[str, ...] = (),
    move_failures: tuple[InboxNote, ...] = (),
    unrecognized: tuple[InboxNote, ...] = (),
    wellness_archived: tuple[InboxNote, ...] = (),
    wellness_skipped: tuple[InboxNote, ...] = (),
    wellness_failures: tuple[InboxNote, ...] = (),
) -> DrainReport:
    return DrainReport(
        inbox=inbox,
        sync=sync if sync is not None else _empty_sync_report(),
        deferred=deferred,
        quarantined=quarantined,
        moved=moved,
        move_failures=move_failures,
        unrecognized=unrecognized,
        wellness_archived=wellness_archived,
        wellness_skipped=wellness_skipped,
        wellness_failures=wellness_failures,
    )


def _table_region(output: str) -> str:
    """Return only the box-drawn table's lines (from the top rule ``┏`` to
    the bottom rule ``└``), excluding everything printed before or after it
    -- in particular excluding the ``Label:`` detail headings, which share
    text with the row labels and would otherwise make a substring search
    unable to tell a row from a heading."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("┏"))
    end = next(i for i, line in enumerate(lines) if line.lstrip().startswith("└"))
    return "\n".join(lines[start : end + 1])


def _row_count(table_region: str, label: str) -> int:
    """Find the single table row whose (trimmed) label column is exactly
    ``label`` and return its count column as an int. Fails if the row is
    missing, or if the label appears zero or more-than-once as a distinct
    row."""
    matches = re.findall(rf"│\s*{re.escape(label)}\s*│\s*(\d+)\s*│", table_region)
    assert len(matches) == 1, (
        f"expected exactly one {label!r} row in the table, found {len(matches)}:\n"
        f"{table_region}"
    )
    return int(matches[0])


def _body_row_count(table_region: str) -> int:
    """Count data rows in the table region (lines of the form
    ``│ <label> │ <digits> │``), excluding the header row and the box
    rules."""
    return len(re.findall(r"│[^│\n]*│\s*\d+\s*│", table_region))


def _block(output: str, heading: str) -> str:
    """Return the text printed under ``heading:`` up to (not including) the
    next ``Word:`` heading or end of output, so detail assertions can be
    bound to the heading that introduced them rather than matching anywhere
    in the whole output."""
    after = output.split(f"{heading}:\n", maxsplit=1)[1]
    next_heading = re.search(r"\n[A-Za-z ]+:\n", "\n" + after)
    return after[: next_heading.start()] if next_heading else after


_ALL_LABELS = (
    "Written",
    "Skipped",
    "Failed",
    "Warnings",
    "Deferred",
    "Quarantined",
    "Moved",
    "Move failures",
    "Unrecognized",
    "Wellness archived",
    "Wellness skipped",
    "Wellness failed",
)


def test_names_the_inbox_path_being_drained(capsys: pytest.CaptureFixture[str]) -> None:
    report = _drain_report(inbox="/home/josh/fitdocs-inbox")

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    assert "/home/josh/fitdocs-inbox" in output


def test_each_of_the_twelve_channels_is_exactly_one_table_row_with_its_own_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sync = SyncReport(
        written=tuple(f"workouts/w{i}.md" for i in range(5)),
        skipped=tuple(f"skip{i}.fit" for i in range(6)),
        failures=tuple(FileFailure(source=f"f{i}.fit", reason="bad") for i in range(7)),
        warnings=tuple(DocWarning(doc=f"w{i}.md", detail="x") for i in range(8)),
    )
    report = _drain_report(
        sync=sync,
        unrecognized=tuple(InboxNote(f"u{i}.json", "u") for i in range(9)),
        wellness_archived=tuple(InboxNote(f"a{i}.json", "a") for i in range(10)),
        wellness_skipped=tuple(InboxNote(f"s{i}.json", "s") for i in range(11)),
        wellness_failures=tuple(InboxNote(f"f{i}.json", "f") for i in range(12)),
        deferred=tuple(InboxNote(subject=f"d{i}.fit", detail="x") for i in range(1)),
        quarantined=tuple(InboxNote(subject=f"q{i}.fit", detail="x") for i in range(2)),
        moved=tuple(f"processed/m{i}.fit" for i in range(3)),
        move_failures=tuple(
            InboxNote(subject=f"mf{i}.fit", detail="x") for i in range(4)
        ),
    )

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    table = _table_region(output)
    assert _body_row_count(table) == 12
    assert _row_count(table, "Written") == 5
    assert _row_count(table, "Skipped") == 6
    assert _row_count(table, "Failed") == 7
    assert _row_count(table, "Warnings") == 8
    assert _row_count(table, "Deferred") == 1
    assert _row_count(table, "Quarantined") == 2
    assert _row_count(table, "Moved") == 3
    assert _row_count(table, "Move failures") == 4
    assert _row_count(table, "Unrecognized") == 9
    assert _row_count(table, "Wellness archived") == 10
    assert _row_count(table, "Wellness skipped") == 11
    assert _row_count(table, "Wellness failed") == 12


def test_move_failures_count_is_not_folded_into_the_failed_row(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed move never fails the run and is a distinct channel from a
    per-file processing failure, so the two counts must not be combined in
    either row (design: Move failures "not folded into Failed")."""
    sync = SyncReport(
        written=(),
        skipped=(),
        failures=(FileFailure(source="broken.fit", reason="CRC mismatch"),),
        warnings=(),
    )
    report = _drain_report(
        sync=sync,
        move_failures=(
            InboxNote(subject="e.fit", detail="permission denied"),
            InboxNote(subject="f.fit", detail="disk full"),
        ),
    )

    _report_drain(report, command="sync")

    table = _table_region(capsys.readouterr().out)
    assert _row_count(table, "Failed") == 1
    assert _row_count(table, "Move failures") == 2


def test_move_failures_count_is_not_folded_into_the_moved_row(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file whose move failed never moved, so it must not inflate the
    Moved count (design: Move failures "not folded into ... Moved")."""
    report = _drain_report(
        moved=("processed/x.fit",),
        move_failures=(
            InboxNote(subject="e.fit", detail="permission denied"),
            InboxNote(subject="f.fit", detail="disk full"),
        ),
    )

    _report_drain(report, command="sync")

    table = _table_region(capsys.readouterr().out)
    assert _row_count(table, "Moved") == 1
    assert _row_count(table, "Move failures") == 2


def test_all_twelve_rows_render_with_zero_count_and_no_detail_headings_when_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _drain_report()

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    table = _table_region(output)
    assert _body_row_count(table) == 12
    for label in _ALL_LABELS:
        assert _row_count(table, label) == 0
    for heading in (
        "Written:",
        "Failed:",
        "Warnings:",
        "Deferred:",
        "Quarantined:",
        "Move failures:",
        "Moved:",
        "Unrecognized:",
        "Wellness archived:",
        "Wellness skipped:",
        "Wellness failed:",
    ):
        assert heading not in output


def test_deferred_quarantined_and_move_failure_detail_are_bound_to_their_own_heading(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each note appears under its *own* heading and no other's -- deferred
    means retried automatically next drain (Req 4.2), quarantined means
    known-bad (Req 5.2), and a note printed under the wrong heading would
    misinform the user about which is which."""
    report = _drain_report(
        deferred=(InboxNote(subject="deferred.fit", detail="size still changing"),),
        quarantined=(InboxNote(subject="quarantined.fit", detail="CRC mismatch"),),
        move_failures=(
            InboxNote(subject="move-failed.fit", detail="destination is read-only"),
        ),
    )

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    deferred_block = _block(output, "Deferred")
    quarantined_block = _block(output, "Quarantined")
    move_failures_block = _block(output, "Move failures")

    assert "deferred.fit" in deferred_block
    assert "size still changing" in deferred_block
    assert "deferred.fit" not in quarantined_block
    assert "deferred.fit" not in move_failures_block

    assert "quarantined.fit" in quarantined_block
    assert "CRC mismatch" in quarantined_block
    assert "quarantined.fit" not in deferred_block
    assert "quarantined.fit" not in move_failures_block

    assert "move-failed.fit" in move_failures_block
    assert "destination is read-only" in move_failures_block
    assert "move-failed.fit" not in deferred_block
    assert "move-failed.fit" not in quarantined_block


def test_moved_detail_lists_each_destination(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _drain_report(moved=("processed/2026-07-12-run.fit",))

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    assert "processed/2026-07-12-run.fit" in _block(output, "Moved")


def test_existing_written_failed_and_warning_detail_still_render(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sync = SyncReport(
        written=("workouts/2026-07-12-run.md",),
        skipped=(),
        failures=(FileFailure(source="bad.fit", reason="CRC mismatch"),),
        warnings=(),
    )
    report = _drain_report(sync=sync)

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    assert "workouts/2026-07-12-run.md" in _block(output, "Written")
    failed_block = _block(output, "Failed")
    assert "bad.fit" in failed_block
    assert "CRC mismatch" in failed_block


def test_bracketed_reason_and_path_render_literally_not_as_markup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _drain_report(
        deferred=(
            InboxNote(subject="[weird] name.fit", detail="reason with [brackets]"),
        ),
    )

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    assert "[weird] name.fit" in output
    assert "reason with [brackets]" in output


def test_a_very_long_path_and_reason_are_not_truncated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    long_name = "a" * 300 + ".fit"
    long_reason = "b" * 300
    report = _drain_report(
        quarantined=(InboxNote(subject=long_name, detail=long_reason),),
    )

    _report_drain(report, command="sync")

    output = capsys.readouterr().out
    assert long_name in output
    assert long_reason in output


def test_report_function_is_left_byte_untouched() -> None:
    """AST comparison of ``fitdocs.cli._report`` against its pre-task baseline
    (vendored from commit ``faa6d09``, the last commit that touched
    ``cli.py`` before this task) proves the explicit-source presentation
    function was not modified while adding ``_report_drain`` (Req 7.3)."""
    assert _BASELINE_FIXTURE.is_file(), (
        f"baseline fixture missing: {_BASELINE_FIXTURE} -- see "
        f"_PRE_TASK_CLI_COMMIT ({_PRE_TASK_CLI_COMMIT}) for provenance"
    )
    baseline_source = _BASELINE_FIXTURE.read_text()
    baseline_module = ast.parse(baseline_source)
    baseline_func = next(
        (
            node
            for node in baseline_module.body
            if isinstance(node, ast.FunctionDef) and node.name == "_report"
        ),
        None,
    )
    assert baseline_func is not None, (
        f"no `_report` FunctionDef found in {_BASELINE_FIXTURE} -- fixture is "
        "empty, corrupt, or was edited to remove the baseline"
    )
    baseline_tree = ast.dump(baseline_func)

    actual_source = inspect.getsource(_report)
    actual_tree = ast.dump(ast.parse(actual_source).body[0])
    assert actual_tree == baseline_tree
