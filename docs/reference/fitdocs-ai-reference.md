# fitdocs.ai reference — what we borrow, approximate, or must build ourselves

Findings from a deep read of `joshua-stauffer/fitdocs.ai`, the reference app
for our activity views and metrics. File paths below are relative to that
repo. The headline: fitdocs.ai is primarily an Intervals.icu-backed coaching
app — its **local** `.fit` path computes only a small scalar set, and the rich
derived metrics are *imported* from Intervals.icu. For an offline one-to-one
`.fit` → markdown tool, we must compute those locally.

## 1. `.fit` ingestion (borrow directly)

- Parser: **`garmin-fit-sdk>=21.202.0`** (official Garmin FIT SDK for Python);
  `gpxpy` for `.gpx`. Decode call (`app/ingestion/manual_upload/parsers.py`):

  ```python
  stream = Stream.from_byte_array(raw)
  decoder = Decoder(stream)
  if not decoder.is_fit(): raise ...
  decoder.check_integrity()
  stream.reset()  # is_fit/check_integrity advance the stream
  messages, _errors = decoder.read(
      apply_scale_and_offset=True,
      convert_datetimes_to_dates=False,
      expand_components=True,
  )
  ```

- Message types read: `record_mesgs` (samples), `session_mesgs` (summary),
  `lap_mesgs`, `sport_mesgs`, `activity_mesgs` (fallback totals),
  `device_info_mesgs`. **`set_mesgs` is NOT read** — fitdocs.ai has no
  strength set/rep parsing; we must add it (Garmin encodes sets/reps/weight/
  exercise category in `set_mesgs` + `exercise_title`).
- Per-record channels (parallel arrays, absent = `None`, never `0`):
  `heart_rate`, `power`, `cadence`, `position_lat/long` (semicircles → degrees
  via `180/2³¹`), `altitude` (prefer `enhanced_altitude`), `speed` (prefer
  `enhanced_speed`, m/s), `distance` (cumulative m), `temperature`, plus
  `time_offset_s` since `start_time`. FIT epoch = 1989-12-31 UTC.
- Laps are projected onto record indices (`start_index`/`end_index`,
  inclusive) by matching lap `start_time` to record timestamps.
- Sport map: `cycling→Ride, running→Run, swimming→Swim, walking→Walk,
  hiking→Hike, rowing→Rowing, training/fitness_equipment/generic→Workout`;
  indoor sub-sports flagged separately. Modalities: `run|bike|swim|strength|other`.
- Raw bytes are archived (sha256-keyed) **before** parsing; identity
  `manual:<sha256>` gives replay dedup. Worth copying: never lose the source.

## 2. Metrics: local vs imported (the parity gap we must close)

**Computed locally from the `.fit`** (`.../summary.py`, `.../load.py`):
moving time (session `total_timer_time`, else speed>0.5 m/s or
distance-increase pairs), elapsed, distance, avg/max HR, avg power,
avg cadence, elevation gain (session `total_ascent`, else positive deltas of
10-sample boxcar-smoothed altitude), TRIMP, power TSS, `training_load =
power_load if present else hr_load`.

**Imported from Intervals.icu** (`app/ingestion/intervals_icu/mappers.py`) —
i.e. **we must implement locally for parity**: normalized power, intensity
factor, efficiency factor, variability index, decoupling %, avg pace,
grade-adjusted pace, time-in-zone (HR/power/pace, 7 zones + sweet spot),
calories, min/max/avg altitude & temperature, max speed, CTL/ATL/TSB.

### Local load formulas (reusable verbatim)

TRIMP (Banister, sex-neutral), per consecutive sample pair with dt>0:

```python
HRr = clamp((hr - rest)/(max - rest), 0, 1)
trimp += dt_min * HRr * 0.64 * exp(1.92 * HRr)
```

Returns `None` when resting/max HR unknown — never fabricates.

Power TSS with NP as intermediate: resample power to 1 Hz (None→0 for
coasting), 30 s trailing rolling mean `ra30`, then

```python
NP  = mean(ra30 ** 4) ** 0.25
IF  = NP / FTP
TSS = T_seconds * NP * IF / (FTP * 3600) * 100
```

### Zone models (from `fitdocs-spec.md` §8)

- Run 5-zone, pace-anchored at threshold pace: Z1 >120%, Z2 110–120%,
  Z3 100–110%, Z4 95–100%, Z5 <95% (faster).
- Bike 7-zone Coggan (% FTP): <55, 55–75, 76–90, 91–105, 106–120, 121–150, >150.
- HR 5-zone (% threshold HR): <75, 75–89, 89–95, 95–100, >100.
- 3-zone distribution grouping: Low (Z1–Z2), Moderate (Z3), High (Z4+).

## 3. Activity detail view (the doc template model)

Rendered only for completed **bike + run** (strength gets a scalar fallback).
Section order — our markdown doc should mirror it:

1. **Hero** — editable self-note (serif italic quote), **KeyStats** 6-cell
   grid, route map.
   - KeyStats order: Distance | Moving (+ "elapsed X" sub) | Pace (run,
     `m:ss /km` + best) or Speed (bike, km/h + max) | Climb (+ `min→max m`
     sub) | Avg HR (+ max sub) | Power (bike: `NP · IF · TSS` sub).
   - Map: non-interactive Leaflet on ESRI World Topo tiles; glow polyline
     (weight 10, opacity 0.2) under foreground polyline (weight 4, 0.95);
     start/end pins; tint bike `#1f4d8a`, run `#b22d4a`; overlays: route-name
     pill + `↑ gain ↓ loss peak max` stats.
2. **Telemetry** — metric chips (each shows its average) + **MultiChart**
   (the hero graph) + HR-zone strip.
3. **Splits** — re-sourceable table: device laps / 1 km / 1 mi / 5 km,
   sliced client-side from the sample stream. ~12 sport-aware columns
   (run: Distance, Time, Pace, Avg/Max HR, Avg/Max pwr, Cadence …;
   bike adds Avg km/h and NP — approximated per split as `avgPwr*1.06`).
   Fastest/slowest split accented; elapsed-weighted Σ summary row.
4. **Devices** — trust-graded table (clean / minor gaps / battery low /
   unreliable) with per-channel coverage %, gap counts, HR-source flag.

### The power-vs-HR hero graph (`MultiChart.tsx`) — spec to reproduce in SVG

- **X axis**: cumulative **distance in km** (not time), ticks at 0.1 precision.
- **Default series**: HR + Power overlaid (falls back to first available
  metric). One line per active metric.
- **Normalization trick**: single hidden y-axis; each metric independently
  min/max-normalized into band **[0.42, 0.92]**; elevation rendered as a faint
  backdrop `Area` normalized into **[0, 0.32]** (fill `#888`, opacity 0.18);
  flat series pinned to 0.67. Y-axis ticks shown only when exactly one metric
  is active (3 ticks at 0.42/0.67/0.92 mapped back to metric units).
- **Smoothing**: null-skipping symmetric boxcar, default k=5 (11-sample
  window); no downsampling. Raw values preserved for tooltips.
- **Style**: line width 1.8, no dots, monotone interpolation; dashed vertical
  cursor `3 3`.
- **Colors (oklch)**: HR `oklch(0.6 0.18 14)` red; Power `oklch(0.62 0.17 60)`
  amber; run Pace `oklch(0.55 0.16 240)` blue; bike Speed
  `oklch(0.55 0.16 200)`; Cadence `oklch(0.6 0.17 60)`; Altitude
  `oklch(0.55 0.14 150)`; Temp `oklch(0.6 0.14 60)`.
- **HR-zone strip** below: horizontal stacked bar of time-in-zone; dt between
  adjacent samples attributed to the zone of the sample's HR. NOTE: the
  reference uses hard-coded fallback bands (Z1 <132, Z2 132–152, Z3 152–165,
  Z4 165–178, Z5 178–220) because the wire lacks athlete zones — **we should
  use the athlete's actual zones instead**.
- Lap markers are *not* overlaid on the chart; laps live in the Splits table.

## 4. Weight training

No `.fit` strength support in the reference. Sets/reps exist only as planning
`Routine` objects (`{name, focus, exercises: [{name, sets: [{reps, load?,
rest?}]}]}`) displayed as a per-exercise `set | reps | load | rest` table
(`StrengthDrawer.tsx`) — a reasonable display model for our strength doc view,
but the data must come from our own `set_mesgs` parsing.

## 5. Athlete settings model

`athlete_zones`, versioned per sport (`run|bike|swim|strength|other`):
thresholds `lthr_bpm, max_hr_bpm, resting_hr_bpm, ftp_watts,
indoor_ftp_watts, threshold_pace_seconds_per_km, w_prime_joules, p_max_watts`
+ 7 zone upper bounds each for HR (bpm), power (% FTP), pace (s/km).
Thresholds are **user-confirmed, never silently updated**; unset thresholds
mean load comes back `None` (no fabricated defaults) — a principle worth
keeping: it's exactly our "prompt the user for missing required fields" hook.
Fallback used there: `max_hr ≈ lthr / 0.92` when max HR unset.

## 6. Design decisions to copy or diverge from

- **Copy**: column-major channel arrays with `null` for absent; raw-file
  archival before parsing; loud `None` over fabricated metrics; sport-aware
  metric catalogs; splits re-slicing from the stream (device laps + fixed
  distances).
- **Diverge**: compute rich metrics locally (no Intervals.icu dependency);
  parse `set_mesgs` for strength; use athlete's real zones in the zone strip;
  static SVG charts instead of Recharts; markdown sections instead of React
  components; skip the map for v1 unless a static route SVG proves cheap
  (no tile server in markdown).
