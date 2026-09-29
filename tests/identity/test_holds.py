"""Tests for the hold record store (Req 4.7, 4.10, 8.4).

* a saved record re-loads equal, and entries are written sorted by ``sha256``
  even when the record was built unsorted;
* a second save of an unchanged record reports no write and leaves the file's
  mtime as it was (the mtime is set far in the past first, so an unchanged
  value means the file was not replaced);
* each malformed shape raises :class:`HoldRecordError` naming the file, and a
  repeated ``sha256`` is one of them;
* loading an absent record returns an empty record and creates no ``.fitdocs/``.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from fitdocs.identity.holds import (
    HeldSource,
    HoldRecord,
    HoldRecordError,
    load_holds,
    save_holds,
)
from fitdocs.layout import TOOL_STATE_DIR, held_path

_A = "a" * 64
_B = "b" * 64
_C = "c" * 64

_OLD_NS = 1_000_000_000 * 1_000_000_000  # an arbitrary instant long before the run


def _entry(sha: str, tag: str) -> HeldSource:
    return HeldSource(
        sha256=sha,
        name=f"inbox/{tag}.fit",
        candidates=(f"workouts/{tag}-1.md", f"workouts/{tag}-2.md"),
        evidence=("strict", "weak"),
    )


def _unsorted() -> HoldRecord:
    return HoldRecord(entries=(_entry(_C, "c"), _entry(_A, "a"), _entry(_B, "b")))


def test_round_trip_reloads_equal_and_sorted(tmp_path: Path) -> None:
    assert save_holds(tmp_path, _unsorted()) is True
    loaded = load_holds(tmp_path)
    assert loaded == HoldRecord(
        entries=(_entry(_A, "a"), _entry(_B, "b"), _entry(_C, "c"))
    )
    with held_path(tmp_path).open("rb") as handle:
        on_disk = tomllib.load(handle)
    assert [e["sha256"] for e in on_disk["held"]] == [_A, _B, _C]
    assert on_disk["held_version"] == 1


def test_record_helpers(tmp_path: Path) -> None:
    record = _unsorted().with_entry(_entry(_B, "b2"))
    assert [e.sha256 for e in record.entries] == [_A, _B, _C]
    assert record.get(_B) == _entry(_B, "b2")
    assert record.get("d" * 64) is None
    assert [e.sha256 for e in record.without(_A).entries] == [_B, _C]


def test_second_save_reports_no_write_and_keeps_mtime(tmp_path: Path) -> None:
    assert save_holds(tmp_path, _unsorted()) is True
    path = held_path(tmp_path)
    os.utime(path, ns=(_OLD_NS, _OLD_NS))
    assert path.stat().st_mtime_ns == _OLD_NS
    assert save_holds(tmp_path, _unsorted()) is False
    assert path.stat().st_mtime_ns == _OLD_NS
    changed = _unsorted().with_entry(_entry(_A, "a-changed"))
    assert save_holds(tmp_path, changed) is True
    assert path.stat().st_mtime_ns != _OLD_NS


def test_save_replaces_from_a_held_temp_file_beside_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources: list[Path] = []
    real_replace = os.replace

    def _tracking(src: str | Path, dst: str | Path) -> None:
        sources.append(Path(src))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _tracking)
    assert save_holds(tmp_path, _unsorted()) is True
    assert len(sources) == 1
    assert sources[0].parent == held_path(tmp_path).parent
    assert sources[0].name.startswith(".held-")


def _failing_replace(src: str | Path, dst: str | Path) -> None:
    raise OSError("replace failed")


def test_failed_replace_leaves_previous_bytes_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_holds(tmp_path, HoldRecord(entries=(_entry(_A, "a"),)))
    path = held_path(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(os, "replace", _failing_replace)
    with pytest.raises(OSError, match="replace failed"):
        save_holds(tmp_path, _unsorted())
    assert path.read_bytes() == before
    assert [p.name for p in path.parent.iterdir()] == ["held.toml"]


def test_failed_first_save_leaves_no_record_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "replace", _failing_replace)
    with pytest.raises(OSError, match="replace failed"):
        save_holds(tmp_path, _unsorted())
    assert not held_path(tmp_path).exists()
    assert list((tmp_path / TOOL_STATE_DIR).glob(".held-*")) == []


class _FailingHandle:
    """A temp-file handle whose write fails; closes the real descriptor."""

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def __enter__(self) -> _FailingHandle:
        return self

    def __exit__(self, *exc: object) -> None:
        os.close(self._fd)

    def write(self, data: bytes) -> int:
        raise OSError("write failed")


def _failing_fdopen(fd: int, *args: object, **kwargs: object) -> _FailingHandle:
    return _FailingHandle(fd)


def test_failed_write_leaves_previous_bytes_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_holds(tmp_path, HoldRecord(entries=(_entry(_A, "a"),)))
    path = held_path(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(os, "fdopen", _failing_fdopen)
    with pytest.raises(OSError, match="write failed"):
        save_holds(tmp_path, _unsorted())
    assert path.read_bytes() == before
    assert [p.name for p in path.parent.iterdir()] == ["held.toml"]


def test_failed_first_write_leaves_no_record_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "fdopen", _failing_fdopen)
    with pytest.raises(OSError, match="write failed"):
        save_holds(tmp_path, _unsorted())
    assert not held_path(tmp_path).exists()
    assert list((tmp_path / TOOL_STATE_DIR).glob(".held-*")) == []


def test_record_without_a_held_key_loads_empty(tmp_path: Path) -> None:
    _write(tmp_path, "held_version = 1\n")
    assert load_holds(tmp_path) == HoldRecord(entries=())


def test_load_returns_entries_sorted_whatever_the_file_order(tmp_path: Path) -> None:
    _write(tmp_path, _table(_C) + "\n" + _table(_A) + "\n" + _table(_B))
    assert [e.sha256 for e in load_holds(tmp_path).entries] == [_A, _B, _C]


def test_save_leaves_no_temp_file_and_creates_the_directory(tmp_path: Path) -> None:
    assert not (tmp_path / TOOL_STATE_DIR).exists()
    save_holds(tmp_path, _unsorted())
    assert [p.name for p in (tmp_path / TOOL_STATE_DIR).iterdir()] == ["held.toml"]


def test_absent_record_is_empty_and_creates_nothing(tmp_path: Path) -> None:
    assert load_holds(tmp_path) == HoldRecord(entries=())
    assert list(tmp_path.iterdir()) == []


def _write(root: Path, text: str) -> Path:
    path = held_path(root)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def _table(sha: str = _A, extra: str = "") -> str:
    return (
        "[[held]]\n"
        f'sha256 = "{sha}"\nname = "n"\ncandidates = ["p.md"]\nevidence = ["strict"]\n'
        f"{extra}"
    )


def _raw(**fields: str | None) -> str:
    base = {"name": '"n"', "candidates": "[]", "evidence": "[]"} | fields
    lines = ["[[held]]", 'sha256 = "x"']
    lines += [f"{k} = {v}" for k, v in base.items() if v is not None]
    return "\n".join(lines) + "\n"


_MALFORMED = {
    "invalid toml": "held_version = [",
    "held not a list": "held_version = 1\nheld = 3\n",
    "entry not a table": "held_version = 1\nheld = [1]\n",
    "sha256 missing": "[[held]]\nname = 'n'\ncandidates = []\nevidence = []\n",
    "name not a string": _raw(name="4"),
    "candidates not a list": _raw(candidates='"p"'),
    "evidence has a non-string": _raw(evidence="[1]"),
    "evidence missing": _raw(evidence=None),
    "unsupported version": "held_version = 2\n",
    "boolean version": "held_version = true\n",
    "duplicate sha256": _table(_A) + "\n" + _table(_A),
}


@pytest.mark.parametrize("text", list(_MALFORMED.values()), ids=list(_MALFORMED))
def test_malformed_record_raises_naming_the_file(tmp_path: Path, text: str) -> None:
    path = _write(tmp_path, text)
    with pytest.raises(HoldRecordError) as info:
        load_holds(tmp_path)
    assert str(path) in str(info.value)


def test_a_well_formed_record_is_not_flagged(tmp_path: Path) -> None:
    _write(tmp_path, "held_version = 1\n\n" + _table(_A) + "\n" + _table(_B))
    assert [e.sha256 for e in load_holds(tmp_path).entries] == [_A, _B]


def test_unreadable_record_raises_naming_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "held_version = 1\n")
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("permissions are not enforced for this user")
        with pytest.raises(HoldRecordError) as info:
            load_holds(tmp_path)
        assert str(path) in str(info.value)
    finally:
        path.chmod(0o644)
