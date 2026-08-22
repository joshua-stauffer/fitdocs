"""Behavioral + golden tests for the HR time-in-zone strip renderer.

These exercise :mod:`fitdocs.render.charts.zones`: the horizontal stacked
time-in-zone strip of ``docs/reference/fitdocs-ai-reference.md`` section 3,
rendered as static SVG (Req 8.1, 8.2). The renderer receives already-computed
zone times (``ZoneBand`` values whose ``seconds`` come from fit-ingest's
``hr_time_in_zone_s`` and whose ``color`` the caller picked from the palette);
it holds no zone boundaries and invents no colors, counts, or defaults.

The invariants under test:

* **No output without supplied zone times (8.1, 8.2)** -- ``render_zone_strip([])``
  returns the empty string, and so does an all-absent (total-zero) input: with
  no computed zone times the strip does not exist.
* **Proportional stacked bands (8.1)** -- each band's colored segment width is
  proportional to ``seconds / total``; a zone with 3x the seconds gets ~3x the
  width, and the segments tile the full strip width with no gaps.
* **Label + duration + percent per band (8.1)** -- every band shows its label,
  its ``h:mm`` duration, and its percentage of the total; the passed-in colors
  appear.
* **Zero-time bands keep the label without width (8.1)** -- a zone the athlete
  spent no time in is still listed at ``0:00`` / ``0%`` but consumes no
  proportional segment, leaving the other bands' widths untouched.
* **Determinism (4.1 by extension)** -- identical bands -> byte-identical SVG,
  matched against a committed golden.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs.render.charts.zones import ZoneBand, render_zone_strip

GOLDEN_DIR = Path(__file__).parent / "golden"

# The five documented zone-ramp colors (cool -> hot); the caller supplies these.
Z_COLORS: tuple[str, ...] = (
    "#2f8adc",
    "#32b36e",
    "#d5bf36",
    "#e87f25",
    "#e64343",
)

# A realistic five-zone session totalling 12000 s (200 min): clean 10/20/30/25/15
# percentages and h:mm durations, with Z3 at exactly 1:00 to exercise the hour
# rollover. Widths over an 800 px strip are 80/160/240/200/120 (sum 800).
FIVE_SECONDS: tuple[float, ...] = (1200.0, 2400.0, 3600.0, 3000.0, 1800.0)

# The same session with Z5 emptied (its 1800 s moved into Z4): 10/20/30/40/0.
ZERO_SECONDS: tuple[float, ...] = (1200.0, 2400.0, 3600.0, 4800.0, 0.0)


def five_bands() -> tuple[ZoneBand, ...]:
    return tuple(
        ZoneBand(f"Z{i + 1}", secs, Z_COLORS[i]) for i, secs in enumerate(FIVE_SECONDS)
    )


def zero_bands() -> tuple[ZoneBand, ...]:
    return tuple(
        ZoneBand(f"Z{i + 1}", secs, Z_COLORS[i]) for i, secs in enumerate(ZERO_SECONDS)
    )


def _bar_widths(svg: str) -> list[float]:
    """Every segment width inside the proportional bar group, in order."""
    match = re.search(r'<g class="bar">(.*?)</g>', svg)
    assert match is not None, "bar group missing"
    return [float(w) for w in re.findall(r'width="([^"]*)"', match.group(1))]


def _percent_ints(svg: str) -> list[int]:
    return [int(p) for p in re.findall(r"(\d+)%", svg)]


# --- no output without supplied zone times (8.1, 8.2) -----------------------


def test_empty_bands_render_nothing() -> None:
    # Without computed zone times the caller passes nothing and the strip does
    # not exist -- the "no output" observable.
    assert render_zone_strip([]) == ""


def test_all_absent_total_zero_renders_nothing() -> None:
    # Every band at 0 s is no time-in-zone data at all: no fabricated strip.
    bands = tuple(ZoneBand(f"Z{i + 1}", 0.0, Z_COLORS[i]) for i in range(5))
    assert render_zone_strip(bands) == ""


# --- proportional stacked bands (8.1) ---------------------------------------


def test_five_zone_segment_widths_are_proportional_to_seconds() -> None:
    svg = render_zone_strip(five_bands())
    widths = _bar_widths(svg)
    # one colored segment per (non-zero) band
    assert len(widths) == 5
    # Z3 has 3x the seconds of Z1 (3600 vs 1200) -> ~3x the width
    assert widths[2] == pytest.approx(3.0 * widths[0])
    # every segment is proportional to its share of the total
    total_secs = sum(FIVE_SECONDS)
    total_w = sum(widths)
    for width, secs in zip(widths, FIVE_SECONDS, strict=True):
        assert width == pytest.approx(secs / total_secs * total_w)
    # the segments tile the full 800 px strip with no gaps
    assert total_w == pytest.approx(800.0)


def test_five_zone_labels_durations_percents_and_colors_present() -> None:
    svg = render_zone_strip(five_bands())
    # label + h:mm duration + percent for every band, exactly as one caption
    assert "Z1 0:20 10%" in svg
    assert "Z2 0:40 20%" in svg
    assert "Z3 1:00 30%" in svg  # 3600 s -> exactly one hour
    assert "Z4 0:50 25%" in svg
    assert "Z5 0:30 15%" in svg
    # the percentages sum to ~100
    assert sum(_percent_ints(svg)) == pytest.approx(100, abs=1)
    # every caller-supplied color appears
    for color in Z_COLORS:
        assert color in svg


def test_hmm_matches_documented_example() -> None:
    # 3660 s -> "1:01": the documented h:mm convention, pinned via a single band.
    svg = render_zone_strip([ZoneBand("Z1", 3660.0, Z_COLORS[0])])
    assert "Z1 1:01 100%" in svg


# --- zero-time bands keep the label without width (8.1) ----------------------


def test_zero_time_band_keeps_label_at_zero_without_consuming_width() -> None:
    svg = render_zone_strip(zero_bands())
    # the empty zone is still listed, at 0:00 / 0%
    assert "Z5 0:00 0%" in svg
    widths = _bar_widths(svg)
    # only the four non-zero bands get a colored segment; Z5 has no width
    assert len(widths) == 4
    # Z5 consumed no proportional space: the four still tile the full width
    assert sum(widths) == pytest.approx(800.0)
    # the other bands keep their own proportional widths (Z4 is now 40%)
    total_secs = sum(ZERO_SECONDS)
    for width, secs in zip(widths, ZERO_SECONDS[:4], strict=True):
        assert width == pytest.approx(secs / total_secs * 800.0)


# --- determinism + golden ---------------------------------------------------


def test_render_is_byte_identical_across_calls() -> None:
    assert render_zone_strip(five_bands()) == render_zone_strip(five_bands())


def test_matches_committed_golden() -> None:
    golden = GOLDEN_DIR / "zone_strip_five.svg"
    assert golden.exists(), f"missing golden: {golden}"
    assert render_zone_strip(five_bands()) == golden.read_text(), (
        "golden mismatch for zone_strip_five"
    )
