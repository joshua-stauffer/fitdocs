"""Connecting a relay instance with a pasted token (relay-server task 6.3;
Requirements 12.2, 12.3, 12.4, 12.6, 15.2, 15.4).

Every request goes through a scripted ``FakeTransport``. The relay is the real
``RelayConnector``; the credentials store is a real ``CredentialStore`` in a
temporary directory.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fitdocs.connectors import relay_connect as relay_connect_module
from fitdocs.connectors.credentials import CredentialStore, env_var_name
from fitdocs.connectors.http import HttpResponse, TransportError
from fitdocs.connectors.protocol import AuthStyle
from fitdocs.connectors.relay import RelayConnector, RelaySettings
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode, explain
from fitdocs.connectors.relay_connect import (
    TOKEN_FORMAT_MESSAGE,
    RelayConnected,
    RelayConnectFailed,
    RelayTokenFormatError,
    relay_next_step,
    run_relay_connect,
)
from fitdocs.connectors.relay_envelope import Answer, encode_answer
from fitdocs.connectors.secrets import REDACTED, Redactor
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import FakeTransport

_CLOCK = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_BASE = "https://relay.example.com"
_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52
_OLD_TOKEN = "fdr1_" + "b" * 16 + "_" + "b" * 52
_PLANT = "PLANTED-BY-THE-RELAY-7f3a"

# Relay answers that mean success for some other route: on the token check
# they are an answer the route has no reading of.
_OTHER_ROUTE_CODES = frozenset(
    {
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
    }
)


def _instance(name: str = "relay") -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=RelayConnector(),
        lookback_days=30,
        settings=RelaySettings(url=_BASE),
    )


def _store(tmp_path: Path) -> CredentialStore:
    return CredentialStore(tmp_path / "credentials")


def _envelope(
    code: RelayCode,
    data: Mapping[str, object] | None = None,
    *,
    outcome: str | None = None,
) -> HttpResponse:
    info = RELAY_CODES[code]
    assert info.origin is CodeOrigin.RELAY
    assert info.http_status is not None
    return HttpResponse(
        status=info.http_status,
        headers={},
        body=encode_answer(Answer(code=code, data=data or {}, outcome=outcome)),
    )


def _connect(
    tmp_path: Path,
    script: list[HttpResponse | TransportError],
    *,
    token_text: str = _TOKEN,
    redactor: Redactor | None = None,
    environ: Mapping[str, str] | None = None,
    name: str = "relay",
) -> tuple[RelayConnected | RelayConnectFailed, FakeTransport]:
    transport = FakeTransport(script)
    result = run_relay_connect(
        _instance(name),
        token_text,
        store=_store(tmp_path),
        transport=transport,
        environ=environ or {},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor if redactor is not None else Redactor(),
    )
    return result, transport


def _stored_files(tmp_path: Path) -> list[str]:
    directory = tmp_path / "credentials"
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


def _scripted_for(code: RelayCode) -> list[HttpResponse | TransportError]:
    """What the relay (or the network) does to produce ``code``, with a
    planted string in every field of the answer that could carry one."""
    info = RELAY_CODES[code]
    if code is RelayCode.RATE_LIMITED:
        # Its data must be exactly the stated wait, or the answer is malformed
        # (and then this case would pin the malformed code, not this one).
        return [_envelope(code, {"retry_after_s": 5}, outcome=_PLANT)]
    if info.origin is CodeOrigin.RELAY:
        return [_envelope(code, {"note": _PLANT}, outcome=_PLANT)]
    if code is RelayCode.RELAY_UNREACHABLE:
        return [TransportError("connection refused")]
    assert code is RelayCode.ANSWER_MALFORMED
    return [HttpResponse(status=200, headers={}, body=_PLANT.encode())]


def _expected_code(code: RelayCode) -> RelayCode:
    return RelayCode.ANSWER_MALFORMED if code in _OTHER_ROUTE_CODES else code


_FAILURE_CODES = [code for code in RELAY_CODES if code is not RelayCode.OK]


# --------------------------------------------------------------------------
# Req 12.2: a value outside the token format never reaches the network
# --------------------------------------------------------------------------

_BAD_TOKENS = [
    "",
    "not-a-token",
    _TOKEN + "\n",
    " " + _TOKEN,
    _TOKEN[:-1],
    _TOKEN + "a",
    _TOKEN.upper(),
    "fdr2_" + "a" * 16 + "_" + "a" * 52,
    "fdr1_" + "1" * 16 + "_" + "a" * 52,
]


@pytest.mark.parametrize("bad", _BAD_TOKENS)
def test_a_value_outside_the_token_format_is_refused_before_any_request(
    tmp_path: Path, bad: str
) -> None:
    redactor = Redactor()
    transport = FakeTransport([])
    with pytest.raises(RelayTokenFormatError) as raised:
        run_relay_connect(
            _instance(),
            bad,
            store=_store(tmp_path),
            transport=transport,
            environ={},
            now=lambda: _CLOCK,
            sleep=lambda seconds: None,
            redactor=redactor,
        )
    assert transport.requests == []
    assert _stored_files(tmp_path) == []
    assert str(raised.value) == TOKEN_FORMAT_MESSAGE
    assert TOKEN_FORMAT_MESSAGE == (
        "That is not a relay token: a relay token looks like "
        "fdr1_<16 characters>_<52 characters>."
    )


def test_a_refused_value_is_registered_for_redaction() -> None:
    odd = "hunter2-pasted-by-mistake"
    redactor = Redactor()
    assert redactor.redact(odd) == odd  # not registered beforehand
    with pytest.raises(RelayTokenFormatError):
        run_relay_connect(
            _instance(),
            odd,
            store=CredentialStore(Path("/nonexistent-credentials")),
            transport=FakeTransport([]),
            environ={},
            now=lambda: _CLOCK,
            sleep=lambda seconds: None,
            redactor=redactor,
        )
    assert redactor.redact(odd) == REDACTED


def test_the_format_check_is_the_envelope_modules_not_a_second_pattern() -> None:
    tree = ast.parse(inspect.getsource(relay_connect_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "fitdocs.connectors.relay_envelope"
        for alias in node.names
    }
    assert imported == {
        "MAX_POLL_INTERVAL_S",
        "SLOW_DOWN_STEP_S",
        "is_email",
        "split_relay_token",
    }
    scanned = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert scanned, "the walk saw no calls"
    for call in scanned:
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        assert name not in {"compile", "match", "fullmatch", "search"}
    assert "import re" not in inspect.getsource(relay_connect_module)


# --------------------------------------------------------------------------
# Req 12.3: one check, then store
# --------------------------------------------------------------------------


def test_an_ok_answer_stores_the_token_and_reports_where(tmp_path: Path) -> None:
    result, transport = _connect(tmp_path, [_envelope(RelayCode.OK)])
    assert isinstance(result, RelayConnected)
    assert result.instance == "relay"
    assert result.path == tmp_path / "credentials" / "relay.toml"
    assert result.env_override == ()
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert (request.method, request.url) == ("GET", _BASE + "/v1/token")
    assert request.body is None
    assert _TOKEN not in request.url
    assert {k: v.reveal() for k, v in request.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }
    stored = _store(tmp_path).load("relay")
    assert stored is not None
    assert stored.connector_id == "relay"
    assert stored.auth_style is AuthStyle.RELAY_TOKEN
    assert {k: v.reveal() for k, v in stored.values.items()} == {"token": _TOKEN}
    assert stored.expires_at is None
    assert stored.scopes is None


def test_the_env_override_names_the_variable_that_is_set(tmp_path: Path) -> None:
    variable = env_var_name("relay", "token")
    unset, _ = _connect(tmp_path / "a", [_envelope(RelayCode.OK)], environ={})
    empty, _ = _connect(
        tmp_path / "b", [_envelope(RelayCode.OK)], environ={variable: ""}
    )
    set_, _ = _connect(
        tmp_path / "c", [_envelope(RelayCode.OK)], environ={variable: "x"}
    )
    assert isinstance(unset, RelayConnected) and unset.env_override == ()
    assert isinstance(empty, RelayConnected) and empty.env_override == ()
    assert isinstance(set_, RelayConnected)
    assert set_.env_override == (variable,)
    assert variable == "FITDOCS_CONNECTOR_RELAY_TOKEN"


@pytest.mark.parametrize(
    "response",
    [
        _envelope(RelayCode.UNAVAILABLE),
        HttpResponse(status=503, headers={}, body=b"<html>down</html>"),
        HttpResponse(status=429, headers={"retry-after": "1"}, body=b""),
        _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 1}),
    ],
    ids=["503-envelope", "503-plain", "429-plain", "429-envelope"],
)
def test_a_503_and_a_429_each_produce_exactly_one_transport_call(
    tmp_path: Path, response: HttpResponse
) -> None:
    # A second and third scripted answer that would succeed if the client
    # retried: the sequence must stop after the first.
    result, transport = _connect(
        tmp_path, [response, _envelope(RelayCode.OK), _envelope(RelayCode.OK)]
    )
    assert len(transport.requests) == 1
    assert isinstance(result, RelayConnectFailed)
    assert _stored_files(tmp_path) == []


def test_the_429_wait_the_relay_stated_reaches_the_result(tmp_path: Path) -> None:
    result, _ = _connect(
        tmp_path, [_envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 37})]
    )
    assert isinstance(result, RelayConnectFailed)
    assert result.retry_after_s == 37
    assert result.next_step == "Wait 37 seconds, then try again."


def test_the_token_is_registered_for_redaction_before_the_request_is_sent(
    tmp_path: Path,
) -> None:
    redactor = Redactor()
    seen: list[str] = []

    def transport(request: object, timeout: float) -> HttpResponse:
        seen.append(redactor.redact(_TOKEN))
        return _envelope(RelayCode.OK)

    run_relay_connect(
        _instance(),
        _TOKEN,
        store=_store(tmp_path),
        transport=transport,
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
    )
    assert seen == [REDACTED]


# --------------------------------------------------------------------------
# Req 12.4: every other answer stores nothing and speaks fitdocs text only
# --------------------------------------------------------------------------


def test_the_failure_collection_covers_every_non_ok_code() -> None:
    assert set(_FAILURE_CODES) | {RelayCode.OK} == set(RelayCode)
    assert len(_FAILURE_CODES) == len(RELAY_CODES) - 1 >= 21
    origins = {RELAY_CODES[code].origin for code in _FAILURE_CODES}
    assert origins == {CodeOrigin.RELAY, CodeOrigin.CLIENT}


@pytest.mark.parametrize("code", _FAILURE_CODES, ids=lambda c: c.value)
def test_every_non_ok_code_stores_nothing_and_speaks_only_fitdocs_text(
    tmp_path: Path, code: RelayCode
) -> None:
    script = _scripted_for(code)
    first = script[0]
    if isinstance(first, HttpResponse):
        assert _PLANT.encode() in first.body  # the planted string is on the wire
    result, transport = _connect(tmp_path, script)
    assert len(transport.requests) == 1
    assert isinstance(result, RelayConnectFailed)
    expected = _expected_code(code)
    assert result.instance == "relay"
    assert result.code is expected
    assert result.explanation == explain(expected)
    assert result.next_step == relay_next_step(
        expected, name="relay", retry_after_s=result.retry_after_s
    )
    assert _PLANT not in repr(result)
    assert _stored_files(tmp_path) == []


def test_an_ok_answer_carrying_data_is_malformed_and_stores_nothing(
    tmp_path: Path,
) -> None:
    result, _ = _connect(tmp_path, [_envelope(RelayCode.OK, {"note": _PLANT})])
    assert isinstance(result, RelayConnectFailed)
    assert result.code is RelayCode.ANSWER_MALFORMED
    assert _PLANT not in repr(result)
    assert _stored_files(tmp_path) == []


@pytest.mark.parametrize("code", _FAILURE_CODES, ids=lambda c: c.value)
def test_any_failed_check_leaves_an_existing_token_untouched(
    tmp_path: Path, code: RelayCode
) -> None:
    seeded, _ = _connect(tmp_path, [_envelope(RelayCode.OK)], token_text=_OLD_TOKEN)
    assert isinstance(seeded, RelayConnected)
    path = tmp_path / "credentials" / "relay.toml"
    before = path.read_bytes()
    assert _OLD_TOKEN.encode() in before
    result, transport = _connect(tmp_path, _scripted_for(code))
    assert isinstance(result, RelayConnectFailed)
    assert len(transport.requests) == 1
    assert path.read_bytes() == before
    assert _stored_files(tmp_path) == ["relay.toml"]


# --------------------------------------------------------------------------
# Req 12.6: replace, never revoke
# --------------------------------------------------------------------------


def test_a_replaced_token_is_replaced_and_never_revoked(tmp_path: Path) -> None:
    _connect(tmp_path, [_envelope(RelayCode.OK)], token_text=_OLD_TOKEN)
    old = _store(tmp_path).load("relay")
    assert old is not None and old.values["token"].reveal() == _OLD_TOKEN
    result, transport = _connect(tmp_path, [_envelope(RelayCode.OK)])
    assert isinstance(result, RelayConnected)
    new = _store(tmp_path).load("relay")
    assert new is not None and new.values["token"].reveal() == _TOKEN
    assert [(r.method, r.url) for r in transport.requests] == [
        ("GET", _BASE + "/v1/token")
    ]
    assert _stored_files(tmp_path) == ["relay.toml"]


# --------------------------------------------------------------------------
# Req 15.2, 15.4: the next-step text is fixed and total
# --------------------------------------------------------------------------

_NEXT_STEP_LITERALS: dict[RelayCode, str] = {
    RelayCode.OK: "Nothing more to do.",
    RelayCode.TOKEN_MISSING: "Run `fitdocs connect r1` and paste your relay token.",
    RelayCode.TOKEN_UNKNOWN: (
        "Check the token you pasted, or ask the relay's operator for a new one, "
        "then run `fitdocs connect r1`."
    ),
    RelayCode.TOKEN_REVOKED: (
        "Ask the relay's operator for a new token, or run "
        "`fitdocs connect r1 --register` if the relay offers registration."
    ),
    RelayCode.ENVELOPE_UNSUPPORTED: (
        "Update fitdocs; if it is already current, tell the relay's operator."
    ),
    RelayCode.REQUEST_MALFORMED: (
        "Update fitdocs; if it is already current, tell the relay's operator."
    ),
    RelayCode.REQUEST_TOO_LARGE: (
        "Update fitdocs; if it is already current, tell the relay's operator."
    ),
    RelayCode.NOT_OFFERED: "Ask the relay's operator for a token.",
    RelayCode.RATE_LIMITED: "Wait a few minutes, then try again.",
    RelayCode.UNAVAILABLE: (
        "Try again in a few minutes. If it persists, tell the relay's operator."
    ),
    RelayCode.RELAY_FAILURE: (
        "Try again in a few minutes. If it persists, tell the relay's operator."
    ),
    RelayCode.STORAGE_UNREACHABLE: (
        "Tell the relay's operator; nothing in fitdocs can change this."
    ),
    RelayCode.SCHEMA_BEHIND: (
        "Tell the relay's operator; nothing in fitdocs can change this."
    ),
    RelayCode.SCHEMA_AHEAD: (
        "Tell the relay's operator; nothing in fitdocs can change this."
    ),
    RelayCode.REGISTRATION_STARTED: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.REGISTRATION_PENDING: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.REGISTRATION_SLOW_DOWN: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.REGISTRATION_ISSUED: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.REGISTRATION_REFUSED: "Ask the relay's operator for a token.",
    RelayCode.REGISTRATION_EXPIRED: "Run `fitdocs connect r1 --register` again.",
    RelayCode.CONNECT_STARTED: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.CONNECT_PENDING: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.CONNECT_GRANTED: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.CONNECT_REFUSED: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.CONNECT_EXPIRED: (
        "Run `fitdocs connect r1` again; if this repeats, tell the relay's operator."
    ),
    RelayCode.RELAY_UNREACHABLE: (
        "Check your network connection and the relay's url in your fitdocs "
        "settings, then try again."
    ),
    RelayCode.ANSWER_MALFORMED: (
        "Check the relay's url in your fitdocs settings. If it is right, "
        "tell the relay's operator."
    ),
}


def test_the_next_step_literals_cover_the_whole_vocabulary() -> None:
    assert set(_NEXT_STEP_LITERALS) == set(RELAY_CODES)


@pytest.mark.parametrize("code", list(RELAY_CODES), ids=lambda c: c.value)
def test_every_code_has_its_fixed_next_step(code: RelayCode) -> None:
    assert (
        relay_next_step(code, name="r1", retry_after_s=None)
        == (_NEXT_STEP_LITERALS[code])
    )


@pytest.mark.parametrize("code", list(RELAY_CODES), ids=lambda c: c.value)
def test_only_the_rate_limit_next_step_depends_on_the_stated_wait(
    code: RelayCode,
) -> None:
    with_wait = relay_next_step(code, name="r1", retry_after_s=41)
    if code is RelayCode.RATE_LIMITED:
        assert with_wait == "Wait 41 seconds, then try again."
        assert (
            relay_next_step(code, name="r1", retry_after_s=1)
            == "Wait 1 second, then try again."
        )
        assert (
            relay_next_step(code, name="r1", retry_after_s=0)
            == "Wait 0 seconds, then try again."
        )
    else:
        assert with_wait == _NEXT_STEP_LITERALS[code]


def test_the_next_step_names_the_instance_it_was_given() -> None:
    step = relay_next_step(
        RelayCode.TOKEN_MISSING, name="work-relay", retry_after_s=None
    )
    assert step == "Run `fitdocs connect work-relay` and paste your relay token."


def test_the_result_dataclasses_are_frozen_with_their_designed_fields() -> None:
    assert [f.name for f in dataclasses.fields(RelayConnected)] == [
        "instance",
        "path",
        "env_override",
    ]
    assert [f.name for f in dataclasses.fields(RelayConnectFailed)] == [
        "instance",
        "code",
        "explanation",
        "next_step",
        "retry_after_s",
    ]
    connected = RelayConnected("relay", Path("p"), ())
    failed = RelayConnectFailed("relay", RelayCode.OK, "e", "n", None)
    for frozen in (connected, failed):
        with pytest.raises(dataclasses.FrozenInstanceError):
            frozen.instance = "other"  # type: ignore[misc]


# --------------------------------------------------------------------------
# design.md's RelayConnectEngine block (6.3 and 6.4 parts), whole
# --------------------------------------------------------------------------

_DESIGN_RENDERINGS = {
    "RelayConnected": (
        "@dataclass(frozen=True)\n"
        "class RelayConnected:\n"
        "    instance: str\n"
        "    path: Path\n"
        "    env_override: tuple[str, ...]"
    ),
    "RelayConnectFailed": (
        "@dataclass(frozen=True)\n"
        "class RelayConnectFailed:\n"
        "    instance: str\n"
        "    code: RelayCode\n"
        "    explanation: str\n"
        "    next_step: str\n"
        "    retry_after_s: int | None"
    ),
    "RegistrationShown": (
        "@dataclass(frozen=True)\n"
        "class RegistrationShown:\n"
        "    email: str\n"
        "    user_code: str\n"
        "    expires_in_s: int"
    ),
    "RelayTokenFormatError": "class RelayTokenFormatError(ValueError):\n    ...",
    "run_relay_connect": (
        "def run_relay_connect(instance: ConnectorInstance, token_text: str, *,"
        " store: CredentialStore, transport: Transport,"
        " environ: Mapping[str, str], now: Callable[[], datetime],"
        " sleep: Callable[[float], None], redactor: Redactor)"
        " -> RelayConnected | RelayConnectFailed:\n"
        "    ..."
    ),
    "run_relay_registration": (
        "def run_relay_registration(instance: ConnectorInstance, email: str, *,"
        " store: CredentialStore, transport: Transport,"
        " environ: Mapping[str, str], now: Callable[[], datetime],"
        " sleep: Callable[[float], None], redactor: Redactor,"
        " on_started: Callable[[RegistrationShown], None])"
        " -> RelayConnected | RelayConnectFailed:\n"
        "    ..."
    ),
    "relay_next_step": (
        "def relay_next_step(code: RelayCode, *, name: str,"
        " retry_after_s: int | None) -> str:\n"
        "    ..."
    ),
}


def _render_without_bodies(name: str) -> str:
    tree = ast.parse(inspect.getsource(relay_connect_module))
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef | ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"{name} must be defined exactly once"
    node = matches[0]
    if isinstance(node, ast.FunctionDef):
        node.body = [ast.Expr(ast.Constant(...))]
    else:
        body = node.body
        if (
            isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:] or [ast.Expr(ast.Constant(...))]
        node.body = body
    return ast.unparse(node)


@pytest.mark.parametrize("name", list(_DESIGN_RENDERINGS))
def test_the_engine_types_and_signatures_match_the_design_block_whole(
    name: str,
) -> None:
    assert _render_without_bodies(name) == _DESIGN_RENDERINGS[name]


# --------------------------------------------------------------------------
# Atomic replacement, the style guard, the credential-access stub
# --------------------------------------------------------------------------


def test_the_token_is_replaced_through_a_dot_prefixed_temp_then_one_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import tempfile

    _connect(tmp_path, [_envelope(RelayCode.OK)], token_text=_OLD_TOKEN)
    directory = tmp_path / "credentials"
    events: list[tuple[str, str]] = []
    real_mkstemp = tempfile.mkstemp
    real_replace = os.replace

    def spy_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)  # type: ignore[call-overload]
        events.append(("mkstemp", name))
        return fd, name

    def spy_replace(src: object, dst: object) -> None:
        events.append(("replace", f"{src}->{dst}"))
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
    monkeypatch.setattr(os, "replace", spy_replace)
    result, _ = _connect(tmp_path, [_envelope(RelayCode.OK)])
    assert isinstance(result, RelayConnected)
    assert [kind for kind, _ in events] == ["mkstemp", "replace"]
    temp = Path(events[0][1])
    assert temp.parent == directory
    assert temp.name.startswith(".")
    assert events[1][1] == f"{temp}->{directory / 'relay.toml'}"
    assert _stored_files(tmp_path) == ["relay.toml"]


@pytest.mark.parametrize(
    "style",
    [style for style in AuthStyle if style is not AuthStyle.RELAY_TOKEN],
    ids=lambda style: style.value,
)
def test_a_connector_that_is_not_a_relay_token_connector_is_refused_untouched(
    tmp_path: Path, style: AuthStyle
) -> None:
    class _KeyConnector:
        connector_id = "key"
        display_name = "key"
        auth_style = style
        capabilities: frozenset[object] = frozenset()
        credential_fields = ()

    instance = ConnectorInstance(
        name="key",
        connector=_KeyConnector(),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )
    transport = FakeTransport([])
    with pytest.raises(AssertionError):
        run_relay_connect(
            instance,
            _TOKEN,
            store=_store(tmp_path),
            transport=transport,
            environ={},
            now=lambda: _CLOCK,
            sleep=lambda seconds: None,
            redactor=Redactor(),
        )
    assert transport.requests == []
    assert not (tmp_path / "credentials").exists()


def test_the_session_a_relay_connect_hands_the_connector_gives_no_credential_access(
    tmp_path: Path,
) -> None:
    outcomes: list[str] = []

    class _Probing:
        connector_id = "relay"
        display_name = "probe"
        auth_style = AuthStyle.RELAY_TOKEN
        capabilities: frozenset[object] = frozenset()
        credential_fields = ()

        def check_token(self, session: object, token: object) -> None:
            creds = session.credentials  # type: ignore[attr-defined]
            assert creds.scopes is None
            assert creds.expires_at is None
            with pytest.raises(AssertionError):
                creds.value("token")
            outcomes.append("refused")
            with pytest.raises(AssertionError):
                creds.replace(None)
            outcomes.append("refused")
            return None

    instance = ConnectorInstance(
        name="probe",
        connector=_Probing(),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )
    result = run_relay_connect(
        instance,
        _TOKEN,
        store=_store(tmp_path),
        transport=FakeTransport([]),
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )
    assert isinstance(result, RelayConnected)
    assert outcomes == ["refused", "refused"]
