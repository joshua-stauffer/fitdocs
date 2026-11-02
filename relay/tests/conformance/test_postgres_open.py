"""Opening the PostgreSQL backend: the pool, the password, and error translation."""

from __future__ import annotations

import traceback
from typing import Any

import psycopg
import psycopg.errors
import psycopg_pool
import pytest

from fitdocs_relay.config import PostgresTarget
from fitdocs_relay.storage import postgres
from fitdocs_relay.storage.interface import StorageError, StorageUnreachable
from fitdocs_relay.storage.postgres import PostgresBackend, is_connection_failure

PLANTED_HOST = "planted-host-4f2a.invalid"
PLANTED_PASSWORD = "planted-password-7c1e"  # noqa: S105


def shown(error: BaseException) -> str:
    return "".join(traceback.format_exception(error)) + repr(error) + str(error)


@pytest.mark.parametrize(
    "conninfo",
    [
        f"host={PLANTED_HOST} port=1 dbname=none user=planted_user connect_timeout=2",
        "host=127.0.0.1 port=1 dbname=none user=planted_user connect_timeout=2",
    ],
)
def test_a_connection_failure_is_the_unreachable_error_without_the_driver_message(
    conninfo: str,
) -> None:
    target = PostgresTarget(conninfo=conninfo, password=PLANTED_PASSWORD)
    with pytest.raises(StorageUnreachable) as raised:
        PostgresBackend(target)
    text = shown(raised.value)
    for planted in (PLANTED_HOST, "planted_user", PLANTED_PASSWORD, "127.0.0.1"):
        assert planted not in text
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_the_pool_is_capped_and_the_password_is_passed_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeConnection:
        def close(self) -> None:
            seen["probe_closed"] = True

    def fake_connect(conninfo: str, **kwargs: object) -> FakeConnection:
        seen["probe"] = (conninfo, kwargs)
        return FakeConnection()

    class FakePool:
        def __init__(self, conninfo: str, **kwargs: object) -> None:
            seen["pool"] = (conninfo, kwargs)

        def open(self, **kwargs: object) -> None:
            seen["open"] = kwargs

        def close(self) -> None:
            seen["closed"] = True

    monkeypatch.setattr("fitdocs_relay.storage.postgres.psycopg.connect", fake_connect)
    monkeypatch.setattr(
        "fitdocs_relay.storage.postgres.psycopg_pool.ConnectionPool", FakePool
    )
    conninfo = "host=db.example dbname=relay"

    PostgresBackend(PostgresTarget(conninfo=conninfo, password=PLANTED_PASSWORD))

    pool_conninfo, pool_kwargs = seen["pool"]
    assert pool_conninfo == conninfo
    assert PLANTED_PASSWORD not in pool_conninfo
    assert pool_kwargs["kwargs"] == {"password": PLANTED_PASSWORD}
    assert (pool_kwargs["min_size"], pool_kwargs["max_size"]) == (1, 8)
    assert seen["probe"] == (conninfo, {"password": PLANTED_PASSWORD})
    assert seen["open"] == {"wait": True, "timeout": postgres.POOL_TIMEOUT_S}


def test_no_password_means_no_password_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeConnection:
        def close(self) -> None:
            return None

    class FakePool:
        def __init__(self, conninfo: str, **kwargs: object) -> None:
            seen["kwargs"] = kwargs["kwargs"]

        def open(self, **kwargs: object) -> None:
            return None

    monkeypatch.setattr(
        "fitdocs_relay.storage.postgres.psycopg.connect",
        lambda conninfo, **kwargs: FakeConnection(),
    )
    monkeypatch.setattr(
        "fitdocs_relay.storage.postgres.psycopg_pool.ConnectionPool", FakePool
    )

    PostgresBackend(PostgresTarget(conninfo="dbname=relay", password=None))

    assert seen["kwargs"] == {}


def test_the_pool_on_a_real_server_has_one_to_eight_connections(
    postgres_test_url: str,
) -> None:
    backend = PostgresBackend(PostgresTarget(conninfo=postgres_test_url, password=None))
    try:
        assert (backend._pool.min_size, backend._pool.max_size) == (1, 8)
        backend.ping()
        assert not backend._pool.closed
    finally:
        backend.close()
    assert backend._pool.closed


E = psycopg.errors
CLASSIFIED: list[tuple[psycopg.Error, bool]] = [
    # genuine connection failures: no SQLSTATE (client side), class 08, the
    # server going away or refusing (57P01-57P03, 53300), class 28, the pool
    (psycopg.OperationalError("x"), True),
    (E.ConnectionException("x"), True),
    (E.ConnectionFailure("x"), True),
    (E.SqlclientUnableToEstablishSqlconnection("x"), True),
    (E.AdminShutdown("x"), True),
    (E.CrashShutdown("x"), True),
    (E.CannotConnectNow("x"), True),
    (E.TooManyConnections("x"), True),
    (E.InvalidAuthorizationSpecification("x"), True),
    (E.InvalidPassword("x"), True),
    (psycopg_pool.PoolTimeout("x"), True),
    (psycopg_pool.PoolClosed("x"), True),
    # statement failures, including the other OperationalError subclasses
    (E.DeadlockDetected("x"), False),
    (E.SerializationFailure("x"), False),
    (E.QueryCanceled("x"), False),
    (E.LockNotAvailable("x"), False),
    (E.DiskFull("x"), False),
    (E.OutOfMemory("x"), False),
    (E.UndefinedTable("x"), False),
    (psycopg.ProgrammingError("x"), False),
    (psycopg.IntegrityError("x"), False),
    (psycopg.DataError("x"), False),
]


@pytest.mark.parametrize(
    ("error", "unreachable"),
    CLASSIFIED,
    ids=[f"{type(e).__name__}-{u}" for e, u in CLASSIFIED],
)
def test_driver_errors_are_classified_as_unreachable_or_failed(
    error: psycopg.Error, unreachable: bool
) -> None:
    assert is_connection_failure(error) is unreachable
    with pytest.raises(StorageUnreachable if unreachable else StorageError) as raised:

        def work() -> None:
            raise error

        postgres._guarded(work)
    assert isinstance(raised.value, StorageUnreachable) is unreachable
    assert str(raised.value) == (
        "the PostgreSQL database cannot be reached"
        if unreachable
        else "the PostgreSQL database reported an error"
    )
