"""Shared document sections and the hero telemetry selection (task 3.3).

These pin :mod:`fitdocs.render.sections` against the approved SharedSections
interface (design §SharedSections, §HeroChart series selection, §ZoneStrip
inclusion) and the missing-data-honesty rules (Req 6.2, 6.6, 6.7, 7.2, 7.3,
7.6, 8.1, 8.2, 8.4, 11.1, 11.2, 11.4, 13.2). Contexts are built over real
parsed activities via the fit-ingest public API with a fixed timezone, so the
observable behaviour is proven against the real activity model rather than
hand-built stand-ins.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta, timezone, tzinfo

from fitdocs import (
    AthleteInputs,
    DerivedMetrics,
    ZoneSpec,
    compute_metrics,
    parse_fit,
)
from fitdocs.contract import LOAD_NOT_COMPUTED
from fitdocs.docmerge import (
    begin_marker,
    end_marker,
    extract_regions,
)
from fitdocs.layout import asset_rel_path
from fitdocs.render import Asset, DocContext
from fitdocs.render.sections import (
    devices_section,
    hero_chart,
    hero_chart_spec,
    hero_stats,
    load_section,
    notes_region,
    telemetry_chips,
    zone_strip,
)

TZ: tzinfo = timezone(timedelta(hours=-6))

_STEM = "2021-09-07-run-1946"

# Athlete inputs that enable HR zones (4 dividers -> 5 bands) and TRIMP.
_ATHLETE = AthleteInputs(
    ftp_watts=250.0,
    resting_hr_bpm=45,
    max_hr_bpm=190,
    hr_zones=ZoneSpec([120.0, 140.0, 160.0, 175.0]),
)


def _ctx(
    fit_bytes: bytes,
    *,
    athlete: AthleteInputs | None = None,
    doc_stem: str = _STEM,
    activity_replace: dict[str, object] | None = None,
    metrics: DerivedMetrics | None = None,
) -> DocContext:
    activity = parse_fit(fit_bytes)
    if activity_replace:
        activity = dataclasses.replace(activity, **activity_replace)
    return DocContext(
        activity=activity,
        metrics=metrics if metrics is not None else compute_metrics(activity, athlete),
        athlete=athlete,
        doc_stem=doc_stem,
        source_refs=("fit-archive/aaaa.fit",),
        tz=TZ,
    )


# --- hero_stats -------------------------------------------------------------


def test_hero_stats_rich_run_reference_order(run_fit_bytes: bytes) -> None:
    """A rich run renders the reference key-stats in order with sub-values."""
    out = hero_stats(_ctx(run_fit_bytes))
    # Reference order: Distance, Moving, Pace (run), Climb, Avg HR.
    order = ["Distance", "Moving time", "Pace", "Climb", "Avg HR"]
    positions = [out.index(name) for name in order]
    assert positions == sorted(positions)
    assert "| Distance | 0.03 km |" in out
    assert "0:09 (elapsed 0:09)" in out  # moving with elapsed sub-value
    assert "5:03 /km" in out  # pace, with best sub
    assert "9 m (1600→1609 m)" in out  # climb with min->max altitude sub
    assert "133 bpm (max 147 bpm)" in out  # avg HR with max sub


def test_hero_stats_omits_absent_row_no_fabricated_zero(
    run_no_gps_fit_bytes: bytes,
) -> None:
    """A run with no altitude omits Climb entirely -- never a fabricated 0 m."""
    out = hero_stats(_ctx(run_no_gps_fit_bytes))
    assert "Climb" not in out
    assert "0 m" not in out  # no fabricated zero climb
    assert "| Distance |" in out  # independent rows still render
    assert "Pace" in out


def test_hero_stats_ride_power_with_np_if_tss_subs(ride_fit_bytes: bytes) -> None:
    """A ride shows Speed and Power; Power carries NP/IF/TSS subs when available."""
    base = compute_metrics(parse_fit(ride_fit_bytes))
    enriched = dataclasses.replace(
        base, normalized_power_w=210.0, intensity_factor=0.84, power_tss=12.0
    )
    out = hero_stats(_ctx(ride_fit_bytes, metrics=enriched))
    assert "| Speed |" in out  # rides show speed, not pace
    assert "Pace" not in out
    assert "28.8 km/h (max 28.8 km/h)" in out
    assert "200 w (NP 210 w · IF 0.84 · TSS 12)" in out


def test_hero_stats_ride_power_without_subs_when_unavailable(
    ride_fit_bytes: bytes,
) -> None:
    """When NP/IF/TSS are absent, Power shows the average alone (no subs)."""
    out = hero_stats(_ctx(ride_fit_bytes))
    assert "| Power | 200 w |" in out
    assert "NP" not in out
    assert "IF" not in out
    assert "TSS" not in out


def test_hero_stats_supplementals_recognized_unknown_ignored(
    session_dev_fields_fit_bytes: bytes,
) -> None:
    """Recognized session dev fields render; unknown ones are ignored silently.

    The fixture records HealthFit's real encoding -- UINT16 hundredths with no
    declared ``scale`` -- so these assertions fail if the raw ingest value ever
    reaches the page unscaled (it would read ``5500%`` / ``950``).
    """
    out = hero_stats(_ctx(session_dev_fields_fit_bytes))
    assert "| Humidity | 55% |" in out
    assert "| Avg METs | 9.5 |" in out
    # Unknown / unrecognized developer fields never leak into the summary.
    assert "SESSION UUID" not in out
    assert "SESSION INDOOR" not in out
    # WORKOUT RPE ESTIMATED is recorded but NOT recognized: it is a 0/1 flag, not
    # an RPE, so no row may claim it as one.
    assert "RPE" not in out


def test_declared_scale_developer_field_is_not_double_scaled(
    session_dev_fields_declared_scale_fit_bytes: bytes,
) -> None:
    """A writer-DECLARED scale must not be re-applied by the render fallback.

    ``AVG METs`` here declares ``scale=100`` on the SAME raw wire byte (950)
    ``session_dev_fields_fit_bytes`` uses undeclared -- so fit-ingest decodes
    it to the correct ``9.5`` itself (Req 14.2, as amended). Before Fix 1 this
    reached the page as ``0.1`` (950 -> ingest's 9.5 -> render's fallback
    ``* 0.01`` -> ``0.095`` -> formatted ``0.1``): a CORRECT decoded value
    turned 100x wrong by a hardcoded fallback that could not tell it had
    already been scaled. ``SESSION WEATHER HUMIDITY`` stays undeclared in the
    SAME file, so this also proves the fallback still applies where it must.
    """
    out = hero_stats(_ctx(session_dev_fields_declared_scale_fit_bytes))
    assert "| Avg METs | 9.5 |" in out
    assert "| Avg METs | 0.1 |" not in out  # the exact 100x-wrong regression
    assert "| Humidity | 55% |" in out  # undeclared sibling still fallback-scaled


# --- telemetry_chips --------------------------------------------------------


def test_chips_per_available_metric_run(run_fit_bytes: bytes) -> None:
    """A run shows HR/cadence/speed chips; no power, no threshold metrics."""
    chips = telemetry_chips(_ctx(run_fit_bytes))
    assert "**HR** 133 bpm" in chips
    assert "**Cadence** 85 rpm" in chips
    assert "**Speed** 11.9 km/h" in chips
    assert "Power" not in chips
    assert "TRIMP" not in chips
    assert "TSS" not in chips


def test_chips_power_present_for_ride(ride_fit_bytes: bytes) -> None:
    """A ride's power average appears as a chip."""
    chips = telemetry_chips(_ctx(ride_fit_bytes))
    assert "**Power** 200 w" in chips


def test_chips_trimp_tss_only_when_metrics_have_them(ride_fit_bytes: bytes) -> None:
    """TRIMP/TSS chips appear only when athlete-enabled metrics are present (8.4)."""
    base = compute_metrics(parse_fit(ride_fit_bytes))
    assert "TRIMP" not in telemetry_chips(_ctx(ride_fit_bytes, metrics=base))
    assert "TSS" not in telemetry_chips(_ctx(ride_fit_bytes, metrics=base))

    with_trimp = dataclasses.replace(base, trimp=42.0)
    assert "**TRIMP** 42" in telemetry_chips(_ctx(ride_fit_bytes, metrics=with_trimp))

    with_tss = dataclasses.replace(base, power_tss=55.0)
    assert "**TSS** 55" in telemetry_chips(_ctx(ride_fit_bytes, metrics=with_tss))


# --- hero_chart series selection + x-axis -----------------------------------


def _labels(spec: object) -> list[str]:
    assert spec is not None
    return [s.label for s in spec.series]  # type: ignore[attr-defined]


def test_hero_series_powerless_ride_hr_and_speed(
    ride_no_power_fit_bytes: bytes,
) -> None:
    """A powerless ride falls back to HR + Speed (never power)."""
    spec = hero_chart_spec(_ctx(ride_no_power_fit_bytes))
    assert _labels(spec) == ["HR", "Speed"]
    assert "Power" not in _labels(spec)


def test_hero_series_run_with_power_hr_and_power(
    run_native_power_sparse_hr_fit_bytes: bytes,
) -> None:
    """A run with native power plots HR + Power by default."""
    spec = hero_chart_spec(_ctx(run_native_power_sparse_hr_fit_bytes))
    assert _labels(spec) == ["HR", "Power"]


def test_hero_series_powerless_run_hr_and_pace(run_no_gps_fit_bytes: bytes) -> None:
    """A powerless run falls back to HR + Pace."""
    spec = hero_chart_spec(_ctx(run_no_gps_fit_bytes))
    assert _labels(spec) == ["HR", "Pace"]


def test_hero_series_strength_single_hr_series(
    strength_no_sets_fit_bytes: bytes,
) -> None:
    """An HR-only strength session yields exactly one series."""
    spec = hero_chart_spec(_ctx(strength_no_sets_fit_bytes))
    assert _labels(spec) == ["HR"]
    assert spec is not None
    assert len(spec.series) == 1


def test_hero_chart_none_without_plottable_series(run_fit_bytes: bytes) -> None:
    """With every telemetry channel blank, the hero chart is omitted (7.6)."""
    activity = parse_fit(run_fit_bytes)
    n = len(activity.samples.time_s)
    blank = dataclasses.replace(
        activity.samples,
        heart_rate_bpm=(None,) * n,
        power_w=(None,) * n,
        cadence_rpm=(None,) * n,
        speed_mps=(None,) * n,
        distance_m=(None,) * n,
        altitude_m=(None,) * n,
    )
    ctx = _ctx(run_fit_bytes, activity_replace={"samples": blank})
    assert hero_chart_spec(ctx) is None
    assert hero_chart(ctx) is None


def test_hero_x_axis_distance_when_present(run_fit_bytes: bytes) -> None:
    """Cumulative distance is the x-axis when the distance channel has data."""
    spec = hero_chart_spec(_ctx(run_fit_bytes))
    assert spec is not None
    assert spec.x_unit == "km"


def test_hero_x_axis_time_when_no_distance(strength_no_sets_fit_bytes: bytes) -> None:
    """With no distance channel the x-axis falls back to elapsed minutes (7.3)."""
    spec = hero_chart_spec(_ctx(strength_no_sets_fit_bytes))
    assert spec is not None
    assert spec.x_unit == "min"
    # x is elapsed seconds / 60: second sample at t=1s -> 1/60 min.
    assert spec.x[1] == 1.0 / 60.0


def test_hero_chart_returns_link_and_asset(run_fit_bytes: bytes) -> None:
    """hero_chart returns a relative image link plus its SVG asset."""
    result = hero_chart(_ctx(run_fit_bytes))
    assert result is not None
    link, asset = result
    rel = asset_rel_path(_STEM, "hero")
    assert isinstance(asset, Asset)
    assert asset.rel_path == rel
    assert asset.content.startswith("<svg")
    assert link.startswith("![")
    assert f"({rel})" in link


# --- zone_strip -------------------------------------------------------------


def test_zone_strip_present_with_computed_zone_times(
    run_native_power_sparse_hr_fit_bytes: bytes,
) -> None:
    """With athlete zones, computed time-in-zone renders a strip asset (8.1)."""
    ctx = _ctx(run_native_power_sparse_hr_fit_bytes, athlete=_ATHLETE)
    assert ctx.metrics.hr_time_in_zone_s is not None
    result = zone_strip(ctx)
    assert result is not None
    link, asset = result
    assert asset.rel_path == asset_rel_path(_STEM, "zones")
    assert asset.content.startswith("<svg")
    assert f"({asset.rel_path})" in link


def test_zone_strip_none_without_zone_times_no_defaults(
    run_native_power_sparse_hr_fit_bytes: bytes,
) -> None:
    """No athlete zones -> no strip and no fabricated default boundaries (8.2)."""
    ctx = _ctx(run_native_power_sparse_hr_fit_bytes)  # no athlete
    assert ctx.metrics.hr_time_in_zone_s is None
    assert zone_strip(ctx) is None


# --- devices_section --------------------------------------------------------


def test_devices_display_name_prefers_product_name(run_fit_bytes: bytes) -> None:
    """The device display name is the product name; the placeholder manufacturer
    ``development`` is not shown as an informative value (6.6)."""
    activity = parse_fit(run_fit_bytes)
    dev = dataclasses.replace(
        activity.devices[0],
        manufacturer="development",
        product_name="Watch7,5",
        battery_status="low",
    )
    out = devices_section(_ctx(run_fit_bytes, activity_replace={"devices": (dev,)}))
    assert "Watch7,5" in out  # product name is the display name
    assert "development" not in out  # placeholder manufacturer suppressed
    assert "**low**" in out  # low battery flagged


def test_devices_channel_coverage_rows_only_for_present_channels(
    ride_no_power_fit_bytes: bytes,
) -> None:
    """A channel with no data has no coverage row; present ones do (13.2)."""
    out = devices_section(_ctx(ride_no_power_fit_bytes))
    assert "| Heart rate | 100% |" in out
    assert "| Power |" not in out  # power channel absent -> no coverage row
    assert "| Altitude |" not in out


def test_devices_channel_coverage_reports_sparse_percent(
    run_native_power_sparse_hr_fit_bytes: bytes,
) -> None:
    """Sparse HR coverage is reported honestly (6 of 10 -> 60%)."""
    out = devices_section(_ctx(run_native_power_sparse_hr_fit_bytes))
    assert "| Heart rate | 60% |" in out


def test_devices_decode_errors_none_indicator(run_fit_bytes: bytes) -> None:
    """A clean decode surfaces an explicit 'none' indicator."""
    out = devices_section(_ctx(run_fit_bytes))
    assert "none" in out.lower()


def test_devices_decode_errors_bulleted(run_fit_bytes: bytes) -> None:
    """Reported decode errors surface as a bulleted list."""
    activity = parse_fit(run_fit_bytes)
    prov = dataclasses.replace(
        activity.provenance, decode_errors=("bad frame at offset 42",)
    )
    out = devices_section(_ctx(run_fit_bytes, activity_replace={"provenance": prov}))
    assert "- bad frame at offset 42" in out


# --- load_section / notes_region --------------------------------------------


def test_load_section_is_exact_placeholder_no_numbers() -> None:
    """The load region contains exactly LOAD_NOT_COMPUTED and no digits (11.1-11.4)."""
    out = load_section()
    assert begin_marker("load") in out
    assert end_marker("load") in out
    regions = extract_regions(out)
    assert regions == {"load": LOAD_NOT_COMPUTED}
    assert not any(ch.isdigit() for ch in regions["load"])


def test_notes_region_wraps_placeholder() -> None:
    """notes_region wraps the placeholder verbatim in the notes markers (10.5)."""
    placeholder = "Add your own notes about this workout here."
    out = notes_region(placeholder)
    assert begin_marker("notes") in out
    assert end_marker("notes") in out
    assert extract_regions(out) == {"notes": placeholder}


# --- determinism ------------------------------------------------------------


def test_sections_are_deterministic(ride_fit_bytes: bytes) -> None:
    """Identical context yields byte-identical section output (4.1)."""
    ctx = _ctx(ride_fit_bytes)
    assert hero_stats(ctx) == hero_stats(ctx)
    assert telemetry_chips(ctx) == telemetry_chips(ctx)
    assert devices_section(ctx) == devices_section(ctx)
    first = hero_chart(ctx)
    second = hero_chart(ctx)
    assert first is not None and second is not None
    assert first[0] == second[0]
    assert first[1] == second[1]
