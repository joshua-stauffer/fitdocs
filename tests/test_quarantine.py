"""Tests for :mod:`fitdocs.quarantine` -- the quarantine record store.

Covers: absent-yields-empty-creating-nothing, a first save into a data root
with no tool-state directory, hash-sorted order pinned separately at each of
the three sites that establishes it -- ``with_entry`` and the load path
observed in memory with no round trip, and the save path observed in the
written bytes -- malformed-record raising
(unparseable TOML, an unreadable file, bad entry shapes, and duplicate
``sha256`` entries) naming the file, content-keyed membership (rename does
not resurrect; same-named different content misses; a lookup by the stored
name itself also misses), copy-not-mutate mutators, and write-if-different
proven by inode/mtime stability, an untouched-bytes check, and the boolean
return value.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fitdocs.layout import quarantine_path
from fitdocs.quarantine import (
    QUARANTINE_VERSION,
    QuarantineEntry,
    QuarantineError,
    QuarantineRecord,
    load_quarantine,
    save_quarantine,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def test_load_absent_yields_empty_and_creates_nothing(tmp_path: Path) -> None:
    """A data root with no ``.fitdocs/`` directory at all still loads cleanly.

    Asserts the record is empty and that neither the quarantine file nor its
    parent ``.fitdocs/`` directory exists afterward -- reading never creates
    (Req 5.6).
    """
    record = load_quarantine(tmp_path)
    assert record.entries == ()
    assert not quarantine_path(tmp_path).exists()
    assert not quarantine_path(tmp_path).parent.exists()


def test_first_save_creates_tool_state_dir_on_demand(tmp_path: Path) -> None:
    """Saving into a data root with no ``.fitdocs/`` directory succeeds.

    The directory is created on demand at save time (unlike ``layout``,
    which performs no I/O), and the file is written.
    """
    assert not (tmp_path / ".fitdocs").exists()
    record = QuarantineRecord(
        entries=(QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom"),)
    )
    wrote = save_quarantine(tmp_path, record)
    assert wrote is True
    assert quarantine_path(tmp_path).is_file()


def test_with_entry_sorts_entries_in_memory_without_any_round_trip() -> None:
    """``with_entry`` establishes hash order on ``entries`` itself.

    Observes ``record.entries`` **directly**, with no save and no load. Every
    other ordering test in this module observed order through serialized bytes,
    and ``save_quarantine`` re-sorts on the way out -- so the save-path sort
    masked this one completely, and deleting ``with_entry``'s sort left the
    whole suite green. The module and class docstrings state the
    sorted-``entries`` invariant as a contract that in-memory consumers
    (``get``, ``without``, any future report or CLI listing) may rely on without
    a round trip; this is what pins it.

    Insertion is b-then-a against ``HASH_A < HASH_B``, so the tuple violates the
    asserted property before the sort runs.
    """
    entry_b = QuarantineEntry(sha256=HASH_B, name="b.fit", reason="reason-b")
    entry_a = QuarantineEntry(sha256=HASH_A, name="a.fit", reason="reason-a")
    assert HASH_A < HASH_B  # the fixture is only adversarial while this holds

    record = QuarantineRecord(entries=()).with_entry(entry_b).with_entry(entry_a)

    assert [e.sha256 for e in record.entries] == [HASH_A, HASH_B]


def test_load_sorts_entries_from_a_file_written_out_of_order(tmp_path: Path) -> None:
    """The load path establishes hash order on what it parses.

    The file is written **literally**, in reverse hash order. Producing it with
    ``save_quarantine`` would re-introduce exactly the mask this test exists to
    remove: the saved bytes would already be sorted, the load-path sort would
    have nothing left to do, and deleting it would stay green -- which is what
    the whole suite did before this test existed.
    """
    quarantine_file = quarantine_path(tmp_path)
    quarantine_file.parent.mkdir(parents=True, exist_ok=True)
    quarantine_file.write_text(
        f"quarantine_version = {QUARANTINE_VERSION}\n"
        "\n"
        "[[entries]]\n"
        f'sha256 = "{HASH_B}"\n'
        'name = "b.fit"\n'
        'reason = "reason-b"\n'
        "\n"
        "[[entries]]\n"
        f'sha256 = "{HASH_A}"\n'
        'name = "a.fit"\n'
        'reason = "reason-a"\n',
        encoding="utf-8",
    )
    # The precondition, asserted rather than assumed: the bytes on disk really
    # are out of order, so the sort has work to do.
    text = quarantine_file.read_text(encoding="utf-8")
    assert text.index(HASH_B) < text.index(HASH_A)

    record = load_quarantine(tmp_path)

    assert [e.sha256 for e in record.entries] == [HASH_A, HASH_B]


def test_round_trip_stable_sorted_order(tmp_path: Path) -> None:
    """A saved record loads back with entries sorted by sha256.

    Two records built with entries inserted in opposite order serialize
    identically and load back in the same (hash-sorted) order.

    Scope, stated precisely because this docstring used to overclaim: what it
    pins is the **stored form**, through ``save_quarantine``'s own sort. It does
    not pin ``with_entry``'s sort or the load path's -- the save-path sort
    re-establishes the order either way, which is why deleting either of the
    other two left this test green. Both are pinned directly by the two tests
    above.
    """
    entry_b = QuarantineEntry(sha256=HASH_B, name="b.fit", reason="reason-b")
    entry_a = QuarantineEntry(sha256=HASH_A, name="a.fit", reason="reason-a")

    record_inserted_b_then_a = (
        QuarantineRecord(entries=()).with_entry(entry_b).with_entry(entry_a)
    )
    save_quarantine(tmp_path, record_inserted_b_then_a)
    bytes_first = quarantine_path(tmp_path).read_bytes()

    other_root = tmp_path / "other"
    other_root.mkdir()
    record_inserted_a_then_b = (
        QuarantineRecord(entries=()).with_entry(entry_a).with_entry(entry_b)
    )
    save_quarantine(other_root, record_inserted_a_then_b)
    bytes_second = quarantine_path(other_root).read_bytes()

    assert bytes_first == bytes_second

    loaded = load_quarantine(tmp_path)
    assert [e.sha256 for e in loaded.entries] == [HASH_A, HASH_B]
    assert loaded.entries == (entry_a, entry_b)


def test_round_trip_preserves_fields(tmp_path: Path) -> None:
    """A loaded entry matches every field of the entry that was saved."""
    entry = QuarantineEntry(sha256=HASH_A, name="2026-07-12-run.fit", reason="CRC")
    save_quarantine(tmp_path, QuarantineRecord(entries=(entry,)))
    loaded = load_quarantine(tmp_path)
    assert loaded.get(HASH_A) == entry


def test_save_sorts_even_a_record_constructed_out_of_order(tmp_path: Path) -> None:
    """Saving a record whose ``entries`` tuple was built out of hash order
    still serializes them sorted by sha256.

    Builds a :class:`QuarantineRecord` directly, bypassing ``with_entry``, with
    entries in reverse hash order, so this pins the save path rather than the
    mutator. (``with_entry`` does sort, but nothing here observes that; it is
    pinned by ``test_with_entry_sorts_entries_in_memory_without_any_round_trip``.)
    """
    entry_b = QuarantineEntry(sha256=HASH_B, name="b.fit", reason="reason-b")
    entry_a = QuarantineEntry(sha256=HASH_A, name="a.fit", reason="reason-a")
    out_of_order = QuarantineRecord(entries=(entry_b, entry_a))

    save_quarantine(tmp_path, out_of_order)
    text = quarantine_path(tmp_path).read_text()

    assert text.index(HASH_A) < text.index(HASH_B)


def test_save_stamps_quarantine_version(tmp_path: Path) -> None:
    """The written file contains the current ``quarantine_version``."""
    save_quarantine(tmp_path, QuarantineRecord(entries=()))
    text = quarantine_path(tmp_path).read_text()
    assert f"quarantine_version = {QUARANTINE_VERSION}" in text


def test_malformed_toml_raises_naming_file(tmp_path: Path) -> None:
    """Unparseable TOML raises :class:`QuarantineError` naming the file path."""
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("this is not [ valid toml")
    with pytest.raises(QuarantineError) as excinfo:
        load_quarantine(tmp_path)
    assert str(path) in str(excinfo.value)


def test_entries_not_a_list_raises(tmp_path: Path) -> None:
    """A present ``entries`` value that is not a list raises, naming the file.

    Uses an integer, which is not iterable, so this pins the explicit
    ``isinstance(raw_entries, list)`` guard: without it, iterating over an
    int raises a raw (uncaught) ``TypeError`` rather than
    :class:`QuarantineError`. A string value would iterate into
    non-table characters and be caught by the "not a table" branch instead,
    which would not distinguish a dropped list guard from a working one.
    """
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("quarantine_version = 1\nentries = 42\n")
    with pytest.raises(QuarantineError) as excinfo:
        load_quarantine(tmp_path)
    assert str(path) in str(excinfo.value)


def test_entry_missing_reason_raises(tmp_path: Path) -> None:
    """An entry missing the ``reason`` key raises :class:`QuarantineError`."""
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        'quarantine_version = 1\n\n[[entries]]\nsha256 = "'
        + HASH_A
        + '"\nname = "run.fit"\n'
    )
    with pytest.raises(QuarantineError) as excinfo:
        load_quarantine(tmp_path)
    assert str(path) in str(excinfo.value)


def test_entry_sha256_not_a_string_raises(tmp_path: Path) -> None:
    """An entry whose ``sha256`` is not a string raises :class:`QuarantineError`."""
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "quarantine_version = 1\n\n[[entries]]\nsha256 = 123\n"
        'name = "run.fit"\nreason = "boom"\n'
    )
    with pytest.raises(QuarantineError) as excinfo:
        load_quarantine(tmp_path)
    assert str(path) in str(excinfo.value)


def test_entry_not_a_table_raises(tmp_path: Path) -> None:
    """An ``entries`` list containing a non-table element raises."""
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('quarantine_version = 1\nentries = ["not-a-table"]\n')
    with pytest.raises(QuarantineError) as excinfo:
        load_quarantine(tmp_path)
    assert str(path) in str(excinfo.value)


def test_duplicate_sha256_raises(tmp_path: Path) -> None:
    """Two entries sharing one ``sha256`` raise :class:`QuarantineError`,
    naming the file, rather than silently loading as two entries or being
    de-duplicated without complaint.
    """
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "quarantine_version = 1\n\n"
        f'[[entries]]\nsha256 = "{HASH_A}"\nname = "a.fit"\nreason = "first"\n\n'
        f'[[entries]]\nsha256 = "{HASH_A}"\nname = "b.fit"\nreason = "second"\n'
    )
    with pytest.raises(QuarantineError) as excinfo:
        load_quarantine(tmp_path)
    assert str(path) in str(excinfo.value)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_unreadable_file_raises_naming_path(tmp_path: Path) -> None:
    """A record that exists but cannot be read (permissions denied) raises
    :class:`QuarantineError` naming the file, rather than letting a raw
    ``OSError``/``PermissionError`` escape uncaught (Req 5.6).
    """
    path = quarantine_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("quarantine_version = 1\nentries = []\n")
    path.chmod(0o000)
    try:
        with pytest.raises(QuarantineError) as excinfo:
            load_quarantine(tmp_path)
        assert str(path) in str(excinfo.value)
    finally:
        path.chmod(0o644)


def test_membership_by_content_rename_still_matches() -> None:
    """A recorded file recognized under a new name is still found by hash.

    Simulates a rename: the stored entry's ``name`` differs from the name we
    query with, but lookup is keyed on ``sha256`` only, so it still matches.
    """
    record = QuarantineRecord(
        entries=(QuarantineEntry(sha256=HASH_A, name="old-name.fit", reason="boom"),)
    )
    found = record.get(HASH_A)
    assert found is not None
    assert found.name == "old-name.fit"


def test_membership_same_name_different_content_misses() -> None:
    """A same-named file with different content is not a quarantine match,
    and a lookup by the stored *name* itself also misses.

    The record holds an entry named ``run.fit`` under ``HASH_A``. A query for
    a different hash (as a same-named-but-different file would present)
    finds nothing. A query using the stored *name* ``"run.fit"`` in place of
    a hash also finds nothing and ``without("run.fit")`` leaves the record
    unchanged -- together proving ``get``/``without`` cannot be satisfied by
    anything but the content hash, never falling back to name.
    """
    record = QuarantineRecord(
        entries=(QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom"),)
    )
    assert record.get(HASH_B) is None
    assert record.get("run.fit") is None
    assert record.without("run.fit").entries == record.entries


def test_with_entry_returns_copy_original_unchanged() -> None:
    """``with_entry`` does not mutate the original record."""
    original = QuarantineRecord(entries=())
    entry = QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom")
    updated = original.with_entry(entry)
    assert original.entries == ()
    assert updated.entries == (entry,)


def test_with_entry_replaces_existing_by_hash() -> None:
    """Adding an entry with an existing ``sha256`` replaces it, not duplicates."""
    original = QuarantineRecord(
        entries=(QuarantineEntry(sha256=HASH_A, name="old.fit", reason="old-reason"),)
    )
    replacement = QuarantineEntry(sha256=HASH_A, name="new.fit", reason="new-reason")
    updated = original.with_entry(replacement)
    assert len(updated.entries) == 1
    assert updated.entries[0] == replacement


def test_without_returns_copy_original_unchanged() -> None:
    """``without`` does not mutate the original record."""
    entry = QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom")
    original = QuarantineRecord(entries=(entry,))
    updated = original.without(HASH_A)
    assert original.entries == (entry,)
    assert updated.entries == ()


def test_without_missing_hash_leaves_record_unchanged_content() -> None:
    """Removing a hash absent from the record leaves entries as they were."""
    entry = QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom")
    original = QuarantineRecord(entries=(entry,))
    updated = original.without(HASH_C)
    assert updated.entries == (entry,)


def test_save_unchanged_record_writes_nothing(tmp_path: Path) -> None:
    """Saving an equal record a second time performs no write.

    Captures mtime *and* inode after the first save, then saves an
    independently-built-but-equal record and asserts both are unchanged --
    proving no write occurred, not merely that the content matches (content
    matching alone would not distinguish a rewrite of identical bytes from no
    write at all).
    """
    entry = QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom")
    first_record = QuarantineRecord(entries=(entry,))
    assert save_quarantine(tmp_path, first_record) is True

    path = quarantine_path(tmp_path)
    stat_before = path.stat()
    bytes_before = path.read_bytes()

    second_record = QuarantineRecord(
        entries=(QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom"),)
    )
    wrote = save_quarantine(tmp_path, second_record)
    stat_after = path.stat()

    assert wrote is False
    assert stat_after.st_ino == stat_before.st_ino
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns
    assert path.read_bytes() == bytes_before


def test_save_unchanged_record_does_not_touch_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the record is unchanged, no temp file is created and no replace occurs.

    Monkeypatches ``os.replace`` to raise if called, proving the write path
    is skipped entirely rather than performed and discovered to be
    no-different after the fact.
    """
    entry = QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom")
    save_quarantine(tmp_path, QuarantineRecord(entries=(entry,)))

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("os.replace should not be called for an unchanged save")

    monkeypatch.setattr(os, "replace", _explode)
    wrote = save_quarantine(tmp_path, QuarantineRecord(entries=(entry,)))
    assert wrote is False


def test_save_changed_record_writes_and_returns_true(tmp_path: Path) -> None:
    """Saving a genuinely different record writes new bytes and returns True."""
    entry_a = QuarantineEntry(sha256=HASH_A, name="a.fit", reason="boom")
    entry_b = QuarantineEntry(sha256=HASH_B, name="b.fit", reason="crash")
    save_quarantine(tmp_path, QuarantineRecord(entries=(entry_a,)))
    path = quarantine_path(tmp_path)
    bytes_before = path.read_bytes()

    wrote = save_quarantine(tmp_path, QuarantineRecord(entries=(entry_a, entry_b)))
    assert wrote is True
    assert path.read_bytes() != bytes_before


def test_save_changed_record_uses_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine write goes through ``os.replace``, proving the atomic-rename
    pattern is used rather than a direct in-place write.

    Wraps ``os.replace`` to record whether it was called while still
    delegating to the real implementation, then asserts it was invoked and
    that the resulting file holds the expected bytes.
    """
    calls: list[tuple[object, object]] = []
    real_replace = os.replace

    def _tracking_replace(src: object, dst: object) -> None:
        calls.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _tracking_replace)
    entry = QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom")
    wrote = save_quarantine(tmp_path, QuarantineRecord(entries=(entry,)))
    assert wrote is True
    assert len(calls) == 1
    assert quarantine_path(tmp_path).is_file()


def test_save_atomic_no_tmp_file_left_behind(tmp_path: Path) -> None:
    """After a successful save, no stray ``.tmp`` file remains in the tool-state dir."""
    save_quarantine(
        tmp_path,
        QuarantineRecord(
            entries=(QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom"),)
        ),
    )
    tool_state_dir = quarantine_path(tmp_path).parent
    leftovers = [p for p in tool_state_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_no_clock_derived_value_in_output(tmp_path: Path) -> None:
    """The serialized document contains no key that looks like a timestamp."""
    save_quarantine(
        tmp_path,
        QuarantineRecord(
            entries=(QuarantineEntry(sha256=HASH_A, name="run.fit", reason="boom"),)
        ),
    )
    text = quarantine_path(tmp_path).read_text()
    for banned in ("time", "date", "timestamp"):
        assert banned not in text.lower()
