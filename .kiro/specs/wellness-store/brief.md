# Brief: wellness-store

## Problem

fitdocs sees only workouts. Recovery happens between them, in resting HR,
HRV, sleep, weight and the days without training. That data exists for most
athletes, but in different places and shapes:

- **intervals.icu wellness records**: the aggregator for Garmin, COROS,
  Polar, Suunto, Oura, WHOOP, Zepp and Huawei, and for Apple Health through
  HealthFit.
- **Garmin's "Export Your Data" JSON files.**
- **Apple Health's export.**

Every Phase 12 consumer needs one answer to "what was this athlete's
resting HR, HRV and sleep on this day, and where did each number come
from?". The consumers are the recovery page, the morning-of block, HR
derivation and the analytics index.

## Current State

- No wellness model, store or parser exists.
  - `parse_fit` reads only activity messages (`ingest/__init__.py:66-76`).
    It never reads `file_id.type` (`ingest/file_id.py:32-46`).
  - A Garmin monitoring or sleep `.fit` dropped in the inbox would probably
    become an `undated-` workout page. That is an inference from
    `summary.py:273-293` and `layout.py:235-237`; no test covers it.
- **The inbox takes `.fit` files only** (`inbox.py:587`). The archive
  (`fit-archive/`) is immutable and content-hashed, and holds `.fit` only.
- **Owned locations** are `workouts/`, `history/`, `blocks/`, `fit-archive/`,
  `.cache/` and `.fitdocs/` (`layout.py:133-142`), with `CONTRACT_VERSION`
  "9" (`contract.py:328`).
  - `.cache/` may hold only re-fetchable data.
  - `.fitdocs/` holds run state, not archived sources
    (`docs/ownership-contract.md:59-71`).
  - A raw wellness file is an archived source, so it belongs in neither.
- **The analytics index** accepts non-page tables through the corpus
  producer tier. `BenchmarkProducer` (`index/derived/benchmarks.py:200-209`)
  and `BlockProducer` (`index/derived/blocks.py:230-255`) are the precedents.
  `SCHEMA_VERSION` is 2 (`index/schema.py:15`).
- **Measured data** (2026-10-12; maintainer's data, shapes only):
  - **intervals.icu**: 483 days, 2025-06-17 → today. Resting HR, HRV SDNN,
    sleep seconds, SpO2, steps, VO2max, weight. Sleep stages are absent.
  - **Garmin export.** It covers 2018-11 → 2023-02, from the maintainer's
    Garmin-watch years. After that the Garmin is only a bike computer, and
    its files are near empty.

    | File | Records | What it holds |
    |---|---|---|
    | `DI-Connect-Aggregator/UDSFile_*.json` | 1,325 day records | `restingHeartRate` on 937 days, plus min/max HR, all-day stress, body battery (2022), respiration, SpO2, steps |
    | `DI-Connect-Wellness/*_sleepData.json` | 1,065 nights | deep/light/REM/awake seconds on 604 nights |
    | `DI-Connect-Metrics/MetricsMaxMetData_*.json` | 1,802 | VO2max |
    | `*_userBioMetrics.json` | 23 | weight entries |

    HRV is not in the JSON. Garmin puts overnight HRV in FIT files inside
    the export's upload zips (research 2026-10-12).
  - **The gap.** Nothing covers 2023-03 → 2025-06 except Apple Health. That
    gap is `apple-health-import`'s reason to exist.
  - **HealthFit's iCloud folder** holds no wellness. It has activity
    `.fit`/`.gpx` files and 13 app-database CSVs (gear, goals, routes,
    workout names).

## Desired Outcome

- The athlete drops a supported wellness file into the inbox, or a connector
  delivers one. The drain then:
  1. recognizes it;
  2. archives its original bytes;
  3. parses it into per-day records;
  4. merges them into one normalized daily series;
  5. reports what it added or changed.
- Every consumer reads the series. `regen` rebuilds the series from the
  archive alone.
- A file fitdocs cannot use is reported and left alone, never rendered as a
  workout. That covers an unsupported wellness format and a non-activity
  FIT.

## Approach

**Archive plus a normalized series** (maintainer, 2026-10-12), over
re-parsing the archive on every pass (minutes for an Apple Health export)
and over an index-only store (pages would depend on a per-machine cache).

- **Recognition** is by a registry of wellness formats. Each declares a
  suffix and a content sniff: JSON shape, XML root, zip member names.
  - This spec ships the intervals.icu and Garmin-export formats.
  - `apple-health-import` registers Apple Health through the same registry.
- **The archive** is a new fitdocs-owned, content-hashed, immutable location
  beside `fit-archive/`, recommended `wellness-archive/`.
  - The original bytes are kept whole for the small JSON formats.
  - A format may instead declare a **canonical extract** as its archived
    form. Apple Health does (maintainer, 2026-10-12, after viability: a
    whole export is 0.1–2 GB, never de-duplicates, and breaks GitHub pushes;
    see `apple-health-import`).
  - `fit-archive/` keeps its meaning.
- **The model** is per day and per field:
  - canonical metric names with units in the name (resting HR bpm, HRV
    SDNN ms, HRV rMSSD ms, sleep seconds and stage seconds, SpO2 %, weight
    kg, VO2max, steps, stress, body battery, the subjective 1–4 scores);
  - the source and the source's definition of the metric on each value;
  - absent values are `None`.
- **The merge.** A per-field source precedence decides which value is the
  day's canonical value when sources overlap.
  - Every source's value stays available for per-source baselines.
  - Default: a device-native export (the Garmin export, an Apple Health
    export) outranks an aggregator relay (intervals.icu). This mirrors Phase
    8's "a device original outranks a partner-API or phone-side copy".
  - The precedence is configurable in `fitdocs.toml`.
- **The series** is written as fitdocs-owned yearly data files under a new
  location (for example `wellness/2025.csv`):
  - deterministic and diff-friendly;
  - readable without fitdocs;
  - re-derivable from the archive.

  The design picks the format (CSV, TOML or a markdown table) and justifies
  it.
- **The day-boundary rule** is set once, here, for sleep and morning-of
  consumers: which calendar date a night belongs to. Garmin's `calendarDate`
  and Apple's segment overlaps differ.
- **The index.** A `wellness_daily` corpus producer fingerprints the series
  files. It brings a `SCHEMA_VERSION` bump and a regenerated
  `docs/analytics.md` schema block.

## Scope

- **In**:
  - the format registry and inbox recognition (amending the `.fit`-only
    inbox);
  - the parsers:
    - intervals.icu wellness JSON, as `wellness-pull` delivers it;
    - Garmin export `UDSFile`, `sleepData`, `MetricsMaxMetData` and
      `userBioMetrics` JSON, each accepted as an individual file;
  - the wellness archive and its owned-location plumbing;
  - the model, the merge and the series files;
  - the rebuild on `regen`;
  - `check` findings: an orphaned archive entry, a series out of date, a
    conflicting duplicate;
  - the non-activity-FIT guard (held and reported, not rendered);
  - the `wellness_daily` index table;
  - docs (a wellness page in `docs/`) and the packaged skill's routine.
- **Out**:
  - the Apple Health parser (`apple-health-import`);
  - the intervals.icu wellness pull (`wellness-pull`);
  - parsing Garmin wellness FIT messages (monitoring, sleep, HRV status).
    These are follow-ons. The guard keeps such files out of workouts
    meanwhile;
  - importing a whole Garmin export zip. It also carries some 15,000
    activity files, so the athlete drops the wellness JSON files instead;
  - baselines and visualisation (`recovery`, `workout-wellness`);
  - a generic wellness CSV format (follow-on);
  - nutrition, blood pressure and glucose fields. The model may reserve the
    names; parsers fill only what the measured sources carry.

## Boundary Candidates

- The format registry plus recognition: the seam `apple-health-import` and
  `wellness-pull` both plug into.
- Archive and owned-location plumbing.
- Model, merge and series files: what every consumer reads.
- The index producer.

## Out of Boundary

- Any network access.
- Any document other than the series files.
- Baselines, scores and verdicts.

## Upstream / Downstream

- **Upstream**:
  - `inbox` (the drain);
  - `wiki-contract` (owned locations, `CONTRACT_VERSION`);
  - `analytics-index` (producer seam);
  - `fit-ingest` (the non-activity-FIT guard reads `file_id`).
- **Downstream**: `wellness-pull`, `apple-health-import`, `hr-derivation`,
  `recovery`, `workout-wellness`, and dashboards over `wellness_daily`.

## Existing Spec Touchpoints

- **Extends**:
  - `wiki-contract`: an amendment for the archive and series locations and
    `CONTRACT_VERSION` main + 1;
  - `inbox`: an amendment for non-FIT recognition and the drain step;
  - `analytics-derived` or `analytics-index`: an amendment for the
    `wellness_daily` producer and `SCHEMA_VERSION` + 1;
  - `fit-ingest`: an amendment for the non-activity guard, if the design
    places it in ingest.
- **Adjacent**:
  - `connectors` (the delivered-file contract with `wellness-pull`);
  - `activity-identity` (local-date conventions).

## Constraints

- **Personal data never enters the repo.** Tests use synthetic files shaped
  like the measured ones, never the maintainer's values.
- **Absent is `None`, never 0.** A Garmin `0` stress or a `-1`/`-2` sentinel
  is decoded to `None` where the format documents it as invalid.
- **HRV statistics are never conflated.** SDNN and rMSSD are separate
  metrics, and nothing converts between them.
- **Deterministic, stdlib-only parsing.** No new runtime dependency. JSON,
  XML, zipfile and CSV come from the stdlib.
- **No network.** The drain stays offline.
- **Inbox semantics are kept.** A file that was handled is archived and
  removed from the inbox, exactly as a `.fit` is. A second drain with
  nothing new changes nothing.
  - Today a `.json` or `.zip` in the inbox is silently ignored and stays
    forever. It is filtered before selection (`inbox.py:586-588`), and the
    report has no "ignored" channel (`sync.py:766-767`).
  - The inbox change must keep the folder connector, which reuses
    `select_candidates` (`connectors/folder.py`), from silently widening.
- **The drain reads every candidate whole into memory** (`sync.py:890`, and
  again at `:1438` and `:1525`). Wellness candidates must be streamed
  instead.
- **Pins the inbox and archive change must move** (viability 2026-10-12):
  - inbox and layout:
    - `inbox.py:530-550` (ignore patterns justified by the `.fit` filter);
    - `layout.py:59`, `:297-298` and `:382-386` (archive name, `<sha>.fit`,
      `source_ref`);
    - `OWNED_PATHS` and `DECLARED_DIRS` (`layout.py:133-142`, `:160-165`);
  - sync and audit:
    - `sync.py:992` (a disposition gate on the `.fit` archive path);
    - `sync.py:2448` and `audit.py:503` (`*.fit` orphan and audit globs);
  - declarations and contract:
    - `declaration.py:461`;
    - `CONTRACT_VERSION` in the `tests/declaration_golden/*` goldens;
  - tests:
    - `tests/test_inbox.py:652-658`;
    - `tests/test_layout.py:187`, `:403`, `:421`, `:649`, `:863`, `:885`;
    - `tests/test_sync.py:484`, `:551`.
- **Size.** The archive and series sit in the maintainer's iCloud and git
  data root.
  - The series files must stay small.
  - Archived originals stay small: the JSON formats are kilobytes to a few
    megabytes, and Apple Health archives an extract.
  - **Eviction.** iCloud may evict rarely read archive files, and macOS does
    not materialise them on read by default. The drain already defers a
    placeholder it cannot read (`sync.py:888-901`). A series rebuild needs
    the same behaviour: report what it could not read, and never write a
    partial series as if it were complete.
