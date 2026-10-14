"""Instance wellness settings (wellness-pull 2.1, 2.3, 2.4, 2.5)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors.http import Transport
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    Granted,
    SettingsContext,
)
from fitdocs.connectors.registry import register
from fitdocs.connectors.secrets import Secret
from fitdocs.connectors.settings import (
    ConnectorInstance,
    ConnectorsSettingsError,
    load_connectors_settings,
)
from fitdocs.layout import connector_ledger_path
from tests.connectors.conftest import FakeTransport, ScriptedWellnessPuller


class _CredentialWellnessPuller(ScriptedWellnessPuller):
    auth_style = AuthStyle.API_KEY
    credential_fields = (CredentialField("api_key", "API Key", secret=True),)

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        self.calls.append("verify")
        return Granted(scopes=None)


def _load(tmp_path: Path, table: dict[str, object]) -> ConnectorInstance:
    return load_connectors_settings(
        {"connectors": {"morning": table}},
        settings_file=tmp_path / "fitdocs.toml",
        context=SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox"),
    )[0]


def _error_body(error: BaseException, settings_file: Path) -> str:
    path, separator, body = str(error).partition(": ")
    assert (path, separator) == (str(settings_file), ": ")
    return body


@pytest.mark.parametrize("table", [{}, {"wellness": False}, {"wellness": True}])
def test_wellness_boolean_and_default(tmp_path: Path, table: dict[str, object]) -> None:
    register(ScriptedWellnessPuller())
    instance = _load(tmp_path, {"connector": "scripted-wellness-puller", **table})
    assert instance.wellness is table.get("wellness", False)


def test_direct_instance_defaults_wellness_to_false() -> None:
    assert (
        ConnectorInstance("morning", ScriptedWellnessPuller(), 30, None).wellness
        is False
    )


def test_framework_strips_wellness_before_connector_parser(tmp_path: Path) -> None:
    connector = ScriptedWellnessPuller()
    register(connector)
    _load(
        tmp_path,
        {
            "connector": connector.connector_id,
            "lookback_days": 7,
            "wellness": True,
            "marker": "synthetic-value",
        },
    )
    assert connector.parse_settings_tables == [{"marker": "synthetic-value"}]


@pytest.mark.parametrize("value", ["yes", 1, 0])
def test_non_boolean_wellness_is_rejected(tmp_path: Path, value: object) -> None:
    register(ScriptedWellnessPuller())
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        _load(tmp_path, {"connector": "scripted-wellness-puller", "wellness": value})
    body = _error_body(excinfo.value, tmp_path / "fitdocs.toml")
    assert body == (
        f"[connectors.morning] wellness: must be true or false, "
        f"got {value!r} ({type(value).__name__})"
    )


def test_true_wellness_rejected_for_connector_without_capability(
    tmp_path: Path,
) -> None:
    register(
        ScriptedWellnessPuller(capabilities=frozenset({Capability.PULL_ACTIVITIES}))
    )
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        _load(tmp_path, {"connector": "scripted-wellness-puller", "wellness": True})
    body = _error_body(excinfo.value, tmp_path / "fitdocs.toml")
    assert body == (
        "[connectors.morning] wellness: the scripted-wellness-puller connector "
        "does not pull wellness"
    )


def test_true_wellness_rejected_for_folder(tmp_path: Path) -> None:
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        _load(tmp_path, {"connector": "folder", "path": "source", "wellness": True})
    body = _error_body(excinfo.value, tmp_path / "fitdocs.toml")
    assert (
        body
        == "[connectors.morning] wellness: the folder connector does not pull wellness"
    )


def test_false_wellness_accepted_for_folder(tmp_path: Path) -> None:
    instance = _load(
        tmp_path, {"connector": "folder", "path": "source", "wellness": False}
    )
    assert instance.wellness is False


def test_lookback_is_checked_before_wellness(tmp_path: Path) -> None:
    register(ScriptedWellnessPuller())
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        _load(
            tmp_path,
            {
                "connector": "scripted-wellness-puller",
                "lookback_days": -1,
                "wellness": "yes",
            },
        )
    body = _error_body(excinfo.value, tmp_path / "fitdocs.toml")
    assert (
        body == "[connectors.morning] lookback_days: must be between 0 and 3650, got -1"
    )


def test_wellness_is_checked_before_credential_keys(tmp_path: Path) -> None:
    connector = _CredentialWellnessPuller()
    register(connector)
    table: dict[str, object] = {
        "connector": connector.connector_id,
        "lookback_days": 7,
        "wellness": False,
        "api_key": "ik-synthetic-7Q2x9",
    }
    with pytest.raises(ConnectorsSettingsError) as credential_error:
        _load(tmp_path, table)
    credential_body = _error_body(credential_error.value, tmp_path / "fitdocs.toml")
    assert credential_body == (
        "[connectors.morning] api_key: credentials belong in `fitdocs connect` "
        "or the environment, never in the settings file"
    )

    table["wellness"] = "yes"
    with pytest.raises(ConnectorsSettingsError) as wellness_error:
        _load(tmp_path, table)
    wellness_body = _error_body(wellness_error.value, tmp_path / "fitdocs.toml")
    assert connector.parse_settings_calls == 0
    assert connector.calls == []
    assert wellness_body == (
        "[connectors.morning] wellness: must be true or false, got 'yes' (str)"
    )


@pytest.mark.parametrize("wellness", ['"yes"', "1", "0", "true"])
def test_pull_rejects_wellness_before_transport_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wellness: str
) -> None:
    settings_file = tmp_path / "fitdocs.toml"
    settings_file.write_text(
        '[connectors.morning]\nconnector = "folder"\npath = "source"\n'
        f"wellness = {wellness}\n"
    )
    before = (settings_file.read_bytes(), settings_file.stat().st_mtime_ns)
    transport_calls: list[str] = []

    def transport_factory() -> Transport:
        transport_calls.append("transport")
        return FakeTransport([])

    monkeypatch.setattr(cli_module, "_connector_transport", transport_factory)
    result = CliRunner().invoke(app, ["pull", "--out", str(tmp_path)])
    assert transport_calls == []
    assert not connector_ledger_path(tmp_path, "morning").exists()
    assert not (tmp_path / "inbox").exists()
    assert (settings_file.read_bytes(), settings_file.stat().st_mtime_ns) == before
    assert result.exit_code == 2


_CAPABILITY_CASES = [
    pytest.param(frozenset({Capability.PULL_WELLNESS}), True, id="wellness-only"),
    pytest.param(
        frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS}),
        True,
        id="both-driven",
    ),
    pytest.param(
        frozenset({Capability.PULL_WELLNESS, Capability.PULL_THRESHOLDS}),
        True,
        id="wellness-and-reserved",
    ),
    pytest.param(frozenset(Capability), True, id="all-capabilities"),
    pytest.param(frozenset({Capability.PULL_ACTIVITIES}), False, id="activities-only"),
    pytest.param(frozenset({Capability.PULL_THRESHOLDS}), False, id="reserved-only"),
    pytest.param(
        frozenset(Capability) - {Capability.PULL_WELLNESS},
        False,
        id="all-without-wellness",
    ),
]


@pytest.mark.parametrize("capabilities,supports_wellness", _CAPABILITY_CASES)
@pytest.mark.parametrize(
    "table,expected_value",
    [
        pytest.param({}, False, id="absent"),
        pytest.param({"wellness": False}, False, id="false"),
        pytest.param({"wellness": True}, True, id="true"),
    ],
)
def test_wellness_value_capability_matrix(
    tmp_path: Path,
    capabilities: frozenset[Capability],
    supports_wellness: bool,
    table: dict[str, object],
    expected_value: bool,
) -> None:
    connector = ScriptedWellnessPuller(capabilities=capabilities)
    register(connector)
    configured = {
        "connector": connector.connector_id,
        "lookback_days": 11,
        "marker": "synthetic-matrix-value",
        **table,
    }
    if expected_value and not supports_wellness:
        with pytest.raises(ConnectorsSettingsError) as excinfo:
            _load(tmp_path, configured)
        body = _error_body(excinfo.value, tmp_path / "fitdocs.toml")
        assert body == (
            "[connectors.morning] wellness: the scripted-wellness-puller connector "
            "does not pull wellness"
        )
    else:
        instance = _load(tmp_path, configured)
        assert instance.wellness is expected_value
        assert connector.parse_settings_tables == [{"marker": "synthetic-matrix-value"}]


@pytest.mark.parametrize("capabilities,supports_wellness", _CAPABILITY_CASES)
@pytest.mark.parametrize("value", ["yes", 1, 0], ids=["string", "one", "zero"])
def test_malformed_wellness_capability_matrix(
    tmp_path: Path,
    capabilities: frozenset[Capability],
    supports_wellness: bool,
    value: object,
) -> None:
    register(ScriptedWellnessPuller(capabilities=capabilities))
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        _load(
            tmp_path,
            {
                "connector": "scripted-wellness-puller",
                "lookback_days": 11,
                "wellness": value,
            },
        )
    body = _error_body(excinfo.value, tmp_path / "fitdocs.toml")
    assert body == (
        f"[connectors.morning] wellness: must be true or false, "
        f"got {value!r} ({type(value).__name__})"
    )
