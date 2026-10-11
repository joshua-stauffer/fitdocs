# Research & Design Decisions: chart-kit

## Summary
- **Feature**: `chart-kit`
- **Discovery Scope**: New Feature (a new stdlib-only subsystem beside the
  existing chart renderers), with one integration point into
  `fitdocs.index.schema` (the unit vocabulary).
- **How research ran**: three read-only `Explore` subagents surveyed the
  codebase in parallel (boundary guards and declared registries; chart goldens,
  palette and theme facts; query result types and unit suffixes). Five
  stdlib/`uv run` probes ran in the session scratchpad (import closure of
  `render.charts.svg`; candidate palettes; a greedy palette search under the
  contrast constraint; ink greys and SVG size estimates; verification of the
  chosen palette through the shipped `palette._oklch_to_hex`). **Downgrade**: no
  WebSearch/WebFetch — the batch controller ruled the run network-free. The
  external facts this design rests on (WCAG 2.x contrast, Machado 2009 CVD
  matrices, Heckbert nice numbers, CSS-over-presentation-attribute precedence,
  SVG `<title>`/`<desc>` semantics) are stable standards cited from knowledge,
  and the browser behaviour of the theme mechanism was established by the
  Phase 11 discovery probes recorded in the roadmap.
- **Key Findings**:
  - Importing any `fitdocs.render.charts` submodule executes
    `fitdocs/render/__init__.py`, which loads `fitdocs.model`, `metrics`,
    `contract`, `compose.types`, `identity.kinds` and `yaml`. "Stdlib only" and
    "imports nothing from model" can therefore be a *static* property of the
    kit's own modules, not a runtime import-closure property, as long as the kit
    reuses `svg.py`.
  - `UNIT_SUFFIXES` lives in `fitdocs.index.schema`, which the kit may not
    import. The only way to have one table and keep the import rule is a neutral
    leaf module both sides import.
  - The theme's three greys can be chosen so that *no* rule a viewer might
    apply, right or wrong, drops text below 3:1 on any reference background:
    the WebKit mismatch case (system light, page dark) becomes harmless.

## Research Log

### Existing chart primitives and renderers
- **Context**: the brief requires reuse of `svg.py`, `series.py`, `palette.py`
  and forbids changing the four renderers.
- **Sources Consulted**: `src/fitdocs/render/charts/{svg,series,palette,hero,calendar,zones,map}.py`;
  `tests/render/charts/*`; `tests/sitebuild/test_hero_chart.py`.
- **Findings**:
  - `svg.el(tag, attrs, children)` emits attributes in caller order, escapes
    attribute values and joins children verbatim; `text()` escapes content;
    `fmt_num` gives ≤2 decimals with `-0` normalised. `svg_document` emits a
    fixed root with no `role` attribute, so the kit builds its own root with `el`.
  - The presentation-attributes-only rule is prose in `svg.py:23-29` and
    `:105-108`; no test enforces a tag or attribute whitelist. No golden contains
    `<style`, `<title`, `<desc`.
  - `series.gap_segments(x, y)` splits at `None` and never bridges.
  - `palette.py` ships hex constants with oklch sources in
    `SERIES_COLORS`/`ZONE_COLORS`/`ROUTE_COLORS`, checked by
    `tests/render/charts/test_palette.py` which reimplements OKLCH→sRGB.
  - Existing text inks: hero `#555`/`#333`/`#999`, calendar `#333333`/`#444444`,
    zones `#333`, map `#333333`. Only `map.py` sets `font-family`
    (`sans-serif`). Width estimates: hero 7.0 px at 11 px (0.64 em), map 6.0 px
    at 10 px (0.6 em).
  - Goldens are one-line SVGs with no trailing newline, compared as `str`
    against `read_text()`; regeneration is a per-test-module `main()` behind
    `if __name__ == "__main__"`; only `tests/sitebuild/test_hero_chart.py`
    compares bytes and carries a tamper test.
  - Golden sizes today: 1.4–3.7 KB; no test sets a size budget.
- **Implications**: the kit reuses `el`, `text`, `fmt_num`, `gap_segments` and
  appends its categorical palette to `palette.py` under the same
  provenance-and-test convention. It builds its own root, compares goldens as
  bytes, and follows the per-module `main()` regeneration convention plus a
  tamper test of the comparator.

### Runtime import closure of the chart package
- **Context**: Requirement 16.4 (stdlib only; no model/ingest imports).
- **Sources Consulted**: probe `import_closure.py` (imports
  `fitdocs.render.charts.svg`, lists `sys.modules`).
- **Findings**: 22 `fitdocs.*` modules load, including `fitdocs.model`,
  `fitdocs.metrics.*`, `fitdocs.contract`, `fitdocs.compose.types`,
  `fitdocs.identity.kinds` and `fitdocs.render.charts.map`; third-party `yaml`
  loads through `contract`.
- **Implications**: the boundary guard is a static AST guard on the kit's own
  modules (the repo's established pattern: `tests/connectors/test_boundary.py`,
  `tests/compose/test_boundary.py`). The design states this limit explicitly so
  no later reviewer reads "stdlib only" as a runtime-closure claim. Moving
  `svg.py` out of `fitdocs.render` to fix the closure would touch the four
  renderers' imports and is out of scope.

### Unit vocabulary
- **Context**: roadmap seam "one table of unit tokens, not two drifting copies";
  Requirements 2.1–2.3.
- **Sources Consulted**: `src/fitdocs/index/schema.py:77-97,137-179`;
  `src/fitdocs/query/schemaview.py:86-90`; `tests/index/test_schema.py:181-205,1229-1288`;
  `tests/query/test_schemaview.py:142-167`; `src/fitdocs/model.py:24-28`;
  `src/fitdocs/index/derived/benchmarks.py:17-23`;
  `src/fitdocs/index/core/computed.py:249-251`.
- **Findings**:
  - 19 suffixes, ordered longest first, first match wins; each maps to the unit
    phrase a column description must contain. Pinned by exact equality, a count
    of 19 and the length ordering.
  - Data-level unit tokens already exist as "the suffix without its
    underscore": `zone_times.bound_unit` (`bpm`, `w`, `s_per_km`),
    `benchmarks.unit`, and the model's documented units. The kit's token
    convention is the established one.
  - Index columns per suffix: `_s_per_km` (only `activities.avg_pace_s_per_km`),
    `_local` and `_utc` only on TIMESTAMP columns, `_km` on no index column (only
    aliases), `_pct` values in percent units (`decoupling_pct`), `_s` on both
    durations and offsets. DATE columns carry no suffix.
  - The suffix convention is taught nowhere in `docs/` or the skills; one
    skill example (`SUM(z.time_s) AS seconds`) drops it.
- **Implications**: a new leaf module `fitdocs.units` holds the one table
  (token, phrase, symbol, family, decimals); `index.schema.UNIT_SUFFIXES`
  becomes a projection of it with an identical value, so every existing pin
  stays green unchanged. Teaching suffix-keeping aliases is `dashboards`' skill
  work.

### The cadence-label trap (maintainer first-use note, 2026-10-11)
- **Context**: `analytics-feedback.md` item 1 (untracked, main checkout):
  running `cadence_rpm` holds strides per minute (one foot, the FIT
  convention), labelled "revolutions per minute".
- **Sources Consulted**: `src/fitdocs/load/qa/types.py:73-80`
  (`STEPS_PER_CADENCE_REVOLUTION = 2`), `load/qa/cadence.py:107`,
  `index/core/computed.py:29-30,70,178-180`, `render/sections.py:297,363`,
  `docs/analytics.md:150-151,256,421`.
- **Findings**: for running, `*_cadence_rpm` is half of steps per minute; every
  label in fitdocs today says "rpm" / "revolutions per minute"; nothing says
  "spm", "steps" or "strides".
- **Implications**: the kit takes the conservative position the batch
  controller set: it labels what the suffix names (`rpm`) and never
  reinterprets a unit by sport or value (Requirement 2.5). Correcting the
  vocabulary (a derived steps-per-minute column, a new suffix) is a schema
  decision outside this spec. The trap is carried forward as a design note the
  `dashboards` skill must state. Maintainer-visible.

### Query result values the kit will receive
- **Context**: the data contract must accept exactly what `dashboards` can
  build from a query result.
- **Sources Consulted**: `src/fitdocs/query/format.py:22-29,74-168`;
  `query/statement.py:171-205`; `index/store.py:98-136,314`;
  `tests/query/test_format.py:30-77`.
- **Findings**: rows are plain DuckDB Python values: `bool`, `int`, `float`,
  `Decimal` (DECIMAL; literals such as `1.5` are DECIMAL), `str`, `date`, naive
  `datetime`, `time`, `timedelta` (INTERVAL), `list`, `dict`, `bytes`, `UUID`,
  `None`. TIMESTAMPTZ cannot be fetched. Nothing normalises values. `datetime`
  is a subclass of `date`; existing code tests `datetime` first or uses
  `type(v) is date`. NaN and infinities are possible DOUBLE values.
- **Implications**: number columns accept `int` (not `bool`), finite `float`
  and finite `Decimal`; date columns refuse `datetime`; date-time columns refuse
  aware values; `time`, lists, dicts, bytes and UUIDs have no value kind (the
  adapter in `dashboards` refuses them). Non-finite numbers are refused, never
  turned into absence.

### Boundary-guard and registry patterns
- **Context**: Requirements 5, 16.3, 16.4, 18.5.
- **Sources Consulted**: `tests/query/test_boundary.py:24-238,490-551`,
  `tests/connectors/test_boundary.py:82-145,254-507,639-706`,
  `tests/compose/test_boundary.py:37-408`, `tests/render/test_attribution.py:304-317`,
  `src/fitdocs/agentskill.py:44-53`, `src/fitdocs/index/registry.py:17-26`,
  `tests/test_skill_locator.py:59-65,198-205`, `pyproject.toml:87-268`.
- **Findings**: no shared boundary helper — each guard owns its AST walker.
  The strictest clock guard is compose's (9 spellings + `_CLOCK_NAMES` matched
  on AST names, with positive and negative controls). Registries are module
  `Final` tuples of frozen-dataclass instances, pinned by exact ordered
  equality. mypy covers all of `src` through a `"src"` entry but needs explicit
  test-path entries. No existing test proves `render/charts` imports only
  stdlib plus siblings.
- **Implications**: the kit's guard enumerates its modules by hand and checks
  the list against `rglob` both ways, applies the `sys.stdlib_module_names`
  rule with an allow-list of chart primitives and `fitdocs.units`, forbids the
  five named packages by dotted descent, and copies compose's clock guard. The
  registry is a `Final` tuple pinned by an ordered prefix of the eight core
  names. New test directories are registered in `[tool.mypy].files`.

### Theme contrast arithmetic
- **Context**: Requirements 8.2–8.4; the brief's note that no single grey reaches
  4.5:1 on both `#ffffff` and `#1e1e1e`.
- **Sources Consulted**: WCAG 2.x relative luminance and contrast ratio; probes
  `palette_probe.py`, `ink_size_probe.py`, `verify_palette.py`.
- **Findings** (contrast against white / `#1e1e1e` / `#0d1117` / `#1e2129`):

  | Ink | Role | White | Obsidian | GitHub | Slate |
  |---|---|---|---|---|---|
  | `#7f7f7f` | base (no rule) | 4.00 | 4.16 | 4.73 | 4.02 |
  | `#707070` | light-scheme rule | 4.95 | 3.37 | 3.82 | 3.25 |
  | `#8e8e8e` | dark-scheme rule | 3.28 | 5.09 | 5.78 | 4.91 |

  A grey satisfies "≥4.5 on white and ≥3 on every dark" when its relative
  luminance lies in about [0.146, 0.183]; "≥4.5 on every dark and ≥3 on white"
  in about [0.243, 0.30]. Both intervals are non-empty.
- **Implications**: each scheme rule raises text where it is honoured and still
  holds 3:1 where it is misapplied (WebKit following system appearance on a page
  of the other scheme, bug 316640). This is stronger than the brief's rule and
  costs nothing.

### Categorical palette
- **Context**: Requirement 8.7 (colour-blind-safe, oklch sources) under the
  3:1 constraint of Requirement 8.2.
- **Findings**: the 3:1-on-all-four constraint confines series colours to a
  relative-luminance band of about [0.146, 0.30], so luminance cannot separate
  them; hue and chroma must. Two hand-picked palettes failed (a yellow at
  2.46:1 on white; deuteranopic pairs at 0.023 OKLab). A greedy search over an
  oklch grid (L 0.54–0.72, C 0.10–0.18, H every 5°, in gamut, min contrast
  ≥3.15) maximising the minimum pairwise OKLab distance under normal vision and
  Machado-2009 full-severity protanopia, deuteranopia and tritanopia (CVD
  distances weighted ×1.6) chose, in order:

  | # | oklch source | sRGB | min contrast | role |
  |---|---|---|---|---|
  | 1 | `oklch(0.6 0.14 250)` | `#3284d0` | 3.93 | blue |
  | 2 | `oklch(0.66 0.18 45)` | `#e86518` | 3.33 | orange |
  | 3 | `oklch(0.56 0.14 345)` | `#ac4e87` | 3.21 | magenta |
  | 4 | `oklch(0.64 0.1 135)` | `#719a5b` | 3.24 | green |
  | 5 | `oklch(0.56 0.16 30)` | `#c04637` | 3.20 | red |
  | 6 | `oklch(0.66 0.1 355)` | `#c27895` | 3.27 | pink |
  | 7 | `oklch(0.54 0.12 160)` | `#098356` | 3.37 | teal |
  | 8 | `oklch(0.56 0.18 285)` | `#6e5dd8` | 3.23 | violet |

  Minimum pairwise OKLab distance over all 28 pairs: normal 0.109, protanopia
  0.067, deuteranopia 0.062, tritanopia 0.071. Hex values verified through the
  shipped `palette._oklch_to_hex`.
- **Implications**: thresholds for the test are ≥0.10 (normal) and ≥0.06 (each
  simulation), ≥3:1 contrast. Distances this small mean colour alone is weak
  for CVD readers by construction, which is why Requirement 8.8's second
  carrier (dash, shape, or position-and-legend-order) is mandatory, not
  decorative.

### Size estimates
- **Context**: Requirement 11.4–11.5.
- **Findings** (probe `ink_size_probe.py`): three 365-point polylines ≈ 15.2 KB
  of mark bytes; 2,000 round-cap dots in one path ≈ 31 KB, 2,000 square-ish
  path shapes ≈ 43 KB; 200 bar rectangles ≈ 14.5 KB. The frame (root, title,
  desc, style, axes, ticks, legend) is estimated at 3–5 KB.
- **Implications**: the budgets in design.md are set with ~25% headroom over
  these estimates and are measured, not assumed, at implementation (task notes
  say so). The named mutation that must bust each budget is a per-point element
  instead of one path or polyline per series.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|---|---|---|---|---|
| Named kinds over a shared layer | One module per kind mapping its channels onto shared scales, axes, legend, theme | Small surface; an agent picks a kind and binds columns; kinds append independently | Some duplication between similar kinds | Maintainer decision 2026-10-11; selected |
| Composable grammar (marks × encodings × transforms) | Vega-Lite-style | Expressive | Far larger to build and test; many valid-but-wrong specs | Rejected at discovery |
| Plotting dependency (matplotlib) | Delegate drawing | Mature | Heavy; text as paths; random ids; hard to theme or golden | Rejected at discovery; `tech.md` keeps it out |
| Kit as flat modules in `render.charts` | `kit_*.py` beside `hero.py` | No new package | Mixes kit and renderer namespaces; guard must list files by prefix | Rejected for a subpackage |
| Kit as top-level `fitdocs.chartkit` | Sibling package | Clear name | Still loads `fitdocs.render` through `svg.py`, so no closure benefit; splits chart code across two trees | Rejected |
| Kit as `fitdocs.render.charts.kit` subpackage | New subpackage beside the renderers | Sits with the primitives it reuses; one guard walks one directory; chart-catalog's kinds land in `kit/kinds/` | Runtime closure includes `fitdocs.render` | Selected |

## Design Decisions

### Decision: one unit table in a neutral leaf module
- **Context**: the kit may not import `fitdocs.index`; the roadmap forbids two
  drifting copies.
- **Alternatives Considered**:
  1. Kit keeps its own token table, pinned equal to `UNIT_SUFFIXES` by a test —
     a guarded second copy.
  2. Table in the kit; `index.schema` imports it from `fitdocs.render.charts.kit`
     — adds an index → render edge, against the layer direction.
  3. Leaf module `fitdocs.units`, imported by both.
- **Selected Approach**: 3. `fitdocs.units.UNITS` holds token, phrase, symbol,
  family, decimals and spacing for all 19 units in today's order;
  `index.schema.UNIT_SUFFIXES = tuple((u.suffix, u.phrase) for u in UNITS)`.
- **Rationale**: one table; import rules intact; existing pins unchanged.
- **Trade-offs**: `analytics-index`'s module gains one import; adding a unit
  later is a schema-visible change (its pins fail), which is the right signal.
- **Follow-up**: `structure.md` gains the `units` line; `analytics-index`'s
  design gains a note that its suffix table's source moved.

### Decision: the kit converts no units; pace comes from a `_s_per_km` column
- **Context**: the brief lists "pace in min/km from metres per second" among
  unit-aware labels.
- **Alternatives Considered**:
  1. A per-channel display option (`y_pace: true`) converting m/s to s/km in
     the kit.
  2. No conversion in the kit: the `s_per_km` token formats as `m:ss` labelled
     `min/km`; a query that wants pace from speed writes
     `1000.0 / NULLIF(speed_mps, 0) AS pace_s_per_km`.
- **Selected Approach**: 2.
- **Rationale**: units already "ride on column-name suffixes" (roadmap); one
  mechanism, visible in the SQL; one fewer way to write a valid-but-wrong spec;
  no kit rule needed for a zero or negative speed. The min/km label the brief
  wants is delivered.
- **Trade-offs**: an agent writes a short expression. Reversible by appending
  an option later without breaking any chart. **Maintainer-visible**: this
  narrows the brief's wording.

### Decision: mismatch-safe theme inks, rules emitted per role
- **Selected Approach**: base `#7f7f7f`; light rule `#707070`; dark rule
  `#8e8e8e` (table above). Two core roles (`ck-t` fill for text, `ck-s` stroke
  for axes, ticks and gridlines). The `<style>` body is a fixed string for the
  core roles; an appended role's rule is emitted only by a chart that uses it.
- **Rationale**: no misapplied scheme drops below 3:1; appending a role never
  changes a core golden.

### Decision: colour is never alone
- **Selected Approach**: line and area outlines carry a per-series dash
  pattern; scatter series carry a per-series marker shape; bar series are
  ordered in the legend exactly as they are grouped (left to right) and stacked
  (bottom to top). The legend swatch reproduces the carrier.

### Decision: problems are data, refusals are exceptions
- **Selected Approach**: `validate_chart(request, columns)` returns a tuple of
  `ChartProblem`; `render_chart(request, data)` returns a `RenderedChart` or
  raises `ChartError(problems)`. Each kind contributes a columns-only
  `validate`, a data-level `check` and a `draw`.
- **Rationale**: `dashboards`' check form needs every problem without rows; the
  render path needs one refusal carrying all of them.

### Decision: option values accept their canonical text form
- **Context**: `dashboards` parses directives with a strict YAML loader with no
  implicit resolvers, so `trend: true` and `bins: 20` arrive as strings.
- **Selected Approach**: each option type declares one canonical text syntax
  (`true`/`false`; `-?[0-9]+`; a decimal literal; an exact choice) that the
  kit accepts beside the typed value, converting it. Anything else is an
  `option_value` problem.
- **Rationale**: the parse lives once, beside the option's declaration;
  `dashboards` passes strings through without a second copy of the types.

### Decision: absence rules per kind
- **Selected Approach**: lines break; isolated points are dots; absent bars are
  not drawn while zero bars are 2 px stubs; rows unplaceable on a continuous
  axis are counted in a visible note and the description; absent category or
  colour values form a last series or band labelled `—`; stacked kinds refuse
  absent values; stacked areas refuse a missing (x, series) pair. A missing row
  (as opposed to a row with an absent value) is not absence: the kit draws the
  rows it is given.
- **Rationale**: every absent value leaves a visible trace or a stated count;
  nothing absent is ever positioned as zero; a stacked total is never silently
  wrong.

### Decision: em dash in markdown output
- **Context**: `render/format.py:33` uses an **en dash** (U+2013) for absent
  values in workout documents; the brief and roadmap say **em dash**.
- **Selected Approach**: U+2014, per the brief. One constant; flagged to the
  maintainer as a cross-document inconsistency.

### Decision: no CHANGELOG entry from this spec
- **Context**: CHANGELOG entries describe user-observable behaviour.
- **Selected Approach**: nothing a user can run reaches the kit until
  `dashboards` lands; `dashboards`' entry describes charts.

## Risks & Mitigations
- **The theme rests on browser behaviour probed once at discovery.** —
  Mitigation: the inks are safe even when the media query is ignored or
  misapplied; the contrast arithmetic is pinned by tests; an optional
  maintainer visual check is listed in the tasks.
- **Character-width estimate is approximate** — real fonts differ (0.6–0.64 em
  for digits in common sans fonts; wider for `W`/`M`). Mitigation: the estimate
  is the conservative 0.64 em of `hero.py`, labels are short, and long labels
  truncate.
- **Thin CVD margins** (deuteranopia 0.062 vs threshold 0.06). — Mitigation:
  colour is never alone (Requirement 8.8); the palette is fixed constants, so
  the margin cannot erode without a test failing.
- **Golden volume** (~60 files, mark-bound goldens up to ~45 KB). —
  Mitigation: goldens are one per behaviour named in Requirement 18; the
  regeneration writer is a single module.
- **Wave-2 parallel edits to shared files** (`kit/registry.py`, `palette.py`,
  `pyproject.toml` mypy list). — Mitigation: append-only rules and an ordered
  prefix pin rather than a count where possible; the second lander re-pins.

## References
- WCAG 2.2, §1.4.3 Contrast (Minimum) and §1.4.11 Non-text Contrast; relative
  luminance definition.
- Machado, Oliveira & Fernandes (2009), "A Physiologically-based Model for
  Simulation of Color Vision Deficiency", IEEE TVCG 15(6) — severity-1.0
  matrices.
- Ottosson (2020), "A perceptual color space for image processing" (OKLab).
- Heckbert (1990), "Nice numbers for graph labels", Graphics Gems.
- SVG 2 §6.6 (presentation attributes have specificity 0 and precede author
  style sheets); SVG-AAM 1.0 (`<title>`/`<desc>` as accessible name and
  description).
- Phase 11 viability (roadmap, 2026-10-11): Chromium 2e97c36 / crbug 1345247;
  WebKit bugs 199134 and 316640.
