"""The relay's route table: the reserved paths and the core routes.

The probes live here; the capabilities, token and registration routes are added
to `core_routes` by the tasks that serve them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from fitdocs_relay.answers import answer
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import ROUTE_LIVEZ, ROUTE_READYZ
from fitdocs_relay.storage.interface import Storage, StorageUnreachable

if TYPE_CHECKING:
    from fitdocs_relay.app import RelayServices

OFFERED_TARGETS: tuple[str, ...] = ()  # later specs append target ids here
RESERVED_PREFIXES: Final = ("/v", "/livez", "/readyz", "/x/")


def readiness(storage: Storage) -> Response:
    """The readiness answer: `ok` only when the store is reachable and at this
    build's schema version, else the code naming the failing condition."""
    try:
        storage.ping()
        state = storage.schema_state()
    except StorageUnreachable:
        return answer(RelayCode.STORAGE_UNREACHABLE)
    if state.current < state.expected:
        code = RelayCode.SCHEMA_BEHIND
    elif state.current > state.expected:
        code = RelayCode.SCHEMA_AHEAD
    else:
        code = RelayCode.OK
    return answer(
        code, {"schema": {"current": state.current, "expected": state.expected}}
    )


def core_routes(services: RelayServices) -> list[BaseRoute]:
    def livez(request: Request) -> Response:
        return answer(RelayCode.OK)

    def readyz(request: Request) -> Response:
        try:
            response = readiness(services.storage)
        except Exception:
            services.ready = False  # a probe that fails is not a ready store
            raise
        services.ready = response.status_code == 200
        return response

    return [Route(ROUTE_LIVEZ, livez), Route(ROUTE_READYZ, readyz)]
