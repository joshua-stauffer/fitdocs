# Implementation Plan

## Upstream Prerequisites

- **`wellness-store` must be on `main` first.** This plan consumes its
  package `fitdocs.wellness` (model, probe, spec, registry, archive, intake,
  engine, merge, series), its CLI progress printer and drain report rows, and
  its frozen test helpers in `tests/wellness/_helpers.py` and
  `tests/wellness/conftest.py` (data-root factory, counting file opener,
  `use_formats`, the test-only `ORIGINAL` and `EXTRACT`/`LATEST_ENTRY`
  formats, `tree_snapshot`, `assert_untouched`). Branch from the `main` that
  holds wellness-store's merge; cite its code by content, not line number.
- **No version constant moves.** This spec adds no owned location, page type,
  frontmatter key or index table: `CONTRACT_VERSION`, `DOC_VERSION` and the
  index `SCHEMA_VERSION` stay as main has them.
- **No upstream amendment is carried by this plan.** The controller folded
  this spec's upstream needs into `wellness-store`'s own spec (design §
  Upstream Behaviour Consumed). **Verify before building** — each must exist
  on `main` before the task that consumes it starts, else stop and report:
  - `archive.read_entry_order(entry)` and `rebuild_series` parsing only the
    greatest `(order, ref)` entry of a `LATEST_ENTRY` format; the test-only
    `EXTRACT` format's `entry_order` reads its header only (4.1, 4.2);
  - `commit_extract`: an extractor `WellnessFormatError` → `Invalid` (failed,
    quarantined); an extractor `OSError` → `Unreadable` (deferred); the
    `.incoming-*` temp file removed on `KeyboardInterrupt`; the original
    re-hashed before an extractor error is classified, so a file changed or
    truncated mid-read is deferred, not quarantined (4.2);
  - the counting opener's read rule: a read requests at most `CHUNK_BYTES`,
    or is `zipfile`'s end-record read beginning within `ZIP_MAX_COMMENT + 22`
    bytes of end of file (`zipfile._EndRecData`), or `zipfile`'s central-directory read of exactly the size the end record states (one read, which may exceed `CHUNK_BYTES`; `ZipFile._RealGetContents`) (3.1, 4.1, 4.2).
  - Not a stop condition: `wellness-store`'s gapped ranks between `spec` and
    `registry` in `tests/wellness/test_boundary.py`; 1.1 uses tuple ranks if
    no gap exists and never renumbers.
  - `sync.drain(..., wellness_progress=...)` forwarding `(rel, read, total)`
    (4.2).
- **Phase 12 peers** (`wellness-pull`, `hr-derivation`, `recovery`) may land
  in any order. Keep both sides on rebase of: `registry.SOURCES` /
  `FORMATS`, the rank table and module list of
  `tests/wellness/test_boundary.py`, every pin of `candidate_suffixes()` /
  `default_source_order()`, `docs/wellness.md` sections, `docs/inbox.md`,
  `docs/configuration.md`, `src/fitdocs/skills/fitdocs-workouts/SKILL.md`,
  `tests/test_agent_skill.py`, and `CHANGELOG.md` Unreleased.

**Hard rules for every task**

- **Absent is `None`.** A day without a qualifying record has no value; every
  value passes `accept_value`; nothing substitutes zero or a default.
- **No clock, no machine timezone, no network.** No `date.today`,
  `datetime.now`, `time.*`, argument-less `astimezone()`, `urllib`,
  `socket`, `http` in `fitdocs.wellness.formats.apple`; `wellness-store`'s
  boundary guard enforces it once the modules are in its rank table (1.1).
- **Imports follow design § Allowed Dependencies**: `records`, `sleep` →
  `defects` → `reader`, `extract` → `reduce` → package `__init__`; only the
  standard library, `fitdocs.wellness.model`, `fitdocs.wellness.spec` and
  `fitdocs.wellness.probe`.
- **Synthetic data only.** Exports come from `tests/wellness/apple/builders.py`
  with invented writers ("Example Apple Watch", "Example iPhone", "Example
  Sleep App", "Example Scale"), invented values and dates; no maintainer
  value, device name or file name enters the repository.
- **Stream, never slurp.** Every read of a candidate or of the main export
  document requests at most `CHUNK_BYTES`, except `zipfile`'s end-record read
  beginning within `ZIP_MAX_COMMENT + 22` bytes of end of file (Python
  3.11's `zipfile._EndRecData` reads that tail without a size) and
  `zipfile`'s central-directory read of exactly the size the end record
  states (one read, which may exceed `CHUNK_BYTES`;
  `ZipFile._RealGetContents`); tests assert exactly this rule, with a positive control that reads of the candidate were
  observed. The export is read once, by the extractor.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination): each named mutation applied, observed red,
  reverted by restoring a `cp` taken before it, observed green, and recorded
  in Implementation Notes; a mutation that cannot be made red is reported
  UNPINNED. Run the prose-claim grep over changed test files before
  submitting.
- **Fixtures discriminate.** Pairwise-distinct values wherever a mapping or a
  choice is asserted; the record that must win is never first in document
  order; timing order and value order disagree; an asserted end state shown
  false beforehand; "nothing written" asserted on bytes and `st_mtime_ns`.
- **Parallel streams.** `(P)` tasks run in separate worktrees and touch only
  their `_Boundary_` module and test file. `tests/wellness/apple/builders.py`
  is created by 1.2 and frozen afterwards: a later task that needs another
  helper defines it locally in its own test module.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in the
  same worktree** (`tests/test_bytecode_hygiene.py`).
- **Linux-CI portable.** `tmp_path` only; child processes get
  `{**os.environ, …}`; permission tests skip as root.
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`, `git
  clean` or `git checkout -- <path>`; never chain a destructive command after
  `cd`.
- **Types and lint.** Each task runs `uv run mypy`, `uv run ruff check` and
  `uv run ruff format --check`.
- **Stop and report** on any need for: a runtime dependency; a new metric or
  unit; a change to a `wellness-store` source module beyond the registry
  append (4.1); a change to `wellness-store` tests beyond the boundary-guard
  rows (1.1) and the registry-consequence re-pins (4.1); a missing upstream
  behaviour from the verify-before-building list; reading the export more
  than once; any write that does not go through `wellness-store`'s commit
  protocol.

## Shared source files

- `src/fitdocs/wellness/formats/apple/__init__.py`: 1.1 creates it
  docstring-only; 4.1 fills it.
- `src/fitdocs/wellness/formats/apple/{defects,sleep,reader,extract,reduce}.py`:
  1.1 creates each docstring-only; exactly one task fills each (2.1, 2.2,
  3.1, 2.3, 2.4 then 3.2).
- `src/fitdocs/wellness/formats/apple/reduce.py`: 2.4, then 3.2.
- `tests/wellness/test_boundary.py`: 1.1 only (rank rows and module list for
  all seven modules at once, inserted into the gapped ranks, or as tuple
  ranks if none exists; never renumbered).
- `tests/wellness/apple/builders.py`: 1.2 only.

## Test File Ownership

All paths below are under `tests/wellness/apple/` unless written in full;
`wellness-store` owns `tests/wellness/test_e2e.py` and
`tests/wellness/test_determinism.py`, which this plan never edits except the
4.1 registry-consequence re-pins.

- `__init__.py`, `test_records.py`, and the rank rows in
  `tests/wellness/test_boundary.py`: **1.1**.
- `builders.py`, `test_builders.py`: **1.2**.
- `test_defects.py`: **2.1**. `test_sleep.py`: **2.2**. `test_extract.py`:
  **2.3**. `test_reduce.py`: **2.4**.
- `test_reader.py`: **3.1**. `test_reduce_nights.py`: **3.2**.
- `test_format.py` and the registry-consequence re-pins in `wellness-store`'s
  tests (`tests/wellness/test_registry.py`,
  `tests/wellness/test_registered_formats.py`,
  `tests/wellness/test_engine.py`, `tests/wellness/test_drain_wellness.py`,
  `tests/wellness/test_e2e.py`, wherever a literal moves): **4.1**.
- `test_import.py`, `test_e2e.py`: **4.2**.
- `test_docs_apple.py`: **5.1**.
- `test_determinism.py`: **6.1**.

---

- [x] 1. Foundation: package scaffold, record types, synthetic exports

- [x] 1.1 Scaffold the Apple Health format package and its record types
  - Create `fitdocs.wellness.formats.apple` with all seven modules of design §
    File Structure Plan; every module but `records` is docstring-only for
    now.
  - **`records.py`** per design § Records: `AppleType` (the eight
    identifiers), `SleepState` (the seven values, the deprecated "asleep"
    included), `RECORD_ATTRIBUTES`, `RawRecord`, `ExportDate`,
    `Corrections`, `ExportItem`, `normalize_device`.
  - **Boundary guard**: add the seven modules to the rank table of
    `tests/wellness/test_boundary.py` in the internal order of design §
    Allowed Dependencies, inserted into the gapped ranks `wellness-store`
    leaves between `spec` and `registry` (if no gap exists, use tuple ranks
    such as `(spec_rank, 1)`; never renumber an existing row), and to its
    literal module-list pin; the guard then enforces imports, clock and
    network for the package.
  - **Tests** (`tests/wellness/apple/test_records.py`): `normalize_device`
    strips `<<HKDevice: 0x1a2b3c>, ` and the trailing `>` from a watch
    description; leaves text without the prefix, and a prefix with a non-hex
    address, unchanged; `AppleType` equals a test-local literal of the eight
    identifiers; `SleepState` holds the deprecated value.
  - **Mutations:** keep the address in `normalize_device`; drop the trailing
    `>` removal; omit `SleepState.ASLEEP`; drop one apple module's row from
    the rank table (the guard reds).
  - **Observable:** `uv run pytest tests/wellness/test_boundary.py
    tests/wellness/apple` green with the seven modules visited.
  - _Requirements: 5.1, 7.1, 10.6, 14.1, 14.2_

- [x] 1.2 Build synthetic Apple Health exports for every later test
  - `tests/wellness/apple/builders.py`: an export-document builder (XML
    declaration, a DTD shaped like Apple's, `HealthData` with `ExportDate`, a
    `Me` carrying an invented date of birth, records of the eight read types
    and of unread types such as heart rate, a `Workout` with
    `WorkoutStatistics`, a `Correlation` with a nested record, an
    `ActivitySummary`); writer presets (Apple Watch and iPhone device
    descriptions with distinct hex addresses, a sleep app and a scale with no
    or other devices); record helpers taking times with explicit offsets;
    switches injecting each of the three defects (a malformed internal
    subset, a `\x0b` inside a `sourceName`, a doubled `startDate` on
    `WorkoutStatistics`); a bulk generator of N unread heart-rate records;
    zip packaging (deflate, `force_zip64`, the English path, a translated
    main document with its `_cda` companion, a `__MACOSX` copy, a Garmin-like
    zip, an ambiguous zip with two companion pairs).
  - **Tests** (`tests/wellness/apple/test_builders.py`, positive controls for
    the fixtures):
    a clean built document parses with stdlib `iterparse` and holds the
    expected element counts; each defect switch, alone, makes stdlib
    `iterparse` fail with expat's message for that defect; a ZIP64 zip's
    local header carries sizes `0xFFFFFFFF` and extra id `0x0001`.
  - **Mutations:** make a defect switch a no-op (its positive control reds);
    drop `force_zip64` (the header check reds).
  - **Observable:** `uv run pytest tests/wellness/apple/test_builders.py`
    green; builders frozen from here on.
  - _Requirements: 14.4_

- [x] 2. Core: defect filter, sleep sweep, extract codec, daily rules

- [x] 2.1 (P) Repair the three known export defects in the byte stream
  - `defects.py` per design § DefectFilter: `CONTROL_BYTES`,
    `PROLOG_LIMIT`, `MAX_TAG_BYTES`, `CHUNK_BYTES`, `DefectFilter` with
    `read` and `corrections`.
  - **Tests** (`test_defects.py`, builders' documents, `chunk_bytes=7` so the
    DOCTYPE, a control byte and a `WorkoutStatistics` tag straddle reads):
    each defect alone and all three together produce a stream stdlib
    `iterparse` accepts; a clean document passes byte-identical with zero
    corrections; line count before and after equal; corrections exact (one
    DOCTYPE, three control bytes, two repeated attributes); the first
    `startDate` survives; a repeated attribute on a `Record` is left alone;
    a document with no `HealthData` start tag within the (patched small)
    limit raises naming the limit; a `WorkoutStatistics` tag longer than
    `MAX_TAG_BYTES` raises; `read` never returns `b""` before end of input;
    upstream read only in `chunk_bytes` pieces (counting wrapper).
  - **Mutations:** delete control bytes without counting; keep the last
    occurrence of a repeated attribute; replace the DOCTYPE with nothing
    instead of its line breaks; drop the carry of a split tag; strip `\t`.
  - **Observable:** `uv run pytest tests/wellness/apple/test_defects.py`
    green.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_
  - _Boundary: DefectFilter_

- [x] 2.2 (P) Count a night's sleep once per instant under the most specific stage
  - `sleep.py` per design § Sleep: `Stage`, `Segment`, `NightTotals`,
    `night_totals`, `asleep_intervals`.
  - **Tests** (`test_sleep.py`, pairwise-distinct stage durations): two
    overlapping core segments counted once; a deep segment inside a core
    segment counted as deep and removed from core; REM over core, core over
    awake, awake over unspecified, each overlap counted once; segments given
    in shuffled order give equal totals; `staged` false for an
    unspecified-only night; `asleep_intervals` merges touching asleep
    segments, excludes awake, and is half-open; zero-length segments add
    nothing.
  - **Mutations:** sum durations without the sweep; swap REM and core
    priority; let awake win over deep; include awake in `asleep_intervals`.
  - **Observable:** `uv run pytest tests/wellness/apple/test_sleep.py` green.
  - _Requirements: 10.1, 10.2, 10.3_
  - _Boundary: Sleep_

- [x] 2.3 (P) Write and read the canonical extract
  - `extract.py` per design § ExtractCodec: `EXTRACT_FORMAT`,
    `EXTRACT_VERSION`, `READABLE_VERSIONS`, `ExtractHeader`,
    `export_date_utc`, `write_extract`, `read_header`, `read_records`.
  - **Tests** (`test_extract.py`, item streams built from `records` types):
    round trip of records with and without device, unit, creation date and
    metadata; header fields equal the given sha, size and export date, with
    `export_date_utc` for `-0800` and `+0530` offsets; two writes of the same
    items byte-identical; the gzip header has mtime 0, no FNAME flag, and the
    sink's file name appears nowhere in the bytes (sink is a named temp
    file); lines have sorted keys and compact separators; trailer count and
    corrections; `read_header` reads only the first line (counting wrapper
    over the decompressed stream); a record before the export date, an
    export with no export date, a trailer count mismatch, a missing trailer,
    a truncated gzip, an unknown key, a record type absent from the header
    and a version above `EXTRACT_VERSION` each raise `WellnessFormatError`
    naming the problem.
  - **Mutations:** omit `filename=""`; omit `mtime=0`; drop `sort_keys`; skip
    the trailer count check; accept a newer version.
  - **Observable:** `uv run pytest tests/wellness/apple/test_extract.py`
    green.
  - _Requirements: 3.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.9_
  - _Boundary: ExtractCodec_

- [x] 2.4 (P) Validate records, classify writers and compute the day values other than sleep and readings
  - `reduce.py` per design § Reduce, without the sleep nights and the
    asleep readings (3.2): `Writer`, `DayRule`, `DailyRule`, `TypePolicy`,
    `POLICIES` (all eight types, so 3.2 adds behaviour, not rows),
    `APPLE_ORIGIN`, `device_maker_model`, `writer_of`, `DayReducer`
    (validation, unit conversion, device evidence, FINAL, LARGEST_TOTAL,
    LATEST), `reduce_records`.
  - **Tests** (`test_reduce.py`, `RawRecord`s built directly, of the resting
    HR, VO2max, step and body-mass types only, so 3.2's sleep and reading
    rules never change these tests' expected snapshots):
    - writers: a deviceless resting-HR record of a writer whose other records
      name an Apple Watch is used; the same record from a writer with no
      Apple device evidence is not; an iPhone-only writer is `PHONE`.
    - resting HR and VO2max: final estimate where end order and value order
      disagree; equal ends resolved by the later creation, which is not first
      in input; a sleep app's resting HR excluded.
    - steps: iPhone total larger than the watch's wins; a sleep app's larger
      total excluded; two writers never summed; integral counts summed
      exactly.
    - weight: a scale app's latest measurement wins over an earlier iPhone
      entry; `lb`, `g` and `st` convert to kg rounded to 0.01; origin absent.
    - origins `apple` on every other metric; resting HR `0` absent through
      `accept_value`; a day with only excluded writers yields no snapshot.
    - validation: an unknown unit (names type and unit), a non-numeric and a
      `nan` value, a time without offset, an end before start, a missing
      `sourceName` each raise `WellnessFormatError` naming the type, the
      problem and the start time.
    - day rule `START_DATE`: a record starting 23:30 `-08:00` belongs to that
      local date, not the UTC date.
    - order independence: the same records shuffled three ways give equal
      snapshots.
  - **Mutations:** classify per record instead of per writer; allow `OTHER`
    for resting HR; sum steps across writers; `min` instead of `max` for the
    final estimate; drop the creation-date tie-break; drop `accept_value`;
    assign the UTC date instead of the local start date.
  - **Observable:** `uv run pytest tests/wellness/apple/test_reduce.py`
    green.
  - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.4, 9.5, 9.6, 9.7, 11.4, 12.1, 12.2_
  - _Boundary: Reduce_

- [x] 3. Core: the streaming reader and the night-based rules

- [x] 3.1 (P) Recognize exports and stream the main export document's items
  - `reader.py` per design § Reader: `MAIN_DOCUMENT`, `CDA_SUFFIX`,
    `main_member`, `looks_like_export_document`, `MainDocument`,
    `open_main_document`, `iter_items` (counting reader with the progress
    throttle, `DefectFilter`, `iterparse` with start and end events, root
    captured from the first start, depth tracking, `root.clear()` after each
    depth-1 element).
  - **Tests** (`test_reader.py`, builders' documents and zips):
    - `main_member` over the English zip, the translated zip with its
      companion, the `__MACOSX`-only zip, the Garmin-like zip and the
      ambiguous zip (one, one, none, none, none);
      `looks_like_export_document` true for the export and the defective
      export, false for a `ClinicalDocument` and a GPX.
    - items: export date first, then exactly the read-type records at depth
      one in document order with metadata kept and the HRV instantaneous-BPM
      list dropped, then corrections; the nested `Correlation` record, `Me`
      and the unread types never yielded; the invented date of birth absent
      from every item.
    - errors: a wrong root, an `ExportDate` after a read record, two
      `ExportDate`s, a fourth kind of malformation (an unclosed tag) naming
      its line equal to the line in the built document, a zip whose member
      CRC is corrupted, an unsupported compression method — each
      `WellnessFormatError`; a missing file raises `OSError`.
    - ZIP64: the forced-ZIP64 zip yields the same items as the plain zip.
    - progress: at most 101 calls, percents strictly increasing, the last
      call `(size, size)`; none with `progress=None`.
    - streaming: every read of the candidate a counting wrapper sees
      requests at most `CHUNK_BYTES`, or is `zipfile`'s end-record read within
      `ZIP_MAX_COMMENT + 22` bytes of end of file, or is `zipfile`'s
      central-directory read of exactly the size the end record states (one
      read, which may exceed `CHUNK_BYTES`), with a positive control
      that reads of the candidate were observed, for the zip and the bare
      document; `tracemalloc` peak while iterating a document of N bulk
      records and of 4N differs by less than 50 %.
  - **Mutations:** drop the depth check (the nested record appears); drop
    `root.clear()` (the 4N peak grows about fourfold); report progress on
    every read; accept a second `ExportDate`; match `export.xml` by English
    name only (the translated zip reds).
  - **Observable:** `uv run pytest tests/wellness/apple/test_reader.py`
    green.
  - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3, 2.4, 3.5, 5.6_
  - _Boundary: Reader_
  - _Depends: 2.1_

- [x] 3.2 (P) Assign sleep to nights and take HRV, respiration and SpO2 from the readings taken asleep
  - Complete `reduce.py` with the `SLEEP_NIGHT` and `ASLEEP_MEAN` rules
    (design § Reduce): segments grouped by `wellness_day_of_sleep_end` of
    their end; the night's device kind (watch, else iPhone); `night_totals`
    over the chosen segments; stage metrics only for a staged night; total
    absent at zero; readings located by `bisect` in the Apple Watch's
    `asleep_intervals`; mean via `math.fsum`, rounded to 0.1; SpO2 × 100.
  - **Tests** (`tests/wellness/apple/test_reduce_nights.py`):
    - a night with watch stages and iPhone in-bed: stages from the watch,
      in-bed ignored; a night with only iPhone asleep segments uses them; a
      watch night is never combined with the iPhone's longer segments; a
      sleep app's longer night excluded.
    - a pre-watchOS-9 night of unspecified asleep time: `sleep_s` only, no
      stage metrics; the deprecated "asleep" value counted as unspecified; a
      night of only awake and in-bed time: no sleep value.
    - day assignment: segments ending 17:59 and 18:00 local on the day before
      D, in `+09:00` and `-08:00`, land on four distinct expected days; a nap
      ending 15:00 on D counts toward D.
    - readings: HRV readings ending inside the asleep interval, at its start
      (included) and at its end (excluded); a reading at 23:00 inside the
      night window but while awake excluded; a reading from a sleep app
      excluded; no watch sleep → no HRV, respiration or SpO2 for that day;
      SpO2 `0.97` and `0.95` → `96`; means rounded to one decimal.
    - validation: an unknown `HKCategoryValueSleepAnalysis…` value raises
      `WellnessFormatError` naming the type, the problem and the
      `startDate`; a sleep record carrying an unexpected `unit` attribute is
      accepted and counted.
    - order independence over shuffled segments and readings.
  - **Mutations:** skip unknown sleep states instead of raising; choose the
    iPhone first; emit stage metrics for an
    unstaged night; use the calendar date of the end instead of
    `wellness_day_of_sleep_end`; include readings taken in the night window
    while awake; make the asleep interval end-inclusive; skip the SpO2
    factor.
  - **Observable:** `uv run pytest tests/wellness/apple` green.
  - _Requirements: 7.8, 8.1, 8.2, 9.2, 9.3, 10.4, 10.5, 10.7, 10.8, 11.1, 11.2, 11.3, 11.5_
  - _Boundary: Reduce_
  - _Depends: 2.2, 2.4_

- [x] 4. Integration: the format, its registration and imports through the drain

- [x] 4.1 Declare and register the Apple Health format
  - Fill `formats/apple/__init__.py` per design § AppleFormat: `FORMAT_ID`,
    `ARCHIVED_SUFFIX`, `RULES_VERSION`, `METRICS`, `SOURCE`, `FORMAT`,
    `recognize`, `extract`, `parse`, `entry_order`.
  - Append `apple.SOURCE` and `apple.FORMAT` to `wellness/registry.py`; re-pin
    in `wellness-store`'s tests, append-only, every exact value of
    `candidate_suffixes()` (`{".json", ".xml", ".zip"}`),
    `default_source_order()` (`("garmin-export", "apple-health",
    "intervals-icu")`), any count of `SOURCES`/`FORMATS`, and every literal
    manifest `[precedence] default` list and `inputs_digest` value in
    `tests/wellness/test_engine.py`, `tests/wellness/test_drain_wellness.py`
    and `tests/wellness/test_e2e.py` (the effective order per metric gains
    `apple-health`, so existing series go stale once); pins a grep misses
    surface in the full suite.
  - **Peer registry consumers:** where confirmed by full-suite failures,
    append Apple to source-order expectation tuples in
    `tests/hr_benchmarks/test_engine.py` and the matching source-order
    observation in `tests/test_cli_derive.py`; preserve every existing HR entry,
    fixture and behavior. These are source-registry consequence pins only.
  - **Integration compatibility:** correct only the codec module import in
    `tests/wellness/apple/test_extract.py` so the public callable
    `apple.extract` does not shadow the codec module used by its tests.
    Preserve all existing codec assertions and fixtures.
  - **Tests** (`test_format.py`): `validate_registry()` passes;
    `FORMAT.metrics` equals the union of `POLICIES` metrics; `recognize`
    through real `CandidateProbe`s claims the English zip, the translated
    zip, the forced-ZIP64 zip and the bare document (renamed `data.xml`),
    and rejects the Garmin-like zip, `export_cda.xml`, a GPX renamed `.xml`
    and the ambiguous zip, with the counting opener showing nothing read
    beyond the head and the central directory, every read obeying the
    stream rule of the hard rules (at most `CHUNK_BYTES`, the end-record read,
    or the central-directory read of exactly its stated size), and a positive
    control that reads of the candidate were observed; `extract` into a sink then
    `parse` and `entry_order` over it give the expected snapshots and the
    export date in UTC; two exports whose verbatim export dates sort opposite
    to their instants (`2024-03-01 01:00:00 +0900` is earlier than
    `2024-02-29 20:00:00 -0800`) are ordered by instant; `entry_order` over
    an extract with a valid header and corrupt record lines returns the
    header's UTC export date; the candidate's bytes and mtime unchanged after
    `extract`; `extract` on a zip and on its bare member give identical
    decompressed record lines.
  - **Mutations:** claim any `.zip` without `main_member`; return the
    verbatim export date from `entry_order` (lexicographic order breaks across
    offsets: a test with two exports whose local and UTC orders disagree
    reds); `entry_order` through `read_records` (the corrupt-records case
    reds); open the candidate with `'wb'` (the unchanged-bytes assertion
    reds).
  - **Observable:** full `uv run pytest` green (integration point).
  - _Requirements: 1.3, 1.4, 3.6, 5.8, 6.1, 6.2, 6.3, 6.5, 7.2_
  - _Depends: 2.3, 3.1, 3.2_

- [x] 4.2 Import exports through the drain end to end
  - No production change expected; a failing test here is a stop-and-report
    unless the fix lies inside this spec's package. First confirm the
    verify-before-building items (`commit_extract`'s edge behaviour, the
    order-only rebuild, `wellness_progress`) exist on `main`.
  - **Tests** (`tests/wellness/apple/test_import.py`, through `sync.drain`
    with `wellness_progress` recorded, and `tests/wellness/apple/test_e2e.py`
    through `CliRunner` with isolated `HOME`, `FITDOCS_INDEX_DIR`,
    `XDG_CACHE_HOME`):
    - a zip export drained → exactly one new archive file,
      `wellness-archive/apple-health/<sha256 of the zip>.jsonl.gz`, whose
      header sha and size equal the zip's; series lines with source
      `apple-health` and origin `apple`; the progress recorder saw increasing
      percents ending at 100; a second drain reports it already archived and
      writes nothing.
    - the same export as its bare document → archived; year-file bytes and
      mtimes unchanged; the manifest lists one contributed and one
      superseded entry.
    - a later export with changed values → the earlier superseded, the series
      follows the later; an export dated earlier drained afterwards →
      archived and superseded, year files unchanged; the superseded extract
      then corrupted on disk (records garbled, header intact) and `fitdocs
      regen` run → the series status is neither `FAILED` nor `DEFERRED`, it
      carries no notes, and the year-file and manifest bytes and
      `st_mtime_ns` are unchanged.
    - a defective export (all three defects) imports, with the trailer's
      corrections counted.
    - all-or-nothing: a malformed export and an export with an unknown unit →
      reported failed with the reason, quarantined, no entry and no
      `.incoming-*` file, series bytes and mtimes untouched; the next drain
      reports it quarantined without extracting it again (a spy on
      `open_main_document` sees no call and no `.incoming-*` file appears;
      the probe and hash reads are allowed); a bare `.xml` candidate
      rewritten in place, same length, inside bytes already read (from the
      progress callback) so the parse still succeeds → deferred "changed
      during the run", nothing archived; a `KeyboardInterrupt` raised from
      the progress callback propagates and leaves no entry and no temp
      file.
    - disposition: left in place under leave, moved under move, never
      deleted.
    - confinement: the data-root paths the import changed ⊆ the archive
      entry, `wellness/` and the declared `AGENTS.md` files.
    - E2E: `fitdocs sync` exit 0 with the wellness rows; `fitdocs check`
      clean; `fitdocs regen` reports no series change; `fitdocs query`
      returns `wellness_daily` rows with source `apple-health`.
  - **Mutations:** declare `Supersession.NONE` (the superseded assertions
    red); in `iter_items`, end the stream with its corrections on a parse
    error instead of raising (the malformed export then archives a partial
    extract and the all-or-nothing assertions red); move a failed candidate.
  - **Observable:** `uv run pytest tests/wellness tests/test_confinement.py`
    green.
  - _Requirements: 1.4, 2.4, 2.6, 4.1, 4.2, 4.3, 4.4, 5.10, 6.1, 6.2, 6.3, 6.4, 6.5, 14.3_
  - _Depends: 4.1_

- [x] 5. Documentation and release notes

- [x] 5.1 Document the Apple Health import and record the inbox change
  - `docs/wellness.md` § "Apple Health" per design § Docs: exporting from the
    Health app; the type table (Apple type, metrics, writers, daily rule, day
    rule); the reasons; the writer classification and its known
    misclassification; the extract (location, contents, what it never holds,
    reading it with `gzip -dc`); the corrections and that a removed control
    character changes its text; supersession and its consequences; time and
    memory; the original export's fate; naps; no HRV without the watch at
    night; what is not imported. Apple's definition of each of its 12
    metrics wherever the page states per-source definitions, keeping
    `wellness-store`'s metric-table pin green.
  - `docs/inbox.md`: `.zip`/`.xml` wellness candidates, the unrecognized
    report for other zips and XML with the `[inbox] ignore` remedy, progress
    during a long import.
  - `CHANGELOG.md` Unreleased: Added (Apple Health import); Changed (inbox
    interface: `.zip`/`.xml` candidates and the ignore action; the default
    source order gains `apple-health`, so the first sync or regen after
    upgrading rebuilds the series once); absolute `https://` links only.
  - Grep `docs/`, `src/fitdocs/skills/` and `src/fitdocs/` docstrings for
    text naming `.json` as the only wellness suffix or `garmin-export,
    intervals-icu` as the whole default order, and update each (candidates:
    `docs/configuration.md` `[wellness]`, the Meaning cell of the
    `unrecognized` row of `src/fitdocs/skills/fitdocs-workouts/SKILL.md`,
    the `DEFAULT_IGNORE_PATTERNS` docstring in `src/fitdocs/inbox.py`);
    record the grep and its hits in Implementation Notes. In the skill, edit
    the Meaning cell only: the row's Do cell is pinned row-scoped by
    `wellness-store` 5.2 in `tests/test_agent_skill.py` and is never
    touched, and the set of packaged skills does not change.
  - **Documentation compatibility:** replace only the obsolete Apple-planned
    statement parameter in `tests/wellness/test_docs_wellness.py::test_guide_topics`
    with truthful supported-format wording; preserve all other parameters and
    the existing assertion/helper behavior.
  - The day rules in the Apple section refer to the page's one statement of
    the day-boundary rule and never restate it.
  - **Tests** (`test_docs_apple.py`): the doc's type table equals `POLICIES`
    (types, metrics, writers, day and daily rules) row for row; the suffixes
    the docs name equal `FORMAT.suffixes`; the extract path pattern in the
    doc equals `FORMAT_ID` and `ARCHIVED_SUFFIX`; a "how to export" heading
    exists; every `fitdocs` command the section names is registered;
    `wellness-store`'s day-boundary statement still appears exactly once
    across `docs/`; `tests/test_changelog.py` and
    `tests/test_agent_skill.py` green.
  - **Mutations:** remove a writer from a `POLICIES` row (the doc pin reds);
    rename `ARCHIVED_SUFFIX` (the path pin reds).
  - **Observable:** `uv run pytest tests/wellness/apple/test_docs_apple.py
    tests/wellness/test_docs_wellness.py tests/test_changelog.py
    tests/test_agent_skill.py` green; the stale-text grep finds no hit.
  - _Requirements: 1.6, 2.5, 6.6, 8.7, 9.8, 10.8, 13.1, 13.2, 13.3, 13.4_
  - _Depends: 4.1_

- [x] 6. Validation

- [x] 6.1 Determinism, offline behaviour and the whole suite after the final rebase
  - **Determinism** (`tests/wellness/apple/test_determinism.py`): extracting and parsing the same
    export in child processes under `TZ=Pacific/Auckland` and
    `TZ=America/Los_Angeles` gives byte-identical decompressed extracts and
    equal snapshots; a drained data root's `wellness/` tree is byte-identical
    across the two.
  - **Offline** (same module): the drain import completes with
    `socket.socket` patched to raise.
  - Rebase onto `main`; keep both sides of every append-only list named in
    Upstream Prerequisites; confirm no version constant moved; `uv run pytest
    && uv run ruff check . && uv run ruff format --check . && uv run mypy`;
    branch CI green (`gh run list --branch`); `/kiro-spec-status
    apple-health-import` clean.
  - **Mutations:** use `astimezone()` without an argument in the day rule
    (the TZ test reds).
  - **Observable:** the full suite, lint and types green after the final
    rebase; the merge and follow-ups are in the shared log and the queue.
  - _Requirements: 5.3, 11.5, 14.1, 14.2_

- [ ]* 6.2 Maintainer-run smoke on the maintainer's own export (no data enters the repository)
  - In a scratch data root outside the repository, drop the real
    `export.zip` and run the drain with `/usr/bin/time -l`; record in
    Implementation Notes only: wall time, peak RSS, export and extract sizes,
    and from the extract counts per record type, per writer class, per unit
    string and per sleep state; SpO2 records with value ≤ 1 and > 1;
    resting-HR records with and without a device; the corrections; days per
    metric in the series; whether the zip's main document has the English
    name.
  - Confirms the [verify] items of research.md; any mismatch is a
    `RULES_VERSION` bump and a follow-up.
  - **Observable:** counts and timings recorded; no value, device name or
    file name written to the repository.
  - _Requirements: 1.1, 2.5, 7.4_

## Implementation Notes

- **3.1 (historical blocker, resolved below):** Final review after the original
  two allowed debug cycles was REJECTED.
  Correct Reader source and 175-case/57-site test work remain preserved in the
  worktree; no task completion or independent replay acceptance is claimed.
  Two reviewer-designed faults survive all 1122 component tests: suppressing
  progress only for a ZIP member and admitting wanted Records at depth three.
  Separate cache-proof probes fail at the intended assertions; exact source
  and test copies are restored, with final component/static checks green.
  All nine clauses, public schemas, ownership, error/depth cases, literal/AST
  prefixes and factual prose were audited. Historical 188 groups/182 edits/
  246 observations remain uncredited by this last independent review, which
  short-circuited on the two concrete survivors. Preserve existing ZIP bounds,
  memory, privacy, constants, required arguments and native-error fixtures.
  Task 3.2 depends only on accepted 2.2 and 2.4 and remains actionable; 4.1,
  4.2 and 5.1 cannot proceed until 3.1 is approved. Final feature validation
  cannot claim GO while this blocker remains.

- **2.4:** Independently APPROVED and completion VERIFIED: 947 component
  tests, mypy, Ruff, formatting and diff checks pass. All eight policy rows,
  sourceName-only writer evidence across software versions, four-type
  validation/conversion, complete FINAL/LATEST keys, exact per-source step
  totals, own-offset start days and accepted snapshots implemented. Source
  evidence applies to deviceless records; Watch takes precedence over Phone.
  Finite inputs can overflow integer acceptance or `math.fsum`: preserve exact
  integer totals, use the normal fsum path with exact Fraction fallback on
  overflow, then apply the absent-value rule without changing the model.
  Reviewer confirmed 293 claims across 177 distinct source edits (292 selected
  observations, one transparent exact alias) plus two own faults; every group
  was assertion-red and exactly restored to 947-green. All 224 cases/32 sites,
  21 task-local sections and twelve type/writer admission cells audited;
  original 205 cases/27 sites and literal prefix/AST preserved. A writer that
  loses an existing fixture does not prove its admission: retain the earlier
  Phone/later Other weight case while adding winning Phone weight, and pin
  VO2 Phone/Other exclusion independently of policy declarations and RHR.
  Sleep nights, asleep readings, oxygen runtime conversion and sleep-state
  mapping remain assigned to 3.2. Equal step-total source identity has no
  distinct emitted scalar/origin and is not claimed as discriminated.

- **2.3:** Independently APPROVED and completion VERIFIED: 723 component
  tests, mypy, Ruff, formatting and diff checks pass. Canonical level-9 gzip
  JSONL has zero mtime/no filename, sorted compact UTF-8 keys, supplied
  provenance plus fixed UTC export date, ordered raw records/metadata and
  checked trailer counts. Header-only reading parses the first logical line;
  archive entry streams supply compressed bytes, so the codec owns gzip.
  Preserve caller streams and do not import Reader at the same boundary rank;
  task 4.1 orchestrates them. Newer-version checks precede current-layout keys.
  Reviewer replayed 182 claims (180 distinct source edits, two aliases) plus
  four own mutations, each intended assertion-red and exactly restored to
  723-green. All 395 cases/78 sites covered; existing fixtures remain literal
  prefixes with unchanged ASTs. Debug isolated casing-invariant fixtures:
  preserve contrasting inputs, None/empty/zero, padding/interior whitespace,
  metadata member/container distinctions, duplicate/order cases, Unicode
  decomposition and case. Use ISO `T`, mixed units/software versions and actual
  sleep-state text; isolate negative case aliases with empty valid trailers so
  another body guard cannot shadow the header comparison. Source unchanged
  during test repairs; no new follow-ups.

- **2.2:** Independently APPROVED and completion VERIFIED: 328 component
  tests, mypy, Ruff, formatting and diff checks pass. Pure integer-second
  Stage/Segment/NightTotals, boundary sweep and sorted merged half-open asleep
  union implemented. All ten priority pairs retain both nested and partial
  overlap geometries with the winner second; distinct stage counts and union
  lengths, zero/empty, generator/shuffle, touching/gaps and carrier contracts
  pinned. Reviewer replayed 152 claims plus two own mutations, each
  assertion-red and exactly restored to 328-green. Preserve contrasting
  geometries together: replacing one with its opposite can exchange one
  duration/start-time blind spot for another. Raw Apple state-to-metric mapping
  and in-bed dropping remain assigned to 3.2. No new follow-ups.

- **2.1:** Independently APPROVED after one additive test remediation and
  completion VERIFIED: 253 component tests, mypy, Ruff, formatting and diff
  checks pass. `DefectFilter` repairs/counts DOCTYPE, forbidden C0 bytes and
  repeated WorkoutStatistics attributes while preserving CR/LF and first
  values; bounded reads, raw prolog limits, quote-aware tag/name carries and
  EOF behavior verified. Original file bytes, timestamps, seeks and caller
  ownership are observed on a writable temporary file. Mutation groups cover
  all 29 controls, counts, line positions, tag/prolog boundaries, chunks,
  read-only behavior and the 32-case XML whitespace/position/quote matrix.
  Reviewer replayed 235 claims plus three own mutations, each assertion-red
  and exactly restored to 253-green. No new follow-ups.
- **2.1 learnings:** Put a decoy in the same read chunk when testing a search
  bound; place the legal delimiter exactly at the limit. Canonical XML
  formatting does not exercise every valid whitespace form: cover space,
  tab, LF and CR independently around names/equals under both quotes. Group
  related observables without letting an earlier parse exception shadow the
  intended assertion; retain byte-only and counter-only mutation evidence.

- **1.2:** Independently APPROVED and completion VERIFIED: 135 component
  tests, mypy, Ruff, formatting and diff checks pass. Builders are frozen.
  `record_xml` accepts writer/times/value/unit/metadata/raw children and
  attribute overrides (`None` omits a field); `export_document` accepts record
  iterables, optional export date/Me/scaffold/DTD and raw extra elements.
  Use `include_doctype=False` for byte-identical clean-filter fixtures.
  `bulk_records(N)` yields unread HR records; `export_zip` provides English,
  translated, MACOSX-only, Garmin-like and ambiguous layouts; `zip_members`
  accepts arbitrary contents. ZIP helpers support forced ZIP64 and deflate.
  Later tasks define any additional helper locally. Mutation groups pin
  writer/record literals, XML inventory/options/escaping, each real expat
  defect, bulk iteration/counts, ZIP names/content/order/compression/metadata
  and ZIP64 sentinel sizes/extra field. Reviewer replayed all 72 cases and
  13 own mutations, each assertion-red and exactly restored to 135-green.

- **1.1:** Independently APPROVED and completion VERIFIED: 99 component tests,
  mypy, Ruff, formatting and diff checks pass. Seven modules added at ranks
  21–25 without changing existing ranks or guard logic. Mutation groups cover
  enum identifiers/aliases, record attributes, dataclass field order/types,
  defaults and factories, required arguments, frozen instances, verbatim
  storage/nullable fields, correction counts, device normalization and boundary
  violations. Reviewer replayed 157 claims (134 distinct groups) plus four own
  mutations, each assertion-red and exactly restored before 99-green.
- **1.1 learnings:** Check both dataclass default mechanisms and required
  constructor arguments; construct omission/frozen fixtures during tests rather
  than collection. Use distinct stored values and independently nullable fields.
  Device payloads preserve whitespace/newlines and may be empty; test minimal,
  full ASCII hex, invalid-address and trailing-junk partitions. DOTALL fixes
  multiline payload normalization. Use case-safe mutation evidence filenames.
  Broad Apple dependency allowance and relative sibling import resolution are
  shared guard follow-ups; actual Apple imports comply with the narrow boundary.
- Task 3.2 debug cycle 1: correct production passed fresh probes, but same-kind multi-night fixtures and whole-second reading ends leave global Watch-ASLEEP preference and rounded end-instant membership unpinned; fresh debug RETRY_TASK prescribes 12 mixed-device plus 24 fractional-boundary cases, preserving the existing 340/39 test prefix and frozen reducer source.
- Task 3.2 debug cycle 2 (final allowed): correct production passed fresh probes, but raw-asleep/AWAKE overlap admission and individual zero samples before daily acceptance remain unpinned; fresh debug RETRY_TASK prescribes 24 overlap-union plus six zero-in-mean cases, preserving the 376/41 prefix and frozen reducer source.
- Task 3.2 final review: BLOCKED after both allowed debug cycles; unequal Watch-source cardinalities expose an unpinned mean-of-readings rule (60,60 from one source and90 from another require70, not75). All 406 night cases/43 sites and all prior prefixes retained; final draft source6c8bd089…/test4fb1bb48… preserved uncommitted. Fresh controller component1528 plus mypy/Ruff/format/diff pass; final independent review remains REJECTED, so no checkbox or feature-success claim. Exact findings: /private/tmp/apple-review3.2-debug2-report.md; verification: /private/tmp/apple-task3.2-blocked-verification.md.
- **Additional-round authorization (2026-10-15):** The maintainer authorized
  two more debug rounds each for 3.1 and 3.2, followed by regrouping before
  integration. Both additional budgets are now exhausted.
- **3.1, additional rounds:** The first repair pinned ZIP progress and
  depth-three Record exclusion; review then found repaired-byte progress
  and sleep-type device normalization gaps. The second repair added six
  repair/container progress and eight per-type normalization cases.
  Final review remains REJECTED for three proven coverage gaps: STEP_COUNT
  metadata preservation, SleepAnalysis source-version preservation, and
  lowercase DOCTYPE-only rejection. Correct source `e0ed732f…` and the
  191-case/61-site test draft `cfbab2f…` remain uncommitted. The bounded next
  repair is an eight-type raw-fields/ordered-metadata matrix and one
  lowercase DOCTYPE-only negative; further work needs a new authorization.
  Report: `/private/tmp/apple-review3.1-debug4-report.md`; verification:
  `/private/tmp/apple-task3.1-extra-blocked-verification.md`.
- **3.2, first additional round:** The unequal Watch-source cardinality
  repair retained 418 cases/44 sites. Independent review then found valid
  creationDate replacing measurement END and equal averaging by asleep
  bout. Both faults survived 1,556 component tests and failed independent
  sole assertions; exact restoration and statics passed. Report:
  `/private/tmp/apple-review3.2-debug3-report.md`.
- **3.2, approved after both additional rounds:** Sleep-night assignment and
  asleep HRV, respiration and SpO2 reduction are independently APPROVED and
  fresh controller completion VERIFIED. The final repair added 12 delayed
  creation and 12 unequal-bout cases. All 442 cases/46 assertion-or-raises
  sites and thirteen clauses were audited; the reviewer replayed all 108
  groups/531 selected targets across 99 distinct edits/nine aliases at the
  final test SHA, plus two independently derived faults caught. The whole
  prior 418-case literal/AST/location/collection prefix is preserved.
  Fresh component tests (1,580), mypy (567 files), Ruff, formatting (752
  files), and diff checks pass. Preserve delayed-creation END membership,
  unequal Watch-source and asleep-bout cardinalities together with the prior
  mixed-night, raw-asleep-union, zero-sample and fractional-boundary cases.
  Source `6c8bd089…`, night tests `03757c2c…`; the Reader draft remains
  separately blocked. Evidence: `/private/tmp/apple-review3.2-debug4-report.md`
  and `/private/tmp/apple-task3.2-extra-verification.md`. Regroup before 4.1.

- **Reader contract-matrix authorization (2026-10-16):** The maintainer
  approved Astra's finite verification approach: one test-only repair and
  one independent review. Add the eight-type raw-projection matrix and
  isolated recognition table; preserve the current 191-case test baseline,
  production source and accepted Reduce. Replace historical alias/ancestor
  packaging with one deduplicated current evidence table without dropping
  required target observations or independent replay. Stop and regroup on
  rejection; do not start integration automatically. Strategy:
  `/private/tmp/apple-health-astra-reader-strategy.md`.

- **3.1, contract matrix accepted (2026-10-16):** The authorized test-only
  repair added eight type cases, each with 25 independent raw-projection
  records, and thirteen isolated DOCTYPE cases. All original 191 cases
  remain; final Reader has 212 cases/63 assertion-or-raises sites.
  Independent review APPROVED all 538 distinct edits/624 selected target
  observations at final test SHA, plus three own faults caught; all nine
  Reader facets and raw/API foundations are pinned. The exact three prior
  regressions are caught. Current deduplicated evidence replaced repeated
  historical alias/ancestor packaging without dropping target observations.
  Correct production Reader remains unchanged at `e0ed732f…`; final tests
  `c0a4284f…`. Fresh controller full suite: 16287 passed, 44 skipped; mypy, Ruff,
  formatting and diff checks pass; completion VERIFIED. Evidence:
  `/private/tmp/apple-reader-contract-review-report.md` and
  `/private/tmp/apple-reader-contract-verification.md`. Historical rejected
  rounds above remain provenance, not current blockers. Mandatory progress
  is 8/12; regroup before 4.1 under this pass's authorization.

- **Feature completion authorization:** The maintainer requested all remaining
  implementation, merge and push, with the full suite green in CI on merged
  main. This supersedes prior regroup holds and the remote-export hold.
  Rebased cleanly onto `origin/main` at `700b32e…`, preserving wellness-pull
  and HR derivation; accepted Apple components remain unchanged. Remaining
  tasks run one at a time with independent review and fresh verification.

- **4.1 codec import seam:** The facade requires callable `apple.extract`,
  which shadows the codec submodule name used by the accepted codec tests.
  Parent authorized an import-only correction in `test_extract.py` under
  the full-feature completion instruction, with all assertions/fixtures and
  production codec preserved. This is integration compatibility, not a new
  codec API or callable-module compatibility mechanism.

- **4.1 peer registry pins:** Full integration exposed HR engine expectation tuples for the old source registry. Parent licensed only confirmed source-order literal additions in tests/hr_benchmarks/test_engine.py, preserving existing entries and all HR behavior/source/fixtures. Apple registration extends effective partial and default precedence.

- **4.1 CLI consumer pin:** First full integration run reported six failures: four HR source-order pins plus two parameterizations of the same expected-order tuple in tests/test_cli_derive.py. Parent licensed only the Apple addition in that tuple; fixture configuration, other observations, results and all HR/CLI runtime remain unchanged.

- **4.1:** Independently APPROVED and completion VERIFIED before marking complete.
  Public EXTRACT/LATEST_ENTRY facade, real bounded recognition, readonly extraction,
  extract-only parsing and UTC header ordering are registered. The reviewer confirmed
  53 claimed observations (51 unique edits) and two independently designed faults,
  all intended-red and exactly restored-green. Final canonical suite: 22,381 passed,
  44 skipped; parent fresh focused/static/hash checks passed. Codec changes are
  import-only with remaining AST preserved; wellness/HR/CLI differences are narrow
  registry-consequence source-order pins. Declared observed-read controls remain
  infrastructure controls. Remaining feature work and merged-main CI are pending.

- **4.2:** Independently APPROVED and completion VERIFIED before completion metadata.
  Real drain/CLI lifecycle, original provenance, progress, duplicate/later/older
  supersession, header-only regeneration, corrections, quarantine, changed files,
  interrupts, disposition and confinement are covered by 17 new cases. All 66
  distinct faults / 110 selected observations were independently replayed at final
  hashes, plus four own faults; every edit exactly restored and focused-green.
  Final canonical wellness/confinement: 2,727 passed; statics and fresh parent
  verification pass. No production or accepted helper/test changes were needed.
  Earlier-hash implementer proofs retain honest mechanical-fix provenance; independent
  final-hash replay is the acceptance evidence. Documentation and final validation remain.

- **5.1 existing guide pin:** Parent licensed only the obsolete Apple-planned statement parameter in tests/wellness/test_docs_wellness.py::test_guide_topics to follow the now-supported format. All peer statements and existing assertion/helper behavior stay unchanged. No inbox docstring edit is required where the current text already accurately generalizes registered wellness suffixes.

- **5.1:** Independently APPROVED and completion VERIFIED before completion
  metadata. Apple export/import policy, eight type rows and twelve definitions,
  writer/sleep/extract/correction/privacy/supersession guidance, inbox changes and
  release notes are documented. Rendered guards reject extra candidate suffixes
  and extra precedence entries. All39 current fault edits and three independent
  edits were replayed at final hashes, each exactly restored; 342 canonical
  documentation tests, statics and fresh parent verification pass. Runtime and
  skill Do cell are unchanged; only the obsolete Apple-planned guide parameter
  changed in the existing guide tests. Final validation remains pending.

- **5.1 stale-text sweep:** The following exact multiline grep had five baseline
  matches and zero final matches (exit1). The baseline hits were
  docs/configuration.md:254 (whole default order), docs/inbox.md:56 (JSON-only
  candidates), docs/wellness.md:35 (planned import), :203 (whole default order),
  and :220 (Apple unregistered); all were updated. Broader analytics source-order
  examples describe intentional configurations, so remain unchanged. The inbox
  DEFAULT_IGNORE_PATTERNS docstring already described registered suffixes
  generically and stayed unchanged; packaged skill Meaning changed, Do did not.

  ```sh
  rg -n -i -U 'currently\s+`\.json`,\s+with|garmin-export`(?:,\s+then\s+|\s+before\s+)`intervals-icu|Apple Health import is planned|apple-health` is not registered' docs src/fitdocs --glob '*.md' --glob '*.py'
  ```

- **6.1 test implementation:** Independently APPROVED and fresh parent focused/static
  verification passed. Two tests exercise real Auckland/Los Angeles child-process
  extraction/parsing/drain with independently expected eleven raw records, twelve
  metrics and CSV/tree bytes, plus blocked sockets and extract-only rebuilding.
  All fourteen distinct production faults/fifteen selected observations and the
  socket control were independently confirmed, plus three own faults; exact
  restorations and scoped nineteen tests passed. The task stays unchecked until
  the parent finishes its rebase, full-suite, CI and release-validation gates.

- **6.1 final implementation gates:** Final rebase onto main 700b32e is current and
  clean; no Apple version change. Full suite: 22,413 passed, 44 environment skips; Ruff,
  formatting, mypy and diff pass. Canonical build and isolated installed-wheel Apple
  lifecycle pass. Exact implementation-HEAD full CI, including artifact scanning and
  fail-closed checks, passed:
  https://github.com/joshua-stauffer/fitdocs/actions/runs/38984974303. The integration
  audit maps all 14 requirements and 84 criteria with no new blocker. All 12 mandatory
  leaves are accepted; optional maintainer-only 6.2 remains unrun. Final metadata branch
  CI, main merge/push and exact merged-main CI are still required before landing
  completion.

- Landing record (2026-10-17): merged to main at a885031; exact merged-main
  CI 39030817880 SUCCESS; feature Definition of Done complete. The
  "still required before landing" sentence in the 6.1 note above is
  historical.
