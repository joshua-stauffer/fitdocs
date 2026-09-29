# Requirements Document

## Project Description (Input)
A runner who records with a Stryd footpod, or with a watch that has
running-dynamics sensors, carries second-by-second running-form data in their
`.fit` files: ground contact time and its balance, vertical oscillation,
vertical ratio and step length (native FIT fields), and, from Stryd, form
power, air power, leg spring stiffness, impact and three further balance
channels (developer fields). fitdocs reads none of it today. `Samples` has ten
native channels, record-level developer fields are dropped (only the session's
are read), the native dynamics fields are dropped, and no page shows running
form. A Stryd file handed to fitdocs renders the same page as its HealthFit
copy, minus the HealthFit summaries, and it is unsafe as a page's only file:
it writes zeros at pauses and at the first sample, carries no session heart-rate
summary, states a wrong lap count, and stamps the session with a timestamp that
is not its end.

This feature reads record-level developer fields generically by their field
descriptions, exposes the native and Stryd running dynamics as sample channels
that channel-generic consumers can enumerate, applies a stated zero and
invalid-value policy so placeholders never become data, makes a Stryd file safe
as a page's only file, and adds a running-dynamics section with a chart to run
pages. It lands fitdocs Phase 8's Existing Spec Updates for `fit-ingest`
(record-level developer fields and running dynamics) and `workout-docs` (a
running-dynamics section on run pages). Discovery context:
`.kiro/specs/running-dynamics/brief.md` and the roadmap's
`### Phase 8 — source connectors` section.

## Introduction

Phase 8 lets the athlete pull the files that phone-side copies never carried.
For a runner with a Stryd footpod, the whole reason to pull the Stryd file is
its running-dynamics data: Apple Health has no fields for it, so HealthFit's
copies lack it. This feature makes that data readable and visible. It is
useful on a single Stryd file with no merge at all; combining a Stryd file
with a HealthFit copy of the same run is `channel-merge`'s work, which consumes
the channel set this feature publishes.

Two principles govern every requirement: absent data is `None`, never a
fabricated zero (a Stryd zero at a pause is a placeholder, not a measurement);
and fitdocs decodes what a file declares but never infers a convention the file
does not declare.

## Boundary Context

- **In scope**:
  - reading record-level developer fields by their field descriptions, with
    the declared scale and offset, the base type's invalid value, and 32-bit
    float noise handled, and with their provenance;
  - the session-level developer-field reader sharing that decoding;
  - the native running-dynamics fields as sample channels;
  - Stryd's running-dynamics developer fields recognized by exact name as
    sample channels;
  - the placeholder-zero and pause policy, including heart rate;
  - the Stryd-file summary quirks (missing session heart rate, wrong lap
    count, a session timestamp that is not the end, laps without heart rate
    or cadence, environmental values out of physical range);
  - the Running Dynamics section and its chart on run pages;
  - the document-format version advance;
  - synthesized fixtures reproducing the measured Stryd shapes;
  - the amendment records for `fit-ingest` and `workout-docs`, and this
    feature's part of the roadmap bookkeeping for those two updates.
- **Out of scope**:
  - composing a Stryd file with a HealthFit copy of the same run
    (`channel-merge`), and deciding that two files are the same run
    (`activity-identity`);
  - fetching Stryd files (no shipped Stryd connector; see the roadmap's
    Phase 8 decisions);
  - running-power load models, and any new metric that changes load, zones or
    thresholds. The heart-rate placeholder rule corrects the input the
    existing heart-rate metrics read for a file that records 0 bpm; it adds
    no metric;
  - cycling dynamics, fractional cadence and GPS accuracy;
  - rendering any developer field other than the running-dynamics channels on
    a page (the rest are available on the activity model only);
  - plausibility flags for dynamics channels (`activity-qa-flags`);
  - Garmin device naming and attribution (`intervals-connector`).
- **Adjacent expectations**:
  - `channel-merge` enumerates the published channel set to donate the
    channels a base file lacks. No session or derived summary is fed by a
    running-dynamics channel, so a donated dynamics channel needs no summary
    recomputation; the Running Dynamics section is computed from the channels
    at render time.
  - `activity-identity` adds file-identity fields to the activity model in the
    same release cycle; both changes are additive.
  - HealthFit's session humidity and METs rows keep their current rendering.
    The open queue item `2026-07-25-supplemental-scale-single-writer` is
    explicitly left alone: nothing here infers an undeclared scale.
  - The published ownership contract and the frontmatter's managed keys are
    unchanged; only the document-format version advances.

## Requirements

### Requirement 1: Record-Level Developer Fields Read by Field Description
**Objective:** As a downstream feature author, I want every described
developer field a file records on its samples exposed generically, correctly
decoded and with its provenance, so that exporter-specific per-sample data
reaches consumers without fitdocs guessing what it means.

#### Acceptance Criteria
1. When a file's record messages carry developer fields that the file describes, fitdocs shall expose each such field on the activity model under its described name, as one value per sample, index-aligned with the activity's sample channels.
2. When a file's field descriptions appear in an order that differs from their field definition numbers, fitdocs shall expose each recorded value under the name of the description it was recorded against, never under the name of a different description whose field definition number happens to equal the recorded description's position in the file.
3. fitdocs shall expose with each record-level developer field its declared units, its developer data index, its field definition number, and the application identifier of its developer, where the file records one.
4. When a field description declares a scale and/or an offset, fitdocs shall decode each value of that field with the FIT formula `value / scale - offset`, treating an undeclared term as its identity; if a description declares a scale of 0, then fitdocs shall omit that field entirely.
5. If a recorded developer value equals the invalid value of its declared base type, or is a non-finite floating-point value, then fitdocs shall treat that sample's value as not recorded (`None`).
6. If every element of a recorded developer array equals its base type's invalid value, then fitdocs shall treat the array as not recorded; an array with at least one valid element shall pass through unchanged, element for element.
7. When a developer field's base type is a 32-bit float, fitdocs shall express each value as the shortest decimal number that denotes the same 32-bit value (a recorded 11.369999885559082 is exposed as 11.37).
8. If a file describes the same developer data index and field definition number twice, then fitdocs shall decode that field's values against the first description and shall not expose the later description's name.
9. If two described fields that are both recorded share a name, then fitdocs shall expose the one described last in the file under that name and omit the other, the same rule the session-level reader applies.
10. fitdocs shall ignore any native message or native field number a field description carries: a developer field shall never fill, replace or override a native channel.
11. If a described field is recorded on no sample, or every value it records is treated as not recorded under criteria 5 and 6, then fitdocs shall omit it; an activity with no such field shall expose an empty collection, and this shall not be an error.
12. fitdocs shall not infer a scale, unit, or other convention that a field's description does not declare.

### Requirement 2: Session-Level Developer Fields Share the Decoding
**Objective:** As a fitdocs user, I want session-level developer values decoded
by the same rules as sample-level ones, so that an invalid sentinel never
becomes a session value while everything I rely on today stays as it is.

#### Acceptance Criteria
1. When fitdocs decodes a session-level developer value, fitdocs shall apply the invalid-value, array and 32-bit float rules of Requirement 1 criteria 5-7 in addition to the declared scale and offset it already applies.
2. fitdocs shall expose every session-level developer value that is neither an invalid value nor a 32-bit float exactly as it did before this feature, including a 16-entry session identifier whose entries include the value 255.
3. fitdocs shall keep a page's stable session identity, and its humidity and average-METs summary rows, exactly as they rendered before this feature.

### Requirement 3: Native Running Dynamics as Sample Channels
**Objective:** As a runner whose watch or sensor records running dynamics, I
want them available as per-sample channels next to heart rate, power and pace,
so that pages and later features can read my running form.

#### Acceptance Criteria
1. When a file's records carry native step length, vertical oscillation, stance time, stance time balance or vertical ratio, fitdocs shall expose each as a per-sample channel aligned with the existing channels: step length and vertical oscillation in millimetres, stance time in milliseconds, stance time balance and vertical ratio in percent.
2. When a native dynamics value is absent at a sample, fitdocs shall hold `None` for that channel at that sample.
3. When a file records no running-dynamics data, fitdocs shall hold `None` in every running-dynamics channel at every sample.
4. The fitdocs activity model shall publish the set of running-dynamics channel names, and each named channel shall be a member of the same per-sample channel set as heart rate, power and speed, so that a consumer can enumerate every channel without naming each one.

### Requirement 4: Stryd Running Dynamics Recognized by Name
**Objective:** As a Stryd runner, I want the running-form channels my footpod
records as developer fields treated as first-class channels, so that a Stryd
file's reason for existing reaches my pages.

#### Acceptance Criteria
1. When a file's records carry developer fields named exactly `Form Power`, `Air Power`, `Leg Spring Stiffness`, `Impact`, `Leg Spring Stiffness Balance`, `Impact Loading Rate Balance` or `Vertical Oscillation Balance`, fitdocs shall expose them as the running-dynamics channels form power and air power (watts), leg spring stiffness (kilonewtons per metre), impact (body weights), and leg spring stiffness balance, impact loading rate balance and vertical oscillation balance (percent).
2. fitdocs shall take a recognized channel's values from the decoded developer field of Requirement 1, with no unit conversion beyond the scale and offset the description declares.
3. If a developer field's name is not one of the names in criterion 1 (for example `Power`, `Speed`, `Distance`, `Stryd Temperature` or `Stryd Humidity`), then fitdocs shall not expose it as a running-dynamics channel and shall not use it to fill any native channel; it shall remain available as a generic record-level developer field.
4. fitdocs shall recognize these channels by name whichever application wrote the file.

### Requirement 5: Placeholder Zeros and Pauses
**Objective:** As a runner, I want the zeros a device writes when it has no
reading to be treated as missing, so that pauses and the first sample never
drag my averages, charts and heart-rate metrics down.

#### Acceptance Criteria
1. If a record's heart rate is 0, then fitdocs shall hold `None` for heart rate at that sample.
2. If a record's stance time, vertical oscillation, vertical ratio, step length, leg spring stiffness, impact or form power is 0, then fitdocs shall hold `None` for that channel at that sample.
3. While a sample's stance time, vertical oscillation, leg spring stiffness or impact is `None`, fitdocs shall hold `None` at that sample for the balance channel paired with it (stance time balance with stance time, vertical oscillation balance with vertical oscillation, leg spring stiffness balance with leg spring stiffness, impact loading rate balance with impact); otherwise fitdocs shall hold the recorded balance, including a recorded 0.
4. While a sample's form power is `None`, fitdocs shall hold `None` for air power at that sample; otherwise fitdocs shall hold the recorded air power, including a recorded 0.
5. fitdocs shall keep recorded zeros of power, cadence, speed, distance, altitude and temperature as genuine recorded values.
6. fitdocs shall apply criteria 1-4 identically whichever application wrote the file.

### Requirement 6: A Stryd File as a Page's Only File
**Objective:** As a Stryd runner syncing a Stryd file on its own, I want a
correct page, so that the file's own inconsistencies never produce a wrong
number.

#### Acceptance Criteria
1. If a file's session records no average or maximum heart rate while its records carry heart rate, then fitdocs shall report the page's average and maximum heart rate from the recorded heart-rate samples, excluding the placeholder zeros of Requirement 5.
2. fitdocs shall render one device-lap row per lap the file records, whatever lap count the session message states.
3. fitdocs shall take the page's elapsed and moving time from the session's elapsed and timer totals, and shall not derive either from the session message's timestamp.
4. If a lap records no heart rate or cadence, then fitdocs shall present each missing lap value it shows with the absence marker, never as a zero or a value taken from elsewhere.
5. fitdocs shall render no record-level environmental developer value (Stryd's temperature or humidity) on any page, so a recorded value outside its physical range, such as humidity above 100%, never reaches a page; such values shall remain available on the activity model as decoded.
6. When a file reproducing every measured Stryd shape is synced as its activity's only file, fitdocs shall write a run page carrying the Running Dynamics section, without error.

### Requirement 7: The Running Dynamics Section on Run Pages
**Objective:** As a runner, I want my running form summarized on each run
page, so that I can see ground contact, oscillation, stiffness and form power
at a glance.

#### Acceptance Criteria
1. When a run page's activity has recorded data in at least one running-dynamics channel, fitdocs shall include a `## Running Dynamics` section placed after the Summary, Map and Telemetry sections (each when present) and before the Splits section (when present).
2. The Running Dynamics section shall present one row per running-dynamics channel that has recorded data, in a fixed order, each showing the channel's average, its typical range (10th to 90th percentile of recorded samples) and its coverage (the percentage of samples that recorded it).
3. fitdocs shall compute every average, range and coverage in the section over recorded samples only, never counting an absent sample as zero.
4. fitdocs shall display ground contact time in milliseconds, vertical oscillation in centimetres, step length in metres, leg spring stiffness in kilonewtons per metre, form and air power in watts, impact in body weights, and vertical ratio and every balance in percent.
5. fitdocs shall present each balance channel as its recorded percentage, without attributing it to a left or right side.
6. If no running-dynamics channel has recorded data, then fitdocs shall omit the section entirely, heading included.
7. fitdocs shall include the section only on pages whose activity modality is run; ride, strength and generic pages shall not include it.

### Requirement 8: The Running Dynamics Chart
**Objective:** As a runner, I want a chart of my running form over the run,
so that I can see how it held up.

#### Acceptance Criteria
1. When at least one of ground contact time, leg spring stiffness, vertical oscillation, form power, step length or vertical ratio has recorded data, the Running Dynamics section shall include one chart plotting the first two of those channels, in that order, that have recorded data.
2. The chart shall use the same horizontal axis as the page's telemetry chart: cumulative distance when the activity records distance, otherwise elapsed time.
3. While a charted channel has no recorded value at a sample, the chart shall leave a gap there and shall never interpolate across it.
4. fitdocs shall generate the chart as a static image next to the document, linked by a standard relative image link, byte-identical for identical inputs and free of scripts.
5. If none of the chartable channels in criterion 1 has recorded data, then fitdocs shall render the section without a chart.

### Requirement 9: Existing Pages and the Document-Format Version
**Objective:** As an athlete with an existing workout library, I want pages
without running dynamics left as they are, and pages that gain the section
brought current by the regeneration I already know, so that upgrading is one
command.

#### Acceptance Criteria
1. When a page's source file records no running-dynamics data, no 0 bpm heart-rate sample, and no session-level developer value that is an invalid value or a 32-bit float, fitdocs shall render its document and chart images byte-identically to how fitdocs rendered them immediately before this feature landed, apart from the recorded document-format version.
2. fitdocs shall advance the document-format version by exactly one from the value current when this feature lands, so that every document written before it is reported stale by `fitdocs check` and brought current by `fitdocs regen`.
3. When `fitdocs regen` rewrites a run page written before this feature whose source records running dynamics, fitdocs shall add the Running Dynamics section and preserve every user-owned region and user-owned frontmatter key.
4. fitdocs shall add no frontmatter key and shall leave the published ownership contract's version unchanged.
5. The fitdocs release notes shall state, under the unreleased entry, that run pages gain a Running Dynamics section and that the document-format change is resolved by running `fitdocs regen`.

### Requirement 10: Determinism, Dependencies and Evidence
**Objective:** As a fitdocs maintainer, I want this feature deterministic,
dependency-free and proven by tests that can fail, so that the public
repository stays reproducible and honest.

#### Acceptance Criteria
1. When given identical input bytes and identical athlete inputs, fitdocs shall produce an identical activity model, an identical document and byte-identical chart images.
2. fitdocs shall add no runtime dependency.
3. The fitdocs test suite shall use only synthesized `.fit` fixtures that reproduce the measured Stryd shapes (description order differing from definition numbers, the misused native-message number on the duplicated Speed, Distance and Temperature descriptions, zeros at the first sample and around pauses, no session heart-rate summary, a session lap count of 1 beside several laps, a session timestamp equal to the last lap's start, laps without heart rate or cadence, humidity above 100%), and no personal file, name, date or value.
4. If developer values are paired with descriptions by field definition number, or the invalid-value filter is dropped, or a placeholder zero is kept as data, then the fitdocs test suite shall fail.
5. The fitdocs repository shall name no Stryd web or service endpoint in this feature's code, tests, specification or documentation.
