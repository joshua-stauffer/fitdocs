"""Connection policy and small typed facade for the analytics DuckDB index."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version as _distribution_version
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NoReturn

if TYPE_CHECKING:
    import duckdb

SettingValue = str | int | bool
MANDATORY_SETTINGS: Final[Mapping[str, SettingValue]] = MappingProxyType(
    {
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "allow_community_extensions": False,
        "allow_persistent_secrets": False,
        "enable_external_access": False,
        "python_enable_replacements": False,
        "lock_configuration": True,
    }
)
WRITER_SETTINGS: Final[Mapping[str, SettingValue]] = MappingProxyType(
    {"storage_compatibility_version": "v1.0.0"}
)
WRITER_SPILL_DIRNAME: Final[str] = "writer-spill"


class FaultKind(StrEnum):
    LOCKED = "locked"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    CORRUPT = "corrupt"
    OTHER = "other"


@dataclass(frozen=True)
class IndexFault:
    kind: FaultKind
    message: str
    holder_pid: int | None


class IndexOpenError(Exception):
    def __init__(self, fault: IndexFault) -> None:
        self.fault = fault
        super().__init__(fault.message)


class IndexStatementError(Exception):
    """A DuckDB statement failed during execute or fetch."""


class IndexInterrupted(Exception):
    """DuckDB stopped a statement after its connection was interrupted."""


class _DuckDBErrorTypes:
    def __init__(
        self,
        error_type: type[BaseException],
        interrupt_type: type[BaseException],
    ) -> None:
        self.error_type = error_type
        self.interrupt_type = interrupt_type

    def raise_statement_error(self, error: BaseException) -> NoReturn:
        if isinstance(error, self.interrupt_type):
            raise IndexInterrupted(str(error)) from error
        raise IndexStatementError(str(error)) from error


@dataclass(frozen=True)
class ResultColumn:
    name: str
    type_name: str


class IndexResult:
    def __init__(
        self, relation: duckdb.DuckDBPyRelation | None, errors: _DuckDBErrorTypes
    ):
        self._relation = relation
        self._errors = errors

    @property
    def columns(self) -> tuple[ResultColumn, ...]:
        if self._relation is None:
            return ()
        return tuple(
            ResultColumn(str(name), str(type_name))
            for name, type_name in zip(
                self._relation.columns, self._relation.types, strict=True
            )
        )

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        try:
            if self._relation is None:
                return []
            return self._relation.fetchmany(size)
        except self._errors.error_type as error:
            self._errors.raise_statement_error(error)

    def fetchall(self) -> list[tuple[object, ...]]:
        try:
            if self._relation is None:
                return []
            return self._relation.fetchall()
        except self._errors.error_type as error:
            self._errors.raise_statement_error(error)


class IndexConnection:
    def __init__(
        self, connection: duckdb.DuckDBPyConnection, errors: _DuckDBErrorTypes
    ) -> None:
        self._connection = connection
        self._errors = errors

    def execute(self, sql: str, params: Sequence[object] = ()) -> IndexResult:
        try:
            relation = self._connection.sql(sql, params=params)
        except self._errors.error_type as error:
            self._errors.raise_statement_error(error)
        return IndexResult(relation, self._errors)

    def interrupt(self) -> None:
        self._connection.interrupt()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> IndexConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def classify_error(error: BaseException) -> IndexFault:
    """Classify real DuckDB failures by stable message stems."""
    duckdb_module = sys.modules.get("duckdb")
    error_type = getattr(duckdb_module, "Error", None)
    message = str(error)
    if not isinstance(error_type, type) or not isinstance(error, error_type):
        return IndexFault(FaultKind.OTHER, message, None)

    if "Could not set lock on file" in message:
        pid_match = re.search(r"\(PID (\d+)\)", message)
        holder_pid = int(pid_match.group(1)) if pid_match is not None else None
        return IndexFault(FaultKind.LOCKED, message, holder_pid)
    if "database does not exist" in message or "No such file or directory" in message:
        return IndexFault(FaultKind.MISSING, message, None)
    if "Trying to read a database file with version number" in message:
        return IndexFault(FaultKind.INCOMPATIBLE, message, None)
    if any(
        stem in message
        for stem in (
            "Corrupt database file",
            "is not a valid DuckDB database file",
            "Could not read enough bytes",
        )
    ):
        return IndexFault(FaultKind.CORRUPT, message, None)
    return IndexFault(FaultKind.OTHER, message, None)


def duckdb_version() -> str:
    """Return the installed DuckDB distribution version without importing it."""
    return _distribution_version("duckdb")


def _connect(
    path: Path,
    *,
    read_only: bool,
    config: Mapping[str, SettingValue],
) -> IndexConnection:
    import duckdb

    try:
        connection = duckdb.connect(str(path), read_only=read_only, config=dict(config))
    except duckdb.Error as error:
        raise IndexOpenError(classify_error(error)) from error
    errors = _DuckDBErrorTypes(duckdb.Error, duckdb.InterruptException)
    return IndexConnection(connection, errors)


def open_index(
    path: Path,
    *,
    read_only: bool,
    settings: Mapping[str, SettingValue] = MappingProxyType({}),
) -> IndexConnection:
    """Open an index with locked safety settings and writer-only policy."""
    for name, required in MANDATORY_SETTINGS.items():
        if name in settings:
            supplied = settings[name]
            if type(supplied) is not type(required) or supplied != required:
                raise ValueError(f"mandatory setting {name!r} cannot be overridden")
    config: dict[str, SettingValue] = dict(MANDATORY_SETTINGS)
    config.update(settings)
    if not read_only:
        config.update(WRITER_SETTINGS)
        config["temp_directory"] = str(path.parent / WRITER_SPILL_DIRNAME)
    return _connect(path, read_only=read_only, config=config)


def create_index(path: Path) -> IndexConnection:
    """Create a new writable index and refuse to overwrite any existing path."""
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"index already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return open_index(path, read_only=False)
