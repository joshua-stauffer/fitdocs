"""The suite-wide guard against tests leaving this machine (``network.py``)."""

from __future__ import annotations

import contextlib
import socket
from pathlib import Path

import pytest

from fitdocs.render import TileRef
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileStore, TileUnavailableError
from tests.conftest import pytest_runtest_teardown
from tests.support import network


def test_a_lookup_off_this_machine_is_refused_and_recorded() -> None:
    with pytest.raises(network.ExternalNetworkRefused):
        socket.getaddrinfo("tile.example.invalid", 443)
    assert network.take_attempts() == ("tile.example.invalid",)


def test_a_connection_off_this_machine_is_refused_and_recorded() -> None:
    with socket.socket() as client:
        client.settimeout(0.1)
        with pytest.raises(network.ExternalNetworkRefused):
            client.connect(("192.0.2.1", 9))  # TEST-NET-1, reserved for documentation
    assert network.take_attempts() == ("192.0.2.1",)


def test_a_loopback_connection_still_works() -> None:
    with (
        socket.create_server(("127.0.0.1", 0)) as server,
        socket.create_connection(server.getsockname(), timeout=5),
    ):
        pass
    assert network.take_attempts() == ()


def test_a_unix_socket_connection_is_not_treated_as_a_host() -> None:
    with socket.socket(socket.AF_UNIX) as client, pytest.raises(FileNotFoundError):
        client.connect("/nonexistent-fitdocs-test-socket")
    assert network.take_attempts() == ()


@pytest.mark.parametrize(
    "host",
    ["localhost", b"localhost", "LOCALHOST", "127.0.0.1", "::1", "0.0.0.0", "", None],
)
def test_a_local_lookup_is_not_recorded(host: str | bytes | None) -> None:
    # Whether this machine can resolve the name is not the point, only that the
    # guard stays out of the way.
    with contextlib.suppress(socket.gaierror):
        socket.getaddrinfo(host, 80)
    assert network.take_attempts() == ()


def test_an_attempt_the_code_under_test_swallows_still_fails_the_test(
    tmp_path: Path,
) -> None:
    """The case that let real tile fetches go unnoticed: ``TileStore`` turns the
    refusal into a page without a map, so only the teardown hook can object."""
    store = TileStore(tmp_path, DEFAULT_TILE_SETTINGS)
    with pytest.raises(TileUnavailableError):
        store.resolve([TileRef(z=1, x=0, y=0)])

    teardown = pytest_runtest_teardown()
    next(teardown)
    with pytest.raises(pytest.fail.Exception, match=r"tile\.openstreetmap\.org"):
        teardown.send(None)
    assert network.take_attempts() == ()


def test_teardown_does_not_object_when_nothing_was_attempted() -> None:
    teardown = pytest_runtest_teardown()
    next(teardown)
    with pytest.raises(StopIteration):
        teardown.send(None)
