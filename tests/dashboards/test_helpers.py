"""Self-tests for the shared dashboards helpers."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pytest

from fitdocs.query.command import QueryRequest, run_query
from tests.dashboards._helpers import (
    FakeSource,
    MustNotOpen,
    assert_untouched,
    directive_block,
    query_environment,
    snapshot_of,
)
from tests.dashboards.conftest import IndexedDashboardRoot, copy_dashboard_root


def test_crlf_directive_has_no_bare_line_feed() -> None:
    text = directive_block(
        [("id", "load"), ("sql", "|\n  SELECT 1\n  FROM x")], ending="\r\n"
    )
    assert text.count("\n") == 6
    assert re.search(r"(?<!\r)\n", text) is None
    assert directive_block([("id", "a")]) == "<!-- fitdocs:chart\nid: a\n-->\n"


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_bytes(b"alpha")
    (root / "sub" / "b.md").write_bytes(b"beta")
    return root


def test_snapshot_accepts_an_unchanged_tree(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    before = snapshot_of(root)
    assert set(before) == {"a.md", "sub/b.md"}
    assert_untouched(before, snapshot_of(root))


def test_assert_untouched_fails_on_bytes_only_change(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    target = root / "a.md"
    before = snapshot_of(root)
    stat = target.stat()
    target.write_bytes(b"alphb")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(AssertionError, match="bytes"):
        assert_untouched(before, snapshot_of(root))


def test_assert_untouched_fails_on_mtime_only_change(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    target = root / "a.md"
    before = snapshot_of(root)
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    with pytest.raises(AssertionError, match="st_mtime_ns"):
        assert_untouched(before, snapshot_of(root))


def test_assert_untouched_fails_on_an_added_file(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    before = snapshot_of(root)
    (root / "sub" / "c.md").write_bytes(b"gamma")
    with pytest.raises(AssertionError, match="set of files"):
        assert_untouched(before, snapshot_of(root))


def test_assert_untouched_fails_on_an_empty_before(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AssertionError, match="empty"):
        assert_untouched(snapshot_of(empty), snapshot_of(empty))


def test_fake_source_counts_opens_and_records_misuse() -> None:
    source = FakeSource()
    opener = source.opener()
    assert source.opened == 0
    assert opener() is source and opener() is source
    assert source.opened == 2
    with pytest.raises(AssertionError):
        source.fetch("SELECT 1", today=date(2021, 1, 1), page="p", chart="c", line=1)
    assert source.misused == ["SELECT 1"]


def test_must_not_open_class_counts_attempts() -> None:
    guard = MustNotOpen()
    with pytest.raises(AssertionError):
        guard()
    assert guard.attempts == 1


def test_copy_dashboard_root_is_independent_and_matches_environment(
    indexed_dashboard_root: IndexedDashboardRoot, tmp_path: Path
) -> None:
    shared = indexed_dashboard_root
    copy = copy_dashboard_root(shared, tmp_path)
    assert copy.root != shared.root and copy.root.is_relative_to(tmp_path)
    assert copy.environ["FITDOCS_INDEX_DIR"] != shared.environ["FITDOCS_INDEX_DIR"]
    assert (copy.index_dir / "index.duckdb").is_file()
    assert copy.index_dir.is_relative_to(tmp_path)
    before = snapshot_of(shared.root)
    (copy.root / "scratch.md").write_text("x", encoding="utf-8")
    assert_untouched(before, snapshot_of(shared.root))
    outcome = run_query(
        QueryRequest(
            copy.root, "SELECT count(*) FROM activities", False, 10, 30.0, copy.today
        ),
        query_environment(copy.environ, copy.home),
    )
    assert outcome.result is not None, outcome.kind
    count = outcome.result.rows[0][0]
    assert isinstance(count, int) and count > 0
