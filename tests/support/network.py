"""Refuse and record any connection a test tries to make off this machine.

Refusing alone would not be enough. Production code degrades on purpose when the
network is unavailable: ``TileStore`` turns any fetch failure into a page without
a map, so a test that reaches for the network passes anyway and nobody hears about
it. Four tests did exactly that against ``tile.openstreetmap.org`` on every run.
So each attempt is recorded as well as refused, and ``tests/conftest.py`` fails the
test at teardown if anything was recorded, whatever the code under test did with
the refusal.

This is an audit hook rather than a patched ``socket`` attribute because many tests
patch ``socket`` themselves, and a hook cannot be undone by them. It sees the pytest
process only, not child processes.
"""

from __future__ import annotations

import ipaddress
import sys


class ExternalNetworkRefused(OSError):
    """A test tried to reach a host off this machine.

    An ``OSError`` so the code under test sees what it would see offline.
    """


_attempts: list[str] = []


def _is_local(host: object) -> bool:
    """Whether *host* stays on this machine; ``None`` and ``""`` mean a local bind."""
    if host is None or host in ("", b""):
        return True
    name = host.decode() if isinstance(host, bytes) else str(host)
    if name.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _refuse_external(event: str, args: tuple[object, ...]) -> None:
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event == "socket.connect":
        address = args[1]
        # A unix socket's address is a path. Only (host, port, ...) can leave.
        if not isinstance(address, tuple):
            return
        host = address[0]
    else:
        return
    if _is_local(host):
        return
    _attempts.append(str(host))
    raise ExternalNetworkRefused(f"tests may not contact {host}")


def install() -> None:
    """Install the hook, which lasts for the life of the process."""
    sys.addaudithook(_refuse_external)


def take_attempts() -> tuple[str, ...]:
    """Return the hosts attempted since the last call, and forget them."""
    attempts = tuple(_attempts)
    _attempts.clear()
    return attempts
