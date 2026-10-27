"""Chart-asset size budgets (compact-chart-assets Req 1.5, 7.3).

At task 1.4 only the fixture smoke tests are active. The four ``BASELINE_*``
constants are the sizes, in UTF-8 bytes, that the renderer produced for the
synthetic 1 h and 6 h activities at base f28316d7, before any change to the
line or map renderer. The budget assertions that compare the compacted
renderer against them are task 7.1.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
from pathlib import Path
from typing import Final

import pytest
from PIL import Image

from tests.fixtures import budget_activities as activities
from tests.fixtures import builder

# Pre-change sizes in UTF-8 bytes: the renderer at base f28316d7, before any
# change to the line or map renderer.
BASELINE_1H_HERO_BYTES: Final = 149_489
BASELINE_1H_DYNAMICS_BYTES: Final = 96_588
BASELINE_6H_HERO_BYTES: Final = 887_112
BASELINE_6H_DYNAMICS_BYTES: Final = 571_079

_FIXTURE_TILE_SIZE: Final = (16, 16)
_PRE_COMPACT: Final = Path(__file__).parent / "fixtures" / "pre_compact"
_POLYLINE: Final = re.compile(r'<polyline points="([^"]*)"')
_IMAGE_HREF: Final = re.compile(r'<image [^>]*href="([^"]*)"')

# (label, expected samples, with GPS): literal expectations, compared with what
# the generator module produces from its own duration constants.
_BASELINES: Final = {
    "1h": {"hero": BASELINE_1H_HERO_BYTES, "dynamics": BASELINE_1H_DYNAMICS_BYTES},
    "6h": {"hero": BASELINE_6H_HERO_BYTES, "dynamics": BASELINE_6H_DYNAMICS_BYTES},
}
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
