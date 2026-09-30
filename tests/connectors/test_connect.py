"""Pins for the connect engine: one auth attempt, store only on success
(design.md "ConnectEngine", Req 4.6, 4.8, 5.5, 5.6, 5.7, 5.8, 10.2).

``ScriptedPersonalKeyConnector``/``ScriptedLoginConnector`` (``conftest.py``,
closed to new fixtures after task 2.3) answer ``verify``/``login`` from a
queued script and never touch ``session.http`` themselves. To pin "exactly
one request per attempt" this module defines local subclasses whose
``verify``/``login`` issue a real request through ``session.http`` -- exactly
the "local subclass in your test module" the task brief calls for -- and
translate the response with ``auth_failure_from``, echoing every submitted
value (not only the one sent as a header) back in a synthetic service
message, so the redaction pin has something to catch for every answer field,
not only the ones a connector happens to put in a header.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fitdocs.connectors.connect import (
    Connected,
    ConnectFailed,
    run_connect,
)
from fitdocs.connectors.credentials import CredentialStore, env_var_name
from fitdocs.connectors.errors import AuthFailureKind, next_step
from fitdocs.connectors.http import HttpResponse, TransportError, auth_failure_from
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    Connector,
    ConnectorSession,
    CredentialField,
    Granted,
    TokenSet,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
)

_NOW = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # noqa: E731
_NO_SLEEP = lambda seconds: None  # noqa: E731


def _message_from(values: Mapping[str, Secret], *, label: str) -> str:
    """Echo every submitted value back, sorted by field name, so a fixture
    that never contains a given answer cannot pin that it is redacted."""
    parts = ", ".join(
        f"{name}={secret.reveal()}" for name, secret in sorted(values.items())
    )
    return f"{label} refused ({parts})"


class _HttpPersonalKeyConnector(ScriptedPersonalKeyConnector):
    """A personal-key connector whose ``verify`` sends one real request."""

    def __init__(
        self, *, credential_fields: tuple[CredentialField, ...] | None = None
    ) -> None:
        super().__init__()
        if credential_fields is not None:
            # ScriptedPersonalKeyConnector's own ``credential_fields`` is
            # inferred as the narrower fixed-length tuple of its one default
            # field; this test connector widens it to test a multi-field env
            # override, which mypy sees as variance it cannot verify.
            fields: tuple[CredentialField, ...] = credential_fields
            self.credential_fields = fields  # type: ignore[assignment]

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        self.verify_calls.append(values)
        response = session.http.post(
            "https://svc.example/verify",
            body=b"{}",
            secret_headers={"Authorization": values["api_key"]},
        )
        message = _message_from(values, label="request")
        failure = auth_failure_from(response, service_message=message)
        if failure is not None:
            raise failure
        scopes_header = response.headers.get("x-scopes")
        scopes = tuple(scopes_header.split(",")) if scopes_header else None
        return Granted(scopes=scopes)


class _HttpLoginConnector(ScriptedLoginConnector):
    """A login-style connector whose ``login`` sends one real request and,
    on acceptance, is issued a tz-aware expiry and (unless ``scopes=None``
    is given) non-empty scopes, so the stored file's ``expires_at``/``scopes``
    fields are pinnable against literals as well as against absence."""

    def __init__(self, *, scopes: tuple[str, ...] | None = ("activity:read",)) -> None:
        super().__init__()
        self._issued_scopes = scopes

    def login(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> TokenSet:
        self.login_calls.append(values)
        response = session.http.post(
            "https://svc.example/login",
            body=b"{}",
            secret_headers={"Authorization": values["password"]},
        )
        message = _message_from(values, label="login")
        failure = auth_failure_from(response, service_message=message)
        if failure is not None:
            raise failure
        return TokenSet(
            values={"access_token": session.secret("issued-token-xyz")},
            expires_at=datetime(2026, 3, 1, tzinfo=UTC),
            scopes=self._issued_scopes,
        )


@dataclass(frozen=True)
class _OAuthBrowserConnector:
    """A minimal connector declaring the reserved ``OAUTH_BROWSER`` style.

    No synthetic connector in ``conftest.py`` declares this style; this
    class exists only to prove ``run_connect`` refuses to dispatch to it
    rather than silently doing nothing, matching the CLI's own refusal
    (Req 5.3) that is expected to run before ``run_connect`` is ever called
    for an instance like this.
    """

    connector_id: str = "oauth-conn"
    display_name: str = "OAuth Conn"
    auth_style: AuthStyle = AuthStyle.OAUTH_BROWSER
    credential_fields: tuple[CredentialField, ...] = ()
    capabilities: frozenset[Capability] = field(default_factory=frozenset)

    def parse_settings(self, table: Mapping[str, object], context: object) -> object:
        return None


def _instance(*, name: str, connector: Connector) -> ConnectorInstance:
    return ConnectorInstance(
        name=name, connector=connector, lookback_days=30, settings=None
    )


def _run(
    instance: ConnectorInstance,
    answers: Mapping[str, str],
    *,
    store: CredentialStore,
    transport: FakeTransport,
    environ: Mapping[str, str] | None = None,
    redactor: Redactor | None = None,
) -> Connected | ConnectFailed:
    return run_connect(
        instance,
        answers,
        store=store,
        transport=transport,
        environ=environ or {},
        now=_NOW,
        sleep=_NO_SLEEP,
        redactor=redactor if redactor is not None else Redactor(),
    )


# ---------------------------------------------------------------------------
# Success: personal-key verify then store
# ---------------------------------------------------------------------------


def test_personal_key_verify_success_stores_answers_and_scopes(tmp_path: Path) -> None:
    transport = FakeTransport(
        [HttpResponse(status=200, headers={"x-scopes": "read,write"}, body=b"{}")]
    )
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc1", connector=connector)

    result = _run(
        instance, {"api_key": "leaked-key-1"}, store=store, transport=transport
    )

    assert isinstance(result, Connected)
    assert result.instance == "svc1"
    assert result.scopes == ("read", "write")
    assert result.env_override == ()
    assert len(transport.requests) == 1
    assert result.path == tmp_path / "creds" / "svc1.toml"

    document = tomllib.loads(result.path.read_text())
    assert document["connector"] == "personal-key"
    assert document["auth_style"] == "api-key"
    assert document["values"] == {"api_key": "leaked-key-1"}
    assert document["scopes"] == ["read", "write"]
    assert "expires_at" not in document
    assert set(document.keys()) == {
        "credentials_version",
        "connector",
        "auth_style",
        "scopes",
        "values",
    }


def test_personal_key_success_with_no_scopes_is_recorded_as_absent(
    tmp_path: Path,
) -> None:
    """Req 4.8: unreported scopes are absent, never an empty grant."""

    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc-noscopes", connector=connector)

    result = _run(
        instance, {"api_key": "leaked-key-8"}, store=store, transport=transport
    )

    assert isinstance(result, Connected)
    assert result.scopes is None

    document = tomllib.loads(result.path.read_text())
    assert "scopes" not in document


def test_login_success_stores_tokens_and_not_the_password(tmp_path: Path) -> None:
    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpLoginConnector()
    instance = _instance(name="login1", connector=connector)

    result = _run(
        instance,
        {"username": "alice", "password": "hunter2-secret"},
        store=store,
        transport=transport,
    )

    assert isinstance(result, Connected)
    assert result.instance == "login1"
    assert result.scopes == ("activity:read",)
    assert len(transport.requests) == 1
    assert result.path == tmp_path / "creds" / "login1.toml"

    raw_bytes = result.path.read_bytes()
    assert b"hunter2-secret" not in raw_bytes

    document = tomllib.loads(raw_bytes.decode("utf-8"))
    assert document["connector"] == "login-style"
    assert document["auth_style"] == "login"
    assert document["values"] == {"access_token": "issued-token-xyz"}
    assert document["expires_at"] == datetime(2026, 3, 1, tzinfo=UTC)
    assert document["scopes"] == ["activity:read"]


def test_login_success_with_no_scopes_is_recorded_as_absent(tmp_path: Path) -> None:
    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")
    instance = _instance(
        name="login-noscopes", connector=_HttpLoginConnector(scopes=None)
    )

    result = _run(
        instance,
        {"username": "alice", "password": "hunter2-secret"},
        store=store,
        transport=transport,
    )

    assert isinstance(result, Connected)
    assert result.scopes is None
    document = tomllib.loads(result.path.read_text())
    assert "scopes" not in document


def test_personal_key_stores_every_answer_not_only_the_secret_ones(
    tmp_path: Path,
) -> None:
    fields = (
        CredentialField("api_key", "API Key", secret=True),
        CredentialField("org_id", "Org ID", secret=False),
    )
    connector = _HttpPersonalKeyConnector(credential_fields=fields)
    instance = _instance(name="svc-two", connector=connector)
    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")

    result = _run(
        instance,
        {"api_key": "two-field-key", "org_id": "org-77"},
        store=store,
        transport=transport,
    )

    assert isinstance(result, Connected)
    document = tomllib.loads(result.path.read_text())
    assert document["values"] == {"api_key": "two-field-key", "org_id": "org-77"}


# ---------------------------------------------------------------------------
# Failure kinds: exactly one request, nothing stored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected_kind",
    [
        (429, AuthFailureKind.RATE_LIMITED),
        (401, AuthFailureKind.REJECTED),
        (403, AuthFailureKind.BLOCKED),
        (503, AuthFailureKind.UNAVAILABLE),
    ],
)
def test_each_scripted_failure_makes_one_request_and_stores_nothing(
    tmp_path: Path, status: int, expected_kind: AuthFailureKind
) -> None:
    transport = FakeTransport([HttpResponse(status=status, headers={}, body=b"{}")])
    credentials_dir = tmp_path / "creds"
    store = CredentialStore(credentials_dir)
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc-fail", connector=connector)

    result = _run(
        instance, {"api_key": "leaked-key-2"}, store=store, transport=transport
    )

    assert isinstance(result, ConnectFailed)
    assert result.instance == "svc-fail"
    assert result.kind == expected_kind
    assert result.message == "request refused (api_key=<redacted>)"
    assert result.next_step == next_step(
        expected_kind, name="svc-fail", retry_after_s=None
    )
    assert len(transport.requests) == 1
    assert not credentials_dir.exists()


def test_non_header_answer_is_also_redacted_from_a_personal_key_failure(
    tmp_path: Path,
) -> None:
    """``org_id`` is never sent as a header (only ``api_key`` is); this pins
    that every answer is registered with the redactor, not only the ones a
    connector happens to put in a header."""

    fields = (
        CredentialField("api_key", "API Key", secret=True),
        CredentialField("org_id", "Org ID", secret=False),
    )
    connector = _HttpPersonalKeyConnector(credential_fields=fields)
    instance = _instance(name="svc-org", connector=connector)
    transport = FakeTransport([HttpResponse(status=401, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")

    result = _run(
        instance,
        {"api_key": "leaked-key-5", "org_id": "org-secret-77"},
        store=store,
        transport=transport,
    )

    assert isinstance(result, ConnectFailed)
    assert "org-secret-77" not in result.message
    assert "leaked-key-5" not in result.message
    assert REDACTED in result.message


def test_login_failure_redacts_the_username_and_not_only_the_password(
    tmp_path: Path,
) -> None:
    """``username`` is never sent as a header (only ``password`` is)."""

    transport = FakeTransport([HttpResponse(status=401, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpLoginConnector()
    instance = _instance(name="login-fail", connector=connector)

    result = _run(
        instance,
        {"username": "alice-secret-name", "password": "hunter2-secret-2"},
        store=store,
        transport=transport,
    )

    assert isinstance(result, ConnectFailed)
    assert result.kind == AuthFailureKind.REJECTED
    assert "alice-secret-name" not in result.message
    assert "hunter2-secret-2" not in result.message
    assert REDACTED in result.message


def test_429_with_retry_after_names_the_wait(tmp_path: Path) -> None:
    transport = FakeTransport(
        [HttpResponse(status=429, headers={"retry-after": "120"}, body=b"{}")]
    )
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc-429", connector=connector)

    result = _run(
        instance, {"api_key": "leaked-key-6"}, store=store, transport=transport
    )

    assert isinstance(result, ConnectFailed)
    assert result.kind == AuthFailureKind.RATE_LIMITED
    assert result.next_step == next_step(
        AuthFailureKind.RATE_LIMITED, name="svc-429", retry_after_s=120.0
    )
    assert " at least 120 seconds" in result.next_step


def test_network_error_redacts_the_key_but_keeps_the_target(tmp_path: Path) -> None:
    transport = FakeTransport(
        [
            TransportError(
                "network failure (OSError): https://svc.example/verify leaked-key-3"
            )
        ]
    )
    credentials_dir = tmp_path / "creds"
    store = CredentialStore(credentials_dir)
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc-net", connector=connector)

    result = _run(
        instance, {"api_key": "leaked-key-3"}, store=store, transport=transport
    )

    assert isinstance(result, ConnectFailed)
    assert result.instance == "svc-net"
    assert result.kind == AuthFailureKind.UNAVAILABLE
    assert "leaked-key-3" not in result.message
    assert "svc.example" in result.message
    assert "/verify" in result.message
    assert result.next_step == next_step(
        AuthFailureKind.UNAVAILABLE, name="svc-net", retry_after_s=None
    )
    assert len(transport.requests) == 1
    assert not credentials_dir.exists()


def test_503_makes_exactly_one_request_never_retried(tmp_path: Path) -> None:
    """Distinct from the parametrized failure test above: this asserts the
    request *count* specifically for the status DATA-mode would retry, so a
    session accidentally built in ``CallMode.DATA`` (which retries 503 up to
    three times) is caught here even if a future change relaxed the
    parametrized test's request-count assertion.
    """

    transport = FakeTransport(
        [
            HttpResponse(status=503, headers={}, body=b"{}"),
            HttpResponse(status=503, headers={}, body=b"{}"),
            HttpResponse(status=503, headers={}, body=b"{}"),
        ]
    )
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc-503", connector=connector)

    result = _run(
        instance, {"api_key": "leaked-key-4"}, store=store, transport=transport
    )

    assert isinstance(result, ConnectFailed)
    assert len(transport.requests) == 1


# ---------------------------------------------------------------------------
# Replace on reconnect
# ---------------------------------------------------------------------------


def test_second_connect_replaces_the_first_file(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds")
    connector = _HttpPersonalKeyConnector()
    instance = _instance(name="svc-replace", connector=connector)

    first_transport = FakeTransport(
        [HttpResponse(status=200, headers={"x-scopes": "read"}, body=b"{}")]
    )
    first = _run(
        instance, {"api_key": "first-key"}, store=store, transport=first_transport
    )
    assert isinstance(first, Connected)

    second_transport = FakeTransport(
        [HttpResponse(status=200, headers={"x-scopes": "read,write"}, body=b"{}")]
    )
    second = _run(
        instance, {"api_key": "second-key"}, store=store, transport=second_transport
    )
    assert isinstance(second, Connected)
    assert second.path == first.path

    document = tomllib.loads(second.path.read_text())
    assert document["values"] == {"api_key": "second-key"}
    assert document["scopes"] == ["read", "write"]

    files = list((tmp_path / "creds").glob("*.toml"))
    assert len(files) == 1


# ---------------------------------------------------------------------------
# Overriding environment variables are reported by name
# ---------------------------------------------------------------------------


def test_overriding_env_variables_are_reported_in_declared_order(
    tmp_path: Path,
) -> None:
    fields = (
        CredentialField("api_key", "API Key", secret=True),
        CredentialField("org_id", "Org ID", secret=False),
    )
    connector = _HttpPersonalKeyConnector(credential_fields=fields)
    instance = _instance(name="svc-env", connector=connector)
    api_key_var = env_var_name("svc-env", "api_key")
    org_id_var = env_var_name("svc-env", "org_id")
    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")

    result = _run(
        instance,
        {"api_key": "some-key", "org_id": "42"},
        store=store,
        transport=transport,
        environ={api_key_var: "override-1", org_id_var: "override-2"},
    )

    assert isinstance(result, Connected)
    assert result.env_override == (api_key_var, org_id_var)


def test_empty_env_variable_is_not_reported_as_an_override(tmp_path: Path) -> None:
    fields = (
        CredentialField("api_key", "API Key", secret=True),
        CredentialField("org_id", "Org ID", secret=False),
    )
    connector = _HttpPersonalKeyConnector(credential_fields=fields)
    instance = _instance(name="svc-env2", connector=connector)
    api_key_var = env_var_name("svc-env2", "api_key")
    org_id_var = env_var_name("svc-env2", "org_id")
    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")

    result = _run(
        instance,
        {"api_key": "some-key", "org_id": "42"},
        store=store,
        transport=transport,
        environ={api_key_var: "override-1", org_id_var: ""},
    )

    assert isinstance(result, Connected)
    assert result.env_override == (api_key_var,)


def test_login_style_never_reports_an_env_override(tmp_path: Path) -> None:
    connector = _HttpLoginConnector()
    instance = _instance(name="login-env", connector=connector)
    transport = FakeTransport([HttpResponse(status=200, headers={}, body=b"{}")])
    store = CredentialStore(tmp_path / "creds")
    var_name = env_var_name("login-env", "password")

    result = _run(
        instance,
        {"username": "bob", "password": "pw-1"},
        store=store,
        transport=transport,
        environ={var_name: "set-but-irrelevant-for-login"},
    )

    assert isinstance(result, Connected)
    assert result.env_override == ()


# ---------------------------------------------------------------------------
# Auth styles run_connect does not dispatch to (the CLI, task 5.1, must
# refuse these before ever calling run_connect -- Req 5.2, 5.3)
# ---------------------------------------------------------------------------


def test_none_auth_style_raises_before_any_request(tmp_path: Path) -> None:
    transport = FakeTransport([])
    credentials_dir = tmp_path / "creds"
    store = CredentialStore(credentials_dir)
    connector = ScriptedPuller()
    instance = _instance(name="svc-none", connector=connector)

    with pytest.raises(AssertionError):
        _run(instance, {}, store=store, transport=transport)

    assert len(transport.requests) == 0
    assert not credentials_dir.exists()


def test_oauth_browser_auth_style_raises_before_any_request(tmp_path: Path) -> None:
    transport = FakeTransport([])
    credentials_dir = tmp_path / "creds"
    store = CredentialStore(credentials_dir)
    connector = _OAuthBrowserConnector()
    instance = _instance(name="svc-oauth", connector=connector)

    with pytest.raises(AssertionError):
        _run(instance, {}, store=store, transport=transport)

    assert len(transport.requests) == 0
    assert not credentials_dir.exists()
