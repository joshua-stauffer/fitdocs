"""Self-tests for the query test fixtures."""

from pathlib import Path

import pytest

from tests.query.conftest import _REAL_HOME, HomeDirectory


def test_home_dir_is_temporary(home_dir: HomeDirectory) -> None:
    assert Path.home() == home_dir.path
    assert Path.home() != _REAL_HOME


@pytest.mark.parametrize(
    "entry_kind",
    ["file", "directory", "symlink_to_file", "symlink_to_directory", "broken_symlink"],
)
def test_assert_untouched_tracks_contents(
    home_dir: HomeDirectory, entry_kind: str
) -> None:
    home_dir.assert_untouched()
    entry = home_dir.path / "extension-cache"
    if entry_kind == "file":
        entry.write_text("created", encoding="utf-8")
    else:
        if entry_kind == "directory":
            entry.mkdir()
        elif entry_kind == "symlink_to_file":
            target = home_dir.path.parent / "file-target"
            target.write_text("target", encoding="utf-8")
            entry.symlink_to(target)
        elif entry_kind == "symlink_to_directory":
            target = home_dir.path.parent / "directory-target"
            target.mkdir()
            entry.symlink_to(target, target_is_directory=True)
        else:
            entry.symlink_to(home_dir.path.parent / "missing-target")
    assert tuple(home_dir.path.iterdir()) == (entry,)
    with pytest.raises(AssertionError):
        home_dir.assert_untouched()
