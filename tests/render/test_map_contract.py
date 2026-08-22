"""Contract for carrying prepared map inputs across the purity boundary.

Task 4.1 adds the frozen :class:`~fitdocs.render.MapData` value (a
:class:`~fitdocs.render.MapPlan`, its resolved tile bytes ordered exactly as the
plan, and the provider attribution) and a defaulted ``map_data`` field on
:class:`~fitdocs.render.DocContext`, and re-exports the planning types from the
package render surface. These tests pin three things:

* the sync engine's import surface is ``fitdocs.render`` -- ``MapData``,
  ``MapPlan``, ``TileRef``, and ``plan_map`` all resolve there, never from chart
  internals, and all four are advertised on ``__all__``;
* the new ``DocContext`` field defaults to ``None`` so every existing
  positional/keyword constructor call stays valid (the default keeps the
  existing render suite unchanged);
* ``MapData`` is a frozen value whose ``tiles`` are aligned to ``plan.tiles``
  order -- the ordering invariant determinism (Req 4.1) rests on.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC

import pytest

from fitdocs import compute_metrics, parse_fit

# The re-export surface itself: this import resolving is the contract under test
# (the engine imports map types from ``fitdocs.render``, not ``charts.map``).
from fitdocs.render import DocContext, MapData, MapPlan, TileRef, plan_map


def _tiny_plan() -> MapPlan:
    """A real :class:`MapPlan` over two nearby positions via ``plan_map``."""
    plan = plan_map([37.7749, 37.7752], [-122.4194, -122.4180])
    assert plan is not None  # both channels present at both indices
    return plan


def test_render_surface_reexports_planning_types() -> None:
    """``MapPlan``, ``TileRef``, ``plan_map`` are the real ``charts.map`` objects."""
    assert MapPlan.__module__ == "fitdocs.render.charts.map"
    assert TileRef.__module__ == "fitdocs.render.charts.map"
    assert callable(plan_map)
    # ``MapData`` is defined on the render surface itself.
    assert dataclasses.is_dataclass(MapData)


def test_all_lists_the_four_reexports() -> None:
    """Every re-exported name is advertised on ``fitdocs.render.__all__``."""
    import fitdocs.render as render_pkg

    for name in ("MapData", "MapPlan", "TileRef", "plan_map"):
        assert name in render_pkg.__all__


def test_doc_context_map_data_defaults_to_none(run_fit_bytes: bytes) -> None:
    """An existing constructor call (no ``map_data``) leaves the field ``None``."""
    activity = parse_fit(run_fit_bytes)
    metrics = compute_metrics(activity)
    ctx = DocContext(
        activity=activity,
        metrics=metrics,
        athlete=None,
        doc_stem="2026-07-12-run-0730",
        source_refs=("fit-archive/aaaa.fit",),
        tz=UTC,
    )
    assert ctx.map_data is None


def test_doc_context_round_trips_map_data(run_fit_bytes: bytes) -> None:
    """``map_data`` round-trips; ``MapData`` is frozen and plan-ordered."""
    activity = parse_fit(run_fit_bytes)
    metrics = compute_metrics(activity)
    plan = _tiny_plan()
    # Tiles aligned to ``plan.tiles`` order, the ordering invariant (Req 4.1).
    tiles: tuple[tuple[TileRef, bytes], ...] = tuple(
        (ref, b"\x89PNG-fake-tile") for ref in plan.tiles
    )
    map_data = MapData(
        plan=plan,
        tiles=tiles,
        attribution="© OpenStreetMap contributors",
    )
    ctx = DocContext(
        activity=activity,
        metrics=metrics,
        athlete=None,
        doc_stem="2026-07-12-run-0730",
        source_refs=("fit-archive/aaaa.fit",),
        tz=UTC,
        map_data=map_data,
    )
    assert ctx.map_data is map_data
    assert ctx.map_data.plan is plan
    assert ctx.map_data.attribution == "© OpenStreetMap contributors"
    # The tile keys are exactly ``plan.tiles``, in that order.
    assert tuple(ref for ref, _ in ctx.map_data.tiles) == plan.tiles

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        map_data.attribution = "changed"  # type: ignore[misc]
