"""Tests for the ``[identity]`` table reader (Req 2.5-2.7).

Documents are plain mappings, as :func:`fitdocs.settings.load_settings_document`
returns them; the reader never opens a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    PrecedenceEntry,
)
from fitdocs.identity.settings import (
    IdentitySettings,
    IdentitySettingsError,
    load_identity_settings,
)
from fitdocs.settings import SettingsError

_FILE = Path("/data/fitdocs.toml")


def _load(document: dict[str, object]) -> IdentitySettings:
    return load_identity_settings(document, _FILE)


def _error(document: dict[str, object]) -> str:
    with pytest.raises(IdentitySettingsError) as excinfo:
        _load(document)
    return str(excinfo.value)


def _precedence(value: object) -> dict[str, object]:
    return {"identity": {"precedence": value}}


class TestDefaults:
    def test_an_empty_document_is_the_default(self) -> None:
        assert _load({}).precedence == DEFAULT_PRECEDENCE

    def test_an_absent_key_is_the_default(self) -> None:
        assert _load({"identity": {}}).precedence == DEFAULT_PRECEDENCE

    def test_unknown_keys_and_tables_are_ignored(self) -> None:
        document: dict[str, object] = {
            "tiles": {"x": 1},
            "identity": {"colour": "blue", "precedence": ["unknown"]},
        }
        assert _load(document).precedence == (
            PrecedenceEntry(SourceKind.UNKNOWN),
            PrecedenceEntry(SourceKind.ORIGINAL),
            PrecedenceEntry(SourceKind.PHONE_COPY),
        )


class TestConfigured:
    def test_a_list_of_kinds_resolves_to_exactly_those_entries(self) -> None:
        precedence = _load(_precedence(["original", "phone_copy", "unknown"]))
        assert precedence.precedence == (
            PrecedenceEntry(SourceKind.ORIGINAL),
            PrecedenceEntry(SourceKind.PHONE_COPY),
            PrecedenceEntry(SourceKind.UNKNOWN),
        )

    def test_a_present_empty_list_is_a_configured_list_not_the_default(self) -> None:
        assert _load(_precedence([])).precedence == (
            PrecedenceEntry(SourceKind.ORIGINAL),
            PrecedenceEntry(SourceKind.PHONE_COPY),
            PrecedenceEntry(SourceKind.UNKNOWN),
        )

    def test_a_manufacturer_entry_is_resolved_with_the_unnamed_kinds_appended(
        self,
    ) -> None:
        assert _load(_precedence(["original:stryd", "phone_copy"])).precedence == (
            PrecedenceEntry(SourceKind.ORIGINAL, "stryd"),
            PrecedenceEntry(SourceKind.PHONE_COPY),
            PrecedenceEntry(SourceKind.ORIGINAL),
            PrecedenceEntry(SourceKind.UNKNOWN),
        )

    def test_a_manufacturer_entry_and_its_kind_are_not_duplicates(self) -> None:
        precedence = _load(_precedence(["original:garmin", "original"])).precedence
        assert precedence[:2] == (
            PrecedenceEntry(SourceKind.ORIGINAL, "garmin"),
            PrecedenceEntry(SourceKind.ORIGINAL),
        )

    def test_the_error_type_is_a_settings_error(self) -> None:
        assert issubclass(IdentitySettingsError, SettingsError)


class TestErrors:
    def _assert_names_file_and_key(self, message: str) -> None:
        assert str(_FILE) in message
        assert "[identity] precedence" in message

    def test_a_non_table_identity(self) -> None:
        message = _error({"identity": "original"})
        assert str(_FILE) in message
        assert "[identity] must be a table" in message

    def test_a_non_list_precedence(self) -> None:
        message = _error(_precedence("original"))
        self._assert_names_file_and_key(message)
        assert "must be a list of strings" in message

    def test_a_non_string_element(self) -> None:
        message = _error(_precedence(["original", 3]))
        self._assert_names_file_and_key(message)
        assert "must be a list of strings" in message
        assert "3" in message

    def test_an_unknown_kind(self) -> None:
        message = _error(_precedence(["original", "bogus"]))
        self._assert_names_file_and_key(message)
        assert "'bogus'" in message
        assert "neither a kind" in message

    def test_original_with_an_empty_name(self) -> None:
        message = _error(_precedence(["original:"]))
        self._assert_names_file_and_key(message)
        assert "no manufacturer" in message

    def test_original_development(self) -> None:
        message = _error(_precedence(["original:development"]))
        self._assert_names_file_and_key(message)
        assert "'original:development'" in message
        assert "phone_copy" in message

    def test_a_duplicate_kind(self) -> None:
        message = _error(_precedence(["original", "phone_copy", "original"]))
        self._assert_names_file_and_key(message)
        assert "'original' twice" in message

    def test_a_duplicate_manufacturer_entry(self) -> None:
        message = _error(_precedence(["original:garmin", "original:garmin"]))
        self._assert_names_file_and_key(message)
        assert "'original:garmin' twice" in message

    def test_a_kind_with_a_manufacturer_suffix_other_than_original(self) -> None:
        message = _error(_precedence(["phone_copy:garmin"]))
        self._assert_names_file_and_key(message)
