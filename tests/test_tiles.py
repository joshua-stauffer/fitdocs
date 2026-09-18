"""Tests for the read-only tile-provider settings reader (Req 5.1, 5.2, 5.3).

These exercise :func:`fitdocs.tiles.load_tile_settings`, the strictly read-only
mapping from an *optional* ``<data-root>/fitdocs.toml`` ``[tiles]`` table onto the
:class:`~fitdocs.tiles.TileSettings` contract (design: "TileSettings +
``load_tile_settings``", ``src/fitdocs/tiles.py``).

Two invariants govern every case:

* *Absent is the default, never an error.* No ``fitdocs.toml`` -- or a file with
  no ``[tiles]`` table -- yields :data:`~fitdocs.tiles.DEFAULT_TILE_SETTINGS` (the
  keyless OSM standard layer, Req 5.2). Each key defaults independently, so a
  partial ``[tiles]`` table fills only the keys it names.
* *Malformed fails loudly.* A ``url`` missing a tile-coordinate placeholder, a
  ``name`` that is not a path-safe slug (cache-path traversal via config), a
  non-boolean ``enabled``, or any wrong-typed value raises
  :class:`~fitdocs.tiles.TileSettingsError`. Silently accepting a bad provider
  would change (or misdirect) tile traffic invisibly, so nothing is swallowed.

Unknown keys within ``[tiles]`` and unknown top-level tables are ignored so that
future fitdocs settings can share this file. The reader is read-only *by
construction*: it never creates the file and writes nothing on any path.
"""

from __future__ import annotations

import dataclasses
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import pytest

import fitdocs.version as version_module
from fitdocs.layout import tile_cache_path
from fitdocs.render.charts.map import TileRef
from fitdocs.settings import SettingsError
from fitdocs.tiles import (
    DEFAULT_TILE_SETTINGS,
    TileSettings,
    TileSettingsError,
    TileSource,
    TileStore,
    TileUnavailableError,
    _user_agent,
    load_tile_settings,
)

# --- helpers ----------------------------------------------------------------


def _write_settings(data_root: Path, content: str) -> Path:
    """Write ``<data_root>/fitdocs.toml`` with *content* and return its path."""
    path = data_root / "fitdocs.toml"
    path.write_text(content)
    return path


def _snapshot(root: Path) -> set[Path]:
    """Every path under *root*, for asserting the reader wrote nothing."""
    return set(root.rglob("*"))


# --- The default is the OSM standard layer (Req 5.2) ------------------------


def test_default_tile_settings_is_the_osm_standard_layer() -> None:
    """The keyless default provider is the OSM standard layer (Req 5.2)."""
    assert (
        TileSettings(
            enabled=True,
            name="osm",
            url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            attribution="© OpenStreetMap contributors",
        )
        == DEFAULT_TILE_SETTINGS
    )


# --- Absent file / table -> defaults (never an error) (Req 5.2) -------------


def test_absent_file_returns_defaults(tmp_path: Path) -> None:
    """No ``fitdocs.toml`` at all -> the default OSM provider (Req 5.2)."""
    assert load_tile_settings(tmp_path) == DEFAULT_TILE_SETTINGS


def test_absent_file_writes_nothing(tmp_path: Path) -> None:
    """Reading an absent file never creates it or writes anything."""
    before = _snapshot(tmp_path)

    assert load_tile_settings(tmp_path) == DEFAULT_TILE_SETTINGS

    assert _snapshot(tmp_path) == before


def test_absent_tiles_table_returns_defaults(tmp_path: Path) -> None:
    """A file with no ``[tiles]`` table -> defaults; other tables ignored (Req 5.2)."""
    _write_settings(
        tmp_path,
        """
        [some_other_feature]
        setting = "value"
        """,
    )

    assert load_tile_settings(tmp_path) == DEFAULT_TILE_SETTINGS


def test_empty_tiles_table_returns_defaults(tmp_path: Path) -> None:
    """A present-but-empty ``[tiles]`` table -> every key defaults (Req 5.2)."""
    _write_settings(tmp_path, "[tiles]\n")

    assert load_tile_settings(tmp_path) == DEFAULT_TILE_SETTINGS


# --- Each key defaults independently (partial table) (Req 5.1, 5.3) ---------


def test_enabled_override_only(tmp_path: Path) -> None:
    """A lone ``enabled = false`` is the persistent opt-out; rest defaults (Req 5.3)."""
    _write_settings(tmp_path, "[tiles]\nenabled = false\n")

    result = load_tile_settings(tmp_path)

    assert result == TileSettings(
        enabled=False,
        name=DEFAULT_TILE_SETTINGS.name,
        url_template=DEFAULT_TILE_SETTINGS.url_template,
        attribution=DEFAULT_TILE_SETTINGS.attribution,
    )


def test_name_override_only(tmp_path: Path) -> None:
    """A lone ``name`` overrides only the cache slug; rest defaults (Req 5.1)."""
    _write_settings(tmp_path, '[tiles]\nname = "opentopomap"\n')

    result = load_tile_settings(tmp_path)

    assert result.name == "opentopomap"
    assert result.enabled is DEFAULT_TILE_SETTINGS.enabled
    assert result.url_template == DEFAULT_TILE_SETTINGS.url_template
    assert result.attribution == DEFAULT_TILE_SETTINGS.attribution


def test_url_override_only(tmp_path: Path) -> None:
    """A lone ``url`` overrides only ``url_template`` (TOML key -> field) (Req 5.1)."""
    _write_settings(
        tmp_path,
        '[tiles]\nurl = "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"\n',
    )

    result = load_tile_settings(tmp_path)

    assert result.url_template == "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"
    assert result.name == DEFAULT_TILE_SETTINGS.name
    assert result.enabled is DEFAULT_TILE_SETTINGS.enabled
    assert result.attribution == DEFAULT_TILE_SETTINGS.attribution


def test_attribution_override_only(tmp_path: Path) -> None:
    """A lone ``attribution`` overrides only that text; rest defaults (Req 5.1)."""
    _write_settings(tmp_path, '[tiles]\nattribution = "Map data: OpenTopoMap"\n')

    result = load_tile_settings(tmp_path)

    assert result.attribution == "Map data: OpenTopoMap"
    assert result.name == DEFAULT_TILE_SETTINGS.name
    assert result.enabled is DEFAULT_TILE_SETTINGS.enabled
    assert result.url_template == DEFAULT_TILE_SETTINGS.url_template


def test_full_override_maps_every_key(tmp_path: Path) -> None:
    """A complete ``[tiles]`` table maps all four keys (``url`` -> ``url_template``)."""
    _write_settings(
        tmp_path,
        """
        [tiles]
        enabled = false
        name = "opentopomap"
        url = "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"
        attribution = "Map data: OpenTopoMap"
        """,
    )

    result = load_tile_settings(tmp_path)

    assert result == TileSettings(
        enabled=False,
        name="opentopomap",
        url_template="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution="Map data: OpenTopoMap",
    )


def test_reading_writes_nothing(tmp_path: Path) -> None:
    """Reading a valid file mutates nothing on disk (read-only by construction)."""
    _write_settings(tmp_path, '[tiles]\nname = "opentopomap"\n')
    before = _snapshot(tmp_path)

    load_tile_settings(tmp_path)

    assert _snapshot(tmp_path) == before


# --- Unknown keys / tables ignored (forward compatibility) (Req 5.1) --------


def test_unknown_keys_within_tiles_are_ignored(tmp_path: Path) -> None:
    """Unknown keys inside ``[tiles]`` are ignored, not an error (Req 5.1)."""
    _write_settings(
        tmp_path,
        """
        [tiles]
        name = "osm"
        future_option = "whatever"
        retina = true
        """,
    )

    result = load_tile_settings(tmp_path)

    assert result == DEFAULT_TILE_SETTINGS


def test_unknown_top_level_table_is_ignored(tmp_path: Path) -> None:
    """Unknown top-level tables are ignored -- future settings share the file."""
    _write_settings(
        tmp_path,
        """
        [tiles]
        enabled = false

        [charts]
        theme = "dark"

        [some_future_feature]
        anything = "goes"
        """,
    )

    result = load_tile_settings(tmp_path)

    assert result.enabled is False
    assert result.name == DEFAULT_TILE_SETTINGS.name


# --- Loud validation: url placeholders (Req 5.1) ----------------------------


def test_url_missing_all_placeholders_raises(tmp_path: Path) -> None:
    """A ``url`` without any ``{z}/{x}/{y}`` placeholders raises (Req 5.1)."""
    _write_settings(tmp_path, '[tiles]\nurl = "https://tiles.example.com/map.png"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_url_missing_one_placeholder_raises(tmp_path: Path) -> None:
    """A ``url`` missing even one of ``{z}/{x}/{y}`` raises (Req 5.1)."""
    _write_settings(
        tmp_path,
        '[tiles]\nurl = "https://tiles.example.com/{z}/{x}.png"\n',
    )

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


# --- Loud validation: name must be a path-safe slug (security) --------------


def test_name_with_slash_raises(tmp_path: Path) -> None:
    """A ``name`` with a path separator is rejected (cache-path traversal)."""
    _write_settings(tmp_path, '[tiles]\nname = "a/b"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_name_with_parent_traversal_raises(tmp_path: Path) -> None:
    """A ``name`` of ``../evil`` is rejected before it can form a cache path."""
    _write_settings(tmp_path, '[tiles]\nname = "../evil"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_name_with_uppercase_raises(tmp_path: Path) -> None:
    """An uppercase ``name`` does not match the path-safe slug pattern (Req 5.1)."""
    _write_settings(tmp_path, '[tiles]\nname = "OSM"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_name_with_leading_hyphen_raises(tmp_path: Path) -> None:
    """A ``name`` starting with a hyphen is not a valid slug (Req 5.1)."""
    _write_settings(tmp_path, '[tiles]\nname = "-osm"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_empty_name_raises(tmp_path: Path) -> None:
    """An empty ``name`` is not a valid slug and raises (Req 5.1)."""
    _write_settings(tmp_path, '[tiles]\nname = ""\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


# --- Loud validation: enabled must be a boolean (Req 5.3) -------------------


def test_string_enabled_raises(tmp_path: Path) -> None:
    """A string ``enabled`` is not a boolean and raises (Req 5.3)."""
    _write_settings(tmp_path, '[tiles]\nenabled = "true"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_integer_enabled_raises(tmp_path: Path) -> None:
    """An integer ``enabled`` is not a boolean and raises (bool-is-int guard)."""
    _write_settings(tmp_path, "[tiles]\nenabled = 1\n")

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


# --- Loud validation: wrong TOML types for string keys (Req 5.1) ------------


def test_non_string_name_raises(tmp_path: Path) -> None:
    """A non-string ``name`` raises rather than being coerced (Req 5.1)."""
    _write_settings(tmp_path, "[tiles]\nname = 123\n")

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_non_string_url_raises(tmp_path: Path) -> None:
    """A non-string ``url`` raises rather than being coerced (Req 5.1)."""
    _write_settings(tmp_path, "[tiles]\nurl = 123\n")

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


def test_non_string_attribution_raises(tmp_path: Path) -> None:
    """A non-string ``attribution`` raises rather than being coerced (Req 5.1)."""
    _write_settings(tmp_path, "[tiles]\nattribution = 123\n")

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


# --- Malformed TOML -> the shared, file-level SettingsError -----------------


def test_malformed_toml_raises(tmp_path: Path) -> None:
    """Invalid TOML raises the shared SettingsError, not a raw parse error.

    Invalid TOML is a property of the *file*, not of ``[tiles]``: the settings
    file is shared, so every table reader would otherwise report the same stray
    bracket in its own words and the user would see whichever ran first. The
    shared reader owns that message. ``TileSettingsError`` subclasses
    ``SettingsError``, so a caller catching the shared type still catches both.
    """
    _write_settings(tmp_path, '[tiles]\nname = = "osm"\nthis is not toml')

    with pytest.raises(SettingsError):
        load_tile_settings(tmp_path)


def test_tiles_not_a_table_raises(tmp_path: Path) -> None:
    """A ``tiles`` key that is a scalar rather than a table raises loudly."""
    _write_settings(tmp_path, 'tiles = "osm"\n')

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)


# --- Loud failures still write nothing (read-only by construction) ----------


def test_malformed_file_writes_nothing(tmp_path: Path) -> None:
    """Even on a raised error the reader writes nothing (read-only)."""
    _write_settings(tmp_path, '[tiles]\nurl = "https://example.com/no-placeholders"\n')
    before = _snapshot(tmp_path)

    with pytest.raises(TileSettingsError):
        load_tile_settings(tmp_path)

    assert _snapshot(tmp_path) == before


# ===========================================================================
# TileStore: cache-first resolve, polite fetch, opt-out gate (Req 3.1-3.4,
# 4.2, 5.4) -- exercised against a fake ``fetch`` so no test touches the
# network. Design: "TileStore (``src/fitdocs/tiles.py``)".
# ===========================================================================


def _tile_payload(url: str) -> bytes:
    """Deterministic fake tile bytes for *url* -- distinct per requested URL."""
    return f"PNGDATA::{url}".encode()


def _tile_url(settings: TileSettings, ref: TileRef) -> str:
    """The provider URL a store forms for *ref* (mirrors the store's own rule)."""
    return settings.url_template.format(z=ref.z, x=ref.x, y=ref.y)


def _seed_cache(
    data_root: Path, settings: TileSettings, ref: TileRef, data: bytes
) -> Path:
    """Pre-seed the on-disk cache for *ref* with *data*; return the cache path."""
    path = tile_cache_path(data_root, settings.name, ref.z, ref.x, ref.y)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _disabled(settings: TileSettings) -> TileSettings:
    """The same provider with the persistent opt-out active (``enabled = False``)."""
    return dataclasses.replace(settings, enabled=False)


class RecordingFetch:
    """A fake ``fetch`` recording every URL and returning deterministic bytes.

    URLs listed in *fail_urls* raise *error* instead of returning, standing in
    for offline / HTTP-error / timeout failures (all surface as the callable
    raising). ``calls`` preserves invocation order, so a test can assert
    cache-first order and that cached tiles were never requested.
    """

    def __init__(
        self,
        *,
        fail_urls: set[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._fail_urls = fail_urls or set()
        self._error = error or urllib.error.URLError("offline")

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self._fail_urls:
            raise self._error
        return _tile_payload(url)


def _forbidden_fetch(url: str) -> bytes:
    """A ``fetch`` that fails the test if the network is touched at all."""
    raise AssertionError(f"network must not be touched, but fetched {url!r}")


class _FakeResponse:
    """A minimal context-manager stand-in for a ``urlopen`` response."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


# --- Cache-first order + no-refetch (Req 3.2) -------------------------------


def test_cache_first_only_true_misses_are_fetched(tmp_path: Path) -> None:
    """A cached ref is read from disk; only true misses reach the fetch (Req 3.2)."""
    settings = DEFAULT_TILE_SETTINGS
    a, b, c = TileRef(14, 1, 1), TileRef(14, 2, 2), TileRef(14, 3, 3)
    cached_bytes = b"the-cached-b-tile"
    _seed_cache(tmp_path, settings, b, cached_bytes)
    fetch = RecordingFetch()
    store = TileStore(tmp_path, settings, fetch=fetch)

    result = store.resolve([a, b, c])

    # Every requested ref is covered; the cached one comes verbatim from disk.
    assert set(result) == {a, b, c}
    assert result[b] == cached_bytes
    assert result[a] == _tile_payload(_tile_url(settings, a))
    assert result[c] == _tile_payload(_tile_url(settings, c))
    # Only the two true misses were fetched, in request order; b never was.
    assert fetch.calls == [_tile_url(settings, a), _tile_url(settings, c)]


def test_second_resolve_of_same_set_fetches_nothing(tmp_path: Path) -> None:
    """After the first resolve caches misses, re-resolving fetches nothing (Req 3.2)."""
    settings = DEFAULT_TILE_SETTINGS
    refs = [TileRef(15, 10, 20), TileRef(15, 11, 20)]
    fetch = RecordingFetch()
    store = TileStore(tmp_path, settings, fetch=fetch)

    first = store.resolve(refs)
    assert len(fetch.calls) == 2

    fetch.calls.clear()
    second = store.resolve(refs)

    assert fetch.calls == []  # cached tiles are never re-requested
    assert second == first


def test_fully_cached_resolve_performs_zero_fetches(tmp_path: Path) -> None:
    """A resolve whose every ref is cached makes no network call (Req 3.2, 4.2)."""
    settings = DEFAULT_TILE_SETTINGS
    refs = [TileRef(12, 1, 2), TileRef(12, 2, 2)]
    for ref in refs:
        _seed_cache(tmp_path, settings, ref, _tile_payload(_tile_url(settings, ref)))
    store = TileStore(tmp_path, settings, fetch=_forbidden_fetch)

    result = store.resolve(refs)

    assert result == {ref: _tile_payload(_tile_url(settings, ref)) for ref in refs}


# --- User-agent + timeout on the real opener (Req 3.4) ----------------------


def test_default_fetch_sends_descriptive_user_agent_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default opener sets the mandatory UA and a 10 s timeout (Req 3.4).

    The installed version is patched to a distinguishable, non-real value
    (``fitdocs.version.version`` is the name :mod:`fitdocs.version` binds)
    and the header is asserted against the literal composed string -- not
    against a fresh call to :func:`_user_agent`, which would pass trivially
    for any implementation that merely repeats whatever the real function
    returns (self-referential compare).
    """
    monkeypatch.setattr(version_module, "version", lambda name: "9.9.9-fetch-patched")
    settings = DEFAULT_TILE_SETTINGS
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: Any = None) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(b"real-network-bytes")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    store = TileStore(tmp_path, settings)  # fetch defaults to the real opener
    ref = TileRef(13, 4, 5)

    result = store.resolve([ref])

    request = captured["request"]
    assert request.full_url == _tile_url(settings, ref)
    assert (
        request.get_header("User-agent")
        == "fitdocs/9.9.9-fetch-patched (+https://github.com/joshua-stauffer/fitdocs)"
    )
    assert captured["timeout"] == 10
    # Bytes from the opener are returned and written through to the cache.
    assert result[ref] == b"real-network-bytes"
    assert (
        tile_cache_path(tmp_path, settings.name, ref.z, ref.x, ref.y).read_bytes()
        == b"real-network-bytes"
    )


def test_user_agent_degrades_to_unknown_token_when_version_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """From an uninstalled source tree the User-Agent still names the project
    and carries the unknown token, rather than raising (Req 2.3, 2.4).

    ``_user_agent()`` composes from :func:`fitdocs.version.version_display`
    fresh on every call (no module-level caching, matching
    :mod:`fitdocs.version`'s own rule), so patching the underlying metadata
    lookup and calling it directly is sufficient -- no module reload needed.
    """
    real_agent = _user_agent()  # captured before patching, for the diff below

    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "version", _raise)

    degraded_agent = _user_agent()

    assert degraded_agent.startswith("fitdocs/unknown ")
    assert degraded_agent.endswith("(+https://github.com/joshua-stauffer/fitdocs)")
    # The real, resolved value differs -- proving this is not merely the
    # literal token embedded regardless of what version_display() returns.
    assert degraded_agent != real_agent


# --- Opt-out gate, both directions (Req 5.4) --------------------------------


def test_optout_miss_raises_and_never_fetches(tmp_path: Path) -> None:
    """Disabled + a cache miss raises, names 'disabled', and never fetches (Req 5.4)."""
    settings = _disabled(DEFAULT_TILE_SETTINGS)
    fetch = RecordingFetch()
    store = TileStore(tmp_path, settings, fetch=fetch)
    ref = TileRef(14, 7, 8)

    with pytest.raises(TileUnavailableError) as excinfo:
        store.resolve([ref])

    assert "disabled" in str(excinfo.value)
    assert "14/7/8" in str(excinfo.value)  # names the offending tile
    assert fetch.calls == []  # opt-out gates before any request


def test_optout_with_everything_cached_serves_from_cache(tmp_path: Path) -> None:
    """Disabled but fully cached still serves from cache -- no error (Req 5.4)."""
    settings = _disabled(DEFAULT_TILE_SETTINGS)
    refs = [TileRef(16, 100, 200), TileRef(16, 101, 200)]
    for ref in refs:
        _seed_cache(tmp_path, settings, ref, _tile_payload(_tile_url(settings, ref)))
    store = TileStore(tmp_path, settings, fetch=_forbidden_fetch)

    result = store.resolve(refs)

    assert result == {ref: _tile_payload(_tile_url(settings, ref)) for ref in refs}


# --- Fetch failure -> TileUnavailableError naming the cause (Req 3.4 -> 4.3) -


def test_fetch_failure_raises_tile_unavailable_naming_cause(tmp_path: Path) -> None:
    """A raising fetch (offline/HTTP/timeout) becomes TileUnavailableError (Req 3.4)."""
    settings = DEFAULT_TILE_SETTINGS
    ref = TileRef(14, 9, 9)
    url = _tile_url(settings, ref)
    boom = urllib.error.URLError("no route to host")
    fetch = RecordingFetch(fail_urls={url}, error=boom)
    store = TileStore(tmp_path, settings, fetch=fetch)

    with pytest.raises(TileUnavailableError) as excinfo:
        store.resolve([ref])

    message = str(excinfo.value)
    assert "14/9/9" in message  # names the tile
    assert "no route to host" in message  # names the cause
    assert excinfo.value.__cause__ is boom  # chained from the underlying failure


# --- Write-through atomicity (Req 3.1) --------------------------------------


def test_successful_fetch_writes_through_atomically(tmp_path: Path) -> None:
    """A fetched tile lands at its exact cache path with no leftover .tmp (Req 3.1)."""
    settings = DEFAULT_TILE_SETTINGS
    ref = TileRef(15, 21, 22)
    fetch = RecordingFetch()
    store = TileStore(tmp_path, settings, fetch=fetch)

    result = store.resolve([ref])

    target = tile_cache_path(tmp_path, settings.name, ref.z, ref.x, ref.y)
    expected = _tile_payload(_tile_url(settings, ref))
    assert target.is_file()
    assert target.read_bytes() == expected
    assert result[ref] == expected
    # No temp file is left behind anywhere under the tile cache.
    assert list(tmp_path.rglob("*.tmp")) == []


# --- Partial failure leaves already-fetched tiles cached (Req 3.1) ----------


def test_partial_failure_leaves_earlier_tiles_cached(tmp_path: Path) -> None:
    """When a later tile fails, tiles fetched before it stay cached (Req 3.1)."""
    settings = DEFAULT_TILE_SETTINGS
    a, b, c = TileRef(14, 1, 1), TileRef(14, 2, 1), TileRef(14, 3, 1)
    url_b = _tile_url(settings, b)
    fetch = RecordingFetch(fail_urls={url_b})
    store = TileStore(tmp_path, settings, fetch=fetch)

    with pytest.raises(TileUnavailableError):
        store.resolve([a, b, c])

    # a was fetched before b failed -> its write-through is durable.
    path_a = tile_cache_path(tmp_path, settings.name, a.z, a.x, a.y)
    assert path_a.is_file()
    assert path_a.read_bytes() == _tile_payload(_tile_url(settings, a))
    # b failed and c was never reached -> neither is cached.
    assert not tile_cache_path(tmp_path, settings.name, b.z, b.x, b.y).exists()
    assert not tile_cache_path(tmp_path, settings.name, c.z, c.x, c.y).exists()
    assert fetch.calls == [_tile_url(settings, a), url_b]  # stopped at the failure


# --- The store is a structural TileSource (the seam sync depends on) --------


def test_tilestore_satisfies_the_tile_source_seam(tmp_path: Path) -> None:
    """TileStore structurally implements the TileSource seam (attribution + resolve)."""
    source: TileSource = TileStore(
        tmp_path, DEFAULT_TILE_SETTINGS, fetch=_forbidden_fetch
    )

    assert source.attribution == DEFAULT_TILE_SETTINGS.attribution
