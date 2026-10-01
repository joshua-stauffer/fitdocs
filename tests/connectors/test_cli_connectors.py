"""CLI end-to-end tests: ``fitdocs connect`` (task 5.1) and ``fitdocs pull``
(task 5.2, in the ``# --- pull ---`` section near the bottom of this module).

Drives the installed entry point through :class:`typer.testing.CliRunner`,
with every connector-facing seam patched (the transport, the TTY check, the
two prompt functions) exactly as design.md's ``CliCommands`` names them, and
the package-level ``tests/connectors/conftest.py`` autouse fixtures doing the
network/registry/environment isolation (socket guard, registry
snapshot/restore, ``FITDOCS_CREDENTIALS_DIR``/``HOME`` pointed outside any
sandbox a test builds). Synthetic connectors come from that conftest
(:class:`ScriptedPersonalKeyConnector`, :class:`ScriptedLoginConnector`,
:class:`ScriptedPuller`, the lone ``AuthStyle.NONE`` fixture there); the
reserved-style (``OAUTH_BROWSER``) connector and the two-field API_KEY
connector this module needs have no counterpart there and are defined
locally, per the plan's "keep helpers local to their own test module" rule.

Several tests below pin an *exact* line of output rather than a substring:
the message text is itself part of what a requirement specifies (which
variables are named, which order two checks fire in, whether a secret or a
path survived redaction), so a substring check that would stay green under a
dropped clause or a wrong-but-overlapping word is not evidence. Where a
pinned line quotes design.md's/``errors.py``'s next-step guidance, the text
is a literal copied by hand, not the imported ``NEXT_STEPS``/``REDACTED``
constant -- a self-referential compare against the same constant the
production code reads cannot catch a change to that constant.

Requirements 1.7, 3.9, 4.2, 5.1, 5.2, 5.3, 5.4, 5.9, 10.6 (``connect``); 3.9,
4.2, 6.1, 6.2, 6.3, 6.9, 8.4, 11.1-11.5 (``pull``, task 5.2).
"""

from __future__ import annotations

import dataclasses
import getpass
import os
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import typer
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import CredentialStore, env_var_name
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind
from fitdocs.connectors.http import TransportError, urllib_transport
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    CredentialField,
    Declined,
    Deferred,
    Granted,
    Listing,
    RemoteActivity,
    SettingsContext,
    TokenSet,
)
from fitdocs.connectors.pull import (
    Delivered,
    InstancePullReport,
    PullNote,
    PullOptions,
    PullReport,
)
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import (
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
)

runner = CliRunner()


@dataclass
class _ReservedConnector:
    """A minimal ``AuthStyle.OAUTH_BROWSER`` connector (Req 1.7, 5.3).

    No counterpart in ``tests/connectors/conftest.py`` -- local per the
    plan's rule that tasks after 2.3 keep their own fixtures local.
    """

    connector_id: str = "reserved-style"
    display_name: str = "Reserved Style"
    auth_style: AuthStyle = AuthStyle.OAUTH_BROWSER
    capabilities: frozenset[Capability] = field(
        default_factory=lambda: frozenset({Capability.PULL_WELLNESS})
    )
    credential_fields: tuple[CredentialField, ...] = (
        CredentialField("token", "Token", secret=True),
    )

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object:
        return None


class _TwoFieldKey(ScriptedPersonalKeyConnector):
    """An ``API_KEY`` connector with two fields, so the non-interactive
    refusal has more than one variable name to join -- a single-field
    connector cannot distinguish "names every variable" from "names a
    variable"."""

    connector_id = "two-field-key"
    credential_fields: tuple[CredentialField, ...] = (  # type: ignore[assignment]
        CredentialField("api_key", "API Key", secret=True),
        CredentialField("athlete_id", "Athlete ID", secret=False),
    )


def _write_settings(data_root: Path, *, connectors: str) -> None:
    (data_root / "fitdocs.toml").write_text(connectors)


def _credentials_dir() -> Path:
    """The per-test credentials directory the package conftest resolved."""
    return Path(os.environ["FITDOCS_CREDENTIALS_DIR"])


def _patch_prompts(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secrets: dict[str, str] | None = None,
    values: dict[str, str] | None = None,
    interactive: bool = True,
) -> tuple[list[str], list[str]]:
    """Patch the four seams CliCommands declares; return (secret, value) call logs.

    ``secrets``/``values`` map a prompt string to the canned answer; a prompt
    not present in either dict is unscripted and raises -- a test must name
    every field it expects to be asked for.
    """
    secret_calls: list[str] = []
    value_calls: list[str] = []
    secrets = secrets or {}
    values = values or {}

    def fake_secret(prompt: str) -> str:
        secret_calls.append(prompt)
        if prompt not in secrets:
            raise AssertionError(f"unscripted secret prompt: {prompt!r}")
        return secrets[prompt]

    def fake_value(prompt: str) -> str:
        value_calls.append(prompt)
        if prompt not in values:
            raise AssertionError(f"unscripted value prompt: {prompt!r}")
        return values[prompt]

    def _forbidden_transport(request: object, timeout: float) -> object:
        raise AssertionError(
            "no synthetic connector used by this test module makes a real "
            "request; this transport must never actually be called"
        )

    monkeypatch.setattr(cli_module, "_ask_secret", fake_secret)
    monkeypatch.setattr(cli_module, "_ask_value", fake_value)
    monkeypatch.setattr(cli_module, "_stdin_is_interactive", lambda: interactive)
    monkeypatch.setattr(
        cli_module, "_connector_transport", lambda: _forbidden_transport
    )
    return secret_calls, value_calls


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def _lines(output: str) -> list[str]:
    return output.splitlines()


def _collapsed(output: str) -> str:
    """Strip Rich's box-drawing characters and collapse all whitespace
    (including the hard line wraps Rich inserts inside a fixed-width panel)
    to single spaces, so a help-text pin does not depend on the terminal
    width the test happens to run under."""
    cleaned = "".join(ch for ch in output if ch not in "│╭╮╰╯─┃┏┓┗┛")
    return " ".join(cleaned.split())


# ---------------------------------------------------------------------------
# The seams themselves (design.md's CliCommands names each one explicitly)
# ---------------------------------------------------------------------------


def test_ask_secret_reads_through_getpass(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patched on the stdlib/third-party module objects directly -- the same
    # objects ``cli.py``'s own ``import getpass``/``import typer`` bind to,
    # since a module is a process-wide singleton -- rather than through
    # ``cli_module.getpass``/``cli_module.typer`` (mypy --strict flags that
    # path as an implicit reexport).
    seen: list[str] = []

    def fake_getpass(prompt: str) -> str:
        seen.append(prompt)
        return "typed"

    monkeypatch.setattr(getpass, "getpass", fake_getpass)

    def _visible(*a: object, **k: object) -> str:
        raise AssertionError("visible prompt used for a secret field")

    monkeypatch.setattr(typer, "prompt", _visible)

    assert cli_module._ask_secret("API Key: ") == "typed"
    assert seen == ["API Key: "]


def test_stdin_is_interactive_delegates_to_isatty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for answer in (False, True):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda a=answer: a))
        assert cli_module._stdin_is_interactive() is answer


def test_connector_transport_is_urllib_transport() -> None:
    assert cli_module._connector_transport() is urllib_transport


# ---------------------------------------------------------------------------
# Preflight / configuration errors
# ---------------------------------------------------------------------------


def test_missing_name_argument_is_a_usage_error() -> None:
    """The NAME argument is required (``typer.Argument(...)``); dropping the
    required marker would let an empty name reach the command body instead
    of failing before it is ever invoked."""
    result = runner.invoke(app, ["connect"])
    assert result.exit_code == 2
    assert "Missing argument" in result.output


def test_data_root_error_is_the_resolver_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 3.9: ``connect`` resolves the data root the same way every other
    command does -- a non-existent ``--out`` is refused before anything else
    is read, with the standard resolver message."""
    _patch_prompts(monkeypatch)
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["connect", "anything", "--out", str(missing)])

    assert result.exit_code == 2
    assert result.output.startswith(f"The --out path does not exist: {missing}\n")


def test_unknown_name_names_every_configured_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for c in (
        ScriptedPersonalKeyConnector(),
        ScriptedLoginConnector(),
        ScriptedPuller(),
    ):
        connector_registry.register(c)
    _write_settings(
        tmp_path,
        connectors=(
            "[connectors.scripted-puller]\n"
            "[connectors.personal-key]\n"
            "[connectors.login-style]\n"
        ),
    )
    _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "nope", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "'nope' is not a configured connector instance; configured "
        "instances: login-style, personal-key, scripted-puller"
    ]


def test_no_configured_instances_lists_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "anything", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "'anything' is not a configured connector instance; configured instances: none"
    ]


def test_malformed_connectors_table_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPersonalKeyConnector())
    _write_settings(tmp_path, connectors="[connectors]\npersonal-key = 7\n")
    _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert result.output.startswith(f"{tmp_path / 'fitdocs.toml'}: [connectors")


def test_none_style_prints_nothing_to_connect_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPuller()
    assert connector.auth_style is AuthStyle.NONE
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.scripted-puller]\n")
    secret_calls, value_calls = _patch_prompts(monkeypatch)
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["connect", "scripted-puller", "--out", str(tmp_path)])

    assert result.exit_code == 0
    assert _lines(result.output) == [
        "scripted-puller: this connector requires no authentication; "
        "nothing to connect."
    ]
    assert secret_calls == []
    assert value_calls == []
    assert _snapshot(tmp_path) == before
    assert not _credentials_dir().exists() or list(_credentials_dir().iterdir()) == []


def test_reserved_style_exact_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(_ReservedConnector())
    _write_settings(tmp_path, connectors="[connectors.reserved-style]\n")
    secret_calls, value_calls = _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "reserved-style", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "reserved-style: oauth-browser authentication is reserved; this "
        "version of fitdocs does not support it."
    ]
    assert secret_calls == []
    assert value_calls == []


def test_non_interactive_names_every_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(_TwoFieldKey())
    _write_settings(tmp_path, connectors="[connectors.two-field-key]\n")
    secret_calls, value_calls = _patch_prompts(monkeypatch, interactive=False)

    result = runner.invoke(app, ["connect", "two-field-key", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "two-field-key: standard input is not an interactive terminal; an "
        "unattended pull can use FITDOCS_CONNECTOR_TWO_FIELD_KEY_API_KEY, "
        "FITDOCS_CONNECTOR_TWO_FIELD_KEY_ATHLETE_ID instead."
    ]
    assert secret_calls == []
    assert value_calls == []


def test_non_interactive_login_exact_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedLoginConnector())
    _write_settings(tmp_path, connectors="[connectors.login-style]\n")
    secret_calls, value_calls = _patch_prompts(monkeypatch, interactive=False)

    result = runner.invoke(app, ["connect", "login-style", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "login-style: standard input is not an interactive terminal; "
        "`fitdocs connect` needs one to prompt for credentials."
    ]
    assert secret_calls == []
    assert value_calls == []


# ---------------------------------------------------------------------------
# Check ORDER: two-violation fixtures per adjacent pair
# ---------------------------------------------------------------------------


def test_none_style_wins_over_a_bad_credentials_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """design.md orders the AuthStyle.NONE short-circuit *before* the
    credentials-directory resolution/check -- a connector that needs no
    authentication must succeed even when FITDOCS_CREDENTIALS_DIR is
    unusable, since connect never touches it in that case."""
    connector_registry.register(ScriptedPuller())
    _write_settings(tmp_path, connectors="[connectors.scripted-puller]\n")
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", "relative/creds")
    _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "scripted-puller", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert _lines(result.output) == [
        "scripted-puller: this connector requires no authentication; "
        "nothing to connect."
    ]


def test_reserved_style_wins_over_credentials_directory_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the reserved-style refusal and the credentials-directory refusal
    would fire; design.md's order puts the style check first."""
    connector_registry.register(_ReservedConnector())
    _write_settings(tmp_path, connectors="[connectors.reserved-style]\n")
    # Violate the credentials-directory check too: point it at a *relative*
    # path, which resolve_credentials_dir refuses outright.
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", "relative/creds")
    secret_calls, value_calls = _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "reserved-style", "--out", str(tmp_path)])

    assert result.exit_code == 2
    lowered = result.output.lower()
    assert "oauth-browser" in lowered or "reserved" in lowered
    assert "FITDOCS_CREDENTIALS_DIR" not in result.output
    assert secret_calls == []
    assert value_calls == []


def test_credentials_inside_data_root_names_the_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPersonalKeyConnector())
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    creds = tmp_path / "creds"
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(creds))
    secret_calls, value_calls = _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert result.output.startswith(
        f"credentials directory {creds.resolve()} is the data root "
        f"{tmp_path.resolve()} or lies inside it"
    )
    assert secret_calls == []
    assert value_calls == []


def test_credentials_directory_check_wins_over_non_interactive_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both the credentials-directory refusal and the non-interactive
    refusal would fire; design.md's order checks the directory first."""
    connector_registry.register(ScriptedPersonalKeyConnector())
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    # The credentials directory resolves inside the data root -- refused by
    # check_outside_data_root -- *and* stdin is non-interactive.
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(tmp_path / "creds"))
    secret_calls, value_calls = _patch_prompts(monkeypatch, interactive=False)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert "is the data root" in result.output or "lies inside it" in result.output
    expected_var = env_var_name("personal-key", "api_key")
    assert expected_var not in result.output
    assert secret_calls == []
    assert value_calls == []


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------


def test_secret_field_prompted_without_echo_plain_through_visible_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedLoginConnector()
    connector.login_script.append(
        TokenSet(values={}, expires_at=None, scopes=("read",))
    )
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.login-style]\n")
    secret_calls, value_calls = _patch_prompts(
        monkeypatch,
        secrets={"Password: ": "s3cr3t-tok3n"},
        values={"Username: ": "athlete"},
    )

    result = runner.invoke(app, ["connect", "login-style", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert secret_calls == ["Password: "]
    assert value_calls == ["Username: "]
    assert "s3cr3t-tok3n" not in result.output


def test_empty_answer_exits_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector()
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    _patch_prompts(monkeypatch, secrets={"API Key: ": ""})

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == ["personal-key: API Key must not be empty."]
    assert connector.verify_calls == []
    store = CredentialStore(_credentials_dir())
    assert store.load("personal-key") is None


# ---------------------------------------------------------------------------
# run_connect outcomes
# ---------------------------------------------------------------------------


def test_connect_success_prints_instance_path_and_scopes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector()
    connector.verify_script.append(Granted(scopes=("read", "write")))
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    _patch_prompts(monkeypatch, secrets={"API Key: ": "s3cr3t-abc"})
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    expected_path = CredentialStore(_credentials_dir()).path_for("personal-key")
    assert _lines(result.output) == [
        "personal-key: connected.",
        f"Credentials: {expected_path}",
        "Scopes: read, write",
    ]
    assert "s3cr3t-abc" not in result.output
    assert expected_path.exists()
    assert oct(expected_path.stat().st_mode)[-3:] == "600"
    # Nothing written under the data root (Req 5.9).
    assert _snapshot(tmp_path) == before


def test_connect_success_no_scopes_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector()
    connector.verify_script.append(Granted(scopes=None))
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    _patch_prompts(monkeypatch, secrets={"API Key: ": "s3cr3t-def"})

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Scopes: the service reported no scopes" in result.output


def test_connect_success_lists_overriding_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector()
    connector.verify_script.append(Granted(scopes=("read",)))
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    expected_var = env_var_name("personal-key", "api_key")
    monkeypatch.setenv(expected_var, "env-key-value")
    _patch_prompts(monkeypatch, secrets={"API Key: ": "typed-key-value"})

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert expected_var in result.output


def test_connect_success_scopes_line_never_hard_wraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-1: the ``Scopes:`` print needs ``soft_wrap=True`` exactly like the
    ``Credentials:`` print does -- a long, comma-joined scope list is exactly
    as path-bearing as a filesystem path, and Rich hard-wraps a non-soft_wrap
    print at the console width (80 columns under CI's TERM=dumb, Req 5.5)."""
    connector = ScriptedPersonalKeyConnector()
    long_scopes = tuple(
        f"scope-{i}-quite-a-bit-of-text-to-force-a-wrap" for i in range(4)
    )
    connector.verify_script.append(Granted(scopes=long_scopes))
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    _patch_prompts(monkeypatch, secrets={"API Key: ": "s3cr3t-wrap"})

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert f"Scopes: {', '.join(long_scopes)}" in result.output


def test_connect_success_env_override_line_never_hard_wraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-1: same as above for the "Overriding environment variables" print --
    two long variable names comma-joined onto one already-long sentence
    exceed 80 columns, so a missing ``soft_wrap=True`` would split it."""
    connector = _TwoFieldKey()
    connector.verify_script.append(Granted(scopes=("read",)))
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.two-field-key]\n")
    api_var = env_var_name("two-field-key", "api_key")
    athlete_var = env_var_name("two-field-key", "athlete_id")
    monkeypatch.setenv(api_var, "env-key-value")
    monkeypatch.setenv(athlete_var, "env-athlete-value")
    _patch_prompts(
        monkeypatch,
        secrets={"API Key: ": "typed-key-value"},
        values={"Athlete ID: ": "typed-athlete-value"},
    )

    result = runner.invoke(app, ["connect", "two-field-key", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (
        "Overriding environment variables (used instead of the stored "
        f"values during a pull): {api_var}, {athlete_var}" in result.output
    )


_STEPS: dict[AuthFailureKind, str] = {
    AuthFailureKind.REJECTED: (
        "Check the credentials and run `fitdocs connect personal-key` again."
    ),
    AuthFailureKind.CHALLENGE: (
        "The service asked for a verification step fitdocs cannot complete. "
        "Complete it on the service's own site, then run `fitdocs connect "
        "personal-key` again."
    ),
    AuthFailureKind.LOCKED: (
        "The service reports the account locked. Unlock it on the service's "
        "own site; do not try again until it is unlocked."
    ),
    AuthFailureKind.BLOCKED: (
        "The service refused this client. Please report it at "
        "https://github.com/joshua-stauffer/fitdocs/issues with the message "
        "above."
    ),
    AuthFailureKind.RATE_LIMITED: (
        "Wait before trying again. fitdocs never retries a sign-in: some "
        "services extend the limit on every attempt."
    ),
    AuthFailureKind.UNAVAILABLE: "The service could not be reached. Try again later.",
}


def _scripted_failure(kind: AuthFailureKind, message: str) -> BaseException:
    """This test drives ``UNAVAILABLE`` through the :class:`TransportError`
    path ``run_connect`` maps to ``UNAVAILABLE``. A connector can also raise
    ``AuthFailure(UNAVAILABLE)`` (e.g. ``http.auth_failure_from`` for a 5xx);
    that goes through the same :class:`AuthFailure` mapping the other five
    kinds exercise."""
    if kind is AuthFailureKind.UNAVAILABLE:
        return TransportError(message)
    return AuthFailure(kind, message)


@pytest.mark.parametrize("kind", list(_STEPS))
def test_each_failure_kind_exact_line_and_next_step(
    kind: AuthFailureKind, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector()
    typed = "typed-key-mno345"
    connector.verify_script.append(
        _scripted_failure(
            kind, f"service says {typed} is bad and cannot be used for this account"
        )
    )
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    _patch_prompts(monkeypatch, secrets={"API Key: ": typed})
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 1
    failure_line = (
        f"personal-key: {kind.value}: service says <redacted> is bad"
        " and cannot be used for this account"
    )
    # Longer than 80 columns, so a dropped soft_wrap hard-wraps it under CI.
    assert len(failure_line) > 80
    assert _lines(result.output) == [failure_line, _STEPS[kind]]
    store = CredentialStore(_credentials_dir())
    assert store.load("personal-key") is None
    # Nothing written under the data root on a refusal either (Req 5.9).
    assert _snapshot(tmp_path) == before


def test_unexpected_connector_exception_is_redacted_type_and_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4.5 follow-up: an unexpected exception from verify()/login() must
    never reach the terminal unredacted."""
    connector = ScriptedLoginConnector()
    typed_password = "unexpected-raise-jkl012"
    connector.login_script.append(
        ValueError(
            f"could not parse {typed_password} as the session response"
            " returned for this connector instance"
        )
    )
    connector_registry.register(connector)
    _write_settings(tmp_path, connectors="[connectors.login-style]\n")
    _patch_prompts(
        monkeypatch,
        secrets={"Password: ": typed_password},
        values={"Username: ": "athlete"},
    )
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["connect", "login-style", "--out", str(tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    unexpected_line = (
        "ValueError: could not parse <redacted> as the session response"
        " returned for this connector instance"
    )
    assert len(unexpected_line) > 80
    assert _lines(result.output) == [unexpected_line]
    store = CredentialStore(_credentials_dir())
    assert store.load("login-style") is None
    # Nothing written under the data root here either (Req 5.9).
    assert _snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# Crash handler / docstring / command count / help text
# ---------------------------------------------------------------------------


def test_app_never_shows_local_variables_on_a_crash() -> None:
    assert cli_module.app.pretty_exceptions_show_locals is False


def test_docstring_names_the_connect_command() -> None:
    doc = cli_module.__doc__ or ""
    assert "fitdocs connect NAME" in doc


def test_help_pins_the_name_argument_help_text() -> None:
    """S-2 remediation: a bare ``"NAME" in output`` check cannot catch Rich
    markup swallowing the bracketed ``[connectors.<name>]`` text this help
    string used to contain -- pin the exact rendered sentence instead."""
    result = runner.invoke(app, ["connect", "--help"])

    assert result.exit_code == 0
    assert "Arguments" in result.output
    assert "required" in result.output.lower()
    assert (
        "The name of a configured connector instance (a table under the "
        "connectors table in fitdocs.toml)." in _collapsed(result.output)
    )


def test_connect_summary_line_is_a_plain_sentence() -> None:
    """The top-level ``fitdocs --help`` command listing renders a command's
    first docstring paragraph as its one-line summary; a parenthetical
    design/requirement reference in that first paragraph used to leak into
    the summary verbatim."""
    result = runner.invoke(app, ["--help"])
    collapsed = _collapsed(result.output)

    assert result.exit_code == 0
    assert (
        "Authenticate one configured connector instance once and store its "
        "credentials only on success." in collapsed
    )
    assert "connectors design" not in collapsed


def test_invalid_settings_document_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_settings(tmp_path, connectors="[connectors\n")
    _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "anything", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert result.output.startswith(f"{tmp_path / 'fitdocs.toml'} is not valid TOML: ")


def test_invalid_inbox_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connector_registry.register(ScriptedPersonalKeyConnector())
    (tmp_path / "not-a-dir").write_text("")
    _write_settings(
        tmp_path,
        connectors='[inbox]\npath = "not-a-dir"\n\n[connectors.personal-key]\n',
    )
    secret_calls, value_calls = _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        f"{tmp_path / 'fitdocs.toml'}: [inbox] path exists but is not a "
        f"directory: {tmp_path / 'not-a-dir'}"
    ]
    assert secret_calls == []


def test_run_connect_receives_the_seam_transport_and_real_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPersonalKeyConnector())
    _write_settings(tmp_path, connectors="[connectors.personal-key]\n")
    _patch_prompts(monkeypatch, secrets={"API Key: ": "typed-wiring"})
    sentinel = object()
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: sentinel)
    seen: dict[str, object] = {}

    class _Stop(Exception):
        pass

    def fake_run_connect(instance: object, answers: object, **kwargs: object) -> object:
        seen.update(kwargs, answers=answers)
        raise _Stop("stop")

    monkeypatch.setattr(cli_module, "run_connect", fake_run_connect)

    result = runner.invoke(app, ["connect", "personal-key", "--out", str(tmp_path)])

    assert result.exit_code == 1
    assert seen["answers"] == {"api_key": "typed-wiring"}
    assert seen["transport"] is sentinel
    assert seen["sleep"] is time.sleep
    assert seen["environ"] is os.environ
    assert isinstance(seen["redactor"], Redactor)
    now = seen["now"]
    assert callable(now)
    assert now().tzinfo is UTC
    store = seen["store"]
    assert isinstance(store, CredentialStore)
    assert store.path_for("personal-key").parent == _credentials_dir()


def test_ask_value_reads_through_typer_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_prompt(*a: object, **k: object) -> str:
        seen.append((a, k))
        return "typed"

    def _no_echo(prompt: str) -> str:
        raise AssertionError("no-echo prompt used for a visible field")

    monkeypatch.setattr(typer, "prompt", fake_prompt)
    monkeypatch.setattr(getpass, "getpass", _no_echo)

    assert cli_module._ask_value("Username: ") == "typed"
    assert seen == [(("Username: ",), {})]


def test_none_style_long_instance_name_never_hard_wraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    name = "a-rather-long-instance-name-for-the-folder"
    _write_settings(
        tmp_path,
        connectors=f'[connectors.{name}]\nconnector = "scripted-puller"\n',
    )
    _patch_prompts(monkeypatch)

    result = runner.invoke(app, ["connect", name, "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert _lines(result.output) == [
        f"{name}: this connector requires no authentication; nothing to connect."
    ]


# ---------------------------------------------------------------------------
# fitdocs pull (task 5.2)
#
# Preflight-order tests below each build a *two*-violation fixture for one
# adjacent pair of design.md's stated check order and assert which message
# survives -- a fixture with only one violation present cannot tell "checked
# first" from "checked only". The internal order of the --sync-only block
# (athlete -> plugins -> tiles -> quarantine -> identity -> holds) is pinned
# only at its two ends here (athlete-before-plugins, identity-before-holds);
# the three middle adjacent pairs reuse already-tested call sequences
# (``_inbox_preflight``, ``_run_drain_passes``) rather than re-pinning them,
# and are declared UNPINNED in the task report.
# ---------------------------------------------------------------------------


def _fit_bytes(tag: bytes = b"") -> bytes:
    """Minimal, valid FIT header bytes; ``tag`` makes the content -- and so
    its hash -- distinct between calls (mirrors ``tests/connectors/test_pull.py``)."""
    return bytes([12, 0x10, 0, 0, 0, 0, 0, 0]) + b".FIT" + tag


def _forbidden_pull_transport(request: object, timeout: float) -> object:
    raise AssertionError(
        "no connector used by this section makes a real request through "
        "this transport seam; it must never actually be called"
    )


def _patch_pull_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module, "_connector_transport", lambda: _forbidden_pull_transport
    )


def test_docstring_names_the_pull_command() -> None:
    doc = cli_module.__doc__ or ""
    assert "fitdocs pull [NAMES...]" in doc


def test_pull_help_lists_the_five_options() -> None:
    result = runner.invoke(app, ["pull", "--help"])
    assert result.exit_code == 0
    collapsed = _collapsed(result.output)
    for option in ("--out", "--since", "--dry-run", "--sync", "--no-prompt"):
        assert option in collapsed


def test_pull_never_links_the_connectors_page() -> None:
    doc = cli_module.__doc__ or ""
    result = runner.invoke(app, ["pull", "--help"])
    assert "connectors.md" not in doc
    assert "connectors.md" not in result.output
    assert "connectors page" not in doc.lower()


# --- single-violation preflight configuration errors (exit 2) ------------


def test_pull_data_root_error_is_the_resolver_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["pull", "--out", str(missing)])

    assert result.exit_code == 2
    assert result.output.startswith(f"The --out path does not exist: {missing}\n")


def test_pull_sync_and_dry_run_conflict_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "--sync", "--dry-run", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "--sync cannot be combined with --dry-run: a dry run writes nothing."
    ]
    assert _snapshot(tmp_path) == before


def test_pull_invalid_since_date_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    before = _snapshot(tmp_path)

    result = runner.invoke(
        app, ["pull", "--since", "not-a-date", "--out", str(tmp_path)]
    )

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "--since 'not-a-date' is not a valid date; use YYYY-MM-DD."
    ]
    assert _snapshot(tmp_path) == before


def test_pull_since_date_rejects_compact_iso_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``date.fromisoformat`` alone accepts ``YYYYMMDD``; the leading
    ``fullmatch`` must reject it too, not just outright garbage text."""
    _patch_pull_transport(monkeypatch)

    result = runner.invoke(app, ["pull", "--since", "20260601", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "--since '20260601' is not a valid date; use YYYY-MM-DD."
    ]


def test_pull_invalid_settings_document_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    _write_settings(tmp_path, connectors="[connectors\n")
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert result.output.startswith(f"{tmp_path / 'fitdocs.toml'} is not valid TOML: ")
    assert _snapshot(tmp_path) == before


def test_pull_invalid_inbox_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    (tmp_path / "not-a-dir").write_text("")
    _write_settings(tmp_path, connectors='[inbox]\npath = "not-a-dir"\n')
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        f"{tmp_path / 'fitdocs.toml'}: [inbox] path exists but is not a "
        f"directory: {tmp_path / 'not-a-dir'}"
    ]
    assert _snapshot(tmp_path) == before


def test_pull_malformed_connectors_table_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.bogus]\nconnector = "does-not-exist"\n'
    )
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _snapshot(tmp_path) == before
    assert result.output.startswith(
        f"{tmp_path / 'fitdocs.toml'}: [connectors.bogus] connector: "
    )


def test_pull_unknown_names_are_listed_sorted_not_argv_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: sorting ``unknown`` with ``reverse=True`` reds this --
    two unknown names given in reverse-sorted order on argv still print in
    ascending order."""
    connector_registry.register(ScriptedPuller())
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )

    result = runner.invoke(app, ["pull", "zulu", "alpha", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "unknown connector instance(s): alpha, zulu; configured instances: src"
    ]


def test_pull_unknown_name_lists_every_configured_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.alpha]\nconnector = "scripted-puller"\n\n'
            '[connectors.beta]\nconnector = "scripted-puller"\n'
        ),
    )
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "zzz", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "unknown connector instance(s): zzz; configured instances: alpha, beta"
    ]
    assert _snapshot(tmp_path) == before


def test_pull_credentials_dir_inside_data_root_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    connector_registry.register(connector)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "personal-key"\n'
    )
    bad_dir = tmp_path / "creds"
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(bad_dir))
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        f"credentials directory {bad_dir.resolve()} is the data root "
        f"{tmp_path.resolve()} or lies inside it; credentials may never be "
        "stored under the data root"
    ]
    assert _snapshot(tmp_path) == before


def test_pull_skips_credentials_dir_check_when_no_selected_instance_authenticates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control for the ``any(... is not AuthStyle.NONE ...)`` gate:
    a misconfigured credentials directory (inside the data root) is never
    even consulted when every selected instance is ``AuthStyle.NONE``."""
    puller = ScriptedPuller()
    puller.listing_script.append(Listing(activities=()))
    connector_registry.register(puller)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(tmp_path / "creds"))

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output


# --- adjacent-pair preflight ordering (two violations; assert the winner) -


def test_preflight_order_data_root_before_sync_dry_run_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["pull", "--sync", "--dry-run", "--out", str(missing)])

    assert result.exit_code == 2
    assert result.output.startswith(f"The --out path does not exist: {missing}\n")


def test_preflight_order_sync_dry_run_conflict_before_since(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)

    result = runner.invoke(
        app,
        [
            "pull",
            "--sync",
            "--dry-run",
            "--since",
            "not-a-date",
            "--out",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "--sync cannot be combined with --dry-run: a dry run writes nothing."
    ]


def test_preflight_order_since_before_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    _write_settings(tmp_path, connectors="[connectors\n")

    result = runner.invoke(app, ["pull", "--since", "bad-date", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "--since 'bad-date' is not a valid date; use YYYY-MM-DD."
    ]


def test_preflight_order_inbox_before_connectors_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    (tmp_path / "not-a-dir").write_text("")
    _write_settings(
        tmp_path,
        connectors=(
            '[inbox]\npath = "not-a-dir"\n\n'
            '[connectors.bogus]\nconnector = "does-not-exist"\n'
        ),
    )

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        f"{tmp_path / 'fitdocs.toml'}: [inbox] path exists but is not a "
        f"directory: {tmp_path / 'not-a-dir'}"
    ]


def test_preflight_order_connectors_table_before_unknown_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.bogus]\nconnector = "does-not-exist"\n'
    )

    result = runner.invoke(app, ["pull", "zzz", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert "unknown connector instance" not in result.output
    assert "bogus" in result.output


def test_preflight_order_unknown_name_before_credentials_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    connector_registry.register(connector)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "personal-key"\n'
    )
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(tmp_path / "creds"))

    result = runner.invoke(app, ["pull", "zzz", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        "unknown connector instance(s): zzz; configured instances: src"
    ]


# The three pairs below only establish the *order* of the --sync preflight's
# checks against their immediate neighbor; they are not exact-line pinned
# the way the checks above them are, because 5.3 (not this task) owns the
# drain helper's own validation of these same inputs and will tighten these
# assertions once that chain exists. They do not reuse any tested helper
# sequence from elsewhere in this module -- each builds its own fixture.
def test_preflight_order_credentials_dir_before_sync_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    connector_registry.register(connector)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "personal-key"\n'
    )
    bad_dir = tmp_path / "creds"
    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(bad_dir))
    (tmp_path / "athlete.toml").write_text("not valid toml [[[")

    result = runner.invoke(app, ["pull", "--sync", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert _lines(result.output) == [
        f"credentials directory {bad_dir.resolve()} is the data root "
        f"{tmp_path.resolve()} or lies inside it; credentials may never be "
        "stored under the data root"
    ]


def test_preflight_order_sync_athlete_before_plugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.src]\nconnector = "scripted-puller"\n\n'
            '[plugins]\nenabled = "not-a-bool"\n'
        ),
    )
    (tmp_path / "athlete.toml").write_text("not valid toml [[[")

    result = runner.invoke(app, ["pull", "--sync", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert result.output.startswith(f"{tmp_path / 'athlete.toml'} is not valid TOML: ")


def test_preflight_order_sync_identity_before_hold_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.src]\nconnector = "scripted-puller"\n\n'
            "[identity]\nprecedence = 5\n"
        ),
    )
    fitdocs_dir = tmp_path / ".fitdocs"
    fitdocs_dir.mkdir()
    (fitdocs_dir / "held.toml").write_text("not valid toml [[[")

    result = runner.invoke(app, ["pull", "--sync", "--out", str(tmp_path)])

    assert result.exit_code == 2
    assert "precedence" in result.output
    assert "held.toml" not in result.output


# --- the no-connectors-configured path (Req 6.3) --------------------------


def test_pull_no_connectors_configured_reports_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert _lines(result.output) == [
        "No connectors are configured; nothing to pull.",
        f"Inbox: {tmp_path / 'inbox'}",
    ]
    assert (tmp_path / "inbox").is_dir()


def test_pull_dry_run_no_connectors_does_not_create_the_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: creating the inbox unconditionally (dropping the
    ``if dry_run`` branch) reds this -- the inbox directory would then
    exist."""
    _patch_pull_transport(monkeypatch)

    result = runner.invoke(app, ["pull", "--dry-run", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert _lines(result.output) == [
        "No connectors are configured; nothing to pull.",
        "Dry run — nothing fetched or written.",
    ]
    assert not (tmp_path / "inbox").exists()


# --- the report table and its detail blocks (Req 11.1, 11.2, 11.3, 11.5) -


def test_pull_report_table_has_every_channel_row_even_when_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: dropping a row from ``_PULL_REPORT_ROWS`` reds this."""
    puller = ScriptedPuller()
    puller.listing_script.append(Listing(activities=()))
    connector_registry.register(puller)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    collapsed = _collapsed(result.output)
    for label in (
        "Listed",
        "Delivered",
        "Would fetch",
        "Already held",
        "Skipped",
        "Deferred",
        "Failed",
        "Removed",
        "Error",
    ):
        assert f"{label} 0" in collapsed, (label, collapsed)


def test_pull_report_table_counts_each_channel_distinctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puller = ScriptedPuller()
    puller.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(remote_id="", original_available=True),
                RemoteActivity(remote_id="d1", original_available=True),
                RemoteActivity(remote_id="f1", original_available=True),
                RemoteActivity(
                    remote_id="u1",
                    original_available=False,
                    unavailable_reason="gone",
                ),
            )
        )
    )
    puller.fetch_script.extend([Declined("nope"), Deferred("wait")])
    connector_registry.register(puller)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    collapsed = _collapsed(result.output)
    assert "Listed 4" in collapsed
    assert "Skipped 2" in collapsed
    assert "Deferred 1" in collapsed
    assert "Failed 1" in collapsed
    assert "Delivered 0" in collapsed


def test_pull_delivers_through_the_folder_connector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    source = tmp_path / "phone-exports"
    source.mkdir()
    (source / "ride.fit").write_bytes(_fit_bytes(b"ride"))
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.folder-src]\nconnector = "folder"\n'
            f'path = "{source.as_posix()}"\nsettle_seconds = 0\n'
        ),
    )

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    collapsed = _collapsed(result.output)
    assert "Delivered 1" in collapsed
    delivered_dir = tmp_path / "inbox" / "folder-src"
    delivered_files = list(delivered_dir.glob("*.fit"))
    assert len(delivered_files) == 1
    assert delivered_files[0].read_bytes() == _fit_bytes(b"ride")
    assert (tmp_path / ".fitdocs" / "connectors" / "folder-src.toml").is_file()
    assert "Delivered:" in result.output
    assert "folder-src/ride.fit" in result.output.replace("\\", "/")


def test_pull_dry_run_lists_would_fetch_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_pull_transport(monkeypatch)
    source = tmp_path / "phone-exports"
    source.mkdir()
    (source / "ride.fit").write_bytes(_fit_bytes(b"ride"))
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.folder-src]\nconnector = "folder"\n'
            f'path = "{source.as_posix()}"\nsettle_seconds = 0\n'
        ),
    )
    before = _snapshot(tmp_path)

    result = runner.invoke(app, ["pull", "--dry-run", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    collapsed = _collapsed(result.output)
    assert "Would fetch 1" in collapsed
    assert "Delivered 0" in collapsed
    assert "Would fetch:" in result.output
    assert "ride.fit" in result.output
    assert _snapshot(tmp_path) == before


def test_pull_isolates_a_failing_instance_from_a_healthy_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: ``_finish(failed=False)`` reds the exit-code assertion."""
    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    connector_registry.register(connector)
    _patch_pull_transport(monkeypatch)
    source = tmp_path / "phone-exports"
    source.mkdir()
    (source / "ride.fit").write_bytes(_fit_bytes(b"ride"))
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.broken]\nconnector = "personal-key"\n\n'
            '[connectors.healthy]\nconnector = "folder"\n'
            f'path = "{source.as_posix()}"\nsettle_seconds = 0\n'
        ),
    )

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    collapsed = _collapsed(result.output)
    assert "fitdocs pull: broken (personal-key)" in collapsed
    assert "fitdocs pull: healthy (folder)" in collapsed
    assert "Error 1" in collapsed
    delivered_dir = tmp_path / "inbox" / "healthy"
    assert len(list(delivered_dir.glob("*.fit"))) == 1


def test_pull_deferral_only_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puller = ScriptedPuller()
    puller.listing_script.append(
        Listing(activities=(RemoteActivity(remote_id="f1", original_available=True),))
    )
    puller.fetch_script.append(Deferred("not ready yet"))
    connector_registry.register(puller)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    collapsed = _collapsed(result.output)
    assert "Deferred 1" in collapsed
    assert "Failed 0" in collapsed


# --- wiring: the run_pull seam, sorted instances, redacted exceptions ----


def test_run_pull_receives_the_seam_transport_real_clock_and_sorted_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 11.5: instances must reach ``run_pull`` name-sorted even when
    NAMES is given out of order on the command line -- a caller that simply
    forwards argv order would fail this."""
    connector_registry.register(ScriptedPuller())
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.zulu]\nconnector = "scripted-puller"\n\n'
            '[connectors.alpha]\nconnector = "scripted-puller"\n\n'
            '[connectors.mike]\nconnector = "scripted-puller"\n'
        ),
    )
    sentinel = object()
    monkeypatch.setattr(cli_module, "_connector_transport", lambda: sentinel)
    seen: dict[str, object] = {}

    class _Stop(Exception):
        pass

    def fake_run_pull(data_root: object, instances: object, **kwargs: object) -> object:
        seen["instances"] = instances
        seen.update(kwargs)
        raise _Stop("stop")

    monkeypatch.setattr(cli_module, "run_pull", fake_run_pull)

    result = runner.invoke(
        app, ["pull", "zulu", "alpha", "mike", "--out", str(tmp_path)]
    )

    assert result.exit_code == 1
    instances = cast(tuple[ConnectorInstance, ...], seen["instances"])
    assert [instance.name for instance in instances] == ["alpha", "mike", "zulu"]
    assert seen["transport"] is sentinel
    assert seen["sleep"] is time.sleep
    assert seen["environ"] is os.environ
    assert isinstance(seen["redactor"], Redactor)
    now = cast("Callable[[], object]", seen["now"])
    assert callable(now)
    assert now().tzinfo is UTC  # type: ignore[attr-defined]
    assert seen["store"] is None
    assert seen["inbox"] == tmp_path / "inbox"
    options = cast(PullOptions, seen["options"])
    assert isinstance(options, PullOptions)
    assert options.since is None
    assert options.dry_run is False


def test_unexpected_run_pull_exception_is_redacted_type_and_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine engine bug must never reach the terminal unredacted, the
    same convention ``connect_command`` already applies to its own call.
    Because this path builds a fresh ``Redactor()`` right before calling
    ``run_pull``, the ``Redactor`` seam is patched to pre-register the
    secret -- standing in for the registration ``run_pull`` would ordinarily
    have done for any secret it actually used."""
    connector_registry.register(ScriptedPuller())
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )
    secret_like = "unexpected-raise-pull-abc999"

    def _seeded_redactor() -> Redactor:
        redactor = Redactor()
        redactor.add(secret_like)
        return redactor

    monkeypatch.setattr(cli_module, "Redactor", _seeded_redactor)

    def fake_run_pull(*args: object, **kwargs: object) -> object:
        raise ValueError(f"could not parse {secret_like} while pulling")

    monkeypatch.setattr(cli_module, "run_pull", fake_run_pull)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert _lines(result.output) == [
        "ValueError: could not parse <redacted> while pulling"
    ]


# --- pull: report rows, the full report, instance selection, --since, the
# --- credentials store, the non-sync gate, and --help (task 5.2 remediation)


def test_pull_report_rows_are_the_design_literal_and_bind_every_channel() -> None:
    assert cli_module._PULL_REPORT_ROWS == (
        ("Listed", "listed"),
        ("Delivered", "delivered"),
        ("Would fetch", "would_fetch"),
        ("Already held", "held"),
        ("Skipped", "skipped"),
        ("Deferred", "deferred"),
        ("Failed", "failed"),
        ("Removed", "removed"),
        ("Error", "error"),
    )
    channels = [
        f.name
        for f in dataclasses.fields(InstancePullReport)
        if f.name not in {"name", "connector_id"}
    ]
    assert [field_name for _, field_name in cli_module._PULL_REPORT_ROWS] == channels


def _long(prefix: str) -> str:
    return prefix + "-" + "x" * 90


def _full_instance(name: str) -> InstancePullReport:
    return InstancePullReport(
        name=name,
        connector_id="folder",
        listed=11,
        delivered=(Delivered("r1", _long(f"{name}/delivered")),),
        would_fetch=(_long("wf0"), "wf1"),
        held=("h0", "h1", "h2"),
        skipped=tuple(PullNote(f"s{i}", _long(f"skip{i}")) for i in range(4)),
        deferred=tuple(PullNote(f"d{i}", f"defer {i}") for i in range(5)),
        failed=tuple(PullNote(f"f{i}", f"fail {i}") for i in range(6)),
        removed=tuple(f"{name}/removed{i}.fit" for i in range(6)) + (_long("rm"),),
        error=PullNote(name, _long("error detail")),
    )


def _empty_instance(name: str) -> InstancePullReport:
    return InstancePullReport(
        name=name,
        connector_id="folder",
        listed=0,
        delivered=(),
        would_fetch=(),
        held=(),
        skipped=(),
        deferred=(),
        failed=(),
        removed=(),
        error=None,
    )


def test_report_pull_prints_every_line_design_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )
    inbox = "/" + "inbox-dir/" * 10 + "inbox"
    report = PullReport(
        inbox=inbox,
        dry_run=False,
        instances=(_full_instance("alpha"), _empty_instance("zulu")),
    )
    monkeypatch.setattr(cli_module, "run_pull", lambda *a, **k: report)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    lines = _lines(result.output)
    assert len(inbox) > 80
    assert lines[0] == f"Inbox: {inbox}"
    collapsed = _collapsed(result.output)
    assert collapsed.index("fitdocs pull: alpha (folder)") < collapsed.index(
        "fitdocs pull: zulu (folder)"
    )
    assert (
        "Listed 11 Delivered 1 Would fetch 2 Already held 3 Skipped 4 "
        "Deferred 5 Failed 6 Removed 7 Error 1"
    ) in collapsed
    assert (
        "Listed 0 Delivered 0 Would fetch 0 Already held 0 Skipped 0 "
        "Deferred 0 Failed 0 Removed 0 Error 0"
    ) in collapsed
    start = lines.index("Delivered:")
    end = next(i for i, line in enumerate(lines) if "fitdocs pull: zulu" in line)
    expected = (
        ["Delivered:", f"  {_long('alpha/delivered')}"]
        + ["Would fetch:", f"  {_long('wf0')}", "  wf1"]
        + ["Skipped:"]
        + [x for i in range(4) for x in (f"  s{i}", f"    {_long(f'skip{i}')}")]
        + ["Deferred:"]
        + [x for i in range(5) for x in (f"  d{i}", f"    defer {i}")]
        + ["Failed:"]
        + [x for i in range(6) for x in (f"  f{i}", f"    fail {i}")]
        + ["Removed:"]
        + [f"  alpha/removed{i}.fit" for i in range(6)]
        + [f"  {_long('rm')}"]
        + ["Error:", f"  {_long('error detail')}"]
    )
    assert lines[start:end] == expected
    assert lines[-1].strip() != "Delivered:"  # the empty instance prints no block


def test_pull_names_select_exactly_the_named_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(ScriptedPuller())
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.zulu]\nconnector = "scripted-puller"\n\n'
            '[connectors.alpha]\nconnector = "scripted-puller"\n\n'
            '[connectors.mike]\nconnector = "scripted-puller"\n'
        ),
    )
    seen: dict[str, object] = {}

    def fake_run_pull(data_root: object, instances: object, **kwargs: object) -> object:
        seen["instances"] = instances
        return PullReport(inbox="i", dry_run=False, instances=())

    monkeypatch.setattr(cli_module, "run_pull", fake_run_pull)

    result = runner.invoke(app, ["pull", "zulu", "alpha", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    instances = cast(tuple[ConnectorInstance, ...], seen["instances"])
    assert [instance.name for instance in instances] == ["alpha", "zulu"]


@pytest.fixture
def _new_york_tz(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize(
    ("since", "expected_utc_hour"), [("2026-01-15", 5), ("2026-07-15", 4)]
)
def test_pull_since_is_that_days_local_midnight_in_utc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _new_york_tz: None,
    since: str,
    expected_utc_hour: int,
) -> None:
    connector_registry.register(ScriptedPuller())
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "scripted-puller"\n'
    )
    seen: dict[str, object] = {}

    def fake_run_pull(data_root: object, instances: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return PullReport(inbox="i", dry_run=False, instances=())

    monkeypatch.setattr(cli_module, "run_pull", fake_run_pull)

    result = runner.invoke(app, ["pull", "--since", since, "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    options = cast(PullOptions, seen["options"])
    year, month, day = (int(part) for part in since.split("-"))
    assert options.since == datetime(year, month, day, expected_utc_hour, tzinfo=UTC)
    assert options.since is not None and options.since.tzinfo is UTC


def test_pull_passes_a_store_on_the_resolved_credentials_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector_registry.register(
        ScriptedPersonalKeyConnector(
            capabilities=frozenset({Capability.PULL_ACTIVITIES})
        )
    )
    _write_settings(
        tmp_path, connectors='[connectors.src]\nconnector = "personal-key"\n'
    )
    seen: dict[str, object] = {}

    def fake_run_pull(data_root: object, instances: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return PullReport(inbox="i", dry_run=False, instances=())

    monkeypatch.setattr(cli_module, "run_pull", fake_run_pull)

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    store = seen["store"]
    assert isinstance(store, CredentialStore)
    assert store.directory == _credentials_dir()


def test_pull_without_sync_reads_none_of_the_sync_only_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puller = ScriptedPuller()
    puller.listing_script.append(Listing(activities=()))
    connector_registry.register(puller)
    _patch_pull_transport(monkeypatch)
    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.src]\nconnector = "scripted-puller"\n\n'
            '[plugins]\nenabled = "not-a-bool"\n'
        ),
    )
    (tmp_path / "athlete.toml").write_text("not valid toml [[[")

    result = runner.invoke(app, ["pull", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output


def test_pull_dry_run_resolves_the_configured_inbox_not_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named mutation: hard-coding ``data_root / 'inbox'`` under ``--dry-run``
    instead of using ``validated_inbox.inbox_resolved`` reds this -- the
    configured inbox here is a different directory from the default."""
    connector_registry.register(ScriptedPuller())
    custom_inbox = tmp_path / "custom-inbox-dir"
    _write_settings(
        tmp_path,
        connectors=(
            f'[inbox]\npath = "{custom_inbox.name}"\n\n'
            '[connectors.src]\nconnector = "scripted-puller"\n'
        ),
    )
    seen: dict[str, object] = {}

    def fake_run_pull(data_root: object, instances: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return PullReport(inbox="i", dry_run=True, instances=())

    monkeypatch.setattr(cli_module, "run_pull", fake_run_pull)

    result = runner.invoke(app, ["pull", "--dry-run", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert seen["inbox"] == custom_inbox
    assert seen["inbox"] != tmp_path / "inbox"
    assert not custom_inbox.exists()


def test_pull_help_renders_no_swallowed_markup() -> None:
    result = runner.invoke(app, ["pull", "--help"])
    assert result.exit_code == 0
    assert "``" + "``" not in result.output
    assert " the  table" not in _collapsed(result.output)
    assert (
        "List and report what each instance would fetch; fetch, deliver, "
        "remove, and record nothing -- except a token renewal the listing "
        "needs, which is still saved to the credentials store."
    ) in _collapsed(result.output)
