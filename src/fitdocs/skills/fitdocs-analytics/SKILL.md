---
name: fitdocs-analytics
description: Use when an athlete asks for a count, total, average, distribution, or trend about their training and an indexed answer can support it.
license: MIT
compatibility: Requires the fitdocs command to be installed and a built analytics index.
metadata:
  version: 0.1.0
---

# Query the fitdocs analytics index

## When this applies

Use this skill when an athlete asks a question that needs training history
summarized across activities, such as weekly volume, time in zones, training
load, or races and tests. The index is a local, read-only view built from the
athlete's workout documents. It helps answer statistical questions without
opening each document one by one.

## Check the index first

Before writing SQL, run `fitdocs query --schema`. It reports the available
tables and columns, their types and descriptions, row counts, and whether the
index is behind the data. Read the table and column descriptions instead of
guessing names or meanings. If the index is not built or is behind, run
`fitdocs index`; it builds or refreshes the index from the current documents.
Then read the schema again before querying.

## Ask with fitdocs query

Pass one SQL statement as an argument, use `--file` to read a SQL file, or use
`-` to read it from standard input. Use `--format table`, `--format csv`, or
`--format json`; the default is a table in a terminal and CSV when output is
redirected. Results are limited to 1,000 rows by default. Set another positive
limit with `--max-rows`. Each query has a default time limit of 30 seconds; set a
different positive duration with `--timeout`. A query or schema view succeeds
with exit code 0. Query failures and sandbox refusals exit 1; invalid input or
option values exit 2. Results go to standard output and notices go to standard
error.

```bash
fitdocs query --schema
fitdocs query --format json "SELECT sport, count(*) AS activities FROM activities GROUP BY sport"
fitdocs index
```

## Worked examples

Use the schema to confirm a column's meaning before adapting an example. Each
time window is measured back from the latest date in the indexed data, so the
same SQL remains useful as new workouts arrive.

### Weekly running volume

Sum running distance by week for the latest twelve weeks in the index:

```sql
WITH data_end AS (
    SELECT max(CAST(start_utc AS DATE)) AS latest_day
    FROM activities
)
SELECT date_trunc('week', CAST(a.start_utc AS DATE))::DATE AS week_start,
       a.sport,
       sum(a.distance_m) / 1000.0 AS distance_km
FROM activities AS a
CROSS JOIN data_end
WHERE a.sport = 'Run'
  AND CAST(a.start_utc AS DATE) >= data_end.latest_day - INTERVAL '12 weeks'
GROUP BY week_start, a.sport
ORDER BY week_start;
```

### Time in zones

Sum time credited to each heart-rate zone across running activities in the
latest twelve weeks. The index records each channel as `heart_rate`, `power`,
or `pace`.

```sql
WITH data_end AS (
    SELECT max(CAST(start_utc AS DATE)) AS latest_day
    FROM activities
)
SELECT z.channel, z.bound_unit, z.zone, sum(z.time_s) AS seconds
FROM zone_times AS z
JOIN activities AS a USING (page_key)
CROSS JOIN data_end
WHERE z.channel = 'heart_rate'
  AND a.sport = 'Run'
  AND CAST(a.start_utc AS DATE) >= data_end.latest_day - INTERVAL '12 weeks'
GROUP BY z.channel, z.bound_unit, z.zone
ORDER BY z.zone;
```

### Training load

Add selected load points by week for the latest twelve weeks. A missing load
is absent; it contributes no measured value.

```sql
WITH data_end AS (
    SELECT max(date) AS latest_day
    FROM pages
)
SELECT date_trunc('week', p.date)::DATE AS week_start,
       l.calculator_id, l.selected,
       sum(l.load_value) AS selected_load
FROM pages AS p
JOIN loads AS l USING (page_key)
CROSS JOIN data_end
WHERE l.selected IS TRUE
  AND l.calculator_id = 'threshold'
  AND p.date >= data_end.latest_day - INTERVAL '12 weeks'
GROUP BY week_start, l.calculator_id, l.selected
ORDER BY week_start;
```

### Races, tests and hard efforts

List tagged efforts from the latest year of indexed activity dates. The tag
records how the athlete classified an effort; it does not infer race results.

```sql
WITH data_end AS (
    SELECT max(date) AS latest_day
    FROM pages
)
SELECT date, effort, effort_distance_m, effort_time_s, effort_event
FROM pages
CROSS JOIN data_end
WHERE effort IN ('race', 'test', 'hard')
  AND date >= data_end.latest_day - INTERVAL '1 year'
ORDER BY date, effort;
```

### Best efforts

Show the best recorded power for each duration in the latest year of data,
with the workout page it came from. This fixture's ride supports 1-, 5- and
10-second efforts; a fixed 20-minute filter would return no row.

```sql
WITH data_end AS (
    SELECT max(date) AS latest_day
    FROM pages
)
SELECT p.date, p.path, p.title, p.sport, m.duration_s, m.power_w
FROM mean_max AS m
JOIN pages AS p USING (page_key)
CROSS JOIN data_end
WHERE m.power_w IS NOT NULL
  AND p.date >= data_end.latest_day - INTERVAL '1 year'
QUALIFY row_number() OVER (
    PARTITION BY m.duration_s
    ORDER BY m.power_w DESC, p.date DESC, p.page_key
) = 1
ORDER BY m.duration_s;
```

### Fitness, fatigue and form

Show the last four weeks of form for the methodology `fitdocs history`
chooses by default. The window is measured back from that series' end date.

```sql
SELECT d.day, d.methodology, d.fitness, d.fatigue, d.form
FROM daily_load AS d
JOIN load_series AS s USING (methodology)
WHERE s.history_default
  AND d.day >= s.series_end - INTERVAL '28 days'
ORDER BY d.day;
```

### Thresholds in force

Show the FTP in force on each ride's date in the latest year of data. The
period's end is open while that benchmark remains in force.

```sql
WITH data_end AS (
    SELECT max(date) AS latest_day
    FROM pages
)
SELECT p.date, p.sport, b.kind, b.discipline, b.starts_on, b.ends_before,
       b.value, b.unit, b.measured_on
FROM benchmark_periods AS b
JOIN pages AS p
  ON p.sport = 'Ride'
 AND p.date >= b.starts_on
 AND (b.ends_before IS NULL OR p.date < b.ends_before)
CROSS JOIN data_end
WHERE b.kind = 'ftp_watts'
  AND b.discipline = 'Ride'
  AND p.date >= data_end.latest_day - INTERVAL '1 year'
ORDER BY p.date;
```

### Planned sessions not logged

List the sessions still marked not logged in the latest valid block. A
session dated after the index's resolved-on day is upcoming instead.

```sql
SELECT p.block_id, p.workout_id, p.day, p.sport, p.title, p.state
FROM planned_workouts AS p
JOIN blocks AS b USING (block_id)
WHERE b.valid
  AND b.starts_on = (
      SELECT max(starts_on)
      FROM blocks
      WHERE valid
  )
  AND p.state = 'not logged'
ORDER BY p.day, p.workout_id;
```

## Reporting an answer

Prefer the index for counts, totals, averages, distributions and trends.
Reading workout documents one by one is slower and makes aggregation easier to
get wrong. Show the SQL used to support your answer. State the date range and
units, and distinguish an empty result from a measured zero. NULL means absent, never zero.

## What the sandbox refuses

The sandbox accepts one read-only query or `EXPLAIN`. It refuses writes,
multiple statements, changing settings, loading or installing extensions,
attaching databases, copying files, file access outside the index, and network
access. A read-only connection alone would not block every file or network
operation; fitdocs also checks statement types and locks the database settings.

## Ownership

The analytics index is a disposable local cache. Workout documents and
archived source files remain the record, and the index can be rebuilt from
them. Do not edit the index to correct an answer. Read the published
[ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
for the boundary around generated data.

## Further reading

- [Querying the analytics index](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md) — command details, schema, and opening the index from another DuckDB client.
- [Ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) — the published boundary for generated data.
