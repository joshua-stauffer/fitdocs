"""Connection policy and small typed facade for the analytics DuckDB index."""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from importlib.metadata import version as _distribution_version
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NoReturn, cast

from fitdocs.index.bookkeeping import (
    Bookkeeping,
    ComputedState,
    IndexMeta,
    PageState,
)
from fitdocs.index.schema import ColumnType, ResolvedTable, TableScope

if TYPE_CHECKING:
    import duckdb

    from fitdocs.index.producer import Row

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


class RowShapeError(ValueError):
    """A producer row does not match its declared table schema."""


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


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _column_definition_type(column_type: ColumnType) -> str:
    return column_type.value


def apply_descriptions(conn: IndexConnection, tables: Sequence[ResolvedTable]) -> None:
    """Apply the declared table and column descriptions as DuckDB comments."""
    for table in tables:
        table_name = _quote_identifier(table.name)
        conn.execute(
            f"COMMENT ON TABLE {table_name} IS {_quote_literal(table.description)}"
        )
        for column in table.columns:
            conn.execute(
                f"COMMENT ON COLUMN {table_name}.{_quote_identifier(column.name)} "
                f"IS {_quote_literal(column.description)}"
            )


def create_schema(conn: IndexConnection, tables: Sequence[ResolvedTable]) -> None:
    """Create nullable tables without constraints, then write all descriptions."""
    for table in tables:
        definitions = ", ".join(
            f"{_quote_identifier(column.name)} {_column_definition_type(column.type)}"
            for column in table.columns
        )
        conn.execute(f"CREATE TABLE {_quote_identifier(table.name)} ({definitions})")
    apply_descriptions(conn, tables)


@contextmanager
def transaction(conn: IndexConnection) -> Iterator[None]:
    """Commit on success; roll back and re-raise the same exception on failure."""
    conn.execute("BEGIN")
    try:
        yield
    except BaseException:
        with suppress(BaseException):
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _validate_value(value: object, column_type: ColumnType, column_name: str) -> None:
    if value is None:
        return
    valid = False
    if column_type is ColumnType.VARCHAR:
        valid = type(value) is str
    elif column_type is ColumnType.BOOLEAN:
        valid = type(value) is bool
    elif column_type in (ColumnType.INTEGER, ColumnType.BIGINT):
        valid = type(value) is int
    elif column_type is ColumnType.DOUBLE:
        valid = type(value) in (int, float)
    elif column_type is ColumnType.DATE:
        valid = type(value) is date
    elif column_type is ColumnType.TIMESTAMP:
        valid = isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() is None
        )
    elif column_type is ColumnType.VARCHAR_LIST:
        valid = isinstance(value, tuple) and all(type(item) is str for item in value)
    if not valid:
        raise RowShapeError(
            f"value for column {column_name!r} does not match {column_type.value}"
        )


def _json_value(value: object, column_type: ColumnType) -> object:
    if value is None:
        return None
    if column_type is ColumnType.DATE:
        assert isinstance(value, date)
        return value.isoformat()
    if column_type is ColumnType.TIMESTAMP:
        assert isinstance(value, datetime)
        return value.isoformat(timespec="microseconds")
    if column_type is ColumnType.VARCHAR_LIST:
        assert isinstance(value, tuple)
        return list(value)
    if (
        column_type is ColumnType.DOUBLE
        and isinstance(value, float)
        and not math.isfinite(value)
    ):
        return None
    return value


def insert_rows(
    conn: IndexConnection,
    table: ResolvedTable,
    rows: Sequence[Row],
    *,
    page_key: str | None,
) -> int:
    """Insert ordered producer rows through one typed JSON-columnar statement."""
    per_page = table.scope in (TableScope.DOCUMENT, TableScope.COMPUTED)
    if per_page != (page_key is not None):
        raise RowShapeError("page_key must be supplied only for per-page tables")
    expected_columns = table.columns[1:] if per_page else table.columns
    for row in rows:
        if not isinstance(row, tuple) or len(row) != len(expected_columns):
            raise RowShapeError(
                f"table {table.name!r} expects rows with {len(expected_columns)} values"
            )
        for value, column in zip(row, expected_columns, strict=True):
            _validate_value(value, column.type, column.name)
    if not rows:
        return 0

    column_values: dict[str, list[object]] = {}
    for index, column in enumerate(expected_columns):
        column_values[f"c{index}"] = [
            _json_value(row[index], column.type) for row in rows
        ]
    payload = json.dumps(column_values, allow_nan=False, separators=(",", ":"))
    json_fields: dict[str, object] = {}
    for index, column in enumerate(expected_columns):
        field_type = column.type.value
        if column.type is ColumnType.VARCHAR_LIST:
            json_fields[f"c{index}"] = [[ColumnType.VARCHAR.value]]
        else:
            json_fields[f"c{index}"] = [field_type]
    json_type = json.dumps(json_fields, separators=(",", ":"))

    target_columns = table.columns
    selected = []
    parameters: tuple[object, ...]
    if per_page:
        selected.append("$2")
        parameters = (payload, page_key)
    else:
        parameters = (payload,)
    for index, column in enumerate(expected_columns):
        if column.type is ColumnType.VARCHAR_LIST:
            selected.append(f"unnest(j.c{index}, max_depth := 1)")
        else:
            selected.append(f"unnest(j.c{index})")
    target = ", ".join(_quote_identifier(column.name) for column in target_columns)
    select_values = ", ".join(selected)
    conn.execute(
        f"INSERT INTO {_quote_identifier(table.name)} ({target}) "
        f"SELECT {select_values} FROM (SELECT from_json($1, "
        f"{_quote_literal(json_type)}) AS j)",
        parameters,
    )
    return len(rows)


def replace_table_rows(
    conn: IndexConnection, table: ResolvedTable, rows: Sequence[Row]
) -> int:
    """Replace every row in a whole-table producer table."""
    if table.scope in (TableScope.DOCUMENT, TableScope.COMPUTED):
        raise RowShapeError("per-page tables must be replaced with a page key")
    conn.execute(f"DELETE FROM {_quote_identifier(table.name)}")
    return insert_rows(conn, table, rows, page_key=None)


def delete_page_rows(
    conn: IndexConnection, page_key: str, tables: Sequence[ResolvedTable]
) -> None:
    """Delete a page's rows from document and computed producer tables."""
    for table in tables:
        if table.scope not in (TableScope.DOCUMENT, TableScope.COMPUTED):
            continue
        conn.execute(
            f"DELETE FROM {_quote_identifier(table.name)} WHERE page_key = $1",
            (page_key,),
        )


def read_bookkeeping(conn: IndexConnection) -> Bookkeeping | None:
    """Read the unique meta row and all page/producer bookkeeping when present."""
    meta_table = conn.execute(
        "SELECT table_name FROM duckdb_tables() WHERE table_name = 'index_meta'"
    ).fetchall()
    if not meta_table:
        return None
    meta_rows = conn.execute(
        "SELECT schema_version, fitdocs_version, duckdb_version, data_root, "
        "athlete_fingerprint FROM index_meta"
    ).fetchall()
    if len(meta_rows) != 1:
        return None
    schema_version, fitdocs_version, duckdb_version_value, data_root, athlete_fp = (
        meta_rows[0]
    )
    meta = IndexMeta(
        schema_version=int(cast(int, schema_version)),
        fitdocs_version=cast(str | None, fitdocs_version),
        duckdb_version=str(duckdb_version_value),
        data_root=str(data_root),
        athlete_fingerprint=str(athlete_fp),
    )
    page_rows = conn.execute(
        "SELECT page_key, path, document_fingerprint, render_fingerprint, "
        "computed_state FROM index_pages"
    ).fetchall()
    pages = {
        str(page_key): PageState(
            page_key=str(page_key),
            path=str(path),
            document_fingerprint=str(document_fingerprint),
            render_fingerprint=cast(str | None, render_fingerprint),
            computed_state=ComputedState(str(computed_state)),
        )
        for (
            page_key,
            path,
            document_fingerprint,
            render_fingerprint,
            computed_state,
        ) in page_rows
    }
    producer_rows = conn.execute(
        "SELECT producer, fingerprint FROM index_producers"
    ).fetchall()
    producers: dict[str, str | None] = {
        str(name): cast(str | None, fingerprint) for name, fingerprint in producer_rows
    }
    return Bookkeeping(meta=meta, pages=pages, producers=producers)


def write_meta(conn: IndexConnection, meta: IndexMeta) -> None:
    conn.execute("DELETE FROM index_meta")
    conn.execute(
        "INSERT INTO index_meta VALUES ($1, $2, $3, $4, $5)",
        (
            meta.schema_version,
            meta.fitdocs_version,
            meta.duckdb_version,
            meta.data_root,
            meta.athlete_fingerprint,
        ),
    )


def write_page_state(conn: IndexConnection, state: PageState) -> None:
    delete_page_state(conn, state.page_key)
    conn.execute(
        "INSERT INTO index_pages VALUES ($1, $2, $3, $4, $5)",
        (
            state.page_key,
            state.path,
            state.document_fingerprint,
            state.render_fingerprint,
            state.computed_state.value,
        ),
    )


def delete_page_state(conn: IndexConnection, page_key: str) -> None:
    conn.execute("DELETE FROM index_pages WHERE page_key = $1", (page_key,))


def write_producer_state(
    conn: IndexConnection,
    name: str,
    kind: TableScope,
    tables: Sequence[str],
    fingerprint: str | None,
) -> None:
    conn.execute("DELETE FROM index_producers WHERE producer = $1", (name,))
    conn.execute(
        "INSERT INTO index_producers VALUES ($1, $2, $3, $4)",
        (name, kind.value, list(tables), fingerprint),
    )


def checkpoint(conn: IndexConnection) -> None:
    conn.execute("CHECKPOINT")
