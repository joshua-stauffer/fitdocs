"""Freshness measurements reproduce the index refresh's inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import TypeVar, cast
from unittest.mock import Mock

import pytest

from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.index import build, corpus, registry
from fitdocs.index.bookkeeping import Bookkeeping
from fitdocs.index.corpus import CorpusScan, scan_workout_pages
from fitdocs.index.producer import CorpusSnapshot, PageDocument
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.index.store import (
    IndexConnection,
    IndexResult,
    open_index,
    read_bookkeeping,
)
from fitdocs.query.freshness import (
    AthleteDrift,
    CorpusDrift,
    PageDrift,
    athlete_drift,
    corpus_drift,
    corpus_fingerprints,
    current_athlete_fingerprint,
    page_drift,
)
from tests.query._helpers import FIXTURE_TODAY
from tests.query._helpers import copy_indexed_root as copy_indexed_root_helper
from tests.query.conftest import HomeDirectory

FreshnessAssessment = tuple[
    CorpusScan, Bookkeeping, Mapping[str, str | Exception], CorpusDrift
]
T = TypeVar("T")


def _tree_bytes(
    root: Path, index_dir: Path
) -> tuple[tuple[str, str, bytes | str | None], ...]:
    entries = [*root.rglob("*"), *index_dir.rglob("*")]
    snapshot: list[tuple[str, str, bytes | str | None]] = []
    for path in entries:
        if path.is_symlink():
            snapshot.append((str(path), "symlink", path.readlink().as_posix()))
        elif path.is_dir():
            snapshot.append((str(path), "directory", None))
        elif path.is_file():
            snapshot.append((str(path), "file", path.read_bytes()))
    return tuple(sorted(snapshot))


def test_tree_bytes_lists_literal_directory_file_and_symlink_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    index_dir = tmp_path / "index"
    nested = data_root / "nested"
    nested.mkdir(parents=True)
    index_dir.mkdir()
    (nested / "value.bin").write_bytes(b"fixture-data")
    (data_root / "z-last").mkdir()
    (data_root / "a-first").mkdir()
    (data_root / "live-link").symlink_to("nested/value.bin")
    (data_root / "broken-link").symlink_to("missing-target")
    (index_dir / "index.duckdb").write_bytes(b"fixture-index")

    original_rglob = Path.rglob

    def reversed_rglob(path: Path, pattern: str) -> Iterator[Path]:
        return iter(reversed(sorted(original_rglob(path, pattern))))

    raw_paths = tuple(reversed_rglob(data_root, "*"))
    assert raw_paths != tuple(sorted(raw_paths))
    monkeypatch.setattr(Path, "rglob", reversed_rglob)
    entries = _tree_bytes(data_root, index_dir)
    actual = tuple(
        (Path(path).relative_to(tmp_path).as_posix(), kind, content)
        for path, kind, content in entries
    )
    expected = (
        ("data/a-first", "directory", None),
        ("data/broken-link", "symlink", "missing-target"),
        ("data/live-link", "symlink", "nested/value.bin"),
        ("data/nested", "directory", None),
        ("data/nested/value.bin", "file", b"fixture-data"),
        ("data/z-last", "directory", None),
        ("index/index.duckdb", "file", b"fixture-index"),
    )
    assert actual == expected
    assert len(entries) == len(expected)


@pytest.mark.parametrize("changed_root", ["data", "index"])
def test_tree_bytes_changes_for_new_empty_directory(
    tmp_path: Path, changed_root: str
) -> None:
    data_root = tmp_path / "data"
    index_dir = tmp_path / "index"
    data_root.mkdir()
    index_dir.mkdir()
    (data_root / "sentinel").write_bytes(b"data-root")
    (index_dir / "sentinel").write_bytes(b"index-root")
    before = _tree_bytes(data_root, index_dir)
    assert before == (
        (str(data_root / "sentinel"), "file", b"data-root"),
        (str(index_dir / "sentinel"), "file", b"index-root"),
    )

    target_root = data_root if changed_root == "data" else index_dir
    empty_directory = target_root / "assessment-empty-directory"
    assert not empty_directory.exists()
    empty_directory.mkdir()
    assert empty_directory.is_dir()
    assert _tree_bytes(data_root, index_dir) != before


def test_tree_bytes_changes_when_regular_file_bytes_change(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    index_dir = tmp_path / "index"
    data_root.mkdir()
    index_dir.mkdir()
    subject = data_root / "input.bin"
    subject.write_bytes(b"before")
    before = _tree_bytes(data_root, index_dir)
    assert before == ((str(subject), "file", b"before"),)

    subject.write_bytes(b"after")
    assert _tree_bytes(data_root, index_dir) != before


@pytest.mark.parametrize(
    ("link_name", "initial_target", "changed_target"),
    [
        ("live-link", "inside.bin", "another-inside.bin"),
        ("broken-link", "missing-one", "missing-two"),
    ],
)
def test_tree_bytes_changes_when_symlink_target_changes(
    tmp_path: Path, link_name: str, initial_target: str, changed_target: str
) -> None:
    data_root = tmp_path / "data"
    index_dir = tmp_path / "index"
    data_root.mkdir()
    index_dir.mkdir()
    (data_root / "inside.bin").write_bytes(b"target-bytes")
    link = data_root / link_name
    link.symlink_to(initial_target)
    assert link.is_symlink()
    if initial_target.startswith("missing-"):
        assert not link.exists()
    else:
        assert link.exists()
    before = _tree_bytes(data_root, index_dir)
    assert (str(link), "symlink", initial_target) in before

    link.unlink()
    link.symlink_to(changed_target)
    assert _tree_bytes(data_root, index_dir) != before


def _measured(root: Path, index_dir: Path, operation: Callable[[], T]) -> T:
    before = _tree_bytes(root, index_dir)
    result = operation()
    assert _tree_bytes(root, index_dir) == before
    return result


def _bookkeeping(index_dir: Path) -> Bookkeeping:
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        value = read_bookkeeping(conn)
    assert value is not None
    return value


def _copy_page(root: Path, *, name: str, unique_key: bool = False) -> Path:
    pages = sorted((root / "workouts").glob("*.md"))
    assert pages
    target = pages[0].with_name(name)
    shutil.copy2(pages[0], target)
    if unique_key:
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        source_lines = [
            index
            for index, line in enumerate(lines)
            if line.strip().startswith("-") and ".fit" in line
        ]
        assert source_lines
        index = source_lines[-1]
        source = lines[index]
        prefix, _, suffix = source.rpartition("/")
        basename = suffix.strip().strip("\"'")
        assert basename.endswith(".fit")
        lines[index] = f"{prefix}/{('e' * 64)}.fit"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _rebuild(root: Path, index_dir: Path, home: Path, *, rebuild: bool) -> None:
    report = build.run_index_command(
        root,
        environ={"FITDOCS_INDEX_DIR": str(index_dir.parent)},
        home=home,
        athlete=load_athlete_inputs(root),
        today=FIXTURE_TODAY,
        rebuild=rebuild,
        progress=None,
    )
    assert report.outcome.value in {"built", "refreshed", "unchanged"}


def _counts(root: Path, index_dir: Path) -> tuple[int, int, int, int, int]:
    def assess() -> PageDrift:
        scan = scan_workout_pages(root)
        held = _bookkeeping(index_dir).pages
        drift = page_drift(scan, held)
        assert drift.behind is bool(drift.added or drift.changed or drift.removed)
        assert drift.as_mapping() == {
            "workout_pages": drift.workout_pages,
            "pages_held": drift.pages_held,
            "added": drift.added,
            "changed": drift.changed,
            "removed": drift.removed,
            "behind": drift.behind,
        }
        return drift

    drift = _measured(root, index_dir, assess)
    return (
        drift.workout_pages,
        drift.pages_held,
        drift.added,
        drift.changed,
        drift.removed,
    )


def test_page_drift_counts_each_change_on_independent_copies(
    indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    tmp_path: Path,
) -> None:
    source_root, source_index = indexed_root
    home_dir.assert_untouched()
    cases: list[tuple[str, object]] = []
    for label in ("added", "changed", "removed", "renamed", "duplicate"):
        target = tmp_path / f"copy-{label}"
        target.mkdir()
        root, index_dir = copy_indexed_root_helper(source_root, source_index, target)
        home = tmp_path / f"home-{label}"
        home.mkdir()
        cases.append((label, (root, index_dir, home)))

    for label, packed in cases:
        root, index_dir, home = cast(tuple[Path, Path, Path], packed)
        before = _counts(root, index_dir)
        assert before[:2] == (2, 2)
        assert before[2:] == (0, 0, 0)
        if label == "added":
            _copy_page(root, name="zz-added.md", unique_key=True)
            after = _counts(root, index_dir)
            assert after[0] == 3
            assert after[1] == 2
            assert after[2:] == (1, 0, 0)
        elif label == "changed":
            page = next(
                path
                for path in sorted((root / "workouts").glob("*.md"))
                if "effort_time_s: 12345" in path.read_text(encoding="utf-8")
            )
            original = page.read_text(encoding="utf-8")
            assert "effort_time_s: 12345" in original
            page.write_text(
                original.replace("effort_time_s: 12345", "effort_time_s: 12346"),
                encoding="utf-8",
            )
            after = _counts(root, index_dir)
            assert after[0] == 2
            assert after[1] == 2
            assert after[2:] == (0, 1, 0)
        elif label == "removed":
            page = sorted((root / "workouts").glob("*.md"))[0]
            page.unlink()
            after = _counts(root, index_dir)
            assert after[0] == 1
            assert after[1] == 2
            assert after[2:] == (0, 0, 1)
        elif label == "renamed":
            page = sorted((root / "workouts").glob("*.md"))[0]
            page.rename(page.with_name("zz-renamed.md"))
            after = _counts(root, index_dir)
            assert after[0] == 2
            assert after[1] == 2
            assert after[2:] == (0, 1, 0)
        else:
            before_scan = scan_workout_pages(root)
            duplicate = _copy_page(root, name="zz-duplicate.md")
            scan = scan_workout_pages(root)
            assert all(
                item.path != duplicate.relative_to(root).as_posix()
                for item in before_scan.left_out
            )
            assert any(
                item.path == duplicate.relative_to(root).as_posix()
                for item in scan.left_out
            )
            after = _counts(root, index_dir)
            assert after[0] == 2
            assert after[1] == 2
            assert after[2:] == (0, 0, 0)
        if label != "duplicate":
            assert after[0] != before[0] or after[2:] != before[2:]
        _rebuild(root, index_dir, home, rebuild=False)
        assert _counts(root, index_dir)[2:] == (0, 0, 0)
        assert tuple(home.iterdir()) == ()
    home_dir.assert_untouched()


class _FakeCorpus:
    name = "query_test_corpus"
    tables = (
        TableSpec(
            "query_test_rows",
            "One fake corpus table for freshness tests.",
            (ColumnSpec("value", ColumnType.VARCHAR, "Fake value."),),
        ),
    )

    def __init__(self, input_path: Path) -> None:
        self.input_path = input_path
        self.raise_fingerprint = False

    def fingerprint(self, snapshot: CorpusSnapshot) -> str:
        if self.raise_fingerprint:
            raise RuntimeError("cannot fingerprint")
        material = {
            "today": snapshot.today.isoformat(),
            "pages": [(p.path, p.document_fingerprint) for p in snapshot.pages],
            "left_out": [(p.path, p.document_fingerprint) for p in snapshot.left_out],
            "input": self.input_path.read_bytes().hex(),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()

    def rows(self, snapshot: CorpusSnapshot) -> Mapping[str, tuple[tuple[str], ...]]:
        return {"query_test_rows": (("one",),)}


class _FailingDocument:
    name = "query_test_page_failure"
    tables: tuple[TableSpec, ...] = ()

    def __init__(self, path: str) -> None:
        self.path = path

    def rows(self, page: PageDocument) -> Mapping[str, tuple[tuple[object, ...], ...]]:
        if page.path == self.path:
            raise ValueError("selected page failure")
        return {}


def _get_corpus_assessment(root: Path, index_dir: Path) -> FreshnessAssessment:
    before = _tree_bytes(root, index_dir)
    scan = scan_workout_pages(root)
    book = _bookkeeping(index_dir)
    fingerprints = _measured(
        root,
        index_dir,
        lambda: corpus_fingerprints(
            scan,
            book.pages,
            data_root=root,
            today=FIXTURE_TODAY,
            athlete_fingerprint=book.meta.athlete_fingerprint,
        ),
    )
    table_map = {"query_test_corpus": ("query_test_rows",)}
    assessment = (
        scan,
        book,
        fingerprints,
        _measured(
            root,
            index_dir,
            lambda: corpus_drift(fingerprints, book.producers, table_map),
        ),
    )
    assert _tree_bytes(root, index_dir) == before
    return assessment


def test_corpus_freshness_reproduces_refresh_and_reports_movement(
    indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from fitdocs import version

    target = tmp_path / "copy-corpus"
    target.mkdir()
    home_dir.assert_untouched()
    root, index_dir = copy_indexed_root_helper(indexed_root[0], indexed_root[1], target)
    monkeypatch.setattr(version, "tool_version", lambda: "0.0.0+query-test")
    fake = _FakeCorpus(root / "controlled-input.bin")
    fake.input_path.write_bytes(b"v1")
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (fake,))
    assert (fake,) == registry.CORPUS_PRODUCERS
    snapshot_builder = Mock(wraps=corpus.corpus_snapshot)
    monkeypatch.setattr(corpus, "corpus_snapshot", snapshot_builder)
    duplicate = _copy_page(root, name="zz-duplicate.md")
    scan = scan_workout_pages(root)
    assert any(
        item.path == duplicate.relative_to(root).as_posix() for item in scan.left_out
    )
    _rebuild(root, index_dir, home_dir.path, rebuild=True)

    snapshot_calls = snapshot_builder.call_count
    scan, book, fingerprints, drift = _get_corpus_assessment(root, index_dir)
    assert snapshot_builder.call_count == snapshot_calls + 1
    assert scan.left_out
    assert fake.name in book.producers
    assert fingerprints["query_test_corpus"] == book.producers["query_test_corpus"]
    assert drift == CorpusDrift((), ())
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        assert conn.execute("SELECT count(*) FROM query_test_rows").fetchall() == [(1,)]

    fake.input_path.write_bytes(b"v2-moved")
    snapshot_calls = snapshot_builder.call_count
    _, _, moved, moved_drift = _get_corpus_assessment(root, index_dir)
    assert snapshot_builder.call_count == snapshot_calls + 1
    assert moved["query_test_corpus"] != book.producers["query_test_corpus"]
    assert moved_drift.behind == ("query_test_rows",)

    fake.raise_fingerprint = True
    snapshot_calls = snapshot_builder.call_count
    _, _, raised, raised_drift = _get_corpus_assessment(root, index_dir)
    assert snapshot_builder.call_count == snapshot_calls + 1
    assert isinstance(raised["query_test_corpus"], RuntimeError)
    assert raised_drift.unassessed == (
        ("query_test_corpus", "RuntimeError: cannot fingerprint"),
    )
    home_dir.assert_untouched()


def test_failed_page_is_reproduced_as_left_out(
    indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from fitdocs import version

    target = tmp_path / "copy-page-error"
    target.mkdir()
    home_dir.assert_untouched()
    root, index_dir = copy_indexed_root_helper(indexed_root[0], indexed_root[1], target)
    monkeypatch.setattr(version, "tool_version", lambda: "0.0.0+query-test")
    fake = _FakeCorpus(root / "controlled-input.bin")
    fake.input_path.write_bytes(b"stable")
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (fake,))
    _rebuild(root, index_dir, home_dir.path, rebuild=True)

    new_page = _copy_page(root, name="zz-failing-page.md", unique_key=True)
    failing = _FailingDocument(new_page.relative_to(root).as_posix())
    monkeypatch.setattr(
        registry, "DOCUMENT_PRODUCERS", (*registry.DOCUMENT_PRODUCERS, failing)
    )
    _rebuild(root, index_dir, home_dir.path, rebuild=False)
    before_assessment = _tree_bytes(root, index_dir)
    scan = scan_workout_pages(root)
    book = _bookkeeping(index_dir)
    failed_key = next(
        page.page_key
        for page in scan.pages
        if page.path == new_page.relative_to(root).as_posix()
    )
    assert failed_key not in book.pages
    assert any(page.page_key == failed_key for page in scan.pages)

    fingerprints = _measured(
        root,
        index_dir,
        lambda: corpus_fingerprints(
            scan,
            book.pages,
            data_root=root,
            today=FIXTURE_TODAY,
            athlete_fingerprint=book.meta.athlete_fingerprint,
        ),
    )
    drift = _measured(
        root,
        index_dir,
        lambda: corpus_drift(
            fingerprints, book.producers, {fake.name: ("query_test_rows",)}
        ),
    )
    assert drift.behind == ()
    assert _tree_bytes(root, index_dir) == before_assessment
    home_dir.assert_untouched()


def test_athlete_drift_uses_current_profile_and_skips_bad_profile(
    indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    tmp_path: Path,
) -> None:
    target = tmp_path / "copy-athlete"
    target.mkdir()
    home_dir.assert_untouched()
    root, index_dir = copy_indexed_root_helper(indexed_root[0], indexed_root[1], target)
    current = _measured(root, index_dir, lambda: current_athlete_fingerprint(root))
    assert isinstance(current, str)
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        initial = _measured(root, index_dir, lambda: athlete_drift(conn, current))
    assert initial == AthleteDrift(0, None)

    athlete = root / "athlete.toml"
    original = athlete.read_text(encoding="utf-8")
    assert "ftp_watts = 250" in original
    athlete.write_text(
        original.replace("ftp_watts = 250", "ftp_watts = 251"), encoding="utf-8"
    )
    changed = _measured(root, index_dir, lambda: current_athlete_fingerprint(root))
    assert isinstance(changed, str)
    assert changed != current
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        drift = _measured(root, index_dir, lambda: athlete_drift(conn, changed))
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        activities = cast(
            int, conn.execute("SELECT count(*) FROM activities").fetchall()[0][0]
        )
    assert activities > 0
    assert drift == AthleteDrift(activities, None)

    with open_index(index_dir / "index.duckdb", read_only=False) as conn:
        conn.execute("UPDATE activities SET athlete_fingerprint = NULL")
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        null_fingerprints = cast(
            int,
            conn.execute(
                "SELECT count(*) FROM activities WHERE athlete_fingerprint IS NULL"
            ).fetchall()[0][0],
        )
        assert null_fingerprints > 0
        null_drift = _measured(root, index_dir, lambda: athlete_drift(conn, changed))
    assert null_drift == AthleteDrift(null_fingerprints, None)

    athlete.write_text("profile_version = [", encoding="utf-8")
    malformed = _measured(root, index_dir, lambda: current_athlete_fingerprint(root))
    assert isinstance(malformed, AthleteFileError)
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        calls = 0

        class Spy:
            def execute(
                self, sql: str, parameters: tuple[object, ...] = ()
            ) -> IndexResult:
                nonlocal calls
                calls += 1
                return conn.execute(sql, parameters)

        skipped = _measured(
            root,
            index_dir,
            lambda: athlete_drift(cast(IndexConnection, Spy()), malformed),
        )
        assert calls == 0
    assert skipped.skipped_reason == str(malformed)
    assert skipped.activities_other_inputs is None
    home_dir.assert_untouched()


def test_corpus_drift_sorts_tables_and_names_unassessed_producer() -> None:
    got = corpus_drift(
        {"z": "new", "a": "same", "bad": ValueError("broken")},
        {"z": "old", "a": "same", "bad": None},
        {"z": ("z_table", "z_aux"), "a": ("a_table",), "bad": ("b_table",)},
    )
    assert got == CorpusDrift(("z_aux", "z_table"), (("bad", "ValueError: broken"),))
