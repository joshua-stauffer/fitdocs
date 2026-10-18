"""Pin the system zone the CLI dates pages by, for one block of a test.

``fitdocs`` commands date a page whose file records no local offset in the
system's zone (``cli._local_tz``), and a page fitdocs named follows a changed
local start to a new filename (activity-identity A2.1). A test that writes
pages through the engine with a fixed ``tz`` and then runs a CLI command over
them pins the CLI to the same zone, or its page paths depend on the host.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def system_zone(key: str) -> Iterator[None]:
    """Set ``TZ`` to ``key`` (and the C library with it), then restore both."""
    saved = os.environ.get("TZ")
    os.environ["TZ"] = key
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        if hasattr(time, "tzset"):
            time.tzset()
