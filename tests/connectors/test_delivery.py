"""Pins for delivery into the inbox and the sweep of archived deliveries
(design.md "Delivery layer", Req 6.7, 6.8, 8.1-8.8).

Every sweep fixture that asserts a state change builds the pre-sweep state
explicitly and asserts it is false before calling :func:`sweep`, per the
task boundary: a pending file that exists before removal, an entry that
exists in the ledger before it is forgotten. One fixture
(``test_sweep_never_removes_a_hand_dropped_inbox_file``) also drops a
hand-dropped inbox file the ledger never mentions alongside a real pending
delivery, and asserts that file alone survives the sweep untouched.
"""

from __future__ import annotations

import dataclasses
import hashlib
import tempfile
from pathlib import Path
from typing import Any

import pytest

from fitdocs import layout
from fitdocs.connectors import delivery as delivery_mod
from fitdocs.connectors.delivery import (
    DeliveryResult,
    deliver,
    delivery_name,
    is_fit,
    sweep,
)
from fitdocs.connectors.ledger import Ledger, LedgerEntry, Outcome
from fitdocs.connectors.protocol import RemoteActivity


def _activity(
    *, suggested_name: str | None = None, remote_id: str = "r1"
) -> RemoteActivity:
    return RemoteActivity(
        remote_id=remote_id, original_available=True, suggested_name=suggested_name
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_archive(data_root: Path, data: bytes) -> str:
    sha = _sha(data)
    path = layout.archive_path(data_root, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha


def _pending_entry(
    remote_id: str, *, sha256: str, pending: str, revision: str
) -> LedgerEntry:
    return LedgerEntry(
        remote_id=remote_id,
        outcome=Outcome.DELIVERED,
        revision=revision,
        sha256=sha256,
        pending=pending,
    )


# --- is_fit (Req 6.7) --------------------------------------------------------


def test_is_fit_accepts_a_valid_12_byte_header() -> None:
    # size(1) + protocol(1) + profile(2) + data_size(4) + ".FIT"(4) = 12 bytes
    data = bytes([12, 0x10]) + b"\x00\x00" + b"\x00\x00\x00\x00" + b".FIT"
    assert len(data) == 12
    assert is_fit(data) is True


def test_is_fit_accepts_a_14_byte_header_with_crc() -> None:
    data = bytes([14, 0x10]) + b"\x00\x00" + b"\x00\x00\x00\x00" + b".FIT" + b"\x00\x00"
    assert len(data) == 14
    assert is_fit(data) is True


def test_is_fit_rejects_a_non_fit_payload() -> None:
    data = bytes([12, 0x10]) + b"\x00\x00" + b"\x00\x00\x00\x00" + b"XXXX"
    assert is_fit(data) is False


def test_is_fit_rejects_a_short_payload() -> None:
    data = bytes([12, 0x10]) + b"\x00\x00" + b".FIT"  # 8 bytes total, short of 12
    assert len(data) < 12
    assert is_fit(data) is False


def test_is_fit_rejects_empty_bytes_without_raising() -> None:
    # Below the length guard, `data[0]` would raise IndexError on an empty
    # buffer if the length check were skipped -- this must return False, not crash.
    assert is_fit(b"") is False


def test_is_fit_rejects_an_invalid_header_size_byte() -> None:
    # Otherwise well-formed (right length, correct ".FIT" magic) but byte 0
    # is neither 12 nor 14.
    data = bytes([99, 0x10]) + b"\x00\x00" + b"\x00\x00\x00\x00" + b".FIT"
    assert len(data) == 12
    assert is_fit(data) is False


# --- delivery_name (design.md literal rule) ---------------------------------


@pytest.mark.parametrize(
    ("suggested_name", "remote_id", "expected"),
    [
        # sanitization: disallowed characters -> "-"
        ("weird name!!.fit", "r1", "weird-name--.fit"),
        # leading "." and "-" stripped
        ("...--hidden.fit", "r1", "hidden.fit"),
        # already ends in .fit (any case) -- kept as-is, not doubled
        ("Already.FIT", "r1", "Already.FIT"),
        # empty after sanitization -> "activity"
        ("....----", "r1", "activity.fit"),
        # hint with path components -- only the last component is used
        ("some/nested/dir/leaf-name.fit", "r1", "leaf-name.fit"),
        # no suggested_name -> fall back to remote_id, also with a path shape
        (None, "vendor/12345", "12345.fit"),
        # "!" is outside the allowed charset -> sanitized to "-", which then
        # becomes a *leading* "-" and is stripped
        ("!run", "r1", "run.fit"),
        # a leading space (sanitized to "-") followed by a leading "."
        (" .hidden", "r1", "hidden.fit"),
        # falsy (empty-string) suggested_name must fall back to remote_id,
        # the same as suggested_name=None -- `"" or remote_id` is truthy-or,
        # not an is-None check
        ("", "r9", "r9.fit"),
    ],
)
def test_delivery_name_table(
    suggested_name: str | None, remote_id: str, expected: str
) -> None:
    activity = _activity(suggested_name=suggested_name, remote_id=remote_id)
    assert delivery_name(activity) == expected


def test_delivery_name_caps_the_stem_at_100_characters() -> None:
    long_stem = "a" * 150
    activity = _activity(suggested_name=f"{long_stem}.fit")
    result = delivery_name(activity)
    assert result == ("a" * 100) + ".fit"
    assert len(result) == 104


def test_delivery_name_caps_stem_even_without_an_existing_extension() -> None:
    long_stem = "b" * 150
    activity = _activity(suggested_name=long_stem)
    result = delivery_name(activity)
    assert result == ("b" * 100) + ".fit"


def test_delivery_name_leaves_a_stem_under_the_cap_untruncated() -> None:
    # 98 characters is below the 100-character cap: nothing should be cut.
    stem = "x" * 98
    activity = _activity(suggested_name=f"{stem}.fit")
    result = delivery_name(activity)
    assert result == ("x" * 98) + ".fit"


# --- deliver (Req 8.1-8.4) ---------------------------------------------------


def test_deliver_writes_bytes_unchanged_under_the_instance_subdirectory(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    data = b"fit-bytes-12345"
    sha = _sha(data)

    result = deliver(inbox, "healthfit", "run.fit", data, sha)

    assert result == DeliveryResult(rel="healthfit/run.fit", written=True)
    target = inbox / "healthfit" / "run.fit"
    assert target.is_file()
    assert target.read_bytes() == data


def test_deliver_reuses_an_identical_file_and_writes_nothing(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    data = b"identical-bytes"
    sha = _sha(data)
    directory = inbox / "healthfit"
    directory.mkdir(parents=True)
    existing = directory / "run.fit"
    existing.write_bytes(data)
    before_mtime = existing.stat().st_mtime_ns

    result = deliver(inbox, "healthfit", "run.fit", data, sha)

    assert result == DeliveryResult(rel="healthfit/run.fit", written=False)
    # Nothing else was created in the directory, and the file was not rewritten.
    assert [p.name for p in directory.iterdir()] == ["run.fit"]
    assert existing.stat().st_mtime_ns == before_mtime


def test_deliver_escalates_on_collision_with_different_content(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    directory = inbox / "healthfit"
    directory.mkdir(parents=True)
    old_data = b"old-different-bytes"
    (directory / "run.fit").write_bytes(old_data)

    new_data = b"new-fetched-bytes"
    sha = _sha(new_data)

    result = deliver(inbox, "healthfit", "run.fit", new_data, sha)

    expected_name = f"run-{sha[:8]}.fit"
    assert result == DeliveryResult(rel=f"healthfit/{expected_name}", written=True)
    # The original file at the primary name is untouched.
    assert (directory / "run.fit").read_bytes() == old_data
    assert (directory / expected_name).read_bytes() == new_data


def test_deliver_escalates_past_a_taken_hashed_name_too(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    directory = inbox / "healthfit"
    directory.mkdir(parents=True)
    new_data = b"new-fetched-bytes-2"
    sha = _sha(new_data)
    (directory / "run.fit").write_bytes(b"primary-taken")
    (directory / f"run-{sha[:8]}.fit").write_bytes(b"hashed-name-also-taken")

    result = deliver(inbox, "healthfit", "run.fit", new_data, sha)

    expected_name = f"run-{sha[:8]}-2.fit"
    assert result.rel == f"healthfit/{expected_name}"
    assert (directory / expected_name).read_bytes() == new_data


def test_deliver_escalation_name_preserves_the_stems_case(tmp_path: Path) -> None:
    # The primary name itself is uppercase ("RUN.FIT"); the escalated name
    # must keep that case in the stem while the appended extension is
    # always the literal lowercase ".fit" (see `_escalate`'s docstring).
    inbox = tmp_path / "inbox"
    directory = inbox / "healthfit"
    directory.mkdir(parents=True)
    (directory / "RUN.FIT").write_bytes(b"old-different-bytes")

    new_data = b"new-fetched-bytes-3"
    sha = _sha(new_data)

    result = deliver(inbox, "healthfit", "RUN.FIT", new_data, sha)

    expected_name = f"RUN-{sha[:8]}.fit"
    assert result == DeliveryResult(rel=f"healthfit/{expected_name}", written=True)
    assert (directory / expected_name).read_bytes() == new_data


def test_deliver_escalates_past_a_directory_at_the_primary_name(
    tmp_path: Path,
) -> None:
    # A directory sitting at the primary path is not a file to reuse or
    # overwrite -- deliver must escalate past it and leave it intact.
    inbox = tmp_path / "inbox"
    directory = inbox / "healthfit"
    directory.mkdir(parents=True)
    blocking_dir = directory / "run.fit"
    blocking_dir.mkdir()
    (blocking_dir / "some-child-file").write_text("do not touch")

    new_data = b"new-fetched-bytes-4"
    sha = _sha(new_data)

    result = deliver(inbox, "healthfit", "run.fit", new_data, sha)

    expected_name = f"run-{sha[:8]}.fit"
    assert result == DeliveryResult(rel=f"healthfit/{expected_name}", written=True)
    assert (directory / expected_name).read_bytes() == new_data
    # The directory itself, and its child, are exactly as they were.
    assert blocking_dir.is_dir()
    assert (blocking_dir / "some-child-file").read_text() == "do not touch"


def test_deliver_temp_file_is_dot_prefixed_and_never_ends_in_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    data = b"some-bytes"
    sha = _sha(data)

    captured: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def _spy_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | Path | None = None,
        text: bool = False,
    ) -> tuple[int, str]:
        fd, name = real_mkstemp(suffix=suffix, prefix=prefix, dir=dir, text=text)
        captured.append(Path(name).name)
        return fd, name

    # The atomic writer (_atomic.py) and this test both reference the same
    # `tempfile` module object, so patching it here is visible to both.
    monkeypatch.setattr(tempfile, "mkstemp", _spy_mkstemp)

    deliver(inbox, "healthfit", "run.fit", data, sha)

    assert len(captured) == 1
    tmp_name = captured[0]
    assert tmp_name.startswith(".")
    assert not tmp_name.lower().endswith(".fit")


# --- sweep (Req 8.5-8.8) -----------------------------------------------------


def test_sweep_removes_a_pending_file_whose_hash_matches_the_archive(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    data = b"archived-and-matching"
    sha = _write_archive(data_root, data)

    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    pending_file = pending_dir / "run.fit"
    pending_file.write_bytes(data)
    assert pending_file.is_file()  # false-before-sweep: still present pre-sweep

    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-removed"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ("healthfit/run.fit",)
    assert not pending_file.exists()
    # Removed clears only `pending`: revision, sha256, and outcome survive intact.
    assert result.ledger.get("r1") == dataclasses.replace(entry, pending=None)
    assert result.failures == ()


def test_sweep_leaves_non_pending_ledger_entries_untouched(tmp_path: Path) -> None:
    """A ledger's non-pending entries are never visited by :func:`sweep`.

    ``ledger.entries`` here holds two entries with ``pending is None`` --
    a ``skipped`` entry (no ``sha256``, a required ``detail``) and a
    ``delivered`` entry whose delivery has already been resolved (``sha256``
    set, ``pending`` cleared) -- alongside one real pending entry. Only the
    pending one should move; the other two must come back byte-for-byte
    identical to what went in, proving :func:`sweep` iterates
    ``ledger.pending_entries()`` and not ``ledger.entries``.
    """
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    data = b"the-only-pending-one"
    sha = _write_archive(data_root, data)

    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    (pending_dir / "run.fit").write_bytes(data)

    pending_entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-r2-pending"
    )
    skipped_entry = LedgerEntry(
        remote_id="r2",
        outcome=Outcome.SKIPPED,
        revision="rev-r2-skipped",
        detail="no original available",
    )
    already_resolved_entry = LedgerEntry(
        remote_id="r3",
        outcome=Outcome.DELIVERED,
        revision="rev-r2-resolved",
        sha256=_sha(b"already-resolved-and-archive-absent"),
        pending=None,
    )
    ledger = Ledger(
        connector_id="folder",
        watermark=None,
        entries=(already_resolved_entry, pending_entry, skipped_entry),
    )
    # This entry's own sha256 has no archive file at all -- if sweep ever
    # visited it, there would be nothing to distinguish "leave alone" from
    # "forget" other than the fact that `pending` is already None; asserting
    # equality below is what actually proves it was never touched.
    assert not layout.archive_path(
        data_root,
        already_resolved_entry.sha256,  # type: ignore[arg-type]
    ).is_file()

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ("healthfit/run.fit",)
    assert result.ledger.get("r2") == skipped_entry
    assert result.ledger.get("r3") == already_resolved_entry


def test_sweep_releases_a_pending_file_whose_bytes_differ_from_the_archive(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    archived_data = b"the-archived-bytes"
    sha = _write_archive(data_root, archived_data)

    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    pending_file = pending_dir / "run.fit"
    different_data = b"someone-edited-this-file"
    assert different_data != archived_data
    pending_file.write_bytes(different_data)
    assert pending_file.is_file()

    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-released"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ()
    assert result.failures == ()
    # released, never touched: the file survives with its differing bytes intact
    assert pending_file.is_file()
    assert pending_file.read_bytes() == different_data
    # Released clears only `pending`: revision and sha256 survive intact.
    assert result.ledger.get("r1") == dataclasses.replace(entry, pending=None)


def test_sweep_settles_an_archived_entry_whose_file_has_vanished(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    data = b"moved-by-the-drain"
    sha = _write_archive(data_root, data)
    # No file at the pending path: the drain's move disposition already moved it.
    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-settled"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))
    assert not (inbox / "healthfit" / "run.fit").exists()

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ()
    assert result.failures == ()
    # Settled clears only `pending`: revision and sha256 survive intact.
    assert result.ledger.get("r1") == dataclasses.replace(entry, pending=None)


def test_sweep_leaves_an_unarchived_still_present_file_unchanged(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    # No archive file written at all: this delivery has not been drained yet.
    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    pending_file = pending_dir / "run.fit"
    pending_file.write_bytes(b"not-yet-drained")
    assert pending_file.is_file()

    sha = _sha(b"not-yet-drained")
    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-unchanged"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ()
    assert result.failures == ()
    assert pending_file.is_file()
    # Unchanged: the entry is untouched, byte for byte.
    assert result.ledger.get("r1") == entry


def test_sweep_forgets_an_unarchived_entry_whose_file_is_gone(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    # No archive, no file: the earlier delivery vanished before it was ever drained.
    sha = _sha(b"never-archived")
    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-forgotten"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))
    assert ledger.get("r1") is not None  # false-before-sweep: entry exists pre-sweep
    assert not (inbox / "healthfit" / "run.fit").exists()

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ()
    assert result.failures == ()
    assert result.ledger.get("r1") is None


def test_sweep_reports_a_failed_removal_and_keeps_the_entry_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    data = b"cant-remove-this"
    sha = _write_archive(data_root, data)

    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    pending_file = pending_dir / "run.fit"
    pending_file.write_bytes(data)
    assert pending_file.is_file()

    def _boom(path: Path) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(delivery_mod, "_remove", _boom)

    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-failed"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ()
    assert len(result.failures) == 1
    failed_path, reason = result.failures[0]
    assert failed_path == "healthfit/run.fit"
    assert "permission denied" in reason
    # A failed removal changes nothing about the entry: it stays exactly as it was.
    assert result.ledger.get("r1") == entry
    # The mocked removal never actually happened.
    assert pending_file.is_file()


def test_sweep_never_removes_a_hand_dropped_inbox_file(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    data = b"an-actual-pending-delivery"
    sha = _write_archive(data_root, data)

    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    pending_file = pending_dir / "run.fit"
    pending_file.write_bytes(data)

    # A file dropped by hand into the inbox, never mentioned by the ledger.
    hand_dropped = inbox / "hand-dropped.fit"
    hand_dropped.write_bytes(b"a person put this here")
    assert hand_dropped.is_file()

    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-handdropped"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))

    result = sweep(inbox, data_root, ledger)

    assert result.removed == ("healthfit/run.fit",)
    assert hand_dropped.is_file()
    assert hand_dropped.read_bytes() == b"a person put this here"


def test_sweep_computes_the_hash_only_when_the_archive_copy_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    inbox = tmp_path / "inbox"
    # No archive at all -- an unchanged (not-yet-drained) case.
    pending_dir = inbox / "healthfit"
    pending_dir.mkdir(parents=True)
    pending_file = pending_dir / "run.fit"
    pending_file.write_bytes(b"not-yet-drained-bytes")

    sha = _sha(b"not-yet-drained-bytes")
    entry = _pending_entry(
        "r1", sha256=sha, pending="healthfit/run.fit", revision="rev-hashonly"
    )
    ledger = Ledger(connector_id="folder", watermark=None, entries=(entry,))
    # False-before: the file is genuinely present and the archive genuinely
    # absent going in, so the "archive absent" branch is actually reached.
    assert pending_file.is_file()
    assert not layout.archive_path(data_root, sha).is_file()

    real_sha256 = hashlib.sha256
    calls: list[bytes] = []

    def _spy_sha256(data: bytes = b"") -> Any:
        calls.append(data)
        return real_sha256(data)

    # delivery.py references the same `hashlib` module object via `import hashlib`.
    monkeypatch.setattr(hashlib, "sha256", _spy_sha256)

    sweep(inbox, data_root, ledger)

    assert calls == []  # never hashed the pending file: the archive was absent
