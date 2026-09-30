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
from pathlib import Path
from typing import NoReturn

import pytest

from fitdocs.connectors.http import HttpRequest, HttpResponse, TransportError


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
