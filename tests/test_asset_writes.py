"""docio.write_bytes_if_changed: compare, then atomically replace (Req 6.1, 6.2)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from fitdocs import docio

OLD_NS = 1_000_000_000_123_456_789  # an old mtime a rewrite would visibly change


def _temp_leftovers(directory: Path, keep: set[str]) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name not in keep)


def test_identical_bytes_leave_content_and_mtime_untouched(tmp_path: Path) -> None:
    target = tmp_path / "a.svg"
    target.write_bytes(b"same")
    os.utime(target, ns=(OLD_NS, OLD_NS))
    before = target.stat()
    assert before.st_mtime_ns == OLD_NS  # precondition: the old mtime took

    assert docio.write_bytes_if_changed(target, b"same") is False

    after = target.stat()
    assert target.read_bytes() == b"same"
    assert after.st_mtime_ns == OLD_NS
    assert after.st_ino == before.st_ino
    assert _temp_leftovers(tmp_path, {"a.svg"}) == []


def test_changed_bytes_replace_content(tmp_path: Path) -> None:
    target = tmp_path / "a.svg"
    target.write_bytes(b"old")
    os.utime(target, ns=(OLD_NS, OLD_NS))

    assert docio.write_bytes_if_changed(target, b"new bytes") is True

    assert target.read_bytes() == b"new bytes"
    assert target.stat().st_mtime_ns != OLD_NS
    assert _temp_leftovers(tmp_path, {"a.svg"}) == []


def test_changed_bytes_with_same_length_still_replace(tmp_path: Path) -> None:
    target = tmp_path / "a.svg"
    target.write_bytes(b"abcd")

    assert docio.write_bytes_if_changed(target, b"abce") is True
    assert target.read_bytes() == b"abce"


def test_missing_file_is_created(tmp_path: Path) -> None:
    target = tmp_path / "new.svg"
    assert not target.exists()

    assert docio.write_bytes_if_changed(target, b"fresh") is True

    assert target.read_bytes() == b"fresh"
    assert _temp_leftovers(tmp_path, {"new.svg"}) == []


def test_failed_replace_keeps_old_content_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.svg"
    target.write_bytes(b"old")
    seen_temp: list[str] = []

    def boom(src: object, dst: object) -> None:
        # The temp file exists at the moment of failure: the cleanup has work.
        seen_temp.append(Path(str(src)).name)
        assert Path(str(src)).exists()
        raise OSError("replace refused")

    monkeypatch.setattr(docio.os, "replace", boom)

    with pytest.raises(OSError, match="replace refused"):
        docio.write_bytes_if_changed(target, b"new")

    assert len(seen_temp) == 1
    assert seen_temp[0].startswith(".a.svg.") and seen_temp[0].endswith(".tmp")
    assert target.read_bytes() == b"old"
    assert _temp_leftovers(tmp_path, {"a.svg"}) == []


def test_temp_is_hidden_and_in_the_target_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.svg"
    real_replace = os.replace
    sources: list[Path] = []

    def spy(src: str | Path, dst: str | Path) -> None:
        sources.append(Path(src))
        real_replace(src, dst)

    monkeypatch.setattr(docio.os, "replace", spy)

    assert docio.write_bytes_if_changed(target, b"x") is True

    assert [s.parent for s in sources] == [tmp_path]
    assert sources[0].name.startswith(".a.svg.") and sources[0].name.endswith(".tmp")


def test_symlink_is_replaced_and_its_target_untouched(tmp_path: Path) -> None:
    far = tmp_path / "far.bin"
    far.write_bytes(b"far end")
    os.utime(far, ns=(OLD_NS, OLD_NS))
    link = tmp_path / "a.svg"
    link.symlink_to(far)

    assert docio.write_bytes_if_changed(link, b"new") is True

    assert not link.is_symlink()
    assert link.read_bytes() == b"new"
    assert far.read_bytes() == b"far end"
    assert far.stat().st_mtime_ns == OLD_NS


def test_symlink_to_equal_bytes_is_still_replaced(tmp_path: Path) -> None:
    far = tmp_path / "far.bin"
    far.write_bytes(b"equal")
    os.utime(far, ns=(OLD_NS, OLD_NS))
    link = tmp_path / "a.svg"
    link.symlink_to(far)
    assert link.read_bytes() == b"equal"  # a follow-the-link compare would see a match

    assert docio.write_bytes_if_changed(link, b"equal") is True

    assert not link.is_symlink()
    assert link.read_bytes() == b"equal"
    assert far.stat().st_mtime_ns == OLD_NS


def test_dangling_symlink_is_replaced(tmp_path: Path) -> None:
    link = tmp_path / "a.svg"
    link.symlink_to(tmp_path / "nowhere")

    assert docio.write_bytes_if_changed(link, b"x") is True

    assert not link.is_symlink()
    assert link.read_bytes() == b"x"
    assert not (tmp_path / "nowhere").exists()


def test_unreadable_existing_file_counts_as_differs(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root reads mode-000 files")
    target = tmp_path / "a.svg"
    target.write_bytes(b"same")
    target.chmod(0)

    try:
        assert docio.write_bytes_if_changed(target, b"same") is True
    finally:
        target.chmod(0o644)
    assert target.read_bytes() == b"same"


def test_interrupt_from_replace_leaves_old_content_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.svg"
    target.write_bytes(b"old")

    def boom(src: object, dst: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(docio.os, "replace", boom)

    with pytest.raises(KeyboardInterrupt):
        docio.write_bytes_if_changed(target, b"new")

    assert target.read_bytes() == b"old"
    assert _temp_leftovers(tmp_path, {"a.svg"}) == []


def test_write_failure_before_replace_leaves_old_content_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.svg"
    target.write_bytes(b"old")

    def boom(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(docio.os, "fsync", boom)

    with pytest.raises(OSError, match="disk full"):
        docio.write_bytes_if_changed(target, b"new")

    assert target.read_bytes() == b"old"
    assert _temp_leftovers(tmp_path, {"a.svg"}) == []


def test_temp_is_flushed_and_fsynced_in_full_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.svg"
    data = b"payload"
    events: list[tuple[str, int, int | None]] = []
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd: int) -> None:
        st = os.fstat(fd)
        events.append(("fsync", st.st_ino, st.st_size))
        real_fsync(fd)

    def spy_replace(src: str | Path, dst: str | Path) -> None:
        events.append(("replace", os.stat(src).st_ino, None))
        real_replace(src, dst)

    monkeypatch.setattr(docio.os, "fsync", spy_fsync)
    monkeypatch.setattr(docio.os, "replace", spy_replace)

    assert docio.write_bytes_if_changed(target, data) is True

    assert [e[0] for e in events] == ["fsync", "replace"]
    assert events[0][1] == events[1][1]
    assert events[0][2] == len(data)


def test_written_file_mode_follows_the_umask(tmp_path: Path) -> None:
    target = tmp_path / "a.svg"
    old = os.umask(0o002)
    try:
        docio.write_bytes_if_changed(target, b"x")
    finally:
        os.umask(old)

    assert target.stat().st_mode & 0o777 == 0o664


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_fifo_at_path_is_replaced_without_being_read(tmp_path: Path) -> None:
    target = tmp_path / "a.svg"
    os.mkfifo(target)
    result: list[bool] = []

    thread = threading.Thread(
        target=lambda: result.append(docio.write_bytes_if_changed(target, b"data")),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "reading the FIFO blocked"

    assert result == [True]
    assert target.is_file()
    assert target.read_bytes() == b"data"
