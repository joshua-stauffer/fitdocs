"""Test harness: environment isolation, the test pepper, backend fixtures.

Two variables drive the PostgreSQL half of the conformance suite:

- `FITDOCS_RELAY_TEST_POSTGRES_URL`: a server the suite may create schemas in;
- `FITDOCS_RELAY_REQUIRE_POSTGRES=1`: an unset URL then fails the PostgreSQL
  cases instead of skipping them.

Neither is a contract variable (`load_config` refuses any unknown
`FITDOCS_RELAY_*` name), so both are read once, when this module is imported,
and every `FITDOCS_RELAY_*` name is then removed from the environment of every
test. Subprocess tests must build their environment without them.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Protocol

import pytest

from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.contract import ENV_PREFIX
from fitdocs_relay.storage import interface
from fitdocs_relay.storage.interface import (
    PrincipalStore,
    RateLimitStore,
    RecordStore,
    SchemaStore,
    ServingStore,
    TokenStore,
)
from fitdocs_relay.storage.migrate import migrate

TEST_POSTGRES_URL_VARIABLE = ENV_PREFIX + "TEST_POSTGRES_URL"
REQUIRE_POSTGRES_VARIABLE = ENV_PREFIX + "REQUIRE_POSTGRES"

# Captured once; the autouse fixture below removes them from os.environ.
_POSTGRES_URL: str | None = os.environ.get(TEST_POSTGRES_URL_VARIABLE) or None
_REQUIRE_POSTGRES: bool = os.environ.get(REQUIRE_POSTGRES_VARIABLE) == "1"

# A fixed, test-only pepper (at least the contract's minimum length).
TEST_PEPPER = "test-pepper-not-a-secret-0123456789abcdefghijklmnopqrstuv"

COVERS_MARKER = "covers"
_COVERS_KEY = pytest.StashKey[list[tuple[str, tuple[object, ...]]]]()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{COVERS_MARKER}(*members): the Storage protocol members this test "
        'covers, each "<declaring protocol>.<member>", e.g. "TokenStore.find_token"',
    )


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    config.stash[_COVERS_KEY] = [
        (
            item.nodeid,
            tuple(arg for m in item.iter_markers(COVERS_MARKER) for arg in m.args),
        )
        for item in items
        if any(True for _ in item.iter_markers(COVERS_MARKER))
    ]


# --- environment ------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_relay_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `FITDOCS_RELAY_*` name reaches a test, so `load_config` sees only its own."""
    for name in [n for n in os.environ if n.startswith(ENV_PREFIX)]:
        monkeypatch.delenv(name)


@pytest.fixture
def test_pepper() -> str:
    return TEST_PEPPER


# --- the coverage marker ----------------------------------------------------


def _members_of(root: type) -> set[str]:
    """`<declaring protocol>.<member>` for every member of the protocol `root`.

    Walks the protocol classes in `root`'s MRO defined in `root`'s own module,
    and reads each one's own namespace and annotations.
    """
    members: set[str] = set()
    for cls in root.__mro__:
        if cls.__module__ != root.__module__ or not getattr(cls, "_is_protocol", False):
            continue
        declared = {
            name
            for name, value in vars(cls).items()
            if callable(value) or isinstance(value, property)
        } | set(vars(cls).get("__annotations__", {}))
        members |= {
            f"{cls.__name__}.{name}" for name in declared if not name.startswith("_")
        }
    return members


@pytest.fixture(scope="session")
def storage_members() -> set[str]:
    members = _members_of(interface.Storage)
    assert members, "the member enumeration found nothing"
    return members


@pytest.fixture(scope="session")
def members_of() -> Callable[[type], set[str]]:
    return _members_of


def _problems(
    collected: Sequence[tuple[str, Sequence[object]]], members: set[str]
) -> list[str]:
    problems: list[str] = []
    for nodeid, names in collected:
        if not names:
            problems.append(f"{nodeid}: covers() names nothing")
        for name in names:
            if not isinstance(name, str):
                problems.append(f"{nodeid}: covers() argument {name!r} is not a string")
            elif name not in members:
                problems.append(f"{nodeid}: {name!r} is not a Storage member")
    return problems


@pytest.fixture(scope="session")
def marker_problems(
    storage_members: set[str],
) -> Callable[[Sequence[tuple[str, Sequence[object]]]], list[str]]:
    def check(collected: Sequence[tuple[str, Sequence[object]]]) -> list[str]:
        return _problems(collected, storage_members)

    return check


@pytest.fixture
def collected_covers(
    pytestconfig: pytest.Config,
) -> list[tuple[str, tuple[object, ...]]]:
    return pytestconfig.stash[_COVERS_KEY]


# --- backends ---------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_test_url() -> str:
    """The test server URL; skips, or fails under the require flag, when unset."""
    if _POSTGRES_URL is not None:
        return _POSTGRES_URL
    if _REQUIRE_POSTGRES:
        pytest.fail(
            f"{REQUIRE_POSTGRES_VARIABLE}=1 but "
            f"{TEST_POSTGRES_URL_VARIABLE} is not set",
            pytrace=False,
        )
    pytest.skip(f"{TEST_POSTGRES_URL_VARIABLE} is not set")


@pytest.fixture(params=["sqlite", "postgres"])
def database_target(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[SqliteTarget | PostgresTarget]:
    """A fresh, empty database location on each backend.

    SQLite: a path in the test's temporary directory (the file does not exist
    yet). PostgreSQL: an empty schema created on the test server, selected by
    the connection's `search_path` and dropped on teardown.
    """
    if request.param == "sqlite":
        yield SqliteTarget(path=tmp_path / "relay.sqlite3")
        return
    url: str = request.getfixturevalue("postgres_test_url")
    yield from _postgres_schema(url)


def _postgres_schema(url: str) -> Iterator[PostgresTarget]:
    # Driver use in the tests: this fixture creates and drops the per-test schema;
    # test_harness.py also imports psycopg to inspect that schema.
    try:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
    except ImportError:
        pytest.fail(
            f"{TEST_POSTGRES_URL_VARIABLE} is set but psycopg is not installed "
            "(sync with the relay postgres extra)",
            pytrace=False,
        )
    schema = f"relay_test_{uuid.uuid4().hex}"
    try:
        admin = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError as error:
        pytest.fail(
            f"{TEST_POSTGRES_URL_VARIABLE} is set but the server is unreachable: "
            f"{type(error).__name__}",
            pytrace=False,
        )
    with admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield PostgresTarget(
                conninfo=make_conninfo(url, options=f"-csearch_path={schema}"),
                password=None,
            )
        finally:
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.fixture
def open_schema_store(
    database_target: SqliteTarget | PostgresTarget,
) -> Iterator[Callable[[], SchemaStore]]:
    """Open another backend instance on the test's database.

    Every instance opened is closed on teardown through `StorageBase.close`,
    before `database_target` drops the PostgreSQL schema. The instances are
    typed by the one area protocol the schema tests exercise.
    """
    opened: list[SchemaStore] = []

    def open_one() -> SchemaStore:
        store: SchemaStore
        if isinstance(database_target, SqliteTarget):
            from fitdocs_relay.storage.sqlite import SqliteBackend

            store = SqliteBackend(database_target)
        else:
            from fitdocs_relay.storage.postgres import PostgresBackend

            store = PostgresBackend(database_target)
        opened.append(store)
        return store

    yield open_one
    for store in opened:
        store.close()


@pytest.fixture
def schema_store(open_schema_store: Callable[[], SchemaStore]) -> SchemaStore:
    """A backend on a fresh, empty database, typed as the schema area."""
    return open_schema_store()


# Ids whose byte order differs from a locale-aware order (case, '_' and digits):
# bytes sort A_b, Z, _z, a1, aB, a_b, ab.
TIED_IDS = ["ab", "Z", "a_b", "aB", "_z", "A_b", "a1"]
BYTE_ORDER = ["A_b", "Z", "_z", "a1", "aB", "a_b", "ab"]


class AccountStore(PrincipalStore, TokenStore, Protocol):
    """The two areas the principal and token conformance tests exercise."""


@pytest.fixture
def open_account_store(
    database_target: SqliteTarget | PostgresTarget,
) -> Iterator[Callable[[], AccountStore]]:
    """Open a backend instance on the test's database, migrated to the build.

    Every instance opened is closed on teardown, before `database_target`
    drops the PostgreSQL schema.
    """
    opened: list[AccountStore] = []

    def open_one() -> AccountStore:
        if isinstance(database_target, SqliteTarget):
            from fitdocs_relay.storage.sqlite import SqliteBackend

            sqlite = SqliteBackend(database_target)
            migrate(sqlite, now=1)
            store: AccountStore = sqlite
        else:
            from fitdocs_relay.storage.postgres import PostgresBackend

            postgres = PostgresBackend(database_target)
            migrate(postgres, now=1)
            store = postgres
        opened.append(store)
        return store

    yield open_one
    for store in opened:
        store.close()


@pytest.fixture
def account_store(open_account_store: Callable[[], AccountStore]) -> AccountStore:
    """A migrated, empty backend, typed as the principal and token areas."""
    return open_account_store()


class StateStore(RateLimitStore, RecordStore, ServingStore, Protocol):
    """The three areas the rate-limit, record and serving-claim tests exercise."""


@pytest.fixture
def second_database_target(
    database_target: SqliteTarget | PostgresTarget,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[SqliteTarget | PostgresTarget]:
    """A second, different database location of the same backend kind.

    SQLite: another file in the test's temporary directory. PostgreSQL: another
    empty schema on the same server, dropped on teardown.
    """
    if isinstance(database_target, SqliteTarget):
        yield SqliteTarget(path=tmp_path / "other.sqlite3")
        return
    url: str = request.getfixturevalue("postgres_test_url")
    yield from _postgres_schema(url)


@pytest.fixture
def open_state_store(
    database_target: SqliteTarget | PostgresTarget,
) -> Iterator[Callable[[SqliteTarget | PostgresTarget | None], StateStore]]:
    """Open a backend instance, migrated to the build, on the test's database
    (or on the target given). Every instance opened is closed on teardown,
    before `database_target` drops the PostgreSQL schema.
    """
    opened: list[StateStore] = []

    def open_one(target: SqliteTarget | PostgresTarget | None = None) -> StateStore:
        chosen = database_target if target is None else target
        if isinstance(chosen, SqliteTarget):
            from fitdocs_relay.storage.sqlite import SqliteBackend

            sqlite = SqliteBackend(chosen)
            migrate(sqlite, now=1)
            store: StateStore = sqlite
        else:
            from fitdocs_relay.storage.postgres import PostgresBackend

            postgres = PostgresBackend(chosen)
            migrate(postgres, now=1)
            store = postgres
        opened.append(store)
        return store

    yield open_one
    for store in opened:
        store.close()


@pytest.fixture
def state_store(
    open_state_store: Callable[[SqliteTarget | PostgresTarget | None], StateStore],
) -> StateStore:
    """A migrated, empty backend, typed as the rate-limit, record and claim areas."""
    return open_state_store(None)


@pytest.fixture
def ids_sort_by_locale_here(
    database_target: SqliteTarget | PostgresTarget,
) -> None:
    """On PostgreSQL, assert the database's own collation orders `TIED_IDS`
    differently from bytes; otherwise an ordering test cannot tell `COLLATE "C"`
    from its absence. A no-op on SQLite, whose ordering is always bytes."""
    if isinstance(database_target, SqliteTarget):
        return
    import psycopg

    with psycopg.connect(database_target.conninfo, autocommit=True) as connection:
        rows = connection.execute(
            "SELECT x FROM unnest(%s::text[]) AS x ORDER BY x", (TIED_IDS,)
        ).fetchall()
    assert [r[0] for r in rows] != BYTE_ORDER, (
        "the database collation orders the ids as bytes: "
        "this ordering check is vacuous here"
    )
