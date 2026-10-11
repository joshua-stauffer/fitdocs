# Brief: chart-catalog

## Problem

`chart-kit`'s eight core kinds cover comparison and trend: line, area, bar,
hbar, scatter, histogram, stat and table. Several questions the athlete
actually asks of the analytics index need shapes the core doesn't have:

- **Consistency over a year.** Which days did I train, and how hard? This
  needs a GitHub-style calendar heatmap of daily load or volume.
- **Composition over time.** How did my zone distribution shift week by
  week? This needs a 100% stacked bar, or a zone × week heatmap.
- **Two quantities with different units on one time axis.** Pace and HR
  across a block, where one shared y-axis flattens one of them.
- **Spread, not just the average.** Weekly HR at steady pace, as a
  p10–p90 band around a median, or a box per block.
- **Best-effort curves.** Mean-max power or pace over a log duration axis,
  this season against last. `analytics-derived` already writes the
  `mean_max` table this would draw.
- **Many small series at once.** One mini line per shoe, per block or per
  sport.

## Current State

- `chart-kit` (upstream, this phase) provides the typed data contract,
  scales (linear, log, date, category), ticks, unit formatters, axes,
  legend, theme, the declared kind registry, validation and mark bounds.
- The existing calendar chart (`render/charts/calendar.py`) is a daily
  multi-line chart, not a heatmap, and is untouched by this spec.
- `analytics-derived` tables that these kinds are shaped for:
  - `mean_max`;
  - `daily_load` (`index/derived/load_series.py:68`);
  - `weekly_load` (`:112`);
  - `zone_times` (`index/core/computed.py:228`);
  - `blocks` and `mesocycles`.

## Desired Outcome

Eight more kinds, each registered through chart-kit's registry. Each
declares its encodings, mark bound and output, and each validates and
renders with the same guarantees as the core kinds:

1. `calendar-heatmap`: one cell per day in week columns, with a colour scale
   over a value and absent days distinct from zero days.
2. `heatmap`: two category or date axes against a value, such as zone ×
   week or weekday × hour.
3. `dual-axis`: two series over a shared x with independent y scales, each
   axis labelled in its own unit and colour.
4. `band`: a low/high band with an optional centre line (p10–p90 plus
   median, or min–max).
5. `box`: a box-and-whisker per category, from precomputed quartiles or
   from raw values binned by the kit (the design picks one and states it).
6. `mean-max`: duration on a log x axis with ticks at familiar durations
   (5 s, 1 min, 5 min, 20 min, 1 h), one curve per period, in a power or
   pace unit.
7. `small-multiples`: a grid of mini line charts, one per category, on
   shared or independent scales as the encoding says.
8. `stacked-100`: composition bars that sum to 100%, by a colour column.

The design decides the exact names. Once a name is in the registry it's an
interface: dashboards pages reference it.

## Approach

**Kinds as thin modules over chart-kit's shared layer** (maintainer,
2026-10-11). Nothing new in the shared layer unless a kind proves the need.
If one does (a sequential colour scale for heatmaps, say), the addition goes
into chart-kit's modules through this spec, as an append-only extension, and
the design records it.

## Scope

- **In**:
  - the eight kinds, with their encoding schemas, mark bounds, goldens
    (light/dark, empty, all-null, single point, mark-bound edge) and named
    mutations;
  - any shared-layer addition a kind needs, appended;
  - the docs listing of kinds, if `dashboards` has landed first (see
    Constraints).
- **Out**:
  - pages, directives, SQL, refresh (`dashboards`);
  - the core eight kinds (`chart-kit`);
  - a map kind (network);
  - pie and donut;
  - interactive output.

## Boundary Candidates

- One kind per module, registered in chart-kit's declared registry.
  Append-only, so it never edits a core kind.
- Shared-layer additions (sequential and diverging colour scales, the log
  duration ticks) as named, separately tested extensions.

## Out of Boundary

- How a dashboard chooses or validates a kind beyond the encoding schema
  the kind declares.
- Where chart files go, and any data access.

## Upstream / Downstream

- **Upstream**: `chart-kit`.
- **Downstream**: `dashboards` lists and renders whatever is registered,
  and later pages may use these kinds outside dashboards (follow-on).

## Existing Spec Touchpoints

- **Extends**: `chart-kit` (registry entries, and shared-layer additions if
  proven necessary). It runs in parallel with `dashboards`.
- **Adjacent**: `analytics-derived`, whose `mean_max`, `daily_load`,
  `weekly_load` and `zone_times` tables are what these kinds are shaped
  for. The kinds take typed columns, not table names.

## Constraints

- Every chart-kit constraint applies: stdlib only, byte-deterministic,
  `None` never drawn as zero, the theme mechanism recorded in the roadmap,
  colour never the sole carrier, and the mark bounds.
- A heatmap or calendar cell with no value is visibly different from a cell
  whose value is zero.
- **Second-lander duty**, shared with `dashboards`. Whichever of the two
  lands second updates every count or listing of registered kinds:
  - any registry-count guard;
  - the kinds block in `docs/dashboards.md`, pinned live against the
    registry;
  - the skill's worked examples, if they name kinds.

  This is the analytics-query/analytics-derived arrangement from Phase 10.
