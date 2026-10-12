# Research & Design Decisions — apple-health-import

## Summary
- **Feature**: `apple-health-import`
- **Discovery Scope**: Extension (a format plugged into `wellness-store`'s
  registry), with full discovery on the one external input: the Health app's
  export file. No network was used; Apple identifiers come from knowledge of
  HealthKit and are marked where uncertain.
- **Key Findings**:
  - `wellness-store`'s registry contract (design § Seams 3) carries this
    feature without change: an `EXTRACT` format with `LATEST_ENTRY`
    supersession, an `extract(candidate, sink, ExtractContext)` that streams,
    and a `parse` over the archived extract. One amendment is needed for
    rebuild cost: today every superseded entry is parsed on every rebuild.
  - The export's writing sources (`sourceName`, `device`) are enough to
    separate the Apple Watch, the iPhone and other apps, but only per writing
    source, not per record: Apple's computed types (resting HR) may carry no
    `device`. Classification is therefore made once per writing source from
    all of that source's records.
  - Other apps write into Apple Health's SDNN type with their own (often
    rMSSD) values, so "SDNN stays SDNN" requires taking HRV from the Apple
    Watch alone; the same per-source-definition argument covers resting HR,
    respiration, SpO2 and VO2max.

## Research Log

### Viability already established at discovery (roadmap § Viability, brief § Constraints)
- **Context**: the controller's notes and the brief record measurements made
  on synthetic data during discovery (2026-10-12).
- **Findings**:
  - Streaming `xml.etree.ElementTree.iterparse` over a `zipfile` member with
    `events=("start","end")` and root clearing runs at about 10 s per GB of
    XML with flat ~33 MiB RSS on Python 3.11 and 3.13; `elem.clear()` alone
    grows to ~760 MiB at 3 GB.
  - ZIP64 members larger than 4 GB stream.
  - Three defects break stdlib `iterparse` and each has a byte-level fix: the
    iOS 16 malformed DOCTYPE internal subset, stray C0 control characters in
    attribute values, and a duplicate `startDate` on `<WorkoutStatistics>`
    (iOS 16 20A362, Apple developer forum thread 714063).
  - Parse errors surface mid-stream, so an import must be all-or-nothing.
  - `datetime.fromisoformat` parses `2024-02-06 14:30:00 -0800`
    identically on 3.11–3.14.
- **Implications**: the reader design follows the measured idiom exactly;
  the extractor is responsible for streaming; the framework's temp-then-commit
  protocol provides all-or-nothing.

### Stdlib behaviour verified in a scratch probe (no repository change)
- **Sources**: probes under the session scratchpad on CPython 3.11.15 and
  3.14.6/3.14.7.
- **Findings**:
  - `datetime.fromisoformat("2024-02-06 14:30:00 -0800")` returns an aware
    datetime with offset −08:00 on 3.11 and 3.14; `.date()` gives the date
    in that offset.
  - expat (through `iterparse`) rejects a raw `\x0b` in an attribute value
    ("not well-formed (invalid token)"), a character reference `&#11;`
    ("reference to invalid character number"), a duplicate attribute
    ("duplicate attribute") and a malformed internal DTD subset ("syntax
    error"), each with a `(line, column)` position.
  - `iterparse` accepts any object with `read(size)`; on 3.11 it calls
    `source.read(16 * 1024)` (`xml/etree/ElementTree.py:1253`) and sets
    `.root` only after the document ends, so the root must be captured from
    the first `start` event.
  - `zipfile.ZipFile.open(name, "w", force_zip64=True)` writes a member whose
    local header carries the ZIP64 extra field (sizes `0xFFFFFFFF`, extra id
    `0x0001`), readable back through the ZIP64 path: a cheap synthetic ZIP64
    fixture.
  - `gzip.GzipFile(fileobj=…, mtime=0, filename="")` writes the header
    `1f8b 08 00 00000000 02 ff` (no FNAME, mtime 0, XFL 2 for level 9, OS
    255). Without `filename=""`, `GzipFile` takes `fileobj.name`
    (`gzip.py:176`), which would put the framework's temp-file name into the
    extract.
- **Implications**: the gzip call must pass `filename=""` and `mtime=0`;
  ZIP64 is testable without a 4 GB file; error positions are available for
  Req 3.5.

### The Health app export (knowledge of HealthKit; no real export consulted)
- **Context**: no export is in the repository and the maintainer's export was
  deliberately not opened. Statements below are from knowledge of the
  export format; **[verify]** marks what the maintainer-only smoke task must
  confirm by counts.
- **Findings**:
  - `export.zip` holds `apple_health_export/export.xml` (the main export
    document), `apple_health_export/export_cda.xml` (a clinical-document
    file), and folders such as `workout-routes/` and `electrocardiograms/`.
    Exports from devices set to other languages are reported to use
    translated names for the zip and its documents **[verify: unverified;
    recognition must not depend on the English names alone]**.
  - `export.xml` starts with an XML declaration, a `<!DOCTYPE HealthData [ …
    ]>` internal subset of a few hundred lines, then `<HealthData
    locale="…">` with children in order: `ExportDate value="…"`, `Me` (date
    of birth, biological sex, blood type, skin type, medication use), then
    `Record`, `Correlation` (whose children repeat records), `Workout` (with
    `WorkoutEvent`, `WorkoutStatistics`, `WorkoutRoute`, `MetadataEntry`),
    `ActivitySummary`, `ClinicalRecord`, `Audiogram`, `VisionPrescription`.
  - A `Record` carries `type`, `sourceName`, `sourceVersion`, optional
    `device`, `unit` (quantity types only), `creationDate`, `startDate`,
    `endDate`, `value`; children are `MetadataEntry key value` and, for HRV,
    `HeartRateVariabilityMetadataList` of `InstantaneousBeatsPerMinute`.
  - `device` is a description such as `<<HKDevice: 0x283f9a6c0>, name:Apple
    Watch, manufacturer:Apple Inc., model:Watch, hardware:Watch6,1,
    software:9.0>`; the hex is an in-memory object address of the exporting
    process, different on every record. Records Apple computes rather than
    measures (resting heart rate) may carry no `device` **[verify: count
    RestingHeartRate records with and without `device`]**.
  - `sourceName` for Apple's own data is the user-chosen device name
    (for example "<name>'s Apple Watch"), so it cannot be matched against a
    constant; it is stable per device.
  - Timestamps have the form `YYYY-MM-DD HH:MM:SS ±HHMM`: second resolution
    and the offset in force when recorded.
  - Type identifiers read: `HKQuantityTypeIdentifierRestingHeartRate`
    (`count/min`), `HKQuantityTypeIdentifierHeartRateVariabilitySDNN` (`ms`),
    `HKQuantityTypeIdentifierRespiratoryRate` (`count/min`),
    `HKQuantityTypeIdentifierOxygenSaturation` (`%`, written as a fraction
    0–1 **[verify: count records with value ≤ 1 and > 1]**),
    `HKQuantityTypeIdentifierVO2Max` (`mL/min·kg` **[verify the unit
    string]**), `HKQuantityTypeIdentifierStepCount` (`count`),
    `HKQuantityTypeIdentifierBodyMass` (`kg`, `lb`, `g`, `st` by the
    athlete's preferred unit **[verify which unit appears]**),
    `HKCategoryTypeIdentifierSleepAnalysis` (no unit; values
    `HKCategoryValueSleepAnalysisInBed`, `…AsleepUnspecified`, `…Awake`,
    `…AsleepCore`, `…AsleepDeep`, `…AsleepREM`, and the deprecated
    `…Asleep` in older exports).
  - Apple Watch writes sleep stages (core, deep, REM, awake) since watchOS 9;
    before that it wrote unspecified asleep time; the iPhone writes in-bed
    time from its sleep schedule.
  - The Apple Watch takes HRV (SDNN, about one-minute windows) readings at
    irregular times, more of them at night; respiratory rate during sleep
    only; blood oxygen in the background day and night (Series 6 and later).
  - Third-party apps (sleep trackers, rings, HRV apps, scales, Garmin Connect)
    write into the same types. HealthKit had no rMSSD type before iOS 27, so
    apps measuring rMSSD commonly write it into the SDNN type.
  - Resting heart rate is Apple's sedentary estimate for the day, revised
    during the day; the brief cites Apple's note that it "may delete earlier
    samples and replace them with better estimates".
  - `HKQuantityTypeIdentifierHeartRateVariabilityRMSSD` (iOS/watchOS 27) is
    undocumented and out of scope.
- **Implications**: recognition uses the main document plus its
  clinical-document companion, not only the English name; classification is
  per writing source; units are a closed table per type with a named failure;
  every [verify] item is in the smoke task (counts only).

### `wellness-store` seams consumed (its design.md, authoritative)
- **Findings**:
  - Registry (§ Registry, § Seams 1, 3): `FormatSpec` with `suffixes`,
    `archive_form=EXTRACT`, `archived_suffix`, `rules_version`, `metrics`,
    `recognize(CandidateProbe)`, `parse(BinaryIO) -> Iterator[DaySnapshot]`,
    `supersession=LATEST_ENTRY`, `extract(Path, BinaryIO, ExtractContext)`,
    `entry_order(BinaryIO) -> str`. `validate_registry` requires formats of
    one source to declare disjoint metrics, which forces **one** Apple format
    for both `.zip` and `.xml`.
  - Probe (§ Probe): `name`, `suffix`, `size`, `head` (64 KiB),
    `zip_members()` (central directory only).
  - Archive (§ Archive): the extractor opens the candidate itself; the
    framework re-hashes after `extract`, parses the temp extract (and
    `entry_order`), and commits `wellness-archive/<format>/<sha of the
    original><archived_suffix>`; the temp file is removed on any outcome but
    success; the listing matches `64 hex + archived_suffix` by string, so a
    two-part suffix (`.jsonl.gz`) is valid.
  - Intake (§ Intake): an entry that exists for the candidate's sha →
    already archived without reading further; `Invalid` → failure and
    quarantine; `Changed` → deferred.
  - Merge (§ Merge): `LATEST_ENTRY` keeps the greatest `(order, entry_ref)`;
    the others are listed as superseded. But `archive.parse_entry` is called
    for every entry before the merge, so a superseded Apple extract is fully
    parsed on every rebuild.
  - Default order (§ Seams 3): `SourceSpec("apple-health", "Apple Health",
    SourceKind.HUB)` gives `garmin-export`, `apple-health`,
    `intervals-icu`.
  - Day rule (§ Seams 4): `wellness_day_of_sleep_end(end)` = the date of
    `end + 6 h` in the end's own offset; sources that report dates keep them.
  - Model (§ Data Models): the 28 metrics, ranges and zero rules; the 12 this
    feature emits exist already, so no metric or unit is added.
  - CLI (§ CliWellness): a progress printer writes `"<rel>: <percent>%"` to
    stderr on a terminal; it does not throttle, so the extractor must.
- **Implications**: the format is a pure plug-in. Its one upstream need, a
  rebuild that reads superseded entries only for their order, was proposed
  as amendment A1 and folded by the controller into `wellness-store`'s own
  spec at the Step 3.5 review (below).

### Current code that bounds the design (main at the branch base)
- `sync.py:888-890` reads each stable FIT candidate whole
  (`candidate.path.read_bytes()`); `wellness-store` § DrainWellnessStep keeps
  that loop FIT-only and routes wellness candidates through the probe,
  `hash_file` and `commit_extract`, so a multi-GB export never reaches it.
- `inbox.settle` (`inbox.py:667-721`) observes only `stat` and never opens a
  candidate: settling a multi-GB export costs nothing.
- `fitdocs.units.UNITS` (`units.py:41-61`) holds `bpm`, `ms`, `pct`, `kg`,
  `s`; `wellness-store` 1.1 appends `ml_per_kg_min` and `brpm`. No unit is
  added here.
- `CHANGELOG.md:8-14`: an entry touching the inbox interface names the
  contract and the action; `tests/test_changelog.py` requires absolute
  `https://` link targets.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| One module | `formats/apple.py` with everything | One file | ~700 lines mixing byte filtering, XML, codec and statistics; poor review boundaries | Rejected |
| Subpackage by concern | `formats/apple/` with `records`, `defects`, `reader`, `extract`, `sleep`, `reduce`, and the format declaration in `__init__` | Matches the brief's boundary candidates; each module testable alone; one-way imports | More rank-table rows in `wellness-store`'s boundary guard | **Selected** |
| Separate source package | `fitdocs.apple_health` outside `wellness` | Independent | Breaks `wellness-store`'s rule that formats live in `wellness/formats/` and the registry imports them | Rejected |

## Design Decisions

### Decision: One format for `.zip` and `.xml`
- **Context**: `validate_registry` requires disjoint metrics per source;
  supersession is per format.
- **Alternatives**: two formats (zip, xml) of one source — rejected: same
  metrics (validation fails) and two independent "latest" entries that would
  conflict in the merge.
- **Selected**: one `FormatSpec` `apple-health` with suffixes `{".zip",
  ".xml"}`; its recognizer and extractor handle both, and both produce the
  same extract layout.

### Decision: The extract is gzip-compressed JSON Lines
- **Alternatives**: a filtered XML subset (re-parsing needs the defect filter
  again and is slower); CSV (metadata pairs and optional attributes fit
  badly); SQLite (not text, not diffable, an extra writer).
- **Selected**: UTF-8 JSON Lines (`json.dumps(sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)`) inside gzip (level 9,
  `mtime=0`, `filename=""`): a header line, one line per record with Apple's
  own attribute names and verbatim text values, and a trailer line with the
  record count and the corrections.
- **Rationale**: readable with `gzip -dc` and any JSON tool; deterministic;
  the trailer detects truncation; values stay text so a later rules change
  re-derives everything.
- **Trade-offs**: decompressed content is deterministic everywhere;
  compressed bytes are deterministic for one zlib build. The archive entry is
  named by the original's sha, and an existing entry is never rewritten, so a
  zlib difference between machines never churns the archive.

### Decision: Which record types the extract keeps
- **Selected**: exactly the eight types this feature reads, from every
  writing source, at the top level of `HealthData` only (a record repeated
  inside a `Correlation` is not taken twice).
- **Alternatives**: also keep wrist temperature and the iOS 27 rMSSD type for
  later — rejected: every export is the whole history, so a later fitdocs that
  reads them asks for one new export; keeping unread types grows every
  extract now for a speculative later.

### Decision: Writer classification per writing source
- **Context**: the export has no bundle identifier; `sourceName` is
  user-named; `device` may be absent on computed types.
- **Selected**: a writing source (`sourceName`) is the Apple Watch when any
  of its records in the extract names a device with `manufacturer:Apple Inc.`
  and `model:Watch`; otherwise the iPhone when any names `manufacturer:Apple
  Inc.` and `model:iPhone`; otherwise another app. Every record of the source
  takes the source's class.
- **Risk**: a third-party app running on the watch that names the watch as
  its device would be classified as the Apple Watch. Accepted and documented;
  the smoke task counts records per class per type.

### Decision: Physiological metrics from the Apple Watch only; weight from every writer
- **Alternatives**: a preference order Watch > iPhone > other apps with
  fallback — rejected: an HRV app's rMSSD in the SDNN type would splice into
  `hrv_sdnn_ms` (the brief's and the roadmap's hard rule), and a series whose
  definition switches from day to day defeats per-source baselines.
- **Selected**: resting HR, HRV, respiration, SpO2, VO2max from the Apple
  Watch; steps and sleep from the Apple Watch or the iPhone; weight from every
  writer (no Apple device weighs). Other apps' values reach fitdocs through
  their own sources (intervals.icu relays Oura, WHOOP, Garmin…), where their
  definition and baseline stay their own. The roadmap's research already
  notes Garmin Connect writes into Apple Health (`wellness-store`
  research.md, default precedence decision).

### Decision: HRV, respiration and SpO2 as the mean of readings taken asleep
- **Alternatives**: (a) the mean of the calendar day's readings — mixes
  readings after exercise, stress and posture changes taken at random times
  and splits a night across two days; (b) the mean over the window
  `wellness_day_of_sleep_end` gives (18:00 to 18:00) — consistent day, but the
  day's value would include readings taken after a morning workout, which the
  morning-of block shows as "that morning's HRV"; (c) the first reading after
  waking — one noisy reading.
- **Selected**: the mean of the Apple Watch's readings whose end lies within
  the Apple Watch's asleep time of the day's night, rounded to 0.1. Overnight
  averaging is the convention of the platforms the series compares against
  (Garmin HRV Status, Oura and WHOOP report overnight values) and measures
  under one condition, at rest, every day — which the 7-day ln-mean method
  recovery applies assumes.
- **Trade-off**: an athlete who does not sleep with the watch gets no Apple
  HRV, respiration or SpO2. Stated in the docs.

### Decision: Steps as the largest single-source day total
- **Alternatives**: (a) Watch, else iPhone — undercounts every day the watch
  was worn briefly; (b) Apple's own per-interval priority merge — needs every
  step sample of every source in memory at once (about a million samples for
  a decade) or a second pass over the extract; (c) sum — double counts.
- **Selected**: each allowed source's day total; the day's value is the
  largest. Never summed across sources. Documented as possibly lower than the
  Health app's figure on days the watch was off for part of the day while the
  iPhone was carried.

### Decision: Sleep — one device kind per night, a per-stage sweep within it
- **Selected**: segments are assigned to nights by `wellness_day_of_sleep_end`
  of their end; a night uses the Apple Watch's segments when it recorded
  asleep time, else the iPhone's; within that kind, a sweep over all segment
  boundaries assigns each instant the most specific stage covering it (deep,
  REM, core, awake, unspecified asleep); in-bed time is ignored.
- **Rationale**: the union never double counts overlapping segments (two
  watch names, duplicated writes); never mixing devices keeps onset and wake
  estimates from different algorithms from inflating a night. This is the
  brief's "union per stage under a source preference" with the preference
  applied per night.

### Decision: The defect filter rewrites bytes, keeps line breaks
- **Selected**: (1) the prolog from `<!DOCTYPE` up to the root start tag is
  replaced by its own line breaks (robust to any malformed internal subset);
  (2) bytes 0x00–0x08, 0x0B, 0x0C, 0x0E–0x1F are deleted (UTF-8 continuation
  bytes are ≥ 0x80, so deletion never splits a character); (3) inside a
  `<WorkoutStatistics` start tag a repeated attribute is removed, keeping the
  first (fitdocs never reads the element, so which value survives does not
  change the extract). Every rewrite keeps the line breaks it removes, so the
  parser's error line is the export's own line.
- **Not handled**: a character reference to a control character (`&#11;`)
  and invalid UTF-8; they fail the import with a line number and become a
  follow-up if seen.

### Decision: Superseded extracts are read for their order only
- **Context**: Req 6.5; with monthly exports the rebuild would parse every
  past extract (seconds each) on every `regen`.
- **Selected**: `entry_order` reads the extract's header line alone; the
  rebuild reads every `LATEST_ENTRY` entry's order through
  `archive.read_entry_order` and calls `parse_entry` only for the greatest
  `(order, ref)`. Proposed here as amendment A1; at the Step 3.5 review the
  controller folded the rebuild half (with the extractor edge behaviours of
  `commit_extract`, gapped boundary-guard ranks and the counting opener's
  zipfile end-record rule) into `wellness-store`'s own spec, so this spec
  consumes it as provided.
- **Verified evidence for the counting-opener rule**: CPython 3.11.15
  `zipfile._EndRecData` calls `fpin.read()` without a size after seeking to
  the end record (`zipfile.py:320`, `:342`); `is_zipfile` and `ZipFile()`
  both go through it.

## Risks & Mitigations
- Identifier or unit strings differ from knowledge (VO2max unit, SpO2
  scale, localized names) — the unit table fails the import naming the type
  and unit; SpO2 at ×100 scale falls outside 1–100 and is absent, never wrong;
  the smoke task counts each; a rules_version bump fixes it.
- A real export carries a fourth defect — the import fails whole with the
  export's line number; quarantine prevents re-running a multi-minute failing
  import on every drain; queue the defect.
- A later export with a shorter history (new phone without Health sync)
  supersedes a longer one — documented; the older extract stays in the
  archive.
- The parse holds every sleep segment and spot reading of the history in
  memory (about 100 bytes each, tens of MB for a decade) — documented bound;
  measured by the smoke task.

## References
- Apple developer forum thread 714063 — the iOS 16 duplicate `startDate` on
  `WorkoutStatistics` (cited by the brief; not fetched).
- GitHub, "About large files on GitHub" — 100 MiB block, 50 MiB warning
  (cited by the brief; not fetched).
- CPython `xml/etree/ElementTree.py` (3.11) `iterparse`; `gzip.py`
  `GzipFile` header fields; `zipfile.ZipFile.open(force_zip64=)`.
- `.kiro/specs/wellness-store/design.md` § Seams for downstream specs.
