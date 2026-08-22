"""Tile provider settings and cache-first tile acquisition (Req 3.1-3.4, 4.2, 5.1-5.4).

This module has two halves that together own everything network- and cache-
related for route-map basemap tiles. The *settings* half (below) is the typed,
read-only ``fitdocs.toml`` ``[tiles]`` reader. The *store* half
(:class:`TileSource`, :class:`TileUnavailableError`, :class:`TileStore`) is the
package's **only** network-touching code (Req 4.2): it resolves a plan's tiles
cache-first, fetching a miss politely and writing it through to the cache
atomically before returning, and gates every request behind the persistent
opt-out.

Settings half
-------------

This module owns the typed provider configuration for route-map basemap tiles.
It maps an *optional* ``<data-root>/fitdocs.toml`` ``[tiles]`` table onto the
:class:`TileSettings` contract (design: "TileSettings + ``load_tile_settings``").
The settings source unlocks provider choice (Req 5.1), the keyless OSM default
(Req 5.2), and the persistent privacy opt-out (Req 5.3).

Two invariants shape the reader:

* **Defaulted, never an error.** An absent ``fitdocs.toml`` -- or a file with no
  ``[tiles]`` table -- yields :data:`DEFAULT_TILE_SETTINGS` (the OSM standard
  layer). Each key defaults *independently*, so a partial ``[tiles]`` table fills
  only the keys it names; the rest come from the default.
* **Loud, never lossy.** A file whose ``[tiles]`` table is malformed -- a ``url``
  missing a tile-coordinate placeholder, a ``name`` that is not a path-safe slug
  (which would let a config value traverse out of the tile cache), a non-boolean
  ``enabled``, or any wrong-typed value -- raises :class:`TileSettingsError`.
  Silently accepting a bad provider would misdirect (or leak) tile traffic
  invisibly, so nothing is swallowed.

The file is **user-owned and read-only to fitdocs**: this reader never creates
it, never prompts, and writes nothing on any path. Unknown keys within
``[tiles]`` and unknown top-level tables are ignored, because future fitdocs
settings tables will share this same file.

The TOML key for the address pattern is ``url`` while the dataclass field is
``url_template``; the mapping is applied here. Because Python's ``bool`` is a
subclass of ``int``, ``enabled`` is validated with an explicit ``bool`` check so
a TOML integer never sneaks through as ``True``/``False``.
"""

from __future__ import annotations

import os
import re
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Final, Protocol

from fitdocs.layout import settings_path, tile_cache_path
from fitdocs.render.charts.map import TileRef
from fitdocs.settings import SettingsError, load_settings_document

TILES_TABLE: Final[str] = "tiles"

# A path-safe cache-directory slug: lowercase alphanumerics and hyphens, first
# character alphanumeric. Rejects separators, ``..``, uppercase, and the empty
# string -- so a provider ``name`` from config can never traverse the tile cache.
_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9-]*")

# The three slippy-map tile-coordinate placeholders every provider URL must carry.
_URL_PLACEHOLDERS: Final[tuple[str, ...]] = ("{z}", "{x}", "{y}")


@dataclass(frozen=True)
class TileSettings:
    """Validated tile-provider configuration (design: TileSettings).

    Every field has a default (see :data:`DEFAULT_TILE_SETTINGS`); a ``[tiles]``
    table overrides them per key.
    """

    enabled: bool
    """``False`` is the persistent opt-out: no tile requests are made (Req 5.3)."""

    name: str
    """Cache-directory slug (path-safe, e.g. ``"osm"``); keys the tile cache."""

    url_template: str
    """HTTPS URL carrying ``{z}``/``{x}``/``{y}`` placeholders (from TOML ``url``)."""

    attribution: str
    """Provider attribution text, rendered legibly on every map image (Req 2.7)."""


#: The keyless default provider: the OpenStreetMap standard tile layer, whose
#: published policy permits fitdocs' identified, cached, low-volume access (Req
#: 5.2). Used whenever ``fitdocs.toml`` or its ``[tiles]`` table is absent.
DEFAULT_TILE_SETTINGS: Final[TileSettings] = TileSettings(
    enabled=True,
    name="osm",
    url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution="© OpenStreetMap contributors",
)


class TileSettingsError(SettingsError):
    """The ``fitdocs.toml`` ``[tiles]`` table exists but is not valid configuration.

    Raised for a ``url`` missing a tile-coordinate placeholder, a ``name`` that is
    not a path-safe slug, a non-boolean ``enabled``, a non-table ``tiles`` value,
    or any wrong-typed value -- faults that belong to *this table*. An *absent*
    file or ``[tiles]`` table is never an error -- it yields
    :data:`DEFAULT_TILE_SETTINGS`. The message names the file and the offending
    key so a user can correct the configuration (CLI maps this to a loud exit-2
    failure, consistent with ``athlete.toml``).

    File-level faults -- an unreadable file, invalid TOML -- are *not* raised
    here: they belong to the file rather than to any one table and surface as the
    shared :class:`~fitdocs.settings.SettingsError`, so a user with a stray
    bracket gets one message instead of whichever table happened to be read
    first. This type subclasses it, so ``except SettingsError`` still catches
    both.
    """


def load_tile_settings(data_root: Path) -> TileSettings:
    """Read ``<data_root>/fitdocs.toml`` ``[tiles]`` into :class:`TileSettings`.

    The convenience entry point for a caller that wants tile settings and nothing
    else: it performs the shared one-time read of the settings document and then
    projects the ``[tiles]`` table out of it. A caller that consults several
    tables in one invocation should call
    :func:`~fitdocs.settings.load_settings_document` once and pass the result to
    :func:`tile_settings_from_document` instead, so the file is read once.

    Returns :data:`DEFAULT_TILE_SETTINGS` when the file or its ``[tiles]`` table
    is absent (Req 5.2). Raises :class:`TileSettingsError` for a malformed
    ``[tiles]`` table and the shared :class:`~fitdocs.settings.SettingsError` for
    a file-level fault. Only ever reads; never writes, creates, or prompts.
    """
    document = load_settings_document(data_root)
    return tile_settings_from_document(document, settings_path(data_root))


def tile_settings_from_document(
    document: Mapping[str, object], path: Path
) -> TileSettings:
    """Project the ``[tiles]`` table of an already-parsed settings document.

    The per-table reader: it validates only ``[tiles]`` and never opens a file --
    ``document`` is the mapping :func:`~fitdocs.settings.load_settings_document`
    returned (empty when the settings file is absent), and ``path`` is used only
    to name the file in error messages.

    Every recognized key is mapped independently onto the corresponding field
    (present keys override, absent keys keep the default), the TOML ``url`` key is
    mapped onto ``url_template``, and unknown keys are ignored for forward
    compatibility (Req 5.1).

    Raises :class:`TileSettingsError` when the ``[tiles]`` table is malformed: a
    non-table ``tiles`` value, a ``url`` missing any of ``{z}``/``{x}``/``{y}``
    (Req 5.1), a ``name`` that is not a path-safe slug (rejects cache-path
    traversal via config), a non-boolean ``enabled`` (Req 5.3), or a wrong-typed
    string key.
    """
    if TILES_TABLE not in document:
        return DEFAULT_TILE_SETTINGS
    table = document[TILES_TABLE]
    if not isinstance(table, dict):
        raise TileSettingsError(
            f"{path}: [tiles] must be a table, got {table!r} ({type(table).__name__})"
        )

    return TileSettings(
        enabled=_setting_bool(table, "enabled", DEFAULT_TILE_SETTINGS.enabled, path),
        name=_setting_name(table, path),
        url_template=_setting_url(table, path),
        attribution=_setting_str(
            table, "attribution", DEFAULT_TILE_SETTINGS.attribution, path
        ),
    )


def _setting_bool(table: dict[str, Any], key: str, default: bool, path: Path) -> bool:
    """Map an optional boolean key; reject non-bools (a TOML int is not a bool)."""
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise TileSettingsError(
            f"{path}: [tiles] {key} must be a boolean, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_str(table: dict[str, Any], key: str, default: str, path: Path) -> str:
    """Map an optional string key; reject non-strings (never coerce)."""
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, str):
        raise TileSettingsError(
            f"{path}: [tiles] {key} must be a string, "
            f"got {value!r} ({type(value).__name__})"
        )
    return value


def _setting_name(table: dict[str, Any], path: Path) -> str:
    """Map the optional ``name`` key, enforcing the path-safe slug pattern.

    A non-slug ``name`` (uppercase, empty, or containing separators / ``..``)
    would let a config value traverse out of the tile cache, so it is rejected
    loudly rather than sanitized (Req 5.1, security).
    """
    name = _setting_str(table, "name", DEFAULT_TILE_SETTINGS.name, path)
    if "name" in table and _SLUG_PATTERN.fullmatch(name) is None:
        raise TileSettingsError(
            f"{path}: [tiles] name must be a path-safe slug "
            f"matching [a-z0-9][a-z0-9-]*, got {name!r}"
        )
    return name


def _setting_url(table: dict[str, Any], path: Path) -> str:
    """Map the optional TOML ``url`` key onto ``url_template``, requiring placeholders.

    The address pattern must carry all three slippy-map tile-coordinate
    placeholders ``{z}``/``{x}``/``{y}``; a URL missing any of them cannot address
    a tile and is rejected loudly (Req 5.1).
    """
    url = _setting_str(table, "url", DEFAULT_TILE_SETTINGS.url_template, path)
    if "url" in table:
        missing = [ph for ph in _URL_PLACEHOLDERS if ph not in url]
        if missing:
            raise TileSettingsError(
                f"{path}: [tiles] url must contain the tile-coordinate "
                f"placeholders {', '.join(_URL_PLACEHOLDERS)}; "
                f"missing {', '.join(missing)} in {url!r}"
            )
    return url


# ===========================================================================
# Store half: cache-first tile acquisition (Req 3.1-3.4, 4.2, 5.4)
#
# The only network-touching code in the package. Everything above is pure
# configuration parsing; everything below reaches the filesystem cache and,
# on a miss, the configured provider over HTTPS.
# ===========================================================================

#: The mandatory descriptive User-Agent every tile request carries (Req 3.4).
#: OSM actively blocks the default library UA, so identifying fitdocs (with its
#: installed version and project URL) is load-bearing, not cosmetic. Derived
#: from the installed distribution version -- the same accessor the CLI
#: ``--version`` flag uses -- so it tracks releases automatically. Exposed as a
#: module constant so a test can assert the exact header value.
USER_AGENT: Final[str] = (
    f"fitdocs/{version('fitdocs')} (+https://github.com/joshua-stauffer/fitdocs)"
)

#: Per-request network timeout, in seconds. One attempt per tile per run (no
#: retries), so this bounds the wait before a miss degrades to a warning.
_FETCH_TIMEOUT_SECONDS: Final[int] = 10


class TileSource(Protocol):
    """The tile-resolution seam the sync engine depends on (design: TileSource).

    Tests inject fakes; the CLI injects a real :class:`TileStore`. Keeping sync
    behind this protocol is what confines all network and cache I/O to this
    module (Req 4.2). :meth:`resolve` is the *only* entry point -- there is no
    prefetch/warm surface, so tiles are requested only for maps actually being
    rendered (supports Req 3.5).
    """

    @property
    def attribution(self) -> str:
        """The provider attribution text, rendered on every composed map (Req 2.7)."""
        ...

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        """Return the bytes of every ref, or raise :class:`TileUnavailableError`."""
        ...


class TileUnavailableError(Exception):
    """A required tile is neither cached nor fetchable, so the map cannot render.

    Raised on a cache miss when tile requests are disabled (the persistent
    opt-out, Req 5.4) or when a fetch fails (offline, HTTP error, or timeout,
    Req 3.4). The message names both the cause and the offending tile. The sync
    engine turns this into a doc-scoped warning and renders the document without
    a Map section (-> Req 4.3, 4.4); it is never a fatal error.
    """


class TileStore:
    """Cache-first tile resolution with a polite fetch on miss (design: TileStore).

    Structurally implements :class:`TileSource`. For each requested ref
    :meth:`resolve` reads the per-provider cache under the data root first; only
    a true miss touches the network, and a cached tile is never re-requested
    (Req 3.2), so a fully-cached resolve makes zero network calls (Req 3.2,
    4.2). A miss is fetched *sequentially* with the mandatory descriptive
    :data:`USER_AGENT` and a bounded timeout -- one attempt per tile per run, no
    retries (Req 3.4) -- and written through to the cache atomically *before*
    the bytes are used, so an interrupted run never leaves a torn tile and
    already-fetched tiles survive a later failure (Req 3.1).

    The opt-out gates fetching in both directions (Req 5.4): with
    ``settings.enabled = False`` a cache miss raises :class:`TileUnavailableError`
    and nothing is requested, while a fully-cached map still renders from cache.
    Any fetch failure likewise raises :class:`TileUnavailableError` naming the
    cause. The cache is append-only: bytes are embedded verbatim (a corrupt
    provider tile is the provider's content, not validated here), never
    rewritten and never pruned.

    ``fetch`` is an injectable seam (default: the real :func:`_default_fetch`
    urllib opener) so tests drive every path with a fake and never touch the
    network.
    """

    def __init__(
        self,
        data_root: Path,
        settings: TileSettings,
        fetch: Callable[[str], bytes] | None = None,
    ) -> None:
        self._data_root = data_root
        self._settings = settings
        self._fetch: Callable[[str], bytes] = _default_fetch if fetch is None else fetch

    @property
    def attribution(self) -> str:
        """The provider's attribution text, rendered on every map (Req 2.7)."""
        return self._settings.attribution

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        """Resolve every ref in *refs* to its PNG bytes, cache-first (Req 3.1-3.4, 5.4).

        Iterates *refs* in order and returns a dict covering every distinct ref.
        Each ref is served from the per-provider cache when present; otherwise,
        with tile requests enabled, it is fetched sequentially and written
        through to the cache before its bytes are used. Raises
        :class:`TileUnavailableError` on the first ref that is missing while the
        opt-out is active, or whose fetch fails (offline, HTTP error, timeout) --
        naming the cause and the tile. Because writes are per-tile write-through,
        a failure on a later ref leaves the tiles already fetched durably cached
        (Req 3.1); the error then propagates without rolling them back.
        """
        resolved: dict[TileRef, bytes] = {}
        for ref in refs:
            if ref not in resolved:
                resolved[ref] = self._tile_bytes(ref)
        return resolved

    def _tile_bytes(self, ref: TileRef) -> bytes:
        """Cache-first bytes for one tile: read, else gate, fetch, and write through.

        Reads the cache first (Req 3.2); on a miss raises
        :class:`TileUnavailableError` when tile requests are disabled (Req 5.4),
        otherwise fetches once with no retries, writes the result through to the
        cache atomically before returning (Req 3.1), and turns any fetch failure
        into a :class:`TileUnavailableError` naming the cause and the tile (Req
        3.4).
        """
        path = tile_cache_path(
            self._data_root, self._settings.name, ref.z, ref.x, ref.y
        )
        if path.is_file():
            return path.read_bytes()

        if not self._settings.enabled:
            raise TileUnavailableError(
                "tile requests are disabled (fitdocs.toml [tiles] enabled = false); "
                f"tile {ref.z}/{ref.x}/{ref.y} is not cached"
            )

        url = self._settings.url_template.format(z=ref.z, x=ref.x, y=ref.y)
        try:
            data = self._fetch(url)
        except Exception as exc:  # noqa: BLE001 -- any fetch failure degrades uniformly
            raise TileUnavailableError(
                f"could not fetch tile {ref.z}/{ref.x}/{ref.y} from {url}: {exc}"
            ) from exc

        _write_through(path, data)
        return data


def _default_fetch(url: str) -> bytes:
    """Fetch *url* over HTTPS with the mandatory UA and timeout (Req 3.4, 4.2).

    The package's only network call. Issues a single GET carrying
    :data:`USER_AGENT` (OSM blocks default library UAs) and a
    :data:`_FETCH_TIMEOUT_SECONDS`-second timeout, returning the raw response
    bytes. Any failure (offline, HTTP error, timeout) surfaces as the underlying
    ``urllib`` exception, which :meth:`TileStore._tile_bytes` maps to
    :class:`TileUnavailableError`. ``urlopen`` is referenced through the
    ``urllib.request`` module so a test can substitute the opener.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        payload: bytes = response.read()
    return payload


def _write_through(path: Path, data: bytes) -> None:
    """Write *data* to the cache *path* atomically (the ``save_profile`` pattern).

    Creates the tile's parent directories, writes to a temporary file in the
    *same* directory, then :func:`os.replace` renames it over the target -- a
    same-filesystem atomic rename, so a reader never sees a torn tile (Req 3.1).
    The temporary file is removed if anything fails, leaving no ``.tmp`` residue.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tile-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
