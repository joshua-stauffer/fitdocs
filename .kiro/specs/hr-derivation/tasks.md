# Implementation Plan

## Upstream Prerequisites

- **wellness-store must be on `main` first.** Tasks 1.x and 2.x do not need
  it; 3.1 onward does. No wellness-store amendment is needed. Before building
  3.1, verify that each of these exists on `main`:
  - the `fitdocs.wellness` facade names `read_series`,
    `WellnessSeries.sources` / `by_source`, `Metric.RESTING_HR_BPM`,
    `load_wellness_settings`, `effective_order`, `SeriesReadError`,
    `WellnessSettingsError`;
  - `fitdocs.layout.wellness_series_path`;
  - the one sanctioned series test builder,
    `tests/wellness/builders_series.py::write_series(data_root, values:
    Iterable[SeriesValue]) -> tuple[Path, ...]`.
  Any name missing is a stop-and-report, not a local substitute.
- **Version constants.** `CONTRACT_VERSION` becomes main + 1 at landing
  (4.2 writes it; 5.2 re-derives it after the final rebase). `DOC_VERSION`,
  the index `SCHEMA_VERSION`, `ATHLETE_SCHEMA_VERSION` and
  `LOAD_PAYLOAD_VERSION` stay as main has them (design § Decisions 8, 9, 19).
- **Selection is not touched.** `BenchmarkSet.applicable` stays exactly as
  it is for every kind (maintainer decision 3, 2026-10-12). The
  hand-recorded-wins rule lives only in what the heart-rate walk writes.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Amendments). Each is appended to the named spec's documents as
  `## Amendment N (<date>): <title>, landed by hr-derivation` by the task
  that makes the change, taking the next free number at that moment:
  athlete-benchmarks (1.1, provenance only), performance-benchmarks (1.2),
  load-channels (1.3), wiki-contract (4.2).
- **Peers.** `impl-dashboards` (not on main) edits `cli.py`'s drain-pass
  block, not `derive_benchmarks_command`, and takes `CONTRACT_VERSION`
  9 → 10. `CONTRACT_VERSION` is raised by dashboards and by all five Phase
  12 bumpers — wellness-store, wellness-pull, hr-derivation, recovery and
  workout-wellness — each of which may add head- or history-paragraph pins;
  whichever lands later re-derives main + 1 and keeps every pin it finds.
  `apple-health-import` touches none of this plan's source files, and
  `workout-wellness` none except the append-only lists below.

**Hard rules for every task**

- **Absent is `None` / no entry.** No code here substitutes a default,
  zero, an earlier hand value or another kind's value; no evidence means no
  entry.
- **No clock, no network, no index.** No `date.today`, `datetime.now`,
  `time.*`, `urllib`, `socket`, `fitdocs.index`, `fitdocs.query` or `duckdb`
  anywhere in `fitdocs.hr_benchmarks`; only `engine.py` does I/O. The guard
  (2.2, 4.1) enforces it.
- **Imports follow design § Allowed Dependencies**: pure modules in the
  order `types` → `sources` → `peaks`, `maximum`, `resting` → `timeline` →
  `inspect`; `fitdocs.wellness` reached only through its facade and only
  from `engine.py`; nothing in `fitdocs.load.*`, `fitdocs.performance`,
  `fitdocs.wellness` or `fitdocs.index` imports `fitdocs.hr_benchmarks`.
- **No general baseline API.** `fitdocs.hr_benchmarks` exports no baseline,
  rolling-median or normal-range function; `recovery` owns those.
- **Synthetic data only.** Samples, sessions, series values and profiles are
  invented by `tests/hr_benchmarks/builders.py` or local helpers; FIT files
  come from `tests/fixtures/builder.py`; a series is staged only through
  `tests/wellness/builders_series.py::write_series` (never `encode_year` or
  the manifest encoder directly); no maintainer value, date, file name or
  count appears in a test or a doc (the measured aggregates already in
  design.md and research.md are the only exception, and they are not copied
  into tests).
- **A staged series is stale by design.** `write_series` writes no archive
  entries, so `fitdocs check` reports the series stale and a drain or
  `regen` rebuilds it away. Tests that stage a series never run a drain or
  `regen` afterwards and never assert a clean `check` over it.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination): each named mutation is applied, observed red,
  reverted by restoring a `cp` taken before it, observed green, and recorded
  in Implementation Notes. A mutation that cannot be made red is reported
  UNPINNED, never hidden. Before submitting, run the prose-claim grep over
  changed test files and re-run or delete every surviving claim.
- **Fixtures discriminate.** Pairwise-distinct values wherever a mapping is
  asserted; value order and date order disagree; the interesting entry or
  session is not first; an asserted end state is shown false beforehand;
  "nothing written" asserted on bytes and `st_mtime_ns`.
- **Parallel streams.** `(P)` tasks run in separate worktrees and edit only
  files inside their `_Boundary_`. `tests/hr_benchmarks/builders.py` and
  `tests/hr_benchmarks/conftest.py` are created by 2.1 and frozen
  afterwards: a stream that needs another helper defines it in its own test
  module. Only 2.2 and 4.1 edit `tests/hr_benchmarks/test_boundary.py`.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in
  the same worktree** (`tests/test_bytecode_hygiene.py`).
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`.
- **Types and lint.** Each task runs `uv run mypy`, `uv run ruff check` and
  `uv run ruff format --check`.
- **Stop and report** on any need for: a runtime dependency; a new
  configuration key; any change to `BenchmarkSet.applicable` or to how an
  entry is selected; a change to the threshold calculator, channel selection
  or prompts; a read of the analytics index or the wellness archive; a write
  anywhere but `athlete.toml` (and, for 4.2, the contract files and
  declarations); a version-constant change other than `CONTRACT_VERSION`; a
  wellness-store change.

## Shared source files

Each file below has more than one writer; its writers are sequential.

- `src/fitdocs/load/profile.py`: 1.1 (recognized source key), then 1.2
  (`kinds` partition).
- `src/fitdocs/performance/engine.py`, `tests/performance/test_engine.py`:
  1.2 (partition, `accepted`, `load_settings`), then 3.2 (the three-resolver
  agreement case in the test file).
- `src/fitdocs/hr_benchmarks/sources.py`, `tests/hr_benchmarks/test_sources.py`:
  2.1 creates them; 2.8* (optional) adds corroborators and the blocked set's
  members.
- `src/fitdocs/hr_benchmarks/__init__.py`: 2.1 (docstring only), then 3.3
  (re-exports).
- `src/fitdocs/hr_benchmarks/engine.py`, `tests/hr_benchmarks/test_engine.py`:
  3.1 creates; 3.2, then 3.3 extend.
- `tests/hr_benchmarks/test_boundary.py`: 2.2 creates; 4.1 adds the literal
  module list, single-writer and reachability pins.
- `src/fitdocs/cli.py`, `tests/test_cli_derive.py`: 3.5 only (1.2 touches
  `tests/test_cli_derive.py` only if a pin of the old write breaks; 3.5
  follows).
- `docs/ownership-contract.md`: 4.2 (version line, "What changed"
  paragraph), then 4.3 (`derive-benchmarks` operation, `athlete.toml`
  paragraph). `README.md`, `docs/configuration.md`,
  `.kiro/steering/structure.md`: 4.3. `src/fitdocs/skills/fitdocs-workouts/SKILL.md`,
  `CHANGELOG.md`: 4.4.
- `pyproject.toml`: 2.1 (append `tests/hr_benchmarks` to
  `[tool.mypy].files`).
- `src/fitdocs/index/derived/benchmarks.py` (the `source_page` description),
  `tests/index/derived/test_benchmark_producer.py`, `docs/analytics.md`: 4.3
  only.

## Cross-spec shared files (append-only, keep both sides on rebase)

`CONTRACT_VERSION` and its history paragraph, the declaration goldens'
version line, the contract head-paragraph and history pins,
`WRITING_ENTRY_POINTS` (`tests/test_confinement.py`), `FindingKind`
(`audit.py`; wellness-store appends four), the licensed callers of
`load_load_settings` (`tests/load/test_settings.py`), the contract-consumer
registry (`tests/test_contract_consumers.py`), `[tool.mypy].files`,
`CHANGELOG.md` Unreleased, `.kiro/steering/structure.md`, the public API
pins (`tests/test_public_api.py`), the workouts skill and
`tests/test_agent_skill.py`, `docs/ownership-contract.md`, `README.md`,
`docs/configuration.md`, and the generated `docs/analytics.md` block
(regenerate it after the rebase rather than merging it by hand).

## Test File Ownership

- Provenance and selection-pin cases in `tests/test_benchmarks.py`, the
  overlay case in `tests/load/test_profile.py`: **1.1**. The fourteen
  `with_derived_benchmarks(...)` calls and the new partition cases in
  `tests/load/test_profile.py`; the partition, `accepted`, field-order and
  `load_settings` cases in `tests/performance/test_engine.py`: **1.2**. Value
  pins in `tests/load/channels/test_heart_rate.py`: **1.3**.
- `tests/hr_benchmarks/__init__.py`, `builders.py`, `conftest.py`,
  `test_types.py`, `test_sources.py`: **2.1** (2.8* extends
  `test_sources.py`). `test_purity.py`, `test_boundary.py`,
  `test_constant_guard.py`: **2.2**. `test_peaks.py`: **2.3**.
  `test_maximum.py`: **2.4**. `test_resting.py`: **2.5**.
  `test_timeline.py`: **2.6**. `test_inspect.py`: **2.7**.
- `tests/hr_benchmarks/test_engine.py` (created), the licensed-caller set in
  `tests/load/test_settings.py`: **3.1**. The contract-consumer registry entry
  in `tests/test_contract_consumers.py`, the three-resolver agreement case in
  `tests/performance/test_engine.py`, workout cases in `test_engine.py`:
  **3.2**. Reconciliation and report cases in `test_engine.py`: **3.3**.
  Heart-rate cases in `tests/test_audit.py` and `tests/test_cli_check.py`:
  **3.4**. `tests/test_cli_derive.py` heart-rate cases, the re-scoped
  untagged-archive test and the `perturbed_calls` re-pin; the
  one-read assertion in `tests/load/test_settings.py:2478-2483` re-run
  unchanged: **3.5**.
- The module-list, single-writer and reachability pins in
  `tests/hr_benchmarks/test_boundary.py`, the public API pin in
  `tests/test_public_api.py`, the `derive-benchmarks-heart-rate` entry point
  in `tests/test_confinement.py`: **4.1**. Contract-version pins
  (`tests/identity/test_contract_docs.py:177-209`, `tests/test_contract.py`,
  `tests/test_ownership_contract.py`, `tests/test_declaration*.py`,
  `tests/index/test_contract_docs.py`, `tests/index/derived/test_preserved.py`,
  `tests/compose/test_contract_docs.py`, every peer head- or history-paragraph
  pin present at landing) and the regenerated declaration goldens: **4.2**.
  Doc pins in `tests/test_docs_guarantees.py` / `tests/test_ownership_contract.py`
  narrative phrases, `tests/hr_benchmarks/test_docs.py`: **4.3**.
  `tests/test_agent_skill.py`, `tests/test_changelog.py` if they pin
  sections: **4.4**.
- `tests/hr_benchmarks/test_e2e.py`, `test_determinism.py`: **5.1**.

---

- [ ] 1. Shared seams: provenance, the partitioned write and the channel's inputs

- [x] 1.1 Accept a series reference in a benchmark's provenance record, and pin that selection is unchanged (athlete-benchmarks amendment, provenance only)
  - Add the optional series reference to the provenance value (trailing,
    absent by default); the parser accepts it absent or as a non-empty string
    and rejects any other value naming the entry; derived origins still
    require method, document, inputs and citation; the serializer emits it
    after the document; the store's recognized source keys gain it after the
    document, so the overlay replaces it and keeps unknown keys.
  - Selection is not modified. Add the first test that combines a derived
    entry with a hand back-reach: a derived `max_hr_bpm` measured before a
    hand entry whose `applies_from` is earlier still wins on its own date and
    after, up to the hand entry's measurement date, and the hand entry fills
    only the days before the derived entry (today every `applies_from`
    fixture is hand-only: `tests/test_benchmarks.py:1722-3129`,
    `tests/index/derived/conftest.py:126-128`,
    `tests/index/derived/test_refresh.py:123-127`).
  - Append the athlete-benchmarks amendment record: Req 1.13, 2.13 and 2.14
    extended with the series reference; the Boundary Context names the
    heart-rate stage and records its hand-wins rule as a rule of what that
    pass writes; Req 3 and Amendment 1 untouched.
  - **Tests**: round trip with and without the reference; empty string and
    a number rejected with the entry named; emitted key order
    `kind, method, document, series, inputs, citation`; a rewrite overlays the
    reference and keeps an unknown source key; a derived record without a
    document is still rejected (an earlier release always finds a
    document); the selection pin above, with the derived and hand values
    distinct and the probe dates on both sides of the derived date.
  - **Mutations:** emit the reference before the document; drop it from the
    recognized keys (an old reference then survives a rewrite that removed
    it); accept an empty string; let tier 2 win over a derived tier-1 winner
    inside the hand entry's back-reach (the rule this spec's first draft
    proposed; the selection pin reds).
  - **Observable:** `uv run pytest tests/test_benchmarks.py tests/load
    tests/index` green; `git diff` shows no change to
    `BenchmarkSet.applicable`.
  - _Requirements: 5.6, 6.5, 7.4, 7.5, 10.7_

- [x] 1.2 Partition the derived write by kind, move the tagged-effort stage onto its partition, and let it reuse the run's `[load]` read (performance-benchmarks amendment)
  - This is an explicit integration task across the profile store and the
    tagged-effort stage: the new `kinds` argument is required, so both
    callers change in one commit.
  - The derived write takes a required set of kinds: it replaces only
    derived entries of those kinds, keeps derived entries of other kinds
    byte-equivalent, scopes the "group no longer covered" removal to those
    kinds, and refuses (nothing stored) an entry outside the set, an entry
    without derived provenance, or a collision with a hand-recorded key.
  - Publish the tagged-effort stage's three kinds as its partition; its change
    test compares only that partition's derived entries; its write names the
    partition; its report carries the accepted set (written, or would be
    under preview) as a trailing field.
  - The tagged-effort stage accepts already-read load settings; when given,
    it neither reads the settings document nor calls the `[load]` reader
    (today `performance/engine.py:328-329` always reads it). Direct callers
    without the argument keep today's behaviour. (3.5 passes the preflight's
    settings, so `tests/load/test_settings.py:2478-2483` stays at exactly one
    read per `derive-benchmarks` run.)
  - Append the performance-benchmarks amendment record: 10.4 reworded to the
    tagged-effort stage, 1.3, 10.5 and 10.7 scoped to that stage, 6.3 scoped
    to its quantities, design § ProfileDerivedWrite's `kinds`, the
    `load_settings` argument; update the 10.4 reference in the derive
    module's docstring (`performance/derive.py:747`).
  - **Existing tests this turns red, and their re-pin:** the fourteen
    `with_derived_benchmarks(...)` calls in `tests/load/test_profile.py`
    (2723, 2808, 2855, 2860, 2873, 2876, 2902, 2928, 2956, 2999, 3070, 3126,
    3171, 3194) gain `kinds` (line 2823 is docstring wording naming the
    call; update it only if it quotes the old signature). Store-level tests that mix kinds pass the
    union of both partitions, which keeps their meaning: 2808 passes max,
    resting, pace, FTP and LTHR entries in one call, and the empty write at
    2698-2775 removes derived entries of both partitions. The `DeriveReport`
    field-order pin at `tests/performance/test_engine.py:513-520` gains
    `accepted` last.
  - **New tests**: one per partition — writing the tagged partition leaves
    derived max/resting entries byte-equivalent, and writing the heart-rate
    partition leaves derived threshold entries byte-equivalent; a second
    tagged run with an unchanged tag set writes nothing (mtime unchanged)
    while a derived heart-rate entry is on file; an entry outside the
    partition and a derived-less entry each raise with nothing stored; group
    removal leaves another partition's emptied group alone; the accepted set
    equals what was written and is identical under preview; with
    `load_settings` given, a monkeypatched `[load]` reader is never called
    and the given sufficiency settings are the ones applied (a value that
    changes a decline).
  - **Mutations:** compare `previous_derived` across all kinds (the
    idempotence case reds); retain no other-partition derived entries; drop
    the outside-partition check; read `[load]` even when settings are given.
  - **Observable:** `uv run pytest tests/load tests/performance
    tests/test_cli_derive.py` green.
  - _Requirements: 1.8, 4.6, 5.1, 8.1, 8.3, 8.4, 8.5, 8.6_

- [ ] 1.3 (P) Report the dated resting and maximum entries the heart-rate channel used (load-channels amendment)
  - Append the measurement dates of the resting and maximum heart-rate
    entries to the channel's reported inputs, after the threshold's date;
    nothing else in the channel changes.
  - Pin the `impulse` and `reference` values with pairwise-distinct
    expectations computed independently of the channel, and make true or
    delete the `# Req 1.3` comment beside them (closes
    `.kiro/queue/2026-08-25-heart-rate-inputs-used-values-unpinned.md`; move
    it to `closed/` with `status: done`).
  - Append the load-channels amendment record (new criterion under
    Requirement 5).
  - **Tests**: the two dates equal the supplied entries' dates, with resting
    and maximum dated differently from each other and from the threshold;
    impulse and reference values asserted.
  - **Mutations:** swap the two new dates; swap impulse and reference (the
    queue item's mutation); report the threshold's date for both.
  - **Observable:** `uv run pytest tests/load/channels` green; any golden of
    an HR-computed load region regenerated and diffed to show only the two
    new rows.
  - _Requirements: 10.2, 10.3_
  - _Boundary: HeartRateChannelInputs_

- [ ] 2. The pure core of `fitdocs.hr_benchmarks`

- [ ] 2.1 Create the package with its vocabulary, its constants and their records, and the shared test builders
  - Create `fitdocs.hr_benchmarks` with a docstring-only facade and the types
    of design § HrTypes (the two-kind partition, the method vocabulary,
    evidence, session peak, no-evidence reasons, kind rule, takeover,
    back-reach and back-reach change, violation, inconsistency, skipped
    document, failure, kind outcome, stage report).
  - Create the sources module per design § HrSources: one fitdocs-choice
    record per constant group with justification, search basis and the
    aggregate measurement design.md records; every constant bound to exactly
    one record; the two kind rules assembled from them; an empty tracked
    exception set. No configuration key for any constant.
  - Create `tests/hr_benchmarks/__init__.py`, `builders.py` (synthetic
    `Samples` with explicit times, session peaks, per-source day values,
    hand and derived benchmark entries, a tmp data root with an
    `athlete.toml`) and `conftest.py`; append `tests/hr_benchmarks` to
    `[tool.mypy].files`.
  - **Tests**: the partition is exactly the two heart-rate kinds and disjoint
    from the tagged-effort partition (1.2); method values are the two
    published tokens; every constant appears in the constant table exactly
    once and is governed by one record of the fitdocs-choice shape; the kind
    rules carry 3 and 2 bpm steps and 14 and 1 confirmation days.
  - **Mutations:** bind a constant to no record; change a step value (the
    pinned table reds); add a third kind to the partition.
  - **Observable:** `uv run pytest tests/hr_benchmarks` green and
    `uv run mypy` covers the new tests.
  - _Requirements: 1.2, 2.6, 4.1, 5.9, 7.6, 7.7_
  - _Depends: 1.2_

- [ ] 2.2 Guard the package's purity, imports and constants before the streams start
  - An AST guard over every module of `fitdocs.hr_benchmarks` found by glob:
    a rank table naming the modules of design § File Structure Plan; pure
    modules import only the sanctioned set and lower-ranked package modules;
    only `engine.py` may import the I/O modules; no module imports
    `fitdocs.index`, `fitdocs.query`, `duckdb`, `fitdocs.performance`,
    `fitdocs.render`, `fitdocs.sync`, `fitdocs.cli` or a `fitdocs.wellness`
    submodule; no clock call, network module or prompt anywhere; a module on
    disk missing from the rank table fails.
  - A constant guard following `tests/performance/test_constant_guard.py`'s
    rules: the arithmetic modules reach every constant through its bound
    record, never as a bare literal.
  - **Positive control**: the visited module set equals a filesystem glob of
    the package and is non-empty; synthetic violators (an `fitdocs.index`
    import, a `datetime.now()` call, a `fitdocs.wellness.series` import, a
    higher-ranked import, a bare `365` in an arithmetic module) are each
    caught.
  - **Mutations:** skip `types.py` in the walk (the glob control reds);
    drop the clock check; drop the rank comparison.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_purity.py
    tests/hr_benchmarks/test_boundary.py tests/hr_benchmarks/test_constant_guard.py`
    green with every synthetic violator caught.
  - _Requirements: 1.7, 1.9, 3.8, 4.8_

- [ ] 2.3 (P) Find one session's 30-second sustained peak
  - Implement design § SessionPeaks in its normative order: no heart rate;
    a locked cadence-lock verdict; exclusion of samples in locked spans for
    running; sample rejection by range and by rate against the previous kept
    sample; stretches split at gaps over 10 s; the greatest forward-held
    30-second mean inside one stretch, in linear time; no stretch long
    enough.
  - Reads only the samples, the modality and the flag settings; never the
    session summary.
  - **Tests**: a single high spike removed by the rate rule; range bounds 30
    and 230 inclusive; a 31-s stretch beside a higher 29-s stretch split by
    an 11-s gap; a 10-s gap does not split; a locked span's samples excluded
    in an otherwise clear run and ignored for a ride; a locked verdict
    returns the reason before any peak; forward hold distinguished from
    backward hold by a fixture whose two holds differ; a summary maximum far
    above every sample never appears in the result; the linear search equals
    a brute-force reference on generated stretches.
  - **Mutations:** drop the rate test; `>` → `>=` on the gap; hold the later
    sample; skip span exclusion; read the summary maximum.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_peaks.py` green.
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.8_
  - _Boundary: SessionPeaks_

- [ ] 2.4 (P) Work out maximum-heart-rate evidence over the 365-day window
  - Implement design § MaxEvidence: evidence days at every session date and
    every leave day; the window's three highest by peak with ties broken by
    date then page; the median rounded half up; the median session's page as
    document; the inputs and summary texts.
  - **Tests**: window bounds at 364 and 365 days; fewer than three sessions
    gives none; peaks whose date order disagrees with value order; a leave
    day lowering the value; the document is the median session's page, not
    the highest's; x.5 rounds up; tie-break deterministic under reversed
    input order.
  - **Mutations:** window off by one; take the highest instead of the
    median; sort by date; round half to even.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_maximum.py`
    green.
  - _Requirements: 3.6, 3.7, 4.10, 7.2_
  - _Boundary: MaxEvidence_

- [ ] 2.5 (P) Work out resting-heart-rate evidence, one baseline per source
  - Implement design § RestingEvidence over plain per-source day values (no
    wellness import): the 28-day median formed with at least 14 values; the
    first source in the given precedence whose baseline is formed, then any
    unlisted source by id; half-up rounding; the series reference, document
    (through the injected year-to-path function), inputs and summary texts.
  - **Tests**: 13 vs 14 values; median not mean (a window where the two
    round differently); a higher-ranked source without a formed baseline
    loses to a lower-ranked one that has one, and wins back once formed;
    values of two sources never combined (a fixture where a combined median
    differs); a day with no formed baseline gives no evidence; the series
    reference names the chosen source.
  - **Mutations:** use the mean; pick the first source with a value that
    day; pool sources; `>=` → `>` on the minimum count.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_resting.py`
    green.
  - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.10, 7.3_
  - _Boundary: RestingEvidence_

- [ ] 2.6 (P) Turn evidence and hand-recorded entries into derived entries and takeovers (the write-time rule)
  - Implement design § Timeline: a hand entry's measurement date supplies no
    evidence and ends any run; the value in force on each evidence day is
    today's unchanged selection over the hand entries and the derived entries
    already decided for earlier days (a hand entry measured on or before the
    day, a hand entry reaching back by its `applies_from` where no earlier
    entry covers the day, or a derived entry); no value in force starts an
    entry; agreement within the step ends the run; disagreement grows a run
    of consecutive calendar days of one source under one entry in force, and
    the run's first day starts an entry when the confirmation count is
    reached; entries carry derived provenance, no applies-from date, and the
    takeover note (with the back-reach wording when the superseded entry is
    measured after the start day) or the ordinary note.
  - Uses the existing `BenchmarkSet.applicable`; changes nothing outside
    `timeline.py`.
  - **Tests**: first entry immediate; agreeing evidence never starts an
    entry; after a hand date, evidence is compared with the hand value and a
    takeover carries its note; evidence on the hand date ignored; evidence
    before a hand date with an earlier `applies_from` is compared with the
    back-reach value until the first derived entry, then with that entry,
    and a disagreeing day there produces a back-reach takeover with the
    back-reach note; 13 vs 14 confirmation days; a gap day, an agreeing day
    and a source change each end the run; the entry is dated on the run's
    first day with that day's value; a new hand value later in time makes
    the derived entries after it follow the new value on recompute; a
    derived value below a threshold is never clamped; no evidence gives no
    entry; appending evidence after a day never changes the entries already
    decided before it.
  - **Mutations:** `<=` → `<` on the step; drop the hand-date exclusion (a
    derived entry then collides with the hand key); compare with the hand
    value even where a derived entry is in force; date the entry on the
    run's last day; let a source change keep the run; a two-pass walk that
    selects over the walk's final entries instead of those decided for
    earlier days (the first-entry and confirmation cases red).
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_timeline.py`
    green.
  - _Requirements: 2.7, 2.8, 4.2, 4.3, 4.4, 4.5, 4.10, 4.11, 5.1, 5.2, 5.3, 5.4, 5.5, 5.8, 6.2, 6.5, 7.1, 9.6_
  - _Boundary: Timeline_

- [ ] 2.7 Detect takeovers, back-reach cover and inconsistencies over any benchmark set
  - Implement design § Inspect: structural takeovers of the two heart-rate
    kinds (with the derived entry set aside, the entry selected on its date
    is hand-recorded, back-reach included), the current ones (derived entry
    is the latest of its kind), each hand entry's back-reach cover as one
    interval, and inconsistency periods (maximum not above resting;
    threshold outside the reserve per recorded discipline, only when the
    maximum is above resting), each only when a derived resting or maximum
    value is involved, merged and sorted.
  - **Tests**: structural takeovers equal the timeline's takeovers on
    generated timelines, back-reach takeovers included; a later hand entry
    and a later derived entry each end the current listing; the cover of a
    hand entry ends at the first derived entry and is empty when a derived
    entry precedes its `applies_from`; two back-reaching hand entries split
    the days by earliest measurement; a hand-only inconsistency is not
    reported; period boundaries and merging; two disciplines with different
    thresholds.
  - **Mutations:** report every takeover as current; look at the day before
    instead of the entry's own date with it set aside (a hand back-reach
    starting on the derived date reds); report hand-only inconsistencies;
    borrow a threshold across disciplines.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_inspect.py`
    green.
  - _Requirements: 5.7, 6.3, 6.4, 9.1, 9.2_

- [ ]* 2.8 (controller- or maintainer-run, needs the network) Record the published works that corroborate the constants
  - Not an implementer task. When run, identify and read the works the brief
    names (Ausland, Kelemen & Seiler 2026 on age-formula error; the 2002
    field-versus-laboratory peak heart-rate study recommending a median of
    several maximal efforts) and the standard references design § HrSources
    lists as candidates; record each as a corroboration of the constant it
    speaks to, with locator and agreement, at the verification status
    actually achieved.
  - **Default when not run: record nothing.** Req 7.6 is met by the
    fitdocs-choice records alone; nothing downstream depends on this task.
  - A work not read is recorded as secondary attestation and named in the
    tracked exception set with what reading would resolve, or not recorded
    at all; no work governs a constant.
  - **Tests**: every corroboration names a constant that exists; every
    secondary-attestation record is in the tracked set and vice versa; no
    corroboration is the governing record of its constant.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_sources.py`
    green; Implementation Notes list each work and the status reached.
  - _Requirements: 7.6_

- [ ] 3. The stage, `check` and the command

- [ ] 3.1 Load the stage's settings and its resting-heart-rate evidence from the wellness series
  - Verify the upstream names listed under Upstream Prerequisites first.
  - Create the engine with the stage settings and their loader (the
    resting-heart-rate precedence through `effective_order`; the whole
    `[load]` settings through the `[load]` reader, kept so the CLI can hand
    them to the tagged-effort stage; the peaks use their flags) and the
    series step of design § HrStageEngine: read the series through the
    facade, per-source day values of resting heart rate, the year-file
    document function from the layout helper, the resting evidence; an
    unreadable series is a failure that keeps the resting partition.
  - Add the engine to the licensed callers of the `[load]` reader.
  - **Tests** (tmp data root; series staged only through
    `tests/wellness/builders_series.py::write_series`): a malformed
    `[wellness]` table and a malformed `[load.flags]` table each raise the
    settings error; an absent series and a series with no
    `resting_hr_bpm` value each give no evidence and the empty-series signal
    (not a failure); an unreadable manifest gives a failure naming
    `wellness/manifest.toml` and no exception; configured precedence changes the chosen source; the document
    of an entry dated in a given year is that year's series file.
  - **Mutations:** ignore the configured precedence (use the default order);
    turn the unreadable series into an empty one; report an empty series as
    a failure; drop the licensed-caller entry (the guard reds).
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_engine.py
    tests/load/test_settings.py` green.
  - _Requirements: 1.8, 1.9, 2.1, 2.9_
  - _Depends: 2.5_

- [ ] 3.2 Collect maximum-heart-rate evidence from every workout document
  - The workout step of design § HrStageEngine: sorted discovery, one
    frontmatter read per page through the contract, undated pages, the load
    pass's archive-resolution rule restated, composition of the listed
    files, missing and undecodable archives as reported skips, an
    unreadable archive as a failure that keeps the maximum partition, peaks
    per session with their no-evidence reasons, and progress after each page.
  - Register the engine in the contract-consumer registry; extend the
    archive-resolver agreement test to the three resolvers (load pass,
    tagged-effort stage, this engine), including a traversal-shaped ref.
  - **Tests** (tmp data root, FIT files from `tests/fixtures/builder.py`):
    counts per no-evidence reason with one page of each kind; the skipped
    list names missing and undecodable archives; an unreadable archive
    (permission removed; skipped when running as root) gives a failure and
    no exception; a page that lists an extra composes it (only the extra
    carries heart rate, and its peak is found); a non-workout markdown file
    is not considered.
  - **Mutations:** parse only the base file (the extra case reds); treat an
    undecodable archive as a failure; count a non-workout page.
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_engine.py
    tests/test_contract_consumers.py tests/performance/test_engine.py` green.
  - _Requirements: 1.7, 3.1, 3.5, 3.9, 3.10_
  - _Depends: 2.3, 2.4_

- [ ] 3.3 Reconcile, write the heart-rate partition once, and report
  - Complete design § HrStageEngine: load the profile once after the
    evidence; hand-recorded entries per kind; the timeline per kind, or the
    kind's entries on file when its evidence failed or, for resting heart
    rate, when the series is absent or holds no resting value (with the
    report's note); the partitioned write
    only when the heart-rate partition changed and never under preview;
    takeovers new to this run; back-reach changes (hand entries whose cover
    differs between the profile before and after the run); inconsistencies
    over the timeline both stages leave (the tagged-effort stage's accepted
    set substituted when given); resting sources; the changed flag; the
    facade's re-exports.
  - **Tests**: a run writes resting and maximum entries with full
    provenance; a second run writes nothing (bytes and mtime) and reports no
    takeover and no back-reach change; preview writes nothing and returns a
    report equal to the writing run's; a hand entry whose back-reach covers
    the corpus yields derived entries dated before its measurement date that
    apply on their own dates, one back-reach takeover, one back-reach change
    from the full span to the days before the first derived entry, and a
    takeover after its date only when later evidence disagrees; a failure
    keeps that kind's entries byte-equivalent while the other kind updates;
    with derived resting entries on file, an absent series and a series with
    no resting values each keep them byte-equivalent, report the note, record
    no failure and exit the stage successfully;
    the accepted-set substitution changes the inconsistency list in preview;
    no flat top-level key is written; no file but `athlete.toml` changes.
  - **Mutations:** write even when unchanged; write under preview; report
    every takeover rather than new ones; report the back-reach change on
    every run; ignore the kept-partition rule; remove the resting partition
    on an empty series.
  - **Observable:** `uv run pytest tests/hr_benchmarks` green.
  - _Requirements: 1.2, 1.3, 1.4, 1.10, 2.8, 4.6, 4.7, 4.9, 5.7, 5.8, 6.1, 8.2, 8.3, 9.3, 10.4, 10.6_
  - _Depends: 1.2, 2.6, 2.7, 3.1, 3.2_

- [ ] 3.4 (P) Report heart-rate benchmark findings in `fitdocs check`
  - Implement design § AuditHeartRate: `check` reads `athlete.toml`; an
    unreadable profile is one finding and the other checks still run;
    current takeovers and inconsistency periods become findings with the
    design's details and remedies; nothing else is opened.
  - **Tests**: takeover finding text names kind, values, dates and
    evidence; it disappears after a later hand entry and after a later
    derived entry; a profile holding a back-reach takeover gives no takeover
    finding, because the hand entry it took over is a later entry of the
    kind by construction (controller ruling R4); an inconsistency finding per
    period; an
    unreadable or newer-schema profile gives one finding while a document
    finding is still reported; absent `athlete.toml` gives none; `check`
    exits 1 with a finding and 0 without; no archive or wellness path is
    opened (access recorder).
  - **Mutations:** list every takeover, not only the current one; let a
    profile error abort the scan; drop the inconsistency findings.
  - **Observable:** `uv run pytest tests/test_audit.py tests/test_cli_check.py`
    green.
  - _Requirements: 6.3, 6.4, 9.1, 9.2, 9.4, 9.5_
  - _Boundary: AuditHeartRate_
  - _Depends: 2.7_

- [ ] 3.5 Run both stages from `derive-benchmarks` and print the heart-rate report
  - Implement design § DeriveCommand: the settings preflight before either
    stage (`[wellness]` and `[load]` read once); the tagged-effort stage
    with the preflight's load settings; the heart-rate stage with the
    tagged stage's accepted set; the heart-rate table, the `Heart-rate
    benchmarks written` line, takeovers, back-reach changes,
    inconsistencies, skipped documents, failures and the recompute hint;
    progress on stderr only on a terminal; exit 1 on a failure of either
    stage, 2 on a configuration fault. Update the `check` command's
    docstring (it now reads `athlete.toml`).
  - **Existing tests this touches:**
    - `tests/load/test_settings.py:2478-2483` (exactly one `[load]` read per
      `derive-benchmarks` run) must stay green unchanged; it is the proof
      that the preflight's settings reached the tagged-effort stage.
    - `tests/test_cli_derive.py:1388` asserts `perturbed_calls == [1]`; the
      heart-rate stage also globs `workouts/*.md`, so it becomes `[1, 1]`.
      State that reason in the assertion message.
    - `test_mixed_run_derives_declines_fails_and_never_opens_the_untagged_archive`
      is re-scoped to the tagged-effort stage: a monkeypatched wrapper on
      `fitdocs.cli.derive_hr_benchmarks` snapshots the recorded archive
      accesses when the heart-rate stage starts, and the assertion runs over
      that snapshot; the wrapper then calls the real stage.
  - **New tests**: both tables printed with pairwise-distinct counts; the
    takeover line; the back-reach change line printed once and absent on a
    rerun; the recompute hint only when the timeline changed; the existing
    `Profile written` pins unchanged; a malformed `[wellness]` table exits 2
    with `athlete.toml` untouched; a heart-rate failure exits 1; progress
    absent from stdout.
  - **Mutations:** read the settings after the tagged stage writes (the
    preflight case reds); do not pass the load settings (the one-read test
    reds); print the recompute hint always; drop the heart-rate failures
    from the exit rule.
  - **Observable:** `uv run pytest tests/test_cli_derive.py
    tests/load/test_settings.py` green.
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.8, 1.11, 5.7, 6.1, 10.4_
  - _Depends: 3.3_

- [ ] 4. Guards, the contract version, documentation and the skill

- [ ] 4.1 Pin the package's reach: module list, single writer, reachability, public surface and confinement
  - Add the literal module list to the boundary guard; assert the stage's
    entry point is imported only by `cli.py` and `inspect` only by `audit.py`
    and the package; assert no module of `fitdocs.load`, `fitdocs.performance`,
    `fitdocs.wellness` or `fitdocs.index` imports `fitdocs.hr_benchmarks`;
    pin the facade in the public API test; register a
    `derive-benchmarks-heart-rate` writing entry point whose non-vacuous
    check is that only `athlete.toml` changed; assert no settings key names a
    constant (the engine reads only the precedence and the `[load]`
    settings).
  - **Positive controls** and synthetic violators for each scan.
  - **Mutations:** skip `engine.py` in the walk (the module-list pin reds);
    import the stage from `sync.py` (single writer reds); import
    `hr_benchmarks` from a channel module (reachability reds); write a stray
    file from the stage (confinement reds).
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_boundary.py
    tests/test_public_api.py tests/test_confinement.py` green.
  - _Requirements: 1.6, 1.9, 1.10, 3.8, 5.9, 10.1, 10.5, 10.6_

- [ ] 4.2 Raise `CONTRACT_VERSION` for the changed `derive-benchmarks` guarantee (wiki-contract amendment)
  - `CONTRACT_VERSION` = main + 1 with a history paragraph beginning
    "Raised from ``N`` to ``N+1`` by hr-derivation" and stating, in one
    sentence, that `derive-benchmarks` now also reads every workout's listed
    files and the wellness series and may write `athlete.toml` once per
    stage; `docs/ownership-contract.md` version line and a new "What changed
    at this version" paragraph (the same facts, plus "recompute load to
    apply a changed heart-rate timeline"); regenerate every declaration
    golden with the goldens module's regeneration entry point.
  - Append the wiki-contract amendment record.
  - **Pins that move:** every hard-coded contract-version literal
    (`tests/test_contract.py`, `tests/test_ownership_contract.py`,
    `tests/test_declaration*.py`, `tests/index/test_contract_docs.py`,
    `tests/index/derived/test_preserved.py`,
    `tests/compose/test_contract_docs.py`); the "What changed at this version"
    head-paragraph pin at `tests/identity/test_contract_docs.py:177-187`
    and every peer head-paragraph pin present at landing (dashboards,
    wellness-store, wellness-pull, recovery, workout-wellness), each moved to
    the new head or
    retired the way its own spec retired its predecessor's (find them by
    grepping the outgoing "What changed at this version" paragraph's
    phrases); and a LITERAL pin on the history paragraph's content, appended
    to `test_the_version_history_records_the_amendment`: "Raised from ``N``
    to ``N+1`` by hr-derivation" with the landed numbers written as literals
    (5.2 rewrites them if the rebase moves main), plus the sentence. Never
    compute the pin from the live `CONTRACT_VERSION`; the existing
    `_contract_version_history` helper fails only when no docstring is
    adjacent, so only a literal content pin catches a dropped paragraph.
  - **Mutations:** leave `CONTRACT_VERSION` at main's value; drop the new
    history paragraph's hr-derivation sentence (the content pin reds); leave
    one golden un-regenerated.
  - **Observable:** full `uv run pytest` green; a sync in a scratch data root
    writes declarations whose version line equals the new constant.
  - _Requirements: 11.2_
  - _Depends: 3.5_

- [ ] 4.3 Document the heart-rate stage, the write-time hand rule, the back-reach consequence and the takeover
  - README benchmarks section; `docs/configuration.md` athlete-profile
    section with a "Derived heart-rate benchmarks" subsection (evidence,
    windows, steps, the write-time hand rule, selection unchanged, how
    derived entries narrow a hand entry's back-reach and that historic load
    before a hand date moves once load is recomputed, takeovers, how long
    `check` lists one and that a back-reach takeover is announced by the run
    and the timeline only, never by `check`, how to answer, the recompute
    step, runtime);
    `docs/ownership-contract.md`'s `derive-benchmarks` operation and
    `athlete.toml` paragraph (reads every workout's composed activity and the
    wellness series; at most one write per stage; never modifies a
    hand-recorded entry); `.kiro/steering/structure.md` dependency bullet
    for `hr_benchmarks`.
  - The index column description: in `src/fitdocs/index/derived/benchmarks.py`
    the `source_page` description becomes "Data-root-relative page or
    wellness series file used to derive the entry; NULL when not recorded."
    Descriptions are outside the schema digest (`index/schema.py:243-265`),
    so `SCHEMA_VERSION` does not move. Re-pin the literal at
    `tests/index/derived/test_benchmark_producer.py:121-125` and regenerate
    the `docs/analytics.md` block with
    `uv run python -m tests.query.test_docs_analytics`.
  - Synthetic numbers only.
  - **Tests**: existing doc pins re-run; any phrase pin that moves is
    updated in the same commit; `tests/hr_benchmarks/test_docs.py` pins the
    two steps, the confirmation days and the `check` listing rule in the
    configuration guide against the constants.
  - **Mutations:** change a step constant (the doc pin reds); revert the
    `source_page` description (the producer pin and the docs regeneration
    test red).
  - **Observable:** `uv run pytest tests/test_docs_guarantees.py
    tests/test_ownership_contract.py tests/hr_benchmarks
    tests/index/derived/test_benchmark_producer.py
    tests/query/test_docs_analytics.py` green.
  - _Requirements: 11.1, 11.2, 11.3, 11.6_
  - _Depends: 4.2_

- [ ] 4.4 Teach the workouts skill the new findings and record the release notes
  - The workouts skill: how to read `hr_benchmark_takeover`,
    `hr_benchmark_inconsistent` and `athlete_profile_unreadable`; relay a
    takeover to the athlete and never answer it; never run
    `load --recompute` unasked.
  - CHANGELOG Unreleased, naming the governed contracts per the file's
    convention: the heart-rate stage; the `series` provenance key; the three
    `check` findings; the heart-rate channel's two dated inputs; the
    ownership contract's new version (action: run `fitdocs sync` or `regen`
    once to refresh the declarations); and the one-time consequence that on
    the first run historic heart-rate load before a hand-recorded entry's
    date moves to derived values where derived evidence exists, applied by
    `fitdocs load --recompute`.
  - **Tests**: the skill tests' pinned findings list extended; the
    changelog test passes; a test pins the historic-load sentence in the
    Unreleased entry.
  - **Mutations:** drop a finding name from the skill (its pin reds); drop
    the historic-load sentence (its pin reds).
  - **Observable:** `uv run pytest tests/test_agent_skill.py
    tests/test_changelog.py tests/test_skill_wheel.py` green.
  - _Requirements: 11.4, 11.5, 11.6_
  - _Depends: 3.4_

- [ ] 5. Validation

- [ ] 5.1 Prove the whole flow end to end, deterministic and non-erasing
  - A CLI end-to-end run over a staged data root: first create the workout
    pages (heart rate, a tagged race) with `fitdocs sync`, then write the
    hand-recorded maximum (with an `applies_from` before every workout) and
    run threshold into `athlete.toml`, then stage a two-source series with
    `write_series`; run no `sync` or `regen` after staging (a drain would
    rebuild the staged series away). Both stages report; the
    back-reach takeover and the back-reach change are printed once; a
    takeover after the hand date is printed when later evidence disagrees;
    `fitdocs check` lists the current takeover; a later hand value ends the
    listing; `fitdocs load --recompute` then scores a walk dated before the
    hand date with the derived maximum and reports both dates.
  - Determinism: reversed discovery order, a pinned non-system time zone and
    a perturbed locale give byte-identical profiles; a second run is a byte
    and mtime no-op.
  - Non-erasure: tagged then heart-rate and heart-rate then tagged runs leave
    each other's entries byte-equivalent.
  - **Mutations:** sort sessions by discovery order only (reversed glob
    reds); revert 1.2's partitioned change test (the second-run no-op reds).
  - **Observable:** `uv run pytest tests/hr_benchmarks/test_e2e.py
    tests/hr_benchmarks/test_determinism.py` green.
  - _Requirements: 1.4, 4.7, 4.9, 5.5, 5.6, 5.7, 6.1, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 10.1, 10.2_

- [ ] 5.2 Land: rebase, contract version, full validation, follow-ups
  - Rebase onto `main`; keep both sides of every append-only list;
    re-derive `CONTRACT_VERSION` as main + 1 and every amendment number;
    write the landed numbers as literals into the history-paragraph content
    pin (append-only, never `{v-1}`/`{v}` from the live constant) and re-pin
    every peer head-paragraph pin now on main;
    confirm no other version constant moved and `BenchmarkSet.applicable`
    is unchanged; full `uv run pytest`, `ruff check`, `ruff format --check`,
    `mypy`; check the branch CI before merging;
    `/kiro-spec-status hr-derivation` clean.
  - File a `.kiro/queue/` item for a per-session peak cache: the stage runs
    only inside `derive-benchmarks` (`cli.py` is its one caller) and re-parses
    every archive on each run, measured at about 84 ms per document (216 s
    for 2,564 documents on the maintainer's corpus); include the resume
    command and context paths.
  - **Observable:** full suite green after the rebase; the amendment records
    and the history paragraph carry the numbers free at landing; the queue
    item exists.
  - _Requirements: 1.6, 4.7, 7.5, 10.5, 11.2_

- [ ]* 5.3 (maintainer-only) Dry-run on a scratch copy of the real data root
  - `fitdocs derive-benchmarks --dry-run --out <scratch copy>`: compare the
    entry counts per kind, the takeover count and the back-reach change with
    design § Performance's expectation, and record counts and runtime only
    in Implementation Notes; no value enters the repository.
  - _Requirements: 4.1, 4.7_

## Implementation Notes

- 1.1: Optional provenance `series` is trailing in `BenchmarkSource` but emitted after `document`; construct sources with keyword arguments. Independent review approved after closing the distinct truthy wrong-type setter guard (numeric and bool fixtures keep the empty-string boundary). All 28 claimed mutations, two new reviewer mutations and 32 historical prose checks red/restored green; full suite 14,798 passed / 44 skipped; controller fresh 65 provenance cases passed. Selection and athlete schema unchanged.

- 1.2: Required `kinds` partitions the derived writer; tagged-effort uses `TAGGED_EFFORT_KINDS` and exposes trailing `accepted`, with optional pre-read `load_settings`. Other-partition retention fixtures need a hand entry in the same raw group so passthrough cannot mask missing derived retention. The cleanup filter alone is behavior preserving because retained groups stay covered; tests pin actual removal and raw empty-group preservation, not helper counts. Independent review: 51 faulty mutations red, one declared redundant mutation green, three own faults red/restored; full 14,818 passed / 44 skipped; controller 1,798 passed. Existing collision-test mechanism prose follow-up queued as 2026-10-14-collision-test-overwrite-explanation.
