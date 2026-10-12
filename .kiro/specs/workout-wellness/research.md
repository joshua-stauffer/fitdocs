# Research & Design Decisions — workout-wellness

## Summary
- **Feature**: `workout-wellness`
- **Discovery Scope**: Extension (a new region, a pure renderer and a
  whole-root pass on top of the existing render, merge, CLI and index
  machinery; upstream seams from `wellness-store` and `recovery`, which are
  specs on this branch and not yet code).
- **Key Findings**:
  - The established way to change part of a workout page without
    re-rendering it is a region plus a pass that rewrites only that region:
    the training-load pass and `load/docedit.py` (`replace_load_region`,
    `src/fitdocs/load/docedit.py:208-243`). A full re-render reads and decodes
    every listed `.fit` file (`src/fitdocs/sync.py:1940-1955`).
  - The analytics index recomputes a page's computed values, which means
    decoding its `.fit` files again (`src/fitdocs/index/refresh.py:227-262`),
    whenever the page's render fingerprint moves
    (`src/fitdocs/index/refresh.py:297-311`); the render fingerprint blanks
    exactly `contract.PRESERVED_REGIONS` (`src/fitdocs/index/fingerprint.py:40-58`).
    Block text outside a blanked region would make every wellness backfill
    re-decode every touched page's `.fit` files in the index post-pass.
  - `contract.DOC_BANNER` is shared by workout, history, block, planned and
    (planned) recovery pages (`src/fitdocs/render/views.py:192`,
    `src/fitdocs/history/page.py:693`, `src/fitdocs/plans/page.py:228`) and
    states "everything outside the notes/workout/load regions is replaced on
    regeneration" (`src/fitdocs/contract.py:810-813`). Adding the block as a
    *preserved* region would make that sentence false and force a banner
    change on five page types; a region whose content fitdocs replaces keeps
    it true.

## Research Log

### How a page is rewritten today
- **Context**: Requirement 7 (refresh without a full regeneration).
- **Sources Consulted**: `src/fitdocs/sync.py:1818-2121` (`_page_task`),
  `src/fitdocs/docmerge.py:119-162` (`merge_regions`),
  `src/fitdocs/load/engine.py:603-684` (`_discover_workout_docs`,
  `_atomic_write`), `src/fitdocs/docio.py:94-117` (`read_document`).
- **Findings**:
  - `_page_task` reads the existing page once, renders a fresh page, carries
    every region present in both through `merge_regions` (the merge reads no
    policy; it carries every region the fresh render defines,
    `docmerge.py:119-134`) and writes unconditionally
    (`sync.py:2336-2339`).
  - The load pass scans every `workouts/*.md` on every `sync`, drain and
    `regen` (`load/engine.py:56-71` and `:603-623`) and writes atomically
    through a same-directory temp file (`:666-684`).
  - `docio.read_document` is the one shared read with the symlink refusal
    (`docio.py:103-117`).
- **Implications**: the block is a region; the morning-of pass mirrors the
  load pass (scan, classify, splice, atomic write). A whole-root pass is the
  codebase's norm, not an exception.

### Measured scan cost
- **Context**: Requirement 7.5 (bounded cost, one pass).
- **Method**: synthetic probe (`<scratchpad>/workout-wellness/probe_scan.py`):
  2,500 copies of `tests/render/golden_docs/stryd_run.md` read with
  `read_text`, `contract.parse_frontmatter`, `document_date`,
  `document_version` and `docmerge.extract_regions`, on the worktree's
  interpreter.
- **Findings**: 1.13 s for 2,500 pages, 0.45 ms per page (warm cache, local
  disk). The block computation is bounded by `recovery`'s cost note: `on()` is
  O(`LOOKBACK_DAYS`) map lookups (`recovery/design.md:579-580`), nine metrics
  per page at most.
- **Implications**: a whole-root pass costs about the same as one more scan
  of the kind the load pass and the index already make on every run. No
  persisted "last pass" state is needed; the pass is self-healing after an
  interrupted run.

### Where the block may sit
- **Context**: Requirement 1.1.
- **Sources Consulted**: `src/fitdocs/render/views.py:196-311`,
  `src/fitdocs/contract.py:828-850` (`PRESERVED_REGIONS` is "in document
  order" and equals `USER_REGIONS + TOOL_REGIONS`, pinned by
  `tests/test_contract.py:69-70`).
- **Findings**: `## Training Load` is present on every view
  (`views.py:239, 272, 308`); regions sit at column zero and docmerge
  recognises only `fitdocs:begin|end:<id>` lines (`docmerge.py:63-66`).
- **Implications**: placing the block immediately before `## Training Load`
  gives one insertion point on every view. Because the morning region is not
  a preserved region, `PRESERVED_REGIONS`' order and definition are untouched.

### Absence marker and formatting
- **Sources Consulted**: `src/fitdocs/render/format.py:33` (`ABSENT = "–"`,
  en dash, tables only), `src/fitdocs/render/charts/kit/format.py:19` (the
  kit's own `ABSENT` is an em dash), `:116-149` (`format_value`), `:202-204`
  (`escape_markdown`); `src/fitdocs/units.py:41-61` (`bpm` and `ms` 0
  decimals, `s` a duration).
- **Implications**: figures go through `format_value` exactly as the recovery
  page formats them (recovery design § Seams: "numbers formatted like the
  page"); an absent cell is the workout pages' en dash, never the kit's em
  dash (`format_value(None, …)` is never called).

### Garmin attribution
- **Sources Consulted**: `.kiro/specs/intervals-connector/research.md:97-133`
  (intervals.icu API terms §1.1, Garmin API Brand Guidelines),
  `.kiro/specs/wellness-pull/requirements.md:94-96` and
  `design.md:1347-1350` (rendering is recovery's and workout-wellness's),
  `src/fitdocs/render/attribution.py:17-66` (the page-title line's wording).
- **Findings**: derived figures count ("information derived from
  Garmin-sourced data"); combined data must list Garmin as a contributing
  source and never imply Garmin vouches for other data; the attribution goes
  directly beneath the heading of the data view. `recovery`'s requirements
  and design never mention Garmin (`grep -n -i garmin
  .kiro/specs/recovery/{requirements,design}.md` returns nothing): its page
  prints origins in a "Sources shown" line but no attribution beneath its
  title and none in its chart images.
- **Implications**: the block decides attribution from the origins of every
  value its printed figures are computed from (the day, the 7-day window, the
  60-day window), not only the day value's origin. The recovery gap is
  reported to the controller for cross-spec review.

### Upstream seams consumed
- **wellness-store** (`design.md § Seams for downstream specs`, `:1485-1692`):
  `read_series`, `SeriesReadError`, `WellnessSeries.by_source`, `METRICS[m]
  .label/.unit`; the day-boundary rule (`:1608-1618`). Not used:
  `WellnessSeries.day_digest` and `SeriesReport.days` (see Decisions).
- **recovery** (`design.md § Seams for downstream specs`, `:1102-1137`):
  `Baselines.of`, `shown`, `shown_source`, `on`, `BaselineDay`,
  `RangePosition`, `METHODS`, `BASELINED_METRICS`, `SLEEP_METRICS`. Not used:
  `baseline_key` (see Decisions). Recovery's SleepView rule for stage rows
  ("`baselines.on(m, s, night)` for each `m` in `SLEEP_METRICS` that source `s`
  records that night", `:616-619`) is reused unchanged.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Generated section, full re-render of affected pages | Block rendered by `render_document`; the pass re-renders whole pages | Brief's wording ("at page-render time") | Decodes every affected `.fit` file twice (render, index); ~2,500 decodes after a backfill; needs wellness inputs threaded through `sync`/`drain`/`regen` | Rejected: cost |
| B. Generated section spliced by heading anchors | Block outside regions; pass finds `## Morning Of` and the next heading | Banner unchanged | New ad-hoc anchor grammar; insertion logic when absent; index re-decodes on every block change | Rejected |
| C. Preserved tool region (the `load` precedent) | `morning` in `TOOL_REGIONS`, carried verbatim, filled by a pass | Exact precedent; index blanks it for free | Banner on five page types becomes false and must change; "preserved" contradicts generated content; hand edits would need protecting | Rejected |
| **D. Refreshed region** | `morning` in a new `REFRESHED_REGIONS` class: delimited like a region, content always fitdocs's, refreshed by a pass after every page-writing run; index blanks it | Region grammar and damage detection; banner stays true; index cost avoided by one-line amendment; no `.fit` read | New region class in the contract (contract version bump) | **Selected** |

## Design Decisions

### Decision: A refreshed region filled by a whole-root pass
- **Context**: Requirements 7, 9.5, 10.1.
- **Alternatives Considered**: A, B, C above.
- **Selected Approach**: a fresh render emits an empty `morning` region; the
  sync/regen merge carries its previous content like every region; the
  morning-of pass, chained after every page-writing run, replaces the region
  with the current block whenever the bytes differ.
- **Rationale**: no `.fit` decode, one pass, byte-local writes, the index
  blanks the region, the shared banner stays true.
- **Trade-offs**: a brand-new page is written twice in its first run (render,
  then pass); a page's block is stale between the page write and the pass in
  the same run, and stays as it was when the series is unreadable.

### Decision: Compare the block's bytes; fingerprint the printed facts
- **Context**: Requirement 6 and the controller's churn rule.
- **Alternatives Considered**:
  1. Fingerprint `day_digest(D)` plus `baseline_key` of each shown signal
     (full precision), rewrite when it moves.
  2. Fingerprint the printed facts; rewrite when the block's bytes differ.
- **Selected Approach**: 2. The stamp line carries the block format version
  and a SHA-256 of the canonical printed facts; the pass rewrites a page only
  when the fresh region content differs from the stored content.
- **Rationale**: `day_digest` covers every metric of the day, including
  steps, weight and ratings the block does not show; `baseline_key` changes
  for differences below the printed precision (a past-day revision moves
  every 60-day mean of the next 60 days by a fraction of a beat). Option 1
  rewrites pages whose visible block did not change: churn in the
  maintainer's git and iCloud wiki that the brief forbids.
- **Trade-offs**: `day_digest` and `baseline_key` stay unused; equality of
  printed facts is the stronger churn guarantee.

### Decision: The pass visits every page; `SeriesReport.days` is not an input
- **Context**: controller notes name `SeriesReport.days` and the X..X+60
  bound as the targeted re-render input.
- **Selected Approach**: the pass reads every workout page (0.45 ms/page
  measured) and rewrites only those whose block changed. The X..X+60 bound is
  a test oracle (Requirement 7.4), not a page filter.
- **Rationale**: a days-driven filter misses pages after an interrupted run
  (series rebuilt, pass not finished: the next drain reports the series
  unchanged), after `fitdocs sync SOURCE` writes new pages (no rebuild, no
  days), after a change of `[wellness]` precedence handled by `regen`, and
  after a fitdocs upgrade that changes the block format or
  `BASELINES_VERSION`. Mapping days to pages needs the page scan anyway,
  since pages are matched by frontmatter, not file name.
- **Trade-offs**: about one second per 2,500 pages on every page-writing run,
  also for athletes with no wellness.

### Decision: Placement immediately before Training Load
- **Rationale**: after the activity's own data (summary, map, telemetry,
  splits) and beside the training load; does not push the hero chart down;
  one insertion point on every view.

### Decision: Attribution from the windows' origins
- **Rationale**: a 7-day mean or normal range computed from Garmin-origin
  values is derived Garmin data even when the day's own value is absent or
  from another platform. Values with no recorded origin make the line
  "contributing", never "sole".

### Decision: Contract and version numbers
- `DOC_VERSION` main + 1 (every page gains the region).
- `CONTRACT_VERSION` main + 1: a new region class, a new overwriting
  operation, and the re-derivability statement now includes the wellness
  archive (wiki-contract Req 2.3, 2.5, 2.6).
- Index `SCHEMA_VERSION` unchanged: no table, column or producer derivation
  changes; only when computed values are recomputed.
- Compatibility class (docs/compatibility.md:36-44): additive. No prose an
  existing document owns moves; a new document-format version resolved by
  `fitdocs regen` alone.

## Risks & Mitigations
- **The merge carries a stale block until the pass runs** — every
  page-writing flow runs the pass before the index post-pass; an unreadable
  series is reported, and the next run with a readable series refreshes.
- **A markdown formatter (Obsidian linter) reformats the block table** — the
  next pass rewrites it; the ownership contract states edits there are
  replaced.
- **Stage values from another source leaking in** — stage rows come only from
  the shown source of total sleep (recovery's SleepView rule); pinned by a
  two-source fixture.
- **Block figures drifting from the recovery page** — the block calls
  `Baselines.shown`/`on` and `format_value` with the metric's unit; a test
  compares every printed figure with the formatted `BaselineDay` fields.
- **Upstream not on main** — tasks start with an upstream verification task
  that stops on drift.

## References
- `.kiro/specs/wellness-store/design.md` § Seams for downstream specs.
- `.kiro/specs/recovery/design.md` § Seams for downstream specs and § View.
- `.kiro/specs/intervals-connector/research.md` § Terms and attribution.
- `.kiro/specs/channel-merge/tasks.md` task 5.1 (the DOC_VERSION advance
  precedent and its pin list).
