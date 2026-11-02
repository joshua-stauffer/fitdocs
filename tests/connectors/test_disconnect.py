"""Disconnecting an instance per authentication style (relay-server task 6.5;
Requirements 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 15.2).

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

from fitdocs.connectors import disconnect as disconnect_module
from fitdocs.connectors.credentials import (
    CredentialStore,
    CredentialStoreError,
    StoredCredentials,
    env_var_name,
)
from fitdocs.connectors.disconnect import (
    Disconnected,
    DisconnectFailed,
    NothingToDisconnect,
    run_disconnect,
)
from fitdocs.connectors.http import HttpResponse, TransportError
from fitdocs.connectors.protocol import AuthStyle, CredentialField
from fitdocs.connectors.relay import RelayConnector, RelaySettings
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode, explain
from fitdocs.connectors.relay_envelope import Answer, encode_answer
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from fitdocs.connectors.strava import StravaConnector, StravaSettings
from tests.connectors.conftest import FakeTransport

_CLOCK = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_BASE = "https://relay.example.com"
_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52
_ENV_TOKEN = "fdr1_" + "c" * 16 + "_" + "c" * 52
_PLANT = "PLANTED-BY-THE-RELAY-7f3a"

_REMOVING = (RelayCode.OK, RelayCode.TOKEN_UNKNOWN, RelayCode.TOKEN_REVOKED)

_LOCAL_ONLY_NOTE = "the token stays valid at the relay until its operator revokes it"
_SERVICE_NOTE = "the credential remains valid at the service"
_NEXT_STEP = (
    "Run `fitdocs disconnect {name}` again to retry, or add `--local-only` to "
    "forget the stored token without asking the relay."
)

# Relay answers that mean success for some other route: on the revocation
# they are an answer the route has no reading of.
_OTHER_ROUTE_CODES = frozenset(
    {
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
    }
)


class _Fake:
    """A connector of an arbitrary style; it has no operations at all, so any
    attempt to call one fails loudly."""

    connector_id = "fake"
    display_name = "fake"
    capabilities: frozenset[object] = frozenset()

    def __init__(self, style: AuthStyle, fields: tuple[str, ...] = ("key",)) -> None:
        self.auth_style = style
        self.credential_fields = tuple(CredentialField(f, f, True) for f in fields)


def _relay_instance(name: str = "relay") -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=RelayConnector(),
        lookback_days=30,
        settings=RelaySettings(url=_BASE),
    )


def _strava_instance(name: str = "strava") -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=StravaConnector(),
        lookback_days=30,
        settings=StravaSettings(
            relay_instance="home", upload=False, relay=RelaySettings(url=_BASE)
        ),
    )


def _fake_instance(
    style: AuthStyle, name: str = "svc", fields: tuple[str, ...] = ("key",)
) -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=_Fake(style, fields),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )


def _store(tmp_path: Path) -> CredentialStore:
    return CredentialStore(tmp_path / "credentials")


def _seed(
    tmp_path: Path,
    name: str,
    style: AuthStyle,
    token: str = _TOKEN,
    field: str = "token",
) -> Path:
    return _store(tmp_path).save(
        name,
        StoredCredentials(
            connector_id="x",
            auth_style=style,
            values={field: Secret(token)},
            expires_at=None,
            scopes=None,
        ),
    )


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


def _scripted_for(code: RelayCode) -> list[HttpResponse | TransportError]:
    info = RELAY_CODES[code]
    if code is RelayCode.RATE_LIMITED:
        return [_envelope(code, {"retry_after_s": 5}, outcome=_PLANT)]
    if info.origin is CodeOrigin.RELAY:
        return [_envelope(code, {"note": _PLANT}, outcome=_PLANT)]
    if code is RelayCode.RELAY_UNREACHABLE:
        return [TransportError("connection refused")]
    assert code is RelayCode.ANSWER_MALFORMED
    return [HttpResponse(status=200, headers={}, body=_PLANT.encode())]


def _expected_code(code: RelayCode) -> RelayCode:
    return RelayCode.ANSWER_MALFORMED if code in _OTHER_ROUTE_CODES else code


def _disconnect(
    tmp_path: Path,
    instance: ConnectorInstance,
    script: list[HttpResponse | TransportError] | None = None,
    *,
    local_only: bool = False,
    environ: Mapping[str, str] | None = None,
    redactor: Redactor | None = None,
    sleeps: list[float] | None = None,
) -> tuple[Disconnected | NothingToDisconnect | DisconnectFailed, FakeTransport]:
    transport = FakeTransport(script or [])
    log = sleeps if sleeps is not None else []
    result = run_disconnect(
        instance,
        local_only=local_only,
        store=_store(tmp_path),
        transport=transport,
        environ=environ or {},
        now=lambda: _CLOCK,
        sleep=log.append,
        redactor=redactor if redactor is not None else Redactor(),
    )
    return result, transport


def _snapshot(tmp_path: Path) -> dict[str, bytes]:
    directory = tmp_path / "credentials"
    if not directory.exists():
        return {}
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


_NON_REMOVING = [code for code in RELAY_CODES if code not in _REMOVING]


# --------------------------------------------------------------------------
# Req 14.1: one revocation with the stored token; three codes remove the file
# --------------------------------------------------------------------------


def test_the_collections_cover_the_whole_vocabulary() -> None:
    assert set(_NON_REMOVING) | set(_REMOVING) == set(RelayCode)
    assert not set(_NON_REMOVING) & set(_REMOVING)
    origins = {RELAY_CODES[code].origin for code in _NON_REMOVING}
    assert origins == {CodeOrigin.RELAY, CodeOrigin.CLIENT}
    assert len(_NON_REMOVING) >= 19


@pytest.mark.parametrize("code", _REMOVING, ids=lambda c: c.value)
def test_ok_unknown_and_revoked_each_remove_the_file_after_one_revocation(
    tmp_path: Path, code: RelayCode
) -> None:
    path = _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN)
    other = _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    other_before = other.read_bytes()
    assert path.exists()
    result, transport = _disconnect(tmp_path, _relay_instance(), [_envelope(code)])
    assert result == Disconnected(
        instance="relay",
        path=path,
        code=code,
        remote_revoked=code is RelayCode.OK,
        note=None,
    )
    assert not path.exists()
    assert other.read_bytes() == other_before
    assert (tmp_path / "credentials").is_dir()
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert (request.method, request.url) == ("POST", _BASE + "/v1/token/revoke")


def test_the_revocation_carries_the_stored_token_never_the_environment_override(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN)
    var = env_var_name("relay", "token")
    _, transport = _disconnect(
        tmp_path,
        _relay_instance(),
        [_envelope(RelayCode.OK)],
        environ={var: _ENV_TOKEN},
    )
    [request] = transport.requests
    assert {k: v.reveal() for k, v in request.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }
    assert _ENV_TOKEN not in repr(request.headers) + str(request.body)


def test_the_stored_token_is_registered_for_redaction_before_the_request_is_sent(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN)
    redactor = Redactor()
    assert redactor.redact(_TOKEN) == _TOKEN
    seen: list[str] = []

    def transport(request: object, timeout: float) -> HttpResponse:
        seen.append(redactor.redact(_TOKEN))
        return _envelope(RelayCode.OK)

    run_disconnect(
        _relay_instance(),
        local_only=False,
        store=_store(tmp_path),
        transport=transport,
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
    )
    assert seen == [REDACTED]


# --------------------------------------------------------------------------
# Req 14.2: every other answer keeps the file byte-identical
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", _NON_REMOVING, ids=lambda c: c.value)
def test_every_other_code_keeps_the_file_and_speaks_only_fitdocs_text(
    tmp_path: Path, code: RelayCode
) -> None:
    path = _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN)
    _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    _seed(tmp_path, "svc", AuthStyle.API_KEY, field="key")
    before = _snapshot(tmp_path)
    assert set(before) == {"relay.toml", "other.toml", "svc.toml"}
    result, transport = _disconnect(tmp_path, _relay_instance(), _scripted_for(code))
    expected = _expected_code(code)
    assert result == DisconnectFailed(
        instance="relay",
        code=expected,
        explanation=explain(expected),
        next_step=_NEXT_STEP.format(name="relay"),
    )
    assert len(transport.requests) == 1
    assert _snapshot(tmp_path) == before
    assert path.exists()
    assert _PLANT not in repr(result)


@pytest.mark.parametrize(
    "response",
    [
        HttpResponse(status=503, headers={}, body=b"<html>down</html>"),
        _envelope(RelayCode.UNAVAILABLE),
        HttpResponse(status=429, headers={"retry-after": "1"}, body=b""),
        _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 1}),
    ],
    ids=["503-plain", "503-envelope", "429-plain", "429-envelope"],
)
def test_a_503_and_a_429_each_produce_exactly_one_transport_call(
    tmp_path: Path, response: HttpResponse
) -> None:
    _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN)
    before = _snapshot(tmp_path)
    sleeps: list[float] = []
    # Answers that would succeed if the client retried.
    result, transport = _disconnect(
        tmp_path,
        _relay_instance(),
        [response, _envelope(RelayCode.OK), _envelope(RelayCode.OK)],
        sleeps=sleeps,
    )
    assert len(transport.requests) == 1
    assert isinstance(result, DisconnectFailed)
    assert sleeps == []
    assert _snapshot(tmp_path) == before


def test_a_stored_file_holding_no_token_is_an_error_and_sends_nothing(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN, field="other")
    before = _snapshot(tmp_path)
    transport = FakeTransport([])
    with pytest.raises(CredentialStoreError) as excinfo:
        run_disconnect(
            _relay_instance(),
            local_only=False,
            store=_store(tmp_path),
            transport=transport,
            environ={},
            now=lambda: _CLOCK,
            sleep=lambda seconds: None,
            redactor=Redactor(),
        )
    path = tmp_path / "credentials" / "relay.toml"
    assert str(excinfo.value) == (
        f"{path} holds no relay token; run: fitdocs disconnect relay --local-only"
    )
    assert transport.requests == []
    assert _snapshot(tmp_path) == before


# --------------------------------------------------------------------------
# Req 14.3, 14.5: no request, the file removed, a note
# --------------------------------------------------------------------------


def test_local_only_removes_the_file_with_no_request_and_a_note(
    tmp_path: Path,
) -> None:
    path = _seed(tmp_path, "relay", AuthStyle.RELAY_TOKEN)
    other = _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    other_before = other.read_bytes()
    result, transport = _disconnect(tmp_path, _relay_instance(), local_only=True)
    assert result == Disconnected(
        instance="relay",
        path=path,
        code=None,
        remote_revoked=False,
        note=_LOCAL_ONLY_NOTE,
    )
    assert transport.requests == []
    assert not path.exists()
    assert other.read_bytes() == other_before


@pytest.mark.parametrize("local_only", [False, True], ids=["plain", "local-only"])
@pytest.mark.parametrize("style", [AuthStyle.API_KEY, AuthStyle.LOGIN])
def test_personal_key_and_login_instances_remove_the_file_without_a_request(
    tmp_path: Path, style: AuthStyle, local_only: bool
) -> None:
    path = _seed(tmp_path, "svc", style, field="key")
    other = _seed(tmp_path, "other", AuthStyle.API_KEY, field="key")
    other_before = other.read_bytes()
    result, transport = _disconnect(
        tmp_path, _fake_instance(style), local_only=local_only
    )
    assert result == Disconnected(
        instance="svc",
        path=path,
        code=None,
        remote_revoked=False,
        note=_SERVICE_NOTE,
    )
    assert transport.requests == []
    assert not path.exists()
    assert other.read_bytes() == other_before


# --------------------------------------------------------------------------
# Req 14.4, 14.5: nothing to disconnect
# --------------------------------------------------------------------------

_AUTHENTICATING = [AuthStyle.RELAY_TOKEN, AuthStyle.API_KEY, AuthStyle.LOGIN]


@pytest.mark.parametrize("local_only", [False, True], ids=["plain", "local-only"])
@pytest.mark.parametrize("style", _AUTHENTICATING, ids=lambda s: s.value)
def test_an_absent_file_is_nothing_to_disconnect_listing_the_set_overrides(
    tmp_path: Path, style: AuthStyle, local_only: bool
) -> None:
    instance = (
        _relay_instance("inst")
        if style is AuthStyle.RELAY_TOKEN
        else _fake_instance(style, "inst", fields=("alpha", "beta", "gamma"))
    )
    fields = [f.name for f in instance.connector.credential_fields]
    # The decoy: another instance's file, never reported or touched.
    _seed(tmp_path, "other", AuthStyle.API_KEY, field="key")
    before = _snapshot(tmp_path)
    environ = {env_var_name("inst", f): "set" for f in fields}
    if len(fields) > 1:
        environ[env_var_name("inst", fields[1])] = ""
    environ["FITDOCS_CONNECTOR_OTHER_KEY"] = "decoy"
    environ_before = dict(environ)
    result, transport = _disconnect(
        tmp_path, instance, local_only=local_only, environ=environ
    )
    expected = tuple(
        env_var_name("inst", f) for f in fields if environ[env_var_name("inst", f)]
    )
    assert expected and (len(fields) == 1 or len(expected) == 2)
    assert result == NothingToDisconnect(instance="inst", env_override=expected)
    assert transport.requests == []
    assert _snapshot(tmp_path) == before
    assert environ == environ_before


@pytest.mark.parametrize("style", _AUTHENTICATING, ids=lambda s: s.value)
def test_an_absent_file_with_no_override_set_lists_nothing(
    tmp_path: Path, style: AuthStyle
) -> None:
    instance = (
        _relay_instance("inst")
        if style is AuthStyle.RELAY_TOKEN
        else _fake_instance(style, "inst")
    )
    result, _ = _disconnect(tmp_path, instance)
    assert result == NothingToDisconnect(instance="inst", env_override=())


def test_a_no_authentication_instance_has_nothing_to_disconnect(
    tmp_path: Path,
) -> None:
    # A file at the instance's name is not this style's and stays untouched.
    _seed(tmp_path, "svc", AuthStyle.API_KEY, field="key")
    before = _snapshot(tmp_path)
    result, transport = _disconnect(tmp_path, _fake_instance(AuthStyle.NONE))
    assert result == NothingToDisconnect(instance="svc", env_override=())
    assert transport.requests == []
    assert _snapshot(tmp_path) == before


def test_no_current_style_is_refused_as_unsupported(tmp_path: Path) -> None:
    # The browser-consent style used to raise UnsupportedDisconnect here.
    path = _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    result, transport = _disconnect(
        tmp_path, _strava_instance(), [_envelope(RelayCode.OK)]
    )
    assert isinstance(result, Disconnected)
    assert len(transport.requests) == 1
    assert not path.exists()


# The outcome of every style, with a stored file present and absent.
_STYLE_OUTCOMES: dict[AuthStyle, tuple[type | None, type]] = {
    AuthStyle.NONE: (NothingToDisconnect, NothingToDisconnect),
    AuthStyle.API_KEY: (Disconnected, NothingToDisconnect),
    AuthStyle.LOGIN: (Disconnected, NothingToDisconnect),
    AuthStyle.OAUTH_BROWSER: (Disconnected, NothingToDisconnect),
    AuthStyle.RELAY_TOKEN: (Disconnected, NothingToDisconnect),
}


_TOKEN_STYLES = (AuthStyle.RELAY_TOKEN, AuthStyle.OAUTH_BROWSER)


def test_every_authentication_style_has_a_pinned_outcome() -> None:
    assert set(_STYLE_OUTCOMES) == set(AuthStyle)


@pytest.mark.parametrize("present", [True, False], ids=["present", "absent"])
@pytest.mark.parametrize("style", list(AuthStyle), ids=lambda s: s.value)
def test_each_style_reaches_its_outcome_with_the_file_present_and_absent(
    tmp_path: Path, style: AuthStyle, present: bool
) -> None:
    if style is AuthStyle.RELAY_TOKEN:
        instance = _relay_instance("inst")
        script: list[HttpResponse | TransportError] = [_envelope(RelayCode.OK)]
    elif style is AuthStyle.OAUTH_BROWSER:
        instance = _strava_instance("inst")
        script = [_envelope(RelayCode.OK)]
    else:
        instance = _fake_instance(style, "inst")
        script = []
    if present:
        _seed(
            tmp_path,
            "inst",
            style,
            field="token" if style in _TOKEN_STYLES else "key",
        )
    result, _ = _disconnect(tmp_path, instance, script)
    expected = _STYLE_OUTCOMES[style][0 if present else 1]
    assert type(result) is expected


# --------------------------------------------------------------------------
# The result types and signature, whole
# --------------------------------------------------------------------------

_DESIGN_RENDERINGS = {
    "Disconnected": (
        "@dataclass(frozen=True)\n"
        "class Disconnected:\n"
        "    instance: str\n"
        "    path: Path\n"
        "    code: RelayCode | None\n"
        "    remote_revoked: bool\n"
        "    note: str | None"
    ),
    "NothingToDisconnect": (
        "@dataclass(frozen=True)\n"
        "class NothingToDisconnect:\n"
        "    instance: str\n"
        "    env_override: tuple[str, ...]"
    ),
    "DisconnectFailed": (
        "@dataclass(frozen=True)\n"
        "class DisconnectFailed:\n"
        "    instance: str\n"
        "    code: RelayCode\n"
        "    explanation: str\n"
        "    next_step: str"
    ),
    "UnsupportedDisconnect": "class UnsupportedDisconnect(ValueError):\n    ...",
    "run_disconnect": (
        "def run_disconnect(instance: ConnectorInstance, *, local_only: bool,"
        " store: CredentialStore, transport: Transport,"
        " environ: Mapping[str, str], now: Callable[[], datetime],"
        " sleep: Callable[[float], None], redactor: Redactor)"
        " -> Disconnected | NothingToDisconnect | DisconnectFailed:\n"
        "    ..."
    ),
}


def _render_without_bodies(name: str) -> str:
    tree = ast.parse(inspect.getsource(disconnect_module))
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
def test_the_types_and_signature_match_the_design_block_whole(name: str) -> None:
    assert _render_without_bodies(name) == _DESIGN_RENDERINGS[name]


def test_the_result_dataclasses_are_frozen() -> None:
    frozen: list[object] = [
        Disconnected("a", Path("p"), None, False, None),
        NothingToDisconnect("a", ()),
        DisconnectFailed("a", RelayCode.UNAVAILABLE, "e", "n"),
    ]
    for value in frozen:
        with pytest.raises(dataclasses.FrozenInstanceError):
            value.instance = "other"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# strava-publish Req 11.1-11.4: the browser-consent rows
# --------------------------------------------------------------------------

_STRAVA_NOTE_UNKNOWN = (
    "the relay no longer knows this token; a remaining Strava connection can "
    "be revoked in Strava's settings"
)
_STRAVA_LOCAL_ONLY_NOTE = (
    "the Strava connection stays at the relay until this instance is connected "
    "and disconnected again, or access is revoked in Strava's settings"
)
_STRAVA_DISCONNECT_URL = _BASE + "/v1/targets/strava/disconnect"

# Answers that mean success on another route: the disconnect route reads
# them as malformed.
_STRAVA_OTHER_ROUTE_CODES = _OTHER_ROUTE_CODES | {
    RelayCode.CONNECT_STARTED,
    RelayCode.CONNECT_PENDING,
    RelayCode.CONNECT_GRANTED,
}


@pytest.mark.parametrize(
    ("code", "note"),
    [
        (RelayCode.OK, None),
        (RelayCode.TOKEN_UNKNOWN, _STRAVA_NOTE_UNKNOWN),
        (RelayCode.TOKEN_REVOKED, _STRAVA_NOTE_UNKNOWN),
    ],
    ids=["ok", "token-unknown", "token-revoked"],
)
def test_strava_ok_unknown_and_revoked_remove_the_file_after_one_request(
    tmp_path: Path, code: RelayCode, note: str | None
) -> None:
    path = _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    other = _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    other_before = other.read_bytes()
    assert path.exists()
    result, transport = _disconnect(tmp_path, _strava_instance(), [_envelope(code)])
    assert result == Disconnected(
        instance="strava",
        path=path,
        code=code,
        remote_revoked=code is RelayCode.OK,
        note=note,
    )
    assert not path.exists()
    assert other.read_bytes() == other_before
    assert (tmp_path / "credentials").is_dir()
    [request] = transport.requests
    assert (request.method, request.url) == ("POST", _STRAVA_DISCONNECT_URL)
    assert {k: v.reveal() for k, v in request.secret_headers.items()} == {
        "Authorization": "Bearer " + _TOKEN
    }


_STRAVA_NON_REMOVING = [c for c in RELAY_CODES if c not in _REMOVING]


@pytest.mark.parametrize("code", _STRAVA_NON_REMOVING, ids=lambda c: c.value)
def test_strava_every_other_code_keeps_the_file_and_speaks_only_fitdocs_text(
    tmp_path: Path, code: RelayCode
) -> None:
    path = _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    before = _snapshot(tmp_path)
    assert set(before) == {"strava.toml", "other.toml"}
    result, transport = _disconnect(tmp_path, _strava_instance(), _scripted_for(code))
    expected = RelayCode.ANSWER_MALFORMED if code in _STRAVA_OTHER_ROUTE_CODES else code
    assert result == DisconnectFailed(
        instance="strava",
        code=expected,
        explanation=explain(expected),
        next_step=_NEXT_STEP.format(name="strava"),
    )
    assert len(transport.requests) == 1
    assert _snapshot(tmp_path) == before
    assert path.exists()
    assert _PLANT not in repr(result)


def test_strava_a_503_is_attempted_once_and_keeps_the_file(tmp_path: Path) -> None:
    _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    before = _snapshot(tmp_path)
    sleeps: list[float] = []
    result, transport = _disconnect(
        tmp_path,
        _strava_instance(),
        [
            HttpResponse(status=503, headers={}, body=b"down"),
            _envelope(RelayCode.OK),
            _envelope(RelayCode.OK),
        ],
        sleeps=sleeps,
    )
    assert len(transport.requests) == 1
    assert isinstance(result, DisconnectFailed)
    assert sleeps == []
    assert _snapshot(tmp_path) == before


def test_strava_the_request_carries_the_stored_token_never_the_override(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    var = env_var_name("strava", "token")
    assert var == "FITDOCS_CONNECTOR_STRAVA_TOKEN"
    _, transport = _disconnect(
        tmp_path,
        _strava_instance(),
        [_envelope(RelayCode.OK)],
        environ={var: _ENV_TOKEN},
    )
    [request] = transport.requests
    assert request.secret_headers["Authorization"].reveal() == "Bearer " + _TOKEN
    everything = repr(request.headers) + str(request.body) + request.url
    everything += "".join(v.reveal() for v in request.secret_headers.values())
    assert _ENV_TOKEN not in everything


def test_strava_the_stored_token_is_registered_for_redaction(tmp_path: Path) -> None:
    _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    redactor = Redactor()
    assert redactor.redact(_TOKEN) == _TOKEN
    _disconnect(
        tmp_path,
        _strava_instance(),
        [_envelope(RelayCode.OK)],
        redactor=redactor,
    )
    assert redactor.redact(_TOKEN) == REDACTED


def test_strava_a_stored_file_holding_no_token_is_an_error_and_sends_nothing(
    tmp_path: Path,
) -> None:
    path = _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER, field="other")
    before = _snapshot(tmp_path)
    with pytest.raises(CredentialStoreError) as caught:
        _disconnect(tmp_path, _strava_instance(), [_envelope(RelayCode.OK)])
    assert str(caught.value) == (
        f"{path} holds no connection token; run: fitdocs disconnect strava --local-only"
    )
    assert _snapshot(tmp_path) == before


def test_strava_local_only_removes_the_file_with_no_request_and_a_note(
    tmp_path: Path,
) -> None:
    path = _seed(tmp_path, "strava", AuthStyle.OAUTH_BROWSER)
    other = _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    other_before = other.read_bytes()
    result, transport = _disconnect(
        tmp_path, _strava_instance(), [_envelope(RelayCode.OK)], local_only=True
    )
    assert result == Disconnected(
        instance="strava",
        path=path,
        code=None,
        remote_revoked=False,
        note=_STRAVA_LOCAL_ONLY_NOTE,
    )
    assert transport.requests == []
    assert not path.exists()
    assert other.read_bytes() == other_before


@pytest.mark.parametrize("local_only", [False, True], ids=["plain", "local-only"])
def test_strava_an_absent_file_is_nothing_to_disconnect_with_no_request(
    tmp_path: Path, local_only: bool
) -> None:
    var = env_var_name("strava", "token")
    other = _seed(tmp_path, "other", AuthStyle.RELAY_TOKEN, token=_ENV_TOKEN)
    before = _snapshot(tmp_path)
    result, transport = _disconnect(
        tmp_path,
        _strava_instance(),
        [_envelope(RelayCode.OK)],
        local_only=local_only,
        environ={var: _ENV_TOKEN},
    )
    assert result == NothingToDisconnect(instance="strava", env_override=(var,))
    assert transport.requests == []
    assert _snapshot(tmp_path) == before
    assert other.exists()
