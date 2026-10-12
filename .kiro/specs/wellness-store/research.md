# Research & Design Decisions

## Summary
- **Feature**: `wellness-store`
- **Discovery Scope**: Complex extension of an existing system (new package,
  inbox/drain amendment, ownership-contract amendment, fit-ingest amendment,
  analytics-index amendment). Discovery was codebase-first: every
  current-state claim below was read in this worktree at base `c3687a8`.
  No web research was run (this batch run is network-free); external facts
  are taken from the Phase 12 discovery record in
  `.kiro/steering/roadmap.md` and the sibling briefs, and the maintainer's
  Garmin export was probed for **shapes and aggregate counts only** with
  stdlib scripts in the session scratchpad (no value, file name or user id
  was printed or written into the repository).
- **Key Findings**:
  1. The inbox, the archive and the drain are FIT-shaped in many places, but
     a **separate `wellness-archive/`** plus a **separate wellness selector**
     leaves almost every FIT pin the brief listed untouched: `fit-archive/`,
     `archive_path`, `source_ref`, the `*.fit` orphan and audit globs and
     `select_candidates` keep their meaning byte for byte.
  2. Garmin's `restingHeartRate` in the export's daily summaries is a
     **seven-day rolling mean**, not the day's resting HR. The day's value is
     `currentDayRestingHeartRate`. The brief's and roadmap's "`restingHeartRate`
     on 937 days" names the wrong field for a daily series.
  3. Garmin's sleep `calendarDate` is the **wake date** (it equals the local
     end date of the night), contradicting the `workout-wellness` brief's
     "Garmin `calendarDate` against sleep start".
  4. A non-activity FIT parses without error and becomes
     `workouts/undated-workout-<uid>.md` plus an archived source — confirmed by
     a scratch probe, not covered by any test.
  5. The analytics index isolates a failing corpus producer and keeps its old
     rows (`index/refresh.py:442-471`), so an unreadable series degrades the
     `wellness_daily` table instead of failing a command.

## Research Log

### The inbox drain today
- **Context**: Requirement 1-3 amend the drain; the brief listed many pins.
- **Sources Consulted**: `src/fitdocs/inbox.py`, `src/fitdocs/sync.py`,
  `src/fitdocs/cli.py`, `src/fitdocs/connectors/folder.py`,
  `tests/test_inbox.py`, `tests/test_cli_drain_report.py`,
  `tests/test_agent_skill.py`.
- **Findings**:
  - `select_candidates` admits only regular files whose suffix lowercases to
    `.fit` (`inbox.py:563-597`, the predicate at `:587`). The folder connector
    reuses it with `DEFAULT_INBOX_SETTINGS` (`connectors/folder.py:161-163`),
    so widening it would silently widen the connector.
  - `settle` waits once for a whole batch (`inbox.py:667-721`).
  - `drain` reads each stable candidate whole (`sync.py:890`), hashes it,
    partitions it against the quarantine record, then plans the admitted FIT
    files (`sync.py:739-1033`). Disposition moves a candidate only when its
    sha is present in `fit-archive/` and it did not fail this drain
    (`sync.py:988-998`).
  - **The default disposition is leave-in-place** (`inbox.py:198-203`; inbox
    Req 6.1). A handled `.fit` file is *not* removed from the inbox by
    default; it is skipped on the next drain because its bytes are archived.
    Removal happens only under `disposition = "move"` or, for a connector's
    own delivery, through the connector's sweep (`connectors/delivery.py:233-302`).
    The brief's "archived and removed from the inbox, exactly as a `.fit` is"
    is corrected in the requirements to "the configured disposition applies
    exactly as for a `.fit` file" (Req 2.9, 2.10).
  - `DrainReport` (`sync.py:674-737`) has `inbox`, `sync`, `deferred`,
    `quarantined`, `moved`, `move_failures`. The CLI prints eight rows
    unconditionally (`cli.py:2258-2344`); `tests/test_cli_drain_report.py:143`
    and `:230` pin "eight". The packaged skill's channel table is bound to the
    dataclass fields by introspection (`tests/test_agent_skill.py:110-133`,
    `:226-236`, pinned at 8).
  - Under the leave default, an unrecognized file is reported on every drain
    (it never leaves). Mitigation chosen: only suffixes a registered format
    reads are candidates at all; the existing `[inbox] ignore` patterns
    silence a specific file.
- **Implications**: a new `select_wellness_candidates` beside an unchanged
  `select_candidates`; one shared `settle` call; flat new `DrainReport` fields
  with defaults (`unrecognized`, `wellness_archived`, `wellness_skipped`,
  `wellness_failures`, `wellness_series`) so existing constructions keep
  working and the skill introspection excludes only `wellness_series`.

### The archive and the owned locations
- **Sources Consulted**: `src/fitdocs/layout.py`, `src/fitdocs/declaration.py`,
  `src/fitdocs/contract.py`, `docs/ownership-contract.md`,
  `tests/test_layout.py`, `tests/test_ownership_contract.py`,
  `tests/declaration_golden/`, the `impl/dashboards` branch diff.
- **Findings**:
  - `OWNED_PATHS` (`layout.py:133-142`) and `DECLARED_DIRS`
    (`layout.py:161-166`) are exact-tuple pinned (`tests/test_layout.py:649`,
    `:863`, `:885`). `fit-archive/` is a declared directory, so a sync places
    `fit-archive/AGENTS.md` even before any file is archived.
  - `declaration_text` dispatches per directory over a fragment table with no
    fall-through (`declaration.py:444-485`); every emitted text is a byte
    golden under `tests/declaration_golden/` and carries the contract version.
  - `CONTRACT_VERSION` is `"9"` on main (`contract.py:328`), with a version
    history string the docs tests read (`tests/identity/test_contract_docs.py:137-198`).
    Literal pins of `"9"`: `tests/index/test_contract_docs.py:140`,
    `tests/index/derived/test_preserved.py:246`.
  - On `impl/dashboards` (not main): `CONTRACT_VERSION` `"10"`,
    `DASHBOARDS_DIR` appended to both tuples, and `_OWNER_BLOCK` takes an
    `owner` argument instead of `generator`. The wellness lander re-derives
    main + 1 and keeps both sides of every append.
  - History refuses a foreign occupant by the `GENERATED_PREFIX` line marker
    (`history/engine.py:40-47`); a CSV cannot carry an HTML comment.
- **Implications**: `wellness-archive/` and `wellness/` appended to both
  tuples; two new goldens; the series uses its exact header line as its
  provenance marker and the manifest a `generator = "fitdocs"` key.

### The non-activity FIT path
- **Sources Consulted**: `src/fitdocs/ingest/__init__.py`,
  `src/fitdocs/ingest/file_id.py`, `src/fitdocs/model.py`,
  `src/fitdocs/layout.py:206-235`, the garmin-fit-sdk profile, a scratch
  probe.
- **Findings**:
  - `parse_fit` reads `file_id_mesgs` (`ingest/__init__.py:76`) but
    `extract_file_identity` never reads `type` (`ingest/file_id.py:32-46`).
    `FileIdentity` has four fields (`model.py:282-297`) and is public plugin
    API (`docs/plugins.md:255`, `tests/test_public_api.py:118`).
  - The SDK profile's `file` enum names 20 types (`activity` = 4,
    `monitoring_a/b`, `monitoring_daily`, `settings`, `course`, …); Garmin's
    sleep and HRV-status file types are not in it, and the decoder returns
    the raw integer for them (probe: type `49` decodes as `49`, `monitoring_b`
    as `"monitoring_b"`).
  - Probe: a synthetic `monitoring_b` file with one monitoring message,
    synced through `sync()`, wrote `workouts/undated-workout-<uid12>.md` and
    archived the source. The brief's inference is confirmed.
  - The guard placed in `_run_planned`'s preparation (`sync.py:1438-1449`,
    after `parse_fit` at `:1446`) covers `sync`, `drain` and `regen`'s
    unreferenced-archive part; `regen`'s page part (`_process_isolated`) never
    reaches it, so existing pages are untouched.
- **Implications**: fit-ingest amendment: `FileIdentity.file_type: str | None
  = None` plus `is_activity_file`; sync amendment: a fourth `skipped` cause and
  a ninth warning cause (the `SyncReport` docstring already anticipates "a
  ninth cause", `sync.py:420`).

### The analytics index producer seam
- **Sources Consulted**: `src/fitdocs/index/schema.py`,
  `src/fitdocs/index/registry.py`, `src/fitdocs/index/derived/benchmarks.py`,
  `src/fitdocs/index/derived/inputs.py`, `src/fitdocs/index/refresh.py`,
  `tests/index/test_schema_version.py`, `tests/index/derived/test_boundary.py`,
  `tests/index/derived/test_registration.py`.
- **Findings**:
  - `SCHEMA_VERSION = 2` (`schema.py:15`), pinned with a per-version digest
    map (`tests/index/test_schema_version.py:15-24`).
  - Corpus producers have `fingerprint(corpus)` and `rows(corpus)`
    (`index/producer.py:108-117`); `BenchmarkProducer` fingerprints one file
    with `file_digest` (`index/derived/benchmarks.py:200-235`).
  - The benchmarks table is long-format with `value` + `unit` token columns
    (`benchmarks.py:24-72`): precedent for a long `wellness_daily`.
  - A failing producer is caught, reported, and its previous rows kept
    (`index/refresh.py:442-471`).
  - `index.derived` modules import from an allow-list
    (`tests/index/derived/test_boundary.py:104-188`); `fitdocs.wellness` must
    be appended. `CORPUS_PRODUCERS` and the 24-table count are pinned
    (`tests/index/derived/test_registration.py:25`, `:59`).
  - Only `cli` and `query` may import `fitdocs.index`
    (`tests/index/test_boundary.py:38-46`, `:449-462`): wellness never imports
    the index.
- **Implications**: `WellnessProducer` in `index/derived/wellness.py`, one long
  table, schema version main + 1, regenerated docs block
  (`uv run python -m tests.query.test_docs_analytics`).

### Units
- **Sources Consulted**: `src/fitdocs/units.py`, `tests/test_units.py`.
- **Findings**: 19 units (`units.py:41-61`); no token for millilitres per
  kilogram per minute or breaths per minute. The unit table is the single
  vocabulary (chart-kit decision; peer log 2026-10-12). Count pins:
  `tests/test_units.py:76`, `:87`, `:104`, and the pre-change projection
  literal of `UNIT_SUFFIXES`.
- **Implications**: append `ml_per_kg_min` and `brpm`; update the pins
  append-only. No existing index column ends in either suffix, so no schema
  description changes.

### Measured shapes (maintainer's Garmin export, keys/types/counts only)
- **UDSFile** (30 files, 1,325 day records): `calendarDate` (all YYYY-MM-DD,
  no duplicate dates across files), `restingHeartRate` and
  `currentDayRestingHeartRate` (both on 937 days, equal on 83),
  `minHeartRate`/`maxHeartRate` (1,052), `totalSteps` (1,116; zero on 114),
  `averageSpo2Value` (131), `allDayStress.aggregatorList[]` with
  `type ∈ {TOTAL, AWAKE, ASLEEP}` and `averageStressLevel` (TOTAL negative on
  93, zero on 2), `bodyBattery.bodyBatteryStatList[]` with
  `bodyBatteryStatType ∈ {HIGHEST, LOWEST, MOSTRECENT, ENDOFDAY, STARTOFDAY}`,
  `respiration.{avgWakingRespirationValue,…}`, `version` (int), `uuid`.
  - Seven-day test: `restingHeartRate` is within 1 bpm of the trailing
    seven-day mean of `currentDayRestingHeartRate` (including the day) on 737
    of 937 days; mean absolute day-to-day change 1.17 bpm versus 6.51 bpm for
    `currentDayRestingHeartRate` (793 consecutive pairs).
- **sleepData** (16 files, 1,065 nights): `calendarDate`,
  `sleepStartTimestampGMT`, `sleepEndTimestampGMT`, `deepSleepSeconds`,
  `lightSleepSeconds`, `remSleepSeconds`, `awakeSleepSeconds`,
  `unmeasurableSeconds`, `averageRespiration`, `spo2SleepSummary{…}`,
  `sleepWindowConfirmationType` (`UNCONFIRMED` 461 = the nights with no
  stages; `OFF_WRIST` 123). Stages: all four present on 462 nights, none on
  461; deep+light+REM > 0 on 481. For the 45 nights spanning two GMT dates,
  `calendarDate` equals the end date on 44 — the wake date.
- **MetricsMaxMetData** (19 files): `calendarDate`, `sport ∈ {RUNNING,
  CYCLING, WALKING, absent}`, `vo2MaxValue` (never null), `updateTimestamp`
  (local ISO, 21 chars). 385 of 643 (day, sport) keys have several records,
  40 with differing values; the latest `updateTimestamp` resolves all 40.
- **userBioMetrics** (1 file, 1,795 records): `metaData.calendarDate` on all;
  `weight{weight, timestampGMT, sourceType}` on 23, every weight above 1,000
  (grams).
- **Other files that must not be recognized**: `HydrationLogFile_*`
  (has `calendarDate`, none of the signature keys), `*_bioMetrics_latest`,
  `*_userBioMetricProfileData`, `*_fitnessAgeData`, `*_heartRateZones`.
- Garmin file names embed the user's profile id; recognition never depends
  on it, and no name or id is reproduced in fixtures.

### intervals.icu wellness shape (from the discovery record)
- 483 day records, 47 fields; `id` is the date; every record has `updated`;
  non-null: `restingHR` 452, `hrvSDNN` 481, `hrv` 0, `sleepSecs` 476, `spO2`
  479, `steps` 481, `vo2max` 242, `weight` 29, subjective fields (`fatigue`,
  `mood`, `motivation`, `soreness`, `stress`, `injury`, `hydration`) 10;
  `sleepScore`, `avgSleepingHR`, `respiration`, `readiness` 0. Computed fields
  `ctl`, `atl`, `rampRate`, `sportInfo`, `ctlLoad`, `atlLoad`.
- No intervals.icu payload exists in the repository and none was fetched; the
  field names come from `.kiro/specs/wellness-pull/brief.md` and the roadmap.
  The parser maps only fields named there.

### Folded wave-2 amendments (2026-10-12, controller rulings)
- **`MetricInfo.label`** (from recovery, ruling R1): one short label per
  metric, pairwise distinct, owned here; recovery and workout-wellness hold
  no label table. The labels are the ones recovery's design was written
  against.
- **`LATEST_ENTRY` parses only the winner** (from apple-health-import): the
  engine reads each entry's order header through `archive.read_entry_order`
  and parses only the greatest `(order, ref)`; a damaged superseded body no
  longer fails a rebuild. Supersession moved from the merge to the engine;
  the merge keeps a one-winner precondition.
- **Extractor edge cases**: the original is re-hashed before an extractor's
  error is classified, so a candidate changed or truncated mid-read is
  deferred rather than quarantined; `KeyboardInterrupt` removes the temp file
  and propagates.
- **Gapped boundary ranks** (multiples of 10) so apple-health-import inserts
  its seven `formats/apple/*` modules without renumbering.
- **zipfile reads, measured** (stdlib scripts in the session scratchpad,
  CPython 3.11.15, 3.12.13, 3.13.14):
  - `_EndRecData` issues an **unsized** `read()` on 3.11 (sized on 3.12+):
    22 bytes before EOF for a comment-less zip, and in the comment fallback
    from `size − (1 << 16) − 22`, i.e. **65,558** bytes before EOF — one more
    than `ZIP_MAX_COMMENT + 22` (65,557), the bound first proposed.
  - `_RealGetContents` reads the whole central directory in one sized read:
    1,940,000 bytes for 20,000 members (above `CHUNK_BYTES`) on 3.11 and 3.13.
  - Streaming a member with `ZipFile.open(...).read(CHUNK_BYTES)` never asks
    the file for more than `CHUNK_BYTES` (stored and deflated members).
  - Consequence: the counting-opener rule admits the two structural reads
    once each and bounds memory by the zip's own structure (central directory
    + 65,558 bytes + one chunk), not by member data.
- **Sanctioned series builder**: `tests/wellness/builders_series.py`
  `write_series` stages a series through the real codec, so downstream tests
  (recovery, workout-wellness) never import `encode_year` or the manifest
  encoder.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Widen `fit-archive/` and `select_candidates` | Archive wellness beside FIT files, one selector | One archive | Moves ~15 FIT pins; widens the folder connector; mixes immutable FIT semantics with extracts | Rejected |
| Separate package + archive + selector (chosen) | `fitdocs.wellness`, `wellness-archive/<format>/`, `select_wellness_candidates` | FIT paths untouched; per-format directories route the rebuild; connector unchanged | Two archives to explain | Mirrors `history`/`plans` package precedent |
| Incremental merge into the series | Merge each new file into the existing series | Cheap per drain | Order-dependent; drift between incremental and full results | Rejected: full rebuild is deterministic and cheap |
| Full rebuild on change (chosen) | Re-parse every archive entry when inputs change | Deterministic, crash-healing | Re-parses the archive (seconds) | Gated by an inputs digest |

## Design Decisions

### Decision: Long-format yearly CSV series plus a TOML manifest
- **Context**: Req 11; the brief left CSV, TOML or a markdown table to the
  design.
- **Alternatives Considered**:
  1. Wide CSV, one row per day, one column per metric and source.
  2. Markdown tables per year.
  3. TOML arrays of tables.
  4. Long CSV (`day,metric,source,origin,value,canonical`) per year.
- **Selected Approach**: 4, with `wellness/manifest.toml` recording the
  inputs digest, the files and their hashes, the archive entries and their
  state, the effective precedence and the conflicts.
- **Rationale**: a new metric or source adds rows, never columns, so no file
  is rewritten wholesale when apple-health-import or a follow-on adds a
  metric, and the index table needs no schema bump for it (Req 17.5). One
  line per value diffs cleanly. CSV opens in every spreadsheet and data tool.
  A markdown table of thousands of rows renders poorly; TOML is several times
  larger.
- **Trade-offs**: about 40 bytes per value (roughly 250 KB per year at 18
  values a day) versus about 110 KB for a wide file; accepted for stability.
- **Follow-up**: measure the maintainer's first full build's size.

### Decision: Snapshot-and-revision merge within a source
- **Context**: Req 9; intervals.icu re-delivers days with a newer `updated`;
  Garmin VO2max repeats days with `updateTimestamp`; two Garmin exports may
  overlap.
- **Selected Approach**: a parsed record is a *day snapshot*: the metrics it
  is authoritative for (`covers`), the values it holds, and an optional
  revision. Per source, day and metric, the snapshots with the greatest
  revision decide; a later snapshot without a value makes the metric absent;
  equal-revision snapshots with different values are a conflicting duplicate,
  kept by the greatest `(entry path, ordinal)` and recorded.
- **Rationale**: one rule covers explicit nulls (Req 9.2), late corrections
  (9.1) and genuine conflicts (9.4) without format-specific merge code.

### Decision: Default source precedence by source kind
- **Context**: Req 10.2; the roadmap's "device-native export outranks the
  relay".
- **Selected Approach**: each source declares a kind — `device` (a device
  platform's own export), `hub` (a phone health store), `relay` (an
  aggregator) — and the default order is device, hub, relay, then source id.
  With the Phase 12 sources: `garmin-export`, `apple-health`,
  `intervals-icu`.
- **Rationale**: Apple Health is itself a store third-party apps (Garmin
  Connect among them) write into, so a device's own export ranks above it; no
  future source id needs hard-coding here.

### Decision: Garmin resting HR from `currentDayRestingHeartRate`
- **Context**: measured seven-day relationship (above).
- **Selected Approach**: `currentDayRestingHeartRate` → `resting_hr_bpm`;
  `restingHeartRate` is not imported (a computed rolling mean, like the
  computed fields Req 5.6 excludes).
- **Follow-up**: hr-derivation and recovery consume a daily, not a smoothed,
  Garmin resting HR; the controller relays this.

### Decision: Day-boundary rule
- **Selected Approach**: nights belong to the wake date; a format that has
  end times rather than dates assigns `date(end_local + 6 h)` (end in
  `[D−1 18:00, D 18:00)` → D); local time comes from the recorded UTC offset,
  never the machine timezone; sources that report dates keep them.
- **Rationale**: Garmin (measured), intervals.icu and Oura already attribute
  nights to the wake date, so the rule adds no shifting for the shipped
  formats and gives Apple's segments a crisp rule.

### Decision: Non-activity FIT is skipped, warned and left in place
- **Alternatives**: quarantine it (it is not bad bytes); archive it in the
  wellness archive for a future parser (the roadmap says "held and reported",
  the brief "reported and left alone"); report it in `unrecognized`.
- **Selected Approach**: a fourth `skipped` cause plus a warning, no archive,
  no quarantine entry; existing pages untouched.
- **Rationale**: one implementation in the planner serves `sync`, the drain
  and `regen` alike; the version-gated skip is the precedent for "skipped,
  nothing archived, stays in the inbox".

### Decision: Generalizations kept at the interface, not the implementation
- The format registry is an append-only tuple of frozen `FormatSpec` values
  with callables (chart-kit's `KINDS` precedent), so apple-health-import adds
  a format by appending; no plugin discovery.
- `ArchiveForm.EXTRACT` and `Supersession.LATEST_ENTRY` are defined and
  exercised with a synthetic test-only format, because the Apple format is the
  only planned user and lands in another spec.

### Build vs. adopt
- CSV, JSON, TOML, hashing, zip and XML: standard library (`csv`, `json`,
  `tomllib`, `hashlib`) plus the already-required `tomli_w`. No new runtime
  dependency (Req 20.2).
- DuckDB `read_csv` was not adopted for the index producer: the index's
  connections forbid external file access (tech.md), so the producer reads
  through the series reader like every other consumer.

### Simplification
- No new CLI command: the drain rebuilds a stale series, `regen` always
  rebuilds, `check` reports.
- No incremental merge, no parse cache, no per-entry sidecar files.
- `--force` has no wellness effect (the archive is never rewritten and the
  rebuild is input-driven).

## Risks & Mitigations
- **A conflict finding with no fix keeps `check` red.** Conflicts arise only
  from overlapping exports of a source without a revision field; the remedy
  (delete the wrong entry from the archive and the inbox, `regen`) removes it.
- **Unrecognized `.json` files re-reported every drain under the leave
  default.** Only registered suffixes are candidates; `[inbox] ignore`
  silences a file; the docs say so.
- **Every sync now creates `wellness/` and `wellness-archive/` with an
  `AGENTS.md`**, as `fit-archive/` already is; stated in the contract's "what
  changed" text and the release notes.
- **Dashboards lands first** with a reshaped `_OWNER_BLOCK`; the wellness
  branches use whatever owner formatting main has at landing; append-only
  tuples keep both sides.
- **A page rendered earlier from a non-activity FIT stays.** `check` cannot see
  it (it never opens `.fit` files); queued as a follow-up.

## References
- `.kiro/steering/roadmap.md` § Phase 12 — decisions, measured data,
  viability.
- `.kiro/specs/{wellness-pull,apple-health-import,hr-derivation,recovery,workout-wellness}/brief.md`
  — downstream needs.
- garmin-fit-sdk `Profile['types']['file']` — the public file-type enum.
