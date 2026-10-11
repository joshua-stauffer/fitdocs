# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete whose LLM assistant writes dashboard pages
in their wiki (Phase 11, `dashboards`) and asks questions of the analytics
index that the eight core chart kinds of `chart-kit` (line, area, bar, hbar,
scatter, histogram, stat, table) cannot show: which days of the year they
trained and how hard; how their zone distribution shifted week by week; two
quantities in different units over one time axis; the spread of a value, not
just its average; best-effort curves over a log duration axis; and many small
series at once.

**Current situation.** `chart-kit` provides a typed data contract, scales,
ticks, unit-aware labels, axes, a legend, one light/dark theme, a declared
append-only kind registry with structured validation, and mark bounds. Its
kinds cover comparison and trend only. The existing calendar chart is a daily
multi-line chart, not a heatmap, and stays untouched.

**What should change.** Eight more kinds are appended to chart-kit's registry,
each a thin module over the shared layer with its own encoding schema, mark
bound, goldens and named mutations: `calendar-heatmap`, `heatmap`,
`dual-axis`, `band`, `box`, `mean-max`, `small-multiples` and `stacked-100`.
They validate, render, theme and bound exactly as the core kinds do. Absent
data is never drawn as zero, and a heatmap cell with no value differs visibly
from a cell whose value is zero, in both themes and for colour-blind viewers.
Any shared-layer addition a kind proves it needs is appended, never edited.
Whichever of `dashboards` and `chart-catalog` lands second updates every
listing or count of registered kinds.

Source: `.kiro/specs/chart-catalog/brief.md`; Phase 11 of
`.kiro/steering/roadmap.md`. Dependencies: `chart-kit`. Parallel with
`dashboards`.

## Introduction

The chart catalog adds eight chart shapes to the chart kit. A caller (in
Phase 11, the `dashboards` pass) names one of them in a chart request, binds
the columns of a result table to its channels, and gets back an SVG image or a
list of problems, exactly as for a core kind. Every term defined in
`chart-kit`'s requirements (column, value kind, unit token, kind, channel,
option, chart request, mark, problem, reference backgrounds, ink, decorative)
keeps its meaning here. Further terms:

- The **chart catalog** is the eight kinds this feature appends and the
  shared-layer additions they need. Once appended, they are part of the chart
  kit.
- The **grid kinds** are `calendar-heatmap` and `heatmap`. A **cell** is one
  row drawn at its position in a grid kind.
- A **value class** is the class a grid cell's value falls in: **absent** (no
  value), **zero**, or one **bin**: a value range above zero that excludes its
  lower edge and includes its upper edge.
- A **missing row** is a position for which the data holds no row at all. It
  is different from a row whose value is absent: chart-kit draws the rows it
  is given and never invents one.
- A **panel** is one small chart in `small-multiples`; a **facet value** is
  the value that names it. A **part** is one colour value of a
  `stacked-100` bar. A **period** is one colour value of a `mean-max` chart.

## Boundary Context

- **In scope**: the eight kinds, each with its channels, options, mark bound,
  absent-data rules, degenerate-input rules, goldens and named mutations; the
  shared-layer additions they need (a binned sequential value scale with its
  cell marks and legend, a sequential colour ramp, and new problem codes),
  each appended without changing a core kind's behaviour or output; updating
  the published kinds listing and kind counts if `dashboards` lands first; a
  release-note line.
- **Out of scope**: dashboard pages, directives, SQL, snapshots, refresh and
  the `fitdocs dashboard` command (`dashboards`); the core kinds and the
  shared layer's existing behaviour (`chart-kit`); pie, donut and map charts;
  interactive or JavaScript output; a diverging (signed) colour scale; the
  hero, calendar, zone-strip and map renderers, which stay byte-identical and
  are not moved onto the kit; a mean-max section in workout documents;
  computing quantiles, best efforts or any other aggregate from records.
- **Adjacent expectations**: `chart-kit` supplies the data contract, request
  and problem shapes, registry, validation pipeline, scales, ticks, unit
  formatting, theme, layout, frame, marks and series helpers, and its tests
  find appended kinds by its test-module naming convention. `dashboards`
  lists and renders whatever is registered; the listing it publishes in its
  documentation is pinned against the registry, and whichever of the two
  features lands second brings it up to date. The analytics index's tables
  (`daily_load`, `weekly_load`, `zone_times`, `mean_max`, `blocks`) are what
  these kinds are shaped for, but the kinds take typed columns, never table
  names.

## Requirements

### Requirement 1: Catalog Registration
**Objective:** As the `dashboards` feature and the athlete's assistant, I want
eight more kinds in the same registry with the same contract as the core
kinds, so that a page can name any of them and get the same validation and
rendering guarantees.

#### Acceptance Criteria
1. The chart catalog shall append to the chart kit's registry, after the core kinds and in this order, the kinds `calendar-heatmap`, `heatmap`, `dual-axis`, `band`, `box`, `mean-max`, `small-multiples` and `stacked-100`.
2. The chart catalog shall declare for each kind its name, a one-line description, its output (an SVG image), its channels, its options, its mark bound and how it treats data over that bound, and its maximum number of colour series where it has a colour channel, so that the registry's machine-readable description lists each catalog kind as it lists a core kind.
3. When a chart request names a catalog kind, the chart kit shall validate it against column descriptions alone, check its data, check its shape and render it through the same pipeline and with the same problem structure as a core kind.
4. The chart catalog shall leave every core kind's declaration, validation and output byte-identical.
5. The chart catalog shall keep each published kind, channel and option name, and each problem code it adds, fixed in name and meaning, so that dashboard pages and callers can rely on them.
6. The chart catalog shall provide no pie, donut or map kind and no interactive output.

### Requirement 2: Guarantees Shared With the Core Kinds
**Objective:** As an athlete reading any chart in the wiki, I want the new
kinds to keep every promise the core kinds make, so that a catalog chart is as
trustworthy and readable as a line chart.

#### Acceptance Criteria
1. The chart catalog shall draw every catalog kind through the chart kit's one theme mechanism: a transparent background, every ink at least 3:1 against each of the four reference backgrounds as drawn, the embedded style element, and no kind-specific text, axis or gridline colour.
2. The chart catalog shall never make colour the only carrier of meaning: every value class, series, axis side or part that a catalog kind distinguishes by colour shall also be distinguished by size, shape, dash pattern, position matched to the legend order, or text.
3. The chart catalog shall never draw an absent value as zero, and shall never substitute zero, a default or an interpolated value for an absent value.
4. When a catalog chart has no rows, the chart catalog shall draw the chart kit's no-data state at the kind's normal size.
5. When a catalog chart has rows but none of them leaves a mark (a grid kind marks a row whose value is absent with a cross, so for the grid kinds this means that no row can be placed), the chart catalog shall draw the chart kit's no-data state stating that the rows hold no values.
6. When a row cannot be placed because a value the kind needs to position it is absent, the chart catalog shall state on the chart and in its description how many rows are not drawn and for which channel.
7. When a category, colour or facet value is absent, the chart catalog shall show those rows as their own category, series or panel labelled with an em dash and ordered last.
8. The chart catalog shall state a mark bound for every catalog kind, and shall draw a chart whose count equals the bound.
9. If a catalog chart exceeds its kind's mark bound, then the chart catalog shall refuse the chart with a problem naming the bound, the count and how to reduce the data.
10. The chart catalog shall give every catalog chart the chart kit's accessibility metadata: the image role, a title element, and a description naming the kind, each bound channel's label and unit, the number of rows, the rows not drawn and each axis or value range.
11. The chart catalog shall produce byte-identical output for an identical request and identical data across runs, processes, machines, locales, timezones and hash seeds, and independently of the order in which a request lists its bindings or options.
12. The chart catalog shall read no clock, use no randomness, generate no identifiers, read no environment variable, perform no file or network access, use the standard library only, and import nothing from the analytics index, the query layer, dashboards, the activity model or FIT ingest.
13. The chart catalog shall draw the rows it is given and shall compute no aggregate from them (no quantile, no best effort, no total across rows), except that `stacked-100` divides each part by its own bar's total.

### Requirement 3: Binned Value Scale for the Grid Kinds
**Objective:** As an athlete scanning a year of training or a zone-by-week
grid, I want each cell's size and shade to show how much, and a cell with no
value to look different from a cell whose value is zero, so that I never read
a gap in my data as a rest day.

#### Acceptance Criteria
1. The chart catalog shall classify each cell of a grid kind as absent, zero, or exactly one of at most five bins above zero, each bin excluding its lower edge and including its upper edge, so that zero never shares a value class with a positive value.
2. The chart catalog shall place the bin edges at round values from zero up to the nearest round value at or above the largest present value: multiples of 1, 2 or 5 times a power of ten for numbers, steps of the chart kit's duration ladder for durations (including numbers in seconds), and whole-number steps when every present value is a whole number.
3. The chart catalog shall draw each binned cell as a filled square, centred in its cell, whose area grows with the bin and whose colour steps along one sequential ramp, so that magnitude is carried by size as well as by colour.
4. The chart catalog shall draw each zero cell as an unfilled outlined square and each absent cell as a cross, both in inks that reach at least 3:1 against each reference background, so that absent, zero and the smallest bin differ in shape in both themes and for colour-blind viewers.
5. The chart catalog shall draw nothing at a grid position for which there is a missing row, so that a missing row, an absent value and a zero value each look different.
6. The chart catalog shall draw a scale legend that names the value's label and unit, gives one entry per bin labelled with its upper edge, and gives an entry for zero cells and one for absent cells when the chart holds any, each entry showing the mark it describes.
7. If a grid kind's value holds a negative value, then the chart catalog shall refuse the chart with a problem naming the column, the first offending row and the number of offending rows, whose fix names an unsigned chart kind or a query that removes the sign.
8. When no present value is above zero, the chart catalog shall draw the zero and absent cells and a scale legend without bins.
9. The chart catalog shall colour the bins from one sequential ramp of a stated size, in which each colour is derived from a stated oklch source, reaches at least 3:1 against each reference background, and steps monotonically in lightness and in chroma, with adjacent colours separated by at least a stated perceptual distance under normal vision and under simulated protanopia, deuteranopia and tritanopia.

### Requirement 4: Calendar Heatmap Kind
**Objective:** As an athlete, I want a year of daily load or volume as one
cell per day in week columns, so that I can see consistency and intensity at a
glance.

#### Acceptance Criteria
1. The chart catalog shall draw a `calendar-heatmap` from a `date` channel (date) and a `value` channel (number or duration), one cell per row in a grid of Monday-start week columns ordered left to right in time, with Monday at the top and Sunday at the bottom of each column.
2. The chart catalog shall span the calendar from the Monday on or before the earliest present date to the Sunday on or after the latest present date, label the Monday, Wednesday, Friday and Sunday rows, and label the date axis with the chart kit's date tick rules.
3. If two rows share a date, then the chart catalog shall refuse the chart with a problem naming the date and the first duplicate row.
4. If the present dates span more than the kind's stated number of week columns, then the chart catalog shall refuse the chart with a problem naming the limit, the number of week columns and how to narrow the dates; a span of exactly the stated number renders.
5. The chart catalog shall size the calendar's cells from the chart's width and its number of week columns, never above a stated largest cell, and shall size the chart's height to its seven rows unless the request sets a height.
6. When the present dates fall on a single day, or every present value is equal, the chart catalog shall draw the cells at their normal size with a scale legend whose bins enclose the value, never a collapsed or zero-width grid.

### Requirement 5: Heatmap Kind
**Objective:** As an athlete, I want a value over two axes (zone by week,
weekday by hour), so that I can see how a distribution shifts.

#### Acceptance Criteria
1. The chart catalog shall draw a `heatmap` from an `x` channel and a `y` channel (each category, date, boolean or number) and a `value` channel (number or duration), one cell per row at its x and y position.
2. The chart catalog shall order heatmap categories and booleans by their first appearance, and dates and numbers in ascending order, with an absent x or y value forming its own last column or row labelled with an em dash.
3. If two rows share both an x value and a y value, then the chart catalog shall refuse the chart with a problem naming the values and the first duplicate row.
4. If a heatmap has more than its stated number of cells, of distinct x values or of distinct y values, then the chart catalog shall refuse the chart with a problem naming which limit, the limit and the count; data exactly at each limit renders.
5. The chart catalog shall label every heatmap column and row whose label fits its extent, and otherwise every k-th column or row counting from the first, with the smallest k that fits.
6. The chart catalog shall size the heatmap's height to its number of rows unless the request sets a height.

### Requirement 6: Dual-Axis Kind
**Objective:** As an athlete, I want two quantities in different units over one
time axis, each on its own scale, so that neither is flattened, without ever
misreading which line belongs to which axis.

#### Acceptance Criteria
1. The chart catalog shall draw a `dual-axis` chart from an `x` channel (number, duration, date or date-time), a `y` channel (number or duration) drawn against the left axis and a `y2` channel (number or duration) drawn against the right axis, each series joined in ascending x order.
2. The chart catalog shall give each value axis its own scale, ticks and axis title carrying its own column's label and unit, and shall draw gridlines for the left axis only.
3. The chart catalog shall distinguish the two series by dash pattern as well as by colour, and shall name each series in the legend together with the side of the axis it is drawn against.
4. If `y` and `y2` are bound to the same column, or to columns with the same unit (two durations count as the same unit), then the chart catalog shall refuse the request with a problem whose fix names the `line` kind with a colour column.
5. When a series has an absent value, the chart catalog shall break that series alone at that row, and shall draw a point with no present neighbour as a dot.
6. If two rows share an x value, then the chart catalog shall refuse the chart with a problem naming the x value and the first duplicate row.
7. Where a request asks for it, the chart catalog shall include zero in the left axis, the right axis, or both.

### Requirement 7: Band Kind
**Objective:** As an athlete, I want the spread of a value (p10 to p90 around a
median, or minimum to maximum) over time, so that I see variability and not
just the average.

#### Acceptance Criteria
1. The chart catalog shall draw a `band` chart from an `x` channel (number, duration, date or date-time), a `low` and a `high` channel (number or duration) and an optional `mid` channel (number or duration), as a shaded band between outlined low and high edges, with a centre line for `mid`, in ascending x order.
2. If the `low`, `high` and `mid` columns differ in value kind or unit, then the chart catalog shall refuse the request with a problem naming the columns and their units.
3. If a row's present low value exceeds its present high value, then the chart catalog shall refuse the chart with a problem naming the row, both values and a fix that swaps the bindings or corrects the query.
4. When a row's low or high value is absent, the chart catalog shall break the band at that row, and shall draw an x position whose band has no present neighbour as a vertical line from low to high.
5. When a row's mid value is absent, the chart catalog shall break the centre line alone at that row, and shall draw a centre point with no present neighbour as a dot.
6. If two rows share an x value, then the chart catalog shall refuse the chart with a problem naming the x value and the first duplicate row.
7. The chart catalog shall name the band and the centre line in the legend, each with a swatch of its own shape.

### Requirement 8: Box Kind
**Objective:** As an athlete, I want a box-and-whisker per week or block from
quartiles my query computed, so that I can compare distributions side by side.

#### Acceptance Criteria
1. The chart catalog shall draw a `box` chart from an `x` channel (category, date or boolean) and five value channels `low`, `q1`, `median`, `q3` and `high` (number or duration), one box-and-whisker per row drawn from the values given, computing no quantile itself.
2. If the five value columns differ in value kind or unit, then the chart catalog shall refuse the request with a problem naming the columns and their units.
3. If a row's present values are not in the order low ≤ q1 ≤ median ≤ q3 ≤ high, then the chart catalog shall refuse the chart with a problem naming the row and the first pair out of order.
4. When a row's `q1`, `median` or `q3` value is absent, the chart catalog shall draw no box for it, keep its labelled position, and count it as not drawn.
5. When a row's `low` or `high` value is absent, the chart catalog shall draw its box without that whisker and state on the chart how many whiskers are not drawn.
6. The chart catalog shall end each drawn whisker with a cap, so that a whisker of zero length differs visibly from an absent one.
7. If two rows share an x value, then the chart catalog shall refuse the chart with a problem naming the x value and the first duplicate row.

### Requirement 9: Mean-Max Kind
**Objective:** As an athlete, I want best-effort curves (power or pace against
duration) on a log duration axis, this season against last, so that I can see
where my fitness changed.

#### Acceptance Criteria
1. The chart catalog shall draw a `mean-max` chart from an `x` channel holding durations (a duration, or a number in seconds), a `y` channel (number or duration) and an optional `color` channel (category or boolean) naming the period, one curve per period joined in ascending duration on a logarithmic duration axis.
2. If the `x` channel is bound to a number column whose unit is not seconds, then the chart catalog shall refuse the request with a problem naming the channel and the columns that would fit.
3. The chart catalog shall place x ticks only at durations from the chart kit's log-duration ladder, labelled as durations, and shall label 5 s, 1 min, 5 min, 20 min and 1 h before any other duration whenever they lie inside the axis and their labels fit.
4. If a present duration is zero or negative, then the chart catalog shall refuse the chart with a problem naming the column and the first offending row.
5. If two rows of one period share a duration, then the chart catalog shall refuse the chart with a problem naming the period, the duration and the first duplicate row.
6. When a row's y value is absent, the chart catalog shall break that period's curve at that row, and shall draw a point with no present neighbour as a dot.
7. The chart catalog shall draw the y axis linearly and not inverted for pace, and where a request asks for it, include zero.

### Requirement 10: Small-Multiples Kind
**Objective:** As an athlete, I want one small line chart per shoe, block or
sport, so that I can compare many short series without a tangle of lines.

#### Acceptance Criteria
1. The chart catalog shall draw a `small-multiples` chart from an `x` channel (number, duration, date or date-time), a `y` channel (number or duration) and a `facet` channel (category, boolean or date), one panel per facet value in facet order (first appearance for categories and booleans, ascending for dates, an absent facet value last), laid out left to right and top to bottom.
2. The chart catalog shall draw every panel against one shared x scale, and against one shared y scale unless the request asks for independent y scales, labelling a shared axis once per row or column of panels and an independent y axis in every panel.
3. The chart catalog shall title each panel with its facet value and draw every panel's line in the same style, so that the title, not colour, identifies the panel.
4. When a panel has no drawable value, the chart catalog shall draw the panel with its title and a visible message that it holds no values, never omit it.
5. If a chart has more panels or more rows than the kind's stated limits, then the chart catalog shall refuse the chart with a problem naming which limit, the limit and the count; data exactly at each limit renders.
6. Where a request sets the number of panel columns, the chart catalog shall lay the panels out in that many columns, and otherwise in a stated number derived from the chart's width and panel count.
7. If two rows of one facet value share an x value, then the chart catalog shall refuse the chart with a problem naming the facet value, the x value and the first duplicate row.

### Requirement 11: Stacked-100 Kind
**Objective:** As an athlete, I want each week's zone time as shares of 100%,
so that I can see composition shift independently of volume.

#### Acceptance Criteria
1. The chart catalog shall draw a `stacked-100` chart from an `x` channel (category, date or boolean), a `y` channel (number or duration) and a required `color` channel (category or boolean), one bar per x value in which each part's height is its share of that bar's total, stacked bottom to top in legend order, on an axis from 0% to 100%.
2. If a part's value is absent, then the chart catalog shall refuse the chart with a problem whose fix names supplying the missing value or using an unstacked bar chart.
3. If a part's value is negative, then the chart catalog shall refuse the chart with a problem naming the row.
4. When every part of a bar is zero, the chart catalog shall draw no shares for that bar, mark its position with the chart kit's zero stub, and state on the chart how many bars have a zero total, never drawing a fabricated split.
5. When the data holds no row for one part at one x value, the chart catalog shall draw no segment for that part in that bar and refuse nothing.
6. If two rows share both an x value and a colour value, then the chart catalog shall refuse the chart with a problem naming them.
7. The chart catalog shall separate adjacent segments of a bar with a visible gap, so that segment boundaries do not depend on colour alone.

### Requirement 12: Evidence That the Catalog Is Pinned
**Objective:** As a maintainer, I want every catalog behaviour pinned by tests
that can fail, so that a later change to the kit or a kind cannot silently
restyle or corrupt a catalog chart.

#### Acceptance Criteria
1. The fitdocs test suite shall hold byte goldens for each catalog kind covering typical data with an absent value, no rows, all values absent where the kind draws that state, a single point, negative values where the kind allows them, long labels, data exactly at the mark bound, and each distinction its kind's requirement names.
2. The fitdocs test suite shall hold one golden per case for both themes, and shall check every catalog golden with the chart kit's theme coverage rules, including the ramp colours in the allowed colours.
3. The fitdocs test suite shall fail when any catalog golden differs from the rendered output by a single byte, and each golden shall be shown able to fail by a named mutation of production code.
4. The fitdocs test suite shall state a byte budget for a typical chart of each catalog kind and fail if any exceeds its budget, and shall fail if a catalog chart drawn at its kind's mark bound exceeds the chart kit's at-bound ceiling.
5. The fitdocs test suite shall compute the contrast and perceptual distances of the sequential ramp independently of the kit's own code and fail if any falls below its stated minimum.
6. The fitdocs test suite shall apply the chart kit's import, purity and determinism guards to every catalog module and kind, each with a positive control.
7. The fitdocs test suite shall fail if any core kind's golden or any of the hero, calendar, zone-strip or map renderers' goldens changes.

### Requirement 13: Landing Beside Dashboards
**Objective:** As a maintainer landing `dashboards` and `chart-catalog` in
either order, I want the published kinds listing and every kind count to be
right after both have landed, so that no document or test is stale.

#### Acceptance Criteria
1. When `chart-catalog` lands after `dashboards`, the chart catalog shall bring every published listing and every pinned count of registered kinds owned by `dashboards` up to date against the registry, so that the listing names all sixteen kinds in registration order.
2. When `chart-catalog` lands before `dashboards`, the chart catalog shall change no file that `dashboards` owns.
3. The chart catalog shall add a release-note entry naming the eight kinds as available to dashboard charts.
