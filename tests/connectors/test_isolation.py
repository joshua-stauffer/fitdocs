"""Pins for the autouse isolation fixtures in ``tests/connectors/conftest.py``."""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.connectors.conftest import isolate_connector_environment

_STALE_CONNECTOR_KEY = "FITDOCS_CONNECTOR_STALE_PROBE_API_KEY"
_STALE_XDG_VALUE = "/should/be/removed/by/isolation"


@pytest.fixture(scope="module", autouse=True)
def _stale_env_probe() -> Iterator[str]:
    """Set stale overrides *before* any per-test fixture in this module runs.

    Module scope resolves before function scope for every test in this file
    (pytest's scope ordering, independent of fixture declaration order or
    autouse status), so by the time ``_isolated_connector_environment``
    (function-scoped, in ``conftest.py``) runs for the first test, these
    values are already present in ``os.environ`` -- exactly the "preexisting
    override" scenario the isolation fixture must clear. Confined to this
    module (not session-scoped) so no other test file sees the bogus
    ``XDG_CONFIG_HOME`` value.
    """
    prior_key = os.environ.get(_STALE_CONNECTOR_KEY)
    had_xdg = "XDG_CONFIG_HOME" in os.environ
    prior_xdg = os.environ.get("XDG_CONFIG_HOME")

    os.environ[_STALE_CONNECTOR_KEY] = "leak-if-not-removed-by-isolation"
    os.environ["XDG_CONFIG_HOME"] = _STALE_XDG_VALUE

    yield _STALE_CONNECTOR_KEY

    if prior_key is not None:
        os.environ[_STALE_CONNECTOR_KEY] = prior_key
    else:
        os.environ.pop(_STALE_CONNECTOR_KEY, None)
    if had_xdg:
        assert prior_xdg is not None
        os.environ["XDG_CONFIG_HOME"] = prior_xdg
    else:
        os.environ.pop("XDG_CONFIG_HOME", None)


def test_an_ordinary_test_has_socket_guard_and_isolated_credentials_dir(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError):
        socket.socket()

    credentials_dir = Path(os.environ["FITDOCS_CREDENTIALS_DIR"])
    home_dir = Path(os.environ["HOME"])

    assert credentials_dir.is_dir()
    assert home_dir.is_dir()
    # The isolation base is a distinct tmp_path_factory tree, not the test's
    # own tmp_path -- a hard-coded real (non-temporary) directory, or the
    # test's own tmp_path used as a stand-in sandbox data root, would both
    # fail this.
    assert "connector-env" in str(credentials_dir)
    assert "connector-env" in str(home_dir)
    assert not credentials_dir.is_relative_to(tmp_path)
    assert not home_dir.is_relative_to(tmp_path)


def test_autouse_isolation_fixture_removes_preexisting_stale_overrides(
    _stale_env_probe: str,
) -> None:
    # By the time this test body runs, the function-scoped isolation fixture
    # has already executed once for this test, on top of the module-scoped
    # fixture's preset values -- so if isolation actually ran, both are gone.
    assert _stale_env_probe not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ


def test_isolation_helper_clears_overrides_and_repoints_credentials_dir_and_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "isolation-base"
    monkeypatch.setenv("FITDOCS_CONNECTOR_X_API_KEY", "shh-do-not-tell")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/not/a/real/config/home")

    # Falsity first: the overrides really are present before the helper runs.
    assert "FITDOCS_CONNECTOR_X_API_KEY" in os.environ
    assert "XDG_CONFIG_HOME" in os.environ

    isolate_connector_environment(monkeypatch, base_dir)

    assert "FITDOCS_CONNECTOR_X_API_KEY" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ
    assert Path(os.environ["FITDOCS_CREDENTIALS_DIR"]).is_relative_to(base_dir)
    assert Path(os.environ["HOME"]).is_relative_to(base_dir)


_CREDENTIALS_DIRS_SEEN: set[str] = set()


@pytest.mark.parametrize("case", ["first", "second"])
def test_each_test_gets_its_own_credentials_directory(case: str) -> None:
    """Two tests never share an isolation directory, so a credentials file
    one test saves is invisible to the next. Order-independent: whichever
    case runs second finds its directory new and empty.
    """
    credentials_dir = os.environ["FITDOCS_CREDENTIALS_DIR"]
    assert credentials_dir not in _CREDENTIALS_DIRS_SEEN
    assert list(Path(credentials_dir).iterdir()) == []
    _CREDENTIALS_DIRS_SEEN.add(credentials_dir)
    (Path(credentials_dir) / f"{case}.toml").write_text("", encoding="utf-8")
