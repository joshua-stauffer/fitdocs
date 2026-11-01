"""A test extension: /x/slow/wait answers after a delay, once it is in flight."""

import asyncio
import os
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import BaseRoute, Route

from fitdocs_relay.seam import SEAM_VERSION, ExtensionContext, ExtensionParts

STARTED_FILE_VARIABLE = "SERVE_TEST_STARTED_FILE"
DELAY_VARIABLE = "SERVE_TEST_DELAY_SECONDS"


async def wait(request: Request) -> Response:
    Path(os.environ[STARTED_FILE_VARIABLE]).write_text("in flight", encoding="utf-8")
    await asyncio.sleep(float(os.environ[DELAY_VARIABLE]))
    return PlainTextResponse("finished the slow request")


class SlowExtension:
    name = "slow"
    seam_version = SEAM_VERSION

    def build(self, context: ExtensionContext) -> ExtensionParts:
        routes: tuple[BaseRoute, ...] = (Route("/x/slow/wait", wait),)
        return ExtensionParts(routes=routes)


EXTENSION = SlowExtension()


BUILDING_FILE_VARIABLE = "SERVE_TEST_BUILDING_FILE"
RELEASE_FILE_VARIABLE = "SERVE_TEST_RELEASE_FILE"


class BlockingExtension:
    """Its `build` blocks (the app is mid-construction) until a file appears."""

    name = "blocking"
    seam_version = SEAM_VERSION

    def build(self, context: ExtensionContext) -> ExtensionParts:
        Path(os.environ[BUILDING_FILE_VARIABLE]).write_text(
            "building", encoding="utf-8"
        )
        release = Path(os.environ[RELEASE_FILE_VARIABLE])
        deadline = time.monotonic() + 25
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        return ExtensionParts()


BLOCKING = BlockingExtension()
