"""The relay's route table: the reserved paths and the core routes.

This module holds the skeleton; the probes, capabilities, token and
registration routes are added to `core_routes` by the tasks that serve them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from starlette.routing import BaseRoute

if TYPE_CHECKING:
    from fitdocs_relay.app import RelayServices

OFFERED_TARGETS: tuple[str, ...] = ()  # later specs append target ids here
RESERVED_PREFIXES: Final = ("/v", "/livez", "/readyz", "/x/")


def core_routes(services: RelayServices) -> list[BaseRoute]:
    return []
