"""Shared document sections and hero telemetry selection (design: SharedSections).

This module renders the sections every per-sport view shares -- the hero
key-stats table, the telemetry chips line, the hero chart and HR-zone strip
images, the devices/data-quality block, and the training-load placeholder --
plus the two content regions (``notes``, ``load``) each document reserves. It
also owns the *series selection* and *x-axis choice* for the hero chart
(design: "Series selection lives in ``sections.py``"): the chart modules draw
plain series, and this module decides which channels become series and what the
axis is.

Two rules govern everything here (Req 13.1-13.3, 8.2):

- **Absent data is omitted, never fabricated.** A ``None`` metric drops its row,
  chip, or coverage line entirely -- never a ``0``. Every guard tests ``is
  None`` so a recorded true zero renders as a genuine value. The hero chart is
  omitted when no plottable series exists (Req 7.6); the HR-zone strip is
  included only when real, athlete-derived time-in-zone exists (Req 8.1, 8.2) --
  this module never invents zone boundaries or default zones.
- **No load math.** :func:`load_section` emits exactly
  :data:`fitdocs.contract.LOAD_NOT_COMPUTED` inside the ``load`` region -- a
  graceful "not computed" state with no numbers, the stable placeholder the
  training-load feature fills later (Req 11.1, 11.2, 11.4).

Both region ids and the not-computed text come from :mod:`fitdocs.contract`, so
the regions this module *emits* are by construction the regions the merge
preserves, the training-load pass fills, and the published ownership contract
names (wiki-contract Req 1.4).

Rendering is pure: section functions return markdown strings and the two chart
functions return an ``(image link, Asset)`` pair (the sync engine writes the
asset; nothing here touches the filesystem, Req 4.1).
"""

from __future__ import annotations

from collections.abc import Sequence

from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs.contract import (
    LOAD_NOT_COMPUTED,
    LOAD_REGION,
    NOTES_REGION,
    region_block,
)
from fitdocs.layout import asset_rel_path
from fitdocs.render import Asset, DocContext
from fitdocs.render.charts.hero import HeroChartSpec, HeroSeries, render_hero_chart
from fitdocs.render.charts.map import compose_map
from fitdocs.render.charts.palette import (
    CADENCE_COLOR,
    HR_COLOR,
    PACE_COLOR,
    POWER_COLOR,
    ROUTE_BIKE_TINT,
    ROUTE_NEUTRAL_TINT,
    ROUTE_RUN_TINT,
    SPEED_COLOR,
    zone_colors,
)
from fitdocs.render.charts.zones import ZoneBand, render_zone_strip
from fitdocs.render.format import (
    ABSENT,
    cell,
    fmt_distance_km,
    fmt_duration,
    fmt_int,
    fmt_pace,
    fmt_speed_kmh,
)

__all__ = [
    "devices_section",
    "hero_chart",
    "hero_chart_spec",
    "hero_stats",
    "load_section",
    "map_section",
    "notes_region",
    "telemetry_chips",
    "zone_strip",
]

# Recognized supplemental session developer fields (Req 6.7) as
# ``(key, label, unit, fallback_scale, decimals)``. Every other developer field
# -- including SESSION UUID / SESSION INDOOR -- is ignored silently; only
# these keys map to a summary row.
#
# FALLBACK_SCALE (why it is not 1.0, and why it is a FALLBACK): this module
# does not decode developer fields itself (fit-ingest Req 14.2 owns that) --
# ingest applies a field's OWN declared ``scale``/``offset`` when its
# ``field_description`` declares one, and reports which keys it did that for
# via ``Activity.developer_fields_declared_scale``. HealthFit, the only writer
# in the current 74-file corpus, declares NO scale on these two fields while
# encoding them as UINT16 HUNDREDTHS, so a generic decoder cannot recover the
# unit and the raw integer is 100x the true value -- promoting a key to a
# labelled summary row is where we commit to knowing what THAT writer means,
# so this fallback factor is applied ONLY when ingest reports no declared
# scale for the key (see ``_supplemental_rows``). Verified across 74 real
# HealthFit files: METs 353-1405 -> 3.5-14.1 (calorie-derived METs track
# raw/100 at a constant 0.83 ratio, ruling out any other power of ten);
# humidity 3900-8600 -> 39-86%. A writer that DOES declare a scale is decoded
# by ingest already, and this fallback must NOT be applied on top of that --
# see ``tests/render/test_sections.py``:
# ``test_declared_scale_developer_field_is_not_double_scaled``.
#
# ``WORKOUT RPE ESTIMATED`` is deliberately ABSENT. It decodes as a UINT8 that
# is only ever 0 or 1 across the corpus, with no correlation to effort (1 spans
# 2.6-13.5 kcal/min; 0 sits inside that range), so it reads as a flag meaning
# "RPE was estimated" -- not an RPE on any scale. Rendering it as ``RPE 1`` would
# assert a physiological value we do not have.
_SUPPLEMENTALS: tuple[tuple[str, str, str, float, int], ...] = (
    ("SESSION WEATHER HUMIDITY", "Humidity", "%", 0.01, 0),
    ("AVG METs", "Avg METs", "", 0.01, 1),
)

# Per-channel data-coverage rows (Req 13.2), in display order. A row is emitted
# only for a channel that has at least one recorded sample.
_COVERAGE_CHANNELS: tuple[tuple[str, str], ...] = (
    ("heart_rate_bpm", "Heart rate"),
    ("power_w", "Power"),
    ("cadence_rpm", "Cadence"),
    ("speed_mps", "Speed"),
    ("distance_m", "Distance"),
    ("altitude_m", "Altitude"),
    ("temperature_c", "Temperature"),
    ("latitude_deg", "GPS"),
)

# Battery statuses that warrant a flag in the devices table (Req 6.6).
_BATTERY_FLAGS: frozenset[str] = frozenset({"low", "critical"})

# The literal manufacturer placeholder real files decode (research.md): it is not
# an informative value, so it is suppressed in the devices table (Req 6.6).
_MANUFACTURER_PLACEHOLDER = "development"


# --- hero key stats ---------------------------------------------------------


def hero_stats(ctx: DocContext) -> str:
    """The hero key-stats markdown table in reference order (Req 6.2, 6.7).

    Rows appear in the reference KeyStats order -- Distance; Moving time
    (elapsed sub-value); Pace for runs / Speed for rides (best/max sub); Climb
    (min->max altitude sub); Avg HR (max sub); and, for rides, Power (NP/IF/TSS
    subs where available). A row whose primary value is ``None`` is omitted
    entirely -- never a fabricated ``0`` (Req 13.1) -- while a recorded true zero
    renders as a genuine value. Recognized supplemental session values (humidity,
    average METs) are appended when recorded, scaled to their true unit; unknown
    developer fields are ignored silently (Req 6.7).
    """
    m = ctx.metrics
    modality = ctx.activity.modality
    rows: list[str] = ["| Stat | Value |", "| --- | --- |"]

    _append(rows, "Distance", fmt_distance_km(m.distance_m), [])

    elapsed = fmt_duration(m.elapsed_time_s)
    _append(
        rows,
        "Moving time",
        fmt_duration(m.moving_time_s),
        [f"elapsed {elapsed}"] if elapsed is not None else [],
    )

    if modality is Modality.RUN:
        best = _best_pace(m.max_speed_mps)
        _append(
            rows,
            "Pace",
            fmt_pace(m.avg_pace_s_per_km),
            [f"best {best}"] if best is not None else [],
        )
    elif modality is Modality.BIKE:
        mx = fmt_speed_kmh(m.max_speed_mps)
        _append(
            rows,
            "Speed",
            fmt_speed_kmh(m.avg_speed_mps),
            [f"max {mx}"] if mx is not None else [],
        )

    _append(rows, "Climb", fmt_int(m.elevation_gain_m, "m"), _altitude_sub(m))

    max_hr = fmt_int(m.max_heart_rate_bpm, "bpm")
    _append(
        rows,
        "Avg HR",
        fmt_int(m.avg_heart_rate_bpm, "bpm"),
        [f"max {max_hr}"] if max_hr is not None else [],
    )

    if modality is Modality.BIKE:
        _append(rows, "Power", fmt_int(m.avg_power_w, "w"), _power_subs(m))

    rows.extend(_supplemental_rows(ctx.activity))
    return "\n".join(rows)


def _append(rows: list[str], name: str, primary: str | None, subs: list[str]) -> None:
    """Append one key-stat row, or nothing when ``primary`` is absent (Req 13.1)."""
    if primary is None:
        return
    if subs:
        rows.append(f"| {name} | {primary} ({' · '.join(subs)}) |")
    else:
        rows.append(f"| {name} | {primary} |")


def _best_pace(max_speed_mps: float | None) -> str | None:
    """The best (fastest) pace from the maximum speed, or ``None`` when absent."""
    if max_speed_mps is None or max_speed_mps <= 0:
        return None
    return fmt_pace(1000.0 / max_speed_mps)


def _altitude_sub(m: DerivedMetrics) -> list[str]:
    """The ``min->max m`` altitude sub-value for the Climb row when both exist."""
    if m.min_altitude_m is None or m.max_altitude_m is None:
        return []
    return [f"{round(m.min_altitude_m)}→{round(m.max_altitude_m)} m"]


def _power_subs(m: DerivedMetrics) -> list[str]:
    """The NP/IF/TSS sub-values for the ride Power row, each only when available."""
    subs: list[str] = []
    np_w = fmt_int(m.normalized_power_w, "w")
    if np_w is not None:
        subs.append(f"NP {np_w}")
    if m.intensity_factor is not None:
        subs.append(f"IF {m.intensity_factor:.2f}")
    if m.power_tss is not None:
        subs.append(f"TSS {round(m.power_tss)}")
    return subs


def _supplemental_rows(activity: Activity) -> list[str]:
    """Recognized supplemental session values as summary rows (Req 6.7).

    The module-level fallback scale is applied only when ingest reports NO
    declared scale/offset for the key (``key not in
    activity.developer_fields_declared_scale``): a declared scale means ingest
    already decoded the value (fit-ingest Req 14.2, as amended), so applying
    the hundredths-guess factor on top would silently turn a CORRECT decoded
    number into one 100x wrong -- the exact regression pinned by
    ``test_declared_scale_developer_field_is_not_double_scaled``.
    """
    rows: list[str] = []
    for key, label, unit, fallback_scale, decimals in _SUPPLEMENTALS:
        if key not in activity.developer_fields:
            continue
        value = activity.developer_fields[key]
        if value is None:
            continue
        scale = (
            1.0 if key in activity.developer_fields_declared_scale else fallback_scale
        )
        text = _fmt_supplemental(value, scale, decimals)
        if text is None:
            continue  # unscalable value: omit the row rather than assert a number
        rows.append(f"| {label} | {text}{unit} |")
    return rows


def _fmt_supplemental(value: object, scale: float, decimals: int) -> str | None:
    """Apply a recognized supplemental's unit scale and format it (Req 6.7).

    Returns ``None`` when the raw value is not a real number -- a string, an
    array, or a bool cannot carry the declared scale, and a row is omitted rather
    than printed unscaled under a label that would make it false.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{value * scale:.{decimals}f}"


# --- telemetry chips --------------------------------------------------------


def telemetry_chips(ctx: DocContext) -> str:
    """A single line of per-series average chips plus threshold metrics (Req 8.4).

    One chip per available average among HR / Power / Cadence / Speed (from the
    derived metrics), then a TRIMP chip when ``trimp`` is present and a TSS chip
    when ``power_tss`` is present -- the threshold-dependent metrics athlete
    inputs enable (Req 8.4). A chip whose metric is ``None`` is omitted; the line
    is empty when nothing is available.
    """
    m = ctx.metrics
    chips: list[str] = []
    _chip(chips, "HR", fmt_int(m.avg_heart_rate_bpm, "bpm"))
    _chip(chips, "Power", fmt_int(m.avg_power_w, "w"))
    _chip(chips, "Cadence", fmt_int(m.avg_cadence_rpm, "rpm"))
    _chip(chips, "Speed", fmt_speed_kmh(m.avg_speed_mps))
    if m.trimp is not None:
        _chip(chips, "TRIMP", _fmt_load(m.trimp))
    if m.power_tss is not None:
        _chip(chips, "TSS", _fmt_load(m.power_tss))
    return " · ".join(chips)


def _chip(chips: list[str], label: str, value: str | None) -> None:
    """Append a ``**label** value`` chip, or nothing when the value is absent."""
    if value is not None:
        chips.append(f"**{label}** {value}")


def _fmt_load(value: float) -> str:
    """Format a load scalar to at most one decimal, trailing zeros trimmed."""
    text = f"{round(value, 1):.1f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


# --- hero chart: series selection + x-axis ----------------------------------


def hero_chart(ctx: DocContext) -> tuple[str, Asset] | None:
    """The hero chart image link and its SVG asset, or ``None`` (Req 7.1-7.6).

    Returns ``None`` when no plottable telemetry series exists (Req 7.6) -- the
    document then omits the chart entirely. Otherwise renders the prepared
    :class:`~fitdocs.render.charts.hero.HeroChartSpec` and returns a
    ``![alt](assets/<stem>-hero.svg)`` relative link paired with the
    :class:`~fitdocs.render.Asset` the sync engine writes.
    """
    spec = hero_chart_spec(ctx)
    if spec is None:
        return None
    rel_path = asset_rel_path(ctx.doc_stem, "hero")
    svg = render_hero_chart(spec)
    return f"![Telemetry hero chart]({rel_path})", Asset(rel_path=rel_path, content=svg)


def hero_chart_spec(ctx: DocContext) -> HeroChartSpec | None:
    """Select hero-chart series and x-axis from the activity (Req 7.2, 7.3).

    Series precedence is HR, then Power, then the sport fallback (Pace for runs /
    Speed for rides, both derived from the speed channel; Speed otherwise), then
    Cadence -- keeping at most the first two channels that carry data (Req 7.2).
    The x-axis is cumulative distance in km when the distance channel has data,
    else elapsed minutes (Req 7.3); samples with no x-value are dropped so the
    axis and every series stay aligned (real values only). The altitude channel,
    when present, becomes the backdrop. Returns ``None`` when no channel is
    plottable (Req 7.6).
    """
    s = ctx.activity.samples
    modality = ctx.activity.modality

    # Candidate series in precedence order, filtered to those with real data.
    candidates: list[tuple[str, str, str, list[float | None]]] = []
    _add_candidate(candidates, "HR", "bpm", HR_COLOR, _floats(s.heart_rate_bpm))
    _add_candidate(candidates, "Power", "w", POWER_COLOR, _floats(s.power_w))
    if modality is Modality.RUN:
        _add_candidate(candidates, "Pace", "/km", PACE_COLOR, _pace_values(s.speed_mps))
    else:
        _add_candidate(candidates, "Speed", "km/h", SPEED_COLOR, _kmh(s.speed_mps))
    _add_candidate(candidates, "Cadence", "rpm", CADENCE_COLOR, _floats(s.cadence_rpm))

    selected = candidates[:2]
    if not selected:
        return None

    # X-axis: cumulative distance km when present, else elapsed minutes.
    if _has_data(s.distance_m):
        x_unit = "km"
        raw_x: list[float | None] = [
            d / 1000.0 if d is not None else None for d in s.distance_m
        ]
    else:
        x_unit = "min"
        raw_x = [t / 60.0 for t in s.time_s]

    kept = [(i, xv) for i, xv in enumerate(raw_x) if xv is not None]
    if not kept:
        return None

    altitude = _floats(s.altitude_m)
    backdrop_present = _has_data(s.altitude_m)

    x_vals: list[float] = []
    series_acc: list[list[float | None]] = [[] for _ in selected]
    backdrop_acc: list[float | None] = []
    for index, xv in kept:
        x_vals.append(xv)
        for slot, (_, _, _, values) in enumerate(selected):
            series_acc[slot].append(values[index])
        if backdrop_present:
            backdrop_acc.append(altitude[index])

    series = tuple(
        HeroSeries(label=label, unit=unit, color=color, values=tuple(series_acc[slot]))
        for slot, (label, unit, color, _values) in enumerate(selected)
    )
    backdrop = tuple(backdrop_acc) if backdrop_present else None
    return HeroChartSpec(
        x=tuple(x_vals), x_unit=x_unit, series=series, backdrop=backdrop
    )


def _add_candidate(
    candidates: list[tuple[str, str, str, list[float | None]]],
    label: str,
    unit: str,
    color: str,
    values: list[float | None],
) -> None:
    """Register a candidate series only when the channel carries real data."""
    if _has_data(values):
        candidates.append((label, unit, color, values))


def _has_data(values: Sequence[float | None]) -> bool:
    """True when at least one sample in ``values`` is recorded (not ``None``)."""
    return any(v is not None for v in values)


def _floats(values: Sequence[float | None]) -> list[float | None]:
    """Copy a channel to floats, preserving ``None`` holes (never a fake 0)."""
    return [float(v) if v is not None else None for v in values]


def _kmh(speed_mps: Sequence[float | None]) -> list[float | None]:
    """The speed channel converted to km/h, preserving ``None`` holes."""
    return [v * 3.6 if v is not None else None for v in speed_mps]


def _pace_values(speed_mps: Sequence[float | None]) -> list[float | None]:
    """The speed channel as pace (s/km); non-positive or absent speeds are holes."""
    return [1000.0 / v if (v is not None and v > 0) else None for v in speed_mps]


# --- route map --------------------------------------------------------------


def map_section(ctx: DocContext) -> tuple[str, Asset] | None:
    """The route map image link and its SVG asset, or ``None`` (Req 1.1-1.4, 2.3).

    Returns ``None`` when the context carries no prepared map inputs
    (``ctx.map_data is None``) -- no positions, tiles unavailable, or a strength
    activity -- so the document omits the Map section and its asset entirely (Req
    1.3). Otherwise the route is tinted by sport (rides use
    :data:`~fitdocs.render.charts.palette.ROUTE_BIKE_TINT`, runs
    :data:`~fitdocs.render.charts.palette.ROUTE_RUN_TINT`, and every other
    modality the neutral :data:`~fitdocs.render.charts.palette.ROUTE_NEUTRAL_TINT`,
    Req 2.3), the already-resolved tiles are composed into one self-contained SVG
    (:func:`~fitdocs.render.charts.map.compose_map`), and the function returns a
    ``![Route map](assets/<stem>-map.svg)`` relative link -- the same
    document-relative convention as the other chart assets (Req 1.4, 6.2) --
    paired with the :class:`~fitdocs.render.Asset` the sync engine writes.
    """
    md = ctx.map_data
    if md is None:
        return None
    modality = ctx.activity.modality
    if modality is Modality.BIKE:
        tint = ROUTE_BIKE_TINT
    elif modality is Modality.RUN:
        tint = ROUTE_RUN_TINT
    else:
        tint = ROUTE_NEUTRAL_TINT
    svg = compose_map(md.plan, dict(md.tiles), tint=tint, attribution=md.attribution)
    rel_path = asset_rel_path(ctx.doc_stem, "map")
    return f"![Route map]({rel_path})", Asset(rel_path=rel_path, content=svg)


# --- HR-zone strip ----------------------------------------------------------


def zone_strip(ctx: DocContext) -> tuple[str, Asset] | None:
    """The HR time-in-zone strip image link and asset, or ``None`` (Req 8.1, 8.2).

    Included only when the metrics carry real, athlete-derived time-in-zone
    (``hr_time_in_zone_s`` is not ``None``): bands ``Z1..Zn`` take their seconds
    from the tuple and their colors from the documented zone ramp. Returns
    ``None`` when no zone times exist -- this module never invents zone
    boundaries or default zones (Req 8.2). An all-zero tuple (no recorded time in
    any zone) is likewise not zone data to display, so the strip is omitted.
    """
    times = ctx.metrics.hr_time_in_zone_s
    if times is None:
        return None
    colors = zone_colors(len(times))
    bands = [
        ZoneBand(label=f"Z{i + 1}", seconds=seconds, color=colors[i])
        for i, seconds in enumerate(times)
    ]
    svg = render_zone_strip(bands)
    if not svg:
        return None
    rel_path = asset_rel_path(ctx.doc_stem, "zones")
    return (
        f"![Heart-rate time-in-zone]({rel_path})",
        Asset(rel_path=rel_path, content=svg),
    )


# --- devices / data quality -------------------------------------------------


def devices_section(ctx: DocContext) -> str:
    """The devices table, per-channel coverage, and decode errors (Req 6.6, 13.2).

    The devices table's display name prefers ``product_name`` (real files decode
    ``manufacturer`` as the literal placeholder ``development``), shows the
    manufacturer only when it is informative, and flags a low/critical battery.
    The coverage table has a row only for channels that carry data (Req 13.2).
    Decode errors from provenance render as a bulleted list, or an explicit
    "none" indicator when the file decoded cleanly.
    """
    activity = ctx.activity
    blocks: list[str] = []

    if activity.devices:
        blocks.append(_devices_table(activity))

    coverage = _coverage_table(activity)
    if coverage is not None:
        blocks.append(f"**Channel coverage**\n\n{coverage}")

    blocks.append(_decode_errors(activity))
    return "\n\n".join(blocks)


def _devices_table(activity: Activity) -> str:
    """The recording-devices table (Req 6.6)."""
    rows = [
        "| Device | Manufacturer | Software | Battery |",
        "| --- | --- | --- | --- |",
    ]
    for device in activity.devices:
        name = device.product_name or device.manufacturer or "Unknown device"
        manufacturer = _manufacturer_cell(device.manufacturer)
        software = cell(_fmt_software(device.software_version))
        battery = _battery_cell(device.battery_status)
        rows.append(f"| {name} | {manufacturer} | {software} | {battery} |")
    return "\n".join(rows)


def _manufacturer_cell(manufacturer: str | None) -> str:
    """The manufacturer cell, suppressing the non-informative placeholder."""
    if manufacturer is None:
        return ABSENT
    if manufacturer.strip().lower() == _MANUFACTURER_PLACEHOLDER:
        return ABSENT
    return manufacturer


def _fmt_software(version: float | None) -> str | None:
    """Format a software version compactly, or ``None`` when unrecorded."""
    if version is None:
        return None
    return f"{version:g}"


def _battery_cell(status: str | None) -> str:
    """The battery cell: ``ABSENT`` when unrecorded, bold-flagged when low/critical."""
    if status is None:
        return ABSENT
    if status.strip().lower() in _BATTERY_FLAGS:
        return f"**{status}**"
    return status


def _coverage_table(activity: Activity) -> str | None:
    """Per-channel coverage percentages, rows only for present channels (Req 13.2).

    Returns ``None`` when the activity has no samples or no channel carries data.
    """
    samples = activity.samples
    total = len(samples.time_s)
    if total == 0:
        return None
    rows: list[str] = []
    for attr, label in _COVERAGE_CHANNELS:
        channel: Sequence[float | None] = getattr(samples, attr)
        present = sum(1 for v in channel if v is not None)
        if present == 0:
            continue
        rows.append(f"| {label} | {round(present / total * 100)}% |")
    if not rows:
        return None
    return "\n".join(["| Channel | Coverage |", "| --- | --- |", *rows])


def _decode_errors(activity: Activity) -> str:
    """The decode-error block: a bulleted list, or a 'none' indicator (Req 6.6)."""
    errors = activity.provenance.decode_errors
    if not errors:
        return "**Decode errors:** none"
    bullets = "\n".join(f"- {error}" for error in errors)
    return f"**Decode errors:**\n\n{bullets}"


# --- training-load placeholder + notes region -------------------------------


def load_section() -> str:
    """The ``load`` region in its not-computed state (Req 11.1, 11.2, 11.4).

    Emits the :data:`~fitdocs.contract.LOAD_REGION` region whose inner content is
    exactly :data:`fitdocs.contract.LOAD_NOT_COMPUTED` -- a graceful "not
    computed" state with no numbers or zeros. This layer computes no training
    load of any kind (Req 11.4); this is the stable placeholder the training-load
    feature fills.
    """
    return region_block(LOAD_REGION, LOAD_NOT_COMPUTED)


def notes_region(placeholder: str) -> str:
    """The :data:`~fitdocs.contract.NOTES_REGION` region wrapping a placeholder.

    The placeholder is carried verbatim (Req 10.5); on regeneration the user's
    own notes replace it and survive via the region-merge contract.
    """
    return region_block(NOTES_REGION, placeholder)
