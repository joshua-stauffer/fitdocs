"""User-facing statements of the compact map images (compact-chart-assets 6.2).

Pins the sentences a reader relies on: the install note for Pillow (Req 8.4),
the viewer floor and its consequences (Req 3.7, 8.5), the route-map
documentation (Req 9.3) and the release notes (Req 9.5).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from fitdocs import basemap
from tests._changelog_view import V0_2_0, read_unreleased_since

ROOT = Path(__file__).resolve().parents[1]


def _flat(path: str) -> str:
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


def _section(path: str, heading: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    body = text.split(f"\n## {heading}\n", 1)[1]
    return " ".join(body.split("\n## ", 1)[0].split())


def _unreleased() -> str:
    """Only the ``[Unreleased]`` section: an entry moved into a release is outside."""
    text = read_unreleased_since(ROOT / "CHANGELOG.md", V0_2_0)
    section = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    return " ".join(section.split())


def test_install_docs_name_pillow_its_size_and_the_source_build() -> None:
    install = _flat("docs/install.md")
    for phrase in (
        "Route maps add Pillow, which occupies about 12 MB installed",
        "A platform without a prebuilt Pillow package builds it from source, "
        "and a build from source may lack WebP support.",
        "stops with an error before it writes anything",
    ):
        assert phrase in install, phrase
    # The DuckDB note is still present in the install page.
    assert "The analytics index adds DuckDB, which occupies about 44 MB" in install


def test_compatibility_docs_state_the_viewer_floor() -> None:
    section = _section("docs/compatibility.md", "Map images")
    for phrase in (
        "Obsidian, desktop and mobile",
        "iA Writer",
        "GitHub",
        "GitHub, as an image in a rendered page",
        "Safari on iOS 14 or later and on macOS 11 or later",
        "shows the route, markers and attribution over a blank basemap",
        "The next `fitdocs regen` then rewrites the affected maps once",
    ):
        assert phrase in section, phrase


def test_changelog_names_the_contract_the_floor_and_the_regen_action() -> None:
    entry = _unreleased()
    for phrase in (
        "Chart files are much smaller.",
        "advances from version 16 to 17 (contract version 17)",
        "Safari on iOS 14 or macOS 11 and later",
        "over a blank basemap",
        "run `fitdocs regen` once to rewrite the chart files of an existing "
        "archive in the compact form",
        "page text is unchanged",
        "Later regens leave every chart file whose bytes are unchanged untouched.",
    ):
        assert phrase in entry, phrase


def test_changelog_dependency_floor_is_the_declared_one() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pillow = [d for d in manifest["project"]["dependencies"] if d.startswith("pillow")]
    assert pillow == ["pillow>=13.0.0"]
    assert f"`{pillow[0]}`" in _unreleased()


def test_route_map_docs_cover_the_four_statements() -> None:
    warning = "BasemapError: tile z/x/y cannot be decoded"
    for path in ("README.md", "docs/configuration.md"):
        text = _flat(path)
        assert "one basemap image" in text.lower(), path
        assert "cached" in text and "across maps" in text, path
        assert warning in text, path
        assert "WebP" in text, path
    assert (
        "composed and cropped to the area the map shows, at the tiles' own pixel "
        "density"
    ) in _flat("README.md")
    assert (
        "cropped to the map's visible area, at the highest pixel density among "
        "those tiles"
    ) in _flat("docs/configuration.md")
    assert "stops with an error before it writes anything" in _flat("README.md")
    assert "stop with exit code 2 before they write anything" in _flat(
        "docs/configuration.md"
    )


def test_docs_quote_the_code_constants() -> None:
    assert basemap.MAX_TILE_PX == 1024
    assert set(basemap.TILE_FORMATS) == {"PNG", "JPEG", "WEBP"}
    config = _flat("docs/configuration.md")
    assert "PNG, JPEG or WebP" in config
    assert "square with an edge of at most 1024 pixels" in config


def test_reference_records_the_static_adaptation() -> None:
    ref = _flat("docs/reference/fitdocs-ai-reference.md")
    assert "Static adaptation (compact-chart-assets)" in ref
    assert "within 0.5 output units of the drawn line" in ref
