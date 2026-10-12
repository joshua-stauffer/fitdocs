# Brief: apple-health-import

## Problem

For an Apple Watch athlete, Apple Health is the canonical wellness store,
and the only place that holds all of it. intervals.icu receives a subset
only from the day a bridge app's health sync was switched on. For the
maintainer that day was 2025-06-17. Garmin covers 2018-11 → 2023-02, so
Apple Health alone holds 2023-03 → 2025-06, about 27 months. Apple Health
also carries sleep stages, which intervals.icu has no field for.

## Current State

- Nothing in fitdocs reads Apple Health.
- Apple offers no cloud API. The Health app's **Export All Health Data**
  writes `export.zip`, which contains `apple_health_export/export.xml` and
  more (research 2026-10-12).
- **Record types that matter:**
  - `HKQuantityTypeIdentifierRestingHeartRate` (count/min);
  - `HKQuantityTypeIdentifierHeartRateVariabilitySDNN` (ms);
  - `HKQuantityTypeIdentifierHeartRateVariabilityRMSSD` (new in iOS/watchOS
    27, undocumented; Apple has not confirmed it is the Series 12 "Recovery
    HRV");
  - `HKCategoryTypeIdentifierSleepAnalysis`, with values `InBed`, `Awake`,
    `AsleepCore`, `AsleepDeep`, `AsleepREM`, `AsleepUnspecified` and the
    deprecated `Asleep`;
  - `RespiratoryRate`, `VO2Max`, `AppleSleepingWristTemperature`,
    `BodyMass`, `OxygenSaturation`, `StepCount`.
- `wellness-store` (this phase) provides the format registry, the archive,
  the model, the merge and the series.

## Desired Outcome

- The athlete drops `export.zip`, or a bare `export.xml`, into the inbox.
- The drain streams it once and archives a **canonical extract** in place
  of the original (maintainer, 2026-10-12, after viability; see
  Constraints):
  - only the wellness record types, as raw records, so the daily reduction
    can be re-derived;
  - deterministic and compressed;
  - carrying the original's sha256, byte size and export date.
- The drain parses the extract into per-day records attributed to Apple
  Health. The source app and device are kept where the design needs them for
  de-duplication.
- The original export stays the athlete's to keep or delete. It leaves the
  inbox like any handled file, and fitdocs never needs it again.
- The records merge into the series under the configured precedence.
- A later export of the same account supersedes the earlier one without
  double-counting. Every export is the whole history, so the newer extract
  replaces the older one as the series input.

## Approach

- A streaming, stdlib-only parser registered through `wellness-store`'s
  format registry:
  - `zipfile` member streaming, with no extraction to disk;
  - `xml.etree.ElementTree.iterparse` with element clearing;
  - a byte-level filter for the known export defects.
- **Daily reduction rules**, one per type, chosen and cited by the design:
  - **Resting HR**: Apple "may delete earlier samples and replace them with
    better estimates", so take the day's final Apple Watch sample.
  - **HRV SDNN**: Apple writes spot readings through the day; the design
    picks the daily statistic.
  - **Sleep**:
    - per-stage segments from several sources overlap;
    - union them per stage under a source preference;
    - assign the night to a date by `wellness-store`'s day-boundary rule.
- **Source handling.** Several apps write the same types (`sourceName`); the
  iPhone and the Watch both write steps. De-duplicate by a declared source
  preference instead of summing.

## Scope

- **In**:
  - recognition of `export.zip` and `export.xml`;
  - the canonical extract: its format, determinism, provenance header and
    supersession;
  - the streaming parser and its defect handling;
  - the per-type daily reduction;
  - source de-duplication;
  - supersession by a later export;
  - progress reporting for a multi-minute import;
  - documented memory and time bounds on a multi-GB export;
  - docs: how to export from the Health app, and what is imported.
- **Out**:
  - Apple workouts and routes. Activities keep arriving as `.fit` through
    HealthFit;
  - clinical records, ECG, audiograms and nutrition;
  - third-party file exporters such as Health Auto Export's iCloud JSON/CSV.
    Health Auto Export is a follow-on candidate; it is a paid tier and runs
    only while the phone is unlocked;
  - the iOS 26 Sleep Score, which has no developer API.

## Boundary Candidates

- The byte-level defect filter plus the streaming record reader: pure and
  independently testable on synthetic exports.
- Per-type daily reducers.
- Source de-duplication and supersession.

## Out of Boundary

- The archive, merge and series files (`wellness-store`).
- Any baseline or visualisation.

## Upstream / Downstream

- **Upstream**: `wellness-store` (the registry, archive, model, merge and
  day-boundary rule).
- **Downstream**: `hr-derivation`, `recovery` and `workout-wellness`, all
  through the series.

## Existing Spec Touchpoints

- **Extends**: none directly. It plugs into `wellness-store`'s registry.
- **Adjacent**: `wellness-store`; `inbox` (large-file handling during the
  drain).

## Constraints

- **Viability findings (2026-10-12)**, which make archiving the whole export
  unworkable:
  - **GitHub blocks files over 100 MiB** and warns over 50 MiB
    (<https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github>).
    - Once a 0.1–2 GB `export.zip` is committed, every later push to GitHub
      is blocked until history is rewritten.
    - Git LFS caps a file at 2 GB on the free plan.
  - **Every export is the whole history, and no two are byte-identical.**
    Content hashing therefore never de-duplicates them, and the archive grows
    by a full export each time. In a git repository inside iCloud, each one
    is stored and synced twice: the working-tree file plus the git object.
  - **Eviction.** With "Optimize Mac Storage", macOS's default is to *not*
    materialise an evicted file on read (`man getiopolicy_np`). A rebuild
    from an evicted multi-GB archive would fail, not stall.
  - Hence the canonical extract: small, rebuildable and safe to push to
    GitHub.
- **Streaming.**
  - Exports run from about 1 GB to over 5 GB of XML. The parser holds
    neither the document nor the zip member in memory.
  - Clear the root as well as each element: `iterparse` with
    `events=("start","end")`.
  - Measured on synthetic data: about 10 s per GB of XML, with flat
    ~33 MiB RSS on 3.11 and 3.13. With `elem.clear()` alone, memory grows to
    about 760 MiB at 3 GB.
  - ZIP64 members over 4 GB stream fine.
  - `iterparse`'s `.close()` exists only on 3.13+, so close the member with
    `with`.
- **Three export defects**, each reproduced on synthetic files. Each one
  breaks stdlib `iterparse`, and each is fixed by a byte-level rewrite
  before the parser:
  - **iOS 16-era malformed DOCTYPE internal subset.** Strip the DOCTYPE.
  - **Stray C0 control characters such as `\x0b`** in attribute values.
    Drop them; this changes the value, so the design records it.
  - **Duplicate `startDate`** on `<WorkoutStatistics …>` (iOS 16 20A362,
    <https://developer.apple.com/forums/thread/714063>). The second one is
    the end date.
- **All-or-nothing per export.** Parse errors surface after thousands of
  records have been read, so a failed import must leave the series and the
  archive untouched.
- **The drain must stream large inbox files.** It reads every candidate
  whole into memory today (`sync.py:890`). See `wellness-store`.
- Dates have the form `2024-02-06 14:30:00 -0800`. `datetime.fromisoformat`
  parses them identically on 3.11 to 3.14.
- No new runtime dependency (no lxml). No network.
- Synthetic fixtures only. The maintainer's export never enters the repo.
