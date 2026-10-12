# Implementation Plan

## Upstream Prerequisites

- **No upstream spec.** `chart-kit` is Phase 11's wave 1; it branches from
  `main` at or after `d68034f`. It reads, and never restructures:
  - `src/fitdocs/render/charts/svg.py` (`el`, `text`, `fmt_num`),
    `series.py` (`gap_segments`) and `palette.py` (the provenance convention
    and `_oklch_to_hex`'s pipeline, mirrored by `tests/render/charts/test_palette.py`);
  - `src/fitdocs/index/schema.py:77-97` (`UNIT_SUFFIXES`) and its pins in
    `tests/index/test_schema.py:181-205`, `:1229-1288`, which must stay green
    **unedited**: they are the evidence the projection did not change the value.

  A task that finds any of these shaped differently from what design.md
  states stops and reports rather than adapting.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Updates Carried by This Spec). One **analytics-index** update, value-preserving:
  `src/fitdocs/index/schema.py` projects `UNIT_SUFFIXES` from
  `fitdocs.units.UNITS` (task 1.1); `.kiro/specs/analytics-index/design.md`
  gains a dated note beside its unit-suffix table,
  `.kiro/steering/structure.md`'s `index` bullet gains `units`, and the
  exact-phrase pin of that bullet in
  `tests/connectors/test_network_statements.py:680-685` is re-pinned to the
  new wording (task 7.1; controller ruling). The roadmap's Existing Spec
  Updates line for it is the batch controller's, not this plan's.
- **Downstream specs start from design.md § Settled Seams.** `dashboards` and
  `chart-catalog` are written in parallel against it. Any change to a name,
  field, code, default, ink, palette entry, bound or rule listed there is a
  revalidation trigger (design § Revalidation Triggers): a task that needs one
  stops and reports instead of making it.

**Hard rules for every task**

- **Absent is `None`.** No kit code substitutes zero, an empty string, a
  default or an interpolated value for an absent value; zero is drawn as zero.
- **Pure.** No clock, randomness, generated ids, environment reads, file or
  network access in `src/`. Tests that write goldens do so only through a
  module's `main()` writer, never during a pytest run.
- **Imports.** Kit modules import only the standard library,
  `fitdocs.render.charts.{svg,series,palette}`, `fitdocs.units` and earlier
  kit modules in the design's dependency order
  (`units → data → problems → schema → format → ticks → theme → layout →
  scales → frame → marks → cartesian → validate → kinds/* → registry → api →
  __init__`). A kind module never imports another kind or `registry`.
- **Existing charts untouched.** The hero, calendar, zone-strip and map
  modules and every file under `tests/render/charts/golden/`,
  `tests/render/golden_docs/` and `tests/history/golden/` stay byte-identical:
  `git diff --stat main -- src/fitdocs/render/charts/hero.py
  src/fitdocs/render/charts/calendar.py src/fitdocs/render/charts/zones.py
  src/fitdocs/render/charts/map.py tests/render/charts/golden
  tests/render/golden_docs tests/history/golden` is empty at every task.
- **Golden discipline.** Goldens are compared as bytes, never created by a
  test run, and regenerated only by the owning module's `main()`
  (`uv run python -m tests.render.charts.kit.test_<kind>`). Every golden is
  shown able to fail by at least one named mutation of kit code, recorded
  with the golden(s) it reddened: kind-local mutations in the kind's own task
  (group 5), and the standard golden classes reached by shared-layer
  mutations in task 6.2 alone. A golden whose fixture cannot be made to fail
  is reported, not kept.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination). Each named mutation is applied, observed red,
  reverted, observed green, and recorded. Revert by restoring a `cp` of the
  file taken before the mutation, never `git checkout -- <path>`,
  `git stash` or `git reset --hard`. A listed mutation that cannot be made red
  is reported UNPINNED, never hidden by weakening the assertion. Before
  submitting, run the prose-claim grep of `change-protocol.md` over the
  changed test files and re-run or delete every surviving claim.
- **A `(P)` task never mutates a module outside its own boundary.** Its
  named mutations are made only in the files it owns, so parallel tasks
  sharing a tree never red each other's tests or restore each other's
  in-flight files. Mutations of shared modules that reach several kinds'
  goldens run once, sequentially, in task 6.2; the later group-6 tasks are
  sequential for the same reason.
- **Fixtures discriminate.** Category first-appearance order differs from
  alphabetical order; rows are not pre-sorted by x; values are pairwise
  distinct where a mapping is asserted; offending rows sit at indices other
  than 0; an asserted end state is shown false beforehand.
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`.
- **Types and lint.** Each task runs `uv run mypy` (config-driven), and
  `uv run ruff check` and `uv run ruff format --check` on its changed files.
- **Stop and report** on any need for: a runtime dependency; an edit to the
  four renderers or their goldens; a change to a Settled Seam; a shared-layer
  change from a kind task (groups 5); an edit to another spec's files beyond
  those named in task 7.1.

## Shared source files

Each file below has more than one writer in this plan; its writers are
sequential, never two `(P)` tasks at once.

- `src/fitdocs/render/charts/kit/registry.py`: 3.1 creates it with an empty
  `KINDS`; 6.1 alone populates it.
- `src/fitdocs/render/charts/kit/api.py`: 3.1 only. `kit/__init__.py`: 1.2
  creates it as a docstring-only marker; 3.1 alone adds the re-exports.
- `tests/render/charts/kit/_helpers.py`: 1.4 creates the data builders; 3.1
  appends the `render_spec`-based helpers. Kind tasks import it and never
  edit it; a missing helper is a stop-and-report.
- `tests/render/charts/kit/goldens.py`: 1.4 only.
- `pyproject.toml` (`[tool.mypy].files`): 1.1 (`tests/test_units.py`) and
  1.2 (`tests/render/charts/kit`, a directory entry that covers every later
  kit test module). No later task edits it.
- `src/fitdocs/render/charts/palette.py` and
  `tests/render/charts/test_palette.py`: 2.4 only.
- `src/fitdocs/index/schema.py`: 1.1 only.
- `src/fitdocs/render/charts/kit/ticks.py`: 2.3 only (including
  `linear_ticks`' `integer` option); 4.1 consumes it.
- `src/fitdocs/render/charts/svg.py`, `.kiro/steering/structure.md`,
  `.kiro/specs/analytics-index/design.md` and
  `tests/connectors/test_network_statements.py`: 7.1 only.

## Cross-spec shared files

`chart-kit` lands before both wave-2 specs, so nothing here is contended
during this plan. These files become seams for `chart-catalog` (and, for
`pyproject.toml` and `structure.md`, `dashboards`) once this plan lands.

**Append-only, pinned by an ordered prefix** — appending turns no test red:
- `kit/registry.py` `KINDS` — `kind_names()[:8] == CORE_KIND_NAMES`
  (`test_registry.py`, 6.1);
- `kit/problems.py` `ProblemCode` — `tuple(ProblemCode)[:23] == CORE_CODES`
  (`test_problems.py`, 1.2);
- `kit/theme.py` `INK_ROLES` — `INK_ROLES[:2] == (TEXT, STROKE)`
  (`test_theme.py`, 2.4);
- `palette.py` `CATEGORICAL_RAMP` / `CATEGORICAL_COLORS` — the first eight
  entries (`test_palette.py`, `test_theme.py`, 2.4);
- `pyproject.toml`'s mypy `files` (the kit test directory entry already covers
  appended kit test modules); `.kiro/steering/structure.md`;
- `tests/render/charts/test_palette.py` `_all_documented()` — the append
  point for an appended palette's `name -> (hex, oklch source)` mapping
  (`chart-catalog` adds its `SEQUENTIAL_COLORS` there); 2.4 extends it with
  `CATEGORICAL_COLORS` and pins only the first eight categorical sources.

**Shared with `dashboards`** — keep both on rebase:
- `tests/connectors/test_network_statements.py:680-685`, the exact-phrase pin
  of `structure.md`'s `index` bullet: 7.1 re-pins it to the wording with
  `units` ("… `settings`, `version`, `units` and the load payload readers;
  only `cli` and `query` import it; only `index.store` imports `duckdb`.");
  `dashboards` checks the same pin in its own tasks.

**Full pins, explicit re-pin points** — an appending spec edits them in the
same change:
- `tests/render/charts/kit/test_boundary.py` (6.5): the hand-kept kit module
  tuple (checked against `rglob` both ways) and the layer-rank matrix. A new
  kind module joins the kind rank; a new shared module gets a rank.
- `tests/render/charts/kit/test_theme_coverage.py` (6.3): the colour
  whitelist (inks of every `INK_ROLES` entry plus `CATEGORICAL_RAMP`); an
  appended palette (a sequential scale, say) adds its colours.

Not pins: `test_registry.py`'s per-kind invariants, the registry round trip
(6.1), the theme coverage walk (6.3) and the determinism run (6.4) iterate
every registered kind and find its cases by the test-module convention
(design § Settled Seams), so appended kinds are covered unedited.

## Test File Ownership

- `tests/test_units.py`: **1.1**.
- `tests/render/charts/kit/__init__.py`, `test_data.py`, `test_problems.py`:
  **1.2**.
- `tests/render/charts/kit/test_schema.py`: **1.3**.
- `tests/render/charts/kit/goldens.py`, `_helpers.py` (builders),
  `test_goldens_harness.py`: **1.4**.
- `test_validate.py`: **2.1**. `test_format.py`: **2.2**. `test_ticks.py`:
  **2.3**. `test_theme.py` and the categorical additions to
  `tests/render/charts/test_palette.py`: **2.4**.
- `test_api.py` and the `render_spec` helpers in `_helpers.py`: **3.1**.
  `test_layout.py`: **3.2**. `test_marks.py`: **3.3**. `test_cartesian.py`:
  **3.4**.
- `test_scales.py`: **4.1**. `test_frame.py`: **4.2**.
- Kind test modules follow the convention `test_<name with - as _>.py`
  exposing `CASES` and `main()`, goldens in `golden/<name>/`:
  `test_line.py` + `golden/line/`: **5.1**; `test_area.py` + `golden/area/`:
  **5.2**; `test_bar.py` + `golden/bar/`: **5.3**; `test_hbar.py` +
  `golden/hbar/`: **5.4**; `test_scatter.py` + `golden/scatter/`: **5.5**;
  `test_histogram.py` + `golden/histogram/`: **5.6**; `test_stat.py` +
  `golden/stat/`: **5.7**; `test_table.py` + `golden/table/`: **5.8**.
- `tests/connectors/test_network_statements.py` (only the `index`-bullet
  phrase at `:680-685`): **7.1**.
- `test_registry.py`: **6.1**. Task 6.2 adds no test file (its evidence is
  the existing kind golden tests going red together). `test_theme_coverage.py`,
  `test_size_budget.py`: **6.3**. `test_determinism.py`: **6.4**.
  `test_boundary.py`: **6.5**.

---

- [ ] 1. Foundation: the unit vocabulary, the kit package and its contracts, and the golden harness

- [x] 1.1 Create the one unit vocabulary and make the index schema project it
  - **`src/fitdocs/units.py`** per design § UnitVocabulary: `UnitFamily`,
    the frozen `Unit` (with the `suffix` property), the 19-row `UNITS` table
    exactly as the design lists it (order, phrases, symbols, families,
    decimals, `spaced`), `unit_for_column` (first match in table order) and
    `unit_named`. Standard library only.
  - **`src/fitdocs/index/schema.py`**: replace the `UNIT_SUFFIXES` literal
    with `tuple((unit.suffix, unit.phrase) for unit in UNITS)`, keeping its
    name, its `Final` annotation and every other line. `SCHEMA_VERSION` does
    not change.
  - **`pyproject.toml`**: register `tests/test_units.py` in `[tool.mypy].files`.
  - **Tests** (`tests/test_units.py`):
    - the projection equals a literal copy of the pre-change `UNIT_SUFFIXES`
      tuple, element by element and in order (the one deliberate literal);
    - every row's token, symbol, family, decimals and `spaced` pinned against
      the design table; tokens unique; `suffix == "_" + token`;
    - `unit_for_column`: `avg_pace_s_per_km` → `s_per_km` (not `km`),
      `leg_spring_stiffness_kn_m` → `kn_m` (not `m`), `moving_time_s` → `s`,
      `start_time_local` → `local`, `distance` → `None`,
      `cadence_rpm` → a unit whose symbol is `rpm` and phrase
      `revolutions per minute`;
    - `unit_named` round-trips every token and returns `None` for `spm`;
    - `fitdocs/units.py` imports only standard-library modules (AST walk with
      a positive control asserting the walk saw the module's `from enum`
      import, and a synthetic source `import fitdocs.model` that the same
      check rejects).
  - **Mutations:** swap the `_s_per_km` and `_km` rows (lookup and
    projection pins red); drop the early return in `unit_for_column` so the
    last match wins; change the `rpm` symbol to `spm`; change one phrase
    (`tests/index/test_schema.py` reds too, unedited); add
    `import fitdocs.model` to `units.py` (guard reds).
  - **Observable:** `uv run pytest tests/test_units.py tests/index/test_schema.py
    tests/query/test_schemaview.py tests/index/derived/test_registration.py`
    is green with the last three unedited (`git diff --stat` on them is
    empty).
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 16.4, 18.5_

- [x] 1.2 Create the kit package with its data contract and problem types
  - **Package markers**: `src/fitdocs/render/charts/kit/__init__.py` (a
    docstring stating the kit's purpose and allowed imports; no re-exports
    yet), `kit/kinds/__init__.py` (marker, no imports) and
    `tests/render/charts/kit/__init__.py`.
  - **`kit/data.py`** per design § DataContract: `ValueKind`, `Value`,
    `Column`, `ChartData`, `accepts`, `is_finite_number`, `to_number`.
  - **`kit/problems.py`** per design § Problems: `ProblemCode` with the 23
    values in the Settled Seams order, `ChartProblem` (field order as listed),
    `ProblemDict`, `ChartProblem.as_dict()`, `ChartError`.
  - **`pyproject.toml`**: register the directory `tests/render/charts/kit`
    in `[tool.mypy].files`.
  - **Tests** (`test_data.py`, `test_problems.py`):
    - `accepts`: NUMBER takes `3`, `2.5`, `Decimal("1.5")` and refuses `True`;
      DATE takes `date` and refuses a `datetime`; DATETIME refuses an aware
      `datetime`; DURATION takes `timedelta`; CATEGORY takes `str` only;
      BOOLEAN takes `bool` only and refuses `1`; `None` accepted for every
      kind;
    - `is_finite_number` false for `nan`, `inf`, `-inf`, `Decimal("NaN")`,
      `Decimal("Infinity")`;
    - `to_number`: days for dates (`toordinal`), seconds for durations and
      date-times, `float` for `Decimal`, `None` for absent;
    - `tuple(ProblemCode)[:23]` equals a test-local `CORE_CODES` literal of
      the design's 23 values in order (a prefix pin: appending a code keeps it
      green); `as_dict()` keys in field order, `accepted` as a list, JSON-serialisable;
      `str(ChartError(...))` joins messages with `\n`.
  - **Mutations:** test `isinstance(v, int)` instead of excluding `bool`;
    check `isinstance(v, date)` for DATE (lets `datetime` through); drop the
    `tzinfo is None` test; return `0.0` for absent in `to_number`; reorder two
    `ProblemCode` members; reorder two `ProblemDict` keys.
  - **Observable:** `uv run pytest tests/render/charts/kit` is green and
    `uv run mypy` covers the new test directory.
  - _Requirements: 1.1, 1.2, 4.1, 4.5_

- [x] 1.3 Define the kind schema and the bound inputs a kind receives
  - **`kit/schema.py`** per design § KindSchema and § Settled Seams:
    `Output`, `OptionType`, `OverBound`, `OptionValue`, `ChannelSpec`,
    `OptionSpec`, `MarkBound`, `KindSpec` (field order and defaults as
    listed), `ChartRequest` (empty-mapping defaults via `default_factory`),
    `BoundRequest` with its accessors and `problem()` factory, `BoundChart`
    with `values`, `width`, `height`, `no_problems`, and `svg_options`.
  - **Tests** (`test_schema.py`):
    - `svg_options(own, height=320)` returns `own` then `width` (INTEGER,
      320–1600, default 720) then `height` (INTEGER, 160–1200, default 320);
      `height=None` gives a `None` default;
    - `BoundRequest.problem(...)` fills `ref` and `kind` from the request and
      spec; accessors return typed option values;
    - `BoundChart.values("y")` returns the bound column's values in row
      order (fixture: the y column is not the first column);
    - `BoundChart.width`/`height` read the options, `None` height preserved;
    - two `ChartRequest`s built without channels do not share one mapping.
  - **Mutations:** put `height` before `width` in `svg_options`; read
    `values` by channel position instead of the bound column's index; drop
    `ref` from `problem()`; use a shared `{}` default.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_schema.py` is
    green.
  - _Requirements: 3.1, 5.1, 7.5, 11.1_

- [x] 1.4 Build the golden harness and the test data builders
  - **`tests/render/charts/kit/goldens.py`**: `golden_path(kind, case,
    suffix)` under `tests/render/charts/kit/golden/<kind>/`;
    `assert_golden(path, text)` comparing `text.encode("utf-8")` with
    `path.read_bytes()` and failing with a clear message when the file is
    missing (never creating it); `write_golden(path, text)` used only by
    `main()` writers.
  - **`tests/render/charts/kit/_helpers.py`**: small builders for `Column`,
    `ChartData` and `ChartRequest` that kind tests share (no rendering yet),
    and a frozen `Case(name, request, data)` record. Every kind test module
    (group 5) exposes `CASES: tuple[Case, ...]`, the one list its goldens,
    its `main()` writer and tasks 6.1–6.4 read.
  - **Tests** (`test_goldens_harness.py`): a tamper test copies a fixture
    golden written in `tmp_path`, flips one byte and shows `assert_golden`
    fails; a missing golden fails and is not created; a trailing newline
    difference fails (bytes, not `read_text`).
  - **Mutations:** compare with `read_text()` after `strip()`; create the
    file when missing; compare only lengths.
  - **Observable:** the harness tests are green and each listed mutation
    reds exactly them.
  - _Requirements: 18.3_

- [ ] 2. Core contract and shared primitives

- [x] 2.1 (P) Validate requests and data, parse options and bind
  - **`kit/validate.py`** per design § Validator and the stage table in §
    System Flows: `validate_request`, `bind_request`, `check_data`,
    `bind_chart`, `parse_option` (typed values and the canonical text forms).
  - **Tests** (`test_validate.py`), one fixture per problem code that breaks
    only that rule, with a minimal test-local `KindSpec` (two channels, one
    of each option type, a `validate` hook):
    - every stage-1 code (`unknown_kind` with `accepted` = the registered
      names given; `empty_title`; `duplicate_column`; `missing_channel`,
      `unknown_column`, `channel_kind` each with `accepted` = the fitting
      columns in column order; `unknown_unit`; `unit_kind` for a unit on a
      CATEGORY column and for `s` on a DATE column; `unknown_channel`;
      `option_value`; `unknown_option`) and that the kind's `validate` hook
      runs only when nothing else failed;
    - order: a request listing channels and options in reverse spec order
      yields problems in spec order, unknown names sorted;
    - all request problems reported together (three independent faults →
      three problems);
    - `parse_option`: `"true"`/`"false"`, `"20"`, `"-3"`, `"2.5"`, exact
      choices accepted; `"True"`, `"yes"`, `"1.0"` for an integer, `" 20"`,
      `"nan"`, an out-of-range value and `True` for an integer refused;
    - stage 2: `row_width` at row 3 stops the stage; `value_type` and
      `non_finite` name the first offending row (offenders at rows 2 and 5,
      `row == 2`, `rows == 2`); one problem per column and code; unbound
      columns are not checked (a bad value in an unused column passes);
      `uses_all_columns` checks every column;
    - defaults applied when options are omitted; no binding is inferred from
      a column named like a channel.
  - **Mutations:** iterate `request.channels` instead of the spec's channels
    (order test reds); stop after the first problem; check unbound columns;
    accept `"True"`; count `rows` from the first offender only; skip the
    `validate` hook gate.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_validate.py`
    is green.
  - _Requirements: 1.3, 1.4, 1.5, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 4.2, 4.3, 16.2_
  - _Boundary: Validator_

- [x] 2.2 (P) Format labels, values and ticks by unit
  - **`kit/format.py`** per design § Formatter: `ABSENT` (U+2014),
    `ELLIPSIS`, `display_label`, `axis_title`, `format_value`,
    `format_number_tick`, `format_duration`, `format_pace`, `format_delta`,
    `clean_text`, `escape_markdown`. No `locale`, no `strftime`, no `n`
    format specifier, no unit conversion.
  - **Tests** (`test_format.py`):
    - `display_label("avg_speed_mps", unit mps)` → `avg speed`; an explicit
      label wins; a name without its unit's suffix keeps its full text;
    - `axis_title`: `distance (km)`, `pace (min/km)`, `start (UTC)`,
      `start (local time)`, durations `(h:mm:ss)`/`(m:ss)`, `clock_date`
      appended;
    - every family: `int` → no decimals; `float` km → 1 decimal; unitless
      float → ≤2 decimals trimmed (`0.83`, `54.12`, `3`); `-0.0` → `0`;
      `3.2` pct → `3.2%` (unspaced); `45.0` deg → `45.0°`; `21.5` c →
      `21.5 °C`; durations `59:59` at 3599 s and `1:00:00` at 3600 s, banker's
      rounding at a `.5` second; pace `4:35` and `4:35 /km` with unit; date,
      date-time (seconds truncated), `UTC` suffix; booleans `true`/`false`;
      absent → `—`;
    - `format_delta`: `+3.1 km`, `-0:30`, `±0.0 km`, `+1.2 pp` for pct;
    - `clean_text` replaces `\x01` and `￾` with U+FFFD and newlines with
      a space; `escape_markdown` escapes each listed character and leaves
      digits and `.` alone;
    - the module source contains no `strftime`, `locale` or `:n}`.
  - **Mutations:** round durations with `int()` (banker's case reds); use
    `>` 3600 for the h:mm:ss switch; drop `-0` normalisation; space the `%`;
    use U+2013 for `ABSENT`; drop `|` from the markdown set; convert pace
    from speed anywhere (a test asserts `mps` values format as `m/s`
    numbers).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_format.py` is
    green.
  - _Requirements: 1.6, 2.4, 2.5, 2.6, 2.7, 2.8, 9.8_
  - _Boundary: Formatter_

- [x] 2.3 (P) Compute nice steps and tick ladders
  - **`kit/ticks.py`** per design § Ticks: the ladders, `CalendarStep`,
    `nice_step`, `linear_ticks`, `log_ticks`, `calendar_ticks`,
    `clock_ticks`.
  - **Tests** (`test_ticks.py`):
    - decimal ladder: spans 0–9.3, −4.2–17, 0.012–0.087 and 1200–48000 give
      the expected niced domains and steps; the domain encloses the data;
    - duration ladder: 0–5400 s steps in minutes; never below 1 s; 2-day
      spans move to day steps;
    - log: three-plus decades → decades only; under three → 1, 2, 5 per
      decade; duration log ticks inside 5 s–2 h include 1 min and 20 min;
    - calendar: a 10-day span → day/2-day steps; 9 weeks → Mondays; 14
      months → months or quarters; 6 years → years; ticks inside the span;
    - clock: a 3-hour span → 15/30-minute steps aligned to midnight
      multiples;
    - each function's tick count ≤ `max_count`;
    - `linear_ticks(0, 3, 8, duration=False, integer=True)` steps by 1 (not
      0.5) and `integer=False` on the same input steps by 0.5.
  - **Mutations:** drop mantissa 2 from the ladder; ignore `integer`; use floor instead of
    ceil for the outer domain edge; start weeks on Sunday; omit the 1200 s
    entry from the log-duration ladder.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_ticks.py` is
    green.
  - _Requirements: 6.2_
  - _Boundary: Ticks_

- [x] 2.4 (P) Build the theme and the categorical palette
  - **`palette.py`** (append only): `CATEGORICAL_COLORS` (`name -> (hex,
    oklch source)`) and `CATEGORICAL_RAMP` for the eight design entries, with
    the oklch source in each constant's comment. No existing constant moves.
  - **`kit/theme.py`** per design § Theme: `InkRole`, `TEXT`, `STROKE`,
    `CORE_ROLES`, `INK_ROLES`, `REFERENCE_BACKGROUNDS`, `GRID_OPACITY`,
    `ink`, `style_element` (emits `CORE_ROLES` then `extra`; never iterates
    `INK_ROLES`), `Shape`, `SeriesStyle`, `DASHES`, `SHAPES`, `MAX_SERIES`,
    `series_style`, and `shape_path` (the one marker geometry, design §
    Theme).
  - **`tests/render/charts/test_palette.py`**: `_all_documented()` also walks
    `CATEGORICAL_COLORS`; a new test pins the first eight sources in order (a
    prefix pin). Existing assertions are kept.
  - **Tests** (`test_theme.py`), with an independent WCAG contrast
    implementation and the Machado-2009 matrices written in the test (never
    imported from the kit):
    - every base ink and every palette colour ≥3:1 on all four reference
      backgrounds; the light rule ink ≥4.5:1 on `#ffffff`; the dark rule ink
      ≥4.5:1 on each dark background; both rule inks ≥3:1 on all four;
    - every palette pair's OKLab distance ≥0.10 (normal) and ≥0.06 under
      each simulation;
    - contrast and distance tests iterate every `INK_ROLES` entry and the
      whole `CATEGORICAL_RAMP` (so appended roles and colours are checked too);
      `INK_ROLES[:2] == (TEXT, STROKE)` and `CATEGORICAL_RAMP[:8]` equal the
      design's values (prefix pins);
    - `style_element()` equals the design's literal string;
      `style_element((ROLE,))` appends that role's rules after the core ones
      in each `@media` block; with a stub role monkeypatched onto
      `INK_ROLES`, `style_element()` is unchanged;
    - `ink(TEXT)` is `{"class": "ck-t", "fill": "#7f7f7f"}` and its key list
      is exactly `["class", "fill"]`;
    - `series_style(i)` pairs `CATEGORICAL_RAMP[i]`, `DASHES[i]`,
      `SHAPES[i]`; the eight dashes and eight shapes are distinct;
    - `shape_path` for one centre per `Shape` equals a literal subpath (eight
      literals), with round caps for CIRCLE, square caps for SQUARE and a
      stroke for PLUS;
    - the module source contains none of `light-dark(`, `currentColor`.
  - **Mutations:** change the dark ink to `#7f7f7f` (4.5 rule reds); change
    the light ink to `#4d4d4d` (mismatch-safe rule reds on the darks); swap
    palette entries 2 and 5 (prefix pin reds); replace a palette colour with
    `#d5bf36` (contrast reds on white); replace palette entry 6 with a
    near-duplicate of entry 3 that still meets 3:1 (for example
    `oklch(0.57 0.14 345)`; the normal-vision distance reds); replace entries
    1 and 4 with a red/green pair that is ≥0.10 apart in normal vision but not
    under deuteranopia (for example `oklch(0.6 0.15 25)` and
    `oklch(0.6 0.15 140)`; confirm the pair meets contrast and the normal
    threshold first, so only the deuteranopia assertion reds); emit `fill`
    before `class` in `ink()`; iterate `INK_ROLES` in `style_element` (the
    monkeypatch test reds); change one `shape_path` subpath; emit the dark
    block before the light block.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_theme.py
    tests/render/charts/test_palette.py` is green.
  - _Requirements: 8.2, 8.3, 8.4, 8.6, 8.7, 8.8, 18.4_
  - _Boundary: Theme, Palette_
  - **Note:** the mutation colours are starting points; if one does not
    isolate its assertion (it fails contrast, say), pick another that does
    and record it.

- [ ] 3. Shared layer and the entry points

- [x] 3.1 (P) Create the entry points, the registry skeleton and the facade
  - **`kit/registry.py`** with `KINDS: Final[tuple[KindSpec, ...]] = ()`,
    `CORE_KIND_NAMES`, `kind_named`, `kind_names`, `describe_kinds` and the
    `KindListing` family of `TypedDict`s (design § Registry).
  - **`kit/api.py`**: `RenderedChart`, `validate_chart`, `render_chart`,
    `render_spec` (design § Api and System Flows).
  - **`kit/__init__.py`**: re-export exactly the 17 names of design §
    Settled Seams "Facade", in that order, as `__all__` (`ValueKind`,
    `Value`, `Column`, `ChartData`, `ChartRequest`, `OptionValue`, `Output`,
    `ProblemCode`, `ChartProblem`, `ProblemDict`, `ChartError`,
    `RenderedChart`, `validate_chart`, `render_chart`, `describe_kinds`,
    `kind_names`, `KindListing`); not `render_spec` and not the
    `kit.format` helpers (`dashboards` imports `escape_markdown` and
    `clean_text` from `kit.format` directly).
  - **`_helpers.py`** (append): `render_case(spec, request, data)` over
    `render_spec`, and `problems_of(spec, request, data)` returning the
    `ChartError`'s problems.
  - **Tests** (`test_api.py`) with a test-local stub `KindSpec`:
    - `render_spec` runs stage 1, then 2, then the kind's `check`, then
      `draw`, and raises `ChartError` with every problem of the first failing
      stage only (a request fault plus a data fault yields only the request
      problem; a `check` problem prevents `draw`, observed by a draw that
      records its calls);
    - with `registry.KINDS` monkeypatched to two stub specs named `b-stub`
      then `a-stub` (non-alphabetical), `render_chart` with an unknown kind
      raises `unknown_kind` whose `accepted == ("b-stub", "a-stub")`, and
      `render_chart` on `a-stub` reaches that stub's `draw`;
    - `validate_chart` needs no rows;
    - `describe_kinds()` over the same monkeypatch gives two listings in
      registration order, with lists, plain strings and `json.dumps` success;
    - `kind_named`, `kind_names` and `describe_kinds` read `KINDS` at call
      time (the monkeypatch above is the evidence; no import-time index);
    - `fitdocs.render.charts.kit.__all__` equals the design's 17-name tuple
      and every name resolves on the package.
  - **Mutations:** run `draw` before `check`; merge stage-1 and stage-2
    problems; return a `RenderedChart` with empty text instead of raising;
    emit tuples in the listing; build a name→spec dict at import time
    (the monkeypatch tests red); sort `kind_names()`; drop `ChartError` from
    the re-exports (the `__all__` test reds).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_api.py` is
    green; `from fitdocs.render.charts.kit import render_chart` works.
  - _Requirements: 3.2, 4.4, 5.3, 5.5, 5.6_
  - _Boundary: Api, Registry_
  - _Depends: 2.1_

- [x] 3.2 (P) Measure, fit and lay out text and the plot rectangle
  - **`kit/layout.py`** per design § Layout: the font and spacing
    constants, `Rect`, `LegendEntry`, `FramePlan`, `text_width`, `fit_text`,
    `plan_frame` (vertical stack, legend wrapping at 30% label width,
    margins, the fixed two-pass rule is the caller's, recorded in the
    docstring for scales/frame).
  - **Tests** (`test_layout.py`): `text_width` = `len × font × 0.64`;
    `fit_text` unchanged at the limit, shortened by one character plus `…`
    just above it, one character plus `…` at a tiny width; legend entries
    wrap to a second row exactly when the next entry would pass
    `width − PAD`; the plot rectangle moves down by `LEGEND_ROW` per legend
    row and up by `NOTE_ROW` per note; left margin grows with the y-label
    width; nothing is placed outside `[0, width] × [0, height]`.
  - **Mutations:** `CHAR_EM` 0.6; wrap on `>=` instead of `>`; ignore notes
    in the bottom margin; truncate without the ellipsis.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_layout.py` is
    green.
  - _Requirements: 6.3, 7.3, 7.4_
  - _Boundary: Layout_
  - _Depends: 2.4_

- [x] 3.3 (P) Draw marks: lines with dots, areas and bands, bars, points, trends
  - **`kit/marks.py`** per design § Marks: `line_series`, `area_series`,
    `band_path`, `bar`, `zero_stub`, `points`, `trend`; coordinates through
    `fmt_num`; gaps through `series.gap_segments`.
  - **Tests** (`test_marks.py`):
    - a series with a `None` in the middle yields two polylines; a lone
      present point between `None`s yields one round-cap dot; the dash
      attribute is present for series 1–7 and absent for series 0;
    - `area_series` closes each segment to the baseline; `band_path`
      returns the `d` attribute value only (a `str` starting `M` and ending
      `Z`, containing no `<`), visiting the upper edge forward and the lower
      edge backward;
    - `zero_stub` is 2 px tall centred on the zero line;
    - `points` emits one `<path>` per call and equals
      `theme.shape_path(style.shape, centres, style.color)` for every shape
      (marks holds no shape geometry); coordinates carry ≤2 decimals;
    - `trend` carries the series colour and `5 3` dash.
  - **Mutations:** pass `y` with `None` replaced by 0 (gap test reds);
    draw single-point segments as polylines (dot test reds); emit one
    `<path>` per point; draw points with a local circle geometry instead of
    `shape_path`; walk the lower band edge forward.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_marks.py` is
    green.
  - _Requirements: 8.8, 9.1, 9.2_
  - _Boundary: Marks_
  - _Depends: 2.4_

- [x] 3.4 (P) Share series grouping, numeric extraction and the x/y checks
  - **`kit/cartesian.py`** per design § Cartesian: `SeriesGroup`,
    `series_groups`, `category_order`, `numbers`, `undrawn`, `bound_problem`,
    `series_problem`, `duplicate_problem`, `log_problem`, `stack_problems`,
    each problem with the design's message and fix wording.
  - **Tests** (`test_cartesian.py`):
    - groups in first-appearance order (`Run` before `Bike`), absent colour
      last labelled `—`, booleans `true`/`false`; no colour channel → one
      group named by the y label;
    - `category_order`: first appearance for categories, ascending for
      dates (fixture rows not date-sorted), absent last;
    - `undrawn` counts a row absent on x and y once, under x;
    - `bound_problem` silent at the limit and reporting at limit+1 with the
      limit and count in the message;
    - `series_problem` silent at 8 groups, reporting at 9 (the `—` group
      counts);
    - `duplicate_problem` names the first duplicate row (not row 0);
    - `log_problem` reports `0` and a negative, silent for absent;
    - `stack_problems`: absent, negative and (with `complete`) a missing
      (series, x) pair, each alone.
  - **Mutations:** sort groups by label; put the absent group first; count
    a doubly-absent row twice; `>=` in the bound check; skip absent values
    as zero in `stack_problems`.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_cartesian.py`
    is green.
  - _Requirements: 6.6, 6.7, 9.3, 9.4, 11.2, 11.3, 12.2, 13.3_
  - _Boundary: Cartesian_
  - _Depends: 2.2, 2.4_

- [ ] 4. Scales and the chart frame

- [x] 4.1 Build numeric and band scales with the domain rules
  - **`kit/scales.py`** per design § Scales: `ScaleType`, `Side`, `Tick`,
    `NumericScale`, `BandScale`, `numeric_scale`, `band_scale`; scale
    choice by column kind; `include_zero` before degeneracy; the degenerate
    rules; `nice` versus exact extents; vertical and horizontal tick counts
    with the label-fit loop; date, date-time, duration, pace and number
    labels; the `integer` option (passed to `linear_ticks`, degenerate pad 1).
  - **Tests** (`test_scales.py`):
    - each degenerate rule (number `v`≠0, `v`=0, `include_zero` with all
      zeros → `[0, 1]`, log, date ±1 day, date-time ±3600 s) yields a domain
      of positive width containing the value;
    - `nice=False` keeps the exact extent; `nice=True` encloses it at ticks;
    - a 720 px date axis over a year never yields overlapping estimated
      labels and a 320 px one yields fewer ticks;
    - a date-time axis under two days labels `HH:MM` and returns the date
      for the axis title, and `MM-DD HH:MM` when crossing midnight;
    - a duration axis reaching 3600 s labels every tick `h:mm:ss`;
    - pace axes increase upward (not inverted);
    - `integer=True` over counts 0–3 gives whole-number ticks only, and over
      all-zero counts with `include_zero` gives `[0, 1]`; the same data with
      `integer=False` yields a 0.5 tick (precondition shown);
    - `band_scale` labels every band when the widest label fits and every
      k-th otherwise, from band 0.
  - **Mutations:** skip `include_zero` before the degenerate rule (all-zero
    domain collapses); drop the overlap loop; label durations per tick
    rather than per axis; invert pace axes; drop `integer` when calling
    `linear_ticks`.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_scales.py` is
    green.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7_
  - _Depends: 2.2, 2.3, 3.2_

- [x] 4.2 Draw the frame: root, metadata, axes, grid, legend, notes and the no-data state
  - **`kit/frame.py`** per design § Frame: `document`, `title_text`, `grid`,
    `axis`, `legend`, `notes`, `no_data`, `describe`; group classes, draw
    order, note wording and description wording exactly as designed.
  - **Tests** (`test_frame.py`):
    - `document` emits the root attributes in order (`xmlns`, `width`,
      `height`, `viewBox`, `role`, `font-family`), then `<title>`, `<desc>`,
      the style element, then the body; no `id=`, no background `<rect>`;
      caller text with `<`, `&` and `\x01` is escaped and cleaned;
    - every `<text>` carries `ck-t` and every stroked axis/grid element
      `ck-s`; gridlines carry `stroke-opacity="0.25"`;
    - axis label anchoring per side; the axis title uses `axis_title`;
    - legend swatches per kind of swatch (line sample with dash, shape,
      block); `frame` draws the shape swatch with `theme.shape_path` and does
      not import `marks`; for every `Shape`, the swatch's path equals
      `marks.points([(cx, cy)], style)` at the same centre (the test imports
      both);
    - notes wording for one and several channels, singular `row`;
    - `describe` wording for a chart and both no-data forms;
    - `no_data` draws `No data`, adds the second line only when rows exist,
      keeps the given size.
  - **Mutations:** add `id="chart"` to the root; put `<desc>` before
    `<title>`; drop `ck-t` from legend labels; write `1 rows`; always draw
    the second no-data line; draw a fixed circle swatch for every shape (the
    equality test reds for the seven non-circle shapes).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_frame.py` is
    green.
  - _Requirements: 7.1, 7.2, 8.1, 8.3, 8.5, 9.3, 9.6, 9.7, 10.1, 10.2, 10.3_
  - _Depends: 3.3, 4.1_

- [ ] 5. The eight core kinds

- [x] 5.1 (P) Implement the line kind with its goldens
  - **`kit/kinds/line.py`**: `KIND` per the design's kind table (channels,
    `svg_options(x_scale, y_scale, y_zero, height=320)`, bound 2000 rows
    refuse, `max_series` 8) and the per-kind rules (`_validate`: log on a
    time column; `_check`: bound, series, duplicate (series, x), log
    domain; `_draw`: exact x extent, niced y, series sorted by x, gaps,
    dots, the note for rows without x or y, legend when coloured).
  - **Tests** (`test_line.py`) through `_helpers.render_case`:
    - each refusal alone; 2000 rows render and 2001 refuse;
    - rows given out of x order are joined in x order;
    - an absent y mid-series splits the line; an isolated point is a dot;
      rows without x or y are counted in the note and the description;
    - series order is first appearance (`Run` before `Bike`) and the absent
      colour series is last, labelled `—`;
    - `y_zero` includes zero; log axes accept positive data.
  - **Goldens** (`golden/line/`, one per entry of the module's `CASES`):
    `typical` (two series, dates, an absent y
    mid-series, rows out of order), `empty`, `all_absent`, `single`,
    `negative`, `long_labels`, `at_bound`, `log`, `dates_gap` (a run of
    absent days); a `main()` writer.
  - **Mutations** (kind-local, in `kinds/line.py` only; each recorded with
    the goldens it reds): skip the x sort (`typical`, whose rows are out of
    order); replace absent y with 0 before building points (`typical`,
    `dates_gap`); build a linear scale when `log` is requested (`log`); ignore
    `y_zero`; drop the duplicate-(series, x) check from `_check`; drop the
    log-on-time conflict from `_validate`. The standard classes (`empty`,
    `all_absent`, `long_labels`, `single`, `negative`, `at_bound`) are shown
    red in task 6.2.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_line.py` is
    green, and every golden outside the classes 6.2 covers for `line` has a
    recorded kind-local mutation that reds it.
  - _Requirements: 9.1, 9.3, 9.6, 9.7, 10.1, 11.1, 11.2, 12.1, 12.2, 12.3, 18.1, 18.3_
  - _Boundary: line kind_
  - _Depends: 3.1, 3.3, 3.4, 4.2_

- [x] 5.2 (P) Implement the area kind with its goldens
  - **`kit/kinds/area.py`**: `KIND` per the kind table (`stack` option,
    bound 1000 rows) and rules (`_check`: bound, series, duplicate; with
    `stack`, `stack_absent`, `stack_negative`, `stack_incomplete`;
    `_draw`: zero always in y; unstacked translucent fills at
    `fill-opacity 0.2` under dashed outlines breaking at absent y; stacked
    opaque bands bottom to top in legend order with outlines).
  - **Tests** (`test_area.py`): each stacking refusal alone (absent,
    negative, a missing (series, x)); unstacked absent y breaks both fill
    and outline; stacked band k's lower edge equals band k−1's upper edge;
    zero included even when every value is positive; 1000 render, 1001
    refuse.
  - **Goldens** (`golden/area/`, one per entry of the module's `CASES`):
    `typical`, `empty`, `all_absent`,
    `single`, `negative`, `long_labels`, `at_bound`, `stacked`; a `main()`
    writer.
  - **Mutations** (kind-local, in `kinds/area.py` only): stack in reverse
    legend order (`stacked`); pass `include_zero=False` for y (`typical`,
    whose values are all positive); replace absent y with 0 before drawing
    (`typical`); call `stack_problems` with `complete=False` (the
    missing-pair test reds); drop the `fill-opacity` for unstacked fills.
    Standard classes: task 6.2.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_area.py` is
    green, and every golden outside the classes 6.2 covers for `area` has a
    recorded kind-local mutation that reds it.
  - _Requirements: 6.5, 9.1, 9.5, 12.4, 12.5, 18.1, 18.3_
  - _Boundary: area kind_
  - _Depends: 3.1, 3.3, 3.4, 4.2_

- [x] 5.3 (P) Implement the bar kind with its goldens
  - **`kit/kinds/bar.py`**: `KIND` per the kind table (`stack`, bound 200
    rows) and rules (band x in category order, dates ascending, absent `—`
    last; y includes zero; grouped bars 80% of the band, ≤48 px; absent y no
    bar plus a note; zero y a stub; negative bars below zero; stacked
    segments bottom to top in legend order; `stack_absent`,
    `stack_negative`; duplicate (x, colour)).
  - **Tests** (`test_bar.py`): a zero bar and an absent bar differ (stub vs
    nothing, the absent one counted in the note); grouped order within a
    band equals legend order; dates ascending from unsorted rows; a missing
    (x, series) row in a stacked chart draws no segment and refuses nothing;
    each refusal alone; 200 render, 201 refuse.
  - **Goldens** (`golden/bar/`, one per entry of the module's `CASES`):
    `typical` (categories, a zero, an absent),
    `empty`, `all_absent`, `single`, `negative`, `long_labels`, `at_bound`,
    `stacked`, `dates`; a `main()` writer.
  - **Mutations** (kind-local, in `kinds/bar.py` only): skip the
    `zero_stub` call (`typical`); draw an absent y as a zero-height bar and
    leave it out of the note (`typical`); sort the labels returned by
    `category_order` (`typical`, whose categories are not alphabetical);
    build date bands in row order instead of from `category_order` (`dates`,
    whose rows are not date-sorted); group series right to left (`typical`
    when coloured, `stacked`); skip `stack_problems` when `stack` is set
    (the negative-stack test reds); drop the 48 px bar-width cap (`single`,
    which 6.2's degenerate-pad mutation does not reach for bars). Other
    standard classes: task 6.2.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_bar.py` is
    green, and every golden outside the classes 6.2 covers for `bar` has a
    recorded kind-local mutation that reds it.
  - _Requirements: 6.5, 6.7, 9.2, 9.4, 9.5, 13.1, 13.2, 13.3, 18.1, 18.3_
  - _Boundary: bar kind_
  - _Depends: 3.1, 3.3, 3.4, 4.2_

- [x] 5.4 (P) Implement the hbar kind with its goldens
  - **`kit/kinds/hbar.py`**: `KIND` per the kind table (`sort` value|rows,
    bound 50, auto height) and rules (16 px bars on 26 px rows; value
    descending, ties in row order, absent values last, absent y rows after
    all others; left margin to 40% width; x includes zero; negatives left of
    zero; value labels without unit, `—` for absent, a stub for zero).
  - **Tests** (`test_hbar.py`): ranking with a tie whose row order differs
    from label order; absent value last with `—`; absent y last labelled
    `—`; `sort: rows` keeps row order; auto height = rows × 26 plus frame;
    duplicate y refused; 50 render, 51 refuse.
  - **Goldens** (`golden/hbar/`, one per entry of the module's `CASES`):
    `typical`, `empty`, `all_absent`,
    `single`, `negative`, `long_labels`, `at_bound`, `rows`; a
    `main()` writer.
  - **Mutations** (kind-local, in `kinds/hbar.py` only): sort ascending;
    break ties by label; put absent values first; drop value labels; ignore
    `sort: rows` (`rows`); drop the 160 px minimum height (`single`, which
    6.2's degenerate-pad mutation does not reach for hbar). Other standard
    classes: task 6.2.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_hbar.py` is
    green, and every golden outside the classes 6.2 covers for `hbar` has a
    recorded kind-local mutation that reds it.
  - _Requirements: 6.5, 9.2, 9.4, 13.4, 13.5, 18.1, 18.3_
  - _Boundary: hbar kind_
  - _Depends: 3.1, 3.3, 3.4, 4.2_

- [x] 5.5 (P) Implement the scatter kind with its goldens
  - **`kit/kinds/scatter.py`**: `KIND` per the kind table (`x_scale`,
    `y_scale`, `trend`, bound 2000) and rules (`_validate`: trend with log,
    log on time; `_check`: bound, series, log domain; `_draw`: niced axes,
    one points path per series with its shape, rows without x or y in the
    note, trend per series with ≥2 distinct x as least squares over drawn
    points, other series named in a note).
  - **Tests** (`test_scatter.py`): the trend endpoints equal a hand-computed
    least-squares fit on a fixture whose slope is not 1 and intercept not 0;
    a series with one distinct x gets no trend and is named in the note;
    date x regresses on days; each refusal alone; 2000 render, 2001 refuse.
  - **Goldens** (`golden/scatter/`, one per entry of the module's `CASES`):
    `typical` (three series, an absent
    value), `empty`, `all_absent`, `single`, `negative`, `long_labels`,
    `at_bound`, `trend`; a `main()` writer.
  - **Mutations** (kind-local, in `kinds/scatter.py` only): regress x on y
    (`trend`); pass `series_style(0)` for every series (`typical`); draw a
    trend for a one-x series; drop the trend-with-log conflict from
    `_validate`. Standard classes: task 6.2.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_scatter.py`
    is green, and every golden outside the classes 6.2 covers for `scatter`
    has a recorded kind-local mutation that reds it.
  - _Requirements: 6.6, 9.3, 14.1, 14.2, 14.3, 18.1, 18.3_
  - _Boundary: scatter kind_
  - _Depends: 3.1, 3.3, 3.4, 4.2_

- [x] 5.6 (P) Implement the histogram kind with its goldens
  - **`kit/kinds/histogram.py`**: `KIND` per the kind table (`bins`,
    `bin_width`, bound 100 bins reduce) and rules (`_validate`: both options
    → `option_conflict`; `_check`: more than 100 bins → `over_bound`; the
    three binning rules; half-open bins with a closed last bin; the
    degenerate one-bin rule; the count axis through `numeric_scale(...,
    include_zero=True, integer=True)` (4.1); absent values in the note; x
    labelled in the column's unit).
  - **Tests** (`test_histogram.py`): a value exactly on an inner edge falls
    in the upper bin and the maximum in the last bin; the default bin count
    follows Sturges for n = 1, 7, 8, 1000 (clamped at 50 above); `bins` and
    `bin_width` give the stated edges; all-equal values make one bin; a
    `bin_width` producing 101 bins refuses and one producing 100 renders;
    duration columns bin on the duration ladder; 100,000 values render
    (reduction, no refusal).
  - **Goldens** (`golden/histogram/`, one per entry of the module's `CASES`):
    `typical`, `empty`, `all_absent`,
    `single`, `negative`, `long_labels`, `at_bound` (exactly 100 bins),
    `bins`, `bin_width`; a `main()` writer.
  - **Mutations** (kind-local, in `kinds/histogram.py` only): close bins on
    the left; drop the last-bin closure (the maximum vanishes); use `floor`
    instead of `ceil` in Sturges (`typical`); `>` → `>=` in the kind's own
    bin-count comparison (`at_bound`, since histogram does not call
    `bound_problem`); pass `integer=False` for the count axis (a golden whose
    largest count is 3 reds); make the one-bin width 1 instead of
    `nice_step(|v|/10)` (`single`, which 6.2's degenerate-pad mutation does
    not reach for histograms). Other standard classes: task 6.2.
  - **Observable:** `uv run pytest tests/render/charts/kit/test_histogram.py`
    is green, and every golden outside the classes 6.2 covers for
    `histogram` has a recorded kind-local mutation that reds it.
  - _Requirements: 6.5, 11.2, 14.4, 14.5, 18.1, 18.3_
  - _Boundary: histogram kind_
  - _Depends: 3.1, 3.3, 3.4, 4.1, 4.2_

- [x] 5.7 (P) Implement the stat kind with its goldens
  - **`kit/kinds/stat.py`**: `KIND` per the kind table (`value`, `compare`,
    `delta` absolute|percent|both, bound 1 row) and rules (`_validate`:
    compare kind and unit match; `_check`: more than one row; output format,
    signs, percentage change with `—` for a zero comparison, the no-row and
    absent forms, title escaped).
  - **Tests** (`test_stat.py`): each output form; `±0.0 km` for an equal
    comparison; a pct value's absolute delta in `pp`; a duration value and
    delta; compare of another kind → `channel_kind`, another unit →
    `unit_mismatch`; two rows refuse; a title with `*`, `|`, `<` and `#`
    escaped.
  - **Goldens** (`golden/stat/*.md`, one per entry of `CASES`): `value`,
    `compare_absolute`,
    `compare_percent`, `compare_both`, `absent_value`, `absent_compare`,
    `no_rows`, `special_chars`; a `main()` writer.
  - **Mutations** (kind-local, in `kinds/stat.py` only): divide by
    `compare` without `abs` (`compare_percent` with a negative comparison);
    show `0` for an absent value (`absent_value`); skip the
    `escape_markdown` call on the title (`special_chars`); write the
    absolute delta for `delta: percent` (`compare_percent`); change the
    no-row wording (`no_rows`); `>` → `>=` in the kind's own row-count
    comparison, or in its call of `bound_problem` if it uses one (the
    one-row case refuses); drop the comparison clause when `compare` is
    absent instead of `(— vs —)` (`absent_compare`).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_stat.py` is
    green and every golden has a recorded kind-local mutation that reds it.
  - _Requirements: 9.8, 15.1, 15.2, 15.3, 15.4, 18.2, 18.3_
  - _Boundary: stat kind_
  - _Depends: 2.1, 2.2, 3.1, 1.4_

- [x] 5.8 (P) Implement the table kind with its goldens
  - **`kit/kinds/table.py`**: `KIND` per the kind table (no channels,
    `uses_all_columns`, bound 100 rows and 12 columns) and rules (headers
    from `axis_title`, right alignment for NUMBER/DURATION, cells without
    unit, `—` for absent, category text escaped with `|` as `\|` and line
    breaks as spaces, the no-rows form).
  - **Tests** (`test_table.py`): every value kind in one table; alignment
    row; a category containing `|`, `<b>`, `#tag`, `[[x]]` and a newline
    stays one cell and renders literally; 100 rows render, 101 refuse; 12
    columns render, 13 refuse at validation (no rows needed).
  - **Goldens** (`golden/table/*.md`, one per entry of `CASES`); `typical`
    holds every value kind, a DATETIME column among them (task 6.4's
    timezone mutation reaches the suite through it): `typical`,
    `no_rows`,
    `special_chars`, `at_bound`; a `main()` writer.
  - **Mutations** (kind-local, in `kinds/table.py` only): left-align
    numbers (`typical`); skip the `escape_markdown` call for category cells
    (`special_chars`); write `str(value)` for absent cells instead of
    `format_value` (`typical`); pass `with_unit=True` for cells (`typical`);
    change the no-rows wording (`no_rows`); `>` → `>=` in the kind's own row
    comparison (`at_bound` refuses) and in its column comparison (the
    12-column test reds).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_table.py` is
    green and every golden has a recorded kind-local mutation that reds it.
  - _Requirements: 2.7, 9.8, 15.5, 15.6, 18.2, 18.3_
  - _Boundary: table kind_
  - _Depends: 2.1, 2.2, 3.1, 1.4_

- [ ] 6. Integration and cross-cutting validation

- [x] 6.1 Register the core kinds and pin the registry
  - **`kit/registry.py`**: `KINDS` becomes the eight core kinds in the
    design's order; nothing else changes.
  - **Tests** (`test_registry.py`):
    - `kind_names()[:8] == CORE_KIND_NAMES` (a prefix pin: an appended kind
      keeps it green) and `len(KINDS) >= 8`;
    - names unique and grammatical; per kind, channel and option names
      unique, grammatical and disjoint; every default valid for its spec;
      SVG kinds end with `width`, `height`; markdown kinds have neither;
      `max_series` ≤ `MAX_SERIES`;
    - `describe_kinds()` equals a literal listing for `line` and `stat`
      (field by field) and round-trips through `json.dumps`;
    - for every registered kind, `render_chart` on the first entry of its
      test module's `CASES` (found by the naming convention) equals that
      case's golden, so the registry path and `render_spec` agree; the test
      asserts it checked as many kinds as `KINDS` holds;
    - `validate_chart` on an unknown kind lists `kind_names()`, whose first
      eight are the core names.
  - **Mutations:** register `area` before `line`; duplicate a kind; give a
    channel and an option the same name in a test-local spec; drop
    `uses_all_columns` from the listing; route `render_chart` past `check`.
  - **Observable:** `uv run pytest tests/render/charts/kit` is green.
  - _Requirements: 3.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - _Depends: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [ ] 6.2 Show every standard golden class red under its shared-layer mutation
  - **Sequential, after 6.1, and alone in the tree**: the only task that
    mutates shared kit modules to red several kinds' goldens at once. No new
    test file; the evidence is the kind golden tests (`tests/render/charts/kit/test_*.py`)
    going red together.
  - For each mutation below: take a `cp` of the module, apply it, run
    `uv run pytest tests/render/charts/kit`, record which goldens went red,
    restore from the `cp`, and confirm green. Assert from the record that every
    registered kind with a golden of that class went red, except the kinds
    named as not reached, each of which carries a kind-local mutation for that
    class in its own task:
    - `empty` — change the no-data wording in `frame` (`No data` → `No rows`):
      every SVG kind's `empty`;
    - `all_absent` — drop the no-data second line in `frame`: every SVG kind's
      `all_absent`;
    - `long_labels` — make `layout.fit_text` truncate without the ellipsis:
      every SVG kind's `long_labels` (each kind task's `long_labels` golden
      contains `…`, the precondition, asserted in its test);
    - `single` — set the degenerate-domain pad in `scales` to 0: `line`,
      `area`, `scatter` (not reached: `bar`, `hbar`, `histogram`, whose
      `single` value axis includes zero or is binned; their kind-local
      mutations are in 5.3, 5.4, 5.6);
    - `negative` — clamp the value-axis domain's lower edge at 0 in
      `scales.numeric_scale`: every SVG kind's `negative`;
    - `at_bound` — `>` → `>=` in `cartesian.bound_problem`: `line`, `area`,
      `bar`, `hbar`, `scatter` (not reached: `histogram`, `stat`, `table`,
      which compare their own bounds; kind-local mutations in 5.6–5.8).
  - A class a mutation was expected to reach but did not is reported
    UNPINNED with the kind named, not hidden.
  - **Observable:** the Implementation Notes hold, per mutation, the list of
    goldens that went red, matching the lists above, and the suite is green
    after every restore.
  - _Requirements: 18.1, 18.3_
  - _Depends: 6.1_

- [ ] 6.3 Check every golden for the theme and the size budgets
  - **Theme coverage** (`test_theme_coverage.py`): for every registered SVG
    kind, find its test module by the naming convention and walk
    `golden/<name>/`; assert the number of SVG files walked equals the sum of
    those kinds' `len(CASES)` (51 today, derived, never a literal), so the
    walk cannot pass empty or partial; and assert for each file: exactly one
    `<style>` equal to `style_element()`; root `role="img"` and
    `font-family`; `<title>` then `<desc>` as first children, both non-empty;
    every `<text>` has `ck-t`; every stroked element in `ck-axis` and
    `ck-grid` has `ck-s`; every `#rrggbb` literal is in the whitelist (the
    base, light and dark inks of every `INK_ROLES` entry, plus
    `CATEGORICAL_RAMP`; an appended palette is added here by the appending
    spec — a named re-pin point); none of `id=`, `light-dark(`, `currentColor`,
    `<image`, `<script`, `<foreignObject`; no full-canvas `<rect>`.
  - **Size budgets** (`test_size_budget.py`): build each typical chart named
    in design § Testing Strategy and assert its byte budget; assert every
    `at_bound` golden ≤ 80,000 bytes. The design's numbers are initial
    budgets: record the measured sizes in the Implementation Notes; a budget
    the measurement exceeds is a stop-and-report (design change); one with more
    than 40% headroom is lowered to the measured size plus 25%, and from then
    on this test module is the source of truth for the numbers.
  - **Mutations:** give one kind a literal `#333333` text fill; drop the
    style element from `frame.document`; emit one `<circle>` per scatter
    point; add `id="x"` to the root.
  - **Observable:** both test modules are green and each mutation reds them.
  - _Requirements: 8.5, 8.6, 10.1, 10.2, 11.4, 11.5, 16.3_

- [ ] 6.4 Prove byte determinism across processes
  - **`test_determinism.py`**: render every case of every registered kind
    (test modules found by the naming convention; the test asserts it saw
    `len(KINDS)` modules) twice in-process and assert equality; then run two
    subprocesses with `sys.executable`, the repository root as `cwd` (so
    `tests.*` imports) and `env={**os.environ, "PYTHONHASHSEED": …, "TZ": …,
    "LC_ALL": …}` — first `0`/`UTC`/`C`, then `1`/`Pacific/Auckland`/`C.UTF-8`
    — each printing one SHA-256 per case; assert the two maps are equal and
    match the in-process digests. Building the child environment from
    `os.environ` keeps the root conftest's `PYTHONDONTWRITEBYTECODE=1`, so the
    children write no `__pycache__` (`tests/test_bytecode_hygiene.py` stays
    green). A request whose `channels` and `options` mappings are built in
    reverse order renders identical bytes. The locale variant is chosen here
    in addition to 6.5's `locale` import ban.
  - **Mutations:** iterate a `set` of series labels when grouping (reds under
    the hash-seed pair); format a date-time through
    `value.astimezone(timezone.utc)` (a naive value read as local time shifts
    12–13 h under `Pacific/Auckland`, so the digests differ; the case that
    reaches it is `table/typical`, whose DATETIME column 5.8 guarantees); iterate
    `request.options` order when building the frame (reds the
    reversed-mapping case).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_determinism.py`
    is green; each mutation reds it.
  - _Requirements: 16.1, 16.2_

- [ ] 6.5 Guard the kit's imports and purity
  - **`test_boundary.py`** following `tests/connectors/test_boundary.py` and
    `tests/compose/test_boundary.py`:
    - a hand-kept tuple of every kit module, checked equal to an `rglob` of
      `src/fitdocs/render/charts/kit` both ways, with `len >= 24`;
    - every import is standard library (`sys.stdlib_module_names`) or in the
      allow-list (`fitdocs.render.charts.svg`, `.series`, `.palette`,
      `fitdocs.render.charts.kit` and its submodules, `fitdocs.units`),
      relative imports resolved; forbidden roots `fitdocs.index`,
      `fitdocs.query`, `fitdocs.dashboards`, `fitdocs.model`,
      `fitdocs.ingest` by dotted descent;
    - the layer direction: a rank matrix over design § Architecture's order
      (`units`, `data`, `problems`, `schema`, `format`, `ticks`, `theme`,
      `layout`, `scales`, `frame`, `marks`, `cartesian`, `validate`, the kind
      modules and `kinds/__init__` sharing one rank, `registry`, `api`,
      `__init__`; precedent `tests/query/test_boundary.py`
      `_QUERY_DIRECTION`); every kit import must point at a strictly lower
      rank, so kinds never import another kind, `registry` or `api`, and
      `frame` never imports `marks`. Import targets are resolved as in
      `tests/compose/test_boundary.py` `_import_targets`: relative imports
      against the module's package, and `from <pkg> import <name>` to the
      submodule `<pkg>.<name>` when one exists (so
      `from fitdocs.render.charts.kit import marks` is seen as `marks`);
    - compose's clock spellings and clock names, plus `random`, `uuid`,
      `secrets`, `locale`, `os.environ`, `getenv`, `open(`;
    - synthetic positive controls for each rule (an import of each forbidden
      root, a third-party import, a relative import escaping the kit, each
      clock form, and `from fitdocs.render.charts.kit import marks` inside a
      source attributed to `frame`) and a negative control (an injected
      `today` parameter);
    - the module tuple and the rank matrix are full pins, named in the
      plan's Cross-spec shared files as re-pin points for an appending spec.
  - **Mutations:** add `from fitdocs.model import Activity` to one kit
    module; add `import random`; add `datetime.now()`; import `registry`
    from a kind; add `from . import marks` to `frame.py` (the rank check
    reds); empty the module tuple (the both-ways check reds).
  - **Observable:** `uv run pytest tests/render/charts/kit/test_boundary.py`
    is green; each mutation reds it.
  - _Requirements: 16.3, 16.4, 18.5_

- [ ] 7. Records and final validation

- [ ] 7.1 Record the relaxation and the import direction, and run the full suite
  - **`src/fitdocs/render/charts/svg.py`**: docstring only — the element
    subset gains `title`, `desc` and `style`, with the relaxation that a
    chart-kit SVG carries exactly one `<style>` element (the theme's media
    queries). Code unchanged.
  - **`.kiro/steering/structure.md`**: the design's paragraph on `units` and
    the kit's import direction, appended to Code Organization Principles,
    worded without an exhaustive importer list (`units` "imports only the
    standard library and is a leaf module any layer may import; today
    `index.schema` and the kit do"); and `units` added to the existing
    `index` bullet's import list ("… `settings`, `version`, `units` and the
    load payload readers; …"), keeping that bullet's `index.derived`
    sentence inside it (`tests/index/derived/test_published.py:28-33` finds
    the bullet by splitting the file on its leading ``- `index` `` marker).
  - **`tests/connectors/test_network_statements.py:680-685`** (controller
    ruling): re-pin the exact `index`-bullet phrase to the new wording
    ("`settings`, `version`, `units` and the load payload readers; only
    `cli` and `query` import it; only `index.store` imports `duckdb`.").
    Mutation: drop `units` from the bullet in `structure.md` (the re-pinned
    phrase reds); restore from a `cp`. Run that file and
    `tests/index/derived/test_published.py` afterwards.
  - **`.kiro/specs/analytics-index/design.md`**: a dated note beside its
    unit-suffix table that the table's single source is now
    `fitdocs.units.UNITS` and its values are unchanged.
  - **Preservation evidence (no new test):** the existing renderer golden
    tests (`tests/render/charts/test_{hero,calendar,zones,map_golden}.py`,
    `tests/render/test_golden_docs.py`, `tests/history/test_page.py`) run
    unmodified and green, and `git diff --stat $(git merge-base HEAD main) --
    <the four renderer modules> tests/render/charts/golden
    tests/render/golden_docs tests/history/golden` is empty, and
    `git diff $(git merge-base HEAD main) -- pyproject.toml` shows only
    added `[tool.mypy].files` lines (no `[project] dependencies` change);
    record both outputs in the Implementation Notes. (A git-reading test is
    avoided: CI checkouts are shallow.)
  - **Validation:** `uv run pytest && uv run ruff check . && uv run ruff
    format --check . && uv run mypy` green; the steering edit read end to
    end and grepped across `.kiro/steering/` and `CLAUDE.md` for statements
    it contradicts.
  - **Observable:** the full validation command is green on the branch, the
    renderer/golden diff is empty and the `pyproject.toml` diff touches only
    `[tool.mypy].files`.
  - _Requirements: 2.2, 17.1, 17.2, 17.3_

- [ ]* 7.2 (maintainer only) Visual check of the goldens in light and dark viewers
  - Optional and maintainer-only, following analytics-index 8.5's precedent:
    it does **not** gate feature GO, and no implementer or reviewer subagent
    runs it. The contrast arithmetic (2.4) and the coverage walk (6.3) pin the
    mechanism; this looks at real viewers.
  - Open a few goldens per kind as images in Chromium or Firefox inside a
    page with `color-scheme: light` and `color-scheme: dark`, and in Safari;
    the observable result is a note in the Implementation Notes saying where
    text was and was not readable.
  - _Requirements: 8.3_

## Implementation Notes

- 2.3 (controller ruling, 2026-10-12): `calendar_ticks` and `clock_ticks` never return an empty or lone-tick set when the span holds ≥2 ticks of some step. With `allowed = max(max_count, 2)`: take the finest step with 2..allowed ticks; else thin the coarsest overflowing step every k-th from the first; else (every step <2 ticks) keep the finest step. So `max_count=1` may yield 2 ticks. Design § Ticks' "at most max_count" is refined accordingly.
- 2.3 → 4.1: `linear_ticks` returns 3 ticks for `max_count=2` on a range with lo<0<hi (two ticks cannot enclose it). `numeric_scale`'s label-fit loop must measure the ticks it gets back, not trust `max_count`. Degenerate input (lo ≥ hi, non-finite) raises `ValueError`: Scales widens first.
- 2.2: `axis_title(column, *, hours=True)` gained the `hours` keyword (design signature lacked a way to choose `(m:ss)` vs `(h:mm:ss)`); Scales passes the axis's label form.
- 3.3 (controller ruling): `marks.bar(x, y, width, height, color)` — `y` is the zero-line pixel, `height` signed (positive = upward); `width` signed the same way (negative extends left from `x`), so hbar calls `bar` with `x` = zero-line pixel and a signed width. Emitted width/height are non-negative. Bar and hbar kinds (5.3, 5.4) must call it this way.
- 3.2 → 4.2: `FramePlan.y_title_y`/`x_title_y` are `float | None` (None when there is no such title; design § Layout typed them `float`). Frame must handle None. The title→legend and y-title→plot `PAD` gaps are this task's choices (Req 7.3). With a legend and no y title the plot top abuts the last legend row: frame must keep the top y tick label clear of it.
- 3.4 (controller ruling): `cartesian.duplicate_problem(bound, keys, *, skip_absent=())` — rows absent on any bound channel named in `skip_absent` are exempt; unbound key channels are skipped (an unbound colour is one series). Line and area pass `skip_absent=("x",)`, hbar `("y",)`, bar nothing (an absent x is the `—` category). `stack_problems` never builds styles, so it is safe before `series_problem` refuses >8 series; `series_groups` (draw only) raises beyond 8.
- 3.1 (controller ruling): `render_spec(spec, request, data)` takes `RenderedChart.kind` from `spec.name` (a request kind mismatch is not checked). `render_chart` on an unknown kind raises `ChartError` with all of stage 1 (`unknown_kind`, `empty_title`, `duplicate_column`). Nested listing TypedDicts are `ChannelListing`, `OptionListing`, `BoundListing` (not re-exported).
- 4.1 (controller rulings): `NumericScale` gained trailing `clock_date: date | None = None` (the date a same-day date-time axis puts in its title) and `hours: bool = True` (the duration label form); frame passes both to `axis_title`. Label fit = adjacent centre distance ≥ (w1+w2)/2 + 10 px. Time axes keep their exact extent (ignore `nice`/`include_zero`); log ignores `include_zero`. Date-time clock ticks are computed relative to midnight of lo's day and filtered to [lo, hi]. `band_scale` thins by band size, which suits horizontal bands; hbar (5.4) must not thin its row labels by 26 px row height.
- 5.8 (controller ruling): `format.format_duration(seconds, *, hours: bool | None = None)` — None is the per-value form (unchanged), True forces `h:mm:ss`, False forces `m:ss` with unbounded minutes. The table decides each duration-family column once (`h` = any present value with rounded magnitude ≥ 3600; no present values → `(m:ss)`) and uses that `h` for both the header `axis_title(c, hours=h)` and every cell, so header and cells always agree. Table headers go through `clean_text` then `escape_markdown`. Design § Formatter/§ Kinds (table) to be amended.
- 4.2 (controller rulings): `frame.not_drawn_note(counts) -> str | None` follows chart-catalog A2 exactly (zero counts skipped, given order, None when all zero) — chart-catalog consumes it. `frame.no_trend_note(series)` is the scatter no-trend note. `axis(..., title: str | None = None)`: None derives `axis_title(column, clock_date, hours)` for a NumericScale; a string is used verbatim; `""` draws no title; a BandScale needs a string. n=1 is singular ("None of the 1 row has a value to draw."). Every axis title and bottom band label is fitted to the room at its own anchor and stays inside [PAD, width−PAD]; bottom band labels are cleaned and fitted to min(k·band−4, edge clamp). Kinds must call frame this way.
- 5.1–5.6 (controller rulings, cross-kind): (1) every text stays inside the canvas — each cartesian kind reserves the first x tick label's left overhang (widening the left margin) and the last one's right overhang, measured on a provisional plot, and pins it with a test over CASES that also asserts it found every `<text>`; (2) `describe` ranges are named by the drawn axis title (`axis_title(col, clock_date=scale.clock_date, hours=scale.hours)`) and duration-family bounds (DURATION kind or a duration-family unit such as `s`) are formatted with `format_duration(v, hours=scale.hours)`; ranges are the drawn values' extremes; (3) body draw order follows design § Frame (gridlines, marks, axes, legend, title, notes). Known gap (fixed after the kinds land): `frame.describe`'s channel sentence uses `axis_title(col)` defaults.
- Controller step after 5.1–5.6 land, before 6.1 (sequential, shared modules): (a) make `frame.describe`'s channel sentence use each axis's drawn title form (clock_date/hours), regenerating affected goldens; (b) add one cross-kind parametrized test pinning describe range text for every SVG kind × unit family (DURATION kind, NUMBER+`s`, PACE, PERCENT, CLOCK, QUANTITY), so a kind that treats PACE/PERCENT/CLOCK as durations reds. Reviewers of 5.1 deferred their unit-family survivors (F1/F4/F6/F7) to this step by controller ruling.
- Controller step X (done): `frame.describe` channels accept `(name, Column | str)`; a str is the drawn axis title (clean_text'd). All six SVG kinds pass their drawn axis titles. `tests/render/charts/kit/test_describe_ranges.py` pins describe range text per kind × unit family; PACE/PERCENT/CLOCK mutations of each kind's duration check red (CLOCK unreachable on bar/hbar/histogram value axes). No golden changed.
