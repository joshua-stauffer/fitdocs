"""Hand-computed tests for the chart-series preparation math.

These exercise :mod:`fitdocs.render.charts.series`: the reference section 3
math that turns a plain telemetry series into something plottable --
null-skipping boxcar smoothing, per-series band normalization (with the
flat-series midpoint pin), and gap segmentation. Every expected value below is
hand-computed so the arithmetic is pinned, not merely snapshotted.

The invariants under test:

* **Missing stays missing** -- a ``None`` center is never fabricated into a
  value, and ``None`` neighbours are skipped (not treated as ``0``) inside a
  smoothing window (Req 7.5).
* **Null-skipping mean** -- smoothing averages only the non-``None`` samples in
  the ``[i-k, i+k]`` window, clamped at the array ends, and ``k`` controls the
  window width.
* **Band normalization** -- min/max of the non-``None`` values map into the
  target band ``[lo, hi]``; a flat series pins every value to the band midpoint
  ``(lo + hi) / 2`` (Req 7.4).
* **Gaps render as gaps** -- a run of ``None`` breaks a polyline into separate
  segments; missing samples are never interpolated across (Req 7.5).
* **Paired gaps break on either channel** -- for two nullable channels a point
  exists only where *both* are present; a ``None`` in either channel breaks the
  current segment, and a real ``0.0`` is an ordinary value (Req 2.4).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from fitdocs.render.charts.series import (
    boxcar_smooth,
    gap_segments,
    normalize_band,
    paired_gap_segments,
)

# --- helpers ----------------------------------------------------------------


def _assert_series_equal(
    actual: Sequence[float | None],
    expected: Sequence[float | None],
) -> None:
    """Compare two ``float | None`` series element-by-element: ``None`` matches
    only ``None``; numbers match under :func:`pytest.approx`."""
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected, strict=True):
        if want is None:
            assert got is None
        else:
            assert got is not None
            assert got == pytest.approx(want)


# --- boxcar_smooth ----------------------------------------------------------


def test_boxcar_ramp_truncated_edges() -> None:
    """A clean ramp with ``k=1`` (3-sample window): the edges see a truncated
    window (2 samples), the interior sees the full 3."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    # i=0 -> mean(1,2)=1.5; i=1 -> mean(1,2,3)=2.0; i=2 -> mean(2,3,4)=3.0;
    # i=3 -> mean(3,4,5)=4.0; i=4 -> mean(4,5)=4.5
    _assert_series_equal(
        boxcar_smooth(values, k=1),
        (1.5, 2.0, 3.0, 4.0, 4.5),
    )


def test_boxcar_default_k5_window() -> None:
    """Default ``k=5`` is an 11-sample symmetric window. Over the ramp
    ``1..11`` the center sees all 11 samples; the ends see 6 each."""
    values = [float(v) for v in range(1, 12)]  # 1.0 .. 11.0, length 11
    smoothed = boxcar_smooth(values)  # default k=5
    # i=0  -> mean(1..6)  = 21/6 = 3.5
    # i=5  -> mean(1..11) = 66/11 = 6.0
    # i=10 -> mean(6..11) = 51/6 = 8.5
    assert smoothed[0] == pytest.approx(3.5)
    assert smoothed[5] == pytest.approx(6.0)
    assert smoothed[10] == pytest.approx(8.5)


def test_boxcar_skips_none_holes() -> None:
    """A ``None`` center stays ``None``; ``None`` neighbours are skipped in the
    window mean rather than counted as ``0`` (Req 7.5)."""
    values = [1.0, None, 3.0, 4.0, None, 6.0]
    # i=0 -> window[0,1] non-None {1}      -> 1.0
    # i=1 -> None center                   -> None
    # i=2 -> window[1,2,3] non-None {3,4}  -> 3.5
    # i=3 -> window[2,3,4] non-None {3,4}  -> 3.5
    # i=4 -> None center                   -> None
    # i=5 -> window[4,5] non-None {6}      -> 6.0
    _assert_series_equal(
        boxcar_smooth(values, k=1),
        (1.0, None, 3.5, 3.5, None, 6.0),
    )


def test_boxcar_k_controls_window_width() -> None:
    """``k`` widens the window: a lone spike is diluted more as ``k`` grows."""
    values = [0.0] * 5 + [10.0] + [0.0] * 5  # spike of 10 at index 5, length 11
    k1 = boxcar_smooth(values, k=1)
    k2 = boxcar_smooth(values, k=2)
    # k=1 at index 5: window[4..6] = {0,10,0} -> 10/3
    assert k1[5] == pytest.approx(10.0 / 3.0)
    # k=2 at index 5: window[3..7] = {0,0,10,0,0} -> 10/5 = 2.0
    assert k2[5] == pytest.approx(2.0)
    # wider window dilutes the spike further
    assert k2[5] < k1[5]


def test_boxcar_all_none_stays_none() -> None:
    _assert_series_equal(boxcar_smooth([None, None, None]), (None, None, None))


def test_boxcar_empty_returns_empty() -> None:
    assert boxcar_smooth([]) == ()


# --- normalize_band ---------------------------------------------------------

_LO = 0.42
_HI = 0.92
_MID = 0.67  # (0.42 + 0.92) / 2 -- the main band midpoint


def test_normalize_ramp_maps_endpoints_and_proportional_middle() -> None:
    """Endpoints map to ``lo`` and ``hi``; the value at the range midpoint lands
    at the band midpoint."""
    values = [0.0, 5.0, 10.0]  # vmin=0, vmax=10
    # 0 -> 0.42; 5 -> 0.42 + 0.5*0.5 = 0.67; 10 -> 0.92
    _assert_series_equal(
        normalize_band(values, _LO, _HI),
        (_LO, _MID, _HI),
    )


def test_normalize_proportional_interior() -> None:
    """Interior values map in proportion to their position in ``[vmin, vmax]``."""
    values = [10.0, 20.0, 25.0, 30.0]  # vmin=10, vmax=30, span=20
    # onto [0, 1]: (v-10)/20 -> 0.0, 0.5, 0.75, 1.0
    _assert_series_equal(
        normalize_band(values, 0.0, 1.0),
        (0.0, 0.5, 0.75, 1.0),
    )


def test_normalize_preserves_none() -> None:
    values = [0.0, None, 10.0]
    _assert_series_equal(
        normalize_band(values, _LO, _HI),
        (_LO, None, _HI),
    )


def test_normalize_flat_series_pins_to_midpoint() -> None:
    """A flat series (vmax == vmin) pins every value to the band midpoint."""
    _assert_series_equal(
        normalize_band([5.0, 5.0, 5.0], _LO, _HI),
        (_MID, _MID, _MID),
    )


def test_normalize_single_distinct_value_pins_to_midpoint() -> None:
    """A single distinct non-``None`` value (with holes) is also flat: every
    non-``None`` pins to the midpoint; ``None`` stays ``None``."""
    _assert_series_equal(
        normalize_band([5.0, None, 5.0], _LO, _HI),
        (_MID, None, _MID),
    )


def test_normalize_single_element_pins_to_midpoint() -> None:
    _assert_series_equal(normalize_band([7.0], _LO, _HI), (_MID,))


def test_normalize_flat_uses_the_given_band_midpoint() -> None:
    """The pin is the midpoint of the *given* band, not a constant: the backdrop
    band ``[0, 0.32]`` pins flat to 0.16."""
    _assert_series_equal(normalize_band([3.0, 3.0], 0.0, 0.32), (0.16, 0.16))


def test_normalize_all_none_returns_all_none() -> None:
    _assert_series_equal(normalize_band([None, None], _LO, _HI), (None, None))


def test_normalize_empty_returns_empty() -> None:
    assert normalize_band([], _LO, _HI) == ()


# --- gap_segments -----------------------------------------------------------


def test_gap_segments_splits_at_middle_none_run() -> None:
    """A middle run of ``None`` splits the polyline into two segments; the gap is
    never bridged (Req 7.5)."""
    x = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 11.0, None, None, 14.0, 15.0]
    assert gap_segments(x, y) == (
        ((0.0, 10.0), (1.0, 11.0)),
        ((4.0, 14.0), (5.0, 15.0)),
    )


def test_gap_segments_handles_leading_and_trailing_none() -> None:
    x = [0.0, 1.0, 2.0, 3.0]
    y = [None, 11.0, 12.0, None]
    assert gap_segments(x, y) == (((1.0, 11.0), (2.0, 12.0)),)


def test_gap_segments_isolated_points_become_single_point_segments() -> None:
    """Points separated by ``None`` become their own one-point segments -- they
    are never connected across the gap."""
    x = [0.0, 1.0, 2.0]
    y = [10.0, None, 12.0]
    assert gap_segments(x, y) == (((0.0, 10.0),), ((2.0, 12.0),))


def test_gap_segments_no_gaps_is_one_segment() -> None:
    x = [0.0, 1.0, 2.0]
    y = [10.0, 11.0, 12.0]
    assert gap_segments(x, y) == (((0.0, 10.0), (1.0, 11.0), (2.0, 12.0)),)


def test_gap_segments_all_none_is_empty() -> None:
    assert gap_segments([0.0, 1.0], [None, None]) == ()


def test_gap_segments_empty_is_empty() -> None:
    assert gap_segments([], []) == ()


# --- paired_gap_segments ----------------------------------------------------


def test_paired_gap_segments_both_present_is_one_segment() -> None:
    """When both channels are fully present, every index pairs into a single
    contiguous segment of ``(a[i], b[i])`` points."""
    a = [0.0, 1.0, 2.0, 3.0]
    b = [10.0, 11.0, 12.0, 13.0]
    assert paired_gap_segments(a, b) == (
        ((0.0, 10.0), (1.0, 11.0), (2.0, 12.0), (3.0, 13.0)),
    )


def test_paired_gap_segments_none_in_first_channel_breaks() -> None:
    """A ``None`` in the *first* channel drops that index and breaks the
    polyline; the flanking points are never bridged across it."""
    a = [0.0, None, 2.0, 3.0]
    b = [10.0, 11.0, 12.0, 13.0]
    assert paired_gap_segments(a, b) == (
        ((0.0, 10.0),),
        ((2.0, 12.0), (3.0, 13.0)),
    )


def test_paired_gap_segments_none_in_second_channel_breaks() -> None:
    """A ``None`` in the *second* channel breaks the segment identically -- the
    pair is incomplete regardless of which side is absent."""
    a = [0.0, 1.0, 2.0, 3.0]
    b = [10.0, None, 12.0, 13.0]
    assert paired_gap_segments(a, b) == (
        ((0.0, 10.0),),
        ((2.0, 12.0), (3.0, 13.0)),
    )


def test_paired_gap_segments_either_side_absence_breaks() -> None:
    """Absence in either channel at distinct indices breaks the polyline at each
    hole: only indices where both are present form points."""
    #        i=0    i=1    i=2   i=3    i=4    i=5
    a = [0.0, 1.0, None, 3.0, 4.0, 5.0]
    b = [10.0, 11.0, 12.0, None, 14.0, 15.0]
    # complete pairs at i=0,1 (segment) and i=4,5 (segment); i=2 (a None) and
    # i=3 (b None) both break.
    assert paired_gap_segments(a, b) == (
        ((0.0, 10.0), (1.0, 11.0)),
        ((4.0, 14.0), (5.0, 15.0)),
    )


def test_paired_gap_segments_zero_is_a_valid_value() -> None:
    """Presence is tested with ``is not None``, never truthiness: a real ``0.0``
    in either channel is an ordinary value that forms a point."""
    a = [0.0, 0.0, 1.0]
    b = [0.0, 2.0, 0.0]
    assert paired_gap_segments(a, b) == (((0.0, 0.0), (0.0, 2.0), (1.0, 0.0)),)


def test_paired_gap_segments_all_none_is_empty() -> None:
    """No index has both present, so there is no complete pair -> empty."""
    assert paired_gap_segments([None, None], [None, None]) == ()


def test_paired_gap_segments_no_complete_pair_is_empty() -> None:
    """Channels whose non-``None`` values never coincide at any index yield no
    complete pair, hence the empty tuple."""
    assert paired_gap_segments([1.0, None], [None, 2.0]) == ()


def test_paired_gap_segments_empty_is_empty() -> None:
    assert paired_gap_segments([], []) == ()
