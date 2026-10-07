"""Self-tests for the query test fixtures."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from fitdocs.athlete import load_athlete_inputs
from fitdocs.index.corpus import scan_workout_pages
from fitdocs.index.location import resolve_index_location
from fitdocs.index.registry import registered_tables
from fitdocs.index.store import IndexOpenError, open_index, read_bookkeeping
from tests.query._helpers import (
    FIXTURE_TODAY,
    DerivedInputs,
    plain_database,
    schema_only_index,
    write_fixture_inputs,
)
from tests.query._helpers import (
    copy_indexed_root as copy_indexed_root_helper,
)
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


def test_indexed_root_has_multi_page_nonempty_core_data(
    indexed_root: tuple[Path, Path], home_dir: HomeDirectory
) -> None:
    _, index_dir = indexed_root
    assert index_dir.resolve() != _REAL_HOME and not index_dir.resolve().is_relative_to(
        _REAL_HOME
    )
    database = index_dir / "index.duckdb"
    with open_index(database, read_only=True) as connection:
        page_count = connection.execute("SELECT count(*) FROM pages").fetchall()[0][0]
        heart_zone_count = connection.execute(
            "SELECT count(*) FROM zone_times WHERE channel = 'heart_rate'"
        ).fetchall()[0][0]
        selected_count = connection.execute(
            "SELECT count(*) FROM loads WHERE selected"
        ).fetchall()[0][0]
        effort_rows = connection.execute(
            "SELECT effort, effort_distance_m, effort_time_s, effort_event "
            "FROM pages WHERE effort IS NOT NULL"
        ).fetchall()
        dates = connection.execute("SELECT date FROM pages").fetchall()
    assert isinstance(page_count, int) and page_count >= 2
    assert isinstance(heart_zone_count, int) and heart_zone_count > 0
    assert isinstance(selected_count, int) and selected_count > 0
    assert len(effort_rows) == 1
    tagged = effort_rows[0]
    assert len({str(value) for value in tagged}) == len(tagged)
    assert tagged == ("race", 42195.0, 12345.0, "Fixture Marathon")
    assert all(isinstance(item[0], date) and item[0] < FIXTURE_TODAY for item in dates)
    home_dir.assert_untouched()


def test_write_fixture_inputs_preserves_base_keys_and_appends_benchmarks(
    tmp_path: Path,
) -> None:
    base = """profile_version = 2
ftp_watts = 250
resting_hr_bpm = 45
max_hr_bpm = 190
hr_zones = [100, 120, 140, 160]
power_zones = [100, 150, 200, 250]
pace_zones = [240, 300, 360, 420]
"""
    root = tmp_path / "root"
    root.mkdir()
    inputs = DerivedInputs(
        files={"plans/plan.toml": "name = 'synthetic'\n"},
        athlete_toml="\n[benchmarks]\nexample = 77\n",
    )
    write_fixture_inputs(root, base, inputs)
    loaded = load_athlete_inputs(root)
    assert loaded is not None
    assert loaded.ftp_watts == 250
    assert loaded.resting_hr_bpm == 45
    assert loaded.max_hr_bpm == 190
    assert loaded.hr_zones is not None
    assert loaded.power_zones is not None
    assert loaded.pace_zones is not None
    assert "[benchmarks]" in (root / "athlete.toml").read_text(encoding="utf-8")
    assert (root / "plans" / "plan.toml").read_text(
        encoding="utf-8"
    ) == "name = 'synthetic'\n"


def test_write_fixture_inputs_refuses_escape_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    with pytest.raises(ValueError):
        write_fixture_inputs(
            root, "profile_version = 2\n", DerivedInputs({"../outside.txt": "x"}, "")
        )
    assert not outside.exists()
    linked = root / "linked"
    linked.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        write_fixture_inputs(
            root,
            "profile_version = 2\n",
            DerivedInputs({"linked/escaped.txt": "x"}, ""),
        )
    assert not outside.exists()
    assert not (linked / "escaped.txt").exists()


def test_plain_database_runs_facade_statements_without_bookkeeping(
    tmp_path: Path, home_dir: HomeDirectory
) -> None:
    database = plain_database(
        tmp_path / "plain.duckdb",
        "CREATE TABLE sample (value INTEGER)",
        "INSERT INTO sample VALUES (19), (23)",
    )
    with open_index(database, read_only=True) as connection:
        assert connection.execute(
            "SELECT value FROM sample ORDER BY value"
        ).fetchall() == [
            (19,),
            (23,),
        ]
        assert read_bookkeeping(connection) is None
    home_dir.assert_untouched()


def test_schema_only_index_has_registered_empty_tables(
    tmp_path: Path, home_dir: HomeDirectory
) -> None:
    database = schema_only_index(tmp_path / "schema.duckdb")
    tables = registered_tables()
    assert len(tables) >= 10
    with open_index(database, read_only=True) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert {table.name for table in tables} <= names
        counts = {
            table.name: connection.execute(
                f'SELECT count(*) FROM "{table.name}"'
            ).fetchall()[0][0]
            for table in tables
        }
    assert set(counts.values()) == {0}
    home_dir.assert_untouched()


def test_copy_indexed_root_copies_wal_when_present(
    indexed_root: tuple[Path, Path], tmp_path: Path
) -> None:
    source_root, source_index_dir = indexed_root
    source_with_wal = tmp_path / "source-index"
    source_with_wal.mkdir()
    # Copy a valid database and a deterministic sidecar from an isolated input.
    source_db = source_with_wal / "index.duckdb"
    source_db.write_bytes((source_index_dir / "index.duckdb").read_bytes())
    wal_payload = b"fixture-wal-sidecar"
    (source_with_wal / "index.duckdb.wal").write_bytes(wal_payload)
    _, copied_index_dir = copy_indexed_root_helper(
        source_root, source_with_wal, tmp_path / "copy-with-wal"
    )
    assert (copied_index_dir / "index.duckdb.wal").read_bytes() == wal_payload


def test_copy_indexed_root_preserves_path_key_and_page_drift(
    indexed_root: tuple[Path, Path], tmp_path: Path, home_dir: HomeDirectory
) -> None:
    source_root, source_index_dir = indexed_root
    before = resolve_index_location(
        source_root, {"FITDOCS_INDEX_DIR": str(source_index_dir.parent)}, tmp_path
    )
    copied_root, copied_index_dir = copy_indexed_root_helper(
        source_root, source_index_dir, tmp_path / "copy"
    )
    after = resolve_index_location(
        copied_root,
        {"FITDOCS_INDEX_DIR": str(copied_index_dir.parent)},
        copied_index_dir.parent.parent / "home",
    )
    assert before.database != after.database
    try:
        connection_context = open_index(after.database, read_only=True)
    except IndexOpenError as error:
        pytest.fail(f"copied index returned NOT_BUILT: {error.fault.kind.value}")
    with connection_context as connection:
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
    snapshot = scan_workout_pages(copied_root)
    assert len(bookkeeping.pages) >= 2
    assert {page.page_key for page in snapshot.pages} == set(bookkeeping.pages)
    assert all(
        page.path == bookkeeping.pages[page.page_key].path
        and page.document_fingerprint
        == bookkeeping.pages[page.page_key].document_fingerprint
        for page in snapshot.pages
    )
    home_dir.assert_untouched()


def test_use_indexed_root_fixture_overwrites_wrong_cache_and_today(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    request.getfixturevalue("indexed_root")
    import fitdocs.cli as cli_module

    wrong_cache = Path("/tmp/not-the-indexed-fixture")
    wrong_today = date(2022, 1, 1)
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(wrong_cache))
    monkeypatch.setattr(cli_module, "_today", lambda: wrong_today)
    assert Path(os.environ["FITDOCS_INDEX_DIR"]) == wrong_cache
    assert cli_module._today() == wrong_today
    assert wrong_today != FIXTURE_TODAY

    root, index_dir = request.getfixturevalue("use_indexed_root")

    assert Path(os.environ["FITDOCS_INDEX_DIR"]) == index_dir.parent
    assert cli_module._today() == FIXTURE_TODAY
    assert (root / "workouts").is_dir()


def test_copy_indexed_root_fixture_returns_independent_relocated_copy(
    request: pytest.FixtureRequest,
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    home_dir: HomeDirectory,
) -> None:
    source_root, source_index_dir = indexed_root
    copied_root, copied_index_dir = request.getfixturevalue("copy_indexed_root")

    assert copied_root != source_root
    assert copied_index_dir != source_index_dir
    expected_location = resolve_index_location(
        tmp_path / "root",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "index-cache")},
        tmp_path / "home",
    )
    assert copied_root == tmp_path / "root"
    assert copied_index_dir == expected_location.directory
    assert copied_root.is_dir() and copied_index_dir.is_dir()
    assert (copied_index_dir / "index.duckdb").is_file()
    assert (copied_root / "fitdocs.toml").read_bytes() == (
        source_root / "fitdocs.toml"
    ).read_bytes()
    assert (copied_index_dir / "index.duckdb").read_bytes() == (
        source_index_dir / "index.duckdb"
    ).read_bytes()

    with open_index(copied_index_dir / "index.duckdb", read_only=True) as connection:
        bookkeeping = read_bookkeeping(connection)
    assert bookkeeping is not None
    assert len(bookkeeping.pages) >= 2
    home_dir.assert_untouched()
