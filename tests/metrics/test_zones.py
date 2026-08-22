"""Hand-computed tests for generic time-in-band occupancy.

These exercise :func:`fitdocs.metrics.zones.time_in_zone`: the pure band-math
that attributes inter-sample duration to bands given caller-supplied dividers.
Every expected tuple below is hand-computed by attributing each ``dt`` to the
*earlier* sample's band, so the attribution rule and boundary semantics are
pinned exactly -- not merely snapshotted.

The invariants under test:

* **Earlier-sample attribution** -- for consecutive samples ``i`` and ``i+1``
  the gap ``dt = time_s[i+1] - time_s[i]`` is credited to ``values[i]``'s band,
  even when the value crosses a divider between the two samples (Req 10.2).
* **``None`` exclusion** -- a ``None`` earlier value credits its ``dt`` to *no*
  band, so the occupied total falls short of the elapsed span by exactly that
  ``dt``; a ``None`` at the final index has no outgoing ``dt`` and is inert
  (Req 10.3).
* **Boundary via ``bisect_right``** -- a value exactly equal to a divider lands
  in the *upper* band, matching the band semantics documented on
  :class:`~fitdocs.metrics.types.ZoneSpec`.
* **Arbitrary band count, no embedded defaults** -- the result length is always
  ``len(spec.dividers) + 1`` for any divider count; there are no built-in
  5-/7-zone assumptions (Req 10.4).
* **Totality** -- for valid inputs the function never returns ``None`` and never
  raises: fewer than two samples yield an all-zero tuple of the right length; a
  value below all dividers lands in band 0, above all in the last band.
"""

from __future__ import annotations

from fitdocs import metrics
from fitdocs.metrics import zones
from fitdocs.metrics.types import ZoneSpec

# --- module wiring ----------------------------------------------------------


def test_module_imports_from_metrics_package() -> None:
    # zones lives under the metrics package (design File Structure Plan).
    assert zones is metrics.zones


# --- 1. earlier-sample attribution, incl. a divider crossing (Req 10.2) -----


def test_earlier_sample_attribution_across_divider_crossing() -> None:
    # dividers (100, 150) -> 3 bands: [<100), [100..150), [>=150).
    #   values : 90 -> band0, 120 -> band1, 160 -> band2, 130 -> (last, no dt)
    #   time_s : 0, 10, 25, 45  -> dt 10, 15, 20
    # Each dt is credited to the EARLIER sample's band:
    #   dt(10) @ band0, dt(15) @ band1, dt(20) @ band2.
    # The value CROSSES a divider on every step (90->120 crosses 100,
    # 120->160 crosses 150), so a later-sample rule would give a DIFFERENT
    # tuple -- this pins earlier-sample attribution specifically.
    spec = ZoneSpec((100.0, 150.0))
    values: tuple[float | None, ...] = (90.0, 120.0, 160.0, 130.0)
    time_s = (0.0, 10.0, 25.0, 45.0)
    assert zones.time_in_zone(values, time_s, spec) == (10.0, 15.0, 20.0)


# --- 2. None exclusion (Req 10.3) -------------------------------------------


def test_none_earlier_value_contributes_to_no_band() -> None:
    # dividers (150,) -> 2 bands: [<150), [>=150).
    #   values : 120 -> band0, None -> (no band), 130 -> band0, 200 -> (last)
    #   time_s : 0, 10, 30, 60  -> dt 10, 20, 30
    #   dt(10) @ band0; dt(20) EXCLUDED (earlier value is None); dt(30) @ band0.
    # Occupied total 40 s is short of the 60 s elapsed by exactly the 20 s
    # None gap.
    spec = ZoneSpec((150.0,))
    values: tuple[float | None, ...] = (120.0, None, 130.0, 200.0)
    time_s = (0.0, 10.0, 30.0, 60.0)
    result = zones.time_in_zone(values, time_s, spec)
    assert result == (40.0, 0.0)
    elapsed = time_s[-1] - time_s[0]
    assert elapsed - sum(result) == 20.0  # exactly the excluded None gap


def test_none_at_last_index_has_no_effect() -> None:
    # A None at the FINAL index has no outgoing dt, so it changes nothing.
    #   values : 120 -> band0, 130 -> band0, None -> (last, inert)
    #   time_s : 0, 10, 30 -> dt 10, 20  (both @ band0)
    spec = ZoneSpec((150.0,))
    values: tuple[float | None, ...] = (120.0, 130.0, None)
    time_s = (0.0, 10.0, 30.0)
    result = zones.time_in_zone(values, time_s, spec)
    assert result == (30.0, 0.0)
    assert sum(result) == time_s[-1] - time_s[0]  # nothing excluded


# --- 3. boundary via bisect_right: value == divider -> UPPER band -----------


def test_value_equal_to_divider_falls_in_upper_band() -> None:
    # dividers (100, 200) -> 3 bands. Four samples at 1 Hz (dt 1 each; the last
    # has no outgoing dt):
    #   99.999 -> band0 (bisect_right == 0)
    #   100.0  -> band1 (bisect_right == 1: value == divider goes UP)
    #   200.0  -> band2 (bisect_right == 2: value == divider goes UP)
    #   250.0  -> (last, no dt)
    # A bisect_LEFT boundary would instead give (2.0, 0.0, 1.0), so this
    # discriminates the exact-equality rule.
    spec = ZoneSpec((100.0, 200.0))
    values: tuple[float | None, ...] = (99.999, 100.0, 200.0, 250.0)
    time_s = (0.0, 1.0, 2.0, 3.0)
    assert zones.time_in_zone(values, time_s, spec) == (1.0, 1.0, 1.0)


# --- 4. arbitrary band count, no embedded defaults (Req 10.4) ---------------


def test_arbitrary_band_count_two_bands() -> None:
    # 1 divider -> 2 bands; result length is exactly 2 (no fixed zone count).
    spec = ZoneSpec((150.0,))
    values: tuple[float | None, ...] = (100.0, 200.0)
    time_s = (0.0, 10.0)
    result = zones.time_in_zone(values, time_s, spec)
    assert result == (10.0, 0.0)
    assert len(result) == 2


def test_arbitrary_band_count_seven_bands() -> None:
    # 6 dividers -> 7 bands; result length is exactly 7. Values step through
    # every band; a trailing duplicate gives the top band an outgoing dt so all
    # seven receive exactly 1 s.
    spec = ZoneSpec((10.0, 20.0, 30.0, 40.0, 50.0, 60.0))
    values: tuple[float | None, ...] = (5.0, 15.0, 25.0, 35.0, 45.0, 55.0, 65.0, 65.0)
    time_s = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0)
    result = zones.time_in_zone(values, time_s, spec)
    assert result == (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    assert len(result) == 7


# --- 5. degenerate inputs ---------------------------------------------------


def test_zero_samples_all_zero_tuple() -> None:
    # No samples -> no dt to attribute -> all-zero tuple of the right length.
    spec = ZoneSpec((100.0, 150.0))
    result = zones.time_in_zone((), (), spec)
    assert result == (0.0, 0.0, 0.0)
    assert len(result) == 3


def test_single_sample_all_zero_tuple() -> None:
    # One sample has no outgoing dt -> all-zero tuple.
    spec = ZoneSpec((100.0, 150.0))
    values: tuple[float | None, ...] = (120.0,)
    assert zones.time_in_zone(values, (5.0,), spec) == (0.0, 0.0, 0.0)


def test_series_entirely_in_one_band() -> None:
    # Every sample sits in band1 -> all elapsed seconds land in band1.
    spec = ZoneSpec((100.0, 150.0))
    values: tuple[float | None, ...] = (120.0, 130.0, 140.0)
    time_s = (0.0, 10.0, 20.0)
    result = zones.time_in_zone(values, time_s, spec)
    assert result == (0.0, 20.0, 0.0)
    assert sum(result) == time_s[-1] - time_s[0]


# --- 6. totality: never None, never raises (Req 10.4) -----------------------


def test_value_below_all_dividers_lands_in_first_band() -> None:
    spec = ZoneSpec((100.0, 200.0))
    values: tuple[float | None, ...] = (50.0, 999.0)
    result = zones.time_in_zone(values, (0.0, 10.0), spec)
    assert result == (10.0, 0.0, 0.0)


def test_value_above_all_dividers_lands_in_last_band() -> None:
    spec = ZoneSpec((100.0, 200.0))
    values: tuple[float | None, ...] = (999.0, 50.0)
    result = zones.time_in_zone(values, (0.0, 10.0), spec)
    assert result == (0.0, 0.0, 10.0)


def test_result_is_a_tuple_never_none() -> None:
    # For any valid input the function is total: a real tuple, never None.
    spec = ZoneSpec((100.0,))
    result = zones.time_in_zone((120.0, 90.0), (0.0, 5.0), spec)
    assert isinstance(result, tuple)
    assert result is not None
    assert result == (0.0, 5.0)


def test_all_none_values_yield_all_zero_tuple() -> None:
    # Every earlier value is None -> nothing is attributed, no raise.
    spec = ZoneSpec((100.0, 150.0))
    values: tuple[float | None, ...] = (None, None, None)
    assert zones.time_in_zone(values, (0.0, 10.0, 20.0), spec) == (0.0, 0.0, 0.0)


def test_mismatched_lengths_use_aligned_prefix() -> None:
    # Defensive: the facade passes aligned channels, but if lengths differ the
    # function iterates only the aligned prefix (min length) and never raises.
    #   values has 3 entries, time_s has 2 -> only pair (i=0) is attributed.
    spec = ZoneSpec((100.0, 150.0))
    values: tuple[float | None, ...] = (120.0, 130.0, 140.0)
    time_s = (0.0, 10.0)
    assert zones.time_in_zone(values, time_s, spec) == (0.0, 10.0, 0.0)
