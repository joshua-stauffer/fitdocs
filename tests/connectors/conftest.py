"""Environment isolation shared by every test under ``tests/connectors``.

Two autouse fixtures run before every test in this package:

* :func:`_forbid_network_sockets` patches :class:`socket.socket` so
  constructing one raises. Every connector test must reach the transport
  through ``FakeTransport`` (added in a later task) or a patched
  ``urllib.request.urlopen`` -- never a real socket.
* :func:`_isolated_connector_environment` calls
  :func:`isolate_connector_environment` with a fresh
  ``tmp_path_factory.mktemp("connector-env")`` tree -- deliberately not the
  test's own ``tmp_path``, since a test may use ``tmp_path`` as the sandbox
  data root it builds, and the isolation location must sit outside any data
  root a test constructs. ``isolate_connector_environment`` itself is a
  plain helper (not a fixture), so other test modules outside this package
  -- in particular ``tests/test_confinement.py`` (task 6.3), which sits
  outside this conftest's reach -- can import and call it directly, passing
  their own base directory, to get the same isolation locally.

:class:`FakeTransport` (task 2.1) is the scripted :data:`fitdocs.connectors.
http.Transport` every ``HttpClient`` test and later connector test sends
through instead of ``urllib_transport``: a fixed script of
``HttpResponse``/``TransportError`` values, one per call, consumed in order;
every call is recorded (the request and the timeout it was given).
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import NoReturn, TypeVar

import pytest

from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.http import HttpRequest, HttpResponse, TransportError
from fitdocs.connectors.protocol import (
    ActivityPuller,
    AuthStyle,
    Capability,
    Connector,
    ConnectorSession,
    CredentialField,
    FetchResult,
    Granted,
    KeyVerifier,
    Listing,
    RemoteActivity,
    SettingsContext,
    TokenIssuer,
    TokenSet,
)
from fitdocs.connectors.secrets import Secret

_T = TypeVar("_T")


def isolate_connector_environment(
    monkeypatch: pytest.MonkeyPatch, base_dir: Path
) -> None:
    """Point credential/config lookups at a throwaway location under ``base_dir``.

    Creates ``<base_dir>/credentials-dir`` and ``<base_dir>/home``, points
    ``FITDOCS_CREDENTIALS_DIR`` and ``HOME`` at them, and deletes
    ``XDG_CONFIG_HOME`` and every ``FITDOCS_CONNECTOR_*`` variable -- including
    ones already set before this call -- so a developer's real credentials or
    environment overrides can neither be read nor change a test's outcome.

    The caller chooses ``base_dir``; it must sit outside any sandbox data root
    a test itself builds (the autouse fixture below passes a fresh
    ``tmp_path_factory.mktemp("connector-env")`` tree for exactly this
    reason, distinct from a test's own ``tmp_path``).
    """
    credentials_dir = base_dir / "credentials-dir"
    credentials_dir.mkdir(parents=True, exist_ok=True)
    home_dir = base_dir / "home"
    home_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("FITDOCS_CREDENTIALS_DIR", str(credentials_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for name in list(os.environ):
        if name.startswith("FITDOCS_CONNECTOR_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _forbid_network_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("tests/connectors must not open a real network socket")

    monkeypatch.setattr(socket, "socket", _raise)


@pytest.fixture(autouse=True)
def _isolated_connector_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    base_dir = tmp_path_factory.mktemp("connector-env")
    isolate_connector_environment(monkeypatch, base_dir)


class FakeTransport:
    """A scripted :data:`fitdocs.connectors.http.Transport`.

    ``script`` supplies one outcome per call, in order: an
    :class:`~fitdocs.connectors.http.HttpResponse` is returned, a
    :class:`~fitdocs.connectors.http.TransportError` instance is raised.
    Every call is recorded in :attr:`requests` (the exact
    :class:`~fitdocs.connectors.http.HttpRequest` handed to this transport)
    and :attr:`timeouts` (the timeout given alongside it), so a test can
    inspect what ``HttpClient`` actually sent on each attempt.
    """

    def __init__(self, script: list[HttpResponse | TransportError]) -> None:
        self._script = list(script)
        self.requests: list[HttpRequest] = []
        self.timeouts: list[float] = []

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if not self._script:
            raise AssertionError("FakeTransport script exhausted")
        outcome = self._script.pop(0)
        if isinstance(outcome, TransportError):
            raise outcome
        return outcome


# ---------------------------------------------------------------------------
# Registry isolation (task 2.3)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_connector_registry() -> Iterator[None]:
    """Snapshot the connector registry before each test and restore it after.

    ``connectors/registry.py`` is a module-level, process-wide dict: without
    this, a test that registers or unregisters a connector would leak that
    change into every later test in the run, in whatever order the test
    suite happens to execute them in. The snapshot is a plain ``dict`` copy
    (registration order is a dict's iteration order, which ``dict(...)``
    preserves).

    Restoration mutates the existing dict object in place
    (``.clear()``/``.update()``) rather than rebinding
    ``connector_registry._REGISTRY`` to a new object. ``register``,
    ``unregister``, and ``get`` all read ``_REGISTRY`` fresh from the module's
    globals on every call -- they do not close over it -- so today a
    reassignment would restore the same observable state just as well. The
    in-place mutation is deliberately more defensive than that: it also
    restores correctly for any future accessor that captured a direct
    reference to the dict object itself (e.g. a local bound to
    ``connector_registry._REGISTRY``, or a module-level alias) rather than
    going through ``connector_registry.<name>`` on every access -- a
    reassignment here would leave such a reference pointing at the stale,
    un-restored dict.
    """
    snapshot = dict(connector_registry._REGISTRY)
    try:
        yield
    finally:
        connector_registry._REGISTRY.clear()
        connector_registry._REGISTRY.update(snapshot)


class UnscriptedCall(BaseException):
    """Raised when a synthetic connector's operation is called with no
    scripted answer queued.

    Deliberately subclasses :class:`BaseException`, not :class:`Exception`:
    an operation call a test never expected must propagate through any
    ``except Exception`` boundary it passes through on the way out --
    ``registry.validate_connector``'s broad boundary around a raising
    property included -- rather than being absorbed and reported as an
    ordinary connector failure (a malformed-declaration reason string, or a
    caught-and-isolated per-connector error in a later engine). A test that
    asserts "this was never called" must see this exception itself, not a
    downstream value that merely happens to differ from what a real call
    would have produced.
    """


def _consume_script(script: list[_T | BaseException], *, description: str) -> _T:
    """Pop and return the next scripted answer, or raise it if it is an
    exception; raise :class:`UnscriptedCall` naming ``description`` when the
    script is empty.
    """
    if not script:
        raise UnscriptedCall(description)
    outcome = script.pop(0)
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


# ---------------------------------------------------------------------------
# Typed synthetic connectors (task 2.3), reused by every later connector task.
#
# ``verify``, ``login``, ``refresh``, and ``list_activities`` all pop their
# answer through :func:`_consume_script`; ``fetch_activity`` inlines the same
# three outcomes itself (see its own docstring for why it cannot call
# :func:`_consume_script` directly). In every case: a queued ordinary value
# is returned, a queued ``BaseException`` instance (e.g. an ``AuthFailure``)
# is raised as scripted, and an empty script raises :class:`UnscriptedCall`.
# Because ``UnscriptedCall`` is a ``BaseException`` rather than an
# ``Exception``, a test asserting a code path never calls an operation
# observes that exception escape unmodified -- it is not caught and
# converted into an ordinary reason string by
# ``registry.validate_connector``'s ``except Exception`` boundary, nor could
# it be absorbed by any future per-connector ``except Exception`` isolation.
# ---------------------------------------------------------------------------


class _ScriptedActivityPullerMixin:
    """Shared ``PULL_ACTIVITIES`` behavior: scripted
    ``list_activities``/``fetch_activity`` answers (``list_activities``
    through :func:`_consume_script`; ``fetch_activity`` inlines the same
    pop-or-raise logic), plus an optional ``data_url`` request through
    ``session.http.get``.

    Mixed into every synthetic connector that may need to declare
    ``PULL_ACTIVITIES`` -- ``ScriptedPuller`` always, and
    ``ScriptedPersonalKeyConnector``/``ScriptedLoginConnector`` when a test
    overrides their ``capabilities`` to include it -- so that overriding
    ``capabilities`` to add ``PULL_ACTIVITIES`` produces a connector that
    actually *validates* (the capability's required operations are present)
    and can actually pull, not merely one that declares the capability and
    fails ``registry.validate_connector``.
    """

    def _init_activity_puller(self, *, data_url: str | None = None) -> None:
        self.data_url = data_url
        self.listing_script: list[Listing | BaseException] = []
        self.fetch_script: list[FetchResult | BaseException] = []
        self.list_calls: list[datetime | None] = []
        self.fetch_calls: list[RemoteActivity] = []
        self.http_responses: list[HttpResponse] = []

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        self.list_calls.append(since)
        if self.data_url is not None:
            self.http_responses.append(session.http.get(self.data_url))
        return _consume_script(
            self.listing_script,
            description=(
                f"{type(self).__name__}.list_activities called with no scripted answer"
            ),
        )

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        self.fetch_calls.append(activity)
        # Kept separate from _consume_script (unlike every other
        # operation-serving method here): FetchResult is itself a union
        # (Fetched | Declined | Deferred), and mypy cannot solve
        # _consume_script's generic T | BaseException parameter for a T that
        # is already a union -- neither a plain call nor a `cast(FetchResult,
        # ...)` around it resolves the "Cannot infer value of type parameter"
        # error. The logic below is _consume_script's, inlined: pop and
        # return an ordinary value, raise a queued BaseException as
        # scripted, raise UnscriptedCall when nothing is queued.
        if not self.fetch_script:
            raise UnscriptedCall(
                f"{type(self).__name__}.fetch_activity called with no scripted answer"
            )
        outcome = self.fetch_script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ScriptedPersonalKeyConnector(_ScriptedActivityPullerMixin):
    """A synthetic ``API_KEY``-style connector (Req 2.2-2.8).

    ``capabilities`` defaults to a single non-driven capability so a test
    that only needs an ``API_KEY`` connector need not think about
    ``PULL_ACTIVITIES``; a caller that overrides it to include
    ``PULL_ACTIVITIES`` (task 4.4) gets a connector that also implements
    ``list_activities``/``fetch_activity`` (via
    :class:`_ScriptedActivityPullerMixin`), so it validates and can pull.
    """

    connector_id = "personal-key"
    display_name = "Personal Key"
    auth_style = AuthStyle.API_KEY
    credential_fields = (CredentialField("api_key", "API Key", secret=True),)

    def __init__(
        self,
        *,
        capabilities: frozenset[Capability] | None = None,
        data_url: str | None = None,
    ) -> None:
        self.capabilities = (
            capabilities
            if capabilities is not None
            else frozenset({Capability.PULL_THRESHOLDS})
        )
        self._init_activity_puller(data_url=data_url)
        self.verify_script: list[Granted | BaseException] = []
        self.verify_calls: list[Mapping[str, Secret]] = []
        self.parse_settings_calls: int = 0

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object:
        self.parse_settings_calls += 1
        return None

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted:
        self.verify_calls.append(values)
        return _consume_script(
            self.verify_script,
            description=(
                "ScriptedPersonalKeyConnector.verify called with no scripted answer"
            ),
        )


class ScriptedLoginConnector(_ScriptedActivityPullerMixin):
    """A synthetic ``LOGIN``-style connector with ``login`` and ``refresh``
    (Req 2.2-2.8).

    ``capabilities`` defaults to a single non-driven capability; a caller
    that overrides it to include ``PULL_ACTIVITIES`` (task 4.4) gets a
    connector that also implements ``list_activities``/``fetch_activity``
    (via :class:`_ScriptedActivityPullerMixin`), so it validates and can
    pull.
    """

    connector_id = "login-style"
    display_name = "Login Style"
    auth_style = AuthStyle.LOGIN
    credential_fields = (
        CredentialField("username", "Username", secret=False),
        CredentialField("password", "Password", secret=True),
    )

    def __init__(
        self,
        *,
        capabilities: frozenset[Capability] | None = None,
        data_url: str | None = None,
    ) -> None:
        self.capabilities = (
            capabilities
            if capabilities is not None
            else frozenset({Capability.PULL_WELLNESS})
        )
        self._init_activity_puller(data_url=data_url)
        self.login_script: list[TokenSet | BaseException] = []
        self.refresh_script: list[TokenSet | BaseException] = []
        self.login_calls: list[Mapping[str, Secret]] = []
        self.refresh_calls: int = 0
        self.parse_settings_calls: int = 0

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object:
        self.parse_settings_calls += 1
        return None

    def login(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> TokenSet:
        self.login_calls.append(values)
        return _consume_script(
            self.login_script,
            description="ScriptedLoginConnector.login called with no scripted answer",
        )

    def refresh(self, session: ConnectorSession) -> TokenSet:
        self.refresh_calls += 1
        return _consume_script(
            self.refresh_script,
            description="ScriptedLoginConnector.refresh called with no scripted answer",
        )


class ScriptedPuller(_ScriptedActivityPullerMixin):
    """A synthetic ``PULL_ACTIVITIES`` connector with scripted listing and
    fetch answers (Req 2.2-2.8).

    When ``data_url`` is given, ``list_activities`` issues a real request
    through ``session.http.get(data_url)`` before consuming its scripted
    answer -- so a test can assert that a puller which needs remote data to
    decide its listing actually asks for it, using the same
    ``FakeTransport``-backed ``HttpClient`` every other connector test uses.
    """

    connector_id = "scripted-puller"
    display_name = "Scripted Puller"
    auth_style = AuthStyle.NONE
    capabilities = frozenset({Capability.PULL_ACTIVITIES})
    credential_fields: tuple[CredentialField, ...] = ()

    def __init__(self, *, data_url: str | None = None) -> None:
        self._init_activity_puller(data_url=data_url)
        self.parse_settings_calls: int = 0

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object:
        self.parse_settings_calls += 1
        return None


# mypy structurally checks each synthetic connector against the protocols it
# claims (task requirement); the names are not otherwise imported.
_typed_personal_key_as_connector: Connector = ScriptedPersonalKeyConnector()
_typed_personal_key_as_verifier: KeyVerifier = ScriptedPersonalKeyConnector()
_typed_personal_key_as_activity_puller: ActivityPuller = ScriptedPersonalKeyConnector()
_typed_login_as_connector: Connector = ScriptedLoginConnector()
_typed_login_as_issuer: TokenIssuer = ScriptedLoginConnector()
_typed_login_as_activity_puller: ActivityPuller = ScriptedLoginConnector()
_typed_puller_as_connector: Connector = ScriptedPuller()
_typed_puller_as_activity_puller: ActivityPuller = ScriptedPuller()


@pytest.fixture
def personal_key_connector() -> ScriptedPersonalKeyConnector:
    """A fresh :class:`ScriptedPersonalKeyConnector` for this test only."""
    return ScriptedPersonalKeyConnector()


@pytest.fixture
def login_style_connector() -> ScriptedLoginConnector:
    """A fresh :class:`ScriptedLoginConnector` for this test only."""
    return ScriptedLoginConnector()


@pytest.fixture
def scripted_puller_connector() -> ScriptedPuller:
    """A fresh :class:`ScriptedPuller` for this test only."""
    return ScriptedPuller()
