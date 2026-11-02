"""The wrapper seam (Requirements 4.11, 10.1, 10.2, 10.3, 10.7, 10.8).

Every app here comes from `create_app` with a real config, an injected store and
an injected clock, on both backends. The surface pin renders the seam module's
public statements (and `create_app` / `RelayServices`) and compares them whole
against literals copied from design.md, Seam and AppFactory.
"""

from __future__ import annotations

import ast
import io
import json
import logging
import sys
import textwrap
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.routing import BaseRoute, Host, Mount, Route
from starlette.testclient import TestClient

from fitdocs_relay import app as app_module
from fitdocs_relay import seam
from fitdocs_relay.app import RelayServices, create_app
from fitdocs_relay.config import RelayConfig, load_config
from fitdocs_relay.logs import configure_logging
from fitdocs_relay.routes import core_routes as real_core_routes
from fitdocs_relay.seam import (
    SEAM_VERSION,
    ExtensionContext,
    ExtensionParts,
    IssuedToken,
    PollPending,
    SeamError,
    StartRefused,
    envelope_response,
    load_extensions,
)
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.storage.interface import Storage

PEPPER = "seam-test-pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAeQ"
START = 1_700_000_040
SEAM_SOURCE = Path(seam.__file__)
APP_SOURCE = Path(app_module.__file__)


def envelope(code: str, data: str = "{}") -> bytes:
    return f'{{"envelope":1,"code":"{code}","data":{data}}}'.encode()


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> int:
        return self.now


# --- the surface pin -----------------------------------------------------------

# The public statements of design.md, Seam (its python block), rendered as
# (name, rendering): a class is {decorators, bases, body} with one string per
# body statement ("[@decorator ]def name(args) -> returns" for a method; a
# docstring or `...` is not a statement); an assignment is its unparsed text; a
# function is its signature.
DESIGNED_SEAM: list[tuple[str, Any]] = [
    ("SEAM_VERSION", "SEAM_VERSION: Final = 1"),
    ("EXTENSION_ROUTE_PREFIX", "EXTENSION_ROUTE_PREFIX: Final = '/x/'"),
    (
        "IssuedToken",
        {
            "decorators": ["dataclass(frozen=True)"],
            "bases": [],
            "body": [
                "token_id: str",
                "principal_id: str",
                "token: str = field(repr=False)",
            ],
        },
    ),
    (
        "TokenIssuance",
        {
            "decorators": [],
            "bases": ["Protocol"],
            "body": [
                "def issue(self, *, principal_id: str | None, label: str | None)"
                " -> IssuedToken",
                "def revoke(self, token_id: str) -> bool",
                "def delete_principal(self, principal_id: str) -> bool",
            ],
        },
    ),
    (
        "ExtensionRecords",
        {
            "decorators": [],
            "bases": ["Protocol"],
            "body": [
                "def put(self, key: str, value: bytes, *, ttl_s: int) -> None",
                "def get(self, key: str) -> bytes | None",
                "def take(self, key: str) -> bytes | None",
                "def delete(self, key: str) -> bool",
            ],
        },
    ),
    (
        "StartAccepted",
        {
            "decorators": ["dataclass(frozen=True)"],
            "bases": [],
            "body": [
                "user_code: str",
                "poll_secret: str",
                "interval_s: int",
                "expires_in_s: int",
            ],
        },
    ),
    (
        "StartRefused",
        {"decorators": ["dataclass(frozen=True)"], "bases": [], "body": ["pass"]},
    ),
    (
        "RateLimitedAnswer",
        {
            "decorators": ["dataclass(frozen=True)"],
            "bases": [],
            "body": ["retry_after_s: int"],
        },
    ),
    (
        "PollPending",
        {"decorators": ["dataclass(frozen=True)"], "bases": [], "body": ["pass"]},
    ),
    (
        "PollSlowDown",
        {"decorators": ["dataclass(frozen=True)"], "bases": [], "body": ["pass"]},
    ),
    (
        "PollIssued",
        {
            "decorators": ["dataclass(frozen=True)"],
            "bases": [],
            "body": ["token: IssuedToken"],
        },
    ),
    (
        "PollRefused",
        {"decorators": ["dataclass(frozen=True)"], "bases": [], "body": ["pass"]},
    ),
    (
        "PollExpired",
        {"decorators": ["dataclass(frozen=True)"], "bases": [], "body": ["pass"]},
    ),
    (
        "StartAnswer",
        "StartAnswer = StartAccepted | StartRefused | RateLimitedAnswer",
    ),
    (
        "PollAnswer",
        "PollAnswer = PollPending | PollSlowDown | PollIssued | PollRefused"
        " | PollExpired | RateLimitedAnswer",
    ),
    (
        "RegistrationProvider",
        {
            "decorators": [],
            "bases": ["Protocol"],
            "body": [
                "def start(self, email: str) -> StartAnswer",
                "def poll(self, poll_secret: str) -> PollAnswer",
            ],
        },
    ),
    (
        "ExtensionContext",
        {
            "decorators": ["dataclass(frozen=True)"],
            "bases": [],
            "body": [
                "tokens: TokenIssuance",
                "records: ExtensionRecords",
                "clock: Callable[[], int]",
                "logger: logging.Logger",
            ],
        },
    ),
    (
        "ExtensionParts",
        {
            "decorators": ["dataclass(frozen=True)"],
            "bases": [],
            "body": [
                "routes: tuple[BaseRoute, ...] = ()",
                "registration: RegistrationProvider | None = None",
            ],
        },
    ),
    (
        "RelayExtension",
        {
            "decorators": [],
            "bases": ["Protocol"],
            "body": [
                "@property def name(self) -> str",
                "@property def seam_version(self) -> int",
                "def build(self, context: ExtensionContext) -> ExtensionParts",
            ],
        },
    ),
    (
        "envelope_response",
        "def envelope_response(code: RelayCode, data: Mapping[str, object] | None=None)"
        " -> Response",
    ),
    ("SeamError", {"decorators": [], "bases": ["Exception"], "body": []}),
    (
        "load_extensions",
        "def load_extensions(references: tuple[str, ...])"
        " -> tuple[RelayExtension, ...]",
    ),
]

# The two app.py statements design.md, AppFactory, gives in its python block.
DESIGNED_APP: list[tuple[str, Any]] = [
    (
        "RelayServices",
        {
            "decorators": ["dataclass"],
            "bases": [],
            "body": [
                "storage: Storage",
                "tokens: TokenService",
                "limiter: RateLimiter",
                "clock: Callable[[], int]",
                "registration: RegistrationProvider | None",
                "ready: bool",
            ],
        },
    ),
    (
        "create_app",
        "def create_app(config: RelayConfig, *,"
        " extensions: Sequence[RelayExtension]=(),"
        " storage: Storage | None=None, clock: Callable[[], int] | None=None)"
        " -> Starlette",
    ),
]


def _signature(node: ast.FunctionDef) -> str:
    decorators = "".join(f"@{ast.unparse(d)} " for d in node.decorator_list)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{decorators}def {node.name}({ast.unparse(node.args)}){returns}"


def _render(source: str, only: set[str] | None = None) -> list[tuple[str, Any]]:
    """The public module-level statements of `source` (names not starting with
    an underscore), or only those named in `only`."""
    rendered: list[tuple[str, Any]] = []
    for node in ast.parse(source).body:
        name: str | None = None
        value: Any = None
        if isinstance(node, ast.ClassDef):
            body: list[str] = []
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                    continue
                if isinstance(stmt, ast.FunctionDef):
                    body.append(_signature(stmt))
                else:
                    body.append(ast.unparse(stmt))
            name = node.name
            value = {
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "bases": [ast.unparse(b) for b in node.bases],
                "body": body,
            }
        elif isinstance(node, ast.FunctionDef):
            name, value = node.name, _signature(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, ast.unparse(node)
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name, value = node.targets[0].id, ast.unparse(node)
        if name is None or name.startswith("_"):
            continue
        if only is None or name in only:
            rendered.append((name, value))
    return rendered


def test_the_seam_surface_is_the_designed_one_whole() -> None:
    live = _render(SEAM_SOURCE.read_text(encoding="utf-8"))
    assert len(live) == len(DESIGNED_SEAM), "a statement was rendered or dropped"
    assert [name for name, _ in live] == [name for name, _ in DESIGNED_SEAM]
    assert live == DESIGNED_SEAM


def test_the_app_factory_and_services_are_the_designed_ones_whole() -> None:
    live = _render(
        APP_SOURCE.read_text(encoding="utf-8"), only={"RelayServices", "create_app"}
    )
    assert len(live) == 2, "a statement was rendered or dropped"
    assert sorted(live) == sorted(DESIGNED_APP, key=lambda pair: pair[0])
    assert live == DESIGNED_APP


def test_the_seam_version_is_one() -> None:
    # The literal that every wrapper's declared version is compared against.
    assert SEAM_VERSION == 1
    assert type(SEAM_VERSION) is int


def test_the_seam_pin_can_fail() -> None:
    """The renderer sees a signature change, a dropped member and a new name."""
    source = SEAM_SOURCE.read_text(encoding="utf-8")
    changed = source.replace(
        "def revoke(self, token_id: str) -> bool",
        "def revoke(self, token_id: str, extra: int) -> bool",
        1,
    )
    assert changed != source
    assert _render(changed) != DESIGNED_SEAM
    dropped = source.replace(
        "    def take(self, key: str) -> bytes | None: ...\n", "", 1
    )
    assert dropped != source
    assert _render(dropped) != DESIGNED_SEAM
    assert _render(source + "\nEXTRA: Final = 2\n") != DESIGNED_SEAM
    assert _render(source) == DESIGNED_SEAM


# --- a harness: apps built through create_app -----------------------------------


@dataclass
class Ext:
    """A test extension: records the contexts it was built with."""

    name: str
    seam_version: int = SEAM_VERSION
    make: Callable[[ExtensionContext], ExtensionParts] = lambda context: (
        ExtensionParts()
    )
    contexts: list[ExtensionContext] | None = None

    def build(self, context: ExtensionContext) -> ExtensionParts:
        if self.contexts is None:
            self.contexts = []
        self.contexts.append(context)
        return self.make(context)

    @property
    def context(self) -> ExtensionContext:
        assert self.contexts, f"{self.name} was never built"
        [context] = self.contexts
        return context


def parts(*routes: BaseRoute, registration: Any = None) -> ExtensionParts:
    return ExtensionParts(routes=tuple(routes), registration=registration)


def page(request: Request) -> Response:
    return HTMLResponse("<p>hello</p>")


class Provider:
    def start(self, email: str) -> StartRefused:
        return StartRefused()

    def poll(self, poll_secret: str) -> PollPending:
        return PollPending()


@dataclass
class Built:
    app: Any
    store: Storage
    clock: Clock
    services: RelayServices
    config: RelayConfig


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"]
    saved = [
        (n, list(logging.getLogger(n).handlers), logging.getLogger(n).level)
        for n in names
    ]
    propagate = {n: logging.getLogger(n).propagate for n in names}
    yield
    for name, handlers, level in saved:
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
    for name, value in propagate.items():
        logging.getLogger(name).propagate = value


@pytest.fixture
def build(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., Built]:
    def make(*extensions: Any) -> Built:
        store = open_full_storage()
        clock = Clock()
        loaded = load_config(
            {
                "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
                "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
            }
        )
        config = replace(loaded, database=database_target)
        captured: list[RelayServices] = []
        real = real_core_routes

        def capture(services: RelayServices) -> list[BaseRoute]:
            captured.append(services)
            return real(services)

        monkeypatch.setattr(app_module, "core_routes", capture)
        app = create_app(config, extensions=extensions, storage=store, clock=clock)
        [services] = captured
        return Built(app, store, clock, services, config)

    return make


# --- the refusals ---------------------------------------------------------------


class NoVersion:
    """Valid name and build, but no `seam_version` attribute at all."""

    name = "noversion"

    def build(self, context: ExtensionContext) -> ExtensionParts:
        return ExtensionParts()


class NoName:
    """Right seam version and build, but no `name` attribute at all."""

    seam_version = SEAM_VERSION

    def build(self, context: ExtensionContext) -> ExtensionParts:
        return ExtensionParts()


REFUSALS: list[tuple[str, Callable[[], Sequence[Any]], str]] = [
    (
        "version",
        lambda: [Ext("smoke", seam_version=2)],
        "extension 'smoke': declares a seam version this relay does not implement"
        " (it implements seam version 1)",
    ),
    (
        "version-bool",
        lambda: [Ext("smoke", seam_version=True)],
        "extension 'smoke': declares a seam version this relay does not implement"
        " (it implements seam version 1)",
    ),
    (
        "version-zero",
        lambda: [Ext("smoke", seam_version=0)],
        "extension 'smoke': declares a seam version this relay does not implement"
        " (it implements seam version 1)",
    ),
    (
        "name-uppercase",
        lambda: [Ext("Smoke")],
        "extension 'Smoke': its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-digit-first",
        lambda: [Ext("1smoke")],
        "extension '1smoke': its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-empty",
        lambda: [Ext("")],
        "extension '': its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-33-characters",
        lambda: [Ext("a" * 33)],
        f"extension '{'a' * 33}': its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-trailing-newline",
        lambda: [Ext("smoke\n")],
        "extension 'smoke\\n': its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-underscore",
        lambda: [Ext("sm_oke")],
        "extension 'sm_oke': its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-not-text",
        lambda: [Ext(5)],  # type: ignore[arg-type]
        "extension <int>: its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "name-long-is-cut-in-the-message",
        lambda: [Ext("a" * 60)],
        f"extension '{'a' * 49}: its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "no-seam-version-attribute",
        lambda: [NoVersion()],
        "extension 'noversion': declares a seam version this relay does not implement"
        " (it implements seam version 1)",
    ),
    (
        "no-name-attribute",
        lambda: [NoName()],
        "extension <NoneType>: its name is not 1 to 32 characters of lowercase"
        " letters, digits and hyphens, starting with a letter",
    ),
    (
        "duplicate",
        lambda: [Ext("smoke"), Ext("other"), Ext("smoke")],
        "extension 'smoke': its name is already used by another extension",
    ),
    (
        "route-outside-prefix",
        lambda: [Ext("smoke", make=lambda c: parts(Route("/v1/extra", page)))],
        "extension 'smoke': adds a route outside /x/smoke/",
    ),
    (
        "route-core-path",
        lambda: [Ext("smoke", make=lambda c: parts(Route("/livez", page)))],
        "extension 'smoke': adds a route outside /x/smoke/",
    ),
    (
        "route-no-trailing-slash",
        lambda: [Ext("smoke", make=lambda c: parts(Route("/x/smoke", page)))],
        "extension 'smoke': adds a route outside /x/smoke/",
    ),
    (
        "route-another-extensions-prefix",
        lambda: [
            Ext("smoke"),
            Ext("other", make=lambda c: parts(Route("/x/smoke/page", page))),
        ],
        "extension 'other': adds a route outside /x/other/",
    ),
    (
        "route-longer-name-shares-the-prefix-text",
        lambda: [Ext("smoke", make=lambda c: parts(Route("/x/smokey/page", page)))],
        "extension 'smoke': adds a route outside /x/smoke/",
    ),
    (
        "route-one-bad-among-good",
        lambda: [
            Ext(
                "smoke",
                make=lambda c: parts(
                    Route("/x/smoke/a", page), Route("/elsewhere", page)
                ),
            )
        ],
        "extension 'smoke': adds a route outside /x/smoke/",
    ),
    (
        "route-without-a-path",
        lambda: [
            Ext(
                "smoke",
                make=lambda c: parts(Host("example.org", PlainTextResponse("x"))),
            )
        ],
        "extension 'smoke': adds a route outside /x/smoke/",
    ),
    (
        "second-provider",
        lambda: [
            Ext("first", make=lambda c: parts(registration=Provider())),
            Ext("second", make=lambda c: parts(registration=Provider())),
        ],
        "extension 'second': installs a registration provider, but extension"
        " 'first' already installed one",
    ),
    (
        "parts-not-extension-parts",
        lambda: [Ext("smoke", make=lambda c: ())],  # type: ignore[arg-type,return-value]
        "extension 'smoke': build did not return ExtensionParts",
    ),
]


@pytest.mark.parametrize(
    ("label", "extensions", "message"), REFUSALS, ids=[r[0] for r in REFUSALS]
)
def test_the_app_factory_refuses_naming_the_extension_and_the_reason(
    build: Callable[..., Built],
    label: str,
    extensions: Callable[[], Sequence[Any]],
    message: str,
) -> None:
    with pytest.raises(SeamError) as raised:
        build(*extensions())
    assert str(raised.value) == message


def test_a_refused_version_is_not_built(build: Callable[..., Built]) -> None:
    wrong = Ext("smoke", seam_version=2)
    with pytest.raises(SeamError):
        build(wrong)
    assert wrong.contexts is None


def test_the_refusals_are_not_vacuous_a_good_set_builds(
    build: Callable[..., Built],
) -> None:
    built = build(
        Ext("first", make=lambda c: parts(Route("/x/first/a", page))),
        Ext("second-1", make=lambda c: parts(Route("/x/second-1/b", page))),
        Ext("a", make=lambda c: parts(Mount("/x/a/m", routes=[Route("/p", page)]))),
        Ext("p", make=lambda c: parts(registration=Provider())),
    )
    assert built.services.registration is not None
    assert len(REFUSALS) == 23


def test_every_name_the_pattern_admits_is_admitted(
    build: Callable[..., Built],
) -> None:
    for name in ("a", "a" * 32, "a-b-1", "z9"):
        build(Ext(name))


def test_a_refusal_closes_a_store_the_factory_opened(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = open_full_storage()
    closed: list[bool] = []
    real_close = store.close

    def close() -> None:
        closed.append(True)
        real_close()

    monkeypatch.setattr(store, "close", close)
    monkeypatch.setattr(app_module, "open_storage", lambda target: store)
    config = replace(
        load_config(
            {
                "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
                "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
            }
        ),
        database=database_target,
    )
    with pytest.raises(SeamError):
        create_app(config, extensions=[Ext("Bad")])
    assert closed == [True]
    # A store the caller injected stays the caller's.
    closed.clear()
    with pytest.raises(SeamError):
        create_app(config, extensions=[Ext("Bad")], storage=store)
    assert closed == []


def test_a_build_that_raises_propagates_and_closes_only_a_store_the_factory_opened(
    database_target: Any,
    open_full_storage: Callable[[], Storage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = open_full_storage()
    closed: list[bool] = []
    real_close = store.close

    def close() -> None:
        closed.append(True)
        real_close()

    monkeypatch.setattr(store, "close", close)
    monkeypatch.setattr(app_module, "open_storage", lambda target: store)
    config = replace(
        load_config(
            {
                "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
                "FITDOCS_RELAY_TOKEN_PEPPER": PEPPER,
            }
        ),
        database=database_target,
    )

    def explode(context: ExtensionContext) -> ExtensionParts:
        raise RuntimeError("build blew up")

    with pytest.raises(RuntimeError, match="^build blew up$"):
        create_app(config, extensions=[Ext("smoke", make=explode)])
    assert closed == [True]
    closed.clear()
    with pytest.raises(RuntimeError, match="^build blew up$"):
        create_app(config, extensions=[Ext("smoke", make=explode)], storage=store)
    assert closed == []


# --- extension routes: served under their prefix, outside the envelope -----------


def test_an_extension_route_is_served_under_its_prefix_outside_the_envelope(
    build: Callable[..., Built],
) -> None:
    built = build(
        Ext(
            "smoke",
            make=lambda c: parts(
                Route("/x/smoke/page", page),
                Mount("/x/smoke/m", routes=[Route("/deep/{n}", page)]),
            ),
        )
    )
    with TestClient(built.app) as client:
        sent = client.get("/x/smoke/page")
        mounted = client.get("/x/smoke/m/deep/7")
        missing = client.get("/x/smoke/absent")
        wrong_method = client.post("/x/smoke/page")
    assert (sent.status_code, sent.content) == (200, b"<p>hello</p>")
    assert sent.headers["content-type"].startswith("text/html")
    assert "cache-control" not in sent.headers  # not an envelope answer
    assert (mounted.status_code, mounted.content) == (200, b"<p>hello</p>")
    # An unrouted path under the prefix is still the relay's `not-offered`.
    assert (missing.status_code, missing.content) == (404, envelope("not-offered"))
    assert (wrong_method.status_code, wrong_method.content) == (
        404,
        envelope("not-offered"),
    )


def test_an_extension_route_is_not_versioned_or_gated_on_readiness(
    build: Callable[..., Built],
) -> None:
    built = build(Ext("smoke", make=lambda c: parts(Route("/x/smoke/page", page))))
    # Without the lifespan the store has not been checked: not ready.
    client = TestClient(built.app)
    assert built.services.ready is False
    gated = client.get("/v1/token")
    assert (gated.status_code, gated.content) == (503, envelope("unavailable"))
    sent = client.get("/x/smoke/page")
    assert (sent.status_code, sent.content) == (200, b"<p>hello</p>")
    # No version prefix is accepted in front of an extension route.
    versioned = client.get("/v1/x/smoke/page")
    assert (versioned.status_code, versioned.content) == (404, envelope("not-offered"))
    unsupported = client.get("/v9/x/smoke/page")
    assert unsupported.content == envelope("envelope-unsupported", '{"envelopes":[1]}')


def test_an_extension_route_is_logged_by_its_template(
    build: Callable[..., Built],
) -> None:
    out = io.StringIO()
    configure_logging(pepper=PEPPER, password="seam-db-passw0rd", stream=out)
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    built = build(
        Ext("smoke", make=lambda c: parts(Route("/x/smoke/item/{item}", page)))
    )
    with TestClient(built.app) as client:
        client.get("/x/smoke/item/ITEM-SENTINEL")
    [record] = [json.loads(line) for line in out.getvalue().splitlines()]
    assert record["route"] == "/x/smoke/item/{item}"
    assert record["status"] == 200
    assert record["code"] is None
    assert "ITEM-SENTINEL" not in out.getvalue()


def test_the_relay_still_owns_its_own_paths_with_an_extension_installed(
    build: Callable[..., Built],
) -> None:
    built = build(Ext("smoke", make=lambda c: parts(Route("/x/smoke/page", page))))
    with TestClient(built.app) as client:
        assert client.get("/livez").content == envelope("ok")
        assert client.get("/v1/capabilities").status_code == 200


# --- the context --------------------------------------------------------------


def test_the_context_carries_the_services_clock_the_provider_and_a_named_logger(
    build: Callable[..., Built],
) -> None:
    provider = Provider()
    ext = Ext("smoke", make=lambda c: parts(registration=provider))
    other = Ext("other")
    built = build(ext, other)
    assert built.services.registration is provider
    assert ext.context.clock is built.services.clock
    assert ext.context.clock() == START
    assert ext.context.logger.name == "fitdocs_relay.extension.smoke"
    assert other.context.logger.name == "fitdocs_relay.extension.other"
    assert other.context.records is not ext.context.records


def test_without_a_provider_the_services_hold_none(
    build: Callable[..., Built],
) -> None:
    assert build().services.registration is None
    assert build(Ext("smoke")).services.registration is None


# --- the envelope helper ------------------------------------------------------


def test_the_envelope_helper_builds_the_relay_answer() -> None:
    sent = envelope_response(RelayCode.OK, {"n": 1})
    assert sent.status_code == 200
    assert sent.body == envelope("ok", '{"n":1}')
    assert sent.headers["cache-control"] == "no-store"
    assert envelope_response(RelayCode.NOT_OFFERED).body == envelope("not-offered")
    with pytest.raises(ValueError):
        envelope_response(RelayCode.RELAY_UNREACHABLE)


def test_an_extension_can_answer_with_the_envelope(
    build: Callable[..., Built],
) -> None:
    def hello(request: Request) -> Response:
        return envelope_response(RelayCode.OK, {"hello": "x"})

    built = build(Ext("smoke", make=lambda c: parts(Route("/x/smoke/hello", hello))))
    with TestClient(built.app) as client:
        sent = client.get("/x/smoke/hello")
    assert (sent.status_code, sent.content) == (200, envelope("ok", '{"hello":"x"}'))


# --- token issuance, through the same service the operator uses -------------------


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_issued_tokens_authenticate_through_the_relay_routes(
    build: Callable[..., Built],
) -> None:
    ext = Ext("smoke")
    built = build(ext)
    issued = ext.context.tokens.issue(principal_id=None, label="phone")
    assert isinstance(issued, IssuedToken)
    assert issued.token.startswith("fdr1_")
    assert issued.token not in repr(issued)
    # The same service the routes authenticate with.
    outcome = built.services.tokens.authenticate(issued.token)
    assert (outcome.token_id, outcome.principal_id) == (  # type: ignore[union-attr]
        issued.token_id,
        issued.principal_id,
    )
    stored = built.store.get_principal(issued.principal_id)
    assert stored is not None and stored.label is None
    [summary] = built.store.list_tokens(issued.principal_id)
    assert (summary.token_id, summary.label) == (issued.token_id, "phone")
    altered = issued.token[:-1] + ("a" if issued.token[-1] != "a" else "b")
    with TestClient(built.app) as client:
        ok = client.get("/v1/token", headers=bearer(issued.token))
        wrong = client.get("/v1/token", headers=bearer(altered))
    assert (ok.status_code, ok.content) == (200, envelope("ok"))
    assert wrong.content == envelope("token-unknown")


def test_a_second_token_for_an_existing_principal_and_revocation(
    build: Callable[..., Built],
) -> None:
    ext = Ext("smoke")
    built = build(ext)
    tokens = ext.context.tokens
    first = tokens.issue(principal_id=None, label=None)
    second = tokens.issue(principal_id=first.principal_id, label="b")
    assert second.principal_id == first.principal_id
    assert second.token_id != first.token_id
    assert tokens.revoke(first.token_id) is True
    assert tokens.revoke(first.token_id) is True  # already revoked: still known
    assert tokens.revoke("z" * 16) is False
    with TestClient(built.app) as client:
        revoked = client.get("/v1/token", headers=bearer(first.token))
        alive = client.get("/v1/token", headers=bearer(second.token))
    assert revoked.content == envelope("token-revoked")
    assert alive.content == envelope("ok")


def test_deleting_a_principal_unmakes_its_tokens(build: Callable[..., Built]) -> None:
    ext = Ext("smoke")
    built = build(ext)
    tokens = ext.context.tokens
    issued = tokens.issue(principal_id=None, label=None)
    assert tokens.delete_principal(issued.principal_id) is True
    assert tokens.delete_principal(issued.principal_id) is False
    with TestClient(built.app) as client:
        gone = client.get("/v1/token", headers=bearer(issued.token))
    assert gone.content == envelope("token-unknown")


# --- records: namespaced, bounded, expiring -----------------------------------------


def two(
    build: Callable[..., Built],
) -> tuple[Built, ExtensionContext, ExtensionContext]:
    a, b = Ext("alpha"), Ext("beta")
    built = build(a, b)
    return built, a.context, b.context


def test_records_are_isolated_per_extension_name(build: Callable[..., Built]) -> None:
    _, a, b = two(build)
    a.records.put("k", b"from-a", ttl_s=100)
    # B sees nothing of A's record, whatever it does with the key.
    assert b.records.get("k") is None
    assert b.records.take("k") is None
    assert b.records.delete("k") is False
    assert a.records.get("k") == b"from-a"
    b.records.put("k", b"from-b", ttl_s=100)
    assert a.records.get("k") == b"from-a"
    assert b.records.get("k") == b"from-b"
    # A takes its own; B's survives, and A's delete leaves B's alone.
    assert a.records.take("k") == b"from-a"
    assert a.records.get("k") is None
    assert b.records.get("k") == b"from-b"
    a.records.put("k", b"again", ttl_s=100)
    assert a.records.delete("k") is True
    assert a.records.delete("k") is False
    assert b.records.get("k") == b"from-b"
    assert b.records.delete("k") is True


def test_a_record_lands_in_the_extension_namespace_in_the_database(
    build: Callable[..., Built],
) -> None:
    built, a, b = two(build)
    a.records.put("k", b"A", ttl_s=100)
    assert built.store.get_record(namespace="alpha", key="k", now=START) == b"A"
    assert built.store.get_record(namespace="beta", key="k", now=START) is None
    b.records.put("k", b"B", ttl_s=100)
    assert built.store.take_record(namespace="beta", key="k", now=START) == b"B"
    assert built.store.get_record(namespace="alpha", key="k", now=START) == b"A"


def test_take_returns_a_record_once(build: Callable[..., Built]) -> None:
    _, a, _ = two(build)
    a.records.put("k", b"v", ttl_s=100)
    assert a.records.take("k") == b"v"
    assert a.records.take("k") is None


def test_a_record_expires_ttl_seconds_after_the_clock_read_at_put(
    build: Callable[..., Built],
) -> None:
    built, a, _ = two(build)
    a.records.put("k", b"v", ttl_s=10)
    built.clock.now = START + 9
    assert a.records.get("k") == b"v"
    built.clock.now = START + 10
    assert a.records.get("k") is None
    built.clock.now = START + 5
    a.records.put("j", b"w", ttl_s=1)
    built.clock.now = START + 5
    assert a.records.get("j") == b"w"
    built.clock.now = START + 6
    assert a.records.get("j") is None


def test_a_put_purges_expired_records_as_of_the_clock(
    build: Callable[..., Built],
) -> None:
    built, a, _ = two(build)
    a.records.put("old", b"v", ttl_s=1)
    assert built.store.get_record(namespace="alpha", key="old", now=START) == b"v"
    built.clock.now = START + 1
    a.records.put("new", b"w", ttl_s=100)
    # The expired row is physically gone, not merely hidden from reads.
    assert built.store.delete_record(namespace="alpha", key="old") is False
    assert a.records.get("new") == b"w"


def test_a_put_replaces_the_value_and_the_expiry(build: Callable[..., Built]) -> None:
    built, a, _ = two(build)
    a.records.put("k", b"old", ttl_s=10)
    a.records.put("k", b"new", ttl_s=100)
    built.clock.now = START + 50
    assert a.records.get("k") == b"new"


KEY_MAX = 128
VALUE_MAX = 4096
TTL_MIN = 1
TTL_MAX = 2_592_000


def test_the_key_bound_is_128_characters_both_sides(
    build: Callable[..., Built],
) -> None:
    _, a, _ = two(build)
    a.records.put("k" * KEY_MAX, b"v", ttl_s=10)
    assert a.records.get("k" * KEY_MAX) == b"v"
    # Characters, not bytes: 128 two-byte characters fit.
    a.records.put("é" * KEY_MAX, b"w", ttl_s=10)
    assert a.records.get("é" * KEY_MAX) == b"w"
    with pytest.raises(ValueError, match="^a record key is 0 to 128 characters$"):
        a.records.put("k" * (KEY_MAX + 1), b"v", ttl_s=10)
    assert a.records.get("k" * KEY_MAX) == b"v"


@pytest.mark.parametrize("operation", ["get", "take", "delete"])
def test_a_key_over_the_bound_is_refused_by_every_operation(
    build: Callable[..., Built], operation: str
) -> None:
    _, a, _ = two(build)
    call = getattr(a.records, operation)
    call("k" * KEY_MAX)  # at the bound: allowed
    with pytest.raises(ValueError, match="^a record key is 0 to 128 characters$"):
        call("k" * (KEY_MAX + 1))


def test_a_key_must_be_text(build: Callable[..., Built]) -> None:
    _, a, _ = two(build)
    with pytest.raises(ValueError, match="^a record key is 0 to 128 characters$"):
        a.records.put(b"k", b"v", ttl_s=10)  # type: ignore[arg-type]


def test_the_value_bound_is_4096_bytes_both_sides(build: Callable[..., Built]) -> None:
    _, a, _ = two(build)
    a.records.put("k", b"v" * VALUE_MAX, ttl_s=10)
    assert a.records.get("k") == b"v" * VALUE_MAX
    a.records.put("empty", b"", ttl_s=10)
    assert a.records.get("empty") == b""
    with pytest.raises(ValueError, match="^a record value is 0 to 4096 bytes$"):
        a.records.put("big", b"v" * (VALUE_MAX + 1), ttl_s=10)
    assert a.records.get("big") is None
    with pytest.raises(ValueError, match="^a record value is 0 to 4096 bytes$"):
        a.records.put("text", "text", ttl_s=10)  # type: ignore[arg-type]
    assert a.records.get("text") is None


def test_the_expiry_bound_is_1_to_2592000_seconds_both_sides(
    build: Callable[..., Built],
) -> None:
    built, a, _ = two(build)
    a.records.put("low", b"v", ttl_s=TTL_MIN)
    a.records.put("high", b"v", ttl_s=TTL_MAX)
    built.clock.now = START + TTL_MAX - 1
    assert a.records.get("high") == b"v"
    built.clock.now = START + TTL_MAX
    assert a.records.get("high") is None
    message = "^a record expiry is 1 to 2592000 seconds$"
    for bad in (TTL_MIN - 1, TTL_MAX + 1, -5):
        with pytest.raises(ValueError, match=message):
            a.records.put("bad", b"v", ttl_s=bad)
    with pytest.raises(ValueError, match=message):
        a.records.put("bad", b"v", ttl_s=True)
    with pytest.raises(ValueError, match=message):
        a.records.put("bad", b"v", ttl_s=1.5)  # type: ignore[arg-type]
    built.clock.now = START
    assert a.records.get("bad") is None


def test_a_refused_put_leaves_an_existing_record_alone(
    build: Callable[..., Built],
) -> None:
    _, a, _ = two(build)
    a.records.put("k", b"keep", ttl_s=100)
    with pytest.raises(ValueError):
        a.records.put("k", b"x" * (VALUE_MAX + 1), ttl_s=100)
    with pytest.raises(ValueError):
        a.records.put("k", b"x", ttl_s=0)
    assert a.records.get("k") == b"keep"


# --- loading from the configured references ---------------------------------------


@pytest.fixture
def module_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "wrapper_modules"
    directory.mkdir()
    monkeypatch.syspath_prepend(str(directory))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    return directory


def write_module(directory: Path, name: str, source: str) -> None:
    (directory / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")


def test_references_are_loaded_in_order(
    module_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_module(
        module_dir,
        "seam_wrap_one",
        """
        class Thing:
            name = "one"
            seam_version = 1
            def build(self, context):
                return None
        first = Thing()
        class Holder:
            inner = Thing()
        """,
    )
    write_module(
        module_dir,
        "seam_wrap_two",
        """
        class Other:
            name = "two"
            seam_version = 1
            def build(self, context):
                return None
        second = Other()
        """,
    )
    for module in ("seam_wrap_one", "seam_wrap_two"):
        monkeypatch.delitem(sys.modules, module, raising=False)
    loaded = load_extensions(
        (
            "seam_wrap_two:second",
            "seam_wrap_one:first",
            "seam_wrap_one:Holder.inner",
        )
    )
    assert [e.name for e in loaded] == ["two", "one", "one"]
    assert isinstance(loaded, tuple)
    one = sys.modules["seam_wrap_one"]
    assert loaded[1] is one.first
    assert loaded[2] is one.Holder.inner
    assert loaded[2] is not loaded[1]
    for module in ("seam_wrap_one", "seam_wrap_two"):
        monkeypatch.delitem(sys.modules, module, raising=False)


def test_no_references_load_nothing() -> None:
    assert load_extensions(()) == ()


def test_a_reference_that_cannot_be_loaded_is_refused_naming_it(
    module_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_module(module_dir, "seam_wrap_ok", "thing = 1\n")
    write_module(module_dir, "seam_wrap_boom", "raise RuntimeError('SECRET-DETAIL')\n")
    for module in ("seam_wrap_ok", "seam_wrap_boom"):
        monkeypatch.delitem(sys.modules, module, raising=False)
    cases = [
        (
            "seam_wrap_absent:thing",
            "extension reference 'seam_wrap_absent:thing': the module could not be"
            " imported (ModuleNotFoundError)",
        ),
        (
            "seam_wrap_boom:thing",
            "extension reference 'seam_wrap_boom:thing': the module could not be"
            " imported (RuntimeError)",
        ),
        (
            "seam_wrap_ok:missing",
            "extension reference 'seam_wrap_ok:missing': the module has no such"
            " attribute",
        ),
        (
            "seam_wrap_ok:thing.deeper",
            "extension reference 'seam_wrap_ok:thing.deeper': the module has no such"
            " attribute",
        ),
        (
            "no-colon",
            "extension reference 'no-colon': not a module:attribute reference",
        ),
        (
            ":attr",
            "extension reference ':attr': not a module:attribute reference",
        ),
        (
            "mod:",
            "extension reference 'mod:': not a module:attribute reference",
        ),
    ]
    for reference, message in cases:
        with pytest.raises(SeamError) as raised:
            load_extensions((reference,))
        assert str(raised.value) == message
        assert "SECRET-DETAIL" not in str(raised.value)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None or raised.value.__suppress_context__
    # Loading one good and one bad reference refuses the whole set.
    with pytest.raises(SeamError):
        load_extensions(("seam_wrap_ok:thing", "seam_wrap_ok:missing"))
    for module in ("seam_wrap_ok", "seam_wrap_boom"):
        monkeypatch.delitem(sys.modules, module, raising=False)


def test_loaded_extensions_install_through_the_factory(
    module_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    build: Callable[..., Built],
) -> None:
    write_module(
        module_dir,
        "seam_wrap_live",
        """
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from fitdocs_relay.seam import ExtensionParts

        def hello(request):
            return PlainTextResponse("hi from wrapper")

        class Live:
            name = "live"
            seam_version = 1
            def build(self, context):
                return ExtensionParts(routes=(Route("/x/live/hello", hello),))

        extension = Live()
        """,
    )
    monkeypatch.delitem(sys.modules, "seam_wrap_live", raising=False)
    built = build(*load_extensions(("seam_wrap_live:extension",)))
    with TestClient(built.app) as client:
        sent = client.get("/x/live/hello")
    assert (sent.status_code, sent.content) == (200, b"hi from wrapper")
    monkeypatch.delitem(sys.modules, "seam_wrap_live", raising=False)


def test_the_app_factory_default_installs_no_extension(
    build: Callable[..., Built],
) -> None:
    built = build()
    with TestClient(built.app) as client:
        assert client.get("/x/anything/page").content == envelope("not-offered")
