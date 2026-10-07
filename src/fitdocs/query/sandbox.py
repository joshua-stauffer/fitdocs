"""Read-only, bounded access to an analytics index."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
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

SPILL_PREFIX: Final[str] = "query-spill-"
_SKIPS_SPILL_CLEANUP: bool = os.name == "nt"


def spill_directory(location: IndexLocation, pid: int) -> Path:
    return location.directory / f"{SPILL_PREFIX}{pid}"


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_stale_spill(
    location: IndexLocation,
    *,
    own_pid: int,
    is_running: Callable[[int], bool],
) -> tuple[Path, ...]:
    if _SKIPS_SPILL_CLEANUP:
        return ()

    try:
        entries = tuple(location.directory.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return ()

    removed: list[Path] = []
    for entry in entries:
        match = re.fullmatch(r"query-spill-(\d+)", entry.name)
        if match is None or entry.is_symlink() or not entry.is_dir():
            continue
        pid = int(match.group(1))
        if pid == own_pid or is_running(pid):
            continue
        try:
            shutil.rmtree(entry)
        except OSError:
            continue
        removed.append(entry)
    return tuple(removed)


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
            settings = dict(RESOURCE_SETTINGS) | {
                "temp_directory": str(spill_directory(location, pid))
            }
            connection = store.open_index(
                location.database,
                read_only=True,
                settings=settings,
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
