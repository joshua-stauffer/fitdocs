"""``fitdocs connect`` for a Strava instance (strava-publish task 5.8;
Requirements 2.3, 2.8, 2.9, 2.10, 11.1, 11.3).

Drives the entry point through :class:`typer.testing.CliRunner`. The transport
is a scripted ``FakeTransport`` reached through the ``_connector_transport``
seam, the browser opener is the ``_open_browser`` seam, and the clock is a fake
whose ``sleep`` advances ``datetime.now`` as seen by ``cli.py``. The Strava and
relay connectors are the real ones; the credentials directory is the one the
package conftest points ``FITDOCS_CREDENTIALS_DIR`` at.

Printed lines are literals copied by hand, not the engine's constants.
"""

from __future__ import annotations

import os
import time
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import CredentialStore, StoredCredentials
from fitdocs.connectors.http import HttpRequest, HttpResponse, TransportError
from fitdocs.connectors.protocol import AuthStyle
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.secrets import Secret
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
)
from tests.connectors.test_browser_connect import (
    _CONNECTION_TOKEN,
    _POLL_SECRET,
    _RELAY_TOKEN,
    _USER_CODE,
    _envelope,
    _granted,
    _pending,
    _started,
)
from tests.connectors.test_cli_relay_connect import _Clock

runner = CliRunner()

_NAME = "strava"
_URL = "https://relay.example.com"
_PAGE = _URL + "/connect/strava?code=" + _USER_CODE
_SETTINGS = (
    f'[connectors.{_NAME}]\nconnector = "strava"\nrelay = "home"\n'
    f'\n[connectors.home]\nconnector = "relay"\nurl = "{_URL}"\n'
)
_HEADER = f"{_NAME}: open this address in a browser to connect this instance:"
_ADDRESS = f"  {_PAGE}"
_CODE_LINE = f"Code: {_USER_CODE}. Continue only if the page shows this same code."
_NO_BROWSER_LINE = "Could not open a browser; open the address above yourself."


@dataclass
class _Session:
    transport: FakeTransport
    clock: _Clock
    opened: list[str]
    prompts: list[str]


def _store() -> CredentialStore:
    return CredentialStore(Path(os.environ["FITDOCS_CREDENTIALS_DIR"]))


def _seed_relay_token() -> None:
    _store().save(
        "home",
        StoredCredentials(
            connector_id="relay",
            auth_style=AuthStyle.RELAY_TOKEN,
            values={"token": Secret(_RELAY_TOKEN)},
            expires_at=None,
            scopes=None,
        ),
    )


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: Sequence[HttpResponse | TransportError],
    *,
    relay_token: bool = True,
    opener_result: bool = True,
    clock: _Clock | None = None,
    settings: str = _SETTINGS,
) -> _Session:
    (tmp_path / "fitdocs.toml").write_text(settings)
    if relay_token:
        _seed_relay_token()
    transport = FakeTransport(list(script))
    the_clock = clock if clock is not None else _Clock()
    opened: list[str] = []
    prompts: list[str] = []

    def fake_open(url: str) -> bool:
        opened.append(url)
        return opener_result

    def refuse_prompt(prompt: str) -> str:
        prompts.append(prompt)
        raise AssertionError(f"unscripted prompt: {prompt!r}")

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return the_clock.now(tz)

    monkeypatch.setattr(cli_module, "_open_browser", fake_open)
    monkeypatch.setattr(cli_module, "_ask_secret", refuse_prompt)
    monkeypatch.setattr(cli_module, "_ask_value", refuse_prompt)
    monkeypatch.setattr(cli_module, "_stdin_is_interactive", lambda: False)
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: transport)
    monkeypatch.setattr(cli_module, "datetime", _FakeDatetime)
    monkeypatch.setattr(time, "sleep", the_clock.sleep)
    return _Session(transport, the_clock, opened, prompts)


def _run(tmp_path: Path, *args: str, name: str = _NAME) -> tuple[int, list[str]]:
    result = runner.invoke(app, ["connect", name, *args, "--out", str(tmp_path)])
    return result.exit_code, result.output.splitlines()


def _stored_path() -> Path:
    return Path(os.environ["FITDOCS_CREDENTIALS_DIR"]) / f"{_NAME}.toml"


def _credential_files() -> list[str]:
    directory = Path(os.environ["FITDOCS_CREDENTIALS_DIR"])
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


# --------------------------------------------------------------------------
# The started lines, the opener, the grant (2.3, 2.9, 11.1)
# --------------------------------------------------------------------------


def test_a_grant_prints_the_started_lines_opens_the_page_once_and_connects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path, monkeypatch, [_started(expires_in_s=600), _pending(), _granted()]
    )
    assert not _stored_path().exists()
    code, lines = _run(tmp_path)
    assert code == 0
    assert lines == [
        _HEADER,
        _ADDRESS,
        _CODE_LINE,
        "This attempt expires in 10 minutes.",
        f"{_NAME}: connected.",
        f"Credentials: {_stored_path()}",
        f"Relay: {_URL}",
    ]
    assert session.opened == [_PAGE]
    assert session.prompts == []
    assert len(session.transport.requests) == 3
    assert _CONNECTION_TOKEN in _stored_path().read_text()
    printed = "\n".join(lines)
    for hidden in (_CONNECTION_TOKEN, _RELAY_TOKEN, _POLL_SECRET):
        assert hidden not in printed


def test_no_browser_prints_the_same_lines_and_makes_no_browser_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [_started(), _granted()])
    code, lines = _run(tmp_path, "--no-browser")
    assert code == 0
    assert lines[:4] == [
        _HEADER,
        _ADDRESS,
        _CODE_LINE,
        "This attempt expires in 10 minutes.",
    ]
    assert lines[4] == f"{_NAME}: connected."
    assert session.opened == []


def test_an_opener_that_fails_prints_one_line_and_the_connect_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path, monkeypatch, [_started(), _granted()], opener_result=False
    )
    code, lines = _run(tmp_path)
    assert code == 0
    assert lines[:5] == [
        _HEADER,
        _ADDRESS,
        _CODE_LINE,
        "This attempt expires in 10 minutes.",
        _NO_BROWSER_LINE,
    ]
    assert lines[5] == f"{_NAME}: connected."
    assert session.opened == [_PAGE]


def test_the_failure_line_is_absent_when_the_opener_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path, monkeypatch, [_started(), _granted()])
    _, lines = _run(tmp_path)
    assert lines.count(_NO_BROWSER_LINE) == 0
    assert len(lines) == 7


@pytest.mark.parametrize(
    ("expires_in_s", "per_call", "text"),
    [
        (60, 20.0, "less than a minute"),
        (60, 0.0, "1 minute"),
        (150, 0.0, "2 minutes"),
    ],
)
def test_the_time_remaining_is_in_whole_minutes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expires_in_s: int,
    per_call: float,
    text: str,
) -> None:
    _setup(
        tmp_path,
        monkeypatch,
        [_started(expires_in_s=expires_in_s), _granted()],
        clock=_Clock(per_call=per_call),
    )
    code, lines = _run(tmp_path)
    assert code == 0
    assert lines[3] == f"This attempt expires in {text}."


def test_a_granted_connect_names_an_overriding_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FITDOCS_CONNECTOR_STRAVA_TOKEN", "from-the-environment")
    _setup(tmp_path, monkeypatch, [_started(), _granted()])
    code, lines = _run(tmp_path)
    assert code == 0
    assert lines[7:] == [
        "Overriding environment variables (used instead of the stored values "
        "during a publish): FITDOCS_CONNECTOR_STRAVA_TOKEN"
    ]


def test_no_started_line_uses_the_brand_connect_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path, monkeypatch, [_started(), _envelope(RelayCode.CONNECT_REFUSED)])
    _, lines = _run(tmp_path)
    assert len(lines) > 4
    assert "Connect with Strava" not in "\n".join(lines)


# --------------------------------------------------------------------------
# The real opener (design: CliStrava)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("answer", [True, False])
def test_the_opener_opens_a_new_tab_and_reports_the_answer(
    monkeypatch: pytest.MonkeyPatch, answer: bool
) -> None:
    calls: list[tuple[str, int]] = []

    def fake(url: str, new: int = 0, autoraise: bool = True) -> bool:
        calls.append((url, new))
        return answer

    monkeypatch.setattr(webbrowser, "open", fake)
    assert cli_module._open_browser(_PAGE) is answer
    assert calls == [(_PAGE, 2)]


@pytest.mark.parametrize(
    "error",
    [webbrowser.Error("no browser"), OSError("no opener")],
    ids=["webbrowser-error", "os-error"],
)
def test_an_opener_that_raises_is_a_failure_to_open(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def broken(url: str, new: int = 0, autoraise: bool = True) -> bool:
        raise error

    monkeypatch.setattr(webbrowser, "open", broken)
    assert cli_module._open_browser(_PAGE) is False


# --------------------------------------------------------------------------
# Failures and exit codes (2.3, 2.8)
# --------------------------------------------------------------------------


def test_a_relay_instance_without_a_token_exits_1_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [], relay_token=False)
    code, lines = _run(tmp_path)
    assert code == 1
    assert lines == [
        f"{_NAME}: the relay instance home has no stored token.",
        "Connect the relay instance first: run `fitdocs connect home`.",
    ]
    assert session.transport.requests == []
    assert session.opened == []
    assert _credential_files() == []


def test_a_refused_consent_prints_the_code_and_the_next_step_and_stores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path, monkeypatch, [_started(), _envelope(RelayCode.CONNECT_REFUSED)]
    )
    code, lines = _run(tmp_path)
    assert code == 1
    assert lines[4:] == [
        f"{_NAME}: connect-refused: The connection was declined, or was not given "
        "every permission it needs.",
        f"Run `fitdocs connect {_NAME}` again and allow every permission that is "
        "asked for.",
    ]
    assert session.opened == [_PAGE]
    assert _credential_files() == ["home.toml"]


def test_a_start_the_relay_refuses_prints_no_started_lines_and_opens_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [_envelope(RelayCode.NOT_OFFERED)])
    code, lines = _run(tmp_path)
    assert code == 1
    assert lines == [
        f"{_NAME}: not-offered: This relay does not offer that.",
        "Ask the operator of the relay instance `home` to offer this target, or "
        "use another relay.",
    ]
    assert session.opened == []


def test_an_unmapped_exception_prints_its_type_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path, monkeypatch, [])

    def broken(request: HttpRequest, timeout: float) -> HttpResponse:
        raise ValueError("boom")

    monkeypatch.setattr(cli_module, "_connector_transport", lambda: broken)
    code, lines = _run(tmp_path)
    assert code == 1
    assert lines == ["ValueError: boom"]


def test_an_unmapped_exception_after_the_start_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path, monkeypatch, [])
    answers = [_started()]

    def broken(request: HttpRequest, timeout: float) -> HttpResponse:
        if answers:
            return answers.pop(0)
        raise ValueError(f"bad poll {_POLL_SECRET} with {_RELAY_TOKEN}")

    monkeypatch.setattr(cli_module, "_connector_transport", lambda: broken)
    code, lines = _run(tmp_path)
    assert code == 1
    assert answers == []
    assert lines[-1] == "ValueError: bad poll <redacted> with <redacted>"
    printed = "\n".join(lines)
    for hidden in (_POLL_SECRET, _RELAY_TOKEN, _CONNECTION_TOKEN):
        assert hidden not in printed


def test_an_interrupt_while_waiting_exits_130_and_stores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_started(), _pending()],
        clock=_Clock(interrupt_on_sleep=True),
    )
    code, lines = _run(tmp_path)
    assert code == 130
    assert lines == [
        _HEADER,
        _ADDRESS,
        _CODE_LINE,
        "This attempt expires in 10 minutes.",
        f"{_NAME}: interrupted; nothing was stored.",
    ]
    assert len(session.transport.requests) == 1
    assert _credential_files() == ["home.toml"]


# --------------------------------------------------------------------------
# Refused flags (2.10)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flags",
    [
        ["--register"],
        ["--email", "me@example.com"],
        ["--register", "--email", "me@example.com"],
    ],
    ids=["register", "email", "register-and-email"],
)
def test_register_and_email_on_a_strava_instance_exit_2_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str]
) -> None:
    session = _setup(tmp_path, monkeypatch, [])
    code, lines = _run(tmp_path, *flags)
    assert code == 2
    assert lines == [f"{_NAME}: --register and --email apply only to a relay instance."]
    assert session.transport.requests == []
    assert session.opened == []
    assert session.prompts == []
    assert _credential_files() == ["home.toml"]


@pytest.mark.parametrize(
    ("settings", "name"),
    [
        (f'[connectors.{_NAME}]\nconnector = "relay"\nurl = "{_URL}"\n', _NAME),
        ('[connectors.puller]\nconnector = "scripted-puller"\n', "puller"),
        ('[connectors.keyed]\nconnector = "personal-key"\n', "keyed"),
        ('[connectors.logged]\nconnector = "login-style"\n', "logged"),
    ],
    ids=["relay", "no-auth", "api-key", "login"],
)
def test_no_browser_on_another_style_exits_2_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: str, name: str
) -> None:
    connector_registry.register(ScriptedPuller())
    connector_registry.register(ScriptedPersonalKeyConnector())
    connector_registry.register(ScriptedLoginConnector())
    session = _setup(tmp_path, monkeypatch, [], settings=settings, relay_token=False)
    code, lines = _run(tmp_path, "--no-browser", name=name)
    assert code == 2
    assert lines == [
        f"{name}: --no-browser applies only to a browser-consent instance."
    ]
    assert session.transport.requests == []
    assert session.prompts == []
    assert _credential_files() == []
