"""The intervals.icu connector's declaration, registration and settings
(intervals-connector task 3.1; Req 1.1, 1.5, 2.1-2.4, 5.6, 10.2, 10.4).

Task 3.1 covers what needs no request: the declaration, the registry entry,
the ``sources`` settings parser, and the connector's own address admitted by
the service-neutral scan. The three operations are exercised by later tasks'
test modules (3.2-3.4 extend this file), so no test here calls them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fitdocs.connectors import (
    AuthStyle,
    Capability,
    CredentialField,
    SettingsContext,
    get,
    validate_connector,
)
from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.intervals import (
    DEFAULT_SOURCES,
    INTERVALS_CONNECTOR_ID,
    IntervalsConnector,
    IntervalsSettings,
)
from fitdocs.connectors.settings import (
    ConnectorsSettingsError,
    load_connectors_settings,
)


def _context(tmp_path: Path) -> SettingsContext:
    return SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")


def _parse(tmp_path: Path, table: dict[str, object]) -> IntervalsSettings:
    return IntervalsConnector().parse_settings(table, _context(tmp_path))


# --------------------------------------------------------------------------
# Registration and declaration (Req 1.1, 1.5, 10.2)
# --------------------------------------------------------------------------


def test_the_registry_returns_the_connector_and_its_gate_accepts_it() -> None:
    connector = get("intervals")
    assert isinstance(connector, IntervalsConnector)
    assert INTERVALS_CONNECTOR_ID == "intervals"
    assert validate_connector(connector) is None


def test_a_fresh_import_registers_folder_then_intervals() -> None:
    probe = (
        "import fitdocs.connectors as c; "
        "print(','.join(x.connector_id for x in c.available()))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "folder,intervals"


def test_the_declaration_is_a_personal_key_pull_only_connector() -> None:
    connector = IntervalsConnector()
    assert connector.connector_id == "intervals"
    assert connector.display_name == "intervals.icu"
    assert connector.auth_style is AuthStyle.API_KEY
    assert connector.capabilities == frozenset({Capability.PULL_ACTIVITIES})
    assert connector.credential_fields == (
        CredentialField(
            "api_key", "intervals.icu API key (Settings, Developer Settings)", True
        ),
    )


def test_an_instance_table_without_a_connector_key_resolves_to_it(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "fitdocs.toml"
    instances = load_connectors_settings(
        {"connectors": {"intervals": {}}},
        settings_file=settings_file,
        context=_context(tmp_path),
    )
    assert len(instances) == 1
    assert instances[0].name == "intervals"
    assert instances[0].connector is get("intervals")
    assert instances[0].settings == IntervalsSettings(sources=DEFAULT_SOURCES)


# --------------------------------------------------------------------------
# Settings (Req 2.1-2.4)
# --------------------------------------------------------------------------


def test_absent_sources_gives_the_default(tmp_path: Path) -> None:
    assert frozenset({"GARMIN_CONNECT"}) == DEFAULT_SOURCES
    assert _parse(tmp_path, {}).sources == frozenset({"GARMIN_CONNECT"})


def test_a_two_name_list_is_read_as_a_set(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"sources": ["ZWIFT", "GARMIN_CONNECT"]})
    assert settings.sources == frozenset({"ZWIFT", "GARMIN_CONNECT"})


def test_an_unpublished_well_formed_name_is_accepted(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"sources": ["NOT_A_PUBLISHED_SOURCE_9"]})
    assert settings.sources == frozenset({"NOT_A_PUBLISHED_SOURCE_9"})


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ([], "[]"),
        ("GARMIN_CONNECT", "'GARMIN_CONNECT'"),
        (["garmin_connect"], "'garmin_connect'"),
        (["GARMIN_CONNECT", 7], "7"),
        (["GARMIN_CONNECT\n"], "'GARMIN_CONNECT\\n'"),
    ],
)
def test_a_malformed_sources_value_is_refused_naming_key_and_value(
    tmp_path: Path, value: object, shown: str
) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"sources": value})
    assert excinfo.value.key == "sources"
    assert shown in excinfo.value.message
    assert "GARMIN_CONNECT" in excinfo.value.message


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"colour": "teal", "sources": ["ZWIFT"]})
    assert settings == IntervalsSettings(sources=frozenset({"ZWIFT"}))


def test_an_empty_sources_list_in_a_settings_file_names_file_instance_and_key(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "fitdocs.toml"
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"intervals": {"sources": []}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    message = str(excinfo.value)
    assert message.startswith(f"{settings_file}: [connectors.intervals] sources: ")
    assert "[]" in message
