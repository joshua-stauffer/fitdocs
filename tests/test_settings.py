"""The shared, one-time read of the user-owned settings file.

These exercise :func:`fitdocs.settings.load_settings_document` and
:func:`fitdocs.layout.settings_path` -- the settings-foundation contract every
per-table reader (``[tiles]``, and later ``[inbox]`` and ``[plugins]``) is built
on. The properties that matter to those readers are that an absent file is not an
error, that file-level faults have exactly one voice, and that the file is read
through one helper so two readers can never disagree about which file they read.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from fitdocs.layout import SETTINGS_FILE, settings_path
from fitdocs.settings import SettingsError, load_settings_document


def _write_settings(root: Path, text: str) -> Path:
    path = root / SETTINGS_FILE
    path.write_text(text, encoding="utf-8")
    return path


# --- Locating the file -------------------------------------------------------


def test_settings_path_is_the_data_root_file(tmp_path: Path) -> None:
    """The settings file is ``<data-root>/fitdocs.toml`` and nothing else."""
    assert settings_path(tmp_path) == tmp_path / "fitdocs.toml"
    assert SETTINGS_FILE == "fitdocs.toml"


# --- Absent is not an error --------------------------------------------------


def test_absent_file_yields_empty_mapping(tmp_path: Path) -> None:
    """No settings file means no configuration -- an empty mapping, never a raise.

    Every table reader falls back to its documented defaults from this, so the
    keyless first run needs no file at all.
    """
    assert load_settings_document(tmp_path) == {}


def test_empty_file_yields_empty_mapping(tmp_path: Path) -> None:
    """A file that exists but declares nothing is equivalent to no file."""
    _write_settings(tmp_path, "")

    assert load_settings_document(tmp_path) == {}


# --- Parsing -----------------------------------------------------------------


def test_tables_are_returned_verbatim(tmp_path: Path) -> None:
    """Every table is returned as parsed; this reader validates nothing itself."""
    _write_settings(
        tmp_path,
        '[tiles]\nname = "osm"\n\n[inbox]\nenabled = true\n\n[plugins]\npath = "p"\n',
    )

    document = load_settings_document(tmp_path)

    assert document == {
        "tiles": {"name": "osm"},
        "inbox": {"enabled": True},
        "plugins": {"path": "p"},
    }


def test_unknown_tables_are_preserved_not_rejected(tmp_path: Path) -> None:
    """A table this version does not know is passed through, not an error.

    Forward compatibility: an older fitdocs reading a newer file must not fail on
    a table it has no reader for.
    """
    _write_settings(tmp_path, '[future]\nkey = "value"\n')

    assert load_settings_document(tmp_path) == {"future": {"key": "value"}}


# --- One voice for file-level faults -----------------------------------------


def test_invalid_toml_raises_settings_error(tmp_path: Path) -> None:
    """Invalid TOML raises SettingsError, naming the file."""
    path = _write_settings(tmp_path, "[tiles]\nname = = broken\n")

    with pytest.raises(SettingsError) as excinfo:
        load_settings_document(tmp_path)

    assert str(path) in str(excinfo.value)


def test_unreadable_file_raises_settings_error(tmp_path: Path) -> None:
    """An unreadable file raises SettingsError rather than escaping as OSError."""
    path = _write_settings(tmp_path, '[tiles]\nname = "osm"\n')
    path.chmod(0)
    if path.is_file() and _readable(path):  # pragma: no cover - root ignores mode
        pytest.skip("filesystem or user ignores permission bits")

    try:
        with pytest.raises(SettingsError) as excinfo:
            load_settings_document(tmp_path)
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert str(path) in str(excinfo.value)


def _readable(path: Path) -> bool:
    try:
        with path.open("rb"):
            return True
    except OSError:
        return False


# --- Read-only by construction -----------------------------------------------


def test_reading_creates_nothing(tmp_path: Path) -> None:
    """Reading absent settings never creates the file or the data root's contents."""
    load_settings_document(tmp_path)

    assert list(tmp_path.iterdir()) == []
