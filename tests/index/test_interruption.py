"""Page-transaction recovery when a refresh process is killed mid-page."""

from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
import sys
from datetime import UTC, date
from pathlib import Path

from fitdocs.contract import is_workout_document
from fitdocs.docio import read_frontmatter
from fitdocs.index import corpus
from fitdocs.index.bookkeeping import Bookkeeping, ComputedState, IndexMeta
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.fingerprint import athlete_fingerprint as input_fingerprint
from fitdocs.index.refresh import RefreshInputs, reconcile
from fitdocs.index.schema import SCHEMA_VERSION, ResolvedTable, TableSpec
from fitdocs.index.store import (
    create_index,
    create_schema,
    duckdb_version,
    open_index,
    read_bookkeeping,
    write_meta,
)
from fitdocs.metrics.types import AthleteInputs, ZoneSpec
from fitdocs.sync import sync
from fitdocs.version import tool_version
from tests.fixtures import builder
from tests.index.conftest import _SyntheticTiles

_TODAY = date(2044, 5, 6)
_OLD_ATHLETE = AthleteInputs(
    ftp_watts=201.25,
    resting_hr_bpm=48,
    max_hr_bpm=187,
    hr_zones=ZoneSpec((105.0, 132.0, 165.0)),
    power_zones=ZoneSpec((110.0, 190.0, 250.0)),
    pace_zones=ZoneSpec((260.0, 350.0, 520.0)),
)
_NEW_ATHLETE = AthleteInputs(
    ftp_watts=273.75,
    resting_hr_bpm=55,
    max_hr_bpm=198,
    hr_zones=ZoneSpec((118.0, 146.0, 182.0)),
    power_zones=ZoneSpec((145.0, 225.0, 287.0)),
    pace_zones=ZoneSpec((220.0, 310.0, 470.0)),
)


_CHILD_REFRESH = r"""
import os
import signal
from datetime import date
from pathlib import Path

from fitdocs.index import registry
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.producer import PageComputed
from fitdocs.index.refresh import RefreshInputs, reconcile
from fitdocs.index.store import open_index, read_bookkeeping
from fitdocs.metrics.types import AthleteInputs, ZoneSpec

class BlockingComputedProducer:
    name = "test.interruption_blocker"
    tables = ()
    def __init__(self):
        self.calls = 0
    def rows(self, page: PageComputed):
        self.calls += 1
        key = page.document.page_key
        os.write(int(os.environ["FITDOCS_TEST_PIPE_FD"]), (key + "\n").encode())
        if self.calls == 4:
            signal.pause()
        return {}

blocker = BlockingComputedProducer()
registry.DOCUMENT_PRODUCERS = (CORE_DOCUMENTS,)
registry.COMPUTED_PRODUCERS = (CORE_COMPUTED, blocker)
registry.CORPUS_PRODUCERS = ()
assert (
    len(registry.DOCUMENT_PRODUCERS) == 1
    and registry.DOCUMENT_PRODUCERS[0] is CORE_DOCUMENTS
), "child document registry must contain exactly CORE_DOCUMENTS"
assert (
    len(registry.COMPUTED_PRODUCERS) == 2
    and registry.COMPUTED_PRODUCERS[0] is CORE_COMPUTED
    and registry.COMPUTED_PRODUCERS[1] is blocker
), "child computed registry must contain CORE_COMPUTED followed by its blocker"
assert registry.CORPUS_PRODUCERS == (), "child corpus registry must be empty"
athlete = AthleteInputs(
    ftp_watts=273.75,
    resting_hr_bpm=55,
    max_hr_bpm=198,
    hr_zones=ZoneSpec((118.0, 146.0, 182.0)),
    power_zones=ZoneSpec((145.0, 225.0, 287.0)),
    pace_zones=ZoneSpec((220.0, 310.0, 470.0)),
)
with open_index(Path(os.environ["FITDOCS_TEST_DATABASE"]), read_only=False) as conn:
    bookkeeping = read_bookkeeping(conn)
    assert bookkeeping is not None
    reconcile(conn, bookkeeping, RefreshInputs(
        Path(os.environ["FITDOCS_TEST_DATA_ROOT"]),
        athlete,
        None,
        date(2044, 5, 6),
        None,
    ))
"""


def _add_three_pages(data_root: Path, tmp_path: Path) -> None:
    payloads = (
        ("strength", builder.strength_fit_bytes()),
        ("hike", builder.small_sport_fit_bytes(8101, "hiking")),
        (
            "walk",
            builder.small_sport_fit_bytes(8102, "walking", timestamp_offset=8_640_000),
        ),
    )
    for name, payload in payloads:
        source = tmp_path / f"source-{name}"
        source.mkdir()
        (source / f"{name}.fit").write_bytes(payload)
        report = sync(
            source,
            data_root,
            athlete=_OLD_ATHLETE,
            tz=UTC,
            tiles=_SyntheticTiles(),
        )
        assert report.failures == ()


def _new_index(database: Path, data_root: Path) -> None:
    from fitdocs.index import registry

    with create_index(database) as connection:
        create_schema(connection, registry.registered_tables())
        write_meta(
            connection,
            IndexMeta(
                schema_version=SCHEMA_VERSION,
                fitdocs_version=tool_version(),
                duckdb_version=duckdb_version(),
                data_root=str(data_root.resolve()),
                athlete_fingerprint=input_fingerprint(None),
            ),
        )


def _refresh(database: Path, data_root: Path, athlete: AthleteInputs) -> None:
    with open_index(database, read_only=False) as connection:
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
        reconcile(
            connection,
            bookkeeping,
            RefreshInputs(data_root, athlete, None, _TODAY, None),
        )


def _core_tables() -> tuple[TableSpec, ...]:
    return tuple(
        table
        for producer in (CORE_DOCUMENTS, CORE_COMPUTED)
        for table in producer.tables
    )


def _bookkeeping(database: Path) -> Bookkeeping:
    with open_index(database, read_only=True) as connection:
        result = read_bookkeeping(connection)
        assert result is not None
        return result


def _page_rows(
    database: Path,
) -> dict[str, dict[str, tuple[tuple[object, ...], ...]]]:
    result: dict[str, dict[str, tuple[tuple[object, ...], ...]]] = {}
    with open_index(database, read_only=True) as connection:
        for table in _core_tables():
            rows = connection.execute(
                f'SELECT * FROM "{table.name}" ORDER BY ALL'
            ).fetchall()
            for row in rows:
                page_key = str(row[0])
                result.setdefault(page_key, {})[table.name] = (
                    *result.get(page_key, {}).get(table.name, ()),
                    tuple(row),
                )
    for page_rows in result.values():
        for table in _core_tables():
            page_rows.setdefault(table.name, ())
    return result


def _read_four_keys(process: subprocess.Popen[bytes], read_fd: int) -> tuple[str, ...]:
    selector = selectors.DefaultSelector()
    selector.register(read_fd, selectors.EVENT_READ)
    buffer = b""
    keys: list[str] = []
    while len(keys) < 4:
        ready = selector.select(timeout=20)
        assert ready, "child did not reach its fourth computed page"
        chunk = os.read(read_fd, 4096)
        if not chunk:
            stdout, stderr = process.communicate(timeout=5)
            raise AssertionError(
                f"child exited before the fourth page: {stdout!r} {stderr!r}"
            )
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line:
                keys.append(line.decode("ascii"))
    selector.close()
    return tuple(keys)


def test_sigkill_keeps_each_page_wholly_old_or_new_and_recovers(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    synced_corpus: Path,
) -> None:
    data_root = tmp_path / "interruption-data"
    shutil.copytree(synced_corpus, data_root)
    _add_three_pages(data_root, tmp_path)
    page_paths = tuple(
        path
        for path in sorted((data_root / "workouts").glob("*.md"))
        if is_workout_document(read_frontmatter(path))
    )
    assert len(page_paths) == 5

    database = tmp_path / "interrupted.duckdb"
    _new_index(database, data_root)
    _refresh(database, data_root, _OLD_ATHLETE)
    old_bookkeeping = _bookkeeping(database)
    old_rows = _page_rows(database)
    expected_keys = tuple(
        page.page_key for page in corpus.scan_workout_pages(data_root).pages
    )
    assert len(expected_keys) == 5
    assert set(old_bookkeeping.pages) == set(expected_keys)
    assert set(old_rows) == set(expected_keys)
    assert all(
        old_bookkeeping.pages[key].computed_state is ComputedState.COMPUTED
        for key in expected_keys
    )

    # A document edit makes new PageState values observable independently of
    # athlete-driven computed values. The archive refs/page keys stay unchanged.
    old_page_bytes = {path: path.read_bytes() for path in page_paths}
    for path, payload in old_page_bytes.items():
        changed = payload + b"\nSynthetic refresh state change.\n"
        assert changed != payload
        path.write_bytes(changed)

    expected_database = tmp_path / "expected-new.duckdb"
    _new_index(expected_database, data_root)
    _refresh(expected_database, data_root, _NEW_ATHLETE)
    new_bookkeeping = _bookkeeping(expected_database)
    new_rows = _page_rows(expected_database)
    assert set(new_bookkeeping.pages) == set(expected_keys)
    assert set(new_rows) == set(expected_keys)
    for page_key in expected_keys:
        assert old_rows[page_key]["activities"]
        assert new_rows[page_key]["activities"]
        assert old_bookkeeping.pages[page_key] != new_bookkeeping.pages[page_key]
        assert old_rows[page_key] != new_rows[page_key]
        assert old_rows[page_key]["activities"] != new_rows[page_key]["activities"]

    read_fd, write_fd = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    child_keys: tuple[str, ...] = ()
    try:
        environment = dict(os.environ)
        environment["FITDOCS_TEST_PIPE_FD"] = str(write_fd)
        environment["FITDOCS_TEST_DATABASE"] = str(database)
        environment["FITDOCS_TEST_DATA_ROOT"] = str(data_root)
        process = subprocess.Popen(
            [sys.executable, "-c", _CHILD_REFRESH],
            env=environment,
            pass_fds=(write_fd,),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        os.close(write_fd)
        write_fd = -1
        child_keys = _read_four_keys(process, read_fd)
        assert child_keys == expected_keys[:4]
        process.send_signal(signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == -signal.SIGKILL, (stdout, stderr)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
        if write_fd >= 0:
            os.close(write_fd)
        os.close(read_fd)

    interrupted_bookkeeping = _bookkeeping(database)
    interrupted_rows = _page_rows(database)
    for index, page_key in enumerate(expected_keys):
        expected_page_state = (
            new_bookkeeping.pages[page_key]
            if index < 3
            else old_bookkeeping.pages[page_key]
        )
        expected_page_rows = new_rows[page_key] if index < 3 else old_rows[page_key]
        assert interrupted_bookkeeping.pages[page_key] == expected_page_state
        assert interrupted_rows[page_key] == expected_page_rows

    # Page four reached its producer before the kill, but its new rows were
    # inside the uncommitted transaction and therefore are absent on reopen.
    fourth_key = expected_keys[3]
    assert fourth_key in child_keys
    assert interrupted_rows[fourth_key] == old_rows[fourth_key]
    assert interrupted_rows[fourth_key] != new_rows[fourth_key]

    _refresh(database, data_root, _NEW_ATHLETE)
    recovered_bookkeeping = _bookkeeping(database)
    recovered_rows = _page_rows(database)
    assert recovered_bookkeeping.pages == new_bookkeeping.pages
    assert recovered_rows == new_rows
