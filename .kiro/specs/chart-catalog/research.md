# Research & Design Decisions: chart-catalog

## Summary
- **Feature**: `chart-catalog`
- **Discovery Scope**: Extension. Eight kinds appended to `chart-kit`'s
  declared registry, plus the narrowest shared-layer additions they need.
  `chart-kit` is specified (design approved at `560f909`) but not yet
  implemented, so every seam below is read from its design § Settled Seams,
  Components and tasks.md, not from code.
- **How research ran**: one read-only `Explore` subagent surveyed the analytics
  index tables these kinds are shaped for (`mean_max`, `daily_load`,
  `weekly_load`, `zone_times`, `blocks`, `mesocycles`, `activities`) and the
  Python value types the query layer returns. In-context reading covered
  chart-kit's requirements, design, research and tasks in full, the Phase 11
  roadmap section, the steering files, the `dashboards` brief, the
  analytics-query and analytics-derived second-lander tasks, the calendar
  queue item, `palette.py` and `tests/render/charts/test_palette.py`. Three
  stdlib probes ran in the session scratchpad (`seq_ramp.py`,
  `seq_search.py`, `seq_pick.py`): contrast and OKLab arithmetic for candidate
  sequential ramps under the four reference backgrounds and Machado-2009
  simulation, a grid search over hue, lightness and chroma, and verification
  of the chosen ramp through the shipped `palette._oklch_to_hex`. The bundled
  `dataviz` skill's colour formula was read for sequential-ramp and dual-axis
  guidance. **Downgrade**: no WebSearch/WebFetch — the batch controller ruled
  the run network-free; WCAG contrast, Machado 2009 and OKLab are stable
  standards cited from knowledge, as chart-kit's research did.
- **Key Findings**:
  - Under chart-kit's theme rule (every ink at least 3:1 against `#ffffff`,
    `#1e1e1e`, `#0d1117` and `#1e2129` *as drawn*), a sequential colour ramp
    is confined to OKLab lightness of about 0.545–0.665. The best five-step
    ramp the search found separates adjacent steps by only about 0.05 OKLab
    (0.037 under tritanopia). Colour alone cannot carry magnitude in a
    heatmap; cell **area** must carry it, with colour as reinforcement.
  - A translucent ramp (one ink at stepped opacity) would give a real
    light-to-dark ramp in both themes for free, but its low steps fall far
    below 3:1 as drawn (25% of `#3284d0` over white is about 1.3:1), which
    chart-kit Requirement 8.2 forbids for an information-bearing mark.
  - chart-kit's settled seams cover almost every kind. Four small gaps were
    found: no public one-form duration labeller, no public builder for the
    `Not drawn:` note line, `band_scale`'s label-thinning rule measures width
    (so it fits horizontal axes only), and two behaviours the design does not
    pin (`frame.axis` title placement on `Side.RIGHT`, `marks.band_path`'s
    return shape). Each gets the narrowest append-only accommodation or an
    upstream check (§ Seam gaps).
  - The index's tables already fit the kinds: `daily_load` has one row per
    day with `recorded_load` 0 on rest days and `form` NULL when suppressed;
    `zone_times.zone` is an INTEGER, so `heatmap` axes must accept numbers;
    `mean_max.duration_s` is an INTEGER in seconds with 28 fixed durations
    from 1 s to 6 h.

## Research Log

### chart-kit's settled seams, as the catalog consumes them
- **Context**: the catalog is append-only over chart-kit; every name it uses
  must exist in chart-kit's design.
- **Sources Consulted**: `.kiro/specs/chart-kit/design.md` § Settled Seams,
  § Components (Formatter, Ticks, Scales, Theme, Layout, Frame, Marks,
  Cartesian, Validator, Kinds, Registry, Api), § Testing Strategy;
  `.kiro/specs/chart-kit/tasks.md` § Shared source files, § Cross-spec shared
  files, tasks 6.1–6.5; `.kiro/specs/chart-kit/research.md`.
- **Findings**:
  - Adding a kind is: a module `kit/kinds/<name>.py` exporting
    `KIND: Final[KindSpec]`, imported and appended to `KINDS` in
    `kit/registry.py`. Python modules cannot contain `-`, so a hyphenated
    kind's module uses `_` (`kinds/calendar_heatmap.py`), mirroring the test
    convention `test_<name with - as _>.py`.
  - `render_spec(spec, request, data)` runs the full pipeline for one
    `KindSpec` before it is registered, so each kind task can build and pin
    its kind independently of the registry.
  - The cross-cutting tests (registry round trip, theme coverage, determinism)
    iterate `KINDS` and find each kind's `CASES` and goldens by the test
    naming convention; an appended kind is covered unedited once registered.
  - Full pins that an appending spec re-pins in the same change:
    `test_boundary.py`'s hand-kept module tuple (checked against `rglob` both
    ways, `len >= 24`) and its layer-rank matrix; `test_theme_coverage.py`'s
    colour whitelist. Prefix pins (`KINDS`, `ProblemCode`, `INK_ROLES`,
    `CATEGORICAL_*`) stay green on append.
  - Hooks chart-kit names for the catalog: a second `numeric_scale` drawn
    with `frame.axis(..., Side.RIGHT, ...)` (dual axes), `marks.band_path`
    (bands), drawing into a `layout.Rect` (small multiples), the `ticks`
    duration ladder on log axes (mean-max), `cartesian.series_groups` and the
    stack helpers (stacked-100), and `integer=True` on `numeric_scale` and
    `linear_ticks` for count axes.
  - chart-kit's task 6.2 mutates shared modules to show each standard golden
    class red for every registered kind. It runs before the catalog's kinds
    exist, so the catalog must replay those mutations over its own goldens in
    a sequential task of its own.
  - `series_style(i)` requires `i < MAX_SERIES` (8). `small-multiples` allows
    up to 12 panels, so it cannot obtain panel identities from
    `series_groups`; it orders facets with `category_order` and draws every
    panel in `series_style(0)`.
- **Implications**: the catalog consumes chart-kit by exact names, appends
  where the brief allows, and owns the three re-pin points plus a sequential
  shared-mutation task (tasks.md group 3).

### Index tables the kinds are shaped for
- **Context**: the brief names `mean_max`, `daily_load`, `weekly_load`,
  `zone_times`, `blocks` and `mesocycles`. The kinds take typed columns, but
  their channels must fit what a query over these tables returns.
- **Sources Consulted** (Explore subagent): `src/fitdocs/index/derived/load_series.py:20-163`,
  `src/fitdocs/index/derived/mean_max.py:12-83`,
  `src/fitdocs/metrics/mean_max_sources.py:179-212`,
  `src/fitdocs/index/core/computed.py:54-125,228-326`,
  `src/fitdocs/index/derived/blocks.py:45-141`,
  `src/fitdocs/index/core/documents.py:28-29`,
  `src/fitdocs/skills/fitdocs-analytics/SKILL.md:57-215`,
  `src/fitdocs/query/statement.py:171-205`, `src/fitdocs/query/format.py:22-168`,
  `docs/analytics.md:128-486`.
- **Findings**:
  - `daily_load` (grain methodology × day, contiguous days): `day` DATE,
    `recorded_load` DOUBLE, 0 on a day with no load and never NULL;
    `fitness`, `fatigue`, `form` DOUBLE, NULL when the day is suppressed.
    Load columns carry no unit suffix. `form` is signed.
  - `weekly_load`: `week_start` DATE (Monday), `total_load` DOUBLE,
    `sessions` INTEGER.
  - `zone_times` (grain page × channel × zone): `zone` INTEGER from 1,
    `time_s` DOUBLE seconds, every zone gets a row including 0 s; pace zone 1
    is the fastest pace (dividers ascend in s/km).
  - `mean_max` (grain page × duration): `duration_s` INTEGER over a fixed
    list of 28 durations, 1 s to 21600 s (1, 5, 10, 15, 20, 30, 45, 60, 120,
    180, 240, 300, 360, 480, 600, 720, 900, 1200, 1800, 2400, 2700, 3600,
    5400, 7200, 10800, 14400, 18000, 21600); channels `power_w`, `speed_mps`,
    `heart_rate_bpm`; no pace column (pace is `1000.0 / speed_mps` in the
    query) and no date (a period comes from a join to `pages`).
  - Query values arrive unconverted: DATE → `date`, TIMESTAMP → naive
    `datetime`, INTERVAL → `timedelta`, DOUBLE → `float` (NaN possible),
    DECIMAL → `Decimal`, BIGINT/HUGEINT → `int`, BOOLEAN → `bool`.
- **Implications**:
  - `calendar-heatmap` over `daily_load` gets one row per day, zeros on rest
    days; days before the series start are missing rows and draw nothing.
    A signed `form` calendar is refused (`negative_value`), because a
    diverging scale is out of scope.
  - `heatmap`'s x and y axes must accept numbers (`zone`), ordered
    ascending.
  - `mean-max`'s `x` accepts a number column whose unit is `s`
    (`duration_s` maps to unit `s` through `fitdocs.units.unit_for_column`) or
    a duration column. Its typical golden spans 1 s to 1 h, the durations the
    table actually holds.
  - `stacked-100` over `zone_times` aggregated per week receives zero parts
    for empty zones (every zone has a row), and an all-zero week when the
    athlete recorded nothing in it; that week must not become a fabricated
    split.

### Sequential colour under chart-kit's theme rule
- **Context**: Requirements 2.1, 3.3, 3.9; chart-kit Requirement 8.2 (every
  ink at least 3:1 against each reference background as drawn; decorative
  fills exempt) and 5.6/8.5 (appended kinds under the same rules).
- **Sources Consulted**: probes `seq_ramp.py`, `seq_search.py`, `seq_pick.py`
  (scratchpad); chart-kit research § Theme contrast arithmetic; `dataviz`
  skill `references/color-formula.md` (sequential = one hue, monotone
  lightness; ordinal ramps want adjacent ΔL ≥ 0.06).
- **Findings**:
  - Greys reach 3:1 on all four backgrounds only for relative luminance
    about 0.146–0.30 (`#707070` to `#949494`), that is OKLab lightness of
    about 0.545–0.665. Any ink, coloured or grey, lives in that band.
  - Across that band a five-step ramp can change lightness by at most about
    0.12, about 0.03 per step, half the 0.06 the dataviz ordinal check asks
    for.
  - A grid search over hues 0–350° (10° steps), hue drift −30° to +30°,
    lightness 0.665→0.545 and chroma 0.02→0.20 found no ramp whose worst
    adjacent OKLab distance (normal, protanopia, deuteranopia, tritanopia)
    exceeds 0.039. Blue-indigo hues (≈280°) score best.
  - Chosen ramp (`oklch(L C 280)`, lightness and chroma stepped evenly):

    | # | oklch source | sRGB | min contrast | OKLab L |
    |---|---|---|---|---|
    | 1 | `oklch(0.665 0.02 280)` | `#9193a0` | 3.05 (white) | 0.666 |
    | 2 | `oklch(0.635 0.06 280)` | `#8387af` | 3.47 | 0.635 |
    | 3 | `oklch(0.605 0.1 280)` | `#767abd` | 3.97 | 0.604 |
    | 4 | `oklch(0.575 0.14 280)` | `#6a6cc9` | 3.53 (slate) | 0.574 |
    | 5 | `oklch(0.545 0.18 280)` | `#605cd5` | 3.06 (slate) | 0.545 |

    Adjacent OKLab distances: normal 0.049–0.051, protanopia 0.049–0.051,
    deuteranopia 0.052–0.055, tritanopia 0.037–0.038. Hex verified through
    the shipped `palette._oklch_to_hex`, which returned exactly these five.
  - A translucent single-ink ramp is theme-adaptive (light on white, dark on
    dark), but its composite at 25% opacity is about 1.3:1 on white.
- **Implications**:
  - The grid kinds carry magnitude by **cell area** (a filled square whose
    side is the inner cell's side times √(bin ÷ bins)), with the ramp as a
    second, weaker carrier. This satisfies "colour never the sole carrier"
    by construction and keeps every mark at or above 3:1.
  - Stated minima for the test (Requirement 3.9): every ramp colour ≥ 3:1 on
    all four backgrounds; OKLab lightness strictly decreasing and chroma
    strictly increasing along the ramp; adjacent OKLab distance ≥ 0.045
    under normal vision, protanopia and deuteranopia, and ≥ 0.03 under
    tritanopia.
  - **Maintainer-visible**: a "heatmap" here looks like a proportional-area
    grid that is also shaded, not a GitHub-style solid-cell heatmap. That is
    the honest consequence of the mismatch-safe theme rule.

### Absent, zero and missing in a grid
- **Context**: roadmap constraint "a heatmap cell with no value differs
  visibly from one whose value is zero"; chart-kit's rule "a missing row is
  not an absent value"; the calendar queue item's "overlapping no-data
  encodings".
- **Sources Consulted**: `.kiro/queue/2026-09-12-calendar-chart-degenerate-domains-and-band-semantics.md`;
  chart-kit design § Cartesian, § Kinds (bar zero stub, hbar em dash);
  chart-kit research § Decision: absence rules per kind.
- **Findings**: the existing calendar chart stacks two "no data" encodings (a
  suppressed band and a series gap) with no stated precedence, silently
  drops an out-of-range marker, and lets a one-day or constant series
  collapse its axes.
- **Implications** (the catalog's equivalents):
  - Four states per grid position, mutually exclusive by construction
    (duplicate positions are refused): missing row → nothing drawn; absent
    value → a grey cross; zero → an unfilled outlined square; positive → a
    filled square sized by bin. The legend shows the zero and absent marks
    whenever the chart holds any.
  - Zero is its own value class because bins exclude their lower edge.
  - A one-day calendar draws one week column at the normal cell size; a
    constant series falls in its top bin with edges enclosing the value; an
    all-zero series draws outlines and a legend without bins.
  - No catalog kind takes markers or indices, so there is no out-of-range
    marker case; out-of-range values (negative values on a grid kind, zero
    or negative durations on mean-max, low above high) are refused with a
    problem, never clamped.

### Dual axes
- **Context**: the roadmap includes `dual-axis`; the `dataviz` skill calls a
  dual-axis chart "the #1 chart mistake" (two y-scales invite false
  correlation and misattribution).
- **Findings**: the maintainer decided the catalogue at discovery
  (2026-10-11), so the kind ships. The misreadings it invites are which line
  belongs to which axis, and two series in the same unit on independent
  scales.
- **Implications**: series 2 always differs from series 1 by dash pattern as
  well as colour; the legend names each series with its axis side; gridlines
  follow the left axis only; binding the same column or the same unit
  (durations count as one unit) to both value channels is refused with a fix
  naming `line` with a colour column (new code `shared_unit`). The
  `dashboards` skill should steer agents to `small-multiples` or an indexed
  `line` when two quantities are not paired; noted for `dashboards`.

### Box from precomputed quartiles or raw values
- **Context**: the brief leaves the choice to the design.
- **Findings**: raw values would need a quantile method (stdlib
  `statistics.quantiles` 'exclusive' vs 'inclusive' vs DuckDB's
  `quantile_cont`), an outlier rule, and a mark bound over raw rows that is
  unrelated to the number of boxes drawn. DuckDB computes any quantile in
  the query (`quantile_cont(x, 0.25)`), and the whisker rule (min–max,
  p5–p95, Tukey fences) is the athlete's choice.
- **Implications**: precomputed. Five value channels; the kit checks their
  order and draws them. This also keeps Requirement 2.11 (no aggregates).

### Seam gaps in chart-kit, and their accommodations
- **One-form duration labels.** chart-kit's rule is "callers labelling an
  axis use one form for every tick (h:mm:ss if any tick reaches 3600 s)", but
  the only public formatter, `format_duration(seconds)`, switches form per
  value. The per-axis form lives inside `numeric_scale`. The catalog labels
  durations outside `numeric_scale` twice (grid legend edges, mean-max's
  landmark ticks). **Accommodation A1**: append
  `format.format_durations(values) -> tuple[str, ...]` (one form for the
  whole sequence; rounding as `format_duration`). If the landed `format.py`
  already exposes a public equivalent, consume it instead.
- **The `Not drawn:` note line.** chart-kit fixes the wording (`Not drawn:
  1 row without y.` / `Not drawn: 3 rows without x, 2 rows without y.`) but
  names no public builder; `frame.notes(plan, lines)` takes finished strings.
  All eight catalog kinds need the line. **Accommodation A2**: append
  `frame.not_drawn_note(counts) -> str | None` producing exactly that
  wording. If the landed `frame.py` already exposes a public builder,
  consume it instead.
- **Vertical band labels.** `band_scale` labels every band when the widest
  label fits the band *width* minus 4 px, which is the right test for a
  horizontal axis and the wrong one for a vertical axis of rows. No
  accommodation in chart-kit: `heatmap` builds its row `BandScale` directly
  (a public frozen dataclass) with a height-based `labelled` rule, and
  `calendar-heatmap` fixes its weekday labels.
- **Right-axis title and `band_path`'s shape.** chart-kit promises dual axes
  through `frame.axis(..., Side.RIGHT, ...)` but does not state where the
  right axis title sits, and `marks.band_path` is specified as "the closed
  polygon" without saying whether it returns path data or an element. These
  are upstream checks, not accommodations: the catalog's first task verifies
  them against the landed code and stops and reports if either differs from
  what design.md assumes (a right title on the y-title row, end-anchored at
  the right content edge, not overlapping the left title; `band_path`
  returning path data the caller wraps).
- **Legend swatches.** `LegendEntry.swatch` is `line | shape | block`; the
  grid legend needs sized squares, an outline and a cross. No
  accommodation: the grid legend reuses `layout.plan_frame`'s legend rows
  for placement and draws its own swatches in `cells.legend`, inside the
  same `ck-legend` group with `ck-t` text.

### Second-lander precedent
- **Sources Consulted**: `.kiro/specs/analytics-derived/tasks.md:137-160,874-958`;
  `.kiro/specs/analytics-query/tasks.md:170-220,1236-1310`;
  `.kiro/specs/dashboards/brief.md`; roadmap Phase 11 § Boundary Strategy.
- **Findings**: Phase 10's pair stated the rule identically in both plans,
  bounded the second lander to a named set of files, made the first-lander
  path an explicit no-op recorded in Implementation Notes ("no queue item is
  needed, because the other plan tracks it"), and proved the second-lander
  path with the other spec's own tests.
- **Implications**: task 4.2 copies that shape. It reads `dashboards`'
  tasks.md for the exact writer, block and count pins at landing time,
  because `dashboards` is being specified in parallel.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|---|---|---|---|---|
| Thin kind modules over chart-kit, one shared `cells` module for the two grid kinds | Each kind maps channels onto shared scales, axes, marks; the grid kinds share one binned scale | Smallest surface; parallel kind tasks; no core edit | `cells` is a new rank in the layer matrix | **Selected** (maintainer approach: kinds as thin modules) |
| Grid logic duplicated in both grid kinds | No new shared module | No rank change | Two copies of the absent/zero/bin rules drift | Rejected |
| `small-multiples` composing registered kinds | Panels drawn by calling another kind's `draw` | Any kind as a panel | Kinds may not import `registry` or another kind (chart-kit rank matrix); panel geometry is not a `KindSpec` concern | Rejected |
| Translucent sequential ramp | One ink at stepped opacity | Real light→dark ramp in both themes | Low steps far below 3:1 as drawn (chart-kit 8.2) | Rejected |
| Solid in-band ramp alone | Colour as the only magnitude carrier | Classic heatmap look | Adjacent steps ≈ 0.05 OKLab; colour sole carrier (2.2) | Rejected |
| Area plus in-band ramp | Square area by bin, colour reinforcing | Theme- and CVD-robust; every mark ≥ 3:1 | Less conventional look | **Selected** |
| Diverging scale for signed values | Two hues around zero | `form` calendars | Sign by colour alone needs another carrier; more surface | Deferred (follow-on) |

## Design Decisions

### Decision: magnitude by area in the grid kinds
- **Context**: Requirements 2.1, 2.2, 3.3, 3.9; § Sequential colour.
- **Alternatives Considered**: translucent ramp; solid in-band ramp alone;
  value text in each cell (text on a coloured fill fails contrast, and a
  365-cell calendar has no room).
- **Selected Approach**: each positive cell is a filled square centred in
  its cell, side = inner side × √(bin ÷ bins), coloured from the top `bins`
  entries of the five-step ramp; zero is an unfilled outlined square in the
  ramp's first colour; absent is a cross in the theme's stroke ink.
- **Rationale**: every state differs in shape or size, so it reads without
  colour and in either theme; every ink is ≥ 3:1.
- **Trade-offs**: looks unlike GitHub's grid. Maintainer-visible.

### Decision: bins exclude their lower edge, edges from chart-kit's ticks
- **Selected Approach**: edges are `linear_ticks(0, max_positive, 6,
  duration=…, integer=…)`'s ticks (so 1–5 bins with round edges), each bin
  `(e[i-1], e[i]]`. `integer=True` when every present value is a whole
  number; `duration=True` for duration columns and the `s`/`s_per_km` units.
- **Rationale**: zero is never in a bin; edges are the same round values an
  axis would show; no new tick arithmetic.

### Decision: four appended problem codes
- **Selected Approach**: append `negative_value` (a grid value below zero),
  `value_order` (band low > high; box quantiles out of order),
  `shared_unit` (dual-axis's two value channels on one column or unit) and
  `channel_unit` (a channel needing a unit family the bound column lacks:
  mean-max's seconds). Reuse `over_bound`, `duplicate_position`,
  `log_domain`, `stack_absent`, `stack_negative`, `unit_mismatch` and
  `channel_kind` wherever their meaning fits exactly.
- **Rationale**: a code an agent acts on must have one meaning; each new code
  has one fix.

### Decision: kind-local over-bound wording where rows are not the unit
- **Selected Approach**: kinds whose bound counts rows (`heatmap` cells,
  `dual-axis`, `band`, `box`, `mean-max`, `stacked-100`) use
  `cartesian.bound_problem`; `calendar-heatmap` (week columns) and
  `small-multiples` (panels) build their own `over_bound` problems with a
  fix that names the right reduction, as do `heatmap`'s distinct-x and
  distinct-y limits and `small-multiples`' row limit.
- **Follow-up**: chart-kit's at-bound class mutation (`cartesian.bound_problem`
  `>` → `>=`) does not reach the two kind-local bounds; their tasks carry
  kind-local at-bound mutations.

### Decision: `mean-max` labels landmarks first
- **Context**: Requirement 9.3; chart-kit's `log_ticks` thins the duration
  ladder by keeping every k-th tick from the first, so a domain starting at
  2 s or 10 s loses 5 s, 1 min, 5 min, 20 min and 1 h.
- **Selected Approach**: the domain is `numeric_scale`'s log domain; the
  ticks are chosen greedily from the log-duration ladder in a fixed priority
  (60, 3600, 300, 1200, 5, 1, 15, 30, 120, 600, 1800, 7200, 10800, 21600,
  43200, 86400, 2, 10), accepting a tick only when its label does not
  overlap an accepted one (label widths plus 10 px), then sorted. Labels use
  one duration form for the axis (h:mm:ss when the domain reaches 3600 s).

### Decision: `small-multiples` draws its own panels
- **Selected Approach**: one line per panel through `marks.line_series`,
  panels laid out on a grid inside the plot rectangle, each drawn in a
  `<g transform="translate(…)">` with a panel-local `FramePlan` from
  `layout.plan_frame`, so one shared scale serves every panel.
- **Rationale**: chart-kit's rank matrix forbids kind → kind and kind →
  registry imports; the brief asks for mini line charts only.

### Decision: `stacked-100` zero totals
- **Selected Approach**: absent parts are refused (`stack_absent`, chart-kit
  Requirement 9.5 for every stacked chart); negative parts are refused
  (`stack_negative`); a bar whose parts are all zero draws chart-kit's zero
  stub in the stroke ink and is counted in a note, `Zero total, no shares
  drawn: 1 bar.`; a missing (x, part) row draws no segment.
- **Rationale**: 0 ÷ 0 has no share; drawing 0% or 100% would fabricate one.

### Decision: one release-note line, always
- **Context**: chart-kit wrote no CHANGELOG entry because nothing
  user-runnable reached it before `dashboards`.
- **Selected Approach**: the catalog appends one `[Unreleased]` → `### Added`
  line in either landing order, so the release notes are right whichever
  spec lands first.

## Synthesis Outcomes
- **Generalization**: the two grid kinds are one problem (value classes over
  positioned cells); `cells` holds it once. The four multi-value kinds
  (`dual-axis`, `band`, `box`, `small-multiples`) share one counting rule
  for undrawn values (rows without the positioning channel first, then each
  value channel's own absences) through A2.
- **Build vs adopt**: every scale, tick, label, axis, legend layout, series
  style, gap rule and problem helper is adopted from chart-kit. Built: the
  binned scale and cell marks (no chart-kit equivalent), landmark tick
  selection (chart-kit's thinning loses landmarks), panel layout.
- **Simplification**: no diverging scale; no colour channel on `band`,
  `box`, `dual-axis` or `small-multiples`; no per-cell value text; no
  options beyond zero inclusion, panel columns and panel y scales.

## Risks & Mitigations
- **chart-kit is unimplemented at spec time** — its private helpers may
  already cover A1 or A2, or its `frame.axis`/`band_path` may differ from the
  assumptions. Mitigation: task 1.1 verifies each against the landed code,
  consumes an existing public equivalent instead of appending, and stops and
  reports on a behavioural mismatch.
- **Thin contrast margin on the ramp ends** (3.05 and 3.06). Mitigation: the
  ramp is fixed constants pinned by an independent test; area carries the
  magnitude.
- **Golden volume** (~70 SVG files). Mitigation: one golden per behaviour the
  requirements name; regeneration is per kind module.
- **Parallel `dashboards` edits** to `CHANGELOG.md` and, if it lands first,
  to its kinds listing. Mitigation: append-only edits and the bounded
  second-lander task.

## References
- WCAG 2.2 §1.4.3, §1.4.11; relative luminance definition.
- Machado, Oliveira & Fernandes (2009), IEEE TVCG 15(6) — severity-1.0
  matrices.
- Ottosson (2020), OKLab.
- `dataviz` skill (bundled), `references/color-formula.md` — sequential and
  ordinal ramp rules, dual-axis anti-pattern.
- chart-kit spec at `560f909`: `design.md` § Settled Seams, `tasks.md`
  § Cross-spec shared files.
