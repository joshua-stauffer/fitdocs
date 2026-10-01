"""CLI end-to-end tests: ``fitdocs connect`` (task 5.1).

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

Requirements 1.7, 3.9, 4.2, 5.1, 5.2, 5.3, 5.4, 5.9, 10.6.
"""

from __future__ import annotations

import getpass
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace

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
    Granted,
    SettingsContext,
    TokenSet,
)
from fitdocs.connectors.secrets import Redactor
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
