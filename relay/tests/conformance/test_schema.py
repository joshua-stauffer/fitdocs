"""Schema changes on both backends: migrate, pending, apply, ping, the data model."""

from __future__ import annotations

import itertools
import sqlite3
import threading
import time
import traceback
from collections.abc import Callable
from typing import Any

import pytest

from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.storage.interface import (
    SchemaAhead,
    SchemaChange,
    SchemaStore,
    StorageError,
    StorageUnreachable,
)
from fitdocs_relay.storage.migrate import migrate, pending, schema_changes

Target = SqliteTarget | PostgresTarget
Opener = Callable[[], SchemaStore]

NOW = 1_700_000_123
LATER = 1_800_000_456
PLANTED = "planted_distinct_table_9f3a"


def raw(target: Target, sql: str, params: tuple[object, ...] = ()) -> list[Any]:
    """Run SQL on the test database outside the backend under test."""
    if isinstance(target, SqliteTarget):
        connection = sqlite3.connect(target.path, isolation_level=None)
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()
    import psycopg

    with psycopg.connect(target.conninfo, autocommit=True) as pg:
        cursor = pg.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def param(target: Target) -> str:
    return "?" if isinstance(target, SqliteTarget) else "%s"


def version_rows(target: Target) -> list[tuple[int, str, int]]:
    return [
        (int(v), str(n), int(a))
        for v, n, a in raw(
            target,
            "SELECT version, name, applied_at FROM relay_schema ORDER BY version",
        )
    ]


def table_names(target: Target) -> list[str]:
    if isinstance(target, SqliteTarget):
        rows = raw(target, "SELECT name FROM sqlite_master WHERE type = 'table'")
    else:
        rows = raw(
            target,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()",
        )
    return sorted(str(r[0]) for r in rows)


def expected_version(store: SchemaStore) -> int:
    expected = len(schema_changes(store.backend))
    assert expected >= 1, "the build ships no schema change"
    return expected


# --- backend ----------------------------------------------------------------


@pytest.mark.covers("StorageBase.backend")
def test_the_backend_names_itself(
    schema_store: SchemaStore, database_target: Target
) -> None:
    expected = "sqlite" if isinstance(database_target, SqliteTarget) else "postgres"
    assert schema_store.backend == expected


# --- migrate / pending --------------------------------------------------------


@pytest.mark.covers("SchemaStore.schema_state", "SchemaStore.apply_schema_change")
def test_a_fresh_migrate_reaches_the_expected_version(
    schema_store: SchemaStore, database_target: Target
) -> None:
    expected = expected_version(schema_store)
    before = schema_store.schema_state()
    assert (before.current, before.expected) == (0, expected)
    assert [c.version for c in pending(schema_store)] == list(range(1, expected + 1))

    report = migrate(schema_store, now=NOW)

    assert (report.found, report.left) == (0, expected)
    assert report.applied == tuple(range(1, expected + 1))
    after = schema_store.schema_state()
    assert (after.current, after.expected) == (expected, expected)
    assert pending(schema_store) == ()
    assert version_rows(database_target) == [
        (c.version, c.name, NOW) for c in schema_changes(schema_store.backend)
    ]
    assert {"relay_schema", "principals", "tokens", "rate_counts", "records"} <= set(
        table_names(database_target)
    )


@pytest.mark.covers("SchemaStore.schema_state", "SchemaStore.apply_schema_change")
def test_a_migrated_schema_has_no_publication_table_and_is_at_version_two(
    schema_store: SchemaStore, database_target: Target
) -> None:
    migrate(schema_store, now=NOW)

    tables = table_names(database_target)
    assert "target_connections" in tables  # the same query finds a table that exists
    assert "target_publications" not in tables
    assert [v for v, _name, _at in version_rows(database_target)] == [1, 2]
    assert schema_store.schema_state().expected == 2


@pytest.mark.covers("SchemaStore.schema_state", "SchemaStore.apply_schema_change")
def test_a_second_migrate_changes_nothing(
    schema_store: SchemaStore, database_target: Target
) -> None:
    expected = expected_version(schema_store)
    migrate(schema_store, now=NOW)
    rows_before = version_rows(database_target)
    tables_before = table_names(database_target)
    assert rows_before, "the first run left no version row"

    report = migrate(schema_store, now=LATER)

    assert (report.found, report.left, report.applied) == (expected, expected, ())
    assert version_rows(database_target) == rows_before  # applied_at still NOW
    assert table_names(database_target) == tables_before


@pytest.mark.parametrize("ahead_by", [1, 6])
@pytest.mark.covers("SchemaStore.schema_state", "SchemaStore.apply_schema_change")
def test_a_newer_database_is_refused_and_left_unchanged(
    schema_store: SchemaStore, database_target: Target, ahead_by: int
) -> None:
    expected = expected_version(schema_store)
    newer = expected + ahead_by
    raw(
        database_target,
        "CREATE TABLE relay_schema "
        "(version integer PRIMARY KEY, name text, applied_at bigint)",
    )
    raw(
        database_target,
        f"INSERT INTO relay_schema VALUES ({param(database_target)}, 'future', 5)",
        (newer,),
    )
    assert schema_store.schema_state().current == newer  # the scenario is reached
    tables_before = table_names(database_target)
    assert tables_before == ["relay_schema"]

    message = (
        f"the database is at schema version {newer}, newer than this build's {expected}"
    )
    with pytest.raises(SchemaAhead) as migrated:
        migrate(schema_store, now=NOW)
    assert str(migrated.value) == message
    with pytest.raises(SchemaAhead) as listed:
        pending(schema_store)
    assert str(listed.value) == message

    assert version_rows(database_target) == [(newer, "future", 5)]
    assert table_names(database_target) == tables_before


@pytest.mark.covers("SchemaStore.apply_schema_change", "SchemaStore.schema_state")
def test_a_failing_change_leaves_the_last_applied_version(
    schema_store: SchemaStore, database_target: Target
) -> None:
    migrate(schema_store, now=NOW)
    last = schema_store.schema_state().current
    rows_before = version_rows(database_target)
    tables_before = table_names(database_target)
    broken = SchemaChange(
        version=last + 1,
        name=f"{last + 1:04d}_broken",
        sql=f"CREATE TABLE half_applied (x integer);\nSELECT * FROM {PLANTED};\n",
    )

    with pytest.raises(StorageError) as raised:
        schema_store.apply_schema_change(broken, now=NOW)

    error = raised.value
    assert not isinstance(error, StorageUnreachable)
    assert str(error) == (
        "the SQLite database reported an error"
        if schema_store.backend == "sqlite"
        else "the PostgreSQL database reported an error"
    )
    assert error.args == (str(error),)
    shown = "".join(traceback.format_exception(error)) + repr(error) + str(error)
    assert PLANTED not in shown
    assert error.__cause__ is None
    assert error.__context__ is None
    assert schema_store.schema_state().current == last
    assert version_rows(database_target) == rows_before
    assert table_names(database_target) == tables_before  # half_applied rolled back
    # The retry of a repaired change succeeds: nothing of the failed one remains.
    repaired = SchemaChange(
        version=broken.version,
        name=broken.name,
        sql="CREATE TABLE half_applied (x integer)",
    )
    assert schema_store.apply_schema_change(repaired, now=LATER) is True
    assert schema_store.schema_state().current == last + 1


@pytest.mark.covers("SchemaStore.apply_schema_change", "SchemaStore.schema_state")
def test_a_change_and_its_version_row_commit_together(
    schema_store: SchemaStore, database_target: Target
) -> None:
    migrate(schema_store, now=NOW)
    last = schema_store.schema_state().current
    rows_before = version_rows(database_target)
    # The change itself takes the version number the backend is about to
    # record, so the backend's own version-row insert is the step that fails.
    collides = SchemaChange(
        version=last + 1,
        name=f"{last + 1:04d}_collides",
        sql="CREATE TABLE atomic_probe (x integer);\n"
        f"INSERT INTO relay_schema VALUES ({last + 1}, 'taken', 1)",
    )

    with pytest.raises(StorageError):
        schema_store.apply_schema_change(collides, now=LATER)

    assert "atomic_probe" not in table_names(database_target)
    assert version_rows(database_target) == rows_before
    assert schema_store.schema_state().current == last


@pytest.mark.covers("SchemaStore.apply_schema_change", "SchemaStore.schema_state")
def test_an_applied_change_is_skipped_and_a_gap_is_refused(
    schema_store: SchemaStore, database_target: Target
) -> None:
    migrate(schema_store, now=NOW)
    last = schema_store.schema_state().current
    rows_before = version_rows(database_target)
    first = schema_changes(schema_store.backend)[0]
    trap = SchemaChange(version=first.version, name=first.name, sql="DROP TABLE tokens")

    assert schema_store.apply_schema_change(trap, now=LATER) is False
    assert "tokens" in table_names(database_target)

    gap = SchemaChange(version=last + 2, name="gap", sql="CREATE TABLE gap (x integer)")
    with pytest.raises(StorageError):
        schema_store.apply_schema_change(gap, now=LATER)
    assert "gap" not in table_names(database_target)
    assert version_rows(database_target) == rows_before


# --- concurrency ------------------------------------------------------------


def _slow_sql(store: SchemaStore) -> str:
    """A statement that holds the writer lock for a measurable moment."""
    if store.backend == "postgres":
        return "SELECT pg_sleep(0.4)"
    return (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c "
        "WHERE x < 1500000) SELECT count(*) FROM c"
    )


def _race(
    stores: list[SchemaStore], work: Callable[[SchemaStore], object]
) -> tuple[list[object], list[tuple[float, float]]]:
    """Run `work(store)` on every store at once; its results and each run's span."""
    barrier = threading.Barrier(len(stores))
    results: list[object] = [None] * len(stores)
    spans: list[tuple[float, float]] = [(0.0, 0.0)] * len(stores)

    def run(index: int) -> None:
        barrier.wait()
        started = time.monotonic()
        try:
            results[index] = work(stores[index])
        except BaseException as error:
            results[index] = error
        spans[index] = (started, time.monotonic())

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(stores))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a migration hung"
    return results, spans


def _overlapped(spans: list[tuple[float, float]]) -> bool:
    return max(start for start, _ in spans) < min(end for _, end in spans)


@pytest.mark.covers("SchemaStore.apply_schema_change", "SchemaStore.schema_state")
def test_two_concurrent_migrations_apply_each_change_once(
    open_schema_store: Opener, database_target: Target
) -> None:
    stores = [open_schema_store() for _ in range(4)]
    expected = expected_version(stores[0])

    results, _ = _race(stores, lambda store: migrate(store, now=NOW))

    reports = [r for r in results if not isinstance(r, BaseException)]
    assert reports == results, f"a concurrent migrate failed: {results}"
    applied = sorted(itertools.chain.from_iterable(r.applied for r in reports))  # type: ignore[attr-defined]
    assert applied == list(range(1, expected + 1))
    assert [row[0] for row in version_rows(database_target)] == list(
        range(1, expected + 1)
    )
    assert stores[0].schema_state().current == expected


@pytest.mark.covers("SchemaStore.apply_schema_change")
def test_concurrent_applies_of_slow_changes_run_each_exactly_once(
    open_schema_store: Opener, database_target: Target
) -> None:
    stores = [open_schema_store() for _ in range(4)]
    migrate(stores[0], now=NOW)
    base = stores[0].schema_state().current
    slow = _slow_sql(stores[0])
    changes = [
        SchemaChange(
            version=base + n,
            name=f"{base + n:04d}_slow_{n}",
            sql=f"CREATE TABLE slow_{n} (x integer);\n{slow};\n"
            f"INSERT INTO slow_{n} VALUES (1)",
        )
        for n in (1, 2)
    ]

    results, spans = _race(
        stores,
        lambda store: [store.apply_schema_change(c, now=NOW) for c in changes],
    )

    assert _overlapped(spans), "the migrations did not overlap"
    assert max(end - start for start, end in spans) > 0.2, "the change was not slow"
    assert all(isinstance(r, list) for r in results), results
    for position in range(len(changes)):
        outcomes = [r[position] for r in results]  # type: ignore[index]
        assert sorted(outcomes) == [False, False, False, True]
    for n in (1, 2):
        assert raw(database_target, f"SELECT count(*) FROM slow_{n}") == [(1,)]
    assert [r[0] for r in version_rows(database_target)] == [
        *range(1, base + 1),
        base + 1,
        base + 2,
    ]


# --- ping and close ---------------------------------------------------------


@pytest.mark.covers("StorageBase.ping", "StorageBase.close")
def test_ping_succeeds_while_open_and_raises_unreachable_once_closed(
    open_schema_store: Opener,
) -> None:
    store = open_schema_store()
    store.ping()

    store.close()

    with pytest.raises(StorageUnreachable):
        store.ping()
    with pytest.raises(StorageUnreachable):
        store.schema_state()
    store.close()  # closing again is harmless


# --- the data model ---------------------------------------------------------

# design.md, Physical Data Model, for each backend. The expected rows are
# literals for what is queried below: columns (type, nullability, default,
# identity, generation, and on PostgreSQL the collation), constraints, indexes,
# foreign keys, relation kinds and persistence, triggers and custom collations.
# A change to any of those reds here; anything else is not pinned.
DESIGNED_TABLES = [
    "budget_counts",
    "principals",
    "rate_counts",
    "records",
    "relay_schema",
    "target_connections",
    "tokens",
]

# PRAGMA table_xinfo: (cid, name, type, notnull, dflt_value, pk, hidden)
SQLITE_COLUMNS = {
    "budget_counts": [
        (0, "key", "TEXT", 1, None, 1, 0),
        (1, "window_start", "INTEGER", 1, None, 2, 0),
        (2, "count", "INTEGER", 1, None, 0, 0),
        (3, "window_end", "INTEGER", 1, None, 0, 0),
        (4, "principal_id", "TEXT", 0, None, 0, 0),
    ],
    "principals": [
        (0, "principal_id", "TEXT", 1, None, 1, 0),
        (1, "label", "TEXT", 0, None, 0, 0),
        (2, "created_at", "INTEGER", 1, None, 0, 0),
    ],
    "rate_counts": [
        (0, "key", "TEXT", 1, None, 1, 0),
        (1, "window_start", "INTEGER", 1, None, 2, 0),
        (2, "count", "INTEGER", 1, None, 0, 0),
        (3, "window_end", "INTEGER", 1, None, 0, 0),
    ],
    "records": [
        (0, "namespace", "TEXT", 1, None, 1, 0),
        (1, "key", "TEXT", 1, None, 2, 0),
        (2, "value", "BLOB", 1, None, 0, 0),
        (3, "expires_at", "INTEGER", 1, None, 0, 0),
    ],
    "relay_schema": [
        (0, "version", "INTEGER", 1, None, 1, 0),
        (1, "name", "TEXT", 1, None, 0, 0),
        (2, "applied_at", "INTEGER", 1, None, 0, 0),
    ],
    "target_connections": [
        (0, "principal_id", "TEXT", 1, None, 1, 0),
        (1, "target", "TEXT", 1, None, 2, 0),
        (2, "account_key", "TEXT", 1, None, 0, 0),
        (3, "access_sealed", "TEXT", 1, None, 0, 0),
        (4, "refresh_sealed", "TEXT", 0, None, 0, 0),
        (5, "access_expires_at", "INTEGER", 0, None, 0, 0),
        (6, "generation", "INTEGER", 1, None, 0, 0),
        (7, "lease_id", "TEXT", 0, None, 0, 0),
        (8, "lease_until", "INTEGER", 0, None, 0, 0),
        (9, "token_id", "TEXT", 0, None, 0, 0),
        (10, "created_at", "INTEGER", 1, None, 0, 0),
        (11, "updated_at", "INTEGER", 1, None, 0, 0),
    ],
    "tokens": [
        (0, "token_id", "TEXT", 1, None, 1, 0),
        (1, "principal_id", "TEXT", 1, None, 0, 0),
        (2, "verifier", "TEXT", 1, None, 0, 0),
        (3, "label", "TEXT", 0, None, 0, 0),
        (4, "created_at", "INTEGER", 1, None, 0, 0),
        (5, "revoked_at", "INTEGER", 0, None, 0, 0),
    ],
}
# PRAGMA index_list: (name, unique, origin, partial), by name
SQLITE_INDEXES = {
    "budget_counts": [
        ("budget_counts_window_end_idx", 0, "c", 0),
        ("sqlite_autoindex_budget_counts_1", 1, "pk", 0),
    ],
    "principals": [("sqlite_autoindex_principals_1", 1, "pk", 0)],
    "rate_counts": [
        ("rate_counts_window_end_idx", 0, "c", 0),
        ("sqlite_autoindex_rate_counts_1", 1, "pk", 0),
    ],
    "records": [
        ("records_expires_at_idx", 0, "c", 0),
        ("sqlite_autoindex_records_1", 1, "pk", 0),
    ],
    "relay_schema": [],
    "target_connections": [
        ("sqlite_autoindex_target_connections_1", 1, "pk", 0),
        ("sqlite_autoindex_target_connections_2", 1, "u", 0),
    ],
    "tokens": [
        ("sqlite_autoindex_tokens_1", 1, "pk", 0),
        ("tokens_principal_id_idx", 0, "c", 0),
    ],
}
# PRAGMA index_info columns, per index
SQLITE_INDEX_COLUMNS = {
    "budget_counts_window_end_idx": ["window_end"],
    "sqlite_autoindex_budget_counts_1": ["key", "window_start"],
    "sqlite_autoindex_target_connections_1": ["principal_id", "target"],
    "sqlite_autoindex_target_connections_2": ["target", "account_key"],
    "sqlite_autoindex_principals_1": ["principal_id"],
    "rate_counts_window_end_idx": ["window_end"],
    "sqlite_autoindex_rate_counts_1": ["key", "window_start"],
    "records_expires_at_idx": ["expires_at"],
    "sqlite_autoindex_records_1": ["namespace", "key"],
    "sqlite_autoindex_tokens_1": ["token_id"],
    "tokens_principal_id_idx": ["principal_id"],
}
# PRAGMA foreign_key_list: (id, seq, table, from, to, on_update, on_delete, match)
_CASCADE_TO_PRINCIPALS = (
    0,
    0,
    "principals",
    "principal_id",
    "principal_id",
    "NO ACTION",
    "CASCADE",
    "NONE",
)
SQLITE_FOREIGN_KEYS = {
    "budget_counts": [_CASCADE_TO_PRINCIPALS],
    "target_connections": [_CASCADE_TO_PRINCIPALS],
    "tokens": [
        (
            0,
            0,
            "principals",
            "principal_id",
            "principal_id",
            "NO ACTION",
            "CASCADE",
            "NONE",
        )
    ],
}
# Clauses the pragmas do not show; none may appear in any stored definition.
SQLITE_FORBIDDEN_CLAUSES = (
    "CHECK",
    "COLLATE",
    "DEFAULT",
    "GENERATED",
    "AUTOINCREMENT",
    "CONFLICT",
    "DEFERR",
    "WITHOUT ROWID",
    "STRICT",
)
# The one table definition that may say UNIQUE; its index is pinned above
# (origin "u"), and no other definition may carry the clause.
SQLITE_UNIQUE_ALLOWED_IN = ("target_connections",)

# information_schema.columns:
# (table, column, type, nullable, default, identity, generated)
POSTGRES_COLUMNS = [
    ("budget_counts", "key", "text", "NO", None, "NO", "NEVER"),
    ("budget_counts", "window_start", "bigint", "NO", None, "NO", "NEVER"),
    ("budget_counts", "count", "bigint", "NO", None, "NO", "NEVER"),
    ("budget_counts", "window_end", "bigint", "NO", None, "NO", "NEVER"),
    ("budget_counts", "principal_id", "text", "YES", None, "NO", "NEVER"),
    ("principals", "principal_id", "text", "NO", None, "NO", "NEVER"),
    ("principals", "label", "text", "YES", None, "NO", "NEVER"),
    ("principals", "created_at", "bigint", "NO", None, "NO", "NEVER"),
    ("rate_counts", "key", "text", "NO", None, "NO", "NEVER"),
    ("rate_counts", "window_start", "bigint", "NO", None, "NO", "NEVER"),
    ("rate_counts", "count", "integer", "NO", None, "NO", "NEVER"),
    ("rate_counts", "window_end", "bigint", "NO", None, "NO", "NEVER"),
    ("records", "namespace", "text", "NO", None, "NO", "NEVER"),
    ("records", "key", "text", "NO", None, "NO", "NEVER"),
    ("records", "value", "bytea", "NO", None, "NO", "NEVER"),
    ("records", "expires_at", "bigint", "NO", None, "NO", "NEVER"),
    ("relay_schema", "version", "integer", "NO", None, "NO", "NEVER"),
    ("relay_schema", "name", "text", "NO", None, "NO", "NEVER"),
    ("relay_schema", "applied_at", "bigint", "NO", None, "NO", "NEVER"),
    ("target_connections", "principal_id", "text", "NO", None, "NO", "NEVER"),
    ("target_connections", "target", "text", "NO", None, "NO", "NEVER"),
    ("target_connections", "account_key", "text", "NO", None, "NO", "NEVER"),
    ("target_connections", "access_sealed", "text", "NO", None, "NO", "NEVER"),
    ("target_connections", "refresh_sealed", "text", "YES", None, "NO", "NEVER"),
    ("target_connections", "access_expires_at", "bigint", "YES", None, "NO", "NEVER"),
    ("target_connections", "generation", "bigint", "NO", None, "NO", "NEVER"),
    ("target_connections", "lease_id", "text", "YES", None, "NO", "NEVER"),
    ("target_connections", "lease_until", "bigint", "YES", None, "NO", "NEVER"),
    ("target_connections", "token_id", "text", "YES", None, "NO", "NEVER"),
    ("target_connections", "created_at", "bigint", "NO", None, "NO", "NEVER"),
    ("target_connections", "updated_at", "bigint", "NO", None, "NO", "NEVER"),
    ("tokens", "token_id", "text", "NO", None, "NO", "NEVER"),
    ("tokens", "principal_id", "text", "NO", None, "NO", "NEVER"),
    ("tokens", "verifier", "text", "NO", None, "NO", "NEVER"),
    ("tokens", "label", "text", "YES", None, "NO", "NEVER"),
    ("tokens", "created_at", "bigint", "NO", None, "NO", "NEVER"),
    ("tokens", "revoked_at", "bigint", "YES", None, "NO", "NEVER"),
]
# pg_constraint, every kind (not-null rows excluded: PostgreSQL 18 lists them):
# (table, contype, pg_get_constraintdef)
_PG_CASCADE = (
    "FOREIGN KEY (principal_id) REFERENCES principals(principal_id) ON DELETE CASCADE"
)
POSTGRES_CONSTRAINTS = [
    ("budget_counts", "f", _PG_CASCADE),
    ("budget_counts", "p", "PRIMARY KEY (key, window_start)"),
    ("principals", "p", "PRIMARY KEY (principal_id)"),
    ("rate_counts", "p", "PRIMARY KEY (key, window_start)"),
    ("records", "p", "PRIMARY KEY (namespace, key)"),
    ("relay_schema", "p", "PRIMARY KEY (version)"),
    ("target_connections", "f", _PG_CASCADE),
    ("target_connections", "p", "PRIMARY KEY (principal_id, target)"),
    ("target_connections", "u", "UNIQUE (target, account_key)"),
    (
        "tokens",
        "f",
        "FOREIGN KEY (principal_id) REFERENCES principals(principal_id) "
        "ON DELETE CASCADE",
    ),
    ("tokens", "p", "PRIMARY KEY (token_id)"),
]
# pg_index: (table, index, unique, primary, first column, no predicate,
#            column count, no expression, access method)
POSTGRES_INDEXES = [
    ("budget_counts", "budget_counts_pkey", True, True, "key", True, 2, True, "btree"),
    (
        "budget_counts",
        "budget_counts_window_end_idx",
        False,
        False,
        "window_end",
        True,
        1,
        True,
        "btree",
    ),
    (
        "principals",
        "principals_pkey",
        True,
        True,
        "principal_id",
        True,
        1,
        True,
        "btree",
    ),
    ("rate_counts", "rate_counts_pkey", True, True, "key", True, 2, True, "btree"),
    (
        "rate_counts",
        "rate_counts_window_end_idx",
        False,
        False,
        "window_end",
        True,
        1,
        True,
        "btree",
    ),
    (
        "records",
        "records_expires_at_idx",
        False,
        False,
        "expires_at",
        True,
        1,
        True,
        "btree",
    ),
    ("records", "records_pkey", True, True, "namespace", True, 2, True, "btree"),
    (
        "relay_schema",
        "relay_schema_pkey",
        True,
        True,
        "version",
        True,
        1,
        True,
        "btree",
    ),
    (
        "target_connections",
        "target_connections_pkey",
        True,
        True,
        "principal_id",
        True,
        2,
        True,
        "btree",
    ),
    (
        "target_connections",
        "target_connections_target_account_key_key",
        True,
        False,
        "target",
        True,
        2,
        True,
        "btree",
    ),
    ("tokens", "tokens_pkey", True, True, "token_id", True, 1, True, "btree"),
    (
        "tokens",
        "tokens_principal_id_idx",
        False,
        False,
        "principal_id",
        True,
        1,
        True,
        "btree",
    ),
]
POSTGRES_RELATIONS = [
    ("budget_counts", "r"),
    ("budget_counts_pkey", "i"),
    ("budget_counts_window_end_idx", "i"),
    ("principals", "r"),
    ("principals_pkey", "i"),
    ("rate_counts", "r"),
    ("rate_counts_pkey", "i"),
    ("rate_counts_window_end_idx", "i"),
    ("records", "r"),
    ("records_expires_at_idx", "i"),
    ("records_pkey", "i"),
    ("relay_schema", "r"),
    ("relay_schema_pkey", "i"),
    ("target_connections", "r"),
    ("target_connections_pkey", "i"),
    ("target_connections_target_account_key_key", "i"),
    ("tokens", "r"),
    ("tokens_pkey", "i"),
    ("tokens_principal_id_idx", "i"),
]


def test_the_data_model_is_as_designed_on_each_backend(
    schema_store: SchemaStore, database_target: Target
) -> None:
    migrate(schema_store, now=NOW)
    if isinstance(database_target, SqliteTarget):
        _check_sqlite_model(database_target)
    else:
        _check_postgres_model(database_target)


def _check_sqlite_model(target: SqliteTarget) -> None:
    assert (
        sorted(
            r[0]
            for r in raw(target, "SELECT name FROM sqlite_master WHERE type = 'table'")
        )
        == DESIGNED_TABLES
    )
    assert sorted(
        r[0]
        for r in raw(target, "SELECT name FROM sqlite_master WHERE type <> 'table'")
    ) == sorted(name for rows in SQLITE_INDEXES.values() for name, *_ in rows)
    for table in DESIGNED_TABLES:
        assert raw(target, f"PRAGMA table_xinfo({table})") == SQLITE_COLUMNS[table]
        listed = raw(target, f"PRAGMA index_list({table})")
        assert sorted((r[1], r[2], r[3], r[4]) for r in listed) == SQLITE_INDEXES[table]
        assert raw(target, f"PRAGMA foreign_key_list({table})") == (
            SQLITE_FOREIGN_KEYS.get(table, [])
        )
    for index, columns in SQLITE_INDEX_COLUMNS.items():
        assert [r[2] for r in raw(target, f"PRAGMA index_info({index})")] == columns
    listed_tables = {r[1]: r for r in raw(target, "PRAGMA table_list")}
    for table in DESIGNED_TABLES:
        assert listed_tables[table][4:6] == (0, 0)  # rowid table, not STRICT
    definitions = raw(
        target, "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL"
    )
    assert len(definitions) == 11  # 7 tables and 4 created indexes carry text
    for name, text in definitions:
        for clause in SQLITE_FORBIDDEN_CLAUSES:
            assert clause not in text.upper(), (name, clause)
        assert ("UNIQUE" in text.upper()) == (name in SQLITE_UNIQUE_ALLOWED_IN), name


def _check_postgres_model(target: PostgresTarget) -> None:
    here = "current_schema()::regnamespace"
    assert raw(
        target,
        "SELECT table_name, column_name, data_type, is_nullable, column_default, "
        "is_identity, is_generated, collation_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() "
        "ORDER BY table_name, ordinal_position",
    ) == [(*row, None) for row in POSTGRES_COLUMNS]  # no column collation
    assert raw(
        target,
        "SELECT conrelid::regclass::text, contype, pg_get_constraintdef(oid) "
        f"FROM pg_constraint WHERE connamespace = {here} AND contype <> 'n' "
        "ORDER BY 1, 2, 3",
    ) == [tuple(row) for row in POSTGRES_CONSTRAINTS]
    assert raw(
        target,
        "SELECT t.relname, i.relname, ix.indisunique, ix.indisprimary, "
        "pg_get_indexdef(ix.indexrelid, 1, true), ix.indpred IS NULL, ix.indnatts, "
        "ix.indexprs IS NULL, am.amname FROM pg_index ix "
        "JOIN pg_class t ON t.oid = ix.indrelid "
        "JOIN pg_class i ON i.oid = ix.indexrelid "
        "JOIN pg_am am ON am.oid = i.relam "
        f"WHERE t.relnamespace = {here} ORDER BY 1, 2",
    ) == [tuple(row) for row in POSTGRES_INDEXES]
    assert raw(
        target,
        "SELECT relname, relkind, relpersistence FROM pg_class "
        f"WHERE relnamespace = {here} ORDER BY 1",
    ) == [(*row, "p") for row in POSTGRES_RELATIONS]  # permanent, not UNLOGGED
    assert raw(
        target, f"SELECT count(*) FROM pg_collation WHERE collnamespace = {here}"
    ) == [(0,)]
    assert raw(
        target,
        "SELECT count(*) FROM pg_trigger tg JOIN pg_class t ON t.oid = tg.tgrelid "
        f"WHERE t.relnamespace = {here} AND NOT tg.tgisinternal",
    ) == [(0,)]


def test_deleting_a_principal_cascades_its_tokens_and_a_missing_one_is_refused(
    schema_store: SchemaStore, database_target: Target
) -> None:
    migrate(schema_store, now=NOW)
    marker = param(database_target)
    for principal in ("prn_one", "prn_two"):
        raw(
            database_target,
            f"INSERT INTO principals VALUES ({marker}, NULL, 1)",
            (principal,),
        )
    for token, principal in (("a", "prn_one"), ("b", "prn_one"), ("c", "prn_two")):
        raw(
            database_target,
            f"INSERT INTO tokens VALUES ({marker}, {marker}, 'v', NULL, 1, NULL)",
            (token, principal),
        )
    run: Callable[[str], object]
    violation: type[Exception]
    if isinstance(database_target, SqliteTarget):
        # SQLite enforces foreign keys per connection: use the backend's own.
        from fitdocs_relay.storage.sqlite import SqliteBackend

        assert isinstance(schema_store, SqliteBackend)
        run = schema_store._connect().execute
        violation = sqlite3.IntegrityError
    else:
        import psycopg.errors

        def run(sql: str) -> object:
            return raw(database_target, sql)

        violation = psycopg.errors.ForeignKeyViolation
    with pytest.raises(violation):
        run("INSERT INTO tokens VALUES ('d', 'prn_missing', 'v', NULL, 1, NULL)")
    assert raw(database_target, "SELECT count(*) FROM tokens") == [(3,)]

    run("DELETE FROM principals WHERE principal_id = 'prn_one'")

    assert raw(database_target, "SELECT token_id FROM tokens") == [("c",)]
