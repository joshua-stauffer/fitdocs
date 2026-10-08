## Before you start

`fitdocs query` reads a local analytics index. Build it with `fitdocs index`
before the first query. Run `fitdocs index --rebuild` to replace an index that
needs a fresh build. A query never builds or refreshes the index for you.

```bash
fitdocs index
fitdocs index --rebuild
```

## Where the index lives

fitdocs keeps one index directory per data root, outside that root. It chooses
the base directory in this order: `FITDOCS_INDEX_DIR`, then
`$XDG_CACHE_HOME/fitdocs/index`, then `~/.cache/fitdocs/index`. After the index
is built, `fitdocs query --schema` and `fitdocs index` print the index file
path.

```bash
fitdocs query --schema
fitdocs index
```

## Running a query

Give `fitdocs query` one SQL statement as an argument, pass `--file PATH`, or
use `-` to read the statement from standard input. For example:

```bash
fitdocs query "SELECT start_utc, distance_m FROM activities ORDER BY start_utc DESC LIMIT 5"
fitdocs query --file weekly.sql
cat weekly.sql | fitdocs query -
```

Use `--format table`, `--format csv`, or `--format json` to choose an output
format. Without `--format`, fitdocs prints `table` when standard output is a
terminal and `csv` when output is piped or redirected. In table output, SQL
`NULL` appears as `NULL`. In CSV it is an empty unquoted field; an empty string
is `""`. In JSON, SQL `NULL` is `null` and an empty string is `""`.

The default row limit is **1,000 rows**. Set another positive limit with
`--max-rows`; when more rows are available, fitdocs prints the first rows and
reports the truncation on standard error. Table output adds a closing notice,
and JSON sets `truncated` to `true`. A truncated result still exits 0. The
default time limit is **30 seconds**; set another positive number of seconds
with `--timeout`.

Successful queries and schema views exit 0. Query failures, sandbox refusals,
timeouts, and an unavailable or busy index exit 1. Invalid input forms or
option values exit 2. Results go to standard output; notices and errors go to
standard error. If the index is behind the data root, fitdocs prints a
freshness notice and tells you to run `fitdocs index` to bring it up to date.

## The schema view

Run `fitdocs query --schema` to see the database path, schema version, table
and row counts, column types and descriptions, and freshness information. Use
`--format json` for a JSON report; schema output does not support CSV. The page
below carries the complete schema reference generated from a fresh schema-only
index.

```bash
fitdocs query --schema
fitdocs query --schema --format json
```

## The sandbox

The command accepts one query or `EXPLAIN`. It refuses other statement kinds,
including writes, `ATTACH`, `COPY`, `INSTALL`, `LOAD`, and setting changes. It
also refuses file and address access outside the index, network access, and
extensions. The index opens read-only, and the sandbox settings are locked
with external access and extension auto-install and auto-load turned off.

Read-only access alone is not the sandbox: it does not prevent SQL from trying
to read another file or contact a network address. fitdocs's query sandbox
guards against accidental or injected SQL through statement checks and locked
DuckDB settings. It is not a boundary against a local user who can open the
index with another program. DuckDB also says its security settings are not a
substitute for proper sandboxing; see [Securing DuckDB](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview).

Each query has a 30-second default time limit, a 1 GB memory limit, and up to
2 DuckDB threads. When DuckDB needs to spill, its temporary files go under a
per-process `query-spill-<pid>/` directory inside the index directory, with a
4 GB size limit. DuckDB removes the directory when the query closes; a later
query removes a stale directory left by a process that ended unexpectedly.

## Opening the index from another DuckDB client

Using an external DuckDB client bypasses fitdocs's query sandbox and is not
covered by fitdocs's no-network guarantee. Configure every client as read-only, turn
off automatic extension installation and loading, and give each client its own
temporary spill directory. For the DuckDB CLI, pass settings with `-cmd`:

```bash
duckdb -readonly -cmd "SET autoinstall_known_extensions = false; SET autoload_known_extensions = false; SET temp_directory = '/path/to/your-client-temp';" /path/to/index.duckdb
```

The equivalent Python connection is:

```python
import duckdb

connection = duckdb.connect(
    "/path/to/index.duckdb",
    read_only=True,
    config={
        "autoinstall_known_extensions": "false",
        "autoload_known_extensions": "false",
        "temp_directory": "/path/to/your-client-temp",
    },
)
try:
    print(connection.sql("SELECT start_utc, distance_m FROM activities LIMIT 5").fetchall())
finally:
    connection.close()
```

Keep the client open only while you need it. An external connection holds the
index open, so every fitdocs refresh reports the index busy until that client
closes. Close it before running `fitdocs index`.

## Schema reference

<!-- schema-reference:start -->
### `activities`
one row per page whose files compose.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| start_utc | TIMESTAMP | UTC | Activity start instant in UTC. |
| sport | VARCHAR |  | as fitdocs determines it |
| sub_sport | VARCHAR |  | raw FIT value |
| modality | VARCHAR |  | Modality as fitdocs determines it. |
| indoor | BOOLEAN |  | Indoor flag as fitdocs determines it. |
| sample_count | INTEGER |  | Number of activity samples. |
| moving_time_s | DOUBLE | seconds | Moving time in seconds. |
| elapsed_time_s | DOUBLE | seconds | Elapsed time in seconds. |
| distance_m | DOUBLE | metres | Distance in metres. |
| avg_speed_mps | DOUBLE | metres per second | Average speed in metres per second. |
| max_speed_mps | DOUBLE | metres per second | Maximum speed in metres per second. |
| avg_pace_s_per_km | DOUBLE | seconds per kilometre | Average pace in seconds per kilometre. |
| avg_heart_rate_bpm | DOUBLE | beats per minute | Average heart rate in beats per minute. |
| max_heart_rate_bpm | DOUBLE | beats per minute | Maximum heart rate in beats per minute. |
| avg_power_w | DOUBLE | watts | Average power in watts. |
| max_power_w | DOUBLE | watts | Maximum power in watts. |
| avg_cadence_rpm | DOUBLE | revolutions per minute | Average cadence in revolutions per minute. |
| max_cadence_rpm | DOUBLE | revolutions per minute | Maximum cadence in revolutions per minute. |
| normalized_power_w | DOUBLE | watts | Normalized power in watts. |
| intensity_factor | DOUBLE |  | Intensity factor. |
| variability_index | DOUBLE |  | Variability index. |
| efficiency_factor | DOUBLE |  | Efficiency factor. |
| decoupling_pct | DOUBLE | percent | Decoupling in percent. |
| elevation_gain_m | DOUBLE | metres | Elevation gain in metres. |
| elevation_loss_m | DOUBLE | metres | Elevation loss in metres. |
| min_altitude_m | DOUBLE | metres | Minimum altitude in metres. |
| max_altitude_m | DOUBLE | metres | Maximum altitude in metres. |
| min_temperature_c | DOUBLE | degrees Celsius | Minimum temperature in degrees Celsius. |
| max_temperature_c | DOUBLE | degrees Celsius | Maximum temperature in degrees Celsius. |
| avg_temperature_c | DOUBLE | degrees Celsius | Average temperature in degrees Celsius. |
| trimp | DOUBLE |  | Training impulse. |
| trimp_weighting | VARCHAR |  | Training impulse weighting selection. |
| power_tss | DOUBLE |  | Power-based training stress score. |
| calories_kcal | INTEGER | kilocalories | Calories in kilocalories. |
| athlete_fingerprint | VARCHAR |  | SHA-256 of the athlete inputs the metrics were computed under |

### `benchmark_periods`
One row per period during which one benchmark entry is in force for its kind and discipline. Equals the athlete profile's own in-force rule (the rule the training-load pass applies before its cross-discipline borrowing), for the inputs as of the last refresh. Per discipline as recorded: no cross-discipline borrowing.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| kind | VARCHAR |  | Benchmark kind in force. |
| discipline | VARCHAR |  | Recorded sport scope; NULL for athlete-wide benchmarks. |
| starts_on | DATE |  | First calendar day the entry is in force. |
| ends_before | DATE |  | First calendar day the entry is no longer in force; NULL while still in force. |
| value | DOUBLE |  | Recorded value in the unit named by unit; never converted. |
| unit | VARCHAR |  | Unit token for the benchmark kind. |
| measured_on | DATE |  | Calendar day the in-force entry was measured. |
| retroactive | BOOLEAN |  | Whether this period precedes the entry's measured day. |

### `benchmarks`
One row per benchmark entry in athlete.toml. Equals the athlete profile's own reading of athlete.toml (the reading fitdocs derive-benchmarks and the training-load pass use), for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| kind | VARCHAR |  | Benchmark kind recorded in athlete.toml. |
| discipline | VARCHAR |  | Sport scope; NULL for athlete-wide benchmarks. |
| value | DOUBLE |  | Recorded value in the unit named by unit; never converted. |
| unit | VARCHAR |  | Unit token for the benchmark kind. |
| measured_on | DATE |  | Calendar day the benchmark was measured. |
| applies_from | DATE |  | Calendar day the entry applies from; NULL when not recorded. |
| source_kind | VARCHAR |  | Whether the source is derived or measured; NULL when absent. |
| source_method | VARCHAR |  | Derivation method; NULL when not recorded. |
| source_page | VARCHAR |  | Data-root-relative page used to derive the entry; NULL when not recorded. |
| source_citation | VARCHAR |  | Citation key for a derived entry; NULL when not recorded. |

### `blocks`
One row per plan source the plan pass discovers. Equals the plan pass's resolution (`fitdocs plan`) on `resolved_on`, for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| block_id | VARCHAR |  | The plan source file's stem. |
| source_path | VARCHAR |  | The plan source path as the plan pass reports it. |
| valid | BOOLEAN |  | Whether the source parsed as a valid block. |
| problems | INTEGER |  | Number of problems the plan pass reports. |
| title | VARCHAR |  | Block title; NULL when the source is invalid. |
| goal | VARCHAR |  | Block goal; NULL when the source is invalid. |
| starts_on | DATE |  | First day; NULL when the source is invalid. |
| ends_on | DATE |  | Last day; NULL when the source is invalid. |
| mesocycle_days | INTEGER |  | Nominal mesocycle length in days; NULL when invalid. |
| resolved_on | DATE |  | Date used to resolve the plan. |

### `channel_sources`
one row per channel per supplying file.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| channel | VARCHAR |  | activity-model channel name |
| source_sha256 | VARCHAR |  | SHA-256 digest of the supplying file. |
| role | VARCHAR |  | base or extra |

### `daily_load`
One row per day of each methodology's series, from its first to its last contributing day. Equals fitdocs history --methodology <methodology>'s computation for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| methodology | VARCHAR |  | Calculator id. |
| day | DATE |  | Calendar day. |
| recorded_load | DOUBLE |  | Sum of the day's recorded loads in dimensionless load points; 0 on a day with no load, as fitdocs history counts it. |
| pages | INTEGER |  | Pages counted that day. |
| pages_with_load | INTEGER |  | Pages carrying a load that day. |
| fitness | DOUBLE |  | Fitness on the daily-average load scale; NULL on a suppressed day. |
| fatigue | DOUBLE |  | Fatigue on the daily-average load scale; NULL on a suppressed day. |
| form | DOUBLE |  | Fitness minus fatigue on the daily-average load scale; NULL on a suppressed day. |
| suppressed | BOOLEAN |  | TRUE when the day's ISO week is suppressed for low coverage. |

### `laps`
one row per base lap, in recorded order.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| lap_index | INTEGER |  | Zero-based lap position in recorded order. |
| start_utc | TIMESTAMP | UTC | Lap start instant in UTC; NULL when absent. |
| total_elapsed_time_s | DOUBLE | seconds | Lap elapsed time in seconds. |
| total_timer_time_s | DOUBLE | seconds | Lap timer time in seconds. |
| total_distance_m | DOUBLE | metres | Lap distance in metres. |
| avg_heart_rate_bpm | INTEGER | beats per minute | Average heart rate in beats per minute. |
| max_heart_rate_bpm | INTEGER | beats per minute | Maximum heart rate in beats per minute. |
| avg_power_w | INTEGER | watts | Average power in watts. |
| max_power_w | INTEGER | watts | Maximum power in watts. |
| avg_cadence_rpm | DOUBLE | revolutions per minute | Average cadence in revolutions per minute. |
| avg_speed_mps | DOUBLE | metres per second | Average speed in metres per second. |
| max_speed_mps | DOUBLE | metres per second | Maximum speed in metres per second. |
| total_ascent_m | DOUBLE | metres | Total ascent in metres. |
| total_descent_m | DOUBLE | metres | Total descent in metres. |
| start_sample | INTEGER |  | inclusive record indices; NULL when unmatched |
| end_sample | INTEGER |  | inclusive record indices; NULL when unmatched |

### `load_series`
One row per training-load methodology some workout page records a load under: the terms its fitness/fatigue/form series was computed with. Equals fitdocs history --methodology <methodology>'s computation for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| methodology | VARCHAR |  | Calculator id. |
| history_default | BOOLEAN |  | TRUE for the methodology fitdocs history shows without --methodology; FALSE for every row when it would refuse to choose. |
| default_selection | VARCHAR |  | configured or inferred for the default; NULL otherwise. |
| series_start | DATE |  | First day of the series. |
| series_end | DATE |  | Last day of the series. |
| tau_fitness_days | DOUBLE |  | Fitness time constant in days. |
| tau_fatigue_days | DOUBLE |  | Fatigue time constant in days. |
| k_fitness | DOUBLE |  | Fitness weighting, dimensionless. |
| k_fatigue | DOUBLE |  | Fatigue weighting, dimensionless. |
| constants_provenance | VARCHAR |  | seeds for fitdocs's shipped starting values or configured. |
| coverage_threshold | DOUBLE |  | Fraction from 0 to 1 below which a week is suppressed. |

### `loads`
one row per channel a computed load result reports.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| calculator_id | VARCHAR |  | Load calculator identifier |
| channel | VARCHAR |  | `power`, `heart_rate` or `pace` for the built-in calculator |
| selected | BOOLEAN |  | Whether this channel is the selected load basis |
| load_value | DOUBLE |  | dimensionless; NULL when the result records the channel as not computable |

### `mean_max`
One row per duration of the best-effort set that at least one of power, speed and heart rate supports on this page's composed activity. A best effort is the highest average over a window of continuous recording; a window never spans a step longer than the maximum step between recorded values (see the records in fitdocs.metrics.mean_max_sources). Follows the page's rendering, like activities.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| duration_s | INTEGER | seconds | Window length in seconds. |
| power_w | DOUBLE | watts | Best average power in watts; NULL when no window of this duration is allowed. |
| power_start_s | DOUBLE | seconds | Seconds since the activity's start (records.elapsed_s scale) at which the best power window begins; NULL with power_w. |
| speed_mps | DOUBLE | metres per second | Best average speed in metres per second; NULL when no window of this duration is allowed. |
| speed_start_s | DOUBLE | seconds | Seconds since the activity's start (records.elapsed_s scale) at which the best speed window begins; NULL with speed_mps. |
| heart_rate_bpm | DOUBLE | beats per minute | Best average heart rate in beats per minute; NULL when no window of this duration is allowed. |
| heart_rate_start_s | DOUBLE | seconds | Seconds since the activity's start (records.elapsed_s scale) at which the best heart-rate window begins; NULL with heart_rate_bpm. |

### `mesocycles`
One row per mesocycle of a valid block, with its actual-load picture. Equals the plan pass's resolution (`fitdocs plan`) for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| block_id | VARCHAR |  | Identity of the plan block. |
| mesocycle | INTEGER |  | Mesocycle number, beginning at one. |
| starts_on | DATE |  | First day in the mesocycle. |
| ends_on | DATE |  | Last day in the mesocycle. |
| nominal_days | INTEGER |  | Nominal mesocycle length in days. |
| days | INTEGER |  | Actual inclusive mesocycle length in days. |
| target_load | DOUBLE |  | Target load in dimensionless load points; NULL when unstated. |
| focus | VARCHAR |  | Mesocycle focus; NULL when unstated. |
| load_methodology | VARCHAR |  | Methodology used for actual load; NULL when unavailable. |
| actual_load | DOUBLE |  | Actual load in dimensionless load points; NULL when absent. |
| actual_load_lower_bound | BOOLEAN |  | Whether actual load is a lower bound. |
| actual_load_of_target_pct | INTEGER | percent | Actual load as a percent of target; NULL when unavailable. |
| pages | INTEGER |  | Workout pages in the mesocycle window. |
| scored_pages | INTEGER |  | Pages counted with a load. |
| unscored_pages | INTEGER |  | Counted pages without a load. |
| excluded_pages | INTEGER |  | Pages excluded under another methodology. |
| unplanned_pages | INTEGER |  | Pages in the window no planned workout claims. |

### `page_sources`
one row per listed file.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| position | INTEGER |  | 1-based in listed order, ascending rank, base last |
| ref | VARCHAR |  | archive reference as listed |
| sha256 | VARCHAR |  | content hash the reference names; NULL when the reference is not an archive reference |
| role | VARCHAR |  | `base` or `extra` |

### `pages`
one row per workout page; the page's frontmatter as recorded.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| path | VARCHAR |  | data-root-relative POSIX path |
| title | VARCHAR |  | Workout page title |
| doc_version | INTEGER |  | document-format version |
| uuid | VARCHAR |  | session UUID; NULL when no file recorded one |
| date | DATE |  | document date, local |
| start_time_local | TIMESTAMP | local | local wall-clock start |
| sport | VARCHAR |  | Document sport label |
| modality | VARCHAR |  | Document movement modality |
| indoor | BOOLEAN |  | TRUE when the page records an indoor flag; NULL otherwise, because the key is written only when true |
| source_kind | VARCHAR |  | Base source kind |
| source_elapsed_s | DOUBLE | seconds | Elapsed source time in seconds |
| source_distance_m | DOUBLE | metres | Source distance in metres |
| source_device | VARCHAR |  | device digest |
| load_status | VARCHAR |  | `computed`, `unsupported`, `not_computed` or `unreadable` |
| load_value | DOUBLE |  | the selected load as frontmatter records it; dimensionless load points |
| load_methodology | VARCHAR |  | calculator id |
| load_basis | VARCHAR |  | the selected channel |
| effort | VARCHAR |  | `race`, `test` or `hard`; NULL when there is no valid tag |
| effort_distance_m | DOUBLE | metres | Effort distance in metres |
| effort_time_s | DOUBLE | seconds | Effort time in seconds |
| effort_event | VARCHAR |  | the event label as recorded |
| effort_invalid | BOOLEAN |  | TRUE when an effort key is present but the tag is invalid by `fitdocs check`'s rule |

### `planned_workout_pages`
One row per workout page a planned workout claims, and per page an override names that does not exist. Equals the plan pass's resolution (`fitdocs plan`) for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| block_id | VARCHAR |  | Identity of the plan block. |
| workout_id | VARCHAR |  | Identity of the planned workout. |
| stem | VARCHAR |  | Claimed workout page stem. |
| path | VARCHAR |  | Data-root-relative page path; NULL when not found. |
| page_key | VARCHAR |  | Index key; NULL when the page is not held. |
| found | BOOLEAN |  | Whether the named page exists. |

### `planned_workouts`
One row per planned workout in a valid block's current plan, with its resolution. Equals the plan pass's resolution (`fitdocs plan`) for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| block_id | VARCHAR |  | Identity of the plan block. |
| workout_id | VARCHAR |  | Identity of the planned workout. |
| mesocycle | INTEGER |  | Containing mesocycle number. |
| day | DATE |  | Planned calendar day. |
| sport | VARCHAR |  | Planned sport. |
| modality | VARCHAR |  | Planned modality; NULL unless stated. |
| indoor | BOOLEAN |  | Planned indoor flag; NULL unless stated. |
| title | VARCHAR |  | Planned workout title. |
| summary | VARCHAR |  | Planned workout summary. |
| state | VARCHAR |  | Resolution state: matched, overridden, skipped, not logged or upcoming. |
| confidence | VARCHAR |  | Match confidence; NULL unless matched. |
| override_date | DATE |  | Date of the deciding override; NULL unless overridden. |
| claimed_pages | INTEGER |  | Number of workout pages claimed. |
| missing_pages | INTEGER |  | Number of named pages not found. |

### `quality_flags`
one row per flag a computed load result records.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| flag | VARCHAR |  | flag key |
| verdict | VARCHAR |  | `detected`, `not-detected` or `not-assessed` |

### `records`
one row per sample of the composed activity.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| sample_index | INTEGER |  | 0-based recorded order |
| time_utc | TIMESTAMP | UTC | Sample instant in UTC. |
| elapsed_s | DOUBLE | seconds | seconds since the activity's start; may be negative |
| heart_rate_bpm | INTEGER | beats per minute | Heart rate in beats per minute. |
| power_w | INTEGER | watts | Power in watts. |
| cadence_rpm | DOUBLE | revolutions per minute | Cadence in revolutions per minute. |
| speed_mps | DOUBLE | metres per second | Speed in metres per second. |
| distance_m | DOUBLE | metres | Distance in metres. |
| altitude_m | DOUBLE | metres | Altitude in metres. |
| latitude_deg | DOUBLE | degrees | Latitude in degrees. |
| longitude_deg | DOUBLE | degrees | Longitude in degrees. |
| temperature_c | DOUBLE | degrees Celsius | Temperature in degrees Celsius. |
| stance_time_ms | DOUBLE | milliseconds | Stance time in milliseconds. |
| stance_time_balance_pct | DOUBLE | percent | Stance time balance in percent. |
| vertical_oscillation_mm | DOUBLE | millimetres | Vertical oscillation in millimetres. |
| vertical_oscillation_balance_pct | DOUBLE | percent | Vertical oscillation balance in percent. |
| vertical_ratio_pct | DOUBLE | percent | Vertical ratio in percent. |
| step_length_mm | DOUBLE | millimetres | Step length in millimetres. |
| leg_spring_stiffness_kn_m | DOUBLE | kilonewtons per metre | Leg spring stiffness in kilonewtons per metre. |
| leg_spring_stiffness_balance_pct | DOUBLE | percent | Leg spring stiffness balance in percent. |
| form_power_w | DOUBLE | watts | Form power in watts. |
| air_power_w | DOUBLE | watts | Air power in watts. |
| impact_bw | DOUBLE | body weights | Impact in body weights. |
| impact_loading_rate_balance_pct | DOUBLE | percent | Impact loading rate balance in percent. |

### `strength_sets`
one row per base set, in recorded order.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| set_index | INTEGER |  | Zero-based set position in recorded order. |
| set_type | VARCHAR |  | Recorded set type. |
| start_utc | TIMESTAMP | UTC | Set start instant in UTC; NULL when absent. |
| duration_s | DOUBLE | seconds | Set duration in seconds. |
| repetitions | INTEGER |  | Recorded repetition count. |
| weight_kg | DOUBLE | kilograms | 0 means bodyweight, a real zero in kilograms |
| category | VARCHAR |  | Recorded exercise category. |
| exercise_name | VARCHAR |  | Resolved exercise name. |

### `unplanned_pages`
One row per workout page in a mesocycle's window that no planned workout of the block claims. Equals the plan pass's resolution (`fitdocs plan`) for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| block_id | VARCHAR |  | Identity of the plan block. |
| mesocycle | INTEGER |  | Containing mesocycle number. |
| stem | VARCHAR |  | Unplanned workout page stem. |
| path | VARCHAR |  | Data-root-relative workout page path. |
| page_key | VARCHAR |  | Index key; NULL when the page is not held. |

### `weekly_load`
One row per ISO week of each methodology's series. Equals fitdocs history --methodology <methodology>'s weekly table, unrounded, for the inputs as of the last refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| methodology | VARCHAR |  | Calculator id. |
| iso_year | INTEGER |  | ISO week-numbering year. |
| iso_week | INTEGER |  | ISO week number. |
| week_start | DATE |  | Monday of the ISO week. |
| days_in_series | INTEGER |  | Days of the week in the series. |
| total_load | DOUBLE |  | Total dimensionless load points in the week. |
| sessions | INTEGER |  | Pages carrying a load in the week. |
| pages | INTEGER |  | Pages counted in the week. |
| pages_with_load | INTEGER |  | Pages carrying a load in the week. |
| fitness | DOUBLE |  | Fitness on the daily-average load scale at the week's last day; NULL when suppressed. |
| fatigue | DOUBLE |  | Fatigue on the daily-average load scale at the week's last day; NULL when suppressed. |
| form | DOUBLE |  | Form on the daily-average load scale at the week's last day; NULL when suppressed. |
| suppressed | BOOLEAN |  | TRUE when the week is suppressed for low coverage. |

### `zone_times`
one row per channel and zone with computed times.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | Key of the workout page: the SHA-256 (64 hex) of the page's base file, the last file its sources list. |
| channel | VARCHAR |  | heart_rate, power or pace |
| zone | INTEGER |  | 1-based; zone 1 is below the first divider |
| lower_bound | DOUBLE |  | in bound_unit; NULL for an open end |
| upper_bound | DOUBLE |  | in bound_unit; NULL for an open end |
| bound_unit | VARCHAR |  | bpm, w or s_per_km |
| time_s | DOUBLE | seconds | Time credited to the zone in seconds. |

### `index_meta`
Metadata recorded by the most recent index refresh.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| schema_version | INTEGER |  | Schema version of this index. |
| fitdocs_version | VARCHAR |  | Version of fitdocs that last wrote the index; NULL when not installed as a distribution. |
| duckdb_version | VARCHAR |  | Version of DuckDB that wrote the index. |
| data_root | VARCHAR |  | Resolved absolute path of the data root. |
| athlete_fingerprint | VARCHAR |  | SHA-256 fingerprint of athlete inputs current at the last refresh. |

### `index_pages`
Document and computed-value bookkeeping for each indexed workout page.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| page_key | VARCHAR |  | SHA-256 key of the page's base file. |
| path | VARCHAR |  | Data-root-relative POSIX path of the workout page. |
| document_fingerprint | VARCHAR |  | Fingerprint of the page document. |
| render_fingerprint | VARCHAR |  | Fingerprint of the rendering at the last computed attempt; NULL when none. |
| computed_state | VARCHAR |  | Computed state: computed, source_missing, source_unreadable or source_undecodable. |

### `index_producers`
Producer registrations and corpus fingerprints recorded by the index.

| Column | Type | Unit | Description |
| --- | --- | --- | --- |
| producer | VARCHAR |  | Registered producer name. |
| kind | VARCHAR |  | Producer scope: document, computed or corpus. |
| tables | VARCHAR[] |  | Names of tables declared by the producer. |
| fingerprint | VARCHAR |  | Combined corpus fingerprint; NULL for per-page producers. |
<!-- schema-reference:end -->
