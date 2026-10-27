"""Unit coverage for :func:`map_section` (route-maps task 4.2).

Pins the shared Map section's contract directly, without going through a whole
document: clean omission when no map data is present (Req 1.3), tint selection by
modality (Req 2.3), and the standard chart-asset naming and markdown image link
(Req 1.4, 6.2). The document-level placement (after Summary, before Telemetry;
map asset first; strength untouched) is pinned in
:mod:`tests.render.test_golden_docs`.

The basemap is the fixed fake value in ``tests/support/basemap.py`` -- no
basemap-provider tile is ever downloaded or committed. The map plan is built from
a short chosen route so the composition is deterministic and independent of any
fixture's own GPS channels.
"""

from __future__ import annotations

from datetime import timedelta, timezone, tzinfo

from fitdocs import compute_metrics, parse_fit
from fitdocs.layout import asset_rel_path
from fitdocs.render import Basemap, DocContext, MapData, plan_map
from fitdocs.render.charts.palette import (
    ROUTE_BIKE_TINT,
    ROUTE_NEUTRAL_TINT,
    ROUTE_RUN_TINT,
)
from fitdocs.render.sections import map_section
from tests.fixtures import builder
from tests.support.basemap import FAKE_BASEMAP

TZ: tzinfo = timezone(timedelta(hours=-6))

# A short, stable route (no gaps) and the OSM attribution -- enough for a valid,
# deterministic single-segment plan.
_LATS: tuple[float | None, ...] = (45.0, 45.0008, 45.0016)
_LONS: tuple[float | None, ...] = (10.0, 10.0010, 10.0016)
_ATTRIBUTION = "© OpenStreetMap contributors"


def _map_data() -> MapData:
    plan = plan_map(_LATS, _LONS)
    assert plan is not None
    return MapData(plan=plan, basemap=FAKE_BASEMAP, attribution=_ATTRIBUTION)


def _ctx(fit_bytes: bytes, map_data: MapData | None = None) -> DocContext:
    activity = parse_fit(fit_bytes)
    metrics = compute_metrics(activity, None)
    return DocContext(
        activity=activity,
        metrics=metrics,
        athlete=None,
        doc_stem="stem",
        source_refs=(),
        tz=TZ,
        map_data=map_data,
    )


def test_returns_none_without_map_data() -> None:
    """No prepared map inputs -> no section, no asset (Req 1.3)."""
    assert map_section(_ctx(builder.run_fit_bytes())) is None


def test_run_uses_run_tint() -> None:
    """A run tints the route with the running tint (Req 2.3)."""
    result = map_section(_ctx(builder.run_fit_bytes(), _map_data()))
    assert result is not None
    _, asset = result
    assert ROUTE_RUN_TINT in asset.content
    assert ROUTE_BIKE_TINT not in asset.content
    assert ROUTE_NEUTRAL_TINT not in asset.content


def test_ride_uses_bike_tint() -> None:
    """A ride tints the route with the cycling tint (Req 2.3)."""
    result = map_section(_ctx(builder.ride_no_power_fit_bytes(), _map_data()))
    assert result is not None
    _, asset = result
    assert ROUTE_BIKE_TINT in asset.content
    assert ROUTE_RUN_TINT not in asset.content
    assert ROUTE_NEUTRAL_TINT not in asset.content


def test_generic_uses_neutral_tint() -> None:
    """A non-run/ride (here the session-less generic file) uses the neutral tint."""
    result = map_section(_ctx(builder.minimal_fit_bytes(), _map_data()))
    assert result is not None
    _, asset = result
    assert ROUTE_NEUTRAL_TINT in asset.content
    assert ROUTE_RUN_TINT not in asset.content
    assert ROUTE_BIKE_TINT not in asset.content


def test_link_and_asset_use_chart_naming_conventions() -> None:
    """The markdown link and asset path follow the existing chart conventions
    (``assets/<stem>-map.svg``, Req 1.4, 6.2)."""
    result = map_section(_ctx(builder.run_fit_bytes(), _map_data()))
    assert result is not None
    link, asset = result
    expected_rel = asset_rel_path("stem", "map")
    assert expected_rel == "assets/stem-map.svg"
    assert asset.rel_path == expected_rel
    assert link == f"![Route map]({expected_rel})"
    assert asset.content.startswith("<svg")
    assert _ATTRIBUTION in asset.content or "OpenStreetMap" in asset.content


def test_section_embeds_the_map_datas_basemap_as_the_only_image() -> None:
    """The section passes ``MapData.basemap`` through to the one embedded image."""
    plan = plan_map(_LATS, _LONS)
    assert plan is not None
    # A basemap unlike FAKE_BASEMAP, so a pass-through of any other value differs.
    basemap = Basemap("image/x-test", b"\x00\x01\x02", -0.125, -0.5, 640.25, 400.75)
    data = MapData(plan=plan, basemap=basemap, attribution=_ATTRIBUTION)

    result = map_section(_ctx(builder.run_fit_bytes(), data))

    assert result is not None
    _, asset = result
    assert asset.content.count("<image") == 1
    assert (
        '<image x="-0.125" y="-0.5" width="640.25" height="400.75" '
        'href="data:image/x-test;base64,AAEC"/>'
    ) in asset.content
