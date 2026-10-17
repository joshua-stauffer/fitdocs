# Wellness

fitdocs keeps daily wellness as a local, source-attributed series alongside
workouts. It imports files offline, archives the handled bytes, and rebuilds
plain CSV files you can read without fitdocs. The [recovery page](recovery.md)
reads the series, and `fitdocs derive-benchmarks` derives resting heart rate from
it ([configuration](configuration.md)); workout morning blocks are future work.

## Get files into the inbox

Drop supported JSON files or an Apple Health `.zip` / `.xml` export into the
configured [inbox](inbox.md),
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
an inbox file. Unrecognized JSON, ZIP and XML is reported and left in place; `[inbox]
ignore`
can silence a known unrelated file. A failed wellness file is quarantined by
its content hash; correct its bytes or use `fitdocs sync --retry-quarantined`
after fixing the cause. Deferred files are considered again on the next drain.

You can save an intervals.icu wellness API response as a `.json` file and drop
it into the inbox. Connector deliveries use the [envelope below](#delivery-envelope).

The intervals.icu pull delivers wellness files into the inbox: set
`wellness = true` on your connector instance and run `fitdocs pull --sync`.
See [wellness pulling](connectors.md#wellness) for setup and limits.

Apple Health exports are supported as `.zip` or bare `.xml`; see [Apple
Health](#apple-health).

A Garmin monitoring, sleep or settings `.fit` file is not one of these JSON
exports. A FIT header declaring a non-activity type is skipped with a warning,
creates no workout page and stays in the inbox under every disposition.
Garmin wellness FIT message parsing and whole Garmin export ZIP import are not supported.

## Supported files and source definitions

Extract Garmin's data-export ZIP yourself and drop only the individual JSON
files below, including all date chunks you need. Names here are patterns;
recognition uses record structure (and the matching name for an empty list),
not a particular account identifier. These JSON formats archive their original bytes;
Apple Health archives the extract described below.
All four Garmin formats use source `garmin-export` and origin `garmin`.

| File pattern | What is imported and how |
| --- | --- |
| `UDSFile_*.json` | Daily summaries: `currentDayRestingHeartRate` → resting HR; `minHeartRate` / `maxHeartRate` → lowest / highest HR; `totalSteps` → steps; `averageSpo2Value` → SpO2; `allDayStress.aggregatorList` with type `TOTAL` → stress level; `bodyBattery.bodyBatteryStatList` with types `HIGHEST` / `LOWEST` → body battery extrema. The rolling `restingHeartRate` field is ignored. |
| `*_sleepData.json` | Deep, light and REM seconds from `deepSleepSeconds`, `lightSleepSeconds`, `remSleepSeconds`; total sleep is their sum, excluding awake time. `awakeSleepSeconds` supplies awake time when total sleep is positive; `averageRespiration` supplies respiration. An unconfirmed night with no stages supplies no sleep duration; it may still supply respiration. |
| `MetricsMaxMetData_*.json` | `vo2MaxValue` for sport `RUNNING` / `CYCLING` → running / cycling VO2max. Other or missing sports are ignored; `updateTimestamp` selects the latest record. |
| `*_userBioMetrics.json` | `weight.weight`, converted from grams to kilograms, under `metaData.calendarDate`, a local timestamp whose date part is the day. Other body measurements are ignored. |
| intervals.icu wellness `.json` | A bare nonempty list from the [wellness API](https://intervals.icu/api-docs.html), or the delivery envelope below. Source `intervals-icu`; origin is unknown for a bare list and field-specific for an envelope. |

Garmin's daily resting HR is its lowest 30-minute average over a 24-hour period;
fitdocs imports the daily `currentDayRestingHeartRate`, not the separate rolling
average. See [Garmin's definition](https://support.garmin.com/en-AU/?faq=F8YKCB4CJd5PG0DR9ICV3A).
Apple's resting HR is a sedentary estimate from background readings, using motion
data to identify inactive periods; it can be revised during the day. The [Apple
Health import](#apple-health) applies this definition directly; a relay can also
supply Apple measurements. See [Apple's measurement
description](https://support.apple.com/en-mide/120277)
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

## Apple Health

### How to export

On your iPhone, open Health, tap your profile picture, then Export All Health Data →
Export. Put `export.zip` into the configured inbox and run `fitdocs sync`.
See [Apple’s export
instructions](https://support.apple.com/guide/iphone/share-your-health-data-iph5ede58c3d/ios).
A bare main `export.xml` is also accepted; the wellness suffixes are `.zip` and `.xml`.
Recognition uses export contents, so renaming either file is fine. The ZIP must
contain exactly one main export document; its clinical-document companion is not an
import.

### Types and definitions

| Apple type | Metrics | Writers | Day rule | Daily rule |
| --- | --- | --- | --- | --- |
| `HKCategoryTypeIdentifierSleepAnalysis` | `sleep_s`, `sleep_deep_s`, `sleep_light_s`, `sleep_rem_s`, `sleep_awake_s` | Apple Watch, iPhone | wake date of each segment’s end ([wellness day](#wellness-day)) | total asleep; stages only for a staged night |
| `HKQuantityTypeIdentifierHeartRateVariabilitySDNN` | `hrv_sdnn_ms` | Apple Watch | night of the reading ([wellness day](#wellness-day)) | mean of readings asleep, rounded to 0.1 |
| `HKQuantityTypeIdentifierRespiratoryRate` | `respiration_brpm` | Apple Watch | night of the reading ([wellness day](#wellness-day)) | mean of readings asleep, rounded to 0.1 |
| `HKQuantityTypeIdentifierOxygenSaturation` | `spo2_pct` | Apple Watch | night of the reading ([wellness day](#wellness-day)) | mean of readings asleep, rounded to 0.1 |
| `HKQuantityTypeIdentifierRestingHeartRate` | `resting_hr_bpm` | Apple Watch | local start date ([wellness day](#wellness-day)) | latest end, then latest creation |
| `HKQuantityTypeIdentifierVO2Max` | `vo2max_ml_per_kg_min` | Apple Watch | local start date ([wellness day](#wellness-day)) | latest end, then latest creation |
| `HKQuantityTypeIdentifierStepCount` | `steps` | Apple Watch, iPhone | local start date ([wellness day](#wellness-day)) | largest single-source day total |
| `HKQuantityTypeIdentifierBodyMass` | `weight_kg` | Apple Watch, iPhone, other | local start date ([wellness day](#wellness-day)) | latest start, then latest creation; rounded to 0.01 kg |

The writers and daily rules below explain the table; the day links use the page’s
shared rule.

| Metric | Apple definition |
| --- | --- |
| `resting_hr_bpm` | Apple’s sedentary estimate from background heart-rate readings, in bpm |
| `hrv_sdnn_ms` | SDNN: standard deviation of normal-to-normal heartbeat intervals, in ms; not rMSSD |
| `respiration_brpm` | Breathing rate, in breaths per minute |
| `spo2_pct` | Blood-oxygen saturation; the exported fraction is converted to percent |
| `vo2max_ml_per_kg_min` | Estimated maximum oxygen consumption, in millilitres per kilogram per minute |
| `steps` | Number of steps |
| `weight_kg` | Body mass, converted to kilograms |
| `sleep_s` | Total asleep time: core, deep, REM and unspecified asleep; excludes awake and in-bed time |
| `sleep_deep_s` | Time in Apple’s deep sleep stage |
| `sleep_light_s` | Time in Apple’s core sleep stage, mapped to light sleep |
| `sleep_rem_s` | Time in Apple’s REM sleep stage |
| `sleep_awake_s` | Time awake within the staged night |

These definitions follow Apple’s HealthKit references for [resting heart
rate](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/restingheartrate),
[SDNN](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/heartratevariabilitysdnn),
[respiratory
rate](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/respiratoryrate),
[oxygen
saturation](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/oxygensaturation),
[VO2max](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/vo2max),
[steps](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/stepcount),
[body
mass](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/bodymass)
and
[sleep
states](https://developer.apple.com/documentation/healthkit/hkcategoryvaluesleepanalysis).

### Writers and daily rules

A writing source is classified from all its device evidence: manufacturer Apple Inc.
and model Watch wins over model iPhone; otherwise it is other. Records without a
device inherit their writing source’s class.

A third-party watch app that names an Apple Watch as its device can therefore be
misclassified as Apple Watch.

Other apps’ values, except body weight, are excluded; import those platforms’ own
sources instead. Writers are selected from export content, independently of record
order, and different writers’ values are never added together.

Resting HR and VO2max use the final estimate because Apple can revise its estimate
during the day. Equal end times use latest creation; remaining ties use record
content.

HRV, respiration and SpO2 average only readings whose end lies in Apple Watch asleep
time, start inclusive and end exclusive, rounded to one decimal place. This keeps
each day’s measure tied to sleep rather than daytime activity. No watch sleep, or no
qualifying reading, means no value; a night without the watch supplies no HRV.

Steps take the largest single-writer daily sum to avoid counting the phone and watch
together. Weight takes the latest measurement across every writer, including manual
entries and scales, because the last measurement is the daily observation; creation
time and then content break ties. Weight is converted to kilograms and rounded to two
decimal places.

Every imported value has source `apple-health` and origin `apple`, except weight,
whose origin is unknown. SDNN is never converted to rMSSD.

### Sleep and naps

Sleep uses Apple Watch records if that night contains any watch asleep time,
otherwise iPhone records; they are never combined within a night.

Overlapping segments count once, with priority deep, REM, core, awake, then
unspecified asleep. Core maps to light; deprecated asleep maps to unspecified asleep.
In-bed time contributes nothing.

Total sleep includes core, deep, REM and unspecified asleep, excluding awake. Only a
night with core, deep or REM time supplies stage and awake values; an older unstaged
night supplies total sleep only. A zero total supplies no sleep values.

Naps count toward the same night under the linked wellness day rule; this is not
restricted to one main sleep session.

### Extract and corrections

The archive keeps a deterministic gzip-compressed UTF-8 JSON Lines extract at
`wellness-archive/apple-health/<sha256>.jsonl.gz`, named by the original export’s
SHA-256.

Its header records the original SHA-256, byte size and stated export date. Each
supported raw record retains type, writing source, source version, device, unit,
creation/start/end times, value and metadata; the device description’s memory address
is removed. A trailer records record counts and correction counts.

It contains no personal profile (date of birth, biological sex, blood type or skin
type), workouts, routes, clinical records, ECGs, audiograms or unsupported record
types. It contains no run date, original filename/path or machine-specific value.

Read it without fitdocs using `gzip -dc
wellness-archive/apple-health/<sha256>.jsonl.gz`; there is one JSON record per line.

Corrections remove a malformed document-type declaration, remove illegal XML control
characters, and keep the first occurrence of a duplicate WorkoutStatistics attribute.
Removing a control character changes the text it was in. Each correction kind is
counted in the extract; the original export is never modified. Other malformed XML
fails the whole import with a line number and leaves the series unchanged.

### Later exports and the original

The latest export date replaces the earlier export entirely, including any day the
later export no longer holds. Every Apple Health export in the archive is assumed to
belong to the same athlete.

Superseded extracts remain unchanged in the archive and are listed as superseded in
the manifest. An older export is archived but does not replace a newer one. Zip and
bare XML copies use a deterministic archive-reference tie-break.

The series is rebuilt from the extract alone; the original is never needed again. The
original follows inbox disposition: left in place by default, or moved to
processed_dir, never deleted by fitdocs. Move it out of an iCloud inbox yourself to
avoid re-hashing it on every drain.

### Time, memory and exclusions

Allow about 10–20 seconds per GB of main export.xml on a recent computer, plus about
one second per GB for each of two framework hashes. Large imports can take minutes. A
terminal reports the percentage of the main XML document read, at most once per whole
percent.

XML is streamed without unpacking to disk; import memory stays flat with XML size,
under 100 MiB. Daily reduction additionally retains sleep segments and spot readings:
tens of MB for a decade, depending on history.

Import and rebuild are offline. No real export or extract belongs in the fitdocs
repository.

Workouts continue to arrive as `.fit` files through HealthFit. Heart rate, walking
heart rate, wrist temperature, nutrition, clinical records, ECGs, audiograms, Sleep
Score, Apple’s rMSSD type and third-party file exporters are not imported.

## Metrics

Ranges are inclusive acceptance limits for recorded values, not clinical
reference ranges. Unit tokens: `bpm` = beats/minute; `ms` = milliseconds;
`s` = seconds; `brpm` = breaths/minute; `pct` = percent; `kg` = kilograms;
`ml_per_kg_min` = millilitres per kilogram per minute; `—` = unitless.
The supported-file definitions and [Apple Health definitions](#apple-health) specify
which source provides each metric.

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

This is the file contract for wellness-pull. A manual
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
matching `[a-z0-9]+(-[a-z0-9]+)*`, such as `garmin` or `apple`. The pull
obtains these from the athlete's `*_wellness_keys`; unnamed fields have no origin.
The private and ICU namespaces do not name source platforms.
A known platform's wellness-download switch must be boolean true when present;
an absent switch keeps list-based compatibility.
The Garmin health switch does not enable wellness imports.
Only enabled platform lists count toward ambiguity; a field claimed by multiple
enabled platforms has no platform attribution.
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
within each kind. Today that puts `garmin-export` before `apple-health` before
`intervals-icu`.
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
writes. Only registered source ids are accepted: `garmin-export`, `apple-health` and
`intervals-icu`. Changed precedence rebuilds the series on the next drain or `fitdocs
regen`.
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

Handled JSON inputs live at `wellness-archive/<format>/<original-sha256>.json`:
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
over `wellness_daily`, for example) owes Garmin attribution, as the
[recovery page](recovery.md#garmin-attribution) gives it.

Build or refresh the index, inspect the schema, then query canonical values or
one source explicitly:

```bash
fitdocs index
fitdocs query --schema
fitdocs query "SELECT day, value, source, origin FROM wellness_daily WHERE metric = 'resting_hr_bpm' AND canonical ORDER BY day" --format csv
fitdocs query "SELECT day, value FROM wellness_daily WHERE metric = 'hrv_rmssd_ms' AND source = 'intervals-icu' ORDER BY day"
```

Series files stay the source for wellness consumers; deleting the index costs
only a rebuild. The file import itself computes no baselines, scores or
benchmarks; the [recovery page](recovery.md) and `fitdocs derive-benchmarks` do.
