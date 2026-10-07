"""Read-only, bounded access to an analytics index."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

from fitdocs.index import store
from fitdocs.index.location import IndexLocation
from fitdocs.index.store import (
    FaultKind,
    IndexConnection,
    IndexOpenError,
    SettingValue,
)

RESOURCE_SETTINGS: Final[Mapping[str, SettingValue]] = {
    "memory_limit": "1GB",
    "threads": 2,
    "max_temp_directory_size": "4GB",
}
REQUIRED_SANDBOX: Final[Mapping[str, str]] = {
    "enable_external_access": "false",
    "autoinstall_known_extensions": "false",
    "autoload_known_extensions": "false",
    "allow_community_extensions": "false",
    "allow_persistent_secrets": "false",
    "python_enable_replacements": "false",
    "lock_configuration": "true",
    "threads": "2",
}
LOCK_RETRY_WINDOW_S: Final[float] = 10.0
LOCK_RETRY_DELAYS_S: Final[tuple[float, ...]] = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 2.0)


class SandboxUnverified(Exception):
    """A required sandbox setting was absent or had the wrong value."""

    def __init__(self, setting: str, expected: str, actual: str | None) -> None:
        self.setting = setting
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"sandbox setting {setting!r}: expected {expected!r}, got {actual!r}"
        )


class IndexBusy(Exception):
    """The index stayed locked for writing through the retry window."""

    def __init__(self, holder_pid: int | None) -> None:
        self.holder_pid = holder_pid
        super().__init__(f"index is busy (holder pid: {holder_pid})")


def verify_sandbox(conn: IndexConnection) -> None:
    """Read back every mandatory sandbox value and fail at the first mismatch."""
    names = tuple(REQUIRED_SANDBOX)
    literals = ", ".join("'" + name.replace("'", "''") + "'" for name in names)
    rows = conn.execute(
        "SELECT name, value FROM duckdb_settings() WHERE name IN (" + literals + ")"
    ).fetchall()
    actual_values = {
        str(name): None if value is None else str(value) for name, value in rows
    }
    for setting, expected in REQUIRED_SANDBOX.items():
        actual = actual_values.get(setting)
        if actual != expected:
            raise SandboxUnverified(setting, expected, actual)


def open_sandboxed(
    location: IndexLocation,
    *,
    pid: int,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    on_wait: Callable[[int | None], None],
) -> IndexConnection:
    """Open and verify the index, retrying only writer-lock failures."""
    started = monotonic()
    retries = 0
    wait_reported = False
    while True:
        try:
            connection = store.open_index(
                location.database,
                read_only=True,
                settings=RESOURCE_SETTINGS,
            )
        except IndexOpenError as error:
            if error.fault.kind is not FaultKind.LOCKED:
                raise
            elapsed = monotonic() - started
            if elapsed >= LOCK_RETRY_WINDOW_S:
                raise IndexBusy(error.fault.holder_pid) from error
            if not wait_reported:
                on_wait(error.fault.holder_pid)
                wait_reported = True
            delay = LOCK_RETRY_DELAYS_S[min(retries, len(LOCK_RETRY_DELAYS_S) - 1)]
            remaining = LOCK_RETRY_WINDOW_S - elapsed
            sleep(min(delay, remaining))
            retries += 1
            continue

        try:
            verify_sandbox(connection)
        except BaseException:
            connection.close()
            raise
        return connection
