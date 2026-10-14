# Wellness

fitdocs keeps daily wellness as a local, source-attributed series alongside
workouts. It imports files offline, archives the handled bytes, and rebuilds
plain CSV files you can read without fitdocs. Recovery pages, workout morning
blocks, Apple Health import and automatic wellness pulling are future work.

## Get files into the inbox

Drop individual supported JSON files into the configured [inbox](inbox.md),
then run the inbox drain from your usual data root:

```bash
fitdocs sync
fitdocs check
```

An explicit `fitdocs sync SOURCE` processes workout FIT files; use bare
`fitdocs sync` for wellness. The default inbox is `<data-root>/inbox/`.
Use `[inbox] path` in `<data-root>/fitdocs.toml` to choose another location.
The default disposition leaves files in place. Opt-in `disposition = "move"`
moves successfully archived files to `processed_dir`; the drain never deletes
an inbox file. Unrecognized JSON is reported and left in place; `[inbox] ignore`
can silence a known unrelated file. A failed wellness file is quarantined by
its content hash; correct its bytes or use `fitdocs sync --retry-quarantined`
after fixing the cause. Deferred files are considered again on the next drain.

You can save an intervals.icu wellness API response as a `.json` file and drop
it into the inbox today. wellness-pull is planned; it does not yet provide a
command here. Its future connector deliveries use the [envelope below](#delivery-envelope).
Apple Health import is planned and is not a supported format yet.

A Garmin monitoring, sleep or settings `.fit` file is not one of these JSON
exports. A FIT header declaring a non-activity type is skipped with a warning,
creates no workout page and stays in the inbox under every disposition.
Garmin wellness FIT message parsing and whole export ZIP import are not supported.

## Supported files and source definitions

Extract Garmin's data-export ZIP yourself and drop only the individual JSON
files below, including all date chunks you need. Names here are patterns;
recognition uses record structure (and the matching name for an empty list),
not a particular account identifier. Each format archives its original bytes.
All four Garmin formats use source `garmin-export` and origin `garmin`.

| File pattern | What is imported and how |
| --- | --- |
| `UDSFile_*.json` | Daily summaries: `currentDayRestingHeartRate` → resting HR; `minHeartRate` / `maxHeartRate` → lowest / highest HR; `totalSteps` → steps; `averageSpo2Value` → SpO2; `allDayStress.aggregatorList` with type `TOTAL` → stress level; `bodyBattery.bodyBatteryStatList` with types `HIGHEST` / `LOWEST` → body battery extrema. The rolling `restingHeartRate` field is ignored. |
| `*_sleepData.json` | Deep, light and REM seconds from `deepSleepSeconds`, `lightSleepSeconds`, `remSleepSeconds`; total sleep is their sum, excluding awake time. `awakeSleepSeconds` supplies awake time when total sleep is positive; `averageRespiration` supplies respiration. An unconfirmed night with no stages supplies no sleep duration; it may still supply respiration. |
| `MetricsMaxMetData_*.json` | `vo2MaxValue` for sport `RUNNING` / `CYCLING` → running / cycling VO2max. Other or missing sports are ignored; `updateTimestamp` selects the latest record. |
| `*_userBioMetrics.json` | `weight.weight`, converted from grams to kilograms, under `metaData.calendarDate`. Other body measurements are ignored. |
| intervals.icu wellness `.json` | A bare nonempty list from the [wellness API](https://intervals.icu/api-docs.html), or the delivery envelope below. Source `intervals-icu`; origin is unknown for a bare list and field-specific for an envelope. |

Garmin's daily resting HR is its lowest 30-minute average over a 24-hour period;
fitdocs imports the daily `currentDayRestingHeartRate`, not the separate rolling
average. See [Garmin's definition](https://support.garmin.com/en-AU/?faq=F8YKCB4CJd5PG0DR9ICV3A).
Apple's resting HR is a sedentary estimate from background readings, using motion
data to identify inactive periods; it can be revised during the day. Apple is
relevant when a relay supplies Apple measurements, while direct Apple Health
import remains future work. See [Apple's measurement description](https://support.apple.com/en-mide/120277)
and [HealthKit's resting HR definition](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/restingheartrate).
intervals.icu passes on its upstream platform's definition: an Apple-origin
resting HR and a Garmin-origin resting HR need not measure the same thing.
fitdocs preserves that provenance instead of making their definitions equal.

For intervals.icu, each field has its upstream meaning in the metric's listed
unit, with no unit conversion. Only these fields are imported:

| intervals.icu field | Metric |
| --- | --- |
| `restingHR` | `resting_hr_bpm` |
| `hrv` | `hrv_rmssd_ms` |
| `hrvSDNN` | `hrv_sdnn_ms` |
| `sleepSecs` | `sleep_s` |
| `avgSleepingHR` | `sleep_hr_bpm` |
| `respiration` | `respiration_brpm` |
| `spO2` | `spo2_pct` |
| `steps` | `steps` |
| `vo2max` | `vo2max_ml_per_kg_min` |
| `weight` | `weight_kg` |
| `fatigue` | `fatigue_rating` |
| `mood` | `mood_rating` |
| `motivation` | `motivation_rating` |
| `soreness` | `soreness_rating` |
| `stress` | `stress_rating` |
| `injury` | `injury_rating` |
| `hydration` | `hydration_rating` |

The seven ratings retain the recorded 1–4 numbers without reinterpreting their
scale. SDNN and rMSSD stay separate; neither is converted into or spliced onto
the other. Other fields, including `ctl`, `atl`, `rampRate`, `ctlLoad`, `atlLoad`,
`sportInfo`, `sleepScore` and `readiness`, are ignored. No training-model output
such as fitness, fatigue or estimated FTP is imported. The subjective
`fatigue` rating is distinct from computed training fatigue.

## Metrics

Ranges are inclusive acceptance limits for recorded values, not clinical
reference ranges. Unit tokens: `bpm` = beats/minute; `ms` = milliseconds;
`s` = seconds; `brpm` = breaths/minute; `pct` = percent; `kg` = kilograms;
`ml_per_kg_min` = millilitres per kilogram per minute; `—` = unitless.
The supported-file definitions above specify which source provides each metric.

| Metric | Label | Unit | Minimum | Maximum | Meaning |
| --- | --- | --- | --- | --- | --- |
| `resting_hr_bpm` | Resting HR | bpm | 1 | 250 | The day's resting heart rate, as the source defines it |
| `min_hr_bpm` | Lowest HR | bpm | 1 | 250 | Lowest heart rate recorded that day |
| `max_hr_bpm` | Highest HR | bpm | 1 | 250 | Highest heart rate recorded that day, workouts included |
| `hrv_sdnn_ms` | HRV (SDNN) | ms | 1 | 1000 | Heart-rate variability as SDNN |
| `hrv_rmssd_ms` | HRV (rMSSD) | ms | 1 | 1000 | Heart-rate variability as rMSSD |
| `sleep_s` | Sleep | s | 1 | 86400 | Total sleep (excluding awake time) of the night ending on the day |
| `sleep_deep_s` | Deep sleep | s | 0 | 86400 | Deep sleep of that night |
| `sleep_light_s` | Light sleep | s | 0 | 86400 | Light sleep of that night |
| `sleep_rem_s` | REM sleep | s | 0 | 86400 | REM sleep of that night |
| `sleep_awake_s` | Awake in sleep | s | 0 | 86400 | Awake time within that night's sleep |
| `sleep_hr_bpm` | Sleeping HR | bpm | 1 | 250 | Average heart rate during that night's sleep |
| `respiration_brpm` | Respiration | brpm | 1 | 100 | Average respiration rate, as the source defines it |
| `spo2_pct` | SpO2 | pct | 1 | 100 | Average blood-oxygen saturation, as the source defines it |
| `weight_kg` | Weight | kg | 1 | 500 | Body weight |
| `vo2max_ml_per_kg_min` | VO2max | ml_per_kg_min | 1 | 100 | VO2max estimate not tied to a sport by its source |
| `vo2max_run_ml_per_kg_min` | VO2max (running) | ml_per_kg_min | 1 | 100 | Running VO2max estimate |
| `vo2max_ride_ml_per_kg_min` | VO2max (cycling) | ml_per_kg_min | 1 | 100 | Cycling VO2max estimate |
| `steps` | Steps | — | 1 | 1000000 | Steps that day |
| `stress_level` | Stress level | — | 1 | 100 | Average all-day stress level (Garmin's 0–100 scale) |
| `body_battery_highest` | Body battery (highest) | — | 1 | 100 | Highest body battery that day |
| `body_battery_lowest` | Body battery (lowest) | — | 1 | 100 | Lowest body battery that day |
| `fatigue_rating` | Fatigue (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |
| `mood_rating` | Mood (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |
| `motivation_rating` | Motivation (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |
| `soreness_rating` | Soreness (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |
| `stress_rating` | Stress (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |
| `injury_rating` | Injury (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |
| `hydration_rating` | Hydration (rating) | — | 1 | 4 | The athlete's subjective rating, as recorded on the source's 1–4 scale |

## Wellness day

Every value belongs to one wellness day, a local calendar date. Sleep and every
overnight value belong to the wake date. When a format supplies a sleep end
timestamp instead of a date, an end at or after 18:00 on D−1 and before 18:00 on D
belongs to D: take the date of end + 6 hours in its recorded UTC offset. A
source-supplied calendar date is kept: Garmin calendarDate and intervals.icu id
are wake dates for nights. The machine's timezone is never used. The night
before a workout on local date D is the sleep of wellness day D. That morning's
resting HR and HRV are the values of day D; a day-summary resting HR may be
computed over the whole day D.

## Delivery envelope

This is the file contract for the future wellness-pull implementation. A manual
export may use the same envelope now. Write UTF-8 JSON followed by one LF newline,
using `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
plus `"\n"`. For example (synthetic data):

```json
{"format":"fitdocs.intervals-icu-wellness","origins":{"restingHR":"garmin"},"records":[{"id":"2026-01-02","restingHR":51,"updated":"2026-01-03T09:00:00Z"}],"version":1}
```

`format`, `version` and `records` are required. `format` is
`fitdocs.intervals-icu-wellness`; `version` is `1`. `records` holds exactly the
selected day records from `GET /api/v1/athlete/{id}/wellness`, with every field
verbatim, sorted by `id`, with no duplicate `id`. Preserve computed fields in
the delivered bytes; the importer ignores them. `id` is an ISO `YYYY-MM-DD`
date. `updated` is the record's update timestamp and decides which revision wins.
A later record replaces all mapped fields, including values that became null.

`origins` is optional: intervals.icu field name → lowercase platform token
matching `[a-z0-9]+(-[a-z0-9]+)*`, such as `garmin` or `apple`. The future pull
obtains these from the athlete's `*_wellness_keys`; unnamed fields have no origin.
No other envelope key and no pull timestamp are emitted. A newer unsupported
envelope version is unrecognized with a reason naming the newer version.

Place the delivery anywhere under the inbox with a `.json` suffix; recommended
path: `<inbox>/<instance>/wellness-<first id>_<last id>.json`. Recognition is by
content. The archive path is `wellness-archive/intervals-icu/<sha256>.json`, named
by SHA-256 of the original delivery bytes. Re-delivering identical bytes is
already archived. A bare API response list is also accepted but supplies no origins.

## Absent values

Missing, non-finite, out-of-range and placeholder measurements produce no row,
not a zero or a carried-forward estimate. The Python reader returns `None` when
there is no value. A zero is absent for every metric whose minimum is 1 in the
table, including resting HR, steps, stress and body battery. Garmin's negative
stress placeholders (`-1`, `-2`) are absent too. Zero is valid for deep, light,
REM and awake sleep seconds; Garmin exposes those stages only when their total
sleep is positive. A new revision can withdraw an earlier measurement.

## Source precedence

All sources' values are retained. Exactly one available source is canonical for
each day and metric; consumers can instead follow a single source consistently.
The default source ranking is device, then hub, then relay, then source id
within each kind. Today that puts `garmin-export` before `intervals-icu`.
Future source registrations can extend the ranking.

Set the order in `<data-root>/fitdocs.toml`:

```toml
[wellness]
precedence = ["intervals-icu", "garmin-export"]

[wellness.metric_precedence]
resting_hr_bpm = ["garmin-export"]
```

The general list applies to all metrics; a metric-specific list replaces it for
that metric. Every partial list is completed with remaining registered sources
in default order. An empty list uses the default. Unknown sources, duplicate
sources, unknown metrics and malformed lists are configuration errors before
writes. Only registered source ids are accepted; `apple-health` is not registered
yet. Changed precedence rebuilds the series on the next drain or `fitdocs regen`.
Precedence does not mix or average sources, and does not alter their definitions.

## Read the series

`<data-root>/wellness/<year>.csv` holds one UTF-8 CSV per calendar year, sorted
by day, metric and source. Its header is:

```csv
day,metric,source,origin,value,canonical
2026-01-02,resting_hr_bpm,garmin-export,garmin,51,true
2026-01-02,resting_hr_bpm,intervals-icu,,53,false
```

These rows are synthetic. Empty `origin` means unknown; `canonical` is `true` or
`false`. Every row's value uses the metric's unit. `manifest.toml` beside the
CSVs records generator/version, inputs, effective precedence, file hashes and
counts, archive-entry states and conflicts. Both series and manifest are
fitdocs-owned and rebuilt from the archive; do not edit them. A blocked or
unreadable rebuild leaves the last complete series available and reports why.

In a spreadsheet, open a yearly CSV, treat `day` as a date, and filter
`canonical` to `true` (or choose one `source`) before aggregating. Keep metrics
separate because their units differ. Gaps are absent measurements, not zeros.

In your own DuckDB client, start in the data root and read these local CSVs:

```sql
SELECT day, value, source
FROM read_csv('wellness/*.csv', header = true)
WHERE metric = 'resting_hr_bpm' AND canonical
ORDER BY day;
```

This file reader belongs to your own DuckDB client; the `fitdocs query` sandbox
cannot read CSV files. For standard-library Python:

```python
import csv
from pathlib import Path

with Path("/path/to/data/wellness/2026.csv").open(newline="", encoding="utf-8") as stream:
    for row in csv.DictReader(stream):
        if row["metric"] == "resting_hr_bpm" and row["canonical"] == "true":
            print(row["day"], float(row["value"]), row["source"])
```

Code using fitdocs should use its shared reader, which handles all listed years:

```python
from datetime import date
from pathlib import Path
from fitdocs.wellness import Metric, read_series

series = read_series(Path("/path/to/data"))
value = series.canonical(Metric.RESTING_HR_BPM, date(2026, 1, 2))
if value is not None:
    print(value.value, value.source, value.origin)
source_values = series.by_source(Metric.RESTING_HR_BPM, "garmin-export")
```

The reader also provides `days`, `for_day`, `sources`, `value` and
`canonical_series`. It reads only the normalized series, not the archived inputs.

## Archive and withdrawal

Handled inputs live at `wellness-archive/<format>/<original-sha256>.json`:
`intervals-icu`, `garmin-uds`, `garmin-sleep`, `garmin-maxmet` or
`garmin-biometrics`. Entries are immutable. Byte-identical inputs of one format
share an entry; a failed parse writes no archive entry. The next drain rebuilds
the series after intake; `fitdocs regen` forces a rebuild before rendering pages.

To withdraw a wrong import, identify and remove its entry from the wellness
archive, then run `fitdocs regen`. Remove its inbox copy too, or the next drain
can import it again. A connector's own stored copy may also need withdrawal
through that connector's workflow. Removing one entry preserves the values in
remaining entries. Conflicting duplicates within one source are resolved by
revision when present, otherwise by a deterministic archive-reference order;
`check` reports conflicts rather than silently averaging them.

## Check findings

`fitdocs check` is read-only and offline. It lists archive metadata, reads the
series and settings, and does not open archive entries. The relevant findings are:

| Finding | What to do |
| --- | --- |
| `wellness_orphaned_entry` | A file under the archive is not read by any supported format. Move it out; if it is a supported wellness input, put it in the inbox instead. |
| `wellness_series_stale` | The archive, settings or generated files changed, or the series is missing. Run `fitdocs sync` or `fitdocs regen`. |
| `wellness_series_occupied` | A series path contains something fitdocs did not write. Inspect it and move or remove it yourself to free the path. fitdocs refuses to overwrite it. |
| `wellness_conflict` | Inspect the named day, metric, source, kept value and entries. If an entry is wrong, remove it from archive and inbox and run `fitdocs regen`; otherwise the reported deterministic choice stays. |

Missing, stale or foreign `AGENTS.md` declarations for `wellness/` and
`wellness-archive/` are also reported through the normal ownership findings.

## wellness_daily

The disposable [analytics index](analytics.md) exposes the normalized series as
`wellness_daily`: `day` (DATE), `metric`, `source`, `origin`, `value` (DOUBLE),
`unit` and `canonical` (BOOLEAN). Unknown origin and unitless metrics use SQL
`NULL` for those columns. It includes every source, not just canonical rows,
and reflects the last index refresh. It does not re-parse the wellness archive.

The table's `origin` column records the platform that measured each value, and
any surface that charts or prints values whose `origin` is `garmin` (a dashboard
over `wellness_daily`, for example) owes Garmin attribution, as the future
recovery page and morning-of block will give it.

Build or refresh the index, inspect the schema, then query canonical values or
one source explicitly:

```bash
fitdocs index
fitdocs query --schema
fitdocs query "SELECT day, value, source, origin FROM wellness_daily WHERE metric = 'resting_hr_bpm' AND canonical ORDER BY day" --format csv
fitdocs query "SELECT day, value FROM wellness_daily WHERE metric = 'hrv_rmssd_ms' AND source = 'intervals-icu' ORDER BY day"
```

Series files stay the source for wellness consumers; deleting the index costs
only a rebuild. Recovery baselines, scores, benchmark derivation and new pages
are not provided by this file import feature.
