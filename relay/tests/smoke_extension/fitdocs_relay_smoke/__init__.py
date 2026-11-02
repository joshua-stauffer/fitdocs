"""A minimal wrapper for the derived-image smoke run: one route, /x/smoke/ping.

Name it in `FITDOCS_RELAY_EXTENSIONS` as `fitdocs_relay_smoke:EXTENSION`.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import BaseRoute, Route

from fitdocs_relay.seam import SEAM_VERSION, ExtensionContext, ExtensionParts

ANSWER = "smoke extension answers"


def ping(request: Request) -> Response:
    return PlainTextResponse(ANSWER)


class SmokeExtension:
    name = "smoke"
    seam_version = SEAM_VERSION

    def build(self, context: ExtensionContext) -> ExtensionParts:
        routes: tuple[BaseRoute, ...] = (Route("/x/smoke/ping", ping),)
        return ExtensionParts(routes=routes)


EXTENSION = SmokeExtension()
