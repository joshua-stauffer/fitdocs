"""``VersionSource`` (design.md `#### VersionSource`, Req 2.1-2.4): the one
leaf every version-reporting surface reads from.

Three call sites used to resolve the installed version independently and
unguarded: the CLI's eager ``--version`` callback, the tile-fetcher's
User-Agent, and the plugin listing's built-in-calculator version. Each called
``importlib.metadata.version("fitdocs")`` directly, which raises
``PackageNotFoundError`` when the tool runs from an uninstalled source tree
-- turning a routine "not installed" state into a crash (Req 2.4). This
module is the single place that lookup happens; every consumer reads
:func:`tool_version` or :func:`version_display` instead.

The lookup is performed lazily, at the point of use, every time -- never at
import time, and never cached at module scope beyond the distribution name
constant. Metadata reads are slow enough to matter for a command-line
start-up, so nothing here does the read until a caller actually asks; a
module-level cache would also go stale if the distribution's installed state
changed within a process (e.g. across a test's ``importlib.reload``).

This module imports nothing from ``fitdocs`` -- it is the leaf every version
consumer depends on, so it may not acquire a package dependency without
inverting the dependency direction. It is deliberately internal: it is not
re-exported from ``fitdocs/__init__.py`` and not part of the documented
public surface pinned in ``tests/test_public_api.py``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Final

#: The distribution name registered with the packaging index -- the argument
#: every ``importlib.metadata`` lookup below needs to find *this* project's
#: metadata rather than some other installed package.
DIST_NAME: Final[str] = "fitdocs"

#: The fixed token every degraded display falls back to. A constant, not a
#: sentinel computed per call, so it cannot vary between runs or processes
#: (Req 2.4).
UNKNOWN_VERSION: Final[str] = "unknown"


def tool_version() -> str | None:
    """The installed ``fitdocs`` distribution's version, or ``None`` when the
    tool is running from an uninstalled source tree.

    Never raises. Absent data is ``None``, never a fabricated string --
    matching the project's absent-data rule and plugin-api Req 4.3, which
    forbids a fabricated version anywhere it is reported.
    """
    try:
        return version(DIST_NAME)
    except PackageNotFoundError:
        return None


def version_display() -> str:
    """``tool_version()``, or :data:`UNKNOWN_VERSION` when that is ``None``.

    Never raises, never returns an empty string. For surfaces that must
    render *something* -- the CLI's ``--version`` output, the tile
    User-Agent -- rather than propagate an absent value.
    """
    return tool_version() or UNKNOWN_VERSION
