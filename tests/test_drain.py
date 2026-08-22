"""Tests for the drain entry point and its report composition (tasks 3.1,
3.2, 3.3, design: DrainOrchestration, inbox Req 2.1, 2.3, 2.4, 3.5, 4.2, 4.6,
5.1-5.5, 5.7, 6.2, 6.4, 6.5, 7.1, 7.4, 7.5, 7.6).

This module locks three things about :func:`fitdocs.sync.drain`. First, the
skeleton task 3.1 built: select candidates, settle them, read each stable
candidate once (a read failure defers, never fails or quarantines), and hand
every admitted candidate to the same isolated per-file call
:func:`fitdocs.sync.sync` uses, with the candidate's inbox-relative path as
its report label. Second, task 3.2's quarantine partitioning, recording, and
retry: a stable candidate whose content hash is already in the quarantine
record is reported quietly from :attr:`~fitdocs.sync.DrainReport.quarantined`
instead of being processed; a fresh source-level failure (the ``.fit`` bytes
cannot be decoded or parsed) is recorded; a fresh document-level failure (a
damaged preserved region) is reported as a failure and left unrecorded; the
retry option re-attempts recorded files, clearing an entry on success and
updating it on a renewed failure; and the record is persisted once, at the
end, only when it changed. Third, task 3.3's disposition: under the default
leave-in-place policy nothing in the inbox is ever touched; under the move
policy, a candidate is relocated out of the inbox to ``processed_dir`` iff
its content hash is present in ``fit-archive/`` once its processing has
finished -- never on the strength of the ``skipped`` label -- so a
document-format-version skip that deliberately archives nothing stays in the
inbox and is retried by the next drain; failed, deferred, and quarantined
candidates never reach that gate at all; and a move that itself fails is
reported in its own ``move_failures`` channel without changing the run's
success.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest
import yaml

from fitdocs.contract import DOC_VERSION
from fitdocs.declaration import DECLARATION_FILENAME, declaration_path
from fitdocs.docmerge import begin_marker
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS, Disposition, InboxSettings
from fitdocs.layout import (
    ARCHIVE_DIR,
    WORKOUTS_DIR,
    archive_path,
    doc_path,
    quarantine_path,
)
from fitdocs.quarantine import (
    QuarantineEntry,
    QuarantineRecord,
    load_quarantine,
    save_quarantine,
)
from fitdocs.sync import (
    DrainReport,
    FileFailure,
    SyncReport,
    drain,
    is_source_level,
    sync,
)
from tests.fixtures import builder

_TZ = timezone(timedelta(hours=-6))
_EMPTY_QUARANTINE = QuarantineRecord(entries=())
# The canonical session UUID the re-export fixture records (mirrors
# tests/test_sync.py's ``_REEXPORT_UUID``): matching an existing document by
# uuid is what lets a damaged preserved region raise a document-level
# RegionError instead of writing a fresh document.
_REEXPORT_UUID = "64656667-6869-6a6b-6c6d-6e6f70717273"
_REEXPORT_STEM = "2021-09-07-run-1946"


class _RecordingSleep:
    """A sleep stub that records every call instead of blocking wall-clock
    time (mirrors ``tests/test_inbox.py``'s stub for the same injected
    ``sleep`` callable ``settle`` uses)."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _Tiles:
    """Minimal offline tile source: serves deterministic bytes for any ref,
    keeping every test here fully offline (mirrors ``tests/test_sync.py``'s
    ``_ServingTiles``)."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES = _Tiles()


def _put(directory: Path, name: str, data: bytes) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _drain(
    inbox: Path,
    data_root: Path,
    *,
    settings: InboxSettings = DEFAULT_INBOX_SETTINGS,
    processed_dir: Path | None = None,
    force: bool = False,
    quarantine: QuarantineRecord = _EMPTY_QUARANTINE,
    retry_quarantined: bool = False,
) -> DrainReport:
    return drain(
        inbox,
        data_root,
        settings=settings,
        processed_dir=processed_dir,
        quarantine=quarantine,
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        force=force,
        retry_quarantined=retry_quarantined,
        sleep=_RecordingSleep(),
    )


_MOVE_SETTINGS = dataclasses.replace(
    DEFAULT_INBOX_SETTINGS, disposition=Disposition.MOVE
)
"""``[inbox]`` settings with the move disposition active; ``processed_dir``
here is the *config-string* field (unused by :func:`~fitdocs.sync.drain`
directly -- it consults its own resolved ``processed_dir: Path`` parameter
instead, mirroring the CLI's own settings-to-call layering)."""


def _frontmatter(doc: Path) -> dict[str, object]:
    """Parse a written document's leading YAML frontmatter block (mirrors
    ``tests/test_sync.py``'s helper of the same name)."""
    block = doc.read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    return parsed


def _set_doc_version_line(text: str, replacement: str) -> str:
    """Replace the ``doc_version: N`` frontmatter line with an arbitrary line
    (mirrors ``tests/test_sync.py``'s helper of the same name). An empty
    ``replacement`` removes the line entirely, simulating a document with no
    recorded version."""
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        if line.lstrip().startswith("doc_version:"):
            if replacement:
                out.append(replacement + "\n")
            continue
        out.append(line)
    return "".join(out)


# --- empty inbox --------------------------------------------------------


def test_empty_inbox_drains_successfully_with_nothing_reported(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()

    report = _drain(inbox, data_root)

    assert report.sync.written == ()
    assert report.sync.skipped == ()
    assert report.sync.failures == ()
    assert report.deferred == ()
    assert report.quarantined == ()
    assert report.moved == ()
    assert report.move_failures == ()


# --- ignored-only inbox --------------------------------------------------


def test_ignored_only_inbox_reports_nothing_in_any_channel(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    # A hidden AppleDouble companion, excluded by select_candidates' dot-
    # component rule before settle ever sees it (Req 3.2). ``partial.fit.part``
    # is included too, but it is not independent coverage of the pattern
    # rules here: a ``.fit``-suffixed candidate can never end in ``.part``, so
    # it is already excluded by the extension predicate alone.
    _put(inbox, "._run.fit", builder.run_fit_bytes())
    _put(inbox, "partial.fit.part", builder.run_fit_bytes())

    report = _drain(inbox, data_root)

    assert report.sync.written == ()
    assert report.sync.skipped == ()
    assert report.sync.failures == ()
    assert report.deferred == ()
    assert report.quarantined == ()


# --- mixed drain classifies exactly as an explicit-source sync would ----


def test_mixed_drain_classifies_files_exactly_as_an_explicit_source_sync_would(
    tmp_path: Path,
) -> None:
    """The headline differential test: stage identical bytes into an inbox and
    into a plain source directory, drain one and ``sync`` the other, and
    assert the written/skipped/failures classification (by *content*, since
    the report labels differ between an inbox-relative path and a bare
    filename) is identical (inbox Req 2.1)."""
    good = builder.run_fit_bytes()
    bad = builder.non_fit_bytes()

    inbox = tmp_path / "inbox"
    data_root_drain = tmp_path / "data_drain"
    data_root_drain.mkdir()
    _put(inbox, "good.fit", good)
    _put(inbox, "bad.fit", bad)

    source = tmp_path / "src"
    data_root_sync = tmp_path / "data_sync"
    data_root_sync.mkdir()
    _put(source, "good.fit", good)
    _put(source, "bad.fit", bad)

    drain_report = _drain(inbox, data_root_drain)
    sync_report = sync(source, data_root_sync, athlete=None, tz=_TZ, tiles=_TILES)

    # ``written`` entries are data-root-relative document paths, identical
    # between the two runs since both source directories hold identical
    # single-level filenames -- exact equality, not just matching lengths.
    assert drain_report.sync.written == sync_report.written
    assert len(drain_report.sync.written) == 1
    assert drain_report.sync.skipped == sync_report.skipped == ()
    assert len(drain_report.sync.failures) == len(sync_report.failures) == 1
    # Same failing file, same reason (the pipeline is untouched, only the
    # per-run source_label convention differs -- proven separately below).
    assert drain_report.sync.failures[0].reason == sync_report.failures[0].reason


def test_source_label_is_inbox_relative_not_absolute(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(inbox, "nested/good.fit", builder.run_fit_bytes())
    _put(inbox, "nested/bad.fit", builder.non_fit_bytes())

    report = _drain(inbox, data_root)

    assert report.sync.written == ("workouts/2021-09-07-run-1946.md",)
    assert len(report.sync.failures) == 1
    failure = report.sync.failures[0]
    assert failure.source == "nested/bad.fit"
    assert str(inbox) not in failure.source


# --- deferral, including the unreadable-file case ------------------------


def test_a_changed_candidate_is_deferred_not_failed(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    target = _put(inbox, "arriving.fit", b"short")

    def growing_sleep(seconds: float) -> None:
        target.write_bytes(b"short-but-now-longer")

    report = drain(
        inbox,
        data_root,
        settings=DEFAULT_INBOX_SETTINGS,
        processed_dir=None,
        quarantine=_EMPTY_QUARANTINE,
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        sleep=growing_sleep,
    )

    assert report.sync.written == ()
    assert report.sync.failures == ()
    assert len(report.deferred) == 1
    assert report.deferred[0].subject == "arriving.fit"
    assert report.deferred[0].detail


def test_an_unreadable_stable_candidate_is_deferred_not_failed_or_quarantined(
    tmp_path: Path,
) -> None:
    """The readability probe (design: "Readiness in two stages"): a candidate
    that observes as stable across both stat observations but then cannot be
    *read* (simulated here with permission bits, standing in for an
    unmaterialized cloud placeholder) is a deferral, never a failure and
    never a quarantine entry (inbox Req 4.2). This slice's probe is a plain
    read, with no hash computed from it -- task 3.2 adds the content hash
    the quarantine check needs, reusing this same read rather than a second
    one."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    target = _put(inbox, "locked.fit", builder.run_fit_bytes())
    target.chmod(0o000)
    try:
        report = _drain(inbox, data_root)
    finally:
        target.chmod(0o644)

    assert report.sync.written == ()
    assert report.sync.failures == ()
    assert report.quarantined == ()
    assert len(report.deferred) == 1
    assert report.deferred[0].subject == "locked.fit"
    assert report.deferred[0].detail


def test_only_failures_drive_the_failure_outcome_not_deferrals(tmp_path: Path) -> None:
    """A drain whose only exceptional entries are deferrals must present the
    same all-clear shape a caller's exit-code logic keys off of: an empty
    ``failures`` tuple (inbox Req 4.6)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    target = _put(inbox, "arriving.fit", b"short")

    def growing_sleep(seconds: float) -> None:
        target.write_bytes(b"short-but-now-longer")

    report = drain(
        inbox,
        data_root,
        settings=DEFAULT_INBOX_SETTINGS,
        processed_dir=None,
        quarantine=_EMPTY_QUARANTINE,
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        sleep=growing_sleep,
    )

    assert report.sync.failures == ()
    assert len(report.deferred) == 1


# --- report names the drained inbox path ---------------------------------


def test_report_names_the_drained_inbox_path(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()

    report = _drain(inbox, data_root)

    assert isinstance(report, DrainReport)
    assert report.inbox == str(inbox)


# --- ownership declaration refresh wired into the drain -------------------


def test_drain_emits_the_declaration_into_a_data_root_that_lacks_one(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()

    _drain(inbox, data_root)

    assert declaration_path(data_root, f"{WORKOUTS_DIR}/").is_file()
    assert declaration_path(data_root, f"{ARCHIVE_DIR}/").is_file()


def test_drain_refreshes_a_stale_declaration(tmp_path: Path) -> None:
    # A "stale" declaration here is one that is readable but whose content
    # differs from what fitdocs would write today (design: write-when-
    # different) -- not the "foreign" (unrecognized-origin) case covered
    # separately below.
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()

    _drain(inbox, data_root)
    workouts_decl = declaration_path(data_root, f"{WORKOUTS_DIR}/")
    current = workouts_decl.read_text(encoding="utf-8")
    stale = current + "\n<!-- stale: ensure_declarations rewrites this -->\n"
    workouts_decl.write_text(stale, encoding="utf-8")

    report = _drain(inbox, data_root)

    assert workouts_decl.read_text(encoding="utf-8") == current
    assert workouts_decl.read_text(encoding="utf-8") != stale
    assert report.sync.failures == ()


def test_drain_foreign_declaration_becomes_a_warning_not_a_failure(
    tmp_path: Path,
) -> None:
    """Mirrors ``tests/test_declaration_refresh.py``'s sync coverage: a
    foreign occupant at a declared path is preserved untouched and reported
    as a :class:`~fitdocs.sync.DocWarning`, never a failure (inbox Req 7.6)."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_root = tmp_path / "data"
    (data_root / WORKOUTS_DIR).mkdir(parents=True)
    foreign = declaration_path(data_root, f"{WORKOUTS_DIR}/")
    foreign.write_text("# hands off, this is mine\n", encoding="utf-8")
    foreign_text = foreign.read_text(encoding="utf-8")

    report = _drain(inbox, data_root)

    assert foreign.read_text(encoding="utf-8") == foreign_text
    assert report.sync.failures == ()
    expected_doc = f"{WORKOUTS_DIR}/{DECLARATION_FILENAME}"
    matching = [w for w in report.sync.warnings if w.doc == expected_doc]
    assert len(matching) == 1


# --- report type is exactly the unchanged SyncReport, composed -----------


def test_drain_report_wraps_an_unmodified_sync_report(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(inbox, "good.fit", builder.run_fit_bytes())

    report = _drain(inbox, data_root)

    assert isinstance(report.sync, SyncReport)
    assert len(report.sync.written) == 1
    assert isinstance(report.sync.failures, tuple)
    for failure in report.sync.failures:
        assert isinstance(failure, FileFailure)


# --- idempotency under the (default) leave-in-place disposition ----------


def test_second_drain_over_unchanged_inbox_skips_and_writes_nothing_new(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(inbox, "good.fit", builder.run_fit_bytes())

    first = _drain(inbox, data_root)
    second = _drain(inbox, data_root)

    assert len(first.sync.written) == 1
    assert second.sync.written == ()
    assert len(second.sync.skipped) == 1
    assert second.sync.failures == ()


# --- symlinked-document scan parity with sync/regen (beyond Req 7.6) -----


def test_drain_warns_about_a_symlinked_workouts_document(tmp_path: Path) -> None:
    """``drain`` runs the same once-per-run symlinked-``workouts/*.md``-
    document scan :func:`~fitdocs.sync.sync` and :func:`~fitdocs.sync.regen`
    already share (task 7.2 F2) -- named explicitly in ``drain``'s docstring
    as parity with those two entry points, not as coverage of inbox Req 7.6
    itself (that requirement is the declaration refresh, tested above)."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_root = tmp_path / "data"
    workouts = data_root / WORKOUTS_DIR
    workouts.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("not a real document\n", encoding="utf-8")
    stray = workouts / "stray.md"
    stray.symlink_to(outside)

    report = _drain(inbox, data_root)

    expected_doc = f"{WORKOUTS_DIR}/stray.md"
    matching = [w for w in report.sync.warnings if w.doc == expected_doc]
    assert len(matching) == 1
    assert "symlink" in matching[0].detail


# --- declaration refresh happens before any per-file processing ----------


def test_refresh_declarations_runs_before_any_per_file_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the ordering both ``drain``'s docstring and design.md assert:
    the declaration refresh runs before per-file processing starts, not
    interleaved with or after it. A spy records call order around the real
    implementations (so the run's actual outcome is unaffected) and asserts
    the refresh is always the first call recorded, strictly before any
    ``_process_isolated`` call."""
    import fitdocs.sync as sync_module

    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(inbox, "good.fit", builder.run_fit_bytes())

    calls: list[str] = []
    real_refresh = sync_module.refresh_declarations
    real_process = sync_module._process_isolated

    def spy_refresh(*args: object, **kwargs: object) -> None:
        calls.append("refresh_declarations")
        real_refresh(*args, **kwargs)  # type: ignore[arg-type]

    def spy_process(*args: object, **kwargs: object) -> None:
        calls.append("_process_isolated")
        real_process(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sync_module, "refresh_declarations", spy_refresh)
    monkeypatch.setattr(sync_module, "_process_isolated", spy_process)

    _drain(inbox, data_root)

    assert "_process_isolated" in calls  # the fixture file really was processed
    assert calls[0] == "refresh_declarations"
    assert calls.index("refresh_declarations") < calls.index("_process_isolated")


# ===========================================================================
# Quarantine partitioning, recording, and retry (task 3.2, inbox Req 5.1-5.5,
# 5.7, 7.4)
# ===========================================================================


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _place_damaged_notes_document(data_root: Path) -> str:
    """Pre-place a workout document, matched by the re-export fixture's
    session uuid, whose ``notes`` region is damaged (a begin marker with no
    matching end) -- exactly ``tests/test_sync.py``'s region-conflict setup.
    Returns the damaged document's original text, for later untouched checks.
    """
    workouts = data_root / WORKOUTS_DIR
    workouts.mkdir(parents=True, exist_ok=True)
    damaged = (
        "---\n"
        "title: Run 2021-09-07 19:46\n"
        "type: workout\n"
        "doc_version: 1\n"
        f"uuid: {_REEXPORT_UUID}\n"
        "sport: Run\n"
        "modality: run\n"
        "---\n\n"
        f"{begin_marker('notes')}\n"
        "a note whose end marker was deleted\n"
    )
    doc_path(data_root, _REEXPORT_STEM).write_text(damaged, encoding="utf-8")
    return damaged


# --- Observable 1: first source-level failing drain creates an entry, fails


def test_first_source_level_failure_creates_a_quarantine_entry_and_fails(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)

    report = _drain(inbox, data_root)

    assert len(report.sync.failures) == 1
    assert report.quarantined == ()
    record = load_quarantine(data_root)
    entry = record.get(_sha256(bad))
    assert entry is not None
    assert entry.name == "bad.fit"
    assert entry.reason == report.sync.failures[0].reason


# --- Observable 2: the following drain reports it quietly and succeeds


def test_following_drain_reports_the_quarantined_file_quietly_and_succeeds(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)

    first = _drain(inbox, data_root)
    assert len(first.sync.failures) == 1

    record = load_quarantine(data_root)
    second = _drain(inbox, data_root, quarantine=record)

    assert second.sync.failures == ()
    assert second.sync.written == ()
    assert second.sync.skipped == ()
    assert len(second.quarantined) == 1
    assert second.quarantined[0].subject == "bad.fit"
    assert second.quarantined[0].detail == first.sync.failures[0].reason


# --- Observable 3: a document-level failure fails the run, leaves no entry,
# and succeeds on the next drain once the document is repaired -------------


def test_document_level_failure_fails_the_run_and_leaves_no_quarantine_entry(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    damaged = _place_damaged_notes_document(data_root)
    reexport = builder.reexport_a_fit_bytes()
    _put(inbox, "reexport.fit", reexport)

    report = _drain(inbox, data_root)

    assert len(report.sync.failures) == 1
    assert any("reexport.fit" in f.source for f in report.sync.failures)
    assert report.quarantined == ()
    # No quarantine record file was ever written: a document-level fault is
    # never recorded (Req 5.7).
    record = load_quarantine(data_root)
    assert record.entries == ()
    assert doc_path(data_root, _REEXPORT_STEM).read_text(encoding="utf-8") == damaged


def test_document_level_failure_succeeds_next_drain_once_document_repaired(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    _place_damaged_notes_document(data_root)
    reexport = builder.reexport_a_fit_bytes()
    _put(inbox, "reexport.fit", reexport)

    first = _drain(inbox, data_root)
    assert len(first.sync.failures) == 1

    # Repair the document by removing the damaged region entirely, and drain
    # again with no retry flag and no quarantine record needed -- since the
    # fault was never recorded, no special handling is required at all.
    doc_path(data_root, _REEXPORT_STEM).write_text(
        "---\n"
        "title: Run 2021-09-07 19:46\n"
        "type: workout\n"
        "doc_version: 1\n"
        f"uuid: {_REEXPORT_UUID}\n"
        "sport: Run\n"
        "modality: run\n"
        "---\n",
        encoding="utf-8",
    )

    second = _drain(inbox, data_root)

    assert second.sync.failures == ()
    assert len(second.sync.written) == 1
    assert second.quarantined == ()


# --- Observable 4: a renamed copy is still recognized; a same-named
# different file is treated as new ------------------------------------------


def test_renamed_copy_of_quarantined_content_is_still_recognized(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    first = _drain(inbox, data_root)
    assert len(first.sync.failures) == 1

    # Same bytes, renamed: still recognized by content hash (Req 5.4).
    (inbox / "bad.fit").unlink()
    _put(inbox, "renamed.fit", bad)
    record = load_quarantine(data_root)

    second = _drain(inbox, data_root, quarantine=record)

    assert second.sync.failures == ()
    assert len(second.quarantined) == 1
    assert second.quarantined[0].subject == "renamed.fit"


def test_same_named_different_content_is_treated_as_new(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    first = _drain(inbox, data_root)
    assert len(first.sync.failures) == 1
    record = load_quarantine(data_root)
    assert record.get(_sha256(bad)) is not None

    # Different bytes under the exact same name: not a match by content, so
    # it is treated as new -- reprocessed, not silently quarantined.
    (inbox / "bad.fit").unlink()
    good = builder.run_fit_bytes()
    _put(inbox, "bad.fit", good)

    second = _drain(inbox, data_root, quarantine=record)

    assert second.quarantined == ()
    assert len(second.sync.written) == 1


# --- Observable 5: retry both clears and updates entries -------------------


def test_retry_quarantined_clears_the_entry_on_success(tmp_path: Path) -> None:
    """The removal must be observable through the *persisted* record, not a
    caller-held in-memory value ``drain`` never returns: this test writes the
    stale record to disk first, confirms the precondition, captures the raw
    bytes on disk, then confirms both that the sha is gone from the reloaded
    record *and* that the file's bytes actually changed -- so a mutant that
    skips the in-memory clear (and therefore never marks the record changed,
    never triggers a save, and leaves the stale file exactly as it was)
    cannot pass by accident."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    good = builder.run_fit_bytes()
    _put(inbox, "good.fit", good)
    # Artificially quarantine content that would actually succeed, to prove
    # the retry path clears the entry once processing succeeds -- the
    # underlying cause of an original quarantine cannot itself be undone
    # from a test (the same bytes always fail the same way), so this crafts
    # the "was quarantined, now the record is stale" case directly.
    stale_record = QuarantineRecord(
        entries=(
            QuarantineEntry(sha256=_sha256(good), name="good.fit", reason="stale"),
        )
    )
    save_quarantine(data_root, stale_record)
    assert load_quarantine(data_root).get(_sha256(good)) is not None
    before_bytes = quarantine_path(data_root).read_bytes()

    report = _drain(
        inbox,
        data_root,
        quarantine=load_quarantine(data_root),
        retry_quarantined=True,
    )

    assert report.quarantined == ()
    assert len(report.sync.written) == 1
    assert report.sync.failures == ()
    record = load_quarantine(data_root)
    assert record.get(_sha256(good)) is None
    assert quarantine_path(data_root).read_bytes() != before_bytes


def test_retry_quarantined_updates_the_entry_on_renewed_failure(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    stale_record = QuarantineRecord(
        entries=(
            QuarantineEntry(sha256=_sha256(bad), name="bad.fit", reason="stale reason"),
        )
    )

    report = _drain(inbox, data_root, quarantine=stale_record, retry_quarantined=True)

    assert report.quarantined == ()
    assert len(report.sync.failures) == 1
    record = load_quarantine(data_root)
    entry = record.get(_sha256(bad))
    assert entry is not None
    assert entry.reason == report.sync.failures[0].reason
    assert entry.reason != "stale reason"


def test_retry_quarantined_false_leaves_recorded_files_unprocessed(
    tmp_path: Path,
) -> None:
    """The default: without the retry option, a quarantined file's content is
    never handed to the pipeline, even if it would now succeed."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    good = builder.run_fit_bytes()
    _put(inbox, "good.fit", good)
    stale_record = QuarantineRecord(
        entries=(
            QuarantineEntry(sha256=_sha256(good), name="good.fit", reason="stale"),
        )
    )

    report = _drain(inbox, data_root, quarantine=stale_record, retry_quarantined=False)

    assert report.sync.written == ()
    assert report.sync.skipped == ()
    assert report.sync.failures == ()
    assert len(report.quarantined) == 1
    assert report.quarantined[0].detail == "stale"


def test_force_does_not_imply_retry(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    good = builder.run_fit_bytes()
    _put(inbox, "good.fit", good)
    stale_record = QuarantineRecord(
        entries=(
            QuarantineEntry(sha256=_sha256(good), name="good.fit", reason="stale"),
        )
    )

    report = _drain(inbox, data_root, quarantine=stale_record, force=True)

    assert report.sync.written == ()
    assert report.sync.failures == ()
    assert len(report.quarantined) == 1


# --- in-drain evolution: a later candidate sees an earlier one's new entry -


def test_a_second_candidate_sharing_bad_content_is_quarantined_within_one_drain(
    tmp_path: Path,
) -> None:
    """Pins that the quarantine partition is checked against the record as it
    evolves *during* this drain, not only the record the caller passed in --
    two distinct candidates sharing identical undecodable content in one
    drain: the first (by sorted inbox-relative order) is processed, fails,
    and gets recorded; the second must see that just-recorded entry and be
    quarantined quietly rather than independently reprocessed and failed."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "a-bad.fit", bad)
    _put(inbox, "b-bad.fit", bad)

    report = _drain(inbox, data_root)

    assert len(report.sync.failures) == 1
    assert report.sync.failures[0].source == "a-bad.fit"
    assert len(report.quarantined) == 1
    assert report.quarantined[0].subject == "b-bad.fit"
    assert report.quarantined[0].detail == report.sync.failures[0].reason
    record = load_quarantine(data_root)
    assert len(record.entries) == 1


# --- quarantined files never enter written/skipped/failures ---------------


def test_quarantined_files_never_enter_written_skipped_or_failures(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    _drain(inbox, data_root)
    record = load_quarantine(data_root)

    second = _drain(inbox, data_root, quarantine=record)

    assert "bad.fit" not in second.sync.written
    assert "bad.fit" not in second.sync.skipped
    assert not any("bad.fit" in f.source for f in second.sync.failures)
    assert len(second.quarantined) == 1


# --- Req 5.3: a drain whose only exceptional entries are quarantined files
# succeeds --------------------------------------------------------------


def test_a_drain_with_only_quarantined_entries_succeeds(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    _drain(inbox, data_root)
    record = load_quarantine(data_root)

    second = _drain(inbox, data_root, quarantine=record)

    assert second.sync.failures == ()
    assert len(second.quarantined) == 1


# --- persistence: once, at the end, only when changed (Req 7.4) -----------


def test_quarantine_record_is_written_when_a_new_entry_is_recorded(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(inbox, "bad.fit", builder.non_fit_bytes())

    _drain(inbox, data_root)

    assert quarantine_path(data_root).is_file()


def test_quarantine_record_is_not_rewritten_when_the_drain_makes_no_change(
    tmp_path: Path,
) -> None:
    """The record file's bytes and mtime are unchanged after a drain that
    quarantines nothing new (every candidate already recorded, not
    retried). This alone does not prove ``save_quarantine`` was never
    *called* -- ``save_quarantine`` itself no-ops a content-equal write, so
    a spurious call with unchanged content would pass this assertion too;
    see ``test_drain_never_calls_save_quarantine_when_nothing_changed``
    below for the call-count proof that ``drain`` gates the call itself."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    _drain(inbox, data_root)

    path = quarantine_path(data_root)
    before_mtime = path.stat().st_mtime_ns
    record = load_quarantine(data_root)

    # Second drain: the same file is already quarantined and not retried, so
    # nothing about the record changes -- the file must not be rewritten.
    _drain(inbox, data_root, quarantine=record)

    assert path.stat().st_mtime_ns == before_mtime


def test_drain_never_calls_save_quarantine_when_nothing_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The call-count proof ``test_quarantine_record_is_not_rewritten_...``
    cannot give by itself: a spy over ``fitdocs.sync.save_quarantine`` proves
    ``drain`` gates the call itself on ``record_changed`` rather than relying
    on ``save_quarantine``'s own write-if-different no-op -- so a mutant that
    calls ``save_quarantine`` unconditionally (an otherwise-silent spurious
    call on unchanged content) is caught here even though it would leave the
    file's bytes and mtime untouched."""
    import fitdocs.sync as sync_module

    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    bad = builder.non_fit_bytes()
    _put(inbox, "bad.fit", bad)
    _drain(inbox, data_root)
    record = load_quarantine(data_root)

    calls: list[object] = []
    real_save = sync_module.save_quarantine

    def spy_save(*args: object, **kwargs: object) -> bool:
        calls.append(args)
        return real_save(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sync_module, "save_quarantine", spy_save)

    # Second drain: the same file is already quarantined and not retried, so
    # nothing about the record changes -- save_quarantine must not be called.
    _drain(inbox, data_root, quarantine=record)

    assert calls == []


def test_quarantine_record_is_not_created_for_a_drain_with_no_failures(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(inbox, "good.fit", builder.run_fit_bytes())

    _drain(inbox, data_root)

    assert not quarantine_path(data_root).is_file()


# ===========================================================================
# Disposition (task 3.3, inbox Req 6.2, 6.4, 6.5, 7.5): a candidate is moved
# out of the inbox iff its content is present in fit-archive/ once its
# processing has finished -- never on the strength of the `skipped` label.
# ===========================================================================


def test_leave_in_place_leaves_the_inbox_byte_identical_after_a_drain(
    tmp_path: Path,
) -> None:
    """Under the default leave-in-place disposition, a successful drain never
    touches the inbox: the file survives with identical bytes, and both
    disposition channels stay empty (inbox Req 6.1)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    original = builder.run_fit_bytes()
    target = _put(inbox, "good.fit", original)

    report = _drain(inbox, data_root)

    assert len(report.sync.written) == 1
    assert target.is_file()
    assert target.read_bytes() == original
    assert report.moved == ()
    assert report.move_failures == ()


def test_leave_disposition_with_a_processed_dir_supplied_still_touches_nothing(
    tmp_path: Path,
) -> None:
    """The disposition gate keys on ``settings.disposition``, not merely on
    whether a *processed_dir* was supplied to :func:`drain`: even with a real,
    pre-existing processed directory available, the leave-in-place default
    relocates nothing and leaves that directory empty (inbox Req 6.1)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    original = builder.run_fit_bytes()
    target = _put(inbox, "good.fit", original)

    report = _drain(
        inbox, data_root, settings=DEFAULT_INBOX_SETTINGS, processed_dir=processed
    )

    assert len(report.sync.written) == 1
    assert target.is_file()
    assert target.read_bytes() == original
    assert report.moved == ()
    assert report.move_failures == ()
    assert list(processed.iterdir()) == []


def test_forced_reprocessing_failure_on_already_archived_content_is_not_moved(
    tmp_path: Path,
) -> None:
    """Regression for the one case where "archived" and "failed" coincide for
    the very same candidate: under ``force=True``, an already-archived
    candidate bypasses the ordinary dedupe skip (``sync.py``'s
    ``if archive.exists() and not force:`` short-circuit) and is reprocessed
    from scratch, so a damaged preserved region can raise a document-level
    failure for content that *is* already present in ``fit-archive/``. The
    disposition gate must key on ``not failed_this_candidate`` and not on
    archive presence alone, or this failed file would be silently relocated
    out of the inbox even though the run reports it as a failure (inbox Req
    6.4)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    reexport = builder.reexport_a_fit_bytes()
    sha = hashlib.sha256(reexport).hexdigest()
    source = _put(inbox, "a.fit", reexport)

    # First drain: written, archived, and (leave-in-place default) left in
    # the inbox.
    first = _drain(inbox, data_root)
    assert len(first.sync.written) == 1
    assert archive_path(data_root, sha).is_file()
    assert source.is_file()

    # Damage the now-matched document's preserved `notes` region.
    _place_damaged_notes_document(data_root)

    # Second drain, forced: the archive-exists dedupe skip is bypassed, the
    # pipeline reprocesses the (already-archived) content, and the damaged
    # region raises a document-level RegionError -- a failure for content
    # that IS present in fit-archive/.
    second = _drain(
        inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed, force=True
    )

    assert len(second.sync.failures) == 1
    assert archive_path(data_root, sha).is_file()
    assert second.moved == ()
    assert second.move_failures == ()
    assert source.is_file()
    assert not (processed / "a.fit").exists()


def test_move_disposition_relocates_only_files_whose_content_is_archived(
    tmp_path: Path,
) -> None:
    """Under the move disposition, a written candidate (its content just
    archived, last write of the pipeline) is relocated out of the inbox and
    named in ``moved``; a candidate whose processing failed is left in the
    inbox untouched and never named in ``moved`` or ``move_failures`` (inbox
    Req 6.2)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    good = builder.run_fit_bytes()
    bad = builder.non_fit_bytes()
    good_source = _put(inbox, "good.fit", good)
    bad_source = _put(inbox, "bad.fit", bad)

    report = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    # The written file's content is archived (the pipeline's last write), so
    # it passes the disposition gate and is relocated.
    assert len(report.sync.written) == 1
    assert not good_source.exists()
    assert len(report.moved) == 1
    moved_path = Path(report.moved[0])
    assert moved_path.is_file()
    assert moved_path.read_bytes() == good

    # The failed file archived nothing, so it never reaches the gate: it
    # stays exactly where it was.
    assert len(report.sync.failures) == 1
    assert bad_source.is_file()
    assert bad_source.read_bytes() == bad
    assert report.move_failures == ()


def test_failed_deferred_and_quarantined_files_stay_in_the_inbox_under_move(
    tmp_path: Path,
) -> None:
    """The three channels that never reach the disposition gate at all --
    failed, deferred (both of its paths: settle-deferral and the
    readability-probe's read-failure deferral), and quarantined -- each
    leave their file exactly where it was, even with the move disposition
    active (inbox Req 6.2, 6.4)."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"

    fresh_bad = builder.non_fit_bytes()
    fresh_bad_source = _put(inbox, "fresh-bad.fit", fresh_bad)

    known_bad = builder.truncated_fit_bytes()
    known_bad_sha = hashlib.sha256(known_bad).hexdigest()
    known_bad_source = _put(inbox, "known-bad.fit", known_bad)
    prequarantined = QuarantineRecord(
        entries=(
            QuarantineEntry(
                sha256=known_bad_sha, name="known-bad.fit", reason="previously bad"
            ),
        )
    )

    arriving_source = _put(inbox, "arriving.fit", b"short")

    def growing_sleep(seconds: float) -> None:
        arriving_source.write_bytes(b"short-but-now-longer")

    # A stable candidate that settles fine but cannot actually be read (the
    # readability-probe's OSError branch, distinct from settle-deferral).
    locked_source = _put(inbox, "locked.fit", builder.run_fit_bytes())
    locked_source.chmod(0o000)
    try:
        report = drain(
            inbox,
            data_root,
            settings=_MOVE_SETTINGS,
            processed_dir=processed,
            quarantine=prequarantined,
            athlete=None,
            tz=_TZ,
            tiles=_TILES,
            sleep=growing_sleep,
        )
    finally:
        locked_source.chmod(0o644)

    # Failed: never reaches the gate, stays in place.
    assert len(report.sync.failures) == 1
    assert fresh_bad_source.is_file()
    assert fresh_bad_source.read_bytes() == fresh_bad

    # Deferred (settle path AND read-failure path): never reaches the gate,
    # stays in place.
    assert len(report.deferred) == 2
    deferred_subjects = {note.subject for note in report.deferred}
    assert deferred_subjects == {"arriving.fit", "locked.fit"}
    assert arriving_source.is_file()
    assert locked_source.is_file()

    # Quarantined: never reaches the gate, stays in place.
    assert len(report.quarantined) == 1
    assert known_bad_source.is_file()
    assert known_bad_source.read_bytes() == known_bad

    assert report.moved == ()
    assert report.move_failures == ()


def test_a_failed_move_is_reported_in_its_own_channel_and_the_run_still_succeeds(
    tmp_path: Path,
) -> None:
    """A move that fails after successful processing leaves the completed
    processing intact, leaves the file in the inbox, and is reported in its
    own ``move_failures`` channel -- never folded into ``failures`` or
    ``moved`` -- without changing the run's success (inbox Req 6.5)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    # "blocked" occupies the destination subdirectory's name as a plain file,
    # so `move_processed`'s `mkdir(parents=True)` for processed/blocked/*
    # cannot succeed (mirrors tests/test_inbox.py's uncreatable-parent case).
    _put(processed, "blocked", b"i am a file, not a directory")
    good = builder.run_fit_bytes()
    good_source = _put(inbox, "blocked/good.fit", good)

    report = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    # Processing succeeded and is unaffected by the move failure.
    assert len(report.sync.written) == 1
    assert report.sync.failures == ()

    # The move failed: reported in its own channel, not folded into either
    # `failures` or `moved`.
    assert report.moved == ()
    assert len(report.move_failures) == 1
    note = report.move_failures[0]
    assert note.subject == "blocked/good.fit"
    assert note.detail

    # The already-completed processing stands; the source stays in the inbox
    # for a later drain to retry.
    assert good_source.is_file()
    assert good_source.read_bytes() == good
    assert archive_path(data_root, hashlib.sha256(good).hexdigest()).is_file()


def test_move_disposition_collision_stores_under_a_distinct_name_both_survive(
    tmp_path: Path,
) -> None:
    """A drain-level collision at the move destination is handled exactly as
    :func:`fitdocs.inbox.move_processed` documents in isolation: the moved
    file is stored under a distinct, content-derived name rather than
    overwriting the pre-existing occupant, both files survive, and
    ``report.moved`` names the *actual* (renamed) destination on disk (inbox
    Req 6.2, 6.3, 7.1)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    processed.mkdir()
    # Pre-occupy the destination name the move would otherwise use --
    # `move_processed` preserves the candidate's inbox-relative subpath, so
    # this is "good.fit" under `processed`, unrelated to the rendered
    # document's own stem.
    preexisting = b"pre-existing, unrelated content"
    _put(processed, "good.fit", preexisting)

    good = builder.run_fit_bytes()
    good_source = _put(inbox, "good.fit", good)

    report = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    assert len(report.sync.written) == 1
    assert not good_source.exists()
    assert len(report.moved) == 1
    moved_path = Path(report.moved[0])

    # The renamed destination is the one that actually exists on disk and
    # holds the moved content -- never the pre-occupied name.
    assert moved_path != processed / "good.fit"
    assert moved_path.is_file()
    assert moved_path.read_bytes() == good

    # The pre-existing occupant is untouched.
    assert (processed / "good.fit").read_bytes() == preexisting


def test_move_disposition_with_no_processed_dir_touches_nothing(
    tmp_path: Path,
) -> None:
    """A move disposition without a resolved ``processed_dir`` (a contract
    violation the CLI is responsible for preventing) is handled defensively:
    disposition is simply skipped, exactly like leave-in-place."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    target = _put(inbox, "good.fit", builder.run_fit_bytes())

    report = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=None)

    assert len(report.sync.written) == 1
    assert target.is_file()
    assert report.moved == ()
    assert report.move_failures == ()


def test_second_drain_under_move_finds_an_empty_inbox_and_does_nothing(
    tmp_path: Path,
) -> None:
    """Idempotency under the move disposition (inbox Req 7.5): the first
    drain relocates every eligible file, so a second drain over the same
    inbox finds it empty and reports nothing at all."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    _put(inbox, "good.fit", builder.run_fit_bytes())

    first = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)
    assert len(first.moved) == 1
    assert sorted(p.name for p in inbox.iterdir() if p.is_file()) == []

    second = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    assert second.sync.written == ()
    assert second.sync.skipped == ()
    assert second.sync.failures == ()
    assert second.deferred == ()
    assert second.quarantined == ()
    assert second.moved == ()
    assert second.move_failures == ()


def test_already_archived_skip_is_moved_on_a_later_drain_under_move(
    tmp_path: Path,
) -> None:
    """The disposition gate is content-in-``fit-archive/``, not a
    written-this-run label (inbox Req 6.2): a file archived by an *earlier*
    drain (here, a first drain under the default leave disposition) is still
    relocated by a later drain that switches to the move disposition, even
    though that later drain reports the candidate as ``skipped`` rather than
    ``written`` (inbox Req 6.5)."""
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    content = builder.run_fit_bytes()
    source = _put(inbox, "good.fit", content)

    # First drain: default leave-in-place disposition. The file is written
    # and archived, and -- since nothing moves it -- stays in the inbox.
    first = _drain(inbox, data_root)
    assert len(first.sync.written) == 1
    assert source.is_file()

    # Second drain: same unchanged inbox, now under the move disposition.
    # The content is already archived, so this run skips it (no new write)
    # yet the disposition gate still fires because it checks archive
    # presence, not the `skipped` label.
    second = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    assert second.sync.written == ()
    assert len(second.sync.skipped) == 1
    assert second.sync.failures == ()
    assert len(second.moved) == 1
    moved_path = Path(second.moved[0])
    assert moved_path.is_file()
    assert moved_path.read_bytes() == content
    assert not source.exists()
    assert sorted(p.name for p in inbox.iterdir() if p.is_file()) == []


def test_doc_version_gate_skip_stays_in_inbox_under_move_and_is_retried(
    tmp_path: Path,
) -> None:
    """The headline Observable (inbox Req 6.2, 6.4, 7.5): a document at a
    newer document-format version is skipped with a warning, nothing lands
    in the processed directory for it, the file stays in the inbox, the next
    drain still finds it as a candidate, and it is moved only once a drain
    actually archives it -- asserted on filesystem state, not report labels.
    """
    inbox = tmp_path / "inbox"
    data_root = tmp_path / "data"
    data_root.mkdir()
    processed = tmp_path / "processed"
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    doc = doc_path(data_root, _REEXPORT_STEM)

    # First export: written, archived, and (since it is now archived) moved
    # out of the inbox.
    _put(inbox, "a.fit", a)
    first = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)
    assert doc.is_file()
    assert _frontmatter(doc)["doc_version"] == DOC_VERSION
    assert len(first.moved) == 1

    # Simulate the document being written by a NEWER fitdocs.
    newer = _set_doc_version_line(doc.read_text(encoding="utf-8"), "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    # A re-export (same session UUID, different bytes -- NOT yet archived)
    # arrives in the inbox and matches this document via `uuid`.
    b_source = _put(inbox, "b.fit", b)
    b_sha = hashlib.sha256(b).hexdigest()

    second = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    # Nothing was written for the gated source; it is skipped, not a failure.
    assert second.sync.written == ()
    assert len(second.sync.skipped) == 1
    assert second.sync.failures == ()
    assert len(second.sync.warnings) == 1
    # Filesystem-state assertions -- not report labels:
    assert not archive_path(data_root, b_sha).exists()  # nothing archived
    assert b_source.is_file()  # the file stays in the inbox
    assert not (processed / "b.fit").exists()  # nothing landed in processed
    assert second.moved == ()  # not moved this drain
    assert doc.read_text(encoding="utf-8") == newer  # document left untouched

    # The next drain still finds it as a candidate and repeats the gate.
    third = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)
    assert third.sync.written == ()
    assert len(third.sync.skipped) == 1
    assert b_source.is_file()
    assert third.moved == ()

    # Once the document is no longer newer (simulating an upgraded fitdocs),
    # a drain processes the source, archives it, and only then moves it.
    doc.write_text(
        _set_doc_version_line(doc.read_text(encoding="utf-8"), ""),
        encoding="utf-8",
    )
    fourth = _drain(inbox, data_root, settings=_MOVE_SETTINGS, processed_dir=processed)

    assert len(fourth.sync.written) == 1
    assert archive_path(data_root, b_sha).is_file()
    assert not b_source.exists()
    assert len(fourth.moved) == 1
    assert Path(fourth.moved[0]).read_bytes() == b


# ===========================================================================
# is_source_level: the single predicate over the failure's exception type
# ===========================================================================


def test_is_source_level_is_true_for_fit_decode_error(tmp_path: Path) -> None:
    from fitdocs import FitDecodeError

    assert is_source_level(FitDecodeError("bad bytes")) is True


def test_is_source_level_is_false_for_region_error(tmp_path: Path) -> None:
    from fitdocs.docmerge import RegionError

    assert is_source_level(RegionError("damaged region")) is False


def test_is_source_level_defaults_to_false_for_an_unrecognized_exception_type() -> None:
    class _SomeOtherFault(Exception):
        pass

    assert is_source_level(_SomeOtherFault("surprise")) is False
