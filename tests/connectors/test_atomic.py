"""Pins for the private atomic-write helper (design.md, AtomicWriter).

``write_atomic`` is a deliberate private copy of the temp-then-replace idiom
(queue item 2026-09-15-atomic-write-helper-copied-per-engine). These tests
pin: the write lands or the old file survives untouched; the temporary file
sits in the target's own directory under a dot-prefixed, per-caller name; the
bytes are flushed and fsynced before the replace; the file is owner-only
(0o600) from write time, even under a permissive umask; and on any failure
the temporary file is removed and the failure propagates.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from fitdocs.connectors._atomic import write_atomic


def test_write_atomic_creates_a_new_file_with_the_given_bytes(tmp_path: Path) -> None:
    target = tmp_path / "state.toml"
    write_atomic(target, b"hello", prefix="widget")
    assert target.read_bytes() == b"hello"


def test_write_atomic_replaces_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "state.toml"
    target.write_bytes(b"old-content")
    write_atomic(target, b"new-content", prefix="widget")
    assert target.read_bytes() == b"new-content"


def test_write_atomic_creates_the_temp_file_in_the_targets_own_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The target sits in a subdirectory of tmp_path, distinct from
    # tempfile.gettempdir() -- so an implementation that passes dir=None to
    # mkstemp (falling back to the system temp directory) is caught rather
    # than coincidentally matching.
    subdir = tmp_path / "state-dir"
    subdir.mkdir()
    target = subdir / "state.toml"
    seen_parents: list[Path] = []
    real_replace = os.replace

    def _spy_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen_parents.append(Path(src).parent)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy_replace)
    write_atomic(target, b"hello", prefix="widget")

    assert seen_parents == [target.parent]


def test_write_atomic_temp_name_is_dot_prefixed_with_the_given_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.toml"
    seen_names: list[str] = []
    real_replace = os.replace

    def _spy_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen_names.append(Path(src).name)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy_replace)
    write_atomic(target, b"hello", prefix="widget")

    assert len(seen_names) == 1
    assert seen_names[0].startswith(".widget-")


def test_write_atomic_uses_a_different_temp_prefix_for_a_different_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two distinct, pairwise-different prefixes must appear verbatim in the
    # replaced source name -- defeats an implementation that ignores the
    # ``prefix`` argument and always uses one fixed literal.
    seen_names: list[str] = []
    real_replace = os.replace

    def _spy_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen_names.append(Path(src).name)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy_replace)
    write_atomic(tmp_path / "a.toml", b"hello", prefix="alpha")
    write_atomic(tmp_path / "b.toml", b"hello", prefix="beta")

    assert seen_names[0].startswith(".alpha-")
    assert seen_names[1].startswith(".beta-")


def test_write_atomic_flushes_before_fsync_so_the_bytes_are_already_on_the_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A BufferedWriter holds small writes in a userspace buffer until
    # flush() (or close()); os.fstat(fd).st_size only reflects the write once
    # it has actually reached the OS-level file. Checking the size exactly
    # when fsync is called (rather than only afterward) means a missing
    # flush() shows up as 0 here, not just as an assertion that fsync ran.
    target = tmp_path / "state.toml"
    data = b"the size observed at fsync time must already equal this length"
    observed_sizes: list[int] = []
    real_fsync = os.fsync

    def _spy_fsync(fd: int) -> None:
        observed_sizes.append(os.fstat(fd).st_size)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _spy_fsync)
    write_atomic(target, data, prefix="widget")

    assert observed_sizes == [len(data)]


def test_write_atomic_mode_is_owner_only_under_a_permissive_umask(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.toml"
    old_umask = os.umask(0)
    try:
        write_atomic(target, b"hello", prefix="widget")
    finally:
        os.umask(old_umask)

    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600


def test_write_atomic_mode_is_owner_only_at_write_time_not_only_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pins the mode exactly when the write call happens, not only on the
    # final target after everything is done -- catches a widen-before/
    # narrow-after window around the write itself (e.g. os.fchmod(fd, 0o644)
    # immediately before writing, then back to 0o600 immediately after),
    # which a check of only the final file's mode cannot see.
    target = tmp_path / "state.toml"
    observed_modes: list[int] = []
    real_fdopen: Any = os.fdopen

    def _spy_fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
        handle = real_fdopen(fd, *args, **kwargs)
        real_write = handle.write

        def _spy_write(data: bytes) -> int:
            observed_modes.append(stat.S_IMODE(os.fstat(handle.fileno()).st_mode))
            result: int = real_write(data)
            return result

        handle.write = _spy_write
        return handle

    monkeypatch.setattr(os, "fdopen", _spy_fdopen)
    write_atomic(target, b"hello", prefix="widget")

    assert observed_modes == [0o600]


def test_write_atomic_failure_leaves_the_old_target_intact_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.toml"
    target.write_bytes(b"old-and-good")

    def _boom(fd: int) -> None:
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(os, "fsync", _boom)

    with pytest.raises(OSError):
        write_atomic(target, b"new-bytes-that-must-not-land", prefix="widget")

    # Falsity in the starting state: the assertion below would also pass if
    # write_atomic silently no-op'd on success, so we already proved above
    # (test_write_atomic_replaces_an_existing_file) that a successful call
    # does change the target's bytes.
    assert target.read_bytes() == b"old-and-good"
    leftovers = [p.name for p in tmp_path.iterdir() if p != target]
    assert leftovers == []


def test_write_atomic_failure_creates_no_target_when_none_existed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.toml"

    def _boom(fd: int) -> None:
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(os, "fsync", _boom)

    with pytest.raises(OSError):
        write_atomic(target, b"data", prefix="widget")

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_atomic_a_failing_replace_leaves_the_old_target_intact_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Distinct from the fsync-failure tests above: this fails inside
    # os.replace itself, which only reds a cleanup that runs for every
    # failure between opening the temp file and success -- not one that
    # covers only the write/fsync steps and leaves replace uncovered.
    target = tmp_path / "state.toml"
    target.write_bytes(b"old-and-good")

    def _boom_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", _boom_replace)

    with pytest.raises(OSError):
        write_atomic(target, b"new-bytes-that-must-not-land", prefix="widget")

    assert target.read_bytes() == b"old-and-good"
    leftovers = [p.name for p in tmp_path.iterdir() if p != target]
    assert leftovers == []


def test_write_atomic_a_non_oserror_failure_still_cleans_up_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # KeyboardInterrupt is not an OSError: a cleanup handler narrowed to
    # `except OSError` would let it through uncleaned. The failure must both
    # leave no temp file behind and still propagate (never be swallowed).
    target = tmp_path / "state.toml"
    target.write_bytes(b"old-and-good")

    def _boom(fd: int) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(os, "fsync", _boom)

    with pytest.raises(KeyboardInterrupt):
        write_atomic(target, b"new-bytes-that-must-not-land", prefix="widget")

    assert target.read_bytes() == b"old-and-good"
    leftovers = [p.name for p in tmp_path.iterdir() if p != target]
    assert leftovers == []
