---
name: fitdocs-dashboards
description: Use when an athlete asks for a chart, graph or dashboard page built from their training data, or when a chart on a wiki page needs writing, fixing or retaking.
license: MIT
compatibility: Requires the fitdocs command to be installed and a built analytics index.
metadata:
  version: 0.1.0
---

# Put charts on a dashboard page

## When this applies

Use this skill when the athlete wants an answer from their training history
drawn as a chart on a wiki page: weekly volume as bars, a trend as a line, a
distribution as a histogram. A dashboard page is an ordinary markdown page in
the dashboards directory of the data root. You write the prose and, for each
chart, one hidden chart directive holding its SQL; fitdocs runs the SQL
against the analytics index and draws the chart in a region directly below the
directive. Work out the SQL first with the `fitdocs-analytics` skill, then
return here to put the answer on the page.

## Write a chart directive

A directive is an HTML comment whose first line is exactly
`<!-- fitdocs:chart` and whose last line is exactly `-->`, both at column 0.
The lines between are a YAML mapping. Every value is read as text exactly as
written, so `no`, `2026-10-11` and `012` are never turned into a boolean, a
date or a number.

The keys, with these exact spellings:

- `id`: the chart's name on this page, lowercase letters and digits joined by
  single hyphens, at most 64 characters. Required.
- `kind`: which chart to draw. Required. Run `fitdocs dashboard kinds` for the
  kinds that exist, what each one is for, and its channels and options; this
  skill does not list them, because the list grows.
- `mode`: `relative` or `frozen`. Required.
- `title`: single-line text, used as the image's text. Required.
- `sql`: one SELECT statement, written as a literal block with `sql: |`.
  Required.
- `channels`: a mapping from the kind's channel name to a column of the
  result. Optional.
- `options`: a mapping from the kind's option name to its value. Optional.
- `window`: single-line text stated in the chart's caption, such as
  `Last 12 weeks`. It is a caption only; the SQL decides the window. Optional.
- `show_rows`: `true` or `false`; `true` adds the result's rows as a table
  below the chart. Optional.

Any other key is refused. fitdocs never guesses a kind, a channel or an option
from the SQL or the result: if a channel is not bound, say so in `channels`.
Quote a value that contains a colon followed by a space.

A complete directive, shown inside a fence so that it is not live:

```markdown
<!-- fitdocs:chart
id: weekly-run-km
kind: bar
mode: relative
title: Weekly running distance
window: Last 12 weeks
channels:
  x: week_start
  y: distance_km
sql: |
  SELECT date_trunc('week', CAST(start_utc AS DATE))::DATE AS week_start,
         sum(distance_m) / 1000.0 AS distance_km
  FROM activities
  WHERE sport = 'Run'
    AND CAST(start_utc AS DATE) >= $today - 84
  GROUP BY week_start
  ORDER BY week_start
-->
```

The first time `fitdocs dashboard refresh` runs on the page, fitdocs inserts a
region on the line after the directive's closing line: a begin marker
`<!-- fitdocs:begin:chart:weekly-run-km -->`, the chart (an image link for
image charts) with a caption, and an end marker
`<!-- fitdocs:end:chart:weekly-run-km -->`. Keep the region directly below its
directive, with only blank lines between. fitdocs writes the chart image under
its assets directory, one file per page and chart id.

## Relative and frozen charts

A relative chart runs its SQL again whenever the dashboards are refreshed:
after `fitdocs sync`, `fitdocs pull --sync`, `fitdocs regen` or `fitdocs load`
has refreshed the index, and on demand with `fitdocs dashboard refresh`. It
changes bytes only when its rows, its directive or the chart kit change, so a
run with identical rows writes nothing. A window written with `$today` moves
each day, so its rows, and therefore its bytes, can change on a day with no new
workouts.

A frozen chart is a record. The first render runs its SQL once, stores the
result rows and the run date as a snapshot, and draws the chart from the
snapshot; the region records which snapshot it was drawn from. After that the
SQL never runs again, even when the index is gone. Editing the title, kind,
channels, options, window or show_rows redraws a frozen chart from its stored
rows. If you edit its SQL, fitdocs keeps drawing from the snapshot and reports
a `sql_changed` notice.

To retake a frozen chart's snapshot, run `fitdocs dashboard freeze
PAGE:CHART`, where `PAGE` is the page name (the file name without `.md`). It
stores a new snapshot beside the old ones and points the region at it. A page
name alone, `fitdocs dashboard freeze PAGE`, retakes every frozen chart on the
page and leaves the relative ones alone; naming a relative chart is refused.
Freezing needs at least one target. Snapshots (`*.snapshot-<n>.json`) are never
deleted; keep them in version control even if images are ignored.

## Windows with $today

`$today` is the one parameter a chart's SQL may use. It is the run date, bound
as a DATE; any other parameter, or a positional `?`, is refused. A window is
date arithmetic on a date: `$today - 84` is twelve weeks back. Do not write
`$today - INTERVAL 12 WEEK`: subtracting an INTERVAL from a date gives a
timestamp, not a date, so write date arithmetic or cast the result back to a
date, as in `CAST($today - INTERVAL 12 WEEK AS DATE)`. The `window` key only labels the caption; it does not change the query.

## Columns, units and pace

Each result column gets a value kind from its database type: integers, floats
and decimals are numbers, DATE is a date, TIMESTAMP is a date-time, INTERVAL
is a duration, text is a category, BOOLEAN is a boolean. A column of any other
type (time of day, timestamp with time zone, list, struct, map, binary, UUID)
is refused; cast it, or leave it out. A result over 10,000 rows is refused:
aggregate in SQL. Each kind also has its own size limit (rows, bins,
panels, cells or weeks), shown by `fitdocs dashboard kinds`.

A column's unit comes from the suffix of its name, and fitdocs converts
nothing. An alias keeps its suffix to keep its unit: `AS distance_km` is
kilometres, `AS distance_m` is metres, and a column renamed `AS d` has no unit.
Do the arithmetic yourself, in SQL.

Pace is not stored; compute it from speed:
`1000.0 / NULLIF(speed_mps, 0) AS pace_s_per_km`. Guard every division with
`NULLIF`. A non-finite result, such as a division by zero, is refused with a
`non_finite` problem rather than drawn or hidden.

A missing row is not an absent value. A week with no activity has no row, so a
line chart simply bridges over it and a bar chart draws no bar. To show a gap
in a line, produce a row whose value is NULL, for example by left-joining the
data onto a calendar of weeks. To draw a stacked week with no activity as
zero, say so in SQL with `COALESCE(total, 0)`; fitdocs never substitutes a
zero for an absent value on its own, and NULL always means absent.

## Running cadence

Running cadence columns, those ending `_cadence_rpm`, hold strides per minute:
one foot, the FIT convention. They are not steps per minute. A chart in steps
per minute needs a query that doubles the stored value. The doubled column
loses the suffix, and with it the unit, so name it for what it is and say
"steps per minute" in the title.

## The check loop

Write the directive, then check the page before anything else:

```bash
fitdocs dashboard check --format json weekly
fitdocs dashboard check --format json weekly:weekly-run-km
fitdocs dashboard refresh weekly
fitdocs dashboard kinds
```

`check` writes and deletes nothing. It reads the page, parses each directive,
screens the SQL, runs it (a frozen chart that has a snapshot is drawn from
the snapshot instead), checks the result's columns against the kind's
channels, and draws every chart in memory. Give no target to check every page,
a page name for one page, or `PAGE:CHART` for one chart.

Run `fitdocs dashboard check --format json` and read the whole report. At the
top level, `location_problems` holds findings about the dashboards location,
`index` holds the index's state and an optional `problem`, and `pages` lists
each page. A page has its own `problems` and `notices` (a malformed opener or
marker) and a `charts` list; an unclosed or id-less directive is reported as a
chart whose `id` is null. Each chart has an
`outcome` and its own `problems` and `notices`. Every finding has a stable
`code`, a one-sentence `message` and a one-sentence `fix`; the page, chart
and line fields are null where they do not apply. On a problem about a directive key, `option` holds
the key's name; `accepted` lists the values or keys that would have been
accepted. Fix every listed problem, page-level ones included, check again, and
repeat until the exit code is 0. The exit codes are 0 for no problems (notices allowed), 1 when
any problem was reported, 2 for invalid input such as an unknown target, and
130 when interrupted. Then run `fitdocs dashboard refresh` to write the
regions. Without `--format json` the report is text, one line per finding.

If the index cannot be opened, charts that need a query report
`index_unavailable` with the index's state and the command that fixes it, such
as `fitdocs index`. A frozen chart that already has a snapshot still renders.

Test the SQL as a plain query with `fitdocs query` first when it is complicated;
a chart runs under the same read-only sandbox and time limit.

## Traps

- The opening line and the closing line start at column 0, with no
  indentation and nothing else on the line. An indented
  `<!-- fitdocs:chart`, such as one inside a list item, is reported as a
  malformed opener and is not a chart.
- The body must not contain `-->` or `--!>`, not even in a SQL comment: either
  sequence ends the comment early and the rest of the directive shows as
  visible text.
- `sql` is always `sql: |`. A plain, quoted or folded scalar can fold or cut
  SQL text and is refused.
- Two directives on one page with the same `id` are both refused.
- A directive or region marker inside a fenced code block is ignored, so an
  example quoted on a page is never live. Show examples inside a fence.
- Obsidian's reading view hides a directive entirely. Its Live Preview mode
  shows the directive as dimmed source text; that is expected, not a bug.
- Under a refresh (the command, or the pass after sync, pull --sync, regen or
  load), a chart that has never rendered and whose query or drawing fails, or
  whose first frozen result holds a value that cannot be stored (such as a
  non-finite number), gets a region starting `Not rendered:` with the first
  problem. A chart with a directive or region problem is never edited. When a
  chart's image, snapshot or page could not be written, its region is left as
  it was (a chart with no region still has none, and an earlier `Not rendered:`
  note stays) and the failure is reported. A failing `freeze` writes no note. A
  chart that rendered before keeps its last good region and image.

## Ownership

The page is the athlete's: every word, heading, frontmatter line and directive
is theirs, and fitdocs never creates, renames or deletes a page. On a page,
fitdocs owns only the bytes between a chart's begin and end markers; beside the
pages it owns the files it writes in its assets directory (images and
snapshots) and the generated `AGENTS.md`. Never edit between the markers
or in the assets directory by hand; change the directive and run
`fitdocs dashboard refresh`. The generated file named `AGENTS.md` in the
dashboards directory restates this. Read the published
[ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
for the boundary around generated data.

## Further reading

- `fitdocs dashboard kinds` — the live list of chart kinds with their channels and options.
- [Querying the analytics index](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md) — the schema and the SQL a chart runs.
- [Dashboards guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/dashboards.md) — the directive, the chart kinds and the commands in full.
- [Ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) — the published boundary for generated data.
