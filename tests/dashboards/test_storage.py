"""Storage: every filesystem read and write of the dashboards feature.

All paths live under ``tmp_path``. A symlink test builds a real ``outside``
tree that holds what a followed link would reach, and compares that tree's
bytes and ``st_mtime_ns`` before and after.
"""

from __future__ import annotations

import os
import re
import signal
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from fitdocs.contract import is_generated
from fitdocs.dashboards.snapshot import SNAPSHOT_NAME_RE
from fitdocs.dashboards.storage import (
    ASSET_MARK,
    PageFile,
    Refusal,
    asset_rel_path,
    create_snapshot,
    dashboards_root,
    latest_snapshot,
    list_markdown,
    location_refusal,
    read_page,
    read_snapshot,
    remove_stale_images,
    replace_page,
    write_asset,
)
from tests.dashboards._helpers import (
    assert_untouched,
    make_data_root,
    snapshot_of,
    write_page,
)

TMP_NAME = re.compile(r"\.dashboards-.+\.tmp")
NOT_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root reads a mode-000 file",
)
SVG = "<svg>one</svg>\n"
OTHER_SVG = "<svg>two</svg>\n"
MARKED = ASSET_MARK + "\n" + SVG


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def _names(directory: Path) -> list[str]:
    return sorted(entry.name for entry in directory.iterdir())


def _tmp_files(root: Path) -> list[str]:
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.name.startswith(".dashboards-")
    )


class StorageHung(BaseException):
    """Raised by the alarm. Not an ``Exception``, so no ``except OSError`` or
    ``except Exception`` in storage can absorb it and let the call hang again."""


@pytest.fixture(autouse=True)
def _alarm() -> Iterator[None]:
    """Turn a hang (a fifo opened for reading, an endless retry) into a failure."""

    def expired(signum: int, frame: Any) -> None:
        raise StorageHung("storage call did not return within 10 s")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 10)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    data_root = make_data_root(tmp_path)
    (data_root / "dashboards").mkdir()
    return data_root


# -- the path rule -------------------------------------------------------------


def test_asset_path_is_page_and_chart_only() -> None:
    assert asset_rel_path("pace", "weekly-km") == "assets/pace/weekly-km.svg"
    # hyphens move between the two parts without making two names collide
    assert asset_rel_path("a-b", "c") != asset_rel_path("a", "b-c")
    assert asset_rel_path("a-b", "c") == "assets/a-b/c.svg"
    assert asset_rel_path("a", "b-c") == "assets/a/b-c.svg"


@pytest.mark.parametrize(
    ("page", "chart"),
    [
        ("..", "x"),
        ("pace", ".."),
        ("a/b", "x"),
        ("pace", "x/y"),
        ("Pace", "x"),
        ("pace", "X"),
        ("", "x"),
        ("pace", ""),
    ],
)
def test_names_that_are_not_slugs_are_refused_everywhere(
    root: Path, page: str, chart: str
) -> None:
    canary = _write(root / "workouts" / "w.md", "keep")
    before = snapshot_of(root)
    with pytest.raises(ValueError, match="slug"):
        asset_rel_path(page, chart)
    with pytest.raises(ValueError, match="slug"):
        write_asset(root, page, chart, SVG)
    with pytest.raises(ValueError, match="slug"):
        create_snapshot(root, page, chart, lambda n: b"x")
    with pytest.raises(ValueError, match="slug"):
        latest_snapshot(root, page, chart)
    assert canary.read_bytes() == b"keep"
    assert_untouched(before, snapshot_of(root))


def test_mark_is_the_generated_comment_and_dashboards_root_is_below_the_data_root(
    root: Path,
) -> None:
    assert ASSET_MARK == "<!-- fitdocs:generated -->"
    assert is_generated(ASSET_MARK)
    assert dashboards_root(root) == root / "dashboards"


# -- locations -----------------------------------------------------------------


def test_location_refusal_names_each_bad_level(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    exact = {
        "ok": None,
        "absent": None,
        "dashboards-link": "dashboards/ is a symbolic link",
        "dashboards-file": "dashboards/ is not a directory",
        "assets-link": "dashboards/assets/ is a symbolic link",
        "assets-file": "dashboards/assets/ is not a directory",
        "dashboards-fifo": "dashboards/ is not a directory",
        "assets-fifo": "dashboards/assets/ is not a directory",
    }
    for case, expected in exact.items():
        data = make_data_root(tmp_path, f"d-{case}")
        if case != "absent":
            if case == "dashboards-link":
                (data / "dashboards").symlink_to(outside, target_is_directory=True)
            elif case == "dashboards-file":
                _write(data / "dashboards", "x")
            elif case == "dashboards-fifo":
                os.mkfifo(data / "dashboards")
            else:
                (data / "dashboards").mkdir()
                if case == "assets-link":
                    (data / "dashboards" / "assets").symlink_to(
                        outside, target_is_directory=True
                    )
                elif case == "assets-file":
                    _write(data / "dashboards" / "assets", "x")
                elif case == "assets-fifo":
                    os.mkfifo(data / "dashboards" / "assets")
                else:
                    (data / "dashboards" / "assets").mkdir()
        assert location_refusal(data) == expected, case


def _symlinked_layout(tmp_path: Path, level: str) -> tuple[Path, Path]:
    """A root whose ``level`` is a symlink to an ``outside`` tree that holds
    a page, a marked image and a snapshot, so a followed link would work."""
    data = make_data_root(tmp_path)
    outside = tmp_path / "outside"
    if level == "dashboards":
        _write(outside / "pace.md", "# pace\nassets/pace/chart.svg\n")
        _write(outside / "assets" / "pace" / "chart.svg", MARKED)
        _write(outside / "assets" / "pace" / "chart.snapshot-1.json", b"{}\n")
        _write(outside / "assets" / "pace" / "stale.svg", MARKED)
        (data / "dashboards").symlink_to(outside, target_is_directory=True)
    elif level == "assets":
        (data / "dashboards").mkdir()
        _write(data / "dashboards" / "pace.md", "# pace\n")
        _write(outside / "pace" / "chart.svg", MARKED)
        _write(outside / "pace" / "chart.snapshot-1.json", b"{}\n")
        _write(outside / "pace" / "stale.svg", MARKED)
        (data / "dashboards" / "assets").symlink_to(outside, target_is_directory=True)
    else:
        (data / "dashboards" / "assets").mkdir(parents=True)
        _write(data / "dashboards" / "pace.md", "# pace\n")
        _write(outside / "chart.svg", MARKED)
        _write(outside / "chart.snapshot-1.json", b"{}\n")
        _write(outside / "stale.svg", MARKED)
        (data / "dashboards" / "assets" / "pace").symlink_to(
            outside, target_is_directory=True
        )
    return data, outside


LEVEL_MESSAGE = {
    "dashboards": "dashboards/ is a symbolic link",
    "assets": "dashboards/assets/ is a symbolic link",
    "page-directory": "dashboards/assets/pace/ is a symbolic link",
}


@pytest.mark.parametrize("level", ["dashboards", "assets", "page-directory"])
def test_symlinked_level_is_refused_and_never_followed(
    tmp_path: Path, level: str
) -> None:
    data, outside = _symlinked_layout(tmp_path, level)
    before = snapshot_of(outside)
    assert len(before) >= 3

    assert write_asset(data, "pace", "chart", OTHER_SVG) == "foreign"
    with pytest.raises(OSError) as refused:
        create_snapshot(data, "pace", "chart", lambda n: b"new")
    assert str(refused.value) == LEVEL_MESSAGE[level]
    assert read_snapshot(data, "assets/pace/chart.snapshot-1.json") is None
    assert latest_snapshot(data, "pace", "chart") is None
    removed = remove_stale_images(data)
    # only a link at the page directory is skipped alone; the others skip the run
    assert removed == (() if level == "page-directory" else None)

    assert_untouched(before, snapshot_of(outside))


def test_symlinked_dashboards_directory_lists_and_reads_nothing(
    tmp_path: Path,
) -> None:
    data, outside = _symlinked_layout(tmp_path, "dashboards")
    before = snapshot_of(outside)
    assert list_markdown(data) == ()
    assert read_page(data, "pace") is Refusal.SYMLINK
    assert location_refusal(data) == "dashboards/ is a symbolic link"
    assert_untouched(before, snapshot_of(outside))


def test_symlinked_dashboards_directory_refuses_replace_even_if_bytes_match(
    tmp_path: Path,
) -> None:
    data = make_data_root(tmp_path)
    page_path = write_page(data, "pace", "# pace\n")
    page = read_page(data, "pace")
    assert isinstance(page, PageFile)
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside / "pace.md", page.raw)  # identical bytes behind the link
    page_path.unlink()
    page_path.parent.rmdir()
    (data / "dashboards").symlink_to(outside, target_is_directory=True)
    before = snapshot_of(outside)

    with pytest.raises(OSError) as refused:
        replace_page(page, "# changed\n")
    assert str(refused.value) == "dashboards/ is a symbolic link"

    assert_untouched(before, snapshot_of(outside))


# -- listing -------------------------------------------------------------------


def test_list_markdown_names_direct_md_entries_sorted_without_agents(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = root / "dashboards"
    for name in ("z", "a", "Running", "mid-page", "AGENTS-x"):
        _write(d / f"{name}.md", "x")
    _write(d / "AGENTS.md", "declaration")
    _write(d / "notes.txt", "x")
    _write(d / ".md", "no name")
    _write(d / "page.md.bak", "x")
    _write(d / "sub" / "nested.md", "x")
    (d / "folder.md").mkdir()
    (d / "link.md").symlink_to(d / "a.md")
    expected = (
        "AGENTS-x",
        "Running",
        "a",
        "folder",
        "link",
        "mid-page",
        "z",
    )
    real_listdir = os.listdir

    def reversed_listing(path: Any = ".") -> list[str]:
        return sorted(real_listdir(path), reverse=True)

    with monkeypatch.context() as patch:
        patch.setattr(os, "listdir", reversed_listing)
        assert reversed_listing(d) != sorted(real_listdir(d))
        assert list_markdown(root) == expected


def test_list_markdown_of_a_missing_directory_is_empty(root: Path) -> None:
    (root / "dashboards").rmdir()
    assert list_markdown(root) == ()


# -- reading pages -------------------------------------------------------------


def test_read_page_returns_the_bytes_and_text_with_bom_and_crlf(root: Path) -> None:
    raw = "﻿# Pace\r\nπ run\r\n".encode()
    path = _write(root / "dashboards" / "pace.md", raw)
    _write(root / "dashboards" / "other.md", b"other")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    assert page.name == "pace"
    assert page.path == path
    assert page.raw == raw
    assert page.text == "﻿# Pace\r\nπ run\r\n"
    assert page.text.encode("utf-8") == raw


def test_read_page_refusals(root: Path, tmp_path: Path) -> None:
    d = root / "dashboards"
    outside = _write(tmp_path / "outside" / "outside.md", "outside text\n")
    before = snapshot_of(outside.parent)
    (d / "linked.md").symlink_to(outside)
    (d / "folder.md").mkdir()
    _write(d / "latin.md", b"# ok\n\xe9 not utf-8\n")
    _write(d / "fine.md", "fine")

    assert read_page(root, "linked") is Refusal.SYMLINK
    assert read_page(root, "folder") is Refusal.NOT_REGULAR
    assert read_page(root, "latin") is Refusal.NOT_UTF8
    assert read_page(root, "missing") is Refusal.UNREADABLE
    assert isinstance(read_page(root, "fine"), PageFile)
    assert_untouched(before, snapshot_of(outside.parent))


@NOT_ROOT
def test_read_page_without_read_permission_is_unreadable(root: Path) -> None:
    path = _write(root / "dashboards" / "locked.md", "x")
    path.chmod(0)
    try:
        assert read_page(root, "locked") is Refusal.UNREADABLE
    finally:
        path.chmod(0o644)


@pytest.mark.parametrize("name", ["", "a/b", "../x"])
def test_read_page_refuses_names_that_leave_the_directory(
    root: Path, tmp_path: Path, name: str
) -> None:
    _write(tmp_path / "x.md", "outside")
    with pytest.raises(ValueError, match="page name"):
        read_page(root, name)


# -- replacing pages -----------------------------------------------------------


def test_replace_page_writes_exact_bytes_keeping_mode_and_no_temp(root: Path) -> None:
    path = _write(root / "dashboards" / "pace.md", "old\r\n")
    path.chmod(0o640)
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    new_text = "﻿new π\r\nsecond\r\n"
    previous = os.umask(0o022)
    try:
        assert replace_page(page, new_text) == "written"
    finally:
        os.umask(previous)
    assert path.read_bytes() == new_text.encode("utf-8")
    assert path.stat().st_mode & 0o777 == 0o640
    assert _names(root / "dashboards") == ["pace.md"]


def test_replace_page_reports_changed_and_writes_nothing(root: Path) -> None:
    other = _write(root / "dashboards" / "other.md", "untouched")
    path = _write(root / "dashboards" / "pace.md", "version A\n")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    path.write_bytes(b"version B\n")  # same length, different bytes
    before = snapshot_of(root / "dashboards")
    assert other.exists()

    assert replace_page(page, "version C\n") == "changed"

    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert path.read_bytes() == b"version B\n"


def test_replace_page_refuses_a_page_that_became_a_symlink_or_vanished(
    root: Path, tmp_path: Path
) -> None:
    path = _write(root / "dashboards" / "pace.md", "text\n")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    outside = _write(tmp_path / "outside" / "pace.md", page.raw)
    before = snapshot_of(outside.parent)
    path.unlink()
    path.symlink_to(outside)

    with pytest.raises(OSError) as refused:
        replace_page(page, "changed\n")
    assert str(refused.value) == "pace.md is a symbolic link"
    assert_untouched(before, snapshot_of(outside.parent))
    assert path.is_symlink()

    path.unlink()
    with pytest.raises(FileNotFoundError):
        replace_page(page, "changed\n")
    assert not path.exists()
    assert _tmp_files(root) == []


def test_replace_page_refuses_a_page_that_became_a_directory(root: Path) -> None:
    path = _write(root / "dashboards" / "pace.md", "text\n")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    path.unlink()
    path.mkdir()
    _write(path / "inner.txt", "inner")
    before = snapshot_of(root / "dashboards")

    with pytest.raises(OSError) as refused:
        replace_page(page, "changed\n")

    assert str(refused.value) == "pace.md is not a regular file"
    assert_untouched(before, snapshot_of(root / "dashboards"))


@pytest.mark.parametrize("failure", [OSError("disk full"), KeyboardInterrupt()])
def test_failed_page_replace_leaves_the_page_and_no_temp(
    root: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    path = _write(root / "dashboards" / "pace.md", "old\n")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    before = snapshot_of(root / "dashboards")
    seen: list[tuple[list[str], bytes]] = []

    def failing_replace(src: Any, dst: Any) -> None:
        temp = Path(src)
        seen.append(([temp.parent.name, temp.name], temp.read_bytes()))
        assert Path(dst) == path
        raise failure

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(type(failure)):
        replace_page(page, "new\n")
    monkeypatch.undo()

    # the temp file really existed beside the page, holding the new bytes
    assert len(seen) == 1
    assert seen[0][0][0] == "dashboards"
    assert TMP_NAME.fullmatch(seen[0][0][1])
    assert seen[0][1] == b"new\n"
    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert _tmp_files(root) == []


@pytest.mark.parametrize("failure", [OSError("chmod refused"), KeyboardInterrupt()])
def test_failure_while_preparing_the_temp_file_removes_it(
    root: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    _write(root / "dashboards" / "pace.md", "old\n")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)
    before = snapshot_of(root / "dashboards")
    seen: list[str] = []

    def failing_chmod(path: Any, mode: int) -> None:
        seen.append(Path(path).name)
        assert Path(path).exists()
        raise failure

    monkeypatch.setattr(os, "chmod", failing_chmod)
    with pytest.raises(type(failure)):
        replace_page(page, "new\n")
    monkeypatch.undo()

    assert len(seen) == 1
    assert TMP_NAME.fullmatch(seen[0])
    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert _tmp_files(root) == []


def test_cleanup_that_finds_the_temp_already_gone_does_not_mask_the_failure(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(root / "dashboards" / "pace.md", "old\n")
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)

    def replace_that_loses_the_temp(src: Any, dst: Any) -> None:
        os.unlink(src)
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", replace_that_loses_the_temp)
    with pytest.raises(OSError, match="disk full"):
        replace_page(page, "new\n")


def test_temp_name_taken_by_another_file_is_never_opened_or_removed(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root / "dashboards" / "assets" / "pace"
    folder.mkdir(parents=True)
    taken = folder / f".dashboards-{'01' * 8}.tmp"
    outside = _write(tmp_path / "outside" / "target.txt", "target")
    monkeypatch.setattr(os, "urandom", lambda count: b"\x01" * count)

    for occupant in ("file", "link"):
        if occupant == "file":
            _write(taken, "competitor")
        else:
            taken.unlink()
            taken.symlink_to(outside)
        before = snapshot_of(outside.parent)
        before_taken = os.lstat(taken).st_mtime_ns
        with pytest.raises(FileExistsError):
            write_asset(root, "pace", "chart", SVG)
        with pytest.raises(FileExistsError):
            create_snapshot(root, "pace", "chart", _generation_bytes)
        assert_untouched(before, snapshot_of(outside.parent))
        assert os.lstat(taken).st_mtime_ns == before_taken
        assert taken.is_symlink() == (occupant == "link")
    assert _write(taken, "competitor") == taken
    assert _names(folder) == [taken.name]


# -- chart images --------------------------------------------------------------


def test_write_asset_writes_once_then_reports_unchanged(root: Path) -> None:
    assert not (root / "dashboards" / "assets").exists()
    assert write_asset(root, "pace", "weekly-km", SVG) == "written"
    path = root / "dashboards" / "assets" / "pace" / "weekly-km.svg"
    assert path.read_bytes() == MARKED.encode("utf-8")
    assert _names(path.parent) == ["weekly-km.svg"]

    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = snapshot_of(root / "dashboards")
    assert write_asset(root, "pace", "weekly-km", SVG) == "unchanged"
    assert_untouched(before, snapshot_of(root / "dashboards"))

    assert write_asset(root, "pace", "weekly-km", OTHER_SVG) == "written"
    assert path.read_bytes() == (ASSET_MARK + "\n" + OTHER_SVG).encode("utf-8")
    assert _tmp_files(root) == []


def test_new_files_follow_the_umask(root: Path) -> None:
    previous = os.umask(0o022)
    try:
        assert write_asset(root, "pace", "chart", SVG) == "written"
        rel = create_snapshot(root, "pace", "chart", _generation_bytes)
    finally:
        os.umask(previous)
    folder = root / "dashboards" / "assets" / "pace"
    assert (folder / "chart.svg").stat().st_mode & 0o777 == 0o644
    assert (root / "dashboards" / rel).stat().st_mode & 0o777 == 0o644


def test_each_page_and_chart_gets_its_own_image(root: Path) -> None:
    contents = {("pace", "km"): "<svg>1</svg>", ("pace", "hr"): "<svg>2</svg>"}
    contents[("ride", "km")] = "<svg>3</svg>"
    for (page, chart), svg in contents.items():
        assert write_asset(root, page, chart, svg) == "written"
    for (page, chart), svg in contents.items():
        path = root / "dashboards" / asset_rel_path(page, chart)
        assert path.read_text(encoding="utf-8") == f"{ASSET_MARK}\n{svg}"


def test_write_asset_never_overwrites_an_unmarked_file(root: Path) -> None:
    path = _write(
        root / "dashboards" / "assets" / "pace" / "chart.svg", "<svg>mine</svg>\n"
    )
    before = snapshot_of(root / "dashboards")
    assert write_asset(root, "pace", "chart", OTHER_SVG) == "foreign"
    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert path.read_text(encoding="utf-8") == "<svg>mine</svg>\n"


def test_unmarked_file_equal_to_the_new_svg_is_still_foreign(root: Path) -> None:
    _write(root / "dashboards" / "assets" / "pace" / "chart.svg", SVG)
    before = snapshot_of(root / "dashboards")
    assert write_asset(root, "pace", "chart", SVG) == "foreign"
    assert_untouched(before, snapshot_of(root / "dashboards"))


def test_any_marked_image_is_ours_and_is_rewritten_to_the_current_form(
    root: Path,
) -> None:
    folder = root / "dashboards" / "assets" / "pace"
    old_header = _write(folder / "one.svg", "<!-- fitdocs:generated: v0 -->\n" + SVG)
    late_mark = _write(folder / "two.svg", "<svg>t</svg>\n" + ASSET_MARK + "\n")
    assert old_header.read_text(encoding="utf-8").endswith(SVG)

    assert write_asset(root, "pace", "one", SVG) == "written"
    assert write_asset(root, "pace", "two", OTHER_SVG) == "written"

    assert old_header.read_bytes() == MARKED.encode("utf-8")
    assert late_mark.read_bytes() == (ASSET_MARK + "\n" + OTHER_SVG).encode("utf-8")


def test_a_marked_file_that_is_not_utf8_is_foreign(root: Path) -> None:
    _write(
        root / "dashboards" / "assets" / "pace" / "chart.svg",
        b"\xff\xfe\n" + ASSET_MARK.encode() + b"\n<svg/>\n",
    )
    before = snapshot_of(root / "dashboards")
    assert write_asset(root, "pace", "chart", OTHER_SVG) == "foreign"
    assert_untouched(before, snapshot_of(root / "dashboards"))


def test_write_asset_never_follows_a_symlinked_or_directory_image(
    root: Path, tmp_path: Path
) -> None:
    outside = _write(tmp_path / "outside" / "target.svg", MARKED)
    folder = root / "dashboards" / "assets" / "pace"
    folder.mkdir(parents=True)
    (folder / "linked.svg").symlink_to(outside)
    (folder / "folder.svg").mkdir()
    _write(folder / "folder.svg" / "inner.txt", "inner")
    before_outside = snapshot_of(outside.parent)
    before = snapshot_of(root / "dashboards")

    assert write_asset(root, "pace", "linked", OTHER_SVG) == "foreign"
    assert write_asset(root, "pace", "folder", OTHER_SVG) == "foreign"

    assert_untouched(before_outside, snapshot_of(outside.parent))
    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert (folder / "linked.svg").is_symlink()


def test_write_asset_into_a_non_directory_level_is_foreign(root: Path) -> None:
    _write(root / "dashboards" / "assets", "a file")
    before = snapshot_of(root / "dashboards")
    assert write_asset(root, "pace", "chart", SVG) == "foreign"
    assert_untouched(before, snapshot_of(root / "dashboards"))

    page_level = root / "dashboards" / "assets"
    page_level.unlink()
    page_level.mkdir()
    _write(page_level / "pace", "a file")
    before = snapshot_of(root / "dashboards")
    assert write_asset(root, "pace", "chart", SVG) == "foreign"
    assert_untouched(before, snapshot_of(root / "dashboards"))


def test_write_asset_does_not_create_the_dashboards_directory(root: Path) -> None:
    (root / "dashboards").rmdir()
    with pytest.raises(OSError):
        write_asset(root, "pace", "chart", SVG)
    assert _names(root) == []


def test_failed_asset_write_keeps_the_old_image_and_no_temp(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert write_asset(root, "pace", "chart", SVG) == "written"
    path = root / "dashboards" / "assets" / "pace" / "chart.svg"
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = snapshot_of(root / "dashboards")
    temps: list[Path] = []

    def failing_replace(src: Any, dst: Any) -> None:
        temps.append(Path(src))
        assert Path(src).exists()
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="disk full"):
        write_asset(root, "pace", "chart", OTHER_SVG)
    monkeypatch.undo()

    assert len(temps) == 1
    assert temps[0].parent == path.parent
    assert TMP_NAME.fullmatch(temps[0].name)
    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert _tmp_files(root) == []


# -- snapshots -----------------------------------------------------------------


def _generation_bytes(n: int) -> bytes:
    return f"generation {n}\n".encode()


def _snapshot_dir(root: Path) -> Path:
    return root / "dashboards" / "assets" / "pace"


def test_first_snapshot_is_generation_one_and_creates_directories(root: Path) -> None:
    calls: list[int] = []

    def encode_for(n: int) -> bytes:
        calls.append(n)
        return _generation_bytes(n)

    rel = create_snapshot(root, "pace", "weekly-km", encode_for)

    assert rel == "assets/pace/weekly-km.snapshot-1.json"
    assert calls == [1]
    assert (root / "dashboards" / rel).read_bytes() == _generation_bytes(1)
    assert _names(_snapshot_dir(root)) == ["weekly-km.snapshot-1.json"]
    assert SNAPSHOT_NAME_RE.fullmatch(Path(rel).name)


@pytest.mark.parametrize(
    ("present", "expected"),
    [
        ((1, 9), 10),
        ((1, 9, 12), 13),  # a lexical maximum would pick 9 and write 10
        ((2, 11, 3), 12),
    ],
)
def test_next_generation_is_one_past_the_numeric_maximum(
    root: Path, present: tuple[int, ...], expected: int
) -> None:
    folder = _snapshot_dir(root)
    for n in present:
        _write(folder / f"weekly-km.snapshot-{n}.json", f"old {n}")
    _write(folder / "other-chart.snapshot-50.json", "another chart")
    _write(folder / "weekly-km.svg", MARKED)
    _write(folder / "weekly-km.snapshot-007.json", "not a generation")
    _write(root / "dashboards" / "assets" / "ride" / "weekly-km.snapshot-90.json", "p")
    before = snapshot_of(root / "dashboards")

    rel = create_snapshot(root, "pace", "weekly-km", _generation_bytes)

    assert rel == f"assets/pace/weekly-km.snapshot-{expected}.json"
    after = snapshot_of(root / "dashboards")
    new = set(after) - set(before)
    assert new == {rel}
    assert after[rel][0] == _generation_bytes(expected)
    assert {k: v for k, v in after.items() if k != rel} == before


def test_snapshot_never_replaces_a_file_that_appears_at_the_chosen_name(
    root: Path,
) -> None:
    folder = _snapshot_dir(root)
    _write(folder / "weekly-km.snapshot-9.json", "old 9")
    calls: list[int] = []

    def encode_for(n: int) -> bytes:
        calls.append(n)
        if n == 10:  # a competing writer takes the name just before the link
            _write(folder / "weekly-km.snapshot-10.json", "competitor")
        return _generation_bytes(n)

    rel = create_snapshot(root, "pace", "weekly-km", encode_for)

    assert calls == [10, 11]
    assert rel == "assets/pace/weekly-km.snapshot-11.json"
    assert (folder / "weekly-km.snapshot-10.json").read_bytes() == b"competitor"
    assert (folder / "weekly-km.snapshot-11.json").read_bytes() == _generation_bytes(11)
    assert _names(folder) == [
        "weekly-km.snapshot-10.json",
        "weekly-km.snapshot-11.json",
        "weekly-km.snapshot-9.json",
    ]


def test_snapshot_is_made_by_link_from_a_temp_beside_it_never_by_replace(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link
    links: list[tuple[Path, Path, bytes]] = []

    def watching_link(src: Any, dst: Any, **kwargs: Any) -> None:
        links.append((Path(src), Path(dst), Path(src).read_bytes()))
        real_link(src, dst, **kwargs)

    def forbidden_replace(src: Any, dst: Any) -> None:
        raise AssertionError("snapshots are never created with os.replace")

    monkeypatch.setattr(os, "link", watching_link)
    monkeypatch.setattr(os, "replace", forbidden_replace)
    rel = create_snapshot(root, "pace", "weekly-km", _generation_bytes)
    monkeypatch.undo()

    assert len(links) == 1
    src, dst, data = links[0]
    assert src.parent == dst.parent == _snapshot_dir(root)
    assert TMP_NAME.fullmatch(src.name)
    assert dst == root / "dashboards" / rel
    assert data == _generation_bytes(1)
    assert _tmp_files(root) == []


@pytest.mark.parametrize("failure", [OSError("no links here"), KeyboardInterrupt()])
def test_failed_snapshot_creation_leaves_no_temp_and_no_snapshot(
    root: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    folder = _snapshot_dir(root)
    _write(folder / "weekly-km.snapshot-1.json", "old")
    before = snapshot_of(root / "dashboards")

    def failing_link(src: Any, dst: Any, **kwargs: Any) -> None:
        assert Path(src).exists()
        raise failure

    monkeypatch.setattr(os, "link", failing_link)
    with pytest.raises(type(failure)):
        create_snapshot(root, "pace", "weekly-km", _generation_bytes)
    monkeypatch.undo()

    assert_untouched(before, snapshot_of(root / "dashboards"))
    assert _tmp_files(root) == []


def test_snapshot_skips_past_names_taken_by_links_and_directories(root: Path) -> None:
    folder = _snapshot_dir(root)
    folder.mkdir(parents=True)
    (folder / "weekly-km.snapshot-5.json").symlink_to(folder / "nowhere.json")
    (folder / "weekly-km.snapshot-6.json").mkdir()

    rel = create_snapshot(root, "pace", "weekly-km", _generation_bytes)

    assert rel == "assets/pace/weekly-km.snapshot-7.json"
    assert (folder / "weekly-km.snapshot-5.json").is_symlink()


def test_snapshot_into_a_non_directory_level_is_refused(root: Path) -> None:
    _write(root / "dashboards" / "assets", "a file")
    before = snapshot_of(root / "dashboards")
    with pytest.raises(OSError, match="not a directory"):
        create_snapshot(root, "pace", "chart", _generation_bytes)
    assert_untouched(before, snapshot_of(root / "dashboards"))


# -- reading snapshots ---------------------------------------------------------


def test_read_snapshot_returns_bytes_or_none(root: Path, tmp_path: Path) -> None:
    folder = _snapshot_dir(root)
    _write(folder / "chart.snapshot-1.json", b'{"a": 1}\n')
    (folder / "chart.snapshot-3.json").mkdir()
    os.mkfifo(folder / "chart.snapshot-5.json")
    outside = _write(tmp_path / "outside" / "real.json", b"outside")
    (folder / "chart.snapshot-4.json").symlink_to(outside)
    before = snapshot_of(outside.parent)

    assert read_snapshot(root, "assets/pace/chart.snapshot-1.json") == b'{"a": 1}\n'
    assert read_snapshot(root, "assets/pace/chart.snapshot-2.json") is None
    assert read_snapshot(root, "assets/pace/chart.snapshot-3.json") is None
    assert read_snapshot(root, "assets/pace/chart.snapshot-4.json") is None
    assert read_snapshot(root, "assets/pace/chart.snapshot-5.json") is None
    assert_untouched(before, snapshot_of(outside.parent))


@NOT_ROOT
def test_read_snapshot_without_permission_is_none(root: Path) -> None:
    path = _write(_snapshot_dir(root) / "chart.snapshot-1.json", "x")
    path.chmod(0)
    try:
        assert read_snapshot(root, "assets/pace/chart.snapshot-1.json") is None
    finally:
        path.chmod(0o644)


def test_read_snapshot_accepts_only_the_snapshot_path_grammar(root: Path) -> None:
    real = _write(_snapshot_dir(root) / "chart.snapshot-1.json", b"real")
    _write(root / "dashboards" / "pace.md", b"a page")
    _write(_snapshot_dir(root) / "chart.snapshot-01.json", b"zero padded")
    _write(_snapshot_dir(root) / "chart.txt", b"text")
    _write(_snapshot_dir(root) / "Xchart.snapshot-1.json", b"prefixed")
    _write(_snapshot_dir(root) / "chart.snapshot-1.json.bak", b"suffixed")
    _write(root / "dashboards" / "assets" / "chart.snapshot-1.json", b"too shallow")
    _write(root / "dashboards" / "chart.snapshot-1.json", b"one level up")
    _write(root / "dashboards" / "assets" / "Bad_Dir" / "chart.snapshot-1.json", b"bad")
    assert read_snapshot(root, "assets/pace/chart.snapshot-1.json") == b"real"
    reachable = [
        "pace.md",
        "assets/pace/../pace/chart.snapshot-1.json",
        "./assets/pace/chart.snapshot-1.json",
        "assets//pace/chart.snapshot-1.json",
        "assets/pace/chart.snapshot-1.json/",
        "assets/pace/chart.snapshot-01.json",
        "assets/pace/chart.txt",
        "elsewhere/pace/chart.snapshot-1.json",
        "assets/pace/Xchart.snapshot-1.json",
        "assets/pace/chart.snapshot-1.json.bak",
        "assets/Pace/chart.snapshot-1.json",
        "assets/./chart.snapshot-1.json",
        "assets/../chart.snapshot-1.json",
        "assets/Bad_Dir/chart.snapshot-1.json",
        "assets/chart.snapshot-1.json",
        "assets/pace/sub/chart.snapshot-1.json",
        str(real),
        "../dashboards/assets/pace/chart.snapshot-1.json",
        "",
    ]
    for rel in reachable:
        assert read_snapshot(root, rel) is None, rel


# -- latest --------------------------------------------------------------------


def test_latest_snapshot_is_numeric_and_specific_to_page_and_chart(
    root: Path, tmp_path: Path
) -> None:
    folder = _snapshot_dir(root)
    for n in (9, 2, 10):
        _write(folder / f"weekly-km.snapshot-{n}.json", f"g{n}")
    _write(folder / "km.snapshot-4.json", "shorter id")
    _write(folder / "weekly-km.snapshot-11.json.bak", "suffix")
    _write(folder / "weekly-km.snapshot-011.json", "padded")
    _write(folder / "weekly-km.svg", MARKED)
    _write(folder / "x-weekly-km.snapshot-40.json", "prefixed id")
    _write(root / "dashboards" / "assets" / "ride" / "weekly-km.snapshot-60.json", "p")
    outside = _write(tmp_path / "outside.json", "link target")
    (folder / "weekly-km.snapshot-12.json").symlink_to(outside)
    (folder / "weekly-km.snapshot-13.json").mkdir()

    latest = latest_snapshot(root, "pace", "weekly-km")

    assert latest == "assets/pace/weekly-km.snapshot-10.json"
    assert read_snapshot(root, latest) == b"g10"
    assert latest_snapshot(root, "pace", "km") == "assets/pace/km.snapshot-4.json"
    assert latest_snapshot(root, "pace", "absent") is None
    assert latest_snapshot(root, "absent", "weekly-km") is None
    assert latest_snapshot(root, "ride", "weekly-km") == (
        "assets/ride/weekly-km.snapshot-60.json"
    )


def test_latest_snapshot_without_a_dashboards_directory_is_none(root: Path) -> None:
    (root / "dashboards").rmdir()
    assert latest_snapshot(root, "pace", "chart") is None


# -- removing stale images -----------------------------------------------------


def _stale_tree(root: Path, tmp_path: Path) -> dict[str, Any]:
    d = root / "dashboards"
    a = d / "assets"
    _write(
        d / "pace.md",
        "# pace\n<!-- fitdocs:begin:chart:a -->\n![a](assets/pace/a.svg)\n"
        "<!-- fitdocs:end:chart:a -->\nsee assets/other/b.svg\n",
    )
    _write(d / "ride.md", "elsewhere: assets/pace/shared.svg\n")
    _write(d / "sub" / "note.md", "nested, not a page: assets/deep/n.svg\n")
    _write(a / "pace" / "a.svg", MARKED)  # referenced by pace.md
    _write(a / "pace" / "shared.svg", MARKED)  # referenced only by ride.md
    _write(a / "pace" / "b.svg", MARKED)  # only assets/other/b.svg is mentioned
    _write(a / "pace" / "unref.svg", MARKED)  # removed
    _write(a / "pace" / "foreign.svg", "<svg>athlete's</svg>\n")
    _write(a / "pace" / "notes.txt", MARKED)
    _write(a / "pace" / "chart.snapshot-1.json", MARKED)
    _write(a / "deep" / "n.svg", MARKED)  # referenced only from sub/note.md
    _write(a / "solo" / "x.svg", MARKED)  # removed with its directory
    _write(a / "mixed" / "y.svg", MARKED)  # removed, directory stays
    _write(a / "mixed" / "z.snapshot-3.json", "{}\n")
    _write(a / "Bad Dir" / "q.svg", MARKED)
    _write(a / "pace" / "Odd Name.svg", MARKED)
    _write(a / "top.svg", MARKED)
    (a / "empty").mkdir()
    # a markdown file inside assets/ is not a page text
    _write(a / "pace" / "readme.md", "assets/pace/readme-only.svg\n")
    _write(a / "pace" / "readme-only.svg", MARKED)
    outside = _write(tmp_path / "outside" / "ln.md", "assets/ln/r.svg\n")
    (d / "ln.md").symlink_to(outside)
    _write(a / "ln" / "r.svg", MARKED)
    _write(tmp_path / "outside" / "target.svg", MARKED)
    (a / "pace" / "link.svg").symlink_to(tmp_path / "outside" / "target.svg")
    (d / "folder.md").mkdir()
    # files that are not markdown are not page text, whatever they hold
    _write(d / "photo.png", b"\x89PNG\xff\xfe\x00")
    _write(d / "scratch.txt", "assets/pace/unref.svg\n")
    # a linked directory is not walked
    _write(tmp_path / "outside" / "linked" / "ref.md", "assets/linkref/z.svg\n")
    (d / "linkdir").symlink_to(
        tmp_path / "outside" / "linked", target_is_directory=True
    )
    _write(a / "linkref" / "z.svg", MARKED)
    # only dashboards/assets/ is left out of the scan, not any directory so named
    _write(d / "sub" / "assets" / "inner.md", "assets/nested/n2.svg\n")
    _write(a / "nested" / "n2.svg", MARKED)
    # the mark must be a line of UTF-8 text, wherever in the file it stands
    _write(a / "pace" / "binary.svg", ASSET_MARK.encode() + b"\n\xff\xfe<svg/>\n")
    _write(a / "pace" / "late.svg", "<svg>t</svg>\n" + ASSET_MARK + "\n")
    # directory names that sort differently from the paths they form
    _write(a / "a" / "x.svg", MARKED)
    _write(a / "a-b" / "x.svg", MARKED)
    return {"outside": tmp_path / "outside"}


STALE_REMOVED = (
    "assets/a-b/x.svg",
    "assets/a/x.svg",
    "assets/linkref/z.svg",
    "assets/ln/r.svg",
    "assets/mixed/y.svg",
    "assets/pace/b.svg",
    "assets/pace/late.svg",
    "assets/pace/readme-only.svg",
    "assets/pace/unref.svg",
    "assets/solo/x.svg",
)


def test_remove_stale_images_by_global_reference_scan(
    root: Path, tmp_path: Path
) -> None:
    info = _stale_tree(root, tmp_path)
    d = root / "dashboards"
    before = snapshot_of(d)
    before_outside = snapshot_of(info["outside"])

    removed = remove_stale_images(root)

    assert removed == STALE_REMOVED
    after = snapshot_of(d)
    assert set(before) - set(after) == set(STALE_REMOVED)
    assert set(after) <= set(before)
    for name in after:
        assert after[name] == before[name]
    assert_untouched(before_outside, snapshot_of(info["outside"]))
    assert not (d / "assets" / "solo").exists()  # emptied directory removed
    assert (d / "assets" / "mixed").is_dir()  # still holds a snapshot
    assert (d / "assets" / "empty").is_dir()  # was never emptied by a removal
    assert (d / "assets" / "pace" / "link.svg").is_symlink()
    assert _tmp_files(root) == []


def test_remove_stale_images_second_run_removes_nothing(
    root: Path, tmp_path: Path
) -> None:
    _stale_tree(root, tmp_path)
    assert remove_stale_images(root) == STALE_REMOVED
    before = snapshot_of(root / "dashboards")
    assert remove_stale_images(root) == ()
    assert_untouched(before, snapshot_of(root / "dashboards"))


def test_remove_stale_images_skips_everything_when_a_page_is_not_utf8(
    root: Path, tmp_path: Path
) -> None:
    _stale_tree(root, tmp_path)
    _write(root / "dashboards" / "bad.md", b"# ok\n\xe9\n")
    before = snapshot_of(root / "dashboards")
    assert remove_stale_images(root) is None
    assert_untouched(before, snapshot_of(root / "dashboards"))


def test_remove_stale_images_skips_everything_when_a_nested_markdown_is_not_utf8(
    root: Path, tmp_path: Path
) -> None:
    _stale_tree(root, tmp_path)
    _write(root / "dashboards" / "sub" / "deeper" / "bad.md", b"\xff\xfe\x00")
    before = snapshot_of(root / "dashboards")
    assert remove_stale_images(root) is None
    assert_untouched(before, snapshot_of(root / "dashboards"))


@NOT_ROOT
def test_remove_stale_images_skips_everything_when_a_page_cannot_be_read(
    root: Path, tmp_path: Path
) -> None:
    _stale_tree(root, tmp_path)
    locked = _write(root / "dashboards" / "locked.md", "x")
    locked.chmod(0)
    try:
        assert remove_stale_images(root) is None
        assert (root / "dashboards" / "assets" / "pace" / "unref.svg").exists()
    finally:
        locked.chmod(0o644)


def test_remove_stale_images_with_no_assets_or_no_dashboards(root: Path) -> None:
    _write(root / "dashboards" / "pace.md", "page")
    assert remove_stale_images(root) == ()
    (root / "dashboards" / "pace.md").unlink()
    (root / "dashboards").rmdir()
    assert remove_stale_images(root) == ()


def test_remove_stale_images_leaves_a_page_directory_that_is_not_emptied(
    root: Path,
) -> None:
    a = root / "dashboards" / "assets" / "kept"
    _write(a / "gone.svg", MARKED)
    _write(a / "other.txt", "athlete note")
    assert remove_stale_images(root) == ("assets/kept/gone.svg",)
    assert _names(a) == ["other.txt"]


def test_remove_stale_images_ignores_an_assets_path_that_is_a_file(root: Path) -> None:
    _write(root / "dashboards" / "assets", "a file")
    before = snapshot_of(root / "dashboards")
    assert remove_stale_images(root) is None
    assert_untouched(before, snapshot_of(root / "dashboards"))


# -- confinement and consistency across the module -----------------------------


def test_nothing_outside_dashboards_is_touched_by_any_write(root: Path) -> None:
    _write(root / "workouts" / "w.md", "workout")
    _write(root / "AGENTS.md", "root declaration")
    _write(root / ".fitdocs" / "state", "state")
    _write(root / "dashboards" / "pace.md", "page")
    outside_state = {
        name: value
        for name, value in snapshot_of(root).items()
        if not name.startswith("dashboards/")
    }
    page = read_page(root, "pace")
    assert isinstance(page, PageFile)

    assert replace_page(page, "changed page") == "written"
    assert write_asset(root, "pace", "chart", SVG) == "written"
    create_snapshot(root, "pace", "chart", _generation_bytes)
    assert remove_stale_images(root) == ("assets/pace/chart.svg",)

    after = {
        name: value
        for name, value in snapshot_of(root).items()
        if not name.startswith("dashboards/")
    }
    assert after == outside_state
    assert outside_state
    assert _tmp_files(root) == []


def test_every_snapshot_name_storage_creates_matches_the_codec_grammar(
    root: Path,
) -> None:
    got = [
        Path(create_snapshot(root, "pace", "chart", _generation_bytes)).name
        for _ in range(12)
    ]
    matches = [SNAPSHOT_NAME_RE.fullmatch(name) for name in got]
    assert all(matches)
    assert [m.group("generation") for m in matches if m] == [
        str(n) for n in range(1, 13)
    ]
    assert (
        latest_snapshot(root, "pace", "chart") == "assets/pace/chart.snapshot-12.json"
    )


# -- unusual occupants and races -----------------------------------------------


def test_the_declaration_name_is_the_one_the_declaration_writer_uses() -> None:
    from fitdocs.declaration import DECLARATION_FILENAME

    assert DECLARATION_FILENAME == "AGENTS.md"


def test_a_fifo_page_is_not_regular_and_a_fifo_image_is_foreign(root: Path) -> None:
    os.mkfifo(root / "dashboards" / "pipe.md")
    folder = root / "dashboards" / "assets" / "pace"
    folder.mkdir(parents=True)
    os.mkfifo(folder / "chart.svg")
    assert read_page(root, "pipe") is Refusal.NOT_REGULAR
    assert write_asset(root, "pace", "chart", SVG) == "foreign"
    assert remove_stale_images(root) == ()


@NOT_ROOT
def test_an_unreadable_image_is_foreign(root: Path) -> None:
    assert write_asset(root, "pace", "chart", SVG) == "written"
    path = root / "dashboards" / "assets" / "pace" / "chart.svg"
    path.chmod(0)
    try:
        assert write_asset(root, "pace", "chart", OTHER_SVG) == "foreign"
    finally:
        path.chmod(0o644)
    assert path.read_bytes() == MARKED.encode("utf-8")


@NOT_ROOT
def test_remove_stale_images_skips_everything_under_an_unreadable_directory(
    root: Path,
) -> None:
    _write(root / "dashboards" / "assets" / "pace" / "unref.svg", MARKED)
    hidden = root / "dashboards" / "hidden"
    _write(hidden / "refs.md", "assets/pace/unref.svg\n")
    hidden.chmod(0)
    try:
        assert remove_stale_images(root) is None
    finally:
        hidden.chmod(0o755)
    assert (root / "dashboards" / "assets" / "pace" / "unref.svg").exists()


def _lstat_claims_regular(
    monkeypatch: pytest.MonkeyPatch, link: Path, target: Path
) -> None:
    """Simulate a swap: ``lstat`` of ``link`` reports ``target``, a regular file,
    though ``link`` is a symbolic link when it is opened."""
    real_lstat = os.lstat
    assert link.is_symlink()
    assert not target.is_symlink()

    def lying_lstat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if Path(path) == link:
            return real_lstat(target)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lying_lstat)


def test_a_link_swapped_in_after_the_check_is_still_not_followed(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    page_target = _write(outside / "page.md", "target page\n")
    image_target = _write(outside / "image.svg", ASSET_MARK + "\n<svg>t</svg>\n")
    snapshot_target = _write(outside / "s.json", "target snapshot")
    folder = root / "dashboards" / "assets" / "pace"
    folder.mkdir(parents=True)
    page_link = root / "dashboards" / "linked.md"
    image_link = folder / "chart.svg"
    snapshot_link = folder / "chart.snapshot-1.json"
    page_link.symlink_to(page_target)
    image_link.symlink_to(image_target)
    snapshot_link.symlink_to(snapshot_target)
    before = snapshot_of(outside)
    stand_in = PageFile("linked", page_link, page_target.read_bytes(), "target page\n")

    with monkeypatch.context() as patch:
        _lstat_claims_regular(patch, page_link, page_target)
        assert read_page(root, "linked") is Refusal.SYMLINK
        with pytest.raises(OSError):
            replace_page(stand_in, "overwritten\n")
    with monkeypatch.context() as patch:
        _lstat_claims_regular(patch, image_link, image_target)
        assert write_asset(root, "pace", "chart", OTHER_SVG) == "foreign"
    with monkeypatch.context() as patch:
        _lstat_claims_regular(patch, snapshot_link, snapshot_target)
        assert read_snapshot(root, "assets/pace/chart.snapshot-1.json") is None

    assert_untouched(before, snapshot_of(outside))
    assert image_link.is_symlink()
