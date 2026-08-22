"""Device-lap table and 1 km re-slice math and rendering (task 3.4).

These pin :mod:`fitdocs.render.splits` against the approved SplitsRenderer
interface (design §SplitsRenderer; research "Split re-slicing is presentation-
level derivation") and the missing-data-honesty rules (Req 6.3, 6.4, 6.5, 13).

The 1 km re-slice math is proven against a **synthetic** sample stream built
directly over the model dataclasses: a crafted cumulative-distance + time stream
spanning three kilometres (two full, one partial) with deliberate ``None`` holes
in the heart-rate and power channels, so every slice aggregate is hand-computed
here and asserted exactly -- including that holes are skipped, never filled.

Device-lap rows are proven against the real parsed run fixture (``parse_fit``):
one :class:`~fitdocs.render.splits.Split` per recorded lap carrying the lap's
recorded summary fields verbatim.
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs import parse_fit
from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)
from fitdocs.render.splits import Split, km_splits, lap_splits, splits_section

# --- synthetic-stream construction ------------------------------------------

_SUMMARY = SessionSummary(
    sport=None,
    sub_sport=None,
    start_time=None,
    total_elapsed_time_s=None,
    total_timer_time_s=None,
    total_distance_m=None,
    total_calories_kcal=None,
    total_ascent_m=None,
    total_descent_m=None,
    avg_heart_rate_bpm=None,
    max_heart_rate_bpm=None,
    avg_power_w=None,
    max_power_w=None,
    avg_cadence_rpm=None,
    max_cadence_rpm=None,
    avg_speed_mps=None,
    max_speed_mps=None,
)

_N = 11
# Cumulative distance in 250 m steps -> 0..2500 m over 11 samples; time in 30 s
# steps. Buckets (max(1, ceil((d)/1000))): samples at 0..1000 -> km 1, at
# 1250..2000 -> km 2, at 2250..2500 -> partial km 3 (500 m covered).
_TIME = tuple(float(i * 30) for i in range(_N))
_DIST = tuple(float(i * 250) for i in range(_N))
# Holes at index 2 and 6; slice 1 = idx0-4, slice 2 = idx5-8, slice 3 = idx9-10.
_HR = (100, 110, None, 120, 130, 140, None, 150, 160, 170, 180)
# Holes at index 1 and 5.
_POWER = (200, None, 210, 220, 230, None, 240, 250, 260, 270, 280)
_CADENCE = (80.0, 80.0, 80.0, 80.0, 80.0, 90.0, 90.0, 90.0, 90.0, 100.0, 100.0)
# Speeds chosen so per-slice means differ: slice1 4.0, slice2 5.0, slice3 2.0.
_SPEED = (4.0, 4.0, 4.0, 4.0, 4.0, 5.0, 5.0, 5.0, 5.0, 2.0, 2.0)


def _samples(
    *,
    time_s: tuple[float, ...] = _TIME,
    distance_m: tuple[float | None, ...] = _DIST,
    heart_rate_bpm: tuple[int | None, ...] = _HR,
    power_w: tuple[int | None, ...] = _POWER,
    cadence_rpm: tuple[float | None, ...] = _CADENCE,
    speed_mps: tuple[float | None, ...] = _SPEED,
) -> Samples:
    n = len(time_s)
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm,
        power_w=power_w,
        cadence_rpm=cadence_rpm,
        speed_mps=speed_mps,
        distance_m=distance_m,
        altitude_m=(None,) * n,
        latitude_deg=(None,) * n,
        longitude_deg=(None,) * n,
        temperature_c=(None,) * n,
    )


def _activity(
    samples: Samples,
    *,
    modality: Modality,
    laps: tuple = (),
) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=Sport.RUN if modality is Modality.RUN else Sport.RIDE,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_SUMMARY,
        laps=laps,
        samples=samples,
        sets=(),
        devices=(),
    )


def _run_synth() -> Activity:
    """Run activity over the synthetic three-km stream (no recorded laps)."""
    return _activity(_samples(), modality=Modality.RUN)


# --- km_splits: hand-computed slice math ------------------------------------


def test_km_splits_hand_computed_three_slices() -> None:
    """Each 1 km slice's distance/time/aggregates match hand computation, and the
    trailing partial km is its own slice (Req 6.3)."""
    splits = km_splits(_run_synth())
    assert len(splits) == 3
    assert all(isinstance(s, Split) for s in splits)

    one, two, three = splits

    # Slice 1: idx 0-4, cumulative 0->1000 m over 0->120 s.
    assert one.label == "1 km"
    assert one.distance_m == 1000.0
    assert one.time_s == 120.0
    # HR non-None over 0-4 = [100,110,120,130] (idx2 skipped) -> mean 115, max 130.
    assert one.avg_hr_bpm == 115.0
    assert one.max_hr_bpm == 130
    # Power non-None over 0-4 = [200,210,220,230] (idx1 skipped) -> mean 215.
    assert one.avg_power_w == 215.0
    assert one.avg_cadence_rpm == 80.0
    assert one.avg_speed_mps == 4.0

    # Slice 2: idx 5-8, cumulative 1000->2000 m over 120->240 s.
    assert two.label == "2 km"
    assert two.distance_m == 1000.0
    assert two.time_s == 120.0
    # HR non-None over 5-8 = [140,150,160] (idx6 skipped) -> mean 150, max 160.
    assert two.avg_hr_bpm == 150.0
    assert two.max_hr_bpm == 160
    # Power non-None over 5-8 = [240,250,260] (idx5 skipped) -> mean 250.
    assert two.avg_power_w == 250.0
    assert two.avg_speed_mps == 5.0

    # Slice 3: idx 9-10, cumulative 2000->2500 m (partial 500 m) over 240->300 s.
    assert three.label == "0.50 km"  # trailing partial labeled by actual distance
    assert three.distance_m == 500.0
    assert three.time_s == 60.0
    assert three.avg_hr_bpm == 175.0
    assert three.max_hr_bpm == 180
    assert three.avg_power_w == 275.0
    assert three.avg_speed_mps == 2.0


def test_km_splits_skips_none_holes_never_fills() -> None:
    """A hole is skipped (divided by the present count), never treated as 0."""
    one = km_splits(_run_synth())[0]
    # If the None HR at idx2 were filled with 0, the mean over five samples would
    # be (100+110+0+120+130)/5 = 92 -- assert it is the honest 115 instead.
    assert one.avg_hr_bpm == 115.0
    # If the None power at idx1 were filled with 0, mean/5 would be 172 -- honest
    # mean over the four present samples is 215.
    assert one.avg_power_w == 215.0


def test_km_splits_totals_reconcile() -> None:
    """Slice distances and times sum to the full covered distance/elapsed span."""
    splits = km_splits(_run_synth())
    assert sum(s.distance_m for s in splits) == 2500.0  # 2500 - 0
    assert sum(s.time_s for s in splits) == 300.0  # 300 - 0


def test_km_splits_empty_without_distance_channel() -> None:
    """No cumulative-distance data -> no km slices (Req 6.5)."""
    blank_distance = _samples(distance_m=(None,) * _N)
    assert km_splits(_activity(blank_distance, modality=Modality.RUN)) == ()


def test_km_splits_all_full_when_exact_multiple() -> None:
    """A stream ending exactly on a km boundary yields only full-km labels."""
    # 0..2000 m in 500 m steps: two full slices, no partial.
    n = 5
    samples = _samples(
        time_s=tuple(float(i * 60) for i in range(n)),
        distance_m=(0.0, 500.0, 1000.0, 1500.0, 2000.0),
        heart_rate_bpm=(None,) * n,
        power_w=(None,) * n,
        cadence_rpm=(None,) * n,
        speed_mps=(None,) * n,
    )
    labels = [s.label for s in km_splits(_activity(samples, modality=Modality.RUN))]
    assert labels == ["1 km", "2 km"]


# --- lap_splits: recorded fields only ---------------------------------------


def test_lap_splits_from_run_fixture(run_fit_bytes: bytes) -> None:
    """One Split per recorded lap, filled straight from lap summary fields (6.3)."""
    activity = parse_fit(run_fit_bytes)
    splits = lap_splits(activity)
    assert [s.label for s in splits] == ["Lap 1", "Lap 2", "Lap 3"]

    first = splits[0]
    assert first.distance_m == pytest.approx(9.9)
    assert first.time_s == 4.0
    assert first.avg_hr_bpm == 124  # recorded, not derived
    assert first.max_hr_bpm == 129
    assert first.avg_power_w is None  # run fixture records no power -> stays None
    assert first.avg_cadence_rpm == 85
    assert first.avg_speed_mps == pytest.approx(3.3)

    # Field values are the recorded lap fields verbatim, per lap.
    assert splits[1].avg_hr_bpm == 135
    assert splits[2].max_hr_bpm == 147


def test_lap_splits_empty_without_laps() -> None:
    """No recorded laps -> empty tuple (Req 6.5)."""
    assert lap_splits(_run_synth()) == ()


# --- splits_section: sport-aware columns ------------------------------------


def test_section_run_has_pace_column_not_speed_power() -> None:
    """A run's tables show a Pace column and no Speed/Avg Power (Req 6.3)."""
    out = splits_section(_run_synth(), Modality.RUN)
    assert "**1 km splits**" in out
    assert "**Device laps**" not in out  # synthetic has no laps
    header = next(ln for ln in out.splitlines() if ln.startswith("| Split "))
    assert "Pace" in header
    assert "Speed" not in header
    assert "Power" not in header


def test_section_ride_has_speed_and_power_columns(ride_fit_bytes: bytes) -> None:
    """A ride's tables show Speed and Avg Power columns and no Pace (Req 6.3)."""
    activity = parse_fit(ride_fit_bytes)  # bike, distance present, no laps
    out = splits_section(activity, Modality.BIKE)
    header = next(ln for ln in out.splitlines() if ln.startswith("| Split "))
    assert "Speed" in header
    assert "Avg Power" in header
    assert "Pace" not in header
    # Ride km aggregates: avg power 200 w, avg speed 8.0 m/s -> 28.8 km/h.
    assert "200 w" in out
    assert "28.8 km/h" in out


# --- splits_section: fastest/slowest + totals -------------------------------


def test_section_marks_fastest_and_slowest(run_fit_bytes: bytes) -> None:
    """The quickest-pace slice is (fastest), the slowest (slowest) (Req 6.4)."""
    out = splits_section(_run_synth(), Modality.RUN)
    # Slice 2 has the highest speed (5.0 -> pace 3:20) => fastest;
    # slice 3 the lowest (2.0 -> pace 8:20) => slowest.
    assert "3:20 /km (fastest)" in out
    assert "8:20 /km (slowest)" in out
    # The middle slice (4:10) carries no marker.
    assert "4:10 /km |" in out
    assert "4:10 /km (" not in out


def test_section_no_marks_when_speeds_uniform(run_fit_bytes: bytes) -> None:
    """Uniform-speed laps get no fastest/slowest markers (Req 6.4)."""
    # Run fixture: three laps all recorded at 3.3 m/s; nulling distance drops the
    # km table so only the uniform lap table remains.
    activity = parse_fit(run_fit_bytes)
    n = len(activity.samples.time_s)
    no_dist = dataclasses.replace(activity.samples, distance_m=(None,) * n)
    activity = dataclasses.replace(activity, samples=no_dist)
    out = splits_section(activity, Modality.RUN)
    assert "**Device laps**" in out
    assert "Lap 1" in out
    assert "(fastest)" not in out
    assert "(slowest)" not in out


def test_section_totals_row_run() -> None:
    """A totals row sums distance/time and shows activity-level pace (Req 6.4)."""
    out = splits_section(_run_synth(), Modality.RUN)
    total_line = next(ln for ln in out.splitlines() if "**Total**" in ln)
    assert "2.50 km" in total_line  # 1000 + 1000 + 500
    assert "5:00" in total_line  # 120 + 120 + 60 s
    assert "2:00 /km" in total_line  # 2500 m / 300 s -> 120 s/km


# --- splits_section: variant omission ---------------------------------------


def test_section_lap_only_when_no_distance(run_fit_bytes: bytes) -> None:
    """Laps present but no distance channel -> lap table only (Req 6.5)."""
    activity = parse_fit(run_fit_bytes)
    n = len(activity.samples.time_s)
    no_dist = dataclasses.replace(activity.samples, distance_m=(None,) * n)
    activity = dataclasses.replace(activity, samples=no_dist)
    out = splits_section(activity, Modality.RUN)
    assert "**Device laps**" in out
    assert "**1 km splits**" not in out


def test_section_km_only_when_no_laps() -> None:
    """Distance present but no laps -> km table only (Req 6.5)."""
    out = splits_section(_run_synth(), Modality.RUN)
    assert "**1 km splits**" in out
    assert "**Device laps**" not in out


def test_section_empty_when_both_absent(run_fit_bytes: bytes) -> None:
    """Neither laps nor distance -> the whole section is omitted (Req 6.5)."""
    activity = parse_fit(run_fit_bytes)
    n = len(activity.samples.time_s)
    no_dist = dataclasses.replace(activity.samples, distance_m=(None,) * n)
    activity = dataclasses.replace(activity, samples=no_dist, laps=())
    assert splits_section(activity, Modality.RUN) == ""


# --- determinism ------------------------------------------------------------


def test_section_is_deterministic() -> None:
    """Identical input yields byte-identical section output (Req 4.1)."""
    activity = _run_synth()
    assert splits_section(activity, Modality.RUN) == splits_section(
        activity, Modality.RUN
    )
