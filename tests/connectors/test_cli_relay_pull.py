"""A bare ``fitdocs pull`` skips relay instances (relay-server task 6.7;
Requirements 11.5, 11.6, 14.6, 15.1)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import CredentialStore, StoredCredentials
from fitdocs.connectors.protocol import AuthStyle, Capability
from fitdocs.connectors.secrets import Secret
from tests.connectors.conftest import ScriptedPersonalKeyConnector
from tests.connectors.test_relay_connect import _TOKEN

runner = CliRunner()

_URL = "https://relay.example.com"
_NOTHING = (
    "No configured connector instance pulls activities or wellness; nothing to pull."
)


class _Spy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: object, timeout: float) -> object:
        self.calls += 1
        raise AssertionError("no request may be made")


def _fit_bytes() -> bytes:
    return bytes([12, 0x10, 0, 0, 0, 0, 0, 0]) + b".FIT" + b"ride"


def _setup(root: Path, monkeypatch: pytest.MonkeyPatch, *, folder: bool) -> _Spy:
    text = f'[connectors.my-relay]\nconnector = "relay"\nurl = "{_URL}"\n'
    if folder:
        source = root / "phone-exports"
        source.mkdir()
        (source / "ride.fit").write_bytes(_fit_bytes())
        text += (
            '[connectors.folder-src]\nconnector = "folder"\n'
            f'path = "{source.as_posix()}"\nsettle_seconds = 0\n'
        )
    (root / "fitdocs.toml").write_text(text)
    spy = _Spy()
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: spy)
    return spy


def _store_token() -> None:
    CredentialStore(Path(os.environ["FITDOCS_CREDENTIALS_DIR"])).save(
        "my-relay",
        StoredCredentials(
            connector_id="relay",
            auth_style=AuthStyle.RELAY_TOKEN,
            values={"token": Secret(_TOKEN)},
            expires_at=None,
            scopes=None,
        ),
    )


def test_bare_pull_pulls_the_folder_and_never_contacts_the_relay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _setup(tmp_path, monkeypatch, folder=True)
    _store_token()
    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(list((tmp_path / "inbox" / "folder-src").glob("*.fit"))) == 1
    assert "my-relay" not in result.output
    assert _NOTHING not in result.output
    assert spy.calls == 0


def test_bare_pull_with_only_a_relay_prints_the_distinct_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _setup(tmp_path, monkeypatch, folder=False)
    _store_token()
    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert _NOTHING in result.output
    assert "No connectors are configured" not in result.output
    assert "my-relay" not in result.output
    assert spy.calls == 0


def test_bare_pull_with_nothing_configured_keeps_its_own_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fitdocs.toml").write_text("")
    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "No connectors are configured; nothing to pull." in result.output
    assert _NOTHING not in result.output


def test_a_named_relay_with_no_stored_token_reports_not_connected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _setup(tmp_path, monkeypatch, folder=False)
    result = runner.invoke(app, ["pull", "my-relay", "--out", str(tmp_path)])
    assert "my-relay" in result.output
    assert "not connected" in " ".join(result.output.split())
    assert result.exit_code == 1, result.output
    assert spy.calls == 0


def test_a_named_relay_with_a_stored_token_reports_it_pulls_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _setup(tmp_path, monkeypatch, folder=False)
    _store_token()
    result = runner.invoke(app, ["pull", "my-relay", "--out", str(tmp_path)])
    assert result.exit_code == 1, result.output
    assert "does not pull activities or wellness" in " ".join(result.output.split())
    assert spy.calls == 0


def _decoy_settings(root: Path, *, folder: bool) -> None:
    """A non-relay connector declaring no pull capability, beside a folder."""
    connector = ScriptedPersonalKeyConnector()
    assert not connector.capabilities & {
        Capability.PULL_ACTIVITIES,
        Capability.PULL_WELLNESS,
    }
    assert connector.connector_id != "relay"
    assert connector.auth_style is not AuthStyle.RELAY_TOKEN
    connector_registry.register(connector)
    text = '[connectors.decoy]\nconnector = "personal-key"\n'
    if folder:
        source = root / "phone-exports"
        source.mkdir()
        (source / "ride.fit").write_bytes(_fit_bytes())
        text += (
            '[connectors.folder-src]\nconnector = "folder"\n'
            f'path = "{source.as_posix()}"\nsettle_seconds = 0\n'
        )
    (root / "fitdocs.toml").write_text(text)


def test_bare_pull_skips_a_non_relay_connector_that_pulls_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _decoy_settings(tmp_path, folder=True)
    spy = _Spy()
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: spy)
    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(list((tmp_path / "inbox" / "folder-src").glob("*.fit"))) == 1
    assert "decoy" not in result.output
    assert spy.calls == 0


def test_bare_pull_with_only_a_non_relay_non_puller_prints_the_distinct_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _decoy_settings(tmp_path, folder=False)
    spy = _Spy()
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: spy)
    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert _NOTHING in result.output
    assert "decoy" not in result.output
    assert spy.calls == 0
