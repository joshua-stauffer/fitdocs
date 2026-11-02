"""The autouse network guard in conftest: non-loopback is refused, loopback works."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from fitdocs_relay.outbound import OutboundRequest, urllib_outbound

REFUSED = "may not reach a non-local host"


def test_a_connection_by_name_is_refused_and_recorded(
    network_attempts: list[str],
) -> None:
    with pytest.raises(AssertionError, match=REFUSED):
        socket.create_connection(("example.com", 443), timeout=1)
    assert network_attempts == ["create_connection"]
    network_attempts.clear()


@pytest.mark.parametrize("address", ["93.184.216.34", "10.0.0.1", "169.254.169.254"])
def test_a_connect_to_a_non_loopback_address_is_refused_and_recorded(
    address: str, network_attempts: list[str]
) -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match=REFUSED):
        sock.settimeout(1)  # bounds a guard that lets the connection through
        sock.connect((address, 443))
    with socket.socket() as sock, pytest.raises(AssertionError, match=REFUSED):
        sock.settimeout(1)
        sock.connect_ex((address, 443))
    with pytest.raises(AssertionError, match=REFUSED):
        socket.create_connection((address, 443), timeout=1)
    assert network_attempts == ["connect", "connect_ex", "create_connection"]
    network_attempts.clear()


def test_a_name_lookup_is_refused_and_recorded(network_attempts: list[str]) -> None:
    with pytest.raises(AssertionError, match=REFUSED):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(AssertionError, match=REFUSED):
        socket.gethostbyname("example.com")
    with pytest.raises(AssertionError, match=REFUSED):
        socket.gethostbyname_ex("example.com")
    with pytest.raises(AssertionError, match=REFUSED):
        socket.getnameinfo(("93.184.216.34", 443), 0)
    assert network_attempts == [
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "getnameinfo",
    ]
    network_attempts.clear()


def test_the_real_outbound_client_cannot_reach_a_host(
    network_attempts: list[str],
) -> None:
    request = OutboundRequest("GET", "https://example.com/", {}, {})
    with pytest.raises(AssertionError, match=REFUSED):
        urllib_outbound(request, 1.0)
    assert network_attempts  # the attempt itself is what the guard recorded
    network_attempts.clear()


def test_loopback_by_address_and_by_name_still_connects(
    network_attempts: list[str],
) -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
        with socket.create_connection(("localhost", port), timeout=2):
            pass
        assert socket.getaddrinfo("localhost", port)
        assert socket.gethostbyname("localhost")
        assert socket.gethostbyname_ex("localhost")
        assert socket.getnameinfo(("127.0.0.1", port), 0)
    assert network_attempts == []


def test_a_unix_socket_path_is_not_refused(
    tmp_path: Path, network_attempts: list[str]
) -> None:
    with socket.socket(socket.AF_UNIX) as client, pytest.raises(OSError) as caught:
        client.connect(str(tmp_path / "missing.sock"))
    assert "may not reach" not in str(caught.value)
    assert network_attempts == []


def test_a_reserved_invalid_name_fails_to_resolve_without_a_lookup(
    network_attempts: list[str],
) -> None:
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("planted-host.invalid", 443)
    assert network_attempts == []


OFFENDER = """
import socket


def test_swallows_the_refusal():
    try:
        socket.getaddrinfo("example.com", 443)
    except AssertionError:
        pass


def test_innocent():
    assert True
"""


def test_a_swallowed_refusal_still_fails_the_test_at_teardown(tmp_path: Path) -> None:
    shutil.copy(Path(__file__).with_name("conftest.py"), tmp_path / "conftest.py")
    (tmp_path / "test_offender.py").write_text(OFFENDER, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        timeout=120,
    )
    assert done.returncode != 0, done.stdout
    assert "reached for the network" in done.stdout
    assert "2 passed, 1 error" in done.stdout
    assert "test_swallows_the_refusal" in done.stdout
