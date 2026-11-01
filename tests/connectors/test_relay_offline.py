"""A configured relay leaves fitdocs offline and confined (relay-server task
7.1; Requirements 11.6, 14.7, 15.1).

* Registration and disconnect write nothing under the data root and touch
  only the instance's credentials file, compared as full directory snapshots
  before and after.
* A bare ``fitdocs pull`` whose only instance is a relay exits 0 with the
  distinct nothing-to-pull line. The transport seam is left unpatched and a
  recording guard on ``socket.socket``, ``socket.getaddrinfo`` and
  ``socket.create_connection`` counts attempts. The exit code and the line are
  asserted explicitly: a bare pull that wrongly selected the relay fails on
  the instance error without making a request, which no network guard can
  tell apart.

The offline-commands half of the task lives in ``test_e2e.py`` (the wired root
there carries a relay instance).
"""

from __future__ import annotations

import os
import socket
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import CredentialStore, StoredCredentials
from fitdocs.connectors.protocol import AuthStyle, Capability
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.secrets import Secret
from tests.connectors.test_cli_relay_connect import (
    _NAME,
)
from tests.connectors.test_cli_relay_connect import (
    _setup as _setup_connect,
)
from tests.connectors.test_relay_connect import _TOKEN, _envelope
from tests.connectors.test_relay_register import (
    _EMAIL,
    _caps,
    _issued,
    _pending,
    _started,
)

runner = CliRunner()

_NOTHING = (
    "No configured connector instance pulls activities or wellness; nothing to pull."
)
#: Name resolution happens before ``socket.socket`` is reached, so a guard on
#: ``socket.socket`` alone lets a request to a host that does not resolve
#: through (``urllib`` -> ``http.client`` -> ``create_connection`` ->
#: ``getaddrinfo``).
_NETWORK_ENTRY_POINTS = ("socket", "getaddrinfo", "create_connection")
_Entry = tuple[str, int, bytes | None, int, int]


def _tree(root: Path) -> dict[str, _Entry]:
    """Every entry under ``root`` (directories included): kind, mode, bytes
    and mtime of a file."""
    entries: dict[str, _Entry] = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        is_file = stat.S_ISREG(info.st_mode)
        entries[path.relative_to(root).as_posix()] = (
            "file" if is_file else "other",
            stat.S_IMODE(info.st_mode),
            path.read_bytes() if is_file else None,
            info.st_mtime_ns if is_file else 0,
            info.st_size if is_file else 0,
        )
    return entries


def _credentials_dir() -> Path:
    return Path(os.environ["FITDOCS_CREDENTIALS_DIR"])


def _env_base() -> Path:
    """The isolation tree the package conftest built: the credentials
    directory and the home directory sit side by side under it."""
    base = _credentials_dir().parent
    assert (base / "home").is_dir()
    assert Path.home() == base / "home"
    return base


def _only_changed(
    before: dict[str, _Entry], after: dict[str, _Entry], changed: set[str]
) -> None:
    """``after`` equals ``before`` except for the entries in ``changed``
    (which may be added, removed or rewritten)."""
    assert {k: v for k, v in after.items() if k not in changed} == {
        k: v for k, v in before.items() if k not in changed
    }


def _seed(name: str, token: str) -> Path:
    return CredentialStore(_credentials_dir()).save(
        name,
        StoredCredentials(
            connector_id="relay",
            auth_style=AuthStyle.RELAY_TOKEN,
            values={"token": Secret(token)},
            expires_at=None,
            scopes=None,
        ),
    )


def _populate_data_root(root: Path) -> None:
    """A data root that is not empty, so an unchanged snapshot says something."""
    (root / "inbox").mkdir()
    (root / "inbox" / "dropped.fit").write_bytes(b"not a real fit file")
    (root / "workouts").mkdir()
    (root / "workouts" / "2024-01-01-run.md").write_text("# a run\n")


def _restrict_credentials_dir() -> None:
    """Set a mode that is neither the conftest directory's nor the 0o700
    ``CredentialStore.save`` creates with, after every seeding (seeding itself
    may touch the directory), so a command that resets the directory's mode
    to either changes it."""
    _credentials_dir().chmod(0o750)
    assert stat.S_IMODE(_credentials_dir().stat().st_mode) == 0o750


def _bystander() -> tuple[Path, bytes]:
    path = _seed("bystander", "fdr1_" + "d" * 16 + "_" + "d" * 52)
    return path, path.read_bytes()


def test_registration_writes_nothing_under_the_data_root_and_one_credentials_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup_connect(
        tmp_path,
        monkeypatch,
        [_caps(), _started(interval_s=10), _pending(), _issued()],
    )
    _populate_data_root(tmp_path)
    bystander, bystander_bytes = _bystander()
    own_file = _credentials_dir() / f"{_NAME}.toml"
    assert not own_file.exists()
    _restrict_credentials_dir()
    root_before = _tree(tmp_path)
    credentials_before = _tree(_credentials_dir())
    base_before = _tree(_env_base())
    assert set(credentials_before) == {".", "bystander.toml"}
    assert {"fitdocs.toml", "inbox/dropped.fit", "workouts/2024-01-01-run.md"} <= set(
        root_before
    )

    result = runner.invoke(
        app,
        ["connect", _NAME, "--register", "--email", _EMAIL, "--out", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert f"{_NAME}: connected." in result.output
    assert len(session.transport.requests) == 4
    assert _tree(tmp_path) == root_before
    credentials_after = _tree(_credentials_dir())
    assert set(credentials_after) == {".", "bystander.toml", f"{_NAME}.toml"}
    assert credentials_after["bystander.toml"] == credentials_before["bystander.toml"]
    assert credentials_after["."][1] == credentials_before["."][1]
    _only_changed(base_before, _tree(_env_base()), {f"credentials-dir/{_NAME}.toml"})
    assert bystander.read_bytes() == bystander_bytes
    assert _TOKEN in own_file.read_text()


@pytest.mark.parametrize("local_only", [False, True], ids=["revoke", "local-only"])
def test_disconnect_writes_nothing_under_the_data_root_and_removes_one_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local_only: bool
) -> None:
    session = _setup_connect(
        tmp_path, monkeypatch, [] if local_only else [_envelope(RelayCode.OK)]
    )
    _populate_data_root(tmp_path)
    bystander, bystander_bytes = _bystander()
    own_file = _seed(_NAME, _TOKEN)
    assert own_file.exists()
    _restrict_credentials_dir()
    root_before = _tree(tmp_path)
    credentials_before = _tree(_credentials_dir())
    base_before = _tree(_env_base())
    assert set(credentials_before) == {".", "bystander.toml", f"{_NAME}.toml"}

    args = ["disconnect", _NAME, "--out", str(tmp_path)]
    result = runner.invoke(app, [*args, "--local-only"] if local_only else args)

    assert result.exit_code == 0, result.output
    assert f"{_NAME}: disconnected." in result.output
    assert len(session.transport.requests) == (0 if local_only else 1)
    assert not own_file.exists()
    assert _tree(tmp_path) == root_before
    credentials_after = _tree(_credentials_dir())
    assert set(credentials_after) == {".", "bystander.toml"}
    assert credentials_after["bystander.toml"] == credentials_before["bystander.toml"]
    assert credentials_after["."][1] == credentials_before["."][1]
    _only_changed(base_before, _tree(_env_base()), {f"credentials-dir/{_NAME}.toml"})
    assert bystander.read_bytes() == bystander_bytes


def test_a_bare_pull_with_only_a_relay_instance_is_offline_and_prints_the_nothing_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fitdocs.toml").write_text(
        '[connectors.my-relay]\nconnector = "relay"\nurl = "https://relay.example.com"\n'
    )
    _seed("my-relay", _TOKEN)
    attempts: list[object] = []

    def _record_and_refuse(*args: object, **kwargs: object) -> object:
        attempts.append(args)
        raise RuntimeError("tests/connectors must not open a real network socket")

    for name in _NETWORK_ENTRY_POINTS:
        monkeypatch.setattr(socket, name, _record_and_refuse)
    relay = connector_registry.get("relay")
    assert relay.auth_style is AuthStyle.RELAY_TOKEN
    assert not relay.capabilities & {
        Capability.PULL_ACTIVITIES,
        Capability.PULL_WELLNESS,
    }

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert _NOTHING in " ".join(result.output.split())
    assert "does not pull" not in result.output
    assert "my-relay" not in result.output
    assert attempts == []
