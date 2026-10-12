# Implementation Plan

## Upstream Prerequisites

- **Base.** Planned at `c3687a8`. `dashboards` is implemented on
  `impl/dashboards` and may land first: it takes `CONTRACT_VERSION` 9 → 10,
  appends `dashboards/` and `dashboards/assets/` to `layout.OWNED_PATHS`,
  `dashboards/` to `layout.DECLARED_DIRS`, reshapes
  `declaration._OWNER_BLOCK` to take an `owner` argument, and adds a
  `dashboards.AGENTS.md` golden. Every version constant in this plan is
  **main + 1 at landing**, re-derived in 6.2 after the final rebase; every
  list it touches is append-only and keeps both sides on rebase.
- **chart-kit and chart-catalog are on `main`.** `fitdocs.units.UNITS` is the
  one unit table; this plan appends two rows (1.1) and adds no second unit
  list.
- **No named-parameter index query is needed.** The wellness producer is a
  corpus producer returning Python rows; it uses neither
  `IndexConnection.execute` nor `execute_named`.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Amendments). Each record is appended to the named spec's `requirements.md`
  as `## Amendment N (<date>): <title>, landed by wellness-store` by the task
  that makes the change, taking the next free number at that moment:
  chart-kit (1.1, the two units), wiki-contract (1.5), fit-ingest (1.6),
  inbox (2.7 and 4.2), analytics-index and analytics-derived (4.4).

**Hard rules for every task**

- **Absent is `None`.** No wellness code substitutes zero, an empty string or
  a default for an absent value; an absent value is no series line.
- **No clock, no machine timezone, no network in `fitdocs.wellness`.** No
  `date.today`, `datetime.now`, `time.*`, `astimezone()` without an explicit
  offset, `urllib`, `socket`, `http`. The boundary guard (1.4) enforces it.
- **Imports follow the design's one-way order** (design § Allowed
  Dependencies): `model`, `probe` → `spec` → `formats/*` → `registry` →
  `settings`, `merge`, `archive` → `series` → `intake`, `engine` →
  `inspect`. `fitdocs.wellness` imports only the standard library,
  `tomli_w`, `fitdocs.layout`, `fitdocs.settings` and `fitdocs.units`.
  `fitdocs.inbox` and `fitdocs.connectors` never import `fitdocs.wellness`.
- **Synthetic data only.** Fixtures are built by test builders from the key
  sets recorded in research.md, with invented values; no maintainer value,
  file name, user id or profile number appears in the repository.
- **Writes only through `wellness.archive` (archive) and `wellness.engine`
  (series)**, atomically, never following a symlink. No wellness test writes
  outside its `tmp_path`.
- **Linux-CI portable.** Temp directories from `tmp_path` /
  `tmp_path_factory`; never `tempfile.gettempdir()`; child processes get
  `{**os.environ, …}`; permission-based unreadability tests skip when running
  as root.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination): each named mutation is applied, observed red,
  reverted by restoring a `cp` taken before the mutation, observed green, and
  recorded in Implementation Notes. A listed mutation that cannot be made red
  is reported UNPINNED, never hidden. Before submitting, run the prose-claim
  grep over changed test files and re-run or delete every surviving claim.
- **Fixtures discriminate.** Values pairwise distinct where a mapping is
  asserted; revision order and value order disagree; the interesting record
  is not first; dates not pre-sorted; an asserted end state shown false
  beforehand; "nothing written" asserted on bytes *and* `st_mtime_ns`.
- **Parallel streams.** `(P)` tasks run in separate worktrees and mutate only
  files inside their `_Boundary_`. `tests/wellness/_helpers.py` and
  `tests/wellness/conftest.py` are created by 1.2 (1.3 appends the registry
  helpers) and are frozen afterwards: a `(P)` task that needs another helper
  defines it locally in its own test module; it never edits the shared
  files, `tests/wellness/test_boundary.py`, or another stream's module.
  `(P)` tasks add only the modules 1.4's rank table names; a needed extra
  module is a stop-and-report. The
  full suite runs at each group's integration point (3.1, 4.1) and in 6.2.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in
  the same worktree** (`tests/test_bytecode_hygiene.py`).
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`.
- **Types and lint.** Each task runs `uv run mypy`, `uv run ruff check` and
  `uv run ruff format --check`.
- **Stop and report** on any need for: a runtime dependency; a change to
  `fit-archive/`, `archive_path`, `source_ref` or `select_candidates`'
  behavior; an edit to chart-kit, dashboards or connectors code; a second
  unit list; a write outside `wellness/`, `wellness-archive/`, the quarantine
  record and the processed directory from a wellness path.

## Shared source files

Each file below has more than one writer; its writers are sequential.

- `src/fitdocs/wellness/series.py`: 2.4 creates the codec and reader; 3.2
  adds `inputs_digest`.
- `src/fitdocs/wellness/registry.py`: 1.3 creates it with empty tuples; 3.1
  appends the shipped sources and formats.
- `tests/wellness/_helpers.py`, `tests/wellness/conftest.py`: 1.2 creates
  them (data root, counting opener); 1.3 appends the registry helpers;
  frozen afterwards.
- `tests/wellness/test_boundary.py`: 1.4 creates it; 3.4 adds the literal
  module-list pin.
- `src/fitdocs/skills/fitdocs-workouts/SKILL.md` and
  `tests/test_agent_skill.py`: 4.2 (the four channel rows, the channel
  literal and its count, `_CHANNEL_EXCLUSIONS`), then 5.2 (the Do-cell
  wording pins and the `check` paragraph).
- `src/fitdocs/wellness/__init__.py`: 1.1 creates a docstring-only module;
  3.4 adds the re-exports.
- `src/fitdocs/sync.py`: 4.1 (guard), then 4.2 (drain step).
- `src/fitdocs/cli.py`: 4.5 only.
- `src/fitdocs/layout.py`, `declaration.py`, `contract.py`: 1.5 only.
- `docs/ownership-contract.md`: 1.5 (version, head paragraph, owned-path
  bullets, directory count), then 5.2 (the narrative section).
- `tests/test_confinement.py`: 1.5 (AGENTS.md sets of the history and plan
  negative halves), then 6.1 (the two wellness entry points).
- `pyproject.toml`: 1.1 (`tests/wellness` mypy entry), 4.4 (the
  `tests/index/derived/test_wellness_producer.py` mypy entry), 5.1
  (`[project.urls] Wellness`).
- `CHANGELOG.md`: 5.2 only.

## Cross-spec shared files (append-only, keep both sides on rebase)

`OWNED_PATHS` / `DECLARED_DIRS`, the declaration goldens' version line,
`CONTRACT_VERSION`, `SCHEMA_VERSION` and its digest map,
`CORPUS_PRODUCERS`, `WRITING_ENTRY_POINTS`, `UNITS` and its test table,
`[project.urls]`, `[tool.mypy].files`, `CHANGELOG.md` Unreleased,
`docs/index.md` rows, `.kiro/steering/structure.md`, the `fitdocs-workouts`
skill's channel table and `tests/test_agent_skill.py`'s channel literal, and
the drain-pass block of `cli.py` (`_run_drain_passes`: dashboards' design
adds its index-pass/dashboard-pass calls there; 4.5 adds the `[wellness]`
preflight and keeps every call dashboards placed).

## Test File Ownership

- `tests/test_units.py` pins; `tests/wellness/__init__.py`,
  `test_model.py`: **1.1**.
- `tests/wellness/_helpers.py`, `conftest.py` (created with the data root
  and counting opener), `test_probe.py`: **1.2**. The registry helpers in
  `_helpers.py`, `test_spec.py`, `test_registry.py` (validation and
  recognition rules over test-only formats): **1.3**. `test_boundary.py` and
  `src/fitdocs/wellness/formats/__init__.py`: **1.4** (3.4 adds the
  module-list pin).
- Goldens `wellness.AGENTS.md`, `wellness-archive.AGENTS.md`, the re-pins in
  `tests/test_layout.py`, `tests/test_declaration*.py`,
  `tests/test_ownership_contract.py`, `tests/identity/test_contract_docs.py`,
  `tests/index/test_contract_docs.py`, `tests/index/derived/test_preserved.py`,
  the AGENTS.md sets in `tests/test_confinement.py` and
  `tests/test_declaration_refresh.py`: **1.5**.
- `tests/ingest/test_file_id.py` additions and its `FileIdentity` equality
  re-pins; the regenerated ingest goldens `tests/golden/{run,ride,minimal,strength}.json`:
  **1.6**.
- `tests/wellness/builders_intervals.py`, `test_intervals.py`: **2.1**.
  `builders_garmin.py`, `test_garmin.py`: **2.2**. `test_merge.py`: **2.3**.
  `test_series.py`: **2.4** (3.2 adds the digest cases). `test_settings.py`:
  **2.5**. `test_archive.py`: **2.6**. `tests/test_inbox.py` additions and
  the folder pin in `tests/connectors/test_folder.py`: **2.7**.
- `tests/wellness/test_registered_formats.py`: **3.1**. `test_engine.py`:
  **3.2**. `test_intake.py`: **3.3**. `test_inspect.py`, `test_facade.py`, the
  module-list pin in `test_boundary.py`: **3.4**.
- Guard cases in `tests/test_sync.py` and `tests/test_drain.py`: **4.1**.
  `tests/wellness/test_drain_wellness.py`; in `tests/test_agent_skill.py`
  `_CHANNEL_EXCLUSIONS`, `_INBOX_CHANNELS_LITERAL` (four names, count 12);
  the four channel rows of the workouts skill: **4.2**.
  Wellness cases in `tests/test_audit.py` and `tests/test_cli_check.py`:
  **4.3**.
  `tests/index/derived/test_wellness_producer.py`, the pins in
  `tests/index/test_schema_version.py`,
  `tests/index/derived/test_registration.py`,
  `tests/index/derived/test_boundary.py`: **4.4**.
  `tests/wellness/test_cli_wellness.py`, `tests/test_cli_drain_report.py`
  re-pins: **4.5**.
- `tests/wellness/test_docs_wellness.py`, `tests/test_docs_guarantees.py`
  required links: **5.1**. The Do-cell wording pins for the four wellness
  rows in `tests/test_agent_skill.py`, `tests/test_changelog.py` if it pins
  sections: **5.2**. `tests/connectors/test_network_statements.py`
  structure.md phrase pin: **5.3**.
- `tests/wellness/test_e2e.py`, `test_determinism.py`, the wellness entry
  points of `tests/test_confinement.py`: **6.1**.

---

- [ ] 1. Foundation: vocabulary, declarations, owned locations, file type

- [ ] 1.1 Create the wellness package with its metric vocabulary, absent-value rule and day-boundary rule, and add the two units
  - **`fitdocs.units`**: append `ml_per_kg_min` ("millilitres per kilogram
    per minute", `mL/kg/min`, QUANTITY, 1) and `brpm` ("breaths per minute",
    `br/min`, QUANTITY, 1); update the design-table literal, the row count
    and the token-uniqueness count in `tests/test_units.py`, and confirm the
    `UNIT_SUFFIXES` projection pin still describes the pre-change rows plus
    the two appended (amend the pin append-only). Record chart-kit's
    amendment.
  - **Package**: `src/fitdocs/wellness/__init__.py` (docstring only for now)
    and `model.py` per design § Model: `Metric` (28 members, design table
    order), `MetricInfo` (unit token resolving through `unit_named`, inclusive
    range, description, derived `zero_is_absent`), `METRICS`, `accept_value`,
    `DaySnapshot`, `SeriesValue`, `ORIGIN_PATTERN`/`is_origin`,
    `wellness_day_of_sleep_end`.
  - **`pyproject.toml`**: append `tests/wellness` to `[tool.mypy].files`.
  - **Tests** (`tests/wellness/test_model.py`): `METRICS` covers every
    `Metric` exactly once and its rows equal a test-local literal of the
    design table (names, units, ranges); every unit token resolves; names end
    in their unit token; `accept_value` at each bound of three metrics with
    different ranges (inclusive both ends), zero for `resting_hr_bpm` (absent)
    vs `sleep_rem_s` (kept), NaN and ±inf absent, negative stress absent;
    `wellness_day_of_sleep_end` for ends at D−1 17:59 and D−1 18:00 in
    +09:00 and −08:00 offsets (four distinct expected dates), a naive
    datetime raising; `is_origin` accepts `garmin`, `oura`, `zepp-life` and
    rejects `Garmin`, `garmin_`, `-x`, ``.
  - **Mutations:** `<=` → `<` on the upper bound; drop the non-finite check;
    `hours=6` → `hours=5`; replace the offset arithmetic with
    `.astimezone()`; swap `hrv_sdnn_ms`'s and `hrv_rmssd_ms`'s unit or range
    rows (the literal pin reds).
  - **Observable:** `uv run pytest tests/test_units.py tests/wellness` green;
    `uv run mypy` covers `tests/wellness`.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.5_

- [ ] 1.2 Read candidates in bounded pieces: the probe, streamed hashing, and the shared test helpers
  - **`probe.py`** per design § Probe: `HEAD_BYTES`, `JSON_PROBE_LIMIT`,
    `CHUNK_BYTES`, `CandidateProbe` (stat, head, cached capped `json()`,
    `zip_members()`), `hash_file`.
  - **Shared helpers**: create `tests/wellness/_helpers.py` with a
    data-root factory and a counting file opener (counts every `read` and its
    requested size per opened path, and flags an unsized `read()`), and
    `tests/wellness/conftest.py` exposing the data-root fixture. 1.3 appends
    the registry helpers; the files are frozen after 1.3.
  - **Tests** (`test_probe.py`): `json()` returns `None` above the (patched)
    limit after reading at most `HEAD_BYTES` (counting opener), and for
    invalid JSON; `json()` is parsed once across two calls; `zip_members()`
    on a small zip and on a non-zip; `hash_file` equals `hashlib.sha256` of
    the bytes and reads only in `CHUNK_BYTES` pieces with no unsized read.
  - **Mutations:** read the whole file in `json()` regardless of size;
    `hash_file` with one unsized `read()`; drop the `json()` cache.
  - **Observable:** `uv run pytest tests/wellness/test_probe.py` green.
  - _Requirements: 3.1, 3.2_

- [ ] 1.3 Define the format declaration types, the registry rules and the test-only formats
  - **`spec.py`** per design § Registry: `SourceKind`, `SourceSpec`,
    `ArchiveForm`, `Supersession`, `ExtractContext`, `WellnessFormatError`,
    `FormatSpec`, `ParsedEntry`.
  - **`registry.py`** with `SOURCES = ()` and `FORMATS = ()` (3.1 fills
    them), `recognize`, `format_named`, `source_named`,
    `candidate_suffixes`, `default_source_order`, `validate_registry`.
    No function caches: each reads the tuples at call time, and nothing
    calls `validate_registry` at runtime (design § Registry), so a test that
    patches the tuples sees its own formats everywhere.
  - **Shared helpers** (append to `tests/wellness/_helpers.py`, which 1.2
    created; frozen after this task): a test-only ORIGINAL format and a
    test-only EXTRACT format with LATEST_ENTRY (a JSON-lines extract whose
    header carries an order key), each with its own test-only source;
    `use_formats(monkeypatch, formats, sources)`; `tree_snapshot(path)` →
    bytes and `st_mtime_ns` of every file; `assert_untouched(before, after)`.
    The test-only recognizers build on `CandidateProbe` (1.2).
  - **Tests** (`test_spec.py`, `test_registry.py`): `validate_registry`
    passes for the test formats and fails, naming the declaration, for each
    rule in design § Registry (one declaration per rule: bad id, duplicate
    id, unknown source, `.fit` suffix, uppercase suffix, ORIGINAL with an
    extractor, EXTRACT without one, LATEST_ENTRY without `entry_order`,
    `rules_version` 0, overlapping metrics within one source); `recognize`
    with zero, one and two claiming formats (the reason names both
    claimants), a raising recognizer counted as no claim, a suffix no format
    declares; `default_source_order` with sources whose id order disagrees
    with kind order; `candidate_suffixes` reflects a patched `FORMATS` on a
    second call after a first call with other formats (no cache).
  - **Mutations:** drop the `.fit` rule from `validate_registry`; return the
    first claimant instead of refusing two; sort `default_source_order` by id
    only; memoize `candidate_suffixes` (the no-cache test reds).
  - **Observable:** `uv run pytest tests/wellness` green.
  - _Requirements: 1.3, 1.4, 1.5, 10.2, 17.1, 17.3, 17.4_

- [ ] 1.4 Guard the wellness package's imports, clock and network
  - Create `src/fitdocs/wellness/formats/__init__.py` (docstring only), so the
    group-2 format streams add modules without an add/add conflict.
  - **Boundary guard** (`tests/wellness/test_boundary.py`, AST walk): a rank
    table naming every module of design § File Structure Plan (`model`,
    `probe`, `spec`, `formats.intervals`, `formats.garmin`, `registry`,
    `settings`, `merge`, `archive`, `series`, `intake`, `engine`, `inspect`,
    the package `__init__` and `formats.__init__`) with its rank; each
    existing module may import only the standard library, `tomli_w`,
    `fitdocs.layout`, `fitdocs.settings`, `fitdocs.units` and wellness
    modules of lower rank (the facade may import any); no clock call
    (`date.today`, `datetime.now`, `datetime.utcnow`, `time.*`), no
    argument-less `astimezone()`, no network module. A module present on disk
    but missing from the rank table fails. **Positive control**: the set of
    modules the walk visited equals the set a filesystem glob of
    `src/fitdocs/wellness/**/*.py` finds, and is non-empty (no literal module
    list here; 3.4 adds that pin once every module exists, so the group-2
    streams never edit this file).
  - Synthetic violators: a module importing `fitdocs.sync`, one calling
    `datetime.now()`, one importing `urllib.request`, one importing a
    higher-ranked wellness module — each caught.
  - **Mutations:** let the walk skip `formats/` (the visited set then lacks
    `formats.__init__`, which this task creates, and the glob control reds);
    drop the clock check; drop the rank comparison (the higher-rank violator
    passes and its test reds).
  - **Observable:** `uv run pytest tests/wellness/test_boundary.py` green and
    every synthetic violator caught.
  - _Requirements: 20.1, 20.2_

- [ ] 1.5 (P) Declare `wellness/` and `wellness-archive/`, their AGENTS.md and the next contract version (wiki-contract amendment)
  - **`layout.py`**: `WELLNESS_ARCHIVE_DIR`, `WELLNESS_DIR`,
    `WELLNESS_MANIFEST_NAME`; append `"wellness/"` and
    `"wellness-archive/"` to `OWNED_PATHS` and `DECLARED_DIRS` (after any
    entries main holds); pure helpers `wellness_archive_path`,
    `wellness_series_path` (four-digit year), `wellness_manifest_path`;
    docstrings name both locations.
  - **`declaration.py`**: the four fragments of design § OwnedLocations, each
    with a CLAIM ANCHOR comment naming the code that makes it true
    (`wellness.archive` commit protocol, `wellness.engine`, the manifest),
    and the two dispatch branches with headings "Wellness Archive" and
    "Wellness Series", using the owner block main has at landing.
  - **`contract.py`**: `CONTRACT_VERSION` = main + 1 with the history
    paragraph of design § OwnedLocations.
  - **`docs/ownership-contract.md`**: version line; the new "What changed at
    this version" paragraph; two Owned Paths bullets; the declared-directory
    count and list.
  - **Goldens**: create `tests/declaration_golden/wellness.AGENTS.md` and
    `wellness-archive.AGENTS.md`; regenerate every existing golden (version
    line) with the goldens module's regeneration entry point; extend the
    golden-name list and the outside-the-declared-set lookalikes
    (`wellness-old/`).
  - **Pins that move**: the `OWNED_PATHS`/`DECLARED_DIRS` exact tuples and
    lengths in `tests/test_layout.py`; the prefix test (no new nesting:
    `wellness/` is not a prefix of `wellness-archive/`); the hard-coded
    contract-version literals in `tests/index/test_contract_docs.py` and
    `tests/index/derived/test_preserved.py`; the head-paragraph phrases in
    `tests/identity/test_contract_docs.py`; the AGENTS.md sets in the history
    and plan negative halves of `tests/test_confinement.py` and in
    `tests/test_declaration_refresh.py`. Pins a grep cannot find surface in
    the full suite; fix them in this task.
  - **Tests**: the two new goldens; a `tests/test_declaration.py` case that
    the archive text says fitdocs never modifies the files and the series
    text says edits are overwritten; `wellness_archive_path` and
    `wellness_series_path` compose exact paths and never touch the
    filesystem.
  - **Mutations:** drop `"wellness-archive/"` from `OWNED_PATHS`; select
    `_IMMUTABILITY` (the FIT archive's fragment) for `wellness-archive/`;
    leave `CONTRACT_VERSION` at main's value.
  - **Observable:** full `uv run pytest` green; a sync in a scratch data
    root (an existing harness) creates both AGENTS.md files equal to their
    goldens; wiki-contract amendment recorded.
  - _Requirements: 2.1, 11.1, 11.7, 14.6, 19.1_
  - _Boundary: OwnedLocations_

- [ ] 1.6 (P) Read the FIT file type into the file identity (fit-ingest amendment)
  - `FileIdentity.file_type: str | None = None` as the last field;
    `extract_file_identity` maps `type` like `manufacturer` (profile name,
    else the number as text, else `None` for absent or wrong-typed);
    `is_activity_file(identity)` in `ingest/file_id.py`.
  - **Pins that move**: the fixture builder's `_file_id` writes
    `"type": "activity"` (`tests/fixtures/builder.py:169`), so every built
    file now reads `file_type="activity"`: the `FileIdentity(...)` equality
    pins in `tests/ingest/test_file_id.py` (~:185, ~:203, ~:256; cite by
    content) gain `file_type="activity"`; the ingest goldens serialize every
    dataclass field (`tests/golden/_serialize.py:98`), so
    `tests/golden/{run,ride,minimal,strength}.json` gain the key —
    regenerate them with `uv run python -m tests.golden.generate` and review
    the diff (only `file_type` lines may change).
  - **Tests** (`tests/ingest/test_file_id.py`, synthetic FIT bytes from the
    fixture builder; never the type name `"sleep"`, which the SDK cannot
    encode): `activity` → `"activity"`; `monitoring_b` → `"monitoring_b"`;
    an unknown type `49` → `"49"`; no `file_id` → `None`; a bool or float
    type → `None`; `is_activity_file` true for `None` and `"activity"`,
    false for `"monitoring_b"` and `"49"`; every existing `FileIdentity(...)`
    construction in tests still type-checks.
  - **Mutations:** read `manufacturer` into `file_type`; return `True` from
    `is_activity_file` for `"49"`; drop the number-as-text branch.
  - **Observable:** the full `uv run pytest` green, including
    `tests/test_golden.py` with the regenerated goldens; fit-ingest
    amendment recorded.
  - _Requirements: 4.1, 4.4_
  - _Boundary: FitIngestFileType_

- [ ] 2. Core: formats, merge, codec, settings, archive, inbox selector

- [ ] 2.1 (P) Parse intervals.icu wellness: the API list and the fitdocs delivery envelope
  - `formats/intervals.py` per design § IntervalsFormat: `SOURCE`, `FORMAT`,
    `DELIVERY_FORMAT`, `DELIVERY_VERSION`, `FIELD_METRICS`, recognizer,
    parser (17 mapped fields, `updated` normalization, envelope origins,
    strict type errors as `WellnessFormatError`). Not yet registered (3.1).
  - **Builders** (`tests/wellness/builders_intervals.py`): records carrying
    the fields research.md names (the 17 mapped fields, `id`, `updated` and
    the computed fields) plus invented unmapped keys, with synthetic values;
    the bare list; the envelope serialized by the canonical `json.dumps` of
    design § Seams 2.
  - **Tests**: recognition of the list and of the envelope; a list of
    objects without date `id` and a Garmin-shaped list not claimed; envelope
    with version 2 not claimed; each of the 17 fields lands on its metric
    with pairwise-distinct values; `ctl`, `atl`, `rampRate`, `ctlLoad`,
    `atlLoad`, `sportInfo`, `sleepScore`, `readiness` present with non-null
    values produce no value; `updated` with `+02:00` and with `Z` normalizes
    to the same UTC string; origins applied only to present values and
    rejected when malformed; `"restingHR": true` and a duplicate `id` raise;
    `restingHR: 0` absent; covers equal all 17 metrics on a record with one
    value.
  - **Mutations:** map `hrv` to `hrv_sdnn_ms`; drop the `updated`
    normalization; let a bool pass as a number; emit covers only for present
    values.
  - **Observable:** `uv run pytest tests/wellness/test_intervals.py` green.
  - _Requirements: 5.6, 6.2, 7.4, 8.3, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_
  - _Boundary: IntervalsFormat_

- [ ] 2.2 (P) Parse the four Garmin export kinds
  - `formats/garmin.py` per design § GarminFormats: `SOURCE` and the four
    `FormatSpec`s with recognizers (content signature, name pattern for an
    empty list) and parsers. Not yet registered (3.1).
  - **Builders** (`tests/wellness/builders_garmin.py`): UDS, sleep, MaxMet
    and bio files from the measured key sets (research.md) with invented
    values and invented, non-personal names (`UDSFile_2000-01-01_2000-04-10.json`,
    `2000-01-01_2000-04-10_1_sleepData.json`, …); a `HydrationLogFile`-shaped
    decoy.
  - **Tests**: each kind recognized by content and, empty, by name; an empty
    list with an unrelated name not claimed; the decoy not claimed;
    `currentDayRestingHeartRate` used and `restingHeartRate` ignored with
    different values; stress `-1`, `-2`, `0` absent and `37` kept; TOTAL
    aggregator chosen over AWAKE/ASLEEP with distinct values; steps `0`
    absent; body battery HIGHEST/LOWEST; sleep total = deep + light + REM
    (awake excluded) with distinct stage values, a no-stage night emitting
    no sleep values but its respiration; RUNNING → run metric, CYCLING →
    ride metric, WALKING and sport-less → nothing; MaxMet revisions
    normalized; weight grams → kg; a missing `calendarDate` raises; every
    value's origin `garmin`; the four formats' metrics are disjoint.
  - **Mutations:** read `restingHeartRate`; include awake in the total; map
    WALKING to the run metric; skip the ÷1000; accept an empty list without
    the name check.
  - **Observable:** `uv run pytest tests/wellness/test_garmin.py` green.
  - _Requirements: 5.6, 6.2, 6.3, 7.4, 8.4, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8_
  - _Boundary: GarminFormats_

- [ ] 2.3 (P) Merge parsed entries into series values
  - `merge.py` per design § Merge (supersession, revision resolution,
    absence by a later snapshot, conflict keep-rule, precedence, ordering);
    `Conflict`, `MergeResult`.
  - **Tests** (synthetic `ParsedEntry`s): later revision wins where the later
    value is smaller and the later entry ref sorts first; a later snapshot
    covering the metric without a value yields no value; two `None`-revision
    snapshots, one with a value, yield that value; equal values from two
    entries yield no conflict; two equal-revision distinct values conflict
    and keep the greater `(ref, ordinal)` with ref order and value order
    disagreeing; LATEST_ENTRY keeps only the greatest `order` (order and ref
    disagree) and lists the rest as superseded; precedence marks exactly one
    canonical per day and metric across three sources with pairwise-distinct
    values, skipping a top source without a value; every source's value
    kept; output order by `(day, metric name, source)` from shuffled input.
  - **Mutations:** `max` → `min` on revisions; drop the absence branch;
    choose canonical by source id; keep superseded entries.
  - **Observable:** `uv run pytest tests/wellness/test_merge.py` green.
  - _Requirements: 8.1, 8.2, 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 17.3_
  - _Boundary: Merge_

- [ ] 2.4 (P) Encode, decode and read the series files
  - `series.py` per design § Series without `inputs_digest` (3.2): header,
    `format_value`, `encode_year`, `decode_year`, manifest encode/decode
    (`generator`, `series_version`, newer-version detection), `WellnessSeries`
    with every method, `read_series`, `series_files`, `SeriesReadError`.
  - **Tests**: byte golden of a small synthetic year file; round trip;
    `52.0` → `52`, `48.6` → `48.6`, `1e20` handled; line order with metric
    names whose enum order differs from lexicographic; `\n` endings, no BOM;
    decode rejects a wrong header, an unknown metric, a bad date, a non-bool
    `canonical`, an extra column (each naming file and line); manifest round
    trip with dates; `read_series` with no manifest → empty, with a manifest
    listing a missing file → `SeriesReadError`, ignoring an unlisted year
    file; `canonical`/`value`/`by_source`/`sources`/`for_day`/
    `canonical_series` on a fixture with two sources and a canonical switch;
    `day_digest` stable across reads and different when one value changes.
  - **Mutations:** emit `\r\n`; sort by enum order; `format_value` always
    `repr`; `read_series` reads every `*.csv` instead of the listed files;
    `day_digest` hashing only values.
  - **Observable:** `uv run pytest tests/wellness/test_series.py` green.
  - _Requirements: 6.1, 11.2, 11.3, 11.4, 11.8_
  - _Boundary: Series_
  - _Depends: 1.5_

- [ ] 2.5 (P) Read the `[wellness]` settings
  - `settings.py` per design § Settings.
  - **Tests** (test-only sources via `use_formats`): absent table/keys →
    default; `precedence` partial list completed in default order; metric
    override wins for its metric only; unknown source, unknown metric,
    duplicate, non-list, non-string entry, non-table `metric_precedence` each
    raise naming `fitdocs.toml` and the key; unknown keys ignored;
    `effective_order` over three sources whose default order differs from
    the configured one.
  - **Mutations:** append configured sources after the default instead of
    before; ignore `metric_precedence`; accept a duplicate.
  - **Observable:** `uv run pytest tests/wellness/test_settings.py` green.
  - _Requirements: 10.2, 10.3, 10.4, 10.5_
  - _Boundary: Settings_

- [ ] 2.6 (P) Archive layout, listing and the write-once commit protocol
  - `archive.py` per design § Archive: `ArchiveEntry`, `Orphan`,
    `ArchiveListing`, `entry_ref`, `list_archive`, `commit_original`,
    `commit_extract`, `parse_entry` (snapshot invariants validated, ordinals
    assigned).
  - **Tests** (test-only formats): commit of an original creates exactly
    `wellness-archive/<fmt>/<sha><suffix>` with the candidate's bytes and no
    leftover temp file; invalid content → `Invalid`, no entry, no temp;
    a candidate rewritten mid-copy (patched read) → `Changed`; existing entry
    → `Exists` and its bytes and mtime untouched; extract commit names the
    entry by the original's sha, re-hashes after the extractor (an extractor
    that modifies the candidate → `Changed`), and parses the extract before
    committing; `Unreadable` for a `chmod 000` candidate; streaming asserted
    with the counting opener; listing: entries sorted, `AGENTS.md` and
    dot-names skipped, an unknown directory one orphan with its file count, a
    bad name, a wrong suffix and a symlink each an orphan, no file opened
    (counting opener); `parse_entry` rejects a snapshot whose values exceed
    its covers, whose value `accept_value` rejects, whose origin is invalid.
  - **Mutations:** commit before parsing; skip the post-extract re-hash;
    overwrite an existing entry; list a symlink as an entry.
  - **Observable:** `uv run pytest tests/wellness/test_archive.py` green.
  - _Requirements: 2.2, 2.3, 2.4, 2.8, 3.1, 3.3, 17.2_
  - _Boundary: Archive_
  - _Depends: 1.5_

- [ ] 2.7 (P) Select wellness candidates in the inbox without widening `.fit` selection (inbox amendment, part 1)
  - `select_wellness_candidates(inbox, settings, suffixes)` per design §
    InboxSelector; `select_candidates` and the new function share one
    private walk; correct the `DEFAULT_IGNORE_PATTERNS` docstring's
    reachability claim for the wellness suffixes.
  - **Tests** (`tests/test_inbox.py`): `.json` and `.JSON` selected for
    `{".json"}`, `.fit` never selected even when passed in `suffixes`,
    `.gpx` ignored, dot components, default patterns (`x.json.part` is not a
    `.json` candidate; `foo.tmp`), configured patterns (`*_hydration*.json`)
    all applied; sorted by inbox-relative path from an unsorted tree;
    `select_candidates` output unchanged on a mixed tree.
    `tests/connectors/test_folder.py`: a folder source holding a `.json` and
    a `.fit` lists only the `.fit`.
  - **Mutations:** drop the dot-component rule from the shared walk for the
    wellness path; let `select_candidates` accept `.json`; skip configured
    patterns.
  - **Observable:** `uv run pytest tests/test_inbox.py tests/connectors/test_folder.py`
    green; inbox amendment part 1 recorded.
  - _Requirements: 1.1, 1.6, 1.8_
  - _Boundary: InboxSelector_

- [ ] 3. Wellness integration: registration, rebuild, intake, inspection

- [ ] 3.1 Register the shipped sources and formats and prove recognition over the real registry
  - Append `intervals.SOURCE`, `garmin.SOURCE` to `SOURCES` and the five
    formats to `FORMATS`; `validate_registry()` passes on the real
    registry; `candidate_suffixes() == {".json"}`;
    `default_source_order() == ("garmin-export", "intervals-icu")`.
  - **Tests** (`test_registered_formats.py`): a matrix over every builder
    file (intervals list, envelope, four Garmin kinds, each empty Garmin
    file) — recognized by exactly its format; decoys (hydration file,
    `{"a": 1}`, a non-JSON `.json`, an oversize JSON with the limit patched)
    unrecognized with a reason.
  - **Mutations:** register `garmin.UDS_FORMAT` twice (validation reds);
    loosen the UDS signature to `calendarDate` (the hydration decoy is
    claimed and the matrix reds).
  - **Observable:** full `uv run pytest` green (group-2 integration point).
  - _Depends: 2.1, 2.2_
  - _Requirements: 1.3, 1.4, 1.5, 15.1, 16.1, 17.1_

- [ ] 3.2 Assess and rebuild the series
  - `series.inputs_digest` and `engine.py` per design § Engine
    (`SeriesStatus`, `SeriesNote`, `SeriesReport`, `SeriesAssessment`,
    `assess_series`, `rebuild_series`), writing year files and the manifest
    atomically (temp + `os.replace`, manifest last), skipping unchanged
    bytes, removing emptied years, recording entries (contributed or
    superseded), effective precedence and conflicts.
  - **Tests** (`test_engine.py`, real registry plus test formats where an
    extract is needed): first build from Garmin and intervals entries writes
    the expected years and manifest; second build `UNCHANGED` with bytes and
    mtimes untouched; `force=True` on unchanged inputs writes nothing;
    stale after an entry is added, after `[wellness]` changes, after a
    format's `rules_version` is patched, after a year file is edited, after a
    year file is deleted; `BLOCKED` for a symlink, a directory and a
    header-less file at a year path and for a manifest without `generator`
    or with a newer `series_version`, every series byte untouched;
    `DEFERRED` for a `chmod 000` entry and for an unreadable year file;
    `FAILED` for an entry made invalid after archiving; zero entries → no
    year files and no manifest; an emptied year removed; report counts and
    `days` for added, changed, removed and canonical-only changes; a
    LATEST_ENTRY pair recorded as one contributed and one superseded.
  - **Mutations:** write the manifest first; skip the occupancy check for
    the manifest; leave `rules_version` out of the digest; rewrite unchanged
    files; drop `days` for canonical-only changes.
  - **Observable:** `uv run pytest tests/wellness/test_engine.py
    tests/wellness/test_series.py` green.
  - _Depends: 2.3, 2.4, 2.5, 2.6, 3.1_
  - _Requirements: 10.6, 11.1, 11.5, 11.6, 12.1, 12.4, 12.5, 12.6, 12.7, 17.4_

- [ ] 3.3 (P) Decide a wellness candidate's intake outcome
  - `intake.py` per design § Intake (`identify`, `archive_identified` and the
    outcome types).
  - **Tests**: unrecognized and ambiguous reasons; `OSError` in the probe and
    in hashing → deferred; an already-archived sha → `AlreadyArchived` with
    no copy attempted (counting opener); a fresh file → `Archived`; invalid
    content → `Failed` naming the parse error; a file changed during the
    commit → deferred with the "changed during the run" reason; the envelope
    with version 2 → unrecognized "written by a newer fitdocs".
  - **Mutations:** skip the existence check; map `Changed` to `Failed`;
    map a probe `OSError` to unrecognized.
  - **Observable:** `uv run pytest tests/wellness/test_intake.py` green.
  - _Depends: 3.1_
  - _Requirements: 1.4, 2.5, 2.6, 2.8, 15.3_
  - _Boundary: Intake_

- [ ] 3.4 Inspect the wellness tree read-only and publish the facade
  - `inspect.py` per design § Inspect; `__init__.py` re-exports exactly the
    facade list of design § Facade.
  - **Tests** (`test_inspect.py`, `test_facade.py`): one problem per orphan;
    `series_stale` with every reason (entries added, settings changed, file
    edited, file missing, no series with entries present, unreadable file,
    invalid settings); `series_occupied` per occupied path; one `conflict`
    per manifest conflict naming day, metric, source, entries and kept value;
    a clean tree → no problem; `inspect_wellness` opens no archive entry
    (`chmod 000` entries, counting opener) and leaves the tree byte- and
    mtime-identical, creating no directory; the facade's `__all__` equals a
    literal and every name imports. Add to `tests/wellness/test_boundary.py`
    the literal pin that the visited module set equals every module of the
    rank table (now that all exist).
  - **Mutations:** open entries to judge freshness; drop the settings-error
    branch; report conflicts from the archive instead of the manifest.
  - **Observable:** `uv run pytest tests/wellness` green.
  - _Depends: 3.2_
  - _Requirements: 11.8, 14.1, 14.2, 14.3, 14.4, 14.5_

- [ ] 4. Integration with the drain, check, the index and the CLI

- [ ] 4.1 Keep non-activity FIT files off workout pages
  - The guard in `_run_planned`'s preparation per design §
    NonActivityGuard; the `SyncReport` docstring's `skipped` causes and
    warning causes (the ninth) updated.
  - **Warning text** (design § NonActivityGuard): "not an activity file: its
    FIT header declares the file type '<type>'; fitdocs writes workout pages
    only for activity files, so it wrote no page from it and left the file
    where it is" — true for a source-directory, inbox or archived file.
  - **Staging a pre-existing page**: inside `monkeypatch.context()`, patch
    the name where it is looked up (`fitdocs.sync.is_activity_file`, sync
    imports the name) to return `True`, sync a monitoring file so a page is
    written and the file archived, and leave the context so the guard is live
    again. Positive controls after staging: the page exists and its
    `sources` list the monitoring file's sha.
  - **Tests** (`tests/test_sync.py`, `tests/test_drain.py`, synthetic
    monitoring and type-49 FIT bytes):
    - `sync SOURCE` with an activity and a monitoring file → one page;
      `skipped` holds the monitoring file; exactly one warning, naming it and
      `monitoring_b`; no archive entry for its sha.
    - The drain under the move disposition leaves it in the inbox, records no
      quarantine entry, and exits successfully; an untyped FIT still renders.
    - `regen` over the staged page **and**, in the same run, an archived
      monitoring file (type `49`) that no page lists: the staged page's ref
      is in `report.written`, not in `skipped`, and has no "not an activity
      file" warning; the unlisted file is in `skipped` with the warning (this
      proves the patch was undone and the guard is live); the archive is
      byte-identical.
    - `sync SOURCE --force` over the staged page's monitoring file: the file
      is in `skipped` with the warning, and the staged page's bytes and
      `st_mtime_ns` are unchanged (Req 4.2's `--force` case).
  - **Mutations:** archive the skipped file (the no-archive assertion reds);
    count it as a failure (the exit/skipped assertions red); apply the guard
    in `_process_isolated` too (the staged page leaves `report.written` and
    the regen assertion reds); drop the guard (the unlisted file renders and
    the `skipped` assertion reds).
  - **Observable:** full `uv run pytest` green (group-3 integration point).
  - _Depends: 1.6_
  - _Requirements: 4.2, 4.3, 4.5, 4.6_

- [ ] 4.2 Compose wellness intake and the rebuild into the drain (inbox amendment, part 2)
  - `drain(...)` per design § DrainWellnessStep: new keyword parameters, one
    settle over both candidate sets, the wellness loop (identify, quarantine
    check, archive, quarantine record updates, disposition), then
    `rebuild_series(force=False)`, then the unchanged FIT loop; the five new
    `DrainReport` fields with defaults; `sync.sync` untouched apart from 4.1.
  - **Skill binding moves with the dataclass** (it is introspected from
    `DrainReport`): in `tests/test_agent_skill.py` add `wellness_series` to
    `_CHANNEL_EXCLUSIONS`, add `unrecognized`, `wellness_archived`,
    `wellness_skipped` and `wellness_failures` to `_INBOX_CHANNELS_LITERAL`
    and move its count from 8 to 12; add the four rows to the `Reading the
    report` channel table of `src/fitdocs/skills/fitdocs-workouts/SKILL.md`
    with non-empty Channel, Meaning and Do cells (5.2 refines the Do
    wording and pins it).
  - **Tests** (`tests/wellness/test_drain_wellness.py`): a mixed inbox
    (activity FIT, intervals list, envelope, four Garmin kinds, an unknown
    `.json`, a `.gpx`, a monitoring FIT, an invalid Garmin UDS) → each file
    in exactly its channel (asserted as complete sets), the injected `sleep`
    called exactly once, the series rebuilt before the FIT page is planned
    (an `on_rendered` hook reads the series and sees the day's values);
    second drain → nothing archived, `wellness_skipped` for the leave
    disposition, `wellness_series.status == UNCHANGED`, every series byte
    and mtime untouched; the invalid file quarantined and reported
    `quarantined` on the next drain, then archived with `retry_quarantined`
    after it is fixed in place (entry removed from the record); move
    disposition moves archived and already-archived wellness files and
    leaves unrecognized, failed and deferred ones; an unreadable candidate
    deferred; `sync SOURCE` with a `.json` in the source tree touches no
    wellness path.
  - **Mutations:** settle the wellness candidates separately; rebuild after
    the FIT loop; move a failed candidate; skip the quarantine check.
  - **Observable:** the full `uv run pytest` green, including
    `tests/test_agent_skill.py`; inbox amendment part 2 recorded.
  - _Depends: 2.7, 3.2, 3.3, 4.1_
  - _Requirements: 1.2, 1.7, 1.9, 2.6, 2.7, 2.9, 2.10, 12.2, 12.8, 13.6_

- [ ] 4.3 (P) Report wellness findings in `fitdocs check`
  - Four `FindingKind` members, the mapping of `inspect_wellness` problems
    with the remedies of design § AuditWellness, and the module docstring's
    read list.
  - **Tests** (`tests/test_audit.py`, `tests/test_cli_check.py`): each
    finding with its subject, detail and remedy; `fitdocs check` exits 1 on
    a wellness finding and 0 on a clean wellness tree; the declaration
    findings for both directories when their AGENTS.md is missing; sorted
    with the other findings.
  - **Mutations:** map `series_occupied` to the stale remedy; drop the
    conflict mapping.
  - **Observable:** `uv run pytest tests/test_audit.py tests/test_cli_check.py`
    green.
  - _Depends: 3.4_
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.6_
  - _Boundary: AuditWellness_

- [ ] 4.4 (P) Add the `wellness_daily` table to the analytics index (analytics-index and analytics-derived amendments)
  - `index/derived/wellness.py` per design § IndexProducer; append to
    `CORPUS_PRODUCERS`; `SCHEMA_VERSION` = main + 1 with the new digest in
    `tests/index/test_schema_version.py`; append `fitdocs.wellness` to the
    allow-lists of `tests/index/derived/test_boundary.py`; update
    `tests/index/derived/test_registration.py` (producer tuple, table count
    + 1); regenerate `docs/analytics.md` with
    `uv run python -m tests.query.test_docs_analytics`; append the producer
    test module to `[tool.mypy].files`.
  - **Tests** (`tests/index/derived/test_wellness_producer.py`): rows equal
    `read_series` values with the unit column from `METRICS` (a unitless
    metric → NULL); fingerprint changes when a year file or the manifest
    changes and not otherwise; with a series staged by `rebuild_series`
    (3.2) over archive entries written by `commit_original` (no drain), an
    index build through `fitdocs index` shows the rows through `fitdocs
    query`; after a second staged rebuild that changes one value, the refresh
    shows the new value; an unreadable series keeps the previous rows and
    reports the producer error without failing the command.
  - **Mutations:** fingerprint only the manifest; take the unit from the
    metric name suffix; drop the producer from the registry.
  - **Observable:** `uv run pytest tests/index tests/query` green;
    `docs/analytics.md` lists `wellness_daily`; amendments recorded.
  - _Depends: 3.2, 3.4_
  - _Requirements: 17.5, 18.1, 18.2, 18.3, 18.4, 18.5_
  - _Boundary: IndexProducer_

- [ ] 4.5 Wire the CLI: settings preflight, the regen rebuild, report rows, exit status and progress
  - `cli.py` per design § CliWellness (the drain-pass block is a
    keep-both-sides region with dashboards: keep every call it places after
    the index pass): `_wellness_settings` in
    `_run_drain_passes` and `regen_command`; `rebuild_series(force=True)`
    before `regen`; four unconditional drain rows and their detail
    listings; the series summary for every status but `UNCHANGED`; the exit
    rule; the stderr progress printer passed as `wellness_progress`.
  - **Tests** (`tests/wellness/test_cli_wellness.py`,
    `tests/test_cli_drain_report.py` re-pinned to twelve rows): a malformed
    `[wellness]` exits 2 with nothing written (drain and regen); the twelve
    rows render when empty; a rebuilt series prints written files and counts;
    deferred, blocked and failed summaries name their paths; nothing printed
    for `UNCHANGED`; exit 1 for a wellness failure and a failed rebuild, 0
    for unrecognized, deferred, quarantined, blocked and conflicts; `regen`
    rebuilds a stale series before regenerating pages; the progress printer
    writes nothing when stderr is not a terminal and a percentage line when
    it is (test-only EXTRACT format calling `progress`).
  - **Mutations:** print the summary for `UNCHANGED`; omit
    `wellness_failures` from the exit rule; call `rebuild_series` after
    `regen`.
  - **Observable:** `uv run pytest tests/wellness tests/test_cli*.py` green.
  - _Depends: 4.2, 3.2_
  - _Requirements: 3.4, 10.5, 12.3, 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 5. Documentation, skill, records

- [ ] 5.1 Write the wellness guide and link it
  - `docs/wellness.md` per design § Docs, with the metric table, the
    per-source definitions (Garmin resting HR as the day's lowest 30-minute
    average, Apple's sedentary estimate, intervals.icu passing on its
    upstream's definition), the one statement of the day-boundary rule, the
    delivery envelope for wellness-pull, and which Garmin files to drop;
    `docs/index.md` row; `[project.urls] Wellness`.
  - **Tests** (`tests/wellness/test_docs_wellness.py`): the metric table
    equals `METRICS` (names, units, ranges); the envelope constants in the
    doc equal `DELIVERY_FORMAT` and `DELIVERY_VERSION`; the day-boundary
    statement appears exactly once across `docs/`; every documented
    `fitdocs` command and option is registered; the page is in
    `docs/index.md` before Contributing and in `[project.urls]`; required
    links in `tests/test_docs_guarantees.py`.
  - **Mutations:** rename a metric in `METRICS` (doc table pin reds); bump
    `DELIVERY_VERSION` (doc pin reds).
  - **Observable:** `uv run pytest tests/wellness/test_docs_wellness.py
    tests/test_docs_guarantees.py` green.
  - _Requirements: 5.5, 7.4, 7.6, 15.7, 19.2_

- [ ] 5.2 Update the inbox, configuration, plugin and ownership-contract docs, the workouts skill and the CHANGELOG
  - `docs/inbox.md` (wellness candidates, unrecognized channel, `[inbox]
    ignore` for a file, the non-activity guard); `docs/configuration.md`
    `### [wellness]`; `docs/plugins.md` (`FileIdentity.file_type`,
    additive); `docs/ownership-contract.md` "Wellness Archive and Series"
    section; `src/fitdocs/skills/fitdocs-workouts/SKILL.md`: the final Do
    wording of the four wellness rows 4.2 added and the `check` paragraph; `CHANGELOG.md`
    Unreleased entries (Added: wellness store, formats, `wellness_daily`,
    `[wellness]`, findings; Changed: inbox, non-activity guard, drain rows,
    contract and schema versions with the actions; plugin API additive).
  - **Tests**: in `tests/test_agent_skill.py`, row-scoped pins (via the
    existing `_channel_rows_by_field`) that the Do cells for `unrecognized`
    and `wellness_failures` say to tell the user and never suggest deleting
    the file; the configuration doc's `[wellness]` keys equal the settings
    reader's keys; the ownership-contract conformance tests pass.
  - **Mutations:** move the never-delete sentence from the `unrecognized`
    row to another row (the row-scoped pin reds); misspell a `[wellness]` key
    in the doc.
  - **Observable:** `uv run pytest tests/test_agent_skill.py
    tests/test_ownership_contract.py tests/test_changelog.py` green.
  - _Requirements: 19.1, 19.3, 19.4, 19.5, 19.6_

- [ ] 5.3 Record the package's place in steering
  - `.kiro/steering/structure.md`: a `wellness` bullet (imports only the
    standard library, `tomli_w`, `layout`, `settings`, `units`; imported by
    `sync`, `audit`, `cli` and `index.derived`; the reader is how every
    consumer reads wellness) and `index.derived` also imports `wellness`;
    `.kiro/steering/tech.md` pipeline line for wellness. Re-pin the
    structure.md phrase in `tests/connectors/test_network_statements.py` if
    the `index` bullet's pinned phrase moved.
  - **Observable:** a grep of `.kiro/steering/` and `CLAUDE.md` finds no
    statement contradicting the new package rule; the network-statements
    test is green.
  - _Requirements: 20.1, 20.2_

- [ ] 6. Validation

- [ ] 6.1 End-to-end, determinism, offline and confinement
  - **E2E** (`tests/wellness/test_e2e.py`, CLI through `CliRunner` with
    isolated `HOME`, `FITDOCS_INDEX_DIR`, `XDG_CACHE_HOME`): stage a mixed
    inbox; `fitdocs sync --no-prompt` exits 0 with the expected rows;
    `fitdocs check` exits 0; `fitdocs regen` reports no series change;
    `fitdocs query` returns `wellness_daily` rows; an invalid file exits 1
    then 0 on the next drain with it quarantined; a monitoring FIT produces
    no page and stays in the inbox.
  - **Determinism** (`test_determinism.py`): the same archive built in two
    data roots under `TZ=Pacific/Auckland` and `TZ=America/Los_Angeles`
    (child processes) gives byte-identical `wellness/` trees; a hash-seed
    change does not move bytes.
  - **Offline**: the drain and regen with `socket.socket` patched to raise
    complete.
  - **Confinement**: `drain-wellness` and `regen-wellness` entry points in
    `WRITING_ENTRY_POINTS` with non-vacuous checks (an archive entry and a
    year file exist).
  - **Mutations:** consult the machine timezone in the Garmin sleep date
    (determinism reds); write the manifest with a run timestamp
    (determinism reds).
  - **Observable:** `uv run pytest tests/wellness tests/test_confinement.py`
    green.
  - _Requirements: 4.2, 4.3, 12.2, 13.5, 13.6, 18.2, 20.1, 20.3, 20.4, 20.5_

- [ ] 6.2 Rebase, re-derive the version constants and validate the whole
  - Rebase onto `main`; re-derive `CONTRACT_VERSION` and `SCHEMA_VERSION` as
    main + 1 (update the history paragraph, the contract doc, the goldens,
    the schema digest map and every literal pin); keep both sides of every
    append-only list and of the `cli.py` drain-pass block; re-run `uv run pytest && uv run ruff check . && uv run
    ruff format --check . && uv run mypy`; check branch CI with
    `gh run list --branch`; `/kiro-spec-status wellness-store` clean.
  - **Observable:** the full suite, lint and types green after the final
    rebase; the version constants equal main + 1; the merge and the
    follow-ups are in the shared log and the queue.
  - _Requirements: 19.1, 18.4_

- [ ]* 6.3 Maintainer-run smoke on the maintainer's own exports (no data enters the repository)
  - In a scratch data root outside the repository, drop the Garmin export's
    `UDSFile_*`, `*_sleepData`, `MetricsMaxMetData_*` and `*_userBioMetrics`
    files and one intervals.icu delivery; run the drain; record in
    Implementation Notes only counts: files recognized per format,
    unrecognized files, days per metric per source (expected near
    research.md's measured counts: resting HR on about 937 Garmin days),
    conflicts, series size per year.
  - **Observable:** counts recorded; no value, file name or id written to
    the repository.
  - _Requirements: 16.1, 16.2, 15.1_

## Implementation Notes
