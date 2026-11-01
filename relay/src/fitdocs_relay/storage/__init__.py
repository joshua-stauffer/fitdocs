"""Relay storage: the port in `interface`, one module per backend."""

from __future__ import annotations

from fitdocs_relay.config import DatabaseTarget, PostgresTarget
from fitdocs_relay.storage.interface import Storage

POSTGRES_EXTRA_MESSAGE = (
    "PostgreSQL support is not installed: install the relay with the postgres "
    "extra (pip install 'fitdocs-relay[postgres]')"
)


class MissingPostgresSupport(Exception):
    """The `postgres` extra is not installed."""


def open_storage(target: DatabaseTarget) -> Storage:
    """Open the storage the target names.

    The PostgreSQL backend, and with it the driver, is imported only for a
    PostgreSQL target.
    """
    if isinstance(target, PostgresTarget):
        try:
            from fitdocs_relay.storage.postgres import PostgresBackend
        except ImportError as error:
            if (error.name or "").split(".")[0] == "fitdocs_relay":
                raise  # this package's own import failed: a defect, not the extra
            raise MissingPostgresSupport(POSTGRES_EXTRA_MESSAGE) from error
        postgres: Storage = PostgresBackend(target)
        return postgres
    from fitdocs_relay.storage.sqlite import SqliteBackend

    sqlite: Storage = SqliteBackend(target)
    return sqlite
