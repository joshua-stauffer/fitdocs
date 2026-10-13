# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete whose LLM assistant writes dashboard pages
in their wiki (Phase 11, `dashboards`), and the `chart-catalog` spec that adds
more chart shapes, both need fitdocs to draw a chart of *any* typed result
columns in a named shape, readable in light and dark themes.

**Current situation.** fitdocs can draw four purpose-built charts (the hero
chart, the calendar chart, the zone strip and the route map). Each takes a
spec shaped for one page; none accepts "these columns, this encoding". Margins,
scales, ticks, legends and fonts are duplicated per module, ticks are evenly
spaced rather than "nice", tick labels carry no units, and every text and axis
colour is a hard-coded dark grey that is unreadable on a dark background
(`#333333` is 1.32:1 on Obsidian's `#1e1e1e`).

**What should change.** A pure, standard-library-only chart kit turns typed
columns plus a named encoding into a byte-deterministic SVG or a markdown
fragment: a typed data contract in which absent data is never drawn as zero; a
shared layer of scales, nice ticks, unit-aware labels, axes, legend, layout and
one light/dark theme mechanism (transparent background, base inks at least
3:1 on four reference backgrounds, an embedded media-query style raising small
text to 4.5:1 where honoured); a declared, append-only kind registry with
encoding schemas and structured, actionable validation errors; mark bounds and
a size budget; and eight core kinds (`line`, `area`, `bar`, `hbar`, `scatter`,
`histogram`, `stat`, `table`). The four existing renderers stay byte-identical.

Source: `.kiro/specs/chart-kit/brief.md`; Phase 11 of
`.kiro/steering/roadmap.md`. Dependencies: none. Downstream: `dashboards` and
`chart-catalog`, which start in parallel from this spec's design.

## Introduction

The chart kit draws one chart from one table of typed values. A caller (in
Phase 11, the `dashboards` pass) supplies the table and a short chart request:
which kind of chart, which column goes on which visual channel, a title and a
few options. The kit either returns the chart, as an SVG image or a markdown
fragment, or returns a list of problems, each saying what is wrong and what
would fix it. It never guesses.

Terms used below:
- A **column** has a name, a **value kind** (number, date, date-time, duration,
  category or boolean), an optional **unit token** and an optional display
  label. A **row** holds one value per column. An **absent** value is the
  absence of a value (Python `None`), never zero.
- A **unit token** names a unit the way the analytics index's column-name
  suffixes do, without the leading underscore: `km`, `s`, `s_per_km`, `bpm`,
  `rpm`, `pct` and the rest of the index's documented suffixes.
- A **kind** is a named chart shape in the **registry** (`line`, `bar`, …). A
  kind declares its **channels** (named visual roles such as `x`, `y` and
  `color`, each required or optional and each accepting some value kinds), its
  **options**, its output, and its **mark bound**.
- A **chart request** names a kind, a title, a caller **reference** that
  identifies the chart in problems, channel bindings (channel → column name)
  and options.
- A **mark** is one drawn data element: a point, a bar or bar segment, a
  histogram bin, a table cell or a stat value.
- A **problem** is one structured validation finding.
- The **reference backgrounds** are `#ffffff` (light), `#1e1e1e` (Obsidian
  dark), `#0d1117` (GitHub dark) and `#1e2129` (Material slate). The latter
  three are the **dark backgrounds**.
- An **ink** is a colour the kit draws text, axes, tick marks or series marks
  with. Gridlines and the translucent fill behind an outlined series are
  **decorative**: they carry no information of their own.

## Boundary Context

- **In scope**: the typed data contract; the unit vocabulary and how each unit
  is formatted; the chart request, its validation and the structured problems;
  the declared kind registry and its machine-readable description; scales,
  ticks, axes, legend, layout and the light/dark theme; the treatment of absent
  data and the no-data state; accessibility metadata; mark bounds and the size
  budget; the core kinds `line`, `area`, `bar`, `hbar`, `scatter`, `histogram`,
  `stat` and `table`; determinism and purity; the tests that pin all of it.
- **Out of scope**: reading SQL, the analytics index or any file, and where a
  chart's data comes from or where its output is written; dashboard pages,
  directives, captions, chart regions, snapshots and refresh (`dashboards`);
  the extended kinds (`chart-catalog`); changing the hero, calendar, zone-strip
  or map renderers or their output; JavaScript or interactive output; a map
  kind; pie and donut charts; converting a value from one unit to another.
- **Adjacent expectations**: `dashboards` builds chart data from query results
  (mapping result columns to value kinds and unit tokens with the kit's
  column-name lookup) and renders every chart through the registry, listing
  its kinds from the kit's description. `chart-catalog` appends kinds to the
  registry, and any shared-layer addition a kind proves it needs, without
  editing a core kind. The analytics index keeps its documented unit suffixes,
  phrases and order exactly as they are today; this feature makes the kit read
  the same single list rather than a copy.

## Requirements

### Requirement 1: Typed Data Contract
**Objective:** As a caller with a table of query results, I want to hand the
kit typed columns and rows in which absence is explicit, so that the chart can
never mistake a missing value for zero.

#### Acceptance Criteria
1. The chart kit shall accept chart data as an ordered set of uniquely named columns, each declaring one value kind (number, date, date-time, duration, category or boolean), an optional unit token and an optional display label, together with rows that each hold one value per column.
2. The chart kit shall treat an absent value in any column as absent, and shall never substitute zero, an empty string, a default or an interpolated value for it.
3. If a value present in a column a chart uses does not match that column's value kind (a boolean or a non-finite number in a number column, a date-time in a date column, a timezone-aware date-time, or a value of any other type), then the chart kit shall refuse the chart with a problem naming the column, the first offending row and the number of offending rows.
4. If two columns share a name, or a row holds a different number of values than there are columns, then the chart kit shall refuse the chart with a problem naming the column or the row.
5. If a column a chart uses carries a unit token that is not in the unit vocabulary, or one that does not apply to the column's value kind, then the chart kit shall refuse the chart with a problem naming the column, its value kind and the token.
6. When a column declares no display label, the chart kit shall label it with its name, without its unit suffix and with underscores shown as spaces.

### Requirement 2: One Unit Vocabulary
**Objective:** As an athlete reading a chart, I want every axis, label and
cell to show its unit the way fitdocs names it everywhere else, so that a pace
reads as min/km and a duration as h:mm:ss rather than bare numbers.

#### Acceptance Criteria
1. The chart kit shall format values from one unit vocabulary whose tokens are exactly the analytics index's documented column-name unit suffixes, read from the same single list the index schema reads, never from a second copy.
2. The chart kit shall leave the analytics index's documented suffixes, their unit phrases and their order unchanged.
3. When given a column name, the chart kit shall report the unit token of the most specific documented suffix the name ends with, or no unit token when none matches.
4. The chart kit shall format seconds and duration values as `h:mm:ss` (`m:ss` below one hour), seconds per kilometre as `m:ss` labelled `min/km`, percent values with a `%` sign, dates as `YYYY-MM-DD`, date-times as `YYYY-MM-DD HH:MM`, and every other unit token as a number followed by that unit's symbol.
5. The chart kit shall label each unit as its suffix names it, including `rpm` for the revolutions-per-minute suffix, and shall not reinterpret a unit by sport, by column name or by the values it holds.
6. The chart kit shall not convert a value from one unit to another; a chart in another unit takes a column that already carries that unit.
7. The chart kit shall label each axis and each table header with the column's display label followed by its unit symbol, when the column has a unit token.
8. The chart kit shall produce every number, date, duration and label independently of the host's locale, language, timezone and environment.

### Requirement 3: Chart Requests and Encoding Validation
**Objective:** As an agent writing a chart directive, I want to name a kind,
bind columns to its channels and check the result against the columns my query
returns before any rows exist, so that I can fix a wrong encoding in one pass.

#### Acceptance Criteria
1. The chart kit shall accept a chart request naming a kind, a title, a caller reference, bindings from channel names to column names, and option values.
2. The chart kit shall let a caller validate a chart request against column descriptions alone, without rows, and shall report every request-level problem it finds.
3. If the request names a kind that is not registered, then the chart kit shall report a problem listing the registered kinds.
4. If a required channel of the kind is unbound, then the chart kit shall report a problem naming the channel and the columns whose value kind it accepts.
5. If a channel is bound to a column name that is not among the columns, then the chart kit shall report a problem naming the channel, the missing column and the columns whose value kind the channel accepts.
6. If a channel is bound to a column whose value kind the channel does not accept, then the chart kit shall report a problem naming the channel, the column, its value kind, the accepted value kinds and the columns that would fit.
7. If the request binds a channel the kind does not declare, or sets an option the kind does not declare, then the chart kit shall report a problem naming it and listing what the kind declares.
8. If an option value has the wrong type, lies outside the option's declared range or choices, or combines with another option in a way the kind declares invalid, then the chart kit shall report a problem naming the option and what it accepts.
9. If the title is empty, then the chart kit shall report a problem.
10. When the request omits an option, the chart kit shall apply that option's declared default.
11. The chart kit shall never infer a kind, a channel binding or an option value from column names, value kinds or data.

### Requirement 4: Structured Problems an Agent Can Act On
**Objective:** As an agent iterating on a chart in a loop, I want every failure
to arrive as structured problems that say what is wrong and what would fix it,
so that I can correct the request without reading fitdocs's source.

#### Acceptance Criteria
1. The chart kit shall describe each problem with the caller's chart reference, the kind when known, a stable problem code, the channel, column, option or row concerned where one applies, one sentence on what is wrong, one sentence on what would fix it, and the names that would be accepted where such a list exists.
2. When a chart request has several request-level problems, the chart kit shall report all of them together, in an order that depends only on the request and the columns.
3. When the same data problem affects many rows, the chart kit shall report it once per column and problem code, naming the first affected row and the number of rows affected.
4. If a chart cannot be drawn, then the chart kit shall return its problems and no chart, never a partial chart.
5. The chart kit shall keep each problem code's meaning fixed once published, so that callers can act on codes.

### Requirement 5: Declared, Append-Only Kind Registry
**Objective:** As the `dashboards` and `chart-catalog` features, I want one
declared registry of kinds that each describe their channels, options, output
and bounds, so that dashboards can list and render any kind and chart-catalog
can add kinds without touching the core.

#### Acceptance Criteria
1. The chart kit shall hold a declared registry in which each kind states its name, a one-line description, its output (SVG image or markdown fragment), its channels (each with a name, whether it is required, the value kinds it accepts and a description), its options (each with a type, a default, its range or choices, and a description), its mark bound, how it treats data over that bound, and how it is drawn.
2. The registry shall hold the core kinds `line`, `area`, `bar`, `hbar`, `scatter`, `histogram`, `stat` and `table`, in that order, followed by any appended kinds.
3. The chart kit shall add a kind to the registry only by an explicit appended declaration, never by discovering modules, and appending a kind shall not change any core kind's declaration or output.
4. The chart kit shall require kind names to be unique, lowercase and hyphen-separated, and channel and option names to be unique within a kind.
5. The chart kit shall provide a machine-readable description of every registered kind, in registration order, giving for each kind its name, description, output, channels with their accepted value kinds, options with their defaults and constraints, and mark bound.
6. When a kind is appended to the registry, the chart kit shall validate, bound, theme and render charts of that kind under the same rules as the core kinds.

### Requirement 6: Scales, Ticks and Labels
**Objective:** As an athlete reading a chart, I want axes with round tick
values in familiar steps, so that I can read values off the chart at a glance.

#### Acceptance Criteria
1. The chart kit shall place values on linear, logarithmic, date and category scales, chosen from the bound column's value kind and the kind's options.
2. The chart kit shall choose value-axis ticks at round values: 1, 2 or 5 times a power of ten for plain numbers; seconds, minutes and hours steps for durations and paces; and days, Monday-starting weeks, months, quarters and years for dates; and shall extend a value axis to the nearest ticks that enclose the data.
3. The chart kit shall choose fewer ticks when the estimated widths of their labels would overlap, so that no two tick labels overlap.
4. When every value on an axis is the same, including a single point, the chart kit shall widen that axis by a stated rule so that the marks sit inside a non-degenerate axis.
5. Where a kind shows magnitude by length or area (bar, horizontal bar, area and histogram), the chart kit shall include zero in the value axis.
6. If a logarithmic scale is requested for a column holding a zero or negative value, then the chart kit shall refuse the chart with a problem naming the column and the first offending row.
7. The chart kit shall order categories by their first appearance in the rows, and dates in ascending order, except where a kind states another order.

### Requirement 7: Axes, Legend and Layout
**Objective:** As an athlete, I want each chart to carry its title, labelled
axes and a legend that never collide or get clipped, so that it reads on its own
wherever the image is shown.

#### Acceptance Criteria
1. The chart kit shall draw on each SVG chart its title, its axes with tick marks and tick labels, light gridlines at the value-axis ticks, and an axis title for each axis carrying the column's display label and unit symbol.
2. Where a colour channel is bound, the chart kit shall draw a legend naming each series in series order, each entry showing the series' colour and its non-colour carrier.
3. The chart kit shall reserve space for tick labels, axis titles, the legend and notes from a fixed per-character width estimate, so that no text extends past the chart's edge or into the plot area.
4. If a title, tick label, category label or legend label is longer than the space reserved for it, then the chart kit shall shorten it with an ellipsis by a deterministic rule.
5. The chart kit shall draw each SVG kind at a stated default size, which a request may change within stated limits.

### Requirement 8: One Theme for Light and Dark Viewers
**Objective:** As an athlete who reads the wiki in Obsidian, on GitHub and on
the docs site in light or dark mode, I want every chart to stay readable
whichever theme the viewer uses or guesses, so that no chart turns into dark
text on a dark page.

#### Acceptance Criteria
1. The chart kit shall draw every SVG chart on a transparent background.
2. The chart kit shall draw every ink, as it appears without any style rule applied, at a contrast ratio of at least 3:1 against each of the four reference backgrounds; decorative gridlines and fills are exempt.
3. The chart kit shall embed in each SVG chart one style element whose dark-scheme rule raises all text to at least 4.5:1 against each dark background, and whose light-scheme rule raises all text to at least 4.5:1 against `#ffffff`, wherever the viewer applies those rules.
4. The chart kit shall keep every ink set by either scheme rule at a contrast ratio of at least 3:1 against all four reference backgrounds, so that a viewer applying the wrong scheme never drops text below 3:1.
5. The chart kit shall theme every kind, including appended kinds, through this one mechanism, and no kind shall set its own text, axis or gridline colours.
6. The chart kit shall not depend on the `light-dark()` colour function, on `currentColor`, or on serving a separate image per theme.
7. The chart kit shall colour series from one categorical palette of a stated size, in which each colour is derived from a stated oklch source and every pair of colours is separated by at least a stated perceptual distance under normal vision and under simulated protanopia, deuteranopia and tritanopia.
8. The chart kit shall never make colour the only carrier of meaning: every series distinguished by colour shall also be distinguished by a dash pattern, a marker shape, or its position matched to the legend order, and shall be named in the legend.

### Requirement 9: Absent Data and the No-Data State
**Objective:** As an athlete, I want a missing value to look missing and a zero
to look like zero, so that a gap in my data is never read as a rest day.

#### Acceptance Criteria
1. When a line or area series has an absent value, the chart kit shall break the series at that row and shall never bridge the gap; a point with no present neighbour shall be drawn as a dot.
2. When a bar's value is absent, the chart kit shall draw no bar for it, and when a bar's value is zero the chart kit shall draw a visible zero-height stub, so that zero and absent look different.
3. When a row cannot be drawn because a value the kind needs to place it is absent, the chart kit shall state on the chart and in its description how many rows are not drawn and for which channel, and shall never drop a row without saying so.
4. When a colour or category value is absent, the chart kit shall show those rows as their own series or category labelled with an em dash, ordered last.
5. If a stacked chart holds an absent value, or a stacked area lacks a row for a series at an x value another series has, then the chart kit shall refuse the chart with a problem whose fix names unstacking the chart or supplying the missing values.
6. When the data has no rows, the chart kit shall draw an explicit no-data state carrying the title, a visible "No data" message and a matching description, at the chart's normal size.
7. When the data has rows but none holds a value the chart can draw, the chart kit shall draw the no-data state stating that the rows hold no values.
8. The chart kit shall show an absent value in markdown output as an em dash (U+2014).

### Requirement 10: Accessibility Metadata
**Objective:** As an athlete using assistive technology, or an agent reading an
SVG file, I want each chart to describe itself in text, so that its content is
available without seeing it.

#### Acceptance Criteria
1. The chart kit shall give each SVG chart the image role, a title element carrying the chart title, and a description element summarising the kind, each bound channel's label and unit, the number of rows, the number of rows not drawn, and the range of each axis as formatted labels.
2. The chart kit shall draw all chart text as text, never as paths or images.
3. When a chart is in the no-data state, the chart kit shall say so in its description.

### Requirement 11: Mark Bounds and the Size Budget
**Objective:** As an athlete whose wiki syncs through iCloud and git, I want
every chart file to stay small and every oversized result to be refused with a
clear fix, so that one careless query never writes a megabyte of SVG.

#### Acceptance Criteria
1. The chart kit shall draw at most the mark bound each kind declares, and shall draw a chart whose mark count equals the bound.
2. If a chart would exceed its kind's mark bound, then the chart kit shall either refuse it with a problem naming the bound, the count and how to reduce the data, or reduce the data by the rule the kind declares; it shall never drop rows silently to meet the bound.
3. If a colour channel yields more series than the palette holds, then the chart kit shall refuse the chart with a problem naming the series count and the limit.
4. The chart kit shall state a byte budget for each of a set of typical charts, and the fitdocs test suite shall fail if any of those charts exceeds its budget.
5. The chart kit shall state a byte ceiling for any chart drawn at its kind's mark bound, and the fitdocs test suite shall fail if a chart at the bound exceeds it.

### Requirement 12: Line and Area Kinds
**Objective:** As an athlete, I want trends over time or distance as lines or
filled areas, split by a category, so that I can see how a quantity moves.

#### Acceptance Criteria
1. The chart kit shall draw a `line` chart from an `x` channel (number, duration, date or date-time), a `y` channel (number or duration) and an optional `color` channel (category or boolean), with one series per colour value and each series' points joined in ascending x order.
2. If two rows of one series share an x value, then the chart kit shall refuse a `line` or `area` chart with a problem naming the series and the x value.
3. Where a request asks for it, the chart kit shall draw a `line` chart with a logarithmic x or y axis, or with zero included in the y axis.
4. The chart kit shall draw an `area` chart from the same channels as `line`, filling each series to zero, translucent where series overlap.
5. Where a request asks for stacking, the chart kit shall stack `area` series in legend order, and if a stacked area has a negative value then it shall refuse the chart with a problem.

### Requirement 13: Bar and Horizontal Bar Kinds
**Objective:** As an athlete, I want weekly totals as bars and rankings as
horizontal bars, so that I can compare periods and categories.

#### Acceptance Criteria
1. The chart kit shall draw a `bar` chart from an `x` channel (category, date or boolean), a `y` channel (number or duration) and an optional `color` channel (category or boolean), with series side by side within each x position unless the request asks for stacking.
2. The chart kit shall extend `bar` values below zero for negative values, and if a stacked `bar` chart has a negative value then it shall refuse the chart with a problem.
3. If two rows share both an x value and a colour value, then the chart kit shall refuse a `bar` chart with a problem naming them.
4. The chart kit shall draw an `hbar` chart from a `y` channel (category, date or boolean) and an `x` channel (number or duration), one bar per row, ranked by value from largest to smallest with ties kept in row order and absent values last, unless the request asks for row order.
5. The chart kit shall label each `hbar` bar with its formatted value, and a bar whose value is absent with an em dash.

### Requirement 14: Scatter and Histogram Kinds
**Objective:** As an athlete asking how two quantities relate, or how one is
distributed, I want scatter plots with an optional trend line and histograms
binned by a stated rule, so that I can see relationships and spreads.

#### Acceptance Criteria
1. The chart kit shall draw a `scatter` chart from an `x` channel (number, duration, date or date-time), a `y` channel (number or duration) and an optional `color` channel (category or boolean), one point per row, each series with its own marker shape.
2. Where a request asks for a trend line, the chart kit shall draw, for each series with at least two distinct x values, the least-squares line over that series' drawn points across its x range, and shall state on the chart which series have too few points for one.
3. If a trend line is requested together with a logarithmic axis, then the chart kit shall refuse the request with a problem.
4. The chart kit shall draw a `histogram` from one `x` channel (number or duration), counting values into contiguous, equal-width bins by a stated default rule, or by a requested bin count or bin width, and shall draw the count of each bin.
5. If a request gives both a bin count and a bin width, or a binning that yields more bins than the kind's bound, then the chart kit shall refuse it with a problem.

### Requirement 15: Stat and Table Kinds
**Objective:** As an athlete, I want a headline number with its change and a
small formatted table as plain markdown, so that they read in any viewer and an
agent can read the numbers directly.

#### Acceptance Criteria
1. The chart kit shall render a `stat` as a markdown fragment carrying the title and the formatted value of its `value` channel with its unit.
2. Where a `compare` channel is bound, the chart kit shall add the difference between the value and the comparison, with an explicit sign and the value's unit, and optionally the percentage change, as the request asks.
3. If a `stat` chart receives more than one row, then the chart kit shall refuse it with a problem.
4. When a `stat` chart receives no row or an absent value, the chart kit shall show an em dash in place of the value, and when its comparison is absent, an em dash in place of the difference.
5. The chart kit shall render a `table` as a markdown table of every column in column order, with headers carrying each column's label and unit symbol, cells formatted by unit, numbers right-aligned, and cell text escaped so that no value can break the table.
6. If a `table` has more rows or columns than its bound, then the chart kit shall refuse it with a problem; when it has no rows, it shall render its header followed by a "No data" line.

### Requirement 16: Determinism and Purity
**Objective:** As an athlete whose wiki is backed by git and iCloud, I want the
same data to produce the same bytes, so that a refresh with no new data changes
no file.

#### Acceptance Criteria
1. When given an identical chart request and identical data, the chart kit shall produce byte-identical output across runs, processes, machines, locales, timezones and hash seeds.
2. The chart kit shall produce output that does not depend on the order in which a request lists its channel bindings or options.
3. The chart kit shall read no clock, use no randomness, generate no identifiers, read no environment variable, and perform no file or network access.
4. The chart kit shall use the standard library only and shall import nothing from the analytics index, the query layer, dashboards, the activity model or FIT ingest.

### Requirement 17: Existing Charts and Primitives Preserved
**Objective:** As a maintainer, I want the kit to leave every existing chart
exactly as it is, so that no workout or history page changes because the kit
exists.

#### Acceptance Criteria
1. The chart kit shall leave the hero, calendar, zone-strip and map renderers, and every chart they produce, byte-identical.
2. The chart kit shall leave the behaviour of the shared SVG, series and palette primitives unchanged, and shall document where their presentation-attribute rule is stated the one relaxation it makes: one embedded style element per kit chart.
3. The chart kit shall add no runtime dependency.

### Requirement 18: Evidence That the Charts Are Pinned
**Objective:** As a maintainer, I want every chart behaviour pinned by tests
that can fail, so that a later change to the kit cannot silently restyle or
corrupt charts.

#### Acceptance Criteria
1. The fitdocs test suite shall hold byte goldens for each SVG kind covering typical data with an absent value, no rows, all values absent, a single point, negative values where the kind allows them, long labels, and data exactly at the mark bound.
2. The fitdocs test suite shall hold goldens for the `stat` and `table` kinds covering a present value, a comparison, absent values, no rows and long or special-character text.
3. The fitdocs test suite shall fail when any golden differs from the rendered output by a single byte, and each golden shall be shown able to fail by a named mutation of the kit's code.
4. The fitdocs test suite shall compute the contrast of every ink and the distances between palette colours from the shipped values independently of the kit's own code, and shall fail if any falls below its stated minimum.
5. The fitdocs test suite shall fail if a kit module imports outside the standard library and the shared chart primitives, imports any of the analytics index, query layer, dashboards, activity model or FIT ingest, or reads a clock; and each such guard shall carry a positive control showing it detects a violation.

## Amendment 1 (2026-10-13): Wellness units, landed by wellness-store

The shared `fitdocs.units.UNITS` vocabulary appends two QUANTITY rows:
`ml_per_kg_min` (millilitres per kilogram per minute, `mL/kg/min`, one decimal)
and `brpm` (breaths per minute, `br/min`, one decimal). The preceding 19 rows
retain their values and order. The chart kit and analytics-index suffix
projection continue to consume this single vocabulary.
