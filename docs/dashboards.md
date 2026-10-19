## Before you start

A dashboard is a markdown page that you, or your assistant, write in the
`dashboards/` directory of your data root. fitdocs draws charts on it from the
local analytics index and writes nothing else on the page. Every chart's data
comes from SQL that runs against that index, so build the index first with
`fitdocs index`, and read [Analytics](analytics.md) for the tables and the
sandbox the SQL runs in.

```bash
fitdocs index
fitdocs query --schema
```

Test a query with `fitdocs query` before you put it in a directive: a chart
runs under the sandbox and time limit of `fitdocs query`, with one extra
parameter, `$today`, and is stricter: exactly one SELECT statement and at most
10,000 result rows.

## A dashboard page

A dashboard page is a regular file directly in `dashboards/` named
`<page name>.md`. A page name is one or more groups of lowercase ASCII letters
and digits joined by single hyphens, such as `weekly-volume.md`. Files in
subdirectories are not pages, and a markdown file whose name breaks the rule is
left alone and reported. fitdocs recognises a page by its location and name
alone; it never writes frontmatter on it. If your wiki records page types, the
type for these pages is `dashboard`.

fitdocs never creates, renames or deletes a page. You write the prose,
headings, frontmatter and the chart directives; fitdocs fills in one region
below each directive.

## The chart directive

A chart is declared by a hidden HTML comment. It opens with a line that is
exactly the first line of the example below and ends at the next line that is
exactly `-->`; both lines start at column 0. The lines between them are a YAML mapping in which
every value is read as the text you wrote, so `y_zero: true` is the text
`true`, never a boolean.

````markdown
<!-- fitdocs:chart
id: weekly-km
kind: bar
mode: relative
title: Weekly distance
window: last 12 weeks
sql: |
  SELECT date_trunc('week', start_utc)::DATE AS week_start,
         sum(distance_m) / 1000.0 AS distance_km
  FROM activities
  WHERE start_utc::DATE >= $today - 84
  GROUP BY 1
  ORDER BY 1
channels:
  x: week_start
  y: distance_km
-->
````

The required keys are `id`, `kind`, `mode`, `title` and `sql`. The optional
keys are `channels`, `options`, `window` and `show_rows`. Any other key is
refused, and the problem lists the accepted keys.

- `id` names the chart on its page: lowercase ASCII letters and digits joined
  by single hyphens, at most 64 characters. Two directives on one page may not
  share an `id`; both are refused.
- `kind` is a chart kind. [Chart kinds](#chart-kinds) lists the registered
  kinds, their channels and their options; `fitdocs dashboard kinds` prints the
  same list. fitdocs never guesses a kind, a channel or an option from your SQL
  or from the result.
- `mode` is `relative` or `frozen`; see [Relative and frozen
  charts](#relative-and-frozen-charts).
- `title` is single-line text. It becomes the chart's title and the text of the
  image link.
- `sql` is the query. Write it as a literal block (`sql: |`); other scalar
  styles can fold or cut SQL text, and fitdocs refuses them.
- `channels` maps each channel name to a result column name, one per line. The
  kind decides which channels exist and which are required.
- `options` maps option names to values, one per line. Values pass to the
  chart kit as written, and the kit checks them.
- `window` is single-line text that fitdocs shows in the chart's caption, such
  as `last 12 weeks`. It does not change the query; the window itself is
  written in SQL (see [Writing the SQL](#writing-the-sql)).
- `show_rows` is `true` or `false`. When `true`, the region also holds the
  result rows as a markdown table.

Four traps apply to every directive:

- The opening line and the closing `-->` start at column 0 with no
  indentation. A line outside a code fence that holds the opening text but is
  indented, or has other text on the line, is reported as a malformed opening
  line and is not a chart.
- The body contains no `-->` and no `--!>`. Either sequence ends the comment
  early and shows the rest of the directive as visible text, so fitdocs refuses
  the chart. Avoid them in SQL comments and in titles.
- `sql` is a literal block (`sql: |`).
- Obsidian's reading view hides a directive, but its Live Preview mode shows
  the directive as dimmed source. That is expected, not a fault.

A directive or region quoted inside a fenced code block, like the example
above, is not live: fitdocs ignores both inside backtick and tilde fences.

## Chart regions and assets

Directly below a directive, fitdocs keeps a region between two marker lines,
each starting at column 0:

```text
<!-- fitdocs:begin:chart:weekly-km -->
<!-- fitdocs:end:chart:weekly-km -->
```

Only blank lines may sit between the directive's closing `-->` and the begin
marker. If a valid directive has no region, fitdocs inserts one on the line
after the directive's closing line. fitdocs replaces only the bytes between the
two markers, and keeps the page's line endings and any leading byte-order mark.
Do not edit inside a region; the next run overwrites it.

An image chart's region holds one markdown image link whose text is the chart's
title and whose target is the image's path relative to the page. The image
itself is `dashboards/assets/<page name>/<chart id>.svg`. A chart kind that
produces markdown puts that markdown in the region instead. After the chart, a
caption line states, in this order and only where it applies: the date a frozen
chart's snapshot was taken, your `window` text, and the latest date in the
result's date or date-time columns (or that the result had no rows).

A chart that fails is isolated: every other chart and page still renders. A
chart that has rendered before keeps its region exactly as it was, and its
image too, unless the page changed during the run or could not be written after
the chart's new image was written: then the image already shows the new
drawing, and the next successful run brings the region in line. When `refresh`
or the pass finds that a chart that has never rendered fails in its query or
its drawing, or holds a value in its first frozen result that cannot be stored
(such as a non-finite number), that chart gets a region with a short note that
starts `Not rendered:` and states the first problem, and no image link. When a
chart's image, snapshot or page cannot be written, its region is left as it was
(a chart with no region still has none, and an earlier `Not rendered:` note
stays) and the failure is reported. A chart whose directive or region has a
problem is not written at all: no region is inserted or changed, and `check`
reports the problem. A failing `freeze` writes no note.

A region that sits anywhere but directly below its directive, a region with no
end marker, and a region that contains a directive opening line or another
region marker are all refused, and the region is left unchanged. A region whose
id matches no directive is left alone and reported as orphaned.

fitdocs writes a mark into every image. It never overwrites or deletes a file
in `dashboards/assets/` that does not carry the mark. When a `refresh` or
`freeze` run, or the pass after an index refresh, has finished its pages, it
deletes a marked image only when no dashboard page contains that image's path
relative to `dashboards/`. Links from outside `dashboards/` are not protected
from this cleanup: a note elsewhere in your wiki that links an image directly
does not keep it alive, so link the dashboard page instead.

## Relative and frozen charts

A relative chart (`mode: relative`) is redrawn from a fresh run of its SQL every
time fitdocs refreshes dashboards. It writes its region and image only when the
bytes differ, and it never writes the run date or the time, so a run whose
rows are unchanged changes nothing on disk. A window written with `$today`,
like the example above, moves each day, so its rows, and therefore its region
and image, can change on a day with no new workouts. A chart whose SQL does
not use `$today` changes only when its rows, its directive or the chart kit
change.

A frozen chart (`mode: frozen`) is a record. The first time fitdocs renders it
with no snapshot on hand, it runs the SQL once with `$today` bound to the run
date, stores the result as a snapshot, and draws the chart from the snapshot.
The region records which snapshot it was drawn from in a
`<!-- fitdocs:snapshot assets/<page>/<id>.snapshot-<n>.json -->` line.
From then on the chart is drawn from the stored rows and its SQL does not run,
including when no index exists. Changing the kind, title, channels, options,
`window` or `show_rows` redraws the chart from the stored rows.

If you change a frozen chart's SQL after its snapshot was taken, fitdocs keeps
drawing the snapshot and reports a notice that the SQL changed. To take a new
snapshot deliberately, run `fitdocs dashboard freeze PAGE:CHART`. That runs
the SQL again with a new run date, stores a new snapshot beside the old ones,
and points the region at it. Freezing a relative chart is refused; change its
mode first.

```bash
fitdocs dashboard freeze weekly-volume:cadence-before-hill-block
```

Snapshots are the one thing fitdocs never changes or deletes. They live in
`dashboards/assets/<page>/<chart id>.snapshot-<n>.json`, and `fitdocs regen`,
`fitdocs index --rebuild` and image cleanup leave them alone. If the snapshot a
region records is missing or unreadable, fitdocs leaves the chart as it was,
does not run the SQL, and reports how to take a new one.

## Writing the SQL

A chart runs exactly one SELECT statement, read only, under the same sandbox
and time limit as `fitdocs query`. A statement that writes, attaches, or loads
anything is refused, and so is a result of more than 10,000 rows; aggregate in
SQL instead. Each chart kind also has its own size bound (rows, bins, weeks,
cells or panels), listed with the kind under [Chart kinds](#chart-kinds).

- **`$today`** is the only parameter, bound to the run date as a date. Write a
  window as date arithmetic, `$today - 84`, or with an explicit cast, such as
  `CAST($today AS DATE) - 84`. `$today - INTERVAL 12 WEEK` is a timestamp, not
  a date, and will not compare as you expect against a date column. Any other
  parameter, positional ones included, is refused. `$today` inside a string
  literal or a comment is not a use.
- **Aliases keep their unit suffix.** fitdocs gives each column the unit of the
  suffix its name ends with and labels the axis with it, so `AS distance_km`
  is kilometres and `AS distance` has no unit. The analytics index documents
  the suffix vocabulary. fitdocs converts no unit: do the arithmetic in SQL and
  name the result for the unit you produced.
- **Pace is computed in SQL from speed:**
  `1000.0 / NULLIF(speed_mps, 0) AS pace_s_per_km`. The `NULLIF` matters,
  because a non-finite result such as a division by zero is refused by the
  chart kit with its `non_finite` problem rather than drawn or hidden. Guard
  every division.
- **A missing row is not an absent value.** A gap in a line needs a row whose
  value is `NULL`, for example from a calendar of weeks left-joined to the
  data. A stacked week with no activity needs an explicit zero:
  `COALESCE(sum(distance_m), 0)`. A week with no row at all is simply not drawn,
  and a line bridges over it.
- **Types.** Integers, floating-point and decimal values are numbers, `DATE`
  is a date, `TIMESTAMP` is a date-time, `INTERVAL` is a duration, text and
  enumerations are categories, and `BOOLEAN` is a boolean. Time of day,
  lists, structures, maps, binary and UUID columns are refused with the
  column's name and type; cast them in SQL or leave them out. A `TIMESTAMPTZ`
  column fails as a SQL error from the database with a hint to cast it to
  `TIMESTAMP`. A SQL `NULL`
  reaches the chart as an absent value, never as zero.

The [Analytics](analytics.md) page lists the tables. Run the SQL there first, with a
literal date where `$today` would be.

## Checking a page

Write a directive, run `fitdocs dashboard check`, and fix what it reports.
Repeat until it prints no problems. `check` never writes or deletes a file; it
checks the page's structure, each directive, the SQL's screening, the result's
columns against the kind's channels, and draws every chart in memory.

```bash
fitdocs dashboard check weekly-volume
fitdocs dashboard check weekly-volume --format json
```

Every problem carries a stable code, a one-sentence message and a
one-sentence fix, plus the page when it concerns a page, the chart id when it
concerns a chart, and the page line when it has one. A problem about a
directive key also names that key in the JSON report's `option` field; when
there are accepted values, its `accepted` list holds them, and the text report
appends them as ` Accepted: a, b, c.` A problem from the chart kit keeps
the kit's own code, message and fix, and the JSON report marks its `source`
as `chart`.
A notice, such as a frozen chart whose SQL changed, is reported apart and does
not make the exit code non-zero. When the index cannot be opened, `check` still
checks every chart that needs no query and reports each chart that does as not
queried, with the index's state and the command that fixes it.

## The fitdocs dashboard command

`fitdocs dashboard FORM [TARGET...]` takes one of four forms:

- `check` reports problems and notices without writing anything.
- `refresh` renders the targeted charts and writes as the automatic pass
  does, whether or not an index refresh has just run.
- `freeze` retakes the snapshot of the targeted frozen charts. It needs at
  least one target, and a page target freezes every frozen chart on that page.
- `kinds` lists the registered chart kinds. It takes no target and needs no
  data root.

A target is a page name, or a page name and a chart id joined by a colon, as in
`weekly-volume:weekly-km`. With no target, `check` and `refresh` cover every
page. A target that names no existing page or chart is an invalid-input error
that lists the available names. `--out PATH` picks the data root the way it
does for the other commands, and `--format json` prints the report as one JSON
document on standard output instead of text.

```bash
fitdocs dashboard refresh
fitdocs dashboard refresh weekly-volume:weekly-km
fitdocs dashboard kinds --format json
```

The text report ends with a summary line, `Dashboards: <r> rendered, <u>
unchanged, <f> failed.`, and adds `, <n> checked` when any chart was only checked (a `check`, or
charts that a page-target `freeze` left alone) and `, <k> images removed` when
cleanup deleted some. The JSON report lists the index's state,
each page's problems and notices, each chart's id, kind, mode, outcome,
snapshot path, problems and notices, and the paths of any images removed.
Pages come in name order and charts in page order, so the same inputs give the
same report.

The command exits 0 when every chart and page in scope checked or rendered
without a problem (notices are allowed), 1 when any problem was reported, 2 for
invalid input or configuration, and 130 when you interrupt it. An interrupt
stops the running statement and leaves every page, image and snapshot it had
not finished writing unchanged. The command makes no network request.

The commands that refresh the index after writing (`fitdocs sync`,
`fitdocs pull --sync`, `fitdocs regen` and `fitdocs load`) also run a refresh
over every page once the index refresh succeeded. This pass never builds the
index, never changes its command's exit code, and prints nothing when there is
no dashboard page. If the index was not refreshed, it changes no dashboard
file and prints one line saying so and why. `fitdocs index` itself does not run
the pass.

## Chart kinds

Everything between the markers below is generated from the chart registry,
the same source as `fitdocs dashboard kinds`; the test suite fails when it
differs. A kind registered later appears in `fitdocs dashboard kinds` at once,
and in this block when it is regenerated.

<!-- dashboard-kinds:start -->
### `line`

Lines over a numeric or time x, one per colour value

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | The horizontal position: a number, duration, date or date-time. |
| y | yes | number, duration | The vertical value: a number or duration. |
| color | no | category, boolean | One line per value of this column. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| x_scale | choice | linear | linear, log | The x axis scale; log needs a number or duration x. |
| y_scale | choice | linear | linear, log | The y axis scale; log needs values above zero. |
| y_zero | boolean | false | - | Extend the y axis to include zero. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 2000 rows, over refuse — At most 2000 rows; more are refused.

### `area`

Filled areas over a numeric or time x, optionally stacked

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | The horizontal position of each row. |
| y | yes | number, duration | The height of the area at each row. |
| color | no | category, boolean | One series per distinct value. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| stack | boolean | false | - | Stack the series in legend order instead of overlaying them. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 1000 rows, over refuse — An area chart draws at most 1000 rows; more are refused.

### `bar`

Vertical bars per category or date, grouped or stacked by colour

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | category, date, boolean | The category or date each bar group stands at. |
| y | yes | number, duration | The bar's value; the axis always includes zero. |
| color | no | category, boolean | Splits each group into one bar per value, in legend order. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| stack | boolean | false | - | Stack the colour series instead of placing them side by side. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 200 rows, over refuse — A bar chart draws at most 200 rows; more are refused.

### `hbar`

Horizontal bars, one per row, ranked by value

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| y | yes | category, date, boolean | The label of each bar. |
| x | yes | number, duration | The length of each bar. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| sort | choice | value | value, rows | Rank the bars by value, or keep the row order. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | - | 160 to 1200 | Chart height in pixels. |

Bound: 50 rows, over refuse — At most 50 rows; more are refused.

### `scatter`

One point per row, with optional colour and least-squares trend

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | The horizontal position of each point. |
| y | yes | number, duration | The vertical position of each point. |
| color | no | category, boolean | One series, with its own marker shape, per distinct value. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| x_scale | choice | linear | linear, log | The scale of the x axis. |
| y_scale | choice | linear | linear, log | The scale of the y axis. |
| trend | boolean | false | - | Draw a least-squares trend line for each series. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 360 | 160 to 1200 | Chart height in pixels. |

Bound: 2000 rows, over refuse — At most 2000 rows; more are refused.

### `histogram`

Counts of one numeric column in equal-width bins

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration | The values to count. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| bins | integer | - | 1 to 100 | The number of equal-width bins. |
| bin_width | number | - | - | The width of each bin, in the column's unit (seconds for durations). |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 280 | 160 to 1200 | Chart height in pixels. |

Bound: 100 bins, over reduce — Any number of values is binned; a binning that yields more than 100 bins is refused.

### `stat`

One headline value with its unit and an optional change

Output: markdown

| Channel | Required | Accepts | Description |
|---|---|---|---|
| value | yes | number, date, datetime, duration, category, boolean | The headline value. |
| compare | no | number, duration | The value to compare against, of the same kind and unit. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| delta | choice | absolute | absolute, percent, both | How the change from the comparison is shown. |

Bound: 1 rows, over refuse — A stat shows one row; more are refused.

### `table`

The rows as a markdown table with unit-aware cells

Output: markdown

Bound: 100 rows, over refuse — At most 100 rows and 12 columns.

### `calendar-heatmap`

One cell per day in Monday-start week columns, sized and shaded by a value of zero or more (negative values are refused); a day with no row draws nothing, so return a zero row to show a rest day

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| date | yes | date | The day of each row; one row per day. |
| value | yes | number, duration | The amount shown for the day, zero or more. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | - | 160 to 1200 | Chart height in pixels. |

Bound: 54 weeks, over refuse — At most 54 Monday-start week columns: any 366 consecutive days fit.

### `heatmap`

A grid of cells over two category, date, boolean or number axes, sized and shaded by a value of zero or more (negative values are refused); a position with no row draws nothing

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | category, date, boolean, number | The column each cell sits in: a category, date, boolean or number. |
| y | yes | category, date, boolean, number | The row each cell sits in: a category, date, boolean or number. |
| value | yes | number, duration | The size and shade of each cell: a number or duration, zero or more. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | - | 160 to 1200 | Chart height in pixels. |

Bound: 1500 cells, over refuse — At most 1500 cells, 60 x values and 40 y values.

### `dual-axis`

Two series over one x, each on its own y axis with its own unit; unless the two are a deliberate pair, prefer small-multiples or one line with a colour column

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | The horizontal position: a number, duration, date or date-time. |
| y | yes | number, duration | The value drawn solid against the left axis: a number or duration. |
| y2 | yes | number, duration | The value drawn dashed against the right axis, in another unit than y: a number or duration. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| y_zero | boolean | false | - | Extend the left axis to include zero. |
| y2_zero | boolean | false | - | Extend the right axis to include zero. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 2000 rows, over refuse — At most 2000 rows; more are refused.

### `band`

A band from low to high over a numeric or time x, with an optional centre line

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | The horizontal position: a number, duration, date or date-time. |
| low | yes | number, duration | The lower edge of the band: a number or duration. |
| high | yes | number, duration | The upper edge of the band, in the kind and unit of low. |
| mid | no | number, duration | The centre line (for example a median), in the kind and unit of low. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| y_zero | boolean | false | - | Extend the y axis to include zero. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 1000 rows, over refuse — At most 1000 rows; more are refused.

### `box`

One box-and-whisker per category from given quartiles

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | category, date, boolean | The category or date each box stands at. |
| low | yes | number, duration | The lower whisker end. |
| q1 | yes | number, duration | The bottom edge of the box. |
| median | yes | number, duration | The line across the box. |
| q3 | yes | number, duration | The top edge of the box. |
| high | yes | number, duration | The upper whisker end. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| y_zero | boolean | false | - | Extend the y axis to include zero. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 60 rows, over refuse — A box chart draws at most 60 rows; more are refused.

### `mean-max`

Best-effort curves over a log duration axis, one per period

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration | The duration of each best effort: a duration, or a number in seconds. |
| y | yes | number, duration | The best mean value over that duration: a number or duration. |
| color | no | category, boolean | One curve per value of this column, such as a season. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| y_zero | boolean | false | - | Extend the y axis to include zero. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 1000 rows, over refuse — At most 1000 rows; more are refused.

### `small-multiples`

A grid of small line charts, one per facet value

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | The horizontal position in every panel: a number, duration, date or date-time. |
| y | yes | number, duration | The vertical value: a number or duration. |
| facet | yes | category, boolean, date | One panel per value of this column, titled with the value. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| y_axes | choice | shared | shared, independent | Whether every panel shares one y scale or has its own. |
| columns | integer | - | 1 to 6 | The number of panel columns; unset, it follows the chart width. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | - | 160 to 1200 | Chart height in pixels. |

Bound: 12 panels, over refuse — At most 12 panels and 2000 rows.

### `stacked-100`

Bars that split each category or date into shares of 100%

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | category, date, boolean | The category or date each bar stands at. |
| y | yes | number, duration | Each part's value; never absent or negative. |
| color | yes | category, boolean | The part: one segment per value, in legend order, bottom to top. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 400 rows, over refuse — A stacked-100 chart draws at most 400 rows; more are refused.

### `reference-band`

Values as points against a segmented reference band, with optional centre line and flags.

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, duration, date, datetime | Horizontal position. |
| y | yes | number, duration | Values as points. |
| low | no | number, duration | Lower band edge. |
| high | no | number, duration | Upper band edge. |
| mid | no | number, duration | Centre line. |
| segment | no | category | Separate source segments. |
| flag | no | boolean | Rows marked along the bottom axis. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| y_zero | boolean | false | - | Extend the y axis to include zero. |
| width | integer | 720 | 320 to 1600 | Chart width in pixels. |
| height | integer | 320 | 160 to 1200 | Chart height in pixels. |

Bound: 1000 rows, over refuse — At most 1000 rows; more are refused.
<!-- dashboard-kinds:end -->

## Who owns what

You own the page: its prose, headings, frontmatter and directives. fitdocs owns
the bytes between each region's begin and end markers, the chart images in
`dashboards/assets/`, and the snapshots it writes there. `dashboards/AGENTS.md`
is a generated file that tells an agent the same thing. A dashboard run writes
only inside existing pages' regions and inside `dashboards/assets/`, replaces
files atomically, and refuses a symbolic link, a page that changed while it
ran, a page that is not valid UTF-8, and any path in `dashboards/assets/` that
fitdocs did not write. [The ownership contract](ownership-contract.md) states
this per directory.

## Version control

Commit the pages and the snapshots. A snapshot is the only copy of the rows a
frozen chart was drawn from, so do not git-ignore `*.snapshot-<n>.json` files,
even if you ignore the images. The `.svg` images are re-derivable from the
pages, snapshots and the index, so ignoring them is safe, but then a fresh
checkout has no images until `fitdocs dashboard refresh` runs. Relative charts
change only when their rows, their directive or the chart kit change. A chart
whose window uses `$today` moves with the date, so its region and image can
change on the first refresh of a new day even when no new workouts arrived. A
sync that brings no new data leaves the working tree clean only for charts
whose SQL does not use `$today`.
