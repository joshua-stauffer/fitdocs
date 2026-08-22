"""Whole-system inbox validation (task 5.2, inbox Req 1.4, 1.6, 1.7, 2.2,
2.4, 4.6, 5.3, 5.6, 6.1, 6.7, 7.2, 7.3, 7.4, 7.5, 8.5).

The per-task suites (``tests/test_drain.py``, ``tests/test_cli_sync_inbox.py``,
``tests/test_inbox.py``, ``tests/test_quarantine.py``,
``tests/test_cli_drain_report.py``) already lock every channel's behavior in
isolation, including report-level idempotency ("second drain writes nothing
*new*" measured by report counts). This module closes the whole-tree,
byte-and-mtime-level gap those suites do not close: whether a re-run
genuinely rewrites nothing on disk anywhere under the data root -- not merely
whether the report says so -- and whether a configuration refusal leaves the
data root in the exact state it found it, everywhere, not just in the three
paths the CLI suite's narrower ``_nothing_written`` helper inspects.

Every scenario here drives the real, unmocked ``fitdocs sync`` CLI command
through :class:`typer.testing.CliRunner` (mirrors
``tests/test_cli_sync_inbox.py``) and stays offline via the same injected
tile fetch that suite uses; every settings file that exercises a real drain
sets ``settle_seconds = 0`` (inbox Req 4.4's documented, supported
no-wait value), so the stability check's one-sleep-per-drain never costs
wall-clock time, matching the suite hygiene note recorded for task 4.2.
"""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from tests.fixtures import builder

runner = CliRunner()

_ZERO_SETTLE_TOML = "[inbox]\nsettle_seconds = 0\n"

#: Snapshot markers, mirroring ``tests/test_confinement.py``'s ``_snapshot``:
#: a directory has no content to hash, and an absent path has no state at
#: all, so both get their own sentinel and the diff stays a plain string
#: comparison.
_DIRECTORY = "<directory>"


def _put(directory: Path, name: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


#: Marker for a file this process cannot read (permission-denied scenarios):
#: falls back to mtime-only so an unreadable file's *timestamp* is still
#: compared, even though its content cannot be.
_UNREADABLE = "<unreadable>"


def _snapshot(root: Path) -> dict[str, str]:
    """State of every path under ``root``: content hash *and* modification
    time, or the directory marker -- so a rewrite with identical bytes still
    shows up as a change (mirrors ``tests/test_confinement.py``'s
    ``_snapshot``, duplicated locally rather than imported since that
    module's snapshot is scoped to a sandbox holding a *source* directory
    too, which this module's scenarios do not need). A file this process
    cannot read (the unreadable-settings-file scenario deliberately
    ``chmod``s one to 0) falls back to an mtime-only marker rather than
    raising, since the point of the comparison is to prove the refusal never
    touched it -- not to read bytes it was never entitled to read.
    """
    assert root.exists(), f"snapshot root is missing: {root}"
    state: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_dir():
            state[key] = _DIRECTORY
        else:
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                state[key] = f"{digest}:{path.stat().st_mtime_ns}"
            except PermissionError:
                state[key] = f"{_UNREADABLE}:{path.stat().st_mtime_ns}"
    return state


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep this suite network-free, mirroring ``tests/test_cli_sync_inbox.py``."""
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


# =============================================================================
# Byte-identical re-run under leave-in-place (Req 7.4)
# =============================================================================


def test_two_leave_in_place_drains_are_byte_identical_and_the_second_writes_nothing(
    tmp_path: Path,
) -> None:
    """Two consecutive leave-in-place drains over an unchanged inbox produce
    identical documents, assets, archive, and quarantine record on disk, and
    the second drain writes nothing (inbox Req 7.4).

    Stages one processable file (which ends up written, archived, and
    documented) *and* one undecodable file (which ends up quarantined, so
    the comparison also covers the quarantine record) into the inbox, drains
    twice, and diffs a whole-data-root snapshot -- content hash *and* mtime
    per file -- taken after each run. Snapshot equality is a stronger claim
    than the report-level "written == ()" the per-task suites already pin:
    it also catches a rewrite that reproduces identical bytes, which a
    count-only or hash-only check would miss.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    inbox = data_root / "inbox"
    _put(inbox, "good.fit", builder.run_fit_bytes())
    _put(inbox, "bad.fit", builder.non_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    # The fresh source-level failure (bad.fit) fails this run; the point of
    # this test is the state it leaves behind, not this exit code.
    assert first.exit_code == 1
    assert (data_root / "fit-archive").exists()
    assert (data_root / ".fitdocs" / "quarantine.toml").is_file()
    snapshot_after_first = _snapshot(data_root)

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    snapshot_after_second = _snapshot(data_root)

    # bad.fit is now a known quarantine entry rather than a fresh failure, so
    # the second run succeeds outright.
    assert second.exit_code == 0
    assert snapshot_after_second == snapshot_after_first


def test_move_drain_idempotency_inbox_empties_and_second_drain_writes_nothing(
    tmp_path: Path,
) -> None:
    """After a fully successful move drain, the inbox has no candidates left,
    and a second drain over it writes nothing anywhere in the data root
    (inbox Req 7.5).

    ``tests/test_drain.py``'s
    ``test_second_drain_under_move_finds_an_empty_inbox_and_does_nothing``
    already pins this at the engine-report level; this closes the
    whole-tree, filesystem-state gap the way the leave-in-place test above
    does, and drives it through the real CLI rather than the bare engine
    entry point.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        '[inbox]\ndisposition = "move"\nprocessed_dir = "processed"\n'
        "settle_seconds = 0\n",
        encoding="utf-8",
    )
    inbox = data_root / "inbox"
    _put(inbox, "good.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert first.exit_code == 0
    assert list(inbox.glob("*.fit")) == []
    assert list((data_root / "processed").glob("*.fit"))
    snapshot_after_first = _snapshot(data_root)

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    snapshot_after_second = _snapshot(data_root)

    assert second.exit_code == 0
    assert list(inbox.glob("*.fit")) == []
    assert snapshot_after_second == snapshot_after_first


# =============================================================================
# Explicit-source regression: no inbox configuration present or consulted
# (Req 2.2, 7.3)
# =============================================================================


def test_explicit_source_sync_with_no_settings_file_at_all_creates_no_inbox_state(
    tmp_path: Path,
) -> None:
    """With no ``fitdocs.toml`` present at all -- not merely one lacking an
    ``[inbox]`` table -- an explicit-source sync behaves exactly as it did
    before this feature: it writes documents and the archive and never
    creates an inbox directory, a processed-files directory, or the
    tool-state directory the quarantine record would live under.

    ``tests/test_cli_sync_inbox.py``'s
    ``test_explicit_source_sync_never_reads_inbox_settings`` already proves
    the inbox-settings reader itself is never *called*; this proves the
    absence has no observable footprint on disk either -- the two are
    distinct claims (a reader could in principle be called and still
    default harmlessly).
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    assert not (data_root / "fitdocs.toml").exists()

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Written" in result.output
    assert (data_root / "fit-archive").exists()
    assert not (data_root / "inbox").exists()
    assert not (data_root / "processed").exists()
    assert not (data_root / ".fitdocs").exists()


# =============================================================================
# Configuration refusals leave the data root untouched (Req 1.4, 1.6, 1.7,
# 5.6, 6.7)
# =============================================================================
#
# "Untouched" here means literally: a whole-data-root snapshot (content hash
# and mtime per file, existence per directory) taken immediately before the
# invocation is identical to one taken immediately after. This is a stronger
# and more precise claim than ``tests/test_cli_sync_inbox.py``'s
# ``_nothing_written`` helper, which inspects only three known paths
# (``workouts/``, ``fit-archive/``, the quarantine record) -- a stray write
# anywhere else in the data root would pass that helper silently but fails
# here. It is also a *narrower* claim than "the data root is byte-identical
# after any successful drain": a successful empty-inbox drain legitimately
# creates ``workouts/AGENTS.md`` (the ownership declaration, refreshed on
# every run per Req 7.6) and the inbox directory itself (Req 1.5).
#
# Every scenario below is a *refusal* -- the CLI's pre-flight raises and
# routes to the configuration-error exit path before ``fitdocs.sync.drain``
# is ever called, so the declaration refresh (which lives inside ``drain``)
# never runs. Every refusal leaves the whole data root byte-for-byte
# unchanged, because the documented pre-flight order (settings parse ->
# ``[inbox]`` projection -> validate both the inbox and processed-files
# paths (no writes) -> ``load_quarantine`` -> tile settings -> create
# whichever validated path is missing) runs every check that can fail
# *before* either directory is created -- including the quarantine read, so
# a malformed quarantine record refuses before the default inbox is ever
# created (Req 7.2).


def test_invalid_toml_settings_file_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text("not [ valid toml", encoding="utf-8")
    before = _snapshot(data_root)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert _snapshot(data_root) == before


def test_unreadable_settings_file_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    data_root = tmp_path / "data"
    data_root.mkdir()
    settings = data_root / "fitdocs.toml"
    settings.write_text("[inbox]\npath = 'inbox'\n", encoding="utf-8")
    settings.chmod(0o000)
    try:
        before = _snapshot(data_root)
        result = runner.invoke(app, ["sync", "--out", str(data_root)])
        after = _snapshot(data_root)
    finally:
        settings.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert result.exit_code == 2
    assert after == before


def test_malformed_inbox_settings_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 'not a number'\n", encoding="utf-8"
    )
    before = _snapshot(data_root)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert _snapshot(data_root) == before


def test_missing_outside_root_inbox_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    outside_missing = tmp_path / "does-not-exist-inbox"
    (data_root / "fitdocs.toml").write_text(
        f'[inbox]\npath = "{outside_missing.as_posix()}"\n', encoding="utf-8"
    )
    before = _snapshot(data_root)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert not outside_missing.exists()
    assert _snapshot(data_root) == before


def test_missing_outside_root_destination_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    """The move disposition's processed-files destination, not the inbox
    itself, is the one lying outside the data root and missing (inbox Req
    1.6, 6.7) -- unlike the inbox case above, this path is not exercised
    anywhere at the CLI level today (only against
    :func:`fitdocs.inbox.prepare_inbox` directly, in ``tests/test_inbox.py``).
    Both the inbox and the destination are validated before either is
    created (task 1.3's two-phase guarantee), so even the *inbox* directory
    -- which is inside the data root and would otherwise be created -- must
    not appear.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    outside_missing = tmp_path / "does-not-exist-processed"
    (data_root / "fitdocs.toml").write_text(
        f'[inbox]\ndisposition = "move"\n'
        f'processed_dir = "{outside_missing.as_posix()}"\n'
        "settle_seconds = 0\n",
        encoding="utf-8",
    )
    before = _snapshot(data_root)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert not outside_missing.exists()
    assert not (data_root / "inbox").exists()
    assert _snapshot(data_root) == before


def test_malformed_quarantine_record_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    """A malformed quarantine record is refused with the configuration exit
    code and never silently discarded or rebuilt (Req 5.6), and the refusal
    writes nothing at all (Req 7.2): the pre-flight validates the inbox path
    and reads the quarantine record *before* creating the default,
    absent, inside-the-data-root inbox, so that inbox never appears.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    state_dir = data_root / ".fitdocs"
    state_dir.mkdir()
    quarantine_file = state_dir / "quarantine.toml"
    quarantine_file.write_text("not [ valid toml", encoding="utf-8")
    before = _snapshot(data_root)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert _snapshot(data_root) == before
    assert not (data_root / "inbox").exists()


def test_malformed_quarantine_record_leaves_the_root_untouched_under_move(
    tmp_path: Path,
) -> None:
    """The move-disposition variant of the scenario above: with a default,
    absent, inside-the-data-root inbox *and* processed-files destination
    both configured, a malformed quarantine record still refuses before
    either directory is created (Req 5.6, 6.7, 7.2).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        '[inbox]\ndisposition = "move"\nprocessed_dir = "processed"\n'
        "settle_seconds = 0\n",
        encoding="utf-8",
    )
    state_dir = data_root / ".fitdocs"
    state_dir.mkdir()
    quarantine_file = state_dir / "quarantine.toml"
    quarantine_file.write_text("not [ valid toml", encoding="utf-8")
    before = _snapshot(data_root)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert _snapshot(data_root) == before
    assert not (data_root / "inbox").exists()
    assert not (data_root / "processed").exists()


def test_retry_quarantined_with_explicit_source_leaves_the_whole_data_root_untouched(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    before = _snapshot(data_root)

    result = runner.invoke(
        app, ["sync", str(source), "--out", str(data_root), "--retry-quarantined"]
    )

    assert result.exit_code == 2
    assert _snapshot(data_root) == before
