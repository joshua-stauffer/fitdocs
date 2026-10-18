# Implementation Plan

## Upstream Prerequisites

- **Base.** Planned at `b7bb293` (chore/p12-workout-wellness, off
  chore/p12-spec-batch `c2a7908`). Implementation starts only when
  **`wellness-store` and `recovery` are both implemented and on `main`**.
  `wellness-pull`, `apple-health-import`, `hr-derivation` and `dashboards`
  may land first. Every version constant, amendment number and criterion
  number in this plan is **main + 1 (or next free) at landing**, re-derived in
  5.1 after the final rebase; every list it touches is append-only and keeps
  both sides on rebase.
- **Verify before building on it** (1.1 records each outcome with file and
  line in Implementation Notes; stop and report on drift):
  - the wellness facade exports `read_series`, `SeriesReadError`,
    `WellnessSeries` (`values`, `is_empty`, `by_source`), `SeriesValue`,
    `Metric` and `METRICS` with `MetricInfo.label` and `.unit`;
  - wellness-store's sanctioned series builder
    `tests/wellness/builders_series.py::write_series(data_root, values)`,
    its delivery builders `tests/wellness/builders_intervals.py` (the
    delivery envelope) and `tests/wellness/builders_garmin.py` (a sleep file
    with stages), and that the drain rebuilds the series before it writes
    pages and `regen` rebuilds it first and prints its summary after the
    regen table (wellness-store design § DrainWellnessStep, § CliWellness);
  - the recovery facade exports `Baselines` (`of`, `on`, `shown_source`,
    `shown`), `BaselineDay` (the thirteen fields of recovery design
    § Baselines), `RangePosition`, `METHODS` (`rolling_days`,
    `baseline_days`), `BASELINED_METRICS`, `SLEEP_METRICS`; and that
    `fitdocs.recovery.page._FORBIDDEN_PHRASE_PATTERN` exists (tests import
    it);
  - `fitdocs.render.charts.kit.format.format_value(value, column, *,
    with_unit)` and `escape_markdown`, `fitdocs.render.format.ABSENT` (en
    dash) exist as the design cites them, and recovery's append-only
    additions to `fitdocs.render.attribution` are on `main`:
    `GARMIN_ORIGIN`, `WellnessAttribution` (`NONE`, `SOLE`,
    `CONTRIBUTING`), `wellness_attribution(origins: Iterable[str | None])`
    and `wellness_attribution_line(attribution)` (Phase 12 cross-spec
    settlement, I-1);
  - the CLI flow lines the design cites (`cli.py` explicit sync, 
    `_run_drain_passes`, `regen`) and, when `dashboards` is on main, where
    `_run_dashboard_pass` sits.
- **Upstream changes are not this plan's.** A need for anything
  `wellness-store` or `recovery` does not provide is a stop-and-report for
  the controller (an amendment to that spec), never a local workaround.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Amendments), each appended by the task that makes the change as
  `## Amendment N (<date>): <title>, landed by workout-wellness` with a
  `spec.json` entry naming the pinning tests: analytics-index (1.4),
  workout-docs (4.1), wiki-contract (4.2).

**Hard rules for every task**

- **Absent is `None`.** No morning code prints a zero, an empty string or a
  default for an absent figure; an absent cell is
  `fitdocs.render.format.ABSENT` (en dash), and `format_value` is never
  called with `None` (the kit's own absent text is an em dash).
- **No clock, no machine timezone, no network** anywhere under
  `fitdocs.morning`: no `date.today`, `datetime.now`, `time.*`,
  `astimezone()`, `urllib`, `socket`, `http`. 1.1 creates the guard.
- **Imports follow design § Allowed Dependencies.** `block` and `docedit`
  are independent; `engine` imports both; only `fitdocs.cli` imports
  `fitdocs.morning.engine`; no `fitdocs.render` module imports
  `fitdocs.morning`; no morning module imports `sync`, `index`, `query`,
  `load`, `history`, `ingest`, `connectors`, `tiles`, `duckdb` or any
  `fitdocs.wellness.*` / `fitdocs.recovery.*` submodule.
- **Consume, never re-own.** Every figure and the shown source come from
  `Baselines.shown` / `Baselines.on`; labels and units from `METRICS`;
  windows from `METHODS`. No mean, SD, range, position, source choice,
  label table, unit list, literal 7 or literal 60 in `fitdocs.morning`.
- **Synthetic data only.** A series on disk goes only through
  `write_series`; an in-memory series is
  `WellnessSeries(values=tuple(sorted(values)))`. Sole exception: task
  2.3's reordered-input facts/fingerprint test may construct
  `WellnessSeries(values=tuple(reversed(first.values)))` from an otherwise
  valid sorted synthetic series, preserving every value, unique
  `(day, metric, source)` key and exactly one canonical value per
  `(day, metric)`; assert the input tuples differ. Shared builders stay
  unchanged; this exception applies only to that in-memory comparison.
  A staged series has no
  archive entries, so a drain or `regen` rebuilds it away: tests that drain
  or regenerate stage wellness through synthetic inbox deliveries, and tests
  that keep a staged series use `fitdocs sync SOURCE` (no rebuild). No
  maintainer value appears in the repository.
- **Writes only through `morning.engine`**, atomically, to existing
  `workouts/*.md` files, never through a symlink. No test writes outside its
  `tmp_path`.
- **Faking the date.** Determinism tests switch `TZ` and use the history
  precedent's in-process `time.time` fake (`tests/test_history_e2e.py:212`,
  `_fake_system_date`), copied locally.
- **Linux-CI portable.** `tmp_path` only; child processes get
  `{**os.environ, …}`; permission-based tests skip when running as root.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination): each named mutation applied, observed red,
  reverted by restoring a `cp` taken before it, observed green, recorded in
  Implementation Notes; one that cannot be made red is reported UNPINNED.
  Before submitting, run the prose-claim grep over changed test files and
  re-run or delete every surviving claim.
- **Fixtures discriminate.** Pairwise-distinct values where a mapping is
  asserted; two sources whose values differ on every shared day;
  arithmetic and geometric means that differ; the interesting day not first;
  an asserted end state shown false beforehand; "nothing written" asserted
  on bytes *and* `st_mtime_ns`.
- **Parallel streams.** `(P)` tasks run in separate worktrees and touch only
  their `_Boundary_`.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in
  the same worktree** (`tests/test_bytecode_hygiene.py`).
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`.
- **Types and lint.** Each task runs `uv run mypy`, `uv run ruff check` and
  `uv run ruff format --check`.
- **Stop and report** on any need for: a runtime dependency; an edit to
  `docmerge`, `sync`, `load`, `fitdocs.wellness` or `fitdocs.recovery`; a
  change to `DOC_BANNER` or `PRESERVED_REGIONS`; a write outside
  `workouts/*.md` from the pass.

## Shared source files

Each file below has more than one writer; its writers are sequential.

- `src/fitdocs/contract.py`: 1.2 (region constants), 4.1 (`DOC_VERSION`),
  4.2 (`CONTRACT_VERSION`).
- `src/fitdocs/morning/block.py`: 2.1 creates it, 2.2 and 2.3 extend it.
- `tests/morning/builders.py`: 1.1 creates it (series builders); 1.3
  appends the page builder (it needs the region constants and the views'
  layout); frozen afterwards. 2.1 runs alongside 1.3's append and never
  edits it: 2.1, 2.2 and 2.3 keep their own fixture helpers in their own
  test modules.
- `tests/test_contract_consumers.py`: 1.2 (the region-literal scan), 1.3
  (the `fitdocs.render.sections` binding entry), 3.1 (the two morning
  modules in `CONVERTED_MODULES` and `CONTRACT_BINDINGS`).
- `tests/index/test_fingerprint.py`: 1.4 only (1.3 does not touch it, even
  when its grep lists it).
- `tests/morning/test_e2e.py`: 3.3 creates it; 4.1 appends the aged-page
  section.
- `tests/morning/test_boundary.py`: 1.1 creates it (allowed-import upper
  bounds over the modules on disk, `assert scanned`); 3.2 adds the literal
  module-set pin and switches both forward import sets and reverse importers
  to equality.
- `tests/render/golden_docs/*.md`: 1.3 (the empty region), 4.1 (the
  `doc_version` line).
- `tests/declaration_golden/*.AGENTS.md`: 4.2 only.
- `src/fitdocs/cli.py`: 3.2 only.
- `tests/render/test_views.py`: 1.3 (morning placement and pre-region
  frontmatter digest pins), 4.1 (the digest pins' controlled `doc_version`
  re-pin); 5.1 repeats the re-pin only if the final rebase changes the
  landing version.
- `tests/test_confinement.py`: 3.3 only.
- `pyproject.toml`: 1.1 (`tests/morning` in `[tool.mypy].files`).
- `CHANGELOG.md`: 4.3 only.

## Cross-spec shared files (append-only, keep both sides on rebase)

`DOC_VERSION` and `CONTRACT_VERSION` with their history paragraphs; every
render golden's `doc_version` line and every declaration golden's version
line; `tests/test_public_api.py` (`_CONTRACT_SURFACE`);
`tests/test_contract_consumers.py`; `WRITING_ENTRY_POINTS`; the CLI flow
blocks in `cli.py` (explicit `sync`, `_run_drain_passes`, `regen`: keep
wellness-store's rebuild and summary lines and dashboards'
`_run_dashboard_pass` after the index pass); `docs/ownership-contract.md`
head paragraph and the "What changed" pin
(`tests/identity/test_contract_docs.py:177-187`); `CHANGELOG.md` Unreleased;
`.kiro/steering/structure.md`; the workouts skill and
`tests/test_agent_skill.py`; `[tool.mypy].files`; the workout-docs,
wiki-contract and analytics-index amendment and criterion numbers.

## Test File Ownership

- `tests/morning/__init__.py`, `builders.py`, `test_boundary.py` (first
  half): **1.1**.
- Region-constant pins in `tests/test_contract.py`,
  `tests/test_public_api.py`, `tests/test_contract_consumers.py` (the
  region-literal scan): **1.2**; its `fitdocs.render.sections` binding entry:
  **1.3**; its morning-module registrations: **3.1**.
- `tests/render/test_views.py` additions and every pre-existing test that
  pins a fresh page's exact region set or section order (a grep for
  `extract_regions(` and `_headings(` over `tests/` decides);
  `tests/render/golden_docs/*.md`: **1.3**.
- `tests/index/test_fingerprint.py` (the region parameter list and the
  refreshed-region case), the refresh-level case in
  `tests/index/test_refresh.py` (or the module the grep shows owns
  `reconcile` tests): **1.4**.
- `tests/morning/test_block.py`: **2.1** (rows, figures, windows, sleep),
  **2.2** (sources, attribution). `tests/morning/test_render.py` and
  `tests/morning/golden/`: **2.3**. `tests/morning/test_docedit.py`: **2.4**.
- `tests/morning/test_engine.py`: **3.1**.
  `tests/morning/test_cli_morning.py` and the boundary guard's closing pins:
  **3.2**. `tests/morning/test_e2e.py`, the confinement entry point and its
  registration test, the `tests/test_portability.py` allowlist and its
  filled-block case: **3.3**.
- DOC_VERSION literal re-pins (`tests/render/test_frontmatter.py:106`,
  `tests/load/test_render.py:188`, `tests/index/test_contract_docs.py:178`,
  `tests/index/derived/test_preserved.py:245`,
  `tests/metrics/test_sources.py:2270`, grep decides), the aged-page e2e:
  **4.1**.
- `tests/test_ownership_contract.py`, `tests/identity/test_contract_docs.py`
  and every peer head-paragraph pin present at landing,
  `tests/index/test_contract_docs.py:140`,
  `tests/index/derived/test_preserved.py:246`, `tests/test_declaration.py`,
  `tests/declaration_golden/*`: **4.2**.
- `tests/morning/test_docs_morning.py`, `tests/test_agent_skill.py`
  re-pins: **4.3**.

---

- [x] 1. Foundation: package, contract constants, region placement, index blanking

- [x] 1.1 Verify the upstream seams and create the morning package skeleton with its boundary guard
  - Verify the Upstream Prerequisites list and record each outcome with file
    and line in Implementation Notes (stop and report on drift).
  - `src/fitdocs/morning/__init__.py`: a docstring-only module stating the
    package's purpose and design § Allowed Dependencies.
  - `tests/morning/__init__.py` and `tests/morning/builders.py`: in-memory
    series builders (per-source daily values with pairwise-distinct
    patterns, a chosen origin per value, a canonical flag per day and
    metric, `WellnessSeries(values=tuple(sorted(values)))`) and a
    `stage_series` wrapper over `write_series`. The page builder is 1.3's.
  - `tests/morning/test_boundary.py`: an allowed-import table per design
    module, applied as a subset check to the modules present on disk
    (`assert scanned`); a forbidden-name scan, a clock scan and a network
    scan, each with a positive control on a synthetic module. Missing
    allowed imports are permitted during staging; unlisted modules and
    imports outside the table are always rejected. Task 3.2 closes forward
    import sets to equality.
  - `pyproject.toml`: append `tests/morning` to `[tool.mypy].files`.
  - **Mutations:** a synthetic `from fitdocs import sync` module, a
    `date.today()` call and an `urllib` import each red their scan
    (positive controls); point the walk at an empty directory (`assert
    scanned` reds).
  - **Observable:** `import fitdocs.morning` succeeds and loads no other
    `fitdocs` module; `uv run pytest tests/morning` green; Implementation
    Notes list every verified seam with file and line.
  - _Requirements: 12.1, 12.2, 12.4_

- [x] 1.2 Add the morning region to the contract's region policy
  - `contract.py`: `MORNING_REGION = "morning"`, `REFRESHED_REGIONS =
    (MORNING_REGION,)`, `MORNING_PLACEHOLDER = ""` with design § ContractRegion
    docstrings; `__all__`. Rewrite every docstring sentence the third class
    makes false (design § ContractRegion): the "Policy versus mechanism"
    paragraph (`contract.py:18-19`, "the three region ids", "one algorithm,
    not three"), "Region ownership" (`:69`, "Three regions survive
    regeneration verbatim"; it gains the refreshed class), "Fresh-region
    content" (the empty placeholder), the `TOOL_REGIONS` docstring (`:841`)
    and the `PRESERVED_REGIONS` docstring (`:844`). `USER_REGIONS`, `TOOL_REGIONS`, `PRESERVED_REGIONS` and
    `DOC_BANNER` are unchanged.
  - **Tests**: `tests/test_contract.py` pins the three values,
    `REFRESHED_REGIONS` disjoint from `PRESERVED_REGIONS`, and
    `PRESERVED_REGIONS` still `("notes", "workout", "load")`;
    `tests/test_public_api.py` `_CONTRACT_SURFACE` gains the three names;
    `tests/test_contract_consumers.py`'s region-literal scan covers
    `PRESERVED_REGIONS + REFRESHED_REGIONS` over `fitdocs/render` and
    `fitdocs/morning`, with a synthetic module spelling `"morning"` caught
    (positive control).
  - **Mutations:** add `MORNING_REGION` to `TOOL_REGIONS` (the disjointness
    and preserved-set pins red); `MORNING_PLACEHOLDER = " "` (its pin reds);
    drop `REFRESHED_REGIONS` from the literal scan (the positive control
    reds).
  - **Observable:** `fitdocs.contract.REFRESHED_REGIONS == ("morning",)`;
    full `uv run pytest tests/test_contract.py tests/test_public_api.py
    tests/test_contract_consumers.py` green.
  - _Requirements: 1.1, 9.5_

- [x] 1.3 Place the empty morning region immediately before Training Load in every view
  - `render/sections.py`: `morning_region()` returns
    `region_block(MORNING_REGION, MORNING_PLACEHOLDER)`.
  - `render/views.py`: the run/ride, strength and generic views append
    `morning_region().rstrip("\n")` as its own block immediately before the
    Training Load block; module and view docstrings gain the region in the
    section order and the one exception to "headings outside regions"
    (design § RegionPlacement).
  - `tests/morning/builders.py`: append the synthetic workout-page builder
    (a frontmatter document with `type: workout`, `doc_version`, an optional
    `date`, the notes, `morning` and load regions laid out as the views lay
    them out, and a `## Training Load` heading) and a helper rendering a real
    page through `render_document` from `tests/fixtures/builder` bytes.
  - Regenerate `tests/render/golden_docs/*.md` with
    `uv run python -m tests.render.test_golden_docs`; each golden's diff is
    the three added lines and their blank-line separator, nothing else.
  - Re-pin every pre-existing test that pins a fresh page's exact region set
    or section order (grep `extract_regions(` and `_headings(` over
    `tests/`), except `tests/index/test_fingerprint.py`, which is 1.4's;
    record the list in Implementation Notes.
  - `tests/test_contract_consumers.py`: the `fitdocs.render.sections` entry of
    `CONTRACT_BINDINGS` gains `MORNING_REGION` and `MORNING_PLACEHOLDER`.
  - **Tests** (`tests/render/test_views.py`): the region is the block
    directly before `## Training Load` in a run with splits, a run without
    splits, a ride, a strength page with and without sets, a generic page
    with and without telemetry; its content is empty; no fresh page has a
    `## Morning Of` heading; the page has no new frontmatter key (the
    frontmatter block is byte-identical to before this task).
  - **Mutations:** place the region after Training Load (order tests red);
    omit it from the strength view (its test reds); a non-empty placeholder
    (the empty-content test and every golden red); a local
    `MORNING_REGION = "morning"` in `sections.py` (the region-literal scan
    reds); separately rebind `MORNING_REGION = "".join(("morn", "ing"))`
    in `sections.py` (equal value but distinct object, the identity binding
    reds). Verify equality and nonidentity for the latter mutant;
    literal-string interning means the former need not fail identity.
  - **Observable:** full `uv run pytest` green (every page changes); every
    render golden carries the empty region before `## Training Load`.
  - _Requirements: 1.1, 1.6, 1.7_
  - _Depends: 1.2_

- [x] 1.4 Make a change confined to the morning region a document-only change in the analytics index
  - `index/fingerprint.py`: the render fingerprint blanks every region in
    `contract.PRESERVED_REGIONS + contract.REFRESHED_REGIONS`; a region in
    neither keeps its content in the digest.
  - Append the analytics-index amendment: `requirements.md`
    `## Amendment N (<date>): a change confined to the morning region is a
    document-only change, landed by workout-wellness` with criterion 5.8 and
    the glossary note on "rendering"; a `spec.json` `amendments` entry
    naming the two tests below.
  - **Tests**: `tests/index/test_fingerprint.py` adds `"morning"` to the
    region parameter list (a page whose morning region content differs keeps
    its render digest; the fixture page carries the real region since 1.3),
    after widening `_replace_region`'s assertion
    (`tests/index/test_fingerprint.py:60`, `region_id in PRESERVED_REGIONS`)
    to `PRESERVED_REGIONS + REFRESHED_REGIONS`; and
    `test_render_fingerprint_keeps_unmanaged_region_content` stays green; a
    refresh-level test: index a page, change only its morning region, refresh
    with `derive.derive_page` patched to raise, assert the refresh succeeds,
    the page's document fingerprint moved and its computed state is
    unchanged.
  - **Mutations:** drop `REFRESHED_REGIONS` from the blanked set (both tests
    red); blank every region including unknown ids (the future-region test
    reds).
  - **Observable:** `uv run pytest tests/index` green; `SCHEMA_VERSION` and
    `tests/index/test_schema_version.py` unchanged.
  - _Requirements: 10.1, 10.2_
  - _Depends: 1.3_

- [x] 2. The morning-of block (pure)

- [x] 2.1 (P) Compute the block's rows and figures from the shared baselines
  - `morning/block.py` per design § MorningBlock: `Windows`, `SignalRow`,
    `SleepRow`, `MorningInputs.of` (one `Baselines.of` per series; windows
    read from `METHODS`, `ValueError` when the block's methods do not share
    one pair), `MorningInputs.block(day)` (rows 1-4 of the normative
    algorithm); figures through `format_value` with the metric's unit; an
    absent figure is `None`. `RowSource` and attribution are 2.2's; this task
    fills a placeholder row source (source id only) that 2.2 replaces.
  - **Tests** (`tests/morning/test_block.py`): a row per baselined signal
    with a figure, in `BASELINED_METRICS` order, none for a signal without
    one; SDNN and rMSSD rows from two sources with pairwise-distinct values;
    a carried source (no value on D, a value two days earlier) gives the
    absent day value and names the carried source; every printed figure
    equals `format_value` of the matching `Baselines.shown(m, D)` field on a
    fixture whose arithmetic and geometric means differ. A separate
    dependency test wraps the real `WellnessSeries.canonical` method and
    asserts no calls during `MorningInputs` construction and signal-block
    computation; real `Baselines.shown` results still supply the expected
    figures. This guards the prescribed shared-baseline consumption path.
    On valid series, a correctly None-handled canonical lookup for a
    signal's day value is output-equivalent today, so the canonical-day-value
    mutation is killed by this architectural test, not by numerical recovery
    agreement. A 2-of-7 rolling
    window and a 29-of-60 baseline leave those figures `None`; sleep: two
    sources, the shown one with stages and the other with pairwise-distinct
    stages, only the shown source's stages appear, in `SLEEP_METRICS[1:]`
    order; a shown source without stages gives the total row alone; windows:
    a patched `METHODS` with `rolling_days=5` changes `Windows`, mismatched
    windows raise `ValueError`; a day far from any value, and a day holding
    only steps and weight, give `None`; the days bound: a resting-HR value on
    day X raised enough to move the printed normal range at X+60 (one value
    among about 60 must clear the 0-decimal rounding; record the chosen
    delta) changes `block(X)` and `block(X+60)`, asserted changed first, and
    leaves `block(X-1)` and `block(X+61)` equal, on a series with values on
    both sides.
  - **Mutations:** iterate `SLEEP_METRICS` for signal rows; map the rMSSD
    row to `hrv_sdnn_ms`; skip rows whose day value is `None`; take the day
    value from `series.canonical(m, D)`; compute the rolling mean locally
    with `statistics.mean`; `shown(m, D)` per stage instead of `on(m,
    shown_source, D)`; emit a stage row for an absent stage; a literal `7`
    for `rolling_days`; return a block with no rows instead of `None`.
  - **Observable:** `uv run pytest tests/morning/test_block.py` green.
  - _Requirements: 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 5.3, 7.4_
  - _Boundary: MorningBlock_
  - _Depends: 1.1_

- [x] 2.2 Attribute every row to its source and origins, and credit Garmin
  - `morning/block.py`: `RowSource` from the row's contributing days (design
    § MorningBlock "Row sources", windows from `Windows`) through a per-run
    `{day: origin}` map built once per `(metric, source)` from
    `series.by_source`; `block.attribution` is
    `render.attribution.wellness_attribution` over the union of the rows'
    origins plus one `None` when any row is `unattributed`. No local
    attribution enum, origin constant or line text.
  - **Tests** (`tests/morning/test_block.py`): origins are sorted and
    distinct; a Garmin origin only inside the 60-day window while the day
    value is `apple` gives `CONTRIBUTING`; all values
    `garmin` gives `SOLE`; one value with no origin among `garmin` values
    gives `CONTRIBUTING` and sets `unattributed`; no `garmin` value gives
    `NONE`; a row whose 60-day mean is absent does not count the 60-day
    window's origins; a `garmin` value exactly one day outside a window does
    not count: at D−(B+1) for a row with a 60-day mean, and at D−r for a
    rolling-only row (60-day mean absent), with `B` and `r` read from
    `METHODS`.
  - **Mutations:** read only `BaselineDay.origin`; drop the `None` added for
    an `unattributed` row (the unrecorded-origin case reds); count the
    60-day window when the 60-day mean is absent; widen the window by one
    day.
  - **Observable:** `uv run pytest tests/morning/test_block.py` green.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 2.3 Render the region text with its stamp and fingerprint
  - `morning/block.py`: `MORNING_BLOCK_VERSION`, `MORNING_HEADING`,
    `STAMP_PATTERN`, `MorningBlock.facts()` and `.fingerprint()`,
    `render_region` and `parse_stamp` exactly per design § The Region
    Content (parts joined by one blank line, a final newline, en dash for an
    absent cell, `escape_markdown` for labels, sources and origins, the
    attribution line from `render.attribution.wellness_attribution_line`).
    For `None`, return the literal `""` without a contract import or local
    placeholder constant; the final-newline rule applies only to nonempty
    region content.
  - `tests/morning/golden/`: one golden per shape (signals only, sleep only,
    both, Garmin sole, Garmin contributing, carried source), regenerated by
    `uv run python -m tests.morning.test_render` and read back byte-equal.
  - **Tests** (`tests/morning/test_render.py`): the goldens; the first line
    matches `STAMP_PATTERN` and `parse_stamp` returns the version and the
    fingerprint; the content ends with `"\n"`; `render_region(None) == ""`;
    differently ordered input value tuples give equal facts and equal
    fingerprints; the same case independently pins `facts()` to a
    hand-authored exact canonical JSON string, with keys ordered
    `attribution`, `day`, `signals`, `sleep`, `windows`; a resting-HR change
    below the printed precision gives equal fingerprints and byte-identical
    full region text, checked by independently runnable assertions;
    a change in a printed figure or an origin changes the fingerprint; a
    steps value on D changes nothing; an origin turning from unrecorded to
    one the row already lists, with no Garmin value anywhere, leaves the
    region text byte-identical (the row's `unattributed` flag is not a
    fact); no rendered golden matches
    `fitdocs.recovery.page._FORBIDDEN_PHRASE_PATTERN`, and the pattern
    matches a synthetic forbidden word (positive control); the sentence
    names D and both windows.
  - **Mutations:** in an audited isolated snapshot, temporarily carry the
    displayed rows' genuine `BaselineDay`s from `MorningInputs` into
    `MorningBlock` and fingerprint their `repr` instead of printed facts
    (one disclosed three-site mutant; both sub-precision fingerprint and
    full-region equality assertions red while printed facts/body remain
    equal; restore all temporary plumbing exactly); drop the final newline
    (golden and its test red); print `—` for an absent cell (golden reds);
    `sort_keys=False` in `facts()` (the exact canonical-JSON assertion reds;
    separately observe that the reordered-input facts/fingerprint
    equivalence companion stays green); omit the attribution line (Garmin
    goldens red); a local line
    string in place of `wellness_attribution_line` with different wording
    (Garmin goldens red); put
    `unattributed` back into the facts (the unrecorded-origin test reds).
  - **Observable:** `uv run pytest tests/morning/test_render.py` green; six
    goldens committed.
  - _Requirements: 1.5, 1.6, 5.1, 5.2, 6.1, 6.2, 6.3, 9.4_

- [x] 2.4 (P) Read and splice the morning region byte-locally
  - `morning/docedit.py` per design § MorningRegionEdit: `read_morning`,
    `replace_morning`, `MorningRegionMissing`.
  - **Tests** (`tests/morning/test_docedit.py`): round trip for empty,
    multi-line and backslash-and-`$1` content; every byte before the begin
    marker and after the end marker unchanged on a real rendered page with
    notes and load content; a page without the region (`None`, and
    `MorningRegionMissing` on replace); damaged markers raise `RegionError`
    from both.
  - **Mutations:** a string-template replacement (literal `\g<0>` in the
    backslash-and-`$1` fixture is expanded and the exact-output assertion
    reds; `$1` itself stays literal); replace the exact END token with
    `<!-- fitdocs:end:.* -->` under DOTALL (the greedy endpoint consumes
    through the later load END and the outside-byte assertion reds); skip
    the `extract_regions` validation (the damaged case reds). Broadening
    only the endpoint ID to `[A-Za-z0-9_-]+` remains GREEN on validated
    pages and is not claimed as a discriminator.
  - **Observable:** `uv run pytest tests/morning/test_docedit.py` green.
  - _Requirements: 7.3, 7.8_
  - _Boundary: MorningRegionEdit_
  - _Depends: 1.3_

- [x] 3. The morning-of pass and its wiring

- [x] 3.1 Run the pass over every workout page and rewrite only the regions that changed
  - `morning/engine.py` per design § MorningPass: `PageOutcome`,
    `MorningPage`, `MorningReport`, `run_morning_pass` (one
    `docio.read_document` per page, the version gate
    `version is not None and version > DOC_VERSION`, the region read,
    `document_date`, `render_region`, byte comparison, the atomic
    `.morning-*.tmp` write, per-page isolation).
  - `tests/test_contract_consumers.py`: register `fitdocs.morning.docedit`
    and `fitdocs.morning.engine` in `CONVERTED_MODULES` and
    `CONTRACT_BINDINGS` (the contract names each binds: `MORNING_REGION`
    for docedit; `DOC_VERSION`, `document_date`, `document_version`,
    `is_workout_document` for the engine), as hr-derivation 3.2 does for
    its engine.
  - **Tests** (`tests/morning/test_engine.py`, pages from the 1.1 builder
    and one real rendered page, series through `write_series`): the pass
    fills each page's region; a second pass writes nothing (bytes and
    `st_mtime_ns` unchanged, `unchanged` equals the page count); the days
    bound at page level: an origin changed on day X (it shows at X+60 through
    the 60-day window's source cell and attribution line, where a value
    change could round away) rewrites the pages dated X and X+60, asserted
    changed first, and leaves the pages dated X-1 and X+61 byte-identical;
    for every updated page
    the bytes outside the region are unchanged; an emptied series empties a
    filled region (`REMOVED`); a page without `date` keeps an empty region;
    a page with no `doc_version` and one with `doc_version: true` are
    refreshed when they carry the region and counted in `without_region`
    when not, never `newer` and never `FAILED`;
    a page with an older `doc_version` and no region is counted in
    `without_region`; a newer `doc_version` is counted in `newer` and
    untouched even with a stale block; damaged markers give `FAILED` and an
    untouched page while the next page is updated; a read-only `workouts/`
    directory gives `FAILED` for every page and leaves no temp file
    (skipped when running as root; a read-only page file would still be
    replaced, because temp-then-replace needs directory write permission,
    the precedent at `tests/plans/test_engine.py:746-763`); `os.replace`
    patched to raise `OSError` for one chosen page fails that page, leaves
    it byte-identical and no temp file, and the next page is still
    `UPDATED`; `os.replace` patched to raise `KeyboardInterrupt` leaves no
    temp file and the interrupt propagates; an `os.replace` spy records
    exactly one replace per updated page; a region whose body was edited by
    hand but keeps its stamp line is rewritten to the fresh block; a
    symlinked page and a
    non-workout `.md` are untouched and unreported; an unreadable series (a
    manifest naming a missing year file) leaves every page byte-identical
    and sets `unavailable`; `docio.read_document` is called once per page.
  - **Measurement** (controller ruling R4): 2,500 synthetic pages over three
    years and a 3-year, two-source series; time the first pass and the
    second (no-write) pass with `time.perf_counter` in a one-off script under
    the scratchpad, not in the suite; record both figures and the machine in
    Implementation Notes. Above 10 s for either pass is a stop-and-report.
    Memoizing `render_region` per date and skipping the block computation
    for an empty series (filled regions still cleared) are allowed if the
    figure calls for them.
  - **Mutations:** compare stamps only (the hand-edited-body test reds);
    skip the version gate (newer test reds); treat a `None` version as newer
    (the unusable-version tests red); write with `write_text` instead
    of the temp-and-replace (the `os.replace` spy reds); take the day
    from the file name (date test reds); a discovery read before the
    processing read (the call count reds); treat `RegionError` as
    `without_region` (damaged test reds); drop the temp-file cleanup (the
    `OSError` and `KeyboardInterrupt` cases red); a local copy of
    `is_workout_document` in the engine (the identity binding reds).
  - **Observable:** `uv run pytest tests/morning/test_engine.py
    tests/test_contract_consumers.py` green; the R4 figures are in
    Implementation Notes.
  - _Requirements: 1.3, 1.4, 6.4, 7.2, 7.3, 7.5, 7.6, 7.7, 7.8, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.5, 12.3_
  - _Depends: 2.3, 2.4_

- [x] 3.2 Chain the pass into sync, the drain, pull --sync and regen, and print its report
  - `cli.py` per design § CliMorning: `_run_morning_pass` (returns whether
    the pass failed; catches `Exception`, prints `Morning of: not refreshed;
    <ExceptionType>: <message>.`, fails the run and lets the load, plan,
    index and dashboard passes run; `KeyboardInterrupt` propagates,
    controller ruling R3), `_report_morning` (exact lines; `page(s)`,
    `block(s)` and `has/have` agree with the count; the without-block line
    names both causes, an older fitdocs or removed markers), the three call
    sites after the page-writing report (in `regen`, after wellness-store's
    series summary)
    and before the load pass, the exit rule in each, the module docstring.
    Keep wellness-store's and dashboards' lines on rebase; the command count
    is unchanged.
  - Close the boundary guard: pin the literal set of morning modules,
    switch each module's non-standard-library import set from subset to
    equality against the unchanged allowed table, and close the reverse
    half by equality (only `fitdocs.cli` imports `fitdocs.morning.engine`;
    no `fitdocs/render` module imports `fitdocs.morning`). Add controls
    showing a missing allowed dependency fails forward equality and an
    extra dependency still fails.
  - Re-pin any pre-existing exact-output or page-byte assertion the new
    line or a filled block now moves (grep the drain and regen output pins,
    for example `tests/test_cli_drain_report.py` and wellness-store's
    `tests/wellness/test_cli_wellness.py`); record the list.
  - **Tests** (`tests/morning/test_cli_morning.py`, CliRunner; explicit-sync
    cases over a staged series, drain and regen cases over an archived
    synthetic delivery): each report line's exact text and its condition (updated,
    removed, failed, without-block only when the series has values, not
    refreshed); the without-block line reads exactly `Morning of: 1 page
    has no morning-of region (written by an older fitdocs, or the region
    markers were removed); run 'fitdocs regen' to add it.` for one page and
    `… 2 pages have …` for two; nothing printed when nothing happened; the
    exit fold, parametrized over `fitdocs sync SOURCE`, the drain (`fitdocs
    sync`; `pull --sync` shares its helper) and `fitdocs regen`: each exits
    1 when the pass failed a page and 0 otherwise; the `Morning of:`
    line follows the drain report and precedes the load table, in the drain
    and in `regen`; `fitdocs load`, `history`, `plan`, `check`, `index`,
    `query` and `recovery` leave a stale block byte-identical; an engine
    patched to raise `RuntimeError`, parametrized over the same three flows,
    prints the `not refreshed` line naming `RuntimeError`, still prints the
    load table and exits 1; an engine patched to raise a `KeyboardInterrupt`
    instance: called directly, `cli._run_morning_pass` re-raises it
    (`pytest.raises(KeyboardInterrupt)` with `raised.value is interrupt`,
    the precedent at `tests/index/test_cli_post_pass.py:583-600`), and
    through `CliRunner` (which turns an interrupt into `SystemExit(130)`)
    `fitdocs sync` exits 130 with no `not refreshed` line and no load
    table.
  - **Mutations:** drop the call from `_run_drain_passes` (drain test
    reds); leave `morning_failed` out of the exit in the explicit-sync
    `_finish` (its exit case reds), out of `_run_drain_passes`' return (its
    exit case reds), and out of `regen`'s `_finish` (its exit case reds),
    one mutation per call site; print the
    without-block line when the series is empty (reds); call the pass after
    the index pass (ordering test reds); a second importer of the engine
    (the reverse-half equality reds); let the `Exception` escape
    `_run_morning_pass` (the `RuntimeError` test reds); catch
    `BaseException` (both `KeyboardInterrupt` tests red: no re-raise, and a
    `not refreshed` line through the CLI); `have` for a count of one (its
    line test reds).
  - **Observable:** full `uv run pytest` green; `fitdocs --help` lists the
    same commands as before.
  - _Requirements: 7.1, 7.9, 8.1, 8.3, 8.4, 8.5, 8.7, 8.8, 9.2_

- [x] 3.3 Prove the block end to end and register the confinement entry point
  - **Tests** (`tests/morning/test_e2e.py`, CliRunner, `TZ` pinned):
    `fitdocs sync SOURCE` over `small_sport_fit_bytes` files on two dates
    with a staged series: both pages carry their block in the same run, a
    second run prints no `Morning of:` line and writes nothing; determinism:
    a copy of that root with its morning regions emptied, then `fitdocs sync
    SOURCE` again (nothing new to archive, so only the pass writes) under
    `TZ=Pacific/Kiritimati` with a faked system date, refills byte-identical
    blocks; the fixtures' start times fall on different calendar dates
    under the pinned `TZ` and under UTC+14 (asserted first), so a day read
    from the machine timezone would differ; drain: an inbox holding a FIT file and
    an intervals.icu delivery covering its day gives the block in the same
    run, then a second delivery revising one day rewrites only the affected
    page; a Garmin export sleep file gives stage rows and the `Data source:`
    line; with the index built first (`fitdocs index`), the same run's
    index post-pass holds the refreshed page (its document fingerprint
    equals the file's); a page with damaged markers
    makes `fitdocs sync` exit 1 and is named.
  - `tests/test_portability.py`: `_assert_document_invariants` runs on a
    page with a filled block; its HTML-comment allowlist (`:84-87`,
    `:142-145`) gains `STAMP_PATTERN` (imported from `fitdocs.morning.block`).
  - `tests/test_confinement.py`: entry point `sync-morning` (prepare: a
    source directory and a staged series; run: `fitdocs sync SOURCE`;
    non_vacuous: a page's `morning` region is non-empty) and its
    registration test, per the file's existing pattern.
  - **Mutations:** skip the pass in the explicit-source branch (the
    same-run assertion reds); read the machine timezone for the day (the
    `TZ` comparison reds); disable the pass entirely (`non_vacuous` reds the
    confinement entry); drop `STAMP_PATTERN` from the portability allowlist
    (the filled-block case reds).
  - **Observable:** `uv run pytest tests/morning tests/test_confinement.py
    tests/test_portability.py` green.
  - _Requirements: 1.2, 3.2, 4.2, 7.1, 7.2, 7.4, 9.4, 10.1, 12.3_

- [x] 4. Versions, the contract and the published text

- [x] 4.1 Advance the page-format version and record the workout-docs amendment
  - Read `DOC_VERSION` on the branch rebased onto `main`, advance it by one
    and append design § ContractRegion's paragraph; record the old and new
    values in Implementation Notes.
  - Move every literal pin of the old value (a grep for `doc_version: <old>`
    and `DOC_VERSION == <old>` decides; at design time
    `tests/render/test_frontmatter.py:106`, `tests/load/test_render.py:188`,
    `tests/index/test_contract_docs.py:178`,
    `tests/index/derived/test_preserved.py:245`,
    `tests/metrics/test_sources.py:2270`); regenerate the render goldens
    (each diff its `doc_version` line alone).
  - Also re-pin `_PRE_MORNING_FRONTMATTER_SHA256` in
    `tests/render/test_views.py`; these opaque version-sensitive pins are
    not found by the literal-version grep. For all seven unchanged fixture
    contexts, first verify the old frontmatter bytes against the existing
    digest, then require the new frontmatter bytes to equal those old bytes
    with exactly the single `doc_version: <old>` line changed to
    `doc_version: <new>`. Only after that comparison update the digest
    literals. Preserve the original capture provenance (`852e35f`, version
    9) and add the re-pin's old/new versions and version-line-only basis to
    the comment and Implementation Notes. Do not recapture hashes from
    current output without that independent comparison. Task 5.1 repeats
    this procedure if the landing version changes.
  - Aged page (`tests/morning/test_e2e.py` section, the
    `_PRE_CHANNEL_MERGE_DOC_VERSION` precedent): `_PRE_WORKOUT_WELLNESS_DOC_VERSION`
    with a provenance docstring; drain an inbox holding a FIT file and an
    intervals.icu delivery covering its day (the series is then rebuilt from
    the archive by every later drain and `regen`); age the page to the old
    version and remove its morning region; assert
    `DOC_VERSION > _PRE_WORKOUT_WELLNESS_DOC_VERSION`; `fitdocs check`
    reports it out of date; a second drain leaves it untouched and prints the
    without-block line; `fitdocs regen` restores the region with the current
    block; a second `fitdocs check` reports nothing.
  - Append the workout-docs amendment: `requirements.md`
    `## Amendment N (<date>): the morning region, landed by workout-wellness`
    with criteria 4.5, 6.13, 9.7, 10.6, 12.3, 13.5 (next free at landing,
    append only), and a `spec.json` entry naming each criterion's tests.
  - A literal pin on the `DOC_VERSION` history paragraph's content in the
    aged-page section, the adjacent docstring read the way
    `tests/identity/test_contract_docs.py:140-155` reads `CONTRACT_VERSION`'s:
    "Raised from ``N`` to ``N+1`` by workout-wellness" plus one sentence,
    with the landed numbers as literals (5.1 rewrites them after the final
    rebase).
  - **Mutations:** advance by two (the moved pins red); revert the advance
    (the aged-page precondition reds); drop the paragraph's sentence (the
    history pin reds).
  - **Observable:** full `uv run pytest` green; each render golden's
    pre-existing diff is one line.
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 4.2 Advance the ownership contract and publish the region and the pass
  - Advance `CONTRACT_VERSION` by one from the branch's value with design §
    ContractRegion's paragraph ("Raised from ``N`` to ``N+1`` by
    workout-wellness" plus its sentences); record the values.
  - `docs/ownership-contract.md` per design § Docs: version line, the "What
    changed at this version" paragraph, the head paragraph's list of
    enumerations held equal to code (`:25-28`, gains "refreshed regions"),
    the newer-version paragraph (`:1016-1020`, the morning-of pass also
    leaves such a document untouched), the new `## The Morning-Of Region`
    section (one backticked list item, `morning`), the pointer sentence in
    "User-Owned and Tool-Filled Regions" (its bullet list still equals
    `PRESERVED_REGIONS`), "What Regeneration Replaces and Preserves", the
    `sync`, `sync --force` and `regen` bullets and the new morning-of pass
    bullet in "Overwrite Semantics", and "Commit Ordering and
    Re-Derivability".
  - `declaration.py`: `_REDERIVABILITY_DOCS`, `_NEVER_ADD_MARKER` (its claim
    is false for an added `morning` marker, `declaration.py:264-268`) and
    their CLAIM ANCHORs per design § Declarations; regenerate the declaration
    goldens (`uv run python -m tests.test_declaration_goldens`): the
    workouts golden moves by both fragments and the version, the others by
    the version only.
  - Append the wiki-contract amendment (`requirements.md` `## Amendment N`
    with criteria 1.7, 2.17, 2.18, next free at landing; `spec.json` entry).
  - **Tests**: `tests/test_ownership_contract.py` — the new section's
    backticked items equal `REFRESHED_REGIONS`, the regions section still
    equals `PRESERVED_REGIONS`; `tests/identity/test_contract_docs.py` — the
    head-paragraph pin's phrases from the new paragraph, and a new pin,
    appended to `test_the_version_history_records_the_amendment`, on the
    history paragraph's content with LITERAL numbers ("Raised from ``N`` to
    ``N+1`` by workout-wellness" plus one sentence of it, `N` and `N+1`
    written as the landed numbers, never computed from the live
    `CONTRACT_VERSION`; 5.1 rewrites them after the final rebase); every peer "What changed at
    this version" head-paragraph pin present at landing (grep the outgoing
    paragraph's phrases; dashboards, wellness-store, recovery,
    wellness-pull, hr-derivation as they land) moved to an assertion on
    the history docstring the way its own spec retired its predecessor's;
    `tests/index/test_contract_docs.py:140` and
    `tests/index/derived/test_preserved.py:246` re-pinned;
    `tests/test_declaration.py` — the workouts declaration names
    `wellness/` and the morning region and trips no quantifier word, and a
    new pin holds `_NEVER_ADD_MARKER`'s qualifier ("a marker naming a region
    the regenerated document does not carry").
  - **Mutations:** list `morning` in the regions section's bullets (both
    region pins red); drop the morning sentence from `_REDERIVABILITY_DOCS`
    (its pin and the workouts golden red); restore the unqualified
    `_NEVER_ADD_MARKER` sentence (its new pin and the workouts golden red);
    advance by two (version pins red).
  - **Observable:** full `uv run pytest` green; `fitdocs check` on a fresh
    sync reports no declaration finding.
  - _Requirements: 9.3, 9.5, 11.1, 11.2, 11.3_

- [x] 4.3 Document the block in the wellness guide, the workouts skill, the release notes and steering
  - `docs/wellness.md`: the section "Wellness on workout pages" per design §
    Docs.
  - `src/fitdocs/skills/fitdocs-workouts/SKILL.md`: the `Morning of:`
    paragraph under "Reading the report" (what each line means, which need
    the athlete, `fitdocs regen` only when check or the release notes call
    for it); re-pin `tests/test_agent_skill.py` where its fences or
    paragraph pins move.
  - `docs/upgrading.md:83-87`: `regen` also reads the archived wellness
    files, through the wellness series it rebuilds first, for the
    morning-of block.
  - `CHANGELOG.md` `[Unreleased]`: Added and Changed entries naming
    `doc_version` N to N+1 with the action `fitdocs regen`, the contract
    version, and that a change confined to the block does not make the
    analytics index recompute a page's computed values.
  - `.kiro/steering/structure.md`: the `morning` dependency sentence.
  - The section does not restate the day-boundary rule: it says the block
    shows the wellness day equal to the page's date and links to the
    guide's own day-boundary section (wellness-store Req 7.6 pins that
    statement exactly once across `docs/`).
  - **Tests** (`tests/morning/test_docs_morning.py`): the wellness section
    links to the guide's day-boundary section (the link's anchor resolves to
    a heading in `docs/wellness.md`), names both windows, the absence
    marker, the Garmin line,
    when pages refresh, that edits are replaced and that it states no
    verdict; the skill paragraph names each report line; the upgrading
    page names the wellness archive among `regen`'s inputs; the CHANGELOG
    names both version changes with their values read from `contract`.
  - **Mutations:** delete the day-boundary link (its pin reds); restate the
    rule in the new section (wellness-store's exactly-once test in
    `tests/wellness/test_docs_wellness.py` reds); write the previous
    `doc_version` in the CHANGELOG line (reds).
  - **Observable:** full `uv run pytest` green.
  - _Requirements: 11.4, 11.5, 11.6_

- [ ] 5. Final validation

- [ ] 5.1 Rebase, re-derive every number, and run the exhaustive sweep
  - Rebase onto `main`; re-derive `DOC_VERSION` and `CONTRACT_VERSION` as
    `main` + 1 (with every pin, golden and paragraph that names them,
    including the two history-content pins, whose numbers are written as
    literals, append-only, never computed from the live constants), the
    three amendment numbers and their criterion numbers; keep both sides of
    every list in "Cross-spec shared files" and of the CLI flow blocks
    (wellness-store's rebuild and summary, dashboards' dashboard pass after
    the index pass, this plan's morning pass before the load pass).
  - Tick the roadmap's Phase 12 lines for `workout-wellness` and the
    `workout-docs` Existing Spec Update.
  - Run `uv run pytest && uv run ruff check . && uv run ruff format --check .
    && uv run mypy` after the rebase; check the branch CI before merging.
  - Exhaustive sweep: classify each of the 66 criteria PINNED (test and
    mutation), PRESERVED-ONLY (the pre-existing test) or UNPINNED (with the
    mutation run that shows it), in Implementation Notes; run the prose-claim
    grep over every changed test file.
  - **Observable:** the sweep table in Implementation Notes covers every
    criterion; the validation line green after the rebase.
  - _Requirements: 9.1, 9.4, 11.3, 12.1, 12.2_

## Implementation Notes

- Astra decision 13 (2026-10-18, task 3.3): native CLI/confinement
  evidence retains decision 10. A separate bounded exception permits
  minimal faults only in the new STAMP_PATTERN portability allowlist
  alternative, the sync-morning EntryPoint record (omission/id, one wrong
  callable, duplicate for exactly-once), and declared boolean conditions
  of a new directly tested morning predicate. These are checker/registry/
  predicate faults, not production kills. Preserve consumer assertions,
  fixtures, expectations, other implementation and configuration bytes;
  disclose differing mutant whole-file hashes and audit unchanged byte
  segments. Observe the intended failure, restore the whole file/hash and
  GREEN, purging test assertion-rewrite caches before each uv pytest
  process. Native pass-disabled confinement non-vacuity is independently
  required. No new unpinned acceptance waiver or broader boundary applies.
- Astra 13a: sync-morning may keep one private transient data-root slot
  in test_confinement.py. Prepare and run clear it; run publishes only
  after real CLI success. The predicate consumes/clears it before reading
  and requires the same measured touched workout page to have a nonempty
  actual morning region. Run does not assert that region outcome. A
  private explicit-root helper may separate direct content/touched
  controls; only declared N boolean spans are fault-eligible. Lifecycle,
  root capture and I/O remain outside that exception. No cwd, EntryPoint,
  shared harness, module or runtime interface changes. Review reset and
  isolation, and replay disabled production pass reaching the native
  non-vacuity assertion. The full decision defines lifecycle and read bounds.

  Decision artifact for 13 and 13a:
  `/private/tmp/workout-wellness-astra-portability-registry-faults.md`.

- 3.2 accepted after independent review and fresh completion verification:
  all three CLI flows run morning after their page report (regen after its
  wellness summary), before load, and fold morning failures into their exit
  status while continuing later passes. Full suites passed independently
  twice: 26,692 tests and eight documented optional local skips. Fresh
  completion checks passed 870 regressions and 176 isolated CLI/boundary
  cases, with Ruff, formatting and mypy clean. Independent replay confirmed
  58 source faults (154 observations), nine separately labeled guard-control
  faults (30 observations), and three reviewer source faults (six more);
  every intended failure restored GREEN. All nine assigned criteria and all
  41 changed assertion/setup sites are covered. Import boundaries are now
  closed to exact sets; native help is byte-identical with 15 commands.
  No pre-existing output or page-byte pin required changing. End-to-end
  timezone, portability and confinement work remains with 3.3.

- Astra decision 14 (2026-10-18, task 3.2): report composition is covered
  by two valid mixed cases: nonempty series with updates, removals,
  multiple failures and missing regions; empty series with removals and
  failures while the missing-region warning is suppressed. Retain exact
  hand-authored ordered output lists and all prior cases. The bounded
  sweep adds three production faults and extends existing selections,
  for 67 declared faults. Complete that sweep, the requirement mapping
  and preservation checks before freezing candidate bytes and running
  the full suite. Stop speculative expansion after these partitions are
  covered; reopen for concrete normative defects or verification/review
  failures. The decision is not execution evidence. Decision artifact:
  `/private/tmp/workout-wellness-astra-report-matrix-closure.md`.

- Astra decision 12 (2026-10-18, task 3.2): actual-source boundary pins
  retain decision 10's unchanged-test production-fault protocol. Synthetic
  closure-guard controls may use isolated minimal faults only in the
  forward/module/reverse closure implementation or a relevant independent
  literal policy member inside test_boundary.py. Clarification 12a permits
  the permanent same-file _guard_module_imports extraction; only those
  comparison/operand spans follow it, with delegation/control calls
  frozen during faults and native full-guard coverage checked separately.
  This is a bounded
  exception to production-source-only and whole-test-file identity, with
  no changes to control tests, fixtures, expected outputs or configuration.
  Record PINNED — GUARD-CONTROL separately from PINNED — SOURCE-BOUNDARY;
  preserve every byte outside declared implementation edits, show the
  intended unchanged control RED, restore the full original file/hash and
  show GREEN. Purge derived test assertion-rewrite caches before each
  uv pytest process. No assertion masking, entire-guard deletion,
  fixture-dependent fault, new helper module or broader boundary change
  is authorized. Review and final verification audit the partition and
  both evidence categories; decisions 10 and 11 otherwise remain in force.

- 3.1 accepted after independent approval and fresh completion verification:
  250 focused, 1,200 broader and seven shared-reader cases passed, with
  Ruff, formatting and mypy clean. All 78 claimed and three independent
  production faults failed their intended intact assertions and restored
  GREEN. The audit covers 100 assertion sites, 144 engine cases, sixteen
  registry observations and both exception-expectation sites (seven
  expanded observations). All 2,084 regular inputs and nineteen symlinks
  match the reviewed tree and isolated snapshots. All seventeen listed
  criteria and task-text 7.4 are pinned at engine scope, subject to the
  single auxiliary OS-preserved assertion exception below. CLI wiring and
  exact dependency closure remain with 3.2; whole-flow confinement with 3.3.
- R4 measurement for 3.1: Darwin 25.5.0 arm64, Python 3.11.15; 2,500
  populated pages over 1,095 distinct 2021–2023 days, two sources and three
  supported metrics per source (resting HR, HRV SDNN, sleep total), 6,570
  native-valid values / 357,168 series bytes. Input pages were 1,353 bytes
  each / 3,382,500 total. First pass 1.068884792 s, second 0.535227292 s;
  independent reviewer repeat 0.969967375 s / 0.499513792 s. Each produced
  2,500 UPDATED then 2,500 unchanged, with equal second-pass hashes/mtimes
  and no temporary leftovers. Both passes are below the 10 s threshold.
  Engine SHA256: bb235be2d3a2e3d73d1a96f456f6407ce3ce534eb105b20852bc36a88985ad8b.
- Astra decision 11 (2026-10-18, task 3.1): the read-only-directory
  no-temp assertion remains required but is UNPINNED — OS-PRESERVED,
  with an explicit acceptance exception confined to that assertion.
  Non-root directory denial prevents temporary creation before cleanup
  can run; deleting cleanup cannot discriminate this case. No chmod-and-
  orphan fault or cleanup credit is permitted. The intact non-root case
  ran GREEN; its other observables have ordinary discrimination evidence.
  BOTH actual-temp os.replace OSError and KeyboardInterrupt no-temp
  assertions independently failed cleanup deletion and restored GREEN.
  Decision 10 remains in force elsewhere. Carry this exception into the
  final sweep; requirement-level cleanup is pinned by the actual-temp cases.

- Astra decision 10 (2026-10-18, applied at task 3.1): acceptance
  discrimination runs keep the reviewed tests, fixtures and configuration
  intact. Every claimed assertion must itself fail under its permitted
  production fault; preceding failures do not count. Use narrow faults or
  permanently separate/parameterized observable cases to avoid masking.
  An experiment disabling assertions is diagnostic only and earns no
  acceptance credit. Preserve meaningful preconditions and refresh affected
  evidence after restructuring tests. This interprets the existing
  verification protocol, with no requirement or production-boundary change;
  the shared log records the decision and full report.

- 2.4 accepted after independent approval and fresh completion verification:
  19 focused tests, 340 morning/contract/load-editor regressions and all
  static checks passed. All 19 claimed and two independent production
  faults failed intended assertions and restored GREEN; all fifteen
  assertion sites and thirty expanded assertions are covered. The narrow
  generic-ID endpoint experiment remained GREEN across nineteen cases,
  as decision 9 predicts; the greedy DOTALL endpoint and literal group-zero
  template faults failed exact byte assertions. All 2,082 regular inputs
  and nineteen skill symlinks matched the reviewed tree and independent
  snapshot. The pure block/editor group is complete; file writes and
  contract-consumer registration remain with 3.1.

- Astra decision 9 (2026-10-18, applied at task 2.4): validation, an exact
  morning begin marker and a non-greedy body make a generic valid-ID end
  marker output-equivalent on valid pages. Record that narrower control
  GREEN; use the plausible DOTALL greedy endpoint wildcard consuming
  through the later load end marker to pin confinement. The replacement
  template control is discriminated by literal `\g<0>` expansion; Python
  leaves `$1` literal. Exact output/outside-byte assertions run before
  re-extraction, so exceptions cannot substitute for the intended failure.
  No production guard, API, dependency or requirement changes are needed;
  the shared log records the decision and report.

- 2.3 accepted after independent approval and fresh completion verification:
  51 renderer tests and 1,417 morning/recovery regressions passed, with all
  static checks clean. All 47 claimed and two independent mutations failed
  intended assertions and restored GREEN; all 24 assertion sites and 51
  expanded cases have observed RED evidence. All 2,080 regular inputs and
  nineteen skill symlinks match the reviewed live tree and isolated
  snapshot. Exact Unicode canonical JSON and SHA256 oracles, sparse signal
  cells, empty origins and escaping in both tables are pinned. The
  canonical-order mutant preserves equivalence while failing exact bytes;
  the disclosed raw-data hash mutant fails both sub-precision observables
  while printed facts/body stay equal. No raw state ships. Whole-pass
  machine/timezone/date determinism remains with 3.3; the full suite is
  still due at 3.2. Six byte-pinned markdown goldens are committed.

- Astra decision 8 (2026-10-18, applied at task 2.3): the empty region
  renderer returns literal `""`, with no final newline. Its value equals
  the contract placeholder, which region placement already consumes, but
  the pure block retains its approved dependency set without importing
  `fitdocs.contract` or adding a local placeholder constant. This clarifies
  the design's parenthetical and adds no requirement, API or guard change.

- Astra decision 6 (2026-10-18, applied at task 2.3): fixed insertion order
  remains deterministic without JSON key sorting, so equivalent inputs
  alone cannot pin canonical encoding. Retain their equality checks and
  independently assert a hand-authored exact canonical JSON string; the
  `sort_keys=False` mutation must fail the latter while equivalence stays
  GREEN. The sole synthetic-series ordering exception above permits the
  native input-order comparison without changing any value, key or
  canonical flag. Frozen builders and normative output/API are unchanged.

- Astra decision 7 (2026-10-18, applied at task 2.3): the shipped block
  intentionally discards raw figures after formatting. The requested raw
  baseline hash fault therefore uses one disclosed three-site mutant in an
  audited isolated snapshot: a temporary raw tuple field, a constructor
  argument populated by genuine `Baselines.on` results for displayed rows,
  and a fingerprint of that tuple's `repr`. Independently runnable
  sub-precision fingerprint and full-region equality assertions must both
  fail, while diagnostic facts/body comparisons stay equal. Exact
  restoration removes all temporary plumbing; no raw field or test hook
  ships. Requirements, science, public interface and region text are
  unchanged. The shared log records both decisions and their full reports.

- 2.2 accepted after independent approval and fresh completion verification:
  77 focused and 1,366 morning/recovery regression tests passed, with all
  static checks clean. All 43 claimed and two independent mutations failed
  at their intended assertions and restored GREEN; all 27 changed/new
  assertion sites have observed RED evidence. Native validation accepted
  all 5,175 fixture values; 2,073 regular inputs and nineteen skill symlinks
  matched the reviewed live tree and isolated snapshots. All six listed
  criteria are pinned at source/enum scope; rendering remains with 2.3.
  Cache controls change every metric's canonical source on the next day and
  use separate input instances, pinning both parts of the cache key and its
  per-run lifetime without prescribing lookup order or eager/lazy timing.

- 2.1 accepted after independent approval and fresh completion verification:
  45 focused and 1,334 morning/recovery regression tests passed, with all
  static checks clean. All 36 claimed and two independent mutations failed
  at their intended assertions and restored GREEN; all 2,073 snapshot inputs
  matched the reviewed tree. All seventeen listed criteria are pinned at
  the pure-row scope; attribution, rendering and page integration remain
  with their later tasks. The influence-bound fixture changes resting heart
  rate from 60 to 200 bpm (+140, within native bounds), which changes the
  printed range at X+60 before comparing nonempty X−1 and X+61 blocks.

- Astra decision 3 (2026-10-17, applied at task 2.1 on 2026-10-18): a
  correctly None-handled canonical signal day-value lookup is numerically
  equivalent to `Baselines.shown` on valid native series. Keep genuine
  numeric agreement tests and separately wrap the real
  `WellnessSeries.canonical` method, delegating to it while asserting zero
  calls during input construction and signal-block computation. That
  mutation must fail the architectural assertion while numeric agreement
  remains GREEN. Do not fabricate inconsistent series or BaselineDay
  results. Sleep-stage selection still has a real two-source numeric
  discriminator. Requirements, science and production APIs are unchanged.

- 1.4 accepted after independent approval and fresh completion verification:
  892 index tests, 49 existing boundary guards and all static checks passed.
  Fourteen claimed and two independent mutations failed at their intended
  assertions and restored GREEN. Morning-only edits move document state
  without deriving or changing the edited page's substantive computed rows;
  unknown region content still changes the render digest. Analytics-index
  Amendment 3 appends criterion 5.8 and its glossary note, dated 2026-10-18;
  the schema and its version pin are unchanged. Requirement 10.2's broader
  runtime independence remains with the later morning tasks.

- Astra decision 5 (2026-10-18, user-delegated ambiguity resolution):
  permanent source boundaries also apply to the live verification tree.
  Minimal outside-boundary faults needed for discrimination may run only
  in an audited isolated snapshot of HEAD plus the current task edits,
  with a separate environment and pytest import/interpreter provenance.
  Never mutate live frozen/upstream files or share an editable install
  pointing to them. Each changed setup assertion needs its own intended
  RED, exact byte restoration and restored GREEN; an earlier failure does
  not pin a later assertion. Unchanged existing setup may be reused. This
  permits the isolated empty-refreshed-policy control for 1.4's widened
  helper guard, and adds no shipped behavior or requirement amendment.
  The shared log records the full decision and experiment evidence.

- 1.3 accepted after independent approval and fresh completion verification:
  full suite 26,151 passed / eight accounted skips; 5,084 focused tests and
  all static checks passed. Fifteen claimed and three reviewer mutations
  failed at their intended assertions and restored GREEN; nineteen files
  matched their reviewed hashes. All twelve render goldens differ solely
  by the empty region and separator. Separate historical-render probes
  reproduced all seven frontmatter hashes and every other document and
  asset byte after removing the insertion. Required pin grep found no
  pre-existing exact-region assertion needing a re-pin; existing H2-order
  pins remain unchanged because the empty region has no heading. The
  reserved index fingerprint test is untouched. Morning page builders are
  now frozen; task 4.1 owns the controlled version-only digest re-pin.

- Astra decision 4 (2026-10-17), frontmatter pins across tasks 1.3/4.1:
  retain the seven literal pre-region frontmatter SHA256 baselines captured
  at `852e35f` (`DOC_VERSION = 9`). Task 1.3 checks all frontmatter bytes
  unchanged; task 4.1 owns the required version advance and the resulting
  digest re-pin, which the literal-version grep cannot discover. Re-pin
  only after every old capture matches its existing digest and every new
  capture differs solely in the single approved `doc_version` line;
  preserve that provenance. Task 5.1 repeats the controlled re-pin if
  rebasing changes the landing version. No task 1.3 implementation or
  test-strategy change is needed.

- Astra decision 2 (2026-10-17, user-delegated ambiguity resolution): Python
  may intern a copied region literal, so identity cannot establish import
  provenance. Task 1.3 uses the literal scan for a local literal copy and
  a separate runtime-built equal but nonidentical string for the binding
  assertion. Requirements and the public string constants are unchanged;
  the shared log records the decision and its separate mutation evidence.

- 1.2 accepted after independent approval and fresh completion verification:
  401 focused tests, Ruff/format/mypy clean; all 32 implementer mutations
  independently replayed, plus five new or nested module controls, each
  RED at its intended assertion and restored GREEN. The three constants
  are public; both render and morning literal scans have nonempty walks.
  Existing region tuples, banner and both versions remain unchanged.

- Astra decision (2026-10-17, user-delegated ambiguity resolution): the
  allowed dependency lists are upper bounds through task 3.1; task 3.2
  closes forward import sets to equality along with the finished module
  set and reverse importers. This lets task 2.1 implement rows without
  unused rendering/attribution imports or later-task behavior. Requirements
  and the final allowed sets are unchanged. Task 1.1 proves a legitimate
  partial block passes and a partial block plus `fitdocs.sync` fails;
  task 3.2 must prove a missing final dependency fails. Decision recorded
  in the shared log and the design/task text above.

- Planning record (2026-10-12/13): Step 3.5 task-graph review ran twice, as
  an independent reviewer the batch controller dispatched. Round 1 returned
  NEEDS_FIXES with 14 findings (4 important, 10 minor) and four controller
  rulings: R1, the every-page byte-compare pass and the printed-facts
  fingerprint are accepted in place of `SeriesReport.days`, `day_digest`
  and `baseline_key` (a row's `unattributed` flag is not a fact); R2, 1.4
  depends on 1.3 and is not parallel; R3, `_run_morning_pass` catches
  `Exception`, reports, fails the run and lets the later passes run; R4,
  the pass's cost is measured end to end in 3.1 with a 10 s stop threshold.
  All were applied. Round 2 verified every finding resolved and listed five
  minor items (the `KeyboardInterrupt` observation through `CliRunner`, the
  exit fold at all three call sites, the without-block wording, the
  `_NEVER_ADD_MARKER` pin, the criterion count), applied without a further
  review as the controller directed.
- Outcomes of 1.1's upstream checks, 1.3's re-pinned test list, 3.1's R4
  measurement and 5.1's sweep are recorded below when those tasks run.

- 1.1 upstream checks (verified against `399fe7f`, no drift):
  - Wellness facade: `src/fitdocs/wellness/__init__.py:3,11,26` exports the
    required reader, errors, series, values and metric vocabulary;
    `model.py:48-51` supplies labels/units and `series.py:267,270,304,340`
    supplies `values`, `is_empty`, `by_source` and `read_series`.
  - Sanctioned fixtures: `tests/wellness/builders_series.py:12`,
    `builders_intervals.py:18` and `builders_garmin.py:16,65,69` provide
    the series writer, delivery envelope and sleep-stage file. Drain
    rebuilds at `src/fitdocs/sync.py:1001` before page writes at `:1035`;
    regen rebuilds at `cli.py:1025`, writes at `:1027`, reports the table
    at `:1035` and then the wellness summary at `:1036`.
  - Recovery facade: `src/fitdocs/recovery/__init__.py:3-4` exports the
    required types/methods. `baselines.py:23` has all thirteen fields;
    `:49,63,114,121` provide `of`, `on`, `shown_source`, `shown`;
    `constants.py:31,36,38,379,384,392` supplies the windows and metric
    selections; `page.py:28` supplies the forbidden-phrase pattern.
  - Formatting/attribution: `src/fitdocs/render/charts/kit/format.py:116,202`
    has the required formatter/escaping functions; `render/format.py:33`
    is the en dash; `render/attribution.py:71,74,80,91` supplies the Garmin
    origin, attribution enum and both shared functions.
  - CLI flow: explicit sync reports at `cli.py:838`, then load/plan/index/
    dashboard at `:840,845,846,847`; drain reports at `:929`, then those
    passes at `:932,935,936,937`; regen reports at `:1035-1036`, then those
    passes at `:1039,1042,1043,1044`. Dashboard helper is at `:595`.
- 1.1 accepted after independent review and fresh completion verification:
  57 task tests; full suite 26,078 passed, 44 optional checks skipped;
  Ruff/format/mypy passed (825 formatted files, 640 typed sources).
  Independent replay covered 58 claimed mutations plus two reviewer
  mutations. All three assigned clauses (12.1, 12.2, 12.4) are PINNED at
  this task's scope. Later runtime coverage remains with its owning tasks.
- Guard lesson from 1.1: each member of a finite forbidden/network/clock
  policy needs an independent literal control, and a permitted exception
  needs an acceptance control. Deleting an entire guard does not pin its
  individual members. The first review found eighteen such survivors;
  deleting each entry now fails its own control in
  `test_scans_reject_synthetic_modules`, and denying the CLI exception
  fails `test_reverse_scan_accepts_the_cli`. None remain unpinned.

- 3.3 accepted after independent review and fresh completion verification:
  native two-date source sync and archived drain populate morning blocks
  in the same run; repeated page bytes/mtimes and report silence,
  copied-root UTC/Kiritimati determinism, selective revision with a
  populated out-of-window page, Garmin stages/attribution, current index
  fingerprints and damaged-marker reporting all discriminate. Fresh
  required tests passed 583 cases and native regressions passed 72,
  with Ruff, formatting and mypy clean. All 26 new/changed assertion
  sites and both retained native driver observables reached intended
  failures. Independent replay confirmed 26 native-source faults
  (38 observations), one portability-checker fault, six registry faults
  and two predicate faults (ten observations across those nine bounded
  Astra13 faults), plus two reviewer native-source faults; every intended
  failure restored GREEN. The disclosed morning-fold-only mutation stays
  GREEN because load independently rejects the same damaged markers;
  it earns no kill credit. Existing 3.2 fold tests remain preserved.
  Eight assigned criteria have new native pins; the stricter pass-only
  filesystem guarantee in 12.3 and explicitly named subclauses retain
  freshly executed existing coverage. No new unpinned exception applies.
  Final P is the STAMP_PATTERN fullmatch alternative, R the sync-morning
  EntryPoint, and N only _morning_write_observed's workout-parent equality
  and nonempty-content condition. _SYNC_MORNING_DATA_ROOT follows the
  approved clear/publish/consume lifecycle. Neither EntryPoint nor the
  shared driver changed. Full-suite proof is due again in 4.1.

- 4.1 accepted after independent review and fresh completion verification:
  main 51d0e09 has DOC_VERSION 9, advanced once to 10; the ownership
  contract stays 14 until 4.2. The complete append-only history records
  both the empty morning region and the regeneration remedy. The native
  aged-page cases begin with a populated page from drained synthetic FIT
  and Intervals inputs; check is read-only, a second drain preserves the
  aged page and warns, and regen restores the populated current format
  after normalized wellness is deleted, using the archived inputs.
  Current-format literal pins moved to 10; deliberately historic,
  arbitrary-payload and missing-source fixtures retain their old values.
  All twelve render golden changes are their version line alone.
  The seven frontmatter digest pins were controlled re-pins from 9 to 10:
  each original native capture matched its recorded digest, and each new
  capture equaled the old bytes with exactly the single version line
  changed before its digest was updated. Capture provenance remains
  852e35f / DOC_VERSION 9; independent review reproduced both sets.
  Workout-docs Amendment 5 (2026-10-18) appends criteria 4.5, 6.13, 9.7,
  10.6, 12.3 and 13.5, preserving Amendment 4 from analytics-index.
  All 26 new/changed assertion sites (43 observable instances) and two
  history helper error paths have reached fault evidence: twenty source
  faults yielded 46 intended failures, independently replayed, plus two
  reviewer source faults; every restoration passed. No test SUT exception
  or new unpinned limitation applies. All three assigned criteria are
  pinned, with amended-spec retained subclauses named as preserved.
  Two independent full suites passed 26,730 tests with the same eight
  known optional skips (987.03 s and 757.13 s); both exited successfully.
  Fresh completion checks passed 5,177 focused tests, metadata node
  collection and all static checks. All current inputs matched both
  isolated snapshots. Ownership publication and release text follow in
  4.2 and 4.3; final integration and landing remain with 5.1 and the
  controller feature gates.

- Astra decision 15 (2026-10-18, task 4.2) resolves two ambiguities
  in the new ownership bullet. The pass creates, renames or deletes no
  workout document; its approved atomic temporary-file mechanism remains
  permitted. The shared skip guarantee is that pages remain untouched:
  newer pages are counted but not printed, and missing-region warnings
  depend on a nonempty series. The guide drops the universal reporting
  claim; detailed report actions remain with CliMorning and 4.3.
  Only the existing confinement/skips literals and their existing fault
  preimages change; retain the same 37 cases and intact consumers.
  Refresh all bounded evidence, census, prose and input hashes after the
  complete literal history sentence and actual anchors are checked, then
  freeze and run the full suite in the real Git feature worktree. Two
  interrupted superseded attempts have no full-pass credit. This grants
  no runtime/spec behavior change, mutation category or acceptance waiver.
  The finite checklist covers every explicit 4.2 task/design obligation;
  after it closes, reopen only concrete defects or actual check failures.
  Decision artifact:
  /private/tmp/workout-wellness-astra-ownership-prose-closure.md.

- 4.2 accepted after independent review and fresh completion verification:
  CONTRACT_VERSION advances from string 14 on main 51d0e09 to 15;
  DOC_VERSION stays 10. The complete append-only history and its literal
  test include the 14-to-15 advance and the entire prescribed second
  sentence, including the pass and re-derivability clauses. The ownership
  guide publishes the separate refreshed-region class, preserved-region
  pointer, morning ownership and overwrite boundary, newer-version
  preservation, ordering and wellness-backed re-derivability. The
  declaration's two fragments use layout directory constants, retain the
  quantifier guard and supported-marker qualifier, and name the actual
  morning engine function and all three CLI call sites. Seven declaration
  goldens change only their version; the workouts golden also changes its
  two prescribed fragments. All thirteen outgoing Recovery head claims
  move to literal history; older history obligations remain.
  Wiki-contract Amendment 10 (2026-10-18) appends actual free criteria
  1.7, 2.20 and 2.21, preserving dashboards 2.17, wellness-store 2.18,
  Recovery 2.19 and all earlier criteria, amendments and approvals.
  The final finite sweep covers ten changed assertion sites (42
  instances) and eight retained sites (18 instances). Independent replay
  confirmed all 37 source/doc faults and 66 intended failures, plus three
  reviewer source faults with five further observations; every intended
  failure restored GREEN. Publication obligations are pinned; existing
  runtime evidence for 9.3/9.5 remains explicitly preserved. No new
  mutation category, test exception or unpinned limitation applies.
  Two interrupted superseded runs earn no full-pass credit. The final
  source includes the corrected actual anchor, complete history literal
  and Astra15 wording, with its durable note captured before final freeze.
  Two final independent full suites passed 26,763 tests and the same
  eight known optional skips, both exit 0 (898.06 s and 794.43 s).
  Fresh completion passed 2,128 focused tests, all statics and 41 expanded
  amendment-node cases. It independently confirmed all current inputs,
  fault records and the bounded checklist. The guide, packaged skill,
  release notes and final integration follow in 4.3 and 5.1.

- Task 4.3 publication outcome (2026-10-18): the wellness guide links to its
  existing day-boundary section and explains both windows, origins,
  attribution, absence, refreshes and shared Recovery figures. The shipped
  workouts skill explains every Morning of report and action; the upgrading
  guide names archived wellness through the rebuilt-first series. Release
  notes publish page format 9 to 10, ownership contract 14 to 15, regeneration
  and the analytics document-only change. Structure steering names the
  approved morning dependency boundary. All predecessor publication bytes,
  peer Recovery wording and the single Fixed subsection after Changed are
  preserved; existing skill pins required no adjustment.
  Seven new assertion sites expand to 28 cases, with the retained
  wellness-store exactly-once consumer also observed RED. All 47 ordinary
  source/document faults were independently replayed, plus two reviewer
  faults: 51 intended failures and exact restoration/GREEN in review.
  Source criteria 11.4, 11.5 and 11.6 are PINNED; no new exception applies.
  Implementer and fresh reviewer canonical full suites each passed 26,791
  tests with eight known local optional skips and one existing JUnit warning
  (716.67 s and 713.68 s, both exit 0); all 2,106 frozen inputs remained
  unchanged. Focused review passed 845 tests with one known actionlint skip;
  Ruff, formatting and mypy passed. No findings or follow-ups surfaced.
  Fresh completion verification independently audited both full-suite
  XML/log/exit records, all 47 implementer and 49 reviewer fault records,
  every intended assertion and restoration, the census and actual pytest
  import/copy-environment provenance. All 2,106 inputs matched the live tree
  and both snapshots. Its fresh focused run passed 845 tests with one known
  actionlint skip in 15.59 s; Ruff, formatting, mypy and diff checks passed.
