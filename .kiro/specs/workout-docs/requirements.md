# Requirements Document

## Project Description (Input)
User-visible layer of fitdocs (an installable `.fit` → markdown personal
knowledge manager for fitness). Athletes who keep their training in a markdown
PKM need each `.fit` file they drop in a directory to become one strong,
readable workout document — today parsed data (from the fit-ingest library)
has nowhere to live. This spec delivers the `fitdocs` CLI (sync command,
data-root resolution, packaging via `uv tool install`), per-sport markdown
document templates (run/ride, strength, generic fallback) rendered over the
fit-ingest activity model, hand-generated SVG charts (power-vs-HR hero chart
with elevation backdrop, HR-zone strip), splits tables (device laps + 1 km
re-slice), device/data-quality section, pkm-compatible YAML frontmatter with
provenance to the sha256-archived source `.fit`, idempotent re-runs, a
reserved training-load placeholder section filled later by the training-load
spec, and a user-editable free-form section in weight-training docs that
regeneration must preserve. See `.kiro/specs/workout-docs/brief.md` and
`docs/reference/fitdocs-ai-reference.md`.

## Amendment 1 (2026-09-30): the Running Dynamics section, landed by running-dynamics

Run pages show heart rate, power, pace, laps and a map, but nothing of a
runner's form even for a file that records it. Once fit-ingest exposes the
running-dynamics channels (fit-ingest Amendment 3), a run page can summarize
them. This amendment appends criteria only: Requirement 6 gains 6.8-6.10 (the
Running Dynamics section: its placement, its rows and units, its omission and
its run-only scope) and Requirement 7 gains 7.7-7.8 (the running-dynamics
chart). **No existing criterion is renumbered, reworded or withdrawn.** The
section and its chart are computed from the activity's channels at render
time; a page whose source records no running-dynamics data, no 0 bpm
heart-rate sample and no session-level developer value that is an invalid
value or a 32-bit float renders as before, apart from its document-format
version. The document-format version advance that brings existing pages
current is owned by the implementing spec `.kiro/specs/running-dynamics/`.
The tests pinning each new criterion are listed in this spec's `spec.json`
`amendments` array.

## Amendment 2 (2026-10-02): Garmin attribution on workout pages, landed by intervals-connector

Pages built from Garmin device data name Garmin only as a manufacturer in the
devices table, never as the data's source, and the table cannot name a Garmin
device's model when the file records only a product code. The
intervals-connector spec fetches Garmin rides through intervals.icu, whose API
terms (section 1.1) and Garmin's API Brand Guidelines require the data's
source to be attributed beside it. Once fit-ingest resolves Garmin product
names (fit-ingest Amendment 5), a page can name the device that recorded it.
This amendment appends criteria only: Requirement 5 gains 5.7-5.12 (the
attribution line, its absent-model and non-Garmin cases, the combined-device
case, the from-content-alone rule, and its generated, frontmatter-free
rendering) and Requirement 6 gains
6.11 (the devices table shows the resolved product name). **No existing
criterion is renumbered, reworded or withdrawn.** The attribution applies to
every Garmin-recorded file, however it arrived. The document-format version
advance that brings existing pages current is owned by the implementing spec
`.kiro/specs/intervals-connector/`, and is not a criterion here. The tests
pinning each new criterion are listed in this spec's `spec.json` `amendments`
array.

## Amendment 3 (2026-10-02): channel provenance, landed by channel-merge

A page may list several archived files of one workout (activity-identity), and
until now only the base was read. `channel-merge` renders a page from the
composition of those files: each channel from exactly one file, the base's
identity, laps and session values kept. This amendment appends criteria only:
Requirement 3 gains 3.7 (a composed document names each channel's file),
Requirement 6 gains 6.12 (its laps, devices and decode errors are the base's)
and Requirement 13 gains 13.4 (a donated channel's gaps stay absent).
**No existing criterion is renumbered, reworded or withdrawn.** A page with no
extra renders as before, apart from its document-format version, whose advance
is owned by the implementing spec `.kiro/specs/channel-merge/`. Each new criterion is
pinned by channel-merge criteria: 3.7 by 4.1-4.3, 6.12 by 1.5 and 5.4, 13.4 by
2.6 (tests are listed in that spec's tasks).

## Introduction

workout-docs is the user-visible layer of fitdocs: the installable `fitdocs`
command that consumes `.fit` files from a directory and writes, per activity,
one rich markdown workout document plus static chart assets into a
user-configured data root. It renders per-sport views (run/ride, weight
training, generic fallback) over the fit-ingest activity model, archives every
source file by content hash for provenance and deduplication, and produces
documents that are first-class PKM pages yet fully readable in any plain
markdown viewer. Two principles govern every requirement: absent data is
omitted honestly, never rendered as a fabricated zero or default; and
generated documents are derived artifacts — regeneration is always safe and
never destroys content the user wrote by hand.

## Boundary Context

- **In scope**: the `fitdocs` command-line tool and its sync workflow; output
  location resolution (data-root contract) and file naming/layout; sha256-keyed
  archival of source `.fit` files with content-hash deduplication; per-sport
  markdown document templates (run/ride, weight training, generic fallback);
  static SVG chart generation (power-vs-HR hero chart with elevation backdrop,
  athlete-zone HR strip); splits tables (device laps and 1 km re-slice);
  device/data-quality section; PKM-compatible YAML frontmatter with provenance;
  idempotent, deterministic re-runs; user-editable document regions preserved
  across regeneration; a reserved training-load placeholder section; packaging
  and installation of the `fitdocs` executable.
- **Out of scope**: `.fit` parsing and metric computation (fit-ingest spec —
  consumed as a library); training-load calculation, the load section's
  computed content, athlete profile creation/persistence, and interactive
  prompting (training-load spec); route maps (deferred for v1 — no tile
  servers in markdown); training cycles/blocks/weekly rollups; structured
  weight-training workout templates (first pass is a free-form user-editable
  section only); non-`.fit` formats; automated `.fit` acquisition.
- **Adjacent expectations**: fit-ingest provides the parsed activity model and
  derived metrics under a versioned schema contract — this feature renders
  from that model and never re-reads FIT binary data itself; training-load
  will later fill the reserved load section, so its placeholder contract must
  be stable and must tolerate sports for which no load is available;
  the reference pkm wiki's frontmatter conventions are compatible targets —
  workout documents define their own `type` and degrade gracefully outside
  any PKM.

## Requirements

### Requirement 1: Sync Command and File Discovery
**Objective:** As an athlete, I want one command that consumes new `.fit`
files from a directory and turns each into a workout document, so that getting
a workout into my knowledge base is a single step after exporting from my
watch.

#### Acceptance Criteria
1. When invoked with a source directory, the fitdocs CLI shall discover files with the `.fit` extension (case-insensitive) in that directory and its subdirectories.
2. When a discovered file has not been processed before, the fitdocs CLI shall produce exactly one workout document plus its chart assets in the data root.
3. If a discovered file cannot be decoded (not a FIT file, or fails integrity checks), the fitdocs CLI shall report a per-file error naming the file and the reason, and shall continue processing the remaining files.
4. When a sync run completes, the fitdocs CLI shall report a summary of documents written, files skipped as already processed, and failures.
5. If any file failed during a sync run, the fitdocs CLI shall exit with a non-zero status; when all discovered files succeed or are skipped, it shall exit with status zero.
6. The fitdocs CLI shall never modify, move, or delete files in the source directory.

### Requirement 2: Data-Root Resolution and Output Layout
**Objective:** As a PKM user, I want the output location resolved by an
explicit contract, so that workout documents land in my wiki (or any directory
I choose) and never silently inside a code repository.

#### Acceptance Criteria
1. When resolving the output location, the fitdocs CLI shall apply this precedence: explicit output flag, then the `FITDOCS_DATA` environment variable, then a `.fitdocs/data-root` pointer file.
2. If no output location can be resolved, the fitdocs CLI shall exit with an instructive error explaining the three configuration options and shall write nothing.
3. The fitdocs CLI shall never fall back to the current working directory or any implicit default location for output.
4. When writing a workout document, the fitdocs CLI shall name it with a date-prefixed kebab-case slug of the form `YYYY-MM-DD-<sport>-<slug>.md`, using the activity's start date.
5. If an activity has no start date, the fitdocs CLI shall still produce a deterministically named document without fabricating a date.
6. If a document name would collide with a document generated from a different activity, the fitdocs CLI shall disambiguate deterministically and shall never overwrite a different activity's document.
7. When writing chart assets, the fitdocs CLI shall place them in a predictable location relative to the document and reference them with relative links, so that moving the data root as a whole never breaks a document.
8. When output directories do not yet exist inside the data root, the fitdocs CLI shall create them.

### Requirement 3: Source Archival and Deduplication
**Objective:** As an athlete, I want every source `.fit` file archived with my
documents, keyed by content hash, so that provenance is permanent and
re-syncing the same exports never duplicates a workout.

#### Acceptance Criteria
1. When processing a `.fit` file, the fitdocs CLI shall archive a copy of the source bytes inside the data root, keyed by the sha256 hash of those bytes.
2. When a discovered file's content hash matches an already archived source, the fitdocs CLI shall skip re-processing it and shall not create a duplicate document, unless the user explicitly requests regeneration.
3. When two differently named files contain identical bytes, the fitdocs CLI shall archive one copy and produce one document.
4. The fitdocs CLI shall record provenance in each generated document identifying the archived source file it was rendered from.
5. The fitdocs CLI shall never modify an archived source file after it is written.
6. When a discovered file records the same stable session identifier as an existing document but its bytes differ (a re-export of the same activity), the fitdocs CLI shall update that document in place — preserving user-authored regions per Requirement 10 — and archive the new source, rather than creating a duplicate document.

> **Note (2026-09-30), recorded by `activity-identity`:** a page may now be
> rendered from one of several archived files of the same workout, listed in
> its `sources` with the **base** last. Criterion 4's "the archived source
> file it was rendered from" is therefore the base -- the last entry of
> `sources`. Criterion 6's update-in-place on a recorded session identifier is
> generalized by `activity-identity`'s Requirements 3 and 4, which decide by a
> stated rule whether a file is the same session as an existing page, and hold
> a file that cannot be placed on one page. No criterion here is renumbered or
> reworded.

7. _(added by Amendment 3)_ When a document is rendered from a composition of several archived source files, the fitdocs CLI shall name in the document the archived source file each composed channel came from, so that the provenance recorded under criterion 4 is also recorded per channel.

### Requirement 4: Idempotent and Deterministic Rendering
**Objective:** As a user re-running sync freely, I want identical inputs to
produce identical outputs, so that re-runs are safe, diffs are meaningful, and
golden-file verification is possible.

#### Acceptance Criteria
1. When rendering the same activity with the same inputs, the fitdocs CLI shall produce byte-identical document and chart output on every invocation, embedding no run-time timestamps, random identifiers, or other nondeterministic content.
2. When a sync run discovers no new files, the fitdocs CLI shall leave the data root unchanged.
3. Where the user explicitly requests regeneration, the fitdocs CLI shall re-render documents from the archived source files, preserving user-authored regions per Requirement 10.
4. The fitdocs CLI shall be able to regenerate every document from the archived `.fit` sources and optional athlete inputs alone, without the original source directory.

### Requirement 5: PKM Frontmatter and Portability
**Objective:** As a PKM user, I want workout documents to slot into my wiki as
first-class pages, and as a plain-markdown user I want them fully readable
anywhere, so that my training log is never locked to one tool.

#### Acceptance Criteria
1. The fitdocs CLI shall begin every workout document with valid YAML frontmatter carrying at minimum: a title, the document type `workout`, the activity date, the sport, key summary metrics, and a `sources` entry pointing to the archived source file.
2. When a frontmatter metric has no recorded or computed value, the fitdocs CLI shall omit that key rather than writing a zero, null, or placeholder value.
3. The fitdocs CLI shall produce document bodies that render as valid, readable markdown in common renderers (Obsidian, GitHub, plain-text viewers) without requiring any plugin.
4. Where PKM-specific affordances are used in a document, the fitdocs CLI shall use only forms that degrade gracefully in vanilla markdown renderers.
5. The fitdocs CLI shall embed charts as standard image links so they display in any renderer that supports images.
6. When the activity records a stable session identifier, the frontmatter shall include it as the document's activity identity.
7. _(added by Amendment 2)_ When the fitdocs CLI renders a workout document from a file whose recording device — the device the file itself names as its creator — is made by Garmin, it shall show a line reading "Garmin" followed by that device's product name directly beneath the document's title and above every section.
8. _(added by Amendment 2)_ If that Garmin recording device's product name is absent, the fitdocs CLI shall show "Garmin" alone in the line, never a placeholder model.
9. _(added by Amendment 2)_ Where a document's recording device is not made by Garmin, or the file names no recording device, the fitdocs CLI shall show no Garmin attribution.
10. _(added by Amendment 2)_ Where a document combines channels from files recorded by different devices and at least one of them is a Garmin device, the fitdocs CLI shall name each contributing Garmin device and state that other devices also contributed, and shall never present Garmin as the source of the whole document.
11. _(added by Amendment 2)_ The fitdocs CLI shall decide the attribution from the files' own content alone, so that the same files yield the same attribution however they arrived.
12. _(added by Amendment 2)_ The fitdocs CLI shall render the attribution as generated content outside every preserved region, refreshed on every regeneration and byte-identical for identical inputs, and shall record it in no frontmatter key.

### Requirement 6: Run and Ride Document View
**Objective:** As a runner or cyclist, I want one strong document per
activity mirroring the reference activity view, so that a glance gives me the
workout's story and details are one scroll away.

#### Acceptance Criteria
1. When an activity's modality is run or bike, the fitdocs CLI shall render a document with these content sections in order: hero summary, telemetry (hero chart and HR-zone strip), splits, and devices/data quality, together with the user-notes region and the training-load placeholder section.
2. The hero summary shall present the sport-aware key stats: distance, moving time (with elapsed time as a sub-value), pace for runs or speed for rides (with best/max as a sub-value), climb (with minimum-to-maximum altitude as a sub-value), average heart rate (with maximum as a sub-value), and for rides power (with normalized power, intensity factor, and training stress sub-values where available).
3. When device laps are present, the splits section shall render a table of device laps with sport-aware columns; when total distance is available, the splits section shall additionally render a 1 km re-slice of the sample stream.
4. The splits section shall visibly mark the fastest and slowest splits and include a totals/summary row.
5. If lap data or distance data required for a splits variant is absent, the fitdocs CLI shall omit that variant while rendering the others.
6. The devices/data-quality section shall list the recording devices with manufacturer, product, and battery status where recorded, and shall surface per-channel data coverage and any decode errors reported for the source file.
7. Where supplemental recorded session values are present (for example estimated perceived exertion or weather humidity), the summary section shall include the recognized ones and omit the rest silently.
8. _(added by Amendment 1)_ When a run page's activity has recorded data in at least one running-dynamics channel, the fitdocs CLI shall include a `## Running Dynamics` section placed after the summary, map and telemetry sections (each when present) and before the splits section (when present); when no running-dynamics channel has recorded data, the section shall be omitted entirely, heading included, and the fitdocs CLI shall include the section only on pages whose activity modality is run.
9. _(added by Amendment 1)_ The Running Dynamics section shall present one row per running-dynamics channel that has recorded data, in a fixed order, each showing the channel's average, its typical range (10th to 90th percentile of recorded samples) and its coverage (the percentage of samples that recorded it), computed over recorded samples only and never counting an absent sample as zero.
10. _(added by Amendment 1)_ The Running Dynamics section shall display ground contact time in milliseconds, vertical oscillation in centimetres, step length in metres, leg spring stiffness in kilonewtons per metre, form and air power in watts, impact in body weights, and vertical ratio and every balance in percent, and shall present each balance channel as its recorded percentage without attributing it to a left or right side.
11. _(added by Amendment 2)_ The devices table shall show each device's product name as the fit-ingest library resolves it.
12. _(added by Amendment 3)_ When a document is rendered from a composition of several archived source files, the splits section's device laps (criterion 3) and the devices/data-quality section's recording devices and decode errors (criterion 6) shall be the base file's alone.

### Requirement 7: Hero Chart Generation
**Objective:** As an athlete, I want the power-vs-heart-rate hero chart
embedded in each document as a static image, so that the workout's effort
profile is visible in any markdown renderer with zero plugins.

#### Acceptance Criteria
1. When an activity has at least one plottable telemetry series (heart rate, power, pace or speed), the fitdocs CLI shall generate a hero chart as a static image asset alongside the document.
2. The hero chart shall plot heart rate and power overlaid by default; when either is absent, it shall fall back to the available series per a documented precedence order.
3. The hero chart shall use cumulative distance as its x-axis when distance data is available, and elapsed time otherwise.
4. The hero chart shall follow the chart specification documented in `docs/reference/fitdocs-ai-reference.md` §3 — per-series band normalization, faint elevation backdrop band, null-skipping boxcar smoothing, and the documented color palette — adapted only where static rendering demands.
5. When samples are missing within a series, the hero chart shall render gaps rather than interpolating fabricated values.
6. If an activity has no plottable telemetry series, the fitdocs CLI shall omit the hero chart and render the rest of the document without error.
7. _(added by Amendment 1)_ When at least one of ground contact time, leg spring stiffness, vertical oscillation, form power, step length or vertical ratio has recorded data, the Running Dynamics section shall include one chart plotting the first two of those channels, in that order, that have recorded data, on the same horizontal axis as the page's telemetry chart (cumulative distance when the activity records distance, otherwise elapsed time), leaving a gap where a charted channel has no recorded sample and never interpolating across it; if none of those channels has recorded data, the section shall render without a chart.
8. _(added by Amendment 1)_ The fitdocs CLI shall generate the running-dynamics chart as a static image asset alongside the document, linked by a standard relative image link, byte-identical for identical inputs and free of scripts.

### Requirement 8: Athlete Zone Inputs and HR-Zone Strip
**Objective:** As an athlete, I want zone-based displays computed from my
actual zones, so that the document never shows zone data invented from
hard-coded defaults.

#### Acceptance Criteria
1. Where athlete heart-rate zone boundaries are available from the optional athlete-inputs source, the fitdocs CLI shall render an HR-zone strip showing time-in-zone as a proportional stacked band.
2. If athlete heart-rate zone boundaries are not available, the fitdocs CLI shall omit the HR-zone strip entirely and shall never substitute default or hard-coded zone boundaries.
3. The fitdocs CLI shall treat the athlete-inputs source as optional and read-only: it shall never prompt for, create, or modify athlete data (profile creation and prompting belong to the training-load feature).
4. Where athlete threshold inputs (functional threshold power, resting or maximum heart rate) are available, the fitdocs CLI shall include the threshold-dependent metrics they enable (intensity factor, training stress, TRIMP); otherwise it shall omit those metrics.

### Requirement 9: Weight-Training Document View
**Objective:** As a lifter recording with a standard watch, I want my document
to show everything the watch captured and give me a clearly marked place to
write down the actual workout, so that the page becomes the complete record
once I fill it in.

#### Acceptance Criteria
1. When an activity's modality is strength, the fitdocs CLI shall render a document with a session summary of the recorded metrics (duration, heart rate, calories, and other values where present), a telemetry section with the heart-rate chart when plottable series exist, the user-editable workout section, the user-notes region, the devices/data-quality section, and the training-load placeholder section.
2. When strength sets are present, the fitdocs CLI shall render a sets table with columns set, reps, load, and rest, grouped per exercise where exercise names were resolved.
3. When a set's exercise name is unresolved, the fitdocs CLI shall present the set under an unnamed/unknown grouping without guessing an exercise name.
4. When a set field was not recorded by the watch, the fitdocs CLI shall leave that cell blank rather than rendering a zero or default, while preserving recorded zeros (for example bodyweight sets) as genuine values.
5. The fitdocs CLI shall include in every weight-training document a clearly marked user-editable section for the actual workout performed as free-form markdown, pre-filled with brief instructive placeholder text when newly generated.
6. When an activity contains no set data at all, the fitdocs CLI shall still render the weight-training document with its summary, telemetry (when available), and user-editable sections, and shall omit the sets table entirely rather than scaffolding empty or fabricated set rows.

### Requirement 10: User-Content Preservation on Regeneration
**Objective:** As a user who writes into my workout documents, I want
regeneration to never destroy what I wrote, so that documents stay derived
artifacts without my notes being at risk.

#### Acceptance Criteria
1. The fitdocs CLI shall delimit every user-editable region in a generated document with explicit, machine-recognizable markers that survive normal markdown editing.
2. When regenerating a document that already exists, the fitdocs CLI shall carry the content of each user-editable region over verbatim into the regenerated document.
3. If an existing document's user-region markers are missing or damaged, the fitdocs CLI shall leave that document untouched and report a per-document conflict error instead of overwriting it.
4. When regenerating a document, the fitdocs CLI shall fully replace generated (non-editable) regions with freshly rendered content.
5. The fitdocs CLI shall include a user-notes editable region in every workout document, and additionally the workout-details editable region in weight-training documents per Requirement 9.

### Requirement 11: Training-Load Placeholder Section
**Objective:** As the training-load feature (downstream), I want every workout
document to reserve a stable, marked training-load section, so that computed
load can be filled in later without disturbing the rest of the document.

#### Acceptance Criteria
1. The fitdocs CLI shall include in every workout document a training-load section delimited by explicit, machine-recognizable markers forming a stable placeholder contract.
2. While no load result is available for an activity — whether not yet computed or because no calculator supports the sport — the training-load section shall render a graceful "not computed" state and shall never display fabricated load values or zeros.
3. The placeholder contract shall allow the training-load feature to replace the section's content without affecting any other section or any user-editable region.
4. The fitdocs CLI shall not compute methodology-based training load itself.

### Requirement 12: Generic Fallback Document View
**Objective:** As an athlete recording any other sport, I want every activity
to still become a useful document, so that no `.fit` file is ever rejected for
being the "wrong" sport.

#### Acceptance Criteria
1. When an activity's modality is neither run, bike, nor strength, the fitdocs CLI shall render a generic document containing frontmatter, a summary of the available metrics, the telemetry chart when plottable series exist, the devices/data-quality section, the user-notes region, and the training-load placeholder section.
2. The fitdocs CLI shall render a document for every successfully parsed activity regardless of sport, and shall never fail solely because a sport is unrecognized.

### Requirement 13: Missing-Data Honesty in Rendering
**Objective:** As a fitdocs user, I want absent data represented honestly in
every document, so that no page ever states a value the device did not record
or the pipeline did not compute.

#### Acceptance Criteria
1. If a metric's value is absent, the fitdocs CLI shall omit it or render an explicit absence marker, and shall never render a zero or fabricated value in its place.
2. When a telemetry channel is entirely absent, the fitdocs CLI shall omit the sections and chart elements that depend on it while rendering all independent content normally.
3. When a device records a true zero (for example zero power while coasting), the fitdocs CLI shall present it as a genuine recorded value.
4. _(added by Amendment 3)_ When a channel is taken from another of a document's source files than the base, the fitdocs CLI shall leave every sample of the document at which no value of that channel was placed from that file absent, render it as absent under criteria 1 and 2, and never fill it from any other file or invent a value there.

### Requirement 14: Packaging and Installation
**Objective:** As a user, I want fitdocs installable as a standalone
command-line tool, so that setup is one command and the tool works fully
offline.

#### Acceptance Criteria
1. The fitdocs package shall be installable with standard Python tool installers (for example `uv tool install` or `pipx`) and shall expose a `fitdocs` executable as its console entry point.
2. When invoked with `--help`, the fitdocs CLI shall document its commands and options; when invoked with `--version`, it shall report the installed version.
3. The fitdocs CLI shall run on Python 3.11 or newer.
4. The fitdocs CLI shall operate fully offline, requiring no network access for any operation.
