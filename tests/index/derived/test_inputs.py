"""Tests for exact, stable fingerprints of corpus-producer inputs."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from fitdocs.athlete import load_athlete_inputs
from fitdocs.index.corpus import corpus_snapshot, scan_workout_pages
from fitdocs.index.derived.inputs import (
    digest,
    file_digest,
    page_keys,
    settings_digest,
    workouts_digest,
)
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.producer import CorpusSnapshot
from fitdocs.layout import settings_path
from tests.index.derived.conftest import TODAY, snapshot_of


def _snapshot(root: Path) -> CorpusSnapshot:
    return snapshot_of(root, today=TODAY)


def _workout_pairs(snapshot: CorpusSnapshot) -> list[list[str]]:
    pairs = [[page.path, page.document_fingerprint] for page in snapshot.pages]
    pairs.extend([page.path, page.document_fingerprint] for page in snapshot.left_out)
    return sorted(pairs, key=lambda pair: pair[0])


def _profile_digest(root: Path) -> str:
    return digest({"profile": file_digest(root / "athlete.toml")})


def _stable_inputs(root: Path) -> tuple[CorpusSnapshot, str, str, str]:
    first = _snapshot(root)
    repeat = _snapshot(root)
    first_workouts = workouts_digest(first)
    first_settings = settings_digest(root)
    first_profile = _profile_digest(root)
    assert first_workouts == workouts_digest(repeat)
    assert first_settings == settings_digest(root)
    assert first_profile == _profile_digest(root)
    return first, first_workouts, first_settings, first_profile


def test_unchanged_snapshot_and_canonical_json_are_stable(derived_root: Path) -> None:
    first, first_workouts, _, _ = _stable_inputs(derived_root)
    second = _snapshot(derived_root)
    assert first_workouts == workouts_digest(second)
    left = {"z": "last", "a": "first"}
    right = {"a": "first", "z": "last"}
    assert list(left) != list(right)
    assert digest(left) == digest(right)
    expected = hashlib.sha256(b'{"a":"first","z":"last"}').hexdigest()
    assert digest({"z": "last", "a": "first"}) == expected


def test_workouts_digest_sorts_both_snapshot_collections(derived_root: Path) -> None:
    snapshot = _snapshot(derived_root)
    reversed_snapshot = replace(
        snapshot,
        pages=tuple(reversed(snapshot.pages)),
        left_out=tuple(reversed(snapshot.left_out)),
    )
    assert [page.path for page in reversed_snapshot.pages] != sorted(
        page.path for page in reversed_snapshot.pages
    )
    assert workouts_digest(snapshot) == workouts_digest(reversed_snapshot)
    assert workouts_digest(snapshot) == digest({"workouts": _workout_pairs(snapshot)})


def test_held_page_change_moves_workouts_digest_only(derived_root: Path) -> None:
    before, before_workouts, before_settings, _ = _stable_inputs(derived_root)
    page = before.pages[0]
    path = derived_root / page.path
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    after = _snapshot(derived_root)
    assert before_workouts != workouts_digest(after)
    assert before_settings == settings_digest(derived_root)


def test_left_out_page_change_moves_workouts_digest_and_is_in_snapshot(
    derived_root: Path,
) -> None:
    before, before_workouts, before_settings, _ = _stable_inputs(derived_root)
    left_out = next(
        item for item in before.left_out if item.path.endswith("left-out.md")
    )
    path = derived_root / left_out.path
    assert left_out.path in {item.path for item in before.left_out}
    assert path.is_file()
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    after = _snapshot(derived_root)
    assert before_workouts != workouts_digest(after)
    assert before_settings == settings_digest(derived_root)


def test_settings_change_moves_settings_digest_not_workouts_digest(
    derived_root: Path,
) -> None:
    before, old_workouts, old_settings, _ = _stable_inputs(derived_root)
    path = settings_path(derived_root)
    old_bytes = path.read_bytes()
    new_bytes = old_bytes.replace(
        b"coverage_threshold = 0.7", b"coverage_threshold = 0.8", 1
    )
    assert len(new_bytes) == len(old_bytes)
    assert sum(old != new for old, new in zip(old_bytes, new_bytes, strict=True)) == 1
    path.write_bytes(new_bytes)
    after = _snapshot(derived_root)
    assert old_workouts == workouts_digest(after)
    assert old_settings != settings_digest(derived_root)


def test_athlete_profile_change_is_separate_from_workout_and_settings_inputs(
    derived_root: Path,
) -> None:
    before, old_workouts, old_settings, old_profile = _stable_inputs(derived_root)
    profile = derived_root / "athlete.toml"
    assert profile.is_file()
    old_bytes = profile.read_bytes()
    new_bytes = old_bytes.replace(b"ftp_watts = 999", b"ftp_watts = 998", 1)
    assert len(new_bytes) == len(old_bytes)
    assert sum(old != new for old, new in zip(old_bytes, new_bytes, strict=True)) == 1
    profile.write_bytes(new_bytes)
    after = _snapshot(derived_root)
    assert old_profile != _profile_digest(derived_root)
    assert old_workouts == workouts_digest(after)
    assert old_settings == settings_digest(derived_root)


def test_plan_source_file_digest_changes_independently(derived_root: Path) -> None:
    _, old_workouts, old_settings, old_profile = _stable_inputs(derived_root)
    plan = derived_root / "plans" / "derived.toml"
    assert plan.is_file()
    old_plan = file_digest(plan)
    original = plan.read_bytes()
    changed = original.replace(b"Derived fixture block", b"derived fixture block", 1)
    assert len(changed) == len(original)
    assert sum(old != new for old, new in zip(original, changed, strict=True)) == 1
    plan.write_bytes(changed)
    after = _snapshot(derived_root)
    assert old_plan != file_digest(plan)
    assert old_workouts == workouts_digest(after)
    assert old_settings == settings_digest(derived_root)
    assert old_profile == _profile_digest(derived_root)


def test_adding_and_removing_workout_pages_moves_workouts_digest(
    derived_root: Path,
) -> None:
    before, before_workouts, _, _ = _stable_inputs(derived_root)
    assert before.pages
    source = derived_root / before.pages[0].path
    added = derived_root / "workouts" / "2099-01-01-added.md"
    assert not added.exists()
    added.write_bytes(source.read_bytes().replace(b"2026-", b"2099-", 1))
    with_added = _snapshot(derived_root)
    assert before_workouts != workouts_digest(with_added)
    added.unlink()
    after_removal = _snapshot(derived_root)
    assert before_workouts == workouts_digest(after_removal)


def test_non_engine_files_are_present_but_absent_from_snapshot(
    derived_root: Path,
) -> None:
    workout_dir = derived_root / "workouts"
    agents = workout_dir / "AGENTS.md"
    non_workout = workout_dir / "notes.md"
    outside = derived_root / "notes.md"
    non_markdown = workout_dir / "notes.txt"
    agents.write_text("agent instructions\n", encoding="utf-8")
    non_workout.write_text("---\ntype: note\n---\n", encoding="utf-8")
    outside.write_text("outside workouts\n", encoding="utf-8")
    non_markdown.write_text("not markdown\n", encoding="utf-8")
    snapshot, before, _, _ = _stable_inputs(derived_root)
    paths = {page.path for page in snapshot.pages} | {
        page.path for page in snapshot.left_out
    }
    assert agents.is_file() and "workouts/AGENTS.md" not in paths
    assert non_workout.is_file() and "workouts/notes.md" not in paths
    assert outside.is_file() and "notes.md" not in paths
    assert non_markdown.is_file() and "workouts/notes.txt" not in paths
    for path, old_text, new_text in (
        (agents, b"agent instructions\n", b"agent instructionS\n"),
        (non_workout, b"type: note", b"type: notf"),
        (outside, b"outside workouts\n", b"outside workoutS\n"),
        (non_markdown, b"not markdown\n", b"Not markdown\n"),
    ):
        original = path.read_bytes()
        changed = original.replace(old_text, new_text, 1)
        assert len(changed) == len(original)
        assert sum(old != new for old, new in zip(original, changed, strict=True)) == 1
        path.write_bytes(changed)
        assert workouts_digest(_snapshot(derived_root)) == before
        path.write_bytes(original)


def test_held_status_changes_page_keys_but_not_workouts_digest(
    derived_root: Path,
) -> None:
    scan = scan_workout_pages(derived_root)
    assert scan.pages
    key_to_leave_out = scan.pages[0].page_key
    full = corpus_snapshot(
        derived_root,
        scan,
        today=TODAY,
        athlete_fingerprint=athlete_fingerprint(load_athlete_inputs(derived_root)),
        held=None,
    )
    partial = corpus_snapshot(
        derived_root,
        scan,
        today=TODAY,
        athlete_fingerprint=athlete_fingerprint(load_athlete_inputs(derived_root)),
        held=frozenset(
            page.page_key for page in scan.pages if page.page_key != key_to_leave_out
        ),
    )
    assert any(page.page_key == key_to_leave_out for page in full.pages)
    left_out_page = next(
        page for page in partial.left_out if page.path == scan.pages[0].path
    )
    assert left_out_page.path in {page.path for page in full.pages}
    assert workouts_digest(full) == workouts_digest(partial)
    assert page_keys(full) != page_keys(partial)


def test_file_digest_markers_are_distinct_and_never_raise(tmp_path: Path) -> None:
    absent = tmp_path / "absent"
    directory = tmp_path / "directory"
    directory.mkdir()
    target = tmp_path / "target"
    target.write_bytes(b"target bytes")
    link = tmp_path / "link"
    try:
        link.symlink_to("target")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable: {type(exc).__name__}")
    unreadable = tmp_path / "unreadable"
    unreadable.write_bytes(b"unreadable bytes")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read mode-000 files")
    unreadable.chmod(0)
    try:
        markers = {
            file_digest(absent),
            file_digest(link),
            file_digest(directory),
            file_digest(unreadable),
        }
    finally:
        unreadable.chmod(0o600)
    assert markers == {
        "absent",
        "symlink:target",
        "directory",
        "unreadable:PermissionError",
    }


def test_file_digest_hashes_exact_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "bytes"
    path.write_bytes(b"a\x00b\n")
    assert file_digest(path) == "sha256:" + hashlib.sha256(b"a\x00b\n").hexdigest()


def test_workouts_digest_uses_snapshot_without_reading_live_page_bytes(
    derived_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(derived_root)
    original_digest = workouts_digest(snapshot)
    page_path = derived_root / snapshot.pages[0].path
    page_path.write_bytes(page_path.read_bytes() + b" ")

    def reject_read(_path: Path) -> bytes:
        raise AssertionError("workouts_digest tried to read a file")

    monkeypatch.setattr(Path, "read_bytes", reject_read)
    assert workouts_digest(snapshot) == original_digest


def test_workouts_digest_does_not_glob_the_workout_directory(
    derived_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(derived_root)
    original_digest = workouts_digest(snapshot)

    def reject_glob(_path: Path, _pattern: str) -> object:
        raise AssertionError("workouts_digest tried to glob files")

    monkeypatch.setattr(Path, "glob", reject_glob)
    assert workouts_digest(snapshot) == original_digest


def test_settings_digest_uses_layout_path(derived_root: Path) -> None:
    assert settings_digest(derived_root) == file_digest(settings_path(derived_root))


def test_page_keys_is_exactly_the_held_page_path_map(derived_root: Path) -> None:
    snapshot = _snapshot(derived_root)
    expected = {page.path: page.page_key for page in snapshot.pages}
    assert page_keys(snapshot) == expected
    assert set(page_keys(snapshot)) == {page.path for page in snapshot.pages}
    assert not ({page.path for page in snapshot.left_out} & set(page_keys(snapshot)))
