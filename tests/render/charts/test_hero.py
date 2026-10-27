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
  MORE THAN ONE polyline segment, and no fabricated point bridges the gap; each
  segment is thinned on its own and keeps its own first and last point.
* **Lines at output resolution (compact-chart-assets 1.1-1.4)** -- every
  full-resolution point lies within 0.5 output units of the drawn line, each
  segment keeps its endpoints, the backdrop's baseline closure uses the thinned
  first and last x, and with point data removed the thinned and unthinned
  renderings are identical.
* **Axis tick rules (7.4)** -- y-axis ticks appear ONLY when exactly one series
  is active (3 ticks mapped back to the metric's own units); two overlaid
  series show no y ticks.
* **Line style (7.4)** -- series lines are width ``1.8`` with no dot/marker
  elements; an in-SVG legend (swatch + label) replaces hover identification.
* **Determinism (7.1)** -- identical spec -> byte-identical SVG, matched against
  a committed golden per named case.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import replace
from pathlib import Path

import pytest

import fitdocs.render.charts.hero as hero_module
from fitdocs.render.charts.hero import (
    HeroChartSpec,
    HeroSeries,
    render_hero_chart,
)
from fitdocs.render.charts.series import boxcar_smooth, gap_segments, normalize_band
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
    # no fabricated point bridges a gap: every drawn point is within tolerance
    # of the full-resolution points of ITS OWN segment, and each segment keeps
    # its own first and last point.
    spec = sparse_hr_spec()
    full = _full_resolution_series(spec)[0]
    drawn = _drawn_polylines(svg)
    assert len(drawn) == len(full) == 3
    for pts, ref in zip(drawn, full, strict=True):
        assert pts[0] == _round1(ref[0]) and pts[-1] == _round1(ref[-1])
        _assert_within_tolerance(ref, pts)


# --- thinning (compact-chart-assets 1.1-1.4) ---------------------------------


def _round1(p: tuple[float, float]) -> tuple[float, float]:
    return (round(p[0], 1), round(p[1], 1))


def _full_resolution_series(
    spec: HeroChartSpec,
) -> list[list[list[tuple[float, float]]]]:
    """Per series, per gap segment, the un-thinned output-unit points.

    Re-derives the renderer's mapping (smooth, normalize, layout) from the spec
    without calling the simplifier.
    """
    layout = hero_module._resolve_layout(spec)
    out: list[list[list[tuple[float, float]]]] = []
    for s in spec.series:
        norm = normalize_band(boxcar_smooth(s.values, 5), 0.42, 0.92)
        out.append(
            [
                [(layout.x_px(xv), layout.y_px(n)) for xv, n in seg]
                for seg in gap_segments(spec.x, norm)
            ]
        )
    return out


def _parse_pairs(text: str) -> list[tuple[float, float]]:
    return [
        (float(a), float(b))
        for a, b in (t.split(",") for t in text.replace("M", " ").split() if "," in t)
    ]


def _drawn_polylines(svg: str) -> list[list[tuple[float, float]]]:
    return [_parse_pairs(m) for m in re.findall(r'<polyline points="([^"]*)"', svg)]


def _dist_to_segment(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    if n == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _assert_within_tolerance(
    full: list[tuple[float, float]], drawn: list[tuple[float, float]]
) -> None:
    """Every full-resolution point is within 0.5 output units of the drawn line."""
    worst = 0.0
    for p in full:
        if len(drawn) == 1:
            d = math.hypot(p[0] - drawn[0][0], p[1] - drawn[0][1])
        else:
            d = min(
                _dist_to_segment(p, a, b)
                for a, b in zip(drawn, drawn[1:], strict=False)
            )
        worst = max(worst, d)
    assert worst <= 0.5, worst


def dense_spec(seed: int = 7, n: int = 1500, with_gap: bool = False) -> HeroChartSpec:
    """A 1500-sample activity: about two samples per plotted pixel, noisy HR.

    Pairwise-distinct, non-monotone series values; the x axis is irregular so
    plotted x coordinates carry a nonzero second decimal.
    """
    rng = random.Random(seed)
    x = tuple(round(i * 0.00731 + rng.random() * 0.002, 5) for i in range(n))
    hr: list[float | None] = [
        140.0 + 25.0 * math.sin(i / 90.0) + rng.gauss(0.0, 1.2) for i in range(n)
    ]
    power: list[float | None] = [
        220.0 + 60.0 * math.sin(i / 37.0) + rng.gauss(0.0, 9.0) for i in range(n)
    ]
    if with_gap:
        for i in range(400, 460):
            hr[i] = None
    alt = tuple(100.0 + 30.0 * math.sin(i / 300.0) + rng.random() for i in range(n))
    return HeroChartSpec(
        x=x,
        x_unit="km",
        series=(
            HeroSeries("HR", "bpm", HR_COLOR, tuple(hr)),
            HeroSeries("Power", "W", POWER_COLOR, tuple(power)),
        ),
        backdrop=alt,
    )


def test_dense_lines_are_thinned_and_within_tolerance_of_full_resolution() -> None:
    spec = dense_spec(with_gap=True)
    svg = render_hero_chart(spec)
    full = [seg for per_series in _full_resolution_series(spec) for seg in per_series]
    drawn = _drawn_polylines(svg)
    assert len(drawn) == len(full) == 3  # HR is split once by the gap; power is whole
    for pts, ref in zip(drawn, full, strict=True):
        # precondition: the full-resolution run is dense, so thinning is real
        assert len(ref) >= 400
        assert len(pts) < len(ref) / 2
        assert len(pts) > 2  # a real curve is not collapsed to its chord
        assert pts[0] == _round1(ref[0]) and pts[-1] == _round1(ref[-1])
        _assert_within_tolerance(ref, pts)


def test_each_gap_segment_is_thinned_on_its_own() -> None:
    # A single straight ramp with a hole in the middle: each side thins to a
    # few vertices, and the points that border the hole must stay drawn.
    n = 200
    hr: list[float | None] = [100.0 + i * 0.5 for i in range(n)]
    for i in range(80, 120):
        hr[i] = None
    spec = HeroChartSpec(
        x=tuple(i * 0.0173 for i in range(n)),
        x_unit="km",
        series=(HeroSeries("HR", "bpm", HR_COLOR, tuple(hr)),),
        backdrop=None,
    )
    svg = render_hero_chart(spec)
    full = _full_resolution_series(spec)[0]
    drawn = _drawn_polylines(svg)
    assert len(full) == len(drawn) == 2
    for pts, ref in zip(drawn, full, strict=True):
        assert len(ref) > 50
        assert len(pts) < len(ref) / 5  # a ramp thins to a handful of vertices
        # the segment's own first and last sample are drawn: nothing was dropped
        # at the gap edge and nothing was drawn across it
        assert pts[0] == _round1(ref[0]) and pts[-1] == _round1(ref[-1])
        _assert_within_tolerance(ref, pts)
    gap_left = full[0][-1][0]
    gap_right = full[1][0][0]
    assert gap_right - gap_left > 5  # precondition: the hole is wide on screen
    for pts in drawn:
        assert not any(gap_left + 0.1 < p[0] < gap_right - 0.1 for p in pts)


def _backdrop_paths(svg: str) -> list[str]:
    return re.findall(r'<path d="([^"]*)"', svg)


def test_backdrop_outline_is_thinned_and_closure_uses_thinned_end_x() -> None:
    base = dense_spec(with_gap=False)
    assert base.backdrop is not None
    # Absent altitude at both ends puts the outline's end points inside the
    # plot, where their x is not a whole number of output units.
    trimmed = (None,) * 31 + base.backdrop[31:-26] + (None,) * 26
    spec = replace(base, backdrop=trimmed)
    svg = render_hero_chart(spec)
    layout = hero_module._resolve_layout(spec)
    assert spec.backdrop is not None
    norm = normalize_band(boxcar_smooth(spec.backdrop, 5), 0.0, 0.32)
    (full_seg,) = gap_segments(spec.x, norm)
    ref = [(layout.x_px(xv), layout.y_px(n)) for xv, n in full_seg]
    (d,) = _backdrop_paths(svg)
    tokens = d.split()
    assert tokens[0].startswith("M") and tokens[-1] == "Z"
    assert tokens[-2].startswith("L") and tokens[-3].startswith("L")
    outline = _parse_pairs(" ".join(tokens[:-3]).replace("L", " "))
    assert len(outline) < len(ref) / 2  # precondition: the outline really thinned
    _assert_within_tolerance(ref, outline)
    baseline = fmt_num(layout.y_px(0.0))
    last_x, first_x = (fmt_num(outline[-1][0]), fmt_num(outline[0][0]))
    assert tokens[-3] == f"L{last_x},{baseline}"
    assert tokens[-2] == f"L{first_x},{baseline}"
    # precondition: the un-thinned end x differs from its 1-decimal rounding, so
    # a closure drawn at the full-resolution x cannot pass for the thinned one
    assert fmt_num(ref[-1][0]) != last_x and fmt_num(ref[0][0]) != first_x


def _strip_point_data(svg: str) -> str:
    svg = re.sub(r'points="[^"]*"', 'points=""', svg)
    return re.sub(r'<path d="[^"]*"', '<path d=""', svg)


@pytest.mark.parametrize("with_gap", [False, True])
def test_with_point_data_removed_thinned_equals_unthinned(
    monkeypatch: pytest.MonkeyPatch, with_gap: bool
) -> None:
    spec = dense_spec(with_gap=with_gap)
    thinned = render_hero_chart(spec)
    monkeypatch.setattr(hero_module, "thin", lambda pts: tuple(pts))
    unthinned = render_hero_chart(spec)
    # precondition: the two renderings really differ in their point data
    assert len(thinned) < len(unthinned) / 2
    stripped = _strip_point_data(thinned)
    assert stripped == _strip_point_data(unthinned)
    # and the comparison is not vacuous: axes, ticks and legend survive it
    assert stripped.count('class="legend-item"') == 2
    assert stripped.count("<polyline") == (3 if with_gap else 2)
    assert stripped.count('class="x-tick"') == 6


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


def main() -> None:
    """Rewrite every hero golden from the shared cases above.

    Run as ``python -m tests.render.charts.test_hero`` after an intended change
    to the hero renderer; the tests read these files back and compare bytes.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name, spec in GOLDEN_CASES.items():
        path = GOLDEN_DIR / f"{name}.svg"
        path.write_text(render_hero_chart(spec), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
