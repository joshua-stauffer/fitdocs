"""Shared plumbing for the rate-limit, record and serving-claim conformance tests."""

from __future__ import annotations

import sqlite3
from typing import Any

from fitdocs_relay.config import PostgresTarget, SqliteTarget

Target = SqliteTarget | PostgresTarget


def raw(target: Target, sql: str, params: tuple[object, ...] = ()) -> list[Any]:
    """Run SQL on the test database outside the backend under test.

    Placeholders are written `?` and become `%s` on PostgreSQL.
    """
    if isinstance(target, SqliteTarget):
        connection = sqlite3.connect(target.path, isolation_level=None)
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()
    import psycopg

    with psycopg.connect(target.conninfo, autocommit=True) as pg:
        cursor = pg.execute(sql.replace("?", "%s"), params)
        return cursor.fetchall() if cursor.description else []
