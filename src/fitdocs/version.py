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

:func:`user_agent` (connectors design.md VersionUA, Req 9.1) is this leaf's
one composed fitdocs User-Agent, built from :func:`version_display` and
:data:`PROJECT_URL`. ``fitdocs.tiles``'s tile fetcher returns it rather than
holding its own literal, and it has a fourth consumer besides the three call
sites above: the connector transport (``fitdocs/connectors/http.py``), which
sends it with every connector request.

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

#: The project's public home, embedded in every fitdocs User-Agent (connectors
#: design.md VersionUA, Req 9.1) so a service operator can identify and
#: contact the tool behind a request.
PROJECT_URL: Final[str] = "https://github.com/joshua-stauffer/fitdocs"


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


def user_agent() -> str:
    """The one fitdocs User-Agent (design.md VersionUA, Req 9.1): every
    request any connector or the tile fetcher makes carries this string,
    naming the installed version and :data:`PROJECT_URL`, and never the HTTP
    library's default agent.

    Composed at call time from :func:`version_display` -- no module-level
    cache, matching this module's own no-import-time-work,
    no-module-level-cache rule -- so a version that becomes resolvable later
    in the same process is reflected on the very next call, and the
    installed-vs-unknown degradation (Req 2.4) flows through automatically.
    There is exactly one definition of this string in the package;
    ``fitdocs.tiles``'s own agent function returns it rather than composing
    a second literal.
    """
    return f"fitdocs/{version_display()} (+{PROJECT_URL})"
