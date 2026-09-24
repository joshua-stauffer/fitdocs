# Brief: running-dynamics

## Problem

A runner with a Stryd footpod records, second by second:
- form power, air power, leg spring stiffness and impact;
- four balance channels;
- ground contact time and vertical oscillation;
- step length.

Watches with running-dynamics sensors record the native subset. fitdocs
reads none of it. The athlete's reason for pulling from the source (Phase 8)
is exactly this data: Apple Health has no fields for it, so HealthFit's
copies lack it. A Stryd file handed to fitdocs today renders the same page as
the HealthFit copy, minus the HealthFit summaries.

## Current State

- **`Samples` has ten native channels** (`src/fitdocs/model.py:97-115`):
  time, HR, power, cadence, speed, distance, altitude, latitude, longitude,
  temperature. `ingest/records.py:94-115` fills them from native record
  fields only.
- **Developer fields are read from the session only**
  (`ingest/summary.py:146-228`, `session_mesgs[0]`, with a declared scale
  and offset applied). Record-level developer fields are dropped. The only
  developer fields rendered are HealthFit's humidity and METs
  (`render/sections.py:84-114, 240-261`), with a hardcoded hundredths scale
  keyed on field name (queue `2026-07-25-supplemental-scale-single-writer`).
- **Native `step_length`, `vertical_oscillation`, `stance_time`,
  `stance_time_balance` and `vertical_ratio` are dropped**, as are
  fractional cadence and GPS accuracy.
- **No running-dynamics section, chart or coverage row exists**
  (`render/sections.py:116-127` is the coverage table).

What the files actually carry (measured on three Stryd files and their
HealthFit copies, viability check 2026-09-24; shapes only):
- **Stryd records (1 Hz).** Native: timestamp, position, distance, altitude,
  speed/enhanced speed, power, HR (from the watch), cadence, `step_length`
  (mm), `vertical_oscillation` (mm), `stance_time` (ms),
  `stance_time_balance` (%). Developer: Form Power (W), Air Power (W), Leg
  Spring Stiffness (kN/m, float), Impact (body weights), three balance
  channels (%), Stryd Temperature (°C), Stryd Humidity (%), and duplicate
  Speed and Distance. The session carries a "Run Profile" string. No scale
  is declared on any developer field. All eleven numeric developer fields and
  the four native dynamics are present on 100% of records.
- **HealthFit copies** have `vertical_oscillation`, `stance_time`,
  `vertical_ratio`, fractional cadence and GPS accuracy. They lack
  `stance_time_balance` and every Stryd developer field.
- **garmin-fit-sdk returns developer data** on every message as
  `developer_fields`. Consumers must handle four things:
  - it is keyed by the index of the `field_description` message, **not** by
    the field definition number (in Stryd files key 0 is "Air Power",
    definition 11);
  - values are raw, with no declared scale applied and no invalid sentinels
    filtered;
  - arrays come back as lists, and floats carry float32 noise (27.2199…);
  - the first definition of a repeated (developer index, definition number)
    pair wins.
- **Stryd sets native-message numbers 6/5/13** on its Speed, Distance and
  Temperature descriptions, a spec violation. The SDK stores and never uses
  them; consumers must ignore them too.
- **Quirks of a Stryd file as a page's only file:**
  - zeros written as values at the first sample and around pauses (HR 0 in
    four samples);
  - no session average or max HR, even though the HR stream is full;
  - `session.num_laps` = 1 alongside 4 or 15 lap messages;
  - `session.timestamp` is the last lap's start, not the end;
  - laps without HR or cadence;
  - humidity above 100%.

## Desired Outcome

- **Generic record-level developer fields.** Each is read by its field
  description (name, units, declared scale and offset, base type's invalid
  value filtered), with float noise rounded to the field's resolution. It is
  available on the model under its description's name, with provenance
  (developer data index / application id).
- **Running dynamics as first-class channels.** Native step length, vertical
  oscillation, stance time and its balance, and vertical ratio become sample
  channels. So do Stryd's channels, recognized by name: form power, air
  power, leg spring stiffness and its balance, impact and its loading-rate
  balance, vertical oscillation balance. Units are normalized and absent
  values are `None`.
- **Stryd files are safe as a page's only file.** Zero-at-pause values do not
  become data. A missing session HR summary is derived from the stream or
  left `None`, by a stated rule. Lap and session inconsistencies do not
  produce wrong summary numbers. Implausible environmental values are
  bounded or dropped, by a stated rule.
- **Run pages show it.** A running-dynamics section (averages and
  distributions of the channels present, with coverage rows) and at least one
  chart. For example: form power ratio or leg spring stiffness over time,
  and ground contact time vs pace. The section is omitted, not rendered
  empty, when no dynamics channel is present.
- **Existing pages are unaffected.** A page with no dynamics renders
  byte-identically, apart from any coverage-row addition the design
  justifies.

## Approach

- **Ingest.** Widen ingest with a record-level developer-field reader beside
  the session one, sharing the scale and invalid handling. Add the dynamics
  channels to `Samples`, or to an optional companion structure the design
  chooses, so that channel-generic consumers (`channel-merge`) can iterate
  them.
- **Render.** Add the section and charts under the per-sport run view,
  following the existing SVG chart conventions.

## Scope

- **In**:
  - the record-level developer-field reader;
  - native dynamics fields;
  - Stryd channel recognition by name;
  - the zero/invalid policy;
  - the Stryd-file summary quirks;
  - the run-page section, charts and coverage rows;
  - the doc-version bump if the page changes shape;
  - golden fixtures.
- **Out**:
  - merging a Stryd file into a HealthFit page (`channel-merge`);
  - matching the two (`activity-identity`);
  - fetching Stryd files (no shipped connector; see the roadmap's Phase 8
    decisions);
  - running-power load models (RSS, GOVSS);
  - cycling dynamics (a follow-on);
  - rendering developer fields other than dynamics on pages (they are
    available on the model; rendering them is a later choice).

## Boundary Candidates

- The developer-field reader (generic, record- and session-level).
- The dynamics channels (model plus ingest mapping).
- Stryd-file summary quirks.
- The run-page section and charts.

## Out of Boundary

- Which file a merged page takes each channel from (`channel-merge`).
- Any metric that changes load, zones or thresholds.

## Upstream / Downstream

- **Upstream**: `fit-ingest` (decode, `prefer_enhanced`, session
  developer fields); `workout-docs` (run view, chart conventions).
- **Downstream**: `channel-merge` donates these channels from a Stryd extra
  to a HealthFit base; a future Stryd-aware load or benchmark would read
  them.

## Existing Spec Touchpoints

- **Extends**:
  - `fit-ingest`: the record-level developer fields and dynamics channels;
  - `workout-docs`: the run-page section and charts;
  - `wiki-contract`: only if a frontmatter key is added. A body-only section
    needs no contract change beyond the doc version.
- **Adjacent**:
  - `activity-qa-flags`: a dynamics channel may deserve a plausibility flag;
  - the supplemental-scale queue item, which a generic developer-field
    reader should subsume or explicitly leave alone.

## Constraints

- **Absent is `None`**, including Stryd's zeros at pauses and every invalid
  sentinel. A summary over a channel with gaps states its coverage.
- **Determinism**: charts are hand-generated SVG, byte-identical for the
  same inputs.
- **Fixtures are synthesized FIT files** reproducing the measured shapes
  (developer field descriptions in Stryd's order, the index-vs-definition
  offset, the invalid native-message slot, zeros at pauses). No personal
  files.
- **Named mutations**: keying developer fields by definition number, dropping
  the invalid filter, or treating 0 as data must each turn a test red.
- **No new runtime dependencies.**
