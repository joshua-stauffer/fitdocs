"""Behavioral + golden tests for the static hero-chart renderer.

These exercise :mod:`fitdocs.render.charts.hero`: the power-vs-HR hero graph of
``docs/reference/fitdocs-ai-reference.md`` section 3, rendered as static SVG
(Req 7.1, 7.4, 7.5). The renderer receives a fully-prepared
:class:`~fitdocs.render.charts.hero.HeroChartSpec` (series selection and x-axis
choice live in ``sections.py``, a later task) and produces deterministic SVG
text -- no matplotlib, no scripts, no hover.

The invariants under test:

* **Band normalization + overlay (7.4)** -- each series is boxcar-smoothed
  (``k=5``) then independently normalized into ``[0.42, 0.92]`` and overlaid;
  two active series -> exactly two series lines.
* **Faint elevation backdrop (7.4)** -- when a backdrop is present it renders as
  a filled area band (fill ``#888``, opacity ``0.18``) behind the series; when
  ``backdrop`` is ``None`` no such element exists.
* **Gaps render as gaps (7.5)** -- a series with ``None`` holes splits into
  MORE THAN ONE polyline segment, and no fabricated point bridges the gap (the
  total plotted points equal the count of non-``None`` samples).
* **Axis tick rules (7.4)** -- y-axis ticks appear ONLY when exactly one series
  is active (3 ticks mapped back to the metric's own units); two overlaid
  series show no y ticks.
* **Line style (7.4)** -- series lines are width ``1.8`` with no dot/marker
  elements; an in-SVG legend (swatch + label) replaces hover identification.
* **Determinism (7.1)** -- identical spec -> byte-identical SVG, matched against
  a committed golden per named case.
"""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs.render.charts.hero import (
    HeroChartSpec,
    HeroSeries,
    render_hero_chart,
)
from fitdocs.render.charts.series import boxcar_smooth
from fitdocs.render.charts.svg import fmt_num

GOLDEN_DIR = Path(__file__).parent / "golden"

# --- shared fixture data ----------------------------------------------------

X_KM: tuple[float, ...] = (
    0.0,
    0.25,
    0.5,
    0.75,
    1.0,
    1.25,
    1.5,
    1.75,
    2.0,
    2.25,
    2.5,
    2.75,
)
HR_FULL: tuple[float | None, ...] = (
    122.0,
    128.0,
    135.0,
    140.0,
    145.0,
    148.0,
    150.0,
    152.0,
    149.0,
    146.0,
    150.0,
    155.0,
)
POWER_FULL: tuple[float | None, ...] = (
    180.0,
    200.0,
    220.0,
    210.0,
    240.0,
    250.0,
    245.0,
    260.0,
    255.0,
    230.0,
    248.0,
    265.0,
)
ALT: tuple[float | None, ...] = (
    100.0,
    102.0,
    105.0,
    110.0,
    118.0,
    120.0,
    119.0,
    122.0,
    125.0,
    121.0,
    118.0,
    115.0,
)
# Three contiguous non-None runs (2 + 3 + 4 = 9 present samples) split by two
# gaps -- a sparse heart-rate stream (observed coverage as low as 62%).
HR_SPARSE: tuple[float | None, ...] = (
    120.0,
    122.0,
    None,
    None,
    138.0,
    142.0,
    145.0,
    None,
    150.0,
    152.0,
    148.0,
    151.0,
)

HR_COLOR = "#d5455f"
POWER_COLOR = "#cd6600"


def two_series_spec() -> HeroChartSpec:
    """HR + power overlaid, with the elevation backdrop present."""
    return HeroChartSpec(
        x=X_KM,
        x_unit="km",
        series=(
            HeroSeries("HR", "bpm", HR_COLOR, HR_FULL),
            HeroSeries("Power", "W", POWER_COLOR, POWER_FULL),
        ),
        backdrop=ALT,
    )


def single_series_spec() -> HeroChartSpec:
    """A single HR series (with backdrop) -- y ticks in metric units."""
    return HeroChartSpec(
        x=X_KM,
        x_unit="km",
        series=(HeroSeries("HR", "bpm", HR_COLOR, HR_FULL),),
        backdrop=ALT,
    )


def sparse_hr_spec() -> HeroChartSpec:
    """A single HR series with None holes -- gaps render as separate segments."""
    return HeroChartSpec(
        x=X_KM,
        x_unit="km",
        series=(HeroSeries("HR", "bpm", HR_COLOR, HR_SPARSE),),
        backdrop=None,
    )


def backdrop_less_spec() -> HeroChartSpec:
    """HR + power over elapsed minutes with NO backdrop band."""
    return HeroChartSpec(
        x=tuple(float(i) for i in range(12)),
        x_unit="min",
        series=(
            HeroSeries("HR", "bpm", HR_COLOR, HR_FULL),
            HeroSeries("Power", "W", POWER_COLOR, POWER_FULL),
        ),
        backdrop=None,
    )


#: The four observable cases -> golden basename.
GOLDEN_CASES: dict[str, HeroChartSpec] = {
    "two_series": two_series_spec(),
    "single_series": single_series_spec(),
    "sparse_hr": sparse_hr_spec(),
    "backdrop_less": backdrop_less_spec(),
}


def _points_tokens(svg: str) -> list[str]:
    """Every coordinate pair across every ``points="..."`` attribute."""
    tokens: list[str] = []
    for attr in re.findall(r'points="([^"]*)"', svg):
        tokens.extend(t for t in attr.split(" ") if t)
    return tokens


# --- structural: two-series overlay -----------------------------------------


def test_two_series_has_two_lines_two_legend_entries_no_y_ticks() -> None:
    svg = render_hero_chart(two_series_spec())
    # exactly two overlaid series lines, one per active metric
    assert svg.count("<polyline") == 2
    # both series colors present
    assert HR_COLOR in svg
    assert POWER_COLOR in svg
    # a legend with two entries replaces hover identification
    assert svg.count('class="legend-item"') == 2
    assert ">HR</text>" in svg
    assert ">Power</text>" in svg
    # no y-axis ticks when two series are overlaid (shared axis is meaningless)
    assert 'class="y-axis"' not in svg
    assert 'class="y-tick"' not in svg


def test_two_series_line_style_is_width_1_8_without_markers() -> None:
    svg = render_hero_chart(two_series_spec())
    assert 'stroke-width="1.8"' in svg
    # no dots / markers of any kind
    assert "<circle" not in svg
    assert "marker" not in svg
    # series lines are unfilled strokes
    assert 'fill="none"' in svg


# --- structural: single-series y ticks --------------------------------------


def test_single_series_shows_three_y_ticks_in_metric_units() -> None:
    svg = render_hero_chart(single_series_spec())
    assert svg.count("<polyline") == 1
    assert svg.count('class="legend-item"') == 1
    # y ticks present: exactly three, mapped back to the metric's own units
    assert 'class="y-axis"' in svg
    assert svg.count('class="y-tick"') == 3
    # band bottom/mid/top map back to the pre-normalization min/mid/max
    smoothed = boxcar_smooth(HR_FULL, k=5)
    present = [v for v in smoothed if v is not None]
    vmin, vmax = min(present), max(present)
    mid = (vmin + vmax) / 2
    for value in (vmin, mid, vmax):
        assert f"{fmt_num(value)} bpm" in svg


# --- structural: sparse gaps ------------------------------------------------


def test_sparse_series_renders_multiple_segments_without_bridging() -> None:
    svg = render_hero_chart(sparse_hr_spec())
    # a sparse series produces MORE THAN ONE polyline segment
    assert svg.count("<polyline") > 1
    # the three contiguous runs -> three segments
    assert svg.count("<polyline") == 3
    # no fabricated point bridges a gap: plotted points == non-None samples
    present_count = sum(1 for v in HR_SPARSE if v is not None)
    assert len(_points_tokens(svg)) == present_count


# --- structural: backdrop presence ------------------------------------------


def test_backdrop_present_renders_faint_area_band() -> None:
    svg = render_hero_chart(two_series_spec())
    assert 'class="backdrop"' in svg
    assert 'fill="#888"' in svg
    assert 'opacity="0.18"' in svg
    # the backdrop is a filled area (path), not a stroked line
    assert "<path" in svg


def test_backdrop_absent_renders_no_area_band() -> None:
    svg = render_hero_chart(backdrop_less_spec())
    assert 'class="backdrop"' not in svg
    assert 'fill="#888"' not in svg
    assert 'opacity="0.18"' not in svg


# --- static rendering: no scripts / hover -----------------------------------


def test_static_rendering_has_no_scripts_or_cursor() -> None:
    svg = render_hero_chart(two_series_spec())
    assert "<script" not in svg
    assert "onmouse" not in svg.lower()
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")


# --- determinism + golden ---------------------------------------------------


def test_render_is_byte_identical_across_calls() -> None:
    for spec in GOLDEN_CASES.values():
        assert render_hero_chart(spec) == render_hero_chart(spec)


def test_matches_committed_goldens() -> None:
    for name, spec in GOLDEN_CASES.items():
        golden = GOLDEN_DIR / f"{name}.svg"
        assert golden.exists(), f"missing golden: {golden}"
        assert render_hero_chart(spec) == golden.read_text(), (
            f"golden mismatch for {name}"
        )
