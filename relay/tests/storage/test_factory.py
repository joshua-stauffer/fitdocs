"""The storage factory: selection by target, and the missing-extra refusal."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.storage import MissingPostgresSupport, open_storage
from fitdocs_relay.storage.interface import Storage
from fitdocs_relay.storage.sqlite import SqliteBackend


def test_each_target_opens_the_backend_it_names(
    database_target: SqliteTarget | PostgresTarget,
) -> None:
    store: Storage = open_storage(database_target)
    try:
        if isinstance(database_target, SqliteTarget):
            assert isinstance(store, SqliteBackend)
            assert store.backend == "sqlite"
        else:
            assert type(store).__name__ == "PostgresBackend"
            assert store.backend == "postgres"
    finally:
        store.close()


_PROBE = """
import sys
sys.modules[{blocked!r}] = None
from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.storage import MissingPostgresSupport, open_storage
assert "fitdocs_relay.storage.postgres" not in sys.modules, "imported eagerly"
store = open_storage(SqliteTarget(path=__import__("pathlib").Path(sys.argv[1])))
assert store.backend == "sqlite"
store.close()
assert not any(m.startswith("psycopg") for m in sys.modules if m != {blocked!r})
try:
    open_storage(PostgresTarget(conninfo="postgresql://x/y", password="hunter2-secret"))
except MissingPostgresSupport as error:
    print(str(error))
    sys.exit(0)
print("no error")
sys.exit(1)
"""


@pytest.mark.parametrize("blocked", ["psycopg", "psycopg_pool"])
def test_missing_postgres_support_names_the_extra(blocked: str, tmp_path: Path) -> None:
    done = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _PROBE.format(blocked=blocked),
            str(tmp_path / "f.sqlite3"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    message = done.stdout.strip()
    assert "postgres extra" in message
    assert "fitdocs-relay[postgres]" in message
    assert "hunter2-secret" not in message


def test_a_failure_importing_the_relays_own_backend_module_is_not_the_missing_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "fitdocs_relay.storage.postgres", None)
    target = PostgresTarget(conninfo="postgresql://x/y", password=None)
    with pytest.raises(ImportError) as raised:
        open_storage(target)
    assert not isinstance(raised.value, MissingPostgresSupport)
    assert raised.value.name == "fitdocs_relay.storage.postgres"
