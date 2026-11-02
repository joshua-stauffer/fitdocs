"""``fitdocs disconnect`` (relay-server task 6.7; Requirements 14.1-14.7, 15.1).

Drives the entry point through :class:`typer.testing.CliRunner`. The transport
is a scripted ``FakeTransport`` reached through the ``_connector_transport``
seam; the credentials directory is the one the package conftest points
``FITDOCS_CREDENTIALS_DIR`` at. Printed lines are literals copied by hand, not
the engine's constants.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import CredentialStore, StoredCredentials
from fitdocs.connectors.http import HttpResponse, TransportError
from fitdocs.connectors.protocol import AuthStyle
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.secrets import Secret
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
)
from tests.connectors.test_cli_connectors import _ReservedConnector
from tests.connectors.test_relay_connect import _TOKEN, _envelope

runner = CliRunner()

_NAME = "my-relay"
_URL = "https://relay.example.com"
_TOKEN_VARIABLE = "FITDOCS_CONNECTOR_MY_RELAY_TOKEN"
_OVERRIDE_TOKEN = "fdr1_" + "c" * 16 + "_" + "c" * 52
_LOCAL_NOTE = "Note: the token stays valid at the relay until its operator revokes it."
_SERVICE_NOTE = "Note: the credential remains valid at the service."


def _store() -> CredentialStore:
    return CredentialStore(Path(os.environ["FITDOCS_CREDENTIALS_DIR"]))


def _seed(
    name: str = _NAME,
    *,
    style: AuthStyle = AuthStyle.RELAY_TOKEN,
    field: str = "token",
    value: str = _TOKEN,
) -> Path:
    return _store().save(
        name,
        StoredCredentials(
            connector_id="x",
            auth_style=style,
            values={field: Secret(value)},
            expires_at=None,
            scopes=None,
        ),
    )


def _setup(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: Sequence[HttpResponse | TransportError] = (),
    *,
    settings: str | None = None,
) -> FakeTransport:
    (root / "fitdocs.toml").write_text(
        settings
        if settings is not None
        else f'[connectors.{_NAME}]\nconnector = "relay"\nurl = "{_URL}"\n'
    )
    transport = FakeTransport(list(script))
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: transport)
    return transport


def _run(root: Path, name: str, *args: str) -> tuple[int, list[str]]:
    result = runner.invoke(app, ["disconnect", name, *args, "--out", str(root)])
    return result.exit_code, result.output.splitlines()


def _data_root_files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# --------------------------------------------------------------------------
# Relay: revoke, then forget (Req 14.1, 14.2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [RelayCode.OK, RelayCode.TOKEN_UNKNOWN, RelayCode.TOKEN_REVOKED],
    ids=lambda c: c.value,
)
def test_revoke_answers_that_remove_the_file_print_the_code_and_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: RelayCode
) -> None:
    transport = _setup(tmp_path, monkeypatch, [_envelope(code)])
    path = _seed()
    other = _seed("other")
    other_bytes = other.read_bytes()
    before = _data_root_files(tmp_path)
    assert path.exists()
    exit_code, lines = _run(tmp_path, _NAME)
    assert exit_code == 0
    assert lines == [
        f"{_NAME}: disconnected.",
        f"Credentials removed: {path}",
        f"Relay code: {code.value}",
    ]
    assert not path.exists()
    assert other.read_bytes() == other_bytes
    assert len(transport.requests) == 1
    assert transport.requests[0].url == _URL + "/v1/token/revoke"
    assert _data_root_files(tmp_path) == before


def test_the_revocation_uses_the_stored_token_not_the_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _setup(tmp_path, monkeypatch, [_envelope(RelayCode.OK)])
    _seed()
    monkeypatch.setenv(_TOKEN_VARIABLE, _OVERRIDE_TOKEN)
    exit_code, lines = _run(tmp_path, _NAME)
    assert exit_code == 0
    [request] = transport.requests
    assert {k: v.reveal() for k, v in request.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }
    assert _OVERRIDE_TOKEN not in repr(request.headers) + str(request.body)
    assert _TOKEN not in "\n".join(lines)


@pytest.mark.parametrize(
    ("response", "failure_line"),
    [
        (
            _envelope(RelayCode.RATE_LIMITED),
            f"{_NAME}: rate-limited: "
            "The relay is limiting requests; wait before trying again.",
        ),
        (
            _envelope(RelayCode.RELAY_FAILURE),
            f"{_NAME}: relay-failure: The relay failed while handling the request.",
        ),
        (
            TransportError("connection refused"),
            f"{_NAME}: relay-unreachable: fitdocs could not reach the relay.",
        ),
    ],
    ids=["rate-limited", "relay-failure", "unreachable"],
)
def test_other_answers_keep_the_file_print_next_step_and_exit_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: HttpResponse | TransportError,
    failure_line: str,
) -> None:
    transport = _setup(tmp_path, monkeypatch, [response])
    path = _seed()
    before = path.read_bytes()
    exit_code, lines = _run(tmp_path, _NAME)
    assert exit_code == 1
    assert len(lines) == 2
    assert lines[0] == failure_line
    assert lines[1] == (
        f"Run `fitdocs disconnect {_NAME}` again to retry, or add `--local-only` "
        "to forget the stored token without asking the relay."
    )
    assert path.read_bytes() == before
    assert len(transport.requests) == 1


# --------------------------------------------------------------------------
# --local-only and other styles (Req 14.3, 14.5)
# --------------------------------------------------------------------------


def test_local_only_removes_the_file_with_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _setup(tmp_path, monkeypatch, [])
    path = _seed()
    exit_code, lines = _run(tmp_path, _NAME, "--local-only")
    assert exit_code == 0
    assert lines == [
        f"{_NAME}: disconnected.",
        f"Credentials removed: {path}",
        _LOCAL_NOTE,
    ]
    assert not path.exists()
    assert transport.requests == []


def test_personal_key_and_login_styles_remove_the_file_without_a_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for connector in (ScriptedPersonalKeyConnector(), ScriptedLoginConnector()):
        connector_registry.register(connector)
        transport = _setup(
            tmp_path,
            monkeypatch,
            [],
            settings=f'[connectors.svc]\nconnector = "{connector.connector_id}"\n',
        )
        path = _seed("svc", style=connector.auth_style, field="api_key")
        exit_code, lines = _run(tmp_path, "svc")
        assert exit_code == 0
        assert lines == [
            "svc: disconnected.",
            f"Credentials removed: {path}",
            _SERVICE_NOTE,
        ]
        assert not path.exists()
        assert transport.requests == []


def test_no_authentication_style_has_nothing_to_disconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    transport = _setup(
        tmp_path,
        monkeypatch,
        [],
        settings='[connectors.src]\nconnector = "scripted-puller"\n',
    )
    exit_code, lines = _run(tmp_path, "src")
    assert exit_code == 0
    assert lines == ["src: nothing to disconnect."]
    assert transport.requests == []


def test_reserved_style_exits_2_naming_it_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(_ReservedConnector())
    transport = _setup(
        tmp_path,
        monkeypatch,
        [],
        settings='[connectors.res]\nconnector = "reserved-style"\n',
    )
    path = _seed("res", style=AuthStyle.OAUTH_BROWSER)
    exit_code, lines = _run(tmp_path, "res")
    assert exit_code == 2
    assert lines == [
        "res: the oauth-browser authentication style is not supported by "
        "this version of fitdocs"
    ]
    assert path.exists()
    assert transport.requests == []


# --------------------------------------------------------------------------
# Nothing stored (Req 14.4)
# --------------------------------------------------------------------------


def test_no_stored_token_reports_nothing_with_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _setup(tmp_path, monkeypatch, [])
    exit_code, lines = _run(tmp_path, _NAME)
    assert exit_code == 0
    assert lines == [f"{_NAME}: nothing to disconnect."]
    assert transport.requests == []


@pytest.mark.parametrize("args", [[], ["--local-only"]])
def test_an_environment_override_is_stated_as_not_revoked_and_still_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    transport = _setup(tmp_path, monkeypatch, [])
    monkeypatch.setenv(_TOKEN_VARIABLE, _OVERRIDE_TOKEN)
    exit_code, lines = _run(tmp_path, _NAME, *args)
    assert exit_code == 0
    assert lines == [
        f"{_NAME}: nothing to disconnect.",
        f"Environment variable {_TOKEN_VARIABLE} is not revoked and remains set.",
    ]
    assert _OVERRIDE_TOKEN not in "\n".join(lines)
    assert transport.requests == []


def test_several_overrides_are_stated_in_the_plural(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedLoginConnector())
    transport = _setup(
        tmp_path,
        monkeypatch,
        [],
        settings='[connectors.svc]\nconnector = "login-style"\n',
    )
    monkeypatch.setenv("FITDOCS_CONNECTOR_SVC_USERNAME", "someone")
    monkeypatch.setenv("FITDOCS_CONNECTOR_SVC_PASSWORD", "hunter2-planted")
    exit_code, lines = _run(tmp_path, "svc")
    assert exit_code == 0
    assert lines == [
        "svc: nothing to disconnect.",
        "Environment variables FITDOCS_CONNECTOR_SVC_USERNAME, "
        "FITDOCS_CONNECTOR_SVC_PASSWORD are not revoked and remain set.",
    ]
    assert transport.requests == []


# --------------------------------------------------------------------------
# Credential file problems (stream notes: CredentialStoreError -> exit 2)
# --------------------------------------------------------------------------


def test_a_corrupt_credentials_file_exits_2_pointing_at_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _setup(tmp_path, monkeypatch, [])
    path = _store().path_for(_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is = = not toml")
    path.chmod(0o600)
    result = runner.invoke(app, ["disconnect", _NAME, "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"{path} is not valid TOML")
    assert lines[1] == (
        "To forget it without asking the relay, run: "
        f"fitdocs disconnect {_NAME} --local-only"
    )
    assert path.exists()
    assert transport.requests == []


def test_a_file_without_a_token_exits_2_with_the_hint_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _setup(tmp_path, monkeypatch, [])
    path = _seed(field="other")
    result = runner.invoke(app, ["disconnect", _NAME, "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        f"{path} holds no relay token; run: fitdocs disconnect {_NAME} --local-only"
    ]
    assert path.exists()
    assert transport.requests == []
    # --local-only does not read the file, so it works on the same file.
    exit_code, lines = _run(tmp_path, _NAME, "--local-only")
    assert exit_code == 0
    assert not path.exists()


# --------------------------------------------------------------------------
# Preflight (Req 14.6, 14.7)
# --------------------------------------------------------------------------


def test_an_unknown_name_exits_2_naming_every_configured_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    transport = _setup(
        tmp_path,
        monkeypatch,
        [],
        settings=(
            '[connectors.zeta]\nconnector = "scripted-puller"\n'
            '[connectors.alpha]\nconnector = "scripted-puller"\n'
        ),
    )
    path = _seed("alpha", style=AuthStyle.API_KEY)
    exit_code, lines = _run(tmp_path, "nope")
    assert exit_code == 2
    assert lines == [
        "'nope' is not a configured connector instance; "
        "configured instances: alpha, zeta"
    ]
    assert path.exists()
    assert transport.requests == []


def test_a_credentials_directory_inside_the_data_root_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = _setup(tmp_path, monkeypatch, [])
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(tmp_path / "creds"))
    exit_code, lines = _run(tmp_path, _NAME)
    assert exit_code == 2
    assert lines != []
    assert transport.requests == []
    assert not (tmp_path / "creds").exists()


def test_the_command_is_registered_with_a_local_only_option() -> None:
    result = runner.invoke(app, ["disconnect", "--help"])
    assert result.exit_code == 0
    assert "--local-only" in result.output
