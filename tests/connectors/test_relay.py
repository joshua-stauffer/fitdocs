"""The relay connector and its envelope client (relay-server task 6.2;
Requirements 11.1, 11.2, 15.2, 15.3, 15.5).

Every request goes through a scripted ``FakeTransport``; the only place the
real ``urllib_transport`` runs is one test with ``urllib.request.urlopen``
replaced, to show where the token travels on the way out. This module is
admitted by the service-neutral scan for the maintainer's relay address.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fitdocs.connectors import (
    AuthStyle,
    CredentialField,
    SettingsContext,
    get,
    validate_connector,
)
from fitdocs.connectors import relay as relay_module
from fitdocs.connectors.errors import ConnectorError, ConnectorSettingsError
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    Transport,
    TransportError,
    urllib_transport,
)
from fitdocs.connectors.protocol import (
    ConnectorSession,
    RegistrationPolled,
    RegistrationStarted,
    RelayCapabilities,
    RelayRefused,
    TokenSet,
)
from fitdocs.connectors.relay import (
    DEFAULT_RELAY_URL,
    RELAY_CONNECTOR_ID,
    TOKEN_FIELD,
    RelayClient,
    RelayConnector,
    RelayReply,
    RelaySettings,
)
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode
from fitdocs.connectors.relay_envelope import (
    Answer,
    EnvelopeError,
    encode_answer,
    encode_request,
)
from fitdocs.connectors.relay_targets import MAX_UPLOAD_REQUEST_BYTES
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import (
    ConnectorsSettingsError,
    load_connectors_settings,
)
from tests.connectors.conftest import FakeTransport

_CLOCK = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_BASE = "https://relay.example.com"
# Visibly fake: an id of all `a` and a secret of all `a`.
_TOKEN = "fdr1_" + "a" * 16 + "_" + "a" * 52
_OTHER_TOKEN = "fdr1_" + "b" * 16 + "_" + "b" * 52
_POLL_SECRET = "p" * 40
_USER_CODE = "BCDF-GHJK"
_EMAIL = "runner@example.com"


def _context(tmp_path: Path) -> SettingsContext:
    return SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")


def _parse(tmp_path: Path, table: dict[str, object]) -> RelaySettings:
    return RelayConnector().parse_settings(table, _context(tmp_path))


class _StubCredentials:
    """Refuses every read and write: the relay operations take the token as
    an argument and store nothing."""

    def value(self, field: str) -> Secret:
        raise AssertionError("a relay operation takes its token as an argument")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise AssertionError("a relay operation stores nothing")


def _http(
    transport: Transport,
    redactor: Redactor,
    mode: CallMode = CallMode.AUTH,
) -> HttpClient:
    return HttpClient(
        transport, mode=mode, redactor=redactor, sleep=lambda seconds: None
    )


def _session(
    tmp_path: Path,
    transport: Transport,
    *,
    url: str = _BASE,
    redactor: Redactor | None = None,
) -> ConnectorSession:
    redactor = redactor if redactor is not None else Redactor()
    return ConnectorSession(
        instance="relay",
        settings=RelaySettings(url=url),
        http=_http(transport, redactor),
        credentials=_StubCredentials(),
        data_root=tmp_path,
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def _envelope(
    code: RelayCode,
    data: Mapping[str, object] | None = None,
    *,
    outcome: str | None = None,
    status: int | None = None,
    headers: Mapping[str, str] | None = None,
) -> HttpResponse:
    """A relay answer as the relay would send it: the codec's own encoding,
    with the code's published HTTP status unless one is given."""
    info = RELAY_CODES[code]
    assert info.origin is CodeOrigin.RELAY
    assert info.http_status is not None
    return HttpResponse(
        status=info.http_status if status is None else status,
        headers=dict(headers or {}),
        body=encode_answer(Answer(code=code, data=data or {}, outcome=outcome)),
    )


def _plain(
    status: int, body: bytes = b"", headers: Mapping[str, str] | None = None
) -> HttpResponse:
    return HttpResponse(status=status, headers=dict(headers or {}), body=body)


def _started_data() -> dict[str, object]:
    return {
        "user_code": _USER_CODE,
        "poll_secret": _POLL_SECRET,
        "interval_s": 7,
        "expires_in_s": 600,
    }


def _started(session: ConnectorSession) -> RegistrationStarted:
    return RegistrationStarted(
        user_code=_USER_CODE,
        poll_secret=session.secret(_POLL_SECRET),
        interval_s=7,
        expires_at=_CLOCK + timedelta(seconds=600),
    )


# --------------------------------------------------------------------------
# Declaration and registration (Req 11.1)
# --------------------------------------------------------------------------


def test_the_registry_returns_the_connector_and_its_gate_accepts_it() -> None:
    connector = get("relay")
    assert isinstance(connector, RelayConnector)
    assert validate_connector(connector) is None


def test_a_fresh_import_registers_folder_intervals_relay_then_strava() -> None:
    probe = (
        "import fitdocs.connectors as c; "
        "print(','.join(x.connector_id for x in c.available()))"
    )
    done = subprocess.run(
        [sys.executable, "-B", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout.strip() == "folder,intervals,relay,strava"


def test_the_declaration_is_a_capability_free_relay_token_connector() -> None:
    connector = RelayConnector()
    assert RELAY_CONNECTOR_ID == "relay"
    assert connector.connector_id == "relay"
    assert connector.display_name == "fitdocs relay"
    assert connector.auth_style is AuthStyle.RELAY_TOKEN
    assert isinstance(connector.capabilities, frozenset)
    assert connector.capabilities == frozenset()
    assert TOKEN_FIELD == "token"
    assert connector.credential_fields == (
        CredentialField("token", "Relay token", True),
    )


def test_the_default_url_is_the_maintainers_relay() -> None:
    assert DEFAULT_RELAY_URL == "https://api.fitdocs.ai"


# The module's declarations as design.md "RelayConnector and RelayClient"
# gives them, pinned whole: each class is compared as one AST rendering,
# docstrings stripped and every function body replaced by `...`, against a
# literal built from the design's text, so a decorator, base, attribute, alias,
# async method or extra method added to a class changes it.
# Three departures. Two are needed by mypy: the connector's `capabilities`
# carries an annotation to type an empty frozenset, and `parse_settings` is
# annotated `table: Mapping[str, object], context: SettingsContext` where the
# design sketch leaves its parameters bare. The third is `RelayClient.post`'s
# keyword-only `max_request_bytes`, a relay-server amendment carried by
# strava-publish (its design's R13.3).
_DESIGN_CONSTANTS = (
    "RELAY_CONNECTOR_ID: Final = 'relay'",
    "DEFAULT_RELAY_URL: Final = 'https://api.fitdocs.ai'",
    "TOKEN_FIELD: Final = 'token'",
)
_DESIGN_CLASSES = {
    "RelaySettings": ("@dataclass(frozen=True)\nclass RelaySettings:\n    url: str"),
    "RelayReply": (
        "@dataclass(frozen=True)\n"
        "class RelayReply:\n"
        "    code: RelayCode\n"
        "    data: Mapping[str, object]\n"
        "    outcome: str | None\n"
        "    retry_after_s: int | None"
    ),
}
_DESIGN_SIGNATURES = {
    ("RelayClient", "__init__"): (
        "def __init__(self, *, settings: RelaySettings, http: HttpClient,"
        " token: Secret | None) -> None:\n    ..."
    ),
    ("RelayClient", "get"): "def get(self, route: str) -> RelayReply:\n    ...",
    ("RelayClient", "post"): (
        "def post(self, route: str, fields: Mapping[str, object], *,"
        " max_request_bytes: int | None=None) -> RelayReply:\n    ..."
    ),
    ("RelayConnector", "parse_settings"): (
        "def parse_settings(self, table: Mapping[str, object],"
        " context: SettingsContext) -> RelaySettings:\n    ..."
    ),
    ("RelayConnector", "check_token"): (
        "def check_token(self, session: ConnectorSession, token: Secret)"
        " -> RelayRefused | None:\n    ..."
    ),
    ("RelayConnector", "read_capabilities"): (
        "def read_capabilities(self, session: ConnectorSession)"
        " -> RelayCapabilities | RelayRefused:\n    ..."
    ),
    ("RelayConnector", "start_registration"): (
        "def start_registration(self, session: ConnectorSession, email: str)"
        " -> RegistrationStarted | RelayRefused:\n    ..."
    ),
    ("RelayConnector", "poll_registration"): (
        "def poll_registration(self, session: ConnectorSession,"
        " started: RegistrationStarted) -> RegistrationPolled | RelayRefused:"
        "\n    ..."
    ),
    ("RelayConnector", "revoke_token"): (
        "def revoke_token(self, session: ConnectorSession, token: Secret)"
        " -> RelayRefused | None:\n    ..."
    ),
}
_DESIGN_CONNECTOR_ATTRIBUTES = (
    "connector_id = 'relay'",
    "display_name = 'fitdocs relay'",
    "auth_style = AuthStyle.RELAY_TOKEN",
    "capabilities: frozenset[Capability] = frozenset()",
    "credential_fields = (CredentialField('token', 'Relay token', True),)",
)


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(relay_module))


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    matches = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    assert len(matches) == 1, f"{name} must be defined exactly once"
    return matches[0]


def _strip_docstring(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> None:
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        node.body = node.body[1:] or [ast.Expr(ast.Constant(...))]


def test_the_module_constants_match_the_design_block() -> None:
    rendered = {
        ast.unparse(n)
        for n in _module_tree().body
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id in {"RELAY_CONNECTOR_ID", "DEFAULT_RELAY_URL", "TOKEN_FIELD"}
    }
    assert rendered == set(_DESIGN_CONSTANTS)


def test_the_value_classes_match_the_design_block_whole() -> None:
    tree = _module_tree()
    for name, expected in _DESIGN_CLASSES.items():
        node = _class_node(tree, name)
        _strip_docstring(node)
        assert ast.unparse(node) == expected, name


def _indented(text: str) -> str:
    return "\n".join("    " + line if line else line for line in text.split("\n"))


def _methods_of(class_name: str) -> str:
    return "\n\n".join(
        _indented(signature)
        for (owner, _), signature in _DESIGN_SIGNATURES.items()
        if owner == class_name
    )


_DESIGN_WHOLE_CLASSES = {
    "RelayClient": "class RelayClient:\n\n" + _methods_of("RelayClient"),
    "RelayConnector": (
        "class RelayConnector:\n"
        + "\n".join(_indented(line) for line in _DESIGN_CONNECTOR_ATTRIBUTES)
        + "\n\n"
        + _methods_of("RelayConnector")
    ),
}


def _whole_rendering(class_name: str) -> str:
    """The class as ast.unparse renders it, with docstrings stripped and every
    function body (async included) replaced by `...`."""
    node = _class_node(_module_tree(), class_name)
    for inner in ast.walk(node):
        if isinstance(inner, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            _strip_docstring(inner)
        if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef):
            inner.body = [ast.Expr(ast.Constant(...))]
    return ast.unparse(node)


def test_the_client_and_connector_classes_match_the_design_block_whole() -> None:
    assert set(_DESIGN_WHOLE_CLASSES) == {"RelayClient", "RelayConnector"}
    for name, expected in _DESIGN_WHOLE_CLASSES.items():
        assert _whole_rendering(name) == expected, name


def test_post_takes_an_optional_keyword_only_request_bound() -> None:
    parameters = inspect.signature(RelayClient.post).parameters
    assert list(parameters) == ["self", "route", "fields", "max_request_bytes"]
    bound = parameters["max_request_bytes"]
    assert bound.kind is inspect.Parameter.KEYWORD_ONLY
    assert bound.default is None


# --------------------------------------------------------------------------
# Settings: the URL rules (Req 11.1, 11.2)
# --------------------------------------------------------------------------

_NOT_ABSOLUTE = "url must be an absolute http or https URL"
_NOT_HTTPS = (
    "url must use https; http is accepted only for localhost, 127.0.0.1 and ::1"
)
_HAS_QUERY = "url must not carry a query"
_HAS_FRAGMENT = "url must not carry a fragment"
_HAS_USERINFO = "url must not carry user information"
_INVALID = "url is not a valid URL"


def test_an_absent_url_gives_the_default(tmp_path: Path) -> None:
    assert _parse(tmp_path, {}) == RelaySettings(url="https://api.fitdocs.ai")


def test_other_keys_are_ignored(tmp_path: Path) -> None:
    settings = _parse(tmp_path, {"colour": "teal", "url": _BASE})
    assert settings == RelaySettings(url=_BASE)


def _loopback_urls() -> list[str]:
    # Built from parts so this module names no literal loopback address URL.
    return ["http://" + host for host in ("localhost", "127.0.0.1", "[::1]")]


@pytest.mark.parametrize(
    ("given", "normalised"),
    [
        (_BASE, _BASE),
        ("https://relay.example.com:8443", "https://relay.example.com:8443"),
        ("https://localhost", "https://localhost"),
        ("https://relay.example.com/api", "https://relay.example.com/api"),
        ("https://relay.example.com/a@b", "https://relay.example.com/a@b"),
        ("HTTPS://relay.example.com", "HTTPS://relay.example.com"),
    ],
)
def test_accepted_https_urls(tmp_path: Path, given: str, normalised: str) -> None:
    assert _parse(tmp_path, {"url": given}).url == normalised


@pytest.mark.parametrize("given", _loopback_urls())
def test_http_to_each_loopback_host_is_accepted(tmp_path: Path, given: str) -> None:
    assert _parse(tmp_path, {"url": given}).url == given
    assert _parse(tmp_path, {"url": given + ":8080"}).url == given + ":8080"


def test_loopback_host_names_are_matched_without_case(tmp_path: Path) -> None:
    assert _parse(tmp_path, {"url": "http://LocalHost:9"}).url == "http://LocalHost:9"


@pytest.mark.parametrize(
    "given",
    [
        "http://relay.example.com",
        "http://localhost.example.com",
        "http://" + "127.0.0.2",
        "http://" + "0.0.0.0",
        "http://" + "[::2]",
        "http://" + "127.0.0.1.example.com",
        "http://" + "notlocalhost",
    ],
)
def test_http_to_anything_but_loopback_is_refused(tmp_path: Path, given: str) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.key == "url"
    assert excinfo.value.message == _NOT_HTTPS


@pytest.mark.parametrize(
    "given",
    ["ftp://relay.example.com", "ws://relay.example.com", "file:///etc/hosts"],
)
def test_a_scheme_other_than_http_or_https_is_refused(
    tmp_path: Path, given: str
) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.message in {_NOT_HTTPS, _NOT_ABSOLUTE}


@pytest.mark.parametrize(
    "given",
    [
        "",
        "relay.example.com",
        "relay.example.com:8080/x",
        "//relay.example.com",
        "/v1/token",
        "https://",
        "https:///path",
        "https:relay.example.com",
        "https://:8443",
    ],
)
def test_a_url_that_is_not_absolute_is_refused(tmp_path: Path, given: str) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.key == "url"
    assert excinfo.value.message == _NOT_ABSOLUTE


@pytest.mark.parametrize(
    "given",
    [
        "https://relay.example.com/?a=1",
        "https://relay.example.com?a=1",
        "https://relay.example.com/api?",
    ],
)
def test_a_url_with_a_query_is_refused(tmp_path: Path, given: str) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.message == _HAS_QUERY


@pytest.mark.parametrize(
    "given",
    [
        "https://relay.example.com/#top",
        "https://relay.example.com#top",
        "https://relay.example.com/api#",
        "https://relay.example.com/#a?b",
    ],
)
def test_a_url_with_a_fragment_is_refused(tmp_path: Path, given: str) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.message == _HAS_FRAGMENT


@pytest.mark.parametrize(
    "given",
    [
        "https://user@relay.example.com",
        "https://user:hunter2@relay.example.com",
        "https://:hunter2@relay.example.com",
        "https://@relay.example.com",
    ],
)
def test_a_url_with_user_information_is_refused_without_echoing_it(
    tmp_path: Path, given: str
) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.message == _HAS_USERINFO
    assert "hunter2" not in str(excinfo.value)


@pytest.mark.parametrize(
    "given",
    [
        "https://relay.example.com:99999",
        "https://relay.example.com:abc",
        "https://relay.example.com/a b",
        "https://relay.example.com/\n",
        "https://relay.example.com/\x7f",
        "https://relay.example.com/café",
        "http://" + "[::1",
    ],
)
def test_an_unusable_url_is_refused(tmp_path: Path, given: str) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.message == _INVALID


@pytest.mark.parametrize("given", [None, 8080, ["https://relay.example.com"], b"x"])
def test_a_non_string_url_is_refused(tmp_path: Path, given: object) -> None:
    with pytest.raises(ConnectorSettingsError) as excinfo:
        _parse(tmp_path, {"url": given})
    assert excinfo.value.key == "url"
    assert excinfo.value.message == _INVALID


@pytest.mark.parametrize(
    ("given", "normalised"),
    [
        ("https://relay.example.com/", "https://relay.example.com"),
        ("https://relay.example.com/api/", "https://relay.example.com/api"),
        ("https://relay.example.com//", "https://relay.example.com"),
        ("https://relay.example.com/api", "https://relay.example.com/api"),
    ],
)
def test_the_trailing_slash_is_stripped(
    tmp_path: Path, given: str, normalised: str
) -> None:
    assert _parse(tmp_path, {"url": given}).url == normalised


def test_a_refused_url_in_a_settings_file_names_file_instance_and_key(
    tmp_path: Path,
) -> None:
    settings_file = tmp_path / "fitdocs.toml"
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"home": {"connector": "relay", "url": "http://x.invalid"}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    assert str(excinfo.value) == f"{settings_file}: [connectors.home] url: {_NOT_HTTPS}"


def test_the_default_url_instance_loads_from_settings(tmp_path: Path) -> None:
    instances = load_connectors_settings(
        {"connectors": {"relay": {}}},
        settings_file=tmp_path / "fitdocs.toml",
        context=_context(tmp_path),
    )
    assert instances[0].connector is get("relay")
    assert instances[0].settings == RelaySettings(url=DEFAULT_RELAY_URL)


# --------------------------------------------------------------------------
# The envelope client: requests (Req 15.2, 15.3)
# --------------------------------------------------------------------------


def _client(
    transport: Transport,
    *,
    url: str = _BASE,
    token: str | None = None,
    redactor: Redactor | None = None,
    mode: CallMode = CallMode.AUTH,
) -> RelayClient:
    return RelayClient(
        settings=RelaySettings(url=url),
        http=_http(transport, redactor if redactor is not None else Redactor(), mode),
        token=Secret(token) if token is not None else None,
    )


def _lowered(request: HttpRequest) -> dict[str, str]:
    return {name.lower(): value for name, value in request.headers.items()}


def test_get_sends_one_request_to_the_base_plus_route() -> None:
    transport = FakeTransport([_envelope(RelayCode.OK)])
    reply = _client(transport, url=_BASE + "/api").get("/v1/token")
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url == _BASE + "/api/v1/token"
    assert request.body is None
    assert _lowered(request)["accept"] == "application/json"
    assert reply.code is RelayCode.OK


def test_post_sends_the_encoded_fields_as_json() -> None:
    transport = FakeTransport([_envelope(RelayCode.OK)])
    fields = {"email": _EMAIL, "n": 3}
    _client(transport).post("/v1/registrations", fields)
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == _BASE + "/v1/registrations"
    assert request.body == encode_request(fields)
    assert request.body == b'{"email":"runner@example.com","n":3}'
    assert _lowered(request)["content-type"] == "application/json"
    assert _lowered(request)["accept"] == "application/json"


def test_a_request_the_codec_cannot_encode_raises_and_sends_nothing() -> None:
    transport = FakeTransport([])
    with pytest.raises(EnvelopeError):
        _client(transport).post("/v1/registrations", {"email": "a" * 70_000})
    assert transport.requests == []


def test_a_data_mode_get_503_sees_one_transport_call() -> None:
    transport = FakeTransport([_plain(503, b"<html>")] * 3)
    client = _client(transport, mode=CallMode.DATA)
    reply = client.get("/v1/capabilities")
    assert reply.code is RelayCode.UNAVAILABLE
    assert len(transport.requests) == 1
    assert transport.requests[0].single_attempt is True


def test_a_data_mode_post_503_sees_one_transport_call() -> None:
    transport = FakeTransport([_plain(503, b"<html>")] * 3)
    client = _client(transport, mode=CallMode.DATA)
    reply = client.post("/v1/targets/strava/publish", {"a": 1})
    assert reply.code is RelayCode.UNAVAILABLE
    assert len(transport.requests) == 1
    assert transport.requests[0].single_attempt is True


def test_a_data_mode_transport_failure_is_not_repeated() -> None:
    failure = TransportError("network failure")
    transport = FakeTransport([failure] * 3)
    client = _client(transport, mode=CallMode.DATA)
    assert client.get("/v1/capabilities").code is RelayCode.RELAY_UNREACHABLE
    assert client.post("/v1/x", {}).code is RelayCode.RELAY_UNREACHABLE
    assert len(transport.requests) == 2


def test_the_same_503_over_a_plain_data_mode_request_is_retried() -> None:
    transport = FakeTransport([_plain(503, b"<html>")] * 3)
    http = _http(transport, Redactor(), CallMode.DATA)
    response = http.get(_BASE + "/v1/x")
    assert response.status == 503
    assert len(transport.requests) == 3


_BOUND_FIELDS = {"k": "x" * 30}


def test_a_body_exactly_at_the_bound_is_sent() -> None:
    size = len(encode_request(_BOUND_FIELDS))
    assert size == 38
    transport = FakeTransport([_envelope(RelayCode.OK)])
    reply = _client(transport).post("/v1/x", _BOUND_FIELDS, max_request_bytes=size)
    assert reply.code is RelayCode.OK
    assert len(transport.requests) == 1


def test_a_body_one_byte_over_the_bound_is_refused_before_any_request() -> None:
    size = len(encode_request(_BOUND_FIELDS))
    transport = FakeTransport([])
    with pytest.raises(EnvelopeError):
        _client(transport, mode=CallMode.DATA).post(
            "/v1/x", _BOUND_FIELDS, max_request_bytes=size - 1
        )
    assert transport.requests == []


def test_a_bound_of_zero_refuses_any_body_before_any_request() -> None:
    transport = FakeTransport([])
    with pytest.raises(EnvelopeError):
        _client(transport, mode=CallMode.DATA).post("/v1/x", {}, max_request_bytes=0)
    assert transport.requests == []


def test_an_absent_bound_keeps_the_envelope_default() -> None:
    shell = len(encode_request({"k": ""}))
    transport = FakeTransport([_envelope(RelayCode.OK)])
    _client(transport).post("/v1/x", {"k": "x" * (65_536 - shell)})
    assert len(transport.requests) == 1
    assert len(transport.requests[0].body or b"") == 65_536
    refused = FakeTransport([])
    with pytest.raises(EnvelopeError):
        _client(refused).post("/v1/x", {"k": "x" * (65_537 - shell)})
    assert refused.requests == []


def test_the_upload_bound_sends_a_body_over_the_envelope_default() -> None:
    shell = len(encode_request({"k": ""}))
    fields = {"k": "x" * (100_000 - shell)}
    transport = FakeTransport([_envelope(RelayCode.OK)])
    reply = _client(transport, mode=CallMode.DATA).post(
        "/v1/targets/strava/publish", fields, max_request_bytes=MAX_UPLOAD_REQUEST_BYTES
    )
    assert reply.code is RelayCode.OK
    assert len(transport.requests) == 1
    assert len(transport.requests[0].body or b"") == 100_000


def test_the_upload_bound_refuses_one_byte_over_it_before_any_request() -> None:
    shell = len(encode_request({"k": ""}))
    transport = FakeTransport([])
    with pytest.raises(EnvelopeError):
        _client(transport).post(
            "/v1/x",
            {"k": "x" * (MAX_UPLOAD_REQUEST_BYTES + 1 - shell)},
            max_request_bytes=MAX_UPLOAD_REQUEST_BYTES,
        )
    assert transport.requests == []


def test_the_token_is_one_unredirected_credential_header_and_nowhere_else() -> None:
    transport = FakeTransport([_envelope(RelayCode.OK), _envelope(RelayCode.OK)])
    client = _client(transport, token=_TOKEN)
    client.get("/v1/token")
    client.post("/v1/token/revoke", {})
    assert len(transport.requests) == 2
    for request in transport.requests:
        assert request.secret_headers == {"Authorization": Secret("Bearer " + _TOKEN)}
        assert _TOKEN not in request.url
        assert not any(_TOKEN in v for v in request.headers.values())
        assert not any(
            name.lower() in {"authorization", "cookie"} for name in request.headers
        )
        assert request.body is None or _TOKEN.encode() not in request.body
    assert transport.requests[1].body == b"{}"


def test_without_a_token_no_credential_header_is_sent() -> None:
    transport = FakeTransport([_envelope(RelayCode.OK)])
    _client(transport, token=None).get("/v1/capabilities")
    assert transport.requests[0].secret_headers == {}


def test_the_token_reaches_the_real_transport_only_as_an_unredirected_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request

    seen: list[urllib.request.Request] = []

    class _Response:
        status = 200
        headers = {"content-type": "application/json"}

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            return encode_answer(Answer(code=RelayCode.OK, data={}))

    def _urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        seen.append(request)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    reply = _client(urllib_transport, token=_TOKEN).get("/v1/token")
    assert reply.code is RelayCode.OK
    (request,) = seen
    assert request.unredirected_hdrs == {"Authorization": "Bearer " + _TOKEN}
    assert request.headers.get("Authorization") is None
    assert _TOKEN not in request.full_url
    assert not any(_TOKEN in v for v in request.headers.values())


def test_the_request_is_sent_with_the_composed_user_agent() -> None:
    from fitdocs.version import user_agent

    transport = FakeTransport([_envelope(RelayCode.OK)])
    _client(transport).get("/livez")
    headers = {k.lower(): v for k, v in transport.requests[0].headers.items()}
    assert headers["user-agent"] == user_agent()


# --------------------------------------------------------------------------
# The envelope client: replies and fallbacks (Req 15.2, 15.3)
# --------------------------------------------------------------------------


def test_a_valid_envelope_is_exposed_as_code_data_outcome_and_no_retry() -> None:
    transport = FakeTransport([_envelope(RelayCode.OK, {"k": [1, 2]}, outcome="sent")])
    reply = _client(transport).get("/v1/token")
    assert reply == RelayReply(RelayCode.OK, {"k": [1, 2]}, "sent", None)


def test_a_rate_limited_envelope_carries_its_stated_wait() -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 37})]
    )
    assert _client(transport).get("/x").retry_after_s == 37


def test_a_rate_limited_envelope_that_states_none_gives_none() -> None:
    transport = FakeTransport([_envelope(RelayCode.RATE_LIMITED, {})])
    reply = _client(transport).get("/x")
    assert (reply.code, reply.retry_after_s) == (RelayCode.RATE_LIMITED, None)


def test_a_rate_limited_envelope_with_a_malformed_wait_is_malformed() -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.RATE_LIMITED, {"retry_after_s": -1})]
    )
    assert _client(transport).get("/x") == RelayReply(
        RelayCode.ANSWER_MALFORMED, {}, None, None
    )


def test_a_transport_failure_is_relay_unreachable_without_its_message() -> None:
    transport = FakeTransport([TransportError("timed out: " + _BASE + "/secret-path")])
    reply = _client(transport).get("/v1/token")
    assert reply == RelayReply(RelayCode.RELAY_UNREACHABLE, {}, None, None)
    assert "secret-path" not in repr(reply)


@pytest.mark.parametrize(
    ("response", "code", "retry"),
    [
        (_plain(429, b"<html>slow down</html>"), RelayCode.RATE_LIMITED, None),
        (_plain(429, b"", {"retry-after": "7"}), RelayCode.RATE_LIMITED, 7),
        (_plain(429, b"x", {"retry-after": "0"}), RelayCode.RATE_LIMITED, 0),
        (_plain(429, b"x", {"retry-after": "7.5"}), RelayCode.RATE_LIMITED, None),
        (_plain(429, b"x", {"retry-after": "-3"}), RelayCode.RATE_LIMITED, None),
        (_plain(429, b"x", {"retry-after": "+3"}), RelayCode.RATE_LIMITED, None),
        (_plain(429, b"x", {"retry-after": ""}), RelayCode.RATE_LIMITED, None),
        (_plain(429, b"x", {"retry-after": "٥"}), RelayCode.RATE_LIMITED, None),
        (
            _plain(429, b"x", {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}),
            RelayCode.RATE_LIMITED,
            None,
        ),
        (_plain(429, b"x", {"retry-after": " 12 "}), RelayCode.RATE_LIMITED, 12),
        (_plain(500, b"oops"), RelayCode.UNAVAILABLE, None),
        (_plain(502), RelayCode.UNAVAILABLE, None),
        (_plain(503, b"<html>"), RelayCode.UNAVAILABLE, None),
        (_plain(504, b"{}"), RelayCode.UNAVAILABLE, None),
        (_plain(599, b"x"), RelayCode.UNAVAILABLE, None),
        (_plain(503, b"x", {"retry-after": "9"}), RelayCode.UNAVAILABLE, None),
        (_plain(200, b"not json"), RelayCode.ANSWER_MALFORMED, None),
        (_plain(200, b""), RelayCode.ANSWER_MALFORMED, None),
        (_plain(200, b'{"a":1}'), RelayCode.ANSWER_MALFORMED, None),
        (_plain(404, b"<html>"), RelayCode.ANSWER_MALFORMED, None),
        (_plain(400, b"bad"), RelayCode.ANSWER_MALFORMED, None),
        (_plain(401, b"no"), RelayCode.ANSWER_MALFORMED, None),
        (_plain(499, b"x"), RelayCode.ANSWER_MALFORMED, None),
        (_plain(600, b"x"), RelayCode.ANSWER_MALFORMED, None),
        (
            _plain(301, b"", {"location": "https://elsewhere.example.com"}),
            RelayCode.ANSWER_MALFORMED,
            None,
        ),
        (_plain(200, b"x", {"retry-after": "9"}), RelayCode.ANSWER_MALFORMED, None),
    ],
)
def test_a_body_that_is_not_an_envelope_falls_back_on_its_status(
    response: HttpResponse, code: RelayCode, retry: int | None
) -> None:
    reply = _client(FakeTransport([response])).get("/v1/token")
    assert reply == RelayReply(code, {}, None, retry)


def test_a_valid_envelope_wins_over_the_status_fallback() -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.RELAY_FAILURE, status=503, headers={"retry-after": "9"})]
    )
    reply = _client(transport).get("/x")
    assert reply == RelayReply(RelayCode.RELAY_FAILURE, {}, None, None)


def test_a_relay_cannot_send_a_client_only_code() -> None:
    body = b'{"envelope":1,"code":"relay-unreachable","data":{}}'
    reply = _client(FakeTransport([_plain(200, body)])).get("/x")
    assert reply.code is RelayCode.ANSWER_MALFORMED


def test_a_rate_limited_envelope_stating_no_wait_ignores_the_header() -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.RATE_LIMITED, {}, headers={"retry-after": "9"})]
    )
    reply = _client(transport).get("/x")
    assert reply == RelayReply(RelayCode.RATE_LIMITED, {}, None, None)


def test_a_valid_envelope_is_not_confused_by_a_429_status() -> None:
    transport = FakeTransport(
        [_envelope(RelayCode.OK, {"k": 1}, status=429, headers={"retry-after": "5"})]
    )
    reply = _client(transport).get("/x")
    assert reply == RelayReply(RelayCode.OK, {"k": 1}, None, None)


# --------------------------------------------------------------------------
# The five operations (Req 11.1, 15.2, 15.3, 15.5)
# --------------------------------------------------------------------------

# Every relay-origin code that is not a success reading of a relay-connector
# route and not rate-limited (which carries a wait and has its own tests),
# built from the whole vocabulary so a code a later spec appends is exercised
# automatically. connect-started, connect-pending and connect-granted are
# success readings of a Strava connector route, not a relay-connector route,
# so the token operations refuse them as they refuse connect-refused and
# connect-expired, each with its own code.
_NOT_A_REFUSAL = frozenset(
    {
        RelayCode.OK,
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
        RelayCode.RATE_LIMITED,
    }
)
_REFUSAL_CODES = [
    code
    for code, info in RELAY_CODES.items()
    if info.origin is CodeOrigin.RELAY and code not in _NOT_A_REFUSAL
]
# A literal count: a code appended to the vocabulary (strava-publish appends
# some) fails here until someone decides whether it belongs in this list.
_TODAYS_REFUSAL_CODES = 19


def test_the_refusal_collection_is_todays_nineteen() -> None:
    assert len(_REFUSAL_CODES) == _TODAYS_REFUSAL_CODES


def _run_token_ops(
    tmp_path: Path, name: str, answer: HttpResponse
) -> tuple[FakeTransport, RelayRefused | None]:
    transport = FakeTransport([answer])
    session = _session(tmp_path, transport)
    connector = RelayConnector()
    method = getattr(connector, name)
    return transport, method(session, Secret(_TOKEN))


@pytest.mark.parametrize("name", ["check_token", "revoke_token"])
def test_a_token_operation_returns_none_on_ok(tmp_path: Path, name: str) -> None:
    transport, result = _run_token_ops(tmp_path, name, _envelope(RelayCode.OK))
    assert result is None
    assert len(transport.requests) == 1


@pytest.mark.parametrize("name", ["check_token", "revoke_token"])
@pytest.mark.parametrize("code", _REFUSAL_CODES)
def test_a_token_operation_returns_every_other_code_as_a_refusal(
    tmp_path: Path, name: str, code: RelayCode
) -> None:
    transport, result = _run_token_ops(tmp_path, name, _envelope(code))
    assert result == RelayRefused(code, None)
    assert len(transport.requests) == 1


@pytest.mark.parametrize("name", ["check_token", "revoke_token"])
def test_a_token_operation_returns_the_stated_wait_with_rate_limited(
    tmp_path: Path, name: str
) -> None:
    answer = _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 41})
    _, result = _run_token_ops(tmp_path, name, answer)
    assert result == RelayRefused(RelayCode.RATE_LIMITED, 41)


@pytest.mark.parametrize("name", ["check_token", "revoke_token"])
@pytest.mark.parametrize(
    "answer",
    [
        _envelope(RelayCode.OK, {"extra": 1}),
        _envelope(RelayCode.REGISTRATION_ISSUED, {"token": _OTHER_TOKEN}),
        _envelope(RelayCode.REGISTRATION_STARTED, _started_data()),
        _envelope(RelayCode.REGISTRATION_PENDING),
        _envelope(RelayCode.REGISTRATION_SLOW_DOWN),
    ],
)
def test_a_token_operation_treats_an_answer_of_another_route_as_malformed(
    tmp_path: Path, name: str, answer: HttpResponse
) -> None:
    _, result = _run_token_ops(tmp_path, name, answer)
    assert result == RelayRefused(RelayCode.ANSWER_MALFORMED, None)


def test_check_token_is_a_get_of_the_token_route(tmp_path: Path) -> None:
    transport, _ = _run_token_ops(tmp_path, "check_token", _envelope(RelayCode.OK))
    request = transport.requests[0]
    assert (request.method, request.url, request.body) == (
        "GET",
        _BASE + "/v1/token",
        None,
    )


def test_revoke_token_is_a_post_of_an_empty_object(tmp_path: Path) -> None:
    transport, _ = _run_token_ops(tmp_path, "revoke_token", _envelope(RelayCode.OK))
    request = transport.requests[0]
    assert (request.method, request.url, request.body) == (
        "POST",
        _BASE + "/v1/token/revoke",
        b"{}",
    )


@pytest.mark.parametrize("name", ["check_token", "revoke_token"])
def test_a_token_operation_registers_the_token_for_redaction(
    tmp_path: Path, name: str
) -> None:
    redactor = Redactor()
    transport = FakeTransport([_envelope(RelayCode.OK)])
    session = _session(tmp_path, transport, redactor=redactor)
    token = Secret(_OTHER_TOKEN)
    assert redactor.redact("t=" + _OTHER_TOKEN) == "t=" + _OTHER_TOKEN
    getattr(RelayConnector(), name)(session, token)
    assert redactor.redact("t=" + _OTHER_TOKEN) == "t=" + REDACTED


@pytest.mark.parametrize("name", ["check_token", "revoke_token"])
def test_a_token_operation_sends_the_token_only_as_the_credential_header(
    tmp_path: Path, name: str
) -> None:
    transport, _ = _run_token_ops(tmp_path, name, _envelope(RelayCode.OK))
    (request,) = transport.requests
    assert request.secret_headers == {"Authorization": Secret("Bearer " + _TOKEN)}
    assert _TOKEN not in request.url
    assert not any(_TOKEN in v for v in request.headers.values())
    assert request.body is None or _TOKEN.encode() not in request.body


def test_read_capabilities_parses_the_codec_data_and_sends_no_token(
    tmp_path: Path,
) -> None:
    data = {"envelopes": [1, 2], "registration": True, "targets": ["alpha", "beta"]}
    transport = FakeTransport([_envelope(RelayCode.OK, data)])
    result = RelayConnector().read_capabilities(_session(tmp_path, transport))
    assert result == RelayCapabilities(
        envelopes=(1, 2), registration=True, targets=("alpha", "beta")
    )
    (request,) = transport.requests
    assert (request.method, request.url) == ("GET", _BASE + "/v1/capabilities")
    assert request.secret_headers == {}


@pytest.mark.parametrize(
    "data",
    [
        {"envelopes": [1], "registration": True},
        {"envelopes": [1], "registration": "yes", "targets": []},
        {"envelopes": [1], "registration": True, "targets": ["BAD"]},
        {"envelopes": [1], "registration": True, "targets": [], "extra": 1},
        {"envelopes": [], "registration": True, "targets": []},
    ],
)
def test_malformed_capabilities_data_is_answer_malformed(
    tmp_path: Path, data: dict[str, object]
) -> None:
    transport = FakeTransport([_envelope(RelayCode.OK, data)])
    result = RelayConnector().read_capabilities(_session(tmp_path, transport))
    assert result == RelayRefused(RelayCode.ANSWER_MALFORMED, None)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 12}),
            RelayRefused(RelayCode.RATE_LIMITED, 12),
        ),
        (_envelope(RelayCode.UNAVAILABLE), RelayRefused(RelayCode.UNAVAILABLE, None)),
        (
            _envelope(RelayCode.REGISTRATION_ISSUED, {"token": _OTHER_TOKEN}),
            RelayRefused(RelayCode.ANSWER_MALFORMED, None),
        ),
        (_plain(200, b"nope"), RelayRefused(RelayCode.ANSWER_MALFORMED, None)),
        *[
            (
                _envelope(
                    code, {"envelopes": [1], "registration": True, "targets": []}
                ),
                RelayRefused(RelayCode.ANSWER_MALFORMED, None),
            )
            for code in (
                RelayCode.REGISTRATION_STARTED,
                RelayCode.REGISTRATION_PENDING,
                RelayCode.REGISTRATION_SLOW_DOWN,
                RelayCode.REGISTRATION_ISSUED,
            )
        ],
    ],
)
def test_capabilities_other_answers_are_refusals(
    tmp_path: Path, answer: HttpResponse, expected: RelayRefused
) -> None:
    result = RelayConnector().read_capabilities(
        _session(tmp_path, FakeTransport([answer]))
    )
    assert result == expected


def test_start_registration_parses_the_started_answer(tmp_path: Path) -> None:
    redactor = Redactor()
    transport = FakeTransport(
        [_envelope(RelayCode.REGISTRATION_STARTED, _started_data())]
    )
    session = _session(tmp_path, transport, redactor=redactor)
    assert redactor.redact(_POLL_SECRET) == _POLL_SECRET
    result = RelayConnector().start_registration(session, _EMAIL)
    assert result == RegistrationStarted(
        user_code=_USER_CODE,
        poll_secret=Secret(_POLL_SECRET),
        interval_s=7,
        expires_at=_CLOCK + timedelta(seconds=600),
    )
    assert isinstance(result, RegistrationStarted)
    assert redactor.redact("s=" + _POLL_SECRET) == "s=" + REDACTED
    (request,) = transport.requests
    assert (request.method, request.url) == ("POST", _BASE + "/v1/registrations")
    assert request.body == encode_request({"email": _EMAIL})
    assert request.secret_headers == {}


@pytest.mark.parametrize(
    "data",
    [
        {**_started_data(), "user_code": "bcdf-ghjk"},
        {**_started_data(), "poll_secret": "short"},
        {**_started_data(), "interval_s": 0},
        {**_started_data(), "expires_in_s": 59},
        {**_started_data(), "extra": 1},
        {"user_code": _USER_CODE},
    ],
)
def test_a_malformed_started_answer_is_answer_malformed(
    tmp_path: Path, data: dict[str, object]
) -> None:
    redactor = Redactor()
    transport = FakeTransport([_envelope(RelayCode.REGISTRATION_STARTED, data)])
    session = _session(tmp_path, transport, redactor=redactor)
    result = RelayConnector().start_registration(session, _EMAIL)
    assert result == RelayRefused(RelayCode.ANSWER_MALFORMED, None)
    assert redactor.redact(_POLL_SECRET) == _POLL_SECRET


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            _envelope(RelayCode.REGISTRATION_REFUSED),
            RelayRefused(RelayCode.REGISTRATION_REFUSED, None),
        ),
        (_envelope(RelayCode.NOT_OFFERED), RelayRefused(RelayCode.NOT_OFFERED, None)),
        (
            _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 3}),
            RelayRefused(RelayCode.RATE_LIMITED, 3),
        ),
        (
            _envelope(RelayCode.OK, _started_data()),
            RelayRefused(RelayCode.ANSWER_MALFORMED, None),
        ),
    ],
)
def test_start_registration_returns_other_answers_as_refusals(
    tmp_path: Path, answer: HttpResponse, expected: RelayRefused
) -> None:
    result = RelayConnector().start_registration(
        _session(tmp_path, FakeTransport([answer])), _EMAIL
    )
    assert result == expected


def test_poll_registration_posts_the_poll_secret_in_the_body_only(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([_envelope(RelayCode.REGISTRATION_PENDING)])
    session = _session(tmp_path, transport)
    RelayConnector().poll_registration(session, _started(session))
    (request,) = transport.requests
    assert (request.method, request.url) == (
        "POST",
        _BASE + "/v1/registrations/poll",
    )
    assert request.body == encode_request({"poll_secret": _POLL_SECRET})
    assert request.secret_headers == {}
    assert _POLL_SECRET not in request.url
    assert not any(_POLL_SECRET in v for v in request.headers.values())


@pytest.mark.parametrize(
    "code", [RelayCode.REGISTRATION_PENDING, RelayCode.REGISTRATION_SLOW_DOWN]
)
def test_poll_registration_pending_and_slow_down_carry_no_token(
    tmp_path: Path, code: RelayCode
) -> None:
    session = _session(tmp_path, FakeTransport([_envelope(code)]))
    result = RelayConnector().poll_registration(session, _started(session))
    assert result == RegistrationPolled(code=code, token=None)


def test_poll_registration_issued_carries_the_token_registered_for_redaction(
    tmp_path: Path,
) -> None:
    redactor = Redactor()
    transport = FakeTransport(
        [_envelope(RelayCode.REGISTRATION_ISSUED, {"token": _OTHER_TOKEN})]
    )
    session = _session(tmp_path, transport, redactor=redactor)
    started = _started(session)
    assert redactor.redact(_OTHER_TOKEN) == _OTHER_TOKEN
    result = RelayConnector().poll_registration(session, started)
    assert result == RegistrationPolled(
        code=RelayCode.REGISTRATION_ISSUED, token=Secret(_OTHER_TOKEN)
    )
    assert redactor.redact("t=" + _OTHER_TOKEN) == "t=" + REDACTED


@pytest.mark.parametrize(
    "answer",
    [
        _envelope(RelayCode.REGISTRATION_ISSUED, {"token": "fdr1_short"}),
        _envelope(RelayCode.REGISTRATION_ISSUED, {}),
        _envelope(RelayCode.REGISTRATION_ISSUED, {"token": _OTHER_TOKEN, "x": 1}),
        _envelope(RelayCode.REGISTRATION_PENDING, {"x": 1}),
        _envelope(RelayCode.REGISTRATION_SLOW_DOWN, {"retry_after_s": 1}),
        _envelope(RelayCode.OK),
        _envelope(RelayCode.OK, {"token": _OTHER_TOKEN}),
        _envelope(RelayCode.REGISTRATION_STARTED, _started_data()),
    ],
)
def test_poll_registration_malformed_or_misplaced_answers_are_answer_malformed(
    tmp_path: Path, answer: HttpResponse
) -> None:
    session = _session(tmp_path, FakeTransport([answer]))
    result = RelayConnector().poll_registration(session, _started(session))
    assert result == RelayRefused(RelayCode.ANSWER_MALFORMED, None)


@pytest.mark.parametrize(
    "code",
    [
        RelayCode.REGISTRATION_REFUSED,
        RelayCode.REGISTRATION_EXPIRED,
        RelayCode.NOT_OFFERED,
        RelayCode.UNAVAILABLE,
    ],
)
def test_poll_registration_other_codes_are_refusals(
    tmp_path: Path, code: RelayCode
) -> None:
    session = _session(tmp_path, FakeTransport([_envelope(code)]))
    result = RelayConnector().poll_registration(session, _started(session))
    assert result == RelayRefused(code, None)


def test_poll_registration_rate_limited_states_its_wait(tmp_path: Path) -> None:
    answer = _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 8})
    session = _session(tmp_path, FakeTransport([answer]))
    result = RelayConnector().poll_registration(session, _started(session))
    assert result == RelayRefused(RelayCode.RATE_LIMITED, 8)


def _every_operation(
    session: ConnectorSession,
) -> list[
    tuple[
        str,
        RelayRefused
        | RelayCapabilities
        | RegistrationStarted
        | RegistrationPolled
        | None,
    ]
]:
    connector = RelayConnector()
    started = _started(session)
    return [
        ("check_token", connector.check_token(session, Secret(_TOKEN))),
        ("read_capabilities", connector.read_capabilities(session)),
        ("start_registration", connector.start_registration(session, _EMAIL)),
        ("poll_registration", connector.poll_registration(session, started)),
        ("revoke_token", connector.revoke_token(session, Secret(_TOKEN))),
    ]


def test_every_operation_makes_exactly_one_call_and_maps_unreachable(
    tmp_path: Path,
) -> None:
    script: list[HttpResponse | TransportError] = [
        TransportError("network failure (URLError): " + _BASE) for _ in range(5)
    ]
    transport = FakeTransport(script)
    session = _session(tmp_path, transport)
    results = _every_operation(session)
    assert [name for name, _ in results] == [
        "check_token",
        "read_capabilities",
        "start_registration",
        "poll_registration",
        "revoke_token",
    ]
    assert len(transport.requests) == 5
    assert len({(r.method, r.url) for r in transport.requests}) == 5
    unreachable = RelayRefused(RelayCode.RELAY_UNREACHABLE, None)
    assert [result for _, result in results] == [unreachable] * 5


@pytest.mark.parametrize("status", [429, 503])
def test_an_operation_is_attempted_once_whatever_the_answer(
    tmp_path: Path, status: int
) -> None:
    transport = FakeTransport([_plain(status, b"<html>")])
    session = _session(tmp_path, transport)
    result = RelayConnector().check_token(session, Secret(_TOKEN))
    expected = RelayCode.RATE_LIMITED if status == 429 else RelayCode.UNAVAILABLE
    assert result == RelayRefused(expected, None)
    assert len(transport.requests) == 1


def test_an_operation_given_another_connectors_settings_fails_before_any_request(
    tmp_path: Path,
) -> None:
    transport = FakeTransport([])
    redactor = Redactor()
    session = ConnectorSession(
        instance="relay",
        settings=object(),
        http=_http(transport, redactor),
        credentials=_StubCredentials(),
        data_root=tmp_path,
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
    )
    with pytest.raises(ConnectorError):
        RelayConnector().check_token(session, Secret(_TOKEN))
    assert transport.requests == []


def test_the_loopback_url_reaches_the_transport_unchanged(tmp_path: Path) -> None:
    transport = FakeTransport([_envelope(RelayCode.OK)])
    base = "http://" + "[::1]:8080"
    session = _session(tmp_path, transport, url=base)
    RelayConnector().check_token(session, Secret(_TOKEN))
    assert transport.requests[0].url == base + "/v1/token"
