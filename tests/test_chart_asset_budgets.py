"""Chart-asset size budgets (compact-chart-assets Req 1.5, 3.8, 7.3).

The four ``BASELINE_*`` constants are the sizes, in UTF-8 bytes, that the
renderer produced for the synthetic 1 h and 6 h activities at base f28316d7,
before any change to the line or map renderer. ``BUDGET_BYTES`` holds
the ceilings the compacted renderer must stay under, each the size measured at
landing (``MEASURED_BYTES``, macOS arm64) rounded up with 10-40% headroom.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
from pathlib import Path
from typing import Final, NamedTuple

import pytest
from PIL import Image

from tests.fixtures import budget_activities as activities
from tests.fixtures import builder
from tests.support import tiles as tile_factory

# Sizes of the compacted renderer's output, measured on macOS arm64 at task 7.1
# (the 1 h activity has GPS and a map over 256 px map-like tiles).
MEASURED_BYTES: Final = {
    "1h-hero": 24_514,
    "1h-dynamics": 26_272,
    "6h-hero": 47_218,
    "6h-dynamics": 51_951,
    "1h-map": 49_571,
}
BUDGET_BYTES: Final = {
    "1h-hero": 30_000,
    "1h-dynamics": 32_000,
    "6h-hero": 58_000,
    "6h-dynamics": 64_000,
    "1h-map": 61_000,
}
MIN_HEADROOM: Final = 0.10
MAX_HEADROOM: Final = 0.40
MIN_HERO_REDUCTION: Final = 0.75

# Pre-change sizes in UTF-8 bytes: the renderer at base f28316d7, before any
# change to the line or map renderer.
BASELINE_1H_HERO_BYTES: Final = 149_489
BASELINE_1H_DYNAMICS_BYTES: Final = 96_588
BASELINE_6H_HERO_BYTES: Final = 887_112
BASELINE_6H_DYNAMICS_BYTES: Final = 571_079

_FIXTURE_TILE_SIZE: Final = (16, 16)
_BUDGET_TILE_SIZE: Final = (256, 256)
_PRE_COMPACT: Final = Path(__file__).parent / "fixtures" / "pre_compact"
_POLYLINE: Final = re.compile(r'<polyline points="([^"]*)"')
_IMAGE_HREF: Final = re.compile(r'<image [^>]*href="([^"]*)"')

# (label, expected samples, with GPS).
_CASES: Final = (("1h", 3_600, True), ("6h", 21_600, False))


def _points_per_polyline(svg: str) -> list[int]:
    return [len(points.split()) for points in _POLYLINE.findall(svg)]


@pytest.mark.parametrize(("label", "samples", "gps"), _CASES)
def test_activity_has_every_channel_at_one_hertz(
    label: str, samples: int, gps: bool
) -> None:
    messages, errors = builder.decode_messages(
        activities.activity_fit_bytes(
            {"1h": activities.ONE_HOUR_S, "6h": activities.SIX_HOURS_S}[label],
            gps=gps,
        )
    )
    records = messages["record_mesgs"]
    assert not errors
    assert len(records) == samples
    stamps = [r["timestamp"] for r in records]
    assert all(b - a == 1 for a, b in zip(stamps, stamps[1:], strict=False))
    for channel in (
        "heart_rate",
        "power",
        "enhanced_speed",
        "enhanced_altitude",
        "vertical_oscillation",
        "stance_time",
    ):
        values = [r[channel] for r in records]
        assert all(v is not None for v in values), channel
        assert len(set(values)) > 20, f"{channel} is not varying"
    has_position = [r.get("position_lat") is not None for r in records]
    assert all(has_position) if gps else not any(has_position)


def _records_digest(fit: bytes) -> str:
    messages, errors = builder.decode_messages(fit)
    assert not errors
    rows = [
        sorted((key, value) for key, value in record.items() if isinstance(key, str))
        for record in messages["record_mesgs"]
    ]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def test_generated_activity_records_are_pinned() -> None:
    # Renderer-independent pin tying the generator to the committed fixtures and
    # baselines: it hashes the decoded record values (seed, noise, terrain,
    # track, channels), not the encoded .fit bytes, so a garmin-fit-sdk bump
    # that re-encodes identical records leaves it green.
    assert (
        _records_digest(activities.activity_fit_bytes(activities.ONE_HOUR_S, gps=True))
        == "121b1a7ca94ccd1f30a045ea652d3903ac5dea6403c8d3ba94f5bc482b2eaea4"
    )
    assert (
        _records_digest(
            activities.activity_fit_bytes(activities.SIX_HOURS_S, gps=False)
        )
        == "ad71c91e7dd414c03c6d902653993b04fa3b686f63af31e38cc0786feee361c3"
    )


def test_generator_tile_size_matches_the_committed_map_fixture() -> None:
    assert activities._TILE_SIZE == _FIXTURE_TILE_SIZE


def test_activity_bytes_are_deterministic_and_seeded() -> None:
    first = activities.activity_fit_bytes(600, gps=True)
    assert first == activities.activity_fit_bytes(600, gps=True)
    assert first != activities.activity_fit_bytes(600, gps=True, seed=1)


@pytest.mark.parametrize(("label", "samples", "gps"), _CASES)
def test_activity_renders_hero_and_dynamics_charts(
    label: str, samples: int, gps: bool
) -> None:
    duration = {"1h": activities.ONE_HOUR_S, "6h": activities.SIX_HOURS_S}[label]
    assets = activities.render_assets(activities.activity_fit_bytes(duration, gps=gps))
    assert ("map" in assets) is gps
    for kind in ("hero", "dynamics"):
        # Two series per chart, one polyline each. The lines are drawn at output
        # resolution, so each carries fewer points than the recorded samples;
        # the charts still render both series.
        counts = _points_per_polyline(assets[kind])
        assert len(counts) == 2, kind
        assert all(0 < count < samples for count in counts), kind


@pytest.mark.parametrize(
    ("kind", "baseline"),
    [
        ("hero", BASELINE_1H_HERO_BYTES),
        ("dynamics", BASELINE_1H_DYNAMICS_BYTES),
    ],
)
def test_committed_1h_fixture_has_the_recorded_baseline_size(
    kind: str, baseline: int
) -> None:
    svg = (_PRE_COMPACT / f"1h-{kind}.svg").read_text(encoding="utf-8")
    assert len(svg.encode("utf-8")) == baseline
    assert _points_per_polyline(svg) == [3_600, 3_600]


def test_baselines_are_ordered_by_duration() -> None:
    assert BASELINE_6H_HERO_BYTES > BASELINE_1H_HERO_BYTES > 0
    assert BASELINE_6H_DYNAMICS_BYTES > BASELINE_1H_DYNAMICS_BYTES > 0


def test_committed_map_fixture_embeds_decodable_synthetic_tiles() -> None:
    svg = (_PRE_COMPACT / "1h-map.svg").read_text(encoding="utf-8")
    hrefs = _IMAGE_HREF.findall(svg)
    assert len(hrefs) >= 4, "the map has no basemap tiles"
    prefix = "data:image/png;base64,"
    for href in hrefs:
        assert href.startswith(prefix)  # an embedded data URI, not an external URL
        with Image.open(io.BytesIO(base64.b64decode(href[len(prefix) :]))) as tile:
            assert tile.format == "PNG"
            assert tile.size == _FIXTURE_TILE_SIZE
    # The route is drawn over the tiles: a halo and a line, one point per sample.
    assert _points_per_polyline(svg) == [3_600, 3_600]


class _Rendered(NamedTuple):
    assets: dict[str, dict[str, str]]
    stubs: dict[str, tile_factory.FetchStub]  # the tile fetcher each render used


@pytest.fixture(scope="module")
def rendered() -> _Rendered:
    """Assets by activity label; the 1 h map is built over 256 px map-like tiles."""
    stubs: dict[str, tile_factory.FetchStub] = {}
    real_fetch_stub = tile_factory.fetch_stub
    assets: dict[str, dict[str, str]] = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(activities, "_TILE_SIZE", _BUDGET_TILE_SIZE)
        for label, _, gps in _CASES:

            def recording_stub(
                size: tuple[int, int], label: str = label
            ) -> tile_factory.FetchStub:
                stubs[label] = real_fetch_stub(size)
                return stubs[label]

            patch.setattr(tile_factory, "fetch_stub", recording_stub)
            assets[label] = activities.render_assets(
                activities.activity_fit_bytes(
                    {"1h": activities.ONE_HOUR_S, "6h": activities.SIX_HOURS_S}[label],
                    gps=gps,
                )
            )
    return _Rendered(assets, stubs)


def _size(assets: dict[str, dict[str, str]], key: str) -> int:
    label, kind = key.split("-")
    return len(assets[label][kind].encode("utf-8"))


def test_budget_table_covers_exactly_the_measured_assets() -> None:
    assert set(BUDGET_BYTES) == set(MEASURED_BYTES)
    assert len(BUDGET_BYTES) == 5


@pytest.mark.parametrize("key", sorted(BUDGET_BYTES))
def test_each_budget_headroom_is_between_10_and_40_percent(key: str) -> None:
    headroom = BUDGET_BYTES[key] / MEASURED_BYTES[key] - 1
    assert MIN_HEADROOM <= headroom <= MAX_HEADROOM, f"{key}: {headroom:.1%}"


@pytest.mark.parametrize("key", sorted(BUDGET_BYTES))
def test_chart_stays_within_budget_and_budget_is_not_loose(
    rendered: _Rendered, key: str
) -> None:
    size = _size(rendered.assets, key)
    assert size <= BUDGET_BYTES[key], f"{key}: {size} > {BUDGET_BYTES[key]}"
    # Judged against the live size: a budget more than 40% above it fails,
    # even when MEASURED_BYTES was not updated.
    assert BUDGET_BYTES[key] <= size * (1 + MAX_HEADROOM), (
        f"{key}: budget {BUDGET_BYTES[key]} is more than 40% above {size}"
    )


def test_1h_hero_is_at_least_75_percent_smaller_than_the_baseline(
    rendered: _Rendered,
) -> None:
    size = _size(rendered.assets, "1h-hero")
    reduction = 1 - size / BASELINE_1H_HERO_BYTES
    assert reduction >= MIN_HERO_REDUCTION, f"{reduction:.1%}"


def test_map_budget_is_measured_over_map_like_tiles_in_webp(
    rendered: _Rendered,
) -> None:
    # The tiles the map was built from are the 8 z15 tiles actually fetched,
    # each 256 px and drawn rather than solid (the stub is deterministic per
    # URL, so a fresh one returns the bytes the map was built from).
    urls = rendered.stubs["1h"].urls
    assert len(urls) == 8
    assert len(set(urls)) == 8
    fetched = rendered.stubs["1h"]
    assert fetched.size == _BUDGET_TILE_SIZE
    stub = tile_factory.fetch_stub(fetched.size)
    for url in urls:
        assert "/15/" in url, url
        with Image.open(io.BytesIO(stub(url))) as tile:
            assert tile.size == _BUDGET_TILE_SIZE
            colours = tile.convert("RGB").getcolors(maxcolors=1 << 16)
            assert colours is not None and len(colours) >= 5
            assert max(n for n, _ in colours) < 0.9 * 256 * 256  # no flat fill
    # The map embeds one WebP basemap, decoded here, which is not flat either.
    hrefs = _IMAGE_HREF.findall(rendered.assets["1h"]["map"])
    assert len(hrefs) == 1
    prefix = "data:image/webp;base64,"
    assert hrefs[0].startswith(prefix)
    with Image.open(io.BytesIO(base64.b64decode(hrefs[0][len(prefix) :]))) as basemap:
        assert basemap.format == "WEBP"
        assert basemap.size[0] > 256
        colours = basemap.convert("RGB").getcolors(maxcolors=1 << 20)
        assert colours is None or len(colours) > 50
