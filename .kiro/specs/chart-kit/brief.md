# Brief: chart-kit

## Problem

Phase 11 puts charts of analytics results onto wiki pages (`dashboards`).
Those charts can show any column an agent selects, in any of a dozen shapes,
in light or dark themes. Today fitdocs can draw four purpose-built charts and
nothing else:

- **The renderers aren't generic.** The hero chart (`render/charts/hero.py`),
  the calendar chart (`calendar.py`), the zone strip (`zones.py`) and the
  route map (`map.py`) each take a spec shaped for one page. None accepts
  "these columns, this encoding".
- **There is no shared axis layer.** Margins, plot rectangles, x/y scale
  mapping, tick generation, legends and font sizes are duplicated in each
  module (compare `hero.py:103-158` with `calendar.py:114-156`). There is no
  "nice number" tick algorithm: the hero chart uses six evenly spaced ticks
  (`hero.py:112`), the calendar chart uses Jan-1 ticks.
- **There is no theming.** Text and axis colours are hard-coded dark greys
  (`hero.py:117-119`, `calendar.py:133-148`, `zones.py:81`), so every chart
  assumes a light background. The docs site works around this with a fixed
  light card behind its hero image (`website/brand.css:352-363`).
- **There are no units.** Ticks are bare numbers. A pace axis computed from
  `_mps` shows metres per second, not min/km.

## Current State

- Shared primitives exist and are worth keeping:
  - `render/charts/svg.py`: `fmt_num` (fixed two decimals, `-0` normalised,
    :42), `el` (caller-ordered, escaped attributes, :92), `text` (:81),
    `svg_document` (:117).
  - `render/charts/series.py`: `gap_segments`, `paired_gap_segments`. `None`
    breaks a line and is never interpolated.
  - `render/charts/palette.py`: sRGB hex constants with their oklch source,
    checked by a test that reimplements the conversion.
- Determinism is by construction (no ids, no clock, fixed attribute order,
  `fmt_num` everywhere) and pinned by byte goldens under
  `tests/render/charts/golden/`, `tests/render/golden_docs/`,
  `tests/history/golden/`.
- `render/charts/__init__.py:3-5` already states the rule this spec extends:
  chart modules take plain values only, with no `Activity` and no ingest
  imports.
- Text width is a fixed per-character estimate (`hero.py:127`,
  `map.py:97`).

## Desired Outcome

A pure, stdlib-only chart kit that turns **typed columns plus a named
encoding** into either a byte-deterministic SVG or a markdown fragment:

1. **A typed data contract.** An ordered set of columns, each with a value
   kind (number, date, datetime, duration, category, boolean), an optional
   unit token and a label, and rows in which `None` means absent. The kit
   never turns `None` into `0`.
2. **A shared layer.**
   - Scales: linear, log, date, category.
   - Nice-number ticks.
   - Unit-aware tick and value labels: pace in min/km from metres per
     second, h:mm:ss from seconds, dates, percentages. These are locale-free.
   - Axes, gridlines and a legend.
   - Plot-area layout that budgets space for labels using the existing
     character-width estimate.
   - A light/dark theme, using the mechanism this phase's viability check
     settled (see Constraints).
   - Every SVG carries `<title>`/`<desc>` for accessibility.
3. **A kind registry.** Each kind declares its name, a one-line description,
   its encoding channels (required and optional, with the column kinds each
   accepts), its output (SVG or markdown) and its render function. The
   registry is declared, not scanned, like `PACKAGED_SKILLS`. `chart-catalog`
   appends to it, and `dashboards` lists it.
4. **Validation an agent can act on.** Encoding a column that doesn't exist,
   a channel given the wrong column kind, or a missing required channel each
   yields a structured error naming the chart, the channel and what would
   fix it. The kit never guesses.
5. **The core kinds.**
   - SVG:
     - `line`: one or more series over a date or numeric x, with series
       split by a colour column.
     - `area`, including stacked.
     - `bar`, vertical, grouped or stacked by a colour column.
     - `hbar`, ranked horizontal bars.
     - `scatter`, with an optional colour channel and an optional
       least-squares trend line.
     - `histogram`: the kit bins one numeric column by a stated rule.
   - Markdown:
     - `stat`: a KPI value with its unit and an optional delta against a
       comparison value.
     - `table`: rows with unit-aware formatting.
6. **Bounded output.** Each kind declares the most marks it will draw. Over
   that bound it refuses with an actionable error, or reduces by a rule the
   kind states (histogram binning, for example). It never silently drops
   rows. "As lightweight as possible" is measured: the spec states and tests
   a size budget for typical charts.

## Approach

**Named kinds over a shared layer** (maintainer, 2026-10-11). Each kind is a
thin module that maps its encodings onto the shared scales, axes and legend.
Picking a kind and mapping columns to channels is all an agent has to do.
This was chosen over a composable mark/encoding grammar, which is far larger
and gives an agent many more ways to write a valid but wrong spec, and over a
plotting dependency. `tech.md` keeps matplotlib out unless a spec proves the
need, and matplotlib emits large SVGs with text drawn as paths and random
ids.

The kit reuses `svg.py`, `series.py` and `palette.py`. It doesn't touch the
four existing renderers: their goldens stay byte-identical. Moving them onto
the shared layer, which would give workout charts dark mode, is a follow-on.

## Scope

- **In**:
  - the typed data contract;
  - scales, ticks, unit formatters, axes, legend, layout and theme;
  - the kind registry and its encoding schemas;
  - structured validation errors;
  - the eight core kinds;
  - mark bounds and the size budget;
  - accessibility metadata;
  - per-kind goldens: light/dark, empty, all-null, single point, negative
    values, long labels, mark-bound edge;
  - a machine-readable description of the registry (names, channels,
    descriptions) for `dashboards` to print;
  - boundary tests: stdlib-only, no clock, imports nothing from `index`,
    `query`, `dashboards`, `model` or `ingest`.
- **Out**:
  - the extended kinds (`chart-catalog`);
  - reading SQL or the index, and anything about pages, directives or
    refresh (`dashboards`);
  - changing the hero, calendar, zone-strip or map renderers;
  - JavaScript or interactive output;
  - a map kind (maps fetch tiles, which is network);
  - pie and donut charts (deliberately excluded).

## Boundary Candidates

- The **data contract and encoding schema**: the seam `dashboards` and
  `chart-catalog` both build on. Settle it in this spec's design, not after.
- The **kind registry**: append-only. `chart-catalog` adds kinds without
  editing core kinds.
- The **unit vocabulary**: the kit owns the formatting of each unit token.
  `dashboards` maps a result column to a token. See Shared seams in the
  roadmap.
- The **theme**: one mechanism shared by every kind.

## Out of Boundary

- Where a chart's data comes from, and where its file is written.
- Page structure, captions and the chart region (`dashboards`).
- Which kinds exist beyond the core eight (`chart-catalog`).

## Upstream / Downstream

- **Upstream**: none. It builds on `render/charts/svg.py`, `series.py` and
  `palette.py`.
- **Downstream**:
  - `dashboards` (renders every chart through the registry);
  - `chart-catalog` (registers eight more kinds);
  - follow-on: moving the existing workout and history charts onto the
    shared layer.

## Existing Spec Touchpoints

- **Extends**: none. The new modules sit beside the existing renderers in
  `fitdocs.render.charts`, or in a sibling package if the design says so.
- **Adjacent**:
  - `workout-docs` and `load-history` own the existing renderers and their
    goldens, which must stay byte-identical.
  - `route-maps` owns `map.py`.

## Constraints

- Stdlib only, with no new runtime dependency. `mypy --strict`, Python 3.11.
- Byte-deterministic for the same inputs: no ids, no clock, fixed attribute
  order, fixed number formatting.
- Absent data is `None`: a gap in a line, a missing bar, an em dash in a
  `stat` or table cell, never `0`. An empty data set renders an explicit
  no-data state.
- **Theme mechanism** (Phase 11 viability check, 2026-10-11; the evidence is
  in the roadmap, Phase 11 › Viability):
  - **Transparent background.**
  - **Base inks work in both themes.** Every ink set without a media query is
    mid-luminance and reaches at least 3:1 against `#ffffff`, `#1e1e1e`
    (Obsidian dark), `#0d1117` (GitHub dark) and `#1e2129` (Material
    slate). Those inks are what WebKit shows when it guesses the theme
    wrong.
  - **An embedded `<style>` raises contrast where the theme is known.** It
    uses `@media (prefers-color-scheme: dark)`, plus a light counterpart, to
    bring small text up to at least 4.5:1 wherever the query is honoured.
  - **Where the query is honoured.** It follows the embedding page's
    `color-scheme`: Obsidian desktop's own theme, GitHub's theme, and the
    docs site's palette toggle, in Chromium and Firefox.
  - **Where it isn't.** On Obsidian iOS and Safari it follows the system
    appearance at best (WebKit 199134 and 316640).
  - **`svg.py` rule relaxed for one `<style>` element.** This needs a
    deliberate relaxation of `svg.py`'s presentation-attributes-only rule,
    for that one element.
  - **Avoid** `light-dark()`, `currentColor` and `<picture>`, which don't
    help through `<img>`.
  - **Don't reuse the existing chart text and axis constants.** `#333333` is
    1.32:1 on `#1e1e1e`.
- No single grey reaches 4.5:1 on both white and `#1e1e1e`; the best,
  `#7f7f7f`, manages about 4.0. Small text relies on the media query, or the
  design uses text large enough for 3:1.
- Colour is never the only carrier of meaning. The palette is
  colour-blind-safe and comes from oklch sources the way `palette.py` does.
- Every new assertion owes a named mutation it dies on
  (`change-protocol.md` § Fixture Discrimination).
