"""``fitdocs connect`` for relay instances (relay-server task 6.6;
Requirements 12.1, 12.5, 13.2, 13.11, 15.1).

Drives the installed entry point through :class:`typer.testing.CliRunner`.
The prompts, the TTY check and the transport are the seams ``cli.py`` names;
the transport is a scripted ``FakeTransport`` and the clock is a fake whose
``sleep`` advances ``datetime.now`` as seen by ``cli.py``. The relay
connector is the real built-in one; the credentials directory is the one the
package conftest points ``FITDOCS_CREDENTIALS_DIR`` at.

Printed lines are literals copied by hand, not the engine's constants.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.http import HttpResponse, TransportError
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.secrets import Redactor
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
)
from tests.connectors.test_cli_connectors import (
    RESERVED_RELAY_TABLE,
    _ReservedConnector,
)
from tests.connectors.test_relay_connect import _TOKEN, _envelope
from tests.connectors.test_relay_register import (
    _EMAIL,
    _POLL_SECRET,
    _USER_CODE,
    _caps,
    _issued,
    _pending,
    _started,
)

runner = CliRunner()

_NAME = "my-relay"
_URL = "https://relay.example.com"
_TOKEN_VARIABLE = "FITDOCS_CONNECTOR_MY_RELAY_TOKEN"
_EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

_FORMAT_LINE = (
    "That is not a relay token: a relay token looks like "
    "fdr1_<16 characters>_<52 characters>."
)
_EMAIL_LINE = "That is not a plausible email address."
_HINT = "To get your credentials, see https://fitdocs.ai/guides/connectors/"


@dataclass
class _Clock:
    """Fake time as ``cli.py`` sees it. ``sleep`` advances it; ``per_call``
    additionally advances it on every ``now()`` read."""

    offset: float = 0.0
    per_call: float = 0.0
    sleeps: list[float] = field(default_factory=list)
    interrupt_on_sleep: bool = False

    def now(self, tz: object = None) -> datetime:
        value = _EPOCH + timedelta(seconds=self.offset)
        self.offset += self.per_call
        return value

    def sleep(self, seconds: float) -> None:
        if self.interrupt_on_sleep:
            raise KeyboardInterrupt
        self.sleeps.append(seconds)
        self.offset += seconds


@dataclass
class _Session:
    transport: FakeTransport
    clock: _Clock
    secret_calls: list[str]
    value_calls: list[str]
    root: Path


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: Sequence[HttpResponse | TransportError],
    *,
    interactive: bool = True,
    secrets: dict[str, str] | None = None,
    values: dict[str, str] | None = None,
    clock: _Clock | None = None,
) -> _Session:
    (tmp_path / "fitdocs.toml").write_text(
        f'[connectors.{_NAME}]\nconnector = "relay"\nurl = "{_URL}"\n'
    )
    transport = FakeTransport(list(script))
    the_clock = clock if clock is not None else _Clock()
    secret_calls: list[str] = []
    value_calls: list[str] = []
    answers_secret = secrets or {}
    answers_value = values or {}

    def fake_secret(prompt: str) -> str:
        secret_calls.append(prompt)
        if prompt not in answers_secret:
            raise AssertionError(f"unscripted secret prompt: {prompt!r}")
        return answers_secret[prompt]

    def fake_value(prompt: str) -> str:
        value_calls.append(prompt)
        if prompt not in answers_value:
            raise AssertionError(f"unscripted value prompt: {prompt!r}")
        return answers_value[prompt]

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return the_clock.now(tz)

    monkeypatch.setattr(cli_module, "_ask_secret", fake_secret)
    monkeypatch.setattr(cli_module, "_ask_value", fake_value)
    monkeypatch.setattr(cli_module, "_stdin_is_interactive", lambda: interactive)
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: transport)
    monkeypatch.setattr(cli_module, "datetime", _FakeDatetime)
    monkeypatch.setattr(time, "sleep", the_clock.sleep)
    return _Session(transport, the_clock, secret_calls, value_calls, tmp_path)


def _credentials_files() -> list[Path]:
    directory = Path(os.environ["FITDOCS_CREDENTIALS_DIR"])
    return sorted(directory.iterdir()) if directory.exists() else []


def _run(tmp_path: Path, *args: str) -> tuple[int, list[str]]:
    result = runner.invoke(app, ["connect", _NAME, *args, "--out", str(tmp_path)])
    return result.exit_code, result.output.splitlines()


def _stored_path() -> Path:
    return Path(os.environ["FITDOCS_CREDENTIALS_DIR"]) / f"{_NAME}.toml"


# --------------------------------------------------------------------------
# Pasted token (Req 12.1, 12.3, 12.4)
# --------------------------------------------------------------------------


def test_paste_prompts_without_echo_checks_once_and_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_envelope(RelayCode.OK)],
        secrets={"Relay token: ": _TOKEN},
    )
    code, lines = _run(tmp_path)
    assert code == 0
    assert lines == [
        _HINT,
        f"{_NAME}: connected.",
        f"Credentials: {_stored_path()}",
        f"Relay: {_URL}",
    ]
    assert session.secret_calls == ["Relay token: "]
    assert session.value_calls == []
    assert len(session.transport.requests) == 1
    assert _credentials_files() == [_stored_path()]
    assert _TOKEN in _stored_path().read_text()
    assert _TOKEN not in "\n".join(lines)


def test_paste_success_names_an_overriding_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_TOKEN_VARIABLE, "from-the-environment")
    _setup(
        tmp_path,
        monkeypatch,
        [_envelope(RelayCode.OK)],
        secrets={"Relay token: ": _TOKEN},
    )
    code, lines = _run(tmp_path)
    assert code == 0
    assert lines[4:] == [
        "Overriding environment variables (used instead of the stored values "
        f"during a pull): {_TOKEN_VARIABLE}"
    ]
    assert len(lines) == 5


def test_paste_refused_prints_code_explanation_and_next_step_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_envelope(RelayCode.TOKEN_UNKNOWN)],
        secrets={"Relay token: ": _TOKEN},
    )
    code, lines = _run(tmp_path)
    assert code == 1
    assert lines == [
        _HINT,
        f"{_NAME}: token-unknown: The relay does not recognise this token.",
        "Check the token you pasted, or ask the relay's operator for a new one, "
        f"then run `fitdocs connect {_NAME}`.",
    ]
    assert len(session.transport.requests) == 1
    assert _credentials_files() == []


def test_paste_unreachable_relay_prints_its_code_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(
        tmp_path,
        monkeypatch,
        [TransportError("connection refused")],
        secrets={"Relay token: ": _TOKEN},
    )
    code, lines = _run(tmp_path)
    assert code == 1
    assert lines[0] == _HINT
    assert lines[1].startswith(f"{_NAME}: relay-unreachable: ")
    assert len(lines) == 3
    assert _credentials_files() == []


@pytest.mark.parametrize("pasted", ["a", "", "fdr1_short", _TOKEN + "x"])
def test_malformed_token_exits_2_with_the_fixed_message_unredacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pasted: str
) -> None:
    session = _setup(tmp_path, monkeypatch, [], secrets={"Relay token: ": pasted})
    code, lines = _run(tmp_path)
    assert code == 2
    # A one-character paste is registered for redaction before the format
    # check; the message must still read exactly as the fixed text.
    assert lines == [_HINT, _FORMAT_LINE]
    assert session.transport.requests == []
    assert _credentials_files() == []


def test_interrupt_at_the_token_prompt_exits_130_with_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [])

    def interrupted(prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "_ask_secret", interrupted)
    code, lines = _run(tmp_path)
    assert code == 130
    assert lines == [_HINT, f"{_NAME}: interrupted; nothing was stored."]
    assert session.transport.requests == []
    assert _credentials_files() == []


# --------------------------------------------------------------------------
# Exit 2 before any request (Req 12.5, 13.2, 13.11)
# --------------------------------------------------------------------------


def test_non_interactive_paste_exits_2_naming_the_override_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [], interactive=False)
    code, lines = _run(tmp_path)
    assert code == 2
    assert lines == [
        f"{_NAME}: standard input is not an interactive terminal; "
        f"an unattended command can use {_TOKEN_VARIABLE} instead. {_HINT}"
    ]
    assert session.transport.requests == []
    assert session.secret_calls == [] and session.value_calls == []


def test_non_interactive_register_without_email_exits_2_naming_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [], interactive=False)
    code, lines = _run(tmp_path, "--register")
    assert code == 2
    assert lines == [
        f"{_NAME}: standard input is not an interactive terminal; "
        f"pass --email ADDRESS, or an unattended command can use "
        f"{_TOKEN_VARIABLE} instead."
    ]
    assert session.transport.requests == []
    assert session.secret_calls == [] and session.value_calls == []


def test_non_interactive_register_with_an_email_option_needs_no_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path, monkeypatch, [_caps(), _started(), _issued()], interactive=False
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 0
    assert lines[0] == f"Registering {_EMAIL}."
    assert session.secret_calls == [] and session.value_calls == []
    assert _credentials_files() == [_stored_path()]


def test_email_without_register_on_a_relay_instance_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [])
    code, lines = _run(tmp_path, "--email", _EMAIL)
    assert code == 2
    assert lines == [f"{_NAME}: --email needs --register."]
    assert session.transport.requests == []
    assert session.secret_calls == [] and session.value_calls == []
    assert _credentials_files() == []


_FLAG_SETS = [
    ["--register"],
    ["--email", _EMAIL],
    ["--register", "--email", _EMAIL],
]


def _non_relay_connectors() -> list[object]:
    return [
        ScriptedPersonalKeyConnector(),
        ScriptedLoginConnector(),
        ScriptedPuller(),
        _ReservedConnector(),
    ]


@pytest.mark.parametrize("flags", _FLAG_SETS)
@pytest.mark.parametrize("index", range(4))
def test_register_or_email_on_a_non_relay_instance_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str], index: int
) -> None:
    connector = _non_relay_connectors()[index]
    connector_registry.register(connector)  # type: ignore[arg-type]
    styles = [c.auth_style for c in _non_relay_connectors()]  # type: ignore[attr-defined]
    assert len(set(styles)) == 4  # api-key, login, none, browser-consent
    session = _setup(tmp_path, monkeypatch, [])
    (tmp_path / "fitdocs.toml").write_text(
        f'[connectors.{_NAME}]\nconnector = "{connector.connector_id}"\n'  # type: ignore[attr-defined]
        + RESERVED_RELAY_TABLE
    )
    code, lines = _run(tmp_path, *flags)
    assert code == 2
    assert lines == [f"{_NAME}: --register and --email apply only to a relay instance."]
    assert session.transport.requests == []
    assert session.secret_calls == [] and session.value_calls == []
    assert _credentials_files() == []


def test_interrupt_at_the_real_email_prompt_exits_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_ask_value = cli_module._ask_value
    session = _setup(tmp_path, monkeypatch, [])

    def interrupted(prompt: object) -> str:
        raise KeyboardInterrupt

    # The real prompt function, over click's input: typer turns the
    # KeyboardInterrupt into typer.Abort.
    monkeypatch.setattr(cli_module, "_ask_value", real_ask_value)
    monkeypatch.setattr("typer._click.termui.visible_prompt_func", interrupted)
    code, lines = _run(tmp_path, "--register")
    assert code == 130
    assert len(lines) == 1
    assert lines[0].endswith(f"{_NAME}: interrupted; nothing was stored.")
    assert "Abort" not in "\n".join(lines)
    assert session.transport.requests == []
    assert _credentials_files() == []


@pytest.mark.parametrize("address", ["nope", "", "a@b", "two words@example.org"])
def test_implausible_email_exits_2_with_the_engines_message_and_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    session = _setup(tmp_path, monkeypatch, [])
    code, lines = _run(tmp_path, "--register", "--email", address)
    assert code == 2
    assert lines == [_EMAIL_LINE]
    assert session.transport.requests == []
    assert _credentials_files() == []


def test_implausible_prompted_email_exits_2_with_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path, monkeypatch, [], values={"Email address: ": "not an email"}
    )
    code, lines = _run(tmp_path, "--register")
    assert code == 2
    assert lines == [_EMAIL_LINE]
    assert session.value_calls == ["Email address: "]
    assert session.transport.requests == []


# --------------------------------------------------------------------------
# Registration (Req 13.1, 13.3, 13.6-13.10)
# --------------------------------------------------------------------------


def test_register_with_email_option_prints_started_lines_and_stores_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(interval_s=10), _pending(), _issued()],
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 0
    assert lines == [
        f"Registering {_EMAIL}.",
        f"Your code: {_USER_CODE}",
        "Check your email for a confirmation link, and open it to continue. "
        "Confirm only if the page shows this same code.",
        "This registration expires in 10 minutes.",
        f"{_NAME}: connected.",
        f"Credentials: {_stored_path()}",
        f"Relay: {_URL}",
    ]
    assert len(session.transport.requests) == 4
    assert session.clock.sleeps == [10, 10]
    assert session.secret_calls == [] and session.value_calls == []
    stored = _stored_path().read_text()
    assert _TOKEN in stored
    assert _EMAIL not in stored and _POLL_SECRET not in stored
    assert _POLL_SECRET not in "\n".join(lines)


def test_register_prompts_for_the_email_when_no_option_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(), _issued()],
        values={"Email address: ": _EMAIL},
    )
    code, lines = _run(tmp_path, "--register")
    assert code == 0
    assert lines[0] == f"Registering {_EMAIL}."
    assert session.value_calls == ["Email address: "]
    assert session.secret_calls == []


@pytest.mark.parametrize(
    ("expires_in_s", "remaining"),
    [(60, "1 minute"), (170, "2 minutes"), (600, "10 minutes")],
)
def test_minutes_remaining_are_whole_minutes_rounded_down(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expires_in_s: int,
    remaining: str,
) -> None:
    _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(expires_in_s=expires_in_s), _issued()],
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 0
    assert lines[3] == f"This registration expires in {remaining}."


def test_under_a_minute_remaining_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every clock read moves time on, so less than the stated minute is left
    # by the time the lines print.
    session = _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(expires_in_s=60), _issued()],
        clock=_Clock(per_call=20),
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 0
    assert lines[3] == "This registration expires in less than a minute."
    assert session.clock.offset > 0


def test_relay_that_does_not_offer_registration_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(tmp_path, monkeypatch, [_caps(registration=False)])
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 1
    assert lines == [
        f"{_NAME}: not-offered: This relay does not offer that.",
        "Ask the relay's operator for a token.",
    ]
    assert len(session.transport.requests) == 1
    assert _credentials_files() == []


def test_registration_refused_prints_code_and_next_step_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(), _envelope(RelayCode.REGISTRATION_REFUSED)],
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 1
    assert lines[4].startswith(f"{_NAME}: registration-refused: ")
    assert lines[5] == "Ask the relay's operator for a token."
    assert len(lines) == 6
    assert _credentials_files() == []


def test_expired_registration_exits_1_and_stores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(interval_s=20, expires_in_s=60)] + [_pending()] * 2,
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 1
    assert lines[4:] == [
        f"{_NAME}: registration-expired: "
        "The registration expired before it was confirmed.",
        f"Run `fitdocs connect {_NAME} --register` again.",
    ]
    assert len(session.transport.requests) == 4
    assert _credentials_files() == []


def test_interrupt_while_polling_exits_130_and_stores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _setup(
        tmp_path,
        monkeypatch,
        [_caps(), _started(), _pending()],
        clock=_Clock(interrupt_on_sleep=True),
    )
    code, lines = _run(tmp_path, "--register", "--email", _EMAIL)
    assert code == 130
    assert lines[:4] == [
        f"Registering {_EMAIL}.",
        f"Your code: {_USER_CODE}",
        "Check your email for a confirmation link, and open it to continue. "
        "Confirm only if the page shows this same code.",
        "This registration expires in 10 minutes.",
    ]
    assert lines[4:] == [f"{_NAME}: interrupted; nothing was stored."]
    assert len(session.transport.requests) == 2
    assert _credentials_files() == []


def test_unexpected_engine_exception_is_a_redacted_line_with_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup(tmp_path, monkeypatch, [], secrets={"Relay token: ": _TOKEN})

    def boom(*args: object, **kwargs: object) -> object:
        redactor = kwargs["redactor"]
        assert isinstance(redactor, Redactor)
        redactor.add(_TOKEN)
        raise RuntimeError(f"exploded near {_TOKEN}")

    monkeypatch.setattr(cli_module, "run_relay_connect", boom)
    code, lines = _run(tmp_path)
    assert code == 1
    assert len(lines) == 2
    assert lines[0] == _HINT
    assert lines[1].startswith("RuntimeError: exploded near ")
    assert _TOKEN not in lines[1]
