"""Spill ownership and stale query-spill cleanup."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from fitdocs.index import store
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.store import IndexConnection
from fitdocs.query import sandbox
from tests.query.conftest import HomeDirectory

_ROW_COUNT = 3_000_000
# Measured test-contract value, not a derivation of DuckDB's minimum sort
# memory: with the workloads below, a nonempty spill file appears and no
# out-of-memory error occurs in every fresh-process run on duckdb 1.2.0 and
# 1.5.6 at this limit and at 48MB, one step below. Receipts:
# /Users/josh/code/fitdocs-private-evidence/analytics-query-2.3-revision/
# (grid3.jsonl for the sort, matrix-floor.jsonl and matrix-locked.jsonl for
# the window query).
_SPILL_MEMORY_LIMIT = "64MB"
_SORT_SQL = (
    "SELECT i, i * 3 AS tripled FROM spill_rows "
    "ORDER BY (i * 2654435761) % 1000003 DESC, i"
)


# Rows at the two ends of _SORT_SQL's order, derived independently of DuckDB
# by scanning range(_ROW_COUNT) for the extreme keys (ties broken by i ascending).
def _sort_position(i: int) -> tuple[int, int]:
    """Position of row ``i`` under _SORT_SQL: key descending, then i ascending."""
    return (-((i * 2654435761) % 1000003), i)


_SORT_FIRST_ROW = (569_241, 1_707_723)
_SORT_LAST_ROW = (2_000_006, 6_000_018)
_WINDOW_SQL = (
    "SELECT sum(total), max(total), count(*) FROM ("
    "SELECT row_number() OVER (ORDER BY i DESC) AS total FROM spill_rows)"
)


def _nonempty_file_witness(directory: Path) -> tuple[str, int] | None:
    if directory.is_symlink() or not directory.is_dir():
        return None
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            entries = tuple(current.iterdir())
        except (FileNotFoundError, NotADirectoryError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                pending.append(entry)
            elif entry.is_file():
                try:
                    size = entry.stat().st_size
                except FileNotFoundError:
                    continue
                if size > 0:
                    return entry.relative_to(directory).as_posix(), size
    return None


@pytest.fixture(scope="module")
def plain_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[Path, IndexLocation, Path]]:
    base = tmp_path_factory.mktemp("query-spill")
    root = base / "data"
    root.mkdir()
    home = base / "home"
    home.mkdir()
    index_base = base / "index-cache"
    home_was = os.environ.get("HOME")
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setenv("HOME", str(home))
        isolated.setenv("FITDOCS_INDEX_DIR", str(index_base))
        isolated.delenv("XDG_CACHE_HOME", raising=False)
        location = resolve_index_location(
            root, {"FITDOCS_INDEX_DIR": str(index_base)}, home
        )
        location.directory.mkdir(parents=True)
        (root / "fitdocs.toml").write_text(
            "[tiles]\nenabled = false\n", encoding="utf-8"
        )
        with store.create_index(location.database) as connection:
            connection.execute(
                "CREATE TABLE spill_rows AS "
                f"SELECT i::BIGINT AS i FROM range({_ROW_COUNT}) AS rows(i)"
            )
        assert tuple(home.iterdir()) == ()
        yield location.database, location, home
        assert tuple(home.iterdir()) == ()
    assert os.environ.get("HOME") == home_was


@pytest.fixture(autouse=True)
def low_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sandbox,
        "RESOURCE_SETTINGS",
        {
            "memory_limit": _SPILL_MEMORY_LIMIT,
            "threads": 2,
            "max_temp_directory_size": "4GB",
        },
    )


def _open(location: IndexLocation, pid: int | None = None) -> IndexConnection:
    return sandbox.open_sandboxed(
        location,
        pid=os.getpid() if pid is None else pid,
        monotonic=time.monotonic,
        sleep=time.sleep,
        on_wait=lambda _: None,
    )


def test_sorted_query_spills_to_its_process_directory_and_close_removes_it(
    plain_database: tuple[Path, IndexLocation, Path],
    home_dir: HomeDirectory,
) -> None:
    _, location, _ = plain_database
    spill = location.directory / f"query-spill-{os.getpid()}"
    seen = threading.Event()
    stopping = threading.Event()

    def watch() -> None:
        while not stopping.is_set():
            if spill.is_dir():
                seen.set()
            stopping.wait(0.001)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    index_before = _index_inventory(location.directory)
    assert index_before["index.duckdb"][0] == "file"
    assert isinstance(index_before["index.duckdb"][1], bytes)
    assert index_before["index.duckdb"][1]
    connection: IndexConnection | None = None
    try:
        connection = _open(location)
        result = cast(list[tuple[int, int]], connection.execute(_SORT_SQL).fetchall())
        assert len(result) == _ROW_COUNT
        assert result[0] == _SORT_FIRST_ROW
        assert result[-1] == _SORT_LAST_ROW
        assert sum(row[0] for row in result) == _ROW_COUNT * (_ROW_COUNT - 1) // 2
        assert all(row[1] == row[0] * 3 for row in result)
        assert all(0 <= row[0] < _ROW_COUNT for row in result)
        assert all(
            _sort_position(earlier[0]) < _sort_position(later[0])
            for earlier, later in zip(result, result[1:], strict=False)
        )
        assert seen.is_set()
        assert spill.is_dir()
        assert not (location.directory / "index.duckdb.tmp").exists()
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            stopping.set()
            watcher.join(timeout=5)
    assert not watcher.is_alive()
    assert not spill.exists()
    assert not (location.directory / "index.duckdb.tmp").exists()
    assert _index_inventory(location.directory) == index_before
    assert tuple(location.data_root.iterdir()) == (location.data_root / "fitdocs.toml",)
    home_dir.assert_untouched()


def test_four_concurrent_window_spills_match_large_memory_reference(
    plain_database: tuple[Path, IndexLocation, Path],
    home_dir: HomeDirectory,
    tmp_path: Path,
) -> None:
    database, location, _ = plain_database
    reference = store.open_index(
        database,
        read_only=True,
        settings={
            "memory_limit": "1GB",
            "threads": 2,
            "max_temp_directory_size": "4GB",
            "temp_directory": str(location.directory / "query-spill-reference"),
        },
    )
    try:
        expected = reference.execute(_WINDOW_SQL).fetchall()
    finally:
        reference.close()
    total, maximum, row_count = cast(tuple[int, int, int], expected[0])
    assert total > 0
    assert maximum > 0
    assert row_count == _ROW_COUNT
    index_before = _index_inventory(location.directory)
    assert index_before["index.duckdb"][0] == "file"
    assert isinstance(index_before["index.duckdb"][1], bytes)
    assert index_before["index.duckdb"][1]

    coordination = tmp_path / "concurrent-window-coordination"
    coordination.mkdir()
    child = """
import os
import sys
import time
from pathlib import Path
from fitdocs.index.location import resolve_index_location
from fitdocs.query import sandbox
root, base, home, coordination = map(Path, sys.argv[1:5])
memory_limit = sys.argv[5]
os.environ['HOME'] = str(home)
location = resolve_index_location(
    root, {'FITDOCS_INDEX_DIR': str(base)}, home
)
sandbox.RESOURCE_SETTINGS = {
    'memory_limit': memory_limit,
    'threads': 2,
    'max_temp_directory_size': '4GB',
}
connection = sandbox.open_sandboxed(
    location,
    pid=os.getpid(),
    monotonic=time.monotonic,
    sleep=time.sleep,
    on_wait=lambda _: None,
)
try:
    query = sys.stdin.read()
    (coordination / f'ready-{os.getpid()}').write_text('ready', encoding='ascii')
    deadline = time.monotonic() + 60
    while not (coordination / 'release').exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('parent did not release concurrent query barrier')
        time.sleep(0.001)
    (coordination / f'active-{os.getpid()}').write_text('active', encoding='ascii')
    started = time.monotonic_ns()
    row = connection.execute(query).fetchall()[0]
    finished = time.monotonic_ns()
    (coordination / f'end-{os.getpid()}').write_text(str(finished), encoding='ascii')
    print(f'{started},{finished},' + ','.join(map(str, row)))
finally:
    connection.close()
"""
    processes: list[subprocess.Popen[str]] = []
    child_homes = [tmp_path / f"child-home-{ordinal}" for ordinal in range(4)]
    for child_home in child_homes:
        child_home.mkdir()
    watching = threading.Event()
    observed: set[Path] = set()
    simultaneous_witnesses: list[tuple[int, tuple[tuple[str, str, int], ...]]] = []
    spill_paths: dict[int, Path] = {}

    def watch_process_spills() -> None:
        while not watching.is_set():
            observed.update(location.directory.glob("query-spill-*"))
            if len(spill_paths) == 4:
                active = all(
                    (coordination / f"active-{pid}").is_file()
                    and not (coordination / f"end-{pid}").exists()
                    for pid in spill_paths
                )
                if active and all(path.is_dir() for path in spill_paths.values()):
                    witnesses = []
                    witnessed_files: dict[int, tuple[str, int]] = {}
                    for pid in sorted(spill_paths):
                        directory = spill_paths[pid]
                        witness = _nonempty_file_witness(directory)
                        if witness is not None:
                            relative, size = witness
                            witnesses.append((directory.name, relative, size))
                            witnessed_files[pid] = (relative, size)
                    if len(witnesses) == 4:
                        witness_time = time.monotonic_ns()
                        all_end_markers_absent = all(
                            not (coordination / f"end-{pid}").exists()
                            for pid in spill_paths
                        )
                        try:
                            all_payloads_still_present = all(
                                not (
                                    candidate := spill_paths[pid] / relative
                                ).is_symlink()
                                and candidate.is_file()
                                and candidate.stat().st_size == size
                                for pid, (relative, size) in witnessed_files.items()
                            )
                        except (FileNotFoundError, NotADirectoryError):
                            all_payloads_still_present = False
                        if (
                            all_end_markers_absent
                            and all_payloads_still_present
                            and all(path.is_dir() for path in spill_paths.values())
                        ):
                            simultaneous_witnesses.append(
                                (witness_time, tuple(witnesses))
                            )
            watching.wait(0.001)

    watcher = threading.Thread(target=watch_process_spills, daemon=True)
    watcher.start()
    try:
        for child_home in child_homes:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        child,
                        str(location.data_root),
                        str(location.base_dir),
                        str(child_home),
                        str(coordination),
                        _SPILL_MEMORY_LIMIT,
                    ],
                    env={**os.environ, "HOME": str(child_home)},
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        spill_paths = {
            process.pid: location.directory / f"query-spill-{process.pid}"
            for process in processes
        }
        # Feed and close every input before waiting on any child result.
        for process in processes:
            assert process.stdin is not None
            process.stdin.write(_WINDOW_SQL)
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None

        ready_paths = tuple(
            coordination / f"ready-{process.pid}" for process in processes
        )
        ready_deadline = time.monotonic() + 60
        while not all(path.is_file() for path in ready_paths):
            exited = [
                process.pid for process in processes if process.poll() is not None
            ]
            assert not exited, f"children exited before barrier release: {exited}"
            assert time.monotonic() < ready_deadline, "children did not reach barrier"
            time.sleep(0.005)
        assert all(path.is_file() for path in ready_paths)
        (coordination / "release").write_text("go", encoding="ascii")

        outputs: list[str] = []
        intervals: list[tuple[int, int]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=180)
            assert process.returncode == 0, stderr
            fields = stdout.strip().split(",")
            assert len(fields) == 5
            intervals.append((int(fields[0]), int(fields[1])))
            outputs.append(",".join(fields[2:]))
        assert outputs == [",".join(map(str, expected[0]))] * 4
        assert all(start < end for start, end in intervals)
        assert max(start for start, _ in intervals) < min(
            end for _, end in intervals
        ), "all four query execution intervals must overlap"
        assert simultaneous_witnesses, (
            "all four active queries must have nonempty spill files at one time"
        )
        overlap_start = max(start for start, _ in intervals)
        overlap_end = min(end for _, end in intervals)
        assert any(
            overlap_start < witness_time < overlap_end
            for witness_time, _ in simultaneous_witnesses
        ), "the simultaneous spill witness must be inside the common work interval"
    finally:
        (coordination / "release").touch(exist_ok=True)
        for process in processes:
            if process.poll() is None:
                process.kill()
        for process in processes:
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=10)
        watching.set()
        watcher.join(timeout=5)
    assert not watcher.is_alive()
    assert {path.name for path in observed} == {
        f"query-spill-{process.pid}" for process in processes
    }
    assert not tuple(location.directory.glob("query-spill-*"))
    assert _index_inventory(location.directory) == index_before
    assert tuple(location.data_root.iterdir()) == (location.data_root / "fitdocs.toml",)
    for child_home in child_homes:
        assert tuple(child_home.iterdir()) == ()
    home_dir.assert_untouched()


def _plant(directory: Path, name: str) -> Path:
    path = directory / name
    path.mkdir()
    (path / "marker").write_text("keep", encoding="utf-8")
    return path


def _index_inventory(root: Path) -> dict[str, tuple[str, bytes | str | None]]:
    inventory: dict[str, tuple[str, bytes | str | None]] = {}

    def visit(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                metadata = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    inventory[relative] = ("symlink", os.readlink(path))
                elif stat.S_ISDIR(metadata.st_mode):
                    inventory[relative] = ("directory", None)
                    visit(path)
                elif stat.S_ISREG(metadata.st_mode):
                    inventory[relative] = ("file", path.read_bytes())
                else:
                    inventory[relative] = (
                        f"other:{stat.S_IFMT(metadata.st_mode)}",
                        None,
                    )

    visit(root)
    return dict(sorted(inventory.items()))


def test_index_inventory_captures_directories_bytes_and_links_without_following(
    tmp_path: Path,
) -> None:
    index = tmp_path / "index"
    index.mkdir()
    (index / "empty").mkdir()
    (index / "index.duckdb").write_bytes(b"index bytes")
    external = tmp_path / "external"
    external.mkdir()
    (external / "outside").write_bytes(b"outside bytes")
    (index / "external-link").symlink_to(external, target_is_directory=True)
    (index / "broken-link").symlink_to(tmp_path / "not-present")

    assert _index_inventory(index) == {
        "broken-link": ("symlink", str(tmp_path / "not-present")),
        "empty": ("directory", None),
        "external-link": ("symlink", str(external)),
        "index.duckdb": ("file", b"index bytes"),
    }


def test_index_inventory_captures_nested_payloads_and_special_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / "index-with-nested-and-special"
    index.mkdir()
    (index / "empty").mkdir()
    (index / "index.duckdb").write_bytes(b"independent flat index bytes")
    nested = index / "nested"
    nested.mkdir()
    first_payload = nested / "first-level.bin"
    first_payload.write_bytes(b"distinct first-level payload")
    grandchild = nested / "grandchild"
    grandchild.mkdir()
    second_payload = grandchild / "second-level.bin"
    second_payload.write_bytes(b"different deeper payload bytes")

    external = tmp_path / "external-with-payload"
    external.mkdir()
    (external / "outside.bin").write_bytes(b"external target bytes")
    (index / "external-link").symlink_to(external, target_is_directory=True)
    (index / "broken-link").symlink_to(tmp_path / "absent-target")

    fifo = index / "fifo-entry"
    os.mkfifo(fifo)
    fifo_mode = stat.S_IFMT(fifo.stat(follow_symlinks=False).st_mode)
    assert fifo_mode == stat.S_IFIFO

    socket_path = index / "controlled-socket-entry"

    class ControlledSocketEntry:
        name = socket_path.name
        path = str(socket_path)

        def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
            assert follow_symlinks is False
            return cast(os.stat_result, SimpleNamespace(st_mode=stat.S_IFSOCK))

    socket_entry = ControlledSocketEntry()
    real_scandir = os.scandir

    @contextmanager
    def controlled_scandir(
        path: str | os.PathLike[str],
    ) -> Iterator[Iterator[os.DirEntry[str]]]:
        with real_scandir(path) as entries:
            controlled_entries: list[os.DirEntry[str]] = list(entries)
            if Path(path) == index:
                controlled_entries.append(cast(os.DirEntry[str], socket_entry))
            yield iter(controlled_entries)

    real_read_bytes = Path.read_bytes
    forbidden_reads: list[Path] = []

    def reject_special_read(path: Path) -> bytes:
        if path in {fifo, socket_path}:
            forbidden_reads.append(path)
            raise AssertionError(f"inventory tried to read special entry {path.name}")
        return real_read_bytes(path)

    monkeypatch.setattr(os, "scandir", controlled_scandir)
    monkeypatch.setattr(Path, "read_bytes", reject_special_read)
    assert _index_inventory(index) == {
        "broken-link": ("symlink", str(tmp_path / "absent-target")),
        "controlled-socket-entry": (f"other:{stat.S_IFSOCK}", None),
        "empty": ("directory", None),
        "external-link": ("symlink", str(external)),
        "fifo-entry": (f"other:{stat.S_IFIFO}", None),
        "index.duckdb": ("file", b"independent flat index bytes"),
        "nested": ("directory", None),
        "nested/first-level.bin": ("file", b"distinct first-level payload"),
        "nested/grandchild": ("directory", None),
        "nested/grandchild/second-level.bin": (
            "file",
            b"different deeper payload bytes",
        ),
    }
    assert forbidden_reads == []


def test_index_inventory_covers_empty_files_raw_link_targets_and_posix_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / "matrix-index"
    index.mkdir()
    nested = index / "nested"
    nested.mkdir()
    (index / "empty.bin").write_bytes(b"")
    (index / "root.bin").write_bytes(b"root\x00\xff\n")
    (nested / "empty.bin").write_bytes(b"")
    (nested / "nested.bin").write_bytes(b"nested\x00\xfe\n")
    (index / "empty-dir").mkdir()
    (nested / "empty-dir").mkdir()

    targets = tmp_path / "external-targets"
    targets.mkdir()
    (targets / "zero.bin").write_bytes(b"")
    (targets / "payload.bin").write_bytes(b"external\x00payload")
    (targets / "empty-dir").mkdir()
    (targets / "populated-dir").mkdir()
    (targets / "populated-dir" / "outside.bin").write_bytes(b"must stay outside")
    external_fifo = targets / "fifo-target"
    os.mkfifo(external_fifo)
    fifo_target = index / "fifo-root"
    os.mkfifo(fifo_target)

    # These literal target strings deliberately retain ./; the inventory must
    # report readlink text rather than a normalized or resolved destination.
    links = {
        "zero-abs": str(tmp_path) + "/./external-targets/zero.bin",
        "payload-abs": str(tmp_path) + "/./external-targets/payload.bin",
        "empty-dir-abs": str(tmp_path) + "/./external-targets/empty-dir",
        "populated-dir-abs": str(tmp_path) + "/./external-targets/populated-dir",
        "absent-abs": str(tmp_path) + "/./external-targets/absent",
        "fifo-abs": str(tmp_path) + "/./external-targets/fifo-target",
        "zero-rel": "../external-targets/./zero.bin",
        "payload-rel": "../external-targets/./payload.bin",
        "empty-dir-rel": "../external-targets/./empty-dir",
        "populated-dir-rel": "../external-targets/./populated-dir",
        "absent-rel": "../external-targets/./absent",
        "fifo-rel": "../external-targets/./fifo-target",
    }
    for name, target in links.items():
        (index / f"link-{name}").symlink_to(target, target_is_directory="dir" in name)

    nested_links = {
        "zero-abs": links["zero-abs"],
        "payload-abs": links["payload-abs"],
        "empty-dir-abs": links["empty-dir-abs"],
        "populated-dir-abs": links["populated-dir-abs"],
        "absent-abs": links["absent-abs"],
        "fifo-abs": links["fifo-abs"],
        "zero-rel": "../../external-targets/./zero.bin",
        "payload-rel": "../../external-targets/./payload.bin",
        "empty-dir-rel": "../../external-targets/./empty-dir",
        "populated-dir-rel": "../../external-targets/./populated-dir",
        "absent-rel": "../../external-targets/./absent",
        "fifo-rel": "../../external-targets/./fifo-target",
    }
    for name, target in nested_links.items():
        (nested / f"link-{name}").symlink_to(target, target_is_directory="dir" in name)

    special_modes = {
        "socket": (stat.S_IFSOCK, 0o601),
        "char": (stat.S_IFCHR, 0o642),
        "block": (stat.S_IFBLK, 0o673),
    }
    special_paths: set[Path] = {
        fifo_target,
        nested / "fifo-nested",
        external_fifo,
        index / "link-fifo-abs",
        index / "link-fifo-rel",
        nested / "link-fifo-abs",
        nested / "link-fifo-rel",
    }
    os.mkfifo(nested / "fifo-nested")
    controlled_entries: dict[Path, list[os.DirEntry[str]]] = {}

    class ControlledEntry:
        def __init__(self, path: Path, mode: int) -> None:
            self.name = path.name
            self.path = str(path)
            self.mode = mode

        def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
            assert follow_symlinks is False
            return cast(
                os.stat_result,
                SimpleNamespace(st_mode=self.mode, st_size=0, st_mtime_ns=0),
            )

    for parent in (index, nested):
        additions: list[os.DirEntry[str]] = []
        for kind, (type_mode, permissions) in special_modes.items():
            path = parent / f"{kind}-{'root' if parent == index else 'nested'}"
            special_paths.add(path)
            additions.append(
                cast(os.DirEntry[str], ControlledEntry(path, type_mode | permissions))
            )
        controlled_entries[parent] = additions

    real_scandir = os.scandir

    @contextmanager
    def matrix_scandir(
        path: str | os.PathLike[str],
    ) -> Iterator[Iterator[os.DirEntry[str]]]:
        directory = Path(path)
        with real_scandir(path) as entries:
            yield iter([*entries, *controlled_entries.get(directory, [])])

    real_read_bytes = Path.read_bytes
    attempted_special_reads: list[Path] = []

    def guarded_read(path: Path) -> bytes:
        if path in special_paths:
            attempted_special_reads.append(path)
            raise AssertionError(f"inventory tried to read special entry {path.name}")
        return real_read_bytes(path)

    monkeypatch.setattr(os, "scandir", matrix_scandir)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    assert _index_inventory(index) == {
        "block-root": (f"other:{stat.S_IFBLK}", None),
        "char-root": (f"other:{stat.S_IFCHR}", None),
        "empty-dir": ("directory", None),
        "empty.bin": ("file", b""),
        "fifo-root": (f"other:{stat.S_IFIFO}", None),
        "link-absent-abs": ("symlink", str(tmp_path) + "/./external-targets/absent"),
        "link-absent-rel": ("symlink", "../external-targets/./absent"),
        "link-empty-dir-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/empty-dir",
        ),
        "link-empty-dir-rel": ("symlink", "../external-targets/./empty-dir"),
        "link-fifo-abs": ("symlink", str(tmp_path) + "/./external-targets/fifo-target"),
        "link-fifo-rel": ("symlink", "../external-targets/./fifo-target"),
        "link-payload-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/payload.bin",
        ),
        "link-payload-rel": ("symlink", "../external-targets/./payload.bin"),
        "link-populated-dir-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/populated-dir",
        ),
        "link-populated-dir-rel": ("symlink", "../external-targets/./populated-dir"),
        "link-zero-abs": ("symlink", str(tmp_path) + "/./external-targets/zero.bin"),
        "link-zero-rel": ("symlink", "../external-targets/./zero.bin"),
        "nested": ("directory", None),
        "nested/block-nested": (f"other:{stat.S_IFBLK}", None),
        "nested/char-nested": (f"other:{stat.S_IFCHR}", None),
        "nested/empty-dir": ("directory", None),
        "nested/empty.bin": ("file", b""),
        "nested/fifo-nested": (f"other:{stat.S_IFIFO}", None),
        "nested/link-absent-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/absent",
        ),
        "nested/link-absent-rel": ("symlink", "../../external-targets/./absent"),
        "nested/link-empty-dir-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/empty-dir",
        ),
        "nested/link-empty-dir-rel": ("symlink", "../../external-targets/./empty-dir"),
        "nested/link-fifo-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/fifo-target",
        ),
        "nested/link-fifo-rel": ("symlink", "../../external-targets/./fifo-target"),
        "nested/link-payload-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/payload.bin",
        ),
        "nested/link-payload-rel": ("symlink", "../../external-targets/./payload.bin"),
        "nested/link-populated-dir-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/populated-dir",
        ),
        "nested/link-populated-dir-rel": (
            "symlink",
            "../../external-targets/./populated-dir",
        ),
        "nested/link-zero-abs": (
            "symlink",
            str(tmp_path) + "/./external-targets/zero.bin",
        ),
        "nested/link-zero-rel": ("symlink", "../../external-targets/./zero.bin"),
        "nested/nested.bin": ("file", b"nested\x00\xfe\n"),
        "nested/socket-nested": (f"other:{stat.S_IFSOCK}", None),
        "root.bin": ("file", b"root\x00\xff\n"),
        "socket-root": (f"other:{stat.S_IFSOCK}", None),
    }
    assert attempted_special_reads == []


def test_nonempty_file_witness_requires_a_real_directory_and_regular_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    regular_file = tmp_path / "regular-file"
    regular_file.write_bytes(b"file")
    empty = tmp_path / "empty"
    empty.mkdir()
    zero_only = tmp_path / "zero-only"
    zero_only.mkdir()
    (zero_only / "zero-byte").write_bytes(b"")
    assert _nonempty_file_witness(missing) is None
    assert _nonempty_file_witness(regular_file) is None
    assert _nonempty_file_witness(empty) is None
    assert _nonempty_file_witness(zero_only) is None

    nested = empty / "nested"
    nested.mkdir()
    (empty / "zero-byte").write_bytes(b"")
    (nested / "payload").write_bytes(b"spill")
    assert _nonempty_file_witness(empty) == ("nested/payload", 5)

    outside = tmp_path / "outside-payload"
    outside.write_bytes(b"external")
    only_links = tmp_path / "only-links"
    only_links.mkdir()
    (only_links / "payload-link").symlink_to(outside)
    (only_links / "broken-link").symlink_to(tmp_path / "absent-target")
    assert _nonempty_file_witness(only_links) is None
    linked_directory = tmp_path / "linked-directory"
    linked_directory.symlink_to(empty, target_is_directory=True)
    assert _nonempty_file_witness(linked_directory) is None

    vanished = tmp_path / "vanished"
    vanished.mkdir()
    original_iterdir = Path.iterdir

    def missing_during_scan(path: Path) -> Iterator[Path]:
        if path == vanished:
            raise FileNotFoundError(path)
        yield from original_iterdir(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "iterdir", missing_during_scan)
        assert _nonempty_file_witness(vanished) is None

    changed_type = tmp_path / "changed-type"
    changed_type.mkdir()

    def non_directory_during_scan(path: Path) -> Iterator[Path]:
        if path == changed_type:
            raise NotADirectoryError(path)
        yield from original_iterdir(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "iterdir", non_directory_during_scan)
        assert _nonempty_file_witness(changed_type) is None

    disappearing_payload_dir = tmp_path / "disappearing-payload"
    disappearing_payload_dir.mkdir()
    disappearing_payload = disappearing_payload_dir / "payload"
    disappearing_payload.write_bytes(b"spill")
    original_is_file = Path.is_file
    original_is_dir = Path.is_dir
    original_is_symlink = Path.is_symlink
    original_stat = Path.stat

    def still_a_file(path: Path) -> bool:
        return True if path == disappearing_payload else original_is_file(path)

    def not_a_directory(path: Path) -> bool:
        return False if path == disappearing_payload else original_is_dir(path)

    def not_a_symlink(path: Path) -> bool:
        return False if path == disappearing_payload else original_is_symlink(path)

    def missing_payload_stat(
        path: Path, *, follow_symlinks: bool = True
    ) -> os.stat_result:
        if path == disappearing_payload:
            raise FileNotFoundError(path)
        return original_stat(path, follow_symlinks=follow_symlinks)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "is_file", still_a_file)
        scoped.setattr(Path, "is_dir", not_a_directory)
        scoped.setattr(Path, "is_symlink", not_a_symlink)
        scoped.setattr(Path, "stat", missing_payload_stat)
        assert _nonempty_file_witness(disappearing_payload_dir) is None


def test_cleanup_removes_only_reaped_query_process_spills(
    tmp_path: Path,
) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "home",
    )
    location.directory.mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    stale = _plant(location.directory, f"query-spill-{dead_pid}")
    near_matches = (
        _plant(location.directory, f"query-spill-{dead_pid}-suffix"),
        _plant(location.directory, f"query-spill-prefix-{dead_pid}"),
        _plant(location.directory, f"query-spill-x{dead_pid}"),
        _plant(location.directory, f"query-spill--{dead_pid}"),
        _plant(location.directory, f"query-spill-{dead_pid}suffix"),
    )
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    live = _plant(location.directory, f"query-spill-{sleeper.pid}")
    own = _plant(location.directory, f"query-spill-{os.getpid()}")
    external = tmp_path / "outside"
    external.mkdir()
    (external / "important").write_text("preserve", encoding="utf-8")
    link = location.directory / f"query-spill-{dead_pid + 1_000_000}"
    link.symlink_to(external, target_is_directory=True)
    other_file = location.directory / "index.duckdb"
    other_file.write_bytes(b"index")
    writer = _plant(location.directory, "writer-spill")
    malformed = _plant(location.directory, "writer-spill-" + str(dead_pid))
    non_directory = location.directory / f"query-spill-{dead_pid + 1_000_001}"
    non_directory.write_text("preserve", encoding="utf-8")

    try:
        removed = sandbox.remove_stale_spill(
            location,
            own_pid=os.getpid(),
            is_running=lambda pid: pid == sleeper.pid,
        )
        assert removed == (stale,)
        assert not stale.exists()
        assert all(
            item.joinpath("marker").read_text(encoding="utf-8") == "keep"
            for item in near_matches
        )
        assert all(item not in removed for item in near_matches)
        assert live.joinpath("marker").read_text(encoding="utf-8") == "keep"
        assert own.joinpath("marker").read_text(encoding="utf-8") == "keep"
        assert link.is_symlink()
        assert (external / "important").read_text(encoding="utf-8") == "preserve"
        assert other_file.read_bytes() == b"index"
        assert writer.joinpath("marker").read_text(encoding="utf-8") == "keep"
        assert malformed.joinpath("marker").read_text(encoding="utf-8") == "keep"
        assert non_directory.read_text(encoding="utf-8") == "preserve"
        assert sleeper.poll() is None
    finally:
        if sleeper.poll() is None:
            sleeper.terminate()
        sleeper.wait(timeout=10)


def test_cleanup_hook_skips_listing_and_preserves_dead_pid_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "home",
    )
    location.directory.mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    stale = _plant(location.directory, f"query-spill-{dead_pid}")
    monkeypatch.setattr(sandbox, "_SKIPS_SPILL_CLEANUP", True)
    original_iterdir = Path.iterdir
    listing_attempts: list[Path] = []

    def reject_index_listing(path: Path) -> Iterator[Path]:
        if path == location.directory:
            listing_attempts.append(path)
            raise AssertionError("the skip hook must return before listing")
        yield from original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", reject_index_listing)
    assert (
        sandbox.remove_stale_spill(
            location, own_pid=os.getpid(), is_running=lambda _: False
        )
        == ()
    )
    assert listing_attempts == []
    assert stale.joinpath("marker").read_text(encoding="utf-8") == "keep"


def test_process_liveness_handles_current_reaped_and_permission_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    assert sandbox.process_is_running(os.getpid()) is True
    assert sandbox.process_is_running(dead_pid) is False

    def permission_denied(pid: int, signal: int) -> None:
        assert pid == 654321
        assert signal == 0
        raise PermissionError

    monkeypatch.setattr(os, "kill", permission_denied)
    assert sandbox.process_is_running(654321) is True


def test_process_liveness_propagates_unexpected_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_error(pid: int, signal: int) -> None:
        assert pid == 654322
        assert signal == 0
        raise OSError("invalid process query")

    monkeypatch.setattr(os, "kill", unexpected_error)
    with pytest.raises(OSError, match="invalid process query"):
        sandbox.process_is_running(654322)


def test_spill_directory_uses_fixed_index_child_and_pid(tmp_path: Path) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "home",
    )
    assert sandbox.spill_directory(location, 27187) == (
        location.directory / "query-spill-27187"
    )


def test_cleanup_swallows_remove_oserror_and_returns_only_removed_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "home",
    )
    location.directory.mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    stale = _plant(location.directory, f"query-spill-{dead_pid}")
    monkeypatch.setattr(
        shutil, "rmtree", lambda _: (_ for _ in ()).throw(OSError("no"))
    )
    assert (
        sandbox.remove_stale_spill(
            location, own_pid=os.getpid(), is_running=lambda _: False
        )
        == ()
    )
    assert stale.joinpath("marker").read_text(encoding="utf-8") == "keep"


def test_cleanup_never_sends_a_spill_named_file_to_rmtree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "home",
    )
    location.directory.mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait(timeout=10)
    file = location.directory / f"query-spill-{dead_pid}"
    file.write_text("preserve", encoding="utf-8")
    calls: list[Path] = []
    original_rmtree = shutil.rmtree

    def destructive_recorder(path: str | Path) -> None:
        candidate = Path(path)
        calls.append(candidate)
        if candidate.is_file():
            candidate.unlink()
        else:
            original_rmtree(candidate)

    monkeypatch.setattr(shutil, "rmtree", destructive_recorder)
    assert (
        sandbox.remove_stale_spill(
            location, own_pid=os.getpid(), is_running=lambda _: False
        )
        == ()
    )
    assert calls == []
    assert file.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("directory_exists", [False, True])
def test_cleanup_ignores_missing_parent_and_non_directory_parent(
    tmp_path: Path, directory_exists: bool
) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "home",
    )
    if directory_exists:
        location.directory.parent.mkdir(parents=True)
        location.directory.write_text("file", encoding="utf-8")
    assert (
        sandbox.remove_stale_spill(
            location, own_pid=os.getpid(), is_running=lambda _: False
        )
        == ()
    )
