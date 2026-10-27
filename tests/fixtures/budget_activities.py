"""Synthetic budget activities and the pre-change chart-asset generator.

compact-chart-assets task 1.4 (Req 1.5, 7.3). Two deterministic ``.fit``
activities at one sample per second are built in memory through
:func:`tests.fixtures.builder.developer_field_run_fit_bytes`:

* 1 hour (3 600 samples), carrying a synthetic GPS track;
* 6 hours (21 600 samples), without one.

Both carry heart rate, running power, speed, altitude (smooth terrain plus
bounded noise) and two native running-dynamics channels (vertical oscillation
and stance time). Every random draw comes from a private ``random.Random``
seeded per call; no wall-clock time is read.

The GPS track is an ellipse of about 1.3 km north-south by 1.9 km east-west
(about 5.1 km per lap), traced 2.25 times in the hour: about 12.0 km of track,
measured, against 11.5 km of recorded distance. It is centred on latitude 0,
longitude 0 (open ocean in the Gulf of Guinea) with bounded jitter, and
represents no real route or place. The basemap tiles are the factory's
procedurally drawn map-like tiles (``tests/support/tiles.py``), not tiles from
any provider.

Running this module as a script regenerates the committed pre-change fixtures::

    uv run python -m tests.fixtures.budget_activities tests/fixtures/pre_compact

:func:`render_assets` drives the real ``sync`` pipeline over a temporary data
root, so the bytes are whatever the renderer of the checked-out tree produces.
The files in ``pre_compact/`` are the output of the renderer as it stood at base
f28316d7, before any change to the line or map renderer, and must not be
regenerated once a later task alters the hero, dynamics or map renderer.
"""

from __future__ import annotations

import math
import random
import sys
import tempfile
from datetime import timedelta, timezone
from pathlib import Path
from typing import Final

from fitdocs.athlete import load_athlete_inputs
from fitdocs.sync import sync
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileStore
from tests.fixtures import builder
from tests.support import tiles as tile_factory

__all__ = [
    "ASSET_KINDS",
    "ONE_HOUR_S",
    "SIX_HOURS_S",
    "activity_fit_bytes",
    "render_assets",
    "write_fixtures",
]

ONE_HOUR_S: Final = 3_600
SIX_HOURS_S: Final = 6 * 3_600
ASSET_KINDS: Final = ("hero", "dynamics", "map")

_SERIAL: Final = 1401
_TZ: Final = timezone(timedelta(hours=-6))
_TILE_SIZE: Final = (16, 16)
_CENTRE_LAT: Final = 0.0
_CENTRE_LON: Final = 0.0
_SEMI_AXIS_LAT_DEG: Final = 0.0060
_SEMI_AXIS_LON_DEG: Final = 0.0085
_LAP_PERIOD_S: Final = 1_600


def activity_fit_bytes(duration_s: int, *, gps: bool, seed: int = 20260101) -> bytes:
    """A *duration_s*-second run at 1 Hz; *gps* adds the synthetic ellipse track."""
    rng = random.Random(seed + duration_s)
    records: list[tuple[dict[str, object], dict[int, object]]] = []
    distance = 0.0
    hr = 140.0
    for i in range(duration_s):
        phase = 2 * math.pi * i / duration_s
        speed = 3.2 + 0.4 * math.sin(7 * phase) + rng.uniform(-0.15, 0.15)
        distance += speed
        hr = (
            0.97 * hr + 0.03 * (150 + 12 * math.sin(5 * phase)) + rng.uniform(-0.8, 0.8)
        )
        record: dict[str, object] = {
            "distance": round(distance, 2),
            "enhanced_speed": round(speed, 3),
            "enhanced_altitude": round(
                120
                + 40 * math.sin(3 * phase)
                + 8 * math.sin(41 * phase)
                + rng.uniform(-0.5, 0.5),
                1,
            ),
            "heart_rate": round(hr),
            "power": round(250 + 30 * math.sin(11 * phase) + rng.uniform(-8, 8)),
            "vertical_oscillation": round(
                88 + 6 * math.sin(13 * phase) + rng.uniform(-1.5, 1.5), 1
            ),
            "stance_time": round(
                245 + 14 * math.sin(9 * phase) + rng.uniform(-3, 3), 1
            ),
        }
        if gps:
            angle = 2 * math.pi * i / _LAP_PERIOD_S
            drift = 0.00002 * (i / duration_s)
            record["position_lat"] = builder.to_semicircles(
                _CENTRE_LAT
                + _SEMI_AXIS_LAT_DEG * math.sin(angle)
                + drift
                + rng.uniform(-0.00001, 0.00001)
            )
            record["position_long"] = builder.to_semicircles(
                _CENTRE_LON
                + _SEMI_AXIS_LON_DEG * math.cos(angle)
                + rng.uniform(-0.00001, 0.00001)
            )
        records.append((record, {}))
    return builder.developer_field_run_fit_bytes(
        descriptions=(),
        records=records,
        serial=_SERIAL,
        session_distance_m=round(distance, 2),
    )


def render_assets(fit: bytes) -> dict[str, str]:
    """Sync *fit* with the current renderer; return its SVG assets by kind.

    Keys are the members of :data:`ASSET_KINDS` that were written; a kind the
    renderer did not produce is absent (for example ``map`` without GPS).
    """
    with tempfile.TemporaryDirectory(prefix="fitdocs-budget-") as scratch:
        root = Path(scratch)
        source, data_root = root / "source", root / "data"
        source.mkdir()
        (source / "activity.fit").write_bytes(fit)
        report = sync(
            source,
            data_root,
            athlete=load_athlete_inputs(data_root),
            tz=_TZ,
            tiles=TileStore(
                data_root,
                DEFAULT_TILE_SETTINGS,
                fetch=tile_factory.fetch_stub(_TILE_SIZE),
            ),
        )
        if report.failures:
            raise RuntimeError(f"sync failed: {report.failures}")
        assets: dict[str, str] = {}
        for path in sorted((data_root / "workouts" / "assets").glob("*.svg")):
            for kind in ASSET_KINDS:
                if path.stem.endswith(f"-{kind}"):
                    assets[kind] = path.read_text(encoding="utf-8")
        return assets


def write_fixtures(out_dir: Path) -> None:
    """Write the 1 h activity's hero, dynamics and map SVGs into *out_dir*."""
    assets = render_assets(activity_fit_bytes(ONE_HOUR_S, gps=True))
    missing = [kind for kind in ASSET_KINDS if kind not in assets]
    if missing:
        raise RuntimeError(f"renderer produced no {missing} asset")
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in ASSET_KINDS:
        (out_dir / f"1h-{kind}.svg").write_text(assets[kind], encoding="utf-8")


if __name__ == "__main__":
    write_fixtures(Path(sys.argv[1]))
