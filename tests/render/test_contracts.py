"""Constructability and immutability of the shared render contracts.

These pin the three frozen dataclasses every group-3 renderer consumes
(``Asset``, ``RenderedDoc``, ``DocContext``): each holds the values given and
rejects mutation. Their immutability underpins deterministic rendering (Req
4.1). ``DocContext`` is built over a real parsed activity and its derived
metrics to prove the contract composes with the fit-ingest public API.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, tzinfo

import pytest

from fitdocs import Activity, DerivedMetrics, compute_metrics, parse_fit
from fitdocs.render import Asset, DocContext, RenderedDoc


def _frozen_raises() -> object:
    """``FrozenInstanceError`` subclasses ``AttributeError``; accept either so
    the intent under test is immutability, not the exact exception class."""
    return pytest.raises((dataclasses.FrozenInstanceError, AttributeError))


def test_asset_holds_values_and_is_frozen() -> None:
    asset = Asset(rel_path="assets/2026-07-12-run-0730-hero.svg", content="<svg/>")
    assert asset.rel_path == "assets/2026-07-12-run-0730-hero.svg"
    assert asset.content == "<svg/>"
    with _frozen_raises():
        asset.rel_path = "assets/other.svg"  # type: ignore[misc]


def test_rendered_doc_holds_values_and_is_frozen() -> None:
    asset = Asset(rel_path="assets/x-hero.svg", content="<svg/>")
    doc = RenderedDoc(markdown="---\ntype: workout\n---\n# Title\n", assets=(asset,))
    assert doc.markdown == "---\ntype: workout\n---\n# Title\n"
    assert doc.assets == (asset,)
    with _frozen_raises():
        doc.markdown = "changed"  # type: ignore[misc]


def test_rendered_doc_allows_no_assets() -> None:
    doc = RenderedDoc(markdown="# Title\n", assets=())
    assert doc.assets == ()


def test_doc_context_holds_values_and_is_frozen(run_fit_bytes: bytes) -> None:
    activity = parse_fit(run_fit_bytes)
    metrics = compute_metrics(activity)
    tz: tzinfo = UTC
    ctx = DocContext(
        activity=activity,
        metrics=metrics,
        athlete=None,
        doc_stem="2026-07-12-run-0730",
        source_refs=("fit-archive/aaaa.fit", "fit-archive/bbbb.fit"),
        tz=tz,
    )
    assert isinstance(ctx.activity, Activity)
    assert isinstance(ctx.metrics, DerivedMetrics)
    assert ctx.athlete is None
    assert ctx.doc_stem == "2026-07-12-run-0730"
    # Append-ordered: the last ref is the current render source.
    assert ctx.source_refs == ("fit-archive/aaaa.fit", "fit-archive/bbbb.fit")
    assert ctx.source_refs[-1] == "fit-archive/bbbb.fit"
    assert ctx.tz is tz
    with _frozen_raises():
        ctx.doc_stem = "changed"  # type: ignore[misc]
