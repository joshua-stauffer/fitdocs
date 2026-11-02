"""Schema changes: discovery from package data, and the ordered, idempotent runner.

The changes live beside this module as `migrations/<backend>/NNNN_slug.sql`,
numbered contiguously from 1, with identical file names in both backends'
directories. Each backend's `apply_schema_change` owns the writer lock and the
transaction; this module only orders the changes and calls it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Literal

from fitdocs_relay.storage.interface import (
    SchemaAhead,
    SchemaChange,
    SchemaStore,
    StorageError,
)

CHANGE_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")


@dataclass(frozen=True)
class MigrationReport:
    found: int  # the schema version the database was at when the run began
    left: int  # the schema version it was at when the run ended
    applied: tuple[int, ...]  # the versions this run applied, in order


def migrations_directory(backend: Literal["sqlite", "postgres"]) -> Traversable:
    return files("fitdocs_relay.storage") / "migrations" / backend


def load_changes(directory: Traversable) -> tuple[SchemaChange, ...]:
    """The changes in `directory`, by version; refuses any gap, repeat or stray file."""
    found: dict[int, SchemaChange] = {}
    for entry in directory.iterdir():
        match = CHANGE_NAME.fullmatch(entry.name)
        if not entry.is_file() or match is None:
            raise StorageError(
                f"unexpected entry in the migrations directory: {entry.name}"
            )
        version = int(match.group(1))
        if version in found:
            raise StorageError(f"two schema changes are numbered {version}")
        found[version] = SchemaChange(
            version=version,
            name=entry.name.removesuffix(".sql"),
            sql=entry.read_text(encoding="utf-8"),
        )
    if sorted(found) != list(range(1, len(found) + 1)):
        raise StorageError("schema changes are not numbered contiguously from 1")
    return tuple(found[version] for version in sorted(found))


def schema_changes(
    backend: Literal["sqlite", "postgres"],
) -> tuple[SchemaChange, ...]:
    return load_changes(migrations_directory(backend))


def pending(storage: SchemaStore) -> tuple[SchemaChange, ...]:
    """The changes the database has not yet applied; refuses a newer database."""
    state = storage.schema_state()
    _refuse_ahead(state.current, state.expected)
    return schema_changes(storage.backend)[state.current :]


def migrate(storage: SchemaStore, *, now: int) -> MigrationReport:
    """Apply every pending change in order; a failure leaves the last applied one."""
    state = storage.schema_state()
    _refuse_ahead(state.current, state.expected)
    applied: list[int] = []
    for change in schema_changes(storage.backend)[state.current :]:
        if storage.apply_schema_change(change, now=now):
            applied.append(change.version)
    return MigrationReport(
        found=state.current,
        left=storage.schema_state().current,
        applied=tuple(applied),
    )


def _refuse_ahead(current: int, expected: int) -> None:
    if current > expected:
        raise SchemaAhead(
            f"the database is at schema version {current}, "
            f"newer than this build's {expected}"
        )
